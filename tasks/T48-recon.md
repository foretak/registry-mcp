# T48-recon — Peppol / ELMA: the four facts D-045(f) says R-6 cannot be briefed without

Owner: Opus (T48). Everything below fetched **2026-09-08** (UTC), keyless, from a plain `curl`/DoH client with
no Peppol certificate, no account and no key. Brief: `tasks/T48.md`. Rules it answers: **D-029** (shape, TTL,
`provenance.source` names which route answered) and **D-045(f)** items 1–4. Roadmap slot: `CORE_ROADMAP_SPEC.md`
§8 (R-6), blocked in §2.

Tags: **[fetched]** read off the wire in this session · **[search]** from a search result or a secondary page
· **[repo]** read in this repository. Every URL is listed in the last section.

**How it was obtained** (reusable). All three routes answer anonymously over the public internet. The SML step is
**DNS**, not HTTP, and this machine has no `dig`/`host`/`nslookup` and no `dnspython`; NAPTR was therefore read
through Google's DNS-over-HTTPS JSON endpoint (`https://dns.google/resolve?name=…&type=NAPTR`, `accept:
application/dns-json`). That substitution is itself a finding — see the verdict. Volume this session: **17
Peppol Directory queries** (ceiling is 2/s — every batch was serialised with a 0.6 s sleep), **~50 NAPTR
resolutions**, **4 SMP GETs** against 2 different SMPs. No call to `api.foretak.dev`, Companies House or
Bolagsverket; `833286602`/`833285602` never queried.

---

## Fact 1 — the SMP resolution route for a `0192:` participant

**It is a two-step DNS-then-HTTPS walk, and both steps are keyless.** [fetched]

**Step 1 — SML/BDXL.** Build `<base32(sha256(lowercased participant id))>.<schemeID>.<SML domain>` and read its
**U-NAPTR** record. Verbatim from *Peppol Service Metadata Locator (SML) v1.3.0*, valid from 2025-11-01 (text
extracted from the published PDF): [fetched]

> "a hash of the lowercased participantID is always used, using the SHA-256 hash algorithm … The obtained digest
> is Base32 encoded and any eventually trailing `=` characters MUST be removed."

> "`<hash over recipientID>.<schemeID>.<SML domain>`" … "The sender performs a DNS U-NAPTR record lookup with the
> domain name created in the previous step and extracts the base URL for the effective SMP query incl. the URL
> scheme." … "The NAPTR service name MUST be `Meta:SMP`. Other service names MUST NOT be used in relation to this
> specification."

The hash is over the **identifier value only** (`0192:923609016`), *not* over `iso6523-actorid-upis::0192:923609016`
— the scheme is a separate DNS label. Self-checked against the spec's own worked example: `0010:5798000000001` →
`XUKHFQABQZIKI3YKVR2FHR4SNFA3PF5VPQ6K4TONV3LMVSY5ARVQ`, reproduced byte-for-byte. [fetched]

**The live Equinor resolution.** `0192:923609016` → SHA-256 → base32 →
`XQK4T3FMTEZDUY5BOVJMTNAQ45N7E4TIBYHWFPGOT75BSP7UYG2A`.

```
QUERY   NAPTR XQK4T3FMTEZDUY5BOVJMTNAQ45N7E4TIBYHWFPGOT75BSP7UYG2A.iso6523-actorid-upis.participant.sml.prod.tech.peppol.org
ANSWER  100 10 U Meta:SMP !.*!https://smp.elma-smp.no/! .      (TTL 60)
```

Order 100, preference 10, flag `U` (terminal URI), service `Meta:SMP`, regexp `!.*!<base URL>!`, replacement `.`.
The base URL is the whole payload — apply the regexp or just take the substring between the second and third `!`.
[fetched]

**Step 2 — the SMP.** `GET <base URL>/<percent-encoded participant id>` returns the **ServiceGroup** XML.

```
GET https://smp.elma-smp.no/iso6523-actorid-upis%3A%3A0192%3A923609016
→ HTTP 200, text/xml, 5913 bytes
<ns2:ServiceGroup …><ParticipantIdentifier scheme="iso6523-actorid-upis">0192:923609016</ParticipantIdentifier>
  <ns2:ServiceMetadataReferenceCollection>
    <ns2:ServiceMetadataReference href="https://smp.elma-smp.no/iso6523-actorid-upis%3A%3A0192%3A923609016/services/busdox-docid-qns%3A%3Aurn%3Aoasis%3Anames%3Aspecification%3Aubl%3Aschema%3Axsd%3AInvoice-2%3A%3AInvoice%23%23urn%3Acen.eu%3Aen16931%3A2017%23compliant%23urn%3Afdc%3Apeppol.eu%3A2017%3Apoacc%3Abilling%3A3.0%3A%3A2.1"/>
    … 16 more …
```

**No client certificate, no TLS mutual auth, no token.** A bare `curl` gets 200. [fetched] The Peppol certificate
appears only *inside* the answer, as an XMLDSig signature over each ServiceMetadata — an optional integrity check
for a reader, never an entry requirement. Equinor's is signed
`CN=PNO000179,OU=PEPPOL PRODUCTION SMP,O=The Norwegian Digitalisation Agency,C=NO`, which is how one *proves* the
answer came from Digdir rather than asserting it. [fetched]

**Negative path, all three routes, measured on a synthetic MOD11-valid orgnr `0192:999999999`** (synthetic
deliberately: it exercises the path without looking up any real company): [fetched]

| Route | Response |
|---|---|
| SML NAPTR | **NXDOMAIN** (`Status: 3`). This *is* the answer: not registered anywhere in Peppol. |
| ELMA SMP direct | **HTTP 404**, `text/xml`, body is an XML comment: `message : Could not find participant 'iso6523-actorid-upis::0192:999999999'`, `exception : network.oxalis.vefa.peppol.publisher.lang.NotFoundException` |
| Peppol Directory | **HTTP 200**, `{"total-result-count":0,…,"matches":[]}` — never a 404 |

**Which does Digdir recommend for a lookup?** Digdir — the operator of ELMA — rules on it in one sentence, and it
is the single most important quote in this recon (`docs.digdir.no/docs/ELMA/elma_open_data`, updated 19.09.2024):
[fetched]

> "**NB! These datasets must not be used to check if a given norwegian organization is registered in PEPPOL or what
> documents an organization can receive. This should be done via a lookup via the SML (Service Metadata Locator).**"

> "**The only valid way to lookup an organization is the PEPPOL way of lookup via the SML.**"

> "Previously, ELMA was the only PEPPOL SMP where norwegian organizations were registered. **This is no longer the
> case. A norwegian organization may be registered to an other SMP. A lookup only in ELMA is no longer a valid way
> to lookup norwegian organizations in PEPPOL.**"

> "It is also possible to lookup organizations via PEPPOL Directory. **It is currently not mandatory for SMPs to
> publish information to PEPPOL Directory, so the list there is not complete.**"

So D-029(d) is confirmed by the source it was guessing at: SML→SMP is authoritative, the Directory is a lagging
index. D-029(d)'s three DFØ routes are all *browser tools* — the Peppol Directory
(`directory.peppol.eu/public`), DFØ's own `anskaffelser.dev/service/lookup/` and `lookup.peppol.org`. [fetched]
**`anskaffelser.dev` publishes no machine API** — it is a UI over the same SML walk and must not be treated as an
endpoint. [fetched]

### ⚠ The DNS zone moved, and the old one dies this month

- **Production SML zone is now `participant.sml.prod.tech.peppol.org`** (test: `participant.sml.test.tech.peppol.org`);
  management API `https://api.sml.prod.tech.peppol.org/edelivery-sml/`. It replaces the EC-operated
  `edelivery.tech.ec.europa.eu` / `acc.edelivery.tech.ec.europa.eu`. [search: OpenPeppol "SML Insourcing"]
- Both answered identically at **2026-09-08T21:05Z** — the old EC zone still resolves Equinor to
  `https://smp.elma-smp.no/`. [fetched] It is living on borrowed time: the AP deadline for moving lookups was
  **31 August 2026** (passed), and decommissioning of the old participant-lookup URLs is *"likely happening during
  September"* at the Commission's discretion. [search]
- **CNAME is dead.** `B-<md5(lowercased participant id)>.<scheme>.<zone>` returns **NXDOMAIN on both zones** —
  tested with the md5 of the value (`88c037cc…`) and of the full qualified id (`22b8137d…`), on
  `edelivery.tech.ec.europa.eu`, `acc.edelivery.tech.ec.europa.eu` and `peppolcentral.org`: 0 hits out of 6.
  [fetched] The SML v1.3.0 changelog says why: *"Switching from CNAME to U-NAPTR DNS records"*, *"Removed the CNAME
  Wildcard option"*. [fetched] CNAME was fully deprecated **1 February 2026**, the same date SMPs became
  HTTPS-only. [search] `http://smp.elma-smp.no/…` returns **503**. [fetched]

Every pre-2025 tutorial, blog post and library README describes the `B-<md5>` CNAME form against
`edelivery.tech.ec.europa.eu`. Both halves of that sentence are now wrong.

---

## Fact 2 — the Peppol Directory's query endpoint and response shape

**Endpoint** (`directory.peppol.eu/public/menuitem-docs-rest-api`, verbatim): [fetched]

> "The basic URL to query is `/search/1.0/`*format* where "format" can be one of `xml` or `json` … Only HTTP GET
> requests are accepted. Other HTTP verbs are rejected with HTTP status code 405."

> "The usage of the REST API is rate limited. **You are only allowed to run 2 queries per second.** If you are not
> following the instructions, the HTTP Status code 429 (Too Many Requests) is returned."

> "If the combination of query parameters resulted in an empty search result, an HTTP status code **200 with an
> empty result body** is returned!"

The lookup we want is `participant=`, and the docs are explicit that the **scheme must be part of the value**
(`iso6523-actorid-upis::0192:923609016`); a value that will not parse as a participant identifier is *silently
ignored*, and if it was the only term the request 400s. Full parameter set: `q`, `participant`, `name`, `country`,
`geoinfo`, `identifierScheme`, `identifierValue`, `website`, `contact`, `addinfo`, `regdate`, `doctype`,
`resultPageIndex`/`rpi`, `resultPageCount`/`rpc` (default 20). [fetched]

**Live request and response, trimmed** (this is a company's public participant record — nothing redacted):

```
GET https://directory.peppol.eu/search/1.0/json?participant=iso6523-actorid-upis::0192:923609016
→ HTTP 200, application/json;charset=UTF-8

{"version":"1.0","total-result-count":1,"used-result-count":1,"result-page-index":0,
 "result-page-count":20,"first-result-index":0,"last-result-index":0,
 "query-terms":"participant=iso6523-actorid-upis::0192:923609016",
 "creation-dt":"2026-09-08T20:53:31.064151933Z",
 "matches":[{
   "participantID":{"scheme":"iso6523-actorid-upis","value":"0192:923609016"},
   "docTypes":[
     {"scheme":"busdox-docid-qns","value":"urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1"},
     … 11 more … ],
   "entities":[{"name":[{"name":"EQUINOR ASA"}],"countryCode":"NO",
                "websites":["www.equinor.com"],"regDate":"2019-03-18"}]}]}
```

**Do Norwegian ELMA participants appear? Yes, in bulk.** `country=NO` reports **385,268** indexed participants
(SE 160,138; GB 21,765 for scale). [fetched] The Directory aggregates *from* SMPs, so ELMA's registrations flow
into it — but not automatically and not completely.

### ⚠ The Directory cannot produce `registered: false`

Two statements, one from each operator, and they say the same thing. Directory's own Introduction page: [fetched]

> "Currently the publication of Peppol participant information in an SMP happens **on a voluntary basis**. That
> implies that not all business entities are listed in the Peppol Directory which implies that **if your desired
> partner does not show up in here it doesn't mean that the entity is not in the Peppol Network!**"

> "On the other hand **if an entity shows up in the Peppol Directory you can be sure that the participant is a
> participant of the Peppol Network.**"

DFØ, same point, in Norwegian: *"Det er ikke obligatorisk å legge inn en mottaker så i noe tilfeller kan det være
at du ikke finner virksomheten du søker etter."* [fetched]

The Directory is therefore **sound for a positive and unsound for a negative**. It is a legitimate fallback for
`registered: true`, and a Directory miss must map to `registered: null`, never `false`. D-029(b) says
*"`registered=False` is an honest value here … an authoritative SMP resolution that finds no participant is a
definite 'not reachable on the network'"* — true, and true **only of the SML/SMP route**. See the verdict.

**The lag is real and measurable.** Equinor's SMP advertises **17** document types; the Directory lists **12**.
The five missing are all logistics profiles (advanced despatch advice, transport execution plan, transport
execution plan request, transportation status, waybill); nothing is in the Directory that is not in the SMP.
[fetched] The lag is not universal — GLOBUS AS (`0192:927650487`) matches exactly, 2 = 2 [fetched] — which is
worse for a caller, not better: you cannot tell from the Directory whether you are looking at a fresh copy.

**Other measured limits.** [fetched]
- Paging is capped: `rpi`/`rpc` combinations whose first **or** last result index exceeds **1000** return
  HTTP 400 (`"The first result index 4500 is invalid. It must be <= 1000."`). `total-result-count` of 385,268 is
  therefore not enumerable through search — the bulk export is (`/export/businesscards-json`, redirect that MUST
  be followed and MUST NOT be cached, gzip mandatory, **2 downloads per file per 24 h per IP**, data rebuilt daily
  from 02:00 UTC, `HEAD` for the ETag is cheap).
- Only **receiving** capabilities are indexed: *"The current administrative policy of the Peppol Network requires
  that only Document Receiving capabilities of Peppol participants are registered on the network."* That is the
  right semantics for the 2027 duty — "can this counterparty *receive*" is exactly the question — and it should be
  said in `notes` rather than left implicit.

---

## Fact 3 — terms, licence and rate limits

| Source | Public keyless? | Rate limit | Licence |
|---|---|---|---|
| SML DNS (`participant.sml.prod.tech.peppol.org`) | yes, public DNS | **none published** | none stated |
| SMP (`smp.elma-smp.no`, and any other) | yes, HTTPS GET, no cert | **none published** | none stated |
| Peppol Directory REST | yes | **2 queries/second**, else 429 | none stated; a Privacy Policy applies |
| Peppol Directory bulk export | yes | 2 downloads/file/24 h/IP | as above |

All four cells re-verified live. [fetched]

**ELMA's lookup interface is public — and it is not ELMA's own interface.** Digdir's "Om Elma" page grants nothing
to readers; its only access sentence is about *writing*: *"Using ELMA is free of charge for approved access points
in the OpenPEPPOL network. Approved access points may get access by sending an e-mail to servicedesk@digdir.no."*
[fetched] Reading is not gated at all, because reading is a Peppol-network SMP query, not an ELMA product.
Digdir's ELMA docs publish **no terms of use, no rate limit and no licence for the lookup path**; the only usage
rule Digdir states anywhere is the prohibition quoted in Fact 1 — *don't use the datasets for this, use the SML*.

**There is no NLOD statement, and no licence at all.** ELMA is catalogued on data.norge.no as *"Mottakere i ELMA"*
/ *"Participants in ELMA"*, publisher Digitaliseringsdirektoratet, access level **"Allmenn tilgang"** ("Offentlig
tilgjengelig for alle"), distribution = the Peppol Directory (json, xml), last updated 7 November 2025 —
**Lisens: "Ikke oppgitt"** (not stated). [fetched] This is a real gap for `SourceRef.license`, and it is the one
D-045(f) item 3 warned about. Digdir's current house recommendation for *new* open datasets is CC BY 4.0 or CC0,
not NLOD [search] — but that is a recommendation Digdir has not applied here, and quoting it as ELMA's licence
would repeat exactly the mistake `tasks/T26-recon.md` refused to make with Bolagsverket ("Quote the regime; do not
name a licence").

**The one binding restriction found anywhere is in the Directory's Privacy Policy**, and it bites on one field
only: [fetched]

> "Any personal data in the Directory may only be used insofar as this is necessary to ensure the correct,
> effective and secure operation of the Peppol Network. Under this policy, the Operators only permit access to
> personal data in the Directory **by persons who are contractually authorised by at least one of the Operators to
> use the Peppol Network. These are the only permitted recipients of personal data under this policy.**"

registry-mcp is not a contractually authorised Peppol user. The Directory's `contact` block is the only place
personal data lives (the docs describe it as "type, name, phone number and email address"). `participantID`,
`docTypes`, `name`, `countryCode`, `websites` and `regDate` are company data. **Read `contact`, relay never** —
and never populate it into any model. Nothing in the SML or SMP path carries personal data at all, which is one
more argument for making that path primary.

**Statutory framing is unchanged and re-confirmed** (D-029, `~/research/registry-mcp/03-regulation-drivers/06-…md`):
1 January 2027 duty to send, 1 January 2030 to receive and to keep books electronically; exemptions for turnover
< NOK 50,000 and for *finansvirksomhet, forsikringsselskaper og pensjonsforetak*; the scoping sentence is against
counterparties *"registrert i Elektronisk mottakerregister (ELMA)"*. [repo]

### ⚠ D-029(a)'s supporting quote no longer exists

D-029(a) rests its "the two registers can disagree" argument on DFØ conceding *"ELMA-registeret har ikke oppdatert
informasjonen fra adresseregisteret"*. **That sentence is gone** from the DFØ page as revised **14 August 2026** —
0 hits for `oppdatert informasjonen` in the live HTML. What the page says now is a different lag in a different
direction: [fetched]

> "Peppol Directory har ikke registret eller endret informasjon tilsendt fra adresseregister (SMP eller kjent som
> ELMA i Norge)."

i.e. **the Directory lagging the SMP**, not ELMA lagging Enhetsregisteret. D-029(a)'s *conclusion* survives intact
and is now better evidenced — by the measured 17-vs-12 diff above, which is a Directory-vs-SMP disagreement, and by
the fact that ELMA and Enhetsregisteret remain different registers under different operators. Only the citation
needs replacing. Do not quote the old sentence in `notes` or in `rules_markdown()`.

---

## Fact 4 — what `document_types` actually contains

**Document type identifiers, and only those — process identifiers live one HTTP call deeper.** [fetched]

The ServiceGroup and the Directory both return **document type identifiers**, in
`<scheme>::<value>` form with scheme `busdox-docid-qns` or `peppol-doctype-wildcard`. The **process identifier**
appears only in the per-document-type **ServiceMetadata**:

```
GET https://smp.elma-smp.no/iso6523-actorid-upis%3A%3A0192%3A923609016/services/busdox-docid-qns%3A%3A…billing%3A3.0%3A%3A2.1
→ HTTP 200

<DocumentIdentifier scheme="busdox-docid-qns">urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1</DocumentIdentifier>
<ProcessIdentifier scheme="cenbii-procid-ubl">urn:fdc:peppol.eu:2017:poacc:billing:01:1.0</ProcessIdentifier>
<ns2:Endpoint transportProfile="peppol-transport-as4-v2_0">
  <ns3:Address>https://ectrade.ec.evry.com/peppol/as4</ns3:Address>
  <ns2:ServiceActivationDate>2026-03-12T01:00:00.000+01:00</ns2:ServiceActivationDate>
  <ns2:ServiceExpirationDate>2028-03-01T00:59:59.000+01:00</ns2:ServiceExpirationDate>
  <ns2:ServiceDescription>TietoEvry Standard</ns2:ServiceDescription>
```

**Note what this means for the brief.** `tasks/T48.md` lists `urn:fdc:peppol.eu:2017:poacc:billing:01:1.0` as a
`document_types` candidate. **It is not a document type — it is the *process* identifier**, scheme
`cenbii-procid-ubl`, and it is invisible from the ServiceGroup. Harvesting process ids would cost **one extra HTTP
request per document type** — 17 more for Equinor. `document_types` should be document type identifiers, full
qualified `<scheme>::<value>` strings, from the one ServiceGroup call. D-029(b)'s `list[str]` is the right type;
it is usable, not decorative.

**Which one means "can receive an EHF invoice".** DFØ answers it in five words: [fetched]

> "**Peppol BIS billing v3.0 er det samme som EHF-faktura.**"

So the string that carries the 2027 answer is exactly:

```
busdox-docid-qns::urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1
```

with the PINT successor `peppol-doctype-wildcard::urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##urn:peppol:pint:billing-1::2.1`
appearing alongside it in a minority of records. Counted across the Directory: [fetched]

| Query (`country=NO` +) | `total-result-count` | share |
|---|---|---|
| — (all NO participants) | **385,268** | 100 % |
| BIS Billing 3.0 **Invoice** (= EHF faktura) | **384,834** | **99.89 %** |
| BIS Billing 3.0 CreditNote | 384,828 | 99.88 % |
| PINT Billing Invoice (wildcard) | 12,948 | 3.4 % |

**How many does a typical participant list? Two.** Over a 500-participant sample (Directory `country=NO`, pages
0–4 at 100/page): [fetched]

| `docTypes` | participants | share |
|---|---|---|
| 2 | 447 | **89.4 %** |
| 3 | 44 | 8.8 % |
| 4 | 7 | 1.4 % |
| 7 | 1 | 0.2 % |
| 26 | 1 | 0.2 % |

median **2**, mean **2.17**. The modal Norwegian participant lists Invoice + CreditNote and nothing else.
Equinor's 17 is a far-tail case, and the `26` proves the list can be long — do not cap or truncate it.

`ServiceActivationDate`/`ServiceExpirationDate` are **per document type and invisible from the ServiceGroup**. A
document type listed in the ServiceGroup may be dated in the future or already expired. That is a real caveat on
"can receive", and it belongs in `notes`, not in a filter — filtering would require 17 extra calls to answer a
question D-029 did not ask.

---

## Verdict

**Buildable now — but D-029 needs a four-line amendment, and one dependency question needs an owner.**

Nothing is unreachable and nothing needs a key. All four D-045(f) facts are settled. What is *not* settled by
D-029 as written:

**(1) `registered: false` is only earnable on the SML/SMP route.** D-029(b) says `False` "is an honest value here"
and D-029(d) allows the Directory as a fallback. Composed, those two sentences license a Directory miss to be
reported as `registered: false` — and both operators say in writing that a Directory miss means nothing.
**Amendment needed to D-029(b)/(d):** the Directory may answer `registered: true` and populate `document_types`;
a Directory miss is `registered: null` with a `note`. Only NXDOMAIN on the SML, or a 404 from the SMP the SML
named, earns `false`. This is the one substantive correction in this recon.

**(2) `provenance.source` must name the SMP that answered, not "ELMA".** D-029(a) states ELMA is the Norwegian
SMP; Digdir states that is no longer sufficient. Measured: of **43** Norwegian participants resolved,
**42 → `https://smp.elma-smp.no/`** and **1 → `https://smp.conta.no`** (`0192:837056942`, *Hornnes
Håndverkstjenester*, which serves its ServiceGroup keyless exactly like ELMA). [fetched] ~2 % of a small sample,
and Digdir says to expect it. D-029(d)'s "name which route answered" should read **"name which route *and which
SMP* answered"** — `smp_url` already carries the host, so this is a wording fix plus a rule that
`provenance.source` is derived, never a constant.

**(3) The SML step needs a DNS resolver this project does not have.** [repo] `pyproject.toml` declares five
runtime dependencies — `pydantic`, `httpx`, `fastapi`, `uvicorn[standard]`, `fastmcp` — and `grep -rn
"dnspython\|NAPTR\|resolver" src/` returns **nothing**. Python's stdlib cannot read a NAPTR record. So R-6 needs
either a new runtime dependency (`dnspython`) or DNS-over-HTTPS through the existing `httpx` (which is what this
recon used, and which puts a third-party resolver — Google or Cloudflare — inside the trust path of a statutory
answer, and inside the provenance chain). **That is an architect's call, not an implementer's**, and D-029 does
not make it. It is the only thing standing between here and a `tasks/T43.md`.

**(4) The TTL is ours alone.** Both upstreams tell caches not to store: SMP sends `cache-control: no-cache,
no-store, max-age=0, must-revalidate`, Directory sends `no-cache, no-store, must-revalidate, proxy-revalidate`,
and the **NAPTR TTL is 60 seconds**. [fetched] D-029(e)'s 24 h / 1 h is defensible as *our* policy for *our*
answer, but it is 1,440× the SML's own TTL for the SMP binding, and no upstream endorses it. Cache the composed
`PeppolParticipant`, never the NAPTR→SMP binding; say in the docstring that the TTL is registry-mcp's policy and
that neither upstream publishes one.

Everything else in D-029 survives contact with the wire unchanged: the `include=["peppol"]` mechanism,
`PeppolParticipant`'s five fields, `participant_id` derivable offline as `"0192:" + normalised orgnr`, the refusal
to emit a `Deadline`, and the §8 done-check as written (a known participant returns `registered: true` with a
non-empty `document_types`; a non-participant returns `false`; an unreachable SMP returns `null` with
`participant_id` still populated).

### What R-6's brief can now state as fixed

| | |
|---|---|
| Step 1 | `NAPTR <base32(sha256(lower(pid_value)))>.iso6523-actorid-upis.participant.sml.prod.tech.peppol.org`, take the URI between `!.*!` and `!` from the `Meta:SMP` record |
| Step 2 | `GET <base>/iso6523-actorid-upis%3A%3A0192%3A<orgnr>` → ServiceGroup XML → collect `ServiceMetadataReference/@href`, split on `/services/`, percent-decode → `document_types` |
| Fallback | `GET https://directory.peppol.eu/search/1.0/json?participant=iso6523-actorid-upis::0192:<orgnr>` → `matches[0].docTypes[].{scheme,value}` joined `scheme::value`. **Positive answers only.** ≤ 2 req/s. |
| `registered` | `true` = ServiceGroup 200 (or a non-empty Directory match) · `false` = NAPTR NXDOMAIN, or SMP 404 · `null` = anything else, incl. a Directory miss |
| `smp_url` | the NAPTR base URL, verbatim |
| `provenance.source` | derived: the SMP host + "(via Peppol SML)", or "Peppol Directory (index; may lag)" |
| `provenance.license` | **none stated by anyone.** Do not write "NLOD", do not write "CC BY". Describe the regime, as `tasks/T26-recon.md` did for Bolagsverket |
| EHF invoice | `busdox-docid-qns::…Invoice-2::Invoice##urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0::2.1` — DFØ: *"Peppol BIS billing v3.0 er det samme som EHF-faktura."* |
| TTL | D-029(e) 24 h / 1 h, on the composed answer only; NAPTR TTL is 60 s and no upstream publishes a cache policy |

### The one trap

**Hardcoding a host — either of the two.** The trap has two mouths and they close on the same mistake:

1. **Hardcoding `smp.elma-smp.no`.** It works for 42 of 43 Norwegian participants tested, which is precisely why
   an implementer will do it, and why the tests will pass. Digdir says in writing that it is invalid, and the
   1-in-43 (`0192:837056942` → `smp.conta.no`) proves it. A hardcoded ELMA host reports `registered: false` for a
   company that *is* registered — the worst possible failure for a 2027 statutory answer, and the inverse of the
   one D-045(f) predicted.
2. **Hardcoding `edelivery.tech.ec.europa.eu`, or the `B-<md5>` CNAME form.** Every pre-2025 example on the
   internet uses one or both. The CNAME form already returns NXDOMAIN everywhere (0/6 tested). The EC zone still
   answered on 2026-09-08 and is scheduled for decommissioning *this month*. Code written from a tutorial will
   pass review, pass tests, and stop working somewhere between now and October with an NXDOMAIN that looks exactly
   like "not registered".

The rule that closes both: **the SMP base URL is data, read fresh from the NAPTR, never a constant** — and note
that ELMA's NAPTR URI ends in `/` while Conta's does not, so join with care.

---

## Could not be established

1. **A published rate limit for the SML DNS or for any SMP.** Neither Digdir, nor OpenPeppol's SML spec, nor the
   ELMA pages state one. Absence of a stated limit is not permission; the Directory's 2/s is the only published
   number and is the sane default to build to.
2. **The exact decommissioning date of `edelivery.tech.ec.europa.eu` for lookups.** OpenPeppol says "likely
   happening during September" at the Commission's discretion — no date. [search] Not load-bearing if the new zone
   is used, which it must be.
3. **A licence for ELMA/Peppol Directory data.** data.norge.no says **"Ikke oppgitt"**. No NLOD statement, no CC
   statement, nothing on Digdir's or OpenPeppol's pages. Escalate to `HUMAN_TODO.md` if `SourceRef.license`
   requires a non-empty value; otherwise describe the regime.
4. **Whether `smp.conta.no` is representative of a class or a one-off.** n=43, one non-ELMA host. The Directory
   caps search paging at result index 1000, so a larger unbiased sample needs the bulk export (2 downloads/24 h) —
   out of scope for a recon, and the conclusion ("do not hardcode") does not change with the number.
5. **Whether a Norwegian participant can exist in the SML but be absent from *every* SMP's ServiceGroup** — i.e.
   whether NAPTR-resolves-but-SMP-404 is reachable in production. Not observed; the synthetic negative NXDOMAINed
   at step 1. The state must still be handled (it is the `false`-from-404 branch above).
6. **Number of Norwegian EHF receivers as published by DFØ.** The guide links a statistics page
   ("Se antall mottakere EHF og Peppol BIS"); the URL guessed for it 404s and the link target was not extracted.
   The Directory's own 385,268 / 384,834 are counted first-hand and are better evidence anyway.
7. **Whether the ELMA SMP applies any per-IP throttling in practice.** 4 sequential GETs is not a test.
8. **`anskaffelser.dev`'s data source and any API behind its UI.** No machine documentation found; treated as a
   browser tool only.

---

## Every URL fetched (2026-09-08)

**Live data**
- `https://dns.google/resolve?name=<hash>.iso6523-actorid-upis.participant.sml.prod.tech.peppol.org&type=NAPTR` — ~50 resolutions
- `https://dns.google/resolve?name=<hash>.iso6523-actorid-upis.edelivery.tech.ec.europa.eu&type=NAPTR` — old zone, still live
- `https://smp.elma-smp.no/iso6523-actorid-upis%3A%3A0192%3A923609016` (and `…%3A927650487`, `…%3A999999999`)
- `https://smp.elma-smp.no/iso6523-actorid-upis%3A%3A0192%3A923609016/services/busdox-docid-qns%3A%3A…billing%3A3.0%3A%3A2.1`
- `https://smp.conta.no/iso6523-actorid-upis%3A%3A0192%3A837056942`
- `https://directory.peppol.eu/search/1.0/json?participant=…` / `?country=NO…` / `?country=NO&doctype=…` — 17 queries

**Documentation and terms**
- `https://docs.digdir.no/docs/ELMA/` · `…/elma_elma` · **`…/elma_open_data`** (the decisive page)
- `https://www.anskaffelser.no/verktoy/veiledere/mottakere-av-ehf-og-peppol-bis` (updated 14. august 2026)
- `https://anskaffelser.dev/service/lookup/`
- `https://directory.peppol.eu/` (Privacy Policy) · `/public/menuitem-docs-rest-api` · `/public/menuitem-docs-introduction` · `/public/menuitem-docs-export-all`
- `https://data.norge.no/datasets/5a5374c3-c6a7-49f8-b9cc-0a9e48c1acd7` ("Mottakere i ELMA", Lisens: Ikke oppgitt)
- `https://docs.peppol.eu/edelivery/` and `…/sml/Peppol-EDN-Service-Metadata-Locator-1.3.0-2025-02-06.pdf`
- `https://openpeppol.atlassian.net/wiki/spaces/PTPUB/pages/5059608580/SML+Insourcing` [search]
- `https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/blog/2026/05/16/967115567/…` [search]

**Repository** [repo]: `DECISIONS.md` D-029, D-045(f) · `CORE_ROADMAP_SPEC.md` §2, §8 · `pyproject.toml:75-81` ·
`src/registry_mcp/registries/no/__init__.py:37` · `~/research/registry-mcp/03-regulation-drivers/06-norway-mandatory-e-invoicing-2027-and-digital-bookkeeping-2030.md`
