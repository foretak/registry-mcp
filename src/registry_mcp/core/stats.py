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
from math import ceil
from pathlib import Path
from typing import Any

from registry_mcp.core import log

__all__ = ["NO_COUNTRY_KEY", "NO_SOURCE_KEY", "summary"]

logger = logging.getLogger(__name__)

_CALLS_PER_DAY_WINDOW = 30
_TOP_QUERIES_LIMIT = 20

#: `by_country` key for rows where `calls.country` is `NULL` (or, defensively,
#: `''`) — `list_countries`, the two D-031 connector aliases before a country
#: is derived, and any error raised before resolution all log `country` this
#: way. Every real country code is exactly two upper-case letters
#: (`core/registry.py::register` enforces `len(country) == 2 and
#: country.isalpha()`), so a four-character lower-case key can never collide
#: with one. Not a redaction: D-040 empties `query` for a flagged country
#: (Sweden) but never touches `country`, so this bucket never hides a country
#: that *was* resolved — it only ever means no single country applies to the
#: call. `api/dashboard.py` (T36) imports this to render an honest label
#: instead of a fake country code.
NO_COUNTRY_KEY = "none"

#: `by_source` key for rows where `calls.source` is `NULL` (or, defensively,
#: `''`) — every call made with no `?src=` on it at all, which is the great
#: majority of history: the column is new (T64) and optional, and most
#: callers were never given one of our tagged install lines to begin with.
#: Shown rather than dropped for the same reason `NO_COUNTRY_KEY` is: silently
#: excluding these rows would make `sum(row.count for row in by_source)` land
#: short of `total_calls` with nothing on the dashboard explaining why, and
#: "how much of our traffic is attributed at all" is itself the number this
#: bucket answers. A real `source` value can only ever be lower-case
#: `[a-z0-9_-]` (`core/log.py::sanitize_source`), so this four-character
#: lower-case-plus-nothing-unusual key cannot collide with one in practice,
#: and even if a caller's tag happened to be the literal text "none", the two
#: are simply indistinguishable the same way an untagged call and a call
#: tagged "none" would be indistinguishable to a human reading the word on
#: the dashboard regardless of which column produced it.
NO_SOURCE_KEY = "none"

#: Operation value logged for a bare capability probe — what an MCP client
#: calls on connect, before it has asked about any company (`api/main.py`'s
#: `GET /v1/countries` route and `mcp/server.py`'s `list_countries` tool are
#: the only two call sites, both passing `country=None`, `query=None`).
#: Unlike `NO_COUNTRY_KEY`, this is not a bucket key — it is excluded only
#: from `last_non_connect_call_at` / `days_since_last_non_connect_call` below
#: and still counts everywhere else (`total_calls`, `by_operation`,
#: `calls_per_day`, `last_call_at`, ...). The reason for the second pair: a
#: deployment can look freshly used by `last_call_at` alone purely from
#: clients reconnecting, which is a different diagnosis from someone asking
#: it something, and is exactly the gap `by_operation` (below) exists to
#: reveal in the aggregate and this pair exists to reveal in time.
_CONNECT_ONLY_OPERATION = "list_countries"


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
        "by_country": [],
        "by_operation": [],
        "by_source": [],
        "top_queries": [],
        "user_agents": [],
        "error_rate": 0.0,
        "distinct_user_agents": 0,
        "cache_hits": 0,
        "cacheable_calls": 0,
        "cache_hit_rate": 0.0,
        "latency_ms_avg": 0.0,
        "latency_ms_p50": 0,
        "latency_ms_p95": 0,
        "last_call_at": None,
        "days_since_last_call": None,
        "last_non_connect_call_at": None,
        "days_since_last_non_connect_call": None,
    }


def _percentile(sorted_values: list[int], pct: int) -> int:
    """Nearest-rank `pct`th percentile of a non-empty, ascending-sorted list.

    Nearest-rank rather than interpolated: simple, dependency-free, and
    adequate for a morning dashboard read rather than a latency SLO report.
    `pct` is in `[1, 100]`; the one call site (`summary()`) only reaches this
    when `latencies` is non-empty.
    """
    rank = ceil(pct / 100 * len(sorted_values))
    index = min(max(rank, 1), len(sorted_values)) - 1
    return sorted_values[index]


def summary(db_path: str | Path | None = None) -> dict[str, Any]:
    """Aggregate every row in the `calls` table into the `/v1/stats` shape.

    Args:
        db_path: Which SQLite file to read. Defaults to `core/log.py`'s
            `log_path()` (the same file `log_call` writes to, honouring
            `REGISTRY_MCP_LOG_PATH` / `REGISTRY_MCP_CACHE_PATH`).

    Returns:
        A dict with ``total_calls``, ``calls_today``, ``calls_per_day`` (last
        30 days, oldest first, ``{"date", "count"}``), ``by_surface`` (surface
        -> count), ``by_country`` (every distinct country seen, highest count
        first then country code ascending, ``{"country", "count"}`` —
        ``country`` is the ISO-3166-1 alpha-2 code as stored, or
        ``NO_COUNTRY_KEY`` for rows with no resolved country), ``by_operation``
        (every distinct operation seen — ``lookup_company``, ``search_company``,
        ``company_deadlines``, ``validate_company_id``, ``list_countries``, or
        the D-031 connector aliases ``search``/``fetch`` — same shape and
        ordering as ``by_country``, ``{"operation", "count"}``; ``operation``
        is ``NOT NULL`` in the schema so, unlike ``by_country``, there is no
        "none" bucket), ``by_source`` (T64 — every distinct ``?src=`` tag
        seen on our own published install lines, same shape and ordering as
        ``by_country``, ``{"source", "count"}``; ``source`` is nullable, so a
        call with none is bucketed under ``NO_SOURCE_KEY`` exactly as an
        unresolved ``country`` is, never dropped), ``top_queries`` (top 20 ``{"query", "count"}``,
        highest count first), ``user_agents`` (every distinct user agent
        seen, ``{"user_agent", "count"}``, highest count first), ``error_rate``
        (fraction of calls with ``ok=False``, ``0.0`` when there are no
        calls), ``distinct_user_agents``, ``cache_hits`` / ``cacheable_calls``
        / ``cache_hit_rate`` (``calls.cached`` is only ever non-``NULL`` for a
        successful ``lookup_company``/``search_company`` call — every other
        operation, and any failed call, has no cache verdict to report, so
        the rate is of *cacheable* calls seen, not of ``total_calls``; ``0.0``
        when ``cacheable_calls`` is ``0``), ``latency_ms_avg`` /
        ``latency_ms_p50`` / ``latency_ms_p95`` (nearest-rank, over every
        call's ``latency_ms``; ``0``/``0.0`` when there are no calls), and
        ``last_call_at`` / ``days_since_last_call`` (the most recent ``ts``,
        and the whole-day gap between it and today; ``None`` when there are
        no calls, or when no ``ts`` parses) alongside
        ``last_non_connect_call_at`` / ``days_since_last_non_connect_call``,
        the same pair computed only over calls whose ``operation`` is not
        ``"list_countries"`` (see ``_CONNECT_ONLY_OPERATION``) — a deployment
        can look freshly used by ``last_call_at`` alone purely from clients
        reconnecting, which this second pair exists to catch.
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
            "SELECT ts, surface, operation, country, query, user_agent, "
            "latency_ms, ok, cached, source FROM calls"
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
    by_country: Counter[str] = Counter()
    by_operation: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    by_query: Counter[str] = Counter()
    by_user_agent: Counter[str] = Counter()
    error_count = 0
    cache_hits = 0
    cacheable_calls = 0
    latencies: list[int] = []
    last_call_dt: datetime | None = None
    last_non_connect_call_dt: datetime | None = None

    for (
        ts,
        surface,
        operation,
        country,
        query,
        user_agent,
        latency_ms,
        ok,
        cached,
        source,
    ) in rows:
        call_dt: datetime | None
        try:
            call_dt = datetime.fromisoformat(ts)
        except (TypeError, ValueError):
            call_dt = None
        if call_dt is not None:
            call_date = call_dt.date()
            per_day[call_date.isoformat()] += 1
            if call_date == today:
                calls_today += 1
            if last_call_dt is None or call_dt > last_call_dt:
                last_call_dt = call_dt
            if str(operation) != _CONNECT_ONLY_OPERATION and (
                last_non_connect_call_dt is None or call_dt > last_non_connect_call_dt
            ):
                last_non_connect_call_dt = call_dt
        by_surface[str(surface)] += 1
        by_operation[str(operation)] += 1
        by_country[str(country) if country else NO_COUNTRY_KEY] += 1
        by_source[str(source) if source else NO_SOURCE_KEY] += 1
        if query:
            by_query[str(query)] += 1
        if user_agent:
            by_user_agent[str(user_agent)] += 1
        if not ok:
            error_count += 1
        latencies.append(int(latency_ms))
        if cached is not None:
            cacheable_calls += 1
            if cached:
                cache_hits += 1

    calls_per_day = [
        {
            "date": (today - timedelta(days=i)).isoformat(),
            "count": per_day.get((today - timedelta(days=i)).isoformat(), 0),
        }
        for i in range(_CALLS_PER_DAY_WINDOW - 1, -1, -1)
    ]

    by_country_list = [
        {"country": c, "count": n}
        for c, n in sorted(by_country.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    by_operation_list = [
        {"operation": op, "count": n}
        for op, n in sorted(by_operation.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    by_source_list = [
        {"source": s, "count": n}
        for s, n in sorted(by_source.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    top_queries = [
        {"query": q, "count": c}
        for q, c in sorted(by_query.items(), key=lambda kv: (-kv[1], kv[0]))[:_TOP_QUERIES_LIMIT]
    ]
    user_agents = [
        {"user_agent": ua, "count": c}
        for ua, c in sorted(by_user_agent.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    latencies.sort()
    if latencies:
        latency_ms_avg = round(sum(latencies) / len(latencies), 1)
        latency_ms_p50 = _percentile(latencies, 50)
        latency_ms_p95 = _percentile(latencies, 95)
    else:
        latency_ms_avg = 0.0
        latency_ms_p50 = 0
        latency_ms_p95 = 0

    return {
        "total_calls": total_calls,
        "calls_today": calls_today,
        "calls_per_day": calls_per_day,
        "by_surface": dict(by_surface),
        "by_country": by_country_list,
        "by_operation": by_operation_list,
        "by_source": by_source_list,
        "top_queries": top_queries,
        "user_agents": user_agents,
        "error_rate": (error_count / total_calls) if total_calls else 0.0,
        "distinct_user_agents": len(by_user_agent),
        "cache_hits": cache_hits,
        "cacheable_calls": cacheable_calls,
        "cache_hit_rate": (cache_hits / cacheable_calls) if cacheable_calls else 0.0,
        "latency_ms_avg": latency_ms_avg,
        "latency_ms_p50": latency_ms_p50,
        "latency_ms_p95": latency_ms_p95,
        "last_call_at": last_call_dt.isoformat() if last_call_dt is not None else None,
        "days_since_last_call": (
            (today - last_call_dt.date()).days if last_call_dt is not None else None
        ),
        "last_non_connect_call_at": (
            last_non_connect_call_dt.isoformat()
            if last_non_connect_call_dt is not None
            else None
        ),
        "days_since_last_non_connect_call": (
            (today - last_non_connect_call_dt.date()).days
            if last_non_connect_call_dt is not None
            else None
        ),
    }
