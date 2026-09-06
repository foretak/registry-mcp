"""Bolagsverket/SCB JSON -> ``core/models.py`` shapes.

Pure, synchronous, no I/O. ``registries/se/client.py`` calls
:func:`map_entity` after it has the raw ``POST /organisationer`` body in
hand. See ``SWEDEN_SPEC.md`` §§1.6, 2-3, 7-8, 15.

**Read `fel` before every value.** Every field of an ``Organisation`` except
``organisationsidentitet`` and ``namnskyddslopnummer`` is a wrapper carrying
its own ``dataproducent`` and ``fel`` beside its value (§1.6) — a 200 can
carry no data at all. :class:`_FieldReader` centralises that check so no
mapping code below ever reads a value without it.

Legal-form classification and status derivation are business *rules*, owned
by ``registries/se/rules.py`` (§7, §8). This module only reshapes data and
decides *which* raw field feeds a rule — it does not decide whether ``AB``
implies a board.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Any

from registry_mcp.core.models import Address, CompanyReport, CompanyStatus, IndustryCode

__all__ = [
    "is_not_found",
    "is_partial_failure",
    "map_address",
    "map_entity",
    "map_industry_codes",
]

#: The three `FelTyp` values that mean "a data producer could not answer for
#: this field" (§1.6) — distinct from `ORGANISATION_FINNS_EJ`, which means
#: the whole organisation is unknown and is handled by :func:`is_not_found`
#: before `map_entity` is ever called.
_BLOCKING_FEL_TYPES = frozenset({"OTILLGANGLIG_UPPGIFTSKALLA", "TIMEOUT", "OGILTIG_BEGARAN"})

#: Every wrapped top-level field of an `Organisation` that carries its own
#: `fel`/`dataproducent` (§1.6) — everything except `organisationsidentitet`
#: and `namnskyddslopnummer`, which are plain values. Used by
#: :func:`is_not_found` and :func:`is_partial_failure`, which must agree with
#: `_FieldReader` on what counts as "a field" without constructing one (both
#: run before/around `map_entity`, on the raw body).
_WRAPPED_FIELDS = (
    "organisationsnamn",
    "organisationsform",
    "avregistreradOrganisation",
    "avregistreringsorsak",
    "pagaendeAvvecklingsEllerOmstruktureringsforfarande",
    "pagandeAvvecklingsEllerOmstruktureringsforfarande",
    "juridiskForm",
    "verksamOrganisation",
    "organisationsdatum",
    "verksamhetsbeskrivning",
    "naringsgrenOrganisation",
    "postadressOrganisation",
    "reklamsparr",
)


def _first_organisation(body: Mapping[str, Any]) -> Mapping[str, Any] | None:
    organisationer = body.get("organisationer") or []
    if not organisationer:
        return None
    result: Mapping[str, Any] = organisationer[0]
    return result


#: The Bolagsverket *identity-bearing* fields (§1.7, §6.3, review fix 4): a
#: `fel.typ == "ORGANISATION_FINNS_EJ"` on one of these means Bolagsverket
#: itself has no such organisation. An SCB-sourced field (`juridiskForm`,
#: `verksamOrganisation`, `reklamsparr`, ...) can carry the identical code
#: when only Statistics Sweden lacks the entity — the workbook's own
#: `5567223705` scenario, "organisation finns ej hos SCB" — and that must
#: never be read as `not_found` for a company Bolagsverket has (§1.7's own
#: caveat: absent at one data producer does not mean absent at the other).
_IDENTITY_BEARING_FIELDS = ("organisationsnamn", "organisationsform", "organisationsdatum")


def is_not_found(body: Mapping[str, Any]) -> bool:
    """§1.7/§6.3: an empty `organisationer` array, or a populated one whose
    Bolagsverket *identity-bearing* fields (`_IDENTITY_BEARING_FIELDS`) carry
    `fel.typ == "ORGANISATION_FINNS_EJ"`.

    Deliberately scoped to those three fields rather than every wrapped
    field: an SCB-only field can carry the same code while Bolagsverket
    still has the organisation, which is a different fact (§1.7) that must
    not raise `not_found` — or cache a negative for an hour — for a company
    that exists.

    `VERIFY-live` which shape the wire actually uses (T26 recon item 7) —
    both are handled, per `SWEDEN_SPEC.md` §6.
    """
    org = _first_organisation(body)
    if org is None:
        return True
    for field in _IDENTITY_BEARING_FIELDS:
        obj = org.get(field)
        if isinstance(obj, dict):
            fel = obj.get("fel")
            if isinstance(fel, dict) and fel.get("typ") == "ORGANISATION_FINNS_EJ":
                return True
    return False


def is_partial_failure(body: Mapping[str, Any]) -> bool:
    """§1.6/§6.3/§9: true when any wrapped field of the first organisation
    carries a `fel.typ` in `{OTILLGANGLIG_UPPGIFTSKALLA, TIMEOUT,
    OGILTIG_BEGARAN}` — the signal that a data producer did not answer for
    part of this request. The caller (`registries/se/client.py`) must not
    cache such a response for 24 hours (§9); `map_entity` still maps what
    arrived and adds note N13.
    """
    org = _first_organisation(body)
    if org is None:
        return False
    for field in _WRAPPED_FIELDS:
        obj = org.get(field)
        if isinstance(obj, dict):
            fel = obj.get("fel")
            if isinstance(fel, dict) and fel.get("typ") in _BLOCKING_FEL_TYPES:
                return True
    return False


class _FieldReader:
    """Reads one Bolagsverket ``Organisation`` object's wrapped fields,
    checking ``fel`` before returning a value (§1.6) and recording every
    field a blocking ``fel.typ`` hit, for note N13 (§2.1)."""

    def __init__(self, org: Mapping[str, Any]) -> None:
        self._org = org
        #: (human label, dataproducent) pairs for fields whose `fel.typ` was
        #: one of `_BLOCKING_FEL_TYPES` — never for a field that is simply
        #: absent, which is not an error (D-011).
        self.blocked: list[tuple[str, str]] = []

    def wrapper(self, field: str, *, label: str) -> Mapping[str, Any] | None:
        """The wrapper object for ``field``, or ``None`` if it is absent,
        null, or carries any ``fel`` (blocking or not)."""
        obj = self._org.get(field)
        if not obj:
            return None
        fel = obj.get("fel")
        if isinstance(fel, dict) and fel.get("typ"):
            if fel.get("typ") in _BLOCKING_FEL_TYPES:
                producer = obj.get("dataproducent") or "A data producer"
                self.blocked.append((label, producer))
            return None
        result: Mapping[str, Any] = obj
        return result

    def value(self, field: str, subkey: str, *, label: str) -> Any | None:
        obj = self.wrapper(field, label=label)
        if obj is None:
            return None
        return obj.get(subkey)


_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")

#: A leading run of real whitespace or a *literal* two-character escape
#: sequence (``\n``, ``\r``, ``\t`` as backslash-plus-letter, not a control
#: character). Bolagsverket's own sole-trader OpenAPI example over-escapes
#: `verksamhetsbeskrivning.beskrivning`'s leading newline this way — the raw
#: document byte-for-byte carries `\\n` (backslash, backslash, n), which
#: `json.load` turns into the two literal characters ``\`` and ``n``, not a
#: real newline. A plain ``.strip()`` would leave that prefix untouched, so
#: `_clean_text` strips both forms (§2: "`.strip()` is mandatory").
_LEADING_ESCAPED_WHITESPACE_RE = re.compile(r"^(?:\\[nrt]|\s)+")


def _clean_text(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    cleaned = _LEADING_ESCAPED_WHITESPACE_RE.sub("", raw).strip()
    return cleaned or None


def _parse_date(raw: Any) -> date | None:
    """One tolerant parser for every date in this module (§2.5): accept
    ``YYYY-MM-DD`` and any ``YYYY-MM-DD`` followed by ``T…``, taking the date
    part; anything else is ``None``, never a raised exception."""
    if not isinstance(raw, str):
        return None
    match = _DATE_PREFIX_RE.match(raw)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def map_address(postadress: Mapping[str, Any] | None) -> Address | None:
    """``postadressOrganisation.postadress`` -> ``Address`` (§3).

    A correspondence address, not a registered office: ``coAdress`` comes
    first (matching `UK_SPEC.md` §3's care-of convention), ``postnummer`` is
    kept exactly as published (no reformatting), and a missing object maps to
    ``None``, never an empty ``Address``.
    """
    if not postadress:
        return None
    lines = [str(v) for v in (postadress.get("coAdress"), postadress.get("utdelningsadress")) if v]
    land = postadress.get("land")
    # §3: `country_code` is "SE" when `land` is absent *or* casefolds to
    # sverige/sweden — not only on the string match (review fix 6).
    if land is None:
        country_code: str | None = "SE"
    elif isinstance(land, str) and land.strip().casefold() in {"sverige", "sweden"}:
        country_code = "SE"
    else:
        country_code = None
    return Address(
        lines=lines,
        postal_code=postadress.get("postnummer"),
        city=postadress.get("postort"),
        municipality=None,
        municipality_code=None,
        country_code=country_code,
        country_name=land,
    )


def map_industry_codes(naringsgren: Mapping[str, Any] | None) -> list[IndustryCode]:
    """``naringsgrenOrganisation.sni[]`` -> ranked ``IndustryCode`` list.
    Descriptions arrive with the codes here, unlike GB (§2)."""
    if not naringsgren:
        return []
    sni = naringsgren.get("sni") or []
    return [
        IndustryCode(
            code=str(item.get("kod", "")),
            description=item.get("klartext"),
            scheme="SNI 2007",
            rank=rank,
        )
        for rank, item in enumerate(sni, start=1)
    ]


def _rules() -> ModuleType:
    """Lazily import ``registries/se/rules.py`` (matching
    ``registries/gb/mapping.py``'s / ``registries/no/mapping.py``'s
    convention)."""
    import registry_mcp.registries.se.rules as rules_module

    return rules_module


# ---------------------------------------------------------------------------
# §2.3 — the name list
# ---------------------------------------------------------------------------


def _name_list(reader: _FieldReader) -> list[Mapping[str, Any]]:
    wrapper = reader.wrapper("organisationsnamn", label="the business name")
    if wrapper is None:
        return []
    result: list[Mapping[str, Any]] = wrapper.get("organisationsnamnLista") or []
    return result


def _primary_name(names: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The first item whose ``organisationsnamntyp.kod == "FORETAGSNAMN"``,
    else the first item in the list (§2.3)."""
    for entry in names:
        if (entry.get("organisationsnamntyp") or {}).get("kod") == "FORETAGSNAMN":
            return entry
    return names[0] if names else None


def _extra_name_fragment(entry: Mapping[str, Any]) -> str:
    namn = entry.get("namn") or "(unnamed)"
    klartext = (entry.get("organisationsnamntyp") or {}).get("klartext") or "additional name"
    fragment = f"{namn} ({klartext})"
    activity = entry.get("verksamhetsbeskrivningSarskiltForetagsnamn")
    if activity:
        fragment += f', for the business described as "{activity}"'
    return fragment


def _n12_note(names: Sequence[Mapping[str, Any]], primary: Mapping[str, Any] | None) -> str | None:
    extra = [entry for entry in names if entry is not primary]
    if not extra:
        return None
    fragments = "; ".join(_extra_name_fragment(entry) for entry in extra)
    return (
        f"Bolagsverket also publishes these names for this organisation: {fragments}. They "
        "are current alternative or secondary registered names, not former ones."
    )


# ---------------------------------------------------------------------------
# §2.2 — one identifier, several businesses (N7)
# ---------------------------------------------------------------------------


def _business_label(org: Mapping[str, Any]) -> str:
    names = org.get("organisationsnamn") or {}
    name_list = names.get("organisationsnamnLista") or []
    primary = _primary_name(name_list)
    if primary and primary.get("namn"):
        return str(primary["namn"]).strip()
    return "(unnamed)"


def _n7_note(organisationer: Sequence[Mapping[str, Any]]) -> str | None:
    if len(organisationer) <= 1:
        return None
    parts = []
    for org in organisationer:
        name = _business_label(org)
        nsl = org.get("namnskyddslopnummer")
        reg_wrapper = org.get("organisationsdatum") or {}
        reg_date = None
        if not (reg_wrapper.get("fel")):
            reg_date = _parse_date(reg_wrapper.get("registreringsdatum"))
        when = reg_date.isoformat() if reg_date else "an unknown date"
        parts.append(f"{name} (namnskyddslöpnummer {nsl}, registered {when})")
    return (
        f"This identifier carries {len(organisationer)} registered businesses: "
        + "; ".join(parts)
        + ". In Sweden a sole trader's organisationsnummer is the proprietor's personnummer, "
        "so one number can hold several registered business names. The one shown above is "
        "the first Bolagsverket returned; it is not necessarily the one you are looking for."
    )


# ---------------------------------------------------------------------------
# §7 — legal form, both vocabularies
# ---------------------------------------------------------------------------

_N5_NOTE = (
    "The legal form shown comes from Statistics Sweden's juridisk form code list (code "
    "{kod}), not from Bolagsverket's organisationsform. The two are different code lists "
    "— the Tax Agency's is coarser — and Bolagsverket holds no organisationsform for this "
    "organisation."
)

_N8_SOLE_TRADER_NOTE = (
    "This is a sole trader (enskild näringsidkare). Its identifier is the proprietor's "
    "Swedish personnummer, and the registered name and address are often the proprietor's "
    "own name and home address — this record contains personal data about a natural "
    "person and should be handled accordingly. Bolagsverket itself treats the identifier "
    "as personal data: its API takes it in a request body rather than a URL so it does not "
    "reach access logs."
)

_PERSONAL_ID_TYP_KODS = frozenset({"PERSONNUMMER", "SAMORDNINGSNUMMER", "GDNUMMER", "DODSBO"})

_ID_SCHEME_BY_TYP_KOD: dict[str, str] = {
    "ORGANISATIONSNUMMER": "organisationsnummer",
    "PERSONNUMMER": "personnummer",
    "SAMORDNINGSNUMMER": "samordningsnummer",
    "GDNUMMER": "GD-nummer",
    "DODSBO": "dödsbonummer",
    "UTLANDSK_JURIDISK_IDENTITETSBETECKNING": "foreign identifier",
}


class _LegalForm:
    __slots__ = (
        "code",
        "english",
        "has_annual_accounts_duty",
        "has_board_duty",
        "is_unclassified",
        "limited_liability",
        "local",
        "notes",
    )

    def __init__(
        self,
        code: str | None,
        english: str | None,
        local: str | None,
        limited_liability: bool | None,
        has_board_duty: bool | None,
        has_annual_accounts_duty: bool | None,
        notes: list[str],
        *,
        is_unclassified: bool = False,
    ) -> None:
        self.code = code
        self.english = english
        self.local = local
        self.limited_liability = limited_liability
        self.has_board_duty = has_board_duty
        self.has_annual_accounts_duty = has_annual_accounts_duty
        self.notes = notes
        #: True only when `organisationsform` carried a code this module does
        #: not recognise (N6 already fired for it, in `notes`). `False` for a
        #: recognised `organisationsform` code, an SCB `juridiskForm`
        #: fallback code, or no legal-form data at all — review fix 5 uses
        #: this to avoid double-explaining the unclassified case.
        self.is_unclassified = is_unclassified


def _resolve_legal_form(reader: _FieldReader, rules: ModuleType) -> _LegalForm:
    """§7.1 (D-034): ``organisationsform`` drives; ``juridiskForm`` (SCB) is
    the fallback, used only when Bolagsverket holds no value. The SCB code is
    never translated into a Bolagsverket code (§7.1, §15)."""
    org_form = reader.wrapper("organisationsform", label="the legal form")
    if org_form and org_form.get("kod"):
        code = str(org_form["kod"])
        info = rules.legal_form_info(code)
        return _LegalForm(
            code=code,
            english=info.english,
            local=org_form.get("klartext"),
            limited_liability=info.limited_liability,
            has_board_duty=info.has_board_duty,
            has_annual_accounts_duty=info.has_annual_accounts_duty,
            notes=list(info.notes),
            # `legal_form_info` returns a non-empty `notes` (N6) precisely
            # and only when the code is unclassified (§7) — reused here
            # rather than re-checking membership in `ORGANISATION_FORMS`.
            is_unclassified=bool(info.notes),
        )

    juridisk_form = reader.wrapper("juridiskForm", label="the legal form (SCB)")
    if juridisk_form and juridisk_form.get("kod"):
        code = str(juridisk_form["kod"])
        return _LegalForm(
            code=code,
            english=None,
            local=juridisk_form.get("klartext"),
            limited_liability=None,
            has_board_duty=None,
            has_annual_accounts_duty=None,
            notes=[_N5_NOTE.format(kod=code)],
            is_unclassified=False,
        )

    return _LegalForm(None, None, None, None, None, None, [], is_unclassified=False)


# ---------------------------------------------------------------------------
# §8 — status, read from the wire shape (including the misspelling, §15)
# ---------------------------------------------------------------------------


def _ongoing_procedures(reader: _FieldReader) -> list[tuple[str, str | None, date | None]]:
    """§15: both spellings of ``pagaende...`` (and its inner ``...Lista``) are
    read. The schema spells it ``pagaendeAvvecklingsEllerOmstruktureringsforfarande``;
    Bolagsverket's own aktiebolag example misspells it
    ``pagandeAvvecklingsEllerOmstruktureringsforfarande``. Reading only the
    correct spelling would report a bankrupt company as active if the wire
    ever sends the misspelling (test 98)."""
    wrapper = reader.wrapper(
        "pagaendeAvvecklingsEllerOmstruktureringsforfarande", label="ongoing procedures"
    )
    if wrapper is None:
        wrapper = reader.wrapper(
            "pagandeAvvecklingsEllerOmstruktureringsforfarande", label="ongoing procedures"
        )
    if wrapper is None:
        return []
    items = wrapper.get("pagaendeAvvecklingsEllerOmstruktureringsforfarandeLista")
    if items is None:
        items = wrapper.get("pagandeAvvecklingsEllerOmstruktureringsforfarandeLista")
    if not items:
        return []
    result: list[tuple[str, str | None, date | None]] = []
    for item in items:
        kod = item.get("kod")
        if not kod:
            continue
        result.append((str(kod), item.get("klartext"), _parse_date(item.get("fromDatum"))))
    return result


#: The raw fields §8 derives status from (review fix 3): if a blocking `fel`
#: hits any of these, §8 rung 3 ("nothing above fired") must not be read as
#: a confirmed `ACTIVE` — nothing fired because the fields that would tell
#: us were unreadable, not because Bolagsverket said the organisation is in
#: good standing. Both `pagaende...` spellings, matching `_ongoing_procedures`.
_STATUS_SOURCE_FIELDS = (
    "avregistreradOrganisation",
    "avregistreringsorsak",
    "pagaendeAvvecklingsEllerOmstruktureringsforfarande",
    "pagandeAvvecklingsEllerOmstruktureringsforfarande",
)


def _status_data_unavailable_producer(org: Mapping[str, Any]) -> str | None:
    """The `dataproducent` of the first §8 status field a blocking `fel.typ`
    made unreadable, or `None` if all of them arrived (present-and-null is
    not blocked — that is a real "no" per D-011, not silence). Used only to
    decide whether `rules.derive_status`'s rung-3 default may fire."""
    for field in _STATUS_SOURCE_FIELDS:
        obj = org.get(field)
        if not isinstance(obj, dict):
            continue
        fel = obj.get("fel")
        if isinstance(fel, dict) and fel.get("typ") in _BLOCKING_FEL_TYPES:
            producer = obj.get("dataproducent")
            return str(producer) if producer else "A data producer"
    return None


# ---------------------------------------------------------------------------
# The mapper
# ---------------------------------------------------------------------------

_N3_NOTE = (
    "Statistics Sweden does not mark this organisation as economically active (verksam): "
    "it holds no F-skatt, VAT or employer registration. It is on the register and is not "
    "being wound up, so is_active is true — but it may be dormant, and that is a "
    "different question."
)
_N4_NOTE = (
    "This organisation is marked with a reklamspärr (advertising block) in Statistics "
    "Sweden's register: it has asked not to receive direct marketing. If you pass this "
    "record's contact details on, that marking must travel with them."
)
_N13_NOTE = (
    "Part of this record could not be retrieved: {producers} did not answer for {fields}. "
    "The fields below are what arrived, and the missing ones are absent rather than "
    "empty. This answer was not cached — ask again for a complete one."
)

_SOURCE_NAME = "Bolagsverket (bolagsverket.se)"
_SOURCE_URL = "https://gw.api.bolagsverket.se/vardefulla-datamangder/v1"
_LICENSE = (
    "Free re-use (Bolagsverket/SCB high-value datasets, EU Open Data Directive) — the "
    "publisher names no licence"
)
_CONFIDENCE_BASIS = "exact identifier lookup in the Bolagsverket register"


def map_entity(
    body: Mapping[str, Any],
    requested_id: str,
    *,
    cached: bool = False,
    fetched_at: datetime | None = None,
) -> CompanyReport:
    """Build a full ``CompanyReport`` from one ``POST /organisationer`` body.

    Args:
        body: The parsed JSON response, ``{"organisationer": [...]}``.
        requested_id: The normalised identitetsbeteckning this lookup was
            made for — used for ``id``/``name`` only when Bolagsverket's own
            ``organisationsidentitet``/name are entirely absent (§1.6's
            partial-failure branch; T26b's chosen behaviour for test 95:
            construct without raising, name falls back to the identifier).
        cached: Whether this report is being served from the cache.
        fetched_at: The original fetch time (preserved across cache hits per
            ``DECISIONS.md`` D-006). Defaults to now.

    Never raises: a partially failed 200 (§1.6) is mapped as far as it goes,
    with note N13 naming what was missing. Call :func:`is_not_found` first —
    this function assumes the identifier resolved to at least a shape.
    """
    rules = _rules()
    organisationer: list[Mapping[str, Any]] = body.get("organisationer") or []
    org: Mapping[str, Any] = organisationer[0] if organisationer else {}
    reader = _FieldReader(org)
    notes: list[str] = []

    # --- identity ------------------------------------------------------
    identitet = org.get("organisationsidentitet") or {}
    id_value = str(identitet.get("identitetsbeteckning") or requested_id)
    typ_kod = (identitet.get("typ") or {}).get("kod")
    id_scheme = (
        _ID_SCHEME_BY_TYP_KOD.get(typ_kod, "organisationsnummer")
        if typ_kod
        else "organisationsnummer"
    )

    # --- name ------------------------------------------------------------
    name_list = _name_list(reader)
    primary = _primary_name(name_list)
    name = None
    if primary and primary.get("namn"):
        name = str(primary["namn"]).strip()
    name = name or requested_id

    n12 = _n12_note(name_list, primary)
    if n12:
        notes.append(n12)

    n7 = _n7_note(organisationer)
    if n7:
        notes.append(n7)

    # --- legal form (§7) ---------------------------------------------------
    legal_form = _resolve_legal_form(reader, rules)
    notes.extend(legal_form.notes)

    # --- status (§8) ---------------------------------------------------
    deregistered_wrapper = reader.wrapper(
        "avregistreradOrganisation", label="the deregistration date"
    )
    deregistered_at = _parse_date((deregistered_wrapper or {}).get("avregistreringsdatum"))
    reason_wrapper = reader.wrapper("avregistreringsorsak", label="the deregistration reason")
    ongoing = _ongoing_procedures(reader)

    status_result = rules.derive_status(
        deregistered_at=deregistered_at,
        deregistration_reason_kod=(reason_wrapper or {}).get("kod"),
        deregistration_reason_klartext=(reason_wrapper or {}).get("klartext"),
        ongoing=ongoing,
        unavailable_producer=_status_data_unavailable_producer(org),
    )
    notes.extend(status_result.notes)

    n11 = rules.deadline_exemption_note(status_result.status, status_result.procedure_kod)
    if n11:
        notes.append(n11)

    # --- SCB signals that never touch status (D-035) ------------------
    verksam_kod = reader.value(
        "verksamOrganisation", "kod", label="whether it is economically active"
    )
    if verksam_kod == "NEJ":
        notes.append(_N3_NOTE)

    reklamsparr_kod = reader.value("reklamsparr", "kod", label="the advertising block")
    if reklamsparr_kod == "JA":
        notes.append(_N4_NOTE)

    # --- N8: sole-trader personal-data note (D-039) ------------------------
    if typ_kod in _PERSONAL_ID_TYP_KODS or legal_form.code == "E":
        notes.append(_N8_SOLE_TRADER_NOTE)

    # --- N9: the calendar-year assumption, whenever a computed deadline
    # would be returned (D-010, D-023) — independent of `today`, since
    # whether *any* annual deadline exists depends only on status and
    # legal_form_code, both known here.
    if (
        status_result.status is CompanyStatus.ACTIVE
        and legal_form.code in rules.DEADLINE_FORM_CODES
    ):
        notes.append(rules.CALENDAR_YEAR_NOTE)
    elif (
        status_result.status is CompanyStatus.ACTIVE
        and legal_form.code is not None
        and not legal_form.is_unclassified
    ):
        # Review fix 5: a legal form that is classified — via
        # `organisationsform` or as an SCB `juridiskForm` fallback code —
        # but is not `AB`/`EK` (BRF, HB, KB, E, S, the banks and insurers,
        # any SCB-fallback code, ...) otherwise returns `deadlines == []`
        # with no note explaining why. N6 already covers the *unclassified*
        # case (`legal_form.is_unclassified`); this is the classified one.
        notes.append(rules.no_computed_deadlines_note(legal_form.code, legal_form.english))

    # --- dates -----------------------------------------------------------
    org_datum = reader.wrapper("organisationsdatum", label="the registration date")
    registered_at = _parse_date((org_datum or {}).get("registreringsdatum"))

    # --- activity ----------------------------------------------------------
    activity_text = reader.value(
        "verksamhetsbeskrivning", "beskrivning", label="the activity description"
    )
    activity = _clean_text(activity_text)

    # --- address (§3) ----------------------------------------------------
    postadress_wrapper = reader.wrapper("postadressOrganisation", label="the postal address")
    postal_address = map_address((postadress_wrapper or {}).get("postadress"))

    # --- industry codes ----------------------------------------------------
    naringsgren_wrapper = reader.wrapper("naringsgrenOrganisation", label="the industry code")
    industry_codes = map_industry_codes(naringsgren_wrapper)

    # --- N13: a partial 200 (§1.6, §9) --------------------------------------
    if reader.blocked:
        producers = " and ".join(sorted({producer for _label, producer in reader.blocked}))
        fields_text = ", ".join(label for label, _producer in reader.blocked)
        notes.append(_N13_NOTE.format(producers=producers, fields=fields_text))

    return CompanyReport(
        country="SE",
        registry="bolagsverket",
        id=id_value,
        id_formatted=rules.format_id(id_value),
        id_scheme=id_scheme,
        name=name,
        previous_names=[],
        legal_form_code=legal_form.code,
        legal_form=legal_form.english,
        legal_form_local=legal_form.local,
        limited_liability=legal_form.limited_liability,
        has_board_duty=legal_form.has_board_duty,
        has_annual_accounts_duty=legal_form.has_annual_accounts_duty,
        status=status_result.status,
        status_detail=status_result.status_detail,
        is_active=status_result.is_active,
        registered_at=registered_at,
        founded_at=None,
        business_register_registered_at=None,
        bankruptcy_date=status_result.bankruptcy_date,
        deregistered_at=deregistered_at,
        vat_registered=None,
        vat_registered_at=None,
        vat_number=None,
        in_business_register=None,
        registers={},
        employees=None,
        employees_reported=False,
        industry_codes=industry_codes,
        sector_code=None,
        sector=None,
        purpose=None,
        activity=activity,
        share_capital=None,
        share_capital_currency=None,
        business_address=None,
        postal_address=postal_address,
        website=None,
        email=None,
        phone=None,
        parent_id=None,
        is_subunit=False,
        in_group=None,
        last_annual_accounts_year=None,
        published_deadlines=[],
        confidence=1.0,
        confidence_basis=_CONFIDENCE_BASIS,
        cached=cached,
        fetched_at=fetched_at or datetime.now(UTC),
        source=_SOURCE_NAME,
        source_url=_SOURCE_URL,
        license=_LICENSE,
        notes=notes,
    )
