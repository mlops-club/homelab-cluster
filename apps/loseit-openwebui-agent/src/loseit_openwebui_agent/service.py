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
    kitaru_ui_base: str = "https://kitaru.priv.mlops-club.org"
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


def _kitaru_link(exec_id: str, flow_id: str | None = None) -> str:
    base = SETTINGS.kitaru_ui_base.rstrip("/")
    if flow_id:
        return f"{base}/flows/{flow_id}/executions/{exec_id}"
    return f"{base}/executions/{exec_id}"


def _safe_load(art: Any) -> Any:
    try:
        return art.load()
    except Exception as exc:
        return f"<unloadable: {type(exc).__name__}>"


def _trim(s: Any, n: int = 80) -> str:
    text = s if isinstance(s, str) else json.dumps(s, default=str)
    return (text[: n - 1] + "…") if len(text) > n else text


def _tool_args_for(cp: Any) -> str:
    """Return a compact preview of a tool checkpoint's args."""
    for art in getattr(cp, "artifacts", None) or []:
        if getattr(art, "kind", None) == "input" and getattr(art, "name", "") == "tool_args":
            val = _safe_load(art)
            # tool_args is usually {"args": {...}} or just the kwargs dict
            if isinstance(val, dict) and "args" in val and len(val) == 1:
                val = val["args"]
            if isinstance(val, dict):
                # Render as k=v compact
                return _trim(", ".join(f"{k}={_trim(v, 20)}" for k, v in val.items()))
            return _trim(val)
    return ""


def _model_response_text(cp: Any) -> str:
    """Read the model's text response from an llm_call checkpoint's output artifact."""
    for art in getattr(cp, "artifacts", None) or []:
        if getattr(art, "kind", None) == "response":
            val = _safe_load(art)
            return _extract_text(val)
    return ""


def _extract_text(val: Any) -> str:
    """Drill into a pydantic-ai ModelResponse to find user-visible text."""
    if isinstance(val, str):
        return val
    parts = getattr(val, "parts", None) if not isinstance(val, dict) else val.get("parts")
    if parts:
        out = []
        for p in parts:
            if hasattr(p, "content"):
                out.append(str(p.content))
            elif isinstance(p, dict) and "content" in p:
                out.append(str(p["content"]))
        if out:
            return "\n".join(out).strip()
    return str(val)[:500] if val is not None else ""


async def _stream_execution(
    client: Any, exec_id: str, chat: ChatState
) -> AsyncIterator[str]:
    """Poll the Kitaru execution and emit link/tool/reason/final/wait/error frames.

    Kitaru's `executions.events()` is server-side disabled so we poll
    `executions.get(exec_id)` (hydrates checkpoints + artifacts) on a tick.

    Frame schedule per Kitaru checkpoint kind:
      * loseit_agent_model_request[_N] (llm_call): when it completes,
        we load the response artifact and yield a `reason` frame with
        the model's chain-of-thought-ish text. The LAST one is the
        final answer.
      * <tool>_tool: yield `tool` frame on enter (running), `tool_done`
        on exit. args_preview is read from the `tool_args` artifact.
    """
    seen_started: set[str] = set()
    seen_done: set[str] = set()
    last_llm_text = ""
    link_emitted = False

    while True:
        try:
            execution = await asyncio.to_thread(client.executions.get, exec_id)
        except Exception as exc:
            yield _sse({"kind": "error", "message": f"poll failed: {exc}"})
            chat.pending_exec_id = None
            chat.pending_wait_name = None
            return

        if not link_emitted:
            flow_id = getattr(execution, "flow_id", None)
            yield _sse({
                "kind": "link",
                "url": _kitaru_link(exec_id, flow_id),
                "label": "Open this run in Kitaru",
            })
            link_emitted = True

        checkpoints = list(getattr(execution, "checkpoints", None) or [])
        for cp in checkpoints:
            cp_name = getattr(cp, "name", "?")
            cp_id = str(getattr(cp, "call_id", cp_name))
            cp_status = str(getattr(cp, "status", ""))

            is_tool = cp_name.endswith("_tool")
            is_llm = cp_name.startswith("loseit_agent_model_request") or cp_name.startswith("loseit-agent_model_request")

            if is_tool:
                tool_name = cp_name[:-5]
                if cp_status in ("running", "started", "executionstatus.running") and cp_id not in seen_started:
                    seen_started.add(cp_id)
                    yield _sse({
                        "kind": "tool",
                        "name": tool_name,
                        "args_preview": _tool_args_for(cp),
                        "call_id": cp_id,
                    })
                elif "completed" in cp_status or "succeeded" in cp_status or "finished" in cp_status or "failed" in cp_status:
                    if cp_id in seen_done:
                        continue
                    seen_done.add(cp_id)
                    seen_started.add(cp_id)
                    started_at = getattr(cp, "started_at", None)
                    ended_at = getattr(cp, "ended_at", None)
                    elapsed = (ended_at - started_at).total_seconds() if started_at and ended_at else None
                    yield _sse({
                        "kind": "tool_done",
                        "name": tool_name,
                        "args_preview": _tool_args_for(cp),
                        "call_id": cp_id,
                        "elapsed_s": round(elapsed, 2) if elapsed is not None else None,
                        "result_preview": "",
                        "result_truncated": False,
                        "is_error": "failed" in cp_status,
                    })

            elif is_llm and ("completed" in cp_status or "succeeded" in cp_status):
                if cp_id in seen_done:
                    continue
                seen_done.add(cp_id)
                text = _model_response_text(cp)
                if text and text != last_llm_text:
                    last_llm_text = text
                    yield _sse({"kind": "reason", "text": text})

        status_value = getattr(execution, "status", "")
        status_str = str(status_value).lower()
        pending_wait = getattr(execution, "pending_wait", None)

        if pending_wait:
            wait_name = getattr(pending_wait, "name", None) or getattr(pending_wait, "wait_name", None)
            chat.pending_wait_name = wait_name
            yield _sse({
                "kind": "wait",
                "exec_id": exec_id,
                "wait_name": wait_name,
                "prompt": getattr(pending_wait, "question", "Need clarification."),
                "options": (getattr(pending_wait, "metadata", {}) or {}).get("tool_args", {}).get("options", []) or [],
            })
            return

        if "completed" in status_str or "succeeded" in status_str or "finished" in status_str:
            # last_llm_text was set from the LAST llm_call's response —
            # that's the agent's final answer to the user.
            yield _sse({"kind": "final", "text": last_llm_text or "(flow completed)"})
            chat.pending_exec_id = None
            chat.pending_wait_name = None
            return

        if "failed" in status_str or "errored" in status_str or "cancelled" in status_str:
            reason = getattr(execution, "status_reason", "") or "(no reason)"
            yield _sse({"kind": "error", "message": f"execution {status_str}: {reason}"})
            chat.pending_exec_id = None
            chat.pending_wait_name = None
            return

        await asyncio.sleep(SETTINGS.execution_poll_interval_s)


def main() -> None:
    import uvicorn

    uvicorn.run("loseit_openwebui_agent.service:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
