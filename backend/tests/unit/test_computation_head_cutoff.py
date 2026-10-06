"""``computation.head_is_later`` — the way ``head`` of ``behind_its_group`` as a comparison of
two bounds (item COMPUTE-BEHIND-CUTOFF-1, register index 285; 04 §14.1 "A computation behind its
group" rev 1.302; dev-guide DG-CMD-10 rev 1.288). No database: the cases through the product are
``tests/domain/contracts/test_computation_behind_cutoff.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from erev_api.domain.contracts.computation import head_is_later

# The cutoff of a bundle: the start of its transaction, on the database's clock.
CUTOFF = datetime(2026, 10, 3, 3, 4, 50, 897830, tzinfo=UTC)
SECOND = timedelta(seconds=1)
# How far a host's clock runs behind the database's in the measured case.
LAG = timedelta(seconds=20)


def test_a_head_is_later_by_the_cutoff_it_stored_and_strictly() -> None:
    created = CUTOFF - LAG  # the instant of a unit of work on a clock that runs behind
    assert head_is_later(CUTOFF + SECOND, created, CUTOFF) is True
    assert head_is_later(CUTOFF + timedelta(microseconds=1), created, CUTOFF) is True
    # Two computations of one transaction share a cutoff: the second is not behind the first.
    assert head_is_later(CUTOFF, created, CUTOFF) is False
    assert head_is_later(CUTOFF - SECOND, created, CUTOFF) is False


def test_where_a_head_stored_its_cutoff_its_created_at_decides_nothing() -> None:
    for created in (CUTOFF - LAG, CUTOFF, CUTOFF + LAG):
        assert head_is_later(CUTOFF + SECOND, created, CUTOFF) is True
        assert head_is_later(CUTOFF, created, CUTOFF) is False


def test_a_head_stored_before_the_column_answers_by_its_created_at() -> None:
    assert head_is_later(None, CUTOFF + SECOND, CUTOFF) is True
    assert head_is_later(None, CUTOFF, CUTOFF) is False
    # The limit as it stood: an instant behind the bound the head admitted by says nothing.
    assert head_is_later(None, CUTOFF - LAG, CUTOFF) is False
