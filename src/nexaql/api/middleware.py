# Copyright (c) 2026-present NexaQL Contributors
"""FastAPI dependency that extracts UserContext from the request."""

from __future__ import annotations

import json
import logging

from fastapi import Request

from nexaql.policy.context import ANONYMOUS, CANONICAL_FIELDS, UserContext

logger = logging.getLogger(__name__)

# Fields parsed directly into UserContext (not put into attributes)
_KNOWN_FIELDS = CANONICAL_FIELDS | {"roles"}


async def get_user_context(request: Request) -> UserContext:
    """Extract a :class:`UserContext` from the incoming request.

    Dev mode (default):
    - Check the ``X-User-Context`` header.  If present, parse it as JSON
      into a :class:`UserContext`.
    - If the header is absent, return :data:`ANONYMOUS` (full access,
      ``roles=["*"]``).

    All canonical fields (user_id, name, email, manager_id, region,
    department, team_id, level, job_role, org_id) are parsed into their
    typed slots.  Unknown keys are placed in ``attributes``.

    Malformed JSON is handled gracefully: a warning is logged and
    :data:`ANONYMOUS` is returned so the request is not blocked by a
    bad header.
    """
    header_value = request.headers.get("X-User-Context")
    if not header_value:
        return ANONYMOUS

    try:
        data = json.loads(header_value)

        # Separate known fields from extra attributes
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
