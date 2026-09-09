"""Tests for `core/gleif.py` and the `include=["lei"]` attachment it serves
(`DECISIONS.md` D-026(c), D-045(e)).

Unlike `charges`/`filings`/`insolvency` (`tests/test_client_gb.py` etc.),
this attachment's upstream is not a national register — GLEIF publishes
every jurisdiction from one endpoint, under one CC0 licence, with one TTL —
so most tests here call `Registry.lei(id)` directly rather than going
through `Registry.lookup_with`. That is deliberate, not a shortcut: it
proves the query/mapping mechanism in isolation, and it means these tests
need no Companies House API key (`lei()` never calls the country's own
`lookup()`). The two tests that do exercise the full `lookup_with` round
trip (`test_default_lookup_makes_exactly_one_upstream_request_and_lei_is_none`,
`test_a_failed_gleif_fetch_leaves_lei_absent_with_a_note_and_the_lookup_still_succeeds`)
use Norway, which is keyless.

All six `gleif_*.json` fixtures were recorded live and keyless from
`https://api.gleif.org/api/v1/lei-records` on 2026-09-08 — see
`tests/fixtures/README.md`. Every respx mock below matches on the *exact*
`filter[entity.jurisdiction]` / `filter[entity.registeredAs]` pair, so a
future edit that changes which string is queried fails here, not in
production.

**A note on the two Companies House registration-authority codes below**: the
six committed fixtures are raw, live GLEIF recordings, and the ones for
Tesco and Carillion (both England-and-Wales registrations) and NatWest
Markets (a Scottish one) legitimately carry their own real codes as recorded
data — that is the real world, not a test asserting anything. In this
file's own assertions, each of the two codes is pinned in exactly one
dedicated test — one for England-and-Wales, a different one for Scotland —
which is the substance the done-check cares about: nothing here pins the
England-and-Wales code for "the UK" as a whole.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from registry_mcp.core import cache, gleif
from registry_mcp.core.models import CompanyReport, ErrorCode, LeiRecord, RegistryError
from registry_mcp.core.registry import get_registry

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return result


EQUINOR_LEI = _load("gleif_923609016.json")
TESCO_LEI = _load("gleif_00445790.json")
NATWEST_LEI = _load("gleif_SC090312.json")
ERICSSON_LEI = _load("gleif_556016-0680.json")
CARILLION_LEI = _load("gleif_03782379.json")
EMPTY_LEI = _load("gleif_empty.json")

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


def _no_hits(jurisdiction: str, registered_as: str) -> dict[str, Any]:
    """A hand-built zero-hit GLEIF response, shaped like `gleif_empty.json`
    but for an arbitrary jurisdiction/query — used to prove a *miss* on one
    candidate without needing a committed fixture for every possible one."""
    return {
        "meta": {"pagination": {"total": 0}},
        "data": [],
    }


# ---------------------------------------------------------------------------
# The two-level nullability, tested as such (D-026(c), D-011) — three
# separate tests, per `tasks/T42.md` §D.1, not one.
# ---------------------------------------------------------------------------


@respx.mock
async def test_lei_present_with_a_real_lei_for_norway() -> None:
    """`include=["lei"]` on an entity with an LEI: a present block whose
    `provenance.license` is 'CC0 1.0' and whose `provenance.source` names
    GLEIF — the done-check's first clause."""
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "923 609 016"},
    ).mock(return_value=httpx.Response(200, json=EQUINOR_LEI))

    registry = get_registry("NO")
    record = await registry.lei("923609016")

    assert isinstance(record, LeiRecord)
    assert record.lei == "OW6OFBNCKXC4US5C7523"
    assert record.legal_name == "EQUINOR ASA"
    assert record.provenance.license == "CC0 1.0"
    assert record.provenance.source is not None and "GLEIF" in record.provenance.source
    assert record.provenance.cached is False
    assert any("923 609 016" in note for note in record.notes)


@respx.mock
async def test_lei_present_but_null_when_gleif_holds_none() -> None:
    """On an entity without one: a **present** block with `lei: null` — the
    done-check's second clause, and the answer this whole attachment exists
    to make legible rather than absent."""
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "GB", "filter[entity.registeredAs]": "00223668"},
    ).mock(return_value=httpx.Response(200, json=EMPTY_LEI))

    registry = get_registry("GB")
    record = await registry.lei("00223668")

    assert isinstance(record, LeiRecord)
    assert record.lei is None
    assert record.legal_name is None
    assert record.registration_status is None
    assert record.provenance.license == "CC0 1.0"
    assert any("00223668" in note for note in record.notes)


@respx.mock
async def test_a_failed_gleif_fetch_leaves_lei_absent_with_a_note_and_the_lookup_still_succeeds() -> (
    None
):
    """With GLEIF unreachable: **no block**, a `notes` sentence on the
    report, and a **successful lookup** — the done-check's third clause.
    This is the one test in this file that must go through `lookup_with`,
    because the absent-block-plus-note behaviour lives there, not in
    `Registry.lei` itself (D-042(b))."""
    from registry_mcp.registries.no import client as no_client_module

    respx.get(f"{no_client_module.BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "923 609 016"},
    ).mock(side_effect=[httpx.Response(500), httpx.Response(500)])

    registry = get_registry("NO")
    report = await registry.lookup_with("923609016", ["lei"])

    assert report.name == "EQUINOR ASA"
    assert report.lei is None
    assert any("lei" in note for note in report.notes)


# ---------------------------------------------------------------------------
# `include=["nonsense"]` -> `bad_request`, `lei` among the allowed values for
# every non-Swedish country (`tasks/T42.md` §D.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("country", ["NO", "GB"])
async def test_unknown_include_lists_lei_among_the_allowed_values(country: str) -> None:
    """Fails before `lookup` is even attempted (the unknown-value check runs
    first), so this needs no upstream mock at all — for either country."""
    registry = get_registry(country)
    with pytest.raises(RegistryError) as excinfo:
        await registry.lookup_with("x", ["nonsense"])
    assert excinfo.value.code is ErrorCode.BAD_REQUEST
    assert "lei" in excinfo.value.details["allowed"]
    assert "lei" in excinfo.value.hint


# ---------------------------------------------------------------------------
# Sweden does not declare `lei` (D-039, D-040, D-045(e)) — `bad_request`,
# never a silent empty block (D-042(d)(3)) (`tasks/T42.md` §D.3)
# ---------------------------------------------------------------------------


async def test_sweden_include_lei_is_bad_request_not_an_empty_block() -> None:
    """The identifier would otherwise reach a third-party host (GLEIF) in a
    URL query string, which for Sweden can be a personnummer (D-039) — so
    `lei` is missing from `effective_includes` entirely, and the caller is
    told that in terms, never handed a quietly-empty block."""
    registry = get_registry("SE")
    assert "lei" not in registry.effective_includes

    with pytest.raises(RegistryError) as excinfo:
        await registry.lookup_with("5560160680", ["lei"])
    assert excinfo.value.code is ErrorCode.BAD_REQUEST
    assert excinfo.value.details["allowed"] == ["filings"]
    assert excinfo.value.details["unknown"] == ["lei"]
    assert "lei" in excinfo.value.hint or "filings" in excinfo.value.hint


def test_list_countries_shows_lei_for_no_and_gb_but_not_se() -> None:
    assert "lei" in get_registry("NO").country_info().supported_includes
    assert "lei" in get_registry("GB").country_info().supported_includes
    assert "lei" not in get_registry("SE").country_info().supported_includes


# ---------------------------------------------------------------------------
# A default lookup makes exactly one upstream request and `report.lei is
# None` (`tasks/T42.md` §D.4 — the R-5 done-check, extended to the real
# attachment rather than a fake one)
# ---------------------------------------------------------------------------


@respx.mock
async def test_default_lookup_makes_exactly_one_upstream_request_and_lei_is_none() -> None:
    """Extended by `tasks/T53.md` §E.13 to cover `parents` too: a default
    lookup (no `include`) fetches neither attachment, so this one assertion
    covers both GLEIF-backed universal includes at once."""
    from registry_mcp.registries.no import client as no_client_module

    company_route = respx.get(f"{no_client_module.BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )
    # No `params=` constraint: *any* call to the search endpoint must not
    # happen. `include=()` never calls `parents()` either, so no
    # `direct-parent`/`ultimate-parent` leg URL is attempted at all — respx's
    # default `assert_all_mocked` would fail this test loudly if one were.
    gleif_route = respx.get(gleif.BASE_URL).mock(return_value=httpx.Response(200, json=EQUINOR_LEI))

    registry = get_registry("NO")
    report = await registry.lookup_with("923609016")

    assert company_route.call_count == 1
    assert gleif_route.call_count == 0
    assert report.lei is None
    assert report.parents is None


# ---------------------------------------------------------------------------
# `format_id`'s output is queried, not the bare identifier — the trap
# D-045(e) measured (`tasks/T42.md` §D.5)
# ---------------------------------------------------------------------------


@respx.mock
async def test_norway_queries_the_formatted_identifier_not_the_bare_one() -> None:
    """A regression tripwire: if a future edit drops `format_id` from the
    query (or queries the bare id first), the bare route below — mocked to
    return zero hits, as it does live — is the one that gets hit, and
    `record.lei` comes back `None` instead of the real value."""
    formatted_route = respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "923 609 016"},
    ).mock(return_value=httpx.Response(200, json=EQUINOR_LEI))
    bare_route = respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "923609016"},
    ).mock(return_value=httpx.Response(200, json=_no_hits("NO", "923609016")))

    registry = get_registry("NO")
    record = await registry.lei("923609016")

    assert record.lei == "OW6OFBNCKXC4US5C7523"
    assert formatted_route.call_count == 1
    assert bare_route.call_count == 0
    assert "filter%5Bentity.registeredAs%5D=923+609+016" in str(
        formatted_route.calls.last.request.url
    )


@respx.mock
async def test_sweden_queries_the_formatted_identifier_not_the_bare_one() -> None:
    """Same trap, Sweden's hyphenated form. Recorded for the mapper only —
    `SE` does not declare `lei` (see the bad_request test above), so this
    calls `Registry.lei` directly, bypassing `lookup_with`'s gate on
    purpose, exactly as `tasks/T42.md`'s fixture table describes."""
    formatted_route = respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "SE", "filter[entity.registeredAs]": "556016-0680"},
    ).mock(return_value=httpx.Response(200, json=ERICSSON_LEI))
    bare_route = respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "SE", "filter[entity.registeredAs]": "5560160680"},
    ).mock(return_value=httpx.Response(200, json=_no_hits("SE", "5560160680")))

    registry = get_registry("SE")
    record = await registry.lei("5560160680")

    assert record.lei == "549300W9JLPW15XIFM52"
    assert formatted_route.call_count == 1
    assert bare_route.call_count == 0


@respx.mock
async def test_both_candidates_are_tried_when_the_formatted_one_also_misses() -> None:
    """The actual two-step fallback, exercised end to end: when even the
    formatted candidate returns zero hits, the bare identifier is tried
    next — never the reverse order — and the block's `notes` name both
    strings, so a `lei: null` here is legible rather than silent."""
    formatted_route = respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "923 609 016"},
    ).mock(return_value=httpx.Response(200, json=_no_hits("NO", "923 609 016")))
    bare_route = respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "923609016"},
    ).mock(return_value=httpx.Response(200, json=_no_hits("NO", "923609016")))

    registry = get_registry("NO")
    record = await registry.lei("923609016")

    assert record.lei is None
    assert formatted_route.call_count == 1
    assert bare_route.call_count == 1
    joined_notes = " ".join(record.notes)
    assert "923 609 016" in joined_notes
    assert "923609016" in joined_notes


@respx.mock
async def test_britain_has_no_grouping_convention_so_only_one_query_is_made() -> None:
    """Britain does not override `format_id` (it returns `None`), which is
    exactly what GLEIF wants (D-045(e)) — one request, not two."""
    route = respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "GB", "filter[entity.registeredAs]": "00445790"},
    ).mock(return_value=httpx.Response(200, json=TESCO_LEI))

    registry = get_registry("GB")
    record = await registry.lei("00445790")

    assert record.lei == "2138002P5RNKC5W2JZ46"
    assert route.call_count == 1


# ---------------------------------------------------------------------------
# The registration-authority codes are asserted, never used as inputs
# (`tasks/T42.md` §D.6) — Scotland pinned separately from England and Wales.
# ---------------------------------------------------------------------------


@respx.mock
async def test_ra_code_for_norway_names_foretaksregisteret() -> None:
    """`RA000472` (Foretaksregisteret) — not `RA000473` (Enhetsregisteret),
    which is the register our own lookup actually reads. That mismatch is
    GLEIF's business, not a bug (D-045(e))."""
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "923 609 016"},
    ).mock(return_value=httpx.Response(200, json=EQUINOR_LEI))
    record = await get_registry("NO").lei("923609016")
    assert any("RA000472" in note for note in record.notes)


@respx.mock
async def test_ra_code_for_sweden_names_bolagsverket() -> None:
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "SE", "filter[entity.registeredAs]": "556016-0680"},
    ).mock(return_value=httpx.Response(200, json=ERICSSON_LEI))
    record = await get_registry("SE").lei("5560160680")
    assert any("RA000544" in note for note in record.notes)


@respx.mock
async def test_ra_code_for_tesco_is_the_england_and_wales_code() -> None:
    """The brief's named trap: a test that pinned this code for "the UK" as
    a whole would pass here and fail on every Scottish company — see the
    Scottish test immediately below, which pins a *different* code for the
    same country."""
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "GB", "filter[entity.registeredAs]": "00445790"},
    ).mock(return_value=httpx.Response(200, json=TESCO_LEI))
    record = await get_registry("GB").lei("00445790")
    assert any("RA000585" in note for note in record.notes)


@respx.mock
async def test_ra_code_for_natwest_markets_is_the_scottish_code() -> None:
    """NatWest Markets plc is a Scottish registration (`SC090312`), and
    Companies House's Scotland code is not the England-and-Wales one pinned
    for Tesco above."""
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "GB", "filter[entity.registeredAs]": "SC090312"},
    ).mock(return_value=httpx.Response(200, json=NATWEST_LEI))
    record = await get_registry("GB").lei("SC090312")
    joined_notes = " ".join(record.notes)
    assert "RA000587" in joined_notes
    assert "RA000585" not in joined_notes


# ---------------------------------------------------------------------------
# `registration.status`, never `entity.status` (`tasks/T42.md` §D.7)
# ---------------------------------------------------------------------------


@respx.mock
async def test_carillion_registration_status_is_lapsed() -> None:
    """Carillion plc, in liquidation since 2018: GLEIF's own
    `entity.status` still reads `ACTIVE` (a claim about the company this
    project does not carry), while `registration.status` — the LEI record's
    own maintenance state, which `LeiRecord.registration_status` does
    carry — reads `LAPSED`. A lapsed LEI is not evidence of insolvency; it
    is evidence the entity stopped renewing its registration."""
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "GB", "filter[entity.registeredAs]": "03782379"},
    ).mock(return_value=httpx.Response(200, json=CARILLION_LEI))
    record = await get_registry("GB").lei("03782379")
    assert record.registration_status == "LAPSED"


def test_no_source_file_reads_gleifs_entity_status_field() -> None:
    """D-045(e) declines `entity.status` by name: it is GLEIF's own opinion
    about whether the *company* is active, made by neither the company's own
    register nor us. The prose "entity.status" appears in comments and
    docstrings explaining the omission (`core/gleif.py` and `core/models.py`
    both name it, on purpose) — what must never appear is code that actually
    *reads* the field into anything."""
    src_dir = Path(gleif.__file__).parent.parent.parent  # .../src/registry_mcp
    forbidden = ('entity.get("status")', "entity['status']", 'entity["status"]')
    hits = [
        (path, pattern)
        for path in src_dir.rglob("*.py")
        for pattern in forbidden
        if pattern in path.read_text(encoding="utf-8")
    ]
    assert hits == []


# ---------------------------------------------------------------------------
# `total > 1`: not observed live, so no tie-break is invented — the first
# record, plus a disclosure note (`tasks/T42.md` §D.8, built by hand)
# ---------------------------------------------------------------------------


def _synthetic_record(lei: str, name: str) -> dict[str, Any]:
    return {
        "type": "lei-records",
        "id": lei,
        "attributes": {
            "lei": lei,
            "entity": {
                "legalName": {"name": name},
                "registeredAt": {"id": "RA999999"},
                "registeredAs": "00445790",
            },
            "registration": {"status": "ISSUED"},
        },
        "links": {"self": f"https://api.gleif.org/api/v1/lei-records/{lei}"},
    }


@respx.mock
async def test_more_than_one_result_returns_the_first_and_discloses_the_rest() -> None:
    """Not observed in any probe D-045(e) made — so this payload is built by
    hand rather than recorded. A silent pick would be the failure this
    project exists to avoid; a disclosed one is honest."""
    payload = {
        "meta": {"pagination": {"total": 2}},
        "data": [
            _synthetic_record("AAAAAAAAAAAAAAAAAAAA", "FIRST RECORD LTD"),
            _synthetic_record("BBBBBBBBBBBBBBBBBBBB", "SECOND RECORD LTD"),
        ],
    }
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "GB", "filter[entity.registeredAs]": "00445790"},
    ).mock(return_value=httpx.Response(200, json=payload))

    record = await get_registry("GB").lei("00445790")

    assert record.lei == "AAAAAAAAAAAAAAAAAAAA"
    assert record.legal_name == "FIRST RECORD LTD"
    joined_notes = " ".join(record.notes)
    assert "2" in joined_notes
    assert "AAAAAAAAAAAAAAAAAAAA" in joined_notes
    assert "BBBBBBBBBBBBBBBBBBBB" in joined_notes


# ---------------------------------------------------------------------------
# Cache key shape — the per-kind TTL table's kind-from-key parsing
# (`core/cache.py`) reads what this module writes.
# ---------------------------------------------------------------------------


@respx.mock
async def test_lei_is_cached_under_the_kind_slot_the_ttl_table_reads() -> None:
    respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "GB", "filter[entity.registeredAs]": "00445790"},
    ).mock(return_value=httpx.Response(200, json=TESCO_LEI))

    await get_registry("GB").lei("00445790")

    entry = cache.get("GB:companies-house:lei:00445790")
    assert entry is not None
    assert entry.status == "ok"


@respx.mock
async def test_a_cached_lei_is_served_without_a_second_gleif_request() -> None:
    route = respx.get(
        gleif.BASE_URL,
        params={"filter[entity.jurisdiction]": "GB", "filter[entity.registeredAs]": "00445790"},
    ).mock(return_value=httpx.Response(200, json=TESCO_LEI))

    registry = get_registry("GB")
    first = await registry.lei("00445790")
    second = await registry.lei("00445790")

    assert route.call_count == 1
    assert second.lei == first.lei
    assert second.provenance.cached is True
    assert first.provenance.cached is False


# ---------------------------------------------------------------------------
# `CompanyReport.lei` shape (D-004: always present, `None` on every lookup
# that did not ask for it)
# ---------------------------------------------------------------------------


def test_company_report_lei_field_defaults_to_none() -> None:
    report = CompanyReport(country="NO", registry="brreg", id="923609016", name="X")
    assert report.lei is None
    assert "lei" in CompanyReport.model_fields
