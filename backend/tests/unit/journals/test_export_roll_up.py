"""CLO-14 run roll-up and retry schedule as pure rules (04 §0.5 SMAP-08; PRD SM-08; 05 ADP-12;
BUILD_SPEC CLO-14). CPU-only: ``export.rolled_up`` over batch states — the run response shows the
batches, and the run's one state field is what the close cockpit and the acknowledgement gate
read."""

from __future__ import annotations

from datetime import timedelta

import pytest
from erev_api.db.transitions import TRANSITIONS
from erev_api.domain.journals import export

A, E, K, F, C, D = "approved", "exported", "acknowledged", "failed", "cancelled", "draft"


@pytest.mark.parametrize(
    ("current", "states", "expected"),
    [
        # every batch acknowledged: the run is acknowledged
        (E, [K], K),
        (E, [K, K], K),
        (A, [K, K], K),
        (F, [K, K], K),
        # at least one failed and none exported: failed
        (A, [F], F),
        (E, [F, K], F),
        (A, [F, A], F),
        (E, [F, F], F),
        # otherwise exported, once no batch waits to be sent ("partially acknowledged")
        (A, [E], E),
        (A, [E, K], E),
        (E, [E, K], E),
        (F, [E, F], E),
        (F, [E], E),
        # a batch still waits to be sent: the run stays as it is
        (A, [A, E], A),
        (A, [A, K], A),
        (A, [A], A),
        # nothing to roll up
        (D, [D], D),
        (C, [C, C], C),
        (A, [], A),
    ],
)
def test_smap_08_run_state_rolls_up_from_its_batches(
    current: str, states: list[str], expected: str
) -> None:
    assert export.rolled_up(current, states) == expected
    assert export.rolled_up(current, list(reversed(states))) == expected  # order-free


def test_every_roll_up_follows_the_e_34_pairs() -> None:
    """The run reaches its rolled-up state along pairs the DB-03 trigger admits: ``failed`` and
    ``acknowledged`` are reached through ``exported`` (E-34 has no other way in)."""
    pairs = TRANSITIONS["journal_run"].pairs
    for (start, end), path in export._RUN_PATHS.items():
        assert path[-1] == end
        steps = list(zip((start, *path), path, strict=False))
        assert all(step in pairs for step in steps), (start, end, steps)
    reachable = {(start, end) for start, end in export._RUN_PATHS}
    # every change rolled_up can ask for has a path
    live = (A, E, K, F)
    for current in (A, E, F):
        for first in live:
            for second in live:
                target = export.rolled_up(current, [first, second])
                assert target == current or (current, target) in reachable, (current, first, second)


def test_adp_12_schedule() -> None:
    """30 s × 2^(n − 1) after the n-th failed attempt, at most 15 minutes, at most 8 attempts."""
    assert [export.export_delay(attempt) for attempt in range(1, 8)] == [
        timedelta(seconds=30),
        timedelta(minutes=1),
        timedelta(minutes=2),
        timedelta(minutes=4),
        timedelta(minutes=8),
        timedelta(minutes=15),
        timedelta(minutes=15),
    ]
    assert export.RETRY_ATTEMPTS == 8
