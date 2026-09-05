# CORE_ROADMAP_SPEC

The implementation spec for `DECISIONS.md` **D-024 … D-030** — the seven decisions the
research library says must precede any further country or feature work. The decisions carry
the rulings and the reasons; this file carries the **order**, the **blockers**, the concrete
**shapes and landing points**, and a **done-check** per item, so an implementer can start the
moment the freeze lifts without re-deriving any of it.

Roadmap ids are `R-1 … R-8` and they **are** the recommended order. They are not task ids:
the orchestrator assigns `T`-numbers, and `DECISIONS.md`'s "Applies to tasks" lines cite the
`R`-id so the two can be mapped without either file guessing at the other's numbering.

Written by Opus A (architect) on 2026-09-05 under task T22. Decisions only — no code was
changed. `uv run pytest -q -m "not live"` re-run after writing: **422 passed, 5 deselected,
0 failed**. The T17/T18 baseline was 417; the five extra are T20's, landing concurrently
(`tests/test_mcp.py`, `tests/test_client_no.py`, `registries/no/mapping.py` — the ENK
personal-data note among them, which is R-8's precondition (1) arriving early). This task's
own footprint is two files: the `DECISIONS.md` append and this one.

---

## 1. Recommended order

| # | Item | Decision | Core? | Blocked? | Why here |
|---|---|---|---|---|---|
| **R-1** | Batch lookup | D-024 | **yes** — 2 models + 1 concrete method | no | Highest value, no external dependency, and it fixes the one gap our own docs already sell. It also sets the per-item error-row precedent every later item reuses, and it defines the unit R-4 has to meter |
| **R-2** | `euid` + `advertising_protected` | D-026(a),(b) | **yes** — 2 nullable fields | Danish *mapping* only | Two lines of model for a cost that only rises. Must be in the shape **before** Denmark's answer arrives (~2026-09-23), because retrofitting a frozen response is the expensive version |
| **R-3** | Sub-national key | D-027 | **yes** — 2 fields + 1 `CountryInfo` field | no | Pure model work, zero upstream, zero privacy. Deciding it under German deadline pressure with a half-built module in the tree is the expensive version. Costs an afternoon now |
| **R-4** | API keys + metering | D-030 | barely — 1 `ErrorCode` member | no | The gate to every revenue item, and — more usefully today — the only way the next ten prioritisations get evidence instead of argument. **Must follow R-1** so the meter counts identifiers rather than requests from day one |
| **R-5** | `SourceRef` / `include=[…]` + LEI | D-026(c) | **yes** — the attachment mechanism | no | Builds the machinery R-6 and R-8 both need, on the **lowest-risk possible payload**: CC0, keyless, no personal data, no statutory clock. Get the mechanism wrong here and it costs a re-shoot; get it wrong on officers and it costs more than that |
| **R-6** | Peppol / ELMA capability | D-029 | **yes** — 1 attachment model | endpoints unverified | Somebody else's calendar sets this one: the duty starts **1 January 2027**. Highest-value thing an accounting agent asked for that nobody offers, and it needs R-5 to exist first |
| **R-7** | NACE harmonisation | D-025 | **yes (small)** — 2 fields + `core/nace.py` | **yes — licence + revision** | S effort and high value; it would sit at R-2 if the table were shippable. It is not, until two facts about a static file are read. Do the reading early even if the build waits |
| **R-8** | Officers / PSC | D-028 | **yes** — the largest model change here | **yes — 4 preconditions** | Last on purpose. The biggest real gap, the only personal-data feature, and the only item on this list where shipping it badly is worse than not shipping it. Every other decision here can be revised by a later entry; a residential address served after the register withdrew it cannot be un-served |

### What must already be true before R-1 starts

- **The feature freeze has lifted.** The guide's Step 11 froze feature work; `PROGRESS.md`
  records Kim's 2026-09-05 exception for the *legibility* backlog only (no `core/` change, no
  response-shape change). **Every item in this file changes `core/`.** None of them is covered
  by that exception, and none may start on it.
- **T19 has landed.** The 26-case agent eval is the before/after instrument for exactly the
  choices R-1, R-5 and R-8 make — argument-versus-tool, `include=[…]` discoverability, whether
  an agent finds the batch path at all. Building these before the eval means never learning
  whether any of them helped, which is the sequence `research/07-product-improvements.md`
  ranks item 6 above every feature to prevent.
- **T20 has landed**, in particular the ENK personal-data note. It is the cheapest half of
  R-8's precondition (1) and it touches no `core/` file; confirm it is in before R-8 opens.

---

## 2. Blocked on external facts

Nothing below is blocked on an engineering unknown. All five are facts somebody else holds.

| Item | Blocked on | Who / when | Blast radius if we guess |
|---|---|---|---|
| **R-7** NACE | **Eurostat's redistribution terms** for the NACE Rev. 2 labels — flagged unread in `12-coverage-gap-accounts-documents-codes-addresses.md` | Eurostat / RAMON licence page; one read | Shipping a bundled table we may not redistribute. **Fallback if restrictive:** the UK ONS SIC 2007 condensed list, Crown copyright under OGL v3, which by the ONS's own statement carries the same words at four digits and so covers both live countries |
| **R-7** NACE | **Which NACE revision** UK SIC 2007 and Norwegian SN2007 correspond to as of 2026 (Rev. 2 vs a Rev. 2.1-based national update) | Each register's own classification documentation; one read per country | A table one revision behind produces confidently wrong classes for exactly the codes that moved — the D-009 failure mode. If the two live countries sit on different revisions, that is a finding to bring back to `DECISIONS.md`, not a thing to average |
| **R-2** advertising protection | **Denmark's terms** and the CVR field name/semantics for the CVR-loven § 19 protection flag | Erhvervsstyrelsen, sagsnummer **177481**, answer expected **~2026-09-23** (`PROGRESS.md` T16) | The *field* is not blocked and should ship regardless — only the Danish *mapping* waits. Guessing the CVR field name costs a re-map; shipping the field late costs a frozen-shape migration |
| **R-8** officers | **AMLD6 / Directive (EU) 2024/1640 transposition** — whether legitimate-interest access to beneficial-ownership registers returns, and on what timetable. The research budget ran out before a primary source was read | EUR-Lex + per-member-state transposition; unresolved | Decides whether a BO block is ever more than an empty list with a reason outside GB. Guessing it *open* would build a feature that cannot lawfully answer; guessing it *closed* only costs us the feature later |
| **R-8** officers | **Whether Companies House signals officer suppression explicitly or omits silently**; and whether brreg's *open* `/roller` returns `fødselsdato` on the unauthenticated path | Both settled by one live unauthenticated call each | If CH omits silently, `suppressed` cannot be derived at all and must stay `None` — emitting `False` would assert "nothing withheld" about a register that never said so. The brreg answer decides how much of precondition (1) is mandatory rather than elective |
| **R-8** officers | **A legal review** of the lawful-basis section (D-028 precondition 4) | A lawyer. Not an architect, and not this file | Nothing in the research library is legal advice and neither is D-028 |
| **R-6** Peppol | The authoritative **SMP/Directory endpoints**, their terms, and whether Digdir publishes a rate limit or expects registration at our volume | Digdir / DFØ documentation and one live resolution | A Directory-only implementation that reports a lagging index as authoritative — the exact disagreement the attachment exists to expose |

**Not blocked, start when the freeze lifts:** R-1, R-3, R-4, R-5.

---

## 3. R-1 — Batch lookup (D-024)

**`core/models.py`** — after `SearchResult` (`:782-832`), before the error section (`:835`);
add both names to `__all__` (`:32-51`):

```python
class BatchLookupItem(_Base):
    index: int                       # 0-based position in the caller's input list
    company_id: str                  # the identifier exactly as supplied
    report: CompanyReport | None = None   # exactly one of these two is populated
    error: ErrorBody | None = None        # D-007's inner object, reused verbatim

class BatchLookupResult(_Base):
    country: str                     # upper-cased by validator, like every other model
    registry: str
    requested: int
    succeeded: int
    failed: int
    results: list[BatchLookupItem] = []
    hint: str | None = None
```

No top-level `cached` / `fetched_at`: fifty rows can disagree and an aggregate would be a lie.

**`core/registry.py`** — a **concrete** builder beside `validate` / `deadline_report`
(`:188-252`), so the ABC stays four abstract methods wide and `registries/xx/` needs no edit:

```python
async def lookup_many(self, ids: Sequence[str], *, max_concurrency: int = 5) -> BatchLookupResult
```

Default implementation: dedupe on the normalised identifier for *fetching* only, run at most
`max_concurrency` in flight, catch `RegistryError` per item into `ErrorBody`, and emit rows in
the caller's input order including duplicates. A country whose upstream has a real multi-id
endpoint may override.

**Surfaces.** `mcp/server.py:260-304` — rename the parameter to `company_id` with
`validation_alias=AliasChoices("company_id", "id")`, widen to `str | list[str]`, and rebuild
the output schema as `TypeAdapter[CompanyReport | BatchLookupResult].json_schema()`.
`api/main.py` — `POST /v1/{country}/companies`, body `{"company_ids": [...]}`, beside
`get_company` (`:601-637`). No country module is edited.

**Done-check.**
1. `lookup_company("923609016")` output is **byte-identical** to the pre-change output;
   existing REST≡MCP parity tests pass unchanged.
2. A 50-id list with one malformed id, one non-existent id and 48 good ones returns HTTP 200,
   `requested=50 succeeded=48 failed=2`, rows in input order, the two failures carrying
   `error.code` `invalid_id` and `not_found` with non-empty hints.
3. 51 ids → `bad_request` whose hint names both the cap and the register's bulk download URL.
4. A duplicated id appears twice in `results` and once in the upstream request log.
5. With a warm cache, a 50-id batch of cached entities makes **zero** upstream requests and
   still returns 50 reports with `cached: true` and their original `fetched_at`.
6. The dereferenced union output schema is served intact and `content/call.py`'s
   `.structured_content` path parses both branches. **If it cannot be**: escalate to Opus A —
   D-024(i)'s fallback is a sixth tool plus an amendment to D-024, not a silent schema drop.

## 4. R-2 — `euid` and `advertising_protected` (D-026(a),(b))

**`core/models.py :: CompanyReport`**, identity block (`:555-568`) and contact block
(`:673-678`):

```python
euid: str | None = None                   # carried verbatim; NEVER constructed from parts
advertising_protected: bool | None = None # True = marked protected; False = flag published, not set;
                                          # None = this register publishes no such flag  ← the default
```

`euid`'s description must carry the three traps (EUID ≠ LEI; "EUid" also names the European
Digital Identity wallet; not stable across a register reorganisation).
`advertising_protected` must **never** default to `False`. A country module that sets it
`True` **must** also append a plain-English `notes` sentence stating the protection — the
CVR-loven § 19 marking has to reach a caller that reads only `notes`.

**Done-check.** Both keys present and `null` on every NO and GB report (D-004: always present,
never omitted); `registries/no/`, `registries/gb/` and `registries/xx/` unedited; a synthetic
report with `advertising_protected=True` and no matching `notes` entry fails a test;
`legal/terms.md` gains the passer-on sentence.

## 5. R-3 — Sub-national key (D-027)

**`core/models.py :: CompanyReport`**, identity block:

```python
subdivision: str | None = None        # ISO 3166-2, full prefixed form: "DE-BE", "US-DE"
register_office: str | None = None    # the register's own local name: "Amtsgericht Charlottenburg"
```

**`core/models.py :: CountryInfo`** (`:210-256`) gains `subdivisions: list[str] = []`;
**`core/registry.py :: Registry`** gains `subdivisions: ClassVar[tuple[str, ...]] = ()`,
defaulted exactly as `requires_api_key` was in D-017, and `country_info()` (`:312-332`) emits
it. `register()`'s two-letter enforcement (`:359-360`) is **unchanged**.

**Done-check.** `list_countries()` still returns `["NO", "GB"]` — never a subdivision code;
`GET /v1/countries` and MCP `list_countries` both carry `subdivisions: []` for both countries
and stay byte-identical to each other; `register()` still rejects a five-character code;
`registries/xx/` unedited.

## 6. R-4 — API keys and metering (D-030)

New `api/auth.py` resolving a request to `(key_id, tier)` or anonymous.
`api/ratelimit.py:82-112` takes both its bucket **key** and its **capacity** from that
resolution instead of always from `client_ip` (`:56`). `core/log.py:69-77` gains a `key_id`
column and `:135-175` writes it. `api/stats.py` aggregates per key.
`core/models.py` changes by exactly two lines: `ErrorCode.UNAUTHORIZED = "unauthorized"`
(`:109-141`) and its `401` row in `HTTP_STATUS` (`:876-886`). `core/registry.py` is untouched.

**Done-check.**
1. `uvx registry-mcp` stdio works with **no key and no environment variable**, and anonymous
   `POST /mcp` works with no header — both asserted by a test, because this is the invariant
   the whole entry is subordinate to.
2. Anonymous and keyed responses for the same lookup are **byte-identical**.
3. A 50-id batch records **50** metered units and **≤50** rate-limit tokens, fewer when the
   cache answered — the two meters differ, on purpose (D-024(g) versus D-030(f)).
4. `validate_company_id` and `list_countries` record **zero** metered units.
5. A revoked key returns 401 whose hint names the anonymous fallback; it does **not** silently
   degrade.
6. `?api_key=…` is refused with a hint naming the header.
7. `grep` of the call log, `/v1/stats`, `/dashboard` and every error body finds no key value —
   only `key_id`.

## 7. R-5 — `SourceRef`, `include=[…]`, and the LEI (D-026(c))

**`core/models.py`** gains `SourceRef` and `LeiRecord` (shapes in D-026(c)) and
`CompanyReport.lei: LeiRecord | None = None`.
**`mcp/server.py` / `api/main.py`** gain `include: list[str] = []` — a closed set validated
against the country module's declared capabilities, unknown value → `bad_request` naming the
allowed set, **never silently ignored**. Default `[]`: the base lookup stays one register, one
licence, one round trip.

The two-level nullability is the contract and must be tested as such: **absent block** = not
requested, or the fetch failed (with a `notes` sentence saying which); **present block with
`lei=None`** = GLEIF holds no LEI for this entity. GLEIF TTL is **7 days**, which is the first
user of the per-kind TTL table (`core/cache.py:84-94`) that R-8 also needs.

**Done-check.** `include=["lei"]` on an entity with an LEI returns a block whose
`provenance.license` is `"CC0 1.0"` and whose `provenance.source` names GLEIF; on an entity
without one, a present block with `lei: null`; with GLEIF unreachable, **no block** plus a
`notes` sentence, and the lookup itself still succeeds. `include=["nonsense"]` →
`bad_request` listing the allowed values. Default lookup makes exactly one upstream request.

## 8. R-6 — Peppol / ELMA capability (D-029)

`PeppolParticipant` (shape in D-029(b)) and `CompanyReport.peppol: PeppolParticipant | None`,
reached by `include=["peppol"]`. `participant_id` is `"0192:" + normalised orgnr`, derived
offline and **always populated**, even when the registration lookup fails.
TTL **24 h positive / 1 h negative**, reusing D-006's asymmetry for the same reason: from
1 January 2027 a stale negative makes a sender skip a statutory duty.
`registries/no/rules.py :: rules_markdown()` gains the prose — both dates, the exemptions
(turnover < NOK 50,000; finance, insurance, pensions), and the ELMA-scoping sentence with its
Prop. 44 L citation. **No `Deadline` is emitted for the 2027 duty** (D-029(f)).

**Done-check.** A known ELMA participant returns `registered: true` with `document_types`
non-empty and `provenance.source` naming which route answered; a non-participant returns
`registered: false`, not `null`; an unreachable SMP returns `registered: null` with
`participant_id` still populated and the lookup still succeeding.
`company_deadlines` for any Norwegian entity emits **no** e-invoicing deadline.
`grep -ri elma src/registry_mcp/core/` returns nothing (D-004: national vocabulary lives in
values, not names).

## 9. R-7 — NACE harmonisation (D-025) — *do the two reads first*

**`core/nace.py`** (new): `NACE_REV2: dict[str, str]` for the ~615 four-digit classes, module
constants recording revision + source URL + download date + licence, and:

```python
def nace_class(code: str) -> tuple[str, str] | None:
    """Strip non-digits, take the first four, format "NN.NN".
    Return (class, label) ONLY if it is a key of NACE_REV2 — else None."""
```

**`core/models.py :: IndustryCode`** (`:189-202`) gains `nace_code` and `nace_description`,
both `str | None = None`. `code`, `description` and `scheme` are **never** overwritten.
`registries/no/mapping.py:150-165` and `registries/gb/mapping.py:118-125` call the helper;
Norway additionally corrects `scheme` to `"SN2007"`, with the `NORBIZ_SPEC.md` §2 row and any
test pinning `"NACE"` updated in the same change.

**Done-check.** `06.100` (NO) and `47110` (GB) both derive `06.10` / `47.11` with identical
English labels, so a cross-country comparison is a string equality; every UK company that had
`description: null` now has a `nace_description`. The three CH administrative codes `99999`,
`98000` and `74990` derive `nace_code: null` — **not** `99.99` / `98.00` / `74.99`; a test
asserts each. `core/nace.py`'s recorded licence matches whichever source survived §2's read.

## 10. R-8 — Officers and PSC (D-028) — *four preconditions, then a model*

**Do not open this item until all four are satisfied and recorded in `PROGRESS.md`:**
(1) company→officers only, never person→companies — a design rule, enforced by the absence of
any name-keyed route or tool; (2) a per-kind cache TTL of **1 hour** for `officers` / `psc`,
with `REGISTRY_MCP_CACHE_TTL_SECONDS` (`core/cache.py:45`) **clamping** rather than overriding
it; (3) `suppressed: bool | None` plus `suppressed_fields`, with `None` the honest value until
the CH signalling question in §2 is settled; (4) the lawful-basis section in `legal/terms.md`,
lawyer-reviewed.

Then `CompanyOfficer` + `OfficerBlock` (shapes in D-028(5)), a **concrete**
`Registry.officers(id)` raising `not_implemented` by default, `include=["officers"]`, and the
REST twin `GET /v1/{country}/company/{id}/officers` returning the identical block from the
identical builder. GB PSC ships before Norwegian beneficial owners; Norway's absence is a
structured `not_implemented` (501) naming Maskinporten and the register's own portal, never a
silent gap. The **PSC ≠ shareholders** caveat appears in the field descriptions *and* in
`notes`.

**Done-check.** No route, tool, argument or resource anywhere accepts a person's name;
`grep -rn "search_officer\|officer_search\|appointments" src/` is empty. A person record's
cache row expires in ≤1 hour with `REGISTRY_MCP_CACHE_TTL_SECONDS=604800` set. A GB officer
whose suppression state is unknown emits `suppressed: null` and a `notes` sentence, never
`false`. `include` absent → no officer data anywhere in the response. `legal/terms.md` names
the categories, the basis, and the retention number.

---

## 11. What this file deliberately does not schedule

Carried over from `research/07-product-improvements.md`'s declined list and restated here so
nobody re-proposes them without new evidence: **sanctions/PEP screening** (build the join key,
say loudly that we do not screen); **webhooks** (needs auth and subscription state, and MCP
removed server-initiated pushes in 2026-07-28, so it would be a REST-only feature that does
not extend the MCP story — a *polled* "what changed since?" delivers most of the value);
**OAuth 2.1** before a customer asks (R-4's Bearer header is the migration path);
**UK iXBRL parsing** (L, permanent maintenance, real risk of publishing a wrong number —
D-009 rules it out); **Norwegian beneficial owners** (Maskinporten is organisational, and the
credential could never ship in `uvx registry-mcp`); **hosting a bulk snapshot** (point at the
register's own, in an error `hint` — R-1 does exactly that); and **renaming the five tools**.

One item is *not* on this list and should be reconsidered on its own merits once R-4 is
producing numbers: a **change-feed consumer for cache invalidation**. It is invisible to the
API contract, changes no model, adds no tool, can be switched off, and is the strongest
available answer to the "your data is 24 hours old" attack — but its value over a flat 24 h
TTL is unquantified, and the free change feeds are themselves the cheapest way to measure it.
Consume for a week and count before deciding.
