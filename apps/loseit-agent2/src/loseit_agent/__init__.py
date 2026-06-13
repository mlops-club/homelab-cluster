"""loseit-agent — FastAPI service for a pydantic-ai agent driving loseit CLI.

Env-var bridging happens here BEFORE any kitaru/zenml import so the SDK
picks up service-account credentials from a single canonical name.
"""

from __future__ import annotations

import os

if os.environ.get("KITARU_API_KEY") and not os.environ.get("KITARU_AUTH_TOKEN"):
    os.environ["KITARU_AUTH_TOKEN"] = os.environ["KITARU_API_KEY"]
