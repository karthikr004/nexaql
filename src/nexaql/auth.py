# Copyright (c) 2026-present NexaQL Contributors
"""JWT-based authentication for NexaQL user context.

When auth_mode is 'jwt', callers must pass a signed JWT token instead of
a raw user_context dict.  The server verifies the signature and extracts
user claims.  In 'dev' mode, raw user_context dicts are accepted as-is.
"""

from __future__ import annotations

from typing import Any

import jwt

from nexaql import bootstrap as bs
from nexaql.policy.context import CANONICAL_FIELDS, UserContext


class AuthError(Exception):
    """Raised when authentication fails."""


def get_auth_config() -> dict[str, Any]:
    """Load auth settings from the bootstrap DB."""
    cfg = bs.get_server_config()
    return {
        "auth_mode": cfg.get("auth_mode", "dev"),
        "auth_secret": cfg.get("auth_secret"),
        "auth_algorithm": cfg.get("auth_algorithm", "HS256"),
    }


def verify_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT token.  Returns the payload claims."""
    auth = get_auth_config()

    secret = auth["auth_secret"]
    if not secret:
        raise AuthError("JWT auth is enabled but no auth_secret is configured. Set it via the admin API.")

    algorithm = auth["auth_algorithm"]
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Invalid token: {e}")

    return payload


def resolve_user_context(
    auth_token: str | None = None,
    user_context: dict[str, Any] | None = None,
) -> UserContext:
    """Resolve a UserContext from either a JWT token or a raw dict.

    - In 'jwt' mode: auth_token is required and verified; user_context is ignored.
    - In 'dev' mode: user_context dict is trusted as-is; auth_token is also
      accepted (verified if auth_secret is configured, payload used directly
      if not).

    Returns a UserContext with admin roles if neither is provided.
    """
    auth = get_auth_config()
    mode = auth["auth_mode"]

    if mode == "jwt":
        if not auth_token:
            raise AuthError(
                "Authentication required. Pass auth_token (a signed JWT) with your request. "
                "Raw user_context is not accepted when auth_mode is 'jwt'."
            )
        claims = verify_token(auth_token)
        return _claims_to_user_context(claims)

    # dev mode
    if auth_token:
        if auth["auth_secret"]:
            claims = verify_token(auth_token)
        else:
            claims = jwt.decode(auth_token, options={"verify_signature": False})
        return _claims_to_user_context(claims)

    return _dict_to_user_context(user_context)


def _claims_to_user_context(claims: dict[str, Any]) -> UserContext:
    """Convert JWT claims to a UserContext."""
    canonical: dict[str, Any] = {}
    attributes: dict[str, Any] = {}

    # JWT standard claims mapping
    if "sub" in claims and "user_id" not in claims:
        claims["user_id"] = claims["sub"]

    for k, v in claims.items():
        if k in ("iss", "exp", "iat", "nbf", "aud", "jti", "sub"):
            continue
        if k == "roles":
            canonical["roles"] = v if isinstance(v, list) else [v]
        elif k in CANONICAL_FIELDS:
            canonical[k] = v
        else:
            attributes[k] = v

    if "roles" not in canonical:
        canonical["roles"] = ["admin"]

    return UserContext(**canonical, attributes=attributes)


def _dict_to_user_context(user_context: dict[str, Any] | None) -> UserContext:
    """Convert a raw dict to a UserContext (dev mode only)."""
    if not user_context:
        return UserContext(roles=["admin"])

    canonical: dict[str, Any] = {}
    attributes: dict[str, Any] = {}

    for k, v in user_context.items():
        if k == "roles":
            canonical["roles"] = v if isinstance(v, list) else [v]
        elif k in CANONICAL_FIELDS:
            canonical[k] = v
        else:
            attributes[k] = v

    if "roles" not in canonical:
        canonical["roles"] = ["admin"]

    return UserContext(**canonical, attributes=attributes)
