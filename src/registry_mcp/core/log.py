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

**`source` — "calls by channel" (T64).** `calls` gains a nullable `source`
column: which of our own published install lines (`?src=readme`, `?src=llms`,
`?src=docs`, `?src=plugin`, `?src=article`, ...) a caller's request carried,
sanitised by :func:`sanitize_source` before it is ever written. An existing
database created before this column existed is migrated in place —
`ensure_schema` adds it with `ALTER TABLE` the first time such a database is
opened — so nothing here requires a fresh database or a manual migration
step. `query` (D-040) is completely untouched by this: `source` is a separate
column with its own sanitiser, never folded into or read from `query`.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from registry_mcp.core.models import Surface

__all__ = [
    "connect",
    "ensure_schema",
    "log_call",
    "log_path",
    "sanitize_source",
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
    cached      INTEGER,
    source      TEXT
);
CREATE INDEX IF NOT EXISTS calls_ts ON calls(ts);
CREATE INDEX IF NOT EXISTS calls_surface ON calls(surface);
"""

#: `calls.source` (T64, "calls by channel"): which of our own published install
#: lines a caller arrived through — `?src=` on the REST routes and on `/mcp`
#: (`api/main.py`, `mcp/server.py::_current_source`), free text, sanitised by
#: :func:`sanitize_source` before it ever reaches SQL. Added after `cached` in
#: `_SCHEMA` above so a *fresh* database gets the column from `CREATE TABLE`
#: directly; `_MIGRATIONS` below is what brings an *existing* database's
#: `calls` table — created by an older build, before this column existed — up
#: to the same shape, the same way `cached` itself would have needed one had
#: this project already been running when it was added. One tuple per column
#: ever added after the original schema, so a second future column is one more
#: entry here, not a new function.
_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("source", "ALTER TABLE calls ADD COLUMN source TEXT"),
)

#: `sanitize_source`: the only characters a stored `source` value may contain.
#: Lower-case letters, digits, `_` and `-` — enough for `readme`, `llms`,
#: `docs`, `card`, `plugin`, `article`, `devto` and any ad-hoc tag a channel
#: needs later, and narrow enough that a `source` value can never carry
#: anything that would need escaping in `top_queries`-style rendering
#: (`api/dashboard.py`) or read as SQL/HTML/shell-meaningful.
_SOURCE_ALLOWED = re.compile(r"[^a-z0-9_-]")
_SOURCE_MAX_LEN = 32

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
    """Create the `calls` table (and its indexes) on ``conn`` if missing, and
    migrate an existing one created before a later column existed.

    ``CREATE TABLE IF NOT EXISTS`` is a no-op on a database an older build of
    this project already created, so a column added to ``_SCHEMA`` after that
    (``source``, T64) would never appear on such a database by itself.
    ``PRAGMA table_info(calls)`` lists the columns actually present, and
    ``_MIGRATIONS`` runs the matching ``ALTER TABLE ... ADD COLUMN`` for any
    column missing from it — skipped when already present, so this is safe to
    call on every :func:`connect` (fresh database, already-migrated database,
    or one still on the old shape alike).
    """
    conn.executescript(_SCHEMA)
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(calls)")}
    for column, migration_sql in _MIGRATIONS:
        if column not in existing_columns:
            conn.execute(migration_sql)
    conn.commit()


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


def sanitize_source(raw: str | None) -> str | None:
    """A free-text ``?src=`` value -> a safe attribution tag, or ``None``.

    Lower-cased, then every character outside ``[a-z0-9_-]`` is dropped
    (filtered, not rejected — punctuation, spaces and case are noise on an
    attribution tag, not a reason to discard the whole value), then the
    result is truncated to 32 characters. Filtering before truncating keeps
    as much of the caller's intent as fits — truncating first could cut into
    the readable part and leave only trailing punctuation to strip.

    ``None``, ``""`` and a string that is *all* disallowed characters
    (``"???"``) all become ``None`` here: the column is nullable and a bare
    ``""`` would just be a second, indistinguishable "no value" beside
    ``NULL`` — the same reasoning `core/stats.py`'s ``if query:`` guard
    already applies to an empty ``query`` (D-040(c)).

    Pure and never raises. Called once, here, by :func:`log_call` — neither
    surface (`api/main.py`, `mcp/server.py`) needs to sanitise its own ``src``
    value before passing it through, the same centralising instinct as
    `core/registry.py::loggable_query` for ``query``, minus the country
    lookup: unlike D-040's redaction, this transform needs no context beyond
    the string itself, so there is no reason to push it out to the surfaces.
    """
    if not raw:
        return None
    cleaned = _SOURCE_ALLOWED.sub("", raw.lower())[:_SOURCE_MAX_LEN]
    return cleaned or None


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
    source: str | None = None,
) -> None:
    """Record one call to the `calls` table. Never raises.

    Signature matches ``api/main.py::record_call``'s call site exactly (see
    the module docstring) and `NORBIZ_SPEC.md` §11. ``source`` (T64) is the
    caller's raw ``?src=`` value, if any — run through :func:`sanitize_source`
    here rather than by either caller, so a surface can pass its query
    parameter straight through with no risk of an unsanitised value ever
    reaching SQL.
    """
    try:
        ts = datetime.now(UTC).isoformat()
        cached_value: int | None = None if cached is None else int(cached)
        source_value = sanitize_source(source)
        with connect() as conn:
            conn.execute(
                "INSERT INTO calls "
                "(ts, surface, operation, country, query, user_agent, latency_ms, ok, "
                "error_code, cached, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    source_value,
                ),
            )
            conn.commit()
    except Exception:
        logger.warning("log_call failed for operation %r", operation, exc_info=True)
