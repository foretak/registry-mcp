# syntax=docker/dockerfile:1

# ---- Builder stage --------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies first, separately from the project, to maximise
# layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

# Now copy the project and install it.
COPY . .
RUN uv sync --locked --no-dev

# ---- Runtime stage ---------------------------------------------------------
FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src /app/src

# `NORBIZ_SPEC.md` §15 requires `GET /`, `/llms.txt`, `/llms-full.txt` and
# `/server.json` to be served from the API origin. `api/main.py`'s
# `_static_dir()`/`_server_json_path()` heuristic falls back to the repo
# root (three parents up from this module, i.e. `/app` in this image) when
# `REGISTRY_MCP_STATIC_DIR` is unset, so copying these to `/app/static` and
# `/app/server.json` would already be enough on its own — the env var below
# is set anyway to make the intent explicit and to keep the routes working
# even if that heuristic ever changes (`REVIEW.md` T04 note).
COPY --from=builder --chown=app:app /app/static /app/static
COPY --from=builder --chown=app:app /app/server.json /app/server.json

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    REGISTRY_MCP_CACHE_PATH=/app/data/cache.sqlite3 \
    REGISTRY_MCP_STATIC_DIR=/app/static

RUN mkdir -p /app/data && chown -R app:app /app/data

USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

CMD ["uvicorn", "registry_mcp.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
