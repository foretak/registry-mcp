#!/usr/bin/env python3
"""Manual smoke test: fetch one company and print its `CompanyReport`.

Usage:
    uv run python scripts/lookup_demo.py [--country CC] [id]

Defaults to `--country NO 923609016` (Equinor ASA). Run it twice in a row:
the first call hits the live API (`cached: false`), the second is served
from the SQLite cache (`cached: true`) — see `NORBIZ_SPEC.md` §9 /
`DECISIONS.md` D-006.

For `--country GB`, set `COMPANIES_HOUSE_API_KEY` first (a free key is at
https://developer.company-information.service.gov.uk/get-started), e.g.:

    COMPANIES_HOUSE_API_KEY=... uv run python scripts/lookup_demo.py --country GB 00445790
"""

from __future__ import annotations

import argparse
import asyncio

from registry_mcp.core.registry import get_registry


async def main(country: str, id: str) -> None:
    registry = get_registry(country)
    try:
        report = await registry.lookup(id)
    finally:
        await registry.aclose()

    print(report.model_dump_json(indent=2))
    print(f"\ncached: {str(report.cached).lower()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--country", default="NO", help="ISO-3166-1 alpha-2 country code (default: NO)"
    )
    parser.add_argument(
        "id", nargs="?", default="923609016", help="National identifier to look up"
    )
    args = parser.parse_args()

    # GB's default 923609016 would be a Norwegian orgnr; use the module's own
    # id_example instead when the caller didn't override --country's default id.
    identifier = args.id
    if args.country.upper() != "NO" and identifier == "923609016":
        identifier = get_registry(args.country).id_example

    asyncio.run(main(args.country, identifier))
