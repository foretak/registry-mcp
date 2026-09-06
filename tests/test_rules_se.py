"""Swedish rules — ``registries/se/rules.py``.

Tests 1-78 of ``SWEDEN_SPEC.md`` §14 (sections A-E). Section D (status
derivation, 43-60) and part of section C (40-42) go through
``registries/se/mapping.py::map_entity`` on small constructed payloads,
matching ``tests/test_rules_gb.py``'s precedent (its own "status derivation"
section mixes ``derive_status`` and ``mapping.map_entity`` calls) — the test
descriptions are framed in terms of raw payload field values
(``avregistreringsdatum``, ``pagaende...Lista``, ``verksamOrganisation.kod``),
which is ``mapping.py``'s layer, not ``rules.py``'s.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from registry_mcp.core.models import CompanyReport, CompanyStatus, ErrorCode, RegistryError
from registry_mcp.registries.se import mapping
from registry_mcp.registries.se.rules import (
    AS_OF,
    DEADLINE_FORM_CODES,
    ORGANISATION_FORMS,
    deadlines_for,
    format_id,
    id_caveat,
    legal_form_info,
    modulus10_ok,
    rules_markdown,
    validate_id,
)

NBSP = " "


# ---------------------------------------------------------------------------
# Payload-building helpers for sections C (40-42) and D (43-60)
# ---------------------------------------------------------------------------


def _kod_klartext(kod: str | None, klartext: str | None = None) -> dict[str, Any] | None:
    if kod is None:
        return None
    return {"kod": kod, "klartext": klartext, "fel": None, "dataproducent": "Bolagsverket"}


def _org(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "organisationsidentitet": {
            "identitetsbeteckning": "5560160680",
            "typ": {"kod": "ORGANISATIONSNUMMER", "klartext": "Organisationsnummer"},
        },
        "namnskyddslopnummer": None,
        "organisationsnamn": {
            "organisationsnamnLista": [
                {
                    "namn": "Test AB",
                    "organisationsnamntyp": {"kod": "FORETAGSNAMN", "klartext": "Företagsnamn"},
                    "registreringsdatum": "2000-01-01",
                    "verksamhetsbeskrivningSarskiltForetagsnamn": None,
                }
            ],
            "fel": None,
            "dataproducent": "Bolagsverket",
        },
        "registreringsland": {"kod": "SE-LAND", "klartext": "Sverige"},
        "organisationsform": {
            "kod": "AB",
            "klartext": "Aktiebolag",
            "fel": None,
            "dataproducent": "Bolagsverket",
        },
        "avregistreradOrganisation": None,
        "avregistreringsorsak": None,
        "pagaendeAvvecklingsEllerOmstruktureringsforfarande": None,
        "juridiskForm": None,
        "verksamOrganisation": None,
        "reklamsparr": None,
        "organisationsdatum": None,
        "verksamhetsbeskrivning": None,
        "naringsgrenOrganisation": None,
        "postadressOrganisation": None,
    }
    base.update(overrides)
    return base


def _map(**overrides: Any) -> CompanyReport:
    body = {"organisationer": [_org(**overrides)]}
    return mapping.map_entity(body, "5560160680")


def _pagaende(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pagaendeAvvecklingsEllerOmstruktureringsforfarandeLista": items,
        "fel": None,
        "dataproducent": "Bolagsverket",
    }


# ---------------------------------------------------------------------------
# A. validate_id — normalisation and shape (1-22)
# ---------------------------------------------------------------------------


def test_01_canonical_unchanged() -> None:
    assert validate_id("5560160680") == "5560160680"


def test_02_hyphen_stripped() -> None:
    assert validate_id("556016-0680") == "5560160680"


def test_03_space_stripped_including_nbsp() -> None:
    assert validate_id("556016 0680") == "5560160680"
    assert validate_id(f"556016{NBSP}0680") == "5560160680"


def test_04_dot_stripped() -> None:
    assert validate_id("556016.0680") == "5560160680"


def test_05_vat_form_stripped() -> None:
    assert validate_id("SE556016068001") == "5560160680"


def test_06_vat_form_upper_cased_first() -> None:
    assert validate_id("se556016068001") == "5560160680"


def test_07_twelve_digits_preserved_not_truncated() -> None:
    """The single most important normalisation test in the file (§5.1)."""
    assert validate_id("194009272719") == "194009272719"


def test_08_personnummer_hyphen_stripped() -> None:
    assert validate_id("19400927-2719") == "194009272719"


def test_09_personnummer_over_100_plus_separator() -> None:
    assert validate_id("19400927+2719") == "194009272719"


def test_10_gd_nummer_accepted() -> None:
    assert validate_id("3021234567") == "3021234567"


def test_11_wrong_check_digit_accepted() -> None:
    """A wrong check digit is *not* a local rejection (§5.1.1). This test is
    the ruling."""
    assert validate_id("5560160681") == "5560160681"


def test_12_test_environment_allowlist_number_accepted() -> None:
    """One of the four numbers Bolagsverket's own test environment permits
    and modulus-10 refuses."""
    assert validate_id("5560000002") == "5560000002"


def test_13_empty_raises() -> None:
    with pytest.raises(RegistryError):
        validate_id("")


def test_14_nine_digits_raises_norway_hint() -> None:
    with pytest.raises(RegistryError) as excinfo:
        validate_id("923609016")
    assert "NO" in excinfo.value.hint
    assert "Norwegian" in excinfo.value.hint


def test_15_eleven_digits_raises() -> None:
    with pytest.raises(RegistryError):
        validate_id("55601606800")


def test_16_nine_digits_after_stripping_raises() -> None:
    with pytest.raises(RegistryError):
        validate_id("556016068")


def test_17_thirteen_digits_raises() -> None:
    with pytest.raises(RegistryError):
        validate_id("1940092727190")


def test_18_letters_not_se_prefix_raises() -> None:
    with pytest.raises(RegistryError):
        validate_id("55601606AB")


def test_19_se_plus_ten_digits_is_not_vat_form_raises() -> None:
    with pytest.raises(RegistryError) as excinfo:
        validate_id("SE5560160680")
    assert "VAT" in excinfo.value.hint


def test_20_impossible_month_raises() -> None:
    with pytest.raises(RegistryError):
        validate_id("197713012384")


def test_21_impossible_day_or_month_raises() -> None:
    with pytest.raises(RegistryError):
        validate_id("198100032384")


def test_22_invalid_error_has_code_and_hint() -> None:
    with pytest.raises(RegistryError) as excinfo:
        validate_id("923609016")
    assert excinfo.value.code is ErrorCode.INVALID_ID
    assert excinfo.value.hint


# ---------------------------------------------------------------------------
# B. format_id and id_caveat (23-30)
# ---------------------------------------------------------------------------


def test_23_format_organisationsnummer() -> None:
    assert format_id("5560160680") == "556016-0680"


def test_24_format_personnummer() -> None:
    assert format_id("194009272719") == "19400927-2719"


def test_25_format_unrecognised_width_is_none() -> None:
    assert format_id("55601") is None


def test_26_validate_personnummer_valid_with_caveat() -> None:
    from registry_mcp.core.registry import get_registry

    registry = get_registry("SE")
    result = registry.validate("194009272719")
    assert result.valid is True
    assert result.hint is None
    assert result.reason is not None
    assert "personnummer" in result.reason
    assert "several" in result.reason and "businesses" in result.reason


def test_27_validate_wrong_check_digit_caveat_content() -> None:
    from registry_mcp.core.registry import get_registry

    registry = get_registry("SE")
    result = registry.validate("5560160681")
    assert result.valid is True
    assert result.hint is None
    assert result.reason is not None
    assert "check digit" in result.reason
    assert "not been able to confirm" in result.reason
    assert AS_OF in result.reason
    assert "Bolagsverket" in result.reason


def test_28_validate_passing_check_digit_is_silent() -> None:
    """A passing unverified check is silent (§5.1.5)."""
    from registry_mcp.core.registry import get_registry

    registry = get_registry("SE")
    result = registry.validate("5560160680")
    assert result.valid is True
    assert result.reason is not None
    assert "check digit" not in result.reason


def test_29_validate_normalized_and_formatted() -> None:
    from registry_mcp.core.registry import get_registry

    registry = get_registry("SE")
    result = registry.validate("5560160680")
    assert result.normalized == "5560160680"
    assert result.formatted == "556016-0680"


def test_30_validate_never_raises() -> None:
    from registry_mcp.core.registry import get_registry

    registry = get_registry("SE")
    valid_inputs = [
        "5560160680",
        "556016-0680",
        "556016 0680",
        "556016.0680",
        "SE556016068001",
        "se556016068001",
        "194009272719",
        "19400927-2719",
        "19400927+2719",
        "3021234567",
        "5560160681",
        "5560000002",
    ]
    invalid_inputs = [
        "",
        "923609016",
        "55601606800",
        "556016068",
        "1940092727190",
        "55601606AB",
        "SE5560160680",
        "197713012384",
        "198100032384",
    ]
    for value in valid_inputs + invalid_inputs:
        result = registry.validate(value)
        if value in invalid_inputs:
            assert result.valid is False
            assert result.reason
            assert result.hint
        else:
            assert result.valid is True


# ---------------------------------------------------------------------------
# C. Legal-form mapping (31-42)
# ---------------------------------------------------------------------------


def test_31_ab() -> None:
    info = legal_form_info("AB")
    assert info.english == "Private or public limited company"
    assert info.limited_liability is True
    assert info.has_board_duty is True
    assert info.has_annual_accounts_duty is True
    assert "AB" in DEADLINE_FORM_CODES
    report = CompanyReport(
        country="SE",
        registry="bolagsverket",
        id="5560160680",
        name="T",
        legal_form_code="AB",
        status=CompanyStatus.ACTIVE,
        is_active=True,
    )
    assert deadlines_for(report, date(2026, 3, 1))


def test_32_ek() -> None:
    info = legal_form_info("EK")
    assert info.has_annual_accounts_duty is True
    assert "EK" in DEADLINE_FORM_CODES
    report = CompanyReport(
        country="SE",
        registry="bolagsverket",
        id="5560160680",
        name="T",
        legal_form_code="EK",
        status=CompanyStatus.ACTIVE,
        is_active=True,
    )
    assert deadlines_for(report, date(2026, 3, 1))


def test_33_e_sole_trader() -> None:
    info = legal_form_info("E")
    assert info.limited_liability is False
    assert info.has_annual_accounts_duty is None
    assert "E" not in DEADLINE_FORM_CODES


def test_34_hb_and_kb_not_limited() -> None:
    for code in ("HB", "KB"):
        info = legal_form_info(code)
        assert info.limited_liability is not True
        assert info.has_annual_accounts_duty is None
        assert code not in DEADLINE_FORM_CODES


def test_35_brf_no_computed_period() -> None:
    info = legal_form_info("BRF")
    assert info.english
    assert info.has_annual_accounts_duty is None
    assert "BRF" not in DEADLINE_FORM_CODES


def test_36_banks_and_insurers_no_computed_period() -> None:
    for code in ("BAB", "FAB", "SB"):
        info = legal_form_info(code)
        assert info.has_annual_accounts_duty is None
        assert code not in DEADLINE_FORM_CODES
        assert info.limited_liability is True


def test_37_filial_not_a_subunit() -> None:
    info = legal_form_info("FL")
    assert info.english
    report = _map(organisationsform=_kod_klartext("FL", "Filial"))
    assert report.is_subunit is False
    assert report.parent_id is None


def test_38_se_europabolag_not_confused_with_country() -> None:
    info = legal_form_info("SE")
    assert info.english is not None and "European company" in info.english
    report = _map(organisationsform=_kod_klartext("SE", "Europabolag"))
    assert report.country == "SE"
    assert report.legal_form_code == "SE"


def test_39_unclassified_form() -> None:
    info = legal_form_info("ZZZ")
    assert info.english is None
    assert info.limited_liability is None
    assert info.has_board_duty is None
    assert info.has_annual_accounts_duty is None
    assert info.notes
    report = _map(organisationsform=_kod_klartext("ZZZ", "Okänd"))
    assert report.legal_form is None
    assert report.limited_liability is None
    assert report.has_board_duty is None
    assert report.has_annual_accounts_duty is None
    assert any("ZZZ" in n for n in report.notes)


def test_40_scb_fallback_when_organisationsform_null() -> None:
    report = _map(
        organisationsform=None,
        juridiskForm=_kod_klartext("49", "Övriga aktiebolag"),
    )
    assert report.legal_form_code == "49"
    assert report.legal_form_local == "Övriga aktiebolag"
    assert any("Statistics Sweden" in n for n in report.notes)


def test_41_both_present_organisationsform_wins_no_n5() -> None:
    report = _map(
        organisationsform=_kod_klartext("AB", "Aktiebolag"),
        juridiskForm=_kod_klartext("49", "Övriga aktiebolag"),
    )
    assert report.legal_form_code == "AB"
    assert not any("Statistics Sweden" in n and "juridisk form" in n for n in report.notes)
    dumped = report.model_dump(mode="json")
    # `fetched_at` is `datetime.now(UTC)` and its digits are volatile — pop it
    # before the scan, or this assertion fails for the whole of minute :49 of
    # every hour and randomly whenever the microseconds contain "49" (T26e
    # fix 1). Keep the assertion itself: it is the right one.
    dumped.pop("fetched_at", None)
    assert "49" not in json_values(dumped)


def json_values(obj: Any) -> str:
    import json as _json

    return _json.dumps(obj, ensure_ascii=False)


def test_42_sector_fields_always_none() -> None:
    for report in (
        _map(),
        _map(organisationsform=None, juridiskForm=_kod_klartext("61", "Ideella föreningar")),
    ):
        assert report.sector_code is None
        assert report.sector is None


# ---------------------------------------------------------------------------
# D. Status derivation (43-60)
# ---------------------------------------------------------------------------


def test_43_healthy_active_no_status_note() -> None:
    report = _map(verksamOrganisation=_kod_klartext("JA"))
    assert report.status is CompanyStatus.ACTIVE
    assert report.is_active is True
    assert not any(
        keyword in n.lower()
        for n in report.notes
        for keyword in ("struck off", "konkurs", "likvidation", "does not classify", "bankrupt")
    )


def test_44_deregistered_verkupp() -> None:
    report = _map(
        avregistreradOrganisation={
            "avregistreringsdatum": "2001-03-15",
            "fel": None,
            "dataproducent": "Bolagsverket",
        },
        avregistreringsorsak=_kod_klartext("VERKUPP", "Verksamheten har upphört"),
    )
    assert report.status is CompanyStatus.DELETED
    assert report.deregistered_at == date(2001, 3, 15)
    assert report.is_active is False
    assert report.status_detail is not None and "VERKUPP" in report.status_detail


def test_45_deregistered_datetime_shaped_date() -> None:
    report = _map(
        avregistreradOrganisation={
            "avregistreringsdatum": "2023-05-05T00:00:00.000+00:00",
            "fel": None,
            "dataproducent": "Bolagsverket",
        },
        avregistreringsorsak=_kod_klartext("LIAV", "Likvidation"),
    )
    assert report.deregistered_at == date(2023, 5, 5)


def test_46_deregistered_arseed_renders_klartext() -> None:
    report = _map(
        avregistreradOrganisation={
            "avregistreringsdatum": "2020-01-01",
            "fel": None,
            "dataproducent": "Bolagsverket",
        },
        avregistreringsorsak=_kod_klartext("ARSEED", "Årsredovisning saknas"),
    )
    assert report.status is CompanyStatus.DELETED
    assert report.status_detail is not None and "Årsredovisning saknas" in report.status_detail


def test_47_unrecognised_deregistration_reason_still_deleted() -> None:
    report = _map(
        avregistreradOrganisation={
            "avregistreringsdatum": "2020-01-01",
            "fel": None,
            "dataproducent": "Bolagsverket",
        },
        avregistreringsorsak=_kod_klartext("QQQQ", "Ett nytt skäl"),
    )
    assert report.status is CompanyStatus.DELETED
    assert report.status_detail is not None and "QQQQ" in report.status_detail


def test_48_kk_sets_bankruptcy_date() -> None:
    report = _map(
        pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende(
            [{"kod": "KK", "klartext": "Konkurs", "fromDatum": "2024-01-26"}]
        )
    )
    assert report.status is CompanyStatus.BANKRUPT
    assert report.bankruptcy_date == date(2024, 1, 26)
    assert report.is_active is False


def test_49_kk_datetime_shaped_date() -> None:
    report = _map(
        pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende(
            [{"kod": "KK", "klartext": "Konkurs", "fromDatum": "2024-01-26T00:00:00.000+00:00"}]
        )
    )
    assert report.bankruptcy_date == date(2024, 1, 26)


def test_50_li_no_voluntary_distinction() -> None:
    report = _map(
        pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende(
            [{"kod": "LI", "klartext": "Likvidation"}]
        )
    )
    assert report.status is CompanyStatus.UNDER_LIQUIDATION
    assert report.bankruptcy_date is None
    assert report.status_detail is not None
    assert "voluntary" in report.status_detail.lower()
    assert "compulsory" in report.status_detail.lower()


def test_51_kk_beats_li_regardless_of_order() -> None:
    for items in (
        [{"kod": "KK"}, {"kod": "LI"}],
        [{"kod": "LI"}, {"kod": "KK"}],
    ):
        report = _map(pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende(items))
        assert report.status is CompanyStatus.BANKRUPT


def test_52_fr_is_distress_not_bankruptcy() -> None:
    report = _map(
        pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende(
            [{"kod": "FR", "klartext": "Företagsrekonstruktion"}]
        )
    )
    # Negative assertion first (T26e fix 2a): asserting `is CompanyStatus.
    # UNDER_LIQUIDATION` first narrows `report.status` to that literal for
    # mypy, making the `is not BANKRUPT` check below a non-overlapping
    # identity comparison — `mypy --strict` (which `mypy .` runs, unlike
    # `mypy src`) flags it. Order matters here for the type checker, not
    # just the reader.
    assert report.status is not CompanyStatus.BANKRUPT
    assert report.status is CompanyStatus.UNDER_LIQUIDATION
    assert report.status_detail is not None and "not bankruptcy" in report.status_detail.lower()


def test_53_ac_and_res_under_liquidation() -> None:
    for kod in ("AC", "RES"):
        report = _map(pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende([{"kod": kod}]))
        assert report.status is CompanyStatus.UNDER_LIQUIDATION


def test_54_fuol_vs_fuot_false_alarm() -> None:
    fuol = _map(pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende([{"kod": "FUOL"}]))
    assert fuol.status is CompanyStatus.UNDER_LIQUIDATION

    fuot = _map(pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende([{"kod": "FUOT"}]))
    assert fuot.status is CompanyStatus.ACTIVE
    assert fuot.is_active is True
    assert any("acquiring" in n.lower() or "fusion" in n.lower() for n in fuot.notes)


def test_55_deot_vs_deol() -> None:
    deot = _map(pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende([{"kod": "DEOT"}]))
    assert deot.status is CompanyStatus.ACTIVE
    assert any("delning" in n.lower() or "division" in n.lower() for n in deot.notes)

    deol = _map(pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende([{"kod": "DEOL"}]))
    assert deol.status is CompanyStatus.UNDER_LIQUIDATION


def test_56_unrecognised_procedure_code_is_unknown() -> None:
    report = _map(
        pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende(
            [{"kod": "XYZ", "klartext": "Något nytt"}]
        )
    )
    assert report.status is CompanyStatus.UNKNOWN
    assert report.is_active is False
    assert any("XYZ" in n and "Något nytt" in n for n in report.notes)


def test_57_deregistered_and_kk_deleted_wins_bankruptcy_date_kept() -> None:
    report = _map(
        avregistreradOrganisation={
            "avregistreringsdatum": "2024-06-01",
            "fel": None,
            "dataproducent": "Bolagsverket",
        },
        avregistreringsorsak=_kod_klartext("KKAV", "Konkurs"),
        pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende(
            [{"kod": "KK", "fromDatum": "2024-01-26"}]
        ),
    )
    assert report.status is CompanyStatus.DELETED
    assert report.bankruptcy_date == date(2024, 1, 26)


def test_58_verksam_nej_stays_active_with_n3() -> None:
    """The D-035 test."""
    report = _map(verksamOrganisation=_kod_klartext("NEJ"))
    assert report.status is CompanyStatus.ACTIVE
    assert report.is_active is True
    assert any("Statistics Sweden" in n for n in report.notes)


def test_59_verksam_absent_no_n3() -> None:
    report = _map(verksamOrganisation=None)
    assert report.status is CompanyStatus.ACTIVE
    assert not any("economically active" in n for n in report.notes)


def test_60_kkav_reason_never_sets_bankruptcy_date() -> None:
    report = _map(
        avregistreradOrganisation={
            "avregistreringsdatum": "2020-01-01",
            "fel": None,
            "dataproducent": "Bolagsverket",
        },
        avregistreringsorsak=_kod_klartext("KKAV", "Konkurs"),
    )
    assert report.status is CompanyStatus.DELETED
    assert report.bankruptcy_date is None


# ---------------------------------------------------------------------------
# E. Deadlines (61-78)
# ---------------------------------------------------------------------------


def _report(
    *, legal_form_code: str = "AB", status: CompanyStatus = CompanyStatus.ACTIVE
) -> CompanyReport:
    return CompanyReport(
        country="SE",
        registry="bolagsverket",
        id="5560160680",
        name="Test AB",
        legal_form_code=legal_form_code,
        status=status,
        is_active=(status is CompanyStatus.ACTIVE),
    )


def _by_kind(deadlines: list[Any], kind: str) -> Any:
    matches = [d for d in deadlines if d.kind == kind]
    assert len(matches) == 1, f"expected exactly one {kind!r}, got {len(matches)}: {deadlines}"
    return matches[0]


def test_61_both_deadlines_this_year() -> None:
    deadlines = deadlines_for(_report(), date(2026, 3, 1))
    assert len(deadlines) == 2
    assert _by_kind(deadlines, "general_meeting").due_date == date(2026, 6, 30)
    assert _by_kind(deadlines, "annual_accounts").due_date == date(2026, 7, 31)


def test_62_general_meeting_rolls_to_next_year_sorted_by_due_date() -> None:
    deadlines = deadlines_for(_report(), date(2026, 7, 1))
    assert _by_kind(deadlines, "general_meeting").due_date == date(2027, 6, 30)
    assert _by_kind(deadlines, "annual_accounts").due_date == date(2026, 7, 31)
    assert deadlines[0].kind == "annual_accounts"


def test_63_both_next_year() -> None:
    deadlines = deadlines_for(_report(), date(2026, 8, 1))
    assert _by_kind(deadlines, "general_meeting").due_date == date(2027, 6, 30)
    assert _by_kind(deadlines, "annual_accounts").due_date == date(2027, 7, 31)


def test_64_due_on_today_is_not_past() -> None:
    deadlines = deadlines_for(_report(), date(2026, 6, 30))
    gm = _by_kind(deadlines, "general_meeting")
    assert gm.due_date == date(2026, 6, 30)
    assert gm.days_until == 0


def test_65_statutory_equals_due_even_on_saturday() -> None:
    assert date(2027, 7, 31).weekday() == 5  # Saturday
    deadlines = deadlines_for(_report(), date(2026, 8, 1))
    for d in deadlines:
        assert d.statutory_date == d.due_date
        assert d.rolled_forward is False
    assert _by_kind(deadlines, "annual_accounts").due_date == date(2027, 7, 31)


def test_66_no_holiday_table_never_calls_roll_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    import registry_mcp.registries.se as se_pkg

    se_dir = Path(se_pkg.__file__).parent
    assert not (se_dir / "holidays.py").exists()

    from registry_mcp.core.rules import common as rules_common

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("roll_forward must never be called for SE")

    monkeypatch.setattr(rules_common, "roll_forward", _boom)
    deadlines = deadlines_for(_report(), date(2026, 3, 1))
    assert deadlines

    for path in se_dir.glob("*.py"):
        assert "roll_forward" not in path.read_text(encoding="utf-8"), path


def test_67_annual_accounts_applies_because_content() -> None:
    aa = _by_kind(deadlines_for(_report(), date(2026, 3, 1)), "annual_accounts")
    text = aa.applies_because
    assert "8 kap. 6 §" in text
    assert "seven months" in text or "sju månader" in text
    assert "7 500" in text
    assert "15 000" in text
    assert "may be earlier" in text


def test_68_general_meeting_applies_because_content() -> None:
    gm = _by_kind(deadlines_for(_report(), date(2026, 3, 1)), "general_meeting")
    assert "7 kap. 10 §" in gm.applies_because
    assert "six months" in gm.applies_because


def test_69_annual_accounts_does_not_attribute_seven_months_to_8_3() -> None:
    """This test exists because the project's own library file said
    otherwise (§5.4.1)."""
    aa = _by_kind(deadlines_for(_report(), date(2026, 3, 1)), "annual_accounts")
    text = aa.applies_because
    assert "one month" in text
    idx = text.find("8 kap. 3")
    assert idx != -1
    # The seven-month figure is anchored to 8 kap. 6 §, not 8 kap. 3 §.
    window = text[max(0, idx - 80) : idx + 80]
    assert "seven months" not in window


def test_70_ek_gets_annual_accounts_only() -> None:
    deadlines = deadlines_for(_report(legal_form_code="EK"), date(2026, 3, 1))
    kinds = {d.kind for d in deadlines}
    assert kinds == {"annual_accounts"}


def test_71_sole_trader_no_deadlines_with_n8_and_n14() -> None:
    """N14 added 2026-09-06, T26e fix 5 — before that this test passed on N8
    alone."""
    report = _map(organisationsform=_kod_klartext("E", "Enskild näringsverksamhet"))
    assert deadlines_for(report, date(2026, 3, 1)) == []
    assert any("sole trader" in n.lower() for n in report.notes), report.notes  # N8
    assert any(
        "no primary source for them has been read" in n for n in report.notes
    ), report.notes  # N14


def test_72_brf_no_deadlines_and_n14() -> None:
    """The note is the assertion, not an incidental (§7.3, N14)."""
    report = _map(organisationsform=_kod_klartext("BRF", "Bostadsrättsförening"))
    assert deadlines_for(report, date(2026, 3, 1)) == []
    assert any(
        "no primary source for them has been read" in n for n in report.notes
    ), report.notes


def test_73_unclassified_form_no_deadlines_and_n6() -> None:
    report = _map(organisationsform=_kod_klartext("ZZZ", "Okänd"))
    assert deadlines_for(report, date(2026, 3, 1)) == []
    assert any("ZZZ" in n for n in report.notes)


def test_74_bankrupt_no_deadlines_note_cites_8_7() -> None:
    """T26e fix 9: assert the 8 kap. 7 § sentence on a real, mapped report —
    not only via the direct `deadline_exemption_note` call, which is kept
    below because the wiring being correct is worth pinning on its own."""
    report = _map(
        pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende(
            [{"kod": "KK", "fromDatum": "2024-01-26"}]
        )
    )
    assert deadlines_for(report, date(2026, 3, 1)) == []
    assert any("8 kap. 7 §" in n for n in report.notes), report.notes

    from registry_mcp.registries.se.rules import deadline_exemption_note

    note = deadline_exemption_note(CompanyStatus.BANKRUPT, "KK")
    assert note is not None and "8 kap. 7 §" in note


def test_75_deleted_no_deadlines_plus_note() -> None:
    report = _map(
        avregistreradOrganisation={
            "avregistreringsdatum": "2020-01-01",
            "fel": None,
            "dataproducent": "Bolagsverket",
        },
        avregistreringsorsak=_kod_klartext("AVREG", "Avregistrerad"),
    )
    assert deadlines_for(report, date(2026, 3, 1)) == []
    assert any("no filing deadlines are given" in n or "Struck off" in n for n in report.notes)


def test_76_under_liquidation_no_deadlines_plus_note() -> None:
    """Sweden follows GB, not NO."""
    report = _map(pagaendeAvvecklingsEllerOmstruktureringsforfarande=_pagaende([{"kod": "LI"}]))
    assert deadlines_for(report, date(2026, 3, 1)) == []
    assert any("no filing deadlines are given" in n for n in report.notes)


def test_77_dormant_still_gets_both_deadlines() -> None:
    """The dormancy flag never suppresses a duty (§5.4.5)."""
    report = _map(verksamOrganisation=_kod_klartext("NEJ"))
    deadlines = deadlines_for(report, date(2026, 3, 1))
    assert {d.kind for d in deadlines} == {"general_meeting", "annual_accounts"}


def test_78_shape_and_purity(monkeypatch: pytest.MonkeyPatch) -> None:
    today = date(2026, 3, 1)
    first = deadlines_for(_report(), today)
    second = deadlines_for(_report(), today)
    assert first == second
    for d in first:
        assert d.country == "SE"
        assert d.registry == "bolagsverket"
        assert d.applies_because
        assert d.source_url and "lagen.nu" in d.source_url
        assert d.days_until == (d.due_date - today).days

    # T26e fix 10: the result does not change with the process timezone
    # either — structurally true, since `deadlines_for` takes `today` as a
    # parameter and reads no clock at all, but this closes the numbered test
    # rather than leaving it unpinned.
    import os
    import time

    if hasattr(time, "tzset"):
        original_tz = os.environ.get("TZ")
        try:
            monkeypatch.setenv("TZ", "America/New_York")
            time.tzset()
            new_york = deadlines_for(_report(), today)

            monkeypatch.setenv("TZ", "Australia/Sydney")
            time.tzset()
            sydney = deadlines_for(_report(), today)

            assert new_york == sydney == first
        finally:
            if original_tz is None:
                monkeypatch.delenv("TZ", raising=False)
            else:
                monkeypatch.setenv("TZ", original_tz)
            time.tzset()


# ---------------------------------------------------------------------------
# rules_markdown() and small supplementary checks
# ---------------------------------------------------------------------------


def test_rules_markdown_covers_required_points() -> None:
    text = rules_markdown()
    lowered = text.lower()
    assert "no name search" in lowered or "cannot search by" in lowered
    assert "check digit" in lowered
    assert "personnummer" in lowered
    assert "8 kap. 6 §" in text
    assert "7 kap. 10 §" in text
    assert "verksam" in lowered
    assert "juridiskform" in lowered.replace(" ", "") or "juridisk form" in lowered
    assert "weekend" in lowered or "holiday" in lowered


def test_organisation_forms_table_has_no_duplicate_keys() -> None:
    assert len(ORGANISATION_FORMS) == len(set(ORGANISATION_FORMS))


def test_modulus10_ok_matches_the_spec_table() -> None:
    passing = [
        "5560021361",
        "9124001992",
        "7164099017",
        "7020008350",
        "5567223705",
        "5561890038",
        "5562820745",
        "5560986878",
        "5299999994",
        "5560160680",
        "5560125790",
        "5560427220",
    ]
    for number in passing:
        assert modulus10_ok(number) is True, number
    for number in ("5560000002", "7140000001", "9160000001"):
        assert modulus10_ok(number) is False, number
    assert modulus10_ok("198101032384"[2:]) is True
    assert modulus10_ok("198101052382"[2:]) is True
    assert modulus10_ok("193403223328"[2:]) is True
    assert modulus10_ok("198210300002"[2:]) is False


def test_id_caveat_none_for_ten_digit_gd_nummer_when_check_passes() -> None:
    # A ten-digit GD-nummer is checked exactly like an organisationsnummer.
    assert id_caveat("5560160680") is None


# ---------------------------------------------------------------------------
# advertising_protected — reklamsparr -> the field (D-026(b), D-036), 122-125
# ---------------------------------------------------------------------------


def test_122_reklamsparr_ja_sets_advertising_protected_true_and_n4() -> None:
    report = _map(reklamsparr=_kod_klartext("JA"))
    assert report.advertising_protected is True
    assert any("reklamspärr" in n.lower() for n in report.notes)


def test_123_reklamsparr_nej_sets_advertising_protected_false_and_no_n4() -> None:
    report = _map(reklamsparr=_kod_klartext("NEJ"))
    assert report.advertising_protected is False
    assert not any("reklamspärr" in n.lower() for n in report.notes)


def test_124_reklamsparr_absent_is_advertising_protected_none() -> None:
    report = _map(reklamsparr=None)
    assert report.advertising_protected is None
    assert not any("reklamspärr" in n.lower() for n in report.notes)


def test_125_reklamsparr_blocked_by_fel_is_advertising_protected_none() -> None:
    """SWEDEN_SPEC.md §14 test 125: blocked by `fel` -> `None`, and N13 names
    the data producer that could not answer (here, SCB)."""
    report = _map(
        reklamsparr={
            "kod": None,
            "klartext": None,
            "fel": {"typ": "OTILLGANGLIG_UPPGIFTSKALLA"},
            "dataproducent": "SCB",
        }
    )
    assert report.advertising_protected is None
    assert not any("reklamspärr" in n.lower() for n in report.notes)
    assert any("could not be retrieved" in n and "SCB" in n for n in report.notes)
