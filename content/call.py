"""Call one MCP tool on a running registry-mcp server and print the JSON.

Every JSON block in these articles was produced with this script, against a
server started as:

    REGISTRY_MCP_CACHE_DISABLED=1 uv run uvicorn registry_mcp.api.main:app --port 8091 &

(the `XX` blocks in `04-add-your-country/` add `REGISTRY_MCP_INCLUDE_STUBS=1`).

Usage:

    uv run python content/call.py <tool_name> '<json args>'

e.g. `uv run python content/call.py lookup_company '{"id": "833285602"}'`.
A tool that raises prints its `{"error": {...}}` envelope instead, which is
exactly what the agent sees.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from fastmcp import Client

URL = os.environ.get("REGISTRY_MCP_URL", "http://localhost:8091/mcp")


async def main() -> None:
    tool = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    async with Client(URL) as client:
        try:
            # `.data` re-validates structured_content through a schema-derived
            # dynamic type (`fastmcp.utilities.json_schema_type`) and returns a
            # live object, not a plain dict — not JSON-serialisable as-is on
            # current fastmcp. `.structured_content` is the exact JSON object
            # the server sent (`SomeModel.model_dump(mode="json")`), so use
            # that instead; it is what an agent actually receives on the wire.
            data = (await client.call_tool(tool, args)).structured_content
        except Exception as exc:  # the D-007 envelope arrives as the error text
            try:
                data = json.loads(str(exc))
            except json.JSONDecodeError:
                data = {"error": {"message": str(exc)}}
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
