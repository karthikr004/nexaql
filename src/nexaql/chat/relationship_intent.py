"""Compile absence of a related record as a left-join null check."""

from copy import deepcopy


def compile_missing_relationship(intent, ontology):
    if not intent.missing_relationship:
        return intent
    from nexaql.chat.intent import IntentCalcFilter, IntentEdge

    node = ontology.nodes[intent.node]
    edge = (node.edges or {}).get(intent.missing_relationship)
    if edge is None or (edge.join_type or "LEFT").upper() not in ("LEFT", "LEFT JOIN"):
        raise ValueError("Missing relationship requires a declared left-join edge")
    target = ontology.nodes[edge.node]
    if not target.primary_key or target.primary_key not in target.fields:
        raise ValueError("Missing relationship requires a declared target primary key")
    result = deepcopy(intent)
    selected = next((e for e in result.edges if e.name == intent.missing_relationship), None)
    if selected and (selected.required or selected.filters or selected.edges):
        raise ValueError("Missing relationship cannot also require or filter matching records")
    if selected is None:
        result.edges.append(IntentEdge(name=intent.missing_relationship))
    result.calc_filters.append(
        IntentCalcFilter(expr=f"{intent.missing_relationship}.{target.primary_key}", op="null", value=True)
    )
    return result
