# Validate and enrich a spreadsheet of Norwegian org.nrs with one MCP server

Every finance team has this file: a supplier column of organisasjonsnummer (orgnr, org.nr) typed in by hand. Some are wrong. `registry-mcp` checks them against Brønnøysundregistrene / Enhetsregisteret (brreg) and fills in the rest.

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp
# or locally, over stdio: uvx registry-mcp
```

## The prompt

> Here's `suppliers.csv`. Check every org.nr, drop the ones that aren't real companies, and add legal form, status, VAT number and city.

`suppliers.csv`:

<!-- input file, hand-typed: content/03-enrich-spreadsheet/suppliers.csv -->
```csv
org_nr,supplier_name
923609016,Equinor
833285602,El Ansari Konsult
974760673,Registerenheten i Brønnøysund
833286602,Nordvik Regnskap
999999999,Fjord Design
923 609 016,Equinor (duplicate row)
```

## Step 1 — `validate_company_id` on every row

It does no network call, so run it on all six before spending a lookup on any. Two rows are interesting:

<!-- uv run python content/call.py validate_company_id '{"id": "923 609 016"}' (excerpt) -->
```json
{
  "input": "923 609 016",
  "valid": true,
  "normalized": "923609016",
  "formatted": "923 609 016"
}
```

<!-- uv run python content/call.py validate_company_id '{"id": "833286602"}' (excerpt) -->
```json
{
  "input": "833286602",
  "valid": false,
  "normalized": null,
  "reason": "'833286602' is not a valid Norwegian organisasjonsnummer.",
  "hint": "An organisasjonsnummer is nine digits with a MOD11 check digit, e.g. 923609016. If you have a company name instead, call search_company."
}
```

`normalized` is the dedupe key — the spaced row and row 1 are the same company. And `valid: false` is a plain answer, not an exception: MOD11 catches the transposed digit in `833286602`. That's one lookup saved and one bad supplier caught for free.

## Step 2 — `lookup_company` on the survivors

Five rows, five calls, ~60 lines of Python ([`enrich.py`](https://github.com/foretak/registry-mcp/tree/main/content/03-enrich-spreadsheet)):

<!-- uv run python content/03-enrich-spreadsheet/enrich.py content/03-enrich-spreadsheet/suppliers.csv content/03-enrich-spreadsheet/suppliers-enriched.csv -->
```csv
org_nr,supplier_name,valid,normalized,name,legal_form,status,vat_registered,vat_number,employees,city,problem
923609016,Equinor,True,923609016,EQUINOR ASA,Public limited company,active,True,NO923609016MVA,21239,STAVANGER,
833285602,El Ansari Konsult,True,833285602,EL ANSARI KONSULT,Sole proprietorship,active,True,NO833285602MVA,,OSLO,
974760673,Registerenheten i Brønnøysund,True,974760673,REGISTERENHETEN I BRØNNØYSUND,Organisational unit of a public body,active,False,,492,BRØNNØYSUND,not VAT-registered — do not accept MVA on an invoice
833286602,Nordvik Regnskap,False,,,,,,,,,'833286602' is not a valid Norwegian organisasjonsnummer.
999999999,Fjord Design,True,999999999,,,,,,,,not_found: No entity with organisasjonsnummer 999999999 exists in Enhetsregisteret.
923 609 016,Equinor (duplicate row),True,923609016,EQUINOR ASA,Public limited company,active,True,NO923609016MVA,21239,STAVANGER,
```

Three different failures, three different fixes, and the `problem` column keeps them apart:

- **`833286602`** — never a valid number. Someone mistyped it. Search by name.
- **`999999999`** — passes MOD11, but `lookup_company` raises `not_found`. Well-formed is not the same as real; only the network call can tell you.
- **`974760673`** — a real, active entity that is simply **not** in Merverdiavgiftsregisteret. If it sends you an invoice with MVA on it, that's the finding.

One column deserves a note. `EL ANSARI KONSULT`'s `employees` is blank because the API returned `null` — the register publishes no figure. `null` is not `0`; the report carries `employees_reported` so you can tell "unknown" from "zero" instead of writing a false headcount into your spreadsheet.

Source: Enhetsregisteret, NLOD 2.0. Same JSON over MCP and REST.
Repo: <https://github.com/foretak/registry-mcp>
