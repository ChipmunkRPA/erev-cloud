"""05 RCP-15 rev 1.94 (supervisor rulings R-112 (e) and R-114 (d) of 2026-09-30; item
CLO-LOCK-LEGACY-1; 04 §14.1 DB-07 and T-REF-06 rev 1.155): the period states bundle assembly hands
the engine for the LEGACY book. Pure — no database.

The LEGACY book has no close of its own, so its state rows stay postable while the primary book's
periods are locked. The DB-07 guard admits a LEGACY line only while the primary book's period is
postable too; the planner agrees with it by handing the engine the PRIMARY book's state wherever
that state is not postable and the LEGACY row's is. Until this rule ``bundles._entities`` handed
every state as stored and ``handed_states`` did not exist: the engine assigned a LEGACY amount to
a period the primary book had locked.
"""

from __future__ import annotations

import pytest
from erev_api.domain.contracts.bundles import handed_states

PRIMARY = "ASC606"
SECOND = "IFRS15"
LEGACY = "LEGACY"


@pytest.mark.parametrize(
    ("primary", "legacy", "handed"),
    [
        # the primary book's period is not postable and the LEGACY row is: the primary's state
        ("closed", "open", "closed"),
        ("closed", "closing", "closed"),
        ("closed", "reopened", "closed"),
        ("permanently_locked", "open", "permanently_locked"),
        ("future", "open", "future"),
        # both postable: as stored
        ("open", "open", "open"),
        ("closing", "open", "open"),
        ("reopened", "open", "open"),
        ("open", "closing", "closing"),
        ("open", "reopened", "reopened"),
        # the LEGACY row is not postable: as stored, whatever the primary's
        ("open", "closed", "closed"),
        ("closed", "permanently_locked", "permanently_locked"),
        ("open", "future", "future"),
        ("closed", "future", "future"),
        ("future", "closed", "closed"),
    ],
)
def test_rcp_15_the_legacy_state_handed_is_the_primary_books_where_that_is_not_postable(
    primary: str, legacy: str, handed: str
) -> None:
    found = [(LEGACY, legacy), (PRIMARY, primary)]
    assert handed_states(found, PRIMARY) == ((PRIMARY, primary), (LEGACY, handed))


def test_rcp_15_legacy_follows_the_primary_book_alone() -> None:
    """A second posting book's close does not move the LEGACY state (R-114 (d)); the primary is
    the book the tenant flags, whichever its code."""
    found = [(PRIMARY, "open"), (SECOND, "closed"), (LEGACY, "open")]
    assert handed_states(found, PRIMARY) == tuple(found)
    assert handed_states(found, SECOND) == (
        (PRIMARY, "open"),
        (SECOND, "closed"),
        (LEGACY, "closed"),
    )


def test_rcp_15_states_without_a_legacy_or_a_primary_row_are_handed_as_stored() -> None:
    """No LEGACY row, no row of the primary book for the period, or no primary book: nothing is
    rewritten — the engine refuses a period without a state for a kept book by its own rule
    (ENGINE_SPEC CV-13)."""
    posting = [(PRIMARY, "closed"), (SECOND, "open")]
    assert handed_states(posting, PRIMARY) == tuple(posting)
    assert handed_states([(LEGACY, "open")], PRIMARY) == ((LEGACY, "open"),)
    assert handed_states([(LEGACY, "open"), (PRIMARY, "closed")], None) == (
        (PRIMARY, "closed"),
        (LEGACY, "open"),
    )
    assert handed_states([], PRIMARY) == ()


def test_rcp_15_the_pairs_are_handed_in_book_order() -> None:
    """The pairs stay sorted by book code, as ``_entities`` handed them before the rule."""
    found = [(LEGACY, "open"), (SECOND, "open"), (PRIMARY, "closed")]
    assert handed_states(found, PRIMARY) == (
        (PRIMARY, "closed"),
        (SECOND, "open"),
        (LEGACY, "closed"),
    )
