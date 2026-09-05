**Title:** Stop your agent paying VAT to a supplier that isn't VAT-registered (Norway, brreg MCP)

`registry-mcp` puts Brønnøysundregistrene / Enhetsregisteret behind an MCP tool: give it an organisasjonsnummer (orgnr), get the company.

<!-- uv run python content/call.py lookup_company '{"id": "833285602"}' (excerpt) -->
```json
{
  "name": "EL ANSARI KONSULT",
  "status": "active",
  "vat_registered": true,
  "vat_registered_at": "2024-04-15",
  "vat_number": "NO833285602MVA",
  "fetched_at": "2026-09-05T14:44:24.836394Z"
}
```

`vat_number` must match the invoice; `vat_registered_at` catches invoices dated before the supplier could charge MVA.

It does not stop invoice fraud, where only the bank account is wrong. It stops the deduction Skatteklagenemnda reverses: [NS 116/2018](https://www.skatteetaten.no/rettskilder/type/vedtak/skatteklagenemnda/etterberegning-av-inngaende-merverdiavgift-pa-bakgrunn-av-at-selger-ikke-var-registrert-i-merverdiavgiftsregisteret/), kr 691,100 disallowed plus kr 138,220 penalty; [NS 27/2019](https://www.skatteetaten.no/en/rettskilder/type/vedtak/skatteklagenemnda/etterberegning-av-inngaende-merverdiavgift-nar-selger-ikke-er-registrert-i-merverdiavgiftsregisteret.-skjerpet-tilleggsskatt/), kr 492,541 plus two 20% surcharges. [Rundskriv 15/2019](https://www.finanstilsynet.no/nyhetsarkiv/rundskriv/2019/veiledning-om-regnskapsforeres-og-regnskapsforerselskapers-etterlevelse-av-hvitvaskingsregelverket/) § 4.4.1 wants an Enhetsregisteret oppslag no older than three months, and a record of it: `fetched_at` and `source_url`, never over 24 h old.

`validate_company_id` never throws: a bad check digit comes back as `valid: false` with a `hint`.

`claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp`, or `uvx registry-mcp`. Source: NLOD 2.0. MIT: github.com/foretak/registry-mcp
