# @foretak/brreg-mcp

**MCP server for brreg — Norwegian company lookup in Brønnøysundregistrene / Enhetsregisteret by organisasjonsnummer (orgnr, org.nr).**

This is an **alias package**. It contains no logic: it launches the Python
server published on PyPI as [`brreg-mcp`](https://pypi.org/project/brreg-mcp/),
which is itself an alias of
[`registry-mcp`](https://pypi.org/project/registry-mcp/) — the same five tools,
the same entry point. Install whichever name you searched for; you get the same
server. You need **Python 3.12+** and one of **`uv`** or **`pipx`** on your PATH.

```bash
uvx brreg-mcp             # identical to: uvx registry-mcp
npx -y @foretak/brreg-mcp # the same, launched from Node
```

## Add to Claude Code

```bash
claude mcp add brreg-mcp -- uvx brreg-mcp
```

```json
{
  "mcpServers": {
    "brreg-mcp": {
      "command": "uvx",
      "args": ["brreg-mcp"],
      "env": { "REGISTRY_MCP_CONTACT_EMAIL": "you@example.com" }
    }
  }
}
```

The same block works for Cursor (`~/.cursor/mcp.json`) and Claude Desktop
(`claude_desktop_config.json`). No install at all, using the hosted server:

```bash
claude mcp add brreg-mcp --transport http https://api.foretak.dev/mcp
```

## Tools

| Tool | What it does |
|---|---|
| `lookup_company(id, country="NO")` | Full report for one company by organisasjonsnummer |
| `search_company(name, country="NO", limit=10)` | Find a Norwegian company by name |
| `company_deadlines(id, country="NO", today=None)` | Årsregnskap, skattemelding, mva-melding, a-melding and the rest, next occurrence of each |
| `validate_company_id(id, country="NO")` | MOD11-validate an orgnr with no network call |
| `list_countries()` | Which national registries are supported |

```console
$ curl https://api.foretak.dev/v1/NO/company/923609016
{"country": "NO", "registry": "brreg", "id": "923609016", "name": "EQUINOR ASA",
 "legal_form_code": "ASA", "status": "active", "vat_registered": true,
 "vat_number": "NO923609016MVA", "employees": 21239, "license": "NLOD 2.0"}
```

Full documentation, REST endpoints, and the guide to adding another country:
**https://github.com/foretak/registry-mcp**

## Data source and licence

Data from Enhetsregisteret (Brønnøysundregistrene) under NLOD 2.0. Code MIT
licensed. Not affiliated with or endorsed by Brønnøysundregistrene.
