"""Tests for `registries/no/client.py` and `registries/no/mapping.py`.

Numbered tests 82-97 of `NORBIZ_SPEC.md` §13 ("G. Mapping" / "H. Live done-check")
are T03's — implemented here, named `test_NN_<slug>` to match T02's convention
in `tests/no/test_rules.py`.

`registries/no/rules.py` (T02) landed during this session and is used directly
below — no mocking needed. `mapping.py` and `client.py` reach it through a
lazy, function-local import (see their module docstrings) purely so that
importing them never depended on `rules.py`'s existence or file-write timing
while both tasks were building in parallel; now that it exists, these tests
exercise the real `validate_orgnr` / `legal_form_info` / `derive_status`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from registry_mcp.core.models import ErrorCode, RegistryError
from registry_mcp.core.registry import get_registry
from registry_mcp.registries.no import client as client_module
from registry_mcp.registries.no import mapping, rules

FIXTURES = Path(__file__).parent / "fixtures"
BASE_URL = client_module.BASE_URL


def _load_fixture(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return result


EQUINOR = _load_fixture("brreg_923609016.json")
BROENNOYSUND = _load_fixture("brreg_974760673.json")
EL_ANSARI = _load_fixture("brreg_833285602.json")


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


# ---------------------------------------------------------------------------
# G. Mapping — pure, no network
# ---------------------------------------------------------------------------


def test_82_core_fields_and_vat_number() -> None:
    report = mapping.map_entity(EQUINOR, source_url="https://example/enheter/923609016")
    assert report.name == "EQUINOR ASA"
    assert report.legal_form_code == "ASA"
    assert report.id_formatted == "923 609 016"
    assert report.vat_registered is True
    assert report.vat_number == "NO923609016MVA"


def test_83_previous_names_newest_first() -> None:
    report = mapping.map_entity(EQUINOR, source_url="https://example/enheter/923609016")
    assert report.previous_names[0] == "STATOIL ASA"


def test_84_industry_codes_ranked() -> None:
    report = mapping.map_entity(EQUINOR, source_url="https://example/enheter/923609016")
    assert [c.rank for c in report.industry_codes] == [1, 2, 3]
    assert report.industry_codes[0].code == "06.100"
    assert all(c.scheme == "NACE" for c in report.industry_codes)


def test_85_share_capital_and_last_accounts_year() -> None:
    report = mapping.map_entity(EQUINOR, source_url="https://example/enheter/923609016")
    assert report.share_capital == 5976872600.0
    assert report.share_capital_currency == "NOK"
    assert report.last_annual_accounts_year == 2025
    assert isinstance(report.last_annual_accounts_year, int)


def test_86_addresses() -> None:
    report = mapping.map_entity(EQUINOR, source_url="https://example/enheter/923609016")
    assert report.business_address is not None
    assert report.business_address.city == "STAVANGER"
    assert report.business_address.lines == ["Forusbeen 50"]
    assert report.postal_address is not None
    assert report.postal_address.lines == ["Postboks 8500"]


def test_87_second_fixture_email_parent_founded_capital() -> None:
    report = mapping.map_entity(BROENNOYSUND, source_url="https://example/enheter/974760673")
    assert report.email == "firmapost@brreg.no"
    assert report.parent_id == "912660680"
    assert report.founded_at is None
    assert report.share_capital is None


def test_88_employees_not_reported_is_none_not_zero() -> None:
    data = dict(EQUINOR)
    data["harRegistrertAntallAnsatte"] = False
    data.pop("antallAnsatte", None)
    report = mapping.map_entity(data, source_url="https://example/enheter/923609016")
    assert report.employees is None
    assert report.employees_reported is False


def test_89_search_result_no_embedded_key() -> None:
    result = mapping.map_search_result({}, query="nonexistent co")
    assert result.hits == []
    assert result.total == 0
    assert result.truncated is False


# ---------------------------------------------------------------------------
# Third live fixture: 833285602 (EL ANSARI KONSULT, ENK) — the build plan's
# canonical org.nr was a typo for this number, not for the invalid 833286602
# (see `NORBIZ_SPEC.md` §1.1). A sole proprietorship has a much sparser
# payload than the ASA/ORGL fixtures, which is exactly what this exercises.
# ---------------------------------------------------------------------------


def test_el_ansari_maps_without_crashing_on_a_sparse_enk_payload() -> None:
    """An ENK payload omits `historiskeNavn` entries, `kapital`, `stiftelsesdato`
    and (despite `harRegistrertAntallAnsatte: true`) `antallAnsatte` — every
    field the mapper reads must be handled as absent-is-`None`, not crash."""
    report = mapping.map_entity(EL_ANSARI, source_url="https://example/enheter/833285602")
    assert report.name == "EL ANSARI KONSULT"
    assert report.legal_form_code == "ENK"
    assert report.status.value == "active"
    assert report.vat_registered is True
    assert report.vat_number == "NO833285602MVA"
    assert report.previous_names == []
    assert report.share_capital is None
    assert report.founded_at is None


def test_el_ansari_has_annual_accounts_duty_is_none_not_false() -> None:
    """`rules.legal_form_info("ENK")` says `has_annual_accounts_duty=None`
    (it depends on turnover/balance-sheet facts brreg does not publish,
    `NORBIZ_SPEC.md` §7/§5.5) — `False` would be guessing a duty that D-009
    explicitly forbids guessing."""
    info = rules.legal_form_info("ENK", "Enkeltpersonforetak")
    assert info.has_annual_accounts_duty is None
    report = mapping.map_entity(EL_ANSARI, source_url="https://example/enheter/833285602")
    assert report.has_annual_accounts_duty is None
    assert report.limited_liability is False
    assert report.has_board_duty is False


def test_el_ansari_employees_reported_true_but_count_absent_maps_to_none() -> None:
    """This live payload has `harRegistrertAntallAnsatte: true` with no
    `antallAnsatte` key at all (brreg appears to omit the field rather than
    send `0`) — the mapper's `.get` falls through to `None` for the count
    while still recording that a figure was reported. Documented as a
    real-data quirk in `NORBIZ_SPEC.md` §1.1, not changed here."""
    assert "antallAnsatte" not in EL_ANSARI
    assert EL_ANSARI["harRegistrertAntallAnsatte"] is True
    report = mapping.map_entity(EL_ANSARI, source_url="https://example/enheter/833285602")
    assert report.employees is None
    assert report.employees_reported is True


def test_el_ansari_deadlines_tax_return_and_vat_return_only() -> None:
    """Per `NORBIZ_SPEC.md` §5.4/§7 and D-009: an ENK gets `tax_return` (all
    forms except sub-units) and `vat_return` (VAT-registered), but not
    `annual_accounts` (has_annual_accounts_duty is None, not True) or
    `general_meeting`/`shareholder_register_statement` (AS/ASA only). No
    `payroll_report` either, since `employees` is `None` here."""
    report = mapping.map_entity(EL_ANSARI, source_url="https://example/enheter/833285602")
    deadlines = rules.deadlines_for(report, date(2026, 3, 15))
    kinds = {d.kind for d in deadlines}
    assert kinds == {"tax_return", "vat_return"}
    assert "annual_accounts" not in kinds
    assert "general_meeting" not in kinds
    assert "shareholder_register_statement" not in kinds
    assert "payroll_report" not in kinds


# ---------------------------------------------------------------------------
# D-010 follow-up: CompanyReport.notes carries the calendar-year assumption
# and/or `deadline_exemption_note`, since `Registry.deadline_report` copies
# `notes` verbatim into `DeadlineReport.notes` for both REST and MCP.
# ---------------------------------------------------------------------------


def test_calendar_year_assumption_note_present_when_any_annual_deadline_applies() -> None:
    """Equinor (ASA, active, annual-accounts duty) gets annual deadlines, so
    the calendar-year assumption must be surfaced in `notes`."""
    report = mapping.map_entity(EQUINOR, source_url="https://example/enheter/923609016")
    assert any("calendar-year" in note for note in report.notes)
    assert any("avvikende regnskapsår" in note for note in report.notes)


def test_no_calendar_year_note_when_no_annual_deadline_applies() -> None:
    """974760673 (ORGL, active, not VAT-registered, `has_annual_accounts_duty`
    is `None`, not `AS`/`ASA`, not in the `tax_return` form list) gets no
    annual-recurrence deadline under the D-009 gating, so no assumption note
    is added — and it is a classified, active, non-sub-unit form, so
    `deadline_exemption_note` also has nothing to say. `notes` is empty."""
    report = mapping.map_entity(BROENNOYSUND, source_url="https://example/enheter/974760673")
    assert report.notes == []


def test_deadline_exemption_note_surfaced_for_unclassified_legal_form() -> None:
    """An unlisted legal-form code gets `deadline_exemption_note`'s text
    (D-009/D-010) instead of the calendar-year note, since `deadlines_for`
    returns `[]` for an unclassified form."""
    data = dict(EQUINOR)
    data["organisasjonsform"] = {"kode": "ZZZZ", "beskrivelse": "Fantasiform"}
    report = mapping.map_entity(data, source_url="https://example/enheter/923609016")
    assert not any("calendar-year" in note for note in report.notes)
    assert any("not yet classified" in note for note in report.notes)


def test_deadline_exemption_note_surfaced_for_subunit() -> None:
    data = dict(BROENNOYSUND)
    data["organisasjonsform"] = {"kode": "BEDR", "beskrivelse": "Underenhet"}
    report = mapping.map_entity(data, source_url="https://example/enheter/974760673")
    assert report.is_subunit is True
    assert any("parent_id" in note for note in report.notes)


def test_deadline_report_copies_notes_verbatim() -> None:
    """`Registry.deadline_report` (D-010) is what both REST and MCP show, so
    the note must survive that hop unchanged."""
    report = mapping.map_entity(EQUINOR, source_url="https://example/enheter/923609016")
    registry = get_registry("NO")
    deadline_report = registry.deadline_report(report, date(2026, 1, 15))
    assert deadline_report.notes == report.notes
    assert any("calendar-year" in note for note in deadline_report.notes)


def test_format_id_returns_grouped_orgnr() -> None:
    registry = get_registry("NO")
    assert registry.format_id("923609016") == "923 609 016"


def test_validate_invalid_orgnr_returns_valid_false_with_hint() -> None:
    registry = get_registry("NO")
    result = registry.validate("833286602")
    assert result.valid is False
    assert result.hint is not None and result.hint
    assert result.normalized is None
    assert result.formatted is None


def test_validate_valid_orgnr_returns_formatted() -> None:
    registry = get_registry("NO")
    result = registry.validate("923609016")
    assert result.valid is True
    assert result.normalized == "923609016"
    assert result.formatted == "923 609 016"


# ---------------------------------------------------------------------------
# H. Client — respx-mocked HTTP
# ---------------------------------------------------------------------------


@respx.mock
async def test_90_404_from_both_endpoints_raises_not_found() -> None:
    respx.get(f"{BASE_URL}/enheter/999999999").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE_URL}/underenheter/999999999").mock(return_value=httpx.Response(404))

    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("999999999")

    assert excinfo.value.code is ErrorCode.NOT_FOUND
    assert "search_company" in excinfo.value.hint


@respx.mock
async def test_91_cache_hit_same_fetched_at() -> None:
    route = respx.get(f"{BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )

    first = await client_module.lookup("923609016")
    assert first.cached is False

    # Second call must not need a second HTTP mock — respx will fail the test
    # if the route is called again while unmocked (it isn't, so it's fine
    # either way), but we also assert the route's call count directly.
    second = await client_module.lookup("923609016")
    assert second.cached is True
    assert second.fetched_at == first.fetched_at
    assert route.call_count == 1


@respx.mock
async def test_92_500_then_200_retried_exactly_once() -> None:
    route = respx.get(f"{BASE_URL}/enheter/923609016").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json=EQUINOR)]
    )
    report = await client_module.lookup("923609016")
    assert report.name == "EQUINOR ASA"
    assert route.call_count == 2


@respx.mock
async def test_93_two_500s_raises_upstream_error_called_exactly_twice() -> None:
    route = respx.get(f"{BASE_URL}/enheter/923609016").mock(
        side_effect=[httpx.Response(500), httpx.Response(500)]
    )
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("923609016")
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR
    assert route.call_count == 2


@respx.mock
async def test_94_404_is_not_retried_against_same_url() -> None:
    enheter_route = respx.get(f"{BASE_URL}/enheter/999999999").mock(
        return_value=httpx.Response(404)
    )
    respx.get(f"{BASE_URL}/underenheter/999999999").mock(return_value=httpx.Response(404))

    with pytest.raises(RegistryError):
        await client_module.lookup("999999999")

    assert enheter_route.call_count == 1


@respx.mock
async def test_95_user_agent_header_contains_contact_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRY_MCP_CONTACT_EMAIL", "test-contact@example.com")
    route = respx.get(f"{BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )
    await client_module.lookup("923609016")
    sent_request = route.calls.last.request
    user_agent = sent_request.headers["user-agent"]
    assert "registry-mcp" in user_agent
    assert "test-contact@example.com" in user_agent


@respx.mock
async def test_timeout_retried_once_then_error() -> None:
    route = respx.get(f"{BASE_URL}/enheter/923609016").mock(
        side_effect=httpx.TimeoutException("timed out")
    )
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("923609016")
    assert excinfo.value.code is ErrorCode.UPSTREAM_TIMEOUT
    assert route.call_count == 2


@respx.mock
async def test_ttl_expiry_triggers_refetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_TTL_SECONDS", "0")
    route = respx.get(f"{BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )
    first = await client_module.lookup("923609016")
    second = await client_module.lookup("923609016")
    assert first.cached is False
    assert second.cached is False
    assert route.call_count == 2


@respx.mock
async def test_underenheter_fallback_maps_as_subunit() -> None:
    subunit_payload = dict(BROENNOYSUND)
    subunit_payload["organisasjonsform"] = {"kode": "BEDR", "beskrivelse": "Underenhet"}
    respx.get(f"{BASE_URL}/enheter/974760673").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE_URL}/underenheter/974760673").mock(
        return_value=httpx.Response(200, json=subunit_payload)
    )
    report = await client_module.lookup("974760673")
    assert report.is_subunit is True


@respx.mock
async def test_search_maps_hal_envelope() -> None:
    envelope = {
        "_embedded": {"enheter": [EQUINOR]},
        "page": {"size": 1, "totalElements": 1, "totalPages": 1, "number": 0},
    }
    respx.get(f"{BASE_URL}/enheter").mock(return_value=httpx.Response(200, json=envelope))
    result = await client_module.search("equinor", limit=1)
    assert result.total == 1
    assert result.hits[0].id == "923609016"
    assert result.hint is not None


async def test_search_limit_out_of_range_raises_bad_request() -> None:
    with pytest.raises(RegistryError) as excinfo:
        await client_module.search("equinor", limit=0)
    assert excinfo.value.code is ErrorCode.BAD_REQUEST

    with pytest.raises(RegistryError) as excinfo:
        await client_module.search("equinor", limit=101)
    assert excinfo.value.code is ErrorCode.BAD_REQUEST


# ---------------------------------------------------------------------------
# H. Live done-check (network; excluded from CI)
# ---------------------------------------------------------------------------


@pytest.mark.live
async def test_96_live_lookup_cached_then_true() -> None:
    first = await client_module.lookup("923609016")
    assert first.cached is False
    second = await client_module.lookup("923609016")
    assert second.cached is True


def test_97_live_fixture_fields_present_or_optional() -> None:
    """Every brreg field the mapper reads is present in the live 923609016
    payload, or is explicitly optional per `NORBIZ_SPEC.md` §2."""
    mandatory_top_level = {
        "organisasjonsnummer",
        "navn",
        "organisasjonsform",
        "historiskeNavn",
        "registreringsdatoEnhetsregisteret",
        "registrertIMvaregisteret",
        "registrertIForetaksregisteret",
        "registrertIStiftelsesregisteret",
        "registrertIFrivillighetsregisteret",
        "registrertIPartiregisteret",
        "harRegistrertAntallAnsatte",
        "konkurs",
        "underAvvikling",
        "underTvangsavviklingEllerTvangsopplosning",
    }
    missing = mandatory_top_level - EQUINOR.keys()
    assert not missing, f"Live 923609016 payload is missing mandatory fields: {missing}"

    # Optional per §2 — absence on this fixture is fine, so only type-check when present.
    optional_top_level = {
        "konkursdato",
        "slettedato",
        "overordnetEnhet",
        "epostadresse",
        "stiftelsesdato",
        "registreringsdatoForetaksregisteret",
        "vedtektsfestetFormaal",
        "aktivitet",
        "kapital",
        "sisteInnsendteAarsregnskap",
        "antallAnsatte",
        "hjemmeside",
        "telefon",
        "erIKonsern",
    }
    # Just document which ones this particular fixture happens to carry.
    assert optional_top_level  # non-empty sanity check on the allow-list itself
