"""ChatGPT connector aliases — ``search`` and ``fetch`` (``DECISIONS.md`` D-031).

ChatGPT's deep research and "company knowledge" features reach an MCP server through
exactly two tool names, `search` and `fetch`, with a shape OpenAI defines rather than us
(<https://developers.openai.com/api/docs/mcp>). This module ships that pair as two
**aliases** over operations this server already has — `Registry.validate`, `.lookup`,
`.search` and `.deadline_report` — so a ChatGPT connector can reach this server at all,
without the five registry tools' names, signatures, annotations or output schemas
changing by one byte. Full spec: ``CONNECTOR_SPEC.md``. Ruling: ``DECISIONS.md`` D-031.

Imported by ``mcp/server.py`` purely so the ``@mcp.tool`` registrations below run at
import time, beside the five tools server.py declares directly — the same
side-effect-import pattern ``core/registry.py::_load_registries`` uses for country
modules. This module imports no country module and contains no country string in a
branch (only in prose): every country-specific fact comes from ``list_registries()`` /
``Registry`` (D-001, D-008), so a third country lights up here with no edit.

``search`` (D-031(c)): a country token or a live registry's name in the query narrows the
fan-out to one country (never a default — a miss just means every live country is asked,
which is why the matcher can stay this thin); an identifier that validates for a country
short-circuits straight to one `lookup`, skipping name search entirely; otherwise every
candidate country is name-searched, merged into **one** list — never grouped by registry —
and sorted by confidence descending, an exact name match (legal-form suffix and punctuation
ignored) breaking a confidence tie ahead of everything else, with registry return order as
the last-resort, stable tie-break; zero rows returns one row per live country pointing at
its rules document rather than an empty result OpenAI's UI would show as "nothing found". A
per-country failure anywhere in the fan-out drops that country silently — this tool never
raises because one register is unreachable.

Fixed 2026-09-06, live-deployment finding: ``search(query="Equinor")`` returned
``GB:11777091 — EQUINOR BLANDFORD ROAD LIMITED`` first, not ``NO:923609016 — EQUINOR ASA``.
Both hits share the same D-005 confidence anchor (0.8, "name starts with the query") — a
real name match and an unrelated company that merely starts with the same word are
indistinguishable by confidence alone — and the previous tie-break (registry return order,
alphabetical by country code) has no relevance signal in it at all. The exact-name
tie-break above is the fix; see ``CONNECTOR_SPEC.md`` §3's dated note. The merged-row cap
was lowered from 20 to 10 in the same change, for the same reason `search_company`'s own
default `limit` is 10: a deep-research turn should not have to sift through twenty mixed
rows to find the one it wants.

``fetch`` (D-031(d)): parses ``"{COUNTRY}:{identifier}"`` (or ``"rules:{COUNTRY}"`` for a
rules document, or derives the country from every live ``validate`` when there is no
colon), then does the one `lookup` `company_deadlines` already does internally and renders
both documents as one Markdown `text` plus the full JSON of both in `metadata` — deep
research cannot call `company_deadlines` itself, so this is the only way it ever sees a
deadline.

``id`` is always ``"{COUNTRY}:{identifier}"`` and ``url`` is always this server's own REST
record URL (never the register's ``source_url``, which travels inside `metadata`/`text`
instead) — always non-empty, because OpenAI drops the citation otherwise, and it resolves
to the same bytes `fetch` returns.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Awaitable, Sequence
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from registry_mcp.core.models import (
    Address,
    CompanyReport,
    DeadlineReport,
    ErrorCode,
    RegistryError,
    SearchHit,
)
from registry_mcp.core.registry import Registry, get_registry, list_registries
from registry_mcp.core.rules.common import parse_iso_date
from registry_mcp.mcp.server import _READ_EXTERNAL, _call_context, mcp

__all__ = ["fetch", "search"]

#: Our own REST record URL, cited as `url` on every `search` row and every `fetch`
#: document (D-031(c)) — never the register's own `source_url`, which is carried inside
#: `metadata`/`text` instead. A citation target only: nothing in this server ever calls
#: it. Overridable so a self-hosted deployment cites itself rather than the hosted one.
PUBLIC_BASE_URL = os.environ.get("REGISTRY_MCP_PUBLIC_BASE_URL", "https://api.foretak.dev").rstrip(
    "/"
)

#: `search`'s merged-and-sorted row cap, across every registry combined. Lowered from
#: CONNECTOR_SPEC.md's original 20 to 10 (see the module docstring's dated note and
#: CONNECTOR_SPEC.md §3) — matching `search_company`'s own default `limit`, and small
#: enough that a deep-research turn is not left to sift through twenty mixed rows.
_MAX_SEARCH_RESULTS = 10

#: Common legal-form suffixes stripped from a name's *trailing* tokens only, before
#: comparing it with the query for the exact-match tie-break below. Deliberately the
#: short, literal list named in the live-defect report — not a per-country table (no
#: country string appears here, D-031(g)): the same set is tried against every hit
#: regardless of which registry it came from.
_LEGAL_FORM_SUFFIXES = frozenset({"asa", "as", "ltd", "limited", "plc", "llp"})

_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)

#: A maximal alphanumeric run within a free-text `search` query — used by the D-040(b)
#: personnummer redaction below to find candidate identifiers embedded among other
#: tokens (a name, a country word, punctuation), so they can be checked individually
#: against every live flagged registry rather than only the query's whole remainder.
_ID_RUN = re.compile(r"[0-9A-Za-z\-]+")


def _normalised_name(name: str) -> str:
    """Case-, punctuation- and trailing-legal-form-suffix-insensitive form of a name.

    Used **only** to break an already-equal D-005 confidence tie (`_merge_sort_and_cap`)
    — never to compute a confidence value, which stays exactly what `Registry.search`
    returned. `"EQUINOR ASA"` and the query `"Equinor"` both normalise to `"equinor"`;
    `"EQUINOR BLANDFORD ROAD LIMITED"` normalises to `"equinor blandford road"`, which is
    not equal to either — the distinction the previous tie-break (registry order) could
    not draw.
    """
    tokens = _NON_WORD_RE.sub(" ", name.casefold()).split()
    while tokens and tokens[-1] in _LEGAL_FORM_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# Wire shapes — OpenAI's field list, not ours. Exempt from `core/models.py`'s D-004
# contract (`CONNECTOR_SPEC.md` §1): these three shapes belong to somebody else's API,
# and live here rather than in `core/` for exactly that reason.
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    """`extra="forbid"` guards only our own construction — data flows one way through
    these models (us to the client), so this is a typo guard, not a contract like
    `core.models._Base`'s."""

    model_config = ConfigDict(extra="forbid")


class ConnectorSearchHit(_Base):
    """One `search` result row. OpenAI reads exactly `id`, `title` and `url`."""

    id: str
    title: str
    url: str


class ConnectorSearchResponse(_Base):
    """The whole `search` response: `{"results": [...]}`."""

    results: list[ConnectorSearchHit] = Field(default_factory=list)


class ConnectorDocument(_Base):
    """The whole `fetch` response. `text` is a Markdown rendering (§2 of the spec);
    `metadata` carries the full `CompanyReport`/`DeadlineReport` JSON plus flat scalars."""

    id: str
    title: str
    text: str
    url: str
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------


async def _bounded_gather[T](coros: Sequence[Awaitable[T]], *, limit: int = 5) -> list[T]:
    """Run every awaitable with at most `limit` in flight (D-024(g)'s bound, applied one
    level up to `search`'s fan-out across `list_registries()`) — moot at two live
    countries today, load-bearing once there are ten."""
    semaphore = asyncio.Semaphore(limit)

    async def _run(coro: Awaitable[T]) -> T:
        async with semaphore:
            return await coro

    results: list[T] = await asyncio.gather(*(_run(c) for c in coros))
    return results


def _record_url(country: str, identifier: str) -> str:
    return f"{PUBLIC_BASE_URL}/v1/{country}/company/{identifier}"


def _connector_title(
    name: str, country: str, identifier: str, legal_form: str | None, status: str, is_subunit: bool
) -> str:
    """`"{name} — {country} {id}"`, then legal form and status (whichever are known,
    joined with `", "`), then `" — sub-unit"` — the only prose a `search` caller reads
    before deciding what to `fetch` (D-031(c))."""
    title = f"{name} — {country} {identifier}"
    extra = [part for part in (legal_form, None if status == "unknown" else status) if part]
    if extra:
        title += " — " + ", ".join(extra)
    if is_subunit:
        title += " — sub-unit"
    return title


#: One candidate row plus what `_merge_sort_and_cap` needs to rank it: the raw
#: (never-fabricated) D-005 confidence, the entity's name (for the exact-match
#: tie-break only), and the row itself.
_Ranked = tuple[float, str, ConnectorSearchHit]


def _row_from_report(report: CompanyReport) -> _Ranked:
    row = ConnectorSearchHit(
        id=f"{report.country}:{report.id}",
        title=_connector_title(
            report.name, report.country, report.id, report.legal_form, report.status.value,
            report.is_subunit,
        ),
        url=_record_url(report.country, report.id),
    )
    return report.confidence, report.name, row


def _row_from_hit(hit: SearchHit) -> _Ranked:
    row = ConnectorSearchHit(
        id=f"{hit.country}:{hit.id}",
        title=_connector_title(
            hit.name, hit.country, hit.id, hit.legal_form, hit.status.value, hit.is_subunit
        ),
        url=_record_url(hit.country, hit.id),
    )
    return hit.confidence, hit.name, row


def _merge_sort_and_cap(ranked: list[_Ranked], query: str) -> list[ConnectorSearchHit]:
    """One global sort across every candidate registry's rows — never grouped by
    registry (D-020's "best match, best first" applied one level up, across countries
    rather than within one). Primary key: confidence descending, exactly as
    `Registry.search` computed it — never re-scored or fabricated here. Tie-break: a
    hit whose normalised name exactly equals the normalised query ranks first among
    equal-confidence hits (`_normalised_name`); `list.sort` is stable, so a genuine
    remaining tie keeps the order the registries were asked in — the same order
    `_identifier_rows`/`_name_search_rows` built `ranked` in, i.e. `list_registries()`'s
    order, never wall-clock arrival order (`_bounded_gather` preserves input order).

    Fixes the live defect where two registries shared one D-005 anchor (0.8, "starts
    with the query") for hits of very different relevance, and registry order — which
    carries no relevance signal — decided the winner (module docstring, dated note)."""
    normalised_query = _normalised_name(query)
    ranked.sort(key=lambda item: (-item[0], 0 if _normalised_name(item[1]) == normalised_query else 1))
    return [row for _confidence, _name, row in ranked][:_MAX_SEARCH_RESULTS]


def _rules_rows() -> list[ConnectorSearchHit]:
    """One row per live country pointing at its rules document — the zero-hit fallback
    (D-031(c)): a real document, never a fabricated company, and the one place `search`
    can answer D-007's "what next?" at all, since a search row carries no `hint`."""
    return [
        ConnectorSearchHit(
            id=f"rules:{registry.country}",
            title=(
                f"{registry.name} ({registry.country}) — identifier rules, legal forms "
                "and filing deadlines"
            ),
            url=f"{PUBLIC_BASE_URL}/v1/countries",
        )
        for registry in list_registries()
    ]


def _derive_country(query: str, registries: list[Registry]) -> tuple[Registry | None, str]:
    """Country derivation for `search` (D-031(c)): a whitespace-delimited token equal to
    a live registry's `country` code, or a live registry's `country_info().name`
    appearing in the query, picks that country and drops the matched text from the
    query. No synonym table — a miss costs nothing, because the caller fans out to
    every live registry when nothing matches. Returns `(None, query)` on a miss."""
    tokens = query.split()
    for index, token in enumerate(tokens):
        for candidate in registries:
            if token.casefold() == candidate.country.casefold():
                remainder = " ".join(tokens[:index] + tokens[index + 1 :]).strip()
                return candidate, (remainder or query)

    lowered = query.casefold()
    for candidate in registries:
        name = candidate.country_info().name
        folded = name.casefold()
        position = lowered.find(folded)
        if position != -1:
            remainder = (query[:position] + query[position + len(name) :]).strip()
            remainder = " ".join(remainder.split())
            return candidate, (remainder or query)

    return None, query


async def _identifier_rows(candidates: list[Registry], query: str) -> tuple[bool, list[_Ranked]]:
    """Step 3 of `search` (D-031(c)): every candidate that says `Registry.validate(query)
    .valid` gets one `lookup`. Returns `(True, rows)` the moment any country validated —
    the caller must stop there and skip name search even if every lookup then fails —
    or `(False, [])` when no country recognised the query as an identifier at all. A
    per-country lookup failure drops that country's row rather than raising, matching
    the fan-out's general rule (D-031(c))."""
    validated: list[tuple[Registry, str]] = []
    for candidate in candidates:
        validation = candidate.validate(query)
        if validation.valid and validation.normalized is not None:
            validated.append((candidate, validation.normalized))
    if not validated:
        return False, []

    async def _lookup_row(pair: tuple[Registry, str]) -> _Ranked | None:
        registry, normalized = pair
        try:
            report = await registry.lookup(normalized)
        except RegistryError:
            return None
        return _row_from_report(report)

    outcomes = await _bounded_gather([_lookup_row(pair) for pair in validated])
    rows = [row for row in outcomes if row is not None]
    return True, rows


async def _name_search_rows(candidates: list[Registry], query: str) -> list[_Ranked]:
    """Step 4 of `search`: name-search every candidate, at most 5 concurrent
    (D-024(g)). A `RegistryError` from one country — e.g. GB with no
    `COMPANIES_HOUSE_API_KEY` — drops that country and never raises (D-031(c)).
    Returns one flat list in candidate order (never grouped by registry) — the actual
    cross-registry sort happens once, in `_merge_sort_and_cap`."""

    async def _search_hits(registry: Registry) -> list[SearchHit]:
        try:
            result = await registry.search(query, 10)
        except RegistryError:
            return []
        return list(result.hits)

    hit_lists = await _bounded_gather([_search_hits(candidate) for candidate in candidates])
    return [_row_from_hit(hit) for hits in hit_lists for hit in hits]


def _resolve_fetch_id(raw_id: str) -> tuple[Registry, str, bool]:
    """Parse a `fetch` id (D-031(d)). Returns `(registry, identifier-or-country-code,
    is_rules_document)`.

    * `"{COUNTRY}:{identifier}"` (a two-letter alphabetic left part) names a country.
    * `"rules:{COUNTRY}"` names that country's rules document.
    * No usable colon: derive, never default — every live registry's own `validate` is
      tried against the whole string, and exactly one match wins. Zero or several is
      `bad_request` naming the `"{COUNTRY}:{identifier}"` form and `list_countries`.
    """
    left, colon, right = raw_id.partition(":")
    if colon and left.casefold() == "rules":
        registry = get_registry(right)
        return registry, right, True
    if colon and len(left) == 2 and left.isalpha():
        registry = get_registry(left)
        return registry, right, False

    matches: list[tuple[Registry, str]] = []
    for candidate in list_registries():
        validation = candidate.validate(raw_id)
        if validation.valid and validation.normalized is not None:
            matches.append((candidate, validation.normalized))

    if len(matches) == 1:
        registry, normalized = matches[0]
        return registry, normalized, False

    if matches:
        codes = ", ".join(sorted(registry.country for registry, _ in matches))
        message = f"{raw_id!r} matches more than one country's identifier format ({codes})."
    else:
        message = f"Could not determine which country {raw_id!r} belongs to."
    raise RegistryError(
        ErrorCode.BAD_REQUEST,
        message,
        hint=(
            'Prefix the identifier with its country code, "{COUNTRY}:{identifier}" '
            '(e.g. "NO:923609016"), or call list_countries (MCP) / GET /v1/countries '
            "(REST) for the supported codes."
        ),
    )


def _address_line(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    return Address.model_validate(data).one_line() or None


def _identity_lines(company: dict[str, Any]) -> list[str]:
    """The header block of `_render_text` (§2): one line per known fact, a `None` value
    omits its line entirely rather than printing "unknown" or "0" (D-004, D-011) —
    except `employees`, which states "not published by this register" when
    `employees_reported` is `False`, a positive fact rather than an unknown one."""
    lines: list[str] = []

    id_scheme = company.get("id_scheme")
    id_value = company.get("id_formatted") or company["id"]
    identifier_bit = f"**Identifier:** {f'{id_scheme} ' if id_scheme else ''}{id_value}"
    register_bit = f"**Register:** {company['source']}" if company.get("source") else None
    lines.append(" · ".join(bit for bit in (register_bit, identifier_bit) if bit))

    status_line = f"**Status:** {company.get('status', 'unknown')}"
    if company.get("status_detail"):
        status_line += f" — {company['status_detail']}"
    lines.append(status_line)

    legal_form = company.get("legal_form")
    legal_form_code = company.get("legal_form_code")
    legal_form_local = company.get("legal_form_local")
    if legal_form or legal_form_code or legal_form_local:
        main = legal_form or legal_form_code or legal_form_local
        parenthetical = [p for p in (legal_form_code, legal_form_local) if p and p != main]
        line = f"**Legal form:** {main}"
        if parenthetical:
            line += f" ({' / '.join(parenthetical)})"
        lines.append(line)

    dates = " · ".join(
        bit
        for bit in (
            f"**Registered:** {company['registered_at']}" if company.get("registered_at") else None,
            f"**Founded:** {company['founded_at']}" if company.get("founded_at") else None,
        )
        if bit
    )
    if dates:
        lines.append(dates)

    vat_registered = company.get("vat_registered")
    if vat_registered is True:
        vat_value = company.get("vat_number") or company["id"]
        vat_line = f"**VAT:** registered as {vat_value}"
        if company.get("vat_registered_at"):
            vat_line += f" since {company['vat_registered_at']}"
        lines.append(vat_line)
    elif vat_registered is False:
        lines.append("**VAT:** not registered for VAT")

    employees = company.get("employees")
    if employees is not None:
        lines.append(f"**Employees:** {employees}")
    elif company.get("employees_reported") is False:
        lines.append("**Employees:** not published by this register")

    industry_codes = company.get("industry_codes") or []
    if industry_codes:
        fragments = []
        for index, code in enumerate(industry_codes):
            description = code.get("description")
            fragment = f"{code['code']} {description}" if description else code["code"]
            if index == 0 and code.get("scheme"):
                fragment += f" ({code['scheme']})"
            fragments.append(fragment)
        lines.append(f"**Industry:** {'; '.join(fragments)}")

    business_line = _address_line(company.get("business_address"))
    if business_line:
        lines.append(f"**Business address:** {business_line}")
    postal_line = _address_line(company.get("postal_address"))
    if postal_line:
        lines.append(f"**Postal address:** {postal_line}")

    contact = " · ".join(
        bit
        for bit in (
            f"**Website:** {company['website']}" if company.get("website") else None,
            f"**Phone:** {company['phone']}" if company.get("phone") else None,
            f"**Email:** {company['email']}" if company.get("email") else None,
        )
        if bit
    )
    if contact:
        lines.append(contact)

    if company.get("share_capital") is not None:
        currency = f" {company['share_capital_currency']}" if company.get("share_capital_currency") else ""
        lines.append(f"**Share capital:** {company['share_capital']}{currency}")

    return lines


def _render_text(company: dict[str, Any], deadline: dict[str, Any]) -> str:
    """The Markdown rendering of one `fetch` document (`CONNECTOR_SPEC.md` §2): fixed
    section order, a section with no content is omitted entirely, and every `notes`
    sentence survives verbatim — never summarised — because `notes` is where a country
    module's caveats live (D-010) and this rendering is the only thing a ChatGPT deep
    research run ever reads."""
    lines = [f"# {company['name']} — {company['country']} {company['id']}", ""]
    lines.extend(_identity_lines(company))
    lines.append("")

    deadline_rows = deadline.get("deadlines") or []
    if deadline_rows:
        lines.append(f"## Statutory filing deadlines (as of {deadline['today']})")
        for row in deadline_rows:
            label = row.get("local_name") or row["name"]
            when = f" ({row['days_until']} days)" if row.get("days_until") is not None else ""
            lines.append(f"- **{label}** — due {row['due_date']}{when}. {row['applies_because']}")
        lines.append("")

    published = company.get("published_deadlines") or []
    if published:
        lines.append("## Register-published dates")
        for row in published:
            entry = f"- {row['kind']}"
            if row.get("due_date"):
                entry += f": due {row['due_date']}"
            if row.get("source"):
                entry += f" (source: {row['source']})"
            lines.append(entry)
        lines.append("")

    notes = company.get("notes") or []
    if notes:
        lines.append("## Notes")
        lines.extend(f"- {note}" for note in notes)
        lines.append("")

    lines.append("## Source")
    citation = " — ".join(p for p in (company.get("source"), company.get("source_url")) if p)
    if citation:
        lines.append(citation)
    provenance = " · ".join(
        p
        for p in (
            f"Licence: {company['license']}" if company.get("license") else None,
            f"Fetched {company['fetched_at']}" if company.get("fetched_at") else None,
            f"Served from cache: {'yes' if company['cached'] else 'no'}",
        )
        if p
    )
    if provenance:
        lines.append(provenance)
    lines.append(
        "Relayed from the national register. Not a sanctions, PEP or adverse-media "
        "screening, and not a verification of bank account details."
    )
    return "\n".join(lines).strip()


def _rules_document(registry: Registry) -> ConnectorDocument:
    title = (
        f"{registry.name} ({registry.country}) — identifier rules, legal forms and "
        "filing deadlines"
    )
    return ConnectorDocument(
        id=f"rules:{registry.country}",
        title=title,
        text=registry.rules_markdown(),
        url=f"{PUBLIC_BASE_URL}/v1/countries",
        metadata={"country": registry.country, "registry": registry.registry},
    )


def _company_document(report: CompanyReport, deadlines: DeadlineReport) -> ConnectorDocument:
    """Assemble the `fetch` document from the same two operations `lookup_company` and
    `company_deadlines` already expose (D-031(d)) — `company`/`deadline` below are each
    `model_dump(mode="json")` of the model those tools return, byte-identical, so
    `metadata.company_report`/`.deadline_report` are exactly what those two tools would
    have returned for the same call."""
    company = report.model_dump(mode="json")
    deadline = deadlines.model_dump(mode="json")

    metadata: dict[str, Any] = {
        "company_report": company,
        "deadline_report": deadline,
        "country": company["country"],
        "registry": company["registry"],
        "company_id": company["id"],
        "name": company["name"],
        "status": company["status"],
        "is_active": company["is_active"],
        "legal_form": company.get("legal_form"),
        "source": company.get("source"),
        "source_url": company.get("source_url"),
        "license": company.get("license"),
        "cached": company["cached"],
        "fetched_at": company.get("fetched_at"),
    }
    deadline_rows = deadline.get("deadlines") or []
    if deadline_rows:
        metadata["next_deadline_kind"] = deadline_rows[0]["kind"]
        metadata["next_deadline_due_date"] = deadline_rows[0]["due_date"]

    return ConnectorDocument(
        id=f"{report.country}:{report.id}",
        title=f"{report.name} — {report.country} {report.id}",
        text=_render_text(company, deadline),
        url=_record_url(report.country, report.id),
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    output_schema=ConnectorSearchResponse.model_json_schema(),
    annotations={
        **_READ_EXTERNAL,
        "title": "Find a company (ChatGPT connector alias for search_company)",
    },
)
async def search(
    query: Annotated[
        str,
        Field(
            description=(
                "What to look for: a company name, a national identifier, or a name "
                "plus a country, e.g. 'Equinor', '923609016', 'Tesco United Kingdom'."
            ),
            examples=["Equinor", "923609016", "Tesco GB"],
        ),
    ],
) -> dict[str, Any]:
    """ChatGPT connector alias; other clients should prefer `search_company`, which takes an
    explicit `country` and returns the full SearchResult. Finds companies in this server's
    national business registers (Norway, United Kingdom) from one free-text query — a name, a
    national identifier, or a name plus a country — and returns {"results": [{"id", "title",
    "url"}]}. Pass a result's `id` to `fetch`.
    """
    with _call_context(operation="search", country=None, query=query) as outcome:
        stripped = query.strip()
        if not stripped:
            raise RegistryError(
                ErrorCode.BAD_REQUEST,
                "query must not be empty.",
                hint=(
                    "Call search again with a non-empty query — a company name, a "
                    "national identifier, or a name plus a country."
                ),
            )

        registries = list_registries()
        derived, remainder = _derive_country(stripped, registries)
        # D-040(b): the log's `country` is whatever `_derive_country` itself
        # produced (`None` on a miss) — the same signal `search` already
        # computes for its own fan-out, not a second, separate detection.
        outcome.country = derived.country if derived is not None else None
        candidates = [derived] if derived is not None else registries

        any_validated, ranked = await _identifier_rows(candidates, remainder)
        if not any_validated:
            ranked = await _name_search_rows(candidates, remainder)

        # D-040(b): blanket, by registry flag, never by digit count (D-040(d)). Every
        # maximal alphanumeric run of the query is checked against every *live flagged*
        # registry — not just `candidates`, which an explicit "NO"/"GB" token narrows to
        # one unflagged registry, and not just `remainder`, which is the whole string
        # whenever `_derive_country` missed. `Registry.validate` is pure and cheap.
        # `outcome.country` is left as `_derive_country` produced it — this redacts the
        # query without inventing a country.
        #
        # Residual, left open: a personnummer glued to other alphanumerics with no
        # separator (e.g. "x194009272719", "1940092727191234") is not a maximal run by
        # itself and so is not caught here. Closing that needs a substring/shape scan,
        # which is precisely what D-040(c) declined.
        flagged = [r for r in registries if r.id_may_be_personal]
        if flagged:
            runs = {stripped, remainder, *_ID_RUN.findall(stripped)}
            if any(r.validate(run).valid for r in flagged for run in runs if run):
                outcome.query = None

        rows = _merge_sort_and_cap(ranked, remainder)
        if not rows:
            rows = _rules_rows()

    return ConnectorSearchResponse(results=rows).model_dump(mode="json")


@mcp.tool(
    output_schema=ConnectorDocument.model_json_schema(),
    annotations={
        **_READ_EXTERNAL,
        "title": "Fetch one company record (ChatGPT connector alias for lookup_company)",
    },
)
async def fetch(
    id: Annotated[
        str,
        Field(
            description=(
                "An `id` from a `search` result: '{COUNTRY}:{identifier}', e.g. "
                "'NO:923609016' or 'GB:00445790'."
            ),
            examples=["NO:923609016", "GB:00445790"],
        ),
    ],
) -> dict[str, Any]:
    """ChatGPT connector alias; other clients should prefer `lookup_company` plus
    `company_deadlines`, which return the CompanyReport and DeadlineReport shapes directly.
    Takes one `id` from `search` — "{COUNTRY}:{identifier}", e.g. "NO:923609016" — and returns
    that company's register record and statutory filing deadlines as readable text, with both
    full JSON documents in `metadata`.
    """
    with _call_context(operation="fetch", country=None, query=id) as outcome:
        registry, identifier, is_rules = _resolve_fetch_id(id)
        if is_rules:
            document = _rules_document(registry)
        else:
            # D-040(b): now that the id has parsed, log the country it named
            # and the bare identifier — never the combined "{COUNTRY}:{id}"
            # string `fetch` was called with. Set before the lookup, so a
            # `RegistryError` raised below (not_found, upstream_error, ...)
            # still logs the real country/identifier rather than falling
            # back to this block's `None`/raw-id defaults.
            outcome.country = registry.country
            outcome.query = identifier
            report = await registry.lookup(identifier)
            today = parse_iso_date(None)
            deadlines = registry.deadline_report(report, today)
            outcome.cached = report.cached
            document = _company_document(report, deadlines)

    return document.model_dump(mode="json")
