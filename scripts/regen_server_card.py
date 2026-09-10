"""Regenerate ``static/well-known/mcp/server-card.json`` from the live in-process server.

Run from the repo root::

    uv run python scripts/regen_server_card.py

Rewrites every tool entry (description, annotation title, ``inputSchema``),
``lookup_company``'s and ``company_deadlines``'s ``outputSchema`` (the two tools whose
card entry hand-pins one, per ``tests/test_mcp.py``'s two matching drift tests),
every prompt (description, arguments), and every resource (uri, name, description,
mimeType), to match what FastMCP actually serves — the same comparison
``tests/test_mcp.py``'s card tests make, so a synced card passes them and an
out-of-date one is fixed by running this rather than by hand. Formatting is
preserved (indent 2, ``ensure_ascii=False``, trailing newline); running it on a
synced card changes nothing.
"""

from __future__ import annotations

import asyncio
import json
import pathlib

from fastmcp import Client
from fastmcp.utilities.json_schema import dereference_refs
from pydantic import BaseModel

from registry_mcp.core.models import CompanyReport, DeadlineReport
from registry_mcp.mcp.server import mcp

CARD = pathlib.Path(__file__).resolve().parent.parent / "static" / "well-known" / "mcp" / "server-card.json"

#: Tools whose card entry pins a full ``outputSchema`` to one pydantic model,
#: each with its own drift test in ``tests/test_mcp.py`` — everything else's
#: schema lives only in the live server, per `DECISIONS.md` D-010's shapes.
_OUTPUT_SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "lookup_company": CompanyReport,
    "company_deadlines": DeadlineReport,
}


async def main() -> None:
    card = json.loads(CARD.read_text(encoding="utf-8"))
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
        prompts = {p.name: p for p in await client.list_prompts()}
        resources = await client.list_resources()
    for entry in card["tools"]:
        tool = tools[entry["name"]]
        entry["description"] = tool.description
        if tool.annotations is not None and "annotations" in entry:
            entry["annotations"]["title"] = tool.annotations.title
        entry["inputSchema"] = tool.input_schema
        model = _OUTPUT_SCHEMA_MODELS.get(entry["name"])
        if model is not None:
            entry["outputSchema"] = dereference_refs(model.model_json_schema())
    for entry in card["prompts"]:
        prompt = prompts[entry["name"]]
        entry["description"] = prompt.description
        entry["arguments"] = [
            {"name": a.name, "description": a.description, "required": a.required}
            for a in (prompt.arguments or [])
        ]
    card["resources"] = [
        {
            "uri": str(resource.uri),
            "name": resource.name,
            "description": resource.description,
            "mimeType": resource.mime_type,
        }
        for resource in resources
    ]
    CARD.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"server card regenerated: {len(tools)} tools, {len(prompts)} prompts, "
        f"{len(resources)} resources"
    )


if __name__ == "__main__":
    asyncio.run(main())
