# Copyright (c) 2026-present NexaQL Contributors
"""NexaQL query engine types — AST nodes, tokens, and result shapes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union


# -- Token types --------------------------------------------------------------

class TokenType(str, Enum):
    KEYWORD = "KEYWORD"      # query
    IDENT = "IDENT"          # identifier
    LBRACE = "LBRACE"        # {
    RBRACE = "RBRACE"        # }
    LPAREN = "LPAREN"        # (
    RPAREN = "RPAREN"        # )
    LBRACKET = "LBRACKET"    # [
    RBRACKET = "RBRACKET"    # ]
    COLON = "COLON"          # :
    COMMA = "COMMA"          # ,
    AT = "AT"                # @
    STRING = "STRING"        # "..." | '...'
    INT = "INT"              # 123
    FLOAT = "FLOAT"          # 12.3
    BOOL = "BOOL"            # true | false
    NULL = "NULL"            # null
    PLUS = "PLUS"            # +
    MINUS = "MINUS"          # -
    STAR = "STAR"            # *
    SLASH = "SLASH"          # /
    DOT = "DOT"              # .
    EOF = "EOF"


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str
    line: int
    col: int


# -- AST types ----------------------------------------------------------------

class FilterOp(str, Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    LIKE = "like"
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    NOT_NULL = "not_null"


FilterValue = Union[str, int, float, bool, None, List["FilterValue"]]


@dataclass
class Filter:
    field: str
    op: FilterOp
    value: FilterValue
    calc_expr: Optional[str] = None


class DirectiveType(str, Enum):
    LIMIT = "limit"
    OFFSET = "offset"
    ORDERBY = "orderby"
    DISTINCT = "distinct"


@dataclass(frozen=True)
class LimitDirective:
    type: Literal["limit"]
    value: int


@dataclass(frozen=True)
class OffsetDirective:
    type: Literal["offset"]
    value: int


@dataclass(frozen=True)
class OrderByDirective:
    type: Literal["orderby"]
    field: str
    direction: Literal["ASC", "DESC"]


@dataclass(frozen=True)
class DistinctDirective:
    type: Literal["distinct"]


Directive = Union[LimitDirective, OffsetDirective, OrderByDirective, DistinctDirective]


@dataclass
class ScalarField:
    kind: Literal["scalar"]
    name: str
    alias: Optional[str] = None


@dataclass
class CalcField:
    """Inline computed expression: alias: calc(expr)

    expr is a raw SQL fragment with bare field names -- expanded by the translator.
    Examples:
        days_left:      calc(due_date - CURRENT_DATE)
        overcharge_amt: calc(unit_price - agreed_unit_price)
        line_total:     calc(quantity * unit_price)
    """
    kind: Literal["calc"]
    alias: str
    expr: str


@dataclass
class AggregationField:
    kind: Literal["aggregation"]
    alias: str
    func: Literal["sum", "avg", "min", "max", "count"]
    argument: str  # field name or "*"


@dataclass
class EdgeField:
    kind: Literal["edge"]
    node: "NodeSelection"


Field = Union[ScalarField, AggregationField, EdgeField, CalcField]


@dataclass
class NodeSelection:
    kind: Literal["node"]
    name: str
    filters: List[Filter] = field(default_factory=list)
    directives: List[Directive] = field(default_factory=list)
    fields: List[Field] = field(default_factory=list)


@dataclass
class QueryAST:
    kind: Literal["query"]
    body: NodeSelection
    name: Optional[str] = None


# -- Validation ----------------------------------------------------------------

@dataclass
class ValidationError:
    message: str
    line: Optional[int] = None
    col: Optional[int] = None


@dataclass
class ValidationResult:
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# -- Execution result ----------------------------------------------------------

@dataclass
class ColumnMeta:
    name: str
    type: str


@dataclass
class ExecuteResult:
    sql: str
    rows: List[Dict[str, Any]]
    row_count: int
    columns: List[ColumnMeta]
    duration_ms: float
    error: Optional[str] = None


# -- Query result shape (for nested JSON reconstruction) -----------------------

@dataclass
class NodeShape:
    edge_name: Optional[str]  # name used by parent when traversing this edge (None for root)
    node: str                 # ontology node name
    column_aliases: List[str] = field(default_factory=list)       # "nodeName__fieldName" SELECT aliases
    aggregation_aliases: List[str] = field(default_factory=list)  # user-defined aggregation column aliases
    children: List["NodeShape"] = field(default_factory=list)


# -- Suggest types -------------------------------------------------------------

@dataclass
class SuggestContext:
    type: Literal["node", "field", "filter", "directive"]
    node_name: Optional[str] = None
    partial: Optional[str] = None


@dataclass
class SuggestionItem:
    label: str
    kind: Literal["node", "field", "edge", "aggregation", "filter", "special-filter", "directive"]
    insert_text: str
    detail: Optional[str] = None
