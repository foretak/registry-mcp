"""Smoke tests for the T01 interface: the shapes exist and the plugin wiring works.

Behavioural tests for Norwegian rules are T02's job (see ``NORBIZ_SPEC.md`` §5).
"""

from __future__ import annotations

from datetime import date

import pytest

from registry_mcp.core.models import (
    CompanyReport,
    CompanyStatus,
    Deadline,
    DeadlineRecurrence,
    ErrorCode,
    RegistryError,
    SearchHit,
    SearchResult,
)
from registry_mcp.core.registry import Registry, get_registry, list_countries, list_registries


def test_models_import_and_construct(sample_report: CompanyReport) -> None:
    assert sample_report.country == "NO"
    assert sample_report.status is CompanyStatus.ACTIVE
    dumped = sample_report.model_dump(mode="json")
    assert dumped["status"] == "active"
    assert dumped["registered_at"] == "1995-03-12"


def test_country_code_is_upper_cased() -> None:
    hit = SearchHit(country="no", registry="brreg", id="923609016", name="EQUINOR ASA")
    assert hit.country == "NO"


def test_search_result_shape() -> None:
    result = SearchResult(country="NO", registry="brreg", query="equinor", total=240)
    assert result.hits == []
    assert result.total == 240


def test_deadline_shape() -> None:
    deadline = Deadline(
        country="NO",
        registry="brreg",
        kind="annual_accounts",
        name="Annual accounts filing",
        local_name="Årsregnskap",
        authority="Regnskapsregisteret",
        statutory_date=date(2026, 7, 31),
        due_date=date(2026, 7, 31),
        recurrence=DeadlineRecurrence.ANNUAL,
        applies_because="AS must file annual accounts.",
    )
    assert deadline.rolled_forward is False
    assert deadline.model_dump(mode="json")["due_date"] == "2026-07-31"


def test_error_envelope_shape() -> None:
    err = RegistryError(
        ErrorCode.NOT_FOUND,
        "No entity with organisasjonsnummer 999999999.",
        hint="Check the number, or call search_company with the company name instead.",
        country="NO",
        registry="brreg",
    )
    payload = err.to_dict()
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == "not_found"
    assert payload["error"]["hint"]
    assert err.http_status == 404


def test_no_registry_is_registered(brreg: Registry) -> None:
    assert brreg.country == "NO"
    assert brreg.registry == "brreg"
    assert brreg.is_stub is False
    assert brreg.id_example == "923609016"


def test_public_country_list_hides_stubs() -> None:
    assert list_countries() == ["NO"]
    assert list_countries(include_stubs=True) == ["NO", "XX"]
    assert [r.country for r in list_registries(include_stubs=True)] == ["NO", "XX"]


def test_stub_country_visible_via_env(include_stubs: None) -> None:
    assert list_countries() == ["NO", "XX"]
    assert get_registry("XX").country == "XX"


def test_stub_country_hidden_by_default() -> None:
    with pytest.raises(RegistryError) as excinfo:
        get_registry("XX")
    assert excinfo.value.code is ErrorCode.UNSUPPORTED_COUNTRY


def test_unsupported_country_hint_lists_supported() -> None:
    with pytest.raises(RegistryError) as excinfo:
        get_registry("ZZ")
    err = excinfo.value
    assert err.code is ErrorCode.UNSUPPORTED_COUNTRY
    assert "NO" in err.hint
    assert err.details["supported"] == ["NO"]


def test_second_country_needs_no_core_edit(example_registry: Registry) -> None:
    """The XX folder alone is enough to make a country resolvable and usable."""
    assert example_registry.validate_id("1234 5678") == "12345678"
    assert example_registry.deadlines.__self__ is example_registry  # type: ignore[attr-defined]
    assert example_registry.describe()["is_stub"] is True


async def test_stub_methods_raise_not_implemented(example_registry: Registry) -> None:
    """The XX template still answers ``not_implemented`` for the data operations.

    This is the half of the old ``test_norwegian_methods_raise_not_implemented``
    that is still true: a stub registry resolves, describes itself and validates
    an id, but has no data behind it.
    """
    with pytest.raises(RegistryError) as excinfo:
        await example_registry.lookup("12345678")
    assert excinfo.value.code is ErrorCode.NOT_IMPLEMENTED
    assert excinfo.value.http_status == 501

    with pytest.raises(RegistryError) as excinfo:
        await example_registry.search("example")
    assert excinfo.value.code is ErrorCode.NOT_IMPLEMENTED


def test_norwegian_sync_methods_are_implemented(
    brreg: Registry, sample_report: CompanyReport
) -> None:
    """NO no longer raises ``not_implemented``: T02 filled in the sync methods.

    Only the two pure methods are exercised here — ``lookup`` and ``search`` are
    network calls covered by ``tests/test_client_no.py``.
    """
    assert brreg.validate_id("923 609 016") == "923609016"

    with pytest.raises(RegistryError) as excinfo:
        brreg.validate_id("923609017")
    assert excinfo.value.code is ErrorCode.INVALID_ID
    assert excinfo.value.http_status == 400

    deadlines = brreg.deadlines(sample_report, date(2026, 1, 15))
    assert deadlines, "an active ASA should have filing deadlines"
    assert all(d.country == "NO" and d.registry == "brreg" for d in deadlines)
