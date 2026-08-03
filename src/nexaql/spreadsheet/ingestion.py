# Copyright (c) 2026-present NexaQL Contributors
"""Spreadsheet ingestion — load tabular files into DuckDB for querying."""

from __future__ import annotations

import csv
import os
import re
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
    preview: list[dict[str, str | None]] = field(default_factory=list)
    header_row: int = 0
    skipped_rows: int = 0


_NEXAQL_DIR = os.path.join(Path.home(), ".nexaql")
_UPLOADS_DIR = os.path.join(_NEXAQL_DIR, "uploads")
_SPREADSHEETS_DIR = os.path.join(_NEXAQL_DIR, "spreadsheets")
_SHARED_DUCKDB = os.path.join(_SPREADSHEETS_DIR, "uploads.duckdb")

SPREADSHEETS_CONNECTOR_NAME = "spreadsheets"

_MAX_SCAN_ROWS = 30
_PREVIEW_ROWS = 5


def _ensure_dirs() -> None:
    os.makedirs(_UPLOADS_DIR, exist_ok=True)
    os.makedirs(_SPREADSHEETS_DIR, exist_ok=True)


def _detect_delimiter(file_path: str) -> str:
    """Detect CSV delimiter by sniffing the first few KB."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        sample = f.read(8192)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _is_header_row(cells: list[str], total_cols: int) -> bool:
    """Score whether a row looks like a header.

    A header row has mostly non-empty, non-numeric, unique text values.
    """
    if not cells or total_cols == 0:
        return False

    non_empty = [c.strip() for c in cells if c.strip()]
    if len(non_empty) < max(1, total_cols * 0.5):
        return False

    numeric_count = sum(1 for c in non_empty if _is_numeric(c))
    if numeric_count > len(non_empty) * 0.5:
        return False

    if len(set(c.lower() for c in non_empty)) < len(non_empty) * 0.8:
        return False

    return True


def _is_numeric(val: str) -> bool:
    """Check if a string looks like a number (including dates like 05/30)."""
    val = val.strip().lstrip("$").replace(",", "")
    try:
        float(val)
        return True
    except ValueError:
        return False


def _is_empty_row(cells: list[str]) -> bool:
    return all(not c.strip() for c in cells)


def detect_header_row(file_path: str, delimiter: str) -> tuple[int, int]:
    """Scan the first N rows to find the actual header row.

    Returns (header_row_index, expected_column_count).
    header_row_index is 0-based line number in the file.
    """
    rows: list[list[str]] = []
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for i, row in enumerate(reader):
            if i >= _MAX_SCAN_ROWS:
                break
            rows.append(row)

    if not rows:
        return 0, 0

    max_cols = max(len(r) for r in rows)

    for i, row in enumerate(rows):
        padded = row + [""] * (max_cols - len(row))
        if _is_header_row(padded, max_cols):
            return i, max_cols

    return 0, max_cols


def _clean_table_name(filename: str) -> str:
    """Derive a short, readable table name from a filename.

    Strips extensions, parenthetical content, deduplicates words,
    and truncates to a reasonable length.
    """
    stem = Path(filename).stem

    # Remove content after common separators that indicate duplicated sheet names
    # e.g. "Report - Sheet1" or "Expenses (personal) - Copy"
    stem = re.split(r"\s*[-–—]\s+", stem)[0]

    # Remove parenthetical content
    stem = re.sub(r"\s*\([^)]*\)", "", stem)

    # Replace non-alphanumeric with underscores
    name = re.sub(r"[^a-zA-Z0-9]+", "_", stem)

    # Collapse multiple underscores, strip leading/trailing
    name = re.sub(r"_+", "_", name).strip("_")

    # Lowercase
    name = name.lower()

    # Truncate to 60 chars at a word boundary
    if len(name) > 60:
        name = name[:60].rsplit("_", 1)[0]

    if not name or name[0].isdigit():
        name = f"t_{name}" if name else "uploaded_data"

    return name


def _clean_column_name(raw: str) -> str:
    """Normalize a column name for SQL compatibility."""
    name = raw.strip()
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    name = name.lower()
    if not name:
        return "unnamed"
    if name[0].isdigit():
        name = f"col_{name}"
    return name


_CAST_THRESHOLD = 0.7

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%Y/%m/%d",
    "%b %d, %Y",
    "%B %d, %Y",
    "%m/%d",
    "%d-%b-%Y",
]


def _try_date_upgrade(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    col_name: str,
    non_null_count: int,
) -> bool:
    for fmt in _DATE_FORMATS:
        cast_expr = f'TRY_STRPTIME("{col_name}", \'{fmt}\')'
        cast_count = conn.execute(
            f'SELECT COUNT(*) FROM {table_name} '
            f'WHERE {cast_expr} IS NOT NULL '
            f'AND "{col_name}" IS NOT NULL AND TRIM("{col_name}") != \'\''
        ).fetchone()

        if not cast_count or cast_count[0] / non_null_count < _CAST_THRESHOLD:
            continue

        try:
            tmp_col = f"__{col_name}_cast"
            conn.execute(
                f'ALTER TABLE {table_name} ADD COLUMN "{tmp_col}" DATE'
            )
            conn.execute(
                f'UPDATE {table_name} SET "{tmp_col}" = CAST({cast_expr} AS DATE)'
            )
            conn.execute(f'ALTER TABLE {table_name} DROP COLUMN "{col_name}"')
            conn.execute(
                f'ALTER TABLE {table_name} RENAME COLUMN "{tmp_col}" TO "{col_name}"'
            )
            return True
        except Exception:
            try:
                conn.execute(f'ALTER TABLE {table_name} DROP COLUMN "{tmp_col}"')
            except Exception:
                pass
    return False


def _try_numeric_upgrade(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    col_name: str,
    non_null_count: int,
) -> bool:
    cast_count = conn.execute(
        f'SELECT COUNT(*) FROM {table_name} '
        f'WHERE TRY_CAST("{col_name}" AS DOUBLE) IS NOT NULL '
        f'AND "{col_name}" IS NOT NULL AND TRIM("{col_name}") != \'\''
    ).fetchone()

    if not cast_count or cast_count[0] / non_null_count < _CAST_THRESHOLD:
        return False

    try:
        tmp_col = f"__{col_name}_cast"
        conn.execute(
            f'ALTER TABLE {table_name} ADD COLUMN "{tmp_col}" DOUBLE'
        )
        conn.execute(
            f'UPDATE {table_name} SET "{tmp_col}" = TRY_CAST("{col_name}" AS DOUBLE)'
        )
        conn.execute(f'ALTER TABLE {table_name} DROP COLUMN "{col_name}"')
        conn.execute(
            f'ALTER TABLE {table_name} RENAME COLUMN "{tmp_col}" TO "{col_name}"'
        )
        return True
    except Exception:
        try:
            conn.execute(f'ALTER TABLE {table_name} DROP COLUMN "{tmp_col}"')
        except Exception:
            pass
    return False


def _upgrade_column_types(conn: duckdb.DuckDBPyConnection, table_name: str) -> None:
    """Try to upgrade VARCHAR columns to DATE or numeric types."""
    col_rows = conn.execute(
        f"SELECT column_name, data_type "
        f"FROM information_schema.columns "
        f"WHERE table_name = '{table_name}' AND table_schema = 'main' "
        f"AND data_type = 'VARCHAR' "
        f"ORDER BY ordinal_position"
    ).fetchall()

    if not col_rows:
        return

    for col_name, _ in col_rows:
        non_null = conn.execute(
            f'SELECT COUNT(*) FROM {table_name} WHERE "{col_name}" IS NOT NULL '
            f'AND TRIM("{col_name}") != \'\''
        ).fetchone()
        if not non_null or non_null[0] < 3:
            continue
        non_null_count = non_null[0]

        name_lower = col_name.lower()
        is_date_hint = any(
            kw in name_lower for kw in ("date", "time", "created", "updated", "timestamp", "day", "month")
        )

        if is_date_hint:
            if _try_date_upgrade(conn, table_name, col_name, non_null_count):
                continue

        if not _try_numeric_upgrade(conn, table_name, col_name, non_null_count):
            if not is_date_hint:
                _try_date_upgrade(conn, table_name, col_name, non_null_count)


def get_uploads_dir() -> str:
    _ensure_dirs()
    return _UPLOADS_DIR


def get_shared_duckdb_path() -> str:
    _ensure_dirs()
    return _SHARED_DUCKDB


def ingest_csv(
    file_path: str,
    table_name: str | None = None,
    delimiter: str | None = None,
) -> IngestionResult:
    """Load a CSV/TSV file into the shared spreadsheets DuckDB.

    Performs smart header detection to skip leading blank/metadata rows,
    then uses DuckDB's read_csv_auto for type inference and fast loading.
    """
    _ensure_dirs()

    if table_name is None:
        table_name = _clean_table_name(os.path.basename(file_path))

    if delimiter is None:
        delimiter = _detect_delimiter(file_path)

    header_row, _ = detect_header_row(file_path, delimiter)

    db_path = get_shared_duckdb_path()
    conn = duckdb.connect(db_path)

    try:
        escaped_path = file_path.replace("'", "''")
        escaped_delim = delimiter.replace("'", "''")

        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        conn.execute(
            f"CREATE TABLE {table_name} AS "
            f"SELECT * FROM read_csv_auto("
            f"'{escaped_path}', "
            f"auto_detect=true, "
            f"header=true, "
            f"skip={header_row}, "
            f"delim='{escaped_delim}'"
            f")"
        )

        # Drop rows where ALL columns are NULL (blank rows in the data)
        col_rows = conn.execute(
            f"SELECT column_name, data_type, is_nullable "
            f"FROM information_schema.columns "
            f"WHERE table_name = '{table_name}' AND table_schema = 'main' "
            f"ORDER BY ordinal_position"
        ).fetchall()

        col_names = [r[0] for r in col_rows]
        if col_names:
            null_check = " AND ".join(f'"{c}" IS NULL' for c in col_names)
            conn.execute(f"DELETE FROM {table_name} WHERE {null_check}")

        # Rename columns to clean SQL-safe names if needed
        rename_map: dict[str, str] = {}
        seen: set[str] = set()
        for raw_name, _, _ in col_rows:
            clean = _clean_column_name(raw_name)
            if clean in seen:
                suffix = 2
                while f"{clean}_{suffix}" in seen:
                    suffix += 1
                clean = f"{clean}_{suffix}"
            seen.add(clean)
            if clean != raw_name:
                rename_map[raw_name] = clean

        for old_name, new_name in rename_map.items():
            conn.execute(
                f'ALTER TABLE {table_name} RENAME COLUMN "{old_name}" TO "{new_name}"'
            )

        _upgrade_column_types(conn, table_name)

        # Re-fetch column metadata after renames and type upgrades
        col_rows = conn.execute(
            f"SELECT column_name, data_type, is_nullable "
            f"FROM information_schema.columns "
            f"WHERE table_name = '{table_name}' AND table_schema = 'main' "
            f"ORDER BY ordinal_position"
        ).fetchall()

        columns = [
            ColumnMeta(name=r[0], dtype=str(r[1]), nullable=r[2] == "YES")
            for r in col_rows
        ]

        row_count_result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        row_count = row_count_result[0] if row_count_result else 0

        # Fetch preview rows
        preview: list[dict[str, str | None]] = []
        if col_rows:
            preview_result = conn.execute(
                f"SELECT * FROM {table_name} LIMIT {_PREVIEW_ROWS}"
            ).fetchall()
            col_names_clean = [c.name for c in columns]
            for row in preview_result:
                preview.append({
                    col_names_clean[i]: (str(v) if v is not None else None)
                    for i, v in enumerate(row)
                })

        return IngestionResult(
            table_name=table_name,
            duckdb_path=db_path,
            row_count=row_count,
            columns=columns,
            preview=preview,
            header_row=header_row,
            skipped_rows=header_row,
        )
    finally:
        conn.close()


def list_tables() -> list[dict[str, str | int]]:
    """List all tables in the shared spreadsheets DuckDB."""
    db_path = get_shared_duckdb_path()
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


def drop_table(table_name: str) -> bool:
    """Drop a single table from the shared spreadsheets DuckDB."""
    db_path = get_shared_duckdb_path()
    if not os.path.exists(db_path):
        return False

    conn = duckdb.connect(db_path)
    try:
        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        return True
    finally:
        conn.close()


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the shared spreadsheets DuckDB."""
    db_path = get_shared_duckdb_path()
    if not os.path.exists(db_path):
        return False

    conn = duckdb.connect(db_path, read_only=True)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            f"WHERE table_schema = 'main' AND table_name = '{table_name}'"
        ).fetchone()
        return bool(row and row[0] > 0)
    finally:
        conn.close()
