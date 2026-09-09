"""The plugin interface every national registry module implements.

Adding a country means adding **one folder** under ``registries/`` that defines
a :class:`Registry` subclass and calls :func:`register`. Nothing in ``core/``
or ``api/`` changes (``DECISIONS.md`` D-001, D-008).

Minimal example — the whole contract::

    from registry_mcp.core.registry import Registry, register

    class SeRegistry(Registry):
        country = "SE"
        registry = "bolagsverket"
        id_scheme = "organisationsnummer"
        id_example = "5560160680"

        def validate_id(self, id: str) -> str: ...
        async def lookup(self, id: str) -> CompanyReport: ...
        async def search(self, name: str, limit: int = 10) -> SearchResult: ...
        def deadlines(self, report: CompanyReport, today: date) -> list[Deadline]: ...

    register(SeRegistry())

``lookup`` and ``search`` are async because they do network I/O.
``validate_id`` and ``deadlines`` are sync and pure: no I/O, no clock reads —
``deadlines`` takes ``today`` as a parameter precisely so it stays testable.

Those four are the only methods a country implements. The surfaces do **not**
call ``validate_id`` and ``deadlines`` directly: they call the concrete
:meth:`Registry.validate` and :meth:`Registry.deadline_report`, which wrap the
primitives into the single ``ValidationResult`` / ``DeadlineReport`` document
that REST and MCP both emit (``DECISIONS.md`` D-010).

A country that wants **depth** — a second round trip to the same or a
different upstream endpoint, opt-in via ``include=[...]`` on ``lookup_company``
— declares :attr:`Registry.supported_includes` and adds one concrete method
per name, e.g. ``async def lei(self, id: str) -> LeiRecord: ...``, where the
method name, the ``include`` value and the field it fills on
:class:`~registry_mcp.core.models.CompanyReport` are the same string. Nothing
else changes: the surfaces call the concrete :meth:`Registry.lookup_with`,
which validates ``include`` against :attr:`Registry.supported_includes`,
fetches every requested attachment with bounded concurrency, and leaves a
failed one absent with a ``notes`` sentence rather than failing the whole
lookup (``DECISIONS.md`` D-026(c), D-041(b),(c), D-042(b),(d)). No country
declares an attachment yet — this module ships the mechanism only.
"""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date
from typing import Any, ClassVar

from registry_mcp.core.models import (
    CompanyReport,
    CountryInfo,
    Deadline,
    DeadlineReport,
    ErrorCode,
    LeiRecord,
    ParentBlock,
    RegistryError,
    SearchResult,
    ValidationResult,
)

__all__ = [
    "DEADLINE_INCLUDES",
    "Registry",
    "get_registry",
    "list_countries",
    "list_registries",
    "loggable_query",
    "register",
    "unregister",
]

#: Set ``REGISTRY_MCP_INCLUDE_STUBS=1`` to make stub registries (``XX``) visible
#: to ``list_countries()`` and ``get_registry()`` without passing a flag. Used by
#: the test suite and by anyone developing a new country module.
_INCLUDE_STUBS_ENV = "REGISTRY_MCP_INCLUDE_STUBS"

#: The closed set of ``include=[...]`` values the **deadlines operation** can
#: use, as opposed to what a country publishes (``DECISIONS.md`` D-043(j),
#: D-045(g)). ``company_deadlines`` intersects this with a registry's own
#: :attr:`Registry.supported_includes` in :meth:`Registry.deadline_report_with`
#: — never with :attr:`Registry.effective_includes` — because every member of
#: this set must be a per-country attachment that can change a *computed*
#: date; ``lei`` and ``parents`` cannot, so neither is ever a candidate
#: regardless of how many countries declare it via
#: :attr:`Registry.universal_includes`, and neither is Peppol participant
#: status once a country declares it, which is why this
#: set must never contain ``"peppol"``. Today that leaves exactly ``filings``:
#: a country's own filed-annual-report history, which can supply a real
#: financial year end where one was previously assumed. A country that
#: declares ``filings`` in :attr:`Registry.supported_includes` gets it here
#: for free — no country module edits this set or even imports it.
DEADLINE_INCLUDES: frozenset[str] = frozenset({"filings"})


class Registry(ABC):
    """One national business register.

    Subclasses are instantiated once and registered by country code. They must
    be stateless apart from clients/caches they own; the same instance serves
    every request.
    """

    # -- identity ------------------------------------------------------------

    country: ClassVar[str]
    """ISO-3166-1 alpha-2 country code, upper-case. E.g. ``"NO"``."""

    registry: ClassVar[str]
    """Short lower-case slug for the register itself. E.g. ``"brreg"``."""

    name: ClassVar[str] = ""
    """Human-readable register name, e.g. ``"Enhetsregisteret (Brønnøysundregistrene)"``."""

    id_scheme: ClassVar[str] = ""
    """What the national identifier is called locally, e.g. ``"organisasjonsnummer"``."""

    id_example: ClassVar[str] = ""
    """A real, valid identifier an agent can use to smoke-test the tool."""

    id_description: ClassVar[str] = ""
    """One sentence describing the identifier's format, for tool docstrings."""

    source_url: ClassVar[str] = ""
    """Base URL of the upstream API, for citation."""

    license: ClassVar[str] = ""
    """Licence of the upstream data, e.g. ``"NLOD 2.0"``."""

    is_stub: ClassVar[bool] = False
    """True for example/skeleton modules that must stay out of the public country list."""

    requires_api_key: ClassVar[bool] = False
    """True when the upstream API needs a credential the operator must supply.

    Declarative, not a health check: it says *this registry cannot work without a
    key*, never *this deployment has one*. A module that sets it must still raise
    ``RegistryError(UPSTREAM_ERROR)`` with a hint naming :attr:`api_key_env` when
    the variable is unset — the flag makes that discoverable in advance, it does
    not replace the error (``DECISIONS.md`` D-017).
    """

    api_key_env: ClassVar[str] = ""
    """Environment variable holding that credential, e.g. ``"COMPANIES_HOUSE_API_KEY"``.

    Empty when no key is needed. **Never the key itself** — this value is
    published by ``GET /v1/countries`` and the MCP ``list_countries`` tool.
    """

    id_may_be_personal: ClassVar[bool] = False
    """True when an identifier this registry accepts can be a natural person's
    national identity number (Sweden: a sole trader's organisationsnummer is
    their personnummer). The surfaces consult it before logging; the module
    does not.
    """

    supported_includes: ClassVar[frozenset[str]] = frozenset()
    """The closed set of ``include=[...]`` values this registry declares.

    Empty by default, like :attr:`requires_api_key` (``DECISIONS.md`` D-017):
    a country that offers no attachments gains nothing and edits nothing. A
    non-default value both (a) is what :meth:`lookup_with` validates a
    caller's ``include`` argument against, and (b) is surfaced verbatim,
    sorted, as ``CountryInfo.supported_includes`` — so an agent can discover
    what a country offers *before* asking (``DECISIONS.md`` D-042(d)).

    Each name in this set must be exactly the name of a concrete, awaitable
    method this class defines — ``async def <name>(self, id: str) -> ...`` —
    and, per D-042(b),(g), exactly the name of the field on
    :class:`~registry_mcp.core.models.CompanyReport` that method's result is
    attached to. :meth:`lookup_with` calls that method dynamically by name;
    a mismatch (a declared include with no matching field, or no matching
    method) is a country-module bug and fails loudly there, not silently.

    See also :attr:`universal_includes` and :attr:`effective_includes`: a
    country's *own* declared set, unioned with the attachments every country
    gets by default.
    """

    universal_includes: ClassVar[frozenset[str]] = frozenset({"lei", "parents"})
    """Attachments whose upstream is not a national register, and which
    every country therefore declares by default (``DECISIONS.md`` D-045(e),
    D-047(a)).

    Both members today — ``lei`` and ``parents`` — are GLEIF: it publishes
    every jurisdiction from one endpoint, under one CC0 licence, with one
    TTL, so this is not *any* country's own register and a per-country
    declaration would be three (eventually more) modules asserting the same
    global fact. A country module adds nothing and edits nothing to gain
    either, unlike :attr:`supported_includes` — see :attr:`effective_includes`,
    which is what every call site actually reads instead of this attribute
    alone. A future non-GLEIF universal attachment would join this set the
    same way; nothing about it is GLEIF-specific by construction.
    """

    @property
    def effective_includes(self) -> frozenset[str]:
        """:attr:`universal_includes` unioned with :attr:`supported_includes`
        — what a caller may actually pass to :meth:`lookup_with`, and what
        :meth:`country_info` publishes as ``CountryInfo.supported_includes``.

        The one helper every call site uses (``DECISIONS.md`` D-045(e)), so
        the union is never inlined three times.

        **The** :attr:`id_may_be_personal` **subtraction is not optional.**
        Every attachment in :attr:`universal_includes` today sends the
        identifier to a third-party host, in a URL query string (GLEIF is
        queried by ``filter[entity.registeredAs]=<identifier>``). For a
        registry whose identifiers can be a natural person's national
        identity number (Sweden: a sole trader's organisationsnummer is
        their personnummer, D-039), that string reaching a third party's
        URLs, access logs and ``Referer`` headers is exactly what
        :attr:`id_may_be_personal` exists to prevent (D-040) — unlike
        Bolagsverket's own second call, which D-041(g) permits because it is
        the same host, the same TLS session and a POST body. GLEIF is none
        of those. So a registry with the flag set gets none of
        :attr:`universal_includes`, no matter what it declares in
        :attr:`supported_includes`.
        """
        universal = frozenset() if self.id_may_be_personal else type(self).universal_includes
        return universal | self.supported_includes

    # -- required operations -------------------------------------------------

    @abstractmethod
    def validate_id(self, id: str) -> str:
        """Normalise and check a national identifier.

        Args:
            id: The identifier as the caller typed it — may contain spaces,
                dots, a country prefix, or a VAT suffix.

        Returns:
            The canonical form (what :meth:`lookup` expects and what appears as
            ``CompanyReport.id``).

        Raises:
            RegistryError: with ``code=ErrorCode.INVALID_ID`` and a hint saying
                what a valid identifier looks like for this country.
        """

    @abstractmethod
    async def lookup(self, id: str) -> CompanyReport:
        """Fetch the full report for one entity.

        Implementations must call :meth:`validate_id` first, consult the cache,
        and set ``cached``, ``fetched_at``, ``source``, ``source_url`` and
        ``confidence`` on the result.

        Raises:
            RegistryError: ``invalid_id``, ``not_found``, ``upstream_timeout``
                or ``upstream_error``.
        """

    @abstractmethod
    async def search(self, name: str, limit: int = 10) -> SearchResult:
        """Find entities by name.

        Args:
            name: Free-text company name. Never an identifier — if it looks
                like one, the surface layer should route to :meth:`lookup`.
            limit: Maximum hits to return, 1..100.

        Raises:
            RegistryError: ``bad_request``, ``upstream_timeout`` or ``upstream_error``.
        """

    @abstractmethod
    def deadlines(self, report: CompanyReport, today: date) -> list[Deadline]:
        """Compute the filing deadlines this entity faces, sorted by ``due_date``.

        Pure and deterministic: same ``report`` plus same ``today`` always gives
        the same list. Never reads the clock — ``today`` is the clock.

        Args:
            report: A report produced by this same registry.
            today: The date to compute "next occurrence" from, inclusive.
        """

    # -- canonical response builders (do not override lightly) ----------------
    #
    # These two are concrete on purpose (``DECISIONS.md`` D-010). A country
    # module implements the *pure* primitives above — ``validate_id`` returns a
    # string or raises, ``deadlines`` returns a list — and the base class turns
    # them into the one document shape both surfaces emit. A surface calls
    # these; it never assembles ``DeadlineReport`` or ``ValidationResult``
    # itself, because two assemblers are two shapes waiting to drift apart.

    def deadline_report(self, report: CompanyReport, today: date) -> DeadlineReport:
        """Wrap :meth:`deadlines` into the document REST and MCP both return.

        ``notes`` is carried over from ``report.notes`` verbatim: every caveat
        that explains an empty or surprising list (bankrupt, deleted, sub-unit,
        unclassified legal form) is put there by the country module's mapping,
        so ``core`` synthesises no prose of its own and stays country-neutral
        (``DECISIONS.md`` D-001).

        Args:
            report: A report produced by this same registry.
            today: The date to compute "next occurrence" from, inclusive.
        """
        return DeadlineReport(
            country=self.country,
            registry=self.registry,
            company_id=report.id,
            company_name=report.name,
            today=today,
            deadlines=self.deadlines(report, today),
            notes=list(report.notes),
        )

    def validate(self, id: str) -> ValidationResult:
        """Answer "is this identifier well-formed?" without raising.

        Wraps :meth:`validate_id`: an ``invalid_id`` failure becomes
        ``valid=False`` plus the error's own message and hint, because this
        operation *answers a question* rather than failing at one. Any other
        ``RegistryError`` still propagates — an unsupported country or an
        internal fault is a real error, not a validation verdict.
        """
        try:
            normalized = self.validate_id(id)
        except RegistryError as exc:
            if exc.code is not ErrorCode.INVALID_ID:
                raise
            return ValidationResult(
                country=self.country,
                registry=self.registry,
                id_scheme=self.id_scheme or None,
                input=id,
                valid=False,
                reason=exc.message,
                hint=exc.hint,
            )
        reason = (
            f"Well-formed {self.id_scheme or 'identifier'} for {self.country}. "
            "A valid identifier does not mean the entity exists — call lookup_company "
            "(MCP) or GET /v1/{country}/company/{id} (REST) to find out."
        )
        caveat = self.id_caveat(normalized)
        if caveat:
            reason = f"{reason} {caveat}"

        return ValidationResult(
            country=self.country,
            registry=self.registry,
            id_scheme=self.id_scheme or None,
            input=id,
            valid=True,
            normalized=normalized,
            formatted=self.format_id(normalized),
            reason=reason,
        )

    async def lookup_with(
        self, id: str, include: Sequence[str] = (), *, max_concurrency: int = 5
    ) -> CompanyReport:
        """Fetch the base report and merge in every requested attachment.

        The one assembler for ``include=[...]`` (``DECISIONS.md`` D-026(c),
        D-041(b), D-042(b)): every surface calls this rather than validating
        ``include`` or handling a failed attachment itself, so both of those
        live in one place instead of being reimplemented per surface and per
        country — and drifting the moment one of the copies is not updated.

        Args:
            id: passed to :meth:`lookup` and, unchanged, to every requested
                attachment method — an attachment never takes a second
                identifier scheme.
            include: attachment names to fetch alongside the base report.
                Must be a subset of :attr:`effective_includes`. ``()`` (the
                default) fetches nothing extra, so ``lookup_with(id)`` costs
                exactly the one upstream request ``lookup(id)`` costs.
                Duplicates are fetched once, not once each.
            max_concurrency: bound on simultaneous attachment fetches
                (``DECISIONS.md`` D-024(g): at most 5 in flight).

        Returns:
            The report from :meth:`lookup`, with one field set per
            successfully fetched attachment (same name as the ``include``
            value) and, for any attachment that failed, that field left
            absent and one sentence appended to ``notes`` naming which
            attachment and why. **A failed attachment never fails the
            lookup** (``DECISIONS.md`` D-042(b),(j)) — only :meth:`lookup`
            failing does that.

        Raises:
            RegistryError: whatever :meth:`lookup` raises, unchanged —
                nothing to attach to without a base report. ``bad_request``,
                raised before :meth:`lookup` is even called, when
                ``include`` names a value outside :attr:`effective_includes`;
                its ``hint`` and ``details["allowed"]`` name that registry's
                effective declared set (``DECISIONS.md`` D-042(d), D-045(e))
                — never silently ignored and never answered with an empty
                block.
            RuntimeError: a country-module bug, never a caller's mistake — a
                name in :attr:`effective_includes` with no matching method,
                or whose method's result does not match a field on the
                report :meth:`lookup` returns. Checked for every requested
                name before any network I/O happens for it: the method half
                before :meth:`lookup` is even called, the field half right
                after, so both fail loudly here rather than escaping as a
                bare ``AttributeError`` or hiding behind a plausible-looking
                failed-fetch note (``REVIEW.md`` § S-series finding 6).
        """
        effective = self.effective_includes
        unknown = sorted({name for name in include if name not in effective})
        if unknown:
            allowed = sorted(effective)
            raise RegistryError(
                ErrorCode.BAD_REQUEST,
                f"Unknown include value(s) for {self.country}: {', '.join(unknown)}.",
                hint=(
                    f"Allowed include values for {self.country} today: "
                    f"{', '.join(allowed) if allowed else '(this registry declares none yet)'}."
                ),
                country=self.country,
                registry=self.registry,
                details={"allowed": allowed, "unknown": unknown},
            )

        # De-duplicated, first-occurrence order: a repeated include value
        # costs one fetch, not two (the same principle D-024(e) applies to
        # a repeated batch identifier).
        names = list(dict.fromkeys(include))

        # Misconfiguration guard, part one (method): needs no report, so it
        # runs before `lookup` is even attempted — a broken country module
        # fails loudly for free rather than spending a network call first.
        # `getattr(self, name)` inside `_fetch` below used to let this
        # escape as a bare `AttributeError` (S-series finding 6).
        for name in names:
            if not callable(getattr(type(self), name, None)):
                raise RuntimeError(
                    f"{type(self).__name__} declares include {name!r} but defines no "
                    "matching method — a country-module bug (DECISIONS.md D-042(b),(g)), "
                    "not a runtime condition."
                )

        report = await self.lookup(id)
        if not names:
            return report

        # Misconfiguration guard, part two (report field): checked for
        # *every* requested name, not only the ones about to be fetched
        # successfully — otherwise a misconfigured include whose method
        # raises `RegistryError` hides behind a plausible-looking
        # failed-fetch note instead of failing loudly (S-series finding 6's
        # third, previously-silent case). Run before any attachment is
        # actually fetched.
        report_fields = type(report).model_fields
        misconfigured = sorted(name for name in names if name not in report_fields)
        if misconfigured:
            raise RuntimeError(
                f"{type(self).__name__} declares include(s) {misconfigured!r} but "
                f"{type(report).__name__} has no matching field for it — a "
                "country-module bug (DECISIONS.md D-042(b),(g)), not a runtime "
                "condition."
            )

        semaphore = asyncio.Semaphore(max_concurrency)

        async def _fetch(name: str) -> tuple[str, Any, RegistryError | None]:
            method = getattr(self, name)
            try:
                async with semaphore:
                    block: Any = await method(id)
            except RegistryError as exc:
                return name, None, exc
            return name, block, None

        fetched = await asyncio.gather(*(_fetch(name) for name in names))

        updates: dict[str, Any] = {}
        notes = list(report.notes)
        for name, block, error in fetched:
            if error is not None:
                notes.append(f"Could not fetch the '{name}' attachment: {error.message}")
            else:
                updates[name] = block

        if not updates and notes == report.notes:
            return report
        return report.model_copy(update={**updates, "notes": notes})

    async def deadline_report_with(
        self, id: str, include: Sequence[str], today: date
    ) -> DeadlineReport:
        """The ``company_deadlines`` analogue of :meth:`lookup_with` (``DECISIONS.md`` D-045(g)).

        Both surfaces used to do ``report = await registry.lookup(id)`` then
        ``registry.deadline_report(report, today)``. Swapping in
        ``lookup_with(id, include)`` is **not** sufficient, because
        ``company_deadlines`` accepts a **narrower** ``include`` vocabulary
        than ``lookup_company`` does: an attachment belongs here only if it
        can change a *computed* date (D-043(j)) — today, just ``filings``,
        whose ``financial_year_end`` can replace an assumed accounting period
        with the register's own figure. ``financials``, ``lei``, ``charges``
        and ``insolvency`` cannot move a deadline no matter how many
        countries declare them, so this method validates ``include`` against
        ``self.supported_includes & DEADLINE_INCLUDES`` — that intersection,
        deliberately **not** :attr:`effective_includes` (which would let
        ``lei`` through for every country that gets it for free) and not
        :attr:`supported_includes` alone (which would let ``financials``
        through for Norway) — before any network I/O happens. A rejected
        value's ``hint`` names *this operation's* allowed set, which can
        genuinely differ from :attr:`CountryInfo.supported_includes`: that
        attribute keeps listing the country's full declared set unchanged,
        because it describes what the country publishes, not what this one
        operation can use (D-043(j)'s forward constraint, D-042(d)).

        Once validated, this delegates entirely to the two existing concrete
        builders and adds no logic of its own: :meth:`lookup_with` fetches
        the report and every requested attachment, and :meth:`deadline_report`
        turns the result into the document both surfaces emit. So
        :meth:`deadlines` stays the pure function of ``(report, today)``
        D-018 requires, and neither surface duplicates this validation itself
        — D-042(b)'s finding verbatim, *"written per surface it drifts within
        a release"* — nor gains an ``allowed=`` parameter on :meth:`lookup_with`,
        which would give one method two contracts and put this operation's
        vocabulary into the lookup path's signature.

        Args:
            id: passed to :meth:`lookup_with` unchanged.
            include: attachment names relevant to a deadline computation, a
                subset of ``self.supported_includes & DEADLINE_INCLUDES``.
                ``()`` costs exactly one upstream request, identical to
                today's plain ``lookup``.
            today: the date to compute "next occurrence" from, inclusive —
                passed straight through to :meth:`deadline_report`.

        Returns:
            The same :class:`~registry_mcp.core.models.DeadlineReport`
            :meth:`deadline_report` always returns. ``DeadlineReport`` does
            **not** gain an attachment block of its own (D-041(b), D-010): a
            successfully fetched attachment's effect is visible only through
            each ``Deadline.applies_because`` and through ``notes`` — a
            caller who wants the attachment itself calls ``lookup_company``.

        Raises:
            RegistryError: ``bad_request``, raised before any network I/O,
                when ``include`` names a value outside
                ``self.supported_includes & DEADLINE_INCLUDES`` — its
                ``hint`` and ``details["allowed"]`` name that intersection,
                sorted, never the wider country-level set. Otherwise,
                whatever :meth:`lookup_with` raises, unchanged: nothing to
                compute a deadline from without a base report.
        """
        allowed = self.supported_includes & DEADLINE_INCLUDES
        unknown = sorted({name for name in include if name not in allowed})
        if unknown:
            allowed_sorted = sorted(allowed)
            raise RegistryError(
                ErrorCode.BAD_REQUEST,
                f"company_deadlines does not accept include value(s) for {self.country}: "
                f"{', '.join(unknown)}.",
                hint=(
                    "company_deadlines only accepts include values that can change a "
                    f"computed date. Allowed for {self.country} today: "
                    f"{', '.join(allowed_sorted) if allowed_sorted else '(none)'}. "
                    "lookup_company accepts a wider set — call it directly, or call "
                    "list_countries for this country's full supported_includes."
                ),
                country=self.country,
                registry=self.registry,
                details={"allowed": allowed_sorted, "unknown": unknown},
            )
        report = await self.lookup_with(id, include)
        return self.deadline_report(report, today)

    async def lei(self, id: str) -> LeiRecord:
        """The Legal Entity Identifier GLEIF publishes for this entity.

        The base class's own concrete attachment (``DECISIONS.md`` D-045(e))
        — unlike every other ``include=[...]`` value, this upstream is not
        any country's own register: GLEIF publishes every jurisdiction from
        one endpoint, under one CC0 licence, with one TTL, so it lives here
        once instead of being declared identically by three (eventually
        more) country modules. See :attr:`universal_includes`.

        Normalises ``id`` through :meth:`validate_id` first, exactly as
        every other method here does, so an invalid id raises ``invalid_id``
        before a request is made. Queries GLEIF's own
        ``entity.registeredAs``, which is an *exact* match on the string the
        national register itself published to GLEIF and not on this
        project's own normalised form: :meth:`format_id`'s output is tried
        first when it is not ``None``, and the bare, normalised ``id`` only
        on a zero-hit miss (D-045(e)'s measured trap — Norway and Sweden
        both group their identifiers when reporting to GLEIF, so a
        bare-digit query for either returns zero hits, which reads exactly
        like "no LEI"). ``core/gleif.py`` does the actual HTTP call, cache
        read/write and mapping; this method only normalises the id and
        delegates, so no HTTP transport dependency is imported here.

        Returns a **present** :class:`~registry_mcp.core.models.LeiRecord`
        even when GLEIF holds no LEI for this entity (``lei=None``) — a
        real, useful answer about a counterparty, not an absence (D-011,
        D-026(c)).

        Raises:
            RegistryError: ``invalid_id`` from :meth:`validate_id`, or
                ``upstream_error`` on any GLEIF transport failure or
                non-200 response. :meth:`lookup_with` turns the latter into
                an absent block plus a ``notes`` sentence rather than
                failing the whole lookup (D-042(b)).
        """
        from registry_mcp.core import gleif

        normalized = self.validate_id(id)
        result: LeiRecord = await gleif.fetch_lei(
            self.country, self.registry, normalized, self.format_id(normalized)
        )
        return result

    async def parents(self, id: str) -> ParentBlock:
        """Corporate parents from GLEIF Level 2 — accounting consolidation,
        not shareholding (``DECISIONS.md`` D-047(a)).

        The base class's own concrete attachment, exactly like :meth:`lei`
        and for the same reason: GLEIF is not any one country's own
        register, so it lives here once instead of being declared
        identically by three (eventually more) country modules (see
        :attr:`universal_includes`).

        Normalises ``id`` through :meth:`validate_id` first and delegates to
        ``core/gleif.py``, passing the same ``(country, registry, normalized,
        format_id(normalized))`` tuple :meth:`lei` passes — that tuple is
        what lets ``core/gleif.py`` share one discovery search between the
        two attachments rather than making it twice on a cold cache
        (D-043(h)(3)'s hazard, in a new place). ``core/gleif.py`` does the
        actual HTTP calls, cache read/write and mapping; this method only
        normalises the id and delegates, so no HTTP transport dependency is
        imported here.

        Returns a **present** :class:`~registry_mcp.core.models.ParentBlock`
        even when GLEIF holds no LEI for this entity at all (``direct`` and
        ``ultimate`` both ``None``) — GLEIF cannot hold Level 2 for an
        entity it has no Level 1 for, and that is the answer, not an
        absence (D-011).

        Raises:
            RegistryError: ``invalid_id`` from :meth:`validate_id`, or
                ``upstream_error`` when the discovery search itself fails —
                never for a failure confined to one side's own fetch, which
                degrades that side to ``None`` with a ``notes`` sentence
                instead (D-042(b),(j)). :meth:`lookup_with` turns the
                propagated error into an absent block plus a report-level
                note rather than failing the whole lookup.
        """
        from registry_mcp.core import gleif

        normalized = self.validate_id(id)
        result: ParentBlock = await gleif.fetch_parents(
            self.country, self.registry, normalized, self.format_id(normalized)
        )
        return result

    # -- optional helpers ----------------------------------------------------

    def format_id(self, id: str) -> str | None:
        """The identifier as a local would write it, e.g. ``"923 609 016"``.

        Takes an already-normalised identifier. Returns ``None`` when the
        country has no conventional grouping — the default.
        """
        return None

    def id_caveat(self, id: str) -> str | None:
        """Something true and worth saying about an identifier that **passed**.

        Takes an already-normalised, already-valid identifier and returns one
        sentence to append to :attr:`ValidationResult.reason`, or ``None`` —
        the default, and what every country gets until it opts in
        (``DECISIONS.md`` D-021).

        This is for the case where the shape is right but our knowledge is
        incomplete: a UK company number carrying a prefix that is not in the
        Companies House prefix list this module knows about, say. Rejecting
        such a number is the worse error — Companies House adds prefixes (``OE``
        arrived with ECTEA 2022), and a validator written a year too early turns
        a real company into an ``invalid_id`` (D-015). So ``valid`` stays
        ``True`` and we say what we do not know instead, naming the call that
        settles it.

        Two rules, both load-bearing:

        * The result goes in ``reason``, never in ``hint``. ``hint`` stays
          ``None`` whenever ``valid is True`` (D-010, restated by D-013), and a
          caveat is not a next action.
        * It must never read as a rejection. Date the claim ("not in the list
          this module knows as of …") so a reader can tell a stale table from a
          bad number, and name ``lookup_company`` as the thing that confirms.
        """
        return None

    def rules_markdown(self) -> str:
        """Human/LLM readable description of this country's rules.

        Served as the MCP resource ``registry://rules/{country}`` (T07).
        The default tells the caller nothing useful; override it.
        """
        return f"No rules documentation available for {self.country}."

    async def aclose(self) -> None:
        """Release anything this registry holds open — HTTP clients, pools.

        Concrete and a no-op by default, so a country module that owns no
        resources implements nothing and the ABC stays four methods wide
        (``DECISIONS.md`` D-008, D-014). A module that keeps a shared
        ``httpx.AsyncClient`` **must** override this, because the surface calls
        it on process shutdown and there is no other hook: without an override
        the client is dropped rather than closed and the sockets leak.
        """
        return None

    def country_info(self) -> CountryInfo:
        """This registry as the typed discovery row both surfaces return.

        The single builder behind ``GET /v1/countries`` and the MCP
        ``list_countries`` tool (``DECISIONS.md`` D-012) — the same rule D-010
        applies to ``validate``/``deadline_report``: a surface calls this, it
        never assembles the row itself.
        """
        return CountryInfo(
            country=self.country,
            registry=self.registry,
            name=self.name,
            id_scheme=self.id_scheme,
            id_example=self.id_example,
            id_description=self.id_description,
            source_url=self.source_url,
            license=self.license,
            is_stub=self.is_stub,
            requires_api_key=self.requires_api_key,
            api_key_env=self.api_key_env or None,
            supported_includes=sorted(self.effective_includes),
        )

    def describe(self) -> dict[str, str | bool]:
        """Metadata row for ``GET /v1/countries`` and the MCP ``list_countries`` tool.

        Kept as a plain dict for the surfaces that already call it; it is now
        derived from :meth:`country_info` so there is exactly one definition of
        the row. New code should call :meth:`country_info` and let
        ``CountriesResponse`` do the serialising (D-012).
        """
        return dict(self.country_info().model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_REGISTRIES: dict[str, Registry] = {}


def register(instance: Registry) -> Registry:
    """Register a registry instance under its ``country`` code.

    Called at import time from ``registries/<cc>/__init__.py``. Re-registering
    the same country replaces the previous instance (useful in tests).
    """
    country = instance.country.upper()
    if not (len(country) == 2 and country.isalpha()):
        raise ValueError(f"country must be an ISO-3166-1 alpha-2 code, got {instance.country!r}")
    _REGISTRIES[country] = instance
    return instance


def unregister(country: str) -> None:
    """Remove a registry. Test helper; not used in production code."""
    _REGISTRIES.pop(country.upper(), None)


def _stubs_visible(include_stubs: bool | None) -> bool:
    if include_stubs is not None:
        return include_stubs
    return os.environ.get(_INCLUDE_STUBS_ENV, "").strip().lower() in {"1", "true", "yes"}


def get_registry(country: str, *, include_stubs: bool | None = None) -> Registry:
    """Look up the registry for a country code.

    Args:
        country: ISO-3166-1 alpha-2, any case.
        include_stubs: Allow stub registries. ``None`` (default) reads
            ``REGISTRY_MCP_INCLUDE_STUBS``.

    Raises:
        RegistryError: ``unsupported_country``, with a hint listing the
            countries that *are* supported — so an agent's next call succeeds.
    """
    _load_registries()
    code = country.strip().upper()
    found = _REGISTRIES.get(code)
    if found is not None and (not found.is_stub or _stubs_visible(include_stubs)):
        return found
    supported = list_countries(include_stubs=include_stubs)
    raise RegistryError(
        ErrorCode.UNSUPPORTED_COUNTRY,
        f"No registry module is available for country {code!r}.",
        hint=(
            "Call list_countries (MCP) or GET /v1/countries (REST) for the current list. "
            f"Supported right now: {', '.join(supported) or 'none'}."
        ),
        country=code,
        details={"supported": supported},
    )


def list_countries(*, include_stubs: bool | None = None) -> list[str]:
    """Country codes with a working registry module, sorted.

    Stub modules (``registries/xx/``) are hidden by default so the public
    country list never advertises something that raises ``not_implemented``
    (``DECISIONS.md`` D-008).
    """
    _load_registries()
    show_stubs = _stubs_visible(include_stubs)
    return sorted(cc for cc, r in _REGISTRIES.items() if show_stubs or not r.is_stub)


def list_registries(*, include_stubs: bool | None = None) -> list[Registry]:
    """The registry instances behind :func:`list_countries`, in the same order."""
    _load_registries()
    show_stubs = _stubs_visible(include_stubs)
    return [
        _REGISTRIES[cc]
        for cc in sorted(_REGISTRIES)
        if show_stubs or not _REGISTRIES[cc].is_stub
    ]


_loaded = False


def _load_registries() -> None:
    """Import every bundled registry module once, so each can call :func:`register`.

    Adding a country means adding its import to ``registries/__init__.py`` —
    the only shared line a new country touches, and it is outside ``core/``.
    """
    global _loaded
    if _loaded:
        return
    _loaded = True
    # Deferred import: importing the package registers every bundled country.
    import importlib

    importlib.import_module("registry_mcp.registries")


# ---------------------------------------------------------------------------
# Logging chokepoint (`DECISIONS.md` D-040)
# ---------------------------------------------------------------------------


def loggable_query(country: str | None, query: str | None) -> str | None:
    """The ``query`` value a surface may pass to ``core/log.py::log_call``.

    ``api/main.py::_record`` and ``mcp/server.py::_call_context`` call this —
    nowhere else, so adding a country with :attr:`Registry.id_may_be_personal`
    set changes no route, no tool, and no other line in either surface
    (D-040(b)).

    ``country=None`` (an operation that never carries one, e.g. ``list_countries``,
    or one of the two MCP connector aliases before it has parsed enough of its
    argument to know) returns ``query`` unchanged — there is nothing to protect
    against without a country to check. An unresolvable country (stub modules
    included, via ``include_stubs=True``) also returns ``query`` unchanged: a
    country this service does not serve cannot be Sweden, so losing a real,
    identifiable query to a typo or a not-yet-registered code would cost more
    than it protects. Otherwise: ``None`` when the resolved registry's
    :attr:`Registry.id_may_be_personal` is set, else ``query`` unchanged.

    Pure and never raises.
    """
    if country is None:
        return query
    try:
        registry = get_registry(country, include_stubs=True)
    except RegistryError:
        return query
    return None if registry.id_may_be_personal else query
