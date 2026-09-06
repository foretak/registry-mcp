"""Tests for `core/cache.py` — the country-neutral SQLite cache (`DECISIONS.md` D-006).

Every test points `REGISTRY_MCP_CACHE_PATH` at a fresh tmp file so tests never
share state and never touch the real `./data/cache.sqlite3`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NoReturn

import pytest

from registry_mcp.core import cache


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_PATH", str(tmp_path / "cache.sqlite3"))
    monkeypatch.delenv("REGISTRY_MCP_CACHE_DISABLED", raising=False)
    monkeypatch.delenv("REGISTRY_MCP_CACHE_TTL_SECONDS", raising=False)
    yield


def test_miss_on_empty_cache() -> None:
    assert cache.get("NO:brreg:entity:923609016") is None


def test_set_then_get_roundtrips_payload() -> None:
    cache.set("NO:brreg:entity:923609016", {"name": "EQUINOR ASA"})
    entry = cache.get("NO:brreg:entity:923609016")
    assert entry is not None
    assert entry.payload == {"name": "EQUINOR ASA"}
    assert entry.status == "ok"


def test_get_preserves_original_fetched_at() -> None:
    original = datetime.now(UTC) - timedelta(hours=1)
    cache.set("k", {"x": 1}, fetched_at=original)
    entry = cache.get("k")
    assert entry is not None
    assert entry.fetched_at == original


def test_expired_row_is_a_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_TTL_SECONDS", "1")
    stale = datetime.now(UTC) - timedelta(seconds=10)
    cache.set("k", {"x": 1}, fetched_at=stale)
    assert cache.get("k") is None


def test_ttl_override_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_TTL_SECONDS", "100000")
    old_but_within_override = datetime.now(UTC) - timedelta(hours=25)
    cache.set("k", {"x": 1}, fetched_at=old_but_within_override)
    # 25h is older than the default 24h TTL but well within the overridden one.
    assert cache.get("k") is not None


def test_not_found_status_has_short_ttl_not_overridden_by_ok_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_TTL_SECONDS", "100000")
    just_over_an_hour_ago = datetime.now(UTC) - timedelta(hours=1, minutes=5)
    cache.set("k", {}, status="not_found", fetched_at=just_over_an_hour_ago)
    # not_found TTL is a fixed 1h, unaffected by the ok-TTL override.
    assert cache.get("k") is None


def test_not_found_status_preserved() -> None:
    cache.set("k", {}, status="not_found")
    entry = cache.get("k")
    assert entry is not None
    assert entry.status == "not_found"


def test_disabled_bypasses_get_and_set(monkeypatch: pytest.MonkeyPatch) -> None:
    cache.set("k", {"x": 1})
    monkeypatch.setenv("REGISTRY_MCP_CACHE_DISABLED", "1")
    assert cache.get("k") is None
    cache.set("k2", {"y": 2})
    monkeypatch.delenv("REGISTRY_MCP_CACHE_DISABLED", raising=False)
    assert cache.get("k2") is None


def test_default_path_is_data_cache_sqlite3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REGISTRY_MCP_CACHE_PATH", raising=False)
    assert cache.cache_path() == Path("./data/cache.sqlite3")


def test_set_overwrites_existing_key() -> None:
    cache.set("k", {"v": 1})
    cache.set("k", {"v": 2})
    entry = cache.get("k")
    assert entry is not None
    assert entry.payload == {"v": 2}


def test_cache_failure_is_swallowed_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Point the cache path at a directory (not a file) so sqlite3.connect fails.
    bad_dir = tmp_path / "not_a_file"
    bad_dir.mkdir()
    monkeypatch.setenv("REGISTRY_MCP_CACHE_PATH", str(bad_dir))
    # Neither call should raise.
    cache.set("k", {"x": 1})
    assert cache.get("k") is None


def test_read_and_write_failure_logs_only_the_key_prefix(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Review fix 3(b) (T30, `REVIEW.md` "T26f + T28 + T29"): the SE cache key is
    `SE:bolagsverket:entity:prod:<identitetsbeteckning>` (`registries/se/client.py`),
    so a cache I/O failure that logs the raw key puts a personnummer in the
    application log — D-040(c)'s "nothing, not a hash" applies to every log line,
    not just `top_queries`. Forcing `_connect` to raise (both on read and on write)
    must log only the key's prefix — everything up to and including the last `:`
    — never the identifier that follows it."""

    def _boom() -> NoReturn:
        raise OSError("disk full")

    monkeypatch.setattr(cache, "_connect", _boom)
    key = "SE:bolagsverket:entity:test:194009272719"

    with caplog.at_level(logging.DEBUG):
        assert cache.get(key) is None
        cache.set(key, {"x": 1})

    assert caplog.records, "nothing was logged"
    for record in caplog.records:
        assert "194009272719" not in record.getMessage()
    assert any("SE:bolagsverket:entity:test:" in record.getMessage() for record in caplog.records)
