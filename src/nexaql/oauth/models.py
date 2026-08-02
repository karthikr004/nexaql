# Copyright (c) 2026-present NexaQL Contributors
"""Pydantic models for OAuth configuration and user identity."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class OAuthProviderConfig(BaseModel):
    """Configuration for a single OAuth provider."""

    provider: Literal["google", "github"]
    client_id: str
    client_secret: str
    enabled: bool = True


class OAuthUserInfo(BaseModel):
    """Normalized user identity returned by an OAuth provider."""

    provider: str
    sub: str
    email: str
    name: str | None = None
    avatar_url: str | None = None
