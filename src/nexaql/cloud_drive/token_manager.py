# Copyright (c) 2026-present NexaQL Contributors
"""Token manager — automatic refresh for cloud drive OAuth tokens."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from nexaql.bootstrap import get_cloud_drive_credentials, update_cloud_drive_tokens
from nexaql.cloud_drive.providers import get_cloud_drive_provider

log = logging.getLogger(__name__)

_REFRESH_MARGIN_SECONDS = 300


class TokenManager:
    """Ensures a valid access token before every provider API call."""

    def __init__(self, connector_id: int, account_id: int,
                 email: str, access_token: str, refresh_token: str,
                 token_expires_at: str | None = None) -> None:
        self._connector_id = connector_id
        self._account_id = account_id
        self._email = email
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expires_at = token_expires_at

    async def get_valid_token(self) -> str:
        if not self._is_expired():
            return self._access_token

        log.info("Token for %s expired, refreshing", self._email)
        creds = get_cloud_drive_credentials(self._connector_id)
        if creds is None:
            raise RuntimeError(
                f"No cloud drive connector found for id: {self._connector_id}"
            )

        provider = get_cloud_drive_provider(creds)
        token_data = await provider.refresh_access_token(self._refresh_token)

        new_access = token_data["access_token"]
        new_refresh = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")
        new_expires_at: str | None = None
        if expires_in:
            ts = datetime.now(timezone.utc).timestamp() + int(expires_in)
            new_expires_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

        update_cloud_drive_tokens(
            account_id=self._account_id,
            access_token=new_access,
            refresh_token=new_refresh,
            token_expires_at=new_expires_at,
        )

        self._access_token = new_access
        if new_refresh:
            self._refresh_token = new_refresh
        self._token_expires_at = new_expires_at

        return new_access

    def _is_expired(self) -> bool:
        if self._token_expires_at is None:
            return False
        try:
            expires = datetime.fromisoformat(self._token_expires_at)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            return (expires - now).total_seconds() < _REFRESH_MARGIN_SECONDS
        except (ValueError, TypeError):
            return True
