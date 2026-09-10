<!-- mcp-name: io.github.foretak/registry-mcp -->

# registry-mcp — the company registry MCP

[![PyPI](https://img.shields.io/pypi/v/registry-mcp?label=pypi%20registry-mcp)](https://pypi.org/project/registry-mcp/)
[![PyPI alias](https://img.shields.io/pypi/v/brreg-mcp?label=pypi%20brreg-mcp)](https://pypi.org/project/brreg-mcp/)
[![npm](https://img.shields.io/npm/v/registry-mcp?label=npm%20registry-mcp)](https://www.npmjs.com/package/registry-mcp)
[![CI](https://github.com/foretak/registry-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/foretak/registry-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Listed on mcpservers.org](https://mcpservers.org/badge.svg)](https://mcpservers.org/servers/foretak/registry-mcp)
[![Rated A on Glama](https://glama.ai/mcp/connectors/io.github.foretak/registry-mcp/badges/score.svg)](https://glama.ai/mcp/connectors/io.github.foretak/registry-mcp)

**Company data for AI agents, any country.** One MCP server and REST API, three national registers today: the United Kingdom's **Companies House**, looked up by **company number**; Norway's **Enhetsregisteret** / **Brønnøysundregistrene** (**brreg**), looked up by **organisasjonsnummer** (**orgnr**); and Sweden's **Bolagsverket**, looked up by **organisationsnummer** — one JSON shape whichever you ask.

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp?src=readme
```

No install step, over stdio:

```bash
claude mcp add registry-mcp -- uvx registry-mcp
```

What makes it worth a tool slot:

- **Deadlines that cite the rule, not just a date.** `company_deadlines` gives the next filing date and names why in `applies_because` — a Norwegian legal form's statutory duty, or "Companies House publishes this date for the company itself" when the register states it rather than us computing it. Quote the reason, not just the number.
- **Never more than 24 hours stale, and it says so.** Every response carries `cached` and `fetched_at`. OpenCorporates' own knowledge base tells users to ["allow 30 days"](https://knowledge.opencorporates.com/knowledge-base/the-data-on-opencorporates-is-out-of-date/) for a correction to reach its site — a 30× freshness gap, stated by the incumbent about itself.
- **Seven tools, not fifty** — five registry tools plus two ChatGPT connector aliases. Tool-selection accuracy [degrades past 30-50 tools loaded into an agent's context](https://code.claude.com/docs/en/agent-sdk/tool-search), and some clients cap around 40. Seven tools is roughly 17% of that budget, next to competitors in this space shipping 23 to 78 tools for the same job.

**Security.** Read-only, always — nothing here writes to a register or anywhere else. No credentials are required from a caller; this deployment's own upstream credential (`COMPANIES_HOUSE_API_KEY`) is read from the environment and never logged or returned. The base lookup calls three named upstreams and nothing else: `data.brreg.no`, `api.company-information.service.gov.uk` and `gw.api.bolagsverket.se`. `include=["lei"]`/`include=["parents"]` additionally call `api.gleif.org` (GLEIF, CC0, keyless); `include=["peppol"]` additionally resolves a DNS record at the Peppol SML and calls whichever SMP host it names for that participant, falling back to the Peppol Directory (`directory.peppol.eu`) only when neither answers — see the [attachments](#tools) above. No personal data beyond what each national register already publishes about the entity itself — and because a Swedish sole trader's company number *is* their personnummer, the usage log stores no identifier at all for a country whose identifiers can be a natural person's ([`legal/privacy.md`](legal/privacy.md)). This service does not perform sanctions, PEP or adverse-media screening, and it does not verify bank account details. Details: [SECURITY.md](SECURITY.md).

One-click install, for a remote streamable-HTTP server:

[<img src="https://img.shields.io/badge/VS_Code-VS_Code?style=flat-square&label=Install%20Server&color=0098FF" alt="Install in VS Code">](https://insiders.vscode.dev/redirect?url=vscode%3Amcp%2Finstall%3F%257B%2522name%2522%253A%2522registry-mcp%2522%252C%2522type%2522%253A%2522http%2522%252C%2522url%2522%253A%2522https%253A%252F%252Fapi.foretak.dev%252Fmcp%253Fsrc%253Dreadme%2522%257D)
[<img alt="Install in VS Code Insiders" src="https://img.shields.io/badge/VS_Code_Insiders-VS_Code_Insiders?style=flat-square&label=Install%20Server&color=24bfa5">](https://insiders.vscode.dev/redirect?url=vscode-insiders%3Amcp%2Finstall%3F%257B%2522name%2522%253A%2522registry-mcp%2522%252C%2522type%2522%253A%2522http%2522%252C%2522url%2522%253A%2522https%253A%252F%252Fapi.foretak.dev%252Fmcp%253Fsrc%253Dreadme%2522%257D)
[<img src="https://cursor.com/deeplink/mcp-install-dark.svg" alt="Install in Cursor">](https://cursor.com/en/install-mcp?name=registry-mcp&config=eyJ1cmwiOiJodHRwczovL2FwaS5mb3JldGFrLmRldi9tY3A%2Fc3JjPXJlYWRtZSJ9)

Other clients (Claude Desktop, Cursor, VS Code, Cline, plain JSON configs): see [docs/clients.md](docs/clients.md).

## Add to ChatGPT

ChatGPT reaches an MCP server through a custom connector, and its deep research mode calls
exactly two tools — `search` and `fetch` — which this server ships alongside the five registry
tools. In ChatGPT, open **Settings → Connectors**, add a custom connector, and give it:

    https://api.foretak.dev/mcp?src=readme

No authentication, no key, no account. If your ChatGPT plan does not show custom connectors
under Settings → Connectors, turn on **Settings → Security and login → Developer mode** first,
then add the URL from <https://chatgpt.com/plugins>.

`search` takes one free-text query — a company name, a national identifier, or a name plus a
country ("Tesco United Kingdom") — and returns citable rows; `fetch` takes a row's `id`
(`"NO:923609016"`) and returns that company's register record **and its statutory filing
deadlines**, with the full JSON of both in `metadata`.

## Add to Claude Desktop

Claude Desktop takes the same URL as a custom connector: **Settings → Connectors → Add custom
connector**, then `https://api.foretak.dev/mcp?src=readme`. No key. For a local stdio install instead, see
[Configuration](#configuration).

> Status: `0.4.2`, live — `GET /health` returns `{"version":"0.4.2","countries":["GB","NO","SE"]}`. The five registry tools and their response shapes are frozen; two connector aliases (`search`, `fetch`) wrap them for ChatGPT and add no new shape. The hosted API at `api.foretak.dev` is live, and listed in the official MCP registry as `io.github.foretak/registry-mcp`. Countries: United Kingdom (Companies House), Norway (brreg), Sweden (Bolagsverket) — see [below](#tools) for each country's identifier format and example calls.

## Add to Claude Code

The same two commands as above — Streamable HTTP or local stdio. To add it as a project-level `.mcp.json` file instead of the CLI, see [Configuration](#configuration).

## What it returns

```console
$ curl https://api.foretak.dev/v1/NO/company/923609016
{
  "country": "NO", "registry": "brreg",
  "id": "923609016", "id_formatted": "923 609 016", "id_scheme": "organisasjonsnummer", "euid": null,
  "name": "EQUINOR ASA",
  "legal_form_code": "ASA", "legal_form": "Public limited company", "legal_form_local": "Allmennaksjeselskap",
  "status": "active", "is_active": true, "registered_at": "1995-03-12",
  "vat_registered": true, "vat_number": "NO923609016MVA", "vat_registered_at": "1989-07-01",
  "employees": 21239, "share_capital": 5976872600.0, "share_capital_currency": "NOK",
  "business_address": {"lines": ["Forusbeen 50"], "postal_code": "4035", "city": "STAVANGER"},
  "advertising_protected": null,
  "source": "Enhetsregisteret (Brønnøysundregistrene)", "license": "NLOD 2.0"
}
```

Abridged — the full `CompanyReport` also carries `previous_names`, `industry_codes`, `registers`, `purpose`, `parent_id`, `confidence`, `cached`, `fetched_at` and `notes`. Every field is documented in [`llms-full.txt`](static/llms-full.txt) §5.

`euid` is the EU-wide identifier some member-state registers publish (Finland does; none of ours do yet) — never the LEI, never constructed from parts. `advertising_protected` is `true`/`false`/`null`: whether the register marks this entity as protected against direct-marketing use, `null` meaning the register publishes no such flag at all (Norway and the UK, today); where it is `true` (Sweden's *reklamspärr*, for one), a `notes` sentence states it and that marking must travel with any contact details you pass on.

The United Kingdom, same shape, same abridgement:

```console
$ curl https://api.foretak.dev/v1/GB/company/00445790
{
  "country": "GB", "registry": "companies-house",
  "id": "00445790", "id_formatted": null, "id_scheme": "company number", "euid": null,
  "name": "TESCO PLC",
  "legal_form_code": "plc", "legal_form": "Public limited company",
  "status": "active", "is_active": true, "registered_at": "1947-11-27",
  "vat_registered": null, "vat_number": null,
  "employees": null, "employees_reported": false,
  "registers": {"insolvency": false},
  "industry_codes": [{"code": "47110", "description": null, "scheme": "SIC 2007", "rank": 1}],
  "business_address": {"lines": ["Tesco House, Shire Park", "Kestrel Way"], "postal_code": "AL7 1GA", "city": "Welwyn Garden City"},
  "advertising_protected": null,
  "published_deadlines": [
    {"kind": "annual_accounts", "due_date": "2027-08-26", "period_end": "2027-02-26", "overdue": false, "source": "accounts.next_accounts.due_on"},
    {"kind": "confirmation_statement", "due_date": "2027-07-02", "period_end": "2027-06-18", "overdue": false, "source": "confirmation_statement.next_due"}
  ],
  "source": "Companies House (UK)", "license": "Crown copyright — Companies House public register, free to re-use"
}
```

`published_deadlines` carries the dates the register publishes itself, with the upstream field each came from. It is `[]` for Norway and Sweden, which compute all of their own.

Sweden, added in 0.3.0, is where "one shape" starts to earn the claim:

```console
$ curl https://api.foretak.dev/v1/SE/company/5560160680
{
  "country": "SE", "registry": "bolagsverket",
  "id": "5560160680", "id_formatted": "556016-0680", "id_scheme": "organisationsnummer", "euid": null,
  "name": "Telefonaktiebolaget LM Ericsson",
  "legal_form_code": "AB", "legal_form": "Private or public limited company", "legal_form_local": "Aktiebolag",
  "status": "active", "is_active": true, "registered_at": "1918-08-19",
  "vat_registered": null, "vat_number": null,
  "employees": null, "employees_reported": false,
  "industry_codes": [{"code": "70100", "description": "Verksamheter som utövas av huvudkontor", "scheme": "SNI 2007", "rank": 1}],
  "postal_address": {"postal_code": "16483", "city": "STOCKHOLM", "country_code": "SE"},
  "advertising_protected": null,
  "published_deadlines": [],
  "source": "Bolagsverket (bolagsverket.se)",
  "license": "Free re-use (Bolagsverket/SCB high-value datasets, EU Open Data Directive) — the publisher names no licence"
}
```

Bolagsverket names no licence for this data, so neither do we: the string says what the permission is and says plainly that there is no licence name to quote, because a familiar name in that field would be a fabrication.

Sweden publishes no status field at all. `status` is derived from three independent signals — a strike-off date, an ongoing winding-up or restructuring procedure, and Statistics Sweden's "economically active" flag — and `is_active` therefore means *on the register and not winding down*, which is not the same as trading. Where any of that is unavailable the answer is `unknown`, never `active`.

Two dates are computed, and each carries the provision it comes from:

```console
$ curl "https://api.foretak.dev/v1/SE/company/5560160680/deadlines?today=2026-09-07"
{"kind": "general_meeting",  "due_date": "2027-06-30", "days_until": 296, "rolled_forward": false, "period_label": "2026"}
{"kind": "annual_accounts",  "due_date": "2027-07-31", "days_until": 327, "rolled_forward": false, "period_label": "2026"}
```

Six months to the annual general meeting (aktiebolagslagen 7 kap. 10 §) and seven to the filing before a late fee bites (årsredovisningslagen 8 kap. 6 §). Neither date is rolled forward off a weekend, because no Swedish source says it moves. Both assume a financial year ending 31 December by default — a `notes` sentence says exactly that, including how to shift both dates if the year end is different — but Bolagsverket's document list does publish a filed annual report's own year end: pass `include=["filings"]` (`company_deadlines` accepts it on both surfaces) to read it and replace the assumption with the register's own figure. `search_company` answers `not_implemented` for Sweden: the free API has four operations and none of them accepts a name.

Note the `null`s. Companies House publishes no VAT status, no employee count and no share capital for any company, so those fields are `null` rather than guessed — `null` means "this register does not say", never "no". That honesty is the point of one shape across countries.

And the deadlines, which is where the UK module earns its keep:

```console
$ curl "https://api.foretak.dev/v1/GB/company/00445790/deadlines?today=2026-09-04"
{
  "company_name": "TESCO PLC", "today": "2026-09-04",
  "deadlines": [
    {"kind": "confirmation_statement", "local_name": "Confirmation statement (CS01)",
     "due_date": "2027-07-02", "period_end": "2027-06-18", "days_until": 301,
     "applies_because": "Companies House publishes this date for the company itself; it is the register's own figure, not a calculation."},
    {"kind": "annual_accounts", "local_name": "Annual accounts",
     "due_date": "2027-08-26", "period_end": "2027-02-26", "days_until": 356,
     "applies_because": "Companies House publishes this date for the company itself; it is the register's own figure, not a calculation."}
  ]
}
```

Where Companies House publishes a date, it is quoted; where it does not, the date is computed from a cited statute and `applies_because` says so. UK deadlines never roll forward off a weekend or bank holiday, and `days_until` goes negative for a filing the register still shows as overdue.

**Running it yourself?** The hosted service at `api.foretak.dev` has every credential configured. A self-hosted copy needs a free [Companies House key](https://developer.company-information.service.gov.uk/get-started) for `GB` and an OAuth 2 client pair from Bolagsverket (`BOLAGSVERKET_CLIENT_ID`, `BOLAGSVERKET_CLIENT_SECRET`) for `SE`; without them those two countries return `upstream_error` naming the variable, and every other country keeps answering. Norway needs nothing.

## Tools

| Tool | What it does |
|---|---|
| `lookup_company(id, country="NO")` | Full `CompanyReport` for one company by national identifier |
| `search_company(name, country="NO", limit=10)` | `SearchResult` — candidates with identifiers, in the register's relevance order, each scored |
| `company_deadlines(id, country="NO", today=None)` | `DeadlineReport` — the next occurrence of each statutory filing obligation |
| `validate_company_id(id, country="NO")` | `ValidationResult` — validate and normalise an identifier with no network call |
| `list_countries()` | Which national registries are supported right now |

**Connector aliases** — for ChatGPT, which reaches an MCP server through exactly `search` and `fetch` ([Add to ChatGPT](#add-to-chatgpt)); add no new response shape and have no REST twin.

| Tool | What it does |
|---|---|
| `search(query)` | ChatGPT connector alias for `search_company` — one free-text query, `{"results": [{"id", "title", "url"}]}` |
| `fetch(id)` | ChatGPT connector alias for `lookup_company` + `company_deadlines` — one `"{COUNTRY}:{identifier}"`, a Markdown document with both reports in `metadata` |

Plus the resource `registry://rules/{country}` (identifier rules, legal forms, deadline rules — read once instead of validating in a loop) and the prompt `explain_company`.

**Attachments** — a second, independent fetch alongside the base report, opt-in per name: `include=["filings"]` on MCP, `?include=filings` on REST.

- `filings` — what the entity has filed, and when (`GB`, `NO`, `SE`)
- `charges` — registered charges against the entity (`GB` only)
- `insolvency` — winding-up and administration proceedings (`GB` only)
- `financials` — the register's own financial figures (turnover, profit, balance sheet, equity and liabilities) for the latest filed accounting period, answering whether a supplier looks solvent — Norway's own key-figures feed, Sweden's read out of the entity's own filed annual report (`NO`, `SE`)
- `lei` — the Legal Entity Identifier GLEIF publishes for the entity, CC0-licensed and keyless (every country except `SE`)
- `parents` — the direct and ultimate corporate parent GLEIF's Level 2 data discloses, or the entity's own stated reason — a category word such as `NATURAL_PERSONS`, never a name — when it discloses none (same countries as `lei`)
- `peppol` — whether the entity can receive an e-invoice over the Peppol network, read live from the SML/SMP walk ahead of the 1 January 2027 e-invoicing duty (`NO` only)

A country's declared set is `supported_includes` on `list_countries` / `GET /v1/countries`; see [`llms-full.txt`](static/llms-full.txt) for the two-level nullability and the per-country scope of `filings`.

`parent_id` and `in_group` on a Norwegian `CompanyReport` describe Enhetsregisteret's own parent/sub-unit relation for that entity — nothing more. There is no group-walk tool: following a corporate group upward means calling `lookup_company` again on `parent_id`, repeatedly, and that walk answers "what does the register list as this entity's parent?", not "who beneficially owns or controls this company?" — a different question this service does not answer. `include=["parents"]` above is a different route to an adjacent fact — GLEIF's opinion of who consolidates this entity's accounts, not Enhetsregisteret's own hierarchy and not beneficial ownership either. See [`llms-full.txt`](static/llms-full.txt) §5.

## Why an agent checks a company

Three rules make this a duty rather than a nicety. Finanstilsynet's [Rundskriv 15/2019](https://www.finanstilsynet.no/nyhetsarkiv/rundskriv/2019/veiledning-om-regnskapsforeres-og-regnskapsforerselskapers-etterlevelse-av-hvitvaskingsregelverket/) § 4.4.1 accepts an *oppslag* against Enhetsregisteret no older than three months, one month where the check rests on company details the customer supplied, and asks for *notoritet* about the lookup: what was consulted, and when. From [1 January 2027](https://www.regjeringen.no/no/aktuelt/nye-lovregler-om-e-fakturering-i-naringslivet-og-enkelte-andre-lovendringer-pa-finansmarkedsomradet-settes-i-kraft/) Norwegian bookkeeping-obliged businesses must invoice each other by e-invoice, and the receiver is resolved in ELMA as [`0192:` plus organisasjonsnummer](https://www.anskaffelser.no/verktoy/veiledere/mottakere-av-ehf-og-peppol-bis), the identifier these tools already take. From 10 July 2027, [AMLR](https://eur-lex.europa.eu/eli/reg/2024/1624/oj/eng) Article 23(4) requires "valid proof of registration or a recently issued excerpt of the register" for every new business relationship with a legal entity.

That is what `source_url`, `fetched_at`, `cached`, `license` and `applies_because` are for: which record was consulted, when it was read, whether it came from the 24 h cache, the terms it travels under, and whether a deadline was quoted from the register or computed from a named rule.

The limits, stated rather than implied: no sanctions or PEP screening; no bank-account verification, and the commonest invoice fraud is payment redirection, where the supplier is real and only the account number is wrong; and no beneficial owners, which brreg [releases on application only](https://www.brreg.no/bruke-data-fra-bronnoysundregistrene/datasett-og-api/data-om-reelle-rettighetshavere/), to categories of applicant that do not include a product vendor. Fuller version in [`llms-full.txt`](static/llms-full.txt) §9.

## Configuration

<details open>
<summary><b>Claude Code</b> — <code>.mcp.json</code> in the project root</summary>

```json
{
  "mcpServers": {
    "registry-mcp": {
      "command": "uvx",
      "args": ["registry-mcp"],
      "env": {
        "REGISTRY_MCP_CONTACT_EMAIL": "you@example.com",
        "COMPANIES_HOUSE_API_KEY": "your-companies-house-key"
      }
    }
  }
}
```

Drop `COMPANIES_HOUSE_API_KEY` if you only need Norway; every other country works without it.
</details>

<details>
<summary><b>Cursor</b> — <code>~/.cursor/mcp.json</code> (or <code>.cursor/mcp.json</code> in the project)</summary>

```json
{
  "mcpServers": {
    "registry-mcp": {
      "command": "uvx",
      "args": ["registry-mcp"],
      "env": { "REGISTRY_MCP_CONTACT_EMAIL": "you@example.com" }
    }
  }
}
```
</details>

<details>
<summary><b>Claude Desktop</b> — <code>claude_desktop_config.json</code></summary>

macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "registry-mcp": {
      "command": "uvx",
      "args": ["registry-mcp"],
      "env": { "REGISTRY_MCP_CONTACT_EMAIL": "you@example.com" }
    }
  }
}
```
</details>

<details>
<summary><b>npm instead of uvx</b> — same server, Node launcher</summary>

```json
{
  "mcpServers": {
    "registry-mcp": { "command": "npx", "args": ["-y", "registry-mcp"] }
  }
}
```

`npx registry-mcp` shells out to `uvx registry-mcp` (falling back to `pipx run registry-mcp`), so Python 3.12+ and one of `uv` or `pipx` must be present.
</details>

<details>
<summary><b>Hosted, no local install</b> — Streamable HTTP</summary>

```json
{
  "mcpServers": {
    "registry-mcp": { "type": "http", "url": "https://api.foretak.dev/mcp?src=readme" }
  }
}
```
</details>

**Environment variables** — all optional:

| Variable | Meaning |
|---|---|
| `REGISTRY_MCP_CONTACT_EMAIL` | Contact address sent in the `User-Agent` to the national registry, as Brønnøysundregistrene asks of API clients. Unset means an anonymous client, which may be throttled or blocked upstream. |
| `REGISTRY_MCP_CACHE_PATH` | Path to the local SQLite response cache (24 h TTL). Defaults to `./data/cache.sqlite3`. |
| `COMPANIES_HOUSE_API_KEY` | Required for the United Kingdom (`GB`). A key is [free and instant](https://developer.company-information.service.gov.uk/get-started). Unset means `GB` lookups return `upstream_error` with a hint naming this variable — every other country keeps working. |
| `BOLAGSVERKET_CLIENT_ID`, `BOLAGSVERKET_CLIENT_SECRET` | Required for Sweden (`SE`). An OAuth 2 client pair Bolagsverket issues on request; the data itself is free under the EU high-value-datasets regulation. Unset means `SE` lookups return `upstream_error` naming both variables — every other country keeps working. |

## REST

Every tool has a REST twin returning the identical JSON document.

```bash
# One company by organisasjonsnummer
curl https://api.foretak.dev/v1/NO/company/923609016

# Search by name
curl "https://api.foretak.dev/v1/NO/search?q=equinor&limit=5"

# Statutory filing deadlines, from a date you choose
curl "https://api.foretak.dev/v1/NO/company/923609016/deadlines?today=2026-01-15"

# Checksum-validate an identifier — no upstream call, instant
curl https://api.foretak.dev/v1/NO/validate/923609016

# Which countries are live, and which need an API key
curl https://api.foretak.dev/v1/countries

# The same five routes for the United Kingdom — GB, never UK
curl https://api.foretak.dev/v1/GB/company/00445790
curl "https://api.foretak.dev/v1/GB/search?q=tesco&limit=5"
curl "https://api.foretak.dev/v1/GB/company/00445790/deadlines?today=2026-09-04"
curl https://api.foretak.dev/v1/GB/validate/445790

# Sweden — four of the five. /search returns 501 not_implemented: the free
# Bolagsverket API has no name index, and the error's hint says so.
curl https://api.foretak.dev/v1/SE/company/5560160680
curl "https://api.foretak.dev/v1/SE/company/5560160680/deadlines?today=2026-09-07"
curl https://api.foretak.dev/v1/SE/validate/556016-0680
```

Machine-readable docs: [`/llms.txt`](https://api.foretak.dev/llms.txt), [`/llms-full.txt`](https://api.foretak.dev/llms-full.txt), [`/openapi.json`](https://api.foretak.dev/openapi.json).

## Adding your country

Norway is one folder. So is the United Kingdom: [`registries/gb/`](src/registry_mcp/registries/gb/) was added as four files and one import line, and `GB` appeared in `list_countries`, in every tool, in `/openapi.json` and in `registry://rules/GB` on its own. So is Sweden — [`registries/se/`](src/registry_mcp/registries/se/) shipped in 0.3.0 with **no change to `core/`**, including the parts of Sweden that fit the abstraction worst: a register that publishes no status field, an operation the upstream does not offer (`search_company` answers `not_implemented`), and an identifier that can be a natural person's national ID.

Copy `src/registry_mcp/registries/xx/` to `registries/<cc>/`, implement four methods, add one import line — nothing in `core/` changes, and both surfaces plus the manifests light up for the new country automatically.

**→ [CONTRIBUTING.md](CONTRIBUTING.md) — "Add your country"**, and the [`new country` issue template](.github/ISSUE_TEMPLATE/new_country.yml) to claim one first.

## Development

```bash
uv sync --all-extras
uv run pytest          # `-m "not live"` to skip the tests that hit the real registry
uv run mypy .
uv run ruff check .
```

Layout:

```
src/registry_mcp/core/        country-neutral models, Registry ABC, rules, date helpers
src/registry_mcp/registries/  one folder per country — no/ (Norway), gb/ (UK), se/ (Sweden), xx/ (template)
src/registry_mcp/api/         FastAPI REST surface
src/registry_mcp/mcp/         FastMCP server (stdio + Streamable HTTP at /mcp)
```

## Documents

- [`NORBIZ_SPEC.md`](NORBIZ_SPEC.md) — technical spec of the Norwegian module
- [`UK_SPEC.md`](UK_SPEC.md) — technical spec of the UK module
- [`SWEDEN_SPEC.md`](SWEDEN_SPEC.md) — technical spec of the Swedish module
- [`DECISIONS.md`](DECISIONS.md) — interface and schema decisions
- [`KEYWORDS.md`](KEYWORDS.md) — the canonical alias list
- [`SUBMISSIONS.md`](SUBMISSIONS.md) — registry submission status
- [`legal/terms.md`](legal/terms.md) — terms of use and data attribution

## Data source and licence

Norwegian data comes from **Enhetsregisteret (Brønnøysundregistrene)**, published under **NLOD 2.0** — attribution required. UK data comes from the **Companies House public register**, Crown copyright, free to re-use with no attribution condition; we cite it anyway. Swedish data comes from **Bolagsverket**, with Statistics Sweden (**SCB**) as a second producer inside the same payload, free to re-use as a *värdefull datamängd* under the EU high-value-datasets regime — Bolagsverket's own words are *"Det krävs inget avtal för att du ska få använda vårt API för värdefulla datamängder"* and *"Värdefulla datamängder är avgiftsfritt"* — and **Bolagsverket names no licence**, so neither do we: the `license` string states the permission and states plainly that there is no licence name to quote. Every response carries `source`, `source_url` and `license` so the attribution travels with the data. This project's own code is MIT licensed. Not affiliated with or endorsed by Brønnøysundregistrene, Companies House or Bolagsverket.
