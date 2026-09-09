"""SE key figures — `include=["financials"]`, out of the filed K2/K3 iXBRL.

**DECISIONS.md D-043(c), D-047(f),(g).** Pure and synchronous, mirroring
`registries/no/accounts.py`'s separation between reading the wire and
building the canonical models: this module owns the concept-to-field table
and the D-043(e)/(f) discipline (nothing derived, an absent line stays
`None`), and reads only through `registries/se/ixbrl.py`'s
:class:`~registry_mcp.registries.se.ixbrl.IXBRLDocument` — never a raw
XHTML byte, never an `ix:nonNumeric` element. `registries/se/client.py`
owns the zip fetch, the cache and the `/dokumentlista`-vs-`/dokument`
request budget; nothing here does I/O.

**The concepts, byte-identical across a 2017-09-30 and a 2021-10-31
taxonomy** (`tasks/T52-recon.md`, `tasks/T55-recon.md`) and matched on local
name only (`ixbrl.py`'s docstring explains why the prefix is never trusted):

| D-043(c) field | concept (local name) |
|---|---|
| `revenue` | `Nettoomsattning` |
| `operating_costs` | `Rorelsekostnader` |
| `operating_result` | `Rorelseresultat` |
| `financial_income` | `OvrigaRanteintakterLiknandeResultatposter` |
| `financial_costs` | `RantekostnaderLiknandeResultatposter` |
| `net_financial_items` | `FinansiellaPoster` |
| `profit_before_tax` | `ResultatForeSkatt` |
| `profit_for_period` | `AretsResultat` |
| `fixed_assets` | `Anlaggningstillgangar` |
| `current_assets` | `Omsattningstillgangar` |
| `total_assets` | `Tillgangar` |
| `paid_in_equity` | `BundetEgetKapital` |
| `retained_equity` | `FrittEgetKapital` |
| `equity` | `EgetKapital` |
| `non_current_liabilities` | `LangfristigaSkulder` |
| `current_liabilities` | `KortfristigaSkulder` |
| `total_equity_and_liabilities` | `EgetKapitalSkulder` |

**`total_comprehensive_income` and `liabilities` are never read and stay
`None` unconditionally** — K2 has no concept for the first, and the ÅRL
balance-sheet format has no "summa skulder" line for the second, so there is
no concept to look up and no arithmetic performed to invent one
(`current_liabilities + non_current_liabilities` is refused by name,
D-043(e), D-043(f) — an absent line is not a zero, so the sum would be
unknowable even if it were permitted).

**`se-gen-base:Soliditet` is never read, mapped or relayed, and neither is
any other ratio concept.** There is no field on `FinancialPeriod` or
`BalanceSheet`/`IncomeStatement` a ratio could land on, and this module's
lookup table (above) is the only place a concept name is ever named — a
concept absent from it is never looked up. `grep -rn "Soliditet" src/` must
find nothing outside a comment explaining why (this one, and `ixbrl.py`'s).

**`accounting_framework` and `scope`/`consolidated` — from the `schemaRef`
path, never from a concept.** `"K2"` or `"K3"` from `ixbrl.schema_ref_says`.
For K2: `scope = "entity accounts"` and `consolidated = False` — **a fact
about the channel, not an inference about the company**: Bolagsverket's K2
digital-submission channel structurally excludes koncernredovisning
(`tasks/T52-recon.md` Fact 2), so every K2 document reaching this module is
entity-only by construction, and the `notes` sentence says so in those
terms. **For K3, both stay `None`** — this task read Bolagsverket's own K3
taxonomy specimens, which publish both an entity-only ("risbs") and a group
("k3k") profile, but not a single live K3 filing (`tasks/T55-recon.md`), so
nothing here has verified which profile a real K3 document declares or
whether the schemaRef reliably distinguishes them on the wire; D-011 forbids
a value that would mean both "entity accounts" and "we did not check".

**`small_entity`, `audit_exempt`, `unaudited`, `liquidation_basis` stay
`None` unconditionally for Sweden.** No concept name for any of the four has
been identified in the K2 or K3 taxonomy by this task (unlike Norway's
`regnkapsprinsipper.smaaForetak` / `revisjon.{fravalgRevisjon,
ikkeRevidertAarsregnskap}` / `avviklingsregnskap`, which are named JSON keys
on a payload this project already reads). `None` is correct here for the
same reason it is correct for any fact the document does not say (D-011) —
a future task that identifies one is a `DECISIONS.md`-worthy addition to
this table, not a guess made here.

**The one permitted comparison (D-043(e)).** When `total_assets` and
`total_equity_and_liabilities` are both present and differ, `notes` names
the gap. Never edits, reconciles or drops either figure. `tasks/T52-recon.md`
measured 18 of 18 of these identities reconciling exactly across every K2
document sampled; if this note ever fires against a real document, that is
worth reporting rather than assuming away.
"""

from __future__ import annotations

from datetime import datetime

from registry_mcp.core.models import (
    BalanceSheet,
    FinancialPeriod,
    FinancialSummary,
    IncomeStatement,
    SourceRef,
)
from registry_mcp.registries.se import ixbrl

__all__ = [
    "LICENSE",
    "SOURCE_NAME",
    "build_period",
    "map_financials",
    "summary_notes",
]

SOURCE_NAME = "Bolagsverket (bolagsverket.se)"
LICENSE = (
    "Free re-use (Bolagsverket/SCB high-value datasets, EU Open Data Directive) — the "
    "publisher names no licence"
)

#: D-043(c) field -> concept local name. The only place a concept name is
#: ever named in this module (module docstring's `Soliditet` guarantee).
_INCOME_STATEMENT_CONCEPTS: dict[str, str] = {
    "revenue": "Nettoomsattning",
    "operating_costs": "Rorelsekostnader",
    "operating_result": "Rorelseresultat",
    "financial_income": "OvrigaRanteintakterLiknandeResultatposter",
    "financial_costs": "RantekostnaderLiknandeResultatposter",
    "net_financial_items": "FinansiellaPoster",
    "profit_before_tax": "ResultatForeSkatt",
    "profit_for_period": "AretsResultat",
}
_BALANCE_SHEET_CONCEPTS: dict[str, str] = {
    "fixed_assets": "Anlaggningstillgangar",
    "current_assets": "Omsattningstillgangar",
    "total_assets": "Tillgangar",
    "paid_in_equity": "BundetEgetKapital",
    "retained_equity": "FrittEgetKapital",
    "equity": "EgetKapital",
    "non_current_liabilities": "LangfristigaSkulder",
    "current_liabilities": "KortfristigaSkulder",
    "total_equity_and_liabilities": "EgetKapitalSkulder",
}

_K2 = "K2"
_K3 = "K3"

_UNMAPPED_FIELDS_NOTE = (
    "`total_comprehensive_income` and `liabilities` are not carried for Sweden: K2 has no "
    "concept for total comprehensive income, and the ÅRL balance-sheet format has no "
    "'summa skulder' line to tag for total liabilities. `current_liabilities` and "
    "`non_current_liabilities` are never added together to build one — an absent line is "
    "not a zero, so the sum would be unknowable even where it would otherwise be allowed "
    "(DECISIONS.md D-043(e),(f))."
)

_K2_SCOPE_NOTE = (
    "`scope` is 'entity accounts' and `consolidated` is false because Bolagsverket's K2 "
    "digital-submission channel structurally excludes koncernredovisning — every K2 "
    "document reaching this block is entity-only by construction, which is a fact about "
    "the channel rather than something inferred about this company."
)

_K3_UNKNOWN_SCOPE_NOTE = (
    "`scope` and `consolidated` are not set for this K3 filing: Bolagsverket's K3 taxonomy "
    "publishes both an entity-only and a group (koncernredovisning) profile, and no live K3 "
    "filing has yet been read to establish whether the schemaRef reliably distinguishes them "
    "on the wire (DECISIONS.md D-011)."
)

_K3_VALIDATION_CAVEAT = (
    "This figure was extracted by a parser validated against filed K2 annual reports and "
    "against Bolagsverket's own published K3 taxonomy specimens, but against no live K3 "
    "filing — none has been available to read (tasks/T55-recon.md). Treat a K3 figure with "
    "correspondingly more caution than a K2 one until a live K3 filing has been checked."
)

_COMPARABILITY_NOTE = (
    "These figures are denominated in this period's own currency and prepared under its own "
    "accounting framework — see `currency` and `accounting_framework` on the period — and are "
    "not comparable across companies or across borders without regard to both. Nothing here "
    "converts, restates or annualises a figure."
)

_LATEST_ONLY_NOTE = (
    "This is the most recently filed annual report only. Bolagsverket's document list "
    "reported {total} annual report(s) for this organisation in total, covering the period "
    "ending {period_end}; the complete list with every period and document id is available "
    'through include=["filings"].'
)

_RECONCILIATION_NOTE = (
    "This filing's total assets ({total_assets}) and total equity and liabilities "
    "({total_equity_and_liabilities}) differ by {gap} — the register's own figures, relayed "
    "exactly as filed; neither is edited, reconciled or dropped (DECISIONS.md D-043(e))."
)

_CURRENCY_UNRESOLVED_NOTE = (
    "The most recently filed annual report could not be carried in this block because no "
    "monetary fact in it resolved to a single, unambiguous currency. A figure without its "
    "currency is not carried by this API (DECISIONS.md D-043(d))."
)


def _map_income_statement(doc: ixbrl.IXBRLDocument) -> IncomeStatement | None:
    values = {
        field: fact.value
        for field, concept in _INCOME_STATEMENT_CONCEPTS.items()
        if (fact := doc.latest(concept)) is not None
    }
    if not values:
        return None
    return IncomeStatement(**values)


def _map_balance_sheet(doc: ixbrl.IXBRLDocument) -> BalanceSheet | None:
    values = {
        field: fact.value
        for field, concept in _BALANCE_SHEET_CONCEPTS.items()
        if (fact := doc.latest(concept)) is not None
    }
    if not values:
        return None
    return BalanceSheet(**values)


def _accounting_framework(doc: ixbrl.IXBRLDocument) -> str | None:
    if ixbrl.schema_ref_says(doc.schema_refs, "k2"):
        return _K2
    if ixbrl.schema_ref_says(doc.schema_refs, "k3"):
        return _K3
    return None


def _resolve_currency(doc: ixbrl.IXBRLDocument) -> str | None:
    """The single currency shared by every wanted concept's fact at the
    latest period, or `None` when zero or more than one distinct currency is
    observed — either way, D-043(d) says the period is not carried at all."""
    currencies = {
        fact.currency
        for concept in {**_INCOME_STATEMENT_CONCEPTS, **_BALANCE_SHEET_CONCEPTS}.values()
        if (fact := doc.latest(concept)) is not None and fact.currency is not None
    }
    if len(currencies) == 1:
        return next(iter(currencies))
    return None


def build_period(doc: ixbrl.IXBRLDocument, *, document_id: str) -> FinancialPeriod | None:
    """The one `FinancialPeriod` this document can carry, or `None` when no
    single, unambiguous currency can be established for it (D-043(d)) — the
    **only** reason this returns `None`; every other absence (no documents
    at all, a fetch or parse failure) is handled one level up, in
    `registries/se/client.py::fetch_financials`, by raising before this
    function is ever reached.

    This is the one artefact `registries/se/client.py` caches under
    `SE:bolagsverket:financials:{env}:{dokumentId}` — the hard rule in
    `tasks/T55.md` §D is that nothing else about the document is ever
    stored, and this function's return value is exactly and only what a
    `FinancialPeriod` needs to be reconstructed later without re-parsing.
    """
    currency = _resolve_currency(doc)
    if currency is None:
        return None
    accounting_framework = _accounting_framework(doc)
    return FinancialPeriod(
        period_start=doc.latest_period_start,
        period_end=doc.latest_period_end,
        currency=currency,
        accounting_framework=accounting_framework,
        scope="entity accounts" if accounting_framework == _K2 else None,
        consolidated=False if accounting_framework == _K2 else None,
        small_entity=None,
        audit_exempt=None,
        unaudited=None,
        liquidation_basis=None,
        document_id=document_id,
        income_statement=_map_income_statement(doc),
        balance_sheet=_map_balance_sheet(doc),
    )


def summary_notes(period: FinancialPeriod | None, *, total_annual_reports: int) -> list[str]:
    """The full `FinancialSummary.notes` list for `period` (or for the
    currency-unresolved case, `period is None`).

    Deliberately takes a **built** `FinancialPeriod` rather than the
    `IXBRLDocument` it came from: `registries/se/client.py` calls this on a
    freshly parsed period *and* on one read back from the per-document
    cache, so that `total_annual_reports` — a fact about the **list**, which
    is cached separately and on a much shorter TTL (D-047(f)) — is always
    current even when the figures themselves are served from a 30-day-old
    cache entry. Nothing here re-derives a figure; it only assembles the
    caveats that were always going to be true of `period`.
    """
    if period is None:
        return [_CURRENCY_UNRESOLVED_NOTE]

    notes: list[str] = [
        _COMPARABILITY_NOTE,
        _LATEST_ONLY_NOTE.format(
            total=total_annual_reports,
            period_end=period.period_end.isoformat() if period.period_end else "unknown",
        ),
        _UNMAPPED_FIELDS_NOTE,
    ]
    if period.accounting_framework == _K2:
        notes.append(_K2_SCOPE_NOTE)
    elif period.accounting_framework == _K3:
        notes.append(_K3_UNKNOWN_SCOPE_NOTE)
        notes.append(_K3_VALIDATION_CAVEAT)

    sheet = period.balance_sheet
    if sheet is not None:
        total_assets = sheet.total_assets
        total_equity_and_liabilities = sheet.total_equity_and_liabilities
        if (
            total_assets is not None
            and total_equity_and_liabilities is not None
            and total_assets != total_equity_and_liabilities
        ):
            gap = abs(total_assets - total_equity_and_liabilities)
            notes.append(
                _RECONCILIATION_NOTE.format(
                    total_assets=f"{total_assets:,.0f}",
                    total_equity_and_liabilities=f"{total_equity_and_liabilities:,.0f}",
                    gap=f"{gap:,.0f}",
                )
            )
    return notes


def map_financials(
    doc: ixbrl.IXBRLDocument,
    *,
    document_id: str,
    total_annual_reports: int,
    source_url: str,
    cached: bool,
    fetched_at: datetime,
) -> FinancialSummary:
    """Pure, synchronous, no I/O. Builds the `financials` block from one
    already-parsed :class:`~registry_mcp.registries.se.ixbrl.IXBRLDocument`
    by composing :func:`build_period` and :func:`summary_notes` — the
    convenience entry point for a **fresh** fetch; `registries/se/client.py`
    calls the two pieces separately on a cache hit, where there is a
    `FinancialPeriod` to reuse but no `IXBRLDocument` (none is ever stored).

    Never raises: see :func:`build_period` for the one case this yields an
    empty `periods` list rather than a filled one.
    """
    period = build_period(doc, document_id=document_id)
    notes = summary_notes(period, total_annual_reports=total_annual_reports)
    return FinancialSummary(
        periods=[period] if period is not None else [],
        provenance=SourceRef(
            source=SOURCE_NAME,
            source_url=source_url,
            license=LICENSE,
            fetched_at=fetched_at,
            cached=cached,
        ),
        notes=notes,
    )
