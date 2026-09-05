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

- ~~`README.md` says `https://api.example.dev`~~ — **fixed by T11 (2026-09-04)**;
  it now says `https://api.foretak.dev` throughout, so it is covered by the same
  search-replace as everything else. Note that `README.md`'s **first line** is
  the MCP registry's PyPI ownership marker
  `<!-- mcp-name: io.github.foretak/registry-mcp -->` — if the GitHub org
  changes, that line, `packages/npm/registry-mcp/package.json`'s `mcpName` and
  `server.json`'s `name` must all change together or publishing is rejected.
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

**T11 re-checked this on 2026-09-04: `2025-12-11` is still current.** Probed
`static.modelcontextprotocol.io` for `2026-01-15`, `2026-03-01`, `2026-06-01`,
`2026-07-01` and `2026-09-01` → all 404; `2025-12-11` → 200; and a live
`GET https://registry.modelcontextprotocol.io/v0/servers?limit=1` still returns
entries carrying that `$schema`. `server.json` needs no change. Re-run the probe
anyway if more than a month passes before you publish.

Two schema constraints that will bite an edit:

- `description` is capped at **100 characters**. The full keyword list therefore
  lives in `_meta`, not in `description` (see `KEYWORDS.md` §2).
- `version` must be a concrete version — `latest` and ranges (`^1.2.3`, `1.x`)
  are rejected. `server.json` carries the version in three places (server,
  PyPI package, npm package — `0.2.0` since 2026-09-04); all three must be
  bumped together at each release.

---

## 3. Accounts, logins and DNS

- [x] Domain **`foretak.dev` bought 2026-09-04** (Cloudflare Registrar, $12.20/yr,
      auto-renew). DNS in Cloudflare: `api` CNAME → `ni4lg1ne.up.railway.app`
      (DNS-only, not proxied) + `_railway-verify.api` TXT. Railway verified and
      issued the certificate; **https://api.foretak.dev** serves everything and
      `claude mcp add registry-mcp --transport http https://api.foretak.dev/mcp`
      connects. Every `api.foretak.dev` placeholder in the repo is now real.
- [x] **Bare `foretak.dev` → 301 → `api.foretak.dev`** (done 2026-09-04 via the
      Cloudflare API: proxied dummy `A @ 192.0.2.1` + a Single Redirect rule,
      path and query preserved). `https://foretak.dev/llms.txt` now lands on the
      real file. ~~Delete the Cloudflare API token~~ — **deleted 2026-09-05**
      (token "Edit zone DNS"; the account now has no API tokens).
- [x] GitHub organisation `foretak` and repo `registry-mcp` — **done 2026-09-04**:
      https://github.com/foretak/registry-mcp (public), 12 topics set, labels
      created, seed issues #1–#3 filed. `gh` token now has `workflow` scope.
      See `NAMES.md` for the full name/competitor audit.
- [x] **PyPI published 2026-09-04** as user `foretak` (2FA passkey, account-scoped
      token stored in `~/secrets/registry-mcp/`): `registry-mcp 0.1.0` and the
      alias `brreg-mcp 0.1.0`. For future releases, replace the account-scoped
      token with two project-scoped ones (PyPI → project → Settings → tokens).
- [x] **npm published 2026-09-04** as user `foretak` (2FA via passkey):
      `registry-mcp@0.1.0` and `@foretak/brreg-mcp@0.1.0`. Note: `npx registry-mcp`
      shells out to `uvx registry-mcp`, so it only works once the **PyPI** package
      exists — publish PyPI next. Original note kept below for the record.
- [x] ~~npm account + package name `registry-mcp` (**free**) and the alias.~~
      ⚠️ **`brreg-mcp` on npm is already taken** — by `hellosverre`, v0.1.1,
      published 2026-04-23 (`github.com/hellosverre/brreg-mcp`), an unrelated
      Norwegian brreg MCP server. T11 has prepared the npm alias as
      **`@foretak/brreg-mcp`**, which is publishable today; the installed
      command is still `brreg-mcp`. Creating the free npm org `@foretak`
      (<https://www.npmjs.com/org/create>) is a prerequisite. Alternatives and
      the trade-offs are in `SUBMISSIONS.md` § Prerequisites — **decide before
      publishing.** Note also that this means **a competing brreg MCP server
      already exists** with a five-month head start; read it before launch.
- [x] **`hello@foretak.dev` live 2026-09-04** — Cloudflare Email Routing forwards
      it to fargerod@gmail.com (MX + SPF records added, destination verified).
      Railway `REGISTRY_MCP_CONTACT_EMAIL` switched to it, so the User-Agent we
      send to Brønnøysundregistrene now names a real inbox. `legal/terms.md`
      placeholder removed.
- [x] ~~VPS (Hetzner Helsinki or Norwegian)~~ → **deployed on Railway
      2026-09-04** (project `registry-mcp`, region EU west, one replica, volume
      at `/app/data`): **https://registry-mcp-production.up.railway.app** —
      `/health`, lookups, cache persistence, `/mcp` (connects from Claude Code),
      `/v1/stats` all verified live. `deploy-railway.md` is the runbook.
      - The admin key is only in Railway: `railway variable` (or the dashboard)
        — copy it somewhere safe; it unlocks `/v1/stats` and the dashboard.
      - Until `foretak.dev` is bought and `api.foretak.dev` CNAMEd to Railway
        (`railway domain api.foretak.dev`), the live URL is the Railway one.
        `server.json`'s remote URL and every doc still say `api.foretak.dev` —
        do the domain **before** the MCP-registry publish, or swap the URL.
      - Railway Hobby is ~$5/mo + volume; check the billing page once.
- [x] **Official MCP registry — published 2026-09-04**: `io.github.foretak/registry-mcp`
      v0.1.0. NOT via `mcp-publisher login github` from a laptop — that path
      currently refuses org namespaces even for a public Owner with app
      restrictions removed (registry issues #1468/#1527/#1537/#1551). It was
      published by `.github/workflows/publish-mcp.yml` using **GitHub OIDC**,
      which authenticates as the org. **Future releases:** bump `server.json`
      (3 version fields) + PyPI/npm, then either push a `v*` tag or run the
      workflow from the Actions tab. §7.2 below is superseded by this.
- [x] **Smithery — published 2026-09-04** (`fargerod/registry-mcp`, scan found 5 tools):
      https://smithery.ai/servers/fargerod/registry-mcp
- [x] **mcp.so — submission issue open** chatmcp/mcpso#3927 (2026-09-04); **awesome-mcp-servers
      (punkpeye) — PR #13631 open**; appcypher list is archived (skip).
- [~] **Glama — submitted for review 2026-09-04** by Kim (name `registry-mcp`, repo foretak/registry-mcp). When it appears, the orchestrator adds the Glama score badge to awesome-mcp-servers PR #13631 (their bot requires it before merge). Optional: also list the hosted endpoint at https://glama.ai/mcp/connectors.
      - [x] **Dockerfile for Glama's check — done 2026-09-05.** Glama builds the repo's own `Dockerfile` (methodology page) and runs it with no environment, speaking MCP over stdio. The root `Dockerfile` is now dual-mode: `PORT` set → uvicorn (Railway/compose), `PORT` unset → stdio `registry-mcp`. Verified locally both ways (5 tools over stdio; `/health` over HTTP) and redeployed to Railway. `Dockerfile.glama` was removed again. If Glama's UI still offers a Dockerfile field after the claim, paste the root `Dockerfile` as is.
- [x] **MCP Market — already live** (found 2026-09-05 when submitting): auto-indexed
      from GitHub as https://mcpmarket.com/server/registry-10 under the name
      "Registry". Optional: claim it there to fix the name to `registry-mcp`.
- [x] **mcpservers.org — submitted 2026-09-05** (free listing, category Finance,
      contact hello@foretak.dev; "reviewed within 12 hours", confirmation by
      e-mail).
- [ ] ~~Smithery, Glama, mcp.so, MCP Market — each needs a login.~~ **PulseMCP is
      closed to submissions** as of 2026-09-04 and ingests from the official
      registry instead, so #1 covers it. T11 has prepared every manifest and
      written the exact steps per registry in **`SUBMISSIONS.md`**.
- [ ] **A 400×400 PNG icon.** Cline's marketplace requires one, and Smithery,
      mcp.so and the appcypher awesome list all take one. It is the only thing
      blocking the Cline listing (`SUBMISSIONS.md` §10).

---

## 4. Content that must exist before the homepage goes live

- [x] **`legal/terms.md`** — **written by T11.** It covers the NLOD 2.0
      attribution condition (and that the obligation passes to the user), the
      no-warranty and no-affiliation statements, the calendar-year caveat on
      computed deadlines, the 60/min rate limit and bulk-download etiquette, and
      personal data in register records. `static/index.html`'s JSON-LD
      `termsOfService` link now resolves. The contact line's placeholder marker
      was removed 2026-09-04 once `hello@foretak.dev` went live (§3).
- [ ] **NLOD 2.0 attribution** is a licence condition, not a courtesy. Every
      response already carries `source`, `source_url` and `license`; keep the
      footer line on the homepage too.
- [x] `NAMES.md` per build plan §1.1 — written 2026-09-04, including the
      competitor field (8–10 existing Norway/brreg MCP servers, several active).

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

Five articles, three versions each, all written and ready in `content/`. Full
version of this schedule, plus the rules for whoever posts, is in
`content/README.md`.

**One article every two days. dev.to first, Reddit r/mcp the same day, kode24
two days later.** Never post them all at once.

**Status 2026-09-04 (dev.to account `fargeroddotcom`, API key in `~/secrets/registry-mcp/`):**

| # | dev.to | State | Publish on |
|---|---|---|---|
| 1 | https://dev.to/fargeroddotcom/check-a-norwegian-supplier-is-vat-registered-before-you-pay-the-invoice-pb9 | **PUBLISHED** 2026-09-04 | — |
| 2 | https://dev.to/fargeroddotcom/every-filing-deadline-a-norwegian-as-faces-this-quarter-in-one-tool-call-29gc | **PUBLISHED** 2026-09-04 | — |
| 3 | https://dev.to/fargeroddotcom/validate-and-enrich-a-spreadsheet-of-norwegian-orgnrs-with-one-mcp-server-1fei | **PUBLISHED** 2026-09-04 | — |
| 4 | https://dev.to/fargeroddotcom/add-your-countrys-company-registry-to-registry-mcp-in-an-afternoon-1pei | **PUBLISHED** 2026-09-04 | — |
| 5 | https://dev.to/fargeroddotcom/check-a-uk-supplier-at-companies-house-from-claude-code-and-the-same-tool-works-for-norway-4mk8 | **PUBLISHED** 2026-09-04 | — |

Publish a draft with one command (or the *Publish* button in the dev.to dashboard):

```bash
DEVTO_API_KEY=$(cat ~/secrets/registry-mcp/devto-api-key.txt) python content/publish_devto.py publish 4575628
```

Kim chose to publish all five dev.to articles on 2026-09-04 (overriding the 2-day cadence). Reddit r/mcp and kode24 versions are not automated — post them by hand, ideally spread over the next week.

| Day | dev.to (`devto.md`) | r/mcp (`reddit.md`) | kode24 (`no.md`) |
|---|---|---|---|
| 1 | `01-vat-check` | `01-vat-check` | — |
| 3 | `02-deadlines` | `02-deadlines` | `01-vat-check` |
| 5 | `03-enrich-spreadsheet` | `03-enrich-spreadsheet` | `02-deadlines` |
| 7 | `04-add-your-country` | `04-add-your-country` | `03-enrich-spreadsheet` |
| 9 | — | — | `04-add-your-country` |
| 11 | `05-uk-companies-house` | `05-uk-companies-house` | — |
| 13 | — | — | `05-uk-companies-house` |

- [ ] Accounts still needed: a Reddit account with enough karma to self-post
      in r/mcp, and a kode24 contact (they take contributed pieces; email the
      editor rather than waiting for a form). dev.to is done.
- [ ] **Replace the placeholders first.** Every article contains
      `api.foretak.dev` and `github.com/foretak/registry-mcp`. If §1's domain
      or GitHub org came out different, fix all fifteen files before posting.
- [ ] **Re-run the output blocks if the server has changed since they were
      written.** Both registers are live data — Norwegian `employees` counts
      and addresses move, and every UK `due_date`/`days_until` in article 05
      was true on `today=2026-09-04` and drifts as Companies House rolls each
      filing cycle. `content/README.md` has the commands; do not patch a JSON
      block by hand. Article 05's `GB` blocks need `COMPANIES_HOUSE_API_KEY`
      on the server that produces them.
- [x] ~~Article 05 needs a dev.to draft creating~~ — published 2026-09-04 (table above).
- [ ] Post the Reddit text as a self-post and put the dev.to link in the first
      comment, not the body.
- [ ] Reply to every comment within 24 h and log the substance in
      `FEEDBACK.md` — those comments are the Phase 4 decision-gate input.
- [ ] `04-add-your-country` is the recruiting article. Pin the "open an issue
      with your country code and claim it" line. Denmark (CVR) and Sweden
      (Bolagsverket) are named there as first targets, which matches guide
      Step 12.
- [ ] `05-uk-companies-house` is the proof behind article 04's claim, and the
      first article aimed at a non-Norwegian audience. Post it two days after
      04, and consider a UK-developer venue alongside r/mcp.

Note for copy-editors: each article deliberately carries `brreg`,
`organisasjonsnummer` and `orgnr` in its title or first paragraph
(`KEYWORDS.md` §2, last row); article 05 carries `Companies House`,
`company number` and `company registration number` there too (`KEYWORDS.md`
§GB). Do not edit those terms out.

---

## 7. Publishing and registry submissions (T11)

**Status 2026-09-05: everything below has been done once** (0.1.0 and 0.2.0 are
on PyPI, npm and the official MCP registry; see §3 for the per-registry state).
Kept as the runbook for the next release. `SUBMISSIONS.md` is the full
per-registry runbook. For releases after the npm trusted publisher is set up,
§7.5 is the short path.

### 7.1 Publish the packages (do this first)

The official MCP registry validates that the packages in `server.json` exist and
carry ownership markers, so PyPI and npm come before every registry submission.

```bash
# PyPI — canonical, then the alias
uv build
uvx twine upload dist/registry_mcp-0.1.0*
(cd packages/brreg-mcp && uv build && uvx twine upload dist/brreg_mcp-0.1.0*)

# npm — canonical, then the alias (scoped; see §3 for why)
# Create the free org @foretak at https://www.npmjs.com/org/create first.
(cd packages/npm/registry-mcp && npm publish --access public)
(cd packages/npm/brreg-mcp    && npm publish --access public)   # @foretak/brreg-mcp
```

Then re-run the done-check against what is actually on the indexes, from a
machine that has never seen this repo:

```bash
uvx registry-mcp          < tests/fixtures/tools_list.jsonl   # 5 tools
uvx brreg-mcp             < tests/fixtures/tools_list.jsonl   # same 5 tools
npx -y registry-mcp       < tests/fixtures/tools_list.jsonl
npx -y @foretak/brreg-mcp < tests/fixtures/tools_list.jsonl
```

**Ownership markers — do not remove them.** `README.md`'s first line is
`<!-- mcp-name: io.github.foretak/registry-mcp -->` and
`packages/npm/registry-mcp/package.json` carries
`"mcpName": "io.github.foretak/registry-mcp"`. Both must match `server.json`'s
`name` exactly, so if the GitHub org changes, all three change together (§1).

### 7.5 npm without codes — Trusted Publishing (one-time setup, 2 minutes)

Publishing from a laptop needs a passkey approval every time, and npm is
retiring 2FA-bypass tokens for direct publish in January 2027. The
`.github/workflows/publish-npm.yml` workflow publishes both packages via OIDC
instead — once you register it as a trusted publisher **for each package**:

- [x] https://www.npmjs.com/package/registry-mcp/access → **Trusted Publisher**
      → GitHub Actions → Organization or user: `foretak` · Repository:
      `registry-mcp` · Workflow filename: `publish-npm.yml` · Environment: leave
      empty · **"Allow npm publish" ticked** (the form cannot be edited after
      creation) → Save. **Done 2026-09-05.**
- [x] Same at https://www.npmjs.com/package/@foretak/brreg-mcp/access — **done 2026-09-05.**
      Verified the same day: a manual run of `publish-npm.yml` authenticated via
      OIDC for both packages and was refused only with "cannot publish over the
      previously published versions: 0.2.0" (run 33949808903). Tag trigger
      re-enabled in the workflow.
- [x] Then delete the granular tokens `registry-mcp-publish*` at
      https://www.npmjs.com/settings/foretak/tokens — **done 2026-09-05**
      (`registry-mcp-publish-3` deleted; the account now has no tokens at all,
      and the local `npm-token.txt` copy was removed).

After that a release is: bump versions → `git tag v0.x.y && git push --tags` →
both npm packages and the MCP-registry entry publish themselves; PyPI still
uses the token in `~/secrets/registry-mcp/pypi-token.txt` (`uv publish`).

### 7.2 Official MCP registry

```bash
brew install mcp-publisher            # or the curl installer in SUBMISSIONS.md §1

mcp-publisher validate server.json    # NOT `init` — that would overwrite it
mcp-publisher login github            # ← browser, GitHub device flow, foretak org
mcp-publisher publish

curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=registry-mcp" | head -c 800
```

### 7.3 GitHub repo topics, description and labels

Topics cannot be set by a `git push` — it is the web UI or an authenticated
`gh` call. ASCII and hyphenated only, max 20 (`KEYWORDS.md` §2):

```bash
gh repo edit foretak/registry-mcp \
  --add-topic mcp --add-topic mcp-server --add-topic model-context-protocol \
  --add-topic brreg --add-topic bronnoysund --add-topic enhetsregisteret \
  --add-topic organisasjonsnummer --add-topic orgnr --add-topic norway \
  --add-topic company-data --add-topic business-registry --add-topic ai-agents

gh repo edit foretak/registry-mcp \
  --description "Company data for AI agents, any country. MCP server and REST API over national business registries — Norway first (brreg / Enhetsregisteret, orgnr lookup)." \
  --homepage "https://api.foretak.dev"

gh label create "good first issue" --color 7057ff --description "Good for newcomers" --force
gh label create "new country"      --color 0e8a16 --description "A new national registry module" --force
gh label create "norway"           --color 1d76db --description "The NO module" --force
```

Optional extra topics within the cap: `bronnoysundregistrene`,
`company-registry`, `foretak`, `open-data`, `rest-api`, `fastapi`, `python`,
`vat`.

- [x] File the three drafts in `.github/SEED_ISSUES.md` as issues — done
      2026-09-04 as foretak/registry-mcp#1–#3.

### 7.4 Two decisions only you can make

- [ ] **Does the alias get its own MCP-registry entry?** `brreg-mcp` is already
      an alias on PyPI and npm, where keyword search is the discovery mechanism.
      A second registry entry (`io.github.foretak/brreg-mcp`) would double the
      surface but lists the same server twice, which the registry's moderation
      policy discourages. T11's recommendation is **one entry**. Reasoning in
      `SUBMISSIONS.md` §1.
- [ ] **`glama.json`'s `maintainers` is `["foretak"]`**, the org slug, but
      Glama's docs describe the field as GitHub *usernames*. If the claim flow
      does not recognise it, put the personal username there and re-run the
      claim flow — Glama only re-reads the file when you do.

---

## 7.6 Denmark (T16) — CVR access application

- [x] **Application sent 2026-09-05** from fargerod@gmail.com to
      `cvrselvbetjening@erst.dk` (cc `hello@foretak.dev`), subject "Ansøgning om
      system-til-system adgang til CVR-data". It asks two questions: whether a
      Norwegian ENK without a Danish CVR number qualifies, and whether IP
      whitelisting is required. Erhvervsstyrelsen replies with access details and
      a declaration to sign (protected entities); processing is up to 12 business
      days → expect an answer by about **2026-09-23**. Source: datahub.virk.dk
      dataset "System-til-system adgang til CVR-data".
- [ ] When the reply arrives: sign the declaration, store the credentials in
      `~/secrets/registry-mcp/cvr-*.txt`, and tell the orchestrator so T16 can
      be specced (Opus A) the same way as `UK_SPEC.md`.
- Fallback if a Danish CVR number is required: Datafordeler's open CVR services
  (HentCVRData / SoegCVRData) need a Datafordeler web user + service user and an
  access request to ERST with IP whitelisting; the confidential CVRPerson entity
  additionally needs MitID Erhverv. Not started.

---

## 8. Go-to-market outreach — PLACEHOLDER (T14)

`BRREG_MCP_FIRST_KRONE.md` (the go-to-market companion named in
`MULTI_AGENT_BUILD_GUIDE.md`) was **never delivered** to the orchestrator, so
the outreach list that T14 was meant to lift from it does not exist in this
repo. When the file arrives:

- [ ] Drop it in the repo root.
- [ ] Copy its outreach list here as §8.1 — who to contact, in what order,
      with the one-line pitch per segment.
- [ ] Cross-check its pricing assumptions against `BRREG_MCP_BUILD_PLAN.md`
      Phase 5 (free MCP stdio forever; charge for hosted volume; first
      customer 10–30k NOK/month for roadmap input).

Until then, the build plan's own Phase 4 rule applies: **no feature work for
two weeks after launch.** Read the stats dashboard every morning
(`https://api.<domain>/v1/stats/dashboard?key=<REGISTRY_MCP_ADMIN_KEY>`),
log every inbound question in `FEEDBACK.md`, and contact any client with
more than 100 calls (user agent, GitHub issues) to ask what they'd pay for.
Decision gate is day 45 — see `BRREG_MCP_BUILD_PLAN.md` §4.3.

---

## 9. Sequence — the shortest path from here to "an agent found us"

1. §3 names: domain, GitHub org, PyPI, npm org (`@foretak`), inbox, VPS.
   Write them into `NAMES.md`. Decide the npm alias question (§3).
2. §1 search-replace if anything differs from `foretak`.
3. Push the repo, set topics/labels (§7.3), file the three seed issues.
4. Deploy: follow `deploy.md` on the VPS; set `REGISTRY_MCP_CONTACT_EMAIL`,
   `REGISTRY_MCP_ADMIN_KEY`, `REGISTRY_MCP_DOMAIN`. Smoke-test from your phone:
   `https://api.<domain>/v1/NO/company/923609016` and `/status`.
5. Publish packages (§7.1), then the official registry (§7.2), then the rest
   per `SUBMISSIONS.md`.
6. Post the articles on the §6 schedule.
7. Two weeks of watching. Then the day-45 decision gate.
