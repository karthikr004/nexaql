# Copyright (c) 2026-present NexaQL Contributors
"""NexaQL lexer — tokenizes query source text."""

from __future__ import annotations

from .types import Token, TokenType

_KEYWORDS = frozenset({"query"})
_BOOLEANS = frozenset({"true", "false"})


class LexerError(Exception):
    """Raised when the lexer encounters an invalid character or unterminated literal."""

    def __init__(self, message: str, line: int, col: int) -> None:
        self.line = line
        self.col = col
        super().__init__(f"Lexer error at {line}:{col} — {message}")


def tokenize(src: str) -> list[Token]:
    """Tokenize *src* into a list of :class:`Token` objects (terminated by EOF)."""

    tokens: list[Token] = []
    pos = 0
    line = 1
    col = 1
    length = len(src)

    def peek(offset: int = 0) -> str | None:
        idx = pos + offset
        if idx < length:
            return src[idx]
        return None

    def advance() -> str:
        nonlocal pos, line, col
        ch = src[pos]
        pos += 1
        if ch == "\n":
            line += 1
            col = 1
        else:
            col += 1
        return ch

    def add_token(typ: TokenType, value: str, l: int, c: int) -> None:
        tokens.append(Token(type=typ, value=value, line=l, col=c))

    while pos < length:
        start_line = line
        start_col = col
        ch = peek()

        # Whitespace
        if ch is not None and ch in " \t\n\r\f\v":
            advance()
            continue

        # Line comment: # or //
        if ch == "#" or (ch == "/" and peek(1) == "/"):
            while pos < length and peek() != "\n":
                advance()
            continue

        # Single-char tokens
        if ch == "{":
            advance()
            add_token(TokenType.LBRACE, "{", start_line, start_col)
            continue
        if ch == "}":
            advance()
            add_token(TokenType.RBRACE, "}", start_line, start_col)
            continue
        if ch == "(":
            advance()
            add_token(TokenType.LPAREN, "(", start_line, start_col)
            continue
        if ch == ")":
            advance()
            add_token(TokenType.RPAREN, ")", start_line, start_col)
            continue
        if ch == "[":
            advance()
            add_token(TokenType.LBRACKET, "[", start_line, start_col)
            continue
        if ch == "]":
            advance()
            add_token(TokenType.RBRACKET, "]", start_line, start_col)
            continue
        if ch == ":":
            advance()
            add_token(TokenType.COLON, ":", start_line, start_col)
            continue
        if ch == ",":
            advance()
            add_token(TokenType.COMMA, ",", start_line, start_col)
            continue
        if ch == "@":
            advance()
            add_token(TokenType.AT, "@", start_line, start_col)
            continue

        # Arithmetic operators (used inside calc() expressions)
        if ch == "+":
            advance()
            add_token(TokenType.PLUS, "+", start_line, start_col)
            continue
        if ch == "*":
            advance()
            add_token(TokenType.STAR, "*", start_line, start_col)
            continue
        # "/" only emits SLASH when not part of "//" comment (already handled above)
        if ch == "/":
            advance()
            add_token(TokenType.SLASH, "/", start_line, start_col)
            continue
        # "-" emits MINUS only when NOT followed by a digit (negative numbers handled below)
        if ch == "-" and not (peek(1) is not None and peek(1).isdigit()):  # type: ignore[union-attr]
            advance()
            add_token(TokenType.MINUS, "-", start_line, start_col)
            continue

        # String literal
        if ch == '"' or ch == "'":
            quote = advance()
            s = ""
            while pos < length and peek() != quote:
                if peek() == "\\":
                    advance()
                    s += advance()
                else:
                    s += advance()
            if pos >= length:
                raise LexerError("Unterminated string", start_line, start_col)
            advance()  # closing quote
            add_token(TokenType.STRING, s, start_line, start_col)
            continue

        # Number (must come before DOT so decimal points like 12.3 are handled correctly)
        if (ch is not None and ch.isdigit()) or (ch == "-" and peek(1) is not None and peek(1).isdigit()):  # type: ignore[union-attr]
            num = ""
            if ch == "-":
                num += advance()
            while pos < length and peek() is not None and peek().isdigit():  # type: ignore[union-attr]
                num += advance()
            if peek() == "." and (peek(1) is not None and peek(1).isdigit()):  # type: ignore[union-attr]
                num += advance()  # dot
                while pos < length and peek() is not None and peek().isdigit():  # type: ignore[union-attr]
                    num += advance()
                add_token(TokenType.FLOAT, num, start_line, start_col)
            else:
                add_token(TokenType.INT, num, start_line, start_col)
            continue

        # Dot (used for entity.field references inside calc expressions)
        if ch == ".":
            advance()
            add_token(TokenType.DOT, ".", start_line, start_col)
            continue

        # Identifier / keyword / bool / null
        if ch is not None and (ch.isalpha() or ch == "_"):
            ident = ""
            while pos < length and peek() is not None and (peek().isalnum() or peek() == "_"):  # type: ignore[union-attr]
                ident += advance()
            if ident == "null":
                add_token(TokenType.NULL, ident, start_line, start_col)
            elif ident in _BOOLEANS:
                add_token(TokenType.BOOL, ident, start_line, start_col)
            elif ident in _KEYWORDS:
                add_token(TokenType.KEYWORD, ident, start_line, start_col)
            else:
                add_token(TokenType.IDENT, ident, start_line, start_col)
            continue

        raise LexerError(f"Unexpected character '{ch}'", start_line, start_col)

    tokens.append(Token(type=TokenType.EOF, value="", line=line, col=col))
    return tokens
