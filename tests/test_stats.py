"""Tests for `core/stats.py` and `api/stats.py` (`NORBIZ_SPEC.md` §11, T08).

`core/stats.py` tests log ten calls straight into a temp SQLite file (via
`core/log.py::log_call`, so the two modules are tested together the way they
are actually used) and check the aggregation. `api/stats.py` tests mount
`stats_router` on a throwaway `FastAPI()` app — never `registry_mcp.api.main:app`,
per this task's instructions, since another agent is mid-edit on that file.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from registry_mcp.api.stats import stats_router
from registry_mcp.core import log, stats
from registry_mcp.core.models import Surface
from registry_mcp.core.ua_classify import classify


@pytest.fixture(autouse=True)
def _reset_sink() -> Iterator[None]:
    yield
    log.set_sink(None)


def _seed_ten_calls(db: Path) -> None:
    log.set_sink(db)
    # 6 REST, 4 MCP; 3 distinct queries with a clear count ordering; 2
    # distinct user agents; 2 failures for a 0.2 error rate.
    calls = [
        # (surface, operation, country, query, user_agent, ok, error_code)
        (Surface.REST, "lookup_company", "NO", "923609016", "curl/8.0", True, None),
        (Surface.REST, "lookup_company", "NO", "923609016", "curl/8.0", True, None),
        (Surface.REST, "lookup_company", "NO", "923609016", "some-agent/1.0", True, None),
        (Surface.REST, "lookup_company", "NO", "923609016", "some-agent/1.0", True, None),
        (Surface.REST, "lookup_company", "NO", "923609016", "curl/8.0", True, None),
        (Surface.REST, "search_company", "NO", "equinor", "curl/8.0", False, "not_found"),
        (Surface.MCP, "lookup_company", "NO", "923609016", "stdio", True, None),
        (Surface.MCP, "search_company", "NO", "equinor", "stdio", True, None),
        (Surface.MCP, "search_company", "NO", "equinor", "stdio", True, None),
        (Surface.MCP, "validate_company_id", "NO", "000000000", "stdio", False, "invalid_id"),
    ]
    for surface, operation, country, query, user_agent, ok, error_code in calls:
        log.log_call(
            surface=surface,
            operation=operation,
            country=country,
            query=query,
            user_agent=user_agent,
            latency_ms=10,
            ok=ok,
            error_code=error_code,
        )


def _insert_historical_call(
    db: Path,
    *,
    ts: str,
    surface: Surface,
    operation: str,
    country: str | None,
    query: str | None,
    user_agent: str | None,
    latency_ms: int,
    ok: bool,
    cached: bool | None = None,
) -> None:
    """Write one `calls` row with an explicit `ts`, bypassing `log_call`'s own
    `datetime.now(UTC)` stamp.

    The only way to test day-based arithmetic (`days_since_last_call` and
    friends) deterministically: this project has no time-mocking dependency,
    and `log_call`'s signature has no `ts` parameter (by design — a caller
    should never be able to backdate its own usage line). Schema comes from
    `log.connect`, the same function `log_call`/`summary` both use, so the
    columns here can never drift out of sync with production.
    """
    conn = log.connect(db)
    try:
        conn.execute(
            "INSERT INTO calls "
            "(ts, surface, operation, country, query, user_agent, latency_ms, ok, cached) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                surface.value,
                operation,
                country,
                query,
                user_agent,
                latency_ms,
                int(ok),
                None if cached is None else int(cached),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_summary_on_empty_database_is_zeroed(tmp_path: Path) -> None:
    result = stats.summary(tmp_path / "empty.sqlite3")
    assert result["total_calls"] == 0
    assert result["calls_today"] == 0
    assert len(result["calls_per_day"]) == 30
    assert all(day["count"] == 0 for day in result["calls_per_day"])
    assert result["by_surface"] == {}
    assert result["by_country"] == []
    assert result["by_operation"] == []
    assert result["by_source"] == []
    assert result["top_queries"] == []
    assert result["user_agents"] == []
    assert result["error_rate"] == 0.0
    assert result["distinct_user_agents"] == 0
    assert result["cache_hits"] == 0
    assert result["cacheable_calls"] == 0
    assert result["cache_hit_rate"] == 0.0
    assert result["latency_ms_avg"] == 0.0
    assert result["latency_ms_p50"] == 0
    assert result["latency_ms_p95"] == 0
    assert result["last_call_at"] is None
    assert result["days_since_last_call"] is None
    assert result["last_non_connect_call_at"] is None
    assert result["days_since_last_non_connect_call"] is None
    assert result["real_asks"] == {
        "calls": {"all_time": 0, "last_7_days": 0},
        "distinct_user_agents": {"all_time": 0, "last_7_days": 0},
        "mcp_sessions_non_bot": 0,
        "by_source_named": [],
        "last": None,
        "ceiling_hitters": [],
        "playground": {"calls_last_7_days": 0, "distinct_user_agents_last_7_days": 0},
        "crawler_burst_minutes": 0,
    }


def test_summary_aggregates_ten_calls(tmp_path: Path) -> None:
    db = tmp_path / "calls.sqlite3"
    _seed_ten_calls(db)

    result = stats.summary(db)

    assert result["total_calls"] == 10
    assert result["calls_today"] == 10
    assert result["by_surface"] == {"rest": 6, "mcp": 4}
    assert result["distinct_user_agents"] == 3
    assert result["error_rate"] == pytest.approx(0.2)

    # top_queries: "923609016" appears 6x, "equinor" 3x, "000000000" 1x —
    # ordering must reflect descending count.
    assert result["top_queries"] == [
        {"query": "923609016", "count": 6},
        {"query": "equinor", "count": 3},
        {"query": "000000000", "count": 1},
    ]

    user_agents = {row["user_agent"]: row["count"] for row in result["user_agents"]}
    assert user_agents == {"curl/8.0": 4, "some-agent/1.0": 2, "stdio": 4}

    assert len(result["calls_per_day"]) == 30
    today_entry = result["calls_per_day"][-1]
    assert today_entry["count"] == 10


def test_summary_top_queries_capped_at_twenty(tmp_path: Path) -> None:
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    for i in range(25):
        log.log_call(
            surface=Surface.REST,
            operation="lookup_company",
            country="NO",
            query=f"query-{i}",
            user_agent="agent/1.0",
            latency_ms=1,
            ok=True,
        )
    result = stats.summary(db)
    assert result["total_calls"] == 25
    assert len(result["top_queries"]) == 20


def test_summary_null_query_counts_everywhere_but_top_queries(tmp_path: Path) -> None:
    """D-040: a flagged country (Sweden) logs `query=NULL` (`core.registry.loggable_query`'s
    redaction). That row must still count toward `total_calls`, `calls_today`, `by_surface`
    and `error_rate` — every aggregate here except `top_queries`, which already skips a
    falsy query (`core/stats.py`'s ``if query:`` guard, D-040(c)) and must keep doing so for
    `None` exactly as it already does for `""`."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="SE",
        query=None,
        user_agent="agent/1.0",
        latency_ms=5,
        ok=False,
        error_code="upstream_error",
    )
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="agent/1.0",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["total_calls"] == 2
    assert result["calls_today"] == 2
    assert result["by_surface"] == {"rest": 2}
    assert result["error_rate"] == pytest.approx(0.5)
    assert result["top_queries"] == [{"query": "923609016", "count": 1}]

    # D-040 empties `query`, never `country` — the SE row's country is still
    # "SE", not `stats.NO_COUNTRY_KEY`. Tied at 1 each, so alphabetical order.
    assert result["by_country"] == [
        {"country": "NO", "count": 1},
        {"country": "SE", "count": 1},
    ]


def test_summary_by_country_counts_and_orders_with_null_bucket(tmp_path: Path) -> None:
    """`by_country`: highest count first, then country code ascending as a
    tiebreak (GB and NO tie at 3 calls each below). A `country=NULL` row —
    `list_countries`, a D-031 connector alias before the country is derived,
    or an error raised before resolution (`api/dashboard.py`'s T36 module
    docstring) — lands under `stats.NO_COUNTRY_KEY` ("none"), sorted by its
    count like any other bucket, never dropped and never merged into a real
    country's count."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    calls: list[tuple[str | None, str | None]] = [
        ("GB", "00445790"),
        ("GB", "00445790"),
        ("GB", "00445790"),
        ("NO", "923609016"),
        ("NO", "923609016"),
        ("NO", "923609016"),
        ("SE", "5560160680"),
        (None, None),
        (None, None),
    ]
    for country, query in calls:
        log.log_call(
            surface=Surface.REST,
            operation="lookup_company",
            country=country,
            query=query,
            user_agent="agent/1.0",
            latency_ms=1,
            ok=True,
        )

    result = stats.summary(db)

    assert result["total_calls"] == 9
    assert result["by_country"] == [
        {"country": "GB", "count": 3},
        {"country": "NO", "count": 3},
        {"country": stats.NO_COUNTRY_KEY, "count": 2},
        {"country": "SE", "count": 1},
    ]


def test_summary_by_source_counts_and_orders_with_null_bucket(tmp_path: Path) -> None:
    """`by_source`: highest count first, then source tag ascending as a
    tiebreak ("llms" and "readme" tie at 3 calls each below — "l" < "r") —
    same shape and sort as `by_country`
    (`test_summary_by_country_counts_and_orders_with_null_bucket`). A call
    with no `?src=` at all lands under `stats.NO_SOURCE_KEY` ("none"), sorted
    by its count like any other bucket, never dropped and never merged into a
    real tag's count."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    sources: list[str | None] = [
        "readme",
        "readme",
        "readme",
        "llms",
        "llms",
        "llms",
        "docs",
        None,
        None,
    ]
    for source in sources:
        log.log_call(
            surface=Surface.REST,
            operation="lookup_company",
            country="NO",
            query="923609016",
            user_agent="agent/1.0",
            latency_ms=1,
            ok=True,
            source=source,
        )

    result = stats.summary(db)

    assert result["total_calls"] == 9
    assert result["by_source"] == [
        {"source": "llms", "count": 3},
        {"source": "readme", "count": 3},
        {"source": stats.NO_SOURCE_KEY, "count": 2},
        {"source": "docs", "count": 1},
    ]


def test_summary_by_operation_counts_and_orders(tmp_path: Path) -> None:
    """`by_operation`: highest count first, then operation name ascending as
    a tiebreak (`company_deadlines`, `list_countries` and
    `validate_company_id` tie at 2 calls each below — "c" < "l" < "v").
    Unlike `by_country` there is no "none"/unresolved bucket: `operation` is
    `NOT NULL` in the schema, so every row contributes to a real key."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    operations = (
        ["lookup_company"] * 5
        + ["search_company"] * 3
        + ["list_countries"] * 2
        + ["validate_company_id"] * 2
        + ["company_deadlines"] * 2
    )
    for operation in operations:
        log.log_call(
            surface=Surface.REST,
            operation=operation,
            country=None if operation == "list_countries" else "NO",
            query=None if operation == "list_countries" else "923609016",
            user_agent="agent/1.0",
            latency_ms=1,
            ok=True,
        )

    result = stats.summary(db)

    assert result["total_calls"] == 14
    assert result["by_operation"] == [
        {"operation": "lookup_company", "count": 5},
        {"operation": "search_company", "count": 3},
        {"operation": "company_deadlines", "count": 2},
        {"operation": "list_countries", "count": 2},
        {"operation": "validate_company_id", "count": 2},
    ]


def test_summary_cache_hit_rate_counts_only_cacheable_calls(tmp_path: Path) -> None:
    """`cached` is `NULL` for every operation except a successful
    `lookup_company`/`search_company` (`api/main.py`'s `_record` call sites
    only pass it on that path) — `company_deadlines`, `validate_company_id`
    and `list_countries` never set it, and neither does a failed lookup. The
    rate must be of *cacheable* calls seen, not of `total_calls`."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    for cached in (True, True, False):  # 2 hits, 1 miss among cacheable calls
        log.log_call(
            surface=Surface.REST,
            operation="lookup_company",
            country="NO",
            query="923609016",
            user_agent="agent/1.0",
            latency_ms=5,
            ok=True,
            cached=cached,
        )
    for operation in ("company_deadlines", "validate_company_id", "list_countries"):
        log.log_call(
            surface=Surface.REST,
            operation=operation,
            country=None if operation == "list_countries" else "NO",
            query=None if operation == "list_countries" else "923609016",
            user_agent="agent/1.0",
            latency_ms=5,
            ok=True,
        )

    result = stats.summary(db)

    assert result["total_calls"] == 6
    assert result["cacheable_calls"] == 3
    assert result["cache_hits"] == 2
    assert result["cache_hit_rate"] == pytest.approx(2 / 3)


def test_summary_cache_hit_rate_zero_when_no_cacheable_calls(tmp_path: Path) -> None:
    """`cacheable_calls == 0` with `total_calls > 0` (e.g. only
    `list_countries` traffic, never a cacheable lookup/search) must not
    raise `ZeroDivisionError` — `cache_hit_rate` degrades to `0.0`, the same
    pattern `error_rate` already uses for `total_calls == 0`."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="list_countries",
        country=None,
        query=None,
        user_agent="agent/1.0",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["total_calls"] == 1
    assert result["cacheable_calls"] == 0
    assert result["cache_hits"] == 0
    assert result["cache_hit_rate"] == 0.0


def test_summary_latency_percentiles_and_average(tmp_path: Path) -> None:
    """Nearest-rank `p50`/`p95` plus a mean, over every call's `latency_ms`
    regardless of operation or outcome. Ten values 10..100 make both
    percentiles hand-verifiable: `p50` is the 5th-smallest (rank
    `ceil(0.5*10)=5`), `p95` is the largest (rank `ceil(0.95*10)=10`)."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    for latency_ms in range(10, 101, 10):
        log.log_call(
            surface=Surface.REST,
            operation="lookup_company",
            country="NO",
            query="923609016",
            user_agent="agent/1.0",
            latency_ms=latency_ms,
            ok=True,
        )

    result = stats.summary(db)

    assert result["latency_ms_avg"] == pytest.approx(55.0)
    assert result["latency_ms_p50"] == 50
    assert result["latency_ms_p95"] == 100


def test_summary_latency_single_call(tmp_path: Path) -> None:
    """A single call's latency is its own average, `p50` and `p95` alike —
    the boundary case for `_percentile`'s rank/index clamping."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="agent/1.0",
        latency_ms=42,
        ok=True,
    )

    result = stats.summary(db)

    assert result["latency_ms_avg"] == pytest.approx(42.0)
    assert result["latency_ms_p50"] == 42
    assert result["latency_ms_p95"] == 42


def test_summary_last_call_and_last_non_connect_call_diverge(tmp_path: Path) -> None:
    """`list_countries` is a bare capability probe (`_CONNECT_ONLY_OPERATION`)
    — what an MCP client calls on connect, before asking about a company. A
    `list_countries` call today plus a real `lookup_company` call 5 days ago
    must make `last_call_at` read as today (it counts every operation) while
    `last_non_connect_call_at` still shows the 5-day gap — the exact
    divergence this second pair of fields exists to catch."""
    db = tmp_path / "calls.sqlite3"
    today = datetime.now(UTC).date()
    five_days_ago = today - timedelta(days=5)

    _insert_historical_call(
        db,
        ts=datetime.combine(today, datetime.min.time(), tzinfo=UTC).isoformat(),
        surface=Surface.MCP,
        operation="list_countries",
        country=None,
        query=None,
        user_agent="stdio",
        latency_ms=5,
        ok=True,
    )
    _insert_historical_call(
        db,
        ts=datetime.combine(five_days_ago, datetime.min.time(), tzinfo=UTC).isoformat(),
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="curl/8.0",
        latency_ms=20,
        ok=True,
    )

    result = stats.summary(db)

    assert result["days_since_last_call"] == 0
    assert result["last_call_at"] is not None
    assert result["last_call_at"].startswith(today.isoformat())

    assert result["days_since_last_non_connect_call"] == 5
    assert result["last_non_connect_call_at"] is not None
    assert result["last_non_connect_call_at"].startswith(five_days_ago.isoformat())


def test_summary_malformed_ts_is_skipped_for_date_fields_but_still_counted(
    tmp_path: Path,
) -> None:
    """A row whose `ts` does not parse — should never happen in production,
    since `log_call` always writes `datetime.now(UTC).isoformat()` itself,
    but the aggregator must not crash on one — is skipped by every
    date-derived field (`calls_today`, `calls_per_day`, `last_call_at`,
    `last_non_connect_call_at`) while still counting toward `total_calls`,
    `by_surface` and `by_operation`, exactly as it already did for
    `calls_today`/`calls_per_day` before this task."""
    db = tmp_path / "calls.sqlite3"
    _insert_historical_call(
        db,
        ts="not-a-timestamp",
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="agent/1.0",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["total_calls"] == 1
    assert result["calls_today"] == 0
    assert result["by_surface"] == {"rest": 1}
    assert result["by_operation"] == [{"operation": "lookup_company", "count": 1}]
    assert all(day["count"] == 0 for day in result["calls_per_day"])
    assert result["last_call_at"] is None
    assert result["days_since_last_call"] is None
    assert result["last_non_connect_call_at"] is None
    assert result["days_since_last_non_connect_call"] is None


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(stats_router)
    return app


def test_stats_endpoint_403_without_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log.set_sink(tmp_path / "calls.sqlite3")
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats")

    assert resp.status_code == 403
    body = resp.json()
    assert body["error"]["code"] == "bad_request"


def test_stats_endpoint_403_with_wrong_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log.set_sink(tmp_path / "calls.sqlite3")
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats", params={"key": "wrong"})

    assert resp.status_code == 403


def test_stats_endpoint_403_when_admin_key_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log.set_sink(tmp_path / "calls.sqlite3")
    monkeypatch.delenv("REGISTRY_MCP_ADMIN_KEY", raising=False)
    client = TestClient(_make_app())

    resp = client.get("/v1/stats", params={"key": "anything"})

    assert resp.status_code == 403


def test_stats_endpoint_200_with_correct_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "calls.sqlite3"
    _seed_ten_calls(db)
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats", params={"key": "secret-key"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_calls"] == 10
    assert body["by_surface"] == {"rest": 6, "mcp": 4}
    # T65: `/v1/stats` is a thin wrapper around `summary()` (module docstring)
    # and must carry the same `real_asks` block, not a REST-only extra.
    assert "real_asks" in body
    assert "calls" in body["real_asks"]


# ---------------------------------------------------------------------------
# T65 — `real_asks`: the day-45-gate-flavoured subset of `calls`
# (`~/mcp-growth/DECISION-GATE.md`). `core/stats.py::_is_real_ask` is the
# definition under test; see its module-level constants
# (`_DOCUMENTED_EXAMPLE_QUERIES`, `_OWN_AND_BOT_USER_AGENTS`,
# `_DISQUALIFYING_UA_LABELS`) for exactly what it excludes.
# ---------------------------------------------------------------------------


def test_summary_real_asks_scanner_ua_with_example_query_counts_zero(tmp_path: Path) -> None:
    """A documented-example query (README.md's `equinor`) from the exact
    directory-monitor user agent `~/mcp-growth/DECISION-GATE.md` §8.1 names
    must contribute nothing to `real_asks` — disqualified twice over, by
    query and by user agent."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="search_company",
        country="NO",
        query="equinor",
        user_agent="Mozilla/5.0 (compatible)",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["total_calls"] == 1
    assert result["real_asks"]["calls"] == {"all_time": 0, "last_7_days": 0}
    assert result["real_asks"]["distinct_user_agents"] == {"all_time": 0, "last_7_days": 0}
    assert result["real_asks"]["last"] is None


def test_summary_real_asks_chrome_ua_with_new_uk_number_counts_one(tmp_path: Path) -> None:
    """A real browser asking about a UK company number that is neither of
    our documented examples (`00445790`/`445790`) is exactly what "real ask"
    means to count."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="GB",
        query="01234567",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["real_asks"]["calls"] == {"all_time": 1, "last_7_days": 1}
    assert result["real_asks"]["distinct_user_agents"] == {"all_time": 1, "last_7_days": 1}
    last = result["real_asks"]["last"]
    assert last is not None
    assert last["query"] == "01234567"
    assert last["country"] == "GB"
    assert last["operation"] == "lookup_company"


def test_summary_real_asks_documented_example_from_a_real_browser_still_counts_zero(
    tmp_path: Path,
) -> None:
    """(1) applies regardless of user agent: even a real-looking browser
    asking our own flagship example (923609016) teaches us nothing about
    demand and must not count."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["real_asks"]["calls"] == {"all_time": 0, "last_7_days": 0}


def test_summary_real_asks_documented_example_matching_is_case_insensitive(
    tmp_path: Path,
) -> None:
    """"TESCO", "Tesco" and "tesco" are all the one documented example —
    capitalisation must not be a loophole out of the exclusion."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="search_company",
        country="GB",
        query="TESCO",
        user_agent="curl/9.9.9",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["real_asks"]["calls"] == {"all_time": 0, "last_7_days": 0}


def test_summary_real_asks_sasame_mcp_audit_is_never_real(tmp_path: Path) -> None:
    """`SaSame-MCP-Audit/0.1` contains "MCP", so `ua_classify.classify` labels
    it `coding_agent` (checked before any bot rule) and it arrives over the
    MCP surface — both would otherwise satisfy `_is_real_ask`. Only the
    exact-name exclusion in `_OWN_AND_BOT_USER_AGENTS` catches it, which is
    the whole reason that set exists rather than relying on labels alone."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.MCP,
        operation="lookup_company",
        country="NO",
        query="999999999",
        user_agent="SaSame-MCP-Audit/0.1",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert classify("SaSame-MCP-Audit/0.1") == "coding_agent"
    assert result["real_asks"]["calls"] == {"all_time": 0, "last_7_days": 0}
    assert result["real_asks"]["mcp_sessions_non_bot"] == 0


def test_summary_real_asks_swedish_real_ask_shows_no_identifier_in_last(tmp_path: Path) -> None:
    """D-040 stores `query=NULL` for Sweden regardless of surface, so a
    Swedish `lookup_company` real ask is counted via `_is_real_ask`'s Swedish
    carve-out (`_QUERY_WITHHELD_COUNTRY`/`_WITHHELD_QUERY_OPERATIONS`), and
    its `last` entry must never show an identifier."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.MCP,
        operation="lookup_company",
        country="SE",
        query=None,
        user_agent="claude-code/1.0.0",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["real_asks"]["calls"] == {"all_time": 1, "last_7_days": 1}
    last = result["real_asks"]["last"]
    assert last is not None
    assert last["country"] == "SE"
    assert last["query"] is None


# ---------------------------------------------------------------------------
# Orchestrator review, round 1: two definition refinements to `_is_real_ask`.
#
# (1) A Swedish REST row with `query=NULL` is the one case where "no query"
#     means "the query was withheld" (D-040), not "nothing was asked" — it
#     must count as a real ask for a real user agent, on lookup_company,
#     company_deadlines and validate_company_id alike (search_company too,
#     though it 501s for Sweden today).
# (2) `list_countries` (the bare connect probe every client and every
#     scanner makes) is never a real ask, on either surface. `validate_company_id`
#     is excluded only when its query is a documented example or NULL — a
#     validate of a genuinely new number from a real user agent is a real ask.
# ---------------------------------------------------------------------------


def test_summary_real_asks_swedish_rest_lookup_with_null_query_counts_one_for_real_ua(
    tmp_path: Path,
) -> None:
    """The exact case flagged in review: a Chrome UA, Sweden, `lookup_company`,
    `query=NULL`, over REST — must count as one real ask, not zero."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="SE",
        query=None,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["real_asks"]["calls"] == {"all_time": 1, "last_7_days": 1}
    last = result["real_asks"]["last"]
    assert last is not None
    assert last["country"] == "SE"
    assert last["query"] is None


def test_summary_real_asks_swedish_rest_lookup_with_null_query_counts_zero_for_own_ua(
    tmp_path: Path,
) -> None:
    """The same Swedish REST/`lookup_company`/`query=NULL` shape, but from
    `curl/8.5.0` — one of our own frozen smoke-test user agents
    (`_OWN_AND_BOT_USER_AGENTS`) — must still count zero: the Swedish
    carve-out only waives the query test, never the user-agent test."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="SE",
        query=None,
        user_agent="curl/8.5.0",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["real_asks"]["calls"] == {"all_time": 0, "last_7_days": 0}
    assert result["real_asks"]["last"] is None


def test_summary_real_asks_swedish_rest_company_deadlines_and_validate_null_query_count(
    tmp_path: Path,
) -> None:
    """The same carve-out extends to `company_deadlines` and
    `validate_company_id`, per the orchestrator's operation list —
    not just `lookup_company`."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="company_deadlines",
        country="SE",
        query=None,
        user_agent="curl/9.9.9",
        latency_ms=5,
        ok=True,
    )
    log.log_call(
        surface=Surface.REST,
        operation="validate_company_id",
        country="SE",
        query=None,
        user_agent="curl/9.9.9",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["real_asks"]["calls"] == {"all_time": 2, "last_7_days": 2}


def test_summary_real_asks_list_countries_never_real_on_either_surface(
    tmp_path: Path,
) -> None:
    """`list_countries` is the bare capability probe every client — and
    every scanner — makes on connect. A real, non-bot user agent calling it
    must still not count as a real ask, on REST or MCP."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="list_countries",
        country=None,
        query=None,
        user_agent="curl/9.9.9",
        latency_ms=5,
        ok=True,
    )
    log.log_call(
        surface=Surface.MCP,
        operation="list_countries",
        country=None,
        query=None,
        user_agent="claude-code/1.0.0",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["total_calls"] == 2
    assert result["real_asks"]["calls"] == {"all_time": 0, "last_7_days": 0}
    assert result["real_asks"]["last"] is None


def test_summary_real_asks_validate_company_id_new_number_from_real_ua_counts_one(
    tmp_path: Path,
) -> None:
    """A `validate_company_id` call on a genuinely new number, from a real
    (non-bot, non-own) user agent, is a real ask — `validate_company_id` is
    excluded only for a documented-example or NULL query, never blanket."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="validate_company_id",
        country="GB",
        query="12345678",  # not 00445790/445790, and not OC303675 (evals/cases.json's Deloitte LLP example)
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["real_asks"]["calls"] == {"all_time": 1, "last_7_days": 1}
    last = result["real_asks"]["last"]
    assert last is not None
    assert last["operation"] == "validate_company_id"
    assert last["query"] == "12345678"


def test_summary_real_asks_validate_company_id_excluded_for_example_or_null_query(
    tmp_path: Path,
) -> None:
    """`validate_company_id` is excluded when its query is a documented
    example (445790, the GB validate example) or NULL for a non-Swedish
    reason — the same real user agent counts zero either way, unlike the
    Swedish case above."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="validate_company_id",
        country="GB",
        query="445790",
        user_agent="curl/9.9.9",
        latency_ms=5,
        ok=True,
    )
    log.log_call(
        surface=Surface.MCP,
        operation="validate_company_id",
        country=None,
        query=None,
        user_agent="claude-code/1.0.0",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["real_asks"]["calls"] == {"all_time": 0, "last_7_days": 0}
    assert result["real_asks"]["last"] is None


def test_summary_real_asks_last_re_redacts_a_legacy_unredacted_swedish_row(
    tmp_path: Path,
) -> None:
    """Defense in depth: even a historical row that somehow stored a Swedish
    query unredacted must never surface it through `real_asks.last` —
    `core.registry.loggable_query` is re-applied here rather than trusted
    from the write path."""
    db = tmp_path / "calls.sqlite3"
    _insert_historical_call(
        db,
        ts=datetime.now(UTC).isoformat(),
        surface=Surface.MCP,
        operation="lookup_company",
        country="SE",
        query="5566778899",  # deliberately NOT one of the documented examples
        user_agent="claude-code/1.0.0",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    last = result["real_asks"]["last"]
    assert last is not None
    assert last["country"] == "SE"
    assert last["query"] is None


def test_summary_real_asks_ceiling_hitter_fires_at_50_not_49(tmp_path: Path) -> None:
    """M4 (`~/mcp-growth/DECISION-GATE.md` amendment A2): >=50 calls from one
    user agent within a single UTC minute must appear in `ceiling_hitters`;
    49 must not."""
    db = tmp_path / "calls.sqlite3"
    minute = datetime.now(UTC).replace(second=0, microsecond=0)
    for i in range(50):
        _insert_historical_call(
            db,
            ts=(minute + timedelta(seconds=i % 59)).isoformat(),
            surface=Surface.REST,
            operation="lookup_company",
            country="GB",
            query=f"AT{i:06d}",
            user_agent="ceiling-tester/1.0",
            latency_ms=1,
            ok=True,
        )
    for i in range(49):
        _insert_historical_call(
            db,
            ts=(minute + timedelta(seconds=i % 59)).isoformat(),
            surface=Surface.REST,
            operation="lookup_company",
            country="GB",
            query=f"BT{i:06d}",
            user_agent="sub-ceiling-tester/1.0",
            latency_ms=1,
            ok=True,
        )

    result = stats.summary(db)

    hitters = {
        row["user_agent"]: row["calls_in_minute"] for row in result["real_asks"]["ceiling_hitters"]
    }
    assert hitters == {"ceiling-tester/1.0": 50}
    assert "sub-ceiling-tester/1.0" not in hitters


def test_summary_real_asks_ceiling_hitter_only_within_last_7_days(tmp_path: Path) -> None:
    """A 50-call-in-one-minute burst older than 7 days must not appear in
    `ceiling_hitters` (scoped reading) even though it still counts toward
    the all-time real-ask total."""
    db = tmp_path / "calls.sqlite3"
    old_minute = (datetime.now(UTC) - timedelta(days=8)).replace(second=0, microsecond=0)
    for i in range(50):
        _insert_historical_call(
            db,
            ts=(old_minute + timedelta(seconds=i % 59)).isoformat(),
            surface=Surface.REST,
            operation="lookup_company",
            country="GB",
            query=f"OLD{i:06d}",
            user_agent="stale-burst/1.0",
            latency_ms=1,
            ok=True,
        )

    result = stats.summary(db)

    assert result["real_asks"]["ceiling_hitters"] == []
    assert result["real_asks"]["calls"]["all_time"] == 50
    assert result["real_asks"]["calls"]["last_7_days"] == 0


def test_summary_real_asks_by_source_named_excludes_no_source_bucket(tmp_path: Path) -> None:
    """`real_asks.by_source_named` is `by_source` (T64) minus the
    `NO_SOURCE_KEY` bucket — named channels only."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="GB",
        query="01234567",
        user_agent="curl/9.9.9",
        latency_ms=5,
        ok=True,
        source="readme",
    )
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="GB",
        query="09876543",
        user_agent="curl/9.9.9",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["real_asks"]["by_source_named"] == [{"source": "readme", "count": 1}]
    assert all(row["source"] != stats.NO_SOURCE_KEY for row in result["real_asks"]["by_source_named"])


def test_summary_real_asks_mcp_sessions_non_bot_counts_distinct_recent_mcp_user_agents(
    tmp_path: Path,
) -> None:
    """`mcp_sessions_non_bot` is distinct MCP user agents, excluding
    known own/bot ones, in the last 7 days — independent of query content
    and of REST traffic on the same user agent string."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.MCP,
        operation="lookup_company",
        country="NO",
        query="111111111",
        user_agent="claude-code/1.0.0",
        latency_ms=5,
        ok=True,
    )
    log.log_call(
        surface=Surface.MCP,
        operation="lookup_company",
        country="NO",
        query="222222222",
        user_agent="claude-code/1.0.0",
        latency_ms=5,
        ok=True,
    )
    log.log_call(
        surface=Surface.MCP,
        operation="list_countries",
        country=None,
        query=None,
        user_agent="SaSame-MCP-Audit/0.1",
        latency_ms=5,
        ok=True,
    )
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="333333333",
        user_agent="claude-code/2.0.0",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["real_asks"]["mcp_sessions_non_bot"] == 1


def test_summary_real_asks_full_scenario(tmp_path: Path) -> None:
    """One deterministic scenario exercising every `real_asks` field
    together — the fixture quoted in T65's task report.

    Six groups of calls, oldest to newest: (F) a 50-call-in-one-minute burst
    from one user agent (ceiling hitter, all real), (A) a scanner asking a
    documented example (not real), (B) a real browser asking a new GB number
    (real), (D) `SaSame-MCP-Audit` asking a documented example over MCP (not
    real, twice over), (E) `curl` asking a new GB number with a named source
    (real), (C) a Swedish real ask over MCP, most recent of all (real,
    redacted in `last`).
    """
    db = tmp_path / "calls.sqlite3"
    now = datetime.now(UTC)
    minute_f = (now - timedelta(minutes=10)).replace(second=0, microsecond=0)

    for i in range(50):
        _insert_historical_call(
            db,
            ts=(minute_f + timedelta(seconds=i % 59)).isoformat(),
            surface=Surface.REST,
            operation="lookup_company",
            country="NO",
            query=f"F{i:08d}",
            user_agent="ceiling-tester/1.0",
            latency_ms=1,
            ok=True,
        )
    _insert_historical_call(
        db,
        ts=(now - timedelta(minutes=9)).isoformat(),
        surface=Surface.REST,
        operation="search_company",
        country="NO",
        query="equinor",
        user_agent="Mozilla/5.0 (compatible)",
        latency_ms=5,
        ok=True,
    )
    _insert_historical_call(
        db,
        ts=(now - timedelta(minutes=8)).isoformat(),
        surface=Surface.REST,
        operation="lookup_company",
        country="GB",
        query="01234567",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        latency_ms=5,
        ok=True,
    )
    _insert_historical_call(
        db,
        ts=(now - timedelta(minutes=7)).isoformat(),
        surface=Surface.MCP,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="SaSame-MCP-Audit/0.1",
        latency_ms=5,
        ok=True,
    )
    conn = log.connect(db)
    try:
        conn.execute(
            "INSERT INTO calls "
            "(ts, surface, operation, country, query, user_agent, latency_ms, ok, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (now - timedelta(minutes=6)).isoformat(),
                Surface.REST.value,
                "lookup_company",
                "GB",
                "07654321",
                "curl/9.9.9",
                5,
                1,
                "readme",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    _insert_historical_call(
        db,
        ts=now.isoformat(),
        surface=Surface.MCP,
        operation="lookup_company",
        country="SE",
        query=None,
        user_agent="claude-code/1.0.0",
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["total_calls"] == 55  # 50 (F) + A + B + D + E + C
    real_asks = result["real_asks"]
    assert real_asks["calls"] == {"all_time": 53, "last_7_days": 53}
    assert real_asks["distinct_user_agents"] == {"all_time": 4, "last_7_days": 4}
    assert real_asks["mcp_sessions_non_bot"] == 1
    assert real_asks["by_source_named"] == [{"source": "readme", "count": 1}]
    assert real_asks["last"] == {
        "ts": now.isoformat(),
        "operation": "lookup_company",
        "country": "SE",
        "query": None,
    }
    assert real_asks["ceiling_hitters"] == [
        {"user_agent": "ceiling-tester/1.0", "calls_in_minute": 50}
    ]


# ---------------------------------------------------------------------------
# T66 — the homepage playground (`static/index.html`) tags every request it
# makes `?src=playground`, so `real_asks` can exclude those rows instead of
# counting every click via D-040's Swedish query-withheld carve-out (the
# playground's default example is Swedish): live reading was 59 "real asks"
# from 19 user agents on 2026-09-10, almost all one crawler replaying the
# playground under 16 different user agents inside two minutes (07:53Z).
# Fixed two ways below: (1) `source == "playground"` is always excluded and
# reported separately (`real_asks.playground`); (2) a calendar minute with
# `_CRAWLER_BURST_MIN_DISTINCT_UAS` (8) or more distinct non-own user agents
# is a "crawler burst" and excludes every row in it.
# ---------------------------------------------------------------------------


def test_summary_real_asks_playground_source_excluded_and_reported(tmp_path: Path) -> None:
    """A row tagged `source="playground"` must never count as a real ask,
    even though every other criterion here would otherwise count it (a
    non-example GB number from a real browser) — and it must show up
    instead in `real_asks.playground`."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="GB",
        query="01234567",  # not a documented example
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        latency_ms=5,
        ok=True,
        source="playground",
    )

    result = stats.summary(db)

    assert result["total_calls"] == 1
    assert result["real_asks"]["calls"] == {"all_time": 0, "last_7_days": 0}
    assert result["real_asks"]["last"] is None
    assert result["real_asks"]["playground"] == {
        "calls_last_7_days": 1,
        "distinct_user_agents_last_7_days": 1,
    }


def test_summary_real_asks_swedish_playground_click_excluded_but_untagged_browser_call_counts(
    tmp_path: Path,
) -> None:
    """The homepage playground's default example is Swedish, so before T66
    every playground click counted as a real ask via the Swedish
    query-withheld carve-out (D-040, `_QUERY_WITHHELD_COUNTRY`). The
    identical call tagged `?src=playground` must now count zero and appear
    in `real_asks.playground`; the same call from a real browser with no
    `?src=` at all must still count one, exactly as it did before T66."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    chrome_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="SE",
        query=None,
        user_agent=chrome_ua,
        latency_ms=5,
        ok=True,
        source="playground",
    )
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="SE",
        query=None,
        user_agent=chrome_ua,
        latency_ms=5,
        ok=True,
    )

    result = stats.summary(db)

    assert result["total_calls"] == 2
    assert result["real_asks"]["calls"] == {"all_time": 1, "last_7_days": 1}
    last = result["real_asks"]["last"]
    assert last is not None
    assert last["country"] == "SE"
    assert last["query"] is None
    assert result["real_asks"]["playground"] == {
        "calls_last_7_days": 1,
        "distinct_user_agents_last_7_days": 1,
    }


def test_summary_real_asks_crawler_burst_at_eight_not_seven(tmp_path: Path) -> None:
    """`_CRAWLER_BURST_MIN_DISTINCT_UAS`: a calendar minute with 8 distinct
    non-own user agents is a crawler burst and excludes every row logged in
    it from `real_asks`, even though none of those rows is individually a
    documented example, own, or bot-classified user agent. A minute with
    only 7 distinct user agents is not a burst, and those rows count
    normally."""
    db = tmp_path / "calls.sqlite3"
    burst_minute = datetime.now(UTC).replace(second=0, microsecond=0)
    for i in range(8):
        _insert_historical_call(
            db,
            ts=(burst_minute + timedelta(seconds=i)).isoformat(),
            surface=Surface.REST,
            operation="lookup_company",
            country="GB",
            query=f"BURST{i:03d}",
            user_agent=f"visitor-{i}/1.0",
            latency_ms=1,
            ok=True,
        )
    quiet_minute = burst_minute + timedelta(minutes=5)
    for i in range(7):
        _insert_historical_call(
            db,
            ts=(quiet_minute + timedelta(seconds=i)).isoformat(),
            surface=Surface.REST,
            operation="lookup_company",
            country="GB",
            query=f"QUIET{i:03d}",
            user_agent=f"visitor-{i}/1.0",
            latency_ms=1,
            ok=True,
        )

    result = stats.summary(db)

    assert result["total_calls"] == 15
    # Only the 7 rows in the non-burst minute count; all 8 burst-minute rows
    # are excluded.
    assert result["real_asks"]["calls"] == {"all_time": 7, "last_7_days": 7}
    assert result["real_asks"]["crawler_burst_minutes"] == 1


def test_index_html_tags_both_fetch_sites_with_playground_source() -> None:
    """T66: every request `static/index.html` makes must carry
    `?src=playground` (`core/stats.py`'s `_PLAYGROUND_SOURCE`), so the
    homepage playground's own traffic — Swedish by default, which used to
    slip through D-040's query-withheld carve-out — is never counted as a
    real ask. A static read of the file rather than a browser test: this
    project has no JS test runner. Both `fetch(` call sites (the
    `/v1/countries` read at load, and the playground's own request helper)
    must route through the same tagging helper, which must itself append
    `src=playground`. Grouped here rather than in a dedicated static-assets
    test module per this task's footprint."""
    html = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(
        encoding="utf-8"
    )

    assert html.count("fetch(") == 2, "expected exactly two fetch( call sites"
    assert html.count("fetch(withPlaygroundSrc(") == 2, (
        "both fetch( call sites must route through the src=playground tagging helper"
    )
    assert '"src=playground"' in html
