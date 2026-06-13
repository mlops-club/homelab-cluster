"""FastAPI gateway between Open WebUI's Pipe and Kitaru's deployed flow.

The agent itself runs as a Kitaru deployment named `loseit_agent_flow` (see
the `loseit-kitaru-workflow` package). This service:

  1. Accepts a chat prompt + chat_id from the Open WebUI Pipe.
  2. Invokes the deployed flow via `KitaruClient.deployments.invoke()`.
  3. Polls/streams the resulting execution and forwards events to the Pipe
     in our SSE wire format.
  4. Handles HITL: when the flow's `clarify` tool fires a wait condition,
     this gateway emits a `wait` SSE frame; on the next chat turn with the
     same chat_id, it resolves the wait via `client.executions.input(...)`.

NO agent code lives here — this is purely a transport gateway.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("loseit-openwebui-agent")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    agent_token_expected: str = ""
    kitaru_flow_name: str = "loseit_agent_flow"
    kitaru_flow_tag: str = "default"
    chat_ttl_minutes: int = 30
    chat_sweep_interval_s: int = 60
    execution_poll_interval_s: float = 1.0


SETTINGS = Settings()


@dataclass
class ChatState:
    pending_exec_id: str | None = None
    pending_wait_name: str | None = None
    last_used_at: float = field(default_factory=time.monotonic)


@dataclass
class AppState:
    chats: dict[str, ChatState] = field(default_factory=dict)
    chats_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


STATE = AppState()


async def _sweep_loop() -> None:
    ttl = SETTINGS.chat_ttl_minutes * 60
    while True:
        await asyncio.sleep(SETTINGS.chat_sweep_interval_s)
        cutoff = time.monotonic() - ttl
        async with STATE.chats_lock:
            stale = [k for k, v in STATE.chats.items() if v.last_used_at < cutoff]
            for k in stale:
                del STATE.chats[k]
        if stale:
            logger.info("swept %d stale chats", len(stale))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_sweep_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="loseit-openwebui-agent", version="0.1.0", lifespan=lifespan)


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    if not SETTINGS.agent_token_expected:
        raise HTTPException(503, "AGENT_TOKEN_EXPECTED not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer", headers={"WWW-Authenticate": "Bearer"})
    if authorization.split(" ", 1)[1].strip() != SETTINGS.agent_token_expected:
        raise HTTPException(401, "Invalid bearer")


class RunRequest(BaseModel):
    prompt: str = Field(..., description="Natural-language meal-log request.")
    chat_id: str | None = Field(default=None, description="Open WebUI chat id.")


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'), default=str)}\n\n"


def _get_client() -> Any:
    from kitaru.client import KitaruClient

    return KitaruClient()


@app.post("/run", dependencies=[Depends(require_bearer)])
async def run_endpoint(body: RunRequest) -> StreamingResponse:
    chat_id = body.chat_id or f"_anon_{int(time.monotonic() * 1000)}"
    return StreamingResponse(
        _run_or_resume(chat_id, body.prompt),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_or_resume(chat_id: str, prompt: str) -> AsyncIterator[str]:
    async with STATE.chats_lock:
        chat = STATE.chats.get(chat_id) or ChatState()
        STATE.chats[chat_id] = chat
        chat.last_used_at = time.monotonic()

    client = _get_client()

    if chat.pending_exec_id and chat.pending_wait_name:
        try:
            await asyncio.to_thread(
                client.executions.input,
                chat.pending_exec_id,
                wait=chat.pending_wait_name,
                value=prompt,
            )
            exec_id = chat.pending_exec_id
            chat.pending_wait_name = None
        except Exception as exc:
            yield _sse({"kind": "error", "message": f"resume failed: {exc}"})
            chat.pending_exec_id = None
            chat.pending_wait_name = None
            return
    else:
        try:
            handle = await asyncio.to_thread(
                client.deployments.invoke,
                flow=SETTINGS.kitaru_flow_name,
                tag=SETTINGS.kitaru_flow_tag,
                inputs={"prompt": prompt, "chat_id": chat_id},
            )
            exec_id = handle.exec_id
            chat.pending_exec_id = exec_id
        except Exception as exc:
            yield _sse({"kind": "error", "message": f"invoke failed: {exc}"})
            return

    async for frame in _stream_execution(client, exec_id, chat):
        yield frame


async def _stream_execution(
    client: Any, exec_id: str, chat: ChatState
) -> AsyncIterator[str]:
    """Bridge Kitaru's SSE execution events into our chat wire format.

    `client.executions.events(exec_id)` returns a sync iterator of
    ExecutionEvent objects backed by a `text/event-stream` REST endpoint
    with auto-reconnect (see kitaru `_client/_events.py`). We pull each
    event on a thread and translate it into our `tool` / `tool_done` /
    `wait` / `final` / `error` schema.
    """
    loop = asyncio.get_running_loop()

    def _open_iter():
        return client.executions.events(exec_id, reconnect=True)

    try:
        it = await loop.run_in_executor(None, _open_iter)
    except Exception as exc:
        yield _sse({"kind": "error", "message": f"open stream failed: {exc}"})
        chat.pending_exec_id = None
        chat.pending_wait_name = None
        return

    def _next():
        return next(it, None)

    while True:
        try:
            event = await loop.run_in_executor(None, _next)
        except Exception as exc:
            yield _sse({"kind": "error", "message": f"stream read failed: {exc}"})
            chat.pending_exec_id = None
            chat.pending_wait_name = None
            return

        if event is None:
            break

        kind = getattr(event, "kind", "")
        payload = getattr(event, "payload", {}) or {}

        if kind in ("tool_call", "model_call"):
            yield _sse({
                "kind": "tool",
                "name": payload.get("name", kind),
                "args_preview": str(payload.get("args", ""))[:80],
                "call_id": payload.get("call_id", ""),
            })
        elif kind == "tool_done":
            yield _sse({
                "kind": "tool_done",
                "name": payload.get("name", "?"),
                "args_preview": str(payload.get("args", ""))[:80],
                "call_id": payload.get("call_id", ""),
                "elapsed_s": payload.get("elapsed_s"),
                "result_preview": str(payload.get("result", ""))[:4000],
                "result_truncated": len(str(payload.get("result", ""))) > 4000,
            })
        elif kind in ("wait_pending", "execution_paused"):
            wait_name = payload.get("wait_name") or payload.get("name")
            chat.pending_wait_name = wait_name
            yield _sse({
                "kind": "wait",
                "exec_id": exec_id,
                "wait_name": wait_name,
                "prompt": payload.get("question", "Need clarification."),
                "options": payload.get("options", []),
            })
            return
        elif kind in ("execution_completed", "execution_finished"):
            yield _sse({"kind": "final", "text": str(payload.get("output", ""))})
            chat.pending_exec_id = None
            chat.pending_wait_name = None
            return
        elif kind in ("execution_failed", "error"):
            yield _sse({"kind": "error", "message": str(payload.get("message", "failed"))})
            chat.pending_exec_id = None
            chat.pending_wait_name = None
            return


def main() -> None:
    import uvicorn

    uvicorn.run("loseit_openwebui_agent.service:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
