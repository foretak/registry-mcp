"""Tests for `api/status.py` (T13).

Mounts `status_router` on a throwaway `FastAPI()` app, never
`registry_mcp.api.main:app`, per the same pattern `tests/test_stats.py` /
`tests/test_dashboard.py` use for their routers. The upstream brreg check is
mocked with `respx` so this test suite never makes a real network call.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from registry_mcp.api import status as status_module
from registry_mcp.api.status import status_router
from registry_mcp.core import cache
from registry_mcp.registries.no.client import BASE_URL


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_PATH", str(tmp_path / "cache.sqlite3"))
    monkeypatch.delenv("REGISTRY_MCP_CACHE_DISABLED", raising=False)
    yield


@pytest.fixture(autouse=True)
def _reset_upstream_cache() -> Iterator[None]:
    """Each test gets a fresh upstream-reachability cache, not the module singleton."""
    status_module._upstream_state.reachable = None
    status_module._upstream_state.checked_at = None
    yield
    status_module._upstream_state.reachable = None
    status_module._upstream_state.checked_at = None


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(status_router)
    return TestClient(app)


def test_status_ok_when_upstream_reachable() -> None:
    with respx.mock:
        respx.get(BASE_URL).mock(return_value=httpx.Response(200, json={}))
        client = _make_client()
        response = client.get("/status")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "registry-mcp status" in body
    assert "reachable" in body
    assert "NO" in body


def test_status_reports_unreachable_upstream() -> None:
    with respx.mock:
        respx.get(BASE_URL).mock(side_effect=httpx.ConnectTimeout("boom"))
        client = _make_client()
        response = client.get("/status")

    assert response.status_code == 200
    assert "unreachable" in response.text


def test_status_reports_5xx_as_unreachable() -> None:
    with respx.mock:
        respx.get(BASE_URL).mock(return_value=httpx.Response(503))
        client = _make_client()
        response = client.get("/status")

    assert response.status_code == 200
    assert "unreachable" in response.text


def test_upstream_check_is_cached_across_requests() -> None:
    with respx.mock:
        route = respx.get(BASE_URL).mock(return_value=httpx.Response(200, json={}))
        client = _make_client()
        client.get("/status")
        client.get("/status")
        client.get("/status")

    assert route.call_count == 1


def test_status_reflects_cache_row_count() -> None:
    cache.set("NO:brreg:entity:923609016", {"name": "EQUINOR ASA"})
    cache.set("NO:brreg:entity:974760673", {"name": "MICROSOFT NORGE AS"})

    with respx.mock:
        respx.get(BASE_URL).mock(return_value=httpx.Response(200, json={}))
        client = _make_client()
        response = client.get("/status")

    assert "2" in response.text


def test_status_missing_cache_file_reports_unknown_not_error() -> None:
    with respx.mock:
        respx.get(BASE_URL).mock(return_value=httpx.Response(200, json={}))
        client = _make_client()
        response = client.get("/status")

    assert response.status_code == 200
    assert "unknown" in response.text


def test_status_not_in_openapi_schema() -> None:
    app = FastAPI()
    app.include_router(status_router)
    schema = app.openapi()
    assert "/status" not in schema.get("paths", {})


def test_status_carries_no_secrets() -> None:
    """The page must never leak the admin key or any per-query data."""
    with respx.mock:
        respx.get(BASE_URL).mock(return_value=httpx.Response(200, json={}))
        client = _make_client()
        response = client.get("/status")

    assert "REGISTRY_MCP_ADMIN_KEY" not in response.text
    assert "change-me" not in response.text
