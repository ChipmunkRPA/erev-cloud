"""Stage 11 loss provisions (ENGINE_SPEC_B §11.2.7; POL-150 to POL-153; JET-12; ENC-16).

At every period end within the horizon each contract in the book's loss scope is tested at the
POL-150 unit. Under POL-151 ``SCOPED_605_35_ONLY`` the scope is the contract flag ``scope_605_35``
in force at the period end: the booking payload member, else the header column, replaced by the
latest ``CONTRACT_AMENDED`` payload that carries the member. Under ``ALL_CONTRACTS_WITH_EAC`` it is
a contract with an approved ``EAC`` version effective by the period end (S11-R-15; L2-4-Q-39). The
costs come from the latest version of each ``EAC`` element of the unit; under POL-152
``IAS37_68A_COSTS`` the ``EAC_IAS37`` elements replace them when present. The consideration is the
unconstrained, credit-adjusted transaction price of stage 04 allocated to the unit by exact
allocation weights, the exact allocation standing in without a build-up (S11-R-11a, S11-R-11b,
S11-R-16; POL-153; L2-4-Q-34). The provision required at t is max(0, max(0, EAC − TP_u) − max(0,
costs − revenue)) and the movement is required(t) − required(t − 1) (S11-R-14; S11-INV-05). A unit
measured on costs, with costs incurred and no ``EAC`` version at a period end, yields
``LOSS_EAC_MISSING`` (WARNING) for that period end. The ``LOSS_PROVISION_RELEASE`` lines project the
provision at the horizon and are never released at close (S11-R-17; L2-4-Q-41). Standard library
only (DG-ARC-02).
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
from erev_engine.stages.s11_costs_loss import capitalise
from erev_engine.stages.s11_costs_loss.amortise import Revenue
from erev_engine.stages.s11_costs_loss.impair import x_exact
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    ContractView,
    Finding,
    ObligationState,
    ScheduleLineOut,
    Target,
)
from erev_engine.trace import TraceBuilder

__all__ = [
    "MARGIN_FORMULA",
    "MOVEMENT_FORMULA",
    "REQUIRED_FORMULA",
    "TP_FORMULA",
    "LossMeasures",
    "Losses",
    "measure",
    "scope_605_35_at",
]

TP_FORMULA: Final = "loss.tp_unconstrained.v1"
MARGIN_FORMULA: Final = "loss.expected_margin.v1"
REQUIRED_FORMULA: Final = "loss.required_provision.v1"
MOVEMENT_FORMULA: Final = "loss.movement.v1"
_UNIT_POLICY: Final = "loss.unit"  # POL-150
_SCOPE_POLICY: Final = "loss.scope"  # POL-151
_COST_BASIS_POLICY: Final = "loss.cost_basis"  # POL-152
_CONTRACT_UNIT: Final = "CONTRACT"
_POB_UNIT: Final = "POB"
_SCOPED: Final = "SCOPED_605_35_ONLY"
_IAS37_COSTS: Final = "IAS37_68A_COSTS"
_EAC: Final = "EAC"
_EAC_IAS37: Final = "EAC_IAS37"
_AMENDED: Final = "CONTRACT_AMENDED"
_SCOPE_MEMBER: Final = "scope_605_35"
_COST_MEASURES: Final = frozenset({"COST_TO_COST"})
# S11-R-17 asks the METHOD of every unit obligation and not the predicate of S09-R-45 (stage 09
# ``is_deterministic``): its question is whether the unit's ``REVENUE`` schedule lines are the whole
# of the unit's remaining revenue. The lines of a usage obligation with a fixed fee are the fee
# alone — its usage fees stand on no schedule — so such an obligation is deterministic there and
# its unit is not released over its lines here (rev 1.126; L2-4-Q-25).
_WHOLLY_SCHEDULED: Final = "TIME_ELAPSED"
_STAGE: Final = 11


@dataclass(frozen=True, slots=True)
class LossMeasures:
    """T-CON-17 values of one loss unit at a period end (§11.1 ``loss_provisions``)."""

    unit_key: str  # the contract key (CONTRACT) or the obligation subject key (POB)
    contract_key: str
    obligation_key: str | None  # POB unit only
    unit: str  # E literal ``CONTRACT`` | ``POB``
    entity: str  # contracting entity
    period_key: str
    as_of: date
    measurement_basis: str  # ASC_605_35 | IAS_37
    eac_version_keys: tuple[str, ...]
    currency: str
    expected_consideration: int
    expected_total_costs: int  # 0 without an EAC version
    costs_to_date: int
    revenue_to_date: int
    expected_margin: int
    provision_balance: int
    provision_movement: int
    in_scope: bool
    trace_nodes: Mapping[str, str]  # measure -> node id


@dataclass(frozen=True, slots=True)
class Losses:
    """The loss tests of one book."""

    targets: tuple[Target, ...]
    measures: Mapping[tuple[str, str], LossMeasures]
    lines: tuple[ScheduleLineOut, ...]
    findings: tuple[Finding, ...]


@dataclass(frozen=True, slots=True)
class _Unit:
    key: str
    contract_key: str
    entity: str
    obligation: ObligationState | None  # None for a contract unit
    obligations: tuple[ObligationState, ...]
    sole: bool  # the contract has one obligation: unnamed costs and EAC versions belong to it


@dataclass(slots=True)
class _Out:
    targets: list[Target] = field(default_factory=list)
    measures: dict[tuple[str, str], LossMeasures] = field(default_factory=dict)
    lines: list[ScheduleLineOut] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


def _invariant(message: str, subject_key: str | None, **detail: str) -> EngineError:
    return EngineError("ENGINE_INVARIANT_VIOLATED", message, subject_key=subject_key, detail=detail)


def _narrative(formula_id: str) -> str:
    return formula_id.rsplit(".v", 1)[0]


def scope_605_35_at(st: AllocatedState, contract: ContractView, t: date) -> bool:
    """The T-CON-01 flag in force at ``t``: booking payload (else header), then the latest
    ``CONTRACT_AMENDED`` payload carrying the member (§11.1; T-CON-06)."""
    key = contract.header.external_id
    raw: object = contract.booking.get(_SCOPE_MEMBER, contract.header.scope_605_35)
    for ev in st.events:  # ENG-06 order
        if ev.contract_key != key or ev.event_type != _AMENDED or ev.effective_date > t:
            continue
        member = ev.payload.get(_SCOPE_MEMBER)
        if member is not None:
            raw = member
    return raw is True or raw == "true"


def _has_eac(st: AllocatedState, contract_key: str, t: date) -> bool:
    """An approved ``EAC`` version of the contract effective by ``t`` (POL-151
    ``ALL_CONTRACTS_WITH_EAC``)."""
    return any(
        (version := st.estimates.pin(key, t)) is not None and version.estimate_kind == _EAC
        for key in st.estimates.of_contract(contract_key)  # CV-21 encoded lookup (ENG-COST-ENC-1)
    )


def _names_unit(unit: _Unit, obligation_key: object) -> bool:
    """An event or version naming ``obligation_key`` (or none) belongs to the unit (L2-4-Q-40)."""
    if unit.obligation is None:
        return True
    if obligation_key is None:
        return unit.sole
    return obligation_key == unit.obligation.obligation_key


def _eac(
    st: AllocatedState, unit: _Unit, t: date, ias37: bool, mu: int
) -> tuple[int | None, tuple[str, ...]]:
    """Σ ``expected_total_amount`` of the latest version at ``t`` of each ``EAC`` element of the
    unit; the ``EAC_IAS37`` elements replace the others under IAS 37.68A when present (S11-R-15)."""
    found: list[EstimateVersionInput] = []
    for key in st.estimates.of_contract(unit.contract_key):  # CV-21 encoded lookup
        version = st.estimates.pin(key, t)
        if version is None or version.estimate_kind != _EAC:
            continue
        if version.expected_total_amount is None or not _names_unit(unit, version.obligation_key):
            continue
        found.append(version)
    reserved = [version for version in found if version.element_code == _EAC_IAS37]
    chosen = (
        reserved
        if ias37 and reserved
        else [version for version in found if version.element_code != _EAC_IAS37]
    )
    if not chosen:
        return None, ()
    total = sum(
        money.round_half_up(money.to_fraction(version.expected_total_amount), mu)
        for version in chosen
        if version.expected_total_amount is not None
    )
    return total, tuple(version.version_key for version in chosen)


def _costs(st: AllocatedState, unit: _Unit, t: date, mu: int) -> int:
    """``PROGRESS_INPUT`` costs of the unit through ``t`` (§11.2.7 ``progress_costs_to_date``)."""
    total = 0
    for ev in st.measure_events:
        if ev.event_type != capitalise.COST_EVENT or ev.contract_key != unit.contract_key:
            continue
        if ev.effective_date > t or ev.payload.get("purpose") != capitalise.PROGRESS_INPUT:
            continue
        if _names_unit(unit, ev.payload.get("obligation_key")):
            total += capitalise.amount_of(ev, mu)
    return total


def _consideration(
    st: AllocatedState, unit: _Unit, own: Sequence[ObligationState], t: date
) -> tuple[Fraction, Fraction, Fraction, str]:
    """(total, unit weight, contract weight, source) of the S11-R-11b allocation (L2-4-Q-34)."""
    contract_weight = sum((x_exact(ob, t) for ob in own), Fraction(0))
    unit_weight = sum((x_exact(ob, t) for ob in unit.obligations), Fraction(0))
    build = None
    for item in st.tp_unconstrained.get(unit.contract_key, ()):
        if item.at <= t and (build is None or item.at >= build.at):
            build = item
    if build is None:
        return contract_weight, unit_weight, contract_weight, "allocation"
    return build.total.exact, unit_weight, contract_weight, "tp_unconstrained"


def _release(
    ctx: BookContext,
    st: BalanceState,
    unit: _Unit,
    t: date,
    provision: int,
    node_id: str,
    calendar: Sequence[PeriodInput],
    mu: int,
) -> list[ScheduleLineOut]:
    """S11-R-17: the provision at the horizon released by the unit's remaining scheduled revenue
    when every unit obligation is ``TIME_ELAPSED`` — the method, not the predicate of S09-R-45 —
    else as one line in the period of the latest unit end date (L2-4-Q-41)."""
    if provision <= 0:
        return []
    scale: int = 10**mu
    ends = {period.period_key: period.end_date for period in calendar}
    keys = {ob.subject_key for ob in unit.obligations}
    amounts: dict[str, int] = {}
    if all(str(ob.recognition_method) == _WHOLLY_SCHEDULED for ob in unit.obligations):
        for item in st.recognition.schedule_lines:
            if item.schedule_kind != ScheduleKind.REVENUE or item.subject_key not in keys:
                continue
            if ends.get(item.period_key, date.min) > t:
                amounts[item.period_key] = amounts.get(item.period_key, 0) + item.amount
    remaining = sum(amounts.values())
    subject_type = "contract" if unit.obligation is None else "obligation"

    def line(period_key: str, amount: int, cumulative: int, exact: Fraction) -> ScheduleLineOut:
        return ScheduleLineOut(
            schedule_kind=ScheduleKind.LOSS_PROVISION_RELEASE,
            subject_type=subject_type,
            subject_key=unit.key,
            entity=unit.entity,
            period_key=period_key,
            line_type=ScheduleLineType.NORMAL,
            amount=amount,
            cumulative_amount=cumulative,
            cumulative_exact=exact,
            quantity=None,
            is_released_at_close=False,
            trace_node_id=node_id,
        )

    if remaining > 0:
        out: list[ScheduleLineOut] = []
        earned, previous = 0, 0
        for period in calendar:
            if period.period_key not in amounts:
                continue
            earned += amounts[period.period_key]
            ratio = min(Fraction(1), max(Fraction(0), Fraction(earned, remaining)))
            cumulative = money.cumulative_posted(Fraction(provision, scale), provision, ratio, mu)
            if cumulative != previous:
                exact = Fraction(provision, scale) * ratio
                out.append(line(period.period_key, cumulative - previous, cumulative, exact))
            previous = cumulative
        return out
    latest = max((ob.end_date for ob in unit.obligations if ob.end_date is not None), default=t)
    when = max(latest, t + timedelta(days=1))
    period = next(
        (item for item in calendar if item.start_date <= when <= item.end_date), calendar[-1]
    )
    return [line(period.period_key, provision, provision, Fraction(provision, scale))]


def _units(
    ctx: BookContext, contract: ContractView, own: Sequence[ObligationState]
) -> tuple[str, list[_Unit]]:
    key = contract.header.external_id
    entity = contract.header.contracting_entity_code
    option = str(ctx.policies.value(_UNIT_POLICY, contract=key, entity=entity))
    sole = len(own) == 1
    if option == _CONTRACT_UNIT:
        return option, [_Unit(key, key, entity, None, tuple(own), sole)]
    if option != _POB_UNIT:
        raise _invariant("unknown loss unit", key, rule="POL-150", unit=option)
    return option, [_Unit(ob.subject_key, key, entity, ob, (ob,), sole) for ob in own]


def _contract(
    ctx: BookContext,
    st: BalanceState,
    tb: TraceBuilder,
    contract: ContractView,
    revenue: Revenue,
    out: _Out,
) -> None:
    """The loss tests of one contract across the book's periods (§11.2.7)."""
    allocated = st.allocated
    mu = capitalise.minor_unit(ctx)
    key = contract.header.external_id
    entity = contract.header.contracting_entity_code
    own = sorted(
        (ob for ob in allocated.obligations if ob.contract_key == key),
        key=lambda ob: ob.subject_key,
    )
    if not own:
        return
    option, units = _units(ctx, contract, own)
    scope = str(ctx.policies.value(_SCOPE_POLICY, contract=key, entity=entity))
    ias37 = str(ctx.policies.value(_COST_BASIS_POLICY, contract=key, entity=entity)) == _IAS37_COSTS
    basis = "IAS_37" if ias37 else "ASC_605_35"
    calendar = tuple(
        sorted(
            ctx.entities[entity].periods, key=lambda period: (period.start_date, period.end_date)
        )
    )
    previous: dict[str, tuple[str, int]] = {}  # unit key -> (required node id, value)
    last: dict[str, tuple[date, int, str]] = {}  # unit key -> (as of, required, node id)
    for period in capitalise.periods(ctx, allocated, entity):
        t = period.end_date
        in_scope = (
            scope_605_35_at(allocated, contract, t)
            if scope == _SCOPED
            else _has_eac(allocated, key, t)
        )
        if not in_scope and not previous:
            continue
        for unit in units:
            eac, versions = _eac(allocated, unit, t, ias37, mu) if in_scope else (None, ())
            costs = _costs(allocated, unit, t, mu)
            earned = [
                target
                for ob in unit.obligations
                if (target := revenue.target(ob.subject_key, t)) is not None
            ]
            revenue_to_date = sum(target.value for target in earned)
            total, unit_weight, contract_weight, source = _consideration(allocated, unit, own, t)
            exact = total if contract_weight == 0 else total * unit_weight / contract_weight
            consideration = money.round_half_up(exact, mu)
            as_of = t.isoformat()
            eac_param = "none" if eac is None else str(eac)
            tp_node = tb.node(
                measure="tp_unconstrained_credit_adjusted",
                subject_key=unit.key,
                period_key=period.period_key,
                value=consideration,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=TP_FORMULA,
                inputs=[],
                params={
                    "as_of": as_of,
                    "contract_weight": rational_param(contract_weight),
                    "source": source,
                    "total": rational_param(total),
                    "unit_weight": rational_param(unit_weight),
                },
                narrative_key=_narrative(TP_FORMULA),
            )
            margin = consideration - (eac or 0)
            margin_node = tb.node(
                measure="expected_margin",
                subject_key=unit.key,
                period_key=period.period_key,
                value=margin,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=MARGIN_FORMULA,
                inputs=[tp_node],
                params={"as_of": as_of, "eac": eac_param},
                narrative_key=_narrative(MARGIN_FORMULA),
            )
            total_loss = 0 if eac is None else max(0, eac - consideration)
            margin_loss = max(0, costs - revenue_to_date)
            required = 0 if eac is None else max(0, total_loss - margin_loss)
            completed = eac is not None and costs == eac and revenue_to_date == consideration
            if not 0 <= required <= total_loss or (completed and required != 0):
                raise _invariant(
                    "the required provision breaks S11-INV-05",
                    unit.key,
                    rule="S11-INV-05",
                    period_key=period.period_key,
                )
            required_node = tb.node(
                measure="loss_provision_required",
                subject_key=unit.key,
                period_key=period.period_key,
                value=required,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=REQUIRED_FORMULA,
                inputs=[tp_node, *(target.node_id for target in earned)],
                params={
                    "as_of": as_of,
                    "costs": str(costs),
                    "eac": eac_param,
                    "eac_versions": "|".join(versions),
                    "in_scope": "true" if in_scope else "false",
                    "unit": option,
                },
                narrative_key=_narrative(REQUIRED_FORMULA),
            )
            prior = previous.get(unit.key)
            movement = required - (0 if prior is None else prior[1])
            movement_node = tb.node(
                measure="provision_movement",
                subject_key=unit.key,
                period_key=period.period_key,
                value=movement,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=MOVEMENT_FORMULA,
                inputs=[required_node] if prior is None else [required_node, prior[0]],
                params={"as_of": as_of},
                narrative_key=_narrative(MOVEMENT_FORMULA),
            )
            previous[unit.key] = (required_node, required)
            last[unit.key] = (t, required, required_node)
            measured_on_costs = any(
                str(ob.recognition_method) in _COST_MEASURES for ob in unit.obligations
            )
            if in_scope and eac is None and costs > 0 and measured_on_costs:
                detail = {"period_key": period.period_key, "rule": "S11-R-14"}
                out.findings.append(
                    Finding(
                        "LOSS_EAC_MISSING",
                        "WARNING",
                        unit.key,
                        MappingProxyType(detail),
                        _STAGE,
                        None,
                    )
                )
            nodes = {
                "tp_unconstrained_credit_adjusted": tp_node,
                "expected_margin": margin_node,
                "loss_provision_required": required_node,
                "provision_movement": movement_node,
            }
            values = {
                "tp_unconstrained_credit_adjusted": consideration,
                "expected_margin": margin,
                "loss_provision_required": required,
                "provision_movement": movement,
            }
            for measure_name, node_id in nodes.items():
                out.targets.append(
                    Target(
                        ctx.book_code,
                        entity,
                        unit.key,
                        measure_name,
                        period.period_key,
                        None,
                        values[measure_name],
                        None,
                        node_id,
                    )
                )
            out.measures[(unit.key, period.period_key)] = LossMeasures(
                unit_key=unit.key,
                contract_key=key,
                obligation_key=None if unit.obligation is None else unit.obligation.obligation_key,
                unit=option,
                entity=entity,
                period_key=period.period_key,
                as_of=t,
                measurement_basis=basis,
                eac_version_keys=versions,
                currency=ctx.txn_currency,
                expected_consideration=consideration,
                expected_total_costs=eac or 0,
                costs_to_date=costs,
                revenue_to_date=revenue_to_date,
                expected_margin=margin,
                provision_balance=required,
                provision_movement=movement,
                in_scope=in_scope,
                trace_nodes=MappingProxyType(nodes),
            )
    for unit in units:
        if unit.key in last:
            t, required, node_id = last[unit.key]
            out.lines.extend(_release(ctx, st, unit, t, required, node_id, calendar, mu))


def measure(ctx: BookContext, st: BalanceState, tb: TraceBuilder) -> Losses:
    """The loss provisions of every member contract of one book (§11.2.7)."""
    allocated = st.allocated
    by_key = {ob.subject_key: ob for ob in allocated.obligations}
    revenue = Revenue(ctx, st.recognition.revenue_targets, by_key)
    out = _Out()
    for contract in sorted(allocated.contracts, key=lambda view: view.header.external_id):
        _contract(ctx, st, tb, contract, revenue, out)
    return Losses(
        targets=tuple(out.targets),
        measures=MappingProxyType(out.measures),
        lines=tuple(out.lines),
        findings=tuple(out.findings),
    )
