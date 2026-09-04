"""Usage logging: one function used by both surfaces (`NORBIZ_SPEC.md` §11, T08).

``log_call`` is the exact keyword shape ``api/main.py::record_call`` already
calls (see the comment above ``record_call`` there) — this module's whole
integration contract is::

    from registry_mcp.core import log
    registry_mcp.api.main.record_call = log.log_call

No route or tool changes to pick this module up; a later step wires the
assignment above into ``api/main.py`` and an analogous hook into
``mcp/server.py``.

**DB path — a deliberate difference from the literal `NORBIZ_SPEC.md` §11
text.** The spec's draft has logging live at its own default path
(``./data/calls.sqlite3`` via ``REGISTRY_MCP_LOG_PATH``). Per this task's
orchestrator instructions, this implementation instead **shares the cache's
SQLite file by default**: ``log_path()`` returns ``REGISTRY_MCP_LOG_PATH``
when set, else ``REGISTRY_MCP_CACHE_PATH`` (else the same
``./data/cache.sqlite3`` default `core/cache.py` uses, D-006). The ``calls``
table lives beside `core/cache.py`'s ``cache`` table in that one file, so a
deployment that never sets either env var gets one SQLite file, not two.
Setting ``REGISTRY_MCP_LOG_PATH`` splits logging into its own file again,
which restores the spec's original default path if that is preferred later.

Design notes (mirrors `core/cache.py`'s style deliberately):

* Every public function re-reads its configuration from the environment on
  each call rather than caching a singleton, so tests can flip
  ``REGISTRY_MCP_LOG_PATH`` / ``REGISTRY_MCP_CACHE_PATH`` with ``monkeypatch``
  and see the effect immediately. ``set_sink()`` is a stronger override for
  tests that don't want to touch the environment at all (or want to point
  logging at a path independent of whatever the cache tests are doing in the
  same process).
* ``query`` is the org.nr or the search string only — never a full request
  body, never headers, no IP addresses, no API keys. Enforcing that is the
  caller's job (per `NORBIZ_SPEC.md` §11); this module stores whatever string
  it is given.
* ``log_call`` never raises. Any failure (locked file, disk full, bad path)
  is logged at WARNING and swallowed — logging is not allowed to fail a
  request.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from registry_mcp.core.models import Surface

__all__ = [
    "connect",
    "ensure_schema",
    "log_call",
    "log_path",
    "set_sink",
]

logger = logging.getLogger(__name__)

_LOG_PATH_ENV = "REGISTRY_MCP_LOG_PATH"
_CACHE_PATH_ENV = "REGISTRY_MCP_CACHE_PATH"
_DEFAULT_CACHE_PATH = "./data/cache.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
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
CREATE INDEX IF NOT EXISTS calls_ts ON calls(ts);
CREATE INDEX IF NOT EXISTS calls_surface ON calls(surface);
"""

# Test hook: when set, overrides env-derived path entirely. `None` means
# "read the environment as normal" (see `log_path()`).
_sink_override: Path | None = None


def set_sink(path: str | Path | None) -> None:
    """Point logging at ``path`` regardless of env vars, or ``None`` to reset.

    A test hook only — production code should rely on ``REGISTRY_MCP_LOG_PATH``
    / ``REGISTRY_MCP_CACHE_PATH`` instead.
    """
    global _sink_override
    _sink_override = Path(path) if path is not None else None


def log_path() -> Path:
    """Where the `calls` table lives.

    ``REGISTRY_MCP_LOG_PATH`` if set; otherwise the same file `core/cache.py`
    uses (``REGISTRY_MCP_CACHE_PATH``, default ``./data/cache.sqlite3``).
    """
    if _sink_override is not None:
        return _sink_override
    raw = os.environ.get(_LOG_PATH_ENV, "").strip()
    if raw:
        return Path(raw)
    cache_raw = os.environ.get(_CACHE_PATH_ENV, "").strip() or _DEFAULT_CACHE_PATH
    return Path(cache_raw)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the `calls` table (and its indexes) on ``conn`` if missing."""
    conn.executescript(_SCHEMA)


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the log database at ``path`` (default `log_path()`), schema ensured.

    May raise — callers that must never fail a request (`log_call`) catch
    around it. `core/stats.py` also uses this so read and write agree on the
    schema.
    """
    target = path if path is not None else log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=5.0)
    ensure_schema(conn)
    return conn


def log_call(
    *,
    surface: Surface,
    operation: str,
    country: str | None,
    query: str | None,
    user_agent: str | None,
    latency_ms: int,
    ok: bool,
    error_code: str | None = None,
    cached: bool | None = None,
) -> None:
    """Record one call to the `calls` table. Never raises.

    Signature matches ``api/main.py::record_call``'s call site exactly (see
    the module docstring) and `NORBIZ_SPEC.md` §11.
    """
    try:
        ts = datetime.now(UTC).isoformat()
        cached_value: int | None = None if cached is None else int(cached)
        with connect() as conn:
            conn.execute(
                "INSERT INTO calls "
                "(ts, surface, operation, country, query, user_agent, latency_ms, ok, "
                "error_code, cached) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ts,
                    surface.value,
                    operation,
                    country,
                    query,
                    user_agent,
                    int(latency_ms),
                    int(ok),
                    error_code,
                    cached_value,
                ),
            )
            conn.commit()
    except Exception:
        logger.warning("log_call failed for operation %r", operation, exc_info=True)
