"""loseit-openwebui-agent — FastAPI gateway invoking a Kitaru deployed flow."""

import os

if os.environ.get("KITARU_API_KEY") and not os.environ.get("KITARU_AUTH_TOKEN"):
    os.environ["KITARU_AUTH_TOKEN"] = os.environ["KITARU_API_KEY"]
