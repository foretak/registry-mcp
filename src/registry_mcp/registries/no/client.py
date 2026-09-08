"""HTTP client for Enhetsregisteret (data.brreg.no). See ``NORBIZ_SPEC.md`` §§1, 6.

Behaviour, exactly:

* Base URL ``https://data.brreg.no/enhetsregisteret/api``, 5 s timeout per
  attempt, one retry on a timeout or a 5xx (never a 4xx), 250 ms backoff.
* One module-level ``httpx.AsyncClient``, created lazily, closed by
  :func:`aclose`.
* ``User-Agent: registry-mcp/{version} (+https://github.com/foretak/registry-mcp;
  {contact})`` where ``contact`` is ``REGISTRY_MCP_CONTACT_EMAIL`` (default
  ``"unknown@example.invalid"``, logged as a warning).
* A 404 from ``/enheter`` is retried once against ``/underenheter`` (branches);
  a 404 from both is ``not_found``.
* A 410 (or the confirmed live shape: a 200 body carrying ``slettedato``) maps
  to a deleted entity. See ``NORBIZ_SPEC.md`` §1.1 for what was actually
  observed live on 2026-09-03.

R-5d adds one more call to a **different dataset on the same host**:
:func:`fetch_accounts` reads ``data.brreg.no/regnskapsregisteret/regnskap/
{orgnr}`` — open, keyless, and mapped by ``registries/no/accounts.py``. It
reuses :func:`_fetch`'s timeout, retry, User-Agent and connection pool by
passing an absolute URL (``httpx`` leaves an absolute URL alone when a
``base_url`` is set), and carries its own cache key and its own provenance,
because two round trips have two moments and two failure modes
(``DECISIONS.md`` D-041(c)).

D-043 (T38, ``R-5f``) adds :func:`fetch_financials` beside it, reading **the
same URL, the same cache entry and the same upstream call** as
:func:`fetch_accounts` — ``filings`` and ``financials`` are one fetch
producing two blocks, not two fetches (D-043(h)). ``core/registry.py::
lookup_with`` runs every requested attachment concurrently (D-042(b)), so the
two must not race into two upstream requests on a cold cache: both are thin
wrappers over :func:`_fetch_accounts_payload`, which is the single point
that reads the cache, and — on a miss — the single point that starts the
upstream fetch, sharing one ``asyncio.Task`` between however many callers
arrive before it finishes (an in-flight map, not a lock; see that function's
docstring for why no lock is needed).

Rules (MOD11 validation, deadlines) live in ``registries/no/rules.py``, owned
by T02 and built in parallel with this file. Every use of it here is a lazy,
function-local import so importing this module — and running the respx-mocked
HTTP tests — never depends on ``rules.py`` existing yet.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx

from registry_mcp import __version__
from registry_mcp.core import cache
from registry_mcp.core.models import (
    CompanyReport,
    ErrorCode,
    FilingHistory,
    FinancialSummary,
    RegistryError,
    SearchResult,
)
from registry_mcp.registries.no import accounts, mapping

__all__ = ["aclose", "fetch_accounts", "fetch_financials", "lookup", "search"]

logger = logging.getLogger(__name__)

BASE_URL = "https://data.brreg.no/enhetsregisteret/api"
_TIMEOUT = httpx.Timeout(5.0)
_RETRY_BACKOFF_SECONDS = 0.25
_MAX_ATTEMPTS = 2  # one try + one retry

_client: httpx.AsyncClient | None = None


def _validate_orgnr(id: str) -> str:
    """Lazy hand-off to T02's ``registries/no/rules.py::validate_orgnr``."""
    from registry_mcp.registries.no import rules

    result: str = rules.validate_orgnr(id)
    return result


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
            base_url=BASE_URL,
            timeout=_TIMEOUT,
            headers={"Accept": "application/json", "User-Agent": _user_agent()},
        )
    return _client


async def aclose() -> None:
    """Close the shared client. Call on application shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _fetch(path: str, *, params: dict[str, Any] | None = None) -> httpx.Response:
    """GET ``path``, retrying exactly once on a timeout or a 5xx. Never on a 4xx."""
    client = _get_client()
    attempt = 0
    while True:
        attempt += 1
        try:
            response = await client.get(path, params=params)
        except httpx.TimeoutException as exc:
            if attempt >= _MAX_ATTEMPTS:
                raise RegistryError(
                    ErrorCode.UPSTREAM_TIMEOUT,
                    f"Brønnøysundregistrene did not respond within the timeout for {path}.",
                    hint=(
                        "The upstream API timed out twice. Retry the call in a moment; if it "
                        "keeps timing out, the upstream API may be degraded."
                    ),
                    country="NO",
                    registry="brreg",
                ) from exc
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        if response.status_code >= 500:
            if attempt >= _MAX_ATTEMPTS:
                raise RegistryError(
                    ErrorCode.UPSTREAM_ERROR,
                    f"Brønnøysundregistrene returned {response.status_code} for {path}.",
                    hint=(
                        "This is an upstream problem, not a bad request. Retry the call "
                        "in a moment."
                    ),
                    country="NO",
                    registry="brreg",
                )
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        return response


def _not_found_error(orgnr: str) -> RegistryError:
    # N2 (T10 review): `hint` must not repeat `message` — it carries only the
    # next action, since `message` already said what went wrong.
    hint = (
        "The number is well-formed, so it may never have been issued or the entity may "
        "have been deleted. Call search_company with the company name instead."
    )
    return RegistryError(
        ErrorCode.NOT_FOUND,
        f"No entity with organisasjonsnummer {orgnr} exists in Enhetsregisteret.",
        hint=hint,
        country="NO",
        registry="brreg",
    )


def _deleted_error(response: httpx.Response) -> RegistryError:
    """A 410 Gone. Defensive: live testing (2026-09-03) found deleted entities
    answer 200 with `slettedato` instead — see `NORBIZ_SPEC.md` §1.1 — but this
    path is kept for records outside the API's retention window."""
    details: dict[str, Any] = {"deleted": True}
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and body.get("slettedato"):
        details["slettedato"] = body["slettedato"]
    return RegistryError(
        ErrorCode.NOT_FOUND,
        "This entity has been deleted from Enhetsregisteret.",
        hint=(
            "The identifier was valid but the entity is deleted. Call search_company with "
            "the company name to find a currently active entity."
        ),
        country="NO",
        registry="brreg",
        details=details,
    )


def _rate_limited_error() -> RegistryError:
    # DECISIONS.md D-019: rate_limited (429), not upstream_error (502) — the
    # register is not broken, it will succeed shortly, and only the former
    # tells an agent that.
    return RegistryError(
        ErrorCode.RATE_LIMITED,
        "Brønnøysundregistrene rate-limited this request (429).",
        hint="Wait about a minute, then retry the same call.",
        country="NO",
        registry="brreg",
    )


def _upstream_error(response: httpx.Response) -> RegistryError:
    return RegistryError(
        ErrorCode.UPSTREAM_ERROR,
        f"Brønnøysundregistrene returned an unexpected status {response.status_code}.",
        hint="This is an upstream problem, not a bad request. Retry the call in a moment.",
        country="NO",
        registry="brreg",
    )


async def lookup(id: str) -> CompanyReport:
    """Fetch one entity, consulting the cache first (`NORBIZ_SPEC.md` §§2, 9)."""
    orgnr = _validate_orgnr(id)
    cache_key = f"NO:brreg:entity:{orgnr}"

    entry = cache.get(cache_key)
    if entry is not None:
        if entry.status == "not_found":
            raise _not_found_error(orgnr)
        report = CompanyReport.model_validate(entry.payload)
        return report.model_copy(update={"cached": True, "fetched_at": entry.fetched_at})

    is_subunit = False
    path = f"/enheter/{orgnr}"
    response = await _fetch(path)

    if response.status_code == 404:
        sub_path = f"/underenheter/{orgnr}"
        sub_response = await _fetch(sub_path)
        if sub_response.status_code == 200:
            data = sub_response.json()
            is_subunit = True
            source_url = f"{BASE_URL}{sub_path}"
        elif sub_response.status_code == 404:
            cache.set(cache_key, {}, status="not_found")
            raise _not_found_error(orgnr)
        elif sub_response.status_code == 410:
            raise _deleted_error(sub_response)
        elif sub_response.status_code == 429:
            raise _rate_limited_error()
        else:
            raise _upstream_error(sub_response)
    elif response.status_code == 200:
        data = response.json()
        source_url = f"{BASE_URL}{path}"
    elif response.status_code == 410:
        raise _deleted_error(response)
    elif response.status_code == 429:
        raise _rate_limited_error()
    else:
        raise _upstream_error(response)

    fetched_at = datetime.now(UTC)
    report = mapping.map_entity(
        data,
        source_url=source_url,
        is_subunit=is_subunit,
        cached=False,
        fetched_at=fetched_at,
    )
    cache.set(cache_key, report.model_dump(mode="json"), status="ok", fetched_at=fetched_at)
    return report


async def search(name: str, limit: int = 10) -> SearchResult:
    """Search by name, consulting the cache first (`NORBIZ_SPEC.md` §§4, 9)."""
    if not 1 <= limit <= 100:
        raise RegistryError(
            ErrorCode.BAD_REQUEST,
            f"limit must be between 1 and 100, got {limit}.",
            hint="Call search_company again with limit between 1 and 100.",
            country="NO",
            registry="brreg",
        )

    query = name.strip()
    cache_key = f"NO:brreg:search:{query.casefold()}:{limit}"

    entry = cache.get(cache_key)
    if entry is not None:
        result = SearchResult.model_validate(entry.payload)
        return result.model_copy(update={"cached": True, "fetched_at": entry.fetched_at})

    response = await _fetch("/enheter", params={"navn": query, "size": limit})

    if response.status_code == 200:
        data = response.json()
    elif response.status_code == 429:
        raise _rate_limited_error()
    else:
        raise _upstream_error(response)

    fetched_at = datetime.now(UTC)
    result = mapping.map_search_result(data, query=query, cached=False, fetched_at=fetched_at)
    cache.set(cache_key, result.model_dump(mode="json"), status="ok", fetched_at=fetched_at)
    return result


def _accounts_cache_key(orgnr: str) -> str:
    """``{COUNTRY}:{registry}:{name}:{id}`` (``DECISIONS.md`` D-042(j)), where
    ``name`` was the ``include`` value this block was first reached by.

    **One key now serves both `filings` and `financials`** (D-043(h)(1)):
    they are the same upstream call, so a second key would double-store the
    same body and let the two blocks age apart — D-042(j)'s "one key per
    attachment" is corrected by D-043(h)(1) to "one key per upstream call".
    Kept under its original ``filings`` segment rather than renamed to
    ``accounts``: a rename is a cache-compatibility decision for whoever
    next touches ``core/cache.py``'s per-kind TTL table (D-045(e)), not one
    this task makes unilaterally while that table does not exist yet."""
    return f"NO:brreg:filings:{orgnr}"


def _accounts_upstream_error(orgnr: str) -> RegistryError:
    """The accounts endpoint's own 5xx, with the hint the generic one cannot give.

    Recorded live 2026-09-08 and **not transient**: banks, insurers and many
    foundations return 500 here on every attempt while their Enhetsregisteret
    record shows filed accounts (34 of 36 sampled entities under NACE 64.190,
    65.110 and 65.120). ``registries/no/accounts.py``'s docstring carries the
    measurement. An agent that reads "retry in a moment" and retries forever
    is being sent on an errand that cannot succeed, so this hint says what to
    do instead.
    """
    return RegistryError(
        ErrorCode.UPSTREAM_ERROR,
        f"Regnskapsregisteret returned a server error for organisasjonsnummer {orgnr}.",
        hint=(
            "The company record itself is unaffected — only the annual-accounts block "
            "failed. This dataset returns a persistent error for banks, insurers and some "
            "foundations, which file under sector-specific accounting regulations it does "
            "not present, so retrying may never succeed for those entities. Check "
            "last_annual_accounts_year on the company record, or Brønnøysundregistrene "
            "directly."
        ),
        country="NO",
        registry="brreg",
    )


#: One upstream fetch in flight per cold cache key, so that `fetch_accounts`
#: and `fetch_financials` called concurrently for the same organisation share
#: it rather than racing to make two (``DECISIONS.md`` D-043(h)(3)):
#: ``core/registry.py::lookup_with`` runs every requested attachment with
#: bounded concurrency, so ``include=["filings", "financials"]`` calls both
#: methods before either's fetch can complete on a cold cache. Populated and
#: drained only by :func:`_fetch_accounts_payload`, below — nothing else
#: touches it.
#:
#: **Why no lock is needed.** Between checking the cache and registering the
#: task here there is no ``await`` at all, so this whole sequence is one
#: uninterruptible step from the event loop's point of view: whichever of the
#: two coroutines reaches :func:`_fetch_accounts_payload` first always
#: finishes registering its task in this map before the other gets a turn,
#: because Python's cooperative scheduling only switches coroutines at a
#: genuine suspension. The second coroutine then always finds the task
#: already there, on a cold cache, however the two happen to be interleaved.
_inflight_accounts_fetch: dict[str, asyncio.Task[tuple[list[Any], bool, datetime]]] = {}


async def _do_fetch_accounts_payload(orgnr: str, cache_key: str) -> tuple[list[Any], bool, datetime]:
    """The upstream call itself — everything :func:`fetch_accounts` did
    before D-043, unchanged, including the cache write. Run at most once per
    cold cache key: :func:`_fetch_accounts_payload` is the only caller, and it
    never starts a second one while this one is in flight.

    Returns ``(items, cached=False, fetched_at)`` — a fresh fetch is never
    itself a cache hit, whichever of :func:`fetch_accounts` /
    :func:`fetch_financials` happened to trigger it.
    """
    try:
        response = await _fetch(accounts.ACCOUNTS_URL.format(orgnr=orgnr))
    except RegistryError as exc:
        if exc.code is ErrorCode.UPSTREAM_ERROR:
            raise _accounts_upstream_error(orgnr) from exc
        raise

    if response.status_code == 200:
        body = response.json()
        data = body if isinstance(body, list) else []
    elif response.status_code == 404:
        data = []
    elif response.status_code == 429:
        raise _rate_limited_error()
    else:
        raise _accounts_upstream_error(orgnr)

    fetched_at = datetime.now(UTC)
    cache.set(
        cache_key,
        {"items": data},
        status="ok" if data else "not_found",
        fetched_at=fetched_at,
    )
    return data, False, fetched_at


async def _fetch_accounts_payload(orgnr: str) -> tuple[list[Any], bool, datetime]:
    """The parsed payload behind **both** :func:`fetch_accounts` and
    :func:`fetch_financials` — one cache entry, one in-flight upstream call,
    shared regardless of which of the two callers arrives first (D-043(h)).

    Returns ``(items, cached, fetched_at)``: ``items`` is the bare JSON array
    Regnskapsregisteret returns (never re-shaped — D-026(a)), and ``cached``/
    ``fetched_at`` are what both :class:`~registry_mcp.core.models.
    FilingHistory.provenance` and :class:`~registry_mcp.core.models.
    FinancialSummary.provenance` are built from, so a caller requesting both
    blocks together always gets two `SourceRef`\\ s equal in all five fields
    (D-043(h)(2)).
    """
    cache_key = _accounts_cache_key(orgnr)

    entry = cache.get(cache_key)
    if entry is not None:
        # The payload is a bare JSON array; `CacheEntry.payload` is a dict, so
        # it is stored under one key rather than reshaped (D-026(a): carried,
        # never constructed).
        items: list[Any] = entry.payload.get("items") or []
        return items, True, entry.fetched_at

    existing = _inflight_accounts_fetch.get(cache_key)
    if existing is not None:
        return await existing

    task = asyncio.ensure_future(_do_fetch_accounts_payload(orgnr, cache_key))
    _inflight_accounts_fetch[cache_key] = task
    try:
        return await task
    finally:
        _inflight_accounts_fetch.pop(cache_key, None)


async def fetch_accounts(id: str) -> FilingHistory:
    """Fetch one entity's filed annual accounts, consulting the cache first.

    R-5d (``DECISIONS.md`` D-042(i)); closes D-023(d). Open and keyless —
    unlike Sweden's equivalent, this needs no credential at all.

    **A 404 is a present, empty block, never ``not_found``.** Regnskapsregisteret
    answers a bodyless 404 both for an entity that has filed nothing and for an
    organisasjonsnummer that was never issued, so it cannot decide existence
    and is not allowed to: ``/enheter/{orgnr}`` alone does that (D-041(h)),
    and a caller only reaches this function after that lookup succeeded.
    Unlike Britain's charges endpoint — where the same rule was written
    defensively because no live 404 could be produced — this branch is the
    ordinary case here, confirmed live on real entities that exist
    (``974760673``, ``936295592``) as well as on numbers that do not.

    A 5xx becomes ``upstream_error`` after ``_fetch``'s single retry, and
    ``core/registry.py::lookup_with`` leaves the block absent with a note
    (D-042(j)); it never fails the lookup.

    TTL asymmetry (D-042(j): 24 h non-empty, 1 h empty) is implemented by
    reusing ``core/cache.py``'s existing ``status="not_found"`` label purely
    for its 1 h TTL — **never** raised as a ``not_found`` error on the read
    path below, unlike its use in :func:`lookup`. ``core/cache.py`` still has
    no per-kind TTL table (D-042(j) names one; ``core/`` is another agent's
    footprint), so this is the same stand-in ``registries/gb/client.py::
    fetch_charges`` uses, and both should be replaced together.

    **D-043 (T38):** the fetch behind this function is shared with
    :func:`fetch_financials` — see :func:`_fetch_accounts_payload`. This
    function's own contract (cache key, TTL, 404/5xx/429 handling) is
    otherwise exactly what it was before that task.
    """
    orgnr = _validate_orgnr(id)
    data, cached, fetched_at = await _fetch_accounts_payload(orgnr)
    return accounts.map_regnskap(data, orgnr, cached=cached, fetched_at=fetched_at)


async def fetch_financials(id: str) -> FinancialSummary:
    """Fetch one entity's key figures from its filed annual accounts,
    consulting the cache first.

    D-043 (T38, ``R-5f``). **The exact same fetch as :func:`fetch_accounts`,
    not a second one**: both read
    ``data.brreg.no/regnskapsregisteret/regnskap/{orgnr}`` through
    :func:`_fetch_accounts_payload`, which serves both from one cache entry
    and, on a cold cache, from one in-flight upstream call however the two
    are interleaved (D-043(h)). Consequently this function's failure modes,
    TTL and 404 handling are identical to :func:`fetch_accounts`'s — see that
    function's docstring — and the two blocks' ``provenance`` are equal in
    all five fields when fetched together (D-043(h)(2)).
    """
    orgnr = _validate_orgnr(id)
    data, cached, fetched_at = await _fetch_accounts_payload(orgnr)
    return accounts.map_regnskap_financials(data, orgnr, cached=cached, fetched_at=fetched_at)
