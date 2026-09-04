# content/ — worked examples

Four articles, three versions each. Every JSON and CSV block in them is real
output from a locally running server, and the exact command that produced it is
in an HTML comment directly above the block.

| Folder | Article | Tools shown |
|---|---|---|
| `01-vat-check/` | Check a Norwegian supplier is VAT-registered before you pay the invoice | `lookup_company`, `validate_company_id` |
| `02-deadlines/` | Every filing deadline a Norwegian AS faces this quarter | `company_deadlines` |
| `03-enrich-spreadsheet/` | Validate and enrich a spreadsheet of Norwegian org.nrs | `validate_company_id` + `lookup_company` |
| `04-add-your-country/` | Add your country's company registry in an afternoon | `list_countries`, the `Registry` ABC |

Each folder has `devto.md` (≤600 words, the long form), `reddit.md` (≤150
words, for r/mcp) and `no.md` (Norwegian, for kode24 and Norwegian dev
communities). `03-enrich-spreadsheet/` also has `suppliers.csv`,
`suppliers-enriched.csv` and `enrich.py`.

Every article names `brreg`, `organisasjonsnummer` and `orgnr` in its title or
first paragraph (`KEYWORDS.md` §2). The articles are search surface, not only
prose — do not edit those terms out when copy-editing.

## Reproducing the output blocks

```bash
REGISTRY_MCP_CACHE_DISABLED=1 uv run uvicorn registry_mcp.api.main:app --port 8091 &
uv run python content/call.py lookup_company '{"id": "833285602"}'
```

`content/call.py` calls one MCP tool over Streamable HTTP and prints the JSON —
the same shape an agent sees, including the `{"error": {...}}` envelope on
failure. The `XX` blocks in `04-add-your-country/` need
`REGISTRY_MCP_INCLUDE_STUBS=1` on the server as well; their comments say so.

Re-run these before publishing if the server has changed. Enhetsregisteret is
live data: `employees` and addresses move, so refresh the blocks rather than
patching them by hand.

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

Rules for whoever posts:

- **Never all at once.** Four posts in one day reads as a launch dump and burns
  the r/mcp audience for the whole week.
- **Reddit is a comment, not a crosspost.** Post the `reddit.md` text as a
  self-post; put the dev.to link in the first comment, not the body.
- **Reply to every comment within 24 h.** The comments are the point — they are
  the `FEEDBACK.md` input the Phase 4 decision gate reads.
- **Article 4 is the recruiting one.** Post it last, when the other three have
  shown the thing works, and pin the "open an issue with your country code"
  line.
- Replace `api.foretak.dev` and `github.com/foretak/registry-mcp` everywhere if
  the real domain or org differs, before the first post.
