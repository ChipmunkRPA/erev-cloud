"""Money kernel (dev-guide §5.9 DG-KRN-MONEY-01, 02, 05, 06; POLICIES ALG-01 §2.1.1, §2.1.2)."""

from __future__ import annotations

import dataclasses
from decimal import (
    ROUND_HALF_UP,
    Decimal,
    DivisionByZero,
    FloatOperation,
    InvalidOperation,
    Overflow,
)
from fractions import Fraction

import pytest
from erev_engine.errors import EngineError
from erev_engine.money import (
    DECIMAL_CONTEXT,
    EXACT_PLACES,
    Money,
    decimal_to_minor,
    format_exact,
    format_money,
    largest_remainder,
    minor_to_decimal,
    round_half_up,
    to_fraction,
)

KEYS = ["POB-001", "POB-002", "POB-003"]


def _by_key(total: int, weights: list[int], keys: list[str]) -> dict[str, int]:
    return dict(zip(keys, largest_remainder(total, weights, keys), strict=True))


def test_largest_remainder_errors_and_order_independence() -> None:
    with pytest.raises(EngineError) as negative:
        largest_remainder(100, [1, -1], KEYS[:2])
    assert negative.value.code == "NEGATIVE_WEIGHT"
    assert negative.value.subject_key == "POB-002"
    with pytest.raises(EngineError) as zero:
        largest_remainder(100, [0, 0], KEYS[:2])
    assert zero.value.code == "TOTAL_WEIGHT_ZERO"

    for total, weights in ((3, [1, 2, 3]), (2, [1, 1, 1]), (-10000, [1, 1, 1]), (7, [0, 5, 5])):
        forward = _by_key(total, weights, KEYS)
        backward = _by_key(total, weights[::-1], KEYS[::-1])
        assert forward == backward
        assert sum(forward.values()) == total
    # Equal remainders and weights: ascending key receives the extra minor units.
    assert _by_key(2, [1, 1, 1], KEYS) == {"POB-001": 1, "POB-002": 1, "POB-003": 0}
    # A zero weight receives nothing.
    assert _by_key(7, [0, 5, 5], KEYS)["POB-001"] == 0


def test_largest_remainder_rejects_malformed_input() -> None:
    with pytest.raises(ValueError, match="same length"):
        largest_remainder(100, [1, 1], KEYS)
    with pytest.raises(ValueError, match="unique"):
        largest_remainder(100, [1, 1], ["POB-001", "POB-001"])
    with pytest.raises(TypeError):
        largest_remainder(100, [0.5, 0.5], KEYS[:2])  # type: ignore[list-item]
    with pytest.raises(TypeError):
        largest_remainder(True, [1], KEYS[:1])


def test_round_half_up_symmetric() -> None:
    assert round_half_up(Fraction(5, 1000), 2) == 1
    assert round_half_up(Fraction(-5, 1000), 2) == -1
    assert round_half_up(Fraction(4999, 1000000), 2) == 0
    assert round_half_up(Decimal("-2.5"), 0) == -3
    assert round_half_up(1300, 2) == 130000
    assert format(minor_to_decimal(0, 2), "f") == "0.00"
    assert format(minor_to_decimal(round_half_up(Fraction(-4, 1000), 2), 2), "f") == "0.00"
    assert minor_to_decimal(-1230, 2) == Decimal("-12.30")
    with pytest.raises(ValueError):
        round_half_up(Fraction(1, 3), EXACT_PLACES + 1)


def test_to_fraction_rejects_float_bool_and_exponent() -> None:
    with pytest.raises(TypeError):
        to_fraction(1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        to_fraction(True)
    with pytest.raises(ValueError):
        to_fraction("1E+2")
    with pytest.raises(ValueError):
        to_fraction(Decimal("NaN"))
    assert to_fraction("-12.30") == Fraction(-123, 10)
    assert to_fraction(Decimal("0.1")) == Fraction(1, 10)
    assert to_fraction(7) == Fraction(7)


def test_decimal_to_minor_exact_only() -> None:
    assert decimal_to_minor(Decimal("12.30"), 2) == 1230
    assert decimal_to_minor(Decimal("12.300"), 2) == 1230
    assert decimal_to_minor(Decimal("-0.00"), 2) == 0
    assert decimal_to_minor(Decimal("1200"), 0) == 1200
    with pytest.raises(ValueError):
        decimal_to_minor(Decimal("12.305"), 2)
    with pytest.raises(TypeError):
        decimal_to_minor(12.3, 2)  # type: ignore[arg-type]


def test_format_money_minor_units() -> None:
    assert format_money(1200, 0) == "1200"
    assert format_money(1230, 2) == "12.30"
    assert format_money(1250, 3) == "1.250"
    assert format_money(-5, 2) == "-0.05"
    assert format_money(0, 4) == "0.0000"


def test_format_exact_places_and_trimming() -> None:
    assert format_exact(Fraction(5, 2)) == "2.5"
    assert format_exact(Fraction(2, 3)) == "0.666666666666666667"
    assert format_exact(Fraction(-2, 3)) == "-0.666666666666666667"
    assert format_exact(Fraction(1, 10**19)) == "0"
    assert format_exact(Decimal("12.3400")) == "12.34"
    assert format_exact(Fraction(5, 2), places=0) == "3"


def test_decimal_context() -> None:
    assert DECIMAL_CONTEXT.prec == 38
    assert DECIMAL_CONTEXT.rounding == ROUND_HALF_UP
    for signal in (FloatOperation, InvalidOperation, DivisionByZero, Overflow):
        assert DECIMAL_CONTEXT.traps[signal]


def test_money_value_object() -> None:
    amount = Money(minor=1230, currency="USD")
    with pytest.raises(dataclasses.FrozenInstanceError):
        amount.minor = 1  # type: ignore[misc]
    with pytest.raises(TypeError):
        Money(minor=True, currency="USD")
    with pytest.raises(ValueError):
        Money(minor=1, currency="usd")
