"""SE filing history — ``POST /dokumentlista`` (Bolagsverket).

Built for **R-5b / T31 Part B**, **behind the seam** (``DECISIONS.md``
D-041, D-042(b), ``tasks/T31.md``): this module is deliberately
self-contained inside ``registries/se/``, built against no assumption about
what ``core/models.py`` carries. ``SourceRef``, ``FiledDocument`` and
``FilingHistory`` are R-5's ``include=[...]`` machinery, owned and being
edited in parallel by other agents, per this task's explicit footprint.
**Nothing here touches ``core/``, and nothing here depends on its shape** —
the only ``core`` import is :func:`core.rules.common.add_months`, a pure
date helper ``registries/se/rules.py`` already draws from the same module.

This mirrors ``registries/gb/charges.py`` exactly, one country over: local
model stand-ins whose field names are the ruled ones, plus a pure mapper,
wired up by a follow-up task. Wiring is then a rename, not a redesign:

* delete (or thinly re-export) :class:`FiledDocument`,
  :class:`FilingProvenance` and :class:`FilingHistory` from this module;
* ``core/models.py`` gains the real ``FiledDocument`` / ``FilingHistory``
  (D-041(d) as amended by D-042(h)) and
  ``CompanyReport.filings: FilingHistory | None = None``;
* ``BolagsverketRegistry`` (``registries/se/__init__.py``) gains
  ``async def filings(self, id: str) -> FilingHistory`` — call
  :func:`registry_mcp.registries.se.client.fetch_filings` and copy the
  returned :class:`FilingHistory`'s fields onto the real model
  (``provenance`` becomes a real ``SourceRef`` built from
  :class:`FilingProvenance`'s five identically-named fields);
* ``BolagsverketRegistry.supported_includes`` gains ``"filings"``.

**The finding this module exists for.** ``SWEDEN_SPEC.md`` §5.4 computes
both Swedish deadlines from an *assumed* 31 December financial year end, and
note N9 discloses the assumption, because the spec concluded Bolagsverket's
free dataset never publishes the financial year. It does:
``rapporteringsperiodTom`` is the end of the reporting period of each filed
annual report — the company's own financial year end — and a *brutet
räkenskapsår* is lawful, so a company with an April year end is today told
30 June and 31 July when its own dates are four months later. **This module
does not change how any deadline is computed** (that is D-041(e)'s ladder
and (f)'s three-state N9, a follow-on task); it puts the published fact
where that task can read it.

Recon against the Bolagsverket **TEST** environment, 2026-09-08, credentials
from ``~/secrets/registry-mcp/bolagsverket-test.txt`` and never written to a
file, log, fixture or test. The load-bearing findings, so a later reader
does not re-derive them:

* **``5561890038`` is confirmed as the ``/dokumentlista`` scenario company**
  — ``SWEDEN_SPEC.md`` §17's table had two other numbers backwards until
  2026-09-07, so this one was re-verified rather than trusted. It returns
  HTTP 200 with **three** annual reports (``tests/fixtures/
  bv_dokumentlista.json``), and the single item ``tasks/T26-recon.md``
  line ~100 records from the test workbook is present in it byte-for-byte.
* **The two endpoints have *disjoint* test allowlists.** ``5561890038``
  answers ``/dokumentlista`` with a 200 and ``/organisationer`` with a
  **400**; the eight companies with live ``/organisationer`` recordings
  (``tests/fixtures/README.md``) all answer ``/dokumentlista`` with a
  **400**. So the test environment cannot produce a lookup and a filing
  history for the same entity, and it cannot produce an empty document list
  at all — see :func:`map_dokumentlista` and the two
  ``_SYNTHETIC_COMBINATION`` fixtures.
* **D-041(h)'s "no ``dataproducent``/``fel`` wrapper" is confirmed on the
  wire.** The 200 body is exactly ``{"dokument": [ ... ]}`` — a plain array
  of plain objects. ``SWEDEN_SPEC.md`` §1.6's "every field is a wrapper,
  therefore HTTP 200 ≠ data arrived" is an ``/organisationer`` rule and must
  not be pointed at this response. Errors are RFC 7807
  (``type``/``instance``/``status``/``title``/``detail``/``requestId``/
  ``timestamp``), with ``instance: "client.error"`` and a **null**
  ``timestamp`` live, where the OpenAPI's own example carries a real one.
* **``filformat`` is ``"application/zip"``** on every observed document — a
  MIME type despite the field name, and the ``dokumentId`` carries a
  ``_paket`` suffix. Both are relayed verbatim and never interpreted; the
  zip itself is out of scope (D-041(g)).
* **``rapporteringsperiodTom`` was never absent and never a datetime** on
  the three observed documents: a plain ``YYYY-MM-DD``, as the OpenAPI's
  ``format: date`` declares. So is ``registreringstidpunkt``, despite the
  ``-tidpunkt`` ("point in time") in its name — which is exactly why
  :func:`_parse_date` below is the tolerant ``YYYY-MM-DD[T...]`` parser
  ``registries/se/mapping.py`` uses rather than a strict one: three
  documents on one company is not a sample that licenses a strict parser,
  and Bolagsverket has already shipped a datetime where this project's own
  notes expected a date (``bv_ab_avregistrerad.json``).
* **Never code to the 400 ``detail`` string** (D-041(h)) — and the reason is
  sharper than that entry had it. The OpenAPI's shared
  ``ApiError-felbegaran`` example, *"Identitetsbeteckning har ogiltig
  kontrollsiffra."*, is **not** a documentation invention: ``/dokumentlista``
  returns that exact string for a bad check digit (``5560000000``). What is
  a documentation bug is only that the same example is attached to
  ``GET /dokument/{dokumentId}``, whose sole input is a document id. A
  second, undocumented ``detail`` exists as well — *"Ogiltig
  identitetsbeteckning i begäran. Se testdokumentation för giltiga
  identitetsbeteckningar."* — for a well-formed identifier that is not on
  the test environment's allowlist (``tests/fixtures/
  bv_dokumentlista_400.json``). Two strings, one status, and only the status
  is behaviour.
* **No rate-limit headers.** The 200 carries ``x-request-id``,
  ``x-response-id``, ``x-timestamp`` and cache/security headers, and no
  ``X-RateLimit-*`` of any kind; the OpenAPI's
  ``x-throttling-tier: "Unlimited"`` is a WSO2 gateway artefact and does not
  repeal the published 60/min (``SWEDEN_SPEC.md`` §1.5). This call spends a
  token-bucket token like any other.

Three shape choices flagged for the architect rather than made quietly:

* **The three D-042(h) fields are present and are ``None`` for Sweden.**
  ``tasks/T31.md`` predates D-042 and says D-041(d)'s shape "is not to be
  widened"; D-042(h) then widened ``FiledDocument`` by ``category``,
  ``type_code`` and ``description_code`` **by name**, ruling that Britain's
  superset defines the model before Sweden fills it. Following the later,
  explicit ruling is what makes wiring a rename; all three are honestly
  ``None`` here, because ``/dokumentlista`` publishes no category, form code
  or description key. If the architect wants strictly D-041(d), it is a
  three-line deletion.
* **``days_from_fee_point`` uses the same-day-of-month reading of "sju
  månader".** For the only year end this module can observe, 31 December,
  every reading agrees: 31 July, and D-041(g)'s own worked example ("filed
  2023-06-27 … 34 days before the late-fee point") reproduces exactly. For a
  **non-December** year end the ambiguity D-041(e) leaves open as a
  ``VERIFY`` bites here too — is seven months from 30 June the 30th of
  January (same day of month, :func:`core.rules.common.add_months`) or the
  end of the seventh month, 31 January? A Swedish räkenskapsår ends on the
  last day of a month, so the two readings agree for every month end except
  30 June (30 vs 31 January) and 28/29 February (28/29 vs 30 September) —
  a one- or two-day difference, and only for a broken financial year. The
  measurement is accurate to within that until the ``VERIFY`` is closed, and
  :func:`map_dokumentlista` says so in a ``notes`` sentence rather than
  leaving it to inference (D-009, D-011). **Nothing this module computes for
  a 31 December company differs under any reading.**
* **``kind`` is ``"annual_accounts"`` on every document.**
  ``/dokumentlista``'s own summary is *"Retrieve a list of available annual
  reports"*, so the endpoint is single-purpose; the field is a slug rather
  than an enum so a register with more document types fits without a
  reshape (D-042(h)).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from registry_mcp.core.rules.common import add_months

__all__ = [
    "FEE_POINT_MONTHS",
    "FiledDocument",
    "FilingHistory",
    "FilingProvenance",
    "map_dokumentlista",
]


class _Base(BaseModel):
    """Local stand-in for ``core.models._Base`` — the same ``extra="forbid"``
    discipline (``DECISIONS.md`` D-004), kept out of ``core/`` per this
    task's footprint restriction rather than imported from there."""

    model_config = ConfigDict(extra="forbid", frozen=False)


class FilingProvenance(_Base):
    """Stand-in for the future ``core.models.SourceRef`` (D-026(c)) — the
    same five field names, unrenamed, so that building the real
    ``FilingHistory.provenance`` from this object is a straight field copy.

    Its independence from ``CompanyReport``'s own provenance is the whole
    point of D-041(c): *one fetch, one ``SourceRef`` — not one organisation.*
    Two round trips have two moments, two failure modes and two cache
    states, so this block's ``fetched_at`` and ``cached`` are its own and
    may disagree with the record's.
    """

    source: str | None = Field(
        default=None,
        description='Who published this block, e.g. "Bolagsverket (bolagsverket.se)".',
    )
    source_url: str | None = Field(
        default=None, description="Where this block was fetched from."
    )
    license: str | None = Field(
        default=None, description="The licence this block is published under."
    )
    fetched_at: datetime | None = Field(
        default=None,
        description=(
            "When this block was fetched from Bolagsverket — its own moment, not the "
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
    """One filed annual report from ``POST /dokumentlista``. Field-for-field
    the shape ``DECISIONS.md`` D-041(d) rules for the future
    ``core.models.FiledDocument``, plus the three fields D-042(h) adds to it
    (all ``None`` for Sweden — see this module's docstring)."""

    kind: str | None = Field(
        default=None,
        description=(
            "The `Deadline.kind` slug this filing discharges, or `None` when it discharges "
            'none. Always "annual_accounts" for Sweden: `/dokumentlista` returns filed '
            "annual reports and nothing else."
        ),
    )
    period_end: date | None = Field(
        default=None,
        description=(
            "The reporting period's last day, exactly as the register published it "
            "(`rapporteringsperiodTom`) — this filing's financial year end."
        ),
    )
    period_start: date | None = Field(
        default=None,
        description=(
            "The reporting period's first day. **Always `None` for Sweden**: Bolagsverket "
            "publishes no `...From` counterpart, and deriving one by subtracting twelve "
            "months would assert a period length the register never stated "
            "(bokföringslagen 3 kap. 3 § permits an 18-month first or final period). The "
            "field exists because Norway's Regnskapsregisteret publishes "
            "`regnskapsperiode: {fraDato, tilDato}` and will fill it."
        ),
    )
    filed_at: date | None = Field(
        default=None,
        description=(
            "When the register recorded this filing (`registreringstidpunkt`), verbatim. "
            "Named for a point in time, but published as a plain date."
        ),
    )
    days_from_fee_point: int | None = Field(
        default=None,
        description=(
            "Signed days from the late-fee point to `filed_at`: negative means filed "
            "before it, positive means after. The datum is **seven months after "
            "`period_end`**, where årsredovisningslagen 8 kap. 6 § starts a "
            "förseningsavgift of 7 500 kr (15 000 kr for a public company). It is **not "
            "this company's own filing deadline**: ÅRL 8 kap. 3 § requires filing within "
            "one month of the general meeting that adopts the accounts, and that meeting "
            "date is not published, so a company's real deadline may be much earlier. Nor "
            "can the nine-month variant of 8 kap. 6 § be excluded — it applies to "
            "companies this dataset does not identify. A measurement against a named "
            "datum, never a verdict: there is deliberately no `filed_late` boolean. "
            "`None` when `period_end` or `filed_at` is missing."
        ),
    )
    document_id: str | None = Field(
        default=None,
        description=(
            "The register's own opaque handle for this document (`dokumentId`), relayed "
            "verbatim and never interpreted. **Not fetchable through this API** — "
            "Bolagsverket's `GET /dokument/{dokumentId}` returns a zip, which is out of "
            "scope; this is the only key a Bolagsverket support case can name."
        ),
    )
    file_format: str | None = Field(
        default=None,
        description=(
            'What Bolagsverket holds the document as (`filformat`), verbatim: '
            '"application/zip" on every document observed — a MIME type despite the '
            "field name."
        ),
    )
    category: str | None = Field(
        default=None,
        description=(
            "The register's own category for this filing, verbatim. **`None` for "
            "Sweden**: `/dokumentlista` publishes no category, because it returns annual "
            "reports and nothing else."
        ),
    )
    type_code: str | None = Field(
        default=None,
        description=(
            "The register's own form code for this filing, verbatim. **`None` for "
            "Sweden**: Bolagsverket publishes none on this endpoint."
        ),
    )
    description_code: str | None = Field(
        default=None,
        description=(
            "The register's own description-template key, verbatim and never resolved. "
            "**`None` for Sweden**: Bolagsverket publishes none on this endpoint."
        ),
    )


class FilingHistory(_Base):
    """Stand-in for the future ``core.models.FilingHistory`` (D-041(d)) — the
    same field names, ``provenance`` typed to :class:`FilingProvenance`
    above rather than to ``core.models.SourceRef``, which this module
    deliberately does not depend on.

    Two-level nullability is the contract (D-041(c)) and belongs to whoever
    wires this up: **an absent block** on a report means "you did not ask, or
    the fetch failed" — never a present block with invented content — while
    **a present block with ``documents: []``** means "Bolagsverket holds no
    filed annual report for this entity", which is a real and useful answer
    about a counterparty and must never be rendered as an absence.
    """

    documents: list[FiledDocument] = Field(
        default_factory=list,
        description=(
            "Every filed annual report the register lists, sorted newest first: "
            "`period_end` descending, then `filed_at` descending. Empty means the "
            "register holds none — not that we could not look."
        ),
    )
    financial_year_end: date | None = Field(
        default=None,
        description=(
            "The `period_end` of this company's most recent filed annual report, carried "
            "verbatim — never a synthesised month-day. It is **evidence of** the "
            "company's financial year, not a statement of it: a company may relay its "
            "räkenskapsår under bokföringslagen 3 kap., and only the period *end* is "
            "published, so a shortened or extended period is invisible here. `None` when "
            "no filed report carries a reporting period."
        ),
    )
    provenance: FilingProvenance = Field(
        description="Where, when and under what licence this block was fetched."
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Plain-English caveats about this block.",
    )


#: Årsredovisningslagen 8 kap. 6 §: the förseningsavgift starts when the
#: documents have not arrived "inom sju månader från räkenskapsårets utgång".
#: The datum `days_from_fee_point` is measured against — never a deadline.
FEE_POINT_MONTHS = 7

_SOURCE_NAME = "Bolagsverket (bolagsverket.se)"
_SOURCE_URL = "https://gw.api.bolagsverket.se/vardefulla-datamangder/v1"
_LICENSE = (
    "Free re-use (Bolagsverket/SCB high-value datasets, EU Open Data Directive) — the "
    "publisher names no licence"
)

_ANNUAL_ACCOUNTS = "annual_accounts"

_EMPTY_NOTE = (
    "Bolagsverket's document list holds no filed annual report for this organisation. "
    "That is the register's own answer, not a failed lookup — but it is not proof that "
    "none was ever due: the list covers the documents Bolagsverket publishes through "
    "this dataset, and a newly filed report can take time to appear."
)

_BROKEN_YEAR_NOTE = (
    "This organisation's last filed annual report covers a period ending on a day other "
    "than 31 December, so it has a brutet räkenskapsår — lawful under bokföringslagen "
    "3 kap. Its own filing dates move by the same number of months as its year end, so "
    "they are not the 30 June and 31 July a calendar year would give. "
    "`days_from_fee_point` is measured seven months after the period end taking the same "
    "day of the month; årsredovisningslagen 8 kap. 6 §'s \"inom sju månader\" does not "
    "settle whether the seventh month's last day is meant instead, which would move the "
    "datum by one or two days for a period ending 30 June or in February. This module "
    "does not guess: the figure is a measurement against a named datum, not a deadline."
)

#: The same tolerant parser ``registries/se/mapping.py::_parse_date`` uses
#: (`SWEDEN_SPEC.md` §2.5): accept ``YYYY-MM-DD`` and any ``YYYY-MM-DD``
#: followed by ``T…``, taking the date part. Both dates on this endpoint were
#: plain dates in every observed payload and are declared ``format: date`` in
#: the OpenAPI — but three documents on one company does not license a strict
#: parser, and ``registreringstidpunkt`` is named for a point in time.
_DATE_PREFIX_RE = re.compile(r"\A(\d{4}-\d{2}-\d{2})(?:T.*)?\Z")


def _parse_date(raw: Any) -> date | None:
    """``YYYY-MM-DD`` or ``YYYY-MM-DDT…``; anything else is ``None``, never a
    raised exception."""
    if not isinstance(raw, str):
        return None
    match = _DATE_PREFIX_RE.match(raw)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def fee_point(period_end: date) -> date:
    """The late-fee point for a period ending ``period_end``: seven months
    later, årsredovisningslagen 8 kap. 6 §.

    Uses :func:`core.rules.common.add_months`, i.e. the same day of the
    month, clamped to the target month's length. For a 31 December period
    end — the only one this module can observe live, and the one every
    shipped Swedish deadline assumes — that is 31 July, which reproduces
    D-041(g)'s own worked example exactly. See the module docstring for the
    ±1 day this reading can cost a broken financial year, and D-041(e) for
    the ``VERIFY`` that closes it.
    """
    return add_months(period_end, FEE_POINT_MONTHS)


def _map_one_document(item: Mapping[str, Any]) -> FiledDocument:
    period_end = _parse_date(item.get("rapporteringsperiodTom"))
    filed_at = _parse_date(item.get("registreringstidpunkt"))
    days = (filed_at - fee_point(period_end)).days if period_end and filed_at else None
    document_id = item.get("dokumentId")
    file_format = item.get("filformat")

    return FiledDocument(
        kind=_ANNUAL_ACCOUNTS,
        period_end=period_end,
        # D-041(d)/(e): Bolagsverket publishes no `...From`, and subtracting
        # twelve months would assert a period length it never stated.
        period_start=None,
        filed_at=filed_at,
        days_from_fee_point=days,
        document_id=str(document_id) if document_id is not None else None,
        file_format=str(file_format) if file_format is not None else None,
        # D-042(h)'s three: Britain fills them, Bolagsverket publishes none.
        category=None,
        type_code=None,
        description_code=None,
    )


def map_dokumentlista(
    payload: Mapping[str, Any],
    *,
    cached: bool,
    fetched_at: datetime,
) -> FilingHistory:
    """Pure, synchronous, no I/O — mirrors ``registries/se/mapping.py``'s
    ``map_entity`` convention, one level down.

    ``DokumentlistaSvar`` is ``{"dokument": [ ... ]}`` and ``dokument`` is
    **not** in the schema's ``required`` list, so an absent key and an empty
    array mean the same thing and both produce a present block with
    ``documents: []`` (D-041(h)). There is no ``dataproducent``/``fel``
    wrapper on this endpoint — ``SWEDEN_SPEC.md`` §1.6's wrapper rule is an
    ``/organisationer`` rule and pointing this module's helpers at it would
    find nothing and mean nothing. **An empty list is never ``not_found``**:
    ``/organisationer`` alone decides whether an entity exists.

    Args:
        payload: The parsed JSON body of ``POST /dokumentlista``. Any
            top-level key this function does not read is ignored, so the
            ``_SYNTHETIC_COMBINATION`` header on an assembled fixture costs
            nothing (``tests/fixtures/README.md``).
        cached: Whether this block is being served from the cache — this
            block's own cache state, not the company record's (D-041(c)).
        fetched_at: The original fetch time, preserved across cache hits
            (D-006) — again this block's own, not the record's.
    """
    raw = payload.get("dokument")
    items = raw if isinstance(raw, list) else []
    documents = [_map_one_document(item) for item in items if isinstance(item, Mapping)]
    # D-041(g): newest first, `period_end` descending then `filed_at`
    # descending. A document with no `period_end` sorts last and can never
    # become `financial_year_end` below.
    documents.sort(key=lambda d: (d.period_end or date.min, d.filed_at or date.min), reverse=True)

    financial_year_end = documents[0].period_end if documents else None

    notes: list[str] = []
    if not documents:
        notes.append(_EMPTY_NOTE)
    elif financial_year_end is not None and (
        financial_year_end.month,
        financial_year_end.day,
    ) != (12, 31):
        notes.append(_BROKEN_YEAR_NOTE)

    return FilingHistory(
        documents=documents,
        financial_year_end=financial_year_end,
        provenance=FilingProvenance(
            source=_SOURCE_NAME,
            source_url=_SOURCE_URL,
            license=_LICENSE,
            fetched_at=fetched_at,
            cached=cached,
        ),
        notes=notes,
    )
