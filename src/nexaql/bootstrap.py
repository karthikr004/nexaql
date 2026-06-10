# Copyright (c) 2026-present NexaQL Contributors
"""Bootstrap database — single DuckDB file that stores all NexaQL configuration.

Replaces nexaql.yaml, api_keys.json, and connectors.json with a proper
database at ``~/.nexaql/nexaql.db``.

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

log = logging.getLogger(__name__)

# ── Bootstrap DB path ─────────────────────────────────────────────────────────

_DEFAULT_DB_DIR = os.path.join(Path.home(), ".nexaql")
_DEFAULT_DB_PATH = os.path.join(_DEFAULT_DB_DIR, "nexaql.db")


def _get_db_path() -> str:
    """Get the bootstrap DB path. Override with NEXAQL_BOOTSTRAP_DB env var."""
    return os.environ.get("NEXAQL_BOOTSTRAP_DB", _DEFAULT_DB_PATH)


# ── Connection management ─────────────────────────────────────────────────────

_conn: duckdb.DuckDBPyConnection | None = None
_initialized: bool = False


def _get_conn() -> duckdb.DuckDBPyConnection:
    """Get or create the singleton DuckDB connection."""
    global _conn, _initialized
    if _conn is None:
        db_path = _get_db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        _conn = duckdb.connect(db_path)
        log.info(f"Bootstrap DB opened at {db_path}")
    if not _initialized:
        _ensure_tables(_conn)
        _initialized = True
    return _conn


def close() -> None:
    """Close the bootstrap DB connection."""
    global _conn, _initialized
    if _conn is not None:
        _conn.close()
        _conn = None
        _initialized = False


def _now() -> str:
    """UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat()


# ── DDL ───────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS connectors (
    id          INTEGER PRIMARY KEY DEFAULT nextval('seq_connectors'),
    name        TEXT UNIQUE NOT NULL,
    type        TEXT NOT NULL,
    url         TEXT,
    credentials TEXT,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS domains (
    id          INTEGER PRIMARY KEY DEFAULT nextval('seq_domains'),
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at  TEXT
);

CREATE TABLE IF NOT EXISTS schemas (
    id             INTEGER PRIMARY KEY DEFAULT nextval('seq_schemas'),
    domain_id      INTEGER NOT NULL REFERENCES domains(id),
    connector_id   INTEGER NOT NULL REFERENCES connectors(id),
    name           TEXT NOT NULL,
    ontology_json  TEXT NOT NULL,
    created_at     TEXT,
    updated_at     TEXT,
    UNIQUE(domain_id, name)
);

CREATE TABLE IF NOT EXISTS llm_config (
    id              INTEGER PRIMARY KEY DEFAULT nextval('seq_llm_config'),
    provider        TEXT NOT NULL DEFAULT '',
    model           TEXT NOT NULL DEFAULT '',
    max_tokens      INTEGER DEFAULT 4096,
    summary_max_tokens INTEGER DEFAULT 2048,
    generation_mode TEXT DEFAULT 'intent',
    is_active       BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS api_keys (
    id         INTEGER PRIMARY KEY DEFAULT nextval('seq_api_keys'),
    provider   TEXT UNIQUE NOT NULL,
    name       TEXT,
    key        TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS server_config (
    id            INTEGER PRIMARY KEY DEFAULT 1 CHECK(id = 1),
    host          TEXT DEFAULT '0.0.0.0',
    port          INTEGER DEFAULT 3717,
    cors_origins  TEXT DEFAULT '["*"]',
    auth_mode     TEXT DEFAULT 'dev',
    active_domain TEXT
);
"""


def _ensure_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create tables if they don't exist."""
    # Create sequences for auto-increment IDs
    for seq in ["seq_connectors", "seq_domains", "seq_schemas", "seq_llm_config", "seq_api_keys"]:
        try:
            conn.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START 1")
        except Exception:
            pass  # sequence already exists

    # Create tables
    for stmt in _DDL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except Exception as e:
                log.debug(f"DDL statement skipped: {e}")

    # Ensure server_config singleton row exists
    row = conn.execute("SELECT COUNT(*) FROM server_config").fetchone()
    if row and row[0] == 0:
        conn.execute("INSERT INTO server_config (id) VALUES (1)")

    # Attempt legacy migration on first init
    _migrate_from_legacy(conn)

    # Seed bundled / local ontology YAML files if no domains exist yet
    _seed_ontology_files(conn)


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
        "SELECT id, name, description, created_at FROM domains WHERE name = ?", [name]
    ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "description": row[2], "created_at": row[3]}


def create_domain(name: str, description: str = "") -> int:
    """Create a domain. Returns the domain ID."""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO domains (name, description, created_at) VALUES (?, ?, ?)",
        [name, description, _now()],
    )
    row = conn.execute("SELECT id FROM domains WHERE name = ?", [name]).fetchone()
    return row[0]


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

    # Upsert by (domain, schema_name)
    existing = get_schema(domain_name, schema_name)
    if existing:
        conn.execute(
            "UPDATE schemas SET connector_id = ?, ontology_json = ?, updated_at = ? "
            "WHERE id = ?",
            [connector_id, ontology_json, _now(), existing["id"]],
        )
        return existing["id"]
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

    # Collect top-level ontology metadata from the first schema that has it
    version = "1.0"
    roles: dict[str, Any] = {}
    access_functions: dict[str, Any] = {}
    for schema in schemas:
        try:
            ont_data = json.loads(schema["ontology_json"]) if isinstance(schema["ontology_json"], str) else schema["ontology_json"]
        except (json.JSONDecodeError, TypeError):
            continue
        if ont_data.get("version") and version == "1.0":
            version = str(ont_data["version"])
        if ont_data.get("roles") and not roles:
            roles = ont_data["roles"]
        if ont_data.get("access_functions") and not access_functions:
            access_functions = ont_data["access_functions"]

    domain = get_domain(domain_name)
    result: dict[str, Any] = {
        "domain": domain_name,
        "description": domain["description"] if domain else "",
        "nodes": merged_nodes,
        "node_to_connector": node_to_connector,
        "version": version,
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
        "SELECT host, port, cors_origins, auth_mode, active_domain FROM server_config WHERE id = 1"
    ).fetchone()
    if row is None:
        return {"host": "0.0.0.0", "port": 3717, "cors_origins": ["*"], "auth_mode": "dev", "active_domain": None}
    try:
        cors = json.loads(row[2]) if row[2] else ["*"]
    except (json.JSONDecodeError, TypeError):
        cors = ["*"]
    return {
        "host": row[0] or "0.0.0.0",
        "port": row[1] or 3717,
        "cors_origins": cors,
        "auth_mode": row[3] or "dev",
        "active_domain": row[4],
    }


def update_server_config(**kwargs: Any) -> None:
    """Update server config fields."""
    conn = _get_conn()
    allowed = {"host", "port", "cors_origins", "auth_mode", "active_domain"}
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


# ── Legacy migration ─────────────────────────────────────────────────────────


def _migrate_from_legacy(conn: duckdb.DuckDBPyConnection) -> None:
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


def _seed_ontology_files(conn: duckdb.DuckDBPyConnection) -> None:
    """Seed bundled YAML ontology files into the bootstrap DB on first run.

    Only runs if the domains table is empty (no domains exist yet).
    Scans for YAML files in:
      1. src/nexaql/data/*.yaml  (bundled with the package)
      2. ontologies/*.yaml       (local project dir)

    Creates a placeholder "sample" connector so the FK constraint on
    schemas.connector_id is satisfied.  Sets the first seeded domain
    as the active domain.
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

        # Create domain
        now = _now()
        conn.execute(
            "INSERT OR IGNORE INTO domains (name, description, created_at) VALUES (?, ?, ?)",
            [domain_name, description, now],
        )
        domain_row = conn.execute(
            "SELECT id FROM domains WHERE name = ?", [domain_name]
        ).fetchone()
        domain_id = domain_row[0]

        # Create schema (one schema per YAML file, named after the domain)
        schema_name = domain_name
        conn.execute(
            "INSERT OR IGNORE INTO schemas "
            "(domain_id, connector_id, name, ontology_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [domain_id, sample_connector_id, schema_name, ontology_json, now, now],
        )

        if first_domain is None:
            first_domain = domain_name

        log.info("Seeded domain '%s' from %s", domain_name, path)

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
        # Collect domains already found in pkg data to avoid duplicates
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


def _ensure_sample_connector(conn: duckdb.DuckDBPyConnection) -> int:
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
