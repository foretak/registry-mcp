# 01 — Market and buyers: who pays for company-registry data, how much, and for what

Thirteen source files. Everything below carries a URL and a date. Fetched 2026-09-05.

---

## Key findings

**1. The incumbent wholesale price of a company lookup is 16–20 pence, published.**
Dun & Bradstreet's G-Cloud 14 filing states *"Cleanse and match £0.16p record"* with a 12-month
minimum and *"up to 6% per annum"* escalation
([D&B pricing doc, March 2024](https://assets.applytosupply.digitalmarketplace.service.gov.uk/g-cloud-14/documents/93073/755551008932552-pricing-document-2024-05-03-1057.pdf)).
Creditsafe's is starker — *"License fee: £500 … Transactional Cost: **£0.20** for Freedom UK &
Ireland Company Credit Reports"*
([Creditsafe G-Cloud doc](https://assets.applytosupply.digitalmarketplace.service.gov.uk/g-cloud-14/documents/717735/547521322603115-pricing-document-2025-08-27-1504.pdf)).
Twenty pence buys a *full credit report*, not a register record. **Per-lookup pricing is a lost
war.** (Files 03, 04)

**2. There is a published, empty price band between free and £15,150/year.**
Moody's/kompany — the incumbent closest in shape to registry-mcp — publishes its whole API
ladder: **£15,150 / £30,300 / £50,500 / £101,000 / £151,500 a year**, 12-month minimum, no
self-serve tier
([kompany G-Cloud pricing](https://assets.applytosupply.digitalmarketplace.service.gov.uk/g-cloud-14/documents/720211/190003313465057-pricing-document-2024-05-02-1253.pdf)).
Below that: free registers. Between: nothing. **That gap is the market, and it is defined by a
published price rather than a guess.** (File 05)

**3. Moody's contractually forbids the use its data is now most wanted for.**
Its filed terms state the client will not *"use the Information in connection with artificial
intelligence technologies or tools or machine learning language models to generate any data or
content"*
([kompany T&Cs](https://assets.applytosupply.digitalmarketplace.service.gov.uk/g-cloud-14/documents/720211/190003313465057-terms-and-conditions-2024-05-07-1128.pdf)).
registry-mcp's upstreams — **NLOD 2.0** and **Crown copyright, free to re-use** — carry no such
restriction, and the README already ships `license` in every response. This is a real, checkable
legal advantage. (File 05)

**4. The Nordic incumbent has already shipped an MCP server.**
**Proff Premium MCP** — *"bedriftsdata fra Proff til dine AI-agenter"* — covers Norway, Sweden,
Denmark and Finland with financials, roles, ownership and beneficial owners
([forvalt.no/ProffAPI/MCP](https://forvalt.no/ProffAPI/MCP)). It is quote-only, subscription-gated
(NOK 12,490–24,990/year) and has no free tier or self-serve signup. `NAMES.md` did not find this.
**registry-mcp is not first in Norway; it is the only self-serve option.** (File 09)

**5. The closest comparable business meters exports, not lookups.**
Endole sells UK company data built on the free register for **£39/month, or £25/month billed
annually** — with *"Unlimited Know Your Business (KYB) checks"* and a metered
*"Export allowance: 1,000 rows/month or 15,000 rows/year"*
([endole.co.uk/pricing](https://www.endole.co.uk/pricing/)). Queries are free; bulk extraction is
the paywall. (File 12)

**6. Demand is enormous and mostly unpriced.**
Companies House reports *"Number of times the register was accessed: **16.3 billion**"* in
2024-25 against **5,479,045** companies on the register
([annual report](https://www.gov.uk/government/publications/companies-house-annual-report-and-accounts-2024-to-2025/companies-house-annual-report-and-accounts-2024-to-2025);
[FYE 2026 statistics](https://www.gov.uk/government/statistics/companies-register-activities-statistical-release-april-2025-to-march-2026/companies-register-activities-statistical-release-april-2025-to-march-2026)).
Norway's Enhetsregisteret returns **1,173,016** entities, of which **409,507** are VAT-registered
(live API read, 2026-09-05). Access is free in both. (Files 08, 13)

**7. But the people hitting the free ceiling ask for more free capacity, not a paid tier.**
On the Companies House developer forum, July 2026: *"I run read-only batch jobs against the API
for some internal compliance work, and I'm hitting the 600 requests per 5 minutes limit as my
list grows"* and *"Please increase default rate limit for all instead of increasing for specific
consumer"* ([thread 12886](https://forum.companieshouse.gov.uk/t/increase-rate-limiting/12886)).
Anecdotes — but they are the clearest demand signal found, and **none of them offers to pay.**
This is the folder's most important negative finding. (File 12)

**8. Market-size reports disagree by 34×; use bottom-up instead.**
Published KYB estimates for overlapping periods run from **US$366.0M (2024) → US$741.6M (2030),
12.5% CAGR** (Market Glass via Research and Markets, Aug 2026) to **$12.4bn (2025)**
(Business Research Insights). Against that, three companies publish audited revenue totalling
**~$2.9bn**: D&B **$2,381.7m** FY2024, Creditsafe **€289m** FY2024, Enento **€150.4m** FY2024.
D&B was taken private at **$7.7bn EV** — only ~3.2× revenue. (File 11)

**9. The price of the *job* spans four orders of magnitude.**
£0 (register) → £0.16 (D&B match) → £0.20 (Creditsafe report) → £0.20–0.375 (OpenCorporates
call) → $2.00 (Didit KYB) → $12.95 (Experian BizVerify) → NOK 990 (Proff Firmarapport) →
$1,500–3,000 (a bank's full KYC review, Fenergo survey). The spread is explained by **channel and
bundle**, never by data cost. (Files 06, 07, 10, 02)

**10. The cost of a wrong answer is concentrated in accounts payable, not compliance.**
The FBI's IC3 puts BEC at *"Domestic and international exposed dollar loss: $55,499,915,582"*
across 305,033 incidents to end-2023 ([IC3 PSA, 11 Sep 2024](https://www.ic3.gov/PSA/2024/PSA240911)) —
the classic vector being a supplier invoice with changed details. AML/KYC regulatory penalties,
by contrast, are **falling**: $6.6bn (2023) → $4.6bn (2024) → **$3.8bn (2025)**
([Fenergo, Jan 2026](https://resources.fenergo.com/newsroom/global-financial-regulatory-penalties-fall-by-18-in-2025-as-enforcement-shifts-from-us-to-emea-and-apac)).
(File 02)

---

## What this means for registry-mcp

**Sell throughput, shape and exports — never lookups.** The lookup is worth £0.16–0.20 wholesale
and is given away free by the registers and by Didit ("Key People Extraction — Free"). Endole's
tested answer is the one to copy: unlimited queries, metered bulk.

**Recommended pricing hypothesis**

| Tier | Price | Meter | Evidence |
|---|---|---|---|
| **Local MCP (stdio)** | Free forever | — | Build plan §5.2 already commits to this; costs nothing |
| **Hosted Free** | £0 | 1,000 lookups/day, 100 monitored companies, no export | Must beat CH's 600/5min ([forum evidence](https://forum.companieshouse.gov.uk/t/increase-rate-limiting/12886)) or there is no reason to switch |
| **Starter** | **£29/month** | 50k lookups/mo, 2,500 monitored, 5k rows/mo export | Sits just above Endole's £25 and 8× below OpenCorporates' £225 entry |
| **Team** | **£99/month** | 500k lookups, 25k monitored, 50k rows, batch endpoints, SLA | Fills the empty band; still 1/12th of OpenCorporates Basic (£1,200/mo) |
| **Enterprise** | **from £6,000/year** | Bulk delivery, custom limits, invoice, DPA | Deliberately half OpenCorporates Basic (£12,000/yr) and well under Moody's £15,150 floor |

Anchor the pitch on **licence and shape**, not price: NLOD 2.0 and Crown copyright impose no
share-alike (unlike OpenCorporates) and no AI prohibition (unlike Moody's). Target **accounts
payable and Norwegian VAT verification** first — the best-fit jobs — with `company_deadlines` as
the hook, since no priced competitor for it was found anywhere in this research.

Two cautions. Proff is already in the MCP channel, so the self-serve advantage is perishable.
And the build plan's Phase 5.3 target of *"10–30k NOK/month"* from one Norwegian customer is
roughly **12–30× Proff's entire annual seat price** — it needs re-examination before it is used
as a goal.

---

## Open questions we could not answer

1. **Would anyone actually pay?** Every demand signal found asks for *more free capacity*.
   No neutral case study of an organisation switching from an incumbent to open data was found —
   only vendor-written comparisons. Build plan Phase 4.2 (ask clients with >100 calls what
   they'd pay) remains the only way to settle this.
2. **What does Proff Premium MCP cost, and what are its limits?** Quote-only. A sales enquiry
   would answer it; this is the highest-value single unknown.
3. **Enin and Bizzy pricing** — both sites are JavaScript-rendered; `/priser` 404s on Bizzy.
   Not found. These are the closest Norwegian price comparators.
4. **D&B's per-record data-block price table** — page 5 of its G-Cloud PDF is a raster image.
   Only the £0.16 cleanse-and-match rate was recoverable.
5. **brreg API call volumes** — not published anywhere located. Companies House publishes
   "16.3 billion accesses" but does not define the metric or break out API calls.
6. **Sweden's exact register size** and **a directly-read Danish figure** — both blocked by
   JavaScript-rendered official pages. Denmark's ~420,000–460,000 is medium confidence; Sweden's
   "over one million" is low.
7. **Alloy's pricing** — no published figure found at any confidence level.
8. **Whether Moody's AI clause is enforced or routinely waived on Order Forms.** The default is
   a prohibition; actual practice is unknown and unverifiable from outside.
9. **The real addressable market for registry-mcp specifically.** Deliberately not estimated —
   see file 11 on why the available top-down numbers cannot support one.

---

## Files

| # | File | Subject |
|---|---|---|
| 01 | `01-buyer-segments-and-their-jobs.md` | The seven segments, their jobs, and which fit |
| 02 | `02-cost-of-a-wrong-answer.md` | AML fines, BEC losses, manual-review cost |
| 03 | `03-dun-and-bradstreet-published-pricing.md` | G-Cloud prices, £0.16/record, revenue, Bisnode |
| 04 | `04-creditsafe-published-pricing.md` | £500 + £0.20/report; €289m revenue |
| 05 | `05-moodys-kompany-pricing-and-the-ai-clause.md` | Full API ladder £15,150–£151,500; the AI prohibition |
| 06 | `06-experian-and-bvd-orbis-prices.md` | Retail per-report prices; the Jisc/Orbis contract |
| 07 | `07-opencorporates-pricing-and-licence.md` | £2,250–£12,000/yr; ODbL share-alike |
| 08 | `08-the-free-sources-and-what-they-cost-you-anyway.md` | CH, brreg, GLEIF — free, and their frictions |
| 09 | `09-nordic-resellers-proff-enento-and-the-incumbent-mcp.md` | Proff's price list and Proff Premium MCP |
| 10 | `10-kyb-api-vendors-and-the-price-collapse.md` | Didit, Middesk, Persona, Trulioo; the price ladder |
| 11 | `11-market-sizing-and-how-much-to-believe-it.md` | The 34× disagreement; bottom-up build |
| 12 | `12-willingness-to-pay-signals.md` | Endole, forum anecdotes, the self-serve band |
| 13 | `13-register-scale-norway-uk-denmark-sweden.md` | Company counts, query volumes, resellers |
