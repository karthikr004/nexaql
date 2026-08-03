# Copyright (c) 2026-present NexaQL Contributors
"""Spreadsheet uploads — ingest CSV/TSV files into a shared DuckDB connector."""

from __future__ import annotations

import os

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse

from nexaql import bootstrap as bs
from nexaql.api.deps import _adapter_cache, reload_config
from nexaql.spreadsheet.ingestion import (
    SPREADSHEETS_CONNECTOR_NAME,
    _clean_table_name,
    drop_table,
    get_shared_duckdb_path,
    get_uploads_dir,
    ingest_csv,
    list_tables,
    table_exists,
)

router = APIRouter(tags=["spreadsheet"])

_ALLOWED_EXTENSIONS = {".csv", ".tsv", ".txt"}
_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


def _ensure_spreadsheets_connector() -> int:
    """Get or create the shared spreadsheets connector."""
    existing = bs.get_connector(SPREADSHEETS_CONNECTOR_NAME)
    if existing:
        return existing["id"]

    return bs.save_connector(
        name=SPREADSHEETS_CONNECTOR_NAME,
        type="duckdb",
        url=get_shared_duckdb_path(),
    )


@router.post("/connectors/upload")
async def upload_spreadsheet(file: UploadFile) -> JSONResponse:
    """Upload a CSV/TSV file into the shared spreadsheets DuckDB."""
    if not file.filename:
        return JSONResponse({"error": "No file provided"}, status_code=400)

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return JSONResponse(
            {"error": f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"},
            status_code=400,
        )

    content = await file.read()
    if len(content) > _MAX_FILE_SIZE:
        return JSONResponse(
            {"error": f"File too large ({len(content) // (1024*1024)}MB). Maximum: {_MAX_FILE_SIZE // (1024*1024)}MB"},
            status_code=400,
        )

    uploads_dir = get_uploads_dir()
    file_path = os.path.join(uploads_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(content)

    table_name = _clean_table_name(file.filename)
    replaced = table_exists(table_name)

    delimiter = "\t" if ext == ".tsv" else None

    try:
        result = ingest_csv(
            file_path=file_path,
            table_name=table_name,
            delimiter=delimiter,
        )
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        return JSONResponse({"error": f"Failed to process file: {e}"}, status_code=400)

    connector_id = _ensure_spreadsheets_connector()

    columns_info = [
        {"name": col.name, "type": col.dtype, "nullable": col.nullable}
        for col in result.columns
    ]

    return JSONResponse({
        "status": "replaced" if replaced else "uploaded",
        "connector_id": connector_id,
        "connector_name": SPREADSHEETS_CONNECTOR_NAME,
        "table_name": result.table_name,
        "row_count": result.row_count,
        "column_count": len(result.columns),
        "columns": columns_info,
        "preview": result.preview,
        "file_name": file.filename,
        "duckdb_path": result.duckdb_path,
        "header_row": result.header_row,
        "skipped_rows": result.skipped_rows,
    })


@router.get("/spreadsheet/tables")
async def get_spreadsheet_tables() -> JSONResponse:
    """List all tables in the shared spreadsheets DuckDB."""
    tables = list_tables()
    return JSONResponse({"tables": tables})


@router.delete("/spreadsheet/tables/{table_name}")
async def delete_spreadsheet_table(table_name: str) -> JSONResponse:
    """Drop a single table from the shared spreadsheets DuckDB."""
    if not table_exists(table_name):
        return JSONResponse({"error": f"Table '{table_name}' not found"}, status_code=404)

    drop_table(table_name)

    # If no tables remain, clean up the connector
    remaining = list_tables()
    if not remaining:
        connector = bs.get_connector(SPREADSHEETS_CONNECTOR_NAME)
        if connector:
            try:
                bs.delete_connector(SPREADSHEETS_CONNECTOR_NAME)
            except ValueError:
                pass

    _adapter_cache.clear()
    reload_config()

    return JSONResponse({"status": "deleted", "table_name": table_name})
