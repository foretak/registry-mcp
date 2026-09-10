# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning applies to the response shapes and tool contract described in
[`DECISIONS.md`](DECISIONS.md) — the five tools and their response shapes are
frozen as of `0.2.0`.

## [Unreleased]

### Added

- **`real_asks` in `GET /v1/stats` and a new "Real asks (what the gate
  counts)" row atop the dashboard, above "Total calls"** (`tasks/T65.md`,
  `~/mcp-growth/DECISION-GATE.md`'s day-45 gate). Raw call counts include
  directory scanners, crawlers, our own smoke tests and playground clicks
  against our own documented examples — none of that is evidence anyone
  asked this service anything. `core/stats.py::summary()` now also reports,
  from the same `calls` table: `calls` and `distinct_user_agents` (each
  all-time and last-7-days), `mcp_sessions_non_bot` (distinct non-bot MCP
  user agents, last 7 days), `by_source_named` (T64's `by_source` minus the
  "no src" bucket), `last` (the single most recent real ask, its query
  re-redacted through `core.registry.loggable_query` so a Swedish
  identifier is never shown), and `ceiling_hitters` (the new M4 reading,
  amendment A2: user agents at or above 50 calls in any one minute in the
  last 7 days — near the 60/minute REST limit). A "real ask" excludes (1)
  a fixed set of our own documented example queries collected from
  `README.md`, `static/llms-full.txt` and `evals/cases.json`
  (`923609016`, `00445790`, `445790`, `5560160680`, `equinor`, `tesco`,
  `833285602`, `833286602`, `test` — matched case-insensitively) and (2)
  a fixed list of known own/bot user agents (`SaSame-MCP-Audit/0.1` and
  `~/mcp-growth/BASELINE-2026-09-07.md`'s untruncated own-traffic
  strings) plus `core/ua_classify.py`'s new `bot` label. `ua_classify.py`
  gains that label — crawlers/monitors such as Googlebot or the bare
  `Mozilla/5.0 (compatible)` directory monitor, checked before `browser` —
  because before this there was no way to tell one from a real browser by
  label alone. Two operation-shaped refinements from review: `list_countries`
  (the bare connect probe every client, and every scanner, makes) is never a
  real ask on either surface; and, since D-040 stores `query=NULL` for every
  Swedish call regardless of surface, a Swedish `lookup_company` /
  `company_deadlines` / `validate_company_id` (`search_company` too, if it
  ever logs — currently `not_implemented` for Sweden) row with `query=NULL`
  now counts as a real ask for a real user agent, on REST as much as MCP —
  "no query" there means "withheld", not "nothing was asked". A non-Swedish
  `validate_company_id` with `query=NULL`, or a documented-example query on
  any country, still counts zero.
- **`?src=` on the REST routes and on `/mcp`, logged as a new `source`
  column on the `calls` table — "calls by channel"** (`tasks/T64.md`).
  Free text, sanitised to `[a-z0-9_-]` and truncated to 32 characters
  (`core/log.py::sanitize_source`); an existing database is migrated in
  place (`ALTER TABLE ... ADD COLUMN`, guarded by `PRAGMA table_info`), no
  fresh database required. Surfaced in `GET /v1/stats` and the dashboard
  (`GET /v1/stats/dashboard`) as `by_source`, one row per tag plus a "no
  src" bucket for everything else — the same treatment `by_country`
  already gives an unresolved country. `query` (D-040) is untouched: `src`
  is a separate column with its own sanitiser. Verified locally that a
  Streamable HTTP client connecting to `/mcp?src=...` still completes
  `initialize` and `tools/list` — FastMCP ignores the extra query
  parameter — so `src` is read on both surfaces, not REST only. Our own
  install lines now carry a tag: `?src=readme` (`README.md`), `?src=llms`
  (`static/llms.txt`, `static/llms-full.txt`), `?src=docs`
  (`docs/clients.md`), `?src=plugin` (the Claude Code plugin's `.mcp.json`
  and skill), `?src=article` (`content/`) — never in `server.json`, which
  the MCP registry validates as a plain endpoint.

## [0.4.2] — 2026-09-10

The `rules last reviewed` stamp (products round, `~/mcp-growth/products/00-SYNTHESIS.md` §4.1 S1).

### Added

- **`rules_last_reviewed` on `DeadlineReport`, and atop every
  `registry://rules/{country}` resource** — the date each country's deadline
  statutes and day-count arithmetic were last checked against the law, so an
  agent can tell a deadline computed long after that date from a fresh one
  (`tasks/T62.md`, `~/mcp-growth/products/00-SYNTHESIS.md` §4.1 S1).

## [0.4.1] — 2026-09-09

The token diet (`DECISIONS.md` D-048).

### Changed

- **The tool surface's fixed context cost** (`DECISIONS.md` D-048): 10,124 →
  ~7,400 tokens of fixed context (7 tools + `instructions`, measured with
  `count_tokens` on `claude-opus-5`), −26%. Attachments are now explained
  once, in the `include` argument, not twice; the D-007 error contract is
  written once, in `instructions`, not in four places; country prose is
  written once per fact rather than repeated across four tools' docstrings;
  `search`/`fetch` are unchanged in behaviour and stay visible to every
  client; no response byte changed.

## [0.4.0] — 2026-09-09

Depth per country. Seven `include=[...]` attachments on `lookup_company` — `filings`
(all three countries), `charges` and `insolvency` (United Kingdom), `financials`
(Norway from Regnskapsregisteret's key figures, Sweden from the filed K2 iXBRL),
`lei` and `parents` (Norway and the United Kingdom, from GLEIF) and `peppol`
(Norway, the SML/SMP walk ahead of the 2027 e-invoicing duty) — plus
`include=["filings"]` on `company_deadlines`, and the privacy policy and terms
naming all three countries. Reviewed under mutation before shipping (`REVIEW.md`
§ "Depth track"). **Deployed to the hosted service at `api.foretak.dev` on
2026-09-09** (Railway deployment `846084c1`, smoked against the live registers)
and published to PyPI, npm and the MCP registry with the `v0.4.0` tag.

### Added

- **`SourceRef` and `include=[...]`** on `lookup_company` (MCP) and `GET
  /v1/{country}/company/{id}` (REST) — every attachment is a second,
  independent fetch with its own provenance (`source`, `source_url`,
  `license`, `fetched_at`, `cached`) rather than reusing the base report's,
  assembled in one place: `Registry.lookup_with` (D-026(c), D-042, `10f46f2`).
- **`CountryInfo.supported_includes`**, a sorted list on every `GET
  /v1/countries` / `list_countries` row, so a caller can see what more a
  country answers for before guessing an `include` value, in one round trip
  and no upstream request (D-042(d), `10f46f2`).
- **`include=["charges"]` for `GB`** — registered charges (mortgages and
  other security interests against the company), with its own `ChargeBlock`
  (D-042, `3ecc369`).
- **`include=["filings"]` for `GB`, `NO` and `SE`, and `include=["insolvency"]`
  for `GB`** — one canonical `FilingHistory` shared by all three countries
  (Companies House the whole filing history, Bolagsverket filed annual
  reports, Regnskapsregisteret filed annual accounts) and one
  `InsolvencyBlock` for Britain's winding-up and administration proceedings
  (D-044, `e03a518`).
- **`CompanyReport.charges`, `.filings` and `.insolvency`** — each `null`
  unless its name was passed in `include=[...]`, and still `null` if that
  fetch failed (`notes` names which attachment and why) (`3ecc369`,
  `e03a518`).
- Prompts **`counterparty_check`** and **`register_coverage`** — each names
  the job an agent actually has rather than the architecture behind it, and
  states this service's honest limits in its own output (`cf5f13f`).
- **`include=["financials"]` for `NO`** — the register's own key figures
  (turnover, operating result, profit, balance sheet totals, equity,
  liabilities) for the latest filed accounting period, each figure beside
  its own `currency`; a `None` figure inside a present block means the
  company did not report that line, an absent block means the country does
  not publish figures. One fetch serves both this and `filings` for Norway
  — one `SourceRef`, not two (Sweden's own `financials` line below shares
  only its discovery fetch with `filings`, not its `SourceRef` — see
  D-047(f)). No derived ratio, indicator or verdict exists on this block
  (D-043, `067a1cc`).
- **`include=["financials"]` for `SE`** — the same block, out of the
  entity's own filed annual report instead of an open key-figures feed:
  the K2 (and, on the taxonomy evidence available, K3) inline-XBRL document
  Bolagsverket's document API serves, read out via a pure extractor that
  reads only `ix:nonFraction` and never `ix:nonNumeric`. Shares the
  `/dokumentlista` fetch with `filings`, then makes one further `/dokument`
  request for the most recently filed report only; figures are cached 30
  days on the immutable `dokumentId`, and the document itself is parsed and
  discarded — never cached, logged or written to disk. `currency` comes
  from the document's own unit, never from Bolagsverket's renamed,
  re-typed currency concept. The block is entity accounts, never a group,
  as a fact about the K2 channel; a K3 filing carries a caveat that no live
  K3 document had been read when this shipped. A company whose document
  list is empty gets **no** `financials` block and a report-level note
  saying so — deliberately unlike `filings`, which returns a present block
  with `documents: []` for the identical wire state (D-047(f),(g);
  `076faa7`, `af94220`, `edbd105`).
- **The `financials` cache-TTL row, `(30 days, 1 hour)`.** The per-kind
  table in `core/cache.py` is now `lei`, `parents`, `peppol`, `financials`
  (`03571eb`, `b5fc6a9`).
- **`include=["lei"]` for `GB` and `NO`** — the Legal Entity Identifier
  GLEIF, the Global LEI Foundation, publishes for the entity, CC0-licensed
  and keyless, on a new `Registry.universal_includes` mechanism every
  country declares by default; `SE` is excluded and `include=["lei"]` for
  `SE` is `bad_request`, because the identifier would leave for a
  third-party host in a URL and a Swedish identifier can be a natural
  person's own. A present block with `lei: null` means GLEIF holds none
  for this entity (D-045(e), `e6e7ad1`).
- **A per-kind cache TTL table** in `core/cache.py`, keyed on the existing
  cache key's own kind segment so no existing caller migrates; `lei` is the
  first row, `(7 days, 24 hours)` (D-045(e), `e6e7ad1`).
- **`include=["parents"]` for `GB` and `NO`** (the same countries as `lei`,
  for the same reason; `SE` is `bad_request`) — the direct and ultimate
  corporate parent GLEIF's Level 2 "who owns whom" data discloses, or the
  entity's own stated reason from a closed vocabulary such as
  `NATURAL_PERSONS` when it discloses none. Read that reason as a category
  word, never a name: it is the filer's own unverified claim, and it is
  applied inconsistently between filers for materially identical situations
  (D-047(a), `6905db3`).
- **`include=["peppol"]` for `NO` only** — whether the entity can receive an
  e-invoice over the Peppol network, resolved live through the Peppol
  SML/SMP walk with the Peppol Directory as a positive-only fallback, ahead
  of Norway's 1 January 2027 e-invoicing duty. `registered` earns `false`
  only from an authoritative NXDOMAIN or SMP 404; everything else — a
  resolver failure, an SMP error, or a Directory miss, which both Peppol
  operators say in writing does not mean the entity is unreachable — is
  `null`, never `false` (D-046, `0748bfa`, `f5372c5`, `64b5366`).
- **`include=["filings"]` on `company_deadlines`** (MCP and REST), and
  Sweden's second deadline rung: when the caller asks for it, Bolagsverket's
  own filed-report year end replaces the 31 December assumption behind both
  Swedish deadlines. `company_deadlines` accepts a narrower `include` set
  than `lookup_company` — only a value that can change a computed date,
  `filings` alone today — and a value outside it (`financials` included) is
  `bad_request` naming this operation's own allowed set (D-041, D-045(g),
  `5c71bc8`).
- **`registry://rules/{country}` for Norway gains an "Electronic invoicing
  (2027) and electronic bookkeeping (2030)" section** — both statutory
  dates, the ELMA-scoping sentence quoted from the statute, and the two
  exemptions (turnover under NOK 50,000; regulated financial institutions).
  States explicitly that neither date produces a computed `Deadline`,
  because neither binds on a fact this register publishes (D-029(f),
  `3e550f9`).
- **The privacy policy and terms are served at `/legal/privacy` and
  `/legal/terms`**, and the dashboard gains a breakdown by operation, the
  cache hit rate, p50/p95 latency, freshness and a per-country call count
  (`50a243e`, `b2b92b0`).

### Changed

- **`GB` company reports no longer carry `registers["charges"]`.** Companies
  House's own `has_charges` flag is wrong — `false` for TESCO PLC while the
  charges endpoint lists nine, two still outstanding — so the key is
  omitted rather than asserting a boolean this service cannot stand behind.
  This is a **removed key on the wire**; `include=["charges"]` is the real
  answer, and it returns a present, empty block for a company that
  genuinely has none (`beb287f`).
- **`register_coverage`'s worked example** no longer calls
  `employees_reported: false` an entity-level gap for every country: it is
  a *structural* silence for `GB` and `SE`, whose registers publish no
  employee count for anybody, and an *entity-level* gap only for `NO`,
  whose register does publish one and simply has none for that company
  (`beb287f`).
- **`ChargeBlock.outstanding_count` is removed; four fields are added.**
  D-045(a) struck it — it was `total_count - satisfied_count`, our own
  arithmetic wearing a register figure's name, and on a shared model it
  would have meant two different things depending on which country filled
  it (D-011). Added in its place: `ChargeBlock.part_satisfied_count` (the
  register's own whole-company figure, `0` in every observed payload, not
  derived); `Charge.contains_fixed_charge` and
  `Charge.contains_negative_pledge` beside the existing
  `contains_floating_charge` (Companies House emits each key only when
  `True`; absence maps to `None`, never `False`); and
  `Charge.assets_charged_type` / `Charge.obligations_secured_type`, the
  register's own category token for each free-text field — on 19 of 19
  observed items, `obligations_secured`'s own token was `amount-secured`,
  never `obligations-secured`. `ChargeBlock.notes` also gains one
  unconditional sentence, beside the existing truncation note, whenever a
  page carries either free-text field: the text is the register's own
  prose, relayed verbatim and not parsed, and may name a natural person
  (D-045(a), `7ce3979`).
- **`instructions` (the string every MCP client puts in front of the model)
  gains the payment-fraud caveat** — this is not sanctions, PEP or
  adverse-media screening, does not verify bank account details, and is
  not a defence against payment fraud — so a caller that only reads
  `instructions` and never renders the `counterparty_check` prompt still
  sees it (T45, `5e54a54`).
- **The scope note leads every `SE` and `GB` `filings` block**, before any
  other caveat (T40, `7143f9f`); the Swedish `filings` scope note and empty
  note now state the channel's population precisely — digitally submitted
  aktiebolag annual reports under K2 or K3, from 2020 onwards, so an IFRS
  preparer's empty document list is a stated limit of the channel rather
  than an unexplained gap (T44 `5c71bc8`, T55 `edbd105`).
- **`dnspython>=2.7` (ISC licence) is a new runtime dependency**, bought by
  the Peppol SML NAPTR walk (D-046, `919b01d`).
- **The shared GLEIF and Peppol `httpx.AsyncClient`s are closed at
  shutdown.** Neither was reached by the existing per-country shutdown
  loop, so both outlived the request that was supposed to end them (T46
  `74ce037`, T43 `64b5366`).
- **The privacy policy and terms name all three countries and the privacy
  page carries an effective date.** `legal/privacy.md` said "Norway … and
  the United Kingdom", contradicted itself about Sweden three paragraphs
  later, omitted Bolagsverket and GLEIF from *what we send to third
  parties*, and opened with a draft preamble on a page that was already
  published; `legal/terms.md` had the same two-country gap. Fixed, and the
  mcpb manifest now declares the privacy policy URL too (T46 `ff2b89b`,
  `2520a2d`).

### Fixed

- The dashboard's 30-day calls-per-day chart no longer opens scrolled to
  its empty half on a narrow screen — it carried a fixed pixel width inside
  an `overflow-x` wrapper, so a phone opened it scrolled to the oldest,
  empty days while every real bar sat off-screen to the right. Sized by
  `viewBox` at `width: 100%` (capped 900px) instead (`13d5e4a`).
- **The Swedish "does not publish the financial year" sentence is retired
  from every surface.** It was already false once `include=["filings"]`
  carried Bolagsverket's own filed year end, and false again once
  `include=["financials"]` shipped (T44 `5c71bc8`, T46 `907aafc`).
- **The usage log no longer counts an internal error as a success.**
  `_CallOutcome.ok` is now `False` on any exception other than a
  `RegistryError` the caller is meant to see, not only on the ones this
  service raises deliberately (T45, `5e54a54`).
- **A country module missing a declared `include` attachment method now
  fails as a `RuntimeError` before any network I/O for it, not after.** A
  `supported_includes` entry with no matching method previously escaped as
  a bare `AttributeError`, or hid behind a plausible-looking failed-fetch
  note, instead of failing loudly as the country-module bug it is
  (`REVIEW.md` § S-series finding 6; T42, `e6e7ad1`).
- **A concurrency test for the attachment machinery no longer races on
  wall-clock time.** It asserted an exact interleaving produced by two
  hard-coded sleep durations and failed once under machine load; it now
  proves the two attachments were in flight together by rendezvous instead
  (`5bf0134`).
- **`legal/privacy` and `legal/terms` 404'd in the deployed container.**
  The routes existed in code and passed every local test, but the runtime
  image's `.dockerignore` excluded markdown and `legal/` was never copied
  in, so the pages were unreachable in production from the moment they
  were added until this was found. A test now asserts the runtime image
  receives every directory the application reads at request time
  (`0d20df9`).
- **The server card published `"resources": []` while the server serves
  three** (`registry://rules/{GB,NO,SE}`); `scripts/regen_server_card.py`
  now writes the resource list and the card drift test pins it
  (`REVIEW.md` § Depth track, finding 7; `3f72ec2`).
- **The `country` and `id` argument descriptions on `lookup_company`,
  `company_deadlines` and `validate_company_id` named two of three
  countries.** Sweden's clause is added to both and `SE` to the examples
  (finding 8; `24575c3`).

## [0.3.0] — 2026-09-07

Third country, and the first two items off the core roadmap.

This section gathers everything that accumulated under *Unreleased* since 0.2.0 and
shipped together on 2026-09-07 — which is why it carries several `### Added` blocks,
each labelled with the work it came from. **Deployed to the hosted service at
`api.foretak.dev`. Not published to PyPI, npm or the MCP registry:** no tag was pushed,
so those still serve 0.2.0 and `packages/brreg-mcp` pins a `registry-mcp==0.3.0` that
exists only in this repository until one is.

### Added

- **Sweden (`SE`), Bolagsverket's free "värdefulla datamängder" API.** Lookup by
  organisationsnummer (ten digits, or twelve for a sole trader), shape-only validation,
  and filing deadlines from aktiebolagslagen 7 kap. 10 § and årsredovisningslagen
  8 kap. 6 §. `search_company` answers `not_implemented`: the API has no name index.
  Requires `BOLAGSVERKET_CLIENT_ID` and `BOLAGSVERKET_CLIENT_SECRET`.
- **`euid` and `advertising_protected` on every company report** (D-026). Both default to
  `null` and are present on every country. Sweden fills the advertising flag from
  Statistics Sweden's *reklamspärr*; a `true` value always carries an explanatory note.

### Changed

- **A country may declare that its identifiers can be a natural person's** (D-040). A
  Swedish sole trader's organisationsnummer is their personnummer, so for such countries
  the usage log now stores no identifier at all. The uvicorn access log is off, the
  unhandled-exception log records the route template rather than the request path, and
  cache failures log only a key prefix. `legal/privacy.md` says so.

### Fixed

- Swedish industry codes no longer include Statistics Sweden's blank padding slots.

Legibility fixes (T17): no `core/` change, no response-shape change.

### Added (tool legibility, T17)
- Real `outputSchema` on every MCP tool, generated from the same pydantic
  model the tool already returns (`CompanyReport`, `SearchResult`,
  `DeadlineReport`, `ValidationResult`, `CountriesResponse`), in place of the
  previous degenerate `{"type": "object", "additionalProperties": true}`.
- `ToolAnnotations` (`title`, `readOnlyHint`, `destructiveHint`,
  `idempotentHint`, `openWorldHint`) on all five MCP tools — all five are
  read-only, non-destructive and idempotent; `lookup_company`,
  `search_company` and `company_deadlines` are `openWorldHint: true` (they
  call a national register), `validate_company_id` and `list_countries` are
  `openWorldHint: false` (no network call).
- Parameter `description`s and `examples` on every MCP tool input.
- `GET /.well-known/mcp/server-card.json` and `GET /robots.txt`.
- An `X-Request-ID` response header on every REST response — echoes an
  incoming `X-Request-ID` if the caller sent one, otherwise a generated
  UUID4.
- `CHANGELOG.md` and `SECURITY.md`.

### Changed (evals)
- Agent-mode harness: generic fixture-derived mocks for every registry route
  (a real gap is reported as `GAP`, never as a model failure), structured
  checks against the tool results the model actually received, date and
  wording variants in answer checks, a negation-aware fabrication gate, and
  `today` wildcards where the prompt gives no date. Real-model run 2:
  23 pass / 1 fail / 2 live-only skips (run 1: 13 / 11 / 2). The remaining
  failure, E19, is a genuine finding: asked whether Tesco PLC is VAT
  registered, the model answered from general knowledge without calling
  `lookup_company`.

### Added (evening, distribution)
- A "Try it" playground on the homepage: validate → lookup + deadlines, or
  search, with the exact request URL shown and the install lines and badges
  under the result. Nothing fires on page load.
- A self-hosted Claude Code plugin marketplace (`.claude-plugin/`,
  `plugins/registry-mcp/`): `claude plugin marketplace add foretak/registry-mcp`
  then `claude plugin install registry-mcp@foretak`.
- `mcpb/manifest.json`, a Claude Desktop extension manifest that launches
  `uvx registry-mcp` (build with `npx @anthropic-ai/mcpb pack mcpb`).
- `docs/clients.md`: per-client install steps (Claude Code, Claude Desktop,
  Cursor, VS Code, Cline, ChatGPT, plain stdio JSON).
- `legal/privacy.md`: a privacy policy for the hosted service (draft, pending
  the operator's review).

### Added (later the same day)
- Concrete `registry://rules/NO` and `registry://rules/GB` resources so the
  per-country rules document appears in `resources/list` (the template still
  works).
- A `notes` entry on Norwegian sole proprietorships (ENK) saying the record
  contains a natural person's published data.
- "Does not screen" statements (no sanctions/PEP/adverse-media screening, no
  bank-account verification) in the README, `llms-full.txt`, the terms and the
  `lookup_company` tool description.
- A 400×400 icon at `GET /icon.png`, referenced from the homepage JSON-LD and
  `server.json`'s `icons`.
- `evals/`: a 26-case agent eval harness — golden mode (no model; offline
  cases run in CI) and an opt-in agent mode driven by the Anthropic SDK
  (`uv run --group eval python evals/run.py --agent`).
- README section "Why an agent checks a company" and `llms-full.txt` §9: the
  regulatory reasons (Finanstilsynet Rundskriv 15/2019, Norway B2B
  e-invoicing 2027, EU AMLR 2027) and the honest limits.

### Added (ChatGPT connector aliases, D-031)
- `search(query)` and `fetch(id)`, two read-only MCP tools implementing
  OpenAI's connector contract for ChatGPT deep research and company
  knowledge (`src/registry_mcp/mcp/connector.py`) — the tool count becomes
  "five registry tools plus two connector aliases", not a sixth registry
  tool. `search` takes one free-text query — a company name, a national
  identifier, or a name plus a country — derives the country from
  `list_registries()` with no synonym table, short-circuits to one
  `lookup_company` when the query is a valid identifier, otherwise fans out
  to a name search across every live registry, and returns
  `{"results": [{"id", "title", "url"}]}`, `id` always
  `"{COUNTRY}:{identifier}"`. Zero hits returns one row per live country
  pointing at its rules document instead of an empty result. `fetch(id)`
  parses that same `"{COUNTRY}:{identifier}"` form (or `"rules:{COUNTRY}"`,
  or derives the country when there is no colon), does the one
  `lookup_company` + `company_deadlines` already do internally, and returns
  a Markdown rendering of both — including the statutory filing deadlines,
  which ChatGPT's deep research mode cannot otherwise reach — with the full
  `CompanyReport`/`DeadlineReport` JSON in `metadata`. Both tools are
  read-only/idempotent/open-world annotated like the five registry tools,
  add no `core/` model, no `Registry` method and no REST route, and the
  five registry tools' names, schemas, annotations and wire bytes are
  unchanged. README "Add to ChatGPT"/"Add to Claude Desktop" sections and
  `docs/clients.md`'s ChatGPT entry document the connector URL.

### Added (third country, Sweden — how it was built)
- Sweden (`SE`): Bolagsverket's free "värdefulla datamängder" API as a third
  registry module (`registries/se/`), one folder plus one import line, no
  change to `core/`. The API needs OAuth 2 client
  credentials Bolagsverket issues on request; those arrived on 2026-09-07 and are
  set on the hosted deployment. Without them every
  `SE` call returns `upstream_error` with a hint naming both variables
  (D-037). `SE` is listed by `GET /v1/countries` and `list_countries` with
  `requires_api_key: true` so that is discoverable before the call.
- **No name search for Sweden.** Bolagsverket's free API has four operations
  and none of them takes a company name, so `search_company` for `SE` raises
  `not_implemented` (HTTP 501) with a hint naming the alternatives: look up
  by identifier, or use Bolagsverket's bulk downloadable files. This is a
  fact about the register, not a gap — `lookup_company`,
  `company_deadlines` and `validate_company_id` all answer for `SE`, and the
  ChatGPT `search` alias drops Sweden from its fan-out unchanged.
- Swedish identifier validation is **shape-only**: ten digits for an
  organisationsnummer, or twelve for the personnummer a sole trader is
  looked up by (`YYYYMMDDNNNN`); `556016-0680`, `5560160680` and
  `SE556016068001` all normalise to the same ten digits. A check digit
  exists and Bolagsverket enforces it server-side, but no primary source for
  the algorithm could be found, so this module does not reject on it — the
  modulus-10 result is reported as a caveat on an otherwise valid result
  (D-021/D-032) rather than making a real company unfetchable.
- Two computed Swedish deadlines for an `AB` or `EK`, both under the
  calendar-year assumption the free dataset forces (it does not publish a
  company's financial year): `general_meeting` — the ordinary general
  meeting within six months of the financial year end, aktiebolagslagen
  7 kap. 10 § — and `annual_accounts` — seven months, where
  årsredovisningslagen 8 kap. 6 §'s förseningsavgift begins. The statute
  that actually governs filing, ÅRL 8 kap. 3 §, is one month after the
  meeting adopted the accounts and is not computable from published data, so
  `applies_because` states all three steps and says the company's own
  deadline may be earlier. Swedish dates do not roll forward off a weekend
  or holiday: no rule saying they do could be sourced.
- A personal-data note on a Swedish sole trader (`enskild näringsidkare`),
  mirroring Norway's ENK note and going further because the case is worse —
  the identifier *is* the proprietor's personnummer, which is why
  Bolagsverket's own read operations are POSTs rather than GETs (D-039).

### Added (R-2: `euid` and `advertising_protected`)
- `CompanyReport` gains two nullable keys, both additive and both `null` by
  default — no existing key changes shape or meaning: `euid` (the EU-wide
  identifier some member-state registers publish, e.g. Finland; carried
  verbatim, never constructed, and never the LEI) and `advertising_protected`
  (`true`/`false`/`null` — whether the register marks this entity as
  protected against direct-marketing use; `null`, the default, means the
  register publishes no such flag at all). A model validator rejects any
  report with `advertising_protected=true` unless `notes` carries a matching
  "direct marketing" sentence (D-026(a),(b)). Sweden's `reklamsparr` now sets
  `advertising_protected` directly, alongside its existing `notes` sentence,
  instead of the field going unset (D-036).

### Fixed
- Norwegian `annual_accounts` and `general_meeting` deadlines no longer roll
  forward off a weekend or holiday: no provision grants that, and
  regnskapsloven § 8-3(1) charges the late fee unless the accounts are sent
  before 1 August, so the rolled date was later than lawful (R01, D-022).
  The other four Norwegian deadlines keep their roll-forward and now cite
  the provision it comes from in `applies_because`; the calendar-year
  assumption note names the 1 February rule and the Regnskapsregisteret
  route (D-023). Worked examples in `content/02-deadlines/` and
  `llms-full.txt` regenerated.

### Changed
- README: rewrote the first screen — what the service is in one sentence,
  the Claude Code install lines, three evidence-backed differentiators
  (computed deadlines with `applies_because`, 24-hour freshness against the
  documented incumbent figure, five tools against a client's tool budget), a
  short security summary, and one-click install badges for VS Code, VS Code
  Insiders and Cursor.

## [0.2.0] - 2026-09-04

Second country: the United Kingdom.

### Added
- United Kingdom (`GB`): Companies House lookup, search, deadlines (annual
  accounts, confirmation statement) and identifier validation — a second
  registry module (`registries/gb/`) added as one folder plus one import
  line, with no change to `core/`.
- `CompanyReport.published_deadlines`, carrying the filing dates Companies
  House publishes for an entity itself, so the register's own figure can win
  over a computed one without `Registry.deadlines` doing any I/O (D-018).
- `Registry.requires_api_key` / `api_key_env`, surfaced by `GET
  /v1/countries` and the `list_countries` tool, so a caller can tell in
  advance that a country needs a credential this deployment might not have
  configured (D-017).
- `Registry.id_caveat`: a well-formed but unrecognised identifier prefix
  stays `valid: true` with an honest caveat in `reason`, instead of a false
  rejection that a new Companies House prefix would otherwise cause (D-021).
- A fifth worked example, on Companies House, in `content/`.

### Changed
- `SearchResult.hits` is now sorted by `confidence` descending for every
  country, enforced once by the model rather than by each registry module
  (D-020) — closing a case where the UK's own relevance order could put a
  lower-confidence hit above a higher-confidence one.
- An upstream `429` is `rate_limited` on every country. Norway previously
  reported `upstream_error` for the same condition (D-019).

### Fixed
- `company_deadlines` no longer silently returns an empty list with no
  explanatory note for the UK when the response cache is disabled or cold
  (D-018).

## [0.1.0] - 2026-09-04

Initial public release: Norway (`NO`) only.

### Added
- MCP server (FastMCP, Streamable HTTP at `/mcp` and stdio) and REST API
  over Enhetsregisteret / Brønnøysundregistrene, sharing one pydantic
  contract byte-for-byte between both surfaces (D-004).
- Five tools / REST routes: `lookup_company`, `search_company`,
  `company_deadlines`, `validate_company_id`, `list_countries`.
- Computed Norwegian filing deadlines (årsregnskap, generalforsamling,
  skattemelding, aksjonærregisteroppgaven, mva-melding, a-melding), each
  carrying `applies_because`.
- A 24-hour SQLite response cache with honest `cached` / `fetched_at`
  (D-006).
- Structured `{"error": {"code", "message", "hint"}}` errors on every
  failure, identical on REST and MCP (D-007).
- Per-call logging and a `/v1/stats` dashboard.
- `llms.txt`, `llms-full.txt` and `server.json`, and a listing in the
  official MCP registry as `io.github.foretak/registry-mcp`.
- Published to PyPI and npm as `registry-mcp`, with `brreg-mcp` as an alias
  package.

[Unreleased]: https://github.com/foretak/registry-mcp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/foretak/registry-mcp/releases/tag/v0.2.0
[0.1.0]: https://github.com/foretak/registry-mcp/commit/2f72c54
