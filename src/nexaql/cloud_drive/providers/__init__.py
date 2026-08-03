# Copyright (c) 2026-present NexaQL Contributors
"""Cloud drive provider implementations."""

from __future__ import annotations

from nexaql.cloud_drive.models import CloudDriveClientConfig
from nexaql.cloud_drive.providers.base import CloudDriveProvider
from nexaql.cloud_drive.providers.google_drive import GoogleDriveProvider


_PROVIDER_CLASSES: dict[str, type] = {
    "google_drive": GoogleDriveProvider,
}


def get_cloud_drive_provider(config: CloudDriveClientConfig) -> CloudDriveProvider:
    """Factory: create a cloud drive provider instance from config."""
    cls = _PROVIDER_CLASSES.get(config.provider)
    if cls is None:
        raise ValueError(f"Unsupported cloud drive provider: {config.provider}")
    return cls(config)
