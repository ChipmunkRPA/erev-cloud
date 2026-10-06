"""Variance between closes: driver decomposition over ordered metric evaluations (ENGINE_SPEC_B
§15.2.8 S15-R-21 to S15-R-23; S15-INV-07; EX-15-D; 03 REQ-RPT-019; BUILD_SPEC EDS-6).

The variance of a metric (a waterfall cell, a balance, RPO) between two lock snapshots is
decomposed by replaying the group's events recorded between the two cutoffs in ENG-06 order and
evaluating the metric at the later as-of date after each maximal run of events with the same driver
(S15-R-21). This module is the pure decomposition: given the metric at the earlier snapshot and the
ordered ``(driver, metric after the run)`` evaluations, ``decompose`` returns one effect per maximal
run and the total. Drivers sum exactly to the metric change (S15-INV-07), and grouping consecutive
events of one driver changes no driver total (S15-R-22 [J]). The platform runs the replays as
``DRY_RUN`` computes (S15-R-23); it is not here.

Values are exact (``Fraction``); the report renders them. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

__all__ = [
    "DRIVERS",
    "Decomposition",
    "DriverEffect",
    "Evaluation",
    "decompose",
    "totals_by_driver",
]

# S15-R-21 drivers, in the order the report lists them.
DRIVERS: Final = (
    "PROGRESS",
    "NEW_CONTRACT",
    "MODIFICATION",
    "ESTIMATE_CHANGE",
    "BILLING",
    "LATE_EVENT",
    "FX",
    "OTHER",
)


@dataclass(frozen=True, slots=True)
class Evaluation:
    """The metric at the later as-of date after one event (or one time step) of ``driver``."""

    driver: str
    value: Fraction
    event_key: str | None = None  # the ENG-06 event replayed; None for a passage-of-time step

    def __post_init__(self) -> None:
        if self.driver not in DRIVERS:
            raise ValueError(f"unknown variance driver {self.driver!r} (S15-R-21)")
        if not isinstance(self.value, Fraction):
            raise TypeError("a metric evaluation is a Fraction (CV-30)")


@dataclass(frozen=True, slots=True)
class DriverEffect:
    """One maximal run of events of one driver: its effect on the metric."""

    driver: str
    amount: Fraction
    event_keys: tuple[str, ...]  # the events of the run, ENG-06 order; () for a time step
    value_after: Fraction


@dataclass(frozen=True, slots=True)
class Decomposition:
    metric_before: Fraction
    metric_after: Fraction
    effects: tuple[DriverEffect, ...]

    @property
    def total(self) -> Fraction:
        return self.metric_after - self.metric_before

    @property
    def sums_exactly(self) -> bool:
        """S15-INV-07: Σ effects = metric(later) − metric(earlier)."""
        return sum((effect.amount for effect in self.effects), Fraction(0)) == self.total


def decompose(metric_before: Fraction, evaluations: Sequence[Evaluation]) -> Decomposition:
    """S15-R-21/22: one ``DriverEffect`` per maximal run of consecutive same-driver evaluations.

    The effect of a run is the metric after its last evaluation less the metric before its first;
    the decomposition therefore sums exactly (a telescoping sum) whatever the grouping. A run
    whose effect is 0 is kept (EX-15-D shows ``PROGRESS`` (time) 0.00 explicitly).
    """
    if not isinstance(metric_before, Fraction):
        raise TypeError("metric_before is a Fraction (CV-30)")
    effects: list[DriverEffect] = []
    previous = metric_before
    run_driver: str | None = None
    run_keys: list[str] = []
    run_start = metric_before
    run_last = metric_before
    for item in evaluations:
        if run_driver is not None and item.driver != run_driver:
            effects.append(
                DriverEffect(run_driver, run_last - run_start, tuple(run_keys), run_last)
            )
            run_start = run_last
            run_keys = []
        run_driver = item.driver
        if item.event_key is not None:
            run_keys.append(item.event_key)
        run_last = item.value
        previous = item.value
    if run_driver is not None:
        effects.append(DriverEffect(run_driver, run_last - run_start, tuple(run_keys), run_last))
    return Decomposition(metric_before, previous, tuple(effects))


def totals_by_driver(effects: Iterable[DriverEffect]) -> dict[str, Fraction]:
    """Σ effect per driver in the S15-R-21 order (the report's driver rows)."""
    totals = {driver: Fraction(0) for driver in DRIVERS}
    for effect in effects:
        totals[effect.driver] += effect.amount
    return totals
