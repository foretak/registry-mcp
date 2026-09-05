# SUBMISSIONS

Where `registry-mcp` gets listed, what each place actually takes **today**, and
exactly which steps need a human login.

Every process below was checked live on **2026-09-04** by fetching the
registry's own current documentation — not from memory, and not from a blog
post. Two of them had changed since the build plan was written (see
[What changed](#what-changed-since-the-build-plan)). Re-check before publishing
if more than a month has passed.

**Status as of 2026-09-05** (the per-section text below keeps the original
"how to" and each section's own status line):

| # | Target | Manifest in this repo | Needs a login? | Status |
|---|---|---|---|---|
| 1 | [Official MCP registry](#1-official-mcp-registry) | `server.json` + `mcp-name:` marker + `mcpName` | **Yes** — GitHub (`foretak` org) | **Live** — `io.github.foretak/registry-mcp` 0.2.0 (via `publish-mcp.yml`) |
| 2 | [Smithery](#2-smithery) | `static/well-known/mcp/server-card.json` (optional) | **Yes** — Smithery account | **Live** — `fargerod/registry-mcp` |
| 3 | [Glama](#3-glama) | `glama.json` + root `Dockerfile` (stdio when `PORT` unset) | **Yes** — GitHub OAuth | **Listed 2026-09-05 13:45Z** (approval mail) — shows "This server cannot be installed" and no score until Kim **claims** it and pastes the Dockerfile at `/admin/dockerfile`; only servers passing Glama's checks appear in its search |
| 4 | [PulseMCP](#4-pulsemcp) | — | No | **Closed to submissions** — auto-ingests from #1 |
| 5 | [mcp.so](#5-mcpso) | — | **Yes** — GitHub (to file an issue) | **Pending** — chatmcp/mcpso#3927, no reply yet |
| 6 | [MCP Market](#6-mcp-market) | — | No (form takes repo URL + e-mail only) | **Live** — auto-indexed as https://mcpmarket.com/server/registry-10 ("Registry"); resubmission 2026-09-05 answered "already listed" |
| 7 | [awesome-mcp-servers (punkpeye)](#7-awesome-mcp-servers--punkpeye) | — | **Yes** — GitHub (fork + PR) | **Badge added 2026-09-05** (fork commit 0726bb2e on `add-registry-mcp`; line also mentions the UK). Badge renders once Glama has a score → needs #3's claim + Dockerfile |
| 8 | [awesome-mcp-servers (appcypher)](#8-awesome-mcp-servers--appcypher) | — | **Yes** — GitHub (fork + PR) | **Skip** — repo archived |
| 9 | [mcpservers.org (wong2's list)](#9-mcpserversorg--wong2s-awesome-mcp-servers) | — | No login; web form | **Submitted 2026-09-05** (free, Finance; review "within 12 hours", e-mail to hello@foretak.dev) |
| 10 | [Cline MCP Marketplace](#10-cline-mcp-marketplace-bonus) | 400×400 PNG icon (**missing**) | **Yes** — GitHub | Blocked on icon + a README-only install test in Cline |
| — | [GitHub repo topics](#github-repo-topics) | — | **Yes** — GitHub | **Done** — 12 topics set 2026-09-04 |

**Order matters.** Do #1 first: PulseMCP ingests from it automatically, and
several other directories use it as a trust signal. Do #2 after the VPS is live
(T13) — Smithery's current flow needs a public HTTPS URL.

---

## Prerequisites (do these once, before anything below)

### ⚠️ Name availability, checked 2026-09-04

| Index | Name | Status |
|---|---|---|
| PyPI | `registry-mcp` | **Free** (404) |
| PyPI | `brreg-mcp` | **Free** (404) |
| npm | `registry-mcp` | **Free** (404) |
| npm | `brreg-mcp` | **TAKEN** ❌ |

**`brreg-mcp` on npm is already published** — by `hellosverre`
(`sverresig@proton.me`), v0.1.1, first published **2026-04-23**, repo
`github.com/hellosverre/brreg-mcp`, described as *"MCP server for Brønnøysund
Register Centre — Norwegian business registry lookup for Claude Code"*. That is
an unrelated project doing a similar thing, and it owns the name. `npm publish`
of an unscoped `brreg-mcp` will fail with 403.

**What T11 did about it:** `packages/npm/brreg-mcp/package.json` is now
**`@foretak/brreg-mcp`**, which is publishable today. The `bin` name stays
`brreg-mcp`, so the installed command is unchanged; only the install line
becomes `npx -y @foretak/brreg-mcp`. The *PyPI* alias `brreg-mcp` is unaffected —
it is free and `uvx brreg-mcp` works as planned.

**Human decision.** Three options, pick one before publishing:

1. **`@foretak/brreg-mcp`** (what is prepared). Honest, publishable now, keeps
   `brreg` in the name. Loses the bare `npx brreg-mcp` line.
2. **An unscoped near-name** — `brreg-mcp-server`, `mcp-brreg`,
   `norway-company-mcp`. Better for npm's keyword search than a scope; needs a
   rename in `package.json` and in `server.json`'s npm package identifier.
3. **Ask `hellosverre`** whether they would transfer or share the name. Slowest,
   and the answer is probably no.

Whichever you pick, `server.json` currently names the **npm package
`registry-mcp`** only, so the official-registry submission is unaffected.

Worth knowing regardless: **there is already a competing brreg MCP server**, and
it has had a five-month head start on npm. Read
`github.com/hellosverre/brreg-mcp` before launch — what it does *not* do is the
argument for this one.

### Then

1. **Publish to PyPI and npm first.** The official registry validates that the
   packages named in `server.json` exist and carry the ownership markers.

   ```bash
   # PyPI — both distributions are already built in ./dist and ./packages/brreg-mcp/dist
   uv build
   uvx twine upload dist/registry_mcp-0.1.0*
   (cd packages/brreg-mcp && uv build && uvx twine upload dist/brreg_mcp-0.1.0*)

   # npm — publish the canonical name first, then the (scoped) alias
   (cd packages/npm/registry-mcp && npm publish --access public)
   (cd packages/npm/brreg-mcp    && npm publish --access public)   # @foretak/brreg-mcp
   ```

   The npm scope `@foretak` must exist and be owned by the account: create it at
   <https://www.npmjs.com/org/create> (a free public org), or `npm publish` will
   reject the scoped name.

   Needs: a **PyPI account** (and an API token in `~/.pypirc` or `TWINE_*` env
   vars) and an **npm account** (`npm login`).

2. **Verify from a clean machine** — the build plan's §3.2 done-check:

   ```bash
   uvx registry-mcp            < tests/fixtures/tools_list.jsonl   # 5 tools
   uvx brreg-mcp               < tests/fixtures/tools_list.jsonl   # same 5 tools
   npx -y registry-mcp         < tests/fixtures/tools_list.jsonl
   npx -y @foretak/brreg-mcp   < tests/fixtures/tools_list.jsonl
   ```

   Locally, before publishing, the same check runs against the built artifacts:

   ```bash
   uvx --from dist/registry_mcp-0.1.0-py3-none-any.whl registry-mcp < tests/fixtures/tools_list.jsonl
   REGISTRY_MCP_SPEC=$PWD/dist/registry_mcp-0.1.0-py3-none-any.whl \
     node packages/npm/registry-mcp/bin/registry-mcp.js < tests/fixtures/tools_list.jsonl
   ```

3. **Repo public**, `LICENSE` present, README rendering — several directories
   scrape the README and will list whatever is there.

---

## 1. Official MCP registry

- **Registry:** <https://registry.modelcontextprotocol.io>
- **Docs:** <https://github.com/modelcontextprotocol/registry> → `docs/modelcontextprotocol-io/quickstart.mdx`
- **Server name:** `io.github.foretak/registry-mcp`
- **Manifest:** [`server.json`](server.json) — already written and validated by T05

### Schema check (2026-09-04)

`2025-12-11` is **still the current schema**. Probed
`static.modelcontextprotocol.io` for `2026-01-15`, `2026-03-01`, `2026-06-01`,
`2026-07-01`, `2026-09-01` → all **404**; `2025-12-11` → **200**; and a live
`GET https://registry.modelcontextprotocol.io/v0/servers?limit=1` returns
entries carrying that same `$schema`. `server.json` needs no schema change.

Re-validate before publishing:

```bash
uv run --with check-jsonschema --no-project check-jsonschema \
  --schemafile https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json \
  server.json
```

### Ownership markers — done in this repo

The registry refuses to publish unless each named package proves the publisher
owns it. Both markers must match the `name` in `server.json` **exactly**:

| Package | Marker | Where | Done |
|---|---|---|---|
| PyPI `registry-mcp` | `<!-- mcp-name: io.github.foretak/registry-mcp -->` | first line of `README.md` (the `readme` PyPI renders) | ✅ |
| npm `registry-mcp` | `"mcpName": "io.github.foretak/registry-mcp"` | `packages/npm/registry-mcp/package.json` | ✅ |

Change the GitHub org and **all three** of these change together, or publishing
is rejected at submit time (`HUMAN_TODO.md` §1).

### Steps

```bash
# 1. Install the publisher CLI
brew install mcp-publisher
# ...or, without Homebrew:
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" \
  | tar xz mcp-publisher && sudo mv mcp-publisher /usr/local/bin/

# 2. Validate the manifest we already have (do NOT run `mcp-publisher init` —
#    it would overwrite server.json with a generated template)
mcp-publisher validate server.json

# 3. Log in.  ← HUMAN: opens a browser, GitHub device flow.
#    The account must own (or be an admin of) the `foretak` org, because the
#    registry authenticates `io.github.foretak/*` against that namespace.
mcp-publisher login github

# 4. Publish
mcp-publisher publish

# 5. Confirm it is live
curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=registry-mcp" | head -c 800
```

**Needs a human login: yes** — `mcp-publisher login github`, as a member of the
`foretak` GitHub org.

In CI later, `mcp-publisher login github-oidc` does the same thing without a
browser (see `docs/modelcontextprotocol-io/github-actions.mdx` upstream).

### Should `brreg-mcp` get its own registry entry?

**Human decision.** A second entry `io.github.foretak/brreg-mcp` would double
the surface an agent can find, but the alias is the *same server*, and the
registry's moderation policy discourages duplicate listings. Recommendation:
**publish one entry** and let the alias do its work on PyPI and npm, where
keyword search is the discovery mechanism. If you do decide to publish it, it
needs its own `server.json`, and `packages/brreg-mcp/README.md` needs its own
`<!-- mcp-name: io.github.foretak/brreg-mcp -->` marker.

### Version bumps

`server.json` carries `0.1.0` in **three** places (server, PyPI package, npm
package). All three must move together at each release — the schema rejects
`latest` and ranges.

---

## 2. Smithery

- **Site:** <https://smithery.ai> · publish at <https://smithery.ai/new>
- **Docs:** <https://smithery.ai/docs/build/publish>

### ⚠️ `smithery.yaml` is gone — do not write one

The build plan and most third-party guides still say "add a `smithery.yaml`".
**Smithery's current documentation does not mention `smithery.yaml` anywhere**;
the full docs index (`https://smithery.ai/docs/llms.txt`, fetched 2026-09-04)
has no config-file page at all. Publishing is now one of two flows:

| Flow | What it takes | Fits us? |
|---|---|---|
| **URL** (bring your own hosting) | A public **HTTPS Streamable HTTP** endpoint | ✅ — `https://api.foretak.dev/mcp` |
| **Local** (MCPB bundle) | A prepared `.mcpb` bundle | Possible later; not needed |

So: **no manifest to add to the repo**, and this step is **blocked until T13
has the VPS serving `https://api.foretak.dev/mcp`**.

### Steps (after deploy)

1. Confirm the endpoint answers from outside the box:
   ```bash
   curl -sS -X POST https://api.foretak.dev/mcp \
     -H 'Content-Type: application/json' \
     -H 'Accept: application/json, text/event-stream' \
     --data @tests/fixtures/tools_list.jsonl | head -c 400
   ```
2. Go to <https://smithery.ai/new>. ← **HUMAN: Smithery account (GitHub sign-in).**
3. Enter `https://api.foretak.dev/mcp` and complete the publishing flow.
4. Smithery **scans the server automatically** to extract tools, prompts and
   resources. Ours is public and unauthenticated, so the scan should complete on
   its own.
5. Add the keyword list from `KEYWORDS.md` §1 wherever the flow offers tags or a
   description. Do not re-word them per site.

### Optional: the static server card

If the automatic scan fails, Smithery reads metadata from
`/.well-known/mcp/server-card.json`. One is prepared in this repo at
**`static/well-known/mcp/server-card.json`**, generated from the real
`tools/list` output of the built wheel (5 tools, real input schemas, the
`explain_company` prompt).

It is **not currently served** — serving it needs a route in `api/main.py`
(owned by T06/T13), e.g. mounting `static/well-known/` at `/.well-known/`. Only
do that if the scan fails; an unused well-known path is not worth a route.

### CLI alternative

```bash
smithery mcp publish "https://api.foretak.dev/mcp" -n @foretak/registry-mcp
```

**Needs a human login: yes** — Smithery account.

**Status (2026-09-04): published** via `smithery mcp publish https://api.foretak.dev/mcp -n fargerod/registry-mcp`
(API key from Kim's Smithery account; namespace is `fargerod`, not `foretak` — Smithery namespaces follow the
GitHub login). Listing: <https://smithery.ai/servers/fargerod/registry-mcp>. Re-run the same command after
each release; it re-scans the endpoint.

**2026-09-05 — description was empty, listing invisible.** The CLI publish sets no description, and
Smithery search is full-text + semantic, so `fargerod/registry-mcp` appeared in no search (useCount 0;
research library `04-mcp-and-agent-ecosystem/`). Fixed via the registry API, which the CLI does not expose:

```bash
curl -X PATCH https://api.smithery.ai/servers/fargerod%2Fregistry-mcp \
  -H "Authorization: Bearer $(cat ~/secrets/registry-mcp/smithery-api-key.txt)" \
  -H "Content-Type: application/json" \
  -d '{"displayName": "...", "description": "...", "repositoryUrl": "https://github.com/foretak/registry-mcp"}'
```

Verified: `registry.smithery.ai/servers?q=brreg organisasjonsnummer` now returns us (4th). `repositoryUrl`
came back `null` after the PATCH — re-check the field name in
<https://smithery.ai/docs/api-reference/servers/update-a-server.md> if the repo link matters. Re-apply the
PATCH after any `smithery mcp publish` in case a re-scan resets it.

---

## 3. Glama

**Status (2026-09-05): approved and listed** at <https://glama.ai/mcp/servers/foretak/registry-mcp> (mail 13:45Z). The approval mail says: claim the server under the admin settings on the server page, then "provide a Dockerfile via your server's admin page on Glama: https://glama.ai/mcp/servers/foretak/registry-mcp/admin/dockerfile … it does not need to be added to your repository. Only servers that pass these checks are listed in search results." Until then the page reads "This server cannot be installed" and the score badge is 404. Paste the root `Dockerfile` (dual-mode, stdio when `PORT` is unset). Awesome-mcp-servers PR #13631 already carries the badge line (§7).

- **Site:** <https://glama.ai/mcp/servers>
- **Manifest:** [`glama.json`](glama.json) — **created by T11**

Glama crawls GitHub and will very likely list the repo **without any action**
once it is public. `glama.json` is not what gets you listed; it is what lets you
**claim** the listing, which is what unlocks editing the name and description,
usage reports and review notifications.

```json
{
  "$schema": "https://glama.ai/mcp/schemas/server.json",
  "maintainers": ["foretak"]
}
```

The schema (fetched 2026-09-04 from `https://glama.ai/mcp/schemas/server.json`)
requires exactly one property, `maintainers`: an array of **GitHub usernames**.
The file must sit in the **repository root**, which it does.

> **Check before launch:** `maintainers` currently contains `"foretak"`, the
> org slug. Glama's own docs describe it as GitHub *usernames*. If the claim
> flow does not recognise it, replace it with the **personal GitHub username**
> that will do the claiming, then re-run the claim flow.

### Steps

1. Push `glama.json` with the repo.
2. Find the server at `https://glama.ai/mcp/servers/foretak/registry-mcp` (or
   search for `registry-mcp`); if it is not there yet, use **Add Server**.
3. Run the **Claim ownership** flow. ← **HUMAN: sign in with GitHub.**
   - Personal repo: GitHub auth alone is enough.
   - **Org-owned repo (ours): `glama.json` is required** — this is why it exists.
4. After **any** later edit to `glama.json`, run the claim flow again — that is
   what triggers Glama to re-read the file.
5. Once claimed, set the description from `pyproject.toml` and the keywords from
   `KEYWORDS.md` §1.
6. **Dockerfile (required since 2026-09 for the listing check).** Glama's bot on
   awesome-mcp-servers PR #13631: "you must add Dockerfile directly to Glama.
   For checks to pass, we only need the server to start and respond to
   introspection requests." Their [methodology](https://glama.ai/mcp/methodology)
   says the build uses a Dockerfile "checked into the repository" when there
   is one, and their inspector runs the container with no environment and
   speaks MCP over **stdio**. The root `Dockerfile` is therefore dual-mode
   since 2026-09-05: `PORT` set → uvicorn (Railway injects it; compose sets
   `PORT=8080`), `PORT` unset → `registry-mcp` over stdio. Verified locally:
   `docker run --rm -i registry-mcp:latest < tests/fixtures/tools_list.jsonl`
   answers `initialize` (registry-mcp 0.2.0) and `tools/list` (5 tools), and
   `-e PORT=8091` serves `/health`. If the claimed listing still offers a
   Dockerfile field, paste the root `Dockerfile` unchanged.

**Needs a human login: yes** — GitHub OAuth on glama.ai.

---

## 4. PulseMCP

- **Site:** <https://www.pulsemcp.com> · submit page: <https://www.pulsemcp.com/submit>

**Closed.** As of 2026-09-04 the submit page reads:

> "We are not accepting new MCP server or client submissions right now, and we
> are not making changes to existing listings."

...while they rework their "directory pipeline and listing management". Their
own recommendation is to **publish to the official MCP registry first**, and
listings will be "picked up automatically" when they resume.

**Action: none, beyond doing #1.** Re-check `https://www.pulsemcp.com/submit`
about a month after launch. **No login needed** while it is closed.

---

## 5. mcp.so

- **Site:** <https://mcp.so> · submit: <https://mcp.so/submit?type=server>
- **Backing repo:** [`chatmcp/mcpso`](https://github.com/chatmcp/mcpso) —
  "directory for Awesome MCP Servers", homepage `https://mcp.so`, issues open
  (3,101 open at time of writing: that is where submissions land)
- **Status:** submitted 2026-09-04 via Route A —
  <https://github.com/chatmcp/mcpso/issues/3927> (open; no issue template on
  the repo, body as below plus the official-registry name).

Two routes; the GitHub issue is free and is the one we use.

### Route A — GitHub issue (free, preferred)

Open an issue on `chatmcp/mcpso` with:

```
Title: registry-mcp — company data for AI agents from national business registries (Norway: brreg / Enhetsregisteret)

- Name: registry-mcp
- Repo: https://github.com/foretak/registry-mcp
- Homepage: https://api.foretak.dev
- Transport: Streamable HTTP (https://api.foretak.dev/mcp) and stdio (uvx registry-mcp / npx registry-mcp)
- Tools: 5 — lookup_company, search_company, company_deadlines, validate_company_id, list_countries
- Description: Look up a company in a national business register by its national
  identifier, search by name, check VAT registration, and compute statutory
  filing deadlines. First module: Norway — Brønnøysundregistrene /
  Enhetsregisteret, by organisasjonsnummer (orgnr). Also published as brreg-mcp.
- Tags: brreg, brønnøysund, brønnøysundregistrene, enhetsregisteret,
  organisasjonsnummer, orgnr, org.nr, norway company lookup,
  norwegian business registry, foretak, company registry, mcp
- License: MIT (code) / NLOD 2.0 (data)
```

### Route B — the web form

<https://mcp.so/submit?type=server>. Same fields. There is a **paid "publish
immediately"** tier; the free tier is a review queue. Do not pay for it.

**Needs a human login: yes** — a GitHub account to file the issue (Route A), or
whatever the form asks for (Route B).

> Note: `https://mcp.so/` and `https://mcp.so/submit` both return **403** to
> automated fetches, so the form's exact fields could not be read directly; the
> field list above is from the site's own indexed submission guidance plus the
> backing repo. Expect it to ask for roughly: name, one-sentence description,
> tool count, transport, repo URL, homepage, optional icon.

---

## 6. MCP Market

- **Site:** <https://mcpmarket.com> · submit: <https://mcpmarket.com/submit>
- **App / account:** <https://app.mcpmarket.com/signup>
- **Docs:** <https://docs.mcpmarket.com/docs>

Submission is a form that takes the **GitHub repository URL**, then a review
before the listing goes live.

### Steps

1. Create an account at <https://app.mcpmarket.com/signup>. ← **HUMAN.**
2. Go to <https://mcpmarket.com/submit>.
3. Submit `https://github.com/foretak/registry-mcp` with the description and
   tags from #5 above.
4. Wait for review.

**Needs a human login: yes** — MCPmarket account.

> **Could not verify directly:** `https://mcpmarket.com/submit` returned
> **429 Too Many Requests** on every attempt on 2026-09-04, so the exact form
> fields are unconfirmed. The steps above come from the site's own indexed
> submission page and docs. Check the live form before filling it in.

---

## 7. awesome-mcp-servers — punkpeye

- **Repo:** <https://github.com/punkpeye/awesome-mcp-servers> (the big one)
- **Rules:** its `CONTRIBUTING.md`
- **Process:** fork → edit `README.md` → PR
- **Status:** PR opened 2026-09-04 —
  <https://github.com/punkpeye/awesome-mcp-servers/pull/13631> (open; from fork
  `foretak/awesome-mcp-servers`, branch `add-registry-mcp`, inserted between
  `flox-foundation/flox-mcp` and `Fund-z/fundzwatch-mcp`).

### Rules that actually get PRs merged here

- Server name **linked to its repository**, then a brief description.
- Put it in the **right category** and keep the category **alphabetical**.
- One server per line; match the existing formatting exactly.
- Legend emoji after the link: `🎖️` official implementation · `🐍` Python
  codebase · `☁️` cloud service · `🏠` local service.
- Its `CONTRIBUTING.md` notes that PRs titled with a trailing `🤖🤖🤖` (agent
  PRs) are merged faster.

### Category

**`### 💰 Finance & Fintech`** — that is where the closest analogue already
lives: `george-kozlitin/borme-mcp`, Spain's official company registry (BORME).
Alphabetical position: `foretak/registry-mcp` sorts under `f`.

### The line to add

```markdown
- [foretak/registry-mcp](https://github.com/foretak/registry-mcp) 🐍 ☁️ 🏠 - Company data from national business registries, one shape per country. Norway first: Brønnøysundregistrene / Enhetsregisteret (brreg) — look up a company by organisasjonsnummer (orgnr), search by name, check VAT (MVA) registration, and compute statutory filing deadlines (årsregnskap, skattemelding, mva-melding, a-melding) from a date you choose. Adding a country is one folder and four methods. Hosted at `https://api.foretak.dev/mcp`, or `uvx registry-mcp`. Also published as `brreg-mcp`.
```

Add `🎖️` only if we are the official implementation of something — we are not;
leave it off. Add the Glama score badge only after Glama has indexed the repo
(most entries carry one; it is not required).

### Steps

```bash
gh repo fork punkpeye/awesome-mcp-servers --clone --remote
cd awesome-mcp-servers
git checkout -b add-registry-mcp
# insert the line above, alphabetically, in ### 💰 Finance & Fintech
git commit -am "Add foretak/registry-mcp to Finance & Fintech"
git push -u origin add-registry-mcp
gh pr create --title "Add registry-mcp — national company registries (Norway: brreg / Enhetsregisteret) 🤖🤖🤖" \
  --body "Adds \`foretak/registry-mcp\` to Finance & Fintech, alphabetically. MCP server + REST API over national business registries; first module Norway (Brønnøysundregistrene / Enhetsregisteret) with lookup by organisasjonsnummer, name search, VAT status and computed filing deadlines. MIT; data NLOD 2.0. \`uvx registry-mcp\`, or hosted Streamable HTTP at https://api.foretak.dev/mcp."
```

**Needs a human login: yes** — GitHub (fork + PR). And a maintainer has to merge
it; that is out of our hands.

---

## 8. awesome-mcp-servers — appcypher

- **Repo:** <https://github.com/appcypher/awesome-mcp-servers>
- **Rules:** its `CONTRIBUTING.md` — search for duplicates first, **one PR per
  suggestion**, add to the **bottom of the relevant category**, keep it
  alphabetical, mind spelling and trailing whitespace.
- **Status:** blocked 2026-09-04 — the repo is **archived** (last push
  2026-05-06; `gh api repos/appcypher/awesome-mcp-servers` → `archived: true`),
  so GitHub refuses new PRs. The change is ready on fork
  `foretak/awesome-mcp-servers-1`, branch `add-registry-mcp`
  (<https://github.com/foretak/awesome-mcp-servers-1/tree/add-registry-mcp>);
  open the PR only if the repo is ever unarchived. No successor list is named in
  its README.

Different house style from #7: entries lead with a small `<img>` favicon, then
the bold-free `[Name](url)`, then ` - ` and the description. Descriptions here
are **one short sentence** — do not paste the long one from #7.

### Category

**`## 💹 Finance`**.

### The line to add

```markdown
- <img src="https://data.brreg.no/favicon.ico" height="14" alt="Brønnøysundregistrene" /> [registry-mcp](https://github.com/foretak/registry-mcp) - Company data from national business registries: Norway (Brønnøysundregistrene / Enhetsregisteret) lookup by organisasjonsnummer, name search, VAT status and statutory filing deadlines.
```

> The `<img>` points at the upstream register's favicon, which is *their* mark,
> not ours. If that feels wrong — it reasonably might — drop the `<img>` tag
> entirely; plenty of entries in that list have none. Better still, use our own
> icon once one exists (see #10).

**Needs a human login: yes** — GitHub (fork + PR).

---

## 9. mcpservers.org — wong2's awesome-mcp-servers

- **Repo:** <https://github.com/wong2/awesome-mcp-servers>
- **Site:** <https://mcpservers.org>
- **Submit:** <https://mcpservers.org/submit>

**Do not open a PR.** The repo README says, at the top:

> "We do not accept PRs. Please submit your MCP on the website:
> https://mcpservers.org/submit"

### Form values

| Field | Value |
|---|---|
| Server Name | `registry-mcp` |
| Short Description | The company registry MCP: company data for AI agents from national business registries. Norway (brreg / Enhetsregisteret — orgnr lookup, name search, VAT registration, filing deadlines) and United Kingdom (Companies House — company number lookup, search, accounts and confirmation statement deadlines). |
| Link | `https://github.com/foretak/registry-mcp` |
| Category | Finance / Data (pick the closest the form offers) |
| Contact Email | `hello@foretak.dev` |

There is a **$39 one-time "premium review"** option (faster approval, "Official"
badge, dofollow link). The free listing is the same listing. **Do not pay it**
unless there is a reason beyond impatience.

**Needs a human login: no** — a web form with a contact email. But it does need
the **contact inbox to exist** (`HUMAN_TODO.md` §3), because that is where the
confirmation goes.

---

## 10. Cline MCP Marketplace (bonus)

- **Repo:** <https://github.com/cline/mcp-marketplace>
- **Process:** open an issue from their template

Not in the task list, but it is a large install surface (Cline users install
directly from it) and the submission is cheap.

Requirements, verbatim from their README:

1. **GitHub repo link** — "A direct link to the MCP server's repository".
2. **A 400×400 PNG logo** — "that will serve as your server's icon".
3. **Justification** — "Briefly explain why your server is awesome and/or how it
   can benefit other Cline users."
4. **Testing confirmation** — you must "confirm that you have tested giving
   Cline just your `README.md` and/or the `llms-install.md`".

`llms-install.md` is **not required**: "A well-written README with clear
installation instructions is usually sufficient."

**Blocked:** we have **no 400×400 PNG icon**. One needs to be made — it is also
useful for #2, #5 and #8. That is the only thing standing between us and this
listing.

**Needs a human login: yes** — GitHub, plus someone to actually run the
README-only install test in Cline before claiming they did.

---

## GitHub repo topics

Topics are **ASCII and hyphenated only** and capped at 20 (`KEYWORDS.md` §2).
These twelve are the required set:

```
mcp  mcp-server  model-context-protocol  brreg  bronnoysund  enhetsregisteret
organisasjonsnummer  orgnr  norway  company-data  business-registry  ai-agents
```

One authenticated command sets all of them (topics **cannot** be set from a
plain `git push` — it is the web UI or an authenticated API call):

```bash
gh repo edit foretak/registry-mcp \
  --add-topic mcp \
  --add-topic mcp-server \
  --add-topic model-context-protocol \
  --add-topic brreg \
  --add-topic bronnoysund \
  --add-topic enhetsregisteret \
  --add-topic organisasjonsnummer \
  --add-topic orgnr \
  --add-topic norway \
  --add-topic company-data \
  --add-topic business-registry \
  --add-topic ai-agents
```

Optional extras, within the cap of 20, if you want them:
`bronnoysundregistrene`, `company-registry`, `foretak`, `open-data`,
`rest-api`, `fastapi`, `python`, `vat`.

Also worth setting in the same pass:

```bash
gh repo edit foretak/registry-mcp \
  --description "Company data for AI agents, any country. MCP server and REST API over national business registries — Norway first (brreg / Enhetsregisteret, orgnr lookup)." \
  --homepage "https://api.foretak.dev"
```

And the labels the seeded issues need:

```bash
gh label create "good first issue" --color 7057ff --description "Good for newcomers" --force
gh label create "new country"      --color 0e8a16 --description "A new national registry module" --force
gh label create "norway"           --color 1d76db --description "The NO module" --force
```

Then file the three drafts in [`.github/SEED_ISSUES.md`](.github/SEED_ISSUES.md).

---

## What changed since the build plan

Two of the build plan's assumptions (§3.3) are out of date. Both were verified
against the sites' own current docs on 2026-09-04:

1. **Smithery no longer uses `smithery.yaml`.** Its entire current docs index has
   no config-file page; publishing is URL-based or an MCPB bundle. We therefore
   ship **no `smithery.yaml`** — writing one would be cargo cult. See #2.
2. **PulseMCP is closed to submissions** and ingests from the official registry
   instead. See #4.

One thing the build plan did not know about at all:

3. **The official registry now requires package-ownership markers** — a
   `mcp-name:` line in the PyPI README and an `mcpName` field in npm's
   `package.json`. Both are in place. Without them, publishing is rejected. See #1.

---

## Human login summary

| Account | Needed for |
|---|---|
| **PyPI** (+ API token) | Prerequisite: publish `registry-mcp` and `brreg-mcp` |
| **npm** (`npm login`) | Prerequisite: publish `registry-mcp` and `brreg-mcp` |
| **GitHub**, member of the `foretak` org | #1 (`mcp-publisher login github`), #3 (claim), #5 (issue), #7, #8 (PRs), #10 (issue), topics, labels, seeded issues |
| **Smithery** (GitHub sign-in) | #2 — *after* the VPS is live |
| **MCPmarket** | #6 |
| A **real inbox** at `hello@<domain>` | #9's confirmation, the JSON-LD, and the upstream `User-Agent` |

Nothing on this page can be completed by an agent alone.
