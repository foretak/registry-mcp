# 02 — Registers landscape

**Scope:** which national company registers a small open-source project can actually get programmatic access to, on what terms, and in what order countries should be added.
**Compiled:** 2026-09-05, from primary register documentation, statutory texts, and live calls to eleven APIs.
**Covers:** Denmark, Sweden, Finland, Germany, Netherlands, France, Belgium, Ireland, Estonia, Poland, Austria, Switzerland, Spain, Italy, United States, EU/BRIS, and OpenCorporates as an aggregator alternative. Norway and the UK are already live and are described in `~/registry-mcp/NORBIZ_SPEC.md` and `UK_SPEC.md`.

---

## Key findings

**1. Free and keyless is now normal, and it is spreading by EU law.** Five registers answered an unauthenticated request during this survey, live, on 2026-09-05: Finland (`avoindata.prh.fi/opendata-ytj-api/v3/companies?businessId=0112038-9` → 200, Nokia), France (`recherche-entreprises.api.gouv.fr/search?q=danone` → 200, Danone), Poland (`api-krs.ms.gov.pl/api/krs/OdpisAktualny/0000006865?rejestr=P&format=json` → 200), Switzerland via SPARQL (`lindas.admin.ch/query` → 200, Zazuko GmbH), and the SEC (`data.sec.gov/submissions/CIK0000320193.json` → 200, Apple Inc.). GLEIF and New York's Socrata endpoint make seven. **No key, no form, no contract, no fee.**

**2. The EU Open Data Directive is doing the work.** Sweden's registry data became free on a specific date: *"Från den 3 februari 2025 blev Bolagsverkets och Statistikmyndigheten SCB:s värdefulla data avgiftsfria"* — with a two-year derogation from the regulation that entered force 9 February 2023. Bolagsverket now says *"värdefulla datamängder är avgiftsfritt och kräver inget avtal"* and rate-limits at *"60 frågor/minut"*. Poland's open KRS API is grounded in the same directive's national implementation, *"ustawą z dnia 11 sierpnia 2021 r. o otwartych danych"*. Germany, the largest market, has not complied — and that is the single biggest thing to watch.

**3. Beneficial ownership has closed almost everywhere, and Denmark closed most recently.** From **1 September 2025**, CVR no longer shows *reelle ejere* to the public — bekendtgørelse nr. 987 of 30 June 2025, implementing Directive (EU) 2024/1640: *"Adgangen er ikke længere automatisk, men vil fremover være betinget af dokumenteret behov eller legitim interesse."* The Netherlands suspended public UBO access in November 2022; Germany, Belgium, Ireland, France, Finland and Austria are all gated. **Estonia is the exception**: it still publishes a `Beneficial owners` dataset daily, in XML and JSON, under CC BY 4.0.

**4. Per-call pricing varies by three orders of magnitude.** Netherlands: *"Per maand € 6,40"* per API key plus *"€ 0,02"* per Basisprofiel query, search free, capped at *"maximaal 300.000 bevragingen per maand"* and *"niet meer dan 100 bevragingen per seconde"*. Austria: **€4.89** for a current Firmenbuchauszug and **€8.20** with history, after a 5.71 % statutory rise on 1 August 2026 (BGBl II 2026/227), through a mandatory clearing agency that adds a surcharge. OpenCorporates: reported tiers of ~£2,250/£6,600/£12,000 a year for 500/2,500/5,000 calls a month — roughly £0.20–£0.375 per call. Everything else worth having is free.

**5. Two "free" datasets are not fit to answer with.** OffeneRegister.de's German dump carries `last-modified: Tue, 05 Feb 2019 08:09:07 GMT` — **seven and a half years stale**, verified by HTTP HEAD on 2026-09-05. Belgium's KBO Open Data is a *monthly* full dump with weekly deltas, so an answer can be up to five weeks old. Both would return confident, well-formed, wrong company statuses.

**6. Licences are cleanest at the extremes.** GLEIF: *"The data available through the Access Service are provided under the CC0 licence"* — public domain, no attribution, daily golden copy (published `2026-09-05T00:00:00Z`). Ireland's CRO and Estonia's RIK: **CC BY 4.0**, verified from their own CKAN metadata, with Ireland's Company Records dataset modified `2026-09-05T04:00:38`. At the other end, New York's 4,274,856-row corporations dataset has `license: null` and `licenseId: null` — published openly, licensed by nobody. OpenCorporates is **ODbL**, share-alike and viral, with an attribution clause specifying a credit line *"no smaller than 70% of the largest font relating to the information or 7px, whichever is the larger"* — unrenderable in an MCP response and incompatible with an MIT project's hosted API.

**7. Most registers compute deadlines; only two publish them.** Companies House publishes per-company dates (already exploited in `published_deadlines`), and Ireland publishes an Annual Return Date. Everyone else requires statute plus an accounting-period assumption — the same problem `NORBIZ_SPEC.md` §5.4 already documents for Norway. Denmark's number has moved and most secondary sources are wrong: årsregnskabsloven § 138 now says *"Årsrapporten skal være modtaget i styrelsen senest 6 måneder efter regnskabsårets afslutning"*, four months for class D, and *"Der kan ikke dispenseres fra disse frister."*

**8. Access is increasingly gated on national identity, not on money.** The Netherlands: *"Om een overeenkomst te tekenen moet je ingeschreven staan in het handelsregister en tekenbevoegd zijn."* Denmark's Datafordeler needs a Danish FOCES/VOCES certificate. Italy's InfoCamere API needs SPID/CIE/CNS. **A Norwegian sole trader may be structurally ineligible for three European registers regardless of budget** — which is exactly the question already put to Erhvervsstyrelsen for Denmark, and which must be asked before any Dutch or Italian work is scheduled.

---

## The next six countries, ranked

Slots 4–9, on the assumption that Norway is 1, the UK is 2 and Denmark is 3 (applied for 2026-09-05, answer due ~2026-09-23).

**Scoring, 1–5 on four axes, equally weighted.** *Access* = how little paperwork, money and eligibility risk stands between the project and a working call. *Market* = size of the national business population and economy — judged qualitatively, since no sourced market figures were gathered in this pass (that belongs in `01-market-and-buyers/`). *English* = how much of the register, its docs and its data an English-speaking developer can use and extend without a translator. *Publishes* = how much the register states outright (status enums, deadlines, code tables) versus how much the module must derive.

| # | Country | Access | Market | English | Publishes | Total | The one-line reason |
|---|---|---|---|---|---|---|---|
| **4** | **Sweden** | 5 | 4 | 3 | 4 | **16** | Free since 3 Feb 2025, no contract, OAuth2 + OpenAPI, and it completes the Nordic set the project already speaks for |
| **5** | **Finland** | 5 | 2 | 5 | 4 | **16** | The only register that needed nothing at all — no key, English docs, English strings in the payload, and it hands you a EUID |
| **6** | **Ireland** | 4 | 3 | 5 | 4 | **16** | CC BY 4.0 daily bulk data plus a free REST API, in English, with a published Annual Return Date that may fill `published_deadlines` |
| **7** | **France** | 5 | 5 | 2 | 3 | **15** | Biggest open register in Europe, verified live with no key, 7 req/s — the data model is the work, not the access |
| **8** | **Switzerland** | 4 | 3 | 4 | 3 | **14** | Free, daily, four-language, one email for REST or nothing at all for SPARQL; the first non-EU country, which is its own proof point |
| **9** | **Estonia** | 4 | 1 | 5 | 5 | **15** | The only register that still publishes beneficial owners as open data — a capability nothing else on this list can give |

Sweden, Finland and Ireland tie at 16 and the order between them is a judgement call: **Sweden first** because it finishes the Nordic story that Norway and Denmark start and is the largest of the three; **Finland second** because it is the cheapest week of work available and proves the "any country" claim a third time; **Ireland third** because it is the strongest English-language addition and the first chance to test whether `published_deadlines` generalises beyond the UK.

**Estonia is placed below Switzerland deliberately, against its own score.** It totals 15 to Switzerland's 14, but its market is the smallest here by a wide margin, and its distinguishing feature — open beneficial ownership — carries GDPR exposure that deserves the `03-regulation-drivers/` work first. If that work says the exposure is manageable, Estonia moves up to 8 and Switzerland down to 9.

**Explicitly not in the next six, with reasons:**

- **Germany** — largest market in Europe, **no official API of any kind**. Watch for an EU high-value-dataset API or the Unternehmensbasisdatenregister opening; either flips it from hard to easy overnight.
- **Netherlands** — technically the nicest paid API in the survey, blocked on two unanswered questions (foreign eligibility; whether responses may be served to third parties).
- **Belgium** — free and complete, but bulk-only: needs an ingest pipeline, which is an architecture change rather than a country folder.
- **Poland** — largest CEE market, key-free API verified live, but statuses must be inferred from Polish court-extract sections and there is no English anywhere. Reconsider if a Polish-reading contributor appears.
- **Austria, Italy** — structurally closed: per-query statutory fees or a national digital identity requirement.
- **Spain** — event-shaped, not state-shaped; requires replaying seventeen years of gazettes.
- **United States** — not a country for this purpose. Fifty-one registers, one federal disclosure system that is not a register, and a sub-national identity model `core/` does not express.
- **GLEIF LEI** — not a country at all, and more useful than most of them: CC0, keyless, daily, global, and structured as a join key between national registers. **Add it as a cross-cutting field before adding country 4.**

---

## Traps a spec writer must know

The pattern the two existing specs already establish — `UK_SPEC.md` §1.6, "the live payloads contradicted the published schema in eight places", and `NORBIZ_SPEC.md` §1.1 — repeats in every country. These are the ones found in this pass.

**Already in the codebase, restated because they are the template:**

- **Companies House `company_status: "open"`.** Confirmed live on `BR026263`, a `uk-establishment`. Not `active`, not `dissolved` — a third value that a two-branch status mapper silently gets wrong. (`UK_SPEC.md` §1.4, §1.7)
- **brreg returns `200`, not `410`, for deleted entities**, with a normal-shaped body carrying `slettedato` and `respons_klasse: "SlettetEnhet"`. A client that only checks the status code reports a struck-off company as fine. (`NORBIZ_SPEC.md` §1.1)

**New, from this survey:**

- **Denmark's system-to-system endpoint is plain HTTP only.** `http://distribution.virk.dk/cvr-permanent/…` returns `401`; the same host over **HTTPS times out entirely** (verified 2026-09-05). HTTP Basic credentials in the clear, and any blanket "upgrade to https" policy breaks the country.
- **Denmark makes advertising protection a *marking* obligation, not a filter.** CVR-loven § 19: contact data may be passed on *"hvis det i forbindelse med videregivelsen klart markeres over for modtageren, at enheden er beskyttet."* That is a new field in `CompanyReport`, not a footnote. Sweden's `REKLAMSPÄRR` is the same concept.
- **Denmark's filing deadline is 6 months, not 5.** § 138 as it now reads. Most accountants, and most of the internet, still say five.
- **Belgian enterprise numbers no longer start with `0`.** The 0-series was exhausted and the first `1`-prefixed number was issued **19 September 2023**. Any regex or fixture assuming a leading zero rejects every company incorporated since. The mod-97 check also runs over the first *eight* digits **including** the leading zero — storing the identifier as an integer breaks it.
- **France's `etat_administratif` does not know about insolvency.** It is `A` or `C`. *Redressement* and *liquidation judiciaire* are published in BODACC, a different dataset. A status derived from `etat_administratif` alone reports a company in liquidation as active — the exact shape of the Companies House `links.charges` trap.
- **France redacts rather than omits.** Non-diffusible records return `200` with placeholder names and truncated addresses. Check `statut_diffusion`; a mapper that does not will return a company called `INFORMATION NON-DIFFUSIBLE`.
- **Finland's statuses are bare integers.** `status: "2"`, `tradeRegisterStatus: "1"`, `companyForms[].type: "17"`, `languageCode: "1"|"2"|"3"`. No English status string exists anywhere in the payload. Ship code tables and fail loudly on an unknown code.
- **Finland's `names[]` is a versioned history mixing current auxiliary names with former registered names.** `type: 1` is the registered name, `type: 3` an auxiliary trade name. Taking "everything after the first entry" as `previous_names` is wrong in both directions.
- **Finland and Belgium have two official languages in the same record.** Nokia's registered office is in both `ESPOO` and `ESBO`. "The city" requires choosing a language.
- **Poland's `stanZDnia` is an as-of date, and it is not today.** Two live lookups on 2026-09-05 returned `10.08.2026` and `27.08.2026`. Surface it or mislead.
- **Poland needs the right `rejestr`.** `?rejestr=P` and `?rejestr=S` are different registers; the wrong one returns `404`, not a redirect. A lookup may need two calls — the same fallback pattern as brreg's `/enheter` → `/underenheter`.
- **Sweden's payload speaks two vocabularies.** `ORGANISATIONSFORM` (Bolagsverket) and `JURIDISK FORM` (SCB) are different code lists in the same response, and Bolagsverket's value wins only when it exists: *"Data från SCB hämtas när inget data finns att hämta från Bolagsverket."*
- **A Swedish sole trader's organisationsnummer is not unique to one business** — hence `NAMNSKYDDSLÖPNUMMER`. "Identifier → one company" is not an invariant.
- **Estonia's open data appears to contain active entities only.** If true, absence is ambiguous between "never existed" and "dissolved" — the one distinction a supplier check needs.
- **New York publishes 4.27 m corporations with `license: null`.** Openly available, formally unlicensed. Not the same as open-licensed.
- **GLEIF's CC0 has a CHF 100,000 anti-impersonation clause** sitting outside the data licence, and PRH forbids services that *"confuse the service with PRH's services"*. Cite the source; never imply endorsement.
- **The EUID is not the LEI, and "EUid" is also the European Digital Identity wallet.** Three different things, one search-results soup.

---

## What this means for registry-mcp

**Do three cheap things before adding country 4.**

First, **add a nullable `euid` to `CompanyReport`**. Finland hands one over unprompted (`"euId": {"value": "FIFPRO.0112038-9"}`), it is legally mandated across the EU by Implementing Regulation (EU) 2021/1042, and a nullable field costs a line per country. It makes "one shape across countries" concrete.

Second, **treat GLEIF as a cross-cutting resource, not a country**. CC0, keyless, daily, and its Level 1 records name the national register and the entity's number in it — a join key between the registers the project already speaks. It works for Norway and the UK today.

Third, **decide the advertising-protection field now**, before Denmark's credentials arrive. CVR-loven § 19 makes marking a legal condition of passing the data on, and Sweden's `REKLAMSPÄRR` will need the same field. Retrofitting it into a frozen response shape after the fact is worse than adding it once.

**Then take Sweden, Finland and Ireland in that order** — three registers, no contracts, no fees, no eligibility risk, and one of them (Ireland) tests whether `published_deadlines` generalises beyond the UK.

**And write down the sub-national question.** Germany's Länder courts, Spain's provincial registers and the fifty US states all need a `country`-plus-region key that `D-015`'s strict two-letter code cannot express. That is a `DECISIONS.md` entry, and deciding it late is expensive.

---

## Open questions we could not answer

1. **Can a Norwegian ENK sign up at all?** Pending for Denmark (sagsnummer #177481). Unasked for the Netherlands (*"ingeschreven staan in het handelsregister"*) and Italy (SPID/CIE/CNS). Three registers may be closed on identity grounds regardless of budget. **Ask before speccing.**
2. **May KVK responses be served to third parties?** The `gebruiksvoorwaarden` sit behind signup and were not retrieved. If redistribution is barred, the Netherlands is a non-starter for a hosted endpoint even at €0.02.
3. **What are Denmark's CVR rate limits and status enum?** Neither is published; `erhvervsstyrelsen.dk` and `datahub.virk.dk` refused every fetch (403 and DNS failure respectively) and no Wayback snapshot exists. Both must be resolved from live payloads, as the UK was.
4. **What does Bolagsverket's paid API cost?** Every fee page is CAPTCHA-protected against automated fetching. Structure is known (connection fee + banded monthly fee); no krona figure could be verified.
5. **Is Germany planning an EU high-value-dataset API?** No timetable found. This is the highest-value unknown in the survey: it would move the largest European market from hard to easy.
6. **Does Ireland's open dataset carry the Annual Return Date?** If it does, Ireland joins the UK in `published_deadlines` and the field stops being a UK special case.
7. **Is Estonia's open beneficial-ownership dataset stable?** It is the last one standing. AMLD6's legitimate-interest regime points the other way.
8. **Which US states publish free bulk or API access?** Only New York was checked directly; the web-search budget ran out before a fifty-state survey. Delaware, California and Texas are described from general knowledge only.
9. **Has OpenCorporates changed hands, and have its terms changed with it?** Search results were inconclusive. Terms and prices follow ownership, and every conclusion in `15-opencorporates-aggregator.md` depends on them.
10. **Every check-digit rule marked `VERIFY`.** Sweden (Luhn), France (Luhn + the VAT key formula), Estonia (two-pass mod-11 on eight digits), Netherlands (whether the KVK-nummer has one at all), Austria (the check letter), Poland (NIP, REGON), Italy and Spain. Denmark, Finland, Belgium and Switzerland are described from consistent multi-source agreement and worked examples; none was read out of an official specification. **A wrong check digit rejects valid companies, which is worse than no validation.**

---

## Files in this folder

| File | Subject |
|---|---|
| `01-denmark-cvr.md` | CVR system-til-system and Datafordeler — country 3, application pending |
| `02-sweden-bolagsverket.md` | Free HVD API since 3 Feb 2025, and the paid Företagsinformation API |
| `03-finland-prh-ytj.md` | PRH/YTJ open data — the zero-friction register |
| `04-germany-handelsregister.md` | Free to read, no API; OffeneRegister stale since 2019; North Data |
| `05-netherlands-kvk.md` | Four APIs, €0.02/query, and an eligibility rule that may exclude us |
| `06-france-inpi-sirene.md` | recherche-entreprises, Sirene, INPI RNE — open access, hard model |
| `07-belgium-kbo.md` | Free bulk register, no lookup API, mod-97 identifiers |
| `08-ireland-cro.md` | Free REST API + daily CC BY 4.0 bulk data, in English |
| `09-estonia-e-business-register.md` | CC BY 4.0 daily files including beneficial owners |
| `10-poland-krs-ceidg.md` | Key-free court-extract API, no status enum, no English |
| `11-austria-switzerland.md` | €4.89 per extract vs. free open SPARQL — the two extremes |
| `12-spain-italy.md` | Event-shaped (BORME) and closed (InfoCamere) |
| `13-united-states-edgar-states-gleif.md` | Why "the US" is the wrong question, and why GLEIF is the right one |
| `14-eu-bris-euid.md` | BRIS is not an API; the EUID is a standard worth adopting |
| `15-opencorporates-aggregator.md` | The shortcut, and why its ODbL licence forbids taking it |
