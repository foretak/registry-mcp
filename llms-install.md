# Installing registry-mcp (for AI agents such as Cline)

registry-mcp is an MCP server for national company registries (Norway: Brønnøysundregistrene / brreg; United Kingdom: Companies House). It needs no build step and no credentials for Norway.

## Option A — hosted (recommended, nothing to install)

Add a remote MCP server of type Streamable HTTP with this URL:

```
https://api.foretak.dev/mcp
```

No authentication header is required. Example MCP settings entry:

```json
{
  "mcpServers": {
    "registry-mcp": {
      "type": "streamableHttp",
      "url": "https://api.foretak.dev/mcp"
    }
  }
}
```

## Option B — local over stdio

Requires Python 3.12+ and `uv` (https://docs.astral.sh/uv/). No clone, no build:

```json
{
  "mcpServers": {
    "registry-mcp": {
      "command": "uvx",
      "args": ["registry-mcp"]
    }
  }
}
```

`npx -y registry-mcp` works too; it shells out to `uvx`, so `uv` must still be present.

## Optional environment variables (local mode)

| Variable | Purpose |
|---|---|
| `COMPANIES_HOUSE_API_KEY` | Enables United Kingdom (`GB`) lookups. Free key from https://developer.company-information.service.gov.uk/. Without it, GB calls return `upstream_error` with a hint naming this variable; Norway keeps working. |
| `REGISTRY_MCP_CACHE_PATH` | Path to the SQLite response cache (24 h TTL). Default `./data/cache.sqlite3`. |
| `REGISTRY_MCP_CONTACT_EMAIL` | Contact address sent in the User-Agent to the registers, as Brønnøysundregistrene asks. |

## Verify

After connecting, list tools. You should see exactly five: `lookup_company`, `search_company`, `validate_company_id`, `company_deadlines`, `list_countries`. A first call to try:

```
validate_company_id(id="923609016", country="NO")
```

It returns `valid: true` without any network call. Then `lookup_company(id="923609016")` returns Equinor ASA's register record.
