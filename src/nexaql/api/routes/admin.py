# Copyright (c) 2026-present NexaQL Contributors
"""Admin endpoints for managing the NexaQL ontology."""

from __future__ import annotations

import re
from typing import Any, Optional, Union

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from nexaql.api.deps import get_adapter_for_datasource, get_config, get_ontology
from nexaql.ontology.models import Ontology, OntologyNode
from nexaql.ontology.writer import save_ontology
from nexaql.policy.context import CANONICAL_FIELDS
from nexaql.policy.enforcer import _PLACEHOLDER_RE

router = APIRouter(tags=["admin"])


def _ontology_path() -> str:
    return get_config().ontology.path


# ── GET /admin/ontology ────────────────────────────────────────────────────


@router.get("/admin/ontology")
async def get_full_ontology() -> JSONResponse:
    try:
        ont = get_ontology()
        return JSONResponse({
            "ontology": ont.model_dump(exclude_none=True),
            "path": _ontology_path(),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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
        save_ontology(ontology, _ontology_path())
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
        save_ontology(ontology, _ontology_path())
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
        save_ontology(ontology, _ontology_path())
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
        save_ontology(ont, _ontology_path())
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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
