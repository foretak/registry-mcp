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

### D-015 — The United Kingdom is `GB`, strictly. No `UK` alias.
Date: 2026-09-04
Decision: `registries/gb/`, `country = "GB"`. `get_registry("UK")` raises `unsupported_country` like any other unknown code, and the REST path `/v1/UK/company/{id}` is a 404. No alias table is added to `core/registry.py`, and none is added at the API layer either.

Considered and declined, deliberately, because the argument for an alias is real: `UK` is what a human writes, it is the internet ccTLD, and an LLM composing a call from a user's "look up this UK supplier" will reach for it. Three things decide it the other way.

(a) **`core/registry.py` has one rule and it is ISO-3166-1 alpha-2** — `register()` enforces `len == 2 and isalpha()`, `CountryInfo.country` and every model's `country` field are documented as alpha-2, and `D-008` says nothing may hard-code a country code. An alias table is a country-specific exception living in `core/`, which is exactly what D-001 forbids. There is no country-neutral version of it: the next request is `EN`, then `UK` meaning Ukraine to somebody, then `GB` vs `GBR`.

(b) **The error is already the fix.** `get_registry` raises `unsupported_country` with a hint that lists the supported codes and names `list_countries` / `GET /v1/countries` (D-007). An agent that tries `UK` is told, in the same response, that `GB` exists. That is one wasted call, once, and the agent learns. An alias would save that call and cost us a permanent ambiguity in the contract.

(c) **The discovery surfaces are where this belongs.** `KEYWORDS.md` §GB, the tool docstrings and `llms-full.txt` (T15c) all say "United Kingdom (GB)" and "UK" in prose, so the retrieval path an agent actually uses to *find* the tool is not narrowed by the strictness of the *identifier*. Synonyms are a documentation problem, not a routing problem.

If telemetry after launch shows `UK` attempts are common and are not self-correcting from the hint, revisit — but revisit it as a general alias mechanism in `core/`, with evidence, not as a one-country special case.
Reason: a country code that means two things is a contract that means nothing. The cost of strictness is one recoverable error with a hint that names the right answer; the cost of the alias is a permanent country-specific branch in the module D-001 exists to keep country-free.
Applies to tasks: T15a, T15b, T15c

### D-016 — UK deadline policy: the register's own dates are authoritative; we compute only what is sourced; nothing rolls forward
Date: 2026-09-04
Decision: `registries/gb/rules.py` emits exactly two deadline kinds, `annual_accounts` and `confirmation_statement`, under three rules.

**(a) Published beats computed.** Unlike Brønnøysundregistrene, Companies House publishes the dates itself — `accounts.next_accounts.due_on` and `confirmation_statement.next_due`. Those are taken verbatim whenever present, and a computation is used only when the register is silent. This inverts the Norwegian design on purpose: CH's figures already account for accounting-reference-date changes, shortened and extended periods, and administrative extensions that we cannot see, and they are what the filing system will actually judge lateness against. `applies_because` says which of the two it was, in every deadline, so an agent can tell a quoted fact from a derived one.

**(b) Compute only from a sourced rule applied to a published input.** The fallback rungs are: accounts = `next_accounts.period_end_on` + 9 months (private) or 6 months (public), per Companies Act 2006 s.442 as stated in GOV.UK's *Life of a company — Part 1 Accounts*; confirmation statement = `next_made_up_to` + 14 days, per GOV.UK's confirmation statement guidance. Both were verified against live payloads on 2026-09-04 — five independent proofs each, across `ltd`, `plc`, `llp` and `private-limited-guarant-nsc`, in two jurisdictions (`UK_SPEC.md` §1.5). A legal form outside the confirmed private/public buckets gets no computed date at all, only the register's own, and an unclassified `type` gets nothing whatever (D-009(a) applied to Britain).

Three things are therefore **documented but not computed**, and this is the part that matters: **first accounts after incorporation** (21 months private / 18 months public from incorporation, or 3 months from the accounting reference date, whichever is longer — sourced, but picking the right *year* for a first ARD from a bare `{day, month}` is ambiguous once a company has shortened or extended its first period, and CH publishes `due_on` for a company from the day it is incorporated, so the ladder's first rung already answers it correctly); and both **corporation tax** dates. The CT rules are sourced — 12 months after the accounting period ends for the CT600, 9 months and a day for payment — but three inputs are not: HMRC's accounting period is not the Companies House accounting reference period and is not published; whether the entity is within the charge to corporation tax at all depends on the legal form, and an LLP is tax-transparent and files no CT600; and the 9-months-and-a-day payment date does not apply to companies in the quarterly-instalment regime, which turns on a profit figure Companies House does not publish. Corporation tax is HMRC's, not Companies House's. `rules_markdown()` states all three rules in prose, with sources, so an agent that knows the missing input can apply them; the module emits no date.

**(c) No roll-forward, anywhere.** GOV.UK: "If your filing deadline falls on a Sunday or a bank holiday, it is still a legal requirement to file your accounts by that date." So every GB `Deadline` has `statutory_date == due_date` and `rolled_forward is False`, `registries/gb/` ships **no** holiday table, and `core/rules/common.py::roll_forward` is never called — not called with an empty holiday set, not called at all. `core/` needs no change for this: `roll_forward` was already a helper a country may use, not a step in a pipeline every country runs through.

Two consequences worth naming. Deadlines are emitted **only** when `status is ACTIVE`, which is stricter than Norway, where `UNDER_LIQUIDATION` keeps its list — CH's `company_status` does not distinguish voluntary from compulsory liquidation, so the distinction Norway's rule depends on is not available to us, and D-009's "never guess a duty" decides it. And `days_until` is negative for a real, common case: CH leaves an overdue due date in the past rather than rolling it to the next cycle (confirmed live on DELOITTE LLP), so the upstream `overdue` flag is corroboration and `days_until < 0` is the answer.
Reason: the differentiator is deadlines, and the way to keep that differentiator trustworthy across countries is a rule about *provenance* rather than a rule about arithmetic. "Quote the register where it speaks, compute only from a cited statute applied to a published input, and say which you did" generalises to country three; "nine months after the ARD" does not.
Applies to tasks: T15a, T15b, T15c

### D-017 — A registry declares its credential: `requires_api_key` / `api_key_env` on `Registry`, surfaced by `country_info()`
Date: 2026-09-04
Decision: Companies House is the first upstream that needs a credential, and the discovery surface had no way to say so. `core/registry.py :: Registry` gains two class attributes and `core/models.py :: CountryInfo` gains the two matching fields, **both with defaults, so `registries/no/` and `registries/xx/` are untouched and every existing test still passes** (verified: 273 passed after the change, mypy and ruff clean).

```python
requires_api_key: ClassVar[bool] = False
api_key_env:      ClassVar[str]  = ""     # "" means none needed
```

`country_info()` emits `requires_api_key=self.requires_api_key` and `api_key_env=self.api_key_env or None` — the `or None` following the same precedent as `validate()`'s `id_scheme=self.id_scheme or None`, so the model field is `str | None` and D-004's "unknown is `None`, never `''`" holds on the wire while the class attribute stays a plain `str` like every other one.

**Declarative, never a health check.** The attributes say *this registry cannot work without a key*; they never say *this deployment has one*. A `configured: bool` computed from the environment was considered and declined: `country_info()` would then read `os.environ` at call time, making a discovery document depend on deployment state and on when it was called, and the question it answers ("can GB answer right now?") is already answered — correctly and with a next action — by the `upstream_error` and its hint (D-007). A module with `requires_api_key = True` must still raise that error when the variable is unset; the flag makes the constraint discoverable in advance, it does not replace the error.

**Never the key, only its name.** `api_key_env` is published by `GET /v1/countries` and by the MCP `list_countries` tool. It holds the variable's *name*. Nothing anywhere publishes, logs or puts a key value in a `RegistryError.details`; `UK_SPEC.md` test 104 asserts it.

Follow-ups this does not fix by itself, both for **T15c**, both cosmetic rather than functional (the model's defaults mean nothing breaks meanwhile):
- `src/registry_mcp/api/main.py:185 _COUNTRIES_EXAMPLE` is an OpenAPI example dict, not a validated model, so it now advertises fewer keys than `/v1/countries` returns. Add `"requires_api_key": false, "api_key_env": null` to the NO row and a GB row alongside it.
- `static/llms-full.txt`'s `/v1/countries` example needs the same two keys, and the sentence that says the MCP `list_countries` tool returns an identical document has to stay true.

The `Registry` ABC stays four abstract methods wide (D-008): these are class attributes with defaults, like `name` and `license`, so `registries/xx/` needs no edit and a third country inherits them for free.
Reason: `tasks/T15.md` set the rule that a `core/` edit forced by the second country is itself the finding. This is that finding, and it is the good kind: the thing missing from the interface was not country-specific, it was *credential*-specific, and Denmark's CVR (T16, application pending) will need exactly the same two attributes. The alternative — leaving it out — means the only way an agent can learn that a self-hosted deployment cannot answer for GB is to call it and read the error, which is the one thing D-007's hints exist to make unnecessary in advance.
Applies to tasks: T15a, T15b, T15c, T16

### D-018 — The register's own published dates travel on `CompanyReport.published_deadlines`; `Registry.deadlines` stays pure
Date: 2026-09-04
Decision: `core/models.py` gains a small model, `PublishedDeadline`, and `CompanyReport` gains one field, `published_deadlines: list[PublishedDeadline]`, defaulting to `[]`. A registry whose upstream publishes filing dates for the entity itself fills the list at **lookup** time; its `deadlines(report, today)` reads the list and merges — published wins, computation fills the gaps (D-016(a)) — and stays the pure function of `(report, today)` that `core/registry.py:25-26` promises. `registries/no/` and `registries/xx/` leave it empty and are not edited at all.

```python
class PublishedDeadline(_Base):
    kind: str                      # same slug as the matching Deadline.kind, e.g. "annual_accounts"
    due_date: date | None = None   # the register's own figure; None when it names a period but no date
    period_start: date | None = None
    period_end: date | None = None # what a statutory period actually runs from
    overdue: bool | None = None    # the register's flag; corroboration only, our days_until decides
    source: str | None = None      # opaque upstream provenance, e.g. "accounts.next_accounts.due_on"
```

**The finding this closes, and how it surfaced.** T15b reported, correctly and in writing before review, that D-016(a) cannot be honoured over `(report, today)` alone: Companies House's `accounts.next_accounts.due_on` and `confirmation_statement.next_due` are not fields on `CompanyReport`, so `deadlines()` had nowhere to read them from. It worked around it without touching `core/` — `registries/gb/client.py` cached the raw upstream JSON and `deadlines()` recovered it with a synchronous SQLite read (`client.raw_for`). That is I/O inside a method whose contract says "no I/O", and it produces a **silently wrong answer** whenever the cache is cold: with `REGISTRY_MCP_CACHE_DISABLED=1`, `deadline_report` for an active TESCO PLC returns zero deadlines *and* zero notes, which `core/models.py`'s own `DeadlineReport.deadlines` docstring identifies as indistinguishable from a bug. `REGISTRY_MCP_CACHE_DISABLED` is a supported configuration, and D-006 further requires that a *failed* cache write be logged and ignored — so a read-only cache directory, which T10 fault-tested precisely to prove it degrades gracefully, would instead have degraded into wrong deadlines.

**Why this shape.** Three alternatives were considered and declined.

(a) *Widen the ABC to `deadlines(report, today, raw)`.* Rejected: it makes every country carry a country-shaped parameter, and it pushes the upstream payload — the one thing `core/` must never understand — through the interface D-001 exists to keep country-free.

(b) *`filing_due_dates: dict[str, date]`.* Simpler, and it was the first instinct, but it carries only the top rung of the ladder. Britain's third rung computes from `next_accounts.period_end_on` when no date is published (`ch_FC032315.json` is exactly that payload, live), the `Deadline` needs `period_start`/`period_end`/`period_label`, and §5.4.1's overdue-disagreement note needs the register's own flag. A `dict[str, date]` would have forced the raw payload back through the cache for all three.

(c) *Put a full `list[Deadline]` on the report.* Rejected because `Deadline.days_until` is defined against a caller-supplied `today` that does not exist at lookup time, and `applies_because` is prose the *rules* layer owns. Publishing a half-filled `Deadline` would make the two shapes mean different things in different places.

What is left is the honest distinction: **`PublishedDeadline` is theirs, `Deadline` is ours.** One is quoted, one is computed, and `applies_because` already exists to say which. `core/` interprets neither `kind` nor `source` — it only carries them across the lookup → deadlines boundary.

**Country-neutral, and already needed twice.** Most registers state a statute and let you do the arithmetic; some do the arithmetic and publish the answer. Britain is the second country and the first of the second kind, which is why it did not exist before. Denmark's CVR (T16) publishes `nyesteRegnskabsperiode` and Companies House-style filing dates; any register that runs its own filing system will too. And the field is honest even for Norway: an empty list means "Brønnøysundregistrene publishes no dates", which is true and worth an agent knowing.

**Wire effect.** `CompanyReport` grows one key, present and `[]` on every country per D-004's "always present, never omitted". `PublishedDeadline` is exported from `core.models`. Verified after the change: 391 passed / 5 deselected, `mypy` clean on 52 files, `ruff` clean, and the GB live tests still green.

Follow-ups this does not fix by itself:
- **T15b**: remove the `raw_for` workaround and fill `published_deadlines` in `registries/gb/mapping.py` — the exact edit list is in `REVIEW.md` §T15e "Fix list", item B1. `registries/gb/client.py` keeps caching raw JSON (that part is fine, and better than caching the mapped report); what it must stop doing is using the cache as a *transport*.
- **T15c**: `static/llms-full.txt`'s `CompanyReport` field list (the "Accounts" bullet, ~line 447) and the worked example (~line 165) need `published_deadlines`, alongside the two `/v1/countries` keys D-017 already left open.
Reason: `tasks/T15.md` made a `core/` edit forced by the second country the finding itself, and the guide's Step 12 says an abstraction that is wrong should be fixed before country three, not worked around twice. This is that fix, and the missing concept was not "Companies House" — it was *provenance*: the interface could express a date we computed but not a date we were told, which is precisely the distinction D-016 says makes the deadline feature trustworthy.
Applies to tasks: T15b, T15c, T16

### D-019 — An upstream 429 is `rate_limited` everywhere; Norway is aligned to Britain, not the reverse
Date: 2026-09-04
Decision: every registry module maps an upstream `429 Too Many Requests` to `RegistryError(ErrorCode.RATE_LIMITED)`, which `core/models.py` already maps to HTTP 429. `registries/gb/client.py` does this; `registries/no/client.py:167-175` currently raises `ErrorCode.UPSTREAM_ERROR` (HTTP 502) and is the one that changes.

T15a spotted the divergence while writing `UK_SPEC.md` §6 and deliberately deferred it ("do not 'fix' Norway to match as part of T15b; record it for T15e"). Ruled here, in Britain's favour, for three reasons. The code exists and means exactly this — `ErrorCode.RATE_LIMITED` is in D-007's status table and `core/models.py:774` maps it to 429. The two codes tell an agent to do **different things**: `upstream_error`/502 means the register is broken and the call may never succeed, `rate_limited`/429 means the call will succeed shortly, and only one of those is true of a 429. And `/v1/stats` counts error codes, so mislabelling throttling as an upstream fault hides the single operational signal that most warrants an alert.

Scope is deliberately narrow: this is about an error *code*, not about retry policy. Neither country retries a 429, and neither should — retrying a rate limit is how a shared key gets blocked. Our own inbound limiter (`api/ratelimit.py:90`) already emits `RATE_LIMITED`, so after this change the code means one thing on both sides of the server.

No existing test asserts Norway's current behaviour, so the change is three lines in `registries/no/client.py` (the code, and a hint that names the wait) plus the `429` row of `NORBIZ_SPEC.md:278`. Owner: the T15b implementer, as a follow-up to T15e; non-blocking for the GB module.
Reason: two countries answering the same upstream condition with two different error codes is a contract that means nothing to an agent, and the whole point of `core/models.py`'s `ErrorCode` enum is that the agent never has to know which country it is talking to. The second country is the moment such a divergence is cheapest to close — waiting for the third makes it a migration.
Applies to tasks: T15b, T15e, T16

### D-020 — `SearchResult.hits` is sorted by confidence descending, stably, in `core/models.py` — because the contract already says so
Date: 2026-09-04
Decision: `core/models.py :: SearchResult` gains a validator that sorts `hits` by `confidence` **descending, stably**, so the register's own relevance order survives as the tie-break within each confidence tier. No country module sorts; no surface sorts.

The decision is smaller than it looks, because the field is already documented as sorted: `SearchResult.hits` is described as **"Best matches, best first."** (`core/models.py:788`). So this is not a new contract — it is `registries/gb/` failing the existing one, exposed by T15c's real output for `search_company("tesco", country="GB")`: confidences `0.8, 0.4, 0.8`, with a 0.4 hit sitting above a 0.8 hit. Norway passes today only by luck, because brreg's relevance order happens to agree with our scoring; the moment it does not, NO has the same bug and no test would catch it either.

**Why the model and not the country module, or a `Registry.search` wrapper.** D-004's guarantee is that one shape means one thing on both surfaces, and an ordering promise is part of a shape when the field description makes a promise about order. Pushing the sort into each country makes it a rule every future country must remember and no test enforces — which is exactly how it was got wrong here on the first try. There is no concrete `Registry.search` wrapper to hang it on (unlike `validate`/`deadline_report`, D-010): `search` is abstract and returns the model directly, so the model *is* the only country-neutral chokepoint. Putting it in a validator has a second payoff the wrapper would not have had: it also fires on `SearchResult.model_validate(...)` when a search is served from cache (`registries/gb/client.py:373`), so a cached result and a fresh one cannot disagree about order.

**Stable, and descending only.** `sorted(hits, key=lambda h: -h.confidence)` is stable in Python, so hits that score identically stay in the order the register returned them. That matters: D-005's anchors are coarse (0.95/0.8/0.6/0.4) and will routinely tie three or four hits, and within a tie the register's relevance ranking is real information we have no better substitute for. We are re-ranking by our own confidence, not discarding theirs.

Declined: "the contract says register relevance order, read `confidence`". It would require rewriting the `hits` description to promise less, it makes every agent that renders the first hit render a worse one, and it optimises for the caller who reads all ten results over the caller who reads one — which is the opposite of how a tool-calling agent behaves.

Owner: **Opus A (architect)** — `core/models.py` is the architect's file by the D-017/D-018 precedent. Queued to land alongside D-018's `published_deadlines` so the two `core/` edits reach T15b as one re-run. `registries/gb/` and `registries/no/` need no edit; T15b adds one assertion to `UK_SPEC.md` test 90 (hits are non-increasing in `confidence`) and the same to `tests/test_client_no.py`, so the promise is enforced for every country from now on.
Reason: a field whose description promises an order and whose producer does not deliver it is a contract that lies, and the cheapest place to make it true for every country at once — including on the cache path — is the model that carries the promise.
Applies to tasks: T15b, T15c, T16

### D-021 — An unrecognised identifier prefix stays `valid: true` and says so in `reason`, never in `hint`
Date: 2026-09-04
Decision: `validate_company_id("ZZ12", "GB")` keeps returning `valid: true, normalized: "ZZ000012"`, and gains one sentence in **`reason`**: that `ZZ` is not in the Companies House prefix list this module knows as of 2026-09, and that only `lookup_company` can confirm whether the number exists. The coordinator's middle path, with one correction: the signal goes in `reason`, **not** `hint`.

The correction is not cosmetic. D-013 already ruled that `hint` stays `None` when `valid is True` — moving a caveat into `hint` on a success would contradict D-010, and `tests/test_api.py:128` and `tests/test_interface.py:214` assert the null. `reason` is the field D-010 defines as "why it is valid, or what failed", it is already populated on success, and it already carries a caveat of exactly this species ("a valid identifier does not mean the entity exists"). Appending a second, more specific caveat to it is the change that fits the contract we have.

**The hook, because `core/` cannot know about prefixes.** `Registry` gains one optional method beside `format_id`, the existing precedent for "a country may refine this, and the default is silence":

```python
def id_caveat(self, id: str) -> str | None:
    """A caveat about an already-normalised, well-formed identifier. Default: none."""
    return None
```

`Registry.validate` (`core/registry.py:234-247`) appends its return value to the success `reason` when it is not `None`. `registries/no/` and `registries/xx/` inherit `None` and are untouched; `registries/gb/rules.py` implements it against the §5.1.2 prefix table.

**This does not make the prefix table a gate, and D-015 is unchanged.** The whole point of D-015 was that rejecting an unknown prefix turns a real company into an `invalid_id` the day Companies House adds one — `OE` arrived with ECTEA 2022 and would have been rejected by any validator written in 2021. `valid` stays `true`, `normalized` stays populated, `UK_SPEC.md` test 25 (`"QQ000001"` is accepted) still passes unchanged, and the *only* thing that changes is that we say out loud what we know and what we do not. That is the honest reading of D-009 applied to an identifier: we are not guessing that `ZZ12` is invalid, we are stating that we cannot vouch for the prefix and naming the call that can. The sentence must carry the as-of date, so a reader can tell a stale table from a bad number.

The requesting use case — a spreadsheet of supplier numbers run through `validate_company_id` before a bulk lookup — is served exactly by this: the row is not rejected, the operator gets a column they can filter on, and the fix for a false signal is one lookup rather than a support ticket about a real company we called invalid.

Owner: **Opus A (architect)** for the `Registry.id_caveat` hook and the two-line change in `Registry.validate`; **T15b** for `registries/gb/rules.py`'s prefix set and sentence, a `UK_SPEC.md` §14 test asserting `valid is True` **and** the caveat present for `"ZZ12"`, and one asserting a known prefix (`"SC090312"`) gets **no** caveat. `hint` must still be `None` in both cases.
Reason: the failure mode worth designing against is not "an agent trusted a well-formed number", it is "we told an agent a real company was invalid because our table was a year old" — so the answer is to widen what we say, not to narrow what we accept, and to say it in the field the contract has already reserved for saying it.
Applies to tasks: T15b, T15c, T16

### D-022 — A deadline cites only the provision that contains the rule, and roll-forward is a per-deadline fact, not a country setting
Date: 2026-09-05
Decision: raised by the R01 review of live Norwegian output (`REVIEW.md` R01, §1). Two rules, one principle.

**(a) Cite the provision that contains the rule.** A `Deadline` may name a statute in `applies_because` only where that named provision actually states the thing being claimed. `NORBIZ_SPEC.md:212` sourced Norway's weekend roll-forward to "forvaltningsloven § 30 / skattebetalingsloven"; forvaltningsloven § 30 is about when an appeal counts as lodged in time, forvaltningsloven contains no weekend rule at all, and skattebetalingsloven governs payment rather than filing. The correct basis for the tax deadlines is two steps and must be given as two: **skatteforvaltningsloven § 5-5** ("Fristen regnes i overensstemmelse med domstolloven §§ 148 og 149") reaching **domstolloven § 149** ("Ender en frist paa en lørdag, helgedag eller dag som etter lovgivningen er likestilt med helgedag forlenges fristen til den nærmest følgende virkedag"), with § 148's last sentence ("Avslutningen av en frist kan ogsaa betegnes ved en bestemt kalenderdag") making a fixed calendar date a *frist* for that purpose. Where a provision states the rule itself — a-opplysningsforskriften § 2-1, sixth paragraph — cite that one and stop.

**(b) Roll-forward is decided per deadline, from its own source.** `core/rules/common.py::roll_forward` is a helper a rule may call, never a step every deadline passes through. In `registries/no/rules.py` it stays for `tax_return`, `shareholder_register_statement`, `vat_return` (all reached by § 5-5 → § 149) and `payroll_report` (a-opplysningsforskriften § 2-1). It is **removed** from `annual_accounts` and `general_meeting`, which have no such chain: regnskapsloven and aksjeloven neither contain the rule nor reference domstolloven §§ 148–149, and forvaltningsloven — the only general act that would otherwise reach Regnskapsregisteret — has none either. Both get `statutory_date == due_date` and `rolled_forward=False`, and both say in `applies_because` that the date does not move.

**(c) Where the source is silent, the date does not move.** Not "roll it, it is probably fine". This is D-009's "never guess a duty" applied to arithmetic, and it is the rule that decides the two cases in (b) — a published Brønnøysundregistrene practice would reopen them, an inference from what other agencies do would not.

Reason: rolling forward is not a neutral convenience, it can make the answer **later than lawful**, and on `annual_accounts` it crosses the exact line the date exists to stay behind. Regnskapsloven § 8-3(1) charges a late fee unless the accounts are "avsendt før 1. august"; 31 July 2027, 2032 and 2033 fall on a weekend, so the shipped module returns 2 August, 2 August and 1 August — a date on which the fee is already running — and `content/02-deadlines/devto.md:53` publishes that as the worked answer. `general_meeting` is worse-founded still: aksjeloven § 5-5(1)'s six months is an outer limit, a general meeting may be held on a Saturday, and `authority` is literally "Company shareholders (no external filing)" — there is no closed office to roll off.

This also makes one rule out of two. D-016(c) settled Britain with "no roll-forward, anywhere", sourced to GOV.UK; Norway rolls four of six deadlines, sourced to § 5-5 → § 149. Those look like opposite country policies and are in fact the same policy — *the source decides, per deadline, and the output says which source* — which is what generalises to country three. Country modules therefore do not declare a roll-forward posture; individual rules cite one or say they have none.

Owner: **Sonnet implementer** for `registries/no/rules.py` (`_annual_accounts`, `_general_meeting`, the four `applies_because` strings, `rules_markdown()`) and `tests/test_rules_no.py` (test 58 rewritten; 58b, 63b, 63c added) — the fix list is `REVIEW.md` R01 F1–F4, F7. `NORBIZ_SPEC.md` §5.3, §5.4 and §13.F were corrected by the architect in the R01 review and are the spec of record. **Opus B** owns F9: `content/02-deadlines/{devto,reddit}.md`, `static/llms-full.txt:481` and `static/well-known/mcp/server-card.json:57` all assert the roll-forward as universal and must be narrowed once F1 lands. No `core/` change: `roll_forward` was already a helper, not a pipeline stage.
Applies to tasks: R01 follow-up, T02, T15c, and every future country module

### D-023 — The calendar-year assumption is stated where it bites, and the accounting period is a fact we can fetch
Date: 2026-09-05
Decision: raised by the R01 review (`REVIEW.md` R01, §3). Three changes to how the deviating-accounting-year caveat is worded and placed, and one boundary for later.

**(a) Say that it selects a different rule, not a different date.** Regnskapsloven § 8-3(1) second sentence: "Er regnskapsåret avsluttet på en dato fra 1. januar til 30. juni, er fristen etter første punktum **1. februar**." For those entities our 31 July is not a near miss — it is roughly six months after the fee started. `mapping.py`'s note must say the deadline can be one we do not compute at all, and must add § 8-3(1)'s last sentence: the Ministry may postpone by up to one month by regulation, which no register publishes.

**(b) Attach it only to the deadlines whose date actually moves.** `annual_accounts` and `general_meeting` key off the financial year end and keep the caveat. `tax_return` and `shareholder_register_statement` do **not**: skatteforvaltningsforskriften § 8-2-3(1) and § 7-7-4(1) both run from "året etter skattleggingsperioden", and skatteloven § 14-1(1) makes the inntektsperiode the calendar year — § 14-1(3) handles a deviating accounting year by choosing *which* year's figures go into the return, not by moving the frist. The suffix comes off those two. A caveat attached to everything is a caveat an agent learns to skip.

**(c) Enhetsregisteret does not publish the accounting period; Brønnøysundregistrene does.** The note's last clause ("Enhetsregisteret does not publish which companies those are") is true and must stay scoped to Enhetsregisteret, because `GET https://data.brreg.no/regnskapsregisteret/regnskap/{orgnr}` returns `regnskapsperiode: {fraDato, tilDato}` for every filed annual account, open, free and with no API key — verified live 2026-09-05 on 923609016 (2025-01-01/2025-12-31) and 982463718 (2024-01-01/2024-12-31). `sisteInnsendteAarsregnskap` (→ `last_annual_accounts_year`) is a bare year and cannot substitute.

**(d) Not implemented now, and the reason is recorded so it is a decision rather than a gap.** Reading Regnskapsregisteret to pick § 8-3(1)'s branch is D-018's shape — published beats computed — applied to Norway, and it would replace an assumption with a fact for any entity that has filed once. It is out of scope while feature work is frozen, it adds a second upstream to the Norwegian lookup path with its own cache and failure mode, and the field's *variance* is unverified (presence and shape confirmed on two entities; no live example of a non-calendar period was found). When it is picked up, it goes on `CompanyReport` at lookup time and `deadlines(report, today)` stays the pure function of `(report, today)` that D-018 protects — not a synchronous fetch inside the rule, which is the mistake D-018 exists to prevent.

Reason: the caveat was written to be honest about one thing (we cannot see the accounting year) and ended up implying two things that are not true — that the consequence is a shifted date rather than a different rule, and that nobody publishes the input. The first understates the harm to the agent reading it; the second would let us treat a gap we can close as a boundary we cannot.

Owner: **Sonnet implementer** for `registries/no/mapping.py` (`_CALENDAR_YEAR_ASSUMPTION_NOTE`) and `registries/no/rules.py` (`_CALENDAR_YEAR_ASSUMPTION` suffix removed from `_tax_return` and `_shareholder_register_statement`) — `REVIEW.md` R01 F3, F8. Any test asserting the note text verbatim must be updated with it. (d) is unassigned and stays that way until the freeze lifts.
Applies to tasks: R01 follow-up, T02, T03
