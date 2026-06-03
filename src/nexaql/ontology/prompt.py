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
    }


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
