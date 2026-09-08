"""United Kingdom — Companies House.

``validate_id`` and ``deadlines`` delegate to ``registries/gb/rules.py``
(company-number shape validation, legal-form table, status derivation, the
two filing deadlines). ``lookup`` and ``search`` delegate to
``registries/gb/client.py`` (HTTP + cache + ``registries/gb/mapping.py``).

Every delegate is imported lazily, inside the method body, matching
``registries/no/__init__.py``'s convention: this module is imported
unconditionally at package load (``registries/__init__.py``), so a lazy
import means a problem in ``rules.py``/``client.py`` never breaks
``import registry_mcp.registries`` itself — in particular, a missing
``COMPANIES_HOUSE_API_KEY`` must never do that (``UK_SPEC.md`` §1.1).

See ``DECISIONS.md`` D-015 (``GB``, no ``UK`` alias), D-016 (the deadline
policy) and D-017 (``requires_api_key`` / ``api_key_env``).
"""

from __future__ import annotations

from datetime import date
from typing import ClassVar

from registry_mcp.core.models import (
    ChargeBlock,
    CompanyReport,
    Deadline,
    FilingHistory,
    InsolvencyBlock,
    SearchResult,
)
from registry_mcp.core.registry import Registry, register

__all__ = ["CompaniesHouseRegistry"]


class CompaniesHouseRegistry(Registry):
    """The UK registrar of companies."""

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
    supported_includes: ClassVar[frozenset[str]] = frozenset({"charges", "filings", "insolvency"})

    def validate_id(self, id: str) -> str:
        """Normalise and shape-check a UK company number (``registries/gb/rules.py``)."""
        from registry_mcp.registries.gb import rules

        result: str = rules.validate_crn(id)
        return result

    def id_caveat(self, id: str) -> str | None:
        """A prefix-provenance caveat appended to a valid ``ValidationResult.reason``
        (``registries/gb/rules.py``, ``DECISIONS.md`` D-021)."""
        from registry_mcp.registries.gb import rules

        result: str | None = rules.id_caveat(id)
        return result

    async def lookup(self, id: str) -> CompanyReport:
        """Fetch one entity from Companies House (``registries/gb/client.py``)."""
        from registry_mcp.registries.gb import client

        return await client.lookup(id)

    async def search(self, name: str, limit: int = 10) -> SearchResult:
        """Search Companies House by name (``registries/gb/client.py``)."""
        from registry_mcp.registries.gb import client

        return await client.search(name, limit)

    async def charges(self, id: str) -> ChargeBlock:
        """Registered charges (mortgages) for this entity (``registries/gb/client.py``).

        The ``include=["charges"]`` attachment (``DECISIONS.md`` D-042,
        ``tasks/T37.md``): :meth:`Registry.lookup_with` calls this by name —
        it must stay named exactly ``charges``, matching both
        :attr:`supported_includes` and :class:`~registry_mcp.core.models.
        CompanyReport`'s ``charges`` field (D-042(b),(g)).

        ``registries/gb/charges.py`` builds the canonical ``ChargeBlock``
        directly — there is no seam left to cross here.

        A malformed ``id`` raises ``invalid_id`` the same way :meth:`lookup`
        does; a company with no registered charges still returns a
        **present** ``ChargeBlock`` with an empty ``charges`` list, never
        ``not_found`` (D-041(h), confirmed live — ``registries/gb/charges.py``'s
        module docstring).
        """
        from registry_mcp.registries.gb import client

        return await client.fetch_charges(id)

    async def filings(self, id: str) -> FilingHistory:
        """Everything this entity has filed with Companies House (``registries/gb/filing_history.py``).

        The ``include=["filings"]`` attachment (``DECISIONS.md`` D-041(d),
        D-042): :meth:`Registry.lookup_with` calls this by name, so it must
        stay named exactly ``filings``, matching both
        :attr:`supported_includes` and :class:`~registry_mcp.core.models.
        CompanyReport`'s ``filings`` field (D-042(b),(g)).

        Companies House publishes the **whole** filing history here, not just
        accounts: one page of the newest filings, at most
        ``filing_history.FILINGS_ITEMS_PER_PAGE`` (25) entries, with
        ``total_count`` and a ``notes`` sentence disclosing any truncation
        rather than hiding it (D-042(j)).

        ``registries/gb/filing_history.py`` builds the canonical
        ``FilingHistory`` directly — all three countries converged on the
        same shape independently (D-044(a)), and there is no seam left to
        cross here.

        A failed fetch raises; :meth:`Registry.lookup_with` turns that into an
        absent block plus one ``notes`` sentence on the report, in one place
        for every country (D-042(b)). An entity the register lists no filings
        for returns a **present** block with ``documents: []``, never
        ``not_found`` (D-011).
        """
        from registry_mcp.registries.gb import client

        return await client.fetch_filings(id)

    async def insolvency(self, id: str) -> InsolvencyBlock:
        """Insolvency proceedings Companies House publishes against this entity
        (``registries/gb/insolvency.py``).

        The ``include=["insolvency"]`` attachment (``DECISIONS.md`` D-042):
        :meth:`Registry.lookup_with` calls this by name, so it must stay named
        exactly ``insolvency``, matching both :attr:`supported_includes` and
        :class:`~registry_mcp.core.models.CompanyReport`'s ``insolvency`` field
        (D-042(b),(g)).

        The whole history arrives in one request — this endpoint is not
        paginated and ignores both ``items_per_page`` and ``start_index``
        (confirmed live) — so nothing is truncated and D-042(j)'s truncation
        disclosure never fires here.

        **Two things a caller must not misread, both disclosed in the block's
        own fields rather than in this docstring alone.** A 404 from this
        endpoint is the *normal* answer for a solvent company and is
        byte-identical to the answer for a company number that was never
        issued, so a present block with ``cases: []`` is never evidence the
        entity exists; ``notes`` says which empty state it is. And
        ``is_liquidation`` is not a distress signal on its own: a members'
        voluntary liquidation is a *solvent* wind-up, 56 of the 1,485 live
        cases behind the lookup table were exactly that.

        **No practitioner particular crosses this seam.** Companies House
        publishes each appointed practitioner's name and postal address on
        every case; D-042(e)(2) bars relaying them, the mapper strips them
        before a model is built (``insolvency.strip_practitioners``), and
        neither :class:`~registry_mcp.core.models.InsolvencyCase` nor
        :class:`~registry_mcp.core.models.InsolvencyEvent` has a field one
        could land in.
        """
        from registry_mcp.registries.gb import client

        return await client.fetch_insolvency(id)

    def deadlines(self, report: CompanyReport, today: date) -> list[Deadline]:
        """UK filing deadlines for this entity (``registries/gb/rules.py``).

        Pure function of ``report``/``today``: the register's own published
        due dates travel on ``report.published_deadlines``
        (``DECISIONS.md`` D-018), filled by ``registries/gb/mapping.py`` at
        lookup time — nothing here touches the cache or the network.
        """
        from registry_mcp.registries.gb import rules

        result: list[Deadline] = rules.deadlines_for(report, today)
        return result

    async def aclose(self) -> None:
        """Close the shared ``httpx.AsyncClient`` (``registries/gb/client.py``).

        Overrides the ``Registry`` no-op (``DECISIONS.md`` D-014): this
        module keeps one module-level client across every request.
        """
        from registry_mcp.registries.gb import client

        await client.aclose()

    def rules_markdown(self) -> str:
        """Served as the MCP resource ``registry://rules/GB``."""
        try:
            from registry_mcp.registries.gb import rules

            markdown: str = rules.rules_markdown()
            return markdown
        except (ImportError, AttributeError):
            return (
                "# United Kingdom — Companies House\n\n"
                "Rules documentation is generated by `registries/gb/rules.py`, not yet "
                "available. See `UK_SPEC.md` for the authoritative version."
            )


register(CompaniesHouseRegistry())
