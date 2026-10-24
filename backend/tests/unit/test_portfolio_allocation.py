"""Owner-selected SSP distribution conserves the shared total at database precision."""

from decimal import Decimal as D
from fractions import Fraction

import pytest

from erev_api.domain.contracts.portfolio_allocation import Basis, allocate


def test_ssp_total_and_stable_tail():
    weights = [Basis("A", D(100), D(10)), Basis("B", D(200), D(10))]
    assert allocate(D(9), weights) == {"A": "3", "B": "6"}
    assert allocate(D("0.000000000000000001"), weights) == {"A": "0", "B": "0.000000000000000001"}
    tied = [Basis(k, D(1), D(2)) for k in ("C", "A", "B")]
    expected = {
        "A": "0.333333333333333334",
        "B": "0.333333333333333333",
        "C": "0.333333333333333333",
    }
    assert allocate(D(1), tied) == expected
    assert allocate(D(1), list(reversed(tied))) == expected
    assert sum(map(D, expected.values())) == 1


@pytest.mark.parametrize(
    "total,basis",
    [
        (D(1), []),
        (D(1), [Basis("A", D(0), D(10))]),
        (D(-1), [Basis("A", D(1), D(10))]),
        (D("0.0000000000000000001"), [Basis("A", D(1), D(10))]),
        (D(2), [Basis("A", D(1), D(1))]),
        (D(1), [Basis("A", D(1), D(1)), Basis("A", D(1), D(1))]),
        (D(1), [Basis("A", D("NaN"), D(1))]),
    ],
)
def test_invalid_population_is_not_silently_redistributed(total, basis):
    with pytest.raises(ValueError):
        allocate(total, basis)


def test_native_rational_weights_are_not_rounded_before_distribution():
    # These weights round to the same decimal at 18 places but B owns the larger tail.
    tiny = D("0.000000000000000001")
    weights = [
        Basis("A", Fraction(1, 3), Fraction(10)),
        Basis("B", Fraction(1, 3) + Fraction(1, 10**30), Fraction(10)),
    ]
    assert allocate(tiny, weights) == {"A": "0", "B": "0.000000000000000001"}
    with pytest.raises(ValueError, match="18 decimal places"):
        allocate(D(1), [Basis("A", Fraction(1), Fraction(1, 3))])
