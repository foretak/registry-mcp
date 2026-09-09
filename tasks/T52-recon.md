# T52-recon — Britain's and Sweden's financial figures, out of the filed accounts themselves

Owner: Opus (T52), dispatched by the orchestrator 2026-09-09. Brief: `tasks/T52.md`. Everything below was
obtained on **2026-09-09** (UTC) unless dated otherwise. Rules it answers: **D-043(i)**'s "Sweden and Britain
will not [fill this block], and the reason is ours, not theirs" — which this recon finds is **half right for
Sweden and wrong for Britain**, for a register reason D-041(g) never weighed.

Tags: **[fetched]** read off the wire in this session · **[search]** from a search result or a secondary page
· **[repo]** read in this repository. Every URL is in the last section.

**Live-call budget, declared before anything else.** The brief bounds "at most **three** Companies House
Document API fetches" and "at most **three** Bolagsverket zips". Question 4 of the same brief models the
British path as *"filing history → document metadata → document"* — three distinct request kinds — so the
bound was read as **three fetches of document *content***, and that is exactly what was spent. The full
count, so nobody has to trust the reading:

| Endpoint | Requests | Notes |
|---|---|---|
| CH Public Data API `/company/{n}/filing-history` and `/company/{n}` | **8** | 600/5 min budget; peak `x-ratelimit-remain` seen 598 |
| CH Document API `GET /document/{id}` (metadata, JSON, ≤ 621 bytes each) | **9** | its own separate 600/5 min budget — see Fact 4 |
| **CH Document API `GET /document/{id}/content`** | **3** | **the bound.** 24,994 + 86,703 + 26,158 bytes |
| Bolagsverket `POST /oauth2/token` | **1** | |
| Bolagsverket `POST /dokumentlista` | **1** | 1,004 bytes |
| **Bolagsverket `GET /dokument/{id}`** | **3** | **the bound.** 47,497 + 44,909 + 45,258 bytes of zip |

No call to `api.foretak.dev`. `833286602` / `833285602` never queried. Both keys were read from
`~/secrets/registry-mcp/` inside the fetching script, never echoed, never written to a file, never committed.
**No downloaded document was written to disk**: all six were held in `/dev/shm` (tmpfs) for the parse and
deleted at the end of the session — all six carry officer/signatory name concepts, and the brief forbids saving those.

Six documents were sampled. **Three British**, all iXBRL XHTML from the Document API; **three Swedish**, all
iXBRL XHTML inside `/dokument` zips, one company across three taxonomy versions.

---

## Fact 1 — what is actually inside

### Britain: FRC taxonomies, one entry-point schema per document, and the prefix is not stable

All three British documents are **inline XBRL in XHTML** (`application/xhtml+xml`), self-contained, no
sidecar instance and no PDF in the payload. [fetched] The taxonomy is the **FRC (Financial Reporting
Council) UK/Irish digital reporting suite**, declared by a `link:schemaRef`:

| Doc | Company / accounts type | `schemaRef` | Bytes | `ix:nonFraction` | `ix:nonNumeric` |
|---|---|---|---|---|---|
| **A** | `04374209`, micro-entity (filed 2024-08-20, FY 2023-03-31) | `xbrl.frc.org.uk/FRS-102/2023-01-01/…` | 24,994 | 24 | 19 |
| **B** | `13507518`, total-exemption-full (filed 2023-04-13, FY 2022-07-31) | `xbrl.frc.org.uk/FRS-102/2019-01-01/…` | 86,703 | 36 | 44 |
| **C** | `13948759`, micro-entity (filed 2026-04-23, FY 2026-03-31) | `xbrl.frc.org.uk/FRS-102/2023-01-01/…` | 26,158 | 24 | 19 |

⚠ **The namespace prefix for the FRC core taxonomy changes between versions.** The 2023-01-01 documents bind
`uk-core` → `http://xbrl.frc.org.uk/fr/2023-01-01/core` and `uk-direp` → `…/reports/2023-01-01/direp`; the
2019-01-01 document binds the *same concepts* under `core` and `direp`. [fetched] Two of three sampled
documents would be missed by a parser matching the QName string `core:TurnoverRevenue`. Match on the local
name (or the namespace URI), never on the prefix.

**Which D-043(c) figures each document carries, concept by concept** (undimensioned, current period):

| D-043(c) field | A (micro) | B (small, full) | C (micro) |
|---|---|---|---|
| `revenue` | — | `core:TurnoverRevenue` 321,491 | — |
| `operating_costs` | — | `core:AdministrativeExpenses` 88,979 (+ `CostSales` 248,545) | — |
| `operating_result` | — | `core:OperatingProfitLoss` 28,273 | — |
| `financial_income` / `financial_costs` / `net_financial_items` | — | — | — |
| `profit_before_tax` | — | `core:ProfitLossOnOrdinaryActivitiesBeforeTax` 28,273 | — |
| `profit_for_period` | — | **`core:ProfitLossOnOrdinaryActivitiesAfterTax`** 22,990 — *not* `core:ProfitLoss` | — |
| `total_comprehensive_income` | — | — | — |
| `fixed_assets` | `uk-core:FixedAssets` 0 | `core:FixedAssets` 345 | `uk-core:FixedAssets` 500 |
| `current_assets` | `uk-core:CurrentAssets` 6,210 | `core:CurrentAssets` 56,642 | `uk-core:CurrentAssets` 0 |
| **`total_assets`** | **—** | **—** | **—** |
| `paid_in_equity` | — | — | — |
| `retained_equity` | — | `core:Equity[EquityClassesDimension=RetainedEarningsAccumulatedLosses]` | — |
| `equity` | `uk-core:Equity` 17,549 | `core:Equity` 22,990 | `uk-core:Equity` 500 |
| `non_current_liabilities` | `uk-core:Creditors[AfterOneYear]` 0 | — | `uk-core:Creditors[AfterOneYear]` 0 |
| `current_liabilities` | `uk-core:Creditors[WithinOneYear]` 23,759 | `core:Creditors[WithinOneYear]` 33,997 | `uk-core:Creditors[WithinOneYear]` 0 |
| **`liabilities`** | **—** | **—** | **—** |
| **`total_equity_and_liabilities`** | **—** | **—** | **—** |
| **filled** | **5 / 19** | **8 / 19** | **5 / 19** |

Three structural facts hide inside that table, and each is a design constraint rather than a gap:

1. **A micro-entity iXBRL has no income statement at all.** Documents A and C carry **zero** profit-and-loss
   facts — no turnover, no operating result, no profit. Only a balance sheet, an employee count, and the
   audit-exemption statements. [fetched] That is the law, not the filer: a micro-entity need not deliver its
   profit and loss account to the registrar. So the D-043 answer to *"is this supplier solvent"* for the
   commonest British company is a balance sheet and nothing else.
2. **`total_assets`, `liabilities` and `total_equity_and_liabilities` do not exist as tagged facts** in any of
   the three. A UK balance sheet under FRS 102/105 is presented in *net-assets* form — fixed + current −
   creditors-within-one-year = `TotalAssetsLessCurrentLiabilities`, then − creditors-after-one-year −
   provisions = `NetAssetsLiabilities` = `Equity`. There is no "total assets" line and no "total liabilities"
   line to tag. Producing them means **adding two numbers**, which **D-043(e) forbids outright** ("No
   arithmetic produces a figure"). The single most-used solvency number is therefore `None` for Britain, by
   our own rule, on every filing sampled. 0 of 3.
3. **The current and non-current liability split is only reachable through a dimension.** `core:Creditors` is
   *always* dimensioned, on `uk-core:MaturitiesOrExpirationPeriodsDimension` with members `WithinOneYear` /
   `AfterOneYear`. [fetched] A parser that reads only undimensioned facts — the safe default, and the one this
   recon's prototype started with — returns `None` for both. A parser that reads `Creditors` blind sums a
   balance-sheet line with a note disclosure. B carries `Creditors[WithinOneYear] = 33,997` **twice**, once on
   the face and once in the note.

**The metadata D-043's flags would need is carried by the context dimension, not by the fact.** `uk-bus:AccountingStandardsApplied`, `uk-bus:AccountsType` and `uk-bus:AccountsStatusAuditedOrUnaudited` are all
`ix:nonNumeric` elements with **empty content**; the value is the explicit dimension member on their context.
[fetched] Observed: `AccountingStandardsDimension = uk-bus:Micro-entities` (A, C) and `= uk-bus:FRS102` (B);
`AccountsTypeDimension = uk-bus:FullAccounts` (all three); `AccountsStatusDimension =
uk-bus:AuditExempt-NoAccountantsReport` (all three); `LegalFormEntityDimension = uk-bus:CompanyLimitedByGuarantee`
(B). So `accounting_framework`, `scope` and `audit_exempt` are readable **as QNames off a context, without
reading a single character of fact text** — which Fact 5 turns into the person-bearing guarantee.

### Sweden: one K2 taxonomy, no dimensions at all, and every total present

All three Swedish zips contain **exactly one file** — an iXBRL XHTML, nothing else. [fetched] Not the
iXBRL + XBRL + PDF triple that Bolagsverket's *submission* documentation describes [search]; the
värdefulla-datamängder endpoint serves the single original inline document.

| Doc | Period | Zip → XHTML | `schemaRef` (entry point) | `ix:nonFraction` | `ix:nonNumeric` |
|---|---|---|---|---|---|
| **SE-2020** | 2020-12-31 (filed 2021-07-30) | 45,258 → 126,846 | `se-k2-risbs-2017-09-30.xsd` | 95 | 35 |
| **SE-2022** | 2022-12-31 (filed 2023-06-27) | 44,909 → 122,630 | `se-k2-risbs-2017-09-30.xsd` | 79 | 38 |
| **SE-2025** | 2025-12-31 (filed 2026-06-30) | 47,497 → 157,013 | `se-k2-risbs-2021-10-31.xsd` | 88 | 37 |

All three are `5561890038` — the company the brief names, which `/dokumentlista` reports has six annual
reports live (2020-12-31 … 2025-12-31, one per year). [fetched]

| D-043(c) field | concept (identical in all three documents) | SE-2020 | SE-2022 | SE-2025 |
|---|---|---|---|---|
| `revenue` | `se-gen-base:Nettoomsattning` | 0 | 0 | 0 |
| `operating_costs` | `se-gen-base:Rorelsekostnader` | 43,649 | 28,803 | 4,656 |
| `operating_result` | `se-gen-base:Rorelseresultat` | −43,649 | −28,803 | −4,656 |
| `financial_income` | `se-gen-base:OvrigaRanteintakterLiknandeResultatposter` | 0 | 4,141 | 176 |
| `financial_costs` | `se-gen-base:RantekostnaderLiknandeResultatposter` | 6,848 | 573 | 6,056 |
| `net_financial_items` | `se-gen-base:FinansiellaPoster` | −6,848 | 3,568 | −5,880 |
| `profit_before_tax` | `se-gen-base:ResultatForeSkatt` | −50,497 | −25,235 | −10,536 |
| `profit_for_period` | `se-gen-base:AretsResultat` | −50,497 | −25,235 | −10,536 |
| `total_comprehensive_income` | *(no K2 concept)* | — | — | — |
| `fixed_assets` | `se-gen-base:Anlaggningstillgangar` | — | — | — *(company has none)* |
| `current_assets` | `se-gen-base:Omsattningstillgangar` | 992,027 | 928,627 | 515,409 |
| **`total_assets`** | **`se-gen-base:Tillgangar`** | **992,027** | **928,627** | **515,409** |
| `paid_in_equity` | `se-gen-base:BundetEgetKapital` | 522,400 | 522,400 | 522,400 |
| `retained_equity` | `se-gen-base:FrittEgetKapital` | −697,121 | −740,747 | −13,991 |
| `equity` | `se-gen-base:EgetKapital` | −174,721 | −218,347 | 508,409 |
| `non_current_liabilities` | `se-gen-base:LangfristigaSkulder` | 935,948 | 935,948 | — *(none this year)* |
| `current_liabilities` | `se-gen-base:KortfristigaSkulder` | 230,800 | 211,026 | 7,000 |
| `liabilities` | *(no "summa skulder" line in the ÅRL balance-sheet format)* | — | — | — |
| **`total_equity_and_liabilities`** | **`se-gen-base:EgetKapitalSkulder`** | **992,027** | **928,627** | **515,409** |
| **filled** | | **16 / 19** | **16 / 19** | **15 / 19** |

**Not one Swedish context carries a dimension.** Zero explicit or typed members across all three documents.
[fetched] Every figure above is an undimensioned fact under a single period. That is the whole difference in
parsing difficulty between the two registers, in one sentence.

⚠ **Stability is split, and the split is favourable.** Across a 2017-09-30 taxonomy and a 2021-10-31 taxonomy
five years apart, **every financial concept name above is byte-identical**. What drifted is the surrounding
*metadata*: `se-cd-base:Redovisningsvaluta` → `se-cd-base:RedovisningsvalutaHandlingList`,
`se-cd-base:Beloppsformat` → `se-cd-base:BeloppsformatList`, `se-cd-base:Sprak` → `…SprakHandlingUpprattadList`,
`se-cd-base:Land` → `…LandForetagetsSateList`, `se-gen-base:Redovisningsprinciper` →
`se-gen-base:RedovisningsVarderingsprinciper`, and the signature concepts renamed wholesale (Fact 5). Their
*values* changed representation too: `Redovisningsvaluta` was the string `"SEK"` in 2020 and 2022 and is the
enum member `se-mem-base:ValutaSvenskaKronorMember` in 2025. [fetched] **This bites D-043(d) directly** —
`currency` is a required field with no default, so a parser keyed on `se-cd-base:Redovisningsvaluta` builds
nothing at all on the current taxonomy. The safe source is the unit: every monetary fact carries
`unitRef="SEK"` → `xbrli:measure` → `iso4217:SEK`, and that is version-independent in both countries (GB: all
24/36/24 monetary facts `iso4217:GBP`).

---

## Fact 2 — which companies have a machine-readable document at all

### Britain: the register says 75%, and the 25% is the end of the market that matters

**Companies House's own statement**, verbatim from the Accounts Data Product download page: [fetched]

> "The Accounts Data Product is a free downloadable ZIP file, which contains the individual data files
> (instance documents) of company accounts **filed electronically**."

> "**Data is only available for electronically filed accounts, which currently stands at about 75% of the
> 2.2 million accounts we expect to be filed each year.**"

And from Companies House's own FAQ for the same product: [fetched]

> "Approximately **97% of the individual data files will be in iXBRL** (inline eXtensible Business Reporting
> Language) format (HTML file). The remaining 3% will be in XBRL format (XML file)."

So ~75% × ~97% ≈ **73% of British accounts filings are iXBRL today**, and ~25% are not machine-readable at
all. **The missing quarter is not random.** Measured on the wire, per accounts filing:

| Company | Accounts filings inspected | `paper_filed` | Document API `resources` |
|---|---|---|---|
| `00445790` **Tesco PLC** (the brief's own pick) | **25 of 25**, back to 2003 | `true` on **25/25** | latest: **`application/pdf` only**, 14,316,485 bytes, 236 pages |
| `SC090312` **NatWest Markets PLC** (the brief's own pick) | **25 of 25**, back to 2004 | `true` on **25/25** | latest: **`application/pdf` only**, 10,251,352 bytes, 171 pages |
| `09446231` Monzo Bank Ltd | 3 most recent | `true` on 3/3 | latest: **`application/pdf` only**, 7,190,321 bytes |
| `OC303675` Deloitte LLP | 3 most recent | `true` on 3/3 | latest: **`application/pdf` only**, 4,454,597 bytes |
| `13507518` small CIC, 2026 abridged | 1 | `true` | **`application/pdf` only**, 300,852 bytes |
| `13507518` small CIC, 2023 total-exemption-full | 1 | absent | pdf **and `application/xhtml+xml`**, 86,703 bytes |
| `04374209` micro-entity, 2024 | 1 | absent | pdf **and `application/xhtml+xml`**, 24,994 bytes |
| `13948759` micro-entity, 2026 | 1 | absent | pdf **and `application/xhtml+xml`**, 26,158 bytes |

[fetched] **Both companies the brief named for Britain filed on paper on every one of their last 25 accounts
filings, and the most recent of each is PDF-only in the Document API.** So did the bank and the LLP. (The
`paper_filed` flag was read for all 25 filings each; the `resources` map was read for the most recent of each.) The correlation between `filing_history.paper_filed` and the absence of
`application/xhtml+xml` is **8 of 8** — which makes `paper_filed` a free pre-check that costs no Document API
request, and makes the shape of the gap unmistakable: **iXBRL at Companies House is a small-company format.**
The large filers upload a rendered PDF of the annual report their designers laid out, and Companies House
stores exactly that.

**The mandate exists and it is not 2027.** Companies House's own campaign site, verbatim: [fetched]

> "Changes to accounts filing will be introduced in **April 2028**, giving companies 21 months to prepare."

> "all accounts filings made on or after **1 April 2028** must be filed by commercial software in inline
> extensible Business Reporting Language (iXBRL) format."

> "From this date, our web and paper routes will be closed for accounts filings but will remain open for other
> statutory filings."

Secondary sources still say 1 April 2027 [search]; the register says 2028. **And the same page removes most of
what the mandate would have given us**, which is the sentence to weigh hardest: [fetched]

> "Small and micro entity companies will need to file a profit and loss as part of their annual accounts, as
> other companies do, but **will be provided with the option to opt out of having these profit and loss
> accounts published on the public register**."

So after April 2028 the population that *has* iXBRL is exactly the population entitled to keep its revenue and
profit off the public record. Also: *"small companies will also no longer be able to prepare and file 'abridged'
accounts."*

There is a **bulk alternative** for Britain and it should be named so it is a decision and not a gap: the free
Accounts Data Product — daily zips, Tuesday–Saturday, **60 days'** retention, 50–350 MB each (2026 range
observed on the index page), individual files named by company number and balance-sheet date. [fetched] It is
D-045(h)'s Kunngjøringer problem in a second country: *"a pipeline and a database, not a proxy."*

### Sweden: the digital channel is aktiebolag-on-K2-or-K3, and it starts in 2020

Bolagsverket's own API page, quoted through a search result because `bolagsverket.se` refuses this machine
(see *What I could not establish*): [search]

> "I de värdefulla datamängderna ingår dokument i form av digitalt inlämnade årsredovisningar. **Datat avser
> digitalt inkomna årsredovisningar från 2020 och framåt.** Du kan hämta årsredovisningar som är digitalt
> inlämnade i **iXBRL** format från och med 2020 då de första årsredovisningarna lämnades in i det formatet."

> "Digital inlämning av årsredovisning fungerar för **aktiebolag som redovisar enligt K2 eller K3**." The
> e-service opened in **spring 2018** for K2 and on **9 February 2019** for K3. "Bolagsverket tar i nuläget
> inte emot årsredovisningar digitalt från **handelsbolag, ekonomiska föreningar eller
> bostadsrättsföreningar**", and financial companies, insurers and **IFRS** preparers are outside it. [search]

**This closes the T44 addendum's open question.** T44 found `5560160680` (Ericsson — listed, IFRS) returns a
present `filings` block with `documents: []` while `5561890038` returns six. `[repo]` The mechanism is not a
paper-versus-digital accident: **an IFRS preparer cannot use the channel at all.** The `_SCOPE_NOTE` /
`_EMPTY_NOTE` in `registries/se/filings.py` can now say *which* annual reports the list carries — digitally
submitted aktiebolag annual reports under K2 or K3, from 2020 — instead of "may omit companies that do not
file digitally".

Two independent **[fetched]** corroborations from this session: `5561890038`'s six documents run exactly
2020-12-31 … 2025-12-31 and stop, on a company registered long before; and all three sampled documents declare
a **`k2`** entry point in their `schemaRef` path.

**Sweden's mandate is a bill, not a fact.** A Justitiedepartementet proposal would make digital submission
compulsory for K2/K3 aktiebolag, in force 1 January 2026 and first applying to financial years beginning after
31 December 2025 — so first bite in 2027, covering *"mer än 95 procent av samtliga bolag"*. [search] A
secondary source dated August 2026 says no final decision has been taken. [search] **Do not state this as
law.** What is on the wire is the voluntary channel and its population.

---

## Fact 3 — the parsing cost

**A ~150-line stdlib parser reads both registers. No taxonomy files, no third-party dependency, no new
runtime requirement.** The prototype (`ixparse.py`, **153 lines** including its concept map, scratch only, not
committed) uses `xml.etree.ElementTree` and `zipfile` from the standard library and does five things: read
`xbrli:context` into `{start, end, instant, dims}`; read `xbrli:unit` into an ISO-4217 code; walk every
`ix:nonFraction` applying `@format`, `@scale` and `@sign`; pick the undimensioned fact whose context matches
the latest period; map local names onto D-043(c).

| | Prototype (stdlib) | `ixbrlparse` 0.11.2 | `arelle-release` 2.44.8 |
|---|---|---|---|
| Licence | — (ours) | **MIT** [fetched] | **Apache-2.0** [fetched] |
| New runtime deps | **0** | 5 (`beautifulsoup4`, `lxml`, `click`, `pluggy`, `word2number`) | **14** (`lxml`, `numpy`, `pillow`, `openpyxl`, `bottle`, `jsonschema`, `pyparsing`, `regex`, `truststore`, …) |
| Installed size | 0 | ~14 MB (12 MB of it `lxml`) [fetched] | **24.7 MB** wheel unpacked, 751 files [fetched] |
| Taxonomy files needed | **none** | none | yes — `arelle/WebCache.py` fetches schemas over HTTP at validation time |
| Parse time per document | **0.7–4.0 ms** | 11–33 ms | not measured |

[fetched] `arelle` is the right tool for *validating* a filing and the wrong tool for reading nine numbers out
of one: it is a validation platform, it wants the taxonomy suite, and the FRC publishes a **new suite every
year** (2025 and 2026 both current as of today [fetched]) whose version an implementer would then have to
track. A taxonomy-aware engine is not needed because **nothing here requires the taxonomy**: concept identity
is the element name, period is the context, currency is the unit, and the calculation linkbase is the one
thing we must *not* use (D-043(e) forbids deriving figures).

`ixbrlparse` was run against all six documents in a throwaway venv as an independent check: **6/6 parsed, 0
errors**, and its numeric-fact counts are identical to the prototype's on every document (GB 24/36/24, SE
95/79/88). [fetched] It also exposes the `schemaRef` directly as `IXBRL.schema`, which is the cheapest route
to `accounting_framework`. It is a legitimate alternative to the prototype; it is not *needed*.

### What the prototype got right, scored against each document's own totals

Every check below is an identity the **document itself asserts** by tagging both sides.

| Document | Checks | Passed |
|---|---|---|
| A `04374209` micro | `FixedAssets+CurrentAssets−Creditors[≤1y] == TotalAssetsLessCurrentLiabilities` · `CurrentAssets−Creditors[≤1y] == NetCurrentAssetsLiabilities` · `NetAssetsLiabilities == Equity` | **1 / 3** |
| B `13507518` small-full | the two above, plus `Turnover−CostSales == GrossProfit` · `GrossProfit+OtherOperatingIncome−AdminExpenses == OperatingProfitLoss` · `OperatingProfitLoss == PBT` · `PBT−Tax == ProfitAfterTax` · `NetAssets == Equity` | **7 / 7** |
| C `13948759` micro | the three above | **3 / 3** |
| SE-2020 / SE-2022 / SE-2025 | `Tillgangar == EgetKapitalSkulder` · `EgetKapital+Langfristiga+Kortfristiga == EgetKapitalSkulder` · `Nettoomsattning−Rorelsekostnader == Rorelseresultat` · `Rorelseresultat+FinansiellaPoster == ResultatEfterFinansiellaPoster` · `…== AretsResultat` · `BundetEK+FrittEK == EgetKapital` | **6 / 6 each — 18 / 18** |
| **Total** | | **29 / 31** |

**Both failures are one company's, and they are the document's error, not the parser's.** In document A:

```
CurrentAssets = 6,210      Creditors[WithinOneYear] = 23,759      → 6,210 − 23,759 = −17,549
tagged: NetCurrentAssetsLiabilities = 17,549   TotalAssetsLessCurrentLiabilities = 17,549
        NetAssetsLiabilities = 17,549          Equity = 17,549          (all four positive)
```

The company is **net liabilities of £17,549** — it is in compulsory liquidation `[repo]` — and its filed iXBRL
tags all four subtotals as bare positives. The raw markup shows exactly why:

```html
<td class="number subtotal"><div>(<ix:nonFraction contextRef="icur1" decimals="2"
   format="ixt2:numdotdecimal" name="uk-core:NetCurrentAssetsLiabilities" unitRef="GBP"
   >17,549</ix:nonFraction><span class="endnegmark">)</span></div></td>
```

**The opening parenthesis is bare text before the tag and the closing one is a `<span>` after it. Neither is
inside the fact, and there is no `sign="-"` attribute.** A human reading the rendered accounts sees
`(17,549)`. Every XBRL-correct reader gets `+17,549`. The prior-year column of the *same element in the same
document* is a genuine `+1,782` (18,837 − 17,055) tagged with no brackets — so the same software used the
presentation bracket as the only carrier of sign, and got it right by accident one year and wrong the next.
`ixbrlparse`, an independent purpose-built library, returns the same `17,549.0`. [fetched] **This is not a
parser bug anyone can fix.**

The Swedish documents have the opposite property: every loss is tagged **negative** (`Rorelseresultat −43,649`,
`EgetKapital −218,347`), 18/18 identities close to the krona, and the sign never depends on the presentation.

---

## Fact 4 — cost per lookup, the cache, and the terms

### Requests, bytes, seconds

| | Britain | Sweden |
|---|---|---|
| Path | `GET /company/{n}/filing-history?category=accounts` → `GET /document/{id}` (metadata) → `GET /document/{id}/content` | `POST /dokumentlista` → `GET /dokument/{id}` |
| Metered requests per `financials` | **3** (of which 1 on the Public Data budget, 2 on the Document budget) | **2** (+ a token request when the token has expired) |
| Extra hop | the content call answers **302**; the `Location` is a pre-signed URL fetched **without** the `Authorization` header | none |
| Bytes down | 550–620 B metadata + **24,994 / 86,703 / 26,158 B** document | 1,004 B list + **44,909–47,497 B** zip → 122,630–157,013 B XHTML |
| Wall clock (this session) | 0.53 / 0.57 / 0.54 s for the content fetch | 0.50 / 0.59 / 0.78 s for the zip; token 0.21 s |
| Parse | 0.7–2.1 ms | 2.3–4.0 ms including the unzip |

⚠ **The Companies House Document API runs its own rate-limit budget, separate from the Public Data API's.**
Measured directly — three calls in sequence: [fetched]

```
GET api.company-information…/company/00445790          x-ratelimit-limit: 600  x-ratelimit-remain: 599   x-ratelimit-window: 5m
GET document-api.company-information…/document/{id}    X-Ratelimit-Limit: 600  X-Ratelimit-Remaining: 599   (no window header)
GET api.company-information…/company/00445790          x-ratelimit-limit: 600  x-ratelimit-remain: 598
```

The Public Data counter went 599 → 598 across a Document API call, so the Document API call did **not** spend
it; and the Document host answered with its own 600-budget headers, spelled **`X-Ratelimit-Remaining`**, not
the Public Data API's `x-ratelimit-remain`. Reset was ~283 s ahead, consistent with the same 5-minute window.
`UK_SPEC.md` §1.2 records only the Public Data spelling `[repo]`; a client that reads `x-ratelimit-remain` off
a Document API response gets `None` and silently stops limiting. The published limit — *"You can make up to
600 requests within a five-minute period"* — is stated once, for "the Companies House API", with no mention of
per-API budgets. [fetched] **So the Document API doubles the effective budget and the client must count it
separately.** Bolagsverket's 60/min is one budget for everything, token included `[repo]`.

### Cache

D-043(h) rules one cache key per **upstream call**, not per block. Britain's `financials` is a *different*
fetch from Britain's `filings` — filing history is the first of three requests, not the same body — so unlike
Norway this is **two fetches, two `SourceRef`s**, which is D-046's "two fetches, one answer" shape rather than
D-043(h)'s. Sweden's `financials` shares `/dokumentlista` with `filings` and then adds a second call, so it is
one shared key plus one per document.

**Store the figures, never the document.** Both documents contain natural persons' names (Fact 5); the parsed
`FinancialPeriod` does not. That is not only a footprint argument — a cached iXBRL blob is a store of personal
data with a retention policy nobody has written.

### Licence — and it is not the same question as the API's licence

**Britain.** Companies House's copyright statement, verbatim: [fetched]

> "The material featured on this site is subject to Crown copyright protection unless otherwise indicated. The
> Crown copyright protected material … may be reproduced free of charge in any format or medium provided it is
> reproduced accurately and not used in a misleading context. Where any of the Crown copyright items on this
> site are being republished or copied to others, the source of the material must be identified and the
> copyright status acknowledged."

> "**The permission to reproduce Crown protected material does not extend to any material on this site which
> is identified as being the copyright of a third party. Authorisation to reproduce such material must be
> obtained from the copyright holders concerned.**"

That second paragraph is the whole point of asking. A set of filed accounts is **authored by the company and
its accountants**, not by the Crown; Companies House holds it as registrar. Companies House publishes **no
licence statement for the content of a filed document** distinct from its site material, and the Crown
copyright grant it does publish carves out third-party copyright by name. The Accounts Data Product page says
only *"Each data file is provided free of charge and is not supported."* [fetched] The campaign site carries a
blanket *"All content is available under the Open Government Licence v3.0, except where otherwise stated"*
[fetched] — a footer on a campaign site, not a statement about the register's document store. **Do not write
"OGL" into a `SourceRef.license` for a figure derived from a filed document.** Describe the regime, as
`tasks/T26-recon.md` did for Bolagsverket and `tasks/T48-recon.md` did for ELMA. (The mitigating fact, which
is real but is a lawyer's call and not an implementer's: what we would relay is a *number*, and a number is not
an expressive work.)

**Sweden.** Already settled and unchanged `[repo]` `tasks/T26-recon.md`: *"Du får använda dessa data fritt för
kommersiella och icke-kommersiella syften … så länge användningen inte bryter mot lagar om skydd av
personuppgifter eller sekretess"*, with **no named licence** and a third-party audit's "CC BY 4.0" claim
explicitly refused. The personal-data proviso in that sentence bites harder on a document than on a company
record, and Fact 5 is the answer to it.

---

## Fact 5 — the person-bearing test (D-042(e))

**Passed, and by construction rather than by allowlist: in all six documents, every person-bearing fact is an
`ix:nonNumeric` and no `ix:nonFraction` carries a name.** Counted: 24 + 36 + 24 + 95 + 79 + 88 = **346 numeric
facts across six documents, 0 of which are a name.** [fetched]

The person-bearing concepts, by name, so the barred list is explicit — **their values were never printed,
never logged and never written anywhere in this session**:

| Register | Concept | `ix` element | Count |
|---|---|---|---|
| GB | `uk-core:DirectorSigningFinancialStatements` | `nonNumeric` | 2 / 1 / 2 |
| GB | `uk-bus:NameEntityOfficer` | `nonNumeric` | 1 / 4 / 1 |
| SE | `se-gen-base:UnderskriftArsredovisningForetradareTilltalsnamn` / `…Efternamn` (2017 taxonomy) | `nonNumeric` | 4 + 4 |
| SE | `se-gen-base:UnderskriftHandlingTilltalsnamn` / `…Efternamn` (2021 taxonomy — **renamed**) | `nonNumeric` | 4 + 4 |
| SE | `se-comp-base:UnderskriftFaststallelseintygForetradareTilltalsnamn` / `…Efternamn` / `…Foretradarroll` | `nonNumeric` | 1 each |

**The rule an implementer can be held to is one line: read `ix:nonFraction`, never `ix:nonNumeric`.** It is
testable statically (a test asserts the extractor's element filter), it needs no per-concept blocklist, and it
survives a taxonomy rename — which matters, because Sweden renamed its signature concepts between the two
versions sampled and a hardcoded blocklist would have gone stale silently. It also means the FRC's
`DirectorSigningFinancialStatements` concept the brief singles out is not "avoided"; it is **unreachable**.

Three riders:

1. **The three GB flags D-043(g) would want are `ix:nonNumeric` — but their values are not in the text.**
   `AccountingStandardsApplied`, `AccountsType` and `AccountsStatusAuditedOrUnaudited` are empty elements whose
   value is the **explicit dimension member on the context** (Fact 1). So `accounting_framework`, `scope` and
   `audit_exempt` can be read from `xbrldi:explicitMember` QNames without relaxing the one-line rule.
   Sweden's equivalent is cheaper still: the **`schemaRef` href** (`…/k2/risbs/2021-10-31/…`).
2. **Neither document's entity context leaks anything.** GB: `<xbrli:identifier
   scheme="http://www.companieshouse.gov.uk/">04374209</…>`. SE: `scheme="http://www.bolagsverket.se"`,
   value `556189-0038`. [fetched] Company numbers, not personal identifiers — no Swedish personnummer anywhere,
   which was the live risk given that Bolagsverket's `identitetsbeteckning` accepts one.
3. The one numeric fact that is *about* people is `uk-bus:AverageNumberEmployeesDuringPeriod` /
   `se-gen-base:MedelantaletAnstallda` — an aggregate count, not a particular, and it is not a D-043(c) field.

---

## Fact 6 — the trap

**The sign of a British number is in the presentation, not in the fact — and it is silent, self-consistent and
untestable against the register.**

Not "consolidated versus entity-only" (Britain's small-company iXBRL is entity-only by construction, and
Sweden's K2 channel excludes koncernredovisning). Not "prior-period column" — real, live in 2 of 3 British
documents which tag both years, and defeated by one line that selects the latest context. Not "assuming every
company files iXBRL" — that one is loud: the `resources` map simply lacks `application/xhtml+xml`, and
`paper_filed` predicts it 8 times out of 8 for free.

The trap is the one that **passes every test an implementer would write**. A parser that reads
`uk-core:NetAssetsLiabilities` off document A returns `17,549`. It is a well-formed monetary fact, in GBP, on
the right context, with the right `decimals`, and it equals the document's own `Equity` and its own
`TotalAssetsLessCurrentLiabilities` — three tagged facts agreeing with each other. Every internal check an
implementer thinks to write **passes**. The number is wrong by 2 × £17,549 and its sign is inverted, and the
company is in compulsory liquidation, so the block would report a solvent balance sheet for an insolvent
company on a credit question. `ixbrlparse` gets the same answer. Companies House does not validate it —
`filing_history` shows it accepted. The only thing that catches it is the **cross-check the register itself
does not require**: `FixedAssets + CurrentAssets − Creditors[WithinOneYear]` against the tagged
`TotalAssetsLessCurrentLiabilities`, which disagrees by exactly twice the value.

D-043(e) already refuses to *derive* figures, and it is right; what this finding adds is that in Britain the
**one permitted comparison must be a different comparison**. D-043(e) lets the block name a gap between
`total_assets` and `total_equity_and_liabilities` — two fields Britain never carries at all. The British
equivalent is the net-assets identity above, and if it fails, the honest output is not a corrected number but
**no `BalanceSheet` at all plus a note**, because there is no way to know which of the four facts is the
mistagged one.

Sweden's version of the same trap is smaller and different: `se-gen-base:Soliditet` — the equity ratio, which
the register's own taxonomy tags — is filed by **the same company** as `−0.1761` in its 2020 report and
`−17.61` in its 2022 report's comparison column: **the identical quantity under two scales**, both with
`unitRef="procent"` resolving to `xbrli:measure = pure`. [fetched] The unit does not disambiguate it and
nothing in the document does. It is the sharpest possible argument for D-043(e)'s refusal of ratios: here the
register *hands* you the ratio, and it is unusable.

---

## Verdict

**Sweden: bounded — one Sonnet task. Britain: not worth it now, and the thing that would change that is
1 April 2028, not a better parser.** They are different answers to the same brief because the registers are
not comparable, and D-043(i)'s "the reason is ours, not theirs" survives for exactly one of the two.

### Sweden — `bounded`

Every premise holds. 15–16 of 19 D-043(c) figures on every document sampled, including **`total_assets` and
`total_equity_and_liabilities`, which Britain never has**; one concept name per figure, identical across a
2017 and a 2021 taxonomy; **zero dimensions**; correct signs on losses; 18/18 of the documents' own identities
reconcile exactly; two metered requests; a 45 KB zip holding one 125–157 KB XHTML; 2–4 ms to parse with the
standard library; a person-bearing rule that is one line of code.

Sketch for the architect:

| | |
|---|---|
| Footprint | `registries/se/financials.py` + one parser. **No new runtime dependency** — `zipfile` and `xml.etree` are stdlib. `ixbrlparse` (MIT, ~14 MB with `lxml`) is the alternative if a reviewer prefers a maintained library over 150 lines; the recon's measurement is that it is not needed and is 10× slower. |
| Models | `FinancialSummary` / `FinancialPeriod` / `IncomeStatement` / `BalanceSheet` **exactly as D-043(c) defines them**, no new fields. D-042(g) and D-044(a) both bind: the Norwegian block is canonical and this one must be field-identical. |
| Parser's home | `registries/se/`, not `core/`. One filler is not a shared abstraction (D-044(a)'s rule was *measure first, then unify*), and Britain — the only candidate second caller — is not being built. |
| `currency` | from the **unit** (`unitRef` → `xbrli:measure` → `iso4217:SEK`), never from `se-cd-base:Redovisningsvaluta`, which was renamed and re-typed between the two taxonomy versions sampled. D-043(d) makes it required with no default, so getting this wrong drops the whole period. |
| `accounting_framework` | `"K2"` / `"K3"`, from the `link:schemaRef` href path. `scope` = entity accounts (the channel excludes koncernredovisning). |
| `document_id` | the same `dokumentId` the sibling `FiledDocument` already carries — D-043(c) already reserves the field, and here the two blocks genuinely share a handle. |
| Requests | `filings` and `financials` share the `/dokumentlista` fetch (one key, D-043(h)); `financials` adds **one** `/dokument/{id}` per period returned. **Fetch one period by default**, not six — six periods is six requests against 60/min, and D-043 carries one period for Norway. |
| TTL | an annual report is immutable once filed. The document parse is cacheable ~indefinitely on `dokumentId`; the *list* is not. Two kinds, and D-042(j) as amended already keys per upstream call. |
| `notes` | the population sentence, stated as a limit and not an apology: this channel carries **digitally submitted aktiebolag annual reports under K2 or K3, from 2020**; a company that files on paper, under IFRS, or as a handelsbolag / ekonomisk förening / bostadsrättsförening has no document and gets an absent block, not an empty one (D-042(d)(3)). |
| Done-check | `5561890038`'s 2025 report yields `total_assets == total_equity_and_liabilities == 515409.0`, `equity == 508409.0`, `profit_for_period == -10536.0`, `currency == "SEK"`; a company with an empty `/dokumentlista` yields an absent block with the note; **and a test asserts the extractor never touches `ix:nonNumeric`.** |

The one thing the architect must decide rather than inherit: **how many periods.** One request per period is
the whole cost model, and D-043 has no precedent — Norway's register returns one period in the body we already
have.

### Britain — `not worth it`, and the evidence is the population, not the parsing

The parsing is *easier* than Sweden's in one respect (no zip) and harder in two (dimensioned creditors, no
totals), and none of that decides it. Three facts decide it, in order:

1. **The companies a caller asks about do not have the document.** Tesco: 25 of 25 accounts filings PDF-only.
   NatWest Markets: 25 of 25. Monzo, Deloitte LLP: the same. The register's own number is ~75% electronic ×
   ~97% iXBRL, and the missing quarter is the large-filer end. A `financials` block that is `null` for every
   company anyone has heard of is worse than no block: it teaches the caller the capability does not work.
2. **Of the ~20 D-043(c) figures, a micro-entity filing carries 5 and no income statement at all** — no
   revenue, no profit — and no British filing sampled carried `total_assets`, `liabilities` or
   `total_equity_and_liabilities`, because the FRS balance-sheet format has no such lines and **D-043(e)
   forbids adding two numbers to make one**. The best case measured is 8 of 19, on a small company with a full
   P&L.
3. **The sign is not reliably in the fact** (Fact 6), the failure is silent, and it inverts a solvency answer.

And the mandate does not fix it the way it first appears to. From 1 April 2028 everything is iXBRL — *and*
small and micro entities get *"the option to opt out of having these profit and loss accounts published on the
public register"* [fetched]. So the population that will *have* machine-readable accounts is precisely the
population entitled to withhold the two numbers a credit question wants. The right time to revisit Britain is
**after April 2028, on evidence of what the register actually publishes**, not on the strength of the
legislation.

`D-043(i)` should be amended on this point, because as written it is now wrong in both directions: it says
Britain's and Sweden's figures are blocked by *"a scope decision we made"*. Sweden's are — D-041(g) ruled the
zip out as *"a third request, an XBRL package to parse"*, and it is **a second request and a 45 KB single-file
zip that parses in 4 ms with the standard library**, which is the same test D-043(a) applied to D-041(g) and
should now be applied again. Britain's are not: they are blocked by the **register's own population**, which is
the amended D-042(g)'s "record it as the register's silence" case, and it needs saying in writing so nobody
re-opens it as a parsing question.

### What I could not establish

- **Cross-company stability in Sweden.** All three Swedish documents are one company (`5561890038` — the only
  production Swedish company in the repo confirmed to have documents; the other Swedish fixtures are
  test-environment identifiers `[repo]`), so the concept names are proven stable across **five years and two
  taxonomy versions** but not across filers or filing software. `se-gen-base` is the shared base of both K2 and
  K3 [search], so the expectation is strong; it is not measured. **No K3 document was seen at all.** One more
  `/dokumentlista` + `/dokument` pair on a K3 aktiebolag would settle it and is the first thing the
  implementing task should do.
- **Bolagsverket's own documentation, read directly.** `bolagsverket.se` refuses this machine outright — a
  bare `curl` gets `Recv failure: Connection reset by peer`, and every URL fetched through the tooling returns
  a CAPTCHA interstitial. Every Bolagsverket *page* quotation in this file is therefore **[search]**, not
  [fetched], and each has a [fetched] corroboration from the wire beside it. The devportal
  (`portal.api.bolagsverket.se`) and the gateway answered normally, so this is a WAF on the public site only.
- **The taxonomies' licences.** `taxonomier.se` (Sweden) and the FRC (Britain) both publish their suites
  freely; neither page yielded a licence statement to a fetch. Not load-bearing — the prototype downloads no
  taxonomy — but it would be if anyone proposed `arelle`.
- **Whether the British Document API's 600/5-min budget is per key or per host.** Measured that it is a
  *separate* counter from the Public Data API's; not measured whether it is shared across keys or what its
  window truly is (reset was 283 s ahead, consistent with 5 minutes, on one observation).
- **What a large Swedish K3 filer's document looks like**, and therefore whether the block would ever carry a
  company anyone has heard of in Sweden either. Ericsson has none `[repo]`; that is IFRS, which is excluded.
  The K3 population is the open question and it is the one that decides how much the Swedish block is worth.

---

## Sources

**Fetched live this session (2026-09-09).**
`https://api.company-information.service.gov.uk/company/{00445790,SC090312,09446231,OC303675,13948759}/filing-history?category=accounts` ·
`https://api.company-information.service.gov.uk/company/00445790` ·
`https://document-api.company-information.service.gov.uk/document/{id}` (metadata ×9) ·
`https://document-api.company-information.service.gov.uk/document/{id}/content` (×3, `Accept: application/xhtml+xml`) ·
`https://portal.api.bolagsverket.se/oauth2/token` ·
`https://gw.api.bolagsverket.se/vardefulla-datamangder/v1/dokumentlista` ·
`https://gw.api.bolagsverket.se/vardefulla-datamangder/v1/dokument/{id}` (×3) ·
`https://download.companieshouse.gov.uk/en_accountsdata.html` ·
`https://resources.companieshouse.gov.uk/infoAndGuide/faq/accountsDataProduct.shtml` ·
`https://resources.companieshouse.gov.uk/legal/crown.shtml` ·
`https://changestoukcompanylaw.campaign.gov.uk/changes-to-accounts/` ·
`https://developer-specs.company-information.service.gov.uk/guides/rateLimiting` ·
`https://developer-specs.company-information.service.gov.uk/document-api/reference/document-location/fetch-a-document` ·
`https://www.frc.org.uk/library/…/frc-taxonomies/current-uk-and-irish-digital-reporting-taxonomies/` ·
`https://xbrl.frc.org.uk/FRS-102/2023-01-01/FRS-102-2023-01-01.xsd` ·
`http://xbrl.taxonomier.se/se/fr/gaap/k2/risbs/2021-10-31/se-k2-risbs-2021-10-31.xsd` ·
`https://pypi.org/pypi/{arelle-release,ixbrlparse,stream-read-xbrl,python-xbrl,brel-xbrl}/json`

**Refused this machine (CAPTCHA / connection reset), quoted [search] instead.**
`bolagsverket.se/apierochoppnadata/hamtaforetagsinformation/vardefulladatamangder/apiforvardefulladatamangder.5513.html` ·
`bolagsverket.se/omoss/utvecklingavdigitalatjanster/digitalinlamningavarsredovisning.2255.html` and its
`tekniskdokumentationfordigitalinlamningavarsredovisning.2267.html` ·
`bolagsverket.se/…/antaldigitaltinlamnadearsredovisningar.6070.html` (no Wayback snapshot exists for any of them)

**Read in this repository.** `DECISIONS.md` D-041(g), D-042(g)/(j), D-043 (all), D-044, D-045(h), D-046 ·
`UK_SPEC.md` §1.1–§1.4 · `SWEDEN_SPEC.md` §1.1–§1.5, §5.5 · `tasks/T26-recon.md` · `tasks/T44.md` (the
orchestrator addendum) · `tasks/T48-recon.md` (form) · `~/mcp-growth/DEPTH.md` §3.1, §4.2 ·
`src/registry_mcp/registries/se/filings.py` · `tests/fixtures/ch_*_filing_history.json`,
`tests/fixtures/bv_dokumentlista.json`, `tests/fixtures/README.md`
