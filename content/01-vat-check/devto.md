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
  "status": "active",
  "vat_registered": true,
  "vat_registered_at": "2024-04-15",
  "vat_number": "NO833285602MVA",
  "registers": {
    "foretaksregisteret": false,
    "mvaregisteret": true
  },
  "cached": false,
  "fetched_at": "2026-09-05T14:44:24.836394Z",
  "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/833285602",
  "license": "NLOD 2.0"
}
```

Four fields settle it:

- **`vat_registered: true`**, the answer.
- **`registers.mvaregisteret`**, the same fact as the register publishes it. Cite this one.
- **`vat_number`**: `NO833285602MVA` must match the number printed on the invoice. If it does not, stop.
- **`vat_registered_at: "2024-04-15"`**: an invoice dated before this charged VAT the supplier was not entitled to collect.

`status: "active"` is the second half of the question. A bankrupt or deleted entity comes back with a different `status` and a `notes` entry saying so.

## What skipping the check costs

It does not stop invoice fraud: in payment redirection the supplier is real and registered, and only the bank account is wrong. What it stops is deducting VAT that was never chargeable, and Norway has put figures on that:

- Skatteklagenemnda [NS 116/2018](https://www.skatteetaten.no/rettskilder/type/vedtak/skatteklagenemnda/etterberegning-av-inngaende-merverdiavgift-pa-bakgrunn-av-at-selger-ikke-var-registrert-i-merverdiavgiftsregisteret/), 15 September 2018: kr 691,100 of input VAT disallowed and kr 138,220 in penalty, for deducting VAT on invoices from a seller who was not registered.
- Skatteklagenemnda [NS 27/2019](https://www.skatteetaten.no/en/rettskilder/type/vedtak/skatteklagenemnda/etterberegning-av-inngaende-merverdiavgift-nar-selger-ikke-er-registrert-i-merverdiavgiftsregisteret.-skjerpet-tilleggsskatt/), 20 March 2019: kr 492,541 reversed, plus a 20% and a further 20% surcharge at kr 98,508 each. The board's line: *"Skattepliktige skulle selv ha kontrollert hvorfor selger utsteder fakturaer inkludert merverdiavgift når det ikke står MVA bak org nr."*

Both turn on [bokføringsforskriften § 5-1-2](https://lovdata.no/dokument/SF/forskrift/2004-12-01-1558/KAPITTEL_5-1): *"Dersom selger er registrert i Merverdiavgiftsregisteret, skal organisasjonsnummer etterfølges av bokstavene MVA."*

Finanstilsynet's [Rundskriv 15/2019](https://www.finanstilsynet.no/nyhetsarkiv/rundskriv/2019/veiledning-om-regnskapsforeres-og-regnskapsforerselskapers-etterlevelse-av-hvitvaskingsregelverket/) § 4.4.1 accepts an *oppslag* against Enhetsregisteret no older than three months, one month where the check rests on details the customer supplied, and asks for *notoritet* about the lookup: what was consulted, and when. `fetched_at`, `cached` and `source_url` are that record. Nothing is served more than 24 hours old.

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

`valid: false` is a normal 200-shaped answer, never an exception. One transposed digit is the usual cause. Fix it, or call `search_company` with the supplier's name.

**Well-formed, but nobody's.** `999999999` passes the MOD11 check and still is not a company:

<!-- uv run python content/call.py lookup_company '{"id": "999999999"}' (excerpt) -->
```json
{
  "error": {
    "code": "not_found",
    "message": "No entity with organisasjonsnummer 999999999 exists in Enhetsregisteret.",
    "hint": "The number is well-formed, so it may never have been issued or the entity may have been deleted. Call search_company with the company name instead."
  }
}
```

`not_found` means never issued, or deleted. Hold the payment and ask a human.

Source: Enhetsregisteret, NLOD 2.0. Same JSON over MCP and REST.
Repo: <https://github.com/foretak/registry-mcp>
