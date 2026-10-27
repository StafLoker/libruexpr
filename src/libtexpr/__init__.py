"""Placeholder expressions for templates written in Latin or Cyrillic.

``Placeholder.parse`` turns ``ПОЛЕ * 2 | функция: арг`` into a :class:`Placeholder`; an
:class:`Engine` holding your registered functions validates and evaluates it.
"""

from libtexpr.engine import (
    Engine,
    FieldType,
    Function,
    Issue,
    IssueKind,
    Param,
)
from libtexpr.errors import (
    ArgumentError,
    DivisionByZeroError,
    DuplicateFunctionError,
    EvalError,
    FunctionError,
    InvalidNumberError,
    InvalidSignatureError,
    LimitExceededError,
    NotDateError,
    NotNumericError,
    ParseError,
    RegistryError,
    TexprError,
    UnexpectedCharacterError,
    UnexpectedTokenError,
    UnknownFunctionError,
)
from libtexpr.syntax import Placeholder

__all__ = [
    "ArgumentError",
    "DivisionByZeroError",
    "DuplicateFunctionError",
    "Engine",
    "EvalError",
    "FieldType",
    "Function",
    "FunctionError",
    "InvalidNumberError",
    "InvalidSignatureError",
    "Issue",
    "IssueKind",
    "LimitExceededError",
    "NotDateError",
    "NotNumericError",
    "Param",
    "ParseError",
    "Placeholder",
    "RegistryError",
    "TexprError",
    "UnexpectedCharacterError",
    "UnexpectedTokenError",
    "UnknownFunctionError",
]
