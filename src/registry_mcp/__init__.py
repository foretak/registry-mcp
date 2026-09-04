"""registry-mcp — company data for AI agents, any country.

An MCP server and REST API over national business registries. The first module
is Norway (Brønnøysundregistrene / Enhetsregisteret, lookup by
organisasjonsnummer / orgnr).

Layout (``DECISIONS.md`` D-003)::

    src/registry_mcp/core/        country-neutral models, Registry ABC, rules helpers
    src/registry_mcp/registries/  one folder per country: no/, xx/ (template)
    src/registry_mcp/api/         FastAPI REST surface (T06)
    src/registry_mcp/mcp/         FastMCP server (T07)
"""

__version__ = "0.2.0"

__all__ = ["__version__"]
