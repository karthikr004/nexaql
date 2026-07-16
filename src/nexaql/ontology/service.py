# Copyright (c) 2026-present NexaQL Contributors
"""Shared schema generation / regeneration logic.

Used by the REST API, CLI, and MCP server to avoid duplicating the
per-table-schema save + edge-discovery post-processing flow.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from nexaql import bootstrap as bs
from nexaql.ontology.generator import ForeignKey, OntologyGenerator, discover_edges

logger = logging.getLogger(__name__)


async def generate_schemas(
    connector_name: str,
    domain: str,
    include_tables: list[str] | None = None,
    exclude_tables: list[str] | None = None,
    schema_name: str = "public",
    description: str = "",
    detect_enums: bool = True,
    detect_pii: bool = True,
    replace: bool = True,
) -> dict[str, Any]:
    """Generate per-table schemas from a saved connector and save to bootstrap DB.

    Returns a summary dict with status, node info, and edge counts.
    """
    connector = bs.get_connector(connector_name)
    if connector is None:
        return {"error": f"Connector '{connector_name}' not found"}

    connection_url = connector["url"]
    connector_id = connector["id"]

    try:
        gen = OntologyGenerator(connection_url=connection_url)
    except ValueError as e:
        return {"error": str(e)}

    # DuckDB uses 'main' as default schema
    gen_schema = schema_name
    if gen._db_type == "duckdb" and gen_schema == "public":
        gen_schema = "main"

    desc = description or f"Auto-generated from {gen._db_type} database"

    try:
        ontology = await gen.generate(
            schema=gen_schema,
            domain=domain,
            description=desc,
            include_tables=include_tables,
            exclude_tables=exclude_tables,
            detect_enums=detect_enums,
            detect_pii=detect_pii,
        )
    except ImportError as e:
        return {"error": f"Missing database driver: {e}"}
    except Exception as e:
        return {
            "error": f"Ontology generation failed: {e}",
            "details": traceback.format_exc().split("\n")[-3:],
        }

    # Patch datasource URL
    if ontology.datasources and "default" in ontology.datasources:
        ds = ontology.datasources["default"]
        if hasattr(ds, "url"):
            ds.url = connection_url
        elif hasattr(ds, "path"):
            ds.path = connection_url

    # Save per-table schemas to bootstrap DB
    ontology_dict = ontology.model_dump(exclude_none=True)
    all_nodes = ontology_dict.get("nodes", {})
    top_level = {k: v for k, v in ontology_dict.items() if k != "nodes"}

    # Extract or bootstrap roles and access_functions at domain level
    roles = ontology_dict.get("roles")
    access_functions = ontology_dict.get("access_functions")

    if not roles:
        roles = {
            "admin": {"description": "Full access to all data"},
            "analyst": {"description": "Read-only access for reporting and analytics"},
            "manager": {"description": "Access scoped to their department or region"},
        }
    if not access_functions:
        access_functions = {
            "owns_record": {
                "description": "User owns the record (created_by or user_id matches)",
                "sql": "{field} = {user.id}",
                "requires": ["id"],
            },
            "same_department": {
                "description": "User belongs to the same department",
                "sql": "{field} = {user.department}",
                "requires": ["department"],
            },
            "same_region": {
                "description": "User is in the same region",
                "sql": "{field} = {user.region}",
                "requires": ["region"],
            },
        }

    for node_name, node_def in all_nodes.items():
        if not replace:
            existing = bs.get_schema(domain, node_name)
            if existing:
                continue

        node_def["datasource"] = connector_name

        per_table_ont = {**top_level, "nodes": {node_name: node_def}}
        per_table_ont.pop("roles", None)
        per_table_ont.pop("access_functions", None)

        bs.save_schema(
            domain_name=domain,
            schema_name=node_name,
            connector_id=connector_id,
            ontology_json=per_table_ont,
        )

    bs.save_domain_policies(
        domain_name=domain,
        roles=roles,
        access_functions=access_functions,
    )

    # Update domain description
    dom = bs.get_domain(domain)
    if dom:
        bs._get_conn().execute(
            "UPDATE domains SET description = ? WHERE name = ?",
            [desc, domain],
        )

    bs.set_active_domain(domain)

    # Edge discovery post-processing
    ontology = await _run_edge_discovery(domain, list(all_nodes.keys()), connector_id, top_level)

    # Build summary
    node_summary = {}
    for name, node in ontology.nodes.items():
        node_summary[name] = {
            "table": node.table or name,
            "field_count": len(node.fields),
            "edge_count": len(node.edges) if node.edges else 0,
            "fields": list(node.fields.keys()),
            "edges": list(node.edges.keys()) if node.edges else [],
        }

    return {
        "status": "generated",
        "domain": domain,
        "db_type": gen._db_type,
        "connector_name": connector_name,
        "connector_id": connector_id,
        "nodes": node_summary,
        "node_count": len(ontology.nodes),
        "total_fields": sum(len(n.fields) for n in ontology.nodes.values()),
        "total_edges": sum(len(n.edges) for n in ontology.nodes.values() if n.edges),
    }


async def regenerate_schema(
    node_name: str,
    domain: str,
) -> dict[str, Any]:
    """Regenerate a single schema/node within a domain.

    Looks up the connector from the existing schema, re-introspects just that
    table, saves the updated schema, and re-runs edge discovery.
    """
    schema = bs.get_schema(domain, node_name)
    if schema is None:
        return {"error": f"Schema '{node_name}' not found in domain '{domain}'"}

    connector_id = schema["connector_id"]
    connector = bs.get_connector_by_id(connector_id)
    if connector is None:
        return {"error": f"Connector (id={connector_id}) for schema '{node_name}' not found"}

    connection_url = connector["url"]

    # Figure out the actual table name from the existing ontology
    import json
    existing_ont = json.loads(schema.get("ontology_json", "{}"))
    existing_node = existing_ont.get("nodes", {}).get(node_name, {})
    table_name = existing_node.get("table", node_name)

    try:
        gen = OntologyGenerator(connection_url=connection_url)
    except ValueError as e:
        return {"error": str(e)}

    gen_schema = "main" if gen._db_type == "duckdb" else "public"

    try:
        ontology = await gen.generate(
            schema=gen_schema,
            domain=domain,
            description=existing_ont.get("description", ""),
            include_tables=[table_name],
        )
    except Exception as e:
        return {
            "error": f"Regeneration failed: {e}",
            "details": traceback.format_exc().split("\n")[-3:],
        }

    ontology_dict = ontology.model_dump(exclude_none=True)
    all_nodes = ontology_dict.get("nodes", {})
    top_level = {k: v for k, v in ontology_dict.items() if k != "nodes"}

    # Save the regenerated node
    for regen_name, node_def in all_nodes.items():
        node_def["datasource"] = connector["name"]
        per_table_ont = {**top_level, "nodes": {regen_name: node_def}}
        per_table_ont.pop("roles", None)
        per_table_ont.pop("access_functions", None)
        bs.save_schema(
            domain_name=domain,
            schema_name=regen_name,
            connector_id=connector_id,
            ontology_json=per_table_ont,
        )

    # Edge discovery post-processing
    domain_ont = await _run_edge_discovery(domain, list(all_nodes.keys()), connector_id, top_level)

    regen_node = domain_ont.nodes.get(node_name)
    return {
        "status": "regenerated",
        "domain": domain,
        "node": node_name,
        "table": regen_node.table if regen_node else table_name,
        "field_count": len(regen_node.fields) if regen_node else 0,
        "edge_count": len(regen_node.edges) if regen_node and regen_node.edges else 0,
        "fields": list(regen_node.fields.keys()) if regen_node else [],
        "edges": list(regen_node.edges.keys()) if regen_node and regen_node.edges else [],
    }


async def _run_edge_discovery(
    domain: str,
    node_names: list[str],
    fallback_connector_id: int,
    top_level: dict[str, Any],
) -> Any:
    """Load domain ontology, collect FKs, run discover_edges for given nodes, re-save."""
    from nexaql.api.deps import _try_bootstrap_ontology

    domain_ont = _try_bootstrap_ontology(domain)
    if not domain_ont or not domain_ont.nodes:
        return domain_ont

    # Collect FKs from all connectors in this domain
    all_fks: list[ForeignKey] = []
    seen_connector_ids: set[int] = set()
    domain_schemas = bs.list_schemas(domain)
    for s in domain_schemas:
        cid = s["connector_id"]
        if cid in seen_connector_ids:
            continue
        seen_connector_ids.add(cid)
        c = bs.get_connector_by_id(cid)
        if not c or not c.get("url"):
            continue
        try:
            fk_gen = OntologyGenerator(connection_url=c["url"])
            fk_schema = "main" if fk_gen._db_type == "duckdb" else "public"
            _, fks = await fk_gen.introspect(schema=fk_schema)
            all_fks.extend(fks)
        except Exception:
            pass

    # Run edge discovery for each target node
    modified_set: set[str] = set()
    for node_name in node_names:
        if node_name in domain_ont.nodes:
            modified = discover_edges(node_name, domain_ont.nodes, all_fks)
            modified_set.update(modified)

    # Re-save modified nodes with updated edges
    for mod_name in modified_set:
        if mod_name not in domain_ont.nodes:
            continue
        mod_node = domain_ont.nodes[mod_name]
        mod_dict = mod_node.model_dump(exclude_none=True)
        mod_schema = bs.get_schema(domain, mod_name)
        mod_connector_id = mod_schema["connector_id"] if mod_schema else fallback_connector_id
        per_table_ont = {**top_level, "nodes": {mod_name: mod_dict}}
        per_table_ont.pop("roles", None)
        per_table_ont.pop("access_functions", None)
        bs.save_schema(
            domain_name=domain,
            schema_name=mod_name,
            connector_id=mod_connector_id,
            ontology_json=per_table_ont,
        )

    return domain_ont
