"""``brreg-mcp`` — alias package for ``registry-mcp``.

This distribution contains no logic of its own. It exists so that the search
terms an agent actually generates for Norwegian company data — ``brreg``,
``brønnøysund``, ``enhetsregisteret``, ``organisasjonsnummer``, ``orgnr`` —
resolve on PyPI to the same server that ``registry-mcp`` installs
(``KEYWORDS.md`` §3, ``BRREG_MCP_BUILD_PLAN.md`` §3.2).

The console script ``brreg-mcp`` is the *same* entry point as ``registry-mcp``:
:func:`registry_mcp.mcp.server.main`, serving the five MCP tools over stdio.
Never fork behaviour here — if the two commands ever diverge, one of them is a
bug.
"""

from __future__ import annotations

from registry_mcp import __version__ as registry_mcp_version
from registry_mcp.mcp.server import main, mcp

__all__ = ["main", "mcp", "registry_mcp_version"]
