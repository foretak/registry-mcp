#!/usr/bin/env python3
"""Agent eval harness for registry-mcp's five MCP tools (T19).

Two independent modes, selected by CLI flag:

* ``--golden`` (default, no LLM): for every case in ``cases.json``, execute
  the case's own *reference* tool calls against the in-process MCP server
  (``fastmcp.Client`` against ``registry_mcp.mcp.server:mcp``, the same
  pattern ``tests/test_mcp.py`` uses) and assert the case's expected facts.
  This is a deterministic regression suite for the *answers* a well-behaved
  trajectory would produce. It needs no API key and no network for any
  offline case; a case marked ``"live": true`` in ``cases.json`` is skipped
  unless ``--live`` is passed (and a GB live case is skipped further unless
  ``COMPANIES_HOUSE_API_KEY`` is set).

* ``--agent``: drives a real model through the same tools via a manual
  Anthropic Messages API tool-use loop, scoring tool selection, argument
  correctness and the final answer against the same case data, plus a
  fabrication hard gate on the final answer text. Skips cleanly (exit 0) when
  ``ANTHROPIC_API_KEY`` is unset, and again if the ``anthropic`` package
  itself is not installed (it lives in the optional ``eval`` dependency
  group, never in the project's runtime dependencies — see
  ``evals/README.md``).

Neither mode starts a real server process or binds a port: both drive the
``FastMCP`` server object directly, in-process.

See ``evals/README.md`` for what this measures, how to add a case, and the
cost note for ``--agent``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Final

import httpx
import respx
from fastmcp import Client

from registry_mcp.mcp.server import mcp
from registry_mcp.registries.gb import client as gb_client_module
from registry_mcp.registries.no import client as no_client_module


def _import_anthropic() -> Any:
    """The `anthropic` module, or `None` if the `eval` dependency group is
    not installed. A function with an `Any` return type, rather than a
    module-level `try: import anthropic except ImportError: anthropic =
    None`, deliberately: mypy resolves a module-level `import anthropic` to
    its *real* types whenever the package happens to be installed in the
    environment mypy runs in (the `ignore_missing_imports` override for it
    in pyproject.toml only applies when the import genuinely fails to
    resolve), so a bare module-level fallback flips between "assigning None
    to a Module-typed name" and "unused type: ignore" depending on ambient
    venv state — neither of which is this file's to control. Importing
    inside a function declared to return `Any` sidesteps that entirely."""
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic

EVALS_DIR = Path(__file__).parent
CASES_PATH = EVALS_DIR / "cases.json"
FIXTURES_DIR = EVALS_DIR.parent / "tests" / "fixtures"

DEFAULT_MODEL = "claude-sonnet-5"
MAX_AGENT_TURNS = 6
AGENT_MAX_TOKENS = 4096

# A sentinel distinct from `None`: `None` is a real value a check may assert
# on (e.g. `vat_registered is null`); `_MISSING` means the path did not
# resolve at all (a missing dict key, an out-of-range index, no list element
# matching a `[field=value]` filter).
_MISSING: Final[object] = object()

_PLACEHOLDER_RE = re.compile(r"^\{\{(\w+)\.(.+)\}\}$")
_SEGMENT_RE = re.compile(r"^([A-Za-z0-9_*]*)(?:\[([^\]]*)\])?$")


class HarnessGapError(Exception):
    """Raised when --agent mode hits a respx mock-coverage gap: the model
    called a real tool with reasonable arguments and the harness had no
    mocked response for the resulting HTTP request. This is always a
    problem with `cases.json`'s mock coverage, never a finding about model
    behaviour, so it is scored as its own "gap" status rather than a case
    FAIL (2026-09-05 follow-up, item 1)."""


def _is_respx_gap(exc: BaseException) -> bool:
    text = str(exc)
    return "RESPX:" in text and "not mocked" in text


# ---------------------------------------------------------------------------
# Path mini-language: `get_path(obj, "deadlines[kind=annual_accounts].due_date")`
# ---------------------------------------------------------------------------


def _split_bracket(segment: str) -> tuple[str, str | None]:
    match = _SEGMENT_RE.match(segment)
    if match is None:
        return segment, None
    key, bracket = match.group(1), match.group(2)
    return key, bracket


def _apply_bracket(obj: Any, bracket: str) -> Any:
    if not isinstance(obj, list):
        return _MISSING
    if "=" in bracket:
        field_name, _, expected = bracket.partition("=")
        for item in obj:
            if isinstance(item, dict) and str(item.get(field_name)) == expected:
                return item
        return _MISSING
    try:
        index = int(bracket)
    except ValueError:
        return _MISSING
    if -len(obj) <= index < len(obj):
        return obj[index]
    return _MISSING


def _resolve(obj: Any, segments: list[str]) -> Any:
    if obj is _MISSING:
        return _MISSING
    if not segments:
        return obj
    segment, rest = segments[0], segments[1:]
    if segment == "*":
        if not isinstance(obj, list):
            return _MISSING
        return [_resolve(item, rest) for item in obj]
    key, bracket = _split_bracket(segment)
    current = obj
    if key:
        if not isinstance(current, dict) or key not in current:
            return _MISSING
        current = current[key]
    if bracket is not None:
        current = _apply_bracket(current, bracket)
    return _resolve(current, rest)


def get_path(obj: Any, path: str) -> Any:
    """Resolve a dotted path with optional `[index]` / `[field=value]` / `[*]`
    segments against a plain JSON-shaped value (dicts, lists, scalars).

    Returns the module-level `_MISSING` sentinel, never raises, when any
    segment does not resolve — a missing dict key, an out-of-range index, or
    an object filter that matches no element. `path == ""` returns `obj`
    itself, so a check can assert on a whole resource-text string.
    """
    if path == "":
        return obj
    return _resolve(obj, path.split("."))


def _render(value: Any) -> Any:
    return "<missing>" if value is _MISSING else value


# ---------------------------------------------------------------------------
# Check operators
# ---------------------------------------------------------------------------


def _evaluate(value: Any, op: str, expected: Any) -> bool:
    if op == "equals":
        return bool(value == expected)
    if op == "not_equals":
        return bool(value != expected)
    if op == "is_null":
        return value is None
    if op == "not_null":
        return value is not None and value is not _MISSING
    if op == "is_missing":
        return value is _MISSING
    if op == "not_missing":
        return value is not _MISSING
    if op == "contains":
        if value is _MISSING or value is None:
            return False
        return bool(expected in value)
    if op == "not_contains":
        if value is _MISSING or value is None:
            return True
        return bool(expected not in value)
    if op == "any_contains":
        if not isinstance(value, list):
            return False
        return any(isinstance(item, str) and expected in item for item in value)
    if op == "none_contains":
        if not isinstance(value, list):
            return True
        return not any(isinstance(item, str) and expected in item for item in value)
    if op in {"lt", "lte", "gt", "gte"}:
        if value is _MISSING or value is None:
            return False
        if op == "lt":
            return bool(value < expected)
        if op == "lte":
            return bool(value <= expected)
        if op == "gt":
            return bool(value > expected)
        return bool(value >= expected)
    if op == "equals_set":
        if value is _MISSING:
            return False
        return set(value) == set(expected)
    if op == "length_equals":
        if value is _MISSING:
            return False
        return bool(len(value) == expected)
    if op == "confidence_non_increasing":
        if not isinstance(value, list) or not value:
            return False
        confidences = [item.get("confidence") for item in value]
        return all(confidences[i] >= confidences[i + 1] for i in range(len(confidences) - 1))
    raise ValueError(f"unknown check operator {op!r}")


# ---------------------------------------------------------------------------
# --agent free-text scoring: date/synonym-tolerant phrase matching, and a
# negation-aware fabrication gate (2026-09-05 follow-up, items 2 and 3).
# Deliberately small, literal tables rather than a general synonym engine or
# an LLM judge — see evals/README.md "What --agent scoring does and does not
# do" for why, and for the exact substitutions each one performs.
# ---------------------------------------------------------------------------

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: A phrase (lower-cased) that names a check "concept" maps to every
#: rendering of that concept this harness accepts as equivalent. Covers
#: exactly the pairs named in the 2026-09-05 follow-up (item 2): 'late' vs
#: 'overdue'; 'does not' vs "doesn't"/'not'; 'cannot' vs "can't"/'unable'.
_SYNONYM_GROUPS: dict[str, list[str]] = {
    "late": ["late", "overdue", "past due"],
    "overdue": ["overdue", "late", "past due"],
    "cannot": ["cannot", "can't", "unable to", "not able to", "unable"],
    "does not": ["does not", "doesn't", "did not", "didn't", "not"],
    #: A bare negation requirement must accept a contraction-only answer —
    #: "doesn't"/"isn't"/"didn't" contain no "not" substring at all ("n't"
    #: is not "not"), so a text that negates only via contractions would
    #: otherwise fail a literal 'not' check outright (observed live, E19).
    "not": ["not", "n't"],
    "not supported": [
        "not supported",
        "isn't supported",
        "unsupported",
        "doesn't support",
        "does not support",
        "not currently supported",
        "not available",
        "no coverage",
    ],
}

#: Mechanical contraction pairs, applied to a compound phrase that is not
#: itself a whole `_SYNONYM_GROUPS` entry (e.g. "does not publish" ->
#: "doesn't publish"), so a case does not need one of the fixed groups above
#: for every compound sentence fragment it happens to use.
_CONTRACTION_SUBS: list[tuple[str, str]] = [
    ("does not", "doesn't"),
    ("cannot", "can't"),
    ("is not", "isn't"),
    ("did not", "didn't"),
    ("will not", "won't"),
]


def _date_variants(iso: str) -> list[str]:
    """Every rendering of an ISO `YYYY-MM-DD` date this harness accepts as
    equivalent: ISO, '31 July 2026', 'July 31, 2026', '31.07.2026', etc."""
    d = date.fromisoformat(iso)
    month_name, month_abbr = d.strftime("%B"), d.strftime("%b")
    variants = {
        iso,
        f"{d.day} {month_name} {d.year}",
        f"{month_name} {d.day}, {d.year}",
        f"{month_name} {d.day} {d.year}",
        f"{d.day:02d}.{d.month:02d}.{d.year}",
        f"{d.day:02d}/{d.month:02d}/{d.year}",
        f"{d.day} {month_abbr} {d.year}",
        f"{month_abbr} {d.day}, {d.year}",
    }
    return [v.lower() for v in variants]


def _phrase_variants(phrase: str) -> list[str]:
    lowered = phrase.lower()
    if _ISO_DATE_RE.match(phrase):
        return _date_variants(phrase)
    if lowered in _SYNONYM_GROUPS:
        return _SYNONYM_GROUPS[lowered]
    variants = {lowered}
    for canonical, contraction in _CONTRACTION_SUBS:
        if canonical in lowered:
            variants.add(lowered.replace(canonical, contraction))
        if contraction in lowered:
            variants.add(lowered.replace(contraction, canonical))
    return list(variants)


def phrase_present(text_lower: str, phrase: str) -> bool:
    """Whether `phrase` (or an accepted date/contraction/synonym rendering
    of it) appears anywhere in `text_lower`. `text_lower` must already be
    lower-cased; `phrase` need not be."""
    return any(variant in text_lower for variant in _phrase_variants(phrase))


#: Cues that negate a nearby claim, checked against a sentence with the
#: matched forbidden phrase's own span removed (so a phrase that itself
#: contains a cue substring, e.g. "no data", cannot self-negate).
_NEGATION_CUES: list[str] = [
    "not ",
    "n't",
    "no ",
    "never",
    "without",
    "unlikely to",
    "not required",
    "not applicable",
    "no such",
    "not owe",
    "not owed",
    "not need",
    "doesn't need",
    "no need",
    "nothing to",
]
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?\n])\s+")


def find_unnegated_occurrence(text: str, phrase: str) -> str | None:
    """The first sentence in `text` that asserts `phrase` affirmatively —
    contains it with no negation cue anywhere else in that same sentence —
    or `None` if every occurrence of `phrase` is negated (or `phrase` never
    appears at all). Implements "asserts X applies" rather than "mentions
    X" for the fabrication gate (2026-09-05 follow-up, item 3): a sentence
    that correctly says a duty does *not* apply must not fail the gate."""
    phrase_lower = phrase.lower()
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        s_lower = sentence.lower()
        idx = s_lower.find(phrase_lower)
        if idx == -1:
            continue
        context = s_lower[:idx] + s_lower[idx + len(phrase_lower) :]
        if any(cue in context for cue in _NEGATION_CUES):
            continue
        return sentence.strip()
    return None


@dataclass
class CheckOutcome:
    passed: bool
    is_gate: bool
    message: str


def run_checks(checks: list[dict[str, Any]], results_by_index: dict[int, Any]) -> list[CheckOutcome]:
    outcomes: list[CheckOutcome] = []
    for check in checks:
        call_index = check["call"]
        path = check["path"]
        op = check["op"]
        expected = check.get("value")
        is_gate = bool(check.get("gate", False))
        base = results_by_index.get(call_index, _MISSING)
        value = get_path(base, path)
        try:
            passed = _evaluate(value, op, expected)
        except ValueError as exc:
            outcomes.append(CheckOutcome(False, is_gate, str(exc)))
            continue
        note = check.get("note")
        detail = f"call[{call_index}] {path!r} {op} {expected!r} -> got {_render(value)!r}"
        if note:
            detail = f"{detail} ({note})"
        outcomes.append(CheckOutcome(passed, is_gate, detail))
    return outcomes


# ---------------------------------------------------------------------------
# respx mock installation — a small, declarative vocabulary covering every
# offline case in cases.json (see evals/README.md "Adding a case").
# ---------------------------------------------------------------------------


def _load_fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
    return data


def install_mocks(mocks: list[dict[str, Any]]) -> None:
    """Register respx routes for one case's `setup.mocks`. Must be called
    inside an active `with respx.mock:` block."""
    for mock in mocks:
        country = mock["country"]
        kind = mock["kind"]
        base = no_client_module.BASE_URL if country == "NO" else gb_client_module.BASE_URL
        if country == "NO" and kind == "lookup":
            respx.get(f"{base}/enheter/{mock['id']}").mock(
                return_value=httpx.Response(200, json=_load_fixture(mock["fixture"]))
            )
        elif country == "NO" and kind == "lookup_404":
            respx.get(f"{base}/enheter/{mock['id']}").mock(return_value=httpx.Response(404))
            respx.get(f"{base}/underenheter/{mock['id']}").mock(return_value=httpx.Response(404))
        elif country == "NO" and kind == "search":
            fixture = _load_fixture(mock["fixture"])
            envelope = {
                "_embedded": {"enheter": [fixture]},
                "page": {"size": 1, "totalElements": 1, "totalPages": 1, "number": 0},
            }
            respx.get(f"{base}/enheter").mock(return_value=httpx.Response(200, json=envelope))
        elif country == "NO" and kind == "search_empty":
            respx.get(f"{base}/enheter").mock(
                return_value=httpx.Response(200, json={"page": {"totalElements": 0}})
            )
        elif country == "GB" and kind == "lookup":
            respx.get(f"{base}/company/{mock['id']}").mock(
                return_value=httpx.Response(200, json=_load_fixture(mock["fixture"]))
            )
        elif country == "GB" and kind == "search":
            respx.get(f"{base}/search/companies").mock(
                return_value=httpx.Response(200, json=_load_fixture(mock["fixture"]))
            )
        else:
            raise ValueError(f"unknown mock {country}/{kind}")


# ---------------------------------------------------------------------------
# --agent mode mock coverage (2026-09-05 follow-up, item 1): in golden mode
# every HTTP call is one of the case's own reference `calls`, so the small,
# curated `install_mocks` above is exactly right. A real model may call any
# of the five tools with any reasonable arguments — search before looking up
# an id the prompt already gave, look up a *different* known entity to double
# -check, and so on — so agent mode gets a comprehensive fallback built
# directly from every entity fixture in tests/fixtures/, on top of whatever
# the case itself declares. A case's own declared mocks are installed last so
# a deliberate not-found/zero-hit/curated-search mock (E07, E16, E06) always
# overrides the generic fallback for the same route (verified empirically:
# respx resolves two mocks registered against the identical pattern by using
# the most-recently-registered one, but resolves two *different* patterns —
# e.g. a specific id vs the trailing regex catch-all below — in registration
# order, first match wins). A route nothing here anticipates still raises
# respx's AllMockedAssertionError, which run_agent_case turns into a "gap"
# status rather than a model-behaviour failure.
# ---------------------------------------------------------------------------

_EntityFixtures = dict[str, list[tuple[str, dict[str, Any]]]]
_entity_fixtures_cache: _EntityFixtures | None = None


def _all_entity_fixtures() -> _EntityFixtures:
    """Every committed `tests/fixtures/*.json` that is a full company record
    — has the NO or GB entity's identifying keys — grouped by country.
    Excludes search-envelope fixtures (`ch_search_*.json`, keyed by `items`/
    `total_results` instead) and raw upstream error bodies (`ch_401.json`,
    `ch_404.json`, keyed by neither). Cached: the fixture directory does not
    change during one run.
    """
    global _entity_fixtures_cache
    if _entity_fixtures_cache is not None:
        return _entity_fixtures_cache
    no_entities: list[tuple[str, dict[str, Any]]] = []
    gb_entities: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if "organisasjonsnummer" in data and "navn" in data:
            no_entities.append((str(data["organisasjonsnummer"]), data))
        elif "company_number" in data and "company_name" in data:
            gb_entities.append((str(data["company_number"]), data))
    _entity_fixtures_cache = {"NO": no_entities, "GB": gb_entities}
    return _entity_fixtures_cache


def _gb_entity_to_search_item(data: dict[str, Any]) -> dict[str, Any]:
    """A full `GET /company/{id}` body reshaped into one `GET
    /search/companies` `items[]` entry (`registries/gb/mapping.py::
    map_search_hit`'s field names), for the synthesized generic GB search
    envelope below."""
    return {
        "title": data.get("company_name"),
        "company_number": data.get("company_number"),
        "company_type": data.get("type"),
        "company_status": data.get("company_status"),
        "address": data.get("registered_office_address"),
        "date_of_creation": data.get("date_of_creation"),
    }


def _generic_search_envelope(country: str) -> dict[str, Any]:
    """A search response containing every known entity fixture for
    `country`, in the shape `map_search_result` expects. respx cannot
    discriminate by query text, so every query returns the same candidate
    set; the client's own D-005/D-020 confidence scoring and sort still put
    the actual best match first, exactly as it would for a real query that
    happened to return some irrelevant hits alongside the right one."""
    entities = _all_entity_fixtures()[country]
    if country == "NO":
        return {
            "_embedded": {"enheter": [data for _, data in entities]},
            "page": {
                "size": len(entities),
                "totalElements": len(entities),
                "totalPages": 1,
                "number": 0,
            },
        }
    items = [_gb_entity_to_search_item(data) for _, data in entities]
    return {"items": items, "total_results": len(items)}


def install_agent_mocks(case: dict[str, Any]) -> None:
    """The comprehensive respx layer for --agent mode. Must be called inside
    an active `with respx.mock:` block, and only for a non-`live` case.
    Registration order matters (see the module docstring above this
    function's section): generic per-fixture lookups and searches first, the
    case's own declared mocks next (so an identical-pattern override wins),
    a regex 404 catch-all last (so it only ever catches an id genuinely
    outside the fixture set, never shadows a real one)."""
    entities = _all_entity_fixtures()
    for entity_id, data in entities["NO"]:
        respx.get(f"{no_client_module.BASE_URL}/enheter/{entity_id}").mock(
            return_value=httpx.Response(200, json=data)
        )
    respx.get(f"{no_client_module.BASE_URL}/enheter").mock(
        return_value=httpx.Response(200, json=_generic_search_envelope("NO"))
    )
    for entity_id, data in entities["GB"]:
        respx.get(f"{gb_client_module.BASE_URL}/company/{entity_id}").mock(
            return_value=httpx.Response(200, json=data)
        )
    respx.get(f"{gb_client_module.BASE_URL}/search/companies").mock(
        return_value=httpx.Response(200, json=_generic_search_envelope("GB"))
    )

    install_mocks(case.get("setup", {}).get("mocks", []))

    no_base_re = re.escape(no_client_module.BASE_URL)
    gb_base_re = re.escape(gb_client_module.BASE_URL)
    respx.route(method="GET", url__regex=rf"^{no_base_re}/enheter/\d+$").mock(
        return_value=httpx.Response(404)
    )
    respx.route(method="GET", url__regex=rf"^{no_base_re}/underenheter/\d+$").mock(
        return_value=httpx.Response(404)
    )
    respx.route(method="GET", url__regex=rf"^{gb_base_re}/company/[A-Za-z0-9]+$").mock(
        return_value=httpx.Response(404)
    )


# ---------------------------------------------------------------------------
# Per-case environment: cache disabled, GB credential mode, fresh HTTP clients
# ---------------------------------------------------------------------------


def gb_key_available() -> bool:
    return bool(os.environ.get("COMPANIES_HOUSE_API_KEY", "").strip())


def anthropic_key_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


@contextmanager
def case_environment(gb_api_key_mode: str) -> Iterator[None]:
    """Disable the on-disk cache (every case must hit its mock/network fresh),
    set `COMPANIES_HOUSE_API_KEY` per the case's `setup.gb_api_key`
    ("dummy" | "unset" | "real"), and reset both registries' module-level
    `httpx.AsyncClient` so no case can see another's connection or cached
    Companies House auth header. Restores the prior environment on exit."""
    saved_environ = dict(os.environ)
    os.environ["REGISTRY_MCP_CACHE_DISABLED"] = "1"
    if gb_api_key_mode == "unset":
        os.environ.pop("COMPANIES_HOUSE_API_KEY", None)
    elif gb_api_key_mode == "dummy":
        os.environ["COMPANIES_HOUSE_API_KEY"] = "eval-harness-dummy-key"
    # "real": leave the ambient environment exactly as the caller set it.
    no_client_module._client = None
    gb_client_module._client = None
    try:
        yield
    finally:
        no_client_module._client = None
        gb_client_module._client = None
        os.environ.clear()
        os.environ.update(saved_environ)


# ---------------------------------------------------------------------------
# Executing a case's reference `calls` against the in-process MCP server
# ---------------------------------------------------------------------------


def resolve_placeholders(arguments: dict[str, Any], results_by_label: dict[str, Any]) -> dict[str, Any]:
    """Replace an argument value of the exact form `"{{label.path}}"` with
    `get_path(results_by_label[label], path)` — how E05/E06-style cases feed
    a `search_company` hit's `id` into the following `lookup_company` call."""
    resolved: dict[str, Any] = {}
    for key, raw_value in arguments.items():
        if isinstance(raw_value, str):
            match = _PLACEHOLDER_RE.match(raw_value)
            if match is not None:
                label, path = match.group(1), match.group(2)
                resolved[key] = get_path(results_by_label.get(label, _MISSING), path)
                continue
        resolved[key] = raw_value
    return resolved


def _parse_error(exc: Exception) -> dict[str, Any]:
    """The D-007 `{"error": {...}}` envelope out of a raised ToolError/
    ResourceError's text — same pattern as `content/call.py`."""
    try:
        parsed: Any = json.loads(str(exc))
    except json.JSONDecodeError:
        parsed = {"error": {"message": str(exc)}}
    result: dict[str, Any] = parsed
    return result


async def execute_calls(
    client: Any, calls: list[dict[str, Any]]
) -> tuple[dict[int, Any], dict[str, Any], list[str]]:
    """Run one case's reference trajectory. Returns (result-by-call-index,
    result-by-save_as-label, trajectory problems e.g. an unexpected raise or
    a call that unexpectedly succeeded)."""
    results_by_index: dict[int, Any] = {}
    results_by_label: dict[str, Any] = {}
    problems: list[str] = []

    for index, call in enumerate(calls):
        call_type = call["type"]
        if call_type not in {"tool", "resource"}:
            raise ValueError(f"cases.json call[{index}]: unknown call type {call_type!r}")
        arguments = resolve_placeholders(call.get("arguments", {}), results_by_label)
        expect_error = call.get("expect_error")
        label = f"{call.get('tool') or call.get('uri')}"
        try:
            if call_type == "tool":
                tool_result = await client.call_tool(call["tool"], arguments)
                value: Any = tool_result.structured_content
            else:
                contents = await client.read_resource(call["uri"])
                value = contents[0].text
        except Exception as exc:  # the D-007 envelope arrives as the exception text
            if _is_respx_gap(exc):
                raise HarnessGapError(f"call[{index}] {label} hit an unmocked HTTP request") from exc
            parsed = _parse_error(exc)
            if expect_error is None:
                problems.append(f"call[{index}] {label} raised unexpectedly: {parsed}")
            else:
                actual_code = get_path(parsed, "error.code")
                if actual_code != expect_error.get("code"):
                    problems.append(
                        f"call[{index}] {label}: expected error code "
                        f"{expect_error.get('code')!r}, got {actual_code!r}"
                    )
            results_by_index[index] = parsed
            if call.get("save_as"):
                results_by_label[call["save_as"]] = parsed
            continue

        if expect_error is not None:
            problems.append(
                f"call[{index}] {label} was expected to raise "
                f"{expect_error.get('code')!r} but succeeded"
            )
        results_by_index[index] = value
        if call.get("save_as"):
            results_by_label[call["save_as"]] = value

    return results_by_index, results_by_label, problems


async def run_calls(calls: list[dict[str, Any]]) -> tuple[dict[int, Any], dict[str, Any], list[str]]:
    async with Client(mcp) as client:
        return await execute_calls(client, calls)


# ---------------------------------------------------------------------------
# Golden mode
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    case_id: str
    group: str
    mode: str
    status: str  # "pass" | "fail" | "skip"
    notes: list[str] = field(default_factory=list)


async def run_golden_case(case: dict[str, Any], run_live: bool) -> CaseResult:
    case_id = case["id"]
    group = case["group"]
    setup = case.get("setup", {})
    gb_api_key_mode = setup.get("gb_api_key", "dummy")
    is_live = bool(case.get("live", False))

    if is_live and not run_live:
        return CaseResult(case_id, group, "golden", "skip", ["live case; run with --live"])
    if is_live and gb_api_key_mode == "real" and not gb_key_available():
        return CaseResult(
            case_id, group, "golden", "skip", ["live GB case; COMPANIES_HOUSE_API_KEY not set"]
        )

    calls = case.get("calls", [])
    if not calls:
        return CaseResult(
            case_id, group, "golden", "skip", ["no server interaction defined; see the case's notes"]
        )

    with case_environment(gb_api_key_mode):
        try:
            if is_live:
                results_by_index, _, problems = await run_calls(calls)
            else:
                with respx.mock:
                    install_mocks(setup.get("mocks", []))
                    results_by_index, _, problems = await run_calls(calls)
        except HarnessGapError as exc:
            return CaseResult(case_id, group, "golden", "gap", [str(exc)])

    outcomes = run_checks(case.get("checks", []), results_by_index)
    notes: list[str] = list(problems)
    notes.extend(f"FAIL: {o.message}" for o in outcomes if not o.passed and not o.is_gate)
    notes.extend(f"GATE FAIL: {o.message}" for o in outcomes if not o.passed and o.is_gate)

    if notes:
        return CaseResult(case_id, group, "golden", "fail", notes)
    gate_count = sum(1 for o in outcomes if o.is_gate)
    summary = f"{len(outcomes)} check(s) passed"
    if gate_count:
        summary += f" ({gate_count} of them a fabrication gate)"
    return CaseResult(case_id, group, "golden", "pass", [summary])


async def run_golden_mode(cases: list[dict[str, Any]], run_live: bool) -> list[CaseResult]:
    return [await run_golden_case(case, run_live) for case in cases]


# ---------------------------------------------------------------------------
# Agent mode
# ---------------------------------------------------------------------------

_READ_RULES_TOOL: dict[str, Any] = {
    "name": "read_registry_rules",
    "description": (
        "Read the human/LLM-readable rules summary for one country's national company "
        "register (identifier format, legal forms, the filing deadlines this service "
        "computes) without calling a network-touching tool. This mirrors the MCP resource "
        "registry://rules/{country} a real MCP client would also expose."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "country": {
                "type": "string",
                "description": "ISO-3166-1 alpha-2 country code, e.g. 'NO' or 'GB'.",
            }
        },
        "required": ["country"],
        "additionalProperties": False,
    },
}


def anthropic_tools_from_mcp(tools: list[Any]) -> list[dict[str, Any]]:
    converted = [
        {"name": tool.name, "description": tool.description or "", "input_schema": tool.input_schema}
        for tool in tools
    ]
    converted.append(_READ_RULES_TOOL)
    return converted


async def execute_agent_tool(client: Any, name: str, tool_input: dict[str, Any]) -> tuple[str, bool, Any]:
    """Bridge one Anthropic `tool_use` block to the in-process MCP server.
    Returns (content string for the tool_result block, is_error, the parsed
    structured value — a dict for a tool call, the raw text for a resource
    read, or the parsed D-007 error envelope on failure — captured so
    --agent mode can run the same structured `checks` golden mode does
    against what the model actually received, not just its prose).

    Raises HarnessGapError, uncaught, when the underlying cause is a respx
    mock-coverage gap: that is never a `tool_result` to hand back to the
    model, it is a reason to abort the trial and mark the whole case a
    harness gap (2026-09-05 follow-up, item 1)."""
    try:
        if name == "read_registry_rules":
            contents = await client.read_resource(f"registry://rules/{tool_input.get('country', '')}")
            text = str(contents[0].text)
            return text, False, text
        result = await client.call_tool(name, tool_input)
        value: Any = result.structured_content
        return json.dumps(value, default=str), False, value
    except Exception as exc:  # the D-007 envelope arrives as the exception text
        if _is_respx_gap(exc):
            raise HarnessGapError(
                f"tool {name}({tool_input!r}) hit an unmocked HTTP request"
            ) from exc
        parsed = _parse_error(exc)
        return json.dumps(parsed), True, parsed


@dataclass
class AgentTrial:
    calls_made: list[tuple[str, dict[str, Any]]]
    final_text: str
    #: Every structured result seen for each MCP tool name actually called,
    #: as (arguments, result) pairs in call order (a result is a dict on
    #: success, the parsed D-007 error envelope on failure) — kept as a list,
    #: not just the last one, because a case may call the same tool several
    #: times with different arguments each independently checked (E23's
    #: three validate_company_id calls; E17's bad-format-then-corrected
    #: company_deadlines retry).
    results_by_tool: dict[str, list[tuple[dict[str, Any], Any]]]
    #: Last `registry://rules/{cc}` text seen for each URI actually read via
    #: the synthetic `read_registry_rules` tool.
    resource_text_by_uri: dict[str, str]


async def run_agent_trial(
    async_client: Any, model: str, mcp_client: Any, tools: list[dict[str, Any]], prompt: str
) -> AgentTrial:
    """One tool-use loop for one case.

    Raises HarnessGapError, uncaught, when a tool call hits a respx
    mock-coverage gap — the caller aborts the whole case on this, it does
    not retry or continue the loop.
    """
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    calls_made: list[tuple[str, dict[str, Any]]] = []
    results_by_tool: dict[str, list[tuple[dict[str, Any], Any]]] = {}
    resource_text_by_uri: dict[str, str] = {}
    final_text = ""

    for _turn in range(MAX_AGENT_TURNS):
        response = await async_client.messages.create(
            model=model,
            max_tokens=AGENT_MAX_TOKENS,
            system=mcp.instructions,
            tools=tools,
            messages=messages,
        )
        if response.stop_reason != "tool_use":
            final_text = "".join(block.text for block in response.content if block.type == "text")
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool_input = dict(block.input)
            calls_made.append((block.name, tool_input))
            content, is_error, parsed_value = await execute_agent_tool(mcp_client, block.name, tool_input)
            if block.name == "read_registry_rules":
                uri = f"registry://rules/{tool_input.get('country', '')}"
                resource_text_by_uri[uri] = str(parsed_value)
            else:
                results_by_tool.setdefault(block.name, []).append((tool_input, parsed_value))
            tool_result: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content,
            }
            if is_error:
                tool_result["is_error"] = True
            tool_results.append(tool_result)
        messages.append({"role": "user", "content": tool_results})
    else:
        final_text = "(no final answer: hit the turn cap without an end_turn)"

    return AgentTrial(calls_made, final_text, results_by_tool, resource_text_by_uri)


def _find_matching_call(ref_args: dict[str, Any], candidates: list[tuple[dict[str, Any], Any]]) -> Any:
    """Which of the agent's several actual calls to one tool corresponds to
    one specific reference call, when a case calls that tool more than once
    (E23's three `validate_company_id` calls; E14/E17's retry-shaped ones).

    Matches on whichever of `id`/`name`/`country` the reference call itself
    specifies (case-insensitive for strings) — the identifying arguments for
    every tool in this project — and, among ties, prefers the *last* matching
    call, so a corrected retry (E17) or a self-correction (E14) is judged on
    the call that actually succeeded rather than an earlier failed attempt.
    `today`/`limit` are deliberately excluded from the match key: they are
    what legitimately *varies* across a retry, not what identifies which
    call a check is about. Falls back to the plain last call when nothing
    identifying matches (or the reference call gave no identifying argument
    at all) rather than reporting a spurious mismatch.
    """
    if not candidates:
        return _MISSING

    def norm(value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value

    identifying_keys = [k for k in ("id", "name", "country") if k in ref_args]
    if identifying_keys:
        matches = [
            result
            for actual_args, result in candidates
            if all(norm(actual_args.get(k)) == norm(ref_args[k]) for k in identifying_keys)
        ]
        if matches:
            return matches[-1]
    return candidates[-1][1]


def _run_agent_structured_checks(case: dict[str, Any], trial: AgentTrial) -> list[CheckOutcome]:
    """The case's own `checks` (the same ones golden mode runs), evaluated
    against what the agent's actual tool calls returned rather than against
    a fixed call index — "prefer structured checks ... over free-text
    phrase matching wherever possible" (2026-09-05 follow-up, item 2).

    A check is skipped, not failed, when its reference call in `calls` is an
    `expect_error` leg (E14/E15/E16/E17/E18's error-path checks: whether the
    agent actually took that leg is a trajectory question, scored by the
    required/forbidden-tool and repeated-call checks below, not by a fact
    lookup) or when the agent never actually invoked that tool/resource at
    all (silently missing is `required_tools`' job, not this one's — this
    only judges a fact the agent *did* receive).
    """
    outcomes: list[CheckOutcome] = []
    calls = case.get("calls", [])
    for check in case.get("checks", []):
        call_index = check["call"]
        if call_index >= len(calls):
            continue
        ref_call = calls[call_index]
        if ref_call.get("expect_error") is not None:
            continue
        if ref_call["type"] == "tool":
            candidates = trial.results_by_tool.get(ref_call["tool"], [])
            base = _find_matching_call(ref_call.get("arguments", {}), candidates)
            source = ref_call["tool"]
        else:
            base = trial.resource_text_by_uri.get(ref_call["uri"], _MISSING)
            source = ref_call["uri"]
        if base is _MISSING:
            continue
        path, op, expected = check["path"], check["op"], check.get("value")
        is_gate = bool(check.get("gate", False))
        value = get_path(base, path)
        try:
            passed = _evaluate(value, op, expected)
        except ValueError as exc:
            outcomes.append(CheckOutcome(False, is_gate, str(exc)))
            continue
        detail = f"[structured] {source} {path!r} {op} {expected!r} -> got {_render(value)!r}"
        if check.get("note"):
            detail = f"{detail} ({check['note']})"
        outcomes.append(CheckOutcome(passed, is_gate, detail))
    return outcomes


def _score_agent_trial(case: dict[str, Any], trial: AgentTrial) -> list[str]:
    """Best-effort heuristic scoring — see evals/README.md's "What --agent
    scoring does and does not do" for the documented limitations. Returns a
    list of problems; empty means the trial passed."""
    agent_cfg = case.get("agent", {})
    problems: list[str] = []
    calls_made = trial.calls_made
    called_names = [name for name, _ in calls_made]

    required = agent_cfg.get("required_tools")
    if required is None:
        required = sorted({c["tool"] for c in case.get("calls", []) if c["type"] == "tool"})
    for tool_name in required:
        if tool_name not in called_names:
            problems.append(f"required tool {tool_name!r} was never called")

    is_restraint_gate = bool(agent_cfg.get("gate", False))
    for tool_name in called_names:
        if tool_name in agent_cfg.get("forbidden_tools", []):
            prefix = "GATE FAIL" if is_restraint_gate else "FAIL"
            problems.append(f"{prefix}: forbidden tool {tool_name!r} was called")

    max_calls = agent_cfg.get("max_tool_calls")
    if max_calls is not None and len(calls_made) > max_calls:
        problems.append(f"{len(calls_made)} tool calls made, expected at most {max_calls}")

    seen_calls: set[tuple[str, str]] = set()
    for name, actual_args in calls_made:
        key = (name, json.dumps(actual_args, sort_keys=True, default=str))
        if key in seen_calls:
            problems.append(f"FAIL: identical call repeated: {name}({actual_args!r})")
        seen_calls.add(key)

    expected_by_tool: dict[str, list[dict[str, Any]]] = {}
    for expected_call in case.get("calls", []):
        if expected_call["type"] == "tool":
            expected_by_tool.setdefault(expected_call["tool"], []).append(expected_call)
    arg_alternatives = agent_cfg.get("argument_alternatives", {})
    for name, actual_args in calls_made:
        expected_list = expected_by_tool.get(name)
        if not expected_list:
            continue
        if any(
            _arguments_match(actual_args, expected_call.get("arguments", {}), arg_alternatives.get(name, {}))
            for expected_call in expected_list
        ):
            continue
        problems.append(f"{name}({actual_args!r}) did not match any expected argument set for this case")

    for outcome in _run_agent_structured_checks(case, trial):
        if outcome.passed:
            continue
        prefix = "GATE FAIL" if outcome.is_gate else "FAIL"
        problems.append(f"{prefix}: {outcome.message}")

    lowered = trial.final_text.lower()
    for entry in agent_cfg.get("answer_must_include", []):
        options = entry if isinstance(entry, list) else [entry]
        if not any(phrase_present(lowered, opt) for opt in options):
            problems.append(f"final answer missing expected phrase (any of) {options!r}")
    for entry in agent_cfg.get("answer_must_not_include", []):
        options = entry if isinstance(entry, list) else [entry]
        for phrase in options:
            offending = find_unnegated_occurrence(trial.final_text, phrase)
            if offending is not None:
                problems.append(
                    f"GATE FAIL: final answer asserts forbidden phrase {phrase!r}: {offending!r}"
                )

    return problems


#: `country`'s documented default on every one of the five tools
#: (`mcp/server.py`) is `"NO"` — a model that relies on that default rather
#: than passing it explicitly has made exactly as correct a call as one that
#: types it out, so an omitted `country` must match an expected `"NO"`.
_DEFAULT_COUNTRY = "NO"

#: Free-text arguments have no canonical rendering to match against — a
#: `search_company` query of "Tesco" and one of "Tesco PLC" are both a
#: perfectly good call, and only the *result* (checked separately, via
#: structured checks on `hits`) says whether either one was good enough.
#: Excluded from argument-correctness checking entirely (2026-09-05
#: follow-up: observed a real trial searching "Tesco" where the reference
#: call used "Tesco PLC", spuriously flagged as a mismatched call).
_FREE_TEXT_ARGS = frozenset({"name"})


def _arguments_match(
    actual: dict[str, Any], expected: dict[str, Any], alternatives: dict[str, list[Any]]
) -> bool:
    for arg_name, expected_value in expected.items():
        if arg_name in _FREE_TEXT_ARGS:
            continue
        if isinstance(expected_value, str) and _PLACEHOLDER_RE.match(expected_value):
            continue  # a dynamic value (e.g. an id taken from a prior search hit)
        allowed = alternatives.get(arg_name, [expected_value])
        if allowed == ["*"]:
            continue  # any value, including absence, is acceptable (e.g. an
            # unpinned `today` the prompt never gave the agent a reason to guess)
        actual_value = actual.get(arg_name)
        if actual_value is None and arg_name == "country" and expected_value == _DEFAULT_COUNTRY:
            continue  # relying on the documented default is not a mismatch
        norm_actual = actual_value.upper() if isinstance(actual_value, str) else actual_value
        norm_allowed = [v.upper() if isinstance(v, str) else v for v in allowed]
        if norm_actual not in norm_allowed:
            return False
    return True


async def run_agent_case(
    async_client: Any, model: str, case: dict[str, Any], run_live: bool, trials: int
) -> CaseResult:
    case_id, group = case["id"], case["group"]
    setup = case.get("setup", {})
    gb_api_key_mode = setup.get("gb_api_key", "dummy")
    is_live = bool(case.get("live", False))

    if is_live and not run_live:
        return CaseResult(case_id, group, "agent", "skip", ["live case; run with --live"])
    if is_live and gb_api_key_mode == "real" and not gb_key_available():
        return CaseResult(
            case_id, group, "agent", "skip", ["live GB case; COMPANIES_HOUSE_API_KEY not set"]
        )

    passes = 0
    trial_notes: list[str] = []
    for trial_num in range(trials):
        with case_environment(gb_api_key_mode):
            try:
                async with Client(mcp) as mcp_client:
                    tools_list = await mcp_client.list_tools()
                    tools = anthropic_tools_from_mcp(tools_list)
                    if is_live:
                        trial = await run_agent_trial(
                            async_client, model, mcp_client, tools, case["prompt"]
                        )
                    else:
                        with respx.mock:
                            install_agent_mocks(case)
                            trial = await run_agent_trial(
                                async_client, model, mcp_client, tools, case["prompt"]
                            )
            except HarnessGapError as exc:
                # A mock-coverage gap is a harness problem, never a model
                # finding (2026-09-05 follow-up, item 1) — stop immediately
                # rather than burn further trials against the same gap.
                return CaseResult(case_id, group, "agent", "gap", [str(exc)])
            except Exception as exc:  # anthropic API/network error, etc.
                trial_notes.append(f"trial {trial_num + 1}: agent loop raised: {exc}")
                continue

        problems = _score_agent_trial(case, trial)
        if case.get("agent", {}).get("first_try_date_metric"):
            first_call = next((a for n, a in trial.calls_made if n == "company_deadlines"), None)
            today_value = first_call.get("today") if first_call else None
            ok = bool(today_value and re.match(r"^\d{4}-\d{2}-\d{2}$", str(today_value)))
            trial_notes.append(f"trial {trial_num + 1}: first-try today format valid={ok}")

        if problems:
            trial_notes.append(
                f"trial {trial_num + 1}: FAIL - "
                + "; ".join(problems)
                + f" | tools={called_tool_names(trial.calls_made)}, answer={trial.final_text[:200]!r}"
            )
        else:
            passes += 1
            trial_notes.append(
                f"trial {trial_num + 1}: pass - tools={called_tool_names(trial.calls_made)}, "
                f"answer={trial.final_text[:160]!r}"
            )

    status = "pass" if passes == trials else "fail"
    trial_notes.insert(0, f"pass rate {passes}/{trials}")
    return CaseResult(case_id, group, "agent", status, trial_notes)


def called_tool_names(calls_made: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [name for name, _ in calls_made]


async def run_agent_mode(
    cases: list[dict[str, Any]], model: str, run_live: bool, trials: int
) -> list[CaseResult]:
    if not anthropic_key_available():
        print("ANTHROPIC_API_KEY is not set; skipping --agent mode.", file=sys.stderr)
        return [CaseResult(c["id"], c["group"], "agent", "skip", ["ANTHROPIC_API_KEY is not set"]) for c in cases]
    anthropic_module = _import_anthropic()
    if anthropic_module is None:
        print(
            "The 'anthropic' package is not installed (it is kept out of the project's "
            "runtime dependencies). Run:\n"
            "  uv run --group eval python evals/run.py --agent\n"
            "to install it and try again.",
            file=sys.stderr,
        )
        return [
            CaseResult(c["id"], c["group"], "agent", "skip", ["anthropic package not installed"])
            for c in cases
        ]

    async_client = anthropic_module.AsyncAnthropic()
    results: list[CaseResult] = []
    for case in cases:
        results.append(await run_agent_case(async_client, model, case, run_live, trials))
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


_STATUS_LABELS: dict[str, str] = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP", "gap": "GAP"}


def render_markdown(results: list[CaseResult]) -> str:
    lines = [
        "| Case | Group | Mode | Status | Notes |",
        "|---|---|---|---|---|",
    ]
    for result in results:
        notes = _escape_cell("; ".join(result.notes)) if result.notes else ""
        lines.append(
            f"| {result.case_id} | {result.group} | {result.mode} | "
            f"{_STATUS_LABELS[result.status]} | {notes} |"
        )
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    skipped = sum(1 for r in results if r.status == "skip")
    gaps = sum(1 for r in results if r.status == "gap")
    lines.append("")
    summary = f"**{passed} passed, {failed} failed, {skipped} skipped** out of {len(results)}."
    if gaps:
        summary = summary[:-1] + f", **{gaps} harness gap(s)** (not a model finding — fix the mocks)."
    lines.append(summary)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def load_cases(case_ids: list[str] | None) -> list[dict[str, Any]]:
    data: dict[str, Any] = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = data["cases"]
    if case_ids:
        wanted = set(case_ids)
        cases = [c for c in cases if c["id"] in wanted]
    return cases


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden", action="store_true", help="run golden (no-LLM) mode")
    parser.add_argument(
        "--agent", action="store_true", help="run agent mode (drives a real model through the MCP tools)"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="also run cases marked live:true in cases.json (needs network; GB ones also need "
        "COMPANIES_HOUSE_API_KEY)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"model id for --agent (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--trials", type=int, default=1, help="repeat each --agent case this many times (default: 1)"
    )
    parser.add_argument("--case", action="append", default=None, help="only run this case id (repeatable)")
    parser.add_argument("--out", type=Path, default=None, help="also write the markdown summary to this file")
    args = parser.parse_args(argv)
    if not args.golden and not args.agent:
        args.golden = True
    return args


async def main_async(args: argparse.Namespace) -> int:
    cases = load_cases(args.case)
    all_results: list[CaseResult] = []

    if args.golden:
        all_results.extend(await run_golden_mode(cases, args.live))
    if args.agent:
        all_results.extend(await run_agent_mode(cases, args.model, args.live, args.trials))

    report = render_markdown(all_results)
    print(report)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8")

    return 1 if any(r.status in {"fail", "gap"} for r in all_results) else 0


def main() -> None:
    args = parse_args()
    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
