"""Tests for the `include=["parents"]` attachment — GLEIF Level 2 corporate
parents (`DECISIONS.md` D-047(a)), built on `core/gleif.py`'s shared search
with `include=["lei"]` (`tests/test_gleif.py`).

All `gleif_parent*.json` fixtures were recorded live and keyless from
`https://api.gleif.org/api/v1/lei-records` on 2026-09-09 — see
`tests/fixtures/README.md`'s "GLEIF parents" section for the exact query and
leg URL behind each one. Four entities:

* `98450073EGD581D89F03` (EQUINOR ENERGY AS, orgnr `990888213`) — both sides
  disclose a parent, both resolving to EQUINOR ASA, `corroborationLevel:
  ENTITY_SUPPLIED_ONLY` on both legs. The "1 + 4 requests" / disclosed-parent
  path.
* `OW6OFBNCKXC4US5C7523` (EQUINOR ASA, orgnr `923609016`) — both sides are
  reporting exceptions, `reason: NATURAL_PERSONS` on both. The "1 + 2
  requests" / exception path, and the fixture the description text is about
  (`DECISIONS.md` D-047(a)).
* `RR3QWICWWIPCS8A4S074` (NATWEST MARKETS PLC, `SC090312`) — both sides
  disclose NATWEST GROUP PLC (`2138005O9XJIJN4JPN90`), `corroborationLevel:
  FULLY_CORROBORATED` — the contrast with Equinor Energy's
  `ENTITY_SUPPLIED_ONLY` on an identical relationship type.
* `2138002P5RNKC5W2JZ46` (TESCO PLC, `00445790`) — both sides are reporting
  exceptions, `reason: NON_CONSOLIDATING` — the contrast with Equinor ASA's
  `NATURAL_PERSONS` on an identical situation (a listed company at the top of
  its own group).

This module's own tests call `Registry.parents(id)` directly for the same
reason `tests/test_gleif.py` calls `Registry.lei(id)` directly: the upstream
is not a national register, so most tests need no Companies House key. Tests
that must go through `Registry.lookup_with` (the shared-search assertions,
the failed-search nullability test) use Norway, which is keyless.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pydantic
import pytest
import respx

from registry_mcp.core import cache, gleif
from registry_mcp.core.models import (
    CompanyReport,
    ErrorCode,
    ParentBlock,
    ParentLink,
    RegistryError,
)
from registry_mcp.core.registry import get_registry

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return result


# Equinor Energy AS — both sides disclosed, both -> Equinor ASA.
EQUINOR_ENERGY_SEARCH = _load("gleif_parents_search_990888213.json")
EQUINOR_ENERGY_DIRECT_LEI = _load("gleif_parent_lei_990888213_direct.json")
EQUINOR_ENERGY_DIRECT_REL = _load("gleif_parent_rel_990888213_direct.json")
EQUINOR_ENERGY_ULTIMATE_LEI = _load("gleif_parent_lei_990888213_ultimate.json")
EQUINOR_ENERGY_ULTIMATE_REL = _load("gleif_parent_rel_990888213_ultimate.json")

# Equinor ASA — both sides excepted, both NATURAL_PERSONS.
EQUINOR_ASA_SEARCH = _load("gleif_parents_search_923609016.json")
EQUINOR_ASA_DIRECT_EXC = _load("gleif_parent_exc_923609016_direct.json")
EQUINOR_ASA_ULTIMATE_EXC = _load("gleif_parent_exc_923609016_ultimate.json")

# NatWest Markets plc — both sides disclosed, both -> NatWest Group plc.
NATWEST_SEARCH = _load("gleif_parents_search_SC090312.json")
NATWEST_DIRECT_LEI = _load("gleif_parent_lei_SC090312_direct.json")
NATWEST_DIRECT_REL = _load("gleif_parent_rel_SC090312_direct.json")
NATWEST_ULTIMATE_LEI = _load("gleif_parent_lei_SC090312_ultimate.json")
NATWEST_ULTIMATE_REL = _load("gleif_parent_rel_SC090312_ultimate.json")

# Tesco plc — both sides excepted, both NON_CONSOLIDATING.
TESCO_SEARCH = _load("gleif_parents_search_00445790.json")
TESCO_DIRECT_EXC = _load("gleif_parent_exc_00445790_direct.json")
TESCO_ULTIMATE_EXC = _load("gleif_parent_exc_00445790_ultimate.json")

# A `total: 0` search — GLEIF holds no LEI at all.
EMPTY_SEARCH = _load("gleif_parents_empty.json")

EQUINOR = _load("brreg_923609016.json")


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_PATH", str(tmp_path / "cache.sqlite3"))
    monkeypatch.delenv("REGISTRY_MCP_CACHE_DISABLED", raising=False)
    monkeypatch.delenv("REGISTRY_MCP_CACHE_TTL_SECONDS", raising=False)
    yield


@pytest.fixture(autouse=True)
async def _reset_gleif_client() -> AsyncIterator[None]:
    gleif._client = None
    yield
    await gleif.aclose()


def _mock_side(
    search_relationships: dict[str, Any],
    side: str,
    *,
    lei_body: dict[str, Any] | None = None,
    rel_body: dict[str, Any] | None = None,
    exc_body: dict[str, Any] | None = None,
    lei_status: int = 200,
    rel_status: int = 200,
    exc_status: int = 200,
) -> dict[str, respx.Route]:
    """Register respx routes for one side's leg(s), read from the search
    fixture's own `relationships[f"{side}-parent"]["links"]` — never a
    constructed URL, mirroring what `_fetch_side` itself does."""
    links: dict[str, Any] = search_relationships[f"{side}-parent"]["links"]
    routes: dict[str, respx.Route] = {}
    if "reporting-exception" in links:
        body = exc_body if exc_body is not None else {}
        routes["exception"] = respx.get(links["reporting-exception"]).mock(
            return_value=httpx.Response(exc_status, json=body)
        )
    if "lei-record" in links:
        body = lei_body if lei_body is not None else {}
        routes["lei"] = respx.get(links["lei-record"]).mock(
            return_value=httpx.Response(lei_status, json=body)
        )
    if "relationship-record" in links:
        body = rel_body if rel_body is not None else {}
        routes["relationship"] = respx.get(links["relationship-record"]).mock(
            return_value=httpx.Response(rel_status, json=body)
        )
    return routes


def _mock_equinor_energy_full() -> None:
    """Both sides of `98450073EGD581D89F03` (Equinor Energy AS), disclosed,
    both legs each — the "1 + 4" path."""
    relationships = EQUINOR_ENERGY_SEARCH["data"][0]["relationships"]
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "990 888 213"},
    ).mock(return_value=httpx.Response(200, json=EQUINOR_ENERGY_SEARCH))
    _mock_side(
        relationships, "direct", lei_body=EQUINOR_ENERGY_DIRECT_LEI, rel_body=EQUINOR_ENERGY_DIRECT_REL
    )
    _mock_side(
        relationships,
        "ultimate",
        lei_body=EQUINOR_ENERGY_ULTIMATE_LEI,
        rel_body=EQUINOR_ENERGY_ULTIMATE_REL,
    )


def _mock_equinor_asa_full() -> None:
    """Both sides of `OW6OFBNCKXC4US5C7523` (Equinor ASA), excepted, one leg
    each — the "1 + 2" path."""
    relationships = EQUINOR_ASA_SEARCH["data"][0]["relationships"]
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "923 609 016"},
    ).mock(return_value=httpx.Response(200, json=EQUINOR_ASA_SEARCH))
    _mock_side(relationships, "direct", exc_body=EQUINOR_ASA_DIRECT_EXC)
    _mock_side(relationships, "ultimate", exc_body=EQUINOR_ASA_ULTIMATE_EXC)


# ---------------------------------------------------------------------------
# E.1 — the three-level nullability, three separate tests
# ---------------------------------------------------------------------------


@respx.mock
async def test_parents_present_with_a_populated_direct_side() -> None:
    """`include=["parents"]` on an entity with a disclosed parent: a present
    block whose `direct` is populated. Equinor Energy AS -> Equinor ASA."""
    _mock_equinor_energy_full()

    registry = get_registry("NO")
    block = await registry.parents("990888213")

    assert isinstance(block, ParentBlock)
    assert block.direct is not None
    assert block.direct.lei == "OW6OFBNCKXC4US5C7523"
    assert block.direct.legal_name == "EQUINOR ASA"
    assert block.direct.reporting_exception is None
    assert block.provenance.license == "CC0 1.0"
    assert block.provenance.source is not None and "GLEIF" in block.provenance.source
    assert block.provenance.cached is False


@respx.mock
async def test_parents_present_with_an_exception_on_direct_and_ultimate() -> None:
    """On an entity with an exception: a present block whose
    `direct.reporting_exception` is the word and whose `direct.lei` is
    `None`. Equinor ASA reads `NATURAL_PERSONS` on both sides — the fixture
    D-047(a)'s description text is about."""
    _mock_equinor_asa_full()

    registry = get_registry("NO")
    block = await registry.parents("923609016")

    assert block.direct is not None
    assert block.direct.reporting_exception == "NATURAL_PERSONS"
    assert block.direct.lei is None
    assert block.ultimate is not None
    assert block.ultimate.reporting_exception == "NATURAL_PERSONS"
    assert block.ultimate.lei is None


@respx.mock
async def test_gleif_unreachable_leaves_parents_absent_with_a_note_and_lookup_succeeds() -> None:
    """With GLEIF unreachable: **no block**, a `notes` sentence on the
    report, and a **successful lookup** — the search itself failing, not a
    leg. Mirrors `tests/test_gleif.py`'s equivalent `lei` test exactly."""
    from registry_mcp.registries.no import client as no_client_module

    respx.get(f"{no_client_module.BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "923 609 016"},
    ).mock(side_effect=[httpx.Response(500), httpx.Response(500)])

    registry = get_registry("NO")
    report = await registry.lookup_with("923609016", ["parents"])

    assert report.name == "EQUINOR ASA"
    assert report.parents is None
    assert any("parents" in note for note in report.notes)


@respx.mock
async def test_gleif_holds_no_lei_is_a_present_block_with_both_sides_none() -> None:
    """The fourth state: GLEIF holds no LEI for this entity at all -> a
    **present** block, `direct=None`, `ultimate=None`, and a note saying so
    — this is the answer, not an absence (D-011). Genuinely zero hits on
    both the formatted and the bare candidate (D-045(e)'s cascade), so both
    are mocked."""
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "910 000 004"},
    ).mock(return_value=httpx.Response(200, json=EMPTY_SEARCH))
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "910000004"},
    ).mock(return_value=httpx.Response(200, json=EMPTY_SEARCH))

    registry = get_registry("NO")
    block = await registry.parents("910000004")

    assert isinstance(block, ParentBlock)
    assert block.direct is None
    assert block.ultimate is None
    assert any("no LEI" in note for note in block.notes)


# ---------------------------------------------------------------------------
# E.2 — exactly one search request when both `lei` and `parents` are
# requested. This is C1, the assertion that matters most.
# ---------------------------------------------------------------------------


@respx.mock
async def test_lei_and_parents_together_make_exactly_one_search_request() -> None:
    """`include=["lei", "parents"]` on a cold cache: one `lei-records`
    search, not two. `core/gleif.py::_fetch_search_payload`'s in-flight map
    is what closes this — reversing it (each attachment calling
    `_do_fetch_search` independently) was manually verified, during
    development, to make this assertion fail with `call_count == 2`."""
    from registry_mcp.registries.no import client as no_client_module

    respx.get(f"{no_client_module.BASE_URL}/enheter/990888213").mock(
        return_value=httpx.Response(
            200, json={**EQUINOR, "organisasjonsnummer": "990888213", "navn": "EQUINOR ENERGY AS"}
        )
    )
    search_route = respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "990 888 213"},
    ).mock(return_value=httpx.Response(200, json=EQUINOR_ENERGY_SEARCH))
    relationships = EQUINOR_ENERGY_SEARCH["data"][0]["relationships"]
    _mock_side(
        relationships, "direct", lei_body=EQUINOR_ENERGY_DIRECT_LEI, rel_body=EQUINOR_ENERGY_DIRECT_REL
    )
    _mock_side(
        relationships,
        "ultimate",
        lei_body=EQUINOR_ENERGY_ULTIMATE_LEI,
        rel_body=EQUINOR_ENERGY_ULTIMATE_REL,
    )

    registry = get_registry("NO")
    report = await registry.lookup_with("990888213", ["lei", "parents"])

    assert search_route.call_count == 1
    assert report.lei is not None and report.lei.lei == "98450073EGD581D89F03"
    assert report.parents is not None and report.parents.direct is not None
    assert report.parents.direct.lei == "OW6OFBNCKXC4US5C7523"


@respx.mock
async def test_parents_alone_still_populates_the_lei_cache_entry() -> None:
    """A lookup asking for only `parents` still fills the `lei` cache entry
    as a side effect — it is the same fetch (D-047(a))."""
    _mock_equinor_energy_full()

    registry = get_registry("NO")
    await registry.parents("990888213")

    entry = cache.get("NO:brreg:lei:990888213")
    assert entry is not None
    assert entry.status == "ok"


# ---------------------------------------------------------------------------
# E.3 — request count per path: 1 + 2 on the exception path, 1 + 4 on the
# parent path, and the exact URLs.
# ---------------------------------------------------------------------------


@respx.mock
async def test_exception_path_is_one_search_plus_two_leg_requests() -> None:
    relationships = EQUINOR_ASA_SEARCH["data"][0]["relationships"]
    search_route = respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "923 609 016"},
    ).mock(return_value=httpx.Response(200, json=EQUINOR_ASA_SEARCH))
    direct_routes = _mock_side(relationships, "direct", exc_body=EQUINOR_ASA_DIRECT_EXC)
    ultimate_routes = _mock_side(relationships, "ultimate", exc_body=EQUINOR_ASA_ULTIMATE_EXC)

    await get_registry("NO").parents("923609016")

    assert search_route.call_count == 1
    assert direct_routes["exception"].call_count == 1
    assert ultimate_routes["exception"].call_count == 1
    assert (
        str(direct_routes["exception"].calls.last.request.url)
        == relationships["direct-parent"]["links"]["reporting-exception"]
    )
    assert (
        str(ultimate_routes["exception"].calls.last.request.url)
        == relationships["ultimate-parent"]["links"]["reporting-exception"]
    )


@respx.mock
async def test_disclosed_parent_path_is_one_search_plus_four_leg_requests() -> None:
    relationships = EQUINOR_ENERGY_SEARCH["data"][0]["relationships"]
    search_route = respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "990 888 213"},
    ).mock(return_value=httpx.Response(200, json=EQUINOR_ENERGY_SEARCH))
    direct_routes = _mock_side(
        relationships, "direct", lei_body=EQUINOR_ENERGY_DIRECT_LEI, rel_body=EQUINOR_ENERGY_DIRECT_REL
    )
    ultimate_routes = _mock_side(
        relationships,
        "ultimate",
        lei_body=EQUINOR_ENERGY_ULTIMATE_LEI,
        rel_body=EQUINOR_ENERGY_ULTIMATE_REL,
    )

    await get_registry("NO").parents("990888213")

    assert search_route.call_count == 1
    assert direct_routes["lei"].call_count == 1
    assert direct_routes["relationship"].call_count == 1
    assert ultimate_routes["lei"].call_count == 1
    assert ultimate_routes["relationship"].call_count == 1
    assert (
        str(direct_routes["lei"].calls.last.request.url)
        == relationships["direct-parent"]["links"]["lei-record"]
    )
    assert (
        str(direct_routes["relationship"].calls.last.request.url)
        == relationships["direct-parent"]["links"]["relationship-record"]
    )


# ---------------------------------------------------------------------------
# E.4 — Sweden does not declare `parents` (D-039, D-040, D-045(e), D-047(a))
# ---------------------------------------------------------------------------


async def test_sweden_include_parents_is_bad_request_not_an_empty_block() -> None:
    registry = get_registry("SE")
    assert "parents" not in registry.effective_includes

    with pytest.raises(RegistryError) as excinfo:
        await registry.lookup_with("5560160680", ["parents"])
    assert excinfo.value.code is ErrorCode.BAD_REQUEST
    assert "parents" not in excinfo.value.details["allowed"]
    assert excinfo.value.details["unknown"] == ["parents"]


def test_list_countries_shows_parents_for_no_and_gb_but_not_se() -> None:
    assert "parents" in get_registry("NO").country_info().supported_includes
    assert "parents" in get_registry("GB").country_info().supported_includes
    assert "parents" not in get_registry("SE").country_info().supported_includes


# ---------------------------------------------------------------------------
# E.5 — `ParentLink`'s mutual-exclusion validator (D-011)
# ---------------------------------------------------------------------------


def test_parent_link_rejects_both_lei_and_reporting_exception_set() -> None:
    with pytest.raises(pydantic.ValidationError):
        ParentLink(lei="OW6OFBNCKXC4US5C7523", reporting_exception="NATURAL_PERSONS")


def test_parent_link_rejects_neither_lei_nor_reporting_exception_set() -> None:
    with pytest.raises(pydantic.ValidationError):
        ParentLink()


def test_parent_link_accepts_lei_alone() -> None:
    ParentLink(lei="OW6OFBNCKXC4US5C7523")  # must not raise


def test_parent_link_accepts_reporting_exception_alone() -> None:
    ParentLink(reporting_exception="NON_CONSOLIDATING")  # must not raise


# ---------------------------------------------------------------------------
# E.6 — `direct` and `ultimate` differing in kind, built by hand
# ---------------------------------------------------------------------------


def test_direct_and_ultimate_can_differ_in_kind_and_survive_independently() -> None:
    from registry_mcp.core.models import SourceRef

    block = ParentBlock(
        direct=ParentLink(lei="OW6OFBNCKXC4US5C7523", legal_name="EQUINOR ASA"),
        ultimate=ParentLink(reporting_exception="NON_CONSOLIDATING"),
        provenance=SourceRef(source="GLEIF Level 2 (gleif.org)", license="CC0 1.0"),
    )
    assert block.direct is not None
    assert block.direct.lei == "OW6OFBNCKXC4US5C7523"
    assert block.direct.reporting_exception is None
    assert block.ultimate is not None
    assert block.ultimate.reporting_exception == "NON_CONSOLIDATING"
    assert block.ultimate.lei is None


# ---------------------------------------------------------------------------
# E.7 — a failed leg degrades one side and leaves the block present (C5)
# ---------------------------------------------------------------------------


@respx.mock
async def test_a_failed_direct_leg_degrades_only_that_side() -> None:
    """The direct exception fetch 500s twice (both retry attempts) while
    ultimate succeeds: the block is present, `direct` is `None`, and a
    `notes` sentence names the leg that failed."""
    relationships = EQUINOR_ASA_SEARCH["data"][0]["relationships"]
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "923 609 016"},
    ).mock(return_value=httpx.Response(200, json=EQUINOR_ASA_SEARCH))
    direct_url = relationships["direct-parent"]["links"]["reporting-exception"]
    respx.get(direct_url).mock(side_effect=[httpx.Response(500), httpx.Response(500)])
    _mock_side(relationships, "ultimate", exc_body=EQUINOR_ASA_ULTIMATE_EXC)

    block = await get_registry("NO").parents("923609016")

    assert block.direct is None
    assert block.ultimate is not None
    assert block.ultimate.reporting_exception == "NATURAL_PERSONS"
    assert any("direct" in note for note in block.notes)


@respx.mock
async def test_a_failed_disclosed_parent_leg_degrades_only_that_side() -> None:
    """Same rule on the disclosed-parent path: the direct side's own
    `lei-record` fetch fails while its `relationship-record` and the
    ultimate side both succeed."""
    relationships = EQUINOR_ENERGY_SEARCH["data"][0]["relationships"]
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "990 888 213"},
    ).mock(return_value=httpx.Response(200, json=EQUINOR_ENERGY_SEARCH))
    direct_lei_url = relationships["direct-parent"]["links"]["lei-record"]
    respx.get(direct_lei_url).mock(side_effect=[httpx.Response(500), httpx.Response(500)])
    respx.get(relationships["direct-parent"]["links"]["relationship-record"]).mock(
        return_value=httpx.Response(200, json=EQUINOR_ENERGY_DIRECT_REL)
    )
    _mock_side(
        relationships,
        "ultimate",
        lei_body=EQUINOR_ENERGY_ULTIMATE_LEI,
        rel_body=EQUINOR_ENERGY_ULTIMATE_REL,
    )

    block = await get_registry("NO").parents("990888213")

    assert block.direct is None
    assert block.ultimate is not None
    assert block.ultimate.lei == "OW6OFBNCKXC4US5C7523"
    assert any("direct" in note for note in block.notes)


# ---------------------------------------------------------------------------
# E.8 — `corroboration_level` contrast: the two fixtures exist to be
# contrasted (Equinor Energy `ENTITY_SUPPLIED_ONLY` vs NatWest
# `FULLY_CORROBORATED`).
# ---------------------------------------------------------------------------


@respx.mock
async def test_corroboration_level_is_entity_supplied_only_for_equinor_energy() -> None:
    _mock_equinor_energy_full()
    block = await get_registry("NO").parents("990888213")
    assert block.direct is not None
    assert block.direct.corroboration_level == "ENTITY_SUPPLIED_ONLY"


@respx.mock
async def test_corroboration_level_is_fully_corroborated_for_natwest() -> None:
    relationships = NATWEST_SEARCH["data"][0]["relationships"]
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "GB", "filter[entity.registeredAs]": "SC090312"},
    ).mock(return_value=httpx.Response(200, json=NATWEST_SEARCH))
    _mock_side(relationships, "direct", lei_body=NATWEST_DIRECT_LEI, rel_body=NATWEST_DIRECT_REL)
    _mock_side(relationships, "ultimate", lei_body=NATWEST_ULTIMATE_LEI, rel_body=NATWEST_ULTIMATE_REL)

    block = await get_registry("GB").parents("SC090312")

    assert block.direct is not None
    assert block.direct.lei == "2138005O9XJIJN4JPN90"
    assert block.direct.legal_name == "NATWEST GROUP PLC"
    assert block.direct.jurisdiction == "GB"
    assert block.direct.corroboration_level == "FULLY_CORROBORATED"


@respx.mock
async def test_tesco_reads_non_consolidating_the_contrast_with_equinor_asa() -> None:
    """Same situation as Equinor ASA — a listed company at the top of its
    own group — read as a different word: `NON_CONSOLIDATING`, not
    `NATURAL_PERSONS`. Neither is verified by GLEIF or by us."""
    relationships = TESCO_SEARCH["data"][0]["relationships"]
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "GB", "filter[entity.registeredAs]": "00445790"},
    ).mock(return_value=httpx.Response(200, json=TESCO_SEARCH))
    _mock_side(relationships, "direct", exc_body=TESCO_DIRECT_EXC)
    _mock_side(relationships, "ultimate", exc_body=TESCO_ULTIMATE_EXC)

    block = await get_registry("GB").parents("00445790")

    assert block.direct is not None
    assert block.direct.reporting_exception == "NON_CONSOLIDATING"
    assert block.ultimate is not None
    assert block.ultimate.reporting_exception == "NON_CONSOLIDATING"


# ---------------------------------------------------------------------------
# E.9 — no struck field anywhere in the tree (D-042(e), D-047(a))
# ---------------------------------------------------------------------------


def test_no_struck_gleif_field_is_anywhere_in_the_source_tree() -> None:
    """D-047(a) strikes several fields on measurement, none of them carried
    anywhere: `corroborationDocuments` (never read); bracket-style access to
    a relationship's `periods` key (the one date this project does keep —
    `RELATIONSHIP_PERIOD`'s start — is read with `.get(...)`, named in a
    `notes` sentence, and never modelled as a field); `ExceptionReference`
    (the format's own type name for the exception's free-text field, never
    read); the exception's free-text `reference` itself (`[1,*]` of up to
    500 characters, null on 117 of 117 fetched, never read); and
    `entity.category` (never read, alongside `entity.status`, which
    `tests/test_gleif.py::test_no_source_file_reads_gleifs_entity_status_field`
    already covers for the whole tree). None of the five appears anywhere in
    the source, comment or code — a stronger guarantee than the done-check's
    grep asks for."""
    src_dir = Path(gleif.__file__).parent.parent.parent  # .../src/registry_mcp
    forbidden = (
        "corroborationDocuments",
        '["periods"]',
        "['periods']",
        "ExceptionReference",
        '"reference"',
        "entity.category",
    )
    hits = [
        (path, pattern)
        for path in src_dir.rglob("*.py")
        for pattern in forbidden
        if pattern in path.read_text(encoding="utf-8")
    ]
    assert hits == []


# ---------------------------------------------------------------------------
# `CompanyReport.parents` shape (D-004: always present, `None` on every
# lookup that did not ask for it)
# ---------------------------------------------------------------------------


def test_company_report_parents_field_defaults_to_none() -> None:
    report = CompanyReport(country="NO", registry="brreg", id="923609016", name="X")
    assert report.parents is None
    assert "parents" in CompanyReport.model_fields


# ---------------------------------------------------------------------------
# Cache key shape — the per-kind TTL table's kind-from-key parsing
# (`core/cache.py`) reads what this module writes; `provenance.cached`
# describes the `parents` entry, not the `lei` one (C6).
# ---------------------------------------------------------------------------


@respx.mock
async def test_parents_is_cached_under_its_own_kind_slot() -> None:
    _mock_equinor_asa_full()
    await get_registry("NO").parents("923609016")

    entry = cache.get("NO:brreg:parents:923609016")
    assert entry is not None
    assert entry.status == "ok"


@respx.mock
async def test_gleif_holds_no_lei_caches_parents_as_not_found() -> None:
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "910 000 004"},
    ).mock(return_value=httpx.Response(200, json=EMPTY_SEARCH))
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "910000004"},
    ).mock(return_value=httpx.Response(200, json=EMPTY_SEARCH))

    await get_registry("NO").parents("910000004")

    entry = cache.get("NO:brreg:parents:910000004")
    assert entry is not None
    assert entry.status == "not_found"


@respx.mock
async def test_a_cached_parents_block_is_served_without_a_second_fan_out() -> None:
    """`provenance.cached` describes **this** entry, not the `lei` one (C6),
    and a second call makes no new request at all — not the search, not
    either leg."""
    relationships = EQUINOR_ASA_SEARCH["data"][0]["relationships"]
    search_route = respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "923 609 016"},
    ).mock(return_value=httpx.Response(200, json=EQUINOR_ASA_SEARCH))
    direct_routes = _mock_side(relationships, "direct", exc_body=EQUINOR_ASA_DIRECT_EXC)
    ultimate_routes = _mock_side(relationships, "ultimate", exc_body=EQUINOR_ASA_ULTIMATE_EXC)

    registry = get_registry("NO")
    first = await registry.parents("923609016")
    second = await registry.parents("923609016")

    assert second.direct is not None and first.direct is not None
    assert second.direct.reporting_exception == first.direct.reporting_exception
    assert first.provenance.cached is False
    assert second.provenance.cached is True
    assert search_route.call_count == 1
    assert direct_routes["exception"].call_count == 1
    assert ultimate_routes["exception"].call_count == 1
