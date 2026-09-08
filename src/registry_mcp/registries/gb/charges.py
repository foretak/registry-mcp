"""GB charges — ``GET /company/{n}/charges`` (Companies House).

Built for **R-5c / T37**, Part B, **behind the seam** (``DECISIONS.md``
D-042, ``tasks/T37.md``): this module is deliberately self-contained inside
``registries/gb/``, built against no assumption that ``core/models.py``
carries ``SourceRef``, ``Charge`` or ``ChargeBlock`` — those are R-5's
``include=[...]`` machinery, owned and built in parallel by a different
agent (``core/registry.py``, ``core/models.py``), per this task's explicit
footprint. **Nothing here touches ``core/``, imports from it beyond what
``registries/gb/`` already imported, or depends on its shape.**

Update, partway through this task: R-5 landed in the working tree while
this module was being written — ``core/registry.py`` now has a concrete
``lookup_with`` and ``Registry.supported_includes``, and ``core/models.py``
now defines ``SourceRef`` (uncommitted, the parallel agent's own work, not
read or relied on here). That does not change anything below: this module
was scoped to stay self-contained regardless of when R-5 landed, and wiring
it up is still explicitly a follow-up task's job, not this one's.

The model shapes below are copied field-for-field from ``DECISIONS.md``
D-042 part (h) — the ruled shape of the future ``core.models.Charge`` /
``core.models.ChargeBlock`` — precisely so that wiring this up once R-5
lands is a rename, not a redesign:

* delete (or thinly re-export) ``Charge``, ``ChargeProvenance`` and
  ``ChargeList`` from this module;
* ``core/models.py`` gains the real ``Charge`` / ``ChargeBlock`` (D-042(h))
  and ``CompanyReport.charges: ChargeBlock | None``;
* ``CompaniesHouseRegistry`` (``registries/gb/__init__.py``) gains
  ``async def charges(self, id: str) -> ChargeBlock`` — validate the CRN via
  ``rules.validate_crn`` (as every other method here already does), call
  :func:`registry_mcp.registries.gb.client.fetch_charges`, and copy the
  returned :class:`ChargeList`'s fields onto the real ``ChargeBlock``
  (``provenance`` becomes a real ``SourceRef`` built from
  :class:`ChargeProvenance`'s five identically-named fields);
* ``CompaniesHouseRegistry.supported_includes`` gains ``"charges"``.

Recon findings behind every choice below — live calls against
``https://api.company-information.service.gov.uk``, 2026-09-08, credential
from ``COMPANIES_HOUSE_API_KEY``, never written to a file — are reported in
full to the orchestrator. The load-bearing ones, so a later reader does not
have to re-derive them:

* **The endpoint never 404s.** Confirmed on eight real companies with no
  charges filed (``OC303675`` / Deloitte LLP among them — ``tests/fixtures/
  ch_OC303675_charges.json``) *and* on a company number that does not exist
  at all (``99999999``, which 404s at ``/company/{n}`` itself): every one of
  them is HTTP 200, ``{"items": [], "total_count": 0, ...}``. D-041(h)'s
  principle — "``/company/{n}`` decides whether an entity exists; ``/charges``
  never does" — is therefore never actually exercised by a live 404 from
  this endpoint, but :func:`registry_mcp.registries.gb.client.fetch_charges`
  still treats one as a present, empty block rather than ``not_found``, per
  D-042(j), in case a future edge case (a suspended or merged number, a
  transient gateway 404) produces one.
* **``has_charges`` on the company profile cannot be trusted to predict this
  endpoint — at all.** ``tests/fixtures/ch_00445790.json`` (Tesco, recorded
  2026-09-04) carries ``"has_charges": false``; the live ``/charges`` call
  four days later returned **nine** real charges dated 1991-2009, two still
  ``"outstanding"`` (``tests/fixtures/ch_00445790_charges.json``). This is a
  stronger and independent finding from ``UK_SPEC.md`` §1.6 №1 (which only
  says ``links.charges`` is present despite the boolean) — here the boolean
  itself was wrong, not just the link, on a snapshot four days old. Nothing
  in this module reads ``has_charges``; only this endpoint's own response is
  ever authoritative for what it returns.
* **Pagination.** No ``items_per_page`` → 25 items. ``items_per_page=100`` →
  100. ``items_per_page=200`` or ``1000`` → silently capped at 100 (the same
  cap Companies House applies to ``/search/companies``, ``UK_SPEC.md`` §1.6
  №8). ``items_per_page`` and ``start_index`` are never echoed back in the
  body, unlike the documented shape. ``total_count`` / ``unfiltered_count`` /
  ``satisfied_count`` / ``part_satisfied_count`` are **whole-company**
  totals, present and stable regardless of page size — confirmed identical
  across three page sizes (25/50/100) against a 137-charge company
  (``SC090312``, NatWest Markets, ``tests/fixtures/ch_SC090312_charges.json``,
  recorded at ``items_per_page=100``, the confirmed maximum). D-042(j) rules
  "charges: the register's maximum" as the page size, so
  :data:`CHARGES_ITEMS_PER_PAGE` is 100 and
  :func:`registry_mcp.registries.gb.client.fetch_charges` requests exactly
  that.
* **No live ``"part-satisfied"`` example.** Only ``"outstanding"`` and
  ``"fully-satisfied"`` were observed, across 39 items on four companies —
  including the 137-charge bank, whose own ``part_satisfied_count`` was 0.
  :data:`_OUTSTANDING_BY_STATUS` therefore has exactly those two keys. Per
  D-042(j) / D-025(d) / D-011: a status word the table does not contain
  (``"part-satisfied"`` included) yields ``Charge.is_outstanding = None``,
  never a guess — add the word once a live payload confirms the exact
  string Companies House sends for it.
* **No natural person's name observed** among 39 ``persons_entitled[].name``
  values across Tesco, NatWest Markets, Monzo (``09446231``) and ``00000006``
  — every one is a bank, insurer, fund, trustee company or similar
  institution (e.g. "Citibank, N.A., in Its Capacity as Collateral Agent",
  "Tesco Trustee Company of Ireland Limited as Trustee of the Tesco Ireland
  Limited Senior Executive Pension Scheme"). ``parties_entitled`` is kept
  (renamed from ``persons_entitled``, D-042(e)(3)) rather than dropped:
  D-042(h)'s model text includes it, name-only, D-028(1)-bound, because a
  security holder's identity is the one thing a charges credit-check cannot
  do without. **Reported tension, not resolved unilaterally**: this task's
  own Part A framing said "if any field names a natural person, it is
  barred by D-028 and must be dropped, exactly as filing history's
  ``officer_name`` is" — which is *not* what D-042(e)(3)/(h) actually rules
  for this specific field (officer_name is barred outright; persons_entitled
  is relayed, renamed, and bound by D-028(1), because D-042 judged the
  minimisation sufficient and the use case unanswerable without it). This
  module follows D-042 — the fuller, reasoned, dated ruling this task told
  its implementer to read in full — over the shorter paraphrase in its own
  brief, and says so here for the orchestrator to double-check.
* **Two fields observed live that D-042(h) does not mention**:
  ``particulars.contains_fixed_charge`` (a sibling of
  ``contains_floating_charge`` and ``contains_negative_pledge``) and a
  ``charge_code`` absent on roughly a quarter of items (pre-2013 filings,
  before Companies House assigned it retrospectively) — mapped to
  ``charge_id`` when present, honestly ``None`` when not, per D-009. Neither
  is added to the model here: D-042(g)'s anti-bend rule reserves that for an
  entry in ``DECISIONS.md``, not an implementer's judgement call.

Two arithmetic choices this module makes that D-042(h) does not spell out,
flagged for the architect rather than decided quietly:

* ``ChargeList.outstanding_count`` is derived as ``total_count -
  satisfied_count`` (both register-published whole-dataset integers,
  identical in kind to how ``registries/gb/mapping.py::map_search_result``
  derives ``truncated`` from ``total_results`` and ``len(hits)`` — arithmetic
  on published facts, not a guess). Companies House also publishes
  ``part_satisfied_count``, which D-042(h)'s ``ChargeBlock`` has no field
  for; it was 0 in every payload this recon saw, so the choice is untested
  in practice, but the honest reading is that a part-satisfied charge is
  still counted here as "not fully satisfied", i.e. within
  ``outstanding_count``. A future ``ChargeBlock`` may want its own
  ``part_satisfied_count`` field — this module cannot add it (D-042(g)).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CHARGES_ITEMS_PER_PAGE",
    "Charge",
    "ChargeList",
    "ChargeProvenance",
    "map_charges",
]


class _Base(BaseModel):
    """Local stand-in for ``core.models._Base`` — the same ``extra="forbid"``
    discipline (``DECISIONS.md`` D-004), kept out of ``core/`` per this
    task's footprint restriction rather than imported from there."""

    model_config = ConfigDict(extra="forbid", frozen=False)


class ChargeProvenance(_Base):
    """Stand-in for the future ``core.models.SourceRef`` (D-026(c)) — the
    same five field names, unrenamed, so that building the real
    ``ChargeBlock.provenance`` from this object is a straight field copy."""

    source: str | None = Field(
        default=None, description='Who published this block, e.g. "Companies House (UK)".'
    )
    source_url: str | None = Field(
        default=None, description="A human-readable page for this company's charges."
    )
    license: str | None = Field(
        default=None, description="The licence this block is published under."
    )
    fetched_at: datetime | None = Field(
        default=None, description="When this block was fetched from Companies House."
    )
    cached: bool = Field(
        default=False, description="Whether this block was served from this deployment's cache."
    )


class Charge(_Base):
    """One entry from ``GET /company/{n}/charges``. Field-for-field the shape
    ``DECISIONS.md`` D-042(h) rules for the future ``core.models.Charge``."""

    charge_id: str | None = Field(
        default=None,
        description=(
            "The register's own opaque handle for this charge (its `charge_code`); not "
            "fetchable through this API. `None` on roughly a quarter of pre-2013 filings, "
            "which Companies House never back-filled a code for — honestly absent, not guessed."
        ),
    )
    charge_number: int | None = Field(
        default=None,
        description="The register's sequence number for this charge, within this company.",
    )
    status: str | None = Field(
        default=None,
        description='The register\'s own word, verbatim: "outstanding", "fully-satisfied", or '
        "a third word this module has not yet observed live.",
    )
    is_outstanding: bool | None = Field(
        default=None,
        description=(
            "Derived from `status` by membership of a committed table of words this module has "
            "actually observed on the wire (`_OUTSTANDING_BY_STATUS`). `None` when `status` is "
            "absent or is a word not yet in that table — never guessed, never `False` by default."
        ),
    )
    classification: str | None = Field(
        default=None, description="What kind of instrument this is, as the register describes it."
    )
    created_on: date | None = Field(default=None, description="When the charge was created.")
    delivered_on: date | None = Field(
        default=None,
        description="When the charge was delivered to Companies House for registration.",
    )
    satisfied_on: date | None = Field(
        default=None, description="When the charge was satisfied, if it has been."
    )
    assets_charged: str | None = Field(
        default=None, description="The register's own free-text description of what is charged."
    )
    obligations_secured: str | None = Field(
        default=None,
        description="The register's own free-text description of what the charge secures.",
    )
    contains_floating_charge: bool | None = Field(
        default=None,
        description="Whether the register marks this instrument as including a floating charge.",
    )
    parties_entitled: list[str] = Field(
        default_factory=list,
        description=(
            "Names exactly as the register publishes them for the party or parties the charge "
            "is entitled to (typically a bank, an insurer or a trustee company; occasionally a "
            "natural person, e.g. a director lending to their own company — none was observed "
            "live in this module's recon). This is a term of the company's own instrument, not a "
            "person record: it is never a lookup key, never indexed, never searchable and never "
            "reaches a log line (`DECISIONS.md` D-028(1), D-040). It is the one place in this "
            "product a natural person's name can appear, and it is renamed from the register's "
            "own `persons_entitled` deliberately — the register's name asserts a natural person; "
            "this one does not."
        ),
    )


class ChargeList(_Base):
    """Stand-in for the future ``core.models.ChargeBlock`` (D-042(h)) — the
    same field names, ``provenance`` typed to :class:`ChargeProvenance`
    above rather than to ``core.models.SourceRef``, which does not exist
    yet. One page, the register's maximum size (:data:`CHARGES_ITEMS_PER_PAGE`),
    never paginated further (D-042(j))."""

    charges: list[Charge] = Field(
        default_factory=list,
        description="Sorted newest first: `created_on` descending, then `charge_number` descending.",
    )
    total_count: int | None = Field(
        default=None,
        description="The register's own count of charges for this company, which may exceed `len(charges)`.",
    )
    outstanding_count: int | None = Field(
        default=None,
        description=(
            "Derived as `total_count - satisfied_count` (both register-published whole-company "
            "figures); see this module's docstring for why, and for the part-satisfied caveat."
        ),
    )
    satisfied_count: int | None = Field(
        default=None,
        description="The register's own whole-company count of satisfied charges, verbatim.",
    )
    provenance: ChargeProvenance = Field(
        description="Where, when and under what licence this block was fetched."
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Plain-English caveats about this block, e.g. truncation when `total_count` exceeds `len(charges)`.",
    )


# ---------------------------------------------------------------------------
# Status vocabulary -> is_outstanding (D-042(j), D-025(d), D-011): derived by
# membership of a table of words this module has actually seen on the wire.
# A status word not in this table yields `None`, never `False`. Confirmed
# live 2026-09-08 across 39 charges on 4 companies (Tesco/00445790,
# 00000006, Monzo/09446231, NatWest Markets/SC090312 at its full 137-charge,
# 100-item page): only "outstanding" and "fully-satisfied" were ever seen.
# "part-satisfied" is a plausible third word (it names the envelope's own
# `part_satisfied_count`) but was never observed on an item, so it is
# deliberately absent — do not add it without a live payload to cite.
# ---------------------------------------------------------------------------
_OUTSTANDING_BY_STATUS: dict[str, bool] = {
    "outstanding": True,
    "fully-satisfied": False,
}

#: The register's own maximum `items_per_page` for this endpoint, confirmed
#: live 2026-09-08 (asking for 200 or 1000 both silently return 100).
#: D-042(j): "charges: the register's maximum." Public: `client.fetch_charges`
#: requests exactly this many.
CHARGES_ITEMS_PER_PAGE = 100


def _parse_date(raw: Any) -> date | None:
    """Companies House dates are plain ``YYYY-MM-DD``; anything else, or
    absent, stays ``None`` (matches ``registries/gb/mapping.py::_parse_date``)."""
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _map_one_charge(item: Mapping[str, Any]) -> Charge:
    status = item.get("status")
    classification = (item.get("classification") or {}).get("description")
    particulars = item.get("particulars") or {}
    secured_details = item.get("secured_details") or {}
    parties = [str(p["name"]) for p in (item.get("persons_entitled") or []) if p.get("name")]

    return Charge(
        charge_id=item.get("charge_code"),
        charge_number=item.get("charge_number"),
        status=status,
        is_outstanding=(_OUTSTANDING_BY_STATUS.get(status) if status else None),
        classification=classification,
        created_on=_parse_date(item.get("created_on")),
        delivered_on=_parse_date(item.get("delivered_on")),
        satisfied_on=_parse_date(item.get("satisfied_on")),
        assets_charged=particulars.get("description"),
        obligations_secured=secured_details.get("description"),
        contains_floating_charge=particulars.get("contains_floating_charge"),
        parties_entitled=parties,
    )


#: The human-facing find-and-update page for a company's charges tab —
#: mirrors ``registries/gb/mapping.py::_FIND_AND_UPDATE_URL``'s convention
#: (the API host itself is not a page a person can open).
_FIND_AND_UPDATE_CHARGES_URL = (
    "https://find-and-update.company-information.service.gov.uk/company/{id}/charges"
)

_SOURCE = "Companies House (UK)"
_LICENSE = "Crown copyright — Companies House public register, free to re-use"


def map_charges(
    payload: Mapping[str, Any],
    company_number: str,
    *,
    cached: bool,
    fetched_at: datetime,
) -> ChargeList:
    """Pure, synchronous, no I/O — mirrors ``registries/gb/mapping.py``'s
    ``map_entity`` / ``map_search_result`` convention exactly, one level down.

    Args:
        payload: The parsed JSON body of ``GET /company/{n}/charges``.
        company_number: The normalised CRN (``rules.validate_crn``'s
            output), used only to build ``provenance.source_url`` and the
            truncation note — never re-validated here.
        cached: Whether this block is being served from the cache.
        fetched_at: The original fetch time (preserved across cache hits,
            ``DECISIONS.md`` D-006).
    """
    items = payload.get("items") or []
    charges = [_map_one_charge(item) for item in items]
    charges.sort(key=lambda c: (c.created_on or date.min, c.charge_number or 0), reverse=True)

    total_count = payload.get("total_count")
    satisfied_count = payload.get("satisfied_count")
    outstanding_count = (
        total_count - satisfied_count
        if isinstance(total_count, int) and isinstance(satisfied_count, int)
        else None
    )

    notes: list[str] = []
    if isinstance(total_count, int) and total_count > len(charges):
        notes.append(
            f"Companies House lists {total_count} charges for this company; only "
            f"{len(charges)} are included here (one page, the register's own maximum page "
            f"size). See {_FIND_AND_UPDATE_CHARGES_URL.format(id=company_number)} for the rest."
        )

    return ChargeList(
        charges=charges,
        total_count=total_count,
        outstanding_count=outstanding_count,
        satisfied_count=satisfied_count,
        provenance=ChargeProvenance(
            source=_SOURCE,
            source_url=_FIND_AND_UPDATE_CHARGES_URL.format(id=company_number),
            license=_LICENSE,
            fetched_at=fetched_at,
            cached=cached,
        ),
        notes=notes,
    )
