# Sjekk en britisk leverandør i Companies House fra Claude Code — samme verktøy som for brreg

En ny leverandør sender faktura med et britisk organisasjonsnummer — et *company registration number* — øverst. Finnes selskapet, driver det fortsatt, og har det levert det det skal? `registry-mcp` slår det opp i Companies House på company number, og i Brønnøysundregistrene / Enhetsregisteret (brreg) på organisasjonsnummer (orgnr, org.nr), med samme verktøy og samme JSON.

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp
# eller lokalt, over stdio: uvx registry-mcp
```

## Prompten

> Faktura fra Tesco PLC, company number 00445790. Er selskapet aktivt, og er det à jour hos Companies House?

## Kallet

`lookup_company(id="00445790", country="GB")`

<!-- uv run python content/call.py lookup_company '{"id": "00445790", "country": "GB"}' (utdrag) -->
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

Les `null` bokstavelig. Companies House publiserer verken mva-status eller antall ansatte — for noe selskap. `null` betyr «dette registeret sier det ikke», aldri «nei». Enhetsregisteret publiserer begge deler:

<!-- uv run python content/call.py lookup_company '{"id": "923609016", "country": "NO"}' (utdrag) -->
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

Én form, to registre, ærlig om hvem som publiserer hva.

## Den nyttige halvdelen

Companies House publiserer selskapenes egne innleveringsfrister, så `company_deadlines` siterer dem i stedet for å gjette. Deloitte LLP, per 4. september 2026:

<!-- uv run python content/call.py company_deadlines '{"id": "OC303675", "country": "GB", "today": "2026-09-04"}' (utdrag) -->
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

`days_until: -21` er ikke et utdatert svar. Companies House lar en oversittet frist bli liggende i fortiden i stedet for å rulle den fram, så det negative tallet *er* svaret: den confirmation statement-en er tre uker på overtid. Britiske frister flyttes heller aldri forbi en helg eller helligdag — en søndagsfrist er en søndagsfrist i loven, i motsetning til de norske. `applies_because` sier om datoen er sitert eller beregnet; siter den.

## To ting som feller agenten din

**Landkoden er `GB`, aldri `UK`.**

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

Hver feil navngir sin egen løsning i `hint`.

**Et britisk company number har ingen kontrollsiffer.** `validate_company_id` er derfor først og fremst en normaliserer:

<!-- uv run python content/call.py validate_company_id '{"id": "445790", "country": "GB"}' -->
```json
{
  "input": "445790",
  "valid": true,
  "normalized": "00445790",
  "formatted": null
}
```

Korte numre nullpolstres, prefikser gjøres til store bokstaver (`oc303675` → `OC303675`). Men `valid: true` betyr bare *formen stemmer*: et feiltastet britisk nummer er velformet og kommer tilbake som `404 not_found`. MOD11 fanger en tallombytting i et organisasjonsnummer; britene har ingenting å fange den med. Og enkeltpersonforetak og ansvarlige selskaper står ikke i Companies House i det hele tatt, så et britisk foretak som mangler, er ofte et helt reelt foretak.

Britiske data: Crown copyright, fri gjenbruk. Norske data: Enhetsregisteret, NLOD 2.0. Samme JSON over MCP og REST.
Kode: <https://github.com/foretak/registry-mcp>
