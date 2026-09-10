# Tre selskapsregistre, ett ord: hva «aktiv» egentlig betyr i Norge, Storbritannia og Sverige

En agent som skal godkjenne en faktura stiller ett spørsmål først: er selskapet fortsatt aktivt? `registry-mcp` svarer fra tre nasjonale registre — Brønnøysundregistrene / Enhetsregisteret (**brreg**) på **organisasjonsnummer** (orgnr, org.nr), **Companies House** på company number, og **Bolagsverket** på **organisationsnummer** — og returnerer det samme feltet fra alle tre:

```json
{"status": "active", "is_active": true}
```

De tre registrene mener ikke det samme med det. Bare ett av dem publiserer det i det hele tatt.

## Norge: fire flagg, og «aktiv» er fraværet av alle fire

brreg har ikke noe statusfelt. Det publiserer `konkurs`, `underAvvikling`, `underTvangsavviklingEllerTvangsopplosning` og `slettedato`, og `active` er det som står igjen når ingen av dem slår til. Grenen det er verdt å kopiere, er den som ligger *foran* `active`:

```python
if bankrupt is None and under_liquidation is None and under_compulsory_liquidation is None:
    return StatusResult(CompanyStatus.UNKNOWN, "The registry record does not carry status flags.", False, [note])

return StatusResult(CompanyStatus.ACTIVE, "Registered and active in Enhetsregisteret.", True, [])
```

`None` er ikke `False`. En payload uten flagg i det hele tatt blir `unknown`, aldri `active` — «registeret sa ingenting» og «registeret sa nei» er to forskjellige svar, og bare det ene er trygt å betale en faktura på.

## Storbritannia: én status, som kan si `active` om et selskap på vei ut

Companies House publiserer faktisk en status, og den mappes én til én — ingen utledning. Registeret publiserer i tillegg `company_status_detail`, separat, og kombinasjonen `active` + `active-proposal-to-strike-off` er både lovlig og vanlig. Den detaljen kommer som en setning i `notes`:

```
Companies House has published a proposal to strike this company off the register.
It is still active today, but it may be dissolved within about two months unless
the proposal is suspended. Do not treat it as a stable counterparty without
checking the filing history.
```

En britisk `active` med en note er altså et annet faktum enn en britisk `active` uten. Enumen kan ikke bære forskjellen, så setningen gjør det.

## Sverige: ingen status i det hele tatt, og tre uavhengige signaler i stedet

Bolagsverket publiserer ingenting som heter status. Det publiserer en avregistreringsdato; en *liste* over pågående prosesser (`KK` konkurs, `LI` likvidation, `FR` företagsrekonstruktion og flere, som kan komme to om gangen); og — fra Statistiska centralbyrån, i samme payload — et flagg for om enheten er *økonomisk aktiv*. Live, i dag:

<!-- curl https://api.foretak.dev/v1/SE/company/5560160680 (utdrag) -->
```json
{
  "name": "Telefonaktiebolaget LM Ericsson",
  "status": "active",
  "status_detail": "Registered with Bolagsverket and not marked as struck off or in any winding-up or restructuring procedure.",
  "is_active": true
}
```

Les `status_detail`, ikke `status`. Og les dette to ganger: for Sverige betyr `is_active: true` **registrert og ikke under avvikling**. Det betyr ikke at selskapet driver. SCBs flagg kan si NEJ om et selskap i full orden — nystiftet, hvilende, et holdingselskap uten drift — og det selskapet er fortsatt `active` her, med en note som sier det rett ut, og som sier at SCBs spørsmål er et annet enn det å stå i registeret.

Vi kunne ha funnet opp en `dormant`-status. Vi lot være. Det ville endret en delt enum for ett lands skyld, og en agent ville lest det som en påstand om norske og britiske selskaper vi ikke har data til å gjøre.

## Hva det kostet arkitekturen: ingenting i `core/`

Enumen er delt; utledningen er det ikke. Hver landmappe utleder sin egen status og skriver setningen som navngir signalet som avgjorde. Tre registre, tre urelaterte utledninger, én form ved verktøygrensen.

Det er argumentet for å legge et register bak et MCP-verktøy i stedet for en skraper. En skraper gir agenten ordet. Et verktøy kan gi den setningen.

```bash
claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp?src=article
# eller lokalt, over stdio: uvx registry-mcp
```

Data: Enhetsregisteret (NLOD 2.0), Companies House (Crown copyright), Bolagsverket og SCB (fritt under EUs forordning om verdifulle datasett — og Bolagsverket navngir ingen lisens, så det gjør ikke vi heller).

MIT: <https://github.com/foretak/registry-mcp>
