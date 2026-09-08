"""GLEIF Level 1 data — the LEI, the first attachment every country declares.

``include=["lei"]`` (``DECISIONS.md`` D-026(c), D-045(e)). Unlike every other
attachment, this upstream belongs to no country: GLEIF publishes every
jurisdiction from one endpoint, under one CC0 licence, with one TTL, so the
mechanism lives on ``Registry`` itself (``core/registry.py``'s
``universal_includes`` / the concrete ``lei()`` method) rather than in three
country modules. This module holds what a country module's own ``client.py``
would otherwise hold — the HTTP client, the query, the cache read/write and
the mapper — one level up, because the upstream is one level up
(``registries/gb/client.py``'s docstring is the precedent this mirrors).

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
``registration.status: LAPSED``.

Cache TTL is the per-kind table's first user (``core/cache.py``): 7 days on a
hit, 24 hours on an empty result — not D-006's 24 h / 1 h default, because
nothing statutory, time-critical or credit-bearing turns on an entity
acquiring an LEI, and re-asking a free service hourly for an answer that is
"no" for most of the world's companies points the harm the wrong way.
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
from registry_mcp.core.models import ErrorCode, LeiRecord, RegistryError, SourceRef

__all__ = ["BASE_URL", "aclose", "fetch_lei"]

logger = logging.getLogger(__name__)

#: GLEIF's public, keyless Level 1 search — CC0 1.0, no credential, daily
#: golden copy (``DECISIONS.md`` D-026(c)).
BASE_URL = "https://api.gleif.org/api/v1/lei-records"

_TIMEOUT = httpx.Timeout(5.0)
_RETRY_BACKOFF_SECONDS = 0.25
_MAX_ATTEMPTS = 2  # one try + one retry — the same contract every other client here uses

_LICENSE = "CC0 1.0"
_SOURCE = "GLEIF Level 1 (gleif.org)"

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
            "request. Retry the call in a moment, or omit 'lei' from include."
        ),
        country=country,
    )


async def _get(params: dict[str, str], *, country: str) -> dict[str, Any]:
    """One GET against GLEIF's ``lei-records`` search, retrying exactly once
    on a timeout or a 5xx — never on a 4xx. Keyless: no auth header, ever.

    ``country`` is only for the raised error's own ``country`` field
    (D-007) — GLEIF is not scoped to it in any other way here, since
    ``filter[entity.jurisdiction]`` is already inside ``params``.
    """
    client = _get_client()
    attempt = 0
    while True:
        attempt += 1
        try:
            response = await client.get(BASE_URL, params=params)
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

    Tries ``formatted`` first when it is not ``None`` and differs from
    ``id`` — GLEIF's ``entity.registeredAs`` is an exact match on what the
    national register wrote, and Norway/Sweden group theirs when reporting
    to GLEIF — and falls back to the bare ``id`` only on a zero-hit miss. At
    most two upstream requests, the second only on a miss. The cache holds
    the combined answer (which string(s) were queried, and the winning raw
    response) under one key, so a cache hit never re-queries and the
    ``notes`` sentence naming the query string survives a cache hit too.

    Raises:
        RegistryError: ``upstream_error`` on any transport failure, timeout
            or non-200 (never raised for a *successful*, zero-hit search —
            that is a present block with ``lei=None``, not a failure).
    """
    key = _cache_key(country, registry, id)
    entry = cache.get(key)
    if entry is not None:
        return _map_lei(entry.payload, cached=True, fetched_at=entry.fetched_at)

    candidates: list[str] = []
    if formatted and formatted != id:
        candidates.append(formatted)
    candidates.append(id)

    queried: list[str] = []
    response: dict[str, Any] = {}
    for candidate in candidates:
        queried.append(candidate)
        response = await _get(
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
    return _map_lei(cache_payload, cached=False, fetched_at=fetched_at)
