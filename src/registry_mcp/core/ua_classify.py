"""Classify a `User-Agent` string for the T09 stats dashboard.

Pure, dependency-free, and deliberately dumb: one ordered list of
`(pattern, label)` pairs, checked top to bottom, first match wins. Adding a
new coding agent (or any other client) to the dashboard's classifier is a
one-line addition to `RULES` — no other code in this module should need to
change.

Order matters. Some coding-agent user agents embed an HTTP client's name
(e.g. Claude Code's MCP client may report a `python-httpx`-derived string),
so every `coding_agent` rule is checked before any `script` rule. `browser`
is checked last among the "real" categories since `Mozilla/5.0` appears as a
compatibility token in some non-browser user agents too, but nothing we
special-case here collides with it before that point.
"""

from __future__ import annotations

import re
from typing import Literal

__all__ = ["RULES", "Label", "classify"]

Label = Literal["coding_agent", "browser", "script", "unknown"]

# fmt: off
RULES: list[tuple[re.Pattern[str], Label]] = [
    # --- coding agents / MCP clients (checked first: see module docstring) ---
    (re.compile(r"claude-code", re.IGNORECASE), "coding_agent"),
    (re.compile(r"claude[\s-]?cli", re.IGNORECASE), "coding_agent"),
    (re.compile(r"anthropic", re.IGNORECASE), "coding_agent"),
    (re.compile(r"cursor", re.IGNORECASE), "coding_agent"),
    (re.compile(r"codex", re.IGNORECASE), "coding_agent"),
    (re.compile(r"cline", re.IGNORECASE), "coding_agent"),
    (re.compile(r"windsurf", re.IGNORECASE), "coding_agent"),
    (re.compile(r"continue", re.IGNORECASE), "coding_agent"),
    (re.compile(r"copilot", re.IGNORECASE), "coding_agent"),
    (re.compile(r"mcp-client", re.IGNORECASE), "coding_agent"),
    (re.compile(r"modelcontextprotocol", re.IGNORECASE), "coding_agent"),
    (re.compile(r"fastmcp", re.IGNORECASE), "coding_agent"),
    (re.compile(r"\bmcp\b", re.IGNORECASE), "coding_agent"),
    (re.compile(r"^stdio$", re.IGNORECASE), "coding_agent"),
    (re.compile(r"zed", re.IGNORECASE), "coding_agent"),
    (re.compile(r"aider", re.IGNORECASE), "coding_agent"),
    # --- scripts / HTTP client libraries ---
    (re.compile(r"\bcurl\b", re.IGNORECASE), "script"),
    (re.compile(r"\bwget\b", re.IGNORECASE), "script"),
    (re.compile(r"python-requests", re.IGNORECASE), "script"),
    (re.compile(r"python-httpx", re.IGNORECASE), "script"),
    (re.compile(r"\bhttpx\b", re.IGNORECASE), "script"),
    (re.compile(r"\baiohttp\b", re.IGNORECASE), "script"),
    (re.compile(r"node-fetch", re.IGNORECASE), "script"),
    (re.compile(r"\bundici\b", re.IGNORECASE), "script"),
    (re.compile(r"\baxios\b", re.IGNORECASE), "script"),
    (re.compile(r"go-http-client", re.IGNORECASE), "script"),
    (re.compile(r"okhttp", re.IGNORECASE), "script"),
    (re.compile(r"\bjava\b", re.IGNORECASE), "script"),
    (re.compile(r"postmanruntime", re.IGNORECASE), "script"),
    (re.compile(r"insomnia", re.IGNORECASE), "script"),
    # --- browsers ---
    (re.compile(r"mozilla", re.IGNORECASE), "browser"),
    (re.compile(r"chrome", re.IGNORECASE), "browser"),
    (re.compile(r"safari", re.IGNORECASE), "browser"),
    (re.compile(r"firefox", re.IGNORECASE), "browser"),
    (re.compile(r"\bedge\b|edg/", re.IGNORECASE), "browser"),
]
# fmt: on


def classify(user_agent: str | None) -> Label:
    """Classify ``user_agent`` into one of `Label`'s four buckets.

    ``None`` or an empty/whitespace-only string is ``"unknown"``. Otherwise
    the first matching pattern in `RULES` (checked in order) decides; no
    match is also ``"unknown"``.
    """
    if not user_agent or not user_agent.strip():
        return "unknown"
    for pattern, label in RULES:
        if pattern.search(user_agent):
            return label
    return "unknown"
