"""Stage 09 recognition holds (ENGINE_SPEC_B §9.2.12 S09-R-42 to S09-R-44; ENC-9).

A ``HOLD_APPLIED`` with ``hold_type = recognition`` (E-45) opens an interval [applied, released)
on its obligation, or on every obligation of its contract when it names none (S09-R-42).
``HOLD_RELEASED.hold_id`` resolves to the natural key of the hold, the event key of its
``HOLD_APPLIED`` (04 §16.3 handles resolved to natural keys; L1-3-Q-15). Overlapping intervals are
merged, and the earliest applied event of a merged interval sets the freeze level L: the target
at applied − 1 day with the events preceding that ``HOLD_APPLIED`` in ENG-06 order. While the
interval is open the target is min(C(t), L) for A ≥ 0 and max(C(t), L) for A < 0, so a hold never
defers a reversal (S09-R-43). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final

from erev_engine.stages.s09_recognition import progress_events
from erev_engine.stages.s09_recognition.progress_events import Position
from erev_engine.stages.state import AllocatedState, EventView, ObligationState

__all__ = [
    "FREEZE_FORMULA",
    "RECOGNITION",
    "Frozen",
    "HoldInterval",
    "freeze_params",
    "intervals",
    "open_at",
]

RECOGNITION: Final = "recognition"  # 04 E-45 hold_type (verbatim)
FREEZE_FORMULA: Final = "sched.hold_freeze.v1"


@dataclass(frozen=True, slots=True)
class HoldInterval:
    """A merged recognition-hold interval [applied, released) of an obligation."""

    applied: EventView  # earliest HOLD_APPLIED of the merged interval
    released: date | None  # effective date of the release that ends it; None while open
    hold_keys: tuple[str, ...]  # merged HOLD_APPLIED event keys


@dataclass(frozen=True, slots=True)
class Frozen:
    """The hold applied to a target: interval, formula params and the held target."""

    interval: HoldInterval
    params: Mapping[str, str]
    value: int  # minor units


def _covers(ev: EventView, ob: ObligationState) -> bool:
    if ev.contract_key != ob.contract_key:
        return False
    key = ev.payload.get("obligation_key")
    return key in (None, "") or key == ob.obligation_key


def intervals(
    st: AllocatedState, ob: ObligationState, d: date, position: Position | None = None
) -> tuple[HoldInterval, ...]:
    """Merged recognition-hold intervals of ``ob`` from the events admitted at ``d`` (S09-R-42)."""
    applied = [
        ev
        for ev in st.measure_events
        if ev.event_type == "HOLD_APPLIED"
        and ev.payload.get("hold_type") == RECOGNITION
        and progress_events.admitted(ev, d, position)
        and _covers(ev, ob)
    ]
    releases: dict[str, date] = {}
    for ev in st.measure_events:
        if ev.event_type != "HOLD_RELEASED" or not progress_events.admitted(ev, d, position):
            continue
        hold_id = ev.payload.get("hold_id")
        if isinstance(hold_id, str) and ev.contract_key == ob.contract_key:
            releases.setdefault(hold_id, ev.effective_date)
    merged: list[HoldInterval] = []
    for ev in sorted(applied, key=lambda item: item.order_key):
        released = releases.get(ev.event_key)
        if released is not None and released <= ev.effective_date:
            continue  # released on the day it was applied: no period end is held
        last = merged[-1] if merged else None
        if last is not None and (last.released is None or ev.effective_date < last.released):
            end = (
                None if last.released is None or released is None else max(last.released, released)
            )
            merged[-1] = HoldInterval(last.applied, end, (*last.hold_keys, ev.event_key))
        else:
            merged.append(HoldInterval(ev, released, (ev.event_key,)))
    return tuple(merged)


def open_at(holds: tuple[HoldInterval, ...], d: date) -> HoldInterval | None:
    """The merged interval open at ``d``: applied ≤ d < released (S09-R-44)."""
    for hold in holds:
        if hold.applied.effective_date <= d and (hold.released is None or d < hold.released):
            return hold
    return None


def freeze_params(
    hold: HoldInterval, *, as_of: date, level: int, allocation: int, mu: int
) -> Mapping[str, str]:
    """Params of ``sched.hold_freeze.v1`` (S09-R-43)."""
    params = {
        "allocation": str(allocation),
        "applied": hold.applied.effective_date.isoformat(),
        "as_of": as_of.isoformat(),
        "hold_keys": ",".join(hold.hold_keys),
        "level": str(level),
        "minor_unit": str(mu),
    }
    if hold.released is not None:
        params["released"] = hold.released.isoformat()
    return MappingProxyType(dict(sorted(params.items())))
