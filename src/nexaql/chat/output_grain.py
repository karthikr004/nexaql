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

    # Remove lower-grain detail columns, retaining measures that aggregate into
    # the selected entity. Dropping these measures silently changes the request.
    def clear_detail_projection(selected):
        selected.fields = []
        selected.calcs = []
        for child in selected.edges:
            clear_detail_projection(child)

    if not path:
        # The requested entity already owns the result. Its calculated measures
        # and descendant aggregates are outputs, not lower-grain detail rows.
        result.fields = list(dict.fromkeys([*fields, *result.fields]))
        for selected in result.edges:
            clear_detail_projection(selected)
        result.distinct = True
        return result

    for selected in result.edges:
        clear_detail_projection(selected)
    result.fields = fields if not path else []
    result.calcs = []
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
