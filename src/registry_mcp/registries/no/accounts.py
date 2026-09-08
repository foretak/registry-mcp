"""NO annual accounts — ``GET data.brreg.no/regnskapsregisteret/regnskap/{orgnr}``.

Built for **R-5d** (``DECISIONS.md`` D-042(i)), **behind the seam**, exactly
as ``registries/gb/charges.py`` was an hour earlier and
``registries/se/filings.py`` is in parallel: this module is deliberately
self-contained inside ``registries/no/`` and does not import
``core.models.SourceRef``, ``core.models.FiledDocument`` or
``core.models.FilingHistory``. ``SourceRef`` landed with R-5;
``FiledDocument`` / ``FilingHistory`` have **not** landed in ``core/models.py``
yet (``grep -n "FiledDocument" src/registry_mcp/core/models.py`` is empty as
this is written), and ``core/`` is another agent's footprint. **Nothing here
touches ``core/``, ``mcp/`` or ``api/``.**

The model shapes below are copied field-for-field from ``DECISIONS.md``
D-041(d) as widened by D-042(h) — the ruled shape of the future
``core.models.FiledDocument`` / ``core.models.FilingHistory`` — and are
deliberately identical to ``registries/se/filings.py``'s stand-ins, so that
the two converge on **one** shared model and wiring is a rename, not a
redesign:

* delete (or thinly re-export) :class:`FiledDocument`,
  :class:`FilingProvenance` and :class:`FilingHistory` from this module and
  from ``registries/se/filings.py``;
* ``core/models.py`` gains the real ``FiledDocument`` / ``FilingHistory``
  and ``CompanyReport.filings: FilingHistory | None = None``;
* ``BrregRegistry`` (``registries/no/__init__.py``) gains
  ``async def filings(self, id: str) -> FilingHistory`` — a thin call to
  :func:`registry_mcp.registries.no.client.fetch_accounts`, whose returned
  :class:`FilingHistory` is copied field-for-field onto the real model
  (``provenance`` becomes a real ``SourceRef`` from :class:`FilingProvenance`'s
  five identically-named fields);
* ``BrregRegistry.supported_includes`` gains ``"filings"``.

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

Two shape choices flagged for the architect rather than made quietly:

* **The key figures are not carried, and that is a decision.** Every
  successful payload holds ~20 usable numeric fields — turnover
  (``sumDriftsinntekter``), operating result, net financial items,
  ``aarsresultat``, total assets, current/fixed assets, equity, short- and
  long-term debt — plus ``valuta``, ``avviklingsregnskap`` (a liquidation
  account), ``regnkapsprinsipper.smaaForetak`` and the two ``revisjon``
  booleans. All are company facts, all pass minimisation, and none has a
  home in the shape D-041(d)/D-042(h) ruled. D-042(g)'s anti-bend rule
  reserves adding a field to a shared attachment model for an entry in
  ``DECISIONS.md``, not an implementer's judgement — and here the reason is
  not only procedural: with GB, SE and NO stand-ins converging on one
  ``FiledDocument``, a unilateral widening would break the "wiring is a
  rename" property all three modules were built for. There is also a
  substantive argument, and it is D-041(g)'s own: *"an XBRL package to parse,
  and a financial-statements feature wearing a filing-history costume"* —
  the reason Bolagsverket's zip was ruled out. Key figures are that feature.
  They are a strong candidate for a **separate** ``include=["accounts"]``
  block with its own entry; this module deliberately leaves them on the wire
  and unclaimed, exactly as D-023(d) left ``regnskapsperiode`` until D-042
  gave it somewhere to go.
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

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ACCOUNTS_URL",
    "FiledDocument",
    "FilingHistory",
    "FilingProvenance",
    "map_regnskap",
]


class _Base(BaseModel):
    """Local stand-in for ``core.models._Base`` — the same ``extra="forbid"``
    discipline (``DECISIONS.md`` D-004), kept out of ``core/`` per this
    task's footprint restriction rather than imported from there."""

    model_config = ConfigDict(extra="forbid", frozen=False)


class FilingProvenance(_Base):
    """Stand-in for ``core.models.SourceRef`` (D-026(c), landed with R-5) —
    the same five field names, unrenamed, so building the real
    ``FilingHistory.provenance`` from this object is a straight field copy.

    Its independence from ``CompanyReport``'s own provenance is the whole
    point of D-041(c): *one fetch, one ``SourceRef`` — not one organisation.*
    That bites hardest here, where both fetches go to the same host, the same
    publisher and the same open licence: ``/enhetsregisteret/api/enheter`` and
    ``/regnskapsregisteret/regnskap`` are still two round trips with two
    moments, two cache states and — as this module's docstring records — two
    genuinely different failure modes, since a bank's company record resolves
    while its accounts fetch returns a permanent 500.
    """

    source: str | None = Field(
        default=None,
        description='Who published this block, e.g. "Regnskapsregisteret (Brønnøysundregistrene)".',
    )
    source_url: str | None = Field(
        default=None, description="Where this block was fetched from."
    )
    license: str | None = Field(
        default=None,
        description=(
            "The licence this block is published under. `NLOD 2.0` — Brønnøysundregistrene "
            "publishes data.brreg.no under NLOD 2.0 (`NORBIZ_SPEC.md` §1), which is the same "
            "value the company record on the same host already carries; this endpoint states "
            "no separate licence of its own."
        ),
    )
    fetched_at: datetime | None = Field(
        default=None,
        description=(
            "When this block was fetched from Regnskapsregisteret — its own moment, not the "
            "company record's. `None` inside a present block means no request was made."
        ),
    )
    cached: bool = Field(
        default=False,
        description=(
            "Whether this block was served from this deployment's cache — its own cache "
            "state, which may differ from the company record's."
        ),
    )


class FiledDocument(_Base):
    """One filed annual account from Regnskapsregisteret's open dataset.

    Field-for-field the shape ``DECISIONS.md`` D-041(d) rules for the future
    ``core.models.FiledDocument``, plus the three fields D-042(h) adds — and
    deliberately identical to ``registries/se/filings.py``'s stand-in of the
    same name, so the two collapse into one model when they are wired.
    """

    kind: str | None = Field(
        default=None,
        description=(
            "The `Deadline.kind` slug this filing discharges, or `None` when it discharges "
            'none. Always "annual_accounts" for Norway: this dataset holds filed annual '
            "accounts (årsregnskap) and nothing else."
        ),
    )
    period_end: date | None = Field(
        default=None,
        description=(
            "The accounting period's last day, exactly as the register published it "
            "(`regnskapsperiode.tilDato`) — this filing's financial year end. Not always "
            "31 December: a Norwegian company may hold a deviating accounting year, and "
            "regnskapsloven § 8-3(1) second sentence gives a *different* filing rule "
            "(1 February) to a year ending between 1 January and 30 June."
        ),
    )
    period_start: date | None = Field(
        default=None,
        description=(
            "The accounting period's first day (`regnskapsperiode.fraDato`), verbatim. "
            "**Norway publishes this and Sweden does not** — the field exists on this model "
            "for exactly this register (D-041(d)). It is real data, not `period_end` minus "
            "twelve months: a company's first filed period runs from its incorporation date, "
            "so a stub period of a few months is common and a derived start would be wrong."
        ),
    )
    filed_at: date | None = Field(
        default=None,
        description=(
            "When the register recorded this filing. **Always `None` for Norway**: "
            "Regnskapsregisteret's open dataset publishes no filing date under any name. "
            "`journalnr` (relayed as `document_id`) begins with the year the filing was "
            "journalled, but reading a date out of an opaque identifier would be a "
            "constructed fact, not a published one — and it is not derivable from the "
            "period either, since accounts are sometimes journalled years late."
        ),
    )
    days_from_fee_point: int | None = Field(
        default=None,
        description=(
            "Signed days from the late-fee point to `filed_at`. **Always `None` for "
            "Norway**, for two independent reasons: `filed_at` is not published (so "
            "D-041(d)'s own `None` rule applies), and the Norwegian fee point is not "
            '"N months after the period end" but regnskapsloven § 8-3(1)\'s branch — '
            "1 August, or 1 February where the accounting year ended between 1 January "
            "and 30 June — whose year for a non-December period end is not settled by any "
            "source this project has read (D-009: never guess a duty)."
        ),
    )
    document_id: str | None = Field(
        default=None,
        description=(
            "The register's own handle for this filing (`journalnr`), relayed verbatim and "
            "never interpreted. **Not fetchable through this API**: this dataset returns "
            "key figures, not a document. It is the key a Brønnøysundregistrene support "
            "case can name. (The payload also carries an integer `id`, an internal row "
            "identifier, which is not relayed.)"
        ),
    )
    file_format: str | None = Field(
        default=None,
        description=(
            "What the register holds the document as. **Always `None` for Norway**: this "
            "endpoint offers no document at all, only parsed figures, so there is no format "
            "to name."
        ),
    )
    category: str | None = Field(
        default=None,
        description=(
            "The register's own category for this filing, verbatim (`regnskapstype`): "
            '"SELSKAP" for a company\'s own annual accounts. The vocabulary implies a '
            '"KONSERN" (consolidated) counterpart, which this dataset was never observed '
            "to return — including for parent companies. Nothing derived switches on it."
        ),
    )
    type_code: str | None = Field(
        default=None,
        description=(
            "The register's own form code for this filing, verbatim. **`None` for Norway**: "
            "Regnskapsregisteret publishes none. (`oppstillingsplan`, e.g. \"store\", is a "
            "presentation-plan label, not a form code, and is deliberately not mapped here.)"
        ),
    )
    description_code: str | None = Field(
        default=None,
        description=(
            "The register's own description-template key, verbatim and never resolved. "
            "**`None` for Norway**: Regnskapsregisteret publishes no description template, "
            "and therefore none of the resolved-template person data D-042(e)(1) exists to "
            "keep out of this model."
        ),
    )


class FilingHistory(_Base):
    """Stand-in for the future ``core.models.FilingHistory`` (D-041(d)) — the
    same field names, ``provenance`` typed to :class:`FilingProvenance` above
    rather than to ``core.models.SourceRef``, which this module deliberately
    does not depend on.

    Two-level nullability is the contract (D-041(c)) and belongs to whoever
    wires this up: **an absent block** on a report means "you did not ask, or
    the fetch failed" — never a present block with invented content — while
    **a present block with ``documents: []``** means "Regnskapsregisteret
    holds no filed annual account for this entity", which is a real answer
    about a counterparty and must never be rendered as an absence. For Norway
    that distinction is load-bearing rather than theoretical: the empty answer
    arrives as a bodyless 404 that looks exactly like a nonexistent
    identifier, and the failure answer arrives as a permanent 500 for banks
    and insurers whose company record says they filed.
    """

    documents: list[FiledDocument] = Field(
        default_factory=list,
        description=(
            "The filed annual accounts the register lists, sorted newest first: "
            "`period_end` descending, then `filed_at` descending where the register "
            "publishes one — Norway publishes none, so `period_start` is the tiebreak "
            "here. Norway's open dataset returns only the most recently filed period, so "
            "this list holds at most one entry — see `notes`. Empty means the register "
            "holds none, not that we could not look."
        ),
    )
    financial_year_end: date | None = Field(
        default=None,
        description=(
            "The `period_end` of this company's most recently filed annual accounts, "
            "carried verbatim — never a synthesised month-day. It is **evidence of** the "
            "company's financial year, not a statement of it: a company may change its "
            "accounting year, and the accounts on file may be several years old. `None` "
            "when the register holds no filed accounts."
        ),
    )
    provenance: FilingProvenance = Field(
        description="Where, when and under what licence this block was fetched."
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Plain-English caveats about this block.",
    )


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
        provenance=FilingProvenance(
            source=_SOURCE,
            source_url=ACCOUNTS_URL.format(orgnr=orgnr),
            license=_LICENSE,
            fetched_at=fetched_at,
            cached=cached,
        ),
        notes=notes,
    )
