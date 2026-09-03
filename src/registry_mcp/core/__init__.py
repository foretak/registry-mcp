"""Country-neutral core of `registry-mcp`.

Nothing in this package may know about a specific country. Norwegian logic
lives in ``registry_mcp.registries.no`` (``DECISIONS.md`` D-001).

Modules:
    models    -- the response contract (CompanyReport, SearchHit, Deadline, RegistryError)
    registry  -- the Registry ABC and the country registration mechanism
    rules     -- country-neutral date arithmetic for deadline calculation
    log       -- call logging to SQLite (added by T08)
"""

from registry_mcp.core.models import (
    Address,
    CompanyReport,
    CompanyStatus,
    Deadline,
    DeadlineRecurrence,
    ErrorBody,
    ErrorCode,
    ErrorEnvelope,
    IndustryCode,
    RegistryError,
    SearchHit,
    SearchResult,
    Surface,
)
from registry_mcp.core.registry import (
    Registry,
    get_registry,
    list_countries,
    list_registries,
    register,
)

__all__ = [
    "Address",
    "CompanyReport",
    "CompanyStatus",
    "Deadline",
    "DeadlineRecurrence",
    "ErrorBody",
    "ErrorCode",
    "ErrorEnvelope",
    "IndustryCode",
    "Registry",
    "RegistryError",
    "SearchHit",
    "SearchResult",
    "Surface",
    "get_registry",
    "list_countries",
    "list_registries",
    "register",
]
