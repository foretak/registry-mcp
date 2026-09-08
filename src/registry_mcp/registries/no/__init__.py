"""Norway — Brønnøysundregistrene / Enhetsregisteret.

``validate_id`` and ``deadlines`` delegate to ``registries/no/rules.py`` (T02,
MOD11 / org-form table / status derivation / the six deadlines). ``lookup``
and ``search`` delegate to ``registries/no/client.py`` (T03, HTTP + cache +
``registries/no/mapping.py``).

Every delegate is imported lazily, inside the method body, rather than at
module top level. T02's ``rules.py`` and T03's ``client.py`` are built in
parallel by different agents in this session; importing either eagerly here
would make *this* module — which ``registries/__init__.py`` imports
unconditionally at package load — fail to import whenever the other task's
file is momentarily absent or mid-edit. A lazy import only pays that risk at
call time, for the one method that actually needs it.
"""

from __future__ import annotations

from datetime import date
from typing import ClassVar

from registry_mcp.core.models import (
    CompanyReport,
    Deadline,
    FilingHistory,
    SearchResult,
)
from registry_mcp.core.registry import Registry, register

__all__ = ["BrregRegistry"]


class BrregRegistry(Registry):
    """The Norwegian Central Coordinating Register for Legal Entities."""

    country: ClassVar[str] = "NO"
    supported_includes: ClassVar[frozenset[str]] = frozenset({"filings"})
    registry: ClassVar[str] = "brreg"
    name: ClassVar[str] = "Enhetsregisteret (Brønnøysundregistrene)"
    id_scheme: ClassVar[str] = "organisasjonsnummer"
    id_example: ClassVar[str] = "923609016"
    id_description: ClassVar[str] = (
        "A Norwegian organisasjonsnummer (orgnr): nine digits, the ninth a MOD11 "
        "check digit. Written '923 609 016' or '923609016'; a VAT number adds 'MVA'."
    )
    source_url: ClassVar[str] = "https://data.brreg.no/enhetsregisteret/api"
    license: ClassVar[str] = "NLOD 2.0"
    is_stub: ClassVar[bool] = False

    def validate_id(self, id: str) -> str:
        """Normalise and MOD11-check an organisasjonsnummer (``registries/no/rules.py``, T02)."""
        from registry_mcp.registries.no import rules

        result: str = rules.validate_orgnr(id)
        return result

    async def lookup(self, id: str) -> CompanyReport:
        """Fetch one entity from Enhetsregisteret (``registries/no/client.py``, T03)."""
        from registry_mcp.registries.no import client

        return await client.lookup(id)

    async def search(self, name: str, limit: int = 10) -> SearchResult:
        """Search Enhetsregisteret by name (``registries/no/client.py``, T03)."""
        from registry_mcp.registries.no import client

        return await client.search(name, limit)

    async def filings(self, id: str) -> FilingHistory:
        """The annual accounts this entity has filed with Regnskapsregisteret (``registries/no/accounts.py``).

        The ``include=["filings"]`` attachment (``DECISIONS.md`` D-041(d),
        D-042): :meth:`Registry.lookup_with` calls this by name, so it must
        stay named exactly ``filings``, matching both
        :attr:`supported_includes` and :class:`~registry_mcp.core.models.
        CompanyReport`'s ``filings`` field (D-042(b),(g)).

        Regnskapsregisteret publishes **filed annual accounts only**, not a
        general filing history, and no count of its own, so ``total_count``
        is ``None`` (D-011). Open and keyless — unlike Sweden's equivalent,
        this needs no credential at all. Brønnøysundregistrene labels the
        dataset a preview with no guarantee of quality of service, and the
        block says so in its own ``notes`` on every call. It is the one
        country that fills ``period_start``, because ``regnskapsperiode``
        publishes both ends of the period.

        ``registries/no/accounts.py`` builds the canonical ``FilingHistory``
        directly — all three countries converged on the same shape
        independently (D-044(a)), and there is no seam left to cross here.

        A failed fetch raises; :meth:`Registry.lookup_with` turns that into an
        absent block plus one ``notes`` sentence on the report, in one place
        for every country (D-042(b)). An entity the register lists no filings
        for returns a **present** block with ``documents: []``, never
        ``not_found`` (D-011).
        """
        from registry_mcp.registries.no import client

        return await client.fetch_accounts(id)

    def deadlines(self, report: CompanyReport, today: date) -> list[Deadline]:
        """Norwegian filing deadlines for this entity (``registries/no/rules.py``, T02)."""
        from registry_mcp.registries.no import rules

        result: list[Deadline] = rules.deadlines(report, today)
        return result

    def format_id(self, id: str) -> str:
        """``"923609016"`` -> ``"923 609 016"`` (``registries/no/mapping.py``, T03)."""
        from registry_mcp.registries.no import mapping

        result: str = mapping.format_orgnr(id)
        return result

    async def aclose(self) -> None:
        """Close the shared ``httpx.AsyncClient`` (``registries/no/client.py``, T03).

        Overrides the ``Registry`` no-op (``DECISIONS.md`` D-014): this module
        keeps one module-level client across every request, so something has
        to close it on shutdown or the sockets leak. Delegates to
        ``client.aclose()`` in the same lazy-import style as the other
        delegates above.
        """
        from registry_mcp.registries.no import client

        await client.aclose()

    def rules_markdown(self) -> str:
        """Served as the MCP resource ``registry://rules/NO``. Filled in by T02."""
        try:
            from registry_mcp.registries.no import rules

            markdown: str = rules.rules_markdown()
            return markdown
        except (ImportError, AttributeError):
            return (
                "# Norway — Brønnøysundregistrene\n\n"
                "Rules documentation is generated by `registries/no/rules.py` (T02), "
                "not yet available. See `NORBIZ_SPEC.md` for the authoritative version."
            )


register(BrregRegistry())
