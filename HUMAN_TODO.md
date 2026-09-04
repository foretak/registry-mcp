# HUMAN_TODO

Things only a human can do, or that a human must decide before an agent can
finish. Started by T05 (Opus B). T14 (orchestrator) extends it at launch.

---

## 1. Names to search-replace if brand differs

Everything below uses the **placeholder** brand `Foretak`. `BRREG_MCP_BUILD_PLAN.md`
§1.1 asks the human to check domain and org availability first. If the brand
lands somewhere else (`Orgnr` / `orgnr.dev`, `Enhet` / `enhet.dev`, or anything
else), search-replace these strings across the repo.

**Do not change the technical names.** `registry-mcp`, `brreg-mcp`,
`lookup_company`, `search_company`, `company_deadlines`, `validate_company_id`,
`list_countries` are keyword-bearing and stay as they are whatever the brand is
(`DECISIONS.md` D-002, `KEYWORDS.md` §3).

| Placeholder | What it is | Files that contain it |
|---|---|---|
| `https://api.foretak.dev` | API base URL | `static/llms.txt`, `static/llms-full.txt`, `static/index.html`, `server.json` |
| `https://api.foretak.dev/mcp` | Streamable HTTP MCP endpoint | same four, plus `README.md` |
| `https://foretak.dev` | Brand site, JSON-LD `provider.url` | `static/index.html` |
| `hello@foretak.dev` | Contact address in the JSON-LD | `static/index.html` |
| `https://github.com/foretak/registry-mcp` | Repo URL | `server.json`, `static/*`, `pyproject.toml` (`[project.urls]`), `README.md`, `NORBIZ_SPEC.md` §6 (User-Agent) |
| `io.github.foretak/registry-mcp` | MCP registry server name (reverse-DNS, must match the **GitHub org that owns the repo** — the registry verifies this) | `server.json` |
| `foretak` | GitHub organisation slug | everywhere above |
| `Foretak` | Display name in JSON-LD `provider.name` and `alternateName` | `static/index.html` |

One command to find them all:

```bash
grep -rn --exclude-dir=.git --exclude-dir=.venv -i -e 'foretak' -e 'api\.foretak\.dev' .
```

Two known inconsistencies to fix in the same pass:

- `README.md` currently says `https://api.example.dev` in the add-to-Claude-Code
  and curl examples. It should say `https://api.foretak.dev` (or the final
  domain). **T11 owns `README.md`** — T05 did not edit it.
- `pyproject.toml` `[project.urls]` already points at `github.com/foretak/…`, so
  it is covered by the same replace.

If the GitHub org changes, `server.json`'s `name` **must** change with it: the
official registry authenticates `io.github.<org>/<server>` against ownership of
that GitHub namespace. A mismatch is rejected at publish time, not later.

---

## 2. MCP registry schema — what T05 validated against

| | |
|---|---|
| Schema URL | `https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json` |
| Fetched and validated | **2026-09-03** |
| How it was chosen | Probed `static.modelcontextprotocol.io` for later dated schemas (2026-01-15, 2026-03-01, 2026-06-01 → all 404) and confirmed against a live `GET https://registry.modelcontextprotocol.io/v0/servers?limit=1`, whose published entries carry the same `2025-12-11` `$schema`. |
| Validation command | `uv run --with check-jsonschema --no-project check-jsonschema --schemafile https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json server.json` |
| Result | `ok -- validation done` |
| Recorded in | `server.json` `$schema`, and `_meta.io.modelcontextprotocol.registry/publisher-provided.schemaFetchedAt` |

**Before publishing (T11), re-check the schema version.** The MCP registry
publishes dated schemas and rotates them; re-run the probe above and re-validate.
Two schema constraints that will bite an edit:

- `description` is capped at **100 characters**. The full keyword list therefore
  lives in `_meta`, not in `description` (see `KEYWORDS.md` §2).
- `version` must be a concrete version — `latest` and ranges (`^1.2.3`, `1.x`)
  are rejected. `server.json` currently says `0.1.0` in three places (server,
  PyPI package, npm package); all three must be bumped together at each release.

---

## 3. Accounts, logins and DNS

- [ ] Domain for the brand (`foretak.dev` or the fallback), DNS `A`/`AAAA` for
      `api.<domain>` pointing at the VPS.
- [ ] GitHub organisation `foretak` (or fallback) and repo `registry-mcp`, made
      public. Repo topics per `KEYWORDS.md` §2 — topics can only be set through
      the web UI or an authenticated `gh` call.
- [ ] PyPI account + project names `registry-mcp` and the alias `brreg-mcp`.
- [ ] npm account + package names `registry-mcp` and the alias `brreg-mcp`.
- [ ] A contact inbox that a human reads: `hello@<domain>`. It goes into the
      JSON-LD and, via `REGISTRY_MCP_CONTACT_EMAIL`, into the `User-Agent` we
      send to Brønnøysundregistrene — they may block anonymous clients.
- [ ] VPS (Hetzner Helsinki or Norwegian), smallest instance.
- [ ] Official MCP registry publish: needs a GitHub login for the namespace
      check on `io.github.foretak/registry-mcp`.
- [ ] Smithery, Glama, PulseMCP, mcp.so, MCP Market — each needs a login. T11
      prepares the submission files and `SUBMISSIONS.md`.

---

## 4. Content that must exist before the homepage goes live

- [ ] **`legal/terms.md`** — `static/index.html`'s JSON-LD `termsOfService`
      points at `https://github.com/foretak/registry-mcp/blob/main/legal/terms.md`.
      The `legal/` folder is currently empty, so that link 404s until the file
      is written. Either write it or change the JSON-LD field. It must at
      minimum state the NLOD 2.0 attribution requirement for Enhetsregisteret
      data and that the service gives no warranty of accuracy.
- [ ] **NLOD 2.0 attribution** is a licence condition, not a courtesy. Every
      response already carries `source`, `source_url` and `license`; keep the
      footer line on the homepage too.
- [ ] `NAMES.md` per build plan §1.1, recording the names actually owned.

---

## 5. Known corrections carried forward

- The build plan's canonical org.nr **`833286602` is a typo for `833285602`** (EL ANSARI KONSULT, ENK) — the mistyped one fails
  MOD11 and 404s on the live API. Every example in `static/`, `server.json` and
  this file uses **`923609016` (Equinor ASA)**. `833286602` survives only as the
  negative test case (`NORBIZ_SPEC.md` §13 test 9) and as a cautionary example
  in `llms-full.txt` §3.5. Do not reintroduce it as a valid example.
- Route shapes are country-scoped (`/v1/{country}/…`), not the build plan's
  `/v1/company/{id}`. The multi-agent guide and `DECISIONS.md` win where the
  build plan disagrees.

---

## 6. Posting the articles (`content/`)

Four articles, three versions each, all written and ready in `content/`. Full
version of this schedule, plus the rules for whoever posts, is in
`content/README.md`.

**One article every two days. dev.to first, Reddit r/mcp the same day, kode24
two days later.** Never post all four at once.

| Day | dev.to (`devto.md`) | r/mcp (`reddit.md`) | kode24 (`no.md`) |
|---|---|---|---|
| 1 | `01-vat-check` | `01-vat-check` | — |
| 3 | `02-deadlines` | `02-deadlines` | `01-vat-check` |
| 5 | `03-enrich-spreadsheet` | `03-enrich-spreadsheet` | `02-deadlines` |
| 7 | `04-add-your-country` | `04-add-your-country` | `03-enrich-spreadsheet` |
| 9 | — | — | `04-add-your-country` |

- [ ] Accounts needed before day 1: dev.to, a Reddit account with enough karma
      to self-post in r/mcp, and a kode24 contact (they take contributed
      pieces; email the editor rather than waiting for a form).
- [ ] **Replace the placeholders first.** Every article contains
      `api.foretak.dev` and `github.com/foretak/registry-mcp`. If §1's domain
      or GitHub org came out different, fix all twelve files before posting.
- [ ] **Re-run the output blocks if the server has changed since they were
      written.** Enhetsregisteret is live data — `employees` counts and
      addresses move. `content/README.md` has the two commands; do not patch a
      JSON block by hand.
- [ ] Post the Reddit text as a self-post and put the dev.to link in the first
      comment, not the body.
- [ ] Reply to every comment within 24 h and log the substance in
      `FEEDBACK.md` — those comments are the Phase 4 decision-gate input.
- [ ] `04-add-your-country` is the recruiting article. Post it last, and pin
      the "open an issue with your country code and claim it" line. Denmark
      (CVR) and Sweden (Bolagsverket) are named there as first targets, which
      matches guide Step 12.

Note for copy-editors: each article deliberately carries `brreg`,
`organisasjonsnummer` and `orgnr` in its title or first paragraph
(`KEYWORDS.md` §2, last row). Do not edit those terms out.
