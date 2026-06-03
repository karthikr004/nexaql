# Copyright (c) 2026-present NexaQL Contributors
"""NexaQL query validator -- checks AST nodes against an ontology schema."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol

from nexaql.engine.system_functions import find_unknown_functions
from nexaql.engine.types import (
    QueryAST,
    NodeSelection,
    SuggestContext,
    SuggestionItem,
    ValidationError,
    ValidationResult,
)

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Ontology type stubs -- lightweight protocols so this module has zero
# dependency on the concrete ontology loader / YAML models.
# ---------------------------------------------------------------------------


class FieldDef(Protocol):
    type: str
    filterable: bool
    derived: bool
    sql_expr: Optional[str]
    values: Optional[List[str]]
    description: str


class JoinStep(Protocol):
    table: str
    alias_key: str
    condition: str


class OntologyEdge(Protocol):
    node: str
    description: str
    join_steps: List[Any]


class SpecialFilter(Protocol):
    description: str
    type: Optional[str]


class OntologyNode(Protocol):
    fields: Dict[str, Any]  # str -> FieldDef-like
    edges: Optional[Dict[str, Any]]  # str -> OntologyEdge-like
    special_filters: Optional[Dict[str, Any]]  # str -> SpecialFilter-like
    description: str


class Ontology(Protocol):
    nodes: Dict[str, Any]  # str -> OntologyNode-like


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(ast: QueryAST, ontology: Any) -> ValidationResult:
    """Validate an AST against an ontology. Returns errors and warnings."""
    errors: List[ValidationError] = []
    warnings: List[str] = []

    _validate_node(ast.body, ontology, errors, warnings, None)

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


def _validate_node(
    node: NodeSelection,
    ontology: Any,
    errors: List[ValidationError],
    warnings: List[str],
    _parent_node_name: Optional[str],
) -> None:
    node_def = ontology.nodes.get(node.name) if isinstance(ontology.nodes, dict) else None
    if node_def is None:
        available = ", ".join(ontology.nodes.keys()) if isinstance(ontology.nodes, dict) else ""
        errors.append(
            ValidationError(message=f"Unknown node '{node.name}'. Available nodes: {available}")
        )
        return

    fields_map: Dict[str, Any] = getattr(node_def, "fields", {}) or {}
    edges_map: Dict[str, Any] = getattr(node_def, "edges", {}) or {}
    special_filters_map: Dict[str, Any] = getattr(node_def, "special_filters", {}) or {}

    # -- Validate filters ------------------------------------------------------
    for filt in node.filters:
        # Skip policy-injected RLS filters (not user-authored)
        if filt.field == "__rls":
            continue

        # calc(expr) filters use the pseudo-field "__calc" -- skip schema validation,
        # but warn on unknown SQL functions in the expression.
        if filt.calc_expr is not None:
            unknown_fns = find_unknown_functions(filt.calc_expr)
            for fn in unknown_fns:
                warnings.append(
                    f"calc() filter references unknown function '{fn}' "
                    "-- check the system-functions registry"
                )
            continue

        is_special = filt.field in special_filters_map
        if not is_special:
            field_def = fields_map.get(filt.field)
            if field_def is None:
                errors.append(
                    ValidationError(
                        message=f"Field '{filt.field}' does not exist on node '{node.name}'"
                    )
                )
            elif not getattr(field_def, "filterable", False):
                warnings.append(
                    f"Field '{filt.field}' on '{node.name}' is not marked as filterable"
                )

    # -- Validate directives ---------------------------------------------------
    for directive in node.directives:
        if getattr(directive, "type", None) == "orderby":
            field_name = getattr(directive, "field", "")
            field_def = fields_map.get(field_name)
            if field_def is None:
                # It might be an aliased aggregation -- only warn
                warnings.append(
                    f"@orderby field '{field_name}' not found on '{node.name}' "
                    "-- ensure it's an aggregation alias or derived field"
                )

    # -- Validate fields -------------------------------------------------------
    has_aggregation = False
    for field in node.fields:
        if field.kind == "aggregation":
            has_aggregation = True
            if field.func != "count" and field.argument != "*":
                field_def = fields_map.get(field.argument)
                if field_def is None:
                    errors.append(
                        ValidationError(
                            message=f"Aggregation argument '{field.argument}' not found on '{node.name}'"
                        )
                    )
        elif field.kind == "scalar":
            field_def = fields_map.get(field.name)
            if field_def is None:
                errors.append(
                    ValidationError(
                        message=f"Field '{field.name}' does not exist on node '{node.name}'"
                    )
                )
            # Derived fields with sql_expr are valid -- translator handles expression expansion
            if field_def is not None and getattr(field_def, "derived", False) and not getattr(field_def, "sql_expr", None):
                errors.append(
                    ValidationError(
                        message=f"Derived field '{field.name}' on '{node.name}' is missing sql_expr in ontology"
                    )
                )
        elif field.kind == "calc":
            # calc(expr) fields are runtime-computed -- validate alias and function names.
            if not getattr(field, "alias", None):
                errors.append(ValidationError(message="calc() field is missing an alias"))
            unknown_fns = find_unknown_functions(field.expr)
            for fn in unknown_fns:
                warnings.append(
                    f"calc() references unknown function '{fn}' "
                    "-- check the system-functions registry for supported SQL functions"
                )
        elif field.kind == "edge":
            edge_def = edges_map.get(field.node.name)
            if edge_def is None:
                available = ", ".join(edges_map.keys()) if edges_map else "none"
                errors.append(
                    ValidationError(
                        message=(
                            f"Edge '{field.node.name}' not defined on node '{node.name}'. "
                            f"Available edges: {available}"
                        )
                    )
                )
            else:
                # Resolve the target node name from the edge definition
                # The query uses edge names (e.g. "items"), but the ontology nodes
                # are keyed by node names (e.g. "order_item").
                target_node_name = getattr(edge_def, "node", None) or (
                    edge_def.get("node") if isinstance(edge_def, dict) else None
                )
                if target_node_name:
                    # Create a shallow copy of the child node with the resolved name
                    resolved_child = NodeSelection(
                        kind=field.node.kind,
                        name=target_node_name,
                        filters=field.node.filters,
                        directives=field.node.directives,
                        fields=field.node.fields,
                    )
                    _validate_node(resolved_child, ontology, errors, warnings, node.name)
                else:
                    _validate_node(field.node, ontology, errors, warnings, node.name)

    # Warn if mixing aggregations and non-aggregation scalars (auto-group-by will apply)
    if has_aggregation:
        has_scalars = any(f.kind == "scalar" for f in node.fields)
        if has_scalars:
            warnings.append(
                f"Node '{node.name}' has both scalar fields and aggregations "
                "-- scalar fields will be added to GROUP BY automatically"
            )


# ---------------------------------------------------------------------------
# Autocomplete suggestions
# ---------------------------------------------------------------------------


def get_suggestions(ontology: Any, context: SuggestContext) -> List[SuggestionItem]:
    """Returns autocomplete suggestions for a given cursor context."""
    ctx_type = context.type
    node_name = context.node_name
    partial = context.partial

    nodes_map: Dict[str, Any] = getattr(ontology, "nodes", {}) or {}

    if ctx_type == "node":
        # Suggest top-level node names
        return [
            SuggestionItem(
                label=name,
                kind="node",
                detail=getattr(defn, "description", None),
                insert_text=name,
            )
            for name, defn in nodes_map.items()
            if not partial or name.startswith(partial)
        ]

    elif ctx_type == "field":
        if not node_name:
            return []
        node_def = nodes_map.get(node_name)
        if node_def is None:
            return []

        fields_map: Dict[str, Any] = getattr(node_def, "fields", {}) or {}
        edges_map: Dict[str, Any] = getattr(node_def, "edges", {}) or {}

        fields: List[SuggestionItem] = [
            SuggestionItem(
                label=name,
                kind="field",
                detail=(
                    f"{getattr(defn, 'type', '')}{'  <derived>' if getattr(defn, 'derived', False) else ''}"
                    f" -- {getattr(defn, 'description', '')}"
                ),
                insert_text=name,
            )
            for name, defn in fields_map.items()
            if not partial or name.startswith(partial)
        ]

        edges: List[SuggestionItem] = [
            SuggestionItem(
                label=name,
                kind="edge",
                detail=getattr(defn, "description", None),
                insert_text=f"{name} {{\n  \n}}",
            )
            for name, defn in edges_map.items()
            if not partial or name.startswith(partial)
        ]

        aggs: List[SuggestionItem] = [
            SuggestionItem(
                label=f"alias: {fn}(field)",
                kind="aggregation",
                detail=f"{fn.upper()} aggregation",
                insert_text=f"${{1:alias}}: {fn}(${{2:field}})",
            )
            for fn in ("sum", "avg", "min", "max", "count")
        ]

        return fields + edges + aggs

    elif ctx_type == "filter":
        if not node_name:
            return []
        node_def = nodes_map.get(node_name)
        if node_def is None:
            return []

        fields_map = getattr(node_def, "fields", {}) or {}
        special_filters_map: Dict[str, Any] = getattr(node_def, "special_filters", {}) or {}

        field_suggestions: List[SuggestionItem] = []
        for name, defn in fields_map.items():
            if not getattr(defn, "filterable", False):
                continue
            field_type = getattr(defn, "type", "string")
            insert = f'{name}: ""' if field_type == "string" else f"{name}: "
            base = SuggestionItem(
                label=name,
                kind="filter",
                detail=f"{field_type} -- eq filter",
                insert_text=insert,
            )
            field_suggestions.append(base)
            # Add operator variants for numeric/date
            if field_type in ("numeric", "integer", "date"):
                for op in ("_gt", "_gte", "_lt", "_lte"):
                    field_suggestions.append(
                        SuggestionItem(
                            label=f"{name}{op}",
                            kind="filter",
                            detail=f"{name} {op.lstrip('_')} filter",
                            insert_text=f"{name}{op}: ",
                        )
                    )

        special: List[SuggestionItem] = [
            SuggestionItem(
                label=name,
                kind="special-filter",
                detail=getattr(defn, "description", None),
                insert_text=f"{name}: true",
            )
            for name, defn in special_filters_map.items()
        ]

        combined = field_suggestions + special
        if partial:
            combined = [s for s in combined if s.label.startswith(partial)]
        return combined

    elif ctx_type == "directive":
        items: List[SuggestionItem] = [
            SuggestionItem(
                label="@limit",
                kind="directive",
                detail="Limit result rows",
                insert_text="@limit(${1:10})",
            ),
            SuggestionItem(
                label="@offset",
                kind="directive",
                detail="Skip N rows",
                insert_text="@offset(${1:0})",
            ),
            SuggestionItem(
                label="@orderby",
                kind="directive",
                detail="Order results",
                insert_text="@orderby(${1:field}, ${2:ASC})",
            ),
            SuggestionItem(
                label="@distinct",
                kind="directive",
                detail="Remove duplicate rows",
                insert_text="@distinct",
            ),
        ]
        if partial:
            items = [s for s in items if s.label.startswith(partial)]
        return items

    return []
