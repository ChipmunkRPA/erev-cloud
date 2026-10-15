"""Narratives cannot introduce figures absent from the authorized numeric evidence."""

from decimal import Decimal, localcontext

import pytest
from erev_api.domain.ai.numbers import validate_numbers


def test_locale_normalisation() -> None:
    result = validate_numbers(
        "On 2026-09-30, 9,764.38 and USD 9,764.38 offset (29,169.29).",
        [Decimal("9764.38"), Decimal("-29169.29")],
        minor_unit=2,
    )
    assert result.valid
    assert result.numbers == (Decimal("9764.38"), Decimal("9764.38"), Decimal("-29169.29"))


@pytest.mark.parametrize(
    ("text", "locale"),
    [
        ("9.764,38", "de-DE"),
        ("9\u202f764,38", "fr-FR"),
        ("９,７６４.３８", "en-US"),
        ("٩,٧٦٤.٣٨", "en-US"),
    ],
)
def test_explicit_locales_and_unicode_digits(text: str, locale: str) -> None:
    assert validate_numbers(text, [Decimal("9764.38")], minor_unit=2, locale=locale).valid


def test_untraced_figure_discards_entire_narrative() -> None:
    result = validate_numbers(
        "Revenue 9,764.38; adjustment 10,000.00.", [Decimal("9764.38")], minor_unit=2
    )
    assert not result.valid
    assert result.code == "AI_UNTRACED_FIGURE"


@pytest.mark.parametrize("minor_unit", [0, 2, 3])
def test_comparison_uses_supplied_currency_minor_unit(minor_unit: int) -> None:
    text = "123.0004"
    assert validate_numbers(text, [Decimal("123")], minor_unit=minor_unit).valid
    assert not validate_numbers("123.5", [Decimal("123")], minor_unit=minor_unit).valid


@pytest.mark.parametrize(
    "text", ["12,34.00", "1.2.3", "1e3", ".5", "(-100)", "1" * 129, "⅔", "1/3"]
)
def test_unsupported_numbers_cannot_match_smaller_subtokens(text: str) -> None:
    assert not validate_numbers(text, [1, 2, 3, 5, 12, 34, 100, -100, 1000], minor_unit=2).valid


def test_date_exemption_requires_a_valid_iso_date() -> None:
    assert validate_numbers("As of 2026-09-30.", [], minor_unit=2).valid
    assert not validate_numbers("As of 2026-02-30.", [], minor_unit=2).valid
    assert not validate_numbers("USD 2026", [], minor_unit=2).valid


def test_percentages_require_explicit_displayed_evidence() -> None:
    assert validate_numbers("5%", [5], minor_unit=2).valid
    assert not validate_numbers("5%", [Decimal("0.05")], minor_unit=2).valid


def test_negatives_are_not_silently_made_positive() -> None:
    for text in ("−100", "-100", "(100)", "(USD 100)", "($100)"):
        assert validate_numbers(text, [-100], minor_unit=2).valid
        assert not validate_numbers(text, [100], minor_unit=2).valid


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("1e999999999")])
def test_unbounded_evidence_refused(value: Decimal) -> None:
    with pytest.raises(ValueError, match="AI_INVALID_NUMBER_EVIDENCE"):
        validate_numbers("1", [value], minor_unit=2)


def test_text_limits_and_invalid_unicode_fail_closed() -> None:
    assert not validate_numbers("x" * (2 * 1024 * 1024 + 1), [], minor_unit=2).valid
    assert not validate_numbers("\ud800", [], minor_unit=2).valid


def test_accounting_sign_survives_long_whitespace() -> None:
    text = "(USD" + " " * 1000 + "100" + " " * 1000 + ")"
    assert validate_numbers(text, [-100], minor_unit=2).valid
    assert not validate_numbers(text, [100], minor_unit=2).valid


def test_invalid_configuration_and_evidence() -> None:
    with pytest.raises(ValueError, match="CONFIGURATION"):
        validate_numbers("", [], minor_unit=True)
    with pytest.raises(ValueError, match="CONFIGURATION"):
        validate_numbers("", [], minor_unit=2, locale="unknown")
    with pytest.raises(ValueError, match="EVIDENCE"):
        validate_numbers("", [True], minor_unit=2)
    with pytest.raises(ValueError, match="EVIDENCE"):
        validate_numbers("", [1] * 10001, minor_unit=2)


def test_number_count_is_bounded() -> None:
    result = validate_numbers("1; " * 10001, [1], minor_unit=2)
    assert result.code == "AI_TOO_MANY_NUMBERS"


@pytest.mark.parametrize("text", ["1 000", "- 100", "- USD 100", "--100"])
def test_ambiguous_grouping_and_detached_signs_refuse(text: str) -> None:
    assert not validate_numbers(text, [0, 1, 100, -100], minor_unit=2).valid


def test_accounting_negation_is_independent_of_decimal_context() -> None:
    with localcontext() as context:
        context.prec = 2
        result = validate_numbers("(1,234.56)", [Decimal("-1234.56")], minor_unit=2)
    assert result.valid
    assert result.numbers == (Decimal("-1234.56"),)


@pytest.mark.parametrize("text", ["1٬000", "1٫000", "1\u200b000", "1\u2060000", "1'000", "1’000"])
def test_unrecognized_separator_cannot_split_a_large_amount(text: str) -> None:
    result = validate_numbers(text, [1, 0], minor_unit=2)
    assert not result.valid
    assert result.code == "AI_UNSUPPORTED_NUMBER"


@pytest.mark.parametrize("separator", ["  ", "\t", "\n"])
def test_french_grouping_cannot_split_into_smaller_values(separator: str) -> None:
    assert not validate_numbers("1" + separator + "000", [1, 0], minor_unit=2, locale="fr-FR").valid


@pytest.mark.parametrize("text", ["(100 USD)", "(100 €)", "(100USD)", "(USD 100 USD)"])
def test_accounting_currency_suffix_keeps_negative_sign(text: str) -> None:
    assert not validate_numbers(text, [100], minor_unit=2).valid
    result = validate_numbers(text, [-100], minor_unit=2)
    assert result.valid
    assert result.numbers == (Decimal("-100"),)


@pytest.mark.parametrize("text", ["100−", "100 -", "100 USD-", "100 € -"])
def test_trailing_sign_cannot_be_discarded(text: str) -> None:
    assert not validate_numbers(text, [100], minor_unit=2).valid
