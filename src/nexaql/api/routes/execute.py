# Copyright (c) 2026-present NexaQL Contributors
"""POST /api/execute -- parse -> validate -> translate -> execute pipeline."""

from __future__ import annotations

import dataclasses
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from nexaql.api.deps import get_adapter_for_datasource, get_config, get_ontology
from nexaql.api.middleware import get_user_context
from nexaql.engine.parser import ParseError, parse
from nexaql.engine.validator import validate
from nexaql.policy import enforce_access, mask_results

router = APIRouter()


class ExecuteRequest(BaseModel):
    query: str


class ExecuteResponse(BaseModel):
    queryPreview: str | None = None
    adapterType: str | None = None
    shape: Any | None = None
    rows: list[dict[str, Any]] = []
    rowCount: int = 0
    columns: list[dict[str, str]] = []
    durationMs: float = 0
    warnings: list[str] = []
    error: str | None = None


@router.post("/execute")
async def execute_query(body: ExecuteRequest, request: Request) -> ExecuteResponse:
    query_preview: str | None = None

    if not body.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")

    ontology = get_ontology()
    user = await get_user_context(request)
    t0 = time.time()

    # Parse
    try:
        ast = parse(body.query)
    except ParseError as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {e}") from e

    # Enforce access policies (returns a deep copy of the AST)
    enforcement = enforce_access(ast, ontology, user)
    enforced_ast = enforcement.ast
    if enforcement.denied:
        raise HTTPException(
            status_code=403,
            detail={"error": "Access denied", "reason": enforcement.denied_reason},
        )

    # Validate the enforced AST
    validation = validate(enforced_ast, ontology)
    if not validation.valid:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Validation failed",
                "details": [{"message": err.message} for err in validation.errors],
                "warnings": validation.warnings,
            },
        )

    # Execute
    try:
        root_node_name = enforced_ast.body.name
        node_def = ontology.nodes.get(root_node_name)
        ds_name = getattr(node_def, "datasource", None) if node_def else None
        adapter = get_adapter_for_datasource(ds_name)

        result = await adapter.execute(enforced_ast, ontology)
        query_preview = result.query_preview
    except Exception as e:
        return ExecuteResponse(
            queryPreview=query_preview,
            error=f"Execution error: {e}",
        )

    duration_ms = (time.time() - t0) * 1000

    # Convert NodeShape dataclass to dict with camelCase keys for frontend
    def _shape_to_dict(shape) -> dict:
        return {
            "edgeName": shape.edge_name,
            "node": shape.node,
            "columnAliases": list(shape.column_aliases),
            "aggregationAliases": list(shape.aggregation_aliases),
            "children": [_shape_to_dict(c) for c in shape.children],
        }

    shape_dict = _shape_to_dict(result.shape) if result.shape else None

    # Apply PII masking if the enforcer flagged any fields
    rows = result.rows
    if enforcement.masked_fields:
        rows = mask_results(rows, enforcement.masked_fields)

    all_warnings = validation.warnings + enforcement.warnings

    return ExecuteResponse(
        queryPreview=result.query_preview,
        adapterType=result.adapter_type,
        shape=shape_dict,
        rows=rows,
        rowCount=result.row_count,
        columns=[{"name": c.name, "type": c.type} for c in result.columns],
        durationMs=duration_ms,
        warnings=all_warnings,
    )
