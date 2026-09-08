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
from registry_mcp.mcp.server import _PAYMENT_FRAUD_CAVEAT, mcp
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
TESCO_CHARGES = _load_fixture("ch_00445790_charges.json")


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


def test_server_card_lookup_company_output_schema_matches_model() -> None:
    """Review fix 5 (T30, ``REVIEW.md`` "T26f + T28 + T29"): nothing pinned
    ``static/well-known/mcp/server-card.json``'s hand-maintained
    ``outputSchema`` to ``CompanyReport`` — T17, T26c and T29 have all
    hand-edited that file, and the next model change would desynchronise it
    with nothing to catch it. Compared against
    ``dereference_refs(CompanyReport.model_json_schema())``, not the raw
    ``model_json_schema()`` — the same reasoning as
    `test_tool_output_schemas_match_models` above: that dereferenced form is
    what FastMCP actually serves, and what the card is meant to mirror.
    """
    card_path = Path(__file__).parent.parent / "static" / "well-known" / "mcp" / "server-card.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    (entry,) = [tool for tool in card["tools"] if tool["name"] == "lookup_company"]
    assert entry["outputSchema"] == dereference_refs(CompanyReport.model_json_schema())


async def test_server_card_tools_and_prompts_match_the_live_server() -> None:
    """The general-purpose sibling of the test above: that one pins one tool's
    ``outputSchema`` alone. `static/well-known/mcp/server-card.json` is hand-maintained end
    to end (T17, T26c, T29, this task's two new prompts) and nothing regenerates it from
    the live server, so every tool's name, description, annotation title and
    ``inputSchema``, and every prompt's name, description and argument list, must match
    ``tools/list``/``prompts/list`` byte for byte here — or an edit to either side (a
    docstring changed in `mcp/server.py` or `mcp/connector.py`, a prompt added or renamed,
    a `Field(description=..., examples=...)` edited on a tool argument) silently desyncs
    the one document a directory or crawler reads *without* ever calling the server
    (`~/mcp-growth/DEPTH.md` §2.1's finding that Smithery's own listing did not know about
    `search`/`fetch` is exactly this failure mode, one level up; `REVIEW.md` "D-044 wiring"
    finding 5 is the `inputSchema` half of it — the card's `lookup_company.include` had
    drifted from `_INCLUDE_DESCRIPTION`/`_INCLUDE_EXAMPLES` and this test did not catch it)."""
    card_path = Path(__file__).parent.parent / "static" / "well-known" / "mcp" / "server-card.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))

    async with Client(mcp) as client:
        live_tools = await client.list_tools()
        live_prompts = await client.list_prompts()

    card_tools = {t["name"]: t for t in card["tools"]}
    assert card_tools.keys() == {t.name for t in live_tools}
    for tool in live_tools:
        entry = card_tools[tool.name]
        assert entry["description"] == tool.description, f"{tool.name} description drifted"
        live_title = tool.annotations.title if tool.annotations else None
        assert entry["annotations"]["title"] == live_title, f"{tool.name} title drifted"
        assert entry["inputSchema"] == tool.input_schema, f"{tool.name} inputSchema drifted"

    card_prompts = {p["name"]: p for p in card["prompts"]}
    assert card_prompts.keys() == {p.name for p in live_prompts}
    for prompt in live_prompts:
        entry = card_prompts[prompt.name]
        assert entry["description"] == prompt.description, f"{prompt.name} description drifted"
        live_arguments = [
            {"name": a.name, "description": a.description, "required": a.required}
            for a in (prompt.arguments or [])
        ]
        assert entry["arguments"] == live_arguments, f"{prompt.name} arguments drifted"


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
            await client.call_tool("lookup_company", {"id": "1", "country": "ZZ"})
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
    assert codes == {"GB", "NO", "SE"}


async def test_list_countries_gb_requires_api_key() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("list_countries", {})
    rows = {row["country"]: row for row in result.structured_content["countries"]}
    assert rows["GB"]["requires_api_key"] is True
    assert rows["GB"]["api_key_env"] == "COMPANIES_HOUSE_API_KEY"
    assert rows["NO"]["requires_api_key"] is False
    assert rows["NO"]["api_key_env"] is None


async def test_list_countries_se_requires_api_key() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("list_countries", {})
    rows = {row["country"]: row for row in result.structured_content["countries"]}
    assert rows["SE"]["requires_api_key"] is True
    assert rows["SE"]["api_key_env"] == "BOLAGSVERKET_CLIENT_ID"


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


async def test_rules_resource_se_is_non_empty() -> None:
    async with Client(mcp) as client:
        contents = await client.read_resource("registry://rules/SE")
    assert len(contents) == 1
    text = contents[0].text
    assert isinstance(text, str)
    assert len(text.strip()) > 0


#: The English country name each live registry's `rules_markdown()` opens
#: with (`# Norway — ...`, `# United Kingdom — ...`, `# Sweden — ...`) — used
#: only to assert the *content* of a resource read, never to decide which
#: resources exist (that walk is `list_countries()`/`list_registries()`, per
#: `research/07-product-improvements.md` item 9).
_LIVE_COUNTRY_NAMES = {"NO": "Norway", "GB": "United Kingdom", "SE": "Sweden"}


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
    assert expected_uris == {"registry://rules/GB", "registry://rules/NO", "registry://rules/SE"}
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
            await client.read_resource("registry://rules/ZZ")
    payload = json.loads(str(excinfo.value))
    assert payload["error"]["code"] == "unsupported_country"


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


async def test_prompts_list_has_explain_counterparty_and_coverage() -> None:
    """Two prompts added alongside the pre-existing `explain_company`
    (`~/mcp-growth/DEPTH.md` §6: a job-shaped prompt is the artefact that most
    distinguishes a used server from an unused one). `DECISIONS.md` D-042(c) rules that a
    tool is bought by a distinct question and authorises zero new tools today — a prompt
    is a different MCP primitive and is not gated by that ruling, so this adds no tool and
    does not touch `test_tools_list_has_five_registry_tools_plus_two_connector_aliases`
    above."""
    async with Client(mcp) as client:
        prompts = await client.list_prompts()
    assert {p.name for p in prompts} == {
        "explain_company",
        "counterparty_check",
        "register_coverage",
    }


async def test_explain_company_prompt_renders() -> None:
    async with Client(mcp) as client:
        result = await client.get_prompt("explain_company", {"id": "923609016"})
    assert len(result.messages) >= 1
    text = result.messages[0].content.text
    assert "923609016" in text
    assert "lookup_company" in text
    assert "company_deadlines" in text


async def test_counterparty_check_prompt_renders_and_names_its_tools() -> None:
    async with Client(mcp) as client:
        result = await client.get_prompt(
            "counterparty_check", {"id": "923609016", "country": "NO"}
        )
    assert len(result.messages) >= 1
    text = result.messages[0].content.text
    assert "923609016" in text
    assert "validate_company_id" in text
    assert "lookup_company" in text
    assert "company_deadlines" in text


async def test_counterparty_check_prompt_states_what_it_does_not_establish() -> None:
    """The load-bearing caveat (`DECISIONS.md`, this task's brief, `~/mcp-growth/ADOPTION.md`
    §3): business-email-compromise fraud impersonates a real, active, correctly-registered
    supplier and forges only the bank details, so "check a supplier before you pay"
    over-promises. This prompt's own output — not just its docstring — must say plainly
    what it does not establish, every time it renders, regardless of which company was
    asked about."""
    async with Client(mcp) as client:
        result = await client.get_prompt("counterparty_check", {"id": "923609016"})
    text = result.messages[0].content.text
    assert "What this does not establish" in text
    assert "bank account or payment details" in text
    assert "not a defence against payment fraud" in text
    assert "business email compromise" in text
    assert "sanctions, PEP or adverse-media" in text


def test_instructions_state_the_payment_fraud_caveat() -> None:
    """`REVIEW.md` S-series finding 5(a): `instructions` is the string every MCP
    client puts in front of the model, and a caller who uses `lookup_company`
    directly never renders `counterparty_check` at all, so the pitch in
    `instructions` must carry the caveat too — drawn from the same module
    constant the prompt uses, so a third use cannot paraphrase it away."""
    assert mcp.instructions is not None
    assert _PAYMENT_FRAUD_CAVEAT in mcp.instructions


async def test_register_coverage_prompt_renders_and_reads_the_rules_resource() -> None:
    async with Client(mcp) as client:
        result = await client.get_prompt(
            "register_coverage", {"id": "00445790", "country": "GB"}
        )
    text = result.messages[0].content.text
    assert "00445790" in text
    assert "lookup_company" in text
    assert "registry://rules/GB" in text


async def test_register_coverage_prompt_distinguishes_structural_from_entity_nulls() -> None:
    """The honest-negatives requirement operationalised: a `null` field on a
    `CompanyReport` is not one fact, it is two (`DECISIONS.md` D-011 — `employees_reported`
    distinguishes "no figure held" from "brreg set the flag"), and this prompt must tell
    the agent to tell them apart rather than rendering every null the same way, for
    whichever country was asked about."""
    async with Client(mcp) as client:
        result = await client.get_prompt("register_coverage", {"id": "923609016"})
    text = result.messages[0].content.text
    assert "What the register states" in text
    assert "What it does not state" in text
    assert "structural" in text
    assert "entity-level" in text
    assert "employees" in text
    assert "never render a null as" in text.lower()
    # Corrected 2026-09-08 after review: the worked example used to call
    # `employees_reported: false` an entity-level gap full stop. That is true for
    # Norway, whose register publishes employee counts, and false for the UK and
    # Sweden, where neither register publishes one for anybody — a structural
    # silence, the exact collapse this prompt exists to prevent. The example must
    # therefore name the country dependence and send the agent to the rules
    # resource rather than let it infer from the field name.
    lowered = text.lower()
    assert "united kingdom" in lowered and "sweden" in lowered and "norway" in lowered
    assert "registry://rules/" in text


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


@respx.mock
def test_rest_and_mcp_lookup_company_include_charges_are_identical_gb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `include=["charges"]` path (T37 / D-042), same D-004 guarantee:
    `?include=charges` (REST) and `include=["charges"]` (MCP) attach the
    identical `charges` block, both with a `SourceRef` distinct from the
    report's own provenance."""
    monkeypatch.setenv("REGISTRY_MCP_CACHE_DISABLED", "1")
    respx.get(f"{GB_BASE_URL}/company/00445790").mock(
        return_value=httpx.Response(200, json=TESCO)
    )
    respx.get(f"{GB_BASE_URL}/company/00445790/charges").mock(
        return_value=httpx.Response(200, json=TESCO_CHARGES)
    )

    with TestClient(app) as rest_client:
        rest_body = rest_client.get(
            "/v1/GB/company/00445790",
            params={"include": "charges"},
            headers={"X-Forwarded-For": "203.0.113.98"},
        ).json()

    async def _mcp_call() -> dict[str, Any]:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "lookup_company", {"id": "00445790", "country": "GB", "include": ["charges"]}
            )
            assert result.structured_content is not None
            data: dict[str, Any] = result.structured_content
            return data

    mcp_body = anyio.run(_mcp_call)

    assert rest_body["charges"] is not None
    assert len(rest_body["charges"]["charges"]) == 9

    # `charges.provenance.fetched_at` is a *second* live timestamp — its own
    # independent moment (D-041(c)) — captured separately by REST's call and
    # MCP's call here, so it is allowed to differ by microseconds exactly
    # like the report's own `fetched_at` is; strip both before the byte-equal
    # comparison the rest of D-004's guarantee still has to satisfy.
    rest_body["charges"]["provenance"].pop("fetched_at")
    mcp_body["charges"]["provenance"].pop("fetched_at")

    volatile = {"fetched_at"}
    assert {k: v for k, v in rest_body.items() if k not in volatile} == {
        k: v for k, v in mcp_body.items() if k not in volatile
    }


@respx.mock
def test_rest_and_mcp_lookup_company_unknown_include_agree_gb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both surfaces raise the identical `bad_request` for an `include` value
    GB does not declare (D-042(d)) — never a silently empty `charges`."""
    monkeypatch.setenv("REGISTRY_MCP_CACHE_DISABLED", "1")
    respx.get(f"{GB_BASE_URL}/company/00445790").mock(
        return_value=httpx.Response(200, json=TESCO)
    )

    with TestClient(app) as rest_client:
        rest_resp = rest_client.get(
            "/v1/GB/company/00445790",
            params={"include": "officers"},
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
    assert rest_resp.status_code == 400
    rest_error = rest_resp.json()["error"]

    async def _mcp_call() -> dict[str, Any]:
        async with Client(mcp) as client:
            with pytest.raises(ToolError) as excinfo:
                await client.call_tool(
                    "lookup_company", {"id": "00445790", "country": "GB", "include": ["officers"]}
                )
            payload: dict[str, Any] = json.loads(str(excinfo.value))
            return payload

    mcp_payload = anyio.run(_mcp_call)

    assert rest_error["code"] == mcp_payload["error"]["code"] == "bad_request"
    assert rest_error["hint"] == mcp_payload["error"]["hint"]
    assert "charges" in rest_error["hint"]


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
    assert {row["country"] for row in rest_body["countries"]} == {"GB", "NO", "SE"}


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


# ---------------------------------------------------------------------------
# D-004 guarantee, Sweden (T26e fix 11 / `tasks/T26.md` §T26b): the first
# country where REST and MCP have a second thing to agree on besides
# `requires_api_key` — N10 and the `source` suffix. Appended at the end of
# the file per T26f's ground rules (nothing above this point is touched);
# everything it needs beyond the file's existing top-level imports is
# imported locally, and Bolagsverket credentials are set inline rather than
# through a new autouse fixture.
# ---------------------------------------------------------------------------


@respx.mock
def test_rest_and_mcp_lookup_company_are_identical_se(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same D-004 guarantee as `test_rest_and_mcp_lookup_company_are_identical_gb`,
    for Sweden. Bolagsverket needs two upstream calls (token, then data)
    where NO/GB need one, so both are mocked here directly rather than
    reusing this file's NO/GB-only fixtures/constants above."""
    from registry_mcp.registries.se import client as se_client_module

    monkeypatch.setenv("REGISTRY_MCP_CACHE_DISABLED", "1")
    monkeypatch.setenv("BOLAGSVERKET_CLIENT_ID", "test-client-id-should-never-leak")
    monkeypatch.setenv("BOLAGSVERKET_CLIENT_SECRET", "test-client-secret-should-never-leak")
    monkeypatch.delenv("BOLAGSVERKET_ENVIRONMENT", raising=False)
    se_client_module._client = None
    se_client_module._tokens.clear()

    se_fixtures = Path(__file__).parent / "fixtures"
    token_body = json.loads((se_fixtures / "bv_token.json").read_text(encoding="utf-8"))
    ab_active = json.loads((se_fixtures / "bv_ab_active.json").read_text(encoding="utf-8"))

    respx.post("https://portal.api.bolagsverket.se/oauth2/token").mock(
        return_value=httpx.Response(200, json=token_body)
    )
    respx.post("https://gw.api.bolagsverket.se/vardefulla-datamangder/v1/organisationer").mock(
        return_value=httpx.Response(200, json=ab_active)
    )

    try:
        with TestClient(app) as rest_client:
            rest_body = rest_client.get(
                "/v1/SE/company/5299999994", headers={"X-Forwarded-For": "203.0.113.95"}
            ).json()

        async def _mcp_call() -> dict[str, Any]:
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "lookup_company", {"id": "5299999994", "country": "SE"}
                )
                assert result.structured_content is not None
                data: dict[str, Any] = result.structured_content
                return data

        mcp_body = anyio.run(_mcp_call)

        # `fetched_at` is a live timestamp captured independently by each
        # call; every other field must match byte for byte (D-004).
        volatile = {"fetched_at"}
        assert {k: v for k, v in rest_body.items() if k not in volatile} == {
            k: v for k, v in mcp_body.items() if k not in volatile
        }
    finally:
        anyio.run(se_client_module.aclose)


# ---------------------------------------------------------------------------
# `company_deadlines`' `include` argument (T44, D-043(j), D-045(g)) — same
# credential/cache setup as the SE test just above, for the same reason.
# ---------------------------------------------------------------------------


def _se_deadlines_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    from registry_mcp.registries.se import client as se_client_module

    monkeypatch.setenv("REGISTRY_MCP_CACHE_DISABLED", "1")
    monkeypatch.setenv("BOLAGSVERKET_CLIENT_ID", "test-client-id-should-never-leak")
    monkeypatch.setenv("BOLAGSVERKET_CLIENT_SECRET", "test-client-secret-should-never-leak")
    monkeypatch.delenv("BOLAGSVERKET_ENVIRONMENT", raising=False)
    se_client_module._client = None
    se_client_module._tokens.clear()
    return se_client_module


@respx.mock
def test_company_deadlines_include_filings_se_december_is_confirmed_and_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`tasks/T44.md`'s test 1, the December half: `include=["filings"]`
    reads a real recorded document list (`bv_dokumentlista.json`, three
    reports, newest period ending 2022-12-31) through the live MCP tool and
    the dates do not move — D-041(e)'s invariant, now proven through the
    actual surface rather than only `deadlines_for` directly — while
    `applies_because` switches from an assumption to a confirmation."""
    se_client_module = _se_deadlines_env(monkeypatch)
    token_body = json.loads((FIXTURES / "bv_token.json").read_text(encoding="utf-8"))
    ab_active = json.loads((FIXTURES / "bv_ab_active.json").read_text(encoding="utf-8"))
    dokumentlista = json.loads((FIXTURES / "bv_dokumentlista.json").read_text(encoding="utf-8"))

    respx.post("https://portal.api.bolagsverket.se/oauth2/token").mock(
        return_value=httpx.Response(200, json=token_body)
    )
    respx.post("https://gw.api.bolagsverket.se/vardefulla-datamangder/v1/organisationer").mock(
        return_value=httpx.Response(200, json=ab_active)
    )
    respx.post("https://gw.api.bolagsverket.se/vardefulla-datamangder/v1/dokumentlista").mock(
        return_value=httpx.Response(200, json=dokumentlista)
    )

    try:

        async def _call(include: list[str]) -> dict[str, Any]:
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "company_deadlines",
                    {
                        "id": "5299999994",
                        "country": "SE",
                        "today": "2026-03-01",
                        "include": include,
                    },
                )
                assert result.structured_content is not None
                data: dict[str, Any] = result.structured_content
                return data

        without = anyio.run(_call, [])
        with_filings = anyio.run(_call, ["filings"])
        assert [d["due_date"] for d in with_filings["deadlines"]] == [
            d["due_date"] for d in without["deadlines"]
        ]
        annual_accounts = next(
            d for d in with_filings["deadlines"] if d["kind"] == "annual_accounts"
        )
        assert "Confirmed, not a guess" in annual_accounts["applies_because"]
        assert "2022-12-31" in annual_accounts["applies_because"]
        assert "registered 2023-06-27" in annual_accounts["applies_because"]
        assert "assum" not in annual_accounts["applies_because"].lower()
    finally:
        anyio.run(se_client_module.aclose)


@respx.mock
def test_rest_and_mcp_company_deadlines_include_filings_are_identical_se(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The D-004 guarantee for the new argument (`tasks/T44.md`'s test 5):
    `?include=filings` (REST) and `include=["filings"]` (MCP) must produce
    byte-identical `DeadlineReport` documents."""
    se_client_module = _se_deadlines_env(monkeypatch)
    token_body = json.loads((FIXTURES / "bv_token.json").read_text(encoding="utf-8"))
    ab_active = json.loads((FIXTURES / "bv_ab_active.json").read_text(encoding="utf-8"))
    dokumentlista = json.loads((FIXTURES / "bv_dokumentlista.json").read_text(encoding="utf-8"))

    respx.post("https://portal.api.bolagsverket.se/oauth2/token").mock(
        return_value=httpx.Response(200, json=token_body)
    )
    respx.post("https://gw.api.bolagsverket.se/vardefulla-datamangder/v1/organisationer").mock(
        return_value=httpx.Response(200, json=ab_active)
    )
    respx.post("https://gw.api.bolagsverket.se/vardefulla-datamangder/v1/dokumentlista").mock(
        return_value=httpx.Response(200, json=dokumentlista)
    )

    try:
        with TestClient(app) as rest_client:
            rest_body = rest_client.get(
                "/v1/SE/company/5299999994/deadlines",
                params={"today": "2026-03-01", "include": "filings"},
                headers={"X-Forwarded-For": "203.0.113.94"},
            ).json()

        async def _mcp_call() -> dict[str, Any]:
            async with Client(mcp) as client:
                result = await client.call_tool(
                    "company_deadlines",
                    {
                        "id": "5299999994",
                        "country": "SE",
                        "today": "2026-03-01",
                        "include": ["filings"],
                    },
                )
                assert result.structured_content is not None
                data: dict[str, Any] = result.structured_content
                return data

        mcp_body = anyio.run(_mcp_call)
        assert rest_body == mcp_body
    finally:
        anyio.run(se_client_module.aclose)


async def test_company_deadlines_unknown_include_is_bad_request_naming_filings_only() -> None:
    """`tasks/T44.md`'s tests 3-4, through the live tool rather than
    `Registry.deadline_report_with` directly: `company_deadlines` rejects an
    `include` value `lookup_company` would accept for the same country
    (Norway declares `financials`) before any upstream request, naming only
    the deadline operation's own allowed set."""
    async with Client(mcp) as client:
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool(
                "company_deadlines",
                {"id": "923609016", "country": "NO", "include": ["financials"]},
            )
    payload = json.loads(str(excinfo.value))
    assert payload["error"]["code"] == "bad_request"
    assert payload["error"]["details"]["allowed"] == ["filings"]
    assert "financials" not in payload["error"]["hint"]


@respx.mock
def test_rest_and_mcp_company_deadlines_unknown_include_agree_no() -> None:
    """REST≡MCP parity on the rejection path too — no upstream request is
    registered here at all, and none should be attempted."""
    with TestClient(app) as rest_client:
        rest_resp = rest_client.get(
            "/v1/NO/company/923609016/deadlines",
            params={"include": "financials"},
            headers={"X-Forwarded-For": "203.0.113.93"},
        )
    assert rest_resp.status_code == 400
    rest_error = rest_resp.json()["error"]

    async def _mcp_call() -> dict[str, Any]:
        async with Client(mcp) as client:
            with pytest.raises(ToolError) as excinfo:
                await client.call_tool(
                    "company_deadlines",
                    {"id": "923609016", "country": "NO", "include": ["financials"]},
                )
            payload: dict[str, Any] = json.loads(str(excinfo.value))
            return payload

    mcp_error = anyio.run(_mcp_call)["error"]
    assert rest_error["code"] == mcp_error["code"] == "bad_request"
    assert rest_error["details"] == mcp_error["details"]


# ---------------------------------------------------------------------------
# D-040 — a personal identifier never reaches the usage log
# ---------------------------------------------------------------------------


class _RecordSpy:
    """Stand-in for `record_call`: records every call's keyword arguments so a
    test can assert on exactly what `_call_context` tried to log, with no
    SQLite file in the loop at all."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


@pytest.fixture
def record_spy(monkeypatch: pytest.MonkeyPatch) -> _RecordSpy:
    spy = _RecordSpy()
    monkeypatch.setattr("registry_mcp.mcp.server.record_call", spy)
    return spy


async def test_se_lookup_without_credentials_logs_no_identifier(
    record_spy: _RecordSpy, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Swedish sole trader's identifier is a personnummer (D-040). Even a
    failed lookup — no Bolagsverket credentials configured, so `lookup` raises
    `upstream_error` before any socket opens — must never pass it to
    `record_call`."""
    monkeypatch.delenv("BOLAGSVERKET_CLIENT_ID", raising=False)
    monkeypatch.delenv("BOLAGSVERKET_CLIENT_SECRET", raising=False)

    async with Client(mcp) as client:
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool(
                "lookup_company", {"id": "194009272719", "country": "SE"}
            )
    payload = json.loads(str(excinfo.value))
    assert payload["error"]["code"] == "upstream_error"
    assert record_spy.calls, "record_call was never invoked"
    last = record_spy.calls[-1]
    assert last["country"] == "SE"
    assert last["query"] is None


async def test_se_deadlines_without_credentials_logs_no_identifier(
    record_spy: _RecordSpy, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`company_deadlines` looks the entity up first, so it fails — and must
    log — the same way `lookup_company` does with no credentials."""
    monkeypatch.delenv("BOLAGSVERKET_CLIENT_ID", raising=False)
    monkeypatch.delenv("BOLAGSVERKET_CLIENT_SECRET", raising=False)

    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool(
                "company_deadlines", {"id": "194009272719", "country": "SE"}
            )
    assert record_spy.calls, "record_call was never invoked"
    last = record_spy.calls[-1]
    assert last["country"] == "SE"
    assert last["query"] is None


async def test_se_validate_logs_no_identifier(record_spy: _RecordSpy) -> None:
    """`validate_company_id` never touches the network, but the identifier is
    still a personnummer — D-040(d)'s blanket-by-country rule does not care
    whether a call happened to reach the register."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "validate_company_id", {"id": "194009272719", "country": "SE"}
        )
    assert result.structured_content is not None
    assert record_spy.calls, "record_call was never invoked"
    last = record_spy.calls[-1]
    assert last["country"] == "SE"
    assert last["query"] is None


@respx.mock
async def test_no_lookup_still_logs_the_real_identifier(record_spy: _RecordSpy) -> None:
    """Regression: D-040 flags Sweden only (today) — a Norwegian orgnr is a
    company number, not a natural person's, and must keep reaching the log
    unchanged."""
    respx.get(f"{BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )

    async with Client(mcp) as client:
        result = await client.call_tool("lookup_company", {"id": "923609016"})
    assert result.structured_content is not None
    assert record_spy.calls, "record_call was never invoked"
    last = record_spy.calls[-1]
    assert last["country"] == "NO"
    assert last["query"] == "923609016"


# ---------------------------------------------------------------------------
# An internal error is not a successful call (`REVIEW.md` S-series finding 6,
# `mcp/server.py` half — the `core/registry.py` half is T42's).
# ---------------------------------------------------------------------------


async def test_tool_body_runtime_error_is_recorded_ok_false_and_still_raises(
    record_spy: _RecordSpy, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_CallOutcome.ok` used to default `True`, and only `except RegistryError`
    ever set it `False` — so a tool body that raised anything else (an internal
    bug, not a registry failure) was logged to the usage table as a *successful*
    call. `_call_context` must now record `ok=False` for any exception, not just
    `RegistryError`, and the exception must still propagate to the caller
    unchanged (here, as FastMCP's own bare `ToolError`)."""

    class _BoomRegistry:
        async def lookup_with(self, id: str, include: object) -> Any:
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "registry_mcp.mcp.server.get_registry", lambda country: _BoomRegistry()
    )

    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool(
                "lookup_company", {"id": "923609016", "country": "NO"}
            )
    assert record_spy.calls, "record_call was never invoked"
    last = record_spy.calls[-1]
    assert last["ok"] is False
