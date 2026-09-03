"""XX — Example country. **The template for adding a real one.**

This folder exists to prove the claim in ``DECISIONS.md`` D-001: a new country
is one folder under ``registries/`` plus one import line in
``registries/__init__.py``. Nothing in ``core/``, ``api/`` or ``mcp/`` changes.

To add a real country, copy this folder to ``registries/<cc>/``, then:

1. Set ``country`` to the ISO-3166-1 alpha-2 code and ``registry`` to the
   register's slug. Set ``is_stub = False``.
2. Implement ``validate_id`` — normalise, then check the national checksum.
   Raise ``RegistryError(ErrorCode.INVALID_ID, ..., hint=...)`` on failure.
3. Implement ``lookup`` and ``search`` in a ``client.py`` next to this file.
   Reuse the 5 s timeout / one retry / descriptive User-Agent contract from
   ``NORBIZ_SPEC.md`` §6 and the 24 h SQLite cache from D-006.
4. Implement ``deadlines`` in a ``rules.py`` next to this file, importing the
   date helpers from ``core.rules.common``. Keep it pure: ``today`` is the only
   clock.
5. Add ``from registry_mcp.registries import <cc> as <cc>`` to
   ``registries/__init__.py``.
6. Write the country's own numbered rules test list, in the style of
   ``NORBIZ_SPEC.md`` §5, and tests for it.

``is_stub = True`` keeps XX out of ``list_countries()`` and ``/v1/countries``
by default; set ``REGISTRY_MCP_INCLUDE_STUBS=1`` (or pass
``include_stubs=True``) to see it.
"""

from __future__ import annotations

from datetime import date
from typing import ClassVar

from registry_mcp.core.models import (
    CompanyReport,
    Deadline,
    ErrorCode,
    RegistryError,
    SearchResult,
)
from registry_mcp.core.registry import Registry, register

__all__ = ["ExampleRegistry"]


class ExampleRegistry(Registry):
    """A registry module that does nothing, so the wiring can be tested."""

    country: ClassVar[str] = "XX"
    registry: ClassVar[str] = "example"
    name: ClassVar[str] = "Example national business register"
    id_scheme: ClassVar[str] = "example_number"
    id_example: ClassVar[str] = "12345678"
    id_description: ClassVar[str] = "Eight digits, no checksum. Not a real identifier scheme."
    source_url: ClassVar[str] = "https://example.invalid/api"
    license: ClassVar[str] = "CC0-1.0"
    is_stub: ClassVar[bool] = True

    def _todo(self, what: str) -> RegistryError:
        return RegistryError(
            ErrorCode.NOT_IMPLEMENTED,
            f"{what} is not implemented: XX is the example template, not a real registry.",
            hint="Call list_countries to see the countries that are actually supported.",
            country=self.country,
            registry=self.registry,
        )

    def validate_id(self, id: str) -> str:
        """Accept eight digits after stripping separators. No checksum."""
        normalised = "".join(ch for ch in id if ch.isalnum()).upper()
        if len(normalised) != 8 or not normalised.isdigit():
            raise RegistryError(
                ErrorCode.INVALID_ID,
                f"{id!r} is not a valid example_number.",
                hint="An XX example_number is exactly eight digits, e.g. '12345678'.",
                country=self.country,
                registry=self.registry,
            )
        return normalised

    async def lookup(self, id: str) -> CompanyReport:
        """Always raises: the example registry has no data behind it."""
        raise self._todo("lookup")

    async def search(self, name: str, limit: int = 10) -> SearchResult:
        """Always raises: the example registry has no data behind it."""
        raise self._todo("search")

    def deadlines(self, report: CompanyReport, today: date) -> list[Deadline]:
        """No obligations exist in the example country."""
        return []

    def rules_markdown(self) -> str:
        return (
            "# XX — Example country\n\n"
            "Template module. Copy `registries/xx/` to add a real country; see the "
            "module docstring for the six steps."
        )


register(ExampleRegistry())
