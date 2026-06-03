# Copyright (c) 2026-present NexaQL Contributors
"""FastAPI dependency that extracts UserContext from the request."""

from __future__ import annotations

import json
import logging

from fastapi import Request

from nexaql.policy.context import ANONYMOUS, UserContext

logger = logging.getLogger(__name__)


async def get_user_context(request: Request) -> UserContext:
    """Extract a :class:`UserContext` from the incoming request.

    Dev mode (default):
    - Check the ``X-User-Context`` header.  If present, parse it as JSON
      into a :class:`UserContext`.
    - If the header is absent, return :data:`ANONYMOUS` (full access,
      ``roles=["*"]``).

    Malformed JSON is handled gracefully: a warning is logged and
    :data:`ANONYMOUS` is returned so the request is not blocked by a
    bad header.
    """
    header_value = request.headers.get("X-User-Context")
    if not header_value:
        return ANONYMOUS

    try:
        data = json.loads(header_value)
        return UserContext(
            user_id=data.get("user_id", "anonymous"),
            roles=data.get("roles", []),
            attributes=data.get("attributes", {}),
        )
    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning(
            "Malformed X-User-Context header, falling back to ANONYMOUS: %s", exc
        )
        return ANONYMOUS
