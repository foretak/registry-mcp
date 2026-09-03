# registry-mcp

Company data for AI agents, any country. An MCP server and REST API over national business registries.

First module: **Norway** — Brønnøysundregistrene / Enhetsregisteret. Look up a company by organisasjonsnummer (orgnr), search by name, check VAT registration, and get filing deadlines.

> Status: pre-release. The interface is fixed (T01); the Norwegian module is being implemented (T02, T03).

## Add to Claude Code

```bash
claude mcp add registry-mcp --transport http https://api.example.dev/mcp
```

## Try it

```bash
curl https://api.example.dev/v1/NO/company/923609016
```

## Tools

| Tool | What it does |
|---|---|
| `lookup_company(id, country="NO")` | Full report for one company by national identifier |
| `search_company(name, country="NO")` | Find a company by name, returns candidates with identifiers |
| `company_deadlines(id, country, today)` | Filing deadlines the company faces |
| `validate_company_id(id, country)` | Checksum-validate an identifier without a network call |
| `list_countries()` | Which national registries are supported |

## Development

```bash
uv sync --all-extras
uv run pytest
uv run mypy .
uv run ruff check .
```

Layout:

```
src/registry_mcp/core/        country-neutral models, Registry ABC, date helpers
src/registry_mcp/registries/  one folder per country — no/ (Norway), xx/ (template)
src/registry_mcp/api/         FastAPI REST surface
src/registry_mcp/mcp/         FastMCP server
```

## Adding your country

Copy `src/registry_mcp/registries/xx/` to `registries/<cc>/`, implement four methods, add one import line. Nothing in `core/` changes. The template's module docstring has the six steps.

## Documents

- `NORBIZ_SPEC.md` — technical spec of the Norwegian module
- `DECISIONS.md` — interface and schema decisions
- `BRREG_MCP_BUILD_PLAN.md` — the phased build plan

## Data source and licence

Norwegian data comes from Enhetsregisteret (Brønnøysundregistrene), published under NLOD 2.0. This project is MIT licensed.
