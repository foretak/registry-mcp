"""Enhetsregisteret JSON -> ``core/models.py`` shapes.

Pure, synchronous, no I/O. ``registries/no/client.py`` calls these functions
after it has the raw JSON in hand. See ``NORBIZ_SPEC.md`` §§2-4, 8.

Legal-form classification and status derivation are business *rules*, owned by
T02 in ``registries/no/rules.py`` (``NORBIZ_SPEC.md`` §14). This module only
reshapes data; it does not decide whether ``AS`` implies a board.

``rules`` is imported lazily (inside :func:`_rules`, not at module import
time) rather than at the top of the file. T02's ``registries/no/rules.py`` was
built in parallel with this module in the same session; a lazy import means
this module — and its pure formatting/address/search helpers — could always be
imported and exercised regardless of which file landed first, and tests can
still monkeypatch :func:`_rules` to isolate mapping logic from rules logic.
Now that ``rules.py`` exists, this module calls its real API: ``validate_orgnr``,
``legal_form_info(code, local_description) -> LegalFormInfo`` (fields ``english``,
``limited_liability``, ``has_board_duty``, ``has_annual_accounts_duty``,
``is_subunit``, ``notes``), ``derive_status(*, bankrupt, under_liquidation,
under_compulsory_liquidation, deleted_at, bankruptcy_date) -> StatusResult``
(fields ``status``, ``status_detail``, ``is_active``, ``notes``), and
``deadline_exemption_note(report) -> str | None``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Any

from registry_mcp.core.models import (
    Address,
    CompanyReport,
    IndustryCode,
    SearchHit,
    SearchResult,
)

__all__ = [
    "format_orgnr",
    "map_address",
    "map_entity",
    "map_industry_codes",
    "map_previous_names",
    "map_registers",
    "map_search_hit",
    "map_search_result",
]

#: Norwegian sub-unit legal-form codes (`NORBIZ_SPEC.md` §2, `is_subunit`).
_SUBUNIT_FORMS = frozenset({"BEDR", "AAFY"})

#: `CompanyReport.registers` keys -> brreg boolean field (`NORBIZ_SPEC.md` §2).
_REGISTER_FIELDS = {
    "foretaksregisteret": "registrertIForetaksregisteret",
    "stiftelsesregisteret": "registrertIStiftelsesregisteret",
    "frivillighetsregisteret": "registrertIFrivillighetsregisteret",
    "partiregisteret": "registrertIPartiregisteret",
    "mvaregisteret": "registrertIMvaregisteret",
}


def _rules() -> ModuleType:
    """Lazily import ``registries/no/rules.py`` (T02's module).

    A plain function (rather than a module-level import) so that:
    (a) importing ``mapping`` never fails while ``rules.py`` doesn't exist yet,
        and (b) tests can monkeypatch this one seam to inject a fake rules
        module without needing the real one.
    """
    import registry_mcp.registries.no.rules as rules_module

    return rules_module


def format_orgnr(orgnr: str) -> str:
    """``"923609016"`` -> ``"923 609 016"`` (three groups of three)."""
    return f"{orgnr[0:3]} {orgnr[3:6]} {orgnr[6:9]}"


def _join_text_lines(lines: list[str] | None) -> str | None:
    """Join brreg's arbitrary line-wrapped text fragments into one string."""
    if not lines:
        return None
    return " ".join(lines)


def _parse_date(raw: str | None) -> date | None:
    """brreg dates are plain ``YYYY-MM-DD``; anything else stays ``None``."""
    if not raw:
        return None
    return date.fromisoformat(raw)


def map_address(data: Mapping[str, Any] | None) -> Address | None:
    """Map a brreg ``forretningsadresse`` / ``postadresse`` object (`NORBIZ_SPEC.md` §3)."""
    if not data:
        return None
    return Address(
        lines=list(data.get("adresse") or []),
        postal_code=data.get("postnummer"),
        city=data.get("poststed"),
        municipality=data.get("kommune"),
        municipality_code=data.get("kommunenummer"),
        country_code=data.get("landkode"),
        country_name=data.get("land"),
    )


def map_industry_codes(data: Mapping[str, Any]) -> list[IndustryCode]:
    """``naeringskode1..3`` -> ranked ``IndustryCode`` list (`NORBIZ_SPEC.md` §2)."""
    codes: list[IndustryCode] = []
    for rank, key in enumerate(("naeringskode1", "naeringskode2", "naeringskode3"), start=1):
        entry = data.get(key)
        if entry:
            codes.append(
                IndustryCode(
                    code=entry["kode"],
                    description=entry.get("beskrivelse"),
                    scheme="NACE",
                    rank=rank,
                )
            )
    return codes


def map_previous_names(data: Mapping[str, Any]) -> list[str]:
    """``historiskeNavn[].navn``, newest first (the API gives oldest first)."""
    history = data.get("historiskeNavn") or []
    return [entry["navn"] for entry in reversed(history)]


def map_registers(data: Mapping[str, Any]) -> dict[str, bool]:
    """The five sub-register membership flags, keyed lower-case (`NORBIZ_SPEC.md` §2)."""
    return {slug: bool(data.get(field, False)) for slug, field in _REGISTER_FIELDS.items()}


def map_entity(
    data: Mapping[str, Any],
    *,
    source_url: str,
    is_subunit: bool = False,
    cached: bool = False,
    fetched_at: datetime | None = None,
) -> CompanyReport:
    """Build a full ``CompanyReport`` from one ``GET /enheter/{orgnr}`` (or
    ``/underenheter/{orgnr}``) response body.

    Args:
        data: The parsed JSON body.
        source_url: The exact URL this document was fetched from, for citation.
        is_subunit: True when this record came from ``/underenheter``.
        cached: Whether this report is being served from the cache.
        fetched_at: The original fetch time (preserved across cache hits per
            ``DECISIONS.md`` D-006). Defaults to now.
    """
    rules = _rules()

    orgnr = str(data["organisasjonsnummer"])
    org_form = data.get("organisasjonsform") or {}
    legal_form_code = org_form.get("kode")
    legal_form_local = org_form.get("beskrivelse")

    form_info = None
    if legal_form_code:
        form_info = rules.legal_form_info(legal_form_code, legal_form_local or "")

    status_info = rules.derive_status(
        bankrupt=data.get("konkurs"),
        under_liquidation=data.get("underAvvikling"),
        under_compulsory_liquidation=data.get("underTvangsavviklingEllerTvangsopplosning"),
        deleted_at=_parse_date(data.get("slettedato")),
        bankruptcy_date=_parse_date(data.get("konkursdato")),
    )

    notes: list[str] = list(status_info.notes)
    if form_info is not None:
        notes.extend(form_info.notes)

    vat_registered = bool(data.get("registrertIMvaregisteret", False))
    employees_reported = bool(data.get("harRegistrertAntallAnsatte", False))
    employees = data.get("antallAnsatte") if employees_reported else None

    kapital = data.get("kapital") or {}
    last_year_raw = data.get("sisteInnsendteAarsregnskap")

    subunit = is_subunit or (form_info.is_subunit if form_info else False)

    report = CompanyReport(
        country="NO",
        registry="brreg",
        id=orgnr,
        id_formatted=format_orgnr(orgnr),
        id_scheme="organisasjonsnummer",
        name=data["navn"],
        previous_names=map_previous_names(data),
        legal_form_code=legal_form_code,
        legal_form=(form_info.english if form_info else legal_form_local),
        legal_form_local=legal_form_local,
        limited_liability=(form_info.limited_liability if form_info else None),
        has_board_duty=(form_info.has_board_duty if form_info else None),
        has_annual_accounts_duty=(form_info.has_annual_accounts_duty if form_info else None),
        status=status_info.status,
        status_detail=status_info.status_detail,
        is_active=status_info.is_active,
        registered_at=_parse_date(data.get("registreringsdatoEnhetsregisteret")),
        founded_at=_parse_date(data.get("stiftelsesdato")),
        business_register_registered_at=_parse_date(
            data.get("registreringsdatoForetaksregisteret")
        ),
        bankruptcy_date=_parse_date(data.get("konkursdato")),
        deregistered_at=_parse_date(data.get("slettedato")),
        vat_registered=vat_registered,
        vat_registered_at=_parse_date(data.get("registreringsdatoMerverdiavgiftsregisteret")),
        vat_number=(f"NO{orgnr}MVA" if vat_registered else None),
        in_business_register=bool(data.get("registrertIForetaksregisteret", False)),
        registers=map_registers(data),
        employees=employees,
        employees_reported=employees_reported,
        industry_codes=map_industry_codes(data),
        sector_code=(data.get("institusjonellSektorkode") or {}).get("kode"),
        sector=(data.get("institusjonellSektorkode") or {}).get("beskrivelse"),
        purpose=_join_text_lines(data.get("vedtektsfestetFormaal")),
        activity=_join_text_lines(data.get("aktivitet")),
        share_capital=kapital.get("belop"),
        share_capital_currency=kapital.get("valuta"),
        business_address=map_address(data.get("forretningsadresse")),
        postal_address=map_address(data.get("postadresse")),
        website=data.get("hjemmeside"),
        email=data.get("epostadresse"),
        phone=data.get("telefon"),
        parent_id=data.get("overordnetEnhet"),
        is_subunit=subunit,
        in_group=data.get("erIKonsern"),
        last_annual_accounts_year=(int(last_year_raw) if last_year_raw is not None else None),
        confidence=1.0,
        confidence_basis="exact identifier lookup in Enhetsregisteret",
        cached=cached,
        fetched_at=fetched_at or datetime.now(UTC),
        source="Enhetsregisteret (Brønnøysundregistrene)",
        source_url=source_url,
        license="NLOD 2.0",
        notes=notes,
    )

    exemption_note = rules.deadline_exemption_note(report)
    if exemption_note:
        report.notes.append(exemption_note)

    return report


def _confidence_for_hit(query: str, name: str) -> tuple[float, str]:
    """Search-hit confidence per ``DECISIONS.md`` D-005 / `NORBIZ_SPEC.md` §4, §12."""
    q = query.strip().casefold()
    n = name.strip().casefold()
    if q == n:
        return 0.95, "search hit name matches the query exactly, case-insensitively"
    if n.startswith(q):
        return 0.8, "search hit name starts with the query"
    tokens = q.split()
    if tokens and all(token in n for token in tokens):
        return 0.6, "search hit name contains every query token"
    return 0.4, "search hit returned by the registry with no stronger match"


def map_search_hit(data: Mapping[str, Any], *, query: str) -> SearchHit:
    """One ``_embedded.enheter[]`` entry -> ``SearchHit`` (`NORBIZ_SPEC.md` §4)."""
    rules = _rules()
    org_form = data.get("organisasjonsform") or {}
    legal_form_code = org_form.get("kode")
    legal_form_local = org_form.get("beskrivelse")
    name = data["navn"]

    form_info = None
    if legal_form_code:
        form_info = rules.legal_form_info(legal_form_code, legal_form_local or "")

    status_info = rules.derive_status(
        bankrupt=data.get("konkurs"),
        under_liquidation=data.get("underAvvikling"),
        under_compulsory_liquidation=data.get("underTvangsavviklingEllerTvangsopplosning"),
        deleted_at=_parse_date(data.get("slettedato")),
        bankruptcy_date=_parse_date(data.get("konkursdato")),
    )
    confidence, basis = _confidence_for_hit(query, name)
    address = data.get("forretningsadresse") or {}
    is_subunit = form_info.is_subunit if form_info else (legal_form_code in _SUBUNIT_FORMS)

    return SearchHit(
        country="NO",
        registry="brreg",
        id=str(data["organisasjonsnummer"]),
        name=name,
        legal_form_code=legal_form_code,
        legal_form=(form_info.english if form_info else legal_form_local),
        status=status_info.status,
        city=address.get("poststed"),
        municipality=address.get("kommune"),
        registered_at=_parse_date(data.get("registreringsdatoEnhetsregisteret")),
        is_subunit=is_subunit,
        confidence=confidence,
        confidence_basis=basis,
        source_url=(
            f"https://data.brreg.no/enhetsregisteret/api/enheter/{data['organisasjonsnummer']}"
        ),
    )


def map_search_result(
    data: Mapping[str, Any],
    *,
    query: str,
    cached: bool = False,
    fetched_at: datetime | None = None,
) -> SearchResult:
    """A full ``GET /enheter?navn=...`` HAL envelope -> ``SearchResult`` (`NORBIZ_SPEC.md` §4)."""
    hits_raw = data.get("_embedded", {}).get("enheter", [])
    hits = [map_search_hit(hit, query=query) for hit in hits_raw]
    total = data.get("page", {}).get("totalElements", len(hits))
    truncated = total > len(hits)

    if total == 0:
        hint = f"No companies match {query!r}. Try a shorter or different name."
    else:
        hint = (
            f"{total} compan{'y' if total == 1 else 'ies'} match. "
            "Call lookup_company with the id of the right hit for the full report."
        )

    return SearchResult(
        country="NO",
        registry="brreg",
        query=query,
        hits=hits,
        total=total,
        truncated=truncated,
        cached=cached,
        fetched_at=fetched_at or datetime.now(UTC),
        hint=hint,
    )
