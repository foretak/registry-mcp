# Check a UK supplier at Companies House from Claude Code — and the same tool works for Norway

A new supplier sends an invoice with a company registration number on it. Is the company real, still trading, and up to date on its filings? `registry-mcp` answers from Companies House by company number — and from Brønnøysundregistrene / Enhetsregisteret (brreg) by organisasjonsnummer (orgnr, org.nr), with the same tool and the same JSON.

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp
# or locally, over stdio: uvx registry-mcp
```

## The prompt

> Invoice from Tesco PLC, company number 00445790. Is it active, and is it up to date at Companies House?

## The call

`lookup_company(id="00445790", country="GB")`

<!-- uv run python content/call.py lookup_company '{"id": "00445790", "country": "GB"}' (excerpt) -->
```json
{
  "id": "00445790",
  "name": "TESCO PLC",
  "legal_form_code": "plc",
  "legal_form": "Public limited company",
  "status": "active",
  "is_active": true,
  "registered_at": "1947-11-27",
  "registers": {"charges": false, "insolvency": false},
  "vat_registered": null,
  "employees": null,
  "source": "Companies House (UK)",
  "source_url": "https://find-and-update.company-information.service.gov.uk/company/00445790",
  "license": "Crown copyright — Companies House public register, free to re-use"
}
```

Read the `null`s literally. Companies House publishes no VAT status and no employee count, for any company — `null` means "this register does not say", never "no". Norway publishes both:

<!-- uv run python content/call.py lookup_company '{"id": "923609016", "country": "NO"}' (excerpt) -->
```json
{
  "country": "NO",
  "name": "EQUINOR ASA",
  "vat_registered": true,
  "vat_number": "NO923609016MVA",
  "employees": 21239,
  "source": "Enhetsregisteret (Brønnøysundregistrene)"
}
```

One shape, two registers, honest about which publishes what.

## The half that's actually useful

Companies House publishes each company's own filing due dates, so `company_deadlines` quotes them rather than guessing. Deloitte's LLP, on 4 September 2026:

<!-- uv run python content/call.py company_deadlines '{"id": "OC303675", "country": "GB", "today": "2026-09-04"}' (excerpt) -->
```json
{
  "company_name": "DELOITTE LLP",
  "today": "2026-09-04",
  "deadlines": [
    {"kind": "confirmation_statement", "local_name": "Confirmation statement (CS01)",
     "due_date": "2026-08-14", "days_until": -21,
     "applies_because": "Companies House publishes this date for the company itself; it is the register's own figure, not a calculation."},
    {"kind": "annual_accounts", "local_name": "Annual accounts",
     "due_date": "2027-02-28", "period_end": "2026-05-31", "days_until": 177}
  ]
}
```

`days_until: -21` is not a stale response. Companies House leaves an overdue date in the past instead of rolling it forward, so the negative number *is* the answer: that confirmation statement is three weeks late. UK deadlines never move off a weekend or bank holiday either — a Sunday deadline is a Sunday deadline in law. `applies_because` says whether a date is quoted or computed; quote it.

## Two things that will trip your agent

**The country code is `GB`, not `UK`.**

<!-- uv run python content/call.py validate_company_id '{"id": "12345", "country": "UK"}' -->
```json
{
  "error": {
    "code": "unsupported_country",
    "message": "No registry module is available for country 'UK'.",
    "hint": "Call list_countries (MCP) or GET /v1/countries (REST) for the current list. Supported right now: GB, NO."
  }
}
```

Every error names its own fix in `hint`.

**A UK company number has no check digit.** So `validate_company_id` is a normaliser first:

<!-- uv run python content/call.py validate_company_id '{"id": "445790", "country": "GB"}' -->
```json
{
  "input": "445790",
  "valid": true,
  "normalized": "00445790",
  "formatted": null
}
```

Short numbers are zero-padded, prefixes upper-cased (`oc303675` → `OC303675`). But `valid: true` means *the shape is right*, nothing more: a mistyped UK number is well-formed and comes back `404 not_found`. Norway's MOD11 catches a transposed digit; the UK has nothing to catch it with. And sole traders and ordinary partnerships are not on the register at all, so a missing UK business is often a real one.

Companies House data: Crown copyright, free to re-use. Norwegian data: Enhetsregisteret, NLOD 2.0. Same JSON over MCP and REST.
Repo: <https://github.com/foretak/registry-mcp>
