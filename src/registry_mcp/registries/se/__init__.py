"""Sweden — Bolagsverket ("värdefulla datamängder"), with SCB as a second
data producer inside the same payload (§1.9).

``validate_id``, ``format_id``, ``id_caveat`` and ``deadlines`` delegate to
``registries/se/rules.py`` (identitetsbeteckning shape validation, legal-form
table, status derivation, the two filing deadlines). ``lookup`` and
``search`` delegate to ``registries/se/client.py`` (OAuth 2 client
credentials + cache + ``registries/se/mapping.py``).

Every delegate is imported lazily, inside the method body, matching
``registries/no/__init__.py``'s and ``registries/gb/__init__.py``'s
convention: this module is imported unconditionally at package load
(``registries/__init__.py``), so a missing ``BOLAGSVERKET_CLIENT_ID``/
``BOLAGSVERKET_CLIENT_SECRET`` must never break ``import registry_mcp.registries``
itself (``SWEDEN_SPEC.md`` §1.2, D-037).

See ``SWEDEN_SPEC.md`` §0 for three findings this module cannot fix from
inside its own folder (a Swedish sole trader's identifier is a personnummer
and ``core/log.py`` stores it; ``core/registry.py``'s own docstring example
is an invalid organisationsnummer; ``search_company`` has no way to say in
advance that it cannot answer for Sweden) — none of them block this module,
and none of them is addressed here.
"""

from __future__ import annotations

from datetime import date
from typing import ClassVar

from registry_mcp.core.models import CompanyReport, Deadline, SearchResult
from registry_mcp.core.registry import Registry, register

__all__ = ["BolagsverketRegistry"]


class BolagsverketRegistry(Registry):
    """The Swedish Companies Registration Office, with SCB as a second data
    producer inside the same payload (§1.9) — one registry slug either way,
    because ``registry`` is a routing key, not a provenance record."""

    country: ClassVar[str] = "SE"
    registry: ClassVar[str] = "bolagsverket"
    name: ClassVar[str] = "Bolagsverket (Sweden)"
    id_scheme: ClassVar[str] = "organisationsnummer"
    id_example: ClassVar[str] = "5560160680"
    id_description: ClassVar[str] = (
        "A Swedish organisationsnummer: ten digits, written 556016-0680, with a check "
        "digit. A sole trader is looked up by a twelve-digit personnummer instead "
        "(YYYYMMDDNNNN), and one such number can carry several registered businesses."
    )
    source_url: ClassVar[str] = "https://gw.api.bolagsverket.se/vardefulla-datamangder/v1"
    license: ClassVar[str] = (
        "Free re-use (Bolagsverket/SCB high-value datasets, EU Open Data Directive) — "
        "the publisher names no licence"
    )
    is_stub: ClassVar[bool] = False
    requires_api_key: ClassVar[bool] = True
    id_may_be_personal: ClassVar[bool] = True
    api_key_env: ClassVar[str] = "BOLAGSVERKET_CLIENT_ID"

    def validate_id(self, id: str) -> str:
        """Normalise and shape-check an identitetsbeteckning
        (``registries/se/rules.py``, §5.1). No check digit is enforced
        locally (D-032)."""
        from registry_mcp.registries.se import rules

        result: str = rules.validate_id(id)
        return result

    def format_id(self, id: str) -> str | None:
        """``"5560160680"`` -> ``"556016-0680"`` (``registries/se/rules.py``, §5.1.4)."""
        from registry_mcp.registries.se import rules

        return rules.format_id(id)

    def id_caveat(self, id: str) -> str | None:
        """The modulus-10 caveat on an already-valid identifier
        (``registries/se/rules.py``, §5.1.5, D-021)."""
        from registry_mcp.registries.se import rules

        return rules.id_caveat(id)

    async def lookup(self, id: str) -> CompanyReport:
        """Fetch one entity from Bolagsverket (``registries/se/client.py``)."""
        from registry_mcp.registries.se import client

        return await client.lookup(id)

    async def search(self, name: str, limit: int = 10) -> SearchResult:
        """Always raises ``not_implemented``: Bolagsverket's free API cannot
        search by name (``registries/se/client.py``, §4)."""
        from registry_mcp.registries.se import client

        return await client.search(name, limit)

    def deadlines(self, report: CompanyReport, today: date) -> list[Deadline]:
        """Swedish filing deadlines for this entity (``registries/se/rules.py``, §5.4).

        Pure function of ``report``/``today``: Bolagsverket publishes no
        per-company due date, so ``report.published_deadlines`` is always
        empty and every deadline here is computed from ``legal_form_code``
        and ``status`` alone.
        """
        from registry_mcp.registries.se import rules

        result: list[Deadline] = rules.deadlines_for(report, today)
        return result

    async def aclose(self) -> None:
        """Close the shared ``httpx.AsyncClient`` and clear the cached bearer
        token (``registries/se/client.py``, §6.1).

        Overrides the ``Registry`` no-op (``DECISIONS.md`` D-014): this
        module keeps a shared client *and* a cached bearer token, both of
        which must not survive shutdown.
        """
        from registry_mcp.registries.se import client

        await client.aclose()

    def rules_markdown(self) -> str:
        """Served as the MCP resource ``registry://rules/SE``."""
        try:
            from registry_mcp.registries.se import rules

            markdown: str = rules.rules_markdown()
            return markdown
        except (ImportError, AttributeError):
            return (
                "# Sweden — Bolagsverket\n\n"
                "Rules documentation is generated by `registries/se/rules.py`, not yet "
                "available. See `SWEDEN_SPEC.md` for the authoritative version."
            )


register(BolagsverketRegistry())
