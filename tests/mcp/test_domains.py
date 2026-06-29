# Copyright (c) 2026-present NexaQL Contributors
"""Tests for domain & ontology MCP tools."""

from __future__ import annotations

import pytest

from nexaql.mcp_server import (
    describe_node,
    describe_ontology,
    list_domains,
    switch_domain,
)


class TestListDomains:
    @pytest.mark.asyncio
    async def test_returns_domains(self):
        result = await list_domains()
        assert "domains" in result
        assert "active_domain" in result
        assert len(result["domains"]) >= 1

    @pytest.mark.asyncio
    async def test_ecommerce_domain_exists(self):
        result = await list_domains()
        names = [d["name"] for d in result["domains"]]
        assert "ecommerce" in names

    @pytest.mark.asyncio
    async def test_domain_has_node_count(self):
        result = await list_domains()
        ecom = next(d for d in result["domains"] if d["name"] == "ecommerce")
        assert ecom["node_count"] > 0


class TestSwitchDomain:
    @pytest.mark.asyncio
    async def test_switch_to_ecommerce(self):
        result = await switch_domain("ecommerce")
        assert result["status"] == "switched"
        assert result["domain"] == "ecommerce"
        assert len(result["nodes"]) > 0

    @pytest.mark.asyncio
    async def test_switch_to_nonexistent(self):
        result = await switch_domain("nonexistent_domain_xyz")
        assert "error" in result


class TestDescribeOntology:
    @pytest.mark.asyncio
    async def test_returns_nodes(self):
        result = await describe_ontology()
        assert "nodes" in result
        assert "domain" in result
        assert len(result["nodes"]) > 0

    @pytest.mark.asyncio
    async def test_nodes_have_fields(self):
        result = await describe_ontology()
        for node in result["nodes"]:
            assert "name" in node
            assert "fields" in node
            assert len(node["fields"]) > 0


class TestDescribeNode:
    @pytest.mark.asyncio
    async def test_product_node(self):
        result = await describe_node("product")
        assert result["node"] == "product"
        assert result["table"] == "products"
        field_names = [f["name"] for f in result["fields"]]
        assert "id" in field_names
        assert "name" in field_names

    @pytest.mark.asyncio
    async def test_node_has_edges(self):
        result = await describe_node("customer")
        assert len(result["edges"]) > 0
        edge_names = [e["name"] for e in result["edges"]]
        assert "orders" in edge_names

    @pytest.mark.asyncio
    async def test_nonexistent_node(self):
        result = await describe_node("nonexistent_node_xyz")
        assert "error" in result
        assert "Available" in result["error"]

    @pytest.mark.asyncio
    async def test_field_types_present(self):
        result = await describe_node("product")
        for f in result["fields"]:
            assert "type" in f
            assert "filterable" in f

    @pytest.mark.asyncio
    async def test_pii_fields_flagged(self):
        result = await describe_node("customer")
        email_field = next((f for f in result["fields"] if f["name"] == "email"), None)
        if email_field:
            assert email_field.get("pii") is True
