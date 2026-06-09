# Copyright (c) 2026-present NexaQL Contributors
"""Tests for the intent extraction and deterministic NexaQL builder."""

import json

import pytest

from nexaql.chat.intent import (
    QueryIntent,
    IntentAggregation,
    IntentCalc,
    IntentCalcFilter,
    IntentEdge,
    IntentFilter,
    IntentOrderBy,
    build_nexaql,
    extract_intent_json,
    parse_intent,
)
from nexaql.engine.parser import parse


# ── extract_intent_json ─────────────────────────────────────────────────────


class TestExtractIntentJson:
    def test_fenced_json_block(self):
        text = 'Here is the intent:\n```json\n{"node": "suppliers"}\n```'
        result = extract_intent_json(text)
        assert result == {"node": "suppliers"}

    def test_bare_json(self):
        text = '{"node": "suppliers", "fields": ["name"]}'
        result = extract_intent_json(text)
        assert result == {"node": "suppliers", "fields": ["name"]}

    def test_json_with_surrounding_text(self):
        text = 'I think the intent is:\n{"node": "contracts"}\nLet me know.'
        result = extract_intent_json(text)
        assert result == {"node": "contracts"}

    def test_invalid_json(self):
        text = "This is not JSON at all."
        result = extract_intent_json(text)
        assert result is None

    def test_complex_fenced(self):
        text = '''```json
{
  "node": "suppliers",
  "fields": ["name", "status"],
  "filters": [{"field": "status", "op": "eq", "value": "ACTIVE"}],
  "limit": 10
}
```'''
        result = extract_intent_json(text)
        assert result["node"] == "suppliers"
        assert result["limit"] == 10
        assert len(result["filters"]) == 1


# ── parse_intent ────────────────────────────────────────────────────────────


class TestParseIntent:
    def test_minimal(self):
        data = {"node": "suppliers", "fields": ["name"]}
        intent = parse_intent(data)
        assert intent.node == "suppliers"
        assert intent.fields == ["name"]
        assert intent.filters == []
        assert intent.edges == []

    def test_full(self):
        data = {
            "node": "suppliers",
            "fields": ["name", "status"],
            "aggregations": [
                {"alias": "total", "func": "sum", "field": "amount"},
                {"alias": "cnt", "func": "count"},
            ],
            "calcs": [{"alias": "days_left", "expr": "due_date - CURRENT_DATE"}],
            "filters": [{"field": "status", "op": "eq", "value": "ACTIVE"}],
            "calc_filters": [{"expr": "due_date - CURRENT_DATE", "op": "lte", "value": 30}],
            "special_filters": {"expiring_within_days": 30},
            "edges": [
                {
                    "name": "contracts",
                    "fields": ["title", "amount"],
                    "filters": [{"field": "status", "op": "eq", "value": "SIGNED"}],
                }
            ],
            "order_by": [{"field": "total", "direction": "DESC"}],
            "limit": 5,
            "distinct": True,
        }
        intent = parse_intent(data)
        assert intent.node == "suppliers"
        assert len(intent.aggregations) == 2
        assert intent.aggregations[1].field is None  # count()
        assert len(intent.calcs) == 1
        assert len(intent.calc_filters) == 1
        assert intent.special_filters == {"expiring_within_days": 30}
        assert len(intent.edges) == 1
        assert intent.edges[0].name == "contracts"
        assert intent.limit == 5
        assert intent.distinct is True


# ── build_nexaql ─────────────────────────────────────────────────────────────


class TestBuildNexaql:
    def test_simple_query(self):
        intent = QueryIntent(
            node="suppliers",
            fields=["name", "status"],
            limit=10,
        )
        result = build_nexaql(intent)
        assert "query" in result
        assert "suppliers" in result
        assert "@limit(10)" in result
        assert "name" in result
        assert "status" in result

    def test_with_filters(self):
        intent = QueryIntent(
            node="suppliers",
            fields=["name"],
            filters=[
                IntentFilter(field="status", op="eq", value="ACTIVE"),
                IntentFilter(field="amount", op="gt", value=1000),
            ],
        )
        result = build_nexaql(intent)
        assert 'status: "ACTIVE"' in result
        assert "amount: { gt: 1000 }" in result

    def test_with_aggregations(self):
        intent = QueryIntent(
            node="invoices",
            aggregations=[
                IntentAggregation(alias="total_amount", func="sum", field="amount"),
                IntentAggregation(alias="record_count", func="count"),
            ],
        )
        result = build_nexaql(intent)
        assert "total_amount: sum(amount)" in result
        assert "record_count: count()" in result

    def test_with_calc(self):
        intent = QueryIntent(
            node="contracts",
            fields=["title"],
            calcs=[IntentCalc(alias="days_left", expr="end_date - CURRENT_DATE")],
        )
        result = build_nexaql(intent)
        assert "days_left: calc(end_date - CURRENT_DATE)" in result

    def test_with_calc_filter(self):
        intent = QueryIntent(
            node="contracts",
            fields=["title"],
            calc_filters=[
                IntentCalcFilter(expr="end_date - CURRENT_DATE", op="lte", value=30),
            ],
        )
        result = build_nexaql(intent)
        assert "calc(end_date - CURRENT_DATE): { lte: 30 }" in result

    def test_with_edges(self):
        intent = QueryIntent(
            node="suppliers",
            fields=["name"],
            edges=[
                IntentEdge(
                    name="contracts",
                    fields=["title", "amount"],
                    limit=5,
                ),
            ],
        )
        result = build_nexaql(intent)
        assert "contracts" in result
        assert "title" in result
        assert "@limit(5)" in result

    def test_with_order_by(self):
        intent = QueryIntent(
            node="suppliers",
            fields=["name"],
            order_by=[IntentOrderBy(field="name", direction="ASC")],
        )
        result = build_nexaql(intent)
        assert "@orderby(name, ASC)" in result

    def test_distinct(self):
        intent = QueryIntent(
            node="suppliers",
            fields=["status"],
            distinct=True,
        )
        result = build_nexaql(intent)
        assert "@distinct" in result

    def test_special_filters(self):
        intent = QueryIntent(
            node="contracts",
            fields=["title"],
            special_filters={"expiring_within_days": 30},
        )
        result = build_nexaql(intent)
        assert "expiring_within_days: 30" in result

    def test_in_filter(self):
        intent = QueryIntent(
            node="suppliers",
            fields=["name"],
            filters=[
                IntentFilter(field="status", op="in", value=["ACTIVE", "PENDING"]),
            ],
        )
        result = build_nexaql(intent)
        assert 'in: ["ACTIVE", "PENDING"]' in result

    def test_null_filter(self):
        intent = QueryIntent(
            node="suppliers",
            fields=["name"],
            filters=[
                IntentFilter(field="email", op="null", value=False),
            ],
        )
        result = build_nexaql(intent)
        assert "null: false" in result

    def test_nested_edges(self):
        intent = QueryIntent(
            node="suppliers",
            fields=["name"],
            edges=[
                IntentEdge(
                    name="contracts",
                    fields=["title"],
                    edges=[
                        IntentEdge(name="line_items", fields=["description", "amount"]),
                    ],
                ),
            ],
        )
        result = build_nexaql(intent)
        assert "line_items" in result
        assert "description" in result

    def test_query_name_generation(self):
        # With aggregation -> Summary
        intent = QueryIntent(
            node="invoices",
            aggregations=[IntentAggregation(alias="cnt", func="count")],
        )
        assert "InvoicesSummary" in build_nexaql(intent)

        # With filters -> Filtered
        intent = QueryIntent(
            node="suppliers",
            fields=["name"],
            filters=[IntentFilter(field="status", op="eq", value="ACTIVE")],
        )
        assert "FilteredSuppliers" in build_nexaql(intent)

        # With order + limit -> Top
        intent = QueryIntent(
            node="suppliers",
            fields=["name"],
            order_by=[IntentOrderBy(field="amount", direction="DESC")],
            limit=5,
        )
        assert "TopSuppliers" in build_nexaql(intent)

    def test_custom_query_name(self):
        intent = QueryIntent(
            node="suppliers",
            fields=["name"],
            query_name="MyCustomQuery",
        )
        assert "query MyCustomQuery" in build_nexaql(intent)


# ── Integration: build_nexaql output is parseable ────────────────────────────


class TestBuildNexaqlParseable:
    """Verify that build_nexaql output can be parsed by the NexaQL parser."""

    def _assert_parseable(self, intent: QueryIntent):
        query_str = build_nexaql(intent)
        ast = parse(query_str)
        assert ast.kind == "query"
        assert ast.body.name == intent.node

    def test_simple(self):
        self._assert_parseable(QueryIntent(
            node="suppliers",
            fields=["name", "status"],
        ))

    def test_with_filter(self):
        self._assert_parseable(QueryIntent(
            node="suppliers",
            fields=["name"],
            filters=[IntentFilter(field="status", op="eq", value="ACTIVE")],
        ))

    def test_with_aggregation(self):
        self._assert_parseable(QueryIntent(
            node="invoices",
            aggregations=[
                IntentAggregation(alias="total", func="sum", field="amount"),
                IntentAggregation(alias="cnt", func="count"),
            ],
        ))

    def test_with_edge(self):
        self._assert_parseable(QueryIntent(
            node="suppliers",
            fields=["name"],
            edges=[IntentEdge(name="contracts", fields=["title"])],
        ))

    def test_with_directives(self):
        self._assert_parseable(QueryIntent(
            node="suppliers",
            fields=["name"],
            order_by=[IntentOrderBy(field="name", direction="DESC")],
            limit=10,
            offset=20,
            distinct=True,
        ))

    def test_complex_combo(self):
        self._assert_parseable(QueryIntent(
            node="suppliers",
            fields=["name", "status"],
            aggregations=[IntentAggregation(alias="total", func="sum", field="amount")],
            calcs=[IntentCalc(alias="days_active", expr="CURRENT_DATE - created_at")],
            filters=[
                IntentFilter(field="status", op="eq", value="ACTIVE"),
                IntentFilter(field="amount", op="gte", value=1000),
            ],
            edges=[
                IntentEdge(
                    name="contracts",
                    fields=["title"],
                    filters=[IntentFilter(field="status", op="in", value=["SIGNED", "ACTIVE"])],
                    limit=3,
                ),
            ],
            order_by=[IntentOrderBy(field="total", direction="DESC")],
            limit=10,
        ))

    def test_calc_filter(self):
        self._assert_parseable(QueryIntent(
            node="contracts",
            fields=["title", "end_date"],
            calc_filters=[
                IntentCalcFilter(expr="end_date - CURRENT_DATE", op="gte", value=0),
                IntentCalcFilter(expr="end_date - CURRENT_DATE", op="lte", value=30),
            ],
        ))
