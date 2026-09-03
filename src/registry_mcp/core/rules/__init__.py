"""Rules helpers.

``common.py`` holds country-neutral date arithmetic used by every country.
Per-country rule modules live in ``registries/<cc>/rules.py`` and import from
here — never the other way round (``DECISIONS.md`` D-001).
"""

from registry_mcp.core.rules.common import (
    add_months,
    is_business_day,
    last_day_of_month,
    next_occurrence,
    next_weekday,
    roll_forward,
)

__all__ = [
    "add_months",
    "is_business_day",
    "last_day_of_month",
    "next_occurrence",
    "next_weekday",
    "roll_forward",
]
