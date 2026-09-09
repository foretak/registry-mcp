"""SE filing history — ``POST /dokumentlista`` (Bolagsverket).

**R-5b / T31 Part B** (``DECISIONS.md`` D-041, D-042). This module maps the
wire straight onto the canonical :class:`~registry_mcp.core.models.FiledDocument`
/ :class:`~registry_mcp.core.models.FilingHistory` / :class:`~registry_mcp.core.models.SourceRef`
(D-041(d), as widened by D-042(h)) — the same shapes
``registries/gb/filing_history.py`` and ``registries/no/accounts.py`` build,
because all three registers converged on one shape independently (D-044(a)).
There is no local stand-in and nothing to convert: :func:`map_dokumentlista`
constructs the canonical classes directly, and
``BolagsverketRegistry.filings`` (``registries/se/__init__.py``) returns
:func:`registry_mcp.registries.se.client.fetch_filings`'s result unchanged.
The only other ``core`` import is :func:`core.rules.common.add_months`, a
pure date helper ``registries/se/rules.py`` already draws from the same
module.

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
  superset defines the model before Sweden fills it (now the canonical
  model in ``core/models.py``, which this module imports rather than
  re-declares). All three are honestly ``None`` here, because
  ``/dokumentlista`` publishes no category, form code or description key.
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

from registry_mcp.core.models import FiledDocument, FilingHistory, SourceRef
from registry_mcp.core.rules.common import add_months

__all__ = [
    "FEE_POINT_MONTHS",
    "FiledDocument",
    "FilingHistory",
    "map_dokumentlista",
]


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

#: D-044(b): one include name, `filings`, covers three differently-scoped
#: answers, and the scope difference must be disclosed in the block's own
#: `notes` **on every call** — the promise `mcp/server.py` and
#: `core/models.py`'s `FilingHistory` docstring publish. Unconditional and
#: first, exactly like Norway's `_ONE_PERIOD_NOTE` (the pattern this copies).
#:
#: **Rewritten by T55 §E**, now that `tasks/T52-recon.md` has read
#: Bolagsverket's own documentation of the channel rather than only the
#: `/dokumentlista` response shape: this list is not "we don't know the
#: channel's population", it is a stated one. The pending 2027 digital-filing
#: mandate is a bill, not a law (D-047(f)), and is deliberately not mentioned
#: here — silence rather than a guess about whether or when it passes.
_SCOPE_NOTE = (
    "Bolagsverket's own API documentation describes this operation as retrieving "
    "'available annual reports' for the organisation — filed annual reports only, not a "
    "general filing history; other filings this organisation has made — board changes, "
    "articles, capital — are not listed here, and their absence here means nothing. This "
    "list is digitally submitted aktiebolag annual reports prepared under K2 or K3, from "
    "2020 onwards: Bolagsverket's digital-submission channel does not accept a "
    "handelsbolag, an ekonomisk förening, a bostadsrättsförening, a financial company, an "
    "insurer or an IFRS preparer at all, and a paper filing or an earlier year is outside "
    "what this dataset can ever show."
)

_EMPTY_NOTE = (
    "Bolagsverket's document list holds no filed annual report for this organisation. "
    "That is the register's own answer, not a failed lookup — but it is not proof that "
    "none was ever due: the list covers digitally submitted aktiebolag annual reports "
    "under K2 or K3 from 2020 onwards (see the scope note above), and a newly filed "
    "report can take time to appear. Observed live: Telefonaktiebolaget LM Ericsson "
    "(organisationsnummer 5560160680) — Sweden's largest listed company — returns this "
    "same empty answer, against six listed annual reports for organisationsnummer "
    "5561890038. The reason is not that Ericsson files on paper: it reports under IFRS, "
    "which this digital channel does not accept at all, so an IFRS preparer has no "
    "digitally filed annual report here regardless of what it files with Bolagsverket by "
    "any other route."
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

    # D-044(b): the scope note is first and unconditional — empty or not,
    # calendar year or not — because it is what tells a caller which subset
    # of "this company's filings" the block below actually is.
    notes: list[str] = [_SCOPE_NOTE]
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
        provenance=SourceRef(
            source=_SOURCE_NAME,
            source_url=_SOURCE_URL,
            license=_LICENSE,
            fetched_at=fetched_at,
            cached=cached,
        ),
        notes=notes,
    )
