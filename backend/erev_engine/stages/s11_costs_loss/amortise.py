"""Stage 11 amortisation segments (ENGINE_SPEC_B §11.2.3; POL-143, POL-090; JET-09b; ENC-15).

An asset amortises by segments. Each segment amortises its base, the carrying amount after the event
that starts it, from its start to its end, with progress f cumulatively rounded over its own base,
so each segment completes exactly at its base (S11-R-06; S11-INV-02). A segment stops the day
before the next starts (S11-R-07). Under ``STRAIGHT_LINE`` f is ALG-11 over [start, end] with the
POL-090 convention and the contracting entity's calendar. Under ``PROPORTIONAL_TO_RELATED_REVENUE``
f = (C_d − C_0) ÷ (A − C_0): the related obligations' posted revenue since the segment start over
their posted allocation not yet recognised at its start, capped at 1. Standard library only
(DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import money, progress
from erev_engine.bundle import PeriodInput
from erev_engine.errors import EngineError
from erev_engine.formulas import periods_param, rational_param
from erev_engine.stages.s11_costs_loss.capitalise import STRAIGHT_LINE, CostAssetSpec
from erev_engine.stages.state import BookContext, ObligationState, Target

__all__ = [
    "ACCELERATION",
    "CAPITALISATION",
    "CLAWBACK",
    "IMPAIRMENT",
    "PERIOD_CHANGE",
    "PROPORTIONAL_FORMULA",
    "REVERSAL",
    "STRAIGHT_LINE_FORMULA",
    "Amortised",
    "CostSegment",
    "Revenue",
    "amortised",
]

STRAIGHT_LINE_FORMULA: Final = "cost.amortise.straight_line.v1"
PROPORTIONAL_FORMULA: Final = "cost.amortise.proportional.v1"
CAPITALISATION: Final = "CAPITALISATION"  # §11.2.3 CostSegment.cause
IMPAIRMENT: Final = "IMPAIRMENT"
REVERSAL: Final = "REVERSAL"
CLAWBACK: Final = "CLAWBACK"
ACCELERATION: Final = "ACCELERATION"
PERIOD_CHANGE: Final = "PERIOD_CHANGE"


@dataclass(frozen=True, slots=True)
class CostSegment:
    """One amortisation segment of an asset (§11.2.3)."""

    start: date  # first day amortised in this segment
    end: date  # last day of the amortisation period
    base: int  # carrying amount at the start of the segment, minor units
    cause: str  # CAPITALISATION | IMPAIRMENT | REVERSAL | CLAWBACK | ACCELERATION | PERIOD_CHANGE


@dataclass(frozen=True, slots=True)
class Amortised:
    """``amortised_cum`` through a date with the node's formula and params."""

    value: int
    formula_id: str
    params: Mapping[str, str]


class Revenue:
    """Posted revenue targets and posted allocations of obligations by date (stage 09 output)."""

    def __init__(
        self,
        ctx: BookContext,
        targets: Sequence[Target],
        obligations: Mapping[str, ObligationState],
    ) -> None:
        ends = {
            (code, period.period_key): period.end_date
            for code, calendar in ctx.entities.items()
            for period in calendar.periods
        }
        grouped: dict[str, list[tuple[date, Target]]] = {}
        for target in targets:
            if target.measure != "revenue_cum":
                continue
            end = ends.get((target.entity, target.period_key))
            if end is None:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "a target names a period absent from its entity's calendar",
                    subject_key=target.subject_key,
                    detail={"rule": "CV-12", "period_key": target.period_key},
                )
            grouped.setdefault(target.subject_key, []).append((end, target))
        self._series = {
            key: tuple(sorted(items, key=lambda item: item[0])) for key, items in grouped.items()
        }
        self._obligations = obligations

    def target(self, subject_key: str, d: date) -> Target | None:
        """The revenue target of the latest period ending on or before ``d``."""
        found: Target | None = None
        for end, target in self._series.get(subject_key, ()):
            if end > d:
                break
            found = target
        return found

    def value(self, subject_key: str, d: date) -> int:
        found = self.target(subject_key, d)
        return 0 if found is None else found.value

    def allocation(self, subject_key: str, d: date) -> int:
        """A_p of the ``FIXED`` segment in force at ``d`` by effective date, 0 before the first."""
        posted = 0
        for seg in self._obligations[subject_key].segments:
            if seg.component == "FIXED" and seg.effective_date <= d:
                posted = seg.a_posted
        return posted


def _progress(
    spec: CostAssetSpec,
    seg: CostSegment,
    d: date,
    revenue: Revenue,
    calendar: Sequence[PeriodInput] | None,
) -> Fraction:
    """``segment_progress`` of §11.2.3 at ``d``; ``calendar`` None means calendar months."""
    if d < seg.start:
        return Fraction(0)
    if spec.amortization_pattern == STRAIGHT_LINE:
        if seg.start > seg.end:
            return Fraction(1)
        return progress.time_fraction(
            spec.time_convention, seg.start, seg.end, d, calendar=calendar
        )
    keys = spec.related_obligation_keys
    related_a = sum(revenue.allocation(key, d) for key in keys)
    earned = sum(revenue.value(key, d) for key in keys)
    before = sum(revenue.value(key, seg.start - timedelta(days=1)) for key in keys)
    if related_a == before:
        return Fraction(1)
    return min(Fraction(1), max(Fraction(0), Fraction(earned - before, related_a - before)))


def amortised(
    spec: CostAssetSpec,
    segments: Sequence[CostSegment],
    d: date,
    revenue: Revenue,
    calendar: Sequence[PeriodInput] | None,
    mu: int,
) -> Amortised:
    """``amortised_cum`` of §11.2.3 through ``d``: each segment through the day before the next."""
    scale: int = 10**mu
    total = 0
    straight: list[str] = []
    proportional: list[str] = []
    for index, seg in enumerate(segments):
        if d < seg.start:
            break
        stop = segments[index + 1].start - timedelta(days=1) if index + 1 < len(segments) else d
        g = _progress(spec, seg, min(d, stop), revenue, calendar)
        total += money.cumulative_posted(Fraction(seg.base, scale), seg.base, g, mu)
        straight.append(f"{seg.start.isoformat()}/{seg.end.isoformat()}/{seg.base}")
        proportional.append(f"{seg.base}/{rational_param(g)}")
    if spec.amortization_pattern == STRAIGHT_LINE:
        params = {
            "as_of": d.isoformat(),
            "convention": spec.time_convention,
            "segments": ";".join(straight),
        }
        if calendar is not None:  # absent: calendar months (formulas._calendar)
            params["periods"] = periods_param(calendar)
        return Amortised(total, STRAIGHT_LINE_FORMULA, MappingProxyType(params))
    params = {"as_of": d.isoformat(), "segments": ";".join(proportional)}
    return Amortised(total, PROPORTIONAL_FORMULA, MappingProxyType(params))
