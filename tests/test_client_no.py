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

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import anyio
import httpx
import pydantic
import pytest
import respx
from fastapi.testclient import TestClient
from fastmcp import Client as FastMCPClient

from registry_mcp.api.main import app
from registry_mcp.core import cache
from registry_mcp.core.models import (
    CompanyReport,
    CompanyStatus,
    ErrorCode,
    FinancialPeriod,
    RegistryError,
)
from registry_mcp.core.registry import get_registry
from registry_mcp.mcp.server import mcp
from registry_mcp.registries.no import accounts, mapping, rules
from registry_mcp.registries.no import client as client_module

FIXTURES = Path(__file__).parent / "fixtures"
BASE_URL = client_module.BASE_URL


def _load_fixture(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return result


def _load_accounts_fixture(name: str) -> list[dict[str, Any]]:
    """`GET /regnskapsregisteret/regnskap/{orgnr}` answers a **bare JSON
    array**, not an envelope — so these fixtures are lists, not dicts."""
    result: list[dict[str, Any]] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
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


def test_euid_and_advertising_protected_are_null_for_norway() -> None:
    """R-2 (D-026(a),(b)): both keys are always present in the serialised
    document and `null` for Norway, which publishes neither a EUID nor an
    advertising-protection flag (D-004: always present, never omitted)."""
    report = mapping.map_entity(EQUINOR, source_url="https://example/enheter/923609016")
    dumped = report.model_dump(mode="json")
    assert dumped["euid"] is None
    assert dumped["advertising_protected"] is None


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


def test_el_ansari_enk_gets_personal_data_note() -> None:
    """`research/07-product-improvements.md` item 10(1): an ENK's record *is*
    a record about its proprietor, a natural person — the registered name
    and address are often theirs personally, not a trading identity. The
    mapping layer states this on the report itself (D-010: prose about a
    country's data lives in that country's module), citing Enhetsregisteret
    as the source, rather than leaving the caveat only in the docs."""
    report = mapping.map_entity(EL_ANSARI, source_url="https://example/enheter/833285602")
    assert report.legal_form_code == "ENK"
    matches = [note for note in report.notes if "personal data" in note]
    assert len(matches) == 1
    note = matches[0]
    assert "sole proprietorship" in note
    assert "natural person" in note
    assert "Enhetsregisteret" in note


def test_non_enk_report_gets_no_personal_data_note() -> None:
    """Equinor is an ASA, not an ENK — the caveat must not leak onto every
    report regardless of legal form."""
    report = mapping.map_entity(EQUINOR, source_url="https://example/enheter/923609016")
    assert not any("personal data" in note for note in report.notes)


def test_el_ansari_employees_flag_true_but_count_absent_is_not_reported() -> None:
    """**D-011**: this live payload has `harRegistrertAntallAnsatte: true`
    with no `antallAnsatte` key at all (brreg appears to omit the field
    rather than send `0`). `employees_reported` is *derived* —
    `harRegistrertAntallAnsatte and antallAnsatte is not None` — precisely so
    that `employees_reported is True` implies `employees is not None` is a
    real invariant; a set flag with no number behind it must read as "we
    don't have a figure", not as a contradictory "we have one, and it is
    unknown". `employees` itself is never synthesised to `0`."""
    assert "antallAnsatte" not in EL_ANSARI
    assert EL_ANSARI["harRegistrertAntallAnsatte"] is True
    report = mapping.map_entity(EL_ANSARI, source_url="https://example/enheter/833285602")
    assert report.employees is None
    assert report.employees_reported is False
    assert any(
        "flagged an employee count" in note and "did not return the number" in note
        for note in report.notes
    )


def test_employees_reported_invariant_implies_employees_not_none() -> None:
    """The whole point of D-011: `employees_reported is True` must always mean
    `employees is not None`, on any fixture."""
    for fixture in (EQUINOR, BROENNOYSUND, EL_ANSARI):
        report = mapping.map_entity(fixture, source_url="https://example/enheter/x")
        if report.employees_reported:
            assert report.employees is not None


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
# N8 (T10 review): `deregistered_at`/`bankruptcy_date` and DELETED/BANKRUPT
# status had never travelled the actual `map_entity` path in any test — only
# `rules.derive_status` was unit-tested directly. Build synthetic payloads
# from the Equinor fixture (a real, otherwise-valid entity) with `slettedato`
# / `konkursdato` set, the same shape brreg itself returns for a deleted or
# bankrupt entity (`NORBIZ_SPEC.md` §1.1, §8).
# ---------------------------------------------------------------------------


def test_mapping_slettedato_maps_to_deleted_status_and_deregistered_at() -> None:
    data = dict(EQUINOR)
    data["slettedato"] = "2024-01-15"
    report = mapping.map_entity(data, source_url="https://example/enheter/923609016")
    assert report.status.value == "deleted"
    assert report.is_active is False
    assert report.deregistered_at == date(2024, 1, 15)
    assert any("deleted" in note.lower() for note in report.notes)


def test_mapping_konkursdato_maps_to_bankrupt_status_and_bankruptcy_date() -> None:
    data = dict(EQUINOR)
    data["konkurs"] = True
    data["konkursdato"] = "2026-07-08"
    report = mapping.map_entity(data, source_url="https://example/enheter/923609016")
    assert report.status.value == "bankrupt"
    assert report.is_active is False
    assert report.bankruptcy_date == date(2026, 7, 8)
    assert any("bankrupt" in note.lower() for note in report.notes)


def test_mapping_slettedato_and_konkurs_together_deleted_wins() -> None:
    """Status precedence (`NORBIZ_SPEC.md` §8): deletion beats bankruptcy,
    verified through the mapping path, not just `derive_status` directly."""
    data = dict(EQUINOR)
    data["konkurs"] = True
    data["konkursdato"] = "2026-07-08"
    data["slettedato"] = "2024-01-15"
    report = mapping.map_entity(data, source_url="https://example/enheter/923609016")
    assert report.status.value == "deleted"
    assert report.deregistered_at == date(2024, 1, 15)
    # bankruptcy_date is still mapped straight from konkursdato regardless of
    # which status wins — it is a separate field, not gated by status.
    assert report.bankruptcy_date == date(2026, 7, 8)


def test_mapping_deleted_and_bankrupt_entities_get_no_deadlines() -> None:
    deleted = dict(EQUINOR)
    deleted["slettedato"] = "2024-01-15"
    deleted_report = mapping.map_entity(deleted, source_url="https://example/enheter/923609016")
    assert rules.deadlines_for(deleted_report, date(2026, 3, 15)) == []

    bankrupt = dict(EQUINOR)
    bankrupt["konkurs"] = True
    bankrupt["konkursdato"] = "2026-07-08"
    bankrupt_report = mapping.map_entity(bankrupt, source_url="https://example/enheter/923609016")
    assert rules.deadlines_for(bankrupt_report, date(2026, 3, 15)) == []


# ---------------------------------------------------------------------------
# D-010 follow-up: CompanyReport.notes carries the calendar-year assumption
# and/or `deadline_exemption_note`, since `Registry.deadline_report` copies
# `notes` verbatim into `DeadlineReport.notes` for both REST and MCP.
# ---------------------------------------------------------------------------


def test_calendar_year_assumption_note_present_when_any_annual_deadline_applies() -> None:
    """Equinor (ASA, active, annual-accounts duty) gets annual deadlines, so
    the calendar-year assumption must be surfaced in `notes`. Corrected
    2026-09-05 (R01 §3, D-023): the note must say a deviating year selects a
    different rule (the 1 February branch), not just a shifted date, and must
    point at Regnskapsregisteret rather than claim nobody publishes the
    accounting period."""
    report = mapping.map_entity(EQUINOR, source_url="https://example/enheter/923609016")
    assert any("calendar-year" in note for note in report.notes)
    assert any("1 February" in note for note in report.notes)
    assert any("Regnskapsregisteret" in note for note in report.notes)


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
async def test_429_is_rate_limited_not_retried() -> None:
    """DECISIONS.md D-019: brreg's 429 maps to `rate_limited` (429), the same
    code Britain uses, not `upstream_error` (502) — the register is not
    broken, the call will succeed shortly. Never retried."""
    route = respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(429))
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("923609016")
    assert excinfo.value.code is ErrorCode.RATE_LIMITED
    assert excinfo.value.hint
    assert route.call_count == 1


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
    # D-020: `SearchResult.hits` is always confidence-descending, enforced by
    # a `core/models.py` validator — pinned for Norway too, alongside GB's
    # equivalent (`tests/test_client_gb.py::test_90_search_tesco_envelope`).
    confidences = [hit.confidence for hit in result.hits]
    assert confidences == sorted(confidences, reverse=True)


async def test_search_limit_out_of_range_raises_bad_request() -> None:
    with pytest.raises(RegistryError) as excinfo:
        await client_module.search("equinor", limit=0)
    assert excinfo.value.code is ErrorCode.BAD_REQUEST

    with pytest.raises(RegistryError) as excinfo:
        await client_module.search("equinor", limit=101)
    assert excinfo.value.code is ErrorCode.BAD_REQUEST


@respx.mock
async def test_registry_aclose_closes_underlying_http_client() -> None:
    """B2 (T10 review, D-014): `BrregRegistry.aclose()` must actually close
    the shared `httpx.AsyncClient`, not just drop the reference to it."""
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    registry = get_registry("NO")

    await registry.lookup("923609016")  # forces client_module._client to be created
    http_client = client_module._client
    assert http_client is not None
    assert http_client.is_closed is False

    await registry.aclose()

    assert http_client.is_closed is True
    # `client_module._client` is also reset to `None` after `aclose()`, but
    # mypy's narrowing conflates that module global with the `http_client`
    # alias above and (wrongly) calls a fresh read of it unreachable — so the
    # behaviour is exercised only through `http_client.is_closed`, which is
    # what the review actually asked for.


# ---------------------------------------------------------------------------
# H. Live done-check (network; excluded from CI)
# ---------------------------------------------------------------------------


@pytest.mark.live
async def test_96_live_lookup_cached_then_true() -> None:
    first = await client_module.lookup("923609016")
    assert first.cached is False
    second = await client_module.lookup("923609016")
    assert second.cached is True


#: Top-level brreg fields `map_entity` reads unconditionally (present on every
#: entity payload brreg has ever returned in this project's experience).
_MANDATORY_TOP_LEVEL_FIELDS = {
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

#: Top-level brreg fields `map_entity` reads, but which a given entity's
#: payload may omit entirely (`NORBIZ_SPEC.md` §2).
_OPTIONAL_TOP_LEVEL_FIELDS = {
    "konkursdato",
    "slettedato",
    "overordnetEnhet",
    "epostadresse",
    "stiftelsesdato",
    "registreringsdatoForetaksregisteret",
    "registreringsdatoMerverdiavgiftsregisteret",
    "vedtektsfestetFormaal",
    "aktivitet",
    "kapital",
    "sisteInnsendteAarsregnskap",
    "antallAnsatte",
    "hjemmeside",
    "telefon",
    "erIKonsern",
    "forretningsadresse",
    "postadresse",
    "naeringskode1",
    "naeringskode2",
    "naeringskode3",
    "institusjonellSektorkode",
}

#: Brreg fields `NORBIZ_SPEC.md` §2 deliberately does **not** map (listed
#: there by name). Top-level only — `kapital.antallAksjer`/`.type`/`.innfortDato`
#: are nested inside the (mapped) `kapital` object, not separate top-level keys.
_DELIBERATELY_UNMAPPED_FIELDS = {
    "maalform",
    "paategninger",
    "frivilligMvaRegistrertBeskrivelser",
    "registreringsdatoFrivilligMerverdiavgiftsregisteret",
    "registreringsdatoMerverdiavgiftsregisteretEnhetsregisteret",
    "registreringsdatoAntallAnsatteEnhetsregisteret",
    "registreringsdatoAntallAnsatteNAVAaregisteret",
    "vedtektsdato",
    "respons_klasse",
    "_links",
}


def test_97_live_fixture_fields_present_or_optional() -> None:
    """Every brreg field the mapper reads is present in the live 923609016
    payload, or is explicitly optional per `NORBIZ_SPEC.md` §2; and every
    top-level field the live payload actually carries is accounted for by
    one of mandatory / optional / deliberately-unmapped — i.e. nothing in a
    real response falls through this classification unnoticed."""
    missing = _MANDATORY_TOP_LEVEL_FIELDS - EQUINOR.keys()
    assert not missing, f"Live 923609016 payload is missing mandatory fields: {missing}"

    accounted_for = (
        _MANDATORY_TOP_LEVEL_FIELDS | _OPTIONAL_TOP_LEVEL_FIELDS | _DELIBERATELY_UNMAPPED_FIELDS
    )
    unaccounted = EQUINOR.keys() - accounted_for
    assert not unaccounted, (
        f"Live 923609016 payload has top-level fields this test does not classify as "
        f"mandatory, optional, or deliberately unmapped: {unaccounted}"
    )


# ---------------------------------------------------------------------------
# R-5d — `registries/no/accounts.py` and `client.fetch_accounts`
#
# `DECISIONS.md` D-042(i) (R-5d), D-041(c)/(d)/(h), D-042(e)/(f)/(g)/(h)/(j),
# and D-023(d), whose "not implemented now" this closes. Built behind the
# seam: these exercise `registries/no/accounts.py`'s local stand-ins, not
# `core.models.FilingHistory`, which does not exist yet.
# ---------------------------------------------------------------------------

ACCOUNTS_URL = accounts.ACCOUNTS_URL

#: EQUINOR ASA — a calendar accounting year, 2025-01-01/2025-12-31. Recorded
#: live 2026-09-08; pairs with `brreg_923609016.json`, the same entity's
#: `/enheter` record.
EQUINOR_ACCOUNTS = _load_accounts_fixture("brreg_regnskap_923609016.json")

#: ORACLE NORGE AS — a **deviating** accounting year, 2024-06-01/2025-05-31.
#: The period end falls between 1 January and 30 June, so regnskapsloven
#: § 8-3(1) second sentence gives it a 1 February deadline, not the 31 July
#: this project computes today. Recorded live 2026-09-08.
ORACLE_ACCOUNTS = _load_accounts_fixture("brreg_regnskap_939319891.json")

#: .BEIN BERGEN AS — a stub first period, 2025-06-19/2025-12-31, running from
#: incorporation. The live proof that `fraDato` is published data and not
#: `tilDato` minus twelve months. Recorded live 2026-09-08.
STUB_PERIOD_ACCOUNTS = _load_accounts_fixture("brreg_regnskap_935845114.json")

_FETCHED_AT = datetime(2026, 9, 8, 9, 30, tzinfo=UTC)


def test_r5d_maps_a_calendar_year_filing() -> None:
    block = accounts.map_regnskap(
        EQUINOR_ACCOUNTS, "923609016", cached=False, fetched_at=_FETCHED_AT
    )

    assert len(block.documents) == 1
    doc = block.documents[0]
    assert doc.kind == "annual_accounts"
    assert doc.period_start == date(2025, 1, 1)
    assert doc.period_end == date(2025, 12, 31)
    assert doc.document_id == "2026635024"
    assert doc.category == "SELSKAP"
    assert block.financial_year_end == date(2025, 12, 31)


def test_r5d_period_start_is_published_not_derived() -> None:
    """The Norway/Sweden asymmetry, pinned.

    D-041(d) put `period_start` on `FiledDocument` because Norway publishes
    `regnskapsperiode.fraDato` and Sweden publishes no `...From`; D-041(e)
    refused to derive a Swedish one by subtracting twelve months, because a
    first or final period may be short. This fixture is that refusal being
    right: a derived start would have said 2025-01-01 and the register says
    2025-06-19.
    """
    block = accounts.map_regnskap(
        STUB_PERIOD_ACCOUNTS, "935845114", cached=False, fetched_at=_FETCHED_AT
    )

    doc = block.documents[0]
    assert doc.period_start == date(2025, 6, 19)
    assert doc.period_end == date(2025, 12, 31)
    assert doc.period_start != date(doc.period_end.year, 1, 1)
    assert any("shorter than an ordinary year" in note for note in block.notes)


def test_r5d_deviating_accounting_year_note_names_the_other_rule() -> None:
    """D-023(a): a deviating accounting year selects a *different rule*, not a
    shifted date, and the note must say so — the variance D-023(d) recorded as
    unverified, now verified live."""
    block = accounts.map_regnskap(
        ORACLE_ACCOUNTS, "939319891", cached=False, fetched_at=_FETCHED_AT
    )

    assert block.financial_year_end == date(2025, 5, 31)
    assert block.documents[0].period_start == date(2024, 6, 1)
    note = next(n for n in block.notes if "deviating accounting year" in n)
    assert "§ 8-3(1)" in note
    assert "1 February" in note
    # No stub-period note: twelve full months, just not calendar ones.
    assert not any("than an ordinary year" in n for n in block.notes)


def test_r5d_calendar_year_gets_no_deviating_year_note() -> None:
    block = accounts.map_regnskap(
        EQUINOR_ACCOUNTS, "923609016", cached=False, fetched_at=_FETCHED_AT
    )
    assert not any("deviating accounting year" in note for note in block.notes)


def test_r5d_no_filing_date_and_no_fee_point_measurement() -> None:
    """Regnskapsregisteret publishes no filing date under any name, so
    `filed_at` is `None` and `days_from_fee_point` is `None` with it
    (D-041(d)). `journalnr` is carried verbatim as the opaque handle and is
    never read as a date (D-026(a))."""
    for payload, orgnr in (
        (EQUINOR_ACCOUNTS, "923609016"),
        (ORACLE_ACCOUNTS, "939319891"),
        (STUB_PERIOD_ACCOUNTS, "935845114"),
    ):
        block = accounts.map_regnskap(payload, orgnr, cached=False, fetched_at=_FETCHED_AT)
        doc = block.documents[0]
        assert doc.filed_at is None
        assert doc.days_from_fee_point is None
        assert doc.document_id is not None
        assert not doc.document_id.startswith("20") or "-" not in doc.document_id


def test_r5d_empty_block_is_an_answer_not_an_absence() -> None:
    """D-041(c)'s two-level nullability. An empty `documents` means the
    register holds nothing for this entity — the block is still present, with
    its own provenance."""
    block = accounts.map_regnskap([], "974760673", cached=False, fetched_at=_FETCHED_AT)

    assert block.documents == []
    assert block.financial_year_end is None
    assert block.provenance.fetched_at == _FETCHED_AT
    assert block.provenance.source_url == ACCOUNTS_URL.format(orgnr="974760673")
    assert any("holds no filed annual accounts" in note for note in block.notes)


def test_r5d_none_payload_maps_like_an_empty_list() -> None:
    assert accounts.map_regnskap(None, "974760673", cached=False, fetched_at=_FETCHED_AT).documents == []


def test_scope_note_is_present_first_on_every_block_d044b() -> None:
    """D-044(b): one include name, `filings`, covers three differently-scoped
    answers *because* "the scope difference is disclosed in the block's own
    `notes`, on every call". SE and GB got this test from T40; Norway's
    `_ONE_PERIOD_NOTE`/`_EMPTY_NOTE` was the *model* for both but was never
    itself pinned (REVIEW.md T58 finding 3; mutations M8c/M8d — appending
    the note instead of inserting it first, and deleting it outright — both
    left 1030 passing). Both branches, because Norway's note is chosen by a
    branch (filled vs. empty) rather than prepended unconditionally like
    Sweden's and Britain's."""
    filled = accounts.map_regnskap(
        EQUINOR_ACCOUNTS, "923609016", cached=False, fetched_at=_FETCHED_AT
    )
    assert filled.notes[0].startswith(
        "Regnskapsregisteret's open dataset publishes only the most recently filed "
        "accounting period"
    )

    empty = accounts.map_regnskap([], "974760673", cached=False, fetched_at=_FETCHED_AT)
    assert empty.notes[0] == accounts._EMPTY_NOTE


def test_r5d_documents_sorted_newest_first() -> None:
    """Norway's open dataset returns one period, but the list shape is the
    register's own and D-041(g)'s ordering is the model's contract."""
    older = dict(EQUINOR_ACCOUNTS[0])
    older["regnskapsperiode"] = {"fraDato": "2023-01-01", "tilDato": "2023-12-31"}
    newer = dict(EQUINOR_ACCOUNTS[0])
    newer["regnskapsperiode"] = {"fraDato": "2024-01-01", "tilDato": "2024-12-31"}

    block = accounts.map_regnskap([older, newer], "923609016", cached=False, fetched_at=_FETCHED_AT)

    assert [d.period_end for d in block.documents] == [date(2024, 12, 31), date(2023, 12, 31)]
    assert block.financial_year_end == date(2024, 12, 31)


def test_r5d_provenance_is_its_own_moment_and_its_own_cache_state() -> None:
    """D-041(c): *one fetch, one `SourceRef`* — not one organisation. Both
    fetches go to `data.brreg.no` under NLOD 2.0, and this block still carries
    its own five fields."""
    block = accounts.map_regnskap(
        EQUINOR_ACCOUNTS, "923609016", cached=True, fetched_at=_FETCHED_AT
    )
    assert block.provenance.cached is True
    assert block.provenance.license == "NLOD 2.0"
    assert block.provenance.source == "Regnskapsregisteret (Brønnøysundregistrene)"
    assert block.provenance.source_url == ACCOUNTS_URL.format(orgnr="923609016")


def test_r5d_minimisation_no_field_of_this_block_can_name_a_person() -> None:
    """D-042(e)'s field-level test and D-042(f)'s bar, as a regression guard.

    The live payload carries no person-bearing field at all — `revisjon` is two
    booleans, not an auditor, and `virksomhet` names no proprietor — so the
    mapper reads a closed set of keys and relays nothing else. This injects the
    fields a future upstream change might plausibly add and asserts that not one
    character of them reaches the block.
    """
    poisoned = dict(EQUINOR_ACCOUNTS[0])
    poisoned["revisjon"] = {
        "ikkeRevidertAarsregnskap": False,
        "fravalgRevisjon": False,
        "revisor": "Kari Nordmann, statsautorisert revisor",
        "revisorOrganisasjonsnummer": "987654321",
    }
    poisoned["virksomhet"] = {
        **EQUINOR_ACCOUNTS[0]["virksomhet"],
        "innehaver": "Ola Nordmann",
        "signatur": "Ola Nordmann, styreleder",
    }
    poisoned["daglig_leder"] = "Ola Nordmann"

    block = accounts.map_regnskap([poisoned], "923609016", cached=False, fetched_at=_FETCHED_AT)
    serialised = json.dumps(block.model_dump(mode="json"), ensure_ascii=False)

    for forbidden in ("Nordmann", "revisor", "innehaver", "signatur", "daglig_leder", "987654321"):
        assert forbidden not in serialised


def test_r5d_key_figures_are_deliberately_not_carried() -> None:
    """D-042(g)'s anti-bend rule: the ~20 numeric key figures on the wire are
    company facts that pass minimisation and still have no home in the shape
    D-041(d)/D-042(h) ruled. Widening a shared attachment model is a
    `DECISIONS.md` entry, not an implementer's call — and this pins the choice
    so that adding them later is a deliberate act."""
    block = accounts.map_regnskap(
        EQUINOR_ACCOUNTS, "923609016", cached=False, fetched_at=_FETCHED_AT
    )
    serialised = json.dumps(block.model_dump(mode="json"))

    assert "67956000000" not in serialised  # sumDriftsinntekter
    assert "aarsresultat" not in serialised
    assert "sumEiendeler" not in serialised
    assert set(block.documents[0].model_dump()) == {
        "kind",
        "period_end",
        "period_start",
        "filed_at",
        "days_from_fee_point",
        "document_id",
        "file_format",
        "category",
        "type_code",
        "description_code",
    }


@respx.mock
async def test_r5d_fetch_accounts_maps_a_live_shaped_200() -> None:
    route = respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(
        return_value=httpx.Response(200, json=EQUINOR_ACCOUNTS)
    )

    block = await client_module.fetch_accounts("923 609 016")

    assert route.call_count == 1
    assert block.financial_year_end == date(2025, 12, 31)
    assert block.provenance.cached is False


@respx.mock
async def test_r5d_404_is_an_empty_block_never_not_found() -> None:
    """The load-bearing recon finding. Regnskapsregisteret answers a bodyless
    404 both for an entity that has filed nothing (974760673, a real, live
    Brønnøysundregistrene entity) and for a number never issued, so it cannot
    decide existence and is not allowed to — D-041(h), D-042(j). This is the
    same trap that would have turned every unencumbered British company into a
    non-existent one, except that here it is the ordinary case."""
    respx.get(ACCOUNTS_URL.format(orgnr="974760673")).mock(return_value=httpx.Response(404))

    block = await client_module.fetch_accounts("974760673")

    assert block.documents == []
    assert block.financial_year_end is None
    assert any("holds no filed annual accounts" in note for note in block.notes)


@respx.mock
async def test_r5d_500_is_upstream_error_after_exactly_one_retry() -> None:
    """Banks and insurers 500 here permanently while their company record says
    they filed. `_fetch` still retries once — shared with `lookup`/`search` —
    and the hint says not to keep retrying (D-042(j): the attachment fails,
    the lookup does not)."""
    route = respx.get(ACCOUNTS_URL.format(orgnr="916823525")).mock(
        return_value=httpx.Response(500, json=_load_fixture("brreg_regnskap_500.json"))
    )

    with pytest.raises(RegistryError) as excinfo:
        await client_module.fetch_accounts("916823525")

    assert route.call_count == 2
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR
    assert "banks, insurers" in excinfo.value.hint


@respx.mock
async def test_r5d_429_is_rate_limited_and_not_retried() -> None:
    route = respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(
        return_value=httpx.Response(429)
    )

    with pytest.raises(RegistryError) as excinfo:
        await client_module.fetch_accounts("923609016")

    assert route.call_count == 1
    assert excinfo.value.code is ErrorCode.RATE_LIMITED


@respx.mock
async def test_r5d_invalid_orgnr_is_rejected_before_any_request() -> None:
    route = respx.get(url__startswith="https://data.brreg.no/regnskapsregisteret")

    with pytest.raises(RegistryError) as excinfo:
        await client_module.fetch_accounts("12345")

    assert route.call_count == 0
    assert excinfo.value.code is ErrorCode.INVALID_ID


@respx.mock
async def test_r5d_cache_hit_preserves_its_own_fetched_at() -> None:
    """D-006, and D-041(c)'s reason for a per-block `SourceRef`: this block's
    `cached`/`fetched_at` are its own and may disagree with the record's."""
    route = respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(
        return_value=httpx.Response(200, json=EQUINOR_ACCOUNTS)
    )

    first = await client_module.fetch_accounts("923609016")
    second = await client_module.fetch_accounts("923609016")

    assert route.call_count == 1
    assert first.provenance.cached is False
    assert second.provenance.cached is True
    assert second.provenance.fetched_at == first.provenance.fetched_at
    assert second.financial_year_end == first.financial_year_end


@respx.mock
async def test_r5d_empty_result_is_cached_under_the_short_ttl_status() -> None:
    """D-042(j)'s 24 h / 1 h asymmetry, implemented with `core/cache.py`'s
    existing `not_found` status purely for its TTL — never raised as an error
    on the read path. Same stand-in `registries/gb/client.py::fetch_charges`
    uses; both go when the per-kind TTL table is built."""
    respx.get(ACCOUNTS_URL.format(orgnr="974760673")).mock(return_value=httpx.Response(404))

    await client_module.fetch_accounts("974760673")
    entry = cache.get("NO:brreg:filings:974760673")

    assert entry is not None
    assert entry.status == "not_found"
    # And reading it back is an empty block, not a raised `not_found`.
    assert (await client_module.fetch_accounts("974760673")).documents == []


@respx.mock
async def test_r5d_non_list_200_body_is_treated_as_empty() -> None:
    """Defensive: the live endpoint always returns a bare array, but a bare
    array is an unusual JSON contract and this must never raise."""
    respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(
        return_value=httpx.Response(200, json={"unexpected": "envelope"})
    )

    assert (await client_module.fetch_accounts("923609016")).documents == []


@pytest.mark.live
async def test_r5d_live_empty_case_is_a_404_on_a_real_entity() -> None:
    """The recon finding, re-run against the register. `974760673` is
    REGISTERENHETEN I BRØNNØYSUND — it exists (`brreg_974760673.json` is its
    `/enheter` record) and has no filed annual accounts here."""
    block = await client_module.fetch_accounts("974760673")
    assert block.documents == []
    assert block.provenance.cached is False


@pytest.mark.live
async def test_r5d_live_deviating_accounting_year_is_real() -> None:
    """D-023(d) called the field's variance unverified. It is not: ORACLE
    NORGE AS files to a 31 May year end."""
    block = await client_module.fetch_accounts("939319891")
    assert block.financial_year_end is not None
    assert (block.financial_year_end.month, block.financial_year_end.day) != (12, 31)
    assert block.documents[0].period_start is not None


def test_r5d_an_extended_first_period_is_reported_too() -> None:
    """Regnskapsloven § 1-7 lets a first or final period be extended as well as
    shortened, so the length note covers both directions. No live example was
    found in ~600 sampled payloads, so this one is constructed from a recorded
    payload's own shape — the *dates* are synthetic, the envelope is not."""
    extended = dict(EQUINOR_ACCOUNTS[0])
    extended["regnskapsperiode"] = {"fraDato": "2024-01-01", "tilDato": "2025-06-30"}

    block = accounts.map_regnskap([extended], "923609016", cached=False, fetched_at=_FETCHED_AT)

    assert any("longer than an ordinary year" in note for note in block.notes)
    assert block.documents[0].period_start == date(2024, 1, 1)


def test_r5d_an_ordinary_year_is_never_called_unusual() -> None:
    """Measured in days, so no 12-month period trips the threshold whatever day
    of the month it starts on — the Oracle fixture (1 June to 31 May) and a
    mid-month year both stay quiet."""
    midmonth = dict(EQUINOR_ACCOUNTS[0])
    midmonth["regnskapsperiode"] = {"fraDato": "2025-06-19", "tilDato": "2026-06-18"}

    for payload in ([midmonth], ORACLE_ACCOUNTS, EQUINOR_ACCOUNTS):
        block = accounts.map_regnskap(payload, "923609016", cached=False, fetched_at=_FETCHED_AT)
        assert not any("than an ordinary year" in note for note in block.notes)


# ---------------------------------------------------------------------------
# T38 / R-5f — `registries/no/accounts.py::map_regnskap_financials` and
# `client.fetch_financials` / `fetch_accounts` — `include=["financials"]`
# (`DECISIONS.md` D-043).
#
# Every test in this section lives here rather than in `tests/test_attachments.py`
# (per the orchestrator: T42 owns that file this round) and rather than in
# `tests/test_mcp.py`/`tests/test_wiring.py`, even where a test's natural home
# would otherwise be one of those — flagged individually below.
#
# Part A5: the mapper, against the six fixtures `tasks/T38.md` names plus the
# three already recorded for R-5d. Part B3: the wiring — one shared fetch,
# one `SourceRef`, cross-country `bad_request`, REST/MCP parity and a failed
# fetch's note.
# ---------------------------------------------------------------------------

#: 222 HOLDING AS — negative `sumGjeld` (-108,837); equity exceeds total
#: assets; `langsiktigGjeld: {}` and `finansinntekt: {}`; `totalresultat`
#: present. Recorded live 2026-09-08.
HOLDING_222_ACCOUNTS = _load_accounts_fixture("brreg_regnskap_931883836.json")

#: 4WD HOLDING AS — `driftsinntekter: {}` beside a present `driftsresultat`
#: and `sumDriftskostnad`. Recorded live 2026-09-08.
FWD_HOLDING_ACCOUNTS = _load_accounts_fixture("brreg_regnskap_936134610.json")

#: 4U HOLDING AS — explicit `sumDriftsinntekter: 0.0`, the pair to the
#: fixture above. Recorded live 2026-09-08.
FU_HOLDING_ACCOUNTS = _load_accounts_fixture("brreg_regnskap_921378963.json")

#: 22 INVEST AS — `fravalgRevisjon: true`, `smaaForetak: true`, negative
#: equity. Recorded live 2026-09-08.
INVEST_22_ACCOUNTS = _load_accounts_fixture("brreg_regnskap_925922900.json")

#: AGATON SAX MT AS — `avviklingsregnskap: true`, final stub period
#: 2026-01-01/2026-04-30. Recorded live 2026-09-08.
AGATON_SAX_ACCOUNTS = _load_accounts_fixture("brreg_regnskap_998575133.json")


# ---------------------------------------------------------------------------
# A5 — the mapper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "orgnr"),
    [
        (EQUINOR_ACCOUNTS, "923609016"),
        (ORACLE_ACCOUNTS, "939319891"),
        (STUB_PERIOD_ACCOUNTS, "935845114"),
        (HOLDING_222_ACCOUNTS, "931883836"),
        (FWD_HOLDING_ACCOUNTS, "936134610"),
        (FU_HOLDING_ACCOUNTS, "921378963"),
        (INVEST_22_ACCOUNTS, "925922900"),
        (AGATON_SAX_ACCOUNTS, "998575133"),
    ],
)
def test_d043_every_fixture_maps_without_raising(payload: list[dict[str, Any]], orgnr: str) -> None:
    block = accounts.map_regnskap_financials(payload, orgnr, cached=False, fetched_at=_FETCHED_AT)
    assert len(block.periods) == 1
    assert block.provenance.source_url == ACCOUNTS_URL.format(orgnr=orgnr)


def test_d043_936134610_revenue_none_and_921378963_revenue_zero_in_one_test() -> None:
    """The load-bearing pair (D-043(f)): two holding companies with no
    turnover, read the same afternoon, publish that absence two different
    ways. Asserted together so the distinction cannot be silently lost."""
    no_revenue = accounts.map_regnskap_financials(
        FWD_HOLDING_ACCOUNTS, "936134610", cached=False, fetched_at=_FETCHED_AT
    )
    zero_revenue = accounts.map_regnskap_financials(
        FU_HOLDING_ACCOUNTS, "921378963", cached=False, fetched_at=_FETCHED_AT
    )
    assert no_revenue.periods[0].income_statement is not None
    assert no_revenue.periods[0].income_statement.revenue is None
    assert zero_revenue.periods[0].income_statement is not None
    assert zero_revenue.periods[0].income_statement.revenue == 0.0


def test_d043_931883836_liabilities_carried_negative_unchanged() -> None:
    """`sumGjeld` is real, negative, filed data (D-043(e)) and is carried
    exactly, never clamped or dropped.

    **Deviation from `tasks/T38.md` A5, reported per the brief's own
    instruction to stop and report rather than choose differently when the
    wire contradicts a number in D-043.** The brief additionally asks for "a
    reconciliation note ... naming both totals" on this fixture. Live,
    `sumEgenkapitalGjeld` and `sumEiendeler` are both exactly 27,949 — equal,
    not differing — so D-043(e)'s reconciliation note correctly does *not*
    fire here (asserted below). D-043(e) itself only ever attributes this
    organisation number to the *negative `sumGjeld`* finding, never to a
    reconciliation gap; the three live reconciliation-gap examples it names
    (931626469, 880998412, 927866951) are different companies, not in this
    task's fixture set. What *is* true and striking about this filing —
    asserted below instead, as a carried value rather than invented as a
    `notes` sentence, since D-043(e) permits no comparison beyond the one
    reconciliation note — is that `sumEgenkapital` (136,786) exceeds
    `sumEiendeler` (27,949), which the negative liability makes
    arithmetically consistent rather than a filing error.
    """
    block = accounts.map_regnskap_financials(
        HOLDING_222_ACCOUNTS, "931883836", cached=False, fetched_at=_FETCHED_AT
    )
    period = block.periods[0]
    assert period.balance_sheet is not None
    assert period.balance_sheet.liabilities == -108837.0
    assert period.balance_sheet.total_assets == 27949.0
    assert period.balance_sheet.total_equity_and_liabilities == 27949.0
    assert period.balance_sheet.equity == 136786.0
    assert period.balance_sheet.equity > period.balance_sheet.total_assets
    assert not any("differ by" in note for note in block.notes)
    assert period.income_statement is not None
    assert period.income_statement.total_comprehensive_income == -4809.0


def test_d043_923609016_usd_currency_non_nok_note_and_reconciliation_note() -> None:
    block = accounts.map_regnskap_financials(
        EQUINOR_ACCOUNTS, "923609016", cached=False, fetched_at=_FETCHED_AT
    )
    period = block.periods[0]
    assert period.currency == "USD"
    assert any("USD" in note and "not NOK" in note for note in block.notes)
    assert any("differ by 1,000,000" in note for note in block.notes)
    assert period.accounting_framework == "forenkletAnvendelseIFRS"
    assert period.balance_sheet is not None
    assert period.balance_sheet.total_assets == 103432000000.0
    assert period.balance_sheet.total_equity_and_liabilities == 103431000000.0


def test_d043_998575133_liquidation_basis_note_and_no_winding_up_restatement() -> None:
    block = accounts.map_regnskap_financials(
        AGATON_SAX_ACCOUNTS, "998575133", cached=False, fetched_at=_FETCHED_AT
    )
    period = block.periods[0]
    assert period.liquidation_basis is True
    assert period.period_start == date(2026, 1, 1)
    assert period.period_end == date(2026, 4, 30)
    assert any("winding-up account" in note for note in block.notes)
    # D-043(g): the note must not restate the winding-up itself — that is
    # `CompanyReport.status`'s job, from the first round trip.
    assert not any(
        phrase in note.lower()
        for note in block.notes
        for phrase in ("is being wound up", "is in liquidation", "the company is")
    )


def test_d043_925922900_small_entity_audit_exempt_and_negative_equity() -> None:
    block = accounts.map_regnskap_financials(
        INVEST_22_ACCOUNTS, "925922900", cached=False, fetched_at=_FETCHED_AT
    )
    period = block.periods[0]
    assert period.small_entity is True
    assert period.audit_exempt is True
    assert period.balance_sheet is not None
    assert period.balance_sheet.equity == -2743.0
    assert any("small entity" in note or "reduced-disclosure" in note for note in block.notes)
    assert any("opt out of audit" in note for note in block.notes)


def test_d043_unobserved_scope_word_gives_consolidated_none_never_false() -> None:
    synthetic = dict(EQUINOR_ACCOUNTS[0])
    synthetic["regnskapstype"] = "KONSERN"  # implied by the vocabulary, never observed live
    block = accounts.map_regnskap_financials(
        [synthetic], "923609016", cached=False, fetched_at=_FETCHED_AT
    )
    assert block.periods[0].scope == "KONSERN"
    assert block.periods[0].consolidated is None


def test_d043_missing_currency_skips_period_and_notes_why() -> None:
    synthetic = dict(EQUINOR_ACCOUNTS[0])
    del synthetic["valuta"]
    block = accounts.map_regnskap_financials([synthetic], "923609016", cached=False, fetched_at=_FETCHED_AT)
    assert block.periods == []
    assert any("no currency" in note for note in block.notes)


def test_d043_empty_and_none_payload_present_block_empty_periods() -> None:
    empty = accounts.map_regnskap_financials([], "974760673", cached=False, fetched_at=_FETCHED_AT)
    assert empty.periods == []
    assert any("holds no filed annual accounts" in note for note in empty.notes)

    none_payload = accounts.map_regnskap_financials(
        None, "974760673", cached=False, fetched_at=_FETCHED_AT
    )
    assert none_payload.periods == []


def test_d043_financial_period_requires_currency() -> None:
    with pytest.raises(pydantic.ValidationError, match="currency"):
        FinancialPeriod()  # type: ignore[call-arg]


def test_d043_paid_in_equity_reads_the_registers_misspelled_key() -> None:
    """`sumInnskuttEgenkaptial` is spelled that way by the register — pinned
    so nobody "fixes" the spelling later (`tasks/T38.md` A2)."""
    assert "sumInnskuttEgenkaptial" in json.dumps(EQUINOR_ACCOUNTS)
    block = accounts.map_regnskap_financials(
        EQUINOR_ACCOUNTS, "923609016", cached=False, fetched_at=_FETCHED_AT
    )
    assert block.periods[0].balance_sheet is not None
    assert block.periods[0].balance_sheet.paid_in_equity == 995000000.0


def test_d043_no_numeric_field_defaults_to_anything_but_none() -> None:
    """Structural guard behind the `grep -c "float | None"` done-check: every
    field on the two figure models is optional and defaults to `None`, so a
    field the register does not publish can never construct as zero."""
    from registry_mcp.core.models import BalanceSheet, IncomeStatement

    for model in (IncomeStatement, BalanceSheet):
        for name, field in model.model_fields.items():
            assert field.default is None, f"{model.__name__}.{name} does not default to None"


def test_d043_document_id_and_period_end_match_the_sibling_filed_document() -> None:
    """D-043(h)(4): the two blocks may never disagree about the period — both
    are `regnskapsperiode.tilDato`/`journalnr` from the same body."""
    filings = accounts.map_regnskap(EQUINOR_ACCOUNTS, "923609016", cached=False, fetched_at=_FETCHED_AT)
    financials = accounts.map_regnskap_financials(
        EQUINOR_ACCOUNTS, "923609016", cached=False, fetched_at=_FETCHED_AT
    )
    assert filings.documents[0].document_id == financials.periods[0].document_id == "2026635024"
    assert (
        filings.financial_year_end
        == filings.documents[0].period_end
        == financials.periods[0].period_end
    )


# ---------------------------------------------------------------------------
# B3 — the nine invariants D-043(h)/(i)/(j) exist to prove, plus the field-
# routing regression `tests/test_attachments.py` would otherwise carry
# (skipped there this round: T42 owns that file).
# ---------------------------------------------------------------------------


@respx.mock
async def test_d043_fetch_financials_maps_a_live_shaped_200() -> None:
    route = respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(
        return_value=httpx.Response(200, json=EQUINOR_ACCOUNTS)
    )
    block = await client_module.fetch_financials("923 609 016")
    assert route.call_count == 1
    assert block.periods[0].currency == "USD"
    assert block.provenance.cached is False


@respx.mock
async def test_d043_fetch_financials_404_is_an_empty_block_never_not_found() -> None:
    respx.get(ACCOUNTS_URL.format(orgnr="974760673")).mock(return_value=httpx.Response(404))
    block = await client_module.fetch_financials("974760673")
    assert block.periods == []
    assert any("holds no filed annual accounts" in note for note in block.notes)


@respx.mock
async def test_d043_fetch_financials_500_is_upstream_error_after_exactly_one_retry() -> None:
    route = respx.get(ACCOUNTS_URL.format(orgnr="916823525")).mock(
        return_value=httpx.Response(500, json=_load_fixture("brreg_regnskap_500.json"))
    )
    with pytest.raises(RegistryError) as excinfo:
        await client_module.fetch_financials("916823525")
    assert route.call_count == 2
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR


@respx.mock
async def test_d043_fetch_financials_429_is_rate_limited_and_not_retried() -> None:
    route = respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(return_value=httpx.Response(429))
    with pytest.raises(RegistryError) as excinfo:
        await client_module.fetch_financials("923609016")
    assert route.call_count == 1
    assert excinfo.value.code is ErrorCode.RATE_LIMITED


@respx.mock
async def test_d043_fetch_financials_invalid_orgnr_is_rejected_before_any_request() -> None:
    route = respx.get(url__startswith="https://data.brreg.no/regnskapsregisteret")
    with pytest.raises(RegistryError) as excinfo:
        await client_module.fetch_financials("12345")
    assert route.call_count == 0
    assert excinfo.value.code is ErrorCode.INVALID_ID


@respx.mock
async def test_d043_fetch_financials_cache_hit_preserves_its_own_fetched_at() -> None:
    route = respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(
        return_value=httpx.Response(200, json=EQUINOR_ACCOUNTS)
    )
    first = await client_module.fetch_financials("923609016")
    second = await client_module.fetch_financials("923609016")
    assert route.call_count == 1
    assert first.provenance.cached is False
    assert second.provenance.cached is True
    assert second.provenance.fetched_at == first.provenance.fetched_at


@respx.mock
async def test_d043_one_cache_key_serves_both_filings_and_financials() -> None:
    """D-043(h)(1): `filings` (fetched first here) populates the one cache
    entry `financials` then reads — no second upstream request, and the
    entry lives under the key `fetch_accounts` has always used (kept, not
    renamed, per the orchestrator: renaming is `core/cache.py`'s per-kind
    TTL table's decision to make, not this task's)."""
    route = respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(
        return_value=httpx.Response(200, json=EQUINOR_ACCOUNTS)
    )
    await client_module.fetch_accounts("923609016")
    entry = cache.get("NO:brreg:filings:923609016")
    assert entry is not None

    block = await client_module.fetch_financials("923609016")
    assert route.call_count == 1
    assert block.provenance.cached is True


@respx.mock
async def test_d043_invariant1_concurrent_fetch_accounts_and_fetch_financials_share_one_request() -> None:
    """The implementation hazard D-043(h)(3) names by name: `fetch_accounts`
    and `fetch_financials` called concurrently on a cold cache must not race
    into two upstream requests. Exercised directly at the client layer,
    beneath `lookup_with`'s own concurrency (the next test)."""
    route = respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(
        return_value=httpx.Response(200, json=EQUINOR_ACCOUNTS)
    )
    filings, financials = await asyncio.gather(
        client_module.fetch_accounts("923609016"),
        client_module.fetch_financials("923609016"),
    )
    assert route.call_count == 1
    assert filings.provenance == financials.provenance


@respx.mock
async def test_d043_invariant1_lookup_with_both_includes_makes_exactly_one_upstream_request() -> None:
    """B3 invariant 1, at the surface `lookup_with` actually uses: a caller
    asking for both attachments in one call costs one upstream request for
    the accounts payload (plus the one, separate, `/enheter` request the base
    report always costs)."""
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    accounts_route = respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(
        return_value=httpx.Response(200, json=EQUINOR_ACCOUNTS)
    )
    registry = get_registry("NO")
    report = await registry.lookup_with("923609016", ["filings", "financials"])
    assert accounts_route.call_count == 1
    assert report.filings is not None
    assert report.financials is not None


@respx.mock
async def test_d043_invariant2_provenance_equal_in_all_five_fields() -> None:
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(
        return_value=httpx.Response(200, json=EQUINOR_ACCOUNTS)
    )
    registry = get_registry("NO")
    report = await registry.lookup_with("923609016", ["filings", "financials"])
    assert report.filings is not None
    assert report.financials is not None
    assert report.filings.provenance == report.financials.provenance
    assert report.filings.provenance.fetched_at == report.financials.provenance.fetched_at
    assert report.filings.provenance.cached == report.financials.provenance.cached


@respx.mock
async def test_d043_invariant3_filing_history_and_financial_period_agree_on_the_join_keys() -> None:
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(
        return_value=httpx.Response(200, json=EQUINOR_ACCOUNTS)
    )
    registry = get_registry("NO")
    report = await registry.lookup_with("923609016", ["filings", "financials"])
    assert report.filings is not None
    assert report.financials is not None
    filed = report.filings.documents[0]
    period = report.financials.periods[0]
    assert report.filings.financial_year_end == filed.period_end == period.period_end
    assert filed.document_id == period.document_id


@respx.mock
async def test_d043_invariant4_default_lookup_costs_one_request_and_both_blocks_none() -> None:
    entity_route = respx.get(f"{BASE_URL}/enheter/923609016").mock(
        return_value=httpx.Response(200, json=EQUINOR)
    )
    accounts_route = respx.get(ACCOUNTS_URL.format(orgnr="923609016"))
    registry = get_registry("NO")
    report = await registry.lookup_with("923609016")
    assert entity_route.call_count == 1
    assert accounts_route.call_count == 0
    assert report.filings is None
    assert report.financials is None


async def test_d043_invariant5_financials_on_gb_is_bad_request_naming_gb_allowed_set() -> None:
    gb = get_registry("GB")
    with pytest.raises(RegistryError) as excinfo:
        await gb.lookup_with(gb.id_example, ["financials"])
    assert excinfo.value.code is ErrorCode.BAD_REQUEST
    assert "financials" not in excinfo.value.hint
    assert excinfo.value.details["allowed"] == sorted(gb.effective_includes)


# `test_d043_invariant5_financials_on_se_is_bad_request_naming_se_allowed_set`
# pinned SE's *absence* of `financials` shut, per D-043(i)'s "the reason is
# ours, not theirs". D-047(f) reversed exactly that scope decision on
# measurement (`tasks/T55-recon.md`, `tasks/T55.md`), so the invariant it
# checked is retired, not merely renamed: GB's sibling test above is
# unaffected (D-047(f) closes GB `financials` until after 1 April 2028, on
# the register's population), and Sweden's *positive* path — a real
# `lookup_with("...", ["financials"])` succeeding — is exercised in
# `tests/test_client_se.py`'s `test_d047_*` tests instead.


def test_d043_invariant6_country_info_shows_financials_for_norway_and_sweden() -> None:
    """Amended by D-047(f),(g): Norway still fills this block (D-043, T38)
    and Sweden now does too (`tasks/T55.md`), out of the filed K2/K3 iXBRL
    rather than a second-round-trip JSON body — a different mechanism, the
    same `include` name and the same discoverability contract
    (`CountryInfo.supported_includes`, D-042(d)). GB stays excluded, on the
    register's population rather than on parsing (D-047(f))."""
    assert "financials" in get_registry("NO").country_info().supported_includes
    assert "financials" in get_registry("SE").country_info().supported_includes
    assert "financials" not in get_registry("GB").country_info().supported_includes


@respx.mock
async def test_d043_invariant7_deadlines_unchanged_by_adding_financials_on_top_of_filings() -> None:
    """D-043(j): `financials` is never an input to `Registry.deadlines`, so a
    lookup that adds it on top of `filings` must not change one date or one
    `applies_because` string. `DeadlineReport` carries no volatile field (no
    timestamp of its own), so a whole-object comparison is exact, not just
    field-by-field."""
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(
        return_value=httpx.Response(200, json=EQUINOR_ACCOUNTS)
    )
    registry = get_registry("NO")
    today = date(2026, 3, 15)

    with_filings_only = await registry.lookup_with("923609016", ["filings"])
    with_both = await registry.lookup_with("923609016", ["filings", "financials"])

    report_only = registry.deadline_report(with_filings_only, today)
    report_both = registry.deadline_report(with_both, today)
    assert report_only == report_both


@respx.mock
def test_d043_invariant8_rest_and_mcp_lookup_company_include_financials_are_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `include=["financials"]` path (D-043), the same D-004 guarantee
    `tests/test_mcp.py::test_rest_and_mcp_lookup_company_include_charges_are_identical_gb`
    proves for GB's `charges` — written here instead of there, per the
    orchestrator, so every T38 test lives in one file: REST `?include=financials`
    and MCP `include=["financials"]` attach the identical `financials` block,
    co-requested with `filings` so D-043(h)'s shared-provenance guarantee is
    exercised too."""
    monkeypatch.setenv("REGISTRY_MCP_CACHE_DISABLED", "1")
    respx.get(f"{BASE_URL}/enheter/923609016").mock(return_value=httpx.Response(200, json=EQUINOR))
    respx.get(ACCOUNTS_URL.format(orgnr="923609016")).mock(
        return_value=httpx.Response(200, json=EQUINOR_ACCOUNTS)
    )

    with TestClient(app) as rest_client:
        rest_body = rest_client.get(
            "/v1/NO/company/923609016",
            params={"include": ["filings", "financials"]},
            headers={"X-Forwarded-For": "203.0.113.201"},
        ).json()

    async def _mcp_call() -> dict[str, Any]:
        async with FastMCPClient(mcp) as mcp_client:
            result = await mcp_client.call_tool(
                "lookup_company",
                {"id": "923609016", "country": "NO", "include": ["filings", "financials"]},
            )
            assert result.structured_content is not None
            data: dict[str, Any] = result.structured_content
            return data

    mcp_body = anyio.run(_mcp_call)

    assert rest_body["financials"] is not None
    assert rest_body["financials"]["periods"][0]["currency"] == "USD"

    # Each block's `provenance.fetched_at` is a live timestamp captured
    # independently by REST's call and MCP's call — allowed to differ by
    # microseconds, exactly like the report's own `fetched_at` — so strip
    # both before the byte-equal comparison D-004 otherwise requires.
    rest_body["filings"]["provenance"].pop("fetched_at")
    mcp_body["filings"]["provenance"].pop("fetched_at")
    rest_body["financials"]["provenance"].pop("fetched_at")
    mcp_body["financials"]["provenance"].pop("fetched_at")

    volatile = {"fetched_at"}
    assert {k: v for k, v in rest_body.items() if k not in volatile} == {
        k: v for k, v in mcp_body.items() if k not in volatile
    }


@respx.mock
async def test_d043_invariant9_failing_financials_fetch_leaves_block_absent_with_named_note() -> None:
    respx.get(f"{BASE_URL}/enheter/916823525").mock(
        return_value=httpx.Response(200, json={**EQUINOR, "organisasjonsnummer": "916823525"})
    )
    respx.get(ACCOUNTS_URL.format(orgnr="916823525")).mock(
        side_effect=[httpx.Response(500), httpx.Response(500)]
    )
    registry = get_registry("NO")
    report = await registry.lookup_with("916823525", ["financials"])
    assert report.financials is None
    assert any("'financials' attachment" in note for note in report.notes)


async def test_d043_lookup_with_routes_financials_to_the_financials_field_not_filings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression `tests/test_attachments.py::
    test_lookup_with_routes_each_block_to_the_field_of_the_same_name` exists
    to catch, extended here for Norway's new `financials` rather than there
    (that test is hand-parametrized, and T42 owns that file this round): a
    method named `financials` that filled `filings` would pass every other
    test in this module."""
    registry = get_registry("NO")
    sentinel = object()

    async def _fake_base_lookup(_id: str) -> CompanyReport:
        return CompanyReport(
            country="NO",
            registry=registry.registry,
            id="923609016",
            name="X",
            status=CompanyStatus.ACTIVE,
            is_active=True,
        )

    async def _fake_financials(_id: str) -> Any:
        return sentinel

    monkeypatch.setattr(type(registry), "lookup", staticmethod(_fake_base_lookup))
    monkeypatch.setattr(type(registry), "financials", staticmethod(_fake_financials))

    report = await registry.lookup_with("923609016", ["financials"])
    assert report.financials is sentinel
    assert report.filings is None
