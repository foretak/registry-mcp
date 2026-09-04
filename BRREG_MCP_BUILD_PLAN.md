# brreg-mcp — Build plan, zero to launch

A step-by-step plan for building a Norwegian business-data service that AI agents discover and call on their own. Each step has an owner (HUMAN = Kim, AGENT = a coding agent such as Claude Code, Codex, Cursor), a deliverable, and a done-check. Feed steps to agents one phase at a time; don't paste the whole file into a single session.

Companion document: `NORBIZ_SPEC.md` (technical spec for the service itself). Where this plan says "per spec", the agent should open that file.

> Note (orchestrator, 2026-09-04): org.nr `833286602` used below is a typo for **`833285602`** (EL ANSARI KONSULT, ENK, Oslo — confirmed by Kim). The mistyped number fails MOD11 and 404s, and is kept as the negative test case. Task done-checks use `923609016` (Equinor ASA) as the primary fixture because its payload exercises more fields; `833285602` is the third verified fixture and the example in the VAT-check article.
>
> Note (orchestrator, 2026-09-03): this plan predates the `registry-mcp` umbrella framing in `MULTI_AGENT_BUILD_GUIDE.md`. Where the two disagree on layout or route shapes (e.g. `/v1/{country}/company/{id}` vs `/v1/company/{id}`), the multi-agent guide and `DECISIONS.md` win. The done-checks and discoverability steps here remain authoritative.

---

## 0. Name

Agents find tools by keyword match against package names, repo names, and tool descriptions. A clever brand name is invisible to them; a descriptive name is found. So the product has two names:

- **Technical name (what agents see everywhere): `brreg-mcp`**
  Contains "brreg" (the term every agent generates when it needs Norwegian company data) and "mcp" (the protocol clients search for). Aliases used in descriptions and tags: `brønnøysund`, `enhetsregisteret`, `organisasjonsnummer`, `orgnr`, `norway company lookup`, `norwegian business registry`.
- **Brand name (domain, company, later products): `Foretak`** — Norwegian for "enterprise". Short, ownable, and it is itself a keyword agents generate in Norwegian queries. Domain candidates: `foretak.dev`, `foretak.ai`, `foretak.io`. HUMAN checks availability before Step 2.

Fallbacks if the brand domain is taken: `Orgnr` (orgnr.dev), `Enhet` (enhet.dev). Do not change the technical name; `brreg-mcp` stays regardless of brand.

Tool names inside the MCP server use the same logic: `lookup_company`, `search_company`, `company_deadlines`, `validate_orgnr`. Plain, verb-first, English.

---

## Phase 1 — Foundations (Days 1–3)

**1.1 HUMAN — Register the identifiers**
- Domain for the brand (see Step 0)
- GitHub organisation: `foretak` (or brand fallback); repo: `foretak/brreg-mcp`
- PyPI name `brreg-mcp` and npm name `brreg-mcp` (reserve with an empty 0.0.1 if needed)
- A contact email that goes to a real inbox: `hello@<domain>`
- A Hetzner (Helsinki) or Norwegian VPS account, smallest instance
Done when: all names are owned and written into a `NAMES.md` file in the repo.

**1.2 AGENT — Scaffold the repo**
- Python 3.12 project with `uv` or `pip`, `pyproject.toml`, MIT licence, `.gitignore`, `README.md` stub
- Layout exactly as in `NORBIZ_SPEC.md`, but package name `brreg_mcp` and repo name `brreg-mcp`
- Pre-commit with ruff + mypy; GitHub Actions running tests on push
Done when: `pytest` runs (zero tests is fine) and CI is green.

**1.3 AGENT — Rules engine first**
- Implement `rules.py` per spec: MOD11 validation, org-form mapping, status logic, deadline calculation with `today` as a parameter, weekend roll-forward
- Full unit tests per the spec's test list
Done when: all rules tests pass and a coverage report shows `rules.py` at 100%.

---

## Phase 2 — The service (Days 4–8)

**2.1 AGENT — Brønnøysund client**
- `brreg.py` per spec: lookup, search, roles, sub-units; 5s timeout, one retry, descriptive User-Agent, 404 handling
- SQLite cache with 24h TTL
- Fetch the live JSON for org.nr `833286602` and check every field name against reality before finalising the mapping
Done when: a script prints a CompanyReport for 833286602 from the live API, and a second run reports `cached: true`.

**2.2 AGENT — REST API**
- `main.py` per spec: the five endpoints, JSON error format with `hint`, rate limit 60/min per IP, `/` serves `llms.txt`
- OpenAPI descriptions written for an LLM reader: each endpoint says what it's for, when to use it, and what to do on failure
Done when: `curl localhost:8080/v1/company/833286602` returns a valid report and `/openapi.json` validates.

**2.3 AGENT — MCP server**
- `mcp_server.py` with FastMCP: four tools, `brreg://rules` resource, `explain_company` prompt
- Tool docstrings must include the alias keywords from Step 0 naturally ("Look up a Norwegian company in Brønnøysundregistrene / Enhetsregisteret by organisasjonsnummer (orgnr)…")
- Streamable HTTP mounted at `/mcp`; stdio entry point `python -m brreg_mcp`
Done when: `claude mcp add brreg-mcp --transport http http://localhost:8080/mcp` works and Claude Code can call `lookup_company` successfully.

**2.4 AGENT — Usage logging and stats**
- `log.py` per spec; `/v1/stats?key=ADMIN_KEY`
- Log both REST and MCP calls through one function
Done when: after ten test calls, `/v1/stats` shows 10 calls, correct top queries, and at least one distinct user agent.

**2.5 AGENT — Docker and deploy files**
- Multi-stage Dockerfile, `docker-compose.yml` with a volume for the SQLite file, Caddy reverse proxy config for automatic HTTPS
- `deploy.md`: exact commands to bring it up on a fresh Ubuntu VPS
Done when: `docker compose up` on a clean machine serves `/health` over HTTPS.

**2.6 HUMAN — Deploy**
- Follow `deploy.md` on the VPS, point `api.<domain>` at it
- Set `NORBIZ_CONTACT_EMAIL`, `NORBIZ_ADMIN_KEY`
Done when: `https://api.<domain>/v1/company/833286602` returns a report from your phone.

---

## Phase 3 — Discoverability (Days 9–12) — this is the part most people skip

**3.1 AGENT — Machine-readable presence**
- `llms.txt` (under 40 lines) and `llms-full.txt` (complete endpoint docs) served at the domain root
- `mcp.json` / `server.json` manifest in the format the official MCP registry requires (check current schema at registry.modelcontextprotocol.io before writing)
- Homepage: single static page with a JSON-LD `WebAPI` block, the curl example, the MCP add command, and a link to GitHub. No marketing copy above the code example.
Done when: all three URLs return 200 and the manifest validates against the registry schema.

**3.2 AGENT — Publish packages**
- Publish `brreg-mcp` to PyPI (the stdio server as a console script: `brreg-mcp`)
- Publish `brreg-mcp` to npm as a thin wrapper that runs the Python package, or a small TypeScript port of the four tools — either way `npx brreg-mcp` must start a stdio server
- Both package descriptions contain the alias keywords; both READMEs include the Claude Code / Cursor / Claude Desktop config snippets
Done when: `uvx brreg-mcp` and `npx brreg-mcp` both start a working stdio server on a clean machine.

**3.3 AGENT — Registry submissions**
Submit to, in this order: official MCP registry, Smithery, Glama, PulseMCP, mcp.so, MCP Market. For each, produce the submission files/PRs and a checklist of anything that needs a human login.
Done when: `SUBMISSIONS.md` lists every registry with status and URL.

**3.4 HUMAN — Complete submissions**
Log in and finish whatever the agent couldn't. Approve the awesome-list PRs it prepared (awesome-mcp-servers and at least two others).
Done when: brreg-mcp appears in search on the official registry and Smithery.

**3.5 AGENT — GitHub hygiene**
- Repo topics: `mcp`, `mcp-server`, `model-context-protocol`, `norway`, `brreg`, `enhetsregisteret`, `ai-agents`, `company-data`
- README top section: one sentence, the add-to-Claude-Code command, a 10-line example output. Badges for PyPI, npm, CI.
- `CONTRIBUTING.md`, issue templates, a `good first issue` label with three seeded issues
Done when: README renders correctly and the repo is public.

**3.6 AGENT — Worked examples**
Write three short articles, each showing an agent solving a real task with brreg-mcp:
- "Check if a Norwegian supplier is VAT-registered before paying an invoice"
- "Find every filing deadline for a Norwegian AS this quarter"
- "Validate and enrich a list of org.nrs in a spreadsheet"
Each under 600 words, with the exact prompt and the tool output. Format for dev.to, with a shorter version for Reddit r/mcp and a Norwegian version for kode24 / Norwegian dev communities.
Done when: three markdown files exist in `content/`.

**3.7 HUMAN — Post them**
Publish over one week, not all at once.

---

## Phase 4 — Measure (Days 13–45)

**4.1 AGENT — Stats dashboard**
Small script or page: daily calls, unique user agents, MCP vs REST split, top 20 queries, and a classifier that tags user agents as "coding agent", "browser", "script", "unknown".
Done when: Kim can open one URL each morning and see whether agents came.

**4.2 HUMAN — Watch and reach out**
- Do nothing else for two weeks. No feature work.
- Any client with more than 100 calls: find them (user agent, api key, GitHub issues) and ask what they'd pay for.
- Log every inbound question in `FEEDBACK.md`.

**4.3 Decision gate (Day 45)**
Numbers to look at: unique agent clients, calls/day trend, inbound messages.
- Traffic growing and someone asked for more → Phase 5.
- Flat → change the endpoint (add the most-asked-for lookup), rerun Phase 3.6–3.7, wait another two weeks.
- Zero → the discovery layer failed, not the idea; audit each Phase 3 item against a real agent search before concluding anything.

---

## Phase 5 — Toward revenue (Month 2–3)

**5.1 AGENT — Add the second and third lookups** from `FEEDBACK.md` (likely: roles/board, sub-units, Regnskapsregisteret key figures, or Skatteetaten MVA register status).

**5.2 AGENT — API keys and plans**
Key issuance, per-key rate limits, a free tier and one paid tier, Stripe checkout. Keep MCP stdio free forever; charge for hosted volume.

**5.3 HUMAN — First paying customer**
One Norwegian accounting/SaaS company at 10–30k NOK/month in exchange for roadmap input.

**5.4 HUMAN — Start the Altinn system-provider application.** Slow; start early.

---

## Feeding this to agents

- Give an agent one phase at a time, with `NORBIZ_SPEC.md` and this file open.
- Start every session with: "Read BRREG_MCP_BUILD_PLAN.md. We are on step X. Do only that step, run its done-check, and stop."
- Keep a `PROGRESS.md` the agent updates after each step: step number, date, done-check result, anything it couldn't do.
- Different agents can take different phases (e.g. one builds Phase 2, another does Phase 3 packaging). The done-checks are what keep them consistent.
