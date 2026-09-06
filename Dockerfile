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

# One image, two modes, selected by `PORT` (2026-09-05):
#
# - `PORT` set  → HTTP API + Streamable-HTTP MCP via uvicorn. Railway injects
#   `PORT` at runtime and routes/health-checks against it; docker-compose sets
#   `PORT=8080` explicitly (Caddyfile hardcodes `api:8080`).
# - `PORT` unset → the stdio MCP server (`registry-mcp`, the [project.scripts]
#   entry). This is how MCP directory inspectors (Glama and friends) run the
#   image: `docker run -i <image>` with no environment, then speak JSON-RPC on
#   stdin/stdout. The old uvicorn-only CMD failed that introspection.
#
# Shell form (`sh -c`) is required for the `${PORT}` test — exec-form JSON
# arrays don't run through a shell. The healthcheck passes trivially in stdio
# mode, where there is no port to probe.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD [ -z "${PORT:-}" ] || curl -fsS "http://localhost:${PORT}/health" || exit 1

# `--no-access-log` (`DECISIONS.md` D-040(e)): uvicorn's default access log
# writes one line per request, path and all, to this container's stdout —
# duplicating `calls` (our own usage log, D-040) into Railway's log stream
# with an IP address added and none of `loggable_query`'s redaction, for a
# route like `GET /v1/SE/company/<personnummer>` where the identifier is a
# path segment.
CMD ["sh", "-c", "if [ -n \"${PORT:-}\" ]; then exec uvicorn registry_mcp.api.main:app --host 0.0.0.0 --port \"$PORT\" --no-access-log; else exec registry-mcp; fi"]
