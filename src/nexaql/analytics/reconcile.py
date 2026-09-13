"""Reconcile a single authorized parent/child result without LLM arithmetic.

The query must expose stable parent and child identities. Repeated join rows
are rejected instead of deduplicated: they indicate an invalid comparison grain.
"""

from collections import defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256

from .models import EvidenceBatch, Finding, ReconciliationPlan, ReconciliationResult


def number(value) -> Decimal:
    if value is None or isinstance(value, (bool, float)):
        raise ValueError("Missing or inexact numeric value")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Invalid numeric value") from None
    if not result.is_finite():
        raise ValueError("Non-finite numeric value")
    return result


def reconcile(plan: ReconciliationPlan, batch: EvidenceBatch) -> ReconciliationResult:
    # Reserve enough precision for every input scale and the largest possible
    # sum. Do not let the process-wide Decimal context round aggregate totals.
    integer_digits, fractional_digits = 1, 0
    values = [c.tolerance for c in plan.comparisons]
    for row in batch.rows:
        for c in plan.comparisons:
            values.extend((row.get(c.expected_field), row.get(c.actual_field)))
    for value in values:
        try:
            decimal = number(value)
        except ValueError:
            continue  # The evaluator reports these as per-measure gaps.
        integer_digits = max(integer_digits, decimal.adjusted() + 1)
        fractional_digits = max(fractional_digits, -decimal.as_tuple().exponent)
    with localcontext() as context:
        context.prec = max(28, integer_digits + fractional_digits + len(str(len(batch.rows) + 1)) + 2)
        return _reconcile(plan, batch)


def _reconcile(plan: ReconciliationPlan, batch: EvidenceBatch) -> ReconciliationResult:
    if not batch.complete:
        raise ValueError("Reconciliation requires complete evidence; limited samples cannot prove totals")
    groups = defaultdict(list)
    children = set()
    required = {plan.parent_key, plan.child_key}
    for c in plan.comparisons:
        required.update((c.expected_field, c.actual_field, c.expected_unit_field, c.actual_unit_field))
    for row in batch.rows:
        if not required.issubset(row):
            raise ValueError("Evidence lacks required identity, measure, or unit fields")
        parent, child = row[plan.parent_key], row[plan.child_key]
        if parent is None:
            raise ValueError("Missing parent identity")
        if child is None and any(row[c.actual_field] is not None for c in plan.comparisons):
            raise ValueError("Missing child identity for populated measures")
        if child is not None:
            if child in children:
                raise ValueError("Repeated child identity: ambiguous join or fanout")
            children.add(child)
        groups[str(parent)].append(row)
    findings, gaps = [], []
    violated = set()
    counts = {c.name: 0 for c in plan.comparisons}
    totals = {c.name: defaultdict(Decimal) for c in plan.comparisons}
    for parent, rows in groups.items():
        for c in plan.comparisons:
            try:
                expected = number(rows[0][c.expected_field])
                unit = rows[0][c.expected_unit_field]
                if not isinstance(unit, str) or not unit.strip():
                    raise ValueError("Expected measure unit is unknown")
                actual = Decimal(0)
                ids = []
                for row in rows:
                    if number(row[c.expected_field]) != expected or row[c.expected_unit_field] != unit:
                        raise ValueError("Inconsistent parent measure or unit")
                    if row[plan.child_key] is None:
                        continue
                    if row[c.actual_unit_field] != unit:
                        raise ValueError("Actual measure unit is missing or incompatible")
                    actual += number(row[c.actual_field])
                    ids.append(str(row[plan.child_key]))
                delta = actual - expected
                breach = {
                    "exceeds": delta > c.tolerance,
                    "below": delta < -c.tolerance,
                    "not_equal": abs(delta) > c.tolerance,
                }[c.operator]
                if breach:
                    violated.add(parent)
                    counts[c.name] += 1
                    totals[c.name][unit] += delta
                    findings.append(
                        Finding(
                            entity_id=parent,
                            comparison=c.name,
                            expected=expected,
                            actual=actual,
                            difference=delta,
                            unit=unit,
                            contributing_count=len(ids),
                            contributing_ids=sorted(ids)[:50],
                            evidence_truncated=len(ids) > 50 or len(rows) > 50,
                            transactions=rows[:50],
                        )
                    )
            except ValueError as error:
                gaps.append({"entity_id": parent, "comparison": c.name, "reason": str(error)})
    findings.sort(key=lambda f: (f.entity_id, f.comparison))
    return ReconciliationResult(
        plan=plan,
        plan_hash=sha256(plan.model_dump_json().encode()).hexdigest(),
        execution_id=batch.execution_id,
        executed_at=batch.executed_at,
        schema_version=batch.schema_version,
        query=batch.query,
        complete=not gaps,
        entities_checked=len(groups),
        violation_count=len(violated),
        comparison_counts=counts,
        difference_totals_by_unit={k: dict(v) for k, v in totals.items()},
        findings=findings[: plan.sample_limit],
        findings_truncated=len(findings) > plan.sample_limit,
        validation_gaps=gaps,
    )
