"""HTTP client for Companies House (api.company-information.service.gov.uk).

See ``UK_SPEC.md`` §§1, 6, 9.

Behaviour, exactly:

* Base URL ``https://api.company-information.service.gov.uk``, 5 s timeout
  per attempt, one retry on a timeout or a 5xx (never a 4xx), 250 ms backoff.
* HTTP Basic auth, the API key as username, empty password
  (``httpx.BasicAuth(key, "")``) — the key is read from
  ``COMPANIES_HOUSE_API_KEY`` **at call time**, never at import time, so a
  missing key never breaks ``import registry_mcp.registries``.
* An in-process async token bucket (capacity 600, refill 600/5 min) guards
  the operator's shared key against a runaway loop; it never adds meaningful
  latency to a normal request.
* One module-level ``httpx.AsyncClient``, created lazily, closed by
  :func:`aclose`.
* A 429 maps to ``rate_limited`` (HTTP 429), the same code
  ``registries/no/client.py`` maps its own 429 to (``DECISIONS.md`` D-019) —
  it tells an agent the call will succeed shortly, unlike ``upstream_error``.

**Why this module caches the raw upstream JSON, not the mapped
``CompanyReport``** (unlike ``registries/no/client.py``): a later fix to
``registries/gb/mapping.py`` then applies to entries already cached, rather
than serving stale mapped shapes until the 24 h TTL clears them. This cache
is a plain key/value store, never consulted by anything other than
:func:`lookup` itself — the register's own filing dates it carries are read
out of the payload once, at lookup time, into
``CompanyReport.published_deadlines`` (``DECISIONS.md`` D-018), which is what
lets ``rules.deadlines_for(report, today)`` stay the pure function its
contract promises.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from registry_mcp import __version__
from registry_mcp.core import cache
from registry_mcp.core.models import CompanyReport, ErrorCode, RegistryError, SearchResult
from registry_mcp.registries.gb import charges, filing_history, mapping

__all__ = ["aclose", "fetch_charges", "fetch_filings", "lookup", "search"]

logger = logging.getLogger(__name__)

BASE_URL = "https://api.company-information.service.gov.uk"
_TIMEOUT = httpx.Timeout(5.0)
_RETRY_BACKOFF_SECONDS = 0.25
_MAX_ATTEMPTS = 2  # one try + one retry

_API_KEY_ENV = "COMPANIES_HOUSE_API_KEY"
_SIGNUP_URL = "https://developer.company-information.service.gov.uk/get-started"

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


# ---------------------------------------------------------------------------
# §6 — token bucket rate limiter
# ---------------------------------------------------------------------------

_BUCKET_CAPACITY = 600.0
_BUCKET_REFILL_PER_SECOND = 600.0 / 300.0  # 2.0 tokens/s
_BUCKET_MAX_WAIT_SECONDS = 2.0


class _TokenBucket:
    """A guard against a runaway loop burning the operator's shared key.

    Not a scheduler: ``acquire()`` only holds its lock long enough to update
    the token count, never while doing the actual HTTP call, so it never
    serialises concurrent requests to different companies (test 105).
    """

    def __init__(self, capacity: float, refill_per_second: float) -> None:
        self._capacity = capacity
        self._refill_per_second = refill_per_second
        self._tokens = capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        deadline = time.monotonic() + _BUCKET_MAX_WAIT_SECONDS
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._updated
                self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_second)
                self._updated = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
            if time.monotonic() >= deadline:
                raise RegistryError(
                    ErrorCode.RATE_LIMITED,
                    "This deployment's Companies House request budget is exhausted.",
                    hint="Wait a few seconds and retry the same call.",
                    country="GB",
                    registry="companies-house",
                )
            await asyncio.sleep(0.01)


_bucket = _TokenBucket(_BUCKET_CAPACITY, _BUCKET_REFILL_PER_SECOND)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def _read_api_key() -> str:
    return os.environ.get(_API_KEY_ENV, "").strip()


def _no_key_error() -> RegistryError:
    return RegistryError(
        ErrorCode.UPSTREAM_ERROR,
        "This deployment has no Companies House API key, so UK company data cannot be fetched.",
        hint=(
            "Call list_countries to see which countries can answer right now. If you run "
            "this server yourself, set the COMPANIES_HOUSE_API_KEY environment variable — a "
            f"key is free from {_SIGNUP_URL} — and restart it."
        ),
        country="GB",
        registry="companies-house",
    )


def _unauthorized_error() -> RegistryError:
    return RegistryError(
        ErrorCode.UPSTREAM_ERROR,
        "Companies House rejected the configured API key.",
        hint=(
            "COMPANIES_HOUSE_API_KEY is missing, wrong or revoked. Get a free key from "
            f"{_SIGNUP_URL} and set it, or call list_countries to see which countries can "
            "answer right now."
        ),
        country="GB",
        registry="companies-house",
    )


def _not_found_error(company_number: str) -> RegistryError:
    # `details` deliberately carries nothing from the upstream 404 body
    # (product ruling, post-T15e): `request_id` is Companies House's own
    # support-ticket handle, not something this service's callers can act
    # on, and D-007's envelope is documented, minimal and ours — not a place
    # to forward an upstream debug field just because it happened to exist.
    return RegistryError(
        ErrorCode.NOT_FOUND,
        f"No company with number {company_number} is on the Companies House register.",
        hint=(
            "The number is well-formed, so it may never have been issued, or the company "
            "may have been removed from the register. Note that sole traders and ordinary "
            "partnerships are not registered at Companies House at all. Call search_company "
            "with the business name instead."
        ),
        country="GB",
        registry="companies-house",
    )


def _rate_limited_error(response: httpx.Response) -> RegistryError:
    retry_after = response.headers.get("retry-after")
    if retry_after:
        wait = f"{retry_after} seconds"
    else:
        reset = response.headers.get("x-ratelimit-reset")
        wait = "about five minutes"
        if reset:
            try:
                reset_dt = datetime.fromtimestamp(int(reset), tz=UTC)
                wait = f"until {reset_dt.isoformat()} (from the x-ratelimit-reset header)"
            except (ValueError, OverflowError, OSError):
                wait = "about five minutes"
    return RegistryError(
        ErrorCode.RATE_LIMITED,
        "Companies House rate-limited this request (429).",
        hint=f"Wait {wait}, then retry the same call.",
        country="GB",
        registry="companies-house",
    )


def _upstream_error(response: httpx.Response) -> RegistryError:
    return RegistryError(
        ErrorCode.UPSTREAM_ERROR,
        f"Companies House returned an unexpected status {response.status_code}.",
        hint="This is an upstream problem, not a bad request. Retry the call in a moment.",
        country="GB",
        registry="companies-house",
    )


async def _fetch(path: str, *, params: dict[str, Any] | None = None) -> httpx.Response:
    """GET ``path``, retrying exactly once on a timeout or a 5xx. Never on a 4xx.

    Raises before opening a socket when no API key is configured (test 94).
    """
    api_key = _read_api_key()
    if not api_key:
        raise _no_key_error()

    client = _get_client()
    auth = httpx.BasicAuth(api_key, "")

    attempt = 0
    while True:
        attempt += 1
        # One token per HTTP attempt (§6) — inside the loop so a retry
        # spends a second token, not just the first attempt.
        await _bucket.acquire()
        try:
            response = await client.get(path, params=params, auth=auth)
        except httpx.TimeoutException as exc:
            if attempt >= _MAX_ATTEMPTS:
                raise RegistryError(
                    ErrorCode.UPSTREAM_TIMEOUT,
                    f"Companies House did not respond within the timeout for {path}.",
                    hint=(
                        "The upstream API timed out twice. Retry the call in a moment; if "
                        "it keeps timing out, the upstream API may be degraded."
                    ),
                    country="GB",
                    registry="companies-house",
                ) from exc
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        if response.status_code >= 500:
            if attempt >= _MAX_ATTEMPTS:
                raise RegistryError(
                    ErrorCode.UPSTREAM_ERROR,
                    f"Companies House returned {response.status_code} for {path}.",
                    hint=(
                        "This is an upstream problem, not a bad request. Retry the call in "
                        "a moment."
                    ),
                    country="GB",
                    registry="companies-house",
                )
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        return response


def _cache_key(company_number: str) -> str:
    return f"GB:companies-house:entity:{company_number}"


async def lookup(id: str) -> CompanyReport:
    """Fetch one entity, consulting the cache first (`UK_SPEC.md` §§2, 9)."""
    from registry_mcp.registries.gb import rules

    company_number = rules.validate_crn(id)
    cache_key = _cache_key(company_number)

    entry = cache.get(cache_key)
    if entry is not None:
        if entry.status == "not_found":
            raise _not_found_error(company_number)
        return mapping.map_entity(entry.payload, cached=True, fetched_at=entry.fetched_at)

    response = await _fetch(f"/company/{company_number}")

    if response.status_code == 200:
        data = response.json()
    elif response.status_code == 404:
        cache.set(cache_key, {}, status="not_found")
        raise _not_found_error(company_number)
    elif response.status_code in (401, 403):
        raise _unauthorized_error()
    elif response.status_code == 429:
        raise _rate_limited_error(response)
    else:
        raise _upstream_error(response)

    fetched_at = datetime.now(UTC)
    cache.set(cache_key, data, status="ok", fetched_at=fetched_at)
    return mapping.map_entity(data, cached=False, fetched_at=fetched_at)


async def search(name: str, limit: int = 10) -> SearchResult:
    """Search by name, consulting the cache first (`UK_SPEC.md` §§4, 9).

    Companies House validates neither ``q`` nor ``items_per_page`` (§1.6 №8),
    so this module validates both itself, exactly as Norway does.
    """
    if not 1 <= limit <= 100:
        raise RegistryError(
            ErrorCode.BAD_REQUEST,
            f"limit must be between 1 and 100, got {limit}.",
            hint="Call search_company again with limit between 1 and 100.",
            country="GB",
            registry="companies-house",
        )

    query = name.strip()
    if not query:
        raise RegistryError(
            ErrorCode.BAD_REQUEST,
            "name must not be empty.",
            hint=(
                "Call search_company with a non-empty company name, or lookup_company if "
                "you already have the 8-character company number."
            ),
            country="GB",
            registry="companies-house",
        )

    cache_key = f"GB:companies-house:search:{query.casefold()}:{limit}"

    entry = cache.get(cache_key)
    if entry is not None:
        result = SearchResult.model_validate(entry.payload)
        return result.model_copy(update={"cached": True, "fetched_at": entry.fetched_at})

    response = await _fetch("/search/companies", params={"q": query, "items_per_page": limit})

    if response.status_code == 200:
        data = response.json()
    elif response.status_code in (401, 403):
        raise _unauthorized_error()
    elif response.status_code == 429:
        raise _rate_limited_error(response)
    else:
        raise _upstream_error(response)

    fetched_at = datetime.now(UTC)
    result = mapping.map_search_result(data, query=query, cached=False, fetched_at=fetched_at)
    cache.set(cache_key, result.model_dump(mode="json"), status="ok", fetched_at=fetched_at)
    return result


# ---------------------------------------------------------------------------
# Charges — R-5c / T37, Part B, built *behind the seam* (`DECISIONS.md`
# D-042; `registries/gb/charges.py`'s module docstring has the full recon
# trail). Deliberately **not** wired to `include=[...]` by this task — that
# is explicitly a follow-up's job, not this one's, per the brief that
# scoped this work. (`core/registry.py` gained `lookup_with` and `Registry`
# gained `supported_includes` — R-5 — partway through this task, landed by
# the parallel agent who owns `core/`; this module still does not import
# from `core/models.py`'s new shapes or depend on them, on purpose, so it
# stays exactly as self-contained as it was designed to be.) `fetch_charges`
# is the whole seam — a self-contained function that validates the id,
# fetches or serves from cache, and returns a fully-mapped
# `charges.ChargeList`, ready for a follow-up to call from a real
# `charges()` method on `CompaniesHouseRegistry`.
# ---------------------------------------------------------------------------


def _charges_cache_key(company_number: str) -> str:
    return f"GB:companies-house:charges:{company_number}"


async def fetch_charges(id: str) -> charges.ChargeList:
    """Fetch one entity's charges, consulting the cache first.

    One page, ``charges.CHARGES_ITEMS_PER_PAGE`` (100 — the register's own
    confirmed maximum, D-042(j)). Never paginates further.

    A 404 is treated exactly like a 200 with an empty ``items`` list — never
    raised as ``not_found`` — because D-041(h)'s principle binds this
    endpoint: ``/company/{n}`` alone decides whether an entity exists, and a
    caller only reaches this function after that lookup already succeeded.
    Confirmed live that Companies House does not actually 404 this endpoint
    even for a nonexistent company number (``registries/gb/charges.py``'s
    docstring); this branch exists defensively, not because it was observed.

    TTL asymmetry (D-042(j): 24 h for a non-empty result, 1 h for an empty
    one) is implemented by reusing ``core/cache.py``'s existing
    ``status="not_found"`` label purely for its 1 h TTL when this company
    has no charges — **never** raised as a `not_found` error on the read
    path below, unlike its use in :func:`lookup`. ``core/cache.py`` has no
    per-kind TTL table yet (D-042(j) names one, to be built in
    ``core/cache.py:84-94`` "by whichever [task] lands first"); that table
    is out of this task's footprint (``core/`` is owned by a parallel
    agent), so this is the stand-in until it exists.
    """
    from registry_mcp.registries.gb import rules

    company_number = rules.validate_crn(id)
    cache_key = _charges_cache_key(company_number)

    entry = cache.get(cache_key)
    if entry is not None:
        return charges.map_charges(
            entry.payload, company_number, cached=True, fetched_at=entry.fetched_at
        )

    response = await _fetch(
        f"/company/{company_number}/charges",
        params={"items_per_page": charges.CHARGES_ITEMS_PER_PAGE},
    )

    if response.status_code == 200:
        data = response.json()
    elif response.status_code == 404:
        data = {}
    elif response.status_code in (401, 403):
        raise _unauthorized_error()
    elif response.status_code == 429:
        raise _rate_limited_error(response)
    else:
        raise _upstream_error(response)

    fetched_at = datetime.now(UTC)
    status = "ok" if data.get("items") else "not_found"
    cache.set(cache_key, data, status=status, fetched_at=fetched_at)
    return charges.map_charges(data, company_number, cached=False, fetched_at=fetched_at)


# ---------------------------------------------------------------------------
# Filing history — R-5c / T37, built *behind the seam* (`DECISIONS.md` D-042;
# `registries/gb/filing_history.py`'s module docstring has the full recon
# trail and the minimisation argument). Deliberately **not** wired to
# `include=[...]` by this task — that is a follow-up's job. `fetch_filings`
# is the whole seam, and it mirrors `fetch_charges` above line for line:
# validate the id, fetch or serve from cache, return a fully-mapped
# `filing_history.FilingHistory`, ready for a follow-up to call from a real
# `filings()` method on `CompaniesHouseRegistry`.
# ---------------------------------------------------------------------------


def _filings_cache_key(company_number: str) -> str:
    return f"GB:companies-house:filings:{company_number}"


async def fetch_filings(id: str) -> filing_history.FilingHistory:
    """Fetch one entity's filing history, consulting the cache first.

    One page, ``filing_history.FILINGS_ITEMS_PER_PAGE`` (25 — D-042(j)'s
    ruled page size for filings, a quarter of the register's own maximum of
    100). Never paginates further; truncation is disclosed in the block's
    ``notes``, never silent.

    A 404 is treated exactly like a 200 with an empty ``items`` list — never
    raised as ``not_found`` — because D-041(h)'s principle binds this
    endpoint: ``/company/{n}`` alone decides whether an entity exists, and a
    caller only reaches this function after that lookup already succeeded.
    Confirmed live that Companies House does not actually 404 this endpoint,
    not even for a company number that was never issued (it answers 200 with
    ``total_count: 0``); this branch exists defensively, not because it was
    observed.

    TTL asymmetry (D-042(j): 24 h for a non-empty result, 1 h for an empty
    one) is implemented by reusing ``core/cache.py``'s existing
    ``status="not_found"`` label purely for its 1 h TTL when this company has
    no filings — **never** raised as a ``not_found`` error on the read path
    below, unlike its use in :func:`lookup`. That is the same stand-in
    :func:`fetch_charges` uses, for the same reason: ``core/cache.py`` has no
    per-kind TTL table yet (D-042(j) names one) and ``core/`` is outside this
    task's footprint.
    """
    from registry_mcp.registries.gb import rules

    company_number = rules.validate_crn(id)
    cache_key = _filings_cache_key(company_number)

    entry = cache.get(cache_key)
    if entry is not None:
        return filing_history.map_filing_history(
            entry.payload, company_number, cached=True, fetched_at=entry.fetched_at
        )

    response = await _fetch(
        f"/company/{company_number}/filing-history",
        params={"items_per_page": filing_history.FILINGS_ITEMS_PER_PAGE},
    )

    if response.status_code == 200:
        data = response.json()
    elif response.status_code == 404:
        data = {}
    elif response.status_code in (401, 403):
        raise _unauthorized_error()
    elif response.status_code == 429:
        raise _rate_limited_error(response)
    else:
        raise _upstream_error(response)

    fetched_at = datetime.now(UTC)
    status = "ok" if data.get("items") else "not_found"
    cache.set(cache_key, data, status=status, fetched_at=fetched_at)
    return filing_history.map_filing_history(
        data, company_number, cached=False, fetched_at=fetched_at
    )
