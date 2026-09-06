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

---

## R01 — Norwegian deadline citations review (2026-09-05)

Correctness review of live output, authorised by Kim on 2026-09-05 while feature work is frozen. Trigger: `~/research/registry-mcp/03-regulation-drivers/12-norway-statutory-filing-deadlines-exact-citations.md`, which flags three possible errors in what the Norwegian module computes and cites.

Read in full: `src/registry_mcp/registries/no/rules.py` (734 lines), `src/registry_mcp/core/rules/common.py`, `src/registry_mcp/core/models.py :: Deadline`, `src/registry_mcp/registries/no/mapping.py`, `tests/test_rules_no.py`, `NORBIZ_SPEC.md` §§5.2–5.5 and §13.E–F, `legal/terms.md`, D-009 / D-010 / D-016 / D-018.

Baseline: `uv run pytest -q -m "not live"` → **404 passed**, no failures, no server started.

Every Norwegian provision below was read on Lovdata on 2026-09-05 and is quoted from the operative text, not paraphrased. Where a Lovdata chapter page served only its table of contents, the section was fetched at its own URL (`…/%C2%A78-3-10`) and the body extracted from the served HTML.

### Verdicts

| # | Claim in the research file | Verdict |
|---|---|---|
| 1 | We cite §§ that do not contain the roll-forward rule | **PARTIAL** — no `applies_because` cites any statute (so not a bug as framed), but `NORBIZ_SPEC.md:212` carries a citation that is **wrong**, and two deadlines are rolled forward that have **no** roll-forward rule and are made *later than lawful* by it. **CONFIRMED bug, different species.** |
| 2 | MVA term 3 is 31 August, not 10 August | **NOT a bug** — encoded, spec'd, tested and documented. One non-blocking nit about the filing-cycle assumption. |
| 3 | § 8-3(1) sets 1 February for a year ending 1 Jan–30 Jun; is the calendar-year note honest? | **PARTIAL** — the note is honest but understates the size of the error and over-claims that nobody publishes the accounting period. Brønnøysundregistrene does publish it, in a different open API. |

---

### 1. Roll-forward — PARTIAL as reported, CONFIRMED bug underneath

**1a. The reported bug does not exist: nothing in `src/` cites a statute at all.**

```
$ grep -rn "§\|regnskapsloven\|skatteforvaltning\|a-opplysning\|aksjeloven\|lovdata" src/
```
returns only `NORBIZ_SPEC.md` / `UK_SPEC.md` cross-references in docstrings. Every Norwegian `applies_because` is plain prose naming the legal form and the authority — `rules.py:503-506`, `:529-532`, `:555-558`, `:581-584`, `:616-620`, `:650-653` — and `Deadline.source_url` (`core/models.py:424`) is left `None` on all six. So no shipped deadline string attributes a rule to a provision that does not contain it. `legal/terms.md` promises less than the research file assumes: "Each deadline states its **assumption** in `applies_because`" — not its basis. **Not a bug.**

**1b. The one citation we do ship is wrong.**

`NORBIZ_SPEC.md:212`:

> A statutory date falling on a Saturday, Sunday or public holiday moves to the next working day (**forvaltningsloven § 30 / skattebetalingsloven**).

Neither reference holds. Forvaltningsloven § 30 is about when an appeal counts as lodged in time — "For at klage skal være fremsatt i tide, er det nok at erklæringen før utløpet av fristen er avgitt til tilbyder av posttjenester…" — and the act contains **no** weekend or holiday rule anywhere (checked the full consolidated text, <https://lovdata.no/dokument/NL/lov/1967-02-10>). "skattebetalingsloven" names an act, not a provision, and skattebetalingsloven governs *payment*, not the *filing* deadlines this module computes.

**The correct chain, for the four tax deadlines, is two steps and is quotable:**

> **Skatteforvaltningsloven § 5-5 — Fristberegning mv.** "Når ikke annet er bestemt, begynner frister etter denne loven eller forskrift i medhold av loven å løpe fra det tidspunktet meldingen er kommet fram. **Fristen regnes i overensstemmelse med domstolloven §§ 148 og 149.**"
> <https://lovdata.no/dokument/NL/lov/2016-05-27-14/KAPITTEL_5>

> **Domstolloven § 148** "…**Avslutningen av en frist kan ogsaa betegnes ved en bestemt kalenderdag.**"
> **Domstolloven § 149** "**Ender en frist paa en lørdag, helgedag eller dag som etter lovgivningen er likestilt med helgedag forlenges fristen til den nærmest følgende virkedag.** Er fristen fastsatt i timer, reknes ikke helgedager og dager som etter lovgivningen er likestilt med helgedager, med i dens løp."
> <https://lovdata.no/dokument/NL/lov/1915-08-13-5/KAPITTEL_1-8>

§ 148's last sentence is what closes the argument: a frist expressed as a fixed calendar day (31 May, 31 January, 31 August, the 5th) is still a *frist* for §§ 148–149, so § 149 reaches it. And skatteforvaltningsforskriften is "forskrift i medhold av" skatteforvaltningsloven, so § 5-5 reaches §§ 8-2-3, 8-3-10 and 7-7-4. **The roll-forward is lawful for `tax_return`, `shareholder_register_statement` and `vat_return` — we simply had the wrong section.**

For `payroll_report` the rule is in the provision itself and needs no chain:

> **A-opplysningsforskriften § 2-1** "Opplysningene skal leveres senest den 5. i måneden etter utløpet av den kalendermåned opplysningene gjelder. … **Faller fristen på en lørdag, søndag eller helligdag utskytes fristen til første påfølgende virkedag.**"
> <https://lovdata.no/dokument/SF/forskrift/2014-06-24-857/KAPITTEL_2>

**1c. CONFIRMED BUG — `annual_accounts` and `general_meeting` are rolled forward with no rule behind it, and the roll makes the answer late.**

Neither the Companies Act nor the Accounting Act references domstolloven §§ 148–149, and forvaltningsloven — the only general act that would otherwise reach Regnskapsregisteret — has no such rule. So the chain that saves the tax deadlines does not exist here. Worse, on the accounts date the roll crosses the very trigger the date exists to avoid:

> **Regnskapsloven § 8-3(1) — Forsinkelsesgebyr** "Dersom årsregnskap, årsberetning, revisjonsberetning eller oversendelsesbrev som skal sendes til Regnskapsregisteret, **ikke er avsendt før 1. august i året etter regnskapsåret** … skal den regnskapspliktige betale forsinkelsesgebyr inntil innsendingsplikten er oppfylt eller mangler er rettet, men ikke for mer enn 26 uker. **Er regnskapsåret avsluttet på en dato fra 1. januar til 30. juni, er fristen etter første punktum 1. februar.** … Departementet kan i forskrift **utsette fristene** etter første og annet punktum med **inntil en måned**, og gi andre regler om forsinkelsesgebyr."
> <https://lovdata.no/dokument/NL/lov/1998-07-17-56> (Kapittel 8)

Current code, `rules.py:485-487`:

```python
def _annual_accounts(today: date, holidays: frozenset[date], code: str) -> Deadline:
    statutory = next_occurrence(7, 31, today)
    due = roll_forward(statutory, holidays)
```

The fee accrues unless the accounts are **dispatched before 1 August**. Rolling 31 July onto the next business day always lands on or after 1 August, so `due_date` is a date on which the fee is already running. Executed against the shipped module:

| Year | statutory | weekday | `due_date` we return | fee already accruing? |
|---|---|---|---|---|
| 2027 | 2027-07-31 | Sat | **2027-08-02** | yes |
| 2032 | 2032-07-31 | Sat | **2032-08-02** | yes |
| 2033 | 2033-07-31 | Sun | **2033-08-01** | yes |

This is not hypothetical output. It is pinned by `NORBIZ_SPEC.md` test 58 and `tests/test_rules_no.py:375-381`, and it is **already published** as a worked example telling readers the real date is 2 August: `content/02-deadlines/devto.md:43` and `:53` ("31 July 2027 is a Saturday, so the real date is 2 August"), `content/02-deadlines/reddit.md:13`.

`general_meeting` has the same defect with a different reason — there is no office to be closed at all. `Deadline.authority` is literally `"Company shareholders (no external filing)"` (`rules.py:521`), and the six-month limit is an outer bound:

> **Aksjeloven § 5-5(1)** "**Innen seks måneder etter utgangen av hvert regnskapsår** skal selskapet holde ordinær generalforsamling."
> <https://lovdata.no/dokument/NL/lov/1997-06-13-44/KAPITTEL_5-1>
> **Regnskapsloven § 3-1(2)** "Årsregnskapet og årsberetningen skal fastsettes senest seks måneder etter regnskapsårets slutt."

`rules.py:511-513` rolls 30 June forward anyway: 2029-06-30 (Sat) → **2029-07-02**, 2030-06-30 (Sun) → **2030-07-01**, 2035-06-30 (Sat) → **2035-07-02**. Each is past the six months the Act allows, and a general meeting may lawfully be held on a Saturday.

**What could rebut this, and did not.** Skatteetaten's practice is what the chain in 1b codifies, so the tax deadlines are safe. For Regnskapsregisteret I looked for a published brreg practice or a forskrift under § 8-3(1)'s last sentence and **found none I could cite** — `brreg.no` returned 404 on every deadline-guidance path I tried, and this session's WebSearch budget was exhausted before I could search for the right one. Under D-009 ("never guess a duty") the absence of a source is decided against inventing the extension, not for it. If someone later produces a published brreg statement that the date rolls, that is an amendment to D-022, not a code change made on a hunch.

### 2. MVA-melding, term 3 = 31 August — NOT a bug

> **Skatteforvaltningsforskriften § 8-3-10(1)** "Leveringsfrist for skattemelding er **en måned og ti dager** etter utløpet av hver skattleggingsperiode eller fra tidspunktet for virksomhetens opphør. **Fristen for tredje alminnelige skattleggingsperiode er likevel 31. august.** Annet punktum gjelder tilsvarende for annen skattleggingsperiode for særskilt skattemelding etter skatteforvaltningsforskriften § 8-3-9 (1) bokstav a–c."
> **§ 8-3-1** "Skattemelding for merverdiavgift skal leveres periodevis. **Hver skattleggingsperiode omfatter to kalendermåneder.** Første periode er januar og februar, andre periode er mars og april, **tredje periode er mai og juni**, …"
> <https://lovdata.no/dokument/SF/forskrift/2016-11-23-1360/%C2%A78-3-10> · <https://lovdata.no/dokument/SF/forskrift/2016-11-23-1360/%C2%A78-3-1>

The exception is encoded, with a comment naming it, at `rules.py:422-429`:

```python
_VAT_TERMS: tuple[tuple[int, int, int, int, int, int], ...] = (
    (1, 1, 2, 0, 4, 10),
    (2, 3, 4, 0, 6, 10),
    (3, 5, 6, 0, 8, 31),  # exception: 31 August, not 10 August
    ...
```

It is in `NORBIZ_SPEC.md` §5.4's term table ("Term 3 is the exception… the most common thing to get wrong"), in `rules_markdown()` (`rules.py:725-726`), and asserted by `tests/test_rules_no.py:421-428` (test 64: `statutory_date == due_date == date(2026, 8, 31)`). All six terms match § 8-3-10(1) applied to § 8-3-1's periods. Rolling 31 August forward (2030-08-31 Sat → 2030-09-02) is correct under the § 5-5 → § 149 chain. **No fix required.**

**Nit N-1 (non-blocking).** `applies_because` for `vat_return` (`rules.py:616-620`) states the fact that triggers the deadline but not the assumption behind the *date*: §§ 8-3-3 (annual by consent, turnover ≤ 1 MNOK), 8-3-7 (primary industries) and 8-3-2 (monthly, imposed for repeated breach) all exist, none is visible in Enhetsregisteret, and each moves the date by months. The `Deadline` contract already reserves a place for exactly this — `mandatory` is "False when it depends on facts we cannot see… `applies_because` explains the assumption" (`core/models.py:404-412`). The obligation is certain (`registrertIMvaregisteret` is published), so `mandatory` should stay `True`; the *cycle* assumption belongs in the sentence.

### 3. Calendar-year assumption — PARTIAL

The note exists and is attached in the right place. `mapping.py:64-72`:

```python
_CALENDAR_YEAR_ASSUMPTION_NOTE = (
    "Filing deadlines are computed assuming a calendar-year accounting period. "
    "A company with a deviating accounting year (avvikende regnskapsår) will have "
    "different actual dates, and Enhetsregisteret does not publish which companies those are."
)
```

added whenever any annual deadline would be returned (`mapping.py:288-290`), plus the per-deadline suffix `" Assumes a calendar-year accounting period."` (`rules.py:408`). `legal/terms.md` repeats it. That is honest as far as it goes. Three corrections:

**3a. It understates the error by a branch, not by a few days.** § 8-3(1) second sentence does not shift the date; it *selects a different one*. For a financial year ending 1 January–30 June the deadline is **1 February**, and our answer of 31 July is not merely different — it is roughly six months **after** the fee started running. "will have different actual dates" reads as a rounding caveat. It should say the date can be one we do not compute at all.

**3b. It omits the ministerial postponement.** § 8-3(1) last sentence: "Departementet kan i forskrift utsette fristene … med inntil en måned." A computed 31 July can be overtaken by a regulation neither register publishes. This is the same class of unknown as a deviating year and belongs in the same note.

**3c. It is attached to two deadlines whose dates do not move with the accounting year.** `_tax_return` (`rules.py:557`) and `_shareholder_register_statement` (`rules.py:583`) both append the calendar-year suffix, but both are keyed to the *skattleggingsperiode*, not the accounting year:

> **Skatteforvaltningsforskriften § 8-2-3(1)** "Skattemelding skal leveres a. **innen utgangen av mai** i året etter skattleggingsperioden for selskap mv. som nevnt i skatteloven § 2-2 første ledd, for selskap som skal levere selskapsmelding mv. etter skatteforvaltningsloven § 8-9 og for eier av enkeltpersonforetak b. **innen utgangen av april** i året etter skattleggingsperioden for andre skattepliktige…"
> **§ 7-7-4(1)** "Aksje- og allmennaksjeselskap skal gi opplysningene til skattekontoret **innen 31. januar i året etter skattleggingsperioden**."
> **Skatteloven § 14-1(1)** "Med mindre annet er bestemt, er **inntektsperioden kalenderåret**." (3) "For næringsdrivende regnskapspliktig skattyter som … benytter et annet regnskapsår enn kalenderåret (avvikende regnskapsår), **fastsettes inntekten** til det beløpet den har utgjort i det siste regnskapsåret som er utløpt før 1. januar det året skatten fastsettes."
> <https://lovdata.no/dokument/SF/forskrift/2016-11-23-1360/%C2%A78-2-3> · <https://lovdata.no/dokument/SF/forskrift/2016-11-23-1360/%C2%A77-7-3> · <https://lovdata.no/dokument/NL/lov/1999-03-26-14/%C2%A714-1>

A deviating accounting year changes *which* year's figures go into the return (§ 14-1(3)); it does not move the skattleggingsperiode, so 31 May and 31 January stand. The caveat is harmless there but it is not true, and a caveat attached to everything teaches an agent to ignore it. It belongs on `annual_accounts` and `general_meeting`, which key off the financial year end, and nowhere else.

**3d. The last clause of the note is wrong about Brønnøysundregistrene, and this is the useful finding.** "Enhetsregisteret does not publish which companies those are" is true of Enhetsregisteret. It is **false of Regnskapsregisteret**, which is the same agency, the same open-data host and needs no API key. Verified live 2026-09-05:

```
$ curl -s https://data.brreg.no/regnskapsregisteret/regnskap/923609016
[{"id":7192427,…,"regnskapsperiode":{"fraDato":"2025-01-01","tilDato":"2025-12-31"},…}]
$ curl -s https://data.brreg.no/regnskapsregisteret/regnskap/982463718
982463718 SELSKAP {'fraDato': '2024-01-01', 'tilDato': '2024-12-31'} NOK
```

For any entity that has filed at least once, `regnskapsperiode.tilDato` is a **published fact** about the accounting year end, from the register itself. That is the D-018 shape — provenance, published beats computed — applied to Norway, and it would let the module pick § 8-3(1)'s correct branch instead of assuming one. It is not a bug and not in scope for this fix round; it is the reason the note's last clause must be narrowed now so it does not become an excuse later. (I did not find a live entity with a non-calendar `regnskapsperiode`, so the *variance* of the field is unverified; only its presence and shape are.)

`CompanyReport.last_annual_accounts_year` (`mapping.py:285`, from `sisteInnsendteAarsregnskap`) is a bare year and cannot substitute — it says an entity filed for 2025, not that its year ended 31 December.

### 4. Also verified while here

| Rule | Code | Source | Verdict |
|---|---|---|---|
| a-melding, the 5th, rolls forward | `rules.py:624-657` | a-opplysningsforskriften § 2-1 (quoted above) | **Correct**, and the only deadline whose roll-forward is in its own provision. |
| Skattemelding, 31 May | `rules.py:537-539` | skatteforvaltningsforskriften § 8-2-3(1)(a) | **Correct for AS, ASA, SA, BA, ENK, ANS, DA, KS** — (a) covers § 2-2(1) companies, § 8-9 selskapsmelding filers (ANS/DA/KS) and *eier av enkeltpersonforetak*. |
| Skattemelding for `NUF` | `rules.py:415` `_TAX_RETURN_FORMS` | § 8-2-3(1)(a) vs (b) | **Open, `VERIFY`.** A NUF is § 2-2(1) only if "reelt hjemmehørende i riket"; otherwise it is taxed under skatteloven § 2-3 and falls in (b) — **30 April**, not 31 May. Which one turns on effective management, a fact Enhetsregisteret does not publish. Not a finding this round; flagged so it is not discovered by a user. |
| RF-1086, 31 January, AS/ASA only | `rules.py:563-565` | skatteforvaltningsforskriften § 7-7-4(1); duty-holders § 7-7-1(1) | **Correct.** § 7-7-4(2) gives other § 7-7(3) bodies 31 March; we emit for AS/ASA only, so no exposure. |
| Norwegian holidays; 24/31 Dec excluded | `rules.py:120-146` | — | Unchanged this round; the `VERIFY` in `NORBIZ_SPEC.md:207` is still open. |
| Denmark's 6-month deadline (`~/research/.../02-registers-landscape/README.md:74`) | — | årsregnskabsloven § 138 | **No Norwegian impact.** `grep -rn "Denmark\|Danish\|CVR" src/ NORBIZ_SPEC.md` → no hits; Denmark is country 3 and unimplemented. Nothing in Norwegian text derives from it. |

### Fix list — owner: Sonnet implementer (follow-up task), except F5/F6 which are done in this review

**F1 (BLOCKING) — `rules.py:485-509`, `_annual_accounts`: stop rolling forward.**
`due = statutory`, `rolled_forward=False`, and drop `holidays` from the signature (or keep it unused and say why — prefer dropping). Proposed `applies_because`:

> `f"{_article(code)} {code} must file annual accounts with Regnskapsregisteret; regnskapsloven § 8-3(1) starts a late fee unless they are dispatched before 1 August, so 31 July is the last safe day and the date does not move off a weekend or holiday. Assumes a calendar-year accounting period — a financial year ending between 1 January and 30 June has a 1 February deadline instead."`

`statutory_date` stays 31 July: § 8-3(1) names 1 August, but the operative test is "avsendt **før** 1. august", so 31 July is the actionable date and both fields should carry it.

**F2 (BLOCKING) — `rules.py:511-535`, `_general_meeting`: stop rolling forward.** Same change. Proposed `applies_because`:

> `f"{_article(code)} {code} must hold its ordinary general meeting within six months of the financial year end (aksjeloven § 5-5(1)), and the annual accounts must be adopted in the same six months (regnskapsloven § 3-1(2)). Assumes a calendar-year accounting period. Six months is an outer limit, so this date does not move off a weekend or holiday."`

**F3 — cite the roll-forward where it is real, per deadline.** Keep `roll_forward` in `_tax_return`, `_shareholder_register_statement`, `_vat_return`, `_payroll_report`. Add the basis to each `applies_because`, one clause, no more:
- `tax_return` → "(skatteforvaltningsforskriften § 8-2-3(1)(a))"; **drop** the calendar-year suffix (3c).
- `shareholder_register_statement` → "(skatteforvaltningsforskriften § 7-7-4(1))"; **drop** the calendar-year suffix (3c).
- `vat_return` → "(skatteforvaltningsforskriften § 8-3-10(1); periods § 8-3-1)" plus N-1's cycle assumption: "assumes the ordinary two-month cycle — annual filing by consent (§ 8-3-3) or for primary industries (§ 8-3-7) is not published in Enhetsregisteret."
- `payroll_report` → "(a-opplysningsforskriften § 2-1)".
- Where the roll actually fired, the sentence may add: "moved off a Saturday, Sunday or public holiday under domstolloven § 149, applied by skatteforvaltningsloven § 5-5" — for `payroll_report`, a-opplysningsforskriften § 2-1 says it directly and should be cited instead.

**F4 — `rules.py:723-733`, `rules_markdown()`.** Replace the blanket sentence "All annual deadlines assume a calendar-year accounting period, and a statutory date falling on a weekend or Norwegian public holiday rolls forward to the next working day" with a per-deadline statement: the four tax/payroll deadlines roll (cite § 5-5 → § 149, and § 2-1 for the a-melding); `annual_accounts` and `general_meeting` do not, and say why. Add the 1 February branch and the ministerial-postponement caveat.

**F5 — `NORBIZ_SPEC.md` §5.3 and §5.4: done in this review**, marked with the date. §5.3 now carries the correct chain and the two exceptions; §5.4's table gains a "rolls forward" column and the 1 February branch; §13.F test 58 is rewritten and tests 58b, 63b, 63c added.

**F6 — `DECISIONS.md` D-022 and D-023: added in this review.**

**F7 — `tests/test_rules_no.py`.** `:375-381` test 58 must change to assert `statutory_date == due_date == date(2027, 7, 31)` and `rolled_forward is False`; add the spec's new 58b (2033-07-31 Sunday, still 31 July), 63b (2029-06-30 Saturday, still 30 June) and 63c (`annual_accounts` and `general_meeting` never have `rolled_forward is True`, for every year 2026–2040). Test 63 (`:414-418`) still passes unchanged. Tests 59–62, 64–69 are unaffected.

**F8 — `mapping.py:64-72`, `_CALENDAR_YEAR_ASSUMPTION_NOTE`.** Proposed replacement:

> "Filing deadlines are computed assuming a calendar-year accounting period. Enhetsregisteret does not publish a company's accounting year. For a financial year ending between 1 January and 30 June, regnskapsloven § 8-3(1) sets a different deadline — 1 February, not 31 July — so a deviating year changes which rule applies, not just the date. The Ministry may also postpone the accounts deadline by up to one month by regulation (§ 8-3(1)). Verify against Regnskapsregisteret before relying on an annual date."

**F9 — published examples now contradict the fix.** `content/02-deadlines/devto.md:39-43` and `:53`, `content/02-deadlines/reddit.md:13`, and `static/llms-full.txt:481` all show or assert `annual_accounts` rolling to 2027-08-02. Owner: Opus B, after F1 lands. `static/well-known/mcp/server-card.json:57` says `due_date` "already accounts for weekends and public holidays" — narrow it to "where the law says it does".

**F10 (optional) — `legal/terms.md` "Computed deadlines".** One sentence that a computed Norwegian date states its own statutory basis, and that two of them deliberately do not move off a weekend.

**Verdict: one confirmed bug, blocking, in two deadlines.** `annual_accounts` and `general_meeting` return a `due_date` that is later than the law allows whenever the statutory date falls on a weekend — next in 2027, already published as a worked example. Everything else in §5.4 is right, including the term-3 exception the research file expected us to have got wrong. The citation defect the research file predicted is real but lives in the spec, not in the output; the fix for it is D-022, which makes the sourcing rule the same one D-016(c) already applies to Britain.

**Could not verify from a primary source:** (i) whether Brønnøysundregistrene publishes a practice of rolling the 1 August fee trigger — every `brreg.no` guidance path I tried returned 404 and the session's WebSearch budget was exhausted; the fix is written the safe way and says so; (ii) whether `regnskapsperiode` ever comes back non-calendar (presence and shape verified on two entities, variance not); (iii) the `NUF` skattemelding branch, which is genuinely fact-dependent and is flagged `VERIFY` rather than changed.

---

## T26e — 2026-09-05 — APPROVED (no blocking fixes; fifteen non-blocking, four of them urgent)

Full read of `src/registry_mcp/registries/se/{__init__,client,mapping,rules}.py` (2,197 lines), `tests/test_rules_se.py` (889) and `tests/test_client_se.py` (704), all sixteen `tests/fixtures/bv_*.json`, `tests/fixtures/README.md`, the one import line in `registries/__init__.py` and the suite edits in `tests/test_{api,connector,interface,mcp}.py` + `evals/cases.json` — against `SWEDEN_SPEC.md` (all 17 sections), `tasks/T26.md`, `tasks/T26-recon.md` and, for §3 below, the OpenAPI document itself (`~/research/registry-mcp/02-registers-landscape/02b-sweden-openapi.json`) read programmatically rather than off a field table. Every claim below was executed, not read off. `README.md`, `CHANGELOG.md`, `KEYWORDS.md`, `mcp/server.py` and `content/` were out of scope (Opus B, concurrent).

Environment: `uv run pytest -q -m "not live"` → **579 passed, 11 deselected** — but see fix 1: one test fails for a whole minute in every hour. `uv run mypy src` → clean, 35 source files. **`uv run mypy .` — which is what CI runs (`.github/workflows/ci.yml:31-32`) — fails with 2 errors**, both in the new Sweden test files: fix 2. `uv run ruff check .` → clean. `uv run python evals/run.py --golden` → **28 passed, 0 failed, 3 skipped** out of 31. Suite before Sweden: 455.

### Checklist

| # | Item | Verdict |
|---|---|---|
| 1 | Zero edits to `core/`, `api/`, `mcp/`; suite edits are country-list only | **PASS** |
| 2 | §14's 118 numbered tests, one per number, spec-conformant | **PASS** (6 weakened, table below) |
| 3 | Wire contract against the OpenAPI document | **PASS** (one over-broad detector — fix 4) |
| 4 | Client: token cache, scopes, environment pairing, bucket, retries, no-credentials path | **PASS** |
| 5 | Sole-trader personal data (D-039, N8); no production payload committed | **PASS** |
| 6 | Both surfaces answer without credentials — MCP checked in-process here | **PASS** |
| 7 | pytest / mypy / ruff / evals | **PASS** on the commands T26e was asked to run; **CI is red** on `mypy .` (fix 2) and flaky on pytest (fix 1) |
| 8 | Time vs the ≤2-week target | **PASS**, by three orders of magnitude |

---

**1. Core discipline — PASS.**

`git show --stat 14ccd07` lists 29 files: four new `registries/se/*.py`, one `+1` line in `registries/__init__.py` (alphabetical `gb, no, se, xx`), two new test files, sixteen fixtures, `tests/fixtures/README.md`, and five suite files. **Not one file under `core/`, `api/` or `mcp/`.** D-001 and D-008 hold on their third real test: country #3 was one folder plus one import line, and unlike Britain it needed no `core/` change at all — D-018's `published_deadlines` was already there and Sweden uses it (as `[]`, with rung 1 implemented anyway, per §5.4).

The suite edits are exactly what §16 authorises. `test_api.py` (2 country-set assertions), `test_interface.py` (4), `test_connector.py` (1, with a docstring explaining why SE appears in the zero-hit fallback without a mock), `test_mcp.py` (4 assertions + two new SE tests: `requires_api_key`/`api_key_env` and a non-empty `registry://rules/SE`), `evals/cases.json` (two `equals_set` lists). Two `SE` → `ZZ` swaps in `test_mcp.py:180` and `:386` — the T10-style carry-over, correctly spotted: those tests wanted an *unsupported* country and `SE` had just stopped being one. No test was deleted or loosened.

**2. §14's 118 tests — PASS, all present, six weakened.**

All 118 numbers exist, one function per number, named `test_NN_<slug>`: 1–78 in `tests/test_rules_se.py`, 79–112 in `tests/test_client_se.py`, 113–118 in the same file and all six `@pytest.mark.live` (11 deselected in total). Plus five unnumbered extras — `bv_ab_kk_and_li.json` / `bv_ab_rekonstruktion.json` mapping, the bucket-exhaustion branch, `aclose`, `format_id` via the registry, a `modulus10_ok` table check and a `rules_markdown` content check. None skipped, none merged, none stubbed.

| Test | Gap |
|---|---|
| 71 | "an `E` gets no deadlines **and a `notes` entry**" passes only incidentally — the note it finds is N8 (sole-trader personal data), not an explanation of the empty list. A `BRF` or an SCB-fallback `AB` gets `deadlines == []` and **no note at all**. Fix 5 |
| 74 | Calls `deadline_exemption_note(BANKRUPT, "KK")` directly instead of asserting the 8 kap. 7 § sentence reaches a real bankrupt report's `notes`. The wiring is correct (verified by hand) but untested |
| 78 | The "does not change with the process timezone" half is not asserted. Structurally true — `deadlines_for` takes `today` and never reads a clock — but unpinned |
| 116 | Records the check-digit experiment's outcome with `print`, which pytest swallows without `-s`. The one live test whose *output* is the deliverable |
| 117 | Materially weakened: asserts only `report.name`. §14 makes this the test that proves every field name the mapper reads exists on the wire — "a field this spec names that the live payload does not have is a **blocking** finding" — and records which `pagaende…` and `organisationsnamntyp` spellings the wire really uses. As shipped it proves neither. Fix 8 |
| 118 | Sets `os.environ["BOLAGSVERKET_ENVIRONMENT"]` directly rather than via `monkeypatch`, leaking it into the rest of the live session |

Everything else asserts what the spec says, and a dozen tests assert **more**. Test 66 does both halves of §5.2 — it monkeypatches `core.rules.common.roll_forward` to raise *and* greps every `registries/se/*.py` for the string, which is exactly the correction T15e's nit N-4 asked for on Britain. Test 41 asserts the SCB code appears **nowhere** in the serialised report, not merely that `legal_form_code` is right. Test 51 asserts both list orderings. Test 110 drives the real `mcp/connector.py` rather than mocking it. Test 112 bundles six assertions including the credential-leak sweep over `caplog`, `str(exc)` and `to_dict()`.

**The deadline arithmetic is right, and I checked it against the statute text rather than against the code.** ABL 7 kap. 10 § — *"Inom sex månader från utgången av varje räkenskapsår"* — six months from a 31 December year end is **30 June**, and `next_occurrence(6, 30, today)` is inclusive of `today` (test 64: `days_until == 0` on the day). ÅRL 8 kap. 6 § — *"inom sju månader från räkenskapsårets utgång"* — is **31 July** (test 61). `period_label` is `statutory.year - 1` with `period_start`/`period_end` 1 January/31 December of it, so the 30 June 2026 meeting is labelled FY2025: correct. Rung 1 (a published date) is implemented and unreachable, as §5.4 requires. No roll-forward anywhere: `statutory_date == due_date` and `rolled_forward=False` are literals, 31 July 2027 is a Saturday (confirmed: `weekday() == 5`) and stays 31 July (test 65), there is no `holidays.py`, and the string `roll_forward` appears in no file under `registries/se/`. Test 69 — the one that exists because this project's own library file mis-attributed seven months to ÅRL 8:3 — checks an ±80-character window around the "8 kap. 3" citation and finds "one month" there and "seven months" only next to 8 kap. 6 §. That is the correction holding.

**3. Wire contract against the OpenAPI document — PASS, with one over-broad detector.**

I extracted every property name from `components.schemas` plus every key appearing in Bolagsverket's own `components.examples` (52 + 49 names) and diffed all sixteen fixtures against that set: **no fixture invents a key.** `bv_enskild_two.json` and `bv_uppgiftskalla_fel.json` are byte-equal (modulo key order) to `organisationer-enskild-svar` and `organisationer-fel-fran-en-uppgiftskalla-svar`, verified by normalised JSON comparison, and correctly carry **no** `_VERIFY` key; the four `ApiError` bodies and `bv_token.json` likewise; the nine assembled ones all carry it. `mapping.py`'s `_WRAPPED_FIELDS` is exactly the thirteen `Organisation` properties whose schema carries `fel`+`dataproducent`, with `organisationsidentitet`, `namnskyddslopnummer` and `registreringsland` correctly excluded — I checked that against the schema, property by property, rather than against §1.6's prose.

- **POST body, never a URL** — `client.py:417-419` is the only request construction; test 102 asserts `{"identitetsbeteckning": "…"}` and `respx` would not match a GET.
- **Envelope array** — `_first_organisation`, `organisationer[0]`, every field from that same element (test 91).
- **Per-field `fel` before every value** — `_FieldReader.wrapper` is the single gate and nothing in `map_entity` reads a wrapper without it.
- **`not_found` from `fel.typ`** — works (tests 96, 111), but the scan is **wider than §6.3**: see fix 4.
- **Two date shapes** — one `_DATE_PREFIX_RE` parser for every date; `"2023-05-05T00:00:00.000+00:00"` → `date(2023,5,5)` (tests 45, 49, 90).
- **`pagaende…` spelling** — both spellings read at **both** the outer wrapper and the inner `…Lista` (`mapping.py:421-432`), test 98 constructs the misspelled payload and still gets `BANKRUPT`. The Altinn bug is closed.
- **`namnskyddslopnummer` plural** — one report from element 0, N7 names both businesses and both numbers (test 92), `previous_names` stays `[]`.
- **Twelve digits never truncated** — test 7, and `format_id` renders `19400927-2719`.
- **`registreringsland` not ISO** — never read; test 97 injects `XX-LAND` and `country` stays `"SE"`.
- **`organisationsnamntyp` open string** — `"FORETAGSNAMN"` matched exactly for the primary name, everything else rendered from `klartext` into N12; both foreign-language spellings tolerated because neither is branched on.
- **`JaNej` coerced explicitly** — `verksam_kod == "NEJ"` and `reklamsparr_kod == "JA"`, never `bool()`. The most likely single-character bug in the module is not present.

**4. Client — PASS.**

Token cached per environment in a module-level dict with a 60 s refresh margin against `time.monotonic()` (never wall-clock), `expires_in` read from the response rather than hard-coded (`client.py:372-376`), tests 103 and 104b. Both scopes in one form-encoded request, asserted on the wire (`vardefulla-datamangder%3Aread+vardefulla-datamangder%3Aping`, test 102). `BOLAGSVERKET_ENVIRONMENT` indexes `_BASE_URLS` and `_TOKEN_URLS` as a pair so the hosts cannot be mixed, an unrecognised value raises naming both legal values and opens no socket (test 106), and the environment is a segment of the cache key (`SE:bolagsverket:entity:{prod|test}:{id}`) so a switch cannot serve test companies as production ones. **The token host is `portal.`, not `gw.`** — the correction this spec exists for — and test 102 asserts it explicitly. Fresh `uuid4` `X-Request-Id` per *attempt*, logged at DEBUG and nowhere else, distinctness asserted (test 107). Bucket capacity 60, refill 1.0/s, 2 s max wait, and `acquire()` sits **inside** both retry loops so a retry spends a second token — T15e's nit N-1 on Britain, fixed here without being asked. 5 s `httpx.Timeout`, exactly one retry on a timeout or 5xx and never on a 4xx, 250 ms backoff, the 401/403 token-refresh-and-retry layered above it and bounded to one (tests 104, 112). Credentials read inside the request path with `.strip()`; missing either raises `upstream_error` naming **both** variables plus `list_countries` and the kundanmälan URL, before any socket (test 99, mock call count 0), and importing the package with neither set still registers `SE` (test 100). Upstream 400 → `invalid_id`, not retried, and no upstream body is echoed into `message`, `hint` or `details` — `bv_400.json`'s `requestId`, `timestamp` and Swedish `detail` all stay upstream. A partial 200 is mapped but never written to the cache, pinned by a second identical call making a second HTTP request (test 111). `aclose()` closes the client **and** clears `_tokens`, asserted on both (`test_registry_aclose_closes_client_and_clears_token`).

**5. Sole-trader personal data — PASS.**

N8 fires on `typ.kod` in `{PERSONNUMMER, SAMORDNINGSNUMMER, GDNUMMER, DODSBO}` **or** `organisationsform.kod == "E"` (`mapping.py:566`), test 92. `rules_markdown()` states it in prose — "a Swedish national identity number for a natural person" — satisfying §13 item 3. **No note ever repeats the identifier**: test 93 asserts no note contains the digit string, and N7 carries names, `namnskyddslöpnummer` and registration dates instead. `registries/se/` writes the identifier only to the request body, the cache key, `CompanyReport.id` and the two error messages §6.4 specifies verbatim — F1 stays a `core/`+`api/` finding and is not re-opened here. `bv_enskild_two.json` is Bolagsverket's own synthetic OpenAPI example, not a recording; `tests/fixtures/README.md` reproduces §17's redaction rule including the sentence that no production sole-trader payload may ever be committed.

One place the identifier reaches a fourth field: on a partial-failure 200 with no name, `map_entity` falls back to `name = requested_id` (`mapping.py:520`) — so during a Bolagsverket outage a sole-trader lookup would put a personnummer in `CompanyReport.name`. §14 test 95 explicitly authorised either behaviour and the implementer asserted the one it chose, so this is conformant, not a defect. §11's enumeration of where the identifier may appear should gain that fourth place, or the fallback should become `None` in T26d.

**6. Both surfaces without credentials — PASS. MCP checked in-process, no network.**

The implementer smoke-tested REST; I drove the FastMCP client against the server object with `BOLAGSVERKET_CLIENT_ID`/`_SECRET` unset, and with `REGISTRY_MCP_LOG_PATH`/`REGISTRY_MCP_CACHE_PATH` pointed at a scratch directory so no personnummer touched the operator's own SQLite:

- `list_countries` → `['GB', 'NO', 'SE']`; the SE row publishes all eleven §1.10 values, `requires_api_key: true`, `api_key_env: "BOLAGSVERKET_CLIENT_ID"`, and the licence string that names no licence.
- `lookup_company(SE, 5560160680)` → `upstream_error`, `{code, message, hint, country, registry, details}`, hint carries **both** variable names and `list_countries`. No crash, no traceback.
- `validate_company_id(SE, "556002-1361")` → `valid: true`, `normalized: "5560021361"`, `formatted: "556002-1361"`, `hint: null`.
- `validate_company_id(SE, "194009272719")` → `valid: true`, `hint: null`, and the reason carries the §5.1.5 personnummer caveat. `"923609016"` → `valid: false` with the Norway hint. `validate` never raised.
- `search_company(SE, "Volvo")` → `not_implemented`, hint names `lookup_company`. **`ErrorCode.NOT_IMPLEMENTED`'s first real caller across both surfaces, and the 501 path works.**
- The D-031 `search` alias with a Swedish name (`"Cykelbolaget AB"`, NO and GB mocked with `respx`) → `['NO:923609016']`. Sweden's `not_implemented` drops one country and the other two answer, exactly as §4 predicted from reading `mcp/connector.py:314-330`.

**7. The runs — PASS on the four commands T26e was asked to run; CI would be red on two of them.**

Numbers above. Two problems, both in the *tests* rather than in `registries/se/`, and both invisible to the exact command set the done-check names.

The flake is real and reproducible: `test_41_both_present_organisationsform_wins_no_n5` asserts `"49" not in json.dumps(report.model_dump(mode="json"))` and the dump contains `fetched_at`, which is `datetime.now(UTC)`. It therefore fails **for the whole of minute :49 of every hour** and randomly whenever the microseconds contain `49` (measured 1.5 % of maps outside that minute). It failed one of five full-suite runs here, at 06:49 UTC. The assertion it is making is a good one and worth keeping — fix 1 is one line.

The type check is worse, because it is deterministic. T26e was asked for `uv run mypy src`, which is clean; **CI runs `uv run mypy .`** (`.github/workflows/ci.yml:31-32`), and that reports two errors, both introduced by this commit:

```
tests/test_rules_se.py:574: error: Non-overlapping identity check
    (left: Literal[CompanyStatus.UNDER_LIQUIDATION], right: Literal[CompanyStatus.BANKRUPT])  [comparison-overlap]
tests/test_client_se.py:645: error: Statement is unreachable  [unreachable]
```

Neither is a defect in the module — both are mypy narrowing artefacts in correct tests — but the commit message's "green" is not what a CI run would report, and T26d must not discover this at release time. Fix 2, and I verified both replacements type-check under `--strict` before writing them down.

`ruff format --check` still reports repo-wide drift; CI runs `ruff check`, not `ruff format` (`.github/workflows/ci.yml:28-29`), so this is pre-existing and not a T26b finding, as at T15e.

**8. Time vs the ≤2-week target — PASS.**

T26 opened ~21:45 local on 2026-09-05 with recon (T26r) and the architecture (T26a) in parallel; the commit landed at **23:35:22 +0200** — 2,197 lines of implementation, 1,593 lines of test, 118 numbered tests and sixteen fixtures, in **under two hours** against a target measured in weeks. Country #3 was cheaper than country #2 despite being the first with two secrets, the first with no status field, the first whose identifier is a natural person's, and the first where HTTP 200 does not mean the data arrived. The expensive half was again specification: the 2,027-line `SWEDEN_SPEC.md` and the recon digest that corrected the token host, the ÅRL citation and the check-digit claim before a line of code existed.

### Fix list — owner: a Sonnet, dispatched by the orchestrator. None blocks T26c.

**1 (urgent — CI will fail ~1 run in 60 on the clock alone).** `tests/test_rules_se.py:437-438`. `dumped = report.model_dump(mode="json")` then `assert "49" not in json_values(dumped)` matches the timestamp digits in `fetched_at`. Pop the volatile field before the check:
```python
dumped = report.model_dump(mode="json")
dumped.pop("fetched_at", None)
assert "49" not in json_values(dumped)
```
Keep the assertion — it is the right one, it is just reading one field too many.

**2 (urgent — CI's `mypy .` is red; both replacements verified under `--strict`).**

(a) `tests/test_rules_se.py:573-574`, test 52. Line 573 narrows `report.status` to `Literal[UNDER_LIQUIDATION]`, so line 574's `is not CompanyStatus.BANKRUPT` is a non-overlapping identity check. §14 test 52 wants both assertions, so **swap them** — the negative first, then the positive:
```python
assert report.status is not CompanyStatus.BANKRUPT
assert report.status is CompanyStatus.UNDER_LIQUIDATION
```
Confirmed clean under `mypy --strict`; do not silence it with an ignore, and do not drop either line.

(b) `tests/test_client_se.py:640,644-645`, `test_registry_aclose_closes_client_and_clears_token`. `assert http_client.is_closed is False` narrows the property to `Literal[False]` for the rest of the function, so `assert http_client.is_closed is True` after `aclose()` is unreachable and the `_tokens == {}` assertion below it is dead code to mypy — and, worse, mypy is telling us that assertion is never type-checked. Read the property into a fresh annotated local on each side:
```python
closed_before: bool = http_client.is_closed
assert closed_before is False
...
closed_after: bool = http_client.is_closed
assert closed_after is True
assert client_module._tokens == {}
```
Confirmed clean under `mypy --strict`.

**3 (urgent — a wrong answer on the field a payment check reads first).** `src/registry_mcp/registries/se/mapping.py:534-548` + `rules.py:468-571`. A partial-failure 200 (`bv_uppgiftskalla_fel.json`, Bolagsverket's own outage example) currently maps to **`status: active`, `is_active: true`** and `status_detail` "Registered with Bolagsverket and not marked as struck off or in any winding-up or restructuring procedure." — an affirmative claim about a company from a payload that carried no status data at all. `_FieldReader` correctly refuses to read the blocked values; `derive_status`'s rung 3 then turns that silence into `ACTIVE`. This is precisely the failure §1.6 rule 1 was written about, one field further on than the spec followed it. Change: `map_entity` should pass a flag (or `derive_status` should take one) set when any of `avregistreradOrganisation`, `avregistreringsorsak` or `pagaende…` was blocked by a `fel.typ` in `_BLOCKING_FEL_TYPES`; when it is set, return `CompanyStatus.UNKNOWN`, `is_active=False`, and a `status_detail` naming the unavailable producer instead of asserting good standing. N13 still fires. Add a test asserting `map_entity(UPPGIFTSKALLA_FEL, …).status is CompanyStatus.UNKNOWN`, and note the change under §14 test 95's "assert the shipped behaviour explicitly". **`SWEDEN_SPEC.md` §8 gains a rung 0 for this; I will make that spec edit when this lands.**

**4 (urgent — a `not_found` for a company that exists, cached for an hour).** `src/registry_mcp/registries/se/mapping.py:74-90`. `is_not_found` scans **every** wrapped field for `fel.typ == "ORGANISATION_FINNS_EJ"` and returns `True` on the first hit. §6.3 says "on the identity-bearing fields". Consequence, reproduced here: an aktiebolag present at Bolagsverket but absent at SCB — the test workbook's own `5567223705` scenario, and the very number §17 tells T26d to record `bv_scb_only.json` from — returns `True` and the client raises `not_found` **and caches the negative for an hour**. Restrict the scan to the Bolagsverket identity-bearing fields (`organisationsnamn`, `organisationsform`, `organisationsdatum`), or require that *all* wrapped fields carry `ORGANISATION_FINNS_EJ`, or ignore any field whose `dataproducent` is `"SCB"`. `bv_finns_ej.json` satisfies all three, so test 96 keeps passing. Add a regression test built from `bv_ab_active.json` with `juridiskForm`/`verksamOrganisation`/`reklamsparr` carrying `ORGANISATION_FINNS_EJ`, asserting `is_not_found(...) is False`.

**5.** `src/registry_mcp/registries/se/rules.py:670-693` and `mapping.py:573-577`. A legal form that is *classified but computes nothing* — `BRF`, `HB`, `KB`, `E`, `S`, the banks and insurers, and any SCB-fallback code such as `49` — returns `deadlines == []` with **no note explaining why**. `core/models.py:467` documents the contrary contract ("An empty list is a real answer, not an error — read `notes` for why"), and `BRF` is one of the commonest forms on the Swedish register. Add a note, fired from `map_entity` alongside N6, when `status is ACTIVE` and `legal_form_code` is classified but not in `DEADLINE_FORM_CODES`: e.g. *"registry-mcp computes filing deadlines only for aktiebolag (AB) and ekonomiska föreningar (EK) — the two forms årsredovisningslagen 8 kap. 6 § names. {english} has real filing obligations that this module does not compute, because no primary source for them has been read."* Strengthens §14 test 71 and gives test 72 something to assert. (Spec gap as much as an implementation one — §2.1's N6 covers only *unclassified* forms.)

**6.** `src/registry_mcp/registries/se/mapping.py:193-196`. §3 says `country_code` is `"SE"` when `land` is **absent** or casefolds to sverige/sweden; the code sets it only on the string match, so a Swedish address with no `land` gets `country_code=None`. Two lines: `if land is None: country_code = "SE"`.

**7.** `src/registry_mcp/registries/se/rules.py:491-496`. `avregistreringsorsak.klartext` can be the literal `"n/a"` — Bolagsverket's own sole-trader example is exactly that — and it is rendered straight into `status_detail`: *"Struck off the Bolagsverket register on 2001-03-15 (VERKUPP: n/a)."* §2.4 rules that `"n/a"` must never be shown to a user. Treat `klartext` in `{None, "", "n/a"}` as absent and render `({kod})` alone.

**8.** `tests/test_client_se.py:691-695`, test 117. Restore the assertion §14 asked for: walk the live payload for every field name `mapping.py` reads, assert each is present or explicitly optional in §2, and record in the test's failure message (not `print`) which spelling of `pagaende…` and which `organisationsnamntyp` foreign-language code the wire uses. A missing field is a blocking finding for T26d, and as written this test cannot produce one.

**9.** `tests/test_rules_se.py:791-797`, test 74. Assert the 8 kap. 7 § sentence on a real report: `report = _map(pagaende…=_pagaende([{"kod": "KK", "fromDatum": "2024-01-26"}]))`, then `assert any("8 kap. 7 §" in n for n in report.notes)` — keep the direct `deadline_exemption_note` call as well.

**10.** `tests/test_rules_se.py:827-837`, test 78. Add the timezone half: run `deadlines_for` under two `TZ` values (`monkeypatch.setenv("TZ", …)` + `time.tzset()`) and assert equal lists.

**11.** `tests/test_mcp.py`. `tasks/T26.md` §T26b asks for a REST≡MCP parity test for SE; there is none. Copy `test_rest_and_mcp_lookup_company_are_identical_gb` (`:445`), drive `bv_ab_active.json` through `GET /v1/SE/company/5299999994` and the MCP `lookup_company` with the token and data routes mocked, and assert the two documents are equal except `fetched_at`. Sweden is the first country where the two surfaces have a second thing to agree on (N10 and the `source` suffix).

**12.** `src/registry_mcp/registries/se/client.py:365-368`. Any 4xx from the token endpoint becomes "This deployment has no Bolagsverket credentials" — which for a **429** is both wrong and misleading against the tightest rate limit in the project. Special-case `429` → `_rate_limited_error()` before the 4xx branch. (§6.1 says "4xx → upstream_error with the no-credentials hint", so this is a spec correction too; I will make it.)

**13.** `src/registry_mcp/registries/se/client.py:370-371`. `body["access_token"]` raises `KeyError` — not a `RegistryError` — on a 200 whose body is malformed or not JSON, and `response.json()` at `:522` has the same exposure on the data call. Wrap both and raise `upstream_error`.

**14.** `tests/test_client_se.py:679-689` and `:697-704`. Test 116's result reaches nobody without `-s`: raise it through `pytest.fail`/`warnings.warn`, or write it to a file T26d reads. Test 118 sets `os.environ["BOLAGSVERKET_ENVIRONMENT"]` without `monkeypatch`, leaking into the rest of the live run.

**15.** `src/registry_mcp/registries/se/rules.py:506-522` and `:737-836`. Two small losses: (a) when `pagaende…Lista` carries both a bucket-1 and a bucket-2 code (`[KK, FUOT]`), the bucket-2 note is discarded — §8 says "the lower rungs still fill their own fields and notes", so collect bucket-2 notes before returning the bucket-1 result; (b) `rules_markdown()` satisfies thirteen of §13's fourteen points but gives only examples of the organisationsform ↔ juridisk form mapping (`AB`/`TPAB` → 49, five → 51) rather than the published table `tasks/T26-recon.md` carries in full. Add it, with the existing "never run it backwards" warning.

### Recorded for the orchestrator, not a Sweden defect

**F4 — `ValidationResult.id_scheme` is the registry's class attribute, so `validate_company_id("SE", "194009272719")` returns `id_scheme: "organisationsnummer"` while its own `reason` explains that twelve digits are a personnummer.** §2.4 makes `id_scheme` per-record on `CompanyReport` and the module does that correctly; `ValidationResult` has no such hook — `core/registry.py:228` passes `self.id_scheme`. Sweden is the first country where one registry issues identifiers under more than one scheme, so this is the same shape of problem as F3: real, small, and a `core/` decision that should be taken when a second country needs it. **No core edit requested.**

**Verdict: APPROVED.** No test asserts anything the spec forbids, no fixture key is invented (verified against the OpenAPI document programmatically, not by eye), no credential or personnummer is written anywhere `registries/se/` controls beyond the four places §11 and §14 sanction, and neither surface crashes without credentials — both answer with the D-007 envelope and a hint naming both variables. The module is better than the spec required on the things that mattered most: the `pagaende…` misspelling is read at both nesting levels, the rate-limit bucket spends a token per attempt (Britain's does not), and §2.1's invariant holds exactly — a healthy, active, `verksam` `AB` with one name gets **exactly one** note. Fixes 1 and 2 are CI hygiene in the tests — a clock-dependent flake and two mypy narrowing artefacts — and neither touches the module. Fixes 3 and 4 are both "an absence rendered as a fact", which is this country's characteristic failure mode and the reason §1.6 opens the spec; neither is reachable from a fixture the suite currently ships, which is why the tests are green and the review is not. **Fixes 1–4 should land before T26d touches the wire**, because fix 4 will fire on the first live call §17 tells T26d to make (`5567223705`, "Aktiebolag, organisation finns ej hos SCB"). T26c is not blocked by any of them.

---

## T26f + T28 + T29 — 2026-09-06 — APPROVED WITH FIXES

Three changes reviewed together on `main` at `32e157c`: **T26f** (`f76c43e`, the fifteen T26e
fixes), **T28 = F1** (`b363f16`; `ad6e625` + `e398451`, D-040), **T29 = R-2** (`f8d9db1`,
D-026(a),(b)). Every row below was executed — probe scripts under a scratch directory with
`REGISTRY_MCP_LOG_PATH`/`REGISTRY_MCP_CACHE_PATH` pointed away from `./data`; nothing was
committed into `tests/`, no server was started, `api.foretak.dev` was never called.

**Environment, observed:**

```
uv run pytest -m "not live" -o addopts=""   618 passed, 11 deselected, 1 warning in 17.03s
uv run mypy .                               Success: no issues found in 61 source files
uv run ruff check .                         All checks passed!
uv run python evals/run.py --golden         28 passed, 0 failed, 3 skipped out of 31
```

All four match the expected values. 629 tests collect in total; the 11 live tests collect
cleanly (their helper names `client_module._read_environment`, `_fetch_organisationer` and
`mapping._WRAPPED_FIELDS` all resolve), so nothing in T26f's live-test rewrite will
`AttributeError` when T26d runs them.

### A. T26f — the fifteen T26e fixes

| # | Fix | Verdict | How it was checked |
|---|---|---|---|
| 1 | `test_41` pops `fetched_at` before the `"49"` scan | **PASS** | Built the test's report three times 10 ms apart: the dump is byte-identical after the pop, `"49"` is absent, and no clock-derived value survives anywhere in the document (`registered_at` etc. are all fixture-derived) |
| 2a | `test_52` asserts the negative first | **PASS** | `mypy .` clean (was 2 errors); test passes |
| 2b | `is_closed` read into annotated locals | **PASS** | `mypy .` clean; the `_tokens == {}` assertion is now reachable and type-checked |
| 3 | §8 rung 0 — a blocked status-bearing field → `UNKNOWN` | **PASS**, with a residual (fix 2 below) | `bv_uppgiftskalla_fel.json` now maps to `status=unknown`, `is_active=False`; `status_detail` is **byte-identical** to SWEDEN_SPEC §8's string; N13 still fires. Evaluation order matches the "Evaluation order" paragraph exactly: rung 1 (a real `avregistreringsdatum`) and rung 2 bucket 1 (a real `KK`) each still win over a co-occurring blocked field; a blocked **SCB** field (`verksamOrganisation`/`juridiskForm`/`reklamsparr`) never triggers rung 0 |
| 4 | `is_not_found` scoped to the three Bolagsverket identity-bearing fields | **PASS** | Seven cases executed: `ORGANISATION_FINNS_EJ` on `juridiskForm`+`verksamOrganisation`+`reklamsparr` of `bv_ab_active.json` → `False` (and still maps as an active `AB`); the same code on each of `organisationsnamn`, `organisationsform`, `organisationsdatum` → `True`; `bv_finns_ej.json` → `True`; empty `organisationer` → `True`; `bv_scb_only.json` → `False` |
| 5 | N14 for a classified form that computes nothing | **PASS** | Fires for `BRF`, `HB`, `KB`, `E`, `S` and for the SCB `juridiskForm` fallback code `49`; does **not** fire for `AB` (which gets N9 instead, via the `elif`), for an unclassified code (N6's case — `is_unclassified` correctly derived from `legal_form_info().notes`), or for a non-`ACTIVE` status. §2.1's one-note invariant for a healthy `AB` still holds: exactly one note |
| 6 | `country_code = "SE"` when `land` is absent | **PASS** | `None`, missing key, `"Sverige"`, `"Sweden"`, `"  sverige  "` → `"SE"`; `"Norge"` → `None` |
| 7 | `"n/a"` `klartext` never rendered | **PASS** | `"n/a"`, `"N/A"`, `" n/a "`, `""`, `None` all render `(VERKUPP).`; a real `klartext` still renders `(VERKUPP: Verksamheten har upphört).`; `bv_enskild_two.json` — Bolagsverket's own `"n/a"` example — is clean |
| 8 | Test 117 walks the live payload for every field `mapping.py` reads | **PASS (by inspection; live)** | Asserts presence of every `_WRAPPED_FIELDS` entry plus `organisationsidentitet`/`namnskyddslopnummer`, treats the two `pagaende…` spellings as one logical field, and puts the missing list in the assertion message. A missing field now fails the test rather than passing silently |
| 9 | Test 74 asserts 8 kap. 7 § on a real mapped report | **PASS** | Executed |
| 10 | Test 78 runs `deadlines_for` under two `TZ` values | **PASS** | Executed; restores the original `TZ` in a `finally` |
| 11 | SE REST≡MCP parity test | **PASS** | `test_rest_and_mcp_lookup_company_are_identical_se` compares the **whole documents** as dicts, minus `fetched_at` — so it also covers T29's two new keys for free, and `bv_ab_active.json` carries `reklamsparr: JA`, so the `advertising_protected=True` + N4 path is exercised across both surfaces |
| 12 | Token endpoint 429 → `rate_limited`, before the 4xx branch | **PASS** | Executed against a mock transport: 400/401/403 → `upstream_error` + the no-credentials message; **429 → `rate_limited`**; 500 → `upstream_error` naming the status |
| 13 | A malformed 200 body → `upstream_error`, never a bare `KeyError` | **PARTIAL — see fix 4** | Non-JSON and empty bodies, and a JSON object without `access_token`, are wrapped correctly on both the token and data calls. A body that is **valid JSON but not an object** still escapes as a raw `TypeError`/`AttributeError` |
| 14 | Test 116 uses `warnings.warn`; test 118 uses `monkeypatch` | **PASS (by inspection; live)** | Both correct; test 118 no longer leaks `BOLAGSVERKET_ENVIRONMENT` into the rest of the live session |
| 15a | A bucket-2 note survives a bucket-1 result | **PASS** | `[KK, FUOT]` → `status=bankrupt`, `bankruptcy_date=2024-01-26`, and the FUOT "acquiring party" note is present |
| 15b | The full `organisationsform` ↔ juridisk form table in `rules_markdown()` | **PASS** | All 24 rows present, `FL`/`BFL` marked "none", the four codes absent from Bolagsverket's table named, and the "never run it backwards" warning kept and repeated after the table |

### B. T28 = F1 (D-040)

| # | Contract item | Verdict | How it was checked |
|---|---|---|---|
| 1 | Exactly one `record_call(` per surface, both via `loggable_query` | **PASS** | `grep -n "record_call(" src/registry_mcp/api/main.py src/registry_mcp/mcp/*.py` → exactly two hits, `api/main.py:95` and `mcp/server.py:137`; both pass `query=loggable_query(...)`. No other `query=` in either surface reaches the logger |
| 2 | Every SE identifier-bearing path logs `query=None` | **PASS** | Driven offline with `record_call` spied on both modules and every registry's `lookup`/`search` stubbed to raise: REST `lookup`/`deadlines`/`validate`/`search`, MCP `lookup_company`/`company_deadlines`/`validate_company_id`/`search_company` (and with `country="se"` lower-cased), connector `fetch("SE:194009272719")`, `fetch("se:…")`, `fetch("SE:19400927-2719")`, `fetch("194009272719")` (bare, no prefix — the D-031(c) short-circuit), `search("SE 194009272719")` and `search("194009272719")` — **all `query=None`, `country="SE"`** |
| 3 | NO/GB still log the raw company number | **PASS** | REST `lookup`/`deadlines`/`validate` for NO and GB, MCP the same, and `fetch("NO:923609016")` all log `query="923609016"` / `"00000006"`; `search("Equinor")` logs `"Equinor"` |
| 4 | `loggable_query` never raises | **PASS** | 14 inputs: `"ZZ"`, `""`, `None`, `"se-"`, `"S"`, `"SWE"`, `("SE", None)`, mixed case — none raised; unknown/`None`/empty country all pass `query` through unchanged, `"se"`/`"sE"`/`"  se  "` all redact |
| 5 | Dockerfile CMD: `--no-access-log` on the uvicorn branch, stdio untouched | **PASS** | `CMD ["sh","-c","if [ -n \"${PORT:-}\" ]; then exec uvicorn … --no-access-log; else exec registry-mcp; fi"]`; the `else` branch is character-for-character what it was |
| 6 | `legal/privacy.md` gained exactly one sentence, true of the code | **PASS**, conditionally — see fix 1 | `git diff --stat` = 1 insertion, 1 deletion, one bullet reflowed, one sentence added. It is true of every route keyed to `country="SE"`. It becomes unambiguously true once fix 1 lands; today a Swedish personnummer can still be written to `calls` under `country=None`/`NO`/`GB` via the connector `search` alias |
| 7 | `core/stats.py` / dashboard cope with NULL queries | **PASS** | Wrote two `query IS NULL` SE rows and one NO row directly: `total_calls=3`, `calls_today=3`, `by_surface` counts all three, `top_queries` returns only the NO row. `GET /v1/stats/dashboard?key=…` renders 200/9726 bytes with the NULL rows present and no `None`/`null` literal in the top-queries table |
| 8 | Nothing in `registries/se/` beyond the one line | **PASS** | `git diff ad6e625~1 ad6e625 -- src/registry_mcp/registries/se/` is exactly `+    id_may_be_personal: ClassVar[bool] = True` |
| 9 | F2: `core/registry.py` docstring example | **PASS** | `core/registry.py:15` is `id_example = "5560160680"`; `5560212524` appears nowhere in the repo |

### C. T29 = R-2 (D-026(a),(b), D-036)

| # | Contract item | Verdict | How it was checked |
|---|---|---|---|
| 1 | Both keys present and `null` in `model_dump(mode="json")` for NO and GB | **PASS** | Three brreg fixtures and four Companies House fixtures mapped: `"euid" in d` and `"advertising_protected" in d` both `True`, both values `None`. Field order is what D-026 asked for: `euid` is the key immediately after `id_scheme`, `advertising_protected` immediately after `phone`, in the serialised document |
| 2 | The validator | **PASS** | `True` + a note containing "direct marketing" constructs, in lower, UPPER and Mixed case; `True` with an unrelated note or with `notes=[]` raises `ValidationError`; `False` and `None` and the omitted default all construct with no note. `model_validate` of a round-tripped document with `notes` stripped also raises — the constraint survives serialisation, not just construction |
| 3 | Sweden's mapping | **PASS** | `JA` → `True` **and** N4; `NEJ` → `False`, no N4; absent → `None`; blocked by `fel` (`OTILLGANGLIG_UPPGIFTSKALLA`, `TIMEOUT`, `ORGANISATION_FINNS_EJ`) → `None`. Also checked: an unrecognised `kod` → `None` (not `False`), and `JA` arriving alongside a `fel` → `None` (the `_FieldReader` refuses the value, correctly). All five committed SE fixtures map as expected; `euid` is `None` on every one |
| 4 | `euid` description | **PASS** | Carries all three traps — not the LEI (with the register-issued/mandatory/EU-only/free vs voluntary/global/LOU-issued/fee-bearing contrast), the "EUid" Digital Identity wallet, and instability across a register reorganisation with the RNE/RCS worked example — and ends "Carried verbatim from the register; never constructed from parts." Repeated accurately in `static/llms-full.txt` |
| 5 | `advertising_protected` description | **PASS** | States all three values in D-026(b)'s exact terms, says "it must never default to False, since False asserts a claim about a register that made none", and names the "direct marketing" phrase as the contract the validator enforces |
| 6 | `server-card.json` `outputSchema` and `_COMPANY_EXAMPLE` | **PASS on substance; the commit message's claim is inaccurate** | The embedded schema is **not** equal to `CompanyReport.model_json_schema()` (876 lines vs 99 — the raw schema uses `$defs`/`$ref`). It **is** equal, exactly, to `dereference_refs(CompanyReport.model_json_schema())`, which is what FastMCP's `DereferenceRefsMiddleware` actually puts on the wire and what `test_tool_output_schemas_match_models` compares against. So the file is right and the commit message's "byte-verified against `CompanyReport.model_json_schema()`" is not. `_COMPANY_EXAMPLE` validates as a `CompanyReport`, contains no key that is not a model field, and its key order matches the model's |
| 7 | README / `static/llms-full.txt` | **PASS** | Both examples carry the two keys as `null` in model order; the README paragraph and the llms-full "Five fields deserve special attention" block (which does now describe exactly five) are accurate — "Norway and the UK, today" is true, "Finland hands one over unprompted, ours do not yet" is true, and neither claims we construct a EUID |
| 8 | `legal/terms.md` | **PASS** | The sentence is a term we impose on the caller, not a claim about the data, and it matches D-026(b): the marking is a condition of the transfer, contact details are **not** withheld, and the `notes` sentence must not be stripped. It does not over-claim — it never says we suppress anything |
| 9 | CHANGELOG "Unreleased" | **PASS** | Says additive, `null` by default, no existing key changed, and names the validator in the same entry so the one genuine behaviour change is not hidden |
| 10 | `registries/no/`, `gb/`, `xx/` untouched | **PASS** | `git diff --stat ac44419 32e157c -- …/no …/gb …/xx` is empty |
| 11 | REST≡MCP parity with the new keys | **PASS** | The three parity tests compare whole documents (dict equality minus `fetched_at`), so no new test was needed and none was added — correct restraint |

### Fix list — owner: a Sonnet, dispatched by the orchestrator

**1 (blocking — a personnummer reaches the usage log from a surface that is deployed today).**
`src/registry_mcp/mcp/connector.py:654-658`. The `search` alias redacts only when the **whole
remaining text** validates for a flagged registry. It therefore leaks on every query where the
identifier is one token among several. Executed, offline, with `record_call` spied:

```
search("194009272719")            -> query=None                          (correct)
search("SE 194009272719")         -> query=None                          (correct)
search("194009272719 AB")         -> query='194009272719 AB'             LEAK
search("orgnr 194009272719")      -> query='orgnr 194009272719'          LEAK
search("Sweden 194009272719")     -> query='Sweden 194009272719'         LEAK
search("194009272719, Stockholm") -> query='194009272719, Stockholm'     LEAK
search("NO 194009272719")         -> query='NO 194009272719'             LEAK
search("GB 194009272719")         -> query='GB 194009272719'             LEAK
```

`"Sweden"` does not derive SE because `_derive_country`'s name match is against
`country_info().name`, which is `"Bolagsverket (Sweden)"`, not `"Sweden"`; and when an explicit
`NO`/`GB` token *is* present, `candidates` is narrowed to that one registry, so scanning
`candidates` cannot see SE at all. The implementation is faithful to D-040(b) *as written* — its
two triggers are "the derived country's flag" and "any flagged registry validating **the text**"
— but D-040(b) as written does not achieve F1's stated goal, and its own justifying sentence
("an agent that types a personnummer into `search` has typed a personnummer") condemns exactly
these cases. **Change:** scan the maximal alphanumeric runs of the query against every *live
flagged* registry, not the whole remainder against `candidates`:

```python
_ID_RUN = re.compile(r"[0-9A-Za-z\-]+")   # module level, beside the other constants
...
# D-040(b): blanket, by registry flag, never by digit count (D-040(d)). Every
# maximal alphanumeric run of the query is checked against every *live flagged*
# registry — not just `candidates`, which an explicit "NO"/"GB" token narrows to
# one unflagged registry, and not just `remainder`, which is the whole string
# whenever `_derive_country` missed. `Registry.validate` is pure and cheap.
flagged = [r for r in registries if r.id_may_be_personal]
if flagged:
    runs = {stripped, remainder, *_ID_RUN.findall(stripped)}
    if any(r.validate(run).valid for r in flagged for run in runs if run):
        outcome.query = None
```

Verified against 34 inputs: it closes all eight leaks above plus `"(194009272719)"`,
`"id=194009272719"`, `"194009272719."`, `'"194009272719"'`, `"Bygg AB, 5560160680"` and
`"https://x/194009272719"`, and over-redacts **nothing** — `"Equinor"`, `"Tesco PLC"`,
`"Ostermalm Bygg AB"`, `"923609016"`, `"NO 923609016"`, `"00445790"`, `"GB 00445790"` and
`"SE Ostermalm Bygg"` all still log their text verbatim. `outcome.country` stays whatever
`_derive_country` produced — do not invent one. Two residuals remain and should be **left
open**, with a comment saying so: `"x194009272719"` and `"1940092727191234"`, where the number
is glued to other alphanumerics with no separator. Closing those needs a substring/shape scan,
which is precisely what D-040(c) declined. Add to `tests/test_connector.py`, beside the existing
D-040 tests: `search("194009272719 AB")`, `search("NO 194009272719")` and
`search("orgnr 194009272719")` log `query=None`; `search("Equinor")` and `search("NO 923609016")`
still log their text. **The orchestrator, not the implementer, adds the D-040(b) amendment
recording the third trigger.**

**2 (urgent — the residue of T26e fix 3, on the one path fix 3 did not reach).**
`src/registry_mcp/registries/se/rules.py:604-611`. `derive_status`'s bucket-2-only branch
returns `ACTIVE` / `is_active=True` / `_ACTIVE_DETAIL` without ever consulting
`unavailable_producer`. Executed: a payload with `pagaende…Lista = [FUOT]` (a healthy acquiring
company, so rung 2 explicitly "leaves status alone") **and** `avregistreradOrganisation` +
`avregistreringsorsak` blocked by `fel` returns

```
status: active | is_active: True
detail: "Registered with Bolagsverket and not marked as struck off or in any winding-up or
         restructuring procedure."
```

— an affirmative "not struck off" from a payload in which the struck-off fields never arrived.
SWEDEN_SPEC §8 rules that bucket 2 leaves the status alone, so this result is rung 3's, and
"rung 0 is what licenses rung 3's wording". **Change:** move the `unavailable_producer` check so
it also guards this return — simplest is to hoist it into a small local closure, or to add the
same three-line `if unavailable_producer is not None:` block immediately before the
`return StatusResult(status=CompanyStatus.ACTIVE, …, notes=notes)` at `:604`, carrying `notes`
(the bucket-2 sentences) through into the `UNKNOWN` result rather than dropping them — §8's
"the lower rungs still fill their own fields and notes" applies to rung 0 as much as to rung 2.
Test, in `tests/test_client_se.py` as `test_126_…`: `[FUOT]` present, `avregistreradOrganisation`
blocked → `status is UNKNOWN`, `is_active is False`, `status_detail` names the producer, and the
FUOT note is still in `notes`. Note the practical reachability caveat honestly in the docstring:
Bolagsverket's own partial-failure example fails a whole *data producer* at once, which would
block `pagaende…` too; this combination needs a per-field failure, which §1.6 models but the one
fixture we have does not exercise. **SWEDEN_SPEC §8's "Evaluation order" paragraph needs one
clause added by the architect: rung 2 bucket-2-only does not count as "rung 2 fired".**

**3 (urgent — a personnummer in Railway's log stream, on two paths D-040 did not consider).**
Two sinks, both pre-existing and both outside T28's footprint, both demonstrated by execution:

(a) `src/registry_mcp/api/errors.py:86` —
`logger.exception("Unhandled exception in %s %s", request.method, request.url.path)`. D-040(e)
closed uvicorn's access log precisely because `GET /v1/SE/company/<personnummer>` puts the number
in the path; this handler writes the same path to the same stream at ERROR. It is reachable
today: driving `GET /v1/SE/company/194009272719` against an upstream that returns a 200 with the
body `null` produced `Unhandled exception in GET /v1/SE/company/194009272719` verbatim (that
particular trigger is fix 4 below, but any unhandled exception on an SE route does it).
**Change:** log `request.url.path` only when the route is not identifier-bearing, or — simpler
and uniform — log `request.scope.get("route").path` (the *template*, `/v1/{country}/company/{id}`)
instead of the concrete path, plus `request.method`. The template is what a reader of that line
actually needs.

(b) `src/registry_mcp/core/cache.py:134` and `:168` —
`logger.warning("cache read failed for key %r", key, exc_info=True)`. The SE cache key is
`SE:bolagsverket:entity:prod:<identitetsbeteckning>` (`registries/se/client.py:486-491`), so any
cache I/O failure — a locked SQLite, a full volume — writes the personnummer to the application
log. Executed: forcing `_connect` to raise produced
`cache read failed for key 'SE:bolagsverket:entity:test:194009272719'` and the same for the write.
D-040's "Considered and left alone: the cache" reasoned about the cache *contents* (bounded,
required to serve the request) and did not notice that the *key* is logged unbounded. **Change:**
log the key's prefix only — everything up to and including the last `:` — or a stable
`hashlib.blake2s(key.encode(), digest_size=8).hexdigest()`; a hash is fine **here**, unlike in
`top_queries`, because nobody reads this line for the identifier, only to correlate two failures.
Neither of these needs a new decision to *fix*; the orchestrator should record them under D-040
so the next reader knows they were closed deliberately.

**4 (non-blocking — T26e fix 13 is incomplete).** `src/registry_mcp/registries/se/client.py:392-398`
and `:549-554`. Both guards catch `ValueError` (which covers `json.JSONDecodeError`) and, on the
token path, `KeyError` — but a 200 whose body is **valid JSON and not an object** escapes as a
raw exception. Executed:

```
token call, body b'[1,2,3]'  -> TypeError: list indices must be integers or slices, not str
token call, body b'"hello"'  -> TypeError: string indices must be integers, not 'str'
token call, body b'null'     -> TypeError: 'NoneType' object is not subscriptable
data  call, body b'[1,2,3]'  -> AttributeError: 'list' object has no attribute 'get'
data  call, body b'null'     -> AttributeError: 'NoneType' object has no attribute 'get'
data  call, body b'42'       -> AttributeError: 'int' object has no attribute 'get'
```

SWEDEN_SPEC §6.1 says "A 200 whose body is not JSON or lacks `access_token` → `upstream_error`,
never a bare `KeyError`", and this is the same failure one type further out. It is also the
trigger that makes fix 3(a) reachable. **Change:** on the token path add `TypeError` to the
`except` tuple; on the data path, after `data = response.json()`, add
`if not isinstance(data, dict): raise _malformed_response_error("the data request")`. Two tests
in `tests/test_client_se.py`, one per path, asserting `RegistryError(upstream_error)` for a
`b"null"` body.

**5 (non-blocking — the server card will drift silently).** There is no test pinning
`static/well-known/mcp/server-card.json`'s embedded `outputSchema` to the model. `tests/test_api.py`
only checks the file's content type and version. T29 is the third task to hand-edit that file
(after T17 and T26c) and the next model change will desynchronise it with nothing to catch it.
**Change:** add to `tests/test_mcp.py`, beside `test_tool_output_schemas_match_models`, a test
that loads the card, finds the `lookup_company` entry and asserts
`entry["outputSchema"] == dereference_refs(CompanyReport.model_json_schema())` — that equality
holds exactly today, so the test is green on arrival. Fix the commit-message-level claim in the
same breath: the card matches the **dereferenced** schema, which is what FastMCP serves, not the
raw `model_json_schema()`.

**6 (non-blocking — spec hygiene).** `SWEDEN_SPEC.md` has two sections numbered `### 2.6`:
line 638 ("VAT, and the field that would have made Sweden a VAT-verification country") and
line 666 ("`advertising_protected` and `euid`"). The architect's own edit in `95976f6` introduced
the collision, and `tasks/T29.md` cites "§2.6" ambiguously as a result. Renumber the second to
`### 2.7` and fix the three cross-references to it (`§14` test 122-125 preamble, §13 item 15,
`CORE_ROADMAP_SPEC.md` §4). Architect's fix, not a Sonnet's.

### Recorded for the orchestrator, not a fix for this task

**G1 — blanket-by-country protects the *country asked about*, not the *number typed*, and that
is the declared trade.** `lookup_company(country="NO", id="194009272719")` and
`fetch("GB:194009272719")` both log `194009272719` in full, because D-040(c)/(d) ruled the
protection by country and explicitly declined every shape-based alternative. Fix 1 closes the
`search` cases because `search` has no country in its contract; the country-bearing operations
are working as designed. Worth one sentence in D-040 so it is not rediscovered as a bug.

**G2 — FastMCP logs every tool call's arguments at DEBUG.**
`.venv/…/fastmcp/server/mixins/mcp_operations.py:240` —
`logger.debug(f"[{self.name}] Handler called: call_tool %s with %s", key, arguments)`. Off at
the default level, so this is latent, not live; but anyone who raises the level to debug a
production incident turns on personnummer logging as a side effect. `server.py:1505`'s
`logger.warning("Invalid arguments for tool %r: %s", name, detail)` echoes pydantic's error
detail, which includes the offending input — but our `id` is typed `str`, so a string never
reaches that branch. **Recommendation for T26d's go-live checklist:** one line saying the log
level must stay at INFO or above for the SE build.

**G3 — `X-Request-ID` and the rate limiter are clean.** `api/main.py:526` echoes the *caller's*
header or mints a UUID; it never contains our identifier. `api/ratelimit.py:88` keys its buckets
on `client_ip(request)` alone, never the path. Both checked, both fine — recorded so the next
review does not re-derive it.

**G4 — the validator matches `"direct marketing"` with a space only.** `"direct-marketing"`
raises. That is exactly what D-026(b) and the field description say, so it is correct as ruled —
but it is a trap for the author of the fourth country module, whose natural English is the
hyphenated adjective. Denmark's spec (T16) should quote the required phrase verbatim in its §1.

**G5 — F4 is still open.** `ValidationResult.id_scheme` remains the registry class attribute, so
`validate_company_id("SE", "194009272719")` still answers `id_scheme: "organisationsnummer"`
while its own `reason` explains the number is a personnummer. Unchanged by any of these three
tasks; still a `core/` decision for whenever a second country needs it.

### Praise, where it teaches something

**T28's `_CallOutcome` growing `country`/`query` is the right shape, and the reason is worth
keeping.** The obvious implementation would have had `fetch` and `search` each call
`loggable_query` themselves, which puts the redaction decision in two more places and guarantees
the third one gets forgotten. Making the *outcome object* carry the correction, and leaving the
single `loggable_query` call in the `finally`, means the connector aliases participate in the
choke point rather than duplicating it — and it is why fix 1 above is a change to one `if`
statement rather than to two call sites.

**T26f's `_LegalForm.is_unclassified` is derived, not stored twice.** It reads
`bool(info.notes)` — "`legal_form_info` returns a non-empty `notes` (N6) precisely and only when
the code is unclassified" — instead of re-testing membership in `ORGANISATION_FORMS`. Two
predicates that must agree have been collapsed into one, so N6 and N14 cannot drift apart. That
is the fix D-009(a) would have wanted.

**T29's validator earns its place by being enforced on `model_validate`, not only on
`__init__`.** Verified: a document round-tripped through `model_dump(mode="json")` with `notes`
emptied is rejected. A `model_copy(update=…)` still slips past, which is pydantic's documented
behaviour and not worth fighting; the wire path — which is the one CVR-loven § 19 cares about —
is covered.

**Verdict: APPROVED WITH FIXES.** T29 is clean: eleven contract items, eleven passes, nothing to
change in the code and only a commit-message claim to correct. T26f delivers fourteen of fifteen
fixes outright and the fifteenth (fix 13) in part; its rung-0 work is right, including the
judgement call on evaluation order, and its `status_detail` is byte-identical to the spec. T28's
choke point is correct on every path that names a country, and its `NULL` rows flow through
`stats.py` and the dashboard without a scratch — but the `search` alias, the one operation whose
contract has no country in it, still writes a Swedish personnummer to `calls` whenever the number
is one token among several, and that is the single thing F1 exists to prevent. **Fix 1 must land
before the push.** Fixes 2 and 3 should land before T26d touches the wire, for the same reason
T26e's fixes 3 and 4 had to: they are each "an absence rendered as a fact" or "a personal number
rendered into a log", and neither is reachable from a fixture the suite ships, which is why the
suite is green and this review is not. Fixes 4-6 can follow at leisure.
