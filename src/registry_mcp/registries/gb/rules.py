"""UK rules: company-number validation, legal-form duties, status derivation
and filing deadlines.

Everything British lives here, never in ``core/`` (``DECISIONS.md`` D-001).
See ``UK_SPEC.md`` §5, §7, §8 and §14 for the authoritative rules and the
numbered test list this module satisfies (tests 1-72).

``deadlines_for(report, today)`` is a pure function of its two arguments, as
``Registry.deadlines``'s contract requires (``core/registry.py``): no I/O, no
clock reads. Companies House publishes each company's own due dates
(``accounts.next_accounts.due_on``, ``confirmation_statement.next_due``), and
D-016(a) says those beat any computation of ours — ``report.published_deadlines``
(``core/models.py``'s ``PublishedDeadline``, added by D-018) is what carries
them from lookup time, where ``registries/gb/mapping.py`` reads the raw
payload, to here, where they are merged with the computed ladder. Never a
cache round-trip, never the raw payload again.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any, NamedTuple

from registry_mcp.core.models import (
    CompanyReport,
    CompanyStatus,
    Deadline,
    DeadlineRecurrence,
    ErrorCode,
    PublishedDeadline,
    RegistryError,
)
from registry_mcp.core.rules.common import add_months

__all__ = [
    "ACCOUNTS_DUE_ON_SOURCE",
    "ACCOUNTS_KIND",
    "ACCOUNTS_NEXT_DUE_SOURCE",
    "COMPANY_TYPES",
    "CONFIRMATION_KIND",
    "CONFIRMATION_NEXT_DUE_SOURCE",
    "PREFIX_TABLE_AS_OF",
    "LegalFormEntry",
    "LegalFormInfo",
    "StatusResult",
    "deadline_exemption_note",
    "deadlines_for",
    "derive_status",
    "id_caveat",
    "legal_form_info",
    "rules_markdown",
    "validate_crn",
]


# ---------------------------------------------------------------------------
# §5.1 — Identifier validation: shape only, no check digit
# ---------------------------------------------------------------------------

_STRIP_RE = re.compile(r"[\s.\-/]")
_VAT_RE = re.compile(r"^GB\d{9}(\d{3})?$")
_PREFIX_DIGITS_RE = re.compile(r"^([A-Z]{1,2})(\d+)$")
_SHAPE_RE = re.compile(r"^[A-Z0-9]{8}$")


def _invalid(raw: str) -> RegistryError:
    return RegistryError(
        ErrorCode.INVALID_ID,
        f"{raw!r} is not a valid UK company number.",
        hint=(
            "A UK company number is 8 characters: either 8 digits (e.g. 00445790) or a "
            "two-letter prefix and 6 digits (e.g. SC090312 for Scotland, OC303675 for an "
            "LLP). Shorter numbers are zero-padded, so 445790 becomes 00445790. If you have "
            "a company name instead, call search_company."
        ),
        country="GB",
        registry="companies-house",
    )


def _vat_invalid(raw: str) -> RegistryError:
    return RegistryError(
        ErrorCode.INVALID_ID,
        f"{raw!r} is not a valid UK company number.",
        hint=(
            "That looks like a UK VAT registration number, not a company number. The two "
            "are unrelated: a company number is 8 characters, e.g. 00445790. Companies "
            "House does not publish VAT numbers. If you have the company name, call "
            "search_company."
        ),
        country="GB",
        registry="companies-house",
    )


def validate_crn(raw: str) -> str:
    """Normalise and shape-check a UK company registration number (CRN).

    No check digit exists (``UK_SPEC.md`` §5.1), so this checks shape only:
    strip separators, upper-case, zero-pad a short numeric or prefix+digits
    value to 8 characters (never truncate), then require exactly 8 characters
    of ``[A-Z0-9]``, at least one digit, and a leading letter unless the whole
    string is digits. The prefix table is documentation, not a gate — an
    unrecognised-but-well-shaped prefix is accepted (test 25).
    """
    cleaned = _STRIP_RE.sub("", raw).upper()

    if _VAT_RE.match(cleaned):
        raise _vat_invalid(raw)

    if cleaned.isdigit() and 1 <= len(cleaned) <= 8:
        cleaned = cleaned.zfill(8)
    else:
        m = _PREFIX_DIGITS_RE.match(cleaned)
        if m and len(cleaned) < 8:
            letters, digits = m.group(1), m.group(2)
            pad = 8 - len(cleaned)
            cleaned = f"{letters}{'0' * pad}{digits}"

    if (
        _SHAPE_RE.match(cleaned) is not None
        and any(c.isdigit() for c in cleaned)
        and (cleaned.isdigit() or cleaned[0].isalpha())
    ):
        return cleaned
    raise _invalid(raw)


#: §5.1.2 prefix table, compiled 2026-09 — documentation only (D-015): never a
#: validation gate, consulted only by :func:`id_caveat` to say what we do not
#: know about an already-valid number, never to reject one. Two-character
#: prefixes; `"R0"` is the one letter-plus-digit prefix, and its two literal
#: characters already occupy the same two positions this set is keyed on.
_KNOWN_PREFIXES = frozenset(
    {
        "SC", "NI", "R0", "OC", "SO", "NC", "LP", "SL", "NL", "FC", "SF", "NF",
        "BR", "OE", "AC", "SA", "NA", "ZC", "SZ", "NZ", "RC", "SR", "NR", "IP",
        "SP", "NP", "NO", "RS", "IC", "SI", "NV", "CE", "CS", "SE", "ES", "EN",
        "GE", "GS", "GN", "SG", "FE", "PC",
    }
)
#: As-of date quoted in the caveat sentence, so a reader can tell a stale
#: table from a bad number (D-021).
PREFIX_TABLE_AS_OF = "2026-09"


def id_caveat(id: str) -> str | None:
    """A caveat about an already-normalised, valid CRN's prefix (D-021).

    All-digit numbers (England & Wales, no prefix) get no caveat. A prefix
    not in :data:`_KNOWN_PREFIXES` gets one naming the prefix, the as-of
    date, and the call that settles it — never a rejection, since D-015
    already ruled the table documentation, not a gate: Companies House adds
    prefixes (``OE`` arrived with ECTEA 2022), and a caveat lets an agent
    tell "shape is fine, provenance is unconfirmed" from "this is wrong"
    without us guessing which one is true.
    """
    if id.isdigit():
        return None
    prefix = id[:2]
    if prefix in _KNOWN_PREFIXES:
        return None
    return (
        f"Prefix {prefix!r} is not in the Companies House prefix list this module knows "
        f"as of {PREFIX_TABLE_AS_OF}; call lookup_company to confirm whether the number "
        "exists."
    )


# ---------------------------------------------------------------------------
# §7 — Legal-form table
# ---------------------------------------------------------------------------


class LegalFormEntry(NamedTuple):
    """One row of the legal-form table. ``None`` means "depends on facts the
    register does not publish"."""

    english: str
    limited_liability: bool | None
    has_board_duty: bool | None
    has_annual_accounts_duty: bool | None
    #: ``("private", 9)`` / ``("public", 6)`` when this module computes a
    #: fallback accounts period; ``None`` when it does not (§5.4 step 3).
    accounts_period: tuple[str, int] | None = None


#: Companies House ``type`` -> duties (``UK_SPEC.md`` §7). Confirmed forms
#: first, then classified forms with no computed accounts period.
COMPANY_TYPES: dict[str, LegalFormEntry] = {
    "ltd": LegalFormEntry("Private limited company", True, True, True, ("private", 9)),
    "plc": LegalFormEntry("Public limited company", True, True, True, ("public", 6)),
    "llp": LegalFormEntry("Limited liability partnership", True, None, True, ("private", 9)),
    "private-limited-guarant-nsc": LegalFormEntry(
        "Private company limited by guarantee without share capital",
        True,
        True,
        True,
        ("private", 9),
    ),
    "private-limited-guarant-nsc-limited-exemption": LegalFormEntry(
        "Private company limited by guarantee, exempt from using 'limited'",
        True,
        True,
        True,
        ("private", 9),
    ),
    "private-limited-shares-section-30-exemption": LegalFormEntry(
        "Private company limited by shares, section 30 exemption", True, True, True, ("private", 9)
    ),
    "uk-establishment": LegalFormEntry(
        "UK establishment of an overseas company", None, False, False, None
    ),
    # Classified, but no computed accounts period (UK_SPEC.md §7 second table).
    "private-unlimited": LegalFormEntry(
        "Private unlimited company with share capital", False, True, None
    ),
    "private-unlimited-nsc": LegalFormEntry(
        "Private unlimited company without share capital", False, True, None
    ),
    "old-public-company": LegalFormEntry("Old public company", True, True, None),
    "limited-partnership": LegalFormEntry("Limited partnership", None, False, None),
    "scottish-partnership": LegalFormEntry("Scottish partnership", False, False, None),
    "charitable-incorporated-organisation": LegalFormEntry(
        "Charitable incorporated organisation", True, None, None
    ),
    "scottish-charitable-incorporated-organisation": LegalFormEntry(
        "Scottish charitable incorporated organisation", True, None, None
    ),
    "registered-society-non-jurisdictional": LegalFormEntry("Registered society", True, None, None),
    "industrial-and-provident-society": LegalFormEntry(
        "Industrial and provident society", True, None, None
    ),
    "oversea-company": LegalFormEntry("Overseas company", None, None, None),
    "registered-overseas-entity": LegalFormEntry(
        "Overseas entity (register of overseas entities)", None, None, None
    ),
    "european-public-limited-liability-company-se": LegalFormEntry(
        "European company (Societas Europaea)", True, True, None
    ),
    "royal-charter": LegalFormEntry("Royal charter body", None, None, None),
    "unregistered-company": LegalFormEntry("Unregistered company", None, None, None),
    "northern-ireland": LegalFormEntry("Northern Ireland company (legacy record)", None, None, None),
    "northern-ireland-other": LegalFormEntry(
        "Northern Ireland entity (legacy record)", None, None, None
    ),
    "investment-company-with-variable-capital": LegalFormEntry(
        "Investment company with variable capital", True, None, None
    ),
    "icvc-securities": LegalFormEntry("ICVC — securities", True, None, None),
    "icvc-warrant": LegalFormEntry("ICVC — warrant", True, None, None),
    "icvc-umbrella": LegalFormEntry("ICVC — umbrella", True, None, None),
    "protected-cell-company": LegalFormEntry("Protected cell company", True, None, None),
    "assurance-company": LegalFormEntry("Assurance company", None, None, None),
    "eeig": LegalFormEntry("European economic interest grouping", False, None, None),
    "further-education-or-sixth-form-college-corporation": LegalFormEntry(
        "Further education or sixth form college corporation", None, None, None
    ),
    "converted-or-closed": LegalFormEntry("Converted or closed entity", None, None, None),
    "other": LegalFormEntry("Other", None, None, None),
}

#: Subtype -> label fragment appended to the base ``legal_form`` in parentheses.
_SUBTYPE_LABELS: dict[str, str] = {
    "community-interest-company": "community interest company",
    "private-fund-limited-partnership": "private fund limited partnership",
}

_CIC_NOTE = (
    "This is a community interest company. It must file a CIC34 community interest company "
    "report alongside its annual accounts, and its assets are subject to an asset lock."
)


class LegalFormInfo(NamedTuple):
    """Result of looking up a Companies House ``type`` (+ optional ``subtype``)."""

    code: str
    english: str | None
    limited_liability: bool | None
    has_board_duty: bool | None
    has_annual_accounts_duty: bool | None
    accounts_period: tuple[str, int] | None
    notes: list[str]


def legal_form_info(type_code: str, subtype: str | None = None) -> LegalFormInfo:
    """Look up the duties for a Companies House ``type``.

    An unlisted ``type`` maps to ``english=None``, all duty fields ``None``,
    no computed period, and a note saying the form is not classified — never
    guess a duty (D-009 applied to Britain).
    """
    key = (type_code or "").strip().lower()
    entry = COMPANY_TYPES.get(key)
    if entry is None:
        return LegalFormInfo(
            code=key,
            english=None,
            limited_liability=None,
            has_board_duty=None,
            has_annual_accounts_duty=None,
            accounts_period=None,
            notes=[
                f"The legal form {key!r} is not classified by registry-mcp; its duties are "
                "unknown, not absent."
            ],
        )

    english = entry.english
    notes: list[str] = []
    if subtype and subtype in _SUBTYPE_LABELS:
        english = f"{english} ({_SUBTYPE_LABELS[subtype]})"
        if subtype == "community-interest-company":
            notes.append(_CIC_NOTE)

    return LegalFormInfo(
        code=key,
        english=english,
        limited_liability=entry.limited_liability,
        has_board_duty=entry.has_board_duty,
        has_annual_accounts_duty=entry.has_annual_accounts_duty,
        accounts_period=entry.accounts_period,
        notes=notes,
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


#: ``company_status`` values whose status/detail is a fixed pair — everything
#: except the three date-carrying "ended" values, handled separately below.
_STATUS_MAP: dict[str, tuple[CompanyStatus, str]] = {
    "active": (CompanyStatus.ACTIVE, "Active on the Companies House register."),
    "liquidation": (
        CompanyStatus.UNDER_LIQUIDATION,
        "In liquidation. Companies House does not say whether the liquidation is "
        "voluntary or compulsory.",
    ),
    "receivership": (
        CompanyStatus.UNDER_LIQUIDATION,
        "In receivership: a receiver has been appointed over the company's assets.",
    ),
    "administration": (
        CompanyStatus.UNDER_LIQUIDATION,
        "In administration: an administrator is running the company.",
    ),
    "voluntary-arrangement": (
        CompanyStatus.UNDER_LIQUIDATION,
        "Subject to a company voluntary arrangement with its creditors.",
    ),
    "insolvency-proceedings": (
        CompanyStatus.UNDER_LIQUIDATION,
        "Subject to insolvency proceedings.",
    ),
    "removed": (CompanyStatus.DELETED, "Removed from the register."),
    "registered": (CompanyStatus.ACTIVE, "Registered on the register of overseas entities."),
    "open": (CompanyStatus.ACTIVE, "Open on the register."),
}

#: ``company_status`` values that map to DISSOLVED with a date-carrying detail.
_DISSOLVED_DETAIL: dict[str, str] = {
    "dissolved": "Dissolved on {date}. The record remains on the register as history.",
    "converted-closed": "Converted or closed on {date}.",
    "closed": "Closed on {date}.",
}
_DISSOLVED_DETAIL_NO_DATE: dict[str, str] = {
    "dissolved": "Dissolved. The record remains on the register as history.",
    "converted-closed": "Converted or closed.",
    "closed": "Closed.",
}

_STATUS_DETAIL_NOTES: dict[str, str] = {
    "active-proposal-to-strike-off": (
        "Companies House has published a proposal to strike this company off the register. "
        "It is still active today, but it may be dissolved within about two months unless "
        "the proposal is suspended. Do not treat it as a stable counterparty without "
        "checking the filing history."
    ),
    "transferred-from-uk": "This company was transferred from the UK register.",
    "petition-to-restore-dissolved": (
        "A petition to restore this dissolved company to the register has been made."
    ),
    "transformed-to-se": "This company was transformed into a European company (SE).",
    "converted-to-plc": "This company was converted to a public limited company.",
}


def _status_detail_note(value: str) -> str:
    if value in _STATUS_DETAIL_NOTES:
        return _STATUS_DETAIL_NOTES[value]
    return f"Companies House records an additional status detail for this company: {value}."


def derive_status(
    *,
    company_status: str | None,
    company_status_detail: str | None = None,
    date_of_cessation: date | None = None,
) -> StatusResult:
    """Derive :class:`CompanyStatus` from ``company_status`` alone (``UK_SPEC.md`` §8).

    One value to one status, no precedence chain: Companies House publishes a
    single status rather than Norway's independent booleans.
    ``UNDER_COMPULSORY_LIQUIDATION`` and ``BANKRUPT`` are never emitted for GB
    (§8 points 1-2) — the register does not distinguish either.
    """
    notes: list[str] = []

    if not company_status:
        status = CompanyStatus.UNKNOWN
        detail = "Companies House holds no status for this record."
        is_active = False
    else:
        key = company_status.strip().lower()
        if key in _DISSOLVED_DETAIL:
            status = CompanyStatus.DISSOLVED
            is_active = False
            if date_of_cessation is not None:
                detail = _DISSOLVED_DETAIL[key].format(date=date_of_cessation.isoformat())
            else:
                detail = _DISSOLVED_DETAIL_NO_DATE[key]
        elif key in _STATUS_MAP:
            status, detail = _STATUS_MAP[key]
            is_active = status is CompanyStatus.ACTIVE
        else:
            status = CompanyStatus.UNKNOWN
            detail = f"Companies House returned a status this module does not recognise ({company_status!r})."
            is_active = False

    if status is not CompanyStatus.ACTIVE:
        notes.append(detail)

    if company_status_detail:
        notes.append(_status_detail_note(company_status_detail))

    return StatusResult(status=status, status_detail=detail, is_active=is_active, notes=notes)


# ---------------------------------------------------------------------------
# §5.4 — Filing deadlines
# ---------------------------------------------------------------------------

ACCOUNTS_KIND = "annual_accounts"
CONFIRMATION_KIND = "confirmation_statement"

_ACCOUNTS_SOURCE_URL = (
    "https://www.gov.uk/government/publications/life-of-a-company-annual-requirements/"
    "life-of-a-company-part-1-accounts"
)
_CONFIRMATION_SOURCE_URL = "https://www.gov.uk/guidance/confirmation-statement-guidance"

#: An arbitrary, fixed anchor date used only to ask "would a deadline of this
#: *kind* be reachable for this report at all?" — never to compute an actual
#: due date, since which ladder rung applies never depends on ``today`` (only
#: ``days_until`` and the overdue-disagreement caveat do). Mirrors
#: ``registries/no/mapping.py``'s ``_DEADLINE_ELIGIBILITY_PROBE_DATE``.
_PROBE_DATE = date(2000, 1, 1)

_OVERDUE_DISAGREEMENT_NOTE = (
    " Companies House flags this filing as overdue, but the due date it publishes ({due}) is "
    "not yet past relative to today ({today}). The register's own view may be more current "
    "than this cached record."
)


def _is_unclassified_form(report: CompanyReport) -> bool:
    code = report.legal_form_code
    return not code or code.strip().lower() not in COMPANY_TYPES


#: Opaque `PublishedDeadline.source` values `registries/gb/mapping.py` writes.
#: Used only here to choose which "published" sentence to quote (rung 1 vs
#: the deprecated rung 2 for accounts); never interpreted by `core/`.
ACCOUNTS_DUE_ON_SOURCE = "accounts.next_accounts.due_on"
ACCOUNTS_NEXT_DUE_SOURCE = "accounts.next_due"
CONFIRMATION_NEXT_DUE_SOURCE = "confirmation_statement.next_due"


def _accounts_deadline(
    published: PublishedDeadline | None, report: CompanyReport, today: date
) -> Deadline | None:
    due_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    overdue = False
    applies_because = ""

    if published is not None:
        period_start = published.period_start
        period_end = published.period_end
        overdue = bool(published.overdue)
        if published.due_date is not None:
            due_date = published.due_date
            applies_because = (
                "Companies House publishes this date for the company itself; it is the "
                "register's own figure, not a calculation."
            )
            if published.source == ACCOUNTS_NEXT_DUE_SOURCE:
                applies_because += " (From the deprecated `accounts.next_due` field.)"

    if due_date is None:
        if period_end is None:
            return None
        info = legal_form_info(report.legal_form_code or "")
        period = info.accounts_period
        if period is None:
            return None
        kind_label, months = period
        due_date = add_months(period_end, months)
        applies_because = (
            f"Computed: a {kind_label} company must deliver accounts within "
            f"{months} months of the end of the accounting reference period "
            "(Companies Act 2006 s.442). Companies House did not publish a due date "
            "for this company."
        )

    period_label = f"period ending {period_end.isoformat()}" if period_end else None

    days_until = (due_date - today).days
    if overdue and days_until >= 0:
        applies_because += _OVERDUE_DISAGREEMENT_NOTE.format(
            due=due_date.isoformat(), today=today.isoformat()
        )

    return Deadline(
        country="GB",
        registry="companies-house",
        kind=ACCOUNTS_KIND,
        name="Annual accounts filing",
        local_name="Annual accounts",
        authority="Companies House",
        statutory_date=due_date,
        due_date=due_date,
        rolled_forward=False,
        period_label=period_label,
        period_start=period_start,
        period_end=period_end,
        recurrence=DeadlineRecurrence.ANNUAL,
        mandatory=True,
        applies_because=applies_because,
        days_until=days_until,
        source_url=_ACCOUNTS_SOURCE_URL,
    )


def _confirmation_deadline(
    published: PublishedDeadline | None, report: CompanyReport, today: date
) -> Deadline | None:
    due_date: date | None = None
    period_end: date | None = None
    overdue = False
    applies_because = ""

    if published is not None:
        period_end = published.period_end
        overdue = bool(published.overdue)
        if published.due_date is not None:
            due_date = published.due_date
            applies_because = (
                "Companies House publishes this date for the company itself; it is the "
                "register's own figure, not a calculation."
            )

    if due_date is None:
        if period_end is None:
            return None
        due_date = period_end + timedelta(days=14)
        applies_because = (
            "Computed: a confirmation statement may be filed up to 14 days after the end "
            "of the review period (GOV.UK confirmation statement guidance)."
        )

    period_start: date | None = None
    if period_end is not None:
        try:
            period_start = period_end.replace(year=period_end.year - 1) + timedelta(days=1)
        except ValueError:
            period_start = None

    days_until = (due_date - today).days
    if overdue and days_until >= 0:
        applies_because += _OVERDUE_DISAGREEMENT_NOTE.format(
            due=due_date.isoformat(), today=today.isoformat()
        )

    return Deadline(
        country="GB",
        registry="companies-house",
        kind=CONFIRMATION_KIND,
        name="Confirmation statement",
        local_name="Confirmation statement (CS01)",
        authority="Companies House",
        statutory_date=due_date,
        due_date=due_date,
        rolled_forward=False,
        period_label=(f"review period ending {period_end.isoformat()}" if period_end else None),
        period_start=period_start,
        period_end=period_end,
        recurrence=DeadlineRecurrence.ANNUAL,
        mandatory=True,
        applies_because=applies_because,
        days_until=days_until,
        source_url=_CONFIRMATION_SOURCE_URL,
    )


def deadlines_for(report: CompanyReport, today: date) -> list[Deadline]:
    """Compute the two UK filing deadlines this entity faces, from ``today``.

    Pure function of ``(report, today)``: no I/O, no clock reads
    (``core/registry.py``'s ``Registry.deadlines`` contract). The register's
    own published dates travel on ``report.published_deadlines``
    (``DECISIONS.md`` D-018), filled by ``registries/gb/mapping.py`` at
    lookup time from the raw payload — this function never sees that payload.

    Deadlines are emitted only for an ``ACTIVE``, non-sub-unit, classified
    entity (D-009(a) applied to Britain; stricter than Norway for status,
    since GB's ``company_status`` cannot distinguish voluntary from
    compulsory liquidation, ``UK_SPEC.md`` §5.4).
    """
    if report.status is not CompanyStatus.ACTIVE:
        return []
    if report.is_subunit:
        return []
    if _is_unclassified_form(report):
        return []

    published = {pd.kind: pd for pd in report.published_deadlines}
    deadlines: list[Deadline] = []

    accounts_dl = _accounts_deadline(published.get(ACCOUNTS_KIND), report, today)
    if accounts_dl is not None:
        deadlines.append(accounts_dl)

    confirmation_dl = _confirmation_deadline(published.get(CONFIRMATION_KIND), report, today)
    if confirmation_dl is not None:
        deadlines.append(confirmation_dl)

    deadlines.sort(key=lambda d: (d.due_date, d.kind))
    return deadlines


_NO_ACCOUNTS_DATE_NOTE = (
    "Companies House publishes no next-accounts date for this company and its legal form "
    "({type}) has no accounts-filing period this module is confident about, so no accounts "
    "deadline is given. Read `accounts` on the company report directly."
)
_NO_CONFIRMATION_DATE_NOTE = (
    "Companies House publishes no confirmation-statement date for this company, so no "
    "confirmation statement deadline is given. Read `confirmation_statement` on the company "
    "report directly."
)
_STATUS_SUPPRESSES_DEADLINES_NOTE = (
    "This company's Companies House status is {status!r}, so no filing deadlines are given. "
    "Once a company is dissolved, in liquidation, in administration or under a voluntary "
    "arrangement, what must still be filed is decided by the insolvency practitioner or the "
    "registrar and is not derivable from the public register."
)


def deadline_exemption_note(data: Mapping[str, Any] | None, report: CompanyReport) -> list[str]:
    """English sentence(s) explaining why :func:`deadlines_for` returns an
    empty or shorter list than expected for ``report`` — attached to
    ``CompanyReport.notes`` at map time (``UK_SPEC.md`` §2.1).

    Called from ``registries/gb/mapping.py`` *after* ``report`` has been
    built with ``published_deadlines`` already set, so the per-kind "no date"
    check below reuses :func:`deadlines_for` itself (via the probe date)
    rather than re-deriving anything from ``data``. ``data`` is kept only for
    the two raw strings (``company_status``, ``type``) that make the
    sentences concrete.

    The sub-unit and unclassified-legal-form cases already get their own note
    from ``registries/gb/mapping.py`` at map time, so nothing is added here
    for them — this only covers the status gate and the two per-kind "no
    published or computable date" cases.
    """
    if report.status is not CompanyStatus.ACTIVE:
        raw_status = (data or {}).get("company_status") or "unknown"
        return [_STATUS_SUPPRESSES_DEADLINES_NOTE.format(status=raw_status)]

    if report.is_subunit or _is_unclassified_form(report):
        return []

    kinds_present = {d.kind for d in deadlines_for(report, _PROBE_DATE)}
    notes: list[str] = []
    if ACCOUNTS_KIND not in kinds_present:
        notes.append(_NO_ACCOUNTS_DATE_NOTE.format(type=(data or {}).get("type")))
    if CONFIRMATION_KIND not in kinds_present:
        notes.append(_NO_CONFIRMATION_DATE_NOTE)
    return notes


# ---------------------------------------------------------------------------
# §13 — rules_markdown()
# ---------------------------------------------------------------------------


def rules_markdown() -> str:
    """Human/LLM readable summary of the UK rules this module implements.

    Served as the MCP resource ``registry://rules/GB`` via
    ``CompaniesHouseRegistry.rules_markdown``. ``UK_SPEC.md`` is the
    authoritative, detailed version.
    """
    return (
        "# United Kingdom — Companies House\n\n"
        "Companies House is the United Kingdom's registrar of companies, an executive "
        "agency of the Department for Business and Trade. Register data is not published "
        "under the Open Government Licence; it is made available under section 47 of the "
        "Copyright, Designs and Patents Act 1988 and Schedule 1 of the Database Regulations "
        "1997, free to re-use with no rules imposed on how it is used.\n\n"
        "**Sole traders and ordinary (unlimited) partnerships are not registered here at "
        "all.** A search for one will correctly return no hits.\n\n"
        "## Company number\n"
        "8 characters: either 8 digits, zero-padded (445790 -> 00445790), or a two-letter "
        "prefix and 6 digits (SC090312 for Scotland, OC303675 for an LLP, and more — "
        "the prefix table is documentation, Companies House adds prefixes over time). "
        "**There is no check digit.** A well-formed number is not evidence that a company "
        "exists or is active — call lookup_company to find out.\n\n"
        "## Deadlines do not move for weekends or bank holidays\n"
        "GOV.UK: \"If your filing deadline falls on a Sunday or a bank holiday, it is still "
        "a legal requirement to file your accounts by that date.\" Every GB deadline has "
        "`statutory_date == due_date` and `rolled_forward` is always `False` — the "
        "opposite of the Norwegian rule this same server also serves.\n\n"
        "## Filing deadlines computed here\n"
        "Only two kinds, and Companies House's own published dates beat any calculation of "
        "ours whenever it publishes one (`accounts.next_accounts.due_on`, "
        "`confirmation_statement.next_due`) — those figures already account for "
        "accounting-reference-date changes and shortened/extended periods that this module "
        "cannot see.\n"
        "- `annual_accounts` — published date if given, else computed as 9 months "
        "(private company) or 6 months (public company) after the accounting reference "
        "period ends (Companies Act 2006 s.442), only for a legal form this module has "
        "classified with a period.\n"
        "- `confirmation_statement` — published date if given, else computed as 14 "
        "days after the review period ends (GOV.UK confirmation statement guidance).\n\n"
        "Deadlines are emitted only when the company's status is active, and never for a "
        "UK establishment of an overseas company (a sub-unit — look up its parent "
        "instead) or a legal form this module has not classified.\n\n"
        "First accounts after incorporation (21 months private / 18 months public from "
        "incorporation, or 3 months from the accounting reference date, whichever is "
        "longer) are documented but not computed: Companies House's own `due_on` already "
        "answers this correctly from the day a company is incorporated.\n\n"
        "## Corporation tax (not computed — HMRC's, not Companies House's)\n"
        "The Company Tax Return (CT600) is due 12 months after the accounting period for "
        "Corporation Tax ends; payment is due 9 months and 1 day after it ends. Companies "
        "House does not publish the HMRC accounting period (which need not match the "
        "Companies House accounting reference period), whether an entity is within the "
        "charge to corporation tax at all (an LLP is tax-transparent and files no CT600), "
        "or the profit figure that decides whether quarterly instalments apply instead of "
        "the 9-months-and-1-day rule — so this module states the rules but emits no date.\n\n"
        "## What Companies House does not publish\n"
        "Employee counts, VAT registration, turnover, share capital, email, phone and "
        "website. Officers, persons with significant control, charges and filing history "
        "are separate endpoints this module does not yet expose.\n"
    )
