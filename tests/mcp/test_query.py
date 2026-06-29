# Copyright (c) 2026-present NexaQL Contributors
"""Tests for query execution MCP tools — query, validate_query, sql_preview."""

from __future__ import annotations

import pytest

from nexaql.mcp_server import query, sql_preview, validate_query


class TestQuery:
    @pytest.mark.asyncio
    async def test_simple_query(self):
        result = await query(
            nexaql_query="{ product @limit(3) { id name sku } }",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None
        assert result["row_count"] == 3
        assert len(result["rows"]) == 3
        assert "product__id" in result["rows"][0]

    @pytest.mark.asyncio
    async def test_query_with_filter(self):
        result = await query(
            nexaql_query="{ product(is_active: true) { id name } }",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None
        assert result["row_count"] > 0

    @pytest.mark.asyncio
    async def test_query_with_edge(self):
        result = await query(
            nexaql_query="{ customer @limit(2) { name orders { id total_amount } } }",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None
        assert result["row_count"] > 0

    @pytest.mark.asyncio
    async def test_query_with_aggregation(self):
        result = await query(
            nexaql_query="{ product { total: count() } }",
            user_context={"roles": ["admin"]},
        )
        assert result.get("error") is None
        assert result["row_count"] == 1

    @pytest.mark.asyncio
    async def test_invalid_query_syntax(self):
        result = await query(
            nexaql_query="NOT VALID SYNTAX {{{{",
            user_context={"roles": ["admin"]},
        )
        assert "error" in result
        assert "Parse error" in result["error"]

    @pytest.mark.asyncio
    async def test_query_columns_metadata(self):
        result = await query(
            nexaql_query="{ product @limit(1) { id name } }",
            user_context={"roles": ["admin"]},
        )
        assert len(result["columns"]) >= 2
        col_names = [c["name"] for c in result["columns"]]
        assert "product__id" in col_names

    @pytest.mark.asyncio
    async def test_query_sql_preview_returned(self):
        result = await query(
            nexaql_query="{ product @limit(1) { id name } }",
            user_context={"roles": ["admin"]},
        )
        assert result.get("sql_preview") is not None
        assert "SELECT" in result["sql_preview"]


class TestQueryAccessControl:
    @pytest.mark.asyncio
    async def test_admin_sees_all_fields(self):
        result = await query(
            nexaql_query="{ customer @limit(1) { id name email } }",
            user_context={"user_id": "admin1", "roles": ["admin"]},
        )
        assert result.get("error") is None
        col_names = [c["name"] for c in result["columns"]]
        assert "customer__email" in col_names

    @pytest.mark.asyncio
    async def test_analyst_email_stripped(self):
        result = await query(
            nexaql_query="{ customer @limit(1) { id name email } }",
            user_context={"user_id": "analyst1", "roles": ["analyst"]},
        )
        assert result.get("error") is None
        col_names = [c["name"] for c in result["columns"]]
        assert "customer__email" not in col_names

    @pytest.mark.asyncio
    async def test_default_admin_when_no_context(self):
        result = await query(
            nexaql_query="{ product @limit(1) { id name } }",
        )
        assert result.get("error") is None
        assert result["row_count"] == 1


class TestValidateQuery:
    @pytest.mark.asyncio
    async def test_valid_query(self):
        result = await validate_query(
            nexaql_query="{ product @limit(5) { id name sku } }",
        )
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_valid_query_has_sql_preview(self):
        result = await validate_query(
            nexaql_query="{ product @limit(5) { id name } }",
        )
        assert result["valid"] is True
        assert result.get("sql_preview") is not None

    @pytest.mark.asyncio
    async def test_invalid_node(self):
        result = await validate_query(
            nexaql_query="{ fake_node { id } }",
        )
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_parse_error(self):
        result = await validate_query(nexaql_query="{{{{ bad syntax")
        assert result["valid"] is False


class TestSqlPreview:
    @pytest.mark.asyncio
    async def test_returns_sql(self):
        result = await sql_preview(
            nexaql_query="{ product @limit(10) { id name } }",
        )
        assert result.get("error") is None
        assert "SELECT" in result["sql"]
        assert result["adapter_type"] is not None

    @pytest.mark.asyncio
    async def test_sql_reflects_access_control(self):
        admin_result = await sql_preview(
            nexaql_query="{ customer @limit(1) { id name email } }",
            user_context={"roles": ["admin"]},
        )
        analyst_result = await sql_preview(
            nexaql_query="{ customer @limit(1) { id name email } }",
            user_context={"roles": ["analyst"]},
        )
        assert admin_result.get("error") is None
        assert analyst_result.get("error") is None
        assert "email" in admin_result["sql"].lower()
        assert "email" not in analyst_result["sql"].lower()

    @pytest.mark.asyncio
    async def test_invalid_query(self):
        result = await sql_preview(nexaql_query="{ fake_node { id } }")
        assert "error" in result
