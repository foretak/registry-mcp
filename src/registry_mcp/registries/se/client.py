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
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from registry_mcp import __version__
from registry_mcp.core import cache
from registry_mcp.core.models import CompanyReport, ErrorCode, RegistryError, SearchResult
from registry_mcp.registries.se import mapping

__all__ = ["aclose", "lookup", "search"]

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
