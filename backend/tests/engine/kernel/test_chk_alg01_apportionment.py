"""POLICIES ALG-01 §2.1.4 apportionment checks.

CHK-001 and CHK-003a to CHK-003d; ENGINE_SPEC EX-00-A.
"""

from __future__ import annotations

from erev_engine.currencies import ISO_4217
from erev_engine.money import format_money, largest_remainder

KEYS = ["POB-001", "POB-002", "POB-003"]


def _formatted(amounts: list[int], currency: str) -> list[str]:
    return [format_money(amount, ISO_4217[currency].minor_unit) for amount in amounts]


def test_chk_001_equal_ssp_thirds() -> None:
    result = largest_remainder(10000, [1, 1, 1], KEYS)
    assert result == [3334, 3333, 3333]
    assert _formatted(result, "USD") == ["33.34", "33.33", "33.33"]


def test_chk_003a_jpy_equal_weights() -> None:
    assert ISO_4217["JPY"].minor_unit == 0
    result = largest_remainder(10000, [1, 1, 1], KEYS)
    assert result == [3334, 3333, 3333]
    assert _formatted(result, "JPY") == ["3334", "3333", "3333"]


def test_chk_003b_bhd_weights_one_two() -> None:
    result = largest_remainder(100000, [1, 2], KEYS[:2])
    assert result == [33333, 66667]
    assert _formatted(result, "BHD") == ["33.333", "66.667"]


def test_chk_003c_negative_total() -> None:
    result = largest_remainder(-10000, [1, 1, 1], KEYS)
    assert result == [-3334, -3333, -3333]
    assert _formatted(result, "USD") == ["-33.34", "-33.33", "-33.33"]


def test_chk_003d_tie_broken_by_larger_weight() -> None:
    # Remainders 1/2, 0, 1/2: the tie between POB-001 and POB-003 goes to the larger weight.
    assert largest_remainder(3, [1, 2, 3], KEYS) == [0, 1, 2]
