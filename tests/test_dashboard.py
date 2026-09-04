"""Tests for `api/dashboard.py` (T09).

Mounts `dashboard_router` on a throwaway `FastAPI()` app — never
`registry_mcp.api.main:app`, since another agent is concurrently editing that
file (see the module docstring in `api/dashboard.py`). Seeds a temp SQLite
file via `core/log.py::set_sink()` + `log_call()`, exactly like
`tests/test_stats.py` does for `api/stats.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
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
