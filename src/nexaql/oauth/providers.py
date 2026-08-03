# Copyright (c) 2026-present NexaQL Contributors
"""OAuth provider implementations for Google and GitHub."""

from __future__ import annotations

import secrets
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx

from nexaql.oauth.models import OAuthProviderConfig, OAuthUserInfo


class OAuthProvider(Protocol):
    """Protocol that all OAuth providers must implement."""

    provider_name: str

    def get_authorize_url(self, redirect_uri: str, state: str) -> str: ...

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]: ...

    async def get_user_info(self, access_token: str) -> OAuthUserInfo: ...


class GoogleOAuth:
    """Google OIDC provider."""

    provider_name = "google"

    _AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

    def __init__(self, config: OAuthProviderConfig) -> None:
        self._client_id = config.client_id
        self._client_secret = config.client_secret

    def get_authorize_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "select_account",
        }
        return f"{self._AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._TOKEN_URL,
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

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self._USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
        return OAuthUserInfo(
            provider="google",
            sub=data["sub"],
            email=data["email"],
            name=data.get("name"),
            avatar_url=data.get("picture"),
        )


class GitHubOAuth:
    """GitHub OAuth2 provider."""

    provider_name = "github"

    _AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    _TOKEN_URL = "https://github.com/login/oauth/access_token"
    _USER_URL = "https://api.github.com/user"
    _EMAILS_URL = "https://api.github.com/user/emails"

    def __init__(self, config: OAuthProviderConfig) -> None:
        self._client_id = config.client_id
        self._client_secret = config.client_secret

    def get_authorize_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "scope": "read:user user:email",
            "state": state,
        }
        return f"{self._AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient() as client:
            user_resp = await client.get(self._USER_URL, headers=headers)
            user_resp.raise_for_status()
            user_data = user_resp.json()

            email = user_data.get("email")
            if not email:
                emails_resp = await client.get(self._EMAILS_URL, headers=headers)
                emails_resp.raise_for_status()
                for e in emails_resp.json():
                    if e.get("primary") and e.get("verified"):
                        email = e["email"]
                        break

        return OAuthUserInfo(
            provider="github",
            sub=str(user_data["id"]),
            email=email or "",
            name=user_data.get("name"),
            avatar_url=user_data.get("avatar_url"),
        )


_PROVIDER_CLASSES: dict[str, type[GoogleOAuth | GitHubOAuth]] = {
    "google": GoogleOAuth,
    "github": GitHubOAuth,
}


def get_provider(config: OAuthProviderConfig) -> GoogleOAuth | GitHubOAuth:
    """Factory: create an OAuth provider instance from config."""
    cls = _PROVIDER_CLASSES.get(config.provider)
    if cls is None:
        raise ValueError(f"Unsupported OAuth provider: {config.provider}")
    return cls(config)


def generate_state() -> str:
    """Generate a cryptographically secure state parameter."""
    return secrets.token_urlsafe(32)
