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


# ── Ontology graph pathfinding ─────────────────────────────────────────────


def _find_best_chain(
    adj: dict[str, list[tuple[str, str, int]]],
    start: str,
    to_visit: set[str],
) -> list[tuple[str, str, int]] | None:
    """Find the longest chain from *start* visiting nodes in *to_visit*.

    Returns a list of ``(target_node_type, edge_name, join_steps)`` hops.
    Maximises nodes visited first, then prefers junction-table edges (more
    join_steps) as a tiebreaker so mapping tables are chosen over nullable FKs.
    """
    if not to_visit:
        return []

    best: list[tuple[str, str, int]] | None = None
    best_score = (-1, -1)

    for target, edge_name, join_steps in adj.get(start, []):
        if target not in to_visit:
            continue
        sub = _find_best_chain(adj, target, to_visit - {target})
        candidate = [(target, edge_name, join_steps)]
        if sub:
            candidate = candidate + sub

        score = (len(candidate), sum(js for _, _, js in candidate))
        if score > best_score:
            best = candidate
            best_score = score

    return best


def restructure_edges(intent: QueryIntent, ontology: Any) -> QueryIntent:
    """Restructure flat sibling edges into an optimal chain via ontology pathfinding.

    When the LLM produces flat sibling edges (e.g. contracts, purchase_orders,
    invoices all hanging off supplier), this builds the adjacency graph between
    those node types from the ontology and finds the longest single chain that
    covers the most requested nodes with the fewest branches.

    Edge selection prefers junction-table joins (more join_steps) over direct
    FK joins, so ``mapped_purchase_orders`` (via rf_contract_po_map) wins over
    ``purchase_orders`` (direct contract_id FK that may be NULL).
    """
    if len(intent.edges) < 2:
        return intent

    root_def = ontology.nodes.get(intent.node)
    if not root_def or not root_def.edges:
        return intent

    # Only include leaf edges (no sub-edges) as pathfinding candidates.
    # Edges that already have sub-edges express intentional graph traversals
    # from the LLM (e.g. purchase_order → contract) and must not be rearranged
    # — changing their parent node changes which FK join is used.
    edge_data_by_target: dict[str, IntentEdge] = {}
    unresolved_edges: list[IntentEdge] = []
    preserved_edges: list[IntentEdge] = []

    for edge in intent.edges:
        if edge.edges:
            preserved_edges.append(edge)
            continue
        edge_def = root_def.edges.get(edge.name) if root_def.edges else None
        if edge_def:
            edge_data_by_target.setdefault(edge_def.node, edge)
        else:
            unresolved_edges.append(edge)

    if len(edge_data_by_target) < 2:
        return intent

    required_nodes = {intent.node} | set(edge_data_by_target.keys())

    # Build adjacency graph restricted to required node types.
    adj: dict[str, list[tuple[str, str, int]]] = {n: [] for n in required_nodes}
    for node_name in required_nodes:
        node_def = ontology.nodes.get(node_name)
        if not node_def or not node_def.edges:
            continue
        for ename, edef in node_def.edges.items():
            if edef.node in required_nodes and edef.node != node_name:
                adj[node_name].append((edef.node, ename, len(edef.join_steps)))

    # Find the longest chain from the root through all target nodes.
    to_visit = set(edge_data_by_target.keys())
    chain = _find_best_chain(adj, intent.node, to_visit)

    if not chain:
        return intent

    chained_types = {target for target, _, _ in chain}
    unchained_types = to_visit - chained_types

    # Build nested IntentEdge structure from the discovered chain.
    def _make_edge(idx: int) -> IntentEdge:
        target_type, edge_name, _ = chain[idx]
        original = edge_data_by_target.get(target_type)

        sub_edges: list[IntentEdge] = []
        if idx + 1 < len(chain):
            sub_edges.append(_make_edge(idx + 1))
        if original and original.edges:
            sub_edges.extend(original.edges)

        if original:
            return IntentEdge(
                name=edge_name,
                fields=original.fields,
                aggregations=original.aggregations,
                calcs=original.calcs,
                filters=original.filters,
                order_by=original.order_by,
                limit=original.limit,
                edges=sub_edges,
            )
        return IntentEdge(name=edge_name, edges=sub_edges)

    restructured: list[IntentEdge] = [_make_edge(0)]

    for node_type in unchained_types:
        restructured.append(edge_data_by_target[node_type])

    restructured.extend(preserved_edges)
    restructured.extend(unresolved_edges)

    return QueryIntent(
        node=intent.node,
        fields=intent.fields,
        aggregations=intent.aggregations,
        calcs=intent.calcs,
        filters=intent.filters,
        calc_filters=intent.calc_filters,
        special_filters=intent.special_filters,
        edges=restructured,
        order_by=intent.order_by,
        limit=intent.limit,
        offset=intent.offset,
        distinct=intent.distinct,
        query_name=intent.query_name,
        visualization=intent.visualization,
    )


# ── Fan-out decomposition ──────────────────────────────────────────────────


def _count_leaf_edges(edges: list[IntentEdge]) -> int:
    """Count top-level leaf edges that are fan-out sources.

    Edges with sub-edges represent graph traversals and don't fan out.
    Edges that only carry filters (no fields, no aggregations) act as
    query-wide constraints and don't contribute to fan-out either.
    """
    return sum(
        1 for e in edges
        if not e.edges and (e.fields or e.aggregations or e.calcs)
    )


def needs_decomposition(intent: QueryIntent) -> bool:
    """Return True when a multi-edge intent would produce a cartesian product.

    Only flat sibling edges (no sub-edges) cause fan-out. Edges with nested
    sub-edges represent proper graph traversal and are kept together.
    """
    return _count_leaf_edges(intent.edges) >= 2


def decompose_intent(intent: QueryIntent) -> list[QueryIntent]:
    """Split a multi-edge intent into one sub-intent per independent edge.

    Edges that contain sub-edges (nested traversals like PO→invoice) are
    kept intact — they represent intentional graph walks, not fan-out.
    Only flat leaf edges at the same level are split into separate queries.

    Edges that carry filters (e.g. a supplier edge filtering by name) are
    included in every sub-query so the filter is never lost.

    Returns the original intent unchanged if decomposition is not needed.
    """
    if not needs_decomposition(intent):
        return [intent]

    # Edges with filters act as query-wide constraints and must appear in
    # every sub-query so the filter is not lost during decomposition.
    filter_edges = [e for e in intent.edges if e.filters]
    data_edges = [e for e in intent.edges if not e.filters]

    if not data_edges:
        return [intent]

    sub_intents: list[QueryIntent] = []
    for edge in data_edges:
        sub = QueryIntent(
            node=intent.node,
            fields=list(intent.fields),
            aggregations=list(intent.aggregations),
            calcs=list(intent.calcs),
            filters=list(intent.filters),
            calc_filters=list(intent.calc_filters),
            special_filters=dict(intent.special_filters),
            edges=filter_edges + [edge],
            order_by=list(intent.order_by),
            limit=intent.limit,
            offset=intent.offset,
            distinct=intent.distinct,
            query_name=f"{intent.query_name or 'Q'}_{edge.name}",
        )
        sub_intents.append(sub)

    return sub_intents
