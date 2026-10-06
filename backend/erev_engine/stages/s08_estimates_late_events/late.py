"""Stage 08 late events, register facts and reassessment gate facts (ENGINE_SPEC §8.4; ENB-11).

``late_events`` runs once per book over the folded ``AllocatedState``:

- Replay (S08-R-09): stage 01 orders events by (effective date, record_seq, event key) and the
  boundary fold applies them in that order, so a late or back-dated event is folded at its
  effective position and every target is recomputed. Stage 14 posts the cumulative difference of
  closed periods into the period ``assign_posting_period`` returns.
- ``LATE_EVENT`` (``WARNING``, S08-R-10), once per new event (``is_new``) whose effective period is
  ``closed`` or ``permanently_locked`` for the contracting entity, or whose effective date is
  earlier than the effective date of an event of the same contract recorded before it
  (``record_seq``; out-of-order arrival, DEV-024). Detail ``event_key``, ``origin_period_key``,
  ``posting_period_key`` ("-" when absent), ``reason`` and ``rule``.
- Register facts (S08-R-11) for each new event effective in a closed or locked period: {event key,
  contract key, origin period, posting period, event type}. Stage 14 attaches the amounts by
  role; the platform builds the out-of-period register (REQ-CLS-004). When a later postable
  period exists, the node ``late_assign@<event key>:<contract>:-`` (``late.assign.v1``) records the
  periods carried and the states read.
- The engine never classifies a change as an estimate change or an error correction (S08-R-12;
  POL-183): a correction reopens the period, and the recomputation posts into the ``reopened``
  period under S08-R-08.
- Reassessment gate facts (S08-R-13; POL-042 ``vc.reassessment_gate``, pin P): for each open VC
  element and each period end from its first version through the horizon of the contracting
  entity, an element without a version effective at the period end. An approved
  ``no_change_attestation`` version is a version, so it satisfies the gate. The close step
  ``INVARIANTS`` raises ``VC_REASSESSMENT_MISSING``; ``NOT_ENFORCED`` (parity) gives no facts.

Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final

from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import contract_subject_key
from erev_engine.stages.s08_estimates_late_events.assign import (
    LATE_EVENT,
    Assignment,
    assign_posting_period,
)
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    ContractView,
    EventView,
    Finding,
)
from erev_engine.trace import TraceBuilder

__all__ = [
    "LATE_ASSIGN_FORMULA",
    "REASSESSMENT_GATE",
    "REASSESSMENT_MISSING",
    "LateEventFact",
    "LateEvents",
    "ReassessmentGap",
    "close_gate_facts",
    "late_events",
]

LATE_ASSIGN_FORMULA: Final = "late.assign.v1"
REASSESSMENT_GATE: Final = "vc.reassessment_gate"  # POL-042
REASSESSMENT_MISSING: Final = "VC_REASSESSMENT_MISSING"  # 04 table 15.4, source CLOSE
ENFORCED: Final = "REQUIRE_VERSION_OR_ATTESTATION"
VC_KINDS: Final = frozenset({"VARIABLE_CONSIDERATION"})  # T-CON-13 no_change_attestation schema
INCREMENTS: Final = "INCREMENTS"
CLOSED_PERIOD: Final = "CLOSED_PERIOD"
OUT_OF_ORDER: Final = "OUT_OF_ORDER"
ABSENT: Final = "-"
_SEPARATOR: Final = "|"
_STAGE: Final = 8


@dataclass(frozen=True, slots=True)
class LateEventFact:
    """One out-of-period register fact (S08-R-11)."""

    event_key: str
    contract_key: str
    origin_period_key: str
    posting_period_key: str | None  # None: no later postable period in the bundle
    event_type: str  # E-03


@dataclass(frozen=True, slots=True)
class ReassessmentGap:
    """An open VC element without a version effective at a period end (S08-R-13; POL-042)."""

    code: str  # "VC_REASSESSMENT_MISSING"
    estimate_key: str
    contract_key: str
    entity: str
    period_key: str
    version_key: str | None  # the version in force at the period end


@dataclass(frozen=True, slots=True)
class LateEvents:
    """Stage 08 late-event output of one book (ENGINE_SPEC §8.1 outputs)."""

    findings: tuple[Finding, ...]  # LATE_EVENT, CV-43 order
    register: tuple[LateEventFact, ...]  # ENG-06 order of the events
    close_gate_facts: tuple[ReassessmentGap, ...]  # (estimate key, contract key, period end)


def _invariant(message: str, subject_key: str, **detail: str) -> EngineError:
    return EngineError("ENGINE_INVARIANT_VIOLATED", message, subject_key=subject_key, detail=detail)


def _contract(contracts: Mapping[str, ContractView], contract_key: str) -> ContractView:
    view = contracts.get(contract_key)
    if view is None:
        raise _invariant(
            "an event names a contract absent from the state", contract_key, rule="CV-45"
        )
    return view


def _recorded_earlier_latest(st: AllocatedState) -> dict[str, date]:
    """Per event key, the latest effective date among events of its contract recorded before it."""
    latest: dict[str, date] = {}
    running: dict[str, date] = {}
    for ev in sorted(st.events, key=lambda item: (item.record_seq, item.event_key)):
        previous = running.get(ev.contract_key)
        if previous is not None:
            latest[ev.event_key] = previous
        running[ev.contract_key] = (
            ev.effective_date if previous is None else max(previous, ev.effective_date)
        )
    return latest


def _subject(ev: EventView) -> str:
    # One obligation gives its subject key, as answer keys list LATE_EVENT per obligation; otherwise
    # the contract subject key, the encoded external id (CV-21).
    if len(ev.obligation_subject_keys) == 1:
        return ev.obligation_subject_keys[0]
    return contract_subject_key(ev.contract_key)


def _states_carried(ctx: BookContext, entity: str, assignment: Assignment) -> list[str]:
    calendar = ctx.entities[entity]
    book_code = str(ctx.book_code)
    states: list[str] = []
    inside = False
    for period in sorted(calendar.periods, key=lambda p: (p.start_date, p.end_date)):
        if period.period_key == assignment.origin_period_key:
            inside = True
        if inside:
            states.extend(state for code, state in period.states if code == book_code)
        if period.period_key == assignment.posting_period_key:
            break
    return states


def _emit_assignment(
    ctx: BookContext, tb: TraceBuilder, ev: EventView, entity: str, assignment: Assignment
) -> str:
    """``late_assign@<event key>:<contract>:-``: periods from the origin to the posting period."""
    states = _states_carried(ctx, entity, assignment)
    return tb.node(
        measure=f"late_assign@{ev.event_key}",
        subject_key=contract_subject_key(ev.contract_key),
        period_key=None,
        value=len(states) - 1,
        currency=None,
        minor_unit=None,
        formula_id=LATE_ASSIGN_FORMULA,
        inputs=[],
        params={
            "book_code": str(ctx.book_code),
            "effective_date": ev.effective_date.isoformat(),
            "entity": entity,
            "event_key": ev.event_key,
            "event_type": ev.event_type,
            "origin_period_key": assignment.origin_period_key or ABSENT,
            "posting_period_key": assignment.posting_period_key or ABSENT,
            "reason_code": assignment.reason_code or ABSENT,
            "states": _SEPARATOR.join(states),
        },
        narrative_key=LATE_ASSIGN_FORMULA.rsplit(".v", 1)[0],
    )


def late_events(ctx: BookContext, st: AllocatedState, tb: TraceBuilder) -> LateEvents:
    """``LATE_EVENT`` findings, register facts and gate facts of one book (S08-R-10 to S08-R-13)."""
    contracts = {view.header.external_id: view for view in st.contracts}
    earlier = _recorded_earlier_latest(st)
    findings: list[Finding] = []
    register: list[LateEventFact] = []
    for ev in st.events:
        if not ev.is_new:
            continue
        entity = _contract(contracts, ev.contract_key).header.contracting_entity_code
        assignment = assign_posting_period(ctx, entity, ev.effective_date)
        closed = assignment.origin_period_key is not None
        latest = earlier.get(ev.event_key)
        reasons = [
            reason
            for reason, holds in (
                (CLOSED_PERIOD, closed),
                (OUT_OF_ORDER, latest is not None and ev.effective_date < latest),
            )
            if holds
        ]
        if not reasons:
            continue
        detail = {
            "event_key": ev.event_key,
            "origin_period_key": assignment.origin_period_key or ABSENT,
            "posting_period_key": assignment.posting_period_key or ABSENT,
            "reason": ",".join(reasons),
            "rule": "S08-R-10",
        }
        findings.append(Finding(LATE_EVENT, "WARNING", _subject(ev), detail, _STAGE, ev.event_key))
        if assignment.origin_period_key is None:
            continue
        register.append(
            LateEventFact(
                event_key=ev.event_key,
                contract_key=ev.contract_key,
                origin_period_key=assignment.origin_period_key,
                posting_period_key=assignment.posting_period_key,
                event_type=ev.event_type,
            )
        )
        if assignment.posting_period_key is not None:
            _emit_assignment(ctx, tb, ev, entity, assignment)
    return LateEvents(
        findings=tuple(sorted(findings, key=Finding.sort_key)),
        register=tuple(register),
        close_gate_facts=close_gate_facts(ctx, st),
    )


def close_gate_facts(ctx: BookContext, st: AllocatedState) -> tuple[ReassessmentGap, ...]:
    """Open VC elements without a version effective at a period end (S08-R-13; POL-042)."""
    contracts = {view.header.external_id: view for view in st.contracts}
    by_order = {ev.order_key: ev for ev in st.events}
    facts: list[ReassessmentGap] = []
    for estimate_key in sorted(st.estimates.pins):
        pins = st.estimates.pins[estimate_key]
        if not pins:
            continue
        latest = pins[-1].version
        if latest.estimate_kind not in VC_KINDS or latest.allocation_target == INCREMENTS:
            continue
        applied: dict[str, list[date]] = {}
        for pin in pins:
            ev = by_order.get(pin.event_order_key)
            if ev is None:
                raise _invariant(
                    "an estimate pin names an event absent from the state",
                    estimate_key,
                    rule="S01-R-18",
                )
            applied.setdefault(ev.contract_key, []).append(pin.version.effective_date)
        for contract_key in sorted(applied):
            entity = _contract(contracts, contract_key).header.contracting_entity_code
            facts.extend(_element_gaps(ctx, st, estimate_key, contract_key, entity, applied))
    return tuple(facts)


def _element_gaps(
    ctx: BookContext,
    st: AllocatedState,
    estimate_key: str,
    contract_key: str,
    entity: str,
    applied: Mapping[str, list[date]],
) -> list[ReassessmentGap]:
    calendar = ctx.entities.get(entity)
    horizon_key = ctx.horizon.get(entity)
    if calendar is None or horizon_key is None:
        raise _invariant("the contracting entity has no calendar or horizon", entity, rule="CV-13")
    periods = sorted(calendar.periods, key=lambda p: (p.start_date, p.end_date))
    horizon = next((p for p in periods if p.period_key == horizon_key), None)
    if horizon is None:
        raise _invariant("the horizon period is absent from the calendar", entity, rule="CV-13")
    effective = set(applied[contract_key])
    first = min(effective)
    gaps: list[ReassessmentGap] = []
    for period in periods:
        if period.end_date < first or period.end_date > horizon.end_date:
            continue
        gate = ctx.policies.value(REASSESSMENT_GATE, entity=entity, period=period.period_key)
        if gate != ENFORCED or period.end_date in effective:
            continue
        in_force = st.estimates.pin(estimate_key, period.end_date)
        gaps.append(
            ReassessmentGap(
                code=REASSESSMENT_MISSING,
                estimate_key=estimate_key,
                contract_key=contract_key,
                entity=entity,
                period_key=period.period_key,
                version_key=None if in_force is None else in_force.version_key,
            )
        )
    return gaps
