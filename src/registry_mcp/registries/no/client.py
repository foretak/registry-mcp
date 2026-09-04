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
from registry_mcp.core.models import CompanyReport, ErrorCode, RegistryError, SearchResult
from registry_mcp.registries.no import mapping

__all__ = ["aclose", "lookup", "search"]

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
