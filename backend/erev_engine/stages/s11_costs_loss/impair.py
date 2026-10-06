"""Stage 11 segment events, the period-end impairment test and the IFRS reversal (ENGINE_SPEC_B
§11.2.3 to §11.2.6).

The assets of one contract share one period loop. Before each period-end test the events that start
a segment are applied in date order (ENG-06 order on a date, estimate versions first):
- a later ``RENEWAL_EXPECTATION`` version starts a segment on the day after its effective date over
  the new months, with base the carrying amount after amortisation through the effective date
  (S11-R-05, S11-R-07; ENC-15; D-89 L7-6-Q-7);
- a ``COST_INCURRED`` clawback (``cost_adjustment = CLAWBACK``) takes min(amount, carrying) from the
  capitalisations of its payee and plan, oldest first, and the excess stays in the ERP (S11-R-12;
  JET-09f; L2-4-Q-38);
- a ``CONTRACT_TERMINATED`` under POL-145 ``ACCELERATE_TO_REMAINING_BENEFIT`` accelerates
  round(carrying × (1 − ρ)), ρ being the remaining allocation of the related obligations after the
  termination over the remaining allocation before, and the rest amortises to the latest end date
  of the remaining related obligations (S11-R-13; JET-09e; L2-4-Q-37).
A clawback or an acceleration dated d is measured on the carrying amount after amortisation through
d, and its segment starts on d + 1 day (L2-4-Q-37).

The assets whose related obligations are the same are tested together at every period end within
the horizon, after amortisation through the period end (S11-R-08). Remaining consideration = the
unconstrained, credit-adjusted transaction price of stage 04 allocated to the related obligations by
their exact allocation weights, less their posted revenue through the period end, plus the
``expected_total_amount`` of the ``RENEWAL_EXPECTATION`` version in force (S11-R-09, S11-R-11a,
S11-R-11b; D-76). Remaining direct costs = max(0, the ``expected_total_amount`` of the latest
``EAC`` versions of the related obligations − costs), 0 with ``COST_NO_EAC`` (INFO, once per asset)
when there is none. Costs are the ``PROGRESS_INPUT`` costs incurred when one of the related
obligations is effective on or before the period end; otherwise each version's amount runs off by
cumulative rounding with the related obligations' revenue progress since its effective date
(S11-R-09 as amended by D-89 L7-6-Q-7). The impairment min(carrying, max(0,
carrying − recoverable)) is apportioned by carrying amount and starts a segment on the next day
(S11-R-07, S11-R-08 rev 1.3). ASC606 never reverses (S11-INV-03). Under POL-144
``REQUIRED_CAPPED`` a period without impairment reverses max(0, min(recoverable share, unimpaired
carrying) − carrying), capped at impairments not yet reversed, the recoverable amount being shared
by carrying amount (S11-R-10; S11-INV-04). The unimpaired carrying amount follows the first segment,
net of clawbacks and acceleration (L2-4-Q-38). Every value is a trace node of a registered formula
(§11.5). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import money
from erev_engine.bundle import EstimateVersionInput, PeriodInput
from erev_engine.enums import ScheduleKind, ScheduleLineType
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.s11_costs_loss import amortise, capitalise
from erev_engine.stages.s11_costs_loss.amortise import CostSegment, Revenue
from erev_engine.stages.s11_costs_loss.capitalise import STRAIGHT_LINE, CostAssetSpec
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EventView,
    Finding,
    ObligationState,
    ScheduleLineOut,
    SegmentCause,
    Target,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "ACCELERATE",
    "ACCELERATE_FORMULA",
    "CARRYING_FORMULA",
    "CLAWBACK_FORMULA",
    "IMPAIR_FORMULA",
    "RECOVERABLE_FORMULA",
    "REQUIRED_CAPPED",
    "REVERSAL_FORMULA",
    "CostAssetMeasures",
    "Measured",
    "measure",
    "x_exact",
]

RECOVERABLE_FORMULA: Final = "cost.recoverable.v1"
IMPAIR_FORMULA: Final = "cost.impair.us.v1"
REVERSAL_FORMULA: Final = "cost.impair.ifrs_reversal.v1"
CARRYING_FORMULA: Final = "cost.carrying.v1"
CLAWBACK_FORMULA: Final = "cost.clawback.v1"
ACCELERATE_FORMULA: Final = "cost.accelerate.v1"
REVERSAL_POLICY: Final = "costs.impairment_reversal"  # POL-144
ACCELERATION_POLICY: Final = "costs.termination_acceleration"  # POL-145
REQUIRED_CAPPED: Final = "REQUIRED_CAPPED"
ACCELERATE: Final = "ACCELERATE_TO_REMAINING_BENEFIT"
EAC: Final = "EAC"
_EAC_IAS37: Final = "EAC_IAS37"  # the IFRS15 loss-test element (S11-R-15), not an impairment input
_CLAWBACK: Final = "CLAWBACK"  # 04 E-03 payload cost_adjustment
_TERMINATED: Final = "CONTRACT_TERMINATED"
_ONE_DAY: Final = timedelta(days=1)
_STAGE: Final = 11


@dataclass(frozen=True, slots=True)
class CostAssetMeasures:
    """T-CON-16 values of one asset at a period end (§11.1 ``cost_assets``)."""

    asset_key: str
    period_key: str
    as_of: date
    capitalized_cum: int
    amortized_cum: int
    impaired_cum: int
    impairment_reversed_cum: int
    clawback_cum: int  # S11-R-12
    accelerated_cum: int  # S11-R-13
    carrying_amount: int
    remaining_months: int
    renewal_version_key: str | None
    segments: tuple[CostSegment, ...]  # in force after the period-end test
    trace_nodes: Mapping[str, str]  # measure -> node id


@dataclass(frozen=True, slots=True)
class Measured:
    """The assets of one contract across the book's periods."""

    targets: tuple[Target, ...]
    measures: Mapping[tuple[str, str], CostAssetMeasures]
    lines: tuple[ScheduleLineOut, ...]
    findings: tuple[Finding, ...]


@dataclass(frozen=True, slots=True)
class _Clawback:
    ref: SourceRef  # the clawback event amount
    carrying: int  # after amortisation through the clawback date
    taken_before: int  # taken from older capitalisations
    taken: int


@dataclass(frozen=True, slots=True)
class _Acceleration:
    event_key: str
    policy: str  # POL-145 at the termination date
    carrying: int  # after amortisation through the termination date
    before: int  # remaining allocation of the related obligations before the termination
    after: int
    all_ended: bool
    amount: int


@dataclass(slots=True)
class _Asset:
    """Per-asset state across the period loop."""

    spec: CostAssetSpec
    segments: list[CostSegment]
    end: date
    applied: set[str]  # RENEWAL_EXPECTATION versions already in force
    renewal_key: str | None
    impaired: int = 0
    reversed_: int = 0
    clawback: int = 0
    accelerated: int = 0
    amortised_before: int = 0
    no_eac_reported: bool = False
    clawbacks: list[_Clawback] = field(default_factory=list)
    accelerations: list[_Acceleration] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Change:
    """An event that starts a segment: an estimate version or a contract event (S11-R-07)."""

    order: tuple[date, int, int, str]
    version: EstimateVersionInput | None
    event: EventView | None


@dataclass(frozen=True, slots=True)
class _Context:
    """What every change and period-end test of one contract reads."""

    ctx: BookContext
    allocated: AllocatedState
    by_key: Mapping[str, ObligationState]
    revenue: Revenue
    calendar: tuple[PeriodInput, ...]
    versions: tuple[EstimateVersionInput, ...]
    capitalised_nodes: Mapping[str, str]
    mu: int
    # ALG-11 calendar of straight-line amortisation: None (calendar months) for MONTHLY (C-04)
    time_calendar: tuple[PeriodInput, ...] | None = None


@dataclass(slots=True)
class _Out:
    targets: list[Target] = field(default_factory=list)
    lines: list[ScheduleLineOut] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    measures: dict[tuple[str, str], CostAssetMeasures] = field(default_factory=dict)


def _time_calendar(ctx: BookContext, entity_code: str) -> tuple[PeriodInput, ...] | None:
    """The ALG-11 calendar of straight-line amortisation (S11-R-06): None, calendar months, for a
    ``MONTHLY`` calendar, as stage 09 reads time elapsed; else the asset-owning entity's periods
    (C-04). Periods reach only the horizon (CV-12), while the asset amortises to its end date."""
    calendar = ctx.entities[entity_code]
    if calendar.calendar_pattern == "MONTHLY":
        return None
    return tuple(sorted(calendar.periods, key=lambda period: (period.start_date, period.end_date)))


def _invariant(message: str, subject_key: str | None, **detail: str) -> EngineError:
    return EngineError("ENGINE_INVARIANT_VIOLATED", message, subject_key=subject_key, detail=detail)


def _narrative(formula_id: str) -> str:
    return formula_id.rsplit(".v", 1)[0]


def _text(ev: EventView, name: str) -> str | None:
    raw = ev.payload.get(name)
    return None if raw is None else str(raw)


def x_exact(ob: ObligationState, d: date) -> Fraction:
    """x_exact of the ``FIXED`` segment in force at ``d`` by effective date, 0 before the first."""
    found = Fraction(0)
    for seg in ob.segments:
        if seg.component == "FIXED" and seg.effective_date <= d:
            found = seg.x_exact
    return found


def _consideration(
    st: AllocatedState, contract_key: str, related: Sequence[ObligationState], t: date, mu: int
) -> tuple[int, str]:
    """TP_u allocated to the related obligations: X_u,p = TP_u × x_exact_p ÷ Σ x_exact (S11-R-11b).

    Without a stage 04 build-up at ``t`` the related obligations' exact allocation stands in
    (L2-4-Q-34)."""
    own = [ob for ob in st.obligations if ob.contract_key == contract_key]
    related_x = sum((x_exact(ob, t) for ob in related), Fraction(0))
    total_x = sum((x_exact(ob, t) for ob in own), Fraction(0))
    build = None
    for item in st.tp_unconstrained.get(contract_key, ()):
        if item.at <= t and (build is None or item.at >= build.at):
            build = item
    if build is None or total_x == 0:
        return money.round_half_up(related_x, mu), "allocation"
    return money.round_half_up(build.total.exact * related_x / total_x, mu), "tp_unconstrained"


def _amount(version: EstimateVersionInput | None, mu: int) -> int:
    if version is None or version.expected_total_amount is None:
        return 0
    return money.round_half_up(money.to_fraction(version.expected_total_amount), mu)


def _eac(
    st: AllocatedState,
    contract_key: str,
    related: Sequence[ObligationState],
    t: date,
    mu: int,
) -> tuple[int | None, tuple[EstimateVersionInput, ...]]:
    """Σ ``expected_total_amount`` of the latest ``EAC`` version at ``t`` of each element of the
    contract that names a related obligation or none, and those versions; None without any
    (S11-R-09; L2-4-Q-35)."""
    obligation_keys = {ob.obligation_key for ob in related}
    total = 0
    versions: list[EstimateVersionInput] = []
    for key in st.estimates.of_contract(contract_key):  # CV-21 encoded lookup (ENG-COST-ENC-1)
        version = st.estimates.pin(key, t)
        if version is None or version.estimate_kind != EAC or version.element_code == _EAC_IAS37:
            continue
        if version.expected_total_amount is None:
            continue
        if version.obligation_key is not None and version.obligation_key not in obligation_keys:
            continue
        total += _amount(version, mu)
        versions.append(version)
    return (total if versions else None), tuple(versions)


def _run_off(
    cx: _Context,
    related: Sequence[ObligationState],
    versions: Sequence[EstimateVersionInput],
    t: date,
) -> tuple[int, tuple[Fraction, ...]]:
    """Costs when no ``PROGRESS_INPUT`` cost is effective by ``t``: Σ cumulative_posted(eac_v, g_v),
    g_v the related obligations' revenue progress since version v's effective date, (C_t − C_0) ÷
    (A_t − C_0) within [0, 1] and 1 when A_t = C_0, with C their posted revenue and A their posted
    allocation (S11-R-09 as amended by D-89 L7-6-Q-7; EX-11-A COST-CAP rows)."""
    scale: int = 10**cx.mu
    keys = [ob.subject_key for ob in related]
    earned = sum(cx.revenue.value(key, t) for key in keys)
    allocation = sum(cx.revenue.allocation(key, t) for key in keys)
    total = 0
    progress: list[Fraction] = []
    for version in versions:
        before = sum(cx.revenue.value(key, version.effective_date) for key in keys)
        if allocation == before:
            g = Fraction(1)
        else:
            g = min(Fraction(1), max(Fraction(0), Fraction(earned - before, allocation - before)))
        amount = _amount(version, cx.mu)
        total += money.cumulative_posted(Fraction(amount, scale), amount, g, cx.mu)
        progress.append(g)
    return total, tuple(progress)


def _changes(
    st: AllocatedState, contract_key: str, versions: Sequence[EstimateVersionInput]
) -> list[_Change]:
    """Renewal versions, clawbacks and terminations of the contract in date order."""
    items = [
        _Change((version.effective_date, 0, version.version_no, version.version_key), version, None)
        for version in versions
    ]
    for ev in st.events:
        if ev.contract_key != contract_key:
            continue
        adjustment = _text(ev, "cost_adjustment")
        if ev.event_type == capitalise.COST_EVENT and adjustment is not None:
            if adjustment != _CLAWBACK or _text(ev, "purpose") != capitalise.COST_TO_OBTAIN:
                raise _invariant(
                    "cost_adjustment is CLAWBACK on a cost to obtain only",
                    contract_key,
                    rule="CV-45",
                    event_key=ev.event_key,
                )
        elif ev.event_type != _TERMINATED:
            continue
        items.append(_Change((ev.effective_date, 1, ev.record_seq, ev.event_key), None, ev))
    return sorted(items, key=lambda change: change.order)


def _carrying(cx: _Context, asset: _Asset, d: date) -> int:
    """The carrying amount after amortisation through ``d`` (S11-INV-01)."""
    amortised = amortise.amortised(
        asset.spec, asset.segments, d, cx.revenue, cx.time_calendar, cx.mu
    )
    return (
        asset.spec.amount_capitalized
        - amortised.value
        - asset.impaired
        + asset.reversed_
        - asset.clawback
        - asset.accelerated
    )


def _renewal_change(cx: _Context, asset: _Asset, version: EstimateVersionInput) -> None:
    """S11-R-05: a later ``RENEWAL_EXPECTATION`` version starts a segment on the day after its
    effective date that amortises the carrying amount after amortisation through the effective date
    to add_months(start, new months) − 1 day (S11-R-07; D-89 L7-6-Q-7)."""
    if asset.spec.period_option == capitalise.CONTRACT_TERM or version.version_key in asset.applied:
        return
    asset.applied.add(version.version_key)
    if version.amortization_months is None:
        return
    d = max(version.effective_date + _ONE_DAY, asset.spec.amortization_start_date)
    base = _carrying(cx, asset, d - _ONE_DAY)
    end = capitalise.end_of(asset.spec.amortization_start_date, version.amortization_months)
    asset.segments.append(CostSegment(d, end, base, amortise.PERIOD_CHANGE))
    asset.end = end
    asset.renewal_key = version.version_key


def _claw_back(cx: _Context, assets: Sequence[_Asset], ev: EventView) -> None:
    """S11-R-12: the clawback amount taken from the capitalisations of its payee and plan, oldest
    first, each by min(open amount, carrying); any excess stays in the ERP (JET-09f)."""
    payee, plan_code = _text(ev, "payee"), _text(ev, "plan_code")
    if payee is None or plan_code is None:
        raise _invariant(
            "a clawback names no payee or plan code",
            ev.contract_key,
            rule="CV-45",
            event_key=ev.event_key,
        )
    amount = capitalise.amount_of(ev, cx.mu)
    if amount < 0:
        raise _invariant(
            "a clawback amount is negative", ev.contract_key, rule="CV-45", event_key=ev.event_key
        )
    d = ev.effective_date
    ref = SourceRef(
        "contract_event",
        ev.event_key,
        {"member": "amount", "value": money.format_money(amount, cx.mu)},
    )
    matching = sorted(
        (
            asset
            for asset in assets
            if asset.spec.cost_kind == capitalise.OBTAIN
            and (asset.spec.payee, asset.spec.plan_code) == (payee, plan_code)
            and asset.spec.capitalization_date <= d
        ),
        key=lambda asset: (asset.spec.capitalization_date, asset.spec.asset_key),
    )
    taken = 0
    for asset in matching:
        carrying = _carrying(cx, asset, d)
        take = min(max(0, amount - taken), carrying)
        asset.clawbacks.append(_Clawback(ref, carrying, taken, take))
        if take:
            asset.clawback += take
            asset.segments.append(
                CostSegment(d + _ONE_DAY, asset.end, carrying - take, amortise.CLAWBACK)
            )
        taken += take


def _remaining(
    cx: _Context, related: Sequence[ObligationState], ev: EventView
) -> tuple[int, int, bool, bool, list[ObligationState]]:
    """(before, after, every related obligation ended, affected, remaining obligations) of the
    remaining allocation at the termination date (S11-R-13; L2-4-Q-37).

    An obligation with a ``TERMINATION`` segment of the event ended: before = the posted allocation
    in force before the event less that segment's posted allocation (C_before(d_T) with no pool
    share), after = 0. An obligation with another segment of the event: before and after are the
    posted allocations before and after less the segment's base revenue. Any other obligation: its
    posted allocation less its revenue target of the latest period end on or before d_T, both times.
    """
    d = ev.effective_date
    before = after = ended = 0
    affected = False
    remaining: list[ObligationState] = []
    for ob in related:
        fixed = [seg for seg in ob.segments if seg.component == "FIXED"]
        index = next((i for i, seg in enumerate(fixed) if seg.event_key == ev.event_key), None)
        if index is None:
            in_force = [seg.a_posted for seg in fixed if seg.effective_date <= d]
            value = max(0, (in_force[-1] if in_force else 0) - cx.revenue.value(ob.subject_key, d))
            before += value
            after += value
            if ob.terminated_on is None or ob.terminated_on > d:
                remaining.append(ob)
            continue
        affected = True
        seg = fixed[index]
        previous = fixed[index - 1].a_posted if index else 0
        if seg.cause == SegmentCause.TERMINATION:
            ended += 1
            before += max(0, previous - seg.a_posted)
        else:
            before += max(0, previous - seg.base_revenue_posted)
            after += max(0, seg.a_posted - seg.base_revenue_posted)
            remaining.append(ob)
    return before, after, ended == len(related), affected, remaining


def _terminate(cx: _Context, assets: Sequence[_Asset], ev: EventView) -> None:
    """S11-R-13: acceleration on ``CONTRACT_TERMINATED`` under POL-145 (JET-09e; CHK-112)."""
    d = ev.effective_date
    period = capitalise.period_containing(cx.calendar, d, ev.event_key)
    for asset in sorted(assets, key=lambda item: item.spec.asset_key):
        if asset.spec.capitalization_date > d:
            continue
        related = [cx.by_key[key] for key in asset.spec.related_obligation_keys]
        before, after, all_ended, affected, remaining = _remaining(cx, related, ev)
        if not affected:
            continue  # ρ = 1: the termination names none of the related obligations
        policy = str(
            cx.ctx.policies.value(
                ACCELERATION_POLICY, entity=asset.spec.entity, period=period.period_key
            )
        )
        carrying = _carrying(cx, asset, d)
        if all_ended:
            ratio = Fraction(0)
        elif before == 0:
            ratio = Fraction(1)
        else:
            ratio = min(Fraction(1), Fraction(after, before))
        amount = (
            money.round_half_up(Fraction(carrying) * (1 - ratio), 0) if policy == ACCELERATE else 0
        )
        asset.accelerations.append(
            _Acceleration(ev.event_key, policy, carrying, before, after, all_ended, amount)
        )
        if policy != ACCELERATE:
            continue
        asset.accelerated += amount
        start = d + _ONE_DAY
        ends = [ob.end_date for ob in remaining if ob.end_date is not None]
        if not remaining:
            end = start
        elif ends:
            end = max(start, max(ends))
        else:
            end = asset.end
        asset.segments.append(CostSegment(start, end, carrying - amount, amortise.ACCELERATION))
        asset.end = end


def _apply(cx: _Context, assets: Sequence[_Asset], change: _Change, t: date) -> None:
    if change.version is not None:
        for asset in assets:
            if asset.spec.capitalization_date <= t:
                _renewal_change(cx, asset, change.version)
    elif change.event is not None and change.event.event_type == _TERMINATED:
        _terminate(cx, assets, change.event)
    elif change.event is not None:
        _claw_back(cx, assets, change.event)


def _test(
    cx: _Context, tb: TraceBuilder, period: PeriodInput, live: list[_Asset], out: _Out
) -> None:
    """The period-end test of the assets of one related set and their T-CON-16 values."""
    ctx, allocated, mu = cx.ctx, cx.allocated, cx.mu
    t = period.end_date
    first = live[0].spec
    related = [cx.by_key[key] for key in first.related_obligation_keys]
    obligation_keys = frozenset(ob.obligation_key for ob in related)
    group_key = f"{first.contract_key}/" + "+".join(ob.obligation_key for ob in related)
    keys = [asset.spec.asset_key for asset in live]
    amortised_by = {
        asset.spec.asset_key: amortise.amortised(
            asset.spec, asset.segments, t, cx.revenue, cx.time_calendar, mu
        )
        for asset in live
    }
    carrying = [
        asset.spec.amount_capitalized
        - amortised_by[asset.spec.asset_key].value
        - asset.impaired
        + asset.reversed_
        - asset.clawback
        - asset.accelerated
        for asset in live
    ]
    if min(carrying) < 0:
        raise _invariant("a carrying amount is negative", first.contract_key, rule="S11-INV-01")
    consideration, source = _consideration(allocated, first.contract_key, related, t, mu)
    renewal = capitalise.renewal_at(cx.versions, t)
    eac, eac_versions = _eac(allocated, first.contract_key, related, t, mu)
    # D-89 L7-6-Q-7: progress costs when a PROGRESS_INPUT cost is effective by t, else run-off.
    extra: dict[str, str] = {}
    if capitalise.has_progress_input(allocated, first.contract_key, obligation_keys, t):
        costs = capitalise.progress_costs(allocated, first.contract_key, obligation_keys, t, mu)
        extra["costs_basis"] = "progress"
    else:
        costs, progress = _run_off(cx, related, eac_versions, t)
        extra["costs_basis"] = "run_off"
        extra["progress"] = "|".join(rational_param(g) for g in progress)
    earned = [
        target for ob in related if (target := cx.revenue.target(ob.subject_key, t)) is not None
    ]
    remaining_costs = 0 if eac is None else max(0, eac - costs)
    recoverable = (
        consideration - sum(target.value for target in earned) + _amount(renewal, mu)
    ) - remaining_costs
    recoverable_node = tb.node(
        measure="cost_recoverable",
        subject_key=group_key,
        period_key=period.period_key,
        value=recoverable,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=RECOVERABLE_FORMULA,
        inputs=[target.node_id for target in earned],
        params={
            "as_of": t.isoformat(),
            "consideration": str(consideration),
            "consideration_source": source,
            "costs": str(costs),
            "eac": "none" if eac is None else str(eac),
            "eac_versions": "|".join(version.version_key for version in eac_versions),
            "renewal": str(_amount(renewal, mu)),
            "renewal_version": "none" if renewal is None else renewal.version_key,
            **extra,
        },
        narrative_key=_narrative(RECOVERABLE_FORMULA),
    )
    if eac is None:
        for asset in live:
            if not asset.no_eac_reported:
                detail = {"period_key": period.period_key, "rule": "S11-R-09"}
                out.findings.append(
                    Finding("COST_NO_EAC", "INFO", asset.spec.asset_key, detail, _STAGE, None)
                )
                asset.no_eac_reported = True
    total = sum(carrying)
    impairment = min(total, max(0, total - recoverable)) if total > 0 else 0
    impaired = (
        money.largest_remainder(impairment, [Fraction(value) for value in carrying], keys)
        if impairment
        else [0] * len(live)
    )
    option = str(ctx.policies.value(REVERSAL_POLICY, entity=first.entity, period=period.period_key))
    unimpaired = [
        asset.spec.amount_capitalized
        - amortise.amortised(
            asset.spec, asset.segments[:1], t, cx.revenue, cx.time_calendar, mu
        ).value
        - asset.clawback
        - asset.accelerated
        for asset in live
    ]
    weights = carrying if total > 0 else [max(0, value) for value in unimpaired]
    reversals = [0] * len(live)
    if not impairment and option == REQUIRED_CAPPED and sum(weights) > 0:
        shares = money.largest_remainder(recoverable, [Fraction(value) for value in weights], keys)
        for index, asset in enumerate(live):
            raised = max(0, min(shares[index], unimpaired[index]) - carrying[index])
            reversals[index] = min(raised, asset.impaired - asset.reversed_)
    for index, asset in enumerate(live):
        _publish(
            cx,
            tb,
            period,
            asset,
            _Tested(
                amortised=amortised_by[asset.spec.asset_key],
                recoverable_node=recoverable_node,
                carrying=carrying[index],
                carrying_all=tuple(carrying),
                impaired=impaired[index],
                reversal=reversals[index],
                unimpaired=unimpaired[index],
                impaired_now=bool(impairment),
                keys=tuple(keys),
                weights=tuple(weights),
                option=option,
            ),
            out,
        )


@dataclass(frozen=True, slots=True)
class _Tested:
    """The period-end test result of one asset."""

    amortised: amortise.Amortised
    recoverable_node: str
    carrying: int  # after amortisation and events, before the test
    carrying_all: tuple[int, ...]  # of the related set, in key order
    impaired: int  # this period's impairment
    reversal: int  # this period's reversal
    unimpaired: int
    impaired_now: bool
    keys: tuple[str, ...]
    weights: tuple[int, ...]
    option: str  # POL-144


def _publish(
    cx: _Context, tb: TraceBuilder, period: PeriodInput, asset: _Asset, test: _Tested, out: _Out
) -> None:
    """Segments after the test, trace nodes, targets, T-CON-16 values and the schedule line."""
    ctx, mu = cx.ctx, cx.mu
    t = period.end_date
    spec = asset.spec
    key = spec.asset_key
    previous_impaired, previous_reversed = asset.impaired, asset.reversed_
    next_day = t + _ONE_DAY
    if test.impaired:
        asset.impaired += test.impaired
        asset.segments.append(
            CostSegment(next_day, asset.end, test.carrying - test.impaired, amortise.IMPAIRMENT)
        )
    if test.reversal:
        asset.reversed_ += test.reversal
        asset.segments.append(
            CostSegment(next_day, asset.end, test.carrying + test.reversal, amortise.REVERSAL)
        )
    after = test.carrying - test.impaired + test.reversal
    if after < 0 or asset.reversed_ > asset.impaired:
        raise _invariant(
            "the carrying amount or the reversals break S11-INV-01 or S11-INV-04",
            key,
            rule="S11-INV-04",
            period_key=period.period_key,
        )
    if test.reversal and after > test.unimpaired:
        raise _invariant(
            "a reversal exceeds the carrying amount without impairment",
            key,
            rule="S11-INV-04",
            period_key=period.period_key,
        )
    as_of = t.isoformat()
    capitalised_node = cx.capitalised_nodes[key]
    amortised = test.amortised
    amortised_node = tb.node(
        measure="cost_amortised_cum",
        subject_key=key,
        period_key=period.period_key,
        value=amortised.value,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=amortised.formula_id,
        inputs=[capitalised_node],
        params=amortised.params,
        narrative_key=_narrative(amortised.formula_id),
    )
    impaired_node = tb.node(
        measure="cost_impaired_cum",
        subject_key=key,
        period_key=period.period_key,
        value=asset.impaired,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=IMPAIR_FORMULA,
        inputs=[test.recoverable_node],
        params={
            "as_of": as_of,
            "carrying": "|".join(str(value) for value in test.carrying_all),
            "key": key,
            "keys": "|".join(test.keys),
            "previous": str(previous_impaired),
        },
        narrative_key=_narrative(IMPAIR_FORMULA),
    )
    reversal_params = {"as_of": as_of, "policy": test.option, "previous": str(previous_reversed)}
    if test.option == REQUIRED_CAPPED:
        reversal_params.update(
            {
                "carrying": str(test.carrying),
                "impaired_now": "true" if test.impaired_now else "false",
                "key": key,
                "keys": "|".join(test.keys),
                "open": str(previous_impaired - previous_reversed),
                "unimpaired": str(test.unimpaired),
                "weights": "|".join(str(value) for value in test.weights),
            }
        )
    reversed_node = tb.node(
        measure="cost_impairment_reversed_cum",
        subject_key=key,
        period_key=period.period_key,
        value=asset.reversed_,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=REVERSAL_FORMULA,
        inputs=[test.recoverable_node],
        params=reversal_params,
        narrative_key=_narrative(REVERSAL_FORMULA),
    )
    clawback_node = tb.node(
        measure="cost_clawback_cum",
        subject_key=key,
        period_key=period.period_key,
        value=asset.clawback,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=CLAWBACK_FORMULA,
        inputs=[item.ref for item in asset.clawbacks],
        params={
            "as_of": as_of,
            "carrying": "|".join(str(item.carrying) for item in asset.clawbacks),
            "taken_before": "|".join(str(item.taken_before) for item in asset.clawbacks),
        },
        narrative_key=_narrative(CLAWBACK_FORMULA),
    )
    accelerations = asset.accelerations
    accelerated_node = tb.node(
        measure="cost_accelerated_cum",
        subject_key=key,
        period_key=period.period_key,
        value=asset.accelerated,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=ACCELERATE_FORMULA,
        inputs=[capitalised_node],
        params={
            "after": "|".join(str(item.after) for item in accelerations),
            "all_ended": "|".join("true" if item.all_ended else "false" for item in accelerations),
            "as_of": as_of,
            "before": "|".join(str(item.before) for item in accelerations),
            "carrying": "|".join(str(item.carrying) for item in accelerations),
            "events": "|".join(item.event_key for item in accelerations),
            "policy": "|".join(item.policy for item in accelerations),
        },
        narrative_key=_narrative(ACCELERATE_FORMULA),
    )
    carrying_node = tb.node(
        measure="carrying_amount",
        subject_key=key,
        period_key=period.period_key,
        value=after,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=CARRYING_FORMULA,
        inputs=[
            capitalised_node,
            amortised_node,
            impaired_node,
            reversed_node,
            clawback_node,
            accelerated_node,
        ],
        params={"as_of": as_of, "signs": "+|-|-|+|-|-"},
        narrative_key=_narrative(CARRYING_FORMULA),
    )
    nodes = {
        "cost_capitalised": capitalised_node,
        "cost_amortised_cum": amortised_node,
        "cost_impaired_cum": impaired_node,
        "cost_impairment_reversed_cum": reversed_node,
        "cost_clawback_cum": clawback_node,
        "cost_accelerated_cum": accelerated_node,
        "carrying_amount": carrying_node,
    }
    values = {
        "cost_capitalised": spec.amount_capitalized,
        "cost_amortised_cum": amortised.value,
        "cost_impaired_cum": asset.impaired,
        "cost_impairment_reversed_cum": asset.reversed_,
        "cost_clawback_cum": asset.clawback,
        "cost_accelerated_cum": asset.accelerated,
        "carrying_amount": after,
    }
    for measure_name, node_id in nodes.items():
        out.targets.append(
            Target(
                ctx.book_code,
                spec.entity,
                key,
                measure_name,
                period.period_key,
                None,
                values[measure_name],
                None,
                node_id,
            )
        )
    out.measures[(key, period.period_key)] = CostAssetMeasures(
        asset_key=key,
        period_key=period.period_key,
        as_of=t,
        capitalized_cum=spec.amount_capitalized,
        amortized_cum=amortised.value,
        impaired_cum=asset.impaired,
        impairment_reversed_cum=asset.reversed_,
        clawback_cum=asset.clawback,
        accelerated_cum=asset.accelerated,
        carrying_amount=after,
        remaining_months=0 if t >= asset.end else capitalise.months_between(next_day, asset.end),
        renewal_version_key=asset.renewal_key,
        segments=tuple(asset.segments),
        trace_nodes=MappingProxyType(nodes),
    )
    amount = amortised.value - asset.amortised_before
    asset.amortised_before = amortised.value
    if amount:
        out.lines.append(
            ScheduleLineOut(
                schedule_kind=ScheduleKind.COST_AMORTIZATION,
                subject_type="contract_cost_asset",
                subject_key=key,
                entity=spec.entity,
                period_key=period.period_key,
                line_type=ScheduleLineType.NORMAL,
                amount=amount,
                cumulative_amount=amortised.value,
                cumulative_exact=Fraction(amortised.value, 10**mu),
                quantity=None,
                is_released_at_close=spec.amortization_pattern == STRAIGHT_LINE,
                trace_node_id=amortised_node,
            )
        )


def measure(
    ctx: BookContext,
    st: BalanceState,
    specs: Sequence[CostAssetSpec],
    capitalised_nodes: Mapping[str, str],
    tb: TraceBuilder,
) -> Measured:
    """Segment events, amortisation, the period-end tests and T-CON-16 values of one contract's
    assets."""
    allocated = st.allocated
    first = specs[0]
    if any(spec.contract_key != first.contract_key for spec in specs):
        raise _invariant(
            "the assets of one run name several contracts", first.contract_key, rule="S11-R-08"
        )
    by_key = {ob.subject_key: ob for ob in allocated.obligations}
    versions = capitalise.renewal_versions(allocated, first.contract_key)
    cx = _Context(
        ctx=ctx,
        allocated=allocated,
        by_key=MappingProxyType(by_key),
        revenue=Revenue(ctx, st.recognition.revenue_targets, by_key),
        calendar=tuple(
            sorted(
                ctx.entities[first.entity].periods,
                key=lambda period: (period.start_date, period.end_date),
            )
        ),
        versions=versions,
        capitalised_nodes=capitalised_nodes,
        mu=capitalise.minor_unit(ctx),
        time_calendar=_time_calendar(ctx, first.entity),
    )
    assets = [
        _Asset(
            spec=spec,
            segments=[
                CostSegment(
                    spec.amortization_start_date,
                    spec.amortization_end_date,
                    spec.amount_capitalized,
                    amortise.CAPITALISATION,
                )
            ],
            end=spec.amortization_end_date,
            applied={
                version.version_key
                for version in versions
                if version.effective_date <= spec.capitalization_date
            },
            renewal_key=spec.renewal_version_key,
        )
        for spec in sorted(specs, key=lambda spec: spec.asset_key)
    ]
    groups: dict[tuple[str, ...], list[_Asset]] = {}
    for asset in assets:
        groups.setdefault(asset.spec.related_obligation_keys, []).append(asset)
    changes = _changes(allocated, first.contract_key, versions)
    position = 0
    out = _Out()
    for period in capitalise.periods(ctx, allocated, first.entity):
        t = period.end_date
        while position < len(changes) and changes[position].order[0] <= t:
            _apply(cx, assets, changes[position], t)
            position += 1
        for related_keys in sorted(groups):
            live = [asset for asset in groups[related_keys] if asset.spec.capitalization_date <= t]
            if live:
                _test(cx, tb, period, live, out)
    return Measured(
        targets=tuple(out.targets),
        measures=MappingProxyType(out.measures),
        lines=tuple(out.lines),
        findings=tuple(out.findings),
    )
