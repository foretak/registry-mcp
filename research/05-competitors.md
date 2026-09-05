# 05 — Competitors

Who else puts company-registry data in front of AI agents or developers, how good they are, and what they charge. All research conducted **2026-09-05**; every figure below traces to a primary read recorded in one of the twelve topic files in this folder.

## Files

| File | Subject |
|---|---|
| `01-norwegian-brreg-mcp-servers.md` | census of all 14 working brreg MCP servers |
| `02-uk-companies-house-mcp-servers.md` | 19 Companies House servers; the 60k-use incumbent |
| `03-other-national-register-mcp-servers.md` | CVR, Bolagsverket, KVK, Handelsregister, Zefix + who owns which country |
| `04-multi-country-and-gleif-mcp-servers.md` | OpenRegistry, Entyrix, CompanyLens, ENTIA, GLEIF — the real peer group |
| `05-apier-the-closest-competitor.md` | deep dive on the only rival that computes Norwegian deadlines |
| `06-gateway-aggregators.md` | Pipeworx and Nordic Data; the connection-slot threat |
| `07-commercial-kyb-apis-global.md` | OpenCorporates, kompany, Middesk, Trulioo, Persona, Creditsafe, D&B |
| `08-norwegian-commercial-data-vendors.md` | Proff, Enin, Bizzy, Firmaradar, Apier prices |
| `09-registers-as-competitors.md` | Companies House, brreg, Erhvervsstyrelsen, GLEIF |
| `10-traction-and-usage-signals.md` | npm, PyPI and Smithery numbers, honestly read |
| `11-ai-native-entrants.md` | the "for AI agents" positioning field and its funding (none) |
| `12-feature-matrix.md` | **the full matrix** — every product, twelve columns |

## Condensed matrix

Full version with all 40+ products in `12-feature-matrix.md`. `Reg.` = listed in the official MCP registry.

| Product | Countries | Lookup | Search | ID valid. | Deadlines | VAT | UBO | Hosted | stdio | Reg. | Licence | Price |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **registry-mcp** | 2 | ✔ | ✔ | **✔** | **✔** | ✔ | ✖ | ✔ anon | ✔ | ✔ | MIT | **free** |
| Apier | 1 (NO) | ✔ | ✔ | ✖ | **✔** | ~ | ✖ | ✔ keyed | ✔ | ✖ | closed backend | free beta → NOK 0–9,999/mo + 0.50 kr/call |
| OpenRegistry | 29–30 | ✔ | ✔ | ✖ | ✖ | ✖ | ✔ | ✔ keyed | ✔ | ✖ | Apache-2.0 | $0 / $29 / $99 per month |
| Entyrix | 23 | ✔ | ✔ | ~ | ✖ | ✖ | ✔ | ✖ | ✔ | ✖ | MIT | €0, 50k req/mo |
| CompanyLens | 19 | ✔ | ✔ | ✖ | ✖ | ✖ | ✔ | ✔ OAuth | ✖ | ✖ | proprietary | £20/mo; £49/mo agent tier |
| ENTIA | 10 | ✔ | ✔ | ✖ | ✖ | ✔ | ✔ | ✔ **anon** | ✖ | ✖ | proprietary | free 100/mo |
| bouch/uk-due-diligence | 1 (GB, 5 registers) | ✔ | ✔ | ✖ | ~ | ✔ | ✔ | ✔ | ✔ | ✖ | MIT | free |
| stefanoamorelli/companies-house | 1 (GB) | ✔ | ✔ | ✖ | ~ | ✖ | ✔ | ✖ | ✔ | ✖ | **AGPL-3.0** | free |
| nordio-ai/brreg-mcp-server | 1 (NO) | ✔ | ✔ | ✖ | ✖ | ✔ | ~ | ✖ | ✔ | ✖ | MIT | free |
| hellosverre/brreg-mcp | 1 (NO) | ✔ | ✔ | ✖ | ✖ | ✔ | ~ | ✖ | ✔ | ✔ | MIT | free |
| Firmaradar | 1 (NO) | ✔ | ✔ | ✖ | ✖ | ✖ | ✔ | ✖ | ✔ | ✖ | Apache-2.0 shim | 99 kr/mo + **0.08 kr/lookup** |
| **Companies House** | 1 | ✔ | ✔ | ✖ | ✔ | ✖ | ✔ | **✖** | ✖ | ✖ | Crown | **free**, 600 req/5 min |
| **Brønnøysundregistrene** | 1 | ✔ | ✔ | ✖ | ✖ | ✔ | ✔ | **✖** | ✖ | ✖ | NLOD 2.0 | **free**, no registration |
| OpenCorporates | 140 | ✔ | ✔ | ✖ | ✖ | ✖ | ~ | **✖** | ✖ | ✖ | proprietary | **£225–£1,200/mo** (500–5,000 calls) |
| Trulioo | global | ✔ | ✔ | ✖ | ✖ | ✔ | ✔ | ✔ **dormant** | ✔ | ✖ | Apache-2.0 | not published |
| Middesk / Creditsafe / D&B / kompany / Proff | 1–200 | ✔ | ✔ | ~ | ✖ | ✔ | ✔ | **✖** | ✖ | ✖ | proprietary | **not published** |
| Enin | 3 (NO/SE/DK) | ✔ | ✔ | ✖ | ✖ | ✔ | ✔ | **✖** | ✖ | ✖ | proprietary | **1,295 NOK/user/mo** |

## Key findings

**1. The Norwegian lane is crowded by count and empty by quality.** Fifteen brreg MCP repositories exist; thirteen have working code, two are empty placeholders. The star leader, `reidar80/BRREG-MCP`, has **8 stars and has not been touched since 2025-08-28**. The best-engineered, `nordio-ai/brreg-mcp-server` (6,819 LOC, scorecard, tests, Dependabot), has **0 stars**. One has no licence at all (`daveHylde`); one names all five of its tools in Norwegian (`hent_foretak`, `sok_foretak` — a real agent-discoverability handicap). **Only two of the thirteen are in the official MCP registry.**

**2. No open-source brreg server computes a filing deadline.** Verified by grepping twelve of the thirteen working repos for `deadline|innleveringsfrist|forfallsdato|due_date|dueDate`: zero hits in every brreg-only server. Eight of twelve pass `registrertIMvaregisteret` straight through; none constructs the `NO…MVA` number and none distinguishes "the register says no" from "this register does not publish it."

**3. Apier is the exception, and it is three days old in the repo.** `PowerLaunch/apier-mcp` (last push **2026-09-02**) ships 26 tools including `get_company_deadlines`, `get_public_deadlines` and `get_company_obligations` — the last returning "every applicable regulatory obligation with its current state **and the legal reference it derives from**", from a versioned Rulebook computed in Oslo time. It also ships delegated write authority (`request_fullmakt` / `check_fullmakt` / `revoke_fullmakt`) that nobody else attempts. Planned pricing: NOK 0 / 499 / 1,999 / 9,999 per month plus **"Prepaid credits — 50 øre / call"**; free during beta. Norway only, key required, closed backend, not in the official MCP registry.

**4. Anonymous access predicts usage; feature breadth does not.** Live `initialize` probes on 2026-09-05 against Smithery usage counts: ENTIA answers anonymously (HTTP 200) — useCount **16,045**. OpenRegistry returns **401** with 30 registries, 17 GitHub stars and a 3,331-word README — useCount **3**. Its own commit on 2026-05-20 records the change: "docs: drop anonymous-tier wording, free tier is the entry point." `nordicdata.cloud`, listed in the official registry as an `active` 78-tool, 35M-company competitor, returns **HTTP 525 on every endpoint** — the registry does not health-check listings.

**5. The commercial layer has almost no agent surface, and enormous headroom above it.** OpenCorporates charges **"£2,250/year… Up to 500 API calls/month"** — roughly £0.45 per call — for data Companies House gives away at **"600 requests within a five-minute period"** for free. Of ten tier-one vendors searched (OpenCorporates, kompany, Middesk, Trulioo, Persona, Creditsafe, D&B, Proff, Enin, Bizzy), **exactly one has an MCP server**: `Trulioo/mcp-server` — .NET 8 stdio, "This project is experimental", 2 stars, **last push 2025-12-16**, in no registry. **Not one national business register anywhere has published an MCP server or an agent statement.**

**6. Norway's commercial floor is 0.08 kr, not £0.45.** Firmaradar publishes **0.08 kr/lookup** plus 99 kr/month; Apier publishes 0.50 kr/call. Both shipped MCP servers in 2026-05. The three Norwegian vendors that sell seats through sales calls — Proff (**no published price at all**), Enin (**1,295 NOK/user/month**, API "Fixed price - Contact us"), Bizzy — have no agent product. You cannot sell a seat to an agent.

**7. The category is five months old, unfunded, and tiny.** Nine products use a near-identical "company data for AI agents" phrase; **no disclosed venture round was found for any of them**, while $40M went to MCP *security* in the same period. Summed npm and PyPI downloads across the whole company-registry MCP field are roughly **1,900/month**.

## The three competitors that matter most

**Apier** (`05-apier-the-closest-competitor.md`) — the only rival that computes Norwegian statutory deadlines, and it does so with legal citations, a versioned rulebook and Altinn write rails registry-mcp has no path to. It cannot follow across the border, requires a key, and will charge. If registry-mcp's pitch is "the one that computes deadlines", Apier already answers it in Norway, better. The defensible line is narrower and truer: *one response shape, deadlines with cited statutes, across countries, free and keyless.*

**ENTIA** (`04-multi-country-and-gleif-mcp-servers.md`, `10-traction-and-usage-signals.md`) — 10 countries, 12 tools, anonymous hosted endpoint, **16,045 Smithery uses**. It is the proof that anonymous access plus verdict-shaped tools (`run_risk_audit`, `verify_vat`, `get_full_dossier`) beats jurisdiction count by four orders of magnitude. It is the model registry-mcp should study for shape, not for data.

**Brønnøysundregistrene itself** (`09-registers-as-competitors.md`) — free, keyless, no published rate limit, NLOD 2.0. The real competitor is an agent with a `fetch` tool and a URL. Everything registry-mcp offers must be worth more than the two seconds it takes to skip it. brreg is also the register most likely to ship an agent surface first: its 2026 GitHub activity is machine-readable concept modelling.

## Gaps nobody fills

- **Beneficial owners in a normalised shape.** Brønnøysundregistrene publishes a beneficial-owners dataset free; Companies House publishes PSC. registry-mcp exposes neither, and every multi-country rival does. Largest single feature gap, and both live countries already have the data.
- **National identifier ↔ LEI.** Seven GLEIF MCP servers exist; no register server returns an LEI. The one identifier that crosses jurisdictions is unclaimed.
- **Offline ID validation.** `validate_company_id` appears in **no other product surveyed**, free or paid.
- **`search` / `fetch` aliases.** Both usage leaders ship them; they are the ChatGPT deep-research connector contract. Cheapest untaken distribution channel in the field.
- **Uptime as a claim.** Two of the most impressive-sounding listings fail a live probe. Nobody publishes an uptime number.
- **Honest `null`.** Only registry-mcp distinguishes "the register says no" from "this register does not publish it."

## What this means for registry-mcp

The lane was never empty, but it is uncontested where it matters. Thirteen working brreg servers exist and none computes a deadline, validates an identifier offline, or documents what a `null` means. Nineteen UK servers exist and the leader is AGPL — unusable inside anyone's hosted product. Ten commercial vendors and seven national registers have, between them, one abandoned experimental MCP server.

Three moves the evidence supports, in order.

**Protect the anonymous endpoint.** It is the only variable that tracks usage across every product measured. Keyless Norway plus an anonymous `api.foretak.dev/mcp` is worth more than the next three features, and OpenRegistry's collapse from 30 registries to 3 uses after gating is the cautionary case.

**Add beneficial owners and `search`/`fetch`.** UBO is the one column where every serious rival scores and registry-mcp does not, and brreg and Companies House both publish it free. `search`/`fetch` costs two aliases and opens the ChatGPT connector.

**Move one step toward verdicts.** Every product with real usage — bouch (60,787), ENTIA (16,045), the Chinese `financial-services-qcc` (★28) — returns a judgement or runs a workflow, not a record. registry-mcp's honest `CompanyReport` is the right foundation and is not, on this evidence, what gets connected. A `company_deadlines` response that says "this årsregnskap is overdue, here is the statute, here is the date" is already a verdict; leaning into that, plus a shipped skill, matches the traction data without giving up the correctness that is the actual differentiator.

Set expectations to real scale: the leading brreg server does 236 npm downloads a month. Winning Norway means a few hundred developers — achievable, and not achievable by out-featuring anyone.

## Open questions we could not answer

1. **kompany's price list.** https://www.kompany.com/i/support/price returns **HTTP 403** to non-browser clients. The tier list exists; the figures were not readable and no archive copy was retrieved.
2. **Any per-call price for Middesk, Creditsafe, D&B or Persona from a primary source.** All figures in `07-commercial-kyb-apis-global.md` are third-party comparison sites, marked low confidence.
3. **Enin's and Proff's API prices.** "Fixed price - Contact us" and nothing at all, respectively.
4. **Nordic Data (nordicdata.cloud)'s real pricing, tool list and status.** Every endpoint returned HTTP 525 all day on 2026-09-05. The €0–€499/month figures are secondary and unverified. Re-check: it may return.
5. **Whether Brønnøysundregistrene has any internal MCP or agent plan.** No roadmap document found; `org:brreg mcp` returns 0 repositories. This is absence of evidence, not a verified negative.
6. **Erhvervsstyrelsen's actual CVR system-to-system terms, quotas and fees** — disclosed only after emailing `cvrselvbetjening@erst.dk`. No primary quote available.
7. **What Smithery's `useCount` counts** — installs, sessions or cumulative tool calls. Undocumented; the ordering is trustworthy, the magnitudes are not.
8. **Glama's listing and usage data.** `glama.ai/api/mcp/v1/servers` requires an API key and imposes attribution conditions under its API Data License. Not retrieved; the Glama-side census in NAMES.md could not be independently reproduced.
9. **Funding for any AI-native entrant.** Crunchbase itself was not queried directly — only derived news aggregators. "No round found" is not "no round exists".
10. **Whether Apier's beta pricing has taken effect.** The page says "Planned pricing… takes effect when the API exits beta" with no date.
