# Copyright (c) 2026-present NexaQL Contributors
"""Admin endpoints for user management and auth configuration."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nexaql import bootstrap as bs

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Request / Response models ──────────────────────────────────────────────


class UserResponse(BaseModel):
    id: int
    email: str
    name: str | None
    avatar_url: str | None
    oauth_provider: str
    roles: list[str]
    is_active: bool
    created_at: str | None
    last_login_at: str | None


class UpdateRolesRequest(BaseModel):
    roles: list[str]


class UpdateActiveRequest(BaseModel):
    is_active: bool


class AuthConfigResponse(BaseModel):
    auth_mode: str
    providers: list[dict]


class OAuthProviderRequest(BaseModel):
    provider: Literal["google", "github"]
    client_id: str
    client_secret: str
    enabled: bool = True


class UpdateAuthModeRequest(BaseModel):
    auth_mode: Literal["dev", "oauth"]


# ── User CRUD ──────────────────────────────────────────────────────────────


@router.get("/users")
async def list_users() -> list[UserResponse]:
    users = bs.list_users()
    return [UserResponse(**_strip_oauth_sub(u)) for u in users]


@router.put("/users/{user_id}/roles")
async def update_roles(user_id: int, req: UpdateRolesRequest) -> UserResponse:
    user = bs.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    bs.update_user_roles(user_id, req.roles)
    user["roles"] = req.roles
    return UserResponse(**_strip_oauth_sub(user))


@router.put("/users/{user_id}/active")
async def update_active(user_id: int, req: UpdateActiveRequest) -> UserResponse:
    user = bs.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    bs.deactivate_user(user_id, active=req.is_active)
    user["is_active"] = req.is_active
    return UserResponse(**_strip_oauth_sub(user))


# ── Auth configuration ─────────────────────────────────────────────────────


@router.get("/auth-config")
async def get_auth_config() -> AuthConfigResponse:
    cfg = bs.get_server_config()
    providers = bs.get_oauth_providers()
    masked = [_mask_provider(p) for p in providers]
    return AuthConfigResponse(
        auth_mode=cfg.get("auth_mode", "dev"),
        providers=masked,
    )


@router.put("/auth-config")
async def update_auth_config(req: UpdateAuthModeRequest) -> AuthConfigResponse:
    if req.auth_mode == "oauth":
        providers = bs.get_oauth_providers()
        enabled = [p for p in providers if p.get("enabled", True)]
        if not enabled:
            raise HTTPException(
                status_code=400,
                detail="Cannot enable OAuth: configure at least one OAuth provider first",
            )
    bs.update_server_config(auth_mode=req.auth_mode)
    return await get_auth_config()


# ── OAuth provider management ──────────────────────────────────────────────


@router.post("/oauth-providers")
async def add_oauth_provider(req: OAuthProviderRequest) -> AuthConfigResponse:
    bs.save_oauth_provider(
        provider=req.provider,
        client_id=req.client_id,
        client_secret=req.client_secret,
        enabled=req.enabled,
    )
    return await get_auth_config()


@router.delete("/oauth-providers/{provider}")
async def remove_oauth_provider(provider: str) -> AuthConfigResponse:
    deleted = bs.delete_oauth_provider(provider)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")
    return await get_auth_config()


# ── Helpers ────────────────────────────────────────────────────────────────


def _strip_oauth_sub(user: dict) -> dict:
    """Remove oauth_sub from user dict (internal field, not exposed via API)."""
    return {k: v for k, v in user.items() if k != "oauth_sub"}


def _mask_provider(p: dict) -> dict:
    """Mask the client_secret in provider config."""
    masked = dict(p)
    secret = masked.get("client_secret", "")
    if len(secret) > 8:
        masked["client_secret"] = secret[:4] + "****" + secret[-4:]
    elif secret:
        masked["client_secret"] = "****"
    return masked
