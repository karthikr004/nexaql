# Copyright (c) 2026-present NexaQL Contributors
"""NexaQL parser — transforms token stream into a QueryAST."""

from __future__ import annotations

from typing import List, Optional

from .lexer import tokenize
from .types import (
    AggregationField,
    CalcField,
    Directive,
    DistinctDirective,
    EdgeField,
    Filter,
    FilterOp,
    FilterValue,
    LimitDirective,
    NodeSelection,
    OffsetDirective,
    OrderByDirective,
    QueryAST,
    ScalarField,
    Token,
    TokenType,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Operator suffix map: field name suffix -> FilterOp
OP_SUFFIXES: list[tuple[str, FilterOp]] = [
    ("_gte", FilterOp.GTE),
    ("_lte", FilterOp.LTE),
    ("_gt", FilterOp.GT),
    ("_lt", FilterOp.LT),
    ("_ne", FilterOp.NE),
    ("_eq", FilterOp.EQ),
    ("_like", FilterOp.LIKE),
    ("_in", FilterOp.IN),
    ("_not_in", FilterOp.NOT_IN),
    ("_null", FilterOp.IS_NULL),
]

# Object-style operator aliases -> suffix
# Allows: field: { lt: 7, gte: 0 }  (GraphQL-inspired, highly LLM-friendly)
OBJ_OP_ALIASES: dict[str, str] = {
    "eq": "_eq",
    "equals": "_eq",
    "ne": "_ne",
    "not": "_ne",
    "gt": "_gt",
    "greater_than": "_gt",
    "gte": "_gte",
    "gte_eq": "_gte",
    "lt": "_lt",
    "less_than": "_lt",
    "lte": "_lte",
    "lte_eq": "_lte",
    "like": "_like",
    "contains": "_like",
    "in": "_in",
    "not_in": "_not_in",
    "nin": "_not_in",
    "null": "_null",
    "is_null": "_null",
}

AGG_FUNCS: set[str] = {"sum", "avg", "min", "max", "count"}


# ---------------------------------------------------------------------------
# ParseError
# ---------------------------------------------------------------------------

class ParseError(Exception):
    """Raised when the parser encounters an unexpected token."""

    def __init__(self, message: str, line: int, col: int) -> None:
        self.line = line
        self.col = col
        super().__init__(f"Parse error at {line}:{col} — {message}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class Parser:
    """Recursive-descent parser for the NexaQL query language."""

    def __init__(self, src: str) -> None:
        self._tokens: list[Token] = tokenize(src)
        self._pos: int = 0

    # -- helpers ------------------------------------------------------------

    def _peek(self, offset: int = 0) -> Token:
        idx = self._pos + offset
        if idx < len(self._tokens):
            return self._tokens[idx]
        return self._tokens[-1]

    def _advance(self) -> Token:
        t = self._tokens[self._pos]
        self._pos += 1
        return t

    def _at(self, type: TokenType) -> bool:  # noqa: A002
        return self._peek().type == type

    def _eat(self, type: TokenType) -> Token:  # noqa: A002
        t = self._peek()
        if t.type != type:
            raise ParseError(
                f"Expected {type.value} but got '{t.value}' ({t.type.value})",
                t.line,
                t.col,
            )
        return self._advance()

    # -- public entry -------------------------------------------------------

    def parse(self) -> QueryAST:
        """Parse the full token stream into a :class:`QueryAST`."""
        # Optional "query Name?"
        name: Optional[str] = None
        if self._at(TokenType.KEYWORD) and self._peek().value == "query":
            self._advance()
            if self._at(TokenType.IDENT):
                name = self._advance().value

        # Expect outer brace
        self._eat(TokenType.LBRACE)
        body = self.parseNodeSelection()
        self._eat(TokenType.RBRACE)

        if not self._at(TokenType.EOF):
            t = self._peek()
            raise ParseError(
                f"Unexpected token '{t.value}' after query", t.line, t.col
            )

        return QueryAST(kind="query", body=body, name=name)

    # -- node selection -----------------------------------------------------

    def parseNodeSelection(self) -> NodeSelection:
        name_token = self._eat(TokenType.IDENT)
        filters = self.parseFilters() if self._at(TokenType.LPAREN) else []
        directives = self.parseDirectives()
        self._eat(TokenType.LBRACE)
        fields = self.parseFieldList()
        self._eat(TokenType.RBRACE)
        return NodeSelection(
            kind="node",
            name=name_token.value,
            filters=filters,
            directives=directives,
            fields=fields,
        )

    # -- filters ------------------------------------------------------------

    def parseFilters(self) -> list[Filter]:
        self._eat(TokenType.LPAREN)
        filters: list[Filter] = []

        while not self._at(TokenType.RPAREN) and not self._at(TokenType.EOF):
            # -- calc(expr): { op: value } ------------------------------------
            if self._at(TokenType.IDENT) and self._peek().value == "calc":
                self._advance()  # "calc"
                self._eat(TokenType.LPAREN)
                calc_expr = self.collectCalcExpr()
                self._eat(TokenType.RPAREN)
                self._eat(TokenType.COLON)

                if self._at(TokenType.LBRACE):
                    self._advance()  # {
                    while not self._at(TokenType.RBRACE) and not self._at(TokenType.EOF):
                        op_token = self._eat(TokenType.IDENT)
                        self._eat(TokenType.COLON)
                        op_value = self.parseValue()
                        suffix = OBJ_OP_ALIASES.get(op_token.value, f"_{op_token.value}")
                        base = parseFilterArg(f"__calc{suffix}", op_value)
                        base.field = "__calc"
                        base.calc_expr = calc_expr
                        filters.append(base)
                        if self._at(TokenType.COMMA):
                            self._advance()
                    self._eat(TokenType.RBRACE)
                else:
                    # Shorthand: calc(expr): value  -> treated as equality
                    raw_value = self.parseValue()
                    base = parseFilterArg("__calc", raw_value)
                    base.field = "__calc"
                    base.calc_expr = calc_expr
                    filters.append(base)

                if self._at(TokenType.COMMA):
                    self._advance()
                continue

            key_token = self._eat(TokenType.IDENT)
            self._eat(TokenType.COLON)

            if self._at(TokenType.LBRACE):
                # -- Object-style filters: field: { lt: 7, gte: 0, ... } -----
                self._advance()  # consume {
                while not self._at(TokenType.RBRACE) and not self._at(TokenType.EOF):
                    op_token = self._eat(TokenType.IDENT)
                    self._eat(TokenType.COLON)
                    op_value = self.parseValue()
                    suffix = OBJ_OP_ALIASES.get(op_token.value, f"_{op_token.value}")
                    filters.append(
                        parseFilterArg(f"{key_token.value}{suffix}", op_value)
                    )
                    if self._at(TokenType.COMMA):
                        self._advance()
                self._eat(TokenType.RBRACE)
            else:
                # -- Existing shorthand: field: value  or  field_op: value ----
                raw_value = self.parseValue()
                filters.append(parseFilterArg(key_token.value, raw_value))

            if self._at(TokenType.COMMA):
                self._advance()

        self._eat(TokenType.RPAREN)
        return filters

    # -- directives ---------------------------------------------------------

    def parseDirectives(self) -> list[Directive]:
        dirs: list[Directive] = []
        while self._at(TokenType.AT):
            self._advance()  # @
            name_token = self._eat(TokenType.IDENT)

            if name_token.value == "limit":
                self._eat(TokenType.LPAREN)
                v = int(self._eat(TokenType.INT).value)
                self._eat(TokenType.RPAREN)
                dirs.append(LimitDirective(type="limit", value=v))

            elif name_token.value == "offset":
                self._eat(TokenType.LPAREN)
                v = int(self._eat(TokenType.INT).value)
                self._eat(TokenType.RPAREN)
                dirs.append(OffsetDirective(type="offset", value=v))

            elif name_token.value == "orderby":
                self._eat(TokenType.LPAREN)
                field_name = self._eat(TokenType.IDENT).value
                direction: str = "ASC"
                if self._at(TokenType.COMMA):
                    self._advance()
                    dir_val = self._eat(TokenType.IDENT).value.upper()
                    direction = "DESC" if dir_val == "DESC" else "ASC"
                self._eat(TokenType.RPAREN)
                dirs.append(
                    OrderByDirective(type="orderby", field=field_name, direction=direction)  # type: ignore[arg-type]
                )

            elif name_token.value == "distinct":
                dirs.append(DistinctDirective(type="distinct"))

            else:
                # Unknown directive -- skip args if present
                if self._at(TokenType.LPAREN):
                    self._advance()
                    depth = 1
                    while not self._at(TokenType.EOF) and depth > 0:
                        if self._at(TokenType.LPAREN):
                            depth += 1
                        if self._at(TokenType.RPAREN):
                            depth -= 1
                        self._advance()

        return dirs

    # -- field list ---------------------------------------------------------

    def parseFieldList(self) -> list:
        fields: list = []
        while not self._at(TokenType.RBRACE) and not self._at(TokenType.EOF):
            fields.append(self.parseField())
            if self._at(TokenType.COMMA):
                self._advance()
        return fields

    # -- single field -------------------------------------------------------

    def parseField(self):
        # Lookahead: calc field -> IDENT COLON IDENT("calc") LPAREN
        if (
            self._peek(0).type == TokenType.IDENT
            and self._peek(1).type == TokenType.COLON
            and self._peek(2).type == TokenType.IDENT
            and self._peek(2).value == "calc"
            and self._peek(3).type == TokenType.LPAREN
        ):
            alias = self._advance().value  # alias name
            self._advance()  # COLON
            self._advance()  # "calc"
            self._advance()  # LPAREN
            expr = self.collectCalcExpr()
            self._eat(TokenType.RPAREN)
            return CalcField(kind="calc", alias=alias, expr=expr)

        # Lookahead: aggregation -> IDENT COLON IDENT LPAREN
        if (
            self._peek(0).type == TokenType.IDENT
            and self._peek(1).type == TokenType.COLON
            and self._peek(2).type == TokenType.IDENT
            and self._peek(2).value in AGG_FUNCS
            and self._peek(3).type == TokenType.LPAREN
        ):
            return self.parseAggregationField()

        # Lookahead: nested node -> IDENT (LPAREN|AT|LBRACE)
        next_type = self._peek(1).type
        if next_type in (TokenType.LBRACE, TokenType.LPAREN, TokenType.AT):
            return EdgeField(kind="edge", node=self.parseNodeSelection())

        # Scalar field, optionally aliased: alias: name (without agg func)
        if (
            self._peek(0).type == TokenType.IDENT
            and self._peek(1).type == TokenType.COLON
            and self._peek(2).type == TokenType.IDENT
            and self._peek(2).value not in AGG_FUNCS
        ):
            alias = self._advance().value
            self._advance()  # colon
            name = self._advance().value
            return ScalarField(kind="scalar", name=name, alias=alias)

        # Plain scalar
        name = self._eat(TokenType.IDENT).value
        return ScalarField(kind="scalar", name=name)

    # -- aggregation field --------------------------------------------------

    def parseAggregationField(self) -> AggregationField:
        alias = self._eat(TokenType.IDENT).value
        self._eat(TokenType.COLON)
        func = self._eat(TokenType.IDENT).value
        self._eat(TokenType.LPAREN)
        if self._at(TokenType.RPAREN):
            # count() with no arguments
            argument = "*"
        elif self._at(TokenType.AT) or (
            self._at(TokenType.IDENT) and self._peek().value == "*"
        ):
            argument = "*"
            self._advance()
        elif self._at(TokenType.STAR):
            argument = "*"
            self._advance()
        else:
            argument = self._eat(TokenType.IDENT).value
        self._eat(TokenType.RPAREN)
        return AggregationField(kind="aggregation", alias=alias, func=func, argument=argument)  # type: ignore[arg-type]

    # -- calc expression ----------------------------------------------------

    def collectCalcExpr(self) -> str:
        """Collect tokens inside calc(...) into a reconstructed expression string.

        Handles nested parens. Called after the opening LPAREN is consumed.
        Arithmetic operators (PLUS, MINUS, STAR, SLASH) are included as-is.
        Field names and SQL functions are both captured as IDENT tokens.
        """
        parts: list[str] = []
        depth = 0

        while not self._at(TokenType.EOF):
            t = self._peek()

            if t.type == TokenType.LPAREN:
                depth += 1
                parts.append("(")
                self._advance()
                continue

            if t.type == TokenType.RPAREN:
                if depth == 0:
                    break  # end of calc(...)
                depth -= 1
                parts.append(")")
                self._advance()
                continue

            if t.type == TokenType.LBRACKET:
                parts.append("[")
                self._advance()
                continue

            if t.type == TokenType.RBRACKET:
                parts.append("]")
                self._advance()
                continue

            if t.type == TokenType.IDENT:
                parts.append(t.value)
                self._advance()
                continue

            if t.type == TokenType.KEYWORD:
                parts.append(t.value)
                self._advance()
                continue

            if t.type in (TokenType.INT, TokenType.FLOAT):
                parts.append(t.value)
                self._advance()
                continue

            if t.type == TokenType.STRING:
                parts.append(f"'{t.value.replace(chr(39), chr(39) + chr(39))}'")
                self._advance()
                continue

            if t.type == TokenType.BOOL:
                parts.append(t.value.upper())
                self._advance()
                continue

            if t.type == TokenType.NULL:
                parts.append("NULL")
                self._advance()
                continue

            if t.type == TokenType.COMMA:
                parts.append(", ")
                self._advance()
                continue

            if t.type == TokenType.COLON:
                parts.append(":")
                self._advance()
                continue  # for ::type casts

            if t.type == TokenType.DOT:
                parts.append(".")
                self._advance()
                continue  # for entity.field references

            if t.type == TokenType.PLUS:
                parts.append(" + ")
                self._advance()
                continue

            if t.type == TokenType.MINUS:
                parts.append(" - ")
                self._advance()
                continue

            if t.type == TokenType.STAR:
                parts.append(" * ")
                self._advance()
                continue

            if t.type == TokenType.SLASH:
                parts.append(" / ")
                self._advance()
                continue

            # Unknown token inside calc -- stop collecting
            break

        return "".join(parts).strip()

    # -- value parsing ------------------------------------------------------

    def parseValue(self) -> FilterValue:
        t = self._peek()

        if t.type == TokenType.STRING:
            self._advance()
            return t.value

        if t.type == TokenType.INT:
            self._advance()
            return int(t.value)

        if t.type == TokenType.FLOAT:
            self._advance()
            return float(t.value)

        if t.type == TokenType.BOOL:
            self._advance()
            return t.value == "true"

        if t.type == TokenType.NULL:
            self._advance()
            return None

        if t.type == TokenType.LBRACKET:
            self._advance()
            items: list[FilterValue] = []
            while not self._at(TokenType.RBRACKET) and not self._at(TokenType.EOF):
                items.append(self.parseValue())
                if self._at(TokenType.COMMA):
                    self._advance()
            self._eat(TokenType.RBRACKET)
            return items

        raise ParseError(
            f"Expected a value, got '{t.value}' ({t.type.value})", t.line, t.col
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def parseFilterArg(key: str, value: FilterValue) -> Filter:
    """Parse a filter key like ``"status"``, ``"amount_gt"``, ``"status_in"`` into a Filter."""
    for suffix, op in OP_SUFFIXES:
        if key.endswith(suffix):
            field = key[: -len(suffix)]
            if op == FilterOp.IS_NULL:
                return Filter(
                    field=field,
                    op=FilterOp.IS_NULL if value else FilterOp.NOT_NULL,
                    value=value,
                )
            return Filter(field=field, op=op, value=value)
    # Default: equality (includes special filters like unpaid, overcharged)
    return Filter(field=key, op=FilterOp.EQ, value=value)


def parse(src: str) -> QueryAST:
    """Convenience function: parse *src* and return a :class:`QueryAST`."""
    return Parser(src).parse()
