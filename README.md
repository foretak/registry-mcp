<!-- mcp-name: io.github.foretak/registry-mcp -->

# registry-mcp — the company registry MCP

[![PyPI](https://img.shields.io/pypi/v/registry-mcp?label=pypi%20registry-mcp)](https://pypi.org/project/registry-mcp/)
[![PyPI alias](https://img.shields.io/pypi/v/brreg-mcp?label=pypi%20brreg-mcp)](https://pypi.org/project/brreg-mcp/)
[![npm](https://img.shields.io/npm/v/registry-mcp?label=npm%20registry-mcp)](https://www.npmjs.com/package/registry-mcp)
[![CI](https://github.com/foretak/registry-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/foretak/registry-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**The company registry MCP — a company registry for AI agents, as an MCP server and REST API over national business registries, any country.**

**Countries: Norway (brreg), United Kingdom (Companies House).**

**Norway** — `brreg` / Brønnøysundregistrene / **Enhetsregisteret**. Look up a company by **organisasjonsnummer** (**orgnr**, org.nr), search by name, check **MVA / VAT** registration, and compute statutory filing deadlines. Also published as **`brreg-mcp`**, an alias package that installs exactly this server.

**United Kingdom** — **Companies House**. Look up a company by **company number** (**company registration number**, CRN), search by name, and read the **annual accounts** and **confirmation statement** deadlines the register publishes. The country code is **`GB`**, not `UK`. Companies House requires a free API key — see [Configuration](#configuration).

> Status: pre-release (`0.2.0`). The five tools and their response shapes are frozen; the hosted API at `api.foretak.dev` goes live with the first release.

## Add to Claude Code

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp
```

Or run it locally over stdio, no install step:

```bash
claude mcp add registry-mcp -- uvx registry-mcp
```

## What it returns

```console
$ curl https://api.foretak.dev/v1/NO/company/923609016
{
  "country": "NO", "registry": "brreg",
  "id": "923609016", "id_formatted": "923 609 016", "id_scheme": "organisasjonsnummer",
  "name": "EQUINOR ASA",
  "legal_form_code": "ASA", "legal_form": "Public limited company", "legal_form_local": "Allmennaksjeselskap",
  "status": "active", "is_active": true, "registered_at": "1995-03-12",
  "vat_registered": true, "vat_number": "NO923609016MVA", "vat_registered_at": "1989-07-01",
  "employees": 21239, "share_capital": 5976872600.0, "share_capital_currency": "NOK",
  "business_address": {"lines": ["Forusbeen 50"], "postal_code": "4035", "city": "STAVANGER"},
  "source": "Enhetsregisteret (Brønnøysundregistrene)", "license": "NLOD 2.0"
}
```

Abridged — the full `CompanyReport` also carries `previous_names`, `industry_codes`, `registers`, `purpose`, `parent_id`, `confidence`, `cached`, `fetched_at` and `notes`. Every field is documented in [`llms-full.txt`](static/llms-full.txt) §5.

The United Kingdom, same shape, same abridgement:

```console
$ curl https://api.foretak.dev/v1/GB/company/00445790
{
  "country": "GB", "registry": "companies-house",
  "id": "00445790", "id_formatted": null, "id_scheme": "company number",
  "name": "TESCO PLC",
  "legal_form_code": "plc", "legal_form": "Public limited company",
  "status": "active", "is_active": true, "registered_at": "1947-11-27",
  "vat_registered": null, "vat_number": null,
  "employees": null, "employees_reported": false,
  "registers": {"charges": false, "insolvency": false},
  "industry_codes": [{"code": "47110", "description": null, "scheme": "SIC 2007", "rank": 1}],
  "business_address": {"lines": ["Tesco House, Shire Park", "Kestrel Way"], "postal_code": "AL7 1GA", "city": "Welwyn Garden City"},
  "published_deadlines": [
    {"kind": "annual_accounts", "due_date": "2027-08-26", "period_end": "2027-02-26", "overdue": false, "source": "accounts.next_accounts.due_on"},
    {"kind": "confirmation_statement", "due_date": "2027-07-02", "period_end": "2027-06-18", "overdue": false, "source": "confirmation_statement.next_due"}
  ],
  "source": "Companies House (UK)", "license": "Crown copyright — Companies House public register, free to re-use"
}
```

`published_deadlines` carries the dates the register publishes itself, with the upstream field each came from. It is `[]` for Norway, which computes all of its own.

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

## Tools

| Tool | What it does |
|---|---|
| `lookup_company(id, country="NO")` | Full `CompanyReport` for one company by national identifier |
| `search_company(name, country="NO", limit=10)` | `SearchResult` — candidates with identifiers, in the register's relevance order, each scored |
| `company_deadlines(id, country="NO", today=None)` | `DeadlineReport` — the next occurrence of each statutory filing obligation |
| `validate_company_id(id, country="NO")` | `ValidationResult` — validate and normalise an identifier with no network call |
| `list_countries()` | Which national registries are supported right now |

Plus the resource `registry://rules/{country}` (identifier rules, legal forms, deadline rules — read once instead of validating in a loop) and the prompt `explain_company`.

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
    "registry-mcp": { "type": "http", "url": "https://api.foretak.dev/mcp" }
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
```

Machine-readable docs: [`/llms.txt`](https://api.foretak.dev/llms.txt), [`/llms-full.txt`](https://api.foretak.dev/llms-full.txt), [`/openapi.json`](https://api.foretak.dev/openapi.json).

## Adding your country

Norway is one folder. So is the United Kingdom: [`registries/gb/`](src/registry_mcp/registries/gb/) was added as four files and one import line, and `GB` appeared in `list_countries`, in every tool, in `/openapi.json` and in `registry://rules/GB` on its own.

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
src/registry_mcp/registries/  one folder per country — no/ (Norway), gb/ (UK), xx/ (template)
src/registry_mcp/api/         FastAPI REST surface
src/registry_mcp/mcp/         FastMCP server (stdio + Streamable HTTP at /mcp)
```

## Documents

- [`NORBIZ_SPEC.md`](NORBIZ_SPEC.md) — technical spec of the Norwegian module
- [`UK_SPEC.md`](UK_SPEC.md) — technical spec of the UK module
- [`DECISIONS.md`](DECISIONS.md) — interface and schema decisions
- [`KEYWORDS.md`](KEYWORDS.md) — the canonical alias list
- [`SUBMISSIONS.md`](SUBMISSIONS.md) — registry submission status
- [`legal/terms.md`](legal/terms.md) — terms of use and data attribution

## Data source and licence

Norwegian data comes from **Enhetsregisteret (Brønnøysundregistrene)**, published under **NLOD 2.0** — attribution required. UK data comes from the **Companies House public register**, Crown copyright, free to re-use with no attribution condition; we cite it anyway. Every response carries `source`, `source_url` and `license` so the attribution travels with the data. This project's own code is MIT licensed. Not affiliated with or endorsed by Brønnøysundregistrene or Companies House.
