# Copyright (c) 2026-present NexaQL Contributors
"""Cloud drive provider implementations."""

from __future__ import annotations

from typing import Any

from nexaql.cloud_drive.providers.base import CloudDriveProvider
from nexaql.cloud_drive.providers.google_drive import GoogleDriveProvider


_PROVIDER_CLASSES: dict[str, type] = {
    "google_drive": GoogleDriveProvider,
}


def get_cloud_drive_provider(creds: dict[str, Any]) -> CloudDriveProvider:
    """Factory: create a cloud drive provider from connector credentials dict.

    Expects keys: provider, client_id, client_secret.
    """
    provider_type = creds["provider"]
    cls = _PROVIDER_CLASSES.get(provider_type)
    if cls is None:
        raise ValueError(f"Unsupported cloud drive provider: {provider_type}")
    return cls(client_id=creds["client_id"], client_secret=creds["client_secret"])
