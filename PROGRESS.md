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
| T01 | Opus A | doing | — | — |

## Phase 2 — Parallel implementation

| id | owner | status | done-check | blocker |
|---|---|---|---|---|
| T02 | Sonnet 1 | todo | — | Blocked on T01 |
| T03 | Sonnet 2 | todo | — | Blocked on T01 |
| T04 | Sonnet 4 | todo | — | Blocked on T01 |
| T05 | Opus B | todo | — | Blocked on T01 |

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
