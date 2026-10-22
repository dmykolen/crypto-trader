# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.12.21-python3.13-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev --no-editable

# Explicit list — fails loudly if something's missing, instead of silently
# depending on .dockerignore to keep out .git/.env/data/ etc.
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.13-slim-trixie
# libgomp1: LightGBM's OpenMP runtime (the manylinux wheel links against it).
RUN apt-get update -qq && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

# /app stays root-owned (the service cannot rewrite its venv); everything the app writes —
# parquet cache, SQLite, reports, numba cache — goes to the /data volume or /tmp.
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/data \
    REPORTS_DIR=/data/reports \
    DATABASE_URL=sqlite:////data/trader.db \
    NUMBA_CACHE_DIR=/tmp/numba

RUN groupadd --gid 1000 app && useradd --uid 1000 --gid 1000 --create-home app \
    && mkdir -p /data && chown 1000:1000 /data
WORKDIR /app
COPY --from=builder --chown=1000:1000 /app/.venv /app/.venv

USER 1000:1000
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

ENTRYPOINT ["uvicorn"]
CMD ["trader.main:app", "--host", "0.0.0.0", "--port", "8000"]
