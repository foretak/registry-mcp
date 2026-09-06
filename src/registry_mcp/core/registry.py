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
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import date
from typing import ClassVar

from registry_mcp.core.models import (
    CompanyReport,
    CountryInfo,
    Deadline,
    DeadlineReport,
    ErrorCode,
    RegistryError,
    SearchResult,
    ValidationResult,
)

__all__ = [
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
