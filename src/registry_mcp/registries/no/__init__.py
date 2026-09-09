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
    FinancialSummary,
    PeppolParticipant,
    SearchResult,
)
from registry_mcp.core.registry import Registry, register

__all__ = ["BrregRegistry"]


class BrregRegistry(Registry):
    """The Norwegian Central Coordinating Register for Legal Entities."""

    country: ClassVar[str] = "NO"
    supported_includes: ClassVar[frozenset[str]] = frozenset({"filings", "financials", "peppol"})
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

    async def financials(self, id: str) -> FinancialSummary:
        """Key figures from this entity's filed annual accounts (``registries/no/accounts.py``).

        The ``include=["financials"]`` attachment (``DECISIONS.md`` D-043):
        :meth:`Registry.lookup_with` calls this by name, so it must stay
        named exactly ``financials``, matching both :attr:`supported_includes`
        and :class:`~registry_mcp.core.models.CompanyReport`'s ``financials``
        field (D-042(b),(g)).

        **The same fetch as :meth:`filings`, not a second one.** Both read
        Regnskapsregisteret's one filed-accounts payload through
        ``registries/no/client.py``'s shared, single-flight
        ``_fetch_accounts_payload`` — requesting both attachments together
        costs exactly one upstream request, and their two blocks' ``provenance``
        agree in all five fields (D-043(h)). Turnover, operating result,
        profit, balance sheet and equity are carried; no ratio, indicator or
        verdict is derived from them (D-043(e)) — the register itself relays
        filings whose own totals do not always reconcile, and this block
        surfaces that as a `notes` sentence rather than hiding it behind a
        computed figure.

        Every numeric field is individually nullable, and `None` never means
        zero: this register frequently omits a line entirely (D-043(f)) and
        the caller must not confuse "not reported" with "reported as
        nothing". A failed fetch raises; :meth:`Registry.lookup_with` turns
        that into an absent block plus one ``notes`` sentence on the report,
        the same as any other attachment. An entity with no filed accounts —
        or a filed period the register published with no currency, which
        this API cannot carry at all (D-043(d)) — returns a **present**
        block with ``periods: []``, never ``not_found`` (D-011).
        """
        from registry_mcp.registries.no import client

        return await client.fetch_financials(id)

    async def peppol(self, id: str) -> PeppolParticipant:
        """Whether this entity can be reached over the Peppol e-invoicing
        network (``registries/no/peppol.py``).

        The ``include=["peppol"]`` attachment (``DECISIONS.md`` D-029(b),
        amended by D-046): :meth:`Registry.lookup_with` calls this by name,
        so it must stay named exactly ``peppol``, matching both
        :attr:`supported_includes` and :class:`~registry_mcp.core.models.
        CompanyReport`'s ``peppol`` field (D-042(b),(g)).

        **This is Norway's own declaration, not a**
        :attr:`Registry.universal_includes` **attachment** — unlike ``lei``,
        which every non-personal-identifier country gets for free from the
        base class. D-046(h) gives three reasons none of which generalise
        yet: the participant identifier needs a country's own ISO 6523 ICD
        (``0192`` is Norway's), the answer's provenance is a *different SMP
        per participant* rather than one endpoint GLEIF-style, and the
        licence sentence this block carries was earned by reading a
        Norwegian catalogue page. A future country that has read its own ICD
        and terms declares this the same way, independently.

        Two network reads behind one answer: a DNS walk through the Peppol
        SML locates the SMP that speaks for this participant (never ELMA
        assumed — the SML names a different SMP for a measured 1-in-43
        Norwegian participants), then that SMP is asked directly; the Peppol
        Directory is consulted only as a repair when neither step above
        produced an answer, and only ever raises a ``null`` to a ``true``,
        never to a ``false`` (D-046(a)). ``PeppolParticipant.registered`` is
        always populated as one of three states and
        ``PeppolParticipant.participant_id`` is always populated even when
        every network read failed, because that identifier is derivable
        offline and is the key a caller needs to ask elsewhere (D-029(c)).

        A failed fetch raises only when *both* routes failed outright, with
        nothing at all to build even a ``null`` block from;
        :meth:`Registry.lookup_with` turns that into an absent block plus one
        ``notes`` sentence on the report, the same as any other attachment
        (D-042(b)). The far more common "we could not get an authoritative
        answer" case is not this: it is a **present** block with
        ``registered: null``.
        """
        from registry_mcp.registries.no import peppol as peppol_module

        return await peppol_module.fetch_peppol(id)

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
        """Close the shared ``httpx.AsyncClient``\\ s (``registries/no/client.py``,
        T03; ``registries/no/peppol.py``, this task).

        Overrides the ``Registry`` no-op (``DECISIONS.md`` D-014): this module
        keeps one module-level client per upstream family across every
        request, so something has to close each on shutdown or the sockets
        leak. ``registries/no/peppol.py`` owns its own client, separate from
        ``client.py``'s — it talks to a different SMP host per participant
        plus the Peppol Directory, never Enhetsregisteret/Regnskapsregisteret
        — so it needs its own close call here too, in the same lazy-import
        style as the other delegates above.
        """
        from registry_mcp.registries.no import client
        from registry_mcp.registries.no import peppol as peppol_module

        await client.aclose()
        await peppol_module.aclose()

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
