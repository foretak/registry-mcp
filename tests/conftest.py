"""Shared pytest fixtures.

Fixtures here are country-neutral. Norwegian fixtures (sample Enhetsregisteret
JSON, respx mocks) belong in ``tests/no/conftest.py``, added by T02/T03.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest

from registry_mcp.core.models import CompanyReport, CompanyStatus
from registry_mcp.core.registry import Registry, get_registry


@pytest.fixture
def today() -> date:
    """A fixed 'today' so deadline tests never depend on the real clock.

    2026-03-15 is a Sunday, which makes it useful for roll-forward tests too.
    """
    return date(2026, 3, 15)


@pytest.fixture
def brreg() -> Registry:
    """The registered Norwegian registry instance."""
    return get_registry("NO")


@pytest.fixture
def example_registry() -> Registry:
    """The XX template registry (hidden from the public country list by default)."""
    return get_registry("XX", include_stubs=True)


@pytest.fixture
def include_stubs(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make stub registries visible to code that does not pass ``include_stubs``."""
    monkeypatch.setenv("REGISTRY_MCP_INCLUDE_STUBS", "1")
    yield


@pytest.fixture
def sample_report() -> CompanyReport:
    """A minimal, valid Norwegian report for tests that need a report but no network."""
    return CompanyReport(
        country="NO",
        registry="brreg",
        id="923609016",
        id_formatted="923 609 016",
        id_scheme="organisasjonsnummer",
        name="EQUINOR ASA",
        legal_form_code="ASA",
        legal_form="Public limited company",
        legal_form_local="Allmennaksjeselskap",
        limited_liability=True,
        has_board_duty=True,
        has_annual_accounts_duty=True,
        status=CompanyStatus.ACTIVE,
        is_active=True,
        registered_at=date(1995, 3, 12),
        founded_at=date(1972, 9, 18),
        vat_registered=True,
        in_business_register=True,
        confidence=1.0,
        confidence_basis="exact identifier lookup",
        cached=False,
        fetched_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        source="Enhetsregisteret (brreg.no)",
        source_url="https://data.brreg.no/enhetsregisteret/api/enheter/923609016",
        license="NLOD 2.0",
    )
