# REVIEW

Architect (Opus A) review notes, one section per task. A note marked **BLOCKING** sends the task back to `doing` in `PROGRESS.md`. Non-blocking notes are recorded and may become follow-up tasks.

Format: `## <task id> — <date> — <verdict: APPROVED | BLOCKED>` followed by bullet notes.

---

## T02 — 2026-09-03 — BLOCKED

Reviewed: `src/registry_mcp/core/rules/common.py`, `src/registry_mcp/registries/no/rules.py`, `tests/test_rules_common.py`, `tests/test_rules_no.py`.

Verified clean, and worth saying explicitly: **no Norwegian logic, constant or import leaked into `core/`** (`common.py` takes holidays as a parameter and imports only `calendar`/`datetime`); MOD11 including the remainder-10 unissuable case is correct (`rules.py:94-96`, spec test 10); VAT term 3 is 31 August (`rules.py:414`); weekend + Norwegian-holiday roll-forward is correct including Easter/pinse (`rules.py:105-146`); status precedence matches §8 exactly (`rules.py:343-378`); every numbered spec test 1–56 and 57–81 exists, one function per number, with the spec's own dates (extra test `test_76b` for `UNDER_COMPULSORY_LIQUIDATION` is a welcome addition). Done-check reproduced: 84 tests pass, **100 % coverage** (225/225 stmts) on `core/rules/common.py` + `registries/no/rules.py`. `mypy .` and `ruff check .` clean repo-wide.

### BLOCKING

- **B1 — an unclassified legal form still produces deadlines.** `NORBIZ_SPEC.md` §7 line 330: *"Never guess a duty. An unknown code must never produce a deadline."* `deadlines_for` (`src/registry_mcp/registries/no/rules.py:623-650`) never consults whether the code is classified: `tax_return` is appended unconditionally at `rules.py:641`, and `vat_return` / `payroll_report` follow at `:644-647`. Verified by running the real code: a report with `organisasjonsform.kode = "ZZZZ"` (the spec's own test-25 fantasy form) yields `['payroll_report', 'tax_return']`. Fix per **D-009(a)**: return `[]` when `report.legal_form_code` is missing or not a key of `ORG_FORMS`, and have `deadline_exemption_note` (`rules.py:425-447`) explain it so the mapping surfaces it in `notes`.
- **B2 — `tax_return` is emitted for public-sector and unverified legal forms.** Same code path, `rules.py:641`. Verified against the real second fixture: `tests/fixtures/brreg_974760673.json` (Registerenheten i Brønnøysund, `ORGL`) produces `tax_return` due 2026-06-01 — i.e. we would tell an agent that a state agency owes a *Skattemelding for næringsdrivende*. §5.4's "all forms except sub-units" is a looser statement than §7's "never guess a duty", and §7 wins. Fix per **D-009(b)**: gate `tax_return` on an explicit `_TAX_RETURN_FORMS = {"AS","ASA","ENK","ANS","DA","NUF","SA","KS","BA"}`. This keeps spec tests 57–81 and 72–73 passing unchanged (checked). Add a test for `ORGL` → no `tax_return` and for an unlisted code → `[]`. `NORBIZ_SPEC.md` §5.4 (the `tax_return` row) and §7 may be edited for this — the exception to "don't touch the spec" is granted for these two lines only.

### Notes (non-blocking)

- `applies_because` does not name the triggering legal form. §5.4 asks for *"one English sentence naming the legal form or flag that triggered it"* and gives *"An AS must file annual accounts…"* as the model. `rules.py:468-471` says "This legal form must file annual accounts with Regnskapsregisteret." — grammatical, but it names neither the form nor the flag, and `static/llms-full.txt:245` advertises the spec's wording to agents. Interpolate `report.legal_form_code` while B1/B2 are being fixed.
- `deadlines_for` trusts `report.has_annual_accounts_duty` (`rules.py:637`) rather than deriving it from `legal_form_code`. Correct for reports built by `mapping.map_entity`, but a hand-built or partially-populated report silently loses the deadline. Consider falling back to `legal_form_info(code).has_annual_accounts_duty` when the field is `None`. Relevant to T06, which will call `deadlines` on a report that came back through the cache.
- Spec test 81's second half ("two different machine timezones give the same answer") is not implemented — only the purity half is (`tests/test_rules_no.py:560-565`). A `monkeypatch.setenv("TZ", …)` + `time.tzset()` variant would close it. Low value, since the module reads no clock at all, but it is a numbered line.
- `tests/test_rules_no.py` covers §13 sections A/B/C/E/F, `tests/test_rules_common.py` covers D. `NORBIZ_SPEC.md` §13/§14 name the files `tests/no/test_rules.py`; `tasks/T02.md` names `tests/test_rules_no.py`. The task file was followed — correct call, no action, but the spec's file names are now stale.
- `ORG_FORMS` / `LEGAL_FORMS` alias and `deadlines = deadlines_for` alias (`rules.py:258`, `:657`) are extra surface area not in the task. Both are justified in the docstrings and used by `registries/no/__init__.py`; keeping them, but the module now has two public names for one function — fold `deadlines` into the canonical name at T10 if `__init__.py` is refactored.
- `norwegian_holidays` is `@cache`d on an unbounded `year` argument (`rules.py:124`). Harmless in practice (frozenset return, tiny), noted only so nobody later passes attacker-controlled years to it.

## T03 — 2026-09-03 — APPROVED

Reviewed: `src/registry_mcp/core/cache.py`, `src/registry_mcp/registries/no/{__init__,client,mapping}.py`, `tests/test_client_no.py`, `tests/test_cache.py`, `tests/fixtures/*.json`, `scripts/lookup_demo.py`.

**No field was guessed.** Every brreg field name the mapper reads is present in the two committed live fixtures or is listed optional in §2 — checked field by field against `tests/fixtures/brreg_923609016.json` and `brreg_974760673.json`: `organisasjonsnummer`, `navn`, `historiskeNavn[].navn`, `organisasjonsform.{kode,beskrivelse}`, the five `registrertI*` booleans, `harRegistrertAntallAnsatte`/`antallAnsatte`, `naeringskode1..3`, `institusjonellSektorkode.{kode,beskrivelse}`, `vedtektsfestetFormaal`, `aktivitet`, `kapital.{belop,valuta}`, `forretningsadresse`/`postadresse` (all seven sub-fields), `hjemmeside`, `epostadresse`, `telefon`, `overordnetEnhet`, `erIKonsern`, `sisteInnsendteAarsregnskap`, `konkurs`, `underAvvikling`, `underTvangsavviklingEllerTvangsopplosning`, `slettedato`, `konkursdato`, the four `registreringsdato*` dates. The §2 "deliberately not mapped" list is respected — no smuggling into `notes`. The 410-Gone `VERIFY` was resolved by live evidence and the finding is written into §1.1/§6; the defensive 410 path is kept and labelled as such (`client.py:142-163`). Good work: that is exactly the "if verification fails, the item is dropped, not guessed" behaviour the spec asked for.

D-004..D-007 all hold:

- **D-004** — `core/models.py` and `core/registry.py` are untouched since T01 (`git diff bfd8414 HEAD` on both files is empty); no surface-specific reshaping; `extra="forbid"` construction is the only path.
- **D-005** — `mapping.py:254-265` uses the anchors verbatim: 0.95 / 0.8 / 0.6 / 0.4, each with an English `confidence_basis`; identifier lookup is 1.0 with basis "exact identifier lookup in Enhetsregisteret" (`mapping.py:237-238`).
- **D-006** — key shape `"{COUNTRY}:{registry}:{kind}:{id-or-query}"` (`client.py:189`, `:252`, search key casefolded/stripped and includes `limit`); a hit sets `cached=True` and re-applies the **original** `fetched_at` (`client.py:196`, `:257`), asserted by spec test 91; `not_found` TTL is a fixed 1 h that the `REGISTRY_MCP_CACHE_TTL_SECONDS` override cannot lengthen (`cache.py:84-94`, asserted in `tests/test_cache.py:61-68`); expired rows deleted lazily on read (`cache.py:119`); every read and write is wrapped in `try/except Exception` and logged, never raised (`cache.py:133-135`, `:167-168`), with a test that points the path at a directory to prove it.
- **D-007** — every one of the six `RegistryError` constructions passes a non-empty, actionable `hint` naming the next call (`client.py:96-105`, `:111-120`, `:127-139`, `:142-163`, `:166-173`, `:176-183`, `:242-249`); the `not_found` hint is the spec's §6 sentence word for word and names `search_company`.

Spec tests 82–97 are all present and named per the spec. Done-check reproduced: `pytest tests/test_client_no.py tests/test_cache.py -q -m "not live"` → 31 passed (+1 live, excluded); `mypy .` and `ruff check .` clean.

Cache path env: `tasks/T03.md` said `REGISTRY_MCP_DB_PATH` / `./data/registry.db`, `DECISIONS.md` D-006 and `NORBIZ_SPEC.md` §9 say `REGISTRY_MCP_CACHE_PATH` / `./data/cache.sqlite3`. The implementer followed the decision over the task file — **that is the right precedence**, and `Dockerfile`/`docker-compose.yml` already set the same name. No action.

### Notes (non-blocking)

- **Test the other three D-005 anchors.** Only the 0.8 branch is exercised (`test_search_maps_hal_envelope` searches "equinor" against "EQUINOR ASA"); `mapping.py:259` (0.95 exact) and `:262-265` (0.6 token / 0.4 fallback) are uncovered. The anchors are a published contract (`static/llms-full.txt:201-203`) — three cheap unit tests on `_confidence_for_hit` close it.
- **Uncovered client paths worth one test each** (`client.py` is at 80 %): the cached-`not_found` re-raise (`client.py:194`) — that is the visible half of D-006's negative TTL; the search cache hit (`client.py:256-257`) — the `SearchResult` twin of spec test 91; and the 429 → `upstream_error` mapping (`client.py:214`, `:224`).
- **`test_97` half-asserts.** `tests/test_client_no.py:301-319`: the mandatory-field check is real and passes, but the optional-field block ends in `assert optional_top_level`, which can never fail. Either drop it or assert the types of the optional fields that *are* present in the fixture.
- **Non-`RegistryError` exceptions can escape `lookup`.** `httpx.ConnectError` (and other transport errors that are not `TimeoutException`) propagate raw out of `_fetch` (`client.py:94`), and a malformed upstream date would raise `ValueError` out of `mapping._parse_date` (`mapping.py:89-93`). Both become a bare 500 rather than one of our documented codes. Cheap fix: catch `httpx.TransportError` alongside the timeout, mapping to `upstream_error`. T06 must also have a catch-all → `internal_error` regardless.
- **The shared `AsyncClient` needs a shutdown hook.** `client.aclose()` (`client.py:78-83`) exists and `scripts/lookup_demo.py` calls it; T06 must call it from the FastAPI lifespan or the process leaks sockets. Also, the `User-Agent` is frozen at first client construction (`client.py:70-74`), so changing `REGISTRY_MCP_CONTACT_EMAIL` at runtime has no effect until `aclose()`. Fine for a server; noted for T13.
- `map_search_result` does `data.get("_embedded", {}).get("enheter", [])` (`mapping.py:319`) — safe for a *missing* `_embedded` (spec test 89) but not for an explicit `null`. `(data.get("_embedded") or {}).get("enheter") or []` is the same length and total.
- `core/cache.py` is genuinely country-neutral; the only Norwegian tokens are `"NO:brreg:…"` example strings inside docstrings (`cache.py:5-6`, `:149`). Not a D-001 violation — no action, recorded so a future reader does not re-raise it.
- T03's `NORBIZ_SPEC.md` edits (§1.1/§2/§6, the 410 finding) were swept into T05's commit `51bc016` rather than T03's own `bd0d1d6`. Content is committed and correct; noted for the orchestrator only, since a per-task revert would now touch two commits.
- `pytest.mark.live` is not registered in `pyproject.toml`, so every run prints `PytestUnknownMarkWarning`. `-m "not live"` still works (CI and this review both used it). One line — `markers = ["live: hits the real brreg API"]` under `[tool.pytest.ini_options]` — but `pyproject.toml` is being edited by T06 this round, so it should be done by whoever touches that file next, not in parallel.

## T04 — 2026-09-03 — APPROVED (light pass)

Reviewed: `.github/workflows/ci.yml`, `Dockerfile`, `docker-compose.yml`. Already marked `done`; these are notes for T13, not a re-open.

- CI runs `ruff` → `mypy` → `pytest -q --cov -m "not live"` on push and PR, which is the right order and correctly excludes the network test. `.env` is git-ignored and only `.env.example` is tracked — verified.
- **`Dockerfile:32-33` copies only `/app/.venv` and `/app/src` into the runtime stage.** `NORBIZ_SPEC.md` §15 requires `GET /`, `/llms.txt`, `/llms-full.txt` and `/server.json` to be served from the API origin; in the image those files do not exist, so all four routes 404 in production while passing locally. Add `COPY --from=builder --chown=app:app /app/static /app/static` and the root `server.json`, and set `REGISTRY_MCP_STATIC_DIR=/app/static`. Blocking for T13, not for T04 as scoped.
- CI installs with `uv sync --all-extras` rather than `--locked`, so a CI run can silently resolve dependencies that differ from `uv.lock`. Prefer `uv sync --all-extras --locked`.
- The `HEALTHCHECK` and the `uvicorn registry_mcp.api.main:app` command both depend on T06's `/health` route existing. Expected; flagged so T13 checks it rather than assuming a healthy container.

## T05 — 2026-09-03 — APPROVED with corrections required (light pass)

Reviewed: `static/llms-full.txt`, `static/llms.txt`, `server.json`. `server.json` validates against the pinned 2025-12-11 schema and its `_meta` keywords match `KEYWORDS.md`; `llms.txt` contains no factual claim that contradicts the fixtures. The `llms-full.txt` prose is genuinely good agent-facing writing — the error table, the "a search hit is enough to choose, not to act on" line and the `cached`/`fetched_at` honesty section are all worth keeping verbatim.

### Example values that contradict `tests/fixtures/brreg_923609016.json` — fix before launch

- `static/llms-full.txt:116` — `"registered_at": "1995-09-22"`. The fixture's `registreringsdatoEnhetsregisteret` is **`1995-03-12`**.
- `static/llms-full.txt:183` — the same wrong `"registered_at": "1995-09-22"` in the search-hit example.
- `static/llms-full.txt:120` — `"employees": 22000`. The fixture's `antallAnsatte` is **`21239`**. A round invented number in a document whose whole argument is "unknown is null, never 0" is the worst possible place to invent one.

Everything else checked against the fixture is right: `id_formatted`, `previous_names[0] == "STATOIL ASA"` (the API's array really is oldest-first), `share_capital 5976872600.0`, `share_capital_currency "NOK"`, the `06.100` industry code and its description, the entire `business_address` block, `vat_number "NO923609016MVA"`, `status_detail`, `confidence_basis`, and `days_until: 18` for 2026-01-15 → 2026-02-02.

### Other discrepancies with the shipped code

- `static/llms-full.txt:396-397` — the `not_found` example uses `923609017`, which **fails MOD11** and therefore returns `400 invalid_id`, never `404 not_found`; the hint beneath it says "The number is well-formed", which for that string is false. Use a well-formed unissued number (e.g. `934154150`) or state the checksum-valid property explicitly.
- `static/llms-full.txt:186` — `"confidence_basis": "name matches the query exactly (case-insensitive)"`; the code emits `"search hit name matches the query exactly, case-insensitively"` (`mapping.py:259`). Same for `:245` vs the real `applies_because` (`rules.py:546-549`) — see the T02 note, where the code is the side that should move.
- `static/llms-full.txt:323` vs `:227-250` — the MCP tool `company_deadlines` is documented as returning `list[Deadline]` while the REST twin returns an object with `today` / `deadlines` / `notes`. **D-004 requires the two surfaces to emit the same document.** There is currently no model for either that shape or the `/validate` response of `:285-294` (`formatted`, `reason`, `valid`, `normalised`). Opus A owns this: models will be added before T06/T07 freeze, and whichever shape lands, `llms-full.txt` must match it. Tracked for T10.
- Rate-limit specifics (`60/min per IP`, `details.retry_after`) and `GET /health`'s exact body are promises T06 must honour verbatim, since this file is what an agent reads first.

---

Test-suite state after this review's one owned edit (`tests/test_interface.py`, a T01 file): `uv run pytest -q -m "not live"` → **127 passed**, `uv run mypy .` clean (23 files), `uv run ruff check .` clean. The stale `test_norwegian_methods_raise_not_implemented` is replaced by `test_stub_methods_raise_not_implemented` (XX still raises `not_implemented` for `lookup`/`search`) and `test_norwegian_sync_methods_are_implemented` (NO validates and computes deadlines).

Timing note: `src/registry_mcp/api/` was being written by Sonnet 3 (T06) during this review and was not edited here. A transient `RUF022` in `api/ratelimit.py` seen mid-review is gone in T06's commit `ccbadb6`; `ruff check .` is clean repo-wide again.

## D-004 gap — closed 2026-09-03 (follow-up to §T05, at the coordinator's request)

The `list[Deadline]` vs envelope split, and the model-less `/validate` response, are resolved by **`DECISIONS.md` D-010** rather than deferred to T10, because T06 was freezing REST while this review was being written. `core/models.py` gains `DeadlineReport` and `ValidationResult`; `core/registry.py` gains the concrete `deadline_report()` / `validate()` builders and the `format_id()` hook T06 asked for (`api/main.py:160-172`). The `Registry` ABC, `registries/xx/` and `registries/no/rules.py` are untouched — a country implements the same four primitives as before. T06 drops its local `ValidateResponse`/`DeadlinesResponse` and its `_best_effort_id_format` heuristic; T07 inherits the shapes; T11 realigns `static/llms-full.txt` §3.4/§3.5/§4 (`normalised` → `normalized`, and the MCP tool no longer returns a bare list).

## T10 — 2026-09-04 — BLOCKED

Full read of `src/registry_mcp/**` plus `tests/**`, `Dockerfile`, `pyproject.toml`, `KEYWORDS.md`. Baseline for the checklist is `HEAD f030f80`, re-run against the working tree where T11/T12/T13 had already landed changes; where the two differ it is said so explicitly. Every claim below was executed, not read off.

Environment for the run: `uv run mypy .` → clean (45 source files), `uv run ruff check .` → clean, `uv run pytest -m "not live"` → **262 passed, 1 deselected** after this review's own owned edits (256 before them).

### Checklist

| # | Item | Verdict |
|---|---|---|
| 1 | Response schema identical across REST and MCP | **PASS** |
| 2 | `registries/se/` stub needs no `core/`, `api/`, `mcp/` edit | **PASS** |
| 3 | No Norwegian identifiers/constants/imports in `core/`, `api/`, `mcp/` | **PASS** (one note) |
| 4 | Every `CompanyReport` field traces to a verified brreg field or is documented as derived | **PASS** |
| 5 | Tests green on a clean checkout | **FAIL** |
| 6 | No hard-coded secrets; `.env` not tracked | **PASS** |
| 7 | Every error `hint` names a concrete next action | **PASS** (one correction applied) |
| 8 | Rate limiter and logging cannot crash a request | **PASS** |
| 9 | `mypy --strict` and `ruff` clean | **PASS** |
| 10 | Tool docstrings contain the `KEYWORDS.md` aliases | **PASS** |

---

**1. Response schema identical across REST and MCP — PASS.**

Ran all five operations through both surfaces in the same process against the same `respx`-mocked upstream and diffed the resulting documents key by key: 11 cases (`lookup` ok/invalid/not-found/unsupported-country, `search` ok/bad-limit, `deadlines` ok/bad-`today`, `validate` ok/invalid, `countries`). **Every error document is byte-identical**, and every success document is identical except `fetched_at`, which differs only because the two calls are two separate fetches minutes apart — the honest timestamp D-006 asks for, not a schema difference. `cached`, `country` and `registry` are present on every payload that carries them.

The structural reason it holds: both surfaces return `model_dump(mode="json")` of the same `core/models.py` object, and neither assembles `DeadlineReport`/`ValidationResult` itself (`api/main.py:629`, `:662`; `mcp/server.py:246`, `:270` all go through the D-010 builders on `core/registry.py:170-228`).

The one payload D-004 did **not** cover was `list_countries` — see (c) below; closed this round as **D-012**.

**2. `registries/se/` stub without touching `core/`, `api/` or `mcp/` — PASS.**

Actually added one: a 55-line `registries/se/__init__.py` (`SeRegistry`, Luhn-less ten-digit `validate_id`, `format_id` → `556021-2524`) plus **one import line** in `registries/__init__.py`. `git diff --name-only` in the clone showed exactly `src/registry_mcp/registries/__init__.py` and the new folder — no `core/`, `api/` or `mcp/` file touched, as D-008 promises. Results:

- `list_countries()` → `['NO', 'SE']`; `GET /v1/countries` → `['NO', 'SE']`; MCP `list_countries` → `['NO', 'SE']`.
- `GET /v1/SE/validate/5560212524` → `valid: true`, `formatted: "556021-2524"` — SE's own convention, inherited through `Registry.validate` → `format_id`, with no surface edit.
- `GET /v1/SE/company/…/deadlines` and MCP `company_deadlines` both returned a well-formed `DeadlineReport`.
- `mypy` and `ruff` clean with SE present (41 source files).

Stub then deleted and the import reverted; the clone is back to a clean tree.

One thing the exercise exposed, worth a follow-up but **not** a checklist failure, since the item names only `core/`/`api/`/`mcp/`: **the test suite is what a second country actually has to edit.** Ten tests failed with SE registered, seven of them because they assert an exact country list or use `SE` as the example unsupported country — `tests/test_api.py::test_unsupported_country` (uses `SE`), `::test_countries`, `::test_health`, `tests/test_interface.py::test_public_country_list_hides_stubs`, `::test_stub_country_visible_via_env`, `::test_unsupported_country_hint_lists_supported` (`assert err.details["supported"] == ["NO"]`), `tests/test_mcp.py::test_list_countries_hides_stub`, `::test_lookup_company_unsupported_country_is_json_error`, `::test_rules_resource_unsupported_country_is_json_error`. Pick an unregistrable code (`ZZ` is already used elsewhere and is ISO-reserved for private use) for the "unsupported" fixtures, and assert `"NO" in countries` rather than `== ["NO"]`. Owner: whoever adds country #2 (T15), not a T06/T07 fix now.

**3. No Norwegian in `core/`, `api/`, `mcp/` — PASS.**

Grepped all of `brreg|orgnr|organisasjonsnummer|enhetsregist|norway|norwegian|brønnøysund|bronnoysund` across the three packages. Every hit is in a docstring, a `Field(description=…)` example, an OpenAPI example payload, or an MCP tool docstring — **no identifier, no constant, no import, no branch on a country code**. `core/cache.py:148`'s `"NO:brreg:entity:923609016"` is an illustrative key in a docstring (already noted and cleared at T03). `core/rules/common.py` still takes holidays as a parameter and imports only `calendar`/`datetime`.

Note (non-blocking): `mcp/server.py` hard-codes `country: str = "NO"` as the default of four tool signatures (`:162`, `:192`, `:220`, `:251`), and their docstrings are written entirely about Norway. Both are deliberate — `KEYWORDS.md` §2 *requires* keywords 1–9 in those docstrings, and a single-country service wants a default that works. But it means `mcp/server.py` is a file country #2 must edit after all, for prose rather than for logic. Record the intent now so it is a decision later rather than a surprise: when a second country lands, the four docstrings become country-neutral with Norway as a named example, and the default either stays `"NO"` (documented as "the first module, not a preference") or goes away. No action this round.

**4. `CompanyReport` field traceability — PASS.**

All **52** model fields are set explicitly in `registries/no/mapping.py::map_entity` — checked mechanically, the set difference between `CompanyReport.model_fields` and the keyword arguments at `mapping.py:219-274` is empty. **No field silently falls back to a model default**, which is the failure mode that matters: a defaulted field looks like data.

`map_entity` reads 28 brreg keys directly; 26 of them appear in at least one committed fixture. The two that do not are `konkursdato` and `slettedato` (`mapping.py:203`, `:241-242`) — absent because all three fixtures are live, active entities, and T03 verified the deleted-entity shape live against `921084846` (`NORBIZ_SPEC.md` §1.1). Derived fields are all documented as derived: `id_formatted`/`vat_number`/`is_active` (computed), `legal_form`/`limited_liability`/`has_board_duty`/`has_annual_accounts_duty` (the `ORG_FORMS` table), `status`/`status_detail` (`derive_status`), `confidence`/`confidence_basis` (D-005), and the provenance block.

Note (non-blocking, T03): **no test drives a `slettedato`/`konkursdato` payload through `map_entity`.** `derive_status` is unit-tested thoroughly in `tests/test_rules_no.py`, but `deregistered_at` and `bankruptcy_date` never travel the mapping path in any test, so a typo in either of those two lines would ship. These are the two highest-consequence statuses in the product — a synthetic dict based on the Equinor fixture with the two dates added is one cheap test. Related, and still open from the T03 review: `tests/test_client_no.py:462`'s `assert optional_top_level` is a tautology that can never fail.

**5. Tests green on a clean checkout — FAIL. BLOCKING.**

```
git clone . <scratch>/clean && uv sync --all-extras && uv run pytest -q
→ 1 failed, 247 passed
FAILED tests/test_api.py::test_rate_limit_429_shape - assert 200 == 429
```

Not a fluke and not an artefact of the clone: **`tests/test_api.py:274-285` failed 3/3 times in the clean clone and 3/3 times in the working repo when run in isolation**, and intermittently in the full suite (failed under `pytest -q`, passed under `pytest` moments later). It is a timing race, not a logic bug. `api/ratelimit.py:33-34` sets capacity 60 and refill **1.0 token/second**, and the test fires 61 requests in a loop; if those 61 requests take longer than one wall-clock second the bucket has refilled a token and the 61st is legitimately allowed. Measured directly: 61 requests took **0.785 s** warm (→ passes) and over 1 s cold or under load (→ fails). Running the test alone is the slow case, which is why isolation fails every time.

The production limiter is fine — this is purely a test that asserts a rate limit using the real clock. Fix (**T06**): drive the middleware directly with a frozen refill instead of racing it, e.g. build a throwaway app with `RateLimitMiddleware(capacity=3.0, refill_per_second=0.0)` (both are already constructor parameters, `ratelimit.py:59-69`) and assert the 4th request is 429 plus the `Retry-After` header and the `rate_limited` envelope shape. That tests the same three things deterministically and in 4 requests instead of 61.

This is the only clean-checkout failure. `uv sync --all-extras` from the lockfile succeeded with no manual step.

**6. Secrets and `.env` — PASS.**

`git grep -iE "(api[_-]?key|secret|token|password)\s*[=:]\s*['\"][^'\"]{8,}"` → no matches (exit 1). `.env` is untracked and matched by `.gitignore:22`; only `.env.example` is committed. `.dockerignore` excludes `.env` and `.env.*` while allowing `.env.example`, so nothing secret is baked into the image either. The on-disk `.env` does hold a real `REGISTRY_MCP_ADMIN_KEY` and contact address — correctly, and correctly ignored.

**7. Every `hint` names a concrete next action — PASS**, with one correction applied.

Read all 23 `hint=` sites. Every one names a call, an endpoint, or a wait: `not_found` → "Call `search_company` with the company name"; `unsupported_country` → "Call `list_countries` (MCP) or `GET /v1/countries` (REST)" **and interpolates the currently supported list** (`core/registry.py:315-318`); `rate_limited` → "Back off for N seconds" with the number computed from the actual deficit (`api/ratelimit.py:88-95`) and mirrored into `details.retry_after` and the `Retry-After` header; `bad_request` on `today` → "Send `today` as YYYY-MM-DD, e.g. 2026-01-15"; the unknown-route 404 → "GET /llms.txt … or GET /v1/countries"; `internal_error` → retry once, then a specific issue URL. No "invalid input" anywhere.

The one violation was not in a `hint` but in the field next to it: `ValidationResult.reason` on success ended "call **lookup** to find out", and `lookup` is not a callable name on either surface. Corrected in `core/registry.py:224-229` (my file) to name `lookup_company` (MCP) and `GET /v1/{country}/company/{id}` (REST), with a test at `tests/test_interface.py::test_validate_success_reason_names_a_concrete_next_call`. See **D-013** and item (2) of the coordinator's T12 findings below.

Two follow-ups, non-blocking:
- **T03** — `registries/no/client.py:127-139`: the `not_found` hint's first sentence repeats `message` **verbatim** ("No entity with organisasjonsnummer X exists in Enhetsregisteret."), so every miss pays for the same sentence twice. `hint` should start at "The number is well-formed, so it may never have been issued or the entity may have been deleted. Call `search_company` with the company name instead." — the duplicated clause is the only text to remove; the rest is already right. (Raised by T12's content author reading real output.)
- **T08** — `core/rules/common.py:98-128`: `date.fromisoformat` on 3.12 is broader than the documented format. Verified: `today=20260115` → 2026-01-15 and `today=2026-W03-1` → 2026-01-12 are both **accepted**, while the docstring, the `Query` description (`api/main.py:613`) and the hint all promise `YYYY-MM-DD`. An agent sending an ISO week date gets a silently different answer rather than the `bad_request` the docs led it to expect. One `re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)` guard before the parse closes it.

**8. Rate limiter and logging cannot crash a request — PASS.** Fault injection run for real.

Pointed both `REGISTRY_MCP_CACHE_PATH` and `REGISTRY_MCP_LOG_PATH` at a directory with mode `0555`, then made **12 calls** across both surfaces:

```
REST /v1/NO/company/923609016            -> 200
REST /v1/NO/search?q=equinor             -> 200
REST /v1/NO/validate/923609016           -> 200
REST /v1/countries                       -> 200
REST /health                             -> 200
REST /v1/NO/company/923609016/deadlines  -> 200
REST /v1/NO/company/923609016 (repeat)   -> 200
MCP  lookup_company / search_company / validate_company_id
     / list_countries / company_deadlines -> all ok
```

Every call succeeded and no file was created in the read-only directory. The mechanism is sound rather than lucky: `core/log.py:152-175` wraps the whole insert — including `connect()`'s `mkdir` at `:129`, which is what actually raises `PermissionError` here — in one `try/except Exception` that logs at WARNING; `core/cache.py:133-135`, `:167-168` do the same for reads and writes; and both surfaces add a *second* belt at `api/main.py:96-97` and `mcp/server.py:123-124`. The repeat lookup confirms a failed cache **write** does not poison the subsequent read path. The rate limiter touches no disk at all (`api/ratelimit.py:69`, an in-process dict), so it has nothing to fail on.

**9. `mypy --strict` and `ruff` — PASS.** `uv run mypy .` → "Success: no issues found in 45 source files" (`pyproject.toml:98-105`: `strict = true`, `warn_unreachable`, `disallow_any_generics`, pydantic plugin, `packages = ["registry_mcp", "tests"]` so tests are checked too). `uv run ruff check .` → "All checks passed!". Both re-run after this review's own edits.

**10. Tool docstrings carry the `KEYWORDS.md` aliases — PASS.**

Checked mechanically rather than by eye: for each of the four Norway-facing tools, split the docstring into sentences and tested all nine required keywords (`KEYWORDS.md` §2, row "MCP tool docstrings": 1–9) against the **first two sentences**.

```
lookup_company        missing-in-first-2-sentences=[]  missing-anywhere=[]
search_company        missing-in-first-2-sentences=[]  missing-anywhere=[]
company_deadlines     missing-in-first-2-sentences=[]  missing-anywhere=[]
validate_company_id   missing-in-first-2-sentences=[]  missing-anywhere=[]
list_countries        norwegian terms present: []
```

All nine in every one of the four, inside the first two sentences as the table demands, and `list_countries` is clean of Norwegian vocabulary exactly as §3's fourth rule requires. `brønnøysund` (#2) appears as the leading substring of `Brønnøysundregistrene`, which satisfies a keyword match. The prose reads as prose, not as a keyword dump — §3's third rule holds too.

---

### Additional items ruled on this round

**(a) The `antallAnsatte` quirk — decided; recorded as D-011; assigned to T03.**

brreg omits `antallAnsatte` entirely when `harRegistrertAntallAnsatte` is `true` (fixture `833285602`, `EL ANSARI KONSULT`, `ENK`). `mapping.py:211-212` therefore emits `employees=None, employees_reported=True` — a report claiming the registry holds a figure while returning none. `core/models.py:503-506` defines the flag as exactly the opposite of that.

**Ruling: `employees` stays `None` — do not synthesise `0`** — **and `employees_reported` becomes derived**: `harRegistrertAntallAnsatte and antallAnsatte is not None`. The "omits the key when zero" reading is plausible but rests on one fixture and no upstream documentation, and D-004's rule is "unknown is `None`, never `0`". Deriving the flag instead makes `employees_reported is True ⟹ employees is not None` a real invariant — which is the only reason the field exists — and for `833285602` yields the honest `None`/`False` pair. The lost signal becomes a `notes` sentence written in `registries/no/`, per D-010's "prose about a country is written once, in that country's module". Full text in **D-011**.

No deadline impact: `registries/no/rules.py:690` already gates `payroll_report` on `employees is not None and employees > 0`, so `None` and `0` behave identically. Needs: the mapper change, a note, a companion test beside `tests/test_client_no.py:164` (which currently asserts the contradictory pair as though it were correct), and a widened `NORBIZ_SPEC.md` §2 row — spec test 88 stays true as written.

**(b) `parse_iso_date` — country-neutral: yes. Dropping `country` from the error: acceptable. PASS.**

`core/rules/common.py:98-128` takes `(value, *, field)` and returns a `date`; it imports only `calendar`/`datetime` and `core.models`, branches on nothing national, and hard-codes no locale, calendar or format beyond ISO-8601. It is correctly country-neutral, and folding T06's and T07's two verbatim copies into it is the right call — I verified the payoff directly, in item 1: the `deadlines badday` case is now byte-identical across REST and MCP, which two independently maintained copies would not have stayed.

Dropping `country` from the `bad_request` envelope is **acceptable**. D-007 lists `country` as optional; the failure is about a malformed query parameter, not about a country; and the hint still names the field and the format, which is the part an agent acts on. If it is ever wanted back it is a `country: str | None = None` keyword away, and both call sites already have the value in hand — but it buys nothing today and is not worth the churn.

Two smaller observations, neither blocking: the leniency of `date.fromisoformat` (item 7 above, owner T08); and that a request-parameter parser sitting in `core/rules/common.py` — a module whose docstring says "date helpers shared by every registry's **deadline rules**" — is a slightly odd fit, since it is request validation rather than rule arithmetic. Not worth moving now; worth a sentence in that module's docstring so the next reader is not surprised.

**(c) `list_countries` has no core model — decided: yes, add it. Added; recorded as D-012.**

This was not merely a missing model, it was a **latent divergence with no test to catch it**. `api/main.py:169-184`'s private `RegistryInfo` is a plain `BaseModel`, so pydantic's default *drops* an unrecognised key, while `mcp/server.py:290` passes `dict(r.describe())` straight through and *keeps* it. The first attribute anyone adds to `Registry.describe()` would have made `/v1/countries` and `list_countries` disagree by omission, silently — which is precisely the failure D-004 exists to prevent.

Added to `core/models.py` (my file): **`CountryInfo`** (the nine `describe()` values, `extra="forbid"`, `country` upper-cased) and **`CountriesResponse`** (`countries: list[CountryInfo]`). Added to `core/registry.py` (my file): the concrete builder **`Registry.country_info()`**, with `describe()` kept byte-for-byte identical but now derived from it — so **`api/` and `mcp/` keep working untouched and nothing is red**. Five tests in `tests/test_interface.py` cover it, including one asserting an unknown key now raises on the shared model.

The surfaces adopting it are two mechanical edits, listed in **D-012** with line numbers: **T06** `api/main.py:169-184` + `:498`, **T07** `mcp/server.py:289-291`. Both are optional-in-principle and recommended-in-practice: until they land, the divergence is closed by construction (one builder) but not enforced at the surface (`RegistryInfo` still drops extras).

**(d) Dockerfile `static/` + `server.json` — FIXED by T13, confirmed.**

`Dockerfile:43-44` now copies `/app/static` and `/app/server.json` into the runtime stage, and `:49` sets `REGISTRY_MCP_STATIC_DIR=/app/static`. Verified the path logic agrees with the image layout: with that env var set, `_static_dir()` → `/app/static` and `_server_json_path()` → `/app/server.json` (`api/main.py:114-123` derives `server.json` from the static dir's *parent*, which is why the two `COPY` targets have to be siblings — they are). The T04 finding is closed. T13 also left a good comment at `:35-42` explaining why the env var is set even though the fallback would already work.

**(e) `/mcp` mount and lifespan composition — FAIL on client shutdown. BLOCKING.**

Three findings, one of them a production bug that T13 found and fixed while this review was running.

- **The registry's HTTP client is never closed.** Measured: after the FastAPI lifespan exits, `registries.no.client._client.is_closed` is still `False`. `_close_registry_clients` (`api/main.py:376-403`) probes `getattr(reg, "aclose", None)` and `BrregRegistry` has no such attribute (`hasattr(get_registry("NO"), "aclose")` → `False`), so the loop finds nothing and the `httpx.AsyncClient` at `client.py:67-75` is dropped rather than closed — sockets leak on every restart. `client.py:78-83`'s module-level `aclose()` exists and is called by nothing. The function's own docstring diagnoses this correctly and at length; what it could not do is fix the interface. **Closed as D-014**: `Registry.aclose()` is now a concrete no-op on the ABC (my file, landed, breaks nothing, inherited by `xx/` and every future country), so the probe has a real method to find. **T03 must add the three-line override** on `BrregRegistry` delegating to `client.aclose()`.
- **Cleanup is not in a `finally`.** `api/main.py:405-410`: `await _close_registry_clients()` sits *after* the `async with _mcp_app.lifespan(_app)` block. If shutdown raises — including from the MCP session manager's own `__aexit__` — cleanup is skipped entirely. Wrap the `yield` in `try/finally`. **T06.**
- **Ordering itself is correct.** `_warn_if_static_missing()` runs first (and only warns — a missing homepage cannot stop the boot, `:142-154`), then the MCP session-manager lifespan wraps the app's whole lifetime, then registry cleanup. Verified working end to end: `POST /mcp` with a real `initialize` handshake returns 200 with a valid JSON-RPC result, which means the composed lifespan really did start the session manager — the failure mode if it had not.

**T13's `/mcp` route fix — correct, important, and out of its stated scope.** T13 replaced `app.mount("/mcp", _mcp_app)` with two exact `Route`s registered directly (`api/main.py:365-410` in the working tree). The diagnosis is right and I confirmed both halves by measurement:

```
HEAD f030f80 (Mount):      POST /mcp  -> 307      POST /mcp/ -> 200
working tree (two Routes): POST /mcp  -> 200      POST /mcp/ -> 200
```

A Starlette `Mount` compiles to `<path>/{path:path}` and never matches the bare mount path; a bare `POST /mcp` only ever worked via the redirect-slash fallback, and Streamable HTTP clients do not follow a POST redirect. Since `server.json`, `static/llms.txt`, `README.md` and the articles all advertise the URL **without** a trailing slash, this would have failed for a real agent while passing every local check — my own earlier probe returned 200 precisely because `TestClient` follows redirects by default. Good catch, and the fix is the right shape.

Two conditions on it: (i) it lands in **T06/T07's** files and rewrites T07's mounting strategy, so it needs their sign-off rather than arriving through the deploy task; (ii) **there is no test.** `grep` finds no test referencing `/mcp` at all. A regression test asserting `POST /mcp` returns **200 and not 307** with `follow_redirects=False` is mandatory before launch — without it the next refactor silently restores a bug that no local check catches. Owner: **T07**.

**(f) `mcp/server.py` docstrings vs `KEYWORDS.md`** — see item 10. PASS, verified mechanically, nothing to fix.

**(g) Fault injection and clean clone** — both run for real; see items 8 (PASS) and 5 (FAIL).

---

### Fix list

**BLOCKING** — must land before T14:

| # | Owner | File:line | What |
|---|---|---|---|
| B1 | **T06** (Sonnet 3) | `tests/test_api.py:274-285` | `test_rate_limit_429_shape` races the real clock and fails on a clean checkout (3/3 in the clone, 3/3 in isolation here). Rebuild it on `RateLimitMiddleware(capacity=3.0, refill_per_second=0.0)` — both are already constructor params (`api/ratelimit.py:59-69`) — and assert the 4th request is 429 with `Retry-After` and the `rate_limited` envelope. Item 5. |
| B2 | **T03** (Sonnet 2) | `src/registry_mcp/registries/no/__init__.py` | Add `async def aclose(self) -> None` delegating to `registries/no/client.py::aclose()` (`client.py:78-83`), in the same lazy-import style as the other five delegates. Without it the `httpx.AsyncClient` is never closed — measured `is_closed = False` after shutdown. The ABC hook now exists (D-014). Item (e). |
| B3 | **T06** (Sonnet 3) | `src/registry_mcp/api/main.py:405-410` | Wrap the `yield` in `try/finally` so `_close_registry_clients()` runs even when shutdown raises. Item (e). |
| B4 | **T07** (Sonnet 3) | `tests/test_mcp.py` | Regression test for T13's `/mcp` route fix: `POST /mcp` with `follow_redirects=False` must be **200, not 307**, and `POST /mcp/` likewise. At HEAD the first was 307 and no test noticed. Also sign off on T13's rewrite of the mount, which lands in T06/T07's file. Item (e). |

**Before launch, not blocking T11–T13** — data honesty and contract cleanup:

| # | Owner | File:line | What |
|---|---|---|---|
| N1 | **T03** | `registries/no/mapping.py:211-212` | **D-011**: `employees_reported = harRegistrertAntallAnsatte and antallAnsatte is not None`; `employees` stays `None`. Add the `notes` sentence, a test beside `tests/test_client_no.py:164`, and widen `NORBIZ_SPEC.md` §2's row. |
| N2 | **T03** | `registries/no/client.py:127-139` | `not_found` hint repeats `message` verbatim — drop the duplicated first sentence. |
| N3 | **T06** | `api/main.py:334` | `_VALIDATE_EXAMPLE`'s `"reason"` shows a string the code never emits; `/openapi.json` is crawled. Use the real sentence (D-013). |
| N4 | **T06** | `api/main.py:169-184`, `:498` | **D-012**: drop the private `RegistryInfo`/`CountriesResponse`, use `core.models.CountriesResponse` and `r.country_info()`. |
| N5 | **T07** | `mcp/server.py:289-291` | **D-012**: return `CountriesResponse(...).model_dump(mode="json")` instead of a hand-built dict. |
| N6 | **T08** | `core/rules/common.py:98-128` | Reject what the docs reject: guard with `\d{4}-\d{2}-\d{2}` so `20260115` and `2026-W03-1` are `bad_request` rather than silently accepted. |
| N7 | **T11** | `static/llms-full.txt:332` | The success `reason` string changed (D-013) — realign along with the `normalised`→`normalized` and `list[Deadline]` fixes D-010 already assigned. |
| N8 | **T03** | `tests/test_client_no.py` | No test drives a `slettedato`/`konkursdato` payload through `map_entity`; `deregistered_at`/`bankruptcy_date` are untested on the mapping path. Also `:462`'s `assert optional_top_level` is still the tautology flagged at T03. |

**Recorded, no action now:** the seven tests that hard-code the country list (item 2 — for T15); `country: str = "NO"` and Norway-specific prose in `mcp/server.py` (item 3 — for T15); REST does not log `unsupported_country` or a malformed `today` because both raise before the `try` (`api/main.py:531`, `:617-618`) while MCP logs them inside `_call_context` — a small asymmetry in `/v1/stats`, harmless today; `api/stats.py:48` and `api/dashboard.py` compare the admin key with `!=` rather than a constant-time compare, and take it as a query parameter, so it lands in access logs — fine for an admin/debug route on a single instance, worth `hmac.compare_digest` if it ever moves; `RateLimitMiddleware` is a `BaseHTTPMiddleware` and now also governs `/mcp`, so MCP traffic shares the 60/min IP budget — intended, but say so in `deploy.md` since a proxied deployment collapses every agent onto one IP.

### Owned edits made during this review

`core/models.py` (+`CountryInfo`, `CountriesResponse`), `core/registry.py` (+`country_info()`, +`aclose()` hook, `describe()` now derived, `validate()`'s success `reason` names a real call), `tests/test_interface.py` (+6 tests), `DECISIONS.md` (D-011…D-014). Nothing outside my owned files was touched. After them: `mypy` clean (45 files), `ruff` clean, `pytest -m "not live"` → **262 passed**.

### T10 addendum — 2026-09-04, later the same session: B1 and B4 already landed

T13 fixed two of the four blockers while this review was being written; both verified here after the fact, so the fix list is down to **B2 and B3**.

- **B1 closed.** `tests/test_api.py:276-312`: `test_rate_limit_429_shape` now freezes the limiter's clock — a `_FrozenClock` with `monotonic() → 0.0` monkeypatched over `api/ratelimit.py`'s module-level `time` name, which pins refill at exactly zero so the bucket depletes on request count alone. Also switched from a hard-coded IP to the per-test `ip` fixture, ruling out bucket carry-over. Re-ran 3× **in isolation** — the case that failed 3/3 before — now 3/3 green. This is a better fix than the one I proposed (it keeps the test exercising the real middleware on the real app instead of a throwaway one).
- **B4 closed.** `tests/test_mcp.py:274-305`: `test_mcp_mount_has_no_trailing_slash_redirect`, parametrised over `/mcp` and `/mcp/`, with `TestClient(app, follow_redirects=False)` and an explicit `assert resp.status_code != 307` alongside the `== 200`. Exactly the regression guard the finding asked for, and the comment records why (Streamable HTTP clients do not follow a POST redirect; every advertised URL omits the trailing slash). 3/3 green.

**Still blocking: B2** (`BrregRegistry.aclose()`, T03) and **B3** (`try/finally` around the lifespan `yield`, T06). Both are in item (e) and neither is touched by T13's changes — the client is still not closed on shutdown.

Suite after all of the above, working tree: `mypy` clean (45 files), `ruff` clean, `pytest -m "not live"` → **264 passed, 1 deselected**.

### T10 sign-off — 2026-09-04 — APPROVED

Sign-off pass over `686de84..HEAD` (`7eba739`). Every item re-verified by execution, not by reading the diff. Working tree clean, nothing committed or edited here.

**Gates at `7eba739`:** `uv run mypy .` → clean (45 source files) · `uv run ruff check .` → clean · `uv run pytest -q -m "not live"` → **273 passed, 1 deselected**.

**Clean checkout re-run (closes item 5):** fresh `git clone` of `7eba739` + `uv sync --all-extras` + `uv run pytest -q` → **274 passed, 3 runs out of 3**. `tests/test_api.py::test_rate_limit_429_shape` also re-run **in isolation** 3/3 green — the exact case that failed 3/3 before. Item 5 flips **FAIL → PASS**.

#### Blockers

| | Commit | Status |
|---|---|---|
| **B1** — flaky rate-limit test | `7eba739` | **CLOSED.** `tests/test_api.py:276-312`: a `_FrozenClock` monkeypatched over `ratelimit`'s module-level `time` pins refill at zero, so the bucket depletes on request count alone; switched to the per-test `ip` fixture. 3/3 in isolation, 3/3 in a clean clone. |
| **B2** — registry client never closed | `79b18bd` | **CLOSED.** `registries/no/__init__.py:77-89` overrides `aclose()`, lazy-importing `client` and awaiting `client.aclose()`. Measured: `registries.no.client._client` is `None` after the app's lifespan exits — previously `is_closed = False`. |
| **B3** — cleanup outside `finally` | `7eba739` | **CLOSED.** `api/main.py:420-430` wraps the `yield` in `try/finally`. Verified by injecting a lifespan that raises on `__aexit__`: the `RuntimeError` still propagates *and* `_close_registry_clients()` ran. Also `:363-378` now `await reg.aclose()` on every registry unconditionally — a real interface call, no `getattr` probe, `inspect` import dropped. |
| **B4** — `/mcp` redirect regression test | `7eba739` | **CLOSED.** `tests/test_mcp.py:274-305`, parametrised over `/mcp` and `/mcp/` with `follow_redirects=False` and an explicit `!= 307`. Re-measured live: both paths **200**. |

#### N1–N8

| | Commit | Status |
|---|---|---|
| **N1** employees invariant (D-011) | `79b18bd` | **CLOSED.** `mapping.py:210-224` derives `employees_reported = employees_flag and employees is not None`, never synthesises `0`, and appends the D-011 `notes` sentence. Two tests, including `test_employees_reported_invariant_implies_employees_not_none` over all three fixtures. `NORBIZ_SPEC.md` §1.1 and the §2 rows updated; spec test 88 still passes unchanged. |
| **N2** `not_found` hint duplication | `79b18bd` | **CLOSED.** `client.py:127-140` — hint now carries only the next action. `NORBIZ_SPEC.md` §6 and `llms-full.txt:475` realigned (`a46652c`). |
| **N3** `_VALIDATE_EXAMPLE` | `7eba739` | **CLOSED.** `api/main.py:318-325` now shows the string the code actually emits. |
| **N4/N5** D-012 adoption | `7eba739` | **CLOSED.** Private `RegistryInfo`/`CountriesResponse` deleted; `api/main.py:519` and `mcp/server.py:289-291` both build `core.models.CountriesResponse` from `r.country_info()`. |
| **N6** strict `YYYY-MM-DD` | `7eba739` | **CLOSED.** `core/rules/common.py:99-142` guards with `\A\d{4}-\d{2}-\d{2}\Z`. Re-measured: `20260115` and `2026-W03-1` are now `bad_request` on **both** surfaces, identically. |
| **N7** `llms-full.txt` | `37939e3`, `a46652c` | **CLOSED.** Validate `reason`, the `not_found` hint, and the `/v1/countries` example (now with `is_stub` and a "MCP `list_countries` returns this identical document" line) all match live output. |
| **N8** deleted/bankrupt mapping tests | `79b18bd` | **CLOSED.** Four new tests drive `slettedato`/`konkursdato` payloads through `map_entity`, covering `deregistered_at`, `bankruptcy_date`, deleted-wins precedence, and no-deadlines-for-either. |

#### Independent re-verification

- **Item 1 (parity) — still holds, now broader.** Re-ran the full REST-vs-MCP harness at `7eba739` with **13** cases (added the two N6 rejections): **all 13 byte-identical**, `fetched_at` excluded. `list_countries` is now identical *by construction* rather than by coincidence, which is the D-012 payoff.
- **Item 8 (fault injection) — still holds.** Both `REGISTRY_MCP_CACHE_PATH` and `REGISTRY_MCP_LOG_PATH` on a `0555` directory: **12/12** calls succeeded across both surfaces, 0 files created.
- **Item 10 (keywords) — still holds.** All 9 required aliases in the first two sentences of each of the four Norway tools; `list_countries` still free of Norwegian vocabulary after its D-012 rewrite.

#### Still open — non-blocking, for T14 / `HUMAN_TODO.md`

- **`fastmcp>=2.0` is unpinned while 4.0.2 is what runs**, and `api/main.py:381-395` now depends on fastmcp internals: `fastmcp.server.http.StarletteWithLifespan`, and the assumption that `http_app()` exposes **exactly one** `StarletteRoute`. That assumption is a tuple-unpack at module scope (`:391`, executed via `:447`), so a future fastmcp emitting zero or two routes raises `ValueError` **at import** and the whole app fails to boot — not just `/mcp`. Compounded by CI running `uv sync --all-extras` without `--locked` (the T04 note, still open), so CI can resolve a version the lockfile never saw. An upper bound (`fastmcp>=2,<5`) plus `--locked` in CI is the cheap insurance; the route trick itself is fine and well-commented.
- **N1's reverse case is now unguarded.** `mapping.py:211` reads `antallAnsatte` unconditionally, so a payload with `harRegistrertAntallAnsatte: false` *and* a count present would yield `employees=<n>, employees_reported=False` — the D-011 invariant holds in the direction that matters, but not symmetrically. Unreachable with any observed brreg payload (the flag exists precisely to say whether a count was registered), and arguably the more honest reading of such a payload anyway. Recorded so it is a known shape, not a surprise.
- Unchanged from the main T10 section: the seven tests that hard-code the country list (T15), `country: str = "NO"` and Norway-specific prose in `mcp/server.py` (T15), REST not logging pre-`try` failures that MCP does log, and the non-constant-time admin-key compare in `api/stats.py` / `api/dashboard.py`.

**Verdict: APPROVED.** All four blockers and all eight pre-launch items are closed and verified. T10 unblocks T14.

---

## T15e — 2026-09-04 — BLOCKED (one blocking fix; everything else approved)

Full read of `src/registry_mcp/registries/gb/{__init__,client,mapping,rules}.py` (1,643 lines), `tests/test_rules_gb.py`, `tests/test_client_gb.py`, the one import line in `registries/__init__.py`, `scripts/lookup_demo.py`, and `git diff -- tests/`, against `UK_SPEC.md`, D-015/D-016/D-017 and the numbered test list of §14. Every claim below was executed, not read off.

Environment: `uv run pytest -q -m "not live"` → **391 passed, 5 deselected** (273 before GB). `uv run mypy .` → clean, 52 source files. `uv run ruff check .` → clean. Live GB (`-m live`, real `COMPANIES_HOUSE_API_KEY`) → **4 passed** — including test 109, which re-fetches all twelve company fixtures and diffs the mapped report, so the register has not drifted under us. (`ruff format --check` reports 23 files needing reformatting, but that is repo-wide and pre-existing; CI runs `ruff check`, not `ruff format` — `.github/workflows/ci.yml:29-35`. Not a finding against T15b.)

### Checklist

| # | Item | Verdict |
|---|---|---|
| 1 | Zero edits to `core/`, `api/`, `mcp/` | **PASS** |
| 2 | Every §1.6 trap handled (8 of 8) | **PASS** |
| 3 | D-015 identifier rules exactly | **PASS** |
| 4 | D-016 deadline policy (rules layer) | **PASS** — but see 8 for the delivery path |
| 5 | Client: auth, bucket, 429/401, key at call time, D-006, `aclose` | **PASS** (two nits) |
| 6 | Spec tests 1–109, one per number, live tests marked | **PASS** |
| 7 | REST ≡ MCP for GB; `/v1/countries` shows `requires_api_key` | **PASS** |
| 8 | **The architectural finding — `deadlines()` via the raw cache** | **FAIL — BLOCKING** |
| 9 | Suite, mypy, ruff, live tests, independent verifier | **PASS** (verifier: 42/45, adjudicated below) |
| 10 | Time vs the ≤2-week target | **PASS** |

---

**1. Zero edits to `core/`, `api/`, `mcp/` — PASS.**

`git diff --stat` on the working tree: `PROGRESS.md`, `scripts/lookup_demo.py`, `src/registry_mcp/registries/__init__.py` (+1 line), `tests/test_api.py`, `tests/test_interface.py`, `tests/test_mcp.py`; untracked `src/registry_mcp/registries/gb/`, `tests/test_rules_gb.py`, `tests/test_client_gb.py`. Not one file under `core/`, `api/` or `mcp/`. The verifier's own leak grep over those three trees found no GB-specific code. D-001 and D-008 hold on their second real test: **country #2 was one folder plus one import line**, exactly as claimed — and the two `core/` changes it did need (D-017) had already been made by the architect before T15b started.

`scripts/lookup_demo.py` is now country-generic (`--country`) and switched from `registries.no.client.aclose()` to `registry.aclose()`, which is D-014 being used the way it was meant to be. The seven suite tests that hard-coded the country list are updated and `test_unsupported_country` moved `SE` → `ZZ` — the T10 carry-over, closed.

**2. Every §1.6 trap handled — PASS, 8 of 8.**

| §1.6 | Trap | Where handled | Evidence |
|---|---|---|---|
| 1 | `has_charges` boolean, **not** `links.charges` | `mapping.py:130-133` | `map_registers` reads only the two booleans; the live TESCO payload has `links.charges` present and `has_charges: false`, and `registers["charges"]` comes back `False` (verified directly; test 78). The single most important mapping test in the file, and it is right. |
| 2 | `"null"` as a four-character string in `last_accounts.type` | `mapping.py:157-160` | The field is never read — `_last_annual_accounts_year` reads `period_end_on`/`made_up_to` only. `ch_FC032315.json` maps without raising (test 86). Avoidance is the correct handling here, per §15. |
| 3 | Zero-padded ARD **strings** (`{"day": "26", "month": "02"}`) | `rules.py:475` | `accounting_reference_date` is never read at all; the computed rung runs from `next_accounts.period_end_on`. No `int()` coercion is needed because no comparison is made. Test 55 pins it on TESCO, the 52/53-week filer whose ARD drifts from its period end. |
| 4 | Address components individually optional | `mapping.py:78-107` | Every component via `.get()`; a missing object → `None`, not an empty `Address`. `ch_SC090312.json` → `city is None`, `country_code is None` (test 80). |
| 5 | `premises` in search but not the profile | `mapping.py:89` | `premises` is in the `lines` list between `po_box` and `address_line_1`, so `one_line()` renders the same string from either endpoint. |
| 6 | `company_status` absent from a search item | `mapping.py:353` | `item.get("company_status")` → `derive_status` → `UNKNOWN` (test 92). No `KeyError`. |
| 7 | 11-key CIO / registered-society stubs | `mapping.py:140-144`, `227-232` | `_is_stub_profile` keys off *both* `company_status` and `date_of_creation` being absent. `CE020555` and `RS007790` both map, both come back **not ACTIVE** (`UNKNOWN`), both carry the stub note plus (respectively) the external-registration-number and `partial_data_available` sentences. Verified independently. Nothing infers `ACTIVE` from an absent status — the one thing §2.2 said not to do. |
| 8 | `items_per_page` capped at 100; API validates neither `q` nor the limit | `client.py:347-367` | 1..100 raises `bad_request` outside the range; a whitespace-only `name` raises `bad_request` (test 103). |

Two more that §1.6 does not number but the spec turns on, both handled: **`open` → `ACTIVE`** for `uk-establishment` (`rules.py:324`; `ch_BR026263.json` verified → `ACTIVE`, `is_subunit True`, `parent_id "FC041146"`), and **`has_insolvency_history` never a status** (`rules.py:361-403` derives from `company_status` alone; `ch_04374209.json` → `UNDER_LIQUIDATION`, never `BANKRUPT`; an *active* company with insolvency history stays `ACTIVE` and gets the §2.1 note, `mapping.py:201-206`). **`date_of_cessation` never drives status** — it reaches `derive_status` only as a formatting argument for the detail sentence (`rules.py:385-388`) and maps to `deregistered_at` (`mapping.py:286`), which is exactly the §8 reading.

The implementer also found a ninth discrepancy the spec missed, and reported it rather than papering over it: `ch_BR026263.json` and the stub profiles omit `has_charges`/`has_insolvency_history` **entirely**, not merely as `false`. `map_registers`'s `bool(data.get(...))` already gives `False`, which §2 explicitly prescribes ("absent booleans map to `False`, not `None`"). Correct, and correctly escalated.

**3. D-015 identifier rules exactly — PASS.**

`rules.py:92-122` is the §5.1 algorithm verbatim and in order: strip `[\s.\-/]`, upper-case, VAT check *before* padding, then the two padding shapes, then the four-part accept test. Tests 1–25 all present and green. Spot-checked independently: `"1234"`→`"00001234"`, `"sc123456"`→`"SC123456"`, `"oc303675"`→`"OC303675"`, `" 00445790 "`→`"00445790"`; `""`, `"12345678901"`, `"ABCDEFGH"` all rejected with a hint.

The two rules that were most likely to be got wrong are both right. **The prefix table is not a gate** — `COMPANY_TYPES` and §5.1.2 are never consulted by `validate_crn`, and `"QQ000001"` is accepted (test 25). That is the rule that stops us turning a real company into an `invalid_id` the day Companies House adds a prefix. And **nothing truncates**: `"123456789"` and `"SC1234567"` raise rather than being cut to 8 (tests 18, 19). `UK` is rejected — `get_registry("UK")` raises `unsupported_country` (verified), no alias table anywhere.

**4. D-016 deadlines — PASS at the rules layer.**

`rules.py:449-619` implements both ladders exactly. Published beats computed: `next_accounts.due_on` → `accounts.next_due` (rung 2 labels itself "from the deprecated `accounts.next_due` field") → `period_end_on` + 9/6 months → nothing plus a note. Confirmation: `next_due` → `next_made_up_to` + 14 days → nothing plus a note. Only two kinds. Only when `status is ACTIVE` (`:600`), plus the sub-unit gate (`:602`) and the D-009(a) unclassified-form gate (`:604`), so `ch_00000006.json` (dissolved, and still carrying `next_accounts.due_on`) returns `[]` — verified independently. **No roll-forward anywhere**: `statutory_date == due_date` and `rolled_forward=False` are literals at `:508-510` and `:568-570`, there is no `holidays.py`, and `roll_forward` is never imported (`rules.py:36` imports `add_months` only). `days_until < 0` is allowed and is the authoritative overdue signal; the §5.4.1 disagreement note fires only when the upstream flag and our arithmetic actually disagree (`:496`, `:556`).

**TESCO's due dates equal Companies House's own `next_due` — confirmed.** `{2027-08-26, 2027-07-02}` out of `rules.deadlines_for` equals `{accounts.next_due, confirmation_statement.next_due}` read straight off `ch_00445790.json`. The five §1.5 arithmetic proofs each have a test (53–57), including the DELOITTE month-end clamp (31 May + 9 months → 28 Feb 2027) and TESCO's 6-month plc rule computed from `period_end_on` rather than the string-valued ARD.

The one thing the ladder cannot do today is *reach* this code reliably. That is item 8.

**5. Client — PASS, two nits.**

Basic auth with the key as username and an empty password (`client.py:242`, `httpx.BasicAuth(api_key, "")`), asserted by decoding the header (test 96). Token bucket capacity 600, refill 2.0/s, 2 s max wait → `rate_limited` (`client.py:101-143`); it holds its lock only across the token arithmetic, never across the HTTP call, so concurrent lookups of different companies are not serialised (test 105). 429 → `rate_limited` with `Retry-After` if present, else the `x-ratelimit-reset` epoch rendered as a wait, else "about five minutes" (`:199-218`), and never retried (test 100). 401 **and** 403 → `upstream_error` naming `COMPANIES_HOUSE_API_KEY` and the free-signup URL (`:169-180`), not retried. The key is read inside the request path (`:236-238`) and the no-key error is raised **before a socket is opened** — test 94 asserts the mock's call count is 0, and test 95 asserts that importing the package with the variable unset succeeds and still registers `GB`. Upstream error bodies are never echoed: the 404 handler lifts only `request_id` into `details` and writes our own message and hint (`:183-196`, `:303-312`), per D-007. Test 104 drives a 401 and a timeout with a recognisable key and asserts it appears in no log record, no message and no `to_dict()`. D-006 semantics come from the shared `core/cache.py` (24 h ok / 1 h `not_found` fixed, original `fetched_at` preserved on a hit — test 102). `aclose` is overridden on the registry and delegates to the module-level client (`__init__.py:82-90`), with its own test.

Nit **N-1**: `_bucket.acquire()` is called once at `client.py:240`, *outside* the retry loop, so a retried attempt does not spend a second token. §6 says "one token per HTTP attempt (the retry costs a second token)". Immaterial against a 600-token budget, but it is a deviation from a written rule; move the `acquire()` to the top of the `while True` body.

Nit **N-2**: this module caches the **raw upstream JSON** while `registries/no/client.py` caches the mapped report. Each country owns its own cache format, so this is not a violation — and raw is arguably the better call, since a mapping fix then applies to entries already cached. Keep it. What must not survive is using that cache as a *transport* (item 8).

**6. Spec tests 1–109 — PASS.**

All 109 numbers present, one function per number, named `test_NN_<slug>`: 1–72 in `tests/test_rules_gb.py`, 73–105 in `tests/test_client_gb.py`, 106–109 in the same file and all four `@pytest.mark.live` (plus one extra `test_101b`, and six unnumbered extras covering `aclose`, `format_id`, `validate`, `rules_markdown` and the type table). None skipped, none merged, none stubbed.

The tests live in `tests/test_rules_gb.py` / `tests/test_client_gb.py` rather than §14's `tests/gb/test_{rules,mapping,client}.py`. That follows the repo's existing `test_rules_no.py` / `test_client_no.py` convention instead of the spec's, which is the right call — my spec was wrong to invent a second layout for the second country. No action.

**7. REST ≡ MCP parity for GB — PASS.**

`tests/test_mcp.py:305-336` adds `test_rest_and_mcp_lookup_company_are_identical_gb`, which drives the same `respx`-mocked TESCO payload through `GET /v1/GB/company/00445790` and the MCP `lookup_company` tool in one process and asserts the two documents are equal except `fetched_at`. That is the D-004 guarantee re-proved on the country whose surfaces have a second thing to agree on. `test_list_countries_gb_requires_api_key` pins `requires_api_key: true` / `api_key_env: "COMPANIES_HOUSE_API_KEY"` for GB and `false` / `null` for NO, and `test_rest_and_mcp_list_countries_are_identical` carries it to REST. Confirmed live against the app: `GET /v1/countries` returns the GB row with both keys populated. D-017 works end to end.

Still open for **T15c**, unchanged from D-017 and not T15b's to fix: `api/main.py:185 _COUNTRIES_EXAMPLE` and the `/v1/countries` example in `static/llms-full.txt` both still advertise fewer keys than the endpoint returns.

**8. The architectural finding — FAIL, BLOCKING. Ruled on in D-018.**

The implementer's report is accurate and the escalation was exactly right; the workaround is not shippable. `CompaniesHouseRegistry.deadlines(report, today)` (`__init__.py:76-79`) calls `client.raw_for(report.id)`, which is a **synchronous SQLite read** (`client.py:325-338`) of the entry `lookup` last wrote. The ABC's contract says the opposite in as many words: "`validate_id` and `deadlines` are sync and **pure: no I/O, no clock reads**" (`core/registry.py:25-26`).

It is not a style objection. Reproduced:

```
$ REGISTRY_MCP_CACHE_DISABLED=1 uv run python -c "... map_entity(ch_00445790) ; reg.deadline_report(report, 2026-09-04)"
cache disabled -> deadlines: []
```

TESCO PLC — active, with both due dates sitting in the payload the report was built from — yields **zero deadlines and zero notes**. `core/models.py:396-398` calls that exact shape out: "An empty list is a real answer, not an error — read `notes` for why", and here `notes` is empty too, because the notes were computed at map time from the raw payload and correctly found nothing to say. So the failure is silent and indistinguishable from "this company has nothing to file". A wrong answer, with no signal, on the one feature that differentiates the product.

The triggers are not exotic. `REGISTRY_MCP_CACHE_DISABLED=1` is a documented, supported configuration (§9). Worse, §9 also requires that "a cache failure is logged and ignored, never turned into a `RegistryError`" — so an unwritable cache directory, which T10 item 8 fault-tested precisely because it must degrade gracefully, now degrades into *wrong deadlines* instead of a slow request. Add a read-only container filesystem, or a 24 h entry that expires between two REST calls, and the same hole opens.

Every test missed it for one reason, and it is worth naming: `tests/test_client_gb.py:59` deletes `REGISTRY_MCP_CACHE_DISABLED` from the environment in an autouse fixture, so no GB test can ever exercise the cold path, and `test_deadline_report_via_registry_uses_published_dates` (`:513`) passes only because the cache is warm. The orchestrator's verifier, which runs outside pytest, caught it on its first attempt.

**The ruling: D-018.** The abstraction was wrong, not the implementer. `Registry.deadlines(report, today)` is right to be pure; what was missing is that `CompanyReport` had no way to carry the *register's own* published dates from lookup to deadlines. Norway derives everything from statute, so the first country never needed it; Britain publishes its dates, so the second country did. That is the country-neutral shape of the problem, and the guide's Step 12 signal — fix `core/` before country three, not after.

`core/models.py` now carries `PublishedDeadline` and `CompanyReport.published_deadlines: list[PublishedDeadline]` (default `[]`). I made that change; `registries/no/` and `registries/xx/` are untouched and green (391 passed, mypy and ruff clean with it in). The exact `registries/gb/` edits that remove the workaround are listed under "Fix list" below and owned by the T15b implementer — I have deliberately not made them.

Also ruled: **the NO-vs-GB 429 inconsistency**, as **D-019**. GB's `rate_limited`/429 (`registries/gb/client.py:212-218`) is correct and Norway's `upstream_error`/502 (`registries/no/client.py:167-175`) is the bug — `ErrorCode.RATE_LIMITED` exists, maps to 429 in `core/models.py:774`, and tells an agent to wait rather than to treat the register as broken. No test pins Norway's current behaviour, so it is a three-line fix.

**9. The runs — PASS. The independent verifier: 42/45, and all three disagreements adjudicated.**

`uv run python .../verify_gb.py` (run with `REGISTRY_MCP_CACHE_DISABLED=1`) reports **42/45 checks passed**. Of the three failures:

- *"Tesco has_charges False (not links.charges)" — the verifier is wrong.* It reads `report.has_charges`, which is not a field on `CompanyReport`; §2 maps the boolean into `registers["charges"]`. Checked directly: `registers == {"charges": False, "insolvency": False}` on a payload that does carry `links.charges`. The implementation is right; the verifier should assert `report.registers["charges"] is False`.
- *"validate bad 'SC12-34' → valid False" — the verifier is wrong.* §5.1 step 1 strips `-` before anything else (test 7 pins `"0044-5790"` → `"00445790"`), so `"SC12-34"` normalises to `"SC001234"`, which is a well-formed CRN. Accepting it is the specified behaviour. The verifier should use a string that survives stripping, e.g. `"SC12#456"` (test 22).
- *"reg.deadlines without raw cache == pure rules output (FRAGILITY CHECK)" — the verifier is right, and this is item 8.* `via_reg=[]` against `pure=['2027-07-02', '2027-08-26']`. Whoever wrote that check named it correctly.

So: 44 of 45 substantive checks pass, one real blocking failure, and it is the one this review is about.

**10. Time vs the ≤2-week target — PASS, by a wide margin.**

The UK spec (T15a, sixteen live fixtures and a 1,470-line specification) started ~17:15 and the module (T15b, 1,643 lines of implementation plus 1,242 lines of test) was finished ~19:00 on the same day — **under two hours from "no UK support" to a green module with 118 GB tests and four passing live checks**, against a target measured in weeks. The project itself is two days old (2026-09-03 → 2026-09-04). D-001's claim that a country is one folder plus one import line now has a second data point, and the cost of country #2 was dominated by *specifying* Britain, not by coding it.

### Fix list — owner: T15b implementer

**B1 (BLOCKING) — remove the raw-cache workaround; deliver the published dates on `CompanyReport` (D-018).** `core/models.py` already carries `PublishedDeadline` and `CompanyReport.published_deadlines`; nothing else in `core/` changes.

1. `src/registry_mcp/registries/gb/mapping.py:265-318` — in `map_entity`, pass `published_deadlines=` built from the raw payload:
   - `annual_accounts`: `due_date` ← `accounts.next_accounts.due_on` (`source="accounts.next_accounts.due_on"`), else `accounts.next_due` (`source="accounts.next_due"`); `period_start`/`period_end` ← `next_accounts.period_start_on`/`period_end_on`; `overdue` ← `next_accounts.overdue` or `accounts.overdue`. Emit the entry when *either* a date or a `period_end` is present (rung 3 needs `period_end` with no `due_date` — `ch_FC032315.json` is that shape).
   - `confirmation_statement`: `due_date` ← `confirmation_statement.next_due` (`source="confirmation_statement.next_due"`); `period_end` ← `next_made_up_to`; `overdue` ← `confirmation_statement.overdue`.
2. `src/registry_mcp/registries/gb/rules.py:582` — `deadlines_for(data, report, today)` → `deadlines_for(report, today)`. `_accounts_deadline` (`:449`) and `_confirmation_deadline` (`:522`) take the matching `PublishedDeadline | None` instead of `data`; the rung-1-vs-rung-2 `applies_because` wording is chosen from `PublishedDeadline.source`, the computed rung from `period_end` + `legal_form_info(report.legal_form_code).accounts_period`, and the confirmation `period_start` reconstruction (`:548-553`) is unchanged. The three gates at `:600-605` are unchanged.
3. `src/registry_mcp/registries/gb/rules.py:8-19` — delete the "the one thing this module cannot be" paragraph; it is no longer true. `deadline_exemption_note(data, report)` (`:640`) **stays as it is** — it is called from `map_entity`, where the raw payload is genuinely in hand, so it never touches the cache.
4. `src/registry_mcp/registries/gb/client.py` — delete `raw_for` (`:325-338`) and drop it from `__all__` (`:55`); delete the "Why this module caches the raw upstream JSON" rationale (`:22-36`) and replace it with the honest one-line reason (a mapping fix then applies to already-cached entries). Keep caching raw JSON.
5. `src/registry_mcp/registries/gb/__init__.py:68-80` — `deadlines()` becomes `return rules.deadlines_for(report, today)`; drop the `client` import and the cache paragraph from the docstring.
6. `tests/test_client_gb.py:59` — **stop deleting `REGISTRY_MCP_CACHE_DISABLED`** unconditionally; the fixture must let a test choose the cold path. `:513` `test_deadline_report_via_registry_uses_published_dates` must then pass with the cache disabled, and a new regression test should assert exactly that: map `ch_00445790.json`, call `Registry.deadline_report` with no cache anywhere, expect both deadlines. `:528` `test_raw_for_returns_none_on_miss` is deleted with the function.
7. `tests/test_rules_gb.py` tests 51–72 call `deadlines_for(data, report, today)`; rewrite them to build the report with `mapping.map_entity(data)` and call `deadlines_for(report, today)`. This *strengthens* them — they then exercise the path the surfaces actually use, which is what would have caught B1.
8. Add `published_deadlines` to test 79's list of fields (it is `[]` for nothing-published cases) and re-run tests 51–72, 106–109.

**B2 (non-blocking, D-019) — align Norway's 429.** `src/registry_mcp/registries/no/client.py:167-175`: `ErrorCode.UPSTREAM_ERROR` → `ErrorCode.RATE_LIMITED`, and reword the hint to name the wait. Three call sites (`:216`, `:225`, `:265`) need no change. Also correct the `429` row of `NORBIZ_SPEC.md:278`. No existing test asserts the current code.

**N-1 (nit)** — `client.py:240`: move `_bucket.acquire()` inside the retry loop so a retry spends a token, per §6.
**N-2 (nit)** — `mapping.py:114`: `entry["name"]` is the one place the mapper indexes rather than `.get()`s; a `previous_company_names` entry without `name` would `KeyError`. Use `.get("name")` and drop empties.
**N-3 (nit)** — `mapping.py:393`: `total = data.get("total_results", len(hits))` defaults to the hit count where §4 says `0`. The current default is arguably kinder (it keeps `truncated` honest), but the spec and the code should agree — change one of them.
**N-4 (nit)** — `tests/test_rules_gb.py:570` test 72 monkeypatches `rules_common.roll_forward`, but `gb/rules.py` imports `add_months` by name and never touches the module attribute, so the patch can only ever be a no-op. Add the source-inspection half the spec also allows: assert `"roll_forward"` appears in no file under `registries/gb/`.

**Verdict: BLOCKED on B1 alone.** Everything else in the module is approved and, on the traps that mattered, better than the spec required — the finding that produced D-018 was raised by the implementer, in writing, before the review, which is exactly the behaviour the process is for. Fix B1 and T15e signs off; T15c and T15d stay blocked until it lands.
