# Fixtures

Recorded and assembled upstream payloads used by the test suite. Each country
section says which fixtures are real recordings and which are shape-only.

## SE — Bolagsverket

Of the 25 `bv_*.json` fixtures: **ten were recorded live against the
Bolagsverket TEST environment** — eight on 2026-09-07 (T26g, once
credentials arrived) and two on 2026-09-08 (R-5b, `/dokumentlista`);
**seven more are verbatim copies of Bolagsverket's own OpenAPI
document** (T26b, unchanged since); **eight are still assembled**, now
confirmed shape-correct but not scenario-correct (below). `SWEDEN_SPEC.md`
§1.8 and §17 carry the full per-fixture story; this file has the recording
recipe and the number-to-fixture table.

**Recorded live by T26g:** `bv_ab_active.json`, `bv_scb_only.json`,
`bv_finns_ej.json`, `bv_hb_active.json`, `bv_brf_active.json`,
`bv_ek_active.json`, `bv_enskild_avregistrerad.json`, `bv_enskild_three.json`.
Byte-for-byte what Bolagsverket returned, only reformatted to this project's
2-space indent.

**Verbatim from Bolagsverket's own OpenAPI document (T26b, still not a live
call):** `bv_enskild_two.json`, `bv_uppgiftskalla_fel.json`, the `ApiError`
bodies `bv_400.json`/`bv_401.json`/`bv_403.json`/`bv_500.json`, and
`bv_token.json`.

`bv_enskild_two.json` is **deliberately** not replaced by a live recording,
even though sole-trader credentials now exist: it is the one fixture that
demonstrates `organisationsidentitet.typ.kod == "PERSONNUMMER"` mapping to
`id_scheme == "personnummer"` — the row `SWEDEN_SPEC.md` §2.4 documents.
Every live TEST sole trader recorded by T26g (`193403223328`, `198101032384`,
`198101052382`) instead carries `typ.kod == "PERSON"`, a short code neither
§2.4's table nor `mapping._ID_SCHEME_BY_TYP_KOD`/`_PERSONAL_ID_TYP_KODS`
recognise — live `id_scheme` for a real sole trader is currently
`"organisationsnummer"`, not `"personnummer"` (the sole-trader personal-data
note still fires correctly, via the independent `legal_form.code == "E"`
check — this is a labelling gap, not a privacy one). **Live-confirmed,
reported by T26g and fixed in T33** — see `SWEDEN_SPEC.md` §1.8 and §2.4. Replacing
`bv_enskild_two.json` would have silently swapped the one fixture that tests
the *documented* mapping for one that only exposes the *undocumented* gap.

**Still assembled** (`bv_ab_dormant.json`, `bv_ab_konkurs.json`,
`bv_ab_kk_and_li.json`, `bv_ab_rekonstruktion.json`,
`bv_ab_fusion_overtagande.json`, `bv_ab_avregistrerad.json`): no company in
the Bolagsverket TEST register is currently in bankruptcy, liquidation,
reconstruction, a fusion, or (for `bv_ab_avregistrerad.json` specifically) a
deregistration shaped like the OpenAPI example — an `AB` with a
datetime-shaped date. (A real, deregistered sole trader does exist —
`bv_enskild_avregistrerad.json` — but it is a different legal form, a
plain-date `avregistreringsdatum`, and a different `avregistreringsorsak`,
so it does not stand in for this fixture's specific combination.) Their field
names and nesting are confirmed against Bolagsverket's OpenAPI *and* against
all eight live T26g recordings; only each fixture's particular *combination*
of states remains synthetic. They carry a top-level `_SYNTHETIC_COMBINATION`
header key — replacing the old `_VERIFY` — saying exactly that.
`map_entity` ignores any top-level key it doesn't read, same as before.
Re-record any of these the day a matching company appears in the test
register.

The recipe below is **confirmed working** — it is how the eight live
recordings above were made, against the TEST host, with credentials in the
form body. (Both that and HTTP Basic authentication work against
Bolagsverket's OAuth endpoint; this project ships form-body, per
`SWEDEN_SPEC.md` §1.2.) Set `BOLAGSVERKET_CLIENT_ID` and
`BOLAGSVERKET_CLIENT_SECRET` as shell variables first — never write a
credential value into this file, a fixture, or a commit.

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

`python3 -m json.tool`'s default indent is 4 spaces; this project's fixtures
use 2. Reformat before committing:

```bash
python3 -c 'import json, sys; print(json.dumps(json.load(sys.stdin), indent=2, ensure_ascii=False))' \
  < response.json > tests/fixtures/bv_whatever.json
```

**Which number is which fixture** (test environment; corrected 2026-09-07
against the live responses themselves — the workbook's own scenario labels
had `193403223328` and `198101032384` backwards, and called `198101052382`
"two namnskyddslöpnummer" when it is three; see `SWEDEN_SPEC.md` §17):

| Fixture | Number | Scenario |
|---|---|---|
| `bv_ab_active.json` | `5560021361` | Svar utan fel — Aktiebolag |
| `bv_scb_only.json` | `5567223705` | Aktiebolag, organisation finns ej hos SCB |
| `bv_finns_ej.json` | `198101032384` | Organisation finns inte registrerad. **Corrected**: the workbook said `193403223328` for this row; that number is not this scenario (below). |
| `bv_enskild_avregistrerad.json` | `193403223328` | Enskild firma, **deregistered**, two businesses. **Corrected**: the workbook called this number "not registered"; live, it is a real, struck-off sole trader that maps fine. |
| `bv_enskild_three.json` | `198101052382` | Enskild firma. **Corrected**: the workbook says "två namnskyddslöpnummer" (two); the live recording has **three**. |
| `bv_enskild_two.json` | *(none — Bolagsverket's own OpenAPI example, `194009272719`)* | Enskild firma, two namnskyddslöpnummer, `typ.kod == "PERSONNUMMER"`. Kept synthetic on purpose — see above. |
| `bv_hb_active.json` | `9124001992` | Handelsbolag |
| `bv_brf_active.json` | `7164099017` | Bostadsrättsförening |
| `bv_ek_active.json` | `7020008350` | Ekonomisk förening |
| `bv_dokumentlista.json` | `5561890038` | `POST /dokumentlista` — three filed annual reports. **Recorded live 2026-09-08** (R-5b); the number is confirmed, see below. |

**Do not record `5560000002`, `7140000001`, `9160000001` or `198210300002`**
as ordinary fixtures — they are the four modulus-10 counter-examples
(`SWEDEN_SPEC.md` §5.1.1); `5560000002` has a job of its own (§14 test 116)
and the others should be left alone until that experiment resolves.

The test environment only accepts numbers on its allowlist. **Corrected
2026-09-08 (R-5b):** an unlisted number does *not* return a response listing
the permitted ones — it returns a bare RFC 7807 400 whose `detail` merely
points at the workbook (*"Ogiltig identitetsbeteckning i begäran. Se
testdokumentation för giltiga identitetsbeteckningar."*), recorded as
`bv_dokumentlista_400.json`. The permitted numbers are only in the workbook.

### `POST /dokumentlista` — a second, disjoint allowlist (R-5b, 2026-09-08)

Four `bv_dokumentlista*.json` fixtures were added for the `filings` block
(`src/registry_mcp/registries/se/filings.py`, `DECISIONS.md` D-041). Two are
live recordings and two cannot be:

| Fixture | Origin |
|---|---|
| `bv_dokumentlista.json` | **Live**, `5561890038`, 2026-09-08 — three annual reports, periods ending 2022/2021/2020-12-31. |
| `bv_dokumentlista_400.json` | **Live**, the RFC 7807 body for a well-formed identifier the test environment does not hold. |
| `bv_dokumentlista_empty.json` | `_SYNTHETIC_COMBINATION` — `{"dokument": []}`. |
| `bv_dokumentlista_no_key.json` | `_SYNTHETIC_COMBINATION` — the `dokument` key absent, which the OpenAPI permits (it is not in `DokumentlistaSvar`'s `required` list). |

**Why the last two cannot be recorded.** `/dokumentlista` has its **own**
test-environment allowlist, and it is disjoint from `/organisationer`'s:
`5561890038` answers `/dokumentlista` with a 200 and `/organisationer` with a
**400**, while all eight companies with live `/organisationer` recordings
above — plus `5562820745`, `5560986878`, `5560004755`, `198101012386` — answer
`/dokumentlista` with a **400**. So no reachable test company has zero filed
annual reports, and no test company can produce a company record *and* a
document list, which is why no live test can compare the two blocks'
independent provenance. Re-check with
`test_145_live_dokumentlista_allowlist_is_disjoint_from_organisationer`; if it
ever fails, the test register has gained a second `/dokumentlista` company.

**Two different `detail` strings, one status.** A bad check digit
(`5560000000`) returns the OpenAPI's own documented example verbatim —
*"Identitetsbeteckning har ogiltig kontrollsiffra."*, the body already
committed as `bv_400.json` — so that example is **not** a fabrication; only
its attachment to `GET /dokument/{dokumentId}`, which takes no identifier, is
a documentation bug. A valid-but-unheld identifier returns a second,
undocumented string (`bv_dokumentlista_400.json`). Live bodies also carry
`"timestamp": null` where the OpenAPI example has a real timestamp. Never code
to `detail` (D-041(h)); the HTTP status is the only behaviour.

**The 200 has no `dataproducent`/`fel` wrapper** — it is exactly
`{"dokument": [...]}`. `SWEDEN_SPEC.md` §1.6's "every field is a wrapper,
therefore HTTP 200 ≠ data arrived" is an `/organisationer` rule and must not be
pointed at this response.

Recipe (step 1's token as above):

```bash
curl -sS -X POST \
  https://gw-accept2.api.bolagsverket.se/vardefulla-datamangder/v1/dokumentlista \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -H "X-Request-Id: $(uuidgen)" \
  -d '{"identitetsbeteckning":"5561890038"}' | python3 -m json.tool
```

**Redaction:** the recorded bodies contain no credential, but
`bv_enskild_two.json`, `bv_enskild_avregistrerad.json`, `bv_enskild_three.json`
and `bv_finns_ej.json` each contain a **personnummer and a name** —
`bv_enskild_avregistrerad.json` also a real-looking home address — of a
natural person. Bolagsverket's own placeholder names on most of these make
the data's synthetic origin obvious ("Snö i april", "Sol i maj",
"Testbolag_91"); `bv_enskild_avregistrerad.json`'s "Blekinge Mäklarbyrå
Birgitta Andersson..." reads like a real business owner but is Bolagsverket's
own TEST-environment data, the same as the already-committed
`bv_enskild_two.json`'s "CITY SKOR THOMAS CARLSON". Bolagsverket's test data
is synthetic, so the test-environment recordings are safe; **no production
sole-trader payload may ever be committed as a fixture.**

## NO — Brønnøysundregistrene

Two datasets on one host, and they are separate fixtures with separate shapes.

### Enhetsregisteret — `brreg_*.json`

`brreg_923609016.json`, `brreg_974760673.json` and `brreg_833285602.json` are
`GET /enhetsregisteret/api/enheter/{orgnr}` recordings (T01/T03). Unchanged by
R-5d. **`833285602` and `833286602` are not to be looked up again** — the
committed fixture is sufficient for every test that needs a sole trader's
shape, and re-fetching one adds a live request about a natural person for no
benefit.

### Regnskapsregisteret — `brreg_regnskap_*.json` (R-5d + T38/D-043, recorded live 2026-09-08)

Four fixtures were recorded for the `filings` block (`src/registry_mcp/registries/no/accounts.py`,
`DECISIONS.md` D-042(i), closing D-023(d)); five more were added by T38
(D-043, `include=["financials"]`) — reusing the same four, since `filings`
and `financials` read the same payload. **All nine are live recordings** —
this endpoint is open, keyless and needs no credential and no test
environment, so nothing here is assembled and nothing needs to be.

| Fixture | Number | Scenario |
|---|---|---|
| `brreg_regnskap_923609016.json` | `923609016` | EQUINOR ASA — a **calendar** accounting year, 2025-01-01/2025-12-31. Pairs with `brreg_923609016.json`, the same entity's Enhetsregisteret record, so a test can hold both halves of one company. T38: `valuta: "USD"`, `forenkletAnvendelseIFRS`, and assets/equity-and-liabilities differ by 10⁶ (103,432,000,000 vs 103,431,000,000). |
| `brreg_regnskap_939319891.json` | `939319891` | ORACLE NORGE AS — a **deviating** accounting year, 2024-06-01/2025-05-31. The period end falls between 1 January and 30 June, i.e. regnskapsloven § 8-3(1) second sentence's **1 February** branch. This is the fixture that closes D-023(d)'s "the field's *variance* is unverified". |
| `brreg_regnskap_935845114.json` | `935845114` | .BEIN BERGEN AS — a **stub first period**, 2025-06-19/2025-12-31, running from incorporation. The live proof that `fraDato` is published data and not `tilDato` minus twelve months. |
| `brreg_regnskap_500.json` | `916823525` | APRILA BANK ASA — the **deterministic 500**. Banks, insurers and many foundations return this on every attempt while their Enhetsregisteret record says they filed. The body is a Spring error envelope with a `trace` id; it is recorded for its *shape*, and the `trace` and `timestamp` in it are from the recording moment and mean nothing to a test. |
| `brreg_regnskap_931883836.json` | `931883836` | 222 HOLDING AS — T38: negative `sumGjeld` (−108,837), carried unchanged; `langsiktigGjeld: {}` and `finansinntekt: {}`; `totalresultat` present. `sumEgenkapitalGjeld` and `sumEiendeler` are both exactly 27,949 (no reconciliation gap) even though `sumEgenkapital` (136,786) exceeds them both — the negative liability is what keeps the totals internally consistent. |
| `brreg_regnskap_936134610.json` | `936134610` | 4WD HOLDING AS — T38: `driftsinntekter: {}` (no turnover line at all) beside a present `driftsresultat` and `sumDriftskostnad` — maps to `revenue is None`. Pairs with the fixture below to pin D-043(f)'s "an absent line is not a zero". |
| `brreg_regnskap_921378963.json` | `921378963` | 4U HOLDING AS — T38: explicit `sumDriftsinntekter: 0.0` — maps to `revenue == 0.0`, the other half of the pair above. |
| `brreg_regnskap_925922900.json` | `925922900` | 22 INVEST AS — T38: `fravalgRevisjon: true`, `smaaForetak: true`, negative equity (`sumEgenkapital: -2,743`). |
| `brreg_regnskap_998575133.json` | `998575133` | AGATON SAX MT AS — T38: `avviklingsregnskap: true`, a final stub period 2026-01-01/2026-04-30. |

**No fixture for the empty case, and that is deliberate.** The empty answer is
an HTTP 404 with `content-length: 0` and **no body at all** — there is nothing
to record. It is also *indistinguishable from a nonexistent
organisasjonsnummer*: `974760673` (REGISTERENHETEN I BRØNNØYSUND, which
exists — its `/enheter` record is committed here) and `936295592` (ASP DC ASA,
incorporated 2025-10-02) 404 exactly as `999999999` and `123456785` do, which
are MOD11-valid and were never issued. Tests mock the bare 404;
`registries/no/client.py::fetch_accounts` maps it to a present, empty block
and never to `not_found` (D-041(h)).

**Personal data: none, and it was checked rather than assumed.** Every string
-valued path in this payload and its complete value domain was enumerated
across ~600 live responses spanning `AS`, `ASA`, `SA`, `STI`, `BRL`, `ANS`,
`DA` and `NUF`; eight remain and every one is a number, a code or a date. In
particular `revisjon` carries two booleans (`ikkeRevidertAarsregnskap`,
`fravalgRevisjon`) and names no auditor, and `virksomhet` names no proprietor
or signatory. **All 100 sampled `ENK` entities returned 404**, so no
sole-trader payload exists on this endpoint to record — the rule that no
production sole-trader payload may be committed is met by the register itself.

Recipe — no token, no allowlist, no test environment:

```bash
curl -sS -H 'Accept: application/json' \
  -H "User-Agent: registry-mcp/0.3.0 (+https://github.com/foretak/registry-mcp; $REGISTRY_MCP_CONTACT_EMAIL)" \
  https://data.brreg.no/regnskapsregisteret/regnskap/923609016 \
  | python3 -c 'import json, sys; print(json.dumps(json.load(sys.stdin), indent=2, ensure_ascii=False))' \
  > tests/fixtures/brreg_regnskap_923609016.json
```

The response is a **bare JSON array**, not an envelope — so these fixtures are
lists where every other fixture in this directory is an object, and
`tests/test_client_no.py` loads them through `_load_accounts_fixture` rather
than `_load_fixture`. The endpoint takes **no arguments**: `?år=`, `?aar=`,
`?year=`, `?regnskapstype=`, `?size=` and `?historikk=` are all accepted and
all ignored (byte-identical bodies), `/regnskap/{orgnr}/{year}` 404s, and
`OPTIONS` answers `allow: GET,HEAD,OPTIONS`. It returns the most recently
filed period and nothing earlier, so there is no multi-year fixture to record.

## GB — Companies House filing history (`ch_*_filing_history*.json`)

Eight fixtures, all recorded live against
`https://api.company-information.service.gov.uk` on 2026-09-08 with the free
operator key (never written to a file, a fixture or a commit), for R-5c / T37
and `src/registry_mcp/registries/gb/filing_history.py`.

**These eight are the only fixtures in this directory that were deliberately
altered at record time, and the reason is a privacy ruling rather than a
convenience.** `DECISIONS.md` **D-042(e)(1)** reads
`items[].description_values` through an allow-list of **exactly one key,
`made_up_date`**: Companies House resolves its description templates from
that object, 97 of the templates interpolate `{officer_name}` and 26
interpolate `{psc_name}`, so a byte-verbatim recording of this endpoint is an
officers feed that D-028 bars. Every non-allow-listed key was therefore
dropped from every `description_values` object — top-level and inside
`annotations[]`, `resolutions[]` and `associated_filings[]` — **before the
file was written**, and the registrar free prose in `annotations[].annotation`
was replaced by a fixed placeholder for the same reason. **No natural
person's name has ever been in this repository.**

Each file carries a top-level `_MINIMISED` header recording the request URL,
the fetch date, why that company was chosen, the allow-list, and the **names
and counts** of the keys that were stripped — key names are not personal data
and they are the evidence the allow-list was applied against what the register
actually sends. `map_filing_history` ignores any top-level key it does not
read, so the header costs nothing, exactly as SE's `_SYNTHETIC_COMBINATION`
does.

Recon behind the choice of companies — 1876 items across nine companies, with
every observed `description_values` key and its count — is in
`registries/gb/filing_history.py`'s module docstring. The three worst keys
found live are `description` (585 items: the `legacy` free-prose slot, which
reads `"Director appointed mr <full name>"` on four of 512 legacy rows),
`officer_name` (445) and `representative_details` (2 — a natural person's name
*and* their address in one string, which the research's 97/26 count does not
mention at all).

| Fixture | Request | Why |
|---|---|---|
| `ch_00445790_filing_history.json` | `00445790`, page 1 of 25 | TESCO PLC — 25 of **8371**: the truncation case, plus `annotations`/`resolutions` sub-objects and a 52/53-week year end |
| `ch_00000006_filing_history.json` | `00000006`, page 1 of 25 | 25 of 206 — officers-heavy (14 `officer_name` on the wire); holds the AP01 the officer-appointment minimisation test pins |
| `ch_00000006_filing_history_legacy.json` | `00000006`, `start_index=100` | **A deep page**, recorded only because `legacy` rows appear nowhere near the top of a history. Not the page the client fetches |
| `ch_04374209_filing_history.json` | `04374209`, page 1 of 25 | 25 of 101 — in liquidation: an `insolvency` category row, `psc_name`, nine `made_up_date` |
| `ch_13507518_filing_history.json` | `13507518`, page 1 of 25 | 14 of 14 — complete and untruncated; the newest reporting period is a *confirmation statement*, which is why `financial_year_end` reads annual accounts only |
| `ch_FC032315_filing_history.json` | `FC032315`, page 1 of 25 | 6 of 6 — an overseas company, the only observed carrier of `representative_details` |
| `ch_BR026263_filing_history.json` | `BR026263`, page 1 of 25 | `total_count: 0` with `filing_history_status: "filing-history-available"` — the register holds none |
| `ch_CE020555_filing_history.json` | `CE020555`, page 1 of 25 | `total_count: 0` with `filing_history_status: "filing-history-not-available-unknown-prefix"` — the register **cannot answer**. The D-011 pair to the row above, and the reason `FilingHistory.total_count` is `None` rather than `0` there |

Recording recipe — set `COMPANIES_HOUSE_API_KEY` as a shell variable first,
and never write the value into this file, a fixture or a commit. **The
minimisation below is not optional**: recording the raw body, even briefly,
puts personal data in the working tree.

```bash
python3 - "$COMPANIES_HOUSE_API_KEY" <<'PY'
import base64, json, sys, urllib.request
ALLOW = {"made_up_date"}                      # DECISIONS.md D-042(e)(1)
NUMBER, PAGE = "00000006", 25
url = (f"https://api.company-information.service.gov.uk/company/{NUMBER}"
       f"/filing-history?items_per_page={PAGE}")
auth = base64.b64encode(f"{sys.argv[1]}:".encode()).decode()
req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}",
                                           "Accept": "application/json"})
body = json.load(urllib.request.urlopen(req))
def strip(obj):                                # top-level and every sub-object
    dv = obj.get("description_values")
    if isinstance(dv, dict):
        obj["description_values"] = {k: v for k, v in dv.items() if k in ALLOW}
for item in body.get("items") or []:
    strip(item)
    for field in ("annotations", "resolutions", "associated_filings"):
        for sub in item.get(field) or []:
            strip(sub)
            if "annotation" in sub:
                sub["annotation"] = "<registrar free prose removed at record time>"
print(json.dumps(body, indent=2, ensure_ascii=False))
PY
```

Add the `_MINIMISED` header by hand (copy one from an existing file and
update the counts), or the next reader will not know the file was altered.

## GB — Companies House insolvency (`ch_*_insolvency.json`, `ch_insolvency_*.json`)

Nine fixtures for R-5e and `src/registry_mcp/registries/gb/insolvency.py`
(`DECISIONS.md` D-042(i)). **Seven are live recordings, one is a live 404
body, and one is fabricated.** Recorded 2026-09-08 against
`https://api.company-information.service.gov.uk` with the free operator key
(never written to a file, a fixture or a commit).

**Practitioners are removed from every live recording, and that is the point
of this whole block.** `cases[].practitioners[]` carries a licensed insolvency
practitioner's **full name and postal address** — D-042(e) calls this endpoint
"the most person-bearing of the four" it examined, and **D-042(e)(2) rules
that practitioners are not relayed at all in the first tranche**. So the key
was removed from every case **before** each file was written. `map_insolvency`
never reads it either, and `registries/gb/client.py::fetch_insolvency` strips
it before `cache.set`, so no practitioner particular reaches the mapped
output, this deployment's disk, a log line, or this directory. **No natural
person's name from this endpoint has ever been in this repository.**

Each live file carries one of two top-level headers, and they mean different
things:

* **`_PRACTITIONERS_STRIPPED`** — the live payload carried practitioner
  entries and they were removed. The header records the request URL, the
  fetch date, how many entries were removed and from how many cases. The key
  is **removed, not emptied**, so a stripped file can never be mistaken for
  one of the payloads that genuinely carries `"practitioners": []`.
* **`_PRACTITIONERS_NONE`** — nothing was stripped, because the live payload
  had none to strip. `ch_SC001381_insolvency.json` is Companies House's own
  `"practitioners": []` (79 of 1,485 live cases are like it) and
  `ch_00712615_insolvency.json` has no case at all. These two are
  **byte-for-byte** what the register returned.

`map_insolvency` ignores any top-level key it does not read, so the headers
cost nothing — exactly as SE's `_SYNTHETIC_COMBINATION` and GB filing
history's `_MINIMISED` do.

**The recon behind the choices is in
`registries/gb/insolvency.py`'s module docstring**: 1,458 company numbers
sampled from Companies House's own `/advanced-search/companies` across eleven
`company_status` buckets, giving 1,105 HTTP 200s over 1,485 cases and 2,607
practitioner entries, plus 353 HTTP 404s. Two findings decide the fixture
list. First, **a solvent company 404s** — unlike `/charges`, which never does
— and the 404 body is indistinguishable from the one for a company number
that was never issued, so `ch_insolvency_404.json` exists to pin that a 404 is
a present, empty block and never `not_found`. Second, **there are two
different empty answers** (404, and 200 with `"cases": []`) and D-011 forbids
collapsing them, so both are recorded.

| Fixture | Request | Why |
|---|---|---|
| `ch_04374209_insolvency.json` | `04374209` | One `compulsory-liquidation` case with `petitioned-on` + `wound-up-on`, `status: ["liquidation"]`. Pairs with `ch_04374209.json`, the same company's profile, so a test can hold both halves. 1 practitioner stripped |
| `ch_NI031727_insolvency.json` | `NI031727` | `in-administration` + `corporate-voluntary-arrangement`, `status: ["in-administration"]` — the two commonest rescue procedures in one small payload. 2 stripped |
| `ch_SC432231_insolvency.json` | `SC432231` | `corporate-voluntary-arrangement-moratorium` (1 of 1,485 live cases) + `compulsory-liquidation`; `notes: ["scottish-insolvency-info"]` on both; and **no root `status` key at all** — 125 of 1,105 live 200s have none. 3 stripped |
| `ch_05607779_insolvency.json` | `05607779` | `moratorium` (the other 1-in-1,485 type) + `corporate-voluntary-arrangement`, with `moratorium-started-on`. 4 stripped |
| `ch_01034351_insolvency.json` | `01034351` | Three cases, three types (`administrative-receiver`, `receiver-manager`, `creditors-voluntary-liquidation`), numbered 1/2/3 but dated 1990/1984/1992 — the proof the register's own order is not chronological. Also the only recording that keeps two `links.charge` values. 6 stripped |
| `ch_SC001381_insolvency.json` | `SC001381` | `members-voluntary-liquidation` — a **solvent** winding-up, which is why `is_liquidation: true` must not be read as "insolvent". Byte-for-byte: a live `"practitioners": []`, and no `etag` (135 of 1,105 live 200s have none) |
| `ch_00712615_insolvency.json` | `00712615` | HTTP **200** with `"cases": []` — the register holds a record and publishes nothing in it, while the company's own profile says `company_status: "liquidation"` and `has_insolvency_history: true`. Byte-for-byte |
| `ch_insolvency_404.json` | `00445790` | The **404 body**, from Tesco PLC — active, trading, no insolvency history. Identical (bar `path`) to the body for `99999999` and `12345678`, which were never issued, and for the dissolved `00000006`. A 404 here says nothing about whether the company exists |
| `ch_insolvency_practitioners_synthetic.json` | *(none — fabricated)* | `_SYNTHETIC_COMBINATION`. **The only fixture in this directory that carries a `practitioners` array**, and every name and address in it is invented ("Nonexistent Practitioner-One" at "Fabricated House", postcode `ZZ99 9ZZ`). It exists so a test can feed the mapper the exact thing D-042(e)(2) bars and prove nothing survives. It also carries `administration-order` — the one live-observed case type no real recording here happens to hold — and an invented note code, so the allow-list can be tested. **Never replace it with a live payload** |

`test_live_insolvency_fixtures_still_match_stored_files` re-fetches all seven
recordings and diffs the mapped block against the stored one. Because the live
payload carries practitioners and the stored one does not, that test passing
is also a standing proof that everything removed was unreachable.

Recording recipe — set `COMPANIES_HOUSE_API_KEY` as a shell variable first,
and never write the value into this file, a fixture or a commit. **The
stripping is not optional**: writing the raw body, even briefly, puts a
natural person's name and address in the working tree.

```bash
python3 - "$COMPANIES_HOUSE_API_KEY" <<'PY'
import base64, json, sys, urllib.request
NUMBER = "04374209"
url = f"https://api.company-information.service.gov.uk/company/{NUMBER}/insolvency"
auth = base64.b64encode(f"{sys.argv[1]}:".encode()).decode()
req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}",
                                           "Accept": "application/json"})
body = json.load(urllib.request.urlopen(req))       # 404 => a solvent company
removed = sum(len(c.get("practitioners") or []) for c in body.get("cases", []))
for case in body.get("cases", []):
    case.pop("practitioners", None)                 # REMOVE the key, never empty it
assert '"name"' not in json.dumps(body)
print(removed, "practitioner entries removed", file=sys.stderr)
print(json.dumps(body, indent=2, ensure_ascii=False))
PY
```

Add the `_PRACTITIONERS_STRIPPED` header by hand (copy one from an existing
file and update the counts), or the next reader will not know the file was
altered — and use `_PRACTITIONERS_NONE` instead if `removed` was 0, so a
byte-for-byte recording is never labelled as a redacted one.

**Do not use this endpoint to look up a specific individual.** It is reachable
only from a company number and must stay that way (D-028(1)); the sampling
that produced the recon above went company → cases and never the other way.

## GLEIF (`gleif_*.json`)

Six fixtures for `include=["lei"]` (`DECISIONS.md` D-026(c), D-045(e),
`core/gleif.py`). All recorded live and keyless from
`https://api.gleif.org/api/v1/lei-records` on 2026-09-08 — no personal data
of any kind is in scope for this upstream (GLEIF publishes corporate entity
records under CC0 1.0), so unlike the Companies House insolvency fixtures
above, nothing here is stripped: every file is byte-for-byte what GLEIF
returned for the query named below.

| Fixture | jurisdiction | registeredAs | Why |
|---|---|---|---|
| `gleif_923609016.json` | `NO` | `923 609 016` | Norway's space-grouped form — a bare-digit query for the same entity returns zero hits, which is the trap this attachment exists to avoid |
| `gleif_00445790.json` | `GB` | `00445790` | Tesco PLC — Britain does not group its own identifier, so the normalised id is queried as-is |
| `gleif_SC090312.json` | `GB` | `SC090312` | NatWest Markets plc — a Scottish registration, on a different Companies House registration-authority code from an England-and-Wales one |
| `gleif_556016-0680.json` | `SE` | `556016-0680` | Sweden's hyphenated form. Recorded for the mapper only — `SE` does not declare `lei` (its identifier can be a sole trader's personnummer, D-039), so no live `SE` lookup ever reaches this query |
| `gleif_03782379.json` | `GB` | `03782379` | Carillion plc — GLEIF's own `entity.status` reads `ACTIVE` while its `registration.status` reads `LAPSED`, which is why `LeiRecord.registration_status` carries the latter and not the former |
| `gleif_empty.json` | `GB` | `00223668` | `meta.pagination.total: 0` — the present-block-with-`lei: null` case |

Recording recipe (no credential needed; the brackets in the filter names
must be percent-encoded, or a shell/curl will glob them and produce a
confusing empty result that is a probing artefact, not a GLEIF behaviour):

```bash
python3 - <<'PY'
import json, urllib.parse, urllib.request

params = {"filter[entity.jurisdiction]": "NO", "filter[entity.registeredAs]": "923 609 016"}
url = "https://api.gleif.org/api/v1/lei-records?" + urllib.parse.urlencode(params)
with urllib.request.urlopen(url) as resp:
    body = json.load(resp)
print(json.dumps(body, indent=2, ensure_ascii=False))
PY
```
