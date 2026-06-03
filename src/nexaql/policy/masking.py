# Copyright (c) 2026-present NexaQL Contributors
"""Post-query result masking -- applies PII redaction strategies to query results."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, List


@dataclass
class MaskRule:
    column_alias: str  # e.g. "customer__email"
    strategy: str      # "email", "phone", "redact", "hash", "truncate"


def mask_results(rows: List[dict], mask_rules: List[MaskRule]) -> List[dict]:
    """Apply masking to result rows. Returns new list (does not mutate input)."""
    if not mask_rules:
        return list(rows)

    # Build a lookup: column_alias -> strategy
    rules_map = {rule.column_alias: rule.strategy for rule in mask_rules}

    result: List[dict] = []
    for row in rows:
        masked_row = dict(row)
        for col, strategy in rules_map.items():
            if col in masked_row:
                masked_row[col] = mask_value(masked_row[col], strategy)
        result.append(masked_row)
    return result


def mask_value(value: Any, strategy: str) -> Any:
    """Mask a single value using the given strategy."""
    if value is None:
        return None

    s = str(value)

    if strategy == "email":
        # "alice@example.com" -> "a***@example.com"
        at_idx = s.find("@")
        if at_idx > 0:
            return s[0] + "***" + s[at_idx:]
        return "***"

    if strategy == "phone":
        # "+1234567890" -> "+1***890"
        if len(s) > 5:
            return s[:2] + "***" + s[-3:]
        return "***"

    if strategy == "redact":
        return "[REDACTED]"

    if strategy == "hash":
        return hashlib.sha256(s.encode()).hexdigest()[:8]

    if strategy == "truncate":
        # "Alice Johnson" -> "Ali***"
        if len(s) > 3:
            return s[:3] + "***"
        return s + "***"

    # Unknown strategy falls back to redact
    return "[REDACTED]"
