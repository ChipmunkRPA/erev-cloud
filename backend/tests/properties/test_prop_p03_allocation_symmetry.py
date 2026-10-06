"""PROP:P3 allocation symmetry (dev-guide §9.7; POLICIES ALG-01 §2.1.2; REQ-ALC-002)."""

from __future__ import annotations

import pytest
from erev_engine.money import largest_remainder
from hypothesis import given
from hypothesis import strategies as st
from support.strategies import AllocationCase, allocation_cases

pytestmark = pytest.mark.property


@given(case=allocation_cases(), data=st.data())
def test_p03_symmetry(case: AllocationCase, data: st.DataObject) -> None:
    amounts = dict(
        zip(case.keys, largest_remainder(case.total_minor, case.weights, case.keys), strict=True)
    )
    for key, weight in zip(case.keys, case.weights, strict=True):
        if weight == 0:
            assert amounts[key] == 0
    order = data.draw(st.permutations(range(len(case.keys))))
    keys = [case.keys[index] for index in order]
    shuffled = largest_remainder(case.total_minor, [case.weights[index] for index in order], keys)
    assert dict(zip(keys, shuffled, strict=True)) == amounts
    negated = largest_remainder(-case.total_minor, case.weights, case.keys)
    assert negated == [-amounts[key] for key in case.keys]
