"""Country-neutral SQLite cache for registry lookups and searches.

Per ``DECISIONS.md`` D-006: one SQLite file, honest ``cached`` / ``fetched_at``.
This module knows nothing about Norway or any other country — a registry
module builds the cache key (``"{COUNTRY}:{registry}:{kind}:{normalised-id-or-
query}"``) and hands this module a JSON-able payload to store and retrieve.

Design notes:

* Every public function re-reads its configuration from the environment on
  each call (path, TTL, disabled flag) rather than caching a singleton, so
  tests can flip ``REGISTRY_MCP_CACHE_PATH`` / ``REGISTRY_MCP_CACHE_DISABLED``
  with ``monkeypatch`` and see the effect immediately, with no import-order
  surprises.
* A cache failure (locked file, corrupt row, disk full) is logged and
  swallowed. The cache is an optimisation, never a dependency — it must not
  turn into a ``RegistryError``.
* Expired rows are deleted lazily, on the next read that touches the table.
  There is no background sweeper.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "CacheEntry",
    "cache_disabled",
    "cache_path",
    "get",
    "set",
]

logger = logging.getLogger(__name__)

_PATH_ENV = "REGISTRY_MCP_CACHE_PATH"
_TTL_ENV = "REGISTRY_MCP_CACHE_TTL_SECONDS"
_DISABLED_ENV = "REGISTRY_MCP_CACHE_DISABLED"

_DEFAULT_PATH = "./data/cache.sqlite3"
_DEFAULT_OK_TTL_SECONDS = 24 * 60 * 60
_NOT_FOUND_TTL_SECONDS = 60 * 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key         TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    status      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS cache_expires ON cache(expires_at);
"""


@dataclass(frozen=True)
class CacheEntry:
    """One cache hit: the stored payload plus its original provenance."""

    payload: dict[str, Any]
    fetched_at: datetime
    status: str


def cache_path() -> Path:
    """Where the cache file lives, per ``REGISTRY_MCP_CACHE_PATH`` (default ``./data/cache.sqlite3``)."""
    raw = os.environ.get(_PATH_ENV, "").strip() or _DEFAULT_PATH
    return Path(raw)


def cache_disabled() -> bool:
    """True when ``REGISTRY_MCP_CACHE_DISABLED=1`` (or ``true``/``yes``)."""
    return os.environ.get(_DISABLED_ENV, "").strip().lower() in {"1", "true", "yes"}


def _ttl_seconds(status: str) -> int:
    """TTL for a given cache status. Only the ``ok`` TTL is overridable by env."""
    if status == "not_found":
        return _NOT_FOUND_TTL_SECONDS
    raw = os.environ.get(_TTL_ENV, "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            logger.warning("%s=%r is not an int; using default TTL", _TTL_ENV, raw)
    return _DEFAULT_OK_TTL_SECONDS


def _connect() -> sqlite3.Connection:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.executescript(_SCHEMA)
    return conn


def _now() -> datetime:
    return datetime.now(UTC)


def _key_prefix(key: str) -> str:
    """The cache key's prefix only — everything up to and including the last
    ``:`` — safe to put in a log line (review fix 3(b), T30). A cache key is
    ``"{COUNTRY}:{registry}:{kind}:{normalised-id-or-query}"``; for a
    registry whose identifier can be personal data (e.g. Sweden's
    personnummer, ``SE:bolagsverket:entity:prod:<identitetsbeteckning>``,
    ``registries/se/client.py``), that final segment must never reach the
    application log. D-040(c)'s "nothing, not a hash" applies to every log
    line, not just ``top_queries`` — nobody reads *this* line for the
    identifier, only to correlate two failures against the same prefix. A
    key with no ``:`` at all (should not happen; defensive only) logs as an
    empty string rather than risk echoing the whole thing.
    """
    idx = key.rfind(":")
    return key[: idx + 1] if idx != -1 else ""


def get(key: str) -> CacheEntry | None:
    """Return the cached entry for ``key``, or ``None`` on a miss / disabled / failure.

    Expired rows touched by this read are deleted lazily. Never raises.
    """
    if cache_disabled():
        return None
    try:
        with _connect() as conn:
            now_iso = _now().isoformat()
            conn.execute("DELETE FROM cache WHERE expires_at < ?", (now_iso,))
            row = conn.execute(
                "SELECT payload, fetched_at, status FROM cache WHERE key = ? AND expires_at >= ?",
                (key, now_iso),
            ).fetchone()
            conn.commit()
        if row is None:
            return None
        payload_raw, fetched_at_raw, status = row
        return CacheEntry(
            payload=json.loads(payload_raw),
            fetched_at=datetime.fromisoformat(fetched_at_raw),
            status=status,
        )
    except Exception:
        logger.warning("cache read failed for key prefix %r", _key_prefix(key), exc_info=True)
        return None


def set(
    key: str,
    payload: Mapping[str, Any],
    *,
    status: str = "ok",
    fetched_at: datetime | None = None,
) -> None:
    """Store ``payload`` under ``key``. Never raises.

    Args:
        key: Cache key, e.g. ``"NO:brreg:entity:923609016"``.
        payload: JSON-able document (a ``CompanyReport``/``SearchResult`` dump).
        status: ``"ok"`` (24 h default TTL) or ``"not_found"`` (1 h fixed TTL).
        fetched_at: The original fetch time. Defaults to now. Preserved verbatim
            on re-reads so a hit can report honest staleness.
    """
    if cache_disabled():
        return
    try:
        when = fetched_at or _now()
        expires_at = when.timestamp() + _ttl_seconds(status)
        expires_iso = datetime.fromtimestamp(expires_at, tz=UTC).isoformat()
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, payload, fetched_at, expires_at, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (key, json.dumps(payload), when.isoformat(), expires_iso, status),
            )
            conn.commit()
    except Exception:
        logger.warning("cache write failed for key prefix %r", _key_prefix(key), exc_info=True)
