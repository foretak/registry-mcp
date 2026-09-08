"""Tests for `api/dashboard.py` (T09).

Mounts `dashboard_router` on a throwaway `FastAPI()` app — never
`registry_mcp.api.main:app`, since another agent is concurrently editing that
file (see the module docstring in `api/dashboard.py`). Seeds a temp SQLite
file via `core/log.py::set_sink()` + `log_call()`, exactly like
`tests/test_stats.py` does for `api/stats.py`.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from registry_mcp.api.dashboard import dashboard_router
from registry_mcp.core import log
from registry_mcp.core.models import Surface


@pytest.fixture(autouse=True)
def _reset_sink() -> Iterator[None]:
    yield
    log.set_sink(None)


def _seed_calls(db: Path) -> None:
    log.set_sink(db)
    calls = [
        # (surface, operation, country, query, user_agent, ok, error_code)
        (Surface.REST, "lookup_company", "NO", "923609016", "curl/8.4.0", True, None),
        (Surface.REST, "lookup_company", "NO", "923609016", "curl/8.4.0", True, None),
        (
            Surface.REST,
            "lookup_company",
            "NO",
            "923609016",
            "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0.0.0 Safari/537.36",
            True,
            None,
        ),
        (Surface.REST, "search_company", "NO", "equinor", "curl/8.4.0", False, "not_found"),
        (Surface.MCP, "lookup_company", "NO", "923609016", "claude-code/1.0.0", True, None),
        (Surface.MCP, "search_company", "NO", "equinor", "stdio", True, None),
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
    `datetime.now(UTC)` stamp — the only way to test "days ago" wording
    deterministically without a time-mocking dependency this project does
    not have. Duplicated from `tests/test_stats.py` rather than imported
    across test modules, deliberately: keeps this file independent of
    whatever another task is doing to that one. Schema via `log.connect`, the
    same function `log_call`/`summary` both use.
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


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(dashboard_router)
    return app


def test_dashboard_403_without_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log.set_sink(tmp_path / "calls.sqlite3")
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard")

    assert resp.status_code == 403
    body = resp.json()
    assert body["error"]["code"] == "bad_request"


def test_dashboard_403_with_wrong_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log.set_sink(tmp_path / "calls.sqlite3")
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard", params={"key": "wrong"})

    assert resp.status_code == 403


def test_dashboard_403_when_admin_key_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log.set_sink(tmp_path / "calls.sqlite3")
    monkeypatch.delenv("REGISTRY_MCP_ADMIN_KEY", raising=False)
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard", params={"key": "anything"})

    assert resp.status_code == 403


def test_dashboard_200_with_correct_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "calls.sqlite3"
    _seed_calls(db)
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard", params={"key": "secret-key"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    html = resp.text

    # The seeded query appears.
    assert "923609016" in html
    assert "equinor" in html

    # Classifier labels show up as pills.
    assert "coding_agent" in html
    assert "browser" in html
    assert "script" in html

    # Basic counters made it onto the page.
    assert "Total calls" in html
    assert "Calls today" in html
    assert "Error rate" in html

    # The country breakdown section is present, with the seeded country in it.
    assert "Calls by country" in html
    assert ">NO<" in html


def test_dashboard_escapes_malicious_user_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    malicious_ua = "<script>alert('xss')</script>curl/8.0"
    malicious_query = "<img src=x onerror=alert(1)>"
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query=malicious_query,
        user_agent=malicious_ua,
        latency_ms=5,
        ok=True,
    )
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard", params={"key": "secret-key"})

    assert resp.status_code == 200
    html = resp.text
    assert "<script>alert" not in html
    assert "<img src=x onerror" not in html
    # The escaped forms should be present instead.
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_dashboard_empty_database_renders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log.set_sink(tmp_path / "empty.sqlite3")
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard", params={"key": "secret-key"})

    assert resp.status_code == 200
    assert "No calls logged yet." in resp.text


def test_dashboard_renders_with_a_null_query_row_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-040: a Swedish lookup logs `query=NULL` (`core.registry.loggable_query`'s
    redaction). `core/stats.py` already excludes a falsy query from `top_queries`, so this
    row must never reach `api/dashboard.py`'s `row['query']` rendering — the page must
    still render (200, no exception) with a real row present alongside it."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="SE",
        query=None,
        user_agent="curl/8.4.0",
        latency_ms=5,
        ok=False,
        error_code="upstream_error",
    )
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="curl/8.4.0",
        latency_ms=5,
        ok=True,
    )
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard", params={"key": "secret-key"})

    assert resp.status_code == 200
    assert "923609016" in resp.text
    assert "Total calls" in resp.text


def test_dashboard_renders_with_a_null_country_row_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A call with no resolved country (`list_countries`, a D-031 connector
    alias before the country is derived, or an error raised before
    resolution) logs `country=NULL`. `core/stats.py` keys that row
    `stats.NO_COUNTRY_KEY` ("none") in `by_country`; the dashboard must
    render it as an honest label alongside a real country's row — never as
    if the raw key were itself a country code, and this is never a D-040
    redaction (D-040 empties `query` for a flagged country, not `country`)."""
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.REST,
        operation="list_countries",
        country=None,
        query=None,
        user_agent="curl/8.4.0",
        latency_ms=5,
        ok=True,
    )
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="curl/8.4.0",
        latency_ms=5,
        ok=True,
    )
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard", params={"key": "secret-key"})

    assert resp.status_code == 200
    html = resp.text
    assert "Calls by country" in html
    assert ">NO<" in html
    # An honest label, styled like a classifier pill — never the raw
    # `NO_COUNTRY_KEY` value rendered as if it were a country code.
    assert "no country" in html
    assert "pill-nocountry" in html


def test_dashboard_shows_calls_by_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    log.log_call(
        surface=Surface.MCP,
        operation="list_countries",
        country=None,
        query=None,
        user_agent="stdio",
        latency_ms=5,
        ok=True,
    )
    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="curl/8.4.0",
        latency_ms=10,
        ok=True,
    )
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard", params={"key": "secret-key"})

    assert resp.status_code == 200
    html = resp.text
    assert "Calls by operation" in html
    assert "list_countries" in html
    assert "lookup_company" in html


def test_dashboard_shows_cache_and_latency_stats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    for latency_ms in (100, 200):
        log.log_call(
            surface=Surface.REST,
            operation="lookup_company",
            country="NO",
            query="923609016",
            user_agent="curl/8.4.0",
            latency_ms=latency_ms,
            ok=True,
            cached=True,
        )
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard", params={"key": "secret-key"})

    assert resp.status_code == 200
    html = resp.text
    assert "Cache hit rate" in html
    assert "100.0%" in html
    assert "2 of 2 cacheable calls" in html
    assert "Latency (ms)" in html
    assert "150.0" in html  # mean of 100 and 200


def test_dashboard_shows_last_call_recency_tiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`list_countries` today, a real lookup 4 days ago: "Last call" must
    read as fresh ("today") while "Last non-connect call" must show the
    4-day gap — the divergence the two tiles exist to make visible (see
    `core/stats.py`'s `_CONNECT_ONLY_OPERATION`)."""
    db = tmp_path / "calls.sqlite3"
    today = datetime.now(UTC).date()
    four_days_ago = today - timedelta(days=4)
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
        ts=datetime.combine(four_days_ago, datetime.min.time(), tzinfo=UTC).isoformat(),
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="curl/8.4.0",
        latency_ms=10,
        ok=True,
    )
    log.set_sink(db)
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard", params={"key": "secret-key"})

    assert resp.status_code == 200
    html = resp.text
    assert "Last call" in html
    assert "Last non-connect call" in html
    assert "today" in html
    assert "4 days ago" in html


def test_dashboard_empty_database_shows_no_calls_yet_for_recency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log.set_sink(tmp_path / "empty.sqlite3")
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard", params={"key": "secret-key"})

    assert resp.status_code == 200
    html = resp.text
    assert "Last call" in html
    assert "Last non-connect call" in html
    assert "no calls yet" in html
    assert "Cache hit rate" in html
    assert "0.0%" in html
    assert "0 of 0 cacheable calls" in html
    # A `None` day-count or timestamp must never leak into the page as text.
    assert ">None<" not in html


# ---------------------------------------------------------------------------
# The chart fix gets the test it was missing (`REVIEW.md` S-series finding 9):
# a fixed pixel `width='{n * 22 + 4}'` on the chart `<svg>`, inside a
# `overflow-x: auto` wrapper, scrolled a phone straight to the empty left edge
# of the 30-day window. Neither regression below shipped a failing test.
# ---------------------------------------------------------------------------


def _chart_svg_tag(html: str) -> str:
    """The chart's own `<svg ...>` opening tag, isolated from the `<rect>` bars
    inside it — those legitimately carry their own fixed pixel `width='{bar_w}'`
    (drawing coordinates inside the `viewBox`), which must not be confused with a
    fixed pixel width on the outer `<svg>` element itself."""
    match = re.search(r"<svg\b[^>]*>", html)
    assert match is not None, "no <svg> in the rendered dashboard"
    return match.group(0)


def test_dashboard_chart_svg_is_responsive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The chart must be sized by `viewBox` with `width='100%'` — the exact
    attribute form `api/dashboard.py`'s `_render_bar_chart` emits — so it scales
    to its `overflow-x: auto` wrapper instead of forcing a fixed pixel width."""
    db = tmp_path / "calls.sqlite3"
    _seed_calls(db)
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard", params={"key": "secret-key"})

    assert resp.status_code == 200
    html = resp.text
    assert "viewBox=" in html
    assert "width='100%'" in html
    svg_tag = _chart_svg_tag(html)
    assert "viewBox=" in svg_tag
    assert "width='100%'" in svg_tag


def test_dashboard_chart_svg_has_no_fixed_pixel_width(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression pin: the bug that shipped was a fixed pixel `width='<digits>'`
    on the chart `<svg>` itself (e.g. `width='664'` for a 30-day window) — this
    must never come back, on the `<svg>` element specifically."""
    db = tmp_path / "calls.sqlite3"
    _seed_calls(db)
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "secret-key")
    client = TestClient(_make_app())

    resp = client.get("/v1/stats/dashboard", params={"key": "secret-key"})

    assert resp.status_code == 200
    svg_tag = _chart_svg_tag(resp.text)
    assert re.search(r"width='\d+'", svg_tag) is None
