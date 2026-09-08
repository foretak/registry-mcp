"""GB filing history — ``GET /company/{n}/filing-history`` (Companies House).

Built for **R-5c / T37**, **behind the seam** (``DECISIONS.md`` D-042,
``tasks/T37.md``): this module is deliberately self-contained inside
``registries/gb/``, built against no assumption that ``core/models.py``
carries ``SourceRef``, ``FiledDocument`` or ``FilingHistory`` — those are
R-5's ``include=[...]`` machinery, owned and edited in parallel by other
agents, per this task's explicit footprint. It mirrors
``registries/gb/charges.py`` and ``registries/se/filings.py`` exactly: local
model stand-ins whose field names are the ruled ones, plus a pure mapper,
wired up by a follow-up task. Wiring is then a rename, not a redesign:

* delete (or thinly re-export) :class:`FiledDocument`,
  :class:`FilingProvenance` and :class:`FilingHistory` from this module;
* ``core/models.py`` gains the real ``FiledDocument`` / ``FilingHistory``
  (D-041(d) as amended by D-042(h)) and
  ``CompanyReport.filings: FilingHistory | None = None``;
* ``CompaniesHouseRegistry`` (``registries/gb/__init__.py``) gains
  ``async def filings(self, id: str) -> FilingHistory`` — validate the CRN
  via ``rules.validate_crn`` (as every other method there already does),
  call :func:`registry_mcp.registries.gb.client.fetch_filings`, and copy the
  returned :class:`FilingHistory`'s fields onto the real model
  (``provenance`` becomes a real ``SourceRef`` built from
  :class:`FilingProvenance`'s five identically-named fields);
* ``CompaniesHouseRegistry.supported_includes`` gains ``"filings"``.

**The finding this module exists for, and the reason it relays a slug where
a caller would expect a sentence.** ``items[].description_values``
interpolates the register's description templates, and 97 of those templates
interpolate ``{officer_name}`` while 26 interpolate ``{psc_name}``. Relayed
whole, this endpoint is *an officers feed wearing a filing-history costume* —
appointments, terminations and names — which is exactly what D-028 bars.
D-042(e)(1) rules the disposition and this module implements it without
revisiting it: **``items[].description`` is relayed verbatim as
``description_code``, and ``description_values`` is read through an
allow-list of exactly one key, ``made_up_date``.** The template key says
*what happened*; only the values say *who*. A key is added to that allow-list
by a new entry in ``DECISIONS.md``, never by an implementer — so
``grep -n "description_values" src/registry_mcp/registries/gb/`` must keep
showing exactly one key, and :data:`DESCRIPTION_VALUES_ALLOW_LIST` is the
one place it appears.

Recon findings behind every choice below — live calls against
``https://api.company-information.service.gov.uk``, 2026-09-08, credential
read from the operator's secrets file at call time and never written to a
file, a fixture, a log or a commit. **1876 items across nine companies**
were enumerated; the load-bearing findings, so a later reader does not have
to re-derive them:

* **Every one of the 24 distinct ``description_values`` keys observed live,
  with the number of items carrying each** (n=1876) — reported so the
  allow-list is checked against the wire and not against the 97/26 figure
  from the research::

      description 585   officer_name 445   date 276   capital 272
      appointment_date 193   made_up_date 182   termination_date 140
      change_date 110   charge_number 101   charge_creation_date 71
      new_address 14   psc_name 13   old_address 12   notification_date 6
      cessation_date 5   withdrawal_date 3   branch_number 3
      new_date 2   representative_details 2   form_type 1
      original_description 1   change_type 1   change_details 1
      change_name 1

  Three of those are worse than the research predicted, and none is a reason
  to widen the allow-list. **``description`` (585 items, the single most
  common key of all) is the ``legacy`` free-prose slot**, and it is
  person-bearing in exactly the way D-042(e)(1) feared: among the 512
  ``legacy`` items recorded, four read ``"Director appointed mr <full
  name>"`` outright, alongside 96 × ``"New member appointed"``, 48 ×
  ``"New director appointed"``, 34 × ``"Director resigned"``, 24 ×
  ``"Director's particulars changed"``, registrar clarifications
  (*"Information not on the register a Resolution … was removed on
  07/10/2025 …"*) and 1980s allotment shorthand (*"Wd 13/06/89 ad 07/06/89
  --------- premium £ si 6071@.05=303"*). It is arbitrary free text with no
  schema, so it can carry anything, and 255 of the 512 strings were
  distinct. **``representative_details`` (2 items) is worse than
  ``officer_name``**: it is a natural person's name *and their address* in
  one string — the only key observed that carries a second particular, and
  a key the research's 97/26 count does not mention at all. ``officer_name``
  itself appears on 444 of the 670 ``officers``-category items, and the
  other 223 are ``legacy`` rows carrying the name in prose instead: **667 of
  670 officers-category items are person-bearing in ``description_values``.**
* **``items[].description`` is never prose and is never absent.** 94 distinct
  values across 1876 items, 0 absent, every one a template key
  (``appoint-person-director-company-with-name-date``,
  ``accounts-with-accounts-type-full``,
  ``termination-director-company-with-name-termination-date``,
  ``capital-return-purchase-own-shares``, …). The most common value, 512 of
  1876, is the literal sentinel ``"legacy"``, which is what
  ``description_code`` will contain for a pre-2010 filing. D-042(e)(1)'s
  justification — the key says what happened without saying who — holds on
  the wire, including for ``legacy``, whose *key* is inert even though its
  *value* is the worst field in the payload.
* **The empty answer, and the two states inside it.** The endpoint **never
  404s** — confirmed on a UK establishment with no filings (``BR026263``),
  on four never-issued numbers (``99999999``, ``00000001``, ``SC000001``,
  ``OC000001``) and on a malformed one (``ABCDEFGH``): every one is HTTP 200
  with ``{"items": [], "total_count": 0, ...}``. But ``total_count: 0``
  means **two different things**, separated only by ``filing_history_status``
  (all three documented values were reproduced live):
  ``filing-history-available`` (``BR026263``) is *the register holds no
  filings for this company*; ``filing-history-not-available-unknown-prefix``
  (``CE020555``, ``RS007790``, ``ZZ123456``) and
  ``filing-history-not-available-invalid-format`` (``ABCDEFGH``) are *the
  register cannot serve filing history for this number at all*. Relaying
  ``total_count: 0`` in the second case would assert "zero filings" about a
  register that never said so — the two-states-into-one collapse D-011,
  D-026(b), D-028(3), D-041(d) and D-042(d) have now refused five times. So
  :func:`map_filing_history` sets ``total_count`` to ``None`` and says which
  status the register returned, in ``notes``, verbatim. **Flagged for the
  architect rather than decided quietly** — see the shape choices below.
* **Pagination.** No ``items_per_page`` → 25 items. The maximum is **100**:
  101, 200 and 1000 all silently return 100, the same cap ``/charges`` and
  ``/search/companies`` apply. Unlike ``/charges``, this endpoint **does**
  echo ``items_per_page`` and ``start_index`` back in the body — and it
  echoes the *capped* value (asking 1000 returns ``items_per_page: 100``),
  so the echo is the honest one. ``total_count`` is a whole-company total,
  present on every response including the empty ones, and unaffected by
  ``start_index``; it *is* affected by the optional ``category=`` filter
  (Tesco: 8371 unfiltered, 55 for ``category=accounts``), which this module
  never sends. ``start_index`` past the end is an empty page, not an error.
  D-042(j) rules **filings 25**, so :data:`FILINGS_ITEMS_PER_PAGE` is 25 —
  a quarter of what the register would allow, deliberately: an unbounded
  history is an unbounded context cost, Tesco alone has 8371 rows, and
  truncation is disclosed rather than silent.
* **``transaction_id`` is a stable opaque handle** — unique across all 1876
  items, 22–24 characters of base64-looking text
  (``MzEyNDI3ODUzMmFkaXF6a2N4``). Carried as ``document_id`` and never
  interpreted, exactly as D-041(g) ruled for Sweden's ``dokumentId``. **Not
  fetchable through this API**: the document itself lives behind a separate
  host (``document-api.company-information.service.gov.uk``, reachable from
  ``links.document_metadata``), which is a second upstream and therefore a
  second ``SourceRef`` — out of scope here by D-041(c).
* **Dates are plain ``YYYY-MM-DD``, always.** 1876/1876 for ``date``,
  986/986 for ``action_date``, 182/182 for ``made_up_date``. No datetimes,
  no partials.
* **``made_up_date`` covers the filings the allow-list exists to serve.** It
  is present on **118 of 119** ``accounts`` items (the one exception is a
  ``legacy`` row whose only key is the prose one), **46 of 47**
  ``confirmation-statement`` items, and 18 of 59 ``annual-return`` items
  (the other 41 are ``legacy``). The allow-list of one key is not costing
  this module the period end on the filings that have one.
* **``action_date`` is not a substitute for ``made_up_date`` and is not
  read.** It is a top-level, non-person field on 986 items, and it is
  *nearly* the same date on accounts filings — but not the same: it differs
  on 3 of the 118 accounts items that carry both (e.g. ``action_date``
  ``2024-03-31`` against ``made_up_date`` ``2024-02-28``), and it is absent
  on 2 items whose ``made_up_date`` is present. Two dates that agree 97% of
  the time are two dates (D-009); ``made_up_date`` is the one the register
  interpolates into "made up to …", so it is the one ``period_end`` means.
* **Three nested containers carry their own ``description`` and
  ``description_values``** and are a leak vector of their own, with a key
  set of their own that the 24 above do not cover: ``annotations[]`` (182
  entries; ``description_values`` is always the prose ``description`` key,
  182/182), ``resolutions[]`` (122 entries; ``description`` 21, ``res_type``
  17, ``resolution_date`` 5) and ``associated_filings[]`` (22 entries;
  ``description`` 13, ``date`` 4, ``capital`` 4). ``annotations[]`` also has
  a free-prose ``annotation`` field of its own — 33 distinct strings
  observed, all registrar clarifications about stamp duty, but schemaless
  and therefore capable of anything. **This module reads none of them** —
  not the sub-objects, not their ``description``, not their
  ``description_values``, not the ``annotation`` — and the minimisation test
  walks them anyway.
* **``subcategory`` is a string on 587 items and a *list of strings* on one**
  (``["compulsory", "court-order"]``). Not read here; recorded because a
  future task that wants it must not type it ``str``.

Four shape choices flagged for the architect rather than made quietly:

* **``FilingHistory.total_count`` is one field wider than
  ``registries/se/filings.py``.** D-042(j) rules by name that "the block
  carries the register's own ``total_count``", ``ChargeList`` already has a
  field of that name and meaning, and the truncation note is derived from
  it — so it is here. Sweden fills it ``None`` in a one-line change, or the
  architect deletes it in a one-line change; either way wiring stays a
  rename. Every other field is ``registries/se/filings.py``'s, in its order,
  with its meaning.
* **``total_count`` is ``None``, not ``0``, when
  ``filing_history_status`` is not ``filing-history-available``** — the
  D-011 argument above. This is the one place this module declines to relay
  a number the register published, and it is deliberate: the number is a
  true statement about the register's *response* and a false one about the
  *company*. The status string itself reaches the caller verbatim in
  ``notes`` rather than in a field, because it is national vocabulary and
  D-004 keeps national vocabulary out of field names.
* **``financial_year_end`` is taken only from ``kind ==
  "annual_accounts"`` documents**, not from the newest document that happens
  to carry a ``period_end``. In Sweden every document on ``/dokumentlista``
  *is* an annual report, so "the newest ``period_end``" and "the newest
  annual accounts' ``period_end``" are the same sentence; in Britain they
  are not, because a confirmation statement also carries a ``made_up_date``
  and a confirmation-statement date is not a financial year end. Relaying
  one as the other would be the quiet inaccuracy this project exists to
  avoid.
* **Documents are sorted by ``filed_at`` alone**, where Sweden sorts
  ``period_end`` then ``filed_at``. Only 182 of 1876 GB items carry a
  ``period_end`` at all, so Sweden's key would sort 90% of a British
  history into an arbitrary block at the end. ``filed_at`` (the register's
  own ``date``) is on 100% of items, it is what "newest first" means for a
  filing history, and Python's sort is stable — so the register's own order
  within a single date is preserved rather than reshuffled.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from registry_mcp.registries.gb.rules import ACCOUNTS_KIND, CONFIRMATION_KIND

__all__ = [
    "DESCRIPTION_VALUES_ALLOW_LIST",
    "FILINGS_ITEMS_PER_PAGE",
    "FILING_HISTORY_AVAILABLE",
    "FiledDocument",
    "FilingHistory",
    "FilingProvenance",
    "map_filing_history",
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
        default=None, description='Who published this block, e.g. "Companies House (UK)".'
    )
    source_url: str | None = Field(
        default=None, description="A human-readable page for this company's filing history."
    )
    license: str | None = Field(
        default=None, description="The licence this block is published under."
    )
    fetched_at: datetime | None = Field(
        default=None,
        description=(
            "When this block was fetched from Companies House — its own moment, not the "
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
    """One entry from ``GET /company/{n}/filing-history``. Field-for-field
    ``registries/se/filings.py``'s :class:`FiledDocument` — the shape
    ``DECISIONS.md`` D-041(d) rules for the future ``core.models.FiledDocument``,
    as widened by D-042(h) — so the two converge on one shared model.
    Britain is the country D-042(h)'s three extra fields exist for, and
    Britain fills all three."""

    kind: str | None = Field(
        default=None,
        description=(
            "The `Deadline.kind` slug this filing discharges, or `None` when it discharges "
            'none. Britain fills two: `category == "accounts"` maps to "annual_accounts" '
            'and `category == "confirmation-statement"` maps to "confirmation_statement". '
            "The other twenty-odd Companies House categories — `capital`, `officers`, "
            "`mortgage`, `gazette`, `resolution`, `insolvency`, … — map to `None` rather "
            "than to an invented slug: a filing that discharges no deadline this product "
            "publishes says so honestly (`DECISIONS.md` D-009, D-042(h))."
        ),
    )
    period_end: date | None = Field(
        default=None,
        description=(
            "The reporting period's last day, exactly as the register published it. For "
            "Britain this is `description_values.made_up_date` — **the only key of the "
            "register's description-template values this product reads at all** "
            "(D-042(e)(1)). On an `accounts` filing it is the accounting reference date "
            "the accounts were made up to; on a `confirmation-statement` filing it is the "
            "date the statement was made up to, which is *not* a financial year end. "
            "`None` on the great majority of filings, which have no reporting period: it "
            "was published on 182 of 1876 items observed live, and on 118 of 119 "
            "`accounts` items."
        ),
    )
    period_start: date | None = Field(
        default=None,
        description=(
            "The reporting period's first day. **Always `None` for Britain**: Companies "
            "House publishes no counterpart to `made_up_date` on this endpoint, and "
            "deriving one by subtracting twelve months would assert a period length the "
            "register never stated — a first or shortened accounting period is lawful and "
            "common. The field exists because Norway's Regnskapsregisteret publishes "
            "`regnskapsperiode: {fraDato, tilDato}` and will fill it."
        ),
    )
    filed_at: date | None = Field(
        default=None,
        description=(
            "When the register recorded this filing (`items[].date`), verbatim. Present on "
            "every one of the 1876 items observed live, always a plain `YYYY-MM-DD`. This "
            "is the field that makes the block answer *does this company file on time*, "
            "and it is the sort key: newest first."
        ),
    )
    days_from_fee_point: int | None = Field(
        default=None,
        description=(
            "Signed days from a named late-fee datum to `filed_at`, where a register "
            "publishes one. **Always `None` for Britain, and the reason is a missing "
            "datum rather than a missing calculation.** Companies House publishes "
            "`accounts.next_accounts.due_on` and `confirmation_statement.next_due` on the "
            "company profile — the due dates for the *next* period — and publishes no "
            "per-period historical due date anywhere on this endpoint. So for a filing "
            "already made there is nothing to measure against: the datum does not exist "
            "in the data. Deriving one from the statutory rule instead would mean picking "
            "a 9-month or 6-month period, a first-accounts variant and a shortening or "
            "extension the register has not disclosed for that year, and presenting the "
            "result as the register's own — which is precisely the invented figure D-009 "
            "forbids. Sweden fills this field because årsredovisningslagen 8 kap. 6 § "
            "names one datum for every company; Britain has no such single datum. What "
            "Britain gives instead is `filed_at` against the register's own published "
            "next-due dates on `CompanyReport`, which the caller already has."
        ),
    )
    document_id: str | None = Field(
        default=None,
        description=(
            "The register's own opaque handle for this filing (`transaction_id`), relayed "
            "verbatim and never interpreted — unique across every item observed live. "
            "**Not fetchable through this API**: the filed document itself lives behind a "
            "separate Companies House host, which is a second upstream with its own "
            "provenance (D-041(c)) and out of scope here. This is the key a Companies "
            "House support case can name."
        ),
    )
    file_format: str | None = Field(
        default=None,
        description=(
            "What the register holds the document as. **Always `None` for Britain**: this "
            "endpoint publishes no format for a filing — only a page count and a "
            "`paper_filed` marker — and the media type lives on the separate document "
            "host, a second fetch this block does not make."
        ),
    )
    category: str | None = Field(
        default=None,
        description=(
            "The register's own category for this filing, verbatim and never translated: "
            '"accounts", "capital", "officers", "mortgage", "confirmation-statement", '
            '"annual-return", "resolution", "gazette", "incorporation", "address", '
            '"insolvency", "dissolution", "change-of-name", "persons-with-significant-'
            'control", "auditors", "miscellaneous", "historical", "restoration", '
            '"document-replacement", "change-of-constitution", "return", "other" — the '
            "22 values observed across 1876 items, which is not a closed list. It is the "
            "field `kind` is derived from."
        ),
    )
    type_code: str | None = Field(
        default=None,
        description=(
            'The register\'s own form code for this filing, verbatim: "AA", "CS01", '
            '"AP01", "TM01", "MR01", "SH01", and older forms such as "288a", "88(2)" and '
            '"363s" — 100 distinct codes across the 1876 items observed live. Present on '
            "every item."
        ),
    )
    description_code: str | None = Field(
        default=None,
        description=(
            "The register's own description-template key, verbatim and **never resolved** "
            "— e.g. `appoint-person-director-company-with-name-date`, "
            "`accounts-with-accounts-type-full`, "
            "`termination-director-company-with-name-termination-date`, or the literal "
            "sentinel `legacy` on an older filing. This is the key and not the sentence "
            "on purpose, and the reason is the whole design of this block: Companies "
            "House resolves these templates from `description_values`, 97 of the "
            "templates interpolate an officer's name and 26 interpolate a person with "
            "significant control's name, so the resolved sentence is personal data while "
            "the key is not. **The key says what happened; only the values say who** "
            "(`DECISIONS.md` D-042(e)(1), D-028). Present on every one of the 1876 items "
            "observed live, and never free prose — where the register has prose it puts "
            "the sentinel `legacy` here and the prose in a value this product does not "
            "read."
        ),
    )


class FilingHistory(_Base):
    """Stand-in for the future ``core.models.FilingHistory`` (D-041(d)) — the
    same field names as ``registries/se/filings.py``'s, plus ``total_count``
    (D-042(j), see this module's docstring), ``provenance`` typed to
    :class:`FilingProvenance` above rather than to ``core.models.SourceRef``,
    which this module deliberately does not depend on.

    Two-level nullability is the contract (D-041(c)) and belongs to whoever
    wires this up: **an absent block** on a report means "you did not ask, or
    the fetch failed" — never a present block with invented content — while
    **a present block with ``documents: []``** means "Companies House lists
    no filings for this company", which is a real and useful answer about a
    counterparty and must never be rendered as an absence. The third state —
    "Companies House cannot serve filing history for this number at all" —
    is a present block with ``documents: []`` **and ``total_count: None``**,
    and it is spelled out in ``notes``.
    """

    documents: list[FiledDocument] = Field(
        default_factory=list,
        description=(
            "One page of the register's own filing history, newest first by `filed_at`, "
            "at most `FILINGS_ITEMS_PER_PAGE` entries. Never paginated further; when the "
            "register holds more, `total_count` says how many and `notes` says so in "
            "words. Empty means the register lists none — not that we could not look."
        ),
    )
    financial_year_end: date | None = Field(
        default=None,
        description=(
            "The latest reporting period among this company's filed **annual accounts** "
            '(`kind == "annual_accounts"`), carried verbatim — never a synthesised '
            "month-day, and never taken from a confirmation statement, which carries a "
            "`made_up_date` of its own that is not a financial year end. It is the latest "
            "*period*, not the period of the latest *filing*, because Companies House "
            "accepts a second filing that amends an earlier year and that would otherwise "
            "roll this date backwards. It is **evidence of** the company's accounting "
            "reference date, not a statement of it: a company may shorten or extend a "
            "period, and only the period *end* is published here. `None` when this page "
            "holds no annual-accounts filing with a reporting period — including when "
            "older accounts exist further back than this page reaches, which `total_count` "
            "and `notes` disclose."
        ),
    )
    total_count: int | None = Field(
        default=None,
        description=(
            "The register's own count of filings for this company, which may greatly "
            "exceed `len(documents)` — 8371 against a 25-row page, for one company "
            "observed live. **`None` means the register declined to answer for this "
            "company number**, not zero: Companies House returns `total_count: 0` both "
            "for a company it holds no filings for and for a number whose filing history "
            "it cannot serve at all, and relaying the second as a zero would assert "
            "something about the company that the register never said (`DECISIONS.md` "
            "D-011). `notes` names which of the two it was, in the register's own words."
        ),
    )
    provenance: FilingProvenance = Field(
        description="Where, when and under what licence this block was fetched."
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Plain-English caveats about this block.",
    )


# ---------------------------------------------------------------------------
# D-042(e)(1): the allow-list. Exactly one key, and this is the only place in
# `registries/gb/` that names `description_values` at all — so
# `grep -n "description_values" src/registry_mcp/registries/gb/` shows one
# key, which is the greppable check that entry asks for. A key is added here
# by a new entry in `DECISIONS.md`, never by an implementer: 23 further keys
# were observed live (this module's docstring lists every one with its
# count), and `officer_name`, `psc_name`, `representative_details` and the
# `legacy` free-prose `description` are all among them.
# ---------------------------------------------------------------------------
DESCRIPTION_VALUES_ALLOW_LIST = frozenset({"made_up_date"})

#: The page size D-042(j) rules for filings — a quarter of the register's own
#: maximum of 100, deliberately: an unbounded history is an unbounded context
#: cost, and truncation is disclosed in `notes` rather than silent. Public:
#: `client.fetch_filings` requests exactly this many.
FILINGS_ITEMS_PER_PAGE = 25

#: The one value of the register's `filing_history_status` that means "this
#: is a real answer about this company". Confirmed live alongside
#: `filing-history-not-available-unknown-prefix` and
#: `filing-history-not-available-invalid-format`; treated as a closed set of
#: one rather than a vocabulary, because anything else — including a value
#: Companies House has not shipped yet — must fall to the cautious branch.
FILING_HISTORY_AVAILABLE = "filing-history-available"

#: `items[].category` -> the `Deadline.kind` slug that filing discharges
#: (D-042(h)). Derived by membership of a committed table, exactly as
#: `charges.py::_OUTSTANDING_BY_STATUS` is: a category not in this table
#: yields `None`, never a guessed slug (D-025(d), D-009, D-011). The two
#: slugs are imported from `registries/gb/rules.py` rather than retyped, so
#: a filing's `kind` can never drift from the deadline it discharges.
_KIND_BY_CATEGORY: dict[str, str] = {
    "accounts": ACCOUNTS_KIND,
    "confirmation-statement": CONFIRMATION_KIND,
}

#: The human-facing filing-history tab — mirrors
#: ``registries/gb/charges.py``'s convention (the API host itself is not a
#: page a person can open).
_FIND_AND_UPDATE_FILINGS_URL = (
    "https://find-and-update.company-information.service.gov.uk/company/{id}/filing-history"
)

_SOURCE = "Companies House (UK)"
_LICENSE = "Crown copyright — Companies House public register, free to re-use"

#: D-044(b): one include name, `filings`, covers three differently-scoped
#: answers, and the scope difference must be disclosed in the block's own
#: `notes` **on every call** — the promise `mcp/server.py` and
#: `core/models.py`'s `FilingHistory` docstring publish. Unconditional and
#: first, exactly like Norway's `_ONE_PERIOD_NOTE` (the pattern this copies).
_SCOPE_NOTE = (
    "Companies House publishes the whole filing history here, every category of "
    "filing, not only accounts — an accounts filing is one row among confirmation "
    "statements, officer changes, charges and the rest. Use `category` and `kind` to "
    "pick the rows you mean."
)

_FEE_POINT_NOTE = (
    "`days_from_fee_point` is null on every filing here, and that is a missing datum "
    "rather than a missing calculation: Companies House publishes due dates for the "
    "next accounts and the next confirmation statement, and publishes no due date for "
    "a period already filed. There is nothing to measure a past filing against without "
    "inventing one, so this block does not. To judge timeliness, compare `filed_at` "
    "against the register's own published next-due dates on the company record."
)

_MINIMISATION_NOTE = (
    "`description_code` is the register's own description-template key, not a sentence. "
    "Companies House turns those keys into readable descriptions by interpolating "
    "values that name the officer or the person with significant control a filing is "
    "about, so the resolved sentence is personal data and the key is not. This service "
    "relays the key and reads exactly one of the values, the accounting or statement "
    "date. Companies House's own filing-history page resolves them in full."
)

_EMPTY_NOTE = (
    "Companies House lists no filings for this company. That is the register's own "
    "answer, not a failed lookup — but it is not proof that none was ever due: a newly "
    "incorporated company has not filed yet, and a filing can take time to appear."
)

_UNAVAILABLE_NOTE = (
    "Companies House did not answer for this company number: it returned "
    '`filing_history_status: "{status}"`, which means it does not serve filing history '
    "for a number of this kind, rather than that the company has filed nothing. The "
    "empty list here is therefore an absence of an answer, not an answer of none, and "
    "the filing count is reported as unknown rather than as zero."
)


def _parse_date(raw: Any) -> date | None:
    """Companies House dates are plain ``YYYY-MM-DD`` — confirmed on all
    1876 items observed live, for every date field on this endpoint.
    Anything else, or absent, stays ``None`` (matches
    ``registries/gb/mapping.py::_parse_date``)."""
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None


def _allowed_values(item: Mapping[str, Any]) -> dict[str, Any]:
    """The register's description-template values, filtered to
    :data:`DESCRIPTION_VALUES_ALLOW_LIST`.

    **This is the minimisation, and it is the only reader of that field in
    the codebase** (``DECISIONS.md`` D-042(e)(1)). It is written as a filter
    over the allow-list rather than as a direct lookup of the one key so
    that widening the allow-list stays a one-line edit *to the allow-list*,
    and so that a reader grepping for the field finds a rule instead of a
    key. A payload key not in the allow-list is dropped here and can reach
    nothing downstream.
    """
    values = item.get("description_values")
    if not isinstance(values, Mapping):
        return {}
    return {k: v for k, v in values.items() if k in DESCRIPTION_VALUES_ALLOW_LIST}


def _map_one_document(item: Mapping[str, Any]) -> FiledDocument:
    category = item.get("category")
    description = item.get("description")
    type_code = item.get("type")
    transaction_id = item.get("transaction_id")
    values = _allowed_values(item)

    return FiledDocument(
        kind=_KIND_BY_CATEGORY.get(category) if isinstance(category, str) else None,
        period_end=_parse_date(values.get("made_up_date")),
        # Companies House publishes no counterpart to `made_up_date`, and
        # subtracting twelve months would assert a period length it never
        # stated (D-009).
        period_start=None,
        filed_at=_parse_date(item.get("date")),
        # D-042(h): `None` for GB, because the datum does not exist — see the
        # field's own description and `_FEE_POINT_NOTE`.
        days_from_fee_point=None,
        document_id=str(transaction_id) if transaction_id is not None else None,
        # No format is published on this endpoint; the media type lives on
        # the separate document host, which is a second fetch.
        file_format=None,
        category=category if isinstance(category, str) else None,
        type_code=str(type_code) if type_code is not None else None,
        description_code=description if isinstance(description, str) else None,
    )


def map_filing_history(
    payload: Mapping[str, Any],
    company_number: str,
    *,
    cached: bool,
    fetched_at: datetime,
) -> FilingHistory:
    """Pure, synchronous, no I/O — mirrors ``registries/gb/mapping.py``'s
    ``map_entity`` / ``map_search_result`` convention exactly, one level
    down, and ``registries/gb/charges.py``'s ``map_charges`` precisely.

    **An empty list is never ``not_found``**: ``/company/{n}`` alone decides
    whether an entity exists, and this endpoint was confirmed live never to
    404 — not even for a company number that was never issued (D-041(h),
    D-042(j)). What it does instead is answer ``total_count: 0`` for two
    different reasons, and ``filing_history_status`` is the only thing that
    separates them; see this module's docstring.

    Args:
        payload: The parsed JSON body of ``GET /company/{n}/filing-history``.
            Any top-level key this function does not read is ignored, so the
            ``_MINIMISED`` header on a recorded fixture costs nothing
            (``tests/fixtures/README.md``).
        company_number: The normalised CRN (``rules.validate_crn``'s output),
            used only to build ``provenance.source_url`` and the truncation
            note — never re-validated here.
        cached: Whether this block is being served from the cache — this
            block's own cache state, not the company record's (D-041(c)).
        fetched_at: The original fetch time, preserved across cache hits
            (D-006) — again this block's own, not the record's.
    """
    raw_items = payload.get("items")
    items = raw_items if isinstance(raw_items, list) else []
    documents = [_map_one_document(item) for item in items if isinstance(item, Mapping)]
    # Newest first by the register's own filing date. `sort` is stable, and
    # stays stable under `reverse=True`, so filings sharing a date keep the
    # order Companies House returned them in. See the module docstring for
    # why this is not Sweden's `period_end`-first key.
    documents.sort(key=lambda d: d.filed_at or date.min, reverse=True)

    status = payload.get("filing_history_status")
    available = status is None or status == FILING_HISTORY_AVAILABLE
    raw_total = payload.get("total_count")
    # D-011: `total_count: 0` from an unavailable status is a statement about
    # the response, not about the company. Reported as unknown, never as zero.
    total_count = raw_total if isinstance(raw_total, int) and available else None

    # The *latest reporting period* among filed annual accounts, not the
    # period of the most recently filed one: Companies House accepts a second
    # filing that amends an earlier year, and taking the newest filing would
    # then roll the year end backwards. `max` over the periods cannot.
    accounts_periods = [
        d.period_end for d in documents if d.kind == ACCOUNTS_KIND and d.period_end is not None
    ]
    financial_year_end = max(accounts_periods) if accounts_periods else None

    # D-044(b): the scope note is first and unconditional — empty, unavailable
    # or full of accounts and confirmation statements alike — because it is
    # what tells a caller this is the whole filing history, not accounts only.
    notes: list[str] = [_SCOPE_NOTE]
    if not available:
        notes.append(_UNAVAILABLE_NOTE.format(status=status))
    elif not documents:
        notes.append(_EMPTY_NOTE)
    if documents:
        if isinstance(total_count, int) and total_count > len(documents):
            notes.append(
                f"Companies House lists {total_count} filings for this company; only the "
                f"{len(documents)} most recent are included here (one page, newest first). "
                f"See {_FIND_AND_UPDATE_FILINGS_URL.format(id=company_number)} for the rest."
            )
        notes.append(_FEE_POINT_NOTE)
        notes.append(_MINIMISATION_NOTE)

    return FilingHistory(
        documents=documents,
        financial_year_end=financial_year_end,
        total_count=total_count,
        provenance=FilingProvenance(
            source=_SOURCE,
            source_url=_FIND_AND_UPDATE_FILINGS_URL.format(id=company_number),
            license=_LICENSE,
            fetched_at=fetched_at,
            cached=cached,
        ),
        notes=notes,
    )
