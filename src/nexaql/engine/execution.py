"""Shared governed query preparation and execution for all consumption modes."""
from dataclasses import dataclass
from typing import Any, Callable

from nexaql.engine.parser import parse, ParseError
from nexaql.engine.lexer import LexerError
from nexaql.engine.transforms import auto_require_edges
from nexaql.engine.validator import validate
from nexaql.federation import detect_cross_datasource, execute_federated
from nexaql.policy.enforcer import enforce_access
from nexaql.policy.masking import mask_results


@dataclass
class PreparedQuery:
    ast: Any
    ontology: Any
    enforcement: Any
    validation: Any
    connectors: dict
    federated: bool


def prepare_query(query, ontology, user=None):
    try:
        ast = auto_require_edges(parse(query))
    except (ParseError, LexerError) as exc:
        raise ValueError(f"Parse error: {exc}") from exc
    enforcement = enforce_access(ast, ontology, user) if user is not None else None
    if enforcement:
        if enforcement.denied:
            raise PermissionError(f"Access denied: {enforcement.denied_reason}")
        ast = enforcement.ast
    validation = validate(ast, ontology)
    if not validation.valid:
        raise ValueError("Validation failed: " + "; ".join(e.message for e in validation.errors))
    federated, connectors = detect_cross_datasource(ast, ontology)
    return PreparedQuery(ast, ontology, enforcement, validation, connectors, federated)


def resolve_adapter(prepared, fallback, resolver):
    mapping = getattr(prepared.ontology, 'node_to_connector', None) or {}
    connector = mapping.get(prepared.ast.body.name)
    return resolver(connector) if connector is not None else fallback


def masked(prepared, rows):
    fields = prepared.enforcement.masked_fields if prepared.enforcement else None
    return mask_results(rows, fields) if fields else rows


async def execute_prepared(prepared, fallback, resolver: Callable, *, session_id=None):
    if prepared.federated:
        adapters = {identity: resolver(identity) for identity in prepared.connectors}
        result = await execute_federated(prepared.ast, prepared.ontology, adapters, session_id)
    else:
        adapter = resolve_adapter(prepared, fallback, resolver)
        result = await adapter.execute(prepared.ast, prepared.ontology)
    result.rows = masked(prepared, result.rows)
    return result


async def stream_prepared(prepared, fallback, resolver: Callable, *, batch_size=1000):
    # A materialized federation fallback would defeat bounded result handling.
    if prepared.federated:
        raise ValueError('Streaming cross-datasource queries is not supported; use materialized execution')
    adapter = resolve_adapter(prepared, fallback, resolver)
    if not hasattr(adapter, 'stream_rows'):
        raise ValueError('This connector does not support streamed execution yet')
    async for rows in adapter.stream_rows(prepared.ast, prepared.ontology, batch_size=batch_size):
        yield masked(prepared, rows)
