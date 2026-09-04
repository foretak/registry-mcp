"""Tests for `core/log.py` — usage logging (`NORBIZ_SPEC.md` §11, T08).

Every test points logging at a fresh tmp path via `log.set_sink(...)` so
tests never share state and never touch the real cache/log file. `set_sink`
is reset to `None` after every test.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from registry_mcp.core import log
from registry_mcp.core.models import Surface


@pytest.fixture(autouse=True)
def _reset_sink() -> Iterator[None]:
    yield
    log.set_sink(None)


def test_log_path_defaults_to_cache_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REGISTRY_MCP_LOG_PATH", raising=False)
    monkeypatch.setenv("REGISTRY_MCP_CACHE_PATH", "/tmp/some/cache.sqlite3")
    assert log.log_path() == Path("/tmp/some/cache.sqlite3")


def test_log_path_env_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_PATH", "/tmp/some/cache.sqlite3")
    monkeypatch.setenv("REGISTRY_MCP_LOG_PATH", "/tmp/some/calls.sqlite3")
    assert log.log_path() == Path("/tmp/some/calls.sqlite3")


def test_set_sink_overrides_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("REGISTRY_MCP_LOG_PATH", "/tmp/should-not-be-used.sqlite3")
    sink = tmp_path / "calls.sqlite3"
    log.set_sink(sink)
    assert log.log_path() == sink


def test_log_call_creates_calls_table(tmp_path: Path) -> None:
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)

    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="pytest/1.0",
        latency_ms=12,
        ok=True,
    )

    with sqlite3.connect(db) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "calls" in tables
        columns = {row[1] for row in conn.execute("PRAGMA table_info(calls)")}
        assert columns == {
            "id",
            "ts",
            "surface",
            "operation",
            "country",
            "query",
            "user_agent",
            "latency_ms",
            "ok",
            "error_code",
            "cached",
        }


def test_log_call_writes_expected_row(tmp_path: Path) -> None:
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)

    log.log_call(
        surface=Surface.MCP,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="stdio",
        latency_ms=42,
        ok=False,
        error_code="not_found",
        cached=True,
    )

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT surface, operation, country, query, user_agent, latency_ms, ok, "
            "error_code, cached FROM calls"
        ).fetchone()
    assert row == ("mcp", "lookup_company", "NO", "923609016", "stdio", 42, 0, "not_found", 1)


def test_log_call_never_raises_on_unwritable_path(tmp_path: Path) -> None:
    # Point the "file" at a directory: sqlite3.connect() cannot open a
    # directory as a database, so this reliably fails inside `log.connect()`.
    not_a_file = tmp_path / "actually_a_directory"
    not_a_file.mkdir()
    log.set_sink(not_a_file)

    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="pytest/1.0",
        latency_ms=1,
        ok=True,
    )
    # No exception raised is the assertion; nothing else to check.


def test_log_call_never_raises_when_parent_is_unwritable(tmp_path: Path) -> None:
    parent = tmp_path / "readonly"
    parent.mkdir()
    parent.chmod(0o500)
    try:
        log.set_sink(parent / "nested" / "calls.sqlite3")
        log.log_call(
            surface=Surface.REST,
            operation="lookup_company",
            country="NO",
            query="923609016",
            user_agent="pytest/1.0",
            latency_ms=1,
            ok=True,
        )
    finally:
        parent.chmod(0o700)
