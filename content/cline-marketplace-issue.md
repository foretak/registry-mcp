# Cline MCP Marketplace submission — draft (file at https://github.com/cline/mcp-marketplace/issues/new?template=mcp-server-submission.yml)

**Status 2026-09-05:** icon and `llms-install.md` ready. Blocked only on the testing confirmation, which a human must do honestly: install Cline, give it the repo README (or `llms-install.md`) and watch it set the server up. Then the orchestrator files the issue with `gh`.

## Field values

**GitHub Repo URL**
https://github.com/foretak/registry-mcp

**Logo Image (400×400 PNG)**
https://api.foretak.dev/icon.png (also in the repo at `static/icon.png`)

**Reason for Addition**
registry-mcp gives Cline one set of five read-only tools for national company registries: look a company up by its identifier, search by name, validate an identifier offline, and get its statutory filing deadlines with the rule each date comes from. Norway (Brønnøysundregistrene) needs no key at all; the United Kingdom (Companies House) needs a free one. Every answer carries `source_url`, `fetched_at`, `license` and honest `null`s for what a register does not publish, so an agent can cite what it checked. Typical Cline uses: verify a supplier before paying an invoice, check VAT registration, enrich a spreadsheet of company numbers, or ask what a company must file next. Hosted endpoint (no install) or `uvx registry-mcp` locally. MIT.

**Testing confirmation**
[ ] I have tested giving Cline just the `README.md` / `llms-install.md` and watched it successfully set up the server. — TO BE TICKED BY KIM AFTER THE TEST.
