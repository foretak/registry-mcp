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


# ---------------------------------------------------------------------------
# The per-kind TTL table (`DECISIONS.md` D-026(c), D-028(2), D-041(h),
# D-042(j), amended by D-045(e)): `_ttl_seconds` derives the kind from the
# cache key's own third `:`-separated segment rather than a new argument, so
# no existing caller migrates. `lei` is the only declared kind so far.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "expected_kind"),
    [
        ("GB:companies-house:charges:00445790", "charges"),
        ("GB:companies-house:filings:00445790", "filings"),
        ("GB:companies-house:insolvency:00445790", "insolvency"),
        ("SE:bolagsverket:filings:prod:5560160680", "filings"),
        ("NO:brreg:filings:923609016", "filings"),
        ("NO:brreg:lei:923609016", "lei"),
    ],
)
def test_kind_from_key_reads_the_third_segment(key: str, expected_kind: str) -> None:
    assert cache._kind_from_key(key) == expected_kind


@pytest.mark.parametrize("key", ["", "k", "only:two"])
def test_kind_from_key_defensive_on_fewer_than_three_segments(key: str) -> None:
    """A key with fewer than three segments (should not happen for a real
    registry key) yields no kind, which is exactly what makes it fall
    through `_TTL_BY_KIND` untouched."""
    assert cache._kind_from_key(key) is None


def test_lei_ok_ttl_is_seven_days() -> None:
    """D-026(c), unamended by D-045(e): an LEI renews annually, so seven days
    keeps a courtesy load off a free service."""
    assert cache._ttl_seconds("ok", "NO:brreg:lei:923609016") == 7 * 24 * 60 * 60


def test_lei_empty_ttl_is_24h_not_the_old_1h() -> None:
    """The asymmetry is preserved but widened (D-045(e)): nothing statutory,
    time-critical or credit-bearing turns on an entity acquiring an LEI, so a
    'no LEI' answer is good for 24 hours, not D-006's usual 1 hour."""
    assert cache._ttl_seconds("not_found", "GB:companies-house:lei:00445790") == 24 * 60 * 60


@pytest.mark.parametrize(
    "key",
    [
        "GB:companies-house:charges:00445790",
        "GB:companies-house:filings:00445790",
        "GB:companies-house:insolvency:00445790",
        "SE:bolagsverket:filings:prod:5560160680",
        "NO:brreg:filings:923609016",
    ],
)
def test_the_five_status_not_found_stand_ins_fall_through_unchanged(key: str) -> None:
    """None of the five sites that fake a per-kind TTL with `status="not_found"`
    (`registries/gb/client.py` x3, `se/client.py`, `no/client.py`) need to
    migrate: their kinds (`charges`, `filings`, `insolvency`) are absent from
    `_TTL_BY_KIND`, so `_ttl_seconds` falls through to exactly today's two
    numbers, byte for byte (D-045(e))."""
    assert cache._ttl_seconds("ok", key) == cache._DEFAULT_OK_TTL_SECONDS
    assert cache._ttl_seconds("not_found", key) == cache._NOT_FOUND_TTL_SECONDS


def test_env_override_moves_an_undeclared_kinds_ok_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTRY_MCP_CACHE_TTL_SECONDS", "100000")
    assert cache._ttl_seconds("ok", "GB:companies-house:charges:00445790") == 100000


def test_env_override_does_not_move_lei_ok_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """A declared kind ignores `REGISTRY_MCP_CACHE_TTL_SECONDS` entirely
    (D-028(2)'s clamp, arriving early): an operator tuning cache performance
    must not be able to silently move a declared kind's TTL, the way they
    still can for an undeclared one."""
    monkeypatch.setenv("REGISTRY_MCP_CACHE_TTL_SECONDS", "60")
    assert cache._ttl_seconds("ok", "NO:brreg:lei:923609016") == 7 * 24 * 60 * 60


def test_lei_cache_entry_survives_past_the_old_24h_ok_ttl() -> None:
    """End-to-end through `get`/`set`, not just `_ttl_seconds` directly: a
    `lei` hit two days old is still fresh, where D-006's ordinary 24h TTL
    would already call it stale."""
    two_days_ago = datetime.now(UTC) - timedelta(days=2)
    cache.set("NO:brreg:lei:923609016", {"lei": "X"}, fetched_at=two_days_ago)
    assert cache.get("NO:brreg:lei:923609016") is not None


def test_lei_empty_result_survives_past_the_old_1h_ttl_but_not_past_24h() -> None:
    ten_hours_ago = datetime.now(UTC) - timedelta(hours=10)
    cache.set(
        "GB:companies-house:lei:00445790", {}, status="not_found", fetched_at=ten_hours_ago
    )
    assert cache.get("GB:companies-house:lei:00445790") is not None  # a 1h TTL would have expired this

    twenty_five_hours_ago = datetime.now(UTC) - timedelta(hours=25)
    cache.set(
        "GB:companies-house:lei:00445790", {}, status="not_found", fetched_at=twenty_five_hours_ago
    )
    assert cache.get("GB:companies-house:lei:00445790") is None  # past the 24h empty TTL


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
