"""FastAPI REST surface for registry-mcp.

Every route dispatches through ``core.registry.get_registry(country)`` — no
country-specific module is ever imported here (`DECISIONS.md` D-001, D-008),
so a second country lights this whole surface up the moment its module
registers itself. Every success response is a ``core.models`` shape — the
deadlines and validate operations return ``DeadlineReport`` /
``ValidationResult`` built by ``Registry.deadline_report`` /
``Registry.validate`` (`DECISIONS.md` D-010), never assembled here — and
``/v1/countries`` returns a small REST-only convenience model with no MCP
twin. Every failure is a raised
:class:`~registry_mcp.core.models.RegistryError`, turned into the
``{"error": {...}}`` envelope by :mod:`registry_mcp.api.errors` (D-007).

Run with::

    uv run uvicorn registry_mcp.api.main:app --port 8080

See ``NORBIZ_SPEC.md`` §§3, 15, ``DECISIONS.md`` D-010 and ``tasks/T06.md``.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, Response
from fastmcp.server.http import StarletteWithLifespan
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.routing import Route as StarletteRoute

from registry_mcp import __version__
from registry_mcp.api.dashboard import dashboard_router
from registry_mcp.api.errors import install_error_handlers
from registry_mcp.api.ratelimit import RateLimitMiddleware
from registry_mcp.api.stats import stats_router
from registry_mcp.api.status import status_router
from registry_mcp.core import log
from registry_mcp.core.models import (
    CompanyReport,
    CountriesResponse,
    DeadlineReport,
    ErrorCode,
    RegistryError,
    SearchResult,
    Surface,
    ValidationResult,
)
from registry_mcp.core.registry import (
    get_registry,
    list_countries,
    list_registries,
    loggable_query,
)
from registry_mcp.core.rules.common import parse_iso_date
from registry_mcp.mcp.server import mcp as mcp_server

logger = logging.getLogger(__name__)

__all__ = ["app", "record_call"]

# ---------------------------------------------------------------------------
# T08's logging hook (`NORBIZ_SPEC.md` §11): every route below calls
# `record_call(...)` with exactly `core/log.py::log_call`'s keyword shape, so
# wiring it in is this one assignment — no route changes. Static routes (`/`,
# `/llms.txt`, `/llms-full.txt`, `/server.json`) and `/health` deliberately
# never call `_record`/`record_call` at all (`NORBIZ_SPEC.md` §15): they are
# crawler/monitoring reads, not API calls, and logging them would drown the
# per-agent signal `/v1/stats` exists to show.
# ---------------------------------------------------------------------------

record_call: Callable[..., None] = log.log_call


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
            query=loggable_query(country, query),
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


def _missing_static_response(path: Path) -> JSONResponse:
    err = RegistryError(
        ErrorCode.NOT_FOUND, f"{path.name} is not available on this instance.",
        hint=_MISSING_STATIC_HINT,
    )
    return JSONResponse(status_code=err.http_status, content=err.to_dict())


def _serve_static(path: Path, media_type: str) -> Response:
    if not path.is_file():
        return _missing_static_response(path)
    return Response(content=path.read_text(encoding="utf-8"), media_type=media_type)


def _serve_static_bytes(path: Path, media_type: str) -> Response:
    """Binary sibling of :func:`_serve_static`, for an asset that is not
    UTF-8 text — currently just `icon.png` (backlog item C, the Cline
    marketplace / Smithery / Glama / mcp.so icon)."""
    if not path.is_file():
        return _missing_static_response(path)
    return Response(content=path.read_bytes(), media_type=media_type)


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


# ---------------------------------------------------------------------------
# Response shapes local to the REST surface.
#
# `DECISIONS.md` D-004/D-010/D-012 pin `core/models.py` as the *whole*
# contract shared with MCP: `CompanyReport`, `SearchResult`/`SearchHit`,
# `Deadline`, `DeadlineReport`, `ValidationResult`, `CountriesResponse`/
# `CountryInfo`, the enums. `/v1/countries` used to have its own private
# `RegistryInfo`/`CountriesResponse` pair here — a plain `BaseModel` that
# silently *dropped* an unrecognised key, while `mcp/server.py` passed the
# raw `Registry.describe()` dict through and *kept* it — a latent divergence
# with no test to catch it (D-012). Both surfaces now build
# `core.models.CountriesResponse` from `Registry.country_info()` instead.
# ---------------------------------------------------------------------------


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
            "country": "GB",
            "registry": "companies-house",
            "name": "Companies House (United Kingdom)",
            "id_scheme": "company number",
            "id_example": "00445790",
            "id_description": (
                "A UK company registration number (CRN): 8 characters, either 8 digits "
                "or a two-letter prefix and 6 digits. Shorter numbers are zero-padded, "
                "so 445790 is written 00445790. There is no check digit."
            ),
            "source_url": "https://api.company-information.service.gov.uk",
            "license": "Crown copyright — Companies House public register, free to re-use",
            "is_stub": False,
            "requires_api_key": True,
            "api_key_env": "COMPANIES_HOUSE_API_KEY",
        },
        {
            "country": "NO",
            "registry": "brreg",
            "name": "Enhetsregisteret (Brønnøysundregistrene)",
            "id_scheme": "organisasjonsnummer",
            "id_example": "923609016",
            "id_description": (
                "A Norwegian organisasjonsnummer (orgnr): nine digits, the ninth a "
                "MOD11 check digit. Written '923 609 016' or '923609016'; a VAT number "
                "adds 'MVA'."
            ),
            "source_url": "https://data.brreg.no/enhetsregisteret/api",
            "license": "NLOD 2.0",
            "is_stub": False,
            "requires_api_key": False,
            "api_key_env": None,
        },
        {
            "country": "SE",
            "registry": "bolagsverket",
            "name": "Bolagsverket (Sweden)",
            "id_scheme": "organisationsnummer",
            "id_example": "5560160680",
            "id_description": (
                "A Swedish organisationsnummer: ten digits, written 556016-0680, with a "
                "check digit. A sole trader is looked up by a twelve-digit personnummer "
                "instead (YYYYMMDDNNNN), and one such number can carry several registered "
                "businesses."
            ),
            "source_url": "https://gw.api.bolagsverket.se/vardefulla-datamangder/v1",
            "license": (
                "Free re-use (Bolagsverket/SCB high-value datasets, EU Open Data "
                "Directive) — the publisher names no licence"
            ),
            "is_stub": False,
            "requires_api_key": True,
            "api_key_env": "BOLAGSVERKET_CLIENT_ID",
        },
    ]
}

_COMPANY_EXAMPLE = {
    "country": "NO",
    "registry": "brreg",
    "id": "923609016",
    "id_formatted": "923 609 016",
    "id_scheme": "organisasjonsnummer",
    "euid": None,
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
    "advertising_protected": None,
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
    "company_id": "923609016",
    "company_name": "EQUINOR ASA",
    "today": "2026-10-01",
    "deadlines": [
        {
            "country": "NO",
            "registry": "brreg",
            "kind": "shareholder_register_statement",
            "name": "Shareholder register statement",
            "local_name": "Aksjonærregisteroppgaven (RF-1086)",
            "authority": "Skatteetaten",
            "statutory_date": "2027-01-31",
            "due_date": "2027-02-01",
            "rolled_forward": True,
            "period_label": "2026",
            "recurrence": "annual",
            "mandatory": True,
            "applies_because": (
                "An ASA company must file the shareholder register statement "
                "(RF-1086) with Skatteetaten (skatteforvaltningsforskriften "
                "§ 7-7-4(1))."
            ),
            "days_until": 123,
        }
    ],
    "notes": [
        "Filing deadlines are computed assuming a calendar-year accounting period. "
        "Enhetsregisteret does not publish a company's accounting year. For a "
        "financial year ending between 1 January and 30 June, regnskapsloven "
        "§ 8-3(1) sets a different deadline — 1 February, not 31 July — so a "
        "deviating year changes which rule applies, not just the date. The "
        "Ministry may also postpone the accounts deadline by up to one month by "
        "regulation (§ 8-3(1)). Verify against Regnskapsregisteret before relying "
        "on an annual date."
    ],
}

_VALIDATE_EXAMPLE = {
    "country": "NO",
    "registry": "brreg",
    "id_scheme": "organisasjonsnummer",
    "input": "923 609 016",
    "valid": True,
    "normalized": "923609016",
    "formatted": "923 609 016",
    "reason": (
        "Well-formed organisasjonsnummer for NO. A valid identifier does not mean the "
        "entity exists — call lookup_company (MCP) or GET /v1/{country}/company/{id} "
        "(REST) to find out."
    ),
    "hint": None,
}

_HEALTH_EXAMPLE = {"status": "ok", "version": __version__, "countries": ["NO"]}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

_DESCRIPTION = (
    "The company registry MCP: company data for AI agents, any country. One JSON shape, "
    "many national business registries — a `CompanyReport` from this REST API is "
    "byte-identical to the one the MCP tools return.\n\n"
    "Two countries answer today. **Norway** (`/v1/NO/…`) — Enhetsregisteret "
    "(Brønnøysundregistrene, slug `brreg`), looked up by organisasjonsnummer (orgnr, "
    "org.nr), with MVA/VAT registration status. **United Kingdom** (`/v1/GB/…`) — "
    "Companies House, looked up by company number (company registration number, CRN) such "
    "as `00445790`, with annual accounts and confirmation statement deadlines. The code is "
    "`GB`; `/v1/UK/…` is a `404 unsupported_country`. `GET /v1/countries` is the live list "
    "and names any registry that needs a credential (`requires_api_key`, `api_key_env`).\n\n"
    "Also searchable as: brreg, brønnøysund, enhetsregisteret, organisasjonsnummer, "
    "norway company lookup, Companies House, company number, uk company lookup, "
    "uk company search, confirmation statement, business registry, company registry, MCP.\n\n"
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

# ---------------------------------------------------------------------------
# MCP surface (T07). `mcp.http_app(path="/mcp")` builds a Starlette app with
# one internal `Route("/mcp", ...)`. Its lifespan starts/stops the session
# manager and must be composed into this app's own lifespan (`_lifespan`
# below) — FastAPI does not run a mounted sub-app's lifespan on its own.
#
# **Not `app.mount("/mcp", ...)`** (T07's original choice, corrected here per
# T13's `deploy.md` finding and `PROGRESS.md`'s T13 note): a Starlette `Mount`
# compiles its path as `<mount_path>/{path:path}` (`starlette/routing.py`),
# which only ever matches `<mount_path>/` plus a remainder — it never matches
# the bare mount path with no trailing slash at all. A bare `POST /mcp` only
# "worked" through `Router.app`'s redirect-slash fallback, which is
# asymmetric: it 307-redirects whichever trailing-slash variant has no
# direct route match to the one that does. `fastmcp.Client`'s Streamable HTTP
# transport does not follow a POST redirect, so any agent given the URL this
# project advertises everywhere without a trailing slash (`server.json`,
# `llms.txt`, `README.md`, the articles) silently failed.
#
# The fix: register the same underlying ASGI endpoint directly as two exact
# `Route`s, `/mcp` and `/mcp/`, on this app's own router (`_register_mcp_routes`
# below) instead of `Mount`ing a sub-app — both then match `Match.FULL`
# immediately, in either direction, with no redirect involved at all.
# ---------------------------------------------------------------------------

_mcp_app = mcp_server.http_app(path="/mcp")


def _register_mcp_routes(fastapi_app: FastAPI, mcp_app: StarletteWithLifespan) -> None:
    """Serve `mcp_app`'s one Streamable HTTP endpoint at both `/mcp` and `/mcp/`.

    Reuses the exact `Route` (and its `endpoint`/`methods`) `mcp.http_app()`
    built, so the session-manager lifespan (which mutates that same endpoint
    object in place on startup) applies no matter which of the two paths a
    request arrives on.
    """
    (mcp_route,) = [r for r in mcp_app.routes if isinstance(r, StarletteRoute)]
    for path in ("/mcp", "/mcp/"):
        fastapi_app.router.routes.append(
            StarletteRoute(
                path,
                endpoint=mcp_route.endpoint,
                methods=list(mcp_route.methods) if mcp_route.methods else None,
            )
        )


async def _close_registry_clients() -> None:
    """Close any HTTP client a registry module owns, on shutdown.

    `Registry.aclose()` (`core/registry.py`, `DECISIONS.md` D-014) is a
    concrete, always-present ABC method — a no-op by default, overridden by a
    country module that keeps a shared client (`BrregRegistry.aclose()`
    delegates to `registries/no/client.py::aclose()`). Called on every
    registered registry (stubs included, since a future stub's resources
    should still be released), so this is a real interface call rather than
    the `getattr` probe it used to be before D-014 gave the ABC this method.
    """
    for reg in list_registries(include_stubs=True):
        try:
            await reg.aclose()
        except Exception:  # pragma: no cover - defensive; shutdown must not crash
            logger.exception("Registry %s aclose() failed during shutdown", reg.country)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _warn_if_static_missing()
    try:
        async with _mcp_app.lifespan(_app):
            yield
    finally:
        # `finally`, not a plain statement after the `async with`: a shutdown
        # that raises out of the MCP session manager's own `__aexit__` must
        # still release registry clients (`DECISIONS.md` D-014, REVIEW.md B3).
        await _close_registry_clients()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach ``X-Request-ID`` to every response: echo the caller's, or mint one.

    A small, non-breaking trace-correlation primitive (backlog item 5,
    ``research/07-product-improvements.md`` #9). Header only, deliberately:
    ``core/models.py``'s ``ErrorBody`` is the D-007 error envelope, and this
    task does not touch ``core/`` — adding a field there would be the more
    thorough place to carry a request id, but it is out of scope here, so the
    header is the whole feature. Registered *after* :class:`RateLimitMiddleware`
    below so it becomes the outermost middleware (Starlette's
    ``add_middleware`` prepends), guaranteeing the header on a rate-limited
    ``429`` too, not only on a normal response.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


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
app.add_middleware(RequestIDMiddleware)
install_error_handlers(app)
app.include_router(stats_router)
app.include_router(dashboard_router)
app.include_router(status_router)
_register_mcp_routes(app, _mcp_app)


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


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> Response:
    return _serve_static(_static_dir() / "robots.txt", "text/plain; charset=utf-8")


@app.get("/icon.png", include_in_schema=False)
async def icon_png() -> Response:
    """400x400 PNG mark (`static/icon.png`) — same static mechanism as
    `/robots.txt` above, just binary. Referenced from `static/index.html`'s
    JSON-LD `image` and from `server.json`'s `icons`, and is what a directory
    that reads either (Smithery, Glama, mcp.so) or the Cline marketplace
    (which requires one) shows next to this server's listing."""
    return _serve_static_bytes(_static_dir() / "icon.png", "image/png")


@app.get("/.well-known/mcp/server-card.json", include_in_schema=False)
async def well_known_mcp_server_card() -> Response:
    return _serve_static(
        _static_dir() / "well-known" / "mcp" / "server-card.json",
        "application/json; charset=utf-8",
    )


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
    rows = [r.country_info() for r in list_registries()]
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
    response_model=DeadlineReport,
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
) -> DeadlineReport:
    started = time.monotonic()
    registry = get_registry(country)
    today_date = parse_iso_date(today, field="today")

    try:
        report = await registry.lookup(id)
    except RegistryError as exc:
        _record(
            operation="company_deadlines", country=country.upper(), query=id, request=request,
            started=started, ok=False, error_code=exc.code.value,
        )
        raise

    result = registry.deadline_report(report, today_date)
    _record(
        operation="company_deadlines", country=country.upper(), query=id, request=request,
        started=started, ok=True,
    )
    return result


@app.get(
    "/v1/{country}/validate/{id}",
    response_model=ValidationResult,
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
async def validate_id(country: str, id: str, request: Request) -> ValidationResult:
    # No try/except: `Registry.validate` (D-010) already turns an `invalid_id`
    # failure into `valid=False` rather than raising — this operation answers
    # a question, it does not fail (`DECISIONS.md` D-010, the one deliberate
    # exception to D-007). Any other `RegistryError` (e.g. unsupported
    # country, already raised by `get_registry` above) still propagates.
    started = time.monotonic()
    registry = get_registry(country)
    result = registry.validate(id)
    _record(
        operation="validate_company_id", country=country.upper(), query=id, request=request,
        started=started, ok=True, error_code=None if result.valid else "invalid_id",
    )
    return result
