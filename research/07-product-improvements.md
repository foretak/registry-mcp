# 07 — Product improvements: what registry-mcp should build next, ranked

Compiled 2026-09-05. Fourteen source files in this folder; every claim below traces to one
of them, and every file carries its own sources.

---

## Key findings

**1. The five tools are correct and the schemas are empty.** Measured from the running
FastMCP 4.0.2 server on 2026-09-05: every tool's `outputSchema` is the degenerate
`{"type":"object","additionalProperties":true}`; `annotations` is `null` on all five; not
one parameter carries a `description`, a `pattern` or a bound. The models that would fill
those schemas — `CompanyReport`, `SearchResult`, `DeadlineReport`, `ValidationResult`,
`CountriesResponse` — already exist, fully described, in `core/models.py`. The MCP spec is
explicit about what an output schema buys: it "guides clients and LLMs to properly parse
and utilize the returned data"
([spec](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)). Glama
"scans servers for tools, **schemas**, license, and quality score", so this is a discovery
cost as well as a correctness one. → `03`

**2. Absent annotations make five read-only tools look destructive.** The `ToolAnnotations`
defaults are `readOnlyHint=false`, `destructiveHint=**true**`, `idempotentHint=false`,
`openWorldHint=true`. Per FastMCP's docs, "read-only tools skip confirmation prompts in
clients like Claude and ChatGPT" ([gofastmcp.com](https://gofastmcp.com/servers/tools)). An
agent checking a 50-row supplier list currently asks the user 50 unnecessary times. → `02`, `03`

**3. Five tools is a quantified moat, and it is unstated.** Tool-selection accuracy
"degrades with more than 30-50 tools loaded at once"
([Claude Code docs](https://code.claude.com/docs/en/agent-sdk/tool-search)), and Cursor
users report a client-wide cap of about 40 tools. Competitors ship 23
(`olgasafonova/nordic-registry-mcp-server`), 60+ (`sophymarine/openregistry`) and 78
(`cloud.nordicdata`). registry-mcp costs a user ~12% of that budget. The README never says
so. → `01`, `14`

**4. The whole competitive field has produced two user-filed feature requests, and
registry-mcp already answers one — eight fields out of eight.**
`nordio-ai/brreg-mcp-server` issue #7 measured that server reading 12 of brreg's 40 fields
and asked for eight more; all eight are in `CompanyReport` today. The same issue quotes an
eval finding that *"arm C came last. Its four curated tools were a ceiling."* → `04`

**5. The incumbent's own documented freshness is 30 days.** OpenCorporates' knowledge base:
*"please allow 30 days for the information to be automatically updated."* registry-mcp's
worst case is 24 hours with `cached` and the original `fetched_at` on the wire. Its pricing
is £2,250–£12,000/year for 500–5,000 calls a month, i.e. **£0.20–£0.375 per call**. → `06`

**6. Officers, beneficial owners (GB), documents, bulk snapshots and change feeds are all
free upstream in both live countries.** brreg: `/api/enheter/{orgnr}/roller`,
`/api/oppdateringer/enheter`, `/api/enheter/lastned`, and an open
`regnskapsregisteret/regnskap/{orgnr}` (key figures, latest year, marked *"preview, with no
guarantees of quality of service"*). Companies House: officers, PSC, the Document API, a
free Streaming API and monthly bulk CSVs. The constraint is design and privacy policy, not
access. The exception is **Norwegian beneficial ownership**, which requires Maskinporten
authorisation with actor-tiered access to identity numbers — an organisational L, not an
engineering one. → `11`, `12`, `13`

**7. UK SIC 2007 and Norwegian SN2007 are both NACE Rev.2.** The UK ONS states UK SIC 2007
"is identical down to the 4 digit level of NACE". Both truncate to the same NACE class, so
cross-country industry comparison is a static table away — and it would fix
`"description": null` on every UK company's industry codes. → `12`

**8. Companies House's own three surfaces disagree with each other, publicly and
repeatedly** — "Streaming API event not matching REST API" (13 replies), "Inconsistency
between Officer Bulk Snapshot and Stream", "Discrepancies between bulk snapshot and CH
API", plus a "Live Streams Are Down" thread with 30 replies. D-004's "one contract, both
surfaces" has a named real-world enemy. → `05`

**9. The rate limit is a ban risk, and the cache is the mitigation.** Companies House:
600 requests per 5 minutes, and *"We reserve the right to ban without notice applications
that regularly exceed or attempt to bypass the rate limits."* No paid tier raises it.
registry-mcp's 24 h cache is what keeps a spreadsheet job inside that limit — an
availability and compliance feature currently framed as a staleness apology. → `05`, `13`

**10. llms.txt is not a discovery channel.** An SE Ranking study of 300,000 domains found
**10.13%** adoption, of which the HTTP Archive found ~40% were plugin stubs; a monitoring
analysis of 500M+ AI bot events over 90 days found only a few hundred requests for
`/llms.txt`. Google has said it does not support it. `NAMES.md` lists the "llms.txt
discovery layer" as one of four differentiators; the other three are real. Keep the files —
they are excellent *documentation* — and drop the discovery claim. → `14`

**11. Nothing measures whether an agent uses the server correctly.** 391 unit tests prove
the server is right; zero tests prove an agent succeeds with it. D-015 explicitly deferred
the `country="UK"` question to post-launch telemetry — an eval answers it before launch. → `07`, `08`

**12. There is no authentication on the hosted API, so there is no revenue path.**
No API keys, no OAuth, no per-caller metering; the per-IP limiter collapses every agent
behind one proxy onto one bucket. No `CHANGELOG.md`, no `SECURITY.md`, no request ids, and
the terms disclaim commitment: *"The hosted endpoint is a convenience, not a commitment."* → `09`

---

## The backlog, ranked

"Core?" means: does it edit `src/registry_mcp/core/` — which the project treats as
expensive (D-001, D-004, and the D-017/D-018 precedent that `core/` is the architect's file).

| # | Item | Effort | Core? | Expected effect |
|---|---|---|---|---|
| 1 | **Rewrite the README's first screen** — lead with deadlines, freshness-vs-30-days, five-tools-vs-40 | XS | no | Adoption. Every install decision is made on this text |
| 2 | **Real `outputSchema` from the existing models** | S | no | Adoption + directory score; spec MUST once declared |
| 3 | **Tool annotations + explicit titles** | S | no | Removes a permission prompt per call in Claude/ChatGPT |
| 4 | **Input schemas: descriptions, `pattern`, bounds, `examples`; `company_id` with `id` as deprecated alias** | S | no | Fewer argument errors; fewer wasted round-trips |
| 5 | **`CHANGELOG.md`, `SECURITY.md`, request ids** | XS–S | no | Removes procurement objections; feeds release-activity ranking |
| 6 | **The 26-case agent eval, in CI** | M | no | Makes items 2–4 measurable; a publishable trust asset nobody else has |
| 7 | **Batch lookup (`company_id: str \| list[str]`, cap 50, partial failures)** | S–M | **yes** | The product's own docs already promise a spreadsheet workflow |
| 8 | **NACE harmonisation on `IndustryCode`** | S | **yes (small)** | Makes "one shape" true for a field where it is only cosmetically true |
| 9 | **Concrete `registry://rules/{cc}` resources per live country** | S | no | The rules doc is currently invisible to `resources/list` |
| 10 | **The honest-caveat trio**: ENK personal-data note, `parent_id` group-walk documentation, "this service does not screen sanctions/PEP" | XS | no | Closes a privacy exposure and a dangerous inference, for nothing |
| 11 | **API keys + per-caller metering on the hosted tier** | M | no | **The gate to every revenue item on this list** |
| 12 | **Change-feed consumer for cache invalidation** | M | no | Answers the competitor's "zero-stale" attack without losing outage resilience |
| 13 | **Officers (NO roles + GB officers) and GB PSC, as `include=[...]`, not new tools** | M | **yes** | The highest-demand real gap; four privacy preconditions first |
| 14 | **Norwegian annual-accounts key figures** | S–M | **yes** | Answers "is this supplier solvent?"; upstream is free but *preview*-grade |
| 15 | **UK filed documents as `resource_link`s** | M | no | A competitor's flagship; GB-only, so ship it as GB-flavoured |

### Notes on the ranking

**Why the top five are all small.** Items 1–5 are roughly two days of work in total, touch
no `core/` file, break no frozen shape, and each removes a concrete friction that is
measurable today. Doing them first also gives item 6 something to measure.

**Why item 6 sits above every feature.** Items 2, 3, 4 and 9 are hypotheses. Cases E14
(`UK`→`GB` self-correction), E17 (bad `today`) and E24 (rules read once vs in a loop) in
`08-eval-set-registry-mcp.md` are their before/after tests. Building features before the
eval means never learning whether the last one helped.

**Why authentication (11) is not higher.** It is the gate to revenue and it is the largest
single item that unlocks others (webhooks, audit logs, per-customer quotas). It sits at 11
because there is no paying customer yet, and a keyed tier with nobody to bill is
infrastructure without a user. The moment one exists, it moves to 1.

**Why officers (13) is not higher despite being the biggest gap.** It needs a `core/` model,
a fifth `Registry` method, a shorter cache TTL for person records, a `suppressed` state
distinct from `null`, and a documented lawful basis — four decisions, none of them code.
See `10-personal-data-and-gdpr-in-registers.md`. Doing it badly is worse than not doing it.

### Deliberately declined, with reasons

- **Sanctions/PEP screening.** Free source data, M effort, and unbounded liability from
  false negatives. Build the join key (`name`, `previous_names`, `id`) and say loudly that
  the service does not screen. → `11`
- **Webhooks.** L, requires authentication and subscription state, and MCP removed
  server-initiated pushes in 2026-07-28 — so it would be a REST-only feature that does not
  extend the MCP story. A polled "what changed since?" delivers most of the value. → `13`
- **OAuth 2.1 for MCP.** The spec-blessed route to auth, but the requirements are large
  (RFC 9728 metadata, RFC 8707 audience binding, issuer validation) and its only buyer today
  is hypothetical. API keys first; OAuth follows a customer. → `09`
- **Parsing UK iXBRL for accounts figures.** L, permanent maintenance, and a real risk of
  publishing a wrong number — which D-009's "never guess" logic rules out. → `12`
- **Norwegian beneficial owners.** Blocked on Maskinporten organisational onboarding, and
  the resulting credential could never ship in `uvx registry-mcp`. Represent it as an empty
  list with a reason. → `10`, `11`
- **Hosting a bulk snapshot.** Different licence conversation, different cost base, and it
  competes with a free official download. Point at it in a `hint` instead. → `13`
- **JSON-LD on the API.** No documented mechanism; `openapi.json` and `server.json` already
  do the machine-readable job. → `14`
- **Renaming the five tools.** Generic names are a retrieval weakness under tool search, but
  renaming breaks a frozen contract for a marginal gain. Spend the budget on first
  sentences. → `01`, `03`

---

## What this means for registry-mcp

The server is more correct than it is legible. Its hardest-won properties — one shape across
two surfaces, honest `null`s, provenance on every field and every date, a mandatory `hint`
that names the next call — are all real, all verified by review, and almost all invisible:
to a schema scanner, to a permission prompt, to a directory score, and to a developer
reading the first screen of the README. The cheapest work in this folder is not building
anything. It is publishing what already exists in the formats the ecosystem reads.

After that, the sequence is: **measure, then extend.** Build the eval so the next fifteen
decisions have evidence behind them, then add the one capability the product already
promises and does not have (batch), then the one that makes "one shape, many countries"
true rather than cosmetic (NACE). Officers is the biggest real gap and should be approached
as a privacy design problem with a code appendix, not the other way round.

The strategic read from the competitive and incumbent evidence: this is not a coverage race.
OpenCorporates has ~140 jurisdictions at £0.20–£0.375 a call and a 30-day refresh;
`openregistry` has 30 registries and raw bytes. Neither answers *what must this company file
next, and when* — and neither can, because that requires per-country statutory rules with
stated provenance. **Two countries done properly, with obligations attached, is a defensible
position. Three countries done shallowly is not.**

---

## Open questions we could not answer

- **Does FastMCP 4.0.2 serialise a returned pydantic model byte-identically to
  `model_dump(mode="json")`?** It decides whether backlog item 2 is a three-line change or
  needs an explicit `output_schema=`. Not testable without running the suite.
- **Does any widely-used client actually branch on `readOnlyHint`?** FastMCP asserts Claude
  and ChatGPT do; no primary Anthropic source was found saying so. Item 3's payoff rests on it.
- **Is the Norwegian beneficial-ownership lookup endpoint truly Maskinporten-gated?** The
  primary brreg documentation says most endpoints are; one secondary source says the lookup
  is open. Settle with a live unauthenticated call.
- **Does the EU's 2024 AML package restore public or legitimate-interest access to
  beneficial-ownership registers, and when?** The web-search budget ran out before a primary
  source could be read. This matters for country three onward.
- **Does Companies House signal a *suppressed* officer field explicitly, or omit it
  silently?** If silently, the `withheld_by_register` state cannot be derived at all — a
  significant finding for anyone building on officer data.
- **What do business buyers of company data actually require contractually** (SLA %, DPA,
  sub-processor list, SOC 2)? Inferred here from competitor behaviour, not researched.
- **Smithery's and Glama's scoring formulas** are not published; both official criteria URLs
  404'd. The description in `07` rests on secondary write-ups.
- **How often does a typical looked-up company actually change?** Unmeasured, so the value
  of change-driven cache invalidation (item 12) over a flat 24 h TTL is unquantified. The
  free change feeds are themselves the cheapest way to measure it.
- **Cursor's real tool cap** — community threads say 40, some say 80, no official
  documentation was read. Write "about forty", not "40".
- **llms.txt evidence is the weakest in this folder**: SEO-industry write-ups citing a study
  whose methodology was not read, and two 2026 reports that contradict each other.

---

## Files in this folder

| File | Subject |
|---|---|
| `01-anthropic-tool-design-guidance.md` | Anthropic's tool-writing guidance; what tool search changed in 2026 |
| `02-mcp-spec-tool-contract.md` | The MCP 2026-07-28 tool contract: schemas, annotations, errors, MRTR, auth |
| `03-tool-audit-registry-mcp.md` | The measured, item-by-item audit of the five tools, with the fix list |
| `04-competitor-issues-and-asks.md` | Every user-filed issue in the competitive field, and what competitors built unasked |
| `05-companies-house-forum-recurring-asks.md` | What CH API users complain about; rate limits, streaming, bulk |
| `06-opencorporates-and-incumbent-complaints.md` | Incumbent pricing, the 30-day freshness figure, and its weak points |
| `07-measuring-tool-quality-for-agents.md` | How to measure agent tool quality; harnesses, directory scores, telemetry |
| `08-eval-set-registry-mcp.md` | The 26-case eval set with expected calls and answers, and how to run it |
| `09-trust-features-paying-customers-expect.md` | Have/have-not inventory: SLA, changelog, auth, headers, audit logs |
| `10-personal-data-and-gdpr-in-registers.md` | The constraint list before officers or owners can ship |
| `11-coverage-gap-people-owners-groups-screening.md` | Officers, beneficial owners, group structures, screening adjacency |
| `12-coverage-gap-accounts-documents-codes-addresses.md` | Accounts, documents, NACE/SIC, addresses, historical names |
| `13-coverage-gap-batch-bulk-change-feeds.md` | Batch lookup, bulk snapshots, change feeds, webhooks |
| `14-discoverability-llms-txt-jsonld-and-client-selection.md` | llms.txt evidence, JSON-LD, and what the README should say first |
