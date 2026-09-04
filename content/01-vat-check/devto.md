# Check a Norwegian supplier is VAT-registered before you pay the invoice

Your agent is about to approve an invoice charging 25% MVA. Is the supplier actually in Merverdiavgiftsregisteret? `registry-mcp` answers from Brønnøysundregistrene / Enhetsregisteret (brreg), by organisasjonsnummer (orgnr, org.nr).

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp
# or locally, over stdio: uvx registry-mcp
```

## The prompt

> Invoice 2026-0417 from EL ANSARI KONSULT, org.nr 833 285 602, charges NOK 4 000 + 25% MVA. Before I pay: is this supplier VAT-registered, and is the business active?

## The call

`lookup_company(id="833285602")`

<!-- uv run python content/call.py lookup_company '{"id": "833285602"}' (excerpt) -->
```json
{
  "name": "EL ANSARI KONSULT",
  "legal_form_code": "ENK",
  "legal_form": "Sole proprietorship",
  "status": "active",
  "is_active": true,
  "vat_registered": true,
  "vat_registered_at": "2024-04-15",
  "vat_number": "NO833285602MVA",
  "registers": {
    "foretaksregisteret": false,
    "mvaregisteret": true
  },
  "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/833285602",
  "license": "NLOD 2.0"
}
```

Four fields settle it:

- **`vat_registered: true`** — the answer.
- **`registers.mvaregisteret`** — the same fact as the register publishes it, next to the other four registers. Cite this one.
- **`vat_number`** — `NO833285602MVA` must match the number printed on the invoice. If it doesn't, stop.
- **`vat_registered_at: "2024-04-15"`** — an invoice dated before this charged VAT the supplier wasn't entitled to collect.

`status: "active"` is the second half of the question. A bankrupt or deleted entity comes back with a different `status` and a `notes` entry saying so — the tool docstring is blunt about it: *"Read the returned `notes` before acting on the result."*

## The two ways this says no

**Malformed number.** `validate_company_id` is free and does no network call, so run it on invoice input first:

<!-- uv run python content/call.py validate_company_id '{"id": "833286602"}' -->
```json
{
  "input": "833286602",
  "valid": false,
  "normalized": null,
  "reason": "'833286602' is not a valid Norwegian organisasjonsnummer.",
  "hint": "An organisasjonsnummer is nine digits with a MOD11 check digit, e.g. 923609016. If you have a company name instead, call search_company."
}
```

`valid: false` is a normal 200-shaped answer, never an exception. One transposed digit is the usual cause. Fix it, or call `search_company` with the supplier's name — retrying the same string will not help.

**Well-formed, but nobody's.** `999999999` passes the MOD11 check and still isn't a company:

<!-- uv run python content/call.py lookup_company '{"id": "999999999"}' (excerpt) -->
```json
{
  "error": {
    "code": "not_found",
    "message": "No entity with organisasjonsnummer 999999999 exists in Enhetsregisteret.",
    "hint": "... Call search_company with the company name instead."
  }
}
```

A valid orgnr is not an existing company. `not_found` means never issued, or deleted — hold the payment and ask a human.

Source: Enhetsregisteret, NLOD 2.0. Same JSON over MCP and REST.
Repo: <https://github.com/foretak/registry-mcp>
