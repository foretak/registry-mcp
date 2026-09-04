**Title:** Cleaning a supplier spreadsheet with an MCP server: validate first, then look up

Six Norwegian org.nrs (organisasjonsnummer), typed by a human. `validate_company_id` is free and does no network call, so it runs on all six; `lookup_company` only runs on the survivors.

<!-- uv run python content/03-enrich-spreadsheet/enrich.py content/03-enrich-spreadsheet/suppliers.csv content/03-enrich-spreadsheet/suppliers-enriched.csv (columns trimmed) -->
```csv
org_nr,valid,name,status,vat_registered,problem
923609016,True,EQUINOR ASA,active,True,
974760673,True,REGISTERENHETEN I BRØNNØYSUND,active,False,not VAT-registered
833286602,False,,,,'833286602' is not a valid Norwegian organisasjonsnummer.
999999999,True,,,,not_found: No entity with organisasjonsnummer 999999999 exists
923 609 016,True,EQUINOR ASA,active,True,
```

Three distinct failures: a bad MOD11 check digit, a well-formed number nobody was ever issued, and a real entity that just isn't VAT-registered. `normalized` also gives you the dedupe key, so the spaced row collapses onto row 1.

Script + CSVs: github.com/foretak/registry-mcp/tree/main/content · `uvx registry-mcp`
