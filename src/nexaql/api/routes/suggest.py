# Copyright (c) 2026-present NexaQL Contributors
"""POST /api/suggest -- server-side autocomplete."""

from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from nexaql.api.deps import get_ontology
from nexaql.engine.types import SuggestContext
from nexaql.engine.validator import get_suggestions

router = APIRouter()


class SuggestContextBody(BaseModel):
    type: Literal["node", "field", "filter", "directive"]
    node_name: Optional[str] = None
    partial: Optional[str] = None


class SuggestRequest(BaseModel):
    context: SuggestContextBody


class SuggestionItemOut(BaseModel):
    label: str
    kind: str
    insert_text: str
    detail: Optional[str] = None


class SuggestResponse(BaseModel):
    suggestions: list[SuggestionItemOut]


@router.post("/suggest")
async def suggest(body: SuggestRequest) -> SuggestResponse:
    ontology = get_ontology()
    ctx = SuggestContext(
        type=body.context.type,
        node_name=body.context.node_name,
        partial=body.context.partial,
    )
    items = get_suggestions(ontology, ctx)
    return SuggestResponse(
        suggestions=[
            SuggestionItemOut(
                label=item.label,
                kind=item.kind,
                insert_text=item.insert_text,
                detail=item.detail,
            )
            for item in items
        ]
    )
