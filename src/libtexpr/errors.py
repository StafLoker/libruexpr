# --- Base ---


class TexprError(Exception):
    """Base class of every error raised by libtexpr."""


# --- Parse errors ---


class ParseError(TexprError):
    """The placeholder text does not match the grammar.

    ``position`` is the 0-based character offset where parsing failed.
    """

    def __init__(self, message: str, position: int) -> None:
        super().__init__(f"{message} at position {position}")
        self.position = position


class UnexpectedCharacterError(ParseError):
    """A character no token can start with, e.g. ``$`` or a letter outside Latin and Cyrillic."""


class UnexpectedTokenError(ParseError):
    """A valid token where the grammar does not allow it, e.g. an unclosed ``(``."""


class LimitExceededError(ParseError):
    """The placeholder is longer than 500 characters or nests parentheses / unary minus deeper than 20 levels."""


class InvalidNumberError(ParseError):
    """A digit sequence that is not a number, e.g. ``1.2.3``."""


# --- Eval errors ---


class EvalError(TexprError):
    """A parsed placeholder could not be evaluated against the given data."""


class UnknownFunctionError(EvalError):
    """The pipeline calls a function that is not registered."""


class ArgumentError(EvalError):
    """A function got too many arguments, misses a required one, or got a value outside its choices."""


class NotNumericError(EvalError):
    """A math operand did not resolve to a number."""


class NotDateError(EvalError):
    """A value that must be a date is not written as ``YYYY-MM-DD``."""


class DivisionByZeroError(EvalError):
    """The right operand of ``/`` is zero."""


class FunctionError(EvalError):
    """A registered function raised; the original exception is in ``__cause__``."""


# --- Registry errors ---


class RegistryError(TexprError):
    """A function registration was rejected."""


class DuplicateFunctionError(RegistryError):
    """A function with the same name is already registered."""


class InvalidSignatureError(RegistryError):
    """The function name cannot be written in a placeholder, or its parameters are inconsistent."""
