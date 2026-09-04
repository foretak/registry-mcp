**Title:** Companies House from an MCP tool — UK company lookup and filing deadlines, same JSON as the Norwegian register (brreg)

`registry-mcp` added the UK as country two. Give it a company number, get the Companies House record and the filing dates the register publishes.

<!-- uv run python content/call.py company_deadlines '{"id": "OC303675", "country": "GB", "today": "2026-09-04"}' (excerpt) -->
```json
{
  "company_name": "DELOITTE LLP",
  "today": "2026-09-04",
  "deadlines": [
    {"kind": "confirmation_statement", "due_date": "2026-08-14", "days_until": -21},
    {"kind": "annual_accounts", "due_date": "2027-02-28", "days_until": 177}
  ]
}
```

`days_until: -21` is real — Companies House leaves an overdue date in the past rather than rolling it forward. Each deadline's `applies_because` says whether it was quoted from the register or computed from a statute.

Two gotchas: the code is `GB`, never `UK`; and a UK company number has no check digit, so `validate_company_id` normalises (`445790` → `00445790`) but cannot catch a typo the way Norway's MOD11 does.

Norway (`brreg`, organisasjonsnummer/orgnr) returns the identical shape, including `vat_registered` — which Companies House does not publish at all.

`claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp`, or `uvx registry-mcp`. GB needs a free Companies House key.

MIT: github.com/foretak/registry-mcp
