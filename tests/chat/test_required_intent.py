# Copyright (c) 2026-present NexaQL Contributors
"""Tests for @required in the intent builder and auto_require_intent."""

from nexaql.chat.intent import (
    IntentCalc,
    IntentCalcFilter,
    IntentEdge,
    QueryIntent,
    auto_require_intent,
    build_nexaql,
    parse_intent,
)
from nexaql.engine.parser import parse
from nexaql.engine.types import RequiredDirective


class TestIntentRequired:
    def test_required_edge_emits_directive(self):
        intent = QueryIntent(
            node="purchase_order_line",
            fields=["unit_price"],
            edges=[
                IntentEdge(name="contract_lines", fields=["agreed_unit_price"], required=True),
            ],
        )
        nexaql = build_nexaql(intent)
        assert "@required" in nexaql
        ast = parse(nexaql)
        edge = ast.body.fields[1]
        assert any(getattr(d, "type", None) == "required" for d in edge.node.directives)

    def test_non_required_edge_no_directive(self):
        intent = QueryIntent(
            node="purchase_order",
            fields=["po_number"],
            edges=[
                IntentEdge(name="items", fields=["description"]),
            ],
        )
        nexaql = build_nexaql(intent)
        assert "@required" not in nexaql

    def test_parse_intent_reads_required(self):
        data = {
            "node": "purchase_order_line",
            "fields": ["unit_price"],
            "edges": [
                {"name": "contract_lines", "fields": ["agreed_unit_price"], "required": True},
            ],
        }
        intent = parse_intent(data)
        assert intent.edges[0].required is True

    def test_parse_intent_default_not_required(self):
        data = {
            "node": "purchase_order",
            "fields": ["po_number"],
            "edges": [{"name": "items", "fields": ["description"]}],
        }
        intent = parse_intent(data)
        assert intent.edges[0].required is False


class TestAutoRequireIntent:
    def test_dotted_ref_promotes_edge(self):
        """Dotted reference (edge_name.field) in calc triggers promotion."""
        intent = QueryIntent(
            node="purchase_order_line",
            fields=["unit_price"],
            calcs=[IntentCalc(alias="price_diff", expr="unit_price - contract_lines.agreed_unit_price")],
            edges=[
                IntentEdge(name="contract_lines", fields=["agreed_unit_price"]),
            ],
        )
        result = auto_require_intent(intent)
        assert result.edges[0].required is True

    def test_bare_field_name_does_not_promote(self):
        """P1-2 regression: bare identifiers belong to root node, not edges."""
        intent = QueryIntent(
            node="purchase_order_line",
            fields=["unit_price"],
            calcs=[IntentCalc(alias="price_diff", expr="unit_price - agreed_unit_price")],
            edges=[
                IntentEdge(name="contract_lines", fields=["agreed_unit_price"]),
            ],
        )
        result = auto_require_intent(intent)
        assert result.edges[0].required is False

    def test_coalesce_skips_promotion(self):
        """P1-3 regression: COALESCE-wrapped refs preserve LEFT JOIN."""
        intent = QueryIntent(
            node="purchase_order_line",
            fields=["unit_price"],
            calcs=[IntentCalc(alias="safe_price", expr="COALESCE(contract_lines.agreed_unit_price, 0)")],
            edges=[
                IntentEdge(name="contract_lines", fields=["agreed_unit_price"]),
            ],
        )
        result = auto_require_intent(intent)
        assert result.edges[0].required is False

    def test_nullif_skips_promotion(self):
        intent = QueryIntent(
            node="purchase_order_line",
            fields=["unit_price"],
            calcs=[IntentCalc(alias="adj", expr="NULLIF(contract_lines.agreed_unit_price, 0)")],
            edges=[
                IntentEdge(name="contract_lines", fields=["agreed_unit_price"]),
            ],
        )
        result = auto_require_intent(intent)
        assert result.edges[0].required is False

    def test_calc_filter_with_dotted_ref_promotes(self):
        intent = QueryIntent(
            node="purchase_order_line",
            fields=["unit_price"],
            calcs=[IntentCalc(alias="price_diff", expr="unit_price - contract_lines.agreed_unit_price")],
            calc_filters=[IntentCalcFilter(expr="unit_price - contract_lines.agreed_unit_price", op="gt", value=0)],
            edges=[
                IntentEdge(name="contract_lines", fields=["agreed_unit_price"]),
            ],
        )
        result = auto_require_intent(intent)
        assert result.edges[0].required is True

    def test_no_calc_no_promotion(self):
        intent = QueryIntent(
            node="purchase_order",
            fields=["po_number"],
            edges=[
                IntentEdge(name="items", fields=["description"]),
            ],
        )
        result = auto_require_intent(intent)
        assert result.edges[0].required is False

    def test_already_required_stays_required(self):
        intent = QueryIntent(
            node="purchase_order_line",
            fields=["unit_price"],
            calcs=[IntentCalc(alias="price_diff", expr="unit_price - contract_lines.agreed_unit_price")],
            edges=[
                IntentEdge(name="contract_lines", fields=["agreed_unit_price"], required=True),
            ],
        )
        result = auto_require_intent(intent)
        assert result.edges[0].required is True

    def test_unrelated_calc_no_promotion(self):
        """Calc using only root fields should not promote any edge."""
        intent = QueryIntent(
            node="purchase_order_line",
            fields=["unit_price", "quantity"],
            calcs=[IntentCalc(alias="line_total", expr="unit_price * quantity")],
            edges=[
                IntentEdge(name="contract_lines", fields=["agreed_unit_price"]),
            ],
        )
        result = auto_require_intent(intent)
        assert result.edges[0].required is False

    def test_multiple_dotted_refs_promote_multiple_edges(self):
        intent = QueryIntent(
            node="purchase_order_line",
            fields=["unit_price"],
            calcs=[IntentCalc(alias="total", expr="contract_lines.agreed_unit_price - supplier.discount")],
            edges=[
                IntentEdge(name="contract_lines", fields=["agreed_unit_price"]),
                IntentEdge(name="supplier", fields=["discount"]),
            ],
        )
        result = auto_require_intent(intent)
        assert result.edges[0].required is True
        assert result.edges[1].required is True
