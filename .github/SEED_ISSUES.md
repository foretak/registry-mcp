# Seeded issues

Three issues to file by hand on the day the repo goes public, each labelled
`good first issue`. They are written to be *actually* good first issues: a
clear boundary, a named file, a done-check, and no need to understand the whole
codebase to finish one.

**How to file them** (the label must exist first — GitHub creates
`good first issue` by default on new repos, so usually it already does):

```bash
gh label create "good first issue" --color 7057ff --description "Good for newcomers" --force
gh label create "new country"      --color 0e8a16 --description "A new national registry module" --force
gh label create "norway"           --color 1d76db --description "The NO module" --force

# then, for each section below:
gh issue create --title "<title>" --label "good first issue,<extra>" --body-file <(…)
```

Copy each block below verbatim into the issue body.

---

## Issue 1 — Add roles / board lookup for Norway (`company_roles`)

**Labels:** `good first issue`, `norway`, `enhancement`

### Title

```
Add a company_roles tool: CEO and board from Enhetsregisteret
```

### Body

```markdown
Enhetsregisteret publishes an entity's roles — daglig leder (CEO), the board,
signature and procuration rights — at a second endpoint we do not read yet:

    GET https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}/roller

Verified live on 2026-09-04 for 923609016 (Equinor ASA): returns 200 with
`rollegrupper[]`, each with `type.kode` (`DAGL`, `STYR`, …), `sistEndret`, and
`roller[]` carrying either a `person` (`fodselsdato`, `navn.{fornavn,etternavn}`,
`erDoed`) or an `enhet` for corporate role-holders, plus `avregistrert` and
`rekkefolge`.

"Who signs for this company?" is one of the two or three questions people ask
about a company registry, and today we cannot answer it.

## What to build

1. A country-neutral `RoleHolder` / `RoleGroup` pair in `core/models.py` and an
   optional `Registry.roles(id) -> RoleReport` hook — **optional**, defaulting to
   `RegistryError(NOT_IMPLEMENTED, ...)`, so no other country module has to
   change (`DECISIONS.md` D-008). Person names are the only personal data
   involved; carry `birth_date` only if we decide we need it — say what you
   chose and why in the PR.
2. Implement it in `registries/no/client.py` + `mapping.py`, mapping the
   Norwegian role codes to English labels the way `legal_form` already is.
   Reuse the existing cache and User-Agent contract; do not write a new client.
3. Surface it as REST `GET /v1/{country}/company/{id}/roles` and MCP
   `company_roles`, both returning the same document (D-004).
4. Tests from a recorded fixture under `tests/fixtures/`, plus one `@pytest.mark.live`
   test. Include a role group whose holder is a company, not a person, and one
   with `avregistrert: true`.

## Not in scope

Sub-unit roles, historical roles, and the separate `/roller` search API.

## Done when

`curl localhost:8080/v1/NO/company/923609016/roles` names the CEO and the board,
the MCP tool returns the identical JSON, `uv run pytest && uv run mypy .` pass,
and nothing outside `core/models.py`, `core/registry.py`, `registries/no/`,
`api/` and `mcp/` changed.

**Start here:** `src/registry_mcp/registries/no/mapping.py` — the existing
`CompanyReport` mapping is the pattern to copy.
```

---

## Issue 2 — Denmark (CVR): a real stub to build on

**Labels:** `good first issue`, `new country`, `help wanted`

### Title

```
Denmark (DK): scaffold the CVR module — validate_id and list_countries first
```

### Body

```markdown
Denmark is the easiest second country: CVR (Det Centrale Virksomhedsregister,
Erhvervsstyrelsen) is open data, the identifier is 8 digits with a modulus-11
check, and it is close enough to Norway that anything that *doesn't* fit is a
useful signal about `core/` — which is exactly what we want to learn before a
third country (`DECISIONS.md` D-008, build plan Step 12).

This issue is deliberately **only the first half**: identifier validation and
registration, no network calls. That is a self-contained afternoon, and it makes
the second half (lookup + search + deadlines) a much smaller PR for you or for
whoever picks it up next.

## What to build

1. `cp -r src/registry_mcp/registries/xx src/registry_mcp/registries/dk`.
2. Set `country = "DK"`, `registry = "cvr"`, `id_scheme = "cvr-nummer"`,
   `id_example`, `id_description`, `source_url`, `license`, and the register's
   name in Danish and English. Keep **`is_stub = True`** for this PR.
3. Implement `validate_id`: strip spaces, dots and a leading `DK`, require 8
   digits, check the modulus-11 weights `2,7,6,5,4,3,2` with the last digit as
   the check digit. Raise `RegistryError(ErrorCode.INVALID_ID, …, hint=…)` with a
   hint that names the next call.
4. `lookup`, `search` and `deadlines` keep raising `NOT_IMPLEMENTED` — with a
   hint that says Denmark is scaffolded but not yet live, not the template's text.
5. Add the one import line to `registries/__init__.py`.
6. A numbered rules test list in the style of `NORBIZ_SPEC.md` §5: valid CVR,
   wrong check digit, wrong length, `DK`-prefixed, spaced, non-numeric, empty.

## Done when

`REGISTRY_MCP_INCLUDE_STUBS=1 uv run pytest` shows DK in `list_countries()`,
`validate_company_id("13585628", country="DK")` returns `valid: true` and a
wrong check digit returns `valid: false` with a usable hint, and **nothing
outside `registries/dk/` changed except the one import line**. If you had to
touch `core/`, stop and say so in the PR — that is the interesting finding.

**Start here:** the six steps in `src/registry_mcp/registries/xx/__init__.py`'s
module docstring, and `registries/no/rules.py` for the MOD11 pattern.
```

---

## Issue 3 — Check the MVA register directly instead of trusting one flag

**Labels:** `good first issue`, `norway`, `enhancement`

### Title

```
VAT: verify registrertIMvaregisteret against the Merverdiavgiftsregisteret record
```

### Body

```markdown
`vat_registered` today is a single boolean copied straight from Enhetsregisteret's
`registrertIMvaregisteret` field (`registries/no/mapping.py:210`), and
`registers["mvaregisteret"]` reads the same field
(`registries/no/mapping.py:89`). "Is this supplier VAT-registered?" is the
question people ask us before paying an invoice, so it is worth more than one
copied flag:

- Enhetsregisteret's copy of the MVA flag can lag the register it mirrors.
- We report `vat_registered_at` but never verify the entity is registered *now*.
- A deregistered entity that was once VAT-registered is exactly the case where
  being wrong costs someone money.

## What to build

1. Work out — and **write down in the PR** — what Brønnøysundregistrene and
   Skatteetaten actually publish about Merverdiavgiftsregisteret today: which
   endpoint, what it returns, whether it is open, and how fresh it is. This
   research is most of the value of the issue; if the honest answer is "there is
   no better source than the flag we already read", that is a fine outcome —
   document it and close with a `notes` entry instead of code.
2. If a better source exists: read it in `registries/no/client.py`, behind the
   same cache and User-Agent contract, and only when the caller asks —
   `lookup_company` must not get slower by default.
3. Whatever you find, make `CompanyReport` say it honestly. `vat_registered`
   must stay `null` when we do not know, and any disagreement between sources
   belongs in `notes`, not silently resolved in favour of one of them.

## Not in scope

The EU VIES VAT number validation service. Norway is not in the EU and its VAT
numbers are not in VIES; that is a separate issue if anyone wants it.

## Done when

`lookup_company("923609016")` still reports `vat_registered: true` and
`vat_number: "NO923609016MVA"`, an entity whose sources disagree carries a note
saying so, the extra call is opt-in, and the PR contains a short written finding
about what the register actually publishes.

**Start here:** `src/registry_mcp/registries/no/mapping.py:89` and `:210`, and
`NORBIZ_SPEC.md` §6 for the client contract.
```
