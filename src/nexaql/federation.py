# Copyright (c) 2026-present NexaQL Contributors
"""Cross-datasource federation via session-scoped DuckDB.

When a query spans tables from different connectors (e.g. ecommerce in DuckDB
and support tickets in PostgreSQL), this module:

1. Detects the cross-datasource condition
2. Loads the required tables into a session-scoped in-memory DuckDB
3. Executes the translated SQL against that DuckDB
4. Returns the results

The session DuckDB acts as a cache — tables loaded once are reused across
subsequent queries within the same session until the TTL expires.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

import duckdb

from nexaql.adapters.base import AdapterResult, QueryAdapter
from nexaql.engine.translator import TranslateResult, translate
from nexaql.engine.types import ColumnMeta, EdgeField, NodeSelection, NodeShape, QueryAST

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

DEFAULT_ROW_LIMIT = 5_000_000
DEFAULT_TTL_SECONDS = 600  # 10 minutes idle
DEFAULT_MAX_MEMORY_MB = 500


# ── Session DuckDB Manager ──────────────────────────────────────────────────


class _TableEntry:
    """Tracks a loaded table in the session DuckDB."""

    def __init__(self, table_name: str, row_count: int) -> None:
        self.table_name = table_name
        self.row_count = row_count
        self.loaded_at = time.time()
        self.last_used = time.time()

    def touch(self) -> None:
        self.last_used = time.time()

    def is_expired(self, ttl: int) -> bool:
        return (time.time() - self.last_used) > ttl


class SessionDuckDB:
    """A session-scoped in-memory DuckDB for cross-datasource federation."""

    def __init__(
        self,
        session_id: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        row_limit: int = DEFAULT_ROW_LIMIT,
    ) -> None:
        self.session_id = session_id
        self.ttl_seconds = ttl_seconds
        self.row_limit = row_limit
        self._conn = duckdb.connect(":memory:")
        self._tables: Dict[str, _TableEntry] = {}
        self._created_at = time.time()

    def has_table(self, table_name: str) -> bool:
        entry = self._tables.get(table_name)
        if entry is None:
            return False
        if entry.is_expired(self.ttl_seconds):
            self._drop_table(table_name)
            return False
        entry.touch()
        return True

    def load_table(
        self,
        table_name: str,
        rows: List[Dict[str, Any]],
        columns: List[ColumnMeta],
    ) -> int:
        """Load rows into a table in the session DuckDB."""
        if not rows:
            col_defs = ", ".join(
                f"{c.name} VARCHAR" for c in columns
            )
            self._conn.execute(f"CREATE OR REPLACE TABLE {table_name} ({col_defs})")
            self._tables[table_name] = _TableEntry(table_name, 0)
            return 0

        col_names = [c.name for c in columns]
        col_types = []
        for col in columns:
            col_types.append(_nexaql_type_to_duckdb(col.type))

        col_defs = ", ".join(
            f"{name} {dtype}" for name, dtype in zip(col_names, col_types)
        )
        self._conn.execute(f"CREATE OR REPLACE TABLE {table_name} ({col_defs})")

        placeholders = ", ".join(["?"] * len(col_names))
        insert_sql = f"INSERT INTO {table_name} VALUES ({placeholders})"

        batch_size = 10000
        total = len(rows)
        for i in range(0, total, batch_size):
            batch = rows[i : i + batch_size]
            values = []
            for row in batch:
                row_values = []
                for name in col_names:
                    row_values.append(row.get(name))
                values.append(row_values)
            self._conn.executemany(insert_sql, values)

        self._tables[table_name] = _TableEntry(table_name, total)
        logger.info(
            "Loaded %d rows into session DuckDB table '%s' (session=%s)",
            total, table_name, self.session_id[:8],
        )
        return total

    def execute_sql(self, sql: str) -> Tuple[List[Dict[str, Any]], List[ColumnMeta]]:
        """Execute SQL against the session DuckDB and return rows + columns."""
        rel = self._conn.execute(sql)
        description = rel.description
        raw_rows = rel.fetchall()

        columns: List[ColumnMeta] = []
        col_names: List[str] = []
        for col_name, col_type, *_ in description:
            columns.append(ColumnMeta(name=col_name, type=_duckdb_type_to_nexaql(str(col_type))))
            col_names.append(col_name)

        rows: List[Dict[str, Any]] = [dict(zip(col_names, row)) for row in raw_rows]
        return rows, columns

    def cleanup_expired(self) -> int:
        """Drop expired tables. Returns count of tables dropped."""
        expired = []
        for name, entry in self._tables.items():
            if entry.is_expired(self.ttl_seconds):
                expired.append(name)
        for name in expired:
            self._drop_table(name)
        return len(expired)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _drop_table(self, table_name: str) -> None:
        try:
            self._conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        except Exception:
            pass
        self._tables.pop(table_name, None)


# ── Global session registry ─────────────────────────────────────────────────

_sessions: Dict[str, SessionDuckDB] = {}


def get_session(session_id: Optional[str] = None) -> SessionDuckDB:
    """Get or create a session-scoped DuckDB."""
    if session_id is None:
        session_id = str(uuid.uuid4())

    if session_id in _sessions:
        session = _sessions[session_id]
        session.cleanup_expired()
        return session

    session = SessionDuckDB(session_id)
    _sessions[session_id] = session
    return session


def cleanup_sessions() -> int:
    """Remove sessions that have been idle past their TTL."""
    to_remove = []
    for sid, session in _sessions.items():
        session.cleanup_expired()
        if not session._tables:
            idle_time = time.time() - session._created_at
            if idle_time > session.ttl_seconds:
                to_remove.append(sid)

    for sid in to_remove:
        session = _sessions.pop(sid)
        session.close()

    return len(to_remove)


# ── AST node collection ─────────────────────────────────────────────────────


def collect_query_tables(ast: QueryAST, ontology: Any) -> Dict[str, str]:
    """Walk the AST and collect all table names with their node names.

    Returns a dict of {node_name: table_name}.
    """
    nodes_map = getattr(ontology, "nodes", {}) or {}
    result: Dict[str, str] = {}
    _collect_from_node(ast.body, nodes_map, result)
    return result


def _collect_from_node(
    node: NodeSelection,
    nodes_map: Dict[str, Any],
    result: Dict[str, str],
) -> None:
    """Recursively collect node_name -> table_name from the AST."""
    node_def = nodes_map.get(node.name)
    if node_def is not None:
        table_name = getattr(node_def, "table", None) or node.name
        result[node.name] = table_name

    edges_map = getattr(node_def, "edges", {}) or {} if node_def else {}

    for field in node.fields:
        if field.kind == "edge":
            ef: EdgeField = field  # type: ignore
            edge_def = edges_map.get(ef.node.name)
            if edge_def is not None:
                target_node_name = getattr(edge_def, "node", None) or ef.node.name
                target_node_def = nodes_map.get(target_node_name)
                if target_node_def is not None:
                    target_table = getattr(target_node_def, "table", None) or target_node_name
                    result[target_node_name] = target_table

                target_edges = getattr(target_node_def, "edges", {}) or {} if target_node_def else {}
                resolved_child = NodeSelection(
                    kind=ef.node.kind,
                    name=target_node_name,
                    filters=ef.node.filters,
                    directives=ef.node.directives,
                    fields=ef.node.fields,
                )
                _collect_from_node(resolved_child, nodes_map, result)


def detect_cross_datasource(
    ast: QueryAST,
    ontology: Any,
) -> Tuple[bool, Dict[int, Set[str]]]:
    """Check if a query spans multiple datasource connectors.

    Returns (is_cross_datasource, connector_to_nodes).
    connector_to_nodes maps connector_id -> set of node names.
    """
    node_to_connector = getattr(ontology, "node_to_connector", None) or {}
    if not node_to_connector:
        return False, {}

    query_tables = collect_query_tables(ast, ontology)
    connector_to_nodes: Dict[int, Set[str]] = {}

    for node_name in query_tables:
        connector_id = node_to_connector.get(node_name)
        if connector_id is None:
            continue
        if connector_id not in connector_to_nodes:
            connector_to_nodes[connector_id] = set()
        connector_to_nodes[connector_id].add(node_name)

    is_cross = len(connector_to_nodes) > 1
    return is_cross, connector_to_nodes


# ── Federated execution ─────────────────────────────────────────────────────


async def execute_federated(
    ast: QueryAST,
    ontology: Any,
    adapter_map: Dict[int, QueryAdapter],
    session_id: Optional[str] = None,
) -> AdapterResult:
    """Execute a cross-datasource query via session-scoped DuckDB federation.

    1. Collect all tables referenced in the query
    2. Group by source connector
    3. Load each table into session DuckDB (skip if already cached)
    4. Translate the AST to DuckDB SQL
    5. Execute against the session DuckDB
    6. Return results
    """
    session = get_session(session_id)

    query_tables = collect_query_tables(ast, ontology)
    node_to_connector = getattr(ontology, "node_to_connector", None) or {}

    # Group tables by connector for loading
    tables_to_load: Dict[int, List[Tuple[str, str]]] = {}
    for node_name, table_name in query_tables.items():
        if session.has_table(table_name):
            continue
        connector_id = node_to_connector.get(node_name)
        if connector_id is None:
            continue
        if connector_id not in tables_to_load:
            tables_to_load[connector_id] = []
        tables_to_load[connector_id].append((node_name, table_name))

    # Load tables from each source
    for connector_id, table_list in tables_to_load.items():
        adapter = adapter_map.get(connector_id)
        if adapter is None:
            logger.warning("No adapter for connector_id=%d, skipping tables", connector_id)
            continue

        for node_name, table_name in table_list:
            rows, columns = await adapter.fetch_table(table_name, session.row_limit)
            session.load_table(table_name, rows, columns)

    # Translate AST to SQL (DuckDB dialect)
    tr = translate(ast, ontology)
    sql = tr.sql

    logger.info("Federated SQL: %s", sql[:500])

    # Execute against session DuckDB
    rows, columns = session.execute_sql(sql)

    return AdapterResult(
        rows=rows,
        columns=columns,
        row_count=len(rows),
        shape=tr.shape,
        query_preview=f"[federated] {sql}",
        adapter_type="federation",
    )


# ── Type mapping helpers ─────────────────────────────────────────────────────


def _nexaql_type_to_duckdb(nexaql_type: str) -> str:
    mapping = {
        "string": "VARCHAR",
        "integer": "BIGINT",
        "numeric": "DOUBLE",
        "boolean": "BOOLEAN",
        "date": "VARCHAR",
    }
    return mapping.get(nexaql_type, "VARCHAR")


def _duckdb_type_to_nexaql(duckdb_type: str) -> str:
    name = duckdb_type.upper()
    mapping = {
        "VARCHAR": "string",
        "BIGINT": "integer",
        "INTEGER": "integer",
        "DOUBLE": "numeric",
        "FLOAT": "numeric",
        "DECIMAL": "numeric",
        "BOOLEAN": "boolean",
        "DATE": "date",
        "TIMESTAMP": "date",
    }
    matched = mapping.get(name)
    if matched:
        return matched
    base = name.split("(")[0]
    return mapping.get(base, "string")
