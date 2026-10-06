"""Stage 09 manual release, deferral and schedule overrides (ENGINE_SPEC_B §9.2.11; ENC-9).

An approved T-SL-05 ``manual_adjustment`` reaches the engine as ``MANUAL_ADJUSTMENT_APPLIED``. The
bundle carries no adjustment rows, so the event payload holds the approved adjustment with handles
resolved to natural keys (04 §16.3; L1-3-Q-14): ``kind`` (E-93), ``obligation_key``,
``period_key`` (the posting period P) and the kind payload, ``amount`` | ``ratio`` |
``remaining`` for ``MANUAL_RELEASE`` and ``MANUAL_DEFER``, and ``periods`` [{``period_key``,
``amount``}] for ``SCHEDULE_OVERRIDE``. ``MANUAL_JOURNAL`` and ``ACCOUNT_RECLASS`` change no target
(S09-R-41). A payload that names a ``book_code`` applies in that book only (T-SL-05 ``book_code``;
ENGINE_SPEC_B rev 1.63). Adjustments apply in ENG-06 order after the segment targets and before
holds; this module parses them and evaluates the registered formulas, and ``components`` supplies
the targets at P and the other dates the rules read. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import PeriodInput
from erev_engine.errors import EngineError
from erev_engine.formulas import FORMULAS, rational_param
from erev_engine.money import to_fraction
from erev_engine.stages.s09_recognition import progress_events
from erev_engine.stages.state import AllocatedState, BookContext, EventView, ObligationState

__all__ = [
    "KINDS",
    "TARGET_FORMULAS",
    "Adjustment",
    "Applied",
    "adjustments",
    "defer_params",
    "evaluate",
    "override_params",
    "previous_period",
    "release_params",
]

KINDS: Final = frozenset(
    {"SCHEDULE_OVERRIDE", "MANUAL_RELEASE", "MANUAL_DEFER", "MANUAL_JOURNAL", "ACCOUNT_RECLASS"}
)  # 04 E-93
TARGET_FORMULAS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "MANUAL_RELEASE": "sched.manual_release.v1",
        "MANUAL_DEFER": "sched.manual_defer.v1",
        "SCHEDULE_OVERRIDE": "sched.override_respread.v1",
    }
)
_BASES: Final = ("amount", "ratio", "remaining")


@dataclass(frozen=True, slots=True)
class Adjustment:
    """One schedule-changing manual adjustment of an obligation (S09-R-38 to S09-R-40)."""

    event: EventView
    kind: str
    period: PeriodInput  # posting period P
    basis: str  # "amount" | "ratio" | "remaining"; "periods" for SCHEDULE_OVERRIDE
    value: Fraction  # the amount (currency units) or the ratio; 1 for "remaining"
    listed: tuple[tuple[PeriodInput, Fraction], ...]  # SCHEDULE_OVERRIDE (period, amount)


@dataclass(frozen=True, slots=True)
class Applied:
    """An adjustment applied at a date: formula, params and the posted target after it."""

    adjustment: Adjustment
    formula_id: str
    params: Mapping[str, str]
    value: int  # minor units


def _invariant(message: str, ob: ObligationState, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED", message, subject_key=ob.subject_key, detail=detail
    )


def _periods(ctx: BookContext, ob: ObligationState) -> tuple[PeriodInput, ...]:
    entity = ctx.entities.get(ob.performing_entity)
    if entity is None:
        raise _invariant("the performing entity has no calendar", ob, rule="CV-12")
    return tuple(sorted(entity.periods, key=lambda period: (period.start_date, period.end_date)))


def _period(
    periods: tuple[PeriodInput, ...], ob: ObligationState, key: object, ev: EventView
) -> PeriodInput:
    if key is None:
        found = next((p for p in periods if p.start_date <= ev.effective_date <= p.end_date), None)
    else:
        found = next((p for p in periods if p.period_key == key), None)
    if found is None:
        raise _invariant(
            "a manual adjustment names no period of the calendar",
            ob,
            rule="CV-45",
            event_key=ev.event_key,
        )
    return found


def _number(value: object, ob: ObligationState, ev: EventView) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal | Fraction):
        raise _invariant(
            "a manual adjustment amount is malformed", ob, rule="CV-45", event_key=ev.event_key
        )
    return to_fraction(value)


def previous_period(periods: tuple[PeriodInput, ...], period: PeriodInput) -> PeriodInput | None:
    """The calendar period before ``period``, if any."""
    before = [p for p in periods if p.end_date < period.start_date]
    return before[-1] if before else None


def adjustments(
    ctx: BookContext, st: AllocatedState, ob: ObligationState
) -> tuple[Adjustment, ...]:
    """Schedule-changing ``MANUAL_ADJUSTMENT_APPLIED`` events of the obligation, ENG-06 order."""
    periods = _periods(ctx, ob)
    found: list[Adjustment] = []
    for ev in st.measure_events:
        if ev.event_type != "MANUAL_ADJUSTMENT_APPLIED" or not progress_events.concerns(ev, ob):
            continue
        payload = ev.payload
        kind = payload.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            raise _invariant(
                "a manual adjustment kind is unknown", ob, rule="T-SL-05", event_key=ev.event_key
            )
        if kind not in TARGET_FORMULAS:
            continue  # S09-R-41: stage 14 posts the approved lines; targets are unchanged
        named = payload.get("book_code")
        if named is not None and named != str(ctx.book_code):
            continue  # S09-R-41: an adjustment applies in the book it names (04 T-SL-05)
        period = _period(periods, ob, payload.get("period_key"), ev)
        if kind == "SCHEDULE_OVERRIDE":
            rows = payload.get("periods")
            if not isinstance(rows, list | tuple) or not rows:
                raise _invariant(
                    "a schedule override lists no periods",
                    ob,
                    rule="S09-R-40",
                    event_key=ev.event_key,
                )
            listed = []
            for row in rows:
                if not isinstance(row, Mapping):
                    raise _invariant(
                        "a schedule override row is malformed",
                        ob,
                        rule="S09-R-40",
                        event_key=ev.event_key,
                    )
                listed_period = _period(periods, ob, row.get("period_key"), ev)
                listed.append((listed_period, _number(row.get("amount"), ob, ev)))
            listed.sort(key=lambda item: item[0].start_date)
            found.append(Adjustment(ev, kind, period, "periods", Fraction(0), tuple(listed)))
            continue
        bases = [basis for basis in _BASES if payload.get(basis) not in (None, False, "false")]
        if len(bases) != 1:
            raise _invariant(
                "a manual release or deferral needs exactly one of amount, ratio and remaining",
                ob,
                rule="T-SL-05",
                event_key=ev.event_key,
            )
        basis = bases[0]
        value = Fraction(1) if basis == "remaining" else _number(payload.get(basis), ob, ev)
        if value < 0 or (basis == "ratio" and value > 1):
            raise _invariant(
                "a manual adjustment value is out of range",
                ob,
                rule="S09-R-38",
                event_key=ev.event_key,
            )
        found.append(Adjustment(ev, kind, period, basis, value, ()))
    return tuple(found)


def _common(adj: Adjustment, *, as_of: date, allocation: int, mu: int) -> dict[str, str]:
    return {
        "allocation": str(allocation),
        "as_of": as_of.isoformat(),
        "event_key": adj.event.event_key,
        "kind": adj.kind,
        "minor_unit": str(mu),
        "period": adj.period.period_key,
    }


def release_params(
    adj: Adjustment, *, as_of: date, c_p: int, allocation: int, mu: int
) -> Mapping[str, str]:
    """Params of ``sched.manual_release.v1`` (S09-R-38)."""
    params = _common(adj, as_of=as_of, allocation=allocation, mu=mu)
    params.update({"basis": adj.basis, "c_p": str(c_p), "value": rational_param(adj.value)})
    return MappingProxyType(dict(sorted(params.items())))


def defer_params(
    adj: Adjustment, *, as_of: date, c_prev: int, allocation: int, mu: int
) -> Mapping[str, str]:
    """Params of ``sched.manual_defer.v1`` (S09-R-39)."""
    params = _common(adj, as_of=as_of, allocation=allocation, mu=mu)
    params.update({"basis": adj.basis, "c_prev": str(c_prev), "value": rational_param(adj.value)})
    return MappingProxyType(dict(sorted(params.items())))


def override_params(
    adj: Adjustment,
    *,
    as_of: date,
    allocation: int,
    mu: int,
    target: int | None = None,
    t_k: int | None = None,
    x_exact: Fraction | None = None,
    f_t: Fraction | None = None,
    f_k: Fraction | None = None,
) -> Mapping[str, str]:
    """Params of ``sched.override_respread.v1``: a listed target, or the S09-R-40 respread."""
    params = _common(adj, as_of=as_of, allocation=allocation, mu=mu)
    if target is not None:
        params.update({"mode": "listed", "target": str(target)})
    else:
        if t_k is None or x_exact is None or f_t is None or f_k is None:
            raise ValueError("a respread needs T_k, X, f(t) and f(t_k)")
        params.update(
            {
                "f_k": rational_param(f_k),
                "f_t": rational_param(f_t),
                "mode": "respread",
                "t_k": str(t_k),
                "x_exact": rational_param(x_exact),
            }
        )
    return MappingProxyType(dict(sorted(params.items())))


def evaluate(
    ob: ObligationState, formula_id: str, value: int, params: Mapping[str, str], mu: int
) -> int:
    """The posted target after an adjustment or hold formula, minor units."""
    scale: int = 10**mu
    try:
        result = FORMULAS[formula_id]((Fraction(value, scale),), params)
    except ValueError as error:
        raise EngineError(
            "NON_FINITE_AMOUNT",
            "the adjusted target is undefined for the obligation",
            subject_key=ob.subject_key,
            formula_id=formula_id,
            detail={"rule": "S09-R-41"},
        ) from error
    scaled = result * scale
    if scaled.denominator != 1:
        raise _invariant("an adjusted target is below the minor unit", ob, rule="C-01")
    return scaled.numerator
