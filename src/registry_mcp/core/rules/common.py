"""Country-neutral date helpers shared by every registry's deadline rules.

**Signatures only — T02 implements the bodies.** Do not add Norwegian logic
here: national holiday tables, org-form tables and statutory dates belong in
``registries/<cc>/rules.py`` (``DECISIONS.md`` D-001).

The one country-specific thing these functions accept is a set of holiday
dates, passed in by the caller. ``core`` never knows which dates those are.

See ``NORBIZ_SPEC.md`` §5 for the numbered test list T02 must satisfy.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from datetime import date, timedelta

__all__ = [
    "add_months",
    "is_business_day",
    "last_day_of_month",
    "next_occurrence",
    "next_weekday",
    "roll_forward",
]


def is_business_day(d: date, holidays: Iterable[date] = ()) -> bool:
    """True when ``d`` is Monday–Friday and not in ``holidays``.

    Args:
        d: The date to test.
        holidays: Dates treated as non-working. Supplied by the country module.
    """
    if d.weekday() >= 5:
        return False
    return d not in set(holidays)


def next_weekday(d: date) -> date:
    """The first Monday–Friday on or after ``d``.

    Returns ``d`` unchanged when it already falls on a weekday. Ignores
    holidays — use :func:`roll_forward` when holidays matter.

    Examples:
        Saturday 2026-08-01 -> Monday 2026-08-03.
        Friday 2026-07-31 -> Friday 2026-07-31.
    """
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def roll_forward(d: date, holidays: Iterable[date] = ()) -> date:
    """The first business day on or after ``d``, skipping weekends and ``holidays``.

    This is the rule Norwegian filing deadlines use: a statutory date falling on
    a Saturday, Sunday or public holiday moves to the next working day.
    """
    holiday_set = set(holidays)
    while not is_business_day(d, holiday_set):
        d += timedelta(days=1)
    return d


def next_occurrence(month: int, day: int, today: date) -> date:
    """The next calendar occurrence of ``month``/``day`` on or after ``today``.

    Returns this year's date when it has not passed, otherwise next year's.
    Uses the statutory day, before any weekend/holiday roll-forward — call
    :func:`roll_forward` on the result.

    Args:
        month: 1–12.
        day: 1–31; a day past the month's end clamps to the last day of that
            month (so 31 February becomes 28/29 February).
        today: The reference date, inclusive — if ``today`` *is* the date, that
            date is returned.
    """
    candidate = date(today.year, month, min(day, last_day_of_month(today.year, month).day))
    if candidate >= today:
        return candidate
    return date(
        today.year + 1, month, min(day, last_day_of_month(today.year + 1, month).day)
    )


def last_day_of_month(year: int, month: int) -> date:
    """The last calendar day of ``year``/``month``, leap years included."""
    return date(year, month, calendar.monthrange(year, month)[1])


def add_months(d: date, months: int) -> date:
    """``d`` shifted by ``months``, clamping the day to the target month's length.

    Used for period arithmetic such as "the 10th of the second month after the
    VAT term ends".
    """
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, last_day_of_month(year, month).day)
    return date(year, month, day)
