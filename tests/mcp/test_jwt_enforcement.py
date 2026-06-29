# Copyright (c) 2026-present NexaQL Contributors
"""End-to-end JWT auth enforcement tests across all MCP tools."""

from __future__ import annotations

import pytest
import pytest_asyncio

from nexaql.mcp_server import (
    _invalidate_cache,
    ask,
    configure_auth,
    query,
    sql_preview,
    validate_query,
)


@pytest_asyncio.fixture(autouse=True)
async def jwt_mode(jwt_secret):
    """Put server in JWT mode for every test in this module."""
    await configure_auth(auth_mode="jwt", auth_secret=jwt_secret)
    _invalidate_cache()
    yield
    await configure_auth(auth_mode="dev")
    _invalidate_cache()


class TestJWTRejection:
    @pytest.mark.asyncio
    async def test_no_auth_rejected(self):
        result = await query(nexaql_query="{ product @limit(1) { id } }")
        assert "error" in result
        err = result["error"].lower()
        assert "auth_token" in err or "authentication" in err

    @pytest.mark.asyncio
    async def test_raw_context_rejected(self):
        result = await query(
            nexaql_query="{ product @limit(1) { id } }",
            user_context={"roles": ["admin"]},
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_tampered_token_rejected(self, admin_token):
        result = await query(
            nexaql_query="{ product @limit(1) { id } }",
            auth_token=admin_token + "TAMPERED",
        )
        assert "error" in result
        err = result["error"].lower()
        assert "invalid" in err or "signature" in err

    @pytest.mark.asyncio
    async def test_wrong_secret_rejected(self, make_token):
        bad_token = make_token(
            {"sub": "eve", "roles": ["admin"]},
            secret="completely-wrong-secret-key-32-bytes!!",
        )
        result = await query(
            nexaql_query="{ product @limit(1) { id } }",
            auth_token=bad_token,
        )
        assert "error" in result


class TestJWTAcceptance:
    @pytest.mark.asyncio
    async def test_valid_admin_token_accepted(self, admin_token):
        result = await query(
            nexaql_query="{ product @limit(3) { id name } }",
            auth_token=admin_token,
        )
        assert result.get("error") is None
        assert result["row_count"] == 3

    @pytest.mark.asyncio
    async def test_analyst_token_masks_pii(self, make_token):
        token = make_token({"sub": "bob", "roles": ["analyst"], "region": "US-EAST"})
        result = await query(
            nexaql_query="{ customer @limit(1) { id name email } }",
            auth_token=token,
        )
        assert result.get("error") is None
        col_names = [c["name"] for c in result["columns"]]
        assert "customer__email" in col_names
        if result["rows"]:
            email_val = str(result["rows"][0].get("customer__email", ""))
            assert "@" not in email_val, f"Expected masked email, got: {email_val}"

    @pytest.mark.asyncio
    async def test_jwt_user_id_from_sub(self, make_token):
        token = make_token({"sub": "charlie", "roles": ["admin"]})
        result = await query(
            nexaql_query="{ product @limit(1) { id } }",
            auth_token=token,
        )
        assert result.get("error") is None


class TestJWTCrossToolEnforcement:
    """Verify JWT is enforced on validate_query, sql_preview, and ask."""

    @pytest.mark.asyncio
    async def test_validate_query_requires_jwt(self):
        result = await validate_query(nexaql_query="{ product { id } }")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_validate_query_with_jwt(self, admin_token):
        result = await validate_query(
            nexaql_query="{ product @limit(5) { id name } }",
            auth_token=admin_token,
        )
        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_sql_preview_requires_jwt(self):
        result = await sql_preview(nexaql_query="{ product { id } }")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_sql_preview_with_jwt(self, admin_token):
        result = await sql_preview(
            nexaql_query="{ product @limit(5) { id name } }",
            auth_token=admin_token,
        )
        assert result.get("error") is None
        assert "SELECT" in result["sql"]

    @pytest.mark.asyncio
    async def test_ask_requires_jwt(self):
        result = await ask(question="how many products?")
        assert "error" in result
