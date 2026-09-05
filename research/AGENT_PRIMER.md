# registry-mcp — agent primer

Read this first if you are an agent working on registry-mcp. It condenses a
154,000-word research library built on 2026-09-05 by seven researchers, each
folder sourced with URLs and fetch dates under the rules in `BRIEF.md`. Every
figure below is dated **as of 2026-09** and traces to a folder README, which
traces to a source file. Re-verify anything older than a quarter before acting
on it. Where two folders disagree, the disagreement is noted here.

Folder key: **01** market and buyers · **02** registers landscape · **03**
regulation drivers · **04** MCP and agent ecosystem · **05** competitors ·
**06** accounting and finance software · **07** product improvements.

---

## 1. What the product is, in the words the evidence supports

registry-mcp is *the company registry MCP*: five read-only tools
(`lookup_company`, `search_company`, `validate_company_id`,
`company_deadlines`, `list_countries`) that return one JSON shape for every
country. Live: Norway (Brønnøysundregistrene, keyless) and the UK (Companies
House, free key). Denmark applied for (Erhvervsstyrelsen sagsnummer 177481,
answer due ~2026-09-23). Hosted at `api.foretak.dev` with an anonymous MCP
endpoint, and as `uvx registry-mcp` / `npx registry-mcp`. MIT.

The defensible line, after reading the competition (05): **one response shape,
deadlines with cited statutes, across countries, free and keyless.** Not "an
MCP server for brreg" (fourteen exist) and not "the one that computes
deadlines" (Apier does, in Norway, with legal references and a versioned
rulebook).

Positioning to use (Dunford frame, 01/06): not a data vendor and not a KYB
suite. **The agent-callable register excerpt with provenance**, for accounts
payable, VAT verification and onboarding, sold on licence and shape rather
than price.

## 2. Ten facts that change decisions

1. **We were not first, and the name audit missed the two that matter.**
   Proff (Enento) ships "Proff Premium MCP" for NO/SE/DK/FI, quote-only behind
   a NOK 12,490–24,990/year subscription (01). PowerLaunch's **Apier** ships
   26 tools including Norwegian deadlines and obligations with legal
   references, NOK 0–9,999/month or 0.50 kr/call, free in beta, Norway-only,
   key-required (05). Our edge is self-serve, open, keyless, multi-country.
2. **Anonymous access predicts usage; breadth does not.** ENTIA (anonymous
   endpoint) has 16,045 Smithery uses; OpenRegistry (30 registries, key
   required) has 3. The UK competitor `bouch/uk-due-diligence` has 60,787
   uses with a two-line outcome-focused description (04, 05). **Protect the
   keyless Norway path and the anonymous hosted endpoint.**
3. **Lookups are worth 16–20 pence wholesale and are given away free.**
   D&B and Creditsafe G-Cloud filings; Companies House 600 req/5 min free;
   brreg free with no registration. Per-lookup pricing is a lost war. The
   only self-serve comparable, Endole, gives lookups away and meters exports
   at £25–39/month (01). Market rate for agent-consumed retrieval is about
   half a cent to a cent per call (Exa, Tavily, Apify) (04).
4. **There is an empty price band.** Moody's/kompany starts at £15,150/year
   with a 12-month minimum; OpenCorporates at £2,250/year for 500 calls a
   month; below them, the free registers; between, nothing self-serve (01).
   Moody's terms forbid AI use of its data; NLOD 2.0 and Crown copyright do
   not. OpenCorporates is ODbL share-alike, incompatible with an MIT hosted
   API (01, 02).
5. **Nobody who hit a free ceiling offered to pay.** Companies House forum
   users ask for higher free rate limits, not a paid tier. No neutral case
   study of switching from an incumbent to open data exists (01). Whether
   anyone pays is the open question the day-45 gate must answer.
6. **The two lead use cases are table stakes inside accounting software.**
   Fiken warns on VAT purchases from unregistered suppliers and on
   bankruptcy; e-conomic shows CVR bankruptcy status at every invoice (06).
   What none of them produces is a machine-readable answer with `source_url`,
   `fetched_at`, `license` and `applies_because`. Sell the surface, the
   provenance and the plurality, not the function.
7. **Demand is being legislated, with dates.** Norway: mandatory B2B
   e-invoicing from **1 January 2027**, scoped to counterparties in the ELMA
   register, looked up by `0192:<orgnr>` (03). EU AMLR from **10 July 2027**:
   every new legal-entity relationship needs "valid proof of registration or
   a recently issued excerpt of the register" (Art. 23(4)); "recently" is
   undefined (03). EBA guidelines since October 2023 already require the
   register check in fully automated onboarding (03).
8. **Compliance beats fraud as the story.** Skatteklagenemnda NS 116/2018:
   kr 691,100 input VAT disallowed plus kr 138,220 penalty for not checking
   the seller's VAT registration; NS 27/2019 similar (03, 06). Finanstilsynet
   Rundskriv 15/2019 requires an Enhetsregisteret lookup no older than one
   month with a provable record; our 24 h cache and `fetched_at` satisfy it
   30× over (06). Invoice fraud is at record lows and is payment redirection,
   which a registry lookup does not stop (06). Do not overclaim there.
9. **Beneficial ownership is gated almost everywhere and Norway's gate has no
   vendor category** (03, 02). Estonia is the only register still publishing
   it openly. Do not promise it. Represent it as an empty list with a reason.
10. **Our server is more correct than it is legible.** All five tools ship an
    empty `outputSchema`, no annotations (so clients treat them as possibly
    destructive and may prompt on every call), and no parameter descriptions
    or patterns (07). Smithery's listing had an empty description and was
    unsearchable until 2026-09-05 (fixed via the registry API) (04). The
    official MCP registry searches server names only, so our twenty keywords
    do nothing there (04). llms.txt is documentation, not a discovery
    channel (04, 07).

## 3. Where the numbers come from, and how far to trust them

- Register scale: Companies House 5,479,045 companies, 16.3 bn accesses in
  2024-25 (undefined metric); Enhetsregisteret 1,173,016 entities, 409,507
  VAT-registered (live API read) (01).
- Market size reports for "KYB" disagree by 34× (US$366 m to $12.4 bn). Do
  not quote a top-down market size. Three audited incumbents total ~$2.9 bn
  revenue: D&B $2,381.7 m, Creditsafe €289 m, Enento €150.4 m (01).
- Directory scale: official registry 27,184 servers growing ~450/day, not
  consumed by clients directly; Smithery 11,656 listed but only 500
  browsable; Glama ~81,800 crawled (04).
- Whole company-registry MCP field: ~1,900 npm+PyPI downloads a month; the
  leading brreg server does 236 npm downloads a month (05). Winning Norway
  means a few hundred developers.
- Show HN for MCP servers: 317 posts in a year, median 2 points, none over
  100 (04). One lottery ticket at most.

## 4. Countries: the order and the traps

Ranking after Denmark (02), scored on access × market × English × how much
the register publishes: **Sweden** (free since 3 Feb 2025, OAuth2, 60
req/min) → **Finland** (no key at all, English payload, hands over a EUID) →
**Ireland** (CC BY 4.0 daily data, free REST, publishes an Annual Return
Date) → **France** (largest open register, keyless, hard data model) →
**Switzerland** (free SPARQL) → **Estonia** (only open beneficial owners,
tiny market, GDPR exposure). Excluded with reasons: Germany (no official
API), Netherlands (eligibility and redistribution unknown), Belgium
(bulk-only), Poland (no English, statuses inferred), Austria/Italy
(fees or national ID), Spain (gazette replay), US (fifty-one registers).

Do three cheap things before country 4 (02): a nullable `euid` on
`CompanyReport`; GLEIF LEI as a cross-cutting CC0 join key, not a country;
an advertising-protection marking field (Danish CVR-loven § 19 makes marking
a legal condition; Sweden's REKLAMSPÄRR is the same). Decide the sub-national
key question (German Länder, US states) in DECISIONS.md before it is urgent.

Traps found (02): Denmark's system-to-system endpoint is plain HTTP only and
its filing deadline is now 6 months, not 5; Belgian enterprise numbers no
longer start with 0; France's `etat_administratif` does not know about
insolvency and redacts non-diffusible records as `INFORMATION NON-DIFFUSIBLE`;
Finland's statuses are bare integers; Poland needs the right `rejestr` and
returns an as-of date; Swedish sole-trader numbers are not unique to one
business. Every check-digit rule marked VERIFY in 02 must be read from an
official spec before implementation.

Sweden is a separate decision, not a fourth folder: Bokio buys its data from
the credit bureau UC, and the free HVD API's fit for our use is unverified
(06, 02).

## 5. Distribution: what to do and what to stop

Do (04, 07): tool annotations and titles (required by Anthropic's and
OpenAI's directories, a Glama score input); real output schemas; the README
first screen (deadlines, 24 h freshness versus OpenCorporates' documented 30
days, five tools versus a ~40-tool client budget, a security paragraph, one-
click install badges); claim the Glama listing when it appears; hand-install
for ten named developers. Consider `search`/`fetch` aliases for the ChatGPT
connector contract (05). Cost the Claude Connectors Directory deliberately: it
needs a paid Team/Enterprise Claude org.

Stop or expect nothing (04): more directory submissions, paid listing tiers,
llms.txt as a channel, Show HN beyond one attempt. PulseMCP ingests
automatically. Reddit r/mcp is the one channel with zero evidence either way;
first post was filtered on 2026-09-05, modmail sent.

Partners worth a conversation (06): **Pleo** (Nordic, AP agent ingesting
supplier invoices, ~40,000 businesses, nothing to check suppliers with),
**Tripletex** (most-used by Norwegian accountants, open API, lookup stops at
autofill with no VAT or status warning), and the accounting-MCP builders
(Weavio on Fortnox's marketplace at SEK 249/month, Proviscale, Apideck,
Composio) who need a registry tool and will not build one.

## 6. Pricing hypothesis (01, 04) — a hypothesis, not a plan

Free stdio forever. Hosted free tier that beats Companies House's 600/5 min
(~1,000 lookups/day), no export. First paid step around £15–29/month metering
exports and monitored companies, not lookups. Team tier £99/month. Enterprise
from ~£6,000/year, half OpenCorporates Basic and well under Moody's floor.
Meter the hosted endpoint now so the tiers can be designed from real usage;
charge nothing until a caller exists. The build plan's "10–30k NOK/month from
one Norwegian customer" is 12–30× Proff's annual seat price and should not be
used as a goal until re-examined (01).

## 7. Product backlog, ranked (07)

1. README first screen. 2. Real `outputSchema` from existing models. 3. Tool
annotations and titles. 4. Input schema descriptions, patterns, bounds. 5.
`CHANGELOG.md`, `SECURITY.md`, request ids. 6. The 26-case agent eval in CI
(`07/08-eval-set-registry-mcp.md`). 7. Batch lookup (touches core). 8. NACE
harmonisation (UK SIC 2007 and Norwegian SN2007 are both NACE Rev.2). 9.
Concrete `registry://rules/{cc}` resources. 10. Honest-caveat trio (ENK
personal data, group walk, "does not screen sanctions/PEP"). 11. API keys and
metering (the gate to revenue; moves to #1 the day a customer exists). 12.
Change-feed cache invalidation. 13. Officers and GB PSC as `include=[...]`
after four privacy decisions. 14. Norwegian annual-accounts key figures. 15.
UK filed documents as resource links.

Items 1–5 touch no `core/` file and total about two days. Declined with
reasons: sanctions/PEP screening, webhooks, OAuth before a customer, UK iXBRL
parsing, Norwegian beneficial owners, hosting bulk snapshots, renaming tools.

Highest-value addition an accounting agent asked for that nobody offers (06,
03): a **Peppol/ELMA capability lookup** on the same identifier, which also
happens to be the 1 January 2027 Norwegian e-invoicing requirement.

## 8. Correctness flags raised by the research (not yet reviewed)

Folder 03 file 12 carries verbatim citations for the Norwegian deadlines and
notes that the weekend/holiday roll-forward rule is written into
a-opplysningsforskriften § 2-1 but **not** into skatteforvaltningsforskriften
§ 8-3-10 or regnskapsloven § 8-3; that the third VAT period is due 31 August,
not 10 August; and that regnskapsloven § 8-3(1) sets 1 February for financial
years ending 1 January–30 June. If confirmed against `registries/no/rules.py`,
`applies_because` cites sections for rules they do not contain. Needs an
architect review before any fix. Also: Denmark's deadline is 6 months (02).

## 9. Open questions the library could not close

Would anyone pay (01). What "recently issued" means in AMLR Art. 23(4) (03).
Proff Premium MCP's price and limits (01). Whether a Norwegian ENK can get
Danish, Dutch or Italian access at all (02). Danish CVR rate limits and status
enum (02). Whether any client branches on `readOnlyHint` (07). Whether
directory listings cause installs at all (04). Germany's timetable for an
open register API (02). r/mcp's rules and worth (04).

## 10. Rules of evidence for extending this library

Follow `BRIEF.md`: every fact with a URL and fetch date; primary over
secondary; quote legal and numeric text; "not found" beats a guess; mark
confidence; date everything. Researchers hit the 200-call web-search budget
in every folder; plan the search order before starting and fall back to
direct fetches of primary documents.
