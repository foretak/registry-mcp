"""Tests for `registries/se/client.py` and `registries/se/mapping.py`.

Numbered tests 79-118 of `SWEDEN_SPEC.md` §14 ("F. Mapping" / "G. Client" /
"H. Live done-check"), named `test_NN_<slug>` to match
`tests/test_rules_se.py`'s convention. 113-118 are `@pytest.mark.live` and
excluded from CI (`pytest -m "not live"`) — deselected by the marker
regardless of credentials, so they are written but always skipped by the
`-m "not live"` run this suite is checked with. Bolagsverket TEST credentials
exist as of T26g (2026-09-07, `~/secrets/registry-mcp/bolagsverket-test.txt`,
not wired into this test environment's variables) — the eight `bv_*.json`
fixtures loaded below that are real recordings, rather than assembled ones,
were made with them; see `tests/fixtures/README.md`.
"""

from __future__ import annotations

import ast
import copy
import io
import json
import logging
import time
import uuid
import warnings
import zipfile
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from registry_mcp.core.models import CompanyStatus, ErrorCode, FinancialPeriod, RegistryError
from registry_mcp.core.registry import DEADLINE_INCLUDES, get_registry
from registry_mcp.registries.se import client as client_module
from registry_mcp.registries.se import filings, ixbrl, mapping
from registry_mcp.registries.se import financials as financials_module

FIXTURES = Path(__file__).parent / "fixtures"

PRODUCTION_BASE = "https://gw.api.bolagsverket.se/vardefulla-datamangder/v1"
PRODUCTION_TOKEN = "https://portal.api.bolagsverket.se/oauth2/token"
TEST_BASE = "https://gw-accept2.api.bolagsverket.se/vardefulla-datamangder/v1"
TEST_TOKEN = "https://portal-accept2.api.bolagsverket.se/oauth2/token"


def _load(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return result


AB_ACTIVE = _load("bv_ab_active.json")
AB_DORMANT = _load("bv_ab_dormant.json")
AB_KONKURS = _load("bv_ab_konkurs.json")
AB_KK_AND_LI = _load("bv_ab_kk_and_li.json")
AB_REKONSTRUKTION = _load("bv_ab_rekonstruktion.json")
AB_FUSION_OVERTAGANDE = _load("bv_ab_fusion_overtagande.json")
AB_AVREGISTRERAD = _load("bv_ab_avregistrerad.json")
ENSKILD_TWO = _load("bv_enskild_two.json")
SCB_ONLY = _load("bv_scb_only.json")
UPPGIFTSKALLA_FEL = _load("bv_uppgiftskalla_fel.json")
FINNS_EJ = _load("bv_finns_ej.json")
BODY_400 = _load("bv_400.json")
BODY_401 = _load("bv_401.json")
BODY_403 = _load("bv_403.json")
BODY_500 = _load("bv_500.json")
TOKEN_BODY = _load("bv_token.json")

# T26g: recorded 2026-09-07 against the Bolagsverket TEST environment (real
# companies, real legal forms we had no fixture for before). See
# `tests/fixtures/README.md` "SE — Bolagsverket" and `SWEDEN_SPEC.md` §17.
HB_ACTIVE = _load("bv_hb_active.json")
BRF_ACTIVE = _load("bv_brf_active.json")
EK_ACTIVE = _load("bv_ek_active.json")
ENSKILD_AVREGISTRERAD = _load("bv_enskild_avregistrerad.json")
ENSKILD_THREE = _load("bv_enskild_three.json")

# T57 (2026-09-09): every name `bv_enskild_two.json`, `bv_enskild_avregistrerad.json`,
# `bv_enskild_three.json` and `bv_finns_ej.json` carry — real TEST recordings and
# Bolagsverket's own OpenAPI example alike — has been replaced in the fixture with a
# marked placeholder (`[REDACTED TEST NAME]`, or `1`/`2` where a fixture's test logic
# needs two distinguishable values) per D-039/D-040: "no fixture may be committed
# that carries a natural person's name ... keep the shape, replace the name with a
# marked placeholder." See `tests/fixtures/README.md` "Redaction". Identifiers,
# dates, addresses and every other field are untouched.


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_PATH", str(tmp_path / "cache.sqlite3"))
    monkeypatch.delenv("REGISTRY_MCP_CACHE_DISABLED", raising=False)
    monkeypatch.delenv("REGISTRY_MCP_CACHE_TTL_SECONDS", raising=False)
    yield


@pytest.fixture(autouse=True)
def _credentials(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Live tests (`-m live`) need real credentials from the caller's
    # environment; only the mocked (`not live`) tests get the fake
    # credentials that test_112 asserts never leak anywhere.
    if request.node.get_closest_marker("live") is None:
        monkeypatch.setenv("BOLAGSVERKET_CLIENT_ID", "test-client-id-should-never-leak")
        monkeypatch.setenv("BOLAGSVERKET_CLIENT_SECRET", "test-client-secret-should-never-leak")
        monkeypatch.delenv("BOLAGSVERKET_ENVIRONMENT", raising=False)
    yield


@pytest.fixture(autouse=True)
async def _reset_http_client() -> AsyncIterator[None]:
    client_module._client = None
    client_module._tokens.clear()
    yield
    await client_module.aclose()


def _mock_token(base_url: str = PRODUCTION_TOKEN, **kwargs: Any) -> respx.Route:
    return respx.post(base_url).mock(return_value=httpx.Response(200, json=TOKEN_BODY), **kwargs)


def _mock_data(
    body: dict[str, Any], base_url: str = PRODUCTION_BASE, status: int = 200
) -> respx.Route:
    return respx.post(f"{base_url}/organisationer").mock(
        return_value=httpx.Response(status, json=body)
    )


# ---------------------------------------------------------------------------
# F. Mapping — pure, no network (79-98)
# ---------------------------------------------------------------------------


def test_79_core_fields() -> None:
    """Amended 2026-09-07 (T26g): `bv_ab_active.json` is now the real recording
    of `5560021361` (SWEDEN_SPEC.md §17), not the assembled `5299999994`
    shape. `name`/`id`/`id_formatted` follow the fixture's own embedded
    `organisationsidentitet`, which now wins over the requested id below —
    matching what a real lookup of this number returns."""
    report = mapping.map_entity(AB_ACTIVE, "5560021361")
    assert report.name == "Testbolag 4 bokat av SKV Aktiebolag"
    assert report.legal_form_code == "AB"
    assert report.status is CompanyStatus.ACTIVE
    assert report.id == "5560021361"
    assert report.id_formatted == "556002-1361"
    # T33: the wire's typ.kod is "ORGNR" for this record (not the documented
    # "ORGANISATIONSNUMMER") — id_scheme is unaffected by that either way.
    assert report.id_scheme == "organisationsnummer"


def test_80_previous_names_empty_and_n12() -> None:
    """Amended 2026-09-07 (T26g): the real `5560021361` recording publishes
    only one name (no `SARSKILT_FORETAGSNAMN`, no foreign-language name), so
    N12 is not demonstrated by *this* fixture any more — `previous_names`
    stays `[]` either way. N12 with a real multi-name list is now proven by
    `test_94_scb_only` below, against the real `5567223705` recording (three
    names)."""
    report = mapping.map_entity(AB_ACTIVE, "5560021361")
    assert report.previous_names == []
    assert not any("also publishes these names" in n for n in report.notes)


def test_81_industry_codes() -> None:
    report = mapping.map_entity(AB_ACTIVE, "5560021361")
    assert len(report.industry_codes) == 2
    first, second = report.industry_codes
    assert first.code == "46699"
    assert first.description == "Partihandel med diverse andra maskiner och diverse annan utrustning"
    assert first.scheme == "SNI 2007"
    assert first.rank == 1
    assert second.code == "46620"
    assert second.rank == 2


def test_82_dates() -> None:
    report = mapping.map_entity(AB_ACTIVE, "5560021361")
    assert report.registered_at == date(1898, 2, 28)
    assert report.founded_at is None


def test_83_postal_address() -> None:
    """Amended 2026-09-07 (T26g): the real recording's address has no
    `coAdress` and no `land` (both `null`), unlike the assembled fixture —
    `country_code` still resolves to `"SE"` from the §3 absent-`land` rule,
    and `country_name` is honestly `None` rather than `"Sverige"`."""
    report = mapping.map_entity(AB_ACTIVE, "5560021361")
    assert report.postal_address is not None
    assert report.postal_address.lines == ["Testgatan 1"]
    assert report.postal_address.postal_code == "85181"
    assert report.postal_address.city == "SUNDSVALL"
    assert report.postal_address.country_code == "SE"
    assert report.postal_address.country_name is None
    assert report.business_address is None


def test_84_activity_is_trimmed() -> None:
    report = mapping.map_entity(AB_ACTIVE, "5560021361")
    assert report.activity == "Testverksamhet"


def test_85_unpublished_fields_are_honestly_none() -> None:
    report = mapping.map_entity(AB_ACTIVE, "5560021361")
    assert report.employees is None
    assert report.employees_reported is False
    assert report.vat_registered is None
    assert report.vat_number is None
    assert report.share_capital is None
    assert report.website is None
    assert report.email is None
    assert report.phone is None
    assert report.parent_id is None
    assert report.is_subunit is False
    assert report.registers == {}
    assert report.published_deadlines == []
    assert report.sector_code is None


def test_86_reklamsparr_note() -> None:
    """Amended 2026-09-07 (T26g): none of the eight Bolagsverket TEST
    companies recorded for this project carries `reklamsparr.kod == "JA"` —
    the real `bv_ab_active.json` has `reklamsparr: null`, so N4 is not
    reachable through *this* fixture any more. `advertising_protected is
    None` and no N4 is the honest assertion for the real recording; the
    `"JA"` -> N4 branch stays covered synthetically by
    `test_122_reklamsparr_ja_sets_advertising_protected_true_and_n4` in
    `tests/test_rules_se.py` (SWEDEN_SPEC.md §14 test 122)."""
    report = mapping.map_entity(AB_ACTIVE, "5560021361")
    assert report.advertising_protected is None
    assert not any("reklamspärr" in n.lower() for n in report.notes)


def test_87_dormant_active_with_n3() -> None:
    report = mapping.map_entity(AB_DORMANT, "5299999994")
    assert report.status is CompanyStatus.ACTIVE
    assert report.is_active is True
    assert any("Statistics Sweden" in n for n in report.notes)


def test_88_konkurs() -> None:
    """Amended 2026-09-09 (T57): `bv_ab_konkurs.json` is now the real recording
    of `5560986878` ("Testdata 1 AB") — found live by trying, against the TEST
    environment, the `tasks/T26-recon.md` "also permitted" identifiers T26g had
    not yet queried (5562820745, 5560986878, 5560004755, 198101012386).
    `bankruptcy_date` is the real 2025-06-12, not the assembled example's
    2024-01-26 (`SWEDEN_SPEC.md` §1.8/§17 updated to match)."""
    report = mapping.map_entity(AB_KONKURS, "5560986878")
    assert report.status is CompanyStatus.BANKRUPT
    assert report.bankruptcy_date == date(2025, 6, 12)
    assert report.id == "5560986878"
    assert report.name == "Testdata 1 AB"


def test_89_fusion_overtagande_active_plus_note() -> None:
    report = mapping.map_entity(AB_FUSION_OVERTAGANDE, "5299999994")
    assert report.status is CompanyStatus.ACTIVE
    assert report.notes


def test_90_avregistrerad_datetime_shaped_date() -> None:
    report = mapping.map_entity(AB_AVREGISTRERAD, "5299999994")
    assert report.status is CompanyStatus.DELETED
    assert report.deregistered_at == date(2023, 5, 5)


def test_91_enskild_two_one_report_from_first_element() -> None:
    report = mapping.map_entity(ENSKILD_TWO, "194009272719")
    assert report.id == "194009272719"
    assert report.id_scheme == "personnummer"
    assert report.name == "[REDACTED TEST NAME 1]"
    assert report.legal_form_code == "E"
    assert report.activity == "HANDEL MED SKOR."
    assert report.postal_address is not None
    assert report.postal_address.city == "ESLÖV"


def test_92_enskild_two_n7_and_n8() -> None:
    report = mapping.map_entity(ENSKILD_TWO, "194009272719")
    assert any(
        "[REDACTED TEST NAME 1]" in n
        and "[REDACTED TEST NAME 2]" in n
        and "namnskyddslöpnummer 1" in n
        and "namnskyddslöpnummer 2" in n
        for n in report.notes
    )
    assert any("personnummer" in n and "personal data" in n for n in report.notes)


def test_93_no_note_repeats_the_personnummer() -> None:
    report = mapping.map_entity(ENSKILD_TWO, "194009272719")
    assert not any("194009272719" in n for n in report.notes)


def test_94_scb_only() -> None:
    """Amended 2026-09-07 (T26g): `bv_scb_only.json` is now the real recording
    of `5567223705` — the workbook's "Aktiebolag, organisation finns ej hos
    SCB" scenario (SWEDEN_SPEC.md §17) — and the real mechanism is different
    from what the assembled fixture guessed. The assembled version made
    `organisationsform` entirely **absent** so `legal_form_code` fell back to
    SCB's `juridiskForm` (`"49"`, with N5). The real wire instead keeps
    `organisationsform` intact (`"AB"`, no `fel`) and puts
    `fel.typ == "ORGANISATION_FINNS_EJ"` on the *SCB-sourced* fields
    (`juridiskForm`, `verksamOrganisation`, `naringsgrenOrganisation`) —
    exactly `test_119`'s constructed scenario (T26e fix 4), now confirmed
    against the real thing: `is_not_found` stays `False` and the report maps
    as an active `AB`, not an SCB-classified `"49"`. §14 test 94's text
    ("`legal_form_code == \"49\"` and `notes` contains N5") describes the old
    assembled fixture and is now stale pending a spec correction; this is the
    live-verified replacement.

    The three-name list (real, not assembled) also gives N12 real coverage
    that `bv_ab_active.json` lost when it became a single-name real
    recording (`test_80`)."""
    assert mapping.is_not_found(SCB_ONLY) is False
    assert mapping.is_partial_failure(SCB_ONLY) is False
    report = mapping.map_entity(SCB_ONLY, "5567223705")
    assert report.legal_form_code == "AB"
    assert report.status is CompanyStatus.ACTIVE
    assert report.name == "Testbolaget Aktiebolag"
    assert not any("Statistics Sweden" in n for n in report.notes)
    # naringsgrenOrganisation is blocked by the same (non-blocking) fel type,
    # so it maps to no industry codes rather than raising or faking data.
    assert report.industry_codes == []
    assert any(
        "Blv Banken med privilier att automatisera alla transaktioner" in n
        and "Blv PF Banken med privilier att automatisera alla transaktioner" in n
        for n in report.notes
    )


def test_95_uppgiftskalla_fel_constructs_without_raising() -> None:
    """T26b's chosen behaviour (either is permitted by the spec): construct
    without raising, `name` falls back to the identifier, and note N13 names
    the unavailable producer. Amended 2026-09-06 (T26e fix 3): the report's
    `status` is `UNKNOWN` and `is_active` is `False` (§8 rung 0), never
    `ACTIVE` — a blocked status-bearing field must not be read as silent
    good standing."""
    report = mapping.map_entity(UPPGIFTSKALLA_FEL, "194009272719")
    assert report.name == "194009272719"
    assert report.id == "194009272719"
    assert any("could not be retrieved" in n and "Bolagsverket" in n for n in report.notes)
    assert report.status is CompanyStatus.UNKNOWN
    assert report.is_active is False


def test_96_finns_ej_detected_as_not_found() -> None:
    """Amended 2026-09-07 (T26g): `bv_finns_ej.json` is now the real recording
    of `198101032384`, not `193403223328` — the workbook/§17 table had the
    two numbers' scenarios swapped (`193403223328` is a real, deregistered,
    two-business sole trader that maps fine; `198101032384` is the one that
    actually carries `fel.typ == "ORGANISATION_FINNS_EJ"` on
    `organisationsform`). See `SWEDEN_SPEC.md` §17 and
    `test_enskild_avregistrerad_fixture_is_deleted` below for the corrected
    `193403223328`."""
    assert mapping.is_not_found(FINNS_EJ) is True


def test_97_registreringsland_never_read() -> None:
    data = copy.deepcopy(AB_ACTIVE)
    data["organisationer"][0]["registreringsland"] = {"kod": "XX-LAND", "klartext": "Nowhereland"}
    report = mapping.map_entity(data, "5560021361")
    assert report.country == "SE"


def test_119_scb_only_finns_ej_is_not_not_found_and_maps_active() -> None:
    """§6.3, T26e fix 4: `ORGANISATION_FINNS_EJ` on an SCB-sourced field
    (`juridiskForm`, `verksamOrganisation`, `reklamsparr`) means only that
    Statistics Sweden lacks the entity — the workbook's own `5567223705`
    scenario — while Bolagsverket's own identity-bearing fields
    (`organisationsnamn`, `organisationsform`, `organisationsdatum`) still
    carry the organisation. `is_not_found` must stay `False` and the report
    must still map, as an active AB."""
    data = copy.deepcopy(AB_ACTIVE)
    org = data["organisationer"][0]
    finns_ej_fel = {
        "felBeskrivning": (
            "Begärd organisation finns inte registrerad i sökbar form hos aktuell "
            "dataproducent."
        ),
        "typ": "ORGANISATION_FINNS_EJ",
    }
    for field in ("juridiskForm", "verksamOrganisation", "reklamsparr"):
        org[field] = {"fel": finns_ej_fel, "dataproducent": "SCB"}

    assert mapping.is_not_found(data) is False
    report = mapping.map_entity(data, "5299999994")
    assert report.status is CompanyStatus.ACTIVE
    assert report.legal_form_code == "AB"


def test_120_blocked_status_field_gives_unknown_not_active() -> None:
    """§8 rung 0, T26e fix 3: a blocking `fel` on a status-bearing field
    (here `pagaende...Lista`, via `TIMEOUT`) must not be read as silent good
    standing — `status` is `UNKNOWN`, `is_active` is `False`,
    `status_detail` names the producer, and N13 still fires."""
    data = copy.deepcopy(AB_ACTIVE)
    org = data["organisationer"][0]
    org["pagaendeAvvecklingsEllerOmstruktureringsforfarande"] = {
        "pagaendeAvvecklingsEllerOmstruktureringsforfarandeLista": None,
        "fel": {
            "felBeskrivning": "Uppkoppling mot Bolagsverket misslyckades.",
            "typ": "TIMEOUT",
        },
        "dataproducent": "Bolagsverket",
    }
    report = mapping.map_entity(data, "5299999994")
    assert report.status is CompanyStatus.UNKNOWN
    assert report.is_active is False
    assert report.status_detail is not None and "Bolagsverket" in report.status_detail
    assert any("could not be retrieved" in n and "Bolagsverket" in n for n in report.notes)


def test_121_kk_and_fuot_bankrupt_keeps_fuot_bucket2_note() -> None:
    """§8 "the lower rungs still fill their own fields and notes", T26e fix
    15(a): a co-occurring bucket-2 code (`FUOT`) must not have its note
    silently dropped just because a bucket-1 code (`KK`) decided `status`."""
    data = copy.deepcopy(AB_ACTIVE)
    org = data["organisationer"][0]
    org["pagaendeAvvecklingsEllerOmstruktureringsforfarande"] = {
        "pagaendeAvvecklingsEllerOmstruktureringsforfarandeLista": [
            {"kod": "KK", "klartext": "Konkurs", "fromDatum": "2024-01-26"},
            {"kod": "FUOT", "klartext": "Övertagande i fusion", "fromDatum": "2024-02-01"},
        ],
        "fel": None,
        "dataproducent": "Bolagsverket",
    }
    report = mapping.map_entity(data, "5299999994")
    assert report.status is CompanyStatus.BANKRUPT
    assert report.bankruptcy_date == date(2024, 1, 26)
    assert any("acquiring" in n.lower() and "fusion" in n.lower() for n in report.notes)


def test_126_bucket2_only_with_a_status_field_blocked_gives_unknown_not_active() -> None:
    """Review fix 2 (T30, `REVIEW.md` "T26f + T28 + T29"): §8's bucket-2-only branch
    ("leaves status alone") returned a bare `ACTIVE` without ever consulting
    `unavailable_producer` — an affirmative "not struck off" from a payload where the
    struck-off fields never arrived. Here `pagaende...Lista = [FUOT]` (a healthy
    acquiring company, rung 2) is unblocked and populated, while
    `avregistreradOrganisation` (rung 1's own field) is blocked by a `fel` — the
    produced status must be `UNKNOWN`, not `ACTIVE`, and the FUOT note must still be
    present (§8: "the lower rungs still fill their own fields and notes").

    Practical reachability note (from the fix): Bolagsverket's own partial-failure
    fixture (`UPPGIFTSKALLA_FEL`) fails a whole data producer at once, which would
    block `pagaende...` too and so never exercise this combination — this test
    constructs the needed *per-field* failure directly, which §1.6 models but no
    committed fixture does.
    """
    data = copy.deepcopy(AB_ACTIVE)
    org = data["organisationer"][0]
    org["pagaendeAvvecklingsEllerOmstruktureringsforfarande"] = {
        "pagaendeAvvecklingsEllerOmstruktureringsforfarandeLista": [
            {"kod": "FUOT", "klartext": "Övertagande i fusion", "fromDatum": "2024-02-01"},
        ],
        "fel": None,
        "dataproducent": "Bolagsverket",
    }
    org["avregistreradOrganisation"] = {
        "avregistreringsdatum": None,
        "fel": {
            "felBeskrivning": "Uppkoppling mot Bolagsverket misslyckades.",
            "typ": "TIMEOUT",
        },
        "dataproducent": "Bolagsverket",
    }
    report = mapping.map_entity(data, "5299999994")
    assert report.status is CompanyStatus.UNKNOWN
    assert report.is_active is False
    assert report.status_detail is not None and "Bolagsverket" in report.status_detail
    assert any("acquiring" in n.lower() and "fusion" in n.lower() for n in report.notes)


def test_98_misspelled_pagande_key_still_detects_bankruptcy() -> None:
    """The Altinn bug (§15): the schema spells it
    `pagaendeAvvecklingsEllerOmstruktureringsforfarande`, but Bolagsverket's
    own aktiebolag example misspells it `pagande...`. Both spellings, at both
    the outer wrapper and the inner `...Lista`, must be read — this test
    pins the failure mode that reports a bankrupt company as active."""
    data = copy.deepcopy(AB_ACTIVE)
    org = data["organisationer"][0]
    del org["pagaendeAvvecklingsEllerOmstruktureringsforfarande"]
    org["pagandeAvvecklingsEllerOmstruktureringsforfarande"] = {
        "pagandeAvvecklingsEllerOmstruktureringsforfarandeLista": [
            {"kod": "KK", "klartext": "Konkurs", "fromDatum": "2024-01-26"}
        ],
        "fel": None,
        "dataproducent": "Bolagsverket",
    }
    report = mapping.map_entity(data, "5299999994")
    assert report.status is CompanyStatus.BANKRUPT
    assert report.bankruptcy_date == date(2024, 1, 26)


def test_kk_and_li_fixture_maps_bankrupt() -> None:
    """Non-numbered: `bv_ab_kk_and_li.json` and `bv_ab_rekonstruktion.json`
    are named in §1.8's fixture table but not consumed by a numbered mapping
    test directly (43-60 exercise the same logic through constructed
    payloads) — validated here so they stay live, correctly-shaped fixtures."""
    report = mapping.map_entity(AB_KK_AND_LI, "5299999994")
    assert report.status is CompanyStatus.BANKRUPT
    assert report.bankruptcy_date == date(2024, 1, 26)


def test_rekonstruktion_fixture_maps_under_liquidation() -> None:
    report = mapping.map_entity(AB_REKONSTRUKTION, "5299999994")
    assert report.status is CompanyStatus.UNDER_LIQUIDATION


# ---------------------------------------------------------------------------
# T26g: legal forms recorded for the first time against the real Bolagsverket
# TEST environment (2026-09-07) — no fixture exercised HB/BRF/EK before, and
# none used a real (rather than assembled) sole-trader deregistration or a
# real sole trader with more than one registered business. Non-numbered:
# these post-date SWEDEN_SPEC.md §14's list, same convention as
# `test_kk_and_li_fixture_maps_bankrupt` above.
# ---------------------------------------------------------------------------


def test_hb_fixture_maps_general_partnership_no_deadlines() -> None:
    report = mapping.map_entity(HB_ACTIVE, "9124001992")
    assert report.name == "Testbolag 16 bokat av SKV Handelsbolag"
    assert report.legal_form_code == "HB"
    assert report.legal_form == "General partnership"
    assert report.status is CompanyStatus.ACTIVE
    assert report.has_board_duty is False
    assert report.has_annual_accounts_duty is None
    assert report.limited_liability is False
    # HB is neither AB nor EK (rules.DEADLINE_FORM_CODES), so §5.5's "no
    # computed deadlines" note fires instead of a calendar-year one.
    assert any(
        "computes filing deadlines only for aktiebolag" in n and "General partnership" in n
        for n in report.notes
    )


def test_brf_fixture_maps_tenant_owners_association() -> None:
    """Also exercises `naringsgrenOrganisation.sni` padding-removal (§2,
    `test_129`/`test_130`'s logic in `test_rules_se.py`) against a real body
    with three live codes — every other SE fixture in this file has at most
    two, so this is the only one that proves the padding-removal survives a
    third real entry, not just a second."""
    report = mapping.map_entity(BRF_ACTIVE, "7164099017")
    assert report.name == "Testbolag 24 bokat av SKV Bostadsrättsförening"
    assert report.legal_form_code == "BRF"
    assert report.legal_form == "Tenant-owners' (housing) association"
    assert report.status is CompanyStatus.ACTIVE
    assert report.has_board_duty is True
    assert report.has_annual_accounts_duty is None
    assert report.limited_liability is True
    assert [c.code for c in report.industry_codes] == ["68310", "35300", "35140"]
    assert [c.rank for c in report.industry_codes] == [1, 2, 3]
    assert any(
        "computes filing deadlines only for aktiebolag" in n
        and "Tenant-owners' (housing) association" in n
        for n in report.notes
    )


def test_ek_fixture_maps_economic_association_with_deadline_note() -> None:
    """`EK` is the second of the only two forms in `rules.DEADLINE_FORM_CODES`
    — unlike HB/BRF above, an active EK gets the calendar-year deadline
    note, not the "no computed deadlines" one."""
    report = mapping.map_entity(EK_ACTIVE, "7020008350")
    assert report.name == "Testbolag 25 bokat av SKV Ekonomisk förening"
    assert report.legal_form_code == "EK"
    assert report.legal_form == "Economic (co-operative) association"
    assert report.status is CompanyStatus.ACTIVE
    assert report.has_board_duty is True
    assert report.has_annual_accounts_duty is True
    assert report.limited_liability is True
    assert any("financial year ending 31 December" in n for n in report.notes)


def test_enskild_avregistrerad_fixture_is_deleted() -> None:
    """`193403223328` — the number the workbook and old §17 table called
    "Organisation finns inte registrerad" — is actually a real, deregistered,
    two-business sole trader (SWEDEN_SPEC.md §17, corrected 2026-09-07).
    `is_not_found` is `False` for it: Bolagsverket's own identity-bearing
    fields carry the deregistration, not a `fel`.

    T33 (2026-09-07) fixed two live-confirmed defects this fixture exposed;
    both are pinned below so neither can silently return.

    (1) `verksamOrganisation.kod == "NEJ"` on this record fires N3.
    `_N3_NOTE_ACTIVE`'s "...so is_active is true" clause is false for this
    record (`is_active` is `False` — rung 1, deregistered, outranks rung 3's
    dormancy signal), so `map_entity` now picks `_N3_NOTE_NOT_ACTIVE`
    instead, which keeps the SCB signal and drops the false clause. Before
    the fix, this test pinned the wrong "so is_active is true" wording
    deliberately, as a known, reported-not-fixed contradiction.

    (2) This record's wire `organisationsidentitet.typ.kod` is `"ORGNR"`
    (`{"kod": "ORGNR", "klartext": "Organisationsnummer"}`) — an
    undocumented-but-now-recognised code (`SWEDEN_SPEC.md` §2.4) that maps
    to `id_scheme == "organisationsnummer"`. That value is unchanged by the
    T33 fix (it matched the unrecognised-code default before too) but is now
    reached for the right, documented reason rather than by accident. Worth
    reading twice: `193403223328` is a twelve-digit, personnummer-shaped
    identifier for an `organisationsform.kod == "E"` sole trader — same
    shape as `198101052382` below — yet the wire itself calls it an
    organisationsnummer. `id_scheme` follows the wire's own `typ`, not the
    digit count, so this is correct by construction on what Bolagsverket
    actually sent; whether it should *also* fall back to shape when `typ`
    disagrees with a personnummer-looking twelve digits is a policy
    question T33 reports rather than decides (see its final report; D-032
    already declined to enforce a check digit from an unsourced rule, which
    is the neighbouring but not identical question). N8 fires regardless,
    via `legal_form.code == "E"` (D-039's `or`, still doing its job here
    since `"ORGNR"` was never a personal-id code, before or after T33) —
    the near-miss D-039 built in on purpose."""
    assert mapping.is_not_found(ENSKILD_AVREGISTRERAD) is False
    report = mapping.map_entity(ENSKILD_AVREGISTRERAD, "193403223328")
    assert report.legal_form_code == "E"
    assert report.status is CompanyStatus.DELETED
    assert report.is_active is False
    assert report.deregistered_at == date(2016, 8, 24)
    assert report.status_detail is not None and "OVERK" in report.status_detail
    assert any(
        "This identifier carries 2 registered businesses" in n
        and "[REDACTED TEST NAME 1]" in n
        and "[REDACTED TEST NAME 2]" in n
        for n in report.notes
    )
    assert any("sole trader" in n and "personal data" in n for n in report.notes)
    # (1) N3 fix: the false "so is_active is true" clause is gone, and the
    # corrected wording — still naming Statistics Sweden, still keeping the
    # substance that verksam is a different question from the register
    # status — is present instead.
    assert not any("so is_active is true" in n for n in report.notes)
    assert any(
        "does not mark this organisation as economically active" in n
        and "different question from the register's own status" in n
        for n in report.notes
    )
    # (2) id_scheme: value unchanged (see docstring part 2) but now reached
    # via an explicit, documented "ORGNR" mapping rather than the
    # unrecognised-code fallback.
    assert report.id_scheme == "organisationsnummer"


def test_enskild_three_fixture_three_not_two_and_id_scheme_personnummer() -> None:
    """`198101052382` is the workbook's "enskild firma, två
    namnskyddslöpnummer" number (SWEDEN_SPEC.md §17, §14 test 114) — the real
    TEST recording has **three** (`namnskyddslopnummer` 1, 2 and 3; the last
    two share one name on the wire, redacted here to `[REDACTED TEST NAME 2]`
    per D-039/D-040, T57 2026-09-09). See `test_114_live_enskild_two_...`'s
    amended docstring for the live (`@pytest.mark.live`) version of this same
    finding.

    T33 (2026-09-07) regression pin for defect 1: this record's wire
    `organisationsidentitet.typ.kod` is `"PERSON"`
    (`{"kod": "PERSON", "klartext": "Identitetsbeteckning person"}`), an
    undocumented-but-now-recognised code (`SWEDEN_SPEC.md` §2.4) that must
    map to `id_scheme == "personnummer"`. Before the fix this fell through
    to the unrecognised-code default, `"organisationsnummer"`, on every real
    Swedish sole trader this project could reach — this test used to pin
    that wrong value under the name `..._id_scheme_gap`. N8 now fires via
    *both* halves of D-039's `or` for this record (`typ_kod` is in
    `mapping._PERSONAL_ID_TYP_KODS` now, and `legal_form.code == "E"` still
    holds independently) — either half alone remains sufficient, which is
    why D-039 wrote it as an `or` rather than picking one."""
    report = mapping.map_entity(ENSKILD_THREE, "198101052382")
    assert report.legal_form_code == "E"
    assert report.status is CompanyStatus.ACTIVE
    assert report.name == "[REDACTED TEST NAME 1]"
    assert any(
        "This identifier carries 3 registered businesses" in n
        and "[REDACTED TEST NAME 1]" in n
        and n.count("[REDACTED TEST NAME 2]") == 2
        for n in report.notes
    )
    assert any("sole trader" in n and "personal data" in n for n in report.notes)
    # Defect 1, fixed: was "organisationsnummer" (wrong) before T33.
    assert report.id_scheme == "personnummer"


# ---------------------------------------------------------------------------
# G. Client — respx-mocked, no network (99-112)
# ---------------------------------------------------------------------------


async def test_99_no_credentials_raises_without_http_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOLAGSVERKET_CLIENT_ID", raising=False)
    monkeypatch.delenv("BOLAGSVERKET_CLIENT_SECRET", raising=False)
    with respx.mock:
        token_route = _mock_token()
        data_route = _mock_data(AB_ACTIVE)
        with pytest.raises(RegistryError) as excinfo:
            await client_module.lookup("5560160680")
        assert token_route.call_count == 0
        assert data_route.call_count == 0
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR
    assert "BOLAGSVERKET_CLIENT_ID" in excinfo.value.hint
    assert "BOLAGSVERKET_CLIENT_SECRET" in excinfo.value.hint
    assert "list_countries" in excinfo.value.hint


def test_100_import_succeeds_without_credentials_and_registers_se(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOLAGSVERKET_CLIENT_ID", raising=False)
    monkeypatch.delenv("BOLAGSVERKET_CLIENT_SECRET", raising=False)
    from registry_mcp.core.registry import list_countries

    assert "SE" in list_countries()


async def test_101_only_client_id_set_still_names_both(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOLAGSVERKET_CLIENT_SECRET", raising=False)
    with respx.mock, pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("5560160680")
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR
    assert "BOLAGSVERKET_CLIENT_ID" in excinfo.value.hint
    assert "BOLAGSVERKET_CLIENT_SECRET" in excinfo.value.hint


@respx.mock
async def test_102_two_requests_token_then_data_correct_hosts_and_shapes() -> None:
    token_route = _mock_token()
    data_route = _mock_data(AB_ACTIVE)

    report = await client_module.lookup("5560160680")
    assert report.name == "Testbolag 4 bokat av SKV Aktiebolag"

    assert token_route.call_count == 1
    assert data_route.call_count == 1
    token_request = token_route.calls.last.request
    assert (
        token_request.url == PRODUCTION_TOKEN
    )  # "Assert the token host is portal., not gw." (§1.1)
    assert "portal.api.bolagsverket.se" in str(token_request.url)
    assert token_request.headers["content-type"] == "application/x-www-form-urlencoded"
    body = token_request.content.decode()
    assert "grant_type=client_credentials" in body
    assert "vardefulla-datamangder%3Aread+vardefulla-datamangder%3Aping" in body

    data_request = data_route.calls.last.request
    assert "gw.api.bolagsverket.se" in str(data_request.url)
    assert data_request.headers["authorization"].startswith("Bearer ")
    assert json.loads(data_request.content) == {"identitetsbeteckning": "5560160680"}


@respx.mock
async def test_103_token_reused_within_expiry_refetched_after() -> None:
    token_route = _mock_token()
    respx.post(f"{PRODUCTION_BASE}/organisationer").mock(
        return_value=httpx.Response(200, json=AB_ACTIVE)
    )

    await client_module.lookup("5560160680")
    assert token_route.call_count == 1

    # A second, *different* identifier within the token's expiry (so it is a
    # fresh network fetch, not a report-cache hit) must reuse the token.
    await client_module.lookup("5560986878")
    assert token_route.call_count == 1

    # Force the cached token to look expired: a third, different identifier
    # must now fetch a fresh token.
    client_module._tokens["production"].expires_at = time.monotonic() - 1
    await client_module.lookup("5562820745")
    assert token_route.call_count == 2


@respx.mock
async def test_104_401_triggers_one_refresh_then_raises_on_second() -> None:
    _mock_token()
    data_route = respx.post(f"{PRODUCTION_BASE}/organisationer").mock(
        return_value=httpx.Response(401, json=BODY_401)
    )
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("5560160680")
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR
    assert "BOLAGSVERKET_CLIENT_ID" in excinfo.value.hint
    assert "BOLAGSVERKET_CLIENT_SECRET" in excinfo.value.hint
    assert data_route.call_count == 2  # one attempt, one refresh-and-retry


@respx.mock
async def test_104b_401_then_200_succeeds_with_one_refresh() -> None:
    token_route = _mock_token()
    data_route = respx.post(f"{PRODUCTION_BASE}/organisationer").mock(
        side_effect=[httpx.Response(401, json=BODY_401), httpx.Response(200, json=AB_ACTIVE)]
    )
    report = await client_module.lookup("5560160680")
    assert report.name == "Testbolag 4 bokat av SKV Aktiebolag"
    assert token_route.call_count == 2
    assert data_route.call_count == 2


@respx.mock
async def test_127_token_response_valid_json_not_an_object_is_upstream_error() -> None:
    """Review fix 4 (T30, `REVIEW.md` "T26f + T28 + T29"): T26e fix 13 wrapped
    `ValueError`/`KeyError` around `response.json()`/`body["access_token"]`, but a
    200 whose body is valid JSON and not an object — the literal `b"null"` is the
    simplest example — parses cleanly and then raises a bare `TypeError`
    (`'NoneType' object is not subscriptable`) on the subscript, escaping both
    catches. `TypeError` must be caught the same way and re-raised as
    `upstream_error`, never a bare exception. The data endpoint is deliberately
    left unmocked: if the token failure did not stop the call before it, reaching
    the unmocked route would itself fail this test with the wrong exception type."""
    respx.post(PRODUCTION_TOKEN).mock(return_value=httpx.Response(200, content=b"null"))
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("5560160680")
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR


@respx.mock
async def test_128_data_response_valid_json_not_an_object_is_upstream_error() -> None:
    """Review fix 4 (T30): the data call has the same failure one type further out
    — a 200 whose body is valid JSON and not an object (`b"null"`) parses cleanly
    past the `except ValueError` guard and then raises a bare `AttributeError`
    (`'NoneType' object has no attribute 'get'`) in `mapping.is_not_found`.
    `isinstance(data, dict)` must catch it first and raise `upstream_error`
    instead."""
    _mock_token()
    respx.post(f"{PRODUCTION_BASE}/organisationer").mock(
        return_value=httpx.Response(200, content=b"null")
    )
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("5560160680")
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR


@respx.mock
async def test_105_test_environment_uses_accept2_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOLAGSVERKET_ENVIRONMENT", "test")
    _mock_token(TEST_TOKEN)
    _mock_data(AB_ACTIVE, TEST_BASE)

    report = await client_module.lookup("5560160680")
    assert "test environment" in (report.source or "")
    assert any("test environment" in n for n in report.notes)


async def test_106_unrecognised_environment_raises_no_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOLAGSVERKET_ENVIRONMENT", "wibble")
    with respx.mock:
        token_route = _mock_token()
        data_route = _mock_data(AB_ACTIVE)
        with pytest.raises(RegistryError) as excinfo:
            await client_module.lookup("5560160680")
        assert token_route.call_count == 0
        assert data_route.call_count == 0
    assert "production" in excinfo.value.hint
    assert "test" in excinfo.value.hint


@respx.mock
async def test_107_distinct_request_id_and_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRY_MCP_CONTACT_EMAIL", "se-test@example.com")
    _mock_token()
    data_route = respx.post(f"{PRODUCTION_BASE}/organisationer").mock(
        return_value=httpx.Response(200, json=AB_ACTIVE)
    )
    # Two different identifiers so both are genuine network calls, not a
    # report-cache hit on the second.
    await client_module.lookup("5560160680")
    await client_module.lookup("5560986878")

    ids = [call.request.headers["x-request-id"] for call in data_route.calls]
    assert len(ids) == 2
    assert len(set(ids)) == 2
    for request_id in ids:
        uuid.UUID(request_id)  # raises ValueError if not a valid UUID

    ua = data_route.calls.last.request.headers["user-agent"]
    assert "registry-mcp" in ua
    assert "se-test@example.com" in ua


@respx.mock
async def test_108_search_raises_not_implemented_no_http_request_at_all() -> None:
    token_route = _mock_token()
    data_route = _mock_data(AB_ACTIVE)
    with pytest.raises(RegistryError) as excinfo:
        await client_module.search("volvo")
    assert token_route.call_count == 0
    assert data_route.call_count == 0
    assert excinfo.value.code is ErrorCode.NOT_IMPLEMENTED
    assert "lookup_company" in excinfo.value.hint
    assert "downloadable" in excinfo.value.hint or "bulk" in excinfo.value.hint


async def test_109_search_raises_even_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOLAGSVERKET_CLIENT_ID", raising=False)
    monkeypatch.delenv("BOLAGSVERKET_CLIENT_SECRET", raising=False)
    with pytest.raises(RegistryError) as excinfo:
        await client_module.search("volvo")
    assert excinfo.value.code is ErrorCode.NOT_IMPLEMENTED


@respx.mock
async def test_110_connector_search_alias_drops_se_keeps_no_gb_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-031(c): a `RegistryError` from `search` (here, SE's `not_implemented`)
    drops that country silently and never raises — verified against the real
    connector, not assumed (§4)."""
    monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "gb-test-key")
    from registry_mcp.registries.gb import client as gb_client_module
    from registry_mcp.registries.no import client as no_client_module

    gb_client_module._client = None
    no_client_module._client = None

    brreg = _load("brreg_923609016.json")
    envelope = {
        "_embedded": {"enheter": [brreg]},
        "page": {"size": 1, "totalElements": 1, "totalPages": 1, "number": 0},
    }
    respx.get(f"{no_client_module.BASE_URL}/enheter").mock(
        return_value=httpx.Response(200, json=envelope)
    )
    respx.get(f"{gb_client_module.BASE_URL}/search/companies").mock(
        return_value=httpx.Response(200, json=_load("ch_search_empty.json"))
    )

    from fastmcp import Client

    from registry_mcp.mcp.server import mcp

    async with Client(mcp) as mcp_client:
        result = await mcp_client.call_tool("search", {"query": "Equinor"})
    rows = result.structured_content["results"]
    assert len(rows) == 1
    assert rows[0]["id"] == "NO:923609016"

    await gb_client_module.aclose()
    await no_client_module.aclose()


@respx.mock
async def test_111_finns_ej_not_found_uppgiftskalla_not_cached_second_call_hits_http() -> None:
    """The identifier below is `198101032384`, not the workbook/§17-table
    number `193403223328` this test used before T26g — `FINNS_EJ` is now the
    real recording of `198101032384` (see `test_96`'s docstring)."""
    _mock_token()
    data_route = _mock_data(FINNS_EJ)
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("198101032384")
    assert excinfo.value.code is ErrorCode.NOT_FOUND
    assert "other" in excinfo.value.hint.lower() or "another" in excinfo.value.hint.lower()

    # A partial-failure 200 is mapped, noted, and never cached (§9): the
    # second identical call must hit HTTP again. Re-mocking the same route
    # (`.mock()` on an existing respx Route reconfigures it in place, per
    # respx's own de-duplication-by-pattern behaviour — `.reset()` first so
    # `call_count` below counts only this phase's two calls.)
    data_route.reset()
    data_route.mock(return_value=httpx.Response(200, json=UPPGIFTSKALLA_FEL))
    await client_module.lookup("194009272719")
    await client_module.lookup("194009272719")
    assert data_route.call_count == 2


@respx.mock
async def test_112_cache_400_500_retry_and_no_secret_leak(caplog: pytest.LogCaptureFixture) -> None:
    """Bundles the last cluster of §14 assertions into one test function, per
    the numbered list. `data_route` is one respx ``Route`` reconfigured
    (``.mock()`` again) and ``.reset()`` between phases — respx matches by
    URL pattern, so re-registering the same ``/organisationer`` route
    returns the *same* object with an accumulating ``call_count`` rather
    than a fresh one; verified directly before relying on it here."""
    secret = "test-client-secret-should-never-leak"

    # Cache hit/miss + fetched_at stability.
    _mock_token()
    data_route = _mock_data(AB_ACTIVE)
    first = await client_module.lookup("5560160680")
    assert first.cached is False
    second = await client_module.lookup("5560160680")
    assert second.cached is True
    assert second.fetched_at == first.fetched_at
    assert data_route.call_count == 1
    data_route.reset()

    # 400 raises invalid_id, not retried.
    data_route.mock(return_value=httpx.Response(400, json=BODY_400))
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("5560160681")
    assert excinfo.value.code is ErrorCode.INVALID_ID
    assert data_route.call_count == 1
    data_route.reset()

    # 500 then 200: exactly one retry.
    data_route.mock(
        side_effect=[httpx.Response(500, json=BODY_500), httpx.Response(200, json=AB_ACTIVE)]
    )
    report = await client_module.lookup("5560986878")
    assert report.name == "Testbolag 4 bokat av SKV Aktiebolag"
    assert data_route.call_count == 2
    data_route.reset()

    # Two 500s: upstream_error, exactly two data calls (not three).
    data_route.mock(
        side_effect=[httpx.Response(500, json=BODY_500), httpx.Response(500, json=BODY_500)]
    )
    with caplog.at_level(logging.DEBUG), pytest.raises(RegistryError) as excinfo2:
        await client_module.lookup("5562820745")
    assert excinfo2.value.code is ErrorCode.UPSTREAM_ERROR
    assert data_route.call_count == 2
    data_route.reset()

    # A 401 and a timeout: the secret and the bearer token appear nowhere.
    data_route.mock(return_value=httpx.Response(401, json=BODY_401))
    with caplog.at_level(logging.DEBUG), pytest.raises(RegistryError) as excinfo3:
        await client_module.lookup("7140000001")
    assert secret not in json.dumps(excinfo3.value.to_dict())
    assert secret not in str(excinfo3.value)
    data_route.reset()

    data_route.mock(side_effect=httpx.TimeoutException("timed out"))
    with caplog.at_level(logging.DEBUG), pytest.raises(RegistryError) as excinfo4:
        await client_module.lookup("9160000001")
    assert secret not in json.dumps(excinfo4.value.to_dict())
    assert secret not in str(excinfo4.value)

    bearer_token = TOKEN_BODY["access_token"]
    for record in caplog.records:
        message = record.getMessage()
        assert secret not in message
        assert bearer_token not in message


# ---------------------------------------------------------------------------
# Bonus (non-numbered): the rate-limit bucket actually raises when exhausted.
# ---------------------------------------------------------------------------


async def test_bucket_exhaustion_raises_rate_limited() -> None:
    bucket = client_module._TokenBucket(60.0, 1.0)
    bucket._tokens = 0.0
    # Push `_updated` into the future so elapsed time is negative and no
    # refill happens during the (short) wait below — deterministic, no real
    # 2-second sleep required to prove the branch.
    bucket._updated = time.monotonic() + 1000.0
    with pytest.raises(RegistryError) as excinfo:
        await bucket.acquire()
    assert excinfo.value.code is ErrorCode.RATE_LIMITED


# ---------------------------------------------------------------------------
# aclose / format_id / validate wiring through the Registry
# ---------------------------------------------------------------------------


@respx.mock
async def test_registry_aclose_closes_client_and_clears_token() -> None:
    _mock_token()
    _mock_data(AB_ACTIVE)
    registry = get_registry("SE")
    await registry.lookup("5560160680")
    http_client = client_module._client
    assert http_client is not None
    # T26e fix 2b: read the property into a fresh annotated local on each
    # side. `assert http_client.is_closed is False` narrows the property to
    # `Literal[False]` for the rest of the function under mypy, which makes
    # the later `is True` check a non-overlapping identity comparison and
    # the `_tokens == {}` assertion after it unreachable code mypy never
    # type-checks (`mypy .`, which is what CI runs, catches this; `mypy src`
    # does not, since this file is a test).
    closed_before: bool = http_client.is_closed
    assert closed_before is False
    assert "production" in client_module._tokens

    await registry.aclose()
    closed_after: bool = http_client.is_closed
    assert closed_after is True
    assert client_module._tokens == {}


def test_format_id_via_registry() -> None:
    registry = get_registry("SE")
    assert registry.format_id("5560160680") == "556016-0680"


# ---------------------------------------------------------------------------
# H. Live done-check — network, `@pytest.mark.live`, excluded from CI (113-118)
# ---------------------------------------------------------------------------


@pytest.mark.live
async def test_113_live_lookup_cached_then_true() -> None:
    first = await client_module.lookup("5560021361")
    assert first.cached is False
    second = await client_module.lookup("5560021361")
    assert second.cached is True


@pytest.mark.live
async def test_114_live_enskild_two_namnskyddslopnummer() -> None:
    """Amended 2026-09-07 (T26g): §14 test 114 and the workbook describe
    `198101052382` as "två namnskyddslöpnummer" (two) — the real TEST
    recording (`bv_enskild_three.json`) has **three**
    (`namnskyddslopnummer` 1, 2, 3; the last two share one name on the wire,
    not repeated here per D-039/D-040, T57 2026-09-09). The
    function name and §14's text are stale pending a spec correction; the
    assertion below matches the confirmed live body. See
    `test_enskild_three_fixture_three_not_two_and_id_scheme_personnummer` for
    the offline (fixture-based) version of this same finding."""
    report = await client_module.lookup("198101052382")
    assert any("This identifier carries 3 registered businesses" in n for n in report.notes)


@pytest.mark.live
async def test_115_live_finns_ej_not_found() -> None:
    """Amended 2026-09-07 (T26g): §14 test 115 names `193403223328` as the
    not-found number to record as `bv_finns_ej.json` — live, it is a real,
    deregistered, two-business sole trader that maps fine (`is_not_found` is
    `False`). `198101032384` is the number that actually raises `not_found`.
    See `SWEDEN_SPEC.md` §17 and `test_96`'s docstring."""
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("198101032384")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


@pytest.mark.live
async def test_116_live_check_digit_experiment_5560000002() -> None:
    """The §5.1.1 experiment. Record the outcome in `REVIEW.md` §T26e
    whichever way it goes: an organisation refutes the modulus-10 caveat, a
    `400 "ogiltig kontrollsiffra"` confirms it. T26e fix 14: `warnings.warn`,
    not `print` — pytest swallows `print` output without `-s`, and this is
    the one live test whose *output* is the deliverable."""
    try:
        report = await client_module.lookup("5560000002")
        warnings.warn(
            f"5560000002 resolved: {report.name!r} — modulus-10 caveat REFUTED", stacklevel=1
        )
    except RegistryError as exc:
        warnings.warn(
            f"5560000002 raised {exc.code}: {exc.message} — modulus-10 caveat may be CONFIRMED",
            stacklevel=1,
        )


@pytest.mark.live
async def test_117_live_field_names_present_or_optional() -> None:
    """T26e fix 8: walk the live payload for every field name `mapping.py`
    reads and assert each is present (as a key) or explicitly optional in
    §2 — a field this spec names that the live payload does not have is a
    **blocking** finding for `REVIEW.md`/T26d, not something to work around.
    Also records, via `warnings.warn` (not `print`), which spelling of
    `pagaende...` and which `organisationsnamntyp` foreign-language code the
    wire actually uses."""
    environment = client_module._read_environment()
    response = await client_module._fetch_organisationer(environment, "5560021361")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    organisationer: list[dict[str, Any]] = body.get("organisationer") or []
    assert organisationer, "5560021361 returned no organisationer"
    org: dict[str, Any] = organisationer[0]

    # Both spellings of pagaende... are one logical field (§15) — the wire
    # only ever uses one of them, so require at least one key, not both.
    pagaende_kods = (
        "pagaendeAvvecklingsEllerOmstruktureringsforfarande",
        "pagandeAvvecklingsEllerOmstruktureringsforfarande",
    )
    other_wrapped = tuple(field for field in mapping._WRAPPED_FIELDS if field not in pagaende_kods)
    required_fields = (*other_wrapped, "organisationsidentitet", "namnskyddslopnummer")

    missing = [field for field in required_fields if field not in org]
    pagaende_present = [spelling for spelling in pagaende_kods if spelling in org]
    if not pagaende_present:
        missing.append(" or ".join(pagaende_kods))

    assert not missing, (
        "SWEDEN_SPEC.md names these as fields mapping.py reads, but the live 5560021361 "
        f"payload does not have them at all — a blocking finding for REVIEW.md/T26d, not "
        f"something to work around: {missing}"
    )

    namn_wrapper = org.get("organisationsnamn") or {}
    name_list: list[dict[str, Any]] = namn_wrapper.get("organisationsnamnLista") or []
    foreign_language_kods = sorted(
        {
            str((entry.get("organisationsnamntyp") or {}).get("kod"))
            for entry in name_list
            if (entry.get("organisationsnamntyp") or {}).get("kod") != "FORETAGSNAMN"
        }
    )

    warnings.warn(
        f"live wire for 5560021361: pagaende... spelling(s) present as a key = "
        f"{pagaende_present!r}; organisationsnamntyp codes other than FORETAGSNAMN seen in "
        f"the name list = {foreign_language_kods!r}",
        stacklevel=1,
    )


@pytest.mark.live
async def test_118_live_id_example_is_active(monkeypatch: pytest.MonkeyPatch) -> None:
    # T26e fix 14: `monkeypatch`, not a bare `os.environ` assignment — the
    # latter leaks into the rest of the live session.
    monkeypatch.setenv("BOLAGSVERKET_ENVIRONMENT", "production")
    report = await client_module.lookup("5560160680")
    assert report.status is CompanyStatus.ACTIVE
    assert report.name


# ---------------------------------------------------------------------------
# I. `POST /dokumentlista` — R-5b / T31 Part B, behind the seam (132-142)
#
# `DECISIONS.md` D-041, `tasks/T31.md` Part B. The block's models and mapper
# live in `registries/se/filings.py` (local stand-ins for R-5's `SourceRef` /
# `FiledDocument` / `FilingHistory`, exactly as `registries/gb/charges.py`
# does for `Charge`); the fetch is `client.fetch_filings`. Nothing here reads
# or asserts on `core/models.py`, and no test below changes a deadline.
#
# `bv_dokumentlista.json` is a **live recording** of `5561890038` against the
# Bolagsverket TEST environment, 2026-09-08 (`tests/fixtures/README.md`).
# `bv_dokumentlista_empty.json` and `bv_dokumentlista_no_key.json` carry a
# `_SYNTHETIC_COMBINATION` header because that state cannot be reproduced
# live: `/dokumentlista` has its own test allowlist and `5561890038` is the
# only number on it, so every other identifier answers 400 rather than 200
# with an empty list.
# ---------------------------------------------------------------------------

DOKUMENTLISTA = _load("bv_dokumentlista.json")
DOKUMENTLISTA_EMPTY = _load("bv_dokumentlista_empty.json")
DOKUMENTLISTA_NO_KEY = _load("bv_dokumentlista_no_key.json")
DOKUMENTLISTA_400 = _load("bv_dokumentlista_400.json")

FETCHED_AT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def _mock_dokumentlista(
    body: dict[str, Any], base_url: str = PRODUCTION_BASE, status: int = 200
) -> respx.Route:
    return respx.post(f"{base_url}/dokumentlista").mock(
        return_value=httpx.Response(status, json=body)
    )


def test_132_dokumentlista_recording_maps_three_annual_reports() -> None:
    """The live recording of `5561890038`. Every assertion here is a fact
    about the wire, not about a fixture we wrote: three filed annual reports,
    newest first, all `application/zip`, all with a `_paket`-suffixed handle.

    `-34` is D-041(g)'s own worked example — "filed 2023-06-27 for the period
    ending 2022-12-31, 34 days before the late-fee point" — reproduced by the
    arithmetic rather than restated.
    """
    block = filings.map_dokumentlista(DOKUMENTLISTA, cached=False, fetched_at=FETCHED_AT)

    assert [d.period_end for d in block.documents] == [
        date(2022, 12, 31),
        date(2021, 12, 31),
        date(2020, 12, 31),
    ]
    assert [d.filed_at for d in block.documents] == [
        date(2023, 6, 27),
        date(2022, 7, 6),
        date(2021, 7, 30),
    ]
    assert [d.days_from_fee_point for d in block.documents] == [-34, -25, -1]
    assert {d.kind for d in block.documents} == {"annual_accounts"}
    assert {d.file_format for d in block.documents} == {"application/zip"}
    assert block.documents[0].document_id == "02f54e4f-b17a-4cfd-a1cc-d8ab4eaa7f49_paket"

    # D-041(d)/(e): Bolagsverket publishes no `...From`, so `period_start` is
    # `None` for Sweden — never derived by subtracting twelve months.
    assert all(d.period_start is None for d in block.documents)
    # D-042(h)'s three fields exist and Sweden fills none of them.
    assert all(
        (d.category, d.type_code, d.description_code) == (None, None, None)
        for d in block.documents
    )

    # Carried verbatim from the newest report, never synthesised.
    assert block.financial_year_end == date(2022, 12, 31)
    assert block.provenance.fetched_at == FETCHED_AT
    assert block.provenance.cached is False
    assert block.provenance.source == "Bolagsverket (bolagsverket.se)"
    # A 31 December year end is the assumption Sweden already ships, so no
    # broken-financial-year caveat fires — only the D-044(b) scope note
    # (finding 1 of the D-044 wiring review) is present, and it is first.
    assert block.notes == [filings._SCOPE_NOTE]


def test_133_empty_list_and_absent_key_are_a_present_block_never_not_found() -> None:
    """D-041(c),(h): `dokument` is not in `DokumentlistaSvar`'s `required`
    list, so an absent key and an empty array are the same answer — and that
    answer is a **present** block meaning "Bolagsverket holds no filed annual
    report for this entity", never an absence and never `not_found`."""
    for payload in (DOKUMENTLISTA_EMPTY, DOKUMENTLISTA_NO_KEY):
        block = filings.map_dokumentlista(payload, cached=False, fetched_at=FETCHED_AT)
        assert block.documents == []
        assert block.financial_year_end is None
        assert block.provenance.fetched_at == FETCHED_AT
        # The one state that must never read as "we could not look".
        assert any("holds no filed annual report" in n for n in block.notes)


def test_empty_note_names_the_ericsson_observation_t44() -> None:
    """T44's orchestrator addendum asked why production serves a **present**
    block with `documents: []` for Telefonaktiebolaget LM Ericsson
    (5560160680) against six listed reports for 5561890038.
    `tasks/T52-recon.md` answered it: Ericsson reports under IFRS, which
    Bolagsverket's digital-submission channel does not accept at all — T55
    §E rewrites `_EMPTY_NOTE` to state that as the reason rather than as a
    hedged observation, which this pins."""
    empty = filings.map_dokumentlista(DOKUMENTLISTA_EMPTY, cached=False, fetched_at=FETCHED_AT)
    (empty_note,) = [n for n in empty.notes if "holds no filed annual report" in n]
    assert "5560160680" in empty_note
    assert "5561890038" in empty_note
    assert "IFRS" in empty_note
    assert "digital channel" in empty_note


def test_134_no_dataproducent_fel_wrapper_and_unknown_keys_are_ignored() -> None:
    """D-041(h), confirmed live 2026-09-08: `DokumentlistaSvar` is a plain
    `{"dokument": [...]}` with no `dataproducent`/`fel` wrapper, so
    `SWEDEN_SPEC.md` §1.6's "HTTP 200 ≠ data arrived" rule is scoped to
    `/organisationer` and this module's `fel`-inspecting helpers are never
    pointed here. The recording is asserted on directly so a future
    re-recording that grows a wrapper fails this test rather than silently
    changing the contract."""
    assert set(DOKUMENTLISTA) == {"dokument"}
    assert "dataproducent" not in json.dumps(DOKUMENTLISTA)
    assert "fel" not in DOKUMENTLISTA

    # A top-level key the mapper does not read costs nothing — which is what
    # lets the two synthetic fixtures carry their `_SYNTHETIC_COMBINATION`
    # header (`tests/fixtures/README.md`).
    assert "_SYNTHETIC_COMBINATION" in DOKUMENTLISTA_EMPTY
    block = filings.map_dokumentlista(DOKUMENTLISTA_EMPTY, cached=False, fetched_at=FETCHED_AT)
    assert block.documents == []


def test_135_days_from_fee_point_is_a_signed_measurement_never_a_verdict() -> None:
    """D-041(d): a signed integer measured against seven months after
    `period_end` (ÅRL 8 kap. 6 §), `None` when either input is missing, and
    **no `filed_late` boolean anywhere** — D-011/D-028(3): a field whose job
    is to distinguish two states must not have a third that means both."""
    payload = {
        "dokument": [
            # One day after the fee point (31 July 2023) — positive.
            {"rapporteringsperiodTom": "2022-12-31", "registreringstidpunkt": "2023-08-01"},
            # Exactly on it — zero, not None and not False.
            {"rapporteringsperiodTom": "2021-12-31", "registreringstidpunkt": "2022-07-31"},
            # No filing date — honestly None (D-009).
            {"rapporteringsperiodTom": "2020-12-31"},
            # No reporting period — honestly None.
            {"registreringstidpunkt": "2020-05-05"},
        ]
    }
    block = filings.map_dokumentlista(payload, cached=False, fetched_at=FETCHED_AT)
    by_period = {d.period_end: d for d in block.documents}
    assert by_period[date(2022, 12, 31)].days_from_fee_point == 1
    assert by_period[date(2021, 12, 31)].days_from_fee_point == 0
    assert by_period[date(2020, 12, 31)].days_from_fee_point is None
    assert by_period[None].days_from_fee_point is None

    assert "filed_late" not in filings.FiledDocument.model_fields
    assert filings.FEE_POINT_MONTHS == 7
    assert filings.fee_point(date(2022, 12, 31)) == date(2023, 7, 31)


def test_136_sorted_newest_first_and_financial_year_end_skips_undated() -> None:
    """D-041(g): `period_end` descending, then `filed_at` descending. A
    document with no reporting period sorts last and can never become
    `financial_year_end` — the field is carried verbatim from a real
    period end or it is `None`."""
    payload = {
        "dokument": [
            {"rapporteringsperiodTom": "2021-12-31", "registreringstidpunkt": "2022-07-06"},
            {"registreringstidpunkt": "2026-01-01"},
            # Two filings for the same period: the later registration wins.
            {"rapporteringsperiodTom": "2022-12-31", "registreringstidpunkt": "2023-06-27"},
            {"rapporteringsperiodTom": "2022-12-31", "registreringstidpunkt": "2023-11-02"},
        ]
    }
    block = filings.map_dokumentlista(payload, cached=False, fetched_at=FETCHED_AT)
    assert [(d.period_end, d.filed_at) for d in block.documents] == [
        (date(2022, 12, 31), date(2023, 11, 2)),
        (date(2022, 12, 31), date(2023, 6, 27)),
        (date(2021, 12, 31), date(2022, 7, 6)),
        (None, date(2026, 1, 1)),
    ]
    assert block.financial_year_end == date(2022, 12, 31)


def test_137_broken_financial_year_is_disclosed_and_datetime_dates_still_parse() -> None:
    """A *brutet räkenskapsår* is lawful (bokföringslagen 3 kap.) and is the
    whole reason D-041 exists: a company with an April year end is told
    30 June and 31 July today when its own dates are four months later. The
    block says so; it does not change any date (that is D-041(e)'s ladder,
    a follow-on task).

    Both dates are declared `format: date` and were plain dates in every
    observed payload, but `registreringstidpunkt` is named for a point in
    time, so the parser tolerates `YYYY-MM-DDT…` the way
    `registries/se/mapping.py` already does (§2.5).
    """
    payload = {
        "dokument": [
            {
                "rapporteringsperiodTom": "2025-04-30",
                "registreringstidpunkt": "2025-10-15T09:30:00Z",
            }
        ]
    }
    block = filings.map_dokumentlista(payload, cached=False, fetched_at=FETCHED_AT)
    assert block.financial_year_end == date(2025, 4, 30)
    assert block.documents[0].filed_at == date(2025, 10, 15)
    # 30 April + 7 months = 30 November 2025; filed 15 October is 46 days before.
    assert block.documents[0].days_from_fee_point == -46
    assert any("brutet räkenskapsår" in n for n in block.notes)
    # A garbage date is `None`, never an exception.
    junk = filings.map_dokumentlista(
        {"dokument": [{"rapporteringsperiodTom": "not-a-date", "registreringstidpunkt": 17}]},
        cached=False,
        fetched_at=FETCHED_AT,
    )
    assert junk.documents[0].period_end is None
    assert junk.documents[0].filed_at is None


def test_scope_note_is_present_first_on_every_block_d044b() -> None:
    """D-044(b): one include name, `filings`, covers three differently-scoped
    answers *because* "the scope difference is disclosed in the block's own
    `notes`, on every call". D-044 wiring review, finding 1 (blocking): this
    Swedish block returned `notes: []` on a non-empty result, breaking that
    promise for the register whose scope is narrowest. `_SCOPE_NOTE` is now
    unconditional and first — on both a non-empty and an empty block."""
    non_empty = filings.map_dokumentlista(DOKUMENTLISTA, cached=False, fetched_at=FETCHED_AT)
    assert non_empty.notes[0] == filings._SCOPE_NOTE
    assert "annual reports only" in non_empty.notes[0]

    empty = filings.map_dokumentlista(DOKUMENTLISTA_EMPTY, cached=False, fetched_at=FETCHED_AT)
    assert empty.notes[0] == filings._SCOPE_NOTE
    assert any("holds no filed annual report" in n for n in empty.notes)


@respx.mock
async def test_138_default_lookup_makes_no_document_list_request() -> None:
    """D-041(b): the second call is never made by default — it costs a token
    from the tightest published budget in the project (60/min, §1.5). Asserted,
    not assumed (`tasks/T31.md` done-check)."""
    _mock_token()
    _mock_data(AB_ACTIVE)
    dokumentlista = _mock_dokumentlista(DOKUMENTLISTA)

    await client_module.lookup("5560021361")

    assert dokumentlista.call_count == 0


@respx.mock
async def test_139_fetch_filings_posts_the_id_in_the_body_and_spends_a_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The identifier goes in the JSON body and never in a URL (D-039,
    D-040), a fresh `X-Request-Id` travels with it, and the call spends a
    token-bucket token like any other request against the published 60/min —
    the OpenAPI's `x-throttling-tier: "Unlimited"` is a WSO2 gateway artefact
    (confirmed live: no `X-RateLimit-*` header comes back either)."""
    _mock_token()
    route = _mock_dokumentlista(DOKUMENTLISTA)

    # Counted rather than read off `_bucket._tokens`: that float is a module
    # singleton shared with every other test in this session and is only
    # recomputed inside `acquire()`, so comparing it before and after is a
    # flake, not a measurement.
    acquired = 0
    real_acquire = client_module._bucket.acquire

    async def _counting_acquire() -> None:
        nonlocal acquired
        acquired += 1
        await real_acquire()

    monkeypatch.setattr(client_module._bucket, "acquire", _counting_acquire)
    block = await client_module.fetch_filings("5561890038")

    assert route.called
    request = route.calls[0].request
    assert request.url.path.endswith("/dokumentlista")
    assert "5561890038" not in str(request.url)
    assert json.loads(request.content) == {"identitetsbeteckning": "5561890038"}
    assert uuid.UUID(request.headers["X-Request-Id"])
    # One token for the OAuth token request, one for this call — the second
    # call is a real request against the published 60/min, not a free one.
    assert acquired == 2
    assert block.financial_year_end == date(2022, 12, 31)


@respx.mock
async def test_140_status_mapping_never_produces_not_found() -> None:
    """D-041(h): `/organisationer` decides whether an entity exists;
    `/dokumentlista` never does. A 400 is `invalid_id` (the identifier is the
    only input, and D-032 refuses to enforce a check digit we cannot source,
    so upstream's verdict decides); a 5xx and even an undeclared 404 are
    `upstream_error`. **No status maps to `not_found`.**

    The 400 body is the live recording: its `detail` is *not* the OpenAPI's
    documented "ogiltig kontrollsiffra" example but a second, undocumented
    string. Two strings, one status — which is exactly why D-041(h) forbids
    coding to `detail`.
    """
    for status, expected in (
        (400, ErrorCode.INVALID_ID),
        (404, ErrorCode.UPSTREAM_ERROR),
        (500, ErrorCode.UPSTREAM_ERROR),
    ):
        respx.clear()
        _mock_token()
        _mock_dokumentlista(DOKUMENTLISTA_400 if status == 400 else BODY_500, status=status)
        with pytest.raises(RegistryError) as excinfo:
            await client_module.fetch_filings("5561890038")
        assert excinfo.value.code is expected, status
        assert excinfo.value.code is not ErrorCode.NOT_FOUND

    assert DOKUMENTLISTA_400["detail"] != BODY_400["detail"]


@respx.mock
async def test_141_block_caches_under_its_own_key_with_the_1h_empty_split() -> None:
    """D-041(c),(h): the block has its **own** cache key and its own TTL —
    24 h for a non-empty list, 1 h for an empty one (D-006's asymmetry, for
    D-006's reason: an empty list goes stale the instant the company files).
    The key is separate from the entity key, which is what lets a cached
    company record travel beside a freshly fetched document list."""
    from registry_mcp.core import cache

    _mock_token()
    route = _mock_dokumentlista(DOKUMENTLISTA)

    first = await client_module.fetch_filings("5561890038")
    second = await client_module.fetch_filings("5561890038")

    assert route.call_count == 1
    assert first.provenance.cached is False
    assert second.provenance.cached is True
    # Its own moment, preserved across the hit (D-006).
    assert second.provenance.fetched_at == first.provenance.fetched_at

    key = client_module._filings_cache_key("production", "5561890038")
    assert key == "SE:bolagsverket:filings:prod:5561890038"
    assert key != client_module._cache_key("production", "5561890038")
    entry = cache.get(key)
    assert entry is not None
    assert entry.status == "ok"

    # An empty list takes the 1 h TTL, reusing `core/cache.py`'s existing
    # `not_found` label purely for its shorter TTL — never raised as an error.
    respx.clear()
    _mock_token()
    _mock_dokumentlista(DOKUMENTLISTA_EMPTY)
    empty = await client_module.fetch_filings("5560021361")
    assert empty.documents == []
    empty_entry = cache.get(client_module._filings_cache_key("production", "5560021361"))
    assert empty_entry is not None
    assert empty_entry.status == "not_found"


@respx.mock
async def test_142_test_environment_hosts_and_the_n10_note_on_the_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The block's provenance is its own (D-041(c)), so N10 — "this came from
    the test environment, the organisation may not exist" — has to be applied
    to it separately from the report's. `5561890038` is the only number the
    TEST environment answers `/dokumentlista` for, and it 400s on
    `/organisationer`, so this pairing cannot be recorded live at all."""
    # T26e fix 14: `monkeypatch`, never a bare `os.environ` assignment.
    monkeypatch.setenv("BOLAGSVERKET_ENVIRONMENT", "test")
    _mock_token(TEST_TOKEN)
    route = _mock_dokumentlista(DOKUMENTLISTA, base_url=TEST_BASE)
    block = await client_module.fetch_filings("5561890038")

    assert route.called
    assert block.provenance.source is not None
    assert block.provenance.source.endswith("— test environment")
    assert any("test environment" in n for n in block.notes)
    assert client_module._filings_cache_key("test", "5561890038").startswith(
        "SE:bolagsverket:filings:test:"
    )


@respx.mock
async def test_143_401_refreshes_the_token_once_then_raises() -> None:
    """§6.1's one-time refresh-and-retry, layered on this call too — a block
    fetch must not be the one code path that leaves a stale token in place."""
    token = _mock_token()
    _mock_dokumentlista(BODY_401, status=401)

    with pytest.raises(RegistryError) as excinfo:
        await client_module.fetch_filings("5561890038")

    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR
    assert token.call_count == 2


@pytest.mark.live
async def test_144_live_dokumentlista_5561890038(monkeypatch: pytest.MonkeyPatch) -> None:
    """The recording's own done-check. `5561890038` is confirmed as the
    `/dokumentlista` scenario company (`SWEDEN_SPEC.md` §17's table had two
    other numbers backwards until 2026-09-07, so this one was re-verified
    rather than trusted).

    Note what this test cannot do: `5561890038` answers `/organisationer`
    with a **400**, so the TEST environment cannot produce a lookup and a
    filing history for the same entity, and no live test can assert the two
    blocks' independent provenance against each other.
    """
    monkeypatch.setenv("BOLAGSVERKET_ENVIRONMENT", "test")
    block = await client_module.fetch_filings("5561890038")
    assert block.financial_year_end == date(2022, 12, 31)
    assert len(block.documents) >= 3
    assert block.documents[0].days_from_fee_point == -34
    assert {d.file_format for d in block.documents} == {"application/zip"}


@pytest.mark.live
async def test_145_live_dokumentlista_allowlist_is_disjoint_from_organisationer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recorded as a test so the finding is re-checked rather than remembered:
    in the TEST environment the two operations have **disjoint** allowlists.
    `5560021361` — the company eight `/organisationer` fixtures are built on —
    answers `/dokumentlista` with a 400, and every other test-workbook number
    tried on 2026-09-08 did the same. That is why the empty-list state cannot
    be recorded live and its fixtures are `_SYNTHETIC_COMBINATION`.

    If this test ever fails, the test environment has gained a second
    `/dokumentlista` company — record it, and replace
    `bv_dokumentlista_empty.json` if it has no filings.
    """
    monkeypatch.setenv("BOLAGSVERKET_ENVIRONMENT", "test")
    with pytest.raises(RegistryError) as excinfo:
        await client_module.fetch_filings("5560021361")
    assert excinfo.value.code is ErrorCode.INVALID_ID


# ---------------------------------------------------------------------------
# J. `financials` (D-043, D-047(f),(g), `tasks/T55.md` Part F). All fixtures
# under `tests/fixtures/se_ixbrl_*.xhtml` are hand-built from measured
# figures rather than a stripped copy of the real filing -- see the header
# comment on each file and `tasks/T55-recon.md`: stripping only the *tagged*
# `ix:nonNumeric` content was not enough on the real document, which repeats
# a signing director's name as bare, untagged HTML text elsewhere. The
# figures themselves (5561890038's 2020 and 2025 periods) are the real,
# measured ones -- published anyway in `tasks/T52-recon.md` and this brief's
# own done-check -- and every value was cross-checked against the real
# document through this exact code before being hand-copied into the
# fixture (see the final report).
#
# `se_dokumentlista_5561890038.json` is the real, live, production
# `/dokumentlista` body for `5561890038` (six annual reports, no personal
# data in this shape at all). `se_dokumentlista_empty.json` is not
# re-fetched live (D-047(f)'s continuation authorized exactly one
# supplementary `/dokumentlista` call, already spent) -- its header names
# the real, previously observed production fact it stands in for.
# ---------------------------------------------------------------------------

SE_FIXTURES = Path(__file__).parent / "fixtures"
SE_SRC = Path(client_module.__file__).parent  # src/registry_mcp/registries/se/

DOKUMENTLISTA_5561890038 = _load("se_dokumentlista_5561890038.json")
DOKUMENTLISTA_SE_EMPTY = _load("se_dokumentlista_empty.json")

DOKUMENT_ID_2020 = "7c9e96b6-bcef-488c-9d68-eae350547fbf_paket"
DOKUMENT_ID_2025 = "64caa943-a04b-4dda-8be6-26b8ba728adf_paket"


def _xhtml_bytes(name: str) -> bytes:
    return (SE_FIXTURES / name).read_bytes()


def _zip_of(*entries: tuple[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries:
            zf.writestr(name, content)
    return buf.getvalue()


def _mock_dokument(dokument_id: str, xhtml: bytes, base_url: str = PRODUCTION_BASE) -> respx.Route:
    return respx.get(f"{base_url}/dokument/{dokument_id}").mock(
        return_value=httpx.Response(200, content=_zip_of(("document.xhtml", xhtml)))
    )


# --- F1/F2 — the done-check, offline, straight through ixbrl.py + financials.py ---


def test_d047_f1_done_check_2025_offline_exact() -> None:
    """The brief's done-check, verbatim, against the committed fixture
    (`tasks/T55.md`, `tasks/T52-recon.md`): total_assets ==
    total_equity_and_liabilities == 515409.0, equity == 508409.0,
    profit_for_period == -10536.0, currency == 'SEK'."""
    doc = ixbrl.parse(_xhtml_bytes("se_ixbrl_5561890038_2025.xhtml"))
    summary = financials_module.map_financials(
        doc,
        document_id=DOKUMENT_ID_2025,
        total_annual_reports=6,
        source_url=f"{PRODUCTION_BASE}/dokument/{DOKUMENT_ID_2025}",
        cached=False,
        fetched_at=FETCHED_AT,
    )
    assert len(summary.periods) == 1
    period = summary.periods[0]
    bs = period.balance_sheet
    assert bs is not None and period.income_statement is not None
    assert bs.total_assets == bs.total_equity_and_liabilities == 515409.0
    assert bs.equity == 508409.0
    assert period.income_statement.profit_for_period == -10536.0
    assert period.currency == "SEK"
    assert period.accounting_framework == "K2"
    assert period.document_id == DOKUMENT_ID_2025
    assert period.period_start == date(2025, 1, 1)
    assert period.period_end == date(2025, 12, 31)
    # 18/18 identities reconcile on every real K2 document sampled
    # (tasks/T52-recon.md) — this fixture's figures do too, so the one
    # permitted comparison (D-043(e)) must not fire here.
    assert not any("differ by" in n for n in summary.notes)


def test_d047_f2_2020_currency_via_unit_and_redovisningsvaluta_never_read() -> None:
    """The 2020 fixture (2017-09-30 taxonomy, `Redovisningsvaluta` present as
    the plain string `"SEK"`) also yields `currency == "SEK"` — through the
    unit, exactly as the 2025 fixture (enum-member currency) does. A static
    check proves the extractor never reads `se-cd-base:Redovisningsvaluta`
    under either name as a lookup key: with each module's own top docstring
    removed (where the concept is named *as the thing to avoid*), the string
    does not appear anywhere else in `registries/se/`."""
    doc = ixbrl.parse(_xhtml_bytes("se_ixbrl_5561890038_2020.xhtml"))
    summary = financials_module.map_financials(
        doc,
        document_id=DOKUMENT_ID_2020,
        total_annual_reports=6,
        source_url=f"{PRODUCTION_BASE}/dokument/{DOKUMENT_ID_2020}",
        cached=False,
        fetched_at=FETCHED_AT,
    )
    period = summary.periods[0]
    assert period.currency == "SEK"
    assert period.accounting_framework == "K2"
    assert "Redovisningsvaluta" in _xhtml_bytes("se_ixbrl_5561890038_2020.xhtml").decode()

    found_in_code = False
    for py_file in sorted(SE_SRC.glob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        if "Redovisningsvaluta" not in source:
            continue
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree, clean=False) or ""
        remainder = source.replace(docstring, "") if docstring else source
        if "Redovisningsvaluta" in remainder:
            found_in_code = True
    assert not found_in_code, "Redovisningsvaluta must appear only in a module's own top docstring"


# --- F3 — the extractor never touches ix:nonNumeric ---


def test_d047_f3_extractor_element_filter_is_static_and_nonnumeric_never_leaks() -> None:
    """Static half: `ixbrl.parse`'s fact loop matches `nonFraction` only —
    there is no code path anywhere in `ixbrl.py` that compares an element's
    local name against `"nonNumeric"`, so the rule is not a per-concept
    blocklist that could go stale, it is a filter that structurally never
    engages with that element type (module docstring).

    Runtime half: `se_ixbrl_nonnumeric_leak_check.xhtml` *does* contain an
    `ix:nonNumeric` "signature block" — three facts, each carrying the
    obviously-fake token below — verifying the filter holds even when the
    element it must ignore is genuinely present with content, not merely
    absent from the fixture."""
    source = (SE_SRC / "ixbrl.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    compared_literals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for side in (node.left, *node.comparators):
                if isinstance(side, ast.Constant) and isinstance(side.value, str):
                    compared_literals.add(side.value)
    assert "nonFraction" in compared_literals
    assert "nonNumeric" not in compared_literals

    token = "ZZZ-NOT-A-REAL-NAME-LEAK-CHECK-ZZZ"
    xhtml = _xhtml_bytes("se_ixbrl_nonnumeric_leak_check.xhtml")
    assert token in xhtml.decode()  # the fixture really does carry it

    doc = ixbrl.parse(xhtml)
    summary = financials_module.map_financials(
        doc,
        document_id="leak-check",
        total_annual_reports=1,
        source_url="https://example.invalid/leak-check",
        cached=False,
        fetched_at=FETCHED_AT,
    )
    dumped = json.dumps(summary.model_dump(mode="json"))
    assert token not in dumped
    assert "UnderskriftHandling" not in dumped
    # And the fixture's ordinary figures were still read correctly —
    # proving the token's *absence* from the output is because it was never
    # a candidate, not because parsing failed outright.
    leak_check_sheet = summary.periods[0].balance_sheet
    assert leak_check_sheet is not None
    assert leak_check_sheet.total_assets == 100000.0


# --- F4 — Soliditet never read ---


def test_d047_f4_soliditet_never_read_as_a_lookup_key() -> None:
    found_in_code = False
    for py_file in sorted(SE_SRC.glob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        if "Soliditet" not in source:
            continue
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree, clean=False) or ""
        remainder = source.replace(docstring, "") if docstring else source
        # Strip `#:`/`#` line comments too — financials.py names it once in
        # one of those, not only in the module docstring.
        remainder = "\n".join(
            line for line in remainder.splitlines() if not line.strip().startswith("#")
        )
        if "Soliditet" in remainder:
            found_in_code = True
    assert not found_in_code, "Soliditet must appear only in a comment or docstring"
    assert "Soliditet" not in financials_module._INCOME_STATEMENT_CONCEPTS.values()
    assert "Soliditet" not in financials_module._BALANCE_SHEET_CONCEPTS.values()


# --- F5 — an absent line stays None ---


def test_d047_f5_absent_line_stays_none_never_zero() -> None:
    doc = ixbrl.parse(_xhtml_bytes("se_ixbrl_5561890038_2025.xhtml"))
    period = financials_module.build_period(doc, document_id=DOKUMENT_ID_2025)
    assert period is not None
    sheet = period.balance_sheet
    assert sheet is not None
    # No K2 filing for this company ever tags fixed assets (tasks/T52-recon.md).
    assert sheet.fixed_assets is None
    assert sheet.non_current_liabilities is None
    # 2025 files no long-term liabilities; 2020 does — same company, same
    # concept, different years, proving absence is read per period.
    doc_2020 = ixbrl.parse(_xhtml_bytes("se_ixbrl_5561890038_2020.xhtml"))
    period_2020 = financials_module.build_period(doc_2020, document_id=DOKUMENT_ID_2020)
    assert period_2020 is not None
    sheet_2020 = period_2020.balance_sheet
    assert sheet_2020 is not None
    assert sheet_2020.non_current_liabilities == 935948.0


# --- F6 — the latest context is selected when two years are tagged ---


def test_d047_f6_latest_period_selected_over_the_comparison_year() -> None:
    """Both fixtures tag a comparison year (period1/balans1) with different
    figures from the current year (period0/balans0) — `ixbrl.py` must pick
    the latter. `Rorelseresultat` differs between the two years in both
    fixtures, which is what makes this a real test rather than a
    coincidence."""
    doc = ixbrl.parse(_xhtml_bytes("se_ixbrl_5561890038_2025.xhtml"))
    assert doc.latest_period_end == date(2025, 12, 31)
    rorelseresultat = doc.latest("Rorelseresultat")
    tillgangar = doc.latest("Tillgangar")
    assert rorelseresultat is not None and tillgangar is not None
    assert rorelseresultat.value == -4656.0  # not 2024's -12515.0
    assert tillgangar.value == 515409.0  # not 2024's 555857.0


# --- F7 — @sign and @scale both applied ---


def test_d047_f7_sign_applied_on_real_figures_and_scale_on_a_handbuilt_fixture() -> None:
    """`@sign="-"` is genuinely exercised by the real 2020/2025 figures
    (a loss, a negative net-financial-items line). No real or specimen
    document measured carries a non-zero `@scale` on a wanted concept
    (`ixbrl.py`'s docstring), so `se_ixbrl_scale_handbuilt.xhtml` is
    hand-built to exercise it, and says so in its own header comment."""
    doc_2025 = ixbrl.parse(_xhtml_bytes("se_ixbrl_5561890038_2025.xhtml"))
    rorelseresultat = doc_2025.latest("Rorelseresultat")
    finansiella_poster = doc_2025.latest("FinansiellaPoster")
    assert rorelseresultat is not None and finansiella_poster is not None
    assert rorelseresultat.value == -4656.0
    assert finansiella_poster.value == -5880.0

    scale_doc = ixbrl.parse(_xhtml_bytes("se_ixbrl_scale_handbuilt.xhtml"))
    fact = scale_doc.latest("Tillgangar")
    assert fact is not None
    assert fact.value == 500_000.0  # tagged "500" at scale="3" -> 500 * 10**3


# --- F8 — one /dokumentlista request for filings + financials together ---


@respx.mock
async def test_d047_f8_one_dokumentlista_request_serves_filings_and_financials() -> None:
    """D-043(h)(1)/(3), D-047(f): `fetch_filings` and `fetch_financials`
    share one `_fetch_dokumentlista_payload` — called concurrently on a cold
    cache, they must make exactly one upstream `/dokumentlista` request, not
    two. This is the same race D-043(h)(3) named for Norway, reproduced for
    Sweden's second-fetch shape."""
    import asyncio

    _mock_token()
    list_route = _mock_dokumentlista(DOKUMENTLISTA_5561890038)
    _mock_dokument(DOKUMENT_ID_2025, _xhtml_bytes("se_ixbrl_5561890038_2025.xhtml"))

    filings_block, financials_block = await asyncio.gather(
        client_module.fetch_filings("5561890038"),
        client_module.fetch_financials("5561890038"),
    )
    assert list_route.call_count == 1
    assert len(filings_block.documents) == 6
    f8_sheet = financials_block.periods[0].balance_sheet
    assert f8_sheet is not None
    assert f8_sheet.total_assets == 515409.0


# --- F9 — exactly one /dokument request for a company with six reports ---


@respx.mock
async def test_d047_f9_exactly_one_dokument_request_for_six_listed_reports() -> None:
    _mock_token()
    _mock_dokumentlista(DOKUMENTLISTA_5561890038)
    dokument_route = _mock_dokument(
        DOKUMENT_ID_2025, _xhtml_bytes("se_ixbrl_5561890038_2025.xhtml")
    )
    # The 2020 document is listed but must never be fetched — no route is
    # mocked for it, so respx raises if the client tries.

    block = await client_module.fetch_financials("5561890038")

    assert dokument_route.call_count == 1
    assert any("6 annual report" in n for n in block.notes)
    assert any("2025-12-31" in n for n in block.notes)
    assert any('include=["filings"]' in n for n in block.notes)


# --- F10 — empty /dokumentlista -> absent block, not empty, lookup succeeds ---


@respx.mock
async def test_d047_f10_empty_dokumentlista_is_absent_not_empty_and_lookup_succeeds() -> None:
    _mock_token()
    _mock_dokumentlista(DOKUMENTLISTA_SE_EMPTY)

    with pytest.raises(RegistryError) as excinfo:
        await client_module.fetch_financials("5560160680")
    assert excinfo.value.code is ErrorCode.NOT_FOUND

    registry = get_registry("SE")
    respx.post(f"{PRODUCTION_BASE}/organisationer").mock(
        return_value=httpx.Response(200, json=AB_ACTIVE)
    )
    report = await registry.lookup_with("5560160680", ["financials"])
    assert report.financials is None
    assert any("'financials' attachment" in n for n in report.notes)


# --- F11 — GB stays bad_request; list_countries shows financials for NO/SE only ---


async def test_d047_f11_financials_on_gb_bad_request_and_list_countries_shows_se() -> None:
    gb = get_registry("GB")
    with pytest.raises(RegistryError) as excinfo:
        await gb.lookup_with(gb.id_example, ["financials"])
    assert excinfo.value.code is ErrorCode.BAD_REQUEST
    assert "financials" not in excinfo.value.details["allowed"]

    se = get_registry("SE")
    assert "financials" in se.country_info().supported_includes
    no = get_registry("NO")
    assert "financials" in no.country_info().supported_includes
    assert "financials" not in gb.country_info().supported_includes


# --- F12 — cache TTL and no personal-data leak into the cache payload ---


def test_d047_f12_cache_kind_gets_thirty_days_one_hour_unmoved_by_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from registry_mcp.core import cache as cache_module

    ok_ttl, empty_ttl = cache_module._TTL_BY_KIND["financials"]
    assert ok_ttl == 30 * 24 * 60 * 60
    assert empty_ttl == 60 * 60

    monkeypatch.setenv("REGISTRY_MCP_CACHE_TTL_SECONDS", "5")
    key = "SE:bolagsverket:financials:prod:some-dokument-id"
    assert cache_module._ttl_seconds("ok", key) == ok_ttl
    assert cache_module._ttl_seconds("not_found", key) == empty_ttl


@respx.mock
async def test_d047_f12_cached_payload_carries_no_document_and_no_nonnumeric() -> None:
    from registry_mcp.core import cache as cache_module

    _mock_token()
    _mock_dokumentlista(DOKUMENTLISTA_5561890038)
    _mock_dokument(DOKUMENT_ID_2025, _xhtml_bytes("se_ixbrl_5561890038_2025.xhtml"))

    await client_module.fetch_financials("5561890038")

    fin_key = client_module._financials_cache_key("production", DOKUMENT_ID_2025)
    entry = cache_module.get(fin_key)
    assert entry is not None
    payload_text = json.dumps(entry.payload)
    assert "nonNumeric" not in payload_text
    assert "<html" not in payload_text  # the document's own root element
    assert "UnderskriftHandling" not in payload_text
    # Only the parsed period, not the raw figures dict either -- confirm the
    # payload really is FinancialPeriod-shaped and nothing wider.
    assert set(entry.payload) == {"period", "source_url"}
    assert FinancialPeriod.model_validate(entry.payload["period"]).currency == "SEK"


# --- F13 — DEADLINE_INCLUDES does not gain financials ---


def test_d047_f13_deadline_includes_excludes_financials() -> None:
    assert "financials" not in DEADLINE_INCLUDES
    se = get_registry("SE")
    assert se.supported_includes & DEADLINE_INCLUDES == {"filings"}


# --- F14 — the Swedish FinancialPeriod is field-identical to Norway's ---


def test_d047_f14_financial_period_is_field_identical_to_norways() -> None:
    """A static comparison of the model's own field set, as both country
    modules actually use it — both import `core.models.FinancialPeriod`
    directly (D-042(g), D-044(a)); this pins that nobody has quietly
    subclassed or shadowed it for one country, which is the only way a
    future Swedish-only field could ever pass this test unnoticed."""
    from registry_mcp.registries.no import accounts as no_accounts

    assert financials_module.build_period is not None  # module actually loaded
    se_field_source = FinancialPeriod  # what registries/se/financials.py builds
    no_field_source = no_accounts.FinancialPeriod  # what registries/no/accounts.py builds
    assert se_field_source is no_field_source
    assert se_field_source.model_fields.keys() == no_field_source.model_fields.keys()


# --- F15 — REST ≡ MCP parity: intentionally not duplicated here ---
#
# tests/test_mcp.py::test_d043_invariant8_rest_and_mcp_lookup_company_include_financials_are_identical
# already proves the *generic* include=["financials"]/?include=financials
# mechanism is REST≡MCP-identical (api/main.py and mcp/server.py both call
# the same country-blind Registry.lookup_with — neither surface branches on
# country), and
# tests/test_mcp.py::test_rest_and_mcp_lookup_company_are_identical_se
# already proves Sweden's own base lookup is byte-identical across both
# surfaces. Together they cover the same guarantee a bespoke
# SE-plus-financials parity test would, without re-testing plumbing that
# does not know Sweden exists. Not duplicated here per the brief's own F15.


# --- K3: accounting_framework, scope/consolidated, and the validation caveat ---


def test_d047_k3_framework_detected_scope_left_none_with_caveat_note() -> None:
    """K3 detection is from the schemaRef path (A/B), never a concept.
    `scope`/`consolidated` stay `None` for K3 — nobody has read a live K3
    filing (`tasks/T55-recon.md`) — and the block's own `notes` says the
    parser was validated on K2 filings and K3 taxonomy specimens only,
    per the orchestrator's continuation rule 1."""
    doc = ixbrl.parse(_xhtml_bytes("se_ixbrl_k3_specimen.xhtml"))
    assert ixbrl.schema_ref_says(doc.schema_refs, "k3")
    assert not ixbrl.schema_ref_says(doc.schema_refs, "k2")

    period = financials_module.build_period(doc, document_id="k3-specimen")
    assert period is not None
    assert period.accounting_framework == "K3"
    assert period.scope is None
    assert period.consolidated is None

    notes = financials_module.summary_notes(period, total_annual_reports=1)
    (caveat,) = [n for n in notes if "validated against filed K2" in n]
    assert "K3 taxonomy specimens" in caveat
    assert "no live K3" in caveat


def test_d047_k2_scope_is_entity_accounts_consolidated_false() -> None:
    """The K2 channel excludes koncernredovisning structurally
    (`tasks/T52-recon.md` Fact 2), so this is a channel fact, not an
    inference about the company — `financials.py`'s docstring and A/B."""
    doc = ixbrl.parse(_xhtml_bytes("se_ixbrl_5561890038_2025.xhtml"))
    period = financials_module.build_period(doc, document_id=DOKUMENT_ID_2025)
    assert period is not None
    assert period.accounting_framework == "K2"
    assert period.scope == "entity accounts"
    assert period.consolidated is False


# --- Zip handling: report a multi-entry zip, never guess (A1) ---


def test_d047_multi_entry_zip_is_reported_not_guessed() -> None:
    zip_bytes = _zip_of(("a.xhtml", b"<html/>"), ("b.xhtml", b"<html/>"))
    with pytest.raises(ixbrl.MultiEntryZipError) as excinfo:
        ixbrl.unzip_single_xhtml(zip_bytes)
    assert excinfo.value.entry_count == 2


@respx.mock
async def test_d047_multi_entry_zip_from_dokument_is_upstream_error() -> None:
    _mock_token()
    _mock_dokumentlista(DOKUMENTLISTA_5561890038)
    respx.get(f"{PRODUCTION_BASE}/dokument/{DOKUMENT_ID_2025}").mock(
        return_value=httpx.Response(
            200, content=_zip_of(("a.xhtml", b"<html/>"), ("b.xhtml", b"<html/>"))
        )
    )
    with pytest.raises(RegistryError) as excinfo:
        await client_module.fetch_financials("5561890038")
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR
    assert "2 entries" in excinfo.value.message


# --- The one permitted comparison (D-043(e)): total_assets vs total_equity_and_liabilities ---


def test_d047_reconciliation_note_fires_when_the_two_totals_disagree() -> None:
    """Neither 5561890038 fixture triggers this (18/18 identities reconcile
    on every real K2 document sampled, tasks/T52-recon.md) — say so, per the
    brief. This test proves the note *would* fire, on a hand-built,
    deliberately unbalanced document, without editing, reconciling or
    dropping either figure."""
    xhtml = (
        _xhtml_bytes("se_ixbrl_scale_handbuilt.xhtml")
        .decode()
        .replace(
            '<ix:nonFraction name="se-gen-base:EgetKapitalSkulder" contextRef="balans0" '
            'unitRef="SEK" decimals="INF" scale="3" format="ixt:numspacecomma">500'
            "</ix:nonFraction>",
            '<ix:nonFraction name="se-gen-base:EgetKapitalSkulder" contextRef="balans0" '
            'unitRef="SEK" decimals="INF" scale="3" format="ixt:numspacecomma">400'
            "</ix:nonFraction>",
        )
        .encode()
    )
    doc = ixbrl.parse(xhtml)
    period = financials_module.build_period(doc, document_id="mismatch-test")
    assert period is not None
    mismatch_sheet = period.balance_sheet
    assert mismatch_sheet is not None
    assert mismatch_sheet.total_assets == 500_000.0
    assert mismatch_sheet.total_equity_and_liabilities == 400_000.0
    notes = financials_module.summary_notes(period, total_annual_reports=1)
    (gap_note,) = [n for n in notes if "differ by" in n]
    assert "500,000" in gap_note
    assert "400,000" in gap_note
    assert "100,000" in gap_note


# --- Live done-check (F1's live half) ---


@pytest.mark.live
async def test_d047_live_done_check_5561890038_2025() -> None:
    """The brief's done-check against production, unmocked. Run with
    ``pytest -m live`` and real `BOLAGSVERKET_CLIENT_ID`/
    `BOLAGSVERKET_CLIENT_SECRET` in the environment. Deselected by
    `-m "not live"`, so it never runs in CI and needs no credential there."""
    block = await client_module.fetch_financials("5561890038")
    period = block.periods[0]
    live_sheet = period.balance_sheet
    live_income = period.income_statement
    assert live_sheet is not None and live_income is not None
    assert live_sheet.total_assets == live_sheet.total_equity_and_liabilities == 515409.0
    assert live_sheet.equity == 508409.0
    assert live_income.profit_for_period == -10536.0
    assert period.currency == "SEK"
