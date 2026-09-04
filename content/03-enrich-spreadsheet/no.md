# Vask og berik et regneark med norske org.nr med én MCP-server

Alle økonomiavdelinger har denne fila: en leverandørkolonne med organisasjonsnummer (orgnr, org.nr) tastet inn for hånd. Noen av dem er feil. `registry-mcp` kontrollerer dem mot Brønnøysundregistrene / Enhetsregisteret (brreg) og fyller ut resten.

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp
# eller lokalt, over stdio: uvx registry-mcp
```

## Prompten

> Her er `suppliers.csv`. Sjekk hvert org.nr, luk ut dem som ikke er reelle foretak, og legg til organisasjonsform, status, mva-nummer og sted.

`suppliers.csv`:

<!-- inndatafil, tastet for hånd: content/03-enrich-spreadsheet/suppliers.csv -->
```csv
org_nr,supplier_name
923609016,Equinor
833285602,El Ansari Konsult
974760673,Registerenheten i Brønnøysund
833286602,Nordvik Regnskap
999999999,Fjord Design
923 609 016,Equinor (duplicate row)
```

## Steg 1 — `validate_company_id` på hver rad

Verktøyet gjør ingen nettverkskall, så kjør det på alle seks før du bruker et oppslag på noen av dem. To rader er interessante:

<!-- uv run python content/call.py validate_company_id '{"id": "923 609 016"}' (utdrag) -->
```json
{
  "input": "923 609 016",
  "valid": true,
  "normalized": "923609016",
  "formatted": "923 609 016"
}
```

<!-- uv run python content/call.py validate_company_id '{"id": "833286602"}' (utdrag) -->
```json
{
  "input": "833286602",
  "valid": false,
  "normalized": null,
  "reason": "'833286602' is not a valid Norwegian organisasjonsnummer.",
  "hint": "An organisasjonsnummer is nine digits with a MOD11 check digit, e.g. 923609016. If you have a company name instead, call search_company."
}
```

`normalized` er dedupliseringsnøkkelen — raden med mellomrom og rad 1 er samme foretak. Og `valid: false` er et helt vanlig svar, ikke et unntak: MOD11 fanger opp de ombyttede sifrene i `833286602`. Ett oppslag spart, én dårlig leverandør avdekket, gratis.

## Steg 2 — `lookup_company` på dem som står igjen

Fem rader, fem kall, rundt 60 linjer Python ([`enrich.py`](https://github.com/foretak/registry-mcp/tree/main/content/03-enrich-spreadsheet)):

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

Tre ulike feil, tre ulike løsninger, og `problem`-kolonnen holder dem fra hverandre:

- **`833286602`** — aldri et gyldig nummer. Noen har tastet feil. Søk på navn i stedet.
- **`999999999`** — består MOD11, men `lookup_company` svarer `not_found`. Gyldig er ikke det samme som ekte; bare nettverkskallet kan avgjøre det.
- **`974760673`** — en reell, aktiv enhet som rett og slett **ikke** står i Merverdiavgiftsregisteret. Kommer det en faktura med mva fra den, er det funnet ditt.

Én kolonne fortjener en kommentar. `EL ANSARI KONSULT` har tom `employees` fordi API-et returnerte `null` — registeret publiserer ikke noe tall. `null` er ikke `0`; rapporten har `employees_reported` ved siden av, slik at du kan skille «ukjent» fra «null ansatte» i stedet for å skrive et oppdiktet tall inn i regnearket.

Kilde: Enhetsregisteret, NLOD 2.0. Samme JSON over MCP og REST.
Kode (MIT): <https://github.com/foretak/registry-mcp>
