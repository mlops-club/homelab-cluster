"""FastAPI service exposing the loseit-agent over SSE.

Concurrency model: one in-memory `ChatState` per chat_id, holding the
pydantic-ai message_history and an optional pending clarify question.
Resume = the user's next message replays the same chat_id; we re-run
`agent.run(answer, message_history=history)`. No `kitaru.wait()`, no
worker threads parked in poll loops — each paused chat costs ~10 KB.

A background task evicts ChatStates idle for more than `chat_ttl_minutes`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

# Bridge env vars BEFORE any kitaru/zenml import — the SDK reads them at
# module-import time and can't be reconfigured after.
if os.environ.get("KITARU_API_KEY") and not os.environ.get("KITARU_AUTH_TOKEN"):
    os.environ["KITARU_AUTH_TOKEN"] = os.environ["KITARU_API_KEY"]

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from loseit_agent.agent import AgentConfig, ClarifyRequested, build_agent

logger = logging.getLogger("loseit-agent")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    agent_token_expected: str = ""
    ollama_base_url: str = "http://ollama.ollama.svc.cluster.local:11434/v1"
    ollama_model: str = "qwen3:8b"
    loseit_bin: str = "loseit"
    loseit_token_path: Path = Path("/home/agent/.config/loseit/token")
    kitaru_server_url: str = ""
    kitaru_api_key: str = ""
    kitaru_loseit_secret_name: str = "loseit-token"
    kitaru_project: str = ""
    chat_ttl_minutes: int = 30
    chat_sweep_interval_s: int = 60


SETTINGS = Settings()


def _fetch_loseit_creds() -> None:
    if not SETTINGS.kitaru_server_url or not SETTINGS.kitaru_api_key:
        logger.warning("Kitaru creds missing; loseit calls will fail")
        return
    base = SETTINGS.kitaru_server_url.rstrip("/")
    headers = {"Authorization": f"Bearer {SETTINGS.kitaru_api_key}"}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(
                f"{base}/api/v1/secrets",
                params={"name": SETTINGS.kitaru_loseit_secret_name, "hydrate": "false"},
                headers=headers,
            )
            r.raise_for_status()
            items = r.json().get("items", [])
            if not items:
                logger.error("Kitaru secret %r not found", SETTINGS.kitaru_loseit_secret_name)
                return
            secret_id = items[0]["id"]
            r = client.get(
                f"{base}/api/v1/secrets/{secret_id}",
                params={"hydrate": "true"},
                headers=headers,
            )
            r.raise_for_status()
            values: dict[str, str] = r.json().get("body", {}).get("values", {}) or {}
    except Exception as exc:
        logger.exception("Kitaru fetch failed: %s", exc)
        return
    token = values.get("token", "")
    if not token:
        logger.error("Kitaru secret has no `token` key")
        return
    SETTINGS.loseit_token_path.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.loseit_token_path.write_text(token)
    SETTINGS.loseit_token_path.chmod(0o600)
    logger.info("loseit-token: %d bytes → %s", len(token), SETTINGS.loseit_token_path)
    import os

    for key in ("user_id", "user_name", "hours_from_gmt"):
        if key in values:
            os.environ[f"LOSEIT_{key.upper()}"] = str(values[key])


def _hours_from_gmt() -> int:
    import os

    try:
        return int(os.environ.get("LOSEIT_HOURS_FROM_GMT", "-6"))
    except ValueError:
        return -6


@dataclass
class ChatState:
    history: list[ModelMessage] = field(default_factory=list)
    pending_question: str | None = None
    pending_options: list[str] = field(default_factory=list)
    last_used_at: float = field(default_factory=time.monotonic)


@dataclass
class AppState:
    chats: dict[str, ChatState] = field(default_factory=dict)
    chats_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    agent: Any = None
    inner_agent: Agent | None = None


STATE = AppState()


async def _sweep_chats_loop() -> None:
    ttl_s = SETTINGS.chat_ttl_minutes * 60
    while True:
        await asyncio.sleep(SETTINGS.chat_sweep_interval_s)
        cutoff = time.monotonic() - ttl_s
        async with STATE.chats_lock:
            stale = [k for k, v in STATE.chats.items() if v.last_used_at < cutoff]
            for k in stale:
                del STATE.chats[k]
        if stale:
            logger.info("swept %d stale chat states", len(stale))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _fetch_loseit_creds()
    cfg = AgentConfig(
        ollama_base_url=SETTINGS.ollama_base_url,
        model_name=SETTINGS.ollama_model,
        loseit_bin=SETTINGS.loseit_bin,
        hours_from_gmt=_hours_from_gmt(),
    )
    STATE.agent, STATE.inner_agent = build_agent(cfg)
    logger.info("agent ready (model=%s, endpoint=%s)", cfg.model_name, cfg.ollama_base_url)
    sweep_task = asyncio.create_task(_sweep_chats_loop())
    try:
        yield
    finally:
        sweep_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await sweep_task


app = FastAPI(title="loseit-agent", version="0.1.0", lifespan=lifespan)


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    if not SETTINGS.agent_token_expected:
        raise HTTPException(503, "AGENT_TOKEN_EXPECTED not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer", headers={"WWW-Authenticate": "Bearer"})
    if authorization.split(" ", 1)[1].strip() != SETTINGS.agent_token_expected:
        raise HTTPException(401, "Invalid bearer")


class RunRequest(BaseModel):
    prompt: str = Field(..., description="Natural-language request.")
    chat_id: str | None = Field(default=None, description="Open WebUI chat id.")


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.post("/run", dependencies=[Depends(require_bearer)])
async def run_endpoint(body: RunRequest) -> StreamingResponse:
    chat_id = body.chat_id or f"_anon_{uuid.uuid4().hex[:12]}"
    return StreamingResponse(
        _run_or_resume(chat_id, body.prompt),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'), default=str)}\n\n"


def _args_preview(args: Any) -> str:
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            return args[:80]
    if isinstance(args, dict):
        if len(args) == 1:
            (v,) = args.values()
            return (v if isinstance(v, str) else json.dumps(v, default=str))[:80]
        return json.dumps(args, default=str)[:80]
    return str(args)[:80]


async def _run_or_resume(chat_id: str, prompt: str) -> AsyncIterator[str]:
    async with STATE.chats_lock:
        chat = STATE.chats.get(chat_id) or ChatState()
        STATE.chats[chat_id] = chat
        chat.last_used_at = time.monotonic()

    # If we were waiting on a clarify question, just feed the answer in.
    if chat.pending_question:
        prompt = f"My answer to your earlier question ({chat.pending_question!r}): {prompt}"
        chat.pending_question = None
        chat.pending_options = []

    event_queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def event_stream_handler(_ctx, stream) -> None:
        call_meta: dict[str, tuple[float, str, str]] = {}  # call_id -> (started, name, args_preview)
        async for event in stream:
            if isinstance(event, FunctionToolCallEvent):
                call_id = event.part.tool_call_id
                name = event.part.tool_name
                args_preview = _args_preview(event.part.args)
                call_meta[call_id] = (time.monotonic(), name, args_preview)
                event_queue.put_nowait({
                    "kind": "tool",
                    "name": name,
                    "args_preview": args_preview,
                    "call_id": call_id,
                })
            elif isinstance(event, FunctionToolResultEvent):
                started, name, args_preview = call_meta.pop(event.tool_call_id, (None, "?", ""))
                elapsed = round(time.monotonic() - started, 2) if started else None
                result = getattr(event.result, "content", event.result)
                if not isinstance(result, str):
                    try:
                        result = json.dumps(result, default=str)
                    except Exception:
                        result = repr(result)
                truncated = len(result) > 4000
                event_queue.put_nowait({
                    "kind": "tool_done",
                    "name": name,
                    "args_preview": args_preview,
                    "call_id": event.tool_call_id,
                    "elapsed_s": elapsed,
                    "result_preview": result[:4000],
                    "result_truncated": truncated,
                })

    runner_task = asyncio.create_task(_run_agent(chat, prompt, event_stream_handler, event_queue))
    while True:
        event = await event_queue.get()
        if event is None:
            break
        yield _sse(event)
    await runner_task


async def _run_agent(
    chat: ChatState,
    prompt: str,
    handler,
    queue: asyncio.Queue,
) -> None:
    try:
        result = await STATE.agent.run(
            prompt,
            message_history=chat.history,
            event_stream_handler=handler,
        )
        chat.history = list(result.all_messages())
        text = result.output if isinstance(result.output, str) else str(result.output)
        queue.put_nowait({"kind": "final", "text": text})
    except ClarifyRequested as exc:
        chat.pending_question = exc.question
        chat.pending_options = exc.options
        chat.history = _history_for_pending_clarify(chat)
        queue.put_nowait({
            "kind": "wait",
            "prompt": exc.question,
            "options": exc.options,
        })
    except Exception as exc:
        logger.exception("agent run failed")
        queue.put_nowait({
            "kind": "error",
            "message": f"{type(exc).__name__}: {exc}",
        })
    finally:
        chat.last_used_at = time.monotonic()
        queue.put_nowait(None)


def _history_for_pending_clarify(chat: ChatState) -> list[ModelMessage]:
    """Trim the history to what's safe to replay on resume.

    pydantic-ai's tool-call-and-result pairs must be balanced; a clarify
    that raised mid-run leaves a pending tool call with no result. We
    drop the trailing in-flight model request (the one that issued the
    clarify call) so the next agent.run() starts a clean turn with the
    user's answer as a fresh prompt.
    """
    history = list(chat.history)
    while history and getattr(history[-1], "kind", None) == "request":
        history.pop()
    return history


def main() -> None:
    import uvicorn

    uvicorn.run("loseit_agent.service:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
