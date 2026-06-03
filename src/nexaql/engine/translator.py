# Copyright (c) 2026-present NexaQL Contributors
"""NexaQL query translator -- converts an AST + ontology into SQL."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol

from nexaql.engine.dialect import get_calc_translator
from nexaql.engine.types import (
    AggregationField,
    CalcField,
    EdgeField,
    Filter,
    FilterValue,
    NodeSelection,
    NodeShape,
    QueryAST,
    ScalarField,
)

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Ontology type stubs -- lightweight protocols to avoid circular imports
# with the concrete ontology loader.
# ---------------------------------------------------------------------------


class FieldDef(Protocol):
    type: str
    filterable: bool
    derived: bool
    sql_expr: Optional[str]
    values: Optional[List[str]]


class JoinStep(Protocol):
    table: str
    alias_key: str
    condition: str


class OntologyEdge(Protocol):
    node: str
    join_steps: List[Any]
    join_type: Optional[str]


class SpecialFilter(Protocol):
    description: str
    type: Optional[str]
    requires_edge: Optional[str]
    sql: str


class OntologyNode(Protocol):
    table: str
    fields: Dict[str, Any]
    edges: Optional[Dict[str, Any]]
    special_filters: Optional[Dict[str, Any]]
    datasource: Optional[str]


class DatasourceConfig(Protocol):
    type: str


class Ontology(Protocol):
    nodes: Dict[str, Any]
    datasources: Optional[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TranslateError(Exception):
    """Raised when a query AST cannot be translated to SQL."""


# ---------------------------------------------------------------------------
# Internal structures
# ---------------------------------------------------------------------------


@dataclass
class _JoinEntry:
    sql: str
    alias_key: str


@dataclass
class TranslatorContext:
    ontology: Any
    aliases: Dict[str, str] = field(default_factory=dict)  # alias_key -> SQL alias
    joins: Dict[str, _JoinEntry] = field(default_factory=dict)  # alias_key -> JOIN clause
    selects: List[str] = field(default_factory=list)
    wheres: List[str] = field(default_factory=list)
    group_bys: List[str] = field(default_factory=list)
    order_bys: List[str] = field(default_factory=list)
    limit: Optional[int] = None
    offset: Optional[int] = None
    has_agg: bool = False
    counter: int = 0
    dialect: str = "postgresql"


# ---------------------------------------------------------------------------
# Alias helpers
# ---------------------------------------------------------------------------


def _make_alias(base_name: str, ctx: TranslatorContext) -> str:
    parts = base_name.split("_")
    prefix = "".join(p[0] for p in parts if p)[:3] or "t"
    alias = f"{prefix}{ctx.counter}"
    ctx.counter += 1
    return alias


def _get_or_create_alias(alias_key: str, ctx: TranslatorContext) -> str:
    if alias_key not in ctx.aliases:
        ctx.aliases[alias_key] = _make_alias(alias_key, ctx)
    return ctx.aliases[alias_key]


# ---------------------------------------------------------------------------
# Expression resolution helpers
# ---------------------------------------------------------------------------


def _resolve_condition(condition: str, ctx: TranslatorContext) -> str:
    """Replace {alias_key} placeholders with actual SQL aliases."""
    def _replacer(m: re.Match) -> str:
        key = m.group(1)
        alias = ctx.aliases.get(key)
        if alias is None:
            raise TranslateError(
                f"Cannot resolve alias for '{key}' -- ensure join order is correct"
            )
        return alias

    return re.sub(r"\{([^}]+)\}", _replacer, condition)


def _resolve_derived_expr(
    sql_expr: str, node_alias: str, ctx: TranslatorContext
) -> str:
    """
    Resolves a derived field's sql_expr template.
    Replaces {node} with the current table alias.
    Any other {key} placeholders are also resolved via the alias map.
    """
    out = sql_expr.replace("{node}", node_alias)

    def _replacer(m: re.Match) -> str:
        key = m.group(1)
        alias = ctx.aliases.get(key)
        if alias is None:
            raise TranslateError(
                f"Derived field references alias '{key}' which is not yet joined"
            )
        return alias

    return re.sub(r"\{([^}]+)\}", _replacer, out)


# ---------------------------------------------------------------------------
# calc() expression expansion
# ---------------------------------------------------------------------------


def _expand_calc_expr(
    expr: str,
    table_alias: str,
    node_def: Any,
    dialect: str = "postgresql",
    ctx: Optional[TranslatorContext] = None,
) -> str:
    """
    Expands field references inside a calc() expression, then applies dialect translation.

    Step 1 -- cross-entity refs: dotted references like ``entity.field`` are resolved by
              looking up the entity as an edge on the current node, auto-joining via its
              join_steps, and qualifying the field with the edge target's alias.
    Step 2 -- local field expansion: bare identifiers that match node fields -> tableAlias.field
    Step 3 -- dialect translation: function/cast/date-arithmetic patterns -> target dialect

    SQL keywords and function names are left untouched during step 1-2 (they are not
    in node_def.fields), then transformed in step 3 as needed.
    """
    expanded = expr
    fields_map: Dict[str, Any] = getattr(node_def, "fields", {}) or {} if node_def else {}
    edges_map: Dict[str, Any] = getattr(node_def, "edges", {}) or {} if node_def else {}

    if node_def and ctx:
        # Step 1: resolve dotted cross-entity references (e.g. contract_pricing_terms.agreed_unit_price)
        def _replace_dotted(m: re.Match) -> str:
            edge_name = m.group(1)
            field_name = m.group(2)

            edge_def = edges_map.get(edge_name)
            if edge_def is None:
                return m.group(0)  # not an edge -- leave as-is (could be SQL func like pg_catalog.func)

            # Validate the field exists on the target node
            target_node_name = getattr(edge_def, "node", None)
            target_node_def = ctx.ontology.nodes.get(target_node_name) if target_node_name else None
            target_fields: Dict[str, Any] = getattr(target_node_def, "fields", {}) or {} if target_node_def else {}
            if not target_fields.get(field_name):
                raise TranslateError(
                    f"Field '{field_name}' not found on edge target '{target_node_name}' "
                    f"(via edge '{edge_name}')"
                )

            # Auto-join via edge's join_steps (deduplication handled by _process_join_steps)
            join_steps = getattr(edge_def, "join_steps", []) or []
            join_type = getattr(edge_def, "join_type", "LEFT") or "LEFT"
            _process_join_steps(join_steps, join_type, ctx)

            # Resolve to the edge target's alias
            edge_alias = ctx.aliases.get(edge_name)
            if edge_alias is None:
                raise TranslateError(
                    f"Cannot resolve alias for edge '{edge_name}' after join"
                )
            return f"{edge_alias}.{field_name}"

        expanded = re.sub(
            r"([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)",
            _replace_dotted,
            expanded,
        )

    # Step 2: qualify local field references
    if node_def:
        def _replace_local(m: re.Match) -> str:
            ident = m.group(0)
            if ident in fields_map:
                return f"{table_alias}.{ident}"
            return ident

        expanded = re.sub(
            r"(?<![.:])[a-zA-Z_][a-zA-Z0-9_]*",
            _replace_local,
            expanded,
        )

    # Step 3: translate to target dialect
    return get_calc_translator(dialect).translate(expanded)


# ---------------------------------------------------------------------------
# JOIN helpers
# ---------------------------------------------------------------------------


def _join_keyword(join_type: str) -> str:
    t = join_type.upper()
    if t in ("LEFT", "LEFT JOIN"):
        return "LEFT JOIN"
    return "JOIN"


def _process_join_steps(
    steps: List[Any], join_type: str, ctx: TranslatorContext
) -> None:
    for step in steps:
        alias_key = getattr(step, "alias_key", None) or step.get("alias_key") if isinstance(step, dict) else step.alias_key
        if alias_key in ctx.joins:
            continue

        table = getattr(step, "table", None) or (step.get("table") if isinstance(step, dict) else None)
        condition = getattr(step, "condition", None) or (step.get("condition") if isinstance(step, dict) else None)

        alias = _get_or_create_alias(alias_key, ctx)
        on_clause = _resolve_condition(condition, ctx)
        ctx.joins[alias_key] = _JoinEntry(
            sql=f"{_join_keyword(join_type)} {table} {alias} ON {on_clause}",
            alias_key=alias_key,
        )


# ---------------------------------------------------------------------------
# Filter -> SQL
# ---------------------------------------------------------------------------


def _sql_literal(value: Any, _node: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f"'{value.replace(chr(39), chr(39) + chr(39))}'"
    if isinstance(value, list):
        return ", ".join(_sql_literal(v, _node) for v in value)
    return "NULL"


def _filter_to_sql(
    filt: Filter,
    table_alias: str,
    node_def: Any,
    ctx: TranslatorContext,
) -> str:
    fields_map: Dict[str, Any] = getattr(node_def, "fields", {}) or {}
    edges_map: Dict[str, Any] = getattr(node_def, "edges", {}) or {}
    special_filters_map: Dict[str, Any] = getattr(node_def, "special_filters", {}) or {}

    # -- Row-level security (raw WHERE clause from policy enforcer) ------------
    if filt.field == "__rls":
        # Value contains a SQL condition. Qualify bare field names that exist
        # on this node with the table alias, but leave subquery internals alone.
        raw_condition = str(filt.value)
        # Only qualify field names at the START of the condition (before any subquery)
        # e.g. "region = 'EU'" → "c0.region = 'EU'"
        # e.g. "customer_id IN (SELECT ...)" → "o0.customer_id IN (SELECT ...)"
        import re as _re
        def _qualify_leading_field(m: _re.Match) -> str:
            field_name = m.group(1)
            if field_name in fields_map:
                return f"{table_alias}.{field_name}"
            return field_name
        # Match leading identifier before an operator or IN/NOT
        qualified = _re.sub(
            r'^([a-zA-Z_]\w*)',
            _qualify_leading_field,
            raw_condition.strip(),
        )
        return qualified

    # -- calc(expr) filter -----------------------------------------------------
    if filt.calc_expr is not None:
        col = _expand_calc_expr(filt.calc_expr, table_alias, node_def, ctx.dialect, ctx)
        val = _sql_literal(filt.value, node_def)
        op = filt.op if isinstance(filt.op, str) else filt.op.value
        if op == "is_null":
            return f"({col}) IS NULL"
        if op == "not_null":
            return f"({col}) IS NOT NULL"
        op_map = {
            "eq": "=", "ne": "!=", "gt": ">", "gte": ">=",
            "lt": "<", "lte": "<=", "like": "ILIKE",
        }
        if op in op_map:
            return f"({col}) {op_map[op]} {val}"
        if op == "in":
            items = ", ".join(_sql_literal(v, node_def) for v in (filt.value if isinstance(filt.value, list) else []))
            return f"({col}) IN ({items})"
        if op == "not_in":
            items = ", ".join(_sql_literal(v, node_def) for v in (filt.value if isinstance(filt.value, list) else []))
            return f"({col}) NOT IN ({items})"
        return f"({col}) = {val}"

    # -- special filter --------------------------------------------------------
    special_def = special_filters_map.get(filt.field)
    if special_def is not None:
        requires_edge = getattr(special_def, "requires_edge", None)
        if requires_edge:
            edge_def = edges_map.get(requires_edge)
            if edge_def:
                join_steps = getattr(edge_def, "join_steps", []) or []
                join_type = getattr(edge_def, "join_type", "LEFT") or "LEFT"
                _process_join_steps(join_steps, join_type, ctx)
        sql_template = getattr(special_def, "sql", "")
        with_value = sql_template.replace("{value}", str(filt.value))
        return _resolve_condition(with_value, ctx)

    # -- regular field filter --------------------------------------------------
    field_def = fields_map.get(filt.field)
    if field_def is not None and getattr(field_def, "derived", False) and getattr(field_def, "sql_expr", None):
        col = _resolve_derived_expr(field_def.sql_expr, table_alias, ctx)
    else:
        col = f"{table_alias}.{filt.field}"

    op = filt.op if isinstance(filt.op, str) else filt.op.value
    if op == "is_null":
        return f"{col} IS NULL"
    if op == "not_null":
        return f"{col} IS NOT NULL"

    val = _sql_literal(filt.value, node_def)
    op_map = {
        "eq": "=", "ne": "!=", "gt": ">", "gte": ">=",
        "lt": "<", "lte": "<=", "like": "ILIKE",
    }
    if op in op_map:
        return f"{col} {op_map[op]} {val}"
    if op == "in":
        items = ", ".join(_sql_literal(v, node_def) for v in (filt.value if isinstance(filt.value, list) else []))
        return f"{col} IN ({items})"
    if op == "not_in":
        items = ", ".join(_sql_literal(v, node_def) for v in (filt.value if isinstance(filt.value, list) else []))
        return f"{col} NOT IN ({items})"
    return f"{col} = {val}"


# ---------------------------------------------------------------------------
# Node processing
# ---------------------------------------------------------------------------


def _process_node(
    node: NodeSelection,
    ctx: TranslatorContext,
    is_root: bool,
    edge_name: Optional[str],
) -> NodeShape:
    """Recursively processes a node, emitting SELECTs/JOINs/WHEREs and returning a NodeShape."""
    node_def = ctx.ontology.nodes.get(node.name) if isinstance(ctx.ontology.nodes, dict) else None
    if node_def is None:
        raise TranslateError(f"Unknown node '{node.name}'")

    fields_map: Dict[str, Any] = getattr(node_def, "fields", {}) or {}
    edges_map: Dict[str, Any] = getattr(node_def, "edges", {}) or {}

    # Root alias is pre-created; edge aliases are created on demand by join steps
    table_alias = ctx.aliases.get(node.name) or _get_or_create_alias(node.name, ctx)

    # -- Filters ---------------------------------------------------------------
    for filt in node.filters:
        ctx.wheres.append(_filter_to_sql(filt, table_alias, node_def, ctx))

    # -- Directives (root only) ------------------------------------------------
    if is_root:
        _apply_directives(node.directives, ctx, node_def, node.name)

    my_column_aliases: List[str] = []
    my_agg_aliases: List[str] = []
    scalar_raw_exprs: List[str] = []  # for GROUP BY
    children: List[NodeShape] = []

    for f in node.fields:
        if f.kind == "aggregation":
            ctx.has_agg = True
            agg: AggregationField = f  # type: ignore[assignment]
            arg = "*" if agg.argument == "*" else f"{table_alias}.{agg.argument}"
            ctx.selects.append(f"{agg.func.upper()}({arg}) AS {agg.alias}")
            my_agg_aliases.append(agg.alias)

        elif f.kind == "scalar":
            sf: ScalarField = f  # type: ignore[assignment]
            field_def = fields_map.get(sf.name)
            # Derived fields use their sql_expr; regular fields use alias.column_name
            if field_def is not None and getattr(field_def, "derived", False) and getattr(field_def, "sql_expr", None):
                raw_col = _resolve_derived_expr(field_def.sql_expr, table_alias, ctx)
            else:
                raw_col = f"{table_alias}.{sf.name}"
            # User alias takes precedence, otherwise use node-prefixed alias for unambiguous grouping
            col_alias = sf.alias if sf.alias else f"{node.name}__{sf.name}"
            ctx.selects.append(f"{raw_col} AS {col_alias}")
            scalar_raw_exprs.append(raw_col)
            my_column_aliases.append(col_alias)

        elif f.kind == "calc":
            cf: CalcField = f  # type: ignore[assignment]
            expanded_expr = _expand_calc_expr(cf.expr, table_alias, node_def, ctx.dialect, ctx)
            ctx.selects.append(f"{expanded_expr} AS {cf.alias}")
            scalar_raw_exprs.append(expanded_expr)
            my_column_aliases.append(cf.alias)

        elif f.kind == "edge":
            ef: EdgeField = f  # type: ignore[assignment]
            edge_def = edges_map.get(ef.node.name)
            if edge_def is None:
                raise TranslateError(
                    f"Edge '{ef.node.name}' not defined on '{node.name}'"
                )
            join_steps = getattr(edge_def, "join_steps", []) or []
            join_type = getattr(edge_def, "join_type", "JOIN") or "JOIN"
            _process_join_steps(join_steps, join_type, ctx)
            # Resolve edge name → target node name (e.g. "items" → "order_item")
            target_node_name = getattr(edge_def, "node", None) or (
                edge_def.get("node") if isinstance(edge_def, dict) else ef.node.name
            )
            resolved_child = NodeSelection(
                kind=ef.node.kind,
                name=target_node_name,
                filters=ef.node.filters,
                directives=ef.node.directives,
                fields=ef.node.fields,
            )
            child_shape = _process_node(resolved_child, ctx, False, ef.node.name)
            children.append(child_shape)

    # GROUP BY: when this node has aggregations, its scalar columns go into GROUP BY
    if my_agg_aliases:
        for expr in scalar_raw_exprs:
            if expr not in ctx.group_bys:
                ctx.group_bys.append(expr)

    return NodeShape(
        edge_name=edge_name,
        node=node.name,
        column_aliases=my_column_aliases,
        aggregation_aliases=my_agg_aliases,
        children=children,
    )


# ---------------------------------------------------------------------------
# Directives
# ---------------------------------------------------------------------------


def _apply_directives(
    directives: List[Any],
    ctx: TranslatorContext,
    node_def: Any = None,
    node_name: Optional[str] = None,
) -> None:
    fields_map: Dict[str, Any] = getattr(node_def, "fields", {}) or {} if node_def else {}

    for d in directives:
        d_type = getattr(d, "type", None)
        if d_type == "limit":
            ctx.limit = getattr(d, "value", None)
        elif d_type == "offset":
            ctx.offset = getattr(d, "value", None)
        elif d_type == "orderby":
            d_field = getattr(d, "field", "")
            d_direction = getattr(d, "direction", "ASC")
            # If the orderby field is a derived ontology field, use the node-prefixed column alias
            # so PostgreSQL can resolve it (derived fields have no physical column name).
            # calc() aliases are bare aliases in SELECT and resolve directly -- leave them as-is.
            field_def = fields_map.get(d_field)
            if field_def is not None and getattr(field_def, "derived", False) and node_name:
                order_expr = f"{node_name}__{d_field}"
            else:
                order_expr = d_field
            ctx.order_bys.append(f"{order_expr} {d_direction}")
        elif d_type == "distinct":
            pass  # handled at SQL assembly time


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class TranslateResult:
    sql: str
    shape: NodeShape


def translate(ast: QueryAST, ontology: Any) -> TranslateResult:
    """Translate an AST + ontology into SQL and a result shape descriptor."""
    root_node = ast.body
    nodes_map: Dict[str, Any] = getattr(ontology, "nodes", {}) or {}
    root_def = nodes_map.get(root_node.name)
    if root_def is None:
        raise TranslateError(f"Unknown root node '{root_node.name}'")

    # Resolve query dialect directly from the datasource type.
    # The type IS the dialect -- postgresql -> postgresql SQL, snowflake -> Snowflake SQL, etc.
    # REST datasources don't emit SQL; their adapter handles translation separately.
    ds_name = getattr(root_def, "datasource", None)
    datasources_map: Dict[str, Any] = getattr(ontology, "datasources", {}) or {}
    ds_cfg = datasources_map.get(ds_name) if ds_name else None
    if ds_cfg is not None and getattr(ds_cfg, "type", "rest") != "rest":
        dialect: str = getattr(ds_cfg, "type", "postgresql")
    else:
        dialect = "postgresql"

    ctx = TranslatorContext(
        ontology=ontology,
        dialect=dialect,
    )

    # Pre-create root alias so join conditions can reference it
    root_alias = _get_or_create_alias(root_node.name, ctx)

    shape = _process_node(root_node, ctx, True, None)

    # Fallback GROUP BY: if aggregations exist but no group-by yet,
    # collect all non-aggregate SELECT expressions
    if ctx.has_agg and not ctx.group_bys:
        for s in ctx.selects:
            if "(" not in s:
                expr = s.split(" AS ")[0].strip() if " AS " in s else s
                ctx.group_bys.append(expr)

    is_distinct = any(getattr(d, "type", None) == "distinct" for d in root_node.directives)
    select_keyword = "SELECT DISTINCT" if is_distinct else "SELECT"

    lines: List[str] = []
    lines.append(select_keyword)
    select_sep = ",\n  "
    lines.append("  " + select_sep.join(ctx.selects))

    root_table = getattr(root_def, "table", root_node.name)
    lines.append(f"FROM {root_table} {root_alias}")

    for entry in ctx.joins.values():
        lines.append(entry.sql)

    if ctx.wheres:
        where_sep = "\n  AND "
        lines.append("WHERE")
        lines.append("  " + where_sep.join(ctx.wheres))

    if ctx.group_bys:
        gb_sep = ",\n  "
        lines.append("GROUP BY")
        lines.append("  " + gb_sep.join(ctx.group_bys))

    if ctx.order_bys:
        lines.append(f"ORDER BY {', '.join(ctx.order_bys)}")

    if ctx.limit is not None:
        lines.append(f"LIMIT {ctx.limit}")

    if ctx.offset is not None:
        lines.append(f"OFFSET {ctx.offset}")

    return TranslateResult(sql="\n".join(lines), shape=shape)
