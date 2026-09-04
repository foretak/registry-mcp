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

## 2. Where each keyword must appear

| Surface | Which keywords | Rule | Owner |
|---|---|---|---|
| PyPI package description (`pyproject.toml :: description`) | 1–12 | The first sentence names the product; the second carries Norway's terms. Already done. | T11 |
| PyPI `keywords` array | 1–12 + ASCII fallbacks + umbrella | One entry each, lower-case, hyphenated where multiword. Already done. | T11 |
| npm `package.json` description + `keywords` | 1–12 + ASCII fallbacks | Mirror PyPI exactly, so a search on either index hits. | T11 |
| `README.md` first line | 11, 12, then 1, 4, 5, 6 by the third line | An agent reading the repo card sees "company registry" and "MCP" immediately, and "brreg / Enhetsregisteret / organisasjonsnummer (orgnr)" before the fold. | T11 |
| GitHub repo topics | `mcp`, `mcp-server`, `model-context-protocol`, `brreg`, `bronnoysund`, `enhetsregisteret`, `organisasjonsnummer`, `orgnr`, `norway`, `company-data`, `business-registry`, `ai-agents` | Topics are ASCII and hyphenated only — use the fallback spellings. Max 20 topics. | T11 (human clicks) |
| MCP tool docstrings (`lookup_company`, `search_company`, `company_deadlines`, `validate_company_id`) | 1–9 and GB-1…GB-7 in the per-country tools' first two sentences | Written as prose an agent reads, not a keyword dump: *"Look up a company by its national identifier — a Norwegian organisasjonsnummer (orgnr, org.nr) in Brønnøysundregistrene / Enhetsregisteret (brreg), or a UK company number (CRN) at Companies House."* One sentence per country, Norway first. Country-neutral tools stay neutral — do not push a country into `list_countries`. | T07, T15c |
| FastMCP `instructions` and `api/main.py :: _DESCRIPTION` | 11a first, then 1–9 and GB-1…GB-7 | Both lead with "the company registry MCP" (row 11a), then name the live countries with their aliases in one sentence each. These two strings are the first thing a client model reads. | T15c |
| REST OpenAPI endpoint descriptions | 1, 4, 5, 6 on `/v1/{country}/…` routes | Same prose rule. `/openapi.json` is crawled. | T06 |
| `server.json` (`description`, `_meta…/keywords`) | `description` is capped at **100 characters** by the schema, so it carries 1, 5/6, 11 only; the full list lives in `_meta.io.modelcontextprotocol.registry/publisher-provided.keywords` | Done in this repo's `server.json`. | T05 (done) |
| `static/llms.txt` | 1–6 in the opening paragraph | Done. | T05 (done) |
| `static/llms-full.txt` | 1–12, once, in the "Aliases you may be searching for" block near the top | Done. | T05 (done) |
| `static/index.html` | 1–12 in `<meta name="keywords">`, the JSON-LD `keywords` and `alternateName` | Done. | T05 (done) |
| Registry submissions (Smithery, Glama, PulseMCP, mcp.so, MCP Market) | 1–12 wherever a tag/keyword field exists | Copy from §1 verbatim; do not re-word per site. | T11 |
| Article titles and first paragraphs (`content/`) | At least 1, 5 and 6 per article | The articles are search surface, not just prose. | T12 |

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
