"""Pure query functions over `core/log.py`'s `calls` table (`NORBIZ_SPEC.md` §11, T08).

Nothing here writes to the database or knows about HTTP — `api/stats.py`'s
``GET /v1/stats`` route is a thin wrapper around :func:`summary`, and T09
(whatever surface it builds) can call :func:`summary` directly without going
through the REST API.

Every function returns plain ``dict`` / ``list`` / ``str`` / ``int`` / ``float``
values (no dataclasses, no pydantic models) so the result is JSON-serialisable
as-is, e.g. via ``fastapi.responses.JSONResponse(content=summary())``.

A missing or unreadable database is not an error here: it just means no calls
have been logged yet, so every query function degrades to the same zeroed
result a fresh, empty table would produce.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from registry_mcp.core import log

__all__ = ["summary"]

logger = logging.getLogger(__name__)

_CALLS_PER_DAY_WINDOW = 30
_TOP_QUERIES_LIMIT = 20


def _empty_summary(today: date) -> dict[str, Any]:
    calls_per_day = [
        {"date": (today - timedelta(days=i)).isoformat(), "count": 0}
        for i in range(_CALLS_PER_DAY_WINDOW - 1, -1, -1)
    ]
    return {
        "total_calls": 0,
        "calls_today": 0,
        "calls_per_day": calls_per_day,
        "by_surface": {},
        "top_queries": [],
        "user_agents": [],
        "error_rate": 0.0,
        "distinct_user_agents": 0,
    }


def summary(db_path: str | Path | None = None) -> dict[str, Any]:
    """Aggregate every row in the `calls` table into the `/v1/stats` shape.

    Args:
        db_path: Which SQLite file to read. Defaults to `core/log.py`'s
            `log_path()` (the same file `log_call` writes to, honouring
            `REGISTRY_MCP_LOG_PATH` / `REGISTRY_MCP_CACHE_PATH`).

    Returns:
        A dict with ``total_calls``, ``calls_today``, ``calls_per_day`` (last
        30 days, oldest first, ``{"date", "count"}``), ``by_surface`` (surface
        -> count), ``top_queries`` (top 20 ``{"query", "count"}``, highest
        count first), ``user_agents`` (every distinct user agent seen,
        ``{"user_agent", "count"}``, highest count first), ``error_rate``
        (fraction of calls with ``ok=False``, ``0.0`` when there are no
        calls) and ``distinct_user_agents``.
    """
    today = datetime.now(UTC).date()
    path = Path(db_path) if db_path is not None else log.log_path()

    try:
        conn = log.connect(path)
    except Exception:
        logger.warning("stats: could not open log database at %s", path, exc_info=True)
        return _empty_summary(today)

    try:
        rows = conn.execute(
            "SELECT ts, surface, query, user_agent, ok FROM calls"
        ).fetchall()
    except Exception:
        logger.warning("stats: could not read `calls` table at %s", path, exc_info=True)
        return _empty_summary(today)
    finally:
        conn.close()

    total_calls = len(rows)
    calls_today = 0
    per_day: Counter[str] = Counter()
    by_surface: Counter[str] = Counter()
    by_query: Counter[str] = Counter()
    by_user_agent: Counter[str] = Counter()
    error_count = 0

    for ts, surface, query, user_agent, ok in rows:
        call_date: date | None
        try:
            call_date = datetime.fromisoformat(ts).date()
        except (TypeError, ValueError):
            call_date = None
        if call_date is not None:
            per_day[call_date.isoformat()] += 1
            if call_date == today:
                calls_today += 1
        by_surface[str(surface)] += 1
        if query:
            by_query[str(query)] += 1
        if user_agent:
            by_user_agent[str(user_agent)] += 1
        if not ok:
            error_count += 1

    calls_per_day = [
        {
            "date": (today - timedelta(days=i)).isoformat(),
            "count": per_day.get((today - timedelta(days=i)).isoformat(), 0),
        }
        for i in range(_CALLS_PER_DAY_WINDOW - 1, -1, -1)
    ]

    top_queries = [
        {"query": q, "count": c}
        for q, c in sorted(by_query.items(), key=lambda kv: (-kv[1], kv[0]))[:_TOP_QUERIES_LIMIT]
    ]
    user_agents = [
        {"user_agent": ua, "count": c}
        for ua, c in sorted(by_user_agent.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    return {
        "total_calls": total_calls,
        "calls_today": calls_today,
        "calls_per_day": calls_per_day,
        "by_surface": dict(by_surface),
        "top_queries": top_queries,
        "user_agents": user_agents,
        "error_rate": (error_count / total_calls) if total_calls else 0.0,
        "distinct_user_agents": len(by_user_agent),
    }
