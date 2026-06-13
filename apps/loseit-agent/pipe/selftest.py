"""Self-test for the Open WebUI Pipe.

Run from the repo root:

    AGENT_URL=https://loseit-agent.priv.mlops-club.org \
    AUTH_TOKEN=$(kubectl -n loseit-agent get secret agent-token -o jsonpath='{.data.token}' | base64 -d) \
    uv run --no-project --with httpx --with pydantic \
        apps/loseit-agent/pipe/selftest.py

Simulates what Open WebUI's Pipe runtime does: instantiates the Pipe class,
sets valves, hands it a fake `__event_emitter__` callable that prints to
stdout, and calls `pipe()` with a prompt. Prints the final returned text.

This catches Pipe-code bugs without needing to upload to Open WebUI first.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from openwebui_pipe import Pipe  # noqa: E402


async def main() -> int:
    agent_url = os.environ.get("AGENT_URL")
    token = os.environ.get("AUTH_TOKEN")
    if not agent_url or not token:
        print("set AGENT_URL and AUTH_TOKEN", file=sys.stderr)
        return 2

    pipe = Pipe()
    pipe.valves.agent_url = agent_url
    pipe.valves.auth_token = token

    async def emit(event: dict) -> None:
        print(json.dumps(event))

    body = {"messages": [{"role": "user", "content": "hello self-test"}]}
    metadata: dict = {}

    final = await pipe.pipe(body, emit, metadata)
    print("=" * 40)
    print("FINAL:")
    print(final)
    print("=" * 40)
    print("METADATA:", metadata)

    assert "hello self-test" in final, f"expected echo, got: {final!r}"
    print("✅ selftest passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
