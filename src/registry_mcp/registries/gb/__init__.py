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
    Charge,
    ChargeBlock,
    CompanyReport,
    Deadline,
    SearchResult,
    SourceRef,
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
    supported_includes: ClassVar[frozenset[str]] = frozenset({"charges"})

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

        ``registries/gb/charges.py`` was built behind a seam, self-contained
        and blind to ``core/models.py``'s shapes on purpose (R-5 had not
        landed when it was written): its ``ChargeList``/``ChargeProvenance``
        are field-for-field the same shape as the real ``ChargeBlock``/
        ``SourceRef`` this method returns, so wiring the two together here is
        a straight copy, not a translation — verified by comparing both
        model's field names before this method was written.

        A malformed ``id`` raises ``invalid_id`` the same way :meth:`lookup`
        does; a company with no registered charges still returns a
        **present** ``ChargeBlock`` with an empty ``charges`` list, never
        ``not_found`` (D-041(h), confirmed live — ``registries/gb/charges.py``'s
        module docstring).
        """
        from registry_mcp.registries.gb import client

        block = await client.fetch_charges(id)
        return ChargeBlock(
            charges=[Charge.model_validate(c.model_dump()) for c in block.charges],
            total_count=block.total_count,
            outstanding_count=block.outstanding_count,
            satisfied_count=block.satisfied_count,
            provenance=SourceRef.model_validate(block.provenance.model_dump()),
            notes=list(block.notes),
        )

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
