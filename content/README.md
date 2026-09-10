# content/ — worked examples

Eight articles. Every JSON and CSV block in them is real output from a running
server, and the exact command that produced it is in an HTML comment directly
above the block. Articles 01–05 have three versions each (`devto.md`,
`reddit.md`, `no.md`); 06 has three; 07 has two — see "Why 07 has no `no.md`"
below. **08 is the odd one and shows no register output at all** — its subject
is an eval report rather than a lookup, so it has a canonical `article.md`, a
`devto.md` with front matter, its own `README.md` recording where it was
published, and three hand-posted drafts instead of a `no.md`. See "Article 08"
below.

| Folder | Article | Tools shown |
|---|---|---|
| `01-vat-check/` | Check a Norwegian supplier is VAT-registered before you pay the invoice | `lookup_company`, `validate_company_id` |
| `02-deadlines/` | Every filing deadline a Norwegian AS faces this quarter | `company_deadlines` |
| `03-enrich-spreadsheet/` | Validate and enrich a spreadsheet of Norwegian org.nrs | `validate_company_id` + `lookup_company` |
| `04-add-your-country/` | Add your country's company registry in an afternoon | `list_countries`, the `Registry` ABC |
| `05-uk-companies-house/` | Check a UK supplier at Companies House from Claude Code — and the same tool works for Norway | `lookup_company`, `company_deadlines`, `validate_company_id` |
| `06-what-active-means/` | Three company registers, one word: what "active" actually means in Norway, the UK and Sweden | `lookup_company` across `NO`, `GB`, `SE` |
| `07-company-number-is-a-person/` | The company number that is also a person's national ID — and what it cost our logs | `validate_company_id`, `lookup_company` (`SE`) |
| `08-how-wrong-without-a-register/` | How wrong is a model about a company when it has no register to check? | none — the subject is `evals/reports/2026-09-10-accuracy.md` |

Each folder has `devto.md` (≤600 words, the long form), `reddit.md` (≤150
words, for r/mcp) and `no.md` (Norwegian, for kode24 and Norwegian dev
communities) — except `07-company-number-is-a-person/`, which has no `no.md`.
`03-enrich-spreadsheet/` also has `suppliers.csv`, `suppliers-enriched.csv`
and `enrich.py`.

Every article names `brreg`, `organisasjonsnummer` and `orgnr` in its title or
first paragraph (`KEYWORDS.md` §2); article 05 adds `Companies House`,
`company number` and `company registration number` in the same places
(`KEYWORDS.md` §GB), and articles 06 and 07 add `Bolagsverket` and
`organisationsnummer` (`KEYWORDS.md` §SE — note the Swedish `-tion-` beside the
Norwegian `-sjon-`; both spellings appear in both articles' opening paragraphs
on purpose). The articles are search surface, not only prose — do not edit
those terms out when copy-editing.

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

**Articles 06 and 07 are the first taken from the deployed service rather than
a local server**, and their comments are plain `curl` lines against
`https://api.foretak.dev` that anyone can re-run with no credentials at all.
That is deliberate: the `SE` blocks would otherwise need Bolagsverket OAuth 2
credentials on a local server, and a reader who can reproduce a block is worth
more than a convention. `content/call.py` reaches the same deployment with
`REGISTRY_MCP_URL=https://api.foretak.dev/mcp?src=article` if you want the MCP-side bytes
instead of the REST ones — they are identical documents.

Two blocks in those articles are *code*, not output: the `derive_status`
excerpt in 06 and the `id_may_be_personal` / `loggable_query` excerpts in 07.
They are quoted from `src/registry_mcp/registries/no/rules.py` and
`src/registry_mcp/core/registry.py` and must be re-checked against those files,
not re-run.

Re-run these before publishing if the server has changed. All three registers
are live data: Norwegian `employees` and addresses move, and every UK
`due_date` and `days_until` in article 05 was true on `today=2026-09-04` and
will drift as Companies House rolls each company's filing cycle forward. The
Swedish blocks are steadier — Sweden's two dates are computed from a statutory
period, so they move only when the assumed financial year rolls over — but a
Swedish `days_until` is still relative to the `today=` in the URL, so quote the
URL with it. Refresh the blocks rather than patching them by hand — and
re-check the prose around a `days_until` that has gone from negative to
positive, or the point of the paragraph is gone.

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
| 13 | 06 What "active" means | 06 What "active" means | 05 UK Companies House |
| 15 | 07 Company number is a person | 07 Company number is a person | — |
| 17 | — | — | 06 What "active" means |

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
- **Articles 6 and 7 are the Sweden pair, and neither is a release note.**
  6 is the one to lead with: it is about a modelling problem every register
  has, and Sweden is the evidence rather than the subject. 7 is the harder,
  narrower one — post it to a venue that cares about privacy engineering as
  much as about company data, and expect the comments to be about logging
  rather than about registers. Neither one claims usage numbers, and neither
  should acquire any: real traffic is a few hundred calls, most of them our
  own smoke tests.
- Replace `api.foretak.dev` and `github.com/foretak/registry-mcp` everywhere if
  the real domain or org differs, before the first post.

## Hand-posted drafts, outside the schedule

Four self-posts Kim posts by hand. Each carries its own one-line "where and
when to post" header, a title, a body and a first-comment block; the links go
in the comment, never the body.

| File | Venue | Angle |
|---|---|---|
| `reddit-r-mcp-post-01.md` | r/mcp | Launch post, live since 2026-09-05 |
| `reddit-r-claudeai-post.md` | r/ClaudeAI | "I asked Claude Code to check a supplier before paying an invoice" |
| `reddit-uk-developers-post.md` | a UK developer sub | Companies House only: the free key, and why `days_until` goes negative |
| `reddit-sweden-developers-post.md` | a Swedish or Nordic developer community | Bolagsverket only: the two statutory dates with the *förseningsavgift*, and the four things it cannot do |
| `08-…/show-hn.md` | Hacker News, Show HN | The tool is the submission, the accuracy number is the evidence |
| `08-…/linkedin.md` | LinkedIn, Kim's profile | Norwegian and English; pick one, the other goes in the first comment |
| `08-…/reddit.md` | r/LocalLLaMA (first choice) or r/ClaudeAI | Three lines on the eval design; links in the first comment |

`reddit-sweden-developers-post.md` is the Sweden counterpart of the UK draft
and is written in English. Its header says what to do if the venue is
Swedish-language: translate the body, and leave the statutory citations
(*aktiebolagslagen 7 kap. 10 §*, *årsredovisningslagen 8 kap. 6 §*,
*förseningsavgift*, *organisationsnummer*) exactly as they stand — they are
already correct Swedish, and a machine translation of a section symbol is how a
citation stops being one.

Deviations from the caps above, each on purpose:

- `01-vat-check/reddit.md` runs to 167 words, not 150. The two
  Skatteklagenemnda citations and the Rundskriv 15/2019 sentence cost about
  fifty words, and a citation outranks the cap.
- `06-what-active-means/` and `07-company-number-is-a-person/` run to 673 and
  710 words on dev.to and 214 and 215 on Reddit. Both are three-country pieces:
  the whole argument is the contrast between three registers, and cutting one
  register to hit the cap would leave a comparison with two sides. The dev.to
  numbers include their JSON and Python blocks, which is where most of the
  excess sits.
- `08-how-wrong-without-a-register/` runs to 1,036 words against a cap of 600,
  under a cap of 1,200 set for it specifically (T64 Part C). It carries two
  arms of an eval, four rates that are meaningless without the strict-rule
  caveat attached to each, and the limits paragraph that makes the number
  quotable at all — none of which shortens without becoming a claim the report
  does not support.

### Article 08 — the one with no output blocks

08 has no JSON or CSV block, so nothing in it is re-runnable and the
"reproducing the output blocks" section above does not apply. What replaces
that check is `content/08-how-wrong-without-a-register/README.md`: a table
mapping **every number in the article to the line of
`evals/reports/2026-09-10-accuracy.md` it came from**. Re-check the article
against that table rather than against a server, and if the report is ever
superseded, the article is stale even though every command in it still runs.

The one number that is *not* in the article is deliberate: the report's agent
arm dollar cost is an estimate rather than a measurement (`--agent` never
reads `response.usage`), so only the measured baseline figure is quoted, with
"the no-tools half" saying which half it is. Do not fill that gap in a
copy-edit.

08 is also the first article whose install line carries a `?src=` value
(`?src=devto`), and its three hand-posted drafts carry `?src=hn`,
`?src=linkedin` and `?src=reddit` — that is the T64 Part B attribution
parameter, harmless before Part B lands and useful the moment it does.

### Why 07 has no `no.md`

Article 07's subject does not exist in Norway. A Norwegian
enkeltpersonforetak has its own organisasjonsnummer, distinct from the owner's
fødselsnummer; Sweden is the case where the company number and the national ID
are the same string. A Norwegian version would spend its first paragraph
explaining that the problem does not apply to the reader. If a Norwegian venue
wants it, the angle to write is the contrast — *why Norway avoided this and
Sweden could not* — and that is a different article, not a translation.
