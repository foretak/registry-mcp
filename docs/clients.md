# Client setup

Hosted server: `https://api.foretak.dev/mcp` (Streamable HTTP, no authentication). Local: `uvx registry-mcp` (stdio). Full tool/response reference: [`../README.md`](../README.md), [`../static/llms-full.txt`](../static/llms-full.txt).

Three countries answer as of 0.3.0 — the United Kingdom (`GB`, Companies House, by company number), Norway (`NO`, brreg / Enhetsregisteret, by organisasjonsnummer) and Sweden (`SE`, Bolagsverket, by organisationsnummer). Every client below reaches all three through the same five tools; nothing on this page changes per country. Two things do: `search_company` returns `not_implemented` for `SE`, because Bolagsverket's free API has no name index, and a self-hosted install needs a credential for `GB` and for `SE` (see the last section).

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

## ChatGPT

ChatGPT reaches an MCP server through a custom connector, and deep research calls exactly two
tools — `search` and `fetch` (`DECISIONS.md` D-031) — which this server ships alongside the
five registry tools; `search`/`fetch` have no REST twin. Settings → Connectors → Add custom
connector:

```
https://api.foretak.dev/mcp
```

No authentication, no key, no account. If your plan does not show custom connectors under
Settings → Connectors, turn on Settings → Security and login → Developer mode first, then add
the URL from <https://chatgpt.com/plugins>.

`search(query)` takes one free-text query — a name, a national identifier, or a name plus a
country — and returns `{"results": [{"id", "title", "url"}]}`; `fetch(id)` takes a result's
`id` (`"NO:923609016"`, `"SE:5560160680"`) and returns that company's register record and
statutory filing deadlines as Markdown, with both full JSON reports in `metadata`. A Swedish
company reaches ChatGPT through `search` only when the query is the identifier itself — the
name fan-out skips `SE`, which has no name index.

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

Optional env vars: `REGISTRY_MCP_CONTACT_EMAIL`, `REGISTRY_MCP_CACHE_PATH`, `COMPANIES_HOUSE_API_KEY` (`GB`, free and instant) and `BOLAGSVERKET_CLIENT_ID` / `BOLAGSVERKET_CLIENT_SECRET` (`SE`, an OAuth 2 pair Bolagsverket issues on request). Norway needs none of them. A missing credential takes out only its own country: the others keep answering, and the failing one returns `upstream_error` naming the variable. Full table: [`../README.md#configuration`](../README.md#configuration).

The hosted server at `api.foretak.dev` has all of these configured already, which is why every "no authentication" line above is true — the credentials are the *upstream registers'*, not yours.
