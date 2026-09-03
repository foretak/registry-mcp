"""Norwegian legal rules: organisasjonsnummer validation, holidays, legal-form
duties, status derivation and filing deadlines.

Everything Norway-specific lives here, never in ``core/`` (``DECISIONS.md``
D-001). This module is pure and synchronous — no I/O, no clock reads. See
``NORBIZ_SPEC.md`` §5, §7 and §8 for the authoritative rules, and §13 for the
numbered test list this module must satisfy (tests 1–81).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from functools import cache
from typing import NamedTuple

from registry_mcp.core.models import (
    CompanyReport,
    CompanyStatus,
    Deadline,
    DeadlineRecurrence,
    ErrorCode,
    RegistryError,
)
from registry_mcp.core.rules.common import (
    add_months,
    last_day_of_month,
    next_occurrence,
    roll_forward,
)

__all__ = [
    "LEGAL_FORMS",
    "ORG_FORMS",
    "LegalFormEntry",
    "LegalFormInfo",
    "StatusResult",
    "deadline_exemption_note",
    "deadlines",
    "deadlines_for",
    "derive_status",
    "legal_form_info",
    "norwegian_holidays",
    "rules_markdown",
    "validate_orgnr",
]


# ---------------------------------------------------------------------------
# §5.1 — MOD11 validation of an organisasjonsnummer
# ---------------------------------------------------------------------------

_WEIGHTS: tuple[int, ...] = (3, 2, 7, 6, 5, 4, 3, 2)
_STRIP_RE = re.compile(r"[\s.\-/]")


def _invalid(raw: str) -> RegistryError:
    return RegistryError(
        ErrorCode.INVALID_ID,
        f"{raw!r} is not a valid Norwegian organisasjonsnummer.",
        hint=(
            "An organisasjonsnummer is nine digits with a MOD11 check digit, e.g. "
            "923609016. If you have a company name instead, call search_company."
        ),
        country="NO",
        registry="brreg",
    )


def _normalise(raw: str) -> str:
    cleaned = _STRIP_RE.sub("", raw).upper()
    if cleaned.startswith("NO"):
        cleaned = cleaned[2:]
    if cleaned.endswith("MVA"):
        cleaned = cleaned[: -len("MVA")]
    return cleaned


def validate_orgnr(raw: str) -> str:
    """Normalise and MOD11-check a Norwegian organisasjonsnummer.

    Raises:
        RegistryError: ``invalid_id`` if the normalised value is not exactly
            nine digits, or the check digit does not match (including the
            unissuable case where the computed check digit would be 10).
    """
    cleaned = _normalise(raw)
    if len(cleaned) != 9 or not cleaned.isdigit():
        raise _invalid(raw)

    digits = [int(c) for c in cleaned]
    total = sum(d * w for d, w in zip(digits[:8], _WEIGHTS, strict=True))
    remainder = total % 11
    check = 0 if remainder == 0 else 11 - remainder
    if check == 10 or check != digits[8]:
        raise _invalid(raw)
    return cleaned


# ---------------------------------------------------------------------------
# §5.2 — Norwegian public holidays
# ---------------------------------------------------------------------------


def _easter_sunday(year: int) -> date:
    """Easter Sunday for ``year`` (anonymous Gregorian computus)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@cache
def norwegian_holidays(year: int) -> frozenset[date]:
    """Norwegian public holidays (helligdager) for ``year``.

    24 and 31 December are ordinary working days for deadline purposes and are
    deliberately not included.
    """
    easter = _easter_sunday(year)
    dates = {
        date(year, 1, 1),  # nyttårsdag
        date(year, 5, 1),  # arbeidernes dag
        date(year, 5, 17),  # grunnlovsdagen
        date(year, 12, 25),  # 1. juledag
        date(year, 12, 26),  # 2. juledag
        easter - timedelta(days=3),  # skjærtorsdag
        easter - timedelta(days=2),  # langfredag
        easter,  # 1. påskedag
        easter + timedelta(days=1),  # 2. påskedag
        easter + timedelta(days=39),  # Kristi himmelfartsdag
        easter + timedelta(days=49),  # 1. pinsedag
        easter + timedelta(days=50),  # 2. pinsedag
    }
    return frozenset(dates)


def _holidays_spanning(*years: int) -> frozenset[date]:
    combined: set[date] = set()
    for year in years:
        combined |= norwegian_holidays(year)
    return frozenset(combined)


# ---------------------------------------------------------------------------
# §7 — Legal-form table
# ---------------------------------------------------------------------------


class LegalFormEntry(NamedTuple):
    """One row of the legal-form table. ``None`` means "depends on facts the
    register does not publish"."""

    local: str
    english: str
    limited_liability: bool | None
    has_board_duty: bool | None
    has_annual_accounts_duty: bool | None
    is_subunit: bool = False


#: Norwegian legal-form codes -> duties. See ``NORBIZ_SPEC.md`` §7.
ORG_FORMS: dict[str, LegalFormEntry] = {
    "AS": LegalFormEntry("Aksjeselskap", "Private limited company", True, True, True),
    "ASA": LegalFormEntry("Allmennaksjeselskap", "Public limited company", True, True, True),
    "ENK": LegalFormEntry("Enkeltpersonforetak", "Sole proprietorship", False, False, None),
    "ANS": LegalFormEntry(
        "Ansvarlig selskap med solidarisk ansvar",
        "General partnership, joint and several liability",
        False,
        False,
        None,
    ),
    "DA": LegalFormEntry(
        "Ansvarlig selskap med delt ansvar",
        "General partnership, pro-rata liability",
        False,
        False,
        None,
    ),
    "NUF": LegalFormEntry(
        "Norskregistrert utenlandsk foretak",
        "Norwegian-registered branch of a foreign company",
        None,
        False,
        None,
    ),
    "SA": LegalFormEntry("Samvirkeforetak", "Cooperative", True, True, True),
    "STI": LegalFormEntry("Stiftelse", "Foundation", True, True, True),
    "KS": LegalFormEntry("Kommandittselskap", "Limited partnership", None, False, None),
    "BA": LegalFormEntry(
        "Selskap med begrenset ansvar",
        "Company with limited liability (legacy form, no longer issued)",
        True,
        True,
        True,
    ),
    "FLI": LegalFormEntry(
        "Forening/lag/innretning", "Association, club or institution", True, None, None
    ),
    "KF": LegalFormEntry("Kommunalt foretak", "Municipal enterprise", True, True, True),
    "IKS": LegalFormEntry("Interkommunalt selskap", "Inter-municipal company", False, True, True),
    # Sub-unit forms: not legal entities.
    "BEDR": LegalFormEntry(
        "Underenhet til næringsdrivende og offentlig forvaltning",
        "Branch / sub-unit of a business or public body",
        None,
        False,
        False,
        is_subunit=True,
    ),
    "AAFY": LegalFormEntry(
        "Underenhet til ikke-næringsdrivende",
        "Branch / sub-unit of a non-business entity",
        None,
        False,
        False,
        is_subunit=True,
    ),
    # Additional codes seen in the wild — duty columns VERIFY, so None.
    "ORGL": LegalFormEntry("Organisasjonsledd", "Organisational unit of a public body", None, None, None),
    "SF": LegalFormEntry("Statsforetak", "State-owned enterprise", None, None, None),
    "BRL": LegalFormEntry("Borettslag", "Housing cooperative", None, None, None),
    "BBL": LegalFormEntry("Boligbyggelag", "Housing construction cooperative", None, None, None),
    "ESEK": LegalFormEntry(
        "Eierseksjonssameie", "Condominium owners' association", None, None, None
    ),
    "SPA": LegalFormEntry("Sparebank", "Savings bank", None, None, None),
    "GFS": LegalFormEntry("Gjensidig forsikringsselskap", "Mutual insurance company", None, None, None),
    "PK": LegalFormEntry("Pensjonskasse", "Pension fund", None, None, None),
    "KBO": LegalFormEntry("Konkursbo", "Bankruptcy estate", None, None, None),
    "SE": LegalFormEntry("Europeisk selskap", "European company (SE)", None, None, None),
    "VPFO": LegalFormEntry("Verdipapirfond", "Securities fund", None, None, None),
    "KOMM": LegalFormEntry("Kommune", "Municipality", None, None, None),
    "FYLK": LegalFormEntry("Fylkeskommune", "County", None, None, None),
    "STAT": LegalFormEntry("Staten", "The State", None, None, None),
    "UTLA": LegalFormEntry("Utenlandsk enhet", "Foreign entity", None, None, None),
    "PRE": LegalFormEntry("Partrederi", "Shipping partnership", None, None, None),
    "TVAM": LegalFormEntry("Tvangsregistrert for MVA", "Compulsorily VAT-registered", None, None, None),
    "SÆR": LegalFormEntry(
        "Annet foretak iflg. særskilt lov", "Other entity under a specific act", None, None, None
    ),
    "ANNA": LegalFormEntry("Annen juridisk person", "Other legal person", None, None, None),
}

#: Alias matching the name used in ``NORBIZ_SPEC.md`` §7.
LEGAL_FORMS = ORG_FORMS

#: Legal-form codes that are sub-units, not legal entities in their own right.
_SUBUNIT_CODES = frozenset(code for code, entry in ORG_FORMS.items() if entry.is_subunit)


class LegalFormInfo(NamedTuple):
    """Result of looking up a legal-form code, including the unclassified case."""

    code: str
    local: str
    english: str
    limited_liability: bool | None
    has_board_duty: bool | None
    has_annual_accounts_duty: bool | None
    is_subunit: bool
    notes: list[str]


def legal_form_info(code: str, local_description: str = "") -> LegalFormInfo:
    """Look up the duties for a legal-form ``code``.

    An unlisted code maps to ``english = local_description`` (or the code
    itself if that is also empty), all three duty fields ``None``, and a note
    saying the form is not yet classified. Never guess a duty.
    """
    key = code.upper()
    entry = ORG_FORMS.get(key)
    if entry is None:
        label = local_description or key
        return LegalFormInfo(
            code=key,
            local=label,
            english=label,
            limited_liability=None,
            has_board_duty=None,
            has_annual_accounts_duty=None,
            is_subunit=False,
            notes=[
                f"Legal form {key!r} is not yet classified by registry-mcp; "
                "its duties are unknown, not absent."
            ],
        )
    return LegalFormInfo(
        code=key,
        local=entry.local,
        english=entry.english,
        limited_liability=entry.limited_liability,
        has_board_duty=entry.has_board_duty,
        has_annual_accounts_duty=entry.has_annual_accounts_duty,
        is_subunit=entry.is_subunit,
        notes=[],
    )


# ---------------------------------------------------------------------------
# §8 — Status derivation
# ---------------------------------------------------------------------------


class StatusResult(NamedTuple):
    """Result of :func:`derive_status`."""

    status: CompanyStatus
    status_detail: str
    is_active: bool
    notes: list[str]


def derive_status(
    *,
    bankrupt: bool | None,
    under_liquidation: bool | None,
    under_compulsory_liquidation: bool | None,
    deleted_at: date | None,
    bankruptcy_date: date | None = None,
) -> StatusResult:
    """Derive :class:`CompanyStatus` from the brreg lifecycle flags.

    Each boolean argument is ``None`` when the source payload does not carry
    that flag at all (as opposed to carrying it with value ``False``) — this
    is what lets an all-``None`` payload map to ``UNKNOWN`` rather than
    ``ACTIVE``. Precedence, first match wins: deleted > bankrupt > compulsory
    liquidation > voluntary liquidation > active > unknown.
    """
    if deleted_at is not None:
        detail = f"Deleted from Enhetsregisteret on {deleted_at}."
        note = f"This company was deleted from Enhetsregisteret on {deleted_at}."
        return StatusResult(CompanyStatus.DELETED, detail, False, [note])

    if bankrupt:
        if bankruptcy_date is not None:
            detail = f"Bankruptcy proceedings opened on {bankruptcy_date}."
            note = (
                f"This company is bankrupt (registered {bankruptcy_date}). Do not treat it as "
                "a going concern without checking with the bankruptcy estate."
            )
        else:
            detail = "Bankruptcy proceedings opened."
            note = (
                "This company is bankrupt. Do not treat it as a going concern without "
                "checking with the bankruptcy estate."
            )
        return StatusResult(CompanyStatus.BANKRUPT, detail, False, [note])

    if under_compulsory_liquidation:
        detail = "Under compulsory liquidation or dissolution ordered by a court."
        note = "This company is under compulsory liquidation or dissolution ordered by a court."
        return StatusResult(CompanyStatus.UNDER_COMPULSORY_LIQUIDATION, detail, False, [note])

    if under_liquidation:
        detail = "Voluntary liquidation has been registered."
        note = "This company is in voluntary liquidation."
        return StatusResult(CompanyStatus.UNDER_LIQUIDATION, detail, False, [note])

    if bankrupt is None and under_liquidation is None and under_compulsory_liquidation is None:
        detail = "The registry record does not carry status flags."
        note = "The registry record does not carry status flags; status could not be determined."
        return StatusResult(CompanyStatus.UNKNOWN, detail, False, [note])

    return StatusResult(CompanyStatus.ACTIVE, "Registered and active in Enhetsregisteret.", True, [])


# ---------------------------------------------------------------------------
# §5.4 — Filing deadlines
# ---------------------------------------------------------------------------

_NO_DEADLINE_STATUSES = frozenset(
    {
        CompanyStatus.DELETED,
        CompanyStatus.BANKRUPT,
        CompanyStatus.UNDER_COMPULSORY_LIQUIDATION,
    }
)

_MONTH_ABBR = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

_CALENDAR_YEAR_ASSUMPTION = " Assumes a calendar-year accounting period."

#: Legal-form codes that owe a tax return (skattemelding for næringsdrivende).
#: D-009(b): the private-sector business forms of §7's confirmed table. Public
#: -sector and VERIFY-marked forms (``ORGL``, ``KOMM``, ``FYLK``, ``STAT``,
#: ``SF``, ``KF``, ``IKS``, ``STI``, ``FLI``, ``BRL``, ``BBL``, ``ESEK``, ...)
#: get no ``tax_return`` until someone verifies the duty against a source.
_TAX_RETURN_FORMS = frozenset({"AS", "ASA", "ENK", "ANS", "DA", "NUF", "SA", "KS", "BA"})

#: Letters whose spoken name starts with a vowel sound, for the indefinite
#: article in front of a legal-form code (e.g. "An ASA", "An NUF", "A KS").
_AN_LETTERS = frozenset("AEFHILMNORSX")

# (term, period_start_month, period_end_month, due_year_offset, due_month, due_day)
_VAT_TERMS: tuple[tuple[int, int, int, int, int, int], ...] = (
    (1, 1, 2, 0, 4, 10),
    (2, 3, 4, 0, 6, 10),
    (3, 5, 6, 0, 8, 31),  # exception: 31 August, not 10 August
    (4, 7, 8, 0, 10, 10),
    (5, 9, 10, 0, 12, 10),
    (6, 11, 12, 1, 2, 10),
)


def _is_subunit(report: CompanyReport) -> bool:
    return report.is_subunit or (report.legal_form_code or "") in _SUBUNIT_CODES


def _is_unclassified_form(report: CompanyReport) -> bool:
    """True when ``legal_form_code`` is missing or not a key of :data:`ORG_FORMS`.

    D-009(a): "never guess a duty" binds the deadline engine, not only the
    duty columns — an unclassified legal form gets no deadlines at all.
    """
    code = report.legal_form_code
    return not code or code.upper() not in ORG_FORMS


def _article(code: str) -> str:
    """"A" or "An" in front of a legal-form code, by its first letter's sound."""
    return "An" if code[:1].upper() in _AN_LETTERS else "A"


def deadline_exemption_note(report: CompanyReport) -> str | None:
    """English sentence explaining why :func:`deadlines_for` returns ``[]`` for
    ``report``, or ``None`` when it would return deadlines.

    Callers (the mapping layer, T03) attach this to ``CompanyReport.notes``.
    Precedence matches :func:`deadlines_for`: status exemptions, then the
    sub-unit exemption, then an unclassified legal form (D-009(a)).
    """
    if report.status is CompanyStatus.DELETED:
        return "This company is deleted from Enhetsregisteret; no filing deadlines are computed."
    if report.status is CompanyStatus.BANKRUPT:
        return (
            "This company is bankrupt; no filing deadlines are computed for an entity in "
            "bankruptcy proceedings."
        )
    if report.status is CompanyStatus.UNDER_COMPULSORY_LIQUIDATION:
        return (
            "This company is under compulsory liquidation; no filing deadlines are computed."
        )
    if _is_subunit(report):
        return (
            "This is a sub-unit, not a legal entity in its own right; look up parent_id for "
            "its filing deadlines."
        )
    if _is_unclassified_form(report):
        label = report.legal_form_code or "(missing)"
        return (
            f"The legal form {label!r} is not classified by registry-mcp, so no filing "
            "deadlines are computed for it. This does not mean none apply — check with an "
            "accountant."
        )
    return None


def _annual_accounts(today: date, holidays: frozenset[date], code: str) -> Deadline:
    statutory = next_occurrence(7, 31, today)
    due = roll_forward(statutory, holidays)
    period = statutory.year - 1
    return Deadline(
        country="NO",
        registry="brreg",
        kind="annual_accounts",
        name="Annual accounts filing",
        local_name="Årsregnskap",
        authority="Regnskapsregisteret",
        statutory_date=statutory,
        due_date=due,
        rolled_forward=due != statutory,
        period_label=str(period),
        period_start=date(period, 1, 1),
        period_end=date(period, 12, 31),
        recurrence=DeadlineRecurrence.ANNUAL,
        applies_because=(
            f"{_article(code)} {code} must file annual accounts with Regnskapsregisteret."
            + _CALENDAR_YEAR_ASSUMPTION
        ),
        days_until=(due - today).days,
    )


def _general_meeting(today: date, holidays: frozenset[date], code: str) -> Deadline:
    statutory = next_occurrence(6, 30, today)
    due = roll_forward(statutory, holidays)
    period = statutory.year - 1
    return Deadline(
        country="NO",
        registry="brreg",
        kind="general_meeting",
        name="Ordinary general meeting",
        local_name="Ordinær generalforsamling",
        authority="Company shareholders (no external filing)",
        statutory_date=statutory,
        due_date=due,
        rolled_forward=due != statutory,
        period_label=str(period),
        period_start=date(period, 1, 1),
        period_end=date(period, 12, 31),
        recurrence=DeadlineRecurrence.ANNUAL,
        applies_because=(
            f"{_article(code)} {code} company must hold an ordinary general meeting within "
            "six months of the financial year end." + _CALENDAR_YEAR_ASSUMPTION
        ),
        days_until=(due - today).days,
    )


def _tax_return(today: date, holidays: frozenset[date], code: str) -> Deadline:
    statutory = next_occurrence(5, 31, today)
    due = roll_forward(statutory, holidays)
    period = statutory.year - 1
    return Deadline(
        country="NO",
        registry="brreg",
        kind="tax_return",
        name="Tax return for businesses",
        local_name="Skattemelding for næringsdrivende",
        authority="Skatteetaten",
        statutory_date=statutory,
        due_date=due,
        rolled_forward=due != statutory,
        period_label=str(period),
        period_start=date(period, 1, 1),
        period_end=date(period, 12, 31),
        recurrence=DeadlineRecurrence.ANNUAL,
        applies_because=(
            f"{_article(code)} {code} must file a tax return (skattemelding) with "
            "Skatteetaten." + _CALENDAR_YEAR_ASSUMPTION
        ),
        days_until=(due - today).days,
    )


def _shareholder_register_statement(today: date, holidays: frozenset[date], code: str) -> Deadline:
    statutory = next_occurrence(1, 31, today)
    due = roll_forward(statutory, holidays)
    period = statutory.year - 1
    return Deadline(
        country="NO",
        registry="brreg",
        kind="shareholder_register_statement",
        name="Shareholder register statement",
        local_name="Aksjonærregisteroppgaven (RF-1086)",
        authority="Skatteetaten",
        statutory_date=statutory,
        due_date=due,
        rolled_forward=due != statutory,
        period_label=str(period),
        period_start=date(period, 1, 1),
        period_end=date(period, 12, 31),
        recurrence=DeadlineRecurrence.ANNUAL,
        applies_because=(
            f"{_article(code)} {code} company must file the shareholder register statement "
            "(RF-1086) with Skatteetaten." + _CALENDAR_YEAR_ASSUMPTION
        ),
        days_until=(due - today).days,
    )


def _vat_return(today: date, holidays: frozenset[date]) -> Deadline:
    candidates: list[tuple[date, int, int, int, int]] = []
    for period_year in (today.year - 1, today.year, today.year + 1):
        for term, start_month, end_month, due_year_offset, due_month, due_day in _VAT_TERMS:
            statutory = date(period_year + due_year_offset, due_month, due_day)
            if statutory >= today:
                candidates.append((statutory, term, period_year, start_month, end_month))
    statutory, term, period_year, start_month, end_month = min(candidates, key=lambda c: c[0])
    due = roll_forward(statutory, holidays)
    period_label = (
        f"{period_year} term {term} ({_MONTH_ABBR[start_month - 1]}–"
        f"{_MONTH_ABBR[end_month - 1]})"
    )
    return Deadline(
        country="NO",
        registry="brreg",
        kind="vat_return",
        name="VAT return",
        local_name="Mva-melding",
        authority="Skatteetaten",
        statutory_date=statutory,
        due_date=due,
        rolled_forward=due != statutory,
        period_label=period_label,
        period_start=date(period_year, start_month, 1),
        period_end=last_day_of_month(period_year, end_month),
        recurrence=DeadlineRecurrence.BIMONTHLY,
        applies_because=(
            "This entity is registered in Merverdiavgiftsregisteret and must file a VAT "
            "return (mva-melding) with Skatteetaten."
        ),
        days_until=(due - today).days,
    )


def _next_fifth_of_month(today: date) -> date:
    candidate = date(today.year, today.month, 5)
    if candidate < today:
        candidate = add_months(candidate, 1)
    return candidate


def _payroll_report(today: date, holidays: frozenset[date]) -> Deadline:
    statutory = _next_fifth_of_month(today)
    due = roll_forward(statutory, holidays)
    period_start = add_months(date(statutory.year, statutory.month, 1), -1)
    period_end = last_day_of_month(period_start.year, period_start.month)
    return Deadline(
        country="NO",
        registry="brreg",
        kind="payroll_report",
        name="Monthly payroll report (A-melding)",
        local_name="A-melding",
        authority="NAV / Skatteetaten (A-ordningen)",
        statutory_date=statutory,
        due_date=due,
        rolled_forward=due != statutory,
        period_label=f"{period_start.year}-{period_start.month:02d}",
        period_start=period_start,
        period_end=period_end,
        recurrence=DeadlineRecurrence.MONTHLY,
        applies_because=(
            "This entity has reported employees and must file the monthly payroll report "
            "(a-melding) with NAV/Skatteetaten."
        ),
        days_until=(due - today).days,
    )


def deadlines_for(report: CompanyReport, today: date) -> list[Deadline]:
    """Compute the Norwegian filing deadlines this entity faces, from ``today``.

    Pure and deterministic — never reads the clock. See ``NORBIZ_SPEC.md`` §5.4
    for the six obligations implemented here and their statutory dates.
    """
    if report.status in _NO_DEADLINE_STATUSES or _is_subunit(report):
        return []
    if _is_unclassified_form(report):
        return []

    # Guaranteed non-None and a key of ORG_FORMS by the check above.
    code = (report.legal_form_code or "").upper()

    holidays = _holidays_spanning(today.year, today.year + 1, today.year + 2)

    deadlines: list[Deadline] = []

    has_accounts_duty = report.has_annual_accounts_duty
    if has_accounts_duty is None:
        has_accounts_duty = legal_form_info(code).has_annual_accounts_duty

    if has_accounts_duty:
        deadlines.append(_annual_accounts(today, holidays, code))
    if code in {"AS", "ASA"}:
        deadlines.append(_general_meeting(today, holidays, code))
    if code in _TAX_RETURN_FORMS:
        deadlines.append(_tax_return(today, holidays, code))
    if code in {"AS", "ASA"}:
        deadlines.append(_shareholder_register_statement(today, holidays, code))
    if report.vat_registered:
        deadlines.append(_vat_return(today, holidays))
    if report.employees is not None and report.employees > 0:
        deadlines.append(_payroll_report(today, holidays))

    deadlines.sort(key=lambda d: (d.due_date, d.kind))
    return deadlines


#: Alias used by ``registries/no/__init__.py :: BrregRegistry.deadlines`` — the
#: ``Registry`` abstract method is named ``deadlines``, but the module-level
#: function keeps the more descriptive ``deadlines_for`` name for its own
#: tests and docs.
deadlines = deadlines_for


def rules_markdown() -> str:
    """Human/LLM readable summary of the Norwegian rules this module implements.

    Served as the MCP resource ``registry://rules/NO`` via
    ``BrregRegistry.rules_markdown`` (T07). Kept short; ``NORBIZ_SPEC.md`` is
    the authoritative, detailed version.
    """
    return (
        "# Norway — Brønnøysundregistrene (Enhetsregisteret)\n\n"
        "## Organisasjonsnummer\n"
        "Nine digits with a MOD11 check digit (weights 3,2,7,6,5,4,3,2 on the "
        "first eight digits). A leading `NO` and a trailing `MVA` (the VAT "
        "form) are stripped before validation.\n\n"
        "## Filing deadlines computed here\n"
        "- `annual_accounts` — 31 July, for legal forms with an annual-accounts "
        "duty (Regnskapsregisteret).\n"
        "- `general_meeting` — 30 June, for AS and ASA.\n"
        "- `tax_return` — 31 May, for every legal form except sub-units "
        "(Skatteetaten).\n"
        "- `shareholder_register_statement` — 31 January, for AS and ASA "
        "(RF-1086).\n"
        "- `vat_return` — bimonthly, for VAT-registered entities. Term 3 "
        "(May-Jun) is due 31 August, not 10 August.\n"
        "- `payroll_report` — monthly, the 5th of the following month, for "
        "entities with reported employees (A-melding).\n\n"
        "All annual deadlines assume a calendar-year accounting period, and a "
        "statutory date falling on a weekend or Norwegian public holiday rolls "
        "forward to the next working day. Bankrupt, deleted or compulsorily "
        "liquidated entities, and sub-units (BEDR, AAFY), get no deadlines. "
        "See NORBIZ_SPEC.md for the full, numbered rule set."
    )
