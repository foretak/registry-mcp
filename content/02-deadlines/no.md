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
      "applies_because": "This entity has reported employees and must file the monthly payroll report (a-melding) with NAV/Skatteetaten."
    },
    { "kind": "vat_return", "local_name": "Mva-melding", "statutory_date": "2026-10-10", "due_date": "2026-10-12", "rolled_forward": true, "period_label": "2026 term 4 (Jul–Aug)", "days_until": 11 },
    { "kind": "shareholder_register_statement", "local_name": "Aksjonærregisteroppgaven (RF-1086)", "statutory_date": "2027-01-31", "due_date": "2027-02-01", "rolled_forward": true, "days_until": 123 },
    { "kind": "tax_return", "local_name": "Skattemelding for næringsdrivende", "due_date": "2027-05-31", "days_until": 242 },
    { "kind": "general_meeting", "local_name": "Ordinær generalforsamling", "due_date": "2027-06-30", "days_until": 272 },
    { "kind": "annual_accounts", "local_name": "Årsregnskap", "statutory_date": "2027-07-31", "due_date": "2027-08-02", "rolled_forward": true, "days_until": 305 }
  ],
  "notes": [
    "Filing deadlines are computed assuming a calendar-year accounting period. A company with a deviating accounting year (avvikende regnskapsår) will have different actual dates, and Enhetsregisteret does not publish which companies those are."
  ]
}
```

To frister faller innenfor Q4: a-meldingen 5. oktober og mva-meldingen 12. oktober.

**Siter `due_date`, ikke `statutory_date`.** Den lovbestemte datoen for mva-meldingen er 10. oktober — en lørdag. `due_date` er 12. oktober, og `rolled_forward: true` sier hvorfor. Det samme gjelder årsregnskapet: 31. juli 2027 er en lørdag, så den reelle fristen er 2. august.

**`applies_because` er hjemmelen.** Ingenting her er gjettet ut fra organisasjonsform: a-meldingen dukker opp fordi enheten har rapportert ansatte, mva-meldingen fordi den står i Merverdiavgiftsregisteret. Regelen i verktøydokumentasjonen er å sitere den setningen, ikke å presentere datoen som en ubetinget kjensgjerning.

**Les `notes` før du sender svaret videre.** Lista forutsetter kalenderår som regnskapsår, fordi Enhetsregisteret ikke publiserer hvem som har avvikende regnskapsår. Alle årlige datoer over arver den forutsetningen.

En tom `deadlines`-liste er også et ekte svar — konkurs, slettet eller tvangsavviklet enhet, et underenhet, eller en organisasjonsform modulen ikke har klassifisert. `notes` sier hvilken av delene. Tjenesten utelater heller en plikt enn å finne på en.

Kilde: Enhetsregisteret, NLOD 2.0. Samme JSON over MCP og REST.
Kode (MIT): <https://github.com/foretak/registry-mcp>
