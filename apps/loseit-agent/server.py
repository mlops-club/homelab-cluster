"""Slice S7: FastAPI service for a Kitaru-wrapped 5-tool pydantic-ai agent
with genuine human-in-the-loop via `kitaru.wait()` checkpoints.

S6 tools (unchanged):

    search          — query the Lose It! food DB
    describe_food   — inspect 1+ food_ids (units, conversions, nutrients)
    log_food        — write an entry to the diary
    diary           — read the diary for a date
    whoami          — print resolved loseit identity

S7 adds:

    clarify(question, options) — agent calls this when the user's request
        is genuinely ambiguous (e.g. "log some berries"). Internally it
        emits a `wait` SSE event with the durable Kitaru `exec_id` and the
        wait-condition `name`, then calls `kitaru.wait(...)` to suspend the
        execution at a checkpoint. The agent run blocks on the workflow
        thread until the wait is resolved via `POST /resume`.

The SSE wire format on `POST /run` is preserved verbatim from S4/S5/S6 —
the Pipe and selftest already speak it — and gains one new event kind for
human-in-the-loop pauses:

    data: {"kind":"tool",       "name":"<tool>", "args_preview":"<arg>", "call_id":"..."}
    data: {"kind":"tool_done",  "call_id":"<same id>"}
    data: {"kind":"model_call", "turn": N}
    data: {"kind":"wait",       "exec_id":"...", "wait_name":"...",
                                  "prompt":"...", "options":[...]}
    data: {"kind":"final",      "text":"..."}
    data: {"kind":"error",      "message":"..."}

`POST /resume` accepts `{"exec_id":"...", "value":"..."}` and returns the
same SSE schema, continuing the same Kitaru execution from the paused
checkpoint. If the model clarifies a second time, `/resume` emits another
`wait` event and ends the stream; the Pipe routes the next chat message to
`/resume` again with the SAME exec_id.

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
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic_ai import Agent
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

Ambiguity rule — `clarify`:
  If the user's request names a food generically and the choice materially changes calories,
  call `clarify(question=..., options=[...])` BEFORE searching/logging and use the returned
  string as the concrete food name. Examples that REQUIRE clarify:
     - "log some berries"     → clarify(question="Which berry?", options=["strawberry","blueberry","raspberry","blackberry"])
     - "log a couple cookies" → clarify(question="Which cookie?", options=["chocolate chip","oatmeal raisin","sugar"])
  Examples that DO NOT need clarify (proceed directly):
     - "100g guacamole as a snack"     — specific food + unit
     - "log 1 cup of cooked oatmeal"   — specific food + unit
     - "log a banana"                  — specific food, no calorie ambiguity
  Call `clarify` AT MOST ONCE per user request. After it returns, treat the value as the
  bare food noun and proceed with the normal search → describe → log flow above.

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


# ----------------------------------------------------- kitaru core import ----
#
# We need `kitaru.wait()` (suspend execution at a checkpoint and return the
# user-supplied input) and `kitaru.current_execution_id()` (get the active
# exec_id from inside a tool body) for the `clarify` tool below. The high-
# level `KitaruClient` is used by /resume to call `executions.input(...)`.
# The pydantic-ai adapter import is delayed until after the tools so we can
# pin `tool_checkpoint_config_by_name={"clarify": False}` at the wrap site
# without forward-referencing a tool name that hasn't been registered yet.
try:
    import kitaru  # type: ignore[import-not-found]
    from kitaru import KitaruClient  # type: ignore[import-not-found]
    from kitaru.adapters.pydantic_ai import hitl_tool  # type: ignore[import-not-found]
except Exception as exc:  # noqa: BLE001
    logger.exception("kitaru import failed: %s", exc)
    raise


def _sse(event: dict) -> str:
    """Format one SSE `data:` frame. Single-line JSON, blank-line separator."""
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


# --------------------------------------------------------- HITL run state ----
#
# When the model calls `clarify(...)`, the tool body emits a `wait` SSE event
# and then blocks on `kitaru.wait(...)`. The blocking call sits on the
# pipeline/worker thread for the rest of the `agent.run(...)` lifetime; the
# `/run` HTTP request returns its SSE stream as soon as it sees the `wait`
# event, but the agent task itself stays alive in the background. When the
# user replies via `POST /resume`, we look up the still-running task by
# exec_id, hand the value to Kitaru (which unblocks `kitaru.wait()` on the
# worker thread), and re-attach the SAME asyncio.Queue to a new SSE response.
#
# Concurrency: this scheme assumes one in-flight HITL run per agent replica,
# which is the homelab/single-user case. A second `/run` while a wait is
# pending will land on a different exec_id and won't collide with the first
# one's queue (the registry is keyed by exec_id), but the assumption is the
# Pipe routes resume traffic to /resume based on chat metadata so the user
# never sees the contention.

@dataclass
class _HitlRunState:
    """Live state for a single in-flight agent run that may pause for HITL."""

    queue: asyncio.Queue[str | None]
    """SSE-frame queue drained by the current `/run` or `/resume` generator.

    The same queue persists across the run's full lifetime so that events
    emitted AFTER the wait resolves (e.g. log_food tool calls, the final
    summary) land in the queue the next `/resume` generator drains.
    """

    task: asyncio.Task
    """The background task running `agent.run(...)`. Stays alive across the
    wait so resume can plug a new SSE generator into the same queue."""

    loop: asyncio.AbstractEventLoop
    """The FastAPI event loop the queue belongs to. Used by the clarify tool
    body — which runs on a worker thread inside the KitaruAgent auto-flow —
    to schedule queue.put_nowait() via `call_soon_threadsafe(...)`. (For an
    unbounded queue the put never blocks, so call_soon_threadsafe + put_nowait
    is a thread-safe wakeup of any consumer.)"""

    wait_name: str | None = None
    """The name passed to `kitaru.wait(name=...)`. Stored so /resume can pass
    the same name back to `client.executions.input(exec_id, wait=name, ...)`.
    None until the clarify tool fires its first wait."""

    exec_id: str | None = None
    """The Kitaru exec_id, captured from inside the clarify tool body via
    `kitaru.current_execution_id()`. None until clarify fires."""

    chat_id: str | None = None
    """Open WebUI chat id this run belongs to (when invoked via the Pipe).
    On wait we register the exec_id under this chat_id in `_PENDING_BY_CHAT`
    so the next /run from the same chat is recognized as a resume."""



# Registry keyed by exec_id once the agent run reports it. We also have a
# separate single-slot "pending" state for runs that have started but not yet
# emitted any kitaru event — clarify resolves itself to the pending slot when
# it can't find an exec_id-keyed entry. Single-slot is fine for our single-
# user homelab case (see concurrency note above).
_HITL_RUNS: dict[str, _HitlRunState] = {}
_HITL_PENDING: _HitlRunState | None = None
_HITL_LOCK = threading.Lock()


def _hitl_register_pending(state: _HitlRunState) -> None:
    """Mark `state` as the currently-starting run (no exec_id yet)."""
    global _HITL_PENDING
    with _HITL_LOCK:
        _HITL_PENDING = state


def _hitl_clear_pending(state: _HitlRunState) -> None:
    """Clear the pending slot if it still points at `state`."""
    global _HITL_PENDING
    with _HITL_LOCK:
        if _HITL_PENDING is state:
            _HITL_PENDING = None


def _hitl_resolve_active_state() -> _HitlRunState | None:
    """Find the run state for the current `kitaru.wait()` caller.

    Called from inside the clarify tool body on the workflow thread. Prefers
    the exec_id keyed entry (set on a previous clarify in the same run); falls
    back to the pending slot (first clarify of the run, before we knew the
    exec_id).
    """
    exec_id = kitaru.current_execution_id()
    with _HITL_LOCK:
        if exec_id is not None and exec_id in _HITL_RUNS:
            return _HITL_RUNS[exec_id]
        return _HITL_PENDING


def _hitl_promote_pending_to_exec_id(state: _HitlRunState, exec_id: str) -> None:
    """Re-key the pending state under its now-known exec_id so /resume can
    find it. Idempotent: a second clarify in the same run is a no-op."""
    global _HITL_PENDING
    with _HITL_LOCK:
        if state.exec_id is None:
            state.exec_id = exec_id
        _HITL_RUNS[exec_id] = state
        if _HITL_PENDING is state:
            _HITL_PENDING = None


@_inner_agent.tool_plain
def clarify(question: str, options: list[str] | None = None) -> str:
    """Pause the agent run and ask the user for clarification.

    Use this when the user's request names a food generically and the choice
    materially changes calories (e.g. "berries" → strawberry vs blueberry
    have very different calorie densities; "cookie" → chocolate chip vs sugar
    have very different macros). Do NOT use this for unambiguous requests.

    Args:
        question: Human-readable question to display to the user, e.g.
            "Which berry?". Keep it under 12 words.
        options: Optional shortlist of choices. The Pipe renders these as a
            bulleted list and tells the user they can pick one or type their
            own answer. Use 2–5 options.

    Returns:
        The user's answer as a string. Use this as the bare food noun in the
        subsequent `search` call.
    """
    # Resolve the per-run state set up by /run. The clarify body runs on the
    # workflow thread (thanks to allow_sync_tool_body_waits=True), which is
    # NOT the FastAPI event loop's thread — so we go through loop.call_soon_
    # threadsafe to push the wait event onto the asyncio.Queue without
    # ever calling await from this sync function.
    state = _hitl_resolve_active_state()
    if state is None:
        logger.error("clarify: no active HITL run state — aborting wait")
        return (
            "[clarify-unavailable] The HITL primitive could not find the "
            "in-flight run. Proceed without clarification."
        )

    exec_id = kitaru.current_execution_id()
    if exec_id is None:
        logger.error("clarify: kitaru.current_execution_id() returned None")
        return (
            "[clarify-unavailable] No Kitaru execution context. Proceed "
            "without clarification."
        )

    # Stable per-call name so multiple clarifies in one run get unique waits.
    # The Kitaru server tracks pending waits by name; collisions would make
    # /resume's executions.input call ambiguous.
    wait_name = f"clarify_{uuid.uuid4().hex[:12]}"
    state.wait_name = wait_name
    _hitl_promote_pending_to_exec_id(state, exec_id)

    sse_payload = {
        "kind": "wait",
        "exec_id": exec_id,
        "wait_name": wait_name,
        "prompt": question,
        "options": list(options) if options else [],
    }
    frame = _sse(sse_payload)
    logger.info("clarify: emitting wait event exec_id=%s name=%s", exec_id, wait_name)
    try:
        state.loop.call_soon_threadsafe(state.queue.put_nowait, frame)
    except RuntimeError as exc:  # pragma: no cover — loop closed mid-run
        logger.warning("clarify: failed to push wait event: %s", exc)

    # The Kitaru wait. `schema=str` constrains the user input to a string
    # (which is what the Pipe always supplies — the user's chat message).
    # This call blocks the workflow thread, polling the Kitaru server every
    # 5s for the wait condition to be resolved. `/resume` resolves it via
    # `client.executions.input(exec_id, wait=name, value=...)`. A 24h
    # timeout means the worker thread polls the whole time without ever
    # transitioning the run to PAUSED (so we don't need to wrestle with
    # snapshot-based resume); if the pod restarts, the wait DOES land in
    # PAUSED on the server and is recoverable via `kitaru executions input`
    # interactively from a human laptop.
    #
    # This call is what makes step 7 of the S7 verification pass — Kitaru
    # records a checkpoint+wait pair against the execution.
    metadata = {"options": list(options) if options else [], "source": "loseit-agent.clarify"}
    answer = kitaru.wait(
        schema=str,
        name=wait_name,
        question=question,
        metadata=metadata,
        timeout=24 * 60 * 60,
    )
    logger.info("clarify: wait resolved with value=%r", answer)
    return str(answer) if answer is not None else ""


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
#
# Each tool is wrapped by `_with_live_status` so its call shows up as a
# live chat line in Open WebUI (`tool` + `tool_done` SSE frames). This is
# the only place we get per-tool visibility in S7 — pydantic-ai's
# event_stream_handler would give the same data more cleanly but is
# mutually exclusive with `kitaru.wait()` in granular mode (see
# _agent_stream docstring). The wrapper runs OUTSIDE Kitaru's per-tool
# checkpoint wrapping, so it doesn't trip the no-wait-in-checkpoint guard.


def _with_live_status(name: str, args_preview_fn: Callable[..., str]):
    """Wrap a sync tool body to emit `tool` / `tool_done` SSE events.

    The events flow through the active `_HitlRunState`'s queue (resolved
    via the same _hitl_resolve_active_state() helper clarify uses).
    `args_preview_fn(*args, **kwargs) -> str` is a per-tool function
    that produces the short args label the Pipe surfaces in the chat
    line (e.g. `search` → `query`, `log_food` → `100g of <food_id>`).
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        import functools

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            state = _hitl_resolve_active_state()
            call_id = uuid.uuid4().hex[:10]
            try:
                preview = args_preview_fn(*args, **kwargs)
            except Exception:  # noqa: BLE001
                preview = ""
            if state is not None:
                start_frame = _sse({
                    "kind": "tool",
                    "name": name,
                    "args_preview": preview[:80],
                    "call_id": call_id,
                })
                try:
                    state.loop.call_soon_threadsafe(state.queue.put_nowait, start_frame)
                except RuntimeError:
                    pass
            t0 = time.monotonic()
            try:
                return fn(*args, **kwargs)
            finally:
                if state is not None:
                    elapsed = time.monotonic() - t0
                    done_frame = _sse({
                        "kind": "tool_done",
                        "name": name,
                        "call_id": call_id,
                        "elapsed_s": round(elapsed, 2),
                    })
                    try:
                        state.loop.call_soon_threadsafe(state.queue.put_nowait, done_frame)
                    except RuntimeError:
                        pass

        return wrapper

    return decorator


@_inner_agent.tool_plain
@_with_live_status("search", lambda query: query)
def search(query: str) -> str:
    """Search the Lose It! food database for candidates matching `query`."""
    return _run_loseit(["search", query])


@_inner_agent.tool_plain
@_with_live_status("describe_food", lambda food_ids: f"{len(food_ids)} ids")
def describe_food(food_ids: list[str]) -> str:
    """Inspect one or more foods by their hex `food_id`s (concurrently).

    For each food_id, returns:
      - primary_serving: {unit, native_qty_per_serving}
      - cross_class_conversion: {per_serving_g, per_serving_ml} (nullable — tells you
        whether the entry supports gram/mL logging)
      - nutrients_per_serving: {calories, total_fat_g, sat_fat_g, carb_g, fiber_g, protein_g, ...}
    """
    return _run_loseit(["describe-food", *food_ids])


def _log_food_preview(food_id, meal, serving_amount=None, serving_unit=None, servings=1.0, **_):
    qty = f"{serving_amount}{serving_unit}" if serving_amount else f"{servings} servings"
    return f"{qty} → {meal} ({food_id[:8]})"


@_inner_agent.tool_plain
@_with_live_status("log_food", _log_food_preview)
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
@_with_live_status("diary", lambda on_date=None: on_date or "today")
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
@_with_live_status("whoami", lambda: "")
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
#
# S7 wiring:
#   - `tool_checkpoint_config_by_name={"clarify": False}` opts the clarify
#     tool out of the synthetic per-tool checkpoint. Kitaru's `wait()` guard
#     refuses to create a wait inside a checkpoint scope (it logs a wait at
#     flow scope so the run can pause-and-resume cleanly), so we need the
#     opt-out for the clarify body to call `kitaru.wait(...)` at all.
#   - `allow_sync_tool_body_waits=True` tells KitaruAgent to keep supported
#     sync tool bodies on the workflow thread instead of pushing them to a
#     pydantic-ai worker thread. `kitaru.wait()` is required to be called
#     from the pipeline thread; without this flag the wait raises
#     "must be called from the pipeline thread".
#   - `kitaru` itself (for `wait()` + `current_execution_id()`) is imported
#     earlier so the `clarify` tool above can use it; we only need the
#     pydantic-ai adapter here.
try:
    from kitaru.adapters.pydantic_ai import KitaruAgent  # type: ignore[import-not-found]
except Exception as exc:  # noqa: BLE001
    logger.exception("kitaru adapter import failed: %s", exc)
    raise

agent = KitaruAgent(
    _inner_agent,
    name="loseit-agent",
    checkpoint_strategy="calls",
    granular_checkpoints=True,
    # The opt-out is required by KitaruAgent's constructor whenever
    # `allow_sync_tool_body_waits=True` is set (the SDK refuses the flag
    # otherwise — "requires at least one per-tool checkpoint opt-out").
    # Skipping the synthetic `clarify_tool` checkpoint here is fine:
    # clarify's work IS the wait, and we record the wait against the run
    # via the SSE `wait` event + the in-memory _HitlRunState anyway. The
    # other 5 tools still get per-call `*_tool` checkpoints in the Kitaru
    # UI for inspection.
    tool_checkpoint_config_by_name={"clarify": False},
    allow_sync_tool_body_waits=True,
)


# ------------------------------------------------------------- HTTP layer ----

app = FastAPI(title="loseit-agent (S7 KitaruAgent + 5 tools + clarify HITL)", version="0.7.0")


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
    chat_id: str | None = Field(
        default=None,
        description=(
            "Open WebUI chat id, used to track pending HITL waits across chat "
            "turns. When set, the server checks if this chat already has a "
            "pending exec_id from a prior wait — if so, the request is "
            "treated as a resume rather than a new run. Optional; omit for "
            "direct curl usage."
        ),
    )


# Pending-wait registry keyed by chat_id. Open WebUI's `__metadata__` doesn't
# reliably persist Pipe-side dict mutations across chat turns, so the Pipe
# can't store the pending exec_id there. Instead the Pipe sends `chat_id`
# with every /run, and the server decides run-vs-resume internally based on
# this dict.
_PENDING_BY_CHAT: dict[str, str] = {}
_PENDING_BY_CHAT_LOCK = threading.Lock()


def _mark_pending(chat_id: str | None, exec_id: str) -> None:
    if not chat_id:
        return
    with _PENDING_BY_CHAT_LOCK:
        _PENDING_BY_CHAT[chat_id] = exec_id


def _clear_pending(chat_id: str | None) -> None:
    if not chat_id:
        return
    with _PENDING_BY_CHAT_LOCK:
        _PENDING_BY_CHAT.pop(chat_id, None)


def _get_pending(chat_id: str | None) -> str | None:
    if not chat_id:
        return None
    with _PENDING_BY_CHAT_LOCK:
        return _PENDING_BY_CHAT.get(chat_id)


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


async def _drain_queue_until_terminal(state: _HitlRunState) -> AsyncIterator[str]:
    """Yield SSE frames from `state.queue` until a terminal frame.

    Terminal frames:
      - `wait`  — the agent paused for clarification. We yield the frame and
                  STOP draining; the background task is left running. The
                  next chat message will route to /resume and resume drains
                  the same queue.
      - `final` — the agent completed. We yield the frame, clean up registry.
      - `error` — the agent crashed. We yield the frame, clean up registry.
      - `None`  — sentinel pushed when the background task exits cleanly with
                  no final/error (shouldn't happen in practice, but covers
                  the race between cleanup paths).

    Returning early on `wait` is the load-bearing piece of S7: it closes the
    HTTP response stream so the Pipe gets `status: done` for its current
    chat turn, while the agent's `kitaru.wait()` call keeps blocking on the
    workflow thread, ready to be unblocked by `/resume`.
    """
    while True:
        frame = await state.queue.get()
        if frame is None:
            # Background task exited; finished.
            _hitl_finalize(state)
            return
        yield frame
        # Parse the frame's kind without re-serializing. SSE frames have a
        # stable `data: {...}\n\n` shape per `_sse()`.
        try:
            payload_line = frame.split("\n", 1)[0]
            if payload_line.startswith("data: "):
                payload = json.loads(payload_line[6:])
                kind = payload.get("kind")
                if kind == "wait":
                    exec_id = payload.get("exec_id")
                    logger.info(
                        "stream paused at wait exec_id=%s name=%s chat_id=%s",
                        exec_id,
                        payload.get("wait_name"),
                        state.chat_id,
                    )
                    # Mark the chat as having a pending wait so the next /run
                    # from the same chat_id routes to resume instead of run.
                    if state.chat_id and exec_id:
                        _mark_pending(state.chat_id, exec_id)
                    return
                if kind in ("final", "error"):
                    # Clear any pending-by-chat pointer; this run is done.
                    _clear_pending(state.chat_id)
                    _hitl_finalize(state)
                    return
        except Exception:  # noqa: BLE001 — never drop a frame for parse errors
            logger.exception("failed to parse SSE frame for terminal-kind check")


def _hitl_finalize(state: _HitlRunState) -> None:
    """Remove `state` from the HITL registry. Safe to call multiple times."""
    with _HITL_LOCK:
        if state.exec_id and _HITL_RUNS.get(state.exec_id) is state:
            del _HITL_RUNS[state.exec_id]
        global _HITL_PENDING
        if _HITL_PENDING is state:
            _HITL_PENDING = None


async def _agent_stream(prompt: str, chat_id: str | None = None) -> AsyncIterator[str]:
    """Drive a fresh KitaruAgent run and stream its SSE frames.

    Architecture (S7 — diverged from the S5/S6 event_stream_handler path):

    `KitaruAgent.run(..., event_stream_handler=...)` forces a single TURN
    checkpoint around the whole run because per-call streaming checkpointing
    would require draining the stream inside a sync ZenML step (see
    `kitaru.adapters.pydantic_ai.README.md` § Streaming). That turn checkpoint
    is hostile to `kitaru.wait()`: the wait guard refuses to create a wait
    inside any checkpoint, INCLUDING the implicit turn one. So we CANNOT
    use event_stream_handler in S7 — they're mutually exclusive in the
    granular-checkpoints regime kitaru[pydantic-ai]==0.15.0 exposes.

    Trade-off taken in S7: drop the per-call live `tool` / `tool_done` /
    `model_call` SSE frames so we keep `kitaru.wait()` working. The Pipe
    still gets the load-bearing `wait` and `final` frames — chat UX during
    a HITL run is "Starting agent…" → wait question → "Resuming…" → final
    summary, with no intermediate shimmer text. Per-call progress is still
    visible in the Kitaru run inspector via the per-call checkpoints
    `checkpoint_strategy="calls"` keeps producing. A future slice could
    re-add live status by subscribing to Kitaru's server-side
    `client.executions.events(exec_id)` SSE stream and translating events
    back to the S6 wire format; out of scope here.

    What this generator does:

      1. Create an `asyncio.Queue` and capture the FastAPI event loop.
      2. Register a `_HitlRunState` in the global registry so the clarify
         tool body (running on the workflow thread) can find the queue.
      3. Spawn an asyncio task that runs `agent.run(prompt)`. No event
         stream handler — so KitaruAgent uses per-call checkpoints, no turn
         checkpoint, and `kitaru.wait()` inside `clarify` works.
      4. Drain frames from the queue. The only frames that arrive here:
            - clarify tool body  → `wait` SSE frame (pushed via
              `loop.call_soon_threadsafe(queue.put_nowait, ...)`).
            - `run_agent()`      → `final` or `error` SSE frame after
              `agent.run()` returns or raises.
      5. On a `wait` frame, yield it and STOP. The producer task is left
         alive — `kitaru.wait()` is blocked on the workflow thread, ready
         to be unblocked by `/resume`.
    """
    state = _HitlRunState(
        queue=asyncio.Queue(),
        task=asyncio.current_task(),  # placeholder, overwritten below
        loop=asyncio.get_running_loop(),
    )
    state.chat_id = chat_id

    async def run_agent() -> None:
        try:
            # No `event_stream_handler=` — see docstring for why. The agent
            # uses checkpoint_strategy="calls" (the KitaruAgent default we
            # configured) so per-call checkpoints still land in the Kitaru
            # UI; only the live SSE forwarding of intermediate events is
            # dropped here.
            result = await agent.run(prompt)
            out = result.output
            final_text = out if isinstance(out, str) else str(out)
            await state.queue.put(_sse({"kind": "final", "text": final_text}))
        except Exception as exc:  # noqa: BLE001 — surface any failure once
            logger.exception("agent run failed")
            await state.queue.put(
                _sse({"kind": "error", "message": f"{type(exc).__name__}: {exc}"})
            )
        finally:
            await state.queue.put(None)

    state.task = asyncio.create_task(run_agent())
    _hitl_register_pending(state)
    try:
        async for frame in _drain_queue_until_terminal(state):
            yield frame
    finally:
        # Important: if we yielded a `wait` and broke out cleanly, we MUST
        # NOT cancel the background task — it's blocked at kitaru.wait() and
        # /resume will unblock it. Only cancel if the run is truly done
        # (sentinel None received) AND the task is somehow still running, or
        # if the client disconnected before any frame at all.
        if state.exec_id is None and _HITL_PENDING is state and state.task and not state.task.done():
            # Client gave up before any wait; cancel to free resources.
            state.task.cancel()
            try:
                await state.task
            except (asyncio.CancelledError, Exception):
                pass
            _hitl_finalize(state)


async def _resume_stream(
    state: _HitlRunState, value: str, chat_id: str | None = None
) -> AsyncIterator[str]:
    """Resume a paused agent run with `value` and stream subsequent SSE frames.

    The wait_name we use to call `client.executions.input(...)` is the one
    the most recent `clarify` recorded on `state` (the agent could have
    clarified more than once). We dispatch the (sync) Kitaru client call to
    a thread so the FastAPI event loop doesn't block; the actual unblocking
    of `kitaru.wait()` happens on the workflow thread, which is polling for
    the wait condition every 5 seconds (the default) — typically 0–5s after
    the input lands.
    """
    if state.wait_name is None or state.exec_id is None:
        msg = "no pending wait recorded for this exec_id"
        logger.error("resume: %s", msg)
        yield _sse({"kind": "error", "message": msg})
        _hitl_finalize(state)
        return

    # Provide the input to the Kitaru wait condition. This is what unblocks
    # the `kitaru.wait()` call sitting inside `clarify` on the workflow
    # thread. We use the high-level KitaruClient (sync API) and dispatch to
    # a thread so the FastAPI event loop doesn't block on the HTTP round-
    # trip to the Kitaru server. The wait's polling loop on the workflow
    # thread (default 5s interval) picks the resolution up within ~5s.
    # Race: the wait SSE event is pushed onto the queue BEFORE the worker
    # thread's `kitaru.wait()` call registers the wait condition with the
    # Kitaru server. If the user (or our Pipe) replies extremely fast, the
    # resume can arrive before the wait is registered → "no pending waits to
    # resolve". Retry briefly with exponential backoff to absorb that window.
    def _provide_input() -> None:
        from kitaru.errors import KitaruStateError  # type: ignore[import-not-found]

        client = KitaruClient()
        delays = [0.0, 0.2, 0.5, 1.0, 2.0, 3.0]
        last_exc: Exception | None = None
        for delay in delays:
            if delay:
                time.sleep(delay)
            try:
                client.executions.input(state.exec_id, wait=state.wait_name, value=value)
                return
            except KitaruStateError as exc:
                last_exc = exc
                if "no pending waits" not in str(exc).lower():
                    raise
                # Retry — the worker thread hasn't registered the wait yet.
        if last_exc is not None:
            raise last_exc

    try:
        await asyncio.to_thread(_provide_input)
        logger.info(
            "resume: input provided to exec_id=%s wait=%s value=%r",
            state.exec_id,
            state.wait_name,
            value,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("resume: executions.input failed")
        yield _sse(
            {"kind": "error", "message": f"resume failed: {type(exc).__name__}: {exc}"}
        )
        _hitl_finalize(state)
        return

    # Clear the wait_name so the next /resume on the same exec_id (after a
    # second clarify) waits for the new wait_name to be set by clarify.
    state.wait_name = None

    async for frame in _drain_queue_until_terminal(state):
        yield frame


@app.post("/run", dependencies=[Depends(require_bearer)])
async def run(body: RunRequest) -> StreamingResponse:
    """Stream the agent's tool/model/final/wait events for the given prompt.

    If `chat_id` is provided AND this chat already has a pending HITL wait
    (recorded server-side from a previous `/run` that emitted a `wait`),
    the request is internally routed to the resume path instead of starting
    a fresh agent run. This sidesteps Open WebUI's unreliable __metadata__
    persistence — the Pipe doesn't need to track exec_id across turns;
    just sending chat_id is enough.

    Stream may end with `final`, `error`, OR `wait` — in the `wait` case
    the chat continues on the user's next message with the same chat_id.
    """
    pending_exec_id = _get_pending(body.chat_id)
    if pending_exec_id:
        with _HITL_LOCK:
            state = _HITL_RUNS.get(pending_exec_id)
        if state is None:
            # State lost (pod restart?). Clear the stale pointer and fall
            # through to a fresh run so the user isn't stuck forever.
            logger.warning(
                "run: pending exec_id %s for chat %s has no live state; "
                "clearing and starting fresh",
                pending_exec_id,
                body.chat_id,
            )
            _clear_pending(body.chat_id)
        else:
            logger.info(
                "run: chat %s has pending wait exec_id=%s — resuming",
                body.chat_id,
                pending_exec_id,
            )
            return StreamingResponse(
                _resume_stream(state, body.prompt, chat_id=body.chat_id),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

    logger.info("run start prompt_len=%d chat_id=%s", len(body.prompt), body.chat_id)
    return StreamingResponse(
        _agent_stream(body.prompt, chat_id=body.chat_id),
        media_type="text/event-stream",
        headers={
            # Disable proxy buffering so Traefik flushes each event as it
            # arrives instead of holding them until the connection closes.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class ResumeRequest(BaseModel):
    """Body of POST /resume."""

    exec_id: str = Field(..., description="Kitaru exec_id from the `wait` SSE event.")
    value: str = Field(..., description="User-provided clarification (free text).")


@app.post("/resume", dependencies=[Depends(require_bearer)])
async def resume(body: ResumeRequest) -> StreamingResponse:
    """Unblock a paused agent run and stream the subsequent SSE events.

    The agent's `kitaru.wait()` call resolves with the supplied `value`; the
    tool body returns that value to the model, which then continues the run.
    Subsequent tool/model/final events stream over this response. If the
    agent clarifies a SECOND time, this response ends with another `wait`
    event and the Pipe routes the next chat message to /resume again with
    the same exec_id.
    """
    with _HITL_LOCK:
        state = _HITL_RUNS.get(body.exec_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No paused run found for exec_id={body.exec_id!r}.",
        )
    logger.info("resume start exec_id=%s value_len=%d", body.exec_id, len(body.value))
    return StreamingResponse(
        _resume_stream(state, body.value),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
