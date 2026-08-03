# Copyright (c) 2026-present NexaQL Contributors
"""NexaQL chat agent -- 3-step pipeline: generate -> execute -> summarize.

Supports two modes:
  - "intent" (Option B, default): LLM extracts structured JSON intent,
    deterministic builder constructs NexaQL. Works with small/cheap models.
  - "raw" (Option A, legacy): LLM generates raw NexaQL strings directly.
    Requires larger models or fine-tuning for accuracy.

Provider-agnostic: uses the unified LLM layer (chat/llm.py) which routes to
Ollama (local), OpenRouter (cloud), or any OpenAI-compatible endpoint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from nexaql.adapters.base import AdapterResult, QueryAdapter
from nexaql.api.deps import get_adapter_for_connector
from nexaql.chat.intent import (
    QueryIntent,
    build_nexaql,
    extract_intent_json,
    parse_intent,
)
from nexaql.chat.llm import chat_completion
from nexaql.chat.prompts import (
    build_intent_system_prompt,
    build_summary_prompt,
    build_system_prompt,
    extract_nexaql_query,
)
from nexaql.config import LLMConfig
from nexaql.engine.parser import ParseError, parse
from nexaql.engine.types import ColumnMeta, NodeShape
from nexaql.engine.validator import validate
from nexaql.federation import detect_cross_datasource, execute_federated
from nexaql.ontology import Ontology
from nexaql.policy.context import UserContext
from nexaql.policy.enforcer import enforce_access
from nexaql.policy.masking import mask_results

logger = logging.getLogger(__name__)

# Generation mode type
GenerationMode = Literal["intent", "raw"]


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
    # New: expose the intent for debugging / UI display
    intent: dict[str, Any] | None = None
    generation_mode: str | None = None


# ── Step 1a: Generate via intent extraction (Option B) ──────────────────────


async def generate_query_via_intent(
    question: str,
    history: list[dict[str, str]],
    ontology: Ontology,
    llm_config: LLMConfig,
    business_context: list[dict] | None = None,
) -> tuple[str | None, str, dict[str, Any] | None]:
    """Generate a NexaQL query via structured intent extraction.

    The LLM outputs a JSON intent, and the deterministic builder constructs
    the NexaQL query. This guarantees syntactic correctness.

    Returns ``(query_text, llm_response, intent_dict)``.
    """
    system_prompt = build_intent_system_prompt(ontology, business_context)

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

    # Extract JSON intent from LLM response
    intent_data = extract_intent_json(response_text)
    if intent_data is None:
        logger.warning("Failed to extract intent JSON from LLM response")
        return None, response_text, None

    try:
        intent = parse_intent(intent_data)
        query_text = build_nexaql(intent)
        logger.info(f"Intent builder generated query: {query_text[:200]}")
        return query_text, response_text, intent_data
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"Failed to build query from intent: {e}")
        return None, response_text, intent_data


# ── Step 1b: Generate via raw NexaQL (Option A, legacy) ─────────────────────


async def generate_query_raw(
    question: str,
    history: list[dict[str, str]],
    ontology: Ontology,
    llm_config: LLMConfig,
    business_context: list[dict] | None = None,
) -> tuple[str | None, str]:
    """Generate a NexaQL query directly from the LLM (legacy mode).

    Returns ``(query_text, explanation)`` where *query_text* may be ``None``
    if the LLM could not produce a valid query block.
    """
    system_prompt = build_system_prompt(ontology, business_context)

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
    user: UserContext | None = None,
) -> tuple[AdapterResult | None, str | None]:
    """Parse, enforce access control, validate, and execute a query.

    Returns ``(result, error)``.
    """
    try:
        ast = parse(query_text)
    except ParseError as e:
        return None, f"Parse error: {e}"

    if user is not None:
        enforcement = enforce_access(ast, ontology, user)
        if enforcement.denied:
            return None, f"Access denied: {enforcement.denied_reason}"
        ast = enforcement.ast
    else:
        enforcement = None

    validation = validate(ast, ontology)
    if not validation.valid:
        error_msgs = "; ".join(err.message for err in validation.errors)
        return None, f"Validation failed: {error_msgs}"

    try:
        is_cross, connector_to_nodes = detect_cross_datasource(ast, ontology)
        if is_cross:
            adapter_map = {}
            for connector_id in connector_to_nodes:
                adapter_map[connector_id] = get_adapter_for_connector(connector_id)
            result = await execute_federated(ast, ontology, adapter_map)
        else:
            node_to_connector = getattr(ontology, "node_to_connector", None) or {}
            root_connector_id = node_to_connector.get(ast.body.name)
            if root_connector_id is not None:
                resolved_adapter = get_adapter_for_connector(root_connector_id)
            else:
                resolved_adapter = adapter
            result = await resolved_adapter.execute(ast, ontology)
        if enforcement and enforcement.masked_fields:
            result.rows = mask_results(result.rows, enforcement.masked_fields)
        return result, None
    except Exception as e:
        return None, str(e)


async def execute_with_retry_intent(
    query_text: str,
    ontology: Ontology,
    adapter: QueryAdapter,
    llm_config: LLMConfig,
    history: list[dict[str, str]],
    question: str,
    original_response: str,
    intent_data: dict[str, Any] | None,
    user: UserContext | None = None,
) -> tuple[AdapterResult | None, str | None, str, dict[str, Any] | None]:
    """Execute a query built from intent, retrying with corrected intent on failure.

    Returns ``(result, error, final_query_text, final_intent)``.
    """
    result, error = await _try_execute(query_text, ontology, adapter, user)
    if result is not None:
        return result, None, query_text, intent_data

    if error and not error.startswith(("Parse error:", "Validation failed:")):
        return None, error, query_text, intent_data

    # Retry: ask LLM to fix the intent JSON
    try:
        system_prompt = build_intent_system_prompt(ontology)

        retry_messages: list[dict[str, str]] = []
        for m in history:
            retry_messages.append({"role": m["role"], "content": m["content"]})
        retry_messages.append({"role": "user", "content": question})
        retry_messages.append({"role": "assistant", "content": original_response})
        retry_messages.append({
            "role": "user",
            "content": (
                f"The query built from your intent failed with this error:\n\n{error}\n\n"
                "Please fix the JSON intent. Common issues:\n"
                "- Use exact field names from the ontology\n"
                "- Use exact node names from the ontology\n"
                "- Only filter on fields marked as filterable\n"
                "- Enum values must be UPPERCASE and match exactly\n"
                + (
                    "- AGGREGATION PLACEMENT: The field in an aggregation MUST exist on the node where the aggregation appears. "
                    "If the field belongs to a related node, move the aggregation INSIDE that edge. "
                    "Example: to sum(quantity) where quantity is on order_items, place the aggregation inside the order_items edge, NOT at the top-level node.\n"
                    if "not found on" in str(error).lower() or "unknown field" in str(error).lower()
                    else ""
                )
                + "Respond with the corrected JSON only."
            ),
        })

        retry_text = chat_completion(
            llm_config,
            system=system_prompt,
            messages=retry_messages,
            max_tokens=llm_config.max_tokens,
        )

        retry_intent_data = extract_intent_json(retry_text)
        if retry_intent_data:
            retry_intent = parse_intent(retry_intent_data)
            retry_query = build_nexaql(retry_intent)

            result2, error2 = await _try_execute(retry_query, ontology, adapter, user)
            if result2 is not None:
                return result2, None, retry_query, retry_intent_data
            return None, error2, retry_query, retry_intent_data
    except Exception:
        pass  # keep original error

    return None, error, query_text, intent_data


async def execute_with_retry_raw(
    query_text: str,
    ontology: Ontology,
    adapter: QueryAdapter,
    llm_config: LLMConfig,
    history: list[dict[str, str]],
    question: str,
    explanation: str,
    user: UserContext | None = None,
) -> tuple[AdapterResult | None, str | None, str]:
    """Execute a query, retrying once with the LLM if it fails (legacy mode).

    Returns ``(result, error, final_query_text)``.
    """
    result, error = await _try_execute(query_text, ontology, adapter, user)
    if result is not None:
        return result, None, query_text

    if error and not error.startswith(("Parse error:", "Validation failed:")):
        return None, error, query_text

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
            result2, error2 = await _try_execute(retry_query, ontology, adapter, user)
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


def _get_generation_mode(llm_config: LLMConfig) -> GenerationMode:
    """Determine which generation mode to use.

    Checks llm_config for a 'generation_mode' attribute. Defaults to 'intent'.
    """
    mode = getattr(llm_config, "generation_mode", "intent")
    if mode in ("intent", "raw"):
        return mode
    return "intent"


async def ask(
    question: str,
    history: list[dict[str, str]],
    ontology: Ontology,
    adapter: QueryAdapter | None,
    llm_config: LLMConfig,
    user: UserContext | None = None,
    business_context: list[dict] | None = None,
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
    user:
        Resolved user context for access control enforcement.
    business_context:
        Relevant business ontology entries for the current query.

    Returns
    -------
    ChatResponse
        The complete response including query, results, and summary.
    """
    mode = _get_generation_mode(llm_config)

    if mode == "intent":
        return await _ask_intent(question, history, ontology, adapter, llm_config, user, business_context)
    else:
        return await _ask_raw(question, history, ontology, adapter, llm_config, user, business_context)


async def _ask_intent(
    question: str,
    history: list[dict[str, str]],
    ontology: Ontology,
    adapter: QueryAdapter | None,
    llm_config: LLMConfig,
    user: UserContext | None = None,
    business_context: list[dict] | None = None,
) -> ChatResponse:
    """Intent-based pipeline (Option B): extract → build → execute → summarize."""

    # Step 1: Extract intent and build query
    query_text, llm_response, intent_data = await generate_query_via_intent(
        question, history, ontology, llm_config, business_context
    )

    if query_text is None:
        # Fallback to raw mode if intent extraction fails
        logger.warning("Intent extraction failed, falling back to raw mode")
        response = await _ask_raw(question, history, ontology, adapter, llm_config, user, business_context)
        response.generation_mode = "raw_fallback"
        return response

    # Step 2: Execute (with retry)
    if adapter is None:
        return ChatResponse(
            explanation=llm_response,
            nexaql_query=query_text,
            summary=f"Generated query from intent (no datasource to execute).",
            intent=intent_data,
            generation_mode="intent",
            error="No datasource configured -- cannot execute query",
        )

    exec_result, exec_error, final_query, final_intent = await execute_with_retry_intent(
        query_text=query_text,
        ontology=ontology,
        adapter=adapter,
        llm_config=llm_config,
        history=history,
        question=question,
        original_response=llm_response,
        intent_data=intent_data,
        user=user,
    )

    # Access denied — return a clear, non-technical message
    if exec_error and exec_error.startswith("Access denied:"):
        reason = exec_error.replace("Access denied: ", "", 1)
        return ChatResponse(
            explanation=llm_response,
            nexaql_query=final_query,
            summary=f"Your current role does not have permission to access this data. {reason}",
            error=None,
            intent=final_intent,
            generation_mode="intent",
        )

    # System/runtime errors — don't expose raw stack traces
    if exec_error and not exec_error.startswith(("Parse error:", "Validation failed:")):
        return ChatResponse(
            explanation=llm_response,
            nexaql_query=final_query,
            summary="Something went wrong while executing the query. This is a system error, not a problem with your question.",
            error=exec_error,
            intent=final_intent,
            generation_mode="intent",
        )

    # Step 3: Summarize
    summary = llm_response
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
            pass

    return ChatResponse(
        explanation=llm_response,
        nexaql_query=final_query,
        query_preview=exec_result.query_preview if exec_result else None,
        adapter_type=exec_result.adapter_type if exec_result else None,
        rows=exec_result.rows if exec_result else [],
        columns=exec_result.columns if exec_result else [],
        row_count=exec_result.row_count if exec_result else 0,
        shape=exec_result.shape if exec_result else None,
        summary=summary,
        error=exec_error,
        intent=final_intent,
        generation_mode="intent",
    )


async def _ask_raw(
    question: str,
    history: list[dict[str, str]],
    ontology: Ontology,
    adapter: QueryAdapter | None,
    llm_config: LLMConfig,
    user: UserContext | None = None,
    business_context: list[dict] | None = None,
) -> ChatResponse:
    """Raw NexaQL pipeline (Option A, legacy): generate → execute → summarize."""

    # Step 1: Generate query
    query_text, explanation = await generate_query_raw(
        question, history, ontology, llm_config, business_context
    )

    if query_text is None:
        return ChatResponse(
            explanation=explanation,
            nexaql_query=None,
            summary=explanation,
            generation_mode="raw",
        )

    # Step 2: Execute (with retry)
    if adapter is None:
        return ChatResponse(
            explanation=explanation,
            nexaql_query=query_text,
            summary=explanation,
            error="No datasource configured -- cannot execute query",
            generation_mode="raw",
        )

    exec_result, exec_error, final_query = await execute_with_retry_raw(
        query_text=query_text,
        ontology=ontology,
        adapter=adapter,
        llm_config=llm_config,
        history=history,
        question=question,
        explanation=explanation,
        user=user,
    )

    # Access denied — return a clear, non-technical message
    if exec_error and exec_error.startswith("Access denied:"):
        reason = exec_error.replace("Access denied: ", "", 1)
        return ChatResponse(
            explanation=explanation,
            nexaql_query=final_query,
            summary=f"Your current role does not have permission to access this data. {reason}",
            error=None,
            generation_mode="raw",
        )

    # System/runtime errors — don't expose raw stack traces
    if exec_error and not exec_error.startswith(("Parse error:", "Validation failed:")):
        return ChatResponse(
            explanation=explanation,
            nexaql_query=final_query,
            summary="Something went wrong while executing the query. This is a system error, not a problem with your question.",
            error=exec_error,
            generation_mode="raw",
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
            pass

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
        generation_mode="raw",
    )
