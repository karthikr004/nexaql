# Copyright (c) 2026-present NexaQL Contributors
"""NexaQL chat agent -- 3-step pipeline: generate -> execute -> summarize.

Provider-agnostic: uses the unified LLM layer (chat/llm.py) which routes to
Ollama (local), OpenRouter (cloud), or any OpenAI-compatible endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from nexaql.adapters.base import AdapterResult, QueryAdapter
from nexaql.chat.llm import chat_completion
from nexaql.chat.prompts import (
    build_summary_prompt,
    build_system_prompt,
    extract_nexaql_query,
)
from nexaql.config import LLMConfig
from nexaql.engine.parser import ParseError, parse
from nexaql.engine.types import ColumnMeta, NodeShape
from nexaql.engine.validator import validate
from nexaql.ontology import Ontology


# ── Response types ──────────────────────────────────────────────────────────


@dataclass
class ChatResponse:
    explanation: str | None = None
    nexaql_query: str | None = None
    query_preview: str | None = None
    adapter_type: str | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)
    columns: list[ColumnMeta] = field(default_factory=list)
    row_count: int = 0
    shape: NodeShape | None = None
    summary: str | None = None
    error: str | None = None


# ── Step 1: Generate query ──────────────────────────────────────────────────


async def generate_query(
    question: str,
    history: list[dict[str, str]],
    ontology: Ontology,
    llm_config: LLMConfig,
) -> tuple[str | None, str]:
    """Generate a NexaQL query from a natural-language question.

    Returns ``(query_text, explanation)`` where *query_text* may be ``None``
    if the LLM could not produce a valid query block.
    """
    system_prompt = build_system_prompt(ontology)

    messages: list[dict[str, str]] = []
    for m in history:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": question})

    response_text = chat_completion(
        llm_config,
        system=system_prompt,
        messages=messages,
        max_tokens=llm_config.max_tokens,
    )

    query_text = extract_nexaql_query(response_text)
    return query_text, response_text


# ── Step 2: Execute with retry ──────────────────────────────────────────────


async def _try_execute(
    query_text: str,
    ontology: Ontology,
    adapter: QueryAdapter,
) -> tuple[AdapterResult | None, str | None]:
    """Parse, validate, and execute a query. Returns ``(result, error)``."""
    try:
        ast = parse(query_text)
    except ParseError as e:
        return None, f"Parse error: {e}"

    validation = validate(ast, ontology)
    if not validation.valid:
        error_msgs = "; ".join(err.message for err in validation.errors)
        return None, f"Validation failed: {error_msgs}"

    try:
        result = await adapter.execute(ast, ontology)
        return result, None
    except Exception as e:
        return None, str(e)


async def execute_with_retry(
    query_text: str,
    ontology: Ontology,
    adapter: QueryAdapter,
    llm_config: LLMConfig,
    history: list[dict[str, str]],
    question: str,
    explanation: str,
) -> tuple[AdapterResult | None, str | None, str]:
    """Execute a query, retrying once with the LLM if it fails.

    Returns ``(result, error, final_query_text)``.
    """
    result, error = await _try_execute(query_text, ontology, adapter)
    if result is not None:
        return result, None, query_text

    # Retry: ask LLM to fix the query
    try:
        system_prompt = build_system_prompt(ontology)

        retry_messages: list[dict[str, str]] = []
        for m in history:
            retry_messages.append({"role": m["role"], "content": m["content"]})
        retry_messages.append({"role": "user", "content": question})
        retry_messages.append({"role": "assistant", "content": explanation})
        retry_messages.append({
            "role": "user",
            "content": (
                f"The query you generated failed with this error:\n\n{error}\n\n"
                "Common mistakes to fix:\n"
                "- NEVER use dot notation (node.field). Use edges instead: edge_name {{ field }}\n"
                "- Filters use COLON syntax (field: value), NEVER equals (=)\n"
                "- Aggregation arguments are BARE field names: sum(amount), NOT sum(node.amount)\n"
                "- String values must be double-quoted\n"
                "Please provide a corrected NexaQL query."
            ),
        })

        retry_text = chat_completion(
            llm_config,
            system=system_prompt,
            messages=retry_messages,
            max_tokens=llm_config.max_tokens,
        )

        retry_query = extract_nexaql_query(retry_text)

        if retry_query:
            result2, error2 = await _try_execute(retry_query, ontology, adapter)
            if result2 is not None:
                return result2, None, retry_query
            return None, error2, retry_query
    except Exception:
        pass  # keep original error

    return None, error, query_text


# ── Step 3: Summarize results ───────────────────────────────────────────────


async def summarize_results(
    question: str,
    query: str,
    rows: list[dict[str, Any]],
    columns: list[ColumnMeta],
    row_count: int,
    llm_config: LLMConfig,
) -> str:
    """Produce a natural-language summary of query results."""
    prompt = build_summary_prompt(question, query, rows, columns, row_count)

    return chat_completion(
        llm_config,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=llm_config.summary_max_tokens,
    )


# ── Full pipeline ───────────────────────────────────────────────────────────


async def ask(
    question: str,
    history: list[dict[str, str]],
    ontology: Ontology,
    adapter: QueryAdapter | None,
    llm_config: LLMConfig,
) -> ChatResponse:
    """Run the full chat pipeline: generate -> execute -> summarize.

    Parameters
    ----------
    question:
        The natural-language question from the user.
    history:
        Previous chat messages (list of ``{"role": ..., "content": ...}``).
    ontology:
        The loaded ontology definition.
    adapter:
        The query adapter for execution (may be ``None`` if no datasource).
    llm_config:
        LLM configuration (model, API key, token limits).

    Returns
    -------
    ChatResponse
        The complete response including query, results, and summary.
    """
    # Step 1: Generate query
    query_text, explanation = await generate_query(
        question, history, ontology, llm_config
    )

    if query_text is None:
        return ChatResponse(
            explanation=explanation,
            nexaql_query=None,
            summary=explanation,
        )

    # Step 2: Execute (with retry)
    if adapter is None:
        return ChatResponse(
            explanation=explanation,
            nexaql_query=query_text,
            summary=explanation,
            error="No datasource configured -- cannot execute query",
        )

    exec_result, exec_error, final_query = await execute_with_retry(
        query_text=query_text,
        ontology=ontology,
        adapter=adapter,
        llm_config=llm_config,
        history=history,
        question=question,
        explanation=explanation,
    )

    # Step 3: Summarize
    summary = explanation
    if exec_result is not None and exec_error is None:
        try:
            summary = await summarize_results(
                question=question,
                query=final_query,
                rows=exec_result.rows,
                columns=exec_result.columns,
                row_count=exec_result.row_count,
                llm_config=llm_config,
            )
        except Exception:
            pass  # fall through to explanation text

    return ChatResponse(
        explanation=explanation,
        nexaql_query=final_query,
        query_preview=exec_result.query_preview if exec_result else None,
        adapter_type=exec_result.adapter_type if exec_result else None,
        rows=exec_result.rows if exec_result else [],
        columns=exec_result.columns if exec_result else [],
        row_count=exec_result.row_count if exec_result else 0,
        shape=exec_result.shape if exec_result else None,
        summary=summary,
        error=exec_error,
    )
