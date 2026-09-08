# Anthropic Connectors Directory — submission package

**What this is.** Every field the Connectors Directory submission portal asks for, pre-filled, in the
order the portal asks it. Kim opens the portal, works down this file, pastes. Nothing here is a
draft to be re-worded at submission time; where a decision is still open it says so in bold and says
what the decision is.

**Who submits.** Kim. An agent cannot: the portal lives inside a Claude.ai **Team or Enterprise**
organisation's settings, and the account this project has is an individual plan. See
`HUMAN_TODO.md` §7.9 for the purchase and the click path.

**Written** 2026-09-08/09 (the working session straddled midnight CEST) against `main` at commit **`c854e9e7b49d8411db83077f649e594eab4a3645`**
(`c854e9e`), and against the **running production service**, which is a different thing and the
difference matters — see §3.2. Every requirement below is quoted from the page that states it, with
the URL; every URL is listed with its HTTP status in §13.

**Sources for the requirements** (fetched 2026-09-08):

- Pre-submission checklist — <https://claude.com/docs/connectors/building/review-criteria>
- Submitting to the Connectors Directory — <https://claude.com/docs/connectors/building/submission>
- Connectors directory — <https://claude.com/docs/connectors/directory>
- Connector verification — <https://claude.com/docs/connectors/verification>
- Software Directory Policy — <https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy>
- Software Directory Terms — <https://support.claude.com/en/articles/13145338-anthropic-software-directory-terms>

---

## 0. Before you start

> "Remote MCP server submissions happen inside Claude.ai, in the submission portal. The portal is
> part of your organization's settings, so you need: **A Team or Enterprise organization.**
> Organization settings aren't available on individual plans. **Directory management access.** By
> default, only organization Owners and Primary owners can submit and manage directory listings."
> — [submission docs, "Before you start"](https://claude.com/docs/connectors/building/submission)

| | |
|---|---|
| Portal | <https://claude.ai/admin-settings/directory/submissions/new> |
| Status dashboard afterwards | <https://claude.ai/admin-settings/directory/submissions> |
| Escalations | `mcp-review@anthropic.com` |
| Blocker | **Team plan not yet bought.** $25/seat/month billed monthly, $20 annually, "for teams of 2 to 150", cancel anytime — <https://www.claude.com/pricing>, checked 2026-09-08. Two-seat minimum ≈ **$50/month**. |

Have ready before opening the portal: this file, the icon URL (§4), the privacy policy URL (§4) and
the reviewer instructions (§9). No test credentials are needed — see §9.1.

> "Your progress saves automatically in your browser as you move between steps, so within a browser
> session you can jump back to earlier steps without losing work." — submission docs

---

## 1. Step "Introduction"

Nothing to enter. It confirms the portal accepts **remote MCP servers only**, which this is. (A
local/stdio copy of the same software ships as a PyPI and npm package and an MCPB bundle; those are
not this submission and must not be mentioned as if they were.)

---

## 2. Step "Connection"

| Field | Value |
|---|---|
| Server URL | `https://api.foretak.dev/mcp` |
| Transport | **Streamable HTTP** |
| Does every user connect to the same URL? | **Yes — one URL for all users.** |

Notes for the person pasting:

- The URL must be `https://`. It is.
- `https://api.foretak.dev/mcp` and `https://api.foretak.dev/mcp/` both answer, with **no redirect**
  between them (a deliberate property; some clients follow redirects badly). Paste the form without
  the trailing slash.
- There is no SSE endpoint. Choose Streamable HTTP.

---

## 3. Step "Tools"

> "Your server's tools, prompts, and resources sync automatically from the connected server, grouped
> by whether their annotations declare them read-only or write (tools without annotations are grouped
> separately). If any tools are flagged for missing titles or annotations, fix them on your server
> before submitting." — submission docs

Nothing to type. What will sync, read from the **served** server card at
`https://api.foretak.dev/.well-known/mcp/server-card.json` on 2026-09-08 — production's own answer,
not the repo's. The portal syncs by connecting to `/mcp` and listing tools rather than by reading
that card, but the card is generated from the same tool definitions the MCP surface advertises and a
drift test fails the build if the two diverge, so it is a faithful preview. Confirm on screen anyway;
it costs one glance.

### 3.1 Seven tools, every one read-only, every one titled

| Tool | `title` | `readOnlyHint` | `destructiveHint` | name length |
|---|---|---|---|---|
| `lookup_company` | Look up a company in a national business register | `true` | `false` | 14 |
| `search_company` | Search a national company register by name | `true` | `false` | 14 |
| `company_deadlines` | Statutory filing deadlines for a company | `true` | `false` | 17 |
| `validate_company_id` | Validate a company identifier (no network call) | `true` | `false` | 19 |
| `list_countries` | List supported national company registries | `true` | `false` | 14 |
| `search` | Find a company (ChatGPT connector alias for `search_company`) | `true` | `false` | 6 |
| `fetch` | Fetch one company record (ChatGPT connector alias for `lookup_company`) | `true` | `false` | 5 |

Also synced: three prompts — `explain_company`, `counterparty_check`, `register_coverage`. No
resource templates are advertised on the card (`resources: []`); the `registry://rules/{country}`
resources are registered on the live server and are not part of what the directory lists.

**Every tool will land in the read-only group. None will be flagged.** All seven names are far under
the 64-character limit. There is no write tool, no delete tool, and no tool that takes an HTTP method.

### 3.2 The one thing to check before you press Submit

Production today serves **0.3.0** (`GET /health` → `{"status":"ok","version":"0.3.0","countries":["GB","NO","SE"]}`)
and advertises exactly **three** attachments on `include`: `filings`, `charges`, `insolvency`. Two
more — `financials` and `lei` — are **merged on `main` at `c854e9e` but not deployed**; the deploy is
held behind T46 and lands with the 0.4.0 release.

That gives two versions of the listing copy in §4, and one instruction:

- **Submitting before the 0.4.0 deploy** → use **Description A**. Three attachments. Everything in it
  is callable by a reviewer today.
- **Submitting after the 0.4.0 deploy** → use **Description B**. Five attachments. Check
  `GET https://api.foretak.dev/health` reports `0.4.0` first.

Do not paste B before the deploy. "Every tool must return a successful response when called with
valid parameters" is a review criterion, and a description promising an attachment the server
answers `bad_request` for is the cheapest possible rejection.

Not in either description, because they are not merged: **`peppol`** (Norwegian e-invoicing
registration, D-046 — Norway's 2027 duty), the **Swedish filing-deadline rung** that reads the
financial year end from `filings` instead of assuming 31 December, and the **charge-block reconcile**
(D-045(a)). All three are in flight and land **after 0.4.0**. Say nothing about them in the listing.

---

## 4. Step "Listing"

> "The public-facing listing: server name (100 characters max), tagline (55 characters max),
> description (2,000 characters max), one to five categories, documentation URL, privacy policy URL,
> support contact, icon, and the URL slug for your listing page. **The slug is permanent once
> published.**" — submission docs

### 4.1 Server name — 54 / 100 characters

```
Company Check — UK, Sweden & Norway business registers
```

**Why this name.** It is the job first and the countries second, it is already the live display name
on Smithery (`fargerod/registry-mcp`, renamed 2026-09-08 — one name across every surface is itself a
discovery asset, and `DISCOVERY.md`'s finding was that inconsistent listings cost the clicks they do
get), and it carries the phrases a person actually types — *company check*, *business registers*,
and the three country names — while `registry-mcp` is a package identifier nobody searches for. The only naming rule the directory docs state is the 100-character cap; this is 54.

**Never** submit this as "registry-mcp". That string is the package, the repo and the MCP-registry
name, and it belongs nowhere in the listing except §6's repository link.

### 4.2 Tagline — 48 / 55 characters

```
Is this company real, active and filing on time?
```

That is the user's own question, in their words. Runners-up, if the portal rejects a question mark:
`Official company data from three national registers` (51) or `Company status and filing deadlines,
from the register` (54).

### 4.3 Description A — 1,837 / 2,000 characters — **use this before the 0.4.0 deploy**

```
Look up a company in its own national business register and get back what the register actually says: legal name, legal form, registered status, registered address, industry codes, VAT/MVA registration where the register publishes it, and the statutory filing deadlines that follow — each deadline naming the provision or the register field it comes from, so you can quote the reason, not just the date.

Three countries answer today, in one identical shape:

- United Kingdom — Companies House, by company number (CRN), e.g. 00445790.
- Norway — Enhetsregisteret / Brønnøysundregistrene (brreg), by organisasjonsnummer (orgnr), e.g. 923609016.
- Sweden — Bolagsverket, by organisationsnummer, e.g. 5560160680. Sweden is identifier lookup only: Bolagsverket's free API has no name-search operation, so a name search for Sweden returns an explicit not_implemented error saying so, not an empty result.

A lookup can attach a second register on request: what the entity has actually filed and when (all three countries), its register of charges — mortgages and other security interests (United Kingdom), and any winding-up or administration proceedings (United Kingdom). Each attachment is a separate fetch with its own source and licence, absent unless you ask for it.

A field the register does not publish comes back as null, meaning "the register does not say" — never "no". Every response carries the source, the source URL, the licence and how old the answer is; nothing is more than 24 hours stale.

What this does not do: it is not sanctions, PEP or adverse-media screening; it does not verify bank account or payment details; and it is not a defence against payment fraud — the commonest invoice fraud impersonates a real, active, correctly-registered supplier, not a fake one.

Read-only, and no account or key: connect and call.
```

### 4.4 Description B — 1,969 / 2,000 characters — **use this only after `/health` reports 0.4.0**

Identical to A except the attachment sentence, which becomes:

```
A lookup can attach a second register on request: what the entity has actually filed and when (all three countries), its register of charges — mortgages and other security interests (United Kingdom), any winding-up or administration proceedings (United Kingdom), key figures from the filed annual accounts (Norway), and the Legal Entity Identifier it holds at GLEIF (Norway and the United Kingdom). Each attachment is a separate fetch with its own source and licence, absent unless you ask for it.
```

### 4.5 Categories — pick 2 of the 11 offered

The public directory offers these use-case categories (<https://claude.com/connectors>, 2026-09-08):
Code · Communication · **Data** · Design · Education · **Financial services** · Health and wellness ·
Life sciences and healthcare · Nonprofit · Productivity · Sales and marketing.

**Choose `Data` and `Financial services`.** Two, not five: the peers in this exact category (Pappers,
Firmenbuch, D&B Risk Analytics, D&B Finance Analytics) sit in the finance/data end of the catalog,
and a connector that claims five categories reads as one that does not know what it is. The
capability filter will also place it under **Read** — correct, and worth being visibly correct about.

### 4.6 The remaining Listing fields

| Field | Value | Why |
|---|---|---|
| Documentation URL | `https://github.com/foretak/registry-mcp` | The README is the real documentation — every tool, every field, live example payloads for all three countries. "Public documentation is required by your publish date—a blog post or help-center article is sufficient." |
| Privacy policy URL | `https://api.foretak.dev/legal/privacy` | HTTPS, served, no login. **Read §12 OPEN-1 before pasting this.** |
| Support contact | `hello@foretak.dev` | Same address in the privacy policy, the terms, `SECURITY.md` and every package manifest. |
| Icon | `https://api.foretak.dev/icon.png` — 400×400 PNG, 8,882 bytes, verified on the wire 2026-09-08 | If the portal wants a file upload rather than a URL, the same bytes are `static/icon.png` in the repo. |
| URL slug | **`company-check`** (fallback `company-check-registers`) | **Permanent once published.** Short, matches the name, and readable in a URL. If taken, use the fallback rather than inventing a third word. |

There is **no terms-of-use field** in the Listing step — only a privacy policy URL. `legal/terms.md`
is still served at `https://api.foretak.dev/legal/terms` and is linked from the footer of the privacy
page, so a reviewer will see it: read §12 OPEN-2.

---

## 5. Step "Use cases"

> "Describe the primary use cases, what users need before they can connect (accounts, plans, or other
> setup), and whether the connector reads data, writes data, or both." — submission docs

**Primary use cases** (paste as given):

```
1. Onboarding a supplier, customer or counterparty. Before the first invoice is paid or the contract
   is signed: does this entity exist under this identifier, is that its registered name, is it active
   right now, and is it up to date with the filings its own register demands? One identifier in, a
   finished answer out — the counterparty_check prompt does the whole job from a single company
   number, and states in a closing section what it has NOT established.

2. Filing-deadline tracking. What must this company file next, when, and under which provision?
   Deadlines are answered from the register's own published date where the register publishes one
   (the United Kingdom does), and computed from a cited statute where it does not (Norway and
   Sweden) — with the reason returned alongside the date, so it can be quoted rather than trusted.

3. Enriching a list of company numbers. A spreadsheet or CRM export of UK, Norwegian and Swedish
   identifiers, resolved to registered name, status, address, industry code and VAT registration in
   one identical shape per row, with a source URL per row so any cell can be checked.

4. Understanding what a register does not say. The register_coverage prompt distinguishes a field the
   register never publishes for anyone in that country from a field the register could hold and does
   not hold for this company — two different facts that most tools render identically as a blank.
```

**What users need before they can connect:**

```
Nothing. No account, no plan, no API key, no sign-up. The hosted service holds its own upstream
credentials for Companies House and Bolagsverket; Norway needs none. There is no paid tier, no quota
to buy and nothing to configure. The only limit is 60 requests a minute per client IP, applied to the
whole service, which no interactive use comes near; the static discovery routes are exempt from even
that. The software is also MIT-licensed and can be self-hosted or run locally over stdio, in which
case the operator supplies their own upstream credentials.
```

**Reads, writes, or both:**

```
Reads only. Every tool is read-only and annotated readOnlyHint: true. Nothing in this connector
writes to a national register, to any third-party service, or to the user's own systems. There is no
write path in the software at all.
```

---

## 6. Step "Company"

| Field | Value |
|---|---|
| Company name | **EL ANSARI KONSULT** (organisasjonsnummer 833285602, Oslo, Norway) — the operator named in the privacy policy. Use the registered name; a mismatch between the listing and the privacy policy is a reviewer question you do not want. |
| Company website | `https://api.foretak.dev` |
| Repository (if asked) | `https://github.com/foretak/registry-mcp` |
| Primary contact | Pre-filled from Kim's account. Confirm the e-mail is one Kim reads — reviewer feedback lands there. `hello@foretak.dev` is the published support address. |

---

## 7. Step "Authentication"

> "How users authenticate: OAuth …, a custom connection where users supply their own URL or
> credentials at connection time, or **no authentication**." — submission docs

| Field | Value |
|---|---|
| Authentication mode | **No authentication** |
| Do individual tools prompt for auth on demand? | **No.** |

The served server card states this itself: `"authentication": {"required": false, "schemes": []}`.

The requirement *"Use OAuth 2.0 for authenticated services"* (review criteria) does not bite: there
is no authenticated service here to protect. No caller credential is ever accepted, so none can be
mishandled. The deployment's own upstream keys (`COMPANIES_HOUSE_API_KEY`,
`BOLAGSVERKET_CLIENT_ID`/`_SECRET`) are read from the server environment, never returned, never
logged, and never requested from a user.

---

## 8. Step "Data handling"

> "Whether the underlying API is your own, proxied from a partner with permission, or a third
> party's you don't control, and whether the connector handles personal health data or sponsored
> content." — submission docs
>
> "Your server must call your own first-party APIs, **or APIs you legitimately proxy**. The MCP
> server domain should match your service." — [review criteria, "API ownership"](https://claude.com/docs/connectors/building/review-criteria)

This is the one criterion this connector has to argue rather than simply satisfy. It is a declared
case, not an automatic rejection — the portal has a step for exactly this — and there are precedents
already listed in the directory in this same category: **Pappers** (French company register),
**Firmenbuch** (Austrian company register), **Contract-Factory — Sociétés & SIREN**, **D&B Risk
Analytics** and **D&B Finance Analytics**. All of them relay a register or a data source they do not
own.

**Portal answers:**

| Question | Answer |
|---|---|
| Is the underlying API your own, proxied with permission, or a third party's? | **A third party's, proxied under the publisher's own published open-data terms** — pick the closest option the portal offers to "proxied with permission" and paste the statement below into the free-text box. |
| Personal health data? | **No.** |
| Sponsored content? | **No.** |

**The statement to paste:**

```
This server proxies four public data sources. Each is government or public-interest open data,
published for re-use, and each response we return carries that source's name, URL and licence so the
attribution travels with the data. We add no facts of our own; the only computed value is a filing
deadline, and it returns the statutory provision it was computed from.

1. Norway — Enhetsregisteret, published by Brønnøysundregistrene at data.brreg.no, under the
   Norwegian Licence for Open Government Data (NLOD) 2.0, which permits commercial re-use and
   requires attribution: https://data.norge.no/nlod/en/2.0. We attribute on every response
   ("Enhetsregisteret (Brønnøysundregistrene)", licence "NLOD 2.0") and pass the obligation on to our
   own users in our terms of use.

2. United Kingdom — the Companies House public register, api.company-information.service.gov.uk,
   accessed with our own registered API key. Register information is made available under section 47
   of the Copyright, Designs and Patents Act 1988 and Schedule 1 of the Database Regulations
   (SI 1997/3032), and Companies House states: "Companies House imposes no rules or requirements on
   how the information on the public register is used" —
   https://www.gov.uk/government/publications/companies-house-accreditation-to-information-fair-traders-scheme/public-task-copyright-and-crown-copyright
   API terms of use: https://developer.company-information.service.gov.uk/manage-applications/terms-of-use
   We credit it as "Crown copyright — Companies House public register, free to re-use" even though
   the register data carries no attribution obligation, because a citation is what makes an agent's
   answer checkable.

3. Sweden — Bolagsverket's "värdefulla datamängder" API (high-value datasets under the EU Open Data
   Directive), gw.api.bolagsverket.se, accessed with our own OAuth 2 client credentials. Bolagsverket
   states that no agreement is required to use the API ("Det krävs inget avtal för att du ska få
   använda vårt API för värdefulla datamängder") and that the data may be used freely for commercial
   and non-commercial purposes. Bolagsverket names no licence, so neither do we: our licence field
   reads "Free re-use (Bolagsverket/SCB high-value datasets, EU Open Data Directive) — the publisher
   names no licence", because putting a familiar licence name there would be a fabrication.
   https://bolagsverket.se/apierochoppnadata/hamtaforetagsinformation/vardefulladatamangder/kundanmalantillapiforvardefulladatamangder.5528.html

4. Legal Entity Identifiers — GLEIF Level 1 data, published under CC0 1.0, keyless:
   https://www.gleif.org/en/about/open-data

The MCP server domain (api.foretak.dev) is our own and is the domain named in our privacy policy,
our terms and every package we publish.

What we log and keep. We record, per call: the country, the identifier or search text, the tool or
route used, the time, the outcome, and the client's User-Agent. We do not log IP addresses. For a
country whose company identifier can be a natural person's national identity number — Sweden, where
a sole trader's organisationsnummer is their personnummer — the identifier is not written to the log
at all; the country, route, time, outcome and User-Agent still are. That is a blanket rule by
country, not a per-record guess, and it is why we also disabled the web server's own access log.
Register responses are cached for at most 24 hours. Log entries older than 12 months may be deleted.
No accounts, no cookies, no analytics, no advertising, no payment data, and nothing is resold or
enriched. Full text: https://api.foretak.dev/legal/privacy

What we do not collect. We do not read Claude's memory, chat history, conversation summaries or user
files, and we collect no conversation data beyond the identifier and country a tool call needs to
answer it.
```

*(Provenance for the claims above, for whoever has to defend them: `DECISIONS.md` D-038 (Sweden's
licence string and why no name is invented), D-039 (a Swedish sole trader's identifier is a
personnummer), D-040 (the identifier is never written to the usage log; `--no-access-log`);
`UK_SPEC.md` §1.8 (Crown copyright, and why it is **not** the Open Government Licence — the easy
mistake); `SWEDEN_SPEC.md` §1.3 (the "no agreement required" quote); `legal/privacy.md`;
`legal/terms.md`.)*

---

## 9. Step "Test & launch"

> "Test-account setup and access instructions detailed enough for a reviewer to access your server
> end to end: every link, credential, and step, including credentials for a fully populated account
> where relevant. You also confirm you've run every tool yourself, either via MCP Inspector or as a
> custom connector in Claude." — submission docs
>
> "**Test credentials** are required and must be a fully populated account." — review criteria

### 9.1 On the test-credentials requirement

There is no account to give. The server takes no authentication, so every reviewer already has the
fully populated account: the three national registers themselves, with every registered company in
the United Kingdom, Norway and Sweden in them. Say that plainly in the box, then give the calls.

### 9.2 The reviewer instructions to paste

```
No credentials are needed. This connector requires no account, no API key and no sign-up: add
https://api.foretak.dev/mcp as a Streamable HTTP connector and every tool answers immediately. The
"populated account" is the national registers themselves — every registered company in the UK,
Norway and Sweden. The three companies below are large, listed, long-established entities used as
the documented examples throughout our README, so they will not disappear between submission and
review.

TEST 1 — Norway, identity and VAT status.
  Tool: lookup_company
  Arguments: {"id": "923609016", "country": "NO"}
  Expect: name "EQUINOR ASA"; status "active"; is_active true; legal_form_code "ASA";
  vat_registered true with vat_number "NO923609016MVA"; business_address in STAVANGER;
  source "Enhetsregisteret (Brønnøysundregistrene)"; license "NLOD 2.0"; a fetched_at timestamp and
  a cached flag. (Volatile fields such as employees change with the register; the name, status,
  legal form, VAT registration, source and licence do not.)

TEST 2 — United Kingdom, filing deadlines with the reason attached.
  Tool: company_deadlines
  Arguments: {"id": "00445790", "country": "GB", "today": "2026-09-04"}
  Expect: company_name "TESCO PLC"; today echoed as "2026-09-04"; two deadlines, kinds
  "confirmation_statement" and "annual_accounts", each with a due_date, a period_end, a days_until
  and an applies_because reading "Companies House publishes this date for the company itself; it is
  the register's own figure, not a calculation." At the time of writing those dates are 2027-07-02
  and 2027-08-26; they move when Tesco files, because they are the register's own figures — the
  assertion to test is that each date arrives with the provenance sentence, not that the date is
  unchanged. Passing "today" explicitly makes days_until reproducible.

TEST 3 — Sweden, the same shape from a third register.
  Tool: lookup_company
  Arguments: {"id": "5560160680", "country": "SE"}
  Expect: name "Telefonaktiebolaget LM Ericsson"; legal_form_local "Aktiebolag"; status "active";
  industry_codes carrying SNI 2007 code 70100; source "Bolagsverket (bolagsverket.se)"; license
  "Free re-use (Bolagsverket/SCB high-value datasets, EU Open Data Directive) — the publisher names
  no licence". Note the identical field names to TEST 1 — one shape across three countries is the
  point of the connector.

THE REMAINING TOOLS, in one pass:
  validate_company_id {"id": "923609016", "country": "NO"} -> valid true, no network call.
  validate_company_id {"id": "123456789", "country": "NO"} -> valid false, reason "'123456789' is
    not a valid Norwegian organisasjonsnummer.", hint "An organisasjonsnummer is nine digits with a
    MOD11 check digit, e.g. 923609016. If you have a company name instead, call search_company."
    This is the error contract working, not a failure.
  list_countries {} -> three entries (GB, NO, SE), each with its identifier scheme, an example
    identifier, source URL, licence, whether the upstream needs a key, and which attachments that
    country supports.
  search_company {"name": "Equinor", "country": "NO"} -> a list of hits with identifiers.
  search {"query": "Equinor"} and fetch {"id": "NO:923609016"} -> the two ChatGPT connector aliases,
    same data through the two-tool shape those clients require.

ONE DELIBERATE ERROR, so it is not read as a bug:
  search_company {"name": "Ericsson", "country": "SE"} returns the error code "not_implemented" with
  a hint explaining that Bolagsverket's free API has no name-search operation at all — four
  operations, none of which accepts a name. This is stated in the tool description, in the server
  instructions and in the listing description. Use "NO" or "GB" to exercise search_company
  successfully. Every error from every tool is JSON of the shape
  {"error": {"code", "message", "hint"}}, and the hint always names the next action.

Human-readable equivalents of the same three calls, if you prefer curl (the REST API returns
byte-identical payloads to the MCP tools):
  curl https://api.foretak.dev/v1/NO/company/923609016
  curl "https://api.foretak.dev/v1/GB/company/00445790/deadlines?today=2026-09-04"
  curl https://api.foretak.dev/v1/SE/company/5560160680

Documentation: https://github.com/foretak/registry-mcp
Privacy policy: https://api.foretak.dev/legal/privacy
Terms of use:   https://api.foretak.dev/legal/terms
Support:        hello@foretak.dev
```

### 9.3 The confirmation checkbox

> "You also confirm you've run every tool yourself, either via MCP Inspector or as a custom connector
> in Claude." — submission docs

**Kim must actually do this before ticking it**, and it is the one item in this package an agent
could not do on Kim's behalf: standing instructions bar this project's agents from making lookup
calls against production. Adding `https://api.foretak.dev/mcp` as a custom connector in Claude and
running the seven calls in §9.2 takes about five minutes and is also the fastest way to see the
listing the way a reviewer will. See `HUMAN_TODO.md` §7.9 step 3.

---

## 10. Step "Compliance"

> "Seven policy acknowledgments covering the directory guidelines, first-party API usage, financial
> transactions, AI media generation, prompt injection, conversation data collection, and public
> documentation. **All seven are required.**" — submission docs

Each one, with why it can be ticked honestly:

| # | Acknowledgment | Position |
|---|---|---|
| 1 | Directory guidelines / Software Directory Terms and Policy | Accept. The Terms' open-source and "spec will evolve" clauses are "required and not waivable" (review criteria) — the repo is MIT-licensed and public, so both are already true. |
| 2 | First-party API usage | Accept **with the §8 declaration**. Proxied public-register data under each publisher's own open-data terms; the server domain is ours. |
| 3 | No financial transactions | Accept. Nothing transfers money, cryptocurrency or any financial asset. There is no write path at all. |
| 4 | No AI media generation | Accept. No images, video or audio are generated. |
| 5 | No prompt injection | Accept. Tool descriptions describe what the tool does. They do not instruct Claude to call other software, do not interfere with other tools, do not pull instructions from external sources, contain nothing hidden or encoded, and promote nothing. See §12 PASS-7. |
| 6 | No conversation-data collection | Accept. We log the identifier, country, tool, time, outcome and User-Agent — the arguments a lookup needs — and nothing else. We never query Claude's memory, chat history, conversation summaries or user files. |
| 7 | Public documentation | Accept. `https://github.com/foretak/registry-mcp` — README, `docs/clients.md`, `static/llms.txt`, `static/llms-full.txt`, plus the served server card. Public today, not "by the publish date". |

---

## 11. Step "Review"

> "A final read-through of everything you've entered. Any quality warnings (for example, very short
> answers) are shown here and shared with the review team alongside your submission." — submission docs

Nothing in this package is a short answer. If the portal flags one anyway, expand it from the
material in §5 and §8 rather than padding it.

Then submit. What happens next, quoted so the wait is not mistaken for silence:

> "When you submit a server, it is automatically scanned for policy compliance and, by default,
> listed in the directory as a community connector. Anthropic may then escalate listings flagged as
> highly useful to Claude users to verified review, which is higher touch and slower; reviewers run a
> functional test of each tool. This escalation is assessed automatically, and you do not need to
> take any action." — review criteria

So the realistic outcome is a **Community** listing with a "Community" label, which is a normal
outcome and not a rejection. Both labels are eligible for the same thing that makes this submission
worth $50/month:

> "Directory connectors are eligible for **Suggested Connectors** — in-chat recommendations when
> relevant to the user's task. **Every directory entry is included automatically.** **Ranking is
> usage-based**, similar to other app stores." — [directory docs](https://claude.com/docs/connectors/directory)

Read that last clause honestly before setting any expectation: a listing with zero usage ranks last,
and Suggested Connectors presumably weights the same ranking. `~/mcp-growth/ADOPTION.md` Finding 3
rates this **high confidence that it is the best available surface in the ecosystem, low confidence
that it produces usage inside 30 days.** The directory grew from 369 entries on 2026-06-19 to 1,253
in August 2026, so the uncrowded window is closing, and **no Nordic or UK register is listed** — that
is the reason to do it now, not a promise about what it returns.

---

## 12. Review-criteria checklist

Every item on <https://claude.com/docs/connectors/building/review-criteria>, plus the submission
docs' own requirements, marked PASS with evidence or OPEN with what Kim must do. Evidence is a
file:line at `c854e9e`, or a live URL checked 2026-09-08.

### PASS

| # | Criterion | Evidence |
|---|---|---|
| PASS-1 | **Separate read and write tools** — no catch-all tool taking safe and unsafe HTTP methods | There is no write tool and no `method` parameter anywhere. All seven tools are read-only; `src/registry_mcp/mcp/server.py:259-270` defines the only two annotation sets, `_READ_EXTERNAL` and `_READ_LOCAL`, and both carry `readOnlyHint: True, destructiveHint: False`. |
| PASS-2 | **Reference API docs in custom query tools** | Not applicable — no tool accepts a freeform endpoint path, query string or request body. Every tool calls a fixed upstream operation internally. ("Purpose-built tools that call a fixed endpoint internally do not need an API docs reference.") Each tool nonetheless names its upstream register and returns `source_url` per response. |
| PASS-3 | **Tool annotations: `title` + applicable hint on every tool** | All seven, on the wire: `https://api.foretak.dev/.well-known/mcp/server-card.json` — table in §3.1. In source: `src/registry_mcp/mcp/server.py:331-337, 406-412, 480-486, 550-556, 601-607` and the connector aliases in `src/registry_mcp/mcp/connector.py`. This is the requirement that fails most submissions; it was already true before this task started. |
| PASS-4 | **Tool names ≤ 64 characters** | Longest is `validate_company_id`, 19. |
| PASS-5 | **Narrow, accurate descriptions matching actual behaviour** | Every tool docstring names its countries, its identifier schemes and its error modes; `search_company`'s says Sweden raises `not_implemented`, which is what it does. The `include` parameter description tells the caller to read `list_countries`' `supported_includes` rather than guess. |
| PASS-6 | **HTTPS Streamable HTTP transport** | `https://api.foretak.dev/mcp`, HTTPS only; `/mcp` and `/mcp/` both answer with no redirect between them. *Evidence is the served card plus the orchestrator's own production smoke test of the 2026-09-08 deployment (`PROGRESS.md`, Deploy row) — this task did not probe the endpoint itself, per the standing instruction.* |
| PASS-7 | **No prompt-injection patterns** | No tool description instructs Claude to call other software, interferes with other tools, sources instructions externally, hides or encodes anything, or promotes a product. The three prompts instruct Claude about *this* connector's own output only — and the one behavioural instruction any of them gives (`counterparty_check`'s closing "What this does not establish" section) exists to make Claude claim **less**, not more. |
| PASS-8 | **Every tool returns a successful response for valid parameters; no generic errors** | Every error is `{"error": {"code", "message", "hint"}}` with an actionable hint — stated in the server `instructions` and enforced by the REST↔MCP parity tests. No "Internal Server Error" path: an upstream failure returns `upstream_error` naming the upstream and, where relevant, the missing environment variable. |
| PASS-9 | **Validate inputs, actionable errors** | `validate_company_id` exists solely for this and costs no network call: it checksum-checks a Norwegian orgnr, shape-checks and normalises a UK CRN (`'445790'` → `'00445790'`, `'oc303675'` → `'OC303675'`). An unsupported country returns `unsupported_country` naming the supported set. |
| PASS-10 | **Responses reasonably sized** | A `CompanyReport` is one company, roughly 1–3 kB of JSON. Attachments are opt-in and absent by default (`include=[]`), so the default call is exactly one upstream request. `search_company` returns a bounded hit list. Nothing dumps a database. |
| PASS-11 | **No conversation data collected beyond function; no reading memory / chat history / user files** | The server has no such capability. What is logged is listed in §8 and in `legal/privacy.md`. |
| PASS-12 | **Not an unsupported use case** | Transfers no money or crypto (no write path); generates no images, video or audio. |
| PASS-13 | **Test credentials** | Not applicable and explained rather than skipped — no authentication, so the "fully populated account" is the registers themselves (§9.1). |
| PASS-14 | **Allowed link URIs** | Not applicable — the server does not use `ui/open-link`. It returns `source_url` as data in the payload; the client decides what to do with it. Leave the field empty (it is optional). |
| PASS-15 | **Public documentation by publish date** | Public now: <https://github.com/foretak/registry-mcp>. |
| PASS-16 | **MCPB / open-source clauses in the Software Directory Terms (not waivable)** | Repo is public and MIT (`LICENSE`). |
| PASS-17 | **Privacy policy served over HTTPS, no login** | `https://api.foretak.dev/legal/privacy` → **200**, `text/html`, 6,171 bytes. Actually reachable since commit `0d20df9` ("Ship `legal/` in the container, so the privacy policy route actually resolves") — before that the route existed and 404'd, which by itself was an automatic rejection from this channel. **But read OPEN-1: served is not the same as complete.** |
| PASS-18 | **Icon** | `https://api.foretak.dev/icon.png` → **200**, `image/png`, 400×400, 8,882 bytes. |
| PASS-19 | **Support contact** | `hello@foretak.dev`, published in the privacy policy, the terms, `SECURITY.md` and every package manifest. |
| PASS-20 | **`claude plugin validate`** ("Run `claude plugin validate` on plugins" — review criteria, "Before you submit") | Not required for an MCP-server submission, but run anyway for the companion plugin: passes. See `HUMAN_TODO.md` §7.9 track 2. |

### OPEN — Kim's, and two of them are content fixes, not clicks

| # | Open item | What must happen |
|---|---|---|
| **OPEN-1** | **The served privacy policy is out of date, and "missing or incomplete privacy policies result in immediate rejection."** The live page at `https://api.foretak.dev/legal/privacy` (byte-identical to `legal/privacy.md` at `c854e9e`, checked on the wire 2026-09-08) says under *What the service does*: "Today: Norway … and the United Kingdom." **Sweden has been live since 2026-09-07** and is named in the same page's logging paragraph — so the page contradicts itself, omits Bolagsverket from *What we send to third parties* and from *Legal basis and licences*, and will omit GLEIF once `lei` deploys. It also still opens "**Draft** written 2026-09-05 for Kim's review; effective once published at a public URL" — on a page that **is** published. | **Fix before submitting.** Four edits to `legal/privacy.md`, then deploy: (a) drop the "Draft … effective once published" sentence, replace with an "Effective / last updated" date; (b) *What the service does* names all three registers — add "Sweden (Bolagsverket, `gw.api.bolagsverket.se`)"; (c) *What we send to third parties* names Bolagsverket (OAuth 2 client credentials, our own) and, once `lei` is deployed, GLEIF (keyless, CC0); (d) *Legal basis and licences* adds the Bolagsverket sentence from §8 verbatim, and GLEIF CC0. This file is outside T50's write footprint, so it is **not** done here. It is the single highest-risk item in this package. |
| **OPEN-2** | **The served terms page covers Norway only.** `https://api.foretak.dev/legal/terms` names NLOD 2.0 and Brønnøysundregistrene and says nothing about Companies House or Bolagsverket. Terms are **not** a portal field, so this does not block submission — but the privacy page footer links to it, and a reviewer following that link sees a two-country gap in a three-country listing. D-045(a) separately requires the terms to name three charge text fields; that ride is with T47. | Fold the §8 licence paragraphs for GB and SE into `legal/terms.md` § *Where the data comes from*, alongside T47's charge-field edit. Not blocking. |
| **OPEN-3** | **Claude Team organisation.** The portal is org-settings-only; the account is an individual plan. | Kim buys Claude Team, two seats, ≈$50/month billed monthly, cancellable — `HUMAN_TODO.md` §7.9 step 1. This is the only item that costs money and the only one no agent may do. |
| **OPEN-4** | **The "I have run every tool myself" confirmation** (§9.3). | Kim adds the connector in Claude and runs the seven calls in §9.2. Five minutes. Agents on this project are barred from lookup calls against production, so this cannot be pre-satisfied. |
| **OPEN-5** | **Which description, A or B** (§3.2, §4.3, §4.4). | Check `https://api.foretak.dev/health`. `0.3.0` → Description A. `0.4.0` → Description B. Nothing else about the package changes. |
| **OPEN-6** | **The slug is permanent.** | Confirm `company-check` is free in the portal; if not, `company-check-registers`. Decide before pressing Submit, because it cannot be changed afterwards. |
| **OPEN-7** | **Listing name.** The one editorial decision this package cannot make for Kim. | §4.1 recommends `Company Check — UK, Sweden & Norway business registers`. If Kim prefers another, the only hard rules are: ≤100 characters, and **never `registry-mcp`**. |

---

## 13. Every URL in this package, with its HTTP status

Checked 2026-09-08 late evening CEST from this machine. `curl -sIL -o /dev/null -w '%{http_code}'` (or a body GET where
noted).

| Status | URL | Note |
|---|---|---|
| 200 | `https://api.foretak.dev/health` | `{"status":"ok","version":"0.3.0","countries":["GB","NO","SE"]}` |
| 200 | `https://api.foretak.dev/icon.png` | `image/png`, 400×400, 8,882 bytes |
| 200 | `https://api.foretak.dev/legal/privacy` | `text/html`, 6,171 bytes — see OPEN-1 |
| 200 | `https://api.foretak.dev/legal/terms` | `text/html`, 8,544 bytes — see OPEN-2 |
| 200 | `https://api.foretak.dev/.well-known/mcp/server-card.json` | `application/json`, 132,758 bytes; 7 tools, 3 prompts, `authentication.required: false` |
| 200 | `https://api.foretak.dev/llms.txt` | `text/plain`, 3,035 bytes |
| — | `https://api.foretak.dev/mcp` | **Not probed.** Standing instruction: unlogged static routes only, no tool calls against production. The MCP endpoint's health is evidenced by the served card and by the orchestrator's own smoke test of the 2026-09-08 20:47Z deployment (`PROGRESS.md`, Deploy row). |
| 200 | `https://github.com/foretak/registry-mcp` | Documentation URL |
| 200 | `https://data.norge.no/nlod/en/2.0` | NLOD 2.0, English |
| 200 | `https://data.norge.no/nlod/no/2.0` | NLOD 2.0, Norwegian (the URL `legal/terms.md` cites) |
| 200 | `https://www.gov.uk/government/publications/companies-house-accreditation-to-information-fair-traders-scheme/public-task-copyright-and-crown-copyright` | The Crown-copyright position quoted in §8 |
| 200 | `https://developer.company-information.service.gov.uk/manage-applications/terms-of-use` | Companies House API terms |
| **000** | `https://bolagsverket.se/apierochoppnadata/hamtaforetagsinformation/vardefulladatamangder/kundanmalantillapiforvardefulladatamangder.5528.html` | **Not reachable from this machine, and not evidence the URL is dead:** `bolagsverket.se` resolves IPv6-only here (`2001:67c:2214:299::150`) and this host has no IPv6 route, so every request to that domain fails at connect. The URL and the "Det krävs inget avtal…" quote are recorded verbatim in `SWEDEN_SPEC.md` §1.3 from the page itself ("Uppdaterad: 2026-07-07"). **Kim: open it once in a browser before pasting §8.** |
| 200 | `https://www.gleif.org/en/about/open-data` | GLEIF CC0 |
| 200 | `https://www.gleif.org/en/meta/lei-data-terms-of-use` | GLEIF terms (alternative citation) |
| 200 | `https://www.claude.com/pricing` | Team plan $25/seat/month monthly, $20 annually, "teams of 2 to 150", cancel anytime |
| 200 | `https://claude.com/docs/connectors/building/review-criteria` | |
| 200 | `https://claude.com/docs/connectors/building/submission` | |
| 200 | `https://claude.com/docs/connectors/directory` | |
| 200 | `https://claude.com/docs/connectors/verification` | |
| 200 | `https://claude.com/connectors` | The public directory — category list in §4.5 |
| 200 | `https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy` | |
| 200 | `https://support.claude.com/en/articles/13145338-anthropic-software-directory-terms` | |
| **403** | `https://claude.ai/admin-settings/directory/submissions/new` | Expected. The portal is behind Kim's login and behind the Team-organisation requirement; 403 to an unauthenticated fetch is what a working private admin route looks like. |
| 200 | `https://platform.claude.com/plugins/submit` | Track 2 — the plugin form, free, individual Console login |

---

## 14. What this package could not establish

1. **What a fresh listing actually receives.** "Ranking is usage-based" is first-party and explicit;
   how much traffic a zero-usage entry gets is published nowhere. `~/mcp-growth/ADOPTION.md` searched
   for it and found nothing. Treat the $50/month as buying a **position**, not traffic, and re-read
   the number at the day-45 gate.
2. **Whether the API-ownership answer passes.** The precedents (Pappers, Firmenbuch, D&B) are strong
   and the portal has a step for exactly this case, but no published decision covers a proxied
   *foreign government* register specifically. §8 is the best available answer; it is not a guarantee.
3. **Live confirmation of every tool.** Standing instructions bar this project's agents from calling
   production lookups. Everything asserted about tool behaviour here comes from the served server
   card, the source at `c854e9e`, and the orchestrator's own production smoke test recorded in
   `PROGRESS.md` — not from calls made by this task. OPEN-4 is where that gap closes.
4. **The exact portal widgets.** The step list, the field labels and the character limits are quoted
   from Anthropic's own submission docs, which is the best available source; the portal itself is
   behind the Team wall. If a field differs, the docs are what this package was built from — trust
   the screen, and note the difference back into this file.
5. **The Bolagsverket citation URL** — see the 000 row in §13. Reachable, just not from here.
6. **The peer listings, first-hand.** Pappers, Firmenbuch, Contract-Factory and the two D&B
   connectors are named on the strength of `~/mcp-growth/ADOPTION.md` Finding 3 and the census it
   cites (node8.ai, August 2026: 1,253 connectors, 1,206 publishers, Finance 159, Data & Analytics
   198). The public directory at <https://claude.com/connectors> paginates client-side and the
   fetched page returned only its first screen, so **this task did not see those five entries with
   its own eyes.** The category list in §4.5 *is* first-hand from that page. If §8's precedent
   argument matters to Kim, spend two minutes searching the live directory before submitting.
7. **Whether the numbers in §11 have moved.** "369 → 1,253 entries in two months" is ADOPTION's
   measurement, one day old at the time of writing and not re-measured here. The direction is what
   the argument rests on, not the figure.
