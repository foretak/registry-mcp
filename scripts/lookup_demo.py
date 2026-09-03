#!/usr/bin/env python3
"""Manual smoke test: fetch one company and print its `CompanyReport`.

Usage:
    uv run python scripts/lookup_demo.py [orgnr]

Defaults to `923609016` (Equinor ASA). Run it twice in a row: the first call
hits the live API (`cached: false`), the second is served from the SQLite
cache (`cached: true`) — see `NORBIZ_SPEC.md` §9 / `DECISIONS.md` D-006.
"""

from __future__ import annotations

import asyncio
import sys

from registry_mcp.core.registry import get_registry
from registry_mcp.registries.no import client


async def main(orgnr: str) -> None:
    registry = get_registry("NO")
    try:
        report = await registry.lookup(orgnr)
    finally:
        await client.aclose()

    print(report.model_dump_json(indent=2))
    print(f"\ncached: {str(report.cached).lower()}")


if __name__ == "__main__":
    org_number = sys.argv[1] if len(sys.argv) > 1 else "923609016"
    asyncio.run(main(org_number))
