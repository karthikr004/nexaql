from decimal import Decimal
import pytest
from nexaql.analytics import Comparison, ReconciliationPlan, EvidenceBatch, reconcile
from nexaql.analytics.execution import validate_evidence_query


def plan(limit=50):
    return ReconciliationPlan(
        rule_id="capacity",
        rule_version="1",
        parent_key="p",
        child_key="c",
        scope="all visible records",
        sample_limit=limit,
        comparisons=[
            Comparison(
                name="usage",
                expected_field="expected",
                actual_field="actual",
                expected_unit_field="eu",
                actual_unit_field="au",
            )
        ],
    )


def batch(rows, complete=True):
    return EvidenceBatch(
        rows=rows, complete=complete, query="test", schema_version="v1", execution_id="1", executed_at="now"
    )


def row(child, actual, parent=1, expected="10", unit="EA"):
    return dict(p=parent, c=child, expected=expected, actual=actual, eu="EA", au=unit)


def test_cumulative_overage_and_sample_independent_totals():
    result = reconcile(plan(1), batch([row(1, "6"), row(2, "5"), row(3, "12", parent=2)]))
    assert result.violation_count == 2
    assert result.comparison_counts == {"usage": 2}
    assert result.difference_totals_by_unit["usage"]["EA"] == Decimal(3)
    assert len(result.findings) == 1 and result.findings_truncated


def test_equal_under_zero_credits_and_exact_decimals():
    result = reconcile(
        plan(),
        batch(
            [
                row(1, "11"),
                row(2, "-1"),
                row(3, "0", parent=2, expected="0"),
                row(4, "0.1", parent=3, expected="0.3"),
                row(5, "0.2", parent=3, expected="0.3"),
            ]
        ),
    )
    assert result.violation_count == 0 and result.complete


@pytest.mark.parametrize("rows", [[row(1, "6"), row(1, "6")], [row(1, "6"), row(1, "6", parent=2)]])
def test_join_fanout_is_rejected(rows):
    with pytest.raises(ValueError, match="fanout"):
        reconcile(plan(), batch(rows))


@pytest.mark.parametrize("value", [None, 1.2, "NaN", "Infinity"])
def test_invalid_numbers_are_gaps_not_zero(value):
    result = reconcile(plan(), batch([row(1, value)]))
    assert not result.complete and result.validation_gaps and result.violation_count == 0


def test_incompatible_units_do_not_produce_findings():
    result = reconcile(plan(), batch([row(1, "20", unit="KG")]))
    assert not result.complete and result.violation_count == 0


def test_incomplete_evidence_cannot_establish_totals():
    with pytest.raises(ValueError, match="complete evidence"):
        reconcile(plan(), batch([], False))


@pytest.mark.parametrize(
    "query", ["query { parent @limit(10) { id } }", "query { parent { id child(x: {eq: 1}) { id } } }"]
)
def test_incomplete_query_shapes_are_rejected(query):
    with pytest.raises(ValueError):
        validate_evidence_query(query)


def test_aggregate_is_independent_of_default_decimal_precision():
    from decimal import localcontext

    with localcontext() as ctx:
        ctx.prec = 4
        result = reconcile(
            plan(), batch([row(1, "10000000000000000000000000000.01", expected="10000000000000000000000000000.00")])
        )
    assert result.findings[0].difference == Decimal("0.01")
