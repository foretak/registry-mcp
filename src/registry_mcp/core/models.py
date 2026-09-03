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

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "Address",
    "CompanyReport",
    "CompanyStatus",
    "Deadline",
    "DeadlineRecurrence",
    "DeadlineReport",
    "ErrorBody",
    "ErrorCode",
    "ErrorEnvelope",
    "IndustryCode",
    "RegistryError",
    "SearchHit",
    "SearchResult",
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
# Deadlines
# ---------------------------------------------------------------------------


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
    hits: list[SearchHit] = Field(default_factory=list, description="Best matches, best first.")
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
