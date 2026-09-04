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

### D-010 — `DeadlineReport` and `ValidationResult`: the deadlines and validate operations get models too
Date: 2026-09-03
Decision: `core/models.py` gains two models, so that all four operations — not just two — have one shape across both surfaces (this closes the D-004 gap the T02–T05 review found, where `static/llms-full.txt` documented MCP `company_deadlines` returning a bare `list[Deadline]` while REST returned an object, and where the `/validate` response had no model at all).

- **`DeadlineReport`** — `country`, `registry`, `company_id`, `company_name: str | None`, `today: date`, `deadlines: list[Deadline]`, `notes: list[str]`. Returned by REST `GET /v1/{country}/company/{id}/deadlines` and MCP `company_deadlines`, both as `model_dump(mode="json")`, unchanged. Never return a bare `list[Deadline]`: a list has nowhere to put `today` or `notes`, and an empty list with no note is indistinguishable from a bug.
- **`ValidationResult`** — `country`, `registry`, `id_scheme`, `input`, `valid: bool`, `normalized: str | None`, `formatted: str | None`, `reason: str | None`, `hint: str | None`. Returned by REST `GET /v1/{country}/validate/{id}` and MCP `validate_company_id`. An invalid identifier is **HTTP 200 with `valid: false`**, not a raised error — the deliberate exception to D-007, since this operation answers a question rather than failing at one. The `invalid_id` hint is carried on the model so the agent still learns its next call.

The `Registry` ABC is **unchanged**: a country still implements exactly `validate_id(id) -> str` (raises on invalid), `lookup`, `search`, and `deadlines(report, today) -> list[Deadline]`. The two documents are built by new **concrete** base-class methods — `Registry.deadline_report(report, today) -> DeadlineReport` and `Registry.validate(id) -> ValidationResult` — plus an optional `Registry.format_id(id) -> str | None` hook (default `None`; `BrregRegistry` overrides it with T03's `mapping.format_orgnr`, the same helper that fills `CompanyReport.id_formatted`). **Surfaces call `validate()` and `deadline_report()`; they never assemble either model themselves**, because two assemblers are two shapes waiting to drift apart. `Registry.validate` re-raises any non-`invalid_id` `RegistryError` unchanged.

`format_id` is the hook T06 asked for. `validate_id` keeps returning a plain `str` — a checksum routine should not have to know typography, and every existing caller (`client.lookup`, `BrregRegistry.validate_id`, spec tests 1–15) stays valid — so `formatted` is produced by `Registry.validate()` calling `format_id(normalized)`. **T06: delete `api/main.py::_best_effort_id_format` (`:160-172`, used at `:713`) and the local `ValidateResponse`/`DeadlinesResponse` models (`:210-236`); `api/` gets Norway's real convention from the registry instead of a digits-in-3s heuristic that a future country would not recognise.** Country modules with a local convention override `format_id`; the rest inherit `None`, and `formatted` is honestly absent rather than invented.

Likewise **the calendar-year assumption note belongs to the country module, not to a surface**: `api/main.py::get_deadlines` currently synthesises it at `:646-652`, which means T07 would have to synthesise the identical sentence to stay byte-identical. It must instead be on `CompanyReport.notes` (put there in `registries/no/`), from where `deadline_report` copies it into `DeadlineReport.notes` for both surfaces at once. Same rule for any future caveat: prose about a country is written once, in that country's module.

`DeadlineReport.notes` is copied verbatim from `CompanyReport.notes`, so `core` synthesises no prose and stays country-neutral (D-001): any caveat that explains an empty or surprising list must already be on the report, put there by the country module's mapping. T02: if the calendar-year assumption is wanted as a `notes` entry rather than only inside each `applies_because`, add it in `registries/no/`, not in `core/`.

T06, T07 and T11 must conform: T06/T07 return these two shapes on both surfaces, and T11 realigns `static/llms-full.txt` §3.4/§3.5/§4 to them — note that the current file says `normalised` where the model says `normalized`, and shows `list[Deadline]` for the MCP tool. Nothing in `registries/` changed except the three-line `format_id` override in `registries/no/__init__.py`.
Reason: D-004's promise is "one contract, both surfaces". Two of the five operations were exempt from it by accident, and they are exactly the two where the surfaces were already documented as diverging. Wrapping in the base class rather than widening the ABC means a country module needs no edit, the `xx/` template needs no edit, and a second country inherits the shapes for free (D-008).
Applies to tasks: T06, T07, T10, T11

### D-011 — `employees_reported` means "a figure is present", not "brreg set the flag"
Date: 2026-09-04
Decision: Raised by the T10 review (item (a), the T09→T10 carry-over, and independently by T12's content author reading real MCP output). brreg's `833285602` fixture carries `harRegistrertAntallAnsatte: true` with **no `antallAnsatte` key at all**, which the current mapper (`src/registry_mcp/registries/no/mapping.py:211-212`) turns into `employees=None, employees_reported=True` — a report that says "the registry holds a figure" and then does not give one. `core/models.py:505` defines the flag as "whether the registry holds an employee figure at all (distinguishes 0 from unknown)", so the pair as emitted is self-contradictory.

(a) **`employees` stays `None`. Do not synthesise `0`.** The inference "brreg omits the key when the count is zero" is plausible (an `ENK` sole proprietorship has no employees; the owner is not one) but rests on a single fixture and no upstream documentation. D-004's rule is "unknown is `None`, never `0`", and `NORBIZ_SPEC.md` §7's "never guess" binds data as well as duties: an invented `0` is a fact an agent will repeat to a user, and the T03 review praised exactly the opposite behaviour ("if verification fails, the item is dropped, not guessed").

(b) **`employees_reported` becomes derived rather than mirrored**: `employees_reported = harRegistrertAntallAnsatte and antallAnsatte is not None`. This makes `employees_reported is True ⟹ employees is not None` a real invariant an agent can branch on, which is the only reason the field exists. For `833285602` the pair becomes `employees=None, employees_reported=False` — "we have no number", which is the honest reading of what we received.

(c) The lost signal is preserved as prose, not dropped: when `harRegistrertAntallAnsatte` is true and `antallAnsatte` is absent, `registries/no/mapping.py` appends a `notes` entry — "Brønnøysundregistrene flagged an employee count for this entity but did not return the number; treat the employee count as unknown rather than zero." Per D-010, prose about a country is written once, in that country's module.

No deadline changes: `registries/no/rules.py:690` already gates `payroll_report` on `report.employees is not None and report.employees > 0`, so `None` and `0` behave identically there. `NORBIZ_SPEC.md` §2's `employees_reported` row and spec test 88 need the wording widened (88 stays true as written); a companion test for the `true`-flag-absent-count case belongs beside `tests/test_client_no.py:164`, which currently asserts the contradictory pair as if it were correct.
Reason: a field whose whole job is to distinguish "zero" from "unknown" must not have a third state that means both. Given a choice between inventing a number and admitting we do not have one, the product that tells an agent what to do next admits it.
Applies to tasks: T03

### D-012 — `CountryInfo` / `CountriesResponse`: the discovery operation gets models too
Date: 2026-09-04
Decision: Raised by the T10 review (item (c)) and flagged by T07 itself as "the one payload D-004 doesn't cover". `core/models.py` gains **`CountryInfo`** (the nine `Registry.describe()` values, `extra="forbid"`, `country` upper-cased by validator) and **`CountriesResponse`** (`countries: list[CountryInfo]`). `core/registry.py` gains the concrete builder **`Registry.country_info() -> CountryInfo`**; `Registry.describe()` is kept, unchanged in signature and output, but is now `dict(self.country_info().model_dump(mode="json"))` so there is one definition of the row rather than two. **Both already landed in this review, and nothing is broken by them** — `describe()` emits the same nine keys with the same values, so `api/` and `mcp/` work untouched.

The remaining edits are the surfaces adopting the model, and they are mechanical:
- **T06** — `src/registry_mcp/api/main.py:169-184`: delete the local `RegistryInfo` and `CountriesResponse`; import `CountriesResponse`/`CountryInfo` from `core.models`; `:498` becomes `rows = [r.country_info() for r in list_registries()]`. The `response_model=CountriesResponse` at `:481` and the `_COUNTRIES_EXAMPLE` at `:197` need no change.
- **T07** — `src/registry_mcp/mcp/server.py:289-291`: `return CountriesResponse(countries=[r.country_info() for r in list_registries()]).model_dump(mode="json")`, replacing `{"countries": [dict(r.describe()) for r in list_registries()]}`.

`CountriesResponse` is the one returned model that does not carry `country`/`registry` at the top level (D-004): it is a list *about* registries, so the pair lives on each row instead.
Reason: the two surfaces did not merely lack a shared model, they had a **latent divergence**. `api/main.py`'s private `RegistryInfo` is a plain `BaseModel`, so pydantic's default silently *drops* a key `describe()` grows, while `mcp/server.py` passes the raw dict through and *keeps* it. The first registry attribute anyone adds would have made `/v1/countries` and `list_countries` disagree by omission, with no test failing. `extra="forbid"` on one shared model turns that into a loud error on both surfaces at once.
Applies to tasks: T06, T07, T10, T11

### D-013 — `ValidationResult.reason` stays populated on success; the sentence must name a real call
Date: 2026-09-04
Decision: Raised by T12's content author: the success `reason` — "Well-formed organisasjonsnummer for NO. A valid identifier does not mean the entity exists — call lookup to find out." — reads oddly because `reason` sounds like a failure field, and the second sentence is a next-action that arguably belongs in `hint`.

**Considered and declined, with one correction.** `reason` keeps its D-010 meaning ("why it is valid, or what failed") and stays populated in both branches; `hint` stays `None` when `valid is True`. Moving the caveat into `hint` would make `hint` non-null on success, which contradicts D-010, breaks `tests/test_api.py:128` and `tests/test_interface.py:214`, and buys an agent nothing it cannot already read from `valid`. The caveat itself is worth keeping wherever it lives: treating a checksum pass as proof of existence is the single most likely mistake this operation invites.

The correction, **already applied** in `core/registry.py:224-229`: the sentence said "call lookup", and `lookup` is not a callable name on either surface. D-007's standard — a hint names a concrete next call — applies to this sentence too, so it now names `lookup_company` (MCP) and `GET /v1/{country}/company/{id}` (REST). Covered by `tests/test_interface.py::test_validate_success_reason_names_a_concrete_next_call`.

One genuine mismatch this turned up, for **T06**: `src/registry_mcp/api/main.py:334`'s `_VALIDATE_EXAMPLE` advertises `"reason": "Nine digits with a valid MOD11 check digit."`, a string the code has never emitted. `/openapi.json` is a crawled surface, so it must show the real sentence. `static/llms-full.txt:332` already had the real one and needs only the "call lookup" tail updated (**T11**).
Reason: a field's name should not be the reason to move its contents somewhere the contract says is empty. The real defect was that the sentence told an agent to call something that does not exist — which is the same defect D-007 exists to prevent, one field over.
Applies to tasks: T06, T07, T11

### D-014 — `Registry.aclose()`: the shutdown hook is part of the interface, not a `getattr` guess
Date: 2026-09-04
Decision: Raised by the T10 review (item (e)). `core/registry.py` gains a **concrete, default no-op** `async def aclose(self) -> None`. A country module that owns no resources implements nothing; one that keeps a shared client **must** override it. **Already landed in this review**; it breaks nothing, and `api/main.py::_close_registry_clients`'s existing `getattr(reg, "aclose", None)` probe now always finds a real method.

The ABC stays four abstract methods wide (D-008): `aclose` is concrete like `validate`/`deadline_report`/`format_id`/`country_info`, so `registries/xx/` and every future country need no edit to inherit it.

Two follow-ups this does not fix by itself:
- **T03** — `src/registry_mcp/registries/no/__init__.py` must override it: `async def aclose(self) -> None:` delegating to `registries/no/client.py::aclose()` (which already exists at `client.py:78-83` and is called by nothing on shutdown), matching the existing lazy-import delegation pattern of `validate_id`/`lookup`/`search`/`deadlines`/`format_id`. Verified 2026-09-04: after the FastAPI app's lifespan exits, `registries.no.client._client.is_closed` is still `False` — the `httpx.AsyncClient` is dropped, not closed.
- **T06** — `src/registry_mcp/api/main.py:405-410`: `await _close_registry_clients()` sits after the `async with _mcp_app.lifespan(_app)` block rather than in a `finally`, so a shutdown that raises skips cleanup entirely. Wrap the `yield` in `try/finally`.
Reason: `api/main.py:376-392` already documents, at length and correctly, that it is doing a "generic, best-effort probe rather than a real interface method" because the ABC gave it nothing to call. When a surface has to write a paragraph apologising for a `getattr`, the interface is missing a method.
Applies to tasks: T03, T06, T10
