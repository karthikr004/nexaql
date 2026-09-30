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
import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

from nexaql.adapters.base import AdapterResult, QueryAdapter
from nexaql.api.deps import get_adapter_for_connector
from nexaql.chat.intent import (
    QueryIntent,
    auto_require_intent,
    build_nexaql,
    decompose_intent,
    extract_intent_json,
    needs_decomposition,
    parse_intent,
    restructure_edges,
)
from nexaql.chat.context import AdditionalContext
from nexaql.chat.repair import execute_repair_loop, recoverable_query_error
from nexaql.chat.llm import chat_completion
from nexaql.chat.prompts import (
    build_intent_system_prompt,
    build_summary_prompt,
    build_system_prompt,
    extract_nexaql_query,
)
from nexaql.config import LLMConfig
from nexaql.engine.types import ColumnMeta, NodeShape
from nexaql.ontology import Ontology
from nexaql.policy.context import UserContext

logger = logging.getLogger(__name__)

# Generation mode type
GenerationMode = Literal["intent", "raw"]


def _auto_inject_edge_filters(intent: QueryIntent, ontology: Ontology) -> None:
    """Auto-add NOT NULL filters on FK fields for LEFT JOIN edges.

    When the intent requests data from a LEFT JOIN edge, the result includes
    ALL rows from the root table — including rows without the related entity.
    This injects a ``not_null`` filter on the FK field so only linked rows
    are returned, unless the LLM already added such a filter.
    """
    import re
    from nexaql.chat.intent import IntentFilter

    node_def = ontology.nodes.get(intent.node)
    if not node_def or not intent.edges:
        return

    existing_filter_fields = {f.field for f in intent.filters}

    for edge in intent.edges:
        edge_def = node_def.edges.get(edge.name)
        if not edge_def:
            continue
        join_type = getattr(edge_def, "join_type", None)
        if join_type and join_type.upper() != "LEFT":
            continue
        if not join_type:
            continue

        for step in edge_def.join_steps:
            cond = step.condition
            root_alias = "{" + intent.node + "}"
            match = re.search(
                re.escape(root_alias) + r"\.(\w+)",
                cond,
            )
            if match:
                fk_field = match.group(1)
                fields_dict = node_def.fields
                if isinstance(fields_dict, dict) and fk_field in fields_dict:
                    filt_attr = getattr(fields_dict[fk_field], "filterable", False)
                    if filt_attr and fk_field not in existing_filter_fields:
                        intent.filters.append(IntentFilter(field=fk_field, op="not_null", value=True))
                        logger.info(
                            "Auto-injected not_null filter on %s for LEFT JOIN edge %s",
                            fk_field,
                            edge.name,
                        )
                break


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
    visualization: dict[str, Any] | None = None


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

    response_text = await asyncio.to_thread(
        chat_completion, llm_config,
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
        if intent.cumulative_comparison is None:
            import re

            if any(re.search(r"SUM\s*\(.*\)\s*OVER\s*\(", f.expr, re.I) for f in intent.calc_filters):
                raise ValueError(
                    "Use cumulative_comparison for cumulative SUM comparisons: root must be the contributing detail entity, reference its parent edge, and use output_grain for the requested entity. Do not author a window expression."
                )
        from nexaql.chat.output_grain import apply_output_grain
        from nexaql.chat.analytical_intent import compile_comparison

        intent = compile_comparison(intent, ontology)
        from nexaql.chat.relationship_intent import compile_missing_relationship

        intent = compile_missing_relationship(intent, ontology)
        intent = apply_output_grain(intent, ontology)
        intent = auto_require_intent(intent)
        _auto_inject_edge_filters(intent, ontology)
        query_text = build_nexaql(intent)
        logger.info(f"Intent builder generated query: {query_text[:200]}")
        import dataclasses

        return query_text, response_text, dataclasses.asdict(intent)
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"Failed to build query from intent: {e}")
        return None, response_text + "\nGeneration validation failed: " + str(e), intent_data


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

    response_text = await asyncio.to_thread(
        chat_completion, llm_config,
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
    from nexaql.engine.execution import prepare_query, execute_prepared

    try:
        prepared = prepare_query(query_text, ontology, user)
        return await execute_prepared(prepared, adapter, get_adapter_for_connector), None
    except Exception as exc:
        return None, str(exc)


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
    business_context: list[dict] | None = None,
) -> tuple[AdapterResult | None, str | None, str, dict[str, Any] | None]:
    """Execute a query built from intent, retrying with corrected intent on failure.

    Returns ``(result, error, final_query_text, final_intent)``.
    """
    current_intent = intent_data
    review_trace = []

    async def execute(query):
        from nexaql.engine.execution import prepare_query
        from nexaql.chat.query_review import review_query
        from nexaql.chat.intent_contract import repair_contract_errors

        violations = repair_contract_errors(intent_data, current_intent)
        if violations:
            return None, "Validation failed: " + "; ".join(violations)
        try:
            prepare_query(query, ontology, user)
        except (ValueError, PermissionError) as exc:
            return None, str(exc)
        review = await asyncio.to_thread(
            review_query, question,
            query,
            current_intent,
            ontology,
            business_context,
            llm_config,
            required_intent=intent_data,
        )
        review_trace.append(review)
        if not review["approved"]:
            return None, "Validation failed: semantic review: " + "; ".join(review["issues"])
        return await _try_execute(query, ontology, adapter, user)

    async def generate(turns):
        nonlocal current_intent
        query, response, corrected = await generate_query_via_intent(
            question, turns, ontology, llm_config, business_context
        )
        current_intent = corrected
        return query, response, corrected

    result, error, query, final_intent = await execute_repair_loop(
        query_text, intent_data, original_response, history, execute, generate
    )
    return result, error, query, {**(final_intent or {}), "query_review": review_trace}


async def execute_with_retry_raw(
    query_text: str,
    ontology: Ontology,
    adapter: QueryAdapter,
    llm_config: LLMConfig,
    history: list[dict[str, str]],
    question: str,
    explanation: str,
    user: UserContext | None = None,
    business_context: list[dict] | None = None,
) -> tuple[AdapterResult | None, str | None, str]:
    """Execute a query, retrying once with the LLM if it fails (legacy mode).

    Returns ``(result, error, final_query_text)``.
    """

    async def execute(query):
        return await _try_execute(query, ontology, adapter, user)

    async def generate(turns):
        query, response = await generate_query_raw(question, turns, ontology, llm_config, business_context)
        return query, response, None

    result, error, query, _ = await execute_repair_loop(query_text, None, explanation, history, execute, generate)
    return result, error, query


# ── Step 3: Summarize results ───────────────────────────────────────────────


async def summarize_results(
    question: str,
    query: str,
    rows: list[dict[str, Any]],
    columns: list[ColumnMeta],
    row_count: int,
    llm_config: LLMConfig,
    result_entity: str | None = None,
) -> str:
    """Produce a natural-language summary of query results."""
    from nexaql.chat.currency_summary import mixed_currency_summary

    currency_summary = mixed_currency_summary(rows, row_count)
    if currency_summary is not None:
        return currency_summary
    prompt = build_summary_prompt(question, query, rows, columns, row_count)
    if result_entity:
        prompt += f"\nVerified output grain: one row per {result_entity}. The total is {row_count} distinct {result_entity} records, not source/calculation rows."

    return await asyncio.to_thread(
        chat_completion, llm_config,
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
    *,
    additional_context: AdditionalContext | None = None,
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

    additional_context:
        Optional caller business definitions and skill instructions. Existing
        history and business_context parameters remain supported unchanged.

    Returns
    -------
    ChatResponse
        The complete response including query, results, and summary.
    """
    if additional_context is not None:
        business_context = [*(business_context or []), *additional_context.entries()]

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
        # Give structured generation one correction before the existing raw fallback.
        from nexaql.chat.repair import correction_message

        query_text, llm_response, intent_data = await generate_query_via_intent(
            question,
            [
                *history,
                {"role": "assistant", "content": llm_response},
                correction_message("", "Generation failed: return a valid structured intent"),
            ],
            ontology,
            llm_config,
            business_context,
        )

    if query_text is None:
        return ChatResponse(
            error="Generation failed: could not construct a valid structured query without changing the request",
            summary="The query could not be generated reliably. No results were produced.",
            intent=intent_data,
            generation_mode="intent",
        )

    # Step 1.5: Restructure flat sibling edges into chain traversal using ontology
    restructured_intent: QueryIntent | None = None
    if intent_data:
        try:
            parsed = parse_intent(intent_data)
            restructured_intent = restructure_edges(parsed, ontology)
            if len(restructured_intent.edges) < len(parsed.edges):
                query_text = build_nexaql(restructured_intent)
                logger.info(
                    "Restructured %d flat edges into %d chained: %s",
                    len(parsed.edges),
                    len(restructured_intent.edges),
                    query_text[:200],
                )
        except Exception:
            logger.debug("Edge restructuring skipped", exc_info=True)

    if adapter is None:
        return ChatResponse(
            explanation=llm_response,
            nexaql_query=query_text,
            summary="Generated query from intent (no datasource to execute).",
            intent=intent_data,
            generation_mode="intent",
            error="No datasource configured -- cannot execute query",
            visualization=intent_data.get("visualization") if isinstance(intent_data, dict) else None,
        )

    # Step 1.6: Decompose remaining flat sibling edges to prevent cartesian products
    check_intent = restructured_intent or (parse_intent(intent_data) if intent_data else None)
    if check_intent and needs_decomposition(check_intent, ontology):
        return await _ask_intent_decomposed(
            question=question,
            history=history,
            ontology=ontology,
            adapter=adapter,
            llm_config=llm_config,
            llm_response=llm_response,
            intent_data=intent_data,
            user=user,
            business_context=business_context,
        )

    # Step 2: Execute (with retry)
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
        business_context=business_context,
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
    if exec_error and not recoverable_query_error(exec_error):
        return ChatResponse(
            explanation=llm_response,
            nexaql_query=final_query,
            summary="Something went wrong while executing the query. This is a system error, not a problem with your question.",
            error=exec_error,
            intent=final_intent,
            generation_mode="intent",
        )

    # Step 3: Summarize
    summary = (
        "The query could not be completed reliably. No verified result was produced." if exec_error else llm_response
    )
    if exec_result is not None and exec_error is None:
        try:
            summary = await summarize_results(
                question=question,
                query=final_query,
                rows=exec_result.rows,
                columns=exec_result.columns,
                row_count=exec_result.row_count,
                llm_config=llm_config,
                result_entity=_result_entity(final_intent),
            )
        except Exception:
            pass

    viz = final_intent.get("visualization") if isinstance(final_intent, dict) else None

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
        visualization=viz,
    )


async def _ask_intent_decomposed(
    question: str,
    history: list[dict[str, str]],
    ontology: Ontology,
    adapter: QueryAdapter,
    llm_config: LLMConfig,
    llm_response: str,
    intent_data: dict[str, Any],
    user: UserContext | None = None,
    business_context: list[dict] | None = None,
) -> ChatResponse:
    """Execute a multi-edge intent as separate per-edge queries to prevent fan-out.

    Splits the intent into one sub-query per edge, executes each independently,
    then merges all result sets for a single summarization pass.
    """
    intent = parse_intent(intent_data)
    sub_intents = decompose_intent(intent)
    logger.info(
        "Decomposing %d-edge intent into %d sub-queries to prevent cartesian product",
        len(intent.edges),
        len(sub_intents),
    )

    all_rows: list[dict[str, Any]] = []
    all_columns: list[ColumnMeta] = []
    all_queries: list[str] = []
    all_previews: list[str] = []
    total_row_count = 0
    seen_col_names: set[str] = set()
    last_shape: NodeShape | None = None
    last_adapter_type: str | None = None
    first_error: str | None = None

    for sub in sub_intents:
        sub_query = build_nexaql(sub)
        all_queries.append(sub_query)

        import dataclasses

        result, error, final_query, _ = await execute_with_retry_intent(
            sub_query,
            ontology,
            adapter,
            llm_config,
            history,
            question,
            llm_response,
            dataclasses.asdict(sub),
            user,
            business_context,
        )
        all_queries[-1] = final_query

        if error:
            if error.startswith("Access denied:"):
                reason = error.replace("Access denied: ", "", 1)
                return ChatResponse(
                    explanation=llm_response,
                    nexaql_query="\n\n".join(all_queries),
                    summary=f"Your current role does not have permission to access this data. {reason}",
                    error=None,
                    intent=intent_data,
                    generation_mode="intent_decomposed",
                )
            if first_error is None:
                first_error = error
            logger.warning("Sub-query failed: %s — %s", sub_query[:80], error)
            continue

        if result:
            all_rows.extend(result.rows)
            total_row_count += result.row_count
            last_shape = result.shape
            last_adapter_type = result.adapter_type
            if result.query_preview:
                all_previews.append(result.query_preview)
            for col in result.columns:
                if col.name not in seen_col_names:
                    all_columns.append(col)
                    seen_col_names.add(col.name)

    if not all_rows and first_error:
        return ChatResponse(
            explanation=llm_response,
            nexaql_query="\n\n".join(all_queries),
            summary="Something went wrong while executing the query. This is a system error, not a problem with your question.",
            error=first_error,
            intent=intent_data,
            generation_mode="intent_decomposed",
        )

    combined_query = "\n\n".join(all_queries)
    combined_preview = "\n---\n".join(all_previews)

    summary = llm_response
    if all_rows:
        try:
            summary = await summarize_results(
                question=question,
                query=combined_query,
                rows=all_rows,
                columns=all_columns,
                row_count=total_row_count,
                llm_config=llm_config,
            )
        except Exception:
            pass

    return ChatResponse(
        explanation=llm_response,
        nexaql_query=combined_query,
        query_preview=combined_preview or None,
        adapter_type=last_adapter_type,
        rows=all_rows,
        columns=all_columns,
        row_count=total_row_count,
        shape=last_shape,
        summary=summary,
        error=None,
        intent=intent_data,
        generation_mode="intent_decomposed",
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
    query_text, explanation = await generate_query_raw(question, history, ontology, llm_config, business_context)

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
        business_context=business_context,
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
    if exec_error and not recoverable_query_error(exec_error):
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


def _result_entity(intent):
    """Identify distinct entity projections for accurate count labels."""
    if not intent or not intent.get("distinct"):
        return None
    grain = intent.get("output_grain")
    if grain:
        return ".".join(grain.get("path", [])) or intent["node"]
    projections = []

    def visit(selection, path):
        if selection.get("fields") or selection.get("calcs") or selection.get("aggregations"):
            projections.append(path)
        for edge in selection.get("edges", []):
            visit(edge, [*path, edge["name"]])

    visit(intent, [])
    if len(projections) == 1:
        return ".".join(projections[0]) or intent["node"]
    return None
