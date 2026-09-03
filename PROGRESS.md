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
| T02 | Sonnet 1 | review | 2026-09-03: `uv run pytest tests/test_rules_common.py tests/test_rules_no.py --cov=registry_mcp.core.rules --cov=registry_mcp.registries.no.rules --cov-report=term-missing -q` → 84 tests pass, 100% coverage on both `core/rules/common.py` and `registries/no/rules.py` (225/225 stmts). `uv run mypy .` clean (21 files), `uv run ruff check .` on my files clean (2 pre-existing RUF100 findings in `core/cache.py`, not owned by T02). | `tests/test_interface.py::test_norwegian_methods_raise_not_implemented` now fails (not my file) — it asserted `validate_id` raises `not_implemented`, which is no longer true now that T02 implemented it; needs updating by whoever owns that file. Also added `deadlines = deadlines_for` alias and a `rules_markdown()` function in `registries/no/rules.py` beyond the T02.md spec, because `registries/no/__init__.py` (edited concurrently, not owned by T02) already calls `rules.deadlines(...)` and `rules.rules_markdown()` — needed for `mypy .` to stay clean repo-wide. |
| T03 | Sonnet 2 | doing | — | — |
| T04 | Sonnet 4 | review | 2026-09-03: `docker build -t registry-mcp:dev .` succeeds (legacy builder, no BuildKit/buildx available in this env — Dockerfile avoids `--mount=type=cache`); `docker compose config` valid. Runtime verification deferred to T13 (API module doesn't exist yet) | — |
| T05 | Opus B | review | 2026-09-03: `check-jsonschema --schemafile https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json server.json` → `ok -- validation done`. `wc -l static/llms.txt` → 39 (≤40). `static/index.html` JSON-LD `WebAPI` block parses (1 block, 16 keys). Also written: `static/llms-full.txt`, `KEYWORDS.md`, `HUMAN_TODO.md`, `NORBIZ_SPEC.md` §15 "Serving static files" | Placeholders `foretak` / `api.foretak.dev` throughout — see `HUMAN_TODO.md` §1. `README.md` still says `api.example.dev` (T11 owns it). `legal/terms.md` does not exist but the homepage JSON-LD `termsOfService` points at it |

## Phase 3 — Surfaces

| id | owner | status | done-check | blocker |
|---|---|---|---|---|
| T06 | Sonnet 3 | todo | — | Blocked on T02, T03 |
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
