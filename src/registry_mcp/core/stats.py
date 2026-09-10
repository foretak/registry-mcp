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
from registry_mcp.core.models import Surface
from registry_mcp.core.registry import loggable_query
from registry_mcp.core.ua_classify import classify

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

# ---------------------------------------------------------------------------
# T65 — "real asks", not raw calls (`~/mcp-growth/DECISION-GATE.md`, the
# day-45 gate and its 2026-09-10 amendments). The gate's own M1/M2 readings
# (§3.1, §3.2) are computed by hand from the database on 19 October and are
# stricter than what follows (they also filter by `operation`); this block is
# the rough, always-on dashboard preview of the same idea: today's raw
# `total_calls` was 138 and every one of them was a directory scanner, a
# crawler, one of our own smoke tests, or a playground click against the
# examples our own docs show — not evidence anyone asked this service
# anything. The three definitions below are the whole of what "real" means
# here, written once as constants so `summary()` and its tests share exactly
# one copy each.
# ---------------------------------------------------------------------------

#: (1) A query in this set is never a real ask, regardless of surface or user
#: agent — it is the worked example our own README.md, `static/llms-full.txt`
#: and `evals/cases.json` all show, so a call carrying it is far more likely a
#: smoke test, a playground click that copied the docs verbatim, or a scanner
#: replaying the one query every registry-MCP README on the internet
#: demonstrates, than a person or agent with a real question. `833285602`
#: (the operator's own registered company, `legal/privacy.md`) and
#: `833286602` (its deliberate invalid-MOD11 sibling, `NORBIZ_SPEC.md` §"Resolved
#: 2026-09-04") are listed here purely as *strings this module compares
#: against* — this file never looks either one up, per every task's standing
#: rule. Compared case-insensitively (`_is_documented_example`), so "Equinor"
#: and "EQUINOR" cannot dodge the exclusion by capitalisation alone.
_DOCUMENTED_EXAMPLE_QUERIES: frozenset[str] = frozenset(
    {
        "923609016",  # NO — Equinor ASA, the flagship lookup/search/deadlines example
        "00445790",  # GB — Tesco PLC, zero-padded company number
        "445790",  # GB — the same company number, unpadded (the validate example)
        "5560160680",  # SE — the SE lookup/deadlines example
        "equinor",  # NO search_company example query
        "tesco",  # GB search_company example query
        "833285602",  # NO — the operator's own registered company (never looked up here)
        "833286602",  # NO — the invalid-MOD11 example, a typo sibling of the above
        "test",  # generic placeholder query used across docs and the playground
    }
)
_DOCUMENTED_EXAMPLE_QUERIES_CASEFOLDED: frozenset[str] = frozenset(
    query.casefold() for query in _DOCUMENTED_EXAMPLE_QUERIES
)

#: (2, the "our-own" half) Exact user-agent strings known, by name rather than
#: by rule, to never be a real asker. Two frozen sources, neither ever
#: silently extended: `~/mcp-growth/BASELINE-2026-09-07.md`'s "first-party or
#: automated" table — the exact, untruncated entries only; that table's long
#: tail of low-count `Mozilla/5.0 (Windows/Mac/iPhone/Android ...)` rows is
#: truncated in the document itself and not safely reproducible as an exact
#: string here, so it is left to `ua_classify.classify`'s "bot" label and the
#: documented-example-query test to catch what they can — and the bots
#: `~/mcp-growth/DECISION-GATE.md` §8.1/§3.3 name explicitly:
#: `SaSame-MCP-Audit/0.1` (an external MCP audit scanner — it contains "MCP"
#: and would otherwise be misclassified `coding_agent` by `ua_classify.classify`,
#: since that label is checked before `bot`; only an exact name catches it)
#: and the bare `Mozilla/5.0 (compatible)` directory monitor (also caught by
#: the `bot` label independently — kept here too, for the one call site that
#: wants an exact-match answer without importing the classifier).
_OWN_AND_BOT_USER_AGENTS: frozenset[str] = frozenset(
    {
        "curl/8.5.0",
        "python-requests/2.32.5",
        "python-httpx2/2.12.0",
        "Mozilla/5.0 (compatible)",
        "SaSame-MCP-Audit/0.1",
    }
)

#: (2, the "bot/monitor/scanner" half) `classify()` labels that disqualify a
#: user agent from ever being a real asker. Only `"bot"` — `"script"` and
#: `"unknown"` are deliberately left eligible: a real third-party integration
#: calling the REST API with `curl` or `python-requests` looks identical, by
#: label, to our own smoke tests, and only the exact strings in
#: `_OWN_AND_BOT_USER_AGENTS` above tell them apart; `"coding_agent"` is how
#: this product is meant to be used (`api/dashboard.py`'s module docstring
#: makes the same call for the UA-class rollup).
_DISQUALIFYING_UA_LABELS: frozenset[str] = frozenset({"bot"})

#: M4, "ceiling-hitters" (`~/mcp-growth/DECISION-GATE.md` amendment A2,
#: 2026-09-10): "any non-own user agent at or near 60 requests/minute" — the
#: REST rate limit (`api/ratelimit.py::_CAPACITY`) — "routes, it does not
#: gate": it is the one thing that authorises building a metered API key
#: (R-4). Set at 50 rather than 60 itself so the reading fires before a
#: caller starts drawing 429s, not after.
_CEILING_HITTER_CALLS_PER_MINUTE = 50

#: The rolling window `real_asks` reads alongside its all-time counts — short
#: enough to answer "is anyone asking *this week*", long enough that one quiet
#: day does not read as zero.
_REAL_ASKS_RECENT_DAYS = 7

#: Operations that *ask about a company* and so, for a flagged country
#: (Sweden), can have `query=NULL` mean "withheld by D-040", not "nothing was
#: asked" — the orchestrator's fix to this file's first draft. Excludes
#: `_CONNECT_ONLY_OPERATION` (never asks about a company at all) and
#: `"validate_company_id"` (handled on its own in `_is_real_ask`: a NULL
#: query there is excluded everywhere *except* this same Swedish case, so it
#: cannot share this set's blanket "count it" treatment). `search_company` is
#: `not_implemented` for Sweden today (Bolagsverket's free API has no name
#: search, `SWEDEN_SPEC.md`) but is listed anyway per the orchestrator's
#: instruction, in case that ever changes.
_WITHHELD_QUERY_OPERATIONS: frozenset[str] = frozenset(
    {"lookup_company", "company_deadlines", "search_company"}
)

#: The one country D-040 ever nulls a query for today
#: (`registries/se/__init__.py`'s `id_may_be_personal = True`) — spelled out
#: as its own constant rather than repeated as a string literal, since
#: `_is_real_ask` checks it twice for two different reasons.
_QUERY_WITHHELD_COUNTRY = "SE"


def _is_documented_example(query: str) -> bool:
    """(1) — see `_DOCUMENTED_EXAMPLE_QUERIES`'s comment for the definition."""
    return query.strip().casefold() in _DOCUMENTED_EXAMPLE_QUERIES_CASEFOLDED


def _is_own_or_bot_user_agent(user_agent: str | None) -> bool:
    """(2) — true when `user_agent` is a known non-asker, by exact name
    (`_OWN_AND_BOT_USER_AGENTS`) or by `ua_classify.classify`'s own label
    (`_DISQUALIFYING_UA_LABELS`).

    A missing/empty user agent is *not* excluded here: `classify(None)` is
    `"unknown"`, not `"bot"`, and there is no name to match against nothing —
    an anonymous caller is ambiguous, not automated, so this returns `False`
    and leaves the call eligible on its query/surface alone.
    """
    if not user_agent:
        return False
    if user_agent in _OWN_AND_BOT_USER_AGENTS:
        return True
    return classify(user_agent) in _DISQUALIFYING_UA_LABELS


def _is_real_ask(
    surface: str,
    operation: str,
    country: str | None,
    query: str | None,
    user_agent: str | None,
) -> bool:
    """The full "real ask" test for one `calls` row: (1) and (2) combined,
    plus the two operation-shaped refinements below (both from the
    orchestrator's review of this file's first draft).

    In order:

    1. A known non-asker user agent (2) is never a real ask, regardless of
       anything else.
    2. `_CONNECT_ONLY_OPERATION` ("list_countries") is never a real ask, on
       either surface — it is the bare capability probe every client, and
       every scanner, makes on connect, before asking about a company.
    3. A non-NULL query is a real ask exactly when it is not one of our own
       documented examples (1) — the query itself is the strongest signal
       there is, and neither surface nor country changes that.
    4. From here, `query` is NULL. For `"validate_company_id"`: a real ask
       only for the one case NULL there ever means "withheld" rather than
       "excluded" — Sweden (`_QUERY_WITHHELD_COUNTRY`), D-040. Every other
       NULL `validate_company_id` (no country flag in play) is excluded,
       full stop — unlike the other operations below, it never falls back to
       "arrived over MCP", because a validate call always receives an
       identifier argument from its caller, so a NULL query outside the
       Swedish case is unexplained rather than merely unlogged.
    5. For the remaining "asks about a company" operations
       (`_WITHHELD_QUERY_OPERATIONS`): a real ask when the country is Sweden
       (same D-040 reasoning as (4)), or, failing that, when the call arrived
       over the MCP surface at all — the weaker fallback this file shipped
       with, kept for every NULL-query case D-040 does not explain (a D-031
       connector alias before country resolution, for instance).
    """
    if _is_own_or_bot_user_agent(user_agent):
        return False
    if operation == _CONNECT_ONLY_OPERATION:
        return False
    if query is not None:
        return not _is_documented_example(str(query))
    if operation == "validate_company_id":
        return country == _QUERY_WITHHELD_COUNTRY
    if country == _QUERY_WITHHELD_COUNTRY and operation in _WITHHELD_QUERY_OPERATIONS:
        return True
    return surface == Surface.MCP.value


def _empty_real_asks() -> dict[str, Any]:
    """The zeroed `real_asks` block — shared by `_empty_summary` (an
    unreadable/missing database) and nothing else, since `summary()` always
    builds this block fresh from whatever rows it read, never falling back to
    this shape for a non-empty result."""
    return {
        "calls": {"all_time": 0, "last_7_days": 0},
        "distinct_user_agents": {"all_time": 0, "last_7_days": 0},
        "mcp_sessions_non_bot": 0,
        "by_source_named": [],
        "last": None,
        "ceiling_hitters": [],
    }


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
        "real_asks": _empty_real_asks(),
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

        T65 adds ``real_asks`` — the same rows, restricted to what
        ``~/mcp-growth/DECISION-GATE.md``'s day-45 gate counts rather than
        every logged call (see ``_is_real_ask`` for the exact test): ``calls``
        and ``distinct_user_agents`` (each ``{"all_time", "last_7_days"}``),
        ``mcp_sessions_non_bot`` (distinct non-bot/own user agents seen on the
        MCP surface in the last 7 days), ``by_source_named`` (``by_source``
        above, minus the ``NO_SOURCE_KEY`` bucket — channel attribution rarely
        applies to a bot anyway), ``last`` (``{"ts", "operation", "country",
        "query"}`` for the single most recent real ask, all time; ``query``
        is re-redacted through ``core.registry.loggable_query`` here as a
        second line of defence, never trusting that every historical row was
        already redacted at write time; ``None`` when there has never been
        one), and ``ceiling_hitters`` (the M4 reading, amendment A2: user
        agents that made at least ``_CEILING_HITTER_CALLS_PER_MINUTE`` calls
        within any single minute in the last 7 days, ``{"user_agent",
        "calls_in_minute"}``, highest first).
    """
    now_dt = datetime.now(UTC)
    today = now_dt.date()
    recent_cutoff = now_dt - timedelta(days=_REAL_ASKS_RECENT_DAYS)
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

    # T65 — "real asks" accumulators (`_is_real_ask`).
    real_ask_calls_all_time = 0
    real_ask_calls_recent = 0
    real_ask_uas_all_time: set[str] = set()
    real_ask_uas_recent: set[str] = set()
    mcp_non_bot_uas_recent: set[str] = set()
    per_minute_calls: Counter[tuple[str, str]] = Counter()
    last_real_ask_dt: datetime | None = None
    last_real_ask_operation: str | None = None
    last_real_ask_country: str | None = None
    last_real_ask_query: str | None = None

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

        # T65 — "real asks". Computed regardless of whether `ts` parsed (an
        # all-time real-ask count needs no date, exactly like `total_calls`
        # above), except the pieces that are inherently date-scoped: the
        # "last 7 days" counters, `last`, and the per-minute ceiling check
        # all require a valid `call_dt`.
        surface_str = str(surface)
        operation_str = str(operation)
        country_str = str(country) if country else None
        user_agent_str = str(user_agent) if user_agent else None
        if _is_real_ask(surface_str, operation_str, country_str, query, user_agent_str):
            real_ask_calls_all_time += 1
            if user_agent_str:
                real_ask_uas_all_time.add(user_agent_str)
            if call_dt is not None:
                if last_real_ask_dt is None or call_dt > last_real_ask_dt:
                    last_real_ask_dt = call_dt
                    last_real_ask_operation = operation_str
                    last_real_ask_country = country_str
                    last_real_ask_query = str(query) if query else None
                if call_dt >= recent_cutoff:
                    real_ask_calls_recent += 1
                    if user_agent_str:
                        real_ask_uas_recent.add(user_agent_str)
        if (
            call_dt is not None
            and call_dt >= recent_cutoff
            and surface_str == Surface.MCP.value
            and user_agent_str
            and not _is_own_or_bot_user_agent(user_agent_str)
        ):
            mcp_non_bot_uas_recent.add(user_agent_str)
        if (
            call_dt is not None
            and call_dt >= recent_cutoff
            and user_agent_str
            and not _is_own_or_bot_user_agent(user_agent_str)
        ):
            per_minute_calls[(user_agent_str, call_dt.strftime("%Y-%m-%dT%H:%M"))] += 1

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

    # T65 — "real asks" derived shapes.
    by_source_named = [row for row in by_source_list if row["source"] != NO_SOURCE_KEY]

    max_calls_per_minute: dict[str, int] = {}
    for (ua, _minute), count in per_minute_calls.items():
        if count > max_calls_per_minute.get(ua, 0):
            max_calls_per_minute[ua] = count
    ceiling_hitters = [
        {"user_agent": ua, "calls_in_minute": count}
        for ua, count in sorted(max_calls_per_minute.items(), key=lambda kv: (-kv[1], kv[0]))
        if count >= _CEILING_HITTER_CALLS_PER_MINUTE
    ]

    real_asks_last = (
        {
            "ts": last_real_ask_dt.isoformat(),
            "operation": last_real_ask_operation,
            "country": last_real_ask_country,
            "query": loggable_query(last_real_ask_country, last_real_ask_query),
        }
        if last_real_ask_dt is not None
        else None
    )

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
        "real_asks": {
            "calls": {
                "all_time": real_ask_calls_all_time,
                "last_7_days": real_ask_calls_recent,
            },
            "distinct_user_agents": {
                "all_time": len(real_ask_uas_all_time),
                "last_7_days": len(real_ask_uas_recent),
            },
            "mcp_sessions_non_bot": len(mcp_non_bot_uas_recent),
            "by_source_named": by_source_named,
            "last": real_asks_last,
            "ceiling_hitters": ceiling_hitters,
        },
    }
