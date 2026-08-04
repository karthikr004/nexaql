# Copyright (c) 2026-present NexaQL Contributors
"""Cloud drive routes — OAuth, file browsing, and import."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from nexaql import bootstrap as bs
from nexaql.api.deps import _adapter_cache, reload_config
from nexaql.cloud_drive.providers import get_cloud_drive_provider
from nexaql.cloud_drive.token_manager import TokenManager
from nexaql.oauth.providers import generate_state
from nexaql.spreadsheet.ingestion import (
    SPREADSHEETS_CONNECTOR_NAME,
    _clean_table_name,
    get_shared_duckdb_path,
    get_uploads_dir,
    ingest_csv,
    table_exists,
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["cloud-drive"])

_pending_states: dict[str, int] = {}


# ── Request bodies ─────────────────────────────────────────────────────────


class ImportFileBody(BaseModel):
    file_id: str
    file_name: str
    mime_type: str


# ── Helpers ────────────────────────────────────────────────────────────────


def _ensure_spreadsheets_connector() -> int:
    existing = bs.get_connector(SPREADSHEETS_CONNECTOR_NAME)
    if existing:
        return existing["id"]
    return bs.save_connector(
        name=SPREADSHEETS_CONNECTOR_NAME,
        type="duckdb",
        url=get_shared_duckdb_path(),
    )


def _build_redirect_uri(request: Request, provider: str) -> str:
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get(
        "x-forwarded-host", request.headers.get("host", "localhost")
    )
    return f"{scheme}://{host}/api/cloud-drive/callback/{provider}"


def _get_creds_or_404(connector_id: int) -> dict:
    creds = bs.get_cloud_drive_credentials(connector_id)
    if not creds:
        raise HTTPException(status_code=404, detail="Cloud drive connector not found")
    return creds


def _build_token_manager(account: dict) -> TokenManager:
    return TokenManager(
        connector_id=account["connector_id"],
        account_id=account["id"],
        email=account["email"],
        access_token=account["access_token"],
        refresh_token=account["refresh_token"],
        token_expires_at=account.get("token_expires_at"),
    )


# ── Account connection (OAuth) ─────────────────────────────────────────────


@router.get("/cloud-drive/accounts")
async def list_accounts() -> JSONResponse:
    rows = bs.list_cloud_drive_accounts()
    result = []
    for row in rows:
        result.append({
            "id": row["id"],
            "connector_id": row["connector_id"],
            "provider": row["provider"],
            "email": row["email"],
            "display_name": row.get("display_name"),
            "created_at": row["created_at"],
        })
    return JSONResponse({"accounts": result})


@router.get("/cloud-drive/connect/{connector_id}")
async def connect(connector_id: int, request: Request) -> JSONResponse:
    creds = _get_creds_or_404(connector_id)
    provider = creds["provider"]
    drv = get_cloud_drive_provider(creds)
    state = generate_state()
    _pending_states[state] = connector_id
    redirect_uri = _build_redirect_uri(request, provider)
    url = drv.get_authorize_url(redirect_uri, state)
    return JSONResponse({"authorize_url": url})


@router.get("/cloud-drive/callback/{provider}")
async def callback(
    provider: str, request: Request, code: str = "", state: str = ""
) -> HTMLResponse:
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    connector_id = _pending_states.pop(state, None)
    if connector_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    creds = _get_creds_or_404(connector_id)
    drv = get_cloud_drive_provider(creds)
    redirect_uri = _build_redirect_uri(request, provider)

    try:
        token_data = await drv.exchange_code(code, redirect_uri)
    except Exception as e:
        log.error("Cloud drive token exchange failed: %s", e)
        raise HTTPException(status_code=502, detail="Token exchange failed")

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in")

    token_expires_at: str | None = None
    if expires_in:
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).timestamp() + int(expires_in)
        token_expires_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    try:
        info = await drv.get_account_info(access_token)
    except Exception as e:
        log.error("Cloud drive account info failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to fetch account info")

    account_id = bs.save_cloud_drive_account(
        connector_id=connector_id,
        email=info["email"],
        display_name=info.get("name"),
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=token_expires_at,
    )

    html = f"""<!doctype html>
<html><body><script>
window.opener.postMessage({{
  type: "cloud-drive-connected",
  provider: "{provider}",
  email: "{info['email']}",
  accountId: {account_id}
}}, window.location.origin);
window.close();
</script></body></html>"""
    return HTMLResponse(html)


@router.delete("/cloud-drive/accounts/{account_id}")
async def disconnect(account_id: int) -> JSONResponse:
    deleted = bs.delete_cloud_drive_account(account_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Account not found")
    return JSONResponse({"status": "disconnected"})


# ── Browse + Import ────────────────────────────────────────────────────────


@router.get("/cloud-drive/browse/{account_id}")
async def browse(
    account_id: int,
    folder_id: str | None = None,
    page_token: str | None = None,
) -> JSONResponse:
    account = bs.get_cloud_drive_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    mgr = _build_token_manager(account)
    token = await mgr.get_valid_token()

    creds = _get_creds_or_404(account["connector_id"])
    drv = get_cloud_drive_provider(creds)

    try:
        result = await drv.list_files(token, folder_id=folder_id, page_token=page_token)
    except Exception as e:
        log.error("Cloud drive browse failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to list files")

    return JSONResponse(result)


@router.post("/cloud-drive/import/{account_id}")
async def import_file(account_id: int, body: ImportFileBody) -> JSONResponse:
    account = bs.get_cloud_drive_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    mgr = _build_token_manager(account)
    token = await mgr.get_valid_token()

    creds = _get_creds_or_404(account["connector_id"])
    drv = get_cloud_drive_provider(creds)

    try:
        content = await drv.download_file(token, body.file_id, body.mime_type)
    except Exception as e:
        log.error("Cloud drive download failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to download file")

    table_name = _clean_table_name(body.file_name)
    uploads_dir = get_uploads_dir()

    is_xlsx = body.mime_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    if is_xlsx:
        file_path = os.path.join(uploads_dir, f"{table_name}.xlsx")
    else:
        file_path = os.path.join(uploads_dir, f"{table_name}.csv")

    with open(file_path, "wb") as f:
        f.write(content)

    replaced = table_exists(table_name)

    try:
        if is_xlsx:
            from nexaql.spreadsheet.ingestion import ingest_xlsx

            result = ingest_xlsx(file_path=file_path, table_name=table_name)
        else:
            result = ingest_csv(file_path=file_path, table_name=table_name)
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=400, detail=f"Failed to ingest file: {e}"
        )

    connector_id = _ensure_spreadsheets_connector()

    _adapter_cache.clear()
    reload_config()

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
        "file_name": body.file_name,
        "duckdb_path": result.duckdb_path,
        "header_row": result.header_row,
        "skipped_rows": result.skipped_rows,
    })
