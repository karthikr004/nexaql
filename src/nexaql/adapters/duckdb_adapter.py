"""DuckDB adapter — executes NexaQL queries against a DuckDB database."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List

import duckdb

from nexaql.adapters.base import AdapterResult, QueryAdapter
from nexaql.engine.translator import translate
from nexaql.engine.types import ColumnMeta, QueryAST

# DuckDB Python type name -> friendly type name
_DUCKDB_TYPE_MAP: Dict[str, str] = {
    "BOOLEAN": "boolean",
    "TINYINT": "integer",
    "SMALLINT": "integer",
    "INTEGER": "integer",
    "BIGINT": "integer",
    "HUGEINT": "integer",
    "FLOAT": "numeric",
    "DOUBLE": "numeric",
    "DECIMAL": "numeric",
    "VARCHAR": "string",
    "DATE": "date",
    "TIMESTAMP": "date",
    "TIMESTAMP WITH TIME ZONE": "date",
}


def _duckdb_type_to_str(type_name: Any) -> str:
    # DuckDB returns DuckDBPyType objects, not plain strings — convert first
    name = str(type_name).upper()
    matched = _DUCKDB_TYPE_MAP.get(name)
    if matched:
        return matched
    # Handle parameterised types like DECIMAL(10,2) → DECIMAL
    base = name.split("(")[0]
    return _DUCKDB_TYPE_MAP.get(base, "string")


class DuckDBAdapter(QueryAdapter):
    """In-process adapter for DuckDB.

    Uses a persistent connection so :memory: databases retain data across queries.
    Supports auto-seeding via a SQL file on first connect.
    """

    def __init__(self, path: str = ":memory:", seed_file: str | None = None) -> None:
        self._path = path
        self._seed_file = seed_file
        self._conn: duckdb.DuckDBPyConnection | None = None

    def _get_conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(self._path)
            self._maybe_seed()
        return self._conn

    def _maybe_seed(self) -> None:
        """Run the seed SQL file if the database has no tables."""
        if not self._seed_file or not self._conn:
            return

        # Check if tables already exist
        tables = self._conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchone()
        if tables and tables[0] > 0:
            return

        # Resolve seed file path relative to config file location
        seed_path = self._seed_file
        if not os.path.isabs(seed_path):
            # Try relative to CWD
            if not os.path.exists(seed_path):
                return

        if os.path.exists(seed_path):
            with open(seed_path) as f:
                sql = f.read()
            self._conn.execute(sql)
            table_count = self._conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchone()
            print(f"  Seeded DuckDB with {table_count[0] if table_count else 0} tables from {seed_path}")

    # -- QueryAdapter interface ------------------------------------------------

    @property
    def adapter_type(self) -> str:
        return "duckdb"

    def describe(self, ast: QueryAST, ontology: Any) -> str:
        result = translate(ast, ontology)
        return result.sql

    async def execute(self, ast: QueryAST, ontology: Any) -> AdapterResult:
        result = translate(ast, ontology)
        sql = result.sql

        loop = asyncio.get_running_loop()
        rows, columns = await loop.run_in_executor(None, self._run_query, sql)

        return AdapterResult(
            rows=rows,
            columns=columns,
            row_count=len(rows),
            shape=result.shape,
            query_preview=sql,
            adapter_type=self.adapter_type,
        )

    async def healthcheck(self) -> bool:
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._ping)
            return True
        except Exception:
            return False

    # -- internal helpers ------------------------------------------------------

    def _run_query(self, sql: str) -> tuple[List[Dict[str, Any]], List[ColumnMeta]]:
        conn = self._get_conn()
        rel = conn.execute(sql)
        description = rel.description
        raw_rows = rel.fetchall()

        columns: List[ColumnMeta] = []
        col_names: List[str] = []
        for col_name, col_type, *_ in description:
            columns.append(ColumnMeta(name=col_name, type=_duckdb_type_to_str(col_type)))
            col_names.append(col_name)

        rows: List[Dict[str, Any]] = [dict(zip(col_names, row)) for row in raw_rows]
        return rows, columns

    def _ping(self) -> None:
        conn = self._get_conn()
        conn.execute("SELECT 1").fetchone()

    async def fetch_table(self, table_name: str, row_limit: int = 5_000_000) -> tuple[List[Dict[str, Any]], List[ColumnMeta]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_table_sync, table_name, row_limit)

    def _fetch_table_sync(self, table_name: str, row_limit: int) -> tuple[List[Dict[str, Any]], List[ColumnMeta]]:
        conn = self._get_conn()
        rel = conn.execute(f"SELECT * FROM {table_name} LIMIT {row_limit}")
        description = rel.description
        raw_rows = rel.fetchall()

        columns: List[ColumnMeta] = []
        col_names: List[str] = []
        for col_name, col_type, *_ in description:
            columns.append(ColumnMeta(name=col_name, type=_duckdb_type_to_str(col_type)))
            col_names.append(col_name)

        rows: List[Dict[str, Any]] = [dict(zip(col_names, row)) for row in raw_rows]
        return rows, columns
