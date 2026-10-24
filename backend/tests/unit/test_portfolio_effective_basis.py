"""Historical shared-allocation inputs use the native dated event fold."""

from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from support import golden_streams

from erev_api.domain.contracts.portfolio_allocation import Basis, allocate
from erev_api.domain.contracts.portfolio_effective_basis import from_bundle
from erev_api.problems import Problem

SUBJECT = "Contract 2/POB %231"


def test_later_modifications_do_not_change_an_earlier_allocation_basis():
    full = golden_streams.stream("Contract 2", "09").input_bundle(preset="LEGACY_PARITY")
    before = golden_streams.stream("Contract 2", "07").input_bundle(preset="LEGACY_PARITY")
    day = date(2023, 5, 14)
    historical = from_bundle(full, "ASC606", day, [SUBJECT])
    assert historical == from_bundle(before, "ASC606", day, [SUBJECT])
    assert historical[SUBJECT].entitlement == 8
    assert historical[SUBJECT].ssp == 612
    changed = from_bundle(full, "ASC606", date(2023, 5, 15), [SUBJECT])[SUBJECT]
    assert changed.entitlement == 10  # not the remaining segment's 9 units
    assert changed.ssp == Fraction(1485, 2)
    # The dated native basis feeds the conserving allocator without decimal conversion.
    allocation = allocate(
        Decimal(10), [Basis(changed.subject_key, changed.ssp, changed.entitlement)]
    )
    assert allocation == {SUBJECT: "10"}


def test_unknown_original_subject_is_not_replaced_by_an_available_obligation():
    bundle = golden_streams.stream("Contract 2", "09").input_bundle(preset="LEGACY_PARITY")
    with pytest.raises(Problem, match="Original targets are missing"):
        from_bundle(bundle, "ASC606", date(2023, 5, 15), ["Contract 2/NOT-PRESENT"])


def test_group_cannot_supply_a_basis_before_its_inception():
    bundle = golden_streams.stream("Contract 2", "09").input_bundle(preset="LEGACY_PARITY")
    with pytest.raises(Problem, match="members created after"):
        from_bundle(bundle, "ASC606", date(2000, 1, 1), [SUBJECT])
