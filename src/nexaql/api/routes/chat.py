# Copyright (c) 2026-present NexaQL Contributors
"""POST /api/chat -- NL -> NexaQL -> execute -> summarize pipeline."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from nexaql import bootstrap as bs
from nexaql.adapters import get_adapter
from nexaql.api.deps import get_config, get_ontology
from nexaql.api.middleware import get_user_context
from nexaql.chat.agent import ChatResponse, ask

router = APIRouter()


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatMessage] = []
    thread_id: int | None = None


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
    # Pipeline trace fields for debugging
    intent: dict[str, Any] | None = None
    generationMode: str | None = None
    # Thread context
    threadId: int | None = None


@router.post("/chat")
async def chat_endpoint(body: ChatRequest, request: Request) -> ChatResponseBody:
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")

    cfg = get_config()

    # Check LLM is configured
    if not cfg.llm.provider or not cfg.llm.model:
        return ChatResponseBody(
            error=(
                "LLM not configured. Add an API key in the Admin panel (it will auto-configure the provider), "
                "or set 'provider' and 'model' in nexaql.yaml. Supported providers: ollama, openrouter, openai, anthropic, meta."
            ),
        )

    # Cloud providers (openrouter, openai, anthropic) require an API key; Ollama (local) does not
    if cfg.llm.provider.lower() != "ollama" and not cfg.llm.api_key:
        saved_key = bs.get_api_key(cfg.llm.provider)
        if saved_key:
            cfg.llm.api_key = saved_key
        else:
            return ChatResponseBody(
                error=(
                    f"Agent Chat with provider '{cfg.llm.provider}' requires an API key. "
                    "Add one in the Admin panel under API Keys, or switch to Ollama (local, no key needed)."
                ),
            )

    ontology = get_ontology()
    user = await get_user_context(request)

    # Auto-create thread if not provided
    thread_id = body.thread_id
    if thread_id is None:
        user_id = int(user.user_id) if user.user_id != "anonymous" else None
        if user_id:
            thread = bs.create_thread(user_id, domain=getattr(ontology, "domain", None))
            thread_id = thread["id"]

    # Persist user message
    if thread_id:
        bs.add_message(thread_id, "user", body.question)

    # Resolve the default adapter
    try:
        if cfg.datasources:
            adapter = get_adapter(next(iter(cfg.datasources.values())))
        else:
            adapter = None
    except Exception:
        adapter = None

    # Build history from thread if available, otherwise use provided history
    if thread_id and not body.history:
        stored = bs.get_messages(thread_id, limit=100)
        history = [{"role": m["role"], "content": m["content"]} for m in stored[:-1]]
    else:
        history = [{"role": m.role, "content": m.content} for m in body.history]

    # Lookup relevant business ontology entries for this question
    business_context: list[dict] = []
    domain_name = getattr(ontology, "domain", None)
    if domain_name:
        domain_record = bs.get_domain(domain_name)
        if domain_record:
            business_context = bs.lookup_business_ontology(domain_record["id"], body.question)

    try:
        result: ChatResponse = await ask(
            question=body.question,
            history=history,
            ontology=ontology,
            adapter=adapter,
            llm_config=cfg.llm,
            user=user,
            business_context=business_context or None,
        )
    except Exception as e:
        return ChatResponseBody(error=str(e), threadId=thread_id)

    # Persist assistant response
    if thread_id:
        metadata = {
            "nexaql_query": result.nexaql_query,
            "query_preview": result.query_preview,
            "adapter_type": result.adapter_type,
            "row_count": result.row_count,
            "generation_mode": result.generation_mode,
        }
        if result.error:
            metadata["error"] = result.error
        bs.add_message(thread_id, "assistant", result.summary or result.error or "", metadata)

        # Auto-title: set thread title from first question
        thread = bs.get_thread(thread_id, int(user.user_id))
        if thread and not thread.get("title"):
            title = body.question[:80]
            bs.update_thread(thread_id, int(user.user_id), title=title)

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
        intent=result.intent,
        generationMode=result.generation_mode,
        threadId=thread_id,
    )
