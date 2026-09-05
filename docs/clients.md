# Client setup

Hosted server: `https://api.foretak.dev/mcp` (Streamable HTTP, no authentication). Local: `uvx registry-mcp` (stdio). Full tool/response reference: [`../README.md`](../README.md), [`../static/llms-full.txt`](../static/llms-full.txt).

## Claude Code

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp
```

Or install as a plugin, from this repo's self-hosted marketplace:

```bash
claude plugin marketplace add foretak/registry-mcp
claude plugin install registry-mcp@foretak
```

The marketplace is [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json); the plugin it points to is [`plugins/registry-mcp/`](../plugins/registry-mcp/), which registers the hosted server via its own `.mcp.json`. Schema and commands: [Plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces) (`name`, `owner.name`, `plugins[].name`, `plugins[].source`, `claude plugin marketplace add <source>`, `claude plugin install <plugin>@<marketplace>`) and [Plugins reference](https://code.claude.com/docs/en/plugins-reference) (`plugin.json`'s `mcpServers` field, pointing at an external `.mcp.json`). Both files pass `claude plugin validate`.

## Claude Desktop

Settings → Connectors → Add custom connector:

```
https://api.foretak.dev/mcp
```

No authentication.

Or install the desktop extension bundle (works offline once built, no `uv` required on the user's machine beforehand — the bundle still shells out to `uvx` at run time): see [`../mcpb/README.md`](../mcpb/README.md).

## Cursor

[<img src="https://cursor.com/deeplink/mcp-install-dark.svg" alt="Install in Cursor">](https://cursor.com/en/install-mcp?name=registry-mcp&config=eyJ1cmwiOiJodHRwczovL2FwaS5mb3JldGFrLmRldi9tY3AifQ%3D%3D)

`.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "registry-mcp": { "url": "https://api.foretak.dev/mcp" }
  }
}
```

## VS Code

[<img src="https://img.shields.io/badge/VS_Code-VS_Code?style=flat-square&label=Install%20Server&color=0098FF" alt="Install in VS Code">](https://insiders.vscode.dev/redirect?url=vscode%3Amcp%2Finstall%3F%257B%2522name%2522%253A%2522registry-mcp%2522%252C%2522type%2522%253A%2522http%2522%252C%2522url%2522%253A%2522https%253A%252F%252Fapi.foretak.dev%252Fmcp%2522%257D)

`.vscode/mcp.json`:

```json
{
  "servers": {
    "registry-mcp": {
      "type": "http",
      "url": "https://api.foretak.dev/mcp"
    }
  }
}
```

## Cline

See [`../llms-install.md`](../llms-install.md) — hosted and stdio settings blocks, plus the optional environment variables.

## ChatGPT — see D-031

## Generic stdio (any MCP client)

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

Optional env vars (`REGISTRY_MCP_CONTACT_EMAIL`, `REGISTRY_MCP_CACHE_PATH`, `COMPANIES_HOUSE_API_KEY`): see [`../README.md#configuration`](../README.md#configuration).
