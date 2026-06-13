"""Slice S5: FastAPI service for a Kitaru-wrapped pydantic-ai agent.

The pydantic-ai Agent (single `search` tool, qwen3:8b on homelab Ollama) is
now wrapped in `KitaruAgent`, so every `POST /run` becomes a durable Kitaru
execution with per-call checkpoints visible in the Kitaru UI / API. The SSE
wire format on `POST /run` is preserved verbatim from S2/S4 — the Pipe and
selftest already speak it. Each pydantic-ai stream event is translated into
one of the schemas defined in apps/loseit-agent/SPEC.md:

    data: {"kind":"tool",       "name":"search", "args_preview":"<query>", "call_id":"..."}
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

Slices S6-S7 add: 4 more tools (S6), wait/resume (S7).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import AsyncIterator

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


# ------------------------------------------------------------------ agent ----

_model = OpenAIChatModel(
    OLLAMA_MODEL,
    provider=OpenAIProvider(base_url=OLLAMA_BASE_URL, api_key="ollama"),
)

SYSTEM_PROMPT = (
    "You help the user search the Lose It! food database. When given a query, "
    "call `search` ONCE and return a concise summary of the top 3-5 results "
    "(name, brand if any, and the food_id). Don't try to log anything yet."
)

# `name=` is REQUIRED by KitaruAgent (it's how runs are grouped in the UI).
# Setting it on the inner Agent also gives KitaruAgent a sensible default if
# we forget to pass `name=` again at the wrapping layer.
_inner_agent: Agent[None, str] = Agent(
    _model,
    name="loseit-search-agent",
    system_prompt=SYSTEM_PROMPT,
    retries=2,
)


def _run_loseit_search(query: str) -> str:
    """Subprocess `loseit -o json search <query>` and return stdout.

    Errors are encoded as a JSON object so the model can surface them in the
    final response instead of the agent loop blowing up.
    """
    cmd = [LOSEIT_BIN, "-o", "json", "search", query]
    logger.info("loseit-cmd: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "loseit_timeout", "query": query})
    if proc.returncode != 0:
        return json.dumps(
            {
                "error": "loseit_cli_failed",
                "exit_code": proc.returncode,
                "stderr": proc.stderr.strip()[:2000],
            }
        )
    return proc.stdout.strip()


@_inner_agent.tool_plain
def search(query: str) -> str:
    """Search the Lose It! food database for candidates matching `query`."""
    return _run_loseit_search(query)


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
    name="loseit-search-agent",
    checkpoint_strategy="calls",
)


# ------------------------------------------------------------- HTTP layer ----

app = FastAPI(title="loseit-agent (S5 KitaruAgent + search)", version="0.5.0")


@app.on_event("startup")
async def _on_startup() -> None:
    _fetch_loseit_creds_from_kitaru()
    logger.info("agent ready: model=%s endpoint=%s", OLLAMA_MODEL, OLLAMA_BASE_URL)


class RunRequest(BaseModel):
    """Body of POST /run."""

    prompt: str = Field(..., description="Natural-language search request.")


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
