import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum, auto
from typing import Any

from libtexpr.errors import (
    ArgumentError,
    DuplicateFunctionError,
    FunctionError,
    InvalidSignatureError,
    NotDateError,
    NotNumericError,
    TexprError,
    UnknownFunctionError,
)
from libtexpr.syntax import (
    BinOp,
    Call,
    Node,
    Placeholder,
    is_field,
    is_function_name,
)

# --- Constants ---


_SEPARATORS = str.maketrans({" ": None, " ": None, " ": None, ",": "."})
_NUMBER_RE = re.compile(r"[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


# --- Types ---


type Value = str | Decimal | date
"""The value a pipeline carries: ``str`` for TEXT, ``Decimal`` for NUMBER, ``date`` for DATE."""


class FieldType(Enum):
    """Type of a field value or of a function's input/output.

    The value of each member is the Python class a pipeline carries for that type.
    """

    TEXT = str
    NUMBER = Decimal
    DATE = date

    def _coerce(self, value: Value) -> Value:
        match self:
            case FieldType.TEXT:
                if isinstance(value, Decimal):
                    result: Value = _format_number(value)
                elif isinstance(value, date):
                    result = value.isoformat()
                else:
                    result = value
            case FieldType.NUMBER:
                result = _to_number(value)
            case FieldType.DATE:
                try:
                    result = (
                        date.fromisoformat(value.strip())
                        if isinstance(value, str) and _DATE_RE.fullmatch(value.strip())
                        else value
                    )
                except ValueError:
                    result = ""
                if not isinstance(result, date):
                    raise NotDateError(f"expected a date as YYYY-MM-DD, got {value!r}")
        return result


@dataclass(frozen=True, slots=True)
class Param:
    """One positional argument of a registered function.

    ``choices`` lists the allowed literal values; empty means any word, number or field
    reference. ``default`` is passed when the argument is omitted; ``None`` makes the
    argument required.
    """

    choices: frozenset[str] = frozenset()
    default: str | None = None


@dataclass(frozen=True, slots=True)
class Function:
    """A function callable in a pipeline (``| name: arg, arg``), with its whole signature.

    ``run(value, args)`` is the code. ``value`` has the Python type of ``input_type``
    (TEXT ``str``, NUMBER ``Decimal``, DATE ``datetime.date``) and the result must have the
    type of ``output_type``. ``args`` holds exactly one string per declared :class:`Param`:
    field references already replaced by their data value, omitted arguments filled with
    their default. An exception raised by ``run``, or a result of the wrong type, becomes
    a :class:`FunctionError`.

    ``validate`` type-checks pipelines with ``input_type`` and ``output_type``; ``evaluate``
    converts the value to ``input_type`` before every call. Pass the function to
    :meth:`Engine.register`.

    Raises :class:`InvalidSignatureError` when built with a ``name`` that is not a
    lowercase Latin or Cyrillic word, a required parameter after an optional one, or a default
    outside its choices.
    """

    name: str
    run: Callable[[Any, tuple[str, ...]], Any]
    input_type: FieldType
    output_type: FieldType
    params: tuple[Param, ...] = ()

    def __post_init__(self) -> None:
        problems: list[str] = []
        optional_seen = False

        if not is_function_name(self.name):
            problems.append(f"{self.name!r} is not a lowercase Latin or Cyrillic function name")
        for index, param in enumerate(self.params, start=1):
            if param.default is None and optional_seen:
                problems.append(f"required parameter {index} follows an optional one")
            if param.choices and param.default is not None and param.default not in param.choices:
                problems.append(
                    f"default {param.default!r} of parameter {index} is not among its choices"
                )
            optional_seen = optional_seen or param.default is not None
        if problems:
            raise InvalidSignatureError("; ".join(problems))


class IssueKind(Enum):
    UNKNOWN_FIELD = auto()
    UNKNOWN_FUNCTION = auto()
    TYPE_MISMATCH = auto()
    BAD_ARGUMENT = auto()


@dataclass(frozen=True, slots=True)
class Issue:
    """One problem found by :meth:`Engine.validate`."""

    kind: IssueKind
    message: str


# --- Value helpers ---


def _to_number(value: Value) -> Decimal:
    """Read a number written the way field values are stored.

    Accepts an optional sign, a comma or dot decimal separator and spaces / NBSP as
    thousands separators (``"1 000,50"``). Raises :class:`NotNumericError` for anything
    else; exponents, ``inf`` and ``nan`` are rejected.
    """
    cleaned = value.strip().translate(_SEPARATORS) if isinstance(value, str) else ""
    parsed = Decimal(cleaned) if _NUMBER_RE.fullmatch(cleaned) else value
    if not isinstance(parsed, Decimal):
        raise NotNumericError(f"expected a number, got {value!r}")
    return parsed


def _format_number(value: Decimal) -> str:
    """Plain decimal notation without exponent or trailing zeros: ``2001``, ``15000.5``."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


# --- Argument checks ---


def _argument_problems(call: Call, fn: Function) -> list[str]:
    problems: list[str] = []

    if len(call.args) > len(fn.params):
        problems.append(
            f"{call.name!r} takes at most {len(fn.params)} arguments, got {len(call.args)}"
        )
    for index, param in enumerate(fn.params):
        given = call.args[index] if index < len(call.args) else None
        if given is None and param.default is None:
            problems.append(f"{call.name!r} misses required argument {index + 1}")
        elif (
            given is not None and param.choices and (is_field(given) or given not in param.choices)
        ):
            problems.append(
                f"argument {index + 1} of {call.name!r} must be one of "
                f"{', '.join(sorted(param.choices))}; got {given!r}"
            )
    return problems


# --- Validation ---


def _check(node: Node, schema: Mapping[str, FieldType], issues: list[Issue]) -> FieldType:
    result = FieldType.NUMBER

    match node:
        case str() if is_field(node):
            result = schema.get(node, FieldType.TEXT)
            if node not in schema:
                issues.append(Issue(IssueKind.UNKNOWN_FIELD, f"unknown field {node}"))
        case str():
            result = FieldType.TEXT
        case BinOp():
            for side, operand in (("left", node.left), ("right", node.right)):
                if _check(operand, schema, issues) is not FieldType.NUMBER:
                    issues.append(
                        Issue(
                            IssueKind.TYPE_MISMATCH,
                            f"{side} operand of {node.op.value!r} is not NUMBER",
                        )
                    )
    return result


# --- Evaluation ---


def _numeric(node: Node, data: Mapping[str, str]) -> Decimal:
    match node:
        case Decimal():
            result = node
        case BinOp():
            result = node.op.apply(_numeric(node.left, data), _numeric(node.right, data))
        case str():
            result = _to_number(_value(node, data))
    return result


def _value(node: Node, data: Mapping[str, str]) -> Value:
    match node:
        case str() if is_field(node):
            result = data.get(node, "")
        case str():
            result = node
        case Decimal() | BinOp():
            result = _numeric(node, data)
    return result


# --- Engine ---


class Engine:
    """Registered functions plus the operations that use them.

    Register every function once at startup; ``validate``, ``evaluate`` and
    ``render_text`` never change the engine and are safe to call from several threads.
    """

    def __init__(self) -> None:
        self._functions: dict[str, Function] = {}

    def register(self, function: Function) -> None:
        """Make ``function`` callable in a pipeline under ``function.name``.

        Raises :class:`DuplicateFunctionError` if the name is already taken.
        """
        if function.name in self._functions:
            raise DuplicateFunctionError(f"function {function.name!r} is already registered")
        self._functions[function.name] = function

    def validate(self, placeholder: Placeholder, schema: Mapping[str, FieldType]) -> list[Issue]:
        """Check ``placeholder`` against ``schema`` and the registered functions.

        ``schema`` maps a field name (``"ПОЛЕ"``, ``"ДОЛГ.СУММА"``) to its type.

        Returns every issue found, not only the first; an empty list means it can be
        evaluated. After an unknown function the type flowing through the pipeline is
        left unchanged, so later steps are still checked.
        """
        issues: list[Issue] = []
        current = _check(placeholder.expr, schema, issues)

        for call in placeholder.pipeline:
            fn = self._functions.get(call.name)
            if fn is None:
                issues.append(Issue(IssueKind.UNKNOWN_FUNCTION, f"unknown function {call.name!r}"))
            else:
                if current is not fn.input_type:
                    issues.append(
                        Issue(
                            IssueKind.TYPE_MISMATCH,
                            f"{call.name!r} expects {fn.input_type.name}, got {current.name}",
                        )
                    )
                issues.extend(
                    Issue(IssueKind.BAD_ARGUMENT, p) for p in _argument_problems(call, fn)
                )
                current = fn.output_type
            for arg in call.args:
                _check(arg, schema, issues)
        return issues

    def evaluate(self, placeholder: Placeholder, data: Mapping[str, str]) -> str:
        """Compute ``placeholder`` for one row of ``data`` (same keys → raw value).

        The result is always text: a number is written without exponent, a date as
        ``YYYY-MM-DD``. A missing field is ``""``; where a number or date is needed it raises an :class:`EvalError`. Math runs on
        :class:`~decimal.Decimal`. Raises an :class:`EvalError` subclass.
        """
        value = _value(placeholder.expr, data)
        for call in placeholder.pipeline:
            value = self._call(call, value, data)
        return str(FieldType.TEXT._coerce(value))

    def render_text(self, text: str, data: Mapping[str, str]) -> str:
        """Replace every ``[...]`` in ``text`` with its value for ``data``.

        A placeholder that fails to parse or evaluate is left exactly as written.
        """

        def replace(match: re.Match[str]) -> str:
            try:
                result = self.evaluate(Placeholder.parse(match.group(1)), data)
            except TexprError:
                result = match.group(0)
            return result

        return Placeholder.PATTERN.sub(replace, text)

    def _call(self, call: Call, value: Value, data: Mapping[str, str]) -> Value:
        fn = self._functions.get(call.name)
        if fn is None:
            raise UnknownFunctionError(f"unknown function {call.name!r}")
        problems = _argument_problems(call, fn)
        if problems:
            raise ArgumentError("; ".join(problems))

        given = tuple(data.get(a, "") if is_field(a) else a for a in call.args)
        defaults = tuple(p.default for p in fn.params[len(given) :] if p.default is not None)
        typed = fn.input_type._coerce(value)
        try:
            result = fn.run(typed, given + defaults)
        except Exception as e:
            raise FunctionError(f"{call.name!r} failed: {e}") from e
        if not isinstance(result, fn.output_type.value):
            raise FunctionError(
                f"{call.name!r} returned {type(result).__name__}, declared {fn.output_type.name}"
            )
        return result
