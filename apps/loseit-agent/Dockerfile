# Multi-stage uv-based image for the loseit-agent FastAPI service.
#
# Slice S2: this image only ships the echo FastAPI server. No pydantic-ai, no
# kitaru, no lose-it CLI yet — those land in S4-S6. The Dockerfile is shaped
# so we can drop those dependencies in later by extending the `uv pip install`
# line below.
#
# Base image rationale: ghcr.io/astral-sh/uv:python3.12-bookworm-slim ships
# both uv and CPython 3.12 in a slim Debian base, so we skip the pip-vs-uv
# bootstrapping dance.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies into a project-local venv. We avoid a pyproject/lock
# for S2 to keep the image trivially auditable; S4 will swap to a lockfile
# when we add pydantic-ai + lose-it.
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    VIRTUAL_ENV=/opt/venv

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      "fastapi==0.115.*" \
      "uvicorn[standard]==0.32.*" \
      "httpx==0.27.*"

# ---------- runtime ----------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    VIRTUAL_ENV=/opt/venv

# Non-root user. UID 10001 is arbitrary but stays out of the way of any
# host-mapped UIDs we may add later.
RUN groupadd --system --gid 10001 agent \
 && useradd --system --uid 10001 --gid agent --home /home/agent --create-home agent

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=agent:agent server.py /app/server.py

USER agent
EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
