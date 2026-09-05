# NAMES

What is owned, what is free, what is taken — per build plan §1.1. Checked 2026-09-04 (read-only RDAP / registry API probes; evidence in the orchestrator's availability report).

## Owned

| Name | Where | Status |
|---|---|---|
| `foretak` | GitHub organisation | **Owned** — created 2026-09-04 by Kim (`fargerod-dotcom`) |
| `foretak/registry-mcp` | GitHub repo | **Owned, public** — https://github.com/foretak/registry-mcp |
| `io.github.foretak/registry-mcp` | Official MCP registry name | Matches the org; publishable once packages exist |

## Free as of 2026-09-04 (not yet registered)

| Name | Where | Evidence |
|---|---|---|
| `foretak.dev` | Domain (primary choice) | Google Registry RDAP 404, no DNS |
| `foretak.ai`, `foretak.io` | Domain (defensive) | Identity Digital RDAP 404 |
| `orgnr.dev`, `enhet.dev` | Fallback brands | RDAP 404 |
| `registry-mcp`, `brreg-mcp` | PyPI | 404 on `/pypi/<name>/json` |
| `registry-mcp` | npm | `registry.npmjs.org` → Not found |
| `@foretak/registry-mcp`, `@foretak/brreg-mcp` | npm (scoped) | 404 — needs the free `@foretak` org first |

## Taken

| Name | Where | By whom |
|---|---|---|
| `foretak.no` | Domain | Unrelated Norwegian company, registered 2015 |
| `brreg-mcp` | npm | `hellosverre` (v0.1.1, 2026-04-23, dormant, 57 downloads/week) — see below |

## Competitive field (important — the build plan assumed an empty lane)

Found 2026-09-04 across the official MCP registry, Glama and Smithery. None has real traction, but several are active:

| Server | Scope | Activity |
|---|---|---|
| `hellosverre/brreg-mcp` (npm, registry `io.github.hellosverre/brreg`) | 5 tools, brreg only | dormant since 2026-04 |
| `pipeworx-io/mcp-brreg-no` | hosted Streamable HTTP | pushed 2026-08-26 |
| `nordio-ai/brreg-mcp-server` | brreg | updated ~2026-08-24 |
| `7nashinick/norwegian-data-mcp` | brreg + SSB macro data | updated ~2026-08-28 |
| `olgasafonova/nordic-registry-mcp-server` | NO/DK/FI/SE, 23 tools, Docker | pushed 2026-08-31, Glama grade A |
| `cloud.nordicdata/nordic-data` | commercial KYB, 78 tools, 35M companies | active, hosted |
| `sophymarine/openregistry` | 27 countries, 60+ tools | active |
| `DimaVasilenko-Intune/mcp-brreg`, `andyarntsen-alt/brreg-mcp-server`, `daveHylde`, `reidar80`, `josuekongolo/CompanyIQ`, `Mnymann/nordic-data-mcp` | various | stale (7–12 months) |

What none of them appear to do: filing deadlines with `today`, verified-field mapping with honest `null`/`notes`, REST≡MCP parity, `llms.txt` discovery layer.

**Positioning.** The phrase we own stays **"the company registry MCP"** (`KEYWORDS.md` row 11a): it leads the homepage H1, the README H1, `llms.txt` line 1 and the package descriptions. The one sentence that defends it, after the competitor census in `research/05-competitors.md`, is **one response shape, deadlines with cited statutes, across countries, free and keyless**. Lead with that, not with "an MCP server for brreg" (fifteen of those exist, the best has 8 stars) and not with "the one that computes deadlines" (Apier does, in Norway, with legal references).

---

## Addendum 2026-09-05 — competitors the 2026-09-04 audit missed

Found by the research task force (`research/05-competitors.md`; full census in
`~/research/registry-mcp/05-competitors/`):

- **Proff Premium MCP** (Enento) — NO/SE/DK/FI, financials, roles, beneficial owners; quote-only behind a NOK 12,490–24,990/year subscription. https://forvalt.no/ProffAPI/MCP
- **Apier** (`PowerLaunch/apier-mcp`) — 26 tools incl. Norwegian deadlines and obligations with legal references, Altinn delegation; NOK 0–9,999/month or 0.50 kr/call, free in beta; Norway-only, key required, closed backend. The closest competitor. https://www.apier.no/pricing
- **`io.github.pipeworx-io/brreg-no`** — a second brreg server in the official MCP registry (with `hellosverre/brreg`).
- **`bouch/uk-due-diligence`** — 16 tools over five UK registers, 60,787 Smithery uses (created 2026-04-29). The UK incumbent.
- **ENTIA** — 10 countries, anonymous hosted endpoint, 16,045 Smithery uses; the proof that keyless access predicts usage.
- **Firmaradar** — 99 kr/month + 0.08 kr/lookup; **Nordic Data** (`nordicdata.cloud`) listed active in the official registry but HTTP 525 all day on 2026-09-05; **CompanyIQ** 404.

Net: fifteen brreg MCP repos exist (best: 8 stars); none computes a deadline, none validates an identifier offline, and only two are in the official registry. That census is what the positioning paragraph above is drawn from.
