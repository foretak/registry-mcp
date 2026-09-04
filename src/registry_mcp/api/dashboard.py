"""`GET /v1/stats/dashboard` — a human-readable usage dashboard (T09).

One URL a human opens each morning: a single self-contained HTML page (inline
CSS/JS only, no external URLs, no CDN) rendered from `core/stats.py::summary()`
plus `core/ua_classify.py::classify()`.

Mounted on the real app via `app.include_router(dashboard_router)` in
`api/main.py`. `include_in_schema=False`, for the same reason `api/stats.py`
is: an admin/debugging page, not part of the versioned public data API.

Auth mirrors `api/stats.py` exactly: `?key=` must equal the
`REGISTRY_MCP_ADMIN_KEY` env var. Missing key, wrong key, or the env var
being unset at all -> 403, in the same `DECISIONS.md` D-007 envelope
(`ErrorCode.BAD_REQUEST` with `http_status=403`, since `ErrorCode` has no
`forbidden` member). The response is built directly in this route rather
than via `install_error_handlers`, so this router works when mounted on an
app that hasn't installed those handlers (e.g. the throwaway `FastAPI()` test
apps `tests/test_dashboard.py` uses).

Every user-supplied string that reaches the page (user agents, queries) is
passed through `html.escape` — `core/stats.py` reads straight from the
`calls` table, so nothing in `top_queries` or `user_agents` should be trusted
as safe markup.
"""

from __future__ import annotations

import os
from html import escape
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from registry_mcp.core import stats as stats_module
from registry_mcp.core.models import ErrorCode, RegistryError
from registry_mcp.core.ua_classify import Label, classify

__all__ = ["dashboard_router"]

_ADMIN_KEY_ENV = "REGISTRY_MCP_ADMIN_KEY"

# Display order + colour for each classifier label (dashboard-only styling;
# `ua_classify.Label` itself carries no colour).
_LABEL_ORDER: list[Label] = ["coding_agent", "browser", "script", "unknown"]
_LABEL_COLOR: dict[Label, str] = {
    "coding_agent": "#6366f1",
    "browser": "#10b981",
    "script": "#f59e0b",
    "unknown": "#94a3b8",
}

dashboard_router = APIRouter()


def _forbidden() -> JSONResponse:
    err = RegistryError(
        ErrorCode.BAD_REQUEST,
        "Missing or incorrect stats key.",
        hint=(
            f"Pass the correct value as ?key= (see the {_ADMIN_KEY_ENV} env var on "
            "the server). This endpoint is not publicly readable."
        ),
        http_status=403,
    )
    return JSONResponse(status_code=err.http_status, content=err.to_dict())


@dashboard_router.get("/v1/stats/dashboard", response_model=None, include_in_schema=False)
def get_dashboard(key: str | None = None) -> HTMLResponse | JSONResponse:
    """Render the usage dashboard when `key` matches; else a 403 envelope."""
    admin_key = os.environ.get(_ADMIN_KEY_ENV, "")
    if not admin_key or key != admin_key:
        return _forbidden()
    data = stats_module.summary()
    return HTMLResponse(content=_render_page(data))


# ---------------------------------------------------------------------------
# Rendering — pure string building, no template engine needed for one page.
# ---------------------------------------------------------------------------


def _render_page(data: dict[str, Any]) -> str:
    calls_per_day: list[dict[str, Any]] = data["calls_per_day"]
    by_surface: dict[str, int] = data["by_surface"]
    top_queries: list[dict[str, Any]] = data["top_queries"]
    user_agents: list[dict[str, Any]] = data["user_agents"]
    total_calls: int = data["total_calls"]
    calls_today: int = data["calls_today"]
    error_rate: float = data["error_rate"]
    distinct_user_agents: int = data["distinct_user_agents"]

    rest_count = by_surface.get("rest", 0)
    mcp_count = by_surface.get("mcp", 0)

    label_rollup: dict[Label, int] = dict.fromkeys(_LABEL_ORDER, 0)
    ua_rows_html = []
    for row in user_agents:
        ua = str(row["user_agent"])
        count = int(row["count"])
        label = classify(ua)
        label_rollup[label] += count
        ua_rows_html.append(
            "<tr>"
            f"<td class='ua'>{escape(ua)}</td>"
            f"<td><span class='pill pill-{escape(label)}'>{escape(label)}</span></td>"
            f"<td class='num'>{count}</td>"
            "</tr>"
        )

    query_rows_html = [
        f"<tr><td class='q'>{escape(str(row['query']))}</td>"
        f"<td class='num'>{int(row['count'])}</td></tr>"
        for row in top_queries
    ]

    rollup_html = "".join(
        f"<div class='rollup-row'>"
        f"<span class='dot' style='background:{_LABEL_COLOR[label]}'></span>"
        f"<span class='rollup-label'>{escape(label)}</span>"
        f"<span class='rollup-count'>{label_rollup[label]}</span>"
        f"</div>"
        for label in _LABEL_ORDER
    )

    chart_svg = _render_bar_chart(calls_per_day)
    surface_bar = _render_surface_split(rest_count, mcp_count)

    error_pct = f"{error_rate * 100:.1f}%"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>registry-mcp — usage dashboard</title>
<style>
  :root {{
    --bg: #f8fafc;
    --card: #ffffff;
    --text: #0f172a;
    --muted: #64748b;
    --border: #e2e8f0;
    --accent: #6366f1;
    --accent-2: #10b981;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #0b1120;
      --card: #131c2e;
      --text: #e2e8f0;
      --muted: #94a3b8;
      --border: #253048;
      --accent: #818cf8;
      --accent-2: #34d399;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 2rem 1.5rem 4rem;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }}
  h1 {{ font-size: 1.4rem; margin: 0 0 0.25rem; }}
  .subtitle {{ color: var(--muted); margin: 0 0 1.5rem; font-size: 0.9rem; }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1rem;
    max-width: 1100px;
    margin: 0 auto 1.5rem;
  }}
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.25rem;
  }}
  .card h2 {{
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin: 0 0 0.5rem;
  }}
  .stat {{ font-size: 1.8rem; font-weight: 600; }}
  .wide {{ max-width: 1100px; margin: 0 auto 1.5rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th, td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 500; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.04em; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.ua {{ word-break: break-all; max-width: 420px; }}
  td.q {{ word-break: break-all; }}
  .table-wrap {{ max-height: 360px; overflow: auto; }}
  .pill {{
    display: inline-block;
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    font-size: 0.72rem;
    color: #fff;
  }}
  .pill-coding_agent {{ background: {_LABEL_COLOR["coding_agent"]}; }}
  .pill-browser {{ background: {_LABEL_COLOR["browser"]}; }}
  .pill-script {{ background: {_LABEL_COLOR["script"]}; }}
  .pill-unknown {{ background: {_LABEL_COLOR["unknown"]}; }}
  .rollup-row {{ display: flex; align-items: center; gap: 0.5rem; padding: 0.2rem 0; font-size: 0.85rem; }}
  .dot {{ width: 0.6rem; height: 0.6rem; border-radius: 50%; flex-shrink: 0; }}
  .rollup-label {{ flex: 1; }}
  .rollup-count {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
  .chart-wrap {{ overflow-x: auto; }}
  svg text {{ fill: var(--muted); font-size: 9px; }}
  .surface-bar {{ display: flex; height: 1.5rem; border-radius: 6px; overflow: hidden; margin-top: 0.5rem; }}
  .surface-legend {{ display: flex; gap: 1.25rem; margin-top: 0.5rem; font-size: 0.8rem; color: var(--muted); }}
  .surface-legend .dot {{ margin-right: 0.35rem; }}
  footer {{ max-width: 1100px; margin: 0 auto; color: var(--muted); font-size: 0.75rem; text-align: center; }}
</style>
</head>
<body>
  <h1>registry-mcp — usage dashboard</h1>
  <p class="subtitle">Aggregated from the local usage log. Refresh this page for current numbers.</p>

  <div class="grid">
    <div class="card"><h2>Total calls</h2><div class="stat">{total_calls}</div></div>
    <div class="card"><h2>Calls today</h2><div class="stat">{calls_today}</div></div>
    <div class="card"><h2>Error rate</h2><div class="stat">{error_pct}</div></div>
    <div class="card"><h2>Distinct user agents</h2><div class="stat">{distinct_user_agents}</div></div>
  </div>

  <div class="wide card">
    <h2>Calls per day — last 30 days</h2>
    <div class="chart-wrap">{chart_svg}</div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>MCP vs REST</h2>
      {surface_bar}
    </div>
    <div class="card">
      <h2>User agents by class</h2>
      {rollup_html}
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>Top 20 queries</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Query</th><th class="num">Count</th></tr></thead>
          <tbody>{"".join(query_rows_html) or "<tr><td colspan='2'>No calls logged yet.</td></tr>"}</tbody>
        </table>
      </div>
    </div>
    <div class="card">
      <h2>Unique user agents</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>User agent</th><th>Class</th><th class="num">Count</th></tr></thead>
          <tbody>{"".join(ua_rows_html) or "<tr><td colspan='3'>No calls logged yet.</td></tr>"}</tbody>
        </table>
      </div>
    </div>
  </div>

  <footer>registry-mcp stats dashboard &middot; generated on each request, no client-side fetching.</footer>
</body>
</html>
"""


def _render_bar_chart(calls_per_day: list[dict[str, Any]]) -> str:
    """A minimal inline SVG bar chart, oldest day left, today right."""
    if not calls_per_day:
        return "<p>No data.</p>"

    counts = [int(d["count"]) for d in calls_per_day]
    max_count = max(counts) or 1

    n = len(calls_per_day)
    bar_w = 18
    gap = 4
    width = n * (bar_w + gap) + gap
    chart_h = 140
    label_h = 24
    height = chart_h + label_h

    bars = []
    for i, day in enumerate(calls_per_day):
        count = int(day["count"])
        day_str = str(day["date"])
        x = gap + i * (bar_w + gap)
        bar_h = round((count / max_count) * (chart_h - 10)) if max_count else 0
        y = chart_h - bar_h
        title = escape(f"{day_str}: {count} calls")
        bars.append(
            f"<g><title>{title}</title>"
            f"<rect x='{x}' y='{y}' width='{bar_w}' height='{max(bar_h, 1)}' "
            f"rx='2' fill='#6366f1'/>"
            + (
                f"<text x='{x + bar_w / 2}' y='{chart_h + 14}' "
                f"text-anchor='middle'>{escape(day_str[5:])}</text>"
                if i % 3 == 0 or i == n - 1
                else ""
            )
            + "</g>"
        )

    return (
        f"<svg width='{width}' height='{height}' viewBox='0 0 {width} {height}' "
        f"role='img' aria-label='Calls per day, last {n} days'>"
        f"{''.join(bars)}"
        f"</svg>"
    )


def _render_surface_split(rest_count: int, mcp_count: int) -> str:
    total = rest_count + mcp_count
    if total == 0:
        rest_pct = mcp_pct = 0.0
    else:
        rest_pct = rest_count / total * 100
        mcp_pct = mcp_count / total * 100

    bar = (
        "<div class='surface-bar'>"
        f"<div style='width:{rest_pct:.2f}%; background:{_LABEL_COLOR['coding_agent']}'></div>"
        f"<div style='width:{mcp_pct:.2f}%; background:{_LABEL_COLOR['browser']}'></div>"
        "</div>"
    )
    legend = (
        "<div class='surface-legend'>"
        f"<span><span class='dot' style='display:inline-block;width:0.6rem;height:0.6rem;"
        f"border-radius:50%;background:{_LABEL_COLOR['coding_agent']}'></span>"
        f"REST: {rest_count}</span>"
        f"<span><span class='dot' style='display:inline-block;width:0.6rem;height:0.6rem;"
        f"border-radius:50%;background:{_LABEL_COLOR['browser']}'></span>"
        f"MCP: {mcp_count}</span>"
        "</div>"
    )
    return bar + legend
