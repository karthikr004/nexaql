"""Resolve identifiers in calculated expressions against ontology fields."""

import re

# SQL expression grammar words are not column references.
KEYWORDS = set(
    """AND OR NOT NULL TRUE FALSE CASE WHEN THEN ELSE END DISTINCT ALL
AS CAST EXTRACT FROM IN IS BETWEEN LIKE ILIKE OVER PARTITION BY ORDER ASC DESC
NULLS FIRST LAST ROWS RANGE GROUPS UNBOUNDED PRECEDING FOLLOWING CURRENT ROW
FILTER WHERE INTERVAL YEAR MONTH DAY HOUR MINUTE SECOND WEEK QUARTER DOW DOY
EPOCH DATE TIME TIMESTAMP TIMESTAMPTZ AT ZONE NUMERIC DECIMAL INTEGER INT BIGINT
SMALLINT FLOAT DOUBLE PRECISION REAL TEXT VARCHAR CHAR BOOLEAN SIGNED UNSIGNED
BOTH LEADING TRAILING FOR WITH WITHOUT TIMEZONE""".split()
)
TOKEN = re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|[A-Za-z_][A-Za-z_0-9]*|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[^\s]")


def expression_errors(expr, node, ontology):
    tokens = TOKEN.findall(expr)
    errors = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if not (re.match(r"^[A-Za-z_]", token) or token.startswith('"')):
            i += 1
            continue
        name = token.strip('"')
        if i + 1 < len(tokens) and tokens[i + 1] == "(":
            i += 1  # Function names are checked separately.
            continue
        if i + 2 < len(tokens) and tokens[i + 1] == ".":
            field = tokens[i + 2].strip('"')
            edge = (getattr(node, "edges", None) or {}).get(name)
            target = ontology.nodes.get(edge.node) if edge else None
            if target is None or field not in target.fields:
                errors.append(f"Unknown expression reference '{name}.{field}'")
            i += 3
            continue
        if name not in node.fields and (token.startswith('"') or name.upper() not in KEYWORDS):
            errors.append(
                f"Unknown expression field '{name}'. Use a declared field or an edge.field reference; output aliases are not source fields"
            )
        i += 1
    return errors
