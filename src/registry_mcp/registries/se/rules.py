"""Swedish rules: identitetsbeteckning validation, legal-form duties, status
derivation and filing deadlines.

Everything Swedish lives here, never in ``core/`` (``DECISIONS.md`` D-001).
See ``SWEDEN_SPEC.md`` §5, §7, §8 and §14 for the authoritative rules, and
§14 for the numbered test list this module satisfies (tests 1-78).

Pure and synchronous: no I/O, no clock reads. ``deadlines_for(report, today)``
takes ``today`` as a parameter precisely so it stays testable and so
``Registry.deadlines``'s contract (``core/registry.py``) holds.
"""

from __future__ import annotations

import re
from datetime import date
from typing import NamedTuple

from registry_mcp.core.models import (
    CompanyReport,
    CompanyStatus,
    Deadline,
    DeadlineRecurrence,
    ErrorCode,
    FiledDocument,
    FilingHistory,
    RegistryError,
)
from registry_mcp.core.rules.common import next_occurrence

__all__ = [
    "AS_OF",
    "DEADLINE_FORM_CODES",
    "ORGANISATION_FORMS",
    "RULES_LAST_REVIEWED",
    "LegalFormEntry",
    "LegalFormInfo",
    "StatusResult",
    "deadlines_for",
    "derive_status",
    "format_id",
    "id_caveat",
    "legal_form_info",
    "modulus10_ok",
    "rules_markdown",
    "validate_id",
]

#: The date this module's statutes and day-count arithmetic were last checked
#: against the law — verified live by T26/T44 (`DECISIONS.md` D-022, D-023,
#: D-041). Surfaced at the top of `rules_markdown()` and, via
#: `BolagsverketRegistry.rules_last_reviewed`, on every `DeadlineReport` (T62).
RULES_LAST_REVIEWED = date(2026, 9, 8)

# ---------------------------------------------------------------------------
# §5.1 — identitetsbeteckning validation: shape only, no check digit
# ---------------------------------------------------------------------------

#: Whitespace (including the non-breaking space U+00A0, matched by \s in a
#: Unicode pattern), dot, hyphen, slash and plus (the over-100 personnummer
#: separator) — stripped before anything else (§5.1 step 1).
_STRIP_RE = re.compile(r"[\s.\-/+]")
_VAT_RE = re.compile(r"^SE(\d{12})$")
_TEN_DIGITS_RE = re.compile(r"^\d{10}$")
_TWELVE_DIGITS_RE = re.compile(r"^\d{12}$")
_NINE_DIGITS_RE = re.compile(r"^\d{9}$")
_ELEVEN_DIGITS_RE = re.compile(r"^\d{11}$")

_DEFAULT_HINT = (
    "A Swedish organisationsnummer is ten digits with a check digit, written 556016-0680 "
    "or 5560160680. A sole trader is looked up by a twelve-digit personnummer "
    "(YYYYMMDDNNNN). Bolagsverket's free API cannot search by name."
)
_NORWAY_HINT = (
    "That is nine digits, which is the length of a Norwegian organisasjonsnummer, not a "
    "Swedish one. Swedish numbers are ten digits (e.g. 5560160680). If the company is "
    "Norwegian, call the same tool with country 'NO'."
)
_VAT_HINT = (
    "That looks like a Swedish VAT number — SE, then the ten-digit organisationsnummer, "
    "then 01. Call this tool with the ten middle digits: for SE556016068001 that is "
    "5560160680."
)
_PERSONNUMMER_HINT = (
    "A Swedish personnummer must be given in full, with the century and a real date: "
    "19400927-2719, not 400927-2719. Bolagsverket's API takes twelve digits for a person "
    "and ten for an organisation."
)


def _invalid(raw: str, hint: str) -> RegistryError:
    return RegistryError(
        ErrorCode.INVALID_ID,
        f"{raw!r} is not a valid Swedish identitetsbeteckning.",
        hint=hint,
        country="SE",
        registry="bolagsverket",
    )


def _twelve_digit_date_shape_ok(cleaned: str) -> bool:
    """YYYYMMDDNNNN: month 01-12; day 01-31 (personnummer) or 61-91
    (samordningsnummer, whose 'DD' is the birth day + 60). The schema names
    both widths (§5.1); this is the date-shape half of that description."""
    month = int(cleaned[4:6])
    if not 1 <= month <= 12:
        return False
    day = int(cleaned[6:8])
    return 1 <= day <= 31 or 61 <= day <= 91


def validate_id(raw: str) -> str:
    """Normalise and shape-check a Swedish identitetsbeteckning (§5.1).

    Ten digits (organisationsnummer, or a GD-nummer beginning ``302``) or
    twelve digits in ``YYYYMMDDNNNN`` form (personnummer, or a
    samordningsnummer) are accepted. **No check digit is enforced** — D-032
    rules that the register is the authority on its own check digit (§5.1.1);
    a failing modulus-10 result surfaces only as a caveat on a valid result
    (:func:`id_caveat`), never a rejection here.
    """
    cleaned = _STRIP_RE.sub("", raw).upper()

    vat_match = _VAT_RE.match(cleaned)
    if vat_match and vat_match.group(1).endswith("01"):
        cleaned = vat_match.group(1)[:-2]
    elif cleaned.startswith("SE"):
        raise _invalid(raw, _VAT_HINT)

    if _TEN_DIGITS_RE.match(cleaned):
        return cleaned
    if _TWELVE_DIGITS_RE.match(cleaned):
        if _twelve_digit_date_shape_ok(cleaned):
            return cleaned
        raise _invalid(raw, _PERSONNUMMER_HINT)
    if _NINE_DIGITS_RE.match(cleaned):
        raise _invalid(raw, _NORWAY_HINT)
    if _ELEVEN_DIGITS_RE.match(cleaned):
        raise _invalid(raw, _PERSONNUMMER_HINT)
    raise _invalid(raw, _DEFAULT_HINT)


# ---------------------------------------------------------------------------
# §5.1.4 — format_id
# ---------------------------------------------------------------------------


def format_id(id: str) -> str | None:
    """``"5560160680"`` -> ``"556016-0680"``; ``"194009272719"`` ->
    ``"19400927-2719"``. Anything else -> ``None``. Cosmetic only (§5.1.4,
    ``VERIFY`` — the hyphen convention has no primary source but the API
    itself never uses it either way)."""
    if len(id) == 10 and id.isdigit():
        return f"{id[:6]}-{id[6:]}"
    if len(id) == 12 and id.isdigit():
        return f"{id[:8]}-{id[8:]}"
    return None


# ---------------------------------------------------------------------------
# §5.1.1 / §5.1.5 — the modulus-10 caveat (D-021)
# ---------------------------------------------------------------------------

#: As-of date for the id_caveat sentence (D-021) — lets a reader tell a stale
#: rule from a bad number.
AS_OF = "2026-09"


def _luhn_check_digit(nine_digits: str) -> int:
    """Modulus-10 (Luhn) check digit over ``nine_digits``, leftmost doubled."""
    total = 0
    for index, char in enumerate(nine_digits):
        digit = int(char)
        if index % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return (10 - (total % 10)) % 10


def modulus10_ok(ten_digits: str) -> bool:
    """The unsourced modulus-10 rule (§5.1.1), computed but never enforced.

    Takes exactly ten digits: the organisationsnummer itself, or the last ten
    digits of a twelve-digit personnummer/samordningsnummer (the century
    stripped). Returns ``False`` for anything not shaped like ten digits,
    rather than raising — this is a caveat computation, not a validator.
    """
    if len(ten_digits) != 10 or not ten_digits.isdigit():
        return False
    return _luhn_check_digit(ten_digits[:9]) == int(ten_digits[9])


_PERSONNUMMER_CAVEAT = (
    "Twelve digits is a personnummer or samordningsnummer, which Sweden uses as a sole "
    "trader's identifier. It identifies a natural person, and one such number can carry "
    "several registered businesses; only lookup_company can say which."
)
_CHECK_DIGIT_CAVEAT = (
    "Note that this number does not satisfy the modulus-10 check digit that Swedish "
    "identifiers are generally described as carrying. registry-mcp has not been able to "
    f"confirm that rule against a primary source, as of {AS_OF}, so the number is not "
    "rejected here — but Bolagsverket validates a check digit server-side and may answer "
    "'Identitetsbeteckning har ogiltig kontrollsiffra'. Check the digits before relying on it."
)


def id_caveat(id: str) -> str | None:
    """D-021 applied to Sweden (§5.1.5): two sentences, each only when it
    applies, appended to a **valid** ``ValidationResult.reason`` — never to
    ``hint``. Nothing is said when the modulus-10 check passes: a passing
    unverified check adds no information."""
    parts: list[str] = []
    if len(id) == 12:
        parts.append(_PERSONNUMMER_CAVEAT)
    check_subject = id[2:] if len(id) == 12 else id
    if not modulus10_ok(check_subject):
        parts.append(_CHECK_DIGIT_CAVEAT)
    return " ".join(parts) if parts else None


# ---------------------------------------------------------------------------
# §7 — legal-form table
# ---------------------------------------------------------------------------


class LegalFormEntry(NamedTuple):
    """One row of the ``organisationsform`` table. ``None`` means "depends on
    facts the register does not publish" (or, for ``limited_liability``,
    "partly" — a Kommanditbolag has both limited and unlimited partners)."""

    swedish: str
    english: str
    limited_liability: bool | None
    has_board_duty: bool | None
    has_annual_accounts_duty: bool | None


#: Bolagsverket's ``ORGANISATIONSFORM`` code list (§7, T26-recon), complete —
#: 29 codes. English labels and duty columns are ours. Only ``AB``/``EK``
#: (`DEADLINE_FORM_CODES`) get a computed accounts period; the rest are
#: classified but compute nothing (§7.3, D-009).
ORGANISATION_FORMS: dict[str, LegalFormEntry] = {
    "AB": LegalFormEntry("Aktiebolag", "Private or public limited company", True, True, True),
    "EK": LegalFormEntry(
        "Ekonomisk förening", "Economic (co-operative) association", True, True, True
    ),
    "E": LegalFormEntry("Enskild näringsverksamhet", "Sole trader", False, False, None),
    "HB": LegalFormEntry("Handelsbolag", "General partnership", False, False, None),
    "KB": LegalFormEntry("Kommanditbolag", "Limited partnership", None, False, None),
    "EB": LegalFormEntry(
        "Enkla bolag", "Simple partnership (not a legal person)", False, False, None
    ),
    "BRF": LegalFormEntry(
        "Bostadsrättsförening", "Tenant-owners' (housing) association", True, True, None
    ),
    "KHF": LegalFormEntry(
        "Kooperativ hyresrättsförening", "Co-operative rental-tenancy association", True, True, None
    ),
    "BF": LegalFormEntry("Bostadsförening", "Housing association", True, True, None),
    "SF": LegalFormEntry("Sambruksförening", "Joint-farming association", True, True, None),
    "S": LegalFormEntry(
        "Stiftelse som bedriver näringsverksamhet",
        "Foundation carrying on business",
        True,
        None,
        None,
    ),
    "I": LegalFormEntry(
        "Ideell förening som bedriver näringsverksamhet",
        "Non-profit association carrying on business",
        True,
        None,
        None,
    ),
    "TSF": LegalFormEntry(
        "Trossamfund som bedriver näringsverksamhet",
        "Registered religious community carrying on business",
        True,
        None,
        None,
    ),
    "FL": LegalFormEntry("Filial", "Branch of a foreign company", None, None, None),
    "BFL": LegalFormEntry("Utländsk banks filial", "Branch of a foreign bank", None, None, None),
    "BAB": LegalFormEntry("Bankaktiebolag", "Bank (limited company)", True, True, None),
    "SB": LegalFormEntry("Sparbank", "Savings bank", True, True, None),
    "MB": LegalFormEntry("Medlemsbank", "Co-operative bank", True, True, None),
    "FAB": LegalFormEntry("Försäkringsaktiebolag", "Insurance company (limited)", True, True, None),
    "OFB": LegalFormEntry(
        "Ömsesidigt försäkringsbolag", "Mutual insurance company", True, True, None
    ),
    "FOF": LegalFormEntry("Försäkringsförening", "Insurance association", True, True, None),
    "TPAB": LegalFormEntry(
        "Tjänstepensionsaktiebolag", "Occupational pension company (limited)", True, True, None
    ),
    "OTPB": LegalFormEntry(
        "Ömsesidigt tjänstepensionsbolag", "Mutual occupational pension company", True, True, None
    ),
    "TPF": LegalFormEntry(
        "Tjänstepensionsförening", "Occupational pension association", True, True, None
    ),
    "FF": LegalFormEntry("Försäkringsförmedlare", "Insurance intermediary", None, None, None),
    "SE": LegalFormEntry("Europabolag", "European company (SE)", True, True, None),
    "SCE": LegalFormEntry("Europakooperativ", "European co-operative society", True, True, None),
    "EEIG": LegalFormEntry(
        "Europeisk ekonomisk intressegruppering",
        "European economic interest grouping",
        False,
        None,
        None,
    ),
    "EGTS": LegalFormEntry(
        "Europeisk gruppering för territoriellt samarbete",
        "European grouping of territorial co-operation",
        None,
        None,
        None,
    ),
}

#: The only two codes årsredovisningslagen 8 kap. 6 § names (§7.2) — the only
#: ones ``deadlines_for`` computes an ``annual_accounts`` date for.
DEADLINE_FORM_CODES = frozenset({"AB", "EK"})

#: Of those two, only ``AB`` also gets ``general_meeting`` (aktiebolagslagen 7
#: kap. 10 § names only aktiebolag; the ekonomisk förening's föreningsstämma
#: is a different, unsourced statute — §5.5).
GENERAL_MEETING_FORM_CODES = frozenset({"AB"})


class LegalFormInfo(NamedTuple):
    """Result of looking up an ``organisationsform`` code, including the
    unclassified case (D-009: never guess a duty)."""

    code: str
    swedish: str | None
    english: str | None
    limited_liability: bool | None
    has_board_duty: bool | None
    has_annual_accounts_duty: bool | None
    notes: list[str]


_UNCLASSIFIED_FORM_NOTE = (
    "The legal form {code!r} is not classified by registry-mcp, so no filing deadlines are "
    "computed for it. This does not mean none apply — check with an accountant."
)


def legal_form_info(code: str | None) -> LegalFormInfo:
    """Look up the duties for a Bolagsverket ``organisationsform`` code.

    An unclassified code maps to ``english=None``, all three duty fields
    ``None``, and note N6 (§2.1). Never guess a duty.
    """
    key = (code or "").strip().upper()
    entry = ORGANISATION_FORMS.get(key)
    if entry is None:
        return LegalFormInfo(
            code=key,
            swedish=None,
            english=None,
            limited_liability=None,
            has_board_duty=None,
            has_annual_accounts_duty=None,
            notes=[_UNCLASSIFIED_FORM_NOTE.format(code=key)],
        )
    return LegalFormInfo(
        code=key,
        swedish=entry.swedish,
        english=entry.english,
        limited_liability=entry.limited_liability,
        has_board_duty=entry.has_board_duty,
        has_annual_accounts_duty=entry.has_annual_accounts_duty,
        notes=[],
    )


# ---------------------------------------------------------------------------
# §8 — status derivation
# ---------------------------------------------------------------------------


class StatusResult(NamedTuple):
    """Result of :func:`derive_status`."""

    status: CompanyStatus
    status_detail: str
    is_active: bool
    bankruptcy_date: date | None
    procedure_kod: str | None
    """The `pagaende...` code that decided a non-ACTIVE, non-DELETED status,
    if any — used only to decide whether the ÅRL 8 kap. 7 § sentence belongs
    in the deadline-exemption note (KK/LI only, never FR/AC/RES/FUOL/DEOL)."""
    notes: list[str]


_ACTIVE_DETAIL = (
    "Registered with Bolagsverket and not marked as struck off or in any winding-up or "
    "restructuring procedure."
)

#: Precedence within `pagaende...Lista` (§8 rung 2): first match wins,
#: regardless of the list's own order or the codes' `fromDatum`.
_BUCKET1_ORDER = ("KK", "LI", "FR", "AC", "RES", "FUOL", "DEOL")

_BUCKET1_STATUS: dict[str, CompanyStatus] = {
    "KK": CompanyStatus.BANKRUPT,
    "LI": CompanyStatus.UNDER_LIQUIDATION,
    "FR": CompanyStatus.UNDER_LIQUIDATION,
    "AC": CompanyStatus.UNDER_LIQUIDATION,
    "RES": CompanyStatus.UNDER_LIQUIDATION,
    "FUOL": CompanyStatus.UNDER_LIQUIDATION,
    "DEOL": CompanyStatus.UNDER_LIQUIDATION,
}

_BUCKET1_DETAIL: dict[str, str] = {
    "KK": "Bankruptcy (konkurs) proceedings were opened on {date}.",
    "LI": (
        "Likvidation (liquidation) has been registered. Bolagsverket's dataset does not "
        "distinguish voluntary liquidation from compulsory (court-ordered) liquidation."
    ),
    "FR": (
        "Företagsrekonstruktion (business reorganisation) has been registered. This is "
        "financial distress, not bankruptcy."
    ),
    "AC": (
        "Ackordsförhandling (composition negotiation with creditors) has been registered. "
        "This is financial distress, not bankruptcy."
    ),
    "RES": (
        "Resolution proceedings have been registered — a bank or investment firm in resolution."
    ),
    "FUOL": (
        "This entity is the transferring party in a merger (överlåtande i fusion) and is "
        "being absorbed; it will cease to exist."
    ),
    "DEOL": (
        "This entity is the transferring party in a division (överlåtande vid delning) and "
        "is being absorbed; it will cease to exist."
    ),
}

#: Bucket 2 (§8): the procedure is about somebody else, or about form rather
#: than survival. Status is left ACTIVE; each gets a loud note so a caller is
#: never left with a bare ACTIVE for a company mid-conversion.
_BUCKET2_NOTE: dict[str, str] = {
    "FUOT": (
        "Bolagsverket records this organisation as the acquiring party in a merger "
        "(övertagande i fusion). It is healthy and continuing — the winding-up flag "
        "belongs to the company being absorbed, not to this one."
    ),
    "DEOT": (
        "Bolagsverket records this organisation as the receiving party in a division "
        "(övertagande vid delning). It is healthy and continuing."
    ),
    "OM": (
        "Bolagsverket records an ongoing change of legal form (ombildning) for this "
        "organisation. The entity continues to exist under its new form."
    ),
    "GROM": (
        "Bolagsverket records an ongoing cross-border conversion (gränsöverskridande "
        "ombildning) for this organisation. The entity continues to exist in another "
        "member state."
    ),
}

_UNCLASSIFIED_PROCEDURE_NOTE = (
    "Bolagsverket records an ongoing winding-up or restructuring procedure for this "
    "organisation ({kod}: {klartext}, registered {from_datum}) that registry-mcp does not "
    "classify. Treat this organisation as not plainly active and check with Bolagsverket "
    "before contracting with it."
)


#: §2.4: ``klartext`` can be the literal string ``"n/a"`` — Bolagsverket's
#: own sole-trader example carries ``{"kod": "PERSONNUMMER", "klartext":
#: "n/a"}`` — and that must never reach a user (review fix 7). Blank and
#: whitespace-only strings get the same treatment.
def _clean_reason_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.casefold() == "n/a":
        return None
    return stripped


#: Verbatim from `SWEDEN_SPEC.md` §8 rung 0 (added 2026-09-06 after T26e fix
#: 3) — matched exactly rather than paraphrased, per this project's
#: convention for every other note/detail string in this module.
_STATUS_DATA_UNAVAILABLE_DETAIL = (
    "Bolagsverket could not supply this organisation's registration status ({producer} did "
    "not answer), so it is unknown whether it is struck off or in a winding-up or "
    "restructuring procedure."
)


def derive_status(
    *,
    deregistered_at: date | None,
    deregistration_reason_kod: str | None,
    deregistration_reason_klartext: str | None,
    ongoing: list[tuple[str, str | None, date | None]],
    unavailable_producer: str | None = None,
) -> StatusResult:
    """Derive :class:`CompanyStatus` from Sweden's three orthogonal signals
    (§8). ``ongoing`` is the ``pagaende...Lista`` entries as
    ``(kod, klartext, fromDatum)`` — already read past the ``fel``/spelling
    ambiguity by ``registries/se/mapping.py``. ``verksamOrganisation`` and
    ``reklamsparr`` never reach this function: they do not change ``status``
    (D-035), only ``notes`` (N3/N4), so ``registries/se/mapping.py`` handles
    them directly.

    Precedence, highest first: struck off (rung 1) > a bucket-1 procedure
    (rung 2) > active (rung 3). ``bankruptcy_date`` is set from a ``KK`` entry
    **independent of precedence** — even a struck-off company keeps the date
    if a ``KK`` is present (test 57).

    ``unavailable_producer`` (review fix 3) is the data producer that a
    blocking ``fel`` kept ``registries/se/mapping.py`` from reading one of
    the fields this function derives status from (``avregistreradOrganisation``,
    ``avregistreringsorsak`` or either spelling of ``pagaende...``), or
    ``None`` if all of them arrived. It is consulted at rung 3's true
    "nothing above fired" default **and** at rung 2's bucket-2-only branch:
    a positive signal from rung 1, or a bucket-1 hit at rung 2, always wins
    regardless — but bucket-2-only does not count as "rung 2 fired"
    (``SWEDEN_SPEC.md`` §8: it "leaves status alone"), so a blocked producer
    still overrides it to ``UNKNOWN`` rather than asserting good standing on
    data that never arrived — the failure mode the module calls "an absence
    rendered as a fact" (§1.6 rule 1, one field further on). The bucket-2
    notes are carried through into that ``UNKNOWN`` result rather than
    dropped (§8: "the lower rungs still fill their own fields and notes").

    Practical reachability caveat: Bolagsverket's own partial-failure
    example fails a whole data producer at once, which would block
    ``pagaende...`` too and so keep ``ongoing`` empty in the same call where
    ``unavailable_producer`` is set. Exercising this branch for real needs a
    *per-field* failure — one producer blocked while another still supplies
    bucket-2 codes — which §1.6 models but the one fixture this module has
    does not.
    """
    bankruptcy_date = next((from_datum for kod, _kt, from_datum in ongoing if kod == "KK"), None)

    if deregistered_at is not None:
        reason_kod = deregistration_reason_kod or "?"
        reason_klartext = _clean_reason_text(deregistration_reason_klartext)
        detail = (
            f"Struck off the Bolagsverket register on {deregistered_at.isoformat()} "
            f"({reason_kod}: {reason_klartext})."
            if reason_klartext is not None
            else f"Struck off the Bolagsverket register on {deregistered_at.isoformat()} "
            f"({reason_kod})."
        )
        return StatusResult(
            status=CompanyStatus.DELETED,
            status_detail=detail,
            is_active=False,
            bankruptcy_date=bankruptcy_date,
            procedure_kod=None,
            notes=[detail],
        )

    if ongoing:
        bucket1_hits = [item for item in ongoing if item[0] in _BUCKET1_STATUS]
        if bucket1_hits:
            kod, _klartext, from_datum = min(
                bucket1_hits, key=lambda item: _BUCKET1_ORDER.index(item[0])
            )
            status = _BUCKET1_STATUS[kod]
            when = from_datum.isoformat() if from_datum else "an unspecified date"
            detail = _BUCKET1_DETAIL[kod].format(date=when)
            # Review fix 15(a): §8 says "the lower rungs still fill their own
            # fields and notes" — a co-occurring bucket-2 code (e.g. `KK`
            # alongside `FUOT`) must not have its note silently dropped just
            # because bucket 1 decided `status`.
            extra_notes = [
                _BUCKET2_NOTE[other_kod]
                for other_kod, _kt, _fd in ongoing
                if other_kod != kod and other_kod in _BUCKET2_NOTE
            ]
            return StatusResult(
                status=status,
                status_detail=detail,
                is_active=False,
                bankruptcy_date=bankruptcy_date,
                procedure_kod=kod,
                notes=[detail, *extra_notes],
            )

        notes: list[str] = []
        unknown_hits: list[tuple[str, str | None, date | None]] = []
        for kod, klartext, from_datum in ongoing:
            if kod in _BUCKET2_NOTE:
                notes.append(_BUCKET2_NOTE[kod])
            else:
                unknown_hits.append((kod, klartext, from_datum))

        if unknown_hits:
            first_kod, first_klartext, _fd = unknown_hits[0]
            for kod, klartext, from_datum in unknown_hits:
                notes.append(
                    _UNCLASSIFIED_PROCEDURE_NOTE.format(
                        kod=kod,
                        klartext=klartext or "no description",
                        from_datum=from_datum.isoformat() if from_datum else "an unknown date",
                    )
                )
            detail = (
                f"Bolagsverket records an ongoing procedure this module does not classify "
                f"({first_kod}: {first_klartext or 'no description'})."
            )
            return StatusResult(
                status=CompanyStatus.UNKNOWN,
                status_detail=detail,
                is_active=False,
                bankruptcy_date=bankruptcy_date,
                procedure_kod=None,
                notes=notes,
            )

        # Review fix 2 (T30): bucket-2-only does not count as "rung 2 fired" —
        # SWEDEN_SPEC.md §8 says it "leaves status alone", so an
        # `unavailable_producer` blocking the struck-off/bucket-1 fields must
        # still override this to UNKNOWN, the same as rung 3's true default
        # below. `notes` (the bucket-2 sentences already collected above) is
        # carried through rather than dropped — §8's "the lower rungs still
        # fill their own fields and notes" applies here too.
        if unavailable_producer is not None:
            return StatusResult(
                status=CompanyStatus.UNKNOWN,
                status_detail=_STATUS_DATA_UNAVAILABLE_DETAIL.format(producer=unavailable_producer),
                is_active=False,
                bankruptcy_date=bankruptcy_date,
                procedure_kod=None,
                notes=notes,
            )

        return StatusResult(
            status=CompanyStatus.ACTIVE,
            status_detail=_ACTIVE_DETAIL,
            is_active=True,
            bankruptcy_date=bankruptcy_date,
            procedure_kod=None,
            notes=notes,
        )

    # Rung 3, the true "nothing above fired" default (review fix 3): only
    # here, because `ongoing` being non-empty above means real (unblocked)
    # procedure data arrived and already produced a real answer.
    if unavailable_producer is not None:
        return StatusResult(
            status=CompanyStatus.UNKNOWN,
            status_detail=_STATUS_DATA_UNAVAILABLE_DETAIL.format(producer=unavailable_producer),
            is_active=False,
            bankruptcy_date=bankruptcy_date,
            procedure_kod=None,
            notes=[],
        )

    return StatusResult(
        status=CompanyStatus.ACTIVE,
        status_detail=_ACTIVE_DETAIL,
        is_active=True,
        bankruptcy_date=bankruptcy_date,
        procedure_kod=None,
        notes=[],
    )


# ---------------------------------------------------------------------------
# §5.4 — filing deadlines
# ---------------------------------------------------------------------------

GENERAL_MEETING_KIND = "general_meeting"
ANNUAL_ACCOUNTS_KIND = "annual_accounts"

_ABL_URL = "https://lagen.nu/2005:551"
_ARL_URL = "https://lagen.nu/1995:1554"

_CALENDAR_YEAR_NOTE = (
    "Filing deadlines are computed assuming a financial year ending 31 December. "
    "Bolagsverket does not name a company's financial year in the record this figure is "
    "read from by default, but its document list does publish it, for a company's filed "
    "annual reports — call company_deadlines or lookup_company with include=[\"filings\"] "
    "to read Bolagsverket's own document list and replace this assumption with the "
    "register's own figure. Without it: if the true financial year is not the calendar "
    "year, both dates move, and the filing date is also an outer limit rather than this "
    "company's own regardless: årsredovisningslagen 8 kap. 3 § requires filing within one "
    "month of the general meeting that adopts the accounts, so a company whose meeting "
    "was earlier must file earlier. Årsredovisningslagen 8 kap. 6 § allows nine months "
    "instead of seven for a company that has filed the notice and auditor's assurance it "
    "describes; the free dataset does not say which companies those are."
)

# ---------------------------------------------------------------------------
# The financial-year-end fact (D-041(a),(e),(f)) — rung 2 is NOT implemented
# ---------------------------------------------------------------------------
#
# `report.filings.financial_year_end` (D-044) is a real, sourced fact once a
# caller asks for it via `include=["filings"]`: Bolagsverket's own
# `/dokumentlista` publishes `rapporteringsperiodTom`, the reporting period
# of a company's last filed annual report. D-041(a) ruled that the old claim
# to the contrary — "Bolagsverket's free dataset does not publish the
# financial year" — is false, and `_CALENDAR_YEAR_NOTE` above and
# `_year_end_clause` below are the correction.
#
# What is **not** implemented is D-041(e)'s rung 2: computing a *different*
# `due_date` from that fact for a non-31-December year end. That needs
# Bolagsverket's own published table of *sista dag för årsstämma* and *sista
# dag att lämna in årsredovisningen* by räkenskapsårsslut, because ABL 7 kap.
# 10 §'s "inom sex månader" and ÅRL 8 kap. 6 §'s "inom sju månader" do not by
# themselves settle whether a 30 April year end gives 30 October (same day
# of month) or 31 October (end of the sixth month) — both readings agree
# only for a 31 December year end, which is why nothing shipped here depends
# on the answer.
#
# `VERIFY` attempted 2026-09-09, not sourced. `bolagsverket.se` answered a
# CAPTCHA challenge on every path tried in this environment — both guidance
# pages, the English mirror, `robots.txt`, and a direct PDF download link —
# so no Bolagsverket page could be read at all. Independent third-party
# accounting sites disagree with each other on exactly the disambiguating
# case (a 30 June year end's seven-month filing datum): one gives 31 January
# (end of month), another gives 30 January (same day of month) while also
# folding in an unrelated, unsourced weekend-roll-forward rule this project
# has separately declined to adopt for Sweden (§5.3, no Bolagsverket source
# found). Per D-009 and this task's own instruction, a non-December date is
# not computed from that disagreement. Rung 2 is therefore left out:
# `deadlines_for` still computes only rung 3 (the calendar-year assumption)
# for every year end, and `financial_year_end` is read only to choose which
# of `_year_end_clause`'s honest sentences below is true for this call —
# never to move a date. If this table is sourced later, rung 2 is one `if`
# per deadline plus a cited day-of-month rule; nothing else here changes.


def _observed_annual_report(filings: FilingHistory | None) -> FiledDocument | None:
    """The filed annual report ``FilingHistory.financial_year_end`` was taken
    from, or ``None`` when there is nothing to report: ``filings`` was never
    requested or its fetch failed (both leave ``filings`` itself ``None``),
    or Bolagsverket's document list held no filed annual report with a
    usable period end (``financial_year_end`` is then also ``None`` — the
    Ericsson case, ``registries/se/filings.py``'s ``_EMPTY_NOTE``)."""
    if filings is None or filings.financial_year_end is None:
        return None
    year_end = filings.financial_year_end
    return next((doc for doc in filings.documents if doc.period_end == year_end), None)


_NOT_ASKED_CLAUSE = (
    "Assumes a financial year ending 31 December: Bolagsverket does not name a company's "
    "financial year in the record this figure is read from by default, but its document "
    "list does publish it, for a company's filed annual reports — call company_deadlines "
    "or lookup_company with include=[\"filings\"] to read Bolagsverket's own document list "
    "and replace this assumption with the register's own figure."
)

_ASKED_BUT_NOTHING_FILED_CLAUSE = (
    "Assumes a financial year ending 31 December. include=[\"filings\"] was read for this "
    "company and Bolagsverket's document list holds no filed annual report with a usable "
    "financial year end, so there is nothing in it yet to confirm or correct that "
    "assumption against."
)


def _year_end_clause(filings: FilingHistory | None) -> str:
    """The sentence that replaces "Assumes a financial year ending 31
    December …" in each deadline's ``applies_because`` — D-041(f)'s three
    states of note N9, realised here rather than on ``CompanyReport.notes``.

    N9 was specified against ``CompanyReport.notes`` (``CALENDAR_YEAR_NOTE``
    below), but that field is fixed by ``registries/se/mapping.py`` when
    ``lookup`` runs — before ``include=["filings"]`` has been read, if it
    ever is — and ``Registry.deadline_report`` (``core/registry.py``, out of
    this task's footprint) copies ``report.notes`` verbatim rather than
    re-deriving it from the assembled report (D-018). A sentence that must
    vary with *this call's* ``filings`` cannot live there; it lives here,
    on the one document ``deadlines_for`` builds fresh, from the fully
    assembled ``report``, every time it runs. ``_NOT_ASKED_CLAUSE`` below
    says roughly what ``CALENDAR_YEAR_NOTE`` says — shorter, because each
    deadline's own fixed prose already names the one-month and nine-month
    provisions ``CALENDAR_YEAR_NOTE`` also carries, and repeating them
    verbatim inside the same ``applies_because`` would read as a stutter
    rather than as a second, independent statement.

    Four states, not three: D-041(e)'s own text anticipates the fourth for
    exactly the "rung 2 not sourced" outcome this module ships — "N9 says
    the year end is known but not yet computed from" — which is why a known
    non-December year end gets its own sentence below rather than reusing
    either the "not asked" or the "confirmed" one.
    """
    if filings is None:
        return _NOT_ASKED_CLAUSE
    document = _observed_annual_report(filings)
    if document is None or document.period_end is None:
        return _ASKED_BUT_NOTHING_FILED_CLAUSE

    year_end = document.period_end
    filed_clause = f", registered {document.filed_at.isoformat()}" if document.filed_at else ""
    if (year_end.month, year_end.day) == (12, 31):
        # D-041(f): the word "assum" must not appear in this state.
        return (
            "Confirmed, not a guess: Bolagsverket's document list shows this company's "
            f"last filed annual report covering a period ending {year_end.isoformat()}"
            f"{filed_clause} — a financial year ending 31 December, the same year end "
            "this date is computed from."
        )
    return (
        "Bolagsverket's document list shows this company's last filed annual report "
        f"covering a period ending {year_end.isoformat()}{filed_clause} — not "
        "31 December. This module has not been able to confirm, from a primary "
        "Bolagsverket source, how to convert a financial year end other than "
        "31 December into an exact statutory date (VERIFY, D-041(e)), so the date below "
        "still assumes a 31 December year end and may not be this company's own. A "
        "company may also relay its räkenskapsår under bokföringslagen 3 kap., and only "
        "the period end shown above is published."
    )


def _general_meeting_applies_because(filings: FilingHistory | None) -> str:
    return (
        "An aktiebolag must hold its ordinary general meeting (årsstämma) within six "
        "months of the end of each financial year (aktiebolagslagen 7 kap. 10 §). "
        f"{_year_end_clause(filings)} Six months is an outer limit and there is no "
        "filing office to be closed, so this date does not move off a weekend or a "
        "public holiday."
    )


def _annual_accounts_applies_because(filings: FilingHistory | None) -> str:
    return (
        "An aktiebolag or ekonomisk förening must file its annual report with "
        "Bolagsverket within one month of the general meeting that adopts it "
        "(årsredovisningslagen 8 kap. 3 §), and that meeting must be held within six "
        "months of the financial year end (aktiebolagslagen 7 kap. 10 §). Bolagsverket "
        "does not publish the meeting date, so this is the outer limit instead: a late "
        "fee of 7 500 kr (15 000 kr for a public company) starts if the documents have "
        "not arrived within seven months of the financial year end (årsredovisningslagen "
        "8 kap. 6 §) — nine months instead of seven for a company that has filed the "
        "notice and auditor's assurance 8 kap. 6 § describes; the free dataset does not "
        "say which companies those are. This company's own deadline may be earlier if "
        f"its general meeting was held earlier. {_year_end_clause(filings)} The date "
        "does not move off a weekend or a public holiday."
    )


def _general_meeting(today: date, filings: FilingHistory | None) -> Deadline:
    """30 June, and it does **not** roll forward (§5.3: no sourced rule)."""
    statutory = next_occurrence(6, 30, today)
    period = statutory.year - 1
    return Deadline(
        country="SE",
        registry="bolagsverket",
        kind=GENERAL_MEETING_KIND,
        name="Ordinary general meeting",
        local_name="Ordinarie bolagsstämma (årsstämma)",
        authority="Company shareholders (no external filing)",
        statutory_date=statutory,
        due_date=statutory,
        rolled_forward=False,
        period_label=str(period),
        period_start=date(period, 1, 1),
        period_end=date(period, 12, 31),
        recurrence=DeadlineRecurrence.ANNUAL,
        mandatory=True,
        applies_because=_general_meeting_applies_because(filings),
        days_until=(statutory - today).days,
        source_url=_ABL_URL,
    )


def _annual_accounts(today: date, filings: FilingHistory | None) -> Deadline:
    """31 July, and it does **not** roll forward (§5.3: no sourced rule)."""
    statutory = next_occurrence(7, 31, today)
    period = statutory.year - 1
    return Deadline(
        country="SE",
        registry="bolagsverket",
        kind=ANNUAL_ACCOUNTS_KIND,
        name="Annual accounts filing",
        local_name="Årsredovisning",
        authority="Bolagsverket",
        statutory_date=statutory,
        due_date=statutory,
        rolled_forward=False,
        period_label=str(period),
        period_start=date(period, 1, 1),
        period_end=date(period, 12, 31),
        recurrence=DeadlineRecurrence.ANNUAL,
        mandatory=True,
        applies_because=_annual_accounts_applies_because(filings),
        days_until=(statutory - today).days,
        source_url=_ARL_URL,
    )


def deadlines_for(report: CompanyReport, today: date) -> list[Deadline]:
    """Compute the Swedish filing deadlines this entity faces, from ``today``
    (§5.4). Pure and deterministic — never reads the clock.

    Deadlines are emitted only for an ``ACTIVE`` entity whose
    ``legal_form_code`` is ``AB`` or ``EK`` (D-009(a) applied to Sweden: an
    unclassified form gets none at all). ``verksamOrganisation`` never
    suppresses a deadline (§5.4.5) — a dormant ``AB`` still owes an annual
    report.

    Reads ``report.filings`` (D-044) — present only when the caller asked
    ``lookup_company`` or ``company_deadlines`` for ``include=["filings"]``
    and the fetch succeeded — to choose which of ``applies_because``'s
    honest sentences applies (D-041(f)); this is still a pure read of the
    already-assembled ``report``, never I/O, and never moves a computed date
    off the calendar-year assumption (see the module comment above
    ``_observed_annual_report`` for why rung 2 itself is not implemented).
    """
    if report.status is not CompanyStatus.ACTIVE:
        return []

    code = (report.legal_form_code or "").upper()
    if code not in DEADLINE_FORM_CODES:
        return []

    filings = report.filings
    deadlines: list[Deadline] = []
    if code in GENERAL_MEETING_FORM_CODES:
        deadlines.append(_general_meeting(today, filings))
    deadlines.append(_annual_accounts(today, filings))

    deadlines.sort(key=lambda d: (d.due_date, d.kind))
    return deadlines


_STATUS_SUPPRESSES_DEADLINES_NOTE = (
    "This organisation's status with Bolagsverket is {status!r}, so no filing deadlines are given."
)
_KK_LI_EXEMPTION_SENTENCE = (
    " Once bankruptcy is registered, årsredovisningslagen 8 kap. 7 § forbids Bolagsverket "
    "from imposing a late-filing fee at all; once liquidation is registered, no fee may be "
    "imposed for the period before the liquidation decision. What must still be filed is "
    "decided by the bankruptcy trustee or the liquidator."
)


def deadline_exemption_note(status: CompanyStatus, procedure_kod: str | None) -> str | None:
    """N11 (§2.1, §5.4.5): the sentence explaining why :func:`deadlines_for`
    returns ``[]`` because of ``status`` — ``None`` when ``status`` is
    ``ACTIVE`` (the unclassified-legal-form case gets its own note, N6, from
    :func:`legal_form_info`, not this one).

    The ÅRL 8 kap. 7 § sentence is appended only when the status arose from a
    registered ``KK`` (bankruptcy) or ``LI`` (liquidation) — the two
    procedures that statute actually names — never for ``FR``/``AC``/``RES``/
    ``FUOL``/``DEOL``, which reach ``UNDER_LIQUIDATION`` too but are not what
    8 kap. 7 § is about.
    """
    if status is CompanyStatus.ACTIVE:
        return None
    note = _STATUS_SUPPRESSES_DEADLINES_NOTE.format(status=status.value)
    if status is CompanyStatus.BANKRUPT or (
        status is CompanyStatus.UNDER_LIQUIDATION and procedure_kod == "LI"
    ):
        note += _KK_LI_EXEMPTION_SENTENCE
    return note


CALENDAR_YEAR_NOTE = _CALENDAR_YEAR_NOTE


_NO_COMPUTED_DEADLINES_NOTE = (
    "registry-mcp computes filing deadlines only for aktiebolag (AB) and ekonomiska "
    "föreningar (EK) — the two forms årsredovisningslagen 8 kap. 6 § names. {label} has "
    "real filing obligations that this module does not compute, because no primary "
    "source for them has been read."
)


def no_computed_deadlines_note(code: str, english: str | None) -> str:
    """Review fix 5 (§2.1, §5.4, D-009): the note ``registries/se/mapping.py``
    fires, alongside N6, for a legal form that is *classified* — via
    ``organisationsform`` (``BRF``, ``HB``, ``KB``, ``E``, ``S``, the banks
    and insurers, ...) or as an SCB ``juridiskForm`` fallback code — but is
    not one of :data:`DEADLINE_FORM_CODES`. Distinct from N6
    (:data:`_UNCLASSIFIED_FORM_NOTE`), which covers a code this module does
    not recognise at all; this note is for a code it does recognise and
    simply computes nothing for.

    ``english`` is ``None`` for an SCB fallback code (Statistics Sweden's
    ``juridiskForm`` list has no English label in this module) — the note
    then names the code itself rather than leaving `{label}` blank.
    """
    label = english if english else f"This organisation's legal form (code {code!r})"
    return _NO_COMPUTED_DEADLINES_NOTE.format(label=label)


# ---------------------------------------------------------------------------
# §13 — rules_markdown()
# ---------------------------------------------------------------------------


def rules_markdown() -> str:
    """Human/LLM readable summary of the Swedish rules this module implements.

    Served as the MCP resource ``registry://rules/SE`` via
    ``BolagsverketRegistry.rules_markdown``. ``SWEDEN_SPEC.md`` is the
    authoritative, detailed version. Opens with ``RULES_LAST_REVIEWED`` (T62)
    so a caller can tell a stale answer from a fresh one before reading any
    further.
    """
    return (
        f"Rules last reviewed: {RULES_LAST_REVIEWED.isoformat()}\n\n"
        "# Sweden — Bolagsverket (with Statistics Sweden, SCB)\n\n"
        "Bolagsverket (the Swedish Companies Registration Office) publishes the "
        "'värdefulla datamängder' (high-value datasets) API free of charge, with SCB as a "
        "second data producer inside the same payload: 'Data från Bolagsverket hämtas när "
        "det finns data att hämta från både Bolagsverket och SCB. Data från SCB hämtas när "
        "inget data finns att hämta från Bolagsverket.' Bolagsverket names **no licence** "
        "for this data — it states only that commercial and non-commercial reuse is free "
        "so long as personal-data and secrecy law is respected, and that attribution is "
        "'sometimes' required. Do not repeat third-party claims of a CC BY licence; none "
        "is stated on Bolagsverket's own pages.\n\n"
        "## No name search\n"
        "The API has four operations — isalive, organisationer, dokumentlista, dokument — "
        "and none of them accepts a company name. search_company therefore always raises "
        "not_implemented for Sweden. Look up a company by its identifier instead, or use "
        "Bolagsverket's bulk downloadable files ('Nedladdningsbara filer') to build a name "
        "index of your own.\n\n"
        "## The identifier\n"
        "An organisationsnummer is ten digits with a check digit, written 556016-0680 or "
        "5560160680. A sole trader is looked up by a twelve-digit personnummer "
        "(YYYYMMDDNNNN) instead — a Swedish national identity number for a natural person "
        "— and one such number can carry several registered businesses, distinguished only "
        "by namnskyddslöpnummer; a lookup returns the first Bolagsverket lists and names "
        "every business found. The wire format is digits only, with no hyphen.\n\n"
        "This module does **not** check the identifier's check digit. The algorithm is not "
        "sourced from any primary reference, and rejecting a real company on an unverified "
        "rule is worse than not checking at all — Bolagsverket validates it server-side and "
        "answers 'Identitetsbeteckning har ogiltig kontrollsiffra' when it is wrong. A "
        "modulus-10 result is still computed and reported as a caveat on an otherwise-valid "
        "identifier, never as a rejection.\n\n"
        "## Filing deadlines do not move for weekends or holidays\n"
        "No provision of årsredovisningslagen 8 kap. and no Bolagsverket page stating a "
        "roll-forward rule for filing deadlines was found, so — unlike the Norwegian rules "
        "this same server also serves — every Swedish deadline has "
        "`statutory_date == due_date` and `rolled_forward` is always `False`. This is the "
        "honest reading of a silent source, not a rule that says dates do not move.\n\n"
        "## The two deadlines computed here, and their derivation\n"
        "Both apply only to `AB` (aktiebolag) and `EK` (ekonomisk förening) — the two forms "
        "årsredovisningslagen 8 kap. 6 § actually names — and only while the entity's "
        "status is active.\n"
        "- `general_meeting` (AB only) — 30 June, computed as six months after a "
        "31 December financial year end (aktiebolagslagen 7 kap. 10 §).\n"
        "- `annual_accounts` (AB and EK) — 31 July. The real chain has three links: the "
        "general meeting within six months (aktiebolagslagen 7 kap. 10 §), filing within "
        "one month of that meeting adopting the accounts (årsredovisningslagen 8 kap. 3 §, "
        "**not computable** — the adoption date is not published), and the seven-month "
        "outer limit where a förseningsavgift (late-filing fee) begins "
        "(årsredovisningslagen 8 kap. 6 §) — which is what this module computes and what "
        "most users mean by 'the filing deadline'. A company whose general meeting was "
        "held earlier must file earlier than 31 July.\n\n"
        "## The förseningsavgift (late-filing fee)\n"
        "7 500 kr for a private aktiebolag or an ekonomisk förening, 15 000 kr for a public "
        "aktiebolag, if the annual report has not arrived within seven months of the "
        "financial year end (årsredovisningslagen 8 kap. 6 §) — nine months instead of "
        "seven for a company that filed the 7 kap. 14 § notice and an auditor's written "
        "assurance within the seven months (the free dataset does not say which companies "
        "those are). The fee escalates twice more at two-month intervals (8 kap. 6 a §) to "
        "a maximum of 30 000 kr private / 60 000 kr public. Once bankruptcy (konkurs) is "
        "registered, no förseningsavgift may be imposed at all; once liquidation "
        "(likvidation) is registered, none may be imposed for the period before the "
        "liquidation decision (årsredovisningslagen 8 kap. 7 §).\n\n" + _CALENDAR_YEAR_NOTE + "\n\n"
        "## Status: three independent signals, not one field\n"
        "Bolagsverket publishes no status field. Three things can each be true "
        "independently: struck off (avregistrerad, with a reason code — always maps to "
        "`deleted`, never `dissolved`), an ongoing winding-up or restructuring procedure "
        "(pågående avvecklings- eller omstruktureringsförfarande — konkurs beats "
        "likvidation beats everything else), and whether Statistics Sweden marks the "
        "organisation as economically active (verksam: holding F-skatt, VAT or an employer "
        'registration). **`is_active` means "on the register and not winding down", not '
        '"trading"**: a company can be registered, in good standing, and not '
        "economically active — newly formed, dormant, or a pure holding company — and this "
        "module reports that as `active` with a note, never as a lifecycle state of its "
        "own.\n\n"
        "## The advertising block (reklamspärr)\n"
        "`advertising_protected` is `true`/`false` from Statistics Sweden's *reklamspärr* "
        "flag; when `true`, a `notes` sentence states it and must travel with any contact "
        "details passed on.\n\n"
        "## Two vocabularies for the legal form\n"
        "Bolagsverket's own `organisationsform` drives `legal_form_code`/`legal_form_local`; "
        "SCB's `juridiskForm` (a Swedish Tax Agency classification) is the fallback, used "
        "only when Bolagsverket holds no value. The mapping between them is published but "
        "many-to-one and lossy — `AB` and `TPAB` both map to juridisk form `49`; five "
        "different organisationsformer map to `51` — so it is never run backwards: a "
        "juridiskForm code is carried as-is, in the same field, and never translated into a "
        "guessed organisationsform. Bolagsverket's own connection guide publishes the full "
        "table, reproduced here for reference **only** — never used the other way round:\n\n"
        "| organisationsform | juridisk form |\n"
        "|---|---|\n"
        "| `AB` | 49 |\n"
        "| `TPAB` | 49 |\n"
        "| `KB` | 31 |\n"
        "| `HB` | 31 |\n"
        "| `BRF` | 53 |\n"
        "| `EK` | 51 |\n"
        "| `FOF` | 51 |\n"
        "| `TPF` | 51 |\n"
        "| `BF` | 51 |\n"
        "| `SF` | 51 |\n"
        "| `E` | 10 or 91 |\n"
        "| `BAB` | 41 |\n"
        "| `FAB` | 42 |\n"
        "| `SE` | 43 |\n"
        "| `KHF` | 54 |\n"
        "| `MB` | 93 |\n"
        "| `SB` | 93 |\n"
        "| `SCE` | 55 |\n"
        "| `TSF` | 63 |\n"
        "| `I` | 61 |\n"
        "| `S` | 72 |\n"
        "| `OTPB` | 92 |\n"
        "| `OFB` | 92 |\n"
        "| `FL` | none — \"not its own juridisk form; it belongs to a parent company's\" |\n"
        "| `BFL` | none — same |\n\n"
        "`EB`, `EEIG`, `EGTS` and `FF` are not in Bolagsverket's published mapping table at "
        "all. Never run this table backwards: `49` alone cannot say whether the "
        "organisationsform was `AB` or `TPAB`, so a juridiskForm code is carried as-is, in "
        "the same field, rather than translated into a guessed organisationsform.\n\n"
        "## What this dataset does not publish\n"
        "Officers, share capital, beneficial owners, employee counts, financial figures, "
        "VAT registration, a visiting (business) address, email, phone and website — none "
        "of these reach this module from any call. A company's financial year end is "
        "different: Bolagsverket does not include it in the base company record, but does "
        "publish it, for a company's filed annual reports, in its document list — call "
        "lookup_company or company_deadlines with `include=[\"filings\"]` to read it. "
        "`postal_address` is a correspondence address only — often an accountant's "
        "office, a box, or (for a sole trader) a home address — never a registered "
        "office; Sweden has no equivalent dataset for that. Skatteverket's own deadlines "
        "(inkomstdeklaration 2, moms, arbetsgivardeklaration) are real obligations this "
        "module does not compute: the free dataset gives no VAT period to key them from, "
        "and Skatteverket's own dates are additionally keyed to filing channel as well as "
        "financial-year-end month, which this module does not attempt to derive even "
        "where `include=[\"filings\"]` supplies the year end.\n\n"
        "`/dokumentlista` (filed annual reports) is exposed by this module as "
        "`include=[\"filings\"]`. `/dokument`, the zip behind each filed report, is not: "
        "a third request, an XBRL package to parse, and out of scope by design.\n"
    )
