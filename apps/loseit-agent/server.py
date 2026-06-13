"""Slice S6: FastAPI service for a Kitaru-wrapped 5-tool pydantic-ai agent.

This slice expands the S4/S5 single-`search` agent into the full 5-tool agent
ported from `tools/agent-sandbox/agent.py` (the v7 reference that produced the
successful 4-food log run). Tools:

    search          — query the Lose It! food DB
    describe_food   — inspect 1+ food_ids (units, conversions, nutrients)
    log_food        — write an entry to the diary
    diary           — read the diary for a date
    whoami          — print resolved loseit identity

The pydantic-ai Agent is wrapped in `KitaruAgent`, so every `POST /run` becomes
a durable Kitaru execution with per-call checkpoints visible in the Kitaru UI.
The SSE wire format on `POST /run` is preserved verbatim from S4/S5 — the Pipe
and selftest already speak it:

    data: {"kind":"tool",       "name":"<tool>", "args_preview":"<arg>", "call_id":"..."}
    data: {"kind":"tool_done",  "call_id":"<same id>"}
    data: {"kind":"model_call", "turn": N}
    data: {"kind":"final",      "text":"..."}
    data: {"kind":"error",      "message":"..."}

Auth: `Authorization: Bearer <token>` where the token equals the
`AGENT_TOKEN_EXPECTED` env var. `/healthz` is unauthenticated so kubelet probes
work without a token.

Loseit credentials: at startup we fetch the `loseit-token` secret from Kitaru's
centralized secrets store (its API at $KITARU_SERVER_URL, authenticated via
$KITARU_API_KEY). The secret carries four keys — `token`, `user_id`,
`user_name`, `hours_from_gmt`. The JWT is written to ~/.config/loseit/token
(chmod 600) and the identity fields are exported as `LOSEIT_*` env vars so the
lose-it CLI's pydantic-settings loader picks them up automatically. No K8s
Secret for the loseit JWT — per SPEC §"Agent ↔ Lose It!".

Kitaru auth: the K8s Secret exposes `KITARU_API_KEY` + `KITARU_SERVER_URL`.
The Kitaru Python client (used both indirectly by `KitaruAgent` to record
runs and directly by us for secret fetch) reads `KITARU_AUTH_TOKEN` and
`KITARU_SERVER_URL` from the environment — no `kitaru.login()` call is
required for service-account API keys. We bridge `KITARU_API_KEY` →
`KITARU_AUTH_TOKEN` at import time so the manifest doesn't need to set both.

Slice S7 adds: kitaru.wait()-based clarification + /resume endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartStartEvent,
    ToolCallPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("loseit-agent")

EXPECTED_TOKEN = os.environ.get("AGENT_TOKEN_EXPECTED", "")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://ollama.ollama.svc.cluster.local:11434/v1")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
LOSEIT_BIN = os.environ.get("LOSEIT_BIN", "loseit")
LOSEIT_TOKEN_PATH = Path(os.environ.get("LOSEIT_TOKEN_PATH", "/home/agent/.config/loseit/token"))

KITARU_SERVER_URL = os.environ.get("KITARU_SERVER_URL", "")
KITARU_API_KEY = os.environ.get("KITARU_API_KEY", "")
KITARU_LOSEIT_SECRET_NAME = os.environ.get("KITARU_LOSEIT_SECRET_NAME", "loseit-token")

# Bridge our K8s-Secret-style env vars to the names the Kitaru Python client
# expects. The client (and the KitaruAgent runtime that records executions to
# the Kitaru server) auto-picks up `KITARU_AUTH_TOKEN` + `KITARU_SERVER_URL`
# from os.environ — no explicit `kitaru.login()` needed for a service-account
# API key. We keep `KITARU_API_KEY` as the canonical secret-key name in the
# manifest because that's what `kitaru auth api-keys create` mints, and
# bridge it here so we don't have to set the same value twice on the pod.
if KITARU_API_KEY and not os.environ.get("KITARU_AUTH_TOKEN"):
    os.environ["KITARU_AUTH_TOKEN"] = KITARU_API_KEY

# Default to the `default` project — Kitaru's SDK refuses to talk to a remote
# server without an active project (KitaruUsageError), and `default` is the
# project the kitaru server auto-creates on first boot. We also set the
# ZenML-flavored env vars because the underlying ZenML stack honors those
# directly; setting both means it doesn't matter which layer wins. The
# operator can override KITARU_PROJECT (and the ZenML twins) via a future
# manifest tweak if we ever go multi-project.
os.environ.setdefault("KITARU_PROJECT", "default")
os.environ.setdefault("ZENML_ACTIVE_PROJECT_ID", "default")
os.environ.setdefault("ZENML_PROJECT", "default")


# ------------------------------------------------------------------ startup --

def _fetch_loseit_creds_from_kitaru() -> None:
    """Fetch the `loseit-token` secret from Kitaru and materialize CLI creds.

    The Kitaru secret holds four assignments: `token`, `user_id`, `user_name`,
    `hours_from_gmt`. We write the JWT to ~/.config/loseit/token (chmod 600)
    and set the three identity values as `LOSEIT_*` env vars so the lose-it
    CLI's pydantic-settings loader picks them up.

    On failure we log clearly and leave the file/env unset. The agent will
    still boot — only `search` calls will fail until the credentials are
    fixed, and the SSE `error` event surfaces that in chat.
    """
    if not KITARU_SERVER_URL or not KITARU_API_KEY:
        logger.error(
            "Kitaru creds env vars missing (KITARU_SERVER_URL/KITARU_API_KEY); "
            "skipping loseit secret fetch"
        )
        return

    base = KITARU_SERVER_URL.rstrip("/")
    headers = {"Authorization": f"Bearer {KITARU_API_KEY}"}
    try:
        with httpx.Client(timeout=10.0) as client:
            # Resolve secret-name → secret-id.
            r = client.get(
                f"{base}/api/v1/secrets",
                params={"name": KITARU_LOSEIT_SECRET_NAME, "hydrate": "false"},
                headers=headers,
            )
            r.raise_for_status()
            items = r.json().get("items", [])
            if not items:
                logger.error("Kitaru secret %r not found", KITARU_LOSEIT_SECRET_NAME)
                return
            secret_id = items[0]["id"]

            # Hydrate the secret to get its values.
            r = client.get(
                f"{base}/api/v1/secrets/{secret_id}",
                params={"hydrate": "true"},
                headers=headers,
            )
            r.raise_for_status()
            values: dict[str, str] = r.json().get("body", {}).get("values", {}) or {}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Kitaru fetch for %r failed: %s", KITARU_LOSEIT_SECRET_NAME, exc)
        return

    token = values.get("token", "")
    if not token:
        logger.error("Kitaru secret %r has no `token` key", KITARU_LOSEIT_SECRET_NAME)
        return
    LOSEIT_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOSEIT_TOKEN_PATH.write_text(token)
    LOSEIT_TOKEN_PATH.chmod(0o600)
    logger.info(
        "loseit-token: fetched from Kitaru, %d bytes → %s", len(token), LOSEIT_TOKEN_PATH
    )

    # Expose the rest as env vars consumed by lose-it's pydantic-settings loader.
    for key in ("user_id", "user_name", "hours_from_gmt"):
        if key in values:
            os.environ[f"LOSEIT_{key.upper()}"] = str(values[key])
            logger.info("loseit env: LOSEIT_%s set", key.upper())


# ------------------------------------------------------------ user-today ----
#
# Lose It! stores log entries by UTC date but the CLI's `diary` defaults to
# user-local date. Forcing both sides to the SAME local date by passing
# `on_date` everywhere avoids the "logged today, missing from diary" mismatch.
# The reference sandbox reads the offset from ~/.config/loseit/config.yaml; in
# our service the offset is shipped via the Kitaru secret (parsed into
# LOSEIT_HOURS_FROM_GMT). Since the secret fetch is a startup hook that runs
# AFTER module import (we can't reorder it — the FastAPI app + KitaruAgent
# need to construct before lifespan starts), the env var may not be set yet
# here. Fall back to "-6" (US Mountain) — that matches the operator's locale
# and any future GMT correction can be picked up at the next pod restart.

def _user_today() -> str:
    raw = os.environ.get("LOSEIT_HOURS_FROM_GMT", "-6")
    try:
        offset_hours = int(raw)
    except ValueError:
        offset_hours = -6
    local_now = datetime.now(timezone.utc) + timedelta(hours=offset_hours)
    return local_now.date().isoformat()


USER_TODAY = _user_today()


# ------------------------------------------------------------------ agent ----

_model = OpenAIChatModel(
    OLLAMA_MODEL,
    provider=OpenAIProvider(base_url=OLLAMA_BASE_URL, api_key="ollama"),
)

# Ported verbatim from tools/agent-sandbox/agent.py (the v7 reference that
# produced the successful 4-food log run). The only deltas vs the sandbox:
#   - USER_TODAY is computed from the LOSEIT_HOURS_FROM_GMT env var (which
#     the Kitaru-fetched loseit secret materializes) instead of from a
#     config.yaml file on disk — there's no config.yaml inside the container.
#   - The "Be concise. Don't narrate." footer is preserved; the model needs
#     this even more in chat context because verbose reasoning eats into
#     Pipe-side responsiveness.
SYSTEM_PROMPT = f"""You log meals to Lose It! by driving the `loseit` CLI via tools.

Today (user's local date) is {USER_TODAY}. Always pass `on_date="{USER_TODAY}"` to `log_food` and `diary`.

For EACH food the user mentions:
  1. `search` with the BARE food noun ONLY (e.g. "guacamole", "asparagus") — DO NOT include
     user modifiers like "homemade", "fresh", "cooked" in the query. The DB is full of brand
     entries that match those words and they're often the WORST entries for gram-based logging.
  2. `describe_food` on at least the TOP 3 food_ids from that search (one batched call).
     Mandatory — the #1 result is often a brand entry that doesn't support grams; #2-#3 are
     usually plain entries that DO.
  3. Pick the candidate that supports the user's stated unit:
     - User said grams → entry needs `primary_serving.unit == "grams"` OR
       `cross_class_conversion.per_serving_g != null` (a number, NOT null).
     - If none of those 3 support grams, RE-SEARCH with a different bare noun ("avocado dip",
       "avocado mash") and describe the top 3 again. Up to 3 rounds.
     - Sanity-check calories: lentils ~115/100g, asparagus ~20/100g, potatoes ~70/100g, guacamole ~150/100g.
  4. `log_food` (no dry_run) with the chosen food_id, the user's AMOUNT and UNIT EXACTLY as the user said it
     (do not convert), meal=snacks unless stated, on_date.
  5. After all foods, `diary(on_date="{USER_TODAY}")` and confirm each appears with sane calories.

NEVER convert "100g" to tablespoons, teaspoons, or fluid ounces. NEVER compute serving counts > 30
of any spoon unit — that's always a math error. If you can't find an entry that supports the user's
unit, log the food in its native unit at `servings=1.0` and note the limitation in your summary.

Meal rules: explicit meal wins; time-of-day cue infers; else default to `snacks` — NEVER ask.

Units: "Xg" → serving_amount=X, serving_unit="g". "N cup" → serving_amount=N, serving_unit="cup". Bare "oz" is rejected.

Splitting: "255g evenly split between A, B, C" → log 255/3 ≈ 85g of each.

Be concise. Don't narrate. When you're done, return one line summarizing what you logged."""

# `name=` is REQUIRED by KitaruAgent (it's how runs are grouped in the UI).
# Setting it on the inner Agent also gives KitaruAgent a sensible default if
# we forget to pass `name=` again at the wrapping layer.
_inner_agent: Agent[None, str] = Agent(
    _model,
    name="loseit-agent",
    system_prompt=SYSTEM_PROMPT,
    retries=2,
)


def _run_loseit(args: list[str], *, json_output: bool = True) -> str:
    """Subprocess `loseit [-o json] <args...>` and return stdout.

    Errors are encoded as a JSON object so the model can surface them in the
    final response instead of the agent loop blowing up. Critically, when
    log_food fails with "doesn't have a tablespoon/teaspoon" or
    "unit_not_supported", we rewrite the error into an imperative `guidance`
    string. Without that hint, qwen3:8b's natural reaction is to "fix" the
    error by converting the user's unit (e.g. "100g" → "20 tsp"), which lands
    obviously-wrong calorie counts in the diary. The guidance flips it into
    a re-search instead.
    """
    cmd = [LOSEIT_BIN]
    if json_output:
        cmd += ["-o", "json"]
    cmd += args
    logger.info("loseit-cmd: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "loseit_timeout", "args": args})
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        err: dict[str, object] = {
            "error": "loseit_cli_failed",
            "exit_code": proc.returncode,
            "stderr": stderr[:2000],
        }
        if (
            "doesn't have a tablespoon" in stderr
            or "doesn't have a teaspoon" in stderr
            or "unit_not_supported" in stderr
        ):
            err["guidance"] = (
                "STOP. This food entry does not support the user's requested unit. "
                "DO NOT switch to a unit it does support — that converts the wrong way "
                "and gives bad calories. Instead, call `search` again with DIFFERENT KEYWORDS "
                "(add modifiers like 'fresh', 'homemade', 'plain', or remove brand words) "
                "and pick a different `food_id` from the new search results that DOES support "
                "the user's unit."
            )
        logger.warning("loseit-failed: %s", json.dumps(err))
        return json.dumps(err)
    return proc.stdout.strip()


# --------- Tools (ported from tools/agent-sandbox/agent.py) ----------------


@_inner_agent.tool_plain
def search(query: str) -> str:
    """Search the Lose It! food database for candidates matching `query`."""
    return _run_loseit(["search", query])


@_inner_agent.tool_plain
def describe_food(food_ids: list[str]) -> str:
    """Inspect one or more foods by their hex `food_id`s (concurrently).

    For each food_id, returns:
      - primary_serving: {unit, native_qty_per_serving}
      - cross_class_conversion: {per_serving_g, per_serving_ml} (nullable — tells you
        whether the entry supports gram/mL logging)
      - nutrients_per_serving: {calories, total_fat_g, sat_fat_g, carb_g, fiber_g, protein_g, ...}
    """
    return _run_loseit(["describe-food", *food_ids])


@_inner_agent.tool_plain
def log_food(
    food_id: str,
    meal: Literal["breakfast", "lunch", "dinner", "snacks"],
    serving_amount: float | None = None,
    serving_unit: str | None = None,
    servings: float = 1.0,
    on_date: str | None = None,
    dry_run: bool = False,
) -> str:
    """Log a food to the diary. Default behaviour ACTUALLY WRITES the entry — that's the goal.

    Args:
        food_id: The 32-char hex food_id (from `search`).
        meal: breakfast | lunch | dinner | snacks.
        serving_amount: Quantity in `serving_unit` (e.g. 120 grams → 120). Pair with serving_unit.
        serving_unit: One of: g, tsp, tbsp, cup, piece, each, fl_oz, mL, bottle, can, slice,
            serving, scoop, container, pie. Bare "oz" is REJECTED — pick g or fl_oz.
        servings: Use ONLY when not specifying serving_amount/unit (logs `servings` native servings).
        on_date: YYYY-MM-DD for past-dated entries. Default: today.
        dry_run: If True, preview without writing. DEFAULT FALSE — leave it false to actually log.
    """
    # Guardrail: a serving_amount > 30 in tsp/tbsp/fl_oz is almost certainly the model
    # doing unit-conversion math after it failed to find a gram-supporting entry. Block
    # it and force a re-search instead of letting absurd logs land in the diary.
    if serving_unit in {"tsp", "tbsp", "fl_oz"} and serving_amount and serving_amount > 30:
        guidance = (
            f"REFUSING: {serving_amount} {serving_unit} is absurdly high for one food entry. "
            "You almost certainly converted grams or milliliters into spoons after a previous "
            "log_food failed. Don't do that — it gives huge wrong calorie counts. Instead, call "
            "`search` again with a simpler query (just the food name, no user modifiers like "
            "'homemade' or 'fresh') and `describe_food` the FIRST 3 results to find one with "
            "`cross_class_conversion.per_serving_g != null`. Then log in the user's original unit."
        )
        err = {"error": "agent_guardrail_unit_conversion", "guidance": guidance}
        logger.warning("guardrail-tripped: %s", json.dumps(err))
        return json.dumps(err)

    args = ["log", "--food-id", food_id, "--meal", meal]
    if serving_amount is not None:
        args += ["--serving-amount", str(serving_amount)]
    if serving_unit:
        args += ["--serving-unit", serving_unit]
    if serving_amount is None and serving_unit is None:
        args += ["--servings", str(servings)]
    if on_date:
        args += ["--date", on_date]
    if dry_run:
        args += ["--dry-run"]
    return _run_loseit(args, json_output=False)


@_inner_agent.tool_plain
def diary(on_date: str | None = None) -> str:
    """Read the user's diary for a given date (default: today).

    Returns JSON with `date`, `count`, and `entries[]`. Each entry has `food_name`,
    `food_brand`, `food_measure_unit`, `servings`, `meal_ordinal` (0=breakfast 1=lunch
    2=dinner 3=snacks), and `nutrients_by_label: {calories, protein_g, ...}`.
    """
    args = ["diary"]
    if on_date:
        args += ["--date", on_date]
    return _run_loseit(args)


@_inner_agent.tool_plain
def whoami() -> str:
    """Print resolved Lose It! client configuration."""
    return _run_loseit(["whoami"])


# ------------------------------------------------------------ Kitaru wrap ----
#
# Wrap the inner agent with KitaruAgent so each call to `agent.run(...)`
# becomes a durable execution recorded against the Kitaru server. We can't
# attach the event_stream_handler here at construction time because it needs
# to push events into a per-request asyncio.Queue — so we build the handler
# inside `_agent_stream` and pass it as a per-call override via the
# `event_stream_handler=` kwarg to `agent.run(...)` (pydantic-ai's
# AbstractAgent contract; KitaruAgent forwards it).
#
# `checkpoint_strategy="calls"` opens one checkpoint per model/tool call —
# what the SPEC wants for an inspectable per-call tree in the UI.
try:
    from kitaru.adapters.pydantic_ai import KitaruAgent  # type: ignore[import-not-found]
except Exception as exc:  # noqa: BLE001
    logger.exception("kitaru adapter import failed: %s", exc)
    raise

agent = KitaruAgent(
    _inner_agent,
    name="loseit-agent",
    checkpoint_strategy="calls",
)


# ------------------------------------------------------------- HTTP layer ----

app = FastAPI(title="loseit-agent (S6 KitaruAgent + 5 tools)", version="0.6.0")


@app.on_event("startup")
async def _on_startup() -> None:
    _fetch_loseit_creds_from_kitaru()
    logger.info(
        "agent ready: model=%s endpoint=%s user_today=%s",
        OLLAMA_MODEL,
        OLLAMA_BASE_URL,
        USER_TODAY,
    )


class RunRequest(BaseModel):
    """Body of POST /run."""

    prompt: str = Field(..., description="Natural-language request (search, log, diary, …).")


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    """Reject requests without a valid `Authorization: Bearer <token>` header.

    Fail closed if `AGENT_TOKEN_EXPECTED` is unset — that's a misconfiguration,
    not "auth disabled".
    """

    if not EXPECTED_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AGENT_TOKEN_EXPECTED is not configured on the server.",
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    presented = authorization.split(" ", 1)[1].strip()
    if presented != EXPECTED_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness/readiness probe. No auth so kubelet doesn't need the token."""
    return {"status": "ok"}


def _sse(event: dict) -> str:
    """Format one SSE `data:` frame. Single-line JSON, blank-line separator."""
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


def _args_preview(part: ToolCallPart) -> str:
    """Render a tool-call's arguments as a compact one-liner.

    The Pipe surfaces this as the status text (e.g. `→ search(guacamole)`), so
    we keep it short and avoid quoting JSON.
    """
    args = part.args
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            return args[:80]
    if isinstance(args, dict):
        # Heuristic: a single scalar arg renders as its value; otherwise show
        # the whole dict.
        if len(args) == 1:
            (value,) = args.values()
            if isinstance(value, str):
                return value[:80]
            return json.dumps(value, separators=(",", ":"))[:80]
        return json.dumps(args, separators=(",", ":"))[:80]
    return str(args)[:80]


async def _agent_stream(prompt: str) -> AsyncIterator[str]:
    """Drive the KitaruAgent and translate its events into SSE frames.

    Architecture note (why this is a queue-and-producer, not a generator):

    With `KitaruAgent.run(prompt, event_stream_handler=...)`, pydantic-ai
    invokes our handler ONCE per model-request/tool-call "event stream" —
    each invocation gets its own `AsyncIterable[AgentStreamEvent]`. The
    handler itself doesn't yield SSE frames (its signature is `async def
    h(ctx, stream) -> None`). So we plumb events out through an
    `asyncio.Queue` that this generator drains. A producer task runs
    `agent.run(...)`; the handler stuffs SSE frames into the queue as events
    arrive; we yield them as fast as we get them. The terminal `final` /
    `error` frame is pushed by the producer task after `run()` returns or
    raises, then a sentinel `None` closes the stream.

    Event mapping (Pipe-stable — same wire format as S4):
      - PartStartEvent(ToolCallPart) → `tool` event keyed by call_id. We use
        part-start because FunctionToolCallEvent only fires AFTER args are
        validated, so it lands slightly later on the wall clock — emitting
        on part-start flips the chat shimmer to `→ search(...)` as soon as
        the model commits to a call.
      - FunctionToolCallEvent → `tool` event (deduped by call_id, so the
        chat doesn't see the status flip twice if both events fire).
      - FunctionToolResultEvent → `tool_done` event keyed by call_id.
      - Each top-level handler invocation increments `turn` and emits one
        `model_call` event. This matches the original S4 semantics (one per
        ModelRequestNode) closely enough — pydantic-ai calls the handler
        once per model-request stream and once per tool-call stream, and we
        treat any handler invocation whose first event is NOT a tool result
        as a model turn. The SPEC marks `model_call` as optional, so even
        if this heuristic over- or under-counts the chat status is still
        useful as progress signal.

    On the Kitaru side, this is all pure forwarding — KitaruAgent intercepts
    the same event stream upstream of our handler to open checkpoints and
    record artifacts; the wrapper guarantees our handler still receives the
    untouched pydantic-ai events. So the run shows up in `kitaru.priv...` as
    an execution with per-call checkpoints, AND the Pipe sees the live
    statuses unchanged. Win-win.

    S6 note: the magnitude guardrail (`tbsp/tsp/fl_oz` + >30) and the
    "doesn't have a tablespoon" guidance rewrite both live in the tool layer
    (log_food / _run_loseit) and return as a regular tool result — they show
    up here as plain `tool_done` events with no special handling required.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    emitted_tool_ids: set[str] = set()
    turn = 0

    async def event_stream_handler(
        ctx: RunContext[None],
        stream: AsyncIterator[object],
    ) -> None:
        nonlocal turn
        # Determine if this handler invocation is a model-request stream
        # (first event is NOT a tool-result) vs a tool-execution stream.
        # We bump `turn` at the first event of a non-tool-result stream.
        # This is a coarse heuristic but matches the original S4 cadence
        # closely enough for chat-side progress reporting.
        first = True
        async for event in stream:
            if first:
                first = False
                if not isinstance(event, FunctionToolResultEvent):
                    turn += 1
                    await queue.put(_sse({"kind": "model_call", "turn": turn}))

            if isinstance(event, FunctionToolCallEvent):
                call_id = event.part.tool_call_id
                if call_id in emitted_tool_ids:
                    continue
                emitted_tool_ids.add(call_id)
                await queue.put(
                    _sse(
                        {
                            "kind": "tool",
                            "name": event.part.tool_name,
                            "args_preview": _args_preview(event.part),
                            "call_id": call_id,
                        }
                    )
                )
            elif isinstance(event, FunctionToolResultEvent):
                await queue.put(_sse({"kind": "tool_done", "call_id": event.tool_call_id}))
            elif isinstance(event, PartStartEvent) and isinstance(event.part, ToolCallPart):
                call_id = event.part.tool_call_id
                if call_id in emitted_tool_ids:
                    continue
                emitted_tool_ids.add(call_id)
                await queue.put(
                    _sse(
                        {
                            "kind": "tool",
                            "name": event.part.tool_name,
                            "args_preview": _args_preview(event.part),
                            "call_id": call_id,
                        }
                    )
                )
            # Other events (PartDeltaEvent text deltas, FinalResultEvent) are
            # intentionally ignored: the Pipe consumes the consolidated final
            # text via the `final` SSE frame that the producer task emits
            # after `agent.run()` returns. Streaming text deltas through the
            # Pipe is S6/S7 territory.

    async def run_agent() -> None:
        try:
            result = await agent.run(
                prompt,
                event_stream_handler=event_stream_handler,
            )
            out = result.output
            final_text = out if isinstance(out, str) else str(out)
            await queue.put(_sse({"kind": "final", "text": final_text}))
        except Exception as exc:  # noqa: BLE001 — surface any failure once
            logger.exception("agent run failed")
            await queue.put(_sse({"kind": "error", "message": f"{type(exc).__name__}: {exc}"}))
        finally:
            await queue.put(None)

    runner = asyncio.create_task(run_agent())
    try:
        while True:
            frame = await queue.get()
            if frame is None:
                break
            yield frame
    finally:
        if not runner.done():
            runner.cancel()
            try:
                await runner
            except (asyncio.CancelledError, Exception):
                pass


@app.post("/run", dependencies=[Depends(require_bearer)])
async def run(body: RunRequest) -> StreamingResponse:
    """Stream the agent's tool/model/final events for the given prompt."""
    logger.info("run start prompt_len=%d", len(body.prompt))
    return StreamingResponse(
        _agent_stream(body.prompt),
        media_type="text/event-stream",
        headers={
            # Disable proxy buffering so Traefik flushes each event as it
            # arrives instead of holding them until the connection closes.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
