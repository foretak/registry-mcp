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
