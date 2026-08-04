# Copyright (c) 2026-present NexaQL Contributors
"""Google Drive provider — OAuth, file listing, and download."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from nexaql.cloud_drive.models import CloudDriveFile


_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"

_SCOPES = "openid email profile https://www.googleapis.com/auth/drive.readonly"

_SPREADSHEET_MIME_TYPES = {
    "application/vnd.google-apps.spreadsheet",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/tab-separated-values",
}

_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

_FIELDS = "nextPageToken,files(id,name,mimeType,size,modifiedTime,parents)"


class GoogleDriveProvider:
    """Google Drive API v3 provider."""

    provider_name = "google_drive"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def get_authorize_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _SCOPES,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def get_account_info(self, access_token: str) -> dict[str, str]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                _USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
        return {
            "email": data["email"],
            "name": data.get("name", ""),
        }

    async def list_files(
        self,
        access_token: str,
        folder_id: str | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        q_parts = ["trashed = false"]

        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")
        else:
            q_parts.append("'root' in parents")

        mime_filter = " or ".join(
            f"mimeType = '{mt}'"
            for mt in sorted(_SPREADSHEET_MIME_TYPES | {_FOLDER_MIME_TYPE})
        )
        q_parts.append(f"({mime_filter})")

        params: dict[str, str] = {
            "q": " and ".join(q_parts),
            "fields": _FIELDS,
            "pageSize": "100",
            "orderBy": "folder,name",
        }
        if page_token:
            params["pageToken"] = page_token

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                _DRIVE_FILES_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        files: list[dict[str, Any]] = []
        for item in data.get("files", []):
            is_folder = item["mimeType"] == _FOLDER_MIME_TYPE
            files.append(
                CloudDriveFile(
                    id=item["id"],
                    name=item["name"],
                    mime_type=item["mimeType"],
                    size=int(item["size"]) if "size" in item else None,
                    modified_at=item.get("modifiedTime"),
                    is_folder=is_folder,
                    parent_id=item.get("parents", [None])[0],
                ).model_dump()
            )

        return {
            "files": files,
            "next_page_token": data.get("nextPageToken"),
        }

    async def download_file(
        self,
        access_token: str,
        file_id: str,
        mime_type: str,
    ) -> bytes:
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            if mime_type == "application/vnd.google-apps.spreadsheet":
                resp = await client.get(
                    f"{_DRIVE_FILES_URL}/{file_id}/export",
                    headers=headers,
                    params={"mimeType": "text/csv"},
                    follow_redirects=True,
                )
            else:
                resp = await client.get(
                    f"{_DRIVE_FILES_URL}/{file_id}",
                    headers=headers,
                    params={"alt": "media"},
                    follow_redirects=True,
                )
            resp.raise_for_status()
            return resp.content
