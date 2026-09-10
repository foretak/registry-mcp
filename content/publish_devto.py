#!/usr/bin/env python3
"""Create a dev.to draft from a markdown file, publish a draft by id, or list.

Usage:
    DEVTO_API_KEY=... python content/publish_devto.py list
    DEVTO_API_KEY=... python content/publish_devto.py create <path/to/devto.md>
    DEVTO_API_KEY=... python content/publish_devto.py update <article_id> <path>
    DEVTO_API_KEY=... python content/publish_devto.py publish <article_id>

`create` and `update` post the file verbatim as `body_markdown`. dev.to reads
the title, tags and `published:` flag out of the file's own front matter, and
**front matter wins over the API field** — so `publish <id>` alone cannot lift
a file whose front matter still says `published: false`. Set `published: true`
in the file and `update` it. `publish` remains correct for a draft created
without front matter (articles 01-05 were).

The key lives outside the repo (Kim: ~/secrets/registry-mcp/devto-api-key.txt):
    DEVTO_API_KEY=$(cat ~/secrets/registry-mcp/devto-api-key.txt) python content/publish_devto.py publish 4575628
"""

from __future__ import annotations

import json
import os
import pathlib
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
    if len(argv) == 3 and argv[1] == "create":
        body = pathlib.Path(argv[2]).read_text(encoding="utf-8")
        a = _req("POST", "/articles", {"article": {"body_markdown": body}})
        # The create response omits `published`; `list` is where you confirm state.
        print(f'created {a["id"]}: {a["url"]}')
        return 0
    if len(argv) == 4 and argv[1] == "update":
        body = pathlib.Path(argv[3]).read_text(encoding="utf-8")
        a = _req("PUT", f"/articles/{argv[2]}", {"article": {"body_markdown": body}})
        print("updated:", a["url"])
        return 0
    if len(argv) == 3 and argv[1] == "publish":
        a = _req("PUT", f"/articles/{argv[2]}", {"article": {"published": True}})
        print("published:", a["url"])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
