<!-- mcp-name: io.github.foretak/registry-mcp -->

# registry-mcp

[![PyPI](https://img.shields.io/pypi/v/registry-mcp?label=pypi%20registry-mcp)](https://pypi.org/project/registry-mcp/)
[![PyPI alias](https://img.shields.io/pypi/v/brreg-mcp?label=pypi%20brreg-mcp)](https://pypi.org/project/brreg-mcp/)
[![npm](https://img.shields.io/npm/v/registry-mcp?label=npm%20registry-mcp)](https://www.npmjs.com/package/registry-mcp)
[![CI](https://github.com/foretak/registry-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/foretak/registry-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**A company registry for AI agents — an MCP server and REST API over national business registries, any country.**

First module: **Norway** — `brreg` / Brønnøysundregistrene / **Enhetsregisteret**. Look up a company by **organisasjonsnummer** (**orgnr**, org.nr), search by name, check **MVA / VAT** registration, and compute statutory filing deadlines. Also published as **`brreg-mcp`**, an alias package that installs exactly this server.

> Status: pre-release (`0.1.0`). The five tools and their response shapes are frozen; the hosted API at `api.foretak.dev` goes live with the first release.

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

## Tools

| Tool | What it does |
|---|---|
| `lookup_company(id, country="NO")` | Full `CompanyReport` for one company by national identifier |
| `search_company(name, country="NO", limit=10)` | `SearchResult` — candidates with identifiers, best first |
| `company_deadlines(id, country="NO", today=None)` | `DeadlineReport` — the next occurrence of each statutory filing obligation |
| `validate_company_id(id, country="NO")` | `ValidationResult` — checksum-validate an identifier with no network call |
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
      "env": { "REGISTRY_MCP_CONTACT_EMAIL": "you@example.com" }
    }
  }
}
```
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

**Environment variables** — both optional:

| Variable | Meaning |
|---|---|
| `REGISTRY_MCP_CONTACT_EMAIL` | Contact address sent in the `User-Agent` to the national registry, as Brønnøysundregistrene asks of API clients. Unset means an anonymous client, which may be throttled or blocked upstream. |
| `REGISTRY_MCP_CACHE_PATH` | Path to the local SQLite response cache (24 h TTL). Defaults to `./data/cache.sqlite3`. |

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

# Which countries are live
curl https://api.foretak.dev/v1/countries
```

Machine-readable docs: [`/llms.txt`](https://api.foretak.dev/llms.txt), [`/llms-full.txt`](https://api.foretak.dev/llms-full.txt), [`/openapi.json`](https://api.foretak.dev/openapi.json).

## Adding your country

Norway is one folder. Copy `src/registry_mcp/registries/xx/` to `registries/<cc>/`, implement four methods, add one import line — nothing in `core/` changes, and both surfaces plus the manifests light up for the new country automatically.

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
src/registry_mcp/registries/  one folder per country — no/ (Norway), xx/ (template)
src/registry_mcp/api/         FastAPI REST surface
src/registry_mcp/mcp/         FastMCP server (stdio + Streamable HTTP at /mcp)
```

## Documents

- [`NORBIZ_SPEC.md`](NORBIZ_SPEC.md) — technical spec of the Norwegian module
- [`DECISIONS.md`](DECISIONS.md) — interface and schema decisions
- [`KEYWORDS.md`](KEYWORDS.md) — the canonical alias list
- [`SUBMISSIONS.md`](SUBMISSIONS.md) — registry submission status
- [`legal/terms.md`](legal/terms.md) — terms of use and data attribution

## Data source and licence

Norwegian data comes from **Enhetsregisteret (Brønnøysundregistrene)**, published under **NLOD 2.0**; every response carries `source`, `source_url` and `license` so the attribution travels with the data. This project's own code is MIT licensed. Not affiliated with or endorsed by Brønnøysundregistrene.
