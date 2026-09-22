"""Execute generated projections against independent, small analytical fixtures."""

from decimal import Decimal
import duckdb
from nexaql.ontology.models import Ontology
from nexaql.chat.intent import parse_intent, build_nexaql
from nexaql.chat.output_grain import apply_output_grain
from nexaql.engine.execution import prepare_query
from nexaql.engine.translator import translate


def ontology():
    def field(kind):
        return {"type": kind, "description": ""}

    return Ontology.model_validate(
        {
            "version": "1",
            "domain": "test",
            "description": "",
            "nodes": {
                "buyer": {
                    "table": "buyers",
                    "description": "",
                    "primary_key": "id",
                    "fields": {"id": field("integer"), "name": field("string")},
                    "edges": {
                        "orders": {
                            "description": "",
                            "node": "order",
                            "join_steps": [
                                {
                                    "description": "",
                                    "table": "orders",
                                    "alias_key": "orders",
                                    "condition": "{buyer}.id = {orders}.buyer_id",
                                }
                            ],
                        }
                    },
                },
                "order": {
                    "table": "orders",
                    "description": "",
                    "primary_key": "id",
                    "fields": {
                        "id": field("integer"),
                        "buyer_id": field("integer"),
                        "amount": field("numeric"),
                        "paid": field("numeric"),
                    },
                    "edges": {
                        "buyer": {
                            "description": "",
                            "node": "buyer",
                            "join_steps": [
                                {
                                    "description": "",
                                    "table": "buyers",
                                    "alias_key": "buyer",
                                    "condition": "{order}.buyer_id = {buyer}.id",
                                }
                            ],
                        }
                    },
                },
            },
        }
    )


def execute(intent):
    schema = ontology()
    projected = apply_output_grain(parse_intent(intent), schema)
    prepared = prepare_query(build_nexaql(projected), schema)
    sql = translate(prepared.ast, schema).sql
    with duckdb.connect(":memory:") as db:
        db.execute("CREATE TABLE buyers(id INTEGER, name VARCHAR)")
        db.execute("CREATE TABLE orders(id INTEGER, buyer_id INTEGER, amount DECIMAL(10,2), paid DECIMAL(10,2))")
        db.execute("INSERT INTO buyers VALUES (1,'A'),(2,'B')")
        db.execute("INSERT INTO orders VALUES (10,1,100,20),(11,1,50,50),(12,2,70,0)")
        rows = db.execute(sql).fetchall()
    return sorted(rows)


def test_entity_projection_retains_requested_calculated_amount():
    rows = execute(
        {
            "node": "order",
            "fields": ["id"],
            "calcs": [{"alias": "outstanding", "expr": "amount - paid"}],
            "output_grain": {"path": [], "fields": ["id"]},
        }
    )
    assert rows == [(10, Decimal("80")), (11, Decimal("0")), (12, Decimal("70"))]


def test_entity_projection_retains_child_sum_without_child_detail_grain():
    rows = execute(
        {
            "node": "buyer",
            "fields": ["id", "name"],
            "output_grain": {"path": [], "fields": ["id", "name"]},
            "edges": [
                {
                    "name": "orders",
                    "fields": ["id"],
                    "required": True,
                    "aggregations": [{"alias": "total", "func": "sum", "field": "amount"}],
                }
            ],
        }
    )
    assert rows == [(1, "A", Decimal("150")), (2, "B", Decimal("70"))]


def test_parent_projection_aggregates_source_measures_at_parent_grain():
    rows = execute(
        {
            "node": "order",
            "fields": ["id", "amount"],
            "aggregations": [{"alias": "total", "func": "sum", "field": "amount"}],
            "output_grain": {"path": ["buyer"], "fields": ["name"]},
        }
    )
    # The aggregate is emitted before parent fields, with one row per buyer.
    assert rows == [(Decimal("70"), 2, "B"), (Decimal("150"), 1, "A")]
