# Copyright (c) 2026-present NexaQL Contributors
"""Pydantic models for cloud drive configuration and file browsing."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


CloudDriveProviderType = Literal["google_drive", "onedrive", "dropbox"]


class CloudDriveClientConfig(BaseModel):
    """OAuth client credentials for a cloud drive provider."""

    provider: CloudDriveProviderType
    client_id: str
    client_secret: str
    enabled: bool = True


class CloudDriveAccount(BaseModel):
    """A connected cloud drive account with OAuth tokens."""

    id: int
    provider: str
    email: str
    display_name: str | None = None
    access_token: str
    refresh_token: str
    token_expires_at: str | None = None
    created_at: str


class CloudDriveFile(BaseModel):
    """A file or folder entry from a cloud drive listing."""

    id: str
    name: str
    mime_type: str
    size: int | None = None
    modified_at: str | None = None
    is_folder: bool
    parent_id: str | None = None
