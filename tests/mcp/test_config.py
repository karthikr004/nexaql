# Copyright (c) 2026-present NexaQL Contributors
"""Tests for auth configuration and user_context_schema MCP tools."""

from __future__ import annotations

import pytest

from nexaql.mcp_server import configure_auth, user_context_schema


class TestUserContextSchema:
    @pytest.mark.asyncio
    async def test_returns_schema(self):
        result = await user_context_schema()
        assert "auth_mode" in result
        assert "standard_fields" in result
        assert "defined_roles" in result
        assert "note" in result

    @pytest.mark.asyncio
    async def test_standard_fields_complete(self):
        result = await user_context_schema()
        field_names = [f["name"] for f in result["standard_fields"]]
        assert "user_id" in field_names
        assert "roles" in field_names
        assert "region" in field_names
        assert "department" in field_names
        assert "team_id" in field_names

    @pytest.mark.asyncio
    async def test_roles_from_ontology(self):
        result = await user_context_schema()
        roles = result["defined_roles"]
        assert "admin" in roles
        assert "analyst" in roles
        assert "manager" in roles

    @pytest.mark.asyncio
    async def test_rls_attributes_detected(self):
        result = await user_context_schema()
        if result.get("rls_required_attributes"):
            attrs = result["rls_required_attributes"]
            assert isinstance(attrs, list)
            assert len(attrs) > 0

    @pytest.mark.asyncio
    async def test_dev_mode_note(self):
        result = await user_context_schema()
        assert result["auth_mode"] == "dev"
        assert "dev" in result["note"].lower()

    @pytest.mark.asyncio
    async def test_jwt_mode_note(self, jwt_secret):
        await configure_auth(auth_mode="jwt", auth_secret=jwt_secret)
        result = await user_context_schema()
        assert result["auth_mode"] == "jwt"
        assert "jwt_claims_mapping" in result
        assert "sub" in result["jwt_claims_mapping"]


class TestConfigureAuth:
    @pytest.mark.asyncio
    async def test_switch_to_jwt(self, jwt_secret):
        result = await configure_auth(auth_mode="jwt", auth_secret=jwt_secret)
        assert result["status"] == "configured"
        assert result["auth_mode"] == "jwt"
        assert result["auth_secret_set"] is True

    @pytest.mark.asyncio
    async def test_switch_to_dev(self):
        result = await configure_auth(auth_mode="dev")
        assert result["status"] == "configured"
        assert result["auth_mode"] == "dev"

    @pytest.mark.asyncio
    async def test_jwt_without_secret_fails(self):
        result = await configure_auth(auth_mode="jwt")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_invalid_mode_fails(self):
        result = await configure_auth(auth_mode="invalid")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_custom_algorithm(self, jwt_secret):
        result = await configure_auth(
            auth_mode="jwt", auth_secret=jwt_secret, auth_algorithm="HS512",
        )
        assert result["auth_algorithm"] == "HS512"
