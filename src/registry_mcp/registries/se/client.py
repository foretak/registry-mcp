"""HTTP client for Bolagsverket's "värdefulla datamängder" API.

See ``SWEDEN_SPEC.md`` §§1, 6, 9. Behaviour, exactly:

* Two base URLs and two token URLs, selected together as one pair by
  ``BOLAGSVERKET_ENVIRONMENT`` (``"production"`` default, or ``"test"``) —
  never a silent fall back to production on an unrecognised value (§6,
  D-037). **The token host is ``portal.api.bolagsverket.se``, not
  ``gw.api.bolagsverket.se``** (§1.1) — both hosts are wrong in an earlier
  draft of this project's own notes.
* OAuth 2 client-credentials token, both scopes in one request, cached in
  memory per environment with a 60 s refresh margin (§6.1). Read from
  ``BOLAGSVERKET_CLIENT_ID``/``BOLAGSVERKET_CLIENT_SECRET`` **inside the
  request path**, never at import time, so a deployment with no Swedish
  credentials still imports and serves every other country (§1.2, D-037).
* ``POST /organisationer`` with the identitetsbeteckning in the JSON body,
  never a URL or query parameter (§1.4, §6.2) — Bolagsverket's own design,
  because the identifier is personal data for a large class of Swedish
  entities.
* 5 s timeout per attempt, one retry on a timeout or a 5xx (never a 4xx),
  250 ms backoff — for the token request too. A 401/403 on a *data* call
  invalidates the cached token exactly once and retries with a fresh one
  (§6.1); a second 401/403 raises.
* An in-process async token bucket, capacity 60, refill 1.0 token/second
  (§1.5, §6) — one token per HTTP attempt, **including the token request**.
  Unlike Britain's, a modest agent loop can reach this ceiling legitimately,
  so ``acquire()`` waits (at most 2 s) rather than merely guarding a runaway.
* One module-level ``httpx.AsyncClient``, created lazily, closed by
  :func:`aclose` — which also clears the cached token(s), so a credential
  never survives the shutdown that was supposed to end it.
* ``search`` raises ``not_implemented`` before touching the network, the
  token or the environment (§4): the register has no search operation, and
  the check must not cost a request from the 60/min budget to say so.

**Why this module caches the raw upstream JSON, not the mapped
``CompanyReport``** (the GB choice, for the GB reason,
``registries/gb/client.py``): a later fix to ``registries/se/mapping.py``
then applies to entries already cached. **One Sweden-specific rule**: a
partially failed 200 (§1.6 — some field's ``fel.typ`` blocked it) is never
written to the cache (§9) — serving a company with no name or dates for 24
hours because Bolagsverket had a bad moment would be worse than a cache miss.

**`financials` (D-043, D-047(f),(g)) is the one deliberate exception to that
rule, and the exception runs the other way.** ``/dokument/{id}`` returns a
zip holding one inline-XBRL XHTML — a filed annual report, which names its
signatories (``registries/se/ixbrl.py``'s docstring). **Nothing about that
document is ever cached, logged or written to disk**: the zip is fetched,
unzipped and parsed inside :func:`fetch_financials`, and only the resulting
:class:`~registry_mcp.core.models.FinancialPeriod` — the parsed figures,
never a byte of the source — is stored, under its own key
(:func:`_financials_cache_key`, keyed on the immutable ``dokumentId`` rather
than on the company) with its own thirty-day TTL (``core/cache.py``'s
``_TTL_BY_KIND["financials"]``). ``/dokumentlista`` is shared with
:func:`fetch_filings` exactly as D-043(h) requires for Norway — one upstream
call, one in-flight fetch, one cache entry — because the two attachments
read the same list to decide which document to fetch and to disclose how
many exist; see :func:`_fetch_dokumentlista_payload`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from registry_mcp import __version__
from registry_mcp.core import cache
from registry_mcp.core.models import (
    CompanyReport,
    ErrorCode,
    FilingHistory,
    FinancialPeriod,
    FinancialSummary,
    RegistryError,
    SearchResult,
    SourceRef,
)
from registry_mcp.registries.se import filings, financials, ixbrl, mapping

__all__ = ["aclose", "fetch_filings", "fetch_financials", "lookup", "search"]

logger = logging.getLogger(__name__)

_PRODUCTION = "production"
_TEST = "test"

#: Base URL and token URL are selected **together**, as one pair (§6,
#: D-037) — an operator can never send production credentials to the test
#: host or the reverse by mixing environment variables.
_BASE_URLS: dict[str, str] = {
    _PRODUCTION: "https://gw.api.bolagsverket.se/vardefulla-datamangder/v1",
    _TEST: "https://gw-accept2.api.bolagsverket.se/vardefulla-datamangder/v1",
}
_TOKEN_URLS: dict[str, str] = {
    _PRODUCTION: "https://portal.api.bolagsverket.se/oauth2/token",
    _TEST: "https://portal-accept2.api.bolagsverket.se/oauth2/token",
}

_ENVIRONMENT_ENV = "BOLAGSVERKET_ENVIRONMENT"
_CLIENT_ID_ENV = "BOLAGSVERKET_CLIENT_ID"
_CLIENT_SECRET_ENV = "BOLAGSVERKET_CLIENT_SECRET"
#: Both scopes in one request, space-separated, exactly as the connection
#: guide's own cURL example shows (§1.2) — a scope missing from the token
#: makes every later resource call fail, which is why this is not two calls.
_SCOPE = "vardefulla-datamangder:read vardefulla-datamangder:ping"
_FORM_URL = (
    "https://bolagsverket.se/apierochoppnadata/hamtaforetagsinformation/vardefulladatamangder"
    "/kundanmalantillapiforvardefulladatamangder.5528.html"
)

_TIMEOUT = httpx.Timeout(5.0)
_RETRY_BACKOFF_SECONDS = 0.25
_MAX_ATTEMPTS = 2  # one try + one retry
_TOKEN_REFRESH_MARGIN_SECONDS = 60.0

_client: httpx.AsyncClient | None = None


@dataclass
class _CachedToken:
    access_token: str
    expires_at: float  # a time.monotonic() timestamp, never wall-clock


#: Keyed by environment, not by client id: a process only ever runs one
#: environment at a time (an env var), but tests switch it via monkeypatch,
#: and keying by environment keeps a stale test-environment token from ever
#: being handed to a production request or the reverse.
_tokens: dict[str, _CachedToken] = {}


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
            timeout=_TIMEOUT, headers={"Accept": "application/json", "User-Agent": _user_agent()}
        )
    return _client


async def aclose() -> None:
    """Close the shared client and clear the cached token(s) (§6.1).

    A cached bearer token surviving ``aclose()`` is a credential leaking past
    the shutdown that was supposed to end it.
    """
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
    _tokens.clear()


# ---------------------------------------------------------------------------
# §1.5/§6 — token bucket rate limiter (60/min, refill 1.0/s)
# ---------------------------------------------------------------------------

_BUCKET_CAPACITY = 60.0
_BUCKET_REFILL_PER_SECOND = 1.0
_BUCKET_MAX_WAIT_SECONDS = 2.0


class _TokenBucket:
    """Unlike Britain's, this bucket is reachable by legitimate traffic: its
    wait is a feature that turns a burst into a short queue instead of a
    429, not merely a runaway guard."""

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
                    "This deployment's Bolagsverket request budget (60 per minute) is exhausted.",
                    hint="Wait about a minute, then retry the same call.",
                    country="SE",
                    registry="bolagsverket",
                )
            await asyncio.sleep(0.01)


_bucket = _TokenBucket(_BUCKET_CAPACITY, _BUCKET_REFILL_PER_SECOND)


# ---------------------------------------------------------------------------
# Environment and credentials
# ---------------------------------------------------------------------------


def _read_environment() -> str:
    """``BOLAGSVERKET_ENVIRONMENT`` (§6, D-037). Default ``production``. An
    unrecognised value raises rather than silently falling back — the one
    failure mode this variable exists to prevent."""
    raw = os.environ.get(_ENVIRONMENT_ENV, "").strip().lower() or _PRODUCTION
    if raw not in _BASE_URLS:
        raise RegistryError(
            ErrorCode.UPSTREAM_ERROR,
            f"{_ENVIRONMENT_ENV}={raw!r} is not a recognised Bolagsverket environment.",
            hint=f"Set {_ENVIRONMENT_ENV} to 'production' or 'test' (default 'production').",
            country="SE",
            registry="bolagsverket",
        )
    return raw


def _read_credentials() -> tuple[str, str]:
    client_id = os.environ.get(_CLIENT_ID_ENV, "").strip()
    client_secret = os.environ.get(_CLIENT_SECRET_ENV, "").strip()
    return client_id, client_secret


def _no_credentials_error() -> RegistryError:
    # The hint names BOTH variables, always — an operator who set the id and
    # not the secret is one variable away, and a hint naming only the one it
    # happened to check first sends them looking in the wrong place (D-037).
    return RegistryError(
        ErrorCode.UPSTREAM_ERROR,
        "This deployment has no Bolagsverket credentials, so Swedish company data cannot "
        "be fetched.",
        hint=(
            "Call list_countries to see which countries can answer right now. If you run "
            f"this server yourself, set BOTH {_CLIENT_ID_ENV} and {_CLIENT_SECRET_ENV} and "
            "restart it — Bolagsverket's API is free and needs no contract; request "
            f"credentials at {_FORM_URL} with an email address and a mobile number."
        ),
        country="SE",
        registry="bolagsverket",
    )


# ---------------------------------------------------------------------------
# Other errors (§6.3, §6.4)
# ---------------------------------------------------------------------------


def _invalid_id_error(identitetsbeteckning: str) -> RegistryError:
    return RegistryError(
        ErrorCode.INVALID_ID,
        f"Bolagsverket rejected {identitetsbeteckning} as a malformed identitetsbeteckning.",
        hint=(
            "Bolagsverket validates a check digit that this module does not: it answers "
            "'Identitetsbeteckning har ogiltig kontrollsiffra' for a number of the right "
            "length whose check digit is wrong. Check the digits. An organisationsnummer "
            "is ten digits and a personnummer is twelve (YYYYMMDDNNNN)."
        ),
        country="SE",
        registry="bolagsverket",
    )


def _not_found_error(identitetsbeteckning: str) -> RegistryError:
    return RegistryError(
        ErrorCode.NOT_FOUND,
        f"Bolagsverket has no organisation registered with identifier {identitetsbeteckning}.",
        hint=(
            "The identifier is well-formed, so it may never have been issued, or the "
            "organisation may have been struck off and removed. Bolagsverket adds a caveat "
            "of its own here: an organisation absent from one data producer may still exist "
            "at the other, so a Statistics Sweden-only entity can answer this way. "
            "Bolagsverket's free API cannot search by name, so there is no search_company "
            "call to fall back on for Sweden."
        ),
        country="SE",
        registry="bolagsverket",
    )


def _unauthorized_error(status_code: int) -> RegistryError:
    # A 403 is more likely a missing scope than a bad secret (§6.3) — that
    # failure is invisible from the data call alone, so the hint says so.
    if status_code == 403:
        detail = (
            "A 403 usually means the access token is missing a required scope, not that "
            "the secret is wrong."
        )
    else:
        detail = "Bolagsverket rejected the access token."
    return RegistryError(
        ErrorCode.UPSTREAM_ERROR,
        f"Bolagsverket returned {status_code} for the data request.",
        hint=(
            f"{detail} Check BOTH {_CLIENT_ID_ENV} and {_CLIENT_SECRET_ENV}, and that the "
            f"token request asks for both scopes ({_SCOPE})."
        ),
        country="SE",
        registry="bolagsverket",
    )


def _rate_limited_error() -> RegistryError:
    return RegistryError(
        ErrorCode.RATE_LIMITED,
        "Bolagsverket rate-limited this request (429).",
        hint="Wait about a minute, then retry the same call.",
        country="SE",
        registry="bolagsverket",
    )


def _upstream_error(status_code: int) -> RegistryError:
    return RegistryError(
        ErrorCode.UPSTREAM_ERROR,
        f"Bolagsverket returned an unexpected status {status_code}.",
        hint="This is an upstream problem, not a bad request. Retry the call in a moment.",
        country="SE",
        registry="bolagsverket",
    )


def _malformed_response_error(context: str) -> RegistryError:
    """§6.1/§6.3, review fix 13: a 200 whose body is not JSON or lacks a
    field this module requires is an upstream problem, not a bare
    ``KeyError``/``json.JSONDecodeError`` reaching the caller. Never echoes
    the response body (D-007)."""
    return RegistryError(
        ErrorCode.UPSTREAM_ERROR,
        f"Bolagsverket returned a 200 for {context} whose body was not valid JSON or was "
        "missing a field this module requires.",
        hint="This is an upstream problem, not a bad request. Retry the call in a moment.",
        country="SE",
        registry="bolagsverket",
    )


def _timeout_error() -> RegistryError:
    return RegistryError(
        ErrorCode.UPSTREAM_TIMEOUT,
        "Bolagsverket did not respond within the timeout.",
        hint=(
            "The upstream API timed out twice. Retry the call in a moment; if it keeps "
            "timing out, the upstream API may be degraded."
        ),
        country="SE",
        registry="bolagsverket",
    )


# ---------------------------------------------------------------------------
# §6.1 — the token
# ---------------------------------------------------------------------------


async def _fetch_token(environment: str, client_id: str, client_secret: str) -> _CachedToken:
    token_url = _TOKEN_URLS[environment]
    http_client = _get_client()
    form = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": _SCOPE,
    }

    attempt = 0
    response: httpx.Response | None = None
    while True:
        attempt += 1
        await _bucket.acquire()
        try:
            response = await http_client.post(token_url, data=form)
        except httpx.TimeoutException as exc:
            if attempt >= _MAX_ATTEMPTS:
                raise _timeout_error() from exc
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        if response.status_code >= 500:
            if attempt >= _MAX_ATTEMPTS:
                raise _upstream_error(response.status_code)
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        break

    assert response is not None  # the loop above only exits via return/raise/break-with-response
    if response.status_code == 429:
        # The token endpoint sits behind the same WSO2 gateway and its own
        # throttling policy (§6.1, T26e fix 12) — a 429 here is a rate limit,
        # not a bad credential, and must be checked before the generic 4xx
        # branch below or an operator would be sent to re-check secrets that
        # are fine.
        raise _rate_limited_error()
    if response.status_code >= 400:
        # Credentials are present but the token endpoint rejected them
        # outright (§6.1) — the no-credentials hint applies unchanged.
        raise _no_credentials_error()

    try:
        body: dict[str, Any] = response.json()
        access_token = str(body["access_token"])
    except (ValueError, KeyError, TypeError) as exc:
        # A 200 whose body is not JSON, or is valid JSON but not an object —
        # a list/string/number/null indexes with `str` and raises `TypeError`,
        # not `KeyError` — or is an object lacking `access_token` (§6.1, T26e
        # fix 13 / review fix 4, T30): never a bare `TypeError`/`KeyError`/
        # `json.JSONDecodeError`.
        raise _malformed_response_error("the token request") from exc
    try:
        expires_in_seconds = float(body.get("expires_in", 3600))
    except (TypeError, ValueError):
        expires_in_seconds = 3600.0
    return _CachedToken(access_token=access_token, expires_at=time.monotonic() + expires_in_seconds)


async def _get_token(environment: str, *, force_refresh: bool = False) -> str:
    if not force_refresh:
        cached = _tokens.get(environment)
        if (
            cached is not None
            and cached.expires_at - _TOKEN_REFRESH_MARGIN_SECONDS > time.monotonic()
        ):
            return cached.access_token

    client_id, client_secret = _read_credentials()
    if not client_id or not client_secret:
        raise _no_credentials_error()

    token = await _fetch_token(environment, client_id, client_secret)
    _tokens[environment] = token
    return token.access_token


# ---------------------------------------------------------------------------
# §6.2 — the lookup call
# ---------------------------------------------------------------------------


async def _post_organisationer(
    base_url: str, token: str, identitetsbeteckning: str
) -> httpx.Response:
    """``POST {base}/organisationer``, retrying exactly once on a timeout or
    a 5xx. Never on a 4xx — including a 401/403, which is the caller's job to
    retry with a fresh token (§6.1), exactly once, one level up."""
    http_client = _get_client()
    attempt = 0
    response: httpx.Response | None = None
    while True:
        attempt += 1
        await _bucket.acquire()
        request_id = str(uuid.uuid4())
        logger.debug("Bolagsverket request %s for /organisationer", request_id)
        try:
            response = await http_client.post(
                f"{base_url}/organisationer",
                json={"identitetsbeteckning": identitetsbeteckning},
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                    "X-Request-Id": request_id,
                },
            )
        except httpx.TimeoutException as exc:
            if attempt >= _MAX_ATTEMPTS:
                raise _timeout_error() from exc
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        if response.status_code >= 500:
            if attempt >= _MAX_ATTEMPTS:
                return response
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        return response


async def _fetch_organisationer(environment: str, identitetsbeteckning: str) -> httpx.Response:
    """One data call, with the §6.1 one-time token-refresh-and-retry on a
    401/403 layered on top of :func:`_post_organisationer`'s own 5xx/timeout
    retry — two independent retry dimensions, never compounded into more
    than four HTTP attempts in the worst case."""
    base_url = _BASE_URLS[environment]
    token = await _get_token(environment)
    response = await _post_organisationer(base_url, token, identitetsbeteckning)
    if response.status_code in (401, 403):
        token = await _get_token(environment, force_refresh=True)
        response = await _post_organisationer(base_url, token, identitetsbeteckning)
    return response


# ---------------------------------------------------------------------------
# Cache and the test-environment note (§9, N10)
# ---------------------------------------------------------------------------


def _cache_key(environment: str, identitetsbeteckning: str) -> str:
    # §9: the environment is part of the identity of a cached row, so a
    # deployment that switches BOLAGSVERKET_ENVIRONMENT does not serve test
    # companies from a production cache or the reverse.
    short_env = "test" if environment == _TEST else "prod"
    return f"SE:bolagsverket:entity:{short_env}:{identitetsbeteckning}"


_N10_TEST_ENVIRONMENT_NOTE = (
    "This record came from Bolagsverket's test environment, not from the live register. "
    "The organisation it describes may not exist."
)


def _apply_environment_notes(report: CompanyReport, environment: str) -> CompanyReport:
    if environment != _TEST:
        return report
    source = (
        f"{report.source} — test environment"
        if report.source
        else "Bolagsverket — test environment"
    )
    return report.model_copy(
        update={"source": source, "notes": [*report.notes, _N10_TEST_ENVIRONMENT_NOTE]}
    )


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------


async def lookup(id: str) -> CompanyReport:
    """Fetch one entity, consulting the cache first (§§2, 9).

    Raises ``invalid_id`` (from :func:`rules.validate_id`) before any socket
    is opened, and raises the no-credentials ``upstream_error`` before any
    socket is opened when the cache misses and no credentials are configured.
    """
    from registry_mcp.registries.se import rules

    identitetsbeteckning = rules.validate_id(id)
    environment = _read_environment()
    cache_key = _cache_key(environment, identitetsbeteckning)

    entry = cache.get(cache_key)
    if entry is not None:
        if entry.status == "not_found":
            raise _not_found_error(identitetsbeteckning)
        report = mapping.map_entity(
            entry.payload, identitetsbeteckning, cached=True, fetched_at=entry.fetched_at
        )
        return _apply_environment_notes(report, environment)

    client_id, client_secret = _read_credentials()
    if not client_id or not client_secret:
        raise _no_credentials_error()

    response = await _fetch_organisationer(environment, identitetsbeteckning)

    if response.status_code == 200:
        try:
            data = response.json()
        except ValueError as exc:
            # A 200 whose body is not JSON (§6.3, T26e fix 13) — the same
            # wrapping the token request gets in `_fetch_token`.
            raise _malformed_response_error("the data request") from exc
        if not isinstance(data, dict):
            # A 200 whose body is valid JSON but not an object — a JSON
            # array/string/number/null parses cleanly and then raises a bare
            # `AttributeError` on `.get(...)` in `mapping.is_not_found`/
            # `map_entity` below, which both expect a `Mapping` (§6.3, review
            # fix 4, T30) — the same failure one type further out than the
            # token path above.
            raise _malformed_response_error("the data request")
    elif response.status_code == 400:
        raise _invalid_id_error(identitetsbeteckning)
    elif response.status_code in (401, 403):
        raise _unauthorized_error(response.status_code)
    elif response.status_code == 429:
        raise _rate_limited_error()
    else:
        raise _upstream_error(response.status_code)

    if mapping.is_not_found(data):
        cache.set(cache_key, {}, status="not_found")
        raise _not_found_error(identitetsbeteckning)

    fetched_at = datetime.now(UTC)
    report = mapping.map_entity(data, identitetsbeteckning, cached=False, fetched_at=fetched_at)

    # §1.6/§9: a partially failed 200 is never cached.
    if not mapping.is_partial_failure(data):
        cache.set(cache_key, data, status="ok", fetched_at=fetched_at)

    return _apply_environment_notes(report, environment)


_SEARCH_HINT = (
    "Sweden can only be looked up by identifier: call lookup_company with the ten-digit "
    "organisationsnummer (e.g. 5560160680), or the twelve-digit personnummer for a sole "
    "trader — validate_company_id will check the shape first without spending a lookup. "
    "Bolagsverket publishes the whole register as downloadable files for callers who need "
    "to search by name. search_company works for the other countries list_countries "
    "returns."
)


async def search(name: str, limit: int = 10) -> SearchResult:
    """Bolagsverket's free API has four operations and none accepts a name
    (§4). Raises **before** touching the network, the token or the
    environment: a 501 that first fetched an OAuth token would spend a
    request from a 60/min budget to answer a question that has no upstream
    at all, and the D-031 connector fan-out relies on this raising with no
    side effect (§4, D-031(c))."""
    raise RegistryError(
        ErrorCode.NOT_IMPLEMENTED,
        "Bolagsverket's free API cannot search by company name.",
        hint=_SEARCH_HINT,
        country="SE",
        registry="bolagsverket",
    )


# ---------------------------------------------------------------------------
# R-5b / T31 Part B, extended by D-043(h)/D-047(f),(g) — `POST /dokumentlista`,
# shared by `fetch_filings` and `fetch_financials`.
#
# `DECISIONS.md` D-041, D-042(b). `filings.py` builds the canonical
# `FilingHistory` directly (D-044(a)); `financials.py` builds
# `FinancialSummary` from an already-parsed `ixbrl.IXBRLDocument`. This
# module owns the wire and both caches; neither of the other two does I/O.
#
# **Response handling here is deliberately NOT `/organisationer`'s**
# (D-041(h), confirmed live 2026-09-08): `DokumentlistaSvar` is
# `{"dokument": [ ... ]}` — a plain array of plain objects with no
# `dataproducent`/`fel` wrapper — so `mapping.is_not_found` and
# `mapping.is_partial_failure` are never called on it. On this endpoint a 200
# means the answer arrived, and `/organisationer` alone decides whether an
# entity exists: an empty or absent `dokument` is a **present** block with
# `documents: []` for `filings` (D-041(c)) but an **absent** `financials`
# block with a report-level note (D-042(d)(3)) — see `fetch_financials`.
# ---------------------------------------------------------------------------


async def _post_dokumentlista(
    base_url: str, token: str, identitetsbeteckning: str
) -> httpx.Response:
    """``POST {base}/dokumentlista``, mirroring :func:`_post_organisationer`
    exactly: the identifier in the JSON body and never in a URL (D-039,
    D-040), one retry on a timeout or a 5xx and never on a 4xx, a **fresh**
    ``X-Request-Id`` UUID4 per attempt logged at DEBUG — the request id only,
    never the body — and one token-bucket token per attempt, because this is
    a real request against the published 60/min (§1.5; the OpenAPI's
    ``x-throttling-tier: "Unlimited"`` is a WSO2 gateway artefact and repeals
    nothing, and no ``X-RateLimit-*`` header comes back)."""
    http_client = _get_client()
    attempt = 0
    response: httpx.Response | None = None
    while True:
        attempt += 1
        await _bucket.acquire()
        request_id = str(uuid.uuid4())
        logger.debug("Bolagsverket request %s for /dokumentlista", request_id)
        try:
            response = await http_client.post(
                f"{base_url}/dokumentlista",
                json={"identitetsbeteckning": identitetsbeteckning},
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                    "X-Request-Id": request_id,
                },
            )
        except httpx.TimeoutException as exc:
            if attempt >= _MAX_ATTEMPTS:
                raise _timeout_error() from exc
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        if response.status_code >= 500:
            if attempt >= _MAX_ATTEMPTS:
                return response
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        return response


async def _fetch_dokumentlista(environment: str, identitetsbeteckning: str) -> httpx.Response:
    """One document-list call, with the same §6.1 one-time
    token-refresh-and-retry on a 401/403 that :func:`_fetch_organisationer`
    has, layered on :func:`_post_dokumentlista`'s own 5xx/timeout retry."""
    base_url = _BASE_URLS[environment]
    token = await _get_token(environment)
    response = await _post_dokumentlista(base_url, token, identitetsbeteckning)
    if response.status_code in (401, 403):
        token = await _get_token(environment, force_refresh=True)
        response = await _post_dokumentlista(base_url, token, identitetsbeteckning)
    return response


def _filings_cache_key(environment: str, identitetsbeteckning: str) -> str:
    """The block's **own** cache key, on :func:`_cache_key`'s convention with
    ``filings`` in the kind slot (D-041(h)). Its own key and its own TTL are
    what let a 20-hour-old company record travel beside a fresh document
    list, which is D-041(c)'s whole point.

    **Shared by `fetch_filings` and `fetch_financials`** (D-043(h)(1),
    D-047(f)): both attachments need this same list to decide what to do
    next, so this is one upstream call and one cache entry for the two of
    them, never two."""
    short_env = "test" if environment == _TEST else "prod"
    return f"SE:bolagsverket:filings:{short_env}:{identitetsbeteckning}"


#: One upstream `/dokumentlista` fetch in flight per cold cache key, so that
#: `fetch_filings` and `fetch_financials` called concurrently for the same
#: identifier share it rather than racing to make two (D-043(h)(3),
#: D-047(f)) — the identical hazard and the identical fix
#: ``registries/no/client.py::_inflight_accounts_fetch`` uses, for the same
#: reason: between checking the cache and registering the task here there is
#: no ``await``, so the check-then-register step is uninterruptible from the
#: event loop's point of view and the second coroutine always finds the
#: first one's task already here on a cold cache.
_inflight_dokumentlista_fetch: dict[str, asyncio.Task[tuple[dict[str, Any], bool, datetime]]] = {}


async def _do_fetch_dokumentlista_payload(
    environment: str, identitetsbeteckning: str, cache_key: str
) -> tuple[dict[str, Any], bool, datetime]:
    """The upstream call itself — everything :func:`fetch_filings` did
    before D-047(f), unchanged, including the credential check and the
    cache write. Run at most once per cold cache key:
    :func:`_fetch_dokumentlista_payload` is the only caller, and it never
    starts a second one while this one is in flight.

    Returns ``(data, cached=False, fetched_at)`` — a fresh fetch is never
    itself a cache hit, whichever of :func:`fetch_filings` /
    :func:`fetch_financials` happened to trigger it.
    """
    client_id, client_secret = _read_credentials()
    if not client_id or not client_secret:
        raise _no_credentials_error()

    response = await _fetch_dokumentlista(environment, identitetsbeteckning)

    if response.status_code == 200:
        try:
            data = response.json()
        except ValueError as exc:
            raise _malformed_response_error("the document-list request") from exc
        if not isinstance(data, dict):
            # A 200 whose body is valid JSON but not an object — the same
            # one-type-further-out failure `lookup` guards against (§6.3).
            raise _malformed_response_error("the document-list request")
    elif response.status_code == 400:
        raise _invalid_id_error(identitetsbeteckning)
    elif response.status_code in (401, 403):
        raise _unauthorized_error(response.status_code)
    elif response.status_code == 429:
        raise _rate_limited_error()
    else:
        raise _upstream_error(response.status_code)

    fetched_at = datetime.now(UTC)
    # `dokument` is not in `DokumentlistaSvar`'s `required` list, so an absent
    # key and an empty array are the same answer — and both take the 1 h TTL.
    status = "ok" if data.get("dokument") else "not_found"
    cache.set(cache_key, data, status=status, fetched_at=fetched_at)
    return data, False, fetched_at


async def _fetch_dokumentlista_payload(
    environment: str, identitetsbeteckning: str
) -> tuple[dict[str, Any], bool, datetime]:
    """The parsed `DokumentlistaSvar` body behind **both** :func:`fetch_filings`
    and :func:`fetch_financials` — one cache entry, one in-flight upstream
    call, shared regardless of which of the two callers arrives first
    (D-043(h), D-047(f)).

    Returns ``(data, cached, fetched_at)``: ``data`` is the parsed JSON body
    (never re-shaped — D-026(a)), and ``cached``/``fetched_at`` are what
    :class:`~registry_mcp.core.models.FilingHistory.provenance` is built
    from. ``fetch_financials`` builds its **own** `SourceRef` from its own
    `/dokument` fetch instead — D-047(f)'s ruling, extending D-046(d)'s "a
    discovery step is disclosed as a field, not as provenance": this list is
    what tells `financials` which document to fetch, but the fetch that
    *produced* the figures is `/dokument`, so that is the one `SourceRef`
    describes, and the list's own facts (how many reports, which period)
    reach the block as a `notes` sentence instead.
    """
    cache_key = _filings_cache_key(environment, identitetsbeteckning)

    entry = cache.get(cache_key)
    if entry is not None:
        return entry.payload, True, entry.fetched_at

    existing = _inflight_dokumentlista_fetch.get(cache_key)
    if existing is not None:
        return await existing

    task = asyncio.ensure_future(
        _do_fetch_dokumentlista_payload(environment, identitetsbeteckning, cache_key)
    )
    _inflight_dokumentlista_fetch[cache_key] = task
    try:
        return await task
    finally:
        _inflight_dokumentlista_fetch.pop(cache_key, None)


def _apply_environment_notes_to_filings(
    block: filings.FilingHistory, environment: str
) -> filings.FilingHistory:
    """N10, for the block's own provenance — the test-environment note
    applies to this ``source`` too (``tasks/T31.md`` Part B §3), and it is
    applied here rather than in the mapper so the mapper stays pure and
    environment-blind, exactly as :func:`_apply_environment_notes` does for
    the report."""
    if environment != _TEST:
        return block
    source = (
        f"{block.provenance.source} — test environment"
        if block.provenance.source
        else "Bolagsverket — test environment"
    )
    return block.model_copy(
        update={
            "provenance": block.provenance.model_copy(update={"source": source}),
            "notes": [*block.notes, _N10_TEST_ENVIRONMENT_NOTE],
        }
    )


def _apply_environment_notes_to_financials(
    block: FinancialSummary, environment: str
) -> FinancialSummary:
    """N10 for `financials`' own provenance, mirroring
    :func:`_apply_environment_notes_to_filings` exactly — the two blocks'
    provenance differ (D-047(f)), so each needs its own application."""
    if environment != _TEST:
        return block
    source = (
        f"{block.provenance.source} — test environment"
        if block.provenance.source
        else "Bolagsverket — test environment"
    )
    return block.model_copy(
        update={
            "provenance": block.provenance.model_copy(update={"source": source}),
            "notes": [*block.notes, _N10_TEST_ENVIRONMENT_NOTE],
        }
    )


async def fetch_filings(id: str) -> FilingHistory:
    """Fetch one entity's filed annual reports, consulting the cache first.

    **A failed fetch is not swallowed here.** It raises, and
    ``core/registry.py::lookup_with`` turns any ``RegistryError`` from an
    attachment into an absent block plus one ``notes`` sentence — in one
    place, once, for every country (D-042(b)). Swallowing it here as well
    would build that mechanism twice and give an empty block two meanings,
    which is the collapse D-011 and D-041(c) exist to prevent.

    Status mapping for this endpoint (D-041(h), ``tasks/T31.md`` Part B §2):
    400 → ``invalid_id``, because the identifier is the only input and D-032
    already refuses to enforce a check digit we cannot source, so upstream's
    verdict decides; 401/403 → the existing unauthorized path; 429 →
    ``rate_limited``; 5xx/timeout → ``upstream_error``/``upstream_timeout``.
    **Never ``not_found``, for any status** — including a 404, which this
    endpoint does not declare and was never observed: ``/organisationer``
    decides whether an entity exists and this call must not be able to turn
    a successful lookup into a 404 (D-041(h)). Do not code to the 400's
    ``detail`` string; two different ones were observed live for the same
    status (``registries/se/filings.py``).

    TTL asymmetry (D-041(h): 24 h for a non-empty list, 1 h for an empty
    one) is implemented by reusing ``core/cache.py``'s existing
    ``status="not_found"`` label purely for its 1 h TTL when the register
    holds no filed report — **never** raised as a ``not_found`` error on the
    read path below, unlike its use in :func:`lookup`. The reason is D-006's
    own: an empty list is the answer that goes stale the instant the company
    files, and during filing season a day-old "nothing filed" about a
    company that filed on Tuesday is wrong in the direction that harms a
    counterparty check.

    **D-047(f):** the fetch behind this function is shared with
    :func:`fetch_financials` — see :func:`_fetch_dokumentlista_payload`.
    This function's own contract (cache key, TTL, status handling) is
    otherwise exactly what it was before that task.
    """
    from registry_mcp.registries.se import rules

    identitetsbeteckning = rules.validate_id(id)
    environment = _read_environment()
    data, cached, fetched_at = await _fetch_dokumentlista_payload(environment, identitetsbeteckning)
    block = filings.map_dokumentlista(data, cached=cached, fetched_at=fetched_at)
    return _apply_environment_notes_to_filings(block, environment)


# ---------------------------------------------------------------------------
# D-043 / D-047(f),(g) — `GET /dokument/{dokumentId}`, added for
# `fetch_financials` alone. `fetch_filings` never calls this: the document
# itself stays out of scope for the filing-history use case D-041(g) ruled
# on, and is opened only for the figures it alone can carry.
# ---------------------------------------------------------------------------

_DOKUMENT_URL = "{base}/dokument/{dokument_id}"


def _no_annual_reports_error(identitetsbeteckning: str) -> RegistryError:
    """D-042(d)(3): an empty `/dokumentlista` makes `financials` **absent**,
    not an empty block — unlike `filings`, which is a present block with
    `documents: []` for the identical wire state. Raised so
    `core/registry.py::lookup_with` performs the absent-plus-note conversion
    in the one place that already does it for every attachment (D-042(b))."""
    return RegistryError(
        ErrorCode.NOT_FOUND,
        "Bolagsverket's digital annual-report channel holds no filed annual report for "
        f"{identitetsbeteckning}.",
        hint=(
            "This is a real, present answer about the channel, not a failed lookup: a "
            "paper filer, an IFRS preparer, a handelsbolag, an ekonomisk förening or a "
            "bostadsrättsförening has no digitally filed annual report to parse. Call "
            'lookup_company with include=["filings"] to see the same empty list with its '
            "own note."
        ),
        country="SE",
        registry="bolagsverket",
    )


def _multi_entry_zip_error(dokument_id: str, entry_count: int) -> RegistryError:
    """A1: report, never guess. Every zip this project has read (six K2
    filings, two K3 taxonomy specimens, `tasks/T55-recon.md`) holds exactly
    one entry."""
    return RegistryError(
        ErrorCode.UPSTREAM_ERROR,
        f"Bolagsverket's document {dokument_id} is a zip with {entry_count} entries, not "
        "the single inline-XBRL XHTML every document this project has read carries.",
        hint="This is an upstream shape this client does not understand. Report it rather than retry.",
        country="SE",
        registry="bolagsverket",
    )


def _unparseable_document_error(dokument_id: str) -> RegistryError:
    """The zip did not hold a valid iXBRL XHTML — malformed XML, or not a
    zip at all despite a 200. Never a bare ``ET.ParseError``/``zipfile.BadZipFile``
    reaching the caller (the same discipline :func:`_malformed_response_error`
    applies to a bad JSON body)."""
    return RegistryError(
        ErrorCode.UPSTREAM_ERROR,
        f"Bolagsverket's document {dokument_id} could not be read as a zip containing one "
        "well-formed iXBRL XHTML file.",
        hint="This is an upstream problem, not a bad request. Retry the call in a moment.",
        country="SE",
        registry="bolagsverket",
    )


async def _post_dokument(base_url: str, token: str, dokument_id: str) -> httpx.Response:
    """``GET {base}/dokument/{dokumentId}``, mirroring
    :func:`_post_dokumentlista`'s retry shape: one retry on a timeout or a
    5xx, never on a 4xx, a fresh ``X-Request-Id`` per attempt logged at
    DEBUG (the request id only — never the response body, which is the
    filing itself), one token-bucket token per attempt."""
    http_client = _get_client()
    attempt = 0
    response: httpx.Response | None = None
    while True:
        attempt += 1
        await _bucket.acquire()
        request_id = str(uuid.uuid4())
        logger.debug("Bolagsverket request %s for /dokument", request_id)
        try:
            response = await http_client.get(
                _DOKUMENT_URL.format(base=base_url, dokument_id=dokument_id),
                headers={
                    "Accept": "application/zip",
                    "Authorization": f"Bearer {token}",
                    "X-Request-Id": request_id,
                },
            )
        except httpx.TimeoutException as exc:
            if attempt >= _MAX_ATTEMPTS:
                raise _timeout_error() from exc
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        if response.status_code >= 500:
            if attempt >= _MAX_ATTEMPTS:
                return response
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue

        return response


async def _fetch_dokument(environment: str, dokument_id: str) -> httpx.Response:
    """One document fetch, with the same §6.1 one-time
    token-refresh-and-retry on a 401/403 every other data call here has."""
    base_url = _BASE_URLS[environment]
    token = await _get_token(environment)
    response = await _post_dokument(base_url, token, dokument_id)
    if response.status_code in (401, 403):
        token = await _get_token(environment, force_refresh=True)
        response = await _post_dokument(base_url, token, dokument_id)
    return response


def _financials_cache_key(environment: str, dokument_id: str) -> str:
    """``SE:bolagsverket:financials:{env}:{dokumentId}`` (D-047(f)) — keyed
    on the **document**, never the company: an annual report is immutable
    once filed, so a stale hit here can only be superseded by a *newer*
    document with a different id, which is what `/dokumentlista`'s own,
    separately cached, shorter-TTL answer decides. ``core/cache.py``'s
    ``_TTL_BY_KIND["financials"]`` gives this kind 30 days on a hit."""
    short_env = "test" if environment == _TEST else "prod"
    return f"SE:bolagsverket:financials:{short_env}:{dokument_id}"


def _select_latest_annual_report(
    data: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """The same newest-first sort `filings.map_dokumentlista` uses
    (`period_end` descending, then `filed_at` descending), returning the
    full sorted list — its length is the truncation-disclosure note's
    ``total`` — and the newest entry, or `None` for an empty list."""
    items = [item for item in (data.get("dokument") or []) if isinstance(item, dict)]
    items.sort(
        key=lambda d: (
            d.get("rapporteringsperiodTom") or "",
            d.get("registreringstidpunkt") or "",
        ),
        reverse=True,
    )
    return items, (items[0] if items else None)


async def fetch_financials(id: str) -> FinancialSummary:
    """Fetch this entity's key figures from its most recently filed annual
    report, consulting two caches: the `/dokumentlista` list (shared with
    :func:`fetch_filings`, see :func:`_fetch_dokumentlista_payload`) and
    this block's own, document-keyed one (:func:`_financials_cache_key`).

    **Absent, not empty, for a company with no digitally filed annual
    report** (D-042(d)(3)): raises :func:`_no_annual_reports_error`, which
    ``core/registry.py::lookup_with`` turns into an absent block plus a
    report-level note — a deliberate difference from :func:`fetch_filings`,
    which returns a *present* block with ``documents: []`` for the
    identical wire state. A fetch or parse failure (a 5xx after retry, a
    multi-entry zip, unparseable XML) is likewise absent-plus-note: this
    function raises and never swallows an error into a plausible-looking
    empty block (D-011, mirroring :func:`fetch_filings`'s own discipline).

    **Exactly one `/dokument` request**, for the most recent annual report
    only (D-047(f)); older periods are never fetched, even though
    `/dokumentlista` lists them — ``notes`` says how many exist and points
    at ``include=["filings"]`` for the rest (D-042(j)).

    **Hard rule (`tasks/T55.md` §D): the zip and the XHTML are parsed and
    discarded in this coroutine.** Nothing about the document — not the
    bytes, not the XHTML, not any ``ix:nonNumeric`` value — reaches the
    cache, a log or disk. Only
    :func:`registries.se.financials.build_period`'s return value, a
    :class:`~registry_mcp.core.models.FinancialPeriod`, is stored, under
    :func:`_financials_cache_key`.
    """
    from registry_mcp.registries.se import rules

    identitetsbeteckning = rules.validate_id(id)
    environment = _read_environment()

    data, _list_cached, _list_fetched_at = await _fetch_dokumentlista_payload(
        environment, identitetsbeteckning
    )
    documents, latest = _select_latest_annual_report(data)
    if latest is None:
        raise _no_annual_reports_error(identitetsbeteckning)

    raw_dokument_id = latest.get("dokumentId")
    if not raw_dokument_id:
        raise _malformed_response_error("the document-list request (missing dokumentId)")
    dokument_id = str(raw_dokument_id)
    total_annual_reports = len(documents)
    base_url = _BASE_URLS[environment]
    source_url = _DOKUMENT_URL.format(base=base_url, dokument_id=dokument_id)

    fin_cache_key = _financials_cache_key(environment, dokument_id)
    entry = cache.get(fin_cache_key)
    if entry is not None:
        stored_period = entry.payload.get("period")
        period = (
            FinancialPeriod.model_validate(stored_period) if stored_period is not None else None
        )
        notes = financials.summary_notes(period, total_annual_reports=total_annual_reports)
        block = FinancialSummary(
            periods=[period] if period is not None else [],
            provenance=SourceRef(
                source=financials.SOURCE_NAME,
                source_url=entry.payload.get("source_url") or source_url,
                license=financials.LICENSE,
                fetched_at=entry.fetched_at,
                cached=True,
            ),
            notes=notes,
        )
        return _apply_environment_notes_to_financials(block, environment)

    response = await _fetch_dokument(environment, dokument_id)
    if response.status_code == 200:
        zip_bytes = response.content
    elif response.status_code in (401, 403):
        raise _unauthorized_error(response.status_code)
    elif response.status_code == 429:
        raise _rate_limited_error()
    else:
        # 400 on this endpoint is Bolagsverket's own documentation bug (its
        # shared `ApiError-felbegaran` example is a check-digit complaint
        # about an identifier this endpoint does not take) and 404/5xx are
        # ordinary upstream trouble — D-041(h): never `invalid_id` here,
        # the identifier was already accepted by `/dokumentlista`.
        raise _upstream_error(response.status_code)

    try:
        xhtml_bytes = ixbrl.unzip_single_xhtml(zip_bytes)
    except ixbrl.MultiEntryZipError as exc:
        raise _multi_entry_zip_error(dokument_id, exc.entry_count) from exc
    except zipfile.BadZipFile as exc:
        raise _unparseable_document_error(dokument_id) from exc

    try:
        doc = ixbrl.parse(xhtml_bytes)
    except ET.ParseError as exc:
        raise _unparseable_document_error(dokument_id) from exc
    del xhtml_bytes, zip_bytes  # never cached, never logged — see the docstring's hard rule

    fetched_at = datetime.now(UTC)
    period = financials.build_period(doc, document_id=dokument_id)
    notes = financials.summary_notes(period, total_annual_reports=total_annual_reports)

    cache.set(
        fin_cache_key,
        {
            "period": period.model_dump(mode="json") if period is not None else None,
            "source_url": source_url,
        },
        status="ok",
        fetched_at=fetched_at,
    )

    block = FinancialSummary(
        periods=[period] if period is not None else [],
        provenance=SourceRef(
            source=financials.SOURCE_NAME,
            source_url=source_url,
            license=financials.LICENSE,
            fetched_at=fetched_at,
            cached=False,
        ),
        notes=notes,
    )
    return _apply_environment_notes_to_financials(block, environment)
