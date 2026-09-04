"""Tests for `mcp/server.py` (T07).

Uses `fastmcp.Client` in-process against the server object (`mcp/server.py`'s
`mcp`), with the Norwegian registry's HTTP mocked with `respx` against
`tests/fixtures/brreg_923609016.json` — the same pattern `tests/test_api.py`
(T06) and `tests/test_client_no.py` (T03) use.

`test_rest_and_mcp_lookup_company_are_identical` is the D-004 guarantee
itself: REST and MCP must emit the same `CompanyReport` JSON for the same
fixture.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import anyio
import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.exceptions import ToolError

from registry_mcp.api.main import app
from registry_mcp.mcp.server import mcp
from registry_mcp.registries.gb import client as gb_client_module
from registry_mcp.registries.no import client as client_module

FIXTURES = Path(__file__).parent / "fixtures"
BASE_URL = client_module.BASE_URL
GB_BASE_URL = gb_client_module.BASE_URL


def _load_fixture(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return result


EQUINOR = _load_fixture("brreg_923609016.json")
TESCO = _load_fixture("ch_00445790.json")


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_PATH", str(tmp_path / "cache.sqlite3"))
    monkeypatch.delenv("REGISTRY_MCP_CACHE_DISABLED", raising=False)
    monkeypatch.delenv("REGISTRY_MCP_CACHE_TTL_SECONDS", raising=False)
    yield


@pytest.fixture(autouse=True)
async def _reset_http_client() -> AsyncIterator[None]:
    client_module._client = None
    gb_client_module._client = None
    yield
    await client_module.aclose()
    await gb_client_module.aclose()


@pytest.fixture(autouse=True)
def _gb_api_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "test-key-for-mcp-tests")
    yield


# ---------------------------------------------------------------------------
# Server shape
# ---------------------------------------------------------------------------


async def test_tools_list_has_exactly_five_tools() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert {t.name for t in tools} == {
        "lookup_company",
        "search_company",
        "company_deadlines",
        "validate_company_id",
        "list_countries",
    }


# ---------------------------------------------------------------------------
# lookup_company
# ---------------------------------------------------------------------------


@respx.mock
async def test_lookup_company_returns_company_report() -> None:
    respx.get(f"{BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )
    async with Client(mcp) as client:
        result = await client.call_tool("lookup_company", {"id": "923609016"})
    body = result.data
    assert body["name"] == "EQUINOR ASA"
    assert body["id"] == "923609016"
    assert body["country"] == "NO"
    assert body["registry"] == "brreg"


async def test_lookup_company_unsupported_country_is_json_error() -> None:
    async with Client(mcp) as client:
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool("lookup_company", {"id": "1", "country": "SE"})
    payload = json.loads(str(excinfo.value))
    assert payload["error"]["code"] == "unsupported_country"
    assert payload["error"]["hint"]


# ---------------------------------------------------------------------------
# search_company
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_company_returns_search_result() -> None:
    envelope = {
        "_embedded": {"enheter": [EQUINOR]},
        "page": {"size": 1, "totalElements": 1, "totalPages": 1, "number": 0},
    }
    respx.get(f"{BASE_URL}/enheter").mock(return_value=httpx.Response(200, json=envelope))
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_company", {"name": "equinor", "limit": 1}
        )
    body = result.data
    assert body["total"] == 1
    assert body["hits"][0]["id"] == "923609016"
    assert body["hint"]


# ---------------------------------------------------------------------------
# company_deadlines
# ---------------------------------------------------------------------------


@respx.mock
async def test_company_deadlines_returns_deadline_report_shape() -> None:
    respx.get(f"{BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "company_deadlines", {"id": "923609016", "today": "2026-01-15"}
        )
    body = result.data
    assert body["today"] == "2026-01-15"
    assert body["company_id"] == "923609016"
    assert body["company_name"] == "EQUINOR ASA"
    assert isinstance(body["deadlines"], list)
    assert len(body["deadlines"]) > 0
    assert isinstance(body["notes"], list)


async def test_company_deadlines_bad_today_is_json_error() -> None:
    async with Client(mcp) as client:
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool(
                "company_deadlines", {"id": "923609016", "today": "not-a-date"}
            )
    payload = json.loads(str(excinfo.value))
    assert payload["error"]["code"] == "bad_request"


# ---------------------------------------------------------------------------
# validate_company_id
# ---------------------------------------------------------------------------


async def test_validate_company_id_invalid_has_hint_not_error() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("validate_company_id", {"id": "833286602"})
    body = result.data
    assert body["valid"] is False
    assert body["normalized"] is None
    assert body["hint"]


async def test_validate_company_id_valid() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("validate_company_id", {"id": "923609016"})
    body = result.data
    assert body["valid"] is True
    assert body["normalized"] == "923609016"
    assert body["formatted"] == "923 609 016"


# ---------------------------------------------------------------------------
# list_countries
# ---------------------------------------------------------------------------


async def test_list_countries_hides_stub() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("list_countries", {})
    codes = {row["country"] for row in result.data["countries"]}
    assert codes == {"GB", "NO"}


async def test_list_countries_gb_requires_api_key() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("list_countries", {})
    rows = {row["country"]: row for row in result.data["countries"]}
    assert rows["GB"]["requires_api_key"] is True
    assert rows["GB"]["api_key_env"] == "COMPANIES_HOUSE_API_KEY"
    assert rows["NO"]["requires_api_key"] is False
    assert rows["NO"]["api_key_env"] is None


# ---------------------------------------------------------------------------
# Resource
# ---------------------------------------------------------------------------


async def test_rules_resource_no_is_non_empty() -> None:
    async with Client(mcp) as client:
        contents = await client.read_resource("registry://rules/NO")
    assert len(contents) == 1
    text = contents[0].text
    assert isinstance(text, str)
    assert len(text.strip()) > 0


async def test_rules_resource_gb_is_non_empty() -> None:
    async with Client(mcp) as client:
        contents = await client.read_resource("registry://rules/GB")
    assert len(contents) == 1
    text = contents[0].text
    assert isinstance(text, str)
    assert len(text.strip()) > 0


async def test_rules_resource_unsupported_country_is_json_error() -> None:
    # A resource error crosses the wire as a standard JSON-RPC error, so the
    # client-side exception is `mcp.shared.exceptions.MCPError`, not
    # `fastmcp.exceptions.ResourceError` (that one is raised server-side, see
    # `mcp/server.py::_resource_error`) — but `str(exc)` still round-trips the
    # same `{"error": {...}}` text raised there, same as a tool error.
    from mcp.shared.exceptions import MCPError

    async with Client(mcp) as client:
        with pytest.raises(MCPError) as excinfo:
            await client.read_resource("registry://rules/SE")
    payload = json.loads(str(excinfo.value))
    assert payload["error"]["code"] == "unsupported_country"


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


async def test_explain_company_prompt_renders() -> None:
    async with Client(mcp) as client:
        result = await client.get_prompt("explain_company", {"id": "923609016"})
    assert len(result.messages) >= 1
    text = result.messages[0].content.text
    assert "923609016" in text
    assert "lookup_company" in text
    assert "company_deadlines" in text


# ---------------------------------------------------------------------------
# D-004 guarantee: REST and MCP must emit the same CompanyReport JSON.
# ---------------------------------------------------------------------------


@respx.mock
def test_rest_and_mcp_lookup_company_are_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    # Disable the shared SQLite cache so both surfaces do an independent, fresh
    # fetch against the same mocked upstream — otherwise the second call would
    # be a cache hit and `cached` would legitimately differ between the two.
    monkeypatch.setenv("REGISTRY_MCP_CACHE_DISABLED", "1")
    respx.get(f"{BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )

    with TestClient(app) as rest_client:
        rest_body = rest_client.get(
            "/v1/NO/company/923609016", headers={"X-Forwarded-For": "203.0.113.99"}
        ).json()

    async def _mcp_call() -> dict[str, Any]:
        async with Client(mcp) as client:
            result = await client.call_tool("lookup_company", {"id": "923609016"})
            data: dict[str, Any] = result.data
            return data

    mcp_body = anyio.run(_mcp_call)

    # `fetched_at` is a live timestamp captured independently by each call and
    # is allowed to differ by microseconds; every other field must match byte
    # for byte, which is the actual D-004 guarantee.
    volatile = {"fetched_at"}
    assert {k: v for k, v in rest_body.items() if k not in volatile} == {
        k: v for k, v in mcp_body.items() if k not in volatile
    }


@respx.mock
def test_rest_and_mcp_lookup_company_are_identical_gb(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same D-004 guarantee as `test_rest_and_mcp_lookup_company_are_identical`,
    for the second country — the one whose surfaces have a second thing to
    agree on (`requires_api_key`), and whose cache stores a different payload
    shape internally (`registries/gb/client.py`'s raw-JSON cache)."""
    monkeypatch.setenv("REGISTRY_MCP_CACHE_DISABLED", "1")
    respx.get(f"{GB_BASE_URL}/company/00445790").mock(
        return_value=httpx.Response(200, json=TESCO)
    )

    with TestClient(app) as rest_client:
        rest_body = rest_client.get(
            "/v1/GB/company/00445790", headers={"X-Forwarded-For": "203.0.113.97"}
        ).json()

    async def _mcp_call() -> dict[str, Any]:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "lookup_company", {"id": "00445790", "country": "GB"}
            )
            data: dict[str, Any] = result.data
            return data

    mcp_body = anyio.run(_mcp_call)

    volatile = {"fetched_at"}
    assert {k: v for k, v in rest_body.items() if k not in volatile} == {
        k: v for k, v in mcp_body.items() if k not in volatile
    }


def test_rest_and_mcp_list_countries_are_identical() -> None:
    """`DECISIONS.md` D-012: `CountriesResponse`/`Registry.country_info()` is
    the one shared builder behind both `GET /v1/countries` and the MCP
    `list_countries` tool — before D-012 each surface re-derived this
    envelope on its own (REST through a private model that silently dropped
    an unrecognised key, MCP by passing the raw `describe()` dict through),
    a latent divergence with no test to catch it."""
    with TestClient(app) as rest_client:
        rest_body = rest_client.get(
            "/v1/countries", headers={"X-Forwarded-For": "203.0.113.98"}
        ).json()

    async def _mcp_call() -> dict[str, Any]:
        async with Client(mcp) as client:
            result = await client.call_tool("list_countries", {})
            data: dict[str, Any] = result.data
            return data

    mcp_body = anyio.run(_mcp_call)
    assert rest_body == mcp_body
    assert {row["country"] for row in rest_body["countries"]} == {"GB", "NO"}


# ---------------------------------------------------------------------------
# `/mcp` mount: both trailing-slash variants must serve directly, no 307.
#
# `fastmcp.Client`'s Streamable HTTP transport does not follow a POST
# redirect, and every URL this project advertises (`server.json`, `llms.txt`,
# README, articles) is `/mcp` with no trailing slash — so a 307 here would
# silently break every agent configured against the advertised URL
# (`deploy.md`'s T13 "Corrections found while verifying" note).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/mcp", "/mcp/"])
def test_mcp_mount_has_no_trailing_slash_redirect(path: str) -> None:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "0"},
        },
    }
    with TestClient(app, follow_redirects=False) as rest_client:
        resp = rest_client.post(
            path,
            json=body,
            headers={"accept": "application/json, text/event-stream"},
        )
    assert resp.status_code != 307
    assert resp.status_code == 200
