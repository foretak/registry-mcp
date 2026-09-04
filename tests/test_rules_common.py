"""Country-neutral date helpers — ``core/rules/common.py``.

Tests 35–50 of ``NORBIZ_SPEC.md`` §13.D. Every date here was computed against
the real calendar; if an implementation disagrees, the implementation is
wrong, not the test.
"""

from __future__ import annotations

from datetime import date

import pytest

from registry_mcp.core.models import ErrorCode, RegistryError
from registry_mcp.core.rules.common import (
    add_months,
    is_business_day,
    last_day_of_month,
    next_occurrence,
    next_weekday,
    parse_iso_date,
    roll_forward,
)

# A small, self-contained set of Norwegian 2026 holidays for the roll_forward
# tests, so this file stays country-neutral (no import from registries/no/).
_NO_2026_HOLIDAYS = frozenset(
    {
        date(2026, 1, 1),
        date(2026, 4, 2),  # skjærtorsdag
        date(2026, 4, 3),  # langfredag
        date(2026, 4, 5),  # 1. påskedag
        date(2026, 4, 6),  # 2. påskedag
        date(2026, 5, 1),
        date(2026, 5, 14),  # Kristi himmelfartsdag
        date(2026, 5, 17),
        date(2026, 5, 24),  # 1. pinsedag
        date(2026, 5, 25),  # 2. pinsedag
        date(2026, 12, 25),
        date(2026, 12, 26),
    }
)


def test_35_next_weekday_saturday_rolls_to_monday() -> None:
    assert next_weekday(date(2026, 8, 1)) == date(2026, 8, 3)


def test_36_next_weekday_friday_unchanged() -> None:
    assert next_weekday(date(2026, 7, 31)) == date(2026, 7, 31)


def test_37_next_weekday_saturday_2027_rolls_to_monday() -> None:
    assert next_weekday(date(2027, 7, 31)) == date(2027, 8, 2)


def test_38_is_business_day_sunday_false() -> None:
    assert is_business_day(date(2026, 3, 15)) is False


def test_39_is_business_day_monday_true() -> None:
    assert is_business_day(date(2026, 3, 16)) is True


def test_40_is_business_day_holiday_false() -> None:
    assert is_business_day(date(2026, 5, 17), holidays={date(2026, 5, 17)}) is False


def test_41_roll_forward_skips_ascension_day() -> None:
    assert roll_forward(date(2026, 5, 14), holidays=_NO_2026_HOLIDAYS) == date(2026, 5, 15)


def test_42_roll_forward_skips_christmas_weekend() -> None:
    assert roll_forward(date(2026, 12, 25), holidays=_NO_2026_HOLIDAYS) == date(2026, 12, 28)


def test_43_roll_forward_ordinary_day_unchanged() -> None:
    assert roll_forward(date(2026, 3, 16), holidays=_NO_2026_HOLIDAYS) == date(2026, 3, 16)


def test_44_next_occurrence_this_year_not_yet_passed() -> None:
    assert next_occurrence(7, 31, date(2026, 1, 15)) == date(2026, 7, 31)


def test_45_next_occurrence_today_is_inclusive() -> None:
    assert next_occurrence(7, 31, date(2026, 7, 31)) == date(2026, 7, 31)


def test_46_next_occurrence_passed_rolls_to_next_year() -> None:
    assert next_occurrence(7, 31, date(2026, 8, 1)) == date(2027, 7, 31)


def test_47_next_occurrence_clamps_leap_day() -> None:
    assert next_occurrence(2, 29, date(2026, 3, 1)) == date(2027, 2, 28)


def test_48_last_day_of_month_leap_and_non_leap() -> None:
    assert last_day_of_month(2026, 2) == date(2026, 2, 28)
    assert last_day_of_month(2028, 2) == date(2028, 2, 29)


def test_49_add_months_clamps_day() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_50_add_months_rolls_year_over() -> None:
    assert add_months(date(2026, 12, 10), 2) == date(2027, 2, 10)


# ---------------------------------------------------------------------------
# `parse_iso_date` — added for T08 (shared REST/MCP `today` parsing, see
# `DECISIONS.md` D-007 and `PROGRESS.md`'s T08 row). Not part of
# `NORBIZ_SPEC.md`'s numbered §13.D list above, hence unnumbered names.
# ---------------------------------------------------------------------------


def test_parse_iso_date_none_defaults_to_today() -> None:
    from datetime import UTC, datetime

    assert parse_iso_date(None) == datetime.now(UTC).date()


def test_parse_iso_date_parses_valid_string() -> None:
    assert parse_iso_date("2026-01-15") == date(2026, 1, 15)


def test_parse_iso_date_invalid_raises_bad_request() -> None:
    with pytest.raises(RegistryError) as excinfo:
        parse_iso_date("not-a-date")
    exc = excinfo.value
    assert exc.code is ErrorCode.BAD_REQUEST
    assert exc.http_status == 400
    assert "today" in exc.hint


def test_parse_iso_date_custom_field_name_in_hint() -> None:
    with pytest.raises(RegistryError) as excinfo:
        parse_iso_date("nope", field="since")
    assert "since" in excinfo.value.hint


# `REVIEW.md` T10 item 7 / N6: `date.fromisoformat` is more lenient than the
# `YYYY-MM-DD` this function documents and promises in its `hint` — a bare
# `20260115` and an ISO week date `2026-W03-1` are both silently *accepted* by
# it (parsing to 2026-01-15 and 2026-01-12 respectively) unless rejected first.
@pytest.mark.parametrize("value", ["20260115", "2026-W03-1"])
def test_parse_iso_date_rejects_non_dash_iso_forms(value: str) -> None:
    with pytest.raises(RegistryError) as excinfo:
        parse_iso_date(value)
    assert excinfo.value.code is ErrorCode.BAD_REQUEST
