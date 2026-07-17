"""Tests for the NexaQL query translator (AST → SQL).

Covers: simple selects, filters, aggregations, GROUP BY with edge
aggregations, edge joins, directives, derived fields.
"""

from __future__ import annotations

import pytest

from nexaql.engine.parser import parse
from nexaql.engine.translator import translate
from nexaql.ontology.models import (
    FieldDef,
    JoinStep,
    Ontology,
    OntologyEdge,
    OntologyNode,
)


def _make_ontology(nodes: dict[str, OntologyNode]) -> Ontology:
    return Ontology(
        version="1.0",
        domain="test",
        description="Test ontology",
        nodes=nodes,
    )


CUSTOMERS_NODE = OntologyNode(
    table="customers",
    description="Customer records",
    primary_key="id",
    fields={
        "id": FieldDef(type="integer", description="ID"),
        "name": FieldDef(type="string", description="Name", filterable=True),
        "email": FieldDef(type="string", description="Email"),
        "region": FieldDef(
            type="enum", description="Region", filterable=True,
            values=["APAC", "EU", "US-EAST", "US-WEST"],
        ),
        "total_spend": FieldDef(type="numeric", description="Total spend", filterable=True),
    },
    edges={
        "orders": OntologyEdge(
            node="orders",
            description="Customer orders",
            join_steps=[
                JoinStep(table="orders", alias_key="orders", condition="{customers}.id = {orders}.customer_id"),
            ],
        ),
    },
)

ORDERS_NODE = OntologyNode(
    table="orders",
    description="Order records",
    primary_key="id",
    fields={
        "id": FieldDef(type="integer", description="ID"),
        "customer_id": FieldDef(type="integer", description="Customer ID"),
        "amount": FieldDef(type="numeric", description="Amount", filterable=True),
        "status": FieldDef(
            type="enum", description="Status", filterable=True,
            values=["PENDING", "SHIPPED", "DELIVERED", "CANCELLED"],
        ),
        "order_date": FieldDef(type="date", description="Order date", filterable=True),
    },
    edges={
        "items": OntologyEdge(
            node="order_items",
            description="Line items",
            join_steps=[
                JoinStep(table="order_items", alias_key="order_items", condition="{orders}.id = {order_items}.order_id"),
            ],
        ),
    },
)

ORDER_ITEMS_NODE = OntologyNode(
    table="order_items",
    description="Order line items",
    primary_key="id",
    fields={
        "id": FieldDef(type="integer", description="ID"),
        "order_id": FieldDef(type="integer", description="Order ID"),
        "product_name": FieldDef(type="string", description="Product"),
        "quantity": FieldDef(type="integer", description="Quantity"),
        "unit_price": FieldDef(type="numeric", description="Unit price"),
    },
)

SUPPORT_TICKETS_NODE = OntologyNode(
    table="support_tickets",
    description="Support tickets",
    primary_key="id",
    fields={
        "id": FieldDef(type="integer", description="ID"),
        "customer_id": FieldDef(type="integer", description="Customer ID"),
        "category": FieldDef(
            type="enum", description="Category", filterable=True,
            values=["BILLING", "PRODUCT_DEFECT", "REFUND", "GENERAL"],
        ),
        "priority": FieldDef(
            type="enum", description="Priority", filterable=True,
            values=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
        ),
    },
)


def _test_ontology() -> Ontology:
    return _make_ontology({
        "customers": CUSTOMERS_NODE.model_copy(
            update={
                "edges": {
                    "orders": OntologyEdge(
                        node="orders",
                        description="Customer orders",
                        join_steps=[
                            JoinStep(table="orders", alias_key="orders", condition="{customers}.id = {orders}.customer_id"),
                        ],
                    ),
                    "support_tickets": OntologyEdge(
                        node="support_tickets",
                        description="Support tickets",
                        join_steps=[
                            JoinStep(table="support_tickets", alias_key="support_tickets",
                                     condition="{customers}.id = {support_tickets}.customer_id"),
                        ],
                    ),
                },
            }
        ),
        "orders": ORDERS_NODE,
        "order_items": ORDER_ITEMS_NODE,
        "support_tickets": SUPPORT_TICKETS_NODE,
    })


# ---------------------------------------------------------------------------
# Simple select
# ---------------------------------------------------------------------------

class TestSimpleSelect:

    def test_single_node_all_fields(self):
        ast = parse("query { customers { id name email region } }")
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "SELECT" in sql
        assert "FROM CUSTOMERS" in sql

    def test_select_specific_fields(self):
        ast = parse("query { customers { name region } }")
        result = translate(ast, _test_ontology())
        sql = result.sql
        assert "name" in sql
        assert "region" in sql

    def test_no_where_without_filters(self):
        ast = parse("query { customers { id name } }")
        result = translate(ast, _test_ontology())
        assert "WHERE" not in result.sql.upper()


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

class TestFilters:

    def test_equality_filter(self):
        ast = parse('query { customers(region: "US-EAST") { id name } }')
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "WHERE" in sql

    def test_comparison_filter_gt(self):
        ast = parse("query { customers(total_spend_gt: 1000) { id name total_spend } }")
        result = translate(ast, _test_ontology())
        assert ">" in result.sql

    def test_comparison_filter_lte(self):
        ast = parse("query { customers(total_spend_lte: 500) { id name } }")
        result = translate(ast, _test_ontology())
        assert "<=" in result.sql

    def test_like_filter(self):
        ast = parse('query { customers(name_like: "%John%") { id name } }')
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "LIKE" in sql

    def test_in_filter(self):
        ast = parse('query { customers(region_in: ["US-EAST", "US-WEST"]) { id name region } }')
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "IN" in sql

    def test_null_filter(self):
        ast = parse("query { customers(email_null: true) { id name } }")
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "IS NULL" in sql


# ---------------------------------------------------------------------------
# Aggregations on root node
# ---------------------------------------------------------------------------

class TestRootAggregations:

    def test_count_only(self):
        ast = parse("query { customers { total: count() } }")
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "COUNT(*)" in sql
        assert "GROUP BY" not in sql

    def test_sum_with_group_by(self):
        ast = parse("query { customers { region total: sum(total_spend) } }")
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "SUM(" in sql
        assert "GROUP BY" in sql

    def test_avg_aggregation(self):
        ast = parse("query { customers { region avg_spend: avg(total_spend) } }")
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "AVG(" in sql
        assert "GROUP BY" in sql

    def test_multiple_aggregations(self):
        ast = parse("query { customers { region total: sum(total_spend) cnt: count() } }")
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "SUM(" in sql
        assert "COUNT(*)" in sql
        assert "GROUP BY" in sql


# ---------------------------------------------------------------------------
# Aggregations on edge node (GROUP BY regression test for #11)
# ---------------------------------------------------------------------------

class TestEdgeAggregationGroupBy:
    """Regression tests for issue #11: GROUP BY missing for root fields
    when aggregation is on an edge node."""

    def test_root_fields_grouped_with_edge_count(self):
        query = """query {
            customers {
                region
                support_tickets {
                    case_count: count()
                }
            }
        }"""
        ast = parse(query)
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "COUNT(*)" in sql
        assert "GROUP BY" in sql
        assert "REGION" in sql.split("GROUP BY")[1]

    def test_root_fields_grouped_with_edge_fields_and_count(self):
        query = """query {
            customers {
                region
                support_tickets {
                    category
                    case_count: count()
                }
            }
        }"""
        ast = parse(query)
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        group_by_clause = sql.split("GROUP BY")[1]
        assert "REGION" in group_by_clause
        assert "CATEGORY" in group_by_clause

    def test_edge_count_with_edge_filter(self):
        query = """query {
            customers {
                region
                support_tickets(category_in: ["BILLING", "REFUND"]) {
                    case_count: count()
                }
            }
        }"""
        ast = parse(query)
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "GROUP BY" in sql
        assert "IN" in sql

    def test_multiple_root_fields_with_edge_aggregation(self):
        query = """query {
            customers {
                name
                region
                orders {
                    total_amount: sum(amount)
                }
            }
        }"""
        ast = parse(query)
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        group_by_clause = sql.split("GROUP BY")[1]
        assert "NAME" in group_by_clause
        assert "REGION" in group_by_clause


# ---------------------------------------------------------------------------
# Edge joins
# ---------------------------------------------------------------------------

class TestEdgeJoins:

    def test_single_edge(self):
        ast = parse("query { customers { name orders { amount status } } }")
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "JOIN" in sql
        assert "ORDERS" in sql

    def test_nested_edge(self):
        ast = parse("query { customers { name orders { amount items { product_name quantity } } } }")
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert sql.count("JOIN") >= 2

    def test_edge_with_filter(self):
        ast = parse('query { customers { name orders(status: "SHIPPED") { amount } } }')
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "JOIN" in sql
        assert "WHERE" in sql


# ---------------------------------------------------------------------------
# Directives
# ---------------------------------------------------------------------------

class TestDirectives:

    def test_limit(self):
        ast = parse("query { customers @limit(10) { id name } }")
        result = translate(ast, _test_ontology())
        assert "LIMIT 10" in result.sql.upper()

    def test_offset(self):
        ast = parse("query { customers @limit(10) @offset(20) { id name } }")
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "LIMIT 10" in sql
        assert "OFFSET 20" in sql

    def test_orderby_asc(self):
        ast = parse("query { customers @orderby(name, ASC) { id name } }")
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "ORDER BY" in sql
        assert "ASC" in sql

    def test_orderby_desc(self):
        ast = parse("query { customers @orderby(total_spend, DESC) { id name total_spend } }")
        result = translate(ast, _test_ontology())
        sql = result.sql.upper()
        assert "ORDER BY" in sql
        assert "DESC" in sql

    def test_distinct(self):
        ast = parse("query { customers @distinct { region } }")
        result = translate(ast, _test_ontology())
        assert "SELECT DISTINCT" in result.sql.upper()


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------

class TestResultShape:

    def test_shape_has_node_name(self):
        ast = parse("query { customers { id name } }")
        result = translate(ast, _test_ontology())
        assert result.shape.node == "customers"

    def test_shape_has_column_aliases(self):
        ast = parse("query { customers { id name } }")
        result = translate(ast, _test_ontology())
        assert len(result.shape.column_aliases) == 2

    def test_shape_has_aggregation_aliases(self):
        ast = parse("query { customers { total: count() } }")
        result = translate(ast, _test_ontology())
        assert "total" in result.shape.aggregation_aliases

    def test_shape_has_children_for_edges(self):
        ast = parse("query { customers { name orders { amount } } }")
        result = translate(ast, _test_ontology())
        assert len(result.shape.children) == 1
        assert result.shape.children[0].node == "orders"
