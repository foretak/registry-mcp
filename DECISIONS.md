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

### D-024 — Batch lookup is an *argument* on `lookup_company`, not a sixth tool; partial failure is a row, not a raise
Date: 2026-09-05
Decision: raised by `research/07-product-improvements.md` backlog item 7 and `~/research/registry-mcp/07-product-improvements/13-coverage-gap-batch-bulk-change-feeds.md` §1, which observes that the product already sells a spreadsheet workflow it does not support (`validate_company_id`'s own docstring says "use it on user input **or a spreadsheet column** before spending a real `lookup_company` call"; `llms-full.txt` §4 says "read it before processing **a list of identifiers**"), and then makes the agent issue N sequential calls, each costing a full `CompanyReport` of context.

**First, a correction to the cross-reference.** There is no "five-tool contract" in D-002 — D-002 is about technical *names* versus brand names. The five-tool count lives in the build guide (Step 5), in `README.md` ("The five tools and their response shapes are frozen"), and in `research/AGENT_PRIMER.md` §1; what `DECISIONS.md` actually rules is *one shape per operation* (D-004), extended to deadlines/validate (D-010) and discovery (D-012). D-024 therefore **ratifies the count here** so later decisions have something to cite: **`registry-mcp` exposes five MCP tools. Adding a sixth requires an explicit amendment of this entry, in this file, with the tool-selection cost argued rather than assumed.** D-028 and D-029 both invoke that rule and both stay at five.

**(a) The shape: one tool, a widened argument.** `lookup_company(company_id: str | list[str], country: str = "NO")`.

* A **`str`** returns `CompanyReport`, **byte-identical to today's output**. Non-negotiable and directly testable: the existing parity tests must pass unchanged.
* A **`list[str]`** returns a new `BatchLookupResult`, always — including a one-element list. The discriminator is the *input type*, which the caller chose and therefore already knows.

*Declined: a sixth tool `lookup_companies`.* It is the cleaner schema story and the worse product. Tool-selection accuracy degrades past ~30–50 loaded tools and Cursor's ceiling is about forty, so registry-mcp's five is a quantified structural advantage (`research/07-product-improvements.md` §3). Two tools whose names differ by one letter and whose descriptions differ by "one" versus "several" is the worst possible case for retrieval: the failure mode is the agent calling the *wrong tool*, which is strictly worse than the agent parsing a shape it predicted. The same reasoning decides D-028.

*Declined: mixed-country batches* (`[{id, country}]` items). `country` stays a single argument. The REST route is `/v1/{country}/…` and D-008 routes by country code; per-item routing would put a country dispatcher inside a request handler and fork the two surfaces' shapes. A caller with three jurisdictions makes three calls, and the `hint` says so.

**(b) The parameter is renamed to `company_id`, with `id` kept as an accepted alias.** `mcp/server.py:268` currently declares `id`, which shadows a builtin, reads ambiguously next to four other tools, and is backlog item 4's outstanding half. Widening the type is already a signature change, so both land in one release. Mechanism: pydantic `validation_alias=AliasChoices("company_id", "id")` on the `Annotated[...] Field`, so the *published* input schema names `company_id` exactly once while a client still sending `id` keeps working. REST paths are positional and unaffected. Implementer verification: that FastMCP 4.x carries the validation alias through into the generated input schema; if it does not, declare `company_id` and accept `id` via an explicit second optional parameter that raises `bad_request` when both are present and differ.

**(c) The cap is 50, declared in prose and enforced in code — never as a `maxItems` bound.** Over the cap is `bad_request` per D-007, and the `hint` names two things: the cap, and **the register's own free bulk download**. T17 already established this precedent for `pattern` ("bounds would pre-empt the JSON error envelope and break REST≡MCP parity"), and it applies with more force here: a client-side `maxItems` rejection produces a validation error with no hint, where our error produces the sentence that tells a 500-row caller to stop calling us and fetch `/api/enheter/lastned` instead. An empty list is also `bad_request`. `50` maps to under a minute of the inbound limit and keeps a response inside a sane context budget.

**(d) Partial failure is a row, not a raise — and it reuses `ErrorBody` verbatim.**

```python
class BatchLookupItem(_Base):
    index: int                      # position in the caller's input list, 0-based
    company_id: str                 # the identifier exactly as the caller supplied it
    report: CompanyReport | None    # exactly one of these two is populated
    error: ErrorBody | None         # D-007's inner object, unchanged

class BatchLookupResult(_Base):
    country: str
    registry: str
    requested: int
    succeeded: int
    failed: int
    results: list[BatchLookupItem]
    hint: str | None
```

Two rules make this honest. **No second error shape**: a row's `error` is `ErrorBody` (`core/models.py:840-855`) — the same `code`/`message`/`hint`/`country`/`registry`/`details` an agent already knows, so `{"company_id": …, "error": {…}}` reads as D-007's envelope positioned inside a row. And **the raise/return line is drawn by scope, not by convenience**: a failure that is true of *the request* still raises (`unsupported_country`, `bad_request`, `rate_limited`); a failure that is true of *one identifier* is a row (`invalid_id`, `not_found`, `upstream_error`, `upstream_timeout`). One bad id in fifty cannot fail the call. This is the second deliberate exception to D-007's "raise, do not return", and it follows the first exactly: D-010 exempted `validate` because it "answers a question rather than failing at one", and a batch answers fifty.

There is no top-level `cached` or `fetched_at` on the envelope. Fifty rows can disagree about both, and an aggregate would be a lie; each `CompanyReport` carries its own, as it always has.

**(e) Ordering is the caller's input order, index for index, duplicates included.** Never sorted by success, never by name, never deduplicated in the *output*. The input is a spreadsheet column and the caller must be able to zip; `index` and `company_id` are echoed so a caller that loses order can recover. Upstream fetching **is** deduplicated on the normalised identifier, so a repeated id costs one fetch and fills both rows. (Contrast D-020, which sorts `SearchResult.hits`: there the field's own description promised an order and the caller supplied no order to preserve.)

**(f) Cache: the same keys as a single lookup, and no batch-level entry.** Each identifier reads and writes `"{COUNTRY}:{registry}:{kind}:{normalised-id}"` under D-006 unchanged. A batch of fifty and fifty singles must populate one cache, or a lookup following a batch would miss and the 24 h TTL would pay off twice as rarely. Never cache the batch envelope: it is keyed by an arbitrary set, it would double-store every report, and it would let a stale envelope outlive a fresh row. Research §1's arithmetic is the payoff — a 50-id batch where 40 are hits costs the register 10 requests, which is where D-006 earns its keep most visibly.

**(g) Two meters, measuring two different things — state it or it looks like a bug.** The **inbound rate limiter** exists to protect the upstream register, so it charges one token per identifier that *actually required an upstream fetch*, with a floor of one token per request; cache hits are free because they cost the register nothing. The pre-request gate still debits one token before the handler runs, so an unauthenticated flood hits the wall immediately; the remaining `n-1` are debited after cache resolution. **Metering** (D-030) exists to measure value delivered, so it counts one unit per identifier resolved *including* cache hits. The two numbers will differ and that is correct.

Bounded concurrency upstream: at most 5 in-flight requests per batch, so a 50-id batch cannot burst through Companies House's 600/5-min budget or look like an attack to a keyless brreg.

**(h) REST: one route, `POST /v1/{country}/companies`, body `{"company_ids": [...]}`,** returning `BatchLookupResult`. It is read-only and idempotent and must be documented and annotated as such; it changes no state. *Declined: `GET …?company_id=a&company_id=b`.* It stays honestly safe and cacheable and fifty Norwegian identifiers fit a URL comfortably today — but it will not survive an identifier scheme longer than nine digits (a EUID as input, D-026(a), is 20+ characters), it is truncated by some proxies, and it would fork the request shape between REST and MCP for no gain. *Declined: offering both.* Two routes for one operation is precisely the drift D-004 exists to prevent.

**(i) The MCP `outputSchema` becomes a union, and this is the one part that can force a sixth tool.** `mcp/server.py:190-194` builds each tool's schema from `Model.model_json_schema()`, and `@mcp.tool(output_schema=…)` takes exactly one. The MCP spec is a MUST once declared, so a tool returning `CompanyReport` for a `str` and `BatchLookupResult` for a `list` must declare both: build it with `TypeAdapter[CompanyReport | BatchLookupResult].json_schema()`, which emits a proper `anyOf` over shared `$defs` rather than two hand-merged dicts with colliding definitions. T17 recorded that FastMCP dereferences `$ref`s on the wire, so **the implementer must verify the dereferenced union is served intact and that `content/call.py`'s `.structured_content` path still parses both branches.** If it cannot be served faithfully, the fallback is **not** to drop the output schema — that would sacrifice T17's most valuable gain on the most important tool — it is to move the batch to a sixth tool `lookup_companies`, amend paragraph one of this entry, and update `README.md`, `research/AGENT_PRIMER.md` §1 and `static/llms-full.txt` in the same release so the count is never wrong in print.

**Where it lands.** `core/models.py`: `BatchLookupItem`/`BatchLookupResult` after `SearchResult` (`:782-832`) and before the error section (`:835`), both added to `__all__` (`:32-51`). `core/registry.py`: a **concrete** `async def lookup_many(self, ids: Sequence[str], *, max_concurrency: int = 5) -> BatchLookupResult` beside the other concrete builders (`:188-252`), whose default implementation loops `self.lookup` with bounded concurrency and turns a per-item `RegistryError` into a row — so the ABC stays four abstract methods wide, `registries/xx/` needs no edit, and a country whose upstream has a real multi-id endpoint may override it (D-008, D-014's precedent). Surfaces: `api/main.py:601-637` gains the sibling route; `mcp/server.py:260-304` widens its parameter and its schema. `registries/no/` and `registries/gb/` are not edited at all.
Reason: the product documents a spreadsheet workflow in two places and then makes the agent do it one row at a time — the one gap where our own text sells something we do not have. Everything else here follows from refusing to buy that capability with the thing that actually distinguishes the server: an argument costs a schema union, a sixth tool costs tool-selection accuracy on the two calls that matter most, and only one of those is recoverable by a caller who already knows what it asked for.
Applies to tasks: R-1 in `CORE_ROADMAP_SPEC.md`, T15c (docs), and D-030

### D-025 — NACE harmonisation: two derived fields on `IndustryCode`, a committed table in `core/nace.py`, and never a code the table does not contain
Date: 2026-09-05
Decision: raised by `research/07-product-improvements.md` backlog item 8 and `~/research/registry-mcp/07-product-improvements/12-coverage-gap-accounts-documents-codes-addresses.md` §3. The UK ONS states UK SIC 2007 "is **identical down to the 4 digit level of NACE**"; Norway's SN2007 is likewise NACE Rev. 2 with a national fifth digit. Today an agent comparing an industry across our two live countries gets `06.100 / "Utvinning av råolje"` (`registries/no/mapping.py:150-165`) against `47110 / null` (`registries/gb/mapping.py:118-125`) and cannot compare them at all — "one shape, many countries" is cosmetic for this field.

**(a) Two optional fields on `IndustryCode`** (`core/models.py:189-202`), both defaulting to `None`:

```python
nace_code: str | None = None         # NACE Rev. 2 class, formatted "NN.NN", e.g. "06.10", "47.11"
nace_description: str | None = None  # the English NACE Rev. 2 label for that class
```

**Never overwrite `code`, `description` or `scheme`.** The register's own code and the register's own words are what we quote; the NACE class is what we derive, and D-016/D-018's provenance discipline says the two must not be allowed to look like one thing.

**(b) The table lives in `core/nace.py` as a committed Python module, not a data file.** `NACE_REV2: dict[str, str]` mapping the ~615 four-digit classes to their English labels, plus module constants recording the revision, the source URL, the download date and the licence. *Declined: a CSV under `core/data/` with a loader* — it adds a runtime file-read failure mode to the lookup path, it depends on package-data inclusion surviving both the `uvx` and the `npx` distributions, and mypy cannot see it. *Declined: fetching from Eurostat at runtime* — a third upstream on the hot path for a static table. A generated-then-committed module is diffable in review, importable, and cannot be missing at runtime.

**(c) One country-neutral helper, and the country module decides whether to call it.** `core/nace.py` exposes `nace_class(code: str) -> tuple[str, str] | None`: strip non-digits, take the first four, format `NN.NN`, and **return the pair only if that string is a key of `NACE_REV2`** — otherwise `None`. Truncation is arithmetic on digits, identical for SN2007 and SIC 2007 *because both are NACE-derived by construction*, so it is not national vocabulary and `core/` may hold it (D-001 intact: `core/` knows NACE, it does not know Norway). What is a national judgement is *whether this register's scheme is NACE-derived at all*, and that stays in the country module, which simply does not call the helper when it is not.

**(d) A derived class that is not in the table is `None`, never a constructed string.** This is D-009's "never guess" applied to codes, and it is not hypothetical: Companies House returns administrative SIC values with no NACE parent — `99999` (dormant company), `98000` (residents' property management), `74990` (non-trading company). Naive truncation yields `99.99` and `98.00`, neither of which is a NACE class. The membership test makes the rule self-enforcing rather than requiring an exclusion list that will go stale. Where a register's code yields no class, the country module appends the reason to `notes` if it is systematic (dormant companies are common), and stays silent if it is a one-off.

**(e) `registries/no/` must correct `scheme` to `"SN2007"` in the same change** (`registries/no/mapping.py:157-162` currently emits `scheme="NACE"`). Once `nace_code` carries the real NACE class, a five-digit SN2007 code labelled `scheme: "NACE"` is actively misleading — the field's job is to name *the register's* classification. This is a value change inside a country module, which D-004 permits; it needs the `NORBIZ_SPEC.md` §2 row and any test pinning the string updated with it. GB's `"SIC 2007"` is already correct.

**(f) BLOCKED on two external facts, and the block is on the *table*, not on the fields.** The two model fields and `nace_class()`'s membership rule can be designed and reviewed now; the table cannot be generated until:

1. **Eurostat's redistribution terms for the NACE labels are read.** `12-coverage-gap…` flags this as unsettled: "published for reuse but the exact terms were not read; this must be settled before shipping a bundled table." Fallback if they prove restrictive: derive the labels from the **UK ONS SIC 2007** condensed list, which is Crown copyright under OGL v3 and explicitly reusable, and which by the ONS's own statement carries the same words as NACE at four digits — so the fallback covers both live countries. Record whichever source was used in `core/nace.py`'s constants and in `nace_description`'s field description; the label is our normalisation, not the register's, and must say so.
2. **Which NACE revision UK SIC 2007 and Norwegian SN2007 actually correspond to as of 2026.** The ONS statement quoted by the research concerns NACE **Rev. 2**. A NACE Rev. 2.1 exists and national classifications track it on their own timetables. Generating a Rev. 2 table against a register that has moved to a Rev. 2.1-based national scheme would produce confidently wrong classes for exactly the codes that changed — the failure mode D-009 exists to prevent. Verify per country against the register's own documentation before generating, name the revision in the field descriptions, and if the two live countries turn out to sit on different revisions, that is a finding to bring back here before shipping, not a thing to average.
Reason: this is the cheapest available change that makes "one shape, many countries" true rather than decorative, and the only way to keep it honest is to derive strictly — add alongside, never overwrite, and emit nothing when the table does not vouch for it. The blockers are both licence-and-vintage questions about a static file, which is precisely the kind of fact that is cheap to check once and expensive to discover in production.
Applies to tasks: R-7 in `CORE_ROADMAP_SPEC.md`, T02, T03, T15b, T15c

### D-026 — Before country 4: `euid` and `advertising_protected` go on `CompanyReport`; the LEI does not, and the reason is provenance
Date: 2026-09-05
Decision: `research/02-registers-landscape.md` names three things to do before adding a fourth country. Two are nullable fields and are ruled here as such. The third turns out to be a general interface gap, and closing it properly is what makes D-028 and D-029 possible at all.

**(a) `euid: str | None` on `CompanyReport`, carried verbatim, never constructed.** Commission Implementing Regulation (EU) 2021/1042 Article 9 requires the EUID to be ISO 6523-compliant and to contain a country code, a domestic register identifier, the registration number in that register, and optionally a verification digit — Finland hands one over unprompted (`"euId": {"value": "FIFPRO.0112038-9"}`, live 2026-09-05: `FI` + `FPRO` + `.` + the Y-tunnus). The field goes in the identity block beside `id_scheme` (`core/models.py:555-568`) and is `None` for every register that does not publish one, which today is both of ours.

**We do not build a EUID from parts.** Doing so requires the table of member-state register identifiers, which lives inside BRIS and is not published (`~/research/registry-mcp/02-registers-landscape/14-eu-bris-euid.md` §"What could not be verified"); constructing one from a guessed register identifier would be a fabricated identifier presented as a legal one. *Declined for now: accepting a EUID as `lookup_company` input.* It needs the same missing table and it would put an identifier parser that picks a country inside `core/`, which is a country router by another name. It becomes cheap and worth revisiting once three or four EU registers are live.

Three traps that must appear in the field description, because the search-results soup around this term is real: **the EUID is not the LEI** (register-issued, mandatory, EU-only, free versus voluntary, global, LOU-issued, fee-bearing, CC0 — a company may have both, one or neither); **"EUid" also names the European Digital Identity wallet**, which is a personal credential and nothing to do with company registers; and **the EUID is not stable across a register reorganisation**, since it encodes the register of origin (France's RNE replacing the RCS in 2023 is the worked example). It is a current key, not an eternal one.

**(b) `advertising_protected: bool | None` on `CompanyReport`, and `None` is the default for a reason.** Danish CVR-loven § 19 permits passing contact data on only *"hvis det i forbindelse med videregivelsen klart markeres over for modtageren, at enheden er beskyttet"* — the marking is a legal condition of the transfer, not a footnote; Sweden's `REKLAMSPÄRR` is the same concept. Exact semantics:

* `True` — the register marks this entity as protected against direct-marketing use.
* `False` — the register publishes such a flag for this entity and it is **not** set.
* `None` — **this register publishes no such flag at all.** Norway and the UK today.

The default is `None` and **must not be `False`**. `False` asserts "this entity is not protected", which is a claim about a register that has never made it, and it is the one value a lead-generation caller would act on. That is D-011's lesson applied before the mistake instead of after: a field whose job is to distinguish two states must not have a third that silently means both.

**The flag alone is not compliance.** Because § 19 conditions the *passing on* rather than the holding, a country module that sets `advertising_protected=True` **must also append a plain-English `notes` sentence** stating the protection — written once, in that country's module, per D-010 — so the marking reaches a caller that reads only `notes` and reaches the human that an LLM renders the report to. Rendering the boolean alone into a spreadsheet column satisfies the letter and loses the marking.

**We do not withhold `email`, `phone` or the addresses when it is set.** § 19 conditions the transfer on marking, not on suppression; withholding would be over-compliance that breaks the "we relay what the register publishes" contract and would make `None` mean three things. *Declined names:* `marketing_protected` (ambiguous in both directions), `reklamebeskyttet` (national vocabulary in a field name, forbidden by D-004), `do_not_contact` (asserts a rule we are not the source of). Lands after `phone` in the contact block (`core/models.py:673-678`); `legal/terms.md` gains a sentence, since we are the passer-on.

**(c) The LEI is *not* a field on `CompanyReport`, and the reason generalises.** `CompanyReport` has one `source`, one `source_url`, one `license` and one `fetched_at`. Every field in it is therefore an assertion by *that* register under *that* licence at *that* moment. A `lei` populated from GLEIF inside a document whose provenance block says "Enhetsregisteret (brreg.no) / NLOD 2.0" is a provenance lie, and provenance is the product (D-016, D-018). The same objection kills every other second-upstream item on the roadmap: Peppol/ELMA (D-029, Digdir), Norwegian accounts key figures (a different brreg host, marked *preview*), and officer records fetched from a different endpoint under a different retention rule (D-028).

So the missing concept is not "the LEI". It is **an attachment with its own provenance**, and `core/models.py` gains it once:

```python
class SourceRef(_Base):
    source: str | None = None      # "GLEIF Level 1 (gleif.org)"
    source_url: str | None = None
    license: str | None = None     # "CC0 1.0"
    fetched_at: datetime | None = None
    cached: bool = False

class LeiRecord(_Base):
    lei: str | None = None         # None *inside a present block* = GLEIF holds no LEI
    legal_name: str | None = None
    registration_status: str | None = None
    provenance: SourceRef
    notes: list[str] = []
```

No new vocabulary: `SourceRef` reuses the five provenance names `CompanyReport` already carries. `CompanyReport` gains `lei: LeiRecord | None = None`, always present per D-004, and the two-level nullability is what resolves the ambiguity D-011 warned about: **an absent block means "you did not ask, or the fetch failed"; a present block with `lei=None` means "GLEIF has no LEI for this entity"**, which is a real and useful answer. A fetch that fails leaves the block absent and appends a `notes` sentence saying so — never a present block with invented content.

**The opt-in is `include=[...]` on `lookup_company`**, a closed set validated against the country module's declared capabilities, with an unknown value raising `bad_request` naming the allowed set (never silently ignored, per D-007). D-028 and D-029 both use this argument rather than adding a tool, so it is designed once here. Default is `[]`: every attachment is off unless asked for, which keeps the base lookup one register, one licence, one round trip — and which is also the right privacy default when the attachment is officers.

**GLEIF specifics.** CC0 1.0, keyless, daily golden copy, so no credential and no `requires_api_key` (D-017). Cache TTL **7 days**, not D-006's 24 h: LEI records renew annually and change far more slowly than a company register, and a longer TTL keeps a courtesy load off a free service — the TTL is a property of the record kind, which is the same mechanism D-028 needs for the opposite reason. And GLEIF's CHF 100,000 anti-impersonation clause sits *outside* its data licence, so the rule is: cite GLEIF in `provenance.source`, never imply endorsement, never describe registry-mcp as a GLEIF service.

**Blocked on an external fact:** (b)'s Danish *mapping* — the CVR field name and semantics of the § 19 protection flag — waits on Erhvervsstyrelsen (sagsnummer 177481, answer expected ~2026-09-23, `PROGRESS.md` T16). The *field* is not blocked, and the whole point of ruling it now is that retrofitting it into a frozen shape after Denmark arrives is worse than adding it once.
Reason: two of these are one-line-per-country nullable fields whose only real cost is being added late, and the guide's Step 12 says an abstraction found wrong should be fixed before country three rather than worked around twice. The third looked like a field and was actually the interface gap underneath three separate roadmap items: the report can express a fact the register told us and cannot express a fact somebody *else* told us — which is the same shape of omission D-018 closed for dates.
Applies to tasks: R-2 and R-5 in `CORE_ROADMAP_SPEC.md`, T16, D-028, D-029

### D-027 — `country` stays strictly ISO-3166-1 alpha-2; a sub-national register is a *field on the record*, never a code, never a registry
Date: 2026-09-05
Decision: `research/02-registers-landscape.md` closes with "write down the sub-national question… Germany's Länder courts, Spain's provincial registers and the fifty US states all need a `country`-plus-region key that D-015's strict two-letter code cannot express. That is a `DECISIONS.md` entry, and deciding it late is expensive." Ruled now, before it is urgent, and without adding a country.

**(a) D-015 is not amended. `country` remains ISO-3166-1 alpha-2, upper-case, two letters.** `core/registry.py:359-360` keeps enforcing `len == 2 and isalpha()`; `list_countries()` keeps returning countries; `/v1/{country}/…` keeps taking two letters. *Declined: extending the code to ISO 3166-2* (`DE-BE`, `US-DE`). It would make `CompanyReport.country` sometimes two characters and sometimes five, break every agent that branches on `country == "US"`, turn `list_countries()` into a fifty-one-row list that no tool description can enumerate, and re-open exactly the ambiguity D-015 closed — a country code that means two things is a contract that means nothing.

**(b) Two nullable fields on `CompanyReport` carry the sub-national fact,** in the identity block beside `id_scheme` (`core/models.py:555-568`):

```python
subdivision: str | None = None       # ISO 3166-2, full form incl. the country prefix: "DE-BE", "US-DE"
register_office: str | None = None   # the register's own local name: "Amtsgericht Charlottenburg"
```

The full ISO 3166-2 form is required, not the bare part: `"BE"` alone is indistinguishable from Belgium's country code, and the prefixed form is how ISO 3166-2 is canonically written. `register_office` exists because the ISO code is *our* normalisation and the court's own name is *the register's* word — the `legal_form` / `legal_form_local` precedent, and the thing a German lawyer will actually check.

**(c) One module per country. There is no sub-national `Registry`.** A country whose register is kept in pieces routes internally to those pieces; it does not register fifty-one instances. D-008's "a country is one folder plus one import line" survives, `get_registry()` needs no new key shape, and `_REGISTRIES` stays keyed by country.

**(d) Discovery gets it in advance:** `CountryInfo` (`core/models.py:210-256`) gains `subdivisions: list[str] = []` — the ISO 3166-2 codes that module can answer for, empty meaning a single national register. So an agent learns from `list_countries` / `GET /v1/countries` that a country is partitioned, and learns the partition, without a per-subdivision country row. `Registry` gains the matching `subdivisions: ClassVar[tuple[str, ...]] = ()`, defaulted like `requires_api_key` was in D-017, so `registries/xx/`, `no/` and `gb/` need no edit.

**(e) The identifier rule, which is the part that actually bites.** `CompanyReport.id` must stay **unique within `(country, registry)`** — `lookup(id)` is a function, and every cache key (D-006), every `parent_id`, every batch row (D-024) depends on that. Where a nation's identifier is only unique within a court or a state, the country module **must define a canonical composite, return it as `id`, and document the construction in `id_description` and `rules_markdown()`**. It must not return a court-local number as `id` and hope. If no canonical composite can be defined for a given register, that register does not ship — which is a real answer, not a deferral.

**(f) What this changes about the excluded countries: nothing yet, but the reasons are now clean.** Germany stays out because it has **no official API** (`research/02-registers-landscape.md`: OffeneRegister's dump was last modified 2019-02-05, verified stale by HEAD on 2026-09-05), not because the model cannot hold a Länder court. The United States stays out because it is **fifty-one registers with fifty-one access regimes and no federal company register**, which fails the access axis — not because `core/` cannot express a state. Spain stays out because its data is event-shaped (BORME gazettes), not state-shaped. Removing the modelling objection in advance is the whole value of ruling this today: when Germany opens an API — the single highest-value unknown in the register survey — the decision waiting for it is "is the data good enough", not "how do we say which court".
Reason: the strict two-letter code is load-bearing in six places and the sub-national fact is load-bearing in one, so the cheap and correct direction is to put the fact on the record rather than into the key. And the expensive version of this decision is the one taken under deadline pressure with a half-built German module already in the tree.
Applies to tasks: R-3 in `CORE_ROADMAP_SPEC.md`, and every future country module

### D-028 — Officers and PSC: four privacy preconditions, and the shape is `include=["officers"]`
Date: 2026-09-05
Decision: officers are the highest-demand real gap (`~/research/registry-mcp/07-product-improvements/11-coverage-gap-people-owners-groups-screening.md`: free and open at `GET /api/enheter/{orgnr}/roller` and `/company/{n}/officers`, shipped by three of four active competitors) and the only feature that turns a company-data product into a personal-data product. `CompanyReport` has 52 fields and **not one names a natural person**; that is a design choice, and reversing it is a privacy decision with a code appendix rather than the other way round. **Nothing in this entry may be implemented until all four preconditions below are satisfied.**

**(1) Company → officers only. Never person → companies.** Officers are reachable **only** from a company identifier. No `search_officers(name)`, no officer-appointments index, no officer identifier accepted as a lookup key, no REST route of the shape `/v1/{country}/officers?name=`; the only routes are `include=["officers"]` on the company lookup and `GET /v1/{country}/company/{id}/officers`. A person-centric index over public records is the thing incumbents take reputational damage for, and it is the difference between relaying a register and building a people-search product. `legal/terms.md` already says "we do not create profiles, enrich, or combine this data with any other source" — this rule is what keeps that sentence true, and it may be relaxed only by a further entry in this file citing a completed legal review.

Field-level minimisation, same principle: carry the **service** address the register publishes and never present it as a residential one; carry a **partial** date of birth only where the register publishes only a partial one, labelled as partial, never assembled into a full date; never accept a date of birth as an input to anything. And ship the ENK note first — `registries/no/mapping.py` appending *"This is a sole proprietorship; the registered name and address may be a person's name and home address. Treat as personal data."* is XS effort, touches no `core/` file, closes the live criticism aimed at a competitor with our exact design, and is the cheapest half of this whole entry (already in flight as T20's caveat trio — confirm it landed before starting here).

**(2) A shorter cache TTL for person records, with a ceiling the operator cannot raise.** D-006's TTL is one global constant pair (`core/cache.py:49-50`). ECCTA identity verification came into force 2025-11-18 with the transition ending 2026-11-17, and individuals may apply to suppress a widening set of particulars including residential addresses — so **the UK officer record is a moving target, and a 24 h TTL means serving an address for 24 hours after the register was ordered to stop.**

Mechanism, and it needs no new API: **D-006's cache key already carries a `kind` segment** (`"{COUNTRY}:{registry}:{kind}:{id}"`), so `_ttl_seconds` (`core/cache.py:84-94`) grows a table keyed on that segment instead of a single constant. Person-bearing kinds (`officers`, `psc`) get **1 hour**. Two hard rules: `REGISTRY_MCP_CACHE_TTL_SECONDS` (`core/cache.py:45`) **clamps** rather than overrides for those kinds — an operator tuning performance must not be able to silently extend personal-data retention — and a person record is never written to the cache when `include` did not request it. This is the same per-kind TTL mechanism D-026(c) needs at the other end of the scale (7 days for GLEIF), so build it once.

**(3) A `suppressed` state distinct from `null`, and it is `bool | None`.** Today `None` means "the register does not say". For a suppressed officer particular the truth is different: *the register holds this and has been ordered not to publish it.* On the officer model:

* `suppressed: bool | None` — `True`: the register signals particulars are withheld. `False`: the register signals they are present and not withheld. **`None`: this register does not signal suppression at all**, so absence of a field is ambiguous and the caller must be told rather than reassured.
* `suppressed_fields: list[str]` — which particulars, where the register says which.

`None` is the *initial* value for Companies House and stays there until settled by observation, because the research could not determine whether CH signals suppression explicitly or simply omits the field — and if it omits silently, `suppressed` **cannot be derived at all** and must never be emitted as `False`. That is D-011's invariant restated: the field exists to distinguish two states and must not acquire a third that means both.

**(4) A documented lawful basis, written before the first line of code.** `legal/terms.md` gains a section naming: the categories of personal data relayed and from which register; the lawful basis (legitimate interests, Art. 6(1)(f), with the register's own publication decision doing most of the balancing) and the balancing itself; retention, which is precondition (2)'s TTL stated as a number; the controller/processor split, already correct in the terms; and the existing rectification/erasure route ("contact the register directly — we cannot change what Enhetsregisteret publishes"). Precondition (1) is the control that keeps this out of profiling territory and must be stated as such. **This is a page of text that a lawyer reviews, not an architect's ruling** — nothing in `~/research/registry-mcp/07-product-improvements/10-personal-data-and-gdpr-in-registers.md` is legal advice and neither is this.

**(5) The shape: an argument, not a sixth tool** — D-024(a)'s reasoning, and here it is also the correct privacy default, because a caller must *ask* for personal data rather than receive it by accident. `lookup_company(..., include=["officers"])` using D-026(c)'s mechanism; officers arrive as an attachment carrying their own `SourceRef`, because they come from a different endpoint under a different retention rule:

```python
class CompanyOfficer(_Base):
    name: str; role_code: str | None; role: str | None; role_local: str | None
    is_person: bool | None; appointed_at: date | None; resigned_at: date | None
    is_current: bool | None; nationality: str | None; country_of_residence: str | None
    date_of_birth_partial: str | None      # "1974-03" where the register publishes month+year only
    address: Address | None                # the service address as published
    officer_entity_id: str | None          # when the officer is itself a company — feed to lookup
    source: str | None; suppressed: bool | None; suppressed_fields: list[str] = []

class OfficerBlock(_Base):
    officers: list[CompanyOfficer] = []; provenance: SourceRef; notes: list[str] = []
```

`Registry` gains a **concrete** `async def officers(self, id: str) -> OfficerBlock` that raises `not_implemented` by default, so the ABC stays four abstract methods wide and `registries/xx/` needs no edit (D-008, D-014). REST gets `?include=officers` on the company route **and** `GET /v1/{country}/company/{id}/officers` returning the identical block from the identical builder — one shape, two placements, and the surface assembles neither (D-010).

**(6) GB PSC ships before Norwegian beneficial owners, and Norway's absence is stated, not silent.** UK PSC is free and structured on the key already in use, with residential addresses suppressed by the register. Norway's register requires Maskinporten — an organisation-level onboarding with a virksomhetssertifikat, producing a credential that could never ship in `uvx registry-mcp`, so it is an organisational L and not an engineering task. The interim behaviour is the structured-unavailability pattern: `ErrorCode.NOT_IMPLEMENTED` (501, in the enum since T01 and still unused) with a `hint` naming the register's own portal and who may access it — "the country module exists but this operation is statutorily unavailable here" is precisely what that code is for, and D-007's mandatory hint is the natural home for the alternative. The same pattern serves every CJEU C-37/20-gated country when we reach one.

And one caveat that must appear in the field descriptions and in `notes`, verbatim in substance: **PSC ≠ shareholders.** Companies House publishes a structured PSC register and a separate filing-only statement of capital, and they disagree — a 10% shareholder appears in the statement of capital but not in PSC; a corporate trustee appears in PSC without being a shareholder. A field labelled "beneficial owners" without that sentence is the quiet inaccuracy this project exists to avoid, and `PublishedDeadline.source` is the precedent for naming which register a value came from.

**Blocked on external facts:** whether Companies House signals officer suppression explicitly or omits silently (decides whether (3) can ever be non-`None` for GB); whether brreg's *open* `/roller` returns `fødselsdato` on the unauthenticated path (decides how much of (1)'s minimisation is mandatory rather than elective) — settle both with live unauthenticated calls; whether Directive (EU) 2024/1640 / AMLD6 transposition restores legitimate-interest access to beneficial-ownership registers and on what timetable, which the research library could not close and which decides whether a BO block is ever more than an empty list with a reason outside GB; and the legal review of (4).
Reason: this is the biggest real gap in the product and the only one where shipping it badly is worse than not shipping it at all. Every other decision in this file could be revised by a later entry; a residential address served for 24 hours after the register withdrew it cannot be un-served. So the four preconditions are ruled first and the model is an appendix to them — which is also, conveniently, the order that makes the model come out right.
Applies to tasks: R-8 in `CORE_ROADMAP_SPEC.md`, T20 (the ENK note), T16

### D-029 — Peppol participant status is a second upstream on `include=["peppol"]`, never a boolean on `CompanyReport`
Date: 2026-09-05
Decision: from **1 January 2027** every bokføringspliktig Norwegian business must issue B2B sales documents in an electronic invoice format (bokføringsloven § 10 new second paragraph, LOV-2026-06-19-39, commencement decided 2026-06-19), and the duty is framed against counterparties *"som er **registrert i Elektronisk mottakerregister (ELMA)**, og som dermed kan motta e-faktura"* (Prop. 44 L (2025–2026), ch. 3). DFØ's operational guidance gives the identifier exactly: *"Man må legge inn landkoden, f.eks. Norge **0192:** + organisasjonsnummer"*. That is a per-counterparty, identifier-keyed lookup written into an Act with a date — the single most direct demand driver for a Norwegian organisasjonsnummer tool that exists, and `research/AGENT_PRIMER.md` §7 names it as the highest-value addition an accounting agent asked for that nobody offers.

**(a) It is a second upstream, and therefore an attachment.** ELMA is a Peppol SMP operated by **Digitaliseringsdirektoratet**, not by Brønnøysundregistrene. Under D-026(c) a fact from another organisation may not travel in a document whose `source`/`license` name Enhetsregisteret and NLOD 2.0. The research supplies the argument's teeth: DFØ's own troubleshooting concedes that *"ELMA-registeret har ikke oppdatert informasjonen fra adresseregisteret"* — **the two registers can disagree**, and a merged boolean would make the disagreement invisible at precisely the moment a caller needs to know which register answered. That is D-018's principle (say which source said what) applied to a capability rather than a date.

**(b) The shape: `include=["peppol"]` on `lookup_company`. The five-tool count is not amended.** D-024 ratified the count and D-026(c) built the mechanism; this is its second user.

```python
class PeppolParticipant(_Base):
    participant_id: str                    # "0192:923609016" — ISO 6523 scheme + identifier
    registered: bool | None = None         # None only when the lookup itself failed
    document_types: list[str] = []         # the profiles/document types the SMP advertises
    smp_url: str | None = None
    provenance: SourceRef                  # source names ELMA/Digdir and which route answered
    notes: list[str] = []
```

`CompanyReport` gains `peppol: PeppolParticipant | None = None`. `registered=False` is an honest value here, unlike most negatives in this codebase: an authoritative SMP resolution that finds no participant is a definite "not reachable on the network", so `False` is a fact and `None` is reserved for "we could not ask".

**`peppol`, not `elma`.** D-004 forbids national vocabulary in a field or model name; ELMA is the *Norwegian* SMP inside the Peppol network, so Peppol is the country-neutral word and the field generalises unchanged to Denmark's NemHandel and to whatever the EU ViDA timetable produces elsewhere. "ELMA" appears in `provenance.source` — a *value* — which is exactly where D-004 says national vocabulary belongs.

**(c) `participant_id` is derivable offline and is always present.** `validate_company_id(id, "NO")` already normalises and MOD11-checks an organisasjonsnummer with no network call, and `0192:` + that string is the participant identifier by definition. So the field is populated even when the registration lookup fails — the caller gets the key it needs to ask elsewhere, which is what D-007's hints exist to provide.

**(d) Which route is authoritative, and it must be recorded.** DFØ names three ways to ask (the Peppol Directory, an `anskaffelser.dev` lookup, and a Peppol lookup). The **SMP resolution is the authoritative one** — it is what a sending access point actually performs and it is what returns the supported document types — while the Directory is a search index that can lag. Rule: prefer the authoritative resolution, allow the Directory as a fallback, and **name in `provenance.source` which one answered**. A caller acting on a statutory duty is entitled to know whether it was told by the network or by an index of the network.

**(e) Cache TTL inverts nothing — it reuses D-006's asymmetry, for the same reason.** **24 h for a positive, 1 h for a negative.** D-006 gives negative results a short TTL because "a newly registered company must become visible fast", and the direction of harm points the same way here, harder: from 1 January 2027 a stale *negative* makes a sender skip a statutory duty and issue a non-compliant invoice, while a stale *positive* makes it send an e-invoice that bounces — one is a breach, the other is recoverable. The per-kind TTL table D-028(2) introduces is where this lives.

**(f) The 2027 duty is not a `Deadline`, and must not become one.** It has no per-entity due date, it is a capability requirement rather than a filing, and whether it binds a given entity turns on facts we cannot see — turnover below NOK 50,000 is exempt, as are *finansvirksomhet, forsikringsselskaper og pensjonsforetak* (Prop. 44 L ch. 3). Emitting a `Deadline` for it would require guessing a duty from a legal form, which is exactly what D-009 forbids and what D-022(c) restated for arithmetic. It belongs in `rules_markdown()` prose with its citations — both dates (1 January 2027 to send, 1 January 2030 to receive and to keep books in an electronic accounting system, bokføringsloven § 7 new fourth paragraph), the exemptions, and the ELMA-scoping sentence — where an agent that *does* know the missing input can apply it. Same treatment D-016(b) gave corporation tax.

**Blocked on external facts:** the exact authoritative SMP/Directory endpoints, their terms of use, and whether Digdir publishes a rate limit or expects registration for our volume; and the Skattedirektoratet report due end-2026 on B2C e-invoicing and e-receipts, which could widen the scope of what a caller needs to ask.
Reason: this is the rare feature with a statutory deadline attached to somebody else's calendar, and it is worth building *because* of the ELMA/Enhetsregisteret lag rather than in spite of it — a caller answering a legal question about two registers that disagree needs both answers labelled, and that is the one thing this codebase is already better at than anything else in the market. Building it as a bare boolean would have thrown away the only part that was hard to earn.
Applies to tasks: R-6 in `CORE_ROADMAP_SPEC.md`, T02 (`rules_markdown`), T15c

### D-030 — API keys and metering: `Authorization: Bearer`, per-identifier units, and stdio plus the anonymous hosted path stay keyless forever
Date: 2026-09-05
Decision: there is no authentication on the hosted API, so there is no way to identify a caller, meter one, or bill one; the per-IP limiter (`api/ratelimit.py:56-112`) collapses every agent behind a proxy onto one bucket, which under-serves a legitimate high-volume customer and over-serves an abusive one (`REVIEW.md` T10). This is backlog item 11 — "the gate to every revenue item on this list".

**(a) The invariant, first, because everything else is subordinate to it.** **`uvx registry-mcp` / `npx registry-mcp` stdio never requires a key, and the anonymous hosted MCP endpoint at `/mcp` never requires a key.** This is not a courtesy, it is the strongest usage signal in the research library: ENTIA, with an anonymous endpoint, has 16,045 Smithery uses; OpenRegistry, with thirty registries and a required key, has **3**; `bouch/uk-due-diligence` has 60,787 with a two-line description. *Anonymous access predicts usage; breadth does not.* The MCP specification agrees for the stdio half — implementations on stdio "SHOULD NOT" follow the authorization spec and should take credentials from the environment, which is exactly what `COMPANIES_HOUSE_API_KEY` already does (D-017). Any later decision that gates the anonymous path must amend this paragraph explicitly.

**(b) A key buys capacity and identity, not capability.** At launch **no tool, no country and no field is behind a key**; the five tools, both countries and every shape stay byte-identical across the anonymous and keyed tiers (D-004 extends to the auth tier). The anonymous ceiling is today's 60/min per IP; a key raises it and meters it per key instead of per IP. The pitch is therefore "get a key so your fleet is not one bucket", not "pay us" — and the first customer-visible benefit is the fix to a defect we already know about. Only a capability with a genuinely different cost base (exports, monitored companies, a change-feed-backed freshness guarantee) may ever sit behind the key, and each one needs its own entry here saying so.

**(c) Header: `Authorization: Bearer <key>` canonical, `X-API-Key: <key>` accepted.** Bearer because it is what MCP clients and HTTP libraries reach for and because an eventual OAuth migration reuses the same header unchanged — a key becomes a token and nothing else moves. `X-API-Key` because it is what a curl or spreadsheet user types. Both present and different is `bad_request`. **A key in a query string is refused outright** (`?api_key=` → `bad_request` whose hint names the header): query strings land in access logs, proxy logs and browser history, and accepting one would leak keys through our own `core/log.py`.

Key format `rmcp_live_<random>` with a visible constant prefix, so a leaked key is greppable in a repository, revocable on sight, and matchable by secret scanners. Costs nothing to decide now and cannot be retrofitted onto issued keys.

**(d) Never the secret, only its identity — D-017's rule generalised.** `core/log.py`'s `calls` table (`:69-77`) gains `key_id`, an opaque non-secret handle, and nothing anywhere logs, echoes, aggregates or puts a key **value** into `/v1/stats`, `/dashboard`, a `RegistryError.details` or a response header. D-017 already asserts the principle for upstream credentials ("it holds the variable's *name*… nothing anywhere publishes, logs or puts a key value in a `RegistryError.details`"); this is the same rule pointed inward.

**(e) A bad key is 401, not a silent downgrade.** `core/models.py` gains `ErrorCode.UNAUTHORIZED = "unauthorized"` (`:109-141`) mapped to 401 in `HTTP_STATUS` (`:876-886`) — D-007 permits adding a member and forbids renaming one — with a mandatory hint that names the fix **and** names the anonymous fallback: "remove the header to use the anonymous tier at 60 requests/minute". *Declined: degrading a bad key to anonymous silently.* It hides a revoked or mistyped key behind a service that appears to work, and then the customer's quota is not applied and nobody finds out until the invoice.

**(f) What is counted: one unit per identifier resolved, including cache hits.** A 50-id batch (D-024) is **50 units, not one call** — anything else makes the batch a metering hole and the pricing model nonsense. Cache hits count, because metering measures value delivered to the caller, not cost incurred by us. **This is deliberately the opposite of D-024(g)'s rate-limit accounting, where a cache hit is free** — the limiter protects the upstream register and so counts upstream fetches; the meter measures answers and so counts answers. Two meters, two questions, and stating it here is what stops the difference reading as a bug.

The rest of the rule, in one line: **metered iff the response carries register-derived data or a register-derived verdict.** So `lookup_company` and `search_company` are metered; `company_deadlines` meters its underlying lookup and not the computation; a `not_found` is metered (upstream was consulted, or its cached verdict was served) while `invalid_id`, `bad_request`, `unsupported_country`, `rate_limited` and `unauthorized` are not (we spent nothing and the caller got no data).

**`validate_company_id` and `list_countries` are never metered.** They make no network call, and metering a pure function would teach an agent to skip the cheap pre-check that `validate_company_id`'s own docstring tells it to make before spending a real lookup — the meter would be charging for the behaviour we spent T17 trying to encourage. They keep a generous anti-abuse ceiling and nothing else.

**Where it lands.** A new `api/auth.py` resolving a request to `(key_id, tier)` or anonymous; `api/ratelimit.py:82-112` taking its bucket capacity and its bucket *key* from that resolution instead of always from `client_ip`; `core/log.py:135-175` gaining `key_id`; `api/stats.py` aggregating per key. **`core/models.py` changes by exactly one enum member and one status row**, and `core/registry.py` not at all — which is why this is a surface feature and cheap, and why it can land in parallel with anything else on the roadmap.
Reason: authentication is the gate to every revenue item, and the way to build it without spending the asset that actually produces the usage is to be precise about what the key is *for*. It buys per-caller identity, per-caller capacity and a bill; it buys no capability, it never touches stdio, and it never touches the anonymous endpoint. The single number in the research that should govern this decision is 16,045 against 3.
Applies to tasks: R-4 in `CORE_ROADMAP_SPEC.md`, T08, D-024

### D-031 — ChatGPT connector compatibility: `search` and `fetch` ship as two aliases over existing operations, and the count becomes "five registry tools plus two connector aliases"
Date: 2026-09-05
Decision: raised by `~/research/registry-mcp/05-competitors/10-traction-and-usage-signals.md` §3 — "the `search`/`fetch` pair shows up in the top two… It is the cheapest untaken distribution channel in the field and registry-mcp does not have it" — and by `04-multi-country-and-gleif-mcp-servers.md`, whose usage leader (`entia/entity-verification`, Smithery useCount 16,045) and category leader by useCount (`bouch/uk-due-diligence`, 60,787) both ship the pair alongside their domain tools.

**The external contract, read first and quoted.** `https://platform.openai.com/docs/mcp` 301-redirects to **`https://developers.openai.com/api/docs/mcp`**, which is the page these shapes are taken from (fetched 2026-09-05). Verbatim:

> "To work with ChatGPT deep research and company knowledge, your MCP server should implement two read-only tools: `search` and `fetch`"

`search` — arguments: *"A single query string."* Returns *"An object with a single key, 'results', whose value is an array of result objects. Each result object should include: id - a unique ID for the document or search result item, title - human-readable title, url - canonical URL for citation."*

`fetch` — arguments: *"A string which is a unique identifier for the search document."* Returns *"A single object with the following properties: id - a unique ID for the document or search result item, title - a string title for the search result item, text - The full text of the document or item, url - a URL to the document or search result item, metadata - an optional key/value pairing of data about the result"*

Both must be served as `structuredContent` **and** as a `content` array carrying the same object JSON-encoded as text; both *"must declare output schemas using typed models"*; and the citation rule is absolute:

> "ChatGPT creates citation metadata only when `url` is a non-empty string."

**(a) The ruling: we ship them. Five tools become seven, and D-024's ratification is amended here rather than quietly outgrown.** D-024 paragraph one says *"`registry-mcp` exposes five MCP tools. Adding a sixth requires an explicit amendment of this entry, in this file, with the tool-selection cost argued rather than assumed."* This is that amendment, and it is the first one: D-024, D-028 and D-029 all invoked the rule and all stayed at five, and each of those was a *capability* asking for a tool. This is not a capability. It is **two aliases over operations that already exist**, added because one large client can only call this server by those two names.

The cost, argued rather than assumed. Seven tools is still ~17% of the ~40-tool ceiling `client-support-discovery-and-tool-limits.md` measures for Cursor, so **the budget is not the cost** — the cost is *retrieval collision*, and it is real: under Claude Code's tool search *"the tool's name and first sentence become the retrieval key"*, and `search` sits next to `search_company` while `fetch` sits next to `lookup_company`. That is the shape D-024 declined for `lookup_companies` ("two tools whose names differ by one letter… the failure mode is the agent calling the *wrong tool*"). Three things make it survivable here where it was not there. **The failure is degradation, not error**: an agent that lands on `search` still gets identifiers it can act on, and one that lands on `fetch` gets a *superset* — `metadata` carries the byte-identical `CompanyReport` and `DeadlineReport` — so it loses tokens, never facts. **The descriptions are written to lose the contest** ((e) below): each opens by naming itself an alias and naming the tool to prefer, which is the one lever tool search actually reads. **And it is measurable**: T19's 26-case eval is the instrument, group F already tests tool choice and restraint, and CONNECTOR_SPEC.md adds five cases (E27–E31) of which the last, E31, exists solely to catch a Claude-side regression.

*Declined: declining.* The gap is not cosmetic. In deep research ChatGPT calls exactly `search` and `fetch`; a server without them is not degraded there, it is **unreachable**. Against that, every argument for five is an argument about a budget we are nowhere near.

*Declined: a second endpoint (`/mcp/chatgpt`) serving only these two.* It is the tidiest answer to retrieval collision and it was seriously considered — FastMCP can mount a second server, and `server.json` can carry a second remote. It loses on evidence and on cost: both usage leaders in our own research chose one endpoint carrying both (`bouch/uk-due-diligence` "ships `search` and `fetch` alongside its 14 domain tools"), and a second endpoint doubles the deploy, status-page, logging and metering surface, forks the README's install instructions, and gives a Claude user no way to reach `fetch` at all — all to buy a collision we can measure and, if it appears, fix by editing two strings. **Keep it as the named escape hatch**: if the eval shows an agent preferring `search` over `search_company` on a plain name query, split the endpoint rather than reword forever.

**(b) "Only when a client asks" is not available, and the near-miss is worth naming precisely.** MCP has no capability negotiation for tool subsets: `initialize` carries `clientInfo: {name, version}` and `tools/list` is answered per session, so a server *could* sniff a self-reported client name and vary its tool list, and FastMCP 4.0.2 has the machinery to do it. **We decline that, and it is not "the client asking" in any case** — the client never asks; the server guesses from an unauthenticated string. It would make `tools/list` non-deterministic, mean the tool list a directory scrapes is not the tool list a user gets, and put a caller-conditional branch into the one surface D-004's "no surface-specific reshaping" exists to keep unconditional. The honest statement is: *the protocol offers no negotiated tool profile; a server can only guess, and we do not.*

**(c) `search(query: str)` — one string, and the parser is allowed to be dumb because the fan-out covers it.**

* **Country is derived, never defaulted.** If a whitespace-delimited token of the query case-insensitively equals a live registry's `country` code, or a live registry's `country_info().name` appears in the query, that country is used and the token is dropped from the search string. Otherwise **the query fans out across every registry `list_registries()` returns**, at most 5 in flight (D-024(g)'s bound), and the hits are merged. *Declined: defaulting to `country="NO"` for parity with the five tools.* Those five take a `country` argument the caller can correct; `search(query)` does not, so a default is not a default, it is a guess presented as an answer — a ChatGPT user asking about Tesco would be told no such Norwegian company exists. The matcher is deliberately thin (no synonym table: "UK", "Britain", "Norwegian" are not matched — country vocabulary in country-neutral code is forbidden by D-001, and an alias table would re-open D-014's declined `UK`→`GB` by the back door), and **it can be thin precisely because a miss is free**: an unmatched country token stays in the search string, the fan-out queries that country anyway, and the right hit still comes back.
* **A per-country failure inside the fan-out is a dropped country, never a raised error** — D-024(d)'s scope rule, applied one level up: a failure true of *one register* is not true of *the request*. A `GB` deployment with no `COMPANIES_HOUSE_API_KEY` therefore returns Norway's hits rather than nothing. A failure true of the request (empty query) still raises `bad_request`, byte-identical to `search_company`'s (D-007).
* **An identifier short-circuits to a lookup.** For each candidate country, `Registry.validate(query)` decides — no regex in the connector, no country knowledge (D-008). Every country that says `valid: true` gets one `lookup`; each success becomes one row. A `not_found` here contributes no row and is **not** an error: in a search, "nothing matched" is a real answer.
* **Otherwise it is a name search**: `registry.search(name, limit=10)` per country, merged, sorted by `confidence` descending with ties keeping the register's order (D-020, unchanged — it is the model's own validator doing the sorting), total capped at 20.
* **`id` is `"{COUNTRY}:{normalised-identifier}"`** — `"NO:923609016"`, `"GB:00445790"`. Upper-case ISO-2, the identifier as `validate_id` normalised it, one colon, no spaces. It is unique because D-008 keys `_REGISTRIES` by country and D-027(e) makes `id` unique within `(country, registry)`; if a country ever registers two registries the composite gains the registry segment, and nothing else changes. `fetch(search_result.id)` must round-trip for every row this tool emits — that is the whole contract between the two tools and it is directly testable.
* **`title` is the only prose ChatGPT reads before choosing what to fetch**, so it carries what decides that choice: `"{name} — {country} {id}"`, then `" — {legal_form}, {status}"` for whichever of those two is known, then `" — sub-unit"` when `is_subunit`. → `"EQUINOR ASA — NO 923609016 — Public limited company, active"`. A dissolved company says so before it costs a fetch.
* **`url` is our own REST record URL — `https://api.foretak.dev/v1/{COUNTRY}/company/{id}` — not the register's `source_url`.** Two reasons, and the second is the load-bearing one. It is **always non-empty**, and OpenAI's rule is that a blank `url` silently loses the citation; `SearchHit.source_url` is `str | None` and a future country module may leave it null, which would produce an uncitable result with no error anywhere. And it **resolves to the same bytes the agent was given** — `fetch`'s `metadata.company_report` is `model_dump(mode="json")` of exactly what that URL serves, so the citation is verifiable in the strongest available sense. The register's own URL is not lost: it travels as `metadata.source_url` and inside `text`, which is where D-004 already puts provenance. *Declined: synthesising a human-facing register page* (`virksomhet.brreg.no/...`) — it exists for Norway, we do not emit it anywhere today, and inventing one in a country-neutral surface is country knowledge outside `registries/` (D-001).
* **Zero hits returns one row per live country pointing at that country's rules document**, `id` = `"rules:{COUNTRY}"`, `title` = `"{registry name} ({country}) — identifier rules, legal forms and filing deadlines"`, `url` = `https://api.foretak.dev/v1/countries`. These are **real documents** — the same `registry.rules_markdown()` already served at `registry://rules/{country}` — never a fabricated company, and the id namespace cannot collide with a country code, which is always two letters. This is the one place the connector can answer D-007's question ("what should I do next?") at all: `search` results have no `hint` field, so on a dead end the next action has to *be* a result or it cannot be said. Left as `results: []`, a deep-research run learns nothing, not even which countries we cover.

**(d) `fetch(id: str)` — one document, assembled from two operations that already exist.**

* **Parse on the first colon.** `"XX:..."` with a two-letter left part is a country; `"rules:XX"` is a rules document. **No colon: derive, never default** — every live registry's `validate_id` is tried, and exactly one match wins; zero or two or more is `bad_request` naming the `"{COUNTRY}:{identifier}"` form and `list_countries`. There is no default country anywhere in this surface; `country="NO"` remains the default only on the five tools, where the caller can override it.
* **`text` is a human-readable Markdown rendering, not the JSON string.** OpenAI's own words for the field are *"The full text of the document"*, and `metadata` is where they put structure; deep research quotes `text`. It renders identity, status, legal form, addresses, VAT, employees, industry codes, provenance (`source`, `source_url`, `license`, `fetched_at`, `cached`) — and **every `notes` sentence verbatim**, because `notes` is where a country module's caveats live (D-010) and a rendering that drops them is the one that gets someone hurt.
* **`text` includes the deadlines, and they are free.** `company_deadlines` already does `lookup` then `deadline_report(report, today)` — the second step is pure and makes no upstream call, so one cached lookup yields both documents. This matters more here than anywhere: in deep research ChatGPT *cannot* call `company_deadlines`, so a `fetch` that omits deadlines silently removes the product's differentiator from its largest potential client. Each rendered deadline carries `due_date` and `applies_because`, per `company_deadlines`' own instruction to quote the reason rather than the number.
* **`metadata` carries the structured documents so nothing is lost**: `company_report` and `deadline_report`, each the exact `model_dump(mode="json")` the five tools return, plus flat scalar keys (`country`, `registry`, `company_id`, `name`, `status`, `is_active`, `legal_form`, `source`, `source_url`, `license`, `cached`, `fetched_at`, `next_deadline_kind`, `next_deadline_due_date`) for any client that flattens metadata. The duplication is deliberate: **whether ChatGPT preserves nested objects under `metadata` is not stated on OpenAI's page and we did not verify it**, so the decision-relevant facts are carried twice — once where a flattening client can still read them, once in full — and `text` carries everything regardless.
* **Errors are D-007, unchanged.** A raised `RegistryError` becomes the same `ToolError` whose text is `json.dumps(err.to_dict())` that the five tools raise, through the same `_tool_error` serialiser — the "one serialiser" rule exists exactly so a new surface cannot invent a second error shape. `not_found` at `fetch` **is** an error (unlike inside `search`): the caller named one document and it is not there. It should be rare by construction, because ids come from our own `search`; when it happens the register changed between the two calls, which is worth surfacing rather than hiding behind an empty document. *Unverified: whether a tool error aborts a deep-research run or is recovered from — OpenAI's page does not say.*

**(e) Same annotations as the five, and descriptions written to lose a retrieval contest.** Both tools are `_READ_EXTERNAL` — `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, `openWorldHint: true` — plus a `title`. This is not decoration: `client-support-discovery-and-tool-limits.md` records OpenAI's own submission requirement, *"Tool annotations required: `readOnlyHint`, `openWorldHint`, and `destructiveHint` for every MCP tool"*, so a connector alias without them fails the review it exists to pass.

The descriptions are **short, outcome-shaped, and open by de-prioritising themselves**, which is the deliberate inversion of how the five docstrings are written. The two clients read a description for different purposes: ChatGPT deep research calls `search`/`fetch` **by name** and reads the description only to shape its argument, while Claude Code and Cursor reach a tool **through** its description under tool search. So the first sentence — the retrieval key — is spent telling a non-ChatGPT client to go elsewhere, and the second does the work ChatGPT needs. Verbatim:

The two strings below are the description text exactly as it must reach the wire (quote them in Python however the file's style prefers — the backslashes are not part of the text):

```text
search:
ChatGPT connector alias; other clients should prefer `search_company`, which takes an
explicit `country` and returns the full SearchResult. Finds companies in this server's
national business registers (Norway, United Kingdom) from one free-text query — a name, a
national identifier, or a name plus a country — and returns {"results": [{"id", "title",
"url"}]}. Pass a result's `id` to `fetch`.

fetch:
ChatGPT connector alias; other clients should prefer `lookup_company` plus
`company_deadlines`, which return the CompanyReport and DeadlineReport shapes directly.
Takes one `id` from `search` — "{COUNTRY}:{identifier}", e.g. "NO:923609016" — and returns
that company's register record and statutory filing deadlines as readable text, with both
full JSON documents in `metadata`.
```

(Line breaks above are wrapping for this file only; each description is one paragraph.)

Titles: `"Find a company (ChatGPT connector alias for search_company)"` and `"Fetch one company record (ChatGPT connector alias for lookup_company)"`.

**(f) The count wording, amended in four places in one release.** The replacement phrasing is **"five registry tools plus two connector aliases"** — it survives contact with a reader who counts `tools/list` and gets seven, and it says which two are which. Concretely: `README.md:27` ("Five tools, not fifty") becomes "Seven tools, not fifty — five registry tools plus two ChatGPT connector aliases", keeping the budget arithmetic and correcting 12% to ~17%; `README.md:37`'s status line becomes "The five registry tools and their response shapes are frozen; two connector aliases (`search`, `fetch`) wrap them for ChatGPT and add no new shape"; `README.md`'s Tools table gains a two-row section under that heading; `MULTI_AGENT_BUILD_GUIDE.md` Step 5 and `research/AGENT_PRIMER.md` §1 and §10 take the same phrase; `static/llms-full.txt` gains a section documenting both. **Nothing in this file is amended except D-024 paragraph one**, and it is amended by this entry rather than contradicted: the sentence now reads "five registry tools plus two connector aliases; a sixth *registry* tool still requires an explicit amendment". The rule D-024 was protecting — that a capability may not buy itself a tool slot — is untouched, and D-028 and D-029 remain at five under it.

**(g) What does not change, stated so no implementer has to infer it.** **The REST surface gains nothing** — no `/v1/search`, no `/v1/fetch`. D-004's "one shape, both surfaces" binds *operations*; these are not operations, they are a client's calling convention wrapped around `lookup`, `search` and `deadline_report`, and giving a shim a REST twin would assert it is a shape we own. **`core/` is not touched**: no model, no `Registry` method, no enum member — if the implementation wants either, that is a finding to bring back here, not a patch. **The five tools' names, signatures, annotations, output schemas and wire bytes are byte-identical afterwards**, and the existing REST≡MCP parity tests must pass unchanged, exactly as D-024(a) requires of the batch argument. **No country module is edited**, and no country string appears in the new code — the fan-out walks `list_registries()`, the identifier check is `Registry.validate`, the rules rows are `rules_markdown()` (D-001, D-008). The new wire shapes (`{results:[…]}` and the fetch document) live in `mcp/connector.py`, **not** `core/models.py`, and are marked there as the one place in this repo where an external contract dictates a field list; they are exempt from D-004 because they are somebody else's shape, not ours.

Implementation spec, JSON examples for one NO and one GB case, the five eval cases and the README wording: **`CONNECTOR_SPEC.md`**.
Reason: this is the cheapest distribution channel left in the field and the only one that is gated on nothing — no login, no directory review, no partner list — and the two servers with the most measured usage in our own competitor research both ship exactly this pair. The count was never the asset; **the tool-selection budget was**, and seven of forty spends none of it. What the entry spends its length on instead is the thing that can actually go wrong: two aliases that shadow the two tools that matter most, mitigated by descriptions that disqualify themselves, by a `fetch` payload that is a superset rather than a substitute, and by an eval that would catch it — with a second endpoint held in reserve as the fix if it does.
Applies to tasks: T23, `CONNECTOR_SPEC.md`; amends D-024 paragraph one
