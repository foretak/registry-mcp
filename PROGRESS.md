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
| T02 | Sonnet 1 | doing | — | — |
| T03 | Sonnet 2 | doing | — | — |
| T04 | Sonnet 4 | doing | — | — |
| T05 | Opus B | doing | — | — |

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
