"""Tests for `registries/gb/client.py` and `registries/gb/mapping.py`.

Numbered tests 73-105 of `UK_SPEC.md` §14 ("E. Mapping" / "F. Client"),
implemented here, named `test_NN_<slug>` to match `tests/test_rules_gb.py`'s
convention. 106-109 ("G. Live done-check") are `@pytest.mark.live` and
excluded from CI (`pytest -m "not live"`).
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import httpx
import pydantic
import pytest
import respx

from registry_mcp.core import cache
from registry_mcp.core.models import (
    Charge,
    ChargeBlock,
    CompanyStatus,
    ErrorCode,
    RegistryError,
    SourceRef,
)
from registry_mcp.core.registry import get_registry
from registry_mcp.registries.gb import CompaniesHouseRegistry, mapping
from registry_mcp.registries.gb import charges as charges_module
from registry_mcp.registries.gb import client as client_module
from registry_mcp.registries.gb import filing_history as filing_history_module
from registry_mcp.registries.gb import rules as gb_rules
from registry_mcp.registries.se import filings as se_filings_module

FIXTURES = Path(__file__).parent / "fixtures"
BASE_URL = client_module.BASE_URL


def _load(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return result


TESCO = _load("ch_00445790.json")
MONZO = _load("ch_09446231.json")
DELOITTE = _load("ch_OC303675.json")
NATWEST = _load("ch_SC090312.json")
DISSOLVED = _load("ch_00000006.json")
LIQUIDATION = _load("ch_04374209.json")
BR_ESTABLISHMENT = _load("ch_BR026263.json")
OVERSEAS = _load("ch_FC032315.json")
CIO_STUB = _load("ch_CE020555.json")
RS_STUB = _load("ch_RS007790.json")
AMICUS = _load("ch_13948759.json")
CIC = _load("ch_13507518.json")
SEARCH_TESCO = _load("ch_search_tesco.json")
SEARCH_EMPTY = _load("ch_search_empty.json")
BODY_404 = _load("ch_404.json")
BODY_401 = _load("ch_401.json")

# Charges — R-5c / T37, Part B, built behind the seam (`DECISIONS.md` D-042).
# All four recorded live 2026-09-08; see `registries/gb/charges.py`'s module
# docstring for the fetch dates, URLs and the full recon trail.
TESCO_CHARGES = _load("ch_00445790_charges.json")  # 9 charges: 2 outstanding, 7 fully-satisfied
MGM_CHARGES = _load("ch_00000006_charges.json")  # 1 charge, outstanding, no charge_code
DELOITTE_CHARGES = _load("ch_OC303675_charges.json")  # HTTP 200, empty: items: [], total_count: 0
NATWEST_CHARGES = _load("ch_SC090312_charges.json")  # 137 total, 100 returned (items_per_page=100)


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Deliberately does NOT `delenv("REGISTRY_MCP_CACHE_DISABLED")` — B1 (T15e
    # review): a test must be free to choose the cold path (cache disabled)
    # to prove `deadlines()` is correct there too, not just when warm.
    monkeypatch.setenv("REGISTRY_MCP_CACHE_PATH", str(tmp_path / "cache.sqlite3"))
    monkeypatch.delenv("REGISTRY_MCP_CACHE_TTL_SECONDS", raising=False)
    yield


@pytest.fixture(autouse=True)
def _api_key(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Live tests (`-m live`) need the real COMPANIES_HOUSE_API_KEY from the
    # caller's environment; only the mocked (`not live`) tests get the fake
    # key that `test_104_api_key_never_leaks` asserts never appears anywhere.
    if request.node.get_closest_marker("live") is None:
        monkeypatch.setenv("COMPANIES_HOUSE_API_KEY", "test-key-should-never-leak")
    yield


@pytest.fixture(autouse=True)
async def _reset_http_client() -> AsyncIterator[None]:
    client_module._client = None
    yield
    await client_module.aclose()


# ---------------------------------------------------------------------------
# E. Mapping — pure, no network (73-93)
# ---------------------------------------------------------------------------


def test_73_core_fields() -> None:
    report = mapping.map_entity(TESCO)
    assert report.name == "TESCO PLC"
    assert report.legal_form_code == "plc"
    assert report.status is CompanyStatus.ACTIVE
    assert report.id == "00445790"
    assert report.id_formatted is None
    # T15c product ruling (post-T15e): the register is already in English,
    # so `legal_form_local` is always `None`, never a copy of `legal_form`.
    assert report.legal_form_local is None


def test_74_previous_names_newest_first() -> None:
    report = mapping.map_entity(TESCO)
    assert report.previous_names == [
        "TESCO STORES (HOLDINGS) PUBLIC LIMITED COMPANY",
        "TESCO STORES (HOLDINGS) LIMITED",
    ]


def test_75_industry_codes() -> None:
    report = mapping.map_entity(TESCO)
    assert len(report.industry_codes) == 1
    code = report.industry_codes[0]
    assert code.code == "47110"
    assert code.description is None
    assert code.scheme == "SIC 2007"
    assert code.rank == 1


def test_76_dates_and_last_accounts_year() -> None:
    report = mapping.map_entity(TESCO)
    assert report.registered_at == date(1947, 11, 27)
    assert report.founded_at == date(1947, 11, 27)
    assert report.business_register_registered_at is None
    assert report.last_annual_accounts_year == 2026


def test_77_business_address() -> None:
    report = mapping.map_entity(TESCO)
    assert report.business_address is not None
    assert report.business_address.city == "Welwyn Garden City"
    assert report.business_address.postal_code == "AL7 1GA"
    assert report.business_address.country_name == "United Kingdom"
    assert report.business_address.country_code == "GB"


def test_78_registers_omits_charges_because_the_boolean_is_wrong() -> None:
    """§1.6 №1, rewritten 2026-09-08 after the live recording falsified its premise.

    This test used to assert `registers["charges"] is False` for TESCO and called
    itself the most important mapping test in the file. It was defending a wrong
    answer: the profile says `has_charges: false` while `/company/00445790/charges`
    returns nine charges, two still outstanding. A key in `registers` asserts
    membership; we can assert neither, so the key is absent — never `False`.
    `include=["charges"]` is the authoritative answer.
    """
    assert "charges" in TESCO["links"]
    assert TESCO["has_charges"] is False
    report = mapping.map_entity(TESCO)
    assert "charges" not in report.registers
    assert report.registers["insolvency"] is False


def test_79_unpublished_fields_are_honestly_none_and_no_notes() -> None:
    report = mapping.map_entity(TESCO)
    assert report.employees is None
    assert report.employees_reported is False
    assert report.vat_registered is None
    assert report.vat_number is None
    assert report.share_capital is None
    assert report.website is None
    assert report.email is None
    assert report.phone is None
    assert report.purpose is None
    assert report.sector is None
    assert report.notes == []
    # `published_deadlines` (D-018) IS published for TESCO — the register's
    # own dates, carried verbatim, for `rules.deadlines_for` to prefer.
    published = {pd.kind: pd for pd in report.published_deadlines}
    assert published["annual_accounts"].due_date == date(2027, 8, 26)
    assert published["confirmation_statement"].due_date == date(2027, 7, 2)


def test_euid_and_advertising_protected_are_null_for_the_uk() -> None:
    """R-2 (D-026(a),(b)): both keys are always present in the serialised
    document and `null` for the United Kingdom, which publishes neither a
    EUID nor an advertising-protection flag (D-004: always present, never
    omitted)."""
    report = mapping.map_entity(TESCO)
    dumped = report.model_dump(mode="json")
    assert dumped["euid"] is None
    assert dumped["advertising_protected"] is None


def test_80_natwest_no_locality_no_country_code_but_jurisdiction_note() -> None:
    report = mapping.map_entity(NATWEST)
    assert report.business_address is not None
    assert report.business_address.city is None
    assert report.business_address.country_code is None
    assert any("scotland" in n.lower() for n in report.notes)


def test_81_monzo_ltd_two_industry_codes_no_notes() -> None:
    report = mapping.map_entity(MONZO)
    assert report.legal_form_code == "ltd"
    assert report.has_annual_accounts_duty is True
    assert [c.rank for c in report.industry_codes] == [1, 2]
    assert [c.code for c in report.industry_codes] == ["64191", "64999"]
    assert report.notes == []


def test_82_deloitte_llp() -> None:
    report = mapping.map_entity(DELOITTE)
    assert report.legal_form_code == "llp"
    assert report.limited_liability is True
    assert report.has_board_duty is None


def test_83_dissolved_company() -> None:
    report = mapping.map_entity(DISSOLVED)
    assert report.status is CompanyStatus.DISSOLVED
    assert report.deregistered_at == date(2018, 7, 10)
    assert report.is_active is False
    assert report.legal_form_code == "private-unlimited-nsc"
    assert report.limited_liability is False
    assert "charges" not in report.registers  # omitted since 2026-09-08: see test 78
    # DISSOLVED carries neither `accounts.next_accounts` nor
    # `confirmation_statement` at all — `published_deadlines` (D-018) is `[]`
    # for a nothing-published case, not merely for the (separate) reason
    # that DISSOLVED status suppresses `deadlines_for`'s own output.
    assert report.published_deadlines == []


def test_84_liquidation_with_insolvency_history_never_bankrupt() -> None:
    # UNDER_LIQUIDATION is itself never BANKRUPT — GB never emits that status
    # (`UK_SPEC.md` §8 point 2).
    report = mapping.map_entity(LIQUIDATION)
    assert report.status is CompanyStatus.UNDER_LIQUIDATION
    assert report.registers["insolvency"] is True


def test_85_uk_establishment_branch() -> None:
    report = mapping.map_entity(BR_ESTABLISHMENT)
    assert report.status is CompanyStatus.ACTIVE
    assert report.is_subunit is True
    assert report.parent_id == "FC041146"
    assert report.activity == "Real Estate Consulting"
    assert report.founded_at is None
    assert any("parent_id" in n for n in report.notes)


def test_86_oversea_company_does_not_raise_on_null_string_type() -> None:
    assert OVERSEAS["accounts"]["last_accounts"]["type"] == "null"
    report = mapping.map_entity(OVERSEAS)
    assert report.legal_form_code == "oversea-company"
    assert report.founded_at is None


def test_87_cio_stub_constructs_without_raising() -> None:
    report = mapping.map_entity(CIO_STUB)
    assert report.status is CompanyStatus.UNKNOWN
    assert report.is_active is False
    assert report.registered_at is None
    assert report.business_address is None
    assert any("minimal record" in n for n in report.notes)
    assert any("1187753" in n for n in report.notes)


def test_88_registered_society_stub_partial_data_note() -> None:
    report = mapping.map_entity(RS_STUB)
    assert any("financial-conduct-authority" in n.lower() for n in report.notes)


def test_89_cic_subtype_not_ltd() -> None:
    report = mapping.map_entity(CIC)
    assert report.legal_form_code == "private-limited-guarant-nsc"
    assert "community interest company" in (report.legal_form or "")
    assert any("CIC34" in n for n in report.notes)


def test_90_search_tesco_envelope() -> None:
    result = mapping.map_search_result(SEARCH_TESCO, query="tesco")
    assert result.total == 356
    assert result.truncated is True
    assert len(result.hits) == 3
    assert result.hits[0].id == "00445790"
    assert result.hits[0].city == "Welwyn Garden City"
    assert result.hint is not None and "lookup_company" in result.hint
    # D-020: `SearchResult.hits` is always confidence-descending — enforced
    # by a `core/models.py` validator, but pinned here too since it is the
    # exact bug T15c's real output found (0.8, 0.4, 0.8 out of order).
    confidences = [hit.confidence for hit in result.hits]
    assert confidences == sorted(confidences, reverse=True)


def test_91_search_empty() -> None:
    result = mapping.map_search_result(SEARCH_EMPTY, query="zzzzzznotacompany")
    assert result.hits == []
    assert result.total == 0
    assert result.hint is not None and "sole trader" in result.hint.lower()


def test_92_search_item_missing_company_status_is_unknown() -> None:
    item = dict(SEARCH_TESCO["items"][0])
    del item["company_status"]
    hit = mapping.map_search_hit(item, query="tesco")
    assert hit.status is CompanyStatus.UNKNOWN


def test_93_search_confidence_anchors() -> None:
    hit = mapping.map_search_hit(SEARCH_TESCO["items"][0], query="tesco")
    assert hit.confidence == 0.8
    exact = mapping.map_search_hit(SEARCH_TESCO["items"][0], query="Tesco PLC")
    assert exact.confidence == 0.95


# ---------------------------------------------------------------------------
# F. Client — respx-mocked, no network (94-105)
# ---------------------------------------------------------------------------


async def test_94_no_key_raises_without_http_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY", raising=False)
    with respx.mock:
        route = respx.get(f"{BASE_URL}/company/00445790").mock(
            return_value=httpx.Response(200, json=TESCO)
        )
        with pytest.raises(RegistryError) as excinfo:
            await client_module.lookup("00445790")
        assert route.call_count == 0
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR
    assert "COMPANIES_HOUSE_API_KEY" in excinfo.value.hint
    assert "list_countries" in excinfo.value.hint


def test_95_import_succeeds_without_key_and_registers_gb(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY", raising=False)
    from registry_mcp.core.registry import list_countries

    assert "GB" in list_countries()


@respx.mock
async def test_96_authorization_header_is_key_as_username() -> None:
    route = respx.get(f"{BASE_URL}/company/00445790").mock(
        return_value=httpx.Response(200, json=TESCO)
    )
    await client_module.lookup("00445790")
    header = route.calls.last.request.headers["authorization"]
    assert header.startswith("Basic ")
    decoded = base64.b64decode(header.removeprefix("Basic ")).decode()
    assert decoded == "test-key-should-never-leak:"


@respx.mock
async def test_97_user_agent_contains_contact_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRY_MCP_CONTACT_EMAIL", "test-contact@example.com")
    route = respx.get(f"{BASE_URL}/company/00445790").mock(
        return_value=httpx.Response(200, json=TESCO)
    )
    await client_module.lookup("00445790")
    ua = route.calls.last.request.headers["user-agent"]
    assert "registry-mcp" in ua
    assert "test-contact@example.com" in ua


@respx.mock
async def test_98_401_and_403_raise_upstream_error_naming_env_var_not_retried() -> None:
    route = respx.get(f"{BASE_URL}/company/00445790").mock(
        return_value=httpx.Response(401, json=BODY_401)
    )
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("00445790")
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR
    assert "COMPANIES_HOUSE_API_KEY" in excinfo.value.hint
    assert route.call_count == 1

    route2 = respx.get(f"{BASE_URL}/company/00445791").mock(return_value=httpx.Response(403))
    with pytest.raises(RegistryError) as excinfo2:
        await client_module.lookup("00445791")
    assert excinfo2.value.code is ErrorCode.UPSTREAM_ERROR
    assert route2.call_count == 1


@respx.mock
async def test_99_404_hint_details_and_message_do_not_leak_upstream_body() -> None:
    route = respx.get(f"{BASE_URL}/company/99999999").mock(
        return_value=httpx.Response(404, json=BODY_404)
    )
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("99999999")
    err = excinfo.value
    assert err.code is ErrorCode.NOT_FOUND
    assert "search_company" in err.hint
    assert "sole trader" in err.hint.lower()
    # Product ruling (post-T15e): `details` never forwards an upstream debug
    # field (Companies House's own `request_id`) into the D-007 envelope —
    # `details` is minimal and ours, not a pass-through for upstream bodies.
    assert err.details == {}
    assert BODY_404["request_id"] not in json.dumps(err.to_dict())
    assert BODY_404["message"] not in err.message
    assert route.call_count == 1


@respx.mock
async def test_100_rate_limited_hints() -> None:
    route = respx.get(f"{BASE_URL}/company/00445790").mock(
        return_value=httpx.Response(429, headers={"retry-after": "300"})
    )
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("00445790")
    assert excinfo.value.code is ErrorCode.RATE_LIMITED
    assert "300" in excinfo.value.hint
    assert route.call_count == 1

    respx.get(f"{BASE_URL}/company/00445791").mock(
        return_value=httpx.Response(429, headers={"x-ratelimit-reset": "1788538297"})
    )
    with pytest.raises(RegistryError) as excinfo2:
        await client_module.lookup("00445791")
    assert excinfo2.value.code is ErrorCode.RATE_LIMITED
    assert excinfo2.value.hint

    respx.get(f"{BASE_URL}/company/00445792").mock(return_value=httpx.Response(429))
    with pytest.raises(RegistryError) as excinfo3:
        await client_module.lookup("00445792")
    assert excinfo3.value.code is ErrorCode.RATE_LIMITED
    assert excinfo3.value.hint


@respx.mock
async def test_101_500_then_200_retried_exactly_once() -> None:
    route = respx.get(f"{BASE_URL}/company/00445790").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json=TESCO)]
    )
    report = await client_module.lookup("00445790")
    assert report.name == "TESCO PLC"
    assert route.call_count == 2


@respx.mock
async def test_101b_two_500s_raises_upstream_error_exactly_twice() -> None:
    route = respx.get(f"{BASE_URL}/company/00445790").mock(
        side_effect=[httpx.Response(500), httpx.Response(500)]
    )
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("00445790")
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR
    assert route.call_count == 2


@respx.mock
async def test_102_cache_hit_same_fetched_at_no_second_request() -> None:
    route = respx.get(f"{BASE_URL}/company/00445790").mock(
        return_value=httpx.Response(200, json=TESCO)
    )
    first = await client_module.lookup("00445790")
    assert first.cached is False
    second = await client_module.lookup("00445790")
    assert second.cached is True
    assert second.fetched_at == first.fetched_at
    assert route.call_count == 1


async def test_103_search_validation() -> None:
    with pytest.raises(RegistryError) as excinfo:
        await client_module.search("tesco", limit=0)
    assert excinfo.value.code is ErrorCode.BAD_REQUEST

    with pytest.raises(RegistryError) as excinfo2:
        await client_module.search("tesco", limit=101)
    assert excinfo2.value.code is ErrorCode.BAD_REQUEST

    with pytest.raises(RegistryError) as excinfo3:
        await client_module.search("  ", limit=10)
    assert excinfo3.value.code is ErrorCode.BAD_REQUEST

    with respx.mock:
        respx.get(f"{BASE_URL}/search/companies").mock(
            return_value=httpx.Response(200, json=SEARCH_TESCO)
        )
        result = await client_module.search("tesco", limit=100)
        assert result.total == 356


@respx.mock
async def test_104_api_key_never_leaks(caplog: pytest.LogCaptureFixture) -> None:
    secret = "test-key-should-never-leak"
    respx.get(f"{BASE_URL}/company/00445790").mock(return_value=httpx.Response(401, json=BODY_401))
    with caplog.at_level(logging.DEBUG), pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("00445790")
    assert secret not in json.dumps(excinfo.value.to_dict())
    assert secret not in str(excinfo.value)
    for record in caplog.records:
        assert secret not in record.getMessage()

    respx.get(f"{BASE_URL}/company/00445791").mock(side_effect=httpx.TimeoutException("timed out"))
    with caplog.at_level(logging.DEBUG), pytest.raises(RegistryError) as excinfo2:
        await client_module.lookup("00445791")
    assert secret not in json.dumps(excinfo2.value.to_dict())
    for record in caplog.records:
        assert secret not in record.getMessage()


@respx.mock
async def test_105_token_bucket_does_not_serialise_concurrent_lookups() -> None:
    """The rate-limit bucket must not turn concurrent lookups into a queue.

    Asserted by observing overlap rather than by timing the wall clock. The
    previous version bounded a mocked round trip at 0.5 s, which is a property
    of the CI runner's load, not of the bucket: it failed on GitHub Actions at
    1.17 s on 2026-09-07 (run 34120021824) with nothing in the module changed.
    Here each mocked response holds the connection open while it counts how many
    requests are in flight; if the bucket serialised, the peak would be 1.
    """
    import asyncio

    in_flight = 0
    peak_in_flight = 0

    async def _counting_response(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak_in_flight
        in_flight += 1
        peak_in_flight = max(peak_in_flight, in_flight)
        try:
            await asyncio.sleep(0.05)
        finally:
            in_flight -= 1
        body = TESCO if "00445790" in str(request.url) else MONZO
        return httpx.Response(200, json=body)

    respx.get(f"{BASE_URL}/company/00445790").mock(side_effect=_counting_response)
    respx.get(f"{BASE_URL}/company/09446231").mock(side_effect=_counting_response)

    results = await asyncio.gather(
        client_module.lookup("00445790"),
        client_module.lookup("09446231"),
    )
    assert peak_in_flight == 2, "the bucket serialised two concurrent lookups"
    assert {r.id for r in results} == {"00445790", "09446231"}


# ---------------------------------------------------------------------------
# aclose / format_id / validate wiring through the Registry
# ---------------------------------------------------------------------------


@respx.mock
async def test_registry_aclose_closes_underlying_http_client() -> None:
    respx.get(f"{BASE_URL}/company/00445790").mock(return_value=httpx.Response(200, json=TESCO))
    registry = get_registry("GB")

    await registry.lookup("00445790")
    http_client = client_module._client
    assert http_client is not None
    assert http_client.is_closed is False

    await registry.aclose()
    assert http_client.is_closed is True


def test_format_id_is_none() -> None:
    registry = get_registry("GB")
    assert registry.format_id("00445790") is None


def test_validate_invalid_returns_valid_false_with_hint() -> None:
    registry = get_registry("GB")
    result = registry.validate("not a company number!")
    assert result.valid is False
    assert result.hint
    assert result.normalized is None
    assert result.formatted is None


def test_validate_valid_returns_no_formatting() -> None:
    registry = get_registry("GB")
    result = registry.validate("445790")
    assert result.valid is True
    assert result.normalized == "00445790"
    assert result.formatted is None


@respx.mock
async def test_deadline_report_via_registry_uses_published_dates() -> None:
    """End-to-end: `lookup()` fills `report.published_deadlines` (D-018) from
    the raw payload, and `Registry.deadline_report` -> `deadlines()` reads it
    straight off `report` — no cache, no second HTTP call, no I/O of any
    kind inside `deadlines()` itself."""
    respx.get(f"{BASE_URL}/company/00445790").mock(return_value=httpx.Response(200, json=TESCO))
    registry = get_registry("GB")

    report = await registry.lookup("00445790")
    result = registry.deadline_report(report, date(2026, 9, 4))
    kinds = {d.kind for d in result.deadlines}
    assert kinds == {"annual_accounts", "confirmation_statement"}
    accounts = next(d for d in result.deadlines if d.kind == "annual_accounts")
    assert accounts.due_date == date(2027, 8, 26)


@respx.mock
async def test_b1_deadline_report_survives_cache_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """B1 (T15e review, BLOCKING) — the regression the review's verifier
    caught: with the cache disabled end to end, an active TESCO PLC must
    still yield both deadlines, not `[]` with no note to explain it.
    `Registry.deadlines(report, today)` must not depend on cache state for
    correctness, because it must not depend on the cache *at all*."""
    monkeypatch.setenv("REGISTRY_MCP_CACHE_DISABLED", "1")
    respx.get(f"{BASE_URL}/company/00445790").mock(return_value=httpx.Response(200, json=TESCO))
    registry = get_registry("GB")

    report = await registry.lookup("00445790")
    assert report.cached is False
    result = registry.deadline_report(report, date(2026, 9, 4))
    kinds = {d.kind for d in result.deadlines}
    assert kinds == {"annual_accounts", "confirmation_statement"}


def test_b1_deadlines_for_is_pure_without_any_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """The narrowest form of B1: `rules.deadlines_for` and
    `CompaniesHouseRegistry.deadlines()` never touch `core.cache` at all —
    build a report directly from a fixture (no `lookup()`, no cache entry
    anywhere) and confirm both still produce the same two deadlines."""
    from registry_mcp.registries.gb import rules

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("deadlines_for must never touch the cache")

    monkeypatch.setattr("registry_mcp.core.cache.get", _boom)
    monkeypatch.setattr("registry_mcp.core.cache.set", _boom)

    report = mapping.map_entity(TESCO)
    registry = get_registry("GB")
    via_registry = registry.deadlines(report, date(2026, 9, 4))
    via_rules = rules.deadlines_for(report, date(2026, 9, 4))
    assert {d.kind for d in via_registry} == {"annual_accounts", "confirmation_statement"}
    assert via_registry == via_rules


# ---------------------------------------------------------------------------
# G. Live done-check (network; excluded from CI, `-m "not live"`)
# ---------------------------------------------------------------------------

#: Top-level Companies House profile fields `map_entity` reads unconditionally.
_MANDATORY_TOP_LEVEL_FIELDS = {
    "company_number",
    "company_name",
    "type",
}

#: Top-level fields `map_entity` reads, but which a given profile may omit
#: entirely (`UK_SPEC.md` §2, §2.2).
_OPTIONAL_TOP_LEVEL_FIELDS = {
    "company_status",
    "company_status_detail",
    "date_of_creation",
    "date_of_cessation",
    "subtype",
    "previous_company_names",
    "sic_codes",
    "registered_office_address",
    "service_address",
    "registered_office_is_in_dispute",
    "undeliverable_registered_office_address",
    "has_charges",
    "has_insolvency_history",
    "has_been_liquidated",
    "is_community_interest_company",
    "accounts",
    "confirmation_statement",
    "jurisdiction",
    "branch_company_details",
    "foreign_company_details",
    "external_registration_number",
    "partial_data_available",
    "corporate_annotation",
    "annual_return",
    "can_file",
    "etag",
    "links",
    "last_full_members_list_date",
    "has_super_secure_pscs",
}


@pytest.mark.live
async def test_106_live_lookup_cached_then_true() -> None:
    first = await client_module.lookup("00445790")
    assert first.cached is False
    second = await client_module.lookup("00445790")
    assert second.cached is True


@pytest.mark.live
async def test_107_live_fixture_fields_present_or_optional() -> None:
    report = await client_module.lookup("00445790")
    assert report.name == "TESCO PLC"
    # `raw_for` no longer exists (B1, T15e review) — fetch the raw payload
    # directly, the same way `client.lookup` itself does, purely to inspect
    # its shape (this test asserts nothing through the mapper here).
    async with httpx.AsyncClient(base_url=client_module.BASE_URL) as raw_client:
        response = await raw_client.get(
            "/company/00445790",
            auth=httpx.BasicAuth(client_module._read_api_key(), ""),
        )
    data = response.json()
    missing = _MANDATORY_TOP_LEVEL_FIELDS - data.keys()
    assert not missing, f"Live 00445790 payload is missing mandatory fields: {missing}"
    accounted_for = _MANDATORY_TOP_LEVEL_FIELDS | _OPTIONAL_TOP_LEVEL_FIELDS
    unaccounted = data.keys() - accounted_for
    assert not unaccounted, (
        f"Live 00445790 payload has top-level fields this test does not classify as "
        f"mandatory or optional: {unaccounted}"
    )


@pytest.mark.live
async def test_108_live_dissolved_company() -> None:
    report = await client_module.lookup("00000006")
    assert report.status is CompanyStatus.DISSOLVED


@pytest.mark.live
async def test_109_live_fixtures_still_match_stored_files() -> None:
    """Re-fetch every saved company fixture and diff the mapped report against
    the report mapped from the stored file, ignoring `fetched_at`/`cached`. A
    difference means the register changed, not that we broke — refresh the
    fixture, don't silently tolerate it."""
    numbers = [
        "00445790",
        "09446231",
        "OC303675",
        "SC090312",
        "00000006",
        "04374209",
        "BR026263",
        "FC032315",
        "CE020555",
        "RS007790",
        "13948759",
        "13507518",
    ]
    volatile = {"fetched_at", "cached"}
    for number in numbers:
        stored = mapping.map_entity(_load(f"ch_{number}.json"))
        live = await client_module.lookup(number)
        stored_dump = {k: v for k, v in stored.model_dump(mode="json").items() if k not in volatile}
        live_dump = {k: v for k, v in live.model_dump(mode="json").items() if k not in volatile}
        assert stored_dump == live_dump, f"{number} fixture is stale relative to the live register"


# ---------------------------------------------------------------------------
# G. Charges — R-5c / T37, Part B, built *behind the seam* (`DECISIONS.md`
# D-042; `registries/gb/charges.py`'s module docstring). Not wired to
# `include=[...]` — `core/registry.py` has no `lookup_with` and `Registry`
# has no `supported_includes` as of this writing (R-5 has not landed).
# `charges_module.map_charges` is pure/no-I/O (mirrors `mapping.py`);
# `client_module.fetch_charges` is the async seam (mirrors `lookup`/`search`).
# ---------------------------------------------------------------------------

_FETCHED_AT = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)


def test_charges_map_tesco_sorted_counts_and_status() -> None:
    """§8 recon: Tesco's own `has_charges` is `false` (`ch_00445790.json`)
    yet the live `/charges` call returns nine real charges — the boolean on
    the company profile cannot predict this endpoint at all."""
    block = charges_module.map_charges(
        TESCO_CHARGES, "00445790", cached=False, fetched_at=_FETCHED_AT
    )
    assert [c.charge_number for c in block.charges] == [9, 8, 7, 6, 5, 4, 3, 2, 1]
    assert block.total_count == 9
    assert block.satisfied_count == 7
    assert block.outstanding_count == 2  # total_count - satisfied_count
    assert block.notes == []  # total_count == len(charges): nothing truncated

    outstanding = block.charges[0]
    assert outstanding.status == "outstanding"
    assert outstanding.is_outstanding is True
    assert outstanding.classification == "Account security agreement"
    assert outstanding.satisfied_on is None
    assert outstanding.parties_entitled == [
        "Tesco Trustee Company of Ireland Limited as Trustee of the Tesco Ireland Limited "
        "Senior Executive Pension Scheme"
    ]
    assert outstanding.contains_floating_charge is None  # not present on this item, live

    satisfied = block.charges[2]  # charge_number 7
    assert satisfied.status == "fully-satisfied"
    assert satisfied.is_outstanding is False
    assert satisfied.satisfied_on == date(2009, 11, 25)
    assert satisfied.obligations_secured == (
        "All monies due or to become due from the company to the chargee under the terms of "
        "the aforementioned instrument creating or evidencing the charge"
    )


def test_charges_map_mgm_single_charge_no_charge_code() -> None:
    """§7 recon: roughly a quarter of live items carry no `charge_code`
    (pre-2013 filings) — `00000006`'s one charge is one of them."""
    block = charges_module.map_charges(
        MGM_CHARGES, "00000006", cached=False, fetched_at=_FETCHED_AT
    )
    assert len(block.charges) == 1
    charge = block.charges[0]
    assert charge.charge_number == 1
    assert charge.charge_id is None  # honestly absent, not guessed (D-009)
    assert charge.status == "outstanding"
    assert charge.is_outstanding is True
    assert charge.parties_entitled == ["Pacific Life Re Limited"]
    assert block.total_count == 1
    assert block.satisfied_count == 0
    assert block.outstanding_count == 1


def test_charges_map_deloitte_empty_block_present_not_error() -> None:
    """§8 recon, the load-bearing case: a company with no charges is a
    *present* block with `charges: []`, never an error and never absent —
    exactly D-041(h)'s principle (`/company/{n}` decides existence;
    `/charges` never does), confirmed live on Deloitte LLP."""
    block = charges_module.map_charges(
        DELOITTE_CHARGES, "OC303675", cached=False, fetched_at=_FETCHED_AT
    )
    assert block.charges == []
    assert block.total_count == 0
    assert block.satisfied_count == 0
    assert block.outstanding_count == 0
    assert block.notes == []
    assert block.provenance.source == "Companies House (UK)"
    assert block.provenance.cached is False


def test_charges_map_natwest_truncation_disclosed() -> None:
    """§2/§5 recon: 137 total, only 100 fit on one page at the register's own
    maximum — D-042(j)'s truncation-disclosure rule, exercised for real."""
    block = charges_module.map_charges(
        NATWEST_CHARGES, "SC090312", cached=False, fetched_at=_FETCHED_AT
    )
    assert block.total_count == 137
    assert len(block.charges) == 100
    assert block.satisfied_count == 27
    assert block.outstanding_count == 110
    assert len(block.notes) == 1
    assert "137" in block.notes[0]
    assert "100" in block.notes[0]
    assert "SC090312/charges" in block.notes[0]

    # newest-first, non-increasing throughout (created_on desc, then
    # charge_number desc as the tie-break) — not hand-verified item by item
    # across all 100, but monotonicity is exactly what the sort promises.
    keys = [(c.created_on or date.min, c.charge_number or 0) for c in block.charges]
    assert keys == sorted(keys, reverse=True)

    statuses = {c.status for c in block.charges}
    assert statuses == {"outstanding", "fully-satisfied"}  # no "part-satisfied" observed live


def test_charges_is_outstanding_never_guesses_unknown_status() -> None:
    """D-025(d) / D-011: a status word the table does not contain yields
    `None`, never a guessed `True`/`False`. `"part-satisfied"` specifically
    was never observed live in this recon (§9) and is deliberately absent
    from `_OUTSTANDING_BY_STATUS`."""
    payload = {
        "items": [{"charge_number": 1, "status": "part-satisfied"}],
        "total_count": 1,
        "satisfied_count": 0,
    }
    block = charges_module.map_charges(payload, "00000001", cached=False, fetched_at=_FETCHED_AT)
    assert block.charges[0].status == "part-satisfied"
    assert block.charges[0].is_outstanding is None

    payload_no_status = {"items": [{"charge_number": 2}], "total_count": 1, "satisfied_count": 0}
    block2 = charges_module.map_charges(
        payload_no_status, "00000001", cached=False, fetched_at=_FETCHED_AT
    )
    assert block2.charges[0].status is None
    assert block2.charges[0].is_outstanding is None


def test_charges_no_natural_person_among_recorded_parties_entitled() -> None:
    """§3/§9 recon finding, recorded two ways.

    A reliable *positive* "is this an institution" classifier does not exist
    as a keyword list — real institution names take too many shapes
    (`"Kfw"`, `"Natixis"`, `"Bnp Paribas"`, `"Ubs Ag"` carry no corporate
    suffix a keyword match would catch; an early version of this test using
    one produced 12 false positives on real banks and clearing houses in the
    `SC090312` fixture alone). A digit-based *negative* check fares no
    better in the other direction — `"Nevis Derivatives No 3 LLP"` is a real
    LLP name, not a person, and contains a digit. So this test does two
    narrower, genuinely reliable things instead of one fragile broad one:

    1. A *negative* check with essentially no false-positive risk: no
       recorded name carries a personal title — a signal that would be very
       unusual on an institution and costs nothing to check.
    2. An exact pin of the two small fixtures (Tesco, `00000006`) this task
       hand-verified name-by-name in `test_charges_map_tesco_sorted_counts_
       and_status` / `test_charges_map_mgm_single_charge_no_charge_code`.

    The full claim — that none of the 68 distinct names across all four
    recorded fixtures, including all 100 items of `SC090312`, reads as a
    natural person — was verified by hand while this module was written and
    is reported to the orchestrator in full; it is not re-derived here by a
    heuristic that cannot make that judgement reliably.
    """
    personal_titles = ("mr ", "mrs ", "miss ", "ms ", "mx ", "dr ", "sir ", "dame ")
    for fixture, number in (
        (TESCO_CHARGES, "00445790"),
        (MGM_CHARGES, "00000006"),
        (NATWEST_CHARGES, "SC090312"),
    ):
        block = charges_module.map_charges(fixture, number, cached=False, fetched_at=_FETCHED_AT)
        for charge in block.charges:
            for name in charge.parties_entitled:
                lowered = name.lower()
                assert not any(lowered.startswith(t) for t in personal_titles), (
                    f"{number}: {name!r} carries a personal title — review by hand."
                )

    tesco_block = charges_module.map_charges(
        TESCO_CHARGES, "00445790", cached=False, fetched_at=_FETCHED_AT
    )
    all_tesco_parties = {name for c in tesco_block.charges for name in c.parties_entitled}
    assert all_tesco_parties == {
        "Tesco Trustee Company of Ireland Limited as Trustee of the Tesco Ireland Limited "
        "Senior Executive Pension Scheme",
        "Tesco Ireland Pension Trustees Limited as Trustee of the Tesco Ireland Limited "
        "Pension Plan",
        "Tesco Ireland Pension Trustees Limited as Trustee of the Tesco Ireland Limited "
        "Executive Scheme",
        "Tesco Trustee Company of Ireland Limited as Trustee of the Tesco Ireland Limited "
        'Staff Scheme (The "Trustee")',
        "Rbs Aerospace Limited",
        "Deutsche International Finance (Ireland) Limited",
        "Deutsche Bank Ag",
        "Cobroad Investments",
    }
    mgm_block = charges_module.map_charges(
        MGM_CHARGES, "00000006", cached=False, fetched_at=_FETCHED_AT
    )
    assert {name for c in mgm_block.charges for name in c.parties_entitled} == {
        "Pacific Life Re Limited"
    }


def test_charges_provenance_and_extra_forbid() -> None:
    block = charges_module.map_charges(MGM_CHARGES, "00000006", cached=True, fetched_at=_FETCHED_AT)
    assert block.provenance.source == "Companies House (UK)"
    assert block.provenance.source_url == (
        "https://find-and-update.company-information.service.gov.uk/company/00000006/charges"
    )
    assert (
        block.provenance.license
        == "Crown copyright — Companies House public register, free to re-use"
    )
    assert block.provenance.fetched_at == _FETCHED_AT
    assert block.provenance.cached is True

    with pytest.raises(pydantic.ValidationError):  # extra="forbid" (D-004)
        charges_module.Charge(charge_number=1, not_a_real_field=True)  # type: ignore[call-arg]


# --- client_module.fetch_charges — respx-mocked, no network ---------------


@respx.mock
async def test_fetch_charges_requests_one_page_at_register_maximum() -> None:
    route = respx.get(f"{BASE_URL}/company/00445790/charges").mock(
        return_value=httpx.Response(200, json=TESCO_CHARGES)
    )
    result = await client_module.fetch_charges("00445790")
    assert route.call_count == 1
    requested = route.calls.last.request.url.params
    assert requested["items_per_page"] == "100"
    assert len(result.charges) == 9


@respx.mock
async def test_fetch_charges_404_is_present_empty_block_not_error() -> None:
    """The single most important recon question (§8): confirmed live that
    Companies House does not actually 404 this endpoint — not even for a
    nonexistent company number — but the client still treats one as a
    present empty block, defensively, never as `not_found`."""
    respx.get(f"{BASE_URL}/company/00445790/charges").mock(return_value=httpx.Response(404))
    result = await client_module.fetch_charges("00445790")
    assert result.charges == []
    assert result.provenance.cached is False


@respx.mock
async def test_fetch_charges_empty_result_is_never_not_found_on_a_cache_hit() -> None:
    """Empty results are cached under the existing `status="not_found"` label
    purely to borrow its 1 h TTL (D-042(j)) — never surfaced as an error on
    read. This is the mechanism itself, not just the outward behaviour."""
    respx.get(f"{BASE_URL}/company/00445790/charges").mock(
        return_value=httpx.Response(200, json=DELOITTE_CHARGES)
    )
    first = await client_module.fetch_charges("00445790")
    assert first.charges == []

    entry = cache.get(client_module._charges_cache_key("00445790"))
    assert entry is not None
    assert entry.status == "not_found"  # the TTL label, not an error signal

    second = await client_module.fetch_charges("00445790")
    assert second.charges == []
    assert second.provenance.cached is True
    assert second.provenance.fetched_at == first.provenance.fetched_at


@respx.mock
async def test_fetch_charges_non_empty_result_cached_as_ok() -> None:
    respx.get(f"{BASE_URL}/company/00445790/charges").mock(
        return_value=httpx.Response(200, json=TESCO_CHARGES)
    )
    await client_module.fetch_charges("00445790")
    entry = cache.get(client_module._charges_cache_key("00445790"))
    assert entry is not None
    assert entry.status == "ok"


@respx.mock
async def test_fetch_charges_cache_hit_same_fetched_at_no_second_request() -> None:
    route = respx.get(f"{BASE_URL}/company/00445790/charges").mock(
        return_value=httpx.Response(200, json=TESCO_CHARGES)
    )
    first = await client_module.fetch_charges("00445790")
    assert first.provenance.cached is False
    second = await client_module.fetch_charges("00445790")
    assert second.provenance.cached is True
    assert second.provenance.fetched_at == first.provenance.fetched_at
    assert route.call_count == 1


@respx.mock
async def test_fetch_charges_401_403_429_error_codes() -> None:
    respx.get(f"{BASE_URL}/company/00445790/charges").mock(return_value=httpx.Response(401))
    with pytest.raises(RegistryError) as excinfo:
        await client_module.fetch_charges("00445790")
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR

    respx.get(f"{BASE_URL}/company/00445791/charges").mock(return_value=httpx.Response(403))
    with pytest.raises(RegistryError) as excinfo2:
        await client_module.fetch_charges("00445791")
    assert excinfo2.value.code is ErrorCode.UPSTREAM_ERROR

    respx.get(f"{BASE_URL}/company/00445792/charges").mock(
        return_value=httpx.Response(429, headers={"retry-after": "60"})
    )
    with pytest.raises(RegistryError) as excinfo3:
        await client_module.fetch_charges("00445792")
    assert excinfo3.value.code is ErrorCode.RATE_LIMITED


@respx.mock
async def test_fetch_charges_500_then_200_retried_exactly_once() -> None:
    route = respx.get(f"{BASE_URL}/company/00445790/charges").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json=TESCO_CHARGES)]
    )
    result = await client_module.fetch_charges("00445790")
    assert len(result.charges) == 9
    assert route.call_count == 2


async def test_fetch_charges_invalid_id_raises_without_http_request() -> None:
    with respx.mock:
        route = respx.get(f"{BASE_URL}/company/00445790/charges").mock(
            return_value=httpx.Response(200, json=TESCO_CHARGES)
        )
        with pytest.raises(RegistryError) as excinfo:
            await client_module.fetch_charges("not-a-crn-at-all-!!")
        assert excinfo.value.code is ErrorCode.INVALID_ID
        assert route.call_count == 0


async def test_fetch_charges_no_key_raises_without_http_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY", raising=False)
    with respx.mock:
        route = respx.get(f"{BASE_URL}/company/00445790/charges").mock(
            return_value=httpx.Response(200, json=TESCO_CHARGES)
        )
        with pytest.raises(RegistryError) as excinfo:
            await client_module.fetch_charges("00445790")
        assert route.call_count == 0
    assert excinfo.value.code is ErrorCode.UPSTREAM_ERROR


@respx.mock
async def test_fetch_charges_institution_names_never_reach_a_log_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D-028(1) / D-040: `parties_entitled` is the one place a natural
    person's name could appear, and it must never reach a log line. Checked
    against every name this recon actually recorded, at DEBUG level."""
    respx.get(f"{BASE_URL}/company/00445790/charges").mock(
        return_value=httpx.Response(200, json=TESCO_CHARGES)
    )
    with caplog.at_level(logging.DEBUG):
        result = await client_module.fetch_charges("00445790")
    names = [name for charge in result.charges for name in charge.parties_entitled]
    assert names  # sanity: the fixture actually has names to check
    for record in caplog.records:
        message = record.getMessage()
        for name in names:
            assert name not in message


# ---------------------------------------------------------------------------
# H. Wiring `charges` through `include=[...]` (joining R-5 and R-5c/T37 Part
# B's seam, `DECISIONS.md` D-042): `CompaniesHouseRegistry.charges()` copies
# `registries/gb/charges.py`'s local `ChargeList`/`ChargeProvenance` onto the
# real `core.models.ChargeBlock`/`SourceRef`, and `Registry.lookup_with`
# (R-5, `core/registry.py`) is what a caller actually uses.
# ---------------------------------------------------------------------------


@respx.mock
async def test_registry_charges_returns_real_core_models_chargeblock() -> None:
    """`CompaniesHouseRegistry.charges()` returns the wired
    `core.models.ChargeBlock`/`Charge`/`SourceRef` — not the local stand-ins
    `registries/gb/charges.py` defines for itself — with every field copied
    across, not just the count."""
    respx.get(f"{BASE_URL}/company/00445790/charges").mock(
        return_value=httpx.Response(200, json=TESCO_CHARGES)
    )
    # `charges()` is concrete on `CompaniesHouseRegistry`, not on the abstract
    # `Registry` `get_registry` is typed to return — the same dynamic-dispatch
    # relationship `Registry.lookup_with` relies on (`getattr(self, name)`).
    registry = cast(CompaniesHouseRegistry, get_registry("GB"))
    block = await registry.charges("00445790")

    assert isinstance(block, ChargeBlock)
    assert isinstance(block.provenance, SourceRef)
    assert all(isinstance(c, Charge) for c in block.charges)
    assert [c.charge_number for c in block.charges] == [9, 8, 7, 6, 5, 4, 3, 2, 1]
    assert block.total_count == 9
    assert block.outstanding_count == 2
    assert block.satisfied_count == 7

    outstanding = block.charges[0]
    assert outstanding.status == "outstanding"
    assert outstanding.is_outstanding is True
    assert outstanding.parties_entitled == [
        "Tesco Trustee Company of Ireland Limited as Trustee of the Tesco Ireland Limited "
        "Senior Executive Pension Scheme"
    ]
    assert block.provenance.source == "Companies House (UK)"
    assert block.provenance.source_url == (
        "https://find-and-update.company-information.service.gov.uk/company/00445790/charges"
    )
    assert (
        block.provenance.license
        == "Crown copyright — Companies House public register, free to re-use"
    )
    assert block.provenance.cached is False


def test_gb_supported_includes_is_charges_only() -> None:
    registry = get_registry("GB")
    assert registry.supported_includes == frozenset({"charges"})


@respx.mock
async def test_lookup_with_charges_round_trip_tesco_has_own_source_ref() -> None:
    """The adversarial round trip: `lookup_with("00445790", ["charges"])`
    returns a report whose `charges` block holds all nine charges, with its
    own `SourceRef` distinct from the report's own provenance (D-041(c))."""
    respx.get(f"{BASE_URL}/company/00445790").mock(return_value=httpx.Response(200, json=TESCO))
    respx.get(f"{BASE_URL}/company/00445790/charges").mock(
        return_value=httpx.Response(200, json=TESCO_CHARGES)
    )
    registry = get_registry("GB")

    report = await registry.lookup_with("00445790", ["charges"])
    assert report.name == "TESCO PLC"
    assert report.charges is not None
    assert len(report.charges.charges) == 9
    assert report.charges.provenance.fetched_at != report.fetched_at
    assert report.charges.provenance.source == "Companies House (UK)"


@respx.mock
async def test_lookup_with_no_include_leaves_charges_absent() -> None:
    """Nullability level one: not requested at all -> `None`, not an empty block."""
    respx.get(f"{BASE_URL}/company/00445790").mock(return_value=httpx.Response(200, json=TESCO))
    registry = get_registry("GB")

    report = await registry.lookup_with("00445790")
    assert report.charges is None
    report_empty_list = await registry.lookup_with("00445790", [])
    assert report_empty_list.charges is None


@respx.mock
async def test_lookup_with_charges_present_empty_block_for_company_with_none() -> None:
    """Nullability level two, the load-bearing case (D-011, D-042(d)): a
    company Companies House confirms has no charges gets a *present* block
    with `charges: []` — never absent, never `not_found`."""
    respx.get(f"{BASE_URL}/company/OC303675").mock(return_value=httpx.Response(200, json=DELOITTE))
    respx.get(f"{BASE_URL}/company/OC303675/charges").mock(
        return_value=httpx.Response(200, json=DELOITTE_CHARGES)
    )
    registry = get_registry("GB")

    report = await registry.lookup_with("OC303675", ["charges"])
    assert report.charges is not None
    assert report.charges.charges == []
    assert report.charges.total_count == 0


@respx.mock
async def test_lookup_with_unknown_include_is_bad_request_naming_gb_allowed_set() -> None:
    respx.get(f"{BASE_URL}/company/00445790").mock(return_value=httpx.Response(200, json=TESCO))
    registry = get_registry("GB")

    with pytest.raises(RegistryError) as excinfo:
        await registry.lookup_with("00445790", ["officers"])
    assert excinfo.value.code is ErrorCode.BAD_REQUEST
    assert "charges" in excinfo.value.hint
    assert excinfo.value.details == {"allowed": ["charges"], "unknown": ["officers"]}


@respx.mock
async def test_lookup_with_failing_charges_fetch_leaves_lookup_intact_with_a_note() -> None:
    """A failed attachment never fails the lookup (D-041(c), D-042(b),(j)):
    the base report still comes back complete, `charges` is left absent, and
    `notes` gains one sentence naming the failed attachment."""
    respx.get(f"{BASE_URL}/company/00445790").mock(return_value=httpx.Response(200, json=TESCO))
    respx.get(f"{BASE_URL}/company/00445790/charges").mock(return_value=httpx.Response(401))
    registry = get_registry("GB")

    report = await registry.lookup_with("00445790", ["charges"])
    assert report.name == "TESCO PLC"
    assert report.charges is None
    assert any("charges" in note for note in report.notes)


def test_se_and_no_still_declare_no_includes() -> None:
    assert get_registry("SE").supported_includes == frozenset()
    assert get_registry("NO").supported_includes == frozenset()


# --- Live done-check --------------------------------------------------------


@pytest.mark.live
async def test_live_charges_no_charges_company_is_present_empty_block() -> None:
    result = await client_module.fetch_charges("OC303675")
    assert result.charges == []
    assert result.total_count == 0


@pytest.mark.live
async def test_live_charges_fixtures_still_match_stored_files() -> None:
    """Mirrors `test_109_live_fixtures_still_match_stored_files` one level
    down: re-fetch each recorded charges fixture and diff the mapped block
    against the stored one, ignoring provenance's own `fetched_at`/`cached`."""
    numbers = ["00445790", "00000006", "OC303675", "SC090312"]
    volatile = {"fetched_at", "cached"}
    for number in numbers:
        stored = charges_module.map_charges(
            _load(f"ch_{number}_charges.json"), number, cached=False, fetched_at=_FETCHED_AT
        )
        live = await client_module.fetch_charges(number)
        stored_dump = stored.model_dump(mode="json")
        live_dump = live.model_dump(mode="json")
        stored_dump["provenance"] = {
            k: v for k, v in stored_dump["provenance"].items() if k not in volatile
        }
        live_dump["provenance"] = {
            k: v for k, v in live_dump["provenance"].items() if k not in volatile
        }
        assert stored_dump == live_dump, (
            f"{number} charges fixture is stale relative to the register"
        )


# ---------------------------------------------------------------------------
# H. Filing history — R-5c / T37, built *behind the seam* (`DECISIONS.md`
# D-042; `registries/gb/filing_history.py`'s module docstring carries the full
# recon trail: 1876 items across nine companies, every `description_values`
# key with its count, and the argument for each shape choice). Not wired to
# `include=[...]` by this task. `filing_history.map_filing_history` is
# pure/no-I/O (mirrors `mapping.py`); `client_module.fetch_filings` is the
# async seam (mirrors `lookup`/`search`/`fetch_charges`).
#
# **Every fixture in this section was minimised at record time** — see each
# file's `_MINIMISED` header and `tests/fixtures/README.md`. D-042(e)(1)
# reads `items[].description_values` through an allow-list of exactly one
# key, `made_up_date`; the other 23 keys observed live were dropped before
# the files were written, because 97 Companies House description templates
# interpolate `{officer_name}`, 26 interpolate `{psc_name}`, and one
# (`representative_details`) interpolates a name *and* an address. No natural
# person's name has ever been in this repository. That is also why the two
# minimisation tests below inject their own synthetic sentinels rather than
# relying on what a fixture happens to contain: a stripped fixture cannot
# prove a filter works, and a fixture that could prove it must not exist.
# ---------------------------------------------------------------------------

DISSOLVED_FILINGS = _load("ch_00000006_filing_history.json")  # 25 of 206, officers-heavy
DISSOLVED_FILINGS_LEGACY = _load("ch_00000006_filing_history_legacy.json")  # deep page, 19 legacy
TESCO_FILINGS = _load("ch_00445790_filing_history.json")  # 25 of 8371 — the truncation case
LIQUIDATION_FILINGS = _load("ch_04374209_filing_history.json")  # 25 of 101, in liquidation
CIC_FILINGS = _load("ch_13507518_filing_history.json")  # 14 of 14 — complete, untruncated
OVERSEAS_FILINGS = _load("ch_FC032315_filing_history.json")  # 6 of 6 — representative_details
BR_FILINGS = _load("ch_BR026263_filing_history.json")  # 0, `filing-history-available`
CIO_FILINGS = _load("ch_CE020555_filing_history.json")  # 0, `...-not-available-unknown-prefix`

_ALL_FILING_FIXTURES: list[tuple[str, dict[str, Any]]] = [
    ("00000006", DISSOLVED_FILINGS),
    ("00000006", DISSOLVED_FILINGS_LEGACY),
    ("00445790", TESCO_FILINGS),
    ("04374209", LIQUIDATION_FILINGS),
    ("13507518", CIC_FILINGS),
    ("FC032315", OVERSEAS_FILINGS),
    ("BR026263", BR_FILINGS),
    ("CE020555", CIO_FILINGS),
]

#: Every distinct `description_values` key observed live, with the number of
#: items carrying it out of 1876 across nine companies (2026-09-08). This is
#: the recon result the allow-list is checked against — reality, not the
#: 97/26 template figure from the research. `made_up_date` is the one key
#: `DESCRIPTION_VALUES_ALLOW_LIST` contains; every other row here is a key
#: whose value must never reach a mapped field.
_OBSERVED_DESCRIPTION_VALUES_KEYS: dict[str, int] = {
    "description": 585,  # the `legacy` free-prose slot — the worst field in the payload
    "officer_name": 445,
    "date": 276,
    "capital": 272,
    "appointment_date": 193,
    "made_up_date": 182,  # the allow-listed key
    "termination_date": 140,
    "change_date": 110,
    "charge_number": 101,
    "charge_creation_date": 71,
    "new_address": 14,
    "psc_name": 13,
    "old_address": 12,
    "notification_date": 6,
    "cessation_date": 5,
    "withdrawal_date": 3,
    "branch_number": 3,
    "new_date": 2,
    "representative_details": 2,  # a natural person's name AND address in one string
    "form_type": 1,
    "original_description": 1,
    "change_type": 1,
    "change_details": 1,
    "change_name": 1,
}

#: The real officer-appointment item this section pins, recorded live in
#: `ch_00000006_filing_history.json`. On the wire it carried
#: `description_values` with exactly two keys, `officer_name` (a real
#: person's four-word name) and `appointment_date`; both were stripped at
#: record time, and the tests below re-inject synthetic stand-ins.
_APPOINTMENT_TRANSACTION_ID = "MzEyNDI3ODUzMmFkaXF6a2N4"
_APPOINTMENT_TEMPLATE = "appoint-person-director-company-with-name-date"
_APPOINTMENT_LIVE_KEYS = ("officer_name", "appointment_date")


# --- filing_history.map_filing_history — pure, no I/O ---------------------


def test_filings_map_dissolved_page_shape_counts_and_truncation() -> None:
    """The ordinary case: one page of 25 out of a 206-filing history, newest
    first, with truncation disclosed rather than silent (D-042(j))."""
    block = filing_history_module.map_filing_history(
        DISSOLVED_FILINGS, "00000006", cached=False, fetched_at=_FETCHED_AT
    )
    assert len(block.documents) == 25
    assert block.total_count == 206

    first = block.documents[0]
    assert first.filed_at == date(2018, 7, 10)
    assert first.category == "gazette"
    assert first.type_code == "GAZ2(A)"
    assert first.description_code == "gazette-dissolved-voluntary"
    assert first.kind is None  # a gazette notice discharges no deadline
    assert first.document_id == "MzIwODg2ODM4OGFkaXF6a2N4"
    assert first.period_end is None
    assert first.period_start is None  # always None for GB
    assert first.file_format is None  # always None for GB

    truncation = [n for n in block.notes if "206 filings" in n]
    assert len(truncation) == 1
    assert "only the 25 most recent are included here" in truncation[0]
    assert (
        "https://find-and-update.company-information.service.gov.uk/company/00000006/"
        "filing-history" in truncation[0]
    )


def test_filings_untruncated_page_says_nothing_about_truncation() -> None:
    """`total_count == len(documents)` must not produce a truncation note —
    the same asymmetry `charges.py` observes."""
    block = filing_history_module.map_filing_history(
        CIC_FILINGS, "13507518", cached=False, fetched_at=_FETCHED_AT
    )
    assert len(block.documents) == 14
    assert block.total_count == 14
    assert not [n for n in block.notes if "most recent are included here" in n]


def test_filings_kind_is_derived_only_from_the_two_categories_that_have_one() -> None:
    """D-042(h): `accounts` -> `annual_accounts`, `confirmation-statement` ->
    `confirmation_statement`, and the other twenty-odd Companies House
    categories -> `None` rather than an invented slug (D-009). The two slugs
    are imported from `registries/gb/rules.py`, not retyped, so a filing's
    `kind` cannot drift from the deadline it discharges."""
    seen: dict[str, set[str | None]] = {}
    for number, fixture in _ALL_FILING_FIXTURES:
        block = filing_history_module.map_filing_history(
            fixture, number, cached=False, fetched_at=_FETCHED_AT
        )
        for doc in block.documents:
            seen.setdefault(doc.category or "", set()).add(doc.kind)

    assert seen["accounts"] == {gb_rules.ACCOUNTS_KIND}
    assert seen["confirmation-statement"] == {gb_rules.CONFIRMATION_KIND}
    # Everything else observed across the eight fixtures maps to None.
    for category, kinds in seen.items():
        if category not in ("accounts", "confirmation-statement"):
            assert kinds == {None}, f"{category} invented a kind: {kinds}"
    # ...and the fixtures really do cover more than the two mapped ones.
    assert len(seen) > 8


def test_filings_financial_year_end_ignores_the_confirmation_statement() -> None:
    """The sharpest divergence from Sweden, and the reason it is not just
    "the newest `period_end`": a Companies House confirmation statement
    carries a `made_up_date` too, and it is not a financial year end.

    `13507518`'s newest reporting period of any kind is 2026-07-12 — a
    confirmation statement. Its newest *annual accounts* period is
    2025-07-31. `financial_year_end` must be the second.
    """
    block = filing_history_module.map_filing_history(
        CIC_FILINGS, "13507518", cached=False, fetched_at=_FETCHED_AT
    )
    newest_period_of_any_kind = max(d.period_end for d in block.documents if d.period_end)
    assert newest_period_of_any_kind == date(2026, 7, 12)
    newest_doc = block.documents[0]
    assert newest_doc.kind == gb_rules.CONFIRMATION_KIND
    assert newest_doc.period_end == date(2026, 7, 12)

    assert block.financial_year_end == date(2025, 7, 31)
    accounts = [d for d in block.documents if d.kind == gb_rules.ACCOUNTS_KIND and d.period_end]
    assert max(d.period_end for d in accounts if d.period_end) == date(2025, 7, 31)


def test_filings_financial_year_end_is_none_when_the_page_holds_no_accounts() -> None:
    """`FC032315` is an overseas company: six filings, none of them accounts,
    so there is no evidence of a financial year end and the field says so
    rather than borrowing a date from another kind of filing."""
    block = filing_history_module.map_filing_history(
        OVERSEAS_FILINGS, "FC032315", cached=False, fetched_at=_FETCHED_AT
    )
    assert len(block.documents) == 6
    assert {d.kind for d in block.documents} == {None}
    assert block.financial_year_end is None


def test_filings_financial_year_end_is_the_latest_period_not_the_latest_filing() -> None:
    """Companies House accepts a second filing that amends an earlier year, so
    "the newest annual-accounts filing" and "the newest annual-accounts
    period" are not the same date. `financial_year_end` is the second: an
    amended 2023 return filed in 2026 must not roll a 2025 year end backwards.

    Built from two real recorded items rather than invented ones — the
    `filed_at`/`made_up_date` pair is the only thing changed.
    """
    accounts = [i for i in CIC_FILINGS["items"] if i["category"] == "accounts"]
    assert len(accounts) >= 2
    recent, amended = json.loads(json.dumps(accounts[0])), json.loads(json.dumps(accounts[1]))
    recent["date"], recent["description_values"] = "2025-11-01", {"made_up_date": "2025-07-31"}
    amended["date"], amended["description_values"] = "2026-08-01", {"made_up_date": "2023-07-31"}
    amended["transaction_id"] = recent["transaction_id"] + "-amended"

    block = filing_history_module.map_filing_history(
        {
            "items": [amended, recent],
            "total_count": 2,
            "filing_history_status": "filing-history-available",
        },
        "13507518",
        cached=False,
        fetched_at=_FETCHED_AT,
    )
    # The amendment is the newest *filing* and sorts first...
    assert block.documents[0].filed_at == date(2026, 8, 1)
    assert block.documents[0].period_end == date(2023, 7, 31)
    # ...and the year end is still the latest *period*.
    assert block.financial_year_end == date(2025, 7, 31)


def test_filings_period_end_comes_from_made_up_date_and_nowhere_else() -> None:
    """`period_end` is the one thing read out of `description_values`, and it
    is read from the one allow-listed key. Every mapped `period_end` must be
    exactly the `made_up_date` of its own item, and an item without that key
    must have `period_end is None` — even when the item carries
    `action_date`, which is *nearly* the same date on accounts filings (it
    differed on 3 of 118 live) and is deliberately not used."""
    for number, fixture in _ALL_FILING_FIXTURES:
        block = filing_history_module.map_filing_history(
            fixture, number, cached=False, fetched_at=_FETCHED_AT
        )
        for item, doc in zip(
            fixture["items"],
            sorted(block.documents, key=lambda d: fixture_order(fixture, d)),
            strict=True,
        ):
            made_up = (item.get("description_values") or {}).get("made_up_date")
            expected = date.fromisoformat(made_up) if made_up else None
            assert doc.period_end == expected, f"{number}/{doc.document_id}"

    # ...and `action_date` never becomes `period_end`: at least one item in
    # the recorded set has an `action_date` and no `made_up_date`.
    with_action_only = [
        i
        for _, f in _ALL_FILING_FIXTURES
        for i in f["items"]
        if i.get("action_date") and "made_up_date" not in (i.get("description_values") or {})
    ]
    assert with_action_only
    ids = {i["transaction_id"] for i in with_action_only}
    for number, fixture in _ALL_FILING_FIXTURES:
        block = filing_history_module.map_filing_history(
            fixture, number, cached=False, fetched_at=_FETCHED_AT
        )
        for doc in block.documents:
            if doc.document_id in ids:
                assert doc.period_end is None


def fixture_order(fixture: dict[str, Any], doc: Any) -> int:
    """Position of `doc` in the fixture's own `items` order — used to zip a
    sorted block back onto the unsorted payload."""
    for index, item in enumerate(fixture["items"]):
        if item["transaction_id"] == doc.document_id:
            return index
    raise AssertionError(f"{doc.document_id} is not in this fixture")


def test_filings_days_from_fee_point_is_none_for_gb_and_the_reason_is_stated() -> None:
    """D-042(h) rules the field `None` for GB, and this task's brief adds
    that **the reason must be stated rather than inferred**. Both halves are
    asserted: every value is `None`, and the block says in words that the
    datum — not the calculation — is what Companies House does not publish."""
    for number, fixture in _ALL_FILING_FIXTURES:
        block = filing_history_module.map_filing_history(
            fixture, number, cached=False, fetched_at=_FETCHED_AT
        )
        assert all(d.days_from_fee_point is None for d in block.documents)
        if block.documents:
            reasons = [n for n in block.notes if "days_from_fee_point" in n]
            assert len(reasons) == 1, number
            assert "missing datum rather than a missing calculation" in reasons[0]
            assert "publishes no due date for a period already filed" in reasons[0]

    # The field's own description carries the reason too, so a caller reading
    # only the schema is not left to infer it.
    described = filing_history_module.FiledDocument.model_fields["days_from_fee_point"].description
    assert described is not None
    assert "Always `None` for Britain" in described
    assert "missing datum rather than a missing calculation" in described


def test_filings_empty_available_and_empty_unavailable_are_two_answers() -> None:
    """The D-011 case, and the one place this module declines to relay a
    number the register published.

    Companies House answers `total_count: 0` for two different reasons and
    only `filing_history_status` separates them. `BR026263` is
    `filing-history-available` — the register holds no filings for this UK
    establishment. `CE020555` is `filing-history-not-available-unknown-prefix`
    — the register cannot serve filing history for a number of that kind at
    all. Relaying the second as a zero would assert something about the
    company the register never said.
    """
    held_none = filing_history_module.map_filing_history(
        BR_FILINGS, "BR026263", cached=False, fetched_at=_FETCHED_AT
    )
    assert BR_FILINGS["filing_history_status"] == "filing-history-available"
    assert BR_FILINGS["total_count"] == 0
    assert held_none.documents == []
    assert held_none.total_count == 0
    assert len(held_none.notes) == 1
    assert "lists no filings for this company" in held_none.notes[0]
    assert "the register's own answer, not a failed lookup" in held_none.notes[0]

    cannot_answer = filing_history_module.map_filing_history(
        CIO_FILINGS, "CE020555", cached=False, fetched_at=_FETCHED_AT
    )
    assert CIO_FILINGS["filing_history_status"] == "filing-history-not-available-unknown-prefix"
    assert CIO_FILINGS["total_count"] == 0  # the register did publish a zero...
    assert cannot_answer.documents == []
    assert cannot_answer.total_count is None  # ...and we do not relay it as one
    assert len(cannot_answer.notes) == 1
    assert "filing-history-not-available-unknown-prefix" in cannot_answer.notes[0]
    assert "rather than that the company has filed nothing" in cannot_answer.notes[0]

    # The two blocks must not be confusable by a caller reading fields only.
    assert held_none.total_count != cannot_answer.total_count


def test_filings_legacy_rows_relay_the_sentinel_key_never_the_prose() -> None:
    """512 of the 1876 items observed live carry the literal
    `description: "legacy"` with the real text in
    `description_values.description` — the single most common key in the
    payload, and free prose that reads `"Director appointed mr <full name>"`
    on four of the 512. D-042(e)(1) bars reading it, so `description_code`
    carries the inert sentinel and nothing carries the prose."""
    legacy_items = [i for i in DISSOLVED_FILINGS_LEGACY["items"] if i["description"] == "legacy"]
    assert len(legacy_items) == 19
    # Stripped at record time: the prose was never written to this repository.
    assert all("description" not in (i.get("description_values") or {}) for i in legacy_items)

    block = filing_history_module.map_filing_history(
        DISSOLVED_FILINGS_LEGACY, "00000006", cached=False, fetched_at=_FETCHED_AT
    )
    legacy_docs = [d for d in block.documents if d.description_code == "legacy"]
    assert len(legacy_docs) == 19
    # A legacy row is still a usable filing record: it keeps its date, its
    # form code, its category and its handle. Only the prose is refused.
    for doc in legacy_docs:
        assert doc.filed_at is not None
        assert doc.category
        assert doc.type_code
        assert doc.document_id


def test_filings_sorted_newest_first_and_stable_within_a_date() -> None:
    """D-042(j): newest first. GB sorts on `filed_at` alone — Sweden's
    `period_end`-first key would sort 90% of a British history (1694 of 1876
    items have no reporting period) into an arbitrary block at the end.
    Python's sort is stable under `reverse=True`, so filings sharing a date
    keep the register's own order."""
    for number, fixture in _ALL_FILING_FIXTURES:
        block = filing_history_module.map_filing_history(
            fixture, number, cached=False, fetched_at=_FETCHED_AT
        )
        dates = [d.filed_at for d in block.documents]
        assert dates == sorted(dates, key=lambda d: d or date.min, reverse=True), number

    # Stability, on a fixture that actually has a repeated date.
    tesco = filing_history_module.map_filing_history(
        TESCO_FILINGS, "00445790", cached=False, fetched_at=_FETCHED_AT
    )
    by_date: dict[date | None, list[str | None]] = {}
    for doc in tesco.documents:
        by_date.setdefault(doc.filed_at, []).append(doc.document_id)
    repeated = {d: ids for d, ids in by_date.items() if len(ids) > 1}
    assert repeated, "expected at least one date with several filings on it"
    for filed_on, ids in repeated.items():
        register_order = [
            i["transaction_id"]
            for i in TESCO_FILINGS["items"]
            if date.fromisoformat(i["date"]) == filed_on
        ]
        assert ids == register_order


def test_filings_provenance_and_extra_forbid() -> None:
    block = filing_history_module.map_filing_history(
        BR_FILINGS, "BR026263", cached=True, fetched_at=_FETCHED_AT
    )
    assert block.provenance.source == "Companies House (UK)"
    assert block.provenance.source_url == (
        "https://find-and-update.company-information.service.gov.uk/company/BR026263/filing-history"
    )
    assert (
        block.provenance.license
        == "Crown copyright — Companies House public register, free to re-use"
    )
    assert block.provenance.fetched_at == _FETCHED_AT
    assert block.provenance.cached is True

    with pytest.raises(pydantic.ValidationError):  # extra="forbid" (D-004)
        filing_history_module.FiledDocument(category="accounts", not_a_real_field=True)  # type: ignore[call-arg]


def test_filings_model_mirrors_the_swedish_one_field_for_field() -> None:
    """D-042(g)/(h): Britain's payload is the superset that defines the shared
    model, and Sweden fills a subset — so wiring both into `core/models.py` is
    a rename, not a redesign. `FiledDocument` must be identical in name and
    order; `FilingHistory` differs by exactly one field, `total_count`, which
    D-042(j) rules by name ("the block carries the register's own
    `total_count`") and which `ChargeBlock` already carries with the same
    meaning. Flagged for the architect in this module's docstring."""
    assert list(filing_history_module.FiledDocument.model_fields) == list(
        se_filings_module.FiledDocument.model_fields
    )
    assert list(filing_history_module.FilingProvenance.model_fields) == list(
        se_filings_module.FilingProvenance.model_fields
    )
    gb_block = list(filing_history_module.FilingHistory.model_fields)
    se_block = list(se_filings_module.FilingHistory.model_fields)
    assert set(gb_block) - set(se_block) == {"total_count"}
    assert set(se_block) - set(gb_block) == set()


# --- The two minimisation proofs (D-042(e)(1), D-028) ---------------------


def test_filings_minimisation_no_value_outside_the_allow_list_can_reach_output() -> None:
    """**The proof, not the assertion.** Walks every item of every committed
    fixture and fails if any mapped output field carries a value from any
    `description_values` key other than `made_up_date`.

    A stripped fixture cannot prove a filter works — there is nothing left to
    leak — and a fixture that could prove it would have to contain a real
    person's name, which this repository must never hold. So the test
    reconstructs the hazard instead: for every item, it re-injects a unique
    sentinel under **every one of the 23 non-allow-listed keys observed live**
    (`_OBSERVED_DESCRIPTION_VALUES_KEYS`, counted over 1876 items on nine
    companies — `officer_name` on 445 of them, `psc_name` on 13,
    `representative_details`, which is a name *and* an address, on 2, and the
    `legacy` free-prose `description` on 585), plus the same sentinels in the
    three nested containers Companies House hangs off an item
    (`annotations[]`, `resolutions[]`, `associated_filings[]`, each with a
    `description_values` of its own) and in `annotations[].annotation`, which
    is registrar free prose. It then maps the item and asserts that not one
    sentinel appears anywhere in the serialised block.

    The positive control matters as much as the negative one: `made_up_date`
    must still come through, or this test would pass on a mapper that returns
    nothing at all.
    """
    hazard_keys = [
        k
        for k in _OBSERVED_DESCRIPTION_VALUES_KEYS
        if k not in filing_history_module.DESCRIPTION_VALUES_ALLOW_LIST
    ]
    assert len(hazard_keys) == 23
    assert "officer_name" in hazard_keys and "psc_name" in hazard_keys
    assert "representative_details" in hazard_keys and "description" in hazard_keys

    # The nested containers have a key set of their own that the 24
    # top-level ones do not cover; injected too, so nothing in them is
    # tested only by omission.
    nested_only_keys = ["res_type", "resolution_date"]

    def poison(values: dict[str, Any], tag: str, keys: list[str]) -> dict[str, Any]:
        poisoned = dict(values)
        for key in keys:
            poisoned[key] = f"SENTINEL-{tag}-{key}-MUST-NOT-LEAK"
        return poisoned

    sentinels_expected = 0
    made_up_dates_seen = 0

    for number, fixture in _ALL_FILING_FIXTURES:
        spiked = json.loads(json.dumps(fixture))
        for index, item in enumerate(spiked.get("items") or []):
            tag = f"{number}-{index}"
            item["description_values"] = poison(
                item.get("description_values") or {}, tag, hazard_keys
            )
            sentinels_expected += len(hazard_keys)
            for container in ("annotations", "resolutions", "associated_filings"):
                for sub_index, sub in enumerate(item.get(container) or []):
                    sub_tag = f"{tag}-{container}-{sub_index}"
                    sub["description_values"] = poison(
                        sub.get("description_values") or {},
                        sub_tag,
                        hazard_keys + nested_only_keys,
                    )
                    sentinels_expected += len(hazard_keys) + len(nested_only_keys)
                    if container == "annotations":
                        sub["annotation"] = f"SENTINEL-{sub_tag}-annotation-MUST-NOT-LEAK"
                        sentinels_expected += 1

        block = filing_history_module.map_filing_history(
            spiked, number, cached=False, fetched_at=_FETCHED_AT
        )
        serialised = json.dumps(block.model_dump(mode="json"), default=str)
        assert "SENTINEL-" not in serialised, (
            f"{number}: a description_values value outside the allow-list reached the "
            f"mapped block — D-042(e)(1) is broken"
        )

        for doc, item in zip(
            sorted(block.documents, key=lambda d: fixture_order(fixture, d)),
            fixture["items"],
            strict=True,
        ):
            made_up = (item.get("description_values") or {}).get("made_up_date")
            if made_up:
                made_up_dates_seen += 1
                assert doc.period_end == date.fromisoformat(made_up)

    # Positive controls: the hazard really was injected, and the one allowed
    # key really does survive it.
    assert sentinels_expected > 3000
    assert made_up_dates_seen == 29


def test_filings_a_real_officer_appointment_never_names_the_person() -> None:
    """The second proof, on a real item rather than a synthetic one.

    `ch_00000006_filing_history.json` item `MzEyNDI3ODUzMmFkaXF6a2N4` is a
    genuine Companies House AP01 recorded live on 2026-09-08: a director
    appointment whose `description_values` carried exactly
    `{"officer_name": <a real person's four-word name>,
      "appointment_date": ...}` on the wire. Both keys were stripped before
    the fixture was written, so the name is nowhere in this repository; the
    test re-injects a synthetic one under the same keys and proves it reaches
    no mapped field.

    The second half does the same for the `legacy` form of the same event —
    `description: "legacy"` with the prose `"Director appointed mr <name>"`,
    which is the exact shape observed live on four of 512 legacy rows. Both
    routes to a person's name are closed, and what survives is the template
    key, which says a director was appointed without saying who.
    """
    item = next(
        i for i in DISSOLVED_FILINGS["items"] if i["transaction_id"] == _APPOINTMENT_TRANSACTION_ID
    )
    assert item["description"] == _APPOINTMENT_TEMPLATE
    assert item["category"] == "officers"
    assert item["subcategory"] == "appointments"
    assert item["type"] == "AP01"
    # The strip really happened: the two live keys are gone from the fixture.
    assert item["description_values"] == {}
    assert not any(k in item["description_values"] for k in _APPOINTMENT_LIVE_KEYS)

    person = "Ada Testperson Nightingale"
    restored = json.loads(json.dumps(item))
    restored["description_values"] = {
        "officer_name": person,
        "appointment_date": "2015-06-01",
    }
    block = filing_history_module.map_filing_history(
        {
            "items": [restored],
            "total_count": 1,
            "filing_history_status": "filing-history-available",
        },
        "00000006",
        cached=False,
        fetched_at=_FETCHED_AT,
    )
    serialised = json.dumps(block.model_dump(mode="json"), default=str)
    assert person not in serialised
    for fragment in ("Ada", "Testperson", "Nightingale"):
        assert fragment not in serialised
    assert "2015-06-01" not in serialised  # the appointment date is not allow-listed either

    # What does survive is the register's own template key — which says a
    # director was appointed, and does not say who.
    doc = block.documents[0]
    assert doc.description_code == _APPOINTMENT_TEMPLATE
    assert "person-director" in doc.description_code
    assert doc.category == "officers"
    assert doc.type_code == "AP01"
    assert doc.kind is None
    assert doc.period_end is None
    assert doc.filed_at == date(2015, 6, 2)
    assert doc.document_id == _APPOINTMENT_TRANSACTION_ID

    # The same appointment as a pre-2010 `legacy` row: the name moves into
    # free prose under `description_values.description`, and is refused there
    # too. This is the exact string shape observed live.
    legacy = json.loads(json.dumps(item))
    legacy["description"] = "legacy"
    legacy["description_values"] = {"description": f"Director appointed mr {person}"}
    legacy_block = filing_history_module.map_filing_history(
        {"items": [legacy], "total_count": 1, "filing_history_status": "filing-history-available"},
        "00000006",
        cached=False,
        fetched_at=_FETCHED_AT,
    )
    legacy_serialised = json.dumps(legacy_block.model_dump(mode="json"), default=str)
    assert person not in legacy_serialised
    assert "Director appointed" not in legacy_serialised
    assert legacy_block.documents[0].description_code == "legacy"


def test_filings_allow_list_has_exactly_one_key_and_only_one_reader() -> None:
    """D-042(e)(1) is greppable by design: `description_values` appears in
    exactly one place under `registries/gb/`, next to an allow-list of
    exactly one key. Widening it is a `DECISIONS.md` entry, never an
    implementer's edit — so this test is the tripwire on that."""
    assert set(filing_history_module.DESCRIPTION_VALUES_ALLOW_LIST) == {"made_up_date"}

    gb_dir = Path(filing_history_module.__file__).parent
    readers = {
        path.name: path.read_text(encoding="utf-8").count('get("description_values")')
        for path in sorted(gb_dir.glob("*.py"))
    }
    assert sum(readers.values()) == 1, readers
    assert readers["filing_history.py"] == 1


# --- client_module.fetch_filings — respx-mocked, no network ---------------


@respx.mock
async def test_fetch_filings_requests_one_page_of_twenty_five() -> None:
    """D-042(j) rules the page size for filings at 25 — a quarter of the
    register's own maximum of 100, confirmed live (101, 200 and 1000 all
    return 100). Never paginated further."""
    route = respx.get(f"{BASE_URL}/company/00445790/filing-history").mock(
        return_value=httpx.Response(200, json=TESCO_FILINGS)
    )
    result = await client_module.fetch_filings("00445790")
    assert route.call_count == 1
    assert route.calls.last.request.url.params["items_per_page"] == "25"
    assert "start_index" not in route.calls.last.request.url.params
    assert len(result.documents) == 25
    assert result.total_count == 8371


@respx.mock
async def test_fetch_filings_404_is_a_present_empty_block_not_an_error() -> None:
    """`/company/{n}` alone decides whether an entity exists (D-041(h)).
    Confirmed live that this endpoint never 404s — not even for a company
    number that was never issued, which answers 200 with `total_count: 0` —
    but the client treats one as a present empty block, defensively."""
    respx.get(f"{BASE_URL}/company/00445790/filing-history").mock(return_value=httpx.Response(404))
    result = await client_module.fetch_filings("00445790")
    assert result.documents == []
    assert result.total_count is None  # nothing was published, not "zero filings"
    assert result.provenance.cached is False


@respx.mock
async def test_fetch_filings_empty_result_is_never_not_found_on_a_cache_hit() -> None:
    """Empty results are cached under the existing `status="not_found"` label
    purely to borrow its 1 h TTL (D-042(j)) — never surfaced as an error on
    read, unlike its use in `lookup`."""
    route = respx.get(f"{BASE_URL}/company/BR026263/filing-history").mock(
        return_value=httpx.Response(200, json=BR_FILINGS)
    )
    first = await client_module.fetch_filings("BR026263")
    assert first.documents == []
    assert first.provenance.cached is False

    second = await client_module.fetch_filings("BR026263")
    assert route.call_count == 1  # served from the cache, not refetched
    assert second.documents == []
    assert second.total_count == 0
    assert second.provenance.cached is True
    assert second.provenance.fetched_at == first.provenance.fetched_at


@respx.mock
async def test_fetch_filings_validates_the_crn_before_opening_a_socket() -> None:
    route = respx.get(f"{BASE_URL}/company/nonsense/filing-history").mock(
        return_value=httpx.Response(200, json=BR_FILINGS)
    )
    with pytest.raises(RegistryError) as excinfo:
        await client_module.fetch_filings("not a company number")
    assert excinfo.value.code is ErrorCode.INVALID_ID
    assert route.call_count == 0


@respx.mock
async def test_fetch_filings_maps_upstream_statuses_like_every_other_gb_fetch() -> None:
    for status, expected in ((401, ErrorCode.UPSTREAM_ERROR), (429, ErrorCode.RATE_LIMITED)):
        # An error path never writes to the cache, so no reset is needed
        # between the two: `_isolated_cache` already gives this test its own.
        respx.get(f"{BASE_URL}/company/00445790/filing-history").mock(
            return_value=httpx.Response(status)
        )
        with pytest.raises(RegistryError) as excinfo:
            await client_module.fetch_filings("00445790")
        assert excinfo.value.code is expected


# --- Live done-check (excluded from CI) ------------------------------------


@pytest.mark.live
async def test_live_filings_minimised_fixtures_map_identically_to_the_wire() -> None:
    """The strongest live check available, and it is a minimisation proof of
    its own: re-fetch each *stable* recorded page and assert the block built
    from the **minimised** fixture equals the block built from the **live,
    un-minimised** payload. If stripping 23 keys at record time changed any
    output, this fails — and it passing is the demonstration that everything
    dropped was, by construction, unreachable.

    Only companies whose filing history cannot move are used: a dissolved
    company, an overseas company last active in 2021, and a UK establishment
    with no filings. Tesco is deliberately excluded — it files most weeks, so
    page one is stale within days and would make this a flake, not a check.
    """
    volatile = {"fetched_at", "cached"}
    for number, name in (
        ("00000006", "ch_00000006_filing_history.json"),
        ("FC032315", "ch_FC032315_filing_history.json"),
        ("BR026263", "ch_BR026263_filing_history.json"),
    ):
        stored = filing_history_module.map_filing_history(
            _load(name), number, cached=False, fetched_at=_FETCHED_AT
        )
        live = await client_module.fetch_filings(number)
        stored_dump = stored.model_dump(mode="json")
        live_dump = live.model_dump(mode="json")
        for dump in (stored_dump, live_dump):
            dump["provenance"] = {k: v for k, v in dump["provenance"].items() if k not in volatile}
        assert stored_dump == live_dump, f"{name} is stale relative to the register"


@pytest.mark.live
async def test_live_filings_empty_is_two_distinguishable_answers() -> None:
    """The D-011 pair, live: `BR026263` holds no filings; `CE020555` is a
    number Companies House does not serve filing history for at all."""
    held_none = await client_module.fetch_filings("BR026263")
    assert held_none.documents == []
    assert held_none.total_count == 0

    cannot_answer = await client_module.fetch_filings("CE020555")
    assert cannot_answer.documents == []
    assert cannot_answer.total_count is None
    assert any("does not serve filing history" in n for n in cannot_answer.notes)
