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

### Regnskapsregisteret — `brreg_regnskap_*.json` (R-5d, recorded live 2026-09-08)

Four fixtures for the `filings` block (`src/registry_mcp/registries/no/accounts.py`,
`DECISIONS.md` D-042(i), closing D-023(d)). **All four are live recordings** —
this endpoint is open, keyless and needs no credential and no test
environment, so nothing here is assembled and nothing needs to be.

| Fixture | Number | Scenario |
|---|---|---|
| `brreg_regnskap_923609016.json` | `923609016` | EQUINOR ASA — a **calendar** accounting year, 2025-01-01/2025-12-31. Pairs with `brreg_923609016.json`, the same entity's Enhetsregisteret record, so a test can hold both halves of one company. |
| `brreg_regnskap_939319891.json` | `939319891` | ORACLE NORGE AS — a **deviating** accounting year, 2024-06-01/2025-05-31. The period end falls between 1 January and 30 June, i.e. regnskapsloven § 8-3(1) second sentence's **1 February** branch. This is the fixture that closes D-023(d)'s "the field's *variance* is unverified". |
| `brreg_regnskap_935845114.json` | `935845114` | .BEIN BERGEN AS — a **stub first period**, 2025-06-19/2025-12-31, running from incorporation. The live proof that `fraDato` is published data and not `tilDato` minus twelve months. |
| `brreg_regnskap_500.json` | `916823525` | APRILA BANK ASA — the **deterministic 500**. Banks, insurers and many foundations return this on every attempt while their Enhetsregisteret record says they filed. The body is a Spring error envelope with a `trace` id; it is recorded for its *shape*, and the `trace` and `timestamp` in it are from the recording moment and mean nothing to a test. |

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
