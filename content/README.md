# content/ — worked examples

Five articles, three versions each. Every JSON and CSV block in them is real
output from a locally running server, and the exact command that produced it is
in an HTML comment directly above the block.

| Folder | Article | Tools shown |
|---|---|---|
| `01-vat-check/` | Check a Norwegian supplier is VAT-registered before you pay the invoice | `lookup_company`, `validate_company_id` |
| `02-deadlines/` | Every filing deadline a Norwegian AS faces this quarter | `company_deadlines` |
| `03-enrich-spreadsheet/` | Validate and enrich a spreadsheet of Norwegian org.nrs | `validate_company_id` + `lookup_company` |
| `04-add-your-country/` | Add your country's company registry in an afternoon | `list_countries`, the `Registry` ABC |
| `05-uk-companies-house/` | Check a UK supplier at Companies House from Claude Code — and the same tool works for Norway | `lookup_company`, `company_deadlines`, `validate_company_id` |

Each folder has `devto.md` (≤600 words, the long form), `reddit.md` (≤150
words, for r/mcp) and `no.md` (Norwegian, for kode24 and Norwegian dev
communities). `03-enrich-spreadsheet/` also has `suppliers.csv`,
`suppliers-enriched.csv` and `enrich.py`.

Every article names `brreg`, `organisasjonsnummer` and `orgnr` in its title or
first paragraph (`KEYWORDS.md` §2); article 05 adds `Companies House`,
`company number` and `company registration number` in the same places
(`KEYWORDS.md` §GB). The articles are search surface, not only prose — do not
edit those terms out when copy-editing.

## Reproducing the output blocks

```bash
REGISTRY_MCP_CACHE_DISABLED=1 uv run uvicorn registry_mcp.api.main:app --port 8091 &
uv run python content/call.py lookup_company '{"id": "833285602"}'
```

`content/call.py` calls one MCP tool over Streamable HTTP and prints the JSON —
the same shape an agent sees, including the `{"error": {...}}` envelope on
failure. The `XX` blocks in `04-add-your-country/` need
`REGISTRY_MCP_INCLUDE_STUBS=1` on the server as well; their comments say so.
The `GB` blocks in `05-uk-companies-house/` need a Companies House key on the
server: add `COMPANIES_HOUSE_API_KEY=…` to the same command line. Never put the
key in a `content/` file, a shell history you commit, or an article.

Re-run these before publishing if the server has changed. Both registers are
live data: Norwegian `employees` and addresses move, and every UK `due_date`
and `days_until` in article 05 was true on `today=2026-09-04` and will drift as
Companies House rolls each company's filing cycle forward. Refresh the blocks
rather than patching them by hand — and re-check the prose around a
`days_until` that has gone from negative to positive, or the point of the
paragraph is gone.

## Posting schedule

One article every two days. dev.to first, Reddit the same day, kode24 two days
later — so the kode24 post of article *n* goes out with the dev.to post of
article *n+1*, and the run never has a silent day after day 1.

| Day | dev.to (`devto.md`) | r/mcp (`reddit.md`) | kode24 (`no.md`) |
|---|---|---|---|
| 1 | 01 VAT check | 01 VAT check | — |
| 3 | 02 Deadlines | 02 Deadlines | 01 VAT check |
| 5 | 03 Enrich spreadsheet | 03 Enrich spreadsheet | 02 Deadlines |
| 7 | 04 Add your country | 04 Add your country | 03 Enrich spreadsheet |
| 9 | — | — | 04 Add your country |
| 11 | 05 UK Companies House | 05 UK Companies House | — |
| 13 | — | — | 05 UK Companies House |

Rules for whoever posts:

- **Never all at once.** Four posts in one day reads as a launch dump and burns
  the r/mcp audience for the whole week.
- **Reddit is a comment, not a crosspost.** Post the `reddit.md` text as a
  self-post; put the dev.to link in the first comment, not the body.
- **Reply to every comment within 24 h.** The comments are the point — they are
  the `FEEDBACK.md` input the Phase 4 decision gate reads.
- **Article 4 is the recruiting one.** Post it after the first three have shown
  the thing works, and pin the "open an issue with your country code" line.
- **Article 5 is the proof.** It ships two days after article 4 on purpose: it
  is the country-two evidence for article 4's claim that a country is one
  folder, and it is the first article whose audience is not Norwegian. Post it
  to r/mcp as usual, and consider a UK-developer venue as well.
- Replace `api.foretak.dev` and `github.com/foretak/registry-mcp` everywhere if
  the real domain or org differs, before the first post.

## Hand-posted drafts, outside the schedule

Three self-posts Kim posts by hand. Each carries its own one-line "where and
when to post" header, a title, a body and a first-comment block; the links go
in the comment, never the body.

| File | Venue | Angle |
|---|---|---|
| `reddit-r-mcp-post-01.md` | r/mcp | Launch post, live since 2026-09-05 |
| `reddit-r-claudeai-post.md` | r/ClaudeAI | "I asked Claude Code to check a supplier before paying an invoice" |
| `reddit-uk-developers-post.md` | a UK developer sub | Companies House only: the free key, and why `days_until` goes negative |

One deviation from the caps above: `01-vat-check/reddit.md` runs to 167 words,
not 150. The two Skatteklagenemnda citations and the Rundskriv 15/2019 sentence
cost about fifty words, and a citation outranks the cap.
