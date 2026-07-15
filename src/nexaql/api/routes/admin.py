# Copyright (c) 2026-present NexaQL Contributors
"""Admin endpoints for managing the NexaQL ontology."""

from __future__ import annotations

import re
from typing import Any, Optional, Union

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from nexaql.api.deps import get_adapter_for_datasource, get_config, get_ontology, invalidate_ontology_cache
from nexaql.ontology.models import Ontology, OntologyNode
from nexaql.policy.context import CANONICAL_FIELDS
from nexaql.policy.enforcer import _PLACEHOLDER_RE

router = APIRouter(tags=["admin"])


async def _save_ontology_to_db(ontology: Ontology) -> None:
    """Save ontology to both the bootstrap DB and the active store.

    Per-table schema model: each node is stored in its own schema.
    Roles and access_functions are saved at the domain level.
    """
    import json as _json
    from nexaql import bootstrap as bs
    from nexaql.api.deps import _get_store_for_datasource

    domain = ontology.domain or bs.get_active_domain() or "default"

    # ── Update bootstrap DB (primary read path) ──────────────────────
    schemas = bs.list_schemas(domain)

    # Build node→schema mapping from existing per-table schemas
    node_schema_map: dict[str, dict] = {}
    for schema in schemas:
        try:
            ont_data = _json.loads(schema["ontology_json"]) if isinstance(schema["ontology_json"], str) else schema["ontology_json"]
        except (ValueError, TypeError):
            ont_data = {}
        for node_name in ont_data.get("nodes", {}):
            node_schema_map[node_name] = schema

    ont_dict = ontology.model_dump(exclude_none=True)
    all_nodes = ont_dict.get("nodes", {})
    top_level = {k: v for k, v in ont_dict.items() if k not in ("nodes", "roles", "access_functions")}

    # Save each node as its own per-table schema
    for node_name, node_def in all_nodes.items():
        src_schema = node_schema_map.get(node_name)
        connector_id = src_schema["connector_id"] if src_schema else None

        if connector_id is None and schemas:
            connector_id = schemas[0]["connector_id"]

        per_table_ont = {**top_level, "nodes": {node_name: node_def}}
        bs.save_schema(
            domain_name=domain,
            schema_name=node_name,
            connector_id=connector_id,
            ontology_json=per_table_ont,
        )

    # Save roles and access_functions at domain level
    roles = ont_dict.get("roles")
    access_functions = ont_dict.get("access_functions")
    if roles or access_functions:
        bs.save_domain_policies(
            domain_name=domain,
            roles=roles,
            access_functions=access_functions,
        )

    # ── Also save to the store (secondary path) ─────────────────────
    store = _get_store_for_datasource()
    await store.save(ontology, author="admin")
    invalidate_ontology_cache()


# ── GET /admin/ontology ────────────────────────────────────────────────────


@router.get("/admin/ontology")
async def get_full_ontology(domain: str | None = None) -> JSONResponse:
    """Return the full ontology from the bootstrap database only.

    If no bootstrap DB ontology exists, returns an empty ontology shell
    so the admin UI renders a clean slate.
    """
    from nexaql import bootstrap as bs
    from nexaql.api.deps import _try_bootstrap_ontology

    target_domain = domain or bs.get_active_domain() or "default"

    # Bootstrap DB only — no fallback to connected DBs or YAML
    ont = _try_bootstrap_ontology(target_domain)
    if ont:
        return JSONResponse({
            "ontology": ont.model_dump(exclude_none=True),
        })

    # No bootstrap ontology — return empty shell
    return JSONResponse({
        "ontology": {
            "version": "1.0",
            "domain": target_domain,
            "description": "",
            "nodes": {},
        },
    })


# ── GET /admin/roles ──────────────────────────────────────────────────────


@router.get("/admin/roles")
async def get_roles() -> JSONResponse:
    """Return the defined roles from the ontology."""
    try:
        ont = get_ontology()
        roles = {name: defn.model_dump() for name, defn in (ont.roles or {}).items()}
        return JSONResponse({"roles": roles})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── PUT /admin/ontology ────────────────────────────────────────────────────


def _format_validation_errors(exc: ValidationError) -> list[str]:
    """Convert Pydantic validation errors into human-readable messages."""
    messages = []
    for err in exc.errors():
        loc = " → ".join(str(p) for p in err["loc"])
        msg = err["msg"]
        messages.append(f"{loc}: {msg}")
    return messages


def _validate_roles(ontology: "Ontology") -> list[str]:
    """Check that all role references in the ontology are defined in the roles registry."""
    if not ontology.roles:
        return []  # No role registry — skip validation
    valid_roles = set(ontology.roles.keys())
    errors: list[str] = []
    for node_name, node_def in ontology.nodes.items():
        if node_def.visible_to:
            for r in node_def.visible_to:
                if r not in valid_roles:
                    errors.append(f"Node '{node_name}' → visible_to: unknown role '{r}'. Defined roles: {sorted(valid_roles)}")
        for fname, fdef in node_def.fields.items():
            if fdef.visible_to:
                for r in fdef.visible_to:
                    if r not in valid_roles:
                        errors.append(f"Node '{node_name}' → field '{fname}' → visible_to: unknown role '{r}'")
        for pi, pol in enumerate(node_def.row_policies or []):
            for r in pol.roles:
                if r != "*" and r not in valid_roles:
                    errors.append(f"Node '{node_name}' → row policy {pi + 1} → roles: unknown role '{r}'")
            for r in (pol.except_roles or []):
                if r not in valid_roles:
                    errors.append(f"Node '{node_name}' → row policy {pi + 1} → except_roles: unknown role '{r}'")
    return errors


@router.put("/admin/ontology")
async def replace_ontology(data: dict[str, Any]) -> JSONResponse:
    try:
        ontology = Ontology(**data)
    except ValidationError as e:
        errors = _format_validation_errors(e)
        return JSONResponse({
            "error": "Validation failed",
            "details": errors,
            "message": errors[0] if errors else str(e),
        }, status_code=400)

    # Validate role references
    role_errors = _validate_roles(ontology)
    if role_errors:
        return JSONResponse({
            "error": "Invalid role references",
            "details": role_errors,
            "message": role_errors[0],
        }, status_code=400)

    try:
        await _save_ontology_to_db(ontology)
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── PUT /admin/ontology/node/{node_name} ───────────────────────────────────


@router.put("/admin/ontology/node/{node_name}")
async def update_node(node_name: str, data: dict[str, Any]) -> JSONResponse:
    try:
        node = OntologyNode(**data)
    except ValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    try:
        ont = get_ontology()
        if node_name not in ont.nodes:
            return JSONResponse(
                {"error": f"Node '{node_name}' not found"},
                status_code=404,
            )
        ont.nodes[node_name] = node
        # Re-validate full ontology after mutation
        ontology = Ontology(**ont.model_dump())
        await _save_ontology_to_db(ontology)
        return JSONResponse({"success": True, "node": node_name})
    except ValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── POST /admin/ontology/node ─────────────────────────────────────────────


@router.post("/admin/ontology/node")
async def create_node(data: dict[str, Any]) -> JSONResponse:
    name = data.get("name")
    node_data = data.get("node")

    if not name or not node_data:
        return JSONResponse(
            {"error": "Request body must include 'name' (str) and 'node' (dict)"},
            status_code=400,
        )

    try:
        node = OntologyNode(**node_data)
    except ValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    try:
        ont = get_ontology()
        if name in ont.nodes:
            return JSONResponse(
                {"error": f"Node '{name}' already exists"},
                status_code=400,
            )
        ont.nodes[name] = node
        # Re-validate full ontology after mutation
        ontology = Ontology(**ont.model_dump())
        await _save_ontology_to_db(ontology)
        return JSONResponse({"success": True, "node": name})
    except ValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── DELETE /admin/ontology/node/{node_name} ────────────────────────────────


@router.delete("/admin/ontology/node/{node_name}")
async def delete_node(node_name: str) -> JSONResponse:
    try:
        ont = get_ontology()
        if node_name not in ont.nodes:
            return JSONResponse(
                {"error": f"Node '{node_name}' not found"},
                status_code=404,
            )
        del ont.nodes[node_name]
        await _save_ontology_to_db(ont)
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── POST /admin/ontology/node/{node_name}/regenerate ─────────────────────────


class RegenerateNodeRequest(BaseModel):
    domain: str | None = None
    """Domain to regenerate the node in (defaults to active domain)."""


@router.post("/admin/ontology/node/{node_name}/regenerate")
async def regenerate_node(node_name: str, req: RegenerateNodeRequest | None = None) -> JSONResponse:
    """Regenerate a single node by re-introspecting its source table.

    This fetches the latest column/FK info from the connected database
    and replaces the node definition in the ontology, preserving all other nodes.
    """
    import json as _json
    import traceback

    from nexaql import bootstrap as bs
    from nexaql.ontology.generator import OntologyGenerator

    domain = (req.domain if req else None) or bs.get_active_domain() or "default"

    # 1. Load existing ontology
    try:
        ont = get_ontology(domain)
    except Exception as e:
        return JSONResponse({"error": f"Cannot load ontology for domain '{domain}': {e}"}, status_code=404)

    if node_name not in ont.nodes:
        return JSONResponse({"error": f"Node '{node_name}' not found in domain '{domain}'"}, status_code=404)

    old_node = ont.nodes[node_name]
    table_name = old_node.table or node_name

    # 2. Find the connector for this domain
    schemas = bs.list_schemas(domain)
    if not schemas:
        return JSONResponse({"error": f"No schemas found for domain '{domain}'"}, status_code=404)

    connector = bs.get_connector_by_id(schemas[0]["connector_id"])
    if not connector or not connector.get("url"):
        return JSONResponse({"error": "No connector URL found for this domain"}, status_code=400)

    connection_url = connector["url"]

    # 3. Generate ontology for just this one table
    try:
        gen = OntologyGenerator(connection_url=connection_url)

        # Determine schema name (DuckDB uses 'main', PostgreSQL uses 'public')
        db_schema = "main" if gen._db_type == "duckdb" else "public"

        regenerated = await gen.generate(
            schema=db_schema,
            domain=domain,
            description=ont.description or "",
            include_tables=[table_name],
        )
    except Exception as e:
        return JSONResponse({
            "error": f"Regeneration failed for table '{table_name}': {e}",
            "details": traceback.format_exc().split("\n")[-3:],
        }, status_code=500)

    # 4. Find the regenerated node (may be named differently from the table)
    regen_nodes = regenerated.nodes
    if not regen_nodes:
        return JSONResponse({"error": f"Table '{table_name}' not found in database"}, status_code=404)

    # Pick the first (and only) regenerated node
    regen_node_name, regen_node = next(iter(regen_nodes.items()))

    # 5. Merge: replace only this node, preserve everything else
    #    Keep manually-set access controls, roles, etc. from old node
    #    but update fields and edges from the fresh introspection
    if old_node.visible_to and not regen_node.visible_to:
        regen_node.visible_to = old_node.visible_to
    if old_node.row_policies and not regen_node.row_policies:
        regen_node.row_policies = old_node.row_policies

    # Preserve PII/mask_with flags from old fields if the field still exists
    for fname, fdef in regen_node.fields.items():
        old_field = old_node.fields.get(fname)
        if old_field:
            if old_field.pii and not fdef.pii:
                fdef.pii = old_field.pii
            if old_field.mask_with and not fdef.mask_with:
                fdef.mask_with = old_field.mask_with
            if old_field.visible_to and not fdef.visible_to:
                fdef.visible_to = old_field.visible_to

    ont.nodes[node_name] = regen_node

    # 6. Save back to bootstrap DB
    try:
        ontology_dict = ont.model_dump(exclude_none=True)
        bs.save_schema(
            domain_name=domain,
            schema_name=schemas[0]["name"],
            connector_id=schemas[0]["connector_id"],
            ontology_json=ontology_dict,
        )
        invalidate_ontology_cache(domain)
    except Exception as e:
        return JSONResponse({"error": f"Failed to save: {e}"}, status_code=500)

    return JSONResponse({
        "success": True,
        "node": node_name,
        "table": table_name,
        "field_count": len(regen_node.fields),
        "edge_count": len(regen_node.edges) if regen_node.edges else 0,
    })


# ── POST /admin/validate-policy ──────────────────────────────────────────────


class _SampleUser(BaseModel):
    user_id: Union[str, int] = ""
    roles: list[str] = []
    name: Optional[str] = None
    email: Optional[str] = None
    manager_id: Optional[Union[str, int]] = None
    region: Optional[str] = None
    department: Optional[str] = None
    team_id: Optional[Union[str, int]] = None
    level: Optional[str] = None
    job_role: Optional[str] = None
    org_id: Optional[Union[str, int]] = None
    attributes: dict[str, Any] = {}


class _ValidatePolicyRequest(BaseModel):
    condition: str
    node_name: str
    sample_user: _SampleUser


@router.post("/admin/validate-policy")
async def validate_policy(req: _ValidatePolicyRequest) -> JSONResponse:
    """Validate a row-policy condition against the ontology and optionally
    test-execute it against the configured adapter.

    Returns *resolved_sql* with ``{user.xxx}`` placeholders filled in, flags
    for unresolved placeholders and unknown field references, and an optional
    *test_result* from a trial ``SELECT 1 ... LIMIT 1`` query.
    """
    ont = get_ontology()

    # 1. Check that the target node exists
    node_def = ont.nodes.get(req.node_name)
    if node_def is None:
        return JSONResponse(
            {"valid": False, "resolved_sql": req.condition,
             "error": f"Node '{req.node_name}' not found in ontology"},
            status_code=400,
        )

    # 2. Resolve {user.xxx} placeholders (check canonical fields first, then attributes)
    def _replacer(m: re.Match) -> str:
        key = m.group(1)
        if key in CANONICAL_FIELDS:
            val = getattr(req.sample_user, key, None)
        else:
            val = req.sample_user.attributes.get(key)
        if val is None:
            return ""
        if isinstance(val, (int, float)):
            return str(val)
        return str(val).replace("'", "''")

    resolved = _PLACEHOLDER_RE.sub(_replacer, req.condition)

    # 3. Check for unresolved placeholders (missing attributes)
    remaining = _PLACEHOLDER_RE.findall(resolved)
    if remaining:
        return JSONResponse({
            "valid": False,
            "resolved_sql": resolved,
            "error": f"Unresolved user attribute placeholders: {remaining}",
        })

    # 4. Validate field names referenced in condition exist on the node
    known_fields = set(node_def.fields.keys())
    # Simple heuristic: find bare identifiers that could be column names.
    # We look for word tokens that are not SQL keywords and not inside quotes.
    _SQL_KEYWORDS = {
        "select", "from", "where", "and", "or", "not", "in", "is", "null",
        "true", "false", "like", "between", "exists", "case", "when", "then",
        "else", "end", "as", "on", "join", "left", "right", "inner", "outer",
        "group", "order", "by", "having", "limit", "offset", "asc", "desc",
        "count", "sum", "avg", "min", "max", "distinct",
    }
    warnings: list[str] = []
    # Strip quoted strings before scanning for identifiers
    stripped = re.sub(r"'[^']*'", "", resolved)
    tokens = re.findall(r"\b([a-zA-Z_]\w*)\b", stripped)
    for tok in tokens:
        if tok.lower() in _SQL_KEYWORDS:
            continue
        # Tokens that look like table-qualified (appear after a dot) are fine
        if tok in known_fields:
            continue
        # Not a known field -- could be a table name, subquery alias, etc.
        # Only warn, don't fail.

    # 5. Try to test-execute against the adapter
    test_result: Optional[dict[str, Any]] = None
    table_name = getattr(node_def, "table", None) or req.node_name
    datasource_name = getattr(node_def, "datasource", None)
    try:
        adapter = get_adapter_for_datasource(datasource_name)
        conn = getattr(adapter, "_conn", None) or getattr(adapter, "conn", None)
        if conn is not None:
            test_sql = f"SELECT 1 FROM {table_name} WHERE {resolved} LIMIT 1"
            try:
                result = conn.execute(test_sql)
                rows = result.fetchall() if hasattr(result, "fetchall") else []
                test_result = {"success": True, "row_count": len(rows)}
            except Exception as exec_err:
                test_result = {"success": False, "error": str(exec_err)}
    except Exception:
        # Adapter not available -- skip test execution
        pass

    response: dict[str, Any] = {
        "valid": True,
        "resolved_sql": resolved,
    }
    if warnings:
        response["warnings"] = warnings
    if test_result is not None:
        response["test_result"] = test_result

    return JSONResponse(response)


# ── GET /admin/access-functions ──────────────────────────────────────────────


@router.get("/admin/access-functions")
async def list_access_functions() -> JSONResponse:
    """Return the named access functions defined in the ontology."""
    ont = get_ontology()
    funcs = ont.access_functions or {}
    return JSONResponse({
        "access_functions": {
            name: func.model_dump(exclude_none=True)
            for name, func in funcs.items()
        },
    })
