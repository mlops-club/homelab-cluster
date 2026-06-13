"""Open WebUI Pipe Function — bridges chat ↔ loseit-agent FastAPI service.

Upload this in Open WebUI: Workspace → Functions → +Add → paste this file.
Once uploaded, "loseit-agent" appears as a selectable model in the chat picker.

Wire format consumed from the agent's SSE stream (one JSON object per `data:` line):

    {"kind":"tool",       "name":"...", "args_preview":"...", "call_id":"..."}
    {"kind":"tool_done",  "call_id":"..."}
    {"kind":"model_call", "turn": 1}
    {"kind":"wait",       "exec_id":"...", "wait_name":"...", "prompt":"...", "options":[...]}
    {"kind":"final",      "text":"..."}
    {"kind":"error",      "message":"..."}
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx
from pydantic import BaseModel


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

        meta = __metadata__ or {}
        pending = (meta.get("loseit_agent") or {}).get("pending_exec_id")

        if pending:
            url = f"{self.valves.agent_url}/resume"
            payload = {"exec_id": pending, "value": prompt}
            await self._status(__event_emitter__, "Resuming…", done=False)
        else:
            url = f"{self.valves.agent_url}/run"
            payload = {"prompt": prompt}
            await self._status(__event_emitter__, "Starting agent…", done=False)

        final_text = ""
        new_pending: str | None = None

        try:
            async for evt in self._stream(url, payload):
                kind = evt.get("kind")
                if kind == "tool":
                    name = evt.get("name", "?")
                    args = evt.get("args_preview", "")
                    await self._status(__event_emitter__, f"→ {name}({args})", done=False)
                elif kind == "tool_done":
                    pass  # noop — the next status update overwrites
                elif kind == "model_call":
                    turn = evt.get("turn", "?")
                    await self._status(__event_emitter__, f"thinking (turn {turn})", done=False)
                elif kind == "wait":
                    new_pending = evt.get("exec_id")
                    question = evt.get("prompt") or "Need clarification."
                    options = evt.get("options") or []
                    body_text = question
                    if options:
                        body_text += "\n\n" + "\n".join(f"- {o}" for o in options)
                        body_text += "\n\n(Pick one or type your own.)"
                    final_text = body_text
                    break
                elif kind == "final":
                    final_text = evt.get("text", "")
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
            return f"Pipe transport error: {exc}"

        # Always emit a final done so the shimmer stops.
        await self._status(__event_emitter__, "Done", done=True)

        # Persist the wait exec_id so the next message in this chat routes to /resume.
        if new_pending:
            meta.setdefault("loseit_agent", {})["pending_exec_id"] = new_pending
        elif "loseit_agent" in meta:
            meta["loseit_agent"].pop("pending_exec_id", None)

        return final_text

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
