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

## Stats baseline — reset considered and declined 2026-09-05 (Kim: "leave it, it's fine")

The usage log (`calls` table in the production SQLite on the Railway volume) keeps its rows. As of 2026-09-05 ~16:15Z it holds **252 calls, all our own** (smoke tests, probes, browser checks); read every later figure as a delta from that baseline. It was going to be emptied because our own smoke tests, probes and browser checks made up nearly all of the 252 rows. The rows are backed up to `~/secrets/registry-mcp/calls_backup_2026-09-05.json` (outside the repo). **Baseline: 252 rows / 248 REST + 4 MCP at 2026-09-05 16:15Z, none external.** Rule from here: the orchestrator's daily read touches only `/health` and `/v1/stats` (not logged as calls); any functional check runs against a local or Docker server, never production; never look up the invalid example 833286602 live.

## Entries

_(none yet — day one, 2026-09-05)_

## Outbound (things we said to others, so replies can be traced)

- 2026-09-05 · GitHub · nordio-ai/brreg-mcp-server#7 (feature request for 8 dropped brreg fields, author fmogensen) · commented with the field-for-field mapping to `CompanyReport`, offered `mapping.py`/`NORBIZ_SPEC.md` §3 under MIT, agreed with their eval finding and mentioned the roll-forward correction · https://github.com/nordio-ai/brreg-mcp-server/issues/7#issuecomment-5552901312 · watch for a reply.
- 2026-09-05 · awesome-mcp-servers PR #13631 · told the maintainers the Glama checks passed · no human reply yet.
- 2026-09-05 · Erhvervsstyrelsen · CVR access application, sagsnummer 177481 · reply due ~2026-09-23.
- 2026-09-05 · Weavio (Nodaro Technologies AB, Fortnox marketplace MCP vendor) · peer email drafted in Kim's Gmail to support@weavio.se asking what a Swedish user wants checked at supplier creation and whether they would compose a registry tool · **sent 2026-09-05 15:5xZ** from fargerod@gmail.com.
- 2026-09-05 · kode24 · pitch to ole@kode24.no (cc hei@kode24.no), VAT article inline · **sent 2026-09-05 15:5xZ** from fargerod@gmail.com · watch for a reply; next piece (deadlines) two days after they answer or publish.
