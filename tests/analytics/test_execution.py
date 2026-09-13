import pytest
from nexaql.adapters.duckdb_adapter import DuckDBAdapter
from nexaql.analytics import Comparison, ReconciliationPlan, execute_reconciliation
from nexaql.ontology.models import Ontology
from nexaql.policy.context import UserContext


def ontology():
    fields = {
        "id": {"type": "integer", "description": "identity"},
        "value": {"type": "numeric", "description": "measure"},
        "unit": {"type": "string", "description": "unit"},
    }
    return Ontology(
        version="1",
        domain="test",
        description="generic capacities",
        nodes={
            "parent": {
                "table": "parents",
                "primary_key": "id",
                "description": "capacity",
                "fields": fields,
                "edges": {
                    "children": {
                        "node": "child",
                        "description": "usage",
                        "join_steps": [
                            {"table": "children", "alias_key": "child", "condition": "{child}.parent_id = {parent}.id"}
                        ],
                    }
                },
            },
            "child": {"table": "children", "primary_key": "id", "description": "usage", "fields": fields},
        },
    )


def plan():
    return ReconciliationPlan(
        rule_id="capacity",
        rule_version="1",
        parent_key="parent.id",
        child_key="child.id",
        scope="all authorized rows",
        comparisons=[
            Comparison(
                name="usage",
                expected_field="parent.value",
                actual_field="child.value",
                expected_unit_field="parent.unit",
                actual_unit_field="child.unit",
            )
        ],
    )


@pytest.mark.asyncio
async def test_query_execution_computes_cumulative_totals_and_retains_empty_parent():
    adapter = DuckDBAdapter()
    conn = adapter._get_conn()
    conn.execute("CREATE TABLE parents(id INT,value DECIMAL(12,2),unit VARCHAR)")
    conn.execute("CREATE TABLE children(id INT,parent_id INT,value DECIMAL(12,2),unit VARCHAR)")
    conn.execute("INSERT INTO parents VALUES(1,10,'EA'),(2,10,'EA')")
    conn.execute("INSERT INTO children VALUES(1,1,6,'EA'),(2,1,5,'EA')")
    try:
        result = await execute_reconciliation(
            plan(),
            "query { parent { id value unit children { id value unit } } }",
            ontology(),
            adapter,
            UserContext(user_id=1),
        )
        assert result.entities_checked == 2
        assert result.violation_count == 1
        assert str(result.findings[0].difference) == "1.00"
        assert result.complete and result.execution_id
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_missing_identity_and_unauthorized_node_are_rejected():
    adapter = DuckDBAdapter()
    onto = ontology()
    query = "query { parent { id value unit children { id value unit } } }"
    with pytest.raises(ValueError, match="authenticated"):
        await execute_reconciliation(plan(), query, onto, adapter, None)
    onto.nodes["parent"].visible_to = ["finance"]
    with pytest.raises(ValueError, match="Access denied"):
        await execute_reconciliation(plan(), query, onto, adapter, UserContext(user_id=1, roles=["guest"]))
