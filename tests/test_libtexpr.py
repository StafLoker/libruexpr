from types import SimpleNamespace

import pytest

from libtexpr import (
    ArgumentError,
    DivisionByZeroError,
    DuplicateFunctionError,
    Engine,
    FieldType,
    Function,
    FunctionError,
    InvalidNumberError,
    InvalidSignatureError,
    IssueKind,
    LimitExceededError,
    NotDateError,
    NotNumericError,
    Param,
    ParseError,
    Placeholder,
    UnexpectedCharacterError,
    UnexpectedTokenError,
    UnknownFunctionError,
)

# Every test runs once per vocabulary, so Cyrillic and Latin names are covered by the same cases.
# Sources, data keys and expectations are templates: "{x} | {case}" is filled from the vocabulary.
VOCABULARIES = {
    "ru": SimpleNamespace(
        case="падеж", agree="согласуй", money="деньги", fail="сбой", bad="плохо",
        rnd="округлить", year="год", short_fn="т", date_fn="д",
        gen="род", dat="дат", purple="фиолетовый", born="родился", unknown="нет",
        rub="руб.", person="Иванов", suffix="_приказ",
        name="ФИО.ПОЛНОЕ", amount="СУММА.ЗНАЧЕНИЕ", date="ДАТА", field="ПОЛЕ",
        debt="ДОЛГ", debt_sum="ДОЛГ.СУММА", x="А.Б", y="А.В", deep="А.Б.В", p="А", q="Б",
        missing="НЕТ.ПОЛЯ", court="СУД.РАЙОН", no_field="НЕТ.ПОЛЕ", no_arg="НЕТ.АРГ",
    ),
    "en": SimpleNamespace(
        case="case", agree="agree", money="money", fail="fail", bad="bad",
        rnd="round", year="year", short_fn="t", date_fn="d",
        gen="gen", dat="dat", purple="purple", born="born", unknown="none",
        rub="rub.", person="Smith", suffix="_order",
        name="FULL.NAME", amount="SUM.VALUE", date="DATE", field="FIELD",
        debt="DEBT", debt_sum="DEBT.SUM", x="A.B", y="A.C", deep="A.B.C", p="P", q="Q",
        missing="NO.FIELD", court="COURT.AREA", no_field="NO.REF", no_arg="NO.ARG",
    ),
}  # fmt: skip


def _boom(value: str, args: tuple[str, ...]) -> str:
    raise ValueError("boom")


@pytest.fixture(params=VOCABULARIES)
def w(request: pytest.FixtureRequest) -> SimpleNamespace:
    words = SimpleNamespace(**vars(VOCABULARIES[request.param]))
    words.engine = Engine()
    for function in (
        Function(
            words.case,
            lambda value, args: f"{value}-{args[0]}",
            FieldType.TEXT,
            FieldType.TEXT,
            (Param(frozenset({words.gen, words.dat}), words.gen),),
        ),
        Function(
            words.agree,
            lambda value, args: f"{value}~{args[0]}",
            FieldType.TEXT,
            FieldType.TEXT,
            (Param(),),
        ),
        Function(
            words.money,
            lambda value, args: f"{value} {words.rub}",
            FieldType.NUMBER,
            FieldType.TEXT,
        ),
        Function(words.fail, _boom, FieldType.TEXT, FieldType.TEXT),
        Function(words.bad, lambda value, args: 5, FieldType.TEXT, FieldType.TEXT),
        Function(
            words.rnd, lambda value, args: value.to_integral(), FieldType.NUMBER, FieldType.NUMBER
        ),
        Function(words.year, lambda value, args: str(value.year), FieldType.DATE, FieldType.TEXT),
    ):
        words.engine.register(function)
    return words


def fill(w: SimpleNamespace, template: str) -> str:
    return template.format(**vars(w))


def run(w: SimpleNamespace, src: str, data: dict[str, str] | None = None) -> str:
    filled = {fill(w, key): value for key, value in (data or {}).items()}
    return w.engine.evaluate(Placeholder.parse(fill(w, src)), filled)


def issues(w: SimpleNamespace, src: str) -> list[IssueKind]:
    schema = {w.name: FieldType.TEXT, w.amount: FieldType.NUMBER}
    return [i.kind for i in w.engine.validate(Placeholder.parse(fill(w, src)), schema)]


# --- parse ---


@pytest.mark.parametrize(
    ("src", "error", "position"),
    [
        ("{x} $", UnexpectedCharacterError, 4),
        ("{debt}.Σ", UnexpectedCharacterError, 5),
        ("1.2.3", InvalidNumberError, 0),
        ("({x}", UnexpectedTokenError, 4),
        ("{x} | {case}:", UnexpectedTokenError, None),
    ],
)
def test_malformed_reports_kind_and_position(
    w: SimpleNamespace, src: str, error: type[ParseError], position: int | None
) -> None:
    filled = fill(w, src)
    with pytest.raises(error) as info:
        Placeholder.parse(filled)
    assert info.value.position == (len(filled) if position is None else position)


@pytest.mark.parametrize(
    "src",
    [
        "(" * (Placeholder.MAX_NESTING + 1) + "{p}" + ")" * (Placeholder.MAX_NESTING + 1),
        "-" * (Placeholder.MAX_NESTING + 1) + "{p}",
        "{p}" + " + {p}" * Placeholder.MAX_LENGTH,
    ],
)
def test_limits_raise_parse_error_not_recursion_error(w: SimpleNamespace, src: str) -> None:
    with pytest.raises(LimitExceededError):
        Placeholder.parse(fill(w, src))


def test_nesting_at_the_limit_still_works(w: SimpleNamespace) -> None:
    depth = Placeholder.MAX_NESTING
    assert run(w, "(" * depth + "1" + ")" * depth) == "1"


# --- evaluate ---


def test_pipeline_with_default_and_field_ref_argument(w: SimpleNamespace) -> None:
    src = "{name} | {case} | {case}: {dat} | {agree}: {name}"
    p = w.person
    assert run(w, src, {"{name}": p}) == f"{p}-{w.gen}-{w.dat}~{p}"


def test_precedence_parentheses_and_unary_minus(w: SimpleNamespace) -> None:
    assert run(w, "2 + 3 * 4") == "14"
    assert run(w, "(2 + 3) * 4") == "20"
    assert run(w, "-{x} + 1", {"{x}": "3"}) == "-2"


def test_math_is_exact_decimal(w: SimpleNamespace) -> None:
    data = {"{field}": "0,1", "{x}": "0.2", "{y}": "15 000"}
    assert run(w, "{field} + {x}", data) == "0.3"
    assert run(w, "{y} + {x} * 0.01 | {money}", data) == f"15000.002 {w.rub}"


def test_field_is_a_dotted_path_of_any_depth(w: SimpleNamespace) -> None:
    data = {"{field}": "a", "{debt_sum}": "b", "{deep}": "c"}
    assert [run(w, key, data) for key in data] == ["a", "b", "c"]


def test_values_keep_their_type_between_functions(w: SimpleNamespace) -> None:
    assert run(w, "{field} | {rnd}", {"{field}": "2,6"}) == "3"
    assert run(w, "{field} * 1.5 | {rnd} | {money}", {"{field}": "2"}) == f"3 {w.rub}"
    assert run(w, "{date} | {year}", {"{date}": "2026-03-26"}) == "2026"


def test_missing_field_is_empty(w: SimpleNamespace) -> None:
    assert run(w, "{missing}") == ""


@pytest.mark.parametrize(
    ("src", "data", "error"),
    [
        ("{x} / {y}", {"{x}": "1", "{y}": "0"}, DivisionByZeroError),
        ("{x} + 1", {"{x}": "abc"}, NotNumericError),
        ("{born} | {unknown}", {}, UnknownFunctionError),
        ("{born} | {fail}", {}, FunctionError),
        ("{born} | {case}: {purple}", {}, ArgumentError),
        ("{born} | {money}", {}, NotNumericError),
        ("{date} | {year}", {"{date}": "yesterday"}, NotDateError),
        ("{born} | {bad}", {}, FunctionError),
    ],
)
def test_eval_errors(
    w: SimpleNamespace, src: str, data: dict[str, str], error: type[Exception]
) -> None:
    with pytest.raises(error):
        run(w, src, data)


# --- validate ---


def test_valid(w: SimpleNamespace) -> None:
    assert issues(w, "{amount} * 2 | {money} | {case}: {dat}") == []


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("{court}", [IssueKind.UNKNOWN_FIELD]),
        ("{name} | {money}", [IssueKind.TYPE_MISMATCH]),
        ("-{name}", [IssueKind.TYPE_MISMATCH]),
        ("{name} | {case}: {purple}", [IssueKind.BAD_ARGUMENT]),
        ("{name} | {case}: {name}", [IssueKind.BAD_ARGUMENT]),
        ("{name} | {money}: {born}", [IssueKind.TYPE_MISMATCH, IssueKind.BAD_ARGUMENT]),
        ("{name} | {agree}", [IssueKind.BAD_ARGUMENT]),
        ("{amount} | {unknown} | {money}", [IssueKind.UNKNOWN_FUNCTION]),
        (
            "{no_field} | {money} | {unknown} | {agree}: {no_arg}",
            [
                IssueKind.UNKNOWN_FIELD,
                IssueKind.TYPE_MISMATCH,
                IssueKind.UNKNOWN_FUNCTION,
                IssueKind.UNKNOWN_FIELD,
            ],
        ),
    ],
)
def test_validate_collects_every_issue(
    w: SimpleNamespace, src: str, expected: list[IssueKind]
) -> None:
    assert issues(w, src) == expected


# --- functions ---


def test_register_rejects_duplicate(w: SimpleNamespace) -> None:
    with pytest.raises(DuplicateFunctionError):
        w.engine.register(Function(w.case, lambda v, a: v, FieldType.TEXT, FieldType.TEXT))


@pytest.mark.parametrize(
    ("name", "params"),
    [
        ("", ()),
        ("{field}", ()),
        ("{case}1", ()),
        ("{case}", (Param(default="a"), Param())),
        ("{case}", (Param(frozenset({"a"}), "b"),)),
    ],
)
def test_function_rejects_bad_signature(
    w: SimpleNamespace, name: str, params: tuple[Param, ...]
) -> None:
    with pytest.raises(InvalidSignatureError):
        Function(fill(w, name), lambda v, a: v, FieldType.TEXT, FieldType.TEXT, params)


# --- text ---


def test_placeholder_extract(w: SimpleNamespace) -> None:
    text = fill(w, "[{x} | {case}: {gen}] and [{y}]")
    assert Placeholder.extract(text) == [
        fill(w, "{x} | {case}: {gen}"),
        fill(w, "{y}"),
    ]
    assert Placeholder.extract("plain text") == []


def test_render_text(w: SimpleNamespace) -> None:
    data = {fill(w, "{x}"): w.person}
    assert w.engine.render_text(fill(w, "[{x}]{suffix}"), data) == f"{w.person}{w.suffix}"
    broken = fill(
        w,
        "[not valid !!]_[1 / 0]_[{born} | {unknown}]_[{born} | {fail}]_[{born} | {case}: {purple}]",
    )
    assert w.engine.render_text(broken, {}) == broken


# --- numbers ---


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1 000,5", "1001.5"),
        ("1 000", "1001"),
        ("-3", "-2"),
        (".5", "1.5"),
        ("15000.50", "15001.5"),
    ],
)
def test_number_data_formats(w: SimpleNamespace, raw: str, expected: str) -> None:
    assert run(w, "{x} + 1", {"{x}": raw}) == expected


@pytest.mark.parametrize("raw", ["1e3", "inf", "nan", "1,000.50", ""])
def test_number_data_rejects_other_notations(w: SimpleNamespace, raw: str) -> None:
    with pytest.raises(NotNumericError):
        run(w, "{x} + 1", {"{x}": raw})


def test_number_result_has_no_exponent_or_negative_zero(w: SimpleNamespace) -> None:
    assert run(w, "100 / 1") == "100"
    assert run(w, "0 * -1") == "0"


# --- regressions from code review ---


def test_long_numbers_keep_every_digit(w: SimpleNamespace) -> None:
    assert run(w, "12345678901234567890123456789") == "12345678901234567890123456789"


def test_huge_product_is_an_eval_error(w: SimpleNamespace) -> None:
    data = {"{p}": "9" * 600_000, "{q}": "9" * 600_000}
    with pytest.raises(NotNumericError):
        run(w, "{p} * {q}", data)


def test_malformed_number_argument_is_a_parse_error(w: SimpleNamespace) -> None:
    with pytest.raises(InvalidNumberError):
        Placeholder.parse(fill(w, "{p} | {short_fn}: 1.2.3"))


def test_date_must_be_iso_with_dashes(w: SimpleNamespace) -> None:
    engine = Engine()
    engine.register(Function(w.date_fn, lambda v, _: str(v.year), FieldType.DATE, FieldType.TEXT))
    src = Placeholder.parse(fill(w, "{p} | {date_fn}"))
    assert engine.evaluate(src, {w.p: "2026-01-05"}) == "2026"
    with pytest.raises(NotDateError):
        engine.evaluate(src, {w.p: "2026-W01-1"})


# --- alphabets ---


def test_mixed_alphabets_in_one_placeholder() -> None:
    engine = Engine()
    engine.register(Function("twice", lambda v, _: v * 2, FieldType.TEXT, FieldType.TEXT))
    data = {"ДОЛГ.AMOUNT": "ab"}
    assert engine.evaluate(Placeholder.parse("ДОЛГ.AMOUNT | twice"), data) == "abab"


@pytest.mark.parametrize("src", ["ΣΟΥΜ", "金額"])
def test_other_alphabets_are_rejected(src: str) -> None:
    with pytest.raises(UnexpectedCharacterError):
        Placeholder.parse(src)
