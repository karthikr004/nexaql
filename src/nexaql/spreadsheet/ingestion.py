# Copyright (c) 2026-present NexaQL Contributors
"""Spreadsheet ingestion — load tabular files into DuckDB for querying."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import duckdb


@dataclass
class ColumnMeta:
    name: str
    dtype: str
    nullable: bool = True


@dataclass
class IngestionResult:
    table_name: str
    duckdb_path: str
    row_count: int
    columns: list[ColumnMeta] = field(default_factory=list)


_NEXAQL_DIR = os.path.join(Path.home(), ".nexaql")
_UPLOADS_DIR = os.path.join(_NEXAQL_DIR, "uploads")
_SPREADSHEETS_DIR = os.path.join(_NEXAQL_DIR, "spreadsheets")


def _ensure_dirs() -> None:
    os.makedirs(_UPLOADS_DIR, exist_ok=True)
    os.makedirs(_SPREADSHEETS_DIR, exist_ok=True)


def _sanitize_table_name(filename: str) -> str:
    stem = Path(filename).stem
    name = "".join(c if c.isalnum() or c == "_" else "_" for c in stem)
    if name and name[0].isdigit():
        name = f"t_{name}"
    return name.lower() or "uploaded_data"


def get_uploads_dir() -> str:
    _ensure_dirs()
    return _UPLOADS_DIR


def get_duckdb_path(connector_name: str) -> str:
    _ensure_dirs()
    return os.path.join(_SPREADSHEETS_DIR, f"{connector_name}.duckdb")


def ingest_csv(
    file_path: str,
    connector_name: str,
    table_name: str | None = None,
    delimiter: str | None = None,
) -> IngestionResult:
    """Load a CSV/TSV file into a DuckDB database.

    Uses DuckDB's read_csv_auto for type inference and fast loading.
    The DuckDB file is stored at ~/.nexaql/spreadsheets/{connector_name}.duckdb.
    """
    _ensure_dirs()

    if table_name is None:
        table_name = _sanitize_table_name(os.path.basename(file_path))

    db_path = get_duckdb_path(connector_name)
    conn = duckdb.connect(db_path)

    try:
        options = f"auto_detect=true, header=true"
        if delimiter:
            escaped = delimiter.replace("'", "''")
            options += f", delim='{escaped}'"

        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        conn.execute(
            f"CREATE TABLE {table_name} AS "
            f"SELECT * FROM read_csv_auto('{file_path}', {options})"
        )

        row_count_result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        row_count = row_count_result[0] if row_count_result else 0

        col_rows = conn.execute(
            f"SELECT column_name, data_type, is_nullable "
            f"FROM information_schema.columns "
            f"WHERE table_name = '{table_name}' AND table_schema = 'main' "
            f"ORDER BY ordinal_position"
        ).fetchall()

        columns = [
            ColumnMeta(
                name=row[0],
                dtype=str(row[1]),
                nullable=row[2] == "YES",
            )
            for row in col_rows
        ]

        return IngestionResult(
            table_name=table_name,
            duckdb_path=db_path,
            row_count=row_count,
            columns=columns,
        )
    finally:
        conn.close()


def list_tables(connector_name: str) -> list[dict[str, str | int]]:
    """List all tables in a spreadsheet connector's DuckDB file."""
    db_path = get_duckdb_path(connector_name)
    if not os.path.exists(db_path):
        return []

    conn = duckdb.connect(db_path, read_only=True)
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()
        result = []
        for (tname,) in rows:
            count = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()
            result.append({"name": tname, "row_count": count[0] if count else 0})
        return result
    finally:
        conn.close()
