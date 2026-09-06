"""Tests for `core/stats.py` and `api/stats.py` (`NORBIZ_SPEC.md` §11, T08).

`core/stats.py` tests log ten calls straight into a temp SQLite file (via
`core/log.py::log_call`, so the two modules are tested together the way they
are actually used) and check the aggregation. `api/stats.py` tests mount
`stats_router` on a throwaway `FastAPI()` app — never `registry_mcp.api.main:app`,
per this task's instructions, since another agent is mid-edit on that file.
"""

from __future__ import annotations

from collections.abc import Iterator
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


def test_summary_on_empty_database_is_zeroed(tmp_path: Path) -> None:
    result = stats.summary(tmp_path / "empty.sqlite3")
    assert result["total_calls"] == 0
    assert result["calls_today"] == 0
    assert len(result["calls_per_day"]) == 30
    assert all(day["count"] == 0 for day in result["calls_per_day"])
    assert result["by_surface"] == {}
    assert result["top_queries"] == []
    assert result["user_agents"] == []
    assert result["error_rate"] == 0.0
    assert result["distinct_user_agents"] == 0


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
