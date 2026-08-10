# Copyright (c) 2026-present NexaQL Contributors
"""OAuth authentication routes: login, callback, logout, session."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any

import jwt
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

from nexaql import bootstrap as bs
from nexaql.oauth.models import OAuthProviderConfig
from nexaql.oauth.providers import get_provider, generate_state

log = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])

_SESSION_COOKIE = "nexaql_session"
_SESSION_EXPIRY_HOURS = 24

# In-memory state store (server restart clears pending logins — acceptable)
_pending_states: dict[str, str] = {}


def _get_session_secret() -> str:
    """Get or auto-generate the session signing secret."""
    cfg = bs.get_server_config()
    secret = cfg.get("auth_secret")
    if secret:
        return secret
    secret = secrets.token_urlsafe(48)
    bs.update_server_config(auth_secret=secret)
    return secret


def _build_redirect_uri(request: Request, provider: str) -> str:
    """Build the OAuth callback URL from the current request."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost"))
    return f"{scheme}://{host}/api/auth/callback/{provider}"


def _issue_session_token(user: dict[str, Any]) -> str:
    """Create a signed JWT session token for the user."""
    secret = _get_session_secret()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "name": user.get("name"),
        "roles": user.get("roles", []),
        "avatar_url": user.get("avatar_url"),
        "iat": now,
        "exp": now + timedelta(hours=_SESSION_EXPIRY_HOURS),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _verify_session_token(token: str) -> dict[str, Any]:
    """Verify and decode a session JWT. Raises HTTPException on failure."""
    secret = _get_session_secret()
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session")


def _get_enabled_providers() -> list[OAuthProviderConfig]:
    """Load enabled OAuth provider configs from the database."""
    raw = bs.get_oauth_providers()
    providers: list[OAuthProviderConfig] = []
    for p in raw:
        if p.get("enabled", True):
            try:
                providers.append(OAuthProviderConfig(**p))
            except Exception:
                log.warning("Invalid OAuth provider config: %s", p.get("provider"))
    return providers


@router.get("/auth/mode")
async def get_auth_mode() -> dict[str, str]:
    """Return the current authentication mode."""
    cfg = bs.get_server_config()
    return {"mode": cfg.get("auth_mode", "dev")}


@router.get("/auth/providers")
async def list_providers() -> dict[str, list[str]]:
    """List enabled OAuth provider names (for the login page)."""
    providers = _get_enabled_providers()
    return {"providers": [p.provider for p in providers]}


@router.get("/auth/login/{provider}")
async def login(provider: str, request: Request) -> RedirectResponse:
    """Initiate OAuth login by redirecting to the provider."""
    configs = _get_enabled_providers()
    config = next((c for c in configs if c.provider == provider), None)
    if not config:
        raise HTTPException(status_code=404, detail=f"OAuth provider '{provider}' not configured")

    oauth = get_provider(config)
    state = generate_state()
    _pending_states[state] = provider
    redirect_uri = _build_redirect_uri(request, provider)
    authorize_url = oauth.get_authorize_url(redirect_uri, state)
    return RedirectResponse(url=authorize_url, status_code=302)


@router.get("/auth/callback/{provider}")
async def callback(provider: str, request: Request, code: str = "", state: str = "") -> RedirectResponse:
    """Handle the OAuth callback: exchange code, create/update user, set session cookie."""
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    expected_provider = _pending_states.pop(state, None)
    if expected_provider != provider:
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter")

    configs = _get_enabled_providers()
    config = next((c for c in configs if c.provider == provider), None)
    if not config:
        raise HTTPException(status_code=404, detail=f"OAuth provider '{provider}' not configured")

    oauth = get_provider(config)
    redirect_uri = _build_redirect_uri(request, provider)

    try:
        token_data = await oauth.exchange_code(code, redirect_uri)
    except Exception as e:
        log.error("OAuth token exchange failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to exchange authorization code")

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="No access token received from provider")

    try:
        user_info = await oauth.get_user_info(access_token)
    except Exception as e:
        log.error("OAuth user info fetch failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to fetch user info from provider")

    if not user_info.email:
        raise HTTPException(status_code=400, detail="Email not available from OAuth provider")

    existing = bs.get_user_by_oauth(user_info.provider, user_info.sub)
    is_first_user = bs.count_users() == 0

    if not existing and not is_first_user and not bs.is_email_invited(user_info.email):
        log.warning("Rejected login from uninvited email: %s", user_info.email)
        return RedirectResponse(url="/login?error=not_invited", status_code=302)

    invite = bs.get_invite_by_email(user_info.email) if not existing else None

    user = bs.upsert_user(
        email=user_info.email,
        name=user_info.name,
        avatar_url=user_info.avatar_url,
        oauth_provider=user_info.provider,
        oauth_sub=user_info.sub,
    )

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")

    if is_first_user and not user.get("roles"):
        bs.update_user_roles(user["id"], ["admin"])
        user["roles"] = ["admin"]
    elif invite and invite.get("roles") and not existing:
        bs.update_user_roles(user["id"], invite["roles"])
        user["roles"] = invite["roles"]
        bs.revoke_invite(user_info.email)

    session_token = _issue_session_token(user)
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=_SESSION_COOKIE,
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=_SESSION_EXPIRY_HOURS * 3600,
        path="/",
    )
    return response


@router.post("/auth/logout")
async def logout() -> JSONResponse:
    """Clear the session cookie."""
    response = JSONResponse({"ok": True})
    response.delete_cookie(key=_SESSION_COOKIE, path="/")
    return response


@router.get("/auth/session")
async def get_session(request: Request) -> dict[str, Any]:
    """Return the current user from the session cookie, or unauthenticated status.

    Roles are always fetched from the database so the frontend
    reflects role changes without requiring re-login.
    """
    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        return {"authenticated": False}
    try:
        claims = _verify_session_token(token)
    except HTTPException:
        return {"authenticated": False}

    user_id = int(claims["sub"])
    db_user = bs.get_user_by_id(user_id)

    if db_user and not db_user.get("is_active", True):
        return {"authenticated": False}

    return {
        "authenticated": True,
        "user": {
            "id": user_id,
            "email": db_user["email"] if db_user else claims.get("email"),
            "name": db_user.get("name") if db_user else claims.get("name"),
            "roles": db_user["roles"] if db_user else claims.get("roles", []),
            "avatar_url": db_user.get("avatar_url") if db_user else claims.get("avatar_url"),
        },
    }
