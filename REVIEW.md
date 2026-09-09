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

## T32 — 2026-09-07 — CHANGES REQUIRED

Nineteen commits, `97ff85b..28efe77` (32 files), plus the *application* of the previous review's
fixes in `97ff85b` itself, which nobody had checked. Every row below was executed — probe scripts
under a scratch directory with `REGISTRY_MCP_LOG_PATH`/`REGISTRY_MCP_CACHE_PATH` pointed away from
`./data`, `record_call` spied, `respx` for transports. Nothing was committed; no file but this one
was written. `api.foretak.dev` was called read-only (GET only); Bolagsverket was never called
directly and `833286602` was never looked up.

**Working-tree caveat, honoured throughout.** Two agents are editing this tree. Every claim about
repository content is read from a commit (`git show <sha>:<path>`), never from the working file.
**`HEAD` moved under me mid-review**: it was `28efe77` when I started and is `6ece116` now
(T26h's `6b3158a` + `6ece116` landed at ~16:43). Findings 3 and 15 turn on that, and both say
which sha they mean.

**Environment, observed:**

```
uv run pytest -m "not live" -o addopts=""   630 passed, 11 deselected, 1 warning in 23.65s
uv run mypy .                               Success: no issues found in 61 source files
uv run ruff check .                         All checks passed!
```

630 is the expected count and it is **not** inflated by the Sonnet's uncommitted work: the two
test files it has open carry the same number of test functions at `HEAD` as in the working tree
(`test_client_se.py` 52/52, `test_rules_se.py` 88/88 — the Sonnet has rewritten bodies, not added
cases). The count is trustworthy.

### A. The application of the previous review's fixes (`97ff85b`) — never reviewed until now

| # | Fix | Verdict | How it was checked |
|---|---|---|---|
| 1 | `search` alias scans alphanumeric runs against every live flagged registry | **PASS, with a hole — finding 1** | 30 inputs through `connector.search` with `record_call` spied and every registry stubbed. All eight leaks the last review listed are closed, plus `"(194009272719)"`, `"id=194009272719"`, `"194009272719."`, `'"194009272719"'`, `"Bygg AB, 5560160680"`, `"https://x/194009272719"`, `"194009272719\xa0AB"`, `"194009272719/AB"`, `"Sok 194009272719 tack"`. Nothing over-redacts: `"Equinor"`, `"Tesco PLC"`, `"923609016"`, `"NO 923609016"`, `"00445790"`, `"GB 00445790"` all still log verbatim. Exactly the two documented residuals survive (`"x194009272719"`, `"1940092727191234"`, and the same-class `"AB194009272719"`). **But the block is unreachable on any exception — finding 1** |
| 2 | `derive_status` bucket-2-only honours a blocked producer | **PASS** | `[FUOT]` + `unavailable_producer="Bolagsverket"` → `unknown` / `is_active=False` / detail names the producer / **the FUOT bucket-2 note is carried through**. Rung 1 (`deregistered_at`) and rung 2 bucket 1 (`KK`) still win over a blocked producer (`deleted`, `bankrupt` with `bankruptcy_date` intact); the clean path is still `active` |
| 3a | `api/errors.py` logs the route template | **PASS** | Drove `GET /v1/SE/company/194009272719` against a registry stubbed to raise `RuntimeError`: the server log line is `Unhandled exception in GET /v1/{country}/company/{id}` — the number appears in no server-side record. (The one line in that capture containing the number came from `httpx`'s own client logger inside `TestClient`; in production our outbound SE calls are `POST` with the identifier in the body, so `httpx`'s INFO line carries no identifier) |
| 3b | `core/cache.py` logs the key prefix | **PASS** | `_key_prefix('SE:bolagsverket:entity:prod:194009272719')` → `'SE:bolagsverket:entity:prod:'`; `'nocolon'` and `''` → `''`; `'a:b'` → `'a:'` |
| 4 | Non-object 200 body → `upstream_error` | **PASS** | Tests 127/128 present and green; token path catches `TypeError` (covers `[1,2,3]`/`"hello"`/`42`/`null`/`true`), data path is an explicit `isinstance(data, dict)` gate that covers every non-object |
| 5 | Server-card `outputSchema` pinned | **PASS** | `test_server_card_lookup_company_output_schema_matches_model` exists, green, compares against `dereference_refs(...)` as recommended |
| 6 | `SWEDEN_SPEC.md`'s duplicate `### 2.6` | **PASS** | Renumbered: §2.6 VAT, §2.7 `advertising_protected`/`euid` |

Five of six applied faithfully. The sixth (fix 1) is applied correctly *where it runs*; it does
not always run. See finding 1.

### B. `fbd4792` — the SCB `sni` padding filter (orchestrator-authored)

| # | Check | Verdict | How it was checked |
|---|---|---|---|
| 1 | The predicate on a well-formed payload | **PASS** | The live shape (`"     "` × 4 + one real code) yields exactly the one real code |
| 2 | `kod` that is JSON `null` | **FAIL — finding 6** | `{"kod": None, "klartext": "Something"}` → `IndustryCode(code="None", …)`. `item.get("kod", "")` returns `None` (the key exists), `str(None)` is `"None"`, which is truthy, so it survives the filter *and* is emitted as the literal string `None` |
| 3 | `kod` missing entirely | **PASS** | → dropped (the default `""` fires) |
| 4 | `kod` that is `"0"` or `0` | **PASS** | Both survive as `"0"` — correct: a zero code is a code, and the predicate tests whitespace, not falsiness |
| 5 | `kod` that is a non-string (`47642`) | **PASS** | → `"47642"`, correctly coerced |
| 6 | Re-ranking from 1 | **PASS** | `["70100", blank, "47642", blank, blank]` → ranks `[1, 2]`. Nothing renumbers a *genuinely* ranked list, because SCB's ranks are positional, not carried: the source objects have no rank field, `enumerate` was always the only source of `rank`, and dropping a blank slot from between two real codes is exactly the renumbering you want. Verified no consumer reads `rank`: `mcp/connector.py:445-453` renders `industry_codes` by **list index**, not by `rank`, so order and rank cannot disagree |
| 7 | `description=(klartext or None)` losing a legitimate falsy value | **PASS (no realistic loss)** | `klartext` is prose. `""` → `None` is the intent; `0` → `None` is the only other reachable case and a numeric description is not a thing SCB emits. Cosmetically `x if x else None` would be more honest than `or`, but nothing is lost |
| 8 | Non-`Mapping` items | **PRE-EXISTING, unchanged** | `{"sni": ["70100"]}` and `{"sni": {"kod": "x"}}` both raise `AttributeError`. The commit neither introduced nor worsened this, and `map_address` has the same house style. Recorded, not charged to this commit |
| 9 | Tests 129/130 | **PASS** | Both assert the right things (codes, contiguous ranks, and `all(c.description for c in codes)` which would catch the description regression). Both green |
| 10 | Spec bookkeeping | **FAIL — finding 13** | `SWEDEN_SPEC.md` §14's numbered list jumps 125 → 129; tests 126/127/128 (added by `97ff85b`) were never written into it, and 129/130 were inserted *above* the stray item 98 |

**Verdict on `fbd4792`: the fix is right, the tests are right, and it should not have needed a
dispatch.** One genuine defect (finding 6) and one bookkeeping miss.

### C. `056bd6c` — GB test 105 rewritten from wall-clock to overlap (orchestrator-authored)

I mutation-tested this rather than reading it, because "does the assertion have teeth" is not a
question inspection answers. Control plus three mutations, driven through the real client with
`respx`:

```
control (real bucket)                        peak_in_flight=2   assert==2 PASSES
M1  capacity-1 bucket (_TokenBucket(1.0,2.0)) peak_in_flight=1   assert==2 FAILS
M2  lock held across the whole HTTP call      peak_in_flight=1   assert==2 FAILS
M3  bucket sleeps 1 s per acquire, concurrent peak_in_flight=2   assert==2 PASSES  (wall clock 1.05 s)
```

| # | Check | Verdict | How it was checked |
|---|---|---|---|
| 1 | Does it prove non-serialisation? | **PASS** | M1 and M2 above are the two realistic ways the bucket could serialise, and both fail the new assertion. It is a mutation-killing test, not a tautology |
| 2 | Could a serialising bucket pass? | **PASS (no)** | Only if it serialised *after* a burst of two, which is not what "serialising" means here and was not asserted by the old test either |
| 3 | Is the `respx` async `side_effect` sound? | **PASS** | Runs (0.17 s for the single test), and `peak_in_flight == 2` proves both handlers were entered — a side-effect that never fired would leave `peak_in_flight == 0` and fail loudly |
| 4 | Is `nonlocal` counting race-free? | **PASS** | asyncio is single-threaded and there is no `await` between `in_flight += 1` and `peak_in_flight = max(...)`, so the read-modify-write cannot interleave. It is also **deterministic, not timing-dependent**: `gather` has both tasks queued before the first one yields at `sleep(0.05)`, so the second is scheduled immediately regardless of runner load — which is precisely why this replacement is right and the old bound was not |
| 5 | Did the rename lose coverage? | **PARTIAL — finding 12** | Yes: M3 above. A bucket that adds a full second of latency per acquire but stays concurrent now passes; the old `elapsed2 < 1.0` would have caught it (1.05 s). "Fast" is now asserted nowhere — `grep -rn "_TokenBucket" tests/` finds one direct unit test for the **SE** bucket (`test_bucket_exhaustion_raises_rate_limited`) and **none** for GB's |

**The judgement was correct even so.** The old bound could not distinguish "the bucket is slow"
from "the runner is slow" — that is why it fired at 1.17 s on an unrelated commit — so it was
never really testing the property it named. Trading an untrustworthy assertion for a
deterministic one is right; the residue is that nothing replaced the discarded half.

### D. `4fd1c92` — the 0.3.0 release

| # | Check | Verdict | How it was checked |
|---|---|---|---|
| 1 | All 13 occurrences moved | **PASS** | Counted from the diff: `marketplace.json` 1, `mcpb/manifest.json` 1, `packages/brreg-mcp/pyproject.toml` 2, both npm `package.json` 1 each, `plugin.json` 1, `pyproject.toml` 1, `server.json` 3, `__init__.py` 1, `server-card.json` 1 = **13 across 10 manifests**, plus `uv.lock`. The commit message's arithmetic is exact |
| 2 | Nothing missed | **PASS** | `grep -rn '0\.2\.0'` over the tree excluding `.venv`, `.git`, `uv.lock`, `CHANGELOG.md` and `research/` leaves only true statements about *published* artefacts: `SUBMISSIONS.md` (MCP registry is still 0.2.0 — true), `HUMAN_TODO.md:79` ("PyPI, npm — 0.2.0 since 2026-09-04" — true), `KEYWORDS.md:187` ("no tag has been pushed, so all three indexes still serve 0.2.0" — true), and `PROGRESS.md`/`tasks/`/`research/` history. No version-bearing file was missed |
| 3 | `packages/brreg-mcp` pin vs PyPI | **PASS on "not broken", FAIL on "not a trap" — finding 5** | Executed against PyPI: `registry-mcp` has `['0.1.0','0.2.0']`, `brreg-mcp` has `['0.1.0','0.2.0']` and the **published** `brreg-mcp` 0.2.0 still declares `requires_dist: ['registry-mcp==0.2.0']`. So no published package is broken. `packages/brreg-mcp` is not in the root workspace (`pyproject.toml` declares no `[tool.uv.workspace]`), so no `uv lock`/`uv sync`/CI job resolves it — CI is not red |
| 4 | CHANGELOG accuracy | **FAIL — finding 9** | The 0.3.0 heading was inserted *above* the whole pre-existing `[Unreleased]` body, so `[Unreleased]` is now empty and the 0.3.0 section swallowed it |
| 5 | Does the CHANGELOG under- or over-sell the logging change? | **Over-sells by exactly one path** | "for such countries the usage log now stores no identifier at all" is true of every route keyed to `country="SE"` — I re-verified the REST and MCP paths — and it is *not* true of the connector `search` alias whenever an exception escapes (finding 1). Otherwise the bullet is precise: "the uvicorn access log is off" (`Dockerfile:79` carries `--no-access-log`), "route template rather than the request path" and "cache failures log only a key prefix" are all verified true above. It does **not** under-sell: it correctly does not claim protection for `lookup_company("NO", <personnummer>)`, which D-040(c)/(d) rule out by design |
| 6 | Is the 0.3.0 "Fixed" list complete? | **Minor gap** | It omits the `97ff85b` SE `derive_status` change, which turns some payloads from `active` to `unknown` — a user-visible status change that shipped in 0.3.0. Everything else from `0.2.0` forward is either covered or subsumed by "Sweden is new" |

### E. `0f952bc` — the go-live text

| # | Check | Verdict | How it was checked |
|---|---|---|---|
| 1 | `_DESCRIPTION` is true of the deployed service | **PASS** | Live `GET /openapi.json`: `info.version == "0.3.0"`, description contains "Three countries answer today", names Sweden and Bolagsverket, and the Swedish keywords are present. Every factual clause checks out against the live service: `/v1/UK/…` is documented as a 404, `/v1/countries` names `requires_api_key`/`api_key_env` (verified live for all three), and "name search is not offered because the register publishes no name index" matches live `GET /v1/SE/search?q=ericsson` → `501 not_implemented` |
| 2 | Does any string still say two countries? | **FAIL — findings 2, 3, 10** | Six do, all at `28efe77`: `static/well-known/mcp/server-card.json`'s `search` tool description, `static/index.html` (**zero** mentions of Sweden or Bolagsverket — and still zero at `6ece116`), `server.json`'s `description`, `mcpb/manifest.json` (description, `long_description`, and the phrase "both countries"), `.claude-plugin/marketplace.json`, `plugins/registry-mcp/.claude-plugin/plugin.json`. The commit's "three countries everywhere" is not true |
| 3 | Did the connector docstring change alter tool-schema behaviour? | **PASS on behaviour, FAIL on consistency — finding 2** | The docstring is the tool's `description` only; `output_schema=ConnectorSearchResponse.model_json_schema()` and the `annotations` are untouched, and `tests/test_mcp.py::test_tools_list_has_five_registry_tools_plus_two_connector_aliases` and the annotation test are both green. But the *wire text* changed and the server card was not regenerated |
| 4 | Is the README example real? | **PASS** | Compared field by field against live `GET /v1/SE/company/5560160680` and `…/deadlines?today=2026-09-07`: name, `legal_form_code`/`legal_form`/`legal_form_local`, `registered_at` 1918-08-19, the single `70100` industry code, `postal_code` 16483 / `STOCKHOLM`, the licence string, `published_deadlines: []`, and both deadlines with `days_until` 296 and 327 and `rolled_forward: false` all match exactly. It was generated from the server, as claimed |
| 5 | README prose | **One gap** | The Swedish JSON block is abridged (≈20 of 50 keys) but, unlike the GB block above it, carries no "Abridged —" sentence. A reader is shown a `$ curl` and a body that command does not return |

### F. The deployment — `https://api.foretak.dev`, read-only GET only

| Endpoint | Result |
|---|---|
| `/health` | `{"status":"ok","version":"0.3.0","countries":["GB","NO","SE"]}` — **correct** |
| `/status` | 200, HTML: "Version 0.3.0 · Uptime 52m 48s · Countries GB, NO, SE" — **correct** |
| `/v1/countries` | Three entries; SE carries `requires_api_key: true`, `api_key_env: "BOLAGSVERKET_CLIENT_ID"`, the licence string, and the correct `id_description` including the sole-trader personnummer caveat — **correct** |
| `/v1/SE/company/5560160680` | 200, Ericsson, `active`, `AB`, **exactly one** industry code (`fbd4792` is deployed), 1 note, `cached: true`, `fetched_at 2026-09-07T12:05:10Z` — **correct**, and consistent with the 12:03Z deploy |
| `/v1/SE/company/5560160680/deadlines?today=2026-09-07` | Both deadlines, statutes cited, `rolled_forward: false`, `days_until` 296/327 — **correct** |
| `/v1/SE/search?q=ericsson` | `501 not_implemented`, hint names `lookup_company`, the example identifier, `validate_company_id` and the bulk files — **correct** |
| `/v1/SE/validate/5560160680` | `valid: true`, `formatted 556016-0680`, the "a valid identifier does not mean the entity exists" reason — **correct** |
| `/openapi.json` | 0.3.0, three countries — **correct** |
| `/.well-known/mcp/server-card.json` | `serverInfo.version 0.3.0`, but the `search` tool description says "(Norway, United Kingdom)" — **finding 2** |
| `/llms.txt` | 1950 B, **zero** mentions of Sweden or Bolagsverket — **finding 3** |
| `/llms-full.txt` | 50988 B, documents `/health` as `{"status": "ok", "version": "0.2.0", "countries": ["GB", "NO"]}`, zero mentions of Sweden — **finding 3** |
| `/server.json` | `version 0.3.0` and **both** `packages[].version` at `0.3.0`, neither of which exists on PyPI or npm — **finding 4**. Description still names two countries |
| `/` (index.html) | 19468 B, zero mentions of Sweden — **finding 10** |
| `/robots.txt` | 200, 23 B |

Both `/llms.txt` and `/llms-full.txt` were re-fetched with `Cache-Control: no-cache` and a
cache-busting query string; the stale bytes are what the origin serves.

### G. The document commits, and the secret sweep

| # | Check | Verdict | How it was checked |
|---|---|---|---|
| 1 | A phone number in the repo | **PASS — clean** | `git grep -E '(\+46\|\+47\|\+45)[ -]?…'` and the Nordic 8-digit patterns over the whole tree at `28efe77` (excluding `research/`): **zero hits**. `HUMAN_TODO.md:127` records that a "mobile number [was] given" on the kundanmälan without recording the number. Correct discipline |
| 2 | Any credential written down | **PASS — clean** | No `client_secret=`, no `BOLAGSVERKET_CLIENT_SECRET=<value>`, no bearer token, no `ghp_`/`sk-`. The TEST credentials are referenced by path (`~/secrets/registry-mcp/bolagsverket-test.txt`) — a pointer outside the repo, which is right. `HUMAN_TODO` correctly records that the two `[DEL 2]` zip codes are sitting in plaintext in Gmail and must be deleted |
| 3 | `d9d9cd2` / `8acca8b` / `b1ab823` / `eeb6d2b` | **PASS** | All four are consistent with each other and with the credential-mail quotes they carry (`"Observera att ett inaktivt konto avslutas efter 6 månader"`, the `portal.` token endpoint). The "zip codes came by e-mail, not SMS" deviation is recorded as a deviation, which is the honest form |
| 4 | `3a22375` / `6ad723b` (Denmark) | **PASS** | Internally consistent: reply 06:52Z, application submitted 13:48:18 Danish time the same day, ~3 weeks to access, sagsnummer #177481 carried through both, and the IP-whitelisting question is correctly left recorded as open in both `HUMAN_TODO` §7.6 and `PROGRESS` T16 rather than being quietly dropped |

### H. `28efe77` — D-041 and `tasks/T31.md`, read critically

| # | Check | Verdict | How it was checked |
|---|---|---|---|
| 1 | D-041's second claim: `deadlines_for` never reads `published_deadlines` | **CONFIRMED — the orchestrator is right, and it is worse than stated** | `grep -n "published_deadlines" src/registry_mcp/registries/se/rules.py` → **zero hits** (GB's `rules.py:642` has `published = {pd.kind: pd for pd in report.published_deadlines}`, so the contrast is visible in the same repo). And `deadlines_for` calls `_general_meeting(today)` / `_annual_accounts(today)` — the helpers do not even *receive* `report`. So `SWEDEN_SPEC.md` line 993's "It is implemented anyway — three lines — so that the day a due date does appear the module prefers it without a redesign" is false twice over: it is not implemented, and adding it *is* a signature change to both helpers |
| 2 | Does D-041 under-count the false-claim sites? | **YES, by two more than the orchestrator found — finding 8** | Full sweep of shipped strings at `28efe77`: `registries/se/rules.py` ×4 (lines 675, 690, 704, and 978's "the financial-year end" in `rules_markdown()`), `mcp/server.py` ×1, `static/well-known/mcp/server-card.json` ×1, `README.md` ×1 — **D-041's "seven across four files" is exactly right for what it names**. Missed: `static/llms-full.txt` ×2 (the orchestrator found these), **`CHANGELOG.md` ×1** (line 152, inside the 0.3.0 entry — found by nobody), and **`content/reddit-sweden-developers-post.md` ×1** (found by nobody; new at `6ece116`, so T26h is writing the false sentence into fresh content *right now*). True total: **11 shipped strings across 7 files.** `SWEDEN_SPEC.md` also has a fourth site D-041 does not name — §13's `rules_markdown()` item at line 1704, beside the §5.4.2/§5.4.3/§5.4.4 three it does |
| 3 | Is D-041 self-consistent about the count? | **NO — finding 8** | (a) says "**seven** shipped strings across four files"; (i) says "it is **six** strings"; the "Applies to tasks" line says "(a)'s **six** strings". Three statements, two numbers, and the real answer is eleven |
| 4 | D-041's technical rulings | **PASS on everything checkable offline** | `CompanyReport.last_annual_accounts_year` exists and is `None` for SE; `PublishedDeadline`'s docstring does say what (c) quotes; `core/registry.py::deadline_report` is synchronous and takes an already-fetched `CompanyReport`, so (b)'s "nowhere lawful to put the fetch" is correct; `core/cache.py:84-94` is where the per-kind TTL table would go. The `include=[…]`/`SourceRef` mechanism genuinely does not exist in `src/` yet, so the R-5 sequencing is right |

---

### Findings

**1 (blocking — a Swedish personnummer reaches the usage log, and `legal/privacy.md` says it
cannot).** `src/registry_mcp/mcp/connector.py:656-662`. The D-040(b) redaction block sits *after*
`await _identifier_rows(...)` and `await _name_search_rows(...)`. Those helpers catch
`RegistryError` and nothing else, and the country clients wrap only `httpx.TimeoutException`
(`registries/no/client.py:94`, `gb/client.py:250`, `se/client.py:365,457`) — so an ordinary
`httpx.ConnectError` (DNS blip, connection refused, TLS reset) propagates out of `search`,
skipping the redaction, and `_call_context`'s `finally` logs the raw query. Executed with `respx`
raising `ConnectError` at the transport for all three upstream hosts:

```
'orgnr 194009272719'    -> logged query = 'orgnr 194009272719'    ok=True  [ConnectError escaped search()]
'194009272719 AB'       -> logged query = '194009272719 AB'       ok=True  [ConnectError escaped search()]
'Bygg AB, 5560160680'   -> logged query = 'Bygg AB, 5560160680'   ok=True  [ConnectError escaped search()]
```

`legal/privacy.md:15` states: *"For a country where the identifier can be a natural person's
number — today, Sweden — the identifier itself is not written to that log."* That sentence is
false on this path, which makes this a false statement in a published legal document as well as
the exact failure F1 exists to prevent. **Failure scenario:** brreg has a thirty-second network
blip; an agent runs `search("orgnr 194009272719")`; the personnummer lands in `calls.query` on the
production volume, and the privacy policy says it did not. **Change:** the redaction depends on
nothing the awaits produce — `stripped`, `remainder` and `registries` are all known before them.
Move the whole `flagged = [...]` / `if flagged:` block to sit **immediately after**
`outcome.country = derived.country if derived is not None else None` (line 641) and before
`any_validated, ranked = await _identifier_rows(...)`. No logic changes; it simply becomes
unconditional. Add to `tests/test_connector.py`, beside the existing D-040 tests: with the
transport mocked to raise `httpx.ConnectError`, `search("orgnr 194009272719")` still logs
`query=None`. Consider the same audit for `fetch`, whose `outcome.country` is likewise set inside
the block.

**2 (blocking — the deployed service contradicts itself about what it covers).**
`static/well-known/mcp/server-card.json`, the `search` tool entry. `0f952bc` changed
`mcp/connector.py`'s `search` docstring to "(United Kingdom, Norway, Sweden)" but did not
regenerate the card, which still serves "(Norway, United Kingdom)". Executed: I diffed **every**
card tool description against the live `Client(mcp).list_tools()` text — `lookup_company`,
`search_company`, `company_deadlines`, `validate_company_id`, `list_countries` and `fetch` all
**MATCH** exactly; `search` is the **only** drift, and it is exactly the one line `0f952bc`
touched. Confirmed on the wire: live `/.well-known/mcp/server-card.json` serves the two-country
text while live `tools/list` serves the three-country one. **Failure scenario:** a client that
reads the discovery card to decide whether to route a Swedish query here concludes Sweden is not
covered, and never calls the tool that would have answered. **Change:** update that one
`description` in `static/well-known/mcp/server-card.json` to the current docstring text, and — so
this cannot recur, since T17, T26c, T29 and now T26d have each hand-edited that file — extend
`tests/test_mcp.py::test_server_card_lookup_company_output_schema_matches_model` (or add a sibling)
to assert `{t["name"]: t["description"] for t in card["tools"]} == {t.name: t.description for t in
await client.list_tools()}`. That equality holds for six of seven tools today, so the test is one
line of fixture away from green and would have caught this.

**3 (blocking — the two files an LLM caller reads first describe a two-country 0.2.0 service).**
`static/llms.txt` and `static/llms-full.txt`, as deployed. At `28efe77` both contain **zero**
occurrences of "Sweden" or "Bolagsverket", and `llms-full.txt:688` documents the `/health`
response as `{"status": "ok", "version": "0.2.0", "countries": ["GB", "NO"]}` while the live
`/health` returns `{"status":"ok","version":"0.3.0","countries":["GB","NO","SE"]}`. Both are live
on `api.foretak.dev` right now (re-fetched cache-busted). **Failure scenario:** `/llms-full.txt` is
what `_DESCRIPTION` itself calls "the complete reference for an LLM caller"; an agent that reads it
learns the service has two countries and a `/health` shape that is wrong, and never tries `SE`.
**Change:** this is already fixed in the repo — T26h's `6ece116` rewrites both files with Sweden
and corrects the health example to `0.3.0`/`["GB","NO","SE"]` — so the fix is **to redeploy**.
Nothing to write. But it must be deployed before this is closed, and the reason it was missed is
worth recording: `4fd1c92`/`0f952bc` shipped a version bump and a "three countries everywhere"
text pass without either one touching `static/llms*.txt`, and no test relates those files to
`__version__` or to `list_countries()`. A cheap guard: a test asserting `__version__` appears in
`static/llms-full.txt`'s health example and that every country in `list_countries()` is named in
`static/llms.txt`.

**4 (urgent — the hosted manifest advertises package versions that do not exist).**
`server.json:6,24,59`, served live at `https://api.foretak.dev/server.json`. `version` and both
`packages[].version` say `0.3.0`. Executed against both indexes: PyPI `registry-mcp` has
`['0.1.0','0.2.0']`; npm has no `0.3.0` either, because no tag was pushed and `publish-npm.yml`
fires on a tag. **Failure scenario:** a client or a human reads the hosted `server.json` and runs
`uvx --from registry-mcp==0.3.0 registry-mcp` — the exact form
`packages/npm/registry-mcp/bin/registry-mcp.js` builds from `require("../package.json").version` —
and gets a resolution failure. The authoritative MCP-registry entry is still 0.2.0, so no
*published* index is wrong; only the copy this service serves. I did not rate this blocking
because the harm is a failed install rather than a false fact about a company. **Change:** either
push `v0.3.0` (after `uv publish`, in that order — see finding 5) so the manifest becomes true, or
hold `server.json`'s three version fields at `0.2.0` until the release actually happens and bump
them as part of it. Whichever, the go-live checklist should say that `server.json`'s package
versions are a *release* artefact and not part of a hosted-deploy bump.

**5 (non-blocking — a latent release trap, ordering-sensitive).**
`packages/brreg-mcp/pyproject.toml:54` — `dependencies = ["registry-mcp==0.3.0"]`. Verified: not a
broken published package (PyPI's `brreg-mcp` 0.2.0 still declares `registry-mcp==0.2.0`), and not
CI-red (`packages/brreg-mcp` is outside the root workspace — root `pyproject.toml` declares no
`[tool.uv.workspace]` — so nothing resolves it). The trap is ordering: `tasks/T15.md:40` has the
runbook right (`uv publish` first, then `git tag`), but the tag *also* fires `publish-npm.yml`, and
the npm wrapper pins `registry-mcp==<its own version>`. **Failure scenario:** whoever releases
0.3.0 pushes the tag before running `uv publish`; npm serves a 0.3.0 wrapper that cannot resolve
its Python package until PyPI catches up. **Change:** one line in `HUMAN_TODO.md`'s release
section — "PyPI first, npm/tag second; the npm wrapper and `packages/brreg-mcp` both pin the PyPI
version by exact `==`."

**6 (urgent — a `kod` of JSON `null` puts the literal string `"None"` on the wire).**
`src/registry_mcp/registries/se/mapping.py:243` and `:246`. `item.get("kod", "")` returns `None`
when the key is present with a null value (the default only fires on a *missing* key), `str(None)`
is `"None"`, and `"None".strip()` is truthy — so the entry passes the new filter and is emitted as
`IndustryCode(code="None", …)`. Executed:

```
kod=None       -> [('None', 'Something', 1)]
kod missing    -> []
```

The observed live padding uses spaces, so this is not today's data; but it is one serialisation
choice away, the whole point of the commit is "drop entries with no real code", and `"None"` is
the worst possible rendering of an absent one. **Change:** `mapping.py:243`, make the filter
null-safe and reuse the value:

```python
real = [(item, str(item.get("kod") or "").strip()) for item in sni]
return [
    IndustryCode(code=kod, description=(item.get("klartext") or None), scheme="SNI 2007", rank=rank)
    for rank, (item, kod) in enumerate((pair for pair in real if pair[1]), start=1)
]
```

`or ""` handles both the missing key and the null value, and computing the stripped code once
removes the duplicated `str(...).strip()` that let the filter and the emitted value disagree in the
first place. Add a case to test 129: `{"kod": None, "klartext": "x"}` is dropped.

**7 (non-blocking — a call that raised is logged as a success).**
`src/registry_mcp/mcp/server.py:129-147`. `_call_context` sets `outcome.ok = False` only in the
`except RegistryError` branch; any other exception passes through the `finally` with `ok=True` and
`error_code=None`. Shown in the finding-1 transcript above: three `ConnectError`s, all logged
`ok=True`. **Failure scenario:** an upstream outage makes `search` fail for every caller and the
usage dashboard shows a 100% success rate. **Change:** add `except Exception: outcome.ok = False;
outcome.error_code = "internal_error"; raise` before the `finally`, or set `ok=False` in a
`BaseException` handler that re-raises. Pre-existing, not introduced by this range — recorded so it
is not rediscovered.

**8 (non-blocking — D-041 under-counts its own brief and contradicts itself).** `DECISIONS.md:825`
vs `:897` vs `:899`. "seven shipped strings across four files" / "it is six strings" / "(a)'s six
strings". The true figure is **eleven strings across seven files**: the seven D-041 names, plus
`static/llms-full.txt` ×2 (the orchestrator already found these), **`CHANGELOG.md:152`** and
**`content/reddit-sweden-developers-post.md:37`** (neither found before now). Also `SWEDEN_SPEC.md`
has a fourth site — §13's `rules_markdown()` item at line 1704 — beside the three D-041 lists.
**Failure scenario:** the Sonnet who takes Part A works the list in D-041, closes seven sites,
reports done, and the false claim survives in the changelog, in a Reddit post about to be
published under Kim's name, and in the LLM reference. **Change:** amend D-041(a) to say "eleven
shipped strings across seven files" with the full list, make (i) and the Applies-to line agree, and
add §13 line 1704 to the SWEDEN_SPEC list. Note especially that
`content/reddit-sweden-developers-post.md` is **new at `6ece116`** — T26h wrote the false sentence
into fresh content while D-041 was being written, so Part A's list has to be re-derived at the time
it is executed, not copied from D-041.

**9 (urgent — the released 0.3.0 changelog entry contradicts itself).** `CHANGELOG.md:10-198`.
`4fd1c92` inserted `## [0.3.0] — 2026-09-07` at line 12, directly under `## [Unreleased]` and
*above* the entire existing Unreleased body. Consequences, all verified by reading the committed
file: `[Unreleased]` is now an empty heading; the 0.3.0 section contains **seven** `### Added`
blocks, **two** `### Fixed` and **two** `### Changed`; the orphaned preamble "Legibility fixes
(T17): no `core/` change, no response-shape change." now reads as if it describes 0.3.0; and
Sweden and `euid`/`advertising_protected` are each described **twice**. The duplicate Sweden
section is headed "**### Added (third country, Sweden — built, not yet live)**" and says "**It
cannot answer yet**". **Failure scenario:** a reader of the 0.3.0 release notes is told in one
section that Sweden goes live and in another, under the same version heading, that it cannot
answer — and the second one is what a changelog-reading tool would quote. That same duplicate
section is also the `CHANGELOG.md` instance of the D-041 false claim (finding 8). **Change:**
promote the pre-existing body into the 0.3.0 section properly — merge the seven `Added` blocks into
one, delete the "built, not yet live" bullet's contradicted clauses (or rewrite the heading to
"Sweden, in detail"), fold the two `Fixed` blocks together and add the `derive_status` change
noted in D.6, and leave `## [Unreleased]` genuinely empty below a filled 0.3.0.

**10 (non-blocking — the commit message's "three countries everywhere" is not true).** `0f952bc`.
Six shipped descriptions still say two countries at `28efe77`, and `static/index.html` still says
it at `6ece116`: `static/index.html` (zero mentions of Sweden — this is the landing page, with the
meta/JSON-LD keywords T15c added), `server.json:5`, `mcpb/manifest.json` (description,
`long_description`, and the literal phrase "both countries"), `.claude-plugin/marketplace.json`,
`plugins/registry-mcp/.claude-plugin/plugin.json`, and the server card (finding 2). Only
`api/main.py::_DESCRIPTION`, the connector docstring and `README.md` were changed. **Failure
scenario:** the four manifests were bumped to 0.3.0 by `4fd1c92` *and* describe a two-country
service, so whichever directory ingests them next publishes "Norway and the UK" against version
0.3.0. **Change:** finish the pass — those six strings — and say so accurately in the next
PROGRESS entry. `static/index.html` matters most: it is the page a human lands on.

**11 (non-blocking — the connector `search` docstring now over-claims Sweden).**
`src/registry_mcp/mcp/connector.py:620`. The new text says it "Finds companies in this server's
national business registers (United Kingdom, Norway, Sweden) from one free-text query — a name, a
national identifier, or a name plus a country". For Sweden only the identifier half is true;
`search_company`'s own description gets this right ("**Sweden cannot be searched by name.**"), and
so does `_DESCRIPTION`. **Failure scenario:** a ChatGPT connector session sends `search("Ericsson")`
expecting the Swedish parent, gets the British and Norwegian Ericsson entities, and reports the
Swedish register as broken. **Change:** append one clause — "…and a name plus a country (Sweden by
identifier only: Bolagsverket publishes no name index)". Fix it in the same edit as finding 2 so
the card and the docstring are regenerated together.

**12 (non-blocking — the "fast" half of GB test 105 is now asserted nowhere).**
`tests/test_client_gb.py:483`. Demonstrated by mutation M3 above: a bucket sleeping a full second
per `acquire()` but staying concurrent passes the new test (wall clock 1.05 s), and the old
`elapsed2 < 1.0` would have failed it. There is no direct unit test of GB's `_TokenBucket` — SE has
one (`tests/test_client_se.py:970`), GB has none. **Failure scenario:** someone changes
`_BUCKET_REFILL_PER_SECOND` or adds a sleep to `acquire()` and every GB call silently gains a
second; the suite stays green. **Change:** do not restore a wall-clock bound — it was flaky for a
real reason. Add a deterministic unit test instead, mirroring SE's: assert that
`_TokenBucket(600.0, 2.0).acquire()` returns without yielding to a timer while tokens remain (e.g.
that 600 sequential `acquire()` calls complete inside one event-loop pass), and that the 601st
raises `rate_limited` after `_BUCKET_MAX_WAIT_SECONDS`. That tests the arithmetic, which is what
"fast" actually means here.

**13 (non-blocking — `SWEDEN_SPEC.md` §14's numbered contract has drifted from the suite).**
`SWEDEN_SPEC.md:1934-1941`. The list jumps 125 → 129: tests **126, 127 and 128** exist in
`tests/test_client_se.py:404,597,614` (added by `97ff85b`) and were never written into the spec, so
`fbd4792` numbered its new tests 129/130 over a gap. The new entries were also inserted *above* the
stray item 98, which was already out of order. **Failure scenario:** the numbered list is the
spec's contract with the suite; a reader who checks "is 126 implemented?" finds nothing.
**Change:** add 126/127/128 under a dated "*Added 2026-09-06 with T30's review fixes*" heading, and
move item 98 back into numeric order while you are there.

**14 (non-blocking — the README's Swedish example lacks the abridged marker its GB sibling has).**
`README.md`, the `$ curl https://api.foretak.dev/v1/SE/company/5560160680` block added by
`0f952bc`. The GB block above it is followed by "Abridged — the full `CompanyReport` also
carries…"; the SE block shows ~20 of 50 keys with no such sentence, and reformats several onto
shared lines. Every value in it is real (verified against the live service), which is the important
part. **Change:** one sentence after the block, matching the GB one. *(`README.md` is open in
T26h's editor; this is for whoever closes that file.)*

### Praise, where it teaches something

**`api/errors.py`'s fallback is the part most people would get wrong.** The obvious
implementation of "log the route template" is `request.scope["route"].path`, and the obvious
failure handling is `or request.url.path`. `97ff85b` instead does
`isinstance(route, StarletteRoute)` and, when it is not, **logs the method alone** — with a comment
saying why: a raw ASGI failure or middleware raising before routing means there is no template, and
substituting the concrete path there would reintroduce exactly the leak the fix exists to close.
That is the case where the fix would have quietly failed open, and it was the case that was
handled.

**`derive_status`'s new UNKNOWN branch carries `notes` through.** The two-line version of review
fix 2 returns a bare `UNKNOWN`. This one passes `notes=notes`, so the FUOT "acquiring party in a
merger" sentence survives into a result whose status is `unknown` — verified. §8's "the lower rungs
still fill their own fields and notes" is a rule about rung 2; applying it to rung 0 as well is the
non-obvious reading, and it is the one that keeps the report explaining itself when the status
becomes least informative.

**`056bd6c` is a rare case of a test that got stronger by dropping an assertion.** The wall-clock
bound looked like it tested two things and actually tested neither reliably; the overlap counter
tests one thing deterministically, and I could not construct a serialising bucket that survives it.
The lesson worth keeping is the mechanism: because `asyncio.gather` has both tasks queued before
the first one yields, the overlap is a *scheduling* fact rather than a *timing* fact, and no runner
load can change it. That is the shape to reach for whenever a concurrency test is tempted to look
at a clock.

**And the orchestrator's own second finding on D-041 is the best catch in the range.** D-041 was
written by an Opus, reviewed by nobody, and the orchestrator still went and checked its incidental
claim about `SWEDEN_SPEC` line 993 against the code — and found that a *previous review* had
asserted the rung-1 hook was implemented when `deadlines_for` does not so much as name
`published_deadlines`. I confirmed it independently: zero occurrences in `registries/se/rules.py`,
and the two helpers do not take `report` at all. Checking a decision's throwaway sentence against
the source is what nobody does, and it is what found this.

**Verdict: CHANGES REQUIRED.** The two orchestrator-authored commits are both defensible — the
`sni` filter is correct on the data it was written for, its tests assert the right things, and the
GB test rewrite is a genuine improvement I could not break. The standing rule was worth breaking
for the second one and arguably for the first; the cost of breaking it shows up not in the code but
in the bookkeeping around it (findings 10, 13) and in the one edge the author of a one-line filter
does not stop to probe (finding 6). What must land before this range is called done: **finding 1**
(a personnummer reaches the usage log on an ordinary upstream connect error, and `legal/privacy.md`
states in print that it cannot — the same class of defect as the last review's fix 1, one layer
further out); **finding 2** (the live server card and the live tool list disagree about which
countries this service covers); and **finding 3** (the two files this service itself calls "the
complete reference for an LLM caller" describe a two-country 0.2.0 build — already fixed in
`6ece116`, so this one is a redeploy, not an edit). Findings 4, 6 and 9 should follow the same day:
a manifest naming package versions that exist nowhere, a null `kod` that would ship the string
`"None"` as an industry code, and a release note that announces Sweden live and not-yet-live under
one heading. The rest can follow at leisure — but **finding 8 should be applied to D-041 before
Part A is dispatched**, or its Sonnet will close seven sites and leave four.

---

## S-series — 2026-09-08 — CHANGES REQUIRED (two blocking, two urgent; the machinery itself is sound)

Reviewer: Opus reviewer. Scope: everything committed today, `cf5f13f..48cb6ab` (`git log --oneline
v0.3.0..HEAD`), plus the `D-042` compliance check the brief asked for.

**Working-tree caveat, stated up front.** Three implementers are mid-flight in this tree. Everything
below was executed against a pristine export of committed `HEAD`
(`git archive HEAD | tar -x -C <scratch>`), never the working tree. On that export:

* `pytest -m "not live"` → **726 passed, 13 deselected** — exactly the count `10f46f2` and `48cb6ab`
  claim. `mypy .` → clean, 65 files. `ruff check .` → clean. **CI is green at HEAD.**
* The working tree gives **724 passed, 2 failed** (`test_mcp.py::test_server_card_lookup_company_
  output_schema_matches_model`, `::test_server_card_tools_and_prompts_match_the_live_server`). That is
  **fully explained by uncommitted work**: `git diff HEAD -- src/registry_mcp/mcp/server.py` shows the
  wiring agent has added the `include` parameter and the charges paragraph to `lookup_company`'s
  docstring, and `static/well-known/mcp/server-card.json` has not been updated to match. **Not a
  regression.** It is, incidentally, the card-drift test from `cf5f13f` doing its job on its first
  real drift, which is a good sign for that test.
* Everything committed today is **already live on `api.foretak.dev`** — verified: the served
  `/.well-known/mcp/server-card.json` is byte-identical to `HEAD`'s, and `/v1/countries` already
  returns `supported_includes: []` on all three countries. Finding 1 is therefore live in production
  now, not pending a deploy.

### Checklist

| # | Claim under test | Method | Result |
|---|---|---|---|
| 1 | 726 tests pass at committed HEAD | pristine `git archive` export + venv | **PASS** |
| 2 | `mypy .` clean, `ruff check .` clean at HEAD | executed on the export | **PASS** |
| 3 | Working-tree failures are uncommitted work, not a regression | `git diff HEAD -- mcp/server.py` | **PASS** (explained) |
| 4 | `counterparty_check` always renders the payment-fraud caveat | mutated the sentence to its opposite | **PASS** — `test_counterparty_check_prompt_states_what_it_does_not_establish` goes red |
| 5 | The caveat is *structurally* guaranteed, not just test-pinned | read the prompt builder | **PARTIAL** — see finding 5 |
| 6 | New instructions/card: Companies House VAT claim | grep + live `GET /v1/GB/company/00445790` (`vat_registered: null`) | **PASS** — VAT is claimed for NO only |
| 7 | New instructions: "no key" honesty | read `instructions`; card `authentication` | **PASS** — names `COMPANIES_HOUSE_API_KEY`/`BOLAGSVERKET_*` and "will answer for Norway only" |
| 8 | New instructions: Sweden has no name search | called `search_company(country="SE")` | **PASS** — raises `not_implemented` with a hint naming `lookup_company` |
| 9 | Both prompts work end to end | rendered both via `fastmcp.Client`; checked every tool name, argument and model field they cite | **PASS** — all exist (`validate_company_id`/`lookup_company`/`company_deadlines` take `id`,`country`; `days_until`, `status_detail`, `notes`, `source_url`, `employees_reported` all real) |
| 10 | `register_coverage`'s null taxonomy is true per country | traced `employees_reported` per country module | **FAIL** — finding 2 |
| 11 | `registry://rules/{country}` resolves for the prompt's interpolation | read all three, incl. lowercase `gb` | **PASS** |
| 12 | A failing attachment leaves the lookup intact | ran `test_one_failing_attachment_does_not_affect_a_succeeding_one` + read `lookup_with` | **PASS** |
| 13 | `include` validation happens *before* the upstream call | mutated: moved the check after `await self.lookup(id)` | **PASS** — 2 tests go red |
| 14 | Concurrency is bounded as claimed | mutated: removed the semaphore | **PASS** — `test_max_concurrency_bounds_in_flight_attachment_fetches` goes red |
| 15 | Duplicate `include` values cost one fetch | mutated: `dict.fromkeys` → `list` | **PASS** — test goes red |
| 16 | The `RuntimeError` guard fires on a declared include with no matching **field** | mutated: deleted the guard | **PASS** — test goes red |
| 17 | …and on a declared include with no matching **method** | constructed one and ran it | **FAIL** — bare `AttributeError`, finding 6 |
| 18 | `include=[]` is genuinely free | read `lookup_with` (no semaphore, no `gather`, early return) + `test_lookup_with_default_include_costs_exactly_one_lookup_call` | **PASS** |
| 19 | The rewritten concurrency test proves overlap | mutated: `asyncio.gather` → sequential comprehension | **PASS** — `TimeoutError`, test goes red; sequential execution cannot pass it |
| 20 | No `persons_entitled` value in any committed fixture is a natural person | extracted all 110 values / 68 distinct from the four fixtures and read every one | **PASS** — all institutions (`Kfw`, `Natixis`, `J. Aron & Company`, `Nevis Derivatives No 3 LLP` checked individually) |
| 21 | Nothing reads Companies House's `has_charges` | `grep -rn has_charges src/` | **FAIL** — `gb/mapping.py:132` does, finding 1 |
| 22 | Tesco's `has_charges` really is wrong | `ch_00445790.json` `has_charges: false`; `ch_00445790_charges.json` → 9 items, `total_count 9`, `satisfied_count 7`, 2 `"outstanding"` | **PASS** — the finding is real |
| 23 | Status table matches the wire | all 110 fixture items: only `outstanding` (80) and `fully-satisfied` (30) | **PASS** — no `part-satisfied`, table is honest |
| 24 | D-042(c) — no new tools | live card + `tools/list`: 7 (5 registry + 2 aliases); no new REST route | **PASS** |
| 25 | D-042(d) — discoverability | `CountryInfo.supported_includes` on the wire, sorted; block names in tool description text | **PARTIAL** — (d)(1) done; (d)(2) is in the uncommitted wiring, correct since no block ships at HEAD |
| 26 | D-042(e)(1) — `description_values` allow-list | `grep -rn description_values src/` | **PASS** — zero (no filing history shipped) |
| 27 | D-042(f) — officers and PSC barred | grep for `/officers`, `persons-with-significant`, `officer_name`, `psc` | **PASS** — prose references only |
| 28 | D-042(j) — truncation disclosed, register's max page, derived flag by table | read `map_charges`; NatWest fixture (137 total, 100 returned) produces the note with the register's URL | **PASS** |
| 29 | D-042 exists in committed history | `git log -S"### D-042" --all` | **FAIL** — finding 3 |
| 30 | The charges model shape is the one D-042 ruled | counted every field name in D-042 | **FAIL** — finding 4 |
| 31 | Dashboard chart is responsive and all 30 bars are reachable | read the renderer; `viewBox` + `width:100%`, `max_count = max(counts) or 1` | **PASS** (untested — finding 9) |

### Findings

**1. `registers["charges"]` is a false "no" on the wire, live, for exactly the company today's
commit proved it wrong on. — BLOCKING.**
`src/registry_mcp/registries/gb/mapping.py:132` — `"charges": bool(data.get("has_charges"))`.
Executed against production: `curl https://api.foretak.dev/v1/GB/company/00445790` returns
`"registers": {"charges": false, "insolvency": false}` for **TESCO PLC**. `48cb6ab` committed
`tests/fixtures/ch_00445790_charges.json`, recorded live today: **nine charges, two outstanding**.
`core/models.py:709` documents `registers` as "Other national sub-registers this entity **is or is
not in**" — a `false` there is an assertion, not an absence.
The commit message says "Nothing in this code reads it". That is true of `charges.py` and false of
the product. Worse, the wrong value is *defended* in three places: `tests/test_client_gb.py:145`
(`test_78_registers_charges_is_false_despite_links`, whose own docstring calls it "the single most
important mapping test in the file") pins it; `UK_SPEC.md:158-166` §1.6 №1 states the now-falsified
premise — "`links.charges` is present even when there are no charges … Read the deprecated boolean"
— when in fact `links.charges` was right and the boolean was wrong; and `static/llms-full.txt:357`
documents the derivation to callers.
*Failure scenario:* an agent runs `counterparty_check` on a GB supplier, reads `registers.charges:
false`, and reports "no registered charges" for a company carrying two outstanding charges. D-042's
own words: "a charge is a credit decision."
*Exact change:* delete the `"charges"` key from `map_registers` (`gb/mapping.py:127-134`) — a
`dict[str, bool]` cannot say *unknown*, and D-011's rule forbids collapsing "not in the register"
and "the register's own flag is unreliable" into one `false`. Let `include=["charges"]` be the only
thing that answers the question. Then repoint `test_78` at the new behaviour, rewrite `UK_SPEC.md`
§1.6 №1 to record the reversal (the boolean is wrong, not merely deprecated), and fix
`static/llms-full.txt:356-357` and its example at `:306`. Re-test `has_insolvency_history` before
continuing to trust it — the same evidence base has not been re-checked for it.

**2. `register_coverage` teaches the agent the wrong half of its own taxonomy, for two of three
countries. — BLOCKING (false statement in user-facing text).**
`src/registry_mcp/mcp/server.py:721-723`. The prompt's only worked example says: *"(b) An
entity-level gap: the register could hold a value here but has none for this particular company —
`employees` null alongside `employees_reported: false` is exactly this."*
That is true for Norway (`registries/no/mapping.py:247` derives the flag from the payload) and false
for the United Kingdom and Sweden, where `registries/gb/mapping.py:346` and
`registries/se/mapping.py:785` hard-code `employees_reported=False` because **neither register
publishes an employee figure for any company**. Verified live: `/v1/GB/company/00445790` and
`/v1/SE/company/5560160680` both return `employees: null, employees_reported: false`. That is case
**(a)**, a structural silence, which the prompt names as case (b).
The prompt does not branch on `country`, so `register_coverage(id, country="GB")` — the exact call
`tests/test_mcp.py::test_register_coverage_prompt_renders_and_reads_the_rules_resource` makes —
instructs the agent to tell a reader that Companies House holds no employee figure *for this
company*, implying it might for another. This is the two-states-into-one collapse the prompt exists
to prevent, in the prompt's single illustration of how to avoid it, and
`test_register_coverage_prompt_distinguishes_structural_from_entity_nulls` pins the sentence so it
will survive edits.
*Exact change:* make the example country-true. Either drop the worked example and keep the rule, or
say: "in Norway, `employees: null` with `employees_reported: false` is an entity-level gap; in the
United Kingdom and Sweden the same pair is structural, because neither register publishes an
employee figure for any company." Update the pinning test's assertion to the new wording.

**3. D-042 has never been committed. — URGENT; must land before 17:00.**
`git show HEAD:DECISIONS.md | grep -c D-042` → **0**. `git log --oneline -S"### D-042" --all` →
**empty**. The last committed entry in `DECISIONS.md` is D-041 (`28efe77`). D-042 exists only as a
96-line uncommitted addition in the working tree, and `tasks/T37.md` is untracked.
Three commits today take D-042 as their governing authority and cite it by part — roughly thirty
times across shipped docstrings in `core/registry.py`, `core/models.py`, `registries/gb/charges.py`
and `registries/gb/client.py`. Anyone reading committed history (the human at 17:00 included) is
sent to a decision that does not exist in the repository; `DECISIONS.md`'s own header calls itself
append-only and the file every implementer reads before starting.
*Exact change:* commit `DECISIONS.md` and `tasks/T37.md` before the review. This is the cheapest
item on the list and the one with the worst failure mode — a lost working tree loses the reasoning
behind the entire depth track.

**4. `charges.py` attributes an unruled model to the architect, and tells the next agent it is a
rename. — URGENT; must land before the wiring commit, which is in flight now.**
`src/registry_mcp/registries/gb/charges.py:20-22` — *"The model shapes below are copied
field-for-field from `DECISIONS.md` D-042 part (h) — the ruled shape of the future
`core.models.Charge` / `core.models.ChargeBlock` — precisely so that wiring this up once R-5 lands
is a rename, not a redesign"* — repeated at `:180` and `:246`.
D-042(h) is titled *"`FiledDocument` is widened by three fields"* and its entire content is
`category` / `type_code` / `description_code` for **filing history**. It rules no charge shape at
all. Counting every field name of the two local models against the whole 27,000-character entry:
`outstanding_count` 0 hits, `satisfied_count` 0, `charge_id` 0, `charge_number` 0, `assets_charged`
0, `obligations_secured` 0, `contains_floating_charge` 0, `classification` 0, `created_on` 0,
`delivered_on` 0, `satisfied_on` 0. Only three names are actually ruled anywhere in D-042:
`parties_entitled` (the rename, (e)(3)), `Charge.is_outstanding` (as the derived-flag example, (j))
and `total_count` (the truncation rule, (j)).
So thirteen of sixteen field names are this implementer's own design, presented as the architect's.
*Failure scenario:* the wiring agent reads "a rename, not a redesign" and lifts these names straight
into `core/models.py` as the **shared, country-neutral** `ChargeBlock` that D-042(g) reserves for
Norway's Løsøreregisteret and Sweden's företagsinteckningar as future fillers — the payload-shaped
bend D-042(g) and (i) exist to prevent, arriving through a citation nobody checked. The same module
is scrupulous elsewhere (it declines to add `contains_fixed_charge` and `part_satisfied_count`
precisely *because* D-042(g) reserves that to the architect), which makes the mis-citation more
likely to be believed, not less.
*Exact change:* replace the three "D-042(h)" citations with an honest one — "shaped by D-042(g)'s
anti-bend rule and (j)'s truncation and derived-flag rules; **the field list itself is this module's
proposal and is not yet ruled**" — and get a ruling (a D-042 amendment or D-043) on
`Charge`/`ChargeBlock` before those names enter `core/models.py`. Note for that ruling: the module
already flags two open questions honestly at `:115-127` (`outstanding_count` as `total_count −
satisfied_count`, and the missing `part_satisfied_count`), and both need answering, because
`part_satisfied_count` was 0 in every payload observed so the arithmetic is untested in practice.

**5. The payment-fraud caveat is CI-guaranteed inside the prompt, and absent from the surface every
client actually reads. — NON-BLOCKING.**
Answering the brief's question directly: **inside `counterparty_check` the caveat cannot silently
vanish.** I mutated `mcp/server.py:694` from *"it is not a defence against payment fraud"* to *"it
is a strong signal the payment is safe"*; `test_counterparty_check_prompt_states_what_it_does_not_
establish` went red on four of its five pinned substrings. That test is a genuine guard and the best
thing in `cf5f13f`.
Two gaps remain. (a) The server `instructions` (`mcp/server.py:169-178`) now carry the same pitch —
"Check whether a company you're about to deal with — a new supplier, a counterparty … is real,
active and keeping up with its statutory filings" — with **no caveat at all**. The caveat reached
the card's `description` and the prompt; `instructions` is the string every MCP client puts in front
of the model, and the card is a static file most clients never fetch. A caller who uses
`lookup_company` directly gets the pitch and not the limit. One sentence fixes it, and it belongs in
the same clause as the pitch. (b) "It then **forces** a section titled…" (commit message) overstates
what an instruction inside a prompt can do — nothing checks the *model's* output. Worth hoisting the
caveat to a module constant so a third prompt reuses it rather than paraphrasing it, and worth one
eval case in `evals/cases.json`, where neither new prompt appears today.

**6. Two of `lookup_with`'s three misconfiguration paths are not what the docstring promises, and
the surface logs the crash as a success. — NON-BLOCKING (unreachable at HEAD; reachable the moment
the include is wired).**
`src/registry_mcp/core/registry.py:342` promises that a country "whose `supported_includes` names a
method it does not define, **or** whose result does not match a field on the report … fails loudly
here (see the `RuntimeError` below)". Executed: only the second case does. A declared include with
no matching method raises `AttributeError: 'Missing' object has no attribute 'nomethod'` at
`:371` — no mention of `supported_includes`, and no test covers it. A third case is silent: the
`RuntimeError` guard at `:389-395` only inspects **successful** attachments, so a misconfigured
include whose method raises `RegistryError` produces a plausible `notes` sentence and no error at
all.
Compounding it: `mcp/server.py:93` defaults `_CallOutcome.ok = True` and only the
`except RegistryError` branch sets it False, so any of these exceptions escaping a tool body is
**recorded in the usage log as a successful call** and reaches the client as a bare FastMCP
`ToolError` rather than a D-007 `{"error": {code, message, hint}}` envelope. R-5 is the first code
that raises non-`RegistryError` exceptions *by design*, which is what makes this worth fixing now.
*Exact change:* validate the whole `supported_includes ↔ method ↔ field` triple in one place before
`lookup` is called (or at class definition, in `__init_subclass__`), raising the same `RuntimeError`
for all three cases; add a test for the missing-method case; and add `except Exception: outcome.ok =
False; raise` to `_call_context` so an internal bug is not counted as a success.

**7. Charge free text is relayed unbounded, and D-042(e)'s person-bearing test never looked at it. —
NON-BLOCKING.**
`registries/gb/charges.py:325-326` maps `particulars.description` → `assets_charged` and
`secured_details.description` → `obligations_secured`, verbatim. D-042(e)'s field-level test for GB
charges names only `persons_entitled`. Free-text particulars can name a natural person (a charged
property, a guarantor). I scanned all 110 committed fixture items for personal titles — clean; 47
carry a `particulars.description`, longest 260 characters, all institutional boilerplate ending "see
image for full details". But nothing constrains what a future payload contains, and this is the same
class of surprise D-042(e) records for filing history's `description_values`. Worth one sentence in
the decision either way — this is a question for the architect, not a defect in the module.

**8. Two provenance shapes now exist in one tree. — NON-BLOCKING, but it must not survive the wiring
commit.**
`core.models.SourceRef` (`10f46f2`) and `registries/gb/charges.py::ChargeProvenance` (`48cb6ab`) are
the same five fields twice — the "hand-rolled per-block provenance in a country module" that
D-042(b) declined by name as "the single thing R-5 exists to prevent". Both commits document it as a
deliberate parallel-work seam with a named removal plan, which is the right call for a
same-morning split. Flagging it only so the wiring commit is checked for its removal rather than its
re-export.

**9. The chart fix has no test, and the bug it fixes is exactly the kind that returns. —
NON-BLOCKING.**
`tests/test_dashboard.py` has 12 tests and not one mentions the chart, the svg, or a width. The
regression that shipped — a fixed `width='{n * 22 + 4}'` inside `overflow-x: auto` — would ship again
unnoticed. One assertion (`"viewBox=" in html and "width='100%'" in html`) closes it. Separately,
`height='auto'` at `api/dashboard.py:474` is not a valid SVG 1.1 length; it is harmless only because
the new CSS rule at `:330` overrides the presentation attribute. Drop the attribute and let the CSS
own it. The diagnosis and the `max_count = max(counts) or 1` dead-branch removal are both correct.

**10. The recon numbers in `charges.py`'s docstring understate the recon, and cite a fixture that is
not committed. — NON-BLOCKING (accuracy).**
`registries/gb/charges.py:87` and `:284` say "39 `persons_entitled[].name` values" / "39 charges on
4 companies". The four committed charge fixtures hold **110** items and **110** `persons_entitled`
values, 68 distinct — which is what the commit message says, correctly. The docstring number looks
like a stale count from an earlier pass at `items_per_page=25`. The same lines cite Monzo
(`09446231`) as one of the four companies, but no `ch_09446231_charges.json` exists, so that quarter
of the evidence cannot be re-checked from the repository. Fix the count to 110/68 and either commit
the Monzo charges fixture or drop it from the list — the evidence is stronger than the docstring
claims, which is a strange way to lose an argument.

### What is factually untrue in what was committed today

1. `48cb6ab`'s message: **"Nothing in this code reads it [`has_charges`]."** `gb/mapping.py:132`
   reads it and ships the result on every GB lookup. (Finding 1.)
2. `charges.py:20-22`, `:180`, `:246`: **"copied field-for-field from D-042 part (h) — the ruled
   shape of the future `core.models.Charge` / `core.models.ChargeBlock`."** D-042(h) rules
   `FiledDocument`; no charge model is ruled anywhere in D-042. (Finding 4.)
3. `mcp/server.py:721-723`: **"`employees` null alongside `employees_reported: false` is exactly
   this [an entity-level gap]."** Structural, not entity-level, for GB and SE. (Finding 2.)
4. `charges.py:87`, `:284`: **"39 `persons_entitled[].name` values" / "39 charges on 4 companies."**
   110 and 110 in the committed fixtures. (Finding 10.)
5. `core/registry.py:342`: **a declared include with no matching method "fails loudly here (see the
   `RuntimeError` below)."** It raises `AttributeError`. (Finding 6.)
6. Carried forward and now falsified by today's own evidence, though not written today:
   `UK_SPEC.md:158` §1.6 №1, **"`links.charges` is present even when there are no charges"** —
   `00445790` has nine. Its prescription, "Read the deprecated boolean", is backwards. (Finding 1.)

### Must land before 17:00

* **Finding 3** — commit `DECISIONS.md` and `tasks/T37.md`. Minutes of work; without it the review
  is a discussion of commits that cite an authority nobody can open.
* **Finding 4** — correct the three citations *before* the wiring commit lands, and decide whether
  `Charge`/`ChargeBlock` enters `core/models.py` under an architect's ruling or under an
  implementer's proposal. The wiring is in the tree right now.
* **Finding 2** — a two-line edit to a prompt string plus its pinning assertion.
* **Finding 1** — the decision, at least, should be taken at 17:00 with the human: the fix is small
  (delete one dict key, repoint one test) but it changes a documented field on a live wire and
  contradicts a spec paragraph, so it wants a person's assent rather than an agent's.

### What is worth keeping

The mutation results are the argument, so they are worth reading as praise: **five** of `lookup_with`'s
claims are load-bearing under mutation, not decorative. Removing the semaphore, removing the guard,
moving the validation after the upstream call, removing the de-duplication and making the fetch
sequential each turn a specific test red, and each of those tests names the decision it enforces.
That is a rate I do not usually see.

`5bf0134` in particular deserves its commit message. The rendezvous rewrite is not merely less
flaky — it is *stronger* than what it replaced: under a sequential mutation the old test would have
passed on a fast machine, and the new one cannot, because the asserted order is unreachable without
overlap. Replacing a timing assertion with a causal one is the correct fix for a flake, and it was
done within an hour of the flake, by the agent that noticed it rather than by CI.

And `test_charges_no_natural_person_among_recorded_parties_entitled` (`test_client_gb.py`) is worth
copying elsewhere: it documents, in the test, why the obvious broad heuristic was rejected (a
keyword classifier produced twelve false positives on real banks in one fixture; a digit check
misfires on `Nevis Derivatives No 3 LLP`), then does two narrow things it can actually guarantee and
says plainly which part of the claim was verified by hand instead. A test that reports the limits of
its own evidence is rarer and more useful than one that overclaims — and its hand-verified part
holds: I re-derived all 68 distinct names independently and every one is an institution.

---

## D-044 wiring (`e03a518`) — 2026-09-08 — APPROVED WITH FIXES (one blocking, two urgent; the wiring itself is correct)

Reviewer: orchestrator (Fable 5.1), reviewing the session Opus ran as orchestrator. Scope: `e03a518`
("Wire the three attachments"), read against D-041, D-042, D-043, D-044, `tasks/T31.md` Part B and
`tasks/T37.md`; plus which of the S-series findings above the later commits closed. Executed on the
working tree at `e03a518` (`main` = `origin/main`, nothing ahead; the two uncommitted files are this
`REVIEW.md` and a one-word `devto.md` edit, neither touching `src/`).

* `uv run pytest -m "not live"` → **834 passed, 22 deselected**, the count the commit claims.
  `uv run mypy .` → clean, 69 files. `uv run ruff check .` → clean.
* **Production has not picked up `e03a518`** (19:35Z): the served `/.well-known/mcp/server-card.json`
  has no `filings` anywhere, HEAD's has; `/health` says 0.3.0 for both. Deploy is manual. Nothing
  below is live yet, including the defect in finding 1.

### Checklist

| # | Claim under test | Method | Result |
|---|---|---|---|
| 1 | D-044(a): the three module `FiledDocument`s are field-for-field identical and `FilingProvenance` ≡ `SourceRef` | listed every field of all four `FiledDocument`s and all provenance classes | **PASS** — ten names, same order, in `gb/filing_history.py`, `se/filings.py`, `no/accounts.py` and `core/models.py`; five names in every provenance class |
| 2 | Each country's `filings` and GB `insolvency` land on the field of the same name | `test_lookup_with_routes_each_block_to_the_field_of_the_same_name` ×4, and read `lookup_with` | **PASS** |
| 3 | Conversion at the seam preserves every field of a real payload | the three conversion tests + insolvency, against recorded fixtures | **PASS** |
| 4 | The practitioner bar holds on the core side | `test_no_practitioner_field_survives_the_conversion_to_core_models` | **PASS** — `extra="forbid"` raises on `practitioners` |
| 5 | Every declared include has a method and a report field, in every country | `test_every_declared_include_is_reachable_in_every_country` | **PASS** |
| 6 | D-044(b): *"the scope difference is disclosed in the block's own `notes`, on every call"* | ran all three mappers on their fixtures and printed `notes` | **FAIL** — finding 1 |
| 7 | D-041(b) / T31 Part B / T37 done-check: `company_deadlines` accepts `include=["filings"]` | read both surfaces' signatures; `grep financial_year_end` over `rules.py` ×3, `core/registry.py`, both surfaces | **FAIL** — finding 2 |
| 8 | `PROGRESS.md` reflects the day | read the board | **FAIL** — finding 3 |
| 9 | S-series finding 8: the second provenance shape did not survive the wiring | `grep -rn "^class .*Provenance" src/` | **FAIL** — six shapes now; finding 4 |
| 10 | "server-card.json regenerated" | diffed the card's `lookup_company.inputSchema.properties.include` against `_INCLUDE_DESCRIPTION`/`_INCLUDE_EXAMPLES` | **PARTIAL** — finding 5 |
| 11 | Insolvency: the two empty states are told apart, practitioners note fires | read `map_insolvency`; fixture run | **PASS** — `_NO_RESOURCE_NOTE` vs `_EMPTY_RESOURCE_NOTE`; practitioners note on every block with cases |
| 12 | D-043(h) rule 1 is already satisfied for T38 | `no/client.py::fetch_accounts` keys on `_accounts_cache_key(orgnr)`, one key per call | **PASS** — and rule 3's race is real: no lock or in-flight map exists in `no/client.py`, so T38 must add one |
| 13 | S-series 1, 2, 3 closed | `beb287f`, `770c53c` | **PASS** |
| 14 | S-series 4–10 closed | see finding 8 | **FAIL** — none of the seven |

### Findings

**1. D-044's central promise is not in the Swedish block, and three published strings say it is. —
BLOCKING (false statement in agent-facing text, on the wire once deployed).**
D-044(b) rules one include name for three scopes *because* "the scope difference is disclosed in the
block's own `notes`, on every call". `mcp/server.py:342` (and the card's `lookup_company`
description) tells the agent "*the block's own `notes` says which*"; `core/models.py:857` — published
in the card's `outputSchema` — says "*`notes` says which, in words, on every block*".
Measured on the fixtures: **SE → 3 documents, `notes: []`.** GB → three notes (truncation, fee
point, minimisation), none naming the scope. NO → `_ONE_PERIOD_NOTE` on every non-empty call, which
does exactly what D-044(b) describes — so the pattern exists and was not copied.
`se/filings.py` has two note constants and both are conditional: `_EMPTY_NOTE` (`:474`, empty list
only) and `_BROKEN_YEAR_NOTE` (`:479`, non-December year end only). A calendar-year Swedish company
with filed reports gets no note at all.
*Failure scenario:* an agent asked "is this Swedish supplier filing on time" receives three annual
reports and an empty `notes`, has been told notes will say which subset this is, and concludes it is
looking at the whole history — the inference D-044(b) exists to prevent, in the country whose scope
is narrowest.
*Exact change:* one unconditional constant in `se/filings.py` ("Bolagsverket's document list
publishes filed annual reports only, not a general filing history; other filings are not listed
here"), appended in `map_dokumentlista` on every call, and the same for GB ("the whole filing history,
every filing kind, not only accounts") in `map_filing_history`. One assertion each. No test pins
`notes == []` for either block, so it is additive; country modules only, `core/` untouched.

**2. The deadline rung D-041 was written for is unwired and untracked. — URGENT (a wrong date D-041
ruled on is still shipping, and the remaining work has no row anywhere).**
D-041(b): the argument "goes on **`company_deadlines` as well as `lookup_company`**, because … this
attachment *changes the answer of another operation*". `tasks/T31.md` Part B is "`include=["filings"]`,
the block, **the second deadline rung**" (line 15), and line 128 makes extending `include` to
`company_deadlines` part of the task; `tasks/T37.md:280` requires `company_deadlines` to accept
`include=["filings"]` for GB as a no-op. Executed: MCP `company_deadlines(id, country, today)` has no
`include`; REST `get_deadlines` takes `today` only; `financial_year_end` is consumed by **nothing** —
zero hits in any `rules.py`, `core/registry.py` or either surface. So a Swedish company with an April
year end is still told 30 June and 31 July, D-041(a)'s own example, with the corrected date now
sitting unread in a block the same server returns.
`e03a518` is honest that it changes no upstream behaviour, and its "Applies to" line says only that
Sweden's `filings` is *wired*. The problem is that the half of T31 Part B and the T37 line it did not
do are recorded nowhere: `PROGRESS.md` T31b still reads "todo — Blocked on R-5".
*Exact change:* no code in this review. Give the rung a home: T31b's row becomes "block wired
(`e03a518`, D-044); **open**: `include` on `company_deadlines` both surfaces, rung 2 in
`se/rules.py` per T31 §4, GB no-op per T37" — then it is one Sonnet task against a brief that
already exists.

**3. The board was not kept. — URGENT (the orchestrator's own rule, and Kim's "resume from repo files
alone").**
`PROGRESS.md` has no row for R-5 (`10f46f2`, `5bf0134`), T37/R-5c (`48cb6ab`, `3ecc369`, `beb287f`),
R-5d, R-5e, the wiring (`e03a518`), D-043/T38 (`fc4bb13`), the two prompts (`cf5f13f`), the S-series
review, or the D-042/D-043/D-044 rulings; T31b says blocked on a mechanism that landed at 10:00;
D1–D2, T32 and T26h still say `doing`. The whole day exists only as a chat handoff. Rows to add:
R-5 done (machinery, `10f46f2`); T37 Part A done, Part B **review** (findings 1, 2, 5 here);
R-5d/R-5e **review**; T31b open per finding 2; T38 todo (owner Sonnet, brief ready); S-series
review received, 1–3 applied, 4–10 open; D1–D2 done (D-042); T32 and T26h resolved or closed.

**4. Six provenance shapes and four `FiledDocument`s in one tree; the S-series said two must not
survive the wiring, and instead they multiplied. — NON-BLOCKING, and it is the next task, not a
someday.**
`grep -rn "^class .*Provenance" src/`: `SourceRef` plus `ChargeProvenance`, `InsolvencyProvenance`
and three `FilingProvenance`. `FiledDocument` ×4, `FilingHistory` ×4, `InsolvencyCase`/`Event` ×2,
`Charge` ×2. D-042(b) declined by name "a hand-rolled per-block provenance … two shapes for one
concept — the single thing R-5 exists to prevent"; S-series finding 8 asked that the wiring commit
be checked for the stand-in's *removal*, not its re-export. `e03a518` instead converts at the seam
on every call (`model_validate(model_dump())` in all four `__init__.py` methods) and adds a drift
test to police the copies — testing a problem rather than removing it. The canonical descriptions
were rewritten country-neutral, so the four copies already differ in prose; a field change is now
four edits and a test.
*Exact change:* each module imports the four core classes and drops its own; the four registry
methods become `return await client.fetch_x(id)`; the four conversion tests go with the conversion.
Country modules and `__init__.py` only. **Do it before T38**, whose Part A would otherwise build a
fifth stand-in behind the seam.

**5. The card's `include` parameter is stale; "regenerated" was two thirds true. — NON-BLOCKING
(card only; live `tools/list` is right).**
`static/well-known/mcp/server-card.json` → `lookup_company.inputSchema.properties.include` still
carries the pre-HEAD description ("e.g. ['charges'] for United Kingdom (country='GB')…") and examples
`[["charges"], []]`; `mcp/server.py:284,298` now say otherwise. The tool descriptions and
`outputSchema` were regenerated, the `inputSchema` was not, and the drift test
(`tests/test_mcp.py:158`) compares names, descriptions, titles, prompts and `lookup_company`'s
`outputSchema` — never `inputSchema` — so it passed. `test_mcp.py:161` records that nothing
regenerates the card. *Exact change:* regenerate `inputSchema` from the live server and extend the
drift test to it, so the third kind of drift is caught the way the first two are.

**6. The static discovery surfaces do not know two of the three includes exist. — NON-BLOCKING.**
`api/main.py:798-807` (the REST `include` query description): charges only. `static/llms-full.txt`:
the sole `include` mention is `include=["charges"]` (`:362`). `README.md`, `docs/clients.md`,
`static/llms.txt`: no `include`, no `supported_includes`. D-042(d)(2) was paid on the MCP tool text;
REST's OpenAPI and `llms-full.txt` are the same retrieval key for REST callers and crawlers.

**7. `CHANGELOG.md` `[Unreleased]` is empty across ~15 commits that changed the wire, one of them a
removal. — NON-BLOCKING.**
Since `v0.3.0`: `SourceRef`, `include`, `lookup_with`; `CompanyReport` gained `charges`, `filings`,
`insolvency`; `CountryInfo.supported_includes`; two prompts; and `registers["charges"]` was
**removed** from every GB report (`beb287f`) — a key 0.3.0 served. The file's own header says
versioning applies to response shapes; `pyproject.toml` is still 0.3.0 and so is production's
`/health`, so the next deploy serves a 0.3.0 that PyPI's 0.3.0 does not have.

**8. S-series findings 4–10 were not applied, and finding 4's failure scenario happened. — for Kim.**
1–3 are closed (`beb287f`, `770c53c`). **S4:** `charges.py:21,27,94,106,115,123,180,246` still cite
"D-042 part (h) — the ruled shape of the future `core.models.Charge`"; `core/models.py:600,675` now
hold `Charge`/`ChargeBlock` citing D-042(g),(h); `DECISIONS.md` contains **none** of `charge_id`,
`charge_number`, `assets_charged`, `obligations_secured`, `contains_floating_charge`,
`satisfied_count`. The shared, country-neutral charge shape D-042(g) reserves for Norway's and
Sweden's future fillers is an implementer's proposal under an architect's citation, in `core/`, on
the wire. **S5:** `instructions` still carries the pitch without the payment-fraud caveat (the
caveat lives only in the prompt, `:730`). **S6:** no missing-method test; `core/registry.py:341-342`
still promises a `RuntimeError` for a missing method (it raises `AttributeError`);
`mcp/server.py:93` still defaults `ok = True`. Mitigated: the new static test makes the
misconfiguration unreachable for the three real countries. **S8:** finding 4. **S9:** no chart test;
`height='auto'` still at `dashboard.py:474`. **S10:** `charges.py:80,87,284` still say "39"; no
`ch_09446231_charges.json`. The S-series section itself is uncommitted; if the tree is lost, 4–10 go
with it.

### What is factually untrue in what was committed

1. `e03a518` message and D-044(b): "*the scope difference is disclosed in each block's own notes, on
   every call*." False for Sweden (no note) and Britain (no scope note). (Finding 1.)
2. `mcp/server.py:342` / card: "*the block's own `notes` says which*." `core/models.py:857`:
   "*`notes` says which, in words, on every block*." Same. (Finding 1.)
3. Session handoff: "server-card.json regenerated." `inputSchema` was not. (Finding 5.)
4. `core/registry.py:341-342`, carried forward: a missing method "fails loudly here (see the
   `RuntimeError` below)". It raises `AttributeError`. (S6, still open.)
5. `charges.py` ×8 and `core/models.py:600,675`, carried forward: the charge shape is "ruled" by
   D-042(h). D-042(h) rules `FiledDocument`. (S4, still open.)

### Must land before the next deploy

* **Finding 1** — two constants, two assertions, country modules only. Without it the deploy ships a
  promise the wire does not keep, in the JSON schema itself.
* **Finding 3** — the board, so the next session does not start from a chat message again.
* **Finding 2** — a row, not code; the code is a Sonnet task against `tasks/T31.md` §4 that is now
  unblocked.
* **Finding 5** — regenerate the card's `inputSchema` before Smithery re-scans.
* Decide **S4** with the architect: either a D-042 amendment ruling `Charge`/`ChargeBlock`'s field
  list, or the citations are corrected to say the list is the module's proposal.

### What holds, and is worth keeping

The measurement in D-044(a) is true — I re-derived it from the four class bodies, not the commit
message. The routing test is the right test: a `filings` method that filled `charges` would pass its
own module's suite and fail exactly this one. Replacing the three seam-pins with a cross-country
invariant that reads `supported_includes` against `model_fields` and `country_info()` is stronger
than what it replaced, and it is what makes S6's remaining gap safe in practice. The practitioner bar
enforced by the *absence* of a field, asserted by a `ValidationError`, is the cheapest kind of
guarantee there is. And Norway's `_ONE_PERIOD_NOTE` is precisely the disclosure D-044(b) describes,
which is why finding 1 is a copy, not a design.

**Post-merge addendum (2026-09-08 22:00Z, after T40).** D-044(a) states that when the docstrings moved to
`core/models.py` "every fact in them was kept, including the count of live observations behind each claim."
T40 diffed every field description against its stand-in before deleting it and found **ten facts that survive
nowhere in the tree** — Sweden's 18-month-period citation and its 7 500 / 15 000 kr fee figures, the 22
British filing categories, the thirteen insolvency event words, the eight status words, the meaning of the
one note code, the Norwegian licence gloss, and three more — plus one canonical description ("newest first by
`filed_at`") that is Britain's sort key stated as everyone's. Listed verbatim in `tasks/T47.md`'s addendum
and restored there. Correction to this review's own finding 4: the drift test D-044(e) added would not have
caught any of this, because a *description* is not a field — the copy was faithful in shape and lossy in
substance. T40's report, not the tests, found it.

---

## Depth track `e03a518..81c91e7` — 2026-09-09 — APPROVED WITH FIXES (one blocking, two urgent; the machinery is correct end to end)

Reviewer: Opus reviewer (T58), `tasks/T58.md`. Scope: every commit since `e03a518` — 84 commits, rounds 1–3
(T38, T40, T42, T43, T44, T45, T47), the rulings D-045/D-046/D-047, T46 and T46b's surfaces syncs, T55's
Swedish financials and T57's re-recorded TEST fixtures.
Executed against a pristine export of `HEAD` (`git archive HEAD | tar -x`), never the working tree,
with `uv sync --locked --all-extras`.

* `uv run pytest -m "not live" -o addopts="" -p no:cacheprovider` → **1030 passed, 26 deselected,
  1 warning** — exactly the count `db20fd5`/T46b claims. `uv run mypy .` → clean, **77 source files**.
  `uv run ruff check .` → clean. **CI is green at HEAD.**

### Checklist

| # | Claim under test | Method | Result |
|---|---|---|---|
| 1 | 1030 tests pass at committed HEAD | pristine `git archive` export + `uv sync --locked --all-extras` | **PASS** — 1030 passed, 26 deselected |
| 2 | `mypy .` clean (77 files), `ruff check .` clean | executed on the export | **PASS** |
| 3 | The seven attachments answer on both surfaces, filled | 12 country×include cases through the real REST app and an in-process MCP client | **PASS** |
| 4 | REST ≡ MCP for every one | field-for-field comparison of each block | **PASS** |
| 5 | Each `bad_request` names the right allowed set | 9 non-declaring combinations, both surfaces | **PASS** |
| 6 | Each failed fetch leaves the block absent with a `notes` sentence | 500 injected on each attachment's own upstream | **PASS** ×8 |
| 7 | Present-and-empty is a real answer, not an absence | GB `filing-history-available` + 0 items; SE empty `dokumentlista` | **PASS** |
| 8 | D-043(h): `filings`+`financials` on NO cost one request, one `SourceRef` | mutation M1 | **PASS** |
| 9 | D-045(e): `lei` absent for SE; `effective_includes` everywhere | mutation M2 + the 9 `bad_request` hints | **PASS** |
| 10 | D-047(a): `lei`+`parents` share one GLEIF search | mutation M3 | **PASS** |
| 11 | D-046: the SMP host comes from the NAPTR | mutation M4 (hardcoded ELMA) | **PASS** — the Conta fixture makes the hardcode fail |
| 12 | D-046: `false` only on NXDOMAIN / SMP 404 | mutation M5 | **PASS** |
| 13 | D-046: `null` is never cached | mutation M6 | **PASS** |
| 14 | D-045(a): the three charge flags are never `False` | mutation M7 | **PASS** |
| 15 | D-044(b): the scope note is first on every `filings` block, all three countries | mutations M8a–M8d | **PARTIAL** — SE and GB pinned; **NO not pinned at all**, finding 3 |
| 16 | D-047(f): `/dokumentlista` shared in flight with `filings` | mutation M9 | **PASS** |
| 17 | D-047(f): exactly one `/dokument` per lookup | mutation M10 | **PASS** |
| 18 | D-047(g): the element filter admits `ix:nonFraction` only | mutation M11 + a direct runtime check | **PASS with a caveat** — finding 5 |
| 19 | D-047(g): `Soliditet` never read | mutation M18 | **PASS** |
| 20 | D-043(d): `currency` from the unit, never from a concept | mutations M12a / M12b | **PARTIAL** — "never from a concept" is pinned; "from the unit or not at all" is not, finding 4 |
| 21 | D-047(g): `liabilities` and `total_comprehensive_income` are `None` unconditionally | mutation M13 | **FAIL** — finding 2 |
| 22 | D-047(f): figures cached on `dokumentId`; the document never stored | mutations M14, M15 | **PASS** |
| 23 | D-042(e)(2): no practitioner particular relayed or cached | mutation M19 | **PASS** |
| 24 | D-042(e)(1): `description_values` allow-list is one key with one reader | grep + read | **PASS** |
| 25 | D-028/D-040: no natural person's name or real personnummer in any committed Swedish fixture | read every `bv_*.json` and `se_ixbrl_*.xhtml` | **PASS** |
| 26 | The T31a sentence is gone from every shipped surface | `grep -rn "does not publish the financial year" src/ static/ README.md content/ legal/ mcpb/ plugins/ packages/` | **PASS** — hits only in `tasks/`, `DECISIONS.md`, `PROGRESS.md`, the CHANGELOG's own *Fixed* line and the test that asserts its absence |
| 27 | The privacy policy and terms name three countries and carry no "Draft" | read `legal/*.md` at HEAD | **PASS at HEAD**, **FAIL on the wire** — see the deploy delta |
| 28 | `_INCLUDE_DESCRIPTION`, both docstrings, `instructions`, README, `llms-full.txt`, the card: every claimed capability exists | rendered each and checked every clause against the code | **FAIL** — finding 1 (five surfaces) |
| 29 | Every manifest at 0.4.0, `uv.lock` included | grep across 13 manifests + `uv.lock:1560` | **PASS** — except `README.md:63`, finding 6 |
| 30 | `dnspython`'s licence is recorded where a distributor can find it | grep | **PASS** — `CHANGELOG.md:160`, *"`dnspython>=2.7` (ISC licence) is a new runtime dependency"*; the licence is also derivable from `uv.lock`'s pin |
| 31 | Description B names exactly what 0.4.0 serves, within the cap | re-derived by substituting B's sentence into A | **PASS** — A 1,837 and B **1,992** characters, exactly as claimed; the seven attachments and their countries are correct |
| 32 | `[Unreleased]` covers every wire-visible change since `v0.3.0` | 52 wire-touching commits vs the section's 31 cited shas + prose | **PASS** — see the deploy-delta note |
| 33 | S-series findings 4, 5, 6, 9, 10 are closed | grep + read | **PASS** — all five |
| 34 | The card matches the live server | `test_server_card_*` ×2 + `scripts/regen_server_card.py` run mentally over the card | **PARTIAL** — tools and prompts match; `resources` does not, finding 7 |

### Mutation results

| # | Claim under test | Mutation | Test that went red |
|---|---|---|---|
| M1 | D-043(h)(2,3): `filings`+`financials` on NO cost one upstream request | deleted the `_inflight_accounts_fetch` rendezvous in `no/client.py` | **RED** — `test_d043_invariant1_concurrent_fetch_accounts_and_fetch_financials_share_one_request`, `…_lookup_with_both_includes_makes_exactly_one_upstream_request`, `…invariant2_provenance_equal_in_all_five_fields` |
| M2 | D-045(e): `lei`/`parents` absent for SE, `effective_includes` everywhere | removed the `id_may_be_personal` subtraction in `core/registry.py::effective_includes` | **RED** ×5 — `test_effective_includes_drops_universal_when_id_may_be_personal`, `test_sweden_include_lei_is_bad_request_not_an_empty_block`, `test_list_countries_shows_lei_for_no_and_gb_but_not_se`, and the two `parents` twins |
| M3 | D-047(a): `lei`+`parents` share one GLEIF search | deleted the `_inflight_search` rendezvous in `core/gleif.py` | **RED** — `test_lei_and_parents_together_make_exactly_one_search_request` (2 ≠ 1) |
| M4 | D-046(d): the SMP host comes from the NAPTR, a hardcoded one is a defect | forced `smp_base = "https://smp.elma-smp.no/"` after a successful resolve | **RED** — `test_non_elma_host_is_read_from_the_naptr_not_hardcoded`, `test_26_document_types_survive_the_full_fetch_uncapped` |
| M5 | D-046(a): `false` only on NXDOMAIN / SMP 404, a Directory miss is `null` | Directory miss returns `registered=False` | **RED** ×3 — `test_noerror_no_meta_smp_record_is_null_not_false`, `test_resolver_timeout_then_directory_empty_is_null_but_present`, `test_null_is_never_written_to_the_cache` |
| M6 | D-046(d): `registered: null` is never cached | added an `else: cache.set(...)` branch | **RED** ×2 — `test_null_is_never_written_to_the_cache`, `test_naptr_to_smp_binding_is_never_cached_under_any_key` |
| M7 | D-045(a): the three `contains_*` flags are `True`-or-absent, never `False` | `particulars.get(k)` → `bool(particulars.get(k))` | **RED** ×4 — incl. `test_charges_contains_flags_absence_maps_to_none_never_false` |
| M8a | D-044(b): the scope note is first on every SE `filings` block | `notes = [_SCOPE_NOTE]` → `notes = []` | **RED** ×2 — `test_scope_note_is_present_first_on_every_block_d044b` (SE) |
| M8b | …on every GB `filings` block | same, `gb/filing_history.py` | **RED** ×2 — `test_scope_note_is_present_first_on_every_block_d044b` (GB) |
| M8c | …first on every NO `filings` block | `notes.insert(0, _ONE_PERIOD_NOTE…)` → `notes.append(…)` | **not caught** — 1030 pass |
| M8d | …present at all on every NO `filings` block | deleted the `_ONE_PERIOD_NOTE` line outright | **not caught** — 1030 pass (finding 3) |
| M9 | D-047(f): `/dokumentlista` is shared in flight with `filings` | deleted the `_inflight_dokumentlista_fetch` rendezvous | **RED** — `test_d047_f8_one_dokumentlista_request_serves_filings_and_financials` (2 ≠ 1) |
| M10 | D-047(f): exactly one `/dokument` per lookup | fetched every listed document, not only the newest | **RED** ×4 — `test_d047_f9_exactly_one_dokument_request_for_six_listed_reports` and three others |
| M11 | D-047(g): the element filter admits `ix:nonFraction` only | `!= "nonFraction"` → `not in ("nonFraction", "nonNumeric")` | **RED** — `test_d047_f3_extractor_element_filter_is_static_and_nonnumeric_never_leaks`, on its **static** half only (see finding 5) |
| M12a | D-043(d): `currency` comes from the unit, no default | unresolved currency falls back to `"SEK"` | **not caught** — 1030 pass (finding 4) |
| M12b | …and never from a concept | read `Redovisningsvaluta` as a fallback lookup key | **RED** — `test_d047_f2_2020_currency_via_unit_and_redovisningsvaluta_never_read` |
| M13 | D-047(g)/D-043(e): SE `liabilities` is `None` unconditionally | derived `liabilities = current + non_current` | **not caught** — 1030 pass (finding 2) |
| M14 | D-047(f): the figures are cached on `dokumentId`, not the company | keyed `_financials_cache_key` on the organisationsnummer | **RED** — `test_d047_f12_cached_payload_carries_no_document_and_no_nonnumeric` |
| M15 | D-047(f): the document itself is never stored | wrote the XHTML into the cache payload | **RED** — `test_d047_f12_cached_payload_carries_no_document_and_no_nonnumeric` |
| M16 | T46b: `/health` and the card are pinned to `pyproject.toml` | `__version__` → `9.9.9` | **RED** ×2 — `test_version_matches_pyproject`, `test_well_known_server_card_version_matches_package` |
| M17 | D-042(j): the truncation note states how many reports the list held | `total=total_annual_reports` → `total=1` | **RED** — `test_d047_f9_exactly_one_dokument_request_for_six_listed_reports` |
| M18 | D-047(g): `Soliditet` is never read | added `Soliditet` to the balance-sheet concept table | **RED** — `test_d047_f4_soliditet_never_read_as_a_lookup_key` |
| M19 | D-042(e)(2): no practitioner particular is relayed or cached | made `strip_practitioners` a no-op | **RED** ×2 — `test_insolvency_strip_practitioners_removes_the_key_and_nothing_else`, `test_fetch_insolvency_never_writes_a_practitioner_to_the_cache` |

**23 mutations, 19 caught, 4 not.** Every mutation was reverted and the export re-verified byte-identical
to `HEAD` afterwards (`diff` against `git show HEAD:<path>` on every touched file); the suite is back at
1030 passed. The four misses are findings 2, 3 and 4.

### The seven attachments end to end, both surfaces

Built a throwaway harness in the scratch export (`tests/test_t58_e2e.py`, never committed) that drives the
**real** `api.main:app` through `TestClient` and the **real** `mcp.server:mcp` through an in-process
`fastmcp.Client`, against committed fixtures only — no Companies House, no Bolagsverket, no network.
**34 assertions, all pass.**

| State | Result |
|---|---|
| Present-and-filled ×12 (`filings` GB/NO/SE, `charges` GB, `insolvency` GB, `financials` NO/SE, `lei` GB/NO, `parents` GB/NO, `peppol` NO) | **PASS** — REST ≡ MCP field-for-field on every block (provenance timestamps normalised out) |
| `bad_request` for a non-declaring country ×9 | **PASS** — hints are exactly `GB: charges, filings, insolvency, lei, parents` / `NO: filings, financials, lei, parents, peppol` / `SE: filings, financials`. SE is `bad_request` for `lei` **and** `parents` (D-045(e), D-047(a)); GB and SE are `bad_request` for `financials`/`peppol` respectively, never a silently empty block |
| Failed fetch ×8 | **PASS** — block absent, one report-level `notes` sentence naming the attachment and the upstream, in every country |
| Present-and-empty | **PASS** — GB `filings` (`filing-history-available`, 0 items) and SE `filings` (empty `dokumentlista`) both return a **present** block with `documents: []` and the scope note first |
| SE `financials` vs `filings` on the identical wire state | **PASS** — `filings` present-and-empty, `financials` **absent** plus *"Bolagsverket's digital annual-report channel holds no filed annual report for 5561890038"* (D-042(d)(3), the deliberate asymmetry) |
| `peppol` when the SMP 500s and the Directory 500s | **PASS** — present block, `registered: null`, two notes; **not** absent, because `participant_id` is still worth returning (D-029(c)) |
| `peppol` when the resolver *and* the Directory both fail | **PASS** — absent block plus the report-level note (the only total-failure path) |

### The person-bearing line

| # | Claim under test | Method | Result |
|---|---|---|---|
| P1 | Nothing reads `practitioners` | `grep -rn practitioner src/` | **PASS** — every hit is prose; `strip_practitioners` removes the key before the cache, and neither `InsolvencyCase` nor `InsolvencyEvent` has a field one could land in (`extra="forbid"`) |
| P2 | Nothing reads the Peppol Directory's `contact` | `grep -rn contact src/` | **PASS** — the only `contact` hits are `REGISTRY_MCP_CONTACT_EMAIL` in the three User-Agent builders, plus `no/peppol.py:68-71`'s docstring saying the block is never requested or read |
| P3 | `description_values` beyond `made_up_date` | `grep -rn description_values src/registries/gb/` | **PASS** — one allow-list, `frozenset({"made_up_date"})`, one reader (`_allowed_values`), written as a filter over the list so a payload key outside it can reach nothing |
| P4 | Officer / PSC keys | grep for `/officers`, `persons-with-significant`, `officer_name`, `psc` | **PASS** — prose and the allow-list's own comment only; no fetch, no field |
| P5 | GLEIF `SOLE_PROPRIETOR` / `NATURAL_PERSONS` handling | read `core/gleif.py` and `ParentLink`'s descriptions | **PASS** — `reporting_exception` is GLEIF's closed category vocabulary relayed verbatim, never a name; `ParentLink.legal_name` is a *company* name bound by D-028(1), and its description records the sole-proprietor risk explicitly rather than assuming it away |
| P6 | Nothing outside an `ix:nonFraction` value reaches the Swedish block | mutation M11 + a runtime check | **PASS with a caveat** — see finding 5 |
| P7 | No committed Swedish fixture carries a natural person's name | read every `bv_*.json` and every `se_ixbrl_*.xhtml` | **PASS** — T57's live TEST recordings carry `[REDACTED TEST NAME]` / `[REDACTED TEST NAME 1|2]` placeholders; all five iXBRL fixtures are hand-built and carry a `FIXTURE NOTICE` saying so, none has an `ix:nonNumeric` signature concept except the deliberate leak-check one, whose token is `ZZZ-NOT-A-REAL-NAME-LEAK-CHECK-ZZZ` |
| P8 | …or a real personnummer | listed every 10–12-digit run in the Swedish fixtures | **PASS** — the four twelve-digit numbers (`193403223328`, `198101032384`, `198101052382`, `194009272719`) are Bolagsverket's own **TEST**-environment workbook identifiers, each row documented in `tests/fixtures/README.md:141-144`; no production personnummer anywhere |

### Findings

**1. Five published surfaces say a `financials` block is *present-with-`periods: []`* when the register
holds no accounts. For Sweden the block is **absent** — deliberately, per `tasks/T55.md` §"Absent versus
empty" — and for Britain the state described cannot occur at all. — BLOCKING (a false statement about a
wire-visible state, in the JSON schema itself).**

Measured end to end on the real app, both surfaces, with an empty `dokumentlista`:

```
NO include=financials, no filed accounts  -> block PRESENT,  periods: []
SE include=financials, no filed accounts  -> block ABSENT,   report note: "Could not fetch the
    'financials' attachment: Bolagsverket's digital annual-report channel holds no filed annual
    report for 5561890038."
GB include=financials                     -> 400 bad_request (never an absent block at all)
```

The **code is right** — `registries/se/__init__.py:154-158` and `client.py::fetch_financials` state the
asymmetry explicitly and `tasks/T55.md` line 233 makes it non-negotiable ("gets an **absent** block plus a
report-level `notes` sentence … **not** an empty `FinancialSummary`"). What is wrong is every sentence
written about it. The claim was true when T38 wrote it for Norway alone; T46b corrected this description's
*mechanism* half ("Norway only … the reason is ours") and left its *nullability* half generalised to "a
country that declares this attachment":

* `src/registry_mcp/core/models.py:2299-2302` — `CompanyReport.financials`: *"A country that declares this
  attachment returns a **present** block with `periods: []` for an entity the register holds no filed
  accounts for — the two states never collapse into each other (D-011, D-042(d))."* This ships in the
  card's `lookup_company.outputSchema` (verified: the string is in `static/well-known/mcp/server-card.json`)
  and in `/openapi.json`.
* `src/registry_mcp/mcp/server.py:404-406` — `lookup_company`'s docstring, i.e. the card's tool
  description and every MCP client's tool list: *"an absent block means the country's register publishes
  no figures at all — true of Britain today"*.
* `src/registry_mcp/api/main.py:821-823` — the REST `include` query description: *"an absent block means
  the country does not publish figures at all — true of the United Kingdom today"*.
* `static/llms-full.txt:517-519` — in **bold**: *"an absent `financials` block means the country's
  register does not publish figures at all."*
* `CHANGELOG.md:61-63` — *"A company whose document list is empty gets a present block with `periods: []`,
  the same two-level nullability `filings` already has (D-047(f),(g))."*

*Failure scenario.* An agent asks for `include=["financials"]` on a Swedish supplier, gets no block, and
has been told in the schema it is reading that this can only mean *the country publishes no figures* or
*you did not ask*. Both are false; the true meaning is *this company has filed no digital annual report* —
which is a fact about the company and, for a solvency question, a signal. The `notes` sentence is there
and is correct, but the schema tells the reader not to look for it. This is D-011's two-states collapse in
the one document written to prevent it, and it is the same defect class as the D-044-wiring review's
finding 1, one round later.

*Exact change (≈25 min, 5 files, no test rewrite needed — nothing pins these strings).*
1. `core/models.py:2299-2302`: replace the sentence with the country-true pair — *"Norway returns a
   **present** block with `periods: []` for an entity Regnskapsregisteret holds no filed accounts for.
   Sweden instead returns **no block at all**, plus a report-level `notes` sentence naming the reason,
   because Bolagsverket's digital annual-report channel holds nothing for that entity — a fact about the
   company, not about the country (D-042(d)(3), `tasks/T55.md`)."*
2. `mcp/server.py:404-406` and `api/main.py:821-823`: replace *"an absent block means the country's
   register publishes no figures at all — true of Britain today"* with *"an absent block means either you
   did not ask, or the fetch failed, or — for Sweden — this company has filed no digital annual report;
   the report's own `notes` says which. Britain does not declare `financials` at all, so
   `include=["financials"]` for `GB` is a `bad_request`, never an empty or absent block"*, keeping the
   existing 1 April 2028 clause as the reason Britain does not declare it.
3. `static/llms-full.txt:517-519`: the same correction, and drop the bold.
4. `CHANGELOG.md:61-63`: *"A company whose document list is empty gets **no** `financials` block and a
   report-level note saying so — deliberately unlike `filings`, which returns a present block with
   `documents: []` for the identical wire state."*
5. Re-run `uv run python scripts/regen_server_card.py` (it rewrites `outputSchema` and the tool
   descriptions), then `uv run pytest -m "not live" -o addopts="" -p no:cacheprovider`.

**2. `liabilities` can be derived from the two Swedish sub-totals and no test notices. — URGENT
(non-blocking today; the guard the docstring promises does not exist).**
`registries/se/financials.py`'s module docstring says the sum *"is refused by name, D-043(e), D-043(f)"*.
Mutation M13 added exactly that arithmetic — `values["liabilities"] = (current or 0.0) + (non_current or
0.0)` in `_map_balance_sheet` — and **1030 tests still pass**. The same is true of
`total_comprehensive_income`: `grep -rn "\.liabilities\b\|total_comprehensive_income" tests/` returns
**nothing**. D-043(e) is this project's single most-argued rule and the two fields it bites hardest on are
pinned by prose alone.
*Exact change (≈10 min, `tests/test_client_se.py`):* one test asserting that on both real K2 fixtures
`period.balance_sheet.liabilities is None` **and**
`period.income_statement.total_comprehensive_income is None` even though `current_liabilities` (and, on the
2020 fixture, `non_current_liabilities`) are present and non-`None` — so the arithmetic is what the test
forbids, not the absence of inputs. Name D-043(e)/(f) in the docstring.

**3. Norway's `filings` scope note — the one the D-044-wiring review called "precisely the disclosure
D-044(b) describes" — can be deleted outright and every test still passes. — URGENT (non-blocking today).**
Mutations M8c (note no longer first) and M8d (note removed entirely) both leave **1030 passing**. Sweden and
Britain each got `test_scope_note_is_present_first_on_every_block_d044b` from T40; Norway, whose
`_ONE_PERIOD_NOTE` was the *model* for both, never did — `grep -rn "d044b" tests/` finds exactly two hits,
`test_client_gb.py:1926` and `test_client_se.py:1425`.
*Exact change (≈10 min, `tests/test_client_no.py`):* the same test for Norway — map
`brreg_regnskap_923609016.json` through `accounts.map_accounts` and assert `notes[0]` starts with
Regnskapsregisteret's one-period sentence, and that the empty-payload case leads with `_EMPTY_NOTE`. Both
states, because Norway's note is chosen by a branch rather than prepended unconditionally.

**4. Sweden's currency can silently acquire a default and no test notices. — NON-BLOCKING.**
D-043(d) makes `currency` required with no default, and `financials.py::_resolve_currency` correctly
returns `None` when zero or more than one currency resolves. Mutation M12a changed that `return None` to
`return "SEK"` — the exact shape D-043(d) forbids — and **1030 tests pass**. The reason is that no fixture
exercises the branch at all: `grep -rn "CURRENCY_UNRESOLVED" tests/` is empty, so
`build_period`'s only `None` return, `summary_notes(None)` and `_CURRENCY_UNRESOLVED_NOTE` are together
dead code as far as the suite is concerned. (M12b — reading the `Redovisningsvaluta` concept as a fallback —
*is* caught, by F2's AST check, so the "never from a concept" half is genuinely load-bearing; it is the
"from the unit, or not at all" half that is not.)
*Exact change (≈15 min):* one hand-built fixture whose facts carry a `procent`/`pure` unit only (or two
different ISO 4217 units), asserted to yield `periods == []` and `notes == [_CURRENCY_UNRESOLVED_NOTE]`.

**5. The `ix:nonFraction`-only guarantee rests entirely on one AST assertion; the runtime half cannot
catch a breach. — NON-BLOCKING, but say so where the guarantee is claimed.**
`test_d047_f3_...` has a static half and a runtime half. I mutated the filter to
`not in ("nonFraction", "nonNumeric")` and confirmed the test goes red — but on the static half only, and
via `assert "nonFraction" in compared_literals`, not via `assert "nonNumeric" not in compared_literals`.
I then ran the mutated extractor against the leak-check fixture directly: **the token does not leak**,
because `_parse_number` drops any fact whose `@format` is not one of the two comma-decimal forms and an
`ix:nonNumeric` element carries no `@format`. So the runtime half passes under the very mutation it exists
to catch. The static half is what holds the line, and it holds it in the robust direction — any
restructuring that removes the literal `!= "nonFraction"` comparison fails the positive assertion, however
the negative one is dodged. Worth one sentence in the test's docstring saying which half is load-bearing,
so a future edit does not "simplify" the positive assertion away.

**6. `README.md:63` still advertises 0.3.0, including a `/health` body it quotes verbatim. — NON-BLOCKING,
but it is the PyPI long description and the repo's first screen.**
`> Status: `0.3.0`, live — `GET /health` returns `{"version":"0.3.0","countries":["GB","NO","SE"]}`.`
Every manifest is at 0.4.0 (verified: `pyproject.toml`, `src/registry_mcp/__init__.py`, `server.json`,
`mcpb/manifest.json`, `.claude-plugin/marketplace.json`, `plugins/registry-mcp/.claude-plugin/plugin.json`,
both npm `package.json`s, `packages/brreg-mcp/pyproject.toml` *and* its `registry-mcp==0.4.0` pin,
`static/well-known/mcp/server-card.json`, and **`uv.lock`'s own project entry at line 1560**) — README is
the one that was missed. Lines 117 and 346 ("added in 0.3.0", "shipped in 0.3.0") are historical and correct;
leave them.
*Exact change (≈2 min, `README.md:63`):* both `0.3.0` occurrences in that line become `0.4.0`.

**7. The server card publishes `"resources": []` while the server serves three. — NON-BLOCKING
(pre-dates this scope; the card-drift test still does not cover it).**
`static/well-known/mcp/server-card.json` → `resources: []`. Live: `registry://rules/GB`,
`registry://rules/NO`, `registry://rules/SE`, plus the template `registry://rules/{country}`. This is
D-044-wiring finding 5's third face: `scripts/regen_server_card.py` (added `69b79da`) regenerates tools and
prompts and not resources, and `test_server_card_tools_and_prompts_match_the_live_server` compares tools and
prompts and not resources — so the one document a crawler reads without calling the server says this server
has no resources. *Exact change (≈15 min):* four lines in the regen script (`await client.list_resources()`
→ `card["resources"]`), the same three lines in the drift test, run the script.

**8. The `country` and `id` argument descriptions on every tool name two of three countries. —
NON-BLOCKING (pre-dates `e03a518`; T17's `86132df`).**
`mcp/server.py:304-311`: `_COUNTRY_DESCRIPTION` = *"'NO' = Norway …, 'GB' = United Kingdom … Call
list_countries for the current set"*; `_COUNTRY_EXAMPLES = ["NO", "GB"]`. `_ID_DESCRIPTION` likewise
documents the Norwegian and British identifier formats and not the organisationsnummer. These are published
in the card's `inputSchema` for `lookup_company`, `company_deadlines` and `validate_company_id`. The
`instructions` string and the tool docstrings both cover Sweden properly, so this is an omission in the one
place a client renders per-argument help. *Exact change (≈5 min):* add the Swedish clause to both constants
and `"SE"` to `_COUNTRY_EXAMPLES`, then re-run `scripts/regen_server_card.py`.

### What is factually untrue in what was committed

1. `core/models.py:2299-2302`, in the card's `outputSchema`: **"A country that declares this attachment
   returns a *present* block with `periods: []` for an entity the register holds no filed accounts for —
   the two states never collapse into each other."** Sweden returns no block. (Finding 1.)
2. `mcp/server.py:404-406` and `api/main.py:821-823`: **"an absent block means the country's register
   publishes no figures at all — true of Britain today."** Britain cannot produce an absent block;
   `include=["financials"]` for `GB` is a 400. (Finding 1.)
3. `static/llms-full.txt:517-519`: the same sentence, in bold. (Finding 1.)
4. `CHANGELOG.md:61-63`, `9778f29`/`447b015`: **"A company whose document list is empty gets a present
   block with `periods: []`."** It gets no block. (Finding 1.)
5. `registries/se/financials.py`'s module docstring: **"`current_liabilities + non_current_liabilities` is
   refused by name"** — refused by the code, yes; by nothing that would notice if it stopped being.
   (Finding 2.)
6. `README.md:63`: **"Status: `0.3.0`, live."** `pyproject.toml` says 0.4.0. (Finding 6.)
7. `static/well-known/mcp/server-card.json`: **`"resources": []`.** Three are served. (Finding 7.)

### The deploy delta — what production serves today vs `HEAD`

Six unlogged static reads against `api.foretak.dev`, no register touched. (One more than the brief's five:
I also fetched `/llms-full.txt`, the same class of static discovery file; noted rather than hidden.)

| Route | Served | `HEAD` | Delta |
|---|---|---|---|
| `/health` | `{"status":"ok","version":"0.3.0","countries":["GB","NO","SE"]}` | `0.4.0` | **Stale.** Production is `bf1f37f` (deployment `3798e727`); nothing from rounds 1–3, T46, T46b, T55 or T57 is live |
| `/.well-known/mcp/server-card.json` | 132,758 bytes | differs | `serverInfo.version` 0.3.0 vs 0.4.0; `lookup_company` **description, inputSchema and outputSchema** all differ; `company_deadlines` description and inputSchema differ. `title`, top-level `description`, `authentication`, `prompts` and `resources` are byte-identical (the last because both are `[]` — finding 7) |
| `/legal/privacy` | **"*Draft written 2026-09-05 for Kim's review; effective once published at a public URL*"**, one mention of Sweden | "*Effective 2026-09-09*", four mentions of Sweden/Bolagsverket, no "Draft" | **The T50 finding is still live.** A labelled draft is the immediate-rejection material T50 identified for the Connectors Directory, and it is what a reviewer opening the listing's privacy-policy URL sees right now |
| `/legal/terms` | **Norway only** — Enhetsregisteret / Brønnøysundregistrene / NLOD 2.0, and no mention of Companies House or Bolagsverket anywhere in 6,054 characters | names all three registers with their own licence regimes (`legal/terms.md:24-58`) | **The terms page on the wire attributes two of three registers to nobody.** Companies House's Crown-copyright credit and Bolagsverket's stated-absence licence are both obligations we tell callers pass to *them* |
| `/llms.txt` | — | — | **Byte-identical.** No delta |
| `/llms-full.txt` | 70,929 bytes | differs, 241 changed lines | Stale: 15 `financials`, 14 `LEI`, 8 `Peppol`, 8 `parents`, 6 `Sweden` insertions missing on the wire |

**Two consequences worth stating plainly.** (a) Everything in finding 1 is *not yet live* — it ships with
this deploy, which is exactly why it belongs on the "before" list rather than in a follow-up. (b) The two
legal pages are the strongest argument *for* deploying promptly: the wire is worse than `HEAD` on both, and
the fix is already committed.

**`CHANGELOG.md` `[Unreleased]` completeness.** 52 commits since `v0.3.0` touch `src/`, `static/` or
`legal/`; the section cites 31 shas and covers the rest by prose. I checked what it does *not* cite and
found no wire-visible gap: `411e50a`, `9288390`, `0595052`, `dd8643b`, `48cb6ab` all built behind the seam
and reached the wire through `e03a518`/`3ecc369`, which are cited; `680d92c` (the stand-in fold) changed no
response shape; `96b434e` (the `peppol` TTL row) is covered by the TTL-table bullet; `98a34d1` is a
docstring fix; `b95e1ae`, `355dcdb`, `8e3af45`, `fa1a870`, `bb4ef25` are merges and card regenerations;
`9778f29` and `ee1c636` are the commits that wrote the section. The two genuinely uncited wire-visible
edits are `a3091fe` (three countries in the plugin-marketplace entry, link preview) and `6efb883`
(homepage lead) — static marketing surfaces, not response shapes, and the file's own header scopes it to
response shapes. **The section is complete**, and the one thing in it that is *wrong* is finding 1's
CHANGELOG line, not an omission.

### The orchestrator's own commits

The standing rule is that the orchestrator does not write production code. Five commits are the
orchestrator's own work rather than a merge of an agent's branch:

| Commit | What it is | Production code? | Correct? |
|---|---|---|---|
| `c854e9e` | two assertions in `tests/test_client_no.py`: `sorted(gb.supported_includes)` → `sorted(gb.effective_includes)` | **No** — tests only | **Yes, and necessary.** T42 put `lei` on `universal_includes`, so the `bad_request` `details["allowed"]` for GB and SE is now `effective_includes`; the round-2 merge left the test comparing against the narrower set. Reconciling a test the merge falsified is squarely the merge's job |
| `69b79da` | new `scripts/regen_server_card.py` (56 lines) | **Borderline — say it plainly: yes, it is code.** It is a dev script, not shipped in the wheel (`pyproject.toml` packages `src/registry_mcp` only), and it is a tool for the orchestrator's own merge step | **Yes, and it closes D-044-wiring finding 5.** It regenerates exactly what the two drift tests compare, so a synced card passes and an out-of-date one is fixed by running it rather than by hand. Its one gap is `resources` (finding 7) — and that gap is the drift test's too, so the script is faithful to its stated contract |
| `b95e1ae` | `static/well-known/mcp/server-card.json` regenerated after the peppol field | **No** — generated artefact | **Yes** — the card is green against both drift tests at HEAD, verified on the pristine export |
| `fcde62f` | `CHANGELOG.md` `[Unreleased]` +43 lines, committed because T46's agent session ended with the file unstaged | **No** — release notes | **Yes**, and honestly labelled in its own message. (One of its lines is finding 1's fifth surface — but that sentence came from T55's own commits, not from this one) |
| `ba7d5bb` | a one-word heading in `content/06-what-active-means/devto.md` | **No** | Yes |

Plus `5c71bc8` (T44) and the T43/T55 keep-both conflict resolutions, which are the agent's code committed
or merged by the orchestrator rather than written by it — the commit messages say so, and the diffs match
the agents' reports.

**Verdict on the rule: not crossed.** The one item with any claim to being production code —
`scripts/regen_server_card.py` — is an unshipped maintenance tool that automates a step the orchestrator
was doing by hand and getting wrong (the D-044-wiring review's finding 5 exists because of exactly that).
Writing it was the right call, and it is correct.

### Must land before `railway up`

1. **Finding 1** — the `financials` absent-vs-empty sentence, on five surfaces. ~25 minutes;
   `src/registry_mcp/core/models.py:2299-2302`, `src/registry_mcp/mcp/server.py:404-406`,
   `src/registry_mcp/api/main.py:821-823`, `static/llms-full.txt:517-519`, `CHANGELOG.md:61-63`; then
   `uv run python scripts/regen_server_card.py` and the suite. Exact replacement text is in the finding.
   **This is the only item that must land before the deploy** — it is a false statement about a
   wire-visible state, in the card's `outputSchema` and in `/openapi.json`, and it ships *with* this deploy
   rather than being already live, so fixing it now costs one edit and fixing it later costs a second
   deploy plus whatever a caller built on it.
2. **Finding 6** — `README.md:63`, both `0.3.0` → `0.4.0`. ~2 minutes, one line. Not wire-visible, but it is
   the PyPI long description and it will be published by the same release, so it is cheaper here than after.

Everything else below is a follow-up task, not a deploy gate.

### Not on the "before" list — a Sonnet follow-up, sized

| Finding | Work | Size |
|---|---|---|
| 2 — `liabilities` / `total_comprehensive_income` unpinned | one test in `tests/test_client_se.py` asserting both are `None` on both real K2 fixtures *while* the summands are present | 10 min, 1 file |
| 3 — Norway's scope note unpinned | `test_scope_note_is_present_first_on_every_block_d044b` for NO, both the filled and the empty branch, in `tests/test_client_no.py` | 10 min, 1 file |
| 4 — the currency-unresolved branch is untested | one hand-built fixture with a non-ISO-4217 unit + one test asserting `periods == []` and the `_CURRENCY_UNRESOLVED_NOTE` | 15 min, 2 files |
| 5 — which half of F3 is load-bearing | one sentence in `test_d047_f3_...`'s docstring | 5 min, 1 file |
| 7 — the card's empty `resources` | four lines in `scripts/regen_server_card.py`, three in `test_server_card_tools_and_prompts_match_the_live_server`, run the script | 15 min, 3 files |
| 8 — `_COUNTRY_DESCRIPTION` / `_ID_DESCRIPTION` name two of three countries | add the Swedish clause and `"SE"` to `_COUNTRY_EXAMPLES`, regenerate the card | 5 min, 2 files |

### What is worth keeping

**The Swedish extractor is the best thing in this scope, and the reason is its shape rather than its
output.** `registries/se/ixbrl.py` does not defend the privacy rule with a blocklist of the concept names
that carry a director's name — it defends it by never iterating the element type those names live on, and
it says in its own first paragraph *why* a blocklist would have been the wrong answer (Sweden renamed both
signature concepts between the two taxonomy generations, and the failure would have been silent). Then it
proves the claim with an AST assertion over its own source rather than a comment. That is a rule enforced by
the shape of the code, tested at the level the shape lives at, and it survived the one mutation that
matters. The same module declines to guess an unrecognised `@format` — degrading one field to absent
rather than to a wrong number — and refuses a dimensioned context as the reporting period *structurally*,
so a note-level breakdown cannot be mistaken for a whole-entity total. Three separate "make the bad state
unrepresentable" moves in one 423-line file.

**The `bad_request` hints are the quiet win.** Nine combinations, both surfaces, and every one names that
country's real allowed set — `SE: filings, financials` with no `lei` and no `parents`, `GB` with no
`financials`, `NO` with no `charges`. `effective_includes` subtracting `universal_includes` for a country
whose identifier can be a person's is one line, and mutation M2 turns five tests red the moment it is
removed. A privacy rule that is also the discoverability answer is a rule that will not rot.

**And the asymmetry Sweden's `financials` chose is right, which is why finding 1 is a prose defect and not
a code one.** A present block with `periods: []` for a company that files on paper would mean *Bolagsverket
holds no figures for this company* and *we could not look* at once — D-011's collapse. Returning nothing,
plus a note that names the channel, keeps them apart. The code got this right, `tasks/T55.md` argued it
before the code was written, and five sentences written around it say the opposite. That is a much better
failure than the reverse.

**On T57.** The board said "nine `_VERIFY` fixtures"; T57 measured that eight had already been relabelled
and that the real number was four untried identifiers. It then found that one of them (`5560986878`) is a
genuine single-procedure bankruptcy, replaced an assembled fixture with a live recording, and — this is
the part worth copying — left `bv_ab_avregistrerad.json` **synthetic**, with the reason written down,
because the real deregistered company had the wrong status combination. Recording what the wire actually
said instead of the fixture you wanted is the whole discipline.

### Verdict

**APPROVED WITH FIXES.** The machinery is correct end to end: twelve country×attachment combinations answer
on both surfaces with REST ≡ MCP, every ruled invariant I could mutate held, the person-bearing line is
clean in code and in fixtures, and 1030 tests, mypy and ruff are green on a pristine export of `HEAD`.

One finding must land before `railway up` (finding 1, ~25 minutes, five files) plus one two-minute README
line (finding 6). Both are prose. Nothing in `src/` behaves wrongly.

### What I could not verify

* **No live K3 Swedish filing exists anywhere in this project's evidence.** `registries/se/ixbrl.py` is
  validated against filed K2 documents and against Bolagsverket's own K3 taxonomy *specimens*. The module
  and the block's `notes` both say so, which is the right disclosure — but the recon's own Fact 6 (a
  well-formed British fact that is wrong by twice its value with its sign inverted, corroborated by two
  other tagged facts) is the reason a specimen cannot stand in for a filing. I did not call Bolagsverket, so
  I confirmed the caveat is present and correctly worded; I could not confirm the parser is right on a real
  K3 document, and neither could T55.
* **The five Swedish iXBRL fixtures are hand-built**, not recordings. I verified they are internally
  consistent, carry the `FIXTURE NOTICE`, reproduce T55's done-check exactly and contain no personal data —
  but the extractor's agreement with them is agreement with figures a previous agent transcribed, not with a
  document Bolagsverket served. `tests/fixtures/README.md` states this plainly.
* **Whether the register ever emits `contains_fixed_charge: false`.** D-045(a) rests on 0 explicit `False`
  values across 110 committed items, and the mapper relays whatever the payload holds; a literal `false` on
  the wire would be relayed as `False` despite three field descriptions saying it must never be. I called no
  Companies House endpoint, so this stays where D-045(a) left it — an observation about 110 items, honestly
  labelled as one.
* **The deployed behaviour of any attachment.** I read only the five unlogged static routes (plus
  `/llms-full.txt`), so every statement above about how a block behaves is about `HEAD` on my machine.
  Production is `bf1f37f` and has none of it.
* **`packages/npm/*` and `mcpb/` beyond their version strings.** I checked the manifests carry 0.4.0; I did
  not build or install either.
