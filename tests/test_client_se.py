"""Tests for `registries/se/client.py` and `registries/se/mapping.py`.

Numbered tests 79-118 of `SWEDEN_SPEC.md` §14 ("F. Mapping" / "G. Client" /
"H. Live done-check"), named `test_NN_<slug>` to match
`tests/test_rules_se.py`'s convention. 113-118 are `@pytest.mark.live` and
excluded from CI (`pytest -m "not live"`) — Sweden has no credentials in this
environment, so they are written but always skipped here.
"""

from __future__ import annotations

import copy
import json
import logging
import time
import uuid
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
    report = mapping.map_entity(AB_ACTIVE, "5299999994")
    assert report.name == "Cykelbolaget AB"
    assert report.legal_form_code == "AB"
    assert report.status is CompanyStatus.ACTIVE
    assert report.id == "5299999994"
    assert report.id_formatted == "529999-9994"


def test_80_previous_names_empty_and_n12() -> None:
    report = mapping.map_entity(AB_ACTIVE, "5299999994")
    assert report.previous_names == []
    assert any("Mopedbolaget AB" in n and "Bicycle expert" in n for n in report.notes)


def test_81_industry_codes() -> None:
    report = mapping.map_entity(AB_ACTIVE, "5299999994")
    assert len(report.industry_codes) == 2
    first, second = report.industry_codes
    assert first.code == "47642"
    assert first.description == "Specialiserad butikshandel med cyklar"
    assert first.scheme == "SNI 2007"
    assert first.rank == 1
    assert second.code == "45400"
    assert second.rank == 2


def test_82_dates() -> None:
    report = mapping.map_entity(AB_ACTIVE, "5299999994")
    assert report.registered_at == date(2000, 1, 23)
    assert report.founded_at is None


def test_83_postal_address() -> None:
    report = mapping.map_entity(AB_ACTIVE, "5299999994")
    assert report.postal_address is not None
    assert report.postal_address.lines == ["C/o Annat företag", "Jobbstigen 2"]
    assert report.postal_address.postal_code == "12345"
    assert report.postal_address.city == "Grönköping"
    assert report.postal_address.country_code == "SE"
    assert report.postal_address.country_name == "Sverige"
    assert report.business_address is None


def test_84_activity_is_trimmed() -> None:
    report = mapping.map_entity(AB_ACTIVE, "5299999994")
    assert report.activity == "Bedriva handel med cyklar och tillbehör till cyklar"


def test_85_unpublished_fields_are_honestly_none() -> None:
    report = mapping.map_entity(AB_ACTIVE, "5299999994")
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
    report = mapping.map_entity(AB_ACTIVE, "5299999994")
    assert any("reklamspärr" in n.lower() for n in report.notes)


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
    report = mapping.map_entity(SCB_ONLY, "5567223705")
    assert report.legal_form_code == "49"
    assert any("Statistics Sweden" in n for n in report.notes)


def test_95_uppgiftskalla_fel_constructs_without_raising() -> None:
    """T26b's chosen behaviour (either is permitted by the spec): construct
    without raising, `name` falls back to the identifier, and note N13 names
    the unavailable producer."""
    report = mapping.map_entity(UPPGIFTSKALLA_FEL, "194009272719")
    assert report.name == "194009272719"
    assert report.id == "194009272719"
    assert any("could not be retrieved" in n and "Bolagsverket" in n for n in report.notes)


def test_96_finns_ej_detected_as_not_found() -> None:
    assert mapping.is_not_found(FINNS_EJ) is True


def test_97_registreringsland_never_read() -> None:
    data = copy.deepcopy(AB_ACTIVE)
    data["organisationer"][0]["registreringsland"] = {"kod": "XX-LAND", "klartext": "Nowhereland"}
    report = mapping.map_entity(data, "5299999994")
    assert report.country == "SE"


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
    assert report.name == "Cykelbolaget AB"

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
    assert report.name == "Cykelbolaget AB"
    assert token_route.call_count == 2
    assert data_route.call_count == 2


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
    _mock_token()
    data_route = _mock_data(FINNS_EJ)
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("193403223328")
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
    assert report.name == "Cykelbolaget AB"
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
    assert http_client.is_closed is False
    assert "production" in client_module._tokens

    await registry.aclose()
    assert http_client.is_closed is True
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
    report = await client_module.lookup("198101052382")
    assert any("namnskyddslöpnummer" in n and "2" in n for n in report.notes)


@pytest.mark.live
async def test_115_live_finns_ej_not_found() -> None:
    with pytest.raises(RegistryError) as excinfo:
        await client_module.lookup("193403223328")
    assert excinfo.value.code is ErrorCode.NOT_FOUND


@pytest.mark.live
async def test_116_live_check_digit_experiment_5560000002() -> None:
    """The §5.1.1 experiment. Record the outcome in `REVIEW.md` §T26e
    whichever way it goes: an organisation refutes the modulus-10 caveat, a
    `400 "ogiltig kontrollsiffra"` confirms it."""
    try:
        report = await client_module.lookup("5560000002")
        print(f"5560000002 resolved: {report.name!r} — modulus-10 caveat REFUTED")
    except RegistryError as exc:
        print(f"5560000002 raised {exc.code}: {exc.message} — modulus-10 caveat may be CONFIRMED")


@pytest.mark.live
async def test_117_live_field_names_present_or_optional() -> None:
    report = await client_module.lookup("5560021361")
    assert report.name


@pytest.mark.live
async def test_118_live_id_example_is_active() -> None:
    import os

    os.environ["BOLAGSVERKET_ENVIRONMENT"] = "production"
    report = await client_module.lookup("5560160680")
    assert report.status is CompanyStatus.ACTIVE
    assert report.name
