"""Slice S4 (+ Kitaru-secrets migration): FastAPI service for a pydantic-ai agent.

The agent drives the `loseit` CLI via a single `search` tool, backed by qwen3:8b
on the homelab Ollama. The SSE wire format on `POST /run` is preserved verbatim
from S2 — the Pipe already speaks it. Each pydantic-ai stream event is
translated into one of the schemas defined in apps/loseit-agent/SPEC.md:

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

Slices S5-S7 add: KitaruAgent wrapping (S5), 4 more tools (S6), wait/resume (S7).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartStartEvent,
    ToolCallPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.run import AgentRunResultEvent

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

agent: Agent[None, str] = Agent(
    _model,
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


@agent.tool_plain
def search(query: str) -> str:
    """Search the Lose It! food database for candidates matching `query`."""
    return _run_loseit_search(query)


# ------------------------------------------------------------- HTTP layer ----

app = FastAPI(title="loseit-agent (S4 pydantic-ai + search)", version="0.4.0")


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
    """Drive the pydantic-ai Agent and translate its events into SSE frames.

    Mapping:
      - PartStartEvent(ToolCallPart) → `tool` event (we use part-start because
        FunctionToolCallEvent fires only AFTER args are validated, so it's
        slightly later in the wall-clock timeline — emitting on part-start
        lets the chat shimmer flip to `→ search(...)` as soon as the model
        commits to a call).
      - FunctionToolResultEvent → `tool_done` event keyed by call_id.
      - Each new `ModelRequestNode` increments `turn` and emits `model_call`.
      - `AgentRunResultEvent` (terminal) carries `result.output` → `final`.
      - Any raised exception is surfaced as one `error` event before the
        stream closes.

    We emit through an `asyncio.Queue` rather than yielding directly inside
    `event_stream_handler` so the handler can stay a clean async callable
    (pydantic-ai will await it for every event) while the StreamingResponse
    consumer pulls frames out asynchronously.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    emitted_tool_ids: set[str] = set()
    turn = 0

    async def emit_event(event: object) -> None:
        nonlocal turn
        # FunctionToolCallEvent: validated tool call about to run. We dedupe
        # against PartStartEvent so the chat doesn't see the status flip twice.
        if isinstance(event, FunctionToolCallEvent):
            call_id = event.part.tool_call_id
            if call_id in emitted_tool_ids:
                return
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
            return
        if isinstance(event, FunctionToolResultEvent):
            await queue.put(_sse({"kind": "tool_done", "call_id": event.tool_call_id}))
            return
        if isinstance(event, PartStartEvent) and isinstance(event.part, ToolCallPart):
            call_id = event.part.tool_call_id
            if call_id in emitted_tool_ids:
                return
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
            return

    async def run_agent() -> None:
        nonlocal turn
        try:
            async with agent.iter(prompt) as run:
                async for node in run:
                    # Each ModelRequestNode is one model call — handy progress
                    # signal even though the SPEC marks this event optional.
                    if Agent.is_model_request_node(node):
                        turn += 1
                        await queue.put(_sse({"kind": "model_call", "turn": turn}))
                        async with node.stream(run.ctx) as stream:
                            async for event in stream:
                                await emit_event(event)
                    elif Agent.is_call_tools_node(node):
                        # Tool start/finish events flow here.
                        async with node.stream(run.ctx) as stream:
                            async for event in stream:
                                await emit_event(event)
                final_text = ""
                if run.result is not None:
                    out = run.result.output
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
