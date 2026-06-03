# Copyright (c) 2026-present NexaQL Contributors
"""GET /api/ontology -- return ontology summary for the UI."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from nexaql.api.deps import get_ontology
from nexaql.ontology import ontology_summary

router = APIRouter()


@router.get("/ontology")
async def ontology_endpoint() -> JSONResponse:
    try:
        ont = get_ontology()
        return JSONResponse(ontology_summary(ont))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
