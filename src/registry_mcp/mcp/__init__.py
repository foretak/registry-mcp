"""MCP surface (FastMCP). Owned by T07 — see ``tasks/T07.md``.

This package is ``registry_mcp.mcp``; ``import mcp`` inside it still resolves to
the ``mcp`` PyPI package, because Python 3 uses absolute imports. That is the
whole point of the src layout chosen in ``DECISIONS.md`` D-003.

Tools: lookup_company, search_company, company_deadlines, validate_company_id,
list_countries. Resource: ``registry://rules/{country}``. Prompt:
``explain_company``.
"""
