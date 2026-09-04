# UK_SPEC — the United Kingdom module (`registries/gb/`)

Technical specification for the UK module of `registry-mcp`, the **second** country and the first
test of D-001's claim that a country is one folder plus one import line.

**Status:** written by Opus A in T15a, from the Companies House developer specification, GOV.UK
statutory guidance, and — from 2026-09-04, once a REST key arrived mid-task — **sixteen live API
responses**, saved as fixtures under `tests/fixtures/ch_*.json`. Authoritative for T15b.

**How to read the markers** — same convention as `NORBIZ_SPEC.md`:

| Marker | Meaning |
|---|---|
| *(no marker)* | Confirmed against a documented source, or against one of the live payloads of §1.4, on 2026-09-04. |
| `VERIFY` | Not yet confirmed against reality. T15b confirms it before the mapping is final. **If verification fails, the item is dropped, not guessed.** |
| `DEFERRED` | Real but deliberately out of scope for T15b. Do not implement. |

Almost every marker that this file carried in draft has been resolved against live JSON. The ones
that remain are listed in §1.7, and there are five of them.

> **The live payloads contradicted the published schema in eight places.** Read §1.6 before writing
> `mapping.py`; two of them would have produced a wrong answer rather than a crash.

Everything here is British. Nothing here may be imported into `core/` (D-001). Where this file says
`core/…` or `registries/…`, read `src/registry_mcp/core/…` and `src/registry_mcp/registries/…`
(D-003).

The country code is **`GB`**, strictly, with no `UK` alias — see D-015.

---

## 1. The upstream API

Base URL: `https://api.company-information.service.gov.uk`

Developer specification: <https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference>

### 1.1 Authentication — the first real difference from Norway

Companies House requires an API key. From the authorisation guide
(<https://developer-specs.company-information.service.gov.uk/guides/authorisation>):

> "the Companies House API takes the username as the API key and ignores the password, so can be
> left blank."
>
> `curl -XGET -u my_api_key: https://api.company-information.service.gov.uk/company/00000006`

So: **HTTP Basic, key as username, empty password.** In httpx that is
`httpx.BasicAuth(api_key, "")`.

The key is read from **`COMPANIES_HOUSE_API_KEY`**, **at call time, never at import time**. A missing
key must never break `import registry_mcp.registries` — `registries/__init__.py` imports every
bundled country unconditionally at package load (`core/registry.py::_load_registries`), so an
`os.environ[...]` at module scope would take the whole server down on a deployment that only wants
Norway. See §6 for the exact error.

Free keys: <https://developer.company-information.service.gov.uk/get-started>.

This is the first registry that needs a credential, which is why `Registry` grew
`requires_api_key` / `api_key_env` in D-017. `CompaniesHouseRegistry` sets both.

### 1.2 Rate limit

From <https://developer-specs.company-information.service.gov.uk/guides/rateLimiting>:

> "You can make up to 600 requests within a five-minute period."
>
> "you will receive a `429 Too Many Requests` HTTP status code"

The limit is per application (per key), and resets "back to its maximum value of 600 requests" at
the end of each five-minute window.

**Rate-limit headers are undocumented but real** — confirmed on a live 200 (2026-09-04):

```
x-ratelimit-limit: 600
x-ratelimit-remain: 591
x-ratelimit-reset: 1788538297      <- unix epoch seconds
x-ratelimit-window: 5m
```

They are also named in `access-control-expose-headers`, so they are intended for clients. Use them,
but never *depend* on them: read them defensively, log `x-ratelimit-remain` at DEBUG, and feed
`x-ratelimit-reset` into the 429 hint (it is far more useful than "about five minutes"). No
`Retry-After` header was observed; read it anyway and prefer it when present.

Because the budget is per key and the key may be shared with the operator's other tools, the client
carries its own limiter (§6) **and** cache aggressively (§9). 600/5 min is generous for our traffic;
the limiter exists so a runaway loop cannot get the operator's key throttled, not because we expect
to approach the ceiling.

### 1.3 Endpoints this module uses

| Purpose | Endpoint | Notes |
|---|---|---|
| Lookup a company | `GET /company/{company_number}` | 200 with the profile; 404 if unknown |
| Search by name | `GET /search/companies?q={q}&items_per_page={n}` | §4 |
| Officers | `GET /company/{n}/officers` | `DEFERRED` — the exact analogue of Norway's `/roller` |
| Charges | `GET /company/{n}/charges` | `DEFERRED` |
| Insolvency | `GET /company/{n}/insolvency` | `DEFERRED` |
| PSCs | `GET /company/{n}/persons-with-significant-control` | `DEFERRED` |
| Filing history | `GET /company/{n}/filing-history` | `DEFERRED` |
| UK establishments | `GET /company/{n}/uk-establishments` | `DEFERRED` |
| Registered office address | `GET /company/{n}/registered-office-address` | Not used — the profile already carries it |

Documented response codes for the search endpoint are `200` and `401`. `VERIFY` the full set for
`/company/{n}`; handle `401`, `403`, `404`, `429`, `5xx` regardless (§6).

### 1.4 Live fixtures — `tests/fixtures/ch_*.json`

Sixteen real responses, fetched with a live REST key on 2026-09-04 and saved verbatim (pretty-printed
only). **T15b starts from these; it does not invent payload shapes.** They were chosen so that every
branch of §2, §5.4, §7 and §8 has a real payload behind it.

| Fixture | Entity | `type` | `company_status` | What it is the fixture *for* |
|---|---|---|---|---|
| `ch_00445790.json` | TESCO PLC | `plc` | `active` | The canonical healthy plc. 6-month accounts rule; two previous names; a 52/53-week year; **`links.charges` present while `has_charges` is `false`** (§1.6 №1) |
| `ch_09446231.json` | MONZO BANK LIMITED | `ltd` | `active` | The canonical healthy `ltd`. 9-month rule; two SIC codes; one previous name |
| `ch_OC303675.json` | DELOITTE LLP | `llp` | `active` | LLP on the private 9-month period, month-end clamped; **`confirmation_statement.overdue: true` with the due date left in the past** |
| `ch_SC090312.json` | NATWEST MARKETS PLC | `plc` | `active` | `SC` prefix, `jurisdiction: "scotland"`; **an address with no `country` and no `locality`** (§1.6 №4) |
| `ch_00000006.json` | MARINE AND GENERAL MUTUAL LIFE ASSURANCE SOCIETY | `private-unlimited-nsc` | `dissolved` | Dissolved, `date_of_cessation: "2018-07-10"`, **no `next_accounts` and no `confirmation_statement` at all**. Companies House's own documentation example, and T15d's smoke target |
| `ch_04374209.json` | *(a guarantee company)* | `private-limited-guarant-nsc-limited-exemption` | `liquidation` | Insolvency: `has_insolvency_history: true`, `links.insolvency` present, both filings overdue since 2024. The §5.4 status-gate fixture |
| `ch_BR026263.json` | CIC INTERNATIONAL REALTY | `uk-establishment` | **`open`** | The sub-unit: `branch_company_details.parent_company_number = "FC041146"`, `links.overseas`, no `jurisdiction`, no accounts |
| `ch_FC032315.json` | CIC PRIVATE DEBT | `oversea-company` | `active` | `foreign_company_details`; **`next_accounts` present with no `due_on` and no `accounts.next_due`** — the live proof that §5.4's step-3/step-4 rungs are reachable |
| `ch_CE020555.json` | COMMUNITY ACCOMMODATION GROUP | `charitable-incorporated-organisation` | *(absent)* | **A near-empty stub profile** — no status, no `date_of_creation`, no address, no `accounts`; carries `external_registration_number` (the Charity Commission number) |
| `ch_RS007790.json` | *(a registered society)* | `registered-society-non-jurisdictional` | *(absent)* | Same stub shape, plus `partial_data_available: "full-data-available-from-financial-conduct-authority-mutuals-public-register"` |
| `ch_13948759.json` | *(a guarantee company)* | `private-limited-guarant-nsc` | `active` | Confirms the guarantee forms take the **private 9-month** period; `last_accounts.type: "micro-entity"` |
| `ch_13507518.json` | COMMUNITY INTEREST CARE CIC | `private-limited-guarant-nsc` | `active` | **`subtype: "community-interest-company"`** plus the deprecated `is_community_interest_company: true` |
| `ch_search_tesco.json` | — | — | — | `GET /search/companies?q=tesco&items_per_page=3`, `total_results: 356` |
| `ch_search_empty.json` | — | — | — | Zero hits: `items` is present and **empty**, `total_results: 0` |
| `ch_404.json` | — | — | — | The 404 body: `{"timestamp", "message", "request_id"}` — **not** empty, unlike brreg's |
| `ch_401.json` | — | — | — | The bad-key body: `{"error": "Invalid Authorization", "type": "ch:service"}`, with a `www-authenticate` response header. Confirms **401**, not 403 |

### 1.5 Live arithmetic — every §5.4 rule, proved

Read straight out of the fixtures above. If an implementation disagrees with a row here, the
implementation is wrong.

| Fixture | Period end | Due | Interval |
|---|---|---|---|
| `00445790` accounts (plc) | 2027-02-26 | 2027-08-26 | **6 months** |
| `SC090312` accounts (plc) | 2026-12-31 | 2027-06-30 | **6 months** |
| `09446231` accounts (ltd) | 2027-03-31 | 2027-12-31 | **9 months** |
| `13948759` accounts (guarantee) | 2027-03-31 | 2027-12-31 | **9 months** |
| `OC303675` accounts (llp) | 2026-05-31 | 2027-02-28 | **9 months**, month-end clamped — 31 May + 9 months lands on 28 Feb because 2027 is not a leap year |
| `00445790` confirmation statement | 2027-06-18 | 2027-07-02 | **+14 days** |
| `SC090312` confirmation statement | 2027-08-31 | 2027-09-14 | **+14 days** |
| `09446231` confirmation statement | 2026-11-11 | 2026-11-25 | **+14 days** |
| `13948759` confirmation statement | 2027-03-01 | 2027-03-15 | **+14 days** |
| `OC303675` confirmation statement | 2026-07-31 | 2026-08-14 | **+14 days**, and overdue as of 2026-09-04 |

Five independent proofs of the accounts period and five of the confirmation-statement period, across
four legal forms and two jurisdictions. `core/rules/common.py::add_months` already does the month-end
clamp that `OC303675` requires.

### 1.6 Where the live payloads contradict the published schema

Eight discrepancies between the developer specification and what the API actually sends. Numbers 1
and 2 would produce a **wrong answer** rather than an exception, which is why they lead.

1. **`links.charges` is present even when there are no charges.** `00445790` has
   `"charges": "/company/00445790/charges"` and `"has_charges": false`; so does `09446231`. The
   documentation says `has_charges` is "Deprecated. Please use links.charges" — **that advice is
   wrong for `charges`**, and following it would report every large company as having charges.
   Read the deprecated boolean. `links.insolvency`, by contrast, *did* correlate: it is present on
   `04374209` (`has_insolvency_history: true`) and absent from all five healthy fixtures — but read
   the boolean there too, for symmetry and because the boolean was present on every payload observed.
2. **`accounts.last_accounts.type` can be the four-character string `"null"`.** `FC032315` carries
   `"type": "null"` — the JSON string, not the JSON literal. Any code that treats a truthy string as
   a real accounts type will report an accounts type of "null". (We do not map this field at all —
   §15 — but the same trap may exist in other string enums.)
3. **`accounts.accounting_reference_date.day` / `.month` are zero-padded strings, not integers.**
   `{"day": "26", "month": "02"}`. The schema says integer. So is
   `foreign_company_details.accounts.must_file_within.months` (`"5"`). Coerce with `int()`, and do
   not compare to an integer literal.
4. **`registered_office_address` fields are individually optional, even for a UK company.**
   `SC090312` has **no `country` and no `locality`** — its `address_line_2` is `"Edinburgh"`. So
   `Address.city` and `Address.country_code` are legitimately `None` for a live plc. Never assume a
   UK address has a post town.
5. **`premises` appears in *search* results but not in the profile.** The search hit for `00445790`
   has `"premises": "Tesco House, Shire Park"` and `"address_line_1": "Kestrel Way"`; the profile
   folds both into `"address_line_1": "Tesco House, Shire Park"`. The same company, two address
   shapes, from two endpoints. Map both defensively.
6. **`company_status` can be absent from a search item** — 12 of 100 hits on `q=community`, all of
   them `charitable-incorporated-organisation` or `scottish-charitable-incorporated-organisation`.
   `item.get("company_status")` → `CompanyStatus.UNKNOWN`, never a `KeyError`.
7. **Two undocumented fields are routinely sent**: `has_super_secure_pscs` (on the profile) and
   `page_number` (on search). Two documented names are wrong:
   `foreign_company_details.is_a_credit_finance_institution` is actually
   `is_a_credit_financial_institution`, and `links["uk-establishments"]` is actually
   `links["uk_establishments"]` — a **hyphen in the docs, an underscore on the wire**.
   `foreign_company_details.legal_form` is sent but not documented at all.
8. **`items_per_page` is capped at 100 upstream.** Asking for 200 returns 100 and echoes
   `"items_per_page": 100`. Our 1..100 clamp (§4) therefore matches the API exactly rather than
   being an arbitrary ceiling. Separately, `items_per_page=0` and a **missing `q`** both return
   `200`, so the API validates neither — we must (§4).

### 1.7 `VERIFY` markers still open after the live pass

Only these five remain. Everything else in this file is confirmed.

- `company_status_detail` — no live example of any value, including
  `active-proposal-to-strike-off`, was found in ~300 sampled records. The §8 table is from the
  documented enum. T15b should try harder to find one; if it cannot, the mapping is exercised by a
  synthetic payload and the note text ships unverified.
- `company_status` values `closed` and `registered` — no live example. (`open` **is** confirmed, on
  `BR026263`.)
- `service_address` — no fixture has one; only a `registered-overseas-entity` should.
- `corporate_annotation[]` — no fixture has one, so its `type` enum is unknown.
- `PC` (protected cell company) as a number prefix — inferred from the `protected-cell-company` type,
  never seen.

### 1.8 Sources and licence

Companies House register data is **not** published under the Open Government Licence, which is the
easy mistake to make. From GOV.UK, *Public task, copyright and Crown copyright*
(<https://www.gov.uk/government/publications/companies-house-accreditation-to-information-fair-traders-scheme/public-task-copyright-and-crown-copyright>):

> "Information on the public register is made available by virtue of approvals issued by us in
> accordance with section 47 of the Copyright, Designs and Patents Act 1988 and Schedule 1 of the
> Database Regulations (SI 1997/3032)."

and

> "Companies House imposes no rules or requirements on how the information on the public register is
> used"

Companies House's *own* material — guidance notes, publications, statistical tables — is separately
Crown copyright under OGL v3.0 and **must be credited**; register information carries no such
obligation but we credit it anyway, because a citation is what makes an agent's answer checkable.

Therefore:

- `Registry.license` = `"Crown copyright — Companies House public register, free to re-use"`
- `CompanyReport.source` = `"Companies House (UK)"`
- `CompanyReport.source_url` = `https://find-and-update.company-information.service.gov.uk/company/{id}`
  — the **human** record, not the API URL, because that is the link an agent should hand a user.
  `VERIFY` this renders for every number shape we return (it does for all twelve company fixtures in §1.4).
- `Registry.source_url` = `"https://api.company-information.service.gov.uk"`

Terms of use for the API itself: <https://developer.company-information.service.gov.uk/manage-applications/terms-of-use>
(requires sign-in; the substantive licence position is the GOV.UK page quoted above).

---

## 1.9 The registry class attributes

`registries/gb/__init__.py`, verbatim. These nine values are what `GET /v1/countries` and the MCP
`list_countries` tool publish (D-012), plus the two D-017 adds.

```python
class CompaniesHouseRegistry(Registry):
    country: ClassVar[str] = "GB"
    registry: ClassVar[str] = "companies-house"
    name: ClassVar[str] = "Companies House (United Kingdom)"
    id_scheme: ClassVar[str] = "company number"
    id_example: ClassVar[str] = "00445790"
    id_description: ClassVar[str] = (
        "A UK company registration number (CRN): 8 characters, either 8 digits or a "
        "two-letter prefix and 6 digits. Shorter numbers are zero-padded, so 445790 is "
        "written 00445790. There is no check digit."
    )
    source_url: ClassVar[str] = "https://api.company-information.service.gov.uk"
    license: ClassVar[str] = "Crown copyright — Companies House public register, free to re-use"
    is_stub: ClassVar[bool] = False
    requires_api_key: ClassVar[bool] = True
    api_key_env: ClassVar[str] = "COMPANIES_HOUSE_API_KEY"
```

`id_example` is **`00445790`** (TESCO PLC, active), not the `00000006` that Companies House uses in
its own authorisation example. `id_description` says "a real, valid identifier an agent can use to
smoke-test the tool", and `00000006` has been dissolved since 2018 — an agent smoke-testing with it
gets a correct but discouraging answer and no accounts or confirmation-statement data at all.
`00000006` stays as the dissolved fixture and as T15d's deployment smoke target, where being
dissolved is the point.

`format_id` is **not** overridden — UK company numbers have no conventional grouping, so
`ValidationResult.formatted` and `CompanyReport.id_formatted` are honestly `None` (D-010).
`aclose` **is** overridden (§6). `rules_markdown` is overridden (§13).

---

## 2. `CompanyReport` field mapping

Target model: `core/models.py :: CompanyReport`. Source is `GET /company/{company_number}` unless
noted. Anything the JSON omits stays `None` — never `""`, never `0`, never a guess (D-004, D-011).

| `CompanyReport` field | Companies House field | Type | Notes |
|---|---|---|---|
| `country` | — | `str` | Constant `"GB"` |
| `registry` | — | `str` | Constant `"companies-house"` |
| `id` | `company_number` | `str` | 8 characters, already canonical upstream. Confirmed on every fixture |
| `id_formatted` | — | `None` | UK company numbers have no conventional grouping. `format_id` is **not** overridden; it inherits `Registry.format_id`'s `None` (D-010) |
| `id_scheme` | — | `str` | Constant `"company number"` |
| `name` | `company_name` | `str` | As registered, upper-case in practice |
| `previous_names` | `previous_company_names[].name` | `list[str]` | **Newest first.** The API's array is already newest-first (confirmed on `00445790` and `SC090312`, both with two entries), but sort by `ceased_on` descending anyway — it costs a line and makes the guarantee ours rather than theirs |
| `legal_form_code` | `type` | `str` | The raw enum value, e.g. `"ltd"`. §7 |
| `legal_form` | derived, §7 | `str` | English label. When `subtype` is present it is appended, e.g. `"Private limited company (community interest company)"` |
| `legal_form_local` | — | `str \| None` | The register is already in English, so there is no separate local label. Set it to the same English label rather than `None`, so an agent that reads `legal_form_local` for display gets something. `VERIFY` with T15c whether that is more helpful than `None` |
| `limited_liability` | derived, §7 | `bool \| None` | |
| `has_board_duty` | derived, §7 | `bool \| None` | `None` for LLPs: an LLP has designated members, not a board (§7) |
| `has_annual_accounts_duty` | derived, §7 | `bool \| None` | |
| `status` | derived, §8 | `CompanyStatus` | From `company_status` **only** |
| `status_detail` | derived, §8 | `str` | One English sentence naming the value it came from |
| `is_active` | derived | `bool` | `status == ACTIVE` |
| `registered_at` | `date_of_creation` | `date \| None` | Incorporation is the register entry; the UK has one date, not two |
| `founded_at` | `date_of_creation` | `date \| None` | **Except** for `oversea-company`, `uk-establishment` and `registered-overseas-entity`, where `date_of_creation` is the date of *UK* registration, not of foundation abroad → `None` |
| `business_register_registered_at` | — | `None` | The UK has no separate commercial register |
| `bankruptcy_date` | — | `None` | Not in the profile. Also a terminology trap: in UK law *bankruptcy* applies to individuals; companies enter liquidation or administration. `DEFERRED` to the insolvency resource |
| `deregistered_at` | `date_of_cessation` | `date \| None` | "The date which the company was converted/closed, dissolved or removed." Read the quirk in §8 before using it |
| `vat_registered` | — | `None` | Not published by Companies House. `DEFERRED` — HMRC runs a separate free "Check a UK VAT number" API |
| `vat_registered_at` | — | `None` | |
| `vat_number` | — | `None` | A UK VAT number (`GB` + 9 digits) is **not** derivable from a company number |
| `in_business_register` | — | `None` | Not applicable: one register |
| `registers` | derived, below | `dict[str, bool]` | |
| `employees` | — | `None` | **Companies House publishes no employee count at all.** Not a gap in our mapping — a gap in the register |
| `employees_reported` | — | `False` | Honest per D-011: we hold no figure |
| `industry_codes` | `sic_codes[]` | `list[IndustryCode]` | `IndustryCode(code=c, description=None, scheme="SIC 2007", rank=i+1)`. Descriptions are `DEFERRED` (§5.5) |
| `sector_code` | — | `None` | No institutional sector classification |
| `sector` | — | `None` | |
| `purpose` | — | `None` | No objects clause is published |
| `activity` | `branch_company_details.business_activity`, else `foreign_company_details.business_activity` | `str \| None` | Only present for UK establishments and overseas companies |
| `share_capital` | — | `None` | Not in the profile; it lives in the confirmation statement's `statement_of_capital`. `DEFERRED` |
| `share_capital_currency` | — | `None` | |
| `business_address` | `registered_office_address` | `Address \| None` | §3. Read `registered_office_is_in_dispute` before trusting it |
| `postal_address` | `service_address` | `Address \| None` | Only returned for a `registered-overseas-entity`. `VERIFY` |
| `website` | — | `None` | Not published |
| `email` | — | `None` | Not published |
| `phone` | — | `None` | Not published |
| `parent_id` | `branch_company_details.parent_company_number` | `str \| None` | Set for `uk-establishment` records |
| `is_subunit` | derived | `bool` | `True` when `type == "uk-establishment"` **or** `branch_company_details` is present. §7 |
| `in_group` | — | `None` | Not published |
| `last_annual_accounts_year` | `accounts.last_accounts.period_end_on` | `int \| None` | `.year` of the period end. Fall back to the deprecated `accounts.last_accounts.made_up_to` if `period_end_on` is absent |
| `confidence` | derived | `float` | `1.0` for identifier lookup (D-005) |
| `confidence_basis` | — | `str` | `"exact identifier lookup in the Companies House register"` |
| `cached` | derived | `bool` | §9 |
| `fetched_at` | derived | `datetime` | UTC, timezone-aware |
| `source` | — | `str` | `"Companies House (UK)"` |
| `source_url` | — | `str` | `https://find-and-update.company-information.service.gov.uk/company/{id}` |
| `license` | — | `str` | §1.8 |
| `notes` | derived | `list[str]` | §2.1 — this is where most of the UK-specific value lands |

`registers` collects the two membership facts the profile actually carries:

```python
{
    "charges":    bool(data.get("has_charges")),
    "insolvency": bool(data.get("has_insolvency_history")),
}
```

**Read the booleans, not the links — the documentation's advice here is wrong.** `has_charges`,
`has_insolvency_history`, `has_been_liquidated` and `is_community_interest_company` are all
documented as deprecated in favour of `links.charges`, `links.insolvency` and `subtype`. For
`subtype` that is correct and we follow it. For `links.charges` it is **false**: the live
`00445790` and `09446231` fixtures both carry a `links.charges` URL alongside `"has_charges": false`
(§1.6 №1), so link presence means "the charges endpoint exists", not "charges exist". Using it would
report every large company as encumbered — a wrong answer, silently, on the field a supplier check
cares about most.

Absent booleans map to `False`, not `None`: `registers` is `dict[str, bool]` and both keys appeared
on every profile that had any register data at all. The near-empty stub profiles of `CE020555` /
`RS007790` carry them too.

### 2.1 `notes` — the rules that fill it

`CompanyReport.notes` is copied verbatim into `DeadlineReport.notes` by `Registry.deadline_report`
(D-010), so every caveat that explains an empty or surprising deadline list must be written here, in
`registries/gb/mapping.py`, and nowhere else.

| Condition | Note |
|---|---|
| `status != ACTIVE` | §8's per-status sentence |
| `company_status_detail == "active-proposal-to-strike-off"` | "Companies House has published a proposal to strike this company off the register. It is still active today, but it may be dissolved within about two months unless the proposal is suspended. Do not treat it as a stable counterparty without checking the filing history." |
| `company_status_detail` is any other value | One sentence naming the value, from §8's table |
| `has_insolvency_history` / `links.insolvency` present, but `status == ACTIVE` | "This company has insolvency filings in its history. It is active today; the filings may relate to a concluded arrangement or to an administration it has since exited." |
| `registered_office_is_in_dispute` is true | "The registered office address shown is disputed and may have been replaced by Companies House with a default address. Do not rely on it for correspondence." |
| `undeliverable_registered_office_address` is true | "Companies House cannot deliver post to this registered office address." |
| `partial_data_available` is present | "Companies House is not the primary source of data for this entity, so this record is incomplete ({value})." Confirmed live on `RS007790`, whose value is `full-data-available-from-financial-conduct-authority-mutuals-public-register` |
| `external_registration_number` is present | "This entity's full record is held by another regulator under registration number {value}." Confirmed live on `CE020555` (`"1187753"`, a Charity Commission number) and `FC032315`. On a stub profile (§2.2) this is often the **only** actionable fact we have, which is why it is mapped despite §15 |
| the profile is a stub (§2.2) | "Companies House holds only a minimal record for this entity: no status, incorporation date or registered office address was returned. The register named above is the authoritative source." |
| `corporate_annotation[]` non-empty | One note per annotation: its `description` when present, otherwise a sentence naming its `type`. `VERIFY` the type enum |
| `subtype == "community-interest-company"` | "This is a community interest company. It must file a CIC34 community interest company report alongside its annual accounts, and its assets are subject to an asset lock." |
| `jurisdiction` is present and is **not** `england-wales` | "Registered under the law of {jurisdiction}." — see §15 for why `jurisdiction` gets no dedicated field |
| `is_subunit` | "This record is a UK establishment of an overseas company, not a company in its own right. Look up parent_id ({parent_id}) for the entity that files." |
| `annual_return` object is present | "This company's last periodic filing was an annual return, a form abolished in June 2016 and replaced by the confirmation statement. Treat any annual-return due date on this record as historical." |
| deadlines suppressed by status | §5.4's exemption sentence |
| no accounts date could be established | §5.4's "no date" sentence |

Note counts stay small: a healthy active `ltd` gets **zero** notes (verified against `09446231`),
which is the point — a note means something the agent must read.

### 2.2 Stub profiles — the shape that will break a naive mapper

Not every 200 carries a company. Charitable incorporated organisations (`CE…`, `CS…`) and registered
societies (`RS…`, `IP…`, `SP…`, `NP…`) are on the Companies House index but regulated elsewhere, and
their profiles are **stubs**. The complete live payload for `CE020555` is eleven keys:

```
can_file, company_name, company_number, etag, external_registration_number,
has_charges, has_insolvency_history, jurisdiction, links,
registered_office_is_in_dispute, undeliverable_registered_office_address, type
```

**No `company_status`. No `date_of_creation`. No `registered_office_address`. No `accounts`. No
`confirmation_statement`.** `ch_RS007790.json` is the same shape minus `jurisdiction` and
`external_registration_number`, plus `partial_data_available`.

`CompanyReport` handles this without a single special case, provided the mapper reads every field
with `.get()`:

- `status` → `CompanyStatus.UNKNOWN` (§8's absent-status row), `is_active` → `False`
- `registered_at`, `founded_at`, `business_address` → `None`
- `name`, `id`, `country`, `registry` → present, so the model constructs
- deadlines → `[]`, because the status is not `ACTIVE` (§5.4)
- `notes` → the stub sentence, the external-registration-number sentence, and the
  `partial_data_available` sentence

That is the right answer: "Companies House has this entity on its index but does not hold its
record; here is who does." **Do not** paper over it by inferring `ACTIVE` from the absence of a
status — that would be inventing the one fact a supplier check turns on.

A mapper that indexes rather than `.get()`s will raise `KeyError` on these two fixtures, which is why
they are in the fixture set.

---

## 3. Address mapping

`registered_office_address` (and `service_address`, identical shape):

| `Address` field | Companies House field |
|---|---|
| `lines` | `[premises, address_line_1, address_line_2]`, `care_of` and `po_box` prepended when present, empties dropped, order preserved |
| `postal_code` | `postal_code` |
| `city` | `locality` |
| `municipality` | `region` |
| `municipality_code` | — (`None`) |
| `country_code` | derived, see below |
| `country_name` | `country` |

`country` is a **free-text name**, not a code: the live fixtures show `"United Kingdom"`
(`00445790`, `OC303675`) and `"England"` (`00000006`, `09446231`). `Address.country_code` is
documented as ISO-3166-1 alpha-2, so map only the values we are sure of — `England`, `Scotland`,
`Wales`, `Northern Ireland`, `United Kingdom`, `Great Britain` (case-insensitively) → `"GB"` — and
leave everything else `None` rather than guessing at a foreign country name.

**Every component is optional, including on a live plc.** `SC090312`'s address is
`{address_line_1: "36 St Andrew Square", address_line_2: "Edinburgh", postal_code: "EH2 2YB"}` —
no `country`, no `locality`, and the post town sitting in `address_line_2` where a parser cannot
reach it. So `Address.city` and `Address.country_code` are legitimately `None` for NatWest Markets
plc, and any test asserting a non-null `city` for a real UK company is wrong. A missing address
object maps to `None`, not to an empty `Address`.

`premises` is the property name or number. **It appears in search results but not in the profile**
(§1.6 №5): the profile for `00445790` folds it into `address_line_1` (`"Tesco House, Shire Park"`)
while the search hit splits it out. Read it defensively in both, and when present put it at the
front of `lines` rather than in a component of its own — that way `Address.one_line()` renders the
same string from either endpoint.

---

## 4. Search mapping

`GET /search/companies?q={q}&items_per_page={limit}` returns:

The live envelope (`ch_search_tesco.json`, `q=tesco&items_per_page=3`):

```json
{
  "kind": "search#companies",
  "page_number": 1,
  "items_per_page": 3,
  "total_results": 356,
  "start_index": 0,
  "items": [ { "kind": "searchresults#company", "company_number": "00445790",
               "title": "TESCO PLC", "company_status": "active", "company_type": "plc",
               "date_of_creation": "1947-11-27",
               "address": {"premises": "Tesco House, Shire Park", "address_line_1": "Kestrel Way",
                           "locality": "Welwyn Garden City", "postal_code": "AL7 1GA",
                           "country": "United Kingdom"},
               "address_snippet": "Tesco House, Shire Park, Kestrel Way, …",
               "description": "00445790 - Incorporated on 27 November 1947",
               "description_identifier": ["incorporated-on"],
               "links": {"self": "/company/00445790"},
               "snippet": "TESCO STORES (HOLDINGS) PUBLIC LIMITED COMPANY",
               "matches": {"snippet": []} } ]
}
```

- `page_number` is sent but undocumented (§1.6 №7). Ignore it.
- Zero hits give `"items": []` — **present and empty**, not absent (`ch_search_empty.json`). Use
  `data.get("items") or []` anyway: absence is documented and costs one `or`.
- `SearchResult.total` ← `total_results` (default `0`); `truncated` ← `total > len(hits)`.
- `SearchHit`: `id`←`company_number`, `name`←`title`, `legal_form_code`←`company_type` (note the
  name change from the profile's `type`), `legal_form` from §7,
  `status` from §8's table applied to **`item.get("company_status")`**, `city`←`address.locality`,
  `municipality`←`address.region`, `registered_at`←`date_of_creation`,
  `is_subunit` ← `company_type == "uk-establishment"`,
  `source_url` ← the human record URL of §1.8.
- **`company_status` is absent from some hits** — 12 of 100 on `q=community`, every one a CIO
  (§1.6 №6, §2.2). Those map to `CompanyStatus.UNKNOWN`. A `KeyError` here is the single most
  likely search bug.
- `date_of_cessation` appears on dissolved hits; it is not mapped to `SearchHit`, which has no field
  for it.
- Observed `description_identifier` values: `incorporated-on`, `dissolved-on`, `liquidation`,
  `registered-on`, `converted-closed-on`, `opened-on`, `first-uk-establishment-opened-on`,
  `registered-externally`. Not mapped (§15) — the status field already carries the signal.
- `SearchResult.hint` is always set: `"240 companies match. Call lookup_company with the id of the
  right hit for the full report."` When `total_results == 0`, the hint must say the thing a UK user
  most often needs to hear: `"No companies match that name. Sole traders and ordinary partnerships
  are not registered at Companies House, so they will never appear here."`
- `limit` maps to `items_per_page` and must be 1..100 — outside that range raises
  `RegistryError(bad_request)`, not a silent clamp, exactly as Norway does. **100 is the API's own
  ceiling**, confirmed live: `items_per_page=200` returns 100 items and echoes
  `"items_per_page": 100` (§1.6 №8). So our range is the real range, not an arbitrary one.
- **The API validates neither `q` nor `items_per_page`**: a missing `q` and `items_per_page=0` both
  return `200`. Validate both ourselves — an empty query string raises `bad_request` with a hint
  naming `lookup_company` for the case where the caller actually has an identifier.
- `start_index` is not exposed. Pagination is `DEFERRED`.
- `restrictions` is not used. `DEFERRED`. In particular do **not** pass `active-companies`: a caller
  checking a supplier needs to see a dissolved match, not an empty result.
- `matches`, `snippet`, `description`, `description_identifier`, `address_snippet`, `kind` are not
  mapped (§15).
- Confidence follows D-005 anchors, computed from our own comparison of the query against `title`,
  never from Companies House's relevance order or its `matches` offsets:

| Value | Basis |
|---|---|
| 0.95 | `title` equals the query, case-insensitively (compare after casefold and whitespace collapse) |
| 0.8 | `title` starts with the query |
| 0.6 | every whitespace-separated token of the query appears in `title` |
| 0.4 | any other hit the register returned |

A `SearchHit` for a **dissolved** company keeps its confidence — confidence is "is this the entity
you meant", not "is this entity any good". The status field is what carries that.

---

## 5. Rules — `registries/gb/rules.py`

### 5.1 Identifier validation — shape only, no check digit

A UK company registration number (CRN) is **8 characters** and has **no check digit**. There is
therefore nothing to validate but shape, and `validate_id` normalises and checks shape only.

**Normalisation, in order:**

1. Strip all whitespace (including non-breaking space ` `), `.`, `-` and `/`.
2. Upper-case.
3. If the result matches `^GB\d{9}(\d{3})?$`, raise `invalid_id` with the **VAT-specific** hint of
   §5.1.1 — that is a UK VAT registration number, a different scheme entirely, and telling the agent
   so is worth more than a generic rejection.
4. Zero-pad, and only in these two shapes:
   - all digits and 1–8 long → left-pad with `0` to 8. `"1234"` → `"00001234"`.
   - matches `^([A-Z]{1,2})(\d+)$` and shorter than 8 → insert zeros between the letters and the
     digits until the whole string is 8. `"SC12345"` → `"SC012345"`; `"NI1234"` → `"NI001234"`.
   - anything else is left exactly as it is. **Never truncate.**
5. Accept iff **all** of:
   - length is exactly 8;
   - every character is `A`–`Z` or `0`–`9`;
   - at least one character is a digit;
   - the first character is a letter, **unless** the whole string is digits.

That last pair is the whole shape rule. `"00000006"` passes on the all-digits branch; `"SC090312"`,
`"OC303675"`, `"R0123456"` and `"BR012345"` pass on the letter branch; `"ABCDEFGH"` fails for having
no digit and `"1SC12345"` fails for starting with a digit without being numeric.

**The prefix table of §5.1.2 is documentation, not a gate.** Companies House adds prefixes — `OE`
for overseas entities arrived with the Economic Crime (Transparency and Enforcement) Act 2022 — and
a validator that rejects a prefix it has not heard of turns a real company into an `invalid_id`,
which is a far worse failure than accepting a shape that then 404s. `lookup` is the thing that knows
whether a number exists.

`VERIFY` one edge: several sources describe letter *suffixes* on some series (`NI…A`, `SL…A`, `RS`
with a one-to-three letter suffix). If T15b finds a real number longer than 8 characters, the length
rule widens and this paragraph becomes a bug report; nothing in §1.4 is longer than 8.

#### 5.1.1 Errors

```python
RegistryError(
    ErrorCode.INVALID_ID,
    f"{raw!r} is not a valid UK company number.",
    hint=(
        "A UK company number is 8 characters: either 8 digits (e.g. 00445790) or a "
        "two-letter prefix and 6 digits (e.g. SC090312 for Scotland, OC303675 for an LLP). "
        "Shorter numbers are zero-padded, so 445790 becomes 00445790. "
        "If you have a company name instead, call search_company."
    ),
    country="GB", registry="companies-house",
)
```

and, for the VAT case:

```python
    hint=(
        "That looks like a UK VAT registration number, not a company number. The two are "
        "unrelated: a company number is 8 characters, e.g. 00445790. Companies House does not "
        "publish VAT numbers. If you have the company name, call search_company."
    )
```

#### 5.1.2 Prefix table

Two-character prefixes unless marked. Compiled 2026-09-04 from the Companies House guide
(<https://chguide.co.uk/general/company-number.html>) cross-checked against the
`type` enum of §7 and the doorda glossary; `VERIFY` each row that T15b can confirm against a live
number. Jurisdiction is *implied* by the prefix, not asserted by us.

| Prefix | Entity | Jurisdiction |
|---|---|---|
| *(none, 8 digits)* | Company | England & Wales |
| `SC` | Company | Scotland |
| `NI` | Company (post-partition) | Northern Ireland |
| `R0` | Company (pre-partition) — the one single-letter-plus-digit prefix | Northern Ireland |
| `OC` | Limited liability partnership | England & Wales |
| `SO` | Limited liability partnership | Scotland |
| `NC` | Limited liability partnership | Northern Ireland |
| `LP` | Limited partnership | England & Wales |
| `SL` | Limited partnership | Scotland |
| `NL` | Limited partnership | Northern Ireland |
| `FC` | Overseas company | — |
| `SF` | Overseas company registered pre-2009 | Scotland |
| `NF` | Overseas company registered pre-2009 | Northern Ireland |
| `BR` | UK establishment of an overseas company | — |
| `OE` | Overseas entity (ECTEA 2022) | — |
| `AC` | Assurance company | England & Wales |
| `SA` | Assurance company | Scotland |
| `NA` | Assurance company | Northern Ireland |
| `ZC` | Unregistered company | England & Wales |
| `SZ` | Unregistered company | Scotland |
| `NZ` | Unregistered company | Northern Ireland |
| `RC` | Royal charter company | England & Wales |
| `SR` | Royal charter company | Scotland |
| `NR` | Royal charter company | Northern Ireland |
| `IP` | Registered / industrial and provident society | England & Wales |
| `SP` | Registered society | Scotland |
| `NP` | Registered society or credit union | Northern Ireland |
| `NO` | Credit union / industrial and provident society | Northern Ireland |
| `RS` | Registered society (non-jurisdictional) | — |
| `IC` | Investment company with variable capital | England & Wales |
| `SI` | Investment company with variable capital | Scotland |
| `NV` | Investment company with variable capital | Northern Ireland |
| `CE` | Charitable incorporated organisation | England & Wales |
| `CS` | Charitable incorporated organisation | Scotland |
| `SE` | European company (Societas Europaea) | England & Wales |
| `ES` | European company | Scotland |
| `EN` | European company | Northern Ireland |
| `GE` | European economic interest grouping | England & Wales |
| `GS` | European economic interest grouping | Scotland |
| `GN` | European economic interest grouping | Northern Ireland |
| `SG` | Scottish qualifying partnership | Scotland |
| `FE` | Further education or sixth form college corporation | England & Wales |
| `PC` | Protected cell company | `VERIFY` — implied by the `protected-cell-company` type |

`NO` as a prefix is an unfortunate collision with the ISO code for Norway. It appears only inside a
GB company number and never as a country code, so nothing in the code can confuse them — but do not
"helpfully" strip a leading `NO` the way `registries/no/rules.py` strips it from a VAT string.

### 5.2 Public holidays — there are none to model

`registries/gb/holidays.py` **must not be written.** See §5.3.

### 5.3 Roll-forward — the UK does not do it

GOV.UK, *Life of a company — Part 1 Accounts*
(<https://www.gov.uk/government/publications/life-of-a-company-annual-requirements/life-of-a-company-part-1-accounts>):

> "If your filing deadline falls on a Sunday or a bank holiday, it is still a legal requirement to
> file your accounts by that date."

So a Sunday deadline is a Sunday deadline. Concretely, for every UK `Deadline`:

- `statutory_date == due_date`, always;
- `rolled_forward` is `False`, always;
- `core/rules/common.py::roll_forward` is **never called**. Not called with an empty holiday set —
  not called at all. It is a country-neutral helper Norway needs and Britain does not, and the two
  countries disagreeing about it is exactly the kind of difference D-001 exists to allow.

This is the single most likely thing for an implementer copying `registries/no/` to get wrong, so
`rules_markdown()` says it in prose (§13) and test 61 asserts it structurally.

### 5.4 Filing deadlines — implement these two

Computed from `report` plus the `today` parameter, never from the clock.

Companies House is unusual among registers in that **it publishes the dates itself**. Norway makes
us derive every date from statute; Britain hands us `accounts.next_accounts.due_on` and
`confirmation_statement.next_due` straight from the filing system that will actually judge
lateness. Those figures are authoritative and beat any calculation of ours — they already account
for accounting-reference-date changes, shortened and extended periods, and administrative
extensions that we cannot see. **We compute only when the register is silent.**

| `kind` | `local_name` | `authority` | Recurrence |
|---|---|---|---|
| `annual_accounts` | Annual accounts | Companies House | annual |
| `confirmation_statement` | Confirmation statement (CS01) | Companies House | annual |

#### `annual_accounts` — derivation ladder, first hit wins

| # | Source | `applies_because` |
|---|---|---|
| 1 | `accounts.next_accounts.due_on` | "Companies House publishes this date for the company itself; it is the register's own figure, not a calculation." |
| 2 | `accounts.next_due` (deprecated mirror of 1) | same, plus "(from the deprecated `accounts.next_due` field)" |
| 3 | `accounts.next_accounts.period_end_on` + 9 months (private) or 6 months (public), **only** for a `type` in a confirmed bucket (§7) | "Computed: a {private,public} company must deliver accounts within {9,6} months of the end of the accounting reference period (Companies Act 2006 s.442). Companies House did not publish a due date for this company." |
| 4 | nothing | **no deadline**, plus a note: "Companies House publishes no next-accounts date for this company and its legal form ({type}) has no accounts-filing period this module is confident about, so no accounts deadline is given. Read `accounts` on the company report directly." |

Statutory periods, from the same GOV.UK guidance:

> Private companies: "9 months from the accounting reference date"
> Public companies: "6 months from the accounting reference date"

Live-confirmed five times over in §1.5. Month-end clamping is `core/rules/common.py::add_months`,
which already does it (`31 May 2026 + 9 months → 28 Feb 2027`, matching DELOITTE LLP exactly).

Set `period_start` ← `accounts.next_accounts.period_start_on` and `period_end` ←
`accounts.next_accounts.period_end_on` when present, and `period_label` ← the ISO period end, e.g.
`"period ending 2027-02-26"`. Do **not** synthesise a calendar-year label the way Norway does: UK
accounting periods are genuinely arbitrary, and TESCO PLC's 52/53-week year — period ending
2027-02-26 against an accounting reference date of 28 February — is the live proof.

**Use `period_end_on`, not the accounting reference date, for step 3.** Two reasons, both live:
`accounts.accounting_reference_date` is `{"day": "26", "month": "02"}` on `00445790` — **strings,
not integers** (§1.6 №3) — and it is the *current* ARD of a 52/53-week filer, which drifts (the
company's last accounts ran to 28 February, the next run to 26 February). `period_end_on` is the
date the statutory period actually runs from, and it needs no parsing.

Step 3 is reachable in the wild: `ch_FC032315.json` carries `accounts.next_accounts` with a
`period_end_on` and **no `due_on`, and no top-level `accounts.next_due`**. In that particular case
the type (`oversea-company`) has no computed period, so it falls through to step 4 — but the shape
is real.

`mandatory` is `True` in steps 1–3.

#### `confirmation_statement` — derivation ladder, first hit wins

| # | Source | `applies_because` |
|---|---|---|
| 1 | `confirmation_statement.next_due` | "Companies House publishes this date for the company itself; it is the register's own figure, not a calculation." |
| 2 | `confirmation_statement.next_made_up_to` + 14 days | "Computed: a confirmation statement may be filed up to 14 days after the end of the review period (GOV.UK confirmation statement guidance)." |
| 3 | nothing | **no deadline**, plus a note saying so |

From <https://www.gov.uk/guidance/confirmation-statement-guidance>:

> "You must review your records and file at least one confirmation statement every 12 months."
>
> "You can file your statement up to 14 days after the review period has ended."

Live-confirmed five times in §1.5. `period_end` ← `next_made_up_to`; `period_start` is
`next_made_up_to` minus one year plus one day when we have it, otherwise `None` — and prefer `None`
over the subtraction if the arithmetic is not exact, because a wrong period is worse than no period.

Note the **early-filing reset**: "If you file early, you will need to choose a new confirmation
statement date. Your next review period will start the day after this date." That is precisely why
step 1 beats step 2 — the register knows the current review period and we do not.

`recurrence` is `annual` even though the statement is filed *at least* every 12 months.

#### Rules that apply to every UK deadline

- `days_until = (due_date - today).days`. **This, not `overdue`, is the overdue signal** — see the
  quirk in §5.4.1.
- Only the **next** occurrence of each `kind`; one `Deadline` per `kind`.
- Sorted by `due_date` ascending, then by `kind`.
- `statutory_date == due_date`, `rolled_forward is False` (§5.3).
- `source_url` is the GOV.UK guidance page for that obligation, not the API.
- **Deadlines are emitted only when `status is CompanyStatus.ACTIVE`.** Every other status returns
  `[]` plus one note: "This company's Companies House status is '{company_status}', so no filing
  deadlines are given. Once a company is dissolved, in liquidation, in administration or under a
  voluntary arrangement, what must still be filed is decided by the insolvency practitioner or the
  registrar and is not derivable from the public register."
  This is deliberately stricter than Norway, which lets `UNDER_LIQUIDATION` keep its deadlines: the
  Norwegian flag distinguishes voluntary from compulsory liquidation and the UK's `company_status`
  does not (§8), so we cannot make the distinction Norway's rule depends on. D-009's "never guess a
  duty" decides it.
- **Sub-units get nothing.** `is_subunit` (a `uk-establishment`) returns `[]` and the §2.1 note
  pointing at `parent_id` — the exact analogue of Norway's `BEDR`/`AAFY` rule.
- `company_status_detail == "active-proposal-to-strike-off"` does **not** suppress deadlines. The
  company is active and filing is the usual way a strike-off gets suspended. The note is loud
  instead.

#### 5.4.1 `overdue` is not our overdue

`accounts.next_accounts.overdue` and `confirmation_statement.overdue` are computed by Companies
House against *its* today, and reach us through a cache with a 24 h TTL (§9). Ours is computed
against the caller's `today`, which `DeadlineReport` echoes back. **`days_until < 0` is the
authoritative answer**; the upstream flag is corroboration only.

Confirmed live: DELOITTE LLP's confirmation statement due 2026-08-14 is flagged overdue and the due
date is **left in the past**, not rolled forward to the next cycle. So a negative `days_until` is a
normal, expected output of this module, and any test that assumes `days_until >= 0` is wrong.

When the two disagree — our `days_until >= 0` but the upstream flag says overdue, or the reverse —
say so in `notes` rather than silently preferring one: "Companies House flags this filing as
overdue, but the due date it publishes ({due_date}) is not yet past relative to today ({today}).
The register's own view may be more current than this cached record."

### 5.5 `DEFERRED` and `VERIFY` — do not implement in T15b

Real obligations and real data, deliberately left out because getting them wrong is worse than
omitting them. Each needs a source check before it ships.

- **Corporation tax — `VERIFY`, and omitted from the computed list.** The *rules* are sourced, from
  <https://www.gov.uk/prepare-file-annual-accounts-for-limited-company/deadlines>: payment is due
  "9 months and 1 day after your 'accounting period' for Corporation Tax ends" and the Company Tax
  Return "12 months after your accounting period for Corporation Tax ends". What is **not** sourced
  is the three things we would need to turn those rules into a date for a specific company:
  (a) HMRC's *accounting period* is not the Companies House accounting reference period and is not
  published by Companies House — a first period longer than 12 months is split into two;
  (b) whether the company is within the charge to corporation tax at all depends on the legal form,
  and several forms in §7 are not — an **LLP is tax-transparent** and files a partnership return,
  not a CT600;
  (c) the "9 months and 1 day" payment date does not apply to companies with taxable profits above
  £1.5m, which pay by quarterly instalments — and Companies House publishes no profit figure.
  Corporation tax is HMRC's, not Companies House's; `rules_markdown()` states the rules in prose so
  an agent that *knows* the accounting period can apply them, and the module emits no date.
- **VAT returns** — HMRC, one month and seven days after each VAT period end. We cannot see whether
  a company is VAT-registered, let alone its stagger group. `VERIFY`.
- **PAYE / RTI full payment submission** — on or before each payday. Companies House publishes no
  employee count, so we cannot even tell whether the duty exists.
- **PSC register updates** — event-driven (14 days to update the company's own register, 14 more to
  notify Companies House), not a calendar deadline. Not computable from a profile.
- **Overseas entity update statement** — a `registered-overseas-entity` must file an update
  statement within 14 days of each anniversary of registration. Plausible and probably derivable
  from `date_of_creation`, but unconfirmed against a source and untested against a live record.
  `VERIFY`.
- **Charity accounts** — a `charitable-incorporated-organisation` files with the Charity Commission
  (or OSCR in Scotland), not with Companies House, on a different clock. `VERIFY`; note it, do not
  compute it.
- **CIC34** — the community interest company report is filed *with* the accounts, so it shares the
  `annual_accounts` date rather than needing its own `kind`. Surfaced as a note (§2.1).
- **SIC code descriptions** — Companies House publishes a condensed SIC 2007 list; bundling ~730
  rows is a data-file decision, not a mapping decision. `IndustryCode.description` stays `None`.
- **Officers, charges, PSCs, insolvency, filing history, UK-establishment lists** — separate
  endpoints, the exact analogue of Norway's deferred `/roller`.
- **Share capital** — in the confirmation statement's `statement_of_capital`, not in the profile.
- **First accounts after incorporation.** The statutory rule is sourced — GOV.UK, *Life of a company
  — Part 1 Accounts*: within "21 months of the date of incorporation for private companies, or 3
  months from the accounting reference date (whichever is longer)", and "18 months … for public
  companies" — and it is quoted in `rules_markdown()`. It is nonetheless **not computed**, because
  picking the right *year* for the first accounting reference date from a bare `{day, month}` is
  ambiguous once a company has shortened or extended its first period, and Companies House publishes
  `accounts.next_accounts.due_on` for a company from the day it is incorporated. Step 1 of the
  ladder already answers this case correctly; a second, guessier answer would only be able to
  disagree with it.

---

## 6. Client behaviour — `registries/gb/client.py`

- **Base URL:** `https://api.company-information.service.gov.uk`
- **Auth:** `httpx.BasicAuth(api_key, "")` — key as username, empty password (§1.1).
- **Key:** `os.environ.get("COMPANIES_HOUSE_API_KEY", "").strip()`, read **inside** the request path.
  Empty → the error below, before any socket is opened.
- **Timeout:** 5 s total per attempt (`httpx.Timeout(5.0)`), same as Norway.
- **Retry:** exactly one, only on a timeout or a 5xx, never on a 4xx (a 429 included — retrying a
  rate limit is how you get the operator's key blocked). 250 ms backoff.
- **User-Agent:** the same contract as `registries/no/client.py`:
  `registry-mcp/{__version__} (+https://github.com/foretak/registry-mcp; {contact})` from
  `REGISTRY_MCP_CONTACT_EMAIL`.
- **Headers:** `Accept: application/json`.
- **Connection reuse:** one module-level `httpx.AsyncClient`, created lazily, closed by an
  `aclose()` that `CompaniesHouseRegistry.aclose` delegates to (D-014). **This is mandatory, not
  optional** — the module keeps a shared client, so without the override the sockets leak.
- **Rate limiter:** an in-process async token bucket, capacity 600, refill 600/300 s = 2.0 tokens/s,
  one token per HTTP attempt (the retry costs a second token). `acquire()` waits at most 2.0 s for a
  token and then raises `RegistryError(RATE_LIMITED)`. It is a guard against a runaway loop burning
  the operator's shared key, not a scheduler: it must never make a normal request slower than a few
  milliseconds. Because the key can be shared with the operator's other tools, an upstream 429 is
  still handled below.
- **Never log the key.** Not at DEBUG, not in a `repr`, not in `details`. `api_key_env` publishes the
  variable's *name*; nothing publishes its value.

**Status handling:**

| Upstream | Result |
|---|---|
| 200 | Map and return |
| 401 | `RegistryError(upstream_error)` — the key is missing, wrong or revoked. Hint names `COMPANIES_HOUSE_API_KEY` and the sign-up URL. **Confirmed live**: a bad key gives `401` with body `{"error": "Invalid Authorization", "type": "ch:service"}` and header `www-authenticate: Invalid or no Authorisation header has been provided` |
| 403 | Same handling as 401, defensively. Not observed |
| 404 | `RegistryError(not_found)`. There is no `/underenheter` second chance to take: `/company/{n}` covers UK establishments (`BR…`) and overseas companies (`FC…`) too |
| 429 | `RegistryError(rate_limited)`; hint carries `Retry-After` if present, else the `x-ratelimit-reset` epoch rendered as a wait, else "about five minutes" |
| 5xx (after the retry) | `RegistryError(upstream_error)` |
| timeout (after the retry) | `RegistryError(upstream_timeout)` |
| anything else | `RegistryError(upstream_error)` naming the status |

**Do not echo upstream error bodies into `message` or `hint`.** Unlike brreg, which returns an empty
404 body, Companies House returns JSON:

```json
{"timestamp": "2026-09-04T16:07:18.488455029",
 "message": "404 NOT_FOUND \"Resource not found for company profile 99999999\"",
 "request_id": "zI3njc2o3Rw3gteEpBEpcqbHFut_"}
```

That `message` is a Java framework string, not something to show an agent, and `timestamp` would
make our output non-deterministic. Put `request_id` in `RegistryError.details` when present — it is
what Companies House support asks for — and write our own message and hint (D-007).

A 429 maps to `rate_limited` (HTTP 429) rather than to `upstream_error` (HTTP 502). This differs
from `registries/no/client.py`, which maps brreg's 429 to `upstream_error`. `rate_limited` is the
better answer — it gives the agent the right status and a retry window — and D-007's status table
already contains it. **Do not "fix" Norway to match as part of T15b**; record it for T15e.

**No key:**

```python
RegistryError(
    ErrorCode.UPSTREAM_ERROR,
    "This deployment has no Companies House API key, so UK company data cannot be fetched.",
    hint=(
        "Call list_countries to see which countries can answer right now. If you run this "
        "server yourself, set the COMPANIES_HOUSE_API_KEY environment variable — a key is "
        "free from https://developer.company-information.service.gov.uk/get-started — and "
        "restart it."
    ),
    country="GB", registry="companies-house",
)
```

`upstream_error` (502) rather than `not_implemented` (501): the module is implemented, the
deployment is unconfigured. And rather than `internal_error`, because it is not a bug — it is a
choice the operator made. The hint carries both branches because the agent does not know which side
of the deployment it is on.

**`not_found`** — message: `"No company with number {id} is on the Companies House register."`
hint (must not repeat the message, per the T10 review's N2):

> "The number is well-formed, so it may never have been issued, or the company may have been removed
> from the register. Note that sole traders and ordinary partnerships are not registered at
> Companies House at all. Call search_company with the business name instead."

---

## 7. Legal-form table

`registries/gb/rules.py :: COMPANY_TYPES`, keyed by the profile's `type` value. Codes are the
Companies House enum, taken from the `companyProfile` resource on 2026-09-04. English labels and
duty columns are ours.

`board` = must have directors registered with the registrar. `accounts` = must deliver annual
accounts **to Companies House**. `period` = the accounts-filing period this module will compute from
(§5.4 step 3); a blank means we do not compute and use only the register's own date. `None` means
"depends on facts the register does not publish".

### Confirmed forms

| `type` | English | Limited liability | board | accounts | period |
|---|---|---|---|---|---|
| `ltd` | Private limited company | yes | yes | yes | **private, 9 months** |
| `plc` | Public limited company | yes | yes | yes | **public, 6 months** |
| `llp` | Limited liability partnership | yes | `None` (designated members, not a board) | yes | **private, 9 months** |
| `private-limited-guarant-nsc` | Private company limited by guarantee without share capital | yes | yes | yes | **private, 9 months** |
| `private-limited-guarant-nsc-limited-exemption` | Private company limited by guarantee, exempt from using "limited" | yes | yes | yes | **private, 9 months** |
| `private-limited-shares-section-30-exemption` | Private company limited by shares, section 30 exemption | yes | yes | yes | **private, 9 months** `VERIFY` |
| `uk-establishment` | UK establishment of an overseas company | inherits | no | no | — (sub-unit; the parent files) |

`ltd`, `plc`, `llp` and `private-limited-guarant-nsc` are live-confirmed by the fixtures of §1.4 and
the arithmetic of §1.5; `private-limited-guarant-nsc-limited-exemption` is confirmed as a *form* by
`ch_04374209.json` (in liquidation, so it proves nothing about the period, but its overdue accounts
run 9 months from 2024-03-31 to 2024-12-31 — consistent).
`private-limited-shares-section-30-exemption` keeps `VERIFY`: no live example was found. All three
are private companies by the definition in their own type name, so Companies Act 2006 s.442(a) gives
them 9 months.

`uk-establishment` is live-confirmed by `ch_BR026263.json`, which carries
`branch_company_details.parent_company_number` and no `accounts` object at all.

### Classified, but no computed accounts period

Labels are ours; duty columns are `None` unless the entry is definitionally clear. These forms use
the register's published date or get no accounts deadline at all.

| `type` | English | Limited liability | board | accounts |
|---|---|---|---|---|
| `private-unlimited` | Private unlimited company with share capital | **no** | yes | `None` — unlimited companies are generally exempt from *filing* accounts (CA 2006 s.448) `VERIFY` |
| `private-unlimited-nsc` | Private unlimited company without share capital | **no** | yes | `None`, same reason |
| `old-public-company` | Old public company (never re-registered under the 1980 Act) | yes | yes | `None` |
| `limited-partnership` | Limited partnership | partly (general partner unlimited) | no | `None` |
| `scottish-partnership` | Scottish partnership | no | no | `None` |
| `charitable-incorporated-organisation` | Charitable incorporated organisation | yes | `None` | `None` — files with the Charity Commission, not Companies House |
| `scottish-charitable-incorporated-organisation` | Scottish charitable incorporated organisation | yes | `None` | `None` — files with OSCR |
| `registered-society-non-jurisdictional` | Registered society | yes | `None` | `None` — files with the Financial Conduct Authority |
| `industrial-and-provident-society` | Industrial and provident society | yes | `None` | `None` — as above |
| `oversea-company` | Overseas company | inherits | `None` | `None` — see `foreign_company_details.accounting_requirement` |
| `registered-overseas-entity` | Overseas entity (register of overseas entities) | inherits | `None` | `None` — the duty is an annual update statement, §5.5 |
| `european-public-limited-liability-company-se` | European company (Societas Europaea) | yes | yes | `None` |
| `royal-charter` | Royal charter body | `None` | `None` | `None` |
| `unregistered-company` | Unregistered company | `None` | `None` | `None` |
| `northern-ireland` | Northern Ireland company (legacy record) | `None` | `None` | `None` |
| `northern-ireland-other` | Northern Ireland entity (legacy record) | `None` | `None` | `None` |
| `investment-company-with-variable-capital` | Investment company with variable capital | yes | `None` | `None` |
| `icvc-securities` | ICVC — securities | yes | `None` | `None` |
| `icvc-warrant` | ICVC — warrant | yes | `None` | `None` |
| `icvc-umbrella` | ICVC — umbrella | yes | `None` | `None` |
| `protected-cell-company` | Protected cell company | yes | `None` | `None` |
| `assurance-company` | Assurance company | `None` | `None` | `None` |
| `eeig` | European economic interest grouping | no | `None` | `None` |
| `further-education-or-sixth-form-college-corporation` | Further education or sixth form college corporation | `None` | `None` | `None` |
| `converted-or-closed` | Converted or closed entity | `None` | `None` | `None` |
| `other` | Other | `None` | `None` | `None` |

Any `type` **not** in either table maps to `legal_form = None`, all three duty fields `None`, a
`notes` entry saying the legal form is not classified, and — following D-009(a) — **no deadlines at
all**, not even from the register's own published dates. An unclassified form is a form we cannot
say anything about.

### `subtype`

`community-interest-company` and `private-fund-limited-partnership`. The subtype is appended to the
English `legal_form` label in parentheses and, for a CIC, produces the §2.1 note about the CIC34
report and the asset lock. It gets no field of its own (§15).

Live-confirmed on `ch_13507518.json`: `type: "private-limited-guarant-nsc"` with
`subtype: "community-interest-company"` **and** the deprecated `is_community_interest_company: true`
alongside it. Note that the CIC subtype sits on a *guarantee* company, not on `ltd` — so
`legal_form_code` stays `"private-limited-guarant-nsc"` and the label becomes "Private company
limited by guarantee without share capital (community interest company)". Anyone who assumed a CIC
is an `ltd` will mis-bucket its accounts period; it is 9 months either way, but for the guarantee
reason, not the `ltd` reason.

### Sole traders are not on this register

There is **no UK register of sole traders or of ordinary (unlimited) partnerships.** A search for
"Dave's Plumbing" will return nothing, and that is a correct answer, not a failure. This sentence
belongs in the zero-hit search hint (§4), in the `not_found` hint (§6) and in `rules_markdown()`
(§13); it is the single most common wrong assumption an agent brings to UK company data.

---

## 8. Status derivation

From `company_status` alone, one value to one status — no precedence chain, because Companies House
publishes a single status rather than Norway's four independent booleans.

| `company_status` | `CompanyStatus` | `status_detail` |
|---|---|---|
| `active` | `ACTIVE` | "Active on the Companies House register." |
| `dissolved` | `DISSOLVED` | "Dissolved on {date_of_cessation}. The record remains on the register as history." |
| `liquidation` | `UNDER_LIQUIDATION` | "In liquidation. Companies House does not say whether the liquidation is voluntary or compulsory." |
| `receivership` | `UNDER_LIQUIDATION` | "In receivership: a receiver has been appointed over the company's assets." |
| `administration` | `UNDER_LIQUIDATION` | "In administration: an administrator is running the company." |
| `voluntary-arrangement` | `UNDER_LIQUIDATION` | "Subject to a company voluntary arrangement with its creditors." |
| `insolvency-proceedings` | `UNDER_LIQUIDATION` | "Subject to insolvency proceedings." |
| `converted-closed` | `DISSOLVED` | "Converted or closed on {date_of_cessation}." |
| `closed` | `DISSOLVED` | "Closed on {date_of_cessation}." `VERIFY` — no live example found |
| `removed` | `DELETED` | "Removed from the register." |
| `registered` | `ACTIVE` | "Registered on the register of overseas entities." `VERIFY` |
| `open` | `ACTIVE` | "Open on the register." Live-confirmed on `ch_BR026263.json`: a UK establishment's status is `open`, not `active` — so an `is_active` check that only tests for `"active"` upstream would report every branch of a foreign company as inactive |
| *(absent)* | `UNKNOWN` | "Companies House holds no status for this record." Live: the stub profiles of §2.2 (`CE020555`, `RS007790`) omit the key entirely |
| *(unrecognised)* | `UNKNOWN` | "Companies House returned a status this module does not recognise ({raw!r})." |

Three things this table deliberately does **not** do:

1. **`UNDER_COMPULSORY_LIQUIDATION` is never used.** `company_status` does not distinguish a members'
   voluntary liquidation from a court-ordered winding-up, and `company_status_detail` does not
   either. Asserting "compulsory" from a value that does not say so would be a guess. The enum member
   stays available for a country whose register does distinguish them; `status_detail` carries the
   honest sentence for Britain. The consequence is that `UNDER_LIQUIDATION` in GB carries less
   information than in NO — which is why §5.4 suspends deadlines for it while Norway does not.
2. **`BANKRUPT` is never used.** UK bankruptcy applies to individuals. A company is not bankrupt; it
   is in liquidation, administration, receivership, or an arrangement.
3. **`has_insolvency_history` never affects the status.** It means insolvency filings *exist in the
   history*, which is compatible with `active` — a company that exited administration years ago
   still carries it. It produces the §2.1 note and nothing else. Treating it as a status would tell
   an agent that a healthy trading company is insolvent, which is close to the worst error this
   product can make. (`ch_04374209.json` is the honest case: `has_insolvency_history: true` **and**
   `company_status: "liquidation"` — the status is what said so, and `has_been_liquidated` is
   `false` on that same payload, which is why that deprecated field is not read at all.)

`company_status_detail` never changes the `CompanyStatus` either. It refines the sentence and adds a
note:

| `company_status_detail` | Note |
|---|---|
| `active-proposal-to-strike-off` | §2.1's strike-off sentence |
| `transferred-from-uk` | "This company was transferred from the UK register." |
| `petition-to-restore-dissolved` | "A petition to restore this dissolved company to the register has been made." |
| `transformed-to-se` | "This company was transformed into a European company (SE)." |
| `converted-to-plc` | "This company was converted to a public limited company." |
| *(unrecognised)* | "Companies House records an additional status detail for this company: {value}." |

`date_of_cessation` — **read the definition before using it**: "The date which the company was
converted/closed, dissolved or removed." It covers three different endings, it is not a status, and
it is not the analogue of Norway's `slettedato`. It maps to `deregistered_at` and it never drives
status derivation; `company_status` does. A record can carry `date_of_cessation` while
`company_status` is `dissolved` (still on the register) or `removed` (gone) — the status is what
tells them apart.

Any status other than `ACTIVE` adds a plain-English `notes` entry, because an agent about to pay an
invoice must see it without reading an enum table.

---

## 9. Cache

Per D-006, unchanged: SQLite, one file, `REGISTRY_MCP_CACHE_PATH`.

- Keys: `"GB:companies-house:entity:{company_number}"` and
  `"GB:companies-house:search:{casefolded-stripped-query}:{limit}"`.
- TTL 24 h for `ok`, 1 h for `not_found`.
- A hit sets `cached=True` and preserves the **original** `fetched_at`.
- `REGISTRY_MCP_CACHE_TTL_SECONDS` / `REGISTRY_MCP_CACHE_DISABLED=1` behave as for Norway.
- A cache failure is logged and ignored, never turned into a `RegistryError`.

The cache matters more here than in Norway: it is what keeps a shared 600-per-5-minutes key from
being spent on repeat questions, and Companies House data changes at most daily.

One interaction to be aware of: the deadline dates are `next_due` values *inside* the cached report,
so a company that files during our 24 h window keeps its old due date until the entry expires.
`DeadlineReport.today` and `CompanyReport.cached` / `fetched_at` are what make that visible, which
is exactly the reason D-006 preserves the original `fetched_at`.

---

## 10. Errors

`{"error": {"code", "message", "hint"}}` — exactly `RegistryError.to_dict()`, byte-identical on REST
and MCP (D-007). Codes this module raises: `invalid_id`, `not_found`, `bad_request`, `rate_limited`,
`upstream_error`, `upstream_timeout`.

Every hint names a concrete next call. The three that carry the most weight for the UK:

- `invalid_id` → the 8-character shape, a zero-padding example, and `search_company` (§5.1.1).
- `not_found` → that sole traders and ordinary partnerships are not on this register (§6).
- `upstream_error` with no key → `list_countries`, plus the env var and the free sign-up URL (§6).

---

## 11. Logging

`core/log.py`, unchanged (`NORBIZ_SPEC.md` §11). `query` is the company number or the search string.
**Never the API key**, never a header.

---

## 12. Confidence

D-005 anchors, unchanged: 1.0 for an identifier lookup, then 0.95 / 0.8 / 0.6 / 0.4 for search hits
(§4). `confidence_basis` spells the reason out in English so an agent can quote it.

---

## 13. `rules_markdown()`

Served as the MCP resource `registry://rules/GB`. It must contain, in prose, at least:

1. What the register is, who runs it, and the licence position of §1.8.
2. **That sole traders and ordinary partnerships are not registered.**
3. The identifier shape: 8 characters, zero-padded, prefix list, **no check digit**, so a
   well-formed number is not evidence a company exists.
4. **That Companies House deadlines do not move for weekends or bank holidays**, quoting the GOV.UK
   sentence of §5.3 — stated explicitly because it is the opposite of the Norwegian rule the same
   server also serves.
5. The two computed deadline kinds, and that their dates come from the register itself wherever the
   register publishes them.
6. The statutory periods, with their sources: 9 months private / 6 months public from the end of the
   accounting reference period; 14 days after the review period for the confirmation statement; and
   the first-accounts rule (21 months private / 18 months public from incorporation, or 3 months from
   the accounting reference date, whichever is longer) **flagged as documented but not computed**.
7. Corporation tax as prose only: 12 months after the accounting period ends for the CT600, 9 months
   and one day for payment — with HMRC named as the authority, the accounting-period caveat, and the
   fact that an LLP files no CT600.
8. What Companies House does **not** publish: employee counts, VAT registration, turnover, share
   capital, email, phone and website.
9. That officers, PSCs, charges and filing history are separate endpoints not yet exposed.

---

## 14. Numbered rules test list

**T15b implements exactly this list**, one test function per number, named `test_NN_<slug>`, in
`tests/gb/test_rules.py` (1–72), `tests/gb/test_mapping.py` (73–93) and `tests/gb/test_client.py`
(94–105), with 106–109 marked `@pytest.mark.live`. Fixed `today` values throughout; nothing reads the
clock. Every date below was read out of a saved fixture or computed against the real calendar — if
an implementation disagrees, the implementation is wrong.

### A. `validate_id` — normalisation and shape

1. `"00445790"` → `"00445790"` (canonical 8-digit number, unchanged).
2. `"00000006"` → `"00000006"`.
3. `"445790"` → `"00445790"` (zero-padded).
4. `"1234"` → `"00001234"`.
5. `"6"` → `"00000006"`.
6. `"00 445 790"` → `"00445790"` (spaces stripped).
7. `"0044-5790"` → `"00445790"` (hyphen stripped).
8. `"00.445.790"` → `"00445790"` (dots stripped).
9. `"sc090312"` → `"SC090312"` (upper-cased).
10. `"SC12345"` → `"SC012345"` (digits padded to fill 8, prefix preserved).
11. `"SC1"` → `"SC000001"`.
12. `"NI1234"` → `"NI001234"`.
13. `"oc303675"` → `"OC303675"`.
14. `"R0123456"` → `"R0123456"` (the single-letter `R0` prefix passes unchanged).
15. `"BR012345"` → `"BR012345"` (UK establishment).
16. `"OE123456"` → `"OE123456"` (a prefix newer than the prefix table — the shape rule must accept it).
17. `""` → raises `invalid_id`.
18. `"123456789"` → raises `invalid_id` (9 digits; never truncated to 8).
19. `"SC1234567"` → raises `invalid_id` (9 characters).
20. `"ABCDEFGH"` → raises `invalid_id` (8 characters, no digit).
21. `"1SC12345"` → raises `invalid_id` (starts with a digit but is not all digits).
22. `"SC12#456"` → raises `invalid_id` (a character survives stripping that is not `[A-Z0-9]`).
23. `"GB123456789"` → raises `invalid_id`, and the hint contains `"VAT"` — the VAT-number branch.
24. The error from test 18 has `code == ErrorCode.INVALID_ID`, a non-empty `hint`, and the string
    `"search_company"` in the hint.
25. `validate_id` never consults the prefix table: a made-up-but-well-shaped `"QQ000001"` is
    **accepted**, because rejecting an unknown prefix would break the day Companies House adds one.

### B. Legal-form mapping

26. `"ltd"` → `"Private limited company"`, `limited_liability=True`, `has_board_duty=True`,
    `has_annual_accounts_duty=True`, accounts period 9 months.
27. `"plc"` → `has_annual_accounts_duty=True`, accounts period **6** months.
28. `"llp"` → `limited_liability=True`, `has_board_duty=None`, `has_annual_accounts_duty=True`,
    accounts period 9 months.
29. `"private-unlimited-nsc"` → `limited_liability=False`, `has_annual_accounts_duty=None`, **no**
    computed accounts period.
30. `"uk-establishment"` → `has_annual_accounts_duty=False`, and the mapper reports it as a sub-unit.
31. `"limited-partnership"` → `limited_liability` is not `True`, `has_annual_accounts_duty=None`.
32. `"charitable-incorporated-organisation"` → `has_annual_accounts_duty=None`, and no computed
    period (it files with the Charity Commission).
33. `"oversea-company"` and `"registered-overseas-entity"` → both `has_annual_accounts_duty=None`.
34. `"royal-charter"` → all three duty fields `None`.
35. `"not-a-real-type"` → `legal_form is None`, all three duty fields `None`, and a `notes` entry
    recording that the form is unclassified.
36. `type="ltd"` with `subtype="community-interest-company"` → `legal_form` contains
    `"community interest company"`, `legal_form_code == "ltd"` (the subtype does not overwrite it),
    and `notes` mentions the CIC34 report.

### C. Status derivation

37. `company_status="active"` → `ACTIVE`, `is_active is True`, `notes == []`.
38. `company_status="dissolved"`, `date_of_cessation="2018-07-10"` → `DISSOLVED`,
    `deregistered_at == date(2018, 7, 10)`, `is_active is False`.
39. `company_status="liquidation"` → `UNDER_LIQUIDATION`, and `status_detail` says Companies House
    does not distinguish voluntary from compulsory.
40. `company_status="administration"` → `UNDER_LIQUIDATION` (**not** `UNDER_COMPULSORY_LIQUIDATION`).
41. `company_status="receivership"` and `"voluntary-arrangement"` → both `UNDER_LIQUIDATION`.
42. `company_status="removed"` → `DELETED`.
43. `company_status="converted-closed"` → `DISSOLVED`.
44. A payload with no `company_status` key → `UNKNOWN`, and `status_detail` says so.
45. `company_status="wibble"` (an enum value we have never seen) → `UNKNOWN`, not a crash, and the
    raw value appears in `status_detail`.
46. `company_status="active"` with `has_insolvency_history=True` → still `ACTIVE`, plus a `notes`
    entry about insolvency history. **No status may ever be `BANKRUPT` for GB.**
47. `company_status="active"` with `company_status_detail="active-proposal-to-strike-off"` → still
    `ACTIVE`, `is_active is True`, and a `notes` entry mentioning strike-off.
48. `registered_office_is_in_dispute=True` → a `notes` entry warning that the address may have been
    replaced.
49. `undeliverable_registered_office_address=True` → a `notes` entry.
50. Any status other than `ACTIVE` adds at least one entry to `report.notes`.

### D. Deadlines

Subject is an active `ltd` unless stated. `today` is given per test.

51. `ch_09446231.json` (`accounts.next_accounts.due_on="2027-12-31"`), `today=2026-09-04` → one
    `annual_accounts` deadline with `due_date == date(2027, 12, 31)` and an `applies_because` saying
    the date comes from Companies House, not from a calculation.
52. The same payload with `next_accounts.due_on` deleted, leaving only the deprecated
    `accounts.next_due="2027-12-31"` → the same `due_date`; the second rung works.
53. Both deleted, `accounts.next_accounts.period_end_on="2027-03-31"`, `type="ltd"` → computed
    `due_date == date(2027, 12, 31)` (9 months).
54. Same rung from `ch_OC303675.json`: `type="llp"`, `period_end_on="2026-05-31"` →
    `due_date == date(2027, 2, 28)` — nine months with the month-end clamp.
55. Same rung from `ch_00445790.json`: `type="plc"`, `period_end_on="2027-02-26"` →
    `due_date == date(2027, 8, 26)`. Six months, **and** proof the computation runs from
    `period_end_on` and not from `accounting_reference_date`, which on that payload is the *string*
    pair `{"day": "26", "month": "02"}`.
56. Same rung from `ch_SC090312.json`: `type="plc"`, `period_end_on="2026-12-31"` →
    `due_date == date(2027, 6, 30)`.
57. Same rung from `ch_13948759.json`: `type="private-limited-guarant-nsc"`,
    `period_end_on="2027-03-31"` → `due_date == date(2027, 12, 31)` (9 months — the guarantee forms
    are private companies).
58. `ch_FC032315.json` unmodified — `next_accounts` present with **no** `due_on` and no
    `accounts.next_due`, `type="oversea-company"` → **no** `annual_accounts` deadline, and a `notes`
    entry explaining that the form has no period this module is confident about. This is step 4 of
    the ladder, reached by a real payload.
59. `ch_00445790.json` (`confirmation_statement.next_due="2027-07-02"`) → one
    `confirmation_statement` deadline with that `due_date`.
60. The same payload with `next_due` deleted, `next_made_up_to="2027-06-18"` → computed
    `due_date == date(2027, 7, 2)` (+14 days).
61. Same rung from `ch_OC303675.json`: `next_made_up_to="2026-07-31"` →
    `due_date == date(2026, 8, 14)`.
62. **Every returned deadline has `statutory_date == due_date` and `rolled_forward is False`**,
    including one whose `due_date` falls on a Sunday: `next_due="2027-01-31"` (a Sunday) stays
    2027-01-31 and is not moved to 1 February.
63. `next_due="2026-08-14"` with `today=date(2026, 9, 4)` → `days_until == -21`; a negative
    `days_until` is a valid, expected result (the live overdue DELOITTE LLP case).
64. When Companies House flags `overdue: true` but `days_until >= 0`, a `notes` entry records the
    disagreement, and `days_until` — not the flag — decides.
65. A `dissolved` company gets an empty deadline list plus one note, **even though the payload still
    carries `accounts.next_accounts.due_on`**.
66. A `liquidation` company gets an empty deadline list — GB suspends where NO would not (§5.4).
67. A `uk-establishment` gets an empty deadline list and a `notes` entry naming `parent_id`.
68. A company whose `type` is unclassified gets an empty deadline list even when the payload carries
    both published dates (D-009(a)).
69. The returned list is sorted by `due_date` ascending, then by `kind`; exactly one `Deadline` per
    `kind`; no `kind` appears twice.
70. Every returned `Deadline` has `country == "GB"`, `registry == "companies-house"`, a non-empty
    `applies_because`, a `source_url` on gov.uk, and `days_until == (due_date - today).days`.
71. `deadlines(report, today)` called twice with the same arguments returns equal lists, and the
    result does not change with the process timezone — purity, no clock reads.
72. `registries/gb/` contains no holiday table and never calls
    `core.rules.common.roll_forward` (assert by source inspection or by monkeypatching
    `roll_forward` to raise).

### E. Mapping — every claim bound to a saved fixture

73. `ch_00445790.json` → `name == "TESCO PLC"`, `legal_form_code == "plc"`, `status == ACTIVE`,
    `id == "00445790"`, `id_formatted is None`.
74. Same fixture: `previous_names == ["TESCO STORES (HOLDINGS) PUBLIC LIMITED COMPANY",
    "TESCO STORES (HOLDINGS) LIMITED"]` — newest first.
75. Same fixture: `industry_codes == [IndustryCode(code="47110", description=None,
    scheme="SIC 2007", rank=1)]`.
76. Same fixture: `registered_at == founded_at == date(1947, 11, 27)`,
    `business_register_registered_at is None`, `last_annual_accounts_year == 2026`.
77. Same fixture: `business_address.city == "Welwyn Garden City"`,
    `business_address.postal_code == "AL7 1GA"`, `business_address.country_name == "United Kingdom"`,
    `business_address.country_code == "GB"`.
78. Same fixture: **`registers["charges"] is False`** even though `links.charges` is present. This is
    §1.6 №1 and it is the single most important mapping test in the file.
79. Same fixture: `employees is None`, `employees_reported is False`, `vat_registered is None`,
    `vat_number is None`, `share_capital is None`, `website is None`, `email is None`,
    `phone is None`, `purpose is None`, `sector is None` — every field Companies House does not
    publish is honestly absent, and `notes == []`.
80. `ch_SC090312.json` → `business_address.city is None` and
    `business_address.country_code is None`, because the live payload has neither `locality` nor
    `country`; and `notes` contains the jurisdiction sentence, because `jurisdiction == "scotland"`.
81. `ch_09446231.json` → `legal_form_code == "ltd"`, `has_annual_accounts_duty is True`,
    two `industry_codes` with `rank` 1 and 2 (`"64191"`, `"64999"`), and `notes == []`.
82. `ch_OC303675.json` → `legal_form_code == "llp"`, `limited_liability is True`,
    `has_board_duty is None`.
83. `ch_00000006.json` → `status == DISSOLVED`, `deregistered_at == date(2018, 7, 10)`,
    `is_active is False`, `legal_form_code == "private-unlimited-nsc"`,
    `limited_liability is False`, and `registers["charges"] is True` (that payload really does have
    a charge).
84. `ch_04374209.json` → `status == UNDER_LIQUIDATION`, `registers["insolvency"] is True`, and
    `status is not CompanyStatus.BANKRUPT` — GB never emits `BANKRUPT`.
85. `ch_BR026263.json` → `status == ACTIVE` (from `company_status: "open"`), `is_subunit is True`,
    `parent_id == "FC041146"`, `activity == "Real Estate Consulting"`, `founded_at is None`
    (a UK establishment's `date_of_creation` is its UK registration date, §2), and `notes` names
    `parent_id`.
86. `ch_FC032315.json` → `legal_form_code == "oversea-company"`, `founded_at is None`,
    `activity` comes from `foreign_company_details.business_activity`, and the mapper does not raise
    on `accounts.last_accounts.type == "null"` (§1.6 №2).
87. `ch_CE020555.json` → **constructs without raising**: `status == UNKNOWN`, `is_active is False`,
    `registered_at is None`, `business_address is None`, and `notes` contains both the stub sentence
    and the external-registration-number sentence naming `1187753`.
88. `ch_RS007790.json` → same stub shape, and `notes` contains the `partial_data_available`
    sentence naming the FCA mutuals register.
89. `ch_13507518.json` → `legal_form_code == "private-limited-guarant-nsc"` (**not** `"ltd"`),
    `legal_form` contains `"community interest company"`, and `notes` mentions the CIC34 report.
90. `ch_search_tesco.json` → `SearchResult.total == 356`, `truncated is True`, three hits,
    `hits[0].id == "00445790"`, `hits[0].city == "Welwyn Garden City"`, and a `hint` naming
    `lookup_company`.
91. `ch_search_empty.json` → `SearchResult(hits=[], total=0)`, no exception, and a `hint` that
    mentions sole traders.
92. A search item with **no `company_status` key** (the live CIO shape of §1.6 №6) maps to
    `CompanyStatus.UNKNOWN` rather than raising `KeyError`.
93. Search confidence: an exact case-insensitive `title` match scores 0.95, a prefix match 0.8, an
    all-tokens match 0.6, anything else 0.4 (D-005). `q="tesco"` against `"TESCO PLC"` scores 0.8,
    not 0.95 — the title is longer than the query.

### F. Client — `respx`-mocked, no network

94. With `COMPANIES_HOUSE_API_KEY` unset, `lookup` raises `upstream_error` **without making an HTTP
    request** (assert the mock's call count is 0), and the hint contains both
    `"COMPANIES_HOUSE_API_KEY"` and `"list_countries"`.
95. Importing `registry_mcp.registries.gb` with the environment variable unset succeeds — no
    exception at import time — and `list_countries()` contains `"GB"`.
96. The outgoing request carries an `Authorization: Basic …` header whose base64 body decodes to
    `"{key}:"` — key as username, empty password.
97. The outgoing `User-Agent` contains `registry-mcp` and the value of
    `REGISTRY_MCP_CONTACT_EMAIL`.
98. A 401 returning the live body of `ch_401.json` raises `upstream_error` whose hint names
    `COMPANIES_HOUSE_API_KEY`; a 403 does the same. Neither is retried.
99. A 404 returning the live body of `ch_404.json` raises `not_found` whose hint mentions both
    `search_company` and sole traders, whose `details` carries the upstream `request_id`, and whose
    `message` contains **none** of the upstream body's text. The mock was called exactly **once**.
100. A 429 carrying `Retry-After: 300` raises `rate_limited` whose hint contains `300`; a 429
    carrying only `x-ratelimit-reset` renders a wait from it; a 429 with neither still raises
    `rate_limited` with a usable hint. Never retried — the mock was called exactly once.
101. A 500 followed by a 200 returns the report (exactly one retry, verified by call count); two
    consecutive 500s raise `upstream_error` with exactly two calls, not three.
102. Two identical `lookup` calls: the first has `cached is False`, the second `cached is True` with
    the **same** `fetched_at`, and the second makes no HTTP request.
103. `search(limit=0)` and `search(limit=101)` each raise `bad_request`; `limit=100` does not.
    `search(name="  ")` raises `bad_request` — the API would return 200 for it (§1.6 №8).
104. **The API key appears in no log record, no exception message and no `RegistryError.details`.**
    Drive a 401 and a timeout with a recognisable key value, and assert it is absent from the
    captured log output and from every `to_dict()` produced.
105. The token bucket admits a normal request in under 10 ms and does not serialise concurrent
    lookups of different companies.

### G. Live done-check — network, `@pytest.mark.live`, excluded from CI

106. A live `lookup("00445790")` returns a `CompanyReport` with `cached is False`; a second call
    within the TTL returns `cached is True`.
107. Every Companies House field name used by the mapper is present in the live `00445790` payload,
    or is explicitly listed as optional in §2. Any field this spec names that the live payload does
    not have is a **blocking** finding for `REVIEW.md`, not something to work around.
108. A live `lookup("00000006")` returns `status == DISSOLVED` — the number Companies House uses in
    its own documentation, and the one T15d smoke-tests against `https://api.foretak.dev`.
109. Re-fetch all twelve company fixtures and diff the mapped `CompanyReport` against the report
    mapped from the stored file, ignoring `fetched_at` and `cached`. A difference means the register
    changed, not that we broke — but it must be seen and the fixture refreshed, not silently
    tolerated.

---

## 15. Deliberately not mapped

Fields Companies House returns that this module reads and drops, or never reads. If T15b finds a
caller that needs one, add it to `core/models.py` in a follow-up — **do not smuggle it into
`notes`**.

| Field | Why not |
|---|---|
| `etag` | Resource versioning for conditional requests; we cache by TTL (D-006), not by ETag |
| `can_file` | A filing-service capability flag, meaningless to a read-only lookup |
| `has_been_liquidated` | Deprecated; superseded by `links.insolvency`, already read into `registers` |
| `is_community_interest_company` | Deprecated; superseded by `subtype`, already read into `legal_form` |
| `accounts.last_accounts.made_up_to` | Deprecated mirror of `period_end_on`; read only as a fallback |
| `accounts.next_made_up_to` | Deprecated mirror of `next_accounts.period_end_on`; ditto |
| `accounts.overdue` | Deprecated mirror of `next_accounts.overdue`, which is itself only corroboration (§5.4.1) |
| `accounts.last_accounts.type` | The 17-value accounts-type enum (`micro-entity`, `dormant`, `total-exemption-full`, …). Genuinely interesting — it is the closest thing Companies House publishes to a size signal — but there is no field for it and inventing one from a single country is how a contract rots. Candidate for a follow-up decision |
| `accounts.last_accounts.period_start_on` | We keep only the year, in `last_annual_accounts_year` |
| `accounts.accounting_reference_date` | Used for nothing: §5.4 computes from `period_end_on`, which is the date the deadline actually runs from |
| `annual_return.*` | A filing abolished in June 2016. Its presence produces a `notes` entry (§2.1) and never a deadline — telling an agent to make a filing that no longer exists would be worse than silence. No fixture carries one; `VERIFY` the shape if T15b finds a record that does |
| `has_super_secure_pscs` | Undocumented but sent on most profiles (§1.6 №7). It counts *withheld* PSCs and means nothing without the PSC endpoint (`DEFERRED`) |
| `has_been_liquidated` | Deprecated **and unreliable**: `false` on `ch_04374209.json`, a company actually in liquidation. Read `company_status` |
| `foreign_company_details.legal_form` | Sent but undocumented (`"Societe Par Actions Simplifiee (Private Limited Company)"` on `FC032315`). Tempting for `legal_form_local`, but it is the form under *foreign* law while `legal_form_code` is the Companies House type — two different taxonomies in one field is how a contract rots |
| `confirmation_statement.last_made_up_to` | Historical; only `next_due` / `next_made_up_to` drive a deadline |
| `jurisdiction` | No dedicated field on `CompanyReport`. Surfaced as a note when it is not `england-wales` (§2.1), and largely inferable from the number prefix (§5.1.2). If a caller needs it structurally, that is a decision with evidence, not a field added on spec |
| `subtype` | Folded into the `legal_form` label and, for a CIC, into `notes` (§7) |
| `super_secure_managing_officer_count` | Overseas-entity specific, and a count of *withheld* officers — meaningless without the officers endpoint (`DEFERRED`) |
| `external_registration_number` | **Now mapped, into `notes`** (§2.1) — the live pass changed this call. It has no dedicated field because it needs a companion field naming *which* register, but on the stub profiles of §2.2 it is the only actionable fact in the payload, and dropping it would leave an agent with nothing |
| `last_full_members_list_date` | Legacy annual-return artefact |
| `partial_data_available` | Read, but into `notes` rather than a field (§2.1) |
| `corporate_annotation[].type` / `.created_on` | Only the human-readable message reaches `notes` |
| `links.*` | Read for `registers["charges"]` / `["insolvency"]` only. The rest address the `DEFERRED` endpoints of §1.3 |
| `foreign_company_details.*` | Only `business_activity` is mapped, to `activity`. The accounting-requirement subtree describes a *foreign* filing regime we do not model |
| `branch_company_details.business_activity` / `.parent_company_name` | `business_activity` → `activity`; the parent *name* is dropped because `parent_id` is what an agent calls next |
| `service_address` | Mapped to `postal_address`, but only overseas entities have one — `VERIFY` |
| Search `matches`, `snippet`, `description`, `description_identifier`, `address_snippet`, `kind` | Presentation and relevance metadata. Confidence is ours (D-005), computed from `title`, so that GB and NO score comparably |
| `start_index` / pagination | `DEFERRED` (§4) |
| `restrictions` search parameter | `DEFERRED`, and deliberately not `active-companies` (§4) |

---

## 16. What T15b owns

`src/registry_mcp/registries/gb/{__init__,client,mapping,rules}.py`, the one import line in
`src/registry_mcp/registries/__init__.py`, and `tests/gb/`.

**There is no `holidays.py`** (§5.3), and **the fixtures already exist**: T15a saved sixteen live
responses under `tests/fixtures/ch_*.json` (§1.4). T15b consumes them; it does not need a key to
build or to test. A key is needed only for the four `@pytest.mark.live` tests (106–109), which are
excluded from CI.

It may also edit the seven suite tests that hard-code the country list, and must switch
`test_unsupported_country` from `SE` to `ZZ` (T10 carry-over, restated in `tasks/T15.md`).

It may **not** edit `core/`, `api/` or `mcp/`. If a shape is wrong, that is a finding for
`PROGRESS.md` and Opus A decides — a silently widened model breaks the REST/MCP parity that D-004
exists to guarantee. The two `core/` changes this second country needed are already made, by the
architect, in D-017.
