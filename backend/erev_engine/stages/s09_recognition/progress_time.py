"""Stage 09 time-elapsed progress (ENGINE_SPEC_B §9.2.3 S09-R-08, S09-R-09; ALG-11; ENC-1, ENC-2).

The convention is the E-21 value pinned on the obligation, else the resolved POL-090
``recognition.time_convention`` (pin K). On the inception basis f(d) runs over the segment's
updated term; since a 25-13(a) boundary, g(d) restarts the convention on [boundary date, updated
end] (ALG-11 rule 5; CV-62). Periods are the performing entity's accounting periods, so partial
periods and the day-15 threshold follow its E-50 calendar (ALG-11 rule 3); a ``MONTHLY`` calendar
uses calendar months. The start never precedes ``recognition_start_date`` (V5). A custodial
obligation starts on the later of its start and the first bill-and-hold control transfer of its
contract (S09-R-09). A ``TERMINATION`` segment gives f = 1 from its effective date (S09-R-06).
Values come from the registered formula, so the trace node reproduces them (DG-KRN-EXP-04).
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import dates
from erev_engine.bundle import PeriodInput
from erev_engine.errors import EngineError
from erev_engine.formulas import FORMULAS, periods_param
from erev_engine.progress import TIME_CONVENTIONS
from erev_engine.stages.state import AllocationSegment, BookContext, ObligationState, SegmentCause

__all__ = [
    "PROSPECTIVE_FORMULA",
    "TIME_FORMULAS",
    "Progress",
    "calendar_of",
    "convention_of",
    "progress",
    "term_of",
]

TIME_FORMULAS: Final[Mapping[str, str]] = MappingProxyType(
    {
        convention: f"rec.progress.time_elapsed.{convention.lower()}.v1"
        for convention in TIME_CONVENTIONS
    }
)
PROSPECTIVE_FORMULA: Final = "rec.progress.prospective_segment.v1"


@dataclass(frozen=True, slots=True)
class Progress:
    """Exact progress in [0, 1] with the formula id and params that reproduce it (S09-INV-10)."""

    value: Fraction
    formula_id: str
    params: Mapping[str, str]


def convention_of(ctx: BookContext, ob: ObligationState) -> str:
    """The E-21 convention pinned on the obligation, else the resolved POL-090 value (S09-R-08)."""
    convention: object = ob.ratable_convention
    if convention is None:
        convention = ctx.policies.value(
            "recognition.time_convention",
            contract=ob.contract_key,
            obligation=ob.subject_key,
            entity=ob.performing_entity,
        )
    if not isinstance(convention, str) or str(convention) not in TIME_CONVENTIONS:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "a time-elapsed obligation carries no ratable convention",
            subject_key=ob.subject_key,
            detail={"rule": "S09-R-08"},
        )
    return str(convention)


def term_of(ob: ObligationState, seg: AllocationSegment) -> tuple[date, date]:
    """[s, e] of §9.2.3: the boundary date since a PROSPECTIVE boundary, else the term start.

    A PROSPECTIVE segment whose updated totals start later than its boundary starts there: an
    ``OPENING_BALANCE`` segment records the day after the cutover, because the imported cumulative
    revenue covers the cutover date itself (S07-R-04; S07-INV-01).
    """
    start: date | None
    if seg.basis == "PROSPECTIVE":
        start = seg.effective_date
        if seg.totals.start_date is not None:
            start = max(start, seg.totals.start_date)
    else:
        start = seg.totals.start_date or ob.start_date
    end = seg.totals.end_date or ob.end_date
    if start is None or end is None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "a time-elapsed segment has no term",
            subject_key=ob.subject_key,
            detail={"rule": "CV-45"},
        )
    if ob.recognition_start_date is not None:
        start = max(start, ob.recognition_start_date)
    return start, end


def calendar_of(ctx: BookContext, ob: ObligationState) -> tuple[PeriodInput, ...] | None:
    """The performing entity's periods; None for a ``MONTHLY`` calendar (ALG-11 rule 3; C-04)."""
    entity = ctx.entities.get(ob.performing_entity)
    if entity is None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the performing entity has no calendar",
            subject_key=ob.subject_key,
            detail={"rule": "CV-12"},
        )
    if entity.calendar_pattern == "MONTHLY":
        return None
    return tuple(sorted(entity.periods, key=lambda period: (period.start_date, period.end_date)))


def progress(
    ctx: BookContext,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    *,
    custodial_start: date | None = None,
) -> Progress:
    """f(d) on the inception basis or g(d) since a boundary, for the segment in force at ``d``.

    ``custodial_start`` is the first bill-and-hold control transfer of the contract; it is read
    only for a ``CUSTODIAL`` obligation, which recognises nothing until that transfer exists.
    """
    convention = convention_of(ctx, ob)
    prospective = seg.basis == "PROSPECTIVE"
    formula_id = PROSPECTIVE_FORMULA if prospective else TIME_FORMULAS[convention]
    start, end = term_of(ob, seg)
    params: dict[str, str] = {"as_of": d.isoformat(), "convention": convention}
    if prospective:
        params["measure"] = "TIME_ELAPSED"
    if seg.cause == SegmentCause.TERMINATION:
        start = end = seg.effective_date
        params["rule"] = "S09-R-06"
    elif str(ob.obligation_kind) == "CUSTODIAL":
        if custodial_start is None:
            params["pending"] = "true"
        else:
            start = max(start, custodial_start)
    params["start"] = start.isoformat()
    params["end"] = end.isoformat()
    calendar = calendar_of(ctx, ob)
    counted = convention != "DAILY" and "rule" not in params and "pending" not in params
    if calendar is not None and counted and start <= end:
        params["periods"] = periods_param(dates.covering_periods(calendar, start, end))
    frozen = MappingProxyType(dict(sorted(params.items())))
    return Progress(FORMULAS[formula_id]((), frozen), formula_id, frozen)
