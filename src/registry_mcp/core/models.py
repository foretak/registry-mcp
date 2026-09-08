"""Country-neutral response models for `registry-mcp`.

Every model here is part of the public contract: the REST API (``api/``) and the
MCP server (``mcp/``) MUST serialise exactly these shapes, with the same field
names, so that an agent gets an identical document whichever surface it calls.

Design rules (see ``DECISIONS.md`` D-004):

* Field names are ``snake_case`` English. No Norwegian ever leaks into a model
  name or field name — Norwegian vocabulary appears only inside *values*
  (``legal_form_local``, ``status_detail``, ``local_name``) and in
  ``registries/no/``.
* Dates are ``datetime.date`` (serialised as ISO-8601 ``YYYY-MM-DD``);
  timestamps are timezone-aware ``datetime`` in UTC.
* Every model that can be returned to a caller carries ``country`` (ISO-3166-1
  alpha-2, upper-case) and ``registry`` (a short lower-case registry slug, e.g.
  ``"brreg"``).
* Unknown is ``None``, never ``""`` or ``0``. An agent must be able to tell
  "the registry says zero employees" from "the registry does not say".
* Models are ``extra="forbid"`` so a typo in a registry module fails loudly at
  construction time rather than silently producing a field nobody reads.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "Address",
    "BalanceSheet",
    "Charge",
    "ChargeBlock",
    "CompanyReport",
    "CompanyStatus",
    "CountriesResponse",
    "CountryInfo",
    "Deadline",
    "DeadlineRecurrence",
    "DeadlineReport",
    "ErrorBody",
    "ErrorCode",
    "ErrorEnvelope",
    "FiledDocument",
    "FilingHistory",
    "FinancialPeriod",
    "FinancialSummary",
    "IncomeStatement",
    "IndustryCode",
    "InsolvencyBlock",
    "InsolvencyCase",
    "InsolvencyEvent",
    "PublishedDeadline",
    "RegistryError",
    "SearchHit",
    "SearchResult",
    "SourceRef",
    "Surface",
    "ValidationResult",
]


class _Base(BaseModel):
    """Shared model configuration."""

    model_config = ConfigDict(extra="forbid", frozen=False, populate_by_name=True)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CompanyStatus(StrEnum):
    """Normalised lifecycle status of a registered entity.

    The mapping from national flags to these values is the registry module's
    job; the values themselves are country-neutral so an agent can branch on
    them without knowing which country it is looking at.

    Precedence when several national flags are true is defined per registry
    (for Norway: ``deleted`` > ``bankrupt`` > ``under_compulsory_liquidation``
    > ``under_liquidation`` > ``active``).
    """

    ACTIVE = "active"
    """Registered and not flagged as winding down."""

    UNDER_LIQUIDATION = "under_liquidation"
    """Voluntary winding-up has been registered; the entity still exists."""

    UNDER_COMPULSORY_LIQUIDATION = "under_compulsory_liquidation"
    """Court-ordered / compulsory dissolution is in progress."""

    BANKRUPT = "bankrupt"
    """Bankruptcy proceedings have been opened."""

    DISSOLVED = "dissolved"
    """Winding-up finished but the record has not been removed from the register."""

    DELETED = "deleted"
    """Removed from the register; the record survives only as history."""

    UNKNOWN = "unknown"
    """The registry returned a record but no status could be derived from it."""


class DeadlineRecurrence(StrEnum):
    """How often a deadline repeats."""

    ANNUAL = "annual"
    BIMONTHLY = "bimonthly"
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"
    ONE_OFF = "one_off"


class ErrorCode(StrEnum):
    """Stable machine-readable error codes (see ``DECISIONS.md`` D-007).

    These strings are part of the API contract. Never rename one; add a new
    member instead.
    """

    INVALID_ID = "invalid_id"
    """The identifier is malformed for that country (failed checksum/format)."""

    NOT_FOUND = "not_found"
    """Well-formed identifier, but the registry has no such entity."""

    UNSUPPORTED_COUNTRY = "unsupported_country"
    """No registry module is registered for the requested country code."""

    UPSTREAM_ERROR = "upstream_error"
    """The national registry answered with an error we cannot interpret."""

    UPSTREAM_TIMEOUT = "upstream_timeout"
    """The national registry did not answer in time (after the single retry)."""

    RATE_LIMITED = "rate_limited"
    """The caller exceeded this service's rate limit."""

    BAD_REQUEST = "bad_request"
    """A parameter was missing or out of range."""

    NOT_IMPLEMENTED = "not_implemented"
    """The registry module exists but does not implement this operation yet."""

    INTERNAL_ERROR = "internal_error"
    """A bug on our side. Should never be returned deliberately."""


class Surface(StrEnum):
    """Which entry point a call arrived through (used by ``core/log.py``, T08)."""

    REST = "rest"
    MCP = "mcp"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


class Address(_Base):
    """A postal or visiting address, flattened to something an LLM can read.

    ``lines`` keeps the registry's own street/box lines in order; the rest are
    parsed components where the registry provides them.
    """

    lines: list[str] = Field(
        default_factory=list,
        description="Street or PO-box lines exactly as the registry supplies them.",
    )
    postal_code: str | None = Field(default=None, description="Postal / ZIP code.")
    city: str | None = Field(default=None, description="Post town.")
    municipality: str | None = Field(default=None, description="Municipality name.")
    municipality_code: str | None = Field(
        default=None, description="National municipality code, if the registry has one."
    )
    country_code: str | None = Field(
        default=None, description="ISO-3166-1 alpha-2 country code of the address itself."
    )
    country_name: str | None = Field(default=None, description="Country name as registered.")

    def one_line(self) -> str:
        """Render the address as a single human/LLM readable line."""
        parts = [*self.lines]
        locality = " ".join(p for p in (self.postal_code, self.city) if p)
        if locality:
            parts.append(locality)
        if self.country_name:
            parts.append(self.country_name)
        return ", ".join(parts)


class IndustryCode(_Base):
    """An industry classification code (NACE / SIC / national equivalent)."""

    code: str = Field(description="The code as published, e.g. '06.100'.")
    description: str | None = Field(default=None, description="Registry's own description.")
    scheme: str | None = Field(
        default=None,
        description="Classification scheme, e.g. 'NACE' or the national variant name.",
    )
    rank: int = Field(
        default=1,
        ge=1,
        description="1 = primary activity, 2 = second, and so on.",
    )


# ---------------------------------------------------------------------------
# Service discovery
# ---------------------------------------------------------------------------


class CountryInfo(_Base):
    """One supported country/registry pair, as returned by the discovery operation.

    Built by ``Registry.country_info()`` from the class attributes of a
    :class:`~registry_mcp.core.registry.Registry` subclass — the same nine
    values ``Registry.describe()`` has always emitted, now with a type
    (``DECISIONS.md`` D-012).

    This is the country-neutral half of the contract even though its *values*
    name a country: it carries no report data, so unlike every other returned
    model it is a row *about* a registry rather than a document *from* one.
    """

    country: str = Field(description="ISO-3166-1 alpha-2, upper-case, e.g. 'NO'.")
    registry: str = Field(description="Registry slug, e.g. 'brreg'.")
    name: str = Field(description="Human-readable register name.")
    id_scheme: str = Field(
        description="What the national identifier is called locally, e.g. 'organisasjonsnummer'."
    )
    id_example: str = Field(
        description="A real, valid identifier the caller can use to smoke-test the service."
    )
    id_description: str = Field(description="One sentence describing the identifier's format.")
    source_url: str = Field(description="Base URL of the upstream registry API, for citation.")
    license: str = Field(description="Licence of the upstream data, e.g. 'NLOD 2.0'.")
    is_stub: bool = Field(
        default=False,
        description=(
            "True for example/template modules, which are hidden from the public list "
            "unless stubs are explicitly requested."
        ),
    )
    requires_api_key: bool = Field(
        default=False,
        description=(
            "True when this registry's upstream API needs a credential the operator must "
            "supply. A self-hosted deployment that has not set it gets upstream_error on "
            "every call to this country (DECISIONS.md D-017)."
        ),
    )
    api_key_env: str | None = Field(
        default=None,
        description=(
            "Name of the environment variable holding that credential, e.g. "
            "'COMPANIES_HOUSE_API_KEY'. None when no key is needed. Never the key itself."
        ),
    )
    supported_includes: list[str] = Field(
        default_factory=list,
        description=(
            "Attachment names this registry declares — the closed set of valid values for "
            "`include=[…]` on `lookup_company`, sorted. Empty when this registry offers no "
            "attachments today. Lets an agent discover what more it can ask for before it "
            "asks (DECISIONS.md D-042(d)); an `include` value outside this list raises "
            "`bad_request` naming this same set, never a silently empty block."
        ),
    )

    @field_validator("country")
    @classmethod
    def _upper_country(cls, v: str) -> str:
        return v.upper()


class CountriesResponse(_Base):
    """The answer to "which countries can you answer for?".

    The only shape the discovery operation returns, on both surfaces
    (``DECISIONS.md`` D-012): REST ``GET /v1/countries`` and the MCP tool
    ``list_countries``. Before D-012 each surface re-derived this envelope from
    ``Registry.describe()`` on its own, which is how the two could have drifted
    — REST validated the dict through a private model that silently *dropped* an
    unrecognised key while MCP passed the raw dict through and *kept* it.
    """

    countries: list[CountryInfo] = Field(
        default_factory=list,
        description="One row per registry that can answer right now, sorted by country code.",
    )


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------


class PublishedDeadline(_Base):
    """A filing obligation exactly as the *register itself* publishes it.

    The counterpart to :class:`Deadline`, and deliberately much smaller.
    :class:`Deadline` is *ours*: computed, English-labelled, dated against a
    caller-supplied ``today``. This is *theirs*: whatever the upstream register
    states about the obligation, carried verbatim, with no interpretation and
    no arithmetic.

    It exists because some registers do the filing arithmetic themselves and
    publish the answer — Companies House publishes
    ``accounts.next_accounts.due_on`` and ``confirmation_statement.next_due``,
    which already account for accounting-reference-date changes, shortened and
    extended periods, and administrative extensions that no outside calculation
    can see (``DECISIONS.md`` D-016(a), D-018). A registry whose upstream
    publishes such a date fills this list at lookup time, and its
    :meth:`Registry.deadlines` then merges: the published date wins, a
    computation fills the gaps. A registry whose upstream publishes nothing —
    Brønnøysundregistrene, and every register that only states the statute —
    leaves the list empty and loses nothing.

    Nothing in ``core/`` interprets any field here. ``kind`` and ``source``
    are opaque strings owned by the country module; ``core`` only carries them
    across the lookup → deadlines boundary so that
    ``Registry.deadlines(report, today)`` can stay the pure function of
    ``(report, today)`` that its contract promises.
    """

    kind: str = Field(
        description=(
            "The same machine slug the country module uses for the matching "
            "`Deadline.kind`, e.g. 'annual_accounts'. Unique within a report."
        )
    )
    due_date: date | None = Field(
        default=None,
        description=(
            "The date the register itself publishes for this filing. `None` when the "
            "register names a period but no date — the country module may still be able "
            "to compute one from `period_end`."
        ),
    )
    period_start: date | None = Field(
        default=None, description="First day of the period this filing covers, if published."
    )
    period_end: date | None = Field(
        default=None,
        description=(
            "Last day of the period this filing covers, if published. This, not an "
            "accounting reference date, is what a statutory period runs from."
        ),
    )
    overdue: bool | None = Field(
        default=None,
        description=(
            "The register's own overdue flag, if it publishes one. Corroboration only: it "
            "is computed against the register's today, not the caller's, so "
            "`Deadline.days_until < 0` is the authoritative answer."
        ),
    )
    source: str | None = Field(
        default=None,
        description=(
            "Where the date came from upstream, e.g. 'accounts.next_accounts.due_on'. "
            "Opaque to core; the country module turns it into `applies_because` prose."
        ),
    )


class Deadline(_Base):
    """One filing obligation with a concrete calendar date.

    Deadlines are *computed*, never fetched: a registry module derives them
    from the entity's legal form and status plus a ``today`` parameter, so the
    same input always produces the same output and tests are deterministic.

    ``due_date`` is always the date the caller should act on; ``statutory_date``
    is the date the statute names before any weekend/holiday roll-forward.
    """

    country: str = Field(description="ISO-3166-1 alpha-2, upper-case.")
    registry: str = Field(description="Registry slug that produced this deadline.")

    kind: str = Field(
        description=(
            "Stable machine slug for the obligation, e.g. 'annual_accounts', "
            "'tax_return', 'vat_return', 'shareholder_register_statement'. "
            "Unique within a country."
        )
    )
    name: str = Field(description="Short English label, e.g. 'Annual accounts filing'.")
    local_name: str | None = Field(
        default=None,
        description="The name a local accountant would use, e.g. 'Årsregnskap'.",
    )
    authority: str = Field(
        description="Who receives the filing, e.g. 'Regnskapsregisteret', 'Skatteetaten'."
    )

    statutory_date: date = Field(
        description="The date named by law, before weekend/holiday roll-forward."
    )
    due_date: date = Field(
        description="The date the caller must actually file by (statutory date rolled forward)."
    )
    rolled_forward: bool = Field(
        default=False,
        description="True when due_date differs from statutory_date because of a non-working day.",
    )

    period_label: str | None = Field(
        default=None,
        description="Which period this filing covers, e.g. '2025' or '2026 term 3 (May–Jun)'.",
    )
    period_start: date | None = Field(default=None, description="First day of the covered period.")
    period_end: date | None = Field(default=None, description="Last day of the covered period.")

    recurrence: DeadlineRecurrence = Field(
        default=DeadlineRecurrence.ANNUAL, description="How often the obligation repeats."
    )
    mandatory: bool = Field(
        default=True,
        description=(
            "True when the obligation follows from the legal form alone. False when it "
            "depends on facts we cannot see (e.g. VAT turnover threshold) — in that case "
            "applies_because explains the assumption."
        ),
    )
    applies_because: str = Field(
        description=(
            "One sentence an agent can quote to the user explaining why this deadline "
            "applies to this company, including any assumption made."
        )
    )
    days_until: int | None = Field(
        default=None,
        description="due_date minus the `today` the calculation was run with. Negative = overdue.",
    )
    source_url: str | None = Field(
        default=None, description="Authoritative page describing the obligation."
    )

    @field_validator("country")
    @classmethod
    def _upper_country(cls, v: str) -> str:
        return v.upper()


class DeadlineReport(_Base):
    """The answer to "what must this company file, and by when?".

    This is the **only** shape the deadlines operation returns, on both
    surfaces (``DECISIONS.md`` D-010): REST
    ``GET /v1/{country}/company/{id}/deadlines`` and the MCP tool
    ``company_deadlines`` each emit ``model_dump(mode="json")`` of this model,
    unchanged. Neither surface may return a bare ``list[Deadline]``, because a
    list has nowhere to put ``today`` or ``notes`` — and an empty list without
    a note is indistinguishable from a bug.

    Build it with ``Registry.deadline_report(report, today)``; do not construct
    it in a surface.
    """

    country: str = Field(description="ISO-3166-1 alpha-2, upper-case.")
    registry: str = Field(description="Registry slug, e.g. 'brreg'.")
    company_id: str = Field(
        description="Canonical national identifier the deadlines were computed for."
    )
    company_name: str | None = Field(
        default=None, description="Registered name, so the caller can echo it back to a user."
    )
    today: date = Field(
        description=(
            "The date 'next occurrence' was computed from, inclusive. Echoed back so the "
            "answer is reproducible and an agent can tell a cached answer from a fresh one."
        )
    )
    deadlines: list[Deadline] = Field(
        default_factory=list,
        description=(
            "One entry per obligation kind, always the next occurrence, sorted by due_date. "
            "An empty list is a real answer, not an error — read `notes` for why."
        ),
    )
    notes: list[str] = Field(
        default_factory=list,
        description=(
            "Caveats to surface to the user, carried over from the company report: why the "
            "list is empty, an unclassified legal form, a status that suspends filing."
        ),
    )

    @field_validator("country")
    @classmethod
    def _upper_country(cls, v: str) -> str:
        return v.upper()


# ---------------------------------------------------------------------------
# Identifier validation
# ---------------------------------------------------------------------------


class ValidationResult(_Base):
    """The answer to "is this identifier well-formed?" — no network call.

    The only shape the validation operation returns, on both surfaces
    (``DECISIONS.md`` D-010): REST ``GET /v1/{country}/validate/{id}`` and the
    MCP tool ``validate_company_id``.

    Note that an invalid identifier is **not** an error here: this operation
    answers a question, so it returns ``valid=False`` with a ``reason`` and a
    ``hint`` rather than raising. That is the one deliberate exception to
    ``DECISIONS.md`` D-007's "every expected failure is a raised
    ``RegistryError``" — and the reason ``hint`` is carried on this model.

    Build it with ``Registry.validate(id)``; do not construct it in a surface.
    """

    country: str = Field(description="ISO-3166-1 alpha-2, upper-case.")
    registry: str = Field(description="Registry slug, e.g. 'brreg'.")
    id_scheme: str | None = Field(
        default=None, description="Name of the identifier scheme, e.g. 'organisasjonsnummer'."
    )
    input: str = Field(description="The identifier exactly as the caller supplied it.")
    valid: bool = Field(description="True when the identifier passes this country's format and checksum.")
    normalized: str | None = Field(
        default=None,
        description="Canonical form to pass to lookup, e.g. '923609016'. None when invalid.",
    )
    formatted: str | None = Field(
        default=None,
        description="The identifier as a local would write it, e.g. '923 609 016'. None when invalid.",
    )
    reason: str | None = Field(
        default=None,
        description="One English sentence saying why it is valid, or what failed.",
    )
    hint: str | None = Field(
        default=None,
        description=(
            "What to do next when `valid` is false — the same hint the invalid_id error "
            "carries. None when valid: the next call is simply lookup."
        ),
    )

    @field_validator("country")
    @classmethod
    def _upper_country(cls, v: str) -> str:
        return v.upper()


# ---------------------------------------------------------------------------
# Attachments (`DECISIONS.md` D-026(c), sharpened by D-041(c) and D-042)
# ---------------------------------------------------------------------------


class SourceRef(_Base):
    """Provenance for one attachment fetch — never for `CompanyReport` itself.

    `CompanyReport` has one `source`, one `source_url`, one `license` and one
    `fetched_at`: every field on it is an assertion by *that* register under
    *that* licence *at that moment* (D-026(c)). An attachment (`include=[…]`
    on `lookup_company`, assembled by `Registry.lookup_with`) is a **second**
    round trip, so it needs its own moment, its own cache state and its own
    failure mode — even when it happens to be the same upstream as the first
    fetch (D-041(c)'s correction: the discipline is **one fetch, one
    `SourceRef`**, not one organisation). No new vocabulary: this reuses the
    five provenance names `CompanyReport` already carries.

    Every attachment model — the LEI (D-026(c)), officers (D-028(5)), Peppol
    (D-029(b)), filing history (D-041(d)) and whatever else lands behind a
    future `include` value — carries exactly one of these, however many
    fields the rest of the block has. None of those models are added by this
    task (D-042(g)): this is the shape they will all reuse.
    """

    source: str | None = Field(
        default=None,
        description="Human-readable source name, e.g. 'GLEIF Level 1 (gleif.org)'.",
    )
    source_url: str | None = Field(
        default=None, description="Direct URL of the upstream record, for citation."
    )
    license: str | None = Field(
        default=None, description="Licence of the upstream data, e.g. 'CC0 1.0'."
    )
    fetched_at: datetime | None = Field(
        default=None, description="UTC timestamp of the live fetch this attachment came from."
    )
    cached: bool = Field(
        default=False,
        description="True when this attachment was served from cache rather than a live fetch.",
    )


class LeiRecord(_Base):
    """The Legal Entity Identifier GLEIF (the Global LEI Foundation) publishes
    for one entity — the ``include=["lei"]`` attachment, D-026(c)'s shape,
    unamended by D-045(e). Unlike every other attachment, this upstream is
    not any one country's own register: GLEIF publishes every jurisdiction
    from one endpoint, under one CC0 licence, with one TTL, so it is the
    first attachment every country declares by default
    (``Registry.universal_includes``, D-045(e)) rather than something a
    country module opts into.

    The two-level nullability is D-026(c)'s and D-011's, restated here: an
    **absent** ``CompanyReport.lei`` means the attachment was not requested,
    or the fetch failed (a ``notes`` sentence on the report says which); a
    **present** block with ``lei=None`` means GLEIF holds no LEI for this
    entity, which is a real and useful answer about a counterparty and must
    never be rendered as though nothing were known.
    """

    lei: str | None = Field(
        default=None,
        description=(
            "The 20-character Legal Entity Identifier GLEIF publishes for this entity. "
            "`None` *inside a present block* means GLEIF holds no LEI for it — a real "
            "and useful answer about a counterparty, and not the same as this block "
            "being absent (D-026(c), D-011). The LEI is **not** the EUID — see "
            "`CompanyReport.euid`'s own description for that distinction rather than "
            "restating it here."
        ),
    )
    legal_name: str | None = Field(
        default=None,
        description=(
            "The legal name as GLEIF publishes it, carried verbatim. May differ from "
            "`CompanyReport.name`, because the two are two registers' opinions recorded "
            "at two different moments — never reconciled against it and never used to "
            "correct the company record (D-018: say which source said what)."
        ),
    )
    registration_status: str | None = Field(
        default=None,
        description=(
            "GLEIF's own `registration.status` for this LEI record, verbatim: "
            "'ISSUED', 'LAPSED', … (national-vocabulary-in-values, D-042(g)). A "
            "'LAPSED' LEI means the entity stopped renewing its registration and is "
            "**not** evidence of insolvency or inactivity — Carillion plc ('03782379') "
            "and Lehman Brothers International (Europe) ('02538254') both read "
            "`entity.status: ACTIVE` beside `registration.status: LAPSED`. This field "
            "carries the *registration's* status; GLEIF's `entity.status` is not "
            "carried at all, because it is a claim about the company made by neither "
            "the company's own register nor us."
        ),
    )
    provenance: SourceRef = Field(
        description=(
            "Where, when and under what licence this block was fetched. `source` "
            "names GLEIF, `license` is 'CC0 1.0', and `source_url` is this record's "
            "own GLEIF URL. Never implies endorsement and never describes registry-mcp "
            "as a GLEIF service — GLEIF's anti-impersonation clause sits outside its "
            "data licence (D-026(c))."
        )
    )
    notes: list[str] = Field(
        default_factory=list,
        description=(
            "Plain-English caveats about this block. Always names the exact string "
            "sent as GLEIF's `entity.registeredAs` filter, so a `lei: null` answer is "
            "legible rather than silent, and the register-authority code GLEIF cites "
            "for this entity. If GLEIF returned more than one record for this "
            "registration number, a sentence discloses how many and each LEI, rather "
            "than silently picking one."
        ),
    )


class Charge(_Base):
    """One registered charge (a mortgage or other security interest) against
    an entity — one row of a `ChargeBlock`.

    Field names are country-neutral (D-042(g)): GB is the first filler
    (Companies House `/company/{n}/charges`, `registries/gb/__init__.py`),
    and any future filler (e.g. Norway's Løsøreregisteret, once it opens a
    public API) maps onto this same shape rather than getting one of its own.

    **The field list is ruled by D-045(a)**, not by D-042(h) — which rules
    `FiledDocument` and no charge shape at all. D-045(a) accepts these names,
    corrects `created_on`'s description (it is the date the charge instrument
    was created, not a record timestamp), and adds `contains_fixed_charge` and
    `contains_negative_pledge` beside `contains_floating_charge`, all three of
    which Companies House emits **only when true** — so an absent flag means
    the register did not mark this instrument, never that it lacks one
    (D-011). **This class has not yet been reconciled with that ruling**; the
    task that does so is named in D-045(a) and is due before the next deploy.
    """

    charge_id: str | None = Field(
        default=None,
        description=(
            "The register's own opaque handle for this charge; not fetchable through this "
            "API. `None` when the register has no such handle for an older filing — "
            "honestly absent, not guessed."
        ),
    )
    charge_number: int | None = Field(
        default=None,
        description="The register's sequence number for this charge, within this company.",
    )
    status: str | None = Field(
        default=None,
        description=(
            'The register\'s own word, verbatim, e.g. "outstanding", "fully-satisfied" — '
            "national vocabulary lives here, in the value, never in a field name (D-042(g)). "
            "See `is_outstanding` for the country-neutral derived flag."
        ),
    )
    is_outstanding: bool | None = Field(
        default=None,
        description=(
            "Derived from `status` by membership of a country module's own committed table "
            "of status words it has actually observed on the wire. `None` when `status` is "
            "absent or is a word not yet in that table — never guessed, never `False` by "
            "default (D-025(d), D-011)."
        ),
    )
    classification: str | None = Field(
        default=None, description="What kind of instrument this is, as the register describes it."
    )
    created_on: date | None = Field(default=None, description="When the charge was created.")
    delivered_on: date | None = Field(
        default=None, description="When the charge was delivered to the register for registration."
    )
    satisfied_on: date | None = Field(
        default=None, description="When the charge was satisfied, if it has been."
    )
    assets_charged: str | None = Field(
        default=None, description="The register's own free-text description of what is charged."
    )
    obligations_secured: str | None = Field(
        default=None,
        description="The register's own free-text description of what the charge secures.",
    )
    contains_floating_charge: bool | None = Field(
        default=None,
        description="Whether the register marks this instrument as including a floating charge.",
    )
    parties_entitled: list[str] = Field(
        default_factory=list,
        description=(
            "Names exactly as the register publishes them for the party or parties the "
            "charge is entitled to (typically a bank, an insurer or a trustee company; "
            "occasionally a natural person, e.g. a director lending to their own company). "
            "This is a term of the company's own instrument, not a person record: it is "
            "never a lookup key, never indexed, never searchable and never reaches a log "
            "line (D-028(1), D-040). It is the one place in this product a natural "
            "person's name can appear, and it is deliberately not named the register's own "
            "`persons_entitled` — that name asserts a natural person; this one does not."
        ),
    )


class ChargeBlock(_Base):
    """Registered charges for one entity — an `include=["charges"]` attachment
    (D-042(g), D-045(a)), never a plain field on `CompanyReport` (D-041(c)):
    it is a second round trip with its own moment, its own cache state and its
    own failure mode, so it carries its own `SourceRef` rather than reusing
    the report's.

    **The count fields are ruled by D-045(a)**, not by D-042(h). It strikes
    `outstanding_count` — `total_count - satisfied_count` is our arithmetic
    wearing a register figure's name, and on a shared model it would mean
    "outstanding" for a register with no partially-satisfied state and "not
    fully satisfied" for one that has it (D-011) — and adds the register's
    own `part_satisfied_count` in its place. **This class has not yet been
    reconciled with that ruling**; the task that does so is named in D-045(a)
    and is due before the next deploy.

    Two-level nullability is the point of this shape (D-026(c), D-041(c),
    D-042(d)(3)): `CompanyReport.charges` is `None` when `charges` was not in
    `include`, or when the fetch failed (`Registry.lookup_with` appends a
    `notes` sentence on the report saying which). Once *present*, this block
    carries `charges: []` for an entity the register confirms has none —
    that case must never collapse into the absent case, and must never be
    `not_found` (D-011).
    """

    charges: list[Charge] = Field(
        default_factory=list,
        description="Sorted newest first (a country module's own tie-break rule).",
    )
    total_count: int | None = Field(
        default=None,
        description=(
            "The register's own count of charges for this company, which may exceed "
            "`len(charges)` — see `notes` for a truncation disclosure when it does."
        ),
    )
    outstanding_count: int | None = Field(
        default=None,
        description=(
            "Derived as `total_count - satisfied_count` when the register publishes both as "
            "whole-company figures; a register that also tracks a distinct "
            "partially-satisfied state folds it in here as not-fully-satisfied. `None` when "
            "the register does not publish enough to derive it."
        ),
    )
    satisfied_count: int | None = Field(
        default=None, description="The register's own whole-company count of satisfied charges, verbatim."
    )
    provenance: SourceRef = Field(
        description="Where, when and under what licence this block was fetched."
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Plain-English caveats about this block, e.g. truncation when `total_count` exceeds `len(charges)`.",
    )


class FiledDocument(_Base):
    """One filing a national register publishes for one entity — one row of a
    :class:`FilingHistory`.

    The shape ``DECISIONS.md`` D-041(d) ruled and D-042(h) widened, and it is
    country-neutral by construction rather than by intent: Britain, Sweden and
    Norway each built this model independently behind their own seam, and all
    three arrived field-for-field at this one. National vocabulary lives in the
    *values* (`category`, `type_code`, `description_code`), never in a field
    name (D-042(g)).

    Every field is nullable and every `None` means the same thing: **the
    register does not publish it** (D-011). It never means zero, never means
    "no", and is never filled by derivation — a register that does not publish
    a period start gets `None`, not a start inferred by subtracting twelve
    months from the end (D-009).
    """

    kind: str | None = Field(
        default=None,
        description=(
            "The `Deadline.kind` slug this filing discharges, or `None` when it discharges "
            "none. This is the one field that is *derived* rather than relayed, and it is "
            "derived only by a committed per-country table of category words actually "
            "observed on the wire. A filing whose category is outside that table gets "
            "`None` rather than an invented slug (D-009): a filing that discharges no "
            "deadline this product publishes says so honestly."
        ),
    )
    period_end: date | None = Field(
        default=None,
        description=(
            "The reporting period's last day, exactly as the register published it. "
            "Beware what the period belongs to: on an annual-accounts filing it is the "
            "date the accounts were made up to, but a register may publish a made-up date "
            "on other filing kinds too — a British confirmation statement carries one, and "
            "it is not a financial year end. Read it together with `kind`. `None` on the "
            "great majority of filings, which have no reporting period at all."
        ),
    )
    period_start: date | None = Field(
        default=None,
        description=(
            "The reporting period's first day, as published. `None` wherever the register "
            "publishes no counterpart to `period_end` — deriving one would assert a period "
            "length the register never stated, and a first, shortened or extended "
            "accounting period is lawful and common (D-009). Norway's Regnskapsregisteret "
            "publishes `regnskapsperiode: {fraDato, tilDato}` and fills both ends; "
            "Companies House publishes only the end."
        ),
    )
    filed_at: date | None = Field(
        default=None,
        description=(
            "When the register recorded this filing, verbatim. This is the field that "
            "makes the block answer *does this company file on time*, and it is the sort "
            "key for `FilingHistory.documents`: newest first."
        ),
    )
    days_from_fee_point: int | None = Field(
        default=None,
        description=(
            "Signed days from a named late-fee datum to `filed_at`, **only where the "
            "register itself publishes such a datum for that period**. Negative is early. "
            "`None` is the common answer and means the datum does not exist in the data, "
            "not that the arithmetic was skipped: Sweden fills it because "
            "årsredovisningslagen 8 kap. 6 § names one datum for every company, while "
            "Companies House publishes only the *next* period's due date and nothing "
            "per-period historical, so there is nothing to measure a past filing against. "
            "Deriving one from the statutory rule would require guessing a period length, "
            "a first-accounts variant and any shortening the register has not disclosed, "
            "then presenting the result as the register's own — the invented figure D-009 "
            "forbids."
        ),
    )
    document_id: str | None = Field(
        default=None,
        description=(
            "The register's own opaque handle for this filing, relayed verbatim and never "
            "interpreted. **Not fetchable through this API**: the filed document itself "
            "lives behind a separate host, which is a second upstream with its own "
            "provenance and out of scope for this block (D-041(c)). It is the key a "
            "support case with the register can name."
        ),
    )
    file_format: str | None = Field(
        default=None,
        description=(
            "What the register holds the document as, where it says. `None` where the "
            "filing-history endpoint publishes no format — Companies House keeps the media "
            "type on its separate document host, a second fetch this block does not make."
        ),
    )
    category: str | None = Field(
        default=None,
        description=(
            "The register's own category for this filing, verbatim and never translated — "
            '"accounts", "mortgage", "confirmation-statement", "gazette" and some twenty '
            "more in Britain alone, and none of these lists is closed. It is the field "
            "`kind` is derived from."
        ),
    )
    type_code: str | None = Field(
        default=None,
        description=(
            'The register\'s own form code for this filing, verbatim: "AA", "CS01", '
            '"AP01", "MR01" and older forms such as "288a" and "363s" in Britain — 100 '
            "distinct codes across 1876 items observed live."
        ),
    )
    description_code: str | None = Field(
        default=None,
        description=(
            "The register's own description-template key, verbatim and **never resolved "
            "into prose**. This is the key and not the sentence on purpose, and the reason "
            "is the whole design of this block: Companies House resolves these templates "
            "from a `description_values` object, 97 templates interpolate an officer's "
            "name and 26 a person with significant control's, so the resolved sentence is "
            "personal data while the key is not. **The key says what happened; only the "
            "values say who** (D-042(e)(1), D-028)."
        ),
    )


class FilingHistory(_Base):
    """What one entity has filed with its national register — an
    ``include=["filings"]`` attachment (D-041(d), D-042), never a plain field
    on :class:`CompanyReport` (D-041(c)): it is a second round trip with its
    own moment, its own cache state and its own failure mode, so it carries its
    own :class:`SourceRef` rather than reusing the report's.

    All three live countries declare it, and each answers a differently-scoped
    question its register actually supports — Companies House returns the whole
    filing history, Bolagsverket the filed annual reports, Regnskapsregisteret
    the filed annual accounts. `notes` says which, in words, on every block.

    Two-level nullability is the contract (D-011, D-026(c), D-041(c)):
    **absent** means "you did not ask, or the fetch failed" — `lookup_with`
    appends one `notes` sentence to the report saying which — while **present
    with `documents: []`** means "the register lists no filings for this
    entity", a real and useful answer about a counterparty that must never be
    rendered as an absence.
    """

    documents: list[FiledDocument] = Field(
        default_factory=list,
        description=(
            "One page of the register's own filing history, newest first by `filed_at`. "
            "Never paginated further; when the register holds more, `total_count` says how "
            "many and `notes` says so in words. Empty means the register lists none — not "
            "that we could not look."
        ),
    )
    financial_year_end: date | None = Field(
        default=None,
        description=(
            "The latest reporting period among this entity's filed **annual accounts** "
            '(`kind == "annual_accounts"`), carried verbatim — never a synthesised '
            "month-day, and never taken from a filing of another kind that happens to "
            "carry a made-up date of its own. It is the latest *period*, not the period of "
            "the latest *filing*, because a register may accept a later filing that amends "
            "an earlier year and that would otherwise roll this date backwards. It is "
            "**evidence of** the entity's accounting reference date, not a statement of "
            "it. `None` when this page holds no annual-accounts filing with a reporting "
            "period, including when older accounts exist further back than the page "
            "reaches."
        ),
    )
    total_count: int | None = Field(
        default=None,
        description=(
            "The register's own count of filings for this entity, which may greatly exceed "
            "`len(documents)` — 8371 against a 25-row page, for one company observed live. "
            "**`None` means the register published no count**, not zero, and for Companies "
            "House it additionally distinguishes a real zero from a number whose filing "
            "history the register cannot serve at all: that endpoint returns `0` for both, "
            "and relaying the second as a zero would assert something the register never "
            "said (D-011). `notes` names which case it was."
        ),
    )
    provenance: SourceRef = Field(
        description="Where, when and under what licence this block was fetched."
    )
    notes: list[str] = Field(
        default_factory=list,
        description=(
            "Plain-English caveats about this block: which subset of filings this "
            "register publishes, truncation when `total_count` exceeds `len(documents)`, "
            "and which empty state an empty `documents` is."
        ),
    )


class InsolvencyEvent(_Base):
    """One dated step in an insolvency case, as the register itself records it.

    These are the register's own events, not this service's interpretation of
    them: D-042(e)(2) rules that case type, case number and *these* dated
    events carry the entire distress signal a pre-contract check needs.
    """

    event_type: str | None = Field(
        default=None,
        description=(
            "The register's own word for what happened, verbatim — national vocabulary "
            "lives here, in the value, never in a field name (D-042(g)). Thirteen words "
            'have been observed live in Britain, from "petitioned-on" and "wound-up-on" to '
            '"declaration-solvent-on" and "dissolved-on". A word outside the observed set '
            "is still relayed verbatim: this field is never filtered, only reported."
        ),
    )
    occurred_on: date | None = Field(
        default=None, description="The date the register gives for this event."
    )


class InsolvencyCase(_Base):
    """One insolvency case a register publishes against one entity.

    **No practitioner particular can land here.** A register commonly publishes
    each appointed practitioner's name and postal address alongside the case;
    D-042(e)(2) bars relaying them in the first tranche, so this model has no
    field for them and no country mapper reads the key. Adding them later is a
    decision with its own entry in ``DECISIONS.md``, inheriting D-028's four
    preconditions in full.
    """

    case_number: str | None = Field(
        default=None,
        description=(
            "The register's own identifier for this case, verbatim. For Companies House "
            'this is a per-company sequence number rendered as a string ("1", "2", … up to '
            '"31" in the live sample) and is **not** a court reference — it identifies the '
            "case only within this entity. Kept as a string because another register's "
            "case identifier need not be numeric."
        ),
    )
    case_type: str | None = Field(
        default=None,
        description=(
            "The register's own word for the kind of procedure, verbatim — national "
            "vocabulary in the value (D-042(g)). Ten words observed live in Britain, among "
            'them "compulsory-liquidation", "creditors-voluntary-liquidation", '
            '"members-voluntary-liquidation" and "in-administration". See `is_liquidation` '
            "for the country-neutral derived flag."
        ),
    )
    is_liquidation: bool | None = Field(
        default=None,
        description=(
            "Whether this procedure is a winding-up — the country-neutral question behind "
            "the national word in `case_type`. Derived by membership of a committed table "
            "of words the country module has actually observed on the wire. `None` when "
            "`case_type` is absent or is a word not yet in that table — never guessed, "
            "never `False` by default (D-011, D-025(d)). **`True` does not mean "
            "insolvent**: a members' voluntary liquidation is a *solvent* winding-up, "
            "begun by a declaration of solvency, and 56 of the 1,485 live British cases "
            "behind this table were exactly that. Read it as 'the entity is being wound "
            "up', not as 'the entity cannot pay'."
        ),
    )
    events: list[InsolvencyEvent] = Field(
        default_factory=list,
        description=(
            "The register's own dated steps in this case, newest first. Frequently empty — "
            "172 of the 1,485 live British cases carried no date at all, most of them old "
            "receiverships — and an empty list means the register publishes no date for "
            "this case, never that nothing happened."
        ),
    )
    note_codes: list[str] = Field(
        default_factory=list,
        description=(
            "The register's own note **codes** for this case, verbatim and never resolved "
            "into prose — the same treatment D-042(e)(1) gives a filing's "
            "`description_code`. Companies House declares this field an unbounded "
            "`array[string]`, so it is the one place in that payload a name could hide; "
            "codes are therefore relayed through an allow-list of observed codes, and an "
            "unrecognised one is dropped and disclosed in the block's `notes` rather than "
            "passed through."
        ),
    )


class InsolvencyBlock(_Base):
    """Insolvency proceedings a register publishes against one entity — an
    ``include=["insolvency"]`` attachment (D-042), never a plain field on
    :class:`CompanyReport` (D-041(c)), and carrying its own :class:`SourceRef`.

    Two-level nullability is the point of the shape (D-011, D-026(c),
    D-041(c), D-042(d)(3)): once *present*, this block carries ``cases: []``
    for an entity the register publishes no insolvency case for — that state
    must never collapse into the absent state and must never be ``not_found``.
    Companies House's 404 here is the *normal* answer for a solvent company and
    is byte-identical to its answer for a number that was never issued, so it
    says nothing about whether the entity exists; ``notes`` therefore
    distinguishes "the register holds no insolvency resource here" from "the
    resource exists and is empty" instead of flattening both into silence.
    """

    cases: list[InsolvencyCase] = Field(
        default_factory=list,
        description=(
            "Every insolvency case the register publishes for this entity — the whole "
            "history, not a page, where the register's endpoint is unpaginated. Sorted "
            "newest first by the case's most recent event date, then by `case_number` "
            "descending; cases the register gives no date for sort last."
        ),
    )
    statuses: list[str] = Field(
        default_factory=list,
        description=(
            "The register's own entity-level insolvency status words, verbatim — national "
            "vocabulary in values (D-042(g)). Eight observed live in Britain, among them "
            '"in-administration", "liquidation" and "voluntary-arrangement". An **empty '
            "list means the register publishes no such word for this entity**, which is "
            "not the same as 'not currently insolvent': about one in ten companies whose "
            "Companies House status is itself an insolvency status still has no word here. "
            "No yes/no flag is derived from this field for exactly that reason (D-011)."
        ),
    )
    provenance: SourceRef = Field(
        description="Where, when and under what licence this block was fetched."
    )
    notes: list[str] = Field(
        default_factory=list,
        description=(
            "Plain-English caveats about this block: which of the register's two empty "
            "states this is, that practitioner particulars exist upstream and are "
            "deliberately not relayed, and any note code withheld by the allow-list."
        ),
    )


# ---------------------------------------------------------------------------
# Financial summary (Norway's key figures) — DECISIONS.md D-043
# ---------------------------------------------------------------------------

#: Every numeric field on `IncomeStatement`/`BalanceSheet` carries this sentence
#: verbatim in its own description, per D-043(f)'s instruction that it be
#: stated in these terms rather than paraphrased into "unknown": the register's
#: nested numeric objects are frequently *present and empty* (`{}`) rather than
#: absent, an empty object and a missing one mean the same thing, and the
#: register is not even consistent about when it states an explicit zero
#: instead — two holding companies with no turnover, read the same afternoon,
#: published that absence two different ways. Only three of the nineteen
#: figures below were present on every one of 573 observed filings.
_FIGURE_ABSENCE_NOTE = (
    "`None` means the register did not publish this line for this filing — never zero. "
    "The register is inconsistent about when it states an explicit zero for an absent "
    "figure versus omitting the line entirely, so this field's absence is not evidence "
    "the true value is zero, and a stated zero is not evidence the register omits the "
    "line elsewhere (DECISIONS.md D-043(f))."
)


class IncomeStatement(_Base):
    """Flows over one reporting period — Regnskapsregisteret's
    ``resultatregnskapResultat``, one of two sub-objects on a
    :class:`FinancialPeriod` (D-043(c)). Nested apart from :class:`BalanceSheet`
    on purpose: revenue is a flow over a span, not a stock at an instant, and a
    caller who mixes the two time semantics makes precisely the error this
    split exists to prevent.

    Every field is `None` or a whole-unit figure in :attr:`FinancialPeriod.currency`
    — never both `None` and zero at once, and never inferred from the other
    (D-043(f)); see `FinancialPeriod.currency` for what the unit is and why it
    is required.
    """

    revenue: float | None = Field(
        default=None,
        description=(
            f"Turnover for the period (`sumDriftsinntekter`). {_FIGURE_ABSENCE_NOTE} "
            "Absent on 51 of 358 observed filings (14%) — not rare."
        ),
    )
    operating_costs: float | None = Field(
        default=None,
        description=f"Total operating costs for the period (`sumDriftskostnad`). {_FIGURE_ABSENCE_NOTE}",
    )
    operating_result: float | None = Field(
        default=None,
        description=f"Operating result for the period (`driftsresultat`). {_FIGURE_ABSENCE_NOTE}",
    )
    financial_income: float | None = Field(
        default=None,
        description=f"Financial income for the period (`sumFinansinntekter`). {_FIGURE_ABSENCE_NOTE}",
    )
    financial_costs: float | None = Field(
        default=None,
        description=f"Financial costs for the period (`sumFinanskostnad`). {_FIGURE_ABSENCE_NOTE}",
    )
    net_financial_items: float | None = Field(
        default=None,
        description=f"Net financial items for the period (`nettoFinans`). {_FIGURE_ABSENCE_NOTE}",
    )
    profit_before_tax: float | None = Field(
        default=None,
        description=(
            "Ordinary result before tax (`ordinaertResultatFoerSkattekostnad`). "
            f"{_FIGURE_ABSENCE_NOTE}"
        ),
    )
    profit_for_period: float | None = Field(
        default=None,
        description=(
            f"Profit or loss for the period (`aarsresultat`). {_FIGURE_ABSENCE_NOTE} One of "
            "only three fields present on every one of 573 observed filings."
        ),
    )
    total_comprehensive_income: float | None = Field(
        default=None,
        description=(
            f"Total comprehensive income for the period (`totalresultat`). {_FIGURE_ABSENCE_NOTE} "
            "Absent on 209 of 358 observed filings (58%) — the register's own line, not "
            "this project's omission."
        ),
    )


class BalanceSheet(_Base):
    """Stocks at the period's last instant — Regnskapsregisteret's
    ``eiendeler`` and ``egenkapitalGjeld``, the other of the two sub-objects on
    a :class:`FinancialPeriod` (D-043(c)). See :class:`IncomeStatement` for why
    the two are separate models rather than one flat one.

    Every field is `None` or a whole-unit figure in :attr:`FinancialPeriod.currency`
    — never both `None` and zero at once, and never inferred from the other
    (D-043(f)). **No field here is a ratio or a verdict** — an equity ratio, a
    current ratio and every similar derived figure are declined by D-043(e): the
    register's own `total_assets` and `total_equity_and_liabilities` disagree
    on 27 of 358 filings (7.5%), so a ratio built from this block would be a
    ratio of two numbers the register itself does not vouch for jointly. The
    one comparison this project makes is a `notes` sentence, never a number —
    see :class:`FinancialSummary`.
    """

    fixed_assets: float | None = Field(
        default=None,
        description=f"Fixed assets at period end (`sumAnleggsmidler`). {_FIGURE_ABSENCE_NOTE}",
    )
    current_assets: float | None = Field(
        default=None,
        description=f"Current assets at period end (`sumOmloepsmidler`). {_FIGURE_ABSENCE_NOTE}",
    )
    total_assets: float | None = Field(
        default=None,
        description=(
            f"Total assets at period end (`sumEiendeler`). {_FIGURE_ABSENCE_NOTE} One of "
            "only three fields present on every one of 573 observed filings. Compare with "
            "`total_equity_and_liabilities` (DECISIONS.md D-043(e)): the two disagree on 27 "
            "of 358 filings, and this block's own `notes` names the gap when they do; "
            "neither figure is edited, reconciled or dropped."
        ),
    )
    paid_in_equity: float | None = Field(
        default=None,
        description=(
            "Paid-in equity at period end (`sumInnskuttEgenkaptial` — the register's own "
            f"spelling, not a typo in this field's description). {_FIGURE_ABSENCE_NOTE}"
        ),
    )
    retained_equity: float | None = Field(
        default=None,
        description=f"Retained equity at period end (`sumOpptjentEgenkapital`). {_FIGURE_ABSENCE_NOTE}",
    )
    equity: float | None = Field(
        default=None,
        description=f"Total equity at period end (`sumEgenkapital`). {_FIGURE_ABSENCE_NOTE}",
    )
    non_current_liabilities: float | None = Field(
        default=None,
        description=f"Non-current liabilities at period end (`sumLangsiktigGjeld`). {_FIGURE_ABSENCE_NOTE}",
    )
    current_liabilities: float | None = Field(
        default=None,
        description=f"Current liabilities at period end (`sumKortsiktigGjeld`). {_FIGURE_ABSENCE_NOTE}",
    )
    liabilities: float | None = Field(
        default=None,
        description=(
            f"Total liabilities at period end (`sumGjeld`). {_FIGURE_ABSENCE_NOTE} Carried "
            "exactly as the register states it, including negative: DECISIONS.md D-043(e) "
            "records real filings with a negative `sumGjeld` (e.g. -108,837), which is a "
            "filing the register relayed without validating, not a company fact this field "
            "corrects."
        ),
    )
    total_equity_and_liabilities: float | None = Field(
        default=None,
        description=(
            f"Total equity and liabilities at period end (`sumEgenkapitalGjeld`). "
            f"{_FIGURE_ABSENCE_NOTE} One of only three fields present on every one of 573 "
            "observed filings. See `total_assets` for the reconciliation note the two "
            "together can trigger."
        ),
    )


class FinancialPeriod(_Base):
    """One filed accounting period's key figures — Regnskapsregisteret's own
    filing, mapped a second time alongside :class:`~registry_mcp.core.models.
    FiledDocument` (D-043(h)): the two travel together because both come from
    the same fetch, and `document_id` and `period_end` are the join keys a
    caller uses to line this period up with its sibling `FiledDocument`.

    `currency` is the one field in this whole block with no default
    (DECISIONS.md D-043(d)): a figure separated from its currency is not
    partially wrong, it is meaningless, and this model makes constructing one
    a `pydantic.ValidationError` rather than a silently-`None` currency. A
    period the register published with no `valuta` is not carried at all —
    the mapper skips it and says why in `FinancialSummary.notes` — which is
    safe because `valuta` was present on 573 of 573 payloads this project has
    read.
    """

    period_start: date | None = Field(
        default=None,
        description=(
            "The reporting period's first day, as published (`regnskapsperiode.fraDato`). "
            "Real, published data — never derived by subtracting twelve months from "
            "`period_end`, because a first or final period may be shorter or longer "
            "(DECISIONS.md D-009)."
        ),
    )
    period_end: date | None = Field(
        default=None,
        description=(
            "The reporting period's last day, as published (`regnskapsperiode.tilDato`). "
            "Equal to the sibling `FiledDocument.period_end` for this filing on the same "
            "report (DECISIONS.md D-043(h))."
        ),
    )
    currency: str = Field(
        description=(
            "ISO-4217-shaped currency code, verbatim from `valuta`. **Required — this "
            "field has no default, and a period the register published with no currency "
            "is not constructed at all** (DECISIONS.md D-043(d)): a figure without its "
            "currency is not partially wrong, it is meaningless, and this model makes "
            "that state unrepresentable rather than merely discouraged. 12 of 358 "
            "observed Norwegian filings are not in kroner (USD, EUR, SEK, DKK), so two "
            "*Norwegian* companies can be incomparable without either crossing a border. "
            "Values are whole units of this currency; scale (thousands, millions) is not "
            "recorded because the register does not publish one, and the figures are "
            "exact integers that are not significant to that precision."
        ),
    )
    accounting_framework: str | None = Field(
        default=None,
        description=(
            "The accounting framework this period was prepared under, verbatim from "
            "`regnkapsprinsipper.regnskapsregler` — observed values include "
            "'regnskapslovenAlminneligRegler', 'IFRS' and 'forenkletAnvendelseIFRS'. Two "
            "Norwegian companies' figures are not necessarily on the same basis; no field "
            "here converts between them (DECISIONS.md D-043(d))."
        ),
    )
    scope: str | None = Field(
        default=None,
        description=(
            "What this filing covers, the register's own word, verbatim from "
            "`regnskapstype` — 'SELSKAP' (company accounts) is the only value observed in "
            "573 payloads; 'KONSERN' (consolidated) is implied by the vocabulary but was "
            "never seen. See `consolidated` for the country-neutral derived flag."
        ),
    )
    consolidated: bool | None = Field(
        default=None,
        description=(
            "Whether this filing is a consolidated (group) statement, derived from "
            "`scope` by a committed table of words this module has actually observed on "
            "the wire — today only `{'SELSKAP': False}`. A word outside that table, "
            "including an implied-but-unobserved 'KONSERN', gets `None`, never `False` "
            "(DECISIONS.md D-011, D-025(d)): this field never guesses."
        ),
    )
    small_entity: bool | None = Field(
        default=None,
        description=(
            "Whether this filing was prepared under the reduced-disclosure regime for a "
            "*lite foretak* (regnskapsloven § 1-6), from `regnkapsprinsipper.smaaForetak`. "
            "**Not a distress signal** — True on 315 of 358 observed filings, the majority "
            "case — it is a disclosure caveat: fewer figures exist, and those that do were "
            "prepared under rules that permit simplification."
        ),
    )
    audit_exempt: bool | None = Field(
        default=None,
        description=(
            "Whether the company has resolved to opt out of audit under aksjeloven § 7-6, "
            "from `revisjon.fravalgRevisjon` — lawful below that section's thresholds and "
            "True on 65 of 358 observed filings (18%). The consequence a credit decision "
            "must weigh: no independent auditor checked these figures."
        ),
    )
    unaudited: bool | None = Field(
        default=None,
        description=(
            "Relayed uninverted from `revisjon.ikkeRevidertAarsregnskap`, which its own "
            "name claims means these accounts were not audited. **`True` was never "
            "observed** in 573 sampled payloads, including every filing by a company that "
            "had opted out of audit under `audit_exempt` — so this flag's semantics are "
            "unverified: do not read a `False` here as an assertion that the accounts were "
            "audited, and do not read this field as more reliable than `audit_exempt` "
            "(DECISIONS.md D-043(g))."
        ),
    )
    liquidation_basis: bool | None = Field(
        default=None,
        description=(
            "Whether this filing is an *avviklingsregnskap* under aksjeloven § 16-10 — a "
            "winding-up account prepared on a realisation rather than a going-concern "
            "basis, over a final stub period — from `avviklingsregnskap`. Rare (3 of 215 "
            "entities the register marks `underAvvikling`) and, when true, real: read "
            "`FinancialSummary.notes` for the caveat this triggers. It does not restate "
            "the winding-up itself, which `CompanyReport.status` already carries."
        ),
    )
    document_id: str | None = Field(
        default=None,
        description=(
            "The register's own opaque handle for this filing, verbatim from `journalnr` "
            "— the same handle the sibling `FiledDocument.document_id` on `filings` "
            "carries for the same filing, and the join key between the two blocks "
            "(DECISIONS.md D-043(h)). Not fetchable through this API."
        ),
    )
    income_statement: IncomeStatement | None = Field(
        default=None,
        description=(
            "Flows for this period. `None` when the register published no line in this "
            "statement at all for this filing; otherwise present with whichever lines it "
            "published, each individually nullable (DECISIONS.md D-043(f))."
        ),
    )
    balance_sheet: BalanceSheet | None = Field(
        default=None,
        description=(
            "Stocks at this period's last instant. `None` when the register published no "
            "line in this statement at all for this filing; otherwise present with "
            "whichever lines it published, each individually nullable (DECISIONS.md "
            "D-043(f))."
        ),
    )


class FinancialSummary(_Base):
    """Key figures from an entity's filed annual accounts — an
    ``include=["financials"]`` attachment (DECISIONS.md D-043), never a plain
    field on :class:`CompanyReport` (D-041(c)): it is a second round trip with
    its own moment, its own cache state and its own failure mode, so it
    carries its own :class:`SourceRef` rather than reusing the report's.

    **A second block, not a wider `FiledDocument`** (D-043(b)): "did they file
    on time" and "what do the numbers say" are two different questions, and
    folding nineteen numeric fields onto `FiledDocument` would collapse two
    meanings into one `None` — "Britain does not publish this" and "this
    Norwegian company did not report this line" — which D-011 forbids.

    Norway fills this block today; Sweden and Britain do not, and the reason
    is a scope decision this project made (Bolagsverket's figures live only
    inside a zip this project declines to parse; Companies House's only
    inside filed iXBRL this project declines to parse), not the register's
    silence (DECISIONS.md D-043(i)). `include=["financials"]` on a country
    that does not declare it is `bad_request`, never a silently empty block.

    Two-level nullability is the point of the shape (D-011, D-026(c),
    D-041(c), D-042(d)(3)): once *present*, this block carries `periods: []`
    for an entity Regnskapsregisteret holds no filed accounts for — that
    state must never collapse into the absent state and must never be
    ``not_found``. **No field on this block or on `FinancialPeriod` is a
    derived ratio, indicator or verdict** — DECISIONS.md D-043(e) rules out an
    equity ratio, a current ratio, a net-debt figure, a working-capital
    figure and every similar field on three independent grounds, the
    strongest being that the register relays filings whose own totals do not
    reconcile on 27 of 358 observed filings. The one comparison this project
    makes is a `notes` sentence, never a number: see `notes` below.
    """

    periods: list[FinancialPeriod] = Field(
        default_factory=list,
        description=(
            "Filed accounting periods, sorted newest first by `period_end`. "
            "Regnskapsregisteret publishes exactly one — the endpoint takes no year "
            "argument and holds no history — so this is a latest-figures block, not a "
            "trend; `notes` says so on every non-empty block. The list exists for a "
            "register that publishes more than one."
        ),
    )
    provenance: SourceRef = Field(
        description=(
            "Where, when and under what licence this block was fetched. **Identical in "
            "all five fields to the sibling `filings` block's `provenance` when both are "
            "requested together**: they are the same upstream fetch, not two (DECISIONS.md "
            "D-043(h))."
        )
    )
    notes: list[str] = Field(
        default_factory=list,
        description=(
            "Plain-English caveats about this block. Unconditional on any non-empty "
            "block: that figures are denominated in the stated currency and framework and "
            "are not comparable across companies or borders without regard to both, and "
            "that this is the latest filed period rather than a history. Conditional: a "
            "reconciliation note when `total_assets` and `total_equity_and_liabilities` "
            "disagree, a non-NOK currency note, and one note each for `small_entity`, "
            "`audit_exempt`, `liquidation_basis` and an observed `unaudited` (DECISIONS.md "
            "D-043(e),(g))."
        ),
    )


# ---------------------------------------------------------------------------
# Company report
# ---------------------------------------------------------------------------


class CompanyReport(_Base):
    """Everything `registry-mcp` knows about one registered entity.

    This is the single most important shape in the project. It is returned
    verbatim by ``GET /v1/{country}/company/{id}`` and by the MCP tool
    ``lookup_company``.

    A registry module fills what its national register publishes and leaves the
    rest ``None``. Nothing here is Norway-specific; ``registries/no/`` maps
    Enhetsregisteret's fields onto it (see ``NORBIZ_SPEC.md`` §3).
    """

    # --- identity -----------------------------------------------------------
    country: str = Field(description="ISO-3166-1 alpha-2, upper-case, e.g. 'NO'.")
    registry: str = Field(description="Registry slug, e.g. 'brreg'.")
    id: str = Field(
        description="Canonical national identifier, digits/letters only, no spaces or dots."
    )
    id_formatted: str | None = Field(
        default=None,
        description="The identifier as a local would write it, e.g. '923 609 016'.",
    )
    id_scheme: str | None = Field(
        default=None,
        description="Name of the identifier scheme, e.g. 'organisasjonsnummer'.",
    )
    euid: str | None = Field(
        default=None,
        description=(
            "European Unique Identifier (EUID, Commission Implementing Regulation (EU) "
            "2021/1042 Article 9), where the register publishes one, e.g. Finland's "
            "'FIFPRO.0112038-9'. None for a register that does not (today: all of ours). "
            "Three traps: (1) this is not the LEI — the EUID is register-issued, mandatory "
            "in the EU and free, the LEI is voluntary, global, LOU-issued and fee-bearing; "
            "an entity may carry both, one or neither. (2) 'EUid' also names the EU Digital "
            "Identity wallet, a personal credential unrelated to company registers. (3) it is "
            "not stable across a register reorganisation, since it encodes the register of "
            "origin (e.g. France's RNE replacing the RCS in 2023). Carried verbatim from the "
            "register; never constructed from parts."
        ),
    )

    # --- names --------------------------------------------------------------
    name: str = Field(description="Current registered name.")
    previous_names: list[str] = Field(
        default_factory=list, description="Former registered names, newest first."
    )

    # --- legal form ---------------------------------------------------------
    legal_form_code: str | None = Field(
        default=None, description="National legal-form code, e.g. 'AS', 'ASA', 'ENK'."
    )
    legal_form: str | None = Field(
        default=None, description="English label, e.g. 'Private limited company'."
    )
    legal_form_local: str | None = Field(
        default=None, description="Local label, e.g. 'Aksjeselskap'."
    )
    limited_liability: bool | None = Field(
        default=None, description="True when owners are not personally liable for debts."
    )
    has_board_duty: bool | None = Field(
        default=None, description="True when this legal form must have a registered board."
    )
    has_annual_accounts_duty: bool | None = Field(
        default=None,
        description="True when this legal form must file annual accounts with the state.",
    )

    # --- status -------------------------------------------------------------
    status: CompanyStatus = Field(
        default=CompanyStatus.UNKNOWN, description="Normalised lifecycle status."
    )
    status_detail: str | None = Field(
        default=None,
        description="One sentence in English explaining the status and the flag it came from.",
    )
    is_active: bool = Field(
        default=False,
        description="Convenience mirror of `status == active`, so agents need no enum table.",
    )

    # --- dates --------------------------------------------------------------
    registered_at: date | None = Field(
        default=None, description="Date first entered in the central register."
    )
    founded_at: date | None = Field(default=None, description="Incorporation / foundation date.")
    business_register_registered_at: date | None = Field(
        default=None,
        description="Date entered in the commercial/business register, where that is separate.",
    )
    bankruptcy_date: date | None = Field(default=None, description="Date bankruptcy was opened.")
    deregistered_at: date | None = Field(
        default=None, description="Date the entity was deleted from the register."
    )

    # --- tax / VAT ----------------------------------------------------------
    vat_registered: bool | None = Field(
        default=None, description="Registered for VAT (Norway: Merverdiavgiftsregisteret)."
    )
    vat_registered_at: date | None = Field(default=None, description="Date of VAT registration.")
    vat_number: str | None = Field(
        default=None,
        description="VAT identifier if it differs from `id` (Norway: id + 'MVA').",
    )

    # --- register memberships ----------------------------------------------
    in_business_register: bool | None = Field(
        default=None,
        description="Listed in the commercial register (Norway: Foretaksregisteret).",
    )
    registers: dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "Other national sub-registers this entity is or is not in, keyed by a "
            "lower-case slug, e.g. {'stiftelsesregisteret': false}."
        ),
    )

    # --- size and activity --------------------------------------------------
    employees: int | None = Field(
        default=None, ge=0, description="Registered number of employees. None = not reported."
    )
    employees_reported: bool | None = Field(
        default=None,
        description="Whether the registry holds an employee figure at all (distinguishes 0 from unknown).",
    )
    industry_codes: list[IndustryCode] = Field(
        default_factory=list, description="Industry classifications, primary first."
    )
    sector_code: str | None = Field(default=None, description="Institutional sector code.")
    sector: str | None = Field(default=None, description="Institutional sector description.")
    purpose: str | None = Field(
        default=None, description="Statutory purpose / objects clause, joined into one string."
    )
    activity: str | None = Field(
        default=None, description="Free-text description of actual activity."
    )

    # --- capital ------------------------------------------------------------
    share_capital: float | None = Field(default=None, description="Registered share capital.")
    share_capital_currency: str | None = Field(
        default=None, description="ISO-4217 code for `share_capital`."
    )

    # --- contact ------------------------------------------------------------
    business_address: Address | None = Field(default=None, description="Visiting/registered office.")
    postal_address: Address | None = Field(default=None, description="Postal address.")
    website: str | None = Field(default=None, description="Website as registered.")
    email: str | None = Field(default=None, description="Contact email as registered.")
    phone: str | None = Field(default=None, description="Contact phone as registered.")
    advertising_protected: bool | None = Field(
        default=None,
        description=(
            "Whether the register marks this entity as protected against direct-marketing "
            "use (Danish CVR-loven § 19 'reklamebeskyttelse', Swedish 'reklamspärr'). "
            "True: the register marks it. False: the register publishes such a flag for "
            "this entity and it is not set. None: this register publishes no such flag at "
            "all — the default, and it must never default to False, since False asserts a "
            "claim about a register that made none. When True, a country module must also "
            "append a `notes` entry containing the phrase 'direct marketing' "
            "(case-insensitive) stating the protection — that phrase is the contract this "
            "model enforces (see the validator below) — because the marking is a legal "
            "condition of passing this record's contact details on, and it must travel with "
            "them."
        ),
    )

    # --- structure ----------------------------------------------------------
    parent_id: str | None = Field(
        default=None, description="Identifier of the parent/owning entity, if any."
    )
    is_subunit: bool = Field(
        default=False, description="True when this record is a branch/sub-unit, not a legal entity."
    )
    in_group: bool | None = Field(default=None, description="Part of a corporate group.")

    # --- accounts -----------------------------------------------------------
    last_annual_accounts_year: int | None = Field(
        default=None, description="Most recent financial year for which accounts were filed."
    )
    published_deadlines: list[PublishedDeadline] = Field(
        default_factory=list,
        description=(
            "Filing dates the upstream register publishes for this entity itself, carried "
            "verbatim. Empty for a register that publishes none — most of them. This is the "
            "input `Registry.deadlines(report, today)` needs to prefer the register's own "
            "figure over any calculation (DECISIONS.md D-018), and it is what keeps that "
            "method the pure function of (report, today) its contract promises."
        ),
    )

    # --- attachments (opt-in via `include=[...]`, D-026(c), D-042) ----------
    lei: LeiRecord | None = Field(
        default=None,
        description=(
            "This entity's Legal Entity Identifier record, from GLEIF — not a national "
            "register (D-026(c), D-045(e)). `None` unless `lei` was passed in "
            "`include=[...]` — and, even then, `None` if that fetch failed (see `notes` "
            "for why). A country that declares this attachment "
            "(`CountryInfo.supported_includes`) returns a *present* block even for an "
            "entity GLEIF holds no LEI for: `LeiRecord.lei` is `None` inside it, which "
            "is a real answer, never the same as this field being absent (D-011). "
            "Declared by default by every country whose identifiers cannot be a "
            "natural person's (`Registry.universal_includes`) — Sweden does not "
            "declare it, because GLEIF is a third-party host queried by identifier in "
            "a URL query string."
        ),
    )
    charges: ChargeBlock | None = Field(
        default=None,
        description=(
            "Registered charges (mortgages / security interests) against this entity. "
            "`None` unless `charges` was passed in `include=[...]` — and, even then, `None` "
            "if that fetch failed (see `notes` for which attachment and why). A country "
            "that declares this attachment (`CountryInfo.supported_includes`) returns a "
            "*present* block with an empty `charges` list for an entity that genuinely has "
            "none — the two states never collapse into each other (D-011, D-042(d))."
        ),
    )

    filings: FilingHistory | None = Field(
        default=None,
        description=(
            "What this entity has filed with its register, and when. `None` unless "
            "`filings` was passed in `include=[...]` — and, even then, `None` if that "
            "fetch failed (see `notes` for which attachment and why). Scope differs by "
            "country because each register publishes a different subset, and the block's "
            "own `notes` says which: Companies House the whole filing history, "
            "Bolagsverket the filed annual reports, Regnskapsregisteret the filed annual "
            "accounts. A *present* block with `documents: []` means the register lists "
            "none — never the same as absent (D-011, D-042(d))."
        ),
    )
    insolvency: InsolvencyBlock | None = Field(
        default=None,
        description=(
            "Insolvency proceedings the register publishes against this entity. `None` "
            "unless `insolvency` was passed in `include=[...]`, or that fetch failed. A "
            "*present* block with `cases: []` means the register publishes no case, which "
            "for Companies House is the normal answer for a solvent company — and is not "
            "evidence the entity exists, since that register answers the same way for a "
            "number never issued. Read `InsolvencyCase.is_liquidation` with its own "
            "caveat: a members' voluntary liquidation is a solvent wind-up."
        ),
    )
    financials: FinancialSummary | None = Field(
        default=None,
        description=(
            "Key figures from this entity's filed annual accounts. `None` unless "
            "`financials` was passed in `include=[...]` — and, even then, `None` if that "
            "fetch failed (see `notes` for which attachment and why). A country that "
            "declares this attachment returns a *present* block with `periods: []` for an "
            "entity the register holds no filed accounts for — the two states never "
            "collapse into each other (D-011, D-042(d)). Norway only, today: Sweden's and "
            "Britain's figures live inside documents this API declines to parse, which is "
            "this project's scope decision, not the register's silence (D-043(i))."
        ),
    )

    # --- provenance ---------------------------------------------------------
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="How sure we are this record is the entity the caller meant (D-005).",
    )
    confidence_basis: str | None = Field(
        default=None,
        description="Why that confidence, e.g. 'exact identifier lookup'.",
    )
    cached: bool = Field(
        default=False, description="True when served from our cache rather than a live fetch."
    )
    fetched_at: datetime | None = Field(
        default=None, description="UTC timestamp of the live fetch this record came from."
    )
    source: str | None = Field(
        default=None, description="Human-readable source name, e.g. 'Enhetsregisteret (brreg.no)'."
    )
    source_url: str | None = Field(
        default=None, description="Direct URL of the upstream record, for citation."
    )
    license: str | None = Field(
        default=None, description="Licence of the upstream data, e.g. 'NLOD 2.0'."
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Caveats an agent should surface to the user, plain English, one per item.",
    )

    @field_validator("country")
    @classmethod
    def _upper_country(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _advertising_protected_true_needs_a_notes_sentence(self) -> Self:
        """D-026(b): ``True`` is a legal condition of passing this entity's
        contact details on (Danish CVR-loven § 19, Swedish *reklamspärr*), and
        that condition is only met if a caller who reads only ``notes`` can
        see it. A country module that sets ``advertising_protected=True``
        must also append a ``notes`` entry containing the phrase "direct
        marketing" (case-insensitive) — enforced here, for every country, not
        only in fixtures.
        """
        if self.advertising_protected is True and not any(
            "direct marketing" in note.lower() for note in self.notes
        ):
            raise ValueError(
                "advertising_protected=True requires a `notes` entry containing the "
                "phrase 'direct marketing' (case-insensitive) — DECISIONS.md D-026(b)."
            )
        return self

    def with_cache_flag(self, cached: bool) -> Self:
        """Return a copy with ``cached`` set — used by the cache layer (T03)."""
        return self.model_copy(update={"cached": cached})


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class SearchHit(_Base):
    """One candidate from a name search.

    Deliberately thin: enough for an agent to pick the right entity and then
    call ``lookup_company`` with ``id`` for the full report.
    """

    country: str = Field(description="ISO-3166-1 alpha-2, upper-case.")
    registry: str = Field(description="Registry slug.")
    id: str = Field(description="Canonical national identifier — feed this to lookup.")
    name: str = Field(description="Registered name.")
    legal_form_code: str | None = Field(default=None, description="National legal-form code.")
    legal_form: str | None = Field(default=None, description="English legal-form label.")
    status: CompanyStatus = Field(
        default=CompanyStatus.UNKNOWN, description="Normalised lifecycle status."
    )
    city: str | None = Field(default=None, description="Post town of the business address.")
    municipality: str | None = Field(default=None, description="Municipality of the business address.")
    registered_at: date | None = Field(default=None, description="Date entered in the register.")
    is_subunit: bool = Field(default=False, description="True for branches / sub-units.")
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Match confidence for this hit (D-005)."
    )
    confidence_basis: str | None = Field(default=None, description="Why that confidence.")
    source_url: str | None = Field(default=None, description="Upstream record URL.")

    @field_validator("country")
    @classmethod
    def _upper_country(cls, v: str) -> str:
        return v.upper()


class SearchResult(_Base):
    """Envelope returned by ``search`` — hits plus what the agent needs next."""

    country: str = Field(description="ISO-3166-1 alpha-2, upper-case.")
    registry: str = Field(description="Registry slug.")
    query: str = Field(description="The name that was searched for.")
    hits: list[SearchHit] = Field(
        default_factory=list,
        description=(
            "Best matches, best first: always sorted by `confidence` descending. Hits that "
            "score equally keep the order the upstream register returned them in."
        ),
    )
    total: int = Field(
        default=0, ge=0, description="Total matches upstream, which may exceed len(hits)."
    )
    truncated: bool = Field(
        default=False, description="True when `total` exceeds the returned hits."
    )
    cached: bool = Field(default=False, description="Served from cache.")
    fetched_at: datetime | None = Field(default=None, description="UTC timestamp of the fetch.")
    hint: str | None = Field(
        default=None,
        description="What to do next, e.g. 'call lookup_company with the id of the right hit'.",
    )

    @field_validator("country")
    @classmethod
    def _upper_country(cls, v: str) -> str:
        return v.upper()

    @field_validator("hits")
    @classmethod
    def _best_first(cls, v: list[SearchHit]) -> list[SearchHit]:
        """Enforce the ordering the ``hits`` description promises (``DECISIONS.md`` D-020).

        The sort lives here, not in a country module, because "best first" is
        part of the shape both surfaces emit (D-004) and ``search`` is abstract
        — there is no concrete wrapper to hang it on the way ``validate`` and
        ``deadline_report`` have one (D-010). A country that forgets to sort is
        therefore impossible rather than merely tested for, and because this is
        a validator it also fires on ``SearchResult.model_validate`` of a cached
        payload, so a cached result and a fresh one cannot disagree about order.

        **Stable, so the register's own relevance order is the tie-break.**
        D-005's confidence anchors are coarse (0.95/0.8/0.6/0.4) and routinely
        tie several hits; within a tie the upstream ranking is real information
        we have no better substitute for. We re-rank by our confidence, we do
        not discard theirs.
        """
        return sorted(v, key=lambda hit: hit.confidence, reverse=True)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ErrorBody(_Base):
    """The inner object of an error response (see ``DECISIONS.md`` D-007)."""

    code: ErrorCode = Field(description="Stable machine-readable code.")
    message: str = Field(description="What went wrong, one sentence, no stack traces.")
    hint: str = Field(
        description=(
            "What the caller should do next, addressed to an AI agent. Always present, "
            "never empty — this field is the product."
        )
    )
    country: str | None = Field(default=None, description="Country the call was for, if known.")
    registry: str | None = Field(default=None, description="Registry the call was for, if known.")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Optional structured extras; never secrets."
    )


class ErrorEnvelope(_Base):
    """The complete error document: ``{"error": {...}}``."""

    error: ErrorBody


class RegistryError(Exception):
    """Raised by every registry module for every expected failure.

    Raised, not returned: ``core`` and the registry modules raise it, and each
    surface (REST in ``api/``, MCP in ``mcp/``) catches it and serialises
    :meth:`envelope` so both produce byte-identical error documents.

    ``hint`` is mandatory. If you cannot say what the agent should do next, you
    have not finished thinking about the error.
    """

    #: Default HTTP status per error code, used by the REST surface (T06).
    HTTP_STATUS: ClassVar[dict[ErrorCode, int]] = {
        ErrorCode.INVALID_ID: 400,
        ErrorCode.BAD_REQUEST: 400,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.UNSUPPORTED_COUNTRY: 404,
        ErrorCode.RATE_LIMITED: 429,
        ErrorCode.NOT_IMPLEMENTED: 501,
        ErrorCode.UPSTREAM_ERROR: 502,
        ErrorCode.UPSTREAM_TIMEOUT: 504,
        ErrorCode.INTERNAL_ERROR: 500,
    }

    def __init__(
        self,
        code: ErrorCode | str,
        message: str,
        hint: str,
        *,
        country: str | None = None,
        registry: str | None = None,
        details: dict[str, Any] | None = None,
        http_status: int | None = None,
    ) -> None:
        self.code = ErrorCode(code)
        self.message = message
        self.hint = hint
        self.country = country.upper() if country else None
        self.registry = registry
        self.details: dict[str, Any] = details or {}
        self.http_status = http_status or self.HTTP_STATUS.get(self.code, 500)
        super().__init__(f"{self.code}: {message}")

    def body(self) -> ErrorBody:
        """The inner error object."""
        return ErrorBody(
            code=self.code,
            message=self.message,
            hint=self.hint,
            country=self.country,
            registry=self.registry,
            details=self.details,
        )

    def envelope(self) -> ErrorEnvelope:
        """The full ``{"error": {...}}`` document."""
        return ErrorEnvelope(error=self.body())

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready ``{"error": {...}}`` — what both surfaces emit."""
        return self.envelope().model_dump(mode="json")
