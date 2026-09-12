# Copyright (c) 2026-present NexaQL Contributors
"""Post-parse AST transforms.

Deterministic rewrites applied after parsing and before translation.
"""

from __future__ import annotations

from .calc_refs import extract_required_edges
from .types import (
    CalcField,
    EdgeField,
    Field,
    NodeSelection,
    QueryAST,
    RequiredDirective,
)


def _collect_required_edge_names(node: NodeSelection) -> set[str]:
    """Collect edge names that must produce rows based on calc/filter context."""
    required: set[str] = set()

    for f in node.fields:
        if isinstance(f, CalcField):
            required |= extract_required_edges(f.expr)

    for filt in node.filters:
        if filt.calc_expr:
            required |= extract_required_edges(filt.calc_expr)

    return required


def _has_required(node: NodeSelection) -> bool:
    return any(getattr(d, "type", None) == "required" for d in node.directives)


def _promote_required(node: NodeSelection) -> NodeSelection:
    """Walk a NodeSelection and add @required to edges explicitly referenced
    via dotted notation (edge_name.field) in calc expressions.

    If a calc references an edge that has no EdgeField selection, a minimal
    edge selection with @required is synthesized so the translator creates
    an INNER JOIN for it.
    """
    required_edges = _collect_required_edge_names(node)

    existing_edge_names: set[str] = set()
    new_fields: list[Field] = []
    for f in node.fields:
        if isinstance(f, EdgeField):
            existing_edge_names.add(f.node.name)
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

    for edge_name in required_edges - existing_edge_names:
        new_fields.append(EdgeField(
            kind="edge",
            node=NodeSelection(
                kind="node",
                name=edge_name,
                filters=[],
                directives=[RequiredDirective(type="required")],
                fields=[],
            ),
        ))

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
