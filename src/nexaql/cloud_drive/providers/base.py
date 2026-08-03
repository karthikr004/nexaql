# Copyright (c) 2026-present NexaQL Contributors
"""Base protocol for cloud drive providers."""

from __future__ import annotations

from typing import Any, Protocol

from nexaql.cloud_drive.models import CloudDriveFile


class CloudDriveProvider(Protocol):
    """Protocol that all cloud drive providers must implement."""

    provider_name: str

    def get_authorize_url(self, redirect_uri: str, state: str) -> str: ...

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]: ...

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]: ...

    async def get_account_info(self, access_token: str) -> dict[str, str]: ...

    async def list_files(
        self,
        access_token: str,
        folder_id: str | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]: ...

    async def download_file(
        self,
        access_token: str,
        file_id: str,
        mime_type: str,
    ) -> bytes: ...
