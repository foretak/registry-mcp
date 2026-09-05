"""FastMCP surface for registry-mcp.

Every tool dispatches through ``core.registry.get_registry(country)`` — no
Norwegian module is ever imported here (``DECISIONS.md`` D-001, D-008), so a
second country lights this whole surface up the moment its module registers
itself. Every success response is ``model_dump(mode="json")`` of the same
``core.models`` shape the REST surface (``api/main.py``) returns for that
operation — ``CompanyReport``, ``SearchResult``, ``DeadlineReport``,
``ValidationResult``, ``CountriesResponse`` — built by ``Registry.lookup``/
``.search``/``.deadline_report``/``.validate``/``.country_info`` (``DECISIONS.md``
D-004, D-010, D-012), never reshaped here. Every failure is a raised
:class:`~registry_mcp.core.models.RegistryError`, turned into a FastMCP
``ToolError``/``ResourceError`` whose text is ``json.dumps(err.to_dict())`` —
the same ``{"error": {...}}`` envelope REST emits (D-007) — never a bare
traceback.

Transports:

* Streamable HTTP, mounted at ``/mcp`` on the FastAPI app in ``api/main.py``.
* stdio, via ``python -m registry_mcp`` (``src/registry_mcp/__main__.py``) or
  the ``registry-mcp`` console script (``pyproject.toml``), both calling
  :func:`main` in this module.

See ``NORBIZ_SPEC.md``, ``DECISIONS.md`` D-002/D-003/D-004/D-007/D-010,
``KEYWORDS.md`` and ``tasks/T07.md``.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError, ToolError
from fastmcp.server.dependencies import get_http_headers
from pydantic import Field

from registry_mcp import __version__
from registry_mcp.core import log
from registry_mcp.core.models import (
    CompanyReport,
    CountriesResponse,
    DeadlineReport,
    RegistryError,
    SearchResult,
    Surface,
    ValidationResult,
)
from registry_mcp.core.registry import Registry, get_registry, list_registries
from registry_mcp.core.rules.common import parse_iso_date

logger = logging.getLogger(__name__)

__all__ = ["main", "mcp"]

# ---------------------------------------------------------------------------
# T08's logging hook (`NORBIZ_SPEC.md` §11), identical in signature to
# `api/main.py`'s `record_call` — both point at the same `core/log.py::log_call`.
# ---------------------------------------------------------------------------

record_call: Callable[..., None] = log.log_call


def _current_user_agent() -> str:
    """The client's `User-Agent` on Streamable HTTP; `"stdio"` otherwise.

    `get_http_headers()` never raises — it returns `{}` when there is no live
    HTTP request (stdio transport, or a background task with no captured
    request), which we fold into the same `"stdio"` fallback as "no header at
    all", since either way there is no real user agent to report.
    """
    return get_http_headers().get("user-agent", "stdio")


@dataclass
class _CallOutcome:
    """Mutable result the `_call_context` caller fills in as it learns more."""

    ok: bool = True
    error_code: str | None = None
    cached: bool | None = None


@contextmanager
def _call_context(
    *, operation: str, country: str | None, query: str | None
) -> Iterator[_CallOutcome]:
    """Time a tool body, turn a `RegistryError` into a `ToolError`, and always
    log via :data:`record_call` in a ``finally`` — the one place every tool
    below shares this shape (T08), instead of five copies of the same
    try/except/record boilerplate.

    Usage::

        with _call_context(operation="lookup_company", country=country, query=id) as outcome:
            report = await registry.lookup(id)
            outcome.cached = report.cached
        return report.model_dump(mode="json")

    A `RegistryError` raised inside the block is recorded as a failure and
    re-raised as a `ToolError` whose text is the D-007 JSON envelope; success
    is recorded as-is, with whatever the caller set on `outcome` (`error_code`
    for `validate_company_id`'s non-raising `invalid_id` case, `cached` for
    `lookup_company`/`search_company`).
    """
    started = time.monotonic()
    outcome = _CallOutcome()
    try:
        yield outcome
    except RegistryError as exc:
        outcome.ok = False
        outcome.error_code = exc.code.value
        raise _tool_error(exc) from exc
    finally:
        try:
            record_call(
                surface=Surface.MCP,
                operation=operation,
                country=country.upper() if country else None,
                query=query,
                user_agent=_current_user_agent(),
                latency_ms=int((time.monotonic() - started) * 1000),
                ok=outcome.ok,
                error_code=outcome.error_code,
                cached=outcome.cached,
            )
        except Exception:  # pragma: no cover - defensive; the hook must never raise
            logger.exception("record_call hook raised; ignoring")


def _tool_error(exc: RegistryError) -> ToolError:
    """The D-007 error envelope, as a FastMCP tool error rather than a traceback."""
    return ToolError(json.dumps(exc.to_dict()))


def _resource_error(exc: RegistryError) -> ResourceError:
    """The D-007 error envelope, as a FastMCP resource error rather than a traceback."""
    return ResourceError(json.dumps(exc.to_dict()))


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp: FastMCP = FastMCP(
    name="registry-mcp",
    version=__version__,
    instructions=(
        "The company registry MCP: company data for AI agents, any country. One JSON shape, "
        "many national business registries — a lookup_company report here is byte-identical "
        "to the REST API's.\n\n"
        "Two countries answer today. Norway is country=\"NO\": Enhetsregisteret / "
        "Brønnøysundregistrene (brreg), looked up by organisasjonsnummer (orgnr, org.nr), "
        "with MVA/VAT registration. The United Kingdom is country=\"GB\": Companies House, "
        "looked up by company number (company registration number, CRN) such as 00445790, "
        "with annual accounts and confirmation statement deadlines. Use \"GB\" — \"UK\" is "
        "not a country code here and is rejected. Call list_countries first if you are "
        "unsure a country is supported; it also tells you which registries need an API key "
        "(requires_api_key, api_key_env) — Companies House does, and a self-hosted "
        "deployment without COMPANIES_HOUSE_API_KEY set will answer for Norway only.\n\n"
        "Every tool error is JSON: {\"error\": {\"code\", \"message\", \"hint\"}} — parse it "
        "for what to do next rather than treating it as an opaque failure."
    ),
)


# ---------------------------------------------------------------------------
# Output schemas — the real JSON Schema of the pydantic model each tool
# already returns, in place of FastMCP's default inference over `dict[str,
# Any]` (the degenerate `{"type": "object", "additionalProperties": true}`
# measured in `research/07-product-improvements.md`). Computed once, from the
# same `core.models` classes the tool bodies already build and
# `model_dump(mode="json")`.
#
# Every tool below keeps returning that plain `model_dump(mode="json")` dict
# rather than the model instance itself, and keeps its return-type annotation
# as `dict[str, Any]`: FastMCP's `structuredContent` (and the text-content
# mirror it derives from the same value) is therefore built exactly as it was
# before this change — only the *advertised* `outputSchema` is new. That is
# what keeps this change from touching the REST≡MCP wire bytes D-004/D-010/
# D-012 pin (see `tests/test_mcp.py::test_tool_output_schemas_match_models`
# and the parity tests below).
# ---------------------------------------------------------------------------

_COMPANY_REPORT_SCHEMA = CompanyReport.model_json_schema()
_SEARCH_RESULT_SCHEMA = SearchResult.model_json_schema()
_DEADLINE_REPORT_SCHEMA = DeadlineReport.model_json_schema()
_VALIDATION_RESULT_SCHEMA = ValidationResult.model_json_schema()
_COUNTRIES_RESPONSE_SCHEMA = CountriesResponse.model_json_schema()

# ---------------------------------------------------------------------------
# Tool annotations (MCP spec `ToolAnnotations`; FastMCP accepts a plain dict
# here and converts it internally). All five tools are read-only,
# non-destructive and idempotent. `lookup_company`, `search_company` and
# `company_deadlines` call an open-world national register; `validate_
# company_id` and `list_countries` do no network I/O at all.
# ---------------------------------------------------------------------------

_READ_EXTERNAL: dict[str, Any] = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}
_READ_LOCAL: dict[str, Any] = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

# ---------------------------------------------------------------------------
# Shared parameter metadata (`Field(description=..., examples=...)`), reused
# across the tools that share a parameter's meaning.
#
# Deliberately no `pattern`/`ge`/`le` here: FastMCP derives the *runtime*
# argument validator from this same annotation, so a hard schema constraint
# is enforced before a tool body ever runs — pre-empting this project's own,
# better-hinted `RegistryError` for exactly the malformed inputs such a
# constraint would target. Verified empirically (not merely assumed): a
# `country` pattern rejects the documented "any case accepted" contract
# (`core/registry.py::get_registry`'s docstring) with a bare pydantic message
# instead of the nice `unsupported_country` envelope, and a `today` pattern
# turns `test_company_deadlines_bad_today_is_json_error`'s
# `{"error": {"code": "bad_request", ...}}` into unparsable text — breaking
# both an existing test and REST≡MCP error parity (D-004), since the REST
# query parameters carry no such constraint and would keep answering through
# `parse_iso_date`/`RegistryError` as today. Descriptions and examples carry
# the real legibility value here with none of that risk.
# ---------------------------------------------------------------------------

_ID_DESCRIPTION = (
    "The company's national identifier. Norway (country='NO'): a nine-digit "
    "organisasjonsnummer (orgnr), e.g. '923609016'; spaces, dots and a "
    "'NO...MVA' VAT suffix are accepted and normalised. United Kingdom "
    "(country='GB'): a Companies House company number (CRN), eight characters, "
    "e.g. '00445790' or 'OC303675'; a short number is zero-padded for you."
)
_ID_EXAMPLES = ["923609016", "00445790"]

_COUNTRY_DESCRIPTION = (
    "ISO-3166-1 alpha-2 country code. 'NO' = Norway (Brønnøysundregistrene / "
    "Enhetsregisteret), 'GB' = United Kingdom (Companies House). 'UK' is not "
    "a country code here and is rejected. Call list_countries for the "
    "current set rather than hard-coding one."
)
_COUNTRY_EXAMPLES = ["NO", "GB"]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    output_schema=_COMPANY_REPORT_SCHEMA,
    annotations={
        **_READ_EXTERNAL,
        "title": "Look up a company in a national business register",
    },
)
async def lookup_company(
    id: Annotated[str, Field(description=_ID_DESCRIPTION, examples=_ID_EXAMPLES)],
    country: Annotated[
        str, Field(description=_COUNTRY_DESCRIPTION, examples=_COUNTRY_EXAMPLES)
    ] = "NO",
) -> dict[str, Any]:
    """Look up a company by its national identifier and get the full CompanyReport — legal
    form, status, address, VAT registration where the register publishes it, board and
    accounts duties, employees, and more.

    `country="NO"` is the norway company lookup for the norwegian business registry:
    Brønnøysundregistrene / Enhetsregisteret (brreg), by organisasjonsnummer (orgnr,
    org.nr). `country="GB"` is the uk company lookup at Companies House, by company number
    (company registration number, CRN) — eight characters, digits or a two-letter prefix
    and six digits, e.g. 00445790 or OC303675; short numbers are zero-padded for you, and
    "UK" is not a country code here, use "GB".

    Use it once you have the identifier — from the user, an invoice, a contract, or a
    `search_company` hit's `id`; the identifier is normalised for you, so spaces, dots and
    a Norwegian VAT suffix ('NO...MVA') are all accepted. Call `list_countries` if you are
    unsure a country is supported. Read the returned `notes` before acting on the result —
    it carries caveats such as bankruptcy, dissolution, a deleted entity, or an
    unclassified legal form.

    This tool does not perform sanctions, PEP or adverse-media screening, and it does not
    verify bank account details — it returns identity and filing data from the national
    register only, never a compliance clearance or a confirmed payment detail.

    On error, this tool raises with the error text `{"error": {"code", "message",
    "hint"}}` (`DECISIONS.md` D-007). `invalid_id` means the identifier is malformed —
    fix it or call `search_company` with the company name instead of retrying the same
    string. `not_found` means the identifier is well-formed but no such entity exists —
    call `search_company`. `unsupported_country` means no module exists for that country
    yet — call `list_countries`. `upstream_error`/`upstream_timeout` means the national
    register is unavailable; it has already been retried once here, so wait roughly a
    minute before trying again yourself.
    """
    with _call_context(operation="lookup_company", country=country, query=id) as outcome:
        registry = get_registry(country)
        report = await registry.lookup(id)
        outcome.cached = report.cached
    return report.model_dump(mode="json")


@mcp.tool(
    output_schema=_SEARCH_RESULT_SCHEMA,
    annotations={
        **_READ_EXTERNAL,
        "title": "Search a national company register by name",
    },
)
async def search_company(
    name: Annotated[
        str,
        Field(
            description=(
                "Company name to search for, free text — not an identifier. Use "
                "lookup_company once you have the id of the right hit."
            ),
            examples=["Equinor", "Tesco"],
        ),
    ],
    country: Annotated[
        str, Field(description=_COUNTRY_DESCRIPTION, examples=_COUNTRY_EXAMPLES)
    ] = "NO",
    limit: Annotated[
        int,
        Field(
            description=(
                "Maximum hits to return. 1-100, default 10; a value outside that "
                "range is a bad_request, not a silent clamp."
            ),
            examples=[10, 50],
        ),
    ] = 10,
) -> dict[str, Any]:
    """Search a national company register by name, when you have a name rather than an
    identifier.

    `country="NO"` searches Brønnøysundregistrene / Enhetsregisteret (brreg) for Norwegian
    companies — the norway company lookup tool for the norwegian business registry when the
    organisasjonsnummer (orgnr, org.nr) is not yet known. `country="GB"` is the uk company
    search: Companies House by company name, returning each hit's company number
    (company registration number, CRN).

    Use it when a user gives you a company name, then call `lookup_company` with the `id`
    of the right hit for the full report — a search hit is deliberately thin (name, legal
    form, status, city) and must not be acted on directly. `limit` is 1-100 (default 10).
    Hits arrive in the register's own relevance order, so read each hit's `confidence`
    rather than assuming the first row is the best one. Zero hits is not an error: `hits`
    is `[]`, `total` is `0`, and `hint` says what to try next — Norwegian names are
    registered upper-case and often carry an 'AS', 'ASA' or 'NUF' suffix, and UK names a
    'LIMITED', 'LTD', 'PLC' or 'LLP' one, worth dropping before concluding a company does
    not exist.

    On error, this tool raises with the error text `{"error": {"code", "message",
    "hint"}}`. `bad_request` means `limit` was out of range or `name` was empty — fix and
    retry. `unsupported_country` means call `list_countries` first.
    `upstream_error`/`upstream_timeout` means the national register is unavailable; wait
    roughly a minute and retry at most once more.
    """
    with _call_context(operation="search_company", country=country, query=name) as outcome:
        registry = get_registry(country)
        result = await registry.search(name, limit)
        outcome.cached = result.cached
    return result.model_dump(mode="json")


@mcp.tool(
    output_schema=_DEADLINE_REPORT_SCHEMA,
    annotations={
        **_READ_EXTERNAL,
        "title": "Statutory filing deadlines for a company",
    },
)
async def company_deadlines(
    id: Annotated[str, Field(description=_ID_DESCRIPTION, examples=_ID_EXAMPLES)],
    country: Annotated[
        str, Field(description=_COUNTRY_DESCRIPTION, examples=_COUNTRY_EXAMPLES)
    ] = "NO",
    today: Annotated[
        str | None,
        Field(
            description=(
                "Date to compute deadlines from, YYYY-MM-DD. Defaults to the "
                "server's current UTC date — pass it explicitly for a "
                "reproducible answer. A value that is not YYYY-MM-DD is a "
                "bad_request naming the required format."
            ),
            examples=["2026-10-01"],
        ),
    ] = None,
) -> dict[str, Any]:
    """Give the next occurrence of each statutory filing deadline a company faces.

    `country="NO"` covers the Norwegian calendar (Regnskapsregisteret, Skatteetaten) for a
    company looked up by organisasjonsnummer (orgnr, org.nr) in Brønnøysundregistrene /
    Enhetsregisteret (brreg): årsregnskap, generalforsamling, skattemelding,
    aksjonærregisteroppgaven, mva-melding, a-melding. `country="GB"` covers the two
    Companies House obligations for a company number (CRN): the annual accounts filing and
    the confirmation statement (CS01).

    Pass `today` (`YYYY-MM-DD`) for a reproducible answer; it defaults to the server's
    current UTC date. Quote `due_date`, not `statutory_date`. Each deadline's
    `applies_because` states where the date came from — quote it rather than presenting a
    date as unconditional fact: for Norway it names the legal form or flag and any
    assumption behind a computed date, and for the UK it says whether the date is
    Companies House's own published figure or one this tool computed from the statutory
    period. UK dates never roll forward off a weekend or bank holiday, so `due_date`
    equals `statutory_date` there; `days_until` goes negative for a filing Companies House
    still shows as overdue rather than rolling it to the next cycle. An empty `deadlines`
    list is a real answer — for Norway a bankrupt, deleted or compulsorily-liquidated
    entity or a branch/sub-unit, and for the UK any company whose status is not active —
    and `notes` explains why.

    On error, this tool raises with the error text `{"error": {"code", "message",
    "hint"}}`. `bad_request` means `today` was not `YYYY-MM-DD` — fix the format and
    retry. Any `lookup_company` error code (`invalid_id`, `not_found`,
    `unsupported_country`, `upstream_error`, `upstream_timeout`) can also surface here,
    since this tool looks the entity up first — follow that code's hint.
    """
    with _call_context(operation="company_deadlines", country=country, query=id):
        registry = get_registry(country)
        today_date = parse_iso_date(today, field="today")
        report = await registry.lookup(id)
        result = registry.deadline_report(report, today_date)
    return result.model_dump(mode="json")


@mcp.tool(
    output_schema=_VALIDATION_RESULT_SCHEMA,
    annotations={
        **_READ_LOCAL,
        "title": "Validate a company identifier (no network call)",
    },
)
def validate_company_id(
    id: Annotated[str, Field(description=_ID_DESCRIPTION, examples=_ID_EXAMPLES)],
    country: Annotated[
        str, Field(description=_COUNTRY_DESCRIPTION, examples=_COUNTRY_EXAMPLES)
    ] = "NO",
) -> dict[str, Any]:
    """Check whether a national company identifier is well-formed — no network call.

    `country="NO"` checksum-checks a Norwegian organisasjonsnummer (orgnr, org.nr) for
    Brønnøysundregistrene / Enhetsregisteret (brreg); this is the cheap norway company
    lookup pre-check for the norwegian business registry. `country="GB"` shape-checks and
    normalises a UK company number (company registration number, CRN) for Companies House:
    it zero-pads a short number ('445790' → '00445790') and upper-cases a prefix
    ('oc303675' → 'OC303675'). A CRN has no check digit, so a GB `valid: true` means the
    shape is right and nothing more.

    Use it on user input or a spreadsheet column before spending a real `lookup_company`
    call, since it is instant and free.

    Returns a ValidationResult and never raises for a malformed identifier: `valid: false`
    comes with `reason` (what failed) and `hint` (what to do next) rather than a tool
    error — this tool answers a question, it does not fail on bad input
    (`DECISIONS.md` D-010). A valid identifier does not mean the entity exists; follow it
    with `lookup_company` if you need facts.

    The only real error here is `unsupported_country` (no module for that country yet —
    call `list_countries`), raised with the error text `{"error": {"code", "message",
    "hint"}}`.
    """
    with _call_context(operation="validate_company_id", country=country, query=id) as outcome:
        registry = get_registry(country)
        result = registry.validate(id)
        if not result.valid:
            outcome.error_code = "invalid_id"
    return result.model_dump(mode="json")


@mcp.tool(
    output_schema=_COUNTRIES_RESPONSE_SCHEMA,
    annotations={
        **_READ_LOCAL,
        "title": "List supported national company registries",
    },
)
def list_countries() -> dict[str, Any]:
    """List every national company registry this service can answer for right now, plus
    each one's identifier scheme (`id_scheme`, `id_example`, `id_description`), source URL,
    licence, and whether the upstream register needs a credential (`requires_api_key`, and
    `api_key_env` naming the environment variable that must be set for it).

    Call this before your first lookup in a country you have not used here before, or
    whenever a user names a country you are unsure is supported — never hard-code a
    country list of your own, since it grows as registry modules are added with no change
    to any other tool's shape. Stub/example modules are hidden; only registries that
    actually answer are listed. This tool has no error mode; a failure here is a bug, not
    something to retry differently.
    """
    with _call_context(operation="list_countries", country=None, query=None):
        result = CountriesResponse(countries=[r.country_info() for r in list_registries()])
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Resource
# ---------------------------------------------------------------------------


@mcp.resource("registry://rules/{country}")
def rules_resource(country: str) -> str:
    """Human/LLM-readable rules summary for one country's registry — legal/organisational
    forms, status derivation, and the filing deadlines this service computes — so an agent
    can read the rules once instead of rediscovering them one tool call at a time.

    URI: `registry://rules/{country}`, e.g. `registry://rules/NO` for Brønnøysundregistrene
    / Enhetsregisteret. An unsupported country raises with the error text
    `{"error": {"code": "unsupported_country", ...}}`, whose `hint` names `list_countries`.
    """
    try:
        registry = get_registry(country)
    except RegistryError as exc:
        raise _resource_error(exc) from exc
    return registry.rules_markdown()


# ---------------------------------------------------------------------------
# Concrete per-country rules resources (`research/07-product-improvements.md`
# item 9). `resources/list` only ever enumerates concrete resources, never
# templates — a client that calls it and nothing else never learns
# `rules_resource` above exists at all, template matching only happens on a
# `resources/read` for a URI nothing concrete claims. Registering one
# concrete resource per country closes that without retiring the template:
# FastMCP tries concrete resources before templates (same URI, same result),
# and `resources/templates/list` still advertises the general pattern for any
# country added after this module was imported.
# ---------------------------------------------------------------------------


def _rules_reader(target: Registry) -> Callable[[], str]:
    """A zero-argument function bound to one registry.

    A concrete `@mcp.resource` is exactly a URI with no `{param}` *and* a
    function with no parameters (FastMCP's own rule — see `rules_resource`'s
    docstring above); the closure is what lets one country's registration
    below read `target` without taking it as an argument.
    """

    def _read() -> str:
        return target.rules_markdown()

    return _read


def _register_concrete_rules_resources() -> None:
    """Register `registry://rules/{cc}` concretely for every live registry.

    ``list_registries()`` already hides stub modules (D-008), so this walks
    exactly the countries `list_countries()` advertises — no country string
    is hard-coded here. Called once, at import time: a second or third
    country lights up in `resources/list` the moment its module registers
    itself, with no edit to this file.
    """
    for target in list_registries():
        mcp.resource(
            f"registry://rules/{target.country}",
            name=f"rules_{target.country.lower()}",
            title=f"{target.name} rules ({target.country})",
            description=(
                f"Identifier rules, legal forms and filing-deadline rules for "
                f"{target.name} ({target.country}) — the same document the "
                "registry://rules/{country} template serves for this country, "
                "listed concretely so it appears in resources/list."
            ),
            mime_type="text/markdown",
        )(_rules_reader(target))


_register_concrete_rules_resources()


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


@mcp.prompt
def explain_company(id: str, country: str = "NO") -> str:
    """Explain one company for a non-expert reader: call lookup + deadlines and summarise."""
    return (
        f"Call lookup_company(id={id!r}, country={country!r}) to get the company's full "
        f"report, then call company_deadlines(id={id!r}, country={country!r}) to get its "
        "upcoming filing deadlines. Using both results, write a short, plain-English "
        "summary for someone who is not an accountant or lawyer: what the company is "
        "(name, legal form, status), whether it is currently active, and what it must "
        "file next and by when. If `status` is not active, lead with that. If `notes` on "
        "either result is non-empty, mention the caveats it names, in plain language. If "
        "either call fails, explain the error's `hint` in plain English instead of "
        "showing raw JSON."
    )


# ---------------------------------------------------------------------------
# stdio entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Console-script / `python -m registry_mcp` entry point: serve over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
