# Copyright (c) 2026-present NexaQL Contributors
"""FastAPI dependencies for authentication and user context extraction."""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException, Request

from nexaql import bootstrap as bs
from nexaql.api.routes.auth import _verify_session_token, _SESSION_COOKIE
from nexaql.policy.context import ANONYMOUS, CANONICAL_FIELDS, UserContext

logger = logging.getLogger(__name__)

_KNOWN_FIELDS = CANONICAL_FIELDS | {"roles"}


async def get_user_context(request: Request) -> UserContext:
    """Extract a :class:`UserContext` from the incoming request.

    Behavior depends on auth_mode:
    - ``dev``: read X-User-Context header, fall back to ANONYMOUS.
    - ``oauth``: verify session cookie JWT, return 401 if missing/invalid.
    """
    cfg = bs.get_server_config()
    auth_mode = cfg.get("auth_mode", "dev")

    if auth_mode == "oauth":
        return _oauth_mode_context(request)

    return _dev_mode_context(request)


def _oauth_mode_context(request: Request) -> UserContext:
    """Extract user from session cookie in oauth mode."""
    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    claims = _verify_session_token(token)
    roles = claims.get("roles", [])
    return UserContext(
        user_id=claims.get("sub", ""),
        roles=roles,
        name=claims.get("name"),
        email=claims.get("email"),
    )


def _dev_mode_context(request: Request) -> UserContext:
    """Extract user from X-User-Context header in dev mode."""
    header_value = request.headers.get("X-User-Context")
    if not header_value:
        return ANONYMOUS

    try:
        data = json.loads(header_value)

        extra_attrs = data.get("attributes", {})
        for key, value in data.items():
            if key not in _KNOWN_FIELDS and key != "attributes":
                extra_attrs[key] = value

        return UserContext(
            user_id=data.get("user_id", "anonymous"),
            roles=data.get("roles", []),
            name=data.get("name"),
            email=data.get("email"),
            manager_id=data.get("manager_id"),
            region=data.get("region"),
            department=data.get("department"),
            team_id=data.get("team_id"),
            level=data.get("level"),
            job_role=data.get("job_role"),
            org_id=data.get("org_id"),
            attributes=extra_attrs,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning(
            "Malformed X-User-Context header, falling back to ANONYMOUS: %s", exc
        )
        return ANONYMOUS


async def require_admin(request: Request) -> None:
    """Dependency that ensures the current user has the admin role."""
    user = await get_user_context(request)
    if "*" in user.roles:
        return
    if "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Admin access required")
