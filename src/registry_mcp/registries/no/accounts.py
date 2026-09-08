"""NO annual accounts — ``GET data.brreg.no/regnskapsregisteret/regnskap/{orgnr}``.

**R-5d** (``DECISIONS.md`` D-042(i)). This module maps the wire straight onto
the canonical :class:`~registry_mcp.core.models.FiledDocument` /
:class:`~registry_mcp.core.models.FilingHistory` /
:class:`~registry_mcp.core.models.SourceRef` (D-041(d), as widened by
D-042(h)) — the same shapes ``registries/se/filings.py`` and
``registries/gb/filing_history.py`` build, because all three registers
converged on one shape independently (D-044(a)). There is no local stand-in
and nothing to convert: :func:`map_regnskap` constructs the canonical
classes directly, and ``BrregRegistry.filings``
(``registries/no/__init__.py``) returns
:func:`registry_mcp.registries.no.client.fetch_accounts`'s result unchanged.
**Nothing here touches ``mcp/`` or ``api/``.**

Recon behind every choice below — live, keyless calls to
``https://data.brreg.no/regnskapsregisteret/regnskap/{orgnr}`` on 2026-09-08,
roughly 700 entities across ``AS``, ``ASA``, ``SA``, ``STI``, ``BRL``,
``ANS``, ``DA``, ``NUF`` and ``ENK`` — is reported in full to the
orchestrator. The load-bearing findings, so a later reader does not re-derive
them:

* **The response is a bare JSON array**, not an envelope: ``[{…}]``. There is
  no ``dataproducent``/``fel`` wrapper and no HAL ``_embedded`` — unlike
  ``/enhetsregisteret/api/enheter``, whose search shape ``mapping.py``
  already handles. A 200 means the answer arrived.
* **The empty case is a 404 with ``content-length: 0`` and no body at all**,
  and it is *indistinguishable from a nonexistent organisasjonsnummer.*
  Both ``974760673`` (REGISTERENHETEN I BRØNNØYSUND — a real, live entity
  that ``tests/fixtures/brreg_974760673.json`` records from
  ``/enheter``) and ``936295592`` (ASP DC ASA, incorporated 2025-10-02, real
  and live) 404 here; so do ``999999999`` and ``123456785``, which are
  MOD11-valid and were never issued. This is precisely the trap that would
  have turned every unencumbered British company into a non-existent one, and
  it is *live* here rather than merely possible. D-041(h)'s principle
  therefore binds absolutely: **``/enheter/{orgnr}`` decides whether an entity
  exists; ``/regnskapsregisteret/regnskap/{orgnr}`` never does.**
  :func:`registry_mcp.registries.no.client.fetch_accounts` maps a 404 to a
  present block with ``documents: []`` and never to ``not_found``.

  Cross-checked, and the cross-check is exact: on a page of 100 ``AS``
  entities, ``sisteInnsendteAarsregnskap`` present on the ``/enheter``
  record ⟺ HTTP 200 here (93/93), and absent ⟺ HTTP 404 here (7/7), with
  the year always equal to ``tilDato``'s year. ``CompanyReport.
  last_annual_accounts_year`` is thus a free, already-fetched predictor of
  whether this call will find anything — but it is *not* a substitute for it
  and *not* a guard on it (see the 500 below, where it is present and the
  fetch still fails).

* **A third state exists and it is a deterministic HTTP 500.** Banks,
  insurers and many foundations return 500 — reproducibly, on three
  consecutive calls, with a Spring error body carrying a ``trace`` id
  (``tests/fixtures/brreg_regnskap_500.json``) — *while their ``/enheter``
  record says they filed*: 34 of 36 sampled entities under NACE 64.190,
  65.110 and 65.120 (APRILA BANK ASA ``916823525``, STOREBRAND
  LIVSFORSIKRING AS ``958995369``, DNB LIVSFORSIKRING AS ``914782007``,
  every sparebank tried) carry ``sisteInnsendteAarsregnskap: 2025`` and 500
  here. The reading that fits: these entities file under the sector-specific
  årsregnskapsforskrifter, whose statements the ``store``/``smaa``
  ``oppstillingsplan`` this dataset serves cannot represent. It is **not**
  transient, so ``client.py``'s retry-once-on-5xx spends a second request to
  learn nothing; that is accepted rather than special-cased, because
  ``_fetch`` is shared with ``lookup``/``search`` and a status-specific
  retry rule is a ``DECISIONS.md`` matter. Per D-042(j) a failed attachment
  never fails the lookup: this raises ``upstream_error`` and
  ``core/registry.py::lookup_with`` leaves the block absent with a note.

* **One filed period, never a history.** Every one of ~600 successful
  responses had **exactly one** element; ``research/07-product-improvements.md``
  line 50 independently records the dataset as *"key figures, latest year"*.
  The endpoint takes **no arguments at all** — ``?år=``/``?aar=``/``?year=``/
  ``?regnskapstype=``/``?size=``/``?historikk=`` are all accepted and all
  ignored (byte-identical bodies), ``/regnskap/{orgnr}/{year}`` 404s, and
  ``OPTIONS`` answers ``allow: GET,HEAD,OPTIONS``. So D-042(j)'s truncation
  rule bites in an unusual way: there is no ``total_count`` to carry and no
  page size to choose, but the *shape* of the answer is itself a truncation —
  a filing history of one — and :func:`map_regnskap` discloses that in
  ``notes`` on every non-empty block rather than letting a caller infer that
  a company filed once.

* **``regnskapsperiode`` is always present, and so are both ``fraDato`` and
  ``tilDato``** — 0 missing in ~600 payloads across eight legal forms. This
  closes the "presence and shape confirmed on two entities" caveat in
  D-023(d).

* **The variance D-023(d) called unverified is real, large, and easy to
  find.** ``tilDato`` is not always 31 December: ORACLE NORGE AS
  ``939319891`` → 2024-06-01/2025-05-31 (recorded as
  ``tests/fixtures/brreg_regnskap_939319891.json``), MICROSOFT NORGE AS
  ``957485030`` → 30 June, DELL AS ``861272702`` and AUTODESK NORWAY AS
  ``923414029`` → 31 January, MEDTRONIC NORGE AS ``975806529`` → 30 April,
  CISCO SYSTEMS NORWAY AS ``979322437`` → 31 July, THE WALT DISNEY COMPANY
  NORDIC AB NUF ``965930302`` → 30 September, HEWLETT-PACKARD NORGE AS
  ``918891919`` → 31 October, ADOBE SYSTEMS NORGE AS ``979953046`` →
  30 November. Five of those end between 1 January and 30 June, which is
  regnskapsloven § 8-3(1) second sentence's **1 February** branch — a
  *different rule*, not a shifted date (D-023(a)). Norwegian subsidiaries of
  foreign groups are where they cluster.

* **``fraDato`` is real data, not ``tilDato`` minus twelve months.** Nine of
  100 sampled ``AS`` entities filed a stub first period running from the
  incorporation date to 31 December (e.g. ``935845114`` → 2025-06-19/
  2025-12-31, recorded as ``tests/fixtures/brreg_regnskap_935845114.json``).
  This is the asymmetry with Sweden that makes ``FiledDocument.period_start``
  worth having: D-041(d) put the field on the model *because Norway would
  fill it*, and D-041(e) refused to derive a Swedish one by subtracting
  twelve months precisely because a first or final period may be short or
  long. Norway does not need the derivation — the register states it — and
  the stub periods are the live proof that deriving it would have been wrong
  about one company in eleven.

* **There is no filing date on this endpoint.** Not under any name: the full
  key set is closed (below) and contains none. ``journalnr`` is a string
  whose first four digits do track the year the filing was journalled
  (2026 for 2025 accounts, 32/32) — but that is an inference from the format
  of an opaque identifier, and it is *not* "period end + 1 year":
  ARBEIDS-STIFTELSEN ``930515752`` journalled its 2023 accounts as
  ``2025305951``, two years late, and CAK ``933673502`` its 2021 accounts as
  ``2022947594``. So ``journalnr`` is carried **verbatim** as
  ``document_id`` (D-026(a): carried, never constructed) and ``filed_at``
  stays ``None``. That in turn makes ``days_from_fee_point`` ``None`` by
  D-041(d)'s own rule, which is the right answer for a second reason: the
  Norwegian fee point is regnskapsloven § 8-3(1)'s **branch** (1 August, or
  1 February for a year ending 1 January–30 June), not "N months after the
  period end", and picking the branch's year for a non-December year end is
  exactly the duty D-009 forbids guessing. Nothing here computes a date.

* **The minimisation test, D-042(e), applied field by field — and it comes
  back clean.** The payload's key set is closed and identical across every
  successful response (~600, eight legal forms): ``id``, ``journalnr``,
  ``regnskapstype``, ``virksomhet.{organisasjonsnummer, organisasjonsform,
  morselskap}``, ``regnskapsperiode.{fraDato, tilDato}``, ``valuta``,
  ``avviklingsregnskap``, ``oppstillingsplan``, ``revisjon.
  {ikkeRevidertAarsregnskap, fravalgRevisjon}``, ``regnkapsprinsipper.
  {smaaForetak, regnskapsregler}``, and the three numeric trees
  ``egenkapitalGjeld``, ``eiendeler`` and ``resultatregnskapResultat``.
  Enumerating every **string-valued** path and its complete value domain
  across those payloads leaves exactly eight, and every one is a number, a
  code or a date: ``journalnr`` (a numeric string), ``oppstillingsplan``
  (only ``"store"``), ``regnkapsprinsipper.regnskapsregler`` (only
  ``"regnskapslovenAlminneligRegler"`` and, on IFRS filers,
  ``"forenkletAnvendelseIFRS"``), ``regnskapsperiode.fraDato`` /
  ``.tilDato``, ``regnskapstype`` (only ``"SELSKAP"``), ``valuta``
  (``"NOK"``/``"USD"``), ``virksomhet.organisasjonsform`` and
  ``virksomhet.organisasjonsnummer``. **No field in this payload can carry a
  natural person's name or any other particular of one.** In particular
  ``revisjon`` — the field whose *name* promises an auditor, and the one this
  task flagged in advance — carries two booleans and nothing else: whether
  the accounts were unaudited, and whether the company has opted out of audit
  (``fravalgRevisjon``). It names no auditor, no firm and no signatory, and
  ``virksomhet`` names no proprietor. D-042(f)'s bar is satisfied without a
  single redaction, and nothing here needs D-042(e)(3)'s treatment of
  ``persons_entitled``; this block ships **no** person-bearing field.

  The sole-trader question is settled by the register itself: **all 100
  sampled ``ENK`` entities returned 404**, which is what regnskapsloven's
  threshold-based regnskapsplikt predicts. No sole-trader payload exists to
  record, none was recorded, and ``833286602``/``833285602`` were never
  called (`tests/fixtures/brreg_833285602.json` is a pre-existing
  ``/enheter`` fixture and is untouched by this work).

Two shape choices flagged for the architect rather than made quietly, one of
which the architect has since answered:

* **The key figures were flagged here, unclaimed — D-043 answered it, and
  they are now carried.** Every successful payload holds ~20 usable numeric
  fields — turnover (``sumDriftsinntekter``), operating result, net
  financial items, ``aarsresultat``, total assets, current/fixed assets,
  equity, short- and long-term debt — plus ``valuta``, ``avviklingsregnskap``
  (a liquidation account), ``regnkapsprinsipper.smaaForetak`` and the two
  ``revisjon`` booleans. All are company facts, all pass minimisation, and
  none had a home in the shape D-041(d)/D-042(h) ruled for ``FiledDocument``
  — widening a shared attachment model is a ``DECISIONS.md`` question, not an
  implementer's judgement (D-042(g)'s anti-bend rule), and ``FiledDocument``
  is the one canonical model all three countries import, so a unilateral
  widening would have changed Britain's and Sweden's shape too. D-043
  answered it with a **second** block rather than a wider `FiledDocument`
  (D-043(b)): :class:`~registry_mcp.core.models.FinancialSummary`, reached by
  ``include=["financials"]`` — not ``include=["accounts"]``, which D-043(b)
  declines by name because Companies House already uses "accounts" for the
  filed document itself. See :func:`map_regnskap_financials` below, which
  reads this same payload a second way and shares this module's one fetch
  (D-043(h)).
* **``category`` carries ``regnskapstype``; ``type_code`` and
  ``description_code`` stay ``None``.** ``regnskapstype`` is the register's
  own classification *of the filing* — company accounts versus consolidated
  accounts — which is what D-042(h) asks ``category`` for, and it is relayed
  verbatim (only ``"SELSKAP"`` was ever observed, including on every
  ``morselskap: true`` parent tried: EQUINOR ASA, ORKLA ASA, Norsk Hydro ASA,
  YARA INTERNATIONAL ASA, AKER ASA, AKER BP ASA; ``"KONSERN"`` is implied by
  the vocabulary but was never seen, so nothing switches on it).
  ``oppstillingsplan`` (``"store"``) is deliberately **not** mapped to
  ``type_code``: it is a presentation-plan label, not a form code like
  ``"AA"`` or ``"CS01"``, and stretching it would put a wrong claim in a
  field description. Regnskapsregisteret publishes no form code and no
  description template, so both are honestly ``None`` — and the second of
  those is the field D-042(e)(1) exists to police, which Norway simply does
  not have.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from registry_mcp.core.models import (
    BalanceSheet,
    FiledDocument,
    FilingHistory,
    FinancialPeriod,
    FinancialSummary,
    IncomeStatement,
    SourceRef,
)

__all__ = [
    "ACCOUNTS_URL",
    "BalanceSheet",
    "FiledDocument",
    "FilingHistory",
    "FinancialPeriod",
    "FinancialSummary",
    "IncomeStatement",
    "map_regnskap",
    "map_regnskap_financials",
]


#: The open, keyless endpoint. A different path prefix on the same host as
#: ``client.BASE_URL`` (``/enhetsregisteret/api``), and a different dataset:
#: hence a different ``SourceRef`` (D-041(c)).
ACCOUNTS_URL = "https://data.brreg.no/regnskapsregisteret/regnskap/{orgnr}"

#: The human-readable Brønnøysundregistrene page for one entity, cited in the
#: "one period only" note. Verified live 2026-09-08 (``/regnskap`` on this
#: path redirects to the entity page itself).
_VIRKSOMHET_URL = "https://virksomhet.brreg.no/nb/oppslag/enheter/{orgnr}"

_SOURCE = "Regnskapsregisteret (Brønnøysundregistrene)"
_LICENSE = "NLOD 2.0"

_ANNUAL_ACCOUNTS = "annual_accounts"

_EMPTY_NOTE = (
    "Regnskapsregisteret's open dataset holds no filed annual accounts for this "
    "organisation. That is the register's own answer, not a failed lookup — but it does "
    "not by itself prove that none was ever due: this dataset covers the entities whose "
    "accounts it can present, and a newly filed set can take time to appear. Two "
    "populations are missing from it for reasons that are not about filing at all — "
    "sole proprietorships (ENK), which mostly have no regnskapsplikt, and banks and "
    "insurers, whose sector-specific accounts this dataset returns an error for rather "
    "than an empty answer."
)

_ONE_PERIOD_NOTE = (
    "Regnskapsregisteret's open dataset publishes only the most recently filed accounting "
    "period, so this is the latest filing rather than a filing history, and the endpoint "
    "takes no year argument. Earlier years are held by Brønnøysundregistrene and can be "
    "ordered from them; see {url}."
)

_PREVIEW_NOTE = (
    "Brønnøysundregistrene labels this dataset a preview, with no guarantees of quality "
    "of service."
)

_DEVIATING_YEAR_NOTE = (
    "This organisation's last filed accounts cover a period ending {period_end}, not "
    "31 December, so it has a deviating accounting year (avvikende regnskapsår). That "
    "selects a different filing rule, not a shifted date: regnskapsloven § 8-3(1) second "
    "sentence gives a financial year ending between 1 January and 30 June a 1 February "
    "deadline instead of the 1 August fee point the first sentence sets, and § 8-3(1)'s "
    "last sentence lets the Ministry postpone by up to one month by regulation, which no "
    "register publishes. This block reports the period the register published and "
    "computes no date from it."
)

_UNUSUAL_LENGTH_NOTE = (
    "The period runs from {period_start} to {period_end} — {days} days, so it is {direction} "
    "than an ordinary year. A first accounting period runs from the incorporation date, and "
    "regnskapsloven § 1-7 lets a first or final period be shortened or extended, so this is "
    "lawful and common. The register published both ends; neither was derived from the other."
)

#: Below/above these, a period is reported as shorter/longer than an ordinary
#: year. Wide enough that no 12-month period is ever called unusual whatever
#: day of the month it starts on: an ordinary year is 365 or 366 days.
_SHORT_PERIOD_DAYS = 330
_LONG_PERIOD_DAYS = 400


def _parse_date(raw: Any) -> date | None:
    """``YYYY-MM-DD``; anything else, or absent, is ``None``.

    Both dates on this endpoint were plain ``YYYY-MM-DD`` in every one of the
    ~600 payloads this module's recon read, and neither is named for a point
    in time (contrast Sweden's ``registreringstidpunkt``). Matches
    ``registries/no/mapping.py``'s own tolerance: parse, never raise.
    """
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _map_one_filing(item: Mapping[str, Any]) -> FiledDocument:
    period = item.get("regnskapsperiode") or {}
    journalnr = item.get("journalnr")

    return FiledDocument(
        kind=_ANNUAL_ACCOUNTS,
        period_end=_parse_date(period.get("tilDato")),
        period_start=_parse_date(period.get("fraDato")),
        # Not published by this register, under any name — see the module
        # docstring. `journalnr`'s leading four digits track the year the
        # filing was journalled, but reading a date out of an opaque handle
        # is a constructed fact (D-026(a)), and the register's own late
        # filings disprove any period-derived guess.
        filed_at=None,
        # `None` follows from `filed_at` being `None` (D-041(d)), and would
        # follow anyway: Norway's fee point is a statutory branch, not an
        # offset (D-009).
        days_from_fee_point=None,
        document_id=str(journalnr) if journalnr is not None else None,
        file_format=None,
        category=item.get("regnskapstype"),
        type_code=None,
        description_code=None,
    )


def _period_length_direction(period_start: date | None, period_end: date | None) -> tuple[int, str] | None:
    """``(days, "shorter"|"longer")`` when the register's own two dates do not
    span an ordinary year, else ``None``.

    Measured in days rather than months so that no 12-month period is ever
    called unusual on a month-length or leap-day technicality, whatever day of
    the month it starts on — the stub periods this exists to describe run a
    few weeks to a few months, and an extended one can run to eighteen.
    """
    if period_start is None or period_end is None:
        return None
    days = (period_end - period_start).days + 1
    if days < _SHORT_PERIOD_DAYS:
        return days, "shorter"
    if days > _LONG_PERIOD_DAYS:
        return days, "longer"
    return None


def map_regnskap(
    payload: Sequence[Mapping[str, Any]] | None,
    orgnr: str,
    *,
    cached: bool,
    fetched_at: datetime,
) -> FilingHistory:
    """Pure, synchronous, no I/O — mirrors ``registries/no/mapping.py``'s
    ``map_entity`` / ``map_search_result`` convention exactly, one level down,
    and ``registries/gb/charges.py::map_charges`` /
    ``registries/se/filings.py::map_dokumentlista`` across countries.

    Args:
        payload: The parsed JSON body of
            ``GET /regnskapsregisteret/regnskap/{orgnr}`` — a bare JSON array,
            with no envelope. ``None`` or ``[]`` for the empty case, which on
            this endpoint arrives as a bodyless 404 and is mapped by
            :func:`registry_mcp.registries.no.client.fetch_accounts` to a
            present, empty block, never to ``not_found``.
        orgnr: The normalised organisasjonsnummer (``rules.validate_orgnr``'s
            output), used only to build ``provenance.source_url`` and the
            note URLs — never re-validated here.
        cached: Whether this block is being served from the cache.
        fetched_at: The original fetch time, preserved across cache hits
            (``DECISIONS.md`` D-006).

    Returns:
        A :class:`FilingHistory`. ``documents == []`` means the register holds
        no filed annual accounts for this entity — a real answer, not an
        absence (D-041(c)).
    """
    items = list(payload or [])
    documents = [_map_one_filing(item) for item in items if isinstance(item, Mapping)]
    documents.sort(
        key=lambda d: (d.period_end or date.min, d.period_start or date.min), reverse=True
    )

    financial_year_end = documents[0].period_end if documents else None

    notes: list[str] = [_PREVIEW_NOTE]
    if not documents:
        notes.insert(0, _EMPTY_NOTE)
    else:
        notes.insert(0, _ONE_PERIOD_NOTE.format(url=_VIRKSOMHET_URL.format(orgnr=orgnr)))
        newest = documents[0]
        if financial_year_end is not None and (
            financial_year_end.month != 12 or financial_year_end.day != 31
        ):
            notes.insert(
                1, _DEVIATING_YEAR_NOTE.format(period_end=financial_year_end.isoformat())
            )
        length = _period_length_direction(newest.period_start, newest.period_end)
        if length is not None and newest.period_start and newest.period_end:
            days, direction = length
            notes.insert(
                1,
                _UNUSUAL_LENGTH_NOTE.format(
                    period_start=newest.period_start.isoformat(),
                    period_end=newest.period_end.isoformat(),
                    days=days,
                    direction=direction,
                ),
            )

    return FilingHistory(
        documents=documents,
        financial_year_end=financial_year_end,
        provenance=SourceRef(
            source=_SOURCE,
            source_url=ACCOUNTS_URL.format(orgnr=orgnr),
            license=_LICENSE,
            fetched_at=fetched_at,
            cached=cached,
        ),
        notes=notes,
    )


# ---------------------------------------------------------------------------
# `financials` — DECISIONS.md D-043: the same payload's ~20 numeric fields
# R-5d left on the wire, unclaimed (see the module docstring above). Maps
# onto the canonical ``core.models.FinancialSummary`` directly — the same
# "no local stand-in" pattern :func:`map_regnskap` uses for ``FilingHistory``
# after T40 — and reads the same parsed body, never a second fetch
# (D-043(h)).
# ---------------------------------------------------------------------------

_CURRENCY_MISSING_NOTE = (
    "One filed period could not be carried in this block because the register published "
    "no currency for it. A figure without its currency is not carried by this API "
    "(DECISIONS.md D-043(d))."
)

_COMPARABILITY_NOTE = (
    "These figures are denominated in this period's own currency and prepared under its "
    "own accounting framework — see `currency` and `accounting_framework` on the period — "
    "and are not comparable across companies or across borders without regard to both. "
    "Nothing here converts, restates or annualises a figure."
)

_RECONCILIATION_NOTE = (
    "This filing's total assets ({total_assets}) and total equity and liabilities "
    "({total_equity_and_liabilities}) differ by {gap} — the register's own figures, "
    "relayed exactly as filed; neither is edited, reconciled or dropped (DECISIONS.md "
    "D-043(e))."
)

_NON_NOK_NOTE = (
    "This filing is denominated in {currency}, not NOK — a caller comparing two Norwegian "
    "companies should not assume kroner."
)

_SMALL_ENTITY_NOTE = (
    "This filing was prepared under the reduced-disclosure regime for a small entity "
    "(regnskapsloven § 1-6): fewer figures exist, and those that do permit "
    "simplifications. This is not a distress signal."
)

_AUDIT_EXEMPT_NOTE = (
    "This company has resolved to opt out of audit (aksjeloven § 7-6): no independent "
    "auditor checked these figures."
)

_LIQUIDATION_BASIS_NOTE = (
    "This filing is a winding-up account (avviklingsregnskap, aksjeloven § 16-10): "
    "prepared on a realisation basis rather than a going concern, over a final period."
)

_UNAUDITED_FLAG_NOTE = (
    "The register set this filing's own 'not audited' flag to true. This project has not "
    "been able to verify what that flag means in practice — it was never observed set, "
    "even on filings by companies that had opted out of audit — so this is not read as an "
    "assertion about whether these accounts were audited."
)

#: D-043(c): `consolidated` is derived from `regnskapstype` by a committed
#: table of words this module has actually observed on the wire. `"KONSERN"`
#: (consolidated) is implied by the vocabulary but was never seen in 573 live
#: responses, including on every `morselskap: true` parent tried (EQUINOR
#: ASA, ORKLA ASA, Norsk Hydro ASA, YARA INTERNATIONAL ASA, AKER ASA, AKER BP
#: ASA — see the module docstring). Add it here, with a citation to the live
#: response that showed it, the day it is actually observed — never guessed
#: in advance (D-025(d)).
_CONSOLIDATED_BY_SCOPE: dict[str, bool] = {
    "SELSKAP": False,
}


def _as_bool(raw: Any) -> bool | None:
    """`True`/`False` only when the wire sent a JSON boolean; never a
    truthy/falsy coercion of a string or a number."""
    return raw if isinstance(raw, bool) else None


def _as_str(raw: Any) -> str | None:
    """A non-empty JSON string only; never coerced from another type."""
    return raw if isinstance(raw, str) and raw else None


def _num(obj: Any, *path: str) -> float | None:
    """Read a numeric leaf ``path`` deep inside ``obj``, tolerant of every way
    Regnskapsregisteret represents "no line here": a missing key, an explicit
    JSON ``null``, or — most commonly — a present-but-empty nested object such
    as ``"langsiktigGjeld": {}`` (D-043(f)). Never reads a zero from an
    absence: a JSON boolean is rejected even though ``bool`` is a subtype of
    ``int`` in Python, because this register never sends one where the wire
    promises a figure. Used for every one of the block's 19 numeric fields —
    never ``dict.get(k, 0)``.
    """
    current: Any = obj
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        return None
    return float(current)


def _map_income_statement(item: Mapping[str, Any]) -> IncomeStatement | None:
    """`None` when the register published no line in this statement at all
    for this filing; otherwise present with whichever lines it published."""
    result = item.get("resultatregnskapResultat")
    result = result if isinstance(result, Mapping) else {}

    statement = IncomeStatement(
        revenue=_num(result, "driftsresultat", "driftsinntekter", "sumDriftsinntekter"),
        operating_costs=_num(result, "driftsresultat", "driftskostnad", "sumDriftskostnad"),
        operating_result=_num(result, "driftsresultat", "driftsresultat"),
        financial_income=_num(result, "finansresultat", "finansinntekt", "sumFinansinntekter"),
        financial_costs=_num(result, "finansresultat", "finanskostnad", "sumFinanskostnad"),
        net_financial_items=_num(result, "finansresultat", "nettoFinans"),
        profit_before_tax=_num(result, "ordinaertResultatFoerSkattekostnad"),
        profit_for_period=_num(result, "aarsresultat"),
        total_comprehensive_income=_num(result, "totalresultat"),
    )
    if all(value is None for value in statement.model_dump().values()):
        return None
    return statement


def _map_balance_sheet(item: Mapping[str, Any]) -> BalanceSheet | None:
    """`None` when the register published no line in this statement at all
    for this filing; otherwise present with whichever lines it published."""
    sheet = BalanceSheet(
        fixed_assets=_num(item, "eiendeler", "anleggsmidler", "sumAnleggsmidler"),
        current_assets=_num(item, "eiendeler", "omloepsmidler", "sumOmloepsmidler"),
        total_assets=_num(item, "eiendeler", "sumEiendeler"),
        # `sumInnskuttEgenkaptial` is spelled that way by the register — not a
        # typo in this module.
        paid_in_equity=_num(
            item, "egenkapitalGjeld", "egenkapital", "innskuttEgenkapital", "sumInnskuttEgenkaptial"
        ),
        retained_equity=_num(
            item, "egenkapitalGjeld", "egenkapital", "opptjentEgenkapital", "sumOpptjentEgenkapital"
        ),
        equity=_num(item, "egenkapitalGjeld", "egenkapital", "sumEgenkapital"),
        non_current_liabilities=_num(
            item, "egenkapitalGjeld", "gjeldOversikt", "langsiktigGjeld", "sumLangsiktigGjeld"
        ),
        current_liabilities=_num(
            item, "egenkapitalGjeld", "gjeldOversikt", "kortsiktigGjeld", "sumKortsiktigGjeld"
        ),
        liabilities=_num(item, "egenkapitalGjeld", "gjeldOversikt", "sumGjeld"),
        total_equity_and_liabilities=_num(item, "egenkapitalGjeld", "sumEgenkapitalGjeld"),
    )
    if all(value is None for value in sheet.model_dump().values()):
        return None
    return sheet


def _map_one_period(item: Mapping[str, Any], currency: str) -> FinancialPeriod:
    period_data = item.get("regnskapsperiode")
    period_data = period_data if isinstance(period_data, Mapping) else {}
    journalnr = item.get("journalnr")
    scope = _as_str(item.get("regnskapstype"))
    principles = item.get("regnkapsprinsipper")
    principles = principles if isinstance(principles, Mapping) else {}
    audit = item.get("revisjon")
    audit = audit if isinstance(audit, Mapping) else {}

    return FinancialPeriod(
        period_start=_parse_date(period_data.get("fraDato")),
        period_end=_parse_date(period_data.get("tilDato")),
        currency=currency,
        accounting_framework=_as_str(principles.get("regnskapsregler")),
        scope=scope,
        # D-043(c): a committed table of observed words. Never `False` for a
        # word the table does not contain — that would be a guess (D-025(d)).
        consolidated=_CONSOLIDATED_BY_SCOPE.get(scope) if scope is not None else None,
        small_entity=_as_bool(principles.get("smaaForetak")),
        audit_exempt=_as_bool(audit.get("fravalgRevisjon")),
        unaudited=_as_bool(audit.get("ikkeRevidertAarsregnskap")),
        liquidation_basis=_as_bool(item.get("avviklingsregnskap")),
        # Same handle as the sibling `FiledDocument.document_id` for this
        # filing (D-026(a): carried, never constructed).
        document_id=str(journalnr) if journalnr is not None else None,
        income_statement=_map_income_statement(item),
        balance_sheet=_map_balance_sheet(item),
    )


def _period_notes(period: FinancialPeriod) -> list[str]:
    """The conditional notes A3 rules for the newest period, in the order
    D-043 lists them: reconciliation, non-NOK currency, small entity, audit
    exemption, liquidation basis, then the unverified `unaudited` flag.

    The reconciliation sentence is the *only* arithmetic this block performs
    (D-043(e)): naming a gap between two figures the register itself does not
    reconcile, never editing, reconciling or dropping either one.
    """
    notes: list[str] = []
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
    if period.currency != "NOK":
        notes.append(_NON_NOK_NOTE.format(currency=period.currency))
    if period.small_entity is True:
        notes.append(_SMALL_ENTITY_NOTE)
    if period.audit_exempt is True:
        notes.append(_AUDIT_EXEMPT_NOTE)
    if period.liquidation_basis is True:
        notes.append(_LIQUIDATION_BASIS_NOTE)
    if period.unaudited is True:
        notes.append(_UNAUDITED_FLAG_NOTE)
    return notes


def map_regnskap_financials(
    payload: Sequence[Mapping[str, Any]] | None,
    orgnr: str,
    *,
    cached: bool,
    fetched_at: datetime,
) -> FinancialSummary:
    """Pure, synchronous, no I/O — the same convention as :func:`map_regnskap`,
    reading the same payload and building the same five-field provenance
    (DECISIONS.md D-043(h)(2)): the two must be constructible from one fetch
    with an identical `SourceRef`, because for Norway they always come from
    one (D-043(h)) — ``registries/no/client.py::fetch_accounts`` /
    ``fetch_financials`` share a single in-flight fetch so that this is true
    under concurrency, not only in principle.

    Args:
        payload: The same parsed JSON body :func:`map_regnskap` reads — a bare
            JSON array, no envelope. ``None`` or ``[]`` for the empty case.
        orgnr: The normalised organisasjonsnummer, used only to build
            ``provenance.source_url`` and the note URL — never re-validated
            here.
        cached: Whether this block is being served from the cache.
        fetched_at: The original fetch time, preserved across cache hits
            (D-006).

    Returns:
        A :class:`~registry_mcp.core.models.FinancialSummary`. ``periods ==
        []`` means either that the register holds no filed annual accounts
        for this entity, or (see ``notes``) that the one filing it holds
        could not be carried because the register published no currency for
        it — either way a real, present answer, never an absence (D-041(c),
        D-043(h)).
    """
    items = [item for item in (payload or []) if isinstance(item, Mapping)]

    periods: list[FinancialPeriod] = []
    skipped_no_currency = False
    for item in items:
        currency = _as_str(item.get("valuta"))
        if currency is None:
            # D-043(d): `FinancialPeriod.currency` has no default, so a period
            # the register published with no currency is not constructed at
            # all — never guessed, never an empty string.
            skipped_no_currency = True
            continue
        periods.append(_map_one_period(item, currency))

    periods.sort(key=lambda p: p.period_end or date.min, reverse=True)

    notes: list[str] = []
    if periods:
        notes.append(_COMPARABILITY_NOTE)
        notes.append(_ONE_PERIOD_NOTE.format(url=_VIRKSOMHET_URL.format(orgnr=orgnr)))
        notes.append(_PREVIEW_NOTE)
    elif not items:
        notes.append(_EMPTY_NOTE)
    if skipped_no_currency:
        notes.append(_CURRENCY_MISSING_NOTE)
    if periods:
        notes.extend(_period_notes(periods[0]))

    return FinancialSummary(
        periods=periods,
        provenance=SourceRef(
            source=_SOURCE,
            source_url=ACCOUNTS_URL.format(orgnr=orgnr),
            license=_LICENSE,
            fetched_at=fetched_at,
            cached=cached,
        ),
        notes=notes,
    )
