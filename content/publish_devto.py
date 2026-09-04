#!/usr/bin/env python3
"""Publish a dev.to draft by article id, or list your articles.

Usage:
    DEVTO_API_KEY=... python content/publish_devto.py list
    DEVTO_API_KEY=... python content/publish_devto.py publish <article_id>

The key lives outside the repo (Kim: ~/secrets/registry-mcp/devto-api-key.txt):
    DEVTO_API_KEY=$(cat ~/secrets/registry-mcp/devto-api-key.txt) python content/publish_devto.py publish 4575628
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from typing import Any

API = "https://dev.to/api"


def _req(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    key = os.environ.get("DEVTO_API_KEY")
    if not key:
        sys.exit("DEVTO_API_KEY is not set")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "api-key": key,
            "Content-Type": "application/json",
            "Accept": "application/vnd.forem.api-v1+json",
            "User-Agent": "registry-mcp-publish",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "list":
        for a in _req("GET", "/articles/me/all?per_page=50"):
            state = "PUBLISHED" if a["published"] else "draft"
            print(f'{a["id"]}  {state:9}  {a["title"]}\n           {a["url"]}')
        return 0
    if len(argv) == 3 and argv[1] == "publish":
        a = _req("PUT", f"/articles/{argv[2]}", {"article": {"published": True}})
        print("published:", a["url"])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
