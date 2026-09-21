"""Ontology-bound cumulative comparisons, compiled without model-authored SQL."""

from copy import deepcopy
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CumulativeComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["sum"] = "sum"
    measure: str
    reference: str
    threshold: str
    operator: Literal["gt", "gte", "lt", "lte", "eq", "ne"]


def to_one_target(node, edge_name, ontology):
    edge = (node.edges or {}).get(edge_name)
    if edge is None:
        raise ValueError(f"Unknown relationship {edge_name}")
    target = ontology.nodes[edge.node]
    if len(edge.join_steps) != 1 or not target.primary_key:
        raise ValueError(f"Cannot prove relationship {edge_name} is many-to-one")
    step = edge.join_steps[0]
    parts = [part.strip() for part in step.condition.split("=")]
    target_key = "{" + step.alias_key + "}." + target.primary_key
    if len(parts) != 2 or target_key not in parts or not all(re.fullmatch(r"\{\w+\}\.\w+", part) for part in parts):
        raise ValueError(
            f"Relationship {edge_name} must join to the target primary key. Use the contributing detail entity as root, not its parent; reference must point from each detail record to its parent."
        )
    return target


def compile_comparison(intent, ontology):
    if intent.cumulative_comparison is None:
        return intent
    from nexaql.chat.intent import IntentCalcFilter

    spec = CumulativeComparison.model_validate(intent.cumulative_comparison)
    node = ontology.nodes[intent.node]
    target = to_one_target(node, spec.reference, ontology)
    numeric = {"numeric", "decimal", "integer", "int", "float", "double", "number", "bigint"}
    for owner, name in [(node, spec.measure), (target, spec.threshold)]:
        field = owner.fields.get(name)
        if field is None or field.type not in numeric:
            raise ValueError(f"Cumulative comparison requires declared numeric field {name}")
    if target.primary_key not in target.fields:
        raise ValueError("Comparison grouping key must be declared in ontology")
    if not intent.output_grain:
        raise ValueError("Cumulative comparison requires explicit output_grain")
    current = node
    for edge_name in intent.output_grain.get("path", []):
        current = to_one_target(current, edge_name, ontology)

    # Reject unrelated fanout joins that could multiply the contributing measure.
    def check_edges(owner, edges):
        for edge in edges:
            child = to_one_target(owner, edge.name, ontology)
            check_edges(child, edge.edges)

    check_edges(node, intent.edges)
    expr = f"SUM({spec.measure}) OVER (PARTITION BY {spec.reference}.{target.primary_key}) - {spec.reference}.{spec.threshold}"
    expected = IntentCalcFilter(expr=expr, op=spec.operator, value=0)
    if intent.calc_filters and intent.calc_filters != [expected]:
        raise ValueError("Typed comparison cannot be combined with independently authored calc filters")
    result = deepcopy(intent)
    result.calc_filters = [expected]
    result.cumulative_comparison = spec.model_dump()
    return result
