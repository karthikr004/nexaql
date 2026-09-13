"""Domain-independent contracts for evidence-backed reconciliation."""

from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Comparison(Contract):
    name: str
    expected_field: str
    actual_field: str
    expected_unit_field: str
    actual_unit_field: str
    tolerance: Decimal = Field(default=Decimal("0"), ge=0, allow_inf_nan=False)
    operator: Literal["exceeds", "below", "not_equal"] = "exceeds"


class ReconciliationPlan(Contract):
    rule_id: str
    rule_version: str
    parent_key: str
    child_key: str
    comparisons: list[Comparison] = Field(min_length=1)
    scope: str = Field(min_length=1)
    sample_limit: int = Field(default=50, ge=0, le=1000)

    @model_validator(mode="after")
    def unique_names(self):
        names = [c.name for c in self.comparisons]
        if len(names) != len(set(names)):
            raise ValueError("Comparison names must be unique")
        return self


class EvidenceBatch(Contract):
    """Trusted executor output. Never populate completeness from LLM assertions."""

    rows: list[dict[str, Any]]
    complete: bool
    query: str
    schema_version: str
    execution_id: str
    executed_at: str


class Finding(Contract):
    entity_id: str
    comparison: str
    expected: Decimal
    actual: Decimal
    difference: Decimal
    unit: str
    contributing_count: int
    contributing_ids: list[str]
    evidence_truncated: bool


class ReconciliationResult(Contract):
    plan: ReconciliationPlan
    plan_hash: str
    execution_id: str
    executed_at: str
    schema_version: str
    query: str
    complete: bool
    entities_checked: int
    violation_count: int
    comparison_counts: dict[str, int]
    difference_totals_by_unit: dict[str, dict[str, Decimal]]
    findings: list[Finding]
    findings_truncated: bool
    validation_gaps: list[dict[str, str]]
