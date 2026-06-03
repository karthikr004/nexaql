# Copyright (c) 2026-present NexaQL Contributors
"""NexaQL chat agent -- 3-step pipeline: generate -> execute -> summarize.

Uses the Anthropic SDK to drive Claude for query generation and result
summarization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import anthropic

from nexaql.adapters.base import AdapterResult, QueryAdapter
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


# ── Anthropic helpers ───────────────────────────────────────────────────────


def _make_client(llm_config: LLMConfig) -> anthropic.Anthropic:
    """Create an Anthropic client from config."""
    return anthropic.Anthropic(api_key=llm_config.api_key)


def _extract_text(response: Any) -> str:
    """Extract text content from an Anthropic message response."""
    parts = []
    for block in response.content:
        if block.type == "text":
            parts.append(block.text)
    return "".join(parts)


# ── Step 1: Generate query ──────────────────────────────────────────────────


async def generate_query(
    question: str,
    history: list[dict[str, str]],
    ontology: Ontology,
    llm_config: LLMConfig,
) -> tuple[str | None, str]:
    """Ask Claude to generate an NexaQL query from a natural-language question.

    Returns ``(query_text, explanation)`` where *query_text* may be ``None``
    if Claude could not produce a valid query block.
    """
    client = _make_client(llm_config)
    system_prompt = build_system_prompt(ontology)

    messages: list[dict[str, str]] = []
    for m in history:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": question})

    response = client.messages.create(
        model=llm_config.model,
        max_tokens=llm_config.max_tokens,
        system=system_prompt,
        messages=messages,  # type: ignore[arg-type]
    )

    response_text = _extract_text(response)
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
    """Execute a query, retrying once with Claude if it fails.

    Returns ``(result, error, final_query_text)``.
    """
    result, error = await _try_execute(query_text, ontology, adapter)
    if result is not None:
        return result, None, query_text

    # Retry: ask Claude to fix the query
    try:
        client = _make_client(llm_config)
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
                "Remember: filters use COLON syntax (field: value), NEVER equals (=). "
                "String values must be quoted. Please provide a corrected NexaQL query."
            ),
        })

        retry_response = client.messages.create(
            model=llm_config.model,
            max_tokens=llm_config.max_tokens,
            system=system_prompt,
            messages=retry_messages,  # type: ignore[arg-type]
        )

        retry_text = _extract_text(retry_response)
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
    """Ask Claude to produce a natural-language summary of query results."""
    client = _make_client(llm_config)

    prompt = build_summary_prompt(question, query, rows, columns, row_count)

    response = client.messages.create(
        model=llm_config.model,
        max_tokens=llm_config.summary_max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    return _extract_text(response)


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
