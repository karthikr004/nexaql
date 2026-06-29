# Copyright (c) 2026-present NexaQL Contributors
"""Shared test fixtures for NexaQL test suite."""

from __future__ import annotations

import jwt
import pytest
import pytest_asyncio

from nexaql.mcp_server import configure_auth, _invalidate_cache

JWT_SECRET = "nexaql-test-secret-key-at-least-32-bytes!!"


@pytest_asyncio.fixture(autouse=True)
async def reset_to_dev_mode():
    """Ensure every test starts and ends in dev mode."""
    await configure_auth(auth_mode="dev")
    _invalidate_cache()
    yield
    await configure_auth(auth_mode="dev")
    _invalidate_cache()


@pytest.fixture()
def jwt_secret():
    return JWT_SECRET


@pytest.fixture()
def make_token(jwt_secret):
    """Factory fixture to mint JWT tokens for testing."""
    def _make(claims: dict, secret: str | None = None, algorithm: str = "HS256") -> str:
        return jwt.encode(claims, secret or jwt_secret, algorithm=algorithm)
    return _make


@pytest.fixture()
def admin_token(make_token):
    return make_token({"sub": "alice", "roles": ["admin"]})


@pytest.fixture()
def analyst_token(make_token):
    return make_token({"sub": "bob", "roles": ["analyst"]})


def has_llm_key() -> bool:
    """Check if an LLM API key is available for chat tests."""
    try:
        from nexaql.bootstrap import get_api_key
        return bool(get_api_key("anthropic") or get_api_key("openai"))
    except Exception:
        return False


requires_llm = pytest.mark.skipif(
    not has_llm_key(),
    reason="No LLM API key configured (set ANTHROPIC_API_KEY or configure via admin panel)",
)
