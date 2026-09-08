"""GB charges — ``GET /company/{n}/charges`` (Companies House).

**R-5c / T37**, Part B (``DECISIONS.md`` D-042). This module maps the wire
straight onto the canonical :class:`~registry_mcp.core.models.Charge` /
:class:`~registry_mcp.core.models.ChargeBlock` /
:class:`~registry_mcp.core.models.SourceRef`. **The field list below is not
a ruled shape** — no charge field name appears anywhere in ``DECISIONS.md``.
It is shaped by D-042(g)'s anti-bend rule (a shared attachment model's field
names are country-neutral, and a field only one register can plausibly ever
fill says so in its own description) and D-042(j)'s truncation and
derived-flag rules, and it is this module's own proposal, pending the
architect's ruling (D-045, pending). There is no local stand-in and nothing
to convert: :func:`map_charges` constructs the canonical classes directly,
and ``CompaniesHouseRegistry.charges`` (``registries/gb/__init__.py``)
returns :func:`registry_mcp.registries.gb.client.fetch_charges`'s result
unchanged.

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
  ``"fully-satisfied"`` were observed, across all 110 items on the four
  committed fixtures (Tesco/``00445790``, NatWest Markets/``SC090312`` at
  its full 137-charge, 100-item page, Deloitte LLP/``OC303675`` and the
  dissolved Marine and General Mutual Life Assurance Society/``00000006``)
  — including the 137-charge bank, whose own ``part_satisfied_count`` was 0.
  :data:`_OUTSTANDING_BY_STATUS` therefore has exactly those two keys. Per
  D-042(j) / D-025(d) / D-011: a status word the table does not contain
  (``"part-satisfied"`` included) yields ``Charge.is_outstanding = None``,
  never a guess — add the word once a live payload confirms the exact
  string Companies House sends for it.
* **No natural person's name observed** among the same four fixtures' 110
  ``persons_entitled[].name`` values (68 distinct) — every one is a bank,
  insurer, fund, trustee company or similar institution (e.g. "Citibank,
  N.A., in Its Capacity as Collateral Agent", "Tesco Trustee Company of
  Ireland Limited as Trustee of the Tesco Ireland Limited Senior Executive
  Pension Scheme"). ``parties_entitled`` is kept (renamed from
  ``persons_entitled``, D-042(e)(3)) rather than dropped, because a security
  holder's identity is the one thing a charges credit-check cannot do
  without. **Reported tension, not resolved unilaterally**: this task's own
  Part A framing said "if any field names a natural person, it is barred by
  D-028 and must be dropped, exactly as filing history's ``officer_name``
  is" — which is *not* what D-042(e)(3) actually rules for this specific
  field (officer_name is barred outright; persons_entitled is relayed,
  renamed, and bound by D-028(1), because D-042 judged the minimisation
  sufficient and the use case unanswerable without it). This module follows
  D-042 — the fuller, reasoned, dated ruling this task told its implementer
  to read in full — over the shorter paraphrase in its own brief, and says
  so here for the orchestrator to double-check.
* **Two fields observed live that are not in this module's field list**:
  ``particulars.contains_fixed_charge`` (a sibling of
  ``contains_floating_charge`` and ``contains_negative_pledge``) and a
  ``charge_code`` absent on roughly a quarter of items (pre-2013 filings,
  before Companies House assigned it retrospectively) — mapped to
  ``charge_id`` when present, honestly ``None`` when not, per D-009. Neither
  is added to the model here: D-042(g)'s anti-bend rule reserves that for an
  entry in ``DECISIONS.md``, not an implementer's judgement call.

Two arithmetic choices this module makes that are not spelled out in any
ruling, flagged for the architect rather than decided quietly:

* ``ChargeBlock.outstanding_count`` is derived as ``total_count -
  satisfied_count`` (both register-published whole-dataset integers,
  identical in kind to how ``registries/gb/mapping.py::map_search_result``
  derives ``truncated`` from ``total_results`` and ``len(hits)`` — arithmetic
  on published facts, not a guess). Companies House also publishes
  ``part_satisfied_count``, which this module's field list has no place
  for; it was 0 in every payload this recon saw, so the choice is untested
  in practice, but the honest reading is that a part-satisfied charge is
  still counted here as "not fully satisfied", i.e. within
  ``outstanding_count``. A future ruling may want its own
  ``part_satisfied_count`` field — this module cannot add it (D-042(g)).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from registry_mcp.core.models import Charge, ChargeBlock, SourceRef

__all__ = [
    "CHARGES_ITEMS_PER_PAGE",
    "Charge",
    "ChargeBlock",
    "map_charges",
]


# ---------------------------------------------------------------------------
# Status vocabulary -> is_outstanding (D-042(j), D-025(d), D-011): derived by
# membership of a table of words this module has actually seen on the wire.
# A status word not in this table yields `None`, never `False`. Confirmed
# live 2026-09-08 across all 110 charges on the four committed fixtures
# (Tesco/00445790, 00000006, NatWest Markets/SC090312 at its full 137-charge,
# 100-item page, and Deloitte LLP/OC303675, which has none): only
# "outstanding" and "fully-satisfied" were ever seen.
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
) -> ChargeBlock:
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

    return ChargeBlock(
        charges=charges,
        total_count=total_count,
        outstanding_count=outstanding_count,
        satisfied_count=satisfied_count,
        provenance=SourceRef(
            source=_SOURCE,
            source_url=_FIND_AND_UPDATE_CHARGES_URL.format(id=company_number),
            license=_LICENSE,
            fetched_at=fetched_at,
            cached=cached,
        ),
        notes=notes,
    )
