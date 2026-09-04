"""`GET /status` — a tiny public status page (T13, `tasks/T13.md`).

Unlike `api/stats.py` / `api/dashboard.py` this route is **public, by
design**: it carries no secrets and no per-query data (no user agents, no
queries, no IPs), only aggregate facts an operator or an uptime monitor would
want at a glance:

* the running version and process uptime,
* which countries are currently supported (`core.registry.list_countries`),
* whether the upstream brreg API answered a cheap request recently, and when
  that check last ran — the check itself is a single `GET` to the brreg base
  URL with a short timeout, cached for `_UPSTREAM_CACHE_SECONDS` so this page
  never causes more than one upstream request a minute no matter how many
  times a human or a monitor refreshes it,
* the number of rows currently held in the local SQLite cache (`core/cache.py`),
  read directly from the file in read-only mode — this route never imports or
  calls into any registry module, so it stays honest even if every country
  module were broken.

Mounted on the real app via `app.include_router(status_router)` in
`api/main.py`. `include_in_schema=False`: like `/health`, this is an
operational page, not part of the versioned public data API `/openapi.json`
describes.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from html import escape

import httpx
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from registry_mcp import __version__
from registry_mcp.core.cache import cache_path
from registry_mcp.core.registry import list_countries
from registry_mcp.registries.no.client import BASE_URL as _BRREG_BASE_URL

__all__ = ["status_router"]

status_router = APIRouter()

_PROCESS_STARTED_AT = time.monotonic()

_UPSTREAM_CACHE_SECONDS = 60.0
_UPSTREAM_TIMEOUT_SECONDS = 3.0


@dataclass
class _UpstreamState:
    reachable: bool | None = None
    checked_at: float | None = None  # time.monotonic() of the last real check


_upstream_state = _UpstreamState()


def _format_uptime(seconds: float) -> str:
    total = int(seconds)
    days, rem = divmod(total, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def _seconds_ago(monotonic_time: float) -> float:
    return max(time.monotonic() - monotonic_time, 0.0)


async def _upstream_reachable() -> _UpstreamState:
    """Cheap, cached check that brreg is reachable. Never raises.

    A real HTTP request is made at most once per `_UPSTREAM_CACHE_SECONDS`;
    every call within that window returns the cached result. Failure of any
    kind (timeout, DNS, connection refused, non-2xx) is recorded as
    unreachable — this is a liveness signal, not a diagnostic.
    """
    now = time.monotonic()
    if _upstream_state.checked_at is not None and (now - _upstream_state.checked_at) < _UPSTREAM_CACHE_SECONDS:
        return _upstream_state

    reachable: bool
    try:
        async with httpx.AsyncClient(timeout=_UPSTREAM_TIMEOUT_SECONDS) as client:
            response = await client.get(_BRREG_BASE_URL)
        reachable = response.status_code < 500
    except Exception:
        reachable = False

    _upstream_state.reachable = reachable
    _upstream_state.checked_at = now
    return _upstream_state


def _cache_row_count() -> int | None:
    """Row count of the local SQLite cache, read-only. `None` if unavailable.

    Opened with `mode=ro` so this route can never create, lock for writing,
    or corrupt the cache file it is only reporting on; a missing file or any
    read error is treated as "unknown" rather than raised.
    """
    path = cache_path()
    if not path.is_file():
        return None
    try:
        uri = f"file:{path}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=2.0) as conn:
            row = conn.execute("SELECT COUNT(*) FROM cache").fetchone()
        return int(row[0]) if row is not None else None
    except Exception:
        return None


def _render_page(
    *,
    version: str,
    uptime_seconds: float,
    countries: list[str],
    upstream: _UpstreamState,
    cache_rows: int | None,
) -> str:
    uptime_str = escape(_format_uptime(uptime_seconds))
    countries_str = escape(", ".join(countries) or "none")
    cache_rows_str = escape(str(cache_rows)) if cache_rows is not None else "unknown"

    if upstream.reachable is None:
        upstream_label, upstream_class, checked_str = "unknown", "warn", "never"
    else:
        upstream_label = "reachable" if upstream.reachable else "unreachable"
        upstream_class = "ok" if upstream.reachable else "bad"
        checked_str = (
            f"{_format_uptime(_seconds_ago(upstream.checked_at))} ago"
            if upstream.checked_at is not None
            else "never"
        )
    checked_str = escape(checked_str)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>registry-mcp — status</title>
<style>
  :root {{
    --bg: #f8fafc;
    --card: #ffffff;
    --text: #0f172a;
    --muted: #64748b;
    --border: #e2e8f0;
    --ok: #10b981;
    --bad: #ef4444;
    --warn: #f59e0b;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0b1120;
      --card: #131c2e;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --border: #253048;
      --ok: #34d399;
      --bad: #f87171;
      --warn: #fbbf24;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 2.5rem 1.5rem;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  main {{ max-width: 640px; margin: 0 auto; }}
  h1 {{ font-size: 1.3rem; margin: 0 0 1.5rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; }}
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.25rem;
  }}
  .card h2 {{
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin: 0 0 0.4rem;
  }}
  .stat {{ font-size: 1.3rem; font-weight: 600; }}
  .dot {{ display: inline-block; width: 0.55rem; height: 0.55rem; border-radius: 50%; margin-right: 0.4rem; }}
  .dot-ok {{ background: var(--ok); }}
  .dot-bad {{ background: var(--bad); }}
  .dot-warn {{ background: var(--warn); }}
  footer {{ margin-top: 1.5rem; color: var(--muted); font-size: 0.78rem; }}
</style>
</head>
<body>
  <main>
    <h1>registry-mcp status</h1>
    <div class="grid">
      <div class="card"><h2>Version</h2><div class="stat">{escape(version)}</div></div>
      <div class="card"><h2>Uptime</h2><div class="stat">{uptime_str}</div></div>
      <div class="card"><h2>Countries</h2><div class="stat">{countries_str}</div></div>
      <div class="card">
        <h2>Upstream (brreg)</h2>
        <div class="stat"><span class="dot dot-{upstream_class}"></span>{upstream_label}</div>
      </div>
      <div class="card"><h2>Last upstream check</h2><div class="stat">{checked_str}</div></div>
      <div class="card"><h2>Cache rows</h2><div class="stat">{cache_rows_str}</div></div>
    </div>
    <footer>No per-query data or secrets are shown on this page. Generated on each request.</footer>
  </main>
</body>
</html>
"""


@status_router.get("/status", response_class=HTMLResponse, include_in_schema=False)
async def get_status() -> HTMLResponse:
    upstream = await _upstream_reachable()
    return HTMLResponse(
        content=_render_page(
            version=__version__,
            uptime_seconds=time.monotonic() - _PROCESS_STARTED_AT,
            countries=list_countries(),
            upstream=upstream,
            cache_rows=_cache_row_count(),
        )
    )
