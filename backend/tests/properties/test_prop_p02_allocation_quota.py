"""PROP:P2 allocation quota (dev-guide §9.7; POLICIES ALG-01 §2.1.2; REQ-ALC-002, REQ-ALC-003)."""

from __future__ import annotations

from fractions import Fraction

import pytest
from erev_engine.money import largest_remainder
from hypothesis import given
from support.strategies import AllocationCase, allocation_cases

pytestmark = pytest.mark.property


@given(case=allocation_cases())
def test_p02_quota_within_one_minor_unit(case: AllocationCase) -> None:
    amounts = largest_remainder(case.total_minor, case.weights, case.keys)
    total_weight = sum(case.weights)
    assert sum(amounts) == case.total_minor
    for amount, weight in zip(amounts, case.weights, strict=True):
        quota = Fraction(case.total_minor) * weight / total_weight
        assert abs(amount - quota) < 1
