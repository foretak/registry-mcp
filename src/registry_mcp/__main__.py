"""Run the MCP server over stdio: ``python -m registry_mcp``.

Equivalent to the ``registry-mcp`` console script (``pyproject.toml``); both
call :func:`registry_mcp.mcp.server.main`.
"""

from __future__ import annotations

from registry_mcp.mcp.server import main

if __name__ == "__main__":
    main()
