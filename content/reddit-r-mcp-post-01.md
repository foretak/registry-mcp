# r/mcp post 1 — posted via Claude in Chrome, 2026-09-05

Combines articles 05 (UK) and 04 (add your country) into one launch post for
r/mcp: problem first, one real output, honest limits, a question at the end so
the comments carry the thread. Text post; the dev.to link goes in the first
comment, never the body (`content/README.md`). Every JSON value below is real
output from the live server on 2026-09-04.

Writing rules applied (`~/sales-library`): Hopkins — specific and provable, no
adjectives; Dunford — frame is "the company registry MCP", the alternative is
one scraper per country; Cialdini — state a weakness before the claim; Kazanjy
— the reply in the comments is the product, answer everything within 24 h.

---

## Title

MCP server for company registries: Companies House (UK) and brreg (Norway) behind the same five tools, one folder per country. Which country should be third?

## Body

I kept running into the same thing: an agent is about to approve an invoice or onboard a supplier, and the one fact it needs — does this company exist, is it active, who is it really — lives in a national register with its own API, its own identifier rules and its own idea of what "active" means. So I built a server where each country is a folder and the agent sees one shape.

Five tools: `lookup_company`, `search_company`, `validate_company_id`, `company_deadlines`, `list_countries`. Two countries so far.

UK, Deloitte LLP, deadlines the register publishes:

```json
{
  "company_name": "DELOITTE LLP",
  "deadlines": [
    {"kind": "confirmation_statement", "due_date": "2026-08-14", "days_until": -21},
    {"kind": "annual_accounts", "due_date": "2027-02-28", "days_until": 177}
  ]
}
```

`days_until: -21` is real. Companies House leaves an overdue date in the past, and so do we. Norway returns the identical shape, except there the deadlines are computed from statute (brreg publishes none) and the record carries `vat_registered`, which Companies House does not publish at all. Every deadline says in `applies_because` whether it was quoted from the register or computed from a rule.

Things it cannot do, so you do not find out the hard way:

- A UK company number has no check digit. `validate_company_id` normalises `445790` to `00445790` but cannot catch a typo. Norway's MOD11 can.
- The country code is `GB`, never `UK`. Strict on purpose.
- UK lookups need a free Companies House API key; Norway needs nothing.

Adding a country is a subclass with four methods plus one import line. Nothing in `core/` changed for the UK except one field for register-published dates. Denmark's CVR access application went in this morning.

Hosted: `claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp`. Local: `uvx registry-mcp`. MIT, Python, `github.com/foretak/registry-mcp`.

Question for the room: if you are building agents that touch company data, which register would you want next, and what field do you keep having to look up by hand?

## First comment (posted by the author right after the post)

Longer write-up with the Norway side by side: https://dev.to/fargeroddotcom/check-a-uk-supplier-at-companies-house-from-claude-code-and-the-same-tool-works-for-norway-4mk8

The "your country is a folder" recipe, with the template module: https://dev.to/fargeroddotcom/add-your-countrys-company-registry-to-registry-mcp-in-an-afternoon-1pei
