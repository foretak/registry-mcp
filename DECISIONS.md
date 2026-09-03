# DECISIONS

Append-only. The architect (Opus A) records every interface or schema decision here with a date and a one-line reason. Implementers read this file before starting any task.

Format: `### D-NNN — <title>` / `Date:` / `Decision:` / `Reason:` / `Applies to tasks:`

---

### D-001 — Product split: `registry-mcp` umbrella, `brreg-mcp` first module
Date: 2026-09-03
Decision: Country-neutral code lives in `core/`; Norwegian code lives in `registries/no/`. A second country must be addable in one folder under `registries/` without editing `core/` or `api/`.
Reason: Product framing from the multi-agent build guide; this is the constraint every later decision serves.
Applies to tasks: all

### D-002 — Technical name vs brand name
Date: 2026-09-03
Decision: Package/repo/tool names are descriptive and keyword-bearing (`registry-mcp`, `brreg-mcp`, `lookup_company`). Brand name (`Foretak` or fallback) is used only for domain and company, never in code identifiers.
Reason: Agents discover tools by keyword match; a brand name is invisible to them (build plan §0).
Applies to tasks: T05, T07, T11, T12

### D-003 — src layout: `src/registry_mcp/{core,registries,api,mcp}/`
Date: 2026-09-03
Decision: All Python moves under `src/registry_mcp/`. The skeleton's top-level `core/`, `registries/`, `api/`, `mcp/` were moved there (git mv, history preserved), `registries/xx/` added. Packaging is `uv` + hatchling, Python ≥3.12, pydantic v2, mypy strict, ruff.
**Path note for every task file: wherever `tasks/T02.md`–`tasks/T13.md` say `core/…`, `registries/…`, `api/…` or `mcp/…`, read `src/registry_mcp/core/…`, `src/registry_mcp/registries/…`, `src/registry_mcp/api/…`, `src/registry_mcp/mcp/…`. `tests/`, `content/`, `legal/` and the root docs are unchanged.** The task files themselves are not edited; this entry is the single search-replace rule.
Reason: a top-level `mcp/` package shadows the `mcp` PyPI package that FastMCP imports, so `import mcp` inside our own MCP server would resolve to us and fail. A src layout also stops tests from accidentally importing the source tree instead of the installed package.
Applies to tasks: all

### D-004 — Response schema: one contract, both surfaces
Date: 2026-09-03
Decision: `core/models.py` is the whole contract — `CompanyReport`, `SearchHit`, `SearchResult`, `Deadline`, `Address`, `IndustryCode`, plus the `CompanyStatus`, `DeadlineRecurrence`, `ErrorCode` and `Surface` enums. Rules: snake_case English field names (no Norwegian in any field or model name — only in *values* such as `legal_form_local`); dates are `date` serialised ISO-8601, timestamps timezone-aware UTC `datetime`; unknown is `None`, never `""` or `0`; every returned model carries `country` (ISO-3166-1 alpha-2, upper-cased by a validator) and `registry`; all models are `extra="forbid"`. REST and MCP must emit `model_dump(mode="json")` of these models unchanged — no surface-specific reshaping, no extra keys. A registry module that needs a new field asks Opus A; it does not widen the model itself.
Reason: the guide's integration check is "schema identical across REST and MCP"; the only way to guarantee that is for neither surface to own a shape. `extra="forbid"` turns a mapping typo into a construction error instead of a silently missing field.
Applies to tasks: T02, T03, T06, T07, T10

### D-005 — Confidence is a 0.0–1.0 float with fixed anchors
Date: 2026-09-03
Decision: `confidence: float` in [0.0, 1.0] on `CompanyReport` and `SearchHit`, always paired with `confidence_basis: str` giving the reason in English. Anchors: 1.0 exact identifier lookup; 0.95 search hit matching the query exactly (case-insensitive); 0.8 name starts with the query; 0.6 name contains every query token; 0.4 any other hit the registry returned. Registry modules use these anchors, not arbitrary values in between.
Reason: a float lets a caller threshold ("only act above 0.9") which an enum cannot, while fixed anchors keep it from becoming an unfalsifiable vibe. `confidence_basis` is what an agent quotes to a user; the number alone would be uninterpretable.
Applies to tasks: T02, T03, T06, T07

### D-006 — Cache: SQLite, 24 h TTL, honest `cached` and `fetched_at`
Date: 2026-09-03
Decision: One SQLite file at `REGISTRY_MCP_CACHE_PATH` (default `./data/cache.sqlite3`), key `"{COUNTRY}:{registry}:{kind}:{normalised-id-or-query}"`. TTL 24 h for successful lookups and searches, 1 h for negative (`not_found`) results. A cache hit sets `cached=True` and preserves the **original** `fetched_at` rather than the read time, so staleness is visible. `REGISTRY_MCP_CACHE_TTL_SECONDS` overrides the TTL; `REGISTRY_MCP_CACHE_DISABLED=1` bypasses it. Expired rows are deleted lazily on read. Any cache failure is logged and ignored — the cache is never allowed to raise a `RegistryError`.
Reason: brreg data changes daily at most, and 24 h keeps us a polite client of a free public API. Negative results get a short TTL because a newly registered company must become visible fast. Preserving `fetched_at` is what makes `cached` useful rather than decorative.
Applies to tasks: T03, T06, T08

### D-007 — Error format: `{"error": {code, message, hint}}`, raised not returned
Date: 2026-09-03
Decision: Every expected failure is a raised `RegistryError` carrying `code` (the `ErrorCode` enum — stable strings, never renamed), `message`, a **mandatory non-empty** `hint`, plus optional `country`, `registry`, `details`. Each surface catches it and serialises `RegistryError.to_dict()`, so REST and MCP emit byte-identical error documents. HTTP status comes from `RegistryError.HTTP_STATUS`: 400 invalid_id/bad_request, 404 not_found/unsupported_country, 429 rate_limited, 501 not_implemented, 502 upstream_error, 504 upstream_timeout, 500 internal_error. `hint` must name the next call the agent can make — "invalid input" is not a hint.
Reason: an agent's next action is the product. Raising rather than returning keeps every code path honest (you cannot forget to check a return value), and one serialiser is the only way the two surfaces stay identical as they drift.
Applies to tasks: T02, T03, T06, T07, T08

### D-008 — A second country is one folder plus one import line
Date: 2026-09-03
Decision: A country is a subclass of `core/registry.py :: Registry` — class attributes (`country`, `registry`, `name`, `id_scheme`, `id_example`, `id_description`, `source_url`, `license`, `is_stub`) and four methods: `validate_id(id)` and `deadlines(report, today)` sync and pure, `lookup(id)` and `search(name, limit)` async. The module calls `register(Instance())` at import time; `registries/__init__.py` imports it. That import line is the only shared file a new country touches, and it is outside `core/`. `get_registry(cc)`, `list_countries()` and `list_registries()` are the only lookups; nothing may hard-code a country code. `registries/xx/` is the working template and its docstring is the six-step recipe. Stub registries set `is_stub = True` and are **hidden** from `list_countries()` and `get_registry()` by default — so `list_countries()` returns `["NO"]`, and `list_countries(include_stubs=True)` (or `REGISTRY_MCP_INCLUDE_STUBS=1`) returns `["NO", "XX"]`.
Reason: the guide's two-week-per-country target only holds if adding a country is mechanical. Hiding stubs by default keeps `/v1/countries` from advertising a country that answers `not_implemented`, while the flag keeps the abstraction testable — which is the point of shipping `xx/` at all.
Applies to tasks: T02, T03, T05, T06, T07, T10, T15

### D-009 — An unclassified legal form gets no deadlines; `tax_return` needs an explicit form list
Date: 2026-09-03
Decision: Raised by the T02 review (`REVIEW.md` T02 B1/B2), where `NORBIZ_SPEC.md` §5.4 ("`tax_return` applies to all forms except sub-units") contradicts §7 ("Never guess a duty. An unknown code must never produce a deadline"). §7 wins. Concretely, in `registries/no/rules.py`:
(a) `deadlines_for` returns `[]` when `report.legal_form_code` is missing or is not a key of `ORG_FORMS`, and `deadline_exemption_note` returns a sentence saying the legal form is not classified so the mapping surfaces it in `CompanyReport.notes`. Sub-unit and status exemptions keep their current precedence over this one.
(b) `tax_return` is emitted only for codes in an explicit `_TAX_RETURN_FORMS = {"AS", "ASA", "ENK", "ANS", "DA", "NUF", "SA", "KS", "BA"}` — the private-sector business forms of §7's confirmed table. Public-sector and `VERIFY`-marked forms (`ORGL`, `KOMM`, `FYLK`, `STAT`, `SF`, `KF`, `IKS`, `STI`, `FLI`, `BRL`, `BBL`, `ESEK`, …) get no `tax_return` until someone verifies the duty against a source.
(c) `vat_return` and `payroll_report` keep their current triggers (`registrertIMvaregisteret`, `antallAnsatte > 0`). They follow from published facts rather than from a legal-form duty, so any *classified* form may still get them.
(d) Applying this, T02's implementer may edit the `tax_return` row of `NORBIZ_SPEC.md` §5.4 and the closing paragraph of §7 to match — the second and last exception to "do not touch the spec", alongside T03's field-name corrections. Spec tests 57–81 are unaffected (checked: 72 and 73 still hold for `ENK`).
Reason: the module currently tells an agent that Registerenheten i Brønnøysund (`ORGL`, our own second live fixture) owes a *Skattemelding for næringsdrivende*, and that a fantasy legal form owes one too. A wrong deadline is worse than a missing one: an omitted obligation makes an agent ask a human, an invented one makes it act. "Never guess a duty" has to bind the deadline engine, not only the duty columns.
Applies to tasks: T02, T06, T07
