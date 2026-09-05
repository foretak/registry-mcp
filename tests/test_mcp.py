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
from fastmcp.utilities.json_schema import dereference_refs

from registry_mcp.api.main import app
from registry_mcp.core.models import (
    CompanyReport,
    CountriesResponse,
    DeadlineReport,
    SearchResult,
    ValidationResult,
)
from registry_mcp.core.registry import list_countries, list_registries
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


async def test_tools_list_has_five_registry_tools_plus_two_connector_aliases() -> None:
    """`DECISIONS.md` D-031 amends the tool count: five registry tools (unchanged) plus
    two ChatGPT connector aliases, `search`/`fetch` (`mcp/connector.py`) — "five tools"
    becomes "seven tools", not "a sixth registry tool"."""
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert {t.name for t in tools} == {
        "lookup_company",
        "search_company",
        "company_deadlines",
        "validate_company_id",
        "list_countries",
        "search",
        "fetch",
    }


_DEGENERATE_OUTPUT_SCHEMA = {"type": "object", "additionalProperties": True}


async def test_tool_output_schemas_match_models() -> None:
    """Backlog item 1 (`research/07-product-improvements.md` #2): every tool's
    `outputSchema` must be the real JSON Schema of the pydantic model it
    returns, not FastMCP's degenerate default inference over `dict[str, Any]`.

    Compared against ``dereference_refs(Model.model_json_schema())``, not the
    raw ``model_json_schema()``: FastMCP's ``DereferenceRefsMiddleware`` is on
    by default (`FastMCP(dereference_schemas=True)`, for client compatibility
    — VS Code Copilot is named in its own docstring) and inlines every
    `$ref`/`$defs` in every tool's `outputSchema` before it reaches
    `tools/list`, verified directly against the raw stdio wire bytes. That
    inlining is semantics-preserving and deliberately not disabled here (the
    README's new one-click VS Code badges depend on the same compatibility
    this middleware buys), so the model's own schema is compared the same
    way any real client actually receives it.
    """
    expected = {
        "lookup_company": dereference_refs(CompanyReport.model_json_schema()),
        "search_company": dereference_refs(SearchResult.model_json_schema()),
        "company_deadlines": dereference_refs(DeadlineReport.model_json_schema()),
        "validate_company_id": dereference_refs(ValidationResult.model_json_schema()),
        "list_countries": dereference_refs(CountriesResponse.model_json_schema()),
    }
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    # Subset, not equality: `mcp/connector.py`'s `search`/`fetch` (D-031) also register
    # on this same server and are covered by their own tests in `test_connector.py`,
    # not duplicated here — this test's job is only the five registry tools' schemas.
    assert expected.keys() <= tools.keys()
    for name, schema in expected.items():
        output_schema = tools[name].output_schema
        assert output_schema is not None, f"{name} has no outputSchema"
        assert output_schema != _DEGENERATE_OUTPUT_SCHEMA, f"{name} is still degenerate"
        assert output_schema == schema, f"{name} outputSchema does not match its model"


async def test_tool_annotations() -> None:
    """Backlog item 2: all five tools are read-only, non-destructive and
    idempotent; the three that call a national register are `openWorldHint`
    True, the two that do no network I/O are False."""
    open_world = {"lookup_company", "search_company", "company_deadlines"}
    closed_world = {"validate_company_id", "list_countries"}
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    for name in open_world | closed_world:
        annotations = tools[name].annotations
        assert annotations is not None, f"{name} has no annotations"
        assert annotations.read_only_hint is True
        assert annotations.destructive_hint is False
        assert annotations.idempotent_hint is True
        assert annotations.open_world_hint is (name in open_world)
        assert annotations.title  # explicit, non-empty — not the auto-derived default


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
    body = result.structured_content
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
    body = result.structured_content
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
    body = result.structured_content
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
    body = result.structured_content
    assert body["valid"] is False
    assert body["normalized"] is None
    assert body["hint"]


async def test_validate_company_id_valid() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("validate_company_id", {"id": "923609016"})
    body = result.structured_content
    assert body["valid"] is True
    assert body["normalized"] == "923609016"
    assert body["formatted"] == "923 609 016"


# ---------------------------------------------------------------------------
# list_countries
# ---------------------------------------------------------------------------


async def test_list_countries_hides_stub() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("list_countries", {})
    codes = {row["country"] for row in result.structured_content["countries"]}
    assert codes == {"GB", "NO"}


async def test_list_countries_gb_requires_api_key() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("list_countries", {})
    rows = {row["country"]: row for row in result.structured_content["countries"]}
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


#: The English country name each live registry's `rules_markdown()` opens
#: with (`# Norway — ...`, `# United Kingdom — ...`) — used only to assert
#: the *content* of a resource read, never to decide which resources exist
#: (that walk is `list_countries()`/`list_registries()`, per
#: `research/07-product-improvements.md` item 9).
_LIVE_COUNTRY_NAMES = {"NO": "Norway", "GB": "United Kingdom"}


async def test_resources_list_shows_concrete_rules_resource_per_live_country() -> None:
    """Item 9: a `@mcp.resource("registry://rules/{country}")` *template*
    (`rules_resource` above) never appears in `resources/list` — only in
    `resources/templates/list` — so a client that calls `resources/list` and
    nothing else never learned this resource existed. `mcp/server.py`
    registers one concrete resource per `list_registries()` row at import
    time; this asserts both live countries show up there, with no country
    hard-coded on either side of the check."""
    async with Client(mcp) as client:
        resources = await client.list_resources()
    by_uri = {str(r.uri): r for r in resources}
    expected_uris = {f"registry://rules/{cc}" for cc in list_countries()}
    assert expected_uris == {"registry://rules/GB", "registry://rules/NO"}
    assert set(by_uri) == expected_uris
    for cc in list_countries():
        row = by_uri[f"registry://rules/{cc}"]
        assert row.title
        assert row.description


async def test_resources_templates_list_still_has_the_general_pattern() -> None:
    """The concrete resources are additive — the template a country not yet
    imported would still match stays advertised."""
    async with Client(mcp) as client:
        templates = await client.list_resource_templates()
    assert any(str(t.uri_template) == "registry://rules/{country}" for t in templates)


async def test_concrete_rules_resources_read_non_empty_and_name_the_country() -> None:
    """Reading each concrete resource returns the same non-empty markdown the
    template serves, naming the country in plain English — not just its
    ISO code or the registry's own local name."""
    async with Client(mcp) as client:
        for registry in list_registries():
            contents = await client.read_resource(f"registry://rules/{registry.country}")
            assert len(contents) == 1
            text = contents[0].text
            assert isinstance(text, str)
            assert len(text.strip()) > 0
            assert _LIVE_COUNTRY_NAMES[registry.country] in text


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
            assert result.structured_content is not None
            data: dict[str, Any] = result.structured_content
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
            assert result.structured_content is not None
            data: dict[str, Any] = result.structured_content
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
            assert result.structured_content is not None
            data: dict[str, Any] = result.structured_content
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
