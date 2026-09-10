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
            "source",
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


# ---------------------------------------------------------------------------
# `source` — "calls by channel" (T64)
# ---------------------------------------------------------------------------


def test_log_call_sanitises_and_stores_source(tmp_path: Path) -> None:
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)

    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="pytest/1.0",
        latency_ms=1,
        ok=True,
        source="README",
    )

    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT source FROM calls").fetchone()
    assert row == ("readme",)


def test_log_call_source_defaults_to_null(tmp_path: Path) -> None:
    db = tmp_path / "calls.sqlite3"
    log.set_sink(db)

    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609016",
        user_agent="pytest/1.0",
        latency_ms=1,
        ok=True,
    )

    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT source FROM calls").fetchone()
    assert row == (None,)


def test_sanitize_source_none_and_empty_are_none() -> None:
    assert log.sanitize_source(None) is None
    assert log.sanitize_source("") is None


def test_sanitize_source_lowercases_and_passes_valid_characters() -> None:
    assert log.sanitize_source("README") == "readme"
    assert log.sanitize_source("my-source_1") == "my-source_1"


def test_sanitize_source_strips_disallowed_characters() -> None:
    assert log.sanitize_source("Read Me!") == "readme"
    assert log.sanitize_source("dev.to! 2026") == "devto2026"


def test_sanitize_source_all_disallowed_characters_is_none() -> None:
    assert log.sanitize_source("???") is None
    assert log.sanitize_source("   ") is None


def test_sanitize_source_truncates_to_32_characters() -> None:
    assert log.sanitize_source("a" * 50) == "a" * 32


def test_sanitize_source_filters_before_truncating() -> None:
    """Order matters. Filtering the five leading `!` out first leaves exactly
    32 valid `b`s to keep, so the result is the full 32-character cap.
    Truncating the raw 37-character string to its first 32 characters
    *before* filtering would instead keep only 27 `b`s (`!!!!!` plus 27
    `b`s survive the cut, then the `!`s are stripped) — one character short
    of the cap for a reason no caller could predict from the value they
    sent."""
    raw = "!" * 5 + "b" * 32
    assert len(raw) == 37
    assert log.sanitize_source(raw) == "b" * 32


def _create_pre_t64_calls_table(db: Path) -> None:
    """A `calls` table exactly as it looked before this task added `source` —
    built with raw `sqlite3`, never `log.connect`/`log.ensure_schema`, since
    those two already carry the migration the tests below exist to prove."""
    conn = sqlite3.connect(db)
    try:
        conn.executescript(
            """
            CREATE TABLE calls (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT NOT NULL,
                surface     TEXT NOT NULL,
                operation   TEXT NOT NULL,
                country     TEXT,
                query       TEXT,
                user_agent  TEXT,
                latency_ms  INTEGER NOT NULL,
                ok          INTEGER NOT NULL,
                error_code  TEXT,
                cached      INTEGER
            );
            CREATE INDEX calls_ts ON calls(ts);
            CREATE INDEX calls_surface ON calls(surface);
            """
        )
        conn.execute(
            "INSERT INTO calls "
            "(ts, surface, operation, country, query, user_agent, latency_ms, ok) "
            "VALUES ('2026-01-01T00:00:00+00:00', 'rest', 'lookup_company', 'NO', "
            "'923609016', 'old-client/1.0', 5, 1)"
        )
        conn.commit()
    finally:
        conn.close()


def test_old_database_migrates_source_column_on_connect(tmp_path: Path) -> None:
    """The proof an old database migrates: a `calls` table with no `source`
    column at all (the shape every database predating T64 has on disk) gets
    the column added by `log.connect` — the `ALTER TABLE ... ADD COLUMN` path
    in `ensure_schema`, not the `CREATE TABLE IF NOT EXISTS` a brand-new
    database takes — with the pre-existing row left in place."""
    db = tmp_path / "old_calls.sqlite3"
    _create_pre_t64_calls_table(db)

    columns_before = {
        row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(calls)")
    }
    assert "source" not in columns_before

    log.connect(db).close()

    columns_after = {
        row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(calls)")
    }
    assert "source" in columns_after

    with sqlite3.connect(db) as conn:
        old_row = conn.execute(
            "SELECT query, source FROM calls WHERE query = '923609016'"
        ).fetchone()
    assert old_row == ("923609016", None)


def test_old_database_migrates_then_logs_a_new_source(tmp_path: Path) -> None:
    """After the same migration, `log_call` on that now-migrated database
    writes a real `source` value into the new column, alongside the
    pre-existing row the migration left untouched."""
    db = tmp_path / "old_calls.sqlite3"
    _create_pre_t64_calls_table(db)
    log.set_sink(db)

    log.log_call(
        surface=Surface.REST,
        operation="lookup_company",
        country="NO",
        query="923609017",
        user_agent="new-client/1.0",
        latency_ms=8,
        ok=True,
        source="readme",
    )

    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT query, source FROM calls ORDER BY id").fetchall()
    assert rows == [("923609016", None), ("923609017", "readme")]
