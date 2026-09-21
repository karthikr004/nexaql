"""Apply an explicit entity output grain without changing calculation filters."""

from copy import deepcopy


def apply_output_grain(intent, ontology):
    grain = intent.output_grain
    if grain is None:
        return intent
    from nexaql.chat.intent import IntentEdge

    path = grain.get("path", [])
    if not isinstance(path, list) or any(not isinstance(step, str) for step in path):
        raise ValueError("Output grain path must be a list of ontology edge names")
    node = ontology.nodes.get(intent.node)
    if node is None:
        raise ValueError("Unknown calculation node")
    edge = None
    for step in path:
        edge = (node.edges or {}).get(step)
        if edge is None:
            raise ValueError("Unknown output-grain relationship")
        node = ontology.nodes[edge.node]
    fields = grain.get("fields", [])
    if not isinstance(fields, list) or any(f not in node.fields for f in fields):
        raise ValueError("Output grain contains unknown fields")
    key = node.primary_key
    if not key or key not in node.fields:
        raise ValueError("Output grain requires a declared primary key")
    fields = list(dict.fromkeys([key, *fields]))
    result = deepcopy(intent)

    # Filter-only edges retain constraints, not lower-grain projections.
    def clear_projection(selected):
        selected.fields = []
        selected.calcs = []
        selected.aggregations = []
        for child in selected.edges:
            clear_projection(child)

    for selected in result.edges:
        clear_projection(selected)
    result.fields = fields if not path else []
    result.calcs = []
    result.aggregations = []
    result.order_by = []
    result.distinct = True
    children = result.edges
    for step in path:
        selected = next((e for e in children if e.name == step), None)
        if selected is None:
            selected = IntentEdge(name=step)
            children.append(selected)
        selected.required = True
        children = selected.edges
    if path:
        selected.fields = fields
    return result
