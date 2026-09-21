"""Detail-grain cumulative comparisons must not become per-row comparisons."""

import duckdb
from nexaql.engine.parser import parse
from nexaql.engine.translator import translate
from nexaql.ontology.models import Ontology


def test_window_total_filters_details_before_pagination():
    ontology = Ontology.model_validate(
        {
            "version": "1",
            "domain": "test",
            "description": "",
            "nodes": {
                "lines": {
                    "description": "",
                    "table": "lines",
                    "primary_key": "id",
                    "fields": {
                        "id": {"description": "", "type": "integer"},
                        "ref": {"description": "", "type": "integer"},
                        "amount": {"description": "", "type": "numeric"},
                    },
                    "edges": {
                        "allowance": {
                            "description": "",
                            "node": "allowances",
                            "join_steps": [
                                {
                                    "description": "",
                                    "table": "allowances",
                                    "alias_key": "allowance",
                                    "condition": "{lines}.ref = {allowance}.id",
                                }
                            ],
                        }
                    },
                },
                "allowances": {
                    "description": "",
                    "table": "allowances",
                    "primary_key": "id",
                    "fields": {
                        "id": {"description": "", "type": "integer"},
                        "amount": {"description": "", "type": "numeric"},
                    },
                },
            },
        }
    )
    db = duckdb.connect(":memory:")
    db.execute("CREATE TABLE lines(id INTEGER, ref INTEGER, amount DECIMAL(10,2))")
    db.execute("CREATE TABLE allowances(id INTEGER, amount DECIMAL(10,2))")
    db.execute("INSERT INTO allowances VALUES (1,100),(2,100),(3,100),(4,100),(5,100)")
    # Multiple individually valid lines breach together; equality/under/null/unlinked do not.
    db.execute(
        "INSERT INTO lines VALUES (1,1,60),(2,1,50),(3,2,60),(4,2,40),(5,3,80),(6,3,-10),(7,4,NULL),(8,NULL,999)"
    )
    query = """query { lines(calc(SUM(amount) OVER (PARTITION BY ref) - allowance.amount): {gt: 0}) {
      id ref amount total: calc(SUM(amount) OVER (PARTITION BY ref)) allowance { amount }
    } }"""
    result = translate(parse(query), ontology)
    rows = db.execute(result.sql).fetchall()
    assert sorted(row[0] for row in rows) == [1, 2]
    assert all(row[3] == 110 for row in rows)
    assert "__nexaql_window_filter" not in [column[0] for column in db.description]
    limited = query.replace("{gt: 0}) {", "{gt: 0}) @orderby(id, DESC) @limit(1) @offset(1) {")
    page = db.execute(translate(parse(limited), ontology).sql).fetchall()
    assert len(page) == 1 and page[0][0] == 1
    assert page[0][3] == 110  # LIMIT must not change the partition total.
    db.close()
