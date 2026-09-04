"""Validate then enrich a column of organisasjonsnummer, via the MCP tools.

    uv run python content/03-enrich-spreadsheet/enrich.py \
        content/03-enrich-spreadsheet/suppliers.csv \
        content/03-enrich-spreadsheet/suppliers-enriched.csv

Reads `suppliers.csv`, calls `validate_company_id` on every row (free, no
network), and `lookup_company` only on the rows that survive. Writes the
enriched CSV. Against a server started as:

    REGISTRY_MCP_CACHE_DISABLED=1 uv run uvicorn registry_mcp.api.main:app --port 8091 &
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import sys

from fastmcp import Client

URL = os.environ.get("REGISTRY_MCP_URL", "http://localhost:8091/mcp")

COLUMNS = [
    "org_nr",
    "supplier_name",
    "valid",
    "normalized",
    "name",
    "legal_form",
    "status",
    "vat_registered",
    "vat_number",
    "employees",
    "city",
    "problem",
]


async def main(src: str, dst: str) -> None:
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    out: list[dict[str, object]] = []

    async with Client(URL) as client:
        for row in rows:
            raw = row["org_nr"]
            rec: dict[str, object] = {
                "org_nr": raw,
                "supplier_name": row["supplier_name"],
                "problem": "",
            }

            check = (await client.call_tool("validate_company_id", {"id": raw})).data
            rec["valid"] = check["valid"]
            rec["normalized"] = check["normalized"] or ""
            if not check["valid"]:
                rec["problem"] = check["reason"]
                out.append(rec)
                continue

            try:
                r = (await client.call_tool("lookup_company", {"id": check["normalized"]})).data
            except Exception as exc:
                err = json.loads(str(exc))["error"]
                rec["problem"] = f"{err['code']}: {err['message']}"
                out.append(rec)
                continue

            rec.update(
                name=r["name"],
                legal_form=r["legal_form"],
                status=r["status"],
                vat_registered=r["vat_registered"],
                vat_number=r["vat_number"] or "",
                employees="" if r["employees"] is None else r["employees"],
                city=r["business_address"]["city"] if r["business_address"] else "",
            )
            if not r["vat_registered"]:
                rec["problem"] = "not VAT-registered — do not accept MVA on an invoice"
            out.append(rec)

    with open(dst, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for rec in out:
            writer.writerow(rec)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
