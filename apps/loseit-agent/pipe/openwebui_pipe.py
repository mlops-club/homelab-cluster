"""Open WebUI Pipe Function — bridges chat ↔ loseit-agent FastAPI service.

Upload this in Open WebUI: Workspace → Functions → +Add → paste this file.
Once uploaded, "loseit-agent" appears as a selectable model in the chat picker.

Wire format consumed from the agent's SSE stream (one JSON object per `data:` line):

    {"kind":"tool",       "name":"...", "args_preview":"...", "call_id":"..."}
    {"kind":"tool_done",  "call_id":"..."}
    {"kind":"model_call", "turn": 1}
    {"kind":"checkpoint", "name":"search_tool", "phase":"started"|"finished",
                          "elapsed_s": 1.5}
    {"kind":"wait",       "exec_id":"...", "wait_name":"...", "prompt":"...", "options":[...]}
    {"kind":"final",      "text":"..."}
    {"kind":"error",      "message":"..."}

UX features:
  - Heartbeat status every 3s while the agent is silent so the chat doesn't
    feel like it hung. Shows elapsed-since-start.
  - Surfaces Kitaru `checkpoint` events as live status — the agent's per-call
    checkpoints (`search_tool`, `log_food_tool`, …) appear in the chat as the
    agent works, even though we don't get pydantic-ai's per-call SSE frames
    (those are mutually exclusive with kitaru.wait() in granular mode).
  - On `wait`, renders the question + options as a normal chat message so
    the user can reply (their reply auto-routes to /resume).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator

import httpx
from pydantic import BaseModel


HEARTBEAT_INTERVAL_S = 3.0


class Pipe:
    class Valves(BaseModel):
        agent_url: str = "https://loseit-agent.priv.mlops-club.org"
        auth_token: str = ""  # set in Open WebUI: Workspace → Functions → loseit-agent → Valves
        request_timeout_s: float = 600.0

    def __init__(self) -> None:
        self.valves = self.Valves()
        self.id = "loseit-agent"
        self.name = "loseit-agent"

    async def pipe(
        self,
        body: dict[str, Any],
        __event_emitter__,
        __metadata__: dict[str, Any] | None = None,
    ) -> str:
        prompt = body["messages"][-1]["content"]

        # Open WebUI doesn't reliably persist Pipe-side __metadata__ mutations
        # across chat turns, so we can't track pending HITL waits there.
        # Instead the server maintains a chat_id → exec_id map and decides
        # run-vs-resume internally — we just always POST /run with chat_id.
        meta = __metadata__ or {}
        chat_id = meta.get("chat_id") or body.get("chat_id") or body.get("session_id")

        url = f"{self.valves.agent_url}/run"
        payload = {"prompt": prompt, "chat_id": chat_id}
        initial_status = "Starting agent…"

        started = time.monotonic()
        # Track the last "human-readable" status we showed; the heartbeat task
        # re-emits it with an updated elapsed counter so the chat shimmer never
        # looks frozen for more than HEARTBEAT_INTERVAL_S.
        last_status: dict[str, str] = {"text": initial_status}

        await self._status(__event_emitter__, f"{initial_status} (0s)", done=False)

        async def heartbeat() -> None:
            try:
                while True:
                    await asyncio.sleep(HEARTBEAT_INTERVAL_S)
                    elapsed = int(time.monotonic() - started)
                    await self._status(
                        __event_emitter__,
                        f"{last_status['text']} ({elapsed}s)",
                        done=False,
                    )
            except asyncio.CancelledError:
                return

        hb_task = asyncio.create_task(heartbeat())

        final_text = ""

        # We build up the chat message text in parallel with the deltas so the
        # function's return value at the end matches what Open WebUI rendered
        # via delta events. Different OW versions handle "return X after
        # streaming deltas" differently; returning the same text we streamed
        # guarantees the chat shows the full trace either way.
        accumulated = ""

        # Track in-flight tool calls so tool_done can render the elapsed time
        # next to the matching opening line.
        active_calls: dict[str, str] = {}  # call_id -> markdown-line text

        try:
            async for evt in self._stream(url, payload):
                kind = evt.get("kind")
                if kind == "tool":
                    name = evt.get("name", "?")
                    args = evt.get("args_preview", "")
                    call_id = evt.get("call_id", "")
                    line = f"\n🔧 `{name}({args})` "
                    active_calls[call_id] = line
                    accumulated += line
                    last_status["text"] = f"→ {name}({args})"
                    await self._status(__event_emitter__, last_status["text"], done=False)
                    # Emit the tool call as a markdown line in the chat
                    await __event_emitter__(
                        {"type": "chat:message:delta", "data": {"content": line}}
                    )
                elif kind == "tool_done":
                    call_id = evt.get("call_id", "")
                    elapsed = evt.get("elapsed_s")
                    suffix = f"✓ ({elapsed:.1f}s)\n" if isinstance(elapsed, (int, float)) else "✓\n"
                    accumulated += suffix
                    active_calls.pop(call_id, None)
                    last_status["text"] = "thinking"
                    await self._status(__event_emitter__, last_status["text"], done=False)
                    await __event_emitter__(
                        {"type": "chat:message:delta", "data": {"content": suffix}}
                    )
                elif kind == "model_call":
                    turn = evt.get("turn", "?")
                    last_status["text"] = f"thinking (turn {turn})"
                    await self._status(__event_emitter__, last_status["text"], done=False)
                elif kind == "checkpoint":
                    # Kitaru per-call checkpoint surfaced live by the server's
                    # polling task — visible in lieu of pydantic-ai's per-call
                    # SSE frames (which are turned off for kitaru.wait() reasons).
                    cp_name = evt.get("name", "?")
                    phase = evt.get("phase", "")
                    elapsed_s = evt.get("elapsed_s")
                    if phase == "started":
                        last_status["text"] = f"→ {cp_name}"
                    elif phase == "finished":
                        if elapsed_s is not None:
                            last_status["text"] = f"✓ {cp_name} ({elapsed_s:.1f}s)"
                        else:
                            last_status["text"] = f"✓ {cp_name}"
                    else:
                        last_status["text"] = f"{cp_name}: {phase}"
                    await self._status(__event_emitter__, last_status["text"], done=False)
                elif kind == "wait":
                    # Server already recorded the pending exec_id keyed by
                    # chat_id; we just need to render the question to the user.
                    question = evt.get("prompt") or "Need clarification."
                    options = evt.get("options") or []
                    body_text = "\n\n❓ **" + question + "**\n"
                    if options:
                        body_text += "\n" + "\n".join(f"- {o}" for o in options)
                        body_text += "\n\n*(Reply with one of the options above, or type your own — your next message in this chat continues the run.)*"
                    accumulated += body_text
                    await __event_emitter__(
                        {"type": "chat:message:delta", "data": {"content": body_text}}
                    )
                    final_text = body_text
                    break
                elif kind == "final":
                    final_text = evt.get("text", "")
                    chunk = "\n\n" + final_text
                    accumulated += chunk
                    # Append a separator + the final summary as chat content.
                    await __event_emitter__(
                        {"type": "chat:message:delta", "data": {"content": chunk}}
                    )
                elif kind == "error":
                    msg = evt.get("message", "agent error")
                    await __event_emitter__(
                        {"type": "notification", "data": {"type": "error", "content": msg}}
                    )
                    final_text = f"Error: {msg}"
                    break
        except Exception as exc:
            await __event_emitter__(
                {"type": "notification", "data": {"type": "error", "content": str(exc)}}
            )
            hb_task.cancel()
            return f"Pipe transport error: {exc}"
        finally:
            hb_task.cancel()
            try:
                await hb_task
            except (asyncio.CancelledError, Exception):
                pass

        # Always emit a final done so the shimmer stops.
        elapsed = int(time.monotonic() - started)
        await self._status(__event_emitter__, f"Done ({elapsed}s)", done=True)

        # Return the accumulated text we already streamed via deltas so the
        # message body is consistent whether OW persists the deltas or the
        # return value.
        return accumulated if accumulated else final_text

    async def _stream(self, url: str, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        if self.valves.auth_token:
            headers["Authorization"] = f"Bearer {self.valves.auth_token}"

        async with httpx.AsyncClient(timeout=self.valves.request_timeout_s) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        # ignore malformed lines — keeps the pipe resilient
                        continue

    @staticmethod
    async def _status(emit, description: str, done: bool) -> None:
        await emit(
            {
                "type": "status",
                "data": {"description": description, "done": done, "hidden": False},
            }
        )
