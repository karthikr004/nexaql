"""Prompt generation functions for NexaQL ontologies.

"""

from __future__ import annotations

from typing import Any

from .models import Ontology


# ── Helpers ──────────────────────────────────────────────────────────────────


def _filterable_ops(field_type: str) -> str:
    ops: dict[str, str] = {
        "string": 'field: "value"  field_like: "%pat%"  field_in: ["a","b"]  field_ne: "v"  field_null: true',
        "enum": 'field: "VALUE"  field_in: ["A","B"]  (use exact uppercase enum value)',
        "integer": "field: N  field_gt: N  field_gte: N  field_lt: N  field_lte: N  field_ne: N",
        "numeric": "field: N  field_gt: N  field_gte: N  field_lt: N  field_lte: N  field_ne: N",
        "date": 'field: "YYYY-MM-DD"  field_gt: "date"  field_gte: "date"  field_lt: "date"  field_lte: "date"',
        "boolean": "field: true  field: false",
    }
    return ops.get(field_type, "field: value")


def _resolve_ds_type(ontology: Ontology, ds_name: str | None) -> str:
    if ds_name and ontology.datasources:
        ds = ontology.datasources.get(ds_name)
        if ds:
            return ds.type
    return "postgresql"


# ── ontology_summary ─────────────────────────────────────────────────────────


def ontology_summary(ontology: Ontology) -> dict[str, Any]:
    """Return a JSON-friendly summary suitable for a UI schema explorer."""
    nodes_out: list[dict[str, Any]] = []

    for name, defn in ontology.nodes.items():
        ds_type = _resolve_ds_type(ontology, defn.datasource)

        fields = [
            {
                "name": fname,
                "type": fdef.type,
                "description": fdef.description,
                "filterable": fdef.filterable or False,
                **({"values": fdef.values} if fdef.values else {}),
                **({"visibleTo": fdef.visible_to} if fdef.visible_to else {}),
                **({"pii": fdef.pii} if fdef.pii else {}),
                **({"maskWith": fdef.mask_with} if fdef.mask_with else {}),
            }
            for fname, fdef in defn.fields.items()
        ]

        edges = [
            {
                "name": ename,
                "target": edef.node,
                "description": edef.description,
            }
            for ename, edef in (defn.edges or {}).items()
        ]

        special_filters = [
            {
                "name": sname,
                "description": sdef.description,
                **({"type": sdef.type} if sdef.type else {}),
            }
            for sname, sdef in (defn.special_filters or {}).items()
        ]

        table_display = defn.table or (
            f"REST {defn.endpoint}" if defn.endpoint else name
        )

        nodes_out.append(
            {
                "name": name,
                "description": defn.description,
                "table": table_display,
                "adapterType": ds_type,
                "fieldCount": len(defn.fields),
                "fields": fields,
                "edges": edges,
                "specialFilters": special_filters,
                **({"visibleTo": defn.visible_to} if defn.visible_to else {}),
            }
        )

    return {
        "domain": ontology.domain,
        "description": ontology.description,
        "nodes": nodes_out,
        "examples": _generate_examples(ontology),
        "nlQuestions": _generate_nl_questions(ontology),
    }


def _generate_examples(ontology: Ontology) -> list[dict[str, str]]:
    """Generate 3-5 example NexaQL queries based on the ontology's nodes/fields/edges."""
    examples: list[dict[str, str]] = []
    node_names = list(ontology.nodes.keys())
    if not node_names:
        return examples

    # Helper: pick up to N field names from a node
    def _pick_fields(node_name: str, max_fields: int = 4) -> list[str]:
        defn = ontology.nodes[node_name]
        return list(defn.fields.keys())[:max_fields]

    # Helper: find the first enum field with values for a given node
    def _first_enum(node_name: str) -> tuple[str, str] | None:
        defn = ontology.nodes[node_name]
        for fname, fdef in defn.fields.items():
            if fdef.values and len(fdef.values) >= 2:
                return fname, fdef.values[0]
        return None

    # Helper: find the first date field
    def _first_date(node_name: str) -> str | None:
        defn = ontology.nodes[node_name]
        for fname, fdef in defn.fields.items():
            if fdef.type in ("date", "datetime", "timestamp"):
                return fname
        return None

    # Helper: find the first numeric field
    def _first_numeric(node_name: str) -> str | None:
        defn = ontology.nodes[node_name]
        for fname, fdef in defn.fields.items():
            if fdef.type in ("numeric", "integer", "float", "decimal"):
                return fname
        return None

    # Helper: human-readable title from node name
    def _title(name: str) -> str:
        return name.replace("_", " ").title()

    # 1. Browse all records from the first node
    first = node_names[0]
    fields_str = "\n    ".join(_pick_fields(first, 5))
    examples.append({
        "name": f"All {_title(first)}",
        "query": (
            f"# Browse all {first}\n"
            f"query All{_title(first).replace(' ', '')} {{\n"
            f"  {first} @limit(50) {{\n"
            f"    {fields_str}\n"
            f"  }}\n"
            f"}}"
        ),
    })

    # 2. Filtered query using an enum field (find first node with an enum)
    for nname in node_names:
        enum_info = _first_enum(nname)
        if enum_info:
            fname, fval = enum_info
            fields_str = "\n    ".join(_pick_fields(nname, 4))
            examples.append({
                "name": f"{_title(nname)} by {_title(fname)}",
                "query": (
                    f"# Filter {nname} by {fname}\n"
                    f"query FilterBy{_title(fname).replace(' ', '')} {{\n"
                    f"  {nname}({fname}: \"{fval}\") {{\n"
                    f"    {fields_str}\n"
                    f"  }}\n"
                    f"}}"
                ),
            })
            break

    # 3. Aggregation query — find a node with a numeric field
    for nname in node_names:
        num_field = _first_numeric(nname)
        if num_field:
            examples.append({
                "name": f"{_title(nname)} Summary",
                "query": (
                    f"# Aggregate {num_field} across {nname}\n"
                    f"query {_title(nname).replace(' ', '')}Summary {{\n"
                    f"  {nname} {{\n"
                    f"    total: sum({num_field})\n"
                    f"    average: avg({num_field})\n"
                    f"    record_count: count()\n"
                    f"  }}\n"
                    f"}}"
                ),
            })
            break

    # 4. Query with edge traversal — find first node that has edges
    for nname in node_names:
        defn = ontology.nodes[nname]
        if defn.edges:
            edge_name = next(iter(defn.edges))
            edge_target = defn.edges[edge_name].node
            parent_fields = "\n    ".join(_pick_fields(nname, 3))
            child_fields = "\n      ".join(_pick_fields(edge_target, 3))
            examples.append({
                "name": f"{_title(nname)} + {_title(edge_name)}",
                "query": (
                    f"# {_title(nname)} with related {edge_name}\n"
                    f"query {_title(nname).replace(' ', '')}With{_title(edge_name).replace(' ', '')} {{\n"
                    f"  {nname} @limit(20) {{\n"
                    f"    {parent_fields}\n"
                    f"    {edge_name} {{\n"
                    f"      {child_fields}\n"
                    f"    }}\n"
                    f"  }}\n"
                    f"}}"
                ),
            })
            break

    # 5. Date-filtered query — if any node has a date field
    for nname in node_names:
        date_field = _first_date(nname)
        if date_field:
            fields_str = "\n    ".join(_pick_fields(nname, 4))
            examples.append({
                "name": f"Recent {_title(nname)}",
                "query": (
                    f"# Recent {nname} by {date_field}\n"
                    f"query Recent{_title(nname).replace(' ', '')} {{\n"
                    f"  {nname}({date_field}: {{ gte: \"2024-01-01\" }}) "
                    f"@orderby({date_field}, DESC) @limit(20) {{\n"
                    f"    {fields_str}\n"
                    f"  }}\n"
                    f"}}"
                ),
            })
            break

    return examples


def _generate_nl_questions(ontology: Ontology) -> list[str]:
    """Generate 4-6 domain-specific natural language questions for the Agent Chat.

    These are plain English questions a user might ask, derived from the
    ontology's nodes, fields, edges, and special filters.
    """
    questions: list[str] = []
    node_names = list(ontology.nodes.keys())
    if not node_names:
        return ["Show me all available data"]

    def _title(name: str) -> str:
        return name.replace("_", " ")

    def _first_date(node_name: str) -> str | None:
        defn = ontology.nodes[node_name]
        for fname, fdef in defn.fields.items():
            if fdef.type in ("date", "datetime", "timestamp"):
                return fname
        return None

    def _first_numeric(node_name: str) -> str | None:
        defn = ontology.nodes[node_name]
        for fname, fdef in defn.fields.items():
            if fdef.type in ("numeric", "integer", "float", "decimal"):
                return fname
        return None

    def _first_enum(node_name: str) -> tuple[str, list[str]] | None:
        defn = ontology.nodes[node_name]
        for fname, fdef in defn.fields.items():
            if fdef.values and len(fdef.values) >= 2:
                return fname, fdef.values
        return None

    # 1. Browse question for the primary node
    first = node_names[0]
    questions.append(f"Show me all {_title(first)}")

    # 2. Date-based question if any node has a date field
    for nname in node_names:
        date_field = _first_date(nname)
        if date_field:
            readable_date = _title(date_field)
            questions.append(
                f"Which {_title(nname)} were created in the last 30 days?"
                if "creat" in date_field.lower()
                else f"Show me {_title(nname)} from the last 30 days"
            )
            break

    # 3. Aggregation question if any node has a numeric field
    for nname in node_names:
        num_field = _first_numeric(nname)
        if num_field:
            readable = _title(num_field)
            questions.append(f"What is the total and average {readable} across all {_title(nname)}?")
            break

    # 4. Enum/status breakdown question
    for nname in node_names:
        enum_info = _first_enum(nname)
        if enum_info:
            fname, vals = enum_info
            questions.append(f"Show me {_title(nname)} grouped by {_title(fname)}")
            break

    # 5. Edge traversal question — find a relationship to ask about
    for nname in node_names:
        defn = ontology.nodes[nname]
        if defn.edges:
            edge_name = next(iter(defn.edges))
            edge_desc = defn.edges[edge_name].description or _title(edge_name)
            questions.append(f"Show me {_title(nname)} with their {_title(edge_name)}")
            break

    # 6. "Top N" question using a numeric field + different node if possible
    for nname in node_names:
        num_field = _first_numeric(nname)
        if num_field and len(questions) < 6:
            questions.append(f"What are the top 10 {_title(nname)} by {_title(num_field)}?")
            break

    return questions[:6]


# ── ontology_to_agent_prompt ─────────────────────────────────────────────────


def ontology_to_agent_prompt(ontology: Ontology) -> str:
    """Detailed prompt text intended for an LLM agent."""
    lines: list[str] = []

    for name, defn in ontology.nodes.items():
        ds_type = _resolve_ds_type(ontology, defn.datasource)

        lines.append(f"┌─ NODE: {name}  [{ds_type}]")
        lines.append(f"│  {defn.description}")
        lines.append("│")
        lines.append("│  SELECT fields (use in query body):")

        for fn, fd in defn.fields.items():
            enum_str = (
                f"  values: {' | '.join(fd.values)}" if fd.values else ""
            )
            derived_tag = "  ⟨derived⟩" if fd.derived else ""
            lines.append(
                f"│    {fn}  ({fd.type}){derived_tag}{enum_str}"
            )

        filterable = [
            (fn, fd)
            for fn, fd in defn.fields.items()
            if fd.filterable
        ]
        if filterable:
            lines.append("│")
            lines.append(
                "│  FILTERABLE fields (can appear in node(…) filter block):"
            )
            for fn, fd in filterable:
                joined = '", "'.join(fd.values) if fd.values else ""
                enum_str = (
                    f'  allowed values: "{joined}"'
                    if fd.values
                    else ""
                )
                ops = _filterable_ops(fd.type)
                lines.append(f"│    {fn}  ({fd.type}){enum_str}")
                lines.append(f"│       operators: {ops}")

        sfs = list((defn.special_filters or {}).items())
        if sfs:
            lines.append("│")
            lines.append(
                "│  SPECIAL filters (pre-defined conditions, use in filter block):"
            )
            for sn, sd in sfs:
                val_hint = (
                    "integer (e.g. 30)" if sd.type == "integer" else "true"
                )
                lines.append(
                    f"│    {sn}: {val_hint}   → {sd.description}"
                )

        edges = list((defn.edges or {}).items())
        if edges:
            lines.append("│")
            lines.append(
                "│  EDGES (traversals you can nest inside this node):"
            )
            for en, ed in edges:
                lines.append(
                    f"│    {en}  →  {ed.node}   ({ed.description})"
                )
            lines.append("│")
            lines.append(
                "│  CROSS-ENTITY calc() — use edge.field inside calc() for ad-hoc comparisons:"
            )
            lines.append(
                "│    calc(field - edge_name.field)  auto-joins the edge and compares values"
            )
            lines.append(
                "│    Example: calc(unit_price - contract_pricing_terms.agreed_unit_price)"
            )

        lines.append(f"└{'─' * 70}")
        lines.append("")

    return "\n".join(lines)


# ── ontology_to_prompt_text ──────────────────────────────────────────────────


def ontology_to_prompt_text(ontology: Ontology) -> str:
    """Compact prompt text intended for an LLM (saves tokens)."""
    lines: list[str] = []

    for name, defn in ontology.nodes.items():
        ds_type = _resolve_ds_type(ontology, defn.datasource)

        lines.append(f"Node: {name} [{ds_type}]")
        lines.append(f"  Description: {defn.description}")

        field_list = ", ".join(
            f"{fn}:{fd.type}{'⚡' if fd.filterable else ''}"
            for fn, fd in defn.fields.items()
        )
        lines.append(f"  Fields: {field_list}")

        edge_list = ", ".join(
            f"{en}→{ed.node}" for en, ed in (defn.edges or {}).items()
        )
        if edge_list:
            lines.append(f"  Edges: {edge_list}")

        sf_list = ", ".join(
            f"{sn}{':N' if sd.type == 'integer' else ''}"
            for sn, sd in (defn.special_filters or {}).items()
        )
        if sf_list:
            lines.append(f"  Special filters: {sf_list}")

        lines.append("")

    return "\n".join(lines)
