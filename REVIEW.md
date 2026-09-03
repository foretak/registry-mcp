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

Timing note: `src/registry_mcp/api/` was being written by Sonnet 3 (T06) during this review and was not read or touched. By the end of the review `ruff check .` reports one finding there (`RUF022`, `api/ratelimit.py:28`, `__all__` not sorted, auto-fixable) — it belongs to T06 and is not a T02/T03 finding; both of those tasks' own files are ruff-clean.
