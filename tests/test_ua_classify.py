"""Tests for `core/ua_classify.py` (T09).

Covers at least 12 real-world user-agent strings spanning all four labels,
plus `None` / empty-string edge cases, and checks that coding-agent rules
win over script rules when a UA string could match both (the whole reason
`RULES` is ordered).
"""

from __future__ import annotations

import pytest

from registry_mcp.core.ua_classify import classify


@pytest.mark.parametrize(
    "user_agent,expected",
    [
        # --- coding_agent ---
        ("claude-code/1.0.0 (Anthropic)", "coding_agent"),
        ("Claude-Code-CLI/2.3.1", "coding_agent"),
        ("cursor/0.42.3", "coding_agent"),
        ("openai-codex/1.0", "coding_agent"),
        ("cline-vscode-extension/3.1", "coding_agent"),
        ("windsurf/1.2.0", "coding_agent"),
        ("Continue/0.9.1 (VSCode)", "coding_agent"),
        ("GitHub-Copilot-Chat/1.0", "coding_agent"),
        ("mcp-client/0.5.0 python-httpx/0.27.0", "coding_agent"),
        ("fastmcp/2.1.0", "coding_agent"),
        ("modelcontextprotocol-inspector/1.0", "coding_agent"),
        ("stdio", "coding_agent"),
        ("Zed/0.130.0", "coding_agent"),
        ("aider/0.55.0 +https://aider.chat", "coding_agent"),
        # --- browser ---
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "browser",
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "browser",
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "browser",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "browser",
        ),
        # --- script ---
        ("curl/8.4.0", "script"),
        ("Wget/1.21.3 (linux-gnu)", "script"),
        ("python-requests/2.31.0", "script"),
        ("python-httpx/0.27.0", "script"),
        ("aiohttp/3.9.1", "script"),
        ("node-fetch/3.3.2", "script"),
        ("axios/1.6.7", "script"),
        ("Go-http-client/1.1", "script"),
        ("okhttp/4.12.0", "script"),
        ("Java/17.0.9", "script"),
        ("PostmanRuntime/7.36.0", "script"),
        ("insomnia/2023.5.8", "script"),
        # --- unknown ---
        (None, "unknown"),
        ("", "unknown"),
        ("   ", "unknown"),
        ("SomeWeirdBotThing/1.0", "unknown"),
    ],
)
def test_classify(user_agent: str | None, expected: str) -> None:
    assert classify(user_agent) == expected


def test_coding_agent_rules_win_over_script_rules() -> None:
    # A realistic case the module docstring calls out: an MCP client built on
    # httpx should still classify as coding_agent, not script, because the
    # coding-agent rules are checked first.
    assert classify("mcp-client/1.0 python-httpx/0.27.0") == "coding_agent"


def test_stdio_is_coding_agent_exactly() -> None:
    # `"stdio"` alone (how the MCP stdio transport logs its user agent) must
    # match, but it should not cause an unrelated string that merely contains
    # "stdio" as a substring to misclassify by accident of a loose pattern.
    assert classify("stdio") == "coding_agent"
