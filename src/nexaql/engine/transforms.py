# Copyright (c) 2026-present NexaQL Contributors
"""Post-parse AST transforms.

Deterministic rewrites applied after parsing and before translation.
"""

from __future__ import annotations

import re

from .types import (
    CalcField,
    EdgeField,
    Field,
    NodeSelection,
    QueryAST,
    RequiredDirective,
)

_NULL_TOLERANT = re.compile(
    r"\b(?:COALESCE|NULLIF|IFNULL|ISNULL|NVL)\s*\(",
    re.IGNORECASE,
)

_DOTTED_REF = re.compile(r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b", re.IGNORECASE)


def _extract_required_edges(expr: str) -> set[str]:
    """Extract edge names from dotted references in a calc expression,
    skipping expressions that are null-tolerant (COALESCE, etc.).

    Only dotted references (edge_name.field_name) unambiguously name an edge.
    Bare identifiers belong to the current node.
    """
    if _NULL_TOLERANT.search(expr):
        return set()
    return {m.group(1) for m in _DOTTED_REF.finditer(expr)}


def _collect_required_edge_names(node: NodeSelection) -> set[str]:
    """Collect edge names that must produce rows based on calc/filter context."""
    required: set[str] = set()

    for f in node.fields:
        if isinstance(f, CalcField):
            required |= _extract_required_edges(f.expr)

    for filt in node.filters:
        if filt.calc_expr:
            required |= _extract_required_edges(filt.calc_expr)

    return required


def _has_required(node: NodeSelection) -> bool:
    return any(getattr(d, "type", None) == "required" for d in node.directives)


def _promote_required(node: NodeSelection) -> NodeSelection:
    """Walk a NodeSelection and add @required to edges explicitly referenced
    via dotted notation (edge_name.field) in calc expressions.

    Only dotted references trigger promotion — bare field names belong to the
    current node. Expressions wrapped in COALESCE/NULLIF/etc. intentionally
    handle missing relationships and are never promoted.
    """
    required_edges = _collect_required_edge_names(node)

    new_fields: list[Field] = []
    for f in node.fields:
        if isinstance(f, EdgeField):
            child = f.node
            child = _promote_required(child)

            if not _has_required(child) and child.name in required_edges:
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
