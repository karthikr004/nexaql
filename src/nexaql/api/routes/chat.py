# Copyright (c) 2026-present NexaQL Contributors
"""POST /api/chat -- NL -> NexaQL -> execute -> summarize pipeline."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nexaql.adapters import get_adapter
from nexaql.api.deps import get_config, get_ontology
from nexaql.chat.agent import ChatResponse, ask

router = APIRouter()


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatMessage] = []


class ChatResponseBody(BaseModel):
    explanation: str | None = None
    nexaqlQuery: str | None = None
    queryPreview: str | None = None
    adapterType: str | None = None
    rows: list[dict[str, Any]] = []
    columns: list[dict[str, str]] = []
    rowCount: int = 0
    shape: Any | None = None
    summary: str | None = None
    error: str | None = None


@router.post("/chat")
async def chat_endpoint(body: ChatRequest) -> ChatResponseBody:
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")

    cfg = get_config()

    # Check LLM is configured
    if not cfg.llm.provider or not cfg.llm.model:
        return ChatResponseBody(
            error=(
                "LLM not configured. Set 'provider' and 'model' in nexaql.yaml "
                "or configure via the Admin panel. Supported providers: ollama, openrouter, openai."
            ),
        )

    # Cloud providers (openrouter, openai) require an API key; Ollama (local) does not
    if cfg.llm.provider.lower() != "ollama" and not cfg.llm.api_key:
        return ChatResponseBody(
            error=(
                f"Agent Chat with provider '{cfg.llm.provider}' requires an API key. "
                "Add one in the Admin panel under API Keys, or switch to Ollama (local, no key needed)."
            ),
        )

    ontology = get_ontology()

    # Resolve the default adapter
    try:
        if cfg.datasources:
            adapter = get_adapter(next(iter(cfg.datasources.values())))
        else:
            adapter = None
    except Exception:
        adapter = None

    history = [{"role": m.role, "content": m.content} for m in body.history]

    try:
        result: ChatResponse = await ask(
            question=body.question,
            history=history,
            ontology=ontology,
            adapter=adapter,
            llm_config=cfg.llm,
        )
    except Exception as e:
        return ChatResponseBody(error=str(e))

    return ChatResponseBody(
        explanation=result.explanation,
        nexaqlQuery=result.nexaql_query,
        queryPreview=result.query_preview,
        adapterType=result.adapter_type,
        rows=result.rows,
        columns=[{"name": c.name, "type": c.type} for c in result.columns] if result.columns else [],
        rowCount=result.row_count,
        shape=result.shape,
        summary=result.summary,
        error=result.error,
    )
