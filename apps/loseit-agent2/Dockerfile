FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" VIRTUAL_ENV=/opt/venv

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-cache /app

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" VIRTUAL_ENV=/opt/venv

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 agent \
 && useradd --system --uid 10001 --gid agent --home /home/agent --create-home agent

COPY --from=builder /opt/venv /opt/venv

USER agent
ENV HOME=/home/agent
EXPOSE 8000
CMD ["loseit-agent"]
