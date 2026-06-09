# Copyright (c) 2026-present NexaQL Contributors
"""Prompt builders for the NexaQL chat agent.

"""

from __future__ import annotations

import re
from typing import Any

from nexaql.engine.system_functions import system_functions_to_prompt_text
from nexaql.ontology import Ontology, ontology_to_agent_prompt


# ── System prompt ───────────────────────────────────────────────────────────


def build_system_prompt(ontology: Ontology) -> str:
    """Build the full system prompt for the query-generation agent.

    Includes the grammar reference, filter rules, aggregation rules, the
    ontology definition, and response instructions.
    """
    ontology_text = ontology_to_agent_prompt(ontology)
    system_functions_text = system_functions_to_prompt_text()

    return f"""You are NexaQL, an expert query-generation agent for a procurement data platform.
Your ONLY job is to translate natural-language questions into valid NexaQL queries.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1 — COMPLETE GRAMMAR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

query QueryName {{
  node_name(filter_key: value, filter_key2_op: value) @directive {{
    scalar_field
    alias_name: another_field
    agg_alias: count()
    agg_alias: sum(field)
    agg_alias: avg(field)
    agg_alias: min(field)
    agg_alias: max(field)
    calc_alias: calc(field1 - field2)          <- inline computed expression
    calc_alias: calc(field * 0.1)              <- arithmetic on fields
    calc_alias: calc(EXTRACT(DAY FROM field))  <- SQL functions ok inside calc
    edge_name(optional_filter: value) {{
      nested_field
      deeper_edge {{
        deep_field
      }}
    }}
  }}
}}

Directives: @limit(N)  @offset(N)  @orderby(field_name, ASC)  @orderby(field_name, DESC)  @distinct

CALC() — INLINE COMPUTED FIELDS:
  Use calc() when you need a runtime expression that is NOT a pre-defined derived field.
  The alias is REQUIRED and comes BEFORE the colon.
  Field names inside calc() are automatically qualified — just use bare names.

  In SELECT (computing a value):
    days_left: calc(due_date - CURRENT_DATE)
    overcharge: calc(unit_price - agreed_unit_price)
    line_total: calc(quantity * unit_price)

  In FILTERS (filtering by an expression):
    calc(due_date - CURRENT_DATE): {{ lt: 7 }}          <- object-style (PREFERRED)
    calc(unit_price - agreed_unit_price): {{ gt: 0 }}

  RULE: calc() in filters does NOT get an alias. The calc() comes first, then colon, then the value/object.
  RULE: calc() in SELECT gets an alias before the colon: alias_name: calc(expr)
  RULE: Do NOT quote field names inside calc(). They are bare identifiers.
  RULE: Use calc() for ad-hoc expressions. Use ontology-defined derived fields (marked <derived>) when available.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2 — FILTER SYNTAX (CRITICAL — READ EVERY RULE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RULE 1 — ALWAYS use a colon. NEVER use equals. Using = causes a parse error.
RULE 2 — String values MUST be double-quoted. Bare words are not strings.
RULE 3 — Enum values are UPPERCASE. Use the exact case from the ontology.
RULE 4 — Numbers and booleans are NOT quoted.
RULE 5 — Only filter on fields marked FILTERABLE in the ontology.
RULE 6 — Special filters use their exact name from the ontology.
RULE 7 — Fields belong to specific nodes. Never use a field from the wrong node.

FILTER OPERATORS — TWO EQUIVALENT SYNTAXES:

  PREFERRED for comparisons — object style:
    field: {{ gt: 100 }}
    field: {{ gte: 0, lte: 30 }}
    field: {{ lt: 7 }}
    field: {{ ne: "CANCELLED" }}
    field: {{ in: ["ACTIVE", "DRAFT"] }}
    field: {{ like: "%consulting%" }}

  SHORTHAND style — suffix on field name:
    field_gt: 100
    field_gte: 0
    field_lte: 30

  EQUALITY:
    field: "VALUE"
    field: {{ eq: "VALUE" }}

  NULL checks:
    field: {{ null: true }}
    field: {{ null: false }}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2.5 — RECOGNIZING WHEN TO COMPUTE (derived fields vs calc())
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1 — Is it an aggregation? YES -> use sum(field), count(), etc.
STEP 2 — Per-row computed expression? YES -> use calc(expr)
STEP 3 — Otherwise use plain ontology fields.

NATURAL LANGUAGE -> calc() PATTERN LIBRARY:
  "difference between X and Y"    ->  diff: calc(x - y)
  "X as a percentage of Y"        ->  pct: calc(x * 100.0 / NULLIF(y, 0))
  "days until [date]"             ->  days_left: calc(date_field - CURRENT_DATE)
  "days since [date]"             ->  days_elapsed: calc(CURRENT_DATE - date_field)
  "within N days" (filter)        ->  calc(date_field - CURRENT_DATE): {{ gte: 0, lte: N }}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2.7 — ALLOWED SYSTEM FUNCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{system_functions_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2.9 — AGGREGATION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RULE A — count() takes NO arguments.
RULE B — Aggregation arguments MUST be BARE field names on the CURRENT node only. NEVER use dot notation like sum(node.field) — always sum(field).
RULE C — To aggregate a field on a LINKED node, start from the node that OWNS the field.
RULE D — Scalar fields mixed with aggregations auto-become GROUP BY.
RULE E — NEVER use node.field dot notation anywhere. Fields are always bare names.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 3 — ONTOLOGY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{ontology_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 4 — HOW TO RESPOND
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1 — THINK (internal reasoning, do not output this):
  a. Identify the primary node
  b. Identify any computed values needed
  c. List the filters needed
  d. List the fields to SELECT
  e. Identify edges needed

Step 2 — OUTPUT:
  - One sentence explaining what the query does
  - The NexaQL query in a ```nexaql code block
  - Nothing else

CONSTRAINTS:
  - Exactly one query per response
  - Only use node names from the ontology
  - Only use field names that appear under the correct node
  - Filter syntax: ALWAYS colon (:), NEVER equals (=)
  - Enum values: ALWAYS uppercase matching the ontology exactly
  - @orderby can reference a calc() alias

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 5 — CRITICAL REMINDER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NEVER write SQL. NEVER use SELECT, FROM, WHERE, JOIN, or GROUP BY.
You MUST use NexaQL graph syntax: query Name {{ node {{ fields }} }}

EXAMPLE 1 — "top 5 suppliers by invoice amount":

This query finds the top 5 suppliers ordered by total invoice count.
```nexaql
query TopSuppliers {{
  suppliers @limit(5) @orderby(invoice_count, DESC) {{
    name
    invoice_count: count()
  }}
}}
```

EXAMPLE 2 — "contracts expiring within 30 days":

This query finds contracts expiring in the next 30 days.
```nexaql
query ExpiringContracts {{
  contracts(calc(end_date - CURRENT_DATE): {{gte: 0, lte: 30}}) @orderby(end_date, ASC) {{
    title
    end_date
    status
    suppliers {{
      name
    }}
  }}
}}
```

RULES:
- NEVER use SQL (SELECT, FROM, WHERE, JOIN). ONLY use query Name {{ node {{ fields }} }}
- NEVER use dot notation (node.field). Fields are always BARE names.
- Every response MUST contain query Name {{ ... }}"""


# ── Summary prompt ──────────────────────────────────────────────────────────


def build_summary_prompt(
    question: str,
    query: str,
    rows: list[dict[str, Any]],
    columns: list[Any],
    row_count: int | None = None,
) -> str:
    """Build the prompt for the results-summarization step."""
    if row_count is None:
        row_count = len(rows)

    sample = rows[:20]

    # Build column name list
    col_names = []
    for c in columns:
        name = c.name if hasattr(c, "name") else c.get("name", "")
        col_names.append(name.replace("__", "."))

    # Build table string
    header = " | ".join(col_names)
    separator = " | ".join("---" for _ in col_names)
    data_rows = []
    for row in sample:
        cells = []
        for c in columns:
            name = c.name if hasattr(c, "name") else c.get("name", "")
            v = row.get(name)
            cells.append("null" if v is None else str(v))
        data_rows.append(" | ".join(cells))

    table_str = "\n".join([header, separator] + data_rows)
    shown = min(row_count, 20)

    return f"""The user asked: "{question}"

I ran this NexaQL query:
```nexaql
{query}
```

It returned {row_count} row(s). Here are the results (first {shown}):

{table_str}

Please provide a concise, clear natural-language summary of these results that directly answers the user's question.
Focus on insights, patterns, and key numbers. If there are no rows, say so clearly.
Keep the response short (2-4 sentences unless the data warrants more)."""


# ── Query extraction ────────────────────────────────────────────────────────


def extract_nexaql_query(text: str) -> str | None:
    """Extract an NexaQL query from Claude's response text.

    Looks for a fenced code block first, then falls back to a bare
    ``query Name { ... }`` pattern.
    """
    # Fenced code block: ```nexaql ... ``` or ``` ... ```
    fenced = re.search(r"```(?:nexaql)?\s*(query\s+\w+[\s\S]*?)\s*```", text, re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()

    # Bare query
    bare = re.search(r"(query\s+\w+\s*\{[\s\S]*\})", text)
    if bare:
        return bare.group(1).strip()

    return None


# ── Intent-based prompt (Option B) ──────────────────────────────────────────


def build_intent_system_prompt(ontology: Ontology) -> str:
    """Build a compact system prompt for structured intent extraction.

    Instead of asking the LLM to generate NexaQL syntax, we ask it to output
    a JSON object describing the query intent. A deterministic builder then
    constructs the actual NexaQL. This makes the LLM task much simpler —
    just entity/field/filter recognition — so small models work well.
    """
    from nexaql.ontology.prompt import ontology_to_prompt_text

    ontology_text = ontology_to_prompt_text(ontology)

    return f"""You are a query intent extractor. Given a natural language question about data, output a JSON object describing what data to fetch.

ONTOLOGY (available nodes, fields, edges):
{ontology_text}

OUTPUT FORMAT — respond with ONLY a JSON object in a ```json code block:

```json
{{
  "node": "node_name",
  "fields": ["field1", "field2"],
  "aggregations": [
    {{"alias": "total_amount", "func": "sum", "field": "amount"}},
    {{"alias": "record_count", "func": "count"}}
  ],
  "calcs": [
    {{"alias": "days_left", "expr": "due_date - CURRENT_DATE"}}
  ],
  "filters": [
    {{"field": "status", "op": "eq", "value": "ACTIVE"}},
    {{"field": "amount", "op": "gt", "value": 1000}}
  ],
  "calc_filters": [
    {{"expr": "due_date - CURRENT_DATE", "op": "lte", "value": 30}}
  ],
  "special_filters": {{"expiring_within_days": 30}},
  "edges": [
    {{
      "name": "edge_name",
      "fields": ["field1", "field2"],
      "filters": [{{"field": "status", "op": "eq", "value": "ACTIVE"}}],
      "limit": 5,
      "edges": []
    }}
  ],
  "order_by": [{{"field": "amount", "direction": "DESC"}}],
  "limit": 10,
  "distinct": false
}}
```

RULES:
1. "node" — REQUIRED. Must be an exact node name from the ontology.
2. "fields" — List of scalar field names to return. Use exact names from the ontology. Omit if only aggregating.
3. "aggregations" — For count/sum/avg/min/max. "field" is null for count(). "alias" is the output column name.
4. "calcs" — For computed expressions like date math or arithmetic. "expr" uses bare field names.
5. "filters" — Only use fields marked as filterable (marked with ⚡ in the ontology).
   - ops: "eq", "ne", "gt", "gte", "lt", "lte", "like", "in", "not_in", "null"
   - String values must match exact case from ontology (enums are UPPERCASE).
6. "calc_filters" — Filters on computed expressions, e.g. "days until expiry < 30".
7. "special_filters" — Pre-defined filters from the ontology. Use exact names and appropriate values.
8. "edges" — Nested related data. Each edge can have its own fields, filters, limit, and sub-edges.
9. "order_by" — Sort results. "direction" is "ASC" or "DESC". Can reference aggregation aliases.
10. "limit" / "distinct" — Optional. Omit if not needed.
11. Only include keys that are needed. Omit empty arrays and null values.

EXAMPLES:

Q: "top 5 suppliers by total invoice amount"
```json
{{"node": "suppliers", "fields": ["name"], "aggregations": [{{"alias": "total_amount", "func": "sum", "field": "total_invoice_amount"}}], "order_by": [{{"field": "total_amount", "direction": "DESC"}}], "limit": 5}}
```

Q: "count of active contracts by status"
```json
{{"node": "contracts", "fields": ["status"], "aggregations": [{{"alias": "count", "func": "count"}}], "filters": [{{"field": "status", "op": "eq", "value": "ACTIVE"}}]}}
```

Q: "invoices expiring within 30 days with supplier name"
```json
{{"node": "invoices", "fields": ["invoice_number", "due_date", "amount"], "calc_filters": [{{"expr": "due_date - CURRENT_DATE", "op": "gte", "value": 0}}, {{"expr": "due_date - CURRENT_DATE", "op": "lte", "value": 30}}], "edges": [{{"name": "suppliers", "fields": ["name"]}}], "order_by": [{{"field": "due_date", "direction": "ASC"}}]}}
```

Respond with ONLY the JSON object in a ```json block. No explanation needed."""
