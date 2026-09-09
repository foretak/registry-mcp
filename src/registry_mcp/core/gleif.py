"""GLEIF Level 1 and Level 2 data — the LEI and its corporate parents, the two
attachments every country declares (except Sweden, see below).

``include=["lei"]`` and ``include=["parents"]`` (``DECISIONS.md`` D-026(c),
D-045(e), D-047(a)). Unlike every other attachment, this upstream belongs to
no country: GLEIF publishes every jurisdiction from one endpoint, under one
CC0 licence, with one TTL, so the mechanism lives on ``Registry`` itself
(``core/registry.py``'s ``universal_includes`` / the concrete ``lei()`` and
``parents()`` methods) rather than in three country modules. This module
holds what a country module's own ``client.py`` would otherwise hold — the
HTTP client, the query, the cache read/write and the mapper — one level up,
because the upstream is one level up (``registries/gb/client.py``'s
docstring is the precedent this mirrors).

**The two attachments share one discovery step, never two.** Both start from
the same ``lei-records`` search — :func:`fetch_lei` needs the record it
returns, and :func:`fetch_parents` needs the ``relationships`` object on the
same record. That search is factored into :func:`_fetch_search_payload`,
which both callers await: it reads the ``lei`` cache entry first, then a
per-key in-flight map, so a lookup asking for **both** ``lei`` and
``parents`` makes **exactly one** search request however
``Registry.lookup_with``'s bounded concurrency interleaves the two calls —
the identical hazard D-043(h)(3) named for Norway's ``filings``/``financials``
(``registries/no/client.py``'s ``_fetch_accounts_payload`` is the precedent
this mirrors), arriving here because the two attachments share an upstream
rather than a country module. A lookup asking for only ``parents`` still
populates the ``lei`` cache entry as a side effect — it is the same fetch.

**The query is the one thing D-045(e) measured and warns about.**
``filter[entity.registeredAs]`` is an *exact* match on the string the
national register itself published to GLEIF, not on the identifier this
project normalises to: Norway and Sweden both group their identifiers when
they report to GLEIF (``"923 609 016"``, ``"556016-0680"``), and a bare-digit
query for either returns **zero hits**, which looks exactly like "no LEI".
:func:`fetch_lei` tries the formatted candidate first (``Registry.format_id``,
already on the contract) and falls back to the bare, normalised identifier
only on a zero-hit miss — two requests at most, and the second only on a
miss — and the returned block's ``notes`` always name the string(s) actually
sent, so a miss is legible rather than silent.

**The registration-authority code is asserted, never used as an input.**
``entity.registeredAt.id`` (beside ``entity.registeredAs``) is carried into
the block's ``notes`` so a caller can see which register GLEIF says the
entity is registered in — ``RA000472`` (Foretaksregisteret) for Norway even
though our own lookup reads Enhetsregisteret, ``RA000544`` (Bolagsverket) for
Sweden, and ``RA000585`` / ``RA000586`` / ``RA000587`` (Companies House,
England-and-Wales / Northern-Ireland / Scotland respectively) for Britain —
never used to build the query itself.

**``entity.status`` is never read, anywhere in this module.**
``registration.status`` — the LEI record's own maintenance state,
``ISSUED`` / ``LAPSED`` / … — is what ``LeiRecord.registration_status``
carries. ``entity.status`` is GLEIF's own opinion about whether the
*company* is active, a claim made by neither the company's own register nor
us, and D-045(e) declines it by name. Carillion plc (``03782379``) is the
fixture that proves why: ``entity.status: ACTIVE`` beside
``registration.status: LAPSED``. The same rule extends to the *parent's* own
entity classification for :func:`fetch_parents`: never read.

**Choosing the parent endpoint: read the ``links`` key GLEIF returns, never
construct one.** The search response's ``relationships`` names a
``direct-parent`` and an ``ultimate-parent``, and their ``links`` carry
either a ``reporting-exception`` key (no parent reported — fetch that URL for
the filer's own reason) or a ``lei-record`` key with a ``relationship-record``
beside it (a parent is disclosed — fetch both, concurrently, for the parent's
own Level 1 record and the relationship's corroboration level).
:func:`_fetch_side` always follows the URL GLEIF put in ``links``; it never
builds one from a template, because a hardcoded path works until GLEIF
changes it and the failure looks exactly like "no parent" (D-046(b)'s
reasoning, one register over). So one lookup's fan-out is one extra request
per side on the exception path and two per side on the disclosed-parent
path — 2 total on the common case, 4 on the rare one — run concurrently so
the added latency is one round trip, not four. A leg that fails degrades
only its own side to ``None``, with a ``notes`` sentence naming which one;
only a failure of the shared search itself propagates as
``upstream_error`` (D-042(b),(j)).

**``?include=direct-parent,ultimate-parent`` on the search request is not
used, on purpose.** GLEIF accepts it and returns a JSON:API compound
document, but its ``included`` array carries resource identifier objects
only — ``{"type", "id"}``, no ``attributes`` — so it fetches nothing at all
while looking exactly like it fetched the parent. ``legal_name`` built from
it would be ``None`` forever. See :func:`fetch_parents`'s own docstring
before reaching for it again.

Cache TTL is the per-kind table's first user (``core/cache.py``): both
``lei`` and ``parents`` get 7 days on a hit, 24 hours on an empty result —
not D-006's 24 h / 1 h default, because nothing statutory, time-critical or
credit-bearing turns on an entity acquiring an LEI or disclosing a parent,
and re-asking a free service hourly for an answer that is "no" for most of
the world's companies points the harm the wrong way. ``parents`` is cached
under its own key, ``{COUNTRY}:{registry}:parents:{id}``, holding the whole
composed answer — never a second key per side.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from registry_mcp import __version__
from registry_mcp.core import cache
from registry_mcp.core.models import (
    ErrorCode,
    LeiRecord,
    ParentBlock,
    ParentLink,
    RegistryError,
    SourceRef,
)

__all__ = ["BASE_URL", "aclose", "fetch_lei", "fetch_parents"]

logger = logging.getLogger(__name__)

#: GLEIF's public, keyless Level 1 search — CC0 1.0, no credential, daily
#: golden copy (``DECISIONS.md`` D-026(c)). Level 2 (parent) records live
#: under this same path, one path segment per leg — see :func:`_fetch_side`.
BASE_URL = "https://api.gleif.org/api/v1/lei-records"

_TIMEOUT = httpx.Timeout(5.0)
_RETRY_BACKOFF_SECONDS = 0.25
_MAX_ATTEMPTS = 2  # one try + one retry — the same contract every other client here uses

_LICENSE = "CC0 1.0"
_SOURCE = "GLEIF Level 1 (gleif.org)"
_SOURCE_LEVEL2 = "GLEIF Level 2 (gleif.org)"

_client: httpx.AsyncClient | None = None


def _user_agent() -> str:
    contact = os.environ.get("REGISTRY_MCP_CONTACT_EMAIL", "").strip()
    if not contact:
        contact = "unknown@example.invalid"
        logger.warning("REGISTRY_MCP_CONTACT_EMAIL is not set; using %s", contact)
    return f"registry-mcp/{__version__} (+https://github.com/foretak/registry-mcp; {contact})"


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers={"Accept": "application/vnd.api+json", "User-Agent": _user_agent()},
        )
    return _client


async def aclose() -> None:
    """Close the shared client. Call on application shutdown.

    Nothing in this task's footprint calls this today — ``api/main.py``'s
    shutdown hook closes every *registered country's* ``Registry.aclose()``,
    and GLEIF is not a country. Left here, tested directly, for whichever
    later task wires a shutdown call in (out of this task's footprint per
    ``tasks/T42.md``).
    """
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _upstream_error(detail: str, *, country: str) -> RegistryError:
    return RegistryError(
        ErrorCode.UPSTREAM_ERROR,
        f"GLEIF (api.gleif.org) {detail}",
        hint=(
            "This is a problem with a third-party data source (GLEIF), not a bad "
            "request. Retry the call in a moment, or omit 'lei'/'parents' from include."
        ),
        country=country,
    )


async def _get(url: str, params: dict[str, str] | None, *, country: str) -> dict[str, Any]:
    """One GET against a GLEIF URL, retrying exactly once on a timeout or a
    5xx — never on a 4xx. Keyless: no auth header, ever.

    ``url`` is either :data:`BASE_URL` (the ``lei-records`` search, with
    ``params``) or one of the exact URLs GLEIF puts in a record's ``links``
    (a parent's own record, a relationship record, or a reporting exception
    — ``params=None`` for all three, since the URL is already complete).

    ``country`` is only for the raised error's own ``country`` field
    (D-007) — GLEIF is not scoped to it in any other way here, since either
    ``filter[entity.jurisdiction]`` is already inside ``params`` or ``url``
    is already scoped to one record.
    """
    client = _get_client()
    attempt = 0
    while True:
        attempt += 1
        try:
            response = await client.get(url, params=params)
        except httpx.TimeoutException as exc:
            if attempt >= _MAX_ATTEMPTS:
                raise _upstream_error(
                    "did not respond within the timeout.", country=country
                ) from exc
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        if response.status_code >= 500:
            if attempt >= _MAX_ATTEMPTS:
                raise _upstream_error(f"returned {response.status_code}.", country=country)
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        if response.status_code != 200:
            raise _upstream_error(
                f"returned an unexpected status {response.status_code}.", country=country
            )

        result: dict[str, Any] = response.json()
        return result


def _cache_key(country: str, registry: str, id: str) -> str:
    """``{COUNTRY}:{registry}:lei:{id}`` — D-006's convention, ``lei`` in the
    kind slot so ``core/cache.py``'s per-kind TTL table finds it. Keyed by
    the *calling* country/registry (not just the bare id) so an identifier
    that happened to collide across two countries' schemes never shares a
    cache row — belt and braces beside ``filter[entity.jurisdiction]``
    already doing the same job on the wire.
    """
    return f"{country}:{registry}:lei:{id}"


def _parents_cache_key(country: str, registry: str, id: str) -> str:
    """``{COUNTRY}:{registry}:parents:{id}`` — one key for the whole
    composed answer (both sides, D-047(a)), never a second key per side. A
    different kind slot from :func:`_cache_key`'s ``lei``, so ``core/cache.py``'s
    per-kind TTL table (which reads the same 7-day / 24-hour pair for both
    kinds) treats the two as independent entries that can age apart, exactly
    as the ``lei`` and ``parents`` attachments are independent requests.
    """
    return f"{country}:{registry}:parents:{id}"


def _pagination_total(response: Mapping[str, Any]) -> int:
    total = response.get("meta", {}).get("pagination", {}).get("total")
    return int(total) if isinstance(total, int) else 0


def _queried_note(queried: list[str]) -> str:
    if len(queried) == 1:
        return f"Queried GLEIF's entity.registeredAs filter as {queried[0]!r}."
    tried = " and then as ".join(repr(q) for q in queried)
    return (
        f"Queried GLEIF's entity.registeredAs filter as {tried} — the first form "
        "returned no match, so the bare identifier was tried next."
    )


def _map_lei(payload: Mapping[str, Any], *, cached: bool, fetched_at: datetime) -> LeiRecord:
    """Pure, synchronous, no I/O — mirrors ``registries/gb/charges.py``'s
    ``map_charges`` convention. ``payload`` is this module's own cache
    shape, ``{"queried": [...], "response": <raw GLEIF body>}``, not GLEIF's
    wire shape directly — see :func:`fetch_lei`.

    Never reads ``entity.status`` (D-045(e)): only ``registration.status``.
    """
    queried: list[str] = list(payload.get("queried") or [])
    response: Mapping[str, Any] = payload.get("response") or {}
    records: list[Mapping[str, Any]] = list(response.get("data") or [])

    notes: list[str] = [_queried_note(queried)]

    if not records:
        return LeiRecord(
            lei=None,
            legal_name=None,
            registration_status=None,
            provenance=SourceRef(
                source=_SOURCE,
                source_url=None,
                license=_LICENSE,
                fetched_at=fetched_at,
                cached=cached,
            ),
            notes=notes,
        )

    first = records[0]
    attributes: Mapping[str, Any] = first.get("attributes") or {}
    entity: Mapping[str, Any] = attributes.get("entity") or {}
    registration: Mapping[str, Any] = attributes.get("registration") or {}
    legal_name_block: Mapping[str, Any] = entity.get("legalName") or {}
    registered_at: Mapping[str, Any] = entity.get("registeredAt") or {}
    links: Mapping[str, Any] = first.get("links") or {}

    lei_value = attributes.get("lei")
    legal_name = legal_name_block.get("name")
    registration_status = registration.get("status")
    ra_id = registered_at.get("id")
    registered_as = entity.get("registeredAs")
    source_url = links.get("self")

    if ra_id or registered_as:
        where = f" as {registered_as!r}" if registered_as else ""
        notes.append(
            f"GLEIF cites registration authority {ra_id or '(unspecified)'} for this "
            f"entity{where}."
        )

    if len(records) > 1:
        other_leis = [
            str((r.get("attributes") or {}).get("lei")) for r in records[1:] if isinstance(r, Mapping)
        ]
        notes.append(
            f"GLEIF returned {len(records)} records for this registration number, not one. "
            f"Showing the first ({lei_value}). The others: {', '.join(other_leis)}."
        )

    return LeiRecord(
        lei=lei_value,
        legal_name=legal_name,
        registration_status=registration_status,
        provenance=SourceRef(
            source=_SOURCE,
            source_url=source_url,
            license=_LICENSE,
            fetched_at=fetched_at,
            cached=cached,
        ),
        notes=notes,
    )


#: One upstream search in flight per cold cache key, so that :func:`fetch_lei`
#: and :func:`fetch_parents` called concurrently for the same entity share it
#: rather than racing to make two (``DECISIONS.md`` D-047(a), D-043(h)(3)'s
#: hazard in a new place): ``core/registry.py::lookup_with`` runs every
#: requested attachment with bounded concurrency, so
#: ``include=["lei", "parents"]`` calls both ``Registry`` methods before
#: either's fetch can complete on a cold cache. Populated and drained only by
#: :func:`_fetch_search_payload`, below — nothing else touches it.
#:
#: **Why no lock is needed** (``registries/no/client.py``'s
#: ``_inflight_accounts_fetch`` is the precedent this mirrors, word for
#: word): between checking the cache and registering the task here there is
#: no ``await`` at all, so this whole sequence is one uninterruptible step
#: from the event loop's point of view — whichever of the two coroutines
#: reaches :func:`_fetch_search_payload` first always finishes registering
#: its task in this map before the other gets a turn, because Python's
#: cooperative scheduling only switches coroutines at a genuine suspension.
_inflight_search: dict[str, asyncio.Task[tuple[dict[str, Any], datetime]]] = {}


async def _do_fetch_search(
    country: str, id: str, formatted: str | None, key: str
) -> tuple[dict[str, Any], datetime]:
    """The search itself — everything :func:`fetch_lei` did before D-047(a),
    unchanged, including the cache write. Run at most once per cold cache
    key: :func:`_fetch_search_payload` is the only caller, and it never
    starts a second one while this one is in flight.

    Tries ``formatted`` first when it is not ``None`` and differs from
    ``id`` — GLEIF's ``entity.registeredAs`` is an exact match on what the
    national register wrote, and Norway/Sweden group theirs when reporting
    to GLEIF — and falls back to the bare ``id`` only on a zero-hit miss. At
    most two upstream requests, the second only on a miss.

    Returns ``(cache_payload, fetched_at)`` — a fresh fetch is never itself
    a cache hit, whichever of :func:`fetch_lei` / :func:`fetch_parents`
    happened to trigger it.
    """
    candidates: list[str] = []
    if formatted and formatted != id:
        candidates.append(formatted)
    candidates.append(id)

    queried: list[str] = []
    response: dict[str, Any] = {}
    for candidate in candidates:
        queried.append(candidate)
        response = await _get(
            BASE_URL,
            {
                "filter[entity.jurisdiction]": country,
                "filter[entity.registeredAs]": candidate,
            },
            country=country,
        )
        if _pagination_total(response):
            break

    fetched_at = datetime.now(UTC)
    cache_payload = {"queried": queried, "response": response}
    status = "ok" if _pagination_total(response) else "not_found"
    cache.set(key, cache_payload, status=status, fetched_at=fetched_at)
    return cache_payload, fetched_at


async def _fetch_search_payload(
    country: str, registry: str, id: str, formatted: str | None
) -> tuple[dict[str, Any], bool, datetime]:
    """The search payload behind **both** :func:`fetch_lei` and
    :func:`fetch_parents` — one cache entry (``{COUNTRY}:{registry}:lei:{id}``),
    one in-flight upstream call, shared regardless of which of the two
    callers arrives first (D-047(a)).

    Returns ``(payload, cached, fetched_at)``: ``payload`` is this module's
    own cache shape, ``{"queried": [...], "response": <raw GLEIF body>}``,
    never GLEIF's wire shape directly. A lookup requesting both attachments
    on a cold cache makes **exactly one** search request; reversing this
    sharing (each attachment calling :func:`_do_fetch_search` on its own)
    is the naive implementation D-047(a) names, and it makes two.
    """
    key = _cache_key(country, registry, id)

    entry = cache.get(key)
    if entry is not None:
        return entry.payload, True, entry.fetched_at

    existing = _inflight_search.get(key)
    if existing is not None:
        payload, fetched_at = await existing
        return payload, False, fetched_at

    task = asyncio.ensure_future(_do_fetch_search(country, id, formatted, key))
    _inflight_search[key] = task
    try:
        payload, fetched_at = await task
        return payload, False, fetched_at
    finally:
        _inflight_search.pop(key, None)


async def fetch_lei(country: str, registry: str, id: str, formatted: str | None) -> LeiRecord:
    """Fetch (or serve from cache) the LEI record for one entity.

    Args:
        country: ``Registry.country`` of the caller — GLEIF's
            ``filter[entity.jurisdiction]``.
        registry: ``Registry.registry`` of the caller — only used to build
            the cache key.
        id: the already-normalised identifier (``Registry.validate_id``'s
            output).
        formatted: ``Registry.format_id(id)`` for the same identifier, or
            ``None`` when the country has no local grouping convention
            (Britain does not override ``format_id``).

    Delegates the search itself to :func:`_fetch_search_payload`, shared
    with :func:`fetch_parents` — see that function's docstring for the
    fallback cascade and the in-flight sharing. The cache holds the combined
    answer (which string(s) were queried, and the winning raw response)
    under one key, so a cache hit never re-queries and the ``notes``
    sentence naming the query string survives a cache hit too.

    Raises:
        RegistryError: ``upstream_error`` on any transport failure, timeout
            or non-200 (never raised for a *successful*, zero-hit search —
            that is a present block with ``lei=None``, not a failure).
    """
    payload, cached, fetched_at = await _fetch_search_payload(country, registry, id, formatted)
    return _map_lei(payload, cached=cached, fetched_at=fetched_at)


# ---------------------------------------------------------------------------
# Level 2 — corporate parents (``include=["parents"]``, D-047(a))
# ---------------------------------------------------------------------------

#: GLEIF's closed reporting-exception vocabulary is relayed verbatim in
#: ``ParentLink.reporting_exception`` and is never read here as anything
#: other than a string — no branch in this module treats one exception
#: reason differently from another. Kept as a comment, not a table, on
#: purpose: a lookup table over a closed enum an implementer might be
#: tempted to validate against is exactly the kind of extra mechanism
#: D-042(g) exists to refuse for a value the wire already constrains.

_EXCEPTION_CAVEAT = (
    "is the entity's own stated reason for not reporting a parent, not verified by "
    "GLEIF or by us, and is not applied consistently between filers — see "
    "`ParentLink.reporting_exception`'s own description before treating it as a fact "
    "about who controls this entity."
)


async def _fetch_side(
    side: str, relationship: Mapping[str, Any], *, country: str
) -> tuple[ParentLink | None, list[str]]:
    """Resolve one side (``"direct"`` or ``"ultimate"``) of a ``ParentBlock``
    from the search response's own ``relationships["{side}-parent"]``.

    **Reads the URL GLEIF put in ``links``; never constructs one** (D-047(a),
    D-046(b)'s reasoning one register over — a hardcoded path works until it
    does not, and the failure looks exactly like "no parent"). The two link
    keys are the discriminator:

    * ``reporting-exception`` present → GET that URL → ``attributes.reason``
      is the whole of what is read; ``attributes.reference`` (the filer's own
      free-text justification, up to 500 characters, null on 117 of 117
      fetched) is never read, never mapped and never relayed (D-042(e)).
    * ``lei-record`` present (with ``relationship-record`` beside it) → GET
      both, concurrently → the parent's own Level 1 record fills ``lei``,
      ``legal_name``, ``jurisdiction``, ``registration_status``; the
      relationship record's own corroboration level fills
      ``corroboration_level``, and its ``RELATIONSHIP_PERIOD`` start date (if
      any) is named in a returned note — the one thing lost by not modelling
      the relationship's period history at all.
    * neither key present (0 of 1,800 records sampled) → ``None`` with a note.

    **A failed leg degrades only this side, never the whole block** (C5):
    any :class:`RegistryError` raised while resolving this side is caught
    here and turned into ``(None, [note naming the leg])`` rather than
    propagating — propagating would fail :func:`fetch_parents` entirely for
    a fetch that only ever touches one side. Only :func:`_fetch_search_payload`
    failing (the shared discovery step) is allowed to propagate.

    Returns ``(link, notes)`` — ``notes`` is appended to the whole block's
    ``notes``, not just this side's.
    """
    links: Mapping[str, Any] = relationship.get("links") or {}
    exception_url = links.get("reporting-exception")
    lei_record_url = links.get("lei-record")
    relationship_record_url = links.get("relationship-record")

    if exception_url:
        try:
            body = await _get(exception_url, None, country=country)
        except RegistryError as exc:
            return None, [
                f"Could not fetch GLEIF's {side} parent reporting exception for this "
                f"entity: {exc.message}"
            ]
        attributes: Mapping[str, Any] = (body.get("data") or {}).get("attributes") or {}
        reason = attributes.get("reason")
        link = ParentLink(reporting_exception=reason, source_url=exception_url)
        notes = [f"GLEIF's {side} parent for this entity is a reporting exception, "
                 f"{reason!r} — this {_EXCEPTION_CAVEAT}"]
        return link, notes

    if lei_record_url:
        lei_task = asyncio.ensure_future(_get(lei_record_url, None, country=country))
        rel_task = (
            asyncio.ensure_future(_get(relationship_record_url, None, country=country))
            if relationship_record_url
            else None
        )
        try:
            lei_body = await lei_task
            rel_body = await rel_task if rel_task is not None else None
        except RegistryError as exc:
            if rel_task is not None and not rel_task.done():
                rel_task.cancel()
            return None, [
                f"Could not fetch GLEIF's {side} parent's own record for this entity: "
                f"{exc.message}"
            ]

        attributes = (lei_body.get("data") or {}).get("attributes") or {}
        entity: Mapping[str, Any] = attributes.get("entity") or {}
        legal_name_block: Mapping[str, Any] = entity.get("legalName") or {}
        registration: Mapping[str, Any] = attributes.get("registration") or {}

        corroboration_level = None
        parent_notes: list[str] = []
        if rel_body is not None:
            rel_attributes: Mapping[str, Any] = (rel_body.get("data") or {}).get("attributes") or {}
            rel_registration: Mapping[str, Any] = rel_attributes.get("registration") or {}
            corroboration_level = rel_registration.get("corroborationLevel")
            periods: list[Mapping[str, Any]] = list(
                (rel_attributes.get("relationship") or {}).get("periods") or []
            )
            for period in periods:
                start_date = period.get("startDate")
                if period.get("type") == "RELATIONSHIP_PERIOD" and start_date:
                    parent_notes.append(
                        f"GLEIF's {side} parent relationship has been in effect since "
                        f"{str(start_date)[:10]}; the relationship's own period history "
                        "beyond that single date is not modelled."
                    )
                    break

        link = ParentLink(
            lei=attributes.get("lei"),
            legal_name=legal_name_block.get("name"),
            jurisdiction=entity.get("jurisdiction"),
            registration_status=registration.get("status"),
            corroboration_level=corroboration_level,
            source_url=lei_record_url,
        )
        return link, parent_notes

    return None, [
        f"GLEIF's relationships for this entity name neither a disclosed parent nor "
        f"a reporting exception on the {side} side."
    ]


def _map_parents(payload: Mapping[str, Any], *, cached: bool, fetched_at: datetime) -> ParentBlock:
    """Pure, synchronous, no I/O — mirrors :func:`_map_lei`. ``payload`` is
    this module's own cache shape for the composed answer,
    ``{"lei": ..., "direct": {...} | None, "ultimate": {...} | None, "notes": [...]}``,
    built once by :func:`fetch_parents` and replayed unchanged on a cache
    hit, so a hit never re-derives anything.
    """
    lei_value = payload.get("lei")
    direct_raw = payload.get("direct")
    ultimate_raw = payload.get("ultimate")
    source_url = f"{BASE_URL}/{lei_value}" if lei_value else None

    return ParentBlock(
        direct=ParentLink.model_validate(direct_raw) if direct_raw else None,
        ultimate=ParentLink.model_validate(ultimate_raw) if ultimate_raw else None,
        provenance=SourceRef(
            source=_SOURCE_LEVEL2,
            source_url=source_url,
            license=_LICENSE,
            fetched_at=fetched_at,
            cached=cached,
        ),
        notes=list(payload.get("notes") or []),
    )


async def fetch_parents(country: str, registry: str, id: str, formatted: str | None) -> ParentBlock:
    """Fetch (or serve from cache) the corporate-parents block for one entity.

    Args:
        country: ``Registry.country`` of the caller.
        registry: ``Registry.registry`` of the caller — only used to build
            the cache key.
        id: the already-normalised identifier.
        formatted: ``Registry.format_id(id)`` for the same identifier — see
            :func:`fetch_lei`.

    **Shares the discovery search with :func:`fetch_lei`, never repeats
    it.** The composed answer is cached separately, under
    ``{COUNTRY}:{registry}:parents:{id}`` (:func:`_parents_cache_key`) — one
    key for the whole fan-out, never a second key per side — but the search
    that discovers the entity's LEI and its ``relationships`` object is the
    exact same call :func:`fetch_lei` makes, through the exact same
    :func:`_fetch_search_payload`. A lookup asking for both ``lei`` and
    ``parents`` therefore makes **exactly one** ``lei-records`` search
    request; a lookup asking for only ``parents`` still populates the
    ``lei`` cache entry as a side effect, because it is the same fetch.

    Three shapes of answer, all *present* blocks (D-011):

    * GLEIF holds **no LEI** for this entity at all (``total == 0`` on the
      search) → ``direct=None``, ``ultimate=None``, a note saying GLEIF
      holds no LEI so there is no Level 2 either. This is the answer, not
      an absence — GLEIF cannot hold Level 2 relationship data for an
      entity it has no Level 1 record for.
    * GLEIF holds an LEI, and each side resolves independently through
      :func:`_fetch_side` — disclosed, excepted, or (0 of 1,800 sampled)
      neither.
    * A failed leg degrades that one side to ``None`` with a note; the
      block itself is still present and the fetch as a whole still
      succeeds.

    Raises:
        RegistryError: ``upstream_error`` only when the shared discovery
            search itself fails — never for a failure confined to one
            side's own leg, which :func:`_fetch_side` already turned into a
            degraded ``None`` plus a note. :meth:`Registry.lookup_with`
            turns a propagated error into an absent block plus a
            report-level note rather than failing the whole lookup
            (D-042(b)).
    """
    key = _parents_cache_key(country, registry, id)
    entry = cache.get(key)
    if entry is not None:
        return _map_parents(entry.payload, cached=True, fetched_at=entry.fetched_at)

    search_payload, _search_cached, _search_fetched_at = await _fetch_search_payload(
        country, registry, id, formatted
    )
    queried: list[str] = list(search_payload.get("queried") or [])
    response: Mapping[str, Any] = search_payload.get("response") or {}
    records: list[Mapping[str, Any]] = list(response.get("data") or [])

    if not records:
        fetched_at = datetime.now(UTC)
        cache_payload: dict[str, Any] = {
            "lei": None,
            "direct": None,
            "ultimate": None,
            "notes": [
                f"{_queried_note(queried)} GLEIF holds no LEI for this entity, so "
                "there is no Level 2 relationship data to report either."
            ],
        }
        cache.set(key, cache_payload, status="not_found", fetched_at=fetched_at)
        return _map_parents(cache_payload, cached=False, fetched_at=fetched_at)

    record = records[0]
    attributes: Mapping[str, Any] = record.get("attributes") or {}
    lei_value = attributes.get("lei")
    relationships: Mapping[str, Any] = record.get("relationships") or {}

    (direct_link, direct_notes), (ultimate_link, ultimate_notes) = await asyncio.gather(
        _fetch_side("direct", relationships.get("direct-parent") or {}, country=country),
        _fetch_side("ultimate", relationships.get("ultimate-parent") or {}, country=country),
    )

    fetched_at = datetime.now(UTC)
    cache_payload = {
        "lei": lei_value,
        "direct": direct_link.model_dump(mode="json") if direct_link else None,
        "ultimate": ultimate_link.model_dump(mode="json") if ultimate_link else None,
        "notes": [*direct_notes, *ultimate_notes],
    }
    cache.set(key, cache_payload, status="ok", fetched_at=fetched_at)
    return _map_parents(cache_payload, cached=False, fetched_at=fetched_at)
