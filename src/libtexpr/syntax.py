import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum, auto
from functools import lru_cache
from typing import ClassVar, Self

from libtexpr.errors import (
    DivisionByZeroError,
    InvalidNumberError,
    LimitExceededError,
    NotNumericError,
    UnexpectedCharacterError,
    UnexpectedTokenError,
)

# --- AST ---


class Op(Enum):
    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "/"

    def apply(self, left: Decimal, right: Decimal) -> Decimal:
        try:
            match self:
                case Op.ADD:
                    result = left + right
                case Op.SUB:
                    result = left - right
                case Op.MUL:
                    result = left * right
                case Op.DIV:
                    if right == 0:
                        raise DivisionByZeroError("division by zero")
                    result = left / right
        except ArithmeticError as e:
            raise NotNumericError(f"result of {self.value!r} is out of range") from e
        return result


# What the parser puts in the tree, by what was written in the placeholder:
#   ДОЛГ.СУММА  -> "ДОЛГ.СУММА"          field (told from a word by its uppercase first letter)
#   краткий     -> "краткий"             literal word
#   2.5         -> Decimal("2.5")        number
#   ПОЛЕ * 2    -> BinOp(...)            arithmetic
type Node = Decimal | str | BinOp


@dataclass(frozen=True, slots=True)
class BinOp:
    op: Op
    left: Node
    right: Node


@dataclass(frozen=True, slots=True)
class Call:
    name: str
    args: tuple[str, ...]


# --- Placeholder ---


@dataclass(frozen=True, slots=True)
class Placeholder:
    """A parsed placeholder. Build it with :meth:`parse`, never directly.

    ``MAX_LENGTH`` and ``MAX_NESTING`` are the limits :meth:`parse` enforces, and ``PATTERN``
    matches one bracketed placeholder in a text (group 1 is the text inside the brackets).
    """

    # Parentheses nest at most MAX_NESTING deep and a flat chain of operators fits in MAX_LENGTH,
    # so the recursive parser and evaluator stay far below Python's recursion limit.
    MAX_LENGTH: ClassVar[int] = 500
    MAX_NESTING: ClassVar[int] = 20

    PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"\[([^\[\]]+)\]")

    expr: Node
    pipeline: tuple[Call, ...]

    # Cached because a template is parsed again for every row it is rendered with.
    @classmethod
    @lru_cache(maxsize=2048)
    def parse(cls, src: str) -> Self:
        """Parse the text inside one ``[...]``, without the brackets.

        Field names are UPPERCASE and may contain dots (``ПОЛЕ``, ``DEBT.AMOUNT``); function
        names and bare words are lowercase. Letters are Latin or Cyrillic. Raises a :class:`ParseError`
        subclass carrying the failing position. A text longer than ``MAX_LENGTH``, or
        parentheses and unary minus nested deeper than ``MAX_NESTING``, raises
        :class:`LimitExceededError`.
        """
        if len(src) > cls.MAX_LENGTH:
            raise LimitExceededError(
                f"placeholder longer than {cls.MAX_LENGTH} characters", cls.MAX_LENGTH
            )
        expr, pipeline = _Parser(_Token.tokenize(src)).placeholder()
        return cls(expr, pipeline)

    @staticmethod
    def extract(text: str) -> list[str]:
        """Return the inner text of every ``[...]`` in ``text``, in order, without parsing it.

        Nested brackets are not supported: the innermost pair is taken. Feed each result to
        :meth:`parse`; extracting first lets you report a syntax error per placeholder.
        """
        return Placeholder.PATTERN.findall(text)


# --- Characters ---


# Latin (with its accented letters) and Cyrillic: the alphabets names may be written in.
_LETTER = re.compile(r"[A-Za-z\u00C0-\u024F\u0400-\u052F]")


def _is_upper(ch: str) -> bool:
    return ch.isupper() and _LETTER.match(ch) is not None


def _is_lower(ch: str) -> bool:
    return ch.islower() and _LETTER.match(ch) is not None


def _is_digit(ch: str) -> bool:
    return "0" <= ch <= "9"


def is_field(text: str) -> bool:
    return _is_upper(text[0])


def is_function_name(text: str) -> bool:
    return text != "" and _is_lower(text[0]) and all(_is_lower(c) or c == "_" for c in text)


# --- Tokens ---


class _Kind(Enum):
    EOF = auto()
    UPPER = auto()
    LOWER = auto()
    NUMBER = auto()
    PIPE = auto()
    COLON = auto()
    COMMA = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    LPAREN = auto()
    RPAREN = auto()


@dataclass(frozen=True, slots=True)
class _Token:
    PUNCTUATION: ClassVar[dict[str, _Kind]] = {
        "|": _Kind.PIPE,
        ":": _Kind.COLON,
        ",": _Kind.COMMA,
        "+": _Kind.PLUS,
        "-": _Kind.MINUS,
        "*": _Kind.STAR,
        "/": _Kind.SLASH,
        "(": _Kind.LPAREN,
        ")": _Kind.RPAREN,
    }

    kind: _Kind
    text: str
    position: int

    @classmethod
    def tokenize(cls, src: str) -> list[Self]:
        tokens: list[_Token] = []
        i = 0

        while i < len(src):
            ch = src[i]
            end = i + 1
            if ch.isspace():
                pass
            elif ch in cls.PUNCTUATION:
                tokens.append(cls(cls.PUNCTUATION[ch], ch, i))
            elif _is_digit(ch):
                end = cls._scan(src, i, lambda c: _is_digit(c) or c == ".")
                tokens.append(cls(_Kind.NUMBER, src[i:end], i))
            elif _is_upper(ch):
                end = cls._scan(src, i, lambda c: _is_upper(c) or _is_digit(c) or c in "_.")
                tokens.append(cls(_Kind.UPPER, src[i:end], i))
            elif _is_lower(ch):
                end = cls._scan(src, i, lambda c: _is_lower(c) or c == "_")
                tokens.append(cls(_Kind.LOWER, src[i:end], i))
            else:
                raise UnexpectedCharacterError(f"unexpected character {ch!r}", i)
            i = end

        tokens.append(cls(_Kind.EOF, "", len(src)))
        return tokens

    def number(self) -> Decimal:
        try:
            return Decimal(self.text)
        except InvalidOperation as e:
            raise InvalidNumberError(f"invalid number {self.text!r}", self.position) from e

    def expected(self, what: str) -> UnexpectedTokenError:
        got = repr(self.text) if self.kind is not _Kind.EOF else "end of placeholder"
        return UnexpectedTokenError(f"expected {what}, got {got}", self.position)

    @staticmethod
    def _scan(src: str, start: int, accept: Callable[[str], bool]) -> int:
        end = start
        while end < len(src) and accept(src[end]):
            end += 1
        return end


# --- Parser ---


class _Parser:
    _ADDITIVE: ClassVar[dict[_Kind, Op]] = {_Kind.PLUS: Op.ADD, _Kind.MINUS: Op.SUB}
    _MULTIPLICATIVE: ClassVar[dict[_Kind, Op]] = {_Kind.STAR: Op.MUL, _Kind.SLASH: Op.DIV}

    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0
        self._depth = 0

    def placeholder(self) -> tuple[Node, tuple[Call, ...]]:
        pipeline: list[Call] = []
        expr = self._expr()
        while self._take(_Kind.PIPE):
            pipeline.append(self._call())
        self._expect(_Kind.EOF, "'|' or end of placeholder")
        return expr, tuple(pipeline)

    @property
    def _peek(self) -> _Token:
        return self._tokens[self._pos]

    def _advance(self) -> _Token:
        token = self._peek
        self._pos = min(self._pos + 1, len(self._tokens) - 1)
        return token

    def _take(self, kind: _Kind) -> bool:
        taken = self._peek.kind is kind
        if taken:
            self._advance()
        return taken

    def _expect(self, kind: _Kind, what: str) -> _Token:
        token = self._peek
        if token.kind is not kind:
            raise token.expected(what)
        return self._advance()

    def _expr(self) -> Node:
        node = self._term()
        while self._peek.kind in self._ADDITIVE:
            node = BinOp(self._ADDITIVE[self._advance().kind], node, self._term())
        return node

    def _term(self) -> Node:
        node = self._factor()
        while self._peek.kind in self._MULTIPLICATIVE:
            node = BinOp(self._MULTIPLICATIVE[self._advance().kind], node, self._factor())
        return node

    def _enter(self, token: _Token) -> None:
        self._depth += 1
        if self._depth > Placeholder.MAX_NESTING:
            raise LimitExceededError(
                f"nesting deeper than {Placeholder.MAX_NESTING} levels", token.position
            )

    def _factor(self) -> Node:
        node: Node
        token = self._advance()

        match token.kind:
            case _Kind.MINUS:
                self._enter(token)
                node = BinOp(Op.SUB, Decimal(0), self._factor())
                self._depth -= 1
            case _Kind.LPAREN:
                self._enter(token)
                node = self._expr()
                self._expect(_Kind.RPAREN, "')'")
                self._depth -= 1
            case _Kind.NUMBER:
                node = token.number()
            case _Kind.UPPER:
                node = token.text
            case _Kind.LOWER:
                node = token.text
            case _:
                raise token.expected("a value")
        return node

    def _call(self) -> Call:
        args: list[str] = []
        name = self._expect(_Kind.LOWER, "function name").text

        if self._take(_Kind.COLON):
            args.append(self._arg())
            while self._take(_Kind.COMMA):
                args.append(self._arg())
        return Call(name, tuple(args))

    def _arg(self) -> str:
        arg: str
        token = self._advance()

        match token.kind:
            case _Kind.UPPER:
                arg = token.text
            case _Kind.LOWER:
                arg = token.text
            case _Kind.NUMBER:
                token.number()
                arg = token.text
            case _:
                raise token.expected("an argument")
        return arg
