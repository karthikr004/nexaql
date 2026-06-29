# Copyright (c) 2026-present NexaQL Contributors
"""Tests for the agent chat (NL→query) via the MCP `ask` tool.

These tests call a real LLM (Anthropic or OpenAI) — the API key is loaded
from the bootstrap DB (~/.nexaql/nexaql.db, set via admin panel) or from
the environment variable ANTHROPIC_API_KEY / OPENAI_API_KEY.

Skipped automatically when no key is available.

Run only chat tests:
    PYTHONPATH=src python3.11 -m pytest tests/mcp/test_agent_chat.py -v
"""

from __future__ import annotations

import pytest

from nexaql.mcp_server import ask, configure_auth, _invalidate_cache
from tests.conftest import requires_llm


@requires_llm
class TestAgentChatDevMode:
    """NL ask in dev mode (no JWT required)."""

    @pytest.mark.asyncio
    async def test_count_query(self):
        result = await ask(
            question="how many products do we have?",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None
        assert result["nexaql_query"] is not None
        assert result["row_count"] >= 1

    @pytest.mark.asyncio
    async def test_returns_summary(self):
        result = await ask(
            question="list 3 customers",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None
        assert result["summary"] is not None
        assert len(result["summary"]) > 0

    @pytest.mark.asyncio
    async def test_top_n_query(self):
        result = await ask(
            question="top 5 products by name",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None
        assert result["row_count"] <= 5

    @pytest.mark.asyncio
    async def test_edge_traversal_query(self):
        result = await ask(
            question="show me customers and their orders",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None
        assert result["row_count"] >= 1

    @pytest.mark.asyncio
    async def test_aggregation_query(self):
        result = await ask(
            question="total number of orders",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None
        assert result["row_count"] >= 1

    @pytest.mark.asyncio
    async def test_generates_valid_nexaql(self):
        result = await ask(
            question="show customer names and their order totals",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None
        assert result["nexaql_query"] is not None
        assert "{" in result["nexaql_query"]

    @pytest.mark.asyncio
    async def test_analyst_pii_masked(self):
        result = await ask(
            question="show me 2 customers with their email and name",
            user_context={"user_id": "analyst1", "roles": ["analyst"], "region": "US-EAST"},
        )
        assert result.get("error") is None
        if result.get("rows"):
            for row in result["rows"]:
                email_val = row.get("customer__email")
                if email_val is not None:
                    assert "@" not in str(email_val), f"Expected masked email, got: {email_val}"

    @pytest.mark.asyncio
    async def test_domain_switch(self):
        result = await ask(
            question="how many products?",
            domain="ecommerce",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None

    @pytest.mark.asyncio
    async def test_sql_preview_in_response(self):
        result = await ask(
            question="list all categories",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None
        assert result.get("sql_preview") is not None
        assert "SELECT" in result["sql_preview"]

    @pytest.mark.asyncio
    async def test_response_has_columns(self):
        result = await ask(
            question="show 2 products with their names",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None
        assert result.get("columns") is not None
        assert len(result["columns"]) > 0
        assert all("name" in c and "type" in c for c in result["columns"])

    @pytest.mark.asyncio
    async def test_response_rows_match_count(self):
        result = await ask(
            question="list 3 products",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None
        assert result["row_count"] == len(result["rows"])


@requires_llm
class TestAgentChatJWTMode:
    """NL ask with JWT authentication."""

    @pytest.mark.asyncio
    async def test_ask_with_admin_jwt(self, jwt_secret, make_token):
        await configure_auth(auth_mode="jwt", auth_secret=jwt_secret)
        _invalidate_cache()
        token = make_token({"sub": "alice", "roles": ["admin"]})
        result = await ask(
            question="how many products?",
            auth_token=token,
        )
        assert result.get("error") is None
        assert result["row_count"] >= 1

    @pytest.mark.asyncio
    async def test_ask_with_analyst_jwt_succeeds(self, jwt_secret, make_token):
        await configure_auth(auth_mode="jwt", auth_secret=jwt_secret)
        _invalidate_cache()
        token = make_token({"sub": "bob", "roles": ["analyst"]})
        result = await ask(
            question="how many products?",
            auth_token=token,
        )
        assert result.get("error") is None
        assert result["row_count"] >= 1

    @pytest.mark.asyncio
    async def test_analyst_jwt_pii_masked(self, jwt_secret, make_token):
        await configure_auth(auth_mode="jwt", auth_secret=jwt_secret)
        _invalidate_cache()
        token = make_token({"sub": "bob", "roles": ["analyst"], "region": "US-EAST"})
        result = await ask(
            question="show 2 customers with name and email",
            auth_token=token,
        )
        assert result.get("error") is None
        if result.get("rows"):
            for row in result["rows"]:
                email_val = row.get("customer__email")
                if email_val is not None:
                    assert "@" not in str(email_val), f"Expected masked email, got: {email_val}"

    @pytest.mark.asyncio
    async def test_ask_no_token_in_jwt_mode(self, jwt_secret):
        await configure_auth(auth_mode="jwt", auth_secret=jwt_secret)
        _invalidate_cache()
        result = await ask(question="how many products?")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_ask_tampered_token_rejected(self, jwt_secret, make_token):
        await configure_auth(auth_mode="jwt", auth_secret=jwt_secret)
        _invalidate_cache()
        token = make_token({"sub": "alice", "roles": ["admin"]})
        result = await ask(
            question="how many products?",
            auth_token=token + "TAMPERED",
        )
        assert "error" in result


@requires_llm
class TestAgentChatEdgeCases:
    """Edge cases and error handling for the ask tool."""

    @pytest.mark.asyncio
    async def test_ambiguous_question(self):
        result = await ask(
            question="show me everything",
            user_context={"roles": ["admin"]},
        )
        # Should still produce some result or graceful error
        assert result.get("nexaql_query") is not None or result.get("error") is not None

    @pytest.mark.asyncio
    async def test_invalid_domain(self):
        # _get_ontology raises ValueError for unknown domains (not yet caught in ask)
        with pytest.raises(ValueError, match="No ontology found"):
            await ask(
                question="how many products?",
                domain="nonexistent_domain_xyz",
                user_context={"roles": ["admin"]},
            )

    @pytest.mark.asyncio
    async def test_no_user_context_defaults_to_admin(self):
        result = await ask(question="how many products?")
        assert result.get("error") is None
        assert result["row_count"] >= 1
