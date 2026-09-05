# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning applies to the response shapes and tool contract described in
[`DECISIONS.md`](DECISIONS.md) — the five tools and their response shapes are
frozen as of `0.2.0`.

## [Unreleased]

Legibility fixes (T17): no `core/` change, no response-shape change.

### Added
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
