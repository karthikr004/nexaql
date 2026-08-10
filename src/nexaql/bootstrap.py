# Copyright (c) 2026-present NexaQL Contributors
"""Bootstrap database — stores all NexaQL configuration.

Supports two backends:
  - **SQLite** (default): file at ``~/.nexaql/nexaql.sqlite``, WAL mode.
  - **PostgreSQL**: when ``NEXAQL_BOOTSTRAP_DB_URL`` is set to a PG connection
    string (e.g. ``postgresql://user:pass@host:5432/dbname``).

All public functions are backend-agnostic; the ``_DbAdapter`` translates
SQL dialect differences transparently.

Tables:
  connectors   — database connections (Postgres, DuckDB, MySQL, etc.)
  domains      — logical groupings of schemas
  schemas      — ontology definitions per domain, each linked to a connector
  llm_config   — LLM provider settings
  api_keys     — API keys for LLM providers
  server_config — server settings (host, port, cors, active domain)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Bootstrap DB path ─────────────────────────────────────────────────────────

_DEFAULT_DB_DIR = os.path.join(Path.home(), ".nexaql")
_DEFAULT_DB_PATH = os.path.join(_DEFAULT_DB_DIR, "nexaql.sqlite")


def _get_db_url() -> str | None:
    """Return PG connection URL if set, else None (fall back to SQLite)."""
    return os.environ.get("NEXAQL_BOOTSTRAP_DB_URL")


def _get_db_path() -> str:
    """Get the bootstrap DB path. Override with NEXAQL_BOOTSTRAP_DB env var."""
    return os.environ.get("NEXAQL_BOOTSTRAP_DB", _DEFAULT_DB_PATH)


def _is_pg() -> bool:
    """True when using PostgreSQL as the bootstrap backend."""
    url = _get_db_url()
    return url is not None and url.startswith("postgres")


# ── Database adapter ─────────────────────────────────────────────────────────

_INSERT_OR_IGNORE_RE = re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\?")


class _CursorResult:
    """Unified cursor result for both SQLite and PostgreSQL."""

    __slots__ = ("_rows", "rowcount", "lastrowid")

    def __init__(self, rows: list[tuple] | None, rowcount: int, lastrowid: int | None = None):
        self._rows = rows
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def fetchone(self) -> tuple | None:
        if self._rows:
            return self._rows[0]
        return None

    def fetchall(self) -> list[tuple]:
        return self._rows or []


class _DbAdapter:
    """Thin wrapper providing a uniform interface over sqlite3 or psycopg2."""

    def __init__(self, backend: str, raw_conn: Any):
        self._backend = backend
        self._raw = raw_conn

    @property
    def is_pg(self) -> bool:
        return self._backend == "pg"

    def execute(self, sql: str, params: list | tuple | None = None) -> _CursorResult:
        if self.is_pg:
            return self._pg_execute(sql, params)
        return self._sqlite_execute(sql, params)

    def insert_returning_id(self, sql: str, params: list | tuple | None = None) -> int:
        """INSERT and return the auto-generated id."""
        if self.is_pg:
            sql = self._translate_sql(sql).rstrip().rstrip(";")
            sql += " RETURNING id"
            cur = self._raw.cursor()
            try:
                cur.execute(sql, params or None)
                return cur.fetchone()[0]
            finally:
                cur.close()
        else:
            self._raw.execute(sql, params or [])
            return self._raw.execute("SELECT last_insert_rowid()").fetchone()[0]

    def close(self) -> None:
        self._raw.close()

    # ── SQLite path ──────────────────────────────────────────────────────────

    def _sqlite_execute(self, sql: str, params: list | tuple | None = None) -> _CursorResult:
        cur = self._raw.execute(sql, params or [])
        desc = cur.description
        if desc is not None:
            rows = cur.fetchall()
        else:
            rows = None
        return _CursorResult(rows, cur.rowcount, cur.lastrowid)

    # ── PostgreSQL path ──────────────────────────────────────────────────────

    def _pg_execute(self, sql: str, params: list | tuple | None = None) -> _CursorResult:
        sql = self._translate_sql(sql)
        cur = self._raw.cursor()
        try:
            cur.execute(sql, params or None)
            if cur.description is not None:
                rows = cur.fetchall()
            else:
                rows = None
            return _CursorResult(rows, cur.rowcount)
        finally:
            cur.close()

    @staticmethod
    def _translate_sql(sql: str) -> str:
        sql = _PLACEHOLDER_RE.sub("%s", sql)
        if _INSERT_OR_IGNORE_RE.search(sql):
            sql = _INSERT_OR_IGNORE_RE.sub("INSERT", sql)
            sql = sql.rstrip().rstrip(";")
            sql += " ON CONFLICT DO NOTHING"
        return sql


# ── Connection management ─────────────────────────────────────────────────────

_conn: _DbAdapter | None = None
_initialized: bool = False


def _get_conn() -> _DbAdapter:
    """Get or create the singleton DB connection (SQLite or PostgreSQL)."""
    global _conn, _initialized
    if _conn is None:
        pg_url = _get_db_url()
        if pg_url and pg_url.startswith("postgres"):
            _conn = _open_pg(pg_url)
        else:
            _conn = _open_sqlite()
    if not _initialized:
        _ensure_tables(_conn)
        _initialized = True
    return _conn


def _open_sqlite() -> _DbAdapter:
    db_path = _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    _migrate_from_duckdb(db_path)
    raw = sqlite3.connect(db_path, isolation_level=None)
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA busy_timeout=5000")
    raw.execute("PRAGMA foreign_keys=ON")
    log.info("Bootstrap DB opened (SQLite) at %s", db_path)
    return _DbAdapter("sqlite", raw)


def _open_pg(url: str) -> _DbAdapter:
    import psycopg2
    raw = psycopg2.connect(url)
    raw.autocommit = True
    log.info("Bootstrap DB opened (PostgreSQL) at %s", url.split("@")[-1] if "@" in url else url)
    return _DbAdapter("pg", raw)


def close() -> None:
    """Close the bootstrap DB connection."""
    global _conn, _initialized
    if _conn is not None:
        _conn.close()
        _conn = None
        _initialized = False


def _migrate_from_duckdb(sqlite_path: str) -> None:
    """Auto-migrate data from old DuckDB nexaql.db to new SQLite file.

    Only runs if the old DuckDB file exists and the SQLite file does not.
    After successful migration, renames the old file to nexaql.db.bak.
    """
    if os.path.exists(sqlite_path):
        return

    old_db_path = os.path.join(os.path.dirname(sqlite_path), "nexaql.db")
    if not os.path.exists(old_db_path):
        return

    log.info("Found legacy DuckDB config at %s — migrating to SQLite...", old_db_path)

    try:
        import duckdb
    except ImportError:
        log.warning("duckdb not installed — cannot migrate old config. Starting fresh.")
        return

    try:
        old_conn = duckdb.connect(old_db_path, read_only=True)
    except Exception as e:
        log.warning("Cannot open old DuckDB config for migration: %s", e)
        return

    try:
        new_conn = sqlite3.connect(sqlite_path, isolation_level=None)
        new_conn.execute("PRAGMA journal_mode=WAL")
        new_conn.execute("PRAGMA foreign_keys=OFF")

        for stmt in _DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                new_conn.execute(stmt)

        new_conn.execute("INSERT OR IGNORE INTO server_config (id) VALUES (1)")

        tables_and_cols = [
            ("connectors", ["id", "name", "type", "url", "credentials", "created_at"]),
            ("domains", ["id", "name", "description", "roles_json", "access_functions_json", "created_at"]),
            ("schemas", ["id", "domain_id", "connector_id", "name", "ontology_json", "created_at", "updated_at"]),
            ("llm_config", ["id", "provider", "model", "max_tokens", "summary_max_tokens", "generation_mode", "is_active"]),
            ("api_keys", ["id", "provider", "name", "key", "created_at"]),
        ]

        for table, cols in tables_and_cols:
            try:
                rows = old_conn.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
            except Exception:
                continue
            if not rows:
                continue
            placeholders = ", ".join(["?"] * len(cols))
            col_list = ", ".join(cols)
            for row in rows:
                try:
                    new_conn.execute(
                        f"INSERT OR IGNORE INTO {table} ({col_list}) VALUES ({placeholders})",
                        list(row),
                    )
                except Exception as e:
                    log.debug("Migration row skipped for %s: %s", table, e)

        try:
            row = old_conn.execute(
                "SELECT host, port, cors_origins, auth_mode, active_domain, auth_secret, auth_algorithm "
                "FROM server_config WHERE id = 1"
            ).fetchone()
            if row:
                new_conn.execute(
                    "UPDATE server_config SET host=?, port=?, cors_origins=?, auth_mode=?, "
                    "active_domain=?, auth_secret=?, auth_algorithm=? WHERE id=1",
                    list(row),
                )
        except Exception as e:
            log.debug("server_config migration skipped: %s", e)

        new_conn.execute("PRAGMA foreign_keys=ON")
        new_conn.close()
        old_conn.close()

        backup_path = old_db_path + ".bak"
        os.rename(old_db_path, backup_path)
        log.info("Migration complete. Old DB backed up to %s", backup_path)

    except Exception as e:
        log.warning("DuckDB to SQLite migration failed: %s. Starting fresh.", e)
        old_conn.close()
        if os.path.exists(sqlite_path):
            os.remove(sqlite_path)


def _now() -> str:
    """UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat()


# ── DDL ───────────────────────────────────────────────────────────────────────

_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS connectors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    type        TEXT NOT NULL,
    url         TEXT,
    credentials TEXT,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS domains (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT UNIQUE NOT NULL,
    description          TEXT,
    roles_json           TEXT,
    access_functions_json TEXT,
    created_at           TEXT
);

CREATE TABLE IF NOT EXISTS schemas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id      INTEGER NOT NULL REFERENCES domains(id),
    connector_id   INTEGER NOT NULL REFERENCES connectors(id),
    name           TEXT NOT NULL,
    ontology_json  TEXT NOT NULL,
    created_at     TEXT,
    updated_at     TEXT,
    UNIQUE(domain_id, name)
);

CREATE TABLE IF NOT EXISTS llm_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    provider        TEXT NOT NULL DEFAULT '',
    model           TEXT NOT NULL DEFAULT '',
    max_tokens      INTEGER DEFAULT 4096,
    summary_max_tokens INTEGER DEFAULT 2048,
    generation_mode TEXT DEFAULT 'intent',
    is_active       BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS api_keys (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    provider   TEXT UNIQUE NOT NULL,
    name       TEXT,
    key        TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS server_config (
    id                   INTEGER PRIMARY KEY DEFAULT 1 CHECK(id = 1),
    host                 TEXT DEFAULT '0.0.0.0',
    port                 INTEGER DEFAULT 3717,
    cors_origins         TEXT DEFAULT '["*"]',
    auth_mode            TEXT DEFAULT 'dev',
    active_domain        TEXT,
    auth_secret          TEXT,
    auth_algorithm       TEXT DEFAULT 'HS256',
    oauth_providers_json TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT UNIQUE NOT NULL,
    name           TEXT,
    avatar_url     TEXT,
    oauth_provider TEXT NOT NULL,
    oauth_sub      TEXT NOT NULL,
    roles_json     TEXT DEFAULT '[]',
    is_active      BOOLEAN DEFAULT 1,
    created_at     TEXT,
    last_login_at  TEXT,
    UNIQUE(oauth_provider, oauth_sub)
);

CREATE TABLE IF NOT EXISTS invited_emails (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT UNIQUE NOT NULL,
    invited_by INTEGER,
    roles_json TEXT DEFAULT '[]',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS chat_threads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    title       TEXT,
    domain      TEXT,
    is_archived BOOLEAN DEFAULT 0,
    created_at  TEXT,
    updated_at  TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id   INTEGER NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at  TEXT,
    FOREIGN KEY (thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS business_ontology (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id       INTEGER NOT NULL REFERENCES domains(id),
    term            TEXT NOT NULL,
    definition      TEXT NOT NULL,
    sql_hint        TEXT,
    tags            TEXT DEFAULT '[]',
    created_by      INTEGER,
    created_at      TEXT,
    updated_at      TEXT,
    UNIQUE(domain_id, term)
);

CREATE TABLE IF NOT EXISTS cloud_drive_accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_id    INTEGER NOT NULL REFERENCES connectors(id),
    email           TEXT NOT NULL,
    display_name    TEXT,
    access_token    TEXT NOT NULL,
    refresh_token   TEXT NOT NULL,
    token_expires_at TEXT,
    created_at      TEXT,
    UNIQUE(connector_id, email)
);
"""

_DDL = _DDL_SQLITE

_DDL_PG = """
CREATE TABLE IF NOT EXISTS connectors (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    type        TEXT NOT NULL,
    url         TEXT,
    credentials TEXT,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS domains (
    id                   SERIAL PRIMARY KEY,
    name                 TEXT UNIQUE NOT NULL,
    description          TEXT,
    roles_json           TEXT,
    access_functions_json TEXT,
    created_at           TEXT
);

CREATE TABLE IF NOT EXISTS schemas (
    id             SERIAL PRIMARY KEY,
    domain_id      INTEGER NOT NULL REFERENCES domains(id),
    connector_id   INTEGER NOT NULL REFERENCES connectors(id),
    name           TEXT NOT NULL,
    ontology_json  TEXT NOT NULL,
    created_at     TEXT,
    updated_at     TEXT,
    UNIQUE(domain_id, name)
);

CREATE TABLE IF NOT EXISTS llm_config (
    id              SERIAL PRIMARY KEY,
    provider        TEXT NOT NULL DEFAULT '',
    model           TEXT NOT NULL DEFAULT '',
    max_tokens      INTEGER DEFAULT 4096,
    summary_max_tokens INTEGER DEFAULT 2048,
    generation_mode TEXT DEFAULT 'intent',
    is_active       BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS api_keys (
    id         SERIAL PRIMARY KEY,
    provider   TEXT UNIQUE NOT NULL,
    name       TEXT,
    key        TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS server_config (
    id                   INTEGER PRIMARY KEY DEFAULT 1 CHECK(id = 1),
    host                 TEXT DEFAULT '0.0.0.0',
    port                 INTEGER DEFAULT 3717,
    cors_origins         TEXT DEFAULT '["*"]',
    auth_mode            TEXT DEFAULT 'dev',
    active_domain        TEXT,
    auth_secret          TEXT,
    auth_algorithm       TEXT DEFAULT 'HS256',
    oauth_providers_json TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS users (
    id             SERIAL PRIMARY KEY,
    email          TEXT UNIQUE NOT NULL,
    name           TEXT,
    avatar_url     TEXT,
    oauth_provider TEXT NOT NULL,
    oauth_sub      TEXT NOT NULL,
    roles_json     TEXT DEFAULT '[]',
    is_active      BOOLEAN DEFAULT TRUE,
    created_at     TEXT,
    last_login_at  TEXT,
    UNIQUE(oauth_provider, oauth_sub)
);

CREATE TABLE IF NOT EXISTS invited_emails (
    id         SERIAL PRIMARY KEY,
    email      TEXT UNIQUE NOT NULL,
    invited_by INTEGER,
    roles_json TEXT DEFAULT '[]',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS chat_threads (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    title       TEXT,
    domain      TEXT,
    is_archived BOOLEAN DEFAULT FALSE,
    created_at  TEXT,
    updated_at  TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          SERIAL PRIMARY KEY,
    thread_id   INTEGER NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at  TEXT,
    FOREIGN KEY (thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS business_ontology (
    id              SERIAL PRIMARY KEY,
    domain_id       INTEGER NOT NULL REFERENCES domains(id),
    term            TEXT NOT NULL,
    definition      TEXT NOT NULL,
    sql_hint        TEXT,
    tags            TEXT DEFAULT '[]',
    created_by      INTEGER,
    created_at      TEXT,
    updated_at      TEXT,
    UNIQUE(domain_id, term)
);

CREATE TABLE IF NOT EXISTS cloud_drive_accounts (
    id              SERIAL PRIMARY KEY,
    connector_id    INTEGER NOT NULL REFERENCES connectors(id),
    email           TEXT NOT NULL,
    display_name    TEXT,
    access_token    TEXT NOT NULL,
    refresh_token   TEXT NOT NULL,
    token_expires_at TEXT,
    created_at      TEXT,
    UNIQUE(connector_id, email)
);
"""


def _ensure_tables(conn: _DbAdapter) -> None:
    """Create tables if they don't exist."""
    ddl = _DDL_PG if conn.is_pg else _DDL_SQLITE
    for stmt in ddl.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except Exception as e:
                log.debug("DDL statement skipped: %s", e)

    row = conn.execute("SELECT COUNT(*) FROM server_config").fetchone()
    if row and row[0] == 0:
        conn.execute("INSERT INTO server_config (id) VALUES (1)")

    # Migrate: add columns if missing (existing DBs)
    for col, default in [
        ("auth_secret", "NULL"),
        ("auth_algorithm", "'HS256'"),
        ("oauth_providers_json", "'[]'"),
    ]:
        try:
            conn.execute(f"SELECT {col} FROM server_config LIMIT 1")
        except Exception:
            conn.execute(f"ALTER TABLE server_config ADD COLUMN {col} TEXT DEFAULT {default}")

    # Attempt legacy migration on first init
    _migrate_from_legacy(conn)


# ── Connectors CRUD ──────────────────────────────────────────────────────────


def list_connectors() -> list[dict]:
    """List all saved connectors."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, name, type, url, credentials, created_at FROM connectors ORDER BY name"
    ).fetchall()
    return [
        {"id": r[0], "name": r[1], "type": r[2], "url": r[3], "credentials": r[4], "created_at": r[5]}
        for r in rows
    ]


def get_connector(name: str) -> dict | None:
    """Get a connector by name."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, name, type, url, credentials, created_at FROM connectors WHERE name = ?", [name]
    ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "type": row[2], "url": row[3], "credentials": row[4], "created_at": row[5]}


def get_connector_by_id(connector_id: int) -> dict | None:
    """Get a connector by ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, name, type, url, credentials, created_at FROM connectors WHERE id = ?", [connector_id]
    ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "type": row[2], "url": row[3], "credentials": row[4], "created_at": row[5]}


def save_connector(name: str, type: str, url: str | None = None, credentials: str | None = None) -> int:
    """Save or update a connector. Returns the connector ID."""
    conn = _get_conn()
    existing = get_connector(name)
    if existing:
        conn.execute(
            "UPDATE connectors SET type = ?, url = ?, credentials = ? WHERE name = ?",
            [type, url, credentials, name],
        )
        return existing["id"]
    else:
        conn.execute(
            "INSERT INTO connectors (name, type, url, credentials, created_at) VALUES (?, ?, ?, ?, ?)",
            [name, type, url, credentials, _now()],
        )
        row = conn.execute("SELECT id FROM connectors WHERE name = ?", [name]).fetchone()
        return row[0]


def delete_connector(name: str) -> bool:
    """Delete a connector. Raises if referenced by schemas (ON DELETE RESTRICT)."""
    conn = _get_conn()
    existing = get_connector(name)
    if existing is None:
        return False
    # Check for referencing schemas
    refs = conn.execute(
        "SELECT s.name, d.name as domain_name FROM schemas s "
        "JOIN domains d ON s.domain_id = d.id "
        "WHERE s.connector_id = ?",
        [existing["id"]],
    ).fetchall()
    if refs:
        schema_list = ", ".join(f"{r[1]}.{r[0]}" for r in refs)
        raise ValueError(
            f"Cannot delete connector '{name}': used by schema(s): {schema_list}. "
            "Remove those schema mappings first."
        )
    conn.execute("DELETE FROM connectors WHERE name = ?", [name])
    return True


def rename_connector(old_name: str, new_name: str) -> bool:
    """Rename a connector. Safe — schemas reference by ID."""
    conn = _get_conn()
    existing = get_connector(old_name)
    if existing is None:
        return False
    conn.execute("UPDATE connectors SET name = ? WHERE name = ?", [new_name, old_name])
    return True


# ── Domains CRUD ─────────────────────────────────────────────────────────────


def list_domains() -> list[dict]:
    """List all domains with their schema count."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT d.id, d.name, d.description, d.created_at, "
        "COUNT(s.id) as schema_count "
        "FROM domains d LEFT JOIN schemas s ON d.id = s.domain_id "
        "GROUP BY d.id, d.name, d.description, d.created_at "
        "ORDER BY d.name"
    ).fetchall()
    return [
        {"id": r[0], "name": r[1], "description": r[2], "created_at": r[3], "schema_count": r[4]}
        for r in rows
    ]


def get_domain(name: str) -> dict | None:
    """Get a domain by name."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, name, description, roles_json, access_functions_json, created_at "
        "FROM domains WHERE name = ?", [name]
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "name": row[1], "description": row[2],
        "roles_json": row[3], "access_functions_json": row[4],
        "created_at": row[5],
    }


def create_domain(name: str, description: str = "") -> int:
    """Create a domain. Returns the domain ID."""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO domains (name, description, created_at) VALUES (?, ?, ?)",
        [name, description, _now()],
    )
    row = conn.execute("SELECT id FROM domains WHERE name = ?", [name]).fetchone()
    return row[0]


def save_domain_policies(
    domain_name: str,
    roles: dict | None = None,
    access_functions: dict | None = None,
) -> None:
    """Save roles and access_functions at the domain level."""
    conn = _get_conn()
    domain = get_domain(domain_name)
    if domain is None:
        raise ValueError(f"Domain '{domain_name}' not found")
    updates = []
    params = []
    if roles is not None:
        updates.append("roles_json = ?")
        params.append(json.dumps(roles))
    if access_functions is not None:
        updates.append("access_functions_json = ?")
        params.append(json.dumps(access_functions))
    if updates:
        params.append(domain_name)
        conn.execute(
            f"UPDATE domains SET {', '.join(updates)} WHERE name = ?",
            params,
        )


def delete_domain(name: str) -> bool:
    """Delete a domain and CASCADE its schemas."""
    conn = _get_conn()
    existing = get_domain(name)
    if existing is None:
        return False
    conn.execute("DELETE FROM domains WHERE name = ?", [name])
    return True


# ── Schemas CRUD ─────────────────────────────────────────────────────────────


def list_schemas(domain_name: str) -> list[dict]:
    """List all schemas for a domain."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT s.id, s.name, s.connector_id, c.name as connector_name, c.type as connector_type, "
        "s.ontology_json, s.created_at, s.updated_at "
        "FROM schemas s "
        "JOIN domains d ON s.domain_id = d.id "
        "JOIN connectors c ON s.connector_id = c.id "
        "WHERE d.name = ? "
        "ORDER BY s.name",
        [domain_name],
    ).fetchall()
    return [
        {
            "id": r[0], "name": r[1], "connector_id": r[2],
            "connector_name": r[3], "connector_type": r[4],
            "ontology_json": r[5], "created_at": r[6], "updated_at": r[7],
        }
        for r in rows
    ]


def get_schema(domain_name: str, schema_name: str) -> dict | None:
    """Get a specific schema by domain and schema name."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT s.id, s.name, s.connector_id, c.name as connector_name, c.type as connector_type, "
        "s.ontology_json, s.created_at, s.updated_at "
        "FROM schemas s "
        "JOIN domains d ON s.domain_id = d.id "
        "JOIN connectors c ON s.connector_id = c.id "
        "WHERE d.name = ? AND s.name = ?",
        [domain_name, schema_name],
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "name": row[1], "connector_id": row[2],
        "connector_name": row[3], "connector_type": row[4],
        "ontology_json": row[5], "created_at": row[6], "updated_at": row[7],
    }


def save_schema(
    domain_name: str,
    schema_name: str,
    connector_id: int,
    ontology_json: str | dict,
) -> int:
    """Save or update a schema. Returns the schema ID."""
    conn = _get_conn()

    # Validate connector exists
    connector = get_connector_by_id(connector_id)
    if connector is None:
        raise ValueError(f"Connector with id={connector_id} does not exist.")

    # Ensure domain exists
    domain = get_domain(domain_name)
    if domain is None:
        domain_id = create_domain(domain_name)
    else:
        domain_id = domain["id"]

    # Serialize ontology if dict
    if isinstance(ontology_json, dict):
        ontology_json = json.dumps(ontology_json)

    # Upsert by (domain_id, name) — direct check without connector JOIN
    row = conn.execute(
        "SELECT id FROM schemas WHERE domain_id = ? AND name = ?",
        [domain_id, schema_name],
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE schemas SET connector_id = ?, ontology_json = ?, updated_at = ? "
            "WHERE id = ?",
            [connector_id, ontology_json, _now(), row[0]],
        )
        return row[0]
    else:
        now = _now()
        conn.execute(
            "INSERT INTO schemas (domain_id, connector_id, name, ontology_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [domain_id, connector_id, schema_name, ontology_json, now, now],
        )
        row = conn.execute(
            "SELECT s.id FROM schemas s JOIN domains d ON s.domain_id = d.id "
            "WHERE d.name = ? AND s.name = ?",
            [domain_name, schema_name],
        ).fetchone()
        return row[0]


def delete_schema(domain_name: str, schema_name: str) -> bool:
    """Delete a schema."""
    conn = _get_conn()
    existing = get_schema(domain_name, schema_name)
    if existing is None:
        return False
    conn.execute("DELETE FROM schemas WHERE id = ?", [existing["id"]])
    return True


def get_domain_ontology(domain_name: str) -> dict | None:
    """Load the merged ontology for a domain (all schemas combined).

    Returns a dict with all nodes from all schemas, plus metadata about
    which connector each node belongs to (for query routing).
    """
    schemas = list_schemas(domain_name)
    if not schemas:
        return None

    merged_nodes: dict[str, Any] = {}
    node_to_connector: dict[str, int] = {}  # node_name -> connector_id

    for schema in schemas:
        try:
            ont_data = json.loads(schema["ontology_json"]) if isinstance(schema["ontology_json"], str) else schema["ontology_json"]
        except (json.JSONDecodeError, TypeError):
            continue

        nodes = ont_data.get("nodes", {})
        for node_name, node_def in nodes.items():
            merged_nodes[node_name] = node_def
            node_to_connector[node_name] = schema["connector_id"]

    # Load roles and access_functions from domain level
    domain = get_domain(domain_name)
    roles: dict[str, Any] = {}
    access_functions: dict[str, Any] = {}
    if domain:
        if domain.get("roles_json"):
            try:
                roles = json.loads(domain["roles_json"]) if isinstance(domain["roles_json"], str) else domain["roles_json"]
            except (json.JSONDecodeError, TypeError):
                pass
        if domain.get("access_functions_json"):
            try:
                access_functions = json.loads(domain["access_functions_json"]) if isinstance(domain["access_functions_json"], str) else domain["access_functions_json"]
            except (json.JSONDecodeError, TypeError):
                pass

    result: dict[str, Any] = {
        "domain": domain_name,
        "description": domain["description"] if domain else "",
        "nodes": merged_nodes,
        "node_to_connector": node_to_connector,
        "version": "1.0",
    }
    if roles:
        result["roles"] = roles
    if access_functions:
        result["access_functions"] = access_functions
    return result


# ── LLM Config CRUD ─────────────────────────────────────────────────────────


def get_active_llm_config() -> dict | None:
    """Get the active LLM configuration."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, provider, model, max_tokens, summary_max_tokens, generation_mode "
        "FROM llm_config WHERE is_active = TRUE ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0], "provider": row[1], "model": row[2],
        "max_tokens": row[3], "summary_max_tokens": row[4],
        "generation_mode": row[5],
    }


def save_llm_config(
    provider: str,
    model: str,
    max_tokens: int = 4096,
    summary_max_tokens: int = 2048,
    generation_mode: str = "intent",
) -> int:
    """Save LLM config. Deactivates all others, makes this one active."""
    conn = _get_conn()
    # Deactivate all existing
    conn.execute("UPDATE llm_config SET is_active = FALSE")
    # Check if one already exists for this provider
    existing = conn.execute(
        "SELECT id FROM llm_config WHERE provider = ? AND model = ?", [provider, model]
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE llm_config SET max_tokens = ?, summary_max_tokens = ?, "
            "generation_mode = ?, is_active = TRUE WHERE id = ?",
            [max_tokens, summary_max_tokens, generation_mode, existing[0]],
        )
        return existing[0]
    else:
        conn.execute(
            "INSERT INTO llm_config (provider, model, max_tokens, summary_max_tokens, generation_mode, is_active) "
            "VALUES (?, ?, ?, ?, ?, TRUE)",
            [provider, model, max_tokens, summary_max_tokens, generation_mode],
        )
        row = conn.execute("SELECT MAX(id) FROM llm_config").fetchone()
        return row[0]


def list_llm_configs() -> list[dict]:
    """List all LLM configs."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, provider, model, max_tokens, summary_max_tokens, generation_mode, is_active "
        "FROM llm_config ORDER BY id"
    ).fetchall()
    return [
        {
            "id": r[0], "provider": r[1], "model": r[2], "max_tokens": r[3],
            "summary_max_tokens": r[4], "generation_mode": r[5], "is_active": r[6],
        }
        for r in rows
    ]


# ── API Keys CRUD ────────────────────────────────────────────────────────────


def list_api_keys() -> list[dict]:
    """List all API keys (with masked key values)."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, provider, name, key, created_at FROM api_keys ORDER BY provider"
    ).fetchall()
    return [
        {"id": r[0], "provider": r[1], "name": r[2], "key": r[3], "created_at": r[4]}
        for r in rows
    ]


def get_api_key(provider: str) -> str | None:
    """Get the API key for a provider. Falls back to env vars."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT key FROM api_keys WHERE provider = ?", [provider.lower()]
    ).fetchone()
    if row:
        return row[0]
    # Fallback: environment variables
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "google": "GOOGLE_API_KEY",
        "cohere": "COHERE_API_KEY",
    }
    env_var = env_map.get(provider.lower())
    if env_var:
        return os.environ.get(env_var)
    return None


def save_api_key(provider: str, name: str, key: str) -> int:
    """Save or update an API key. Returns the key ID."""
    conn = _get_conn()
    provider = provider.lower()
    existing = conn.execute("SELECT id FROM api_keys WHERE provider = ?", [provider]).fetchone()
    if existing:
        conn.execute(
            "UPDATE api_keys SET name = ?, key = ?, created_at = ? WHERE provider = ?",
            [name, key, _now(), provider],
        )
        return existing[0]
    else:
        conn.execute(
            "INSERT INTO api_keys (provider, name, key, created_at) VALUES (?, ?, ?, ?)",
            [provider, name, key, _now()],
        )
        row = conn.execute("SELECT id FROM api_keys WHERE provider = ?", [provider]).fetchone()
        return row[0]


def delete_api_key(provider: str) -> bool:
    """Delete an API key."""
    conn = _get_conn()
    provider = provider.lower()
    existing = conn.execute("SELECT id FROM api_keys WHERE provider = ?", [provider]).fetchone()
    if existing is None:
        return False
    conn.execute("DELETE FROM api_keys WHERE provider = ?", [provider])
    return True


# ── Server Config ────────────────────────────────────────────────────────────


def get_server_config() -> dict:
    """Get the server configuration (singleton row)."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT host, port, cors_origins, auth_mode, active_domain,"
        " auth_secret, auth_algorithm, oauth_providers_json"
        " FROM server_config WHERE id = 1"
    ).fetchone()
    if row is None:
        return {
            "host": "0.0.0.0", "port": 3717, "cors_origins": ["*"],
            "auth_mode": "dev", "active_domain": None,
            "auth_secret": None, "auth_algorithm": "HS256",
            "oauth_providers_json": [],
        }
    try:
        cors = json.loads(row[2]) if row[2] else ["*"]
    except (json.JSONDecodeError, TypeError):
        cors = ["*"]
    try:
        oauth_providers = json.loads(row[7]) if row[7] else []
    except (json.JSONDecodeError, TypeError):
        oauth_providers = []
    return {
        "host": row[0] or "0.0.0.0",
        "port": row[1] or 3717,
        "cors_origins": cors,
        "auth_mode": row[3] or "dev",
        "active_domain": row[4],
        "auth_secret": row[5],
        "auth_algorithm": row[6] or "HS256",
        "oauth_providers": oauth_providers,
    }


def update_server_config(**kwargs: Any) -> None:
    """Update server config fields."""
    conn = _get_conn()
    allowed = {
        "host", "port", "cors_origins", "auth_mode", "active_domain",
        "auth_secret", "auth_algorithm", "oauth_providers_json",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return
    # Serialize cors_origins if it's a list
    if "cors_origins" in updates and isinstance(updates["cors_origins"], list):
        updates["cors_origins"] = json.dumps(updates["cors_origins"])
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values())
    conn.execute(f"UPDATE server_config SET {set_clause} WHERE id = 1", values)


def get_active_domain() -> str | None:
    """Get the currently active domain name."""
    return get_server_config()["active_domain"]


def set_active_domain(domain_name: str) -> None:
    """Set the active domain."""
    update_server_config(active_domain=domain_name)


# ── Users CRUD ────────────────────────────────────────────────────────────────


def list_users() -> list[dict]:
    """List all users."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, email, name, avatar_url, oauth_provider, oauth_sub,"
        " roles_json, is_active, created_at, last_login_at"
        " FROM users ORDER BY id"
    ).fetchall()
    return [_user_row_to_dict(r) for r in rows]


def get_user_by_id(user_id: int) -> dict | None:
    """Get a user by internal ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, email, name, avatar_url, oauth_provider, oauth_sub,"
        " roles_json, is_active, created_at, last_login_at"
        " FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return _user_row_to_dict(row) if row else None


def get_user_by_oauth(provider: str, sub: str) -> dict | None:
    """Get a user by OAuth provider and subject ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, email, name, avatar_url, oauth_provider, oauth_sub,"
        " roles_json, is_active, created_at, last_login_at"
        " FROM users WHERE oauth_provider = ? AND oauth_sub = ?",
        (provider, sub),
    ).fetchone()
    return _user_row_to_dict(row) if row else None


def upsert_user(
    email: str,
    name: str | None,
    avatar_url: str | None,
    oauth_provider: str,
    oauth_sub: str,
) -> dict:
    """Create or update a user from OAuth login. Returns the user dict."""
    conn = _get_conn()
    now = _now()
    existing = get_user_by_oauth(oauth_provider, oauth_sub)
    if existing:
        conn.execute(
            "UPDATE users SET email = ?, name = ?, avatar_url = ?, last_login_at = ?"
            " WHERE id = ?",
            (email, name, avatar_url, now, existing["id"]),
        )
        existing.update(email=email, name=name, avatar_url=avatar_url, last_login_at=now)
        return existing

    conn.execute(
        "INSERT INTO users (email, name, avatar_url, oauth_provider, oauth_sub,"
        " roles_json, is_active, created_at, last_login_at)"
        " VALUES (?, ?, ?, ?, ?, '[]', TRUE, ?, ?)",
        (email, name, avatar_url, oauth_provider, oauth_sub, now, now),
    )
    return get_user_by_oauth(oauth_provider, oauth_sub)  # type: ignore[return-value]


def update_user_roles(user_id: int, roles: list[str]) -> bool:
    """Update the roles assigned to a user."""
    conn = _get_conn()
    cur = conn.execute(
        "UPDATE users SET roles_json = ? WHERE id = ?",
        (json.dumps(roles), user_id),
    )
    return cur.rowcount > 0


def deactivate_user(user_id: int, active: bool = False) -> bool:
    """Activate or deactivate a user."""
    conn = _get_conn()
    cur = conn.execute(
        "UPDATE users SET is_active = ? WHERE id = ?",
        (active, user_id),
    )
    return cur.rowcount > 0


def count_users() -> int:
    """Count total registered users."""
    conn = _get_conn()
    row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    return row[0] if row else 0


def _user_row_to_dict(row: tuple) -> dict:
    """Convert a users table row tuple to a dict."""
    try:
        roles = json.loads(row[6]) if row[6] else []
    except (json.JSONDecodeError, TypeError):
        roles = []
    return {
        "id": row[0],
        "email": row[1],
        "name": row[2],
        "avatar_url": row[3],
        "oauth_provider": row[4],
        "oauth_sub": row[5],
        "roles": roles,
        "is_active": bool(row[7]),
        "created_at": row[8],
        "last_login_at": row[9],
    }


# ── Invites ────────────────────────────────────────────────────────────────


def invite_email(email: str, invited_by: int | None = None, roles: list[str] | None = None) -> dict:
    """Invite an email address. Returns the invite dict."""
    conn = _get_conn()
    now = _now()
    roles_json = json.dumps(roles or [])
    conn.execute(
        "INSERT OR IGNORE INTO invited_emails (email, invited_by, roles_json, created_at)"
        " VALUES (?, ?, ?, ?)",
        (email.lower().strip(), invited_by, roles_json, now),
    )
    return get_invite_by_email(email) or {"email": email}


def revoke_invite(email: str) -> bool:
    """Remove an email from the invite list."""
    conn = _get_conn()
    cur = conn.execute("DELETE FROM invited_emails WHERE email = ?", (email.lower().strip(),))
    return cur.rowcount > 0


def list_invites() -> list[dict]:
    """List all invited emails."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, email, invited_by, roles_json, created_at FROM invited_emails ORDER BY created_at DESC"
    ).fetchall()
    return [_invite_row_to_dict(r) for r in rows]


def get_invite_by_email(email: str) -> dict | None:
    """Look up an invite by email."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, email, invited_by, roles_json, created_at FROM invited_emails WHERE email = ?",
        (email.lower().strip(),),
    ).fetchone()
    return _invite_row_to_dict(row) if row else None


def is_email_invited(email: str) -> bool:
    """Check if an email is on the invite list."""
    return get_invite_by_email(email) is not None


def _invite_row_to_dict(row: tuple) -> dict:
    try:
        roles = json.loads(row[3]) if row[3] else []
    except (json.JSONDecodeError, TypeError):
        roles = []
    return {
        "id": row[0],
        "email": row[1],
        "invited_by": row[2],
        "roles": roles,
        "created_at": row[4],
    }


# ── Chat Threads ────────────────────────────────────────────────────────────


def create_thread(user_id: int, title: str | None = None, domain: str | None = None) -> dict:
    conn = _get_conn()
    now = _now()
    thread_id = conn.insert_returning_id(
        "INSERT INTO chat_threads (user_id, title, domain, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, title, domain, now, now),
    )
    return {"id": thread_id, "user_id": user_id, "title": title, "domain": domain,
            "is_archived": False, "created_at": now, "updated_at": now}


def list_threads(user_id: int, include_archived: bool = False) -> list[dict]:
    conn = _get_conn()
    sql = "SELECT id, user_id, title, domain, is_archived, created_at, updated_at FROM chat_threads WHERE user_id = ?"
    params: list = [user_id]
    if not include_archived:
        sql += " AND is_archived = FALSE"
    sql += " ORDER BY updated_at DESC"
    rows = conn.execute(sql, params).fetchall()
    return [_thread_row_to_dict(r) for r in rows]


def get_thread(thread_id: int, user_id: int) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, user_id, title, domain, is_archived, created_at, updated_at "
        "FROM chat_threads WHERE id = ? AND user_id = ?",
        (thread_id, user_id),
    ).fetchone()
    return _thread_row_to_dict(row) if row else None


def update_thread(thread_id: int, user_id: int, **kwargs: str | bool) -> dict | None:
    conn = _get_conn()
    allowed = {"title", "is_archived"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_thread(thread_id, user_id)
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE chat_threads SET {set_clause} WHERE id = ? AND user_id = ?",
        [*updates.values(), thread_id, user_id],
    )
    return get_thread(thread_id, user_id)


def delete_thread(thread_id: int, user_id: int) -> bool:
    conn = _get_conn()
    conn.execute("DELETE FROM chat_messages WHERE thread_id = ? AND thread_id IN "
                 "(SELECT id FROM chat_threads WHERE user_id = ?)", (thread_id, user_id))
    cursor = conn.execute("DELETE FROM chat_threads WHERE id = ? AND user_id = ?", (thread_id, user_id))
    return cursor.rowcount > 0


# ── Chat Messages ───────────────────────────────────────────────────────────


def add_message(thread_id: int, role: str, content: str, metadata: dict | None = None) -> dict:
    conn = _get_conn()
    now = _now()
    meta_json = json.dumps(metadata) if metadata else "{}"
    msg_id = conn.insert_returning_id(
        "INSERT INTO chat_messages (thread_id, role, content, metadata_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (thread_id, role, content, meta_json, now),
    )
    conn.execute("UPDATE chat_threads SET updated_at = ? WHERE id = ?", (now, thread_id))
    return {"id": msg_id, "thread_id": thread_id, "role": role, "content": content,
            "metadata": metadata or {}, "created_at": now}


def get_messages(thread_id: int, limit: int = 100, offset: int = 0) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, thread_id, role, content, metadata_json, created_at "
        "FROM chat_messages WHERE thread_id = ? ORDER BY created_at ASC LIMIT ? OFFSET ?",
        (thread_id, limit, offset),
    ).fetchall()
    return [_message_row_to_dict(r) for r in rows]


def _thread_row_to_dict(row: tuple) -> dict:
    return {
        "id": row[0], "user_id": row[1], "title": row[2], "domain": row[3],
        "is_archived": bool(row[4]), "created_at": row[5], "updated_at": row[6],
    }


def _message_row_to_dict(row: tuple) -> dict:
    try:
        metadata = json.loads(row[4]) if row[4] else {}
    except (json.JSONDecodeError, TypeError):
        metadata = {}
    return {
        "id": row[0], "thread_id": row[1], "role": row[2], "content": row[3],
        "metadata": metadata, "created_at": row[5],
    }


# ── Business Ontology CRUD ───────────────────────────────────────────────────


def _bo_row_to_dict(row: tuple) -> dict:
    return {
        "id": row[0],
        "domain_id": row[1],
        "term": row[2],
        "definition": row[3],
        "sql_hint": row[4],
        "tags": json.loads(row[5]) if row[5] else [],
        "created_by": row[6],
        "created_at": row[7],
        "updated_at": row[8],
    }


_BO_COLS = "id, domain_id, term, definition, sql_hint, tags, created_by, created_at, updated_at"


def list_business_ontology(domain_id: int) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        f"SELECT {_BO_COLS} FROM business_ontology WHERE domain_id = ? ORDER BY term",
        [domain_id],
    ).fetchall()
    return [_bo_row_to_dict(r) for r in rows]


def get_business_ontology_entry(entry_id: int) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        f"SELECT {_BO_COLS} FROM business_ontology WHERE id = ?", [entry_id]
    ).fetchone()
    return _bo_row_to_dict(row) if row else None


def create_business_ontology_entry(
    domain_id: int,
    term: str,
    definition: str,
    sql_hint: str | None = None,
    tags: list[str] | None = None,
    created_by: int | None = None,
) -> dict:
    conn = _get_conn()
    now = _now()
    conn.execute(
        "INSERT INTO business_ontology (domain_id, term, definition, sql_hint, tags, created_by, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [domain_id, term, definition, sql_hint, json.dumps(tags or []), created_by, now, now],
    )
    row = conn.execute(
        f"SELECT {_BO_COLS} FROM business_ontology WHERE domain_id = ? AND term = ?",
        [domain_id, term],
    ).fetchone()
    return _bo_row_to_dict(row)


def update_business_ontology_entry(
    entry_id: int,
    term: str | None = None,
    definition: str | None = None,
    sql_hint: str | None = ...,
    tags: list[str] | None = ...,
) -> dict | None:
    conn = _get_conn()
    existing = get_business_ontology_entry(entry_id)
    if not existing:
        return None
    updates: list[str] = []
    params: list = []
    if term is not None:
        updates.append("term = ?")
        params.append(term)
    if definition is not None:
        updates.append("definition = ?")
        params.append(definition)
    if sql_hint is not ...:
        updates.append("sql_hint = ?")
        params.append(sql_hint)
    if tags is not ...:
        updates.append("tags = ?")
        params.append(json.dumps(tags if tags is not None else []))
    if not updates:
        return existing
    updates.append("updated_at = ?")
    params.append(_now())
    params.append(entry_id)
    conn.execute(
        f"UPDATE business_ontology SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    return get_business_ontology_entry(entry_id)


def delete_business_ontology_entry(entry_id: int) -> bool:
    conn = _get_conn()
    existing = get_business_ontology_entry(entry_id)
    if not existing:
        return False
    conn.execute("DELETE FROM business_ontology WHERE id = ?", [entry_id])
    return True


def lookup_business_ontology(domain_id: int, query: str) -> list[dict]:
    """Keyword-based lookup: match query terms against term names and tags."""
    all_entries = list_business_ontology(domain_id)
    if not all_entries:
        return []
    words = set(query.lower().split())
    scored: list[tuple[int, dict]] = []
    for entry in all_entries:
        score = 0
        term_lower = entry["term"].lower()
        definition_lower = entry["definition"].lower()
        tags_lower = [t.lower() for t in entry["tags"]]
        for w in words:
            if w in term_lower:
                score += 3
            if any(w in tag for tag in tags_lower):
                score += 2
            if w in definition_lower:
                score += 1
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:10]]


# ── OAuth Provider Config ────────────────────────────────────────────────────


def get_oauth_providers() -> list[dict]:
    """Get configured OAuth providers."""
    cfg = get_server_config()
    return cfg.get("oauth_providers", [])


def save_oauth_provider(provider: str, client_id: str, client_secret: str, enabled: bool = True) -> None:
    """Add or update an OAuth provider configuration."""
    providers = get_oauth_providers()
    updated = False
    for p in providers:
        if p.get("provider") == provider:
            p["client_id"] = client_id
            p["client_secret"] = client_secret
            p["enabled"] = enabled
            updated = True
            break
    if not updated:
        providers.append({
            "provider": provider,
            "client_id": client_id,
            "client_secret": client_secret,
            "enabled": enabled,
        })
    update_server_config(oauth_providers_json=json.dumps(providers))


def delete_oauth_provider(provider: str) -> bool:
    """Remove an OAuth provider configuration."""
    providers = get_oauth_providers()
    filtered = [p for p in providers if p.get("provider") != provider]
    if len(filtered) == len(providers):
        return False
    update_server_config(oauth_providers_json=json.dumps(filtered))
    return True


# ── Cloud Drive Config ────────────────────────────────────────────────────────


CLOUD_DRIVE_TYPES = {"google_drive", "onedrive", "dropbox"}


def get_cloud_drive_credentials(connector_id: int) -> dict | None:
    """Extract cloud drive credentials from a connector's credentials JSON."""
    c = get_connector_by_id(connector_id)
    if not c or c["type"] not in CLOUD_DRIVE_TYPES:
        return None
    creds = c.get("credentials")
    if not creds:
        return None
    parsed = json.loads(creds) if isinstance(creds, str) else creds
    return {
        "provider": c["type"],
        "client_id": parsed["client_id"],
        "client_secret": parsed["client_secret"],
        "connector_id": connector_id,
    }


def list_cloud_drive_connectors() -> list[dict]:
    """List all connectors that are cloud drive types."""
    conn = _get_conn()
    placeholders = ",".join("?" for _ in CLOUD_DRIVE_TYPES)
    rows = conn.execute(
        f"SELECT id, name, type, credentials, created_at FROM connectors "
        f"WHERE type IN ({placeholders}) ORDER BY name",
        list(CLOUD_DRIVE_TYPES),
    ).fetchall()
    result = []
    for r in rows:
        creds = json.loads(r[3]) if r[3] else {}
        result.append({
            "id": r[0],
            "name": r[1],
            "type": r[2],
            "client_id": creds.get("client_id", ""),
            "created_at": r[4],
        })
    return result


# ── Cloud Drive Accounts ─────────────────────────────────────────────────────


def save_cloud_drive_account(
    connector_id: int,
    email: str,
    display_name: str | None,
    access_token: str,
    refresh_token: str,
    token_expires_at: str | None = None,
) -> int:
    """Save or update a connected cloud drive account."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id FROM cloud_drive_accounts "
        "WHERE connector_id = ? AND email = ?",
        [connector_id, email],
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE cloud_drive_accounts SET "
            "display_name = ?, access_token = ?, refresh_token = ?, "
            "token_expires_at = ? WHERE id = ?",
            [display_name, access_token, refresh_token, token_expires_at, row[0]],
        )
        return row[0]
    return conn.insert_returning_id(
        "INSERT INTO cloud_drive_accounts "
        "(connector_id, email, display_name, access_token, refresh_token, "
        "token_expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [connector_id, email, display_name, access_token, refresh_token,
         token_expires_at, _now()],
    )


def get_cloud_drive_account(account_id: int) -> dict | None:
    """Get a cloud drive account by ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, connector_id, email, display_name, access_token, "
        "refresh_token, token_expires_at, created_at "
        "FROM cloud_drive_accounts WHERE id = ?",
        [account_id],
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "connector_id": row[1],
        "email": row[2],
        "display_name": row[3],
        "access_token": row[4],
        "refresh_token": row[5],
        "token_expires_at": row[6],
        "created_at": row[7],
    }


def list_cloud_drive_accounts(connector_id: int | None = None) -> list[dict]:
    """List connected cloud drive accounts, optionally filtered by connector."""
    conn = _get_conn()
    if connector_id is not None:
        rows = conn.execute(
            "SELECT a.id, a.connector_id, c.type as provider, a.email, "
            "a.display_name, a.access_token, a.refresh_token, "
            "a.token_expires_at, a.created_at "
            "FROM cloud_drive_accounts a "
            "JOIN connectors c ON a.connector_id = c.id "
            "WHERE a.connector_id = ? ORDER BY a.created_at DESC",
            [connector_id],
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT a.id, a.connector_id, c.type as provider, a.email, "
            "a.display_name, a.access_token, a.refresh_token, "
            "a.token_expires_at, a.created_at "
            "FROM cloud_drive_accounts a "
            "JOIN connectors c ON a.connector_id = c.id "
            "ORDER BY a.created_at DESC",
        ).fetchall()
    return [
        {
            "id": r[0],
            "connector_id": r[1],
            "provider": r[2],
            "email": r[3],
            "display_name": r[4],
            "access_token": r[5],
            "refresh_token": r[6],
            "token_expires_at": r[7],
            "created_at": r[8],
        }
        for r in rows
    ]


def update_cloud_drive_tokens(
    account_id: int,
    access_token: str,
    refresh_token: str | None = None,
    token_expires_at: str | None = None,
) -> None:
    """Update OAuth tokens for a cloud drive account after refresh."""
    conn = _get_conn()
    if refresh_token is not None:
        conn.execute(
            "UPDATE cloud_drive_accounts SET "
            "access_token = ?, refresh_token = ?, token_expires_at = ? "
            "WHERE id = ?",
            [access_token, refresh_token, token_expires_at, account_id],
        )
    else:
        conn.execute(
            "UPDATE cloud_drive_accounts SET "
            "access_token = ?, token_expires_at = ? WHERE id = ?",
            [access_token, token_expires_at, account_id],
        )


def delete_cloud_drive_account(account_id: int) -> bool:
    """Remove a connected cloud drive account."""
    conn = _get_conn()
    cur = conn.execute(
        "DELETE FROM cloud_drive_accounts WHERE id = ?", [account_id]
    )
    return cur.rowcount > 0


# ── Legacy migration ─────────────────────────────────────────────────────────


def _migrate_from_legacy(conn: _DbAdapter) -> None:
    """Migrate from nexaql.yaml + api_keys.json + connectors.json if they exist.

    Only runs if the bootstrap DB is empty (no connectors, no domains, no llm_config).
    """
    # Check if bootstrap DB already has data
    has_data = False
    for table in ["connectors", "domains", "llm_config", "api_keys"]:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        if row and row[0] > 0:
            has_data = True
            break

    if has_data:
        return  # Already migrated or manually configured

    log.info("Bootstrap DB is empty — checking for legacy config files to migrate...")

    # Try to find config files in CWD or common locations
    cwd = os.getcwd()

    # 1. Migrate api_keys.json
    for path in [os.path.join(cwd, "api_keys.json")]:
        if os.path.exists(path):
            try:
                import json as _json
                with open(path) as f:
                    keys = _json.load(f)
                for provider, data in keys.items():
                    if isinstance(data, dict) and "key" in data:
                        conn.execute(
                            "INSERT OR IGNORE INTO api_keys (provider, name, key, created_at) VALUES (?, ?, ?, ?)",
                            [provider.lower(), data.get("name", provider), data["key"], _now()],
                        )
                log.info(f"Migrated {len(keys)} API keys from {path}")
            except Exception as e:
                log.warning(f"Failed to migrate {path}: {e}")

    # 2. Migrate connectors.json
    for path in [os.path.join(cwd, "connectors.json")]:
        if os.path.exists(path):
            try:
                import json as _json
                with open(path) as f:
                    connectors_data = _json.load(f)
                if isinstance(connectors_data, list):
                    for c in connectors_data:
                        conn.execute(
                            "INSERT OR IGNORE INTO connectors (name, type, url, created_at) VALUES (?, ?, ?, ?)",
                            [c.get("name", "default"), c.get("type", "postgresql"), c.get("url", ""), _now()],
                        )
                    log.info(f"Migrated {len(connectors_data)} connectors from {path}")
            except Exception as e:
                log.warning(f"Failed to migrate {path}: {e}")

    # 3. Migrate nexaql.yaml
    for path in [os.path.join(cwd, "nexaql.yaml")]:
        if os.path.exists(path):
            try:
                import yaml
                with open(path) as f:
                    cfg = yaml.safe_load(f) or {}

                # LLM config
                llm = cfg.get("llm", {})
                if llm.get("provider"):
                    provider = llm["provider"]
                    model = llm.get("model", "")
                    # Don't migrate ${ENV_VAR} references as literal strings
                    api_key_val = llm.get("api_key", "")
                    if api_key_val and not api_key_val.startswith("${"):
                        conn.execute(
                            "INSERT OR IGNORE INTO api_keys (provider, name, key, created_at) VALUES (?, ?, ?, ?)",
                            [provider, provider, api_key_val, _now()],
                        )
                    conn.execute(
                        "INSERT INTO llm_config (provider, model, max_tokens, summary_max_tokens, generation_mode, is_active) "
                        "VALUES (?, ?, ?, ?, ?, TRUE)",
                        [provider, model, llm.get("max_tokens", 4096),
                         llm.get("summary_max_tokens", 2048), llm.get("generation_mode", "intent")],
                    )

                # Server config
                server = cfg.get("server", {})
                if server:
                    cors = server.get("cors_origins", ["*"])
                    conn.execute(
                        "UPDATE server_config SET host = ?, port = ?, cors_origins = ? WHERE id = 1",
                        [server.get("host", "0.0.0.0"), server.get("port", 3717), json.dumps(cors)],
                    )

                # Active domain
                ont_cfg = cfg.get("ontology", {})
                domain = ont_cfg.get("domain")
                if domain:
                    conn.execute("UPDATE server_config SET active_domain = ? WHERE id = 1", [domain])

                # Datasource -> connector
                for ds_name, ds in cfg.get("datasources", {}).items():
                    ds_type = ds.get("type", "postgresql")
                    ds_url = ds.get("url") or ds.get("path", "")
                    conn.execute(
                        "INSERT OR IGNORE INTO connectors (name, type, url, created_at) VALUES (?, ?, ?, ?)",
                        [ds_name, ds_type, ds_url, _now()],
                    )

                log.info(f"Migrated config from {path}")
            except Exception as e:
                log.warning(f"Failed to migrate {path}: {e}")


# ── Seed bundled ontology files ──────────────────────────────────────────────


def _seed_ontology_files(conn: _DbAdapter) -> None:
    """Seed bundled YAML ontology files into the bootstrap DB on first run.

    Only runs if the domains table is empty (no domains exist yet).
    Scans for YAML files in:
      1. src/nexaql/data/*.yaml  (bundled with the package)
      2. ontologies/*.yaml       (local project dir)

    Creates a placeholder "sample" connector so the FK constraint on
    schemas.connector_id is satisfied.  Sets the first seeded domain
    as the active domain.

    If a support.yaml is found, also creates a PostgreSQL connector and
    seeds the support_tickets table for cross-datasource federation demo.
    """
    row = conn.execute("SELECT COUNT(*) FROM domains").fetchone()
    if row and row[0] > 0:
        return  # Domains already exist — nothing to seed

    yaml_files = _discover_ontology_yamls()
    if not yaml_files:
        return

    log.info("Seeding %d bundled ontology file(s) into bootstrap DB...", len(yaml_files))

    # Ensure a placeholder connector exists for sample ontologies
    sample_connector_id = _ensure_sample_connector(conn)

    first_domain: str | None = None

    for path in yaml_files:
        try:
            domain_name, description, ontology_json = _parse_ontology_yaml(path)
        except Exception as e:
            log.warning("Skipping %s: %s", path, e)
            continue

        ont_data = json.loads(ontology_json) if isinstance(ontology_json, str) else ontology_json

        # Extract roles and access_functions for domain level
        roles_json = None
        access_functions_json = None
        if ont_data.get("roles"):
            roles_json = json.dumps(ont_data["roles"])
        if ont_data.get("access_functions"):
            access_functions_json = json.dumps(ont_data["access_functions"])

        # Create domain with roles/access at domain level
        now = _now()
        conn.execute(
            "INSERT OR IGNORE INTO domains (name, description, roles_json, access_functions_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [domain_name, description, roles_json, access_functions_json, now],
        )
        domain_row = conn.execute(
            "SELECT id FROM domains WHERE name = ?", [domain_name]
        ).fetchone()
        domain_id = domain_row[0]

        # Create one schema per node/table
        nodes = ont_data.get("nodes", {})
        for node_name, node_def in nodes.items():
            single_node_ont = {
                "domain": domain_name,
                "nodes": {node_name: node_def},
            }
            conn.execute(
                "INSERT OR IGNORE INTO schemas "
                "(domain_id, connector_id, name, ontology_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [domain_id, sample_connector_id, node_name, json.dumps(single_node_ont), now, now],
            )

        if first_domain is None:
            first_domain = domain_name

        log.info("Seeded domain '%s' with %d per-table schemas from %s", domain_name, len(nodes), path)

    # Set the first seeded domain as active (if none is set)
    if first_domain:
        active = conn.execute(
            "SELECT active_domain FROM server_config WHERE id = 1"
        ).fetchone()
        if not active or not active[0]:
            conn.execute(
                "UPDATE server_config SET active_domain = ? WHERE id = 1",
                [first_domain],
            )
            log.info("Set active domain to '%s'", first_domain)

    # After domains are seeded, try to set up the PostgreSQL support connector
    _ensure_support_connector(conn)


def _discover_ontology_yamls() -> list[str]:
    """Find bundled and local ontology YAML files to seed."""
    import glob

    yamls: list[str] = []

    # 1. Bundled with the package: src/nexaql/data/*.yaml
    pkg_data_dir = os.path.join(os.path.dirname(__file__), "data")
    if os.path.isdir(pkg_data_dir):
        for f in sorted(glob.glob(os.path.join(pkg_data_dir, "*.yaml"))):
            yamls.append(f)

    # 2. Local project: ontologies/*.yaml (relative to CWD)
    #    Only add files whose domain isn't already covered by pkg data.
    ont_dir = os.path.join(os.getcwd(), "ontologies")
    if os.path.isdir(ont_dir):
        seen_domains: set[str] = set()
        for f in yamls:
            try:
                import yaml as _yaml
                with open(f) as fh:
                    d = _yaml.safe_load(fh)
                if isinstance(d, dict) and d.get("domain"):
                    seen_domains.add(d["domain"])
            except Exception:
                pass

        for f in sorted(glob.glob(os.path.join(ont_dir, "*.yaml"))):
            try:
                import yaml as _yaml
                with open(f) as fh:
                    d = _yaml.safe_load(fh)
                if isinstance(d, dict) and d.get("domain") in seen_domains:
                    continue  # Same domain already covered by pkg data
            except Exception:
                pass
            yamls.append(f)

    return yamls


def _parse_ontology_yaml(path: str) -> tuple[str, str, str]:
    """Parse a YAML ontology file and return (domain_name, description, ontology_json).

    Raises ValueError if the file doesn't contain a valid ontology.
    """
    import yaml

    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("Not a valid YAML dict")

    domain = data.get("domain")
    if not domain:
        raise ValueError("Missing 'domain' key")

    description = data.get("description", "").strip()

    # Store the full ontology as JSON
    ontology_json = json.dumps(data, default=str)

    return domain, description, ontology_json


def _ensure_sample_connector(conn: _DbAdapter) -> int:
    """Create or return the 'sample' connector backed by a real DuckDB data file.

    The data file lives at ``~/.nexaql/sample_ecommerce.duckdb`` and is
    populated from the bundled seed SQL (``src/nexaql/data/sample_ecommerce_seed.sql``).
    """
    row = conn.execute(
        "SELECT id FROM connectors WHERE name = 'sample'"
    ).fetchone()
    if row:
        return row[0]

    # Create the sample DuckDB data file and seed it
    sample_db_path = _seed_sample_data()

    conn.execute(
        "INSERT INTO connectors (name, type, url, created_at) VALUES (?, ?, ?, ?)",
        ["sample", "duckdb", sample_db_path, _now()],
    )
    row = conn.execute("SELECT id FROM connectors WHERE name = 'sample'").fetchone()
    return row[0]


def _ensure_support_connector(conn: _DbAdapter) -> int | None:
    """Create or return the 'support_postgres' connector for the support tickets DB.

    Seeds the PostgreSQL database with support_tickets data if available.
    Also creates the support ontology schema and patches ecommerce nodes
    with reverse edges to support_ticket.
    Returns None if PostgreSQL is not available.
    """
    row = conn.execute(
        "SELECT id FROM connectors WHERE name = 'support_postgres'"
    ).fetchone()
    if row:
        return row[0]

    pg_url = _get_support_pg_url()
    if pg_url is None:
        log.info("PostgreSQL not available — skipping support connector")
        return None

    _seed_support_data(pg_url)

    conn.execute(
        "INSERT INTO connectors (name, type, url, created_at) VALUES (?, ?, ?, ?)",
        ["support_postgres", "postgresql", pg_url, _now()],
    )
    row = conn.execute("SELECT id FROM connectors WHERE name = 'support_postgres'").fetchone()
    connector_id = row[0]
    log.info("Created 'support_postgres' connector (id=%d)", connector_id)

    _seed_support_ontology(conn, connector_id)

    return connector_id


def _seed_support_ontology(conn: _DbAdapter, connector_id: int) -> None:
    """Create the support ontology schema and patch ecommerce nodes with reverse edges."""
    support_ontology = {
        "version": "1",
        "domain": "ecommerce",
        "description": "Customer support tickets in PostgreSQL, linked to ecommerce data.",
        "nodes": {
            "support_ticket": {
                "table": "support_tickets",
                "description": "Customer support tickets linked to orders and customers.",
                "primary_key": "id",
                "fields": {
                    "id": {"type": "integer", "description": "Unique ticket identifier.", "filterable": True},
                    "ticket_number": {"type": "string", "description": "Human-readable ticket number.", "filterable": True},
                    "customer_id": {"type": "integer", "description": "FK to customers.", "filterable": True},
                    "order_id": {"type": "integer", "description": "FK to orders.", "filterable": True},
                    "order_item_id": {"type": "integer", "description": "FK to order_items.", "filterable": True},
                    "subject": {"type": "string", "description": "Ticket subject line.", "filterable": True},
                    "description": {"type": "string", "description": "Detailed description of the issue."},
                    "status": {
                        "type": "enum", "description": "Current ticket status.", "filterable": True,
                        "values": ["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"],
                    },
                    "priority": {
                        "type": "enum", "description": "Ticket priority level.", "filterable": True,
                        "values": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                    },
                    "category": {
                        "type": "enum", "description": "Issue category.", "filterable": True,
                        "values": ["PRODUCT_DEFECT", "SHIPPING", "BILLING", "REFUND", "WRONG_ITEM", "MISSING_PARTS", "EXCHANGE"],
                    },
                    "channel": {
                        "type": "enum", "description": "Channel through which the ticket was created.", "filterable": True,
                        "values": ["EMAIL", "PHONE", "CHAT"],
                    },
                    "assigned_to": {"type": "string", "description": "Support agent handling the ticket.", "filterable": True},
                    "satisfaction": {"type": "integer", "description": "Customer satisfaction score (1-5).", "filterable": True},
                    "created_at": {"type": "date", "description": "When the ticket was created.", "filterable": True},
                    "updated_at": {"type": "date", "description": "When the ticket was last updated.", "filterable": True},
                    "resolved_at": {"type": "date", "description": "When the ticket was resolved.", "filterable": True},
                },
                "edges": {
                    "customer": {
                        "node": "customer",
                        "description": "The customer who filed this ticket.",
                        "join_steps": [{"table": "customers", "alias_key": "customer", "condition": "{customer}.id = {support_ticket}.customer_id"}],
                    },
                    "order": {
                        "node": "order",
                        "description": "The order related to this ticket.",
                        "join_type": "LEFT",
                        "join_steps": [{"table": "orders", "alias_key": "order", "condition": "{order}.id = {support_ticket}.order_id"}],
                    },
                    "order_item": {
                        "node": "order_item",
                        "description": "The specific order item related to this ticket.",
                        "join_type": "LEFT",
                        "join_steps": [{"table": "order_items", "alias_key": "order_item", "condition": "{order_item}.id = {support_ticket}.order_item_id"}],
                    },
                },
                "special_filters": {
                    "unresolved": {
                        "description": "Only open or in-progress tickets.",
                        "sql": "{support_ticket}.status IN ('OPEN', 'IN_PROGRESS')",
                    },
                    "high_priority": {
                        "description": "Only HIGH or CRITICAL priority tickets.",
                        "sql": "{support_ticket}.priority IN ('HIGH', 'CRITICAL')",
                    },
                },
                "visible_to": ["analyst", "manager", "admin"],
            },
        },
    }

    domain = get_domain("ecommerce")
    if domain is None:
        log.warning("ecommerce domain not found — cannot seed support ontology")
        return

    now = _now()
    # Per-table schema: one schema named "support_ticket" with one node
    single_node_ont = {
        "domain": "ecommerce",
        "nodes": {"support_ticket": support_ontology["nodes"]["support_ticket"]},
    }
    conn.execute(
        "INSERT OR IGNORE INTO schemas "
        "(domain_id, connector_id, name, ontology_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [domain["id"], connector_id, "support_ticket", json.dumps(single_node_ont, default=str), now, now],
    )
    log.info("Seeded 'support_ticket' per-table schema in ecommerce domain")

    _patch_ecommerce_edges(conn, domain["id"])


def _patch_ecommerce_edges(conn: _DbAdapter, domain_id: int) -> None:
    """Add support_tickets edges to customer and order per-table schemas."""
    now = _now()

    edge_patches = [
        ("customer", {
            "node": "support_ticket",
            "description": "Support tickets filed by this customer.",
            "join_type": "LEFT",
            "join_steps": [{"table": "support_tickets", "alias_key": "support_ticket", "condition": "{support_ticket}.customer_id = {customer}.id"}],
        }),
        ("order", {
            "node": "support_ticket",
            "description": "Support tickets related to this order.",
            "join_type": "LEFT",
            "join_steps": [{"table": "support_tickets", "alias_key": "support_ticket", "condition": "{support_ticket}.order_id = {order}.id"}],
        }),
    ]

    for node_name, edge_def in edge_patches:
        row = conn.execute(
            "SELECT id, ontology_json FROM schemas WHERE domain_id = ? AND name = ?",
            [domain_id, node_name],
        ).fetchone()
        if row is None:
            continue

        schema_id = row[0]
        try:
            ont = json.loads(row[1]) if isinstance(row[1], str) else row[1]
        except (json.JSONDecodeError, TypeError):
            continue

        node_def = ont.get("nodes", {}).get(node_name)
        if node_def is None:
            continue

        edges = node_def.get("edges", {})
        if "support_tickets" not in edges:
            edges["support_tickets"] = edge_def
            node_def["edges"] = edges
            conn.execute(
                "UPDATE schemas SET ontology_json = ?, updated_at = ? WHERE id = ?",
                [json.dumps(ont, default=str), now, schema_id],
            )
            log.info("Patched '%s' schema with support_tickets edge", node_name)


def _get_support_pg_url() -> str | None:
    """Check if PostgreSQL is available and return a connection URL.

    Tries to connect to local PostgreSQL with the nexaql_support database.
    Returns None if PostgreSQL is not reachable.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["pg_isready", "-h", "localhost", "-p", "5432"],
            capture_output=True, timeout=5,
        )
        if result.returncode != 0:
            return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    # Ensure the nexaql_support database exists
    try:
        result = subprocess.run(
            ["createdb", "nexaql_support"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass  # database may already exist

    return "postgresql://localhost:5432/nexaql_support"


def _seed_support_data(pg_url: str) -> None:
    """Seed the support_tickets table into PostgreSQL."""
    seed_sql_path = os.path.join(os.path.dirname(__file__), "data", "sample_support_seed.sql")
    if not os.path.exists(seed_sql_path):
        log.warning("Support seed SQL not found at %s", seed_sql_path)
        return

    try:
        import asyncio
        import asyncpg

        async def _run_seed():
            conn = await asyncpg.connect(pg_url)
            try:
                # Check if table already has data
                try:
                    count = await conn.fetchval("SELECT COUNT(*) FROM support_tickets")
                    if count and count > 0:
                        log.info("support_tickets already seeded (%d rows)", count)
                        return
                except asyncpg.exceptions.UndefinedTableError:
                    pass  # table doesn't exist yet

                with open(seed_sql_path) as f:
                    sql = f.read()
                await conn.execute(sql)
                count = await conn.fetchval("SELECT COUNT(*) FROM support_tickets")
                log.info("Seeded support_tickets with %d rows", count or 0)
            finally:
                await conn.close()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                executor.submit(lambda: asyncio.run(_run_seed())).result()
        else:
            asyncio.run(_run_seed())

    except Exception as e:
        log.warning("Failed to seed support data: %s", e)


def _seed_sample_data() -> str:
    """Create and populate the sample ecommerce DuckDB data file.

    Returns the absolute path to the data file.
    """
    db_dir = os.path.dirname(_get_db_path())
    sample_db = os.path.join(db_dir, "sample_ecommerce.duckdb")

    # Find seed SQL
    seed_sql_path = os.path.join(os.path.dirname(__file__), "data", "sample_ecommerce_seed.sql")
    if not os.path.exists(seed_sql_path):
        log.warning("Sample seed SQL not found at %s", seed_sql_path)
        return sample_db  # Return path anyway; adapter will just have empty DB

    # If the DB already exists (e.g. partial run), recreate it
    if os.path.exists(sample_db):
        return sample_db  # Already seeded

    log.info("Creating sample ecommerce data at %s", sample_db)
    try:
        import re

        import duckdb
        data_conn = duckdb.connect(sample_db)
        with open(seed_sql_path) as f:
            sql = f.read()
        # Strip full-line SQL comments before splitting on ';'
        cleaned = re.sub(r"^\s*--.*$", "", sql, flags=re.MULTILINE)
        for stmt in cleaned.split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    data_conn.execute(stmt)
                except Exception as e:
                    log.debug("Seed SQL statement skipped: %s", e)
        data_conn.close()
        log.info("Sample ecommerce data seeded successfully")
    except Exception as e:
        log.warning("Failed to seed sample data: %s", e)

    return sample_db
