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
from collections.abc import Callable, Iterator, Sequence
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
from registry_mcp.core.registry import Registry, get_registry, list_registries, loggable_query
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
    """Mutable result the `_call_context` caller fills in as it learns more.

    `country`/`query` seed as the (normalised) values `_call_context` was
    entered with, and stay there for every tool in this module — none of the
    five needs to touch them. `mcp/connector.py`'s two aliases do: `fetch`
    parses a country out of its `"{COUNTRY}:{identifier}"` argument only
    after entering, and `search` learns one from `_derive_country` — both
    overwrite the field once they know more, before the `finally` below reads
    it (`DECISIONS.md` D-040(b)).
    """

    ok: bool = True
    error_code: str | None = None
    cached: bool | None = None
    country: str | None = None
    query: str | None = None


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
    re-raised as a `ToolError` whose text is the D-007 JSON envelope. Any other
    exception is also recorded as a failure — an internal bug escaping a tool
    body is not a successful call — and re-raised unchanged, which FastMCP
    turns into a bare `ToolError` of its own. Success is recorded as-is, with
    whatever the caller set on `outcome` (`error_code` for
    `validate_company_id`'s non-raising `invalid_id` case, `cached` for
    `lookup_company`/`search_company`).

    Whatever `outcome.country`/`.query` hold when the block exits is what
    gets logged — run through `core.registry.loggable_query` exactly once,
    here, so no tool (and neither connector alias) ever calls it itself
    (`DECISIONS.md` D-040(b)).
    """
    started = time.monotonic()
    outcome = _CallOutcome(country=country.upper() if country else None, query=query)
    try:
        yield outcome
    except RegistryError as exc:
        outcome.ok = False
        outcome.error_code = exc.code.value
        raise _tool_error(exc) from exc
    except Exception:
        # Any other exception is an internal bug, not a `RegistryError` — it must
        # not be counted as a successful call (`REVIEW.md` S-series finding 6).
        # Re-raised unchanged, so FastMCP's own dispatcher still turns it into a
        # bare `ToolError` rather than the D-007 envelope — closing that gap is
        # `core/registry.py`'s half of finding 6, owned by T42 this round, not
        # this module's.
        outcome.ok = False
        raise
    finally:
        try:
            record_call(
                surface=Surface.MCP,
                operation=operation,
                country=outcome.country,
                query=loggable_query(outcome.country, outcome.query),
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

# The payment-fraud caveat every client that only reads `instructions` — not the
# `counterparty_check` prompt — must still see (`REVIEW.md` S-series finding 5(a)):
# `instructions` is the string every MCP client puts in front of the model, and a
# caller who uses `lookup_company` directly never renders the prompt at all. Defined
# once and used by both `instructions` below and `counterparty_check`'s own prompt
# text, so a third use cannot paraphrase it away.
_PAYMENT_FRAUD_CAVEAT = (
    "This is not sanctions, PEP or adverse-media screening; it does not verify "
    "bank account or payment details; and it is not a defence against payment fraud"
)

mcp: FastMCP = FastMCP(
    name="registry-mcp",
    version=__version__,
    instructions=(
        "The company registry MCP. Check whether a company you're about to deal with — a "
        "new supplier, a counterparty, an entity you're onboarding — is real, active and "
        "keeping up with its statutory filings, straight from the national business "
        f"register itself, not a resold copy. {_PAYMENT_FRAUD_CAVEAT} — the commonest "
        "invoice fraud impersonates a real, active, correctly-registered supplier, not a "
        "fake one. validate_company_id checks an identifier's shape for free before you "
        "spend a real lookup; the prompts counterparty_check and register_coverage each "
        "carry one of these jobs out end to end from a single identifier. A lookup_company "
        "report here is byte-identical to the REST API's.\n\n"
        "Three countries answer today: country=\"NO\" Norway (Enhetsregisteret / "
        "Brønnøysundregistrene, brreg, by organisasjonsnummer), country=\"GB\" the United "
        "Kingdom (Companies House, by company number) — use \"GB\", since \"UK\" is not a "
        "country code here and is rejected — and country=\"SE\" Sweden (Bolagsverket, by "
        "organisationsnummer). Sweden is by identifier only: Bolagsverket's free API has no "
        "name-search operation at all, so search_company for SE raises not_implemented. "
        "Companies House and Bolagsverket each need a credential, so a deployment with "
        "neither COMPANIES_HOUSE_API_KEY nor BOLAGSVERKET_CLIENT_ID/"
        "BOLAGSVERKET_CLIENT_SECRET answers for Norway only. Call list_countries for the "
        "live set, each country's identifier scheme and its supported_includes.\n\n"
        "lookup_company also takes include=[...] for seven attachments beyond the base "
        "report — filings, charges, insolvency, financials, lei, parents and peppol — each "
        "a second fetch with its own provenance, null unless you ask. That argument's own "
        "description is where each one is explained.\n\n"
        "Every tool error is JSON: {\"error\": {\"code\", \"message\", \"hint\"}}, and hint names "
        "the next call — parse it instead of treating a failure as opaque. invalid_id: "
        "malformed — fix it or call search_company with the name; never retry the same "
        "string. not_found: well-formed, no such entity — call search_company. "
        "unsupported_country: no module for that country — call list_countries. "
        "bad_request: read the hint, which names the allowed value. not_implemented: that "
        "register has no such operation and never will — change approach, not timing. "
        "rate_limited: slow down. upstream_error / upstream_timeout: the register is "
        "unavailable and has already been retried once here — wait about a minute."
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
    "The company's national identifier, normalised for you — a Norwegian "
    "organisasjonsnummer (orgnr), a Companies House company number (CRN), or a Swedish "
    "organisationsnummer or personnummer. Spaces, dots, hyphens, a NO...MVA suffix and "
    "a short CRN are accepted; list_countries gives each country's exact shape."
)
_ID_EXAMPLES = ["923609016", "00445790"]

_COUNTRY_DESCRIPTION = (
    "ISO-3166-1 alpha-2 — NO Norway, GB United Kingdom, SE Sweden. UK is not a country "
    "code here and is rejected. Call list_countries for the live set."
)

_INCLUDE_DESCRIPTION = (
    "Attachment names to fetch alongside the base report; empty by default, which "
    "costs exactly one upstream request. Each is a second, independent fetch attached "
    "at that name with its own provenance, null unless you ask, and this argument is "
    "where each of the seven is explained. "
    "'filings' (every country): what the entity has filed, and when — Companies House "
    "the whole filing history, Bolagsverket the filed annual reports, "
    "Regnskapsregisteret the filed annual accounts; the block's notes says which, and "
    "total_count how many more the register holds. "
    "'charges' (GB): registered mortgages and other security interests, in the "
    "register's own words. "
    "'insolvency' (GB): winding-up and administration proceedings — a members' "
    "voluntary liquidation is a *solvent* wind-up, so is_liquidation: true is not by "
    "itself evidence of distress. "
    "'financials' (NO and SE): the register's own figures for the latest filed "
    "accounting period — turnover, operating result, profit, balance sheet, equity, "
    "liabilities, each beside its currency, never a ratio or a verdict. Norway's come "
    "in the 'filings' fetch, Sweden's out of the entity's own filed K2 annual report. A "
    "null figure in a present block means the company did not report that line; an "
    "absent block means you did not ask, the fetch failed, or — Sweden — it has filed "
    "no digital annual report, and notes says which. Britain does not declare it, so "
    "'financials' for GB is a bad_request, never an empty block. "
    "'lei' (every country except Sweden, whose identifier can be a natural person's): "
    "the Legal Entity Identifier GLEIF, the Global LEI Foundation, publishes — CC0 and "
    "keyless; lei: null in a present block means GLEIF holds none. "
    "'parents' (same countries as 'lei'): the direct and ultimate parent from GLEIF's "
    "Level 2 data — the entity that consolidates this one's accounts into its group, "
    "not necessarily its majority shareholder. Where GLEIF discloses none, that side "
    "carries the entity's own stated reason as a category word such as "
    "'NATURAL_PERSONS' — never a name, and unverified. "
    "'peppol' (Norway): whether an e-invoice can reach the entity over the Peppol "
    "network, read live from the SML/SMP walk the way ELMA resolves it, ahead of the 1 "
    "January 2027 EHF (Peppol BIS Billing 3.0) duty. registered: null means no "
    "authoritative answer — never read it as \"no\"; only an NXDOMAIN or an SMP 404 "
    "earns false. "
    "Read a country's supported_includes from list_countries first: a value it does "
    "not declare is a bad_request naming what it does support, never an empty result."
)
_INCLUDE_EXAMPLES: list[list[str]] = [
    ["filings"],
    ["charges", "insolvency"],
    ["financials", "lei"],
]


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
        str, Field(description=_COUNTRY_DESCRIPTION)
    ] = "NO",
    include: Annotated[
        Sequence[str], Field(description=_INCLUDE_DESCRIPTION, examples=_INCLUDE_EXAMPLES)
    ] = (),
) -> dict[str, Any]:
    """Look up a company by its national identifier and get the full CompanyReport — legal
    form, status, address, VAT registration where the register publishes it, board and
    accounts duties, employees, and more.

    `country="NO"` is the norway company lookup for the norwegian business registry:
    Brønnøysundregistrene / Enhetsregisteret (brreg), by organisasjonsnummer (orgnr,
    org.nr). `country="GB"` is the uk company lookup at Companies House, by company number
    (company registration number, CRN) — "UK" is not a country code here. `country="SE"` is
    the swedish company lookup at Bolagsverket, by organisationsnummer or a sole trader's
    (enskild näringsidkare) personnummer, and by identifier only, since Bolagsverket's free
    API has no name search.

    `include=[...]` attaches seven second fetches, each with its own provenance and
    `null` unless you ask: `filings` (filing history — do they file, and on time),
    `charges` (registered mortgages and security interests), `insolvency` (winding-up
    and administration), `financials` (annual accounts — turnover, operating result,
    profit, balance sheet: the solvency question), `lei` (the GLEIF Legal Entity
    Identifier), `parents` (direct and ultimate parent — this entity's group — from
    GLEIF) and `peppol` (whether an e-invoice would reach them, ahead of Norway's 1
    January 2027 EHF duty). The `include` argument explains each: what it returns, which
    countries declare it, how to read its nulls.

    Use it once you have the identifier — from the user, an invoice, a contract, or a
    `search_company` hit's `id`. Read the returned `notes` before acting: it carries
    caveats such as bankruptcy, dissolution, a deleted entity, an unclassified legal
    form, or an attachment whose own fetch failed.

    This tool does not perform sanctions, PEP or adverse-media screening, and it does not
    verify bank account details — it returns identity and filing data from the national
    register only, never a compliance clearance or a confirmed payment detail.

    Errors are the `{"error": {"code", "message", "hint"}}` envelope this server's
    instructions set out code by code (D-007); `hint` names the next call. A failed
    *attachment* fetch is not one of them: the base report still comes back, that block
    is left `null`, and `notes` says which attachment failed and why."""
    with _call_context(operation="lookup_company", country=country, query=id) as outcome:
        registry = get_registry(country)
        report = await registry.lookup_with(id, include)
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
        str, Field(description=_COUNTRY_DESCRIPTION)
    ] = "NO",
    limit: Annotated[
        int,
        Field(
            description=(
                "Maximum hits to return, 1-100; default 10. Outside that range is a "
                "bad_request, not a silent clamp."
            ),
            examples=[10, 50],
        ),
    ] = 10,
) -> dict[str, Any]:
    """Search a national company register by name, when you have a name rather than an
    identifier.

    `country="NO"` searches Brønnøysundregistrene / Enhetsregisteret (brreg) — the norway
    company lookup for the norwegian business registry when the organisasjonsnummer (orgnr,
    org.nr) is not yet known; `country="GB"` is the uk company search at Companies House,
    returning each hit's company number (company registration number, CRN).

    **Sweden cannot be searched by name.** Bolagsverket's free API has four operations and
    none takes a company name, so `country="SE"` raises `not_implemented` — a fact about
    the register, not a temporary gap, and it will not start working. Sweden supports
    lookup by identifier only: call `lookup_company` with the ten-digit
    organisationsnummer (or a sole trader's twelve-digit personnummer), or
    `validate_company_id` first to check the shape for free. Bolagsverket publishes the
    whole register as bulk downloadable files for callers who must search by name.

    Then call `lookup_company` with the `id` of the right hit for the full report — a
    search hit is deliberately thin (name, legal form, status, city) and must not be acted
    on directly. Hits arrive in the register's own relevance order, so read each hit's
    `confidence` rather than assuming the first row is best. Zero hits is not an error, and
    `hint` says what to try next — Norwegian names are registered upper-case and often carry
    an 'AS', 'ASA' or 'NUF' suffix, UK names a 'LIMITED', 'LTD', 'PLC' or 'LLP' one, worth
    dropping before concluding a company does not exist.

    Errors are the `{"error": {"code", "message", "hint"}}` envelope this server's
    instructions set out code by code; `hint` names the next call. Call `list_countries`
    if you are unsure a country is supported."""
    with _call_context(operation="search_company", country=country, query=name) as outcome:
        registry = get_registry(country)
        result = await registry.search(name, limit)
        outcome.cached = result.cached
    return result.model_dump(mode="json")


#: `company_deadlines` accepts a **narrower** `include` vocabulary than
#: `lookup_company` does (`DECISIONS.md` D-043(j), D-045(g)): only a value
#: that can change a *computed* date belongs here. Its own description
#: constant, never `_INCLUDE_DESCRIPTION` — that one advertises `charges`
#: and `insolvency`, neither of which this tool would ever accept.
_DEADLINE_INCLUDE_DESCRIPTION = (
    "Attachment names that can change a *computed* deadline — narrower than "
    "lookup_company's include. Today only 'filings': one extra upstream request for the "
    "entity's filing history, supplying a real financial year end where 31 December "
    "would otherwise be assumed. Empty by default; Norway and the United Kingdom accept "
    "it and it changes nothing for them today. Any other value — including one "
    "lookup_company accepts, such as 'charges' — is a bad_request naming this tool's "
    "allowed set."
)
_DEADLINE_INCLUDE_EXAMPLES: list[list[str]] = [["filings"], []]


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
        str, Field(description=_COUNTRY_DESCRIPTION)
    ] = "NO",
    today: Annotated[
        str | None,
        Field(
            description=(
                "Date to compute deadlines from, YYYY-MM-DD; defaults to the "
                "server's current UTC date. Anything else is a bad_request naming "
                "the format."
            ),
            examples=["2026-10-01"],
        ),
    ] = None,
    include: Annotated[
        Sequence[str],
        Field(description=_DEADLINE_INCLUDE_DESCRIPTION, examples=_DEADLINE_INCLUDE_EXAMPLES),
    ] = (),
) -> dict[str, Any]:
    """Give the next occurrence of each statutory filing deadline a company faces.

    `country="NO"` covers the Norwegian calendar (Regnskapsregisteret, Skatteetaten) for a
    company looked up by organisasjonsnummer (orgnr, org.nr) in Brønnøysundregistrene /
    Enhetsregisteret (brreg): årsregnskap, generalforsamling, skattemelding,
    aksjonærregisteroppgaven, mva-melding, a-melding. `country="GB"` covers the two
    Companies House obligations for a company number (CRN): the annual accounts filing and
    the confirmation statement (CS01). `country="SE"` covers the two Swedish obligations of
    an aktiebolag (AB) or ekonomisk förening (EK) looked up by organisationsnummer at
    Bolagsverket: the ordinary general meeting (ordinarie bolagsstämma / årsstämma) at six
    months from the financial year end, and the annual report (årsredovisning) at seven,
    where the late-filing fee (förseningsavgift) begins.

    Pass `today` (`YYYY-MM-DD`) for a reproducible answer; it defaults to the server's
    current UTC date. Quote `due_date`, not `statutory_date`, and quote each deadline's
    `applies_because` rather than presenting a date as unconditional fact — that sentence
    carries the legal form or flag the date rests on, its statute, any assumption still in
    it, and for the UK whether it is Companies House's own figure or one computed here.
    `days_until` goes negative for a filing Companies House still shows as overdue. Swedish
    dates assume a financial year ending 31 December unless you pass `include=["filings"]`,
    which substitutes the year end of the last filed annual report where Bolagsverket's
    document list holds one; the filing date is an outer limit regardless, since a company
    whose general meeting was earlier must file earlier. An empty `deadlines` list is a real
    answer — a bankrupt, deleted or compulsorily-liquidated entity, a branch/sub-unit, or
    any company whose status is not active — and `notes` explains why.
    `registry://rules/{country}` carries each country's full deadline rules, roll-forward
    treatment and legal sources.

    Errors are the `{"error": {"code", "message", "hint"}}` envelope this server's
    instructions set out code by code; `hint` names the next call. This tool looks the
    entity up first, so any `lookup_company` error code can surface here too."""
    with _call_context(operation="company_deadlines", country=country, query=id):
        registry = get_registry(country)
        today_date = parse_iso_date(today, field="today")
        result = await registry.deadline_report_with(id, include, today_date)
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
        str, Field(description=_COUNTRY_DESCRIPTION)
    ] = "NO",
) -> dict[str, Any]:
    """Check whether a national company identifier is well-formed — no network call.

    `country="NO"` checksum-checks a Norwegian organisasjonsnummer (orgnr, org.nr) for
    Brønnøysundregistrene / Enhetsregisteret (brreg) — the cheap norway company lookup
    pre-check for the norwegian business registry. `country="GB"` shape-checks and
    normalises a UK company number (company registration number, CRN) for Companies House
    ('445790' → '00445790', 'oc303675' → 'OC303675'); a CRN has no check digit, so a GB
    `valid: true` means the shape is right and nothing more. `country="SE"` shape-checks and
    normalises a Swedish organisationsnummer for Bolagsverket ('556016-0680' and
    'SE556016068001' both become '5560160680') and accepts a sole trader's twelve-digit
    personnummer; Sweden's check digit is **not** enforced here (`registry://rules/SE` says
    why), so an `SE` `valid: true` means the shape is right, `reason` may carry a caveat,
    and the register's own verdict arrives on the lookup. It is the cheapest way to tell a
    ten-digit Swedish organisationsnummer from a nine-digit Norwegian organisasjonsnummer.

    Use it on user input or a spreadsheet column before spending a real `lookup_company`
    call, since it is instant and free.

    Returns a ValidationResult and never raises for a malformed identifier: `valid: false`
    comes with `reason` and `hint` rather than a tool error — this tool answers a question,
    it does not fail on bad input (D-010). A valid identifier does not mean the entity
    exists; follow it with `lookup_company` if you need facts. The only error it raises is
    `unsupported_country`, in the usual `{"error": {"code", "message", "hint"}}` envelope —
    call `list_countries`."""
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
    """List every national company registry this service can answer for right now, with each
    one's identifier scheme, source URL, licence, `supported_includes`, and whether the
    upstream register needs a credential (`requires_api_key`, `api_key_env`).

    Call it before your first lookup in a country you have not used here, whenever a user
    names a country you are unsure of, or before guessing an `include` value — never
    hard-code a country list of your own, since it grows as modules are added. Stub modules
    are hidden; only registries that actually answer are listed. No error mode."""
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
# Prompts
#
# Each takes the same (id, country) shape as the tools above and carries out
# one whole job an actual caller has, across whichever tools and resources it
# needs — never a new tool (`DECISIONS.md` D-042(c): a tool is bought by a
# distinct question an agent asks, and this entry authorises none today;
# prompts are free of that constraint). `counterparty_check` and
# `register_coverage` are named in `mcp`'s own `instructions` above, so a
# client that reads the server description before its first call already
# knows they exist.
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


@mcp.prompt
def counterparty_check(id: str, country: str = "NO") -> str:
    """Check a counterparty before contracting with or onboarding them: existence, current
    legal status and filing health — not a payment-fraud or bank-detail check."""
    return (
        f"Call validate_company_id(id={id!r}, country={country!r}) first. If `valid` is "
        "false, stop here and report `reason` and `hint` in plain English — do not guess "
        f"at a corrected identifier. If valid, call lookup_company(id={id!r}, "
        f"country={country!r}) for identity and status, then call "
        f"company_deadlines(id={id!r}, country={country!r}) for filing health. Using both "
        "results, answer three questions in this order: "
        "(1) Existence — does the entity exist, and does `name` match what you were told? "
        "(2) Status — is `status` active right now; if it is not, lead your answer with "
        "that and quote `status_detail` verbatim. "
        "(3) Filing health — is every entry in `deadlines` current, or does any have a "
        "negative `days_until`; name which obligation is overdue and by how many days. "
        "Quote every `notes` entry from both calls verbatim and in full — bankruptcy, "
        "dissolution, an unclassified legal form and every other register-specific caveat "
        "live there, and summarising them away is the one mistake this prompt exists to "
        "prevent.\n\n"
        "End with a section titled exactly 'What this does not establish'. State plainly: "
        f"{_PAYMENT_FRAUD_CAVEAT}. The "
        "costly fraud pattern — business email compromise, where an attacker redirects a "
        "genuine payment — uses a real, active, correctly-registered company and forges "
        "only the bank details, so a clean result here is consistent with that fraud, not "
        "evidence against it. Tell the reader to confirm any bank detail, and any change "
        "to one, through a channel they already trust — a phone call to a number they "
        "already had, never a number or link supplied in the same message that gave the "
        "new details — and never through this lookup. If any call fails, explain the "
        "error's `hint` in plain English instead of showing raw JSON."
    )


@mcp.prompt
def register_coverage(id: str, country: str = "NO") -> str:
    """Explain what this company's register record actually says — and, the point of this
    prompt, what it stays silent on and why."""
    return (
        f"Call lookup_company(id={id!r}, country={country!r}) for the full CompanyReport, "
        f"and read the resource registry://rules/{country} for this register's own stated "
        "rules and caveats. Then write two sections, not one, and do not shorten the "
        "second: '## What the register states' and '## What it does not state' — the "
        "second section is the point of this prompt.\n\n"
        "For every field in the report that is `null`, work out which of two different "
        "things the null means, because they are not the same fact and must not be "
        "reported the same way. (a) A structural silence: this register never publishes "
        "this kind of fact, for any company in this country, so the null is a fact about "
        "the register, not about this entity — the rules resource names most of these. "
        "(b) An entity-level gap: the register could hold a value here but has none for "
        "this particular company. Beware that the same field can be either, depending on the "
        "country: `employees` is a *structural* silence for the United Kingdom and Sweden, "
        "whose registers publish no employee count for anyone, and an *entity-level* gap in "
        "Norway, whose register does publish them and simply holds none for this company. "
        "Read `registry://rules/{country}` before deciding which it is; do not assume from "
        "the field name. Never render a null as "
        "'no', 'zero' or 'not applicable' — say plainly that the register is silent, and "
        "say which of the two reasons it is wherever you can tell.\n\n"
        "Quote every `notes` entry verbatim — an unclassified legal form, a deleted "
        "entity, a bankruptcy flag and every other register-specific caveat live there, in "
        "the register's own words. Also surface anything the rules resource states that "
        "is not a field on this report at all but limits what a caller can do with this "
        "register — a register with no name search, for instance, cannot be queried from "
        "a name alone, which matters to a reader who does not yet have this identifier. "
        "Close with one line naming the register (`source`) and its `source_url`, so the "
        "reader knows whose silence this is — this tool's, or the register's. If the "
        "lookup fails, explain the error's `hint` in plain English instead of raw JSON."
    )


# ---------------------------------------------------------------------------
# ChatGPT connector aliases (`DECISIONS.md` D-031)
# ---------------------------------------------------------------------------


def _register_connector_aliases() -> None:
    """Trigger `mcp/connector.py`'s own `@mcp.tool` registrations for `search`/`fetch`
    against this module's `mcp` object, as a side effect of importing it — the same
    pattern `core/registry.py::_load_registries` uses for country modules. Deferred
    into a function (rather than a top-level import) purely to keep this below the five
    tools in this file without a ruff E402 (module-level import not at top of file).

    `connector.py` imports ``_READ_EXTERNAL``, ``_call_context`` and ``mcp`` back from
    this module; by the time this runs, all three are already defined above, so the
    circular import resolves against this module's (by-then-complete) namespace.
    """
    import registry_mcp.mcp.connector  # noqa: F401


_register_connector_aliases()


# ---------------------------------------------------------------------------
# stdio entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Console-script / `python -m registry_mcp` entry point: serve over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
