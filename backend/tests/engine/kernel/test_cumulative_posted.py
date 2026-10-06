"""Cumulative schedule helpers (dev-guide §5.9 DG-KRN-MONEY-03; ENGINE_SPEC CV-35, EX-00-A)."""

from __future__ import annotations

from fractions import Fraction

import pytest
from erev_engine.money import cumulative_posted, period_amounts, round_half_up


def test_bounds_and_completion() -> None:
    # EX-00-A: a negative allocation is bounded to [A, 0].
    assert cumulative_posted(Fraction(-100, 3), -3334, Fraction(1, 2), 2) == -1667
    assert cumulative_posted(Fraction(-100, 3), -3334, Fraction(1), 2) == -3334
    assert cumulative_posted(Fraction(100, 3), 3333, Fraction(0), 2) == 0

    # Completion returns A even where round(X) differs from A.
    assert cumulative_posted(Fraction(100009, 1000), 10000, Fraction(1), 2) == 10000
    # Above A before completion: round(100.009 × 0.99999) = 100.01 is bounded to A.
    assert cumulative_posted(Fraction(100009, 1000), 10000, Fraction(99999, 100000), 2) == 10000
    assert cumulative_posted(Fraction(-100009, 1000), -10000, Fraction(99999, 100000), 2) == -10000
    # Across zero: A ≥ 0 bounds below by 0; A < 0 bounds above by 0.
    assert cumulative_posted(Fraction(-9, 1000), 0, Fraction(9, 10), 2) == 0
    assert cumulative_posted(Fraction(1, 100), -1, Fraction(9, 10), 2) == 0

    with pytest.raises(ValueError, match="progress"):
        cumulative_posted(Fraction(100), 10000, Fraction(3, 2), 2)
    with pytest.raises(ValueError, match="progress"):
        cumulative_posted(Fraction(100), 10000, Fraction(-1, 2), 2)

    # POL-210: C_0 is the posted cumulative at cutover.
    exact = Fraction(1000)
    amounts = period_amounts(exact, 100000, [Fraction(1, 2), Fraction(3, 4), Fraction(1)], 2, 29569)
    assert amounts[0] == cumulative_posted(exact, 100000, Fraction(1, 2), 2) - 29569
    assert amounts == [50000 - 29569, 25000, 25000]
    assert period_amounts(exact, 100000, [], 2, 29569) == []


def test_period_amounts_minor_units_and_input_types() -> None:
    # JPY (0 places) and BHD (3 places) at the same exact allocation of 100 over three periods.
    progress = [Fraction(1, 3), Fraction(2, 3), Fraction(1)]
    assert period_amounts(Fraction(100), 100, progress, 0) == [33, 34, 33]
    assert period_amounts(Fraction(100), 100000, progress, 3) == [33333, 33334, 33333]

    with pytest.raises(TypeError):
        cumulative_posted(Fraction(100), 10000, 0.5, 2)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        cumulative_posted(100.0, 10000, Fraction(1, 2), 2)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        cumulative_posted(Fraction(100), True, Fraction(1, 2), 2)
    with pytest.raises(TypeError):
        period_amounts(Fraction(100), 10000, [Fraction(1)], 2, opening_posted_minor=False)
    with pytest.raises(ValueError):
        cumulative_posted(Fraction(100), 10000, Fraction(1, 2), -1)


def test_forbidden_rounding_of_posted_allocation() -> None:
    # DG-KRN-MONEY-03 regression guard over the CHK-007 inputs.
    exact = Fraction(1300 * 368, 2018)
    forbidden = round_half_up(Fraction(23707, 100) * Fraction(1, 2), 2)
    assert forbidden == 11854
    assert cumulative_posted(exact, 23707, Fraction(1, 2), 2) != forbidden
