"""Execute reconciliation through NexaQL's existing access-controlled query path."""

from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

from nexaql.engine.parser import parse
from nexaql.federation import detect_cross_datasource
from .models import EvidenceBatch, ReconciliationPlan
from .reconcile import reconcile


def validate_evidence_query(query: str):
    ast = parse(query)

    def walk(node):
        if any(d.type != "orderby" for d in node.directives):
            raise ValueError("Evidence queries cannot limit, offset, distinct, or require rows")
        for field in node.fields:
            if field.kind == "edge":
                if field.node.filters:
                    raise ValueError("Child filters can omit contributing records")
                walk(field.node)
            elif field.kind != "scalar":
                raise ValueError("Evidence queries must expose raw measures and identities")

    walk(ast.body)
    return ast


async def execute_reconciliation(plan: ReconciliationPlan, query: str, ontology, adapter, user):
    if user is None:
        raise ValueError("An authenticated execution identity is required")
    ast = validate_evidence_query(query)
    parent_node, parent_field = plan.parent_key.split(".", 1)
    child_node, child_field = plan.child_key.split(".", 1)
    parent = ontology.nodes.get(parent_node)
    child = ontology.nodes.get(child_node)
    if (
        parent is None
        or child is None
        or ast.body.name != parent_node
        or parent.primary_key != parent_field
        or child.primary_key != child_field
    ):
        raise ValueError("Plan grain must use the root and child ontology primary keys")
    direct_children = [f.node.name for f in ast.body.fields if f.kind == "edge"]
    if not any((parent.edges or {}).get(name) and parent.edges[name].node == child_node for name in direct_children):
        raise ValueError("Comparison requires a direct parent-to-child ontology relationship")
    for comparison in plan.comparisons:
        for name, owner in ((comparison.expected_field, parent_node), (comparison.actual_field, child_node)):
            node_name, field_name = name.split(".", 1)
            definition = ontology.nodes.get(node_name)
            if (
                node_name != owner
                or definition is None
                or field_name not in definition.fields
                or definition.fields[field_name].type not in {"numeric", "integer"}
            ):
                raise ValueError("Comparison measures must be numeric fields on their declared owning nodes")
    if detect_cross_datasource(ast, ontology)[0]:
        raise ValueError("Cross-datasource reconciliation requires consistent snapshot support")
    from nexaql.chat.agent import _try_execute

    result, error = await _try_execute(query, ontology, adapter, user)
    if error or result is None:
        raise ValueError(error or "Evidence execution failed")
    if result.adapter_type not in {"postgresql", "duckdb"}:
        raise ValueError("This adapter has not been verified for complete exact-decimal evidence")
    rows = []
    for row in result.rows:
        normalized = {key.replace("__", ".", 1): value for key, value in row.items()}
        if len(normalized) != len(row):
            raise ValueError("Ambiguous result column aliases")
        rows.append(normalized)
    batch = EvidenceBatch(
        rows=rows,
        complete=result.row_count == len(result.rows),
        query=query,
        schema_version=sha256(ontology.model_dump_json().encode()).hexdigest(),
        execution_id=str(uuid4()),
        executed_at=datetime.now(timezone.utc).isoformat(),
    )
    return reconcile(plan, batch)
