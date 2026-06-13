# Multi-stage uv-based image for the loseit-agent FastAPI service.
#
# Slice S5: the image now also ships the Kitaru SDK (with its pydantic-ai
# adapter extra). S6 will add 4 more tools (no new Python deps needed).
#
# Base image rationale: ghcr.io/astral-sh/uv:python3.12-bookworm-slim ships
# both uv and CPython 3.12 in a slim Debian base, so we skip the pip-vs-uv
# bootstrapping dance.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# git: required so uv pip install can clone the lose-it repo.
# ca-certificates: required for HTTPS to GitHub during the install above and
# at runtime for Ollama + loseit.com.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install dependencies into a project-local venv. We avoid a pyproject/lock
# for now to keep the image trivially auditable; we'll swap to a lockfile
# once the dep set settles (S5+).
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    VIRTUAL_ENV=/opt/venv

# We install `pydantic-ai-slim[openai]` rather than the full `pydantic-ai`
# meta-package because the full distribution pulls in extras (fastmcp,
# logfire, etc.) that drag in opentelemetry-sdk constraints conflicting
# with kitaru[pydantic-ai]==0.15.0 → zenml[local]>=0.94.6 → opentelemetry-sdk
# ==1.38.0. The slim package gives us `Agent`, `RunContext`, the OpenAI
# provider/model classes, and all the streaming-message types we use —
# everything in server.py works against the slim distribution.
#
# Version range matches what Kitaru's pydantic-ai adapter supports
# (>=1.89,<1.104). uvicorn is bumped to >=0.35 because kitaru's MCP
# transitive dep `fastmcp` requires it.
# s3fs + boto3 are needed by ZenML's S3 artifact store flavor (used by the
# `default-s3` Kitaru stack — see apps/kitaru/ops/register-artifact-store.sh
# and apps/kitaru/ARTIFACTS.md). The Kitaru server image ships them, but the
# `kitaru[pydantic-ai]` extra does NOT, so we add them explicitly here. The
# version ranges match what ZenML 0.94.x supports (see
# zenml/integrations/s3/__init__.py).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
      "fastapi==0.115.*" \
      "uvicorn[standard]>=0.35,<0.40" \
      "httpx>=0.28,<0.29" \
      "pydantic-ai-slim[openai]>=1.89,<1.104" \
      "kitaru[pydantic-ai]==0.15.0" \
      "s3fs>2022.3.0,!=2025.3.1" \
      "boto3" \
      "git+https://github.com/phitoduck/lose-it@main"

# ---------- runtime ----------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    VIRTUAL_ENV=/opt/venv

# ca-certificates: still needed at runtime for HTTPS to Ollama + loseit.com.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Non-root user. UID 10001 is arbitrary but stays out of the way of any
# host-mapped UIDs we may add later. The lose-it CLI reads its token from
# `$HOME/.config/loseit/token`; we materialize it at startup in server.py.
RUN groupadd --system --gid 10001 agent \
 && useradd --system --uid 10001 --gid agent --home /home/agent --create-home agent

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=agent:agent server.py /app/server.py

USER agent
ENV HOME=/home/agent
EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
