# CONNECTOR_SPEC

The implementation spec for `DECISIONS.md` **D-031** — the two ChatGPT connector aliases,
`search` and `fetch`. D-031 carries the ruling and the reasons; this file carries the exact
signatures, two worked JSON examples, the eval cases, and the README wording.

It is deliberately **not** in `CORE_ROADMAP_SPEC.md`: every item in that file changes `core/`
and is blocked by the feature freeze on that basis. **D-031 changes no `core/` file, adds no
model, adds no `Registry` method and alters no response shape** — it is a surface shim, and it
is the only outstanding decision that is not a core change.

Written by Opus A (architect) on 2026-09-05 under task T23a. Decisions and docs only — no code
was changed. `uv run pytest -m "not live"` before writing: **423 passed, 5 deselected, 0 failed**
(the stated baseline). Re-run after writing: **424 passed, 5 deselected, 0 failed** — the one
extra is T24's, landing concurrently in `tests/test_api.py` and `static/index.html`; this task's
footprint is four files and none of them is under `src/` or `tests/`: the `DECISIONS.md` append,
this file, one cross-reference paragraph in `CORE_ROADMAP_SPEC.md`, and two `PROGRESS.md` rows.
Owner of the implementation: **T23 (Sonnet 3)**.

---

## 1. Signatures

Both land in a new **`src/registry_mcp/mcp/connector.py`**, imported by `mcp/server.py` so the
`@mcp.tool` registrations run at import time beside the five. The module imports only
`core.models`, `core.registry` and `mcp.server`'s `_call_context` / `_tool_error`; it imports no
country module and contains no country string.

```python
@mcp.tool(
    output_schema=ConnectorSearchResponse.model_json_schema(),
    annotations={**_READ_EXTERNAL,
                 "title": "Find a company (ChatGPT connector alias for search_company)"},
)
async def search(
    query: Annotated[str, Field(
        description=("What to look for: a company name, a national identifier, or a name "
                     "plus a country, e.g. 'Equinor', '923609016', 'Tesco United Kingdom'."),
        examples=["Equinor", "923609016", "Tesco GB"],
    )],
) -> dict[str, Any]: ...


@mcp.tool(
    output_schema=ConnectorDocument.model_json_schema(),
    annotations={**_READ_EXTERNAL,
                 "title": "Fetch one company record (ChatGPT connector alias for lookup_company)"},
)
async def fetch(
    id: Annotated[str, Field(
        description=("An `id` from a `search` result: '{COUNTRY}:{identifier}', e.g. "
                     "'NO:923609016' or 'GB:00445790'."),
        examples=["NO:923609016", "GB:00445790"],
    )],
) -> dict[str, Any]: ...
```

The two descriptions are **verbatim in D-031(e)** and are not to be reworded in implementation:
their first sentence is the tool-search retrieval key and is deliberately spent de-prioritising
the alias.

Wire shapes, in `connector.py` — **not** `core/models.py`, and exempt from D-004 because the
field list is OpenAI's, not ours:

```python
class ConnectorSearchHit(_Base):     # OpenAI: id, title, url — no other key is read
    id: str
    title: str
    url: str

class ConnectorSearchResponse(_Base):
    results: list[ConnectorSearchHit] = []

class ConnectorDocument(_Base):
    id: str
    title: str
    text: str                        # Markdown rendering; see §2
    url: str
    metadata: dict[str, Any] = {}    # company_report, deadline_report, + flat scalars
```

Both tools return `model_dump(mode="json")`, exactly as the five do. FastMCP 4.0.2 derives
`structuredContent` **and** the JSON-encoded text-content mirror from that one value
(`mcp/server.py:180-187` records this), which is precisely the pair OpenAI requires —
**verify it on the wire once and record the result**, do not assume it.

### `search` algorithm

1. `query.strip()`; empty → `bad_request` (D-007), byte-identical to `search_company`'s.
2. **Country token.** For each `r in list_registries()`: match a whitespace token against
   `r.country` case-insensitively, or `r.country_info().name` as a case-insensitive substring
   of the query. On a match, that is the only country and the matched token is removed from the
   search string. No synonym table (D-031(c)) — a miss costs nothing, because step 4 fans out.
3. **Identifier?** For each candidate country, `r.validate(q)`; every country returning
   `valid: true` gets one `r.lookup(normalized)`. Each success is one row; `not_found` is
   silently no row. If any country validated, stop here.
4. **Name search.** `r.search(q, 10)` per candidate country, at most 5 concurrent (D-024(g)).
   A `RegistryError` from one country drops that country and does not raise.
5. Merge every candidate country's rows into **one** list — never grouped by registry — sort
   by `confidence` descending, cap at **10** rows.
   **Amended 2026-09-06** (live-deployment finding, reported against `search(query="Equinor")`):
   `confidence` ties are broken by an exact-name match before falling back to register order,
   and the cap was lowered from the original 20 to 10. The live call above returned
   `GB:11777091 — EQUINOR BLANDFORD ROAD LIMITED` first, ahead of `NO:923609016 — EQUINOR ASA`
   — both hits share the same D-005 anchor (0.8, "name starts with the query"; `EQUINOR ASA`
   is not a case-insensitive exact match to the bare query `"Equinor"`, so it does not reach
   0.95), and "ties keep register order" meant alphabetical-by-country-code, a signal with no
   relationship to relevance. The fix, in `mcp/connector.py::_merge_sort_and_cap`: normalise
   each hit's name (case-fold, strip punctuation, strip a *trailing* common legal-form suffix —
   `ASA`/`AS`/`LTD`/`LIMITED`/`PLC`/`LLP`) and the query the same way; a hit whose normalised
   name equals the normalised query ranks first among equal-`confidence` hits. `EQUINOR ASA`
   normalises to `"equinor"`, matching the query exactly; `EQUINOR BLANDFORD ROAD LIMITED`
   normalises to `"equinor blandford road"`, which does not. `confidence` itself is never
   recomputed or fabricated by this tie-break — only the merged list's order changes. Register
   order remains the last-resort, stable tie-break for any hits still equal after that. The cap
   dropped to 10 in the same change, matching `search_company`'s own default `limit`, so a
   deep-research turn is not left to sift through twenty mixed rows.
6. **Zero rows** → one `rules:{COUNTRY}` row per live country (D-031(c)).

### Row construction

| Field | Value |
|---|---|
| `id` | `f"{hit.country}:{hit.id}"` |
| `title` | `f"{hit.name} — {hit.country} {hit.id}"`, then `" — "` + `", ".join` of `legal_form` and `status.value` (omitting either if unknown), then `" — sub-unit"` when `is_subunit` |
| `url` | `f"{PUBLIC_BASE_URL}/v1/{hit.country}/company/{hit.id}"` — always non-empty (D-031(c)) |

`PUBLIC_BASE_URL` is one module constant defaulting to `https://api.foretak.dev`, overridable
by `REGISTRY_MCP_PUBLIC_BASE_URL` so a self-hosted deployment cites itself. It is a citation
target only: nothing in this server ever calls it.

### `fetch` algorithm

1. Split on the **first** `:`. Two-letter left part → country. `rules` → rules document
   (`get_registry(cc).rules_markdown()`, `title` = the rules title, `url` = `/v1/countries`).
   No colon → try every live `validate_id`; exactly one match wins, zero or ≥2 is `bad_request`
   naming the `"{COUNTRY}:{identifier}"` form and `list_countries`.
2. `report = await registry.lookup(id)`; `deadlines = registry.deadline_report(report, today)`
   with `today` = the server's current UTC date. **One upstream call, not two** — `deadline_report`
   is pure.
3. Render `text` (§2); assemble `metadata` (§3); `url` = the same REST record URL `search` emitted.
4. Any `RegistryError` → `_tool_error(exc)`, unchanged. `not_found` **is** an error here.

---

## 2. `text` — the Markdown rendering

Fixed section order, sections with no content omitted entirely, no invented values, `None`
rendered by omitting its line (never as "unknown" or "0" — D-004, D-011):

```
# {name} — {country} {id}

**Register:** … · **Identifier:** {id_scheme} {id_formatted or id}
**Status:** {status} — {status_detail}
**Legal form:** {legal_form} ({legal_form_code} / {legal_form_local})
**Registered:** … · **Founded:** …
**VAT:** …
**Employees:** …
**Industry:** …
**Business address:** … / **Postal address:** …
**Website / Phone / Email:** …
**Share capital:** …

## Statutory filing deadlines (as of {today})
- **{local_name}** — due {due_date} ({days_until} days). {applies_because}

## Register-published dates          ← only when published_deadlines is non-empty
- {kind}: due {due_date} (source: {source})

## Notes                              ← every notes sentence, verbatim, never summarised
- …

## Source
{source} — {source_url}
Licence: {license} · Fetched {fetched_at} · Served from cache: {yes|no}
Relayed from the national register. Not a sanctions, PEP or adverse-media screening, and not a
verification of bank account details.
```

The `## Notes` rule is load-bearing: `notes` is where a country module puts its caveats
(D-010) — bankruptcy, deletion, an unclassified legal form, the calendar-year assumption — and
in deep research this rendering is the only thing the model reads.

---

## 3. `metadata`

```jsonc
{
  "company_report":  { …CompanyReport.model_dump(mode="json"), byte-identical to lookup_company… },
  "deadline_report": { …DeadlineReport.model_dump(mode="json"), byte-identical to company_deadlines… },

  // flat scalars, duplicated for any client that flattens metadata (D-031(d))
  "country": "NO", "registry": "brreg", "company_id": "923609016",
  "name": "EQUINOR ASA", "status": "active", "is_active": true,
  "legal_form": "Public limited company",
  "source": "Enhetsregisteret (Brønnøysundregistrene)",
  "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/923609016",
  "license": "NLOD 2.0", "cached": false, "fetched_at": "2026-09-05T12:00:00Z",
  "next_deadline_kind": "payroll_report", "next_deadline_due_date": "2026-09-07"
}
```

`next_deadline_*` are the first row of `deadline_report.deadlines` (already sorted by
`due_date`), or absent when the list is empty. Nothing here is computed that is not already in
one of the two documents.

---

## 4. Worked example — Norway

Values below are **real**, derived on 2026-09-05 by running the committed mappers against
`tests/fixtures/brreg_923609016.json` at `today=2026-09-05`; they are not illustrative.

**`search("Equinor")`** — no country token, so it fans out to NO and GB; GB returns nothing for
this query:

```json
{
  "results": [
    {
      "id": "NO:923609016",
      "title": "EQUINOR ASA — NO 923609016 — Public limited company, active",
      "url": "https://api.foretak.dev/v1/NO/company/923609016"
    }
  ]
}
```

**`search("923609016")`** — `validate` says NO, GB rejects nine digits, so it short-circuits to
one lookup and returns the identical single row.

**`fetch("NO:923609016")`**:

```json
{
  "id": "NO:923609016",
  "title": "EQUINOR ASA — NO 923609016",
  "url": "https://api.foretak.dev/v1/NO/company/923609016",
  "text": "…see below…",
  "metadata": { "company_report": {…}, "deadline_report": {…}, "country": "NO", "…": "…" }
}
```

with `text`:

```markdown
# EQUINOR ASA — NO 923609016

**Register:** Enhetsregisteret (Brønnøysundregistrene) · **Identifier:** organisasjonsnummer 923 609 016
**Status:** active — Registered and active in Enhetsregisteret.
**Legal form:** Public limited company (ASA / Allmennaksjeselskap)
**Registered:** 1995-03-12 · **Founded:** 1972-09-18
**VAT:** registered as NO923609016MVA since 1989-07-01
**Employees:** 21239
**Industry:** 06.100 Utvinning av råolje (NACE); 06.200 Utvinning av naturgass; 19.200 Produksjon av raffinerte petroleumsprodukter og fossile brenselsprodukter
**Business address:** Forusbeen 50, 4035 STAVANGER, Norge
**Postal address:** Postboks 8500, 4035 STAVANGER, Norge
**Website:** www.equinor.com · **Phone:** 51 99 00 00
**Share capital:** 5976872600.0 NOK

## Statutory filing deadlines (as of 2026-09-05)
- **A-melding** — due 2026-09-07 (2 days). This entity has reported employees and must file the monthly payroll report (a-melding) with NAV/Skatteetaten (a-opplysningsforskriften § 2-1).
- **Mva-melding** — due 2026-10-12 (37 days). This entity is registered in Merverdiavgiftsregisteret and must file a VAT return (mva-melding) with Skatteetaten (skatteforvaltningsforskriften § 8-3-10(1); periods § 8-3-1). Assumes the ordinary two-month cycle …
- **Aksjonærregisteroppgaven (RF-1086)** — due 2027-02-01 (149 days). An ASA company must file the shareholder register statement (RF-1086) with Skatteetaten (skatteforvaltningsforskriften § 7-7-4(1)).
- **Skattemelding for næringsdrivende** — due 2027-05-31 (268 days). An ASA must file a tax return (skattemelding) with Skatteetaten (skatteforvaltningsforskriften § 8-2-3(1)(a)).
- **Ordinær generalforsamling** — due 2027-06-30 (298 days). An ASA must hold its ordinary general meeting within six months of the financial year end (aksjeloven § 5-5(1)) …
- **Årsregnskap** — due 2027-07-31 (329 days). An ASA must file annual accounts with Regnskapsregisteret; regnskapsloven § 8-3(1) starts a late fee unless they are dispatched before 1 August …

## Notes
- Filing deadlines are computed assuming a calendar-year accounting period. Enhetsregisteret does not publish a company's accounting year. For a financial year ending between 1 January and 30 June, regnskapsloven § 8-3(1) sets a different deadline — 1 February, not 31 July — so a deviating year changes which rule applies, not just the date. The Ministry may also postpone the accounts deadline by up to one month by regulation (§ 8-3(1)). Verify against Regnskapsregisteret before relying on an annual date.

## Source
Enhetsregisteret (Brønnøysundregistrene) — https://data.brreg.no/enhetsregisteret/api/enheter/923609016
Licence: NLOD 2.0 · Fetched 2026-09-05T12:00:00Z · Served from cache: no
Relayed from the national register. Not a sanctions, PEP or adverse-media screening, and not a verification of bank account details.
```

Three `applies_because` sentences are elided with `…` **in this document only**; the real
rendering carries every one in full, and an eval check asserts the statute reference survives.

---

## 5. Worked example — United Kingdom

From `tests/fixtures/ch_00445790.json` at `today=2026-09-05`.

**`search("Tesco PLC")`** — fans out; NO returns nothing, GB returns the Companies House hits:

```json
{
  "results": [
    {"id": "GB:00445790", "title": "TESCO PLC — GB 00445790 — Public limited company, active",
     "url": "https://api.foretak.dev/v1/GB/company/00445790"},
    {"id": "GB:09384423", "title": "KFORD TYRES (GORNAL) LTD — GB 09384423 — Private limited company, active",
     "url": "https://api.foretak.dev/v1/GB/company/09384423"},
    {"id": "GB:05888957", "title": "TESCO AQUA (FINCO2) LIMITED — GB 05888957 — Private limited company, dissolved",
     "url": "https://api.foretak.dev/v1/GB/company/05888957"}
  ]
}
```

Row order is the real one: confidences are 0.95, 0.4, 0.4 (D-005's anchors), so the exact-name
match leads and the two equal scores keep Companies House's own order. The third row is why
`status` is in the title — a dissolved company announces itself before it costs a `fetch`.

**`fetch("GB:00445790")`** `text`, showing the two `null`s that are the product's thesis and the
`## Register-published dates` section Norway never has:

```markdown
# TESCO PLC — GB 00445790

**Register:** Companies House (UK) · **Identifier:** company number 00445790
**Status:** active — Active on the Companies House register.
**Legal form:** Public limited company (plc)
**Registered:** 1947-11-27 · **Founded:** 1947-11-27
**Employees:** not published by this register
**Industry:** 47110 (SIC 2007)
**Business address:** Tesco House, Shire Park, Kestrel Way, AL7 1GA Welwyn Garden City, United Kingdom

## Statutory filing deadlines (as of 2026-09-05)
- **Confirmation statement (CS01)** — due 2027-07-02 (300 days). Companies House publishes this date for the company itself; it is the register's own figure, not a calculation.
- **Annual accounts** — due 2027-08-26 (355 days). Companies House publishes this date for the company itself; it is the register's own figure, not a calculation.

## Register-published dates
- annual_accounts: due 2027-08-26 (source: accounts.next_accounts.due_on)
- confirmation_statement: due 2027-07-02 (source: confirmation_statement.next_due)

## Source
Companies House (UK) — https://find-and-update.company-information.service.gov.uk/company/00445790
Licence: Crown copyright — Companies House public register, free to re-use · Fetched 2026-09-05T12:00:00Z · Served from cache: no
Relayed from the national register. Not a sanctions, PEP or adverse-media screening, and not a verification of bank account details.
```

`vat_registered`, `employees` and `share_capital` are `null` in `metadata.company_report` and
their lines are **absent** from `text` — except `employees`, which renders "not published by
this register" because `employees_reported: false` states positively that the register does not
publish one. A rendering that printed `0` or "unknown" for either would be the D-011 failure.

**Zero-hit case, `search("Zzzqqx Holdings")`:**

```json
{
  "results": [
    {"id": "rules:GB", "title": "Companies House (United Kingdom) (GB) — identifier rules, legal forms and filing deadlines",
     "url": "https://api.foretak.dev/v1/countries"},
    {"id": "rules:NO", "title": "Enhetsregisteret (Brønnøysundregistrene) (NO) — identifier rules, legal forms and filing deadlines",
     "url": "https://api.foretak.dev/v1/countries"}
  ]
}
```

---

## 6. Eval cases to add — `evals/cases.json`

A new group **`G`: "ChatGPT connector aliases"** in `groups`. No change to `evals/run.py` is
needed: every mock kind used below already exists (`NO lookup | lookup_404 | search |
search_empty`, `GB lookup | search`), and `gb_api_key` defaults to `"dummy"`.

**E27 — search by name, then fetch the id it returned** (the round-trip contract).

```json
{
  "id": "E27", "group": "G", "live": false,
  "prompt": "Find the Norwegian company Equinor and tell me when its annual accounts are due.",
  "notes": "The one assertion that matters: fetch(search.results[0].id) must resolve. Golden mode substitutes the id the connector actually minted, so an id-format change fails here rather than in production.",
  "setup": {"mocks": [
    {"country": "NO", "kind": "search", "fixture": "brreg_923609016.json"},
    {"country": "GB", "kind": "search", "fixture": "ch_search_empty.json"},
    {"country": "NO", "kind": "lookup", "id": "923609016", "fixture": "brreg_923609016.json"}
  ]},
  "calls": [
    {"type": "tool", "tool": "search", "arguments": {"query": "Equinor"}, "save_as": "s"},
    {"type": "tool", "tool": "fetch", "arguments": {"id": "{{s.results[0].id}}"}, "save_as": "d"}
  ],
  "checks": [
    {"call": 0, "path": "results[0].id", "op": "equals", "value": "NO:923609016"},
    {"call": 0, "path": "results[0].url", "op": "contains", "value": "/v1/NO/company/923609016"},
    {"call": 0, "path": "results[0].title", "op": "contains", "value": "EQUINOR ASA"},
    {"call": 1, "path": "id", "op": "equals", "value": "NO:923609016"},
    {"call": 1, "path": "metadata.company_report.name", "op": "equals", "value": "EQUINOR ASA"},
    {"call": 1, "path": "text", "op": "contains", "value": "Årsregnskap", "gate": true,
     "note": "deadlines must be in the rendering: ChatGPT deep research cannot call company_deadlines"},
    {"call": 1, "path": "text", "op": "contains", "value": "regnskapsloven § 8-3(1)"},
    {"call": 1, "path": "text", "op": "contains", "value": "calendar-year accounting period", "gate": true,
     "note": "every notes sentence must survive into text (D-010)"}
  ],
  "agent": {"answer_must_include": ["2027-07-31"]}
}
```

**E28 — search with an identifier short-circuits to a lookup** (no name search is issued; the NO
search route is deliberately unmocked, so a fan-out to it would fail the case).

```json
{
  "id": "E28", "group": "G", "live": false,
  "prompt": "What is NO 923 609 016?",
  "setup": {"mocks": [{"country": "NO", "kind": "lookup", "id": "923609016", "fixture": "brreg_923609016.json"}]},
  "calls": [{"type": "tool", "tool": "search", "arguments": {"query": "923609016"}, "save_as": "s"}],
  "checks": [
    {"call": 0, "path": "results", "op": "length_equals", "value": 1},
    {"call": 0, "path": "results[0].id", "op": "equals", "value": "NO:923609016"}
  ]
}
```

**E29 — fetch a GB id: honest nulls survive the rendering.**

```json
{
  "id": "E29", "group": "G", "live": false,
  "prompt": "Fetch the Companies House record GB:00445790 and tell me if it is VAT-registered.",
  "setup": {"mocks": [{"country": "GB", "kind": "lookup", "id": "00445790", "fixture": "ch_00445790.json"}]},
  "calls": [{"type": "tool", "tool": "fetch", "arguments": {"id": "GB:00445790"}, "save_as": "d"}],
  "checks": [
    {"call": 0, "path": "metadata.company_report.vat_registered", "op": "is_null", "gate": true},
    {"call": 0, "path": "metadata.deadline_report.deadlines", "op": "length_equals", "value": 2},
    {"call": 0, "path": "text", "op": "contains", "value": "Confirmation statement (CS01)"},
    {"call": 0, "path": "text", "op": "contains", "value": "the register's own figure"},
    {"call": 0, "path": "url", "op": "contains", "value": "/v1/GB/company/00445790"}
  ],
  "agent": {"answer_must_not_include": ["not VAT-registered", "is not registered for VAT"]}
}
```

**E30 — zero hits returns real rules documents, never a fabricated company.**

```json
{
  "id": "E30", "group": "G", "live": false,
  "prompt": "Look up the company Zzzqqx Holdings.",
  "setup": {"mocks": [
    {"country": "NO", "kind": "search_empty"},
    {"country": "GB", "kind": "search", "fixture": "ch_search_empty.json"}
  ]},
  "calls": [{"type": "tool", "tool": "search", "arguments": {"query": "Zzzqqx Holdings"}, "save_as": "s"}],
  "checks": [
    {"call": 0, "path": "results.*.id", "op": "equals_set", "value": ["rules:GB", "rules:NO"]},
    {"call": 0, "path": "results.*.title", "op": "none_contains", "value": "Zzzqqx", "gate": true,
     "note": "a zero-hit search must never emit a row that looks like the company asked for"}
  ],
  "agent": {"answer_must_not_include": ["Zzzqqx Holdings is", "found the company"]}
}
```

**E31 — the tool-choice guard, and the reason D-031 is a bet worth measuring.** Agent mode only:
a plain name query from a Claude-family client must reach `search_company`, not the alias. **If
this case fails, that is the trigger for D-031(a)'s named escape hatch — split the connector onto
a second endpoint — not for rewording the description a third time.**

```json
{
  "id": "E31", "group": "G", "live": false,
  "prompt": "Search the Norwegian company register for Equinor and give me its organisation number.",
  "setup": {"mocks": [{"country": "NO", "kind": "search", "fixture": "brreg_923609016.json"}]},
  "calls": [{"type": "tool", "tool": "search_company", "arguments": {"name": "Equinor", "country": "NO"}, "save_as": "s"}],
  "checks": [{"call": 0, "path": "hits[0].id", "op": "equals", "value": "923609016"}],
  "agent": {
    "required_tools": ["search_company"],
    "forbidden_tools": ["search", "fetch"],
    "answer_must_include": ["923609016"]
  }
}
```

---

## 7. Done-check

1. `tools/list` returns **seven** tools; the five keep their names, input schemas, output
   schemas and annotations byte-identical (`tests/fixtures/tools_list.jsonl` regenerated and
   diffed — only additions).
2. `uv run pytest -q -m "not live"` ≥ 423 passed, with the existing REST≡MCP parity tests
   passing **unchanged**.
3. `fetch(search(q).results[0].id)` round-trips for a NO name query, a GB name query, and an
   identifier query.
4. `search`'s and `fetch`'s `structuredContent` and the JSON-encoded `content[0].text` mirror
   are both present on the wire and carry the same object (OpenAI requires both). **Verified by
   inspection of an actual response, not assumed from FastMCP's documented behaviour.**
5. Every `results[*].url` is a non-empty string, in every case including the zero-hit one —
   OpenAI drops the citation otherwise.
6. `grep -n "NO\"\|GB\"\|Norway\|Brønnøysund\|Companies House" src/registry_mcp/mcp/connector.py`
   returns only description/docstring prose, never a branch.
7. `git diff --stat` touches no file under `src/registry_mcp/core/`, `src/registry_mcp/api/` or
   `src/registry_mcp/registries/`.
8. A GB deployment with `COMPANIES_HOUSE_API_KEY` unset still answers `search("Equinor")` with
   Norway's hits and does not raise.

---

## 8. README wording

### Under the install badges

```markdown
## Add to ChatGPT

ChatGPT reaches an MCP server through a custom connector, and its deep research mode calls
exactly two tools — `search` and `fetch` — which this server ships alongside the five registry
tools. In ChatGPT, open **Settings → Connectors**, add a custom connector, and give it:

    https://api.foretak.dev/mcp

No authentication, no key, no account. If your ChatGPT plan does not show custom connectors
under Settings → Connectors, turn on **Settings → Security and login → Developer mode** first,
then add the URL from <https://chatgpt.com/plugins>.

`search` takes one free-text query — a company name, a national identifier, or a name plus a
country ("Tesco United Kingdom") — and returns citable rows; `fetch` takes a row's `id`
(`"NO:923609016"`) and returns that company's register record **and its statutory filing
deadlines**, with the full JSON of both in `metadata`.

## Add to Claude Desktop

Claude Desktop takes the same URL as a custom connector: **Settings → Connectors → Add custom
connector**, then `https://api.foretak.dev/mcp`. No key. For a local stdio install instead, see
[Configuration](#configuration).
```

### Amendments elsewhere (D-031(f))

| File | Now | Becomes |
|---|---|---|
| `README.md:27` | "**Five tools, not fifty.**… Five tools is roughly 12% of that budget" | "**Seven tools, not fifty** — five registry tools plus two ChatGPT connector aliases…roughly 17% of that budget" |
| `README.md:37` | "The five tools and their response shapes are frozen" | "The five registry tools and their response shapes are frozen; two connector aliases (`search`, `fetch`) wrap them for ChatGPT and add no new shape" |
| `README.md` Tools table | five rows | a two-row **Connector aliases** section beneath, each row naming the tool it wraps |
| `MULTI_AGENT_BUILD_GUIDE.md` Step 5 | tool list | same list plus "…plus the two ChatGPT connector aliases `search`/`fetch` (D-031)" |
| `research/AGENT_PRIMER.md` §1, §10, §152 | "all five tools", "five tools versus a ~40-tool client budget" | "five registry tools plus two connector aliases", "seven tools versus a ~40-tool client budget" |
| `static/llms-full.txt` | five tool sections | a §3.6 documenting both aliases, the `"{COUNTRY}:{id}"` id format, and that neither has a REST twin |
| `DECISIONS.md` D-024 ¶1 | "exposes five MCP tools. Adding a sixth…" | amended **by D-031**, not edited in place: five registry tools plus two connector aliases; a sixth *registry* tool still needs an explicit amendment |

`server.json`, `glama.json`, `llms.txt` and the Smithery/Glama listings need no change — none of
them enumerates tools.

---

## 9. What was not verifiable from OpenAI's own documentation

Recorded here rather than guessed, because each one changes an implementation choice if it turns
out otherwise:

- **Whether a tool error aborts a deep-research run** or is recovered from. The page describes no
  error contract at all. We raise D-007's envelope as a `ToolError` on the reasoning that a
  `fetch` of a named document that does not exist is a genuine failure; if a raise proves fatal to
  a run, the fallback is a document whose `text` states the error and whose `metadata.error`
  carries `to_dict()` — a change to `fetch` only, and to nothing else.
- **Whether nested objects survive in `metadata`.** OpenAI's words are "an optional key/value
  pairing" and their example is flat strings. This is why §3 duplicates the decision-relevant
  facts as flat scalars.
- **Whether ChatGPT calls tools other than `search`/`fetch`** on a custom connector outside deep
  research. The page says only that deep research and company knowledge use those two.
- **Whether the tool names must be exactly `search` and `fetch`.** The documentation consistently
  says "two read-only tools: `search` and `fetch`" but never states it as a constraint. We treat
  the names as fixed.
- **Which ChatGPT plans can add a custom connector, and whether a no-auth server is accepted.**
  Not stated on that page. `04-mcp-and-agent-ecosystem/client-support-discovery-and-tool-limits.md`
  records that public *submissions* need a verified developer or business identity and that
  write-capable connectors are limited to Business/Enterprise/Edu — but this server is read-only
  and is being added by URL, not submitted, so neither statement settles it. **The README wording
  in §8 hedges the menu path for this reason**: OpenAI's page says "Settings → Security and login
  → Developer mode" then `chatgpt.com/plugins`, which is the developer-mode route; "Settings →
  Connectors" is the route most users will see. A human should confirm which one appears on a
  normal plan before the README ships.
- The **OpenAI cookbook page** on building a deep-research MCP server was not read: both known
  URLs 404 or redirect to a 404 as of 2026-09-05. Everything quoted here is from
  `https://developers.openai.com/api/docs/mcp` (the 301 target of `https://platform.openai.com/docs/mcp`).
