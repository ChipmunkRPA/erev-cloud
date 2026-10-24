"""Explicit historical targets are not screened by today's projection classification."""

from uuid import uuid4

import pytest

from erev_api.domain.contracts.portfolio_preview import _target_candidates


@pytest.mark.parametrize(
    "scope,method",
    [
        ("IN_SCOPE_606", "POINT_IN_TIME"),
        ("LEASE_842", "REDEMPTION_PATTERN"),
    ],
)
def test_explicit_targets_keep_identity_despite_later_classification(scope, method):
    original = dict(
        obligation_key="POINTS", obligation_id=uuid4(), scope_flag=scope, recognition_method=method
    )
    other = dict(original, obligation_key="OTHER", obligation_id=uuid4())
    assert _target_candidates([original, other], {"POINTS"}, set()) == [original]
    # Unspecified populations retain their current eligibility policy.
    assert _target_candidates([original, other], set(), set()) == []


def test_missing_explicit_key_never_substitutes_an_eligible_current_target():
    current = dict(
        obligation_key="OTHER",
        obligation_id=uuid4(),
        scope_flag="IN_SCOPE_606",
        recognition_method="REDEMPTION_PATTERN",
    )
    assert _target_candidates([current], {"POINTS"}, set()) == []
