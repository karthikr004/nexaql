# Copyright (c) 2026-present NexaQL Contributors
"""Post-parse AST transforms.

Deterministic rewrites applied after parsing and before translation.
"""

from __future__ import annotations

import re
from typing import Set

from .types import (
    CalcField,
    EdgeField,
    Field,
    NodeSelection,
    QueryAST,
    RequiredDirective,
)


def _collect_edge_names(fields: list[Field]) -> set[str]:
    """Return the set of edge names present in a field list."""
    return {f.node.name for f in fields if isinstance(f, EdgeField)}


def _field_names_in_expr(expr: str) -> set[str]:
    """Extract bare identifiers from a calc expression."""
    return set(re.findall(r"\b([a-z_][a-z0-9_]*)\b", expr, re.IGNORECASE))


def _collect_referenced_fields(node: NodeSelection) -> set[str]:
    """Collect field names used in calc expressions and filters at this node level."""
    refs: set[str] = set()

    for f in node.fields:
        if isinstance(f, CalcField):
            refs |= _field_names_in_expr(f.expr)

    for filt in node.filters:
        if filt.calc_expr:
            refs |= _field_names_in_expr(filt.calc_expr)

    return refs


def _edge_provides_field(edge_node: NodeSelection, field_name: str) -> bool:
    """Check if an edge's selection includes a scalar field with this name."""
    for f in edge_node.fields:
        if getattr(f, "kind", None) == "scalar" and getattr(f, "name", None) == field_name:
            return True
        if getattr(f, "kind", None) == "calc" and getattr(f, "alias", None) == field_name:
            return True
        if getattr(f, "kind", None) == "aggregation" and getattr(f, "alias", None) == field_name:
            return True
    return False


def _has_required(node: NodeSelection) -> bool:
    return any(getattr(d, "type", None) == "required" for d in node.directives)


def _promote_required(node: NodeSelection) -> NodeSelection:
    """Walk a NodeSelection and add @required to edges whose fields are used in
    calc/filter contexts at the parent level.

    The heuristic: if a calc expression at level N references a field name that
    only exists on a child edge at level N, that edge MUST produce a row for
    the calc to be meaningful — so it's promoted to @required (INNER JOIN).
    """
    referenced = _collect_referenced_fields(node)

    new_fields: list[Field] = []
    for f in node.fields:
        if isinstance(f, EdgeField):
            child = f.node
            child = _promote_required(child)

            if not _has_required(child) and referenced:
                edge_field_names = {
                    getattr(sf, "name", None) or getattr(sf, "alias", None)
                    for sf in child.fields
                    if getattr(sf, "kind", None) in ("scalar", "calc", "aggregation")
                }
                if referenced & edge_field_names:
                    child = NodeSelection(
                        kind=child.kind,
                        name=child.name,
                        filters=child.filters,
                        directives=list(child.directives) + [RequiredDirective(type="required")],
                        fields=child.fields,
                    )

            new_fields.append(EdgeField(kind="edge", node=child))
        else:
            new_fields.append(f)

    return NodeSelection(
        kind=node.kind,
        name=node.name,
        filters=node.filters,
        directives=node.directives,
        fields=new_fields,
    )


def auto_require_edges(ast: QueryAST) -> QueryAST:
    """Apply the @required auto-promotion transform to a parsed AST."""
    new_body = _promote_required(ast.body)
    return QueryAST(kind=ast.kind, body=new_body, name=ast.name)
