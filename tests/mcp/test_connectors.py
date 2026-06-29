# Copyright (c) 2026-present NexaQL Contributors
"""Tests for connector MCP tools."""

from __future__ import annotations

import pytest

from nexaql.mcp_server import list_connectors


class TestListConnectors:
    @pytest.mark.asyncio
    async def test_returns_connectors(self):
        result = await list_connectors()
        assert "connectors" in result
        assert len(result["connectors"]) >= 1

    @pytest.mark.asyncio
    async def test_connector_fields(self):
        result = await list_connectors()
        for c in result["connectors"]:
            assert "name" in c
            assert "type" in c
            assert "id" in c
