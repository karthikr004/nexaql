# Copyright (c) 2026-present NexaQL Contributors
"""Ontology persistence — read, write, and modify ontologies.

Supports two backends:

* **YamlStore** — file-based (dev / OSS default). Same as before.
* **PostgresStore** — production-grade. Stores ontology as JSONB with
  version history, atomic updates, and partial-node modifications.

Usage::

    from nexaql.ontology.store import get_store

    store = get_store()                         # auto-detect from config
    ont = await store.load("my_domain")         # read
    await store.save(ont)                       # write (full replace)
    await store.update_node("my_domain", "customer", node)  # partial
    history = await store.list_versions("my_domain")        # audit trail
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

import yaml

from nexaql.ontology.models import Ontology, OntologyNode


# ── Abstract store interface ────────────────────────────────────────────────


class OntologyStore(ABC):
    """Backend-agnostic interface for ontology persistence."""

    @abstractmethod
    async def load(self, domain: str) -> Ontology:
        """Load the active ontology for a domain."""

    @abstractmethod
    async def save(self, ontology: Ontology, author: str = "system") -> dict[str, Any]:
        """Save a full ontology (creates a new version). Returns metadata."""

    @abstractmethod
    async def update_node(
        self, domain: str, node_name: str, node: OntologyNode, author: str = "system",
    ) -> Ontology:
        """Update a single node within the ontology. Returns updated ontology."""

    @abstractmethod
    async def delete_node(
        self, domain: str, node_name: str, author: str = "system",
    ) -> Ontology:
        """Delete a node from the ontology. Returns updated ontology."""

    @abstractmethod
    async def add_node(
        self, domain: str, node_name: str, node: OntologyNode, author: str = "system",
    ) -> Ontology:
        """Add a new node to the ontology. Returns updated ontology."""

    @abstractmethod
    async def list_domains(self) -> list[dict[str, Any]]:
        """List all available ontology domains."""

    @abstractmethod
    async def list_versions(self, domain: str, limit: int = 20) -> list[dict[str, Any]]:
        """List version history for a domain."""

    @abstractmethod
    async def load_version(self, domain: str, version_id: int) -> Ontology:
        """Load a specific historical version."""

    @abstractmethod
    async def delete_domain(self, domain: str) -> bool:
        """Delete all versions of a domain. Returns True if deleted."""


# ── Helper: serialize ontology to clean dict ────────────────────────────────


def _strip_empty(obj: Any) -> Any:
    """Recursively strip None values, empty dicts, and empty lists."""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            v = _strip_empty(v)
            if v is None or v == {} or v == []:
                continue
            cleaned[k] = v
        return cleaned
    if isinstance(obj, list):
        return [_strip_empty(item) for item in obj]
    return obj


def ontology_to_dict(ontology: Ontology) -> dict[str, Any]:
    """Serialize ontology to a clean dict (no None/empty values)."""
    return _strip_empty(ontology.model_dump(exclude_none=True))


# ── YAML Store (file-based, backward-compatible) ───────────────────────────


class YamlStore(OntologyStore):
    """File-based ontology store using YAML files.

    Maintains backward compatibility with existing NexaQL deployments.
    Version history is NOT supported — save always overwrites.
    """

    def __init__(self, ontology_dir: str = "ontologies"):
        self._dir = os.path.abspath(ontology_dir)
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, domain: str) -> str:
        return os.path.join(self._dir, f"{domain}.yaml")

    async def load(self, domain: str) -> Ontology:
        path = self._path(domain)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Ontology not found: {path}")
        with open(path) as f:
            raw = yaml.safe_load(f)
        return Ontology(**raw)

    async def save(self, ontology: Ontology, author: str = "system") -> dict[str, Any]:
        path = self._path(ontology.domain)
        data = ontology_to_dict(ontology)
        yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
        with open(path, "w") as f:
            f.write("# NexaQL Ontology — managed by NexaQL Admin\n")
            f.write(yaml_str)

        # Invalidate loader cache
        from nexaql.ontology.loader import invalidate_cache
        invalidate_cache(path)

        return {"path": path, "domain": ontology.domain, "version": 1}

    async def update_node(
        self, domain: str, node_name: str, node: OntologyNode, author: str = "system",
    ) -> Ontology:
        ont = await self.load(domain)
        ont.nodes[node_name] = node
        await self.save(ont, author)
        return ont

    async def delete_node(
        self, domain: str, node_name: str, author: str = "system",
    ) -> Ontology:
        ont = await self.load(domain)
        if node_name not in ont.nodes:
            raise KeyError(f"Node '{node_name}' not found in ontology '{domain}'")
        del ont.nodes[node_name]
        await self.save(ont, author)
        return ont

    async def add_node(
        self, domain: str, node_name: str, node: OntologyNode, author: str = "system",
    ) -> Ontology:
        ont = await self.load(domain)
        if node_name in ont.nodes:
            raise KeyError(f"Node '{node_name}' already exists in ontology '{domain}'")
        ont.nodes[node_name] = node
        await self.save(ont, author)
        return ont

    async def list_domains(self) -> list[dict[str, Any]]:
        domains = []
        for fname in sorted(os.listdir(self._dir)):
            if fname.endswith(".yaml") or fname.endswith(".yml"):
                domain = fname.rsplit(".", 1)[0]
                path = os.path.join(self._dir, fname)
                stat = os.stat(path)
                domains.append({
                    "domain": domain,
                    "backend": "yaml",
                    "path": path,
                    "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                })
        return domains

    async def list_versions(self, domain: str, limit: int = 20) -> list[dict[str, Any]]:
        # YAML store doesn't support versioning
        path = self._path(domain)
        if not os.path.exists(path):
            return []
        stat = os.stat(path)
        return [{
            "version_id": 1,
            "domain": domain,
            "author": "unknown",
            "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "note": "YAML store — no version history",
        }]

    async def load_version(self, domain: str, version_id: int) -> Ontology:
        return await self.load(domain)

    async def delete_domain(self, domain: str) -> bool:
        path = self._path(domain)
        if os.path.exists(path):
            os.remove(path)
            from nexaql.ontology.loader import invalidate_cache
            invalidate_cache(path)
            return True
        return False


# ── DuckDB Store (local / quick-start) ────────────────────────────────────────


DUCKDB_DDL = """
CREATE TABLE IF NOT EXISTS nexaql_ontologies (
    id              INTEGER PRIMARY KEY DEFAULT nextval('nexaql_ontologies_id_seq'),
    domain          TEXT NOT NULL,
    version_num     INTEGER NOT NULL DEFAULT 1,
    data            TEXT NOT NULL,
    author          TEXT NOT NULL DEFAULT 'system',
    note            TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT current_timestamp,

    UNIQUE(domain, version_num)
);
"""


class DuckDBStore(OntologyStore):
    """DuckDB-backed ontology store. Same schema as Postgres but using DuckDB.

    Works with both file-based and in-memory DuckDB databases.
    Ontology data is stored as JSON text (DuckDB doesn't have JSONB).
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._migrated = False

    def _connect(self):
        import duckdb
        return duckdb.connect(self._db_path)

    def _ensure_table(self, conn) -> None:
        if self._migrated:
            return
        try:
            conn.execute("CREATE SEQUENCE IF NOT EXISTS nexaql_ontologies_id_seq START 1")
        except Exception:
            pass  # may already exist
        conn.execute(DUCKDB_DDL)
        self._migrated = True

    async def load(self, domain: str) -> Ontology:
        conn = self._connect()
        try:
            self._ensure_table(conn)
            row = conn.execute(
                "SELECT data FROM nexaql_ontologies WHERE domain = ? AND is_active = TRUE "
                "ORDER BY version_num DESC LIMIT 1",
                [domain],
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            raise KeyError(f"No active ontology found for domain '{domain}'")
        data = json.loads(row[0])
        return Ontology(**data)

    async def save(self, ontology: Ontology, author: str = "system", note: str | None = None) -> dict[str, Any]:
        data = ontology_to_dict(ontology)
        conn = self._connect()
        try:
            self._ensure_table(conn)
            conn.begin()

            row = conn.execute(
                "SELECT COALESCE(MAX(version_num), 0) FROM nexaql_ontologies WHERE domain = ?",
                [ontology.domain],
            ).fetchone()
            new_ver = (row[0] if row else 0) + 1

            conn.execute(
                "UPDATE nexaql_ontologies SET is_active = FALSE WHERE domain = ? AND is_active = TRUE",
                [ontology.domain],
            )

            conn.execute(
                "INSERT INTO nexaql_ontologies (domain, version_num, data, author, note, is_active) "
                "VALUES (?, ?, ?, ?, ?, TRUE)",
                [ontology.domain, new_ver, json.dumps(data), author, note],
            )
            conn.commit()

            row = conn.execute(
                "SELECT id, created_at FROM nexaql_ontologies WHERE domain = ? AND version_num = ?",
                [ontology.domain, new_ver],
            ).fetchone()
        finally:
            conn.close()

        return {
            "id": row[0],
            "domain": ontology.domain,
            "version": new_ver,
            "author": author,
            "created_at": str(row[1]),
            "node_count": len(ontology.nodes),
        }

    async def _modify_and_save(self, domain: str, modify_fn, author: str = "system") -> Ontology:
        conn = self._connect()
        try:
            self._ensure_table(conn)
            conn.begin()

            row = conn.execute(
                "SELECT data, version_num FROM nexaql_ontologies WHERE domain = ? AND is_active = TRUE "
                "ORDER BY version_num DESC LIMIT 1",
                [domain],
            ).fetchone()
            if row is None:
                raise KeyError(f"No active ontology for domain '{domain}'")

            data = json.loads(row[0])
            ont = Ontology(**data)
            new_ver = row[1] + 1

            modify_fn(ont)

            conn.execute(
                "UPDATE nexaql_ontologies SET is_active = FALSE WHERE domain = ? AND is_active = TRUE",
                [domain],
            )
            new_data = ontology_to_dict(ont)
            conn.execute(
                "INSERT INTO nexaql_ontologies (domain, version_num, data, author, is_active) "
                "VALUES (?, ?, ?, ?, TRUE)",
                [domain, new_ver, json.dumps(new_data), author],
            )
            conn.commit()
        finally:
            conn.close()

        return ont

    async def update_node(self, domain: str, node_name: str, node: OntologyNode, author: str = "system") -> Ontology:
        def _modify(ont: Ontology):
            ont.nodes[node_name] = node
        return await self._modify_and_save(domain, _modify, author)

    async def delete_node(self, domain: str, node_name: str, author: str = "system") -> Ontology:
        def _modify(ont: Ontology):
            if node_name not in ont.nodes:
                raise KeyError(f"Node '{node_name}' not found")
            del ont.nodes[node_name]
        return await self._modify_and_save(domain, _modify, author)

    async def add_node(self, domain: str, node_name: str, node: OntologyNode, author: str = "system") -> Ontology:
        def _modify(ont: Ontology):
            if node_name in ont.nodes:
                raise KeyError(f"Node '{node_name}' already exists")
            ont.nodes[node_name] = node
        return await self._modify_and_save(domain, _modify, author)

    async def list_domains(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            self._ensure_table(conn)
            rows = conn.execute("""
                SELECT domain,
                       MAX(version_num) AS latest_version,
                       MAX(created_at) AS updated_at,
                       COUNT(*) AS total_versions
                FROM nexaql_ontologies
                GROUP BY domain
                ORDER BY domain
            """).fetchall()
        finally:
            conn.close()

        return [
            {
                "domain": r[0],
                "backend": "duckdb",
                "latest_version": r[1],
                "updated_at": str(r[2]),
                "total_versions": r[3],
            }
            for r in rows
        ]

    async def list_versions(self, domain: str, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            self._ensure_table(conn)
            rows = conn.execute(
                "SELECT id, version_num, author, note, is_active, created_at "
                "FROM nexaql_ontologies WHERE domain = ? "
                "ORDER BY version_num DESC LIMIT ?",
                [domain, limit],
            ).fetchall()
        finally:
            conn.close()

        return [
            {
                "version_id": r[0],
                "version_num": r[1],
                "domain": domain,
                "author": r[2],
                "note": r[3],
                "is_active": r[4],
                "created_at": str(r[5]),
            }
            for r in rows
        ]

    async def load_version(self, domain: str, version_id: int) -> Ontology:
        conn = self._connect()
        try:
            self._ensure_table(conn)
            row = conn.execute(
                "SELECT data FROM nexaql_ontologies WHERE id = ? AND domain = ?",
                [version_id, domain],
            ).fetchone()
        finally:
            conn.close()

        if row is None:
            raise KeyError(f"Version {version_id} not found for domain '{domain}'")
        data = json.loads(row[0])
        return Ontology(**data)

    async def delete_domain(self, domain: str) -> bool:
        conn = self._connect()
        try:
            self._ensure_table(conn)
            before = conn.execute("SELECT COUNT(*) FROM nexaql_ontologies WHERE domain = ?", [domain]).fetchone()[0]
            conn.execute("DELETE FROM nexaql_ontologies WHERE domain = ?", [domain])
        finally:
            conn.close()
        return before > 0


# ── PostgreSQL Store (production) ───────────────────────────────────────────


# DDL for the ontologies table — run once via migrate()
POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS nexaql_ontologies (
    id              SERIAL PRIMARY KEY,
    domain          TEXT NOT NULL,
    version_num     INTEGER NOT NULL DEFAULT 1,
    data            JSONB NOT NULL,
    node_count      INTEGER GENERATED ALWAYS AS (jsonb_array_length(
                        COALESCE((SELECT jsonb_agg(k) FROM jsonb_object_keys(data->'nodes') AS k), '[]'::jsonb)
                    )) STORED,
    author          TEXT NOT NULL DEFAULT 'system',
    note            TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(domain, version_num)
);

-- Fast lookup: active ontology per domain
CREATE INDEX IF NOT EXISTS idx_ontologies_active
    ON nexaql_ontologies (domain, is_active)
    WHERE is_active = TRUE;

-- Full-text search on ontology content (node names, descriptions, field names)
CREATE INDEX IF NOT EXISTS idx_ontologies_data_gin
    ON nexaql_ontologies USING gin (data jsonb_path_ops);

-- Comment on table
COMMENT ON TABLE nexaql_ontologies IS 'NexaQL ontology storage with version history';
"""

# Simplified DDL without generated column (wider PG compatibility)
POSTGRES_DDL_SIMPLE = """
CREATE TABLE IF NOT EXISTS nexaql_ontologies (
    id              SERIAL PRIMARY KEY,
    domain          TEXT NOT NULL,
    version_num     INTEGER NOT NULL DEFAULT 1,
    data            JSONB NOT NULL,
    author          TEXT NOT NULL DEFAULT 'system',
    note            TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(domain, version_num)
);

CREATE INDEX IF NOT EXISTS idx_ontologies_active
    ON nexaql_ontologies (domain, is_active)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_ontologies_data_gin
    ON nexaql_ontologies USING gin (data jsonb_path_ops);
"""


class PostgresStore(OntologyStore):
    """PostgreSQL-backed ontology store with JSONB storage and version history.

    Each save creates a new version. Only one version per domain is active.
    Partial updates (add/update/delete node) read-modify-write atomically
    within a transaction.
    """

    def __init__(self, connection_url: str):
        self._url = connection_url
        self._pool = None
        self._migrated = False

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(self._url, min_size=1, max_size=5)
        return self._pool

    async def migrate(self) -> None:
        """Create the ontologies table if it doesn't exist."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            try:
                await conn.execute(POSTGRES_DDL)
            except Exception:
                # Fall back to simpler DDL without generated column
                await conn.execute(POSTGRES_DDL_SIMPLE)

    async def load(self, domain: str) -> Ontology:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM nexaql_ontologies WHERE domain = $1 AND is_active = TRUE ORDER BY version_num DESC LIMIT 1",
                domain,
            )
        if row is None:
            raise KeyError(f"No active ontology found for domain '{domain}'")
        data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        return Ontology(**data)

    async def save(self, ontology: Ontology, author: str = "system", note: str | None = None) -> dict[str, Any]:
        pool = await self._get_pool()
        data = ontology_to_dict(ontology)

        # Auto-create table on first save
        if not self._migrated:
            try:
                await self.migrate()
                self._migrated = True
            except Exception:
                pass  # Table may already exist

        async with pool.acquire() as conn:
            async with conn.transaction():
                # Get next version number
                max_ver = await conn.fetchval(
                    "SELECT COALESCE(MAX(version_num), 0) FROM nexaql_ontologies WHERE domain = $1",
                    ontology.domain,
                )
                new_ver = max_ver + 1

                # Deactivate previous versions
                await conn.execute(
                    "UPDATE nexaql_ontologies SET is_active = FALSE WHERE domain = $1 AND is_active = TRUE",
                    ontology.domain,
                )

                # Insert new version
                row = await conn.fetchrow(
                    """INSERT INTO nexaql_ontologies (domain, version_num, data, author, note, is_active)
                       VALUES ($1, $2, $3::jsonb, $4, $5, TRUE)
                       RETURNING id, created_at""",
                    ontology.domain,
                    new_ver,
                    json.dumps(data),
                    author,
                    note,
                )

        return {
            "id": row["id"],
            "domain": ontology.domain,
            "version": new_ver,
            "author": author,
            "created_at": row["created_at"].isoformat(),
            "node_count": len(ontology.nodes),
        }

    async def _modify_and_save(
        self, domain: str, modify_fn, author: str = "system",
    ) -> Ontology:
        """Read-modify-write atomically within a transaction."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Read current with FOR UPDATE
                row = await conn.fetchrow(
                    "SELECT data, version_num FROM nexaql_ontologies WHERE domain = $1 AND is_active = TRUE ORDER BY version_num DESC LIMIT 1 FOR UPDATE",
                    domain,
                )
                if row is None:
                    raise KeyError(f"No active ontology for domain '{domain}'")

                data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
                ont = Ontology(**data)
                new_ver = row["version_num"] + 1

                # Apply modification
                modify_fn(ont)

                # Deactivate old, insert new
                await conn.execute(
                    "UPDATE nexaql_ontologies SET is_active = FALSE WHERE domain = $1 AND is_active = TRUE",
                    domain,
                )
                new_data = ontology_to_dict(ont)
                await conn.execute(
                    """INSERT INTO nexaql_ontologies (domain, version_num, data, author, is_active)
                       VALUES ($1, $2, $3::jsonb, $4, TRUE)""",
                    domain,
                    new_ver,
                    json.dumps(new_data),
                    author,
                )

        return ont

    async def update_node(
        self, domain: str, node_name: str, node: OntologyNode, author: str = "system",
    ) -> Ontology:
        def _modify(ont: Ontology):
            ont.nodes[node_name] = node
        return await self._modify_and_save(domain, _modify, author)

    async def delete_node(
        self, domain: str, node_name: str, author: str = "system",
    ) -> Ontology:
        def _modify(ont: Ontology):
            if node_name not in ont.nodes:
                raise KeyError(f"Node '{node_name}' not found")
            del ont.nodes[node_name]
        return await self._modify_and_save(domain, _modify, author)

    async def add_node(
        self, domain: str, node_name: str, node: OntologyNode, author: str = "system",
    ) -> Ontology:
        def _modify(ont: Ontology):
            if node_name in ont.nodes:
                raise KeyError(f"Node '{node_name}' already exists")
            ont.nodes[node_name] = node
        return await self._modify_and_save(domain, _modify, author)

    async def list_domains(self) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT domain,
                       MAX(version_num) AS latest_version,
                       MAX(created_at) AS updated_at,
                       COUNT(*) AS total_versions
                FROM nexaql_ontologies
                GROUP BY domain
                ORDER BY domain
            """)
        return [
            {
                "domain": r["domain"],
                "backend": "postgres",
                "latest_version": r["latest_version"],
                "updated_at": r["updated_at"].isoformat(),
                "total_versions": r["total_versions"],
            }
            for r in rows
        ]

    async def list_versions(self, domain: str, limit: int = 20) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, version_num, author, note, is_active, created_at
                   FROM nexaql_ontologies
                   WHERE domain = $1
                   ORDER BY version_num DESC
                   LIMIT $2""",
                domain,
                limit,
            )
        return [
            {
                "version_id": r["id"],
                "version_num": r["version_num"],
                "domain": domain,
                "author": r["author"],
                "note": r["note"],
                "is_active": r["is_active"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]

    async def load_version(self, domain: str, version_id: int) -> Ontology:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM nexaql_ontologies WHERE id = $1 AND domain = $2",
                version_id,
                domain,
            )
        if row is None:
            raise KeyError(f"Version {version_id} not found for domain '{domain}'")
        data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        return Ontology(**data)

    async def rollback(self, domain: str, version_id: int, author: str = "system") -> dict[str, Any]:
        """Restore a previous version as the new active version."""
        ont = await self.load_version(domain, version_id)
        return await self.save(ont, author, note=f"Rollback to version {version_id}")

    async def delete_domain(self, domain: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM nexaql_ontologies WHERE domain = $1", domain,
            )
        return "DELETE" in result and result != "DELETE 0"

    async def search_nodes(self, query: str) -> list[dict[str, Any]]:
        """Search across all active ontologies for nodes matching a query."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT domain, key AS node_name,
                       value->>'description' AS description,
                       value->>'table' AS table_name
                FROM nexaql_ontologies,
                     jsonb_each(data->'nodes') AS n(key, value)
                WHERE is_active = TRUE
                  AND (key ILIKE $1 OR value->>'description' ILIKE $1 OR value->>'table' ILIKE $1)
                ORDER BY domain, key
            """, f"%{query}%")
        return [dict(r) for r in rows]

    async def close(self):
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None


# ── Factory ─────────────────────────────────────────────────────────────────

_store_instance: OntologyStore | None = None


def get_store(
    backend: str | None = None,
    connection_url: str | None = None,
    ontology_dir: str = "ontologies",
) -> OntologyStore:
    """Get or create the ontology store singleton.

    Auto-detects backend from environment or connection URL:
    - ``postgresql://...`` → PostgresStore
    - ``*.duckdb`` or ``:memory:`` → DuckDBStore
    - Explicit: ``NEXAQL_ONTOLOGY_STORE=postgres|duckdb|yaml``

    Can also be called explicitly::

        store = get_store(backend="postgres", connection_url="postgresql://...")
        store = get_store(backend="duckdb", connection_url="nexaql.duckdb")
    """
    global _store_instance

    if _store_instance is not None:
        return _store_instance

    if backend is None:
        backend = os.environ.get("NEXAQL_ONTOLOGY_STORE", "")

    # Auto-detect from connection URL
    if not backend and connection_url:
        if connection_url.startswith("postgresql"):
            backend = "postgres"
        elif connection_url.endswith(".duckdb") or connection_url == ":memory:":
            backend = "duckdb"

    if not backend:
        backend = "yaml"

    if backend == "postgres":
        url = connection_url or os.environ.get("NEXAQL_ONTOLOGY_DB")
        if not url:
            raise ValueError(
                "PostgresStore requires a connection URL. "
                "Set NEXAQL_ONTOLOGY_DB or pass connection_url."
            )
        _store_instance = PostgresStore(url)
    elif backend == "duckdb":
        path = connection_url or os.environ.get("NEXAQL_ONTOLOGY_DB", "nexaql.duckdb")
        _store_instance = DuckDBStore(path)
    else:
        _store_instance = YamlStore(ontology_dir)

    return _store_instance


def reset_store() -> None:
    """Reset the store singleton (useful for testing)."""
    global _store_instance
    _store_instance = None
