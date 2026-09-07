**Title:** In Sweden a sole trader's company number *is* their personnummer — so our MCP server stopped logging identifiers for that country

`registry-mcp` (company registry MCP: brreg / organisasjonsnummer, Companies House, and now Bolagsverket) added Sweden, and Sweden broke an assumption the other two had let us keep.

A Swedish sole trader's organisationsnummer *is* their national identity number — the same twelve digits, not derived from them. `validate_company_id` accepts twelve digits alongside ten for that reason.

Bolagsverket's own free API takes the identifier in a **POST body**, not a URL path — strange for a read-only lookup, until you count where URLs end up: access logs, proxy logs, browser history, the `curl` in the bug report.

So a registry module now declares one thing about itself, `id_may_be_personal`, and one function reads it:

```python
return None if registry.id_may_be_personal else query
```

Both surfaces call it before writing anything. The usage log keeps country, route, time, outcome and User-Agent; for such a country it stores no identifier at all. Access log off, exception logs record the route template not the path, cache failures log a key prefix. Verified in production: Swedish rows logged a null query while Norwegian rows still logged `923609016`.

Adding a country that sets the flag changes no route and no tool.

MIT: github.com/foretak/registry-mcp
