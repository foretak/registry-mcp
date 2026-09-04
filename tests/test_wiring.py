"""End-to-end tests for the T08 wiring step: `record_call = log.log_call` in both
`api/main.py` and `mcp/server.py`, plus `stats_router`/`dashboard_router` mounted
on the real `registry_mcp.api.main:app`.

Unlike `tests/test_stats.py` / `tests/test_dashboard.py` (T08/T09, mounted on a
throwaway `FastAPI()` app because another agent was mid-edit on `api/main.py`
at the time), these tests exercise the real app end to end: real REST routes,
a real in-process MCP `fastmcp.Client`, and `log.set_sink()` pointed at a temp
database so every call from both surfaces lands in one place to assert on.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.exceptions import ToolError

from registry_mcp.api.main import app
from registry_mcp.core import log, stats
from registry_mcp.mcp.server import mcp
from registry_mcp.registries.no import client as client_module

FIXTURES = Path(__file__).parent / "fixtures"
BASE_URL = client_module.BASE_URL

# A distinct subnet from `tests/test_api.py`/`tests/test_mcp.py`'s 203.0.113.x
# addresses, so this file's calls never share a rate-limit bucket with theirs
# (the limiter's bucket dict lives on the single `RateLimitMiddleware`
# instance attached to the `app` singleton, for the whole test session).
_IP = "198.51.100.10"


def _load_fixture(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return result


EQUINOR = _load_fixture("brreg_923609016.json")


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_PATH", str(tmp_path / "cache.sqlite3"))
    monkeypatch.delenv("REGISTRY_MCP_CACHE_DISABLED", raising=False)
    monkeypatch.delenv("REGISTRY_MCP_CACHE_TTL_SECONDS", raising=False)
    yield


@pytest.fixture(autouse=True)
async def _reset_http_client() -> AsyncIterator[None]:
    client_module._client = None
    yield
    await client_module.aclose()


@pytest.fixture(autouse=True)
def _isolated_log(tmp_path: Path) -> Iterator[Path]:
    """Point `core/log.py` at a private file for this test, regardless of the
    cache path — `log.log_path()` would otherwise fall back to
    `REGISTRY_MCP_CACHE_PATH` (D-006), which `_isolated_cache` above already
    isolates per test, but `set_sink` makes the intent explicit and is what
    the two surfaces' `record_call = log.log_call` wiring reads from directly.
    """
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)
    yield db
    log.set_sink(None)


async def test_rest_and_mcp_calls_land_in_one_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """Eight logged calls (four REST, four MCP) plus two unlogged static/health
    reads, then `stats.summary()` must show exactly the logged eight, both
    surfaces, the right operations, three distinct user agents, and no trace
    of the crawler UA used only for the two calls that must not be logged."""
    with respx.mock:
        respx.get(f"{BASE_URL}/enheter/923609016").mock(
            return_value=httpx.Response(200, json=EQUINOR)
        )
        respx.get(f"{BASE_URL}/enheter/923609017").mock(return_value=httpx.Response(404))
        respx.get(f"{BASE_URL}/underenheter/923609017").mock(return_value=httpx.Response(404))
        envelope = {
            "_embedded": {"enheter": [EQUINOR]},
            "page": {"size": 1, "totalElements": 1, "totalPages": 1, "number": 0},
        }
        respx.get(f"{BASE_URL}/enheter").mock(return_value=httpx.Response(200, json=envelope))

        with TestClient(app) as rest_client:
            # --- must NOT be logged (`NORBIZ_SPEC.md` §15) ---------------------
            rest_client.get(
                "/health",
                headers={"X-Forwarded-For": _IP, "User-Agent": "crawler-agent/1.0"},
            )
            rest_client.get(
                "/llms.txt",
                headers={"X-Forwarded-For": _IP, "User-Agent": "crawler-agent/1.0"},
            )

            # --- REST, logged: 1 lookup ok, 1 validate ok, 1 lookup error, 1 search ok
            r1 = rest_client.get(
                "/v1/NO/company/923609016",
                headers={"X-Forwarded-For": _IP, "User-Agent": "agent-A/1.0"},
            )
            assert r1.status_code == 200
            r2 = rest_client.get(
                "/v1/NO/validate/923609016",
                headers={"X-Forwarded-For": _IP, "User-Agent": "agent-B/1.0"},
            )
            assert r2.status_code == 200
            r3 = rest_client.get(
                "/v1/NO/company/923609017",
                headers={"X-Forwarded-For": _IP, "User-Agent": "agent-B/1.0"},
            )
            assert r3.status_code == 400  # invalid_id (fails MOD11)
            r4 = rest_client.get(
                "/v1/NO/search",
                params={"q": "equinor"},
                headers={"X-Forwarded-For": _IP, "User-Agent": "agent-A/1.0"},
            )
            assert r4.status_code == 200

        # --- MCP, logged: 1 lookup ok, 1 validate (invalid, non-raising), ------
        # --- 1 deadlines ok, 1 lookup error (unsupported_country) --------------
        async with Client(mcp) as mcp_client:
            m1 = await mcp_client.call_tool("lookup_company", {"id": "923609016"})
            assert m1.data["name"] == "EQUINOR ASA"

            m2 = await mcp_client.call_tool("validate_company_id", {"id": "833286602"})
            assert m2.data["valid"] is False

            m3 = await mcp_client.call_tool(
                "company_deadlines", {"id": "923609016", "today": "2026-01-15"}
            )
            assert "deadlines" in m3.data

            with pytest.raises(ToolError):
                await mcp_client.call_tool("lookup_company", {"id": "1", "country": "SE"})

    summary = stats.summary()
    assert summary["total_calls"] == 8
    assert summary["by_surface"] == {"rest": 4, "mcp": 4}
    assert summary["distinct_user_agents"] == 3

    user_agents = {row["user_agent"] for row in summary["user_agents"]}
    assert user_agents == {"agent-A/1.0", "agent-B/1.0", "stdio"}
    assert "crawler-agent/1.0" not in user_agents  # /health and /llms.txt: never logged

    queries = {row["query"] for row in summary["top_queries"]}
    assert "923609016" in queries
    assert "equinor" in queries
    assert "833286602" in queries


async def test_stats_and_dashboard_mounted_on_real_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """`GET /v1/stats` and `GET /v1/stats/dashboard` on the real app agree with
    `stats.summary()`, gated by `REGISTRY_MCP_ADMIN_KEY` exactly like
    `api/stats.py`/`api/dashboard.py` document."""
    monkeypatch.setenv("REGISTRY_MCP_ADMIN_KEY", "test123")

    with respx.mock:
        respx.get(f"{BASE_URL}/enheter/923609016").mock(
            return_value=httpx.Response(200, json=EQUINOR)
        )
        with TestClient(app) as rest_client:
            rest_client.get(
                "/v1/NO/company/923609016",
                headers={"X-Forwarded-For": _IP, "User-Agent": "agent-A/1.0"},
            )

            no_key = rest_client.get("/v1/stats", headers={"X-Forwarded-For": _IP})
            assert no_key.status_code == 403

            wrong_key = rest_client.get(
                "/v1/stats", params={"key": "nope"}, headers={"X-Forwarded-For": _IP}
            )
            assert wrong_key.status_code == 403

            ok = rest_client.get(
                "/v1/stats", params={"key": "test123"}, headers={"X-Forwarded-For": _IP}
            )
            assert ok.status_code == 200
            body = ok.json()
            expected = stats.summary()
            assert body["total_calls"] == expected["total_calls"] == 1
            assert body["by_surface"] == {"rest": 1}

            dashboard = rest_client.get(
                "/v1/stats/dashboard",
                params={"key": "test123"},
                headers={"X-Forwarded-For": _IP},
            )
            assert dashboard.status_code == 200
            assert dashboard.headers["content-type"].startswith("text/html")
            assert "usage dashboard" in dashboard.text.lower()

    # Neither admin route is itself part of the usage stats it reports.
    assert stats.summary()["total_calls"] == 1


def test_stats_and_dashboard_excluded_from_openapi_schema() -> None:
    """Admin/debugging routes, not part of the versioned public data API."""
    schema = app.openapi()
    assert "/v1/stats" not in schema["paths"]
    assert "/v1/stats/dashboard" not in schema["paths"]
