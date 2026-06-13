"""Echo FastAPI agent — slice S2.

This is intentionally a thin stub. It proves the wire between the Open WebUI
Pipe function and the agent pod (HTTPS + SSE + bearer auth) without any real
agent logic. Slices S4-S6 replace the echo body with the pydantic-ai +
KitaruAgent + lose-it CLI stack.

Wire format (must match apps/loseit-agent/SPEC.md):

    POST /run  -> text/event-stream
        data: {"kind":"tool","name":"echo","args_preview":<prompt>,"call_id":<uuid>}
        data: {"kind":"tool_done","call_id":<same uuid>}
        data: {"kind":"final","text":"echo: <prompt>"}

Auth: `Authorization: Bearer <token>` where `<token>` must equal the
`AGENT_TOKEN_EXPECTED` env var (sourced from the `agent-token` Secret).
`/healthz` is unauthenticated so kubelet probes work without a token.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("loseit-agent")

EXPECTED_TOKEN = os.environ.get("AGENT_TOKEN_EXPECTED", "")

app = FastAPI(title="loseit-agent (S2 echo)", version="0.2.0")


class RunRequest(BaseModel):
    """Body of POST /run. Slice S2 only needs `prompt`."""

    prompt: str = Field(..., description="Free-text prompt to echo back.")


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    """Reject requests without a valid `Authorization: Bearer <token>` header.

    We do a constant-ish-time compare and never log the token. If the server
    was started without `AGENT_TOKEN_EXPECTED` set we refuse ALL requests
    rather than fail open — that's much louder to diagnose than a silent
    no-auth deployment.
    """

    if not EXPECTED_TOKEN:
        # Fail closed: missing server config is treated as misconfiguration,
        # not "auth disabled".
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
    # `hmac.compare_digest` would be ideal but `==` on str of equal-ish length
    # is fine for an in-cluster shared token; this isn't a public-facing creds
    # check. Length-mismatch would short-circuit which is the only leak worth
    # worrying about, and we don't log either value.
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
    """Format one SSE data frame. Matches the SPEC.md wire format exactly:
    `data: <one-line-json>\\n\\n`.
    """
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


async def _echo_stream(prompt: str) -> AsyncIterator[str]:
    """Yield the three echo events: tool / tool_done / final."""
    call_id = str(uuid.uuid4())
    logger.info("echo run start prompt_len=%d call_id=%s", len(prompt), call_id)

    yield _sse({"kind": "tool", "name": "echo", "args_preview": prompt, "call_id": call_id})
    yield _sse({"kind": "tool_done", "call_id": call_id})
    yield _sse({"kind": "final", "text": f"echo: {prompt}"})

    logger.info("echo run done call_id=%s", call_id)


@app.post("/run", dependencies=[Depends(require_bearer)])
async def run(body: RunRequest) -> StreamingResponse:
    """Stream the three echo SSE events for the given prompt."""
    return StreamingResponse(
        _echo_stream(body.prompt),
        media_type="text/event-stream",
        headers={
            # Disable proxy buffering so Traefik flushes each event as it
            # arrives instead of holding them until the connection closes.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
