"""Regenerate ``static/well-known/mcp/server-card.json`` from the live in-process server.

Run from the repo root::

    uv run python scripts/regen_server_card.py

Rewrites every tool entry (description, annotation title, ``inputSchema``) and
``lookup_company``'s ``outputSchema``, and every prompt (description, arguments),
to match what FastMCP actually serves — the same comparison ``tests/test_mcp.py``'s
two card tests make, so a synced card passes them and an out-of-date one is
fixed by running this rather than by hand. Formatting is preserved (indent 2,
``ensure_ascii=False``, trailing newline); running it on a synced card changes
nothing.
"""

from __future__ import annotations

import asyncio
import json
import pathlib

from fastmcp import Client
from fastmcp.utilities.json_schema import dereference_refs

from registry_mcp.core.models import CompanyReport
from registry_mcp.mcp.server import mcp

CARD = pathlib.Path(__file__).resolve().parent.parent / "static" / "well-known" / "mcp" / "server-card.json"


async def main() -> None:
    card = json.loads(CARD.read_text(encoding="utf-8"))
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
        prompts = {p.name: p for p in await client.list_prompts()}
    for entry in card["tools"]:
        tool = tools[entry["name"]]
        entry["description"] = tool.description
        if tool.annotations is not None and "annotations" in entry:
            entry["annotations"]["title"] = tool.annotations.title
        entry["inputSchema"] = tool.input_schema
        if entry["name"] == "lookup_company":
            entry["outputSchema"] = dereference_refs(CompanyReport.model_json_schema())
    for entry in card["prompts"]:
        prompt = prompts[entry["name"]]
        entry["description"] = prompt.description
        entry["arguments"] = [
            {"name": a.name, "description": a.description, "required": a.required}
            for a in (prompt.arguments or [])
        ]
    CARD.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"server card regenerated: {len(tools)} tools, {len(prompts)} prompts")


if __name__ == "__main__":
    asyncio.run(main())
