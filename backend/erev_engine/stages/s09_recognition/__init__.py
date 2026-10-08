"""Stage 09: recognition and schedules (ENGINE_SPEC_B §9; ENC-1 to ENC-5, ENC-7, ENC-9, ENC-10).

``run`` asserts one recognition method per obligation version (S09-INV-07), then turns the
allocation segments of ``AllocatedState`` into cumulative revenue targets per obligation and period
end, after manual adjustments, recognition holds and the status guard (§9.1; S09-R-41).
``revenue_by_cause`` decomposes each period amount by E-28 line type (§9.2.10). ``return_states``
holds the ALG-06 quantities of every returnable obligation per period end (§9.2.7).
``schedule_lines`` are the ``REVENUE`` lines of the version and ``obligation_measures`` the T-CON-11
values at the version date (§9.2.13, §9.2.14). ``RecognitionState.allocated`` carries the consumed
state unchanged for stages 10 to 15 (rev 1.2; ENGINE_SPEC B3 decision 6). Escheat components and
close-gate facts are added by the items that build them. Submodules are private to the stage
(DG-ENG-07); ``ReturnState``, ``ObligationMeasures`` and ``is_deterministic`` — the one predicate
of S09-R-45 — are exported for stage 10.
``target_at_position`` is exported for stages 07 and 08, which measure opening differences and
catch-ups with the CV-63 formulas that stage 09 implements, so the values they publish are those
stage 09 cites (S06-R-17; S09-R-36). ``input_progress`` and ``eac_version_at`` are exported for
stage 06, which measures cost-to-cost and labour-hours boundaries with the S09-R-14 to S09-R-16
progress that stage 09 later applies, so allocation and recognition read one progress function
(§9.1; ENC-5). ``deposit_revenue_shares`` and the ``deposit_*`` exports are the S14-R-25
attribution of a contract's 606-10-25-7 revenue to its obligations, which stage 14 posts and
stage 15 nets from RPO (D-91 gaps (iv), (v), (vii)). ``POLICY_KEYS`` and ``FORMULA_IDS`` feed the
``STAGES`` entry (ENGINE_SPEC §0.10; Table 13-A row 09). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import usage
from erev_engine.bundle import EstimateVersionInput
from erev_engine.errors import EngineError
from erev_engine.stages.s09_recognition import components, decompose, progress_inputs, schedule
from erev_engine.stages.s09_recognition.breakage import EscheatComponent
from erev_engine.stages.s09_recognition.progress_events import Position
from erev_engine.stages.s09_recognition.returns import ReturnState
from erev_engine.stages.s09_recognition.royalty import CoverageGap
from erev_engine.stages.s09_recognition.schedule import ObligationMeasures, is_deterministic
from erev_engine.stages.s09_recognition.step1 import (
    SHARE_MEASURE as DEPOSIT_SHARE_MEASURE,
)
from erev_engine.stages.s09_recognition.step1 import (
    TIME_SHARE_MEASURE as DEPOSIT_TIME_SHARE_MEASURE,
)
from erev_engine.stages.s09_recognition.step1 import (
    Attribution as DepositAttribution,
)
from erev_engine.stages.s09_recognition.step1 import (
    attributions as deposit_attributions,
)
from erev_engine.stages.s09_recognition.step1 import (
    share as deposit_share,
)
from erev_engine.stages.s09_recognition.step1 import (
    share_node_id as deposit_share_node_id,
)
from erev_engine.stages.s09_recognition.step1 import (
    weights as deposit_share_weights,
)
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EventView,
    Finding,
    ObligationState,
    ScheduleLineOut,
    Target,
)
from erev_engine.trace import TraceBuilder

__all__ = [
    "DEPOSIT_SHARE_MEASURE",
    "DEPOSIT_TIME_SHARE_MEASURE",
    "FORMULA_IDS",
    "POLICY_KEYS",
    "CoverageGap",
    "DepositAttribution",
    "EscheatComponent",
    "ObligationMeasures",
    "PositionTarget",
    "RecognitionState",
    "ReturnState",
    "deposit_attributions",
    "deposit_share",
    "deposit_share_node_id",
    "deposit_share_weights",
    "eac_version_at",
    "input_progress",
    "input_target",
    "is_deterministic",
    "measures_eac",
    "run",
    "target_at_position",
]

# ENGINE_SPEC_B Table 13-A row 09 (STAGE_POLICY_KEYS), sorted.
POLICY_KEYS: Final[tuple[str, ...]] = (
    "bill_and_hold.custodial_pob",
    "breakage.method",
    "credits.rollover_treatment",
    "licence.renewal_start",
    "recognition.control_trigger",
    "recognition.measure_of_progress",
    "recognition.right_to_invoice_guard",
    "recognition.time_convention",
    "returns.model",
    "returns.returned_units_scope",
    "returns.reversal_rate",
    "rounding.schedule",
    "royalty.minimum_guarantee",
    "royalty.unreported_sales",
    "scope.repurchase_classification",
    "usage.tier_minimum_method",
)
# The registered formulas stage 09 emits (§9.5), sorted.
FORMULA_IDS: Final[tuple[str, ...]] = (
    "breakage.expiry.v1",
    "breakage.proportional.v1",
    "breakage.remote.v1",
    "rec.activity_sum.v1",
    "rec.allocation.v1",
    "rec.allocation_adjustment.v1",
    "rec.awaiting.v1",
    "rec.catch_up.sum.v1",
    "rec.decompose.sequential.v1",
    "rec.exact_activity.v1",
    "rec.exact_difference.v1",
    "rec.exact_endpoint.v1",
    "rec.period_vc_revenue.v1",
    "rec.progress.cost_recovery.v1",
    "rec.progress.cost_to_cost.v1",
    "rec.progress.labour_hours.v1",
    "rec.progress.milestone.v1",
    "rec.progress.output_percent.v1",
    "rec.progress.point_in_time.v1",
    "rec.progress.prospective_segment.v1",
    "rec.progress.right_to_invoice.v1",
    "rec.progress.time_elapsed.daily.v1",
    "rec.progress.time_elapsed.mid_month.v1",
    "rec.progress.time_elapsed.monthly_even.v1",
    "rec.progress.units.v1",
    "rec.progress.unmeasured.v1",
    "rec.realised_allocation.v1",
    "rec.remaining.v1",
    "rec.revenue_cum.v1",
    "rec.schedule.fixed.v1",
    "rec.scheduled.v1",
    "rec.segment_state.v1",
    "rec.step1_net.v1",
    "rec.target_exact.inception.v1",
    "rec.target_exact.prospective.v1",
    "rec.uninstalled_materials.v1",
    "returns.excess_reversal.v1",
    "returns.expected_units.v1",
    "returns.refundable_units.v1",
    "returns.revenue_target.v1",
    "returns.units_billed.v1",
    "royalty.accrual.v1",
    "royalty.minimum_guarantee.v1",
    "royalty.report_true_up.v1",
    "sched.hold_freeze.v1",
    "sched.manual_defer.v1",
    "sched.manual_release.v1",
    "sched.override_respread.v1",
    "step1.deposit_revenue_share.v1",
)


@dataclass(frozen=True, slots=True)
class PositionTarget:
    """The target of one obligation at a date and ENG-06 position (CV-63; S09-R-04)."""

    subject_key: str
    as_of: date  # the evaluation date; the freeze date under S02-R-05
    guard: str | None  # "V4:<E-17 status>", "V5" or "S09-R-13:LEASE": the target is 0
    value: int  # C_p, minor units
    segment: AllocationSegment | None  # the FIXED segment in force
    progress: Fraction | None  # p_k of the FIXED segment
    fixed_exact: Fraction  # E of the FIXED component, currency units
    fixed_posted: int  # C of the FIXED component, minor units
    complete: bool  # φ = 1 for the FIXED component


def target_at_position(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    d: date,
    *,
    event: EventView | None = None,
    inclusive: bool = True,
    adjusted: bool = False,
) -> PositionTarget:
    """C_p(d) at the ENG-06 position of ``event``: at or, unless ``inclusive``, strictly before it.

    Without ``adjusted`` the value is the segment target that S06-R-17 and S09-R-36 compare before
    and after a boundary; with it, manual adjustments and holds apply as well (S09-R-41).
    """
    evaluator = components.Evaluator(ctx, st, ob)
    position = None if event is None else Position(event.order_key, inclusive=inclusive)
    evaluation = evaluator.posted(d, position) if adjusted else evaluator.segments(d, position)
    fixed = evaluation.fixed
    return PositionTarget(
        subject_key=ob.subject_key,
        as_of=evaluation.as_of,
        guard=evaluation.guard,
        value=evaluation.value,
        segment=None if fixed is None else fixed.segment,
        progress=None if fixed is None else fixed.progress.value,
        fixed_exact=Fraction(0) if fixed is None else fixed.exact,
        fixed_posted=0 if fixed is None else fixed.posted,
        complete=fixed is not None and fixed.complete,
    )


def input_progress(
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    *,
    event: EventView | None = None,
    inclusive: bool = False,
) -> Fraction:
    """f(d) or g(d) of an input-measured segment at the ENG-06 position of ``event`` (§9.2.5).

    Stage 06 measures a boundary with it: strictly before the event for the state before it, and
    at the event for the class N segment it creates, whose S06-R-15 updated EAC is the version
    effective at d among every applied version (``progress_inputs.eac_version``).
    """
    position = None if event is None else Position(event.order_key, inclusive=inclusive)
    return progress_inputs.progress(st, ob, seg, d, position=position).progress.value


def input_target(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    *,
    event: EventView | None = None,
    inclusive: bool = False,
) -> tuple[Fraction, Fraction, int, bool]:
    """(f, E, C, φ = 1) of an input-measured segment at the ENG-06 position of ``event`` (§9.2.2,
    §9.2.5). Stage 06 measures a boundary with it so the pool, the class D base and the catch-up
    start from the target stage 09 recognises, uninstalled materials included (S09-R-14, S06-R-17;
    S06-INV-02), while ``f`` keeps the S09-R-14 margin-bearing definition."""
    position = None if event is None else Position(event.order_key, inclusive=inclusive)
    contract = next(view for view in st.contracts if view.header.external_id == ob.contract_key)
    part = components.segment_target(ctx, st, contract, ob, seg, d, position=position)
    return part.progress.value, part.exact, part.posted, part.complete


def measures_eac(st: AllocatedState, ob: ObligationState, ev: EventView) -> bool:
    """Whether ``ev`` applies an ``EAC`` version of the element measuring the input-measured ``ob``
    (S09-R-14 to S09-R-16): a measure-only version, so no segment marks it (S08-R-02)."""
    return decompose.measures_eac(st, ob, ev)


def eac_version_at(
    st: AllocatedState,
    ob: ObligationState,
    seg: AllocationSegment | None,
    d: date,
    *,
    event: EventView | None = None,
    inclusive: bool = False,
) -> EstimateVersionInput | None:
    """The ``EAC`` version measuring ``ob`` at ``d`` and the position of ``event`` (S01-R-18;
    S06-R-15), or None when no element or approved version applies (S09-R-16)."""
    position = None if event is None else Position(event.order_key, inclusive=inclusive)
    return progress_inputs.eac_version(st, ob, seg, d, position)


@dataclass(frozen=True, slots=True)
class RecognitionState:
    """Stage 09 output (ENGINE_SPEC_B §9.1)."""

    allocated: AllocatedState  # consumed state, unchanged (§0.4)
    revenue_targets: tuple[Target, ...]  # measure "revenue_cum" per obligation and period end
    revenue_by_cause: tuple[Target, ...]  # measure "revenue", cause = E-28 line type (§9.2.10)
    return_states: Mapping[tuple[str, str], ReturnState]  # (subject key, period key), §9.2.7
    findings: tuple[Finding, ...]  # CV-43 order
    schedule_lines: tuple[ScheduleLineOut, ...] = ()  # REVENUE lines of the version (§9.2.14)
    obligation_measures: Mapping[str, ObligationMeasures] = MappingProxyType({})  # subject key
    # ENC-8: unclaimed-property amounts at expiry per (obligation, period end) for the stage 10
    # UNCLAIMED_PROPERTY component (§9.1, S09-R-28), and the S09-R-34 royalty coverage-gap facts
    # the close step INVARIANTS raises as ROYALTY_ACCRUAL_MISSING.
    escheat_components: tuple[EscheatComponent, ...] = ()
    close_gate_facts: tuple[CoverageGap, ...] = ()
    # S14-R-25 (D-91): ``deposit_revenue_share`` and ``deposit_revenue_time_share`` per obligation
    # and period end, the contract's 606-10-25-7 revenue attributed to its in-scope obligations.
    deposit_revenue_shares: tuple[Target, ...] = ()


def expedient_guard(ctx: BookContext, st: AllocatedState) -> tuple[Finding, ...]:
    """POL-092 (S09-R-18 rev 1.21; D-98 candidate 37): ``RTI_EXPEDIENT_NOT_APPLICABLE`` for every
    ``RIGHT_TO_INVOICE`` obligation whose pricing terms block the expedient
    (``erev_engine.usage.expedient_blockers``) — ERROR under
    ``BLOCK_IF_NONLINEAR_OR_FIXED_COMPONENT``, WARNING under ``ALLOW`` (the bypass and its policy
    reason recorded in the output). Detail: ``reasons``, ``policy``, ``rule``."""
    versions = [pin.version for pins in st.estimates.pins.values() for pin in pins]
    found: list[Finding] = []
    for ob in st.obligations:
        if str(ob.recognition_method) != usage.RIGHT_TO_INVOICE:
            continue
        contract = next(
            (view for view in st.contracts if view.header.external_id == ob.contract_key), None
        )
        if contract is None:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the obligation's contract is absent from the state",
                subject_key=ob.subject_key,
                detail={"rule": "CV-45"},
            )
        reasons = usage.expedient_blockers(
            contract_key=ob.contract_key,
            obligation_key=ob.obligation_key,
            booking=contract.booking,
            versions=versions,
        )
        if not reasons:
            continue
        policy = ctx.policies.value(
            usage.GUARD_POLICY,
            contract=ob.contract_key,
            obligation=ob.subject_key,
            entity=ob.performing_entity,
        )
        severity = "WARNING" if policy == usage.GUARD_ALLOW else "ERROR"
        detail = {"policy": str(policy), "reasons": ";".join(reasons), "rule": "S09-R-18"}
        found.append(Finding(usage.GUARD_FINDING, severity, ob.subject_key, detail, 9, None))
    return tuple(found)


def run(ctx: BookContext, st: AllocatedState, tb: TraceBuilder) -> RecognitionState:
    """Cumulative revenue targets, schedules and measures of every obligation of one book (§9.2)."""
    schedule.validate(st)  # S09-INV-07 stage entry assertion
    guard = expedient_guard(ctx, st)
    result = components.revenue_targets(ctx, st, tb)
    lines, measures = schedule.build(ctx, st, tb, result)
    return RecognitionState(
        allocated=st,
        revenue_targets=result.revenue_targets,
        revenue_by_cause=result.revenue_by_cause,
        return_states=result.return_states,
        findings=tuple(sorted((*guard, *result.findings), key=Finding.sort_key)),
        schedule_lines=lines,
        obligation_measures=measures,
        escheat_components=result.escheat_components,
        close_gate_facts=result.close_gate_facts,
        deposit_revenue_shares=result.deposit_revenue_shares,
    )
