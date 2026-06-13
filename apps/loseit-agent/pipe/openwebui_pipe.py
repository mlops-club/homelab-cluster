"""Open WebUI Pipe Function — bridges chat ↔ loseit-agent FastAPI service.

Upload this in Open WebUI: Workspace → Functions → +Add → paste this file.
Once uploaded, "loseit-agent" appears as a selectable model in the chat picker.

Wire format consumed from the agent's SSE stream (one JSON object per `data:` line):

    {"kind":"tool",       "name":"...", "args_preview":"...", "call_id":"..."}
    {"kind":"tool_done",  "name":"...", "call_id":"...", "elapsed_s": 1.3}
    {"kind":"model_call", "turn": 1}
    {"kind":"wait",       "exec_id":"...", "wait_name":"...", "prompt":"...", "options":[...]}
    {"kind":"final",      "text":"..."}
    {"kind":"error",      "message":"..."}

UX:
  - Each `tool` event appends `🔧 name(args)` to the message body.
  - Each `tool_done` appends `✓ (1.3s)` on the same line.
  - `wait` emits `❓ question + options` and the run pauses; the user's next
    chat message resumes the run via the chat_id-keyed pending registry on
    the server side (the Pipe itself is stateless across turns).
  - `final` is appended after a blank line.

No heartbeat, no per-event status pings — the streaming tool-call deltas
already telegraph progress; an extra "thinking…" pill on top is just noise.
A single status emission at the end ("Done (Ns)") closes the shimmer.
"""

from __future__ import annotations

import json
import time
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

        # Open WebUI doesn't reliably persist Pipe-side __metadata__ mutations
        # across chat turns, so we can't track pending HITL waits there.
        # Instead the server maintains a chat_id → exec_id map and decides
        # run-vs-resume internally — we just always POST /run with chat_id.
        meta = __metadata__ or {}
        chat_id = meta.get("chat_id") or body.get("chat_id") or body.get("session_id")

        url = f"{self.valves.agent_url}/run"
        payload = {"prompt": prompt, "chat_id": chat_id}

        started = time.monotonic()

        # We build up the chat message text in parallel with the deltas so the
        # function's return value at the end matches what Open WebUI rendered
        # via delta events. Different OW versions handle "return X after
        # streaming deltas" differently; returning the same text we streamed
        # guarantees the chat shows the full trace either way.
        accumulated = ""
        final_text = ""

        try:
            async for evt in self._stream(url, payload):
                kind = evt.get("kind")
                if kind == "tool":
                    # We render the tool call as ONE <details> block at
                    # tool_done time; nothing to emit here.
                    pass
                elif kind == "tool_done":
                    name = evt.get("name", "?")
                    args = evt.get("args_preview", "")
                    elapsed = evt.get("elapsed_s")
                    elapsed_s = f"{elapsed:.1f}s" if isinstance(elapsed, (int, float)) else "?"
                    is_error = evt.get("is_error")
                    marker = "❌" if is_error else "✓"
                    result_preview = evt.get("result_preview", "") or ""
                    truncated = evt.get("result_truncated")

                    # If the result smells like JSON, fence it as json so OW
                    # syntax-highlights it. Otherwise leave it as plain text.
                    stripped = result_preview.strip()
                    fence = "json" if stripped.startswith(("{", "[")) else ""
                    body_lines = ["", f"```{fence}", result_preview, "```"]
                    if truncated:
                        body_lines.append("\n_(truncated to 4 KB; see Kitaru run inspector for full output)_")

                    block = (
                        f"\n<details>\n"
                        f"<summary>🔧 {name}({args}) {marker} ({elapsed_s})</summary>\n"
                        + "\n".join(body_lines)
                        + "\n\n</details>\n"
                    )
                    accumulated += block
                    await __event_emitter__(
                        {"type": "chat:message:delta", "data": {"content": block}}
                    )
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
                # `model_call` is dropped — the tool-call deltas already show
                # progress and the extra status events crowd the message.
        except Exception as exc:
            await __event_emitter__(
                {"type": "notification", "data": {"type": "error", "content": str(exc)}}
            )
            return f"Pipe transport error: {exc}"

        # Single terminal status so the shimmer stops.
        elapsed = int(time.monotonic() - started)
        await self._status(__event_emitter__, f"Done ({elapsed}s)", done=True)

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
