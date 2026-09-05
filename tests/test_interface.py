"""Smoke tests for the T01 interface: the shapes exist and the plugin wiring works.

Behavioural tests for Norwegian rules are T02's job (see ``NORBIZ_SPEC.md`` §5).
"""

from __future__ import annotations

from datetime import date

import pytest

from registry_mcp.core.models import (
    CompanyReport,
    CompanyStatus,
    CountriesResponse,
    CountryInfo,
    Deadline,
    DeadlineRecurrence,
    ErrorCode,
    RegistryError,
    SearchHit,
    SearchResult,
    ValidationResult,
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
    assert list_countries() == ["GB", "NO", "SE"]
    assert list_countries(include_stubs=True) == ["GB", "NO", "SE", "XX"]
    assert [r.country for r in list_registries(include_stubs=True)] == ["GB", "NO", "SE", "XX"]


def test_stub_country_visible_via_env(include_stubs: None) -> None:
    assert list_countries() == ["GB", "NO", "SE", "XX"]
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
    assert err.details["supported"] == ["GB", "NO", "SE"]


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


# ---------------------------------------------------------------------------
# D-010 — the two canonical documents both surfaces must emit
# ---------------------------------------------------------------------------


def test_deadline_report_is_the_canonical_deadlines_document(
    brreg: Registry, sample_report: CompanyReport
) -> None:
    """`Registry.deadline_report` wraps `deadlines()` — surfaces never assemble it."""
    today = date(2026, 1, 15)
    document = brreg.deadline_report(sample_report, today)

    assert document.country == "NO"
    assert document.registry == "brreg"
    assert document.company_id == sample_report.id
    assert document.company_name == sample_report.name
    assert document.today == today
    assert document.deadlines == brreg.deadlines(sample_report, today)
    assert document.notes == sample_report.notes

    dumped = document.model_dump(mode="json")
    assert dumped["today"] == "2026-01-15"
    assert set(dumped) == {
        "country",
        "registry",
        "company_id",
        "company_name",
        "today",
        "deadlines",
        "notes",
    }


def test_deadline_report_carries_notes_when_the_list_is_empty(brreg: Registry) -> None:
    """An empty list is a real answer; `notes` is what makes it readable."""
    bankrupt = CompanyReport(
        country="NO",
        registry="brreg",
        id="923609016",
        name="EQUINOR ASA",
        legal_form_code="ASA",
        has_annual_accounts_duty=True,
        status=CompanyStatus.BANKRUPT,
        notes=["This company is bankrupt; no filing deadlines are computed."],
    )
    document = brreg.deadline_report(bankrupt, date(2026, 1, 15))
    assert document.deadlines == []
    assert document.notes


def test_validate_returns_a_result_not_an_error(brreg: Registry) -> None:
    """`validate` answers a question: an invalid id is `valid=False`, not a raise."""
    ok = brreg.validate("923 609 016")
    assert isinstance(ok, ValidationResult)
    assert ok.valid is True
    assert ok.normalized == "923609016"
    assert ok.formatted == "923 609 016"
    assert ok.id_scheme == "organisasjonsnummer"
    assert ok.input == "923 609 016"
    assert ok.reason
    assert ok.hint is None

    bad = brreg.validate("923609017")
    assert bad.valid is False
    assert bad.normalized is None
    assert bad.formatted is None
    assert bad.reason
    assert bad.hint is not None and "search_company" in bad.hint


def test_validate_is_inherited_by_a_stub_country(example_registry: Registry) -> None:
    """D-008: a new country gets both documents for free, with no extra code."""
    ok = example_registry.validate("1234 5678")
    assert ok.valid is True
    assert ok.normalized == "12345678"
    assert ok.formatted is None  # XX declares no local grouping convention
    assert example_registry.validate("nope").valid is False


def test_validate_success_reason_names_a_concrete_next_call(brreg: Registry) -> None:
    """D-007's "name the next call" standard applies to ``reason`` too (D-013).

    The success sentence used to end "call lookup to find out", and ``lookup``
    is not a callable name on either surface.
    """
    reason = brreg.validate("923609016").reason
    assert reason is not None
    assert "lookup_company" in reason
    assert "/company/" in reason


# ---------------------------------------------------------------------------
# D-012 — the discovery row has a model
# ---------------------------------------------------------------------------


def test_country_info_is_the_single_definition_of_the_discovery_row(brreg: Registry) -> None:
    info = brreg.country_info()
    assert isinstance(info, CountryInfo)
    assert info.country == "NO"
    assert info.registry == "brreg"
    assert info.is_stub is False
    # `describe()` is kept for the surfaces that already call it, but is now
    # derived from `country_info()` — one row, one definition.
    assert brreg.describe() == info.model_dump(mode="json")


def test_country_info_is_inherited_by_a_stub_country(example_registry: Registry) -> None:
    """D-008: a country folder gets the discovery row for free, like the other documents."""
    assert example_registry.country_info().is_stub is True


def test_countries_response_forbids_an_unrecognised_key() -> None:
    """The point of D-012: an extra key fails loudly on *both* surfaces at once.

    Before the model existed, REST validated the dict through a private model
    that silently dropped an unknown key while MCP passed the raw dict straight
    through and kept it — the two surfaces disagreeing by omission.
    """
    row = get_registry("NO").describe()
    assert CountryInfo.model_validate(row).country == "NO"
    with pytest.raises(ValueError):
        CountryInfo.model_validate({**row, "currency": "NOK"})


def test_countries_response_round_trips(brreg: Registry) -> None:
    response = CountriesResponse(countries=[r.country_info() for r in list_registries()])
    dumped = response.model_dump(mode="json")
    assert [row["country"] for row in dumped["countries"]] == list_countries()
    assert brreg.country_info().model_dump(mode="json") in dumped["countries"]


async def test_aclose_is_a_no_op_a_country_may_override(example_registry: Registry) -> None:
    """D-014: the shutdown hook exists on every registry, so a surface can just call it."""
    await example_registry.aclose()


# ---------------------------------------------------------------------------
# D-020 — `SearchResult.hits` is sorted best-first by the model itself
# ---------------------------------------------------------------------------


def _hit(id: str, confidence: float) -> SearchHit:
    return SearchHit(
        country="XX", registry="example", id=id, name=f"HIT {id}", confidence=confidence
    )


def test_search_hits_are_sorted_by_confidence_descending() -> None:
    """D-020: `hits` promises "best first", so the model delivers it.

    The producer that exposed this returned 0.8, 0.4, 0.8 in the register's
    relevance order — a 0.4 hit above a 0.8 hit, on the field an agent reads
    first. `search` is abstract, so there is no D-010-style wrapper to sort in;
    the model is the only country-neutral chokepoint.
    """
    result = SearchResult(
        country="XX",
        registry="example",
        query="tesco",
        hits=[_hit("a", 0.8), _hit("b", 0.4), _hit("c", 0.8)],
    )
    assert [h.confidence for h in result.hits] == [0.8, 0.8, 0.4]


def test_search_hits_sort_is_stable_so_register_order_breaks_ties() -> None:
    """Equal confidence keeps the upstream order: we re-rank by our confidence,
    we do not discard the register's relevance ranking (D-005's anchors are
    coarse enough that ties are the common case, not the edge case)."""
    result = SearchResult(
        country="XX",
        registry="example",
        query="tesco",
        hits=[_hit("a", 0.4), _hit("b", 0.8), _hit("c", 0.4), _hit("d", 0.8)],
    )
    assert [h.id for h in result.hits] == ["b", "d", "a", "c"]


def test_search_hits_are_sorted_on_revalidation_too() -> None:
    """It is a validator, not a constructor step, so a cached payload replayed
    through `model_validate` cannot disagree with a fresh result about order."""
    payload = {
        "country": "XX",
        "registry": "example",
        "query": "tesco",
        "hits": [
            _hit("a", 0.4).model_dump(mode="json"),
            _hit("b", 0.95).model_dump(mode="json"),
        ],
    }
    assert [h.id for h in SearchResult.model_validate(payload).hits] == ["b", "a"]


# ---------------------------------------------------------------------------
# D-021 — `Registry.id_caveat`: say what we do not know, without rejecting
# ---------------------------------------------------------------------------


def test_id_caveat_defaults_to_silence(example_registry: Registry) -> None:
    """Every country inherits `None` and its `reason` is unchanged, so the hook
    costs a country that does not want it exactly nothing (D-008)."""
    assert example_registry.id_caveat("12345678") is None
    ok = example_registry.validate("12345678")
    assert ok.valid is True
    assert ok.reason is not None and ok.reason.endswith("to find out.")
    assert ok.hint is None


def test_id_caveat_is_appended_to_reason_and_never_to_hint(example_registry: Registry) -> None:
    """D-021: a well-shaped identifier we cannot fully vouch for stays
    `valid=True` and says so in `reason`. `hint` stays `None` on success
    (D-010, restated by D-013), so the caveat may not go there.
    """

    class CaveatRegistry(type(example_registry)):  # type: ignore[misc]
        country = "XY"
        registry = "example-caveat"
        is_stub = True

        def id_caveat(self, id: str) -> str | None:
            if id.startswith("9"):
                return (
                    "Prefix '9' is not in the list this module knows as of 2026-09; "
                    "call lookup_company to confirm the number exists."
                )
            return None

    reg = CaveatRegistry()

    flagged = reg.validate("91234567")
    assert flagged.valid is True
    assert flagged.normalized == "91234567"
    assert flagged.reason is not None
    assert "2026-09" in flagged.reason and "lookup_company" in flagged.reason
    assert flagged.hint is None

    plain = reg.validate("12345678")
    assert plain.valid is True
    assert plain.reason is not None and "2026-09" not in plain.reason
    assert plain.hint is None


def test_id_caveat_never_fires_on_an_invalid_identifier(example_registry: Registry) -> None:
    """The hook takes an *already-valid, already-normalised* identifier, so the
    failure branch of `validate` is untouched and a caveat can never be mistaken
    for the reason something was rejected."""

    class AlwaysCaveat(type(example_registry)):  # type: ignore[misc]
        country = "XZ"
        registry = "example-always"
        is_stub = True

        def id_caveat(self, id: str) -> str | None:
            return "CAVEAT"

    bad = AlwaysCaveat().validate("nope")
    assert bad.valid is False
    assert bad.reason is not None and "CAVEAT" not in bad.reason
    assert bad.hint is not None
