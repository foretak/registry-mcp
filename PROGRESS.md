# PROGRESS

One line per task. Status: todo / doing / review / done. Only the orchestrator sets `done`.
Format: `| id | owner | status | done-check result | blocker |`

## Phase 0 — Board setup

| id | owner | status | done-check | blocker |
|---|---|---|---|---|
| T00 | Orchestrator | done | 2026-09-03: skeleton, coordination files, tasks/T01–T14 written | `NORBIZ_SPEC.md` never delivered → T01 now includes writing it. `BRREG_MCP_FIRST_KRONE.md` missing → T14 leaves a placeholder |

## Phase 1 — Interface

| id | owner | status | done-check | blocker |
|---|---|---|---|---|
| T01 | Opus A | done | 2026-09-03: `uv sync --all-extras && uv run mypy . && uv run ruff check . && uv run pytest -q` → mypy clean (14 files), ruff clean, 12 tests pass. `list_countries()` → `['NO']`; `list_countries(include_stubs=True)` → `['NO','XX']`. `NORBIZ_SPEC.md` written (97 numbered tests); D-003…D-008 appended | Build plan's canonical org.nr `833286602` is **not valid** — fails MOD11 and 404s on the live API. Use `923609016` (Equinor ASA). Every done-check naming `833286602` needs correcting. Layout moved to `src/registry_mcp/` — see D-003 path note before assigning T02–T13 |

## Phase 2 — Parallel implementation

| id | owner | status | done-check | blocker |
|---|---|---|---|---|
| T02 | Sonnet 1 | doing | 2026-09-03: `uv run pytest tests/test_rules_common.py tests/test_rules_no.py --cov=registry_mcp.core.rules --cov=registry_mcp.registries.no.rules --cov-report=term-missing -q` → 84 tests pass, 100% coverage on both `core/rules/common.py` and `registries/no/rules.py` (225/225 stmts). `uv run mypy .` clean (21 files), `uv run ruff check .` on my files clean (2 pre-existing RUF100 findings in `core/cache.py`, not owned by T02). | `tests/test_interface.py::test_norwegian_methods_raise_not_implemented` now fails (not my file) — it asserted `validate_id` raises `not_implemented`, which is no longer true now that T02 implemented it; needs updating by whoever owns that file. Also added `deadlines = deadlines_for` alias and a `rules_markdown()` function in `registries/no/rules.py` beyond the T02.md spec, because `registries/no/__init__.py` (edited concurrently, not owned by T02) already calls `rules.deadlines(...)` and `rules.rules_markdown()` — needed for `mypy .` to stay clean repo-wide. **Opus A review 2026-09-03: BLOCKED** — see `REVIEW.md` §T02 B1/B2 and new `DECISIONS.md` D-009: `deadlines_for` emits `tax_return` for unclassified and public-sector legal forms (`registries/no/rules.py:641`), contradicting `NORBIZ_SPEC.md` §7 line 330. Everything else approved, incl. 100 % coverage reproduced. The stale `tests/test_interface.py` failure is fixed by Opus A (that file is T01's). |
| T03 | Sonnet 2 | done | 2026-09-03: `uv run python scripts/lookup_demo.py 923609016` (run 1) → live `CompanyReport` JSON, `cached: false`; run 2 → identical report, `cached: true`, same `fetched_at`. `uv run pytest tests/test_client_no.py tests/test_cache.py -q` → 32 passed (incl. 1 live-marked). `uv run mypy .` clean (23 files), `uv run ruff check .` clean repo-wide. No field names needed correcting — every §2 field verified against the live 923609016/974760673 fixtures (test 97). `registries/no/rules.py` (T02) landed mid-task; switched from mocked rules to the real `validate_orgnr` / `legal_form_info` / `derive_status` / `deadlines_for`-as-`deadlines` / `rules_markdown` before finishing. | **410-Gone VERIFY resolved, and it was wrong**: live deleted entities (found via `/oppdateringer/enheter?...&dato=...`, filtering `endringstype=="Sletting"`, e.g. `921084846`) answer **200** with a normal body carrying `slettedato` + `respons_klasse:"SlettetEnhet"`, never `410` — handled entirely by ordinary status derivation, no special-casing needed. `NORBIZ_SPEC.md` §1.1/§2/§6 updated with the finding; defensive `410→not_found` mapping kept in `client.py` for unconfirmed old/purged records. Pre-existing `tests/test_interface.py::test_norwegian_methods_raise_not_implemented` now fails (not my file, not touched) — same finding T02 already flagged: `validate_id`/`deadlines` no longer raise `not_implemented` now that both T02 and T03 are wired up; needs updating by whoever owns that file. **Opus A review 2026-09-03: APPROVED** — see `REVIEW.md` §T03. No field guessed (every §2 name re-checked against both committed fixtures), D-004…D-007 all hold, spec tests 82–97 all present. Non-blocking follow-ups only: three untested D-005 confidence anchors, untested cached-`not_found` / search-cache-hit / 429 paths, `test_97`'s tautological second half, raw `httpx.ConnectError` escaping `lookup`. |
| T04 | Sonnet 4 | done | 2026-09-03: `docker build -t registry-mcp:dev .` succeeds (legacy builder, no BuildKit/buildx available in this env — Dockerfile avoids `--mount=type=cache`); `docker compose config` valid. Runtime verification deferred to T13 (API module doesn't exist yet) | — |
| T05 | Opus B | done | 2026-09-03: `check-jsonschema --schemafile https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json server.json` → `ok -- validation done`. `wc -l static/llms.txt` → 39 (≤40). `static/index.html` JSON-LD `WebAPI` block parses (1 block, 16 keys). Also written: `static/llms-full.txt`, `KEYWORDS.md`, `HUMAN_TODO.md`, `NORBIZ_SPEC.md` §15 "Serving static files" | Placeholders `foretak` / `api.foretak.dev` throughout — see `HUMAN_TODO.md` §1. `README.md` still says `api.example.dev` (T11 owns it). `legal/terms.md` does not exist but the homepage JSON-LD `termsOfService` points at it |

## Phase 3 — Surfaces

| id | owner | status | done-check | blocker |
|---|---|---|---|---|
| T06 | Sonnet 3 | doing | — | started in parallel with Opus A review of T02/T03 |
| T07 | Sonnet 3 | todo | — | Blocked on T06 |
| T08 | Sonnet 3 | todo | — | Blocked on T07 |
| T09 | Sonnet 4 | todo | — | Blocked on T08 |
| T10 | Opus A | todo | — | Blocked on T06–T09 |

## Phase 4 — Publish and launch

| id | owner | status | done-check | blocker |
|---|---|---|---|---|
| T11 | Opus B | todo | — | Blocked on T10 |
| T12 | Opus B | todo | — | Blocked on T10 |
| T13 | Sonnet 4 | todo | — | Blocked on T10 |
| T14 | Orchestrator | todo | — | Blocked on T11–T13 |
