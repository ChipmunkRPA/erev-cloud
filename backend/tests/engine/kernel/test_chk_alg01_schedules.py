"""POLICIES ALG-01 §2.1.4 and §2.1.5 schedule checks.

CHK-002, CHK-004 to CHK-007 under cumulative rounding (ALG-01 §2.1.3; D-11a; ENGINE_SPEC CV-35).
"""

from __future__ import annotations

from fractions import Fraction

from erev_engine.currencies import ISO_4217
from erev_engine.money import (
    cumulative_posted,
    format_exact,
    format_money,
    largest_remainder,
    period_amounts,
)

USD = ISO_4217["USD"].minor_unit
KEYS = ["POB-001", "POB-002", "POB-003", "POB-004"]


def _formatted(amounts: list[int]) -> list[str]:
    return [format_money(amount, USD) for amount in amounts]


def _even_progress(periods: int) -> list[Fraction]:
    return [Fraction(k, periods) for k in range(1, periods + 1)]


def _schedule(periods: int, high: str, low: str, high_periods: set[int]) -> list[str]:
    return [high if k in high_periods else low for k in range(1, periods + 1)]


def test_chk_002_golden_gt01_gt03_allocations() -> None:
    contracts = (
        (
            130000,
            [500, 368, 150, 1000],
            [32210, 23707, 9663, 64420],
            ["322.1011", "237.0664", "96.6303", "644.2022"],
        ),
        (
            90000,
            [612, 408, 150, 0],
            [47077, 31385, 11538, 0],
            ["470.7692", "313.8462", "115.3846", "0"],
        ),
        (
            95000,
            [612, 544, 150, 0],
            [44518, 39571, 10911, 0],
            ["445.1761", "395.7121", "109.1118", "0"],
        ),
    )
    for total_minor, ssp, posted, exact_4dp in contracts:
        weights = [Fraction(weight) for weight in ssp]
        assert largest_remainder(total_minor, weights, KEYS) == posted
        # CV-34: the exact quota is taken of the posted total.
        total_weight = sum(weights, Fraction(0))
        exact = [Fraction(total_minor, 10**USD) * weight / total_weight for weight in weights]
        assert [format_exact(x, places=4) for x in exact] == exact_4dp
        assert sum(posted) == total_minor


def test_chk_004_ratable_35000_over_24_months() -> None:
    progress = _even_progress(24)
    amounts = period_amounts(Fraction(35000), 3500000, progress, USD)
    assert amounts[:3] == [145833, 145834, 145833]
    assert cumulative_posted(Fraction(35000), 3500000, progress[22], USD) == 3354167
    assert sum(amounts[:23]) == 3354167
    assert amounts[22] == 145834
    assert amounts[23] == 145833
    assert format_money(amounts[23], USD) == "1458.33"  # not 1,458.41
    assert sum(amounts) == 3500000


def test_chk_005_100_over_three_months() -> None:
    assert period_amounts(Fraction(100), 10000, _even_progress(3), USD) == [3333, 3334, 3333]


def test_chk_006_rebaselined_schedules() -> None:
    # (a) S2-EX11-CASEA-OWNPRICES: 35,000.00 over 24 months.
    amounts = period_amounts(Fraction(35000), 3500000, _even_progress(24), USD)
    assert _formatted(amounts) == _schedule(24, "1458.34", "1458.33", {2, 5, 8, 11, 14, 17, 20, 23})

    # (b) S2-WARRANTY-OWN over months 13 to 24, numbered 1 to 12.
    exact = Fraction(10500 * 1000, 11000)
    amounts = period_amounts(exact, 95455, _even_progress(12), USD)
    assert _formatted(amounts) == _schedule(12, "79.55", "79.54", {1, 3, 5, 7, 9, 11, 12})
    assert sum(amounts) == 95455

    # (c) S5-EX63-OWNSSP: custody over 3 years.
    exact = Fraction(1000000 * 30000, 1030000)
    amounts = period_amounts(exact, 2912621, _even_progress(3), USD)
    assert _formatted(amounts) == ["9708.74", "9708.74", "9708.73"]

    # (d) S8-CONTRACT-COSTS ex2: commission 10,000.00 over 7 years.
    amounts = period_amounts(Fraction(10000), 1000000, _even_progress(7), USD)
    assert _formatted(amounts) == _schedule(7, "1428.58", "1428.57", {4})

    # (e) S12-FRANCHISOR-OWN: licence over 10 years.
    exact = Fraction(50000 * 40000, 55000)
    amounts = period_amounts(exact, 3636364, _even_progress(10), USD)
    assert _formatted(amounts) == _schedule(10, "3636.37", "3636.36", {2, 5, 7, 10})

    # (f) S5-UPFRONTFEE-OWN option B: 3,000.00 over 36 months; every third month from month 2.
    amounts = period_amounts(Fraction(3000), 300000, _even_progress(36), USD)
    assert _formatted(amounts) == _schedule(36, "83.34", "83.33", set(range(2, 36, 3)))

    # (g) S6-COMBINED-MOD-OWN: support 70,000.00 over 36 months.
    amounts = period_amounts(Fraction(70000), 7000000, _even_progress(36), USD)
    formatted = _formatted(amounts)
    assert formatted.count("1944.44") == 20
    assert formatted.count("1944.45") == 16
    assert formatted[0] == "1944.44"

    # (h) S6-EX5-CASEB: 8,400.00 over 90 units.
    progress = _even_progress(90)
    amounts = period_amounts(Fraction(8400), 840000, progress, USD)
    assert _formatted(amounts) == ["93.33", "93.34", "93.33"] * 30
    assert (
        format_money(cumulative_posted(Fraction(8400), 840000, progress[59], USD), USD) == "5600.00"
    )
    assert (
        format_money(cumulative_posted(Fraction(8400), 840000, progress[89], USD), USD) == "8400.00"
    )


def test_chk_007_units_rounding_of_exact_allocation() -> None:
    exact = Fraction(1300 * 368, 2018)
    assert cumulative_posted(exact, 23707, Fraction(1, 2), USD) == 11853  # 118.53, not 118.54
    assert cumulative_posted(exact, 23707, Fraction(1), USD) == 23707
    assert period_amounts(exact, 23707, [Fraction(1, 2), Fraction(1)], USD) == [11853, 11854]
