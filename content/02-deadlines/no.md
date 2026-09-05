# Alle innleveringsfrister for et norsk AS dette kvartalet, i ett verktøykall

«Hva skylder vi Skatteetaten og Regnskapsregisteret nå?» er ikke et spørsmål agenten din bør svare på fra hukommelsen. `registry-mcp` regner det ut fra opplysningene i Brønnøysundregistrene / Enhetsregisteret (brreg), på organisasjonsnummer (orgnr, org.nr).

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp
# eller lokalt, over stdio: uvx registry-mcp
```

## Prompten

> I dag er det 1. oktober 2026. For org.nr 923 609 016: list opp alle lovpålagte frister som kommer, med dato og begrunnelse.

## Kallet

`company_deadlines(id="923609016", today="2026-10-01")`

Send alltid med `today`. Fristene blir **regnet ut, ikke hentet**, så samme foretak og samme `today` gir alltid samme liste — det er det som gjør svaret testbart, i stedet for «det serverklokka sa».

<!-- uv run python content/call.py company_deadlines '{"id": "923609016", "today": "2026-10-01"}' (første frist i sin helhet, resten forkortet) -->
```json
{
  "company_name": "EQUINOR ASA",
  "today": "2026-10-01",
  "deadlines": [
    {
      "kind": "payroll_report",
      "name": "Monthly payroll report (A-melding)",
      "local_name": "A-melding",
      "authority": "NAV / Skatteetaten (A-ordningen)",
      "statutory_date": "2026-10-05",
      "due_date": "2026-10-05",
      "rolled_forward": false,
      "period_label": "2026-09",
      "recurrence": "monthly",
      "days_until": 4,
      "applies_because": "This entity has reported employees and must file the monthly payroll report (a-melding) with NAV/Skatteetaten (a-opplysningsforskriften § 2-1)."
    },
    { "kind": "vat_return", "local_name": "Mva-melding", "statutory_date": "2026-10-10", "due_date": "2026-10-12", "rolled_forward": true, "period_label": "2026 term 4 (Jul–Aug)", "days_until": 11 },
    { "kind": "shareholder_register_statement", "local_name": "Aksjonærregisteroppgaven (RF-1086)", "statutory_date": "2027-01-31", "due_date": "2027-02-01", "rolled_forward": true, "days_until": 123 },
    { "kind": "tax_return", "local_name": "Skattemelding for næringsdrivende", "due_date": "2027-05-31", "days_until": 242 },
    { "kind": "general_meeting", "local_name": "Ordinær generalforsamling", "due_date": "2027-06-30", "days_until": 272 },
    { "kind": "annual_accounts", "local_name": "Årsregnskap", "statutory_date": "2027-07-31", "due_date": "2027-07-31", "rolled_forward": false, "days_until": 303 }
  ],
  "notes": [
    "Filing deadlines are computed assuming a calendar-year accounting period. Enhetsregisteret does not publish a company's accounting year. For a financial year ending between 1 January and 30 June, regnskapsloven § 8-3(1) sets a different deadline — 1 February, not 31 July — so a deviating year changes which rule applies, not just the date. The Ministry may also postpone the accounts deadline by up to one month by regulation (§ 8-3(1)). Verify against Regnskapsregisteret before relying on an annual date."
  ]
}
```

To frister faller innenfor Q4: a-meldingen 5. oktober og mva-meldingen 12. oktober.

**Siter `due_date`, ikke `statutory_date`.** Den lovbestemte datoen for mva-meldingen er 10. oktober — en lørdag. `due_date` er 12. oktober, og `rolled_forward: true` sier hvorfor. Årsregnskapsfristen får **ikke** samme behandling: 31. juli 2027 er også en lørdag, men `rolled_forward` er fortsatt `false` og `due_date` blir stående på 31. juli — regnskapsloven § 8-3(1) fritar bare for forsinkelsesgebyr dersom årsregnskapet er avsendt *før* 1. august, så å flytte fristen til mandag ville gitt en dato gebyret allerede løper på. Om en frist flyttes avgjøres per frist, ut fra fristens egen hjemmel, ikke som én regel for hele landet.

**`applies_because` er hjemmelen.** Ingenting her er gjettet ut fra organisasjonsform: a-meldingen dukker opp fordi enheten har rapportert ansatte, mva-meldingen fordi den står i Merverdiavgiftsregisteret. Hver setning navngir også bestemmelsen datoen kommer fra. Regelen i verktøydokumentasjonen er å sitere den setningen, ikke å presentere datoen som en ubetinget kjensgjerning.

**Les `notes` før du sender svaret videre.** `annual_accounts` og `general_meeting` forutsetter kalenderår som regnskapsår, fordi Enhetsregisteret ikke publiserer det reelle regnskapsåret — et regnskapsår som slutter i første halvår gir en frist **1. februar**, ikke bare en forskjøvet dato ut fra 31. juli. `tax_return` og `shareholder_register_statement` har ikke den forutsetningen: de følger skattleggingsperioden, ikke regnskapsåret.

En tom `deadlines`-liste er også et ekte svar — konkurs, slettet eller tvangsavviklet enhet, et underenhet, eller en organisasjonsform modulen ikke har klassifisert. `notes` sier hvilken av delene. Tjenesten utelater heller en plikt enn å finne på en.

Kilde: Enhetsregisteret, NLOD 2.0. Samme JSON over MCP og REST.
Kode (MIT): <https://github.com/foretak/registry-mcp>
