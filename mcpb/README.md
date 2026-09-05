# registry-mcp — Claude Desktop extension (MCPB)

`manifest.json` packages registry-mcp as an [MCP Bundle](https://github.com/modelcontextprotocol/mcpb) (`anthropics/mcpb` redirects there) for one-click install in Claude Desktop. It does not vendor any server code: `mcp_config` launches the already-published PyPI package with `uvx registry-mcp`, the same command used everywhere else in this repo (README, `llms-install.md`, `server.json`). `icon.png` is a copy of [`../static/icon.png`](../static/icon.png) — `mcpb pack` only sees files inside this directory, so the bundle needs its own copy; if the source icon changes, re-copy it here.

## Build

Requires Node (for `npx`); the resulting bundle itself only requires Python 3.12+ and `uv`/`uvx` on the installing machine.

```bash
npx @anthropic-ai/mcpb validate mcpb/manifest.json   # schema + icon check
npx @anthropic-ai/mcpb pack mcpb registry-mcp.mcpb    # from the repo root
```

`pack` runs the same validation first. Both commands were run against this manifest and passed (`Manifest schema validation passes!`; the only output was an icon-size warning — see below). **Do not commit the built `.mcpb`** — it's a generated binary, not source; `.gitignore` excludes `*.mcpb` repo-wide.

## Known gaps before submitting

- **Icon size.** `static/icon.png` is 400×400; `mcpb validate` warns (does not fail) that 512×512 is recommended for Claude Desktop's display. Cosmetic, not blocking.
- **Privacy policy.** The submission form requires an HTTPS privacy-policy URL, and this repo currently only has [`../legal/terms.md`](../legal/terms.md) (terms, not a privacy policy) — the manifest has no `privacy_policies` field because there is nothing true to put in it yet. Terms already state what the service does and does not do with data (no profiling, no enrichment, logs only what's needed to run the service); a standalone privacy policy at an HTTPS URL still needs writing before this can be submitted.

## Submit

Desktop extensions use a separate form, no Claude Team/Enterprise organization required:

**<https://clau.de/desktop-extention-submission>**

(That is the literal URL Anthropic publishes for this form — the misspelling is theirs, not a typo here.)

## User-configurable values (`user_config` in `manifest.json`)

| Key | Sensitive | Required | Purpose |
|---|---|---|---|
| `companies_house_api_key` | yes | no | Enables UK lookups; unset means Norway-only, GB calls return `upstream_error`. |
| `contact_email` | no | no | Sent in the `User-Agent` to the national registry. |
| `cache_path` | no | no | SQLite response-cache path; defaults to `./data/cache.sqlite3`. |

Claude Desktop prompts for these at install/configure time and passes them into `mcp_config.env` as `${user_config.<key>}`.

## Schema sources

`https://github.com/anthropics/mcpb` redirects to `https://github.com/modelcontextprotocol/mcpb`. Read from there: `MANIFEST.md` (field list, `server`/`mcp_config`/`user_config` shapes, the `uv` server type added at manifest version 0.4 for bundling a `pyproject.toml`-declared Python source tree) and the JSON schemas under `schemas/` (`mcpb-manifest-v0.4.schema.json` confirms `server.type` enum `python|node|binary|uv` and that `entry_point` sits in `server`'s required array). This manifest uses `"manifest_version": "0.3"` and `"type": "python"` — the `uv` server type is for bundling source, which this manifest deliberately doesn't do. Fields relied on: top-level `manifest_version`, `name`, `version`, `description`, `author`, `icon`, `server.{type,entry_point,mcp_config}`, `mcp_config.{command,args,env}`, and `user_config.<key>.{type,title,description,sensitive,required}`.

`entry_point` is schema-required but descriptive only — confirmed empirically, not just from the docs: this manifest's `entry_point` points at `../src/registry_mcp/mcp/server.py`, outside anything `mcpb pack` actually zips, and both `mcpb validate mcpb/manifest.json` and `mcpb pack mcpb <out>.mcpb` still pass (schema validation passes; the only diagnostic was the icon-size warning above). `mcp_config` is what Claude Desktop actually executes — a real build of this manifest was packed and inspected: it contains exactly `manifest.json` and `icon.png`, no server code, confirming the `uvx` launch path works with nothing vendored.
