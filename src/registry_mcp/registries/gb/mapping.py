"""Companies House JSON -> ``core/models.py`` shapes.

Pure, synchronous, no I/O. ``registries/gb/client.py`` calls these functions
after it has the raw JSON in hand. See ``UK_SPEC.md`` §§2-4, 8.

Legal-form classification and status derivation are business *rules*, owned
by ``registries/gb/rules.py`` (``UK_SPEC.md`` §7, §8). This module only
reshapes data; it does not decide whether ``ltd`` implies a board.

Every field is read with ``.get()`` — CIO/registered-society profiles are
11-key stubs missing ``company_status``, ``date_of_creation``,
``registered_office_address``, ``accounts`` and ``confirmation_statement``
entirely (``UK_SPEC.md`` §2.2), and a mapper that indexes rather than
``.get()``s raises ``KeyError`` on them.

``rules`` is imported lazily (inside :func:`_rules`), matching
``registries/no/mapping.py``'s convention, so this module stays importable
and testable independent of ``rules.py``'s presence/edit state.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Any

from registry_mcp.core.models import (
    Address,
    CompanyReport,
    CompanyStatus,
    IndustryCode,
    PublishedDeadline,
    SearchHit,
    SearchResult,
)

__all__ = [
    "map_address",
    "map_entity",
    "map_industry_codes",
    "map_previous_names",
    "map_registers",
    "map_search_hit",
    "map_search_result",
]

#: Legal forms whose ``date_of_creation`` is the date of *UK* registration,
#: not of foundation abroad (`UK_SPEC.md` §2) — so `founded_at` stays `None`.
_FOUNDED_AT_EXEMPT = frozenset({"oversea-company", "uk-establishment", "registered-overseas-entity"})

#: Free-text `country` values on a `registered_office_address` that we are
#: confident map to the ISO code `GB` (`UK_SPEC.md` §3). Everything else
#: (a foreign country name) stays `None` rather than guessing.
_UK_COUNTRY_NAMES = frozenset(
    {"england", "scotland", "wales", "northern ireland", "united kingdom", "great britain"}
)

_FIND_AND_UPDATE_URL = "https://find-and-update.company-information.service.gov.uk/company/{id}"


def _rules() -> ModuleType:
    """Lazily import ``registries/gb/rules.py`` (see module docstring)."""
    import registry_mcp.registries.gb.rules as rules_module

    return rules_module


def _parse_date(raw: Any) -> date | None:
    """CH dates are plain ``YYYY-MM-DD``; anything else, or absent, stays ``None``."""
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def map_address(data: Mapping[str, Any] | None) -> Address | None:
    """Map a ``registered_office_address`` / ``service_address`` object.

    Every component is individually optional, including on a live plc
    (`UK_SPEC.md` §3, §1.6 №4/№5) — a missing address object maps to `None`,
    not to an empty `Address`.
    """
    if not data:
        return None

    lines: list[str] = []
    for key in ("care_of", "po_box", "premises", "address_line_1", "address_line_2"):
        value = data.get(key)
        if value:
            lines.append(str(value))

    country_name = data.get("country")
    country_code = None
    if country_name and country_name.strip().lower() in _UK_COUNTRY_NAMES:
        country_code = "GB"

    return Address(
        lines=lines,
        postal_code=data.get("postal_code"),
        city=data.get("locality"),
        municipality=data.get("region"),
        municipality_code=None,
        country_code=country_code,
        country_name=country_name,
    )


def map_previous_names(data: Mapping[str, Any]) -> list[str]:
    """``previous_company_names[]``, newest first by ``ceased_on`` (`UK_SPEC.md` §2)."""
    history = data.get("previous_company_names") or []
    ordered = sorted(history, key=lambda entry: entry.get("ceased_on") or "", reverse=True)
    return [entry["name"] for entry in ordered if entry.get("name")]


def map_industry_codes(data: Mapping[str, Any]) -> list[IndustryCode]:
    """``sic_codes[]`` -> ranked ``IndustryCode`` list. Descriptions are `DEFERRED` (§5.5)."""
    codes = data.get("sic_codes") or []
    return [
        IndustryCode(code=code, description=None, scheme="SIC 2007", rank=rank)
        for rank, code in enumerate(codes, start=1)
    ]


def map_registers(data: Mapping[str, Any]) -> dict[str, bool]:
    """``registers["charges"]``/``["insolvency"]`` — read the deprecated booleans,
    not ``links.*``: ``links.charges`` is present even when ``has_charges`` is
    ``false`` (`UK_SPEC.md` §1.6 №1, §2). Absent booleans map to ``False``."""
    return {
        "charges": bool(data.get("has_charges")),
        "insolvency": bool(data.get("has_insolvency_history")),
    }


def _is_subunit(data: Mapping[str, Any]) -> bool:
    return data.get("type") == "uk-establishment" or bool(data.get("branch_company_details"))


def _is_stub_profile(data: Mapping[str, Any]) -> bool:
    """A CIO/registered-society stub carries neither a status nor an
    incorporation date at all (`UK_SPEC.md` §2.2) — a healthy company or
    branch/overseas profile always carries at least one of the two."""
    return "company_status" not in data and "date_of_creation" not in data


def _activity(data: Mapping[str, Any]) -> str | None:
    branch = data.get("branch_company_details") or {}
    if branch.get("business_activity"):
        activity: str = branch["business_activity"]
        return activity
    foreign = data.get("foreign_company_details") or {}
    result = foreign.get("business_activity")
    return str(result) if result else None


def _last_annual_accounts_year(data: Mapping[str, Any]) -> int | None:
    last = (data.get("accounts") or {}).get("last_accounts") or {}
    parsed = _parse_date(last.get("period_end_on") or last.get("made_up_to"))
    return parsed.year if parsed else None


def _published_deadlines(data: Mapping[str, Any], rules: ModuleType) -> list[PublishedDeadline]:
    """``CompanyReport.published_deadlines`` (``DECISIONS.md`` D-018): the
    register's own filing dates for this entity, carried verbatim so
    ``rules.deadlines_for(report, today)`` never needs the raw payload again.
    An entry is emitted whenever a date *or* a period end is published — the
    computed rung (``rules.py``'s step 3) needs ``period_end`` even when no
    date is (``ch_FC032315.json`` is exactly that shape, live).
    """
    entries: list[PublishedDeadline] = []

    accounts = data.get("accounts") or {}
    next_accounts = accounts.get("next_accounts") or {}
    accounts_due = _parse_date(next_accounts.get("due_on"))
    accounts_source = rules.ACCOUNTS_DUE_ON_SOURCE
    if accounts_due is None:
        accounts_due = _parse_date(accounts.get("next_due"))
        accounts_source = rules.ACCOUNTS_NEXT_DUE_SOURCE
    accounts_period_end = _parse_date(next_accounts.get("period_end_on"))
    accounts_overdue = next_accounts.get("overdue")
    if accounts_overdue is None:
        accounts_overdue = accounts.get("overdue")
    if accounts_due is not None or accounts_period_end is not None:
        entries.append(
            PublishedDeadline(
                kind=rules.ACCOUNTS_KIND,
                due_date=accounts_due,
                period_start=_parse_date(next_accounts.get("period_start_on")),
                period_end=accounts_period_end,
                overdue=(bool(accounts_overdue) if accounts_overdue is not None else None),
                source=(accounts_source if accounts_due is not None else None),
            )
        )

    cs = data.get("confirmation_statement") or {}
    cs_due = _parse_date(cs.get("next_due"))
    cs_period_end = _parse_date(cs.get("next_made_up_to"))
    cs_overdue = cs.get("overdue")
    if cs_due is not None or cs_period_end is not None:
        entries.append(
            PublishedDeadline(
                kind=rules.CONFIRMATION_KIND,
                due_date=cs_due,
                period_start=None,
                period_end=cs_period_end,
                overdue=(bool(cs_overdue) if cs_overdue is not None else None),
                source=(rules.CONFIRMATION_NEXT_DUE_SOURCE if cs_due is not None else None),
            )
        )

    return entries


def map_entity(
    data: Mapping[str, Any],
    *,
    cached: bool = False,
    fetched_at: datetime | None = None,
) -> CompanyReport:
    """Build a full ``CompanyReport`` from one ``GET /company/{company_number}`` body.

    Args:
        data: The parsed JSON body.
        cached: Whether this report is being served from the cache.
        fetched_at: The original fetch time (preserved across cache hits per
            ``DECISIONS.md`` D-006). Defaults to now.
    """
    rules = _rules()

    company_number = str(data["company_number"])
    type_code = (data.get("type") or "").strip() or None
    subtype = data.get("subtype")

    form_info = rules.legal_form_info(type_code, subtype) if type_code else None

    status_info = rules.derive_status(
        company_status=data.get("company_status"),
        company_status_detail=data.get("company_status_detail"),
        date_of_cessation=_parse_date(data.get("date_of_cessation")),
    )

    notes: list[str] = list(status_info.notes)

    if type_code is None:
        notes.append(
            "Companies House did not return a legal form (`type`) for this entity, so its "
            "duties are unknown, not absent."
        )
    elif form_info is not None:
        notes.extend(form_info.notes)

    if data.get("has_insolvency_history") and status_info.status is CompanyStatus.ACTIVE:
        notes.append(
            "This company has insolvency filings in its history. It is active today; the "
            "filings may relate to a concluded arrangement or to an administration it has "
            "since exited."
        )

    if data.get("registered_office_is_in_dispute"):
        notes.append(
            "The registered office address shown is disputed and may have been replaced by "
            "Companies House with a default address. Do not rely on it for correspondence."
        )
    if data.get("undeliverable_registered_office_address"):
        notes.append("Companies House cannot deliver post to this registered office address.")

    if data.get("partial_data_available"):
        notes.append(
            "Companies House is not the primary source of data for this entity, so this "
            f"record is incomplete ({data['partial_data_available']})."
        )
    if data.get("external_registration_number"):
        notes.append(
            "This entity's full record is held by another regulator under registration "
            f"number {data['external_registration_number']}."
        )

    if _is_stub_profile(data):
        notes.append(
            "Companies House holds only a minimal record for this entity: no status, "
            "incorporation date or registered office address was returned. The register "
            "named above is the authoritative source."
        )

    for annotation in data.get("corporate_annotation") or []:
        description = annotation.get("description")
        notes.append(
            description
            if description
            else f"Companies House recorded an annotation of type {annotation.get('type')!r} "
            "for this entity."
        )

    jurisdiction = data.get("jurisdiction")
    if jurisdiction and jurisdiction.strip().lower() != "england-wales":
        notes.append(f"Registered under the law of {jurisdiction}.")

    is_subunit = _is_subunit(data)
    parent_id = (data.get("branch_company_details") or {}).get("parent_company_number")
    if is_subunit:
        notes.append(
            "This record is a UK establishment of an overseas company, not a company in "
            f"its own right. Look up parent_id ({parent_id}) for the entity that files."
        )

    if data.get("annual_return"):
        notes.append(
            "This company's last periodic filing was an annual return, a form abolished in "
            "June 2016 and replaced by the confirmation statement. Treat any annual-return "
            "due date on this record as historical."
        )

    date_of_creation = _parse_date(data.get("date_of_creation"))
    founded_at = None if type_code in _FOUNDED_AT_EXEMPT else date_of_creation

    report = CompanyReport(
        country="GB",
        registry="companies-house",
        id=company_number,
        id_formatted=None,
        id_scheme="company number",
        name=data["company_name"],
        previous_names=map_previous_names(data),
        legal_form_code=type_code,
        legal_form=(form_info.english if form_info else None),
        legal_form_local=None,
        limited_liability=(form_info.limited_liability if form_info else None),
        has_board_duty=(form_info.has_board_duty if form_info else None),
        has_annual_accounts_duty=(form_info.has_annual_accounts_duty if form_info else None),
        status=status_info.status,
        status_detail=status_info.status_detail,
        is_active=status_info.is_active,
        registered_at=date_of_creation,
        founded_at=founded_at,
        business_register_registered_at=None,
        bankruptcy_date=None,
        deregistered_at=_parse_date(data.get("date_of_cessation")),
        vat_registered=None,
        vat_registered_at=None,
        vat_number=None,
        in_business_register=None,
        registers=map_registers(data),
        employees=None,
        employees_reported=False,
        industry_codes=map_industry_codes(data),
        sector_code=None,
        sector=None,
        purpose=None,
        activity=_activity(data),
        share_capital=None,
        share_capital_currency=None,
        business_address=map_address(data.get("registered_office_address")),
        postal_address=map_address(data.get("service_address")),
        website=None,
        email=None,
        phone=None,
        parent_id=parent_id,
        is_subunit=is_subunit,
        in_group=None,
        last_annual_accounts_year=_last_annual_accounts_year(data),
        published_deadlines=_published_deadlines(data, rules),
        confidence=1.0,
        confidence_basis="exact identifier lookup in the Companies House register",
        cached=cached,
        fetched_at=fetched_at or datetime.now(UTC),
        source="Companies House (UK)",
        source_url=_FIND_AND_UPDATE_URL.format(id=company_number),
        license="Crown copyright — Companies House public register, free to re-use",
        notes=notes,
    )

    report.notes.extend(rules.deadline_exemption_note(data, report))
    return report


# ---------------------------------------------------------------------------
# §4 — Search mapping
# ---------------------------------------------------------------------------


def _confidence_for_hit(query: str, title: str | None) -> tuple[float, str]:
    """Search-hit confidence per ``DECISIONS.md`` D-005 / `UK_SPEC.md` §4, §12."""
    q = " ".join(query.strip().casefold().split())
    n = " ".join((title or "").strip().casefold().split())
    if q == n:
        return 0.95, "search hit title matches the query exactly, case-insensitively"
    if n.startswith(q):
        return 0.8, "search hit title starts with the query"
    tokens = q.split()
    if tokens and all(token in n for token in tokens):
        return 0.6, "search hit title contains every query token"
    return 0.4, "search hit returned by the register with no stronger match"


def map_search_hit(item: Mapping[str, Any], *, query: str) -> SearchHit:
    """One ``items[]`` entry -> ``SearchHit`` (`UK_SPEC.md` §4).

    ``company_status`` is absent on some hits (every CIO in a `q=community`
    sample, §1.6 №6) — read with ``.get()``, never index, so that maps to
    ``CompanyStatus.UNKNOWN`` rather than raising ``KeyError``.
    """
    rules = _rules()
    company_type = item.get("company_type")
    form_info = rules.legal_form_info(company_type) if company_type else None
    status_info = rules.derive_status(company_status=item.get("company_status"))
    title = item.get("title") or ""
    confidence, basis = _confidence_for_hit(query, title)
    address = item.get("address") or {}
    company_number = str(item["company_number"])

    return SearchHit(
        country="GB",
        registry="companies-house",
        id=company_number,
        name=title,
        legal_form_code=company_type,
        legal_form=(form_info.english if form_info else None),
        status=status_info.status,
        city=address.get("locality"),
        municipality=address.get("region"),
        registered_at=_parse_date(item.get("date_of_creation")),
        is_subunit=(company_type == "uk-establishment"),
        confidence=confidence,
        confidence_basis=basis,
        source_url=_FIND_AND_UPDATE_URL.format(id=company_number),
    )


_ZERO_HITS_HINT = (
    "No companies match that name. Sole traders and ordinary partnerships are not "
    "registered at Companies House, so they will never appear here."
)


def map_search_result(
    data: Mapping[str, Any],
    *,
    query: str,
    cached: bool = False,
    fetched_at: datetime | None = None,
) -> SearchResult:
    """A full ``GET /search/companies`` envelope -> ``SearchResult`` (`UK_SPEC.md` §4)."""
    items = data.get("items") or []
    hits = [map_search_hit(item, query=query) for item in items]
    total = data.get("total_results", 0)
    truncated = total > len(hits)

    if total == 0:
        hint = _ZERO_HITS_HINT
    else:
        hint = (
            f"{total} compan{'y' if total == 1 else 'ies'} match. Call lookup_company with "
            "the id of the right hit for the full report."
        )

    return SearchResult(
        country="GB",
        registry="companies-house",
        query=query,
        hits=hits,
        total=total,
        truncated=truncated,
        cached=cached,
        fetched_at=fetched_at or datetime.now(UTC),
        hint=hint,
    )
