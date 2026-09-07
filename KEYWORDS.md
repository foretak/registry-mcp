# KEYWORDS — the canonical alias list

Agents find tools by keyword match against package names, repo names, tool
descriptions and docstrings. A brand name is invisible to them; a descriptive
one is found (`DECISIONS.md` D-002, `BRREG_MCP_BUILD_PLAN.md` §0).

This file is the single source of truth for that vocabulary. If a keyword is
not here, do not invent one; if you add one here, apply it everywhere the
placement table says.

---

## 1. The list

| # | Keyword | Why an agent generates it |
|---|---|---|
| 1 | `brreg` | The term an LLM produces first for Norwegian company data; the upstream host is `data.brreg.no` |
| 2 | `brønnøysund` | The place name, in Norwegian prompts |
| 3 | `brønnøysundregistrene` | The full official name of the registry authority |
| 4 | `enhetsregisteret` | The specific register we read |
| 5 | `organisasjonsnummer` | The identifier's legal name |
| 6 | `orgnr` | The everyday short form |
| 7 | `org.nr` | The written abbreviation, dot included |
| 8 | `norway company lookup` | The English task phrase |
| 9 | `norwegian business registry` | The English domain phrase |
| 10 | `foretak` | Norwegian for "enterprise"; also the brand, and a term Norwegian prompts contain |
| 11 | `company registry` | The country-neutral umbrella phrase |
| 11a | `company registry MCP` | **The phrase we own.** "registry MCP" alone collides with the official *MCP Registry* directory, so every headline (homepage H1, README H1, `llms.txt` line 1, package descriptions, `server.json`, FastMCP `instructions`) leads with "the company registry MCP". Decided by Kim 2026-09-04. |
| 12 | `mcp` | The protocol clients search for |

ASCII fallbacks — always in addition to, never instead of, the accented form:
`bronnoysund`, `bronnoysundregistrene`. Some indexes (PyPI keyword search, npm,
GitHub topics) fold or reject non-ASCII, so both spellings must be present
wherever the medium allows only one form.

Umbrella keywords for the country-neutral product, used alongside the
Norwegian ones and never replaced by them: `company-data`, `business-registry`,
`mcp-server`, `model-context-protocol`, `ai-agents`.

---

## §GB — United Kingdom aliases

Rows 1–10 are Norway's. The UK module (`registries/gb/`, T15) adds its own set,
governed by the same rules: they go in prose, they go beside the Norwegian
terms rather than instead of them, and the umbrella rows 11, 11a and 12 still
lead every headline.

| # | Keyword | Why an agent generates it |
|---|---|---|
| GB-1 | `companies house` | The register's name, and the term an LLM produces first for UK company data |
| GB-2 | `company number` | The identifier's everyday name on the UK register |
| GB-3 | `company registration number` | The formal name; abbreviated CRN on invoices and contracts |
| GB-4 | `uk company lookup` | The English task phrase, mirroring row 8 |
| GB-5 | `uk company search` | The other half of the task phrase — a name, not a number |
| GB-6 | `confirmation statement` | The UK-specific filing obligation, and the one deadline term with no Norwegian analogue |
| GB-7 | `companies house api` | What a developer searches for when they already know the upstream |

**`UK` is a keyword, never a country code.** D-015 makes `GB` the only accepted
code: `get_registry("UK")` raises `unsupported_country`. The alias lives here,
in prose an agent reads while *finding* the tool, and never in the routing.
Every surface that carries these terms writes "United Kingdom (GB)" at least
once so the code is learnable from the same sentence as the alias.

`Companies House` is capitalised as two words in prose and lower-cased only in
machine keyword arrays (`server.json`, PyPI/npm `keywords`), which are
case-folded by every index that reads them.

---

## §SE — Sweden aliases

The Sweden module (`registries/se/`, T26) adds its own set under the same
rules: prose, not lists; beside the Norwegian and British terms rather than
instead of them; rows 11, 11a and 12 still lead every headline.

| # | Keyword | Why an agent generates it |
|---|---|---|
| SE-1 | `organisationsnummer` | The identifier's legal name — Swedish, and one letter from Norway's `organisasjonsnummer`, so both spellings must be present or a Swedish prompt lands on the wrong country |
| SE-2 | `bolagsverket` | The register's name, and the term an LLM produces first for Swedish company data |
| SE-3 | `företagsinformation` | The everyday Swedish phrase for company information |
| SE-4 | `kontrollera företag` | The Swedish task phrase — "check a company" |
| SE-5 | `verifiera organisationsnummer` | The validation task phrase, the cheap pre-check before a lookup |
| SE-6 | `konkurs` | Bankruptcy — one of the three status signals a Swedish report derives |
| SE-7 | `likvidation` | Liquidation — the second of those signals |
| SE-8 | `årsredovisning försenad` | "Annual report late": the förseningsavgift question the `annual_accounts` deadline answers |
| SE-9 | `F-skatt` | Swedish tax registration; SCB's *verksam* marking in the payload is F-skatt, VAT or an employer registration, and this module's notes say so |
| SE-10 | `swedish company lookup` | The English task phrase, mirroring rows 8 and GB-4 |
| SE-11 | `swedish company number` | The English name for the identifier, for prompts that do not reach for the Swedish word |

**There is no `swedish company search` row, and that is deliberate.**
Bolagsverket's free API has no name-search operation, so `search_company` for
`SE` raises `not_implemented`; a keyword promising a search Sweden cannot serve
would earn a tool call that always fails. Every Swedish surface says lookup by
identifier instead — and says why — so an agent learns the constraint from the
same prose it found the tool in.

ASCII fallbacks, always in addition to the accented form:
`foretagsinformation`, `arsredovisning`. Same rule as `bronnoysund`.

`Bolagsverket` is capitalised in prose and lower-cased only in machine keyword
arrays. `F-skatt` keeps its hyphen and its capital F in prose (it is a
Skatteverket term of art) and folds to `f-skatt` in a keyword array.

**Sweden went live on 2026-09-07 (0.3.0), so the reason for holding these
back is gone.** `GET /health` returns `{"version":"0.3.0","countries":["GB","NO","SE"]}`
and `GET /v1/SE/company/5560160680` returns Telefonaktiebolaget LM Ericsson. A
Swedish keyword now leads an agent to a country that answers, which is the
condition T26c wrote the hold against. What has actually been placed and what
has not is audited in **§2a** — the short version is that the code-side
surfaces carry Sweden and none of the machine keyword arrays do.

**No keyword row for `euid`, and none for `advertising_protected`/*reklamspärr*,
for the same reason there is no `swedish company search` row.** Both fields
exist on every `CompanyReport` as of 0.3.0, and both came back `null` from
every live call made on go-live day: none of the three registers we read
publishes an EUID at all, and Statistics Sweden's *reklamspärr* flag was absent
from the Swedish record checked (`5560160680`). A keyword earns a tool call, and a tool call that can only
return `null` is a keyword that costs the caller a round trip. These terms go
back on the table the first time a register answers one of them with a value —
the Danish module (CVR-loven § 19) is the likely first, and Finland is the
likely first EUID.

---

## 2. Where each keyword must appear

| Surface | Which keywords | Rule | Owner |
|---|---|---|---|
| PyPI package description (`pyproject.toml :: description`) | 1–12 | The first sentence names the product; the second carries Norway's terms. Already done. | T11 |
| PyPI `keywords` array | 1–12 + ASCII fallbacks + umbrella | One entry each, lower-case, hyphenated where multiword. Already done. | T11 |
| npm `package.json` description + `keywords` | 1–12 + ASCII fallbacks | Mirror PyPI exactly, so a search on either index hits. | T11 |
| `README.md` first line | 11, 12, then 1, 4, 5, 6 by the third line | An agent reading the repo card sees "company registry" and "MCP" immediately, and "brreg / Enhetsregisteret / organisasjonsnummer (orgnr)" before the fold. | T11 |
| GitHub repo topics | The twelve set on 2026-09-04: `mcp`, `mcp-server`, `model-context-protocol`, `brreg`, `bronnoysund`, `enhetsregisteret`, `organisasjonsnummer`, `orgnr`, `norway`, `company-data`, `business-registry`, `ai-agents` | Topics are ASCII and hyphenated only — use the fallback spellings. Max 20 topics, so **eight slots are free and no British or Swedish term has one** (§2a). | T11 (human clicks) |
| MCP tool docstrings (`lookup_company`, `search_company`, `company_deadlines`, `validate_company_id`) | 1–9, GB-1…GB-7 and SE-1…SE-11 in the per-country tools' first two sentences | Written as prose an agent reads, not a keyword dump: *"Look up a company by its national identifier — a Norwegian organisasjonsnummer (orgnr, org.nr) in Brønnøysundregistrene / Enhetsregisteret (brreg), or a UK company number (CRN) at Companies House."* One sentence per country, Norway first. `search_company` carries no Swedish task phrase except the one saying Sweden cannot be searched by name. Country-neutral tools stay neutral — do not push a country into `list_countries`. | T07, T15c, T26c |
| FastMCP `instructions` and `api/main.py :: _DESCRIPTION` | 11a first, then 1–9, GB-1…GB-7 and SE-1/SE-2 | Both lead with "the company registry MCP" (row 11a), then name the live countries with their aliases in one sentence each. These two strings are the first thing a client model reads. **Both carry all three countries since 0.3.0** (T26d, commit `0f952bc`); `mcp/connector.py`'s `search` description does too. | T15c, T26c, T26d |
| REST OpenAPI endpoint descriptions | 1, 4, 5, 6 on `/v1/{country}/…` routes | Same prose rule. `/openapi.json` is crawled. | T06 |
| `server.json` (`description`, `_meta…/keywords`) | `description` is capped at **100 characters** by the schema, so it carries 1, 5/6, 11 only; the full list lives in `_meta.io.modelcontextprotocol.registry/publisher-provided.keywords` | Done in this repo's `server.json`. | T05 (done) |
| `static/llms.txt` | 1–6 in the opening paragraph | Done. | T05 (done) |
| `static/llms-full.txt` | 1–12, once, in the "Aliases you may be searching for" block near the top | Done. | T05 (done) |
| `static/index.html` | 1–12 in `<meta name="keywords">`, the JSON-LD `keywords` and `alternateName` | Done. | T05 (done) |
| Registry submissions (Smithery, Glama, PulseMCP, mcp.so, MCP Market) | 1–12 wherever a tag/keyword field exists | Copy from §1 verbatim; do not re-word per site. | T11 |
| Article titles and first paragraphs (`content/`) | At least 1, 5 and 6 per article | The articles are search surface, not just prose. | T12 |

---

## 2a. Placement audit — 2026-09-07, the day Sweden went live

Checked against the files in this repo and against the running 0.3.0 service,
not against a task's status column. **Every code-side surface carries all three
countries. Not one machine keyword array does — and the British terms never got
there either, so this is a 0.2.0 debt Sweden merely made visible.**

| Surface | Norway | UK | Sweden | Evidence |
|---|---|---|---|---|
| MCP tool docstrings (`mcp/server.py`) | ✅ | ✅ | ✅ | 16 hits for `bolagsverket`/`organisationsnummer` |
| FastMCP `instructions` | ✅ | ✅ | ✅ | same file |
| `mcp/connector.py` `search` description | ✅ | ✅ | ✅ | 1 hit |
| `api/main.py :: _DESCRIPTION` | ✅ | ✅ | ✅ | "Three countries answer today", + the alias line |
| `static/well-known/mcp/server-card.json` | ✅ | ✅ | ✅ | 4 hits |
| `README.md` | ✅ | ✅ | ✅ | Sweden section, live example |
| `CHANGELOG.md` | ✅ | ✅ | ✅ | 0.3.0 entry |
| `static/llms.txt` | ✅ | ✅ | ✅ | **fixed 2026-09-07** — was Norway + UK only |
| `static/llms-full.txt` | ✅ | ✅ | ✅ | **fixed 2026-09-07** — had *zero* occurrences of "Sweden", "Bolagsverket" or "organisationsnummer" in 1 020 lines |
| `docs/clients.md` | ✅ | ✅ | ✅ | **fixed 2026-09-07** |
| `pyproject.toml :: description` | ✅ | ✅ | ✅ | **fixed 2026-09-07 (T34)** — three-country description pasted verbatim |
| `pyproject.toml :: keywords` | ✅ | ✅ | ✅ | **fixed 2026-09-07 (T34)** — 16 GB/SE entries appended, 39 total, nothing removed |
| `packages/npm/registry-mcp/package.json` | ✅ | ✅ | ✅ | **fixed 2026-09-07 (T34)** — description byte-identical to pyproject's; same 16 keywords appended |
| `server.json :: description` | ✅ | ✅ | ✅ | **fixed 2026-09-07 (T34)** — 89 of the schema's 100 characters used; validates against the declared schema |
| `server.json :: _meta…/keywords` | ✅ | ✅ | ✅ | **fixed 2026-09-07 (T34)** — 24 entries |
| `server.json :: _meta…/countries` | ✅ | ✅ | ✅ | **fixed 2026-09-07 (T34)** — now `["GB", "NO", "SE"]` |
| `server.json :: _meta…/dataLicense` | ✅ | ✅ | ✅ | **fixed 2026-09-07 (T34)** — SE clause appended byte-for-byte from §2a, matches `registries/se/__init__.py` and D-038 |
| `static/index.html` | ✅ | ✅ | ✅ | **fixed 2026-09-07 (T34)** — both `<meta>` tags, the lede, the JSON-LD `description`/`keywords`/`areaServed`, and the playground `<select>` (+ `DEFAULT_IDS.SE` and a generic `error.hint` → `addNote()` branch so a Sweden name-search renders its `not_implemented` hint as prose, not JSON-only) |
| `mcpb/manifest.json` | ✅ | ✅ | ✅ | **fixed 2026-09-07 (T34)** — `description`, `long_description` (notes `search_company` is not implemented for Sweden) and `keywords` all carry three countries |
| GitHub repo topics | ✅ | ✅ | ✅ | **fixed 2026-09-07 (T34)** — 20 of 20 set, verified live with `gh repo view --json repositoryTopics` |
| Registry listings (§ `SUBMISSIONS.md`) | ✅ | partly | ❌ | not touched by T34 (out of scope — `T11`, human clicks); the awesome-mcp-servers entry merged 2026-09-07 leads with the UK and Norway; no directory mentions Sweden |

`packages/brreg-mcp/` and `packages/npm/brreg-mcp/` are **correct as they
stand** and must not be touched: §3 makes the alias package Norway-only on
purpose, carrying rows 1–9 and nothing else.

### The strings to paste

These are not code changes; they are the keyword arrays and listing copy this
file already owns. Whoever cuts the next release applies them in one pass,
because they only reach PyPI, npm and the MCP registry when a tag is pushed —
and as of 2026-09-07 no tag has been, so all three indexes still serve 0.2.0.

**`pyproject.toml :: description`** and the npm `registry-mcp` description
(keep them byte-identical — the §2 rule is "mirror PyPI exactly"):

> The company registry MCP: company data for AI agents, any country. MCP server and REST API over national business registries — Norway (brreg / Brønnøysundregistrene / Enhetsregisteret, by organisasjonsnummer, orgnr or org.nr), the United Kingdom (Companies House, by company number / CRN) and Sweden (Bolagsverket, by organisationsnummer).

**`pyproject.toml :: keywords` and the npm `keywords`** — add to what is there,
remove nothing, lower-case throughout:

```
companies-house  companies-house-api  company-number  company-registration-number
uk-company-lookup  uk-company-search  confirmation-statement  united-kingdom
bolagsverket  organisationsnummer  foretagsinformation  arsredovisning
f-skatt  swedish-company-lookup  swedish-company-number  sweden
```

Note `organisationsnummer` (Swedish, **-tion-**) beside the existing
`organisasjonsnummer` (Norwegian, **-sjon-**). One letter apart, and SE-1 exists
precisely because an index that carries only one of them sends half the Nordic
prompts to the wrong country.

**`server.json :: description`** — the schema caps this at 100 characters; the
line below is 89, and carries rows 1, 6, 11a, GB-1, SE-1 and SE-2:

> The company registry MCP: brreg orgnr, Companies House, Bolagsverket organisationsnummer.

**`server.json :: _meta."io.modelcontextprotocol.registry/publisher-provided"`** —
append `"bolagsverket"`, `"organisationsnummer"`, `"swedish company lookup"` and
`"swedish company number"` to `keywords`; set `countries` to
`["GB", "NO", "SE"]`; and append to `dataLicense`:
`"; free re-use, publisher names no licence (Bolagsverket/SCB high-value datasets, EU Open Data Directive)"`.

**GitHub repo topics** — eight free slots, and eight terms that want them.
One authenticated command, the same shape as `SUBMISSIONS.md`'s:

```
companies-house  company-number  united-kingdom  bolagsverket
organisationsnummer  sweden  company-lookup  company-registry
```

**`static/index.html` and `mcpb/manifest.json`** carry executable code and a
bundle contract respectively, so their copy is listed here and changed by
whoever owns those files. `index.html` needs Sweden in six places — the two
`<meta>` tags, the lede, and the JSON-LD `description`, `keywords` and
`areaServed` — plus a decision the copy cannot make on its own: the playground
`<select>` offers `NO` and `GB`, and adding `SE` means the form must handle a
country whose `search_company` is `not_implemented`. That is a behaviour change,
not a keyword.

---

## 3. Rules

- **Never rename the technical names to fit the brand.** Package, repo and tool
  names stay `registry-mcp`, `brreg-mcp`, `lookup_company` whatever the domain
  ends up being (D-002).
- **`brreg-mcp` is published as an alias package** on PyPI and npm that depends
  on `registry-mcp`, so a search for either name resolves (build plan §3.2,
  guide Step 8). Its description carries keywords 1–9.
- **Keywords go in prose, not in lists, wherever a human or an LLM reads the
  text.** A docstring that reads as a keyword dump is scored worse by the
  models doing the matching and is worse for the human too.
- **Do not put Norwegian keywords in `core/`.** Country-neutral code, models and
  the `list_countries` tool stay neutral (D-001, D-004). Norwegian vocabulary
  belongs in `registries/no/`, in the Norway-specific tool docstrings, and in
  the marketing surfaces listed above.
- **Accented and ASCII spellings ship together.** `brønnøysund` for readers,
  `bronnoysund` for indexes that fold diacritics.
