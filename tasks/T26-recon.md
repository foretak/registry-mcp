# T26-recon — Sweden / Bolagsverket: sourced facts for `SWEDEN_SPEC.md` and `registries/se/`

Owner: Opus R (T26r). Fetched **2026-09-05**. Full write-up with verbatim quotes:
`~/research/registry-mcp/02-registers-landscape/02b-sweden-api-shape-and-law.md`.
Raw OpenAPI document saved at `~/research/registry-mcp/02-registers-landscape/02b-sweden-openapi.json`.

Confidence: **[H]** primary source read directly · **[M]** secondary / corroborating · **[L]** inferred.

**How it was obtained** (reusable): Bolagsverket's WSO2 dev portal answers **anonymously** — no account needed. web.archive.org was offline all session. bolagsverket.se serves normally to `curl` with a desktop Chrome `User-Agent` **plus** `Accept-Language: sv-SE,sv;q=0.9`; the CAPTCHA keys on headers, not IP.

---

## API shape

- **[H]** OpenAPI **3.0.3**, `title "VärdefullaDatamängder"`, `version "v1"`. Downloadable with no auth: `https://portal.api.bolagsverket.se/api/am/devportal/v3/apis/ff8f9a91-1fdd-4705-8836-c1906581162f/swagger`. Byte-identical (schemas + examples) to an independent 2026-05-18 capture in `strale-io/strale`; field names also matched by Norwegian gov repo `data-altinn-no/plugin-nsg`.
- **[H]** Server: `https://gw.api.bolagsverket.se/vardefulla-datamangder/v1`.
- **[H]** Four operations only:
  - `GET /isalive` — scope `vardefulla-datamangder:ping`
  - `POST /organisationer` — scope `…:read` — body `{"identitetsbeteckning": "5299999994"}`
  - `POST /dokumentlista` — scope `…:read` — body `{"identitetsbeteckning": "…"}`
  - `GET /dokument/{dokumentId}` — returns `application/zip`
- **[H]** **No search endpoint. Nothing accepts a name.** `search_company` for SE cannot be served by this API.
- **[H]** Org.nr goes in the **POST body**, never the URL (Bolagsverket's stated reason: it is personal data and would leak into logs/`Referer`). Do not convert to GET.
- **[H]** Optional headers on every data op: `X-Request-Id` (client-generated; echoed back as `requestId` on errors — send a fresh UUID per request) and `Authorization`.
- **[H]** Response envelope: `{"organisationer": [ Organisation, … ]}` — **an array**. For a sole trader it is genuinely plural: Bolagsverket's own example returns **two** objects for `194009272719`, separated only by `namnskyddslopnummer` 1 and 2.
- **[H]** `Organisation` has 14 properties, exactly:
  `organisationsidentitet, namnskyddslopnummer, organisationsnamn, registreringsland, reklamsparr, organisationsform, avregistreradOrganisation, avregistreringsorsak, pagaendeAvvecklingsEllerOmstruktureringsforfarande, juridiskForm, verksamOrganisation, organisationsdatum, verksamhetsbeskrivning, naringsgrenOrganisation, postadressOrganisation`
- **[H]** No officers / share capital / beneficial owners / financials (grep for `firmatecknare`, `styrelseledamot`, `företrädare`, `befattningshavare` = 0 hits).

### Per-field shape

- **[H]** **Every field is a wrapper** carrying `dataproducent` + `fel` beside its value.
  `Dataproducent` enum: `["Bolagsverket", "SCB"]`. `JaNej` enum: `["JA", "NEJ"]`.
  `Fel` = `{typ: FelTyp, felBeskrivning}`; `FelTyp` enum: `["ORGANISATION_FINNS_EJ", "OGILTIG_BEGARAN", "OTILLGANGLIG_UPPGIFTSKALLA", "TIMEOUT"]`.
- **[H]** **HTTP 200 ≠ data arrived.** Bolagsverket ships an example where every Bolagsverket-sourced field is null with
  `"fel": {"typ":"OTILLGANGLIG_UPPGIFTSKALLA", "felBeskrivning":"Uppkoppling mot Bolagsverket misslyckades. Efterfrågade uppgifter kunde inte hämtas."}`
  → **check `fel` before reading any value; do not 24 h-cache a partially-failed 200.**
- **[H]** `organisationsidentitet` = `{identitetsbeteckning, typ:{kod,klartext}}`; `typ.kod` observed `PERSONNUMMER`.
- **[H]** `namnskyddslopnummer`: `integer` 1–999, nullable (`null` for an AB).
- **[H]** `organisationsnamn.organisationsnamnLista[]` items = `{namn, organisationsnamntyp:{kod,klartext}, registreringsdatum, verksamhetsbeskrivningSarskiltForetagsnamn}`.
- **[H]** `registreringsland` = `{"kod":"SE-LAND","klartext":"Sverige"}` — **not** ISO `SE`.
- **[H]** `postadressOrganisation.postadress` = `{postnummer (required), utdelningsadress, land, coAdress, postort}`.
- **[H]** `naringsgrenOrganisation.sni[]` = `{kod,klartext}`, 5-digit, e.g. `{"kod":"47642","klartext":"Specialiserad butikshandel med cyklar"}`.
- **[H]** `pagaende…Lista[]` items = `{kod, klartext, fromDatum}` — **a list**; konkurs and likvidation can both be open (Bolagsverket's example has `KK` 2024-01-26 **and** `LI` 2024-05-26).
- **[H]** `avregistreradOrganisation.avregistreringsdatum` is `type: string` with **no** `format: date`; examples mix `"2023-05-05T00:00:00.000+00:00"` and `"2001-03-15"`. Parse both.
- **[H]** `verksamhetsbeskrivning.beskrivning` can carry leading whitespace — real value `"\n       HANDEL MED SKOR."`. Trim.
- **[H]** `juridiskForm` and `verksamOrganisation` are nullable (both `null` for the sole-trader example).

### ⚠ Two spelling traps

- **[H]** Schema field is **`pagaendeAvvecklingsEllerOmstruktureringsforfarande`**. Bolagsverket's own *aktiebolag example* misspells it `pagandeAvvecklings…` (both outer and inner list). The wire uses the schema spelling — the Altinn team wrote a code comment about exactly this bug: *"Bolagsverket sender \"pagaende...\" (med ekstra 'e' etter 'a'), ikke \"Pagande...\". Uten JsonProperty ville feltet aldri bli populert, og konkurs-detekteringen ville alltid feile."* **A fixture copied verbatim from the OpenAPI aktiebolag example carries the misspelling — fix it.**
- **[H]** `organisationsnamntyp`: code list says `FORNAMN_FRSPRAK`, Bolagsverket's response example says `FORETAGSNAMN_PA_FRAMMANDE_SPRAK`. Unresolved. Treat `kod` as an open string; match `FORETAGSNAMN` for the primary name, tolerate both foreign-language spellings.

### Errors

- **[H]** `ApiError` = RFC 7807. `required: [instance, status, title, type]`, plus `timestamp`, `requestId`, `detail`.
  `type` ∈ `about:blank` | `urn:bolagsverket:error:auth` | `urn:bolagsverket:error:network` | `urn:bolagsverket:error:validation`.
  `instance` documented as `not.found`, `server.error`, `auth.error`, `validation.client`, `network.timeout`, `network.error` (shipped examples all use `client.error`/`server.error`).
- **[H]** Example details, verbatim: 400 `"Identitetsbeteckning har ogiltig kontrollsiffra."` · 401 `"Anroparen saknar giltiga autentiseringsuppgifter."` · 403 `"Anroparen saknar behörighet till resursen."` · 500 `"Ett ohanterat fel har uppstått."` · 404 (dokument only) `"Dokument kunde inte hittas."`
- **[H]** **`/organisationer` declares no 404** — responses are 200/400/401/403/500 only. Unknown company → HTTP **200** with `fel.typ = "ORGANISATION_FINNS_EJ"`. Derive `not_found` from the body, never the status.
  Message strings (from the test workbook): *"Begärd organisation finns inte registrerad i sökbar form hos aktuell dataproducent. Observera att en organisation ändå kan existera och eventuellt också finnas registrerad i sökbar form hos en annan dataproducent trots detta fel."* / *"Den efterfrågade informationen gick inte att hitta."*
- **[H]** No `429` is declared anywhere in the spec. Behaviour at the 60/min ceiling is undocumented.

---

## Credentials / form

- **[H]** ⚠ **Token URL is `portal.`, not `gw.`** — T26 §T26r and `02-sweden-bolagsverket.md` both name `https://gw.api.bolagsverket.se/oauth2/token`. **That is wrong.** Bolagsverket's Connection establishment guide v1.01 (2025-02-10):
  - token (prod) `https://portal.api.bolagsverket.se/oauth2/token`
  - token (test) `https://portal-accept2.api.bolagsverket.se/oauth2/token`
  - revoke (prod/test) `…/oauth2/revoke`
  (The spec's `securitySchemes.OAuth2.flows.clientCredentials.tokenUrl` is the bare relative `"/oauth2/token"`, which is what invited the wrong absolutisation. Ignore the `default` scheme's implicit flow at `gw…/authorize`.)
- **[H]** Environments:
  | | Production | Test ("accept2") |
  |---|---|---|
  | API base | `https://gw.api.bolagsverket.se/vardefulla-datamangder/v1` | `https://gw-accept2.api.bolagsverket.se/vardefulla-datamangder/v1` |
  | Token | `https://portal.api.bolagsverket.se/oauth2/token` | `https://portal-accept2.api.bolagsverket.se/oauth2/token` |
- **[H]** Grant `client_credentials`; `Content-Type: application/x-www-form-urlencoded`; body `grant_type`, `client_id`, `client_secret`, `scope`. **Both scopes in one request, space-separated:** `scope=vardefulla-datamangder:read vardefulla-datamangder:ping`. Guide warns: scopes absent from the token → subsequent resource calls fail.
- **[H]** Token response: `{"access_token": "...", "scope": "...", "token_type": "Bearer", "expires_in": 3600}`. JWT. Header `Authorization: Bearer <access_token>`. **[L]** 3600 is from a doc example — read `expires_in` from the response, don't hard-code.
- **[H]** **Kundanmälan form URL:**
  `https://bolagsverket.se/apierochoppnadata/hamtaforetagsinformation/vardefulladatamangder/kundanmalantillapiforvardefulladatamangder.5528.html`
- **[H]** It asks for **exactly two required fields, nothing else** — no company name, no org.nr, no use case, no account:
  - **E-postadress \*** — *"Adressen får inte vara en noreply-adress utan måste vara en giltig e-postadress där Bolagsverket kan nå dig med frågor angående ditt konto."*
  - **Mobilnummer \***
- **[H]** What arrives: *"Values for 'client ID' and 'client secret' are delivered to the user via email as an **encrypted zip file** … The password is sent separately in an SMS."* → **the SMS carries the zip password, not the secret.** One submission yields **both test and production** credentials.
- **[H]** Standing notice on the form page (2026-05-13): *"Hög belastning på API-supporten … svars- och handläggningstider under en period kan vara längre än vanligt."* Expect a wait.
- **[H]** Test environment publishes its companies (portal doc `Testdata API Vardefulla datamangder.xlsx`, v1.02, anonymous download). Only listed numbers work; another number returns a response listing the permitted ones. Scenarios:
  | identitetsbeteckning | scenario |
  |---|---|
  | `5560021361` | OK — Aktiebolag |
  | `9124001992` | OK — Handelsbolag |
  | `7164099017` | OK — Bostadsrättsförening |
  | `7020008350` | OK — Ekonomisk förening |
  | `198101032384` | OK — Enskild firma |
  | `198101052382` | OK — Enskild firma, **två namnskyddslöpnummer** |
  | `193403223328` | error — organisation finns inte registrerad |
  | `5567223705` | error — AB, organisation finns ej hos SCB |
  | `5561890038` | `/dokumentlista` scenario |
  Also permitted: `5562820745`, `5560986878`, `5560000002`, `5560004755`, `7140000001`, `9160000001`, `198101012386`, `198210300002`, ~40 more.
- **[H]** Real `/dokumentlista` item: `{"dokumentId":"02f54e4f-b17a-4cfd-a1cc-d8ab4eaa7f49_paket","filformat":"application/zip","rapporteringsperiodTom":"2022-12-31","registreringstidpunkt":"2023-06-27"}` — note `_paket` suffix and that `filformat` is a MIME type.

---

## Identifier

- **[H]** Wire format is **digits only, no hyphen**: `5299999994`, `194009272719`.
- **[H]** Spec regex, verbatim:
  `^(19|20)?\d{2}(0[1-9]|1[0-2])((0|6)[1-9]|(1|2|7|8)[0-9]|(3|9)[0|1])\d{4}$|^\d{6}\d{4}$|^302\d{8}$`
  Third alternative accepts **any ten digits** → the regex alone does not validate an organisationsnummer.
- **[H]** Four accepted identity kinds, verbatim: *"'Organisationsnummer' is represented by 10 digits, 'personnummer' is represented by 12 digits (YYYYMMDDXXXX), 'samordningsnummer' is represented by 12 digits (YYYYMMDDXXXX, where 'DD' is the persons birthday + 60) and 'GD-nummer' is represented by 10 digits (302XXXXXXX)."*
- **[H]** ⚠ **A sole trader is looked up by a 12-digit personnummer**, not by ten digits (`194009272719` in Bolagsverket's own example). `format_id`/normalisation must not force ten digits.
- **[H]** A check digit **exists and is validated server-side** — 400 `"Identitetsbeteckning har ogiltig kontrollsiffra."`
- **[H]** `IdentitetsbeteckningstypOrganisation`: `DODSBO`, `GDNUMMER`, `ORGANISATIONSNUMMER`, `PERSONNUMMER`, `SAMORDNINGSNUMMER`, `UTLANDSK_JURIDISK_IDENTITETSBETECKNING`.
- ❌ **The check-digit algorithm is NOT sourced.** See "could not be verified". Do not implement Luhn on the old library file's authority.

---

## Statutes / deadlines

- **[H]** **ABL (2005:551) 7 kap. 10 §** — AGM within six months:
  *"Inom sex månader från utgången av varje räkenskapsår ska aktieägarna hålla en ordinarie bolagsstämma där styrelsen ska lägga fram årsredovisningen och revisionsberättelsen …(årsstämma)."* — Lag (2024:350)
- **[H]** ⚠ **CORRECTION: ÅRL (1995:1554) 8 kap. 3 § is not the seven-month rule.** For an aktiebolag it says:
  *"1. Aktiebolag — Bestyrkta kopior av handlingarna ska ha kommit in till registreringsmyndigheten **inom en månad efter det att bolagsstämman fastställde balansräkningen och resultaträkningen**."*
  (Handelsbolag with legal-person partners, and stiftelser: **sex månader efter räkenskapsårets utgång**.)
  → The AB filing deadline in 8:3 keys off the **AGM adoption date**, which the free API does not publish. `02-sweden-bolagsverket.md` §8 attributes seven months to 8:3; that is wrong.
- **[H]** **Seven months lives in ÅRL 8 kap. 6 §**, as the förseningsavgift trigger:
  *"Ett aktiebolag och en ekonomisk förening ska betala en förseningsavgift om de handlingar som anges i 5 § inte har kommit in till registreringsmyndigheten **inom sju månader från räkenskapsårets utgång**. Om bolaget eller föreningen inom denna tid har kommit in med anmälan enligt 7 kap. 14 § tredje stycket aktiebolagslagen (2005:551) … ska dock bolaget eller föreningen betala förseningsavgift först om handlingarna inte har kommit in **inom nio månader** från räkenskapsårets utgång. En stiftelse … **inom sex månader** … Förseningsavgiften ska uppgå till **7 500 kronor för privata aktiebolag, ekonomiska föreningar och stiftelser** och till **15 000 kronor för publika aktiebolag**."* — Lag (2024:1115)
- **[H]** **ÅRL 8 kap. 6 a §** — escalation: a second fee after **two months** from the notice (7 500 private / 15 000 public), a third after two more (**15 000** private / **30 000** public). Max private AB **30 000 kr**, public **60 000 kr**.
- **[H]** **ÅRL 8 kap. 5 §** — the fee is decided by Bolagsverket (`registreringsmyndigheten`).
- **[H]** **ÅRL 8 kap. 7 §** — *no* förseningsavgift once **konkurs** is registered; none for pre-liquidation periods once **likvidation** is registered. → a `KK`/`LI` in `pagaende…` suppresses the fee; usable in `applies_because`.
- **[H]** **ÅRL 8 kap. 8 §** — an easily-remediable defect only triggers a fee after notice and a chance to fix.
- Suggested rule ladder: ABL 7:10 (AGM, 6 mo, mandatory) → ÅRL 8:3 p.1 (file 1 mo after adoption — **not computable**, no adoption date in the free API) → ÅRL 8:6 (7 mo from FY end, the computable date users mean by "filing deadline"). FY end is not in the free dataset → same calendar-year assumption and `applies_because` honesty as NO.
- ❌ **Roll-forward: NOT FOUND.** Nothing in ÅRL 8 kap. mentions weekends/holidays; no Bolagsverket page located. Sweden's general lagen (1930:173) om beräkning av lagstadgad tid was **not read** and its application to ÅRL 8:6 not confirmed. **Ship no roll-forward for SE** (D-016/D-023).
- Skatteverket deadlines (INK2 / moms / arbetsgivardeklaration): **not researched, deliberately** — the free dataset has neither FY end nor VAT period, so they are unusable. Leave out.

---

## Code lists

Complete, from the portal's own "Code lists" document (`text/plain`, anonymous).

- **[H]** **`AVREGISTRERINGSORSAK`** (17): `AKEJH` Aktiekapitalet inte höjts · `ARSEED` Årsredovisning saknas · `AVREG` Avregistrerad · `BABAKEJH` Ombildat till bankaktiebolag eller aktiekapitalet inte höjts · `DELAV` Delning · `DOM` Beslut av domstol · `FUAV` Fusion · `GROMAV` Gränsöverskridande ombildning · `KKAV` Konkurs · `LIAV` Likvidation · `NYINN` Ny innehavare · `OMAV` Ombildning · `OMBAB` Ombildat till bankaktiebolag · `OVERK` Overksamhet · `UTLKKLI` Det utländska företagets likvidation eller konkurs · `VERKUPP` Verksamheten har upphört · `VDSAK` Verkställande direktör saknas
- **[H]** **`PÅGÅENDE AVVECKLINGS-/OMSTRUKTURERINGSFÖRFARANDE`** (11): `AC` Ackordsförhandling · `DEOL` Överlåtande vid delning · `DEOT` Övertagande vid delning · `FR` Företagsrekonstruktion · `FUOL` Överlåtande i fusion · `FUOT` Övertagande i fusion · `GROM` Gränsöverskridande ombildning · `KK` Konkurs · `LI` Likvidation · `OM` Ombildning · `RES` Resolution
  → `KK` + `fromDatum` = `bankruptcy_date`. `FR`/`AC` are distress but **not** bankruptcy.
- **[H]** **`ORGANISATIONSFORM`** (29): `AB` Aktiebolag · `BAB` Bankaktiebolag · `BF` Bostadsförening · `BFL` Utländsk banks filial · `BRF` Bostadsrättsförening · `E` Enskild näringsverksamhet · `EB` Enkla bolag · `EEIG` · `EGTS` · `EK` Ekonomisk förening · `FAB` Försäkringsaktiebolag · `FF` Försäkringsförmedlare · `FL` Filial · `FOF` Försäkringsförening · `HB` Handelsbolag · `I` Ideell förening som bedriver näringsverksamhet · `KB` Kommanditbolag · `KHF` Kooperativ hyresrättsförening · `MB` Medlemsbank · `OFB` Ömsesidigt försäkringsbolag · `OTPB` Ömsesidigt tjänstepensionsbolag · `S` Stiftelse som bedriver näringsverksamhet · `SB` Sparbank · `SCE` Europakooperativ · `SE` Europabolag · `SF` Sambruksförening · `TPAB` Tjänstepensionsaktiebolag · `TPF` Tjänstepensionsförening · `TSF` Trossamfund som bedriver näringsverksamhet
  ⚠ `SE` as an organisationsform code = Europabolag, colliding visually with the country code.
  `kod` is `maxLength: 4, minLength: 1`.
- **[H]** **`ORGANISATIONSNAMNTYP`** (4): `FORETAGSNAMN` · `FORNAMN_FRSPRAK` · `NAMN` · `SARSKILT_FORETAGSNAMN` (see spelling trap above).
- **[H]** **`JURIDISK FORM` is not enumerated by Bolagsverket** — the code-list doc points to Skatteverket. But the API page publishes the **ORGANISATIONSFORM ↔ JURIDISK FORM mapping table** in full: AB→49, KB→31, HB→31, FL→– (*"Finns inte som juridisk form då det inte är en egen organisation utan tillhör ett moderbolag"*), BRF→53, EK→51, E→10/91, BAB→41, FAB→42, TPAB→49, SE→43, FOF→51, TPF→51, BF→51, KHF→54, SF→51, BFL→–, MB→93, SCE→55, SB→93, TSF→63, I→61, S→72, OTBP→92, OFB→92.
  SCB-only: `10` Fysiska personer (utan registrerat namn), `51`, `61`, `63`, `72`. Public: `81` Statliga enheter, `82` Kommuner, `83` Kommunalförbund, `84` Region, `85` Allmänna försäkringskassor, `87` Offentliga korporationer och anstalter, `88` Hypoteksföreningar, `89` Regionala statliga myndigheter. Other: `21` Enkla bolag, `22` Partrederier, `32` Gruvbolag, `62` Samfällighetsföreningar, `71` Familjestiftelser, `91` Oskiftade dödsbon, `94` Understödsföreningar/Försäkringsföreningar.
  → **Mapping is many-to-one and lossy** (AB and TPAB both → 49; five formes → 51). **`ORGANISATIONSFORM` is the finer vocabulary — it should drive `legal_form_code`.**
- **[H]** SNI: not enumerated; Bolagsverket points to `https://snisok.scb.se/`.
- **[H]** Join rule (unchanged): *"Data från Bolagsverket hämtas när det finns data att hämta från både Bolagsverket och SCB. Data från SCB hämtas när inget data finns att hämta från Bolagsverket."*

---

## Licence / rate limit

- **[H]** **60 req/min**, re-fetched 2026-09-05 from `…/apiforvardefulladatamangder.5513.html` ("Uppdaterad: 2026-06-30"): *"Prestandan för detta API tillåter varje användare att göra 60 frågor/minut."* Same page: *"Vårt API är en REST-tjänst baserad på http och json. Anrop mot tjänsten ska krypteras via https. Auktorisation av API-anrop görs med hjälp av OAuth 2."*
- **[M]** The portal's public subscription-tier list shows 25 policies, all `"tierPlan":"FREE"`, banded by monthly quota (100/500/1000/3000/5000/15000…), each with `"rateLimitCount":20,"rateLimitTimeUnit":"sec"`. Which policy this API grants is **not public**; 20/sec is a burst ceiling. **Build to the published 60 req/min.**
- **[H]** No contract: *"Det krävs inget avtal för att du ska få använda vårt API för värdefulla datamängder."*
- **[H]** No fee: *"Värdefulla datamängder är avgiftsfritt. Enligt EU-kommissionens direktiv ska det vara kostnadsfritt för alla att använda."*
- **[H]** **Licence — Bolagsverket names none.** Verbatim (`…/vardefulladatamangder.5294.html`): *"Du får använda dessa data fritt för kommersiella och icke-kommersiella syften, exempelvis för att skapa nya tjänster eller produkter, så länge användningen inte bryter mot lagar om skydd av personuppgifter eller sekretess. Data kan modifieras, bearbetas och kombineras med andra källor…"* and *"Det är dock viktigt att se till att data hanteras enligt de villkor och licenser som gäller, vilket ibland kan inkludera krav på att ange källan och säkerställa att informationen är korrekt återgiven."*
  ⚠ A third-party audit (`strale-io/strale`) claims "CC BY 4.0 (or equivalent)". **Unsupported by anything on Bolagsverket's pages — do not repeat it.** Quote the regime; do not name a licence.

---

## Could not be verified

1. **The organisationsnummer check-digit algorithm.** Only *that* one exists (400 `"…ogiltig kontrollsiffra."`). Skatteverket's `organisationsnummer` page — the one Bolagsverket's own code list cites — describes no digit count, check digit, group digit or hyphen. `lagen.nu/1974:174` and `/1974:661` returned empty bodies. Session WebSearch budget (200) was exhausted. **The Luhn/mod-10 claim in `02-sweden-bolagsverket.md` §6 remains unsourced — do not implement it.**
2. **First-digit legal-form groups** (5=AB, 2=state/municipal, 8=ideell förening, 9=HB…) — no primary source found.
3. **The hyphen convention `556016-0680`** — no primary source found; the API only ever uses unhyphenated digits.
4. **VAT rule `SE` + 10 digits + `01`** — no primary source found.
5. **Weekend/holiday roll-forward** for the ÅRL 8:6 point — no rule found; lagen (1930:173) not read.
6. **WSO2 subscription tier / monthly quota** actually bound to this API.
7. **Whether an unknown org.nr returns `organisationer: []` or a populated object with `fel.typ=ORGANISATION_FINNS_EJ`.** Test workbook names the scenario and the message strings but ships no full body. **Needs a live call — record this fixture first when credentials arrive.**
8. **`organisationsnamntyp`** foreign-language code: `FORNAMN_FRSPRAK` (code list) vs `FORETAGSNAMN_PA_FRAMMANDE_SPRAK` (response example).
9. **Production token lifetime.** `expires_in: 3600` is from a doc example only.
10. **Behaviour at the 60/min ceiling** — no `429` declared anywhere in the spec.
11. **Paid-API krona figures** — still not fetched from Bolagsverket. (A third-party audit claims SEK 6,250 setup + ≥3,000 tx/month, uncited. Do not quote.)
12. **Beneficial owners:** a `VerkligaHuvudmän v1` API exists on the same portal (`/verkliga-huvudman`, `PUBLISHED`); access terms not investigated.
13. **web.archive.org was offline for the entire session** — no Wayback cross-check of any page revision was possible.
