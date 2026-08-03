# Copyright (c) 2026-present NexaQL Contributors
"""Spreadsheet connector — upload CSV/TSV files and query them via DuckDB."""

from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse

from nexaql import bootstrap as bs
from nexaql.api.deps import _adapter_cache, reload_config
from nexaql.spreadsheet.ingestion import (
    get_duckdb_path,
    get_uploads_dir,
    ingest_csv,
    list_tables,
)

router = APIRouter(tags=["spreadsheet"])

_ALLOWED_EXTENSIONS = {".csv", ".tsv", ".txt"}
_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


@router.post("/connectors/upload")
async def upload_spreadsheet(file: UploadFile) -> JSONResponse:
    """Upload a CSV/TSV file and create a connector backed by DuckDB."""
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

    stem = os.path.splitext(file.filename)[0]
    connector_name = "".join(c if c.isalnum() or c == "_" or c == "-" else "_" for c in stem).lower()
    if not connector_name:
        connector_name = "uploaded_csv"

    existing = bs.get_connector(connector_name)
    if existing:
        return JSONResponse(
            {"error": f"Connector '{connector_name}' already exists. Delete it first or rename your file."},
            status_code=409,
        )

    delimiter = "\t" if ext == ".tsv" else None

    try:
        result = ingest_csv(
            file_path=file_path,
            connector_name=connector_name,
            delimiter=delimiter,
        )
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        return JSONResponse({"error": f"Failed to process file: {e}"}, status_code=400)

    connector_id = bs.save_connector(
        name=connector_name,
        type="csv",
        url=result.duckdb_path,
    )

    columns_info = [
        {"name": col.name, "type": col.dtype, "nullable": col.nullable}
        for col in result.columns
    ]

    return JSONResponse({
        "status": "uploaded",
        "connector_id": connector_id,
        "connector_name": connector_name,
        "table_name": result.table_name,
        "row_count": result.row_count,
        "column_count": len(result.columns),
        "columns": columns_info,
        "file_name": file.filename,
        "duckdb_path": result.duckdb_path,
    })


@router.get("/connectors/{name}/spreadsheet-tables")
async def get_spreadsheet_tables(name: str) -> JSONResponse:
    """List tables in a spreadsheet connector's DuckDB file."""
    connector = bs.get_connector(name)
    if connector is None:
        return JSONResponse({"error": f"Connector '{name}' not found"}, status_code=404)

    if connector.get("type") != "csv":
        return JSONResponse(
            {"error": f"Connector '{name}' is not a spreadsheet connector"},
            status_code=400,
        )

    tables = list_tables(name)
    return JSONResponse({"tables": tables})


@router.delete("/connectors/{name}/spreadsheet")
async def delete_spreadsheet_connector(name: str) -> JSONResponse:
    """Delete a spreadsheet connector and its DuckDB file."""
    connector = bs.get_connector(name)
    if connector is None:
        return JSONResponse({"error": f"Connector '{name}' not found"}, status_code=404)

    if connector.get("type") != "csv":
        return JSONResponse(
            {"error": f"Connector '{name}' is not a spreadsheet connector"},
            status_code=400,
        )

    try:
        bs.delete_connector(name)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=409)

    db_path = get_duckdb_path(name)
    if os.path.exists(db_path):
        os.remove(db_path)

    _adapter_cache.clear()
    reload_config()

    return JSONResponse({"status": "deleted", "name": name})
