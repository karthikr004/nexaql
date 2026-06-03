# Copyright (c) 2026-present NexaQL Contributors
"""
Registry of SQL system functions and constants allowed inside calc() expressions.

This serves three purposes:
 1. LLM reference -- surfaced in the system prompt so the agent knows exactly what is available.
 2. Validator awareness -- calc() expressions are checked against this list; unknown uppercase
    identifiers that look like SQL functions trigger a warning (not an error, to stay lenient).
 3. Autocomplete hints -- future IDE support can source suggestions from here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Literal, Optional

SystemFunctionKind = Literal["constant", "function"]
SystemFunctionCategory = Literal["datetime", "math", "null_handling", "type_cast"]
SystemFunctionReturn = Literal[
    "date", "time", "timestamp", "interval", "integer", "numeric", "text", "any"
]


@dataclass(frozen=True)
class SystemFunction:
    """A single SQL system function or constant recognised inside calc() expressions."""

    # SQL name as it must appear in the query (uppercase)
    name: str
    kind: SystemFunctionKind
    category: SystemFunctionCategory
    return_type: SystemFunctionReturn
    description: str
    # Full call syntax, shown to the LLM
    syntax: str
    # Concrete example inside a calc() expression
    example: str


# -- Registry ------------------------------------------------------------------

SYSTEM_FUNCTIONS: List[SystemFunction] = [
    # -- Date / time constants -------------------------------------------------
    SystemFunction(
        name="CURRENT_DATE",
        kind="constant",
        category="datetime",
        return_type="date",
        description="Today's date (no time component). Preferred for date arithmetic.",
        syntax="CURRENT_DATE",
        example="due_date - CURRENT_DATE  ->  integer days remaining",
    ),
    SystemFunction(
        name="CURRENT_TIME",
        kind="constant",
        category="datetime",
        return_type="time",
        description="Current time of day (with timezone). Rarely needed in procurement queries.",
        syntax="CURRENT_TIME",
        example="CURRENT_TIME  ->  e.g. 14:30:00+00",
    ),
    SystemFunction(
        name="CURRENT_TIMESTAMP",
        kind="constant",
        category="datetime",
        return_type="timestamp",
        description="Current date + time with timezone. Use when comparing against timestamp columns.",
        syntax="CURRENT_TIMESTAMP",
        example="CURRENT_TIMESTAMP - created_at  ->  interval since creation",
    ),
    SystemFunction(
        name="NOW",
        kind="function",
        category="datetime",
        return_type="timestamp",
        description="Equivalent to CURRENT_TIMESTAMP. Returns current date+time.",
        syntax="NOW()",
        example="NOW() - invoice_date  ->  interval since invoice was raised",
    ),
    # -- Date / time functions -------------------------------------------------
    SystemFunction(
        name="EXTRACT",
        kind="function",
        category="datetime",
        return_type="numeric",
        description="Extract a named part from a date/interval. Parts: YEAR, MONTH, DAY, HOUR, MINUTE, EPOCH.",
        syntax="EXTRACT(YEAR|MONTH|DAY|HOUR|EPOCH FROM date_or_interval)",
        example="EXTRACT(DAY FROM due_date - CURRENT_DATE)  ->  days as integer",
    ),
    SystemFunction(
        name="DATE_PART",
        kind="function",
        category="datetime",
        return_type="numeric",
        description="Equivalent to EXTRACT but uses string argument. EXTRACT is preferred.",
        syntax="DATE_PART('year'|'month'|'day'|'hour', date_field)",
        example="DATE_PART('month', invoice_date)  ->  month number 1-12",
    ),
    SystemFunction(
        name="DATE_TRUNC",
        kind="function",
        category="datetime",
        return_type="timestamp",
        description="Truncate a date to a given precision. Useful for grouping by month or year.",
        syntax="DATE_TRUNC('year'|'month'|'week'|'day', date_field)",
        example="DATE_TRUNC('month', invoice_date)  ->  first day of the invoice month",
    ),
    SystemFunction(
        name="AGE",
        kind="function",
        category="datetime",
        return_type="interval",
        description="Returns interval between two dates. AGE(end, start) or AGE(date) relative to today.",
        syntax="AGE(end_date, start_date)  or  AGE(date_field)",
        example="AGE(CURRENT_DATE, start_date)  ->  interval '2 years 3 months'",
    ),
    SystemFunction(
        name="TO_DATE",
        kind="function",
        category="datetime",
        return_type="date",
        description="Parse a string into a date using a format mask.",
        syntax="TO_DATE('YYYY-MM-DD', text_field)  or  TO_DATE(text_field, 'YYYY-MM-DD')",
        example="TO_DATE(date_string_field, 'YYYY-MM-DD')",
    ),
    # -- Math functions --------------------------------------------------------
    SystemFunction(
        name="ROUND",
        kind="function",
        category="math",
        return_type="numeric",
        description="Round a number to N decimal places.",
        syntax="ROUND(numeric_expr, decimal_places)",
        example="ROUND(unit_price * quantity, 2)  ->  line total rounded to 2dp",
    ),
    SystemFunction(
        name="CEIL",
        kind="function",
        category="math",
        return_type="integer",
        description="Round up to the nearest integer.",
        syntax="CEIL(numeric_expr)",
        example="CEIL(total_amount / 1000.0)  ->  number of 1K tranches",
    ),
    SystemFunction(
        name="FLOOR",
        kind="function",
        category="math",
        return_type="integer",
        description="Round down to the nearest integer.",
        syntax="FLOOR(numeric_expr)",
        example="FLOOR(days_elapsed / 30)  ->  complete months elapsed",
    ),
    SystemFunction(
        name="ABS",
        kind="function",
        category="math",
        return_type="numeric",
        description="Absolute value. Useful when the sign of a difference is not known in advance.",
        syntax="ABS(numeric_expr)",
        example="ABS(unit_price - agreed_unit_price)  ->  price variance (always positive)",
    ),
    SystemFunction(
        name="GREATEST",
        kind="function",
        category="math",
        return_type="numeric",
        description="Return the largest of two or more values. Useful to clamp negative results to zero.",
        syntax="GREATEST(expr1, expr2, ...)",
        example="GREATEST(due_date - CURRENT_DATE, 0)  ->  days left, clamped at 0",
    ),
    SystemFunction(
        name="LEAST",
        kind="function",
        category="math",
        return_type="numeric",
        description="Return the smallest of two or more values.",
        syntax="LEAST(expr1, expr2, ...)",
        example="LEAST(overcharge_pct, 100)  ->  cap percentage at 100",
    ),
    # -- Null handling ---------------------------------------------------------
    SystemFunction(
        name="COALESCE",
        kind="function",
        category="null_handling",
        return_type="any",
        description="Return the first non-NULL argument. Use to substitute a default when a field may be NULL.",
        syntax="COALESCE(field, default_value)",
        example="COALESCE(paid_amount, 0)  ->  0 when no payment recorded",
    ),
    SystemFunction(
        name="NULLIF",
        kind="function",
        category="null_handling",
        return_type="any",
        description="Return NULL if the two arguments are equal. Primarily used to prevent division-by-zero.",
        syntax="NULLIF(expr, zero_value)",
        example="paid_amount / NULLIF(total_amount, 0)  ->  safe division",
    ),
    # -- Type casts ------------------------------------------------------------
    SystemFunction(
        name="::INTEGER",
        kind="constant",
        category="type_cast",
        return_type="integer",
        description="PostgreSQL cast to integer. Append to any expression.",
        syntax="expr::INTEGER",
        example="(due_date - CURRENT_DATE)::INTEGER  ->  days as a plain integer",
    ),
    SystemFunction(
        name="::NUMERIC",
        kind="constant",
        category="type_cast",
        return_type="numeric",
        description="Cast to numeric (arbitrary precision decimal).",
        syntax="expr::NUMERIC",
        example="quantity::NUMERIC / total_quantity::NUMERIC  ->  decimal ratio",
    ),
    SystemFunction(
        name="::TEXT",
        kind="constant",
        category="type_cast",
        return_type="text",
        description="Cast to text string.",
        syntax="expr::TEXT",
        example="invoice_number::TEXT",
    ),
    SystemFunction(
        name="::DATE",
        kind="constant",
        category="type_cast",
        return_type="date",
        description="Cast a timestamp to a plain date, dropping the time component.",
        syntax="timestamp_field::DATE",
        example="created_at::DATE  ->  date without time",
    ),
]

# -- Lookup helpers ------------------------------------------------------------

# Set of all known system function / constant names (uppercase).
SYSTEM_FUNCTION_NAMES: set[str] = {
    f.name.lstrip(":").upper() for f in SYSTEM_FUNCTIONS
}


def get_system_function(name: str) -> Optional[SystemFunction]:
    """Retrieve a function definition by name (case-insensitive)."""
    upper = name.upper()
    for f in SYSTEM_FUNCTIONS:
        if f.name.upper() == upper:
            return f
    return None


def get_by_category(category: SystemFunctionCategory) -> List[SystemFunction]:
    """Returns all functions in a given category."""
    return [f for f in SYSTEM_FUNCTIONS if f.category == category]


# -- Prompt rendering ----------------------------------------------------------


def system_functions_to_prompt_text() -> str:
    """
    Generates the system-prompt section listing all available system functions.
    Called by build_system_prompt() so the LLM always sees the current registry.
    """
    categories: list[tuple[SystemFunctionCategory, str]] = [
        ("datetime", "Date / Time constants and functions"),
        ("math", "Math functions"),
        ("null_handling", "Null-handling functions"),
        ("type_cast", "Type casts (PostgreSQL :: syntax)"),
    ]

    lines: list[str] = []

    for cat_id, label in categories:
        funcs = get_by_category(cat_id)
        if not funcs:
            continue
        lines.append(f"  -- {label} --")
        for f in funcs:
            lines.append(f"  {f.syntax:<52}  {f.description}")
            lines.append(f"    Example: {f.example}")
        lines.append("")

    return "\n".join(lines)


# -- Validator helper ----------------------------------------------------------


def find_unknown_functions(expr: str) -> List[str]:
    """
    Given a raw calc() expression string (as produced by the parser),
    returns any uppercase IDENT tokens that look like SQL function calls
    but are NOT in the known registry.

    These are returned as warnings, not errors -- the SQL engine may still
    accept them (e.g. vendor-specific functions), but the LLM is likely
    hallucinating.
    """
    # Match uppercase-only words followed by "(" -- these look like function calls
    candidates = re.findall(r"\b([A-Z_][A-Z0-9_]*)\s*\(", expr)
    return [name for name in candidates if name not in SYSTEM_FUNCTION_NAMES]
