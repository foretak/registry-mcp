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

What none of them appear to do: filing deadlines with `today`, verified-field mapping with honest `null`/`notes`, REST≡MCP parity, `llms.txt` discovery layer. That, plus freshness, is the differentiation to lead with in the articles.
