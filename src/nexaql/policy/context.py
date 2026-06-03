# Copyright (c) 2026-present NexaQL Contributors
"""User context and role helpers for policy enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union


@dataclass
class UserContext:
    """Represents the authenticated user for access control.

    Canonical fields are typed and always available for policy resolution.
    Custom attributes provide extensibility for org-specific policies.
    """

    # -- Identity (required) --
    user_id: Union[str, int] = ""
    roles: list[str] = field(default_factory=list)

    # -- Standard profile fields (optional) --
    name: Optional[str] = None
    email: Optional[str] = None
    manager_id: Optional[Union[str, int]] = None
    region: Optional[str] = None
    department: Optional[str] = None
    team_id: Optional[Union[str, int]] = None
    level: Optional[str] = None
    job_role: Optional[str] = None
    org_id: Optional[Union[str, int]] = None

    # -- Custom attributes (extensible) --
    attributes: dict[str, Any] = field(default_factory=dict)


# All canonical field names (for resolving {user.xxx} placeholders)
CANONICAL_FIELDS = {
    "user_id", "name", "email", "manager_id", "region",
    "department", "team_id", "level", "job_role", "org_id",
}

# Sentinel for unauthenticated / anonymous access -- wildcard role grants full access.
ANONYMOUS = UserContext(user_id="anonymous", roles=["*"])


def has_role(user: UserContext, required_roles: Optional[list[str]]) -> bool:
    """Check whether *user* satisfies *required_roles*.

    Returns ``True`` when:
    - *required_roles* is ``None`` or empty (no restriction).
    - The user has the wildcard role ``"*"`` (superadmin).
    - Any role in ``user.roles`` appears in *required_roles*.
    """
    if not required_roles:
        return True
    if "*" in user.roles:
        return True
    return bool(set(user.roles) & set(required_roles))


def resolve_user_value(user: UserContext, key: str) -> Any:
    """Resolve a {user.xxx} placeholder key to its value.
    Checks canonical fields first, then attributes.
    Returns None if not found.
    """
    if key in CANONICAL_FIELDS:
        return getattr(user, key, None)
    return user.attributes.get(key)
