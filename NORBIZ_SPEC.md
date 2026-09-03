# NORBIZ_SPEC — the Norwegian module (`registries/no/`)

Technical specification for the Norway module of `registry-mcp`, the first and reference implementation.

**Status:** written by Opus A in T01, from `BRREG_MCP_BUILD_PLAN.md` plus the live Brønnøysundregistrene open API. The original spec file was never delivered; this replaces it and is authoritative for T02 and T03.

**How to read the markers**

| Marker | Meaning |
|---|---|
| *(no marker)* | Confirmed against the live API on 2026-09-03, or a rule I am confident enough in to ship. |
| `VERIFY` | Must be confirmed against reality before it ships. T03 verifies field names against the live JSON; T02 verifies legal rules against the linked source and records the result in `REVIEW.md`. If verification fails, the item is dropped, not guessed. |
| `DEFERRED` | Real but deliberately out of scope for T02/T03. Do not implement. |

Everything here is Norwegian. Nothing here may be imported into `core/` (`DECISIONS.md` D-001). Where this file says `core/…` or `registries/…`, read `src/registry_mcp/core/…` and `src/registry_mcp/registries/…` (`DECISIONS.md` D-003).

---

## 1. The upstream API

Base URL: `https://data.brreg.no/enhetsregisteret/api`

No API key, no authentication, no registration. Data is published under **NLOD 2.0**; attribution is required, so every `CompanyReport` carries `source`, `source_url` and `license`.

Endpoints this module uses:

| Purpose | Endpoint | Notes |
|---|---|---|
| Lookup a legal entity | `GET /enheter/{orgnr}` | 200 with the entity; 404 if unknown |
| Lookup a sub-unit | `GET /underenheter/{orgnr}` | Branches (`BEDR`, `AAFY`). Try this on a 404 from `/enheter` |
| Search by name | `GET /enheter?navn={q}&size={n}` | HAL envelope, see §4 |
| Filtered search | `GET /enheter?konkurs=true`, `?underAvvikling=true`, `?organisasjonsnummer=` | Used by fixtures/tests |
| Roles / board | `GET /enheter/{orgnr}/roller` | `DEFERRED` — not in the first release |
| Sub-units of a parent | `GET /underenheter?overordnetEnhet={orgnr}` | `DEFERRED` |
| Legal-form code list | `GET /organisasjonsformer` | Used once, offline, to build the table in §7 |

### 1.1 Confirmed live behaviour (2026-09-03)

- `GET /enheter/923609016` → 200. Used as the canonical fixture (Equinor ASA, `ASA`, VAT-registered, in Foretaksregisteret, has `kapital`, `stiftelsesdato`, `sisteInnsendteAarsregnskap`).
- `GET /enheter/974760673` → 200 (Registerenheten i Brønnøysund, `ORGL`, not VAT-registered, has `overordnetEnhet` and `epostadresse`). Useful second fixture: a public body with a different field mix.
- **`GET /enheter/833286602` → 404, with an empty body.** The build plan names this org.nr as the canonical test number. It is not in the register **and it fails MOD11** (weighted sum 145, remainder 2, so the check digit should be 9, not 2). It is not a valid organisasjonsnummer at all. **T03 must use `923609016` as the live-fetch fixture and `974760673` as the second one.** `833286602` is repurposed as the negative fixture in test 9 below. Raise this with the orchestrator: every done-check in `BRREG_MCP_BUILD_PLAN.md` and `tasks/` that names `833286602` should read `923609016`.
- A 404 body is empty — there is no JSON error document to parse. Do not try.
- **Deleted entities confirmed (2026-09-03) — T03.** Found live examples via `GET /oppdateringer/enheter?dato=2026-08-01T00:00:00.000Z&size=200`, filtering `endringstype == "Sletting"` (e.g. `921084846`, `915421970`, `969455706`, `987716770`). `GET /enheter/{orgnr}` on each returns **`200`, not `410`**, with a normal-shaped body carrying `"slettedato"` and `"respons_klasse": "SlettetEnhet"` (`historiskeNavn` still present, most other optional fields simply absent). This is fully handled by the ordinary 200 mapping path — status derivation's "`slettedato` is present → `DELETED`" rule (§8) fires without any special-casing in the client. A `410` may still occur for very old/purged records outside this API's retention window (unconfirmed, no example reachable) — the client keeps the defensive `410 → not_found` mapping in §6 as a belt-and-braces path, but the `200` + `slettedato` path is the one that actually happens and is the one covered by tests.

---

## 2. `CompanyReport` field mapping

Target model: `core/models.py :: CompanyReport`. Every field below is filled from `GET /enheter/{orgnr}` unless noted. Anything the JSON omits stays `None` — never `""`, never `0`.

| `CompanyReport` field | brreg field | Type | Notes |
|---|---|---|---|
| `country` | — | `str` | Constant `"NO"` |
| `registry` | — | `str` | Constant `"brreg"` |
| `id` | `organisasjonsnummer` | `str` | 9 digits, no separators |
| `id_formatted` | derived | `str` | `"923 609 016"` — three groups of three |
| `id_scheme` | — | `str` | Constant `"organisasjonsnummer"` |
| `name` | `navn` | `str` | As registered, usually upper-case |
| `previous_names` | `historiskeNavn[].navn` | `list[str]` | Newest first — reverse the API's order, which is oldest first |
| `legal_form_code` | `organisasjonsform.kode` | `str` | E.g. `"ASA"` |
| `legal_form` | derived, §7 | `str` | English label from the table |
| `legal_form_local` | `organisasjonsform.beskrivelse` | `str` | E.g. `"Allmennaksjeselskap"` |
| `limited_liability` | derived, §7 | `bool \| None` | |
| `has_board_duty` | derived, §7 | `bool \| None` | |
| `has_annual_accounts_duty` | derived, §7 | `bool \| None` | |
| `status` | derived, §8 | `CompanyStatus` | |
| `status_detail` | derived, §8 | `str` | One English sentence naming the flag it came from |
| `is_active` | derived | `bool` | `status == ACTIVE` |
| `registered_at` | `registreringsdatoEnhetsregisteret` | `date` | ISO `YYYY-MM-DD` |
| `founded_at` | `stiftelsesdato` | `date \| None` | Absent for public bodies |
| `business_register_registered_at` | `registreringsdatoForetaksregisteret` | `date \| None` | |
| `bankruptcy_date` | `konkursdato` | `date \| None` | Only present when `konkurs` is true |
| `deregistered_at` | `slettedato` | `date \| None` | Only on deleted entities. Confirmed live 2026-09-03 (see §1.1) |
| `vat_registered` | `registrertIMvaregisteret` | `bool` | |
| `vat_registered_at` | `registreringsdatoMerverdiavgiftsregisteret` | `date \| None` | |
| `vat_number` | derived | `str \| None` | `f"NO{id}MVA"` when `vat_registered` is true, else `None` |
| `in_business_register` | `registrertIForetaksregisteret` | `bool` | |
| `registers` | see below | `dict[str, bool]` | |
| `employees` | `antallAnsatte` | `int \| None` | Absent when `harRegistrertAntallAnsatte` is false |
| `employees_reported` | `harRegistrertAntallAnsatte` | `bool` | Distinguishes "0 employees" from "not reported" |
| `industry_codes` | `naeringskode1..3` | `list[IndustryCode]` | `rank` 1/2/3 in order; `scheme="NACE"` |
| `sector_code` | `institusjonellSektorkode.kode` | `str \| None` | |
| `sector` | `institusjonellSektorkode.beskrivelse` | `str \| None` | |
| `purpose` | `vedtektsfestetFormaal[]` | `str \| None` | Join with `" "`; the API splits it into arbitrary line fragments |
| `activity` | `aktivitet[]` | `str \| None` | Same join |
| `share_capital` | `kapital.belop` | `float \| None` | |
| `share_capital_currency` | `kapital.valuta` | `str \| None` | E.g. `"NOK"` |
| `business_address` | `forretningsadresse` | `Address \| None` | §3 |
| `postal_address` | `postadresse` | `Address \| None` | §3 |
| `website` | `hjemmeside` | `str \| None` | Often bare, no scheme (`"www.equinor.com"`) — do not add one |
| `email` | `epostadresse` | `str \| None` | |
| `phone` | `telefon` | `str \| None` | Norwegian formatting with spaces; pass through unchanged |
| `parent_id` | `overordnetEnhet` | `str \| None` | |
| `is_subunit` | derived | `bool` | True when fetched from `/underenheter`, or `legal_form_code in {"BEDR", "AAFY"}` |
| `in_group` | `erIKonsern` | `bool \| None` | |
| `last_annual_accounts_year` | `sisteInnsendteAarsregnskap` | `int \| None` | API gives a string, e.g. `"2025"` — cast to `int` |
| `confidence` | derived | `float` | `1.0` for identifier lookup (`DECISIONS.md` D-005) |
| `confidence_basis` | — | `str` | `"exact identifier lookup in Enhetsregisteret"` |
| `cached` | derived | `bool` | §9 |
| `fetched_at` | derived | `datetime` | UTC, timezone-aware |
| `source` | — | `str` | `"Enhetsregisteret (Brønnøysundregistrene)"` |
| `source_url` | — | `str` | `https://data.brreg.no/enhetsregisteret/api/enheter/{id}` |
| `license` | — | `str` | `"NLOD 2.0"` |
| `notes` | derived | `list[str]` | Caveats to surface — see §8 and §10 |

`registers` collects the remaining membership booleans, keyed by the Norwegian register name lower-cased:

```python
{
    "foretaksregisteret": registrertIForetaksregisteret,
    "stiftelsesregisteret": registrertIStiftelsesregisteret,
    "frivillighetsregisteret": registrertIFrivillighetsregisteret,
    "partiregisteret": registrertIPartiregisteret,
    "mvaregisteret": registrertIMvaregisteret,
}
```

Brreg fields deliberately **not** mapped: `maalform`, `paategninger`, `frivilligMvaRegistrertBeskrivelser`, `registreringsdatoFrivilligMerverdiavgiftsregisteret`, `registreringsdatoMerverdiavgiftsregisteretEnhetsregisteret`, `registreringsdatoAntallAnsatteEnhetsregisteret`, `registreringsdatoAntallAnsatteNAVAaregisteret`, `vedtektsdato`, `kapital.antallAksjer`, `kapital.type`, `kapital.innfortDato`, `respons_klasse`, `_links`. If T03 finds a caller needs one, add it to `core/models.py` in a follow-up — do not smuggle it into `notes`.

`historiskeNavn[].fraDato` / `tilDato` are `"YYYY-MM-DD HH:MM:SS"`, **not** ISO-8601 with a `T`. Do not feed them to `date.fromisoformat` without splitting on the space. We only use `.navn`, so this only bites if someone extends the mapping.

---

## 3. Address mapping

`forretningsadresse` and `postadresse` both have the same shape:

| `Address` field | brreg field |
|---|---|
| `lines` | `adresse` (a `list[str]`, may be empty) |
| `postal_code` | `postnummer` |
| `city` | `poststed` |
| `municipality` | `kommune` |
| `municipality_code` | `kommunenummer` |
| `country_code` | `landkode` |
| `country_name` | `land` |

`landkode` is already ISO-3166-1 alpha-2 (`"NO"`). A missing address object maps to `None`, not to an empty `Address`.

---

## 4. Search mapping

`GET /enheter?navn={q}&size={limit}` returns a HAL envelope:

```json
{
  "_embedded": {"enheter": [ …entity objects, same shape as lookup… ]},
  "_links": {...},
  "page": {"size": 2, "totalElements": 240, "totalPages": 120, "number": 0}
}
```

- `_embedded` is **absent** when there are no hits. `data.get("_embedded", {}).get("enheter", [])` — never index directly.
- `SearchResult.total` ← `page.totalElements`; `truncated` ← `total > len(hits)`.
- Each hit maps to a `SearchHit`: `id`←`organisasjonsnummer`, `name`←`navn`, `legal_form_code`←`organisasjonsform.kode`, `legal_form` from §7, `status` from §8, `city`←`forretningsadresse.poststed`, `municipality`←`forretningsadresse.kommune`, `registered_at`←`registreringsdatoEnhetsregisteret`.
- `SearchResult.hint` is always set, e.g. `"240 companies match. Call lookup_company with the id of the right hit for the full report."`
- `limit` is clamped to 1..100 (brreg's `size` maximum is 10 000, but a large page is useless to an agent and expensive to serialise). `limit` outside 1..100 → `RegistryError(bad_request)`, not a silent clamp, so the caller learns the range.
- Search hit confidence follows `DECISIONS.md` D-005: 0.95 exact case-insensitive name match, 0.8 the query is a prefix of the name, 0.6 all query tokens appear in the name, 0.4 otherwise.

---

## 5. Rules — `registries/no/rules.py`

### 5.1 MOD11 validation of an organisasjonsnummer

**Normalisation, in order:**
1. Strip all whitespace (including non-breaking space ` `), `.`, `-` and `/`.
2. Upper-case.
3. Strip a leading `NO` and a trailing `MVA` (the VAT form is `NO 923 609 016 MVA`).
4. What remains must be exactly 9 ASCII digits. Anything else → `RegistryError(invalid_id)`.

**Check digit:**
1. Weights for digits 1–8: `3, 2, 7, 6, 5, 4, 3, 2`.
2. `total = sum(digit_i * weight_i)`.
3. `remainder = total % 11`.
4. `check = 0 if remainder == 0 else 11 - remainder`.
5. **If `check == 10` the number is invalid** — such numbers are never issued, so no ninth digit can make it valid.
6. Valid iff `check == digit_9`.

The first digit of an issued organisasjonsnummer is 8 or 9 in practice, but this is **not** enforced: it is convention, not law, and legacy numbers exist. `VERIFY` if you want to add it — do not add it on a hunch.

Error on failure:

```python
RegistryError(
    ErrorCode.INVALID_ID,
    f"{raw!r} is not a valid Norwegian organisasjonsnummer.",
    hint=(
        "An organisasjonsnummer is nine digits with a MOD11 check digit, e.g. 923609016. "
        "If you have a company name instead, call search_company."
    ),
    country="NO", registry="brreg",
)
```

### 5.2 Norwegian public holidays

`registries/no/rules.py :: norwegian_holidays(year) -> frozenset[date]`. Movable dates come from Easter Sunday (anonymous Gregorian computus).

Fixed: 1 Jan (nyttårsdag), 1 May (arbeidernes dag), 17 May (grunnlovsdagen), 25 Dec (1. juledag), 26 Dec (2. juledag).
Movable, relative to Easter Sunday `E`: `E-3` skjærtorsdag, `E-2` langfredag, `E` 1. påskedag, `E+1` 2. påskedag, `E+39` Kristi himmelfartsdag, `E+49` 1. pinsedag, `E+50` 2. pinsedag.

Return a `frozenset` — dates collide (17 May 2027 is also 2. pinsedag) and a list would double-count.

**24 and 31 December are ordinary working days** for deadline purposes and are not in the set. `VERIFY` against Skatteetaten's own wording before launch.

### 5.3 Roll-forward

A statutory date falling on a Saturday, Sunday or public holiday moves to the next working day (forvaltningsloven § 30 / skattebetalingsloven). `core/rules/common.py :: roll_forward(d, holidays)` does the walking; the Norwegian module supplies the holidays for whatever years the walk can touch (pass at least `d.year` and `d.year + 1`).

Every `Deadline` records both dates: `statutory_date` (the date in the statute) and `due_date` (after roll-forward), with `rolled_forward = due_date != statutory_date`.

### 5.4 Filing deadlines — implement these six

Computed from `report.legal_form_code`, `report.vat_registered`, `report.employees` and the `today` parameter. Never from the clock.

| `kind` | `local_name` | Statutory date | Recurrence | Applies to |
|---|---|---|---|---|
| `annual_accounts` | Årsregnskap | 31 July, for the preceding calendar year | annual | forms with `has_annual_accounts_duty` (§7) |
| `general_meeting` | Ordinær generalforsamling | 30 June (six months after a calendar year end) | annual | `AS`, `ASA` |
| `tax_return` | Skattemelding for næringsdrivende | 31 May, for the preceding income year | annual | all forms except sub-units (`BEDR`, `AAFY`) |
| `shareholder_register_statement` | Aksjonærregisteroppgaven (RF-1086) | 31 January, for the preceding income year | annual | `AS`, `ASA` |
| `vat_return` | Mva-melding | see the term table below | bimonthly | `vat_registered == true` |
| `payroll_report` | A-melding | the 5th of the following month | monthly | `employees` is not `None` and `> 0` |

**VAT terms (ordinary bimonthly scheme):**

| Term | Period | Statutory date |
|---|---|---|
| 1 | Jan–Feb | 10 April, same year |
| 2 | Mar–Apr | 10 June, same year |
| 3 | May–Jun | **31 August**, same year |
| 4 | Jul–Aug | 10 October, same year |
| 5 | Sep–Oct | 10 December, same year |
| 6 | Nov–Dec | 10 February, **next** year |

Term 3 is the exception: the deadline is 31 August, not 10 August, because of the Norwegian summer holiday. It is a real rule and the most common thing to get wrong. `deadlines()` returns the **next** VAT term whose statutory date is on or after `today`, with `period_label` like `"2026 term 3 (May–Jun)"` and `period_start` / `period_end` set to the term's first and last day.

**Rules that apply to every deadline:**
- `days_until = (due_date - today).days`.
- Only the **next** occurrence of each `kind` is returned — one `Deadline` per `kind`, never a year's worth.
- Sorted by `due_date` ascending, then by `kind` for a stable order.
- `applies_because` is one English sentence naming the legal form or flag that triggered it, plus any assumption: *"An AS must file annual accounts with Regnskapsregisteret. Assumes a calendar-year accounting period."*
- Every deadline that assumes a calendar-year accounting period sets `mandatory=True` but adds that assumption to `applies_because` — a company with a deviating accounting year (`avvikende regnskapsår`) gets wrong dates and the register does not tell us which companies those are. `lookup` adds a `notes` entry saying so whenever it returns any annual deadline.
- Entities whose `status` is `DELETED`, `BANKRUPT` or `UNDER_COMPULSORY_LIQUIDATION` get **no** deadlines, and a single `notes` entry explaining why. `UNDER_LIQUIDATION` keeps its deadlines: a company in voluntary liquidation still files.
- Sub-units (`BEDR`, `AAFY`) get no deadlines — they are not legal entities. `notes` says to look up `parent_id` instead.

### 5.5 `DEFERRED` — do not implement in T02

Real obligations, deliberately left out of the first release because getting them wrong is worse than omitting them. Each needs a source check before it ships.

- **Forskuddsskatt for AS** — two instalments, 15 February and 15 April of the year after the income year. `VERIFY`.
- **Forskuddsskatt for personlig næringsdrivende (ENK)** — four instalments, 15 March / 15 June / 15 September / 15 December. `VERIFY`.
- **Årlig mva-melding** (turnover under 1 MNOK, on application) — 10 March of the following year. `VERIFY`; we cannot see who is on the scheme.
- **Deviating accounting years** — the register does not publish the accounting year, so every annual date is a calendar-year assumption.
- **Small-entity exemptions** from the annual-accounts duty for ENK/ANS/DA/NUF — they depend on turnover and balance-sheet totals we cannot see. §7 marks these forms `None`, not `False`.
- **Roles, board members, sub-unit lists, Regnskapsregisteret key figures.**

---

## 6. Client behaviour — `registries/no/client.py`

- **Timeout:** 5 s total per attempt (`httpx.Timeout(5.0)`).
- **Retry:** exactly one, and only on a timeout or a 5xx. Never on a 4xx. Back off 250 ms before the retry.
- **User-Agent:** `registry-mcp/{__version__} (+https://github.com/foretak/registry-mcp; {contact})` where `contact` is `os.environ["REGISTRY_MCP_CONTACT_EMAIL"]`, defaulting to `"unknown@example.invalid"` with a `logging.warning` when unset. Brreg asks for a contactable agent; an anonymous one can be blocked.
- **Headers:** `Accept: application/json`.
- **Connection reuse:** one module-level `httpx.AsyncClient`, created lazily, closed on shutdown.
- **Status handling:**

| Upstream | Result |
|---|---|
| 200 | Map and return |
| 404 on `/enheter` | Retry once against `/underenheter/{orgnr}`; if that is also 404 → `RegistryError(not_found)` |
| 410 | `RegistryError(not_found)` with `details={"deleted": true}` and the `slettedato` if the body carries one. Defensive: confirmed 2026-09-03 that live deleted entities actually answer `200` with `slettedato` set (see §1.1), not `410` — this row is kept for records outside the API's retention window, unconfirmed |
| 429 | `RegistryError(upstream_error)`, hint says to retry in a minute |
| 5xx (after the retry) | `RegistryError(upstream_error)` |
| timeout (after the retry) | `RegistryError(upstream_timeout)` |

`not_found` hint: `"No entity with organisasjonsnummer {id} exists in Enhetsregisteret. The number is well-formed, so it may never have been issued or the entity may have been deleted. Call search_company with the company name instead."`

---

## 7. Legal-form table

`registries/no/rules.py :: LEGAL_FORMS`. Codes and Norwegian descriptions come from `GET /organisasjonsformer` (fetched 2026-09-03); English labels and duties are ours.

`board` = must have a registered board (styre). `accounts` = must file annual accounts with Regnskapsregisteret. `None` means "depends on facts the register does not publish" — thresholds on turnover, balance sheet total or number of participants (see §5.5).

| Code | Norwegian | English | Limited liability | board | accounts |
|---|---|---|---|---|---|
| `AS` | Aksjeselskap | Private limited company | yes | yes | yes |
| `ASA` | Allmennaksjeselskap | Public limited company | yes | yes | yes |
| `ENK` | Enkeltpersonforetak | Sole proprietorship | no | no | `None` |
| `ANS` | Ansvarlig selskap med solidarisk ansvar | General partnership, joint and several liability | no | no | `None` |
| `DA` | Ansvarlig selskap med delt ansvar | General partnership, pro-rata liability | no | no | `None` |
| `NUF` | Norskregistrert utenlandsk foretak | Norwegian-registered branch of a foreign company | inherits | no | `None` |
| `SA` | Samvirkeforetak | Cooperative | yes | yes | yes |
| `STI` | Stiftelse | Foundation | yes | yes | yes |
| `KS` | Kommandittselskap | Limited partnership | partly | no | `None` |
| `BA` | Selskap med begrenset ansvar | Company with limited liability (legacy form, no longer issued) | yes | yes | yes |
| `FLI` | Forening/lag/innretning | Association, club or institution | yes | `None` | `None` |
| `KF` | Kommunalt foretak | Municipal enterprise | yes | yes | yes |
| `IKS` | Interkommunalt selskap | Inter-municipal company | no | yes | yes |

Additional codes seen in the wild. English labels are ours; duty columns are `None` until someone checks them (`VERIFY`), except the sub-unit forms, which are `False` because they are not legal entities.

| Code | Norwegian | English | board | accounts |
|---|---|---|---|---|
| `BEDR` | Underenhet til næringsdrivende og offentlig forvaltning | Branch / sub-unit of a business or public body | no | no |
| `AAFY` | Underenhet til ikke-næringsdrivende | Branch / sub-unit of a non-business entity | no | no |
| `ORGL` | Organisasjonsledd | Organisational unit of a public body | `None` | `None` |
| `SF` | Statsforetak | State-owned enterprise | `None` | `None` |
| `BRL` | Borettslag | Housing cooperative | `None` | `None` |
| `BBL` | Boligbyggelag | Housing construction cooperative | `None` | `None` |
| `ESEK` | Eierseksjonssameie | Condominium owners' association | `None` | `None` |
| `SPA` | Sparebank | Savings bank | `None` | `None` |
| `GFS` | Gjensidig forsikringsselskap | Mutual insurance company | `None` | `None` |
| `PK` | Pensjonskasse | Pension fund | `None` | `None` |
| `KBO` | Konkursbo | Bankruptcy estate | `None` | `None` |
| `SE` | Europeisk selskap | European company (SE) | `None` | `None` |
| `VPFO` | Verdipapirfond | Securities fund | `None` | `None` |
| `KOMM` / `FYLK` / `STAT` | Kommune / Fylkeskommune / Staten | Municipality / County / The State | `None` | `None` |
| `UTLA` | Utenlandsk enhet | Foreign entity | `None` | `None` |
| `PRE` | Partrederi | Shipping partnership | `None` | `None` |
| `TVAM` | Tvangsregistrert for MVA | Compulsorily VAT-registered | `None` | `None` |
| `SÆR` | Annet foretak iflg. særskilt lov | Other entity under a specific act | `None` | `None` |
| `ANNA` | Annen juridisk person | Other legal person | `None` | `None` |

The full list from `GET /organisasjonsformer` also contains `ADOS`, `BO`, `EOFG`, `IKJP`, `KIRK`, `KTRF`, `OPMV`, `PERS`, `SAM`. Treat any unlisted code as: `legal_form = organisasjonsform.beskrivelse`, all three duty fields `None`, and a `notes` entry saying the legal form is not classified yet. **Never guess a duty.** An unknown code must never produce a deadline.

---

## 8. Status derivation

From `konkurs`, `underAvvikling`, `underTvangsavviklingEllerTvangsopplosning` and `slettedato`, in this precedence — first match wins:

| # | Condition | `CompanyStatus` | `status_detail` |
|---|---|---|---|
| 1 | `slettedato` is present | `DELETED` | "Deleted from Enhetsregisteret on {date}." |
| 2 | `konkurs` is true | `BANKRUPT` | "Bankruptcy proceedings opened{on {konkursdato}}." |
| 3 | `underTvangsavviklingEllerTvangsopplosning` is true | `UNDER_COMPULSORY_LIQUIDATION` | "Under compulsory liquidation or dissolution ordered by a court." |
| 4 | `underAvvikling` is true | `UNDER_LIQUIDATION` | "Voluntary liquidation has been registered." |
| 5 | all four flags present and false/absent | `ACTIVE` | "Registered and active in Enhetsregisteret." |
| 6 | none of the flags present in the payload | `UNKNOWN` | "The registry record does not carry status flags." |

`CompanyStatus.DISSOLVED` is **not** used by Norway; it exists in the enum for countries that distinguish it. Do not map anything to it here.

Any status other than `ACTIVE` adds a plain-English `notes` entry, because an agent about to pay an invoice must see it without reading an enum: *"This company is bankrupt (registered 2026-07-08). Do not treat it as a going concern without checking with the bankruptcy estate."*

---

## 9. Cache

Per `DECISIONS.md` D-006. SQLite, one file, path from `REGISTRY_MCP_CACHE_PATH` (default `./data/cache.sqlite3`).

```sql
CREATE TABLE IF NOT EXISTS cache (
    key         TEXT PRIMARY KEY,   -- "NO:brreg:entity:923609016" | "NO:brreg:search:equinor:10"
    payload     TEXT NOT NULL,      -- the CompanyReport / SearchResult as JSON
    fetched_at  TEXT NOT NULL,      -- ISO-8601 UTC
    expires_at  TEXT NOT NULL,      -- ISO-8601 UTC
    status      TEXT NOT NULL       -- "ok" | "not_found"
);
CREATE INDEX IF NOT EXISTS cache_expires ON cache(expires_at);
```

- TTL 24 h for `ok`, 1 h for `not_found` (a company created yesterday should appear quickly).
- Search keys lower-case and strip the query, and include `limit`.
- A hit sets `cached=True` and keeps the **original** `fetched_at`, so an agent can see how stale the data is. A miss sets `cached=False`.
- `REGISTRY_MCP_CACHE_TTL_SECONDS` overrides the 24 h. `REGISTRY_MCP_CACHE_DISABLED=1` bypasses the cache entirely (used by T03's live done-check).
- Expired rows are deleted lazily on read; no background job.
- A cache failure (locked file, corrupt row) is logged and ignored — never turned into a `RegistryError`. The cache is an optimisation, not a dependency.

---

## 10. Errors

`{"error": {"code": ..., "message": ..., "hint": ...}}` — exactly `core/models.py :: RegistryError.to_dict()`, identical on REST and MCP (`DECISIONS.md` D-007). Codes the Norwegian module raises: `invalid_id`, `not_found`, `bad_request`, `upstream_error`, `upstream_timeout`, `not_implemented`.

Every hint must name the next call an agent can make. "Invalid organisasjonsnummer" is not a hint; "…nine digits with a MOD11 check digit, e.g. 923609016; if you have a company name instead, call search_company" is.

---

## 11. Logging

`core/log.py`, one function used by both surfaces (T08 builds it; specified here so T03 does not invent a second one):

```python
def log_call(
    *, surface: Surface, operation: str, country: str | None, query: str | None,
    user_agent: str | None, latency_ms: int, ok: bool,
    error_code: str | None = None, cached: bool | None = None,
) -> None: ...
```

SQLite table `calls(id, ts, surface, operation, country, query, user_agent, latency_ms, ok, error_code, cached)`, path from `REGISTRY_MCP_LOG_PATH` (default `./data/calls.sqlite3`). `query` is the org.nr or the search string — never a full request body, never headers. No IP addresses, no API keys. Logging never raises: wrap the whole body in `try/except Exception` and swallow.

---

## 12. Confidence

Per `DECISIONS.md` D-005, a float 0.0–1.0 with fixed anchors:

| Value | Meaning |
|---|---|
| 1.0 | Retrieved by exact national identifier |
| 0.95 | Search hit whose name matches the query exactly, case-insensitively |
| 0.8 | Search hit whose name starts with the query |
| 0.6 | Search hit containing every token of the query |
| 0.4 | Any other search hit the registry returned |

`confidence_basis` always spells the reason out in English so an agent can quote it.

---

## 13. Numbered rules test list

**T02 implements exactly this list**, in `tests/no/test_rules.py` and `tests/test_rules_common.py`, one test function per number, named `test_NN_<slug>`. Every date below was computed against the real calendar; if an implementation disagrees, the implementation is wrong.

Fixed `today` values are used throughout so nothing depends on the clock.

### A. `validate_id` — MOD11 and normalisation

1. `"923609016"` → `"923609016"` (valid; weighted sum 126, remainder 5, check 6).
2. `"974760673"` → `"974760673"` (valid; weighted sum 173, remainder 8, check 3).
3. `"934154150"` → `"934154150"` (valid; weighted sum 121, remainder 0, so the check digit is 0 — the `remainder == 0` branch).
4. `"923 609 016"` → `"923609016"` (spaces stripped).
5. `"923.609.016"` → `"923609016"` (dots stripped).
6. `"NO923609016MVA"` → `"923609016"` (VAT form stripped).
7. `"NO 923 609 016 MVA"` → `"923609016"` (VAT form with spaces).
8. `"923609017"` → raises `RegistryError(invalid_id)` (wrong check digit).
9. `"833286602"` → raises `RegistryError(invalid_id)` (weighted sum 145, remainder 2, check should be 9). This is the number the build plan wrongly names as a live fixture.
10. `"934157150"` → raises `RegistryError(invalid_id)` (weighted sum 133, remainder 1, so the check digit would have to be 10 — the unissuable case).
11. `"92360901"` → raises `RegistryError(invalid_id)` (8 digits).
12. `"9236090160"` → raises `RegistryError(invalid_id)` (10 digits).
13. `"92360901A"` → raises `RegistryError(invalid_id)` (non-digit).
14. `""` → raises `RegistryError(invalid_id)` (empty).
15. The error raised by test 8 has `code == ErrorCode.INVALID_ID`, a non-empty `hint`, and the string `"search_company"` in the hint.

### B. Legal-form mapping

16. `"AS"` → English `"Private limited company"`, `limited_liability=True`, `has_board_duty=True`, `has_annual_accounts_duty=True`.
17. `"ASA"` → `has_board_duty=True`, `has_annual_accounts_duty=True`.
18. `"ENK"` → `limited_liability=False`, `has_board_duty=False`, `has_annual_accounts_duty=None`.
19. `"ANS"` and `"DA"` → both `limited_liability=False`, `has_annual_accounts_duty=None`.
20. `"NUF"` → `has_board_duty=False`, `has_annual_accounts_duty=None`.
21. `"SA"`, `"STI"`, `"KF"`, `"IKS"`, `"BA"` → all `has_annual_accounts_duty=True`.
22. `"KS"` → `has_annual_accounts_duty=None`.
23. `"FLI"` → `has_board_duty=None`, `has_annual_accounts_duty=None`.
24. `"BEDR"` → `has_board_duty=False`, `has_annual_accounts_duty=False`, and the mapper reports it as a sub-unit form.
25. `"ZZZZ"` (unknown code, `beskrivelse="Fantasiform"`) → `legal_form == "Fantasiform"`, all three duty fields `None`, and a note recording that the form is unclassified.

### C. Status derivation

Inputs are the four flags as they appear in the brreg payload.

26. all flags false, no `slettedato` → `ACTIVE`, `is_active is True`.
27. `konkurs=True`, `konkursdato="2026-07-08"` → `BANKRUPT`, `bankruptcy_date == date(2026, 7, 8)`, `is_active is False`.
28. `underAvvikling=True` → `UNDER_LIQUIDATION`.
29. `underTvangsavviklingEllerTvangsopplosning=True` → `UNDER_COMPULSORY_LIQUIDATION`.
30. `slettedato="2024-01-15"` with all other flags false → `DELETED`, `deregistered_at == date(2024, 1, 15)`.
31. `slettedato="2024-01-15"` **and** `konkurs=True` → `DELETED` (precedence: deletion wins).
32. `konkurs=True` **and** `underAvvikling=True` → `BANKRUPT` (precedence).
33. Payload carrying none of the four keys → `UNKNOWN`.
34. Any non-`ACTIVE` status adds at least one entry to `report.notes`.

### D. `core/rules/common.py` — country-neutral date helpers

35. `next_weekday(date(2026, 8, 1))` (Saturday) → `date(2026, 8, 3)` (Monday).
36. `next_weekday(date(2026, 7, 31))` (Friday) → `date(2026, 7, 31)` (unchanged).
37. `next_weekday(date(2027, 7, 31))` (Saturday) → `date(2027, 8, 2)` (Monday).
38. `is_business_day(date(2026, 3, 15))` (Sunday) → `False`.
39. `is_business_day(date(2026, 3, 16))` (Monday) → `True`.
40. `is_business_day(date(2026, 5, 17), holidays={date(2026, 5, 17)})` → `False`.
41. `roll_forward(date(2026, 5, 14), holidays=<NO 2026>)` (Kristi himmelfartsdag, a Thursday) → `date(2026, 5, 15)` (Friday).
42. `roll_forward(date(2026, 12, 25), holidays=<NO 2026>)` (Friday, 1. juledag; 26th is Saturday and 2. juledag; 27th is Sunday) → `date(2026, 12, 28)` (Monday).
43. `roll_forward(date(2026, 3, 16), holidays=<NO 2026>)` (an ordinary Monday) → unchanged.
44. `next_occurrence(7, 31, date(2026, 1, 15))` → `date(2026, 7, 31)` (this year, not yet passed).
45. `next_occurrence(7, 31, date(2026, 7, 31))` → `date(2026, 7, 31)` (today counts — inclusive).
46. `next_occurrence(7, 31, date(2026, 8, 1))` → `date(2027, 7, 31)` (passed, so next year).
47. `next_occurrence(2, 29, date(2026, 3, 1))` → `date(2027, 2, 28)` (clamped: 2027 is not a leap year).
48. `last_day_of_month(2026, 2)` → `date(2026, 2, 28)`; `last_day_of_month(2028, 2)` → `date(2028, 2, 29)`.
49. `add_months(date(2026, 1, 31), 1)` → `date(2026, 2, 28)` (clamped).
50. `add_months(date(2026, 12, 10), 2)` → `date(2027, 2, 10)` (year rolls over).

### E. Norwegian holidays

51. `norwegian_holidays(2026)` contains 2026-01-01, 2026-05-01, 2026-05-17, 2026-12-25, 2026-12-26.
52. `norwegian_holidays(2026)` contains the Easter set: 2026-04-02, 2026-04-03, 2026-04-05, 2026-04-06 (Easter Sunday 2026 is 5 April).
53. `norwegian_holidays(2026)` contains 2026-05-14 (Kristi himmelfartsdag), 2026-05-24 and 2026-05-25 (pinse).
54. `norwegian_holidays(2027)` contains 2027-03-25, 2027-03-26, 2027-03-28, 2027-03-29 (Easter Sunday 2027 is 28 March).
55. `norwegian_holidays(2027)` has 17 May 2027 exactly once, even though it is both grunnlovsdagen and 2. pinsedag — the return value is a set.
56. `norwegian_holidays(2026)` does **not** contain 2026-12-24 or 2026-12-31.

### F. Deadlines

The subject is an active `AS`, VAT-registered, with 3 employees, unless stated otherwise. `today` is given per test.

57. `today=2026-01-15` → `annual_accounts` has `statutory_date == due_date == date(2026, 7, 31)` (a Friday), `rolled_forward is False`, `period_label == "2025"`.
58. `today=2026-08-01` → `annual_accounts` has `statutory_date == date(2027, 7, 31)` (a Saturday) and `due_date == date(2027, 8, 2)` (Monday), `rolled_forward is True`, `period_label == "2026"`.
59. `today=2026-01-15` → `tax_return` has `statutory_date == date(2026, 5, 31)` (a Sunday) and `due_date == date(2026, 6, 1)` (Monday), `rolled_forward is True`.
60. `today=2026-06-02` → `tax_return` moves to the next year: `statutory_date == date(2027, 5, 31)` (a Monday), `due_date` the same, `rolled_forward is False`.
61. `today=2026-01-15` → `shareholder_register_statement` has `statutory_date == date(2026, 1, 31)` (a Saturday) and `due_date == date(2026, 2, 2)` (Monday).
62. `today=2026-03-01` → `shareholder_register_statement` has `statutory_date == date(2027, 1, 31)` (a Sunday) and `due_date == date(2027, 2, 1)` (Monday).
63. `today=2026-01-15` → `general_meeting` has `due_date == date(2026, 6, 30)` (a Tuesday), `rolled_forward is False`.
64. `today=2026-07-01` → VAT: the next term is term 3, `statutory_date == due_date == date(2026, 8, 31)` (a Monday), `period_label == "2026 term 3 (May–Jun)"`, `period_start == date(2026, 5, 1)`, `period_end == date(2026, 6, 30)`.
65. `today=2026-09-01` → VAT term 4, `statutory_date == date(2026, 10, 10)` (a Saturday), `due_date == date(2026, 10, 12)` (Monday).
66. `today=2026-12-15` → VAT term 6, `statutory_date == due_date == date(2027, 2, 10)` (a Wednesday), `period_label == "2026 term 6 (Nov–Dec)"`.
67. `today=2026-03-01` → VAT term 1, `statutory_date == due_date == date(2026, 4, 10)` (a Friday).
68. `today=2026-03-10` (3 employees) → `payroll_report` has `statutory_date == date(2026, 4, 5)` (a Sunday, and Easter Sunday; 6 April is 2. påskedag) and `due_date == date(2026, 4, 7)` (Tuesday).
69. `today=2026-08-10` → `payroll_report` has `statutory_date == date(2026, 9, 5)` (a Saturday) and `due_date == date(2026, 9, 7)` (Monday).
70. A company with `vat_registered=False` gets no `vat_return` deadline.
71. A company with `employees=None` gets no `payroll_report` deadline; one with `employees=0` also gets none.
72. An `ENK` (`has_annual_accounts_duty=None`) gets **no** `annual_accounts` deadline and no `shareholder_register_statement`, but does get `tax_return`.
73. An `ENK` gets no `general_meeting` deadline.
74. A `BEDR` sub-unit gets an empty deadline list and a `notes` entry pointing at `parent_id`.
75. A `BANKRUPT` company gets an empty deadline list and a `notes` entry saying why.
76. A `DELETED` company gets an empty deadline list.
77. An `UNDER_LIQUIDATION` company still gets its full deadline list — voluntary liquidation does not suspend filing.
78. The returned list is sorted by `due_date` ascending; for `today=2026-01-15` the first `kind` is `shareholder_register_statement` (due 2026-02-02).
79. Exactly one `Deadline` is returned per `kind` — no `kind` appears twice.
80. Every returned `Deadline` has `country == "NO"`, `registry == "brreg"`, a non-empty `applies_because`, and `days_until == (due_date - today).days`.
81. `deadlines(report, today)` called twice with the same arguments returns equal lists (purity), and calling it with `today=date(2026, 1, 15)` on two different machine timezones gives the same answer (no clock reads).

### G. Mapping (T03 — same numbering continues, in `tests/no/test_mapping.py`)

82. The stored 923609016 fixture maps to `name == "EQUINOR ASA"`, `legal_form_code == "ASA"`, `id_formatted == "923 609 016"`, `vat_registered is True`, `vat_number == "NO923609016MVA"`.
83. Same fixture: `previous_names[0] == "STATOIL ASA"` (newest first — the API's array is oldest first).
84. Same fixture: `industry_codes` has three entries with `rank` 1, 2, 3 and `code == "06.100"` first.
85. Same fixture: `share_capital == 5976872600.0`, `share_capital_currency == "NOK"`, `last_annual_accounts_year == 2025` (an `int`, not `"2025"`).
86. Same fixture: `business_address.city == "STAVANGER"`, `business_address.lines == ["Forusbeen 50"]`, `postal_address.lines == ["Postboks 8500"]`.
87. The 974760673 fixture maps `email == "firmapost@brreg.no"`, `parent_id == "912660680"`, `founded_at is None`, `share_capital is None`.
88. A fixture with `harRegistrertAntallAnsatte: false` maps `employees is None` and `employees_reported is False` — never `employees == 0`.
89. A search response with no `_embedded` key maps to `SearchResult(hits=[], total=0)` and does not raise.
90. A 404 from both `/enheter` and `/underenheter` raises `RegistryError(not_found)` whose hint mentions `search_company`.
91. Two identical `lookup` calls: the first has `cached is False`, the second `cached is True` with the **same** `fetched_at`.
92. A `respx`-mocked 500 followed by a 200 returns the report — exactly one retry, verified by the mock's call count.
93. Two consecutive 500s raise `RegistryError(upstream_error)`; the mock was called exactly twice, not three times.
94. A 404 is **not** retried against the same URL: the `/enheter` mock is called exactly once.
95. The outgoing `User-Agent` header contains `registry-mcp` and the value of `REGISTRY_MCP_CONTACT_EMAIL`.

### H. Live done-check (T03, network — mark `@pytest.mark.live`, excluded from CI)

96. A live `lookup("923609016")` returns a `CompanyReport` with `cached is False`; a second call within the TTL returns `cached is True`.
97. Every brreg field name used by the mapper is present in the live 923609016 payload, or is explicitly listed as optional in §2. Any field this spec names that the live payload does not have is a **blocking** finding for `REVIEW.md` — not something to work around.

---

## 14. What T02 and T03 own

**T02 — rules.** `core/rules/common.py` (bodies for the six signatures Opus A left), `registries/no/rules.py` (MOD11, holidays, legal-form table, status derivation, the six deadlines), `tests/test_rules_common.py`, `tests/no/test_rules.py` — tests 1–56 and 57–81. Target 100% coverage of both rules modules.

**T03 — client and mapping.** `registries/no/client.py`, `registries/no/mapping.py`, `registries/no/cache.py`, wiring `BrregRegistry.lookup` / `.search` in `registries/no/__init__.py`, `tests/no/conftest.py` (stored fixtures), `tests/no/test_mapping.py`, `tests/no/test_client.py` — tests 82–97.

Neither may edit `core/models.py` or `core/registry.py`. If a shape is wrong, say so in `REVIEW.md` and let Opus A change it — a silently widened model breaks the REST/MCP parity that `DECISIONS.md` D-004 exists to guarantee.

---

## 15. Serving static files

*(Appended by T05. The files themselves are written and owned by T05; **T06 implements the routes.**)*

The discovery layer is four static files in `static/` plus `server.json` at the repo root. They are how an agent or a registry crawler finds the service without being told about it, so they must be served from the API origin itself — not only from GitHub.

| Route | File | Content-Type |
|---|---|---|
| `GET /` | `static/index.html` | `text/html; charset=utf-8` |
| `GET /llms.txt` | `static/llms.txt` | `text/plain; charset=utf-8` |
| `GET /llms-full.txt` | `static/llms-full.txt` | `text/plain; charset=utf-8` |
| `GET /server.json` | `server.json` (repo root) | `application/json; charset=utf-8` |

Rules:

- **`charset=utf-8` is mandatory on the two `.txt` routes.** They contain `Brønnøysundregistrene`, `Årsregnskap` and an en dash; served as latin-1 they are mojibake to the crawler that matters most.
- These four routes are **exempt from the rate limiter**. A registry crawler hitting `/llms.txt` must never get a 429 — that is the one request we most want to succeed.
- They are **not** logged through `core/log.py` (§11). The stats page counts API calls by agents, and static reads would drown the signal. If crawler traffic is wanted later it gets its own counter.
- Files are read from disk at request time (or on startup with a mtime check), never inlined into Python. T05 owns their contents and will edit them without touching `api/`.
- `server.json` is served verbatim from the repo root, byte-for-byte identical to what is published to the official MCP registry. Do not regenerate or reformat it in the API layer — the `$schema` field pins a dated schema version and the registry validates against it.
- `GET /health` (§ build plan 2.5) stays a separate JSON route and is not part of this set.
- Anything else under `/` is a 404 in the standard error envelope of §10, with a `hint` naming `/llms.txt` — a crawler that guesses a path should be told where the real map is.

Path resolution: `static/` sits at the repo root, next to `src/`. Resolve it from the installed package location or an explicit `REGISTRY_MCP_STATIC_DIR` environment variable rather than from the process working directory, so the routes still work under Docker and under `uvx`. If the directory is missing, log a warning at startup and serve 404s for these four routes — a missing homepage must not stop the API from booting.
