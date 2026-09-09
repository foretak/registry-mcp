# SUBMISSIONS

Where `registry-mcp` gets listed, what each place actually takes **today**, and
exactly which steps need a human login.

Every process below was checked live on **2026-09-04** by fetching the
registry's own current documentation — not from memory, and not from a blog
post. Two of them had changed since the build plan was written (see
[What changed](#what-changed-since-the-build-plan)). Re-check before publishing
if more than a month has passed.

**Status as of 2026-09-07 19:33Z** (re-audited end to end after the 0.3.0/Sweden
release — full log in [Audit — 2026-09-07](#audit--2026-09-07); the per-section
text below keeps every original "how to" plus each section's own status line,
corrections appended rather than erased):

| # | Target | Manifest in this repo | Needs a login? | Status |
|---|---|---|---|---|
| 1 | [Official MCP registry](#1-official-mcp-registry) | `server.json` + `mcp-name:` marker + `mcpName` | **Yes** — GitHub (`foretak` org) | **Live and correct** — `io.github.foretak/registry-mcp` **0.3.0**, `isLatest: true`, countries `[GB, NO, SE]`, re-verified live 2026-09-07 19:15Z. No action needed. |
| 2 | [Smithery](#2-smithery) | `static/well-known/mcp/server-card.json` (optional) | **Yes** — Smithery account | **Live, was stale, fixed 2026-09-07** — `fargerod/registry-mcp`. Description named only Norway+UK and promised "Denmark (CVR) next" (not shipped); PATCHed via the documented API (credential in `~/secrets/`) to name all three countries and drop the false promise; `iconUrl` set (was `null`). `registry.smithery.ai`'s public search index lags the write host by some minutes–hours, as it did 2026-09-05 — re-check in a day. |
| 3 | [Glama](#3-glama) | `glama.json` + admin-form build spec (Python 3.12, `uv sync`, mcp-proxy) | **Yes** — GitHub OAuth | **Live and installable, but stale** — still shows **0.2.0** and a Norway+UK-only description as of 2026-09-07 19:15Z; no Sweden. No documented API/credential exists for Glama (unlike Smithery) — fix needs a human on the admin page. See the ready block in [§3](#3-glama). |
| 4 | [PulseMCP](#4-pulsemcp) | — | No | **Closed to submissions** — auto-ingests from #1. Re-confirmed 2026-09-07, identical wording. |
| 5 | [mcp.so](#5-mcpso) | — | **Yes** — GitHub (to file an issue) | **Pending, unchanged, and stale** — chatmcp/mcpso#3927, no reply after 3 days; issue text is still Norway-only. Backing repo looks largely inactive (3,170 open issues, code not pushed since 2025-03-26) — see the judgement-call note in [§5](#5-mcpso) on why this was flagged rather than edited. |
| 6 | [MCP Market](#6-mcp-market) | — | No (form takes repo URL + e-mail only) | **Live** (per the 2026-09-05 "already listed" resubmission answer) — auto-indexed as https://mcpmarket.com/server/registry-10. Still unverifiable directly: 429 on every attempt again 2026-09-07. |
| 7 | [awesome-mcp-servers (punkpeye)](#7-awesome-mcp-servers--punkpeye) | — | **Yes** — GitHub (fork + PR) | **UK+Norway entry MERGED** 2026-09-07T13:14:35Z (PR [#13631](https://github.com/punkpeye/awesome-mcp-servers/pull/13631), live in `README.md` today, badge renders) — **the local/stdio listing; it stands unchanged.** Sweden follow-up **PR [#13893](https://github.com/punkpeye/awesome-mcp-servers/pull/13893) closed by the maintainer 2026-09-08** (not merged, not by us) — hosted/remote servers belong on a sister list instead; see [§13](#13-awesome-remote-mcp-servers--punkpeye). |
| 8 | [awesome-mcp-servers (appcypher)](#8-awesome-mcp-servers--appcypher) | — | **Yes** — GitHub (fork + PR) | **Skip** — repo still archived (re-checked 2026-09-07: `archived: true`, last push 2026-05-06). |
| 9 | [mcpservers.org (wong2's list)](#9-mcpserversorg--wong2s-awesome-mcp-servers) | — | No login; web form | **LIVE — approved 2026-09-05 22:02Z** (https://mcpservers.org/servers/foretak/registry-mcp; badge offered; approval mail to hello@foretak.dev). **Freshness unverified 2026-09-07** — the page now sits behind a Cloudflare bot challenge for automated fetches (curl and WebFetch both got the "Just a moment…" interstitial, not the real page). Needs a human with a real browser; no PR path and no documented API either way. |
| 10 | [Cline MCP Marketplace](#10-cline-mcp-marketplace-bonus) | 400×400 PNG icon (**now present**) | **Yes** — GitHub | **Icon blocker cleared** (`static/icon.png`, confirmed 400×400 PNG, shipped 2026-09-05). Still blocked on Cline's own requirement to *confirm you tested* a README-only install in Cline — no Cline runtime available to an agent here, and claiming a test that didn't happen would break the "keep it factual" rule. Ready block in [§10](#10-cline-mcp-marketplace-bonus). |
| 11 | [Anthropic Connectors Directory](#11-anthropic-connectors-directory) | `content/anthropic-connectors-submission.md` (every portal field pre-filled) | **Yes** — Claude.ai **Team/Enterprise** org (not yet bought) | **PENDING — package ready 2026-09-09 (T50), Kim submits.** The only surface in the ecosystem that proactively suggests a connector to a user who never went looking (Suggested Connectors; same catalog serves Claude.ai, Cowork, Desktop, mobile **and Claude Code**). Peers in this exact category are listed — Pappers, Firmenbuch, D&B — and **no Nordic or UK register is**. Blockers: Team plan ≈$50/mo (Kim's purchase), and **the served privacy policy is stale** (says NO+UK, Sweden live since 09-07) which is an *immediate-rejection* criterion — fix `legal/privacy.md` first. Ranking is usage-based, so book this as a position, not traffic. `HUMAN_TODO.md` §7.9. |
| 12 | [Claude plugin directory](#12-claude-plugin-directory) | `plugins/registry-mcp/` (rebuilt as a job by T50) + `.claude-plugin/marketplace.json` | **Yes** — individual **Console** login (free) | **PENDING — plugin ready 2026-09-09 (T50), Kim submits.** Free, no Team plan needed, ~5 minutes at <https://platform.claude.com/plugins/submit>; takes a public GitHub link. Plugin is no longer a bare `.mcp.json`: skill + `/check-supplier` + `/filing-deadlines` + `/enrich-company-list`; `claude plugin validate --strict` passes on all four targets. Expect the **community** marketplace, which users add by hand — a catalog, not a channel. `HUMAN_TODO.md` §7.9. |
| 13 | [awesome-remote-mcp-servers (punkpeye)](#13-awesome-remote-mcp-servers--punkpeye) | — | **Yes** — GitHub (star + fork + PR) | **Open, blocked on the Glama connector badge (Kim).** PR [#146](https://github.com/punkpeye/awesome-remote-mcp-servers/pull/146), opened 2026-09-09 — `Company Check` in Finance. CI's own checks: `endpoint-ok` (the live MCP `initialize` handshake passed), **`missing-connector`** (this list requires a Glama *connector* badge — a different product from §3 — and we don't have one yet; see [§14](#14-glama-connectors)). Steps for Kim in `HUMAN_TODO.md` §7.11(c); once the connector exists, pushing the badge line to branch `add-company-check` on the `foretak/awesome-remote-mcp-servers` fork is a one-commit follow-up. |
| 14 | [Glama connectors](#14-glama-connectors) | — | **Yes** — GitHub OAuth, Glama's claim flow | **PENDING — not yet listed, not yet attempted.** Surfaced by §13's bot, not chased before that. A separate product from §3's `glama.ai/mcp/servers` listing (itself still stale at 0.2.0 — unchanged from the last check). Kim's admin page. `HUMAN_TODO.md` §7.11(c). |
| — | [GitHub repo topics](#github-repo-topics) | — | **Yes** — GitHub | **Topics done** — 20/20 slots, re-verified 2026-09-07 (includes `bolagsverket`, `sweden`, `united-kingdom`). The repo **description** this section tells you to set was still the Norway-only sentence verbatim from this file — fixed 2026-09-07 via `gh repo edit`; this file's own suggested command below is now updated to match so nobody re-pastes the stale one. |

**Order matters.** Do #1 first: PulseMCP ingests from it automatically, and
several other directories use it as a trust signal. Do #2 after the VPS is live
(T13) — Smithery's current flow needs a public HTTPS URL.

---

## Audit — 2026-09-07

Full re-audit after the 0.3.0 release (three countries, tag `v0.3.0`, all four
package targets published — see `PROGRESS.md`'s "0.3.0 RELEASED" line). Every
directory below was **fetched live tonight**, not assumed from the table above.
Ground truth used throughout: `server.json`, `pyproject.toml`, `git log`/`git
tag`, and live queries to the *directories themselves* — never
`https://api.foretak.dev` (excluded by standing instruction, to keep it out of
usage stats) and never Bolagsverket/Companies House directly.

**Confirmed correct, no action:**
- **Official MCP registry** — `io.github.foretak/registry-mcp` 0.3.0 is
  `isLatest: true` with `countries: [GB, NO, SE]`, the full keyword set and the
  icon. This is the one everything else (PulseMCP in principle, and several
  directories as a trust signal) is supposed to trust — it's right.
- **PyPI** `registry-mcp` and `brreg-mcp`, **npm** `registry-mcp` and
  `@foretak/brreg-mcp` — all four at 0.3.0, descriptions name all three
  countries. The unscoped npm `brreg-mcp` is still `hellosverre`'s unrelated
  0.1.1 package, unchanged, as documented in Prerequisites below.
- **punkpeye/awesome-mcp-servers** — merged entry is live and accurate for the
  two countries it names; the Sweden follow-up PR is open, correct, and
  already excluded from duplication per instructions.
- **appcypher/awesome-mcp-servers** — still archived; skip stands.
- **GitHub repo topics** — still 20/20 and correct.

**Fixed tonight (two mechanisms only, per instructions):**
- **Smithery** — PATCHed via `api.smithery.ai` with the stored key
  (`~/secrets/registry-mcp/smithery-api-key.txt`): description now names all
  three countries and drops the stale "Denmark next" promise; `iconUrl` now
  set. Full before/after in [§2](#2-smithery).
- **GitHub repo description** (`gh repo edit --description`, on our own repo —
  not a third-party submission, so outside the "two mechanisms" question
  entirely): was the literal Norway-only sentence this file itself suggested;
  now names all three countries. See
  [GitHub repo topics](#github-repo-topics).

**Confirmed stale, cannot fix without a human (no login/API path open to an
agent):**
- **Glama** — still 0.2.0 / two countries. No documented API; needs the admin
  UI. [§3](#3-glama).
- **mcpservers.org (wong2)** — Cloudflare blocks automated re-verification;
  status unknown either way. [§9](#9-mcpserversorg--wong2s-awesome-mcp-servers).
- **Cline Marketplace** — icon blocker cleared, but the "tested in Cline"
  attestation needs an actual human or a Cline-equipped agent, not a login.
  [§10](#10-cline-mcp-marketplace-bonus).

**Unchanged, re-confirmed:**
- **PulseMCP** — still closed, identical wording.
- **MCP Market** — still 429 on every attempt; already-confirmed live per the
  2026-09-05 record, so left alone.
- **mcp.so** — issue #3927 still open, unanswered, and stale (Norway-only
  text, filed before the UK or Sweden existed). **Judgement call, not
  guessed:** the task's authorization names exactly two mechanisms for direct
  action — PRs to list repos, and documented HTTP APIs with a stored
  credential. A GitHub *issue comment* on our own already-open, non-duplicate
  submission is arguably harmless and arguably in-bounds (mcp.so's own
  documented mechanism *is* a GitHub issue), but it isn't literally either of
  the two named mechanisms, so this agent left it alone rather than stretch
  the authorization on its own judgement. If you want it corrected, the exact
  command is in [§5](#5-mcpso) — it's one line, no browser needed. Separately:
  the backing repo (`chatmcp/mcpso`) has 3,170 open issues and hasn't had a
  code push since 2025-03-26, so a maintainer reply of any kind may simply
  never come regardless.

---

## Prerequisites (do these once, before anything below)

> **Resolved 2026-09-07.** All four package targets are live at **0.3.0**:
> PyPI `registry-mcp` and `brreg-mcp`, npm `registry-mcp` and
> `@foretak/brreg-mcp` (option 1 below is the one that shipped). Verified live
> tonight against `pypi.org` and `registry.npmjs.org` directly — all four
> summaries name Norway, the United Kingdom and Sweden. The section below is
> kept as the record of *why* — the naming collision, the decision, and the
> clean-machine verification commands are still correct if a fifth package
> (a future country alias) ever needs the same treatment.

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

> **Re-verified live 2026-09-07 19:15Z.** `GET
> https://registry.modelcontextprotocol.io/v0/servers?search=foretak` returns
> all three published versions (0.1.0, 0.2.0, 0.3.0) with only the last
> carrying `isLatest: true`; that 0.3.0 entry has `countries: [GB, NO, SE]`,
> the full 24-keyword list, the icon, and both packages at 0.3.0. This
> directory is correct today — no action taken. One gotcha for next time:
> `search=registry-mcp` alone does **not** reliably surface us (the endpoint's
> relevance ranking buries us behind unrelated servers that also contain the
> substring "registry-mcp" in their name); `search=foretak`, or `search=
> registry-mcp&limit=100`, does. Use the org name to check, not the package
> name.

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

**2026-09-07 19:35Z — description had gone stale again (Sweden shipped, listing didn't know).** `GET
https://registry.smithery.ai/servers/fargerod%2Fregistry-mcp` (no auth needed to read) still described only
Norway + UK and ended "Denmark (CVR) next" — inaccurate now (new countries are on hold per Kim's 2026-09-06
call, and Sweden, not Denmark, actually shipped third). Fetched the docs page fresh
(`smithery.ai/docs/api-reference/servers/update-a-server.md`) to confirm the field names before writing
anything — `displayName`, `description`, `repositoryUrl`, `iconUrl`, `homepage`, `backlinkUrl`, `license`,
`unlisted`, all optional, same `PATCH /servers/{qualifiedName}` endpoint, same bearer token. Sent:

```bash
# payload built with python (avoids shell-quoting the accented text and the
# apostrophe in "Sweden's"), body written to a temp JSON file, then:
curl -X PATCH "https://api.smithery.ai/servers/fargerod%2Fregistry-mcp" \
  -H "Authorization: Bearer $(cat ~/secrets/registry-mcp/smithery-api-key.txt)" \
  -H "Content-Type: application/json" \
  --data @payload.json
# payload.json: {"displayName": "registry-mcp — the company registry MCP",
# "description": "<all three countries, Sweden's no-name-search caveat,
# updated tool/key list>", "repositoryUrl": "https://github.com/foretak/registry-mcp",
# "homepage": "https://api.foretak.dev", "iconUrl": "https://api.foretak.dev/icon.png",
# "license": "MIT"}
```

`{"success":true,...}`. Verified on **`api.smithery.ai`** (the write host, same call with `GET`) immediately
after: `description` and `iconUrl` both landed correctly (Sweden now named, icon no longer `null`). `homepage`,
`repositoryUrl` and `license` do **not** come back in that response at all — not `null`, just absent — which is
the same silent-drop behaviour the 2026-09-05 note above already found for `repositoryUrl` alone. This looks
like a real gap between what the docs page says is writable and what the read schema surfaces, not a mistake
in the request (field names match the docs exactly). Not worth fighting further tonight — `description` and
`iconUrl`, the two that matter for discovery, both confirmed live.

**`registry.smithery.ai`** (the public search host, read seconds later) still served the **old** text — same
propagation lag the 2026-09-05 fix saw before it became searchable. **Re-check
`registry.smithery.ai/servers/fargerod%2Fregistry-mcp` in a day**; if it's still the old description by then,
re-run the PATCH above (unchanged) rather than treating it as a new problem.

---

## 3. Glama

**Status (2026-09-05, evening): live, claimed, checks passed.** Approved 13:45Z; Kim claimed the listing and saved the build spec via the admin form; first build failed on Glama's side (Docker Hub metadata timeout, their build 01a071f7…), the retry succeeded at 14:36Z in 15.7 s and Glama created a release. The listing at <https://glama.ai/mcp/servers/foretak/registry-mcp> no longer says "cannot be installed" and the score badge renders. Earlier notes below kept for the record. The approval mail says: claim the server under the admin settings on the server page, then "provide a Dockerfile via your server's admin page on Glama: https://glama.ai/mcp/servers/foretak/registry-mcp/admin/dockerfile … it does not need to be added to your repository. Only servers that pass these checks are listed in search results." Until then the page reads "This server cannot be installed" and the score badge is 404. Paste the root `Dockerfile` (dual-mode, stdio when `PORT` is unset). Awesome-mcp-servers PR #13631 already carries the badge line (§7).

**Correction 2, same day — it is a form, not a file.** The admin page generates the Dockerfile from
fields. Verified values (local build of the generated equivalent → Python 3.12.14, `initialize` +
`tools/list` = 5 tools through mcp-proxy):

| Field | Value |
|---|---|
| Base image | `debian:trixie-slim` (default) |
| Node.js version | `26` (default) |
| Python version | **`3.12`** (the tested version; the default 3.14 is untested) |
| Build steps | `["uv sync --locked --no-dev", "mkdir -p /app/data"]` |
| CMD arguments | `["/app/.venv/bin/registry-mcp"]` |
| Environment variables JSON schema | the auto-detected one (three optional vars, `required: []`) |

**Earlier note (kept for the record):** Glama's admin page pre-fills *its own* template (debian + node + `mcp-proxy` + uv,
clone of our repo at a pinned commit) ending in `CMD ["mcp-proxy","--"]` with nothing after the `--`. Do not
paste our root Dockerfile over it; complete their template instead. Verified locally 2026-09-05 (build, run
with `MCP_PROXY_DEBUG=true`, `initialize` + `tools/list` over `http://localhost:8080/mcp` → 5 tools):

```dockerfile
FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive \
    GLAMA_VERSION="1.0.0" \
    PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git && curl -fsSL https://deb.nodesource.com/setup_26.x | bash - && apt-get install -y --no-install-recommends nodejs && npm install -g mcp-proxy@6.4.3 pnpm@10.14.0 && node --version && curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR="/usr/local/bin" sh && uv python install 3.14 --default --preview && ln -s $(uv python find) /usr/local/bin/python && python --version && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
WORKDIR /app
RUN git clone https://github.com/foretak/registry-mcp . && git checkout <the commit Glama pre-fills>
RUN uv python install 3.12 && uv sync --locked --no-dev --python 3.12
ENV PATH="/app/.venv/bin:/app/node_modules/.bin:$PATH" \
    REGISTRY_MCP_CACHE_PATH=/app/data/cache.sqlite3
RUN mkdir -p /app/data
CMD ["mcp-proxy","--","registry-mcp"]
```

The three lines that are ours: `uv sync` on Python 3.12 (the tested version; the template defaults to 3.14),
the `PATH`/cache `ENV`, and the completed `CMD`. Glama's environment-variable schema (`COMPANIES_HOUSE_API_KEY`,
`REGISTRY_MCP_CACHE_PATH`, `REGISTRY_MCP_CONTACT_EMAIL`, none required) is correct as auto-detected.

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

**2026-09-07 19:16Z — re-checked, still stale.** `glama.ai/mcp/servers/foretak/registry-mcp` is still live and
installable (no "cannot be installed" text, score badge renders as an A-grade / 4.7-ish TDQS rating), but the
version shown is **0.2.0** and the description still names only Norway and the UK — no Sweden, two releases
behind. The page also shows a "Maintained" / responsiveness pair that reads **"Unresponsive"**; unclear whether
that tracks server uptime or issue-response time on the repo — worth a human glance, not something this agent
could check without calling `api.foretak.dev`, which is off-limits.

Unlike Smithery, **Glama has no documented API and no credential for one is stored in `~/secrets/`** — the only
lever is the claimed owner's admin page, which needs a browser session. Glama's own text says it "crawls
GitHub" for updates, so this *may* clear on its own within some days; if not, this is the fix:

> **HUMAN — ready to execute, ~2 minutes:**
> 1. Open <https://glama.ai/mcp/servers/foretak/registry-mcp/admin> (sign in with GitHub if prompted — the
>    account that claimed it, per §3 above).
> 2. Look for a "re-scan repository" / "rebuild" / "sync" action. If present, click it.
> 3. If the Dockerfile-from-form step re-triggers, the values are unchanged from the table above (`debian:
>    trixie-slim`, Node 26, **Python 3.12**, build steps `["uv sync --locked --no-dev", "mkdir -p /app/data"]`,
>    CMD `["/app/.venv/bin/registry-mcp"]`) — nothing about 0.3.0 changed the build, only the app code.
> 4. Confirm done: the listing shows **0.3.0** and the description mentions Sweden / Bolagsverket.
> 5. If there is no manual re-scan control at all, no action is needed — just re-check in 48h; Glama's crawler
>    likely runs on its own schedule.

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

**Re-checked 2026-09-07:** identical wording, page still says "last updated September 3, 2026" — no change in
three days. Since #1 (the official registry) is confirmed correct and current tonight, nothing more to do here
either way. Next re-check: early October.

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

**2026-09-07 19:18Z — re-checked. Issue #3927 is still open, no reply, and now stale.** Three days with no
maintainer response. Two new things found tonight:

1. `https://mcp.so` (bare domain) now returns **200** to a plain `curl`, not 403 — the block on 2026-09-04 may
   have been transient or IP-based. `https://mcp.so/search?q=...` also returns 200 with a browser User-Agent,
   but it's a client-rendered shell (19 lines of HTML, no results in the static markup), so this agent could
   not confirm whether we're actually listed anywhere on the site itself — only the GitHub-issue submission
   status is checkable.
2. `chatmcp/mcpso` (the backing repo) has **3,170 open issues** (up from 3,101 on 2026-09-04) and **no code
   push since 2025-03-26** — the issue tracker gets some traffic (a handful close each day, several marked
   "Withdrawn" by their own submitters) but the project itself looks dormant. A maintainer reply here may
   simply never come, independent of anything about our listing.

Issue #3927's body is also now factually behind: it says "First module: Norway" and lists only Norway's tags,
filed before the UK or Sweden existed. If it is ever processed as-is, the resulting mcp.so listing would
undersell the server by two-thirds.

**Judgement call, recorded rather than acted on.** The task's authorisation for direct, human-free action names
exactly two mechanisms: GitHub PRs to list repositories, and documented HTTP APIs with a stored credential. A
GitHub *issue comment* — correcting our own already-open, non-duplicate submission, not filing a new one — is
neither of those, even though it uses the same authenticated `gh` and mcp.so's own documented mechanism for
this directory *is* a GitHub issue. Rather than stretch a two-item list on its own judgement, this agent left
the issue untouched and is recording the exact fix here instead. If you want it corrected, this is the whole
job, one command, no browser:

```bash
gh issue comment 3927 --repo chatmcp/mcpso --body "Update: registry-mcp is now at 0.3.0 and covers three
countries, not one. Norway (brreg / Enhetsregisteret) is joined by the United Kingdom (Companies House,
company-number lookup) and Sweden (Bolagsverket, organisationsnummer lookup — no name search, the free API has
no name index). Same repo, same install commands, same 5 tools. Official MCP registry: 0.3.0."
```

Given the repo's own activity level, this may not change the outcome — but it costs one command if you decide
it's worth sending.

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

**Re-checked 2026-09-07:** `https://mcpmarket.com/server/registry-10` still returns **429** to both a plain
`curl` and a browser-User-Agent request — same as three days ago, so this isn't a one-off. Not re-tried
repeatedly to avoid making the rate-limit worse. No content could be verified either way; leaving this as
**live-per-2026-09-05-confirmation, freshness unknown**, rather than guessing.

---

## 7. awesome-mcp-servers — punkpeye

- **Repo:** <https://github.com/punkpeye/awesome-mcp-servers> (the big one)
- **Rules:** its `CONTRIBUTING.md`
- **Process:** fork → edit `README.md` → PR
- **Status:** PR opened 2026-09-04 —
  <https://github.com/punkpeye/awesome-mcp-servers/pull/13631> — **MERGED
  2026-09-07T13:14:35Z** (from fork `foretak/awesome-mcp-servers`, branch
  `add-registry-mcp`, inserted between `flox-foundation/flox-mcp` and
  `Fund-z/fundzwatch-mcp`; confirmed live in `punkpeye/awesome-mcp-servers`'s
  `README.md` at the current line for `foretak/registry-mcp`, badge rendering).
  **Follow-up PR #13893** (adds Sweden to that same line) is open — see the
  note after the steps below. **Do not open a third PR here** — that would be
  the duplicate the hard rules warn about.

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

### The Sweden follow-up — PR #13893, already open, do not duplicate

<https://github.com/punkpeye/awesome-mcp-servers/pull/13893>, open (not merged) as of 2026-09-07 19:20Z. #13631
merged a couple of hours before Sweden shipped, so the line it landed named only the UK and Norway; #13893 is a
one-line edit to that same entry, adding a Sweden clause, changing nothing else (same link, same badge, same
emoji, same alphabetical position — confirmed via `gh pr diff 13893`, it is a single-line replacement, not a
new entry).

Two automated bot comments landed on it, both false positives, both already answered before this audit:
1. A Glama-badge request — the entry already carries the badge (`[![foretak/registry-mcp MCP server]...`),
   inherited unchanged from #13631.
2. A "duplicate" flag — mis-fires on any diff that touches an existing `foretak/registry-mcp` line, because the
   checker apparently just greps the diff for a URL that's already in the list, without checking whether the
   line count actually grew.

A reply from this account already walks through both points on the PR itself. **Nothing further to do** —
per instructions, this was confirmed as the already-open PR and was not duplicated. It just needs a maintainer
to look at it, same as #13631 eventually got.

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

**2026-09-07 19:2xZ — could not re-verify; Cloudflare, not the app, is in the way.** Both a plain `curl` and
WebFetch against `https://mcpservers.org/servers/foretak/registry-mcp` came back **403** — but the body is a
Cloudflare "Just a moment…" bot-challenge page (confirmed by inspecting it directly), not a real 403 from
mcpservers.org itself. So: unknown whether the live listing still reads "Norway and United Kingdom" (the Short
Description above, submitted 2026-09-05, predates Sweden by two days) or whether it's been refreshed.

No fix path exists for an agent either way — this list explicitly refuses PRs, and nothing in its docs
describes an update API, only the one-time submission form. Re-submitting risks creating a second, duplicate
listing rather than editing the first, which the hard rules treat as worse than doing nothing.

> **HUMAN — read-only check, ~1 minute:** open
> <https://mcpservers.org/servers/foretak/registry-mcp> in an actual browser (Cloudflare should pass a real
> one). If it still says only Norway and the UK: there's no documented safe way to edit it short of asking
> wong2 directly, which is outside what an agent may do here (no e-mail/forum contact) — this becomes a
> judgement call for a person, not something to guess at from here.

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

**2026-09-07: the icon blocker is cleared.** `static/icon.png` exists (shipped 2026-09-05, T20) and is confirmed
400×400 PNG (`file` reports `PNG image data, 400 x 400, 8-bit/color RGB`). Checked tonight for an existing
submission first (`gh issue list --repo cline/mcp-marketplace --search "registry-mcp"` and broader searches for
"foretak", "brreg", "bolagsverket", "companies house") — **nothing found**, so filing would not duplicate.

**Still blocked, but on requirement 4, not the icon.** Cline's own template requires the submitter to *confirm
having tested* giving Cline just the README (or `llms-install.md`) and having it work. This agent has no Cline
runtime to actually run that test in, and claiming the test happened when it didn't would break the "keep the
tone factual" rule as directly as an adoption-number claim would — so this stays a human (or Cline-equipped
agent) task, not a login-only one.

> **HUMAN (or an agent with Cline installed) — ready to execute once tested:**
> 1. In Cline, install using **only** `README.md` (do not hand it `llms-install.md` or any other file) — either
>    the `claude mcp add` line won't apply, but the stdio line will: `uvx registry-mcp` (or point Cline at the
>    repo and let it read the README).
> 2. Confirm it works: at minimum, `list_countries` should return `GB`, `NO`, `SE`.
> 3. File the issue at <https://github.com/cline/mcp-marketplace/issues/new/choose> (pick the server-submission
>    template) with:
>    - **GitHub repo link:** `https://github.com/foretak/registry-mcp`
>    - **Logo:** `https://api.foretak.dev/icon.png` (400×400 PNG, already hosted) or attach `static/icon.png`
>      directly if the template wants a file upload.
>    - **Justification (factual, no superlatives):** "Company data from three national business registries —
>      Norway (Brønnøysundregistrene / Enhetsregisteret), the United Kingdom (Companies House) and Sweden
>      (Bolagsverket) — behind one JSON shape and five read-only tools: lookup by national identifier, name
>      search (not available for Sweden — the register has no name index), computed statutory filing
>      deadlines with the rule cited, and identifier validation. No API key needed for Norway; free keys for
>      the UK and Sweden. MIT-licensed, open source, `uvx registry-mcp` with no install step."
>    - **Testing confirmation:** state plainly that the README-only install was tested in Cline just now, and
>      what `list_countries` returned — do not check this box without having actually done step 1–2.

---

## GitHub repo topics

> **Status 2026-09-07: topics done, 20/20 slots filled** (re-verified live tonight — includes `bolagsverket`,
> `sweden`, `united-kingdom` alongside the original twelve, added when the UK and Sweden modules shipped). The
> **repo description**, set in the same original pass, had not been touched since and was still the exact
> Norway-only sentence this file suggests below — **fixed 2026-09-07** via `gh repo edit --description`; the
> command block further down now shows the corrected text that's actually live, so copy-pasting it again is
> safe and idempotent rather than a regression.

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

> **What's actually live (checked 2026-09-07), for the record:** the cap is full at 20 —
> `ai-agents bolagsverket bronnoysund brreg business-registry companies-house company-data company-lookup
> company-number company-registry enhetsregisteret mcp mcp-server model-context-protocol norway
> organisasjonsnummer organisationsnummer orgnr sweden united-kingdom`. That's the original twelve, unchanged,
> plus eight added as the UK and Sweden modules shipped: `bolagsverket`, `companies-house`, `company-lookup`,
> `company-number`, `company-registry`, `organisationsnummer`, `sweden`, `united-kingdom`. Only one of those
> (`company-registry`) was on the "optional extras" list above — the rest are UK/Sweden-specific names the list
> couldn't have anticipated, since neither country existed yet when it was written. If a 21st ever becomes
> worth having, something has to come out first; nothing here is redundant enough to be the obvious cut.

Also worth setting in the same pass — **this was still the original Norway-only sentence, live as of
2026-09-07 19:15Z; fixed the same night** (`gh repo edit`, confirmed via `gh api repos/foretak/registry-mcp`).
The command below is the corrected version, safe to re-run:

```bash
gh repo edit foretak/registry-mcp \
  --description "Company data for AI agents, any country. MCP server and REST API over national business registries: Norway (brreg / Enhetsregisteret), the United Kingdom (Companies House) and Sweden (Bolagsverket) — orgnr, company number or organisationsnummer lookup, VAT/deadline checks." \
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

## 11. Anthropic Connectors Directory

**Status 2026-09-09: PENDING — the package is written, Kim submits.** Prepared by T50 on the
2026-09-08 dispatch. Everything below is a summary; the submission itself is
[`content/anthropic-connectors-submission.md`](content/anthropic-connectors-submission.md), which
holds every portal field in the order the portal asks for it, the review-criteria checklist item by
item, and the data-handling answer with all four licences.

| | |
|---|---|
| Portal | <https://claude.ai/admin-settings/directory/submissions/new> (403 unauthenticated — it is behind the org login, as expected) |
| Docs | <https://claude.com/docs/connectors/building/submission> · <https://claude.com/docs/connectors/building/review-criteria> · <https://claude.com/docs/connectors/directory> |
| Needs a login? | **Yes, and a plan.** Team or Enterprise organisation, Owner role. Individual plans have no organisation settings at all. |
| Cost | Claude Team, two-seat minimum, **$25/seat/month billed monthly** ($20 annually), *"for teams of 2 to 150"*, cancel anytime — <https://www.claude.com/pricing>, checked 2026-09-08. **≈$50/month, cancellable.** |
| Listing name | **Company Check — UK, Sweden & Norway business registers** (54/100 chars) — the job, not the architecture, and the same name as the Smithery listing since 2026-09-08. **Never `registry-mcp`.** |
| Categories | `Data` + `Financial services` (of 11 offered at <https://claude.com/connectors>) |
| Server | `https://api.foretak.dev/mcp`, Streamable HTTP, **no authentication** |

**Why it is worth the money, and the caveat in the same breath.** First-party:
*"Directory connectors are eligible for Suggested Connectors — in-chat recommendations when relevant
to the user's task. Every directory entry is included automatically. Ranking is usage-based, similar
to other app stores."* The first two sentences are the reason to do it — it is the only push
mechanism in the ecosystem, across Claude.ai, Cowork, Desktop, mobile and Claude Code. The third is
why not to expect much: a listing with zero usage ranks last, and there is no public data on what a
fresh entry receives (`~/mcp-growth/ADOPTION.md` Finding 3 — high confidence this is the best
available surface, low confidence it produces usage inside 30 days).

**What already passes, and it is the part that fails most submissions.** Every one of the seven
tools carries a `title` and `readOnlyHint: true` — verified on the wire in the served card, not just
in source. HTTPS Streamable HTTP. Icon 400×400. Privacy policy served (it 404'd until commit
`0d20df9`; that alone was an automatic rejection from this channel). Tool names ≤19 characters
against a 64 limit. No write tool exists in the software at all.

**What is open.** Three things, in order of risk:

1. **The served privacy policy is stale**, and *"missing or incomplete privacy policies result in
   immediate rejection"*. It says the service covers Norway and the United Kingdom; Sweden has been
   live since 2026-09-07 and is named elsewhere on the same page. It also still opens "Draft …
   effective once published at a public URL" on a published page. Four edits, listed in the
   package's §12 OPEN-1. **Fix and deploy before submitting.** (`legal/terms.md` has the same
   three-country gap — not a portal field, so not blocking; it rides with T47.)
2. **The Team plan.** Kim's purchase.
3. **The "I ran every tool myself" confirmation.** Kim's five minutes — agents on this project are
   barred from lookup calls against production.

**The risk that has to be argued rather than satisfied** is the API-ownership criterion (*"Your
server must call your own first-party APIs, or APIs you legitimately proxy"*). We proxy four public
sources: NLOD 2.0 (Brønnøysundregistrene), Crown copyright / Companies House, Bolagsverket's
värdefulla-datamängder regime, GLEIF CC0. The portal has an explicit "Data handling" step for
exactly this, and Pappers, Firmenbuch and D&B are listed precedents. The full answer, quoted and
sourced, is the package's §8.

---

## 12. Claude plugin directory

**Status 2026-09-09: PENDING — the plugin is rebuilt and validated, Kim submits.**

| | |
|---|---|
| Form | <https://platform.claude.com/plugins/submit> (Console) — or <https://claude.ai/admin-settings/directory/submissions/plugins/new> if the Team org exists |
| Docs | <https://claude.com/docs/plugins/submit> · <https://code.claude.com/docs/en/discover-plugins> |
| Needs a login? | **Yes — Console (Developer/Admin/Owner).** *"Individual authors who aren't part of a claude.ai Team or Enterprise organization can sign up for Console at platform.claude.com and submit there."* **No Team plan needed**, so this does not wait on §11. |
| Cost | **Free.** |
| What it takes | A **public** GitHub link: `https://github.com/foretak/registry-mcp`. Closed-source is not accepted. Run `claude plugin validate` first — done, passes `--strict` on the plugin manifest, the marketplace manifest, the commands and the skills. |
| Updates | Automatic. *"Updates pushed to your GitHub repo are picked up automatically… You do not need to re-submit the form for updates."* |

**What changed in the repo (T50).** `plugins/registry-mcp/` was a bare `.mcp.json` pointing at the
hosted URL — which is a tool, not a job, and Anthropic's guidance is explicit that *"the best plugins
bundle related capabilities together into a coherent package that solves a specific job function or
workflow end-to-end"*. It now carries `skills/company-check/SKILL.md` (the counterparty,
filing-deadline and register-coverage workflows, mirroring the three MCP prompts' logic, including
the payment-fraud caveat verbatim) and three commands — `/check-supplier`, `/filing-deadlines`,
`/enrich-company-list` — plus a plugin README. `.claude-plugin/marketplace.json` and
`plugin.json` were renamed to the job as well.

**Official or community? Community — and the docs genuinely disagree, so here is the reasoning.**
<https://claude.com/docs/plugins/submit> says the directory *"is surfaced as the official
`claude-plugins-official` marketplace and is automatically available to all users"*, while
<https://code.claude.com/docs/en/discover-plugins> says *"the official marketplace is curated by
Anthropic, and inclusion is at Anthropic's discretion. The in-app submission forms add plugins to the
community marketplace, not the official one."* Both fetched 2026-09-08. **Believe the Claude Code
page:** it is the more specific claim, it describes a mechanism the other page does not (the
community marketplace gates on automated validation and safety screening and pins each plugin to a
commit SHA), and the submit page's own vocabulary concedes it — it calls what you submit a *community
plugin* and warns that *"there are no guarantees that any community plugin will become Anthropic
Verified."*

So expect: **`/plugin marketplace add anthropics/claude-plugins-community`**, then
`/plugin install registry-mcp@claude-community` — a marketplace the user adds by hand. A catalog, not
a channel. ADOPTION measured 2,282 plugins in it, of which exactly one is categorised finance. Free
and likely accepted, so do it; do not book it as distribution.

---

## 13. awesome-remote-mcp-servers — punkpeye

- **Repo:** <https://github.com/punkpeye/awesome-remote-mcp-servers> — punkpeye's sister list to §7,
  **hosted/remote servers only** (§7's `awesome-mcp-servers` is local/stdio; its own README says so:
  *"Looking for servers you run yourself? See awesome-mcp-servers."*).
- **Rules:** its own `CONTRIBUTING.md`, a different format from §7 — one entry is three lines (name
  linked to the **homepage**, not the repo, plus the endpoint in backticks; a required Glama
  *connector* badge on line two; an auth marker + one-sentence description on line three); starring
  the repo is a stated precondition for merge; CI (`.github/workflows/check-submission.yml`) probes
  the endpoint with a real MCP `initialize` request and checks the badge slug resolves on Glama.
- **Process:** star → fork → branch → edit `README.md` → PR.
- **Status:** PR opened 2026-09-09 — <https://github.com/punkpeye/awesome-remote-mcp-servers/pull/146>
  — **open, blocked on the Glama connector badge (Kim).** CI ran automatically and labelled it
  `endpoint-ok` (the live handshake against `https://api.foretak.dev/mcp` passed) and
  **`missing-connector`**, with an automated comment quoting the rule verbatim: *"PRs without a badge
  are not merged... List your server at glama.ai/mcp/connectors."* Starred
  `punkpeye/awesome-remote-mcp-servers` from `fargerod-dotcom` first, as required. Fork:
  `foretak/awesome-remote-mcp-servers`, branch `add-company-check` — the exact steps Kim needs are in
  `HUMAN_TODO.md` §7.11(c); once the connector exists, tell the orchestrator so the badge line can be
  pushed to that branch.

### Why this PR exists

`awesome-mcp-servers` PR #13893 — the Sweden edit to §7's merged entry — was **closed by the
maintainer 2026-09-08**: remote/hosted servers now belong on this sister list instead, per that
list's own scope. §7's original entry (#13631, merged, UK+Norway, since generalised in prose) is
unaffected and correctly stands — it lists the **local/stdio** install (`uvx registry-mcp`), still in
scope there. This PR is the hosted equivalent: `https://api.foretak.dev/mcp`, Streamable HTTP, no
auth — a different capability, not a duplicate.

### Category and entry

**Finance** — no existing company-registry entry in the list (checked the full README). Alphabetical
position: between `AlphaPipeline` and `Fruit Stand`.

```markdown
- [Company Check](https://api.foretak.dev) `https://api.foretak.dev/mcp`
  🔓 - Look up a company at the UK's Companies House, Norway's Brønnøysundregistrene or Sweden's Bolagsverket, with what it has filed, plus UK charges and insolvency records.
```

Names only what is **live on production today** (`PROGRESS.md`'s Deploy row, checked 2026-09-09):
`filings` for all three countries, `charges` and `insolvency` for the UK only. `financials`, `lei`
and the rest are merged on `main` but not deployed — not mentioned, per the hard rule against listing
undeployed capability.

**Name field kept short** (`Company Check`, not T50's full cross-surface name from §4/§11) — every
other multi-word entry in this list does the same and carries the fuller description in the sentence
below, not the name. Checked against `Evlek` (PR #111): the PR *title* used the long descriptive
form, but the merged README entry's Name field is just `Evlek`. The list's `CONTRIBUTING.md` states
no character cap on the name either way; this follows actual practice over the letter of a silent
rule, and keeps the door open to using the full cross-surface name later if that reading turns out
wrong — it is a one-word diff.

### The Glama-connector-badge blocker

This list's `CONTRIBUTING.md` is explicit, and its CI enforces it, not just documents it: *"The badge
is required. PRs that add an entry without one are not merged."* `glama.ai/mcp/connectors` is a
**different Glama product** from §3's `glama.ai/mcp/servers` (where `foretak/registry-mcp` already
carries a score badge) — checked live 2026-09-09 by fetching `glama.ai/mcp/connectors`, no
`foretak`/`registry-mcp`/`Company Check` entry exists there. Getting listed needs a human on Glama's
own claim flow — [§14](#14-glama-connectors). Once it exists, the follow-up here is one commit: add

```markdown
[![Company Check MCP connector](https://glama.ai/mcp/connectors/NAMESPACE/NAME/badges/score.svg)](https://glama.ai/mcp/connectors/NAMESPACE/NAME)
```

as the entry's second line, on `add-company-check` (branch already pushed to the `foretak` fork) or
against PR #146 directly.

**Needs a human login: yes** — GitHub (star + fork + PR, done, `fargerod-dotcom`); a maintainer still
merges once the badge lands, same as §7.

---

## 14. Glama connectors

**Status 2026-09-09: PENDING — not yet listed, not yet attempted.** Surfaced by
[§13](#13-awesome-remote-mcp-servers--punkpeye)'s bot comment, not chased before that; not part of
T56's brief beyond recording it here and in `HUMAN_TODO.md` as a pending row, per instructions.

`https://glama.ai/mcp/connectors` is a distinct Glama product from the server directory in §3
(`https://glama.ai/mcp/servers`, where `foretak/registry-mcp` is live and claimed but **still shows
0.2.0** as of the last check — its own refresh is a separate open item, unrelated to this one, see
§3). Connectors carry their own score badge
(`glama.ai/mcp/connectors/NAMESPACE/NAME/badges/score.svg`) under a reverse-DNS `NAMESPACE/NAME`
slug, and at least one directory found so far (`awesome-remote-mcp-servers`, §13) treats that badge
as a hard, CI-enforced requirement — worth assuming other hosted-server directories do too, and
checking each one's rules before relying on this being optional.

No documented API was found for this product (same gap §3 already recorded for the servers
directory, and did not re-check here). Listing it is very likely the same admin-page, GitHub-OAuth
claim flow as §3, on the connectors side of the site rather than the servers side — **unconfirmed**,
needs a human browser session to actually open the page and do it.

**Needs a human login: yes** — GitHub OAuth, Glama's claim flow (a browser session, not something a
fetch tool can complete). `HUMAN_TODO.md` §7.11(c).

---

## Press pitch — kode24 (outbound record, not a directory)

Not a listing target — everything else in this file is. Kept here anyway because T56 was asked to
record it alongside §13/§14, and because `SUBMISSIONS.md` is where every outbound submission's
*outcome* lands regardless of channel. The pitch itself and the rest of the outbound trail are
`FEEDBACK.md`'s log and `HUMAN_TODO.md` §6.

**Status 2026-09-08: declined.** Pitch sent 2026-09-05 (Kim, from `fargerod@gmail.com`, to
`ole@kode24.no` cc `hei@kode24.no`, the VAT article inline, 677 words). The editor's reply,
2026-09-08: the piece read **"more like documentation for a tool than a reader's post."** No
counter-offer attached. A rewrite in an opinion-piece voice — the reader's problem stated first, the
tool second, not the reverse — is a real option, but it is an editorial call only Kim can make; an
agent should not draft a second pitch on spec. `HUMAN_TODO.md` §7.11(b).

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
| **PyPI** (+ API token) | Prerequisite: publish `registry-mcp` and `brreg-mcp` — **done, 0.3.0, all four package targets live** (2026-09-07) |
| **npm** (`npm login`) | Prerequisite: publish `registry-mcp` and `brreg-mcp` — **done**, same release |
| **GitHub**, member of the `foretak` org | #1 (`mcp-publisher login github`, **done, 0.3.0 live**), #3 (claim, **done**; a re-scan to pick up 0.3.0 is what's still open — see §3's ready block), #5 (issue filed and open; the *update* comment in §5 is a judgement call recorded there, not executed), #7 (**#13631 merged**; #13893 closed by the maintainer 2026-09-08, see §13), #8 (skip, archived), #10 (issue **not yet filed** — needs the Cline install test first, see §10's ready block), #13 (star + fork done, **PR #146 open**, blocked on §14), topics (**done, 20/20**), labels, seeded issues |
| **Smithery** (GitHub sign-in) | #2 — published and **kept current tonight** without a fresh login, via the stored API key (see below) |
| **MCPmarket** | #6 — account already used per the 2026-09-05 record; nothing new needed, just unverifiable right now (429) |
| A **real inbox** at `hello@<domain>` | #9's confirmation, the JSON-LD, and the upstream `User-Agent` — inbox exists, listing approved 2026-09-05 |
| **A browser that passes Cloudflare** | #9 — re-verifying or fixing the live listing text needs a real browser session, not a login exactly; curl/WebFetch both get the bot-challenge page instead of the site |
| **Cline, actually installed** | #10's testing-confirmation step — this is a capability gap, not a login: no amount of GitHub access substitutes for having run the install |
| **Claude.ai Team or Enterprise org** (Owner) | #11 — the Connectors Directory portal is inside organisation settings and does not exist on an individual plan. ≈$50/month, two seats, cancellable. **Not bought yet.** This is a purchase, not a login, and agents on this project buy nothing. |
| **Anthropic Console** (Developer/Admin/Owner) | #12 — the plugin submission form. Free, individual sign-up at platform.claude.com, and independent of the Team plan. |

**The line that used to close this file — "nothing on this page can be completed by an agent alone" — is no
longer true, and is worth flagging as the one thing in here that turned out to be wrong.** It was accurate when
written (every open item was genuinely login-gated). Two things changed it: Smithery documented a real HTTP API
and a key for it now lives in `~/secrets/registry-mcp/`, and this repo's own GitHub metadata (topics, and now
the description) is something an authenticated `gh` can just fix directly — it was never actually a
third-party submission requiring anyone's *login* in the sense the rest of this table means, just an edit
nobody had gotten back around to. Both were done tonight without a browser. What's left after tonight genuinely
does need a human or a capability an agent doesn't have here: a GitHub OAuth session on Glama's admin page, a
browser that clears Cloudflare on mcpservers.org, and an actual Cline install to test before Cline's own
submission template can be honestly filled in.
