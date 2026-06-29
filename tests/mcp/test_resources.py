# Copyright (c) 2026-present NexaQL Contributors
"""Tests for MCP resources and server registration."""

from __future__ import annotations

import json

import pytest

from nexaql.mcp_server import mcp as mcp_app, resource_grammar, resource_ontology, resource_roles


class TestResources:
    def test_ontology_resource(self):
        text = resource_ontology()
        data = json.loads(text)
        assert "domain" in data
        assert "nodes" in data
        assert len(data["nodes"]) > 0

    def test_grammar_resource(self):
        text = resource_grammar()
        assert "NexaQL" in text or "Query" in text or "node_name" in text

    def test_roles_resource(self):
        text = resource_roles()
        data = json.loads(text)
        assert "roles" in data
        assert "admin" in data["roles"]


class TestMCPRegistration:
    def test_all_tools_registered(self):
        tools = mcp_app._tool_manager.list_tools()
        tool_names = [t.name for t in tools]
        expected = [
            "ask", "query", "validate_query",
            "list_domains", "switch_domain",
            "describe_node", "describe_ontology",
            "list_connectors",
            "user_context_schema", "configure_auth",
            "sql_preview",
        ]
        for name in expected:
            assert name in tool_names, f"Tool '{name}' not registered"

    def test_tool_count(self):
        tools = mcp_app._tool_manager.list_tools()
        assert len(tools) == 11

    def test_tools_have_descriptions(self):
        tools = mcp_app._tool_manager.list_tools()
        for t in tools:
            assert t.description, f"Tool '{t.name}' has no description"

    def test_auth_tools_have_params(self):
        tools = mcp_app._tool_manager.list_tools()
        query_tool = next(t for t in tools if t.name == "query")
        params = list(query_tool.parameters.get("properties", {}).keys())
        assert "auth_token" in params
        assert "user_context" in params

    def test_cli_mcp_command_exists(self):
        from nexaql.cli import main
        commands = [c for c in main.commands]
        assert "mcp" in commands
