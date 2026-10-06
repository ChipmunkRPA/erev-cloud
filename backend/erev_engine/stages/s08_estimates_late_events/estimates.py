"""Stage 08 estimate versions (ENGINE_SPEC §8.2, §8.3 S08-R-01 to S08-R-07, §8.6; ENB-10).

``apply`` folds one ``ESTIMATE_CHANGED`` event:

- The version applied is the event's pin in the index stage 01 builds (S01-R-18); the version it
  replaces is ``EstimatePins.replaced_by``(estimate key, the event): the version in force before
  the event, every version counted from its own position (S08-R-01). The node
  ``estimate_pin@<event key>:<estimate key>:-`` records the pair.
- A measure-only kind changes no allocation: stages 09 to 11 read the pin at each date (S08-R-02).
  An ``INCREMENTS`` element is realised amounts and creates no segment (S08-R-04).
- A reallocating kind changes the price: ΔTP = the change of ``allocation_basis.posted`` between
  the price at the event's position and at the next event's (S08-R-03). A version of a targeted
  element whose target set or 32-40 evidence state differs from the element's version 1 fails
  closed first, before the zero-delta return (S08-R-04; ``routing.check_version``). ``routing``
  splits ΔTP, and each obligation with a share takes a ``TP_CHANGE`` segment copying the segment in
  force with x′ = x + δ and A′ = A + Δ (S08-R-06). An exact quota moving from x ≥ 0 to x′ < 0
  raises ``VC_ALLOCATION_NEGATIVE`` (``ERROR``) and no segment is added, on every routing path
  (the S08-R-06 transition predicate; CV-15, CV-42): an exact quota already negative at inception
  that stays negative does not raise, a newly negative sub-minor-unit exact quota does. The
  catch-up node ``catch_up@<event key>:<ob>:-`` = C_after(d) − C_before(d) at the event position,
  measured with the stage 09 targets that stage 09 later cites (S06-R-17; S09-R-36). The price
  after the event is appended to ``tp_history`` (S04-R-01). After the segments of an evidenced
  ``OBLIGATIONS`` element are added, the quota after the change is appended to
  ``targeted_vc_quota_history`` and ``targeted_vc_quotas`` takes the latest quota (S05-R-14;
  ENGINE_SPEC_B S15-R-09; D-91).

``AllocatedState`` carries no price function, so the stage 04 ``price_at`` over its ``PobState`` is
bound by the caller (ENGINE_SPEC §4.2; L1-3-Q-26); a reallocating version without it fails closed.
A version effective on or before the group inception is part of the inception price and
allocation (stage 04 ``first_boundary``) wherever its event stands among the events of that date
(S01-R-18 ``at_inception``), so it adds no segment. Standard library only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import money
from erev_engine.bundle import EstimateVersionInput
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.stages.s05_allocation import targeted
from erev_engine.stages.s08_estimates_late_events import routing
from erev_engine.stages.s09_recognition import PositionTarget, target_at_position
from erev_engine.stages.state import (
    CONCESSION_EMBEDDED,
    AllocatedState,
    AllocationSegment,
    BookContext,
    ConcessionAddition,
    ConcessionQuota,
    EventView,
    Finding,
    ObligationState,
    Quota,
    SegmentCause,
    TpBuildUp,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "CATCH_UP_FORMULA",
    "DELTA_FORMULA",
    "KIND_EFFECT",
    "PIN_FORMULA",
    "PriceAt",
    "applied_version",
    "apply",
]

# The stage 04 price of the group at a date and ENG-06 position (ENGINE_SPEC §4.2; S04-R-01).
PriceAt = Callable[[BookContext, AllocatedState, date, EventView | None], TpBuildUp]

MEASURE: Final = "MEASURE"
REALLOCATE: Final = "REALLOCATE"
KIND_EFFECT: Final[Mapping[str, str]] = MappingProxyType(
    {  # E-09 kind -> effect of a new version (§8.2)
        "BREAKAGE": MEASURE,
        "EAC": MEASURE,
        "EXERCISE_LIKELIHOOD": MEASURE,
        "EXPECTED_PURCHASES": MEASURE,
        "IMPLICIT_PRICE_CONCESSION": REALLOCATE,
        "RENEWAL_EXPECTATION": MEASURE,
        "RETURN_RATE": MEASURE,
        "ROYALTY_ACCRUAL": MEASURE,
        # 04 E-09 rev 1.2 (POLICIES OQ-14): the S04-R-17 reduction is measured at each date and
        # stays outside allocation_basis (S04-R-02), so a new version reallocates nothing.
        "SHARE_BASED_CONSIDERATION": MEASURE,
        "VARIABLE_CONSIDERATION": REALLOCATE,
    }
)
INCREMENTS: Final = "INCREMENTS"
CONCESSION_TYPES: Final = frozenset({"DISCOUNT", "SLA_CREDIT"})  # D-88 L7-5-Q-4 (iii)
PIN_FORMULA: Final = "estimate.pin.v1"
DELTA_FORMULA: Final = "estimate.tp_delta.v1"
CATCH_UP_FORMULA: Final = "estimate.catch_up.v1"
NEGATIVE_ALLOCATION: Final = "VC_ALLOCATION_NEGATIVE"
_STAGE: Final = 8


def _invariant(message: str, ev: EventView, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=ev.contract_key,
        detail={"event_key": ev.event_key, **detail},
    )


def applied_version(st: AllocatedState, ev: EventView) -> EstimateVersionInput:
    """The version an ``ESTIMATE_CHANGED`` event applies (S01-R-18)."""
    for estimate_key in sorted(st.estimates.pins):
        for pin in st.estimates.pins[estimate_key]:
            if pin.event_order_key == ev.order_key:
                return pin.version
    raise _invariant("the estimate version of the event has no pin", ev, rule="S01-R-18")


def _pin_member(version: EstimateVersionInput) -> tuple[str, Fraction]:
    members = (
        ("constrained_amount", version.constrained_amount),
        ("expected_total_amount", version.expected_total_amount),
        ("expected_quantity", version.expected_quantity),
        ("rate", version.rate),
    )
    for name, raw in members:
        if raw is not None:
            return name, money.to_fraction(raw)
    return "none", Fraction(0)


def _emit_pin(
    tb: TraceBuilder,
    ev: EventView,
    version: EstimateVersionInput,
    previous: EstimateVersionInput | None,
) -> str:
    member, value = _pin_member(version)
    source = SourceRef(
        "estimate_version",
        version.version_key,
        {"member": member, "value": money.format_exact(value)},
    )
    return tb.node(
        measure=f"estimate_pin@{ev.event_key}",
        subject_key=version.estimate_key,
        period_key=None,
        value=value,
        currency=None,
        minor_unit=None,
        formula_id=PIN_FORMULA,
        inputs=[source],
        params={
            "effective_date": version.effective_date.isoformat(),
            "kind": version.estimate_kind,
            "v_new": version.version_key,
            "v_old": "-" if previous is None else previous.version_key,
        },
        narrative_key=PIN_FORMULA.rsplit(".v", 1)[0],
    )


def _contract_royalty_accrual(
    st: AllocatedState, ev: EventView, version: EstimateVersionInput
) -> bool:
    """A ``ROYALTY_ACCRUAL`` version with ``allocation_target = CONTRACT`` on a contract none of
    whose obligations has component ``ROYALTY`` or ``PERIOD_VC``: variable consideration of the
    contract, a reallocating kind (D-88 L7-5-Q-8; S04-R-06 extension). Royalty-component
    obligations keep S08-R-02 as written."""
    if version.estimate_kind != "ROYALTY_ACCRUAL" or version.allocation_target != "CONTRACT":
        return False
    return not any(
        seg.component in ("ROYALTY", "PERIOD_VC")
        for ob in st.obligations
        if ob.contract_key == ev.contract_key
        for seg in ob.segments
    )


def _next_event(st: AllocatedState, ev: EventView) -> EventView | None:
    return next((item for item in st.events if item.order_key > ev.order_key), None)


def _basis_ref(ev: EventView, member: str, price: TpBuildUp, mu: int) -> SourceRef:
    value = money.format_money(price.allocation_basis.posted, mu)
    return SourceRef("contract_event", ev.event_key, {"member": member, "value": value})


def apply(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    tb: TraceBuilder,
    *,
    price_at: PriceAt | None,
) -> AllocatedState:
    """The state after one ``ESTIMATE_CHANGED`` event (ENGINE_SPEC §8.2)."""
    if ev.event_type != "ESTIMATE_CHANGED":
        raise _invariant("stage 08 applies ESTIMATE_CHANGED only", ev, rule="S08-R-01")
    version = applied_version(st, ev)
    previous = st.estimates.replaced_by(version.estimate_key, ev)
    effect = KIND_EFFECT.get(version.estimate_kind)
    if effect is None:
        raise _invariant(
            "the estimate kind has no effect", ev, rule="S08-R-02", kind=version.estimate_kind
        )
    _emit_pin(tb, ev, version, previous)
    if effect == MEASURE and _contract_royalty_accrual(st, ev, version):
        effect = REALLOCATE  # D-88 L7-5-Q-8: ΔTP routes on the inception basis (S08-R-03)
    if effect == MEASURE or version.allocation_target == INCREMENTS:
        return st
    if ev.effective_date <= st.inception_date:
        # In force at inception: the inception price holds the version wherever this event stands
        # among the boundary events of its date (S01-R-18 ``at_inception``; S04-R-01).
        return st
    routing.check_version(st, ev, version)  # S08-R-04 guards, before the zero-delta return
    if price_at is None:
        raise _invariant("the transaction price function is not bound", ev, rule="S08-R-03")
    d = ev.effective_date
    mu = routing.minor_unit(ctx)
    before = price_at(ctx, st, d, ev)
    after = price_at(ctx, st, d, _next_event(st, ev))
    delta = after.allocation_basis.posted - before.allocation_basis.posted
    pair = (None if previous is None else previous.version_key, version.version_key)
    delta_node = tb.node(
        measure=f"tp_delta@{ev.event_key}",
        subject_key=st.group_code,
        period_key=None,
        value=delta,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=DELTA_FORMULA,
        inputs=[
            _basis_ref(ev, "allocation_basis_before", before, mu),
            _basis_ref(ev, "allocation_basis_after", after, mu),
        ],
        params={"as_of": d.isoformat(), "v_new": version.version_key, "v_old": pair[0] or "-"},
        exact=after.allocation_basis.exact - before.allocation_basis.exact,
        narrative_key=DELTA_FORMULA.rsplit(".v", 1)[0],
    )
    history = (*st.tp_history, after)
    if delta == 0:
        return replace(st, tp_history=history)
    shares = routing.route(ctx, st, ev, version, delta, delta_node, tb)
    if sum(share.delta for share in shares) != delta:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the routed shares do not sum to the transaction price change",
            subject_key=st.group_code,
            detail={"event_key": ev.event_key, "invariant": "S08-INV-02"},
        )
    by_key = {ob.subject_key: ob for ob in st.obligations}
    changes: dict[str, tuple[AllocationSegment, AllocationSegment, routing.Share]] = {}
    findings: list[Finding] = []
    for share in shares:
        if share.delta == 0 and share.exact == 0:
            continue
        ob = by_key[share.subject_key]
        current = routing.in_force(st, ob, ev)
        if current is None:
            raise _invariant(
                "an obligation with a share has no allocation",
                ev,
                rule="CV-60",
                obligation_key=ob.obligation_key,
            )
        changed = replace(
            current,
            effective_date=d,
            event_key=ev.event_key,
            cause=SegmentCause.TP_CHANGE,
            x_exact=current.x_exact + share.exact,
            a_posted=current.a_posted + share.delta,
            estimate_pair=pair,
        )
        if current.x_exact >= 0 > changed.x_exact:  # S08-R-06 transition predicate (D-91)
            detail = {
                "a_posted": str(changed.a_posted),
                "allocated_exact": money.format_exact(changed.x_exact),
                "event_key": ev.event_key,
            }
            findings.append(
                Finding(
                    NEGATIVE_ALLOCATION,
                    "ERROR",
                    ob.subject_key,
                    {**detail, "rule": "S08-R-06"},
                    _STAGE,
                    ev.event_key,
                )
            )
        changes[ob.subject_key] = (current, changed, share)
    if findings:
        ordered = tuple(sorted(findings, key=Finding.sort_key))
        return replace(st, findings=(*st.findings, *ordered), tp_history=history)
    obligations = tuple(
        replace(ob, segments=(*ob.segments, changes[ob.subject_key][1]))
        if ob.subject_key in changes
        else ob
        for ob in st.obligations
    )
    result = replace(st, obligations=obligations, tp_history=history)
    for ob in result.obligations:
        if ob.subject_key in changes:
            current, changed, share = changes[ob.subject_key]
            _emit_catch_up(ctx, result, ob, ev, (current, changed), share, pair, tb)
    result = _targeted_quotas(result, ev, version, changes)
    return _concession_quotas(ctx, result, ev, version, changes)


def _frozen(
    values: Mapping[str, Mapping[str, object]],
) -> Mapping[str, Mapping[str, object]]:
    return MappingProxyType(
        {
            estimate_key: MappingProxyType(dict(sorted(members.items())))
            for estimate_key, members in sorted(values.items())
        }
    )


def _targeted_quotas(
    st: AllocatedState,
    ev: EventView,
    version: EstimateVersionInput,
    changes: Mapping[str, tuple[AllocationSegment, AllocationSegment, routing.Share]],
) -> AllocatedState:
    """S05-R-14 and S08-R-07 (rev 1.6; D-91): after a reallocating version of an evidenced
    ``OBLIGATIONS`` element adds its segments, each obligation that received a ``TP_CHANGE`` segment
    appends (effective date, the quota after the change) to ``targeted_vc_quota_history`` and
    ``targeted_vc_quotas`` takes the latest quota, so that POL-200 reads the quota in force at any
    measured date (ENGINE_SPEC_B S15-R-09). Findings that block the segments reach no update."""
    if version.allocation_target != routing.TARGETED or not targeted.evidenced(version):
        return st
    history: dict[str, dict[str, object]] = {
        estimate_key: dict(members)
        for estimate_key, members in st.targeted_vc_quota_history.items()
    }
    latest: dict[str, dict[str, object]] = {
        estimate_key: dict(members) for estimate_key, members in st.targeted_vc_quotas.items()
    }
    dated = history.setdefault(version.estimate_key, {})
    current = latest.setdefault(version.estimate_key, {})
    for subject_key in sorted(changes):
        share = changes[subject_key][2]
        held = dated.get(subject_key, ())
        assert isinstance(held, tuple)
        prior = held[-1][1] if held else Quota(Fraction(0), 0)
        quota = Quota(prior.x_exact + share.exact, prior.a_posted + share.delta)
        dated[subject_key] = (*held, (ev.effective_date, quota))
        current[subject_key] = quota
    return replace(
        st,
        targeted_vc_quotas=_frozen(latest),  # type: ignore[arg-type]
        targeted_vc_quota_history=_frozen(history),  # type: ignore[arg-type]
    )


def _concession_quotas(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    version: EstimateVersionInput,
    changes: Mapping[str, tuple[AllocationSegment, AllocationSegment, routing.Share]],
) -> AllocatedState:
    """D-88 L7-5-Q-4 (iii): a ``VARIABLE_CONSIDERATION`` version on an element with
    ``allocation_target = OBLIGATIONS``, ``vc_element_type`` ``DISCOUNT`` or ``SLA_CREDIT`` and no
    ``refund_liability_target``, whose negative share goes to an obligation with f = 1 at d, adds
    ``refund_components[subject] += Quota(−exact, −delta)``: the ``CONCESSION`` refund quota with
    the ``ESTIMATE_CHANGED`` event key, as stage 06 adds it under CREDIT_OR_REFUND (L6-5-Q-10)."""
    if (
        version.estimate_kind != "VARIABLE_CONSIDERATION"
        or version.allocation_target != routing.TARGETED
        or version.vc_element_type not in CONCESSION_TYPES
        or version.parameters.get("refund_liability_target") is not None
    ):
        return st
    components = dict(st.refund_components)
    additions: list[ConcessionAddition] = []
    for ob in st.obligations:
        found = changes.get(ob.subject_key)
        if found is None or found[2].exact >= 0:
            continue
        share = found[2]
        position = target_at_position(ctx, st, ob, ev.effective_date, event=ev, inclusive=True)
        if not position.complete:
            continue
        # The negative share is carried by the obligation's changed segment (the catch-up above),
        # so the stage 09 revenue node already carries the concession: EMBEDDED (S10-R-26).
        held = components.get(ob.subject_key, Quota(Fraction(0), 0))
        components[ob.subject_key] = ConcessionQuota(
            held.x_exact - share.exact,
            held.a_posted - share.delta,
            revenue_basis=CONCESSION_EMBEDDED,
        )
        # The dated source subledger entry: the routed share's exact and posted delta as computed
        # (D-91 L9-ENG-B3-Q-1; never re-rounded).
        additions.append(
            ConcessionAddition(
                subject_key=ob.subject_key,
                event_key=ev.event_key,
                effective_date=ev.effective_date,
                order_key=ev.order_key,
                exact=-share.exact,
                posted=-share.delta,
                producer="08",
                revenue_basis=CONCESSION_EMBEDDED,
            )
        )
    if not additions:
        return st
    return replace(
        st,
        refund_components=MappingProxyType(dict(sorted(components.items()))),
        concession_history=(*st.concession_history, *additions),
    )


def _side(target: PositionTarget, seg: AllocationSegment, side: str) -> dict[str, str]:
    return {
        f"a_{side}": str(seg.a_posted),
        f"complete_{side}": "true" if target.complete else "false",
        f"exact_{side}": rational_param(target.fixed_exact),
        f"x_{side}": rational_param(seg.x_exact),
    }


def _emit_catch_up(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    ev: EventView,
    segments: tuple[AllocationSegment, AllocationSegment],
    share: routing.Share,
    pair: tuple[str | None, str],
    tb: TraceBuilder,
) -> str:
    """``catch_up@<event key>:<ob>:-``: C_after(d) − C_before(d) at the event position."""
    d = ev.effective_date
    before = target_at_position(ctx, st, ob, d, event=ev, inclusive=False)
    after = target_at_position(ctx, st, ob, d, event=ev, inclusive=True)
    for target, seg in ((before, segments[0]), (after, segments[1])):
        if target.segment is not None and target.segment != seg:
            raise _invariant(
                "stage 09 measures another segment at the boundary",
                ev,
                rule="S09-R-04",
                obligation_key=ob.obligation_key,
            )
    params = {
        "as_of": d.isoformat(),
        "v_new": pair[1],
        "v_old": pair[0] or "-",
        **_side(before, segments[0], "before"),
        **_side(after, segments[1], "after"),
    }
    guard = after.guard or before.guard
    if guard is not None:
        params["guard"] = guard
    if after.progress is not None:
        params["progress"] = rational_param(after.progress)
    return tb.node(
        measure=f"catch_up@{ev.event_key}",
        subject_key=ob.subject_key,
        period_key=None,
        value=after.value - before.value,
        currency=ctx.txn_currency,
        minor_unit=routing.minor_unit(ctx),
        formula_id=CATCH_UP_FORMULA,
        inputs=[share.node_id],
        params=params,
        exact=after.fixed_exact - before.fixed_exact,
        narrative_key=CATCH_UP_FORMULA.rsplit(".v", 1)[0],
    )
