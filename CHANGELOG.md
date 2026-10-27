# Changelog

All notable changes to libtexpr will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-27

### Added
- Parser for placeholders such as `[ДОЛГ.СУММА * 2 | деньги: кратко]`: fields, numbers, words, names in Latin or Cyrillic, arithmetic with parentheses and unary minus, and a pipeline of functions with arguments
- `Engine` with `register`, `validate`, `evaluate` and `render_text`, which leaves a placeholder that fails exactly as written
- `Function` and `Param`: a function declares its name, code, input and output types, and arguments with allowed values and defaults
- Typed values between functions: `TEXT` is `str`, `NUMBER` is `Decimal`, `DATE` is `datetime.date`; `evaluate` converts to the input type of each function and always returns text
- Exact arithmetic with `Decimal`; numbers in data may use a comma as the decimal separator and spaces as thousands separators, and dates are `YYYY-MM-DD`
- `validate` returns every problem found: `UNKNOWN_FIELD`, `UNKNOWN_FUNCTION`, `TYPE_MISMATCH` and `BAD_ARGUMENT`
- Errors rooted in `TexprError`: `ParseError` subclasses carry the position of the error, an exception or a wrongly typed result from a function becomes `FunctionError`
- Limits of 500 characters and 20 nesting levels, exposed as `Placeholder.MAX_LENGTH` and `Placeholder.MAX_NESTING` and reported as `LimitExceededError`
- `Placeholder.parse` and `Placeholder.extract` to read a placeholder and to find the placeholders in a text
- No runtime dependencies; Python 3.12 or newer
