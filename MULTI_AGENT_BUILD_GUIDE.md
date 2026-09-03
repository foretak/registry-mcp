# registry-mcp — Multi-agent build guide

How to build the company-registry-for-agents service with a team of seven AI agents: one orchestrator (Claude Fable), two senior engineers (Claude Opus), four implementers (Claude Sonnet). Written so it can be pasted directly as the orchestrator's instructions.

Companion files, all in the repo root:
- `NORBIZ_SPEC.md` — technical spec of the Norwegian module (rename references to `brreg-mcp`)
- `BRREG_MCP_BUILD_PLAN.md` — the phased build plan with done-checks
- `BRREG_MCP_FIRST_KRONE.md` — go-to-market after launch

## Product framing (read before assigning anything)

- **Umbrella product: `registry-mcp`** — "company data for AI agents, any country." One tool shape, many national registries.
- **First module: `brreg-mcp`** — Norway (Brønnøysundregistrene). This is what ships first and what proves demand.
- Everything country-neutral lives in `core/`. Everything Norwegian lives in `registries/no/`. The second country must be addable without touching `core/`.

---

## Team

| Role | Model | Count | Owns |
|---|---|---|---|
| Orchestrator | Fable | 1 | Plan, task assignment, integration, final review, `PROGRESS.md` |
| Architect | Opus A | 1 | `core/` design, response schema, plugin interface for registries, code review of everything |
| Growth engineer | Opus B | 1 | Discoverability: packages, registries, manifests, docs, content, stats |
| Implementer 1 | Sonnet | 1 | `core/rules` + tests |
| Implementer 2 | Sonnet | 1 | `registries/no/` (brreg client, cache, mapping) |
| Implementer 3 | Sonnet | 1 | HTTP API + MCP server + logging |
| Implementer 4 | Sonnet | 1 | Docker, CI, deploy, status page, stats dashboard |

Rule of thumb: Opus decides shapes and reviews; Sonnet writes code inside shapes that already exist; Fable never writes production code, only integrates and judges.

## How agents communicate

All coordination goes through files in the repo, never through memory of previous sessions:

- `PROGRESS.md` — one line per task: id, owner, status (todo / doing / review / done), done-check result, blocker. Only the orchestrator changes status to done.
- `DECISIONS.md` — architect appends every interface or schema decision with a date and a one-line reason. Implementers read it before starting.
- `tasks/<id>.md` — one file per task written by the orchestrator: goal, files to touch, files not to touch, done-check, which `DECISIONS.md` entries apply.
- `REVIEW.md` — architect's review notes per task; an implementer's task goes back to doing if there's a blocking note.

Every agent session starts with: "Read `PROGRESS.md`, `DECISIONS.md`, and your task file. Do only your task. Run its done-check. Update `PROGRESS.md` to review. Stop."

---

## Step-by-step

### Step 1 — Orchestrator (Fable) sets up the board
1. Read the three companion files fully.
2. Create the repo skeleton: `core/`, `registries/no/`, `api/`, `mcp/`, `tests/`, `tasks/`, `content/`, `legal/`, plus the four coordination files above.
3. Write `tasks/T01.md` through `tasks/T14.md` from the list below.
4. Assign T01 to Opus A and nothing else yet. Everything depends on the interface.

### Step 2 — Opus A: the interface (T01)
Design and write, with docstrings but minimal implementation:
- `core/models.py` — `CompanyReport`, `Deadline`, `SearchHit`, `RegistryError`. Country-neutral. Fields from `NORBIZ_SPEC.md` plus `country: str` (ISO-2) and `registry: str`.
- `core/registry.py` — abstract `Registry` class: `lookup(id)`, `search(name)`, `validate_id(id)`, `deadlines(report, today)`. A registry module is a class implementing this, registered by country code.
- `core/rules/` — package layout: `common.py` (weekend roll-forward, next-occurrence helpers) and per-country rule modules imported by the registry.
- `DECISIONS.md` entries for: response schema, confidence scale, cache policy, error format, how a second country plugs in.
Done-check: `mypy` clean; a stub `registries/xx/` example shows a second country can be added in one folder; orchestrator and Opus B both confirm they can build on it.

### Step 3 — Orchestrator releases parallel work
Once T01 is done, assign at the same time:
- T02 → Sonnet 1: `core/rules/common.py` + `registries/no/rules.py` (MOD11, org forms, status, Norwegian deadlines) + full tests per spec.
- T03 → Sonnet 2: `registries/no/client.py` (brreg HTTP client, cache, field mapping). Must fetch live JSON for org.nr 833286602 and verify field names.
- T04 → Sonnet 4: CI (ruff, mypy, pytest on push), Dockerfile, `docker-compose.yml`, Caddy config, `deploy.md`.
- T05 → Opus B: `llms.txt`, `llms-full.txt`, `server.json` manifest for the official MCP registry (check the current schema live), homepage HTML with JSON-LD, the naming/alias keyword list applied everywhere.
Sonnet 3 waits — the API needs T02 and T03.

### Step 4 — Opus A reviews T02 and T03
Blocking criteria: any Norwegian logic leaked into `core/`; any field guessed rather than verified; tests missing from the spec list. Write notes in `REVIEW.md`. Orchestrator marks done only after Opus A's sign-off.

### Step 5 — Sonnet 3 builds the surfaces (T06, T07)
- T06: `api/main.py` — REST endpoints per spec, but routes are `/v1/{country}/company/{id}`, `/v1/{country}/search`, `/v1/{country}/company/{id}/deadlines`, `/v1/{country}/validate/{id}`, plus `/v1/countries`. Rate limit, error hints, OpenAPI descriptions written for LLM readers.
- T07: `mcp/server.py` — FastMCP tools `lookup_company(id, country="NO")`, `search_company(name, country="NO")`, `company_deadlines(id, country, today)`, `validate_company_id(id, country)`, `list_countries()`. Resource `registry://rules/{country}`. Prompt `explain_company`. Streamable HTTP at `/mcp`; stdio entry `python -m registry_mcp`. Tool docstrings include the alias keywords from the build plan.
Done-check: `claude mcp add registry-mcp --transport http http://localhost:8080/mcp` and a successful `lookup_company("833286602")`.

### Step 6 — Sonnet 3 continues: logging and stats (T08)
`core/log.py` writing every REST and MCP call to SQLite; `/v1/stats?key=`. Then Sonnet 4 builds the stats dashboard page (T09): daily calls, MCP vs REST, unique agents, user-agent classifier.

### Step 7 — Opus A: integration review (T10)
Full read of the codebase. Checklist: schema identical across REST and MCP; a `registries/se/` stub can be added without editing `core/` or `api/`; tests green; no secrets in repo; error hints actually tell an agent what to do next. Fix list to `REVIEW.md`; orchestrator reassigns fixes to the original Sonnet.

### Step 8 — Opus B: publish (T11)
- Package names: PyPI and npm `registry-mcp`, with `brreg-mcp` published as an alias package that depends on it (so both keywords hit).
- `uvx registry-mcp` and `npx registry-mcp` must start stdio servers.
- Submit to: official MCP registry, Smithery, Glama, PulseMCP, mcp.so, MCP Market. Prepare awesome-mcp-servers PRs. Write `SUBMISSIONS.md` with what needs a human login.
- GitHub topics, README top section, badges, three seeded good-first-issues.

### Step 9 — Opus B: content (T12)
Three worked-example articles per the build plan, plus a fourth: "Adding your country's registry to registry-mcp in an afternoon" — this one recruits contributors who build the modules you'd otherwise pay for.

### Step 10 — Sonnet 4: deploy (T13)
Bring it up on the VPS following its own `deploy.md`; fix the doc where reality differs. Status page live.

### Step 11 — Orchestrator: launch review and handoff to human (T14)
- Run every done-check in `PROGRESS.md` again from a clean machine.
- Produce `HUMAN_TODO.md`: domain DNS, registry logins, package-index accounts, posting the articles, the outreach list from `BRREG_MCP_FIRST_KRONE.md`.
- Freeze feature work. The next agent task is not code; it's reading the stats page for two weeks.

### Step 12 — Second country (only after the decision gate in the build plan)
Orchestrator writes `tasks/T15.md`: Sweden (Bolagsverket) or Denmark (CVR — its API is open and well documented, probably the easier first expansion). Same split: Opus A reviews the module, one Sonnet builds it, Opus B updates packages and manifests, Sonnet 4 deploys. Target: two weeks per country. If it takes longer, the core abstraction is wrong and Opus A fixes that before a third country.

---

## Orchestrator rules

- Never let two agents edit the same file in the same round. Task files list owned paths.
- A task is done when its done-check passes on a clean checkout, not when the agent says it's done.
- If an implementer reports a blocker twice, escalate to Opus A rather than reassigning to another Sonnet.
- Keep `PROGRESS.md` under 100 lines; roll completed tasks into a one-line summary per phase.
- Report to the human once per phase, in five lines: what's done, what's blocked, what needs a login or a decision, what's next.

## Budget guide

Rough token-cost split if this runs in Claude Code with subagents: Sonnet does 70% of the tokens, Opus 25%, Fable 5%. Expect most of the cost in Steps 3–7; Steps 8–9 are cheap. If cost matters, run Sonnet 1 and Sonnet 4 as the same session — their tasks never overlap in time.
