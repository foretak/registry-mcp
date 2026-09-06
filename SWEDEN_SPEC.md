# SWEDEN_SPEC — the Sweden module (`registries/se/`)

Technical specification for the Swedish module of `registry-mcp`, the **third** country: the first
that needs *two* secrets, the first with no status field at all, the first whose identifier does not
always identify one business — and the first where **HTTP 200 does not mean the data arrived**.

**Status:** written by Opus A in T26a on 2026-09-05, from the research library brief
`~/research/registry-mcp/02-registers-landscape/02-sweden-bolagsverket.md` and — for the API shape,
the code lists, the auth flow and the statutes — from
`~/research/registry-mcp/02-registers-landscape/02b-sweden-api-shape-and-law.md` (T26r) together
with the **OpenAPI 3.0.3 document itself**, saved verbatim beside it as `02b-sweden-openapi.json`
and read directly for this file. §1, §2, §3, §7 and §8 are written against that document, not
against a field table.

**No live payload has ever been observed.** Bolagsverket credentials arrive only after a human fills
in the *kundanmälan* form (§1.1, T26 §Human step), so unlike `UK_SPEC.md` this file has no
"live arithmetic" section. What it has instead is better than the previous pass had any right to
expect: Bolagsverket's own request/response **examples**, its **test-company workbook**, and its
**complete code lists**, all read anonymously from the developer portal. Authoritative for T26b.

**How to read the markers** — the `NORBIZ_SPEC.md` / `UK_SPEC.md` convention, with one addition:

| Marker | Meaning |
|---|---|
| *(no marker)* | Confirmed against a primary source — the OpenAPI document, Bolagsverket's own examples and code lists, or the statute text — on 2026-09-05. |
| `VERIFY` | Not confirmed. T26b confirms it before the mapping is final. **If verification fails, the item is dropped, not guessed.** |
| `VERIFY-live` | Cannot be confirmed until credentials exist. Ships behind a documented shape and is re-verified in **T26d**, not T26b. |
| `DEFERRED` | Real but deliberately out of scope for T26b. Do not implement. |

> **Read this before writing a line of `mapping.py`.** Five things about Sweden are different from
> both live countries, and every one of them is a wrong *answer* rather than a crash.
>
> 1. **Every field is a wrapper carrying its own `dataproducent` and its own `fel`** (§1.6). A 200
>    with `fel.typ = "OTILLGANGLIG_UPPGIFTSKALLA"` is a *successful* HTTP response containing no
>    data. A mapper that reads the value without reading `fel` reports an unnamed company during a
>    Bolagsverket outage — and caches it for 24 hours.
> 2. **`not_found` is in the body, not in the status code** (§1.7). `POST /organisationer` declares
>    no 404 at all.
> 3. **`organisationer` is an array and for a sole trader it is genuinely plural** (§2.2).
>    Bolagsverket's own example returns *two* businesses for one identifier. And a sole trader's
>    identifier is a **personnummer**.
> 4. **The payload carries two authorities' vocabularies at once** (§7): Bolagsverket's
>    `organisationsform` and SCB's `juridiskForm` are different code lists and the mapping between
>    them is many-to-one and lossy.
> 5. **There is no status field.** Three orthogonal signals can all be true at once, and one of them
>    (`verksamOrganisation`) can contradict the other two without either being wrong (§8).

Everything here is Swedish. Nothing here may be imported into `core/` (D-001). Where this file says
`core/…` or `registries/…`, read `src/registry_mcp/core/…` and `src/registry_mcp/registries/…`
(D-003).

The country code is **`SE`**; the registry slug is **`bolagsverket`**, even though roughly half the
values come from SCB — §1.9 says why one slug, and §7 says what the module does about it.

---

## 0. Findings for the orchestrator

Three things this spec turned up that `registries/se/` **cannot fix inside its own folder**. None
blocks T26b; all three are for Kim via the orchestrator.

> **F1 — A Swedish sole trader's identifier is a personnummer, and `core/log.py` stores it.**
> `api/main.py:652,657,740,747,780` (and the MCP surface) pass the caller's raw `id` to
> `core/log.py::log_call` as `query`, which writes it into the `calls` table. For `NO` and `GB` that
> string is a company number. For `SE` it is, on every sole-trader lookup, a Swedish national
> personal identity number — sitting in an operator's SQLite file beside a timestamp and a
> user-agent. `registries/se/` has no way to intervene: the logging happens in the surface, around
> the country module, not inside it. Bolagsverket takes the same view of the identifier, which is
> **why its read operations are POSTs rather than GETs** (§1.4): it keeps the identitetsbeteckning
> out of URLs, access logs and `Referer` headers. We would be putting it back into a log.
> **This is a `core/` + `api/` finding, not a Sweden finding.** The smallest shape that would close
> it: a `Registry` class attribute (`id_may_be_personal: ClassVar[bool] = False`) that the two call
> sites consult, storing a salted hash — or nothing — instead of the raw query, exactly as D-028(2)
> reaches into `core/cache.py`'s TTL table for person-bearing kinds. **Not authorised by T26a and
> not implemented here.** What T26b *can* do without a `core/` edit is put the fact in `notes`
> (§2.1 N8, D-039) and in `rules_markdown()` (§13). **Ruled 2026-09-06: D-040** (nothing is
> stored, not a hash; blanket by country; one helper in `core/`; uvicorn access log off) — brief in
> `tasks/T28.md`, waiting on Kim's "do F1".
>
> **F2 — `core/registry.py`'s own docstring example is an invalid organisationsnummer.**
> `src/registry_mcp/core/registry.py:15` illustrates the contract with `id_example = "5560212524"`.
> That number fails the check digit of §5.1 (weighted sum 27, so the tenth digit would have to be
> `3`, not `4`). It is an illustrative docstring, it runs nothing and breaks nothing, and correcting
> it is a `core/` edit T26a is not authorised to make. Recorded so nobody copies it into
> `registries/se/__init__.py`. Suggested replacement, if some other task fixes it: `"5560160680"`.
>
> **F3 — `search_company` cannot be served for Sweden at all**, and the contract has no way to say
> so in advance. The free API has four operations and none of them accepts a name (§1.4). `search`
> therefore raises `not_implemented` (§4) — which is the right error and carries the right hint —
> but `CountryInfo` publishes `requires_api_key` and not "which operations this country can answer",
> so an agent can only learn it by calling. D-017's own reasoning ("the flag makes the constraint
> discoverable in advance, it does not replace the error") applies here one field over. **No core
> edit is requested**: the error plus `rules_markdown()` plus the README line is a complete answer
> today, and a `supported_operations` field is a decision that should be taken when a *second*
> country needs it, not on one example. **The D-031 ChatGPT `search` alias is unaffected** —
> `mcp/connector.py:322-327` already drops any country whose `search` raises a `RegistryError`, and
> `not_implemented` is one; verified against the code, not assumed (§4).

---

## 1. The upstream API

Bolagsverket's WSO2 developer portal **allows anonymous reads**: the API list, the OpenAPI document,
and the attached PDFs and code lists are all served without credentials at
`https://portal.api.bolagsverket.se/api/am/devportal/v3/…`. Only *calling* the API needs a
credential. The OpenAPI document is saved verbatim at
`~/research/registry-mcp/02-registers-landscape/02b-sweden-openapi.json` — **T26b works from that
file, not from this table.**

`openapi: "3.0.3"`, `info.title: "VärdefullaDatamängder"`, `info.version: "v1"`, one server:

```json
"servers": [ { "url": "https://gw.api.bolagsverket.se/vardefulla-datamangder/v1" } ]
```

### 1.1 Environments, and the token host the project had wrong

From the portal's **Connection establishment guide v1.01 (2025-02-10)**:

| | Production | Test ("accept2") |
|---|---|---|
| API base | `https://gw.api.bolagsverket.se/vardefulla-datamangder/v1` | `https://gw-accept2.api.bolagsverket.se/vardefulla-datamangder/v1` |
| Token | `https://portal.api.bolagsverket.se/oauth2/token` | `https://portal-accept2.api.bolagsverket.se/oauth2/token` |

> **The token host is `portal.api.bolagsverket.se`, not `gw.api.bolagsverket.se`.** Both `T26.md`
> and the earlier library file say `https://gw.api.bolagsverket.se/oauth2/token`; that is wrong.
> The OpenAPI `securitySchemes` block gives `"tokenUrl": "/oauth2/token"` as a bare relative path,
> which is what invited the wrong absolutisation, and the same block declares an unused *implicit*
> flow at `https://gw.api.bolagsverket.se/authorize` — **ignore it**; use the `clientCredentials`
> flow.

### 1.2 Authentication — OAuth 2 client credentials, therefore two secrets

Token request, verbatim from the guide's own cURL example:

```
POST https://portal-accept2.api.bolagsverket.se/oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
client_id=myClientID
client_secret=myClientSecret
scope=vardefulla-datamangder:read vardefulla-datamangder:ping
```

```json
{ "access_token": "…", "scope": "vardefulla-datamangder:read vardefulla-datamangder:ping",
  "token_type": "Bearer", "expires_in": 3600 }
```

Both scopes are requested in **one** call, space-separated. The guide warns: *"the API resources are
also protected by 'scopes' which must be declared in the request when fetching a token. If they are
not present in the token, subsequent calls to the APIs resources using that token will fail."*
`expires_in: 3600` appears only in a documentation example — **read it from the response, never
hard-code an hour** (`VERIFY-live` the production lifetime). Header prefix is `Bearer`.

**Two secrets in a one-slot contract.** D-017 gave `Registry` a single `api_key_env: ClassVar[str]`.
Sweden needs `BOLAGSVERKET_CLIENT_ID` **and** `BOLAGSVERKET_CLIENT_SECRET`. D-037 rules:
`api_key_env = "BOLAGSVERKET_CLIENT_ID"` — the variable an operator sets first and the one checked
first — and **every error hint names both**, because D-007 already makes the hint the place a
complete next action lives. Widening the class attribute to a list is a `core/` edit and is not
taken here.

**Read both at call time, never at import time.** `registries/__init__.py` imports every bundled
country unconditionally at package load (`core/registry.py::_load_registries`), so an
`os.environ[...]` at module scope would take the whole server down on a deployment that only wants
Norway. Same rule as `UK_SPEC.md` §1.1; tested by §14 test 100.

### 1.3 Getting credentials — the kundanmälan form

**Form:**
<https://bolagsverket.se/apierochoppnadata/hamtaforetagsinformation/vardefulladatamangder/kundanmalantillapiforvardefulladatamangder.5528.html>
(page "Uppdaterad: 2026-07-07"). Two fields, both required, and **nothing else** — no company name,
no org.nr, no use-case description, no account:

> **E-postadress \*** — *"Adressen får inte vara en noreply-adress utan måste vara en giltig
> e-postadress där Bolagsverket kan nå dig med frågor angående ditt konto."*
> **Mobilnummer \***

> "Det krävs inget avtal för att du ska få använda vårt API för värdefulla datamängder."
> "Värdefulla datamängder är avgiftsfritt."

What arrives, and this is the operationally surprising part — from the connection guide:

> *"Values for 'client ID' and 'client secret' are delivered to the user via email as an **encrypted
> zip file** when access is given to the user in Bolagsverkets environment. The password is sent
> separately in an SMS."*

So the SMS carries the **zip password**, not the secret. One submission yields both test and
production credentials. A standing notice dated 2026-05-13 warns that response times are currently
longer than usual (*"Hög belastning på API-supporten"*), so the human step should be started early.

### 1.4 The four operations — and there is no search

| Method | Path | operationId | Scope | Body / param |
|---|---|---|---|---|
| GET | `/isalive` | `isalive` | `vardefulla-datamangder:ping` | none |
| **POST** | **`/organisationer`** | `organisationer` | `vardefulla-datamangder:read` | `{"identitetsbeteckning": "…"}` |
| POST | `/dokumentlista` | `dokumentlista` | `vardefulla-datamangder:read` | same single field. `DEFERRED` |
| GET | `/dokument/{dokumentId}` | `dokument` | `vardefulla-datamangder:read` | returns `application/zip`. `DEFERRED` |

**Nothing accepts a company name.** `search_company` for `SE` cannot be served by this API (§4, §0
F3). The bulk "Nedladdningsbara filer" download is a separate product and a name index would have to
be built from it — `DEFERRED`, but named in every hint that needs an alternative.

**The identifier travels in a POST body, not a URL, and this module must not "optimise" that.**
Bolagsverket's stated reason is that an identitetsbeteckning is personal data and a URL leaks it
into access logs and `Referer` headers. A `GET /organisationer?identitetsbeteckning=…` would be
faster to cache and would undo a deliberate privacy design. (It is also the register agreeing with
finding F1.)

Two header parameters are declared on every data operation:

- **`X-Request-Id`** — *"Client generated ID to call the API. In case of error this will be sent in
  the attribute `requestId` or as a header attribute."* Optional, and the **only** handle for a
  Bolagsverket support case. Send a fresh UUID4 per request and log it at DEBUG (§11).
- `Authorization` — declared `required: false` in the document, which is a spec artefact; it is
  required in practice.

### 1.5 Rate limit — 60 requests per minute, the tightest in the project

From the API page (`apiforvardefulladatamangder.5513.html`, "Uppdaterad: 2026-06-30"):

> "Prestandan för detta API tillåter varje användare att göra **60 frågor/minut**."

For comparison: Companies House allows 600 per five minutes (120/min); Brønnøysundregistrene
publishes no limit. Consequences, all design constraints rather than notes:

- The client carries a token bucket, **capacity 60, refill 1.0 token/second** (§6). Unlike
  Britain's, this limiter is not merely a runaway guard — a modest agent loop can reach 60/min
  legitimately, so the bucket is what turns a burst into a short queue instead of a 429.
- **The token request spends a bucket token too.** Whether Bolagsverket meters the token endpoint
  against the same budget is unknown; over-counting costs one request an hour, under-counting risks
  a 429 storm.
- Caching is load-bearing, not an optimisation (§9).

The portal's public subscription-tier list shows 25 policies, all `"tierPlan":"FREE"`, banded by
monthly quota (100 / 500 / 1000 / 3000 / 5000 / 15000 …), each with `"rateLimitCount":20,
"rateLimitTimeUnit":"sec"`. **Which policy the värdefulla-datamängder subscription gets is not
public**, and 20/sec is a burst ceiling, not the documented limit. **Build to the published 60/min**
and treat a monthly quota as a `VERIFY-live` unknown that will announce itself as a 429.

No rate-limit response headers are documented. Read `Retry-After` and any `X-RateLimit-*` header
defensively; absent, say "about a minute" (§6).

### 1.6 Every field is a wrapper — provenance and failure, per field

This is the single most important shape fact in the document, and it has no analogue in `NO` or
`GB`. A field is not a scalar; it is an object carrying `dataproducent` and `fel` beside its value:

```json
"Dataproducent": { "type": "string", "enum": [ "Bolagsverket", "SCB" ] }
"Fel": { "required": ["typ"],
         "properties": { "typ": {"$ref": "#/components/schemas/FelTyp"},
                         "felBeskrivning": {"type": "string"} } }
"FelTyp": { "enum": [ "ORGANISATION_FINNS_EJ", "OGILTIG_BEGARAN",
                      "OTILLGANGLIG_UPPGIFTSKALLA", "TIMEOUT" ] }
"JaNej":  { "enum": [ "JA", "NEJ" ] }
```

Bolagsverket ships a dedicated example, `organisationer-fel-fran-en-uppgiftskalla-svar`, in which
every Bolagsverket-sourced field has a null value and:

```json
"fel": { "felBeskrivning": "Uppkoppling mot Bolagsverket misslyckades. Efterfrågade uppgifter kunde inte hämtas.",
         "typ": "OTILLGANGLIG_UPPGIFTSKALLA" }
```

Three rules follow, and they are requirements, not advice:

1. **Read `fel` before reading a value, on every field.** A mapper that does not will report an
   unnamed, formless, dateless company during a Bolagsverket outage and present it as a fact.
2. **A partially failed 200 is never written to the cache** (§9). D-006 permits this — the cache is
   ours and a partial answer is not a fact worth keeping for 24 hours.
3. **`dataproducent` is read, not assumed.** The published field table says `naringsgren` is SCB's;
   Bolagsverket's own aktiebolag example returns it with `"dataproducent": "Bolagsverket"`. The
   join rule — *"Data från Bolagsverket hämtas när det finns data att hämta från både Bolagsverket
   och SCB. Data från SCB hämtas när inget data finns att hämta från Bolagsverket"* — means either
   authority can answer for most fields, and the payload says which one did.

`JaNej` is a **string enum**, not a boolean: `"JA"` / `"NEJ"`. Coerce explicitly; `bool("NEJ")` is
`True` and is the most likely single-character bug in this module.

### 1.7 `not_found` lives in the body

`ApiError` is RFC 7807 — `required: [instance, status, title, type]`, plus `timestamp`, `requestId`,
`detail`. Bolagsverket's own examples:

```json
400 {"type":"about:blank","instance":"client.error","status":400,"title":"Bad Request",
     "detail":"Identitetsbeteckning har ogiltig kontrollsiffra."}
401 {"status":401,"title":"Unauthorized","detail":"Anroparen saknar giltiga autentiseringsuppgifter."}
403 {"status":403,"title":"Forbidden","detail":"Anroparen saknar behörighet till resursen."}
500 {"status":500,"title":"Internal Server Error","detail":"Ett ohanterat fel har uppstått."}
```

**`/organisationer` declares no 404.** Its documented responses are 200 / 400 / 401 / 403 / 500. An
unknown organisation comes back as **HTTP 200** with `fel.typ = "ORGANISATION_FINNS_EJ"`; the test
workbook gives the two `felBeskrivning` strings verbatim:

> *"Begärd organisation finns inte registrerad i sökbar form hos aktuell dataproducent. Observera
> att en organisation ändå kan existera och eventuellt också finnas registrerad i sökbar form hos en
> annan dataproducent trots detta fel."*
> *"Den efterfrågade informationen gick inte att hitta."*

Note the caveat Bolagsverket makes about its own answer: **absent at one dataproducent does not mean
absent at the other**. §6's `not_found` hint carries that, because it is the difference between "no
such company" and "Bolagsverket has no such company".

`VERIFY-live` (recon item 6): whether an unknown identifier yields `organisationer: []` or a
populated object with `fel.typ = ORGANISATION_FINNS_EJ` on every field. **§6 handles both**, because
the workbook names the scenario but no full response body for it appears anywhere.

### 1.8 Fixtures — built from Bolagsverket's own examples, and **none of them are live**

`UK_SPEC.md` §1.4 opened with sixteen live payloads. This file cannot. But it is much better placed
than the previous pass: Bolagsverket ships **three** complete 200-response examples and **five**
`ApiError` examples in its OpenAPI document, plus a test-company workbook with named scenarios.

> **The `organisationer-aktiebolag-svar` example is not a coherent company.** It is simultaneously
> struck off (`avregistreradOrganisation` 2023-05-05, `avregistreringsorsak: LIAV`), in bankruptcy
> (`KK`, 2024-01-26), in liquidation (`LI`, 2024-05-26) and not economically active
> (`verksamOrganisation: NEJ`) — while carrying a live address and three current names. It is a
> **shape demonstration**, not a record. Copying it wholesale into `bv_aktiebolag.json` would give
> the test suite one fixture that exercises every branch at once and none of them cleanly.
> **T26b must split it into coherent scenarios**, keeping the field names and nesting verbatim and
> changing only which optional blocks are present.

| Fixture | Built from | What it is the fixture *for* | Live? |
|---|---|---|---|
| `bv_ab_active.json` | `organisationer-aktiebolag-svar`, reduced | Healthy `AB`: no avregistrering, no ongoing procedure, `verksamOrganisation: JA`, one `FORETAGSNAMN` + one `SARSKILT_FORETAGSNAMN` + one foreign-language name. Every happy-path mapping test | No — `VERIFY-live` |
| `bv_ab_dormant.json` | same, `verksamOrganisation: NEJ` | §8's "on the register, not winding down, not economically active" branch. **No other country in this repo has it** | No |
| `bv_ab_konkurs.json` | same, `pagaende…Lista: [KK 2024-01-26]` | `KK` → `BANKRUPT` + `bankruptcy_date`, and no deadlines (ÅRL 8 kap. 7 §) | No |
| `bv_ab_kk_and_li.json` | same, `[KK, LI]` **both** | The list is plural and its precedence is `KK` > `LI` (§8). Straight from Bolagsverket's own example | No |
| `bv_ab_rekonstruktion.json` | same, `[FR 2026-02-01]` | `FR` is distress but **not** bankruptcy (§8 bucket 1) | No |
| `bv_ab_fusion_overtagande.json` | same, `[FUOT]` | The acquiring company in a merger: an ongoing procedure that must **not** make a healthy company non-active (§8 bucket 2). The false-alarm test | No |
| `bv_ab_avregistrerad.json` | same, `avregistrerad` + `LIAV` | → `DELETED`, `deregistered_at`, reason in `status_detail`. Also proves the **datetime-shaped date** parses (`"2023-05-05T00:00:00.000+00:00"`) | No |
| `bv_enskild_two.json` | **`organisationer-enskild-svar` verbatim** | The real two-business sole trader `194009272719` (§2.2). `namnskyddslopnummer` 1 and 2, `typ.kod: PERSONNUMMER`, `juridiskForm: null`, leading-whitespace `beskrivning`. **The single most important fixture in the set** | No, but it is Bolagsverket's own |
| `bv_scb_only.json` | `organisationsform: null`, `juridiskForm` present | §7's SCB fallback branch and note N5 | No |
| `bv_uppgiftskalla_fel.json` | **`organisationer-fel-fran-en-uppgiftskalla-svar` verbatim** | §1.6's partial 200: maps without raising, adds note N13, **and is not cached** | No, but it is Bolagsverket's own |
| `bv_finns_ej.json` | the workbook's `felBeskrivning` strings | `ORGANISATION_FINNS_EJ` → `not_found` (§1.7) | No — shape `VERIFY-live` |
| `bv_400.json` … `bv_500.json` | the five `ApiError` examples, verbatim | §6's status table | No, but they are Bolagsverket's own |
| `bv_token.json` | the connection guide's example | The token response (§1.2) | No |

Every fixture that is **not** copied verbatim from a Bolagsverket example carries a header key:

```json
{"_VERIFY": "SHAPE ONLY — assembled from Bolagsverket's published OpenAPI examples and code lists,
not recorded from a live call. Re-record with the curl recipe in tests/fixtures/README.md when
credentials arrive (T26d), then delete this key."}
```

A key, not a comment: JSON has no comments, and a key that must be deleted is harder to forget.
`map_entity` ignores any top-level key beginning with `_`. **T26e checks that every `_VERIFY` key is
gone before 0.3.0 ships**, and `README.md`'s country line reads "built, awaiting Bolagsverket
credentials" until it is (T26c).

### 1.9 Licence, source and attribution

Bolagsverket names **no licence** — not CC BY, not CC0, not a bespoke name. From
`vardefulladatamangder.5294.html`, verbatim:

> *"När det gäller värdefulla datamängder är de öppna för vidareutnyttjande enligt vissa regler. Du
> får använda dessa data fritt för kommersiella och icke-kommersiella syften, exempelvis för att
> skapa nya tjänster eller produkter, så länge användningen inte bryter mot lagar om skydd av
> personuppgifter eller sekretess. Data kan modifieras, bearbetas och kombineras med andra källor…"*
>
> *"Det är dock viktigt att se till att data hanteras enligt de villkor och licenser som gäller,
> vilket ibland kan inkludera krav på att ange källan och säkerställa att informationen är korrekt
> återgiven."*

Commercial reuse is explicit; attribution is "sometimes" and never pinned down. Note the one
condition Bolagsverket *does* state plainly — the permission is bounded by **personal-data and
secrecy law**, which is precisely §2.2's and D-039's subject.

> A third-party audit (`strale-io/strale`) asserts "License: CC BY 4.0 (or equivalent), confirmed in
> coverage matrix". **Nothing on Bolagsverket's pages supports that.** Do not repeat it. D-038 rules
> that we quote the regime and never invent a licence name.

Therefore:

- `Registry.license` = `"Free re-use (Bolagsverket/SCB high-value datasets, EU Open Data Directive) — the publisher names no licence"`
- `CompanyReport.source` = `"Bolagsverket (bolagsverket.se)"`, with `" — test environment"` appended
  when the module is configured against `accept2` (§6, D-037).
- `CompanyReport.source_url` = the API base URL. **`VERIFY`** — Sweden has no free public equivalent
  of `find-and-update.company-information.service.gov.uk`, and no documented per-company deep link
  was found. T26b must **not** synthesise a `näringslivsregistret` URL from a guessed pattern; an
  honest base URL beats a link that 404s at a human.
- `Registry.source_url` = `"https://gw.api.bolagsverket.se/vardefulla-datamangder/v1"`

**One registry slug for two authorities.** Roughly half the values are SCB's, but `registry` is a
routing key — D-008 keys `_REGISTRIES` by country and D-027(e) makes `CompanyReport.id` unique
within `(country, registry)` — not a provenance record. Splitting `SE` into `bolagsverket` and `scb`
would give one company two records with the same identifier, which is the exact thing D-027(e)
forbids. Provenance for the SCB half goes where D-018 and D-026(c) put provenance: in prose, naming
Statistics Sweden wherever an SCB value decided something (§2.1, §7, §8), on the strength of the
per-field `dataproducent` the payload already carries.

### 1.10 The registry class attributes

`registries/se/__init__.py`, verbatim. These eleven values are what `GET /v1/countries` and the MCP
`list_countries` tool publish (D-012 + D-017).

```python
class BolagsverketRegistry(Registry):
    country: ClassVar[str] = "SE"
    registry: ClassVar[str] = "bolagsverket"
    name: ClassVar[str] = "Bolagsverket (Sweden)"
    id_scheme: ClassVar[str] = "organisationsnummer"
    id_example: ClassVar[str] = "5560160680"
    id_description: ClassVar[str] = (
        "A Swedish organisationsnummer: ten digits, written 556016-0680, with a check "
        "digit. A sole trader is looked up by a twelve-digit personnummer instead "
        "(YYYYMMDDNNNN), and one such number can carry several registered businesses."
    )
    source_url: ClassVar[str] = "https://gw.api.bolagsverket.se/vardefulla-datamangder/v1"
    license: ClassVar[str] = (
        "Free re-use (Bolagsverket/SCB high-value datasets, EU Open Data Directive) — "
        "the publisher names no licence"
    )
    is_stub: ClassVar[bool] = False
    requires_api_key: ClassVar[bool] = True
    api_key_env: ClassVar[str] = "BOLAGSVERKET_CLIENT_ID"
```

`id_example` is **`5560160680`**, whose check digit this file verified arithmetically (§5.1 shows
the sum). `id_description` promises "a real, valid identifier an agent can use to smoke-test the
tool", so it must be a **production** company, not one of Bolagsverket's test numbers.
`VERIFY-live` **which** company it is in T26d; if it turns out to be struck off, replace it with
`5560125790` or `5560427220` — both checked, both pass, both held in reserve for exactly this. The
test-environment smoke number is `5560021361` (§17), which is a different thing and must not be
confused with this one.

`format_id` **is** overridden (§5.1.4). `id_caveat` **is** overridden (§5.1.5, D-021). `aclose`
**is** overridden (§6) — the module keeps a shared client *and* a cached bearer token.
`rules_markdown` is overridden (§13).

---

## 2. `CompanyReport` field mapping

Target: `core/models.py :: CompanyReport`. Source: `POST /organisationer`, the chosen element of
`organisationer[]` (§2.2). Anything the payload omits stays `None` — never `""`, never `0`, never a
guess (D-004, D-011). **Read `fel` before every value** (§1.6).

`Organisation` has exactly fourteen properties. Every one of them is accounted for below or in §15.

| `CompanyReport` field | Bolagsverket field | Notes |
|---|---|---|
| `country` | — | Constant `"SE"`. `registreringsland` is **not** read: its `kod` is `"SE-LAND"`, not ISO `SE` (§15) |
| `registry` | — | Constant `"bolagsverket"` |
| `id` | `organisationsidentitet.identitetsbeteckning` | Digits only, exactly as normalised by §5.1 and echoed by the register. Ten digits for an organisationsnummer, **twelve** for a personnummer/samordningsnummer |
| `id_formatted` | derived | `format_id` (§5.1.4): `556016-0680` / `19400927-2719` |
| `id_scheme` | `organisationsidentitet.typ.kod` | **Varies per record**, through §2.4's table: `ORGANISATIONSNUMMER` → `"organisationsnummer"`, `PERSONNUMMER` → `"personnummer"`, and so on. Absent → `"organisationsnummer"`. The class attribute stays constant; the *report's* field tells the caller what it is actually holding |
| `name` | `organisationsnamn.organisationsnamnLista[]` | §2.3's rule: the first item whose `organisationsnamntyp.kod == "FORETAGSNAMN"`, else the first item. `.strip()` |
| `previous_names` | — | **Always `[]`.** The list holds *concurrent* names of different types, never history (§2.3, §15) |
| `legal_form_code` | `organisationsform.kod`, else `juridiskForm.kod` | §7, D-034. Note N5 fires on the fallback |
| `legal_form` | derived, §7 | English label, ours |
| `legal_form_local` | `organisationsform.klartext`, else `juridiskForm.klartext` | The register's own Swedish words, verbatim. Unlike GB, Sweden genuinely has a separate local label |
| `limited_liability` | derived, §7 | |
| `has_board_duty` | derived, §7 | |
| `has_annual_accounts_duty` | derived, §7 | Means "must file an annual report **with Bolagsverket**", not "must keep books" |
| `status` | derived, §8 | Three orthogonal signals, precedence in §8 |
| `status_detail` | derived, §8 | One English sentence naming the signal, its code and the register's own `klartext` |
| `is_active` | derived | `status == ACTIVE`. **For SE this means "on the register and not winding down". It does not mean economically active** — §8, D-035 |
| `registered_at` | `organisationsdatum.registreringsdatum` | For a sole trader this is scoped to the chosen business (§2.2), and Bolagsverket's own example shows 1990-02-09 and 1984-12-13 for the two rows of one person |
| `founded_at` | — | **`None`.** The dataset has a registration date and nothing else. `infortHosScb` is when SCB ingested the record and is not a foundation date (§15). Do **not** copy `registered_at` here: two fields that always agree are worse than one honest absence (`UK_SPEC.md` §2's ruling for `legal_form_local`) |
| `business_register_registered_at` | — | `None`. One register |
| `bankruptcy_date` | `pagaende…Lista[kod == "KK"].fromDatum` | **Only** for code `KK`. §8 |
| `deregistered_at` | `avregistreradOrganisation.avregistreringsdatum` | §2.5's tolerant date parser: this field is **not** declared `format: date` and the examples show both `"2001-03-15"` and `"2023-05-05T00:00:00.000+00:00"` |
| `vat_registered` | — | **`None`.** §2.6 |
| `vat_registered_at` | — | `None` |
| `vat_number` | — | **`None`.** §2.6 |
| `in_business_register` | — | `None` |
| `registers` | — | `{}`. §2.6 |
| `employees` | — | `None`. **Not in the dataset at all** — a gap in the register, not in our mapping |
| `employees_reported` | — | `False` (D-011) |
| `industry_codes` | `naringsgrenOrganisation.sni[]` | `IndustryCode(code=kod, description=klartext, scheme="SNI 2007", rank=i+1)`. Five-digit codes, e.g. `{"kod":"47642","klartext":"Specialiserad butikshandel med cyklar"}`. **Descriptions arrive with the codes** — unlike GB. `VERIFY` the scheme's published name and edition |
| `sector_code` | — | `None`. **`juridiskForm` must never be put here**: it is a legal-form list, not an institutional sector classification (§7, §15) |
| `sector` | — | `None` |
| `purpose` | — | `None`. No objects clause is published |
| `activity` | `verksamhetsbeskrivning.beskrivning` | **`.strip()` is mandatory**: Bolagsverket's own sole-trader example is `"\n       HANDEL MED SKOR."` |
| `share_capital` / `share_capital_currency` | — | `None` |
| `business_address` | — | **`None`.** §3 |
| `postal_address` | `postadressOrganisation.postadress` | §3 |
| `website` / `email` / `phone` | — | `None`. Not published |
| `parent_id` | — | `None`. A Swedish `FL` (filial) has its own identifier and the dataset does not link it to a parent |
| `is_subunit` | — | **`False`, always.** §7 explains why a `filial` is not treated as a sub-unit |
| `in_group` | — | `None` |
| `last_annual_accounts_year` | — | `None`. `DEFERRED`: derivable from `/dokumentlista`, which is a second request against a 60/min budget (§5.5) |
| `published_deadlines` | — | **`[]`.** Bolagsverket publishes no per-company due date. Sweden is a compute country, like Norway and unlike Britain (D-018) |
| `confidence` | derived | `1.0` (D-005) |
| `confidence_basis` | — | `"exact identifier lookup in the Bolagsverket register"` |
| `cached` / `fetched_at` | derived | §9. UTC, timezone-aware |
| `source` / `source_url` / `license` | — | §1.9 |
| `notes` | derived | §2.1 — **this is where most of Sweden's value lands**, and there is more of it here than in either live country |

### 2.1 `notes` — the rules that fill it

`CompanyReport.notes` is copied verbatim into `DeadlineReport.notes` by `Registry.deadline_report`
(D-010), so every caveat that explains an empty or surprising deadline list must be written here, in
`registries/se/mapping.py`, and nowhere else.

| # | Condition | Note |
|---|---|---|
| N1 | `status != ACTIVE` | §8's per-status sentence |
| N2 | An ongoing procedure code is present that §8's table does not classify | "Bolagsverket records an ongoing winding-up or restructuring procedure for this organisation ({kod}: {klartext}, registered {fromDatum}) that registry-mcp does not classify. Treat this organisation as not plainly active and check with Bolagsverket before contracting with it." |
| N3 | `verksamOrganisation.kod == "NEJ"` | "Statistics Sweden does not mark this organisation as economically active (*verksam*): it holds no F-skatt, VAT or employer registration. It is on the register and is not being wound up, so `is_active` is true — but it may be dormant, and that is a different question." |
| N4 | `reklamsparr.kod == "JA"` (D-036; since R-2 landed, 2026-09-06, set **together with** `advertising_protected = True` — §2.6) | "This organisation is marked with a *reklamspärr* (advertising block) in Statistics Sweden's register: it has asked not to receive direct marketing. If you pass this record's contact details on, that marking must travel with them." |
| N5 | `legal_form_code` came from `juridiskForm` (§7) | "The legal form shown comes from Statistics Sweden's *juridisk form* code list (code {kod}), not from Bolagsverket's *organisationsform*. The two are different code lists — the Tax Agency's is coarser — and Bolagsverket holds no organisationsform for this organisation." |
| N6 | The legal form is unclassified by §7 | "The legal form {kod!r} is not classified by registry-mcp, so no filing deadlines are computed for it. This does not mean none apply — check with an accountant." (Norway's wording, D-009(a)) |
| N7 | `len(organisationer) > 1` (§2.2) | "This identifier carries {n} registered businesses: {namn} (namnskyddslöpnummer {n}, registered {date}); … . In Sweden a sole trader's organisationsnummer is the proprietor's personnummer, so one number can hold several registered business names. The one shown above is the first Bolagsverket returned; it is not necessarily the one you are looking for." |
| N8 | `organisationsidentitet.typ.kod` is `PERSONNUMMER`, `SAMORDNINGSNUMMER`, `GDNUMMER` or `DODSBO`, **or** `organisationsform.kod == "E"` (D-039) | "This is a sole trader (*enskild näringsidkare*). Its identifier is the proprietor's Swedish personnummer, and the registered name and address are often the proprietor's own name and home address — this record contains personal data about a natural person and should be handled accordingly. Bolagsverket itself treats the identifier as personal data: its API takes it in a request body rather than a URL so it does not reach access logs." |
| N9 | Any annual deadline was returned (§5.4) | The calendar-year assumption note of §5.4 |
| N10 | Configured against the test environment (§6) | "This record came from Bolagsverket's **test** environment, not from the live register. The organisation it describes may not exist." |
| N11 | Deadlines suppressed by status (§5.4) | §5.4's exemption sentence, which for `KK`/`LI` cites årsredovisningslagen 8 kap. 7 § |
| N12 | The name list holds a `SARSKILT_FORETAGSNAMN` or a foreign-language name (§2.3) | "Bolagsverket also publishes these names for this organisation: {namn} ({klartext}){, for the business described as \"{verksamhetsbeskrivningSarskiltForetagsnamn}\"}. They are current alternative or secondary registered names, not former ones." |
| N13 | Any mapped field carries `fel.typ` in `{OTILLGANGLIG_UPPGIFTSKALLA, TIMEOUT, OGILTIG_BEGARAN}` (§1.6) | "Part of this record could not be retrieved: {dataproducent} did not answer for {field list}. The fields below are what arrived, and the missing ones are absent rather than empty. This answer was not cached — ask again for a complete one." |
| N14 | `status == ACTIVE` and `legal_form_code` is classified by §7 but not in `DEADLINE_FORM_CODES` (`BRF`, `HB`, `KB`, `E`, `S`, banks/insurers, any SCB-fallback code) — added 2026-09-06, T26e fix 5 | "registry-mcp computes filing deadlines only for aktiebolag (AB) and ekonomiska föreningar (EK) — the two forms årsredovisningslagen 8 kap. 6 § names. {english} has real filing obligations that this module does not compute, because no primary source for them has been read." Distinct from N6: N6 is *unclassified*, N14 is *classified but not computed*. Honours `core/models.py`'s contract that an empty `deadlines` list is explained in `notes` |

A healthy, active, `verksam` `AB` with one name gets **exactly one** note — N9, the calendar-year
assumption. If a routine Swedish `AB` produces four, the rules are firing on absence rather than on
fact, and that is a bug: a note means something the agent must read.

Two rules about the notes themselves:

- **Every note that came from an SCB-produced field names Statistics Sweden.** The report's `source`
  says Bolagsverket; a caller acting on `verksamOrganisation` or `reklamsparr` is acting on somebody
  else's data and is entitled to know (§1.9). The payload's per-field `dataproducent` makes this
  checkable rather than assumed.
- **No note ever repeats the identifier.** N7 and N8 describe the *shape* of the identifier;
  `CompanyReport.id` carries the value once, because the caller supplied it (F1).

### 2.2 One identifier, several businesses

`OrganisationerSvar.organisationer` is an **array**, and Bolagsverket's own
`organisationer-enskild-svar` example returns **two** objects for the single identifier
`194009272719`, distinguished only by `namnskyddslopnummer` 1 and 2 — *CITY SKOR THOMAS CARLSON* and
*SKO-STALLET, THOMAS CARLSSON*. From the schema, verbatim:

> *"'Namnskyddslopnummer' is used to separate companies for organisation types that can have more
> than one company on the same 'identitetsbeteckning'. For example the legal form 'enskild
> näringsverksamhet' can have more than one company with different names on the same company
> registration number."* (`integer`, 1–999; `null` for an aktiebolag)

D-033 rules the behaviour.

**`CompanyReport.id` stays the identifier the caller supplied.** D-027(e) says that where a national
identifier is unique only within a court or a state, the country module must mint a canonical
composite and return *that* as `id`. It does not apply here, and the distinction matters: D-027(e)
addresses two **different legal persons** sharing a number, which would make `lookup` a
non-function. In Sweden the several rows are the **same natural person** — same tax status, same
liability, same personnummer. The identifier really does identify one entity. What it does not
identify is one *business name*. So no composite is minted, `lookup` stays a function, and every
cache key, `parent_id` and batch row (D-006, D-024) keeps working.

**One report, and the extra rows are stated rather than hidden.**

- The report is built from `organisationer[0]` — **the payload's own order**, not the lowest
  `namnskyddslopnummer` (nothing sources the numbering as ordinal) and not a heuristic. A rule that
  can be checked against a fixture beats a rule that has to be argued.
- **Every field comes from that same element.** Mixing one business's name with another's
  `verksamhetsbeskrivning`, address or `registreringsdatum` is the quiet wrong answer this section
  exists to prevent — and Bolagsverket's example shows the two rows really do differ in name,
  address, description, registration date and deregistration reason.
- Note N7 lists **every** business with its `namnskyddslopnummer` and registration date, and says
  out loud that the first may not be the one meant.
- `previous_names` stays `[]`.

**Declined: raising `bad_request` on ambiguity.** It was the tempting answer and it is wrong twice.
The agent cannot answer it — a `namnskyddslopnummer` is not something a supplier prints on an
invoice — so the caller would be stuck in a loop with no exit, and D-007's "the hint names the next
call" would have no next call to name. And the facts a supplier check actually turns on — does this
person exist on the register, are they struck off, are they bankrupt — are person-level and
therefore the **same on every row**. Refusing to answer a question we can answer, because a
different question is ambiguous, is worse than answering it with a caveat.

**Declined: accepting a suffixed identifier** (`"194009272719-1"`). It needs a separator convention
nobody has published, and inventing identifier syntax is what D-026(a) forbade for the EUID. If the
API ever takes `namnskyddslopnummer` as a second parameter, revisiting this is one decision entry
and an optional argument, not a migration.

### 2.3 The name list

`organisationsnamn.organisationsnamnLista[]` items are
`{namn, organisationsnamntyp: KodKlartext, registreringsdatum, verksamhetsbeskrivningSarskiltForetagsnamn}`.
The code list has four values:

```
FORETAGSNAMN;Företagsnamn            FORNAMN_FRSPRAK;Företagsnamn på främmande språk
NAMN;Namn                            SARSKILT_FORETAGSNAMN;Särskilt företagsnamn
```

**`name` ← the first item whose `organisationsnamntyp.kod == "FORETAGSNAMN"`; if none, the first
item in the list.** Everything else goes to note N12 — never to `previous_names`, because these are
*concurrent* names: a särskilt företagsnamn is a live secondary trading name and a foreign-language
name is the same company in another language. Telling an agent that a name a supplier is trading
under today is a former name would be a wrong answer on the field a payment check reads first.

**`organisationsnamntyp.kod` is an open string, not an enum.** Bolagsverket's code list says
`FORNAMN_FRSPRAK`; Bolagsverket's own aktiebolag response example says
`FORETAGSNAMN_PA_FRAMMANDE_SPRAK`. The two disagree and neither can be settled without live traffic
(`VERIFY-live`). Match `"FORETAGSNAMN"` exactly for the primary name — that spelling is consistent
across both sources — and treat every other value as "an additional name", rendering
`klartext` rather than branching on `kod`.

### 2.4 `id_scheme` per record

`organisationsidentitet.typ` is a `KodKlartext` whose codes come from the portal's code list:

| `typ.kod` | `CompanyReport.id_scheme` | Personal? |
|---|---|---|
| `ORGANISATIONSNUMMER` | `"organisationsnummer"` | no |
| `PERSONNUMMER` | `"personnummer"` | **yes** — N8 |
| `SAMORDNINGSNUMMER` | `"samordningsnummer"` | **yes** — N8 |
| `GDNUMMER` | `"GD-nummer"` | **yes** — N8 |
| `DODSBO` | `"dödsbonummer"` | **yes** — N8 (an estate of a deceased person) |
| `UTLANDSK_JURIDISK_IDENTITETSBETECKNING` | `"foreign identifier"` | no |
| *(absent, or unrecognised)* | `"organisationsnummer"` | no |

Bolagsverket's own sole-trader example carries `"typ": {"kod": "PERSONNUMMER", "klartext": "n/a"}` —
so `klartext` can be the literal string `"n/a"` and must never be rendered to a user. Read `kod`.

### 2.5 Dates — two shapes for the same field

`avregistreradOrganisation.avregistreringsdatum` is declared `"type": "string"` with **no**
`format: date`, and Bolagsverket's two examples disagree: `"2001-03-15"` (enskild) and
`"2023-05-05T00:00:00.000+00:00"` (aktiebolag). `pagaende…Lista[].fromDatum` *is* declared
`format: date` — and the aktiebolag example still sends
`"2024-01-26T00:00:00.000+00:00"`.

**One tolerant parser for every date in this module**: accept `YYYY-MM-DD` and any
`YYYY-MM-DD` followed by `T…`, taking the date part; anything else is `None`, never a raised
exception and never a guess. `registreringsdatum`, `infortHosScb` and
`organisationsnamnLista[].registreringsdatum` all go through it too — they are declared as bare
strings as well, and a register that sends two shapes for one field will send two for another.

### 2.6 VAT, and the field that would have made Sweden a VAT-verification country

VAT registration is one of the two lead use cases for this product, and Sweden's dataset comes close
to answering it without arriving.

`verksamOrganisation` is a single `JaNej` whose documented meaning is **"has F-skatt and/or VAT
and/or employer registration"**. As an OR of three facts it cannot tell us whether *this* company is
VAT-registered. The OpenAPI schema confirms there is no decomposition: the field's only properties
are `kod`, `dataproducent` and `fel`. Therefore:

- **`vat_registered` is `None`**, not `False`. `False` would assert that SCB says this company is
  not VAT-registered, which SCB has never said (D-026(b)'s three-state discipline, one field over).
- **`registers` is `{}`.** There is nothing to put in it.
- Note N3 fires when the flag is present and `"NEJ"`, carrying the real signal as prose.

**`vat_number` is `None`, always.** A Swedish VAT number is widely described as `SE` + the ten digits
+ `01`, and §5.1 strips exactly that form on input — but **recon found no primary source for the
construction**, and we would in any case be emitting a VAT number for a company we cannot see is
registered, which for a VAT-verification use case is the worst possible output. The rule goes into
`rules_markdown()` as prose so an agent that knows the missing fact can apply it — the D-016(b)
treatment of UK corporation tax — and the field stays honestly empty.

**VIES is not consulted.** Checking a VAT number against the EU VIES service is a second upstream
with its own licence and provenance: that is D-026(c)'s `SourceRef` attachment (R-5), not something
to smuggle into a Bolagsverket document.

---

### 2.6 `advertising_protected` and `euid` (R-2, authorised 2026-09-06 — T29)

D-036 put the *reklamspärr* in `notes` only because the field did not exist. It exists now
(`CORE_ROADMAP_SPEC.md` §4, D-026(b)), and Sweden is the first country to set it:

| `reklamsparr` | `advertising_protected` | N4 |
|---|---|---|
| `kod == "JA"` | `True` | yes — the note is the passer-on sentence D-026(b) requires, and `core/models.py` refuses a `True` without a note containing "direct marketing" |
| `kod == "NEJ"` | `False` — Sweden publishes the flag, so an explicit no is a real no | no |
| block absent, or blocked by `fel` | `None` | no |

`euid` stays `None`: the fourteen properties of Bolagsverket's `Organisation` schema contain nothing
EUID-shaped (D-036). `rules_markdown()` names the field (§13 item 15).

## 3. Address mapping

The dataset publishes **one** address, `postadressOrganisation.postadress`:

```json
{ "postnummer": "12345", "utdelningsadress": "Jobbstigen 2", "land": "Sverige",
  "coAdress": "C/o Annat företag", "postort": "Grönköping" }
```

Only `postnummer` is required. It maps to `CompanyReport.postal_address`, and
**`business_address` stays `None`.**

That is the opposite of both live countries — brreg's `forretningsadresse` and Companies House's
`registered_office_address` both fill `business_address` — and it is deliberate. The field is named
*postadress*, only `postnummer` is mandatory, and `coAdress` is a first-class member, so this is a
correspondence address and may be an accountant's office or a box. An agent asking "where is this
company" must get silence rather than a c/o address. Sweden's registered *säte* is a municipality
rather than a street and is **not in this dataset**.

| `Address` field | Source | Note |
|---|---|---|
| `lines` | `[coAdress, utdelningsadress]`, empties dropped, order preserved | `coAdress` first, matching `UK_SPEC.md` §3's care-of convention, so `one_line()` reads correctly |
| `postal_code` | `postnummer` | **Exactly as published.** The examples show `"12345"` and `"24131"`, unspaced; Swedes write `"123 45"`. Do not reformat either way |
| `city` | `postort` | Bolagsverket's own examples are upper-case (`"ESLÖV"`); leave the case alone |
| `municipality` | — | `None`. Not published |
| `municipality_code` | — | `None`. Not published |
| `country_code` | derived | `"SE"` when `land` is absent or casefolds to `sverige` / `sweden`; otherwise `None`. **Never guess a foreign country's ISO code from a Swedish-language name** |
| `country_name` | `land` | As published |

A missing `postadress` maps to `None`, not to an empty `Address`. Every component except
`postnummer` is individually optional, so no test may assert a non-null `city` for a real Swedish
organisation.

**A sole trader's postal address is very often a home address** — Bolagsverket's own example is
`VÄSTERG 5, 24131 ESLÖV` with a `c/o`. That is note N8's subject, D-039's reason, and part of
finding F1.

---

## 4. Search — `not_implemented`, and why that is the right answer

**There is no search operation.** The API has four paths (§1.4) and none accepts a name; a grep of
the whole OpenAPI document for a name or free-text parameter finds nothing. This is a fact about the
register, not a gap in this spec.

`search` raises:

```python
RegistryError(
    ErrorCode.NOT_IMPLEMENTED,
    "Bolagsverket's free API cannot search by company name.",
    hint=(
        "Sweden can only be looked up by identifier: call lookup_company with the ten-digit "
        "organisationsnummer (e.g. 5560160680), or the twelve-digit personnummer for a sole "
        "trader — validate_company_id will check the shape first without spending a lookup. "
        "Bolagsverket publishes the whole register as downloadable files for callers who need "
        "to search by name. search_company works for the other countries list_countries returns."
    ),
    country="SE", registry="bolagsverket",
)
```

`ErrorCode.NOT_IMPLEMENTED` (HTTP 501) is exactly right, and it is the precedent D-028(6) already
set for an operation a register cannot answer: *the country module exists but this operation is
unavailable here*. It is **not** `upstream_error` (nothing upstream is broken), **not**
`bad_request` (the caller did nothing wrong), and **not** an empty `SearchResult` — an empty result
would tell an agent that no Swedish company matches "Volvo", which is false. D-004's shapes are not
a place to express "I did not look".

This must be visible in four places besides the error, or agents will keep paying for the discovery:
`rules_markdown()` (§13), `README.md`'s country line and `KEYWORDS.md` §SE (T26c), the MCP
`search_company` docstring (T26c), and finding F3 in §0.

`ErrorCode.NOT_IMPLEMENTED` has been in the enum since T01 and — until now — was used by nothing but
the `xx/` template. Sweden is its first real caller, which is worth noting in `REVIEW.md`: the 501
path across both surfaces has never been exercised by a real country. §14 tests 108–110 exercise it.

**`search` must raise before touching the network, the token or the environment.** Two reasons, and
the second is the one that matters.

The first is cost: a 501 that first fetches an OAuth token would spend a request from a 60/min
budget to answer a question that has no upstream at all.

The second is the **D-031 connector fan-out**, which was checked against the implementation rather
than assumed. `mcp/connector.py::_name_search_rows` (`:314-330`) fans `search` out across
`list_registries()` and wraps each call in `except RegistryError: return []` — *"A `RegistryError`
from one country — e.g. GB with no `COMPANIES_HOUSE_API_KEY` — drops that country and never raises
(D-031(c))"*. That `except` is on the base class, not on a code, so **`not_implemented` is caught
exactly like every other `RegistryError`**: Sweden drops out of the merged results and Norway's and
Britain's hits are returned unchanged. The ChatGPT `search` alias therefore needs **no change
outside `registries/se/`, and none is requested** — this was verified, not inferred, and §14
test 110 pins it so a later narrowing of that `except` to specific codes would fail a test rather
than silently empty the connector.

The same holds for `_identifier_rows` (`:296-311`): it calls `Registry.validate` first, which for a
Swedish ten- or twelve-digit query says `valid: true` and produces one `lookup` — the operation
Sweden *can* serve. A UK or Norwegian identifier fails SE's shape check and costs nothing.

One consequence worth stating so it is not read as a bug: with SE registered, every connector
`search` makes one SE call that raises immediately. It costs no socket, no token and no bucket
token, and it is the price of the fan-out being country-blind — which is what D-001 requires of it.

---

## 5. Rules — `registries/se/rules.py`

### 5.1 Identifier validation

The API's own regex is primary and exact:

```json
"identitetsbeteckning": {
  "pattern": "^(19|20)?\\d{2}(0[1-9]|1[0-2])((0|6)[1-9]|(1|2|7|8)[0-9]|(3|9)[0|1])\\d{4}$|^\\d{6}\\d{4}$|^302\\d{8}$",
  "type": "string", "example": "5299999994" }
```

and the schema spells out the four widths:

> *"'Organisationsnummer' is represented by 10 digits, 'personnummer' is represented by 12 digits
> (YYYYMMDDXXXX), 'samordningsnummer' is represented by 12 digits (YYYYMMDDXXXX, where 'DD' is the
> persons birthday + 60) and 'GD-nummer' is represented by 10 digits (302XXXXXXX)."*

**The wire format is digits only, no hyphen** — every example: `5299999994`, `194009272719`.

**Normalisation, in order** (D-032):

1. Strip all whitespace (including the non-breaking space ` `), `.`, `-`, `/` and `+`.
   (`+` because a personnummer for someone over 100 is written with `+` in place of `-`.)
2. Upper-case.
3. If the result matches `^SE\d{12}$` and its last two digits are `01`, strip the `SE` prefix and
   the `01` suffix: `SE556016068001` → `5560160680`. That is the Swedish VAT form and it contains
   the organisationsnummer exactly. **Any other `SE…` string is not silently stripped** — it goes to
   the shape check and fails with §5.1.2's VAT hint.
4. Accept iff the result is all ASCII digits and matches one of the three widths the API's own
   schema names: **ten digits** (organisationsnummer, or a GD-nummer beginning `302`), or **twelve
   digits** in the `YYYYMMDDNNNN` form (personnummer, or a samordningsnummer whose `DD` is the
   birth day + 60). Nothing else.

> **Do not strip the century from a twelve-digit number.** An earlier draft of this spec did, on the
> reasoning that a Swedish personnummer is "really" ten digits. The API's own schema and its own
> sole-trader example (`194009272719`) settle it: **twelve digits is the wire form for a
> personnummer**, and truncating to ten would send a request Bolagsverket's regex rejects.

#### 5.1.1 The check digit — **not enforced locally**, and why

**A check digit exists and Bolagsverket enforces it server-side.** Its documented 400 is
`"Identitetsbeteckning har ogiltig kontrollsiffra."` / *"Company registration number has an invalid
check digit."* That much is primary and it is the only primary fact available.

**The algorithm is unsourced.** Recon read Skatteverket's own `organisationsnummer` page — the one
Bolagsverket's own code list cites for legal forms — and it describes neither the digit count nor
the check digit; `lagen.nu/1974:174` and `/1974:661` returned empty bodies.

**Ruling (D-032): `validate_id` checks shape only. It never rejects a number on a check digit.**
The register is the authority on its own check digit, and it says so in one round trip; we are not,
and an `invalid_id` raised on an unsourced rule is the failure D-021 was written about — *"we told
an agent a real company was invalid because our table was a year old"*. `validate_id` is called by
`lookup` before every request (§6), so a wrong local rule would not merely mislabel a validation, it
would make a real company **unfetchable**.

That is not a hypothetical here. The rule the earlier library file proposed — modulus 10 (Luhn),
leftmost digit doubled over the nine digits preceding the check digit — was computed against every
Swedish identifier this project holds:

| Set | n | Luhn, leftmost doubled | The only plausible alternative (doubling from the right) |
|---|---|---|---|
| Test-workbook **scenario** numbers (`5560021361`, `9124001992`, `7164099017`, `7020008350`, `5567223705`, `5561890038`, `5562820745`, `5560986878`, `198101032384`, `198101052382`, `193403223328`) | 11 | 11 pass | 1 |
| Bolagsverket's own OpenAPI examples (`5299999994`, `194009272719`) | 2 | 2 pass | 0 |
| Well-known production numbers used in this file (`5560160680`, `5560125790`, `5560427220`) | 3 | 3 pass | 0 |
| Further **permitted** numbers from the test allowlist (`5560000002`, `7140000001`, `9160000001`, `198210300002`) | 4 | **0 pass** | 0 |

Sixteen agreements is not chance and the alternative weighting is refuted — but **four identifiers
Bolagsverket's own test environment permits fail the rule**, and that is exactly the counter-example
a local rejection cannot survive. They are probably hand-made allowlist padding (`…0000002`,
`…0000001`, `…300002`) rather than numbers with a meaningful check digit; "probably" is not the
standard D-009 sets for a rule that decides whether a company can be looked up at all.

**What we do instead, and it loses almost nothing:**

1. `validate_id` enforces shape — which for Sweden is substantive, not a length test: it separates
   nine digits (Norway, §5.1.3) from ten from twelve, strips and recognises the VAT form, and
   rejects letters, wrong widths and impossible date parts in the twelve-digit form.
2. The modulus-10 result is computed and reported as a **caveat on a valid result** (§5.1.5),
   D-021's exact mechanism: widen what we say, do not narrow what we accept. `valid` stays `true`,
   `normalized` stays populated, and the caller gets a column it can filter — which is D-021's own
   requesting use case, a spreadsheet of supplier numbers.
3. The upstream `400` maps to `invalid_id` (§6), so the *verdict* an agent finally receives is the
   register's own, one call later, and is correct by construction.

**The experiment that would settle it, to be run in T26d, written down now so it is not forgotten:**
call the **test** environment with `5560000002`. If it returns an organisation, the modulus-10 rule
is refuted for a real permitted identifier and even the caveat comes out. If it returns
`400 "ogiltig kontrollsiffra"`, the rule is confirmed by the register's own behaviour and a later
decision may promote it into `validate_id`. Either way this section is rewritten from evidence
rather than from argument.

**No smoke test, fixture or `id_example` may rely on one of the four failing numbers.** T26d's
test-environment smoke number is `5560021361`; production's is `5560160680`.

#### 5.1.2 Errors

```python
RegistryError(
    ErrorCode.INVALID_ID,
    f"{raw!r} is not a valid Swedish identitetsbeteckning.",
    hint=(
        "A Swedish organisationsnummer is ten digits with a check digit, written 556016-0680 "
        "or 5560160680. A sole trader is looked up by a twelve-digit personnummer "
        "(YYYYMMDDNNNN). Bolagsverket's free API cannot search by name."
    ),
    country="SE", registry="bolagsverket",
)
```

Four specialised hints, each replacing the generic one. Every one is a mistake a caller will
actually make, and D-007 makes the hint the product:

| Input shape | Hint |
|---|---|
| Exactly **nine** digits | "That is nine digits, which is the length of a **Norwegian** organisasjonsnummer, not a Swedish one. Swedish numbers are ten digits (e.g. 5560160680). If the company is Norwegian, call the same tool with country 'NO'." |
| `SE` + 12 digits not ending `01`, or `SE` + anything else | "That looks like a Swedish VAT number — SE, then the ten-digit organisationsnummer, then 01. Call this tool with the ten middle digits: for SE556016068001 that is 5560160680." |
| Eleven digits, or twelve digits whose month or day is impossible | "A Swedish personnummer must be given in full, with the century and a real date: 19400927-2719, not 400927-2719. Bolagsverket's API takes twelve digits for a person and ten for an organisation." |

There is deliberately **no** "bad check digit" row: §5.1.1 rules that the check digit is not enforced
locally, so a well-shaped number with a wrong check digit is `valid: true` with a caveat (§5.1.5) and
is rejected — correctly, and in the register's own words — by the upstream 400 that §6 maps to
`invalid_id`.

The last row earns its place because the ten-digit personnummer is how Swedes write it and the
twelve-digit form is what the API needs; a bare "ten digits are fine" hint would send the caller
round the loop again.

#### 5.1.3 Nine digits is Norway

Both countries call the identifier an *organisasjons-/organisationsnummer* and this server answers
for both. A nine-digit input for `SE` and a ten-digit input for `NO` are the most likely
cross-country mistakes the product can produce, and both hints name the other country explicitly.
This is not a country alias (D-015 forbids those); it is an error message that names the correct
next call, which is what D-007 requires of every hint.

#### 5.1.4 `format_id`

`5560160680` → `"556016-0680"` (six, hyphen, four). `194009272719` → `"19400927-2719"` (eight,
hyphen, four). Anything else → `None`.

`VERIFY` — the hyphen convention is universal in Swedish practice but recon found it in **no primary
source**, and the API itself only ever uses unhyphenated digits. It is cosmetic, it is clearly
labelled as "how a local would write it", and `ValidationResult.formatted` is documented as exactly
that; if a source is ever found saying otherwise, this is a three-line change.

#### 5.1.5 `id_caveat` — D-021 applied to Sweden

`Registry.id_caveat(id)` appends a sentence to a **valid** `ValidationResult.reason`, never to
`hint`, which stays `None` on success (D-013, D-021). Two sentences, in this order, each only when
it applies:

1. **Twelve digits** → "Twelve digits is a personnummer or samordningsnummer, which Sweden uses as a
   sole trader's identifier. It identifies a natural person, and one such number can carry several
   registered businesses; only lookup_company can say which."
2. **The modulus-10 check fails** (§5.1.1) → "Note that this number does not satisfy the modulus-10
   check digit that Swedish identifiers are generally described as carrying. registry-mcp has not
   been able to confirm that rule against a primary source, as of 2026-09, so the number is not
   rejected here — but Bolagsverket validates a check digit server-side and may answer
   'Identitetsbeteckning har ogiltig kontrollsiffra'. Check the digits before relying on it."
   **Nothing is said when the check passes**: a passing unverified check adds no information, and
   advertising it would lend our own rule an authority it has not earned.

The as-of date is mandatory (D-021), so a reader can tell a stale rule from a bad number. `valid`
stays `true` in both branches, and `hint` stays `None`.

**There is deliberately no first-digit group caveat**, and Sweden is where GB's version of this idea
stops working. `UK_SPEC.md` §5.1.2's prefix table earns its caveat because it is documented and
because every UK company number has a prefix. Sweden's leading-digit groups (`5` aktiebolag, `2`
state and municipal, `8` ideell förening, `9` handelsbolag) were found in **no primary source**, the
list is incomplete, and — decisively — **a sole trader's leading digit is a birth-year digit and
encodes nothing at all**. A caveat built on it would be unsourced prose that is simply false for a
large class of real identifiers. It is not shipped, in either direction.

### 5.2 Public holidays

**`registries/se/holidays.py` must not be written**, unless §5.3 resolves the other way. Sweden's
*röda dagar* are easy to compute, which is precisely why the prohibition has to be explicit: a
holiday table exists to serve a roll-forward rule, §5.3 has no sourced roll-forward rule, so the
table would have no caller — and an unused holiday table is an invitation to invent one.

### 5.3 Roll-forward — **not applied**

D-022(b) makes roll-forward a per-deadline fact decided from that deadline's own source, and
D-022(c) says that where the source is silent the date does not move. Applied to Sweden:

- **Nothing in årsredovisningslagen 8 kap. mentions weekends or public holidays.** Recon read the
  chapter.
- **No Bolagsverket page stating a roll-forward rule for filing deadlines was found.**
- Sweden has a general statute for computing statutory time — **lagen (1930:173) om beräkning av
  lagstadgad tid** — but it was **not read**, and its application to ÅRL 8 kap. 6 § was not
  established. `VERIFY`.

**Therefore every Swedish `Deadline` has `statutory_date == due_date` and `rolled_forward is
False`, `core/rules/common.py::roll_forward` is never called, and `applies_because` says the date
does not move.** The direction of the error decides the default: telling a caller to file *earlier*
than the law requires is never unlawful, while telling them to file later can be — the exact hazard
D-022 was written about, where a rolled Norwegian `annual_accounts` landed on a date the late fee
was already running. A förseningsavgift under ÅRL 8 kap. 6 § is 7 500 kr for a private aktiebolag
and 15 000 kr for a public one, so the cost of the wrong direction is a number.

If a later pass delivers both the statute's text and evidence that it reaches ÅRL 8:6, this section
is rewritten, `holidays.py` is written, and `annual_accounts` gains a roll-forward with the citation
in `applies_because`. Forty lines, and not to be done on an inference.

### 5.4 Filing deadlines — implement these two

Computed from `report` plus the `today` parameter, never from the clock. Sweden is a **compute
country**: Bolagsverket publishes no per-company due date, so `report.published_deadlines` is empty
and rung 1 of each ladder is unreachable today. It is implemented anyway — three lines — so that the
day a due date does appear the module prefers it without a redesign (D-016(a), D-018).

| `kind` | `local_name` | `authority` | Recurrence | Applies to (§7) |
|---|---|---|---|---|
| `general_meeting` | Ordinarie bolagsstämma (årsstämma) | Company shareholders (no external filing) | annual | `AB` |
| `annual_accounts` | Årsredovisning | Bolagsverket | annual | `AB`, `EK` |

Both slugs already exist in `registries/no/rules.py` and mean the same thing there. That is
deliberate: an agent comparing a Norwegian and a Swedish supplier should be able to compare
`kind == "annual_accounts"` without a translation table.

#### 5.4.1 The statutes — and the correction that matters

**Aktiebolagslagen (2005:551) 7 kap. 10 §** — Lag (2024:350), from <https://lagen.nu/2005:551>,
fetched 2026-09-05:

> *"Ordinarie bolagsstämma. 10 § Inom sex månader från utgången av varje räkenskapsår ska
> aktieägarna hålla en ordinarie bolagsstämma där styrelsen ska lägga fram årsredovisningen och
> revisionsberättelsen samt, i ett moderbolag som är skyldigt att upprätta koncernredovisning,
> koncernredovisningen och koncernrevisionsberättelsen (årsstämma)."*

> **Årsredovisningslagen 8 kap. 3 § is *not* the seven-month rule**, and the research library said
> it was. ÅRL (1995:1554) 8 kap. 3 §, verbatim from <https://lagen.nu/1995:1554>, fetched
> 2026-09-05, for an aktiebolag:
>
> *"1. Aktiebolag — Bestyrkta kopior av handlingarna ska ha kommit in till registreringsmyndigheten
> **inom en månad efter det att bolagsstämman fastställde balansräkningen och
> resultaträkningen**."*
>
> That is **one month after an event date the free API does not publish**. Seven months is a
> backstop that lives somewhere else entirely.

**Årsredovisningslagen 8 kap. 5–6 §§** — Lag (2024:1115), verbatim, is where seven months and the
fees actually live:

> *"5 § Om ett aktiebolag, en ekonomisk förening eller en stiftelse inte ger in årsredovisning,
> revisionsberättelse eller granskningsberättelse enligt 3 § … ska bolaget, föreningen eller
> stiftelsen betala förseningsavgift till staten enligt 6 och 6 a §§."*
>
> *"6 § Ett aktiebolag och en ekonomisk förening ska betala en förseningsavgift om de handlingar som
> anges i 5 § inte har kommit in till registreringsmyndigheten **inom sju månader från
> räkenskapsårets utgång**. Om bolaget eller föreningen inom denna tid har kommit in med anmälan
> enligt 7 kap. 14 § tredje stycket aktiebolagslagen … och gett in en skriftlig försäkran från
> bolagets eller föreningens revisor om att revisionsberättelsen lämnats till styrelsen, ska dock
> bolaget eller föreningen betala förseningsavgift först om handlingarna inte har kommit in **inom
> nio månader** från räkenskapsårets utgång. En stiftelse … **inom sex månader** … Förseningsavgiften
> ska uppgå till **7 500 kronor för privata aktiebolag, ekonomiska föreningar och stiftelser** och
> till **15 000 kronor för publika aktiebolag**."*

**So the derivation is a three-step ladder and `applies_because` must say all three steps**, per
D-022(a) — cite the provision that contains the rule:

1. **ABL 7 kap. 10 §** — the AGM within six months of the financial year end. *Computable.*
2. **ÅRL 8 kap. 3 § p.1** — file within one month of the AGM's adoption. *Not computable: the
   adoption date is not published.*
3. **ÅRL 8 kap. 6 §** — seven months from the financial year end is where the förseningsavgift
   begins. *Computable, and it is what a user means by "the filing deadline".*

**ÅRL 8 kap. 7 § is a derivation input, not a footnote:**

> *"7 § Om ett beslut om att aktiebolaget, den ekonomiska föreningen eller stiftelsen har försatts i
> **konkurs** har registrerats, får beslut om förseningsavgift inte meddelas. Om ett beslut om att
> bolaget … har gått i **likvidation** har registrerats, får beslut om förseningsavgift inte
> meddelas när det gäller redovisning för tiden före likvidationsbeslutet."*

That is a **statutory** basis for suppressing `annual_accounts` on a `KK` or `LI` company —
stronger than Britain's, where the same suppression rests on our own caution (D-016). Sweden's
exemption note cites it.

#### 5.4.2 `general_meeting` — derivation ladder, first hit wins

| # | Source | `applies_because` |
|---|---|---|
| 1 | a `published_deadlines` entry `kind == "general_meeting"` with a `due_date` | "Bolagsverket publishes this date for the company itself; it is the register's own figure, not a calculation." *(unreachable today)* |
| 2 | the calendar-year assumption → **30 June** | "An aktiebolag must hold its ordinary general meeting (årsstämma) within six months of the end of each financial year (aktiebolagslagen 7 kap. 10 §). Assumes a financial year ending 31 December — Bolagsverket's free dataset does not publish the financial year. Six months is an outer limit and there is no filing office to be closed, so this date does not move off a weekend or a public holiday." |
| 3 | nothing | no deadline, plus a note |

`mandatory=True`, `recurrence=annual`, `period_label` = the preceding calendar year,
`period_start`/`period_end` = 1 January / 31 December of it, `statutory_date == due_date`,
`rolled_forward=False`. `authority` is literally `"Company shareholders (no external filing)"`,
matching Norway's and for the same reason. `source_url` = `https://lagen.nu/2005:551`.

#### 5.4.3 `annual_accounts` — derivation ladder, first hit wins

| # | Source | `applies_because` |
|---|---|---|
| 1 | a `published_deadlines` entry `kind == "annual_accounts"` with a `due_date` | "Bolagsverket publishes this date for the company itself; it is the register's own figure, not a calculation." *(unreachable today)* |
| 2 | the calendar-year assumption → **31 July** | "An {aktiebolag / ekonomisk förening} must file its annual report with Bolagsverket within one month of the general meeting that adopts it (årsredovisningslagen 8 kap. 3 §), and that meeting must be held within six months of the financial year end (aktiebolagslagen 7 kap. 10 §). Bolagsverket does not publish the meeting date, so this is the outer limit instead: a late fee of 7 500 kr (15 000 kr for a public company) starts if the documents have not arrived within seven months of the financial year end (årsredovisningslagen 8 kap. 6 §). **This company's own deadline may be earlier if its general meeting was held earlier.** Assumes a financial year ending 31 December, which the free dataset does not publish. The date does not move off a weekend or a public holiday." |
| 3 | nothing | no deadline, plus a note |

`mandatory=True`, `recurrence=annual`, same period fields, `statutory_date == due_date`,
`rolled_forward=False`. `source_url` = `https://lagen.nu/1995:1554`.

**The "may be earlier" clause is not padding.** It is the one sentence that keeps this deadline from
being wrong in the dangerous direction, and it is Sweden's analogue of `UK_SPEC.md` §5.4.1's
insistence that the register's own figure beats ours.

**Not computed, and stated in `applies_because` only as a possibility:** the **nine-month** variant
of 8 kap. 6 §, which applies when the company filed a 7 kap. 14 § notice *and* an auditor's written
assurance within the seven months. Neither fact is published. Mentioning it costs one clause and
prevents an agent from reporting a company as overdue when it is not.

#### 5.4.4 The calendar-year assumption note (N9)

Fires once, on `CompanyReport.notes`, whenever any annual deadline is returned (D-010, D-023):

> "Filing deadlines are computed assuming a financial year ending 31 December. Bolagsverket's free
> dataset does not publish a company's financial year, and a Swedish financial year need not be the
> calendar year. If it is not, both dates move by the same number of months — a 30 June year end
> gives 31 December for the annual general meeting and 31 January for the filing. The filing date is
> also an outer limit rather than this company's own: årsredovisningslagen 8 kap. 3 § requires
> filing within one month of the general meeting that adopts the accounts, so a company whose
> meeting was earlier must file earlier. Årsredovisningslagen 8 kap. 6 § allows nine months instead
> of seven for a company that has filed the notice and auditor's assurance it describes; the free
> dataset does not say which companies those are."

`VERIFY` — an earlier draft of this note enumerated the lawful *brutna räkenskapsår* (30 April,
30 June, 31 August) on the strength of bokföringslagen 3 kap. **That enumeration is not sourced**
and has been removed; one worked example is kept because the arithmetic is the reader's own. If the
provision is read later, the enumeration can come back and this note becomes materially more useful
than Norway's.

#### 5.4.5 Rules that apply to every Swedish deadline

- `days_until = (due_date - today).days`. Negative is a valid, expected result.
- Only the **next** occurrence of each `kind`; one `Deadline` per `kind`.
- Sorted by `due_date` ascending, then by `kind`.
- `statutory_date == due_date`, `rolled_forward is False` (§5.3).
- `country == "SE"`, `registry == "bolagsverket"`, non-empty `applies_because`, `source_url` never
  the API URL.
- **Deadlines are emitted only when `status is CompanyStatus.ACTIVE`.** Every other status returns
  `[]` plus one note (N11): "This organisation's status with Bolagsverket is '{status}', so no
  filing deadlines are given." — and for `BANKRUPT` or `UNDER_LIQUIDATION` arising from a registered
  `KK` or `LI`, the sentence continues: "Once bankruptcy is registered, årsredovisningslagen 8 kap.
  7 § forbids Bolagsverket from imposing a late-filing fee at all; once liquidation is registered,
  no fee may be imposed for the period before the liquidation decision. What must still be filed is
  decided by the bankruptcy trustee or the liquidator."
- **An unclassified legal form gets no deadlines at all** (D-009(a)), plus note N6.
- **`verksamOrganisation` never suppresses a deadline.** A dormant `AB` still owes an annual report;
  that is one of the commonest ways a Swedish company acquires a förseningsavgift, and suppressing
  the deadline because SCB holds no tax registration would be this module's most harmful possible
  output.

### 5.5 `DEFERRED` and `VERIFY` — do not implement in T26b

- **Inkomstdeklaration 2 (corporate tax return) — omitted.** Skatteverket's dates are keyed to the
  financial-year-end month in four buckets and differ again by filing channel. We have neither, and
  the authority is Skatteverket rather than Bolagsverket. Recon did not research it, deliberately,
  because the dataset makes it unusable. If it is sourced later it goes into `rules_markdown()` as
  **prose** — the D-016(b) treatment of UK corporation tax — and the module still emits no date.
- **Moms (VAT returns) — omitted.** Period and due date both follow from a registration the dataset
  does not expose (§2.6). Prose only.
- **Arbetsgivardeklaration (AGI) — omitted.** Needs to know the entity is an employer; `verksam` is
  an OR (§2.6). Prose only.
- **`annual_accounts` for forms other than `AB` and `EK`.** ÅRL 8 kap. 3 § p.3 gives *handelsbolag
  in which one or more legal persons are partners* six months from the year end, and p.4 gives
  *stiftelser* six months — but whether a legal person is a partner is not in the dataset, and the
  scope of the stiftelse rule was not read. `BRF`, `KHF`, `SF` and `BF` are ekonomiska föreningar in
  substance and 8 kap. 6 § very likely reaches them; **that is a likelihood, not a source**, and
  D-009 forbids shipping it. Confirming it is one read of bostadsrättslagen and lagen om ekonomiska
  föreningar and would add the most common Swedish form on the register. `VERIFY` — the highest-value
  follow-up in this file.
- **`general_meeting` for `EK`.** The föreningsstämma is in lagen om ekonomiska föreningar 6 kap.,
  not in ABL 7 kap. 10 §. Not sourced, not implemented.
- **Förseningsavgift escalation.** The first fee is quoted in `applies_because` because it is what
  makes the seven-month date operative. The escalation — ÅRL 8 kap. 6 a §: a further 7 500 / 15 000
  kr two months after a notice, then 15 000 / 30 000 kr two months after that, to a maximum of
  30 000 kr for a private and 60 000 kr for a public aktiebolag — belongs in `rules_markdown()`
  prose, not in a `Deadline`.
- **`/dokumentlista` and `/dokument`.** Filed annual reports, and the natural source of
  `last_annual_accounts_year`. A second request per lookup against a 60/min budget, plus a zip to
  parse. `DEFERRED`. The workbook's real payload shape is recorded in the recon file when it is
  picked up.
- **Beneficial owners.** A separate `VerkligaHuvudmän v1` API exists on the same portal and is
  `PUBLISHED`; its access conditions were not investigated. `DEFERRED`, and represented as an
  absence with a reason, never as an empty list implying none exist (`research/AGENT_PRIMER.md`
  §2.9).
- **The paid API.** Cases, more document types, change notifications, behind a signed agreement and
  a fee whose krona figures remain unverified. Out of scope; do not quote a third party's numbers.
- **SNI → NACE.** D-025's `nace_code` is R-7 and is not in this task. SNI is NACE-derived, so
  Sweden will be a beneficiary; `IndustryCode.scheme` must say `"SNI 2007"` and not `"NACE"`, which
  is the mistake D-025(e) is making Norway correct.

---

## 6. Client behaviour — `registries/se/client.py`

- **Base URL:** `https://gw.api.bolagsverket.se/vardefulla-datamangder/v1` (production) or
  `https://gw-accept2.api.bolagsverket.se/vardefulla-datamangder/v1` (test).
- **Token URL:** `https://portal.api.bolagsverket.se/oauth2/token` (production) or
  `https://portal-accept2.api.bolagsverket.se/oauth2/token` (test). **`portal.`, not `gw.`** (§1.1).
- **Environment selection:** `BOLAGSVERKET_ENVIRONMENT` ∈ `{"production", "test"}`, **default
  `production`**, read at call time. It selects the base URL *and* the token URL **together**, as
  one pair, so it is structurally impossible to send production credentials to the test host or the
  reverse (D-037). An unrecognised value raises `RegistryError(upstream_error)` naming the two legal
  values — never a silent fall back to production, which would be the one failure mode this variable
  exists to prevent.
- **Credentials:** `BOLAGSVERKET_CLIENT_ID` and `BOLAGSVERKET_CLIENT_SECRET`, both
  `os.environ.get(..., "").strip()`, read **inside** the request path. Either empty → the
  no-credentials error below, **before any socket is opened**.
- **Timeout:** 5 s total per attempt (`httpx.Timeout(5.0)`), the same as both live countries. Applies
  to the token request as well.
- **Retry:** exactly one, only on a timeout or a 5xx, never on a 4xx. 250 ms backoff. A retry spends
  a second bucket token.
- **User-Agent:** the `registries/no/client.py` contract, unchanged:
  `registry-mcp/{__version__} (+https://github.com/foretak/registry-mcp; {contact})` from
  `REGISTRY_MCP_CONTACT_EMAIL`.
- **Headers:** `Accept: application/json`, `Content-Type: application/json` on the POST,
  `Authorization: Bearer {token}`, and **`X-Request-Id: {uuid4}` — a fresh one per attempt** (§1.4).
  It is the only handle Bolagsverket support can use, so it is logged at DEBUG (§11) and never
  reused between requests.
- **Connection reuse:** one module-level `httpx.AsyncClient`, created lazily, closed by an
  `aclose()` that `BolagsverketRegistry.aclose` delegates to (D-014). Mandatory, not optional.
- **Rate limiter:** an in-process async token bucket, **capacity 60, refill 1.0 token/second**
  (§1.5), one token per HTTP attempt **including the token request**. `acquire()` waits at most
  2.0 s and then raises `RegistryError(RATE_LIMITED)`. Unlike Britain's, this bucket can be reached
  by legitimate traffic, so its wait is a feature; unlike Britain's, it must never be raised by
  configuration.
- **Never log a credential.** Not at DEBUG, not in a `repr`, not in `details`, and **not the bearer
  token either** — a JWT is a credential for its lifetime. `api_key_env` publishes a variable's
  *name*; nothing publishes a value (D-017, D-030(d)).

### 6.1 The token — cached in memory, with a refresh margin

```
POST {token_url}
Content-Type: application/x-www-form-urlencoded
grant_type=client_credentials&client_id=…&client_secret=…&scope=vardefulla-datamangder:read vardefulla-datamangder:ping
```

- **Both scopes in one request**, space-separated, exactly as the connection guide shows. The guide
  warns that a scope missing from the token makes every later resource call fail — a failure that
  would surface as a 403 on the *data* call and be very hard to trace back to the token request.
- The response's `access_token` and `expires_in` are cached in a module-level variable. **Read
  `expires_in` from the response; never hard-code 3600** — that number appears only in a
  documentation example (`VERIFY-live`).
- **Refresh margin: 60 seconds.** A token is considered expired 60 s before its stated expiry, so a
  request never starts with a token that expires mid-flight.
- If the token endpoint returns **429 → `RegistryError(rate_limited)`** (D-019), before any other 4xx
  branch — the token endpoint sits behind the same WSO2 gateway and its throttling policy, and
  calling a 429 "no credentials" would send an operator to re-check secrets that are fine (T26e fix
  12, 2026-09-06). Any **other** 4xx → `RegistryError(upstream_error)` with the no-credentials hint
  (the credentials are present but wrong). If it returns 5xx or times out → one retry, then
  `upstream_error` / `upstream_timeout`. A 200 whose body is not JSON or lacks `access_token` →
  `upstream_error`, never a bare `KeyError` (fix 13; the same wrapping applies to the data call).
- A **401 or 403 on a data call invalidates the cached token exactly once** and the request is
  retried with a fresh one; a second 401/403 raises. Without this, a token revoked or expired early
  poisons the process until restart. This is the one retry-on-4xx in the module and it is bounded to
  one per call.
- `aclose()` clears the cached token as well as closing the client. A cached bearer token surviving
  an `aclose()` is a credential leaking past the shutdown that was supposed to end it.

### 6.2 The lookup call

```
POST {base}/organisationer
{"identitetsbeteckning": "5560160680"}
```

**Never a GET, never a query parameter** (§1.4). The identifier is personal data for a large class
of Swedish entities and Bolagsverket keeps it out of URLs deliberately; a "faster" GET would undo
that and would put a personnummer into every proxy log between us and them.

Request construction lives in **exactly one function**, so that a correction is a one-line change.

### 6.3 Status handling

| Upstream | Result |
|---|---|
| 200, `organisationer` non-empty, no blocking `fel` | Map and return (§2) |
| 200, `organisationer` empty **or** `fel.typ == "ORGANISATION_FINNS_EJ"` on the identity-bearing fields | `RegistryError(not_found)` — §1.7. Cached as a negative for 1 h (D-006). **"Identity-bearing" means exactly the three Bolagsverket-sourced fields `organisationsnamn`, `organisationsform`, `organisationsdatum`** (T26e fix 4, 2026-09-06). The same code on an SCB-sourced field (`juridiskForm`, `verksamOrganisation`, `reklamsparr`) means only that Statistics Sweden lacks the entity — the workbook's own `5567223705` case — and is **not** `not_found`; it maps like any blocked field |
| 200, a *status-bearing* field (`avregistreradOrganisation`, `avregistreringsorsak`, `pagaende…Lista`) carries a blocking `fel.typ` | Map, `status = UNKNOWN`, `is_active = False` — §8 rung 0. N13 fires. Not cached (§9) |
| 200, some field carries `fel.typ` in `{OTILLGANGLIG_UPPGIFTSKALLA, TIMEOUT, OGILTIG_BEGARAN}` | Map what arrived, append note N13, **do not write the cache** (§9) |
| 400 | `RegistryError(invalid_id)` — the only documented 400 for `/organisationer` is a malformed identitetsbeteckning, and the register is the authority on its own check digit (§5.1.1) |
| 401 | `RegistryError(upstream_error)`, after the one token-refresh retry of §6.1. Hint names **both** env vars |
| 403 | Same handling. A 403 is more likely a **missing scope** than a bad secret, so its hint says so — that is the failure the connection guide warns about and it is invisible from the data call alone |
| 5xx (after the retry) | `RegistryError(upstream_error)` |
| timeout (after the retry) | `RegistryError(upstream_timeout)` |
| 429 | `RegistryError(rate_limited)` (D-019). **No 429 is declared anywhere in the OpenAPI document** (`VERIFY-live`), so this branch is written from the 60/min sentence rather than from a documented response; handle it regardless |
| anything else | `RegistryError(upstream_error)` naming the status |

**Do not echo upstream error bodies into `message`, `hint` or `details`.** `ApiError` carries
`detail` (Swedish prose), `timestamp` (which would make our output non-deterministic) and
`requestId` (Bolagsverket's own support handle). The GB ruling applies unchanged: `details` is
documented as minimal and ours (D-007), not a pass-through. The one place the register's own words
appear is the §5.1.5 caveat and the `invalid_id` hint, where `"Identitetsbeteckning har ogiltig
kontrollsiffra"` is quoted as *what Bolagsverket will say*, not forwarded from a response.

### 6.4 The error texts

**No credentials:**

```python
RegistryError(
    ErrorCode.UPSTREAM_ERROR,
    "This deployment has no Bolagsverket credentials, so Swedish company data cannot be fetched.",
    hint=(
        "Call list_countries to see which countries can answer right now. If you run this "
        "server yourself, set BOTH BOLAGSVERKET_CLIENT_ID and BOLAGSVERKET_CLIENT_SECRET and "
        "restart it — Bolagsverket's API is free and needs no contract; request credentials at "
        "https://bolagsverket.se/apierochoppnadata/hamtaforetagsinformation/vardefulladatamangder"
        "/kundanmalantillapiforvardefulladatamangder.5528.html with an email address and a mobile "
        "number."
    ),
    country="SE", registry="bolagsverket",
)
```

`upstream_error` (502) rather than `not_implemented` (501): the module is implemented, the
deployment is unconfigured. And rather than `internal_error`, because it is a choice the operator
made. The hint carries both branches because the agent does not know which side of the deployment it
is on — the GB reasoning, unchanged (D-017).

**The hint names both variables, always**, including when only one is missing. An operator who set
the id and not the secret is one variable away, and a hint that names only the one it happened to
check first sends them looking in the wrong place (D-037).

**`not_found`** — message: `"Bolagsverket has no organisation registered with identifier {id}."`
hint (must not repeat the message):

> "The identifier is well-formed, so it may never have been issued, or the organisation may have
> been struck off and removed. Bolagsverket adds a caveat of its own here: an organisation absent
> from one data producer may still exist at the other, so a Statistics Sweden-only entity can answer
> this way. Bolagsverket's free API cannot search by name, so there is no search_company call to
> fall back on for Sweden."

That last sentence is the honest opposite of Britain's `not_found` hint, which sends the caller to
`search_company`. Sending a Swedish caller there would waste a call on a 501 (§4).

**`invalid_id` from an upstream 400** — message:
`"Bolagsverket rejected {id} as a malformed identitetsbeteckning."` hint:

> "Bolagsverket validates a check digit that this module does not: it answers 'Identitetsbeteckning
> har ogiltig kontrollsiffra' for a number of the right length whose check digit is wrong. Check the
> digits. An organisationsnummer is ten digits and a personnummer is twelve (YYYYMMDDNNNN)."

---

## 7. Legal-form table

`registries/se/rules.py :: ORGANISATION_FORMS`, keyed by `organisationsform.kod`. **The codes are
Bolagsverket's, complete, from the portal's own code-list document.** English labels and duty
columns are ours.

`board` = must have a registered board. `accounts` = must file an annual report **with
Bolagsverket**. `period` = the filing period this module computes from (§5.4); blank means we
compute nothing. `None` means "depends on facts the register does not publish".

### 7.1 Which vocabulary drives `legal_form_code` (D-034)

`organisationsform` (Bolagsverket) **drives**; `juridiskForm` (SCB) is the **fallback**, used only
when `organisationsform` is null or carries a `fel`. Three reasons:

1. **It is the finer vocabulary.** The mapping Bolagsverket publishes is many-to-one and lossy:
   `AB` and `TPAB` both map to juridisk form `49`; five different organisationsformer map to `51`.
   Driving from the coarse list would throw away distinctions the register makes.
2. **It is the register's own.** `juridiskForm` is described in the schema as *"Legal form registered
   at the Swedish Tax Agency"* — a third authority's classification, arriving through SCB.
3. **The join rule says so.** *"Data från Bolagsverket hämtas när det finns data att hämta från både
   Bolagsverket och SCB"* — Bolagsverket wins where both have a value, and this module follows the
   register's own precedence rather than inventing one.

**The SCB code is never translated into a Bolagsverket code, and never carried in a second field.**
Bolagsverket publishes a mapping table and it is tempting to run it backwards; running it backwards
is guessing, because it is many-to-one (`49` could be `AB` or `TPAB`). Presenting a derived code as
if the register had said it is the provenance failure D-018 and D-026(c) exist to prevent, and
`UK_SPEC.md` §15 already ruled the identical case for `foreign_company_details.legal_form`: *"two
different taxonomies in one field is how a contract rots"*. The mapping table goes into
`rules_markdown()` as **documentation** (§13).

**When the fallback is used, note N5 fires**, naming the vocabulary and the code — so
`legal_form_code` is never ambiguous about which list it speaks, even though it is one field.

`legal_form_local` follows the same field: the `klartext` of whichever one drove the code. That is
Sweden's genuine local label, unlike GB where the register is already in English.

### 7.2 Confirmed forms — computed deadlines

| `kod` | Swedish | English | Limited liability | board | accounts | period |
|---|---|---|---|---|---|---|
| `AB` | Aktiebolag | Private or public limited company | yes | yes | yes | **7 months** (ÅRL 8:6) + `general_meeting` (ABL 7:10) |
| `EK` | Ekonomisk förening | Economic (co-operative) association | yes | yes | yes | **7 months** (ÅRL 8:6) — no `general_meeting`, §5.5 |

Those two, and only those two, are named in årsredovisningslagen 8 kap. 6 § in the words this spec
quotes: *"Ett aktiebolag och en ekonomisk förening ska betala en förseningsavgift om … inte har
kommit in … inom sju månader"*. Everything else in §7.3 is classified but computes nothing.

**`AB` covers both private and public companies and the dataset cannot tell them apart.** The
*date* is the same either way (seven months); only the fee differs (7 500 kr vs 15 000 kr), and
`applies_because` gives both figures rather than picking one. Do not attempt to infer *publikt* from
the identifier or the name.

### 7.3 Classified, no computed accounts period

Labels are ours; duty columns are `None` unless the entry is definitionally clear. These forms get
a `legal_form`, a `legal_form_local` and no deadlines.

| `kod` | Swedish | English | Limited liability | board | accounts |
|---|---|---|---|---|---|
| `E` | Enskild näringsverksamhet | Sole trader | **no** | no | `None` — filing depends on size thresholds the dataset does not publish |
| `HB` | Handelsbolag | General partnership | **no** | no | `None` — ÅRL 8:3 p.3 gives six months **only** where a legal person is a partner, which is not published (§5.5) |
| `KB` | Kommanditbolag | Limited partnership | partly | no | `None` — same reason |
| `EB` | Enkla bolag | Simple partnership (not a legal person) | no | no | `None` |
| `BRF` | Bostadsrättsförening | Tenant-owners' (housing) association | yes | yes | `None` — **`VERIFY`, and the highest-value gap in this file** (§5.5) |
| `KHF` | Kooperativ hyresrättsförening | Co-operative rental-tenancy association | yes | yes | `None` — same `VERIFY` |
| `BF` | Bostadsförening | Housing association | yes | yes | `None` — same `VERIFY` |
| `SF` | Sambruksförening | Joint-farming association | yes | yes | `None` — same `VERIFY` |
| `S` | Stiftelse som bedriver näringsverksamhet | Foundation carrying on business | yes | `None` | `None` — ÅRL 8:3 p.4 and 8:6 give **six** months, but the scope of the duty was not read (§5.5) |
| `I` | Ideell förening som bedriver näringsverksamhet | Non-profit association carrying on business | yes | `None` | `None` |
| `TSF` | Trossamfund som bedriver näringsverksamhet | Registered religious community carrying on business | yes | `None` | `None` |
| `FL` | Filial | Branch of a foreign company | inherits | `None` | `None` — see §7.4 |
| `BFL` | Utländsk banks filial | Branch of a foreign bank | inherits | `None` | `None` |
| `BAB` | Bankaktiebolag | Bank (limited company) | yes | yes | `None` — banks report under lagen om årsredovisning i kreditinstitut, a different act |
| `SB` | Sparbank | Savings bank | yes | yes | `None` — same |
| `MB` | Medlemsbank | Co-operative bank | yes | yes | `None` — same |
| `FAB` | Försäkringsaktiebolag | Insurance company (limited) | yes | yes | `None` — insurers report under lagen om årsredovisning i försäkringsföretag |
| `OFB` | Ömsesidigt försäkringsbolag | Mutual insurance company | yes | yes | `None` — same |
| `FOF` | Försäkringsförening | Insurance association | yes | yes | `None` — same |
| `TPAB` | Tjänstepensionsaktiebolag | Occupational pension company (limited) | yes | yes | `None` — same |
| `OTPB` | Ömsesidigt tjänstepensionsbolag | Mutual occupational pension company | yes | yes | `None` — same |
| `TPF` | Tjänstepensionsförening | Occupational pension association | yes | yes | `None` — same |
| `FF` | Försäkringsförmedlare | Insurance intermediary | `None` | `None` | `None` |
| `SE` | Europabolag | European company (SE) | yes | yes | `None` — `VERIFY`; ABL applies supplementarily but the filing chain was not read |
| `SCE` | Europakooperativ | European co-operative society | yes | yes | `None` — same |
| `EEIG` | Europeisk ekonomisk intressegruppering | European economic interest grouping | **no** | `None` | `None` |
| `EGTS` | Europeisk gruppering för territoriellt samarbete | European grouping of territorial co-operation | `None` | `None` | `None` |

> **`SE` is an organisationsform code meaning *Europabolag*, and it collides visually with the ISO
> country code.** Nothing in the code can confuse them — one is a `CompanyReport.legal_form_code`
> value, the other a `CompanyReport.country` value — but a reviewer reading `"SE"` in a fixture must
> know which is which, and no code may "helpfully" treat `legal_form_code == "SE"` as a country.
> Exactly the `NO`-as-a-UK-prefix trap `UK_SPEC.md` §5.1.2 records, one country later.

**Banks, insurers and pension undertakings deliberately compute nothing.** They are aktiebolag in
form, so the temptation to give them the seven-month rule is real; they report under
*lagen om årsredovisning i kreditinstitut och värdepappersbolag* and *lagen om årsredovisning i
försäkringsföretag* respectively, neither of which was read. D-009 decides it: no source, no
deadline.

Any `kod` **not** in either table maps to `legal_form = None`, all three duty fields `None`, note
N6, and — following D-009(a) — **no deadlines at all**.

### 7.4 A `filial` is not a sub-unit

A Swedish `FL` is a branch of a foreign company, and the obvious move is to set `is_subunit = True`
the way GB does for a `uk-establishment`. **Do not.** GB can do it because Companies House publishes
`branch_company_details.parent_company_number`, so `is_subunit` comes with a `parent_id` an agent
can actually call. Bolagsverket's dataset publishes **no link to the parent at all** — the fourteen
properties of `Organisation` contain nothing about ownership. `is_subunit = True` with
`parent_id = None` tells an agent "this is not the entity that files, and I cannot tell you which
one is", which is strictly worse than the truth: a `filial` has its own identifier, is on the
register in its own right, and is what the caller looked up. `is_subunit` stays `False` and the
English `legal_form` label says "Branch of a foreign company", which is the actionable fact.

---

## 8. Status derivation — three orthogonal signals

Sweden publishes no status field. It publishes three independent things that can all be true at
once, and D-035 rules how they combine.

**Precedence, highest first.** The first rung that fires decides `status`; the lower rungs still
fill their own fields and notes.

### Rung 0 — a status-bearing field was blocked by `fel` → `UNKNOWN`

Added 2026-09-06 after T26e (fix 3), the case §1.6 rule 1 was written about, one field further on
than the first draft followed it. If `avregistreradOrganisation`, `avregistreringsorsak` or
`pagaende…Lista` carries a `fel.typ` in `{OTILLGANGLIG_UPPGIFTSKALLA, TIMEOUT, OGILTIG_BEGARAN}`,
the payload contains **no status data**, and silence is not good standing. `status = UNKNOWN`,
`is_active = False` (the field is a plain `bool`, and "on the register and not winding down" is
exactly what we cannot assert), `status_detail`:
`"Bolagsverket could not supply this organisation's registration status ({dataproducent} did not answer), so it is unknown whether it is struck off or in a winding-up or restructuring procedure."`
N13 fires as usual; N1 does not add a second sentence for `UNKNOWN`. Rung 0 is what licenses rung
3's wording — rung 3 is reached only when the fields it speaks for actually arrived.

**Evaluation order, ruled 2026-09-06 (T26f judgement call, confirmed):** rung 0 is *numbered* first
because it is the precondition for rung 3, but it is *evaluated* after rungs 1 and 2 — real data
beats absence. A struck-off date that arrived (rung 1) or a `KK` that arrived (rung 2) decides the
status even when the other status-bearing field was blocked; rung 0 fires only when neither rung 1
nor rung 2 fired **and** at least one status-bearing field was blocked. Reading the "highest first"
sentence above literally — a blocked field overriding a real `avregistreringsdatum` — would turn
a known strike-off into `UNKNOWN`, which is the opposite of §1.6's rule. A blocked
**SCB** field (`verksamOrganisation`, `reklamsparr`, `juridiskForm`) never triggers rung 0: those
never decide status (D-035). Bolagsverket's own partial-failure example (`bv_uppgiftskalla_fel.json`)
is the fixture for this rung.

### Rung 1 — `avregistreradOrganisation.avregistreringsdatum` is present → `DELETED`

The organisation has been struck off. `deregistered_at` ← the date (§2.5's tolerant parser).
`status_detail` names the reason verbatim from `avregistreringsorsak`:
`"Struck off the Bolagsverket register on {date} ({kod}: {klartext})."`

**Every `AVREGISTRERINGSORSAK` maps to `DELETED`**, all seventeen of them, and none of them may
promote the status back. `CompanyStatus.DELETED` is documented as *"Removed from the register; the
record survives only as history"*, which is exactly what happened, whatever the reason —
`KKAV` Konkurs, `LIAV` Likvidation, `FUAV` Fusion, `DELAV` Delning, `OMAV` Ombildning,
`GROMAV` Gränsöverskridande ombildning, `OMBAB` / `BABAKEJH` Ombildat till bankaktiebolag,
`NYINN` Ny innehavare, `DOM` Beslut av domstol, `AKEJH` Aktiekapitalet inte höjts,
`ARSEED` Årsredovisning saknas, `VDSAK` Verkställande direktör saknas, `OVERK` Overksamhet,
`VERKUPP` Verksamheten har upphört, `UTLKKLI`, `AVREG` Avregistrerad.

`DISSOLVED` is deliberately never used for `SE`: it means *"winding-up finished but the record has
not been removed from the register"*, and Bolagsverket has removed it. The reason code is what
carries the nuance, in `status_detail` and in note N1 — and it carries a lot: `ARSEED` (struck off
for missing annual reports) and `FUAV` (absorbed in a merger) are very different facts about a
counterparty and both would be flattened by any single enum member.

An unrecognised reason code is still `DELETED`; `status_detail` renders `{kod}: {klartext}` and note
N1 says the reason is not one this module knows.

### Rung 2 — `pagaende…Lista` is non-empty → the procedure decides

**The list is plural** and Bolagsverket's own example carries `KK` (2024-01-26) *and* `LI`
(2024-05-26). Precedence within the list is by code, not by date or position: **`KK` beats
everything, then `LI`, then the rest of bucket 1.**

**Bucket 1 — the entity is insolvent, being wound up, or being absorbed. Status changes.**

| `kod` | Swedish | `CompanyStatus` | Also |
|---|---|---|---|
| `KK` | Konkurs | **`BANKRUPT`** | `bankruptcy_date` ← `fromDatum`. The only code that sets it |
| `LI` | Likvidation | `UNDER_LIQUIDATION` | |
| `FR` | Företagsrekonstruktion | `UNDER_LIQUIDATION` | Distress, **not** bankruptcy — `status_detail` says so explicitly |
| `AC` | Ackordsförhandling | `UNDER_LIQUIDATION` | Composition proceedings; same sentence |
| `RES` | Resolution | `UNDER_LIQUIDATION` | A bank or investment firm in resolution |
| `FUOL` | Överlåtande i fusion | `UNDER_LIQUIDATION` | This entity is being absorbed and will cease to exist |
| `DEOL` | Överlåtande vid delning | `UNDER_LIQUIDATION` | Same |

**Bucket 2 — the procedure is about somebody else, or about form rather than survival. Status is
left alone**, and a `notes` sentence records it.

| `kod` | Swedish | Why the status must not change |
|---|---|---|
| `FUOT` | Övertagande i fusion | This is the **acquiring** company. It is healthy and continuing; flagging it as winding up would be a false alarm on a company that is growing |
| `DEOT` | Övertagande vid delning | Same |
| `OM` | Ombildning | A change of legal form; the entity continues |
| `GROM` | Gränsöverskridande ombildning | A cross-border conversion; the entity continues in another member state |

`GROM` and `OM` are marked `VERIFY`: their bucket is read from the Swedish label, not from a
statute. Both get a loud `notes` sentence regardless, so a caller is never left with a bare
`ACTIVE` for a company mid-conversion.

**An unrecognised code → `UNKNOWN`, `is_active` False, note N2.** The safe direction, and the
reasoning is a harm asymmetry rather than a preference: a false non-active costs the caller a manual
check, while a false `ACTIVE` on a company Bolagsverket has flagged is how an invoice gets paid to a
bankruptcy estate. `UNKNOWN`'s own docstring — *"the registry returned a record but no status could
be derived from it"* — is exactly true here.

**`UNDER_COMPULSORY_LIQUIDATION` is never used for `SE`.** Swedish law distinguishes *frivillig
likvidation* from *tvångslikvidation*, and this dataset does not: the code is `LI` either way. The
enum member stays available for a register that does distinguish them, and `status_detail` carries
the honest sentence — the same ruling `UK_SPEC.md` §8 note 1 made for Britain, and it has the same
consequence, that `UNDER_LIQUIDATION` means less in `SE` and `GB` than it does in `NO`.

**`bankruptcy_date` is set by `KK` and by nothing else.** Not by `KKAV` (the *deregistration* reason
"konkurs", which records that a completed bankruptcy ended the company — its date is a
deregistration date, not the date bankruptcy was opened), and not by `FR` or `AC`. A date under the
wrong label is worse than no date.

### Rung 3 — nothing above fired → `ACTIVE`

The organisation is on the register and is not winding down. `status_detail`:
`"Registered with Bolagsverket and not marked as struck off or in any winding-up or restructuring procedure."`

**`verksamOrganisation` does not change the status, and this is the decision worth reading twice
(D-035).** SCB's flag means "has F-skatt and/or VAT and/or employer registration". A company can be
registered, in good standing, and hold none of those — newly formed, dormant, or a holding company
with no operations. So:

- `kod == "JA"` → nothing. `ACTIVE`, no note.
- `kod == "NEJ"` → still `ACTIVE`, plus **note N3**, which says in plain English that Statistics
  Sweden does not mark it as economically active and that this is a different question from being on
  the register.
- absent or `fel` → nothing at all. Absence is not a negative (D-011, D-026(b)).

**So `is_active` for `SE` means: on the register and not winding down. It does not mean trading.**
Sweden is the first country in this project where the register publishes both facts and they can
disagree, and the resolution is the one D-004 forces — `is_active` is documented as a mirror of
`status == ACTIVE`, `status` is a lifecycle enum, and "economically active" is not a lifecycle
state. Inventing a `DORMANT` member to hold it would change a shared contract for one country's
convenience, and would be read by an agent as a lifecycle claim about `NO` and `GB` companies that
we have no data to make. The signal is not lost; it is in `notes`, where a caller reads it, and it
is named as Statistics Sweden's rather than Bolagsverket's.

Bolagsverket's own aktiebolag example carries `verksamOrganisation: "NEJ"`, so this branch has a
fixture from day one (`bv_ab_dormant.json`).

Any status other than `ACTIVE` adds a plain-English `notes` entry (N1), because an agent about to
pay an invoice must see it without reading an enum table.

---

## 9. Cache

Per D-006, unchanged in mechanism: SQLite, one file, `REGISTRY_MCP_CACHE_PATH`.

- Key: `"SE:bolagsverket:entity:{identitetsbeteckning}"`. **There is no search key** (§4).
- TTL 24 h for `ok`, 1 h for `not_found`.
- A hit sets `cached=True` and preserves the **original** `fetched_at`.
- `REGISTRY_MCP_CACHE_TTL_SECONDS` / `REGISTRY_MCP_CACHE_DISABLED=1` behave as for the other two.
- A cache failure is logged and ignored, never turned into a `RegistryError`.
- **The raw upstream JSON is cached, not the mapped `CompanyReport`** — the GB choice, for the GB
  reason: a later fix to `mapping.py` then applies to entries already cached.

**One Sweden-specific rule, and it is not optional: a partially failed 200 is never written to the
cache** (§1.6, §6.3). `fel.typ` in `{OTILLGANGLIG_UPPGIFTSKALLA, TIMEOUT, OGILTIG_BEGARAN}` on any
mapped field means a data producer was unreachable for *that request*, and caching it would serve a
company with no name, no form and no dates for the next 24 hours — from a response that was
technically a 200. D-006 explicitly makes cache behaviour the module's own ("any cache failure is
logged and ignored"); declining to store a known-incomplete answer is the same discipline pointed
the other way.

**The cache matters more here than in either live country.** 60 requests a minute is the tightest
budget in the project, there is no search endpoint to spread load across, and Bolagsverket's data
changes daily at most. If the cache is disabled, Sweden is a 60/min service.

**The environment is part of the identity of a cached row.** A deployment that switches
`BOLAGSVERKET_ENVIRONMENT` from `test` to `production` must not serve test companies from the
cache. Either include the environment in the key or document that the cache file is per-environment;
the key is simpler and is what T26b implements: `"SE:bolagsverket:entity:{env}:{id}"` with `env` in
`{prod, test}`. *(This is the one place `SE`'s key shape differs from `NO`/`GB`; D-006's key format
is a convention with a `kind` segment, not a fixed grammar, and the extra segment is inside the
module's own namespace.)*

---

## 10. Errors

`{"error": {"code", "message", "hint"}}` — exactly `RegistryError.to_dict()`, byte-identical on REST
and MCP (D-007). Codes this module raises: `invalid_id`, `not_found`, `not_implemented`,
`rate_limited`, `upstream_error`, `upstream_timeout`. It does **not** raise `bad_request`, because
the operation that would have validated a `limit` does not exist (§4).

Every hint names a concrete next call. The four that carry the most weight for Sweden:

- `not_implemented` → `lookup_company` with a number, `validate_company_id` first, the bulk files,
  and the fact that `search_company` works for the other countries (§4).
- `upstream_error` with no credentials → `list_countries`, **both** env vars, and the form URL (§6.4).
- `invalid_id` → the ten/twelve-digit shapes, and — for a nine-digit input — Norway (§5.1.2).
- `not_found` → that Bolagsverket's own answer is scoped to one data producer, and that there is no
  name search to fall back to (§6.4).

---

## 11. Logging

`core/log.py`, unchanged (`NORBIZ_SPEC.md` §11). `query` is the identifier. **Never a credential,
never the bearer token, never a header.**

> **Read finding F1 in §0 before treating this section as routine.** For a Swedish sole trader the
> `query` this module's callers log **is a personnummer**, and Bolagsverket cares enough about that
> to make its read operations POSTs. The module cannot fix it from inside `registries/se/`; what it
> can do is not make it worse: nothing in `registries/se/` writes the identifier anywhere except the
> request body, the cache key, `CompanyReport.id` — and, on a partial 200 with no name, the
> `CompanyReport.name` fallback (§14 test 95; T26e found this fourth place; T26d may prefer `None`)
> — and **no `notes` sentence ever repeats it** (§2.1). The surface-side fix is ruled in **D-040**
> (`tasks/T28.md`): `Registry.id_may_be_personal = True` for SE, and the surfaces store nothing as
> `query`.

`X-Request-Id` is logged at DEBUG so a Bolagsverket support case can be tied to one of our calls. It
is a UUID we generated and contains nothing about the caller.

---

## 12. Confidence

D-005 anchors. Only one applies: **`1.0`** for an identifier lookup, with
`confidence_basis = "exact identifier lookup in the Bolagsverket register"`. The search anchors
(0.95 / 0.8 / 0.6 / 0.4) have no caller for `SE` because there is no search (§4) — they are not
implemented, and `registries/se/rules.py` contains no scoring function at all.

One case deserves a word: a lookup that resolves to **one of several businesses** on a sole trader's
identifier (§2.2) keeps `confidence = 1.0`. Confidence answers "is this the entity you asked for",
and it is: the caller supplied an identifier and this is the person it identifies. Whether it is the
*business* they meant is a different question, and note N7 is where that is answered — in the field
built for caveats, not by degrading a number that means something else.

---

## 13. `rules_markdown()`

Served as the MCP resource `registry://rules/SE`. It must contain, in prose, at least:

1. What the register is (Bolagsverket, with SCB as a second data producer in the same payload), the
   join rule, and the licence position of §1.9 — quoting the regime and stating that Bolagsverket
   names no licence.
2. **That there is no name search**, why (the API has four operations and none takes a name), and
   what to do instead: an identifier, or the bulk downloadable files.
3. The identifier: ten digits for an organisationsnummer, **twelve for a sole trader's
   personnummer**, digits only on the wire, one number may carry several businesses, and — stated
   plainly — that a sole trader's identifier is a natural person's national identity number.
4. **That this module does not check the check digit** and why (unsourced), and that Bolagsverket
   does, server-side, answering `"Identitetsbeteckning har ogiltig kontrollsiffra"`.
5. **That Swedish filing deadlines do not move for weekends or holidays in this module**, and that
   this is because no rule saying they do could be sourced — not because one was found saying they
   do not. The honest version of §5.3, and the opposite of the Norwegian rule the same server
   serves.
6. The two computed deadlines with their full derivation chain: ABL 7 kap. 10 § (AGM, six months),
   ÅRL 8 kap. 3 § (file within one month of adoption — **not computable**, no adoption date is
   published), ÅRL 8 kap. 6 § (seven months, where the förseningsavgift begins). Say which of the
   three the emitted date is.
7. The förseningsavgift, in prose, with ÅRL 8 kap. 6 § and 6 a §: 7 500 kr for a private aktiebolag
   or ekonomisk förening and 15 000 kr for a public one, escalating twice at two-month intervals to
   a maximum of 30 000 kr and 60 000 kr — and ÅRL 8 kap. 7 §, that no fee may be imposed once
   bankruptcy is registered.
8. The nine-month variant of 8 kap. 6 §, and that we cannot see who qualifies for it.
9. The calendar-year assumption, and that Bolagsverket does not publish the financial year.
10. The three status signals, that they are orthogonal, and **that `is_active` means "on the
    register and not winding down", not "trading"**.
11. The two vocabularies, which one drives `legal_form_code`, and the published mapping table
    between them — as documentation, with the warning that it is many-to-one and must not be run
    backwards.
12. What Bolagsverket's free dataset does **not** publish: officers, share capital, beneficial
    owners, employee counts, financial figures, the financial-year end, VAT registration, a visiting
    address, email, phone and website.
13. Skatteverket's deadlines (inkomstdeklaration 2, moms, arbetsgivardeklaration) named as real
    obligations this module does not compute, with the reason — no financial-year end and no VAT
    period in the dataset.
14. That `/dokumentlista` and `/dokument` exist and are not yet exposed.
15. (Since R-2, 2026-09-06.) That `advertising_protected` is `true`/`false` from Statistics Sweden's
    *reklamspärr* flag, and that when `true` the `notes` sentence states it and must travel with any
    contact details passed on.

---

## 14. Numbered test list

**T26b implements exactly this list**, one test function per number, named `test_NN_<slug>`, in
`tests/test_rules_se.py` (1–78) and `tests/test_client_se.py` (79–112), with 113–118 marked
`@pytest.mark.live`. Fixed `today` values throughout; nothing reads the clock. Follow
`tests/test_client_gb.py`'s fixtures exactly: an autouse isolated cache on `tmp_path`, an autouse
credential fixture that sets fake values for non-live tests, and an autouse client reset that calls
`aclose()` afterwards.

### A. `validate_id` — normalisation and shape (1–22)

1. `"5560160680"` → `"5560160680"` (canonical, unchanged).
2. `"556016-0680"` → `"5560160680"` (hyphen stripped).
3. `"556016 0680"` → `"5560160680"` (space stripped, including a non-breaking space).
4. `"556016.0680"` → `"5560160680"`.
5. `"SE556016068001"` → `"5560160680"` (VAT form: `SE` prefix and `01` suffix stripped).
6. `"se556016068001"` → `"5560160680"` (upper-cased first).
7. `"194009272719"` → `"194009272719"` — **twelve digits are preserved, not truncated**. The
   single most important normalisation test in the file (§5.1).
8. `"19400927-2719"` → `"194009272719"`.
9. `"19400927+2719"` → `"194009272719"` (the over-100 separator).
10. `"3021234567"` → `"3021234567"` (a GD-nummer; ten digits, accepted).
11. `"5560160681"` → **accepted**, returning `"5560160681"`. A wrong check digit is *not* a local
    rejection (§5.1.1). This test is the ruling.
12. `"5560000002"` → **accepted**. One of the four numbers Bolagsverket's own test environment
    permits and modulus-10 refuses.
13. `""` → raises `invalid_id`.
14. `"923609016"` → raises `invalid_id` (nine digits), and the hint contains `"NO"` and
    `"Norwegian"`.
15. `"55601606800"` → raises `invalid_id` (eleven digits).
16. `"556016068"` → raises `invalid_id` (nine digits after stripping).
17. `"1940092727190"` → raises `invalid_id` (thirteen digits).
18. `"55601606AB"` → raises `invalid_id` (letters that are not the `SE` VAT prefix).
19. `"SE5560160680"` → raises `invalid_id` — `SE` plus ten digits is not the VAT form, which is
    `SE` + ten + `01`; the hint mentions VAT.
20. `"197713012384"` → raises `invalid_id` (month `13` is impossible in the twelve-digit form).
21. `"198100032384"` → raises `invalid_id` (day `00`).
22. The error from test 14 has `code == ErrorCode.INVALID_ID` and a non-empty `hint`.

### B. `format_id` and `id_caveat` (23–30)

23. `format_id("5560160680") == "556016-0680"`.
24. `format_id("194009272719") == "19400927-2719"`.
25. `format_id("55601")` is `None` (not a recognised width).
26. `validate("194009272719")` → `valid is True`, `hint is None`, and `reason` mentions
    "personnummer" and that one number can carry several businesses.
27. `validate("5560160681")` → `valid is True`, `hint is None`, and `reason` mentions the check
    digit, the words "not been able to confirm" (or the shipped equivalent), `"2026-09"` and
    Bolagsverket.
28. `validate("5560160680")` → `valid is True` and `reason` says **nothing** about the check digit —
    a passing unverified check is silent (§5.1.5).
29. `validate("5560160680").normalized == "5560160680"` and `.formatted == "556016-0680"`.
30. `validate` never raises for any input in tests 1–21; the invalid ones return `valid is False`
    with a non-empty `reason` and a non-empty `hint`.

### C. Legal-form mapping (31–42)

31. `"AB"` → `"Private or public limited company"`, `limited_liability=True`, `has_board_duty=True`,
    `has_annual_accounts_duty=True`, and a computed accounts period.
32. `"EK"` → `has_annual_accounts_duty=True` and a computed accounts period.
33. `"E"` → `limited_liability=False`, `has_annual_accounts_duty=None`, **no** computed period.
34. `"HB"` and `"KB"` → `limited_liability` is not `True`, `has_annual_accounts_duty=None`, no
    computed period.
35. `"BRF"` → classified, `legal_form` non-empty, `has_annual_accounts_duty=None`, **no** computed
    period (the sourced-gap case of §5.5).
36. `"BAB"`, `"FAB"`, `"SB"` → all `has_annual_accounts_duty=None` and no computed period, despite
    being limited companies.
37. `"FL"` → classified, `is_subunit is False`, `parent_id is None` (§7.4).
38. `"SE"` (Europabolag) → `legal_form` contains "European company"; `report.country` is still
    `"SE"` and nothing treats the code as a country (§7.3).
39. `"ZZZ"` → `legal_form is None`, all three duty fields `None`, and `notes` contains N6.
40. A payload with `organisationsform: null` and `juridiskForm: {"kod": "49", ...}` →
    `legal_form_code == "49"`, `legal_form_local == "Övriga aktiebolag"`, and `notes` contains N5
    naming Statistics Sweden.
41. A payload with **both** present → `legal_form_code` is the `organisationsform` code, N5 does
    **not** fire, and the SCB code appears nowhere in the report (§7.1).
42. `sector_code is None` and `sector is None` on every fixture — `juridiskForm` never reaches them.

### D. Status derivation (43–60)

43. No avregistrering, no procedure, `verksamOrganisation: "JA"` → `ACTIVE`, `is_active is True`,
    and `notes` contains no status note.
44. `avregistreradOrganisation.avregistreringsdatum = "2001-03-15"`, `avregistreringsorsak.kod =
    "VERKUPP"` → `DELETED`, `deregistered_at == date(2001, 3, 15)`, `is_active is False`, and
    `status_detail` contains `"VERKUPP"`.
45. The same with `"2023-05-05T00:00:00.000+00:00"` → `deregistered_at == date(2023, 5, 5)` (§2.5's
    tolerant parser).
46. `avregistreringsorsak.kod = "ARSEED"` → still `DELETED`, and `status_detail` renders the
    register's `klartext`.
47. An unrecognised avregistrering reason → still `DELETED`, no exception, raw code in
    `status_detail`.
48. `pagaende…Lista = [{"kod": "KK", "fromDatum": "2024-01-26"}]` → `BANKRUPT`,
    `bankruptcy_date == date(2024, 1, 26)`, `is_active is False`.
49. `fromDatum = "2024-01-26T00:00:00.000+00:00"` → the same `bankruptcy_date` (§2.5).
50. `[{"kod": "LI"}]` → `UNDER_LIQUIDATION`, `bankruptcy_date is None`, and `status_detail` says
    Bolagsverket does not distinguish voluntary from compulsory liquidation.
51. `[{"kod": "KK"}, {"kod": "LI"}]` (Bolagsverket's own example) → `BANKRUPT`. `KK` beats `LI`
    regardless of list order; assert both orderings.
52. `[{"kod": "FR"}]` → `UNDER_LIQUIDATION`, `status is not CompanyStatus.BANKRUPT`, and
    `status_detail` says företagsrekonstruktion is not bankruptcy.
53. `[{"kod": "AC"}]` and `[{"kod": "RES"}]` → both `UNDER_LIQUIDATION`.
54. `[{"kod": "FUOL"}]` → `UNDER_LIQUIDATION`; `[{"kod": "FUOT"}]` → **`ACTIVE`**, `is_active is
    True`, plus a `notes` sentence. The false-alarm test, and the pair must be asserted together.
55. `[{"kod": "DEOT"}]` → `ACTIVE` plus a note; `[{"kod": "DEOL"}]` → `UNDER_LIQUIDATION`.
56. `[{"kod": "XYZ", "klartext": "Något nytt"}]` → `UNKNOWN`, `is_active is False`, and `notes`
    contains N2 with both the code and the `klartext`.
57. Avregistrerad **and** an ongoing `KK` → `DELETED` (rung 1 wins), and `bankruptcy_date` is still
    set from the `KK`'s `fromDatum`.
58. `verksamOrganisation: "NEJ"` with nothing else → **`ACTIVE`**, `is_active is True`, and `notes`
    contains N3 naming Statistics Sweden. The D-035 test.
59. `verksamOrganisation: null` → `ACTIVE` and **no** N3 (absence is not a negative).
60. `avregistreringsorsak.kod == "KKAV"` with no ongoing procedure → `DELETED` and
    **`bankruptcy_date is None`** — a deregistration reason never sets the bankruptcy date (§8).

### E. Deadlines (61–78)

Subject is an active `AB` unless stated. `today` is given per test.

61. `today = date(2026, 3, 1)` → exactly two deadlines: `general_meeting` due 2026-06-30 and
    `annual_accounts` due 2026-07-31.
62. `today = date(2026, 7, 1)` → `general_meeting` rolls to 2027-06-30 while `annual_accounts` is
    still 2026-07-31; the list is sorted by `due_date` ascending, so `annual_accounts` is first.
63. `today = date(2026, 8, 1)` → both are next year's: 2027-06-30 and 2027-07-31.
64. `today = date(2026, 6, 30)` → `general_meeting` is still 2026-06-30 with `days_until == 0`; a
    deadline is due *on* `today`, not past.
65. Every returned deadline has `statutory_date == due_date` and `rolled_forward is False`,
    including one whose `due_date` falls on a Saturday: 31 July 2027 is a Saturday and stays
    2027-07-31 (§5.3).
66. `registries/se/` contains no holiday table and never calls
    `core.rules.common.roll_forward` — assert by monkeypatching `roll_forward` to raise (§5.2).
67. `annual_accounts.applies_because` contains `"8 kap. 6 §"`, `"sju månader"` or "seven months",
    `"7 500"` and `"15 000"`, and the "may be earlier" sentence about the general meeting.
68. `general_meeting.applies_because` contains `"7 kap. 10 §"` and "six months".
69. **`annual_accounts.applies_because` does not claim that årsredovisningslagen 8 kap. 3 § sets a
    seven-month deadline.** It may cite 8:3, but only as the one-month-after-adoption rule. This
    test exists because the project's own library file said otherwise (§5.4.1).
70. An `EK` gets `annual_accounts` and **no** `general_meeting` (§5.5).
71. An `E` (sole trader) gets **no** deadlines and **both** N8 and N14 in `notes` (N14 added
    2026-09-06, T26e fix 5 — before that this test passed on N8 alone).
72. A `BRF` gets no deadlines (§7.3) **and N14** — the note is the assertion, not an incidental.
73. An unclassified `organisationsform` gets no deadlines and note N6 (D-009(a)).
74. `status == BANKRUPT` → empty list plus a note that contains `"8 kap. 7 §"`.
75. `status == DELETED` → empty list plus a note.
76. `status == UNDER_LIQUIDATION` → empty list plus a note (Sweden follows GB, not NO).
77. `verksamOrganisation: "NEJ"` on an active `AB` → **both deadlines are still returned**. The
    dormancy flag never suppresses a duty (§5.4.5).
78. `deadlines(report, today)` called twice with the same arguments returns equal lists; the result
    does not change with the process timezone; every `Deadline` has `country == "SE"`,
    `registry == "bolagsverket"`, a non-empty `applies_because`, a `source_url` on `lagen.nu`, and
    `days_until == (due_date - today).days`.

### F. Mapping — every claim bound to a saved fixture (79–98)

79. `bv_ab_active.json` → `name == "Cykelbolaget AB"` (the `FORETAGSNAMN` entry, **not** the
    `SARSKILT_FORETAGSNAMN` one that appears later in the list), `legal_form_code == "AB"`,
    `status == ACTIVE`, `id == "5299999994"`, `id_formatted == "529999-9994"`.
80. Same fixture: `previous_names == []`, and `notes` contains N12 naming *Mopedbolaget AB* and
    *Bicycle expert*.
81. Same fixture: `industry_codes == [IndustryCode(code="47642", description="Specialiserad
    butikshandel med cyklar", scheme="SNI 2007", rank=1), IndustryCode(code="45400", …, rank=2)]`.
82. Same fixture: `registered_at == date(2000, 1, 23)` and **`founded_at is None`** —
    `infortHosScb` is not a foundation date (§2).
83. Same fixture: `postal_address.lines == ["C/o Annat företag", "Jobbstigen 2"]`,
    `.postal_code == "12345"` (unspaced, as published), `.city == "Grönköping"`,
    `.country_code == "SE"`, `.country_name == "Sverige"`, and **`business_address is None`** (§3).
84. Same fixture: `activity` is the trimmed `verksamhetsbeskrivning.beskrivning`.
85. Same fixture: `employees is None`, `employees_reported is False`, `vat_registered is None`,
    `vat_number is None`, `share_capital is None`, `website is None`, `email is None`,
    `phone is None`, `parent_id is None`, `is_subunit is False`, `registers == {}`,
    `published_deadlines == []`, `sector_code is None`.
86. Same fixture: `notes` contains N4, because `reklamsparr.kod == "JA"` (D-036).
87. `bv_ab_dormant.json` → `status == ACTIVE`, `is_active is True`, and `notes` contains N3.
88. `bv_ab_konkurs.json` → `status == BANKRUPT`, `bankruptcy_date == date(2024, 1, 26)`.
89. `bv_ab_fusion_overtagande.json` → `status == ACTIVE` plus a note (§8 bucket 2).
90. `bv_ab_avregistrerad.json` → `status == DELETED`, `deregistered_at == date(2023, 5, 5)` from the
    **datetime-shaped** string.
91. `bv_enskild_two.json` (Bolagsverket's own two-business sole trader) → **one** `CompanyReport`,
    `id == "194009272719"`, `id_scheme == "personnummer"`,
    `name == "CITY SKOR THOMAS CARLSON"` (the first element), `legal_form_code == "E"`,
    `activity == "HANDEL MED SKOR."` (**leading whitespace stripped**), and
    `postal_address.city == "ESLÖV"` — every field from the *same* element (§2.2).
92. Same fixture: `notes` contains N7 naming both businesses **and** both `namnskyddslopnummer`
    values, and N8 (the sole-trader personal-data note, D-039).
93. Same fixture: `notes` contains no digit string equal to the identifier — **no note repeats a
    personnummer** (§2.1, §0 F1).
94. `bv_scb_only.json` → `legal_form_code == "49"` and `notes` contains N5.
95. `bv_uppgiftskalla_fel.json` (Bolagsverket's own partial-failure example) → **constructs without
    raising**, `name` falls back to the identifier or the mapper raises a `RegistryError` — assert
    the shipped behaviour explicitly, whichever T26b chooses, and `notes` contains N13 naming the
    unavailable producer. **Amended 2026-09-06 (T26e fix 3): the report's `status` is `UNKNOWN` and
    `is_active` is `False`** (§8 rung 0), never `ACTIVE`.
96. `bv_finns_ej.json` → the mapper's not-found detector fires (§1.7).
97. `registreringsland` is never read: a fixture with `{"kod": "XX-LAND"}` still yields
    `report.country == "SE"`.

*Added 2026-09-06 after T26e (fixes 3–5). T26f may have shipped these unnumbered; the T26f review
reconciles names to numbers.*

119. `bv_ab_active.json` with `juridiskForm`, `verksamOrganisation` and `reklamsparr` each carrying
     `fel.typ == "ORGANISATION_FINNS_EJ"` (SCB lacks it, Bolagsverket has it) → `is_not_found(...)`
     is `False` and the report maps as an active `AB` (§6.3, fix 4).
120. A payload whose `pagaende…Lista` wrapper carries `fel.typ == "TIMEOUT"` → `status is UNKNOWN`,
     `is_active is False`, `status_detail` names the producer, N13 present (§8 rung 0, fix 3).
121. `pagaende…Lista == [KK, FUOT]` → `BANKRUPT` **and** the bucket-2 note for `FUOT` is still
     present (§8 "the lower rungs still fill their own fields and notes", fix 15a).

*Added 2026-09-06 with R-2 (T29), §2.6.*

122. `reklamsparr.kod == "JA"` → `advertising_protected is True` **and** N4 present.
123. `reklamsparr.kod == "NEJ"` → `advertising_protected is False` and no N4.
124. `reklamsparr` absent → `advertising_protected is None`.
125. `reklamsparr` blocked by `fel` → `advertising_protected is None` (and N13 names SCB).
98. A fixture using the **misspelled** `pagandeAvvecklingsEllerOmstruktureringsforfarande` key with
    a `KK` inside still yields `status == BANKRUPT`. This is the Altinn bug (§15) and the test that
    stops a silent regression to "healthy company".

### G. Client — `respx`-mocked, no network (99–112)

99. With `BOLAGSVERKET_CLIENT_ID` and `BOLAGSVERKET_CLIENT_SECRET` unset, `lookup` raises
    `upstream_error` **without making an HTTP request** (assert the mock's call count is 0), and the
    hint contains **both** variable names and `"list_countries"`.
100. Importing `registry_mcp.registries.se` with neither variable set succeeds — no exception at
    import time — and `list_countries()` contains `"SE"`.
101. With only `BOLAGSVERKET_CLIENT_ID` set, the same error, and the hint still names both.
102. A successful lookup makes **two** requests in order: the token POST to
    `portal.api.bolagsverket.se` (form-encoded, both scopes, space-separated) and the data POST to
    `gw.api.bolagsverket.se/vardefulla-datamangder/v1/organisationer` carrying
    `Authorization: Bearer …` and a JSON body `{"identitetsbeteckning": "…"}`. **Assert the token
    host is `portal.`, not `gw.`** (§1.1).
103. A second lookup within the token's `expires_in` makes **no** second token request; a lookup
    after it does.
104. A data call answering 401 triggers exactly one token refresh and one retry; a second 401 raises
    `upstream_error` whose hint names both variables (§6.1).
105. `BOLAGSVERKET_ENVIRONMENT=test` sends both requests to `gw-accept2.` / `portal-accept2.`, and
    the resulting report's `source` contains "test environment" and `notes` contains N10.
106. `BOLAGSVERKET_ENVIRONMENT=wibble` raises `upstream_error` naming the two legal values, and
    makes no request.
107. Each request carries a distinct `X-Request-Id`, and the `User-Agent` contains `registry-mcp`
    and `REGISTRY_MCP_CONTACT_EMAIL`.
108. `search("volvo")` raises `not_implemented`, **makes no HTTP request at all** (call count 0,
    including the token), and the hint contains `lookup_company` and mentions the bulk files.
109. `search` raises `not_implemented` even with no credentials set — the 501 is a fact about the
    register, not about the deployment, and it must not be masked by the credentials check.
110. `mcp/connector.py`'s `search` alias, with `SE` registered and a mocked NO/GB result, still
    returns the NO/GB hits — the SE `not_implemented` drops one country and does not raise (§4,
    D-031(c)).
111. A 200 whose body carries `fel.typ == "ORGANISATION_FINNS_EJ"` raises `not_found`, and the hint
    mentions that the other data producer may still hold the organisation. A 200 carrying
    `OTILLGANGLIG_UPPGIFTSKALLA` does **not** raise, produces N13, and **writes nothing to the
    cache** — assert the second identical call makes a second HTTP request.
112. Two identical successful lookups: the first has `cached is False`, the second `cached is True`
    with the same `fetched_at` and no HTTP request. A 400 raises `invalid_id` and is not retried
    (call count exactly one after the token). A 500 followed by a 200 returns the report (exactly
    one retry); two 500s raise `upstream_error` with exactly two data calls, not three. **A
    recognisable client secret and the bearer token appear in no log record, no exception message
    and no `RegistryError.details`** — drive a 401 and a timeout and assert their absence from the
    captured log output and from every `to_dict()`.

### H. Live done-check — network, `@pytest.mark.live`, excluded from CI (113–118)

Run against the **test** environment unless stated. These are T26d's, not T26b's.

113. `lookup("5560021361")` against test returns a `CompanyReport` with `cached is False`; a second
    call within the TTL returns `cached is True`.
114. `lookup("198101052382")` against test — the workbook's "enskild firma, **två
    namnskyddslöpnummer**" scenario — returns one report whose `notes` contains N7 naming two
    businesses. **The live proof of §2.2.**
115. `lookup("193403223328")` against test raises `not_found`, and the recorded response body is
    saved as `bv_finns_ej.json`, replacing the shape-only fixture (recon "could not be verified"
    item 7).
116. `lookup("5560000002")` against test — **the §5.1.1 experiment.** Record the outcome in
    `REVIEW.md` §T26e whichever way it goes: an organisation refutes the modulus-10 caveat, a
    `400 "ogiltig kontrollsiffra"` confirms it.
117. Every field name this spec's mapper reads is present in the live `5560021361` payload, or is
    explicitly optional in §2. A field this spec names that the live payload does not have is a
    **blocking** finding for `REVIEW.md`, not something to work around. In particular, record which
    spelling of `pagaende…` and which `organisationsnamntyp` foreign-language code the wire actually
    uses.
118. `lookup("5560160680")` against **production** returns `status == ACTIVE` and a plausible
    registered name — the `id_example` check of §1.10. If it does not, replace `id_example` with
    `5560125790` and re-run.

---

## 15. Deliberately not mapped

| Field | Why not |
|---|---|
| `registreringsland` | Always `{"kod": "SE-LAND", "klartext": "Sverige"}`. It is **not** an ISO code and `country` is a constant for a country module anyway |
| `organisationsdatum.infortHosScb` | The date SCB ingested the record. Not a foundation date, not a registration date, and `CompanyReport` has no field whose meaning it matches. Mapping it to `founded_at` would be an invented fact (§2) |
| `namnskyddslopnummer` | Read to build note N7 and to count the businesses; it gets no field, because `CompanyReport` has no place for "which of several registrations this is" and inventing one from a single country is how a contract rots. If a caller needs it structurally, that is a decision with evidence |
| `juridiskForm` when `organisationsform` is present | §7.1. Never a second field, never `sector_code`, never translated |
| `organisationsnamnLista[].registreringsdatum` for non-primary names | Rendered inside note N12 where it helps; not a field |
| `organisationsnamnLista[].verksamhetsbeskrivningSarskiltForetagsnamn` | The activity description attached to a *särskilt företagsnamn*. Rendered in N12; `activity` carries the organisation-level `verksamhetsbeskrivning` only, because mixing them would attribute one business's activity to another (§2.2) |
| `dataproducent` | Read on every field to decide the §7.1 fallback and to write the SCB-naming notes. Not a field of its own — `CompanyReport` has one `source`, and a per-field provenance map is D-026(c)'s `SourceRef` territory, not something to invent here |
| `fel.felBeskrivning` | Swedish prose from an upstream error. Its *presence* drives N13 and the cache rule; its text is not forwarded (D-007, the GB ruling on `request_id`) |
| `ApiError.requestId` / `timestamp` / `instance` / `type` | Bolagsverket's own support handle and a non-deterministic timestamp. Never in `details` (§6.3) |
| `/isalive` | A health endpoint for the operator, not for a read-only lookup. Not called |
| `/dokumentlista`, `/dokument` | `DEFERRED` (§5.5) |
| The misspelled `pagandeAvvecklings…` key | **Not "not mapped" — read as a fallback.** The schema spelling is `pagaende…` and the Altinn team confirm the wire uses it, but Bolagsverket's own aktiebolag example uses the misspelling, so a fixture built from it carries the wrong key. Both spellings are read, for one reason only: if the wire ever sends the misspelled key and we read only the correct one, the module reports **a bankrupt company as active**. Two lines against the worst output this product can produce. §14 test 98 pins it |

---

## 16. What T26b owns

`src/registry_mcp/registries/se/{__init__,client,mapping,rules}.py`, the one import line in
`src/registry_mcp/registries/__init__.py` (alphabetical: `gb`, `no`, `se`, `xx`), `tests/`'s two new
files, and the eleven fixtures of §1.8 plus the new `tests/fixtures/README.md` section (§17).

**There is no `holidays.py`** (§5.2) and **no search scoring function** (§12).

It may also edit the suite tests that hard-code the country list — the same set T15b touched for GB —
and must add `SE` wherever `["GB", "NO"]` appears.

It may **not** edit `core/`, `api/` or `mcp/`. If a shape is wrong, that is a finding for the
orchestrator and Opus A decides. The three findings this spec already carries are in §0, and none of
them blocks the build.

---

## 17. Fixtures — recording the real ones

**Nothing under `tests/fixtures/bv_*.json` is a live recording.** Eleven fixtures are described in
§1.8: four are copied **verbatim** from Bolagsverket's own OpenAPI examples
(`bv_enskild_two.json`, `bv_uppgiftskalla_fel.json`, the `ApiError` bodies, `bv_token.json`), and the
rest are assembled from those examples' field names and nesting with different optional blocks
present. All of the assembled ones carry the `_VERIFY` header key of §1.8 and **must be re-recorded
in T26d**.

`tests/fixtures/README.md` gains an `## SE — Bolagsverket` section containing exactly this, with the
credentials as shell variables and **no credential values committed**:

```bash
# 1. Token (test environment). Production: portal.api.bolagsverket.se
ACCESS_TOKEN=$(curl -sS -X POST \
  https://portal-accept2.api.bolagsverket.se/oauth2/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode grant_type=client_credentials \
  --data-urlencode "client_id=$BOLAGSVERKET_CLIENT_ID" \
  --data-urlencode "client_secret=$BOLAGSVERKET_CLIENT_SECRET" \
  --data-urlencode 'scope=vardefulla-datamangder:read vardefulla-datamangder:ping' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

# 2. One organisation. Production base: gw.api.bolagsverket.se
curl -sS -X POST \
  https://gw-accept2.api.bolagsverket.se/vardefulla-datamangder/v1/organisationer \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -H "X-Request-Id: $(uuidgen)" \
  -d '{"identitetsbeteckning":"5560021361"}' | python3 -m json.tool
```

**Which number to record for which fixture** (test environment; the workbook's scenarios):

| Fixture | Number | Scenario |
|---|---|---|
| `bv_ab_active.json` | `5560021361` | Svar utan fel — Aktiebolag |
| `bv_enskild_two.json` | `198101052382` | Enskild firma, **två namnskyddslöpnummer** |
| *(a one-business sole trader)* | `198101032384` | Enskild firma |
| `bv_finns_ej.json` | `193403223328` | Organisation finns inte registrerad |
| `bv_scb_only.json` | `5567223705` | Aktiebolag, organisation finns ej hos SCB |
| *(handelsbolag)* | `9124001992` | Handelsbolag |
| *(bostadsrättsförening)* | `7164099017` | Bostadsrättsförening |
| *(ekonomisk förening)* | `7020008350` | Ekonomisk förening |
| *(dokumentlista, `DEFERRED`)* | `5561890038` | — |

**Do not record `5560000002`, `7140000001`, `9160000001` or `198210300002` as ordinary fixtures.**
They are the four §5.1.1 counter-examples; `5560000002` has a job of its own (§14 test 116) and the
others should be left alone until that experiment resolves.

The test environment only accepts numbers on its allowlist; another number returns a response
listing the permitted ones, which is itself worth saving the first time it happens.

Redaction: the recorded bodies contain **no credential**, but `bv_enskild_two.json` and any
sole-trader recording contain a **personnummer, a name and a home address of a real natural person**
— committed to a public MIT repository. Bolagsverket's test data is synthetic, so the test-environment
recordings are safe; **no production sole-trader payload may ever be committed as a fixture.** That
is D-039's rule applied to the repository rather than to the API response, and it is the one line in
this section that cannot be relaxed for convenience.
