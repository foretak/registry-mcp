# 06 — Accounting and finance software: where company lookups already happen, and who is opening to agents

Thirteen files. Everything here was fetched on **2026-09-05**. Vendor help centres, government guidance and press releases are primary; comparison blogs and forum comments are labelled as such.

---

## Key findings

**1. registry-mcp's two lead use cases are already shipped features in Norwegian accounting software.** Fiken's help page (last updated 2025-10-08) documents both: *"Når du registrerer et leverandørkjøp med mva vil Fiken slå opp leverandøren i Brønnøysundregisteret. Hvis leverandøren ikke er mva pliktig vil Fiken advare det om dette"* and a konkurs warning on sales/purchases against a company under bankruptcy proceedings. e-conomic does the Danish equivalent: *"du kan se … hvis kunden er ved at gå konkurs ifølge CVR-registret"*, shown every time you create a customer or an invoice. **The function is table stakes; the surface (an agent, anywhere) and the citation (`source_url`, `fetched_at`, `license`) are the differentiators.** [File 01, 02]

**2. Tripletex — the system Norwegian accountants use most — does the lookup only as data entry.** Its help articles (customer, updated 2026-06-04; supplier, updated 2026-08-07) say the user must *click the brreg icon* to fetch info, and document **no VAT-registration or bankruptcy warning at all**. That is the clearest single product gap in Norway. [File 01]

**3. Xero, in April 2026, told 4.5 million subscribers to check VAT numbers on GOV.UK by hand** — *"Go to the official HMRC VAT number checker on the GOV.UK website"*, and *"Verify new suppliers: Check VAT numbers before making your first purchase"* — one month before putting its ledger inside Claude (integration live 2026-05-12). Intuit exposed **TurboTax, Credit Karma, QuickBooks and Mailchimp over MCP** (announced 2026-02-24, ~100 million customers). Sage shipped a **read-only** Intacct MCP server. **None of these agent surfaces can verify a counterparty.** [File 04]

**4. The same hole runs through every spend/AP agent shipped in 2026.** Pleo announced five agents including "Pleo MCP" on 2026-06-11 (beta July 2026, ~40,000 businesses); Ramp's MCP can list vendors and approve bills, with fraud detection across "60+ signals" — all behavioural; Payhawk's Cloudflare-verified agent collects invoices from vendor portals; Spendesk shipped Spendesk MCP. **Tipalti is the only exception**: it automatically checks EU VAT numbers against **VIES** at supplier onboarding, and markets 26,000 global rules and 3,200+ tax validation rules across 47 countries. Enterprises pay for register-backed identifier validation. [File 05]

**5. Skipping the VAT check has a decided price in Norway.** Skatteklagenemnda **NS 116/2018** (15 September 2018): input VAT of **kr 691,100 disallowed plus kr 138,220 penalty tax**, because the buyer deducted VAT on invoices from a seller not registered in Merverdiavgiftsregisteret and was found negligent for not checking. This is the strongest fact in the folder and belongs in `content/01-vat-check/`. [File 09]

**6. Norwegian AML guidance is a specification for `lookup_company`.** Finanstilsynet Rundskriv 15/2019 § 4.4.2: *"Organisasjonsnummer til den juridiske personen skal innhentes og bekreftes."* § 4.4.1: an *oppslag* against Enhetsregisteret/Foretaksregisteret no older than three months, and *"bør opplysningene ikke være eldre enn én måned"*, with *notoritet* (provable record) of the lookup itself. **A 24-hour cache TTL beats the one-month bar by 30×, and `fetched_at` + `source_url` is machine-readable notoritet.** [File 08]

**7. Be honest about fraud.** UK Finance's Annual Fraud Report 2026: total payment fraud **£1.28bn** in 2025; **invoice & mandate £41.3m across 2,305 cases**, "lowest loss total ever reported", with **68% (£28m) landing on business accounts**. But invoice & mandate fraud is *payment redirection* — the supplier is real and registered; the bank account is wrong. A registry lookup does not stop it. It stops fictitious suppliers, dissolved ones, and VAT charged by non-registered entities. Norway: Økokrim puts 2024 fraud proceeds at **kr 2.13bn** with ~⅓ never reported; Finanstilsynet reports **NOK 558m** lost in H2 2025. [File 10]

**8. The demand is documented, small, and articulate.** Xero Product Idea "Tax number validation…", posted 2025-10-06, **20 votes**, still "Gaining Support": *"NO VAT should be reclaimed on a bill without first verifying the quoted VAT registration number"* (Louise Williamson). And on GitHub, **15 brreg MCP repos exist; the best has 8 stars and half were pushed once and abandoned.** Demand is real; nobody has won; and the differentiator cannot be "we call brreg." [File 12]

**9. There is a priced shelf.** Fortnox's own integration marketplace sells **Weavio MCP – AI i bokföringen** at **SEK 249/month ex VAT**, plus a Fortnox integration licence from SEK 189/month — ~SEK 438/mo to talk to your ledger through Claude. Vendor marketplaces list third-party MCP servers. [File 03]

**10. Sweden is the odd one out.** Norway (brreg), Denmark (CVR) and Finland (YTJ) are free and every local product queries them directly. In Sweden, Fortnox uses Bolagsverket + Skatteverket, but **Bokio buys the data from UC**, the credit bureau, and its help page tells users to go check the name on Allabolag.se first. Sweden needs a different plan. [File 02]

---

## Vendor matrix

Read as: documented in the vendor's own public help/developer material on 2026-09-05. "—" = not documented (not proof of absence).

| Vendor | Country | Registry lookup on create | VAT-registration check | Deadlines shown | Public API | Agent / MCP |
|---|---|---|---|---|---|---|
| **Fiken** | NO | **Yes**, Enhetsregisteret, automatic | **Yes** — warns on MVA purchase from non-registered supplier | Skattemelding/årsregnskap filing in-product | Yes | — |
| **Tripletex** | NO | Yes, manual (click brreg icon) | — | Payroll/VAT filing in-product | **Yes** — OpenAPI, free test env | In-product AI assistant (unverified figures) |
| **PowerOffice Go** | NO | **Yes**, automatic — brreg **+ Proff.no** | — | In-product | Yes | — |
| **Visma eAccounting** | NO/SE/DK/FI/NL/UK | "Søk etter firma" field; source unconfirmed | — | In-product | **Yes** — developer.visma.com | 3rd-party `Proviscale/visma-mcp-server` (0★) |
| **Conta** | NO | — | No — Kaia checks the VAT **rate**, not registration | — | Yes | In-product AI (Kaia) |
| **Xledger** | NO | — | — | — | **Yes** — scoped API tokens | — |
| **24SevenOffice** | NO/SE | — | — | Altinn-integrated VAT filing | **Yes** — REST + legacy SOAP | — |
| **Uni Micro** | NO | — | — | — | **Not found** | — |
| **e-conomic** | DK | **Yes**, CVR — behind a setting ("Opslag på CVR-nr. og navn") | — | — | **Yes** — 250k+ customers, app-partner programme | 3rd-party (Peliqan, Workaist) |
| **Dinero** | DK | **Yes**, "vi trækker data direkte fra CVR-registret" | — | — | Yes | Visma Rating (shared with e-conomic): **konkurs from CVR** |
| **Billy** | DK | — (own CVR only) | — | — | Yes | — |
| **Fortnox** | SE | **Yes** — Bolagsverket + Skatteverket, free | — | — | **Yes** (customer pays licence from SEK 189/mo) | AI assistant rolling out 2026; **Weavio MCP in marketplace, SEK 249/mo** |
| **Bokio** | SE | **Yes — via UC credit bureau**, not the register | — | — | Not found | — |
| **Procountor** | FI | **Yes** — YTJ button; **plus duplicate check on business ID** | — | In-product | Yes | — |
| **Xero** | Global | Companies House lookup **not found** | **No** — guide sends users to GOV.UK / VIES | Xero Tax filing (UK) | Yes | **Anthropic partnership; Claude live 2026-05-12; MIT MCP server, 359★** |
| **QuickBooks / Intuit** | Global | Unverified | Unverified | In-product | Yes | **Anthropic partnership 2026-02-24; MCP for 4 products; Claude Agent SDK** |
| **Sage** | Global | Unverified | Sage Copilot VAT assistant (MTD) | MTD in-product | Yes | **Sage Intacct MCP Server — read-only**; Sage Copilot |
| **FreeAgent** | UK | Unverified | Unverified | Yes (UK filing) | Yes | 3rd-party MCP (Composio) |
| **Dext** | UK | Creates supplier records from documents | — | — | Yes | "Supplier verification" = KYC on **own** customer |
| **Pleo** | EU/Nordics | — | — | — | Yes | **5 agents + Pleo MCP, beta Jul 2026** |
| **Payhawk** | EU | — | — | — | Yes | **Financial Controller Agent (Cloudflare-verified), Mar 2026** |
| **Spendesk** | EU | — | — | — | Yes | **Spendesk MCP (Jun 2026)** |
| **Ramp** | US | — | — | — | Yes | **Ramp MCP (read+write); AP & procurement agents** |
| **Bill.com** | US | Vendor master: legal name, tax ID, W-9/W-8 | US TIN/W-form matching | — | Yes | — |
| **Tipalti** | Global | Supplier Hub | **Yes — automatic VIES check on EU VAT numbers** | — | Yes | — |
| **Coupa / SAP Ariba / Oracle** | Global | **Yes — via D&B D-U-N-S**, not national registers | Via bureau data | — | Yes | — |
| **Vic.ai** | US/Global | Vendor portal | No — Plaid **bank** verification + behavioural fraud signals | — | Yes | VicAgents (Q2 2026) |
| **Basis / Numeric / Rillet / Puzzle / Digits / Truewind / Klarity** | US | **Not found** | **Not found** | — | Varies | Agents, but **no public MCP server found** |

---

## The three most promising targets

**1. Pleo** — Copenhagen; ~40,000 businesses; shipped an MCP server and an **AP Agent that ingests supplier invoices from email** (beta July 2026). Its markets (DK, NO, SE, FI, UK, DE, ES) overlap registry-mcp's live and planned countries almost exactly. The AP Agent's ingestion step is the precise moment a fictitious or dissolved supplier enters the books, and Pleo has nothing to check it with. A `lookup_company` call on the CVR/orgnr is a small addition to their toolset and something no competitor gives them free. Nordic, agent-native, right size, right moment.

**2. Tripletex** — the most-used system among Norwegian regnskapsførere, a well-documented public OpenAPI with a free self-serve test environment, and a registry lookup that stops at autofill with **no documented VAT or status control**. The gap is specific, the buyer is regulated (Finanstilsynet's one-month rule, file 08), and the integration is a single tool the agency market already understands. Start with the API, not the boardroom: build the reference integration, then show it to them.

**3. The accounting-MCP builders, not the accounting vendors** — Weavio (Fortnox marketplace, SEK 249/mo), Proviscale (Visma eAccounting MCP), and the aggregators (Apideck, Composio, Zapier). Each of them needs a company-registry tool and none will build one; the Fortnox listing proves the shelf exists, has a price on it, and accepts third-party MCP servers. This is the cheapest distribution in the folder and the only one that does not require a partnership conversation.

*Runner-up:* the AI-native cohort (Basis — $100M at $1.15bn, Feb 2026; Vic.ai; Numeric). Technically fast, agent-native, and missing exactly one thing. Watch for the first to publish an MCP server.

---

## What an accounting agent needs that registry-mcp lacks (full detail: file 13)

1. **Peppol/EHF capability lookup.** Fiken shows an "EHF" badge next to customers who can receive e-invoices; PowerOffice sends users to the community site **peppol.helger.com** to type `0192:<orgnr>` by hand. It is a free public lookup on the identifier registry-mcp already takes, and no MCP server does it. **Highest-value addition.**
2. **Batch lookup and a change/delta feed.** Every real workflow is plural — an agency onboarding clients, generate.TAX's daily re-validation of every stored VAT number, Fiken re-checking at every purchase. Five singular tools do not fit.
3. **Fuzzy name → canonical entity resolution** for vendor-master de-duplication. Procountor's duplicate check on business ID is the most-used control in this folder; `search_company` + `previous_names` are the raw materials.
4. **Roles / signature rights (signaturrett, prokura).** Banks refuse signatures the register does not support; `PowerLaunch/apier-mcp` leads with it. Gated on a personal-data decision.
5. **Beneficial owners — gated, not open.** brreg's own docs: *"Alle endepunktene i APIet med unntak av Kodelister er tilgangsstyrt"*, Maskinporten scope per actor type. Design as bring-your-own-credentials (the `COMPANIES_HOUSE_API_KEY` precedent) or defer.
6. **An explicit "what this does not answer" section** — bank-account ownership, sanctions, creditworthiness, and whether the human is authorised (ID-porten/Altinn) all live elsewhere.

---

## What this means for registry-mcp

Stop selling the function and start selling the **surface, the provenance and the plurality**. Fiken, e-conomic, Fortnox, Procountor and PowerOffice all do the registry lookup already; what none of them produces is a machine-readable answer carrying `source_url`, `license`, `fetched_at` and `applies_because` that an agent can paste into a working paper — which is exactly what Finanstilsynet's *notoritet* requirement asks for, and what a 24-hour cache satisfies thirty times over.

Lead with **compliance, not fraud**. The Skatteklagenemnda case (kr 691,100 + kr 138,220) and Rundskriv 15/2019 are decided, citable and unrebuttable. Invoice-fraud statistics are at record lows and describe a mechanism — payment redirection — that a registry lookup does not address; overclaiming there is the fastest way to lose an accountant.

Compete on **schema and coverage, never on the API call**. Fifteen brreg MCP repos exist and the best has 8 stars; a Xero customer wrote "if someone without any coding experience can do it, Xero can do it." The moat is one shape across countries, `null` meaning "the register does not say", errors as answers, computed deadlines with citations, and a hosted endpoint that works.

Get distribution through **someone else's agent**. Xero, Intuit, Sage, Ramp, Pleo and Spendesk all opened agent surfaces in 2026 and every one of them is inward-facing. Being the outward-facing tool in their box is worth more than being a standalone server nobody finds.

And treat **Sweden as a separate decision**, not a fourth folder: Bokio buys from UC because Bolagsverket does not give the data away.

---

## Open questions we could not answer

- **Coupa, SAP Ariba, Oracle and Tipalti publish no prices** for supplier verification or risk modules. There is no defensible per-check benchmark in this folder. Neither does generate.TAX publish pricing for its Xero VAT checker. *(Attempted: coupa.com, capterra.com, gartner.com Peer Insights, tipalti.com, apps.xero.com, generate.tax.)*
- **Does Visma eAccounting's "Søk etter firma" hit Enhetsregisteret directly, or a Visma/Bisnode data service?** `help.visma.net` failed to resolve from this environment (DNS, then HTTP 000 via curl). Unresolved.
- **QuickBooks UK, Sage Accounting and FreeAgent** — is there a Companies House counterparty lookup on contact creation? Unverified; the session's web-search budget (200/200) was exhausted before the confirming searches ran.
- **Reddit, and GitHub issues on the accounting MCP repos** — the purest demand statements, and not swept. `site:reddit.com r/Accounting r/bookkeeping r/Xero`, plus issues on `XeroAPI/xero-mcp-server` and `Proviscale/visma-mcp-server`, are the highest-value cheap follow-ups.
- **Nordic-language community forums** (Visma Community, Tripletex, Fortnox, e-conomic) for "hente fra Brønnøysund" / "kontrollere mva-registrert" / "hämta uppgifter Bolagsverket" — not searched.
- **Uni Micro** — no public developer portal found; API status unknown.
- **ICAEW article bodies are JavaScript-rendered** and did not retrieve via WebFetch or curl; the "know your supplier / verify trading history, check company records" guidance is quoted from search-index extracts and should be re-verified in a browser before public use.
- **Økokrim, Finanstilsynet and Finans Norge publish no fakturasvindel-specific loss figure for Norway.** Only UK Finance breaks invoice & mandate out. If a Norwegian number is needed, it does not currently exist in public statistics.
- **What Fortnox pays Bolagsverket**, and whether a free-tier Swedish module is licensable at all, is unknown and blocks any `SE` scoping.
