# brreg-mcp

**MCP server for brreg — Norwegian company lookup in Brønnøysundregistrene / Enhetsregisteret by organisasjonsnummer (orgnr, org.nr).**

`brreg-mcp` is an **alias package**. It contains no logic: it depends on
[`registry-mcp`](https://pypi.org/project/registry-mcp/) and its `brreg-mcp`
console script is the same entry point, serving the same five tools over stdio.
Install whichever name you searched for — you get the same server.

```bash
uvx brreg-mcp        # identical to: uvx registry-mcp
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
(`claude_desktop_config.json`).

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
