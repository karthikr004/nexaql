# Copyright (c) 2026-present NexaQL Contributors
"""Shared calc-expression analysis for edge reference extraction.

Used by both the AST transform (transforms.py) and the intent-level
auto-require (chat/intent.py) to determine which edges must produce rows.
"""

from __future__ import annotations

import re

_NULL_TOLERANT = re.compile(
    r"\b(?:COALESCE|NULLIF|IFNULL|ISNULL|NVL)\s*\(",
    re.IGNORECASE,
)

_DOTTED_REF = re.compile(
    r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b",
    re.IGNORECASE,
)


def _find_null_tolerant_spans(expr: str) -> list[tuple[int, int]]:
    """Find character ranges covered by null-tolerant function calls.

    Returns (start, end) pairs where start is the beginning of the function
    name and end is one past the closing paren.
    """
    spans: list[tuple[int, int]] = []
    for m in _NULL_TOLERANT.finditer(expr):
        depth = 1
        pos = m.end()
        while pos < len(expr) and depth > 0:
            if expr[pos] == "(":
                depth += 1
            elif expr[pos] == ")":
                depth -= 1
            pos += 1
        spans.append((m.start(), pos))
    return spans


def extract_required_edges(expr: str) -> set[str]:
    """Extract edge names from dotted references that require INNER JOIN.

    A dotted reference (edge_name.field_name) triggers promotion unless it
    appears inside a null-tolerant function call (COALESCE, NULLIF, etc.).
    Null-tolerance is evaluated per-reference, not per-expression — a NULLIF
    protecting against division by zero does not suppress promotion of an
    unrelated edge reference in the same expression.
    """
    protected = _find_null_tolerant_spans(expr)
    edges: set[str] = set()
    for m in _DOTTED_REF.finditer(expr):
        ref_start = m.start()
        if any(start <= ref_start < end for start, end in protected):
            continue
        edges.add(m.group(1))
    return edges
