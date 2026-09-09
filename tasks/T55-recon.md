# T55-recon — Part 0: one K3 document was not found, and the orchestrator's decision on what follows

Owner: a Sonnet, dispatched by the orchestrator. Brief: `tasks/T55.md`. Obtained **2026-09-09**. See
**"Orchestrator decision and continuation"** below for what happened after Part 0's own verdict — Parts
A, B, C, E and F were built on K2 alone, per that decision, not on this recon's own recommendation.

Tags: **[fetched]** read off the wire this session · **[search]** from a search result · **[repo]** read
in this repository. No document, name or value below is a natural person's — see the last section.

**Part 0's own verdict, unedited from when it was written: no live K3 document was obtained.** Not
because K3 uses different concept names or introduces dimensions — the opposite: everything I *could*
measure says K2's premises hold. It stops because the literal ask — one real company's live-filed K3
document via one `POST /dokumentlista` and one `GET /dokument/{id}` — was not met, and the reason is that
**every `POST /dokumentlista` call this task's
4-call budget allowed came back empty**, on companies chosen for exactly the reason K3 requires (they are
too large to lawfully use K2). The budget is now at 0 of 4; Parts A–C, E and F do not start. Part D (the
`core/cache.py` row) is unblocked by Part 0 per the brief's own table and is done separately.

---

## Live-call budget spent, declared before anything else

| Call | Count | Detail |
|---|---|---|
| `POST /oauth2/token` (production) | 2 | One per script invocation; shares the same 60/min bucket as everything else. |
| `POST /dokumentlista` (production) | **4 of 4** | Four candidate aktiebolag, below. **Budget now exhausted.** |
| `GET /dokument/{id}` (production) | **0 of 6** | Never reached: every candidate's document list was empty, so there was nothing to fetch. |

Credentials were read from `~/secrets/registry-mcp/bolagsverket-prod.txt` into shell variables by the
invoking shell (`set -a; source …; set +a`) immediately before each `uv run python …` invocation, never
echoed, never written to a file, never passed as a script argument, and not present in this repository.
No call was made to `api.foretak.dev`, Companies House, GLEIF or the FCA. `833286602` and `833285602`
were never looked up. The throwaway fetching script (`se_k3_recon.py`) lived only in the session
scratchpad, mirroring `tasks/T52-recon.md`'s `ixparse.py`; it is **not committed** and nothing under
`src/` or `tests/` was touched to write it.

---

## What was tried: four candidates, chosen by a rule, not by fame

`tasks/T52-recon.md`'s "What I could not establish" names the exact gap: *"no K3 document was seen at
all… `se-gen-base` being the shared base of both K2 and K3 is a `[search]` expectation, not a
measurement… the K3 population is the open question."* Bolagsverket's free API has no search operation
(`SWEDEN_SPEC.md` §4), so a candidate identifier has to come from outside it. The rule used: **a
Swedish aktiebolag legally required to use K3 — "större företag" under ÅRL 1 kap. 3 §, exceeding two of
{>50 employees, >40 MSEK balance sheet, >80 MSEK net turnover} for two years running — cannot lawfully
file under K2 at all, so if such a company files digitally through this channel, the filing is K3 by
construction, not by luck.** Four such companies, sourced by web search (never from `api.foretak.dev` or
any barred registry) and Luhn-verified locally against `registries/se/rules.py::_luhn_check_digit`
**before** spending a call on any of them:

| Orgnr | Company | Why chosen | `POST /dokumentlista` result |
|---|---|---|---|
| `5560747569` | IKEA Svenska Försäljnings AB | Large retail operating subsidiary; no listed entity in its own ownership chain (INGKA/Interogo Foundation, unlisted) | **[fetched]** HTTP 200, `dokument: []` |
| `5560747551` | IKEA of Sweden AB | Same group, product-range function; same reasoning | **[fetched]** HTTP 200, `dokument: []` |
| `5560566258` | Ericsson AB | The Swedish operating company — **a different legal entity** from the listed, IFRS, channel-excluded parent Telefonaktiebolaget LM Ericsson (`5560160680`, T52-recon Fact 2) | **[fetched]** HTTP 200, `dokument: []` |
| `5560796871` | Spendrups Bryggeriaktiebolag | Family-owned brewery, ~1,100 employees, no listed parent anywhere, no plausible IFRS/RFR2 motive at all | **[fetched]** HTTP 200, `dokument: []` |

All four are HTTP 200 with a genuinely empty `dokument` array — the same well-formed "nothing here"
answer Ericsson's listed parent gives (T44/T52-recon), not a 400 or a 404. **None of the four numbers is
wrong**: three of the four are independently corroborated across `bolagsfakta.se`, `allabolag.se` and
`merinfo.se`/`syna.se`, and all four pass the modulus-10 check digit Bolagsverket itself validates.

**This is itself a finding, not just an exhausted budget.** Every company chosen is large enough that,
*if* it files through this channel at all, the filing must be K3. Zero of four have filed through this
channel at all. That is weak evidence (n=4, all picked for public fame rather than for using ordinary
bookkeeping software) but it points the same direction as a plausible mechanism: `tasks/T52-recon.md`
Fact 2 already showed Bolagsverket's *K2* population is company software vendors' one-click e-filing
(the sampled K2 filer, `5561890038`, is a small company); a large company's statutory annual report is
often drafted by senior finance staff or an audit firm using a bespoke process that may not route through
the same digital button, **even though nothing legally stops it**. If that mechanism is real, "pick a
famous large company" is a poor way to find a K3 filer, and a better one is a **mid-sized** company just
over the K2/K3 line, filed through an accounting platform with digital-submission support — a company
nobody has heard of, which is exactly the profile the four candidates above were *not*.

---

## Supplementary evidence: Bolagsverket's own K3 taxonomy specimens (not a live filing — read this caveat before the table)

With the `/dokumentlista` budget at zero, I looked for anything that could de-risk the *substantive*
questions Part 0 asks — renamed concepts, dimensions — **without spending a Bolagsverket call**, since
none of that is barred by the ground rules (it calls neither Bolagsverket nor any barred registry).
`taxonomier.se` — already a cited source in `tasks/T52-recon.md` (it served the K2 schema) — publishes
worked example iXBRL instance documents for K3, which any accepted K3 submission must validate against
(a filer cannot invent a tag name; Bolagsverket's own guidance states the validator checks the document
"är uppmärkt med en godkänd taxonomi" [search]). **These are not filings. They are the taxonomy
publisher's own demonstration documents**, fetched by plain `GET` over HTTPS (no Bolagsverket
credential, no budget spent, not a company's data):

| Specimen | URL | Profile |
|---|---|---|
| K3 entity ("risbs"), 2021-10-31 taxonomy | `xbrl.taxonomier.se/se/exempel/faststalld-k3-arsredovisning/exempel-3-2021/faststalld-arsredovisning-k3-exempel-3-2021-rev20240214.xhtml` | "Complete annual report with certification statement and audit report for non-listed corporation with ongoing operations" [fetched] |
| K3 group ("k3k"), 2021-10-31 taxonomy | `xbrl.taxonomier.se/se/exempel/arsredovisning/k3k-exempel-2-2021/tillampningsexempel-k3-koncern-exempel-2-2021-rev20240916.xhtml` | "tagging of an annual **and consolidated** financial statement" [fetched] |

**`link:schemaRef`.** The entity specimen's entry point is
`…/gaap/k3/risbs/2021-10-31/se-k3-risbs-2021-10-31.xsd` — `/k3/` in the path, parallel to K2's `/k2/
risbs/2021-10-31/se-k2-risbs-2021-10-31.xsd` (`tasks/T52-recon.md` Fact 1). **The brief's
`accounting_framework` rule (checking the href path for `/k2/` vs `/k3/`) is confirmed against a real
K3-taxonomy document**, not only against K2's own path convention. [fetched] The group specimen declares
**both** `/k3/risbs/…` and `/k3k/risbs/2021-10-31/se-k3k-risbs-2021-10-31.xsd` — K3's group profile
imports the entity schema rather than replacing it, so checking for `/k3/` alone correctly classifies
both as K3; `/k3k/` appearing is a second signal that *could* mean "koncernredovisning", but **this task
does not wire it up** — see "What remains unverified" below.

**Concept names — the load-bearing table**, checked as the exact byte string `se-gen-base:<name>`
against every `ix:nonFraction/@name` in each document:

| D-043(c) concept | K3 entity specimen | K3 group specimen |
|---|---|---|
| `Nettoomsattning` | ✅ byte-identical | ✅ byte-identical |
| `Rorelsekostnader` | ✅ | ✅ |
| `Rorelseresultat` | ✅ (one instance carries `@sign="-"`) | ✅ |
| `OvrigaRanteintakterLiknandeResultatposter` | ✅ | ✅ |
| `RantekostnaderLiknandeResultatposter` | ✅ | ✅ |
| `FinansiellaPoster` | ✅ | ✅ |
| `ResultatForeSkatt` | ✅ | ✅ |
| `AretsResultat` | ✅ | ✅ |
| `Anlaggningstillgangar` | ✅ | not tagged in this specimen (see caveat) |
| `Omsattningstillgangar` | ✅ | not tagged in this specimen |
| **`Tillgangar`** | ✅ | not tagged in this specimen |
| `BundetEgetKapital` | ✅ | ✅ |
| `FrittEgetKapital` | ✅ | ✅ |
| `EgetKapital` | ✅ | ✅ |
| `LangfristigaSkulder` | absent (see caveat) | not tagged in this specimen |
| `KortfristigaSkulder` | ✅ | ✅ |
| **`EgetKapitalSkulder`** | ✅ | ✅ |
| **filled / checkable** | **16 / 17** | **12 / 17** |

Two absences, two different reasons, neither is a rename:

1. **Entity specimen, `LangfristigaSkulder` absent.** Every *other* balance-sheet total is present and
   byte-identical, including `Tillgangar` and `EgetKapitalSkulder`. The natural reading is the same one
   K2's own SE-2025 fixture already established for the same concept: this example company has no
   long-term liabilities this year, and D-043(f) says an absent line is not a zero. There is no
   alternative concept name anywhere in the document that could be a K3 rename — grepped for `Skuld`
   throughout; nothing else plausible appears.
2. **Group specimen, four balance-sheet totals absent** (`Anlaggningstillgangar`, `Omsattningstillgangar`,
   `Tillgangar`, `LangfristigaSkulder`). This document only tags **58 distinct concepts** total and is
   visibly a *selective* demonstration (a machinery/equipment note, deferred tax, restricted/unrestricted
   equity, group-internal short-term payables) rather than a complete balance sheet — it never tags a
   full asset side at all, for either total. **This is the specimen's own choice of what to demonstrate,
   not evidence that these concepts don't exist or are renamed at group level**: the group taxonomy
   (`se-k3k-risbs`) imports the entity taxonomy (`se-k3-risbs`) rather than replacing it (both appear in
   its own `schemaRef` list), so `se-gen-base:Tillgangar` remains a valid, taggable concept for a
   koncernredovisning; this specimen simply never exercises it. **This is exactly the residual risk this
   recon cannot close** — see below.

**Currency, dimensions, signs, scale — all checked against the entity specimen's own wanted-concept
facts, not the whole document:**

- **Every one of the 16 confirmed monetary facts carries `unitRef="SEK"` resolving to
  `xbrli:measure = iso4217:SEK`.** [fetched] The currency-from-the-unit rule (A3) is confirmed against a
  document built on the current (2021-10-31) taxonomy generation — the same generation as K2's SE-2025
  fixture, and the same generation whose `se-cd-base:Redovisningsvaluta`-successor concept the brief
  already says must never be read.
- **Zero dimensioned contexts in either specimen** (`n_context_with_dims = 0` of 10 and of 12 contexts
  respectively) — `xbrldi:explicitMember`/`typedMember` never appears. [fetched]
- **`@sign="-"` is used**: one of the two `Rorelseresultat` facts (current year vs. comparison) in the
  entity specimen carries it. **`@scale="0"`** on every wanted-concept fact checked — no scaling applied,
  values in whole SEK, matching K2's own precedent.
- **Person-bearing concepts are the same ones already known, not new ones.** The entity specimen's
  `ix:nonNumeric` facts include `UnderskriftHandlingTilltalsnamn`/`…Efternamn` and
  `UnderskriftFaststallelseintygForetradareTilltalsnamn`/`…Efternamn` — **exactly** the 2021-taxonomy
  renamed signature concepts `tasks/T52-recon.md` Fact 5 already recorded from K2's SE-2025 document, and
  no others. K3 does not introduce a fifth signature concept the one-line `ix:nonFraction`-only rule
  would need to additionally guard against — the rule is a static element-type filter, not a
  per-concept blocklist, precisely because it does not need to know these names at all. **No value of any
  `ix:nonNumeric` fact was read, printed or written anywhere in this session**, in either specimen; only
  element names and counts were inspected (12 person-bearing facts in the entity specimen across 4
  concepts, 6 in the group specimen across the same 4 — counts only).
- `n_nonFraction` / `n_nonNumeric`: entity specimen 438 / 131; group specimen 174 / 86. (Not comparable to
  K2's 79–95 / 35–38 — these specimens tag far more notes than a typical small-company K2 filing does,
  which is itself consistent with K3's fuller disclosure regime.)

---

## What remains unverified — the literal Part 0 ask, unmet

A taxonomy specimen is the publisher's demonstration of what a *conformant* document may contain; it is
not evidence of what a *real filer's own software* actually produces, at what completeness, with what
presentation quirks. Four things specifically are still unknown, and are exactly the class of thing
`tasks/T52-recon.md`'s Fact 6 (Britain's inverted sign) says a specimen or a schema can never settle:

1. **Whether a real K3 filing — entity or group — actually tags `Tillgangar` and the other balance-sheet
   totals**, at the completeness the entity specimen shows, or whether real filing software's coverage is
   closer to the group specimen's partial 58-concept demonstration.
2. **Whether a real K3 koncernredovisning is distinguishable from a K3 entity filing by `schemaRef`
   alone** (the `/k3k/` segment looks promising in one specimen, but one specimen is not a measurement).
3. **Whether K3's real-world filers ever produce a dimensioned context.** Zero across two specimens and
   zero across three live K2 documents is suggestive, not proof, for a taxonomy whose group profile
   plainly exists to represent something K2 structurally cannot.
4. **Everything Fact 6 was about** — a real filer's software getting a sign or a subtotal wrong in a way
   that still passes every internal check, which by construction cannot appear in a publisher's own
   correctness demonstration.

**None of this is a stop condition of the kind the brief names** ("if K3 uses different concept names,
stop and report" / "if K3 introduces dimensioned contexts, stop and report") — the specimens say the
opposite on both counts, as far as they go. **It stops because the ground rules fix the budget at four
`POST /dokumentlista` calls for the whole task, that budget is spent, and the brief specifically asks for
a document "in front of you," not a publisher's specimen** (`tasks/T55.md`: *"if a concept name, a byte
count or a figure in this brief disagrees with the document in front of you, stop and report"* —
building a parser and shipping it for K3 on the strength of a specimen rather than a filing is the
"scope decision made from a document's description" D-047's own reason section explicitly distinguishes
from "the document" itself, and only one of those is evidence).

---

## Recommendation

Three ways to close the actual gap, in the order I'd try them:

1. **A known-good identifier, from Kim or from Bolagsverket's own documentation, rather than another
   guess.** The technical guide (`teknisk-guide-digital-inlamning-arsredovisning-3-4.pdf`) and the
   digital-submission test bank page (both found this session, `bolagsverket.se`, both CAPTCHA-walled to
   this machine exactly as `tasks/T52-recon.md` found for the neighbouring pages) may name a real or
   test-bank K3 example company directly; a human reading them in a browser costs nothing against this
   task's budget.
2. **A small supplemental live-call allowance** (2–3 more `POST /dokumentlista` calls) for a second,
   better-informed attempt: mid-sized rather than famous, sourced from an accounting-software vendor's
   own published case study of a company that files digitally (Fortnox/Visma/Björn Lundén customers are
   the population `tasks/T52-recon.md` Fact 2 suggests actually uses this channel), rather than a company
   picked for being large enough to require K3.
3. **Accept the specimen evidence as sufficient to proceed**, on the explicit basis that it is
   *schema-conformance* evidence rather than *filing* evidence, and revisit only if a real K3 document
   ever disagrees with it — the same asymmetry D-043(a) already accepted once for a different reason
   (Norway's key figures "arrived parsed" and cleared D-041(g)'s bar without a byte-level filing read).
   I did not make this call myself: the brief was explicit that nobody has read a K3 filing and that this
   gap is allowed to stop the task, and a specimen is adjacent evidence, not the document the brief asked
   for.

Whichever is chosen, the two specimen files are on the wire and free to re-fetch (URLs above); the
`se_k3_recon.py` analysis script (scratchpad only, not committed) is reusable as-is against a real
document once one is found — it already implements the schemaRef/context/unit/nonFraction/nonNumeric
walk Part A's extractor would need, and nothing in it reads or prints a person-bearing value.

---

## Orchestrator decision and continuation (recorded after Part 0, same session)

**The orchestrator chose recommendation-adjacent option 3, sharpened**: proceed with Parts A, B, C, E and
F on K2 alone, shipping K3 support on the specimen evidence above rather than waiting on a live filing.
Three reasons given, all traceable to measurements already in this file: `tasks/T52-recon.md` proved the
K2 concept names byte-identical across five years and two taxonomy versions on **real filings**; the K3
specimens above show 16 of 17 D-043(c) concepts identical under `se-gen-base` with zero dimensions; and
the four K3-sized companies tried above all have empty `/dokumentlista` results, which is itself evidence
that **the population this channel actually serves is the small aktiebolag filing under K2** — the
supplier long tail `include=["financials"]` exists for in the first place, not the large companies this
recon went looking for. That third reason reframes rather than dismisses the "what remains unverified"
section above: if K3 filers are genuinely rare in this channel, the risk a shipped K3 parser is carrying
is smaller in *practice* than the abstract gap made it look, even though nothing has closed the gap
itself.

**Two rules from the orchestrator shape everything built after this point, and both are enforced in code,
not only in prose:**

1. `accounting_framework` is read from the `link:schemaRef` path (`/k2/` or `/k3/`) exactly as this brief
   always specified. **When it reads K3, the block's own `notes` carries one sentence saying the
   extractor was validated on K2 filings and K3 taxonomy specimens only, no K3 filing having been observed
   live** — `registries/se/financials.py`'s `_K3_VALIDATION_CAVEAT`, appended by `summary_notes()`
   whenever `accounting_framework == "K3"`. The same sentence appears exactly once in
   `registries/se/ixbrl.py`'s module docstring, under "On the K3 taxonomy specifically".
2. **Supplementary live budget, spent exactly as authorized and nowhere else**: one more
   `POST /dokumentlista` and two `GET /dokument/{id}`, all on `5561890038` — the 2025 report (the
   done-check) and 2020 (for the cross-taxonomy / string-currency test, matching the brief's original
   fixture table). No other live call was made after this point. Accounting, added to the table this
   file opened with:

| Call | Count this continuation | Running total this task |
|---|---|---|
| `POST /oauth2/token` (production) | 1 | 3 |
| `POST /dokumentlista` (production) | **1 of 1 authorized** | **5** (4 spent finding no K3 filer, 1 authorized supplement) |
| `GET /dokument/{id}` (production) | **2 of 2 authorized** | **2** |

`5561890038`'s `/dokumentlista` on production lists **six** annual reports, 2020-12-31 through
2025-12-31, matching D-047(f)'s stated fact exactly; the two documents fetched (2025: 47,497 zipped B /
157,013 unzipped B; 2020: 45,258 zipped B / 126,846 unzipped B) are byte-identical in size to
`tasks/T52-recon.md`'s own measurements of the same two filings, which is the strongest evidence available
that this session read the same documents rather than a different pair. Both were parsed through the
shipped `registries/se/ixbrl.py` + `registries/se/financials.py` code (not a throwaway script) and
reproduce the brief's done-check exactly: `total_assets == total_equity_and_liabilities == 515409.0`,
`equity == 508409.0`, `profit_for_period == -10536.0`, `currency == "SEK"` for 2025; and 2020's own figures
match `tasks/T52-recon.md`'s SE-2020 column exactly (`total_assets == total_equity_and_liabilities ==
992027.0`, `equity == -174721.0`, `non_current_liabilities == 935948.0`, `profit_for_period == -50497.0`).
Neither document's currency concept (`Redovisningsvaluta`/`RedovisningsvalutaHandlingList`) was read; both
resolved `currency` through the unit alone, exactly as A3 requires.

What Parts A–F actually built, fixtures included, is reported in full in the implementer's final report to
the orchestrator (not restated here) — this section exists so a reader of this recon file alone, without
that report, is not left believing the task stopped at Part 0.

---

## Person-bearing content — the rule this recon itself followed

No document fetched this session was written to this repository, to a log, or printed as raw content.
The two specimens are held only in the session scratchpad. Every `ix:nonNumeric` fact encountered was
inspected for its **element name and count only**; no value was read, printed, stored or compared. The
four production `/dokumentlista` responses carried no document (nothing to inspect) and no personnummer
(all four identifiers are ten-digit organisationsnummer for aktiebolag, never a personal identifier).

## Sources

**Fetched live this session (2026-09-09).** `https://portal.api.bolagsverket.se/oauth2/token` (×2) ·
`https://gw.api.bolagsverket.se/vardefulla-datamangder/v1/dokumentlista` (×4, production) ·
`https://xbrl.taxonomier.se/se/exempel/faststalld-k3-arsredovisning/exempel-3-2021/faststalld-arsredovisning-k3-exempel-3-2021-rev20240214.xhtml` ·
`https://xbrl.taxonomier.se/se/exempel/arsredovisning/k3k-exempel-2-2021/tillampningsexempel-k3-koncern-exempel-2-2021-rev20240916.xhtml`.

**Search, corroborating the four candidate identifiers only (never a figure or a filing).**
`bolagsfakta.se`, `allabolag.se`, `merinfo.se`, `upplysningar.syna.se` (each candidate's orgnr, cross-checked
against at least two of these) · `taxonomier.se/taxonomier-k3-exempel.html` and
`taxonomier.se/taxonomier-k3k-exempel.html` (the specimen index pages) ·
`bolagsverket.se/.../tekniskdokumentationfordigitalinlamningavarsredovisning...` and the technical-guide
PDF (named, not read — CAPTCHA-walled to this machine, same finding `tasks/T52-recon.md` recorded for
neighbouring Bolagsverket pages).

**Read in this repository.** `tasks/T55.md`, `tasks/T52-recon.md`, `DECISIONS.md` D-043, D-047(f),(g),
D-041(c),(g), D-042, D-044(a), D-038, D-037, D-039, D-040, D-028(2) · `registries/no/accounts.py`,
`registries/no/client.py`, `registries/se/filings.py`, `registries/se/client.py`,
`registries/se/rules.py` · `core/models.py`, `core/cache.py`, `core/registry.py` ·
`~/research/registry-mcp/02-registers-landscape/02b-sweden-openapi.json`.
