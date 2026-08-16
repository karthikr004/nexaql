# Copyright (c) 2026-present NexaQL Contributors
"""Structured intent extraction and deterministic NexaQL query builder.

Option B architecture: LLM extracts structured intent (JSON), then a
deterministic builder constructs guaranteed-valid NexaQL query strings.

This decouples "understanding the question" (LLM) from "writing the syntax"
(deterministic code), making it possible to use small/cheap models while
maintaining 100% syntactic correctness.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional


# ── Intent schema ────────────────────────────────────────────────────────────


@dataclass
class IntentFilter:
    """A single filter condition."""
    field: str
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte", "like", "in", "not_in", "null"]
    value: Any  # str, int, float, bool, list, or None


@dataclass
class IntentCalcFilter:
    """A filter on a computed expression: calc(expr) op value."""
    expr: str
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte"]
    value: Any


@dataclass
class IntentAggregation:
    """An aggregation field: alias: func(field)."""
    alias: str
    func: Literal["count", "sum", "avg", "min", "max"]
    field: Optional[str] = None  # None for count()


@dataclass
class IntentCalc:
    """An inline computed field: alias: calc(expr)."""
    alias: str
    expr: str


@dataclass
class IntentOrderBy:
    """Sort directive."""
    field: str
    direction: Literal["ASC", "DESC"] = "ASC"


@dataclass
class IntentVisualization:
    """LLM-suggested visualization for query results."""
    chart_type: Literal["bar", "line", "pie", "stat", "table"]
    x_field: str | None = None
    y_fields: list[str] = field(default_factory=list)
    title: str | None = None


@dataclass
class IntentEdge:
    """A nested edge traversal."""
    name: str
    fields: list[str] = field(default_factory=list)
    aggregations: list[IntentAggregation] = field(default_factory=list)
    calcs: list[IntentCalc] = field(default_factory=list)
    filters: list[IntentFilter] = field(default_factory=list)
    order_by: list[IntentOrderBy] = field(default_factory=list)
    limit: Optional[int] = None
    # Nested edges
    edges: list["IntentEdge"] = field(default_factory=list)


@dataclass
class QueryIntent:
    """Complete structured intent for a NexaQL query."""
    node: str
    fields: list[str] = field(default_factory=list)
    aggregations: list[IntentAggregation] = field(default_factory=list)
    calcs: list[IntentCalc] = field(default_factory=list)
    filters: list[IntentFilter] = field(default_factory=list)
    calc_filters: list[IntentCalcFilter] = field(default_factory=list)
    special_filters: dict[str, Any] = field(default_factory=dict)
    edges: list[IntentEdge] = field(default_factory=list)
    order_by: list[IntentOrderBy] = field(default_factory=list)
    limit: Optional[int] = None
    offset: Optional[int] = None
    distinct: bool = False
    query_name: Optional[str] = None  # auto-generated if not provided
    visualization: Optional[IntentVisualization] = None


# ── Intent parsing (JSON → QueryIntent) ─────────────────────────────────────


def parse_intent(data: dict[str, Any]) -> QueryIntent:
    """Parse a JSON dict (from LLM output) into a QueryIntent."""

    def _parse_filter(f: dict) -> IntentFilter:
        return IntentFilter(
            field=f["field"],
            op=f.get("op", "eq"),
            value=f.get("value"),
        )

    def _parse_calc_filter(f: dict) -> IntentCalcFilter:
        return IntentCalcFilter(
            expr=f["expr"],
            op=f.get("op", "eq"),
            value=f.get("value"),
        )

    def _parse_agg(a: dict) -> IntentAggregation:
        return IntentAggregation(
            alias=a["alias"],
            func=a["func"],
            field=a.get("field"),
        )

    def _parse_calc(c: dict) -> IntentCalc:
        return IntentCalc(alias=c["alias"], expr=c["expr"])

    def _parse_order(o: dict) -> IntentOrderBy:
        return IntentOrderBy(
            field=o["field"],
            direction=o.get("direction", "ASC"),
        )

    def _parse_edge(e: dict) -> IntentEdge:
        return IntentEdge(
            name=e["name"],
            fields=e.get("fields", []),
            aggregations=[_parse_agg(a) for a in e.get("aggregations", [])],
            calcs=[_parse_calc(c) for c in e.get("calcs", [])],
            filters=[_parse_filter(f) for f in e.get("filters", [])],
            order_by=[_parse_order(o) for o in e.get("order_by", [])],
            limit=e.get("limit"),
            edges=[_parse_edge(ne) for ne in e.get("edges", [])],
        )

    viz_data = data.get("visualization")
    viz = None
    if isinstance(viz_data, dict) and "chart_type" in viz_data:
        viz = IntentVisualization(
            chart_type=viz_data["chart_type"],
            x_field=viz_data.get("x_field"),
            y_fields=viz_data.get("y_fields", []),
            title=viz_data.get("title"),
        )

    return QueryIntent(
        node=data["node"],
        fields=data.get("fields", []),
        aggregations=[_parse_agg(a) for a in data.get("aggregations", [])],
        calcs=[_parse_calc(c) for c in data.get("calcs", [])],
        filters=[_parse_filter(f) for f in data.get("filters", [])],
        calc_filters=[_parse_calc_filter(f) for f in data.get("calc_filters", [])],
        special_filters=data.get("special_filters", {}),
        edges=[_parse_edge(e) for e in data.get("edges", [])],
        order_by=[_parse_order(o) for o in data.get("order_by", [])],
        limit=data.get("limit"),
        offset=data.get("offset"),
        distinct=data.get("distinct", False),
        query_name=data.get("query_name"),
        visualization=viz,
    )


def extract_intent_json(text: str) -> dict[str, Any] | None:
    """Extract JSON intent from LLM response text.

    Looks for a fenced JSON code block first, then tries to parse the entire
    response as JSON.
    """
    # Try fenced code block: ```json ... ```
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Try bare JSON object
    bare = re.search(r"(\{[\s\S]*\})", text)
    if bare:
        try:
            return json.loads(bare.group(1))
        except json.JSONDecodeError:
            pass

    return None


# ── Deterministic NexaQL builder ─────────────────────────────────────────────


def _format_value(value: Any) -> str:
    """Format a filter value for NexaQL syntax."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        items = ", ".join(_format_value(v) for v in value)
        return f"[{items}]"
    return str(value)


def _build_filter_expr(f: IntentFilter) -> str:
    """Build a single filter expression."""
    if f.op == "eq":
        return f"{f.field}: {_format_value(f.value)}"
    if f.op == "null":
        return f"{f.field}: {{ null: {_format_value(f.value)} }}"
    if f.op in ("in", "not_in"):
        op_name = "not_in" if f.op == "not_in" else "in"
        return f"{f.field}: {{ {op_name}: {_format_value(f.value)} }}"
    # Comparison operators: gt, gte, lt, lte, ne, like
    return f"{f.field}: {{ {f.op}: {_format_value(f.value)} }}"


def _build_calc_filter_expr(f: IntentCalcFilter) -> str:
    """Build a calc filter expression."""
    return f"calc({f.expr}): {{ {f.op}: {_format_value(f.value)} }}"


def _build_node_block(
    node: str,
    fields: list[str],
    aggregations: list[IntentAggregation],
    calcs: list[IntentCalc],
    filters: list[IntentFilter],
    calc_filters: list[IntentCalcFilter],
    special_filters: dict[str, Any],
    edges: list[IntentEdge],
    order_by: list[IntentOrderBy],
    limit: int | None,
    offset: int | None,
    distinct: bool,
    indent: int = 2,
) -> list[str]:
    """Build the lines for a node selection block."""
    pad = " " * indent
    inner_pad = " " * (indent + 2)
    lines: list[str] = []

    # Node name + filters
    filter_parts: list[str] = []
    for f in filters:
        filter_parts.append(_build_filter_expr(f))
    for f in calc_filters:
        filter_parts.append(_build_calc_filter_expr(f))
    for name, value in special_filters.items():
        filter_parts.append(f"{name}: {_format_value(value)}")

    filter_str = ""
    if filter_parts:
        filter_str = "(" + ", ".join(filter_parts) + ")"

    # Directives
    directives: list[str] = []
    if distinct:
        directives.append("@distinct")

    # Build a map from aggregation field arguments to their aliases so that
    # ORDER BY on a raw field used only inside an aggregate (e.g. sum(amount))
    # gets rewritten to the aggregation alias (e.g. total_amount).
    agg_field_to_alias: dict[str, str] = {}
    if aggregations:
        for agg in aggregations:
            if agg.field and agg.field not in fields:
                agg_field_to_alias.setdefault(agg.field, agg.alias)

    for ob in order_by:
        resolved_field = agg_field_to_alias.get(ob.field, ob.field)
        directives.append(f"@orderby({resolved_field}, {ob.direction})")
    if limit is not None:
        directives.append(f"@limit({limit})")
    if offset is not None:
        directives.append(f"@offset({offset})")

    directive_str = ""
    if directives:
        directive_str = " " + " ".join(directives)

    lines.append(f"{pad}{node}{filter_str}{directive_str} {{")

    # Scalar fields
    for f in fields:
        lines.append(f"{inner_pad}{f}")

    # Aggregation fields
    for agg in aggregations:
        if agg.field:
            lines.append(f"{inner_pad}{agg.alias}: {agg.func}({agg.field})")
        else:
            lines.append(f"{inner_pad}{agg.alias}: {agg.func}()")

    # Calc fields
    for calc in calcs:
        lines.append(f"{inner_pad}{calc.alias}: calc({calc.expr})")

    # Edge traversals
    for edge in edges:
        edge_lines = _build_node_block(
            node=edge.name,
            fields=edge.fields,
            aggregations=edge.aggregations,
            calcs=edge.calcs,
            filters=edge.filters,
            calc_filters=[],
            special_filters={},
            edges=edge.edges,
            order_by=edge.order_by,
            limit=edge.limit,
            offset=None,
            distinct=False,
            indent=indent + 2,
        )
        lines.extend(edge_lines)

    lines.append(f"{pad}}}")
    return lines


def _generate_query_name(intent: QueryIntent) -> str:
    """Generate a reasonable query name from the intent."""
    if intent.query_name:
        return intent.query_name
    # CamelCase the node name
    parts = intent.node.replace("_", " ").title().replace(" ", "")
    if intent.aggregations:
        return f"{parts}Summary"
    if intent.filters or intent.calc_filters:
        return f"Filtered{parts}"
    if intent.order_by and intent.limit:
        return f"Top{parts}"
    return f"Get{parts}"


def build_nexaql(intent: QueryIntent) -> str:
    """Build a syntactically correct NexaQL query string from a QueryIntent.

    This is the deterministic builder — no LLM involved. The output is
    guaranteed to be parseable NexaQL (though it may still fail ontology
    validation if the intent references non-existent fields/nodes).
    """
    query_name = _generate_query_name(intent)

    lines = [f"query {query_name} {{"]
    body_lines = _build_node_block(
        node=intent.node,
        fields=intent.fields,
        aggregations=intent.aggregations,
        calcs=intent.calcs,
        filters=intent.filters,
        calc_filters=intent.calc_filters,
        special_filters=intent.special_filters,
        edges=intent.edges,
        order_by=intent.order_by,
        limit=intent.limit,
        offset=intent.offset,
        distinct=intent.distinct,
    )
    lines.extend(body_lines)
    lines.append("}")

    return "\n".join(lines)


# ── Fan-out decomposition ──────────────────────────────────────────────────


def needs_decomposition(intent: QueryIntent) -> bool:
    """Return True when a multi-edge intent would produce a cartesian product.

    Multiple independent one-to-many edges from the same root node are joined
    as flat LEFT JOINs, creating N×M×K rows instead of max(N,M,K). Decomposing
    into separate per-edge queries prevents this.
    """
    return len(intent.edges) >= 2


def decompose_intent(intent: QueryIntent) -> list[QueryIntent]:
    """Split a multi-edge intent into one sub-intent per edge.

    Each sub-intent keeps the root node, its scalar fields, filters, and
    exactly one edge. This prevents the cartesian product that would result
    from joining multiple independent one-to-many edges in a single query.

    Returns the original intent unchanged if decomposition is not needed.
    """
    if not needs_decomposition(intent):
        return [intent]

    sub_intents: list[QueryIntent] = []
    for edge in intent.edges:
        sub = QueryIntent(
            node=intent.node,
            fields=list(intent.fields),
            aggregations=list(intent.aggregations),
            calcs=list(intent.calcs),
            filters=list(intent.filters),
            calc_filters=list(intent.calc_filters),
            special_filters=dict(intent.special_filters),
            edges=[edge],
            order_by=list(intent.order_by),
            limit=intent.limit,
            offset=intent.offset,
            distinct=intent.distinct,
            query_name=f"{intent.query_name or 'Q'}_{edge.name}",
        )
        sub_intents.append(sub)

    return sub_intents
