# FEEDBACK

Every inbound signal about registry-mcp, one entry per item, newest first.
This is the input the day-45 decision gate (~2026-10-19, `BRREG_MCP_BUILD_PLAN.md`
§4.3) reads alongside the stats dashboard. Log the substance, not the sentiment:
what they asked for, what they tried, what stopped them, what they would pay for.

Format: `date · channel · who (handle or role) · what they said · what we did`.

## Open threads to watch

| Channel | Where | Since | Status |
|---|---|---|---|
| Reddit r/mcp | https://www.reddit.com/r/mcp/comments/1w7u6j0/ | 2026-09-05 | removed by Reddit's automatic filter on posting; modmail to the mods sent; no comments |
| dev.to | five articles under https://dev.to/fargeroddotcom | 2026-09-04 | no comments yet |
| GitHub | https://github.com/foretak/registry-mcp/issues | 2026-09-04 | only our 3 seed issues |
| mcp.so | chatmcp/mcpso#3927 | 2026-09-04 | no reply |
| Glama | https://glama.ai/mcp/servers/foretak/registry-mcp | 2026-09-05 | live, claimed, build + checks passed 14:36Z, score badge renders |
| awesome-mcp-servers | punkpeye#13631 | 2026-09-04 | Glama badge added 2026-09-05; waiting for bot re-check and a Glama score |
| Erhvervsstyrelsen | cvrselvbetjening@erst.dk (T16) | 2026-09-05 | application sent, acknowledged as sagsnummer 177481; reply due ~2026-09-23 |
| mcpservers.org | https://mcpservers.org/servers/foretak/registry-mcp | 2026-09-05 | approved and live 22:02Z (mail to hello@foretak.dev); badge in README 2026-09-06 |

## Stats baseline — reset considered and declined 2026-09-05 (Kim: "leave it, it's fine")

The usage log (`calls` table in the production SQLite on the Railway volume) keeps its rows. As of 2026-09-05 ~16:15Z it holds **252 calls, all our own** (smoke tests, probes, browser checks); read every later figure as a delta from that baseline. It was going to be emptied because our own smoke tests, probes and browser checks made up nearly all of the 252 rows. The rows are backed up to `~/secrets/registry-mcp/calls_backup_2026-09-05.json` (outside the repo). **Baseline: 252 rows / 248 REST + 4 MCP at 2026-09-05 16:15Z, none external.** Rule from here: the orchestrator's daily read touches only `/health` and `/v1/stats` (not logged as calls); any functional check runs against a local or Docker server, never production; never look up the invalid example 833286602 live.

## Entries

- 2026-09-10 07:20Z · stats read (baseline refresh for the 2026-10-19 gate) · **578 calls total** (562 REST + 16 MCP), 0 today, 95 on 09-09 (our two deploy smokes plus 67 hits from a `pip/24.3.1` user agent — a scanner or a mis-pointed package index, not a caller), 65 distinct user agents, error rate 3.5%, cache hit rate 83%, p95 206 ms · **still no external agent**; every later figure is a delta from 578. The products round (`~/mcp-growth/products/`) concluded 2026-09-10: no product to build for money now; the only build trigger is a stranger at the 60/min ceiling or asking for a key.
- 2026-09-09 · Glama connectors (TDQS review of the hosted endpoint, automated) · Healthy, A 4.6/5 across 7 tools · notes: `company_deadlines` lacks a leading verb; the ChatGPT `search`/`fetch` aliases read as redundant; Sweden's identifier-only lookup recorded as a documented limit · what we did: badge added to awesome-remote-mcp-servers PR #146; the naming note is a tool-rename question for the next contract revision (D-004 freezes the five tools' names — not a quick fix).
- 2026-09-09 · GitHub · punkpeye (maintainer, awesome-remote-mcp-servers #146) · asked in person for the Glama connector badge, "a requirement" · done the same evening; PR mergeable.
- 2026-09-05 19:25Z · stats read · 278 calls total (269 REST + 9 MCP). Of the 5 MCP calls since the 16:52Z read, 3 are our own post-deploy checks of the connector aliases (`search("Equinor")` ×2, `fetch("NO:923609016")`, 18:05Z and 18:19Z). **The other 2 are the first external MCP calls: User-Agent `SaSame-MCP-Audit/0.1`, query `test`** — an MCP audit/scanner bot, not a coding agent; unknown operator, nothing found about it yet. On REST, a Linux Chrome browser (Chrome/134, X11) made 4 lookups: the Tesco README example twice plus UK numbers 05888957 and 09384423 — looks like a real visitor trying the playground. The rest is the `Mozilla/5.0 (compatible)` directory monitor (+6) and curl (+3, Equinor example, probably ours).

## Outbound (things we said to others, so replies can be traced)

- 2026-09-10 · GitHub · Universal-Commerce-Protocol/ucp discussion #146 · itzikhr18 (the Israeli verification vendor) asked whether we had seen demand for Israeli verification, workflow, budget — a vendor validating its own demand · replied honestly on Kim's "post": no requests at all, ~600 calls all our own, the accuracy write-up shared, offered to compare notes · https://github.com/Universal-Commerce-Protocol/ucp/discussions/146#discussioncomment-18383549 · watch for a reply.
- 2026-09-10 · GitHub · UCP discussion #146 · itzikhr18 replied 09:33Z: no validated buyer demand on their side either; proposed a seven-day asynchronous evidence exchange, one hour each, ≤2 public first-person requests per side or an explicit "none", no integration/spending/data/commitments · accepted on Kim's "post" (https://github.com/Universal-Commerce-Protocol/ucp/discussions/146#discussioncomment-18386125): our side = none, plus the accuracy write-up, the register constraints and the pricing floor · **closed 2026-09-10 on Kim's "let's just drop it, what's in it for us": withdrew politely (https://github.com/Universal-Commerce-Protocol/ucp/discussions/146#discussioncomment-18386202) — nothing on our side to contribute, ours already public. No follow-up.**
- 2026-09-05 · GitHub · nordio-ai/brreg-mcp-server#7 (feature request for 8 dropped brreg fields, author fmogensen) · commented with the field-for-field mapping to `CompanyReport`, offered `mapping.py`/`NORBIZ_SPEC.md` §3 under MIT, agreed with their eval finding and mentioned the roll-forward correction · https://github.com/nordio-ai/brreg-mcp-server/issues/7#issuecomment-5552901312 · watch for a reply.
- 2026-09-05 · awesome-mcp-servers PR #13631 · told the maintainers the Glama checks passed · no human reply yet.
- 2026-09-05 · Erhvervsstyrelsen · CVR access application, sagsnummer 177481 · reply due ~2026-09-23.
- 2026-09-05 · Weavio (Nodaro Technologies AB, Fortnox marketplace MCP vendor) · peer email drafted in Kim's Gmail to support@weavio.se asking what a Swedish user wants checked at supplier creation and whether they would compose a registry tool · **sent 2026-09-05 15:5xZ** from fargerod@gmail.com.
- 2026-09-05 · kode24 · pitch to ole@kode24.no (cc hei@kode24.no), VAT article inline · **sent 2026-09-05 15:5xZ** from fargerod@gmail.com · watch for a reply; next piece (deadlines) two days after they answer or publish.
- 2026-09-10 · GitHub · nordio-ai/brreg-mcp-server#7 checked for a reply (T64 Part D) · **still no reply** — issue unchanged at 2 comments since our 2026-09-05 mapping comment · https://github.com/nordio-ai/brreg-mcp-server/issues/7 · keep watching.
- 2026-09-10 08:20Z · GitHub · Universal-Commerce-Protocol/ucp discussion #146 ("Business Verification Extension - Trust Signals for Agentic Commerce" — an open, active cross-vendor proposal thread; on 2026-08-30 itzikhr18 had pitched an Israel company-verification MCP the same way, as a jurisdiction-specific evidence provider) · commented offering registry-mcp as the GB/NO/SE evidence provider in the same shape — named the tool once with the hosted install line (`claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp`), listed `lookup_company`/`validate_company_id`/`company_deadlines` factually, and matched their honest-limits framing (registry evidence only; no UBO; no sanctions/PEP/adverse-media; not a payment/fraud check) · https://github.com/Universal-Commerce-Protocol/ucp/discussions/146#discussioncomment-18383063 · watch for a reply.
