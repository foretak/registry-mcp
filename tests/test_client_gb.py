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
