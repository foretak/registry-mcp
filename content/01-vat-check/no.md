# Sjekk at leverandøren faktisk er mva-registrert før du betaler fakturaen

Agenten din står i ferd med å godkjenne en faktura med 25 % mva. Er leverandøren i det hele tatt registrert i Merverdiavgiftsregisteret? `registry-mcp` slår det opp i Brønnøysundregistrene / Enhetsregisteret (brreg) på organisasjonsnummer (orgnr, org.nr).

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp
# eller lokalt, over stdio: uvx registry-mcp
```

## Prompten

> Faktura 2026-0417 fra EL ANSARI KONSULT, org.nr 833 285 602, er på 4 000 kroner + 25 % mva. Før jeg betaler: er leverandøren mva-registrert, og er foretaket aktivt?

## Kallet

`lookup_company(id="833285602")`

<!-- uv run python content/call.py lookup_company '{"id": "833285602"}' (utdrag) -->
```json
{
  "name": "EL ANSARI KONSULT",
  "legal_form_code": "ENK",
  "legal_form_local": "Enkeltpersonforetak",
  "status": "active",
  "is_active": true,
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

Fire felter avgjør saken:

- **`vat_registered: true`** — selve svaret.
- **`registers.mvaregisteret`** — samme faktum slik registeret publiserer det, ved siden av de fire andre registrene. Det er dette du siterer.
- **`vat_number`** — `NO833285602MVA` må stå på fakturaen. Stemmer det ikke, stopper du.
- **`vat_registered_at: "2024-04-15"`** — en faktura datert før dette krevde inn mva leverandøren ikke hadde adgang til å kreve.

`status: "active"` svarer på andre halvdel av spørsmålet. Er foretaket konkurs eller slettet, kommer det en annen `status` og en `notes`-linje som sier hvorfor. Dokumentasjonen til verktøyet er tydelig på det: les `notes` før du handler på svaret.

## Hva det koster å la være

Kontrollen stopper ikke fakturasvindel: ved betalingsomdirigering er leverandøren reell og registrert, og det er kontonummeret som er feil. Det den stopper, er fradrag for mva som aldri kunne kreves. Norge har satt tall på det:

- Skatteklagenemnda [NS 116/2018](https://www.skatteetaten.no/rettskilder/type/vedtak/skatteklagenemnda/etterberegning-av-inngaende-merverdiavgift-pa-bakgrunn-av-at-selger-ikke-var-registrert-i-merverdiavgiftsregisteret/), 15. september 2018: kr 691 100 i inngående merverdiavgift nektet fradragsført, og kr 138 220 i tilleggsavgift, fordi kjøper fradragsførte mva på fakturaer fra en selger som ikke var registrert i Merverdiavgiftsregisteret.
- Skatteklagenemnda [NS 27/2019](https://www.skatteetaten.no/en/rettskilder/type/vedtak/skatteklagenemnda/etterberegning-av-inngaende-merverdiavgift-nar-selger-ikke-er-registrert-i-merverdiavgiftsregisteret.-skjerpet-tilleggsskatt/), 20. mars 2019: kr 492 541 etterberegnet, pluss 20 % tilleggsskatt og ytterligere 20 % skjerpet tilleggsskatt, kr 98 508 hver. Nemnda skrev: «Skattepliktige skulle selv ha kontrollert hvorfor selger utsteder fakturaer inkludert merverdiavgift når det ikke står MVA bak org nr.»

Begge hviler på [bokføringsforskriften § 5-1-2](https://lovdata.no/dokument/SF/forskrift/2004-12-01-1558/KAPITTEL_5-1): «Dersom selger er registrert i Merverdiavgiftsregisteret, skal organisasjonsnummer etterfølges av bokstavene MVA.»

Finanstilsynets [rundskriv 15/2019](https://www.finanstilsynet.no/nyhetsarkiv/rundskriv/2019/veiledning-om-regnskapsforeres-og-regnskapsforerselskapers-etterlevelse-av-hvitvaskingsregelverket/) punkt 4.4.1 godtar et oppslag mot Enhetsregisteret som ikke er eldre enn tre måneder, og setter én måned der kontrollen må baseres på firmaopplysninger som fremlegges av kunden. Det krever i tillegg notoritet om selve oppslaget: hva som ble slått opp, og når. `fetched_at`, `cached` og `source_url` er den dokumentasjonen, i et format du kan lagre ved siden av bilaget. Ingenting serveres eldre enn 24 timer.

## De to måtene dette sier nei på

**Ugyldig nummer.** `validate_company_id` er gratis og gjør ingen nettverkskall, så kjør det på fakturainput først:

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

`valid: false` er et helt vanlig svar, ikke et unntak. Som regel er det to sifre som har byttet plass. Rett det opp, eller kall `search_company` med navnet — å prøve samme streng på nytt hjelper ikke.

**Gyldig, men ingens.** `999999999` består MOD11-kontrollen og er likevel ikke et foretak:

<!-- uv run python content/call.py lookup_company '{"id": "999999999"}' (utdrag) -->
```json
{
  "error": {
    "code": "not_found",
    "message": "No entity with organisasjonsnummer 999999999 exists in Enhetsregisteret.",
    "hint": "The number is well-formed, so it may never have been issued or the entity may have been deleted. Call search_company with the company name instead."
  }
}
```

Et gyldig orgnr er ikke det samme som et eksisterende foretak. `not_found` betyr at nummeret aldri er tildelt, eller at enheten er slettet. Uansett: hold igjen betalingen og spør et menneske.

Kilde: Enhetsregisteret, NLOD 2.0. Samme JSON over MCP og REST.
Kode (MIT): <https://github.com/foretak/registry-mcp>
