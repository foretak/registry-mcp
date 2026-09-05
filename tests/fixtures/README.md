# Fixtures

Recorded and assembled upstream payloads used by the test suite. Each country
section says which fixtures are real recordings and which are shape-only.

## SE — Bolagsverket

**Nothing under `tests/fixtures/bv_*.json` is a live recording.** Sweden has
no Bolagsverket credentials as of T26b (`SWEDEN_SPEC.md` §1.8, §17). Four are
copied **verbatim** from Bolagsverket's own OpenAPI document
(`bv_enskild_two.json`, `bv_uppgiftskalla_fel.json`, the `ApiError` bodies
`bv_400.json`/`bv_401.json`/`bv_403.json`/`bv_500.json`, and `bv_token.json`);
the rest are assembled from those examples' field names and nesting with
different optional blocks present, and carry a top-level `_VERIFY` header key
that must be deleted once each is replaced by a real recording (T26d).

Record the real ones with:

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

Which number to record for which fixture (test environment; the workbook's
scenarios):

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

**Do not record `5560000002`, `7140000001`, `9160000001` or `198210300002`**
as ordinary fixtures — they are the four modulus-10 counter-examples
(`SWEDEN_SPEC.md` §5.1.1); `5560000002` has a job of its own (§14 test 116)
and the others should be left alone until that experiment resolves.

The test environment only accepts numbers on its allowlist; another number
returns a response listing the permitted ones, which is itself worth saving
the first time it happens.

**Redaction:** the recorded bodies contain no credential, but
`bv_enskild_two.json` and any sole-trader recording contain a **personnummer,
a name and a home address of a real natural person**, committed to a public
MIT repository. Bolagsverket's test data is synthetic, so the test-environment
recordings are safe; **no production sole-trader payload may ever be
committed as a fixture.**
