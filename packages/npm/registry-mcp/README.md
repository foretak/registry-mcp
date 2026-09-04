# registry-mcp (npm launcher)

**A company registry for AI agents — an MCP server and REST API over national business registries, any country.**

First module: **Norway** — `brreg` / Brønnøysundregistrene / **Enhetsregisteret**. Look up a company by **organisasjonsnummer** (**orgnr**, org.nr), search by name, check **MVA / VAT** registration, and compute statutory filing deadlines.

This npm package is a **thin launcher**. The server itself is Python, published
on PyPI as [`registry-mcp`](https://pypi.org/project/registry-mcp/); `npx
registry-mcp` runs `uvx registry-mcp` (falling back to `pipx run`) and passes
stdio straight through. You need **Python 3.12+** and one of **`uv`** or
**`pipx`** on your PATH. It is published under this name so the server is
findable on npm as well as PyPI — the alias `brreg-mcp` resolves to the same
thing.

## Use it

```bash
npx registry-mcp        # stdio MCP server
```

```json
{
  "mcpServers": {
    "registry-mcp": {
      "command": "npx",
      "args": ["-y", "registry-mcp"],
      "env": { "REGISTRY_MCP_CONTACT_EMAIL": "you@example.com" }
    }
  }
}
```

That block works in Claude Code (`.mcp.json`), Cursor (`~/.cursor/mcp.json`) and
Claude Desktop (`claude_desktop_config.json`). No install at all, using the
hosted server:

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp
```

## Tools

| Tool | What it does |
|---|---|
| `lookup_company(id, country="NO")` | Full `CompanyReport` for one company by national identifier |
| `search_company(name, country="NO", limit=10)` | `SearchResult` — candidates with identifiers, best first |
| `company_deadlines(id, country="NO", today=None)` | `DeadlineReport` — next occurrence of each statutory filing obligation |
| `validate_company_id(id, country="NO")` | `ValidationResult` — checksum-validate an identifier, no network call |
| `list_countries()` | Which national registries are supported right now |

```console
$ curl https://api.foretak.dev/v1/NO/company/923609016
{"country": "NO", "registry": "brreg", "id": "923609016", "name": "EQUINOR ASA",
 "legal_form_code": "ASA", "status": "active", "vat_registered": true,
 "vat_number": "NO923609016MVA", "employees": 21239, "license": "NLOD 2.0"}
```

## Environment

| Variable | Meaning |
|---|---|
| `REGISTRY_MCP_CONTACT_EMAIL` | Contact address sent in the `User-Agent` to the national registry, as Brønnøysundregistrene asks of API clients. |
| `REGISTRY_MCP_CACHE_PATH` | Path to the local SQLite response cache (24 h TTL). |
| `REGISTRY_MCP_SPEC` | Override the Python requirement this launcher installs. For CI and testing against a locally built wheel. |

Full documentation, REST endpoints, and how to add your country:
**https://github.com/foretak/registry-mcp**

## Data source and licence

Norwegian data comes from Enhetsregisteret (Brønnøysundregistrene) under
**NLOD 2.0**; every response carries `source`, `source_url` and `license`. This
project's code is MIT licensed. Not affiliated with or endorsed by
Brønnøysundregistrene.
