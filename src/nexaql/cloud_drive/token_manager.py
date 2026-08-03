# Copyright (c) 2026-present NexaQL Contributors
"""Token manager — automatic refresh for cloud drive OAuth tokens."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from nexaql.bootstrap import get_cloud_drive_config, update_cloud_drive_tokens
from nexaql.cloud_drive.models import CloudDriveAccount, CloudDriveClientConfig
from nexaql.cloud_drive.providers import get_cloud_drive_provider

log = logging.getLogger(__name__)

_REFRESH_MARGIN_SECONDS = 300


class TokenManager:
    """Ensures a valid access token before every provider API call."""

    def __init__(self, account: CloudDriveAccount) -> None:
        self._account = account

    async def get_valid_token(self) -> str:
        if not self._is_expired():
            return self._account.access_token

        log.info("Token for %s expired, refreshing", self._account.email)
        config_row = get_cloud_drive_config(self._account.provider)
        if config_row is None:
            raise RuntimeError(
                f"No cloud drive config for provider: {self._account.provider}"
            )

        config = CloudDriveClientConfig(**config_row)
        provider = get_cloud_drive_provider(config)

        token_data = await provider.refresh_access_token(
            self._account.refresh_token,
        )

        new_access = token_data["access_token"]
        new_refresh = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")
        new_expires_at: str | None = None
        if expires_in:
            ts = datetime.now(timezone.utc).timestamp() + int(expires_in)
            new_expires_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        update_cloud_drive_tokens(
            account_id=self._account.id,
            access_token=new_access,
            refresh_token=new_refresh,
            token_expires_at=new_expires_at,
        )

        self._account.access_token = new_access
        if new_refresh:
            self._account.refresh_token = new_refresh
        self._account.token_expires_at = new_expires_at

        return new_access

    def _is_expired(self) -> bool:
        if self._account.token_expires_at is None:
            return False
        try:
            expires = datetime.fromisoformat(self._account.token_expires_at)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            return (expires - now).total_seconds() < _REFRESH_MARGIN_SECONDS
        except (ValueError, TypeError):
            return True
