# 04 — MCP and the agent ecosystem

How MCP servers and agent tools get discovered, adopted and paid for, as of **2026-09**, and what earlier developer-API businesses teach about it. Fifteen files; every number below is sourced in one of them.

---

## Key findings

**1. The official registry holds 27,184 servers and is growing ~450/day.** Counted by full pagination of `registry.modelcontextprotocol.io/v0.1/servers?version=latest` on 2026-09-05: **27,184** servers, 15,313 (56.3%) with a remote endpoint, 11,871 package-only. August 2026 alone added **8,522**. The registry describes itself as "deliberately unopinionated" and states it "is **not** intended to be directly consumed by host applications" ([about](https://modelcontextprotocol.io/registry/about)). Being listed is plumbing, not distribution. → `official-mcp-registry-size-and-growth.md`

**2. Registry search matches the server NAME only.** The OpenAPI spec documents `search` as "Search servers by name (substring match)". Verified live: `brreg` → 2 results, neither of them registry-mcp; `orgnr` → 0; `enhetsregisteret` → 0; `companies house` → 0. All twenty keywords in registry-mcp's `_meta` block, and its whole description, are unsearchable. There is also **a second competing brreg server** the project did not know about (`io.github.pipeworx-io/brreg-no`, alongside `io.github.hellosverre/brreg`). → `official-registry-search-is-name-only.md`

**3. The Smithery listing is currently worth zero, for one fixable reason.** `fargerod/registry-mcp` has an **empty `description`** and no icon, and appears **nowhere in the top 100** for `registry-mcp`, `brreg`, `company registry`, `organisasjonsnummer`, `foretak`, `norway company` or `companies house deadlines`. Smithery's search is "full-text and semantic" over the description — with no description there is nothing to match. Separately: Smithery lists 11,656 servers but **browsing reaches only 500** (5 pages × 100; page 6 is empty), and the cheapest entry to that browsable set is 1,565 uses. The direct UK competitor `bouch/uk-due-diligence` (16 tools, five UK registers, created 2026-04-29) has **60,787** uses. → `third-party-directories-and-counts.md`

**4. The Claude Connectors Directory — the largest install surface — requires a paid Claude Team or Enterprise organisation** to reach the submission portal ("Organization settings aren't available on individual plans"). Two free adjacent doors exist: the MCPB desktop-extension form, and self-hosted Claude Code plugin marketplaces (`/plugin marketplace add owner/repo`). Both Anthropic and OpenAI require **tool annotations** — `title` + `readOnlyHint`/`destructiveHint` (Anthropic), plus `openWorldHint` (OpenAI) — which registry-mcp does not ship. Missing privacy policy is "immediate rejection". → `claude-connectors-directory-submission.md`

**5. There is no payment support in MCP, and no client can pay.** Four payment SEPs, all closed, none merged; PR #2007 was closed 2026-06-24 as "dormant" for want of a sponsor. The 2026-07-28 spec contains no payment feature. Stripe's Machine Payments Protocol works (HTTP 402 → agent pays → retry with receipt, ~10 lines with `mppx`) but imposes a **$0.50 minimum on card payments** ($0.01 on stablecoin). → `mcp-monetisation-state-of-play.md`

**6. Only Apify pays tool authors: "80% of the revenue minus platform usage costs", "$1.5M paid out last month", "most prices on Apify Store range between $1-10 per 1,000 results"** ($0.001–$0.010/result). Smithery's full docs index contains no monetisation page; Glama pays nothing. → `marketplaces-that-pay.md`

**7. Two independent sources put the market rate for a machine-consumed retrieval at roughly half a cent to a cent.** Exa search "$7 / 1k requests"; Tavily "$0.008 / credit" with 1,000 free credits/month; Firecrawl 1,000 free credits/month then $16/month; Browserbase $20/month. Against that, the company-data incumbents charge **£0.20–£4.50 per call**: OpenCorporates Essentials **£2,250/year for 500 calls a month**; Beauhurst's API **£3,500/year for 10,000 credits but only with 10 platform users (£40,000/year)**. Clearbit never published a price at all — three archive snapshots (2017, 2019, 2022) show "configure pricing"/"contact us". → `pricing-benchmarks-*.md`

**8. Show HN is a two-upvote channel for this.** 317 Show HN posts with "MCP" in the title in the last 365 days (HN Algolia API, own measurement): **median 2 points, 83.3% got ≤ 4 points, four posts cleared 50, none reached 100.** All four winners were infrastructure *for* MCP builders, not connectors. → `developer-gtm-and-launch-channels.md`

**9. The protocol changed radically six weeks ago and registry-mcp got lucky.** The 2026-07-28 revision removed sessions and the `initialize` handshake, made MCP stateless, and added a mandatory `server/discover` RPC. registry-mcp's five pure read-only tools were *already* stateless. Two things to verify: the pinned SDK implements 2026-07-28, and no proxy strips the now-required `Mcp-Method`/`Mcp-Name` headers. → `mcp-spec-2026-breaking-changes.md`

**10. Three of six documented MCP security incidents came through public registries.** The official registry states it "does not make guarantees about moderation" and does not remove "servers with security vulnerabilities". Glama is the only registry that actually builds and runs servers in Firecracker microVMs and watches syscalls. registry-mcp's read-only, no-credentials, two-named-upstreams posture is a real advantage that appears nowhere in its README. → `mcp-security-and-registry-trust.md`

---

## Channel-by-channel assessment for registry-mcp

| Channel | Evidence | Effort | Verdict |
|---|---|---|---|
| **Smithery description + icon** | Listing absent from top 100 of every relevant query incl. its own name; `description: ""` | 15 min | **Do now.** Highest return per minute in this folder |
| **Tool annotations** (`title`, `readOnlyHint`, `openWorldHint`) | Required by Anthropic *and* OpenAI directories; a Glama TDQS dimension; machine-readable security claim | 1 h | **Do now** |
| **One-click install badges in README** (VS Code, VS Code Insiders, Cursor) | The only install path open to everyone in every client; README is what directories scrape | 2 h | **Do now** |
| **Security paragraph in README** | 3 of 6 incidents came via registries; no competitor states this | 20 min | **Do now** |
| **Glama claim + Dockerfile** | Glama builds/runs/scores every server, publishes "actionable gap analysis"; is "a superset" of the official registry | 1 h (pending claim) | **Do** — it is the only directory that ranks on merit |
| **Hand-installing for 10 named developers** | PG's "Collison installation"; the project has zero product feedback so far | days | **Do** — highest absolute value |
| **Official MCP registry** | Done. Feeds aggregators; not consumed by clients; search can't find you | done | **Keep, expect nothing more** |
| **Claude Connectors Directory** | Largest install surface; blocked on a Claude Team plan | subscription + review | **Cost it, decide deliberately** |
| **MCPB desktop-extension submission** | Free door to Anthropic; needs a bundle + privacy policy | ~half a day | **Worth it** if the Team plan is a no |
| **Claude Code plugin marketplace** (self-hosted on GitHub) | No gatekeeper; `/plugin marketplace add foretak/registry-mcp` | ~half a day | **Cheap, unmeasured — try it** |
| **Apify Actor** | Only channel with published payouts; free distribution to Make/n8n/Gumloop; costs a rebuild + lock-in | weeks | **Cost it; the $1–10/1k price band is valuable even if you never publish** |
| **Show HN** | Median 2 points, 83% ≤ 4, 0 posts over 100 in a year | 1 h | **One lottery ticket**, framed around the cross-country schema, not "an MCP server for brreg" |
| **PulseMCP** | Closed to submissions; API in staged sunset (100% failure from Sept 2026) | 0 | **Nothing to do** |
| **mcp.so / MCP Market / awesome-lists** | No traffic data from any of them; submissions already in flight | already spent | **Stop after current ones land** |
| **Paid listing tiers** (mcpservers.org $39, mcp.so paid) | Same listing, no evidence of return | $39+ | **No** |
| **llms.txt / llms-full.txt** | 8.7% of top-1,000 sites publish it; **zero published evidence** it affects anything | already built | **Keep, stop investing.** Demote to documentation convenience |
| **r/mcp, dev.to, X, YouTube** | Reddit blocks automated access; no measured data for any | ? | **Unknown — a human should check r/mcp manually** |

## Pricing-model comparison

| Model | Who does it | Free tier | First paid step | Per-call | Fit for registry-mcp |
|---|---|---|---|---|---|
| **Pay-as-you-go, no plan** | Exa, Tavily | $10–20 credits/mo; 1,000 credits/mo | none / $0.008 per credit | $0.005–$0.008 | **Best fit.** Matches how the tool is used (bursty, per-lookup) |
| **Renewing free tier + monthly plans** | Firecrawl, Browserbase | 1,000 credits/mo; 1 browser-hr | **$16–$20/mo** | $0.0006–$0.003 | **Best fit for the paid step.** Not $99 |
| **Marketplace rev-share** | Apify (80% to author) | n/a | n/a | $0.001–$0.010/result | Viable but costs a rebuild and the project's identity |
| **Per-call crypto/402** | x402, Stripe MPP | n/a | n/a | $0.01 min (stablecoin), **$0.50 min (card)** | **Not yet** — no client can pay; card floor is 50–500× the right price |
| **Annual contract + call cap** | OpenCorporates | public-benefit only | **£2,250/yr for 500 calls/mo** | £0.375 | The thing to compete *against*, not copy |
| **Seat licence + API add-on** | Beauhurst | none | **£3,500/yr API, min 10 users = ~£43,500/yr** | £0.35 | Ditto |
| **Opaque, value-priced** | Clearbit (never published a price) | none | "contact us" | unknown | No — kills self-serve, which is the whole distribution model |
| **Bring-your-own-key** | registry-mcp today (UK) | unlimited | n/a | $0 | **Keep for stdio.** Costs nothing, but you never see usage and can never charge |
| **Open core by transport** | Firecrawl, Tavily | self-host free | hosted paid | — | **The natural shape:** `uvx registry-mcp` free forever; `api.foretak.dev` metered |

---

## What this means for registry-mcp

The distribution problem is not "we are not listed enough". registry-mcp is in the official registry, Smithery, MCP Market and (pending) Glama, and it has produced zero uses. The problem is that **on every surface that ranks, the project is invisible for the words it owns** — the registry indexes only names, Smithery indexes a description the project left blank, and both incumbents in this niche have four-month head starts and 60,787 uses.

So the work is not more submissions. It is making the three surfaces already owned actually convert: the **Smithery description**, the **tool annotations**, and the **README** (install badges, the security paragraph, an agent-paste integration prompt). All three are hours, not weeks, and all three compound — annotations feed Anthropic's directory, OpenAI's, and Glama's score simultaneously.

On pricing: charge nothing yet, but **meter the hosted endpoint now**. The comparators are unanimous that the shape is a renewing 1,000-call free tier, a ~$15–20 first step, and a per-lookup unit at roughly a cent — and equally unanimous that you cannot design that without knowing what real callers do. The commercial story writes itself once the metering exists: *OpenCorporates charges £2,250 a year for 500 calls a month; Beauhurst's API starts at £43,500; this is free, open, and normalised across countries.*

Finally, `bouch/uk-due-diligence` should be read closely before the next release. Same country, wider coverage, four months older, 60,787 uses, and a two-line description that names outcomes rather than mechanisms.

---

## Open questions we could not answer

1. **Does a directory listing actually cause installs?** No directory publishes attribution. Smithery's `useCount` is the closest proxy and its docs never define what it counts (tool calls? sessions? installs?).
2. **Should registry-mcp publish a second registry entry named `brreg-mcp`** to win the one search term that matters? It would work — search is name-substring — but the moderation policy names "the same server ... under different names" as spam. Human decision; genuine risk to both listings.
3. **Is r/mcp worth anything?** Reddit blocked every access route available here. Member count, self-promotion rules and engagement all unknown. Needs a human with a browser.
4. **Does any aggregator index `_meta.publisher-provided.keywords`?** If Glama or PulseMCP do, the twenty keywords in `server.json` are working; if not, they are dead weight. Neither vendor documents it.
5. **Can a Norwegian-registered business use Stripe SPTs or stablecoin machine payments?** Both are gated on country lists we did not open.
6. **Does `registry-mcp` 0.2.0's pinned MCP SDK implement the 2026-07-28 spec** (and therefore the mandatory `server/discover`)? Checkable in the repo; the first action from `mcp-spec-2026-breaking-changes.md`.
7. **RapidAPI's provider revenue share and marketplace size** — the page returned no content this session, and the number should not be quoted from memory.
8. **Apify's "Many developers earn over $3k"** — over what period, and revenue or post-split profit? Unstated.
9. **Glama's total server count and registry-mcp's TDQS score** — the methodology page publishes scan volume, not inventory, and the API needs a key.
10. **Abstract API's Standard tier**: its own page says both "60,000 requests / month" and "60,000 requests / year", a 12× difference in the effective rate.
