"""Norwegian rules — ``registries/no/rules.py``.

Tests 1–34 and 51–81 of ``NORBIZ_SPEC.md`` §13 (sections A, B, C, E, F). Every
date below was computed against the real calendar; if an implementation
disagrees, the implementation is wrong.
"""

from __future__ import annotations

from datetime import date

import pytest

from registry_mcp.core.models import (
    CompanyReport,
    CompanyStatus,
    Deadline,
    ErrorCode,
    RegistryError,
)
from registry_mcp.registries.no.rules import (
    deadline_exemption_note,
    deadlines_for,
    derive_status,
    legal_form_info,
    norwegian_holidays,
    rules_markdown,
    validate_orgnr,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _report(
    *,
    legal_form_code: str | None = "AS",
    has_annual_accounts_duty: bool | None = True,
    vat_registered: bool | None = True,
    employees: int | None = 3,
    status: CompanyStatus = CompanyStatus.ACTIVE,
    is_subunit: bool = False,
) -> CompanyReport:
    """An active AS, VAT-registered, with 3 employees, unless overridden."""
    return CompanyReport(
        country="NO",
        registry="brreg",
        id="923609016",
        name="TEST AS",
        legal_form_code=legal_form_code,
        has_annual_accounts_duty=has_annual_accounts_duty,
        vat_registered=vat_registered,
        employees=employees,
        status=status,
        is_subunit=is_subunit,
    )


def _by_kind(deadlines: list[Deadline], kind: str) -> Deadline:
    matches = [d for d in deadlines if d.kind == kind]
    assert len(matches) == 1, f"expected exactly one {kind!r}, got {len(matches)}: {deadlines}"
    return matches[0]


# ---------------------------------------------------------------------------
# A. validate_orgnr — MOD11 and normalisation (1-15)
# ---------------------------------------------------------------------------


def test_01_valid_orgnr_923609016() -> None:
    assert validate_orgnr("923609016") == "923609016"


def test_02_valid_orgnr_974760673() -> None:
    assert validate_orgnr("974760673") == "974760673"


def test_03_valid_orgnr_remainder_zero() -> None:
    assert validate_orgnr("934154150") == "934154150"


def test_04_strips_spaces() -> None:
    assert validate_orgnr("923 609 016") == "923609016"


def test_05_strips_dots() -> None:
    assert validate_orgnr("923.609.016") == "923609016"


def test_06_strips_vat_form() -> None:
    assert validate_orgnr("NO923609016MVA") == "923609016"


def test_07_strips_vat_form_with_spaces() -> None:
    assert validate_orgnr("NO 923 609 016 MVA") == "923609016"


def test_08_wrong_check_digit_raises() -> None:
    with pytest.raises(RegistryError) as excinfo:
        validate_orgnr("923609017")
    assert excinfo.value.code is ErrorCode.INVALID_ID


def test_09_833286602_is_invalid() -> None:
    with pytest.raises(RegistryError):
        validate_orgnr("833286602")


def test_10_unissuable_check_digit_ten_raises() -> None:
    with pytest.raises(RegistryError):
        validate_orgnr("934157150")


def test_11_eight_digits_raises() -> None:
    with pytest.raises(RegistryError):
        validate_orgnr("92360901")


def test_12_ten_digits_raises() -> None:
    with pytest.raises(RegistryError):
        validate_orgnr("9236090160")


def test_13_non_digit_raises() -> None:
    with pytest.raises(RegistryError):
        validate_orgnr("92360901A")


def test_14_empty_raises() -> None:
    with pytest.raises(RegistryError):
        validate_orgnr("")


def test_15_invalid_error_has_hint_and_code() -> None:
    with pytest.raises(RegistryError) as excinfo:
        validate_orgnr("923609017")
    err = excinfo.value
    assert err.code is ErrorCode.INVALID_ID
    assert err.hint
    assert "search_company" in err.hint


# ---------------------------------------------------------------------------
# B. Legal-form mapping (16-25)
# ---------------------------------------------------------------------------


def test_16_as_legal_form() -> None:
    info = legal_form_info("AS")
    assert info.english == "Private limited company"
    assert info.limited_liability is True
    assert info.has_board_duty is True
    assert info.has_annual_accounts_duty is True


def test_17_asa_legal_form() -> None:
    info = legal_form_info("ASA")
    assert info.has_board_duty is True
    assert info.has_annual_accounts_duty is True


def test_18_enk_legal_form() -> None:
    info = legal_form_info("ENK")
    assert info.limited_liability is False
    assert info.has_board_duty is False
    assert info.has_annual_accounts_duty is None


def test_19_ans_and_da_legal_form() -> None:
    for code in ("ANS", "DA"):
        info = legal_form_info(code)
        assert info.limited_liability is False
        assert info.has_annual_accounts_duty is None


def test_20_nuf_legal_form() -> None:
    info = legal_form_info("NUF")
    assert info.has_board_duty is False
    assert info.has_annual_accounts_duty is None


def test_21_forms_with_accounts_duty() -> None:
    for code in ("SA", "STI", "KF", "IKS", "BA"):
        assert legal_form_info(code).has_annual_accounts_duty is True


def test_22_ks_legal_form() -> None:
    assert legal_form_info("KS").has_annual_accounts_duty is None


def test_23_fli_legal_form() -> None:
    info = legal_form_info("FLI")
    assert info.has_board_duty is None
    assert info.has_annual_accounts_duty is None


def test_24_bedr_is_subunit_form() -> None:
    info = legal_form_info("BEDR")
    assert info.has_board_duty is False
    assert info.has_annual_accounts_duty is False
    assert info.is_subunit is True


def test_25_unknown_code_is_unclassified() -> None:
    info = legal_form_info("ZZZZ", local_description="Fantasiform")
    assert info.english == "Fantasiform"
    assert info.limited_liability is None
    assert info.has_board_duty is None
    assert info.has_annual_accounts_duty is None
    assert info.notes


# ---------------------------------------------------------------------------
# C. Status derivation (26-34)
# ---------------------------------------------------------------------------


def test_26_all_flags_false_is_active() -> None:
    result = derive_status(
        bankrupt=False,
        under_liquidation=False,
        under_compulsory_liquidation=False,
        deleted_at=None,
    )
    assert result.status is CompanyStatus.ACTIVE
    assert result.is_active is True


def test_27_bankrupt() -> None:
    result = derive_status(
        bankrupt=True,
        under_liquidation=False,
        under_compulsory_liquidation=False,
        deleted_at=None,
        bankruptcy_date=date(2026, 7, 8),
    )
    assert result.status is CompanyStatus.BANKRUPT
    assert result.is_active is False
    assert "2026-07-08" in result.status_detail


def test_28_under_liquidation() -> None:
    result = derive_status(
        bankrupt=False,
        under_liquidation=True,
        under_compulsory_liquidation=False,
        deleted_at=None,
    )
    assert result.status is CompanyStatus.UNDER_LIQUIDATION


def test_29_under_compulsory_liquidation() -> None:
    result = derive_status(
        bankrupt=False,
        under_liquidation=False,
        under_compulsory_liquidation=True,
        deleted_at=None,
    )
    assert result.status is CompanyStatus.UNDER_COMPULSORY_LIQUIDATION


def test_30_deleted() -> None:
    result = derive_status(
        bankrupt=False,
        under_liquidation=False,
        under_compulsory_liquidation=False,
        deleted_at=date(2024, 1, 15),
    )
    assert result.status is CompanyStatus.DELETED
    assert "2024-01-15" in result.status_detail


def test_31_deleted_wins_over_bankrupt() -> None:
    result = derive_status(
        bankrupt=True,
        under_liquidation=False,
        under_compulsory_liquidation=False,
        deleted_at=date(2024, 1, 15),
    )
    assert result.status is CompanyStatus.DELETED


def test_32_bankrupt_wins_over_liquidation() -> None:
    result = derive_status(
        bankrupt=True,
        under_liquidation=True,
        under_compulsory_liquidation=False,
        deleted_at=None,
    )
    assert result.status is CompanyStatus.BANKRUPT


def test_33_no_flags_present_is_unknown() -> None:
    result = derive_status(
        bankrupt=None,
        under_liquidation=None,
        under_compulsory_liquidation=None,
        deleted_at=None,
    )
    assert result.status is CompanyStatus.UNKNOWN


def test_34_non_active_status_adds_note() -> None:
    result = derive_status(
        bankrupt=True,
        under_liquidation=False,
        under_compulsory_liquidation=False,
        deleted_at=None,
    )
    assert len(result.notes) >= 1


# ---------------------------------------------------------------------------
# E. Norwegian holidays (51-56)
# ---------------------------------------------------------------------------


def test_51_norwegian_holidays_2026_fixed() -> None:
    holidays = norwegian_holidays(2026)
    for d in (
        date(2026, 1, 1),
        date(2026, 5, 1),
        date(2026, 5, 17),
        date(2026, 12, 25),
        date(2026, 12, 26),
    ):
        assert d in holidays


def test_52_norwegian_holidays_2026_easter() -> None:
    holidays = norwegian_holidays(2026)
    for d in (date(2026, 4, 2), date(2026, 4, 3), date(2026, 4, 5), date(2026, 4, 6)):
        assert d in holidays


def test_53_norwegian_holidays_2026_ascension_and_pentecost() -> None:
    holidays = norwegian_holidays(2026)
    for d in (date(2026, 5, 14), date(2026, 5, 24), date(2026, 5, 25)):
        assert d in holidays


def test_54_norwegian_holidays_2027_easter() -> None:
    holidays = norwegian_holidays(2027)
    for d in (date(2027, 3, 25), date(2027, 3, 26), date(2027, 3, 28), date(2027, 3, 29)):
        assert d in holidays


def test_55_norwegian_holidays_2027_may17_counted_once() -> None:
    holidays = norwegian_holidays(2027)
    assert isinstance(holidays, frozenset)
    assert date(2027, 5, 17) in holidays
    assert sum(1 for d in holidays if d == date(2027, 5, 17)) == 1


def test_56_norwegian_holidays_2026_excludes_dec24_and_dec31() -> None:
    holidays = norwegian_holidays(2026)
    assert date(2026, 12, 24) not in holidays
    assert date(2026, 12, 31) not in holidays


# ---------------------------------------------------------------------------
# F. Deadlines (57-81)
# ---------------------------------------------------------------------------


def test_57_annual_accounts_no_roll() -> None:
    deadlines = deadlines_for(_report(), date(2026, 1, 15))
    d = _by_kind(deadlines, "annual_accounts")
    assert d.statutory_date == d.due_date == date(2026, 7, 31)
    assert d.rolled_forward is False
    assert d.period_label == "2025"


def test_58_annual_accounts_no_roll_even_on_saturday() -> None:
    """Corrected 2026-09-05 (R01, D-022(b)): regnskapsloven § 8-3(1) charges a
    late fee unless the accounts are dispatched before 1 August, so rolling
    31 July (a Saturday, in 2027) onto Monday 2 August would return a date on
    which the fee is already running. The date does not move off the
    weekend. (The previous version of this test asserted
    `due_date == date(2027, 8, 2)` and `rolled_forward is True`; that was the
    bug.)"""
    deadlines = deadlines_for(_report(), date(2026, 8, 1))
    d = _by_kind(deadlines, "annual_accounts")
    assert d.statutory_date == date(2027, 7, 31)
    assert d.due_date == date(2027, 7, 31)
    assert d.rolled_forward is False
    assert d.period_label == "2026"


def test_58b_annual_accounts_no_roll_sunday_lands_on_aug1() -> None:
    """Added 2026-09-05 (R01, D-022(b)). The Sunday case: rolling 31 July 2033
    forward would land on 1 August itself — the exact date the late fee
    starts running."""
    deadlines = deadlines_for(_report(), date(2033, 1, 15))
    d = _by_kind(deadlines, "annual_accounts")
    assert d.statutory_date == date(2033, 7, 31)
    assert d.due_date == date(2033, 7, 31)
    assert d.rolled_forward is False


def test_59_tax_return_rolled_forward() -> None:
    deadlines = deadlines_for(_report(), date(2026, 1, 15))
    d = _by_kind(deadlines, "tax_return")
    assert d.statutory_date == date(2026, 5, 31)
    assert d.due_date == date(2026, 6, 1)
    assert d.rolled_forward is True


def test_60_tax_return_next_year() -> None:
    deadlines = deadlines_for(_report(), date(2026, 6, 2))
    d = _by_kind(deadlines, "tax_return")
    assert d.statutory_date == date(2027, 5, 31)
    assert d.due_date == d.statutory_date
    assert d.rolled_forward is False


def test_61_shareholder_register_statement_rolled() -> None:
    deadlines = deadlines_for(_report(), date(2026, 1, 15))
    d = _by_kind(deadlines, "shareholder_register_statement")
    assert d.statutory_date == date(2026, 1, 31)
    assert d.due_date == date(2026, 2, 2)


def test_62_shareholder_register_statement_next_year() -> None:
    deadlines = deadlines_for(_report(), date(2026, 3, 1))
    d = _by_kind(deadlines, "shareholder_register_statement")
    assert d.statutory_date == date(2027, 1, 31)
    assert d.due_date == date(2027, 2, 1)


def test_63_general_meeting_no_roll() -> None:
    deadlines = deadlines_for(_report(), date(2026, 1, 15))
    d = _by_kind(deadlines, "general_meeting")
    assert d.due_date == date(2026, 6, 30)
    assert d.rolled_forward is False


def test_63b_general_meeting_no_roll_saturday() -> None:
    """Added 2026-09-05 (R01, D-022(b)). Aksjeloven § 5-5(1)'s six months is
    an outer limit and a general meeting may lawfully be held on a Saturday,
    so rolling 30 June 2029 (a Saturday) to 2 July would be late."""
    deadlines = deadlines_for(_report(), date(2029, 1, 15))
    d = _by_kind(deadlines, "general_meeting")
    assert d.statutory_date == date(2029, 6, 30)
    assert d.due_date == date(2029, 6, 30)
    assert d.rolled_forward is False


def test_63c_annual_accounts_and_general_meeting_never_roll_2026_2040() -> None:
    """Added 2026-09-05 (R01, D-022(b)). Regression guard: a future change to
    a shared helper (e.g. `roll_forward`, or a rewrite of `deadlines_for`)
    must not reintroduce roll-forward on these two deadlines for any year in
    this range."""
    for year in range(2026, 2041):
        deadlines = deadlines_for(_report(), date(year, 1, 15))
        for kind in ("annual_accounts", "general_meeting"):
            d = _by_kind(deadlines, kind)
            assert d.rolled_forward is False, f"{kind} rolled forward for today year {year}"
            assert d.statutory_date == d.due_date, f"{kind} dates differ for today year {year}"


def test_64_vat_term_3_summer_exception() -> None:
    deadlines = deadlines_for(_report(), date(2026, 7, 1))
    d = _by_kind(deadlines, "vat_return")
    assert d.statutory_date == d.due_date == date(2026, 8, 31)
    assert d.period_label == "2026 term 3 (May–Jun)"
    assert d.period_start == date(2026, 5, 1)
    assert d.period_end == date(2026, 6, 30)


def test_65_vat_term_4_rolled() -> None:
    deadlines = deadlines_for(_report(), date(2026, 9, 1))
    d = _by_kind(deadlines, "vat_return")
    assert d.statutory_date == date(2026, 10, 10)
    assert d.due_date == date(2026, 10, 12)


def test_66_vat_term_6_crosses_year() -> None:
    deadlines = deadlines_for(_report(), date(2026, 12, 15))
    d = _by_kind(deadlines, "vat_return")
    assert d.statutory_date == d.due_date == date(2027, 2, 10)
    assert d.period_label == "2026 term 6 (Nov–Dec)"


def test_67_vat_term_1() -> None:
    deadlines = deadlines_for(_report(), date(2026, 3, 1))
    d = _by_kind(deadlines, "vat_return")
    assert d.statutory_date == d.due_date == date(2026, 4, 10)


def test_68_payroll_report_rolls_past_easter() -> None:
    deadlines = deadlines_for(_report(), date(2026, 3, 10))
    d = _by_kind(deadlines, "payroll_report")
    assert d.statutory_date == date(2026, 4, 5)
    assert d.due_date == date(2026, 4, 7)


def test_69_payroll_report_rolls_weekend() -> None:
    deadlines = deadlines_for(_report(), date(2026, 8, 10))
    d = _by_kind(deadlines, "payroll_report")
    assert d.statutory_date == date(2026, 9, 5)
    assert d.due_date == date(2026, 9, 7)


def test_70_no_vat_return_when_not_registered() -> None:
    deadlines = deadlines_for(_report(vat_registered=False), date(2026, 1, 15))
    assert "vat_return" not in {d.kind for d in deadlines}


def test_71_no_payroll_report_without_employees() -> None:
    deadlines_none = deadlines_for(_report(employees=None), date(2026, 1, 15))
    deadlines_zero = deadlines_for(_report(employees=0), date(2026, 1, 15))
    assert "payroll_report" not in {d.kind for d in deadlines_none}
    assert "payroll_report" not in {d.kind for d in deadlines_zero}


def test_72_enk_gets_tax_return_not_annual_or_shareholder() -> None:
    report = _report(
        legal_form_code="ENK",
        has_annual_accounts_duty=None,
        vat_registered=False,
        employees=None,
    )
    deadlines = deadlines_for(report, date(2026, 1, 15))
    kinds = {d.kind for d in deadlines}
    assert "annual_accounts" not in kinds
    assert "shareholder_register_statement" not in kinds
    assert "tax_return" in kinds


def test_73_enk_gets_no_general_meeting() -> None:
    report = _report(legal_form_code="ENK", has_annual_accounts_duty=None)
    deadlines = deadlines_for(report, date(2026, 1, 15))
    assert "general_meeting" not in {d.kind for d in deadlines}


def test_74_bedr_subunit_has_no_deadlines() -> None:
    report = _report(legal_form_code="BEDR", has_annual_accounts_duty=False, is_subunit=True)
    assert deadlines_for(report, date(2026, 1, 15)) == []
    note = deadline_exemption_note(report)
    assert note is not None
    assert "parent_id" in note


def test_75_bankrupt_company_has_no_deadlines() -> None:
    report = _report(status=CompanyStatus.BANKRUPT)
    assert deadlines_for(report, date(2026, 1, 15)) == []
    note = deadline_exemption_note(report)
    assert note is not None
    assert "bankrupt" in note.lower()


def test_76_deleted_company_has_no_deadlines() -> None:
    report = _report(status=CompanyStatus.DELETED)
    assert deadlines_for(report, date(2026, 1, 15)) == []
    note = deadline_exemption_note(report)
    assert note is not None
    assert "deleted" in note.lower()


def test_76b_under_compulsory_liquidation_has_no_deadlines() -> None:
    report = _report(status=CompanyStatus.UNDER_COMPULSORY_LIQUIDATION)
    assert deadlines_for(report, date(2026, 1, 15)) == []
    note = deadline_exemption_note(report)
    assert note is not None
    assert "compulsory liquidation" in note.lower()


def test_77_under_liquidation_keeps_deadlines() -> None:
    report = _report(status=CompanyStatus.UNDER_LIQUIDATION)
    deadlines = deadlines_for(report, date(2026, 1, 15))
    assert len(deadlines) > 0
    assert deadline_exemption_note(report) is None


def test_78_sorted_by_due_date_shareholder_first() -> None:
    deadlines = deadlines_for(_report(), date(2026, 1, 15))
    assert deadlines[0].kind == "shareholder_register_statement"
    assert deadlines[0].due_date == date(2026, 2, 2)
    due_dates = [d.due_date for d in deadlines]
    assert due_dates == sorted(due_dates)


def test_79_one_deadline_per_kind() -> None:
    deadlines = deadlines_for(_report(), date(2026, 1, 15))
    kinds = [d.kind for d in deadlines]
    assert len(kinds) == len(set(kinds))


def test_80_every_deadline_shape() -> None:
    today = date(2026, 1, 15)
    deadlines = deadlines_for(_report(), today)
    assert deadlines  # sanity: the AS fixture has deadlines
    for d in deadlines:
        assert d.country == "NO"
        assert d.registry == "brreg"
        assert d.applies_because
        assert d.days_until == (d.due_date - today).days


def test_81_deadlines_for_is_pure() -> None:
    report = _report()
    today = date(2026, 1, 15)
    first = deadlines_for(report, today)
    second = deadlines_for(report, today)
    assert first == second


# ---------------------------------------------------------------------------
# Interop with registries/no/__init__.py (BrregRegistry delegates here)
# ---------------------------------------------------------------------------


def test_rules_markdown_is_nonempty_text() -> None:
    markdown = rules_markdown()
    assert isinstance(markdown, str)
    assert "organisasjonsnummer" in markdown.lower()
    assert "vat_return" in markdown


# ---------------------------------------------------------------------------
# D-009 — an unclassified legal form gets no deadlines; tax_return is gated
# on an explicit form list (REVIEW.md T02 B1/B2)
# ---------------------------------------------------------------------------


def test_b1_unknown_code_gets_no_deadlines() -> None:
    """The spec's own test-25 fantasy form must never produce a deadline."""
    report = _report(legal_form_code="ZZZZ", has_annual_accounts_duty=None)
    assert deadlines_for(report, date(2026, 1, 15)) == []
    note = deadline_exemption_note(report)
    assert note is not None
    assert "ZZZZ" in note
    assert "not classified" in note


def test_b1_missing_code_gets_no_deadlines() -> None:
    report = _report(legal_form_code=None, has_annual_accounts_duty=None)
    assert deadlines_for(report, date(2026, 1, 15)) == []
    note = deadline_exemption_note(report)
    assert note is not None


def test_b2_orgl_gets_no_tax_return_but_keeps_fact_based_deadlines() -> None:
    """Registerenheten i Brønnøysund (974760673) is ORGL — a classified but
    §7 `VERIFY`-marked public-sector form. It must never be told it owes a
    Skattemelding for næringsdrivende, but vat_return/payroll_report still
    follow from published facts (D-009(c))."""
    report = _report(
        legal_form_code="ORGL",
        has_annual_accounts_duty=None,
        vat_registered=True,
        employees=5,
    )
    deadlines = deadlines_for(report, date(2026, 1, 15))
    kinds = {d.kind for d in deadlines}
    assert "tax_return" not in kinds
    assert "annual_accounts" not in kinds
    assert "vat_return" in kinds
    assert "payroll_report" in kinds


def test_b2_unlisted_code_gets_empty_list() -> None:
    """An unlisted (unclassified) code gets nothing at all, not just no tax_return."""
    report = _report(legal_form_code="QQQQ", vat_registered=True, employees=5)
    assert deadlines_for(report, date(2026, 1, 15)) == []


def test_annual_accounts_duty_falls_back_to_legal_form_table() -> None:
    """A hand-built report with has_annual_accounts_duty=None still gets the
    deadline when the legal form's own table entry says it applies."""
    report = _report(legal_form_code="ASA", has_annual_accounts_duty=None)
    deadlines = deadlines_for(report, date(2026, 1, 15))
    assert "annual_accounts" in {d.kind for d in deadlines}


def test_applies_because_names_the_legal_form_code() -> None:
    deadlines = deadlines_for(_report(legal_form_code="ASA"), date(2026, 1, 15))
    for kind in ("annual_accounts", "general_meeting", "tax_return", "shareholder_register_statement"):
        d = _by_kind(deadlines, kind)
        assert "ASA" in d.applies_because
