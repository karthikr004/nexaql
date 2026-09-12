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

_STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.|\'{2})*'")


def _find_masked_spans(expr: str) -> list[tuple[int, int]]:
    """Find character ranges that should be ignored: string literals and
    null-tolerant function calls.

    String literals are masked first so that dotted text and parentheses
    inside quotes do not confuse the null-tolerant span tracker.
    """
    spans: list[tuple[int, int]] = []

    for m in _STRING_LITERAL.finditer(expr):
        spans.append((m.start(), m.end()))

    for m in _NULL_TOLERANT.finditer(expr):
        if any(start <= m.start() < end for start, end in spans):
            continue
        depth = 1
        pos = m.end()
        while pos < len(expr) and depth > 0:
            if expr[pos] == "'" :
                sm = _STRING_LITERAL.match(expr, pos)
                if sm:
                    pos = sm.end()
                    continue
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
    appears inside a string literal or a null-tolerant function call
    (COALESCE, NULLIF, etc.). Null-tolerance is evaluated per-reference,
    not per-expression.
    """
    masked = _find_masked_spans(expr)
    edges: set[str] = set()
    for m in _DOTTED_REF.finditer(expr):
        ref_start = m.start()
        if any(start <= ref_start < end for start, end in masked):
            continue
        edges.add(m.group(1))
    return edges
