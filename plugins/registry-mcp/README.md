# Company Check — UK, Sweden & Norway business registers

A Claude Code plugin that does one job end to end: **check a company before you deal with it**,
straight from its own national business register.

```
/plugin marketplace add foretak/registry-mcp
/plugin install registry-mcp@foretak
```

## What it bundles

| Component | What it does |
|---|---|
| **MCP server** (`.mcp.json`) | The hosted server at `https://api.foretak.dev/mcp` over Streamable HTTP. Read-only, no account, no API key, nothing to configure. |
| **Skill** (`skills/company-check/SKILL.md`) | Teaches Claude the three workflows: the counterparty check, the filing-deadline check, and reading a register's silences honestly. Activates on its own when you talk about checking a company. |
| `/check-supplier` | Existence, current status and filing health for one identifier — with a closing section on what the check does **not** establish. |
| `/filing-deadlines` | What must be filed next, when, and under which statutory provision. |
| `/enrich-company-list` | A list or spreadsheet of company numbers resolved to name, status, address, industry code and VAT registration, one row each with a source URL. |

## Coverage

| Country | Register | Identifier | Example |
|---|---|---|---|
| `GB` | Companies House | company number (CRN) | `00445790` |
| `NO` | Enhetsregisteret / Brønnøysundregistrene (brreg) | organisasjonsnummer (orgnr) | `923609016` |
| `SE` | Bolagsverket | organisationsnummer | `5560160680` |

One identical JSON shape for all three. Sweden is identifier-lookup only — Bolagsverket's free
API has no name-search operation, and a name search for `SE` says so rather than returning
nothing.

## What it is not

**This is not sanctions, PEP or adverse-media screening; it does not verify bank account or payment details; and it is not a defence against payment fraud.** The commonest invoice fraud
impersonates a real, active, correctly-registered supplier and forges only the bank details, so a
clean result here is *consistent with* that fraud rather than evidence against it. Confirm bank
details through a channel you already trust.

## Data, licences and privacy

Every response carries `source`, `source_url`, `license` and `fetched_at`. Norway is NLOD 2.0;
the United Kingdom is Crown copyright, free to re-use; Sweden is free re-use under the EU Open
Data Directive high-value datasets regime, for which Bolagsverket names no licence — so neither
do we.

Privacy policy: <https://api.foretak.dev/legal/privacy> · Terms: <https://api.foretak.dev/legal/terms>
· Source: <https://github.com/foretak/registry-mcp> · MIT · `hello@foretak.dev`
