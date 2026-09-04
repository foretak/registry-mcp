"""FastMCP surface for registry-mcp.

Every tool dispatches through ``core.registry.get_registry(country)`` — no
Norwegian module is ever imported here (``DECISIONS.md`` D-001, D-008), so a
second country lights this whole surface up the moment its module registers
itself. Every success response is ``model_dump(mode="json")`` of the same
``core.models`` shape the REST surface (``api/main.py``) returns for that
operation — ``CompanyReport``, ``SearchResult``, ``DeadlineReport``,
``ValidationResult`` — built by ``Registry.lookup``/``.search``/
``.deadline_report``/``.validate`` (``DECISIONS.md`` D-004, D-010), never
reshaped here. Every failure is a raised
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
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError, ToolError

from registry_mcp import __version__
from registry_mcp.core.models import ErrorCode, RegistryError, Surface
from registry_mcp.core.registry import get_registry, list_registries

logger = logging.getLogger(__name__)

__all__ = ["main", "mcp"]

# ---------------------------------------------------------------------------
# T08's logging hook (`NORBIZ_SPEC.md` §11), identical in signature to
# `api/main.py`'s `record_call`. A no-op until T08 replaces the pointer:
#
#     from registry_mcp.core import log
#     registry_mcp.mcp.server.record_call = log.log_call
#
# — no tool below changes.
# ---------------------------------------------------------------------------


def _noop_record_call(**_: Any) -> None:
    """Default `record_call`. Does nothing until T08 replaces it."""


record_call: Callable[..., None] = _noop_record_call


def _record(
    *,
    operation: str,
    country: str | None,
    query: str | None,
    started: float,
    ok: bool,
    error_code: str | None = None,
    cached: bool | None = None,
) -> None:
    """Best-effort call into :data:`record_call`. Logging must never break a tool call."""
    try:
        record_call(
            surface=Surface.MCP,
            operation=operation,
            country=country,
            query=query,
            user_agent=None,
            latency_ms=int((time.monotonic() - started) * 1000),
            ok=ok,
            error_code=error_code,
            cached=cached,
        )
    except Exception:  # pragma: no cover - defensive; the hook must never raise
        logger.exception("record_call hook raised; ignoring")


def _tool_error(exc: RegistryError) -> ToolError:
    """The D-007 error envelope, as a FastMCP tool error rather than a traceback."""
    return ToolError(json.dumps(exc.to_dict()))


def _resource_error(exc: RegistryError) -> ResourceError:
    """The D-007 error envelope, as a FastMCP resource error rather than a traceback."""
    return ResourceError(json.dumps(exc.to_dict()))


def _parse_today(today: str | None, *, country: str) -> date:
    """Same parsing/error shape as `api/main.py::get_deadlines` — kept local because
    `core/` (owned by other tasks) has no shared date-parsing hook to call instead."""
    if today is None:
        return datetime.now(UTC).date()
    try:
        return date.fromisoformat(today)
    except ValueError as exc:
        raise RegistryError(
            ErrorCode.BAD_REQUEST,
            f"{today!r} is not a valid date.",
            hint="Send `today` as YYYY-MM-DD, e.g. 2026-01-15, and retry.",
            country=country.upper(),
        ) from exc


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp: FastMCP = FastMCP(
    name="registry-mcp",
    version=__version__,
    instructions=(
        "Company data for AI agents, any country. One JSON shape, many national business "
        "registries — a lookup_company report here is byte-identical to the REST API's. "
        "First module: Norway's Enhetsregisteret (Brønnøysundregistrene, brreg), looked up "
        "by organisasjonsnummer (orgnr, org.nr). Call list_countries first if you are unsure "
        "a country is supported. Every tool error is JSON: {\"error\": {\"code\", "
        "\"message\", \"hint\"}} — parse it for what to do next rather than treating it as "
        "an opaque failure."
    ),
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool
async def lookup_company(id: str, country: str = "NO") -> dict[str, Any]:
    """Look up a Norwegian company in Brønnøysundregistrene / Enhetsregisteret (brreg) by
    organisasjonsnummer (orgnr, org.nr). This is the norway company lookup tool for the
    norwegian business registry: it returns the full CompanyReport — legal form, status,
    address, VAT registration, board and accounts duties, employees, and more.

    Use it once you have the identifier — from the user, an invoice, a contract, or a
    `search_company` hit's `id`; the identifier is normalised for you, so spaces, dots and
    a VAT suffix ('NO...MVA') are all accepted. Only `country="NO"` is implemented today;
    call `list_countries` first if you are unsure a country is supported. Read the
    returned `notes` before acting on the result — it carries caveats such as bankruptcy,
    a deleted entity, or an unclassified legal form.

    On error, this tool raises with the error text `{"error": {"code", "message",
    "hint"}}` (`DECISIONS.md` D-007). `invalid_id` means the identifier is malformed —
    fix it or call `search_company` with the company name instead of retrying the same
    string. `not_found` means the identifier is well-formed but no such entity exists —
    call `search_company`. `unsupported_country` means no module exists for that country
    yet — call `list_countries`. `upstream_error`/`upstream_timeout` means the national
    register is unavailable; it has already been retried once here, so wait roughly a
    minute before trying again yourself.
    """
    started = time.monotonic()
    try:
        registry = get_registry(country)
        report = await registry.lookup(id)
    except RegistryError as exc:
        _record(
            operation="lookup_company", country=country.upper(), query=id,
            started=started, ok=False, error_code=exc.code.value,
        )
        raise _tool_error(exc) from exc
    _record(
        operation="lookup_company", country=report.country, query=id,
        started=started, ok=True, cached=report.cached,
    )
    return report.model_dump(mode="json")


@mcp.tool
async def search_company(name: str, country: str = "NO", limit: int = 10) -> dict[str, Any]:
    """Search Brønnøysundregistrene / Enhetsregisteret (brreg) for Norwegian companies by
    name, when you have a name rather than an organisasjonsnummer (orgnr, org.nr). This is
    the norway company lookup tool for the norwegian business registry when the identifier
    is not yet known.

    Use it when a user gives you a company name, then call `lookup_company` with the `id`
    of the right hit for the full report — a search hit is deliberately thin (name, legal
    form, status, city) and must not be acted on directly. `limit` is 1-100 (default 10).
    Zero hits is not an error: `hits` is `[]`, `total` is `0`, and `hint` says what to try
    next — Norwegian names are registered upper-case and often carry an 'AS', 'ASA' or
    'NUF' suffix worth dropping before concluding a company does not exist.

    On error, this tool raises with the error text `{"error": {"code", "message",
    "hint"}}`. `bad_request` means `limit` was out of range or `name` was empty — fix and
    retry. `unsupported_country` means call `list_countries` first.
    `upstream_error`/`upstream_timeout` means the national register is unavailable; wait
    roughly a minute and retry at most once more.
    """
    started = time.monotonic()
    try:
        registry = get_registry(country)
        result = await registry.search(name, limit)
    except RegistryError as exc:
        _record(
            operation="search_company", country=country.upper(), query=name,
            started=started, ok=False, error_code=exc.code.value,
        )
        raise _tool_error(exc) from exc
    _record(
        operation="search_company", country=result.country, query=name,
        started=started, ok=True, cached=result.cached,
    )
    return result.model_dump(mode="json")


@mcp.tool
async def company_deadlines(
    id: str, country: str = "NO", today: str | None = None
) -> dict[str, Any]:
    """Compute the next occurrence of every Norwegian filing deadline (Regnskapsregisteret,
    Skatteetaten) a company faces, looked up by organisasjonsnummer (orgnr, org.nr) in
    Brønnøysundregistrene / Enhetsregisteret (brreg). This is the norway company lookup
    companion tool for the norwegian business registry's statutory calendar.

    Deadlines are computed, never fetched, so the same entity and `today` always produce
    the same list — pass `today` (`YYYY-MM-DD`) for a reproducible answer; it defaults to
    the server's current UTC date. Quote `due_date`, not `statutory_date` — it already
    accounts for weekends and public holidays; each deadline's `applies_because` states
    the legal form or flag (and any assumption) behind it, quote it rather than presenting
    a date as unconditional fact. An empty `deadlines` list is a real answer for a
    bankrupt, deleted or compulsorily-liquidated entity, or a branch/sub-unit — `notes`
    explains why.

    On error, this tool raises with the error text `{"error": {"code", "message",
    "hint"}}`. `bad_request` means `today` was not `YYYY-MM-DD` — fix the format and
    retry. Any `lookup_company` error code (`invalid_id`, `not_found`,
    `unsupported_country`, `upstream_error`, `upstream_timeout`) can also surface here,
    since this tool looks the entity up first — follow that code's hint.
    """
    started = time.monotonic()
    try:
        registry = get_registry(country)
        today_date = _parse_today(today, country=country)
        report = await registry.lookup(id)
    except RegistryError as exc:
        _record(
            operation="company_deadlines", country=country.upper(), query=id,
            started=started, ok=False, error_code=exc.code.value,
        )
        raise _tool_error(exc) from exc
    result = registry.deadline_report(report, today_date)
    _record(
        operation="company_deadlines", country=result.country, query=id,
        started=started, ok=True,
    )
    return result.model_dump(mode="json")


@mcp.tool
def validate_company_id(id: str, country: str = "NO") -> dict[str, Any]:
    """Check whether a Norwegian organisasjonsnummer (orgnr, org.nr) is well-formed for
    Brønnøysundregistrene / Enhetsregisteret (brreg) — no network call. This is the cheap
    norway company lookup pre-check for the norwegian business registry: use it on user
    input or a spreadsheet column before spending a real `lookup_company` call, since it
    is instant and free.

    Returns a ValidationResult and never raises for a malformed identifier: `valid: false`
    comes with `reason` (what failed) and `hint` (what to do next) rather than a tool
    error — this tool answers a question, it does not fail on bad input
    (`DECISIONS.md` D-010). A valid identifier does not mean the entity exists; follow it
    with `lookup_company` if you need facts.

    The only real error here is `unsupported_country` (no module for that country yet —
    call `list_countries`), raised with the error text `{"error": {"code", "message",
    "hint"}}`.
    """
    started = time.monotonic()
    try:
        registry = get_registry(country)
        result = registry.validate(id)
    except RegistryError as exc:
        _record(
            operation="validate_company_id", country=country.upper(), query=id,
            started=started, ok=False, error_code=exc.code.value,
        )
        raise _tool_error(exc) from exc
    _record(
        operation="validate_company_id", country=result.country, query=id,
        started=started, ok=True, error_code=None if result.valid else "invalid_id",
    )
    return result.model_dump(mode="json")


@mcp.tool
def list_countries() -> dict[str, Any]:
    """List every national company registry this service can answer for right now, plus
    each one's identifier scheme (`id_scheme`, `id_example`, `id_description`), source URL
    and licence.

    Call this before your first lookup in a country you have not used here before, or
    whenever a user names a country you are unsure is supported — never hard-code a
    country list of your own, since it grows as registry modules are added with no change
    to any other tool's shape. Stub/example modules are hidden; only registries that
    actually answer are listed. This tool has no error mode; a failure here is a bug, not
    something to retry differently.
    """
    started = time.monotonic()
    rows = [dict(r.describe()) for r in list_registries()]
    _record(operation="list_countries", country=None, query=None, started=started, ok=True)
    return {"countries": rows}


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
