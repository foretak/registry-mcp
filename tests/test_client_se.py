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

import copy
import json
import logging
import time
import uuid
import warnings
from collections.abc import AsyncIterator, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from registry_mcp.core.models import CompanyStatus, ErrorCode, RegistryError
from registry_mcp.core.registry import get_registry
from registry_mcp.registries.se import client as client_module
from registry_mcp.registries.se import mapping

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
    report = mapping.map_entity(AB_KONKURS, "5299999994")
    assert report.status is CompanyStatus.BANKRUPT
    assert report.bankruptcy_date == date(2024, 1, 26)


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
    assert report.name == "CITY SKOR THOMAS CARLSON"
    assert report.legal_form_code == "E"
    assert report.activity == "HANDEL MED SKOR."
    assert report.postal_address is not None
    assert report.postal_address.city == "ESLÖV"


def test_92_enskild_two_n7_and_n8() -> None:
    report = mapping.map_entity(ENSKILD_TWO, "194009272719")
    assert any(
        "CITY SKOR THOMAS CARLSON" in n
        and "SKO-STALLET, THOMAS CARLSSON" in n
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
        and "Blekinge Mäklarbyrå Birgitta Andersson Karlshamn" in n
        and "Blekinge Mäklarbyrå Birgitta Andersson, Ronneby" in n
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
    two are both named "Sol i maj"). See `test_114_live_enskild_two_...`'s
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
    assert report.name == "Snö i april"
    assert any(
        "This identifier carries 3 registered businesses" in n
        and "Snö i april" in n
        and n.count("Sol i maj") == 2
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
    (`namnskyddslopnummer` 1, 2, 3; the last two both named "Sol i maj"). The
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
