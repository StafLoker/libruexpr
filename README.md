<div align="center">
   <h1><b>libtexpr</b></h1>
   <p><i>~ Placeholder expressions for templates ~</i></p>
</div>

libtexpr is a Python library that parses and evaluates placeholders such as `[ДОЛГ.СУММА * 2 | деньги: кратко]` or `[DEBT.AMOUNT * 2 | money: short]`. It is for applications that fill data into document templates and let template authors write fields and functions in their own language: Cyrillic or Latin.

The library reads and checks a placeholder, then evaluates it for the given data. The functions themselves (declension, amount in words, date format) are written by the application: the library only calls them in order.

## Quick start

```bash
uv add libtexpr
```

The function `деньги` formats a number; the placeholder computes a sum and applies the function.

```python
from decimal import Decimal

from libtexpr import Engine, FieldType, Function, Param, Placeholder


def money(value: Decimal, args: tuple[str, ...]) -> str:
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return text + (" руб." if args == ("кратко",) else " рублей")


engine = Engine()
engine.register(
    Function(
        "деньги",
        money,
        FieldType.NUMBER,
        FieldType.TEXT,
        (Param(frozenset({"кратко", "полно"}), default="кратко"),),
    )
)

placeholder = Placeholder.parse("ДОЛГ.СУММА * 2 | деньги")
schema = {"ДОЛГ.СУММА": FieldType.NUMBER}
data = {"ДОЛГ.СУММА": "1 000,5"}

print(engine.validate(placeholder, schema))
print(engine.evaluate(placeholder, data))
print(engine.render_text("Сумма: [ДОЛГ.СУММА | деньги: полно]", data))
```

Output:

```
[]
2 001,00 руб.
Сумма: 1 000,50 рублей
```

The empty list on the first line means there are no problems.

## Syntax

A placeholder is a **value** followed by a chain of functions separated by `|`:

```
[ value | function | function: argument, argument ]
```

| Placeholder                              | What it does                                       |
| ---------------------------------------- | -------------------------------------------------- |
| `[ПОЛЕ]`                                 | takes the value of a field                         |
| `[ДОЛГ.СУММА]`, `[А.Б.В]`                | a field name may contain dots, e.g. as a hierarchy |
| `[родился]`                              | a word as plain text                               |
| `[100]`, `[-ПОЛЕ]`                       | a number                                           |
| `[(ДОЛГ.СУММА + ПЕНИ.СУММА) * 0.01]`     | arithmetic: `+ - * /` and parentheses              |
| `[ФИО.ПОЛНОЕ \| падеж: род]`             | a function with an argument                        |
| `[ФИО.ПОЛНОЕ \| падеж: род \| инициалы]` | a chain: the result of one function feeds the next |
| `[ЧИСЛО.ДЕЛ \| число: текст, женский]`   | several arguments separated by commas              |
| `[родился \| согласуй: ФИО.ПОЛНОЕ]`      | a function argument can be a field                 |
| `[DEBT.AMOUNT * 2 \| money: short]`      | the same syntax in Latin                           |

Rules:

- A name in UPPERCASE letters is a field (`ПОЛЕ`, `DEBT`, `ДОЛГ.СУММА`, `DEBT.AMOUNT`). Functions and words are lowercase. Only Cyrillic and Latin letters are allowed; a name starts with a letter.
- An argument is a word, a number or a field. There is no arithmetic inside an argument.
- Arithmetic (`+ - * /`) is allowed only in the value, before the first function: the result of a function cannot go back into arithmetic. Compute first, then apply functions: `[А.Б * 2 | округлить: 1]`.
- In the template text the decimal part is written with a dot (`0.5`), because a comma separates arguments. In data a comma is accepted: `"1 000,5"`.
- There are no quoted strings, conditions, loops or nested calls `f(g(x))`: use the chain `x | g | f` instead.

A syntax error is a `ParseError` carrying the character position: `UnexpectedCharacterError` (for example `$` or a Greek letter), `UnexpectedTokenError` (for example an unclosed parenthesis), `InvalidNumberError`, `LimitExceededError`.

## Functions and types

A function is described by `Function(name, run, input_type, output_type, params)`:

- `run(value, args)` is the code of the function. `args` holds exactly one string per `Param`: an omitted argument is replaced by its default, a field by its value from `data`.
- `Param(choices, default)` is one argument: the allowed words (empty means any) and the default value (`None` makes the argument required).
- A mistake in the description (a name that is not lowercase Latin or Cyrillic letters, a required parameter after an optional one) raises `InvalidSignatureError` as soon as the `Function` is created.

The value keeps its type between functions:

| `FieldType` | Python object     |
| ----------- | ----------------- |
| `TEXT`      | `str`             |
| `NUMBER`    | `decimal.Decimal` |
| `DATE`      | `datetime.date`   |

A `NUMBER → NUMBER` function receives and returns a `Decimal`. Before each call `evaluate` converts the value to the input type: text to a number (`NotNumericError`) and to an ISO 8601 date (`NotDateError`). The result of `evaluate` is always text. An exception inside `run`, or a result of the wrong type, becomes a `FunctionError`.

`validate` is stricter than `evaluate`: the type of the value must match the input type of the function. It returns **all** the problems it finds (`UNKNOWN_FIELD`, `UNKNOWN_FUNCTION`, `TYPE_MISMATCH`, `BAD_ARGUMENT`), so the template author learns about every mistake at once.

## Limits

- A placeholder is at most 500 characters (`Placeholder.MAX_LENGTH`), and parentheses and unary minus nest at most 20 levels (`Placeholder.MAX_NESTING`); beyond that, `LimitExceededError`.
- Arithmetic runs in `Decimal`: `0.1 + 0.2` gives exactly `0.3`; division is exact to 28 significant digits.

## Requirements

Python 3.12 or newer. No dependencies.

## Development

```bash
make test         # tests
make lint         # style check
make format       # auto-format
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

## License

[Apache License 2.0](LICENSE)
