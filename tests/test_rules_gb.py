"""UK rules — ``registries/gb/rules.py``.

Tests 1-72 of ``UK_SPEC.md`` §14 (sections A-D). Every date below was read out
of a saved fixture (``tests/fixtures/ch_*.json``) or computed against the real
calendar; if an implementation disagrees, the implementation is wrong.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from registry_mcp.core.models import (
    CompanyReport,
    CompanyStatus,
    Deadline,
    ErrorCode,
    RegistryError,
)
from registry_mcp.core.rules import common as rules_common
from registry_mcp.registries.gb import mapping
from registry_mcp.registries.gb.rules import (
    COMPANY_TYPES,
    deadline_exemption_note,
    deadlines_for,
    derive_status,
    legal_form_info,
    rules_markdown,
    validate_crn,
)

FIXTURES = Path(__file__).parent / "fixtures"


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
AMICUS = _load("ch_13948759.json")


def _report(
    *,
    legal_form_code: str | None = "ltd",
    status: CompanyStatus = CompanyStatus.ACTIVE,
    is_subunit: bool = False,
    id: str = "00445790",
) -> CompanyReport:
    return CompanyReport(
        country="GB",
        registry="companies-house",
        id=id,
        name="TEST LTD",
        legal_form_code=legal_form_code,
        status=status,
        is_active=(status is CompanyStatus.ACTIVE),
        is_subunit=is_subunit,
    )


def _by_kind(deadlines: list[Deadline], kind: str) -> Deadline:
    matches = [d for d in deadlines if d.kind == kind]
    assert len(matches) == 1, f"expected exactly one {kind!r}, got {len(matches)}: {deadlines}"
    return matches[0]


# ---------------------------------------------------------------------------
# A. validate_crn — normalisation and shape (1-25)
# ---------------------------------------------------------------------------


def test_01_canonical_digit_number_unchanged() -> None:
    assert validate_crn("00445790") == "00445790"


def test_02_00000006_unchanged() -> None:
    assert validate_crn("00000006") == "00000006"


def test_03_zero_padded_from_six_digits() -> None:
    assert validate_crn("445790") == "00445790"


def test_04_zero_padded_from_four_digits() -> None:
    assert validate_crn("1234") == "00001234"


def test_05_zero_padded_from_one_digit() -> None:
    assert validate_crn("6") == "00000006"


def test_06_strips_spaces() -> None:
    assert validate_crn("00 445 790") == "00445790"


def test_07_strips_hyphens() -> None:
    assert validate_crn("0044-5790") == "00445790"


def test_08_strips_dots() -> None:
    assert validate_crn("00.445.790") == "00445790"


def test_09_upper_cases() -> None:
    assert validate_crn("sc090312") == "SC090312"


def test_10_prefix_digits_padded_to_fill_eight() -> None:
    assert validate_crn("SC12345") == "SC012345"


def test_11_prefix_single_digit_padded() -> None:
    assert validate_crn("SC1") == "SC000001"


def test_12_ni_prefix_padded() -> None:
    assert validate_crn("NI1234") == "NI001234"


def test_13_oc_prefix_lower_case() -> None:
    assert validate_crn("oc303675") == "OC303675"


def test_14_r0_single_letter_prefix_unchanged() -> None:
    assert validate_crn("R0123456") == "R0123456"


def test_15_br_establishment_unchanged() -> None:
    assert validate_crn("BR012345") == "BR012345"


def test_16_prefix_newer_than_table_accepted() -> None:
    assert validate_crn("OE123456") == "OE123456"


def test_17_empty_raises() -> None:
    with pytest.raises(RegistryError):
        validate_crn("")


def test_18_nine_digits_never_truncated_raises() -> None:
    with pytest.raises(RegistryError):
        validate_crn("123456789")


def test_19_nine_characters_prefix_raises() -> None:
    with pytest.raises(RegistryError):
        validate_crn("SC1234567")


def test_20_eight_letters_no_digit_raises() -> None:
    with pytest.raises(RegistryError):
        validate_crn("ABCDEFGH")


def test_21_starts_with_digit_not_all_digits_raises() -> None:
    with pytest.raises(RegistryError):
        validate_crn("1SC12345")


def test_22_stray_symbol_survives_stripping_raises() -> None:
    with pytest.raises(RegistryError):
        validate_crn("SC12#456")


def test_23_vat_number_shape_raises_with_vat_hint() -> None:
    with pytest.raises(RegistryError) as excinfo:
        validate_crn("GB123456789")
    assert "VAT" in excinfo.value.hint


def test_24_invalid_error_has_code_hint_and_search_company() -> None:
    with pytest.raises(RegistryError) as excinfo:
        validate_crn("123456789")
    err = excinfo.value
    assert err.code is ErrorCode.INVALID_ID
    assert err.hint
    assert "search_company" in err.hint


def test_25_unknown_prefix_accepted() -> None:
    assert validate_crn("QQ000001") == "QQ000001"


# ---------------------------------------------------------------------------
# B. Legal-form mapping (26-36)
# ---------------------------------------------------------------------------


def test_26_ltd() -> None:
    info = legal_form_info("ltd")
    assert info.english == "Private limited company"
    assert info.limited_liability is True
    assert info.has_board_duty is True
    assert info.has_annual_accounts_duty is True
    assert info.accounts_period == ("private", 9)


def test_27_plc_six_months() -> None:
    info = legal_form_info("plc")
    assert info.has_annual_accounts_duty is True
    assert info.accounts_period == ("public", 6)


def test_28_llp() -> None:
    info = legal_form_info("llp")
    assert info.limited_liability is True
    assert info.has_board_duty is None
    assert info.has_annual_accounts_duty is True
    assert info.accounts_period == ("private", 9)


def test_29_private_unlimited_nsc() -> None:
    info = legal_form_info("private-unlimited-nsc")
    assert info.limited_liability is False
    assert info.has_annual_accounts_duty is None
    assert info.accounts_period is None


def test_30_uk_establishment() -> None:
    info = legal_form_info("uk-establishment")
    assert info.has_annual_accounts_duty is False
    report = mapping.map_entity(BR_ESTABLISHMENT)
    assert report.is_subunit is True


def test_31_limited_partnership() -> None:
    info = legal_form_info("limited-partnership")
    assert info.limited_liability is not True
    assert info.has_annual_accounts_duty is None


def test_32_cio_no_computed_period() -> None:
    info = legal_form_info("charitable-incorporated-organisation")
    assert info.has_annual_accounts_duty is None
    assert info.accounts_period is None


def test_33_overseas_forms_no_accounts_duty() -> None:
    for code in ("oversea-company", "registered-overseas-entity"):
        assert legal_form_info(code).has_annual_accounts_duty is None


def test_34_royal_charter_all_none() -> None:
    info = legal_form_info("royal-charter")
    assert info.limited_liability is None
    assert info.has_board_duty is None
    assert info.has_annual_accounts_duty is None


def test_35_unclassified_form() -> None:
    info = legal_form_info("not-a-real-type")
    assert info.english is None
    assert info.limited_liability is None
    assert info.has_board_duty is None
    assert info.has_annual_accounts_duty is None
    assert info.notes


def test_36_cic_subtype_does_not_overwrite_type() -> None:
    info = legal_form_info("ltd", "community-interest-company")
    assert info.code == "ltd"
    assert info.english is not None
    assert "community interest company" in info.english
    assert any("CIC34" in note for note in info.notes)


# ---------------------------------------------------------------------------
# C. Status derivation (37-50)
# ---------------------------------------------------------------------------


def test_37_active() -> None:
    result = derive_status(company_status="active")
    assert result.status is CompanyStatus.ACTIVE
    assert result.is_active is True
    assert result.notes == []


def test_38_dissolved_with_date() -> None:
    result = derive_status(company_status="dissolved", date_of_cessation=date(2018, 7, 10))
    assert result.status is CompanyStatus.DISSOLVED
    assert result.is_active is False
    assert "2018-07-10" in result.status_detail


def test_39_liquidation_says_no_voluntary_distinction() -> None:
    result = derive_status(company_status="liquidation")
    assert result.status is CompanyStatus.UNDER_LIQUIDATION
    assert "voluntary" in result.status_detail.lower()


def test_40_administration_not_compulsory_liquidation() -> None:
    # UNDER_LIQUIDATION is itself never UNDER_COMPULSORY_LIQUIDATION — the
    # point of this test is that "administration" maps to the *former*, not
    # the (never emitted for GB) latter.
    result = derive_status(company_status="administration")
    assert result.status is CompanyStatus.UNDER_LIQUIDATION


def test_41_receivership_and_voluntary_arrangement() -> None:
    for value in ("receivership", "voluntary-arrangement"):
        assert derive_status(company_status=value).status is CompanyStatus.UNDER_LIQUIDATION


def test_42_removed_is_deleted() -> None:
    assert derive_status(company_status="removed").status is CompanyStatus.DELETED


def test_43_converted_closed_is_dissolved() -> None:
    assert derive_status(company_status="converted-closed").status is CompanyStatus.DISSOLVED


def test_44_no_status_key_is_unknown() -> None:
    result = derive_status(company_status=None)
    assert result.status is CompanyStatus.UNKNOWN
    assert result.status_detail


def test_45_unrecognised_status_is_unknown_with_raw_value() -> None:
    result = derive_status(company_status="wibble")
    assert result.status is CompanyStatus.UNKNOWN
    assert "wibble" in result.status_detail


def test_46_active_with_insolvency_history_stays_active_never_bankrupt() -> None:
    # ACTIVE and UNDER_LIQUIDATION (LIQUIDATION's own status, asserted
    # elsewhere) are themselves never BANKRUPT — GB never emits that status.
    data = dict(TESCO)
    data["has_insolvency_history"] = True
    active_report = mapping.map_entity(data)
    assert active_report.status is CompanyStatus.ACTIVE
    assert any("insolvency" in n.lower() for n in active_report.notes)


def test_47_active_proposal_to_strike_off_stays_active() -> None:
    result = derive_status(company_status="active", company_status_detail="active-proposal-to-strike-off")
    assert result.status is CompanyStatus.ACTIVE
    assert result.is_active is True
    assert any("strike" in n.lower() for n in result.notes)


def test_48_registered_office_in_dispute_note() -> None:
    data = dict(TESCO)
    data["registered_office_is_in_dispute"] = True
    report = mapping.map_entity(data)
    assert any("disputed" in n.lower() for n in report.notes)


def test_49_undeliverable_registered_office_note() -> None:
    data = dict(TESCO)
    data["undeliverable_registered_office_address"] = True
    report = mapping.map_entity(data)
    assert any("cannot deliver" in n.lower() for n in report.notes)


def test_50_any_non_active_status_adds_a_note() -> None:
    for value in ("dissolved", "liquidation", "removed", "converted-closed", "wibble"):
        result = derive_status(company_status=value, date_of_cessation=date(2020, 1, 1))
        assert result.notes


# ---------------------------------------------------------------------------
# D. Deadlines (51-72)
# ---------------------------------------------------------------------------


def test_51_published_accounts_due_date_wins() -> None:
    report = mapping.map_entity(MONZO)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    accounts = _by_kind(deadlines, "annual_accounts")
    assert accounts.due_date == date(2027, 12, 31)
    assert "register's own figure" in accounts.applies_because


def test_52_deprecated_next_due_field_is_second_rung() -> None:
    data = json.loads(json.dumps(MONZO))
    del data["accounts"]["next_accounts"]["due_on"]
    report = mapping.map_entity(data)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    accounts = _by_kind(deadlines, "annual_accounts")
    assert accounts.due_date == date(2027, 12, 31)


def test_53_computed_from_period_end_on_ltd_nine_months() -> None:
    data = json.loads(json.dumps(MONZO))
    del data["accounts"]["next_accounts"]["due_on"]
    del data["accounts"]["next_due"]
    report = mapping.map_entity(data)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    accounts = _by_kind(deadlines, "annual_accounts")
    assert accounts.due_date == date(2027, 12, 31)
    assert "Computed" in accounts.applies_because


def test_54_computed_llp_month_end_clamp() -> None:
    data = json.loads(json.dumps(DELOITTE))
    del data["accounts"]["next_accounts"]["due_on"]
    del data["accounts"]["next_due"]
    report = mapping.map_entity(data)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    accounts = _by_kind(deadlines, "annual_accounts")
    assert accounts.due_date == date(2027, 2, 28)


def test_55_computed_plc_six_months_uses_period_end_not_ard() -> None:
    data = json.loads(json.dumps(TESCO))
    del data["accounts"]["next_accounts"]["due_on"]
    del data["accounts"]["next_due"]
    report = mapping.map_entity(data)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    accounts = _by_kind(deadlines, "annual_accounts")
    assert accounts.due_date == date(2027, 8, 26)


def test_56_computed_plc_natwest() -> None:
    data = json.loads(json.dumps(NATWEST))
    del data["accounts"]["next_accounts"]["due_on"]
    del data["accounts"]["next_due"]
    report = mapping.map_entity(data)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    accounts = _by_kind(deadlines, "annual_accounts")
    assert accounts.due_date == date(2027, 6, 30)


def test_57_computed_guarantee_form_is_private_nine_months() -> None:
    data = json.loads(json.dumps(AMICUS))
    del data["accounts"]["next_accounts"]["due_on"]
    del data["accounts"]["next_due"]
    report = mapping.map_entity(data)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    accounts = _by_kind(deadlines, "annual_accounts")
    assert accounts.due_date == date(2027, 12, 31)


def test_58_oversea_company_no_period_no_deadline() -> None:
    report = mapping.map_entity(OVERSEAS)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    assert all(d.kind != "annual_accounts" for d in deadlines)
    assert any("no accounts-filing period" in n for n in report.notes)


def test_59_published_confirmation_due_date_wins() -> None:
    report = mapping.map_entity(TESCO)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    cs = _by_kind(deadlines, "confirmation_statement")
    assert cs.due_date == date(2027, 7, 2)


def test_60_computed_confirmation_plus_fourteen_days() -> None:
    data = json.loads(json.dumps(TESCO))
    del data["confirmation_statement"]["next_due"]
    report = mapping.map_entity(data)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    cs = _by_kind(deadlines, "confirmation_statement")
    assert cs.due_date == date(2027, 7, 2)


def test_61_computed_confirmation_deloitte() -> None:
    data = json.loads(json.dumps(DELOITTE))
    del data["confirmation_statement"]["next_due"]
    report = mapping.map_entity(data)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    cs = _by_kind(deadlines, "confirmation_statement")
    assert cs.due_date == date(2026, 8, 14)


def test_62_statutory_date_equals_due_date_even_on_sunday() -> None:
    data = json.loads(json.dumps(TESCO))
    data["confirmation_statement"]["next_due"] = "2027-01-31"  # a Sunday
    report = mapping.map_entity(data)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    for d in deadlines:
        assert d.statutory_date == d.due_date
        assert d.rolled_forward is False
    cs = _by_kind(deadlines, "confirmation_statement")
    assert cs.due_date == date(2027, 1, 31)


def test_63_negative_days_until_is_valid() -> None:
    data = json.loads(json.dumps(DELOITTE))
    report = mapping.map_entity(data)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    cs = _by_kind(deadlines, "confirmation_statement")
    assert cs.due_date == date(2026, 8, 14)
    assert cs.days_until == -21


def test_64_overdue_disagreement_is_recorded() -> None:
    data = json.loads(json.dumps(TESCO))
    data["confirmation_statement"]["overdue"] = True
    report = mapping.map_entity(data)
    deadlines = deadlines_for(report, date(2026, 1, 1))  # well before due_date
    cs = _by_kind(deadlines, "confirmation_statement")
    assert cs.days_until is not None and cs.days_until >= 0
    assert "overdue" in cs.applies_because.lower()
    assert "not yet past" in cs.applies_because


def test_65_dissolved_gets_no_deadlines_even_with_published_dates() -> None:
    data = json.loads(json.dumps(DISSOLVED))
    data["accounts"] = {"next_accounts": {"due_on": "2099-01-01"}}
    report = mapping.map_entity(data)
    assert report.status is CompanyStatus.DISSOLVED
    deadlines = deadlines_for(report, date(2026, 9, 4))
    assert deadlines == []


def test_66_liquidation_gets_no_deadlines() -> None:
    report = mapping.map_entity(LIQUIDATION)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    assert deadlines == []


def test_67_uk_establishment_gets_no_deadlines_and_names_parent() -> None:
    report = mapping.map_entity(BR_ESTABLISHMENT)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    assert deadlines == []
    assert any("parent_id" in n for n in report.notes)


def test_68_unclassified_form_gets_no_deadlines_despite_both_dates() -> None:
    data = json.loads(json.dumps(MONZO))
    data["type"] = "not-a-real-type"
    report = mapping.map_entity(data)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    assert deadlines == []


def test_69_sorted_by_due_date_then_kind_one_per_kind() -> None:
    report = mapping.map_entity(TESCO)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    kinds = [d.kind for d in deadlines]
    assert len(kinds) == len(set(kinds))
    assert deadlines == sorted(deadlines, key=lambda d: (d.due_date, d.kind))


def test_70_every_deadline_shape() -> None:
    report = mapping.map_entity(TESCO)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    assert deadlines
    for d in deadlines:
        assert d.country == "GB"
        assert d.registry == "companies-house"
        assert d.applies_because
        assert d.source_url and "gov.uk" in d.source_url
        assert d.days_until == (d.due_date - date(2026, 9, 4)).days


def test_71_pure_no_clock_reads() -> None:
    report = mapping.map_entity(TESCO)
    first = deadlines_for(report, date(2026, 9, 4))
    second = deadlines_for(report, date(2026, 9, 4))
    assert first == second


def test_72_no_holiday_table_and_never_calls_roll_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    import registry_mcp.registries.gb as gb_pkg

    gb_dir = Path(gb_pkg.__file__).parent
    assert not (gb_dir / "holidays.py").exists()

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("roll_forward must never be called for GB")

    monkeypatch.setattr(rules_common, "roll_forward", _boom)
    report = mapping.map_entity(TESCO)
    deadlines = deadlines_for(report, date(2026, 9, 4))
    assert deadlines

    # N-4 (T15e review): `registries/gb/rules.py` imports `add_months` by
    # name, never the `rules_common` module object, so the monkeypatch above
    # can only ever be a no-op — it patches an attribute nothing reads.
    # Source inspection is the half of the test that actually proves it.
    for path in gb_dir.glob("*.py"):
        assert "roll_forward" not in path.read_text(encoding="utf-8"), path


# ---------------------------------------------------------------------------
# rules_markdown()
# ---------------------------------------------------------------------------


def test_rules_markdown_covers_required_points() -> None:
    text = rules_markdown()
    assert "sole trader" in text.lower()
    assert "no check digit" in text.lower()
    assert "bank holiday" in text.lower() or "Sunday" in text
    assert "annual_accounts" in text
    assert "confirmation_statement" in text
    assert "corporation tax" in text.lower()
    assert "employee" in text.lower()


def test_deadline_exemption_note_status_names_raw_value() -> None:
    report = mapping.map_entity(LIQUIDATION)
    notes = deadline_exemption_note(LIQUIDATION, report)
    assert any("liquidation" in n for n in notes)


def test_company_types_table_has_no_duplicate_keys() -> None:
    assert len(COMPANY_TYPES) == len(set(COMPANY_TYPES))


# ---------------------------------------------------------------------------
# D-021 — id_caveat: an unrecognised prefix stays valid, says so in `reason`
# ---------------------------------------------------------------------------


def test_d021_unrecognised_prefix_gets_a_caveat() -> None:
    from registry_mcp.registries.gb.rules import id_caveat

    caveat = id_caveat("ZZ000012")
    assert caveat is not None
    assert "ZZ" in caveat
    assert "lookup_company" in caveat


def test_d021_known_prefix_gets_no_caveat() -> None:
    from registry_mcp.registries.gb.rules import id_caveat

    assert id_caveat("SC090312") is None


def test_d021_all_digit_number_gets_no_caveat() -> None:
    from registry_mcp.registries.gb.rules import id_caveat

    assert id_caveat("00445790") is None


def test_d021_registry_validate_zz12_valid_with_caveat_no_hint() -> None:
    from registry_mcp.core.registry import get_registry

    registry = get_registry("GB")
    result = registry.validate("ZZ12")
    assert result.valid is True
    assert result.normalized == "ZZ000012"
    assert result.hint is None
    assert result.reason is not None and "ZZ" in result.reason


def test_d021_registry_validate_known_prefix_valid_no_caveat_no_hint() -> None:
    from registry_mcp.core.registry import get_registry

    registry = get_registry("GB")
    result = registry.validate("SC090312")
    assert result.valid is True
    assert result.hint is None
    assert result.reason is not None
    assert "not in the Companies House prefix list" not in result.reason
