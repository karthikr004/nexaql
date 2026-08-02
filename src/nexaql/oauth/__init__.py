# Copyright (c) 2026-present NexaQL Contributors
"""OAuth provider abstractions for NexaQL authentication."""

from nexaql.oauth.models import OAuthProviderConfig, OAuthUserInfo
from nexaql.oauth.providers import get_provider, GoogleOAuth, GitHubOAuth

__all__ = [
    "OAuthProviderConfig",
    "OAuthUserInfo",
    "get_provider",
    "GoogleOAuth",
    "GitHubOAuth",
]
