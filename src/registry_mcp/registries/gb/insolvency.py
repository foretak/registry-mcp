"""GB insolvency — ``GET /company/{n}/insolvency`` (Companies House).

**R-5e** (``DECISIONS.md`` D-042(i)). This module maps the wire straight onto
the canonical :class:`~registry_mcp.core.models.InsolvencyCase` /
:class:`~registry_mcp.core.models.InsolvencyEvent` /
:class:`~registry_mcp.core.models.InsolvencyBlock` /
:class:`~registry_mcp.core.models.SourceRef`. D-042 rules no insolvency
shape by name (its part (h) widens ``FiledDocument`` only), so the shapes
these classes carry are this module's proposal, designed to D-042(g)'s
rules — country-neutral names, national vocabulary in values only. There is
no local stand-in and nothing to convert: :func:`map_insolvency` constructs
the canonical classes directly, and ``CompaniesHouseRegistry.insolvency``
(``registries/gb/__init__.py``) returns
:func:`registry_mcp.registries.gb.client.fetch_insolvency`'s result
unchanged. See "What this module still asks of the architect" at the end of
this docstring.

**The person data is the whole difficulty, and D-042(e)(2) already ruled it.**
``cases[].practitioners[]`` carries a licensed individual's **name and postal
address** — D-042(e) calls this endpoint "the most person-bearing of the
four" it examined. D-042(e)(2) rules that **practitioners are not relayed at
all in the first tranche**, because case type, case number and the register's
own dated events carry the entire distress signal a pre-contract check needs;
"who is administering it" is a different question, and D-028 governs it (none
of D-028's four preconditions is met). This module implements that ruling
three times over, so that it holds structurally rather than by care:

1. :func:`map_insolvency` never reads ``practitioners`` at all. There is no
   field on :class:`InsolvencyCase` a practitioner particular could land in,
   including a free-text one — see (2) for the only free-text-*shaped* field
   the payload has, and what happens to it.
2. :func:`strip_practitioners` removes the key from the payload **before**
   ``registries/gb/client.py::fetch_insolvency`` writes anything to the
   cache. So no practitioner name or address is ever written to this
   deployment's disk, and D-028(2)'s person-record-TTL problem never arises
   here: there is no person record to age out.
3. No committed fixture carries one. The seven live recordings in
   ``tests/fixtures/ch_*_insolvency.json`` had ``practitioners`` removed at
   record time and each says so in its own header; the single fixture that
   *does* carry the array,
   ``tests/fixtures/ch_insolvency_practitioners_synthetic.json``, is entirely
   fabricated and exists only so a test can prove nothing survives the mapper.

Recon findings behind every choice below — live calls against
``https://api.company-information.service.gov.uk``, 2026-09-08, credential
from ``COMPANIES_HOUSE_API_KEY``, never written to a file — reported in full
to the orchestrator. Sample: **1,458 company numbers** drawn from Companies
House's own ``/advanced-search/companies`` across eleven ``company_status``
buckets, yielding **1,105 HTTP 200s covering 1,485 cases and 2,607
practitioner entries**, plus 353 HTTP 404s. The load-bearing findings, so a
later reader does not have to re-derive them:

* **A solvent company 404s, and this is the trap.** ``/charges`` never 404s;
  this endpoint does, and it is the *normal* answer for a healthy company.
  Tesco (``00445790``), Monzo (``09446231``), Deloitte LLP (``OC303675``) and
  NatWest Markets (``SC090312``) all return **HTTP 404** with
  ``{"timestamp": …, "status": 404, "error": "Not Found", "path": …}``. So do
  the dissolved ``00000006``, the overseas ``FC032315``, the establishment
  ``BR026263``, and — byte-identically, bar ``path`` — the company numbers
  ``99999999`` and ``12345678``, which were **never issued**. **A 404 here
  carries no information whatever about whether the company exists.** Mapping
  it to ``not_found`` would turn every healthy company into a non-existent
  one; ``fetch_insolvency`` maps it to a *present, empty* block instead, per
  D-041(h)'s principle that ``/company/{n}`` alone decides existence.
* **There are three states, not two, and the mapper keeps them apart**
  (D-011). *(a)* HTTP 404 — the register holds no insolvency resource for
  this number (353/1,458). *(b)* HTTP 200 with ``"cases": []`` — the resource
  exists and publishes no case (20/1,105 — e.g. ``00712615``, whose profile
  says ``company_status == "liquidation"`` and
  ``has_insolvency_history == true``). *(c)* HTTP 200 with cases. The
  distinguisher survives into the mapper for free, because a 200 **always**
  carries the ``cases`` key (1,105/1,105) and the 404 body never does: so
  ``"cases" in payload`` *is* "the register holds a resource here", and
  :func:`map_insolvency` writes a different, honest ``notes`` sentence for
  (a) and (b) rather than collapsing them.
* **``has_insolvency_history`` is honest here — unlike ``has_charges``.**
  Checked on 160 company profiles against their own insolvency responses:
  ``has_insolvency_history == true`` ⟺ ``links.insolvency`` present ⟺ HTTP
  200, 76/76, with no counter-example; ``false`` was never once accompanied
  by a case. It is still not read by this module (only this endpoint's own
  response is authoritative for what this endpoint returns), and it is still
  not a predictor of *content*: 6 of those 76 were ``true`` with zero cases.
* **No pagination, so D-042(j)'s truncation disclosure has nothing to
  disclose.** ``items_per_page`` and ``start_index`` are both accepted and
  both **ignored** — ``?items_per_page=1`` on a three-case company returns
  all three. The register publishes no ``total_count``, ``items_per_page`` or
  ``start_index`` on this resource, and the largest history seen was 31
  cases. One request returns the whole history, so :class:`InsolvencyBlock`
  has no ``total_count`` field and never emits a truncation note.
* **``practitioners`` is always present and sometimes genuinely empty.** The
  key appeared on 1,485/1,485 cases; 79 of those carried ``[]``. Nothing here
  depends on that — the key is removed before the payload is cached and never
  read afterwards — but it means a live ``"practitioners": []`` is a real
  register fact (``tests/fixtures/ch_SC001381_insolvency.json``) and must not
  be confused with this project's own stripping.

**Nothing outside ``practitioners[]`` can carry a person's name or address —
and that was checked, not assumed.** Every string-valued path in all 1,105
live 200s was enumerated and matched against a shape: **zero violations**.
Specifically:

* There is **no ``case_number`` field**. The register's field is
  ``cases[].number``, and its entire observed value domain across 1,485 cases
  is the decimal strings ``"1"`` … ``"31"``. It is a per-company sequence
  number, **not** a court reference, and it is mapped to ``case_number`` with
  a description that says so.
* ``cases[].notes`` is the payload's only free-text-*typed* field — the
  Companies House schema declares it ``array[string]`` with no enumeration.
  Live it is not prose: the **entire** observed value domain across 1,485
  cases is the single slug ``"scottish-insolvency-info"`` (202 occurrences on
  171 companies, every one of them an ``SC`` number). Because a documented
  ``array[string]`` is an unbounded domain and this is the one field a name
  could hide in, it is relayed through an **allow-list**
  (:data:`_KNOWN_NOTE_CODES`) rather than wholesale — D-042(e)(1)'s
  mechanism, applied to the field that needs it. An unrecognised code is
  dropped and disclosed in ``notes``, never relayed and never silently
  swallowed.
* Everything else is machine vocabulary: ``etag`` is 40 hex characters,
  ``status[]`` / ``cases[].type`` / ``cases[].dates[].type`` are lowercase
  hyphenated slugs, ``cases[].dates[].date`` is ``YYYY-MM-DD``, and
  ``cases[].links.charge`` is a ``/company/{n}/charges/{id}`` path.

**Two documentation bugs found, recorded so nobody codes to the docs.** The
published schema declares the root ``status`` a **string**; live it is always
an **array** of strings (980 payloads). It declares
``practitioners[].address`` an **array**; live it is always an **object**.
Also, ``dates[].type`` value ``dissolved-on`` occurs 37 times live and is
**not in the documented enum** at all.

Two deliberate omissions, flagged for the architect rather than decided
quietly:

* **``cases[].links.charge`` is not relayed.** It appeared on 573/1,485 cases
  and names the charge a receiver was appointed under, which is genuinely
  useful. It is dropped because its trailing token is the *charges* endpoint's
  ``links.self`` id, **not** ``Charge.charge_id`` — which
  ``registries/gb/charges.py`` maps from ``charge_code``, and which is
  ``None`` for exactly the pre-2013 charges these old receiverships point at
  (verified on ``01034351``: all 21 charges have ``charge_code == null``).
  Relaying it under any name that reads like a charge id would invite a join
  that silently fails. If the architect wants it, it wants its own name
  (``charge_link``) and its own sentence saying what it does and does not
  join to. ``tests/fixtures/ch_01034351_insolvency.json`` preserves two of
  them so the decision can be revisited against real data.
* **No block-level derived flag over ``statuses``.** The root ``status``
  array is the register's own current company-level insolvency state, and it
  is *nearly* a clean signal: present on 0/7 live ``active`` companies with
  historic cases and 1/41 ``dissolved`` ones, but also **absent on ~10%** of
  companies whose ``company_status`` is an insolvency status (36/327
  ``liquidation``, 11/271 ``administration``). So an absent ``status`` cannot
  be read as "not currently insolvent" without guessing, and D-011 forbids
  the guess. ``statuses`` is relayed verbatim; the empty list means "the
  register publishes no current insolvency status word here", which the field
  description says in as many words.

**What this module still asks of the architect.** The shapes above are this
module's proposal, not a ruling — D-042 never names an insolvency shape, and
nothing since has ruled one either. And ``core/cache.py``'s per-kind TTL
table (D-042(j): 24 h non-empty, 1 h empty) still does not exist, so
:func:`registry_mcp.registries.gb.client.fetch_insolvency` still uses the
stand-in described on its own docstring.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from registry_mcp.core.models import InsolvencyBlock, InsolvencyCase, InsolvencyEvent, SourceRef

__all__ = [
    "InsolvencyBlock",
    "InsolvencyCase",
    "InsolvencyEvent",
    "map_insolvency",
    "strip_practitioners",
]


# ---------------------------------------------------------------------------
# Case-type vocabulary -> is_liquidation (D-042(j), D-025(d), D-011): derived
# by membership of a table of words this module has actually seen on the wire.
# A case type not in this table yields `None`, never `False`. Confirmed live
# 2026-09-08 across 1,485 cases on 1,105 companies; the counts below are that
# sample's, and every one of the ten words was observed at least once.
#
# `receivership` and `foreign-insolvency` are in Companies House's published
# enumeration but were **never observed** in 1,485 cases, so they are
# deliberately absent and yield `None` — do not add them without a live
# payload to cite.
#
# "Liquidation" here means "the company is being wound up", which is what the
# register's own words denote. It does NOT mean "insolvent": a members'
# voluntary liquidation is a solvent winding-up (56 live cases, and the
# `declaration-solvent-on` event type exists precisely for it).
# ---------------------------------------------------------------------------
_LIQUIDATION_BY_CASE_TYPE: dict[str, bool] = {
    "compulsory-liquidation": True,  # 163 live
    "creditors-voluntary-liquidation": True,  # 139 live
    "members-voluntary-liquidation": True,  # 56 live — solvent; see the field description
    "in-administration": False,  # 358 live
    "administration-order": False,  # 20 live
    "administrative-receiver": False,  # 113 live
    "receiver-manager": False,  # 498 live
    "corporate-voluntary-arrangement": False,  # 136 live
    "corporate-voluntary-arrangement-moratorium": False,  # 1 live
    "moratorium": False,  # 1 live
}

# ---------------------------------------------------------------------------
# `cases[].notes` allow-list (D-042(e)(1)'s mechanism). Companies House
# declares this field `array[string]` and enumerates nothing, so its domain is
# formally unbounded — and it is the only free-text-*typed* field in the
# payload, i.e. the only place a practitioner's name could reach a caller
# without going through `practitioners[]`. Across 1,485 live cases the entire
# observed domain is the single slug below (202 occurrences, 171 companies,
# every one an `SC` number). A code outside this set is dropped and disclosed,
# never relayed. Add a code here only with a live payload to cite.
# ---------------------------------------------------------------------------
_KNOWN_NOTE_CODES: frozenset[str] = frozenset({"scottish-insolvency-info"})

#: The key this module removes from every payload before it is cached or
#: mapped. Named once so a grep for it finds every place it is handled.
_PRACTITIONERS_KEY = "practitioners"


def _parse_date(raw: Any) -> date | None:
    """Companies House dates are plain ``YYYY-MM-DD``; anything else, or
    absent, stays ``None`` (matches ``registries/gb/mapping.py::_parse_date``)."""
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def strip_practitioners(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of ``payload`` with every ``cases[].practitioners`` gone.

    Pure, synchronous, no I/O. Called by
    ``registries/gb/client.py::fetch_insolvency`` on the raw upstream body
    **before** anything is written to the cache, so that a licensed
    practitioner's name and postal address never reach this deployment's disk
    — the strongest available reading of D-042(e)(2), and the reason
    D-028(2)'s shortened person-record TTL has nothing to protect here.

    The key is **removed**, not emptied: a live ``"practitioners": []`` is a
    real register fact (79 of 1,485 live cases), and collapsing "the register
    publishes no practitioner" into "this service removed them" would be the
    same two-states-into-one mistake D-011 exists to prevent.

    Nothing downstream depends on this having run — :func:`map_insolvency`
    reads no practitioner field under any circumstance — so this is the
    outer of two independent bars, not the only one.
    """
    out: dict[str, Any] = {k: v for k, v in payload.items() if k != "cases"}
    cases = payload.get("cases")
    if isinstance(cases, list):
        out["cases"] = [
            {k: v for k, v in case.items() if k != _PRACTITIONERS_KEY}
            if isinstance(case, Mapping)
            else case
            for case in cases
        ]
    elif "cases" in payload:
        out["cases"] = cases
    return out


def _map_one_event(raw: Mapping[str, Any]) -> InsolvencyEvent:
    return InsolvencyEvent(
        event_type=raw.get("type"),
        occurred_on=_parse_date(raw.get("date")),
    )


def _map_one_case(item: Mapping[str, Any]) -> tuple[InsolvencyCase, int]:
    """Map one ``cases[]`` entry, returning it and the number of note codes
    the allow-list withheld (disclosed by the caller in the block's ``notes``)."""
    case_type = item.get("type")
    events = [_map_one_event(d) for d in (item.get("dates") or []) if isinstance(d, Mapping)]
    events.sort(key=lambda e: e.occurred_on or date.min, reverse=True)

    raw_notes = [str(n) for n in (item.get("notes") or [])]
    note_codes = [n for n in raw_notes if n in _KNOWN_NOTE_CODES]

    number = item.get("number")
    return (
        InsolvencyCase(
            case_number=str(number) if number is not None else None,
            case_type=case_type,
            is_liquidation=(_LIQUIDATION_BY_CASE_TYPE.get(case_type) if case_type else None),
            events=events,
            note_codes=note_codes,
        ),
        len(raw_notes) - len(note_codes),
    )


def _case_sort_key(case: InsolvencyCase) -> tuple[date, int]:
    """Newest first: the case's most recent event date, then `case_number`.

    A case the register gives no date for sorts to :data:`datetime.date.min`,
    i.e. last — honest rather than invented, and the same shape of tie-break
    ``registries/gb/charges.py::map_charges`` uses.
    """
    latest = max((e.occurred_on for e in case.events if e.occurred_on), default=date.min)
    number = case.case_number or ""
    return (latest, int(number) if number.isdigit() else 0)


#: The human-facing find-and-update page for a company's insolvency tab —
#: mirrors ``registries/gb/charges.py``'s convention (the API host itself is
#: not a page a person can open). Confirmed live 2026-09-08 to return 200.
_FIND_AND_UPDATE_INSOLVENCY_URL = (
    "https://find-and-update.company-information.service.gov.uk/company/{id}/insolvency"
)

_SOURCE = "Companies House (UK)"
_LICENSE = "Crown copyright — Companies House public register, free to re-use"

#: Emitted on every block that has at least one case. Disclosure, not
#: silence: an agent told only "here are the cases" could reasonably infer no
#: practitioner was ever appointed, which is false for 1,406 of the 1,485
#: live cases behind this module.
_PRACTITIONERS_NOTE = (
    "Companies House also publishes the name and postal address of each insolvency "
    "practitioner appointed to these cases. This service does not relay them: they are a "
    "natural person's particulars, and the case type, case number and dated events above "
    "carry the register's whole distress signal without them. For who is administering the "
    "case, read the register's own page: {url}"
)

#: Emitted when the payload has no ``cases`` key at all — i.e. the upstream
#: 404, which ``fetch_insolvency`` turns into an empty payload.
_NO_RESOURCE_NOTE = (
    "Companies House publishes no insolvency record for company number {id}. Note that this "
    "endpoint answers the same way for a company that has simply never been insolvent, for a "
    "dissolved company, and for a company number that was never issued — so this is not "
    "evidence about whether the company exists. Only lookup_company decides that."
)

#: Emitted when the payload has ``cases: []`` — the register holds a resource
#: and publishes nothing in it. A different fact from the one above (D-011).
_EMPTY_RESOURCE_NOTE = (
    "Companies House holds an insolvency record for company number {id} but publishes no case "
    "in it. That is the register's own answer, not a fetch that came back short."
)

#: Emitted when the allow-list withheld a note code (never observed live).
_WITHHELD_NOTES_NOTE = (
    "{count} case note code(s) Companies House published are not relayed here: this service "
    "relays only note codes it has confirmed to be codes rather than free text, because the "
    "register declares this field as unrestricted text and it is the one field in this record "
    "that could carry a person's name. See {url} for the register's own wording."
)


def map_insolvency(
    payload: Mapping[str, Any],
    company_number: str,
    *,
    cached: bool,
    fetched_at: datetime,
) -> InsolvencyBlock:
    """Pure, synchronous, no I/O — mirrors ``registries/gb/charges.py``'s
    ``map_charges`` convention exactly.

    **Reads no practitioner field, under any circumstance.** Feeding this
    function a raw payload that still carries ``cases[].practitioners`` (as
    ``tests/fixtures/ch_insolvency_practitioners_synthetic.json`` does)
    produces the same output as feeding it the stripped one.

    Args:
        payload: The parsed JSON body of ``GET /company/{n}/insolvency``, or
            an empty mapping standing for the upstream 404 (which is the
            normal answer for a solvent company and is never ``not_found``).
        company_number: The normalised CRN (``rules.validate_crn``'s output),
            used only to build ``provenance.source_url`` and the ``notes``
            sentences — never re-validated here.
        cached: Whether this block is being served from the cache.
        fetched_at: The original fetch time (preserved across cache hits,
            ``DECISIONS.md`` D-006).
    """
    page_url = _FIND_AND_UPDATE_INSOLVENCY_URL.format(id=company_number)

    raw_cases = payload.get("cases")
    cases: list[InsolvencyCase] = []
    withheld = 0
    if isinstance(raw_cases, list):
        for item in raw_cases:
            if not isinstance(item, Mapping):
                continue
            case, dropped = _map_one_case(item)
            cases.append(case)
            withheld += dropped
    cases.sort(key=_case_sort_key, reverse=True)

    statuses = [str(s) for s in (payload.get("status") or [])]

    notes: list[str] = []
    if cases:
        notes.append(_PRACTITIONERS_NOTE.format(url=page_url))
    elif "cases" in payload:
        notes.append(_EMPTY_RESOURCE_NOTE.format(id=company_number))
    else:
        notes.append(_NO_RESOURCE_NOTE.format(id=company_number))
    if withheld:
        notes.append(_WITHHELD_NOTES_NOTE.format(count=withheld, url=page_url))

    return InsolvencyBlock(
        cases=cases,
        statuses=statuses,
        provenance=SourceRef(
            source=_SOURCE,
            source_url=page_url,
            license=_LICENSE,
            fetched_at=fetched_at,
            cached=cached,
        ),
        notes=notes,
    )
