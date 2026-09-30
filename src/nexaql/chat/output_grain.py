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

    # Preserve the selected entity and its to-one display relationships. Those
    # fields do not change the output grain (e.g. an order number for each line).
    from nexaql.chat.analytical_intent import to_one_target

    def project_edges(owner, edges, remaining):
        for selected in edges:
            edge_def = (owner.edges or {}).get(selected.name)
            if not edge_def:
                raise ValueError(f"Unknown relationship {selected.name}")
            child = ontology.nodes[edge_def.node]
            if remaining:
                if selected.name == remaining[0]:
                    if len(remaining) > 1:
                        selected.fields = []
                        selected.calcs = []
                    project_edges(child, selected.edges, remaining[1:])
                else:
                    clear_detail_projection(selected)
            else:
                # Only retain fields functionally dependent on the output key.
                try:
                    to_one_target(owner, selected.name, ontology)
                except ValueError:
                    clear_detail_projection(selected)
                else:
                    project_edges(child, selected.edges, [])

    project_edges(ontology.nodes[intent.node], result.edges, path)
    result.fields = fields if not path else []
    comparison = result.cumulative_comparison or {}
    comparison_aliases = {comparison.get("total_alias"), comparison.get("excess_alias")} - {None}
    result.calcs = [calc for calc in result.calcs if calc.alias in comparison_aliases]
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
        selected.fields = list(dict.fromkeys([*fields, *selected.fields]))
    return result
