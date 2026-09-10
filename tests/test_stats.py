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
