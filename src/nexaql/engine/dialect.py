# Copyright (c) 2026-present NexaQL Contributors
"""
Dialect-aware calc() expression translator.

The calc() expression string produced by the parser is "canonical NexaQL expression" --
it uses PostgreSQL-compatible syntax as the canonical form. This module transforms it into
the equivalent expression for the target query dialect.

Translation strategy:
  1. Type-cast pass  -- replaces PostgreSQL ``::TYPE`` suffix syntax with ``CAST(expr AS TYPE)``
  2. Function-call pass -- rewrites function calls using per-dialect templates
  3. Date-arithmetic pass -- detects ``date_field +/- CURRENT_DATE/NOW()`` patterns and
     rewrites to dialect-specific date-diff functions where needed

All other arithmetic (``+``, ``-``, ``*``, ``/`` between non-date expressions) is universal
and passes through unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Tuple

# -- Dialect registry ----------------------------------------------------------

QueryDialect = Literal[
    "postgresql",  # Default -- canonical form, no transformation
    "presto",      # Presto / Trino (Meta / AWS Athena)
    "bigquery",    # Google BigQuery (standard SQL with extensions)
    "snowflake",   # Snowflake
    "spark",       # Apache Spark SQL / Databricks
    "mysql",       # MySQL / MariaDB
    "mssql",       # Microsoft SQL Server / Azure Synapse
]

DIALECT_LABELS: Dict[str, str] = {
    "postgresql": "PostgreSQL",
    "presto": "Presto / Trino",
    "bigquery": "BigQuery",
    "snowflake": "Snowflake",
    "spark": "Spark SQL",
    "mysql": "MySQL",
    "mssql": "SQL Server",
}

# -- Function translation table ------------------------------------------------
#
# Each entry maps a canonical function name to dialect-specific templates.
# Template variables:
#   $1, $2, ...  -- positional arguments from the original call
#   $PART        -- for EXTRACT, the date part keyword (DAY, MONTH, YEAR, ...)
#   $EXPR        -- for EXTRACT, the expression after FROM
#
# If a dialect is absent, the canonical form is used as-is.


@dataclass(frozen=True)
class _FunctionTranslation:
    """How to parse arguments -- 'standard' = comma-separated, 'extract' = 'PART FROM expr'."""

    parse_mode: Literal["standard", "extract", "cast"]
    dialects: Dict[str, str]


_FUNCTION_TRANSLATIONS: Dict[str, _FunctionTranslation] = {
    # -- NOW() -----------------------------------------------------------------
    "NOW": _FunctionTranslation(
        parse_mode="standard",
        dialects={
            "postgresql": "NOW()",
            "presto": "current_timestamp",
            "bigquery": "CURRENT_TIMESTAMP()",
            "snowflake": "CURRENT_TIMESTAMP()",
            "spark": "current_timestamp()",
            "mysql": "NOW()",
            "mssql": "GETDATE()",
        },
    ),
    # -- EXTRACT ---------------------------------------------------------------
    "EXTRACT": _FunctionTranslation(
        parse_mode="extract",
        dialects={
            "postgresql": "EXTRACT($PART FROM $EXPR)",
            "presto": "$PART_PRESTO($EXPR)",
            "bigquery": "EXTRACT($PART FROM $EXPR)",
            "snowflake": "EXTRACT($PART FROM $EXPR)",
            "spark": "EXTRACT($PART FROM $EXPR)",
            "mysql": "EXTRACT($PART FROM $EXPR)",
            "mssql": "DATEPART($PART_LOWER, $EXPR)",
        },
    ),
    # -- DATE_TRUNC ------------------------------------------------------------
    "DATE_TRUNC": _FunctionTranslation(
        parse_mode="standard",
        dialects={
            "postgresql": "DATE_TRUNC($1, $2)",
            "presto": "date_trunc($1, $2)",
            "bigquery": "DATE_TRUNC($2, $UNIT_BQ)",
            "snowflake": "DATE_TRUNC($1, $2)",
            "spark": "date_trunc($1, $2)",
            "mysql": "DATE_FORMAT($2, $MYSQL_FMT)",
            "mssql": "DATETRUNC($UNIT_MSSQL, $2)",
        },
    ),
    # -- DATE_PART -------------------------------------------------------------
    "DATE_PART": _FunctionTranslation(
        parse_mode="standard",
        dialects={
            "postgresql": "DATE_PART($1, $2)",
            "presto": "$PART_PRESTO($2)",
            "bigquery": "EXTRACT($PART_UPPER FROM $2)",
            "snowflake": "DATE_PART($1, $2)",
            "spark": "date_part($1, $2)",
            "mysql": "EXTRACT($PART_UPPER FROM $2)",
            "mssql": "DATEPART($PART_LOWER, $2)",
        },
    ),
    # -- AGE -------------------------------------------------------------------
    "AGE": _FunctionTranslation(
        parse_mode="standard",
        dialects={
            "postgresql": "AGE($1, $2)",
            "presto": "date_diff('day', $2, $1)",
            "bigquery": "DATE_DIFF($1, $2, DAY)",
            "snowflake": "DATEDIFF('day', $2, $1)",
            "spark": "datediff($1, $2)",
            "mysql": "DATEDIFF($1, $2)",
            "mssql": "DATEDIFF(day, $2, $1)",
        },
    ),
    # -- TO_DATE ---------------------------------------------------------------
    "TO_DATE": _FunctionTranslation(
        parse_mode="standard",
        dialects={
            "postgresql": "TO_DATE($1, $2)",
            "presto": "date_parse($1, $2)",
            "bigquery": "PARSE_DATE($2, $1)",
            "snowflake": "TO_DATE($1, $2)",
            "spark": "to_date($1, $2)",
            "mysql": "STR_TO_DATE($1, $2)",
            "mssql": "CONVERT(DATE, $1, $2)",
        },
    ),
    # -- ROUND -----------------------------------------------------------------
    "ROUND": _FunctionTranslation(
        parse_mode="standard",
        dialects={
            "postgresql": "ROUND($1, $2)",
            "presto": "ROUND($1, $2)",
            "bigquery": "ROUND($1, $2)",
            "snowflake": "ROUND($1, $2)",
            "spark": "ROUND($1, $2)",
            "mysql": "ROUND($1, $2)",
            "mssql": "ROUND($1, $2)",
        },
    ),
    # -- COALESCE --------------------------------------------------------------
    "COALESCE": _FunctionTranslation(
        parse_mode="standard",
        dialects={
            "postgresql": "COALESCE($ARGS)",
            "presto": "COALESCE($ARGS)",
            "bigquery": "COALESCE($ARGS)",
            "snowflake": "COALESCE($ARGS)",
            "spark": "COALESCE($ARGS)",
            "mysql": "COALESCE($ARGS)",
            "mssql": "COALESCE($ARGS)",
        },
    ),
    # -- NULLIF ----------------------------------------------------------------
    "NULLIF": _FunctionTranslation(
        parse_mode="standard",
        dialects={
            "postgresql": "NULLIF($1, $2)",
            "presto": "NULLIF($1, $2)",
            "bigquery": "NULLIF($1, $2)",
            "snowflake": "NULLIF($1, $2)",
            "spark": "NULLIF($1, $2)",
            "mysql": "NULLIF($1, $2)",
            "mssql": "NULLIF($1, $2)",
        },
    ),
}

# -- Cast translation ----------------------------------------------------------

# Maps PostgreSQL cast type names to dialect-appropriate CAST(x AS TYPE) forms.
_CAST_TYPE_MAP: Dict[str, Dict[str, str]] = {
    "INTEGER": {
        "postgresql": "INTEGER",
        "presto": "INTEGER",
        "bigquery": "INT64",
        "snowflake": "INTEGER",
        "spark": "INT",
        "mysql": "SIGNED",
        "mssql": "INT",
    },
    "INT": {
        "postgresql": "INTEGER",
        "presto": "INTEGER",
        "bigquery": "INT64",
        "snowflake": "INTEGER",
        "spark": "INT",
        "mysql": "SIGNED",
        "mssql": "INT",
    },
    "BIGINT": {
        "postgresql": "BIGINT",
        "presto": "BIGINT",
        "bigquery": "INT64",
        "snowflake": "BIGINT",
        "spark": "BIGINT",
        "mysql": "SIGNED",
        "mssql": "BIGINT",
    },
    "NUMERIC": {
        "postgresql": "NUMERIC",
        "presto": "DECIMAL",
        "bigquery": "NUMERIC",
        "snowflake": "NUMBER",
        "spark": "DECIMAL",
        "mysql": "DECIMAL",
        "mssql": "NUMERIC",
    },
    "FLOAT": {
        "postgresql": "FLOAT8",
        "presto": "DOUBLE",
        "bigquery": "FLOAT64",
        "snowflake": "FLOAT",
        "spark": "DOUBLE",
        "mysql": "DECIMAL",
        "mssql": "FLOAT",
    },
    "TEXT": {
        "postgresql": "TEXT",
        "presto": "VARCHAR",
        "bigquery": "STRING",
        "snowflake": "VARCHAR",
        "spark": "STRING",
        "mysql": "CHAR",
        "mssql": "NVARCHAR(MAX)",
    },
    "VARCHAR": {
        "postgresql": "VARCHAR",
        "presto": "VARCHAR",
        "bigquery": "STRING",
        "snowflake": "VARCHAR",
        "spark": "STRING",
        "mysql": "CHAR",
        "mssql": "NVARCHAR",
    },
    "DATE": {
        "postgresql": "DATE",
        "presto": "DATE",
        "bigquery": "DATE",
        "snowflake": "DATE",
        "spark": "DATE",
        "mysql": "DATE",
        "mssql": "DATE",
    },
    "TIMESTAMP": {
        "postgresql": "TIMESTAMP",
        "presto": "TIMESTAMP",
        "bigquery": "TIMESTAMP",
        "snowflake": "TIMESTAMP",
        "spark": "TIMESTAMP",
        "mysql": "DATETIME",
        "mssql": "DATETIME2",
    },
    "BOOLEAN": {
        "postgresql": "BOOLEAN",
        "presto": "BOOLEAN",
        "bigquery": "BOOL",
        "snowflake": "BOOLEAN",
        "spark": "BOOLEAN",
        "mysql": "UNSIGNED",
        "mssql": "BIT",
    },
}

# -- Date arithmetic patterns --------------------------------------------------
#
# PostgreSQL: ``date_col - CURRENT_DATE`` -> integer (days)
# Other dialects need explicit date-diff functions.
#
# We detect:  ``<expr> - CURRENT_DATE``
#             ``CURRENT_DATE - <expr>``
#             ``<expr> - NOW()``  etc.
#
# This is done as a final regex pass after function translation.

_DATE_DIFF_BY_DIALECT: Dict[str, str] = {
    "postgresql": "($A - $B)",
    "presto": "date_diff('day', $B, $A)",
    "bigquery": "DATE_DIFF($A, $B, DAY)",
    "snowflake": "DATEDIFF('day', $B, $A)",
    "spark": "datediff($A, $B)",
    "mysql": "DATEDIFF($A, $B)",
    "mssql": "DATEDIFF(day, $B, $A)",
}


# -- Utilities -----------------------------------------------------------------


def _extract_args(src: str, start: int) -> Tuple[List[str], int]:
    """
    Given a position just after the opening ``(`` of a function call,
    extract the comma-separated argument strings respecting nested parens.
    Returns the args list and the offset just after the closing ``)``.
    """
    args: List[str] = []
    depth = 1
    current: List[str] = []
    i = start

    while i < len(src) and depth > 0:
        ch = src[i]
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            if depth == 0:
                args.append("".join(current))
                break
            else:
                current.append(ch)
        elif ch == "," and depth == 1:
            args.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1

    return [a.strip() for a in args], i + 1


# -- Main translator -----------------------------------------------------------


class CalcDialectTranslator:
    """Translates a calc() expression from canonical (PostgreSQL) form to a target dialect."""

    def __init__(self, dialect: str = "postgresql") -> None:
        self._dialect = dialect

    @property
    def dialect(self) -> str:
        return self._dialect

    def translate(self, expr: str) -> str:
        """
        Translate a calc() expression (field refs already expanded) to the target dialect.
        Returns the expression unchanged for ``postgresql`` (canonical form).
        """
        if self._dialect == "postgresql":
            return expr

        out = expr

        # Pass 1 -- type casts: expr::TYPE -> CAST(expr AS TYPE) / dialect equivalent
        out = self._translate_casts(out)

        # Pass 2 -- function calls
        out = self._translate_functions(out)

        # Pass 3 -- date arithmetic (expr +/- CURRENT_DATE / NOW())
        out = self._translate_date_arithmetic(out)

        return out

    # -- Pass 1: type casts ----------------------------------------------------

    def _translate_casts(self, expr: str) -> str:
        out = expr

        # Form A: (expr)::TYPE -- parenthesised expression with cast suffix
        def _replace_paren_cast(m: re.Match) -> str:
            inner = m.group(1)
            cast_type = m.group(2)
            dialect_type = (
                _CAST_TYPE_MAP.get(cast_type.upper(), {}).get(self._dialect)
                or cast_type.upper()
            )
            return f"CAST({inner} AS {dialect_type})"

        out = re.sub(
            r"\(([^()]+)\)\s*::\s*([A-Za-z][A-Za-z0-9]*)",
            _replace_paren_cast,
            out,
        )

        # Form B: word.word::TYPE or word::TYPE -- simple identifier or qualified name
        def _replace_ident_cast(m: re.Match) -> str:
            ident = m.group(1)
            cast_type = m.group(2)
            dialect_type = (
                _CAST_TYPE_MAP.get(cast_type.upper(), {}).get(self._dialect)
                or cast_type.upper()
            )
            return f"CAST({ident} AS {dialect_type})"

        out = re.sub(
            r"([\w.]+)\s*::\s*([A-Za-z][A-Za-z0-9]*)",
            _replace_ident_cast,
            out,
        )

        return out

    # -- Pass 2: function calls ------------------------------------------------

    def _translate_functions(self, expr: str) -> str:
        out = expr

        for fn_name, defn in _FUNCTION_TRANSLATIONS.items():
            dialect_template = defn.dialects.get(self._dialect)
            if dialect_template is None:
                continue
            # Skip if this dialect uses the same template as postgresql
            if dialect_template == defn.dialects.get("postgresql"):
                continue

            if defn.parse_mode == "standard":
                out = self._translate_standard_function(out, fn_name, dialect_template)
            elif defn.parse_mode == "extract":
                out = self._translate_extract(out, dialect_template)

        return out

    def _translate_standard_function(
        self, expr: str, fn_name: str, template: str
    ) -> str:
        """
        Translates calls like FN(a, b, c) to dialect form.

        Uses a manual index-tracking loop so the ENTIRE function call -- including
        args and closing paren -- is replaced atomically.
        """
        pattern = re.compile(r"\b" + re.escape(fn_name) + r"\s*\(", re.IGNORECASE)
        result: List[str] = []
        last_index = 0

        for match in pattern.finditer(expr):
            if match.start() < last_index:
                # This match overlaps with a region we already consumed
                continue

            args_start = match.end()
            args, end_offset = _extract_args(expr, args_start)

            # Append everything before this function call
            result.append(expr[last_index : match.start()])

            # Build the translated call
            translated = template

            translated = translated.replace("$ARGS", ", ".join(args))

            for i, arg in enumerate(args):
                # Replace $1, $2, ... but not $10 when replacing $1
                translated = re.sub(
                    re.escape(f"${i + 1}") + r"(?!\d)", arg.strip(), translated
                )

            if "$UNIT_BQ" in translated and args:
                translated = translated.replace(
                    "$UNIT_BQ", args[0].replace("'", "").replace('"', "").upper()
                )
            if "$UNIT_MSSQL" in translated and args:
                translated = translated.replace(
                    "$UNIT_MSSQL", args[0].replace("'", "").replace('"', "").lower()
                )
            if "$MYSQL_FMT" in translated and args:
                unit = args[0].replace("'", "").replace('"', "").lower()
                fmt_map = {
                    "year": "'%Y-01-01'",
                    "month": "'%Y-%m-01'",
                    "day": "'%Y-%m-%d'",
                    "week": "'%Y-%m-%d'",
                }
                translated = translated.replace(
                    "$MYSQL_FMT", fmt_map.get(unit, "'%Y-%m-%d'")
                )
            if "$PART_PRESTO" in translated and args:
                translated = translated.replace(
                    "$PART_PRESTO",
                    args[0].replace("'", "").replace('"', "").lower(),
                )
            if "$PART_UPPER" in translated and args:
                translated = translated.replace(
                    "$PART_UPPER",
                    args[0].replace("'", "").replace('"', "").upper(),
                )
            if "$PART_LOWER" in translated and args:
                translated = translated.replace(
                    "$PART_LOWER",
                    args[0].replace("'", "").replace('"', "").lower(),
                )

            result.append(translated)
            last_index = end_offset

        result.append(expr[last_index:])
        return "".join(result)

    def _translate_extract(self, expr: str, template: str) -> str:
        """Translates EXTRACT(PART FROM expr) -- uses special FROM keyword syntax, not commas."""
        pattern = re.compile(r"\bEXTRACT\s*\(\s*(\w+)\s+FROM\s*", re.IGNORECASE)
        result: List[str] = []
        last_index = 0

        for match in pattern.finditer(expr):
            if match.start() < last_index:
                continue

            part = match.group(1)
            expr_start = match.end()

            # Collect the inner expression up to the matching closing paren
            depth = 1
            i = expr_start
            while i < len(expr) and depth > 0:
                if expr[i] == "(":
                    depth += 1
                elif expr[i] == ")":
                    depth -= 1
                if depth > 0:
                    i += 1
                else:
                    break
            inner_expr = expr[expr_start:i].strip()
            end_offset = i + 1  # skip the closing )

            result.append(expr[last_index : match.start()])

            part_upper = part.upper()
            part_lower = part.lower()

            if "$PART_PRESTO" in template:
                # Presto: year(expr), month(expr), day(expr), hour(expr)
                presto_fn = "to_unixtime" if part_lower == "epoch" else part_lower
                translated = f"{presto_fn}({inner_expr})"
            else:
                translated = template
                translated = re.sub(r"\$PART\b", part_upper, translated)
                translated = re.sub(r"\$PART_UPPER\b", part_upper, translated)
                translated = re.sub(r"\$PART_LOWER\b", part_lower, translated)
                translated = re.sub(r"\$EXPR\b", inner_expr, translated)

            result.append(translated)
            last_index = end_offset

        result.append(expr[last_index:])
        return "".join(result)

    # -- Pass 3: date arithmetic -----------------------------------------------

    def _translate_date_arithmetic(self, expr: str) -> str:
        tpl = _DATE_DIFF_BY_DIALECT[self._dialect]
        if tpl == _DATE_DIFF_BY_DIALECT["postgresql"]:
            return expr

        # Normalise NOW() (already translated to dialect form if needed -- see Pass 2)
        out = re.sub(
            r"\b(?:NOW\s*\(\s*\)|current_timestamp\s*\(\s*\)|current_timestamp)\b",
            "CURRENT_DATE",
            expr,
            flags=re.IGNORECASE,
        )

        # Pattern A: <field_expr> - CURRENT_DATE  ->  date_diff(field, today)
        field_pattern = r"(?:[\w.]+|CAST\([^)]+\)|COALESCE\([^)]+\))"
        out = re.sub(
            r"(" + field_pattern + r")\s*-\s*CURRENT_DATE\b",
            lambda m: tpl.replace("$A", m.group(1).strip()).replace(
                "$B", "CURRENT_DATE"
            ),
            out,
            flags=re.IGNORECASE,
        )

        # Pattern B: CURRENT_DATE - <field_expr>  ->  date_diff(today, field)
        out = re.sub(
            r"\bCURRENT_DATE\s*-\s*(" + field_pattern + r")",
            lambda m: tpl.replace("$A", "CURRENT_DATE").replace(
                "$B", m.group(1).strip()
            ),
            out,
            flags=re.IGNORECASE,
        )

        return out


# -- Concrete dialect translators (thin wrappers) ------------------------------
#
# These exist for explicit typing / discoverability.  The base class handles
# everything via the dialect string, so these are identity subclasses.


class PostgreSQLTranslator(CalcDialectTranslator):
    """Identity / canonical translator -- returns expressions unchanged."""

    def __init__(self) -> None:
        super().__init__("postgresql")


class PrestoTranslator(CalcDialectTranslator):
    """Translator for Presto / Trino (AWS Athena)."""

    def __init__(self) -> None:
        super().__init__("presto")


class BigQueryTranslator(CalcDialectTranslator):
    """Translator for Google BigQuery."""

    def __init__(self) -> None:
        super().__init__("bigquery")


class SnowflakeTranslator(CalcDialectTranslator):
    """Translator for Snowflake."""

    def __init__(self) -> None:
        super().__init__("snowflake")


class SparkTranslator(CalcDialectTranslator):
    """Translator for Apache Spark SQL / Databricks."""

    def __init__(self) -> None:
        super().__init__("spark")


class MySQLTranslator(CalcDialectTranslator):
    """Translator for MySQL / MariaDB."""

    def __init__(self) -> None:
        super().__init__("mysql")


class MSSQLTranslator(CalcDialectTranslator):
    """Translator for Microsoft SQL Server / Azure Synapse."""

    def __init__(self) -> None:
        super().__init__("mssql")


# -- Singleton factory ---------------------------------------------------------

_translator_cache: Dict[str, CalcDialectTranslator] = {}


def get_calc_translator(dialect: str) -> CalcDialectTranslator:
    """Return a (cached) translator for the given dialect string."""
    if dialect not in _translator_cache:
        _translator_cache[dialect] = CalcDialectTranslator(dialect)
    return _translator_cache[dialect]
