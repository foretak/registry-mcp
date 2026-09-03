"""FastAPI REST surface for registry-mcp.

Every route dispatches through ``core.registry.get_registry(country)`` — no
country-specific module is ever imported here (`DECISIONS.md` D-001, D-008),
so a second country lights this whole surface up the moment its module
registers itself. Every success response is a ``core.models`` shape (or, for
the two REST-only conveniences ``/v1/countries`` and
``/v1/{country}/validate/{id}``, a small local model — see the note above
those); every failure is a raised
:class:`~registry_mcp.core.models.RegistryError`, turned into the
``{"error": {...}}`` envelope by :mod:`registry_mcp.api.errors` (D-007).

Run with::

    uv run uvicorn registry_mcp.api.main:app --port 8080

See ``NORBIZ_SPEC.md`` §§3, 15 and ``tasks/T06.md``.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from registry_mcp import __version__
from registry_mcp.api.errors import install_error_handlers
from registry_mcp.api.ratelimit import RateLimitMiddleware
from registry_mcp.core.models import (
    CompanyReport,
    Deadline,
    DeadlineRecurrence,
    ErrorCode,
    RegistryError,
    SearchResult,
    Surface,
)
from registry_mcp.core.registry import get_registry, list_countries, list_registries

logger = logging.getLogger(__name__)

__all__ = ["app", "record_call"]

# ---------------------------------------------------------------------------
# T08's logging hook (`NORBIZ_SPEC.md` §11).
#
# `core/log.py::log_call` does not exist yet (T08 builds it). Rather than have
# every route below wait on that, or need editing once it lands, each route
# calls `record_call(...)` with exactly the keyword shape `log_call` will
# have. Until T08 wires it up, this is a no-op. T08's whole job here is:
#
#     from registry_mcp.core import log
#     registry_mcp.api.main.record_call = log.log_call
#
# — no route in this file changes.
# ---------------------------------------------------------------------------


def _noop_record_call(**_: Any) -> None:
    """Default `record_call`. Does nothing until T08 replaces it."""


record_call: Callable[..., None] = _noop_record_call


def _record(
    *,
    operation: str,
    country: str | None,
    query: str | None,
    request: Request,
    started: float,
    ok: bool,
    error_code: str | None = None,
    cached: bool | None = None,
) -> None:
    """Best-effort call into :data:`record_call`. Logging must never break a request."""
    try:
        record_call(
            surface=Surface.REST,
            operation=operation,
            country=country,
            query=query,
            user_agent=request.headers.get("user-agent"),
            latency_ms=int((time.monotonic() - started) * 1000),
            ok=ok,
            error_code=error_code,
            cached=cached,
        )
    except Exception:  # pragma: no cover - defensive; the hook must never raise
        logger.exception("record_call hook raised; ignoring")


# ---------------------------------------------------------------------------
# Static discovery files (`NORBIZ_SPEC.md` §15). Read from disk on every
# request rather than inlined into Python — T05 edits their contents without
# touching this file.
# ---------------------------------------------------------------------------

_STATIC_DIR_ENV = "REGISTRY_MCP_STATIC_DIR"


def _repo_root() -> Path:
    # .../src/registry_mcp/api/main.py -> api -> registry_mcp -> src -> repo root
    return Path(__file__).resolve().parents[3]


def _static_dir() -> Path:
    override = os.environ.get(_STATIC_DIR_ENV)
    return Path(override) if override else _repo_root() / "static"


def _server_json_path() -> Path:
    override = os.environ.get(_STATIC_DIR_ENV)
    # `server.json` lives at the repo root, a sibling of `static/`.
    base = Path(override).parent if override else _repo_root()
    return base / "server.json"


_MISSING_STATIC_HINT = (
    "Static discovery assets are not deployed on this instance. See "
    "https://github.com/foretak/registry-mcp for /llms.txt, /llms-full.txt and server.json."
)


def _serve_static(path: Path, media_type: str) -> Response:
    if not path.is_file():
        err = RegistryError(
            ErrorCode.NOT_FOUND, f"{path.name} is not available on this instance.",
            hint=_MISSING_STATIC_HINT,
        )
        return JSONResponse(status_code=err.http_status, content=err.to_dict())
    return Response(content=path.read_text(encoding="utf-8"), media_type=media_type)


def _warn_if_static_missing() -> None:
    """A missing homepage must not stop the API from booting — log and move on."""
    static_dir = _static_dir()
    if not static_dir.is_dir():
        logger.warning(
            "Static directory %s does not exist; /, /llms.txt and /llms-full.txt will 404 "
            "until %s is set or the directory is restored.",
            static_dir,
            _STATIC_DIR_ENV,
        )
    server_json = _server_json_path()
    if not server_json.is_file():
        logger.warning("server.json not found at %s; /server.json will 404.", server_json)


def _best_effort_id_format(normalised: str) -> str:
    """Group an all-digit identifier in 3s from the left, else pass it through.

    The `Registry` ABC (`core/registry.py`) has no generic "format this
    identifier the way a local would write it" hook, and `api/` must not
    import country-specific code to get one Norway-shaped (D-001, D-008). This
    heuristic happens to reproduce Norway's own convention
    ("923609016" -> "923 609 016") for any digits-only scheme; a future
    country whose convention differs from 3-digit grouping will get a
    `formatted` value here nobody local would recognise. Flagged for the
    architect as a candidate for a real `Registry.format_id` hook.
    """
    if normalised.isdigit():
        chunks = [normalised[max(i - 3, 0) : i] for i in range(len(normalised), 0, -3)]
        return " ".join(reversed(chunks))
    return normalised


# ---------------------------------------------------------------------------
# Response shapes local to the REST surface.
#
# `DECISIONS.md` D-004 pins `core/models.py` as the *whole* contract shared
# with MCP: `CompanyReport`, `SearchResult`/`SearchHit`, `Deadline`, the
# enums. The four models below are not that — `/v1/countries` and
# `/v1/{country}/validate/{id}` are REST-only conveniences with no MCP twin
# (MCP has its own `list_countries`/`validate_company_id` tools, T07's to
# shape), and the deadlines route wraps `list[Deadline]` in an envelope the
# way `SearchResult` wraps `list[SearchHit]`. None of this widens or reshapes
# a D-004 model.
# ---------------------------------------------------------------------------


class RegistryInfo(BaseModel):
    """One row of `GET /v1/countries` — mirrors `Registry.describe()`."""

    country: str = Field(examples=["NO"])
    registry: str = Field(examples=["brreg"])
    name: str = Field(examples=["Enhetsregisteret (Brønnøysundregistrene)"])
    id_scheme: str = Field(examples=["organisasjonsnummer"])
    id_example: str = Field(examples=["923609016"])
    id_description: str = Field(examples=["Nine digits with a MOD11 check digit."])
    source_url: str = Field(examples=["https://data.brreg.no/enhetsregisteret/api"])
    license: str = Field(examples=["NLOD 2.0"])
    is_stub: bool = False


class CountriesResponse(BaseModel):
    countries: list[RegistryInfo]


class ValidateResponse(BaseModel):
    """`GET /v1/{country}/validate/{id}` — format/checksum only, no network call."""

    country: str
    registry: str
    input: str
    valid: bool
    normalised: str | None = Field(
        default=None, description="Canonical form, only present when `valid` is true."
    )
    formatted: str | None = Field(
        default=None, description="Best-effort local formatting of `normalised`."
    )
    id_scheme: str
    reason: str = Field(description="Why it is (in)valid, in one sentence.")


class DeadlinesResponse(BaseModel):
    """`GET /v1/{country}/company/{id}/deadlines` — the next occurrence of each
    obligation, alongside the caveats a caller should not act without reading."""

    country: str
    registry: str
    id: str
    today: date
    deadlines: list[Deadline]
    notes: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    countries: list[str]


# ---------------------------------------------------------------------------
# OpenAPI examples
# ---------------------------------------------------------------------------

_COUNTRIES_EXAMPLE = {
    "countries": [
        {
            "country": "NO",
            "registry": "brreg",
            "name": "Enhetsregisteret (Brønnøysundregistrene)",
            "id_scheme": "organisasjonsnummer",
            "id_example": "923609016",
            "id_description": (
                "A Norwegian organisasjonsnummer (orgnr): nine digits, the ninth a "
                "MOD11 check digit."
            ),
            "source_url": "https://data.brreg.no/enhetsregisteret/api",
            "license": "NLOD 2.0",
            "is_stub": False,
        }
    ]
}

_COMPANY_EXAMPLE = {
    "country": "NO",
    "registry": "brreg",
    "id": "923609016",
    "id_formatted": "923 609 016",
    "id_scheme": "organisasjonsnummer",
    "name": "EQUINOR ASA",
    "previous_names": ["STATOIL ASA"],
    "legal_form_code": "ASA",
    "legal_form": "Public limited company",
    "legal_form_local": "Allmennaksjeselskap",
    "limited_liability": True,
    "has_board_duty": True,
    "has_annual_accounts_duty": True,
    "status": "active",
    "status_detail": "Registered and active in Enhetsregisteret.",
    "is_active": True,
    "registered_at": "1995-03-12",
    "vat_registered": True,
    "vat_number": "NO923609016MVA",
    "in_business_register": True,
    "employees": 21239,
    "employees_reported": True,
    "industry_codes": [
        {"code": "06.100", "description": "Utvinning av råolje", "scheme": "NACE", "rank": 1}
    ],
    "share_capital": 5976872600.0,
    "share_capital_currency": "NOK",
    "business_address": {
        "lines": ["Forusbeen 50"],
        "postal_code": "4035",
        "city": "STAVANGER",
        "municipality": "STAVANGER",
        "municipality_code": "1103",
        "country_code": "NO",
        "country_name": "Norge",
    },
    "confidence": 1.0,
    "confidence_basis": "exact identifier lookup in Enhetsregisteret",
    "cached": False,
    "fetched_at": "2026-09-03T09:12:44Z",
    "source": "Enhetsregisteret (Brønnøysundregistrene)",
    "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/923609016",
    "license": "NLOD 2.0",
    "notes": [],
}

_SEARCH_EXAMPLE = {
    "country": "NO",
    "registry": "brreg",
    "query": "equinor",
    "hits": [
        {
            "country": "NO",
            "registry": "brreg",
            "id": "923609016",
            "name": "EQUINOR ASA",
            "legal_form_code": "ASA",
            "legal_form": "Public limited company",
            "status": "active",
            "city": "STAVANGER",
            "municipality": "STAVANGER",
            "registered_at": "1995-03-12",
            "is_subunit": False,
            "confidence": 0.95,
            "confidence_basis": "name matches the query exactly (case-insensitive)",
            "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/923609016",
        }
    ],
    "total": 240,
    "truncated": True,
    "cached": False,
    "fetched_at": "2026-09-03T09:13:02Z",
    "hint": "240 companies match. Call lookup_company with the id of the right hit for the full report.",
}

_DEADLINES_EXAMPLE = {
    "country": "NO",
    "registry": "brreg",
    "id": "923609016",
    "today": "2026-01-15",
    "deadlines": [
        {
            "country": "NO",
            "registry": "brreg",
            "kind": "shareholder_register_statement",
            "name": "Shareholder register statement",
            "local_name": "Aksjonærregisteroppgaven (RF-1086)",
            "authority": "Skatteetaten",
            "statutory_date": "2026-01-31",
            "due_date": "2026-02-02",
            "rolled_forward": True,
            "period_label": "2025",
            "recurrence": "annual",
            "mandatory": True,
            "applies_because": (
                "AS and ASA companies must file the shareholder register statement "
                "(RF-1086) with Skatteetaten. Assumes a calendar-year accounting period."
            ),
            "days_until": 18,
        }
    ],
    "notes": [
        "One or more of these deadlines assume a calendar-year accounting period; a "
        "deviating accounting year would shift the real dates."
    ],
}

_VALIDATE_EXAMPLE = {
    "country": "NO",
    "registry": "brreg",
    "input": "923 609 016",
    "valid": True,
    "normalised": "923609016",
    "formatted": "923 609 016",
    "id_scheme": "organisasjonsnummer",
    "reason": "Nine digits with a valid MOD11 check digit.",
}

_HEALTH_EXAMPLE = {"status": "ok", "version": __version__, "countries": ["NO"]}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

_DESCRIPTION = (
    "Company data for AI agents, any country. One JSON shape, many national business "
    "registries — a `CompanyReport` from this REST API is byte-identical to the one the MCP "
    "tools return. First module: Norway's Enhetsregisteret (Brønnøysundregistrene, slug "
    "`brreg`), looked up by organisasjonsnummer (orgnr, org.nr). Also searchable as: "
    "brreg, brønnøysund, business registry, company registry, MCP.\n\n"
    "`GET /llms-full.txt` is the complete reference for an LLM caller: every endpoint, "
    "every error code and what to do about it, and the full `CompanyReport` field list."
)

_TAGS_METADATA = [
    {
        "name": "companies",
        "description": "Look up, search and compute filing deadlines for one registered entity.",
    },
    {
        "name": "meta",
        "description": "Discover what this service supports and whether it is up.",
    },
]

@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _warn_if_static_missing()
    yield


app = FastAPI(
    title="registry-mcp",
    description=_DESCRIPTION,
    version=__version__,
    contact={"url": "https://github.com/foretak/registry-mcp"},
    license_info={"name": "MIT"},
    openapi_tags=_TAGS_METADATA,
    lifespan=_lifespan,
)
app.add_middleware(RateLimitMiddleware)
install_error_handlers(app)


# ---------------------------------------------------------------------------
# Static discovery routes (`NORBIZ_SPEC.md` §15) — exempt from the rate
# limiter (`api/ratelimit.py::EXEMPT_PATHS`) and not logged (§11 is for API
# calls, not crawler reads). Excluded from the OpenAPI schema: they are not
# part of the versioned data API these docs describe.
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def homepage() -> Response:
    return _serve_static(_static_dir() / "index.html", "text/html; charset=utf-8")


@app.get("/llms.txt", include_in_schema=False)
async def llms_txt() -> Response:
    return _serve_static(_static_dir() / "llms.txt", "text/plain; charset=utf-8")


@app.get("/llms-full.txt", include_in_schema=False)
async def llms_full_txt() -> Response:
    return _serve_static(_static_dir() / "llms-full.txt", "text/plain; charset=utf-8")


@app.get("/server.json", include_in_schema=False)
async def server_json() -> Response:
    return _serve_static(_server_json_path(), "application/json; charset=utf-8")


# ---------------------------------------------------------------------------
# Meta routes
# ---------------------------------------------------------------------------


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["meta"],
    summary="Liveness probe",
    description=(
        "Liveness check for monitoring — returns 200 with the running version and the "
        "currently supported country codes whenever the process is up. Not part of the data "
        "API: it does no upstream call and has no error mode. Do not call it in a polling "
        "loop faster than your monitoring actually needs."
    ),
    responses={200: {"content": {"application/json": {"example": _HEALTH_EXAMPLE}}}},
)
async def health() -> HealthResponse:
    return HealthResponse(version=__version__, countries=list_countries())


@app.get(
    "/v1/countries",
    response_model=CountriesResponse,
    tags=["meta"],
    summary="List supported countries and registries",
    description=(
        "Discover which national business registries this service can answer for right now, "
        "and what each one's identifier looks like — for Norway, an organisasjonsnummer "
        "(orgnr) looked up in Enhetsregisteret (Brønnøysundregistrene, brreg). Call this "
        "before your first lookup in a country you have not used here before, or whenever a "
        "user names a country you are unsure is supported. Never hard-code this list in your "
        "own code — it grows as country modules are added, with no change to any other "
        "endpoint's shape. A 500 here means a bug on our side; retry once, this call has no "
        "other error mode."
    ),
    responses={200: {"content": {"application/json": {"example": _COUNTRIES_EXAMPLE}}}},
)
async def get_countries(request: Request) -> CountriesResponse:
    started = time.monotonic()
    rows = [RegistryInfo.model_validate(r.describe()) for r in list_registries()]
    _record(operation="list_countries", country=None, query=None, request=request, started=started, ok=True)
    return CountriesResponse(countries=rows)


# ---------------------------------------------------------------------------
# Company routes
# ---------------------------------------------------------------------------


@app.get(
    "/v1/{country}/company/{id}",
    response_model=CompanyReport,
    tags=["companies"],
    summary="Full report for one registered entity",
    description=(
        "Fetch everything this service knows about one company by its national identifier — "
        "for Norway (`NO`), an organisasjonsnummer/orgnr (nine digits, MOD11 check digit, "
        "e.g. `923609016`) held in Enhetsregisteret (Brønnøysundregistrene, brreg). Use this "
        "once you have the identifier — from the user, an invoice, a contract, or a `search` "
        "hit's `id`; the identifier is normalised for you, so spaces, dots and a VAT suffix "
        "('NO...MVA') are all accepted. Read `notes` before acting on the result: it carries "
        "caveats such as bankruptcy or an unclassified legal form. On `invalid_id` (400), fix "
        "the identifier or call `search` with the company name instead of retrying the same "
        "string; on `not_found` (404), the identifier is well-formed but no such entity "
        "exists — call `search`. On `upstream_error`/`upstream_timeout` (502/504) the "
        "national register is unavailable; it has already been retried once here, so wait "
        "roughly a minute and retry at most once more yourself."
    ),
    responses={200: {"content": {"application/json": {"example": _COMPANY_EXAMPLE}}}},
)
async def get_company(country: str, id: str, request: Request) -> CompanyReport:
    started = time.monotonic()
    registry = get_registry(country)
    try:
        report = await registry.lookup(id)
    except RegistryError as exc:
        _record(
            operation="lookup_company", country=country.upper(), query=id, request=request,
            started=started, ok=False, error_code=exc.code.value,
        )
        raise
    _record(
        operation="lookup_company", country=country.upper(), query=id, request=request,
        started=started, ok=True, cached=report.cached,
    )
    return report


@app.get(
    "/v1/{country}/search",
    response_model=SearchResult,
    tags=["companies"],
    summary="Find entities by name",
    description=(
        "Turn a company name into candidate identifiers — for Norway (`NO`), a name search "
        "against Enhetsregisteret (Brønnøysundregistrene, brreg). Use this when the user gave "
        "you a name rather than a number, then call the company endpoint with the `id` of the "
        "right hit for the full report; a search hit is deliberately thin and must not be "
        "acted on directly. `limit` is 1-100 (default 10); a value outside that range is a "
        "`bad_request` (400), not a silent clamp, so you learn the real range. Zero hits is "
        "not an error — `hits` is `[]`, `total` is `0`, and `hint` says what to try next: "
        "Norwegian names are registered upper-case and often carry an 'AS', 'ASA' or 'NUF' "
        "suffix worth dropping before concluding a company does not exist."
    ),
    responses={200: {"content": {"application/json": {"example": _SEARCH_EXAMPLE}}}},
)
async def search_companies(
    country: str,
    request: Request,
    q: str = Query(..., min_length=1, description="Company name to search for."),
    limit: int = Query(10, description="Maximum hits to return, 1-100."),
) -> SearchResult:
    started = time.monotonic()
    registry = get_registry(country)
    try:
        result = await registry.search(q, limit)
    except RegistryError as exc:
        _record(
            operation="search_company", country=country.upper(), query=q, request=request,
            started=started, ok=False, error_code=exc.code.value,
        )
        raise
    _record(
        operation="search_company", country=country.upper(), query=q, request=request,
        started=started, ok=True, cached=result.cached,
    )
    return result


@app.get(
    "/v1/{country}/company/{id}/deadlines",
    response_model=DeadlinesResponse,
    tags=["companies"],
    summary="Next filing deadline of each kind",
    description=(
        "Compute the next occurrence of every statutory filing obligation this entity faces, "
        "as of `today` (`YYYY-MM-DD`; defaults to the server's current UTC date — pass it "
        "explicitly whenever you want a reproducible answer). Deadlines are computed, never "
        "fetched, so the same entity and `today` always produce the same list. Quote "
        "`due_date`, not `statutory_date` — it already accounts for weekends and public "
        "holidays; `applies_because` states the legal form or flag (and any assumption) "
        "behind each date, quote it rather than presenting a date as unconditional fact. An "
        "empty list is a real answer for a bankrupt, deleted or compulsorily-liquidated "
        "entity, or a branch/sub-unit — `notes` explains why. On `bad_request` (400), "
        "`today` was not `YYYY-MM-DD` — fix the format and retry."
    ),
    responses={200: {"content": {"application/json": {"example": _DEADLINES_EXAMPLE}}}},
)
async def get_deadlines(
    country: str,
    id: str,
    request: Request,
    today: str | None = Query(
        None,
        description="Date to compute from, YYYY-MM-DD. Defaults to the server's current UTC date.",
    ),
) -> DeadlinesResponse:
    started = time.monotonic()
    registry = get_registry(country)

    if today is None:
        today_date = datetime.now(UTC).date()
    else:
        try:
            today_date = date.fromisoformat(today)
        except ValueError as exc:
            raise RegistryError(
                ErrorCode.BAD_REQUEST,
                f"{today!r} is not a valid date.",
                hint="Send `today` as YYYY-MM-DD, e.g. 2026-01-15, and retry.",
                country=country.upper(),
            ) from exc

    try:
        report = await registry.lookup(id)
        deadlines = registry.deadlines(report, today_date)
    except RegistryError as exc:
        _record(
            operation="company_deadlines", country=country.upper(), query=id, request=request,
            started=started, ok=False, error_code=exc.code.value,
        )
        raise

    notes = list(report.notes)
    has_annual = any(d.recurrence == DeadlineRecurrence.ANNUAL for d in deadlines)
    if has_annual and not any("calendar-year accounting period" in n for n in notes):
        notes.append(
            "One or more of these deadlines assume a calendar-year accounting period; a "
            "deviating accounting year would shift the real dates."
        )

    _record(
        operation="company_deadlines", country=country.upper(), query=id, request=request,
        started=started, ok=True,
    )
    return DeadlinesResponse(
        country=country.upper(),
        registry=registry.registry,
        id=report.id,
        today=today_date,
        deadlines=deadlines,
        notes=notes,
    )


@app.get(
    "/v1/{country}/validate/{id}",
    response_model=ValidateResponse,
    tags=["companies"],
    summary="Check an identifier's format and checksum",
    description=(
        "Validate a national identifier's format and checksum with no network round-trip to "
        "the national register — for Norway (`NO`), the organisasjonsnummer/orgnr MOD11 "
        "check digit. Use this to validate user input or a spreadsheet column before spending "
        "lookups: it is cheap and instant, so prefer it to a speculative company lookup. An "
        "invalid identifier is a normal `200` with `valid: false` and a `reason` — this "
        "endpoint answers a question, it does not fail. A well-formed identifier does not "
        "mean the entity exists; follow a valid result with the company endpoint if you need "
        "facts."
    ),
    responses={200: {"content": {"application/json": {"example": _VALIDATE_EXAMPLE}}}},
)
async def validate_id(country: str, id: str, request: Request) -> ValidateResponse:
    started = time.monotonic()
    registry = get_registry(country)
    try:
        normalised = registry.validate_id(id)
    except RegistryError as exc:
        _record(
            operation="validate_company_id", country=country.upper(), query=id, request=request,
            started=started, ok=True,
        )
        return ValidateResponse(
            country=country.upper(),
            registry=registry.registry,
            input=id,
            valid=False,
            id_scheme=registry.id_scheme,
            reason=exc.message,
        )
    _record(
        operation="validate_company_id", country=country.upper(), query=id, request=request,
        started=started, ok=True,
    )
    return ValidateResponse(
        country=country.upper(),
        registry=registry.registry,
        input=id,
        valid=True,
        normalised=normalised,
        formatted=_best_effort_id_format(normalised),
        id_scheme=registry.id_scheme,
        reason="Well-formed identifier.",
    )
