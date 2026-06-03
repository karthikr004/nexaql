# Copyright (c) 2026-present NexaQL Contributors
"""POST /api/validate -- parse -> validate -> preview."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from nexaql.adapters import get_adapter
from nexaql.api.deps import get_config, get_ontology
from nexaql.api.middleware import get_user_context
from nexaql.engine.parser import ParseError, parse
from nexaql.engine.validator import validate
from nexaql.policy import enforce_access

router = APIRouter()


class ValidateRequest(BaseModel):
    query: str


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    queryPreview: str | None = None
    adapterType: str | None = None


@router.post("/validate")
async def validate_query(body: ValidateRequest, request: Request) -> ValidateResponse:
    if not body.query.strip():
        return ValidateResponse(
            valid=False,
            errors=["Query is empty"],
            warnings=[],
        )

    ontology = get_ontology()
    user = await get_user_context(request)

    try:
        ast = parse(body.query)
    except ParseError as e:
        return ValidateResponse(
            valid=False,
            errors=[str(e)],
            warnings=[],
            queryPreview=None,
            adapterType=None,
        )

    # Enforce access policies (returns deep copy with denied fields stripped)
    enforcement = enforce_access(ast, ontology, user)
    enforced_ast = enforcement.ast
    if enforcement.denied:
        return ValidateResponse(
            valid=False,
            errors=[enforcement.denied_reason or "Access denied"],
            warnings=enforcement.warnings,
            queryPreview=None,
            adapterType=None,
        )

    result = validate(enforced_ast, ontology)

    query_preview: str | None = None
    adapter_type: str | None = None

    if result.valid:
        try:
            # Resolve adapter for query preview
            root_node_name = enforced_ast.body.name
            node_def = ontology.nodes.get(root_node_name)
            ds_name = getattr(node_def, "datasource", None) if node_def else None
            cfg = get_config()
            if ds_name and cfg.datasources and ds_name in cfg.datasources:
                adapter = get_adapter(cfg.datasources[ds_name])
            elif cfg.datasources:
                adapter = get_adapter(next(iter(cfg.datasources.values())))
            else:
                adapter = None

            if adapter is not None:
                query_preview = adapter.describe(enforced_ast, ontology)
                adapter_type = adapter.adapter_type
        except Exception:
            pass  # swallow preview errors

    all_warnings = result.warnings + enforcement.warnings

    return ValidateResponse(
        valid=result.valid,
        errors=[err.message for err in result.errors],
        warnings=all_warnings,
        queryPreview=query_preview,
        adapterType=adapter_type,
    )
