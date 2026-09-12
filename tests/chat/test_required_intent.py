# Copyright (c) 2026-present NexaQL Contributors
"""Tests for @required in the intent builder and auto_require_intent."""

from nexaql.chat.intent import (
    IntentCalc,
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
    def test_calc_referencing_edge_field_promotes(self):
        intent = QueryIntent(
            node="purchase_order_line",
            fields=["unit_price"],
            calcs=[IntentCalc(alias="price_diff", expr="unit_price - agreed_unit_price")],
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
            calcs=[IntentCalc(alias="price_diff", expr="unit_price - agreed_unit_price")],
            edges=[
                IntentEdge(name="contract_lines", fields=["agreed_unit_price"], required=True),
            ],
        )
        result = auto_require_intent(intent)
        assert result.edges[0].required is True

    def test_unrelated_calc_no_promotion(self):
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
