# PROGRESS

One line per task. Status: todo / doing / review / done. Only the orchestrator sets `done`.
Completed phases are rolled up to one line each; the full done-check trails live in git history (`git log --format=%B`) and `REVIEW.md`.

## Rolled-up phases

| Phase | Tasks | Status | Summary |
|---|---|---|---|
| 0 Board | T00 | done | 2026-09-03: skeleton, coordination files, tasks T01–T14. `NORBIZ_SPEC.md` was never delivered → written by T01. `BRREG_MCP_FIRST_KRONE.md` never delivered → `HUMAN_TODO.md` §8 placeholder. |
| 1 Interface | T01 | done | `src/registry_mcp/` layout (D-003), pydantic models (D-004), `Registry` ABC + registration (D-008), spec with 97-test list. Found: build plan orgnr `833286602` invalid → typo for `833285602` (Kim confirmed); primary fixture `923609016` (Equinor ASA). |
| 2 Parallel impl | T02–T05 | done | Rules engine 100% coverage (one review cycle: D-009 fixed tax-return leak to public bodies/unknown forms). brreg client + cache, 3 live-verified fixtures, deleted entities return 200 not 410. CI/Docker/Caddy/deploy.md. llms.txt (39 lines), llms-full.txt, homepage JSON-LD, `server.json` valid against registry schema 2025-12-11. |
| 3 Surfaces | T06–T09 | done | REST (country-scoped routes, D-007 envelope, rate limit, static discovery routes). MCP (FastMCP 4.0.2, 5 tools, rules resource, prompt, Streamable HTTP at `/mcp` and `/mcp/` with no redirect, stdio `registry-mcp`). D-010 `DeadlineReport`/`ValidationResult` and D-012 `CountriesResponse` shared by both surfaces with parity tests. Logging (never raises) + `/v1/stats` + dashboard + UA classifier. |

## Phase 4 — Review, publish, launch

| id | owner | status | done-check | blocker |
|---|---|---|---|---|
| T10 | Opus A | done | 2026-09-04: 10-point checklist 8 PASS / 2 FAIL → B2 (`aclose`) and B3 (lifespan `finally`) fixed at 79b18bd / 7eba739; B1/B4 (flaky 429 test, `/mcp` 307) fixed at 7eba739; N1–N8 all applied. New decisions D-011 (employees invariant), D-012 (countries model), D-013 (validate reason), D-014 (`Registry.aclose`). | — (sign-off APPROVED, see REVIEW.md) |
| T11 | Opus B | done | `uvx --from dist/*.whl registry-mcp` → 5 tools; npm launcher → 5 tools (needs the PyPI package to exist — fails correctly pre-publish); alias `brreg-mcp` built; README/CONTRIBUTING/issue templates/seed issues/`legal/terms.md`/`glama.json`/Smithery card/`SUBMISSIONS.md`. | **npm `brreg-mcp` is taken** (hellosverre, 2026-04) → alias scoped `@foretak/brreg-mcp`; human decision in `HUMAN_TODO.md` §3 |
| T12 | Opus B | done | 4 articles × 3 versions, every JSON block real (`content/call.py`), devto ≤600 words (435/480/480/566). VAT article uses `833285602`. | — |
| T13 | Sonnet 4 | done | Image ships `static/` + `server.json`; compose up via Caddy on 8443 (rootless Docker can't bind 80/443 → `docker-compose.local.yml`); `/health`, company, llms.txt, server.json, `/`, `/status` all 200 over HTTPS; MCP 5 tools over HTTPS; cache survives restart (identical `fetched_at`). Found the `/mcp` 307 bug → fixed in T07's files. | — |
| T14 | Orchestrator | done | 2026-09-04 clean clone (`git clone . scratchpad/clean`): 273 passed, 1 deselected (live); mypy clean (45 files); ruff clean; wheel stdio → 5 tools; `docker build` ok; `docker compose config` ok with `.env.example`; secret grep empty. `HUMAN_TODO.md` §8 (FIRST_KRONE placeholder) + §9 (launch sequence) written. | **Feature work frozen.** Next agent task is not code: read the stats dashboard for two weeks (build plan §4.2). Human items: `HUMAN_TODO.md` §9 |

## Carry-overs for T15 (second country)
- Seven tests hard-code the country list and `test_unsupported_country` uses `SE` — the test suite, not `core/`, is what country #2 must edit (T10 note).
- `content/04-add-your-country` names Denmark (CVR) / Sweden (Bolagsverket) as first targets.
- npm launcher has no offline/dev fallback; it always resolves `registry-mcp` from PyPI.

## Phase 5 — Second country (started 2026-09-04, Kim: "go uk, full autonomy")

| id | owner | status | done-check | blocker |
|---|---|---|---|---|
| T15a | Opus A | review | 2026-09-04: `UK_SPEC.md` (16 sections, 109-test list); D-015 (`GB` strict, no `UK` alias), D-016 (UK deadline policy — CH-published dates authoritative, compute only from a sourced rule, no roll-forward, corporation tax documented not computed), D-017 (`Registry.requires_api_key`/`api_key_env` surfaced by `country_info()`, defaults leave NO/XX untouched). Key arrived mid-task → **16 live payloads saved to `tests/fixtures/ch_*.json`**, resolving all but 5 `VERIFY` markers and finding 8 places the published schema is wrong (§1.6). `uv run pytest -q -m "not live"` 273 passed / 1 deselected; mypy clean; ruff clean. | — |
| T15b | Sonnet | todo | — | Blocked on T15a review. `COMPANIES_HOUSE_API_KEY` received 2026-09-04 (secrets dir + Railway, verified live) — but **fixtures already exist**, so only tests 106–109 (`@pytest.mark.live`) need it |
| T15c | Opus B | todo | — | Blocked on T15b |
| T15d | Sonnet 4 | todo | — | Blocked on T15b, T15c |
| T15e | Opus A | todo | — | Blocked on T15b–d |
| T16 | — | todo | — | Denmark CVR: access application to be started by Kim (Erhvervsstyrelsen) |
