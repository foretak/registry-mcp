"""Tests for `mcp/connector.py` — the ChatGPT connector aliases `search`/`fetch`
(`DECISIONS.md` D-031, `CONNECTOR_SPEC.md`).

Same in-process `fastmcp.Client` + `respx` pattern as `tests/test_mcp.py`, against the
same committed fixtures `tests/test_mcp.py`/`evals/cases.json` use — `E27`-`E31` in
`evals/cases.json` re-run these same scenarios end to end through `evals/run.py
--golden`; these tests isolate `connector.py`'s own logic (row construction, the
identifier short-circuit, country derivation, `text` rendering, id parsing) with finer
assertions than a golden-mode case's `checks` list is meant to carry.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from fastmcp import Client
from fastmcp.exceptions import ToolError
from fastmcp.utilities.json_schema import dereference_refs

from registry_mcp.core.models import CompanyReport, DeadlineReport
from registry_mcp.mcp.connector import ConnectorDocument, ConnectorSearchResponse
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


def _mock_no_search_empty() -> None:
    respx.get(f"{BASE_URL}/enheter").mock(
        return_value=httpx.Response(200, json={"page": {"totalElements": 0}})
    )


def _mock_gb_search_empty() -> None:
    respx.get(f"{GB_BASE_URL}/search/companies").mock(
        return_value=httpx.Response(200, json=_load_fixture("ch_search_empty.json"))
    )


def _mock_no_search_equinor() -> None:
    envelope = {
        "_embedded": {"enheter": [EQUINOR]},
        "page": {"size": 1, "totalElements": 1, "totalPages": 1, "number": 0},
    }
    respx.get(f"{BASE_URL}/enheter").mock(return_value=httpx.Response(200, json=envelope))


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
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "test-key-for-connector-tests")
    yield


# ---------------------------------------------------------------------------
# Server shape: registration, schemas, annotations
# ---------------------------------------------------------------------------


async def test_connector_tools_are_registered_alongside_the_five() -> None:
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert {"search", "fetch"} <= tools.keys()
    assert len(tools) == 7


async def test_connector_output_schemas_match_the_wire_models() -> None:
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert tools["search"].output_schema == dereference_refs(
        ConnectorSearchResponse.model_json_schema()
    )
    assert tools["fetch"].output_schema == dereference_refs(ConnectorDocument.model_json_schema())


async def test_connector_annotations_and_titles() -> None:
    """D-031(e): same `_READ_EXTERNAL` annotation set as the five open-world tools, plus
    the exact titles D-031(e) specifies verbatim."""
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    for name in ("search", "fetch"):
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
        assert annotations.destructive_hint is False
        assert annotations.idempotent_hint is True
        assert annotations.open_world_hint is True
    assert tools["search"].annotations.title == (
        "Find a company (ChatGPT connector alias for search_company)"
    )
    assert tools["fetch"].annotations.title == (
        "Fetch one company record (ChatGPT connector alias for lookup_company)"
    )


async def test_connector_descriptions_open_by_naming_the_preferred_tool() -> None:
    """D-031(e): each description's first sentence — the tool-search retrieval key —
    names itself an alias and names the tool a non-ChatGPT client should prefer."""
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert (tools["search"].description or "").startswith(
        "ChatGPT connector alias; other clients should prefer `search_company`"
    )
    assert (tools["fetch"].description or "").startswith(
        "ChatGPT connector alias; other clients should prefer `lookup_company`"
    )


@pytest.mark.parametrize("tool_name,arguments", [("search", {"query": "Equinor"}), ("fetch", {"id": "NO:923609016"})])
@respx.mock
async def test_structured_content_and_text_mirror_carry_the_same_object(
    tool_name: str, arguments: dict[str, Any]
) -> None:
    """Done-check #4: OpenAI requires both `structuredContent` and a JSON-encoded
    `content[0].text` mirror carrying the *same* object — verified here by inspection of
    an actual response, not assumed from FastMCP's documented behaviour."""
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    _mock_no_search_equinor()
    _mock_gb_search_empty()
    async with Client(mcp) as client:
        result = await client.call_tool(tool_name, arguments)
    assert result.structured_content is not None
    assert len(result.content) >= 1
    text_block = result.content[0]
    assert json.loads(text_block.text) == result.structured_content


# ---------------------------------------------------------------------------
# search — identifier short-circuit
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_identifier_short_circuits_to_one_lookup_no_search_issued() -> None:
    """Mirrors `evals/cases.json` E28: neither country's *search* route is mocked, so a
    fan-out to name search (instead of stopping at the identifier short-circuit) would
    raise, failing this test."""
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    async with Client(mcp) as client:
        result = await client.call_tool("search", {"query": "923609016"})
    rows = result.structured_content["results"]
    assert len(rows) == 1
    assert rows[0]["id"] == "NO:923609016"
    assert rows[0]["url"] == "https://api.foretak.dev/v1/NO/company/923609016"
    assert "EQUINOR ASA" in rows[0]["title"]


@respx.mock
async def test_fetch_round_trips_an_identifier_search_result_id() -> None:
    """Done-check #3: `fetch(search(q).results[0].id)` must round-trip for an
    identifier query too, not only a name query."""
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    async with Client(mcp) as client:
        search_result = await client.call_tool("search", {"query": "923609016"})
        hit_id = search_result.structured_content["results"][0]["id"]
        assert hit_id == "NO:923609016"
        fetch_result = await client.call_tool("fetch", {"id": hit_id})
    assert fetch_result.structured_content["id"] == hit_id


@respx.mock
async def test_search_identifier_with_explicit_country_token_still_short_circuits() -> None:
    """A country token narrows the candidate set (D-031(c)) before the identifier check
    runs; GB's routes are deliberately unmocked here to prove GB was never asked."""
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    async with Client(mcp) as client:
        result = await client.call_tool("search", {"query": "NO 923609016"})
    rows = result.structured_content["results"]
    assert len(rows) == 1
    assert rows[0]["id"] == "NO:923609016"


@respx.mock
async def test_search_empty_query_is_bad_request() -> None:
    async with Client(mcp) as client:
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool("search", {"query": "   "})
    payload = json.loads(str(excinfo.value))
    assert payload["error"]["code"] == "bad_request"
    assert payload["error"]["hint"]


# ---------------------------------------------------------------------------
# search — name search fan-out
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_name_fans_out_and_a_country_with_no_hits_drops_silently() -> None:
    _mock_no_search_equinor()
    _mock_gb_search_empty()
    async with Client(mcp) as client:
        result = await client.call_tool("search", {"query": "Equinor"})
    rows = result.structured_content["results"]
    assert len(rows) == 1
    assert rows[0]["id"] == "NO:923609016"
    assert "Public limited company" in rows[0]["title"]
    assert "active" in rows[0]["title"]


@respx.mock
async def test_search_name_fanout_merges_and_sorts_by_confidence_descending() -> None:
    """The real Tesco/Companies House example from `CONNECTOR_SPEC.md` §5: three GB hits
    at confidences 0.95/0.4/0.4, NO returns nothing, and ties keep the register's own
    order (D-020) rather than being re-shuffled."""
    respx.get(f"{GB_BASE_URL}/search/companies").mock(
        return_value=httpx.Response(200, json=_load_fixture("ch_search_tesco.json"))
    )
    _mock_no_search_empty()
    async with Client(mcp) as client:
        result = await client.call_tool("search", {"query": "Tesco PLC"})
    rows = result.structured_content["results"]
    assert [row["id"] for row in rows] == ["GB:00445790", "GB:09384423", "GB:05888957"]
    assert all(row["url"] for row in rows)  # OpenAI drops the citation on an empty url
    assert "dissolved" in rows[2]["title"]


@respx.mock
async def test_search_cross_registry_confidence_tie_breaks_on_exact_name_match() -> None:
    """Regression for a live-deployment ranking defect (2026-09-06): `search("Equinor")`
    returned `GB:11777091 — EQUINOR BLANDFORD ROAD LIMITED` first, not
    `NO:923609016 — EQUINOR ASA`. Both hits share the same D-005 confidence anchor (0.8,
    "starts with the query"), and the previous tie-break (registry order, alphabetical —
    GB before NO) had no relevance signal in it. `EQUINOR ASA` normalises to `"equinor"`
    (its `ASA` suffix stripped) and equals the normalised query exactly; `EQUINOR
    BLANDFORD ROAD LIMITED` normalises to `"equinor blandford road"`, which does not — so
    the exact-match tie-break must place NO first regardless of registry order."""
    respx.get(f"{GB_BASE_URL}/search/companies").mock(
        return_value=httpx.Response(
            200, json=_load_fixture("ch_search_equinor_blandford.json")
        )
    )
    _mock_no_search_equinor()
    async with Client(mcp) as client:
        result = await client.call_tool("search", {"query": "Equinor"})
    rows = result.structured_content["results"]
    assert rows[0]["id"] == "NO:923609016", (
        f"expected EQUINOR ASA (NO:923609016) first, got {rows[0]!r}"
    )
    assert "GB:11777091" in {row["id"] for row in rows}  # GB hit still present, just not first


@respx.mock
async def test_search_results_are_one_global_list_not_grouped_by_registry() -> None:
    """D-031(c)/D-020 applied across countries: a lower-confidence NO hit must be able to
    outrank a higher-confidence... no — a *higher*-confidence GB hit must outrank a
    *lower*-confidence NO hit, proving the merge is a real cross-registry sort and not
    "all of GB's rows, then all of NO's" or the reverse."""
    # GB: exact match (0.95). NO: a same-fixture Equinor hit, forced down to a lower tier
    # by searching for a query the name only *contains*, not starts with.
    respx.get(f"{GB_BASE_URL}/search/companies").mock(
        return_value=httpx.Response(200, json=_load_fixture("ch_search_equinor_blandford.json"))
    )
    envelope = {
        "_embedded": {"enheter": [EQUINOR]},
        "page": {"size": 1, "totalElements": 1, "totalPages": 1, "number": 0},
    }
    respx.get(f"{BASE_URL}/enheter").mock(return_value=httpx.Response(200, json=envelope))
    async with Client(mcp) as client:
        result = await client.call_tool("search", {"query": "Equinor Blandford Road Limited"})
    rows = result.structured_content["results"]
    assert rows[0]["id"] == "GB:11777091"  # exact match (0.95) outranks NO's lower tier


@respx.mock
async def test_search_merged_results_are_capped_at_ten_across_registries() -> None:
    """D-031(c)'s merged-row cap (`CONNECTOR_SPEC.md` §3, lowered from 20 to 10 in the
    same fix as the ranking defect above): fifteen NO hits alone must still come back as
    exactly ten rows."""
    entities = [
        {"organisasjonsnummer": f"90000{i:04d}", "navn": f"EQUINOR TEST NUMBER {i} AS"}
        for i in range(15)
    ]
    envelope = {
        "_embedded": {"enheter": entities},
        "page": {"size": 15, "totalElements": 15, "totalPages": 1, "number": 0},
    }
    respx.get(f"{BASE_URL}/enheter").mock(return_value=httpx.Response(200, json=envelope))
    _mock_gb_search_empty()
    async with Client(mcp) as client:
        result = await client.call_tool("search", {"query": "Equinor"})
    rows = result.structured_content["results"]
    assert len(rows) == 10


@respx.mock
async def test_search_single_answerable_registry_keeps_working_after_the_fix() -> None:
    """Requirement 4's "a query that only one registry can answer keeps working": GB's
    routes are deliberately unmocked, so this only passes if the merge/sort/cap rewrite
    still short-circuits to NO alone via the identifier check, exactly as before."""
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    async with Client(mcp) as client:
        result = await client.call_tool("search", {"query": "923609016"})
    rows = result.structured_content["results"]
    assert len(rows) == 1
    assert rows[0]["id"] == "NO:923609016"


@respx.mock
async def test_search_registry_name_substring_restricts_fanout_to_gb() -> None:
    """D-031(c): a live registry's full `country_info().name` appearing verbatim in the
    query narrows the candidate set to that registry alone — the match is the *name*
    inside the *query* (not the reverse), so this needs the whole name, not just
    "United Kingdom". NO's routes are deliberately unmocked to prove NO was never
    asked."""
    respx.get(f"{GB_BASE_URL}/search/companies").mock(
        return_value=httpx.Response(200, json=_load_fixture("ch_search_tesco.json"))
    )
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search", {"query": "Tesco at Companies House (United Kingdom)"}
        )
    rows = result.structured_content["results"]
    assert rows
    assert all(row["id"].startswith("GB:") for row in rows)


# ---------------------------------------------------------------------------
# search — zero hits
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_zero_hits_returns_rules_documents_not_a_fabricated_company() -> None:
    _mock_no_search_empty()
    _mock_gb_search_empty()
    async with Client(mcp) as client:
        result = await client.call_tool("search", {"query": "Zzzqqx Holdings"})
    rows = result.structured_content["results"]
    assert {row["id"] for row in rows} == {"rules:GB", "rules:NO"}
    assert all("Zzzqqx" not in row["title"] for row in rows)
    assert all(row["url"] == "https://api.foretak.dev/v1/countries" for row in rows)


# ---------------------------------------------------------------------------
# fetch — NO
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_no_id_returns_document_with_markdown_text_and_full_metadata() -> None:
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    async with Client(mcp) as client:
        result = await client.call_tool("fetch", {"id": "NO:923609016"})
    body = result.structured_content
    assert body["id"] == "NO:923609016"
    assert body["title"] == "EQUINOR ASA — NO 923609016"
    assert body["url"] == "https://api.foretak.dev/v1/NO/company/923609016"

    metadata = body["metadata"]
    assert metadata["company_report"]["name"] == "EQUINOR ASA"
    assert metadata["country"] == "NO"
    assert metadata["company_id"] == "923609016"
    assert metadata["is_active"] is True
    deadlines = metadata["deadline_report"]["deadlines"]
    assert len(deadlines) > 0
    assert metadata["next_deadline_kind"] == deadlines[0]["kind"]
    assert metadata["next_deadline_due_date"] == deadlines[0]["due_date"]

    text = body["text"]
    assert text.startswith("# EQUINOR ASA — NO 923609016")
    assert "Årsregnskap" in text
    assert "regnskapsloven § 8-3(1)" in text
    assert "calendar-year accounting period" in text  # every notes sentence survives (D-010)
    assert "## Source" in text
    assert "NLOD 2.0" in text
    assert "Not a sanctions, PEP or adverse-media" in text


@respx.mock
async def test_fetch_metadata_company_report_matches_lookup_company_byte_for_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The metadata half of D-031's contract: `metadata.company_report` must be exactly
    what `lookup_company` returns for the same identifier — not a re-derived shape. Cache
    disabled so both calls do an independent fresh fetch (otherwise the second would be
    a cache hit and `cached` would legitimately differ), matching
    `test_mcp.py::test_rest_and_mcp_lookup_company_are_identical`'s pattern."""
    monkeypatch.setenv("REGISTRY_MCP_CACHE_DISABLED", "1")
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    async with Client(mcp) as client:
        lookup_result = await client.call_tool("lookup_company", {"id": "923609016"})
        fetch_result = await client.call_tool("fetch", {"id": "NO:923609016"})
    lookup_body = lookup_result.structured_content
    fetch_company = fetch_result.structured_content["metadata"]["company_report"]
    volatile = {"fetched_at"}  # a live timestamp; every other field must match exactly
    assert {k: v for k, v in lookup_body.items() if k not in volatile} == {
        k: v for k, v in fetch_company.items() if k not in volatile
    }


# ---------------------------------------------------------------------------
# fetch — GB: honest nulls, register-published dates
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_gb_id_renders_honest_nulls_and_published_dates() -> None:
    respx.get(f"{GB_BASE_URL}/company/00445790").mock(return_value=httpx.Response(200, json=TESCO))
    async with Client(mcp) as client:
        result = await client.call_tool("fetch", {"id": "GB:00445790"})
    body = result.structured_content
    company = body["metadata"]["company_report"]

    assert company["vat_registered"] is None
    assert company["share_capital"] is None
    assert body["metadata"]["deadline_report"]["deadlines"]
    assert len(body["metadata"]["deadline_report"]["deadlines"]) == 2

    text = body["text"]
    assert "**VAT:**" not in text  # null is omitted, never rendered as "unknown"/"0"
    assert "**Share capital:**" not in text
    assert "not published by this register" in text  # employees_reported is False
    assert "Confirmation statement (CS01)" in text
    assert "the register's own figure" in text
    assert "## Register-published dates" in text
    assert "accounts.next_accounts.due_on" in text


# ---------------------------------------------------------------------------
# fetch — round-trip with search's own id
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_round_trips_a_no_search_result_id() -> None:
    _mock_no_search_equinor()
    _mock_gb_search_empty()
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    async with Client(mcp) as client:
        search_result = await client.call_tool("search", {"query": "Equinor"})
        hit_id = search_result.structured_content["results"][0]["id"]
        fetch_result = await client.call_tool("fetch", {"id": hit_id})
    assert fetch_result.structured_content["id"] == hit_id


@respx.mock
async def test_fetch_round_trips_a_gb_search_result_id() -> None:
    respx.get(f"{GB_BASE_URL}/search/companies").mock(
        return_value=httpx.Response(200, json=_load_fixture("ch_search_tesco.json"))
    )
    _mock_no_search_empty()
    respx.get(f"{GB_BASE_URL}/company/00445790").mock(return_value=httpx.Response(200, json=TESCO))
    async with Client(mcp) as client:
        search_result = await client.call_tool("search", {"query": "Tesco PLC"})
        hit_id = search_result.structured_content["results"][0]["id"]
        assert hit_id == "GB:00445790"
        fetch_result = await client.call_tool("fetch", {"id": hit_id})
    assert fetch_result.structured_content["id"] == hit_id


# ---------------------------------------------------------------------------
# fetch — rules documents and id-parsing errors
# ---------------------------------------------------------------------------


async def test_fetch_rules_prefix_returns_a_real_rules_document() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("fetch", {"id": "rules:GB"})
    body = result.structured_content
    assert body["id"] == "rules:GB"
    assert "Companies House (United Kingdom)" in body["title"]
    assert body["url"] == "https://api.foretak.dev/v1/countries"
    assert len(body["text"].strip()) > 0


async def test_fetch_rules_unsupported_country_is_json_error() -> None:
    async with Client(mcp) as client:
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool("fetch", {"id": "rules:ZZ"})
    payload = json.loads(str(excinfo.value))
    assert payload["error"]["code"] == "unsupported_country"


async def test_fetch_unmatched_no_colon_id_is_bad_request_naming_the_country_form() -> None:
    async with Client(mcp) as client:
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool("fetch", {"id": "not-a-real-identifier-at-all"})
    payload = json.loads(str(excinfo.value))
    assert payload["error"]["code"] == "bad_request"
    assert "{COUNTRY}:{identifier}" in payload["error"]["hint"]
    assert "list_countries" in payload["error"]["hint"]


async def test_fetch_explicit_country_prefix_with_bad_country_is_unsupported_country() -> None:
    async with Client(mcp) as client:
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool("fetch", {"id": "ZZ:12345"})
    payload = json.loads(str(excinfo.value))
    assert payload["error"]["code"] == "unsupported_country"


@respx.mock
async def test_fetch_not_found_is_a_real_error_unlike_inside_search() -> None:
    """D-031(d): unlike `search`'s identifier short-circuit (where `not_found`
    contributes no row and is not an error), `fetch`'s own `not_found` is a real error —
    the caller named one specific document and it is not there."""
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE_URL}/underenheter/923609016").mock(return_value=httpx.Response(404))
    async with Client(mcp) as client:
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool("fetch", {"id": "NO:923609016"})
    payload = json.loads(str(excinfo.value))
    assert payload["error"]["code"] == "not_found"


# ---------------------------------------------------------------------------
# D-031(g): core/, api/ and registries/ are untouched by this feature — a GB deployment
# with no Companies House key must still answer for Norway.
# ---------------------------------------------------------------------------


@respx.mock
async def test_search_without_gb_api_key_still_returns_norways_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY", raising=False)
    gb_client_module._client = None
    _mock_no_search_equinor()
    async with Client(mcp) as client:
        result = await client.call_tool("search", {"query": "Equinor"})
    rows = result.structured_content["results"]
    assert len(rows) == 1
    assert rows[0]["id"] == "NO:923609016"


# ---------------------------------------------------------------------------
# Sanity: the wire models really are the pydantic classes documented in
# `CONNECTOR_SPEC.md` §1 — `dict[str, Any]` in, `model_dump(mode="json")` out.
# ---------------------------------------------------------------------------


def test_connector_models_are_the_documented_shape() -> None:
    response = ConnectorSearchResponse(results=[])
    assert response.model_dump(mode="json") == {"results": []}

    document = ConnectorDocument(id="rules:NO", title="t", text="body", url="https://x")
    dumped = document.model_dump(mode="json")
    assert dumped["metadata"] == {}
    assert set(dumped) == {"id", "title", "text", "url", "metadata"}


def test_company_report_and_deadline_report_still_importable_for_metadata_typing() -> None:
    # Regression guard only: `_company_document` type-hints against these two models.
    assert CompanyReport.model_fields
    assert DeadlineReport.model_fields
