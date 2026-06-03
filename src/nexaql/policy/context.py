# Copyright (c) 2026-present NexaQL Contributors
"""User context and role helpers for policy enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UserContext:
    user_id: str
    roles: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)


# Sentinel for unauthenticated / anonymous access -- wildcard role grants full access.
ANONYMOUS = UserContext(user_id="anonymous", roles=["*"])


def has_role(user: UserContext, required_roles: Optional[List[str]]) -> bool:
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
