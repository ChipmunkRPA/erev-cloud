"""Stage 11 capitalisation gate and amortisation period (ENGINE_SPEC_B §11.2.1, §11.2.2; ENC-15).

Every ``COST_INCURRED`` with ``purpose`` ``COST_TO_OBTAIN`` or ``COST_TO_FULFILL`` passes the gate
in ENG-06 order, except clawbacks (``cost_adjustment = CLAWBACK``; S11-R-12 in ``impair``). The
related obligations are the obligation named by the payload, else every obligation of the contract;
a named obligation outside the group yields ``COST_RELATED_POB_MISSING`` (ERROR) and no asset. A
cost is capitalised on the later of its date and the first date the contract is ``ACTIVE`` in the
book, and expensed with reason ``CONTRACT_NOT_ACTIVE`` when the contract never is (S11-R-01). The
amortisation period is the contract term of the related obligations, whole months rounded up,
unless POL-141 reads the approved ``RENEWAL_EXPECTATION`` version in force (S11-R-04). An
incremental cost to obtain is expensed under POL-140 ``APPLY`` when that period is 12 months or
less; a cost that is not incremental is expensed (340-40-25-3, 25-4). A cost to fulfil is
capitalised only with a REVIEWED attestation of the 340-40-25-5 criteria and is never capitalised
when wasted (S11-R-02; POL-146; L2-4-Q-33).
``PROPORTIONAL_TO_RELATED_REVENUE`` with a period different from the contract term yields
``COST_PATTERN_INVALID`` (ERROR) and no asset (POL-143). The asset key is the key of the
capitalising event (L2-4-Q-32). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import money
from erev_engine.bundle import EstimateVersionInput, PeriodInput
from erev_engine.errors import EngineError
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    ContractView,
    EventView,
    Finding,
    ObligationState,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "CAPITALISE_FORMULA",
    "CONTRACT_NOT_ACTIVE",
    "CONTRACT_TERM",
    "EXPEDIENT_ONE_YEAR",
    "EXPENSE_FORMULA",
    "FULFILMENT_NOT_ATTESTED",
    "NOT_INCREMENTAL",
    "PROPORTIONAL",
    "STRAIGHT_LINE",
    "CostAssetSpec",
    "ExpensedCost",
    "Gated",
    "amount_of",
    "end_of",
    "first_active_date",
    "gate",
    "has_progress_input",
    "minor_unit",
    "months_between",
    "period_containing",
    "periods",
    "progress_costs",
    "renewal_at",
    "renewal_versions",
]

COST_EVENT: Final = "COST_INCURRED"
COST_TO_OBTAIN: Final = "COST_TO_OBTAIN"
COST_TO_FULFILL: Final = "COST_TO_FULFILL"
PROGRESS_INPUT: Final = "PROGRESS_INPUT"
OBTAIN: Final = "OBTAIN"  # E-83
FULFILL: Final = "FULFILL"
NOT_INCREMENTAL: Final = "NOT_INCREMENTAL"
EXPEDIENT_ONE_YEAR: Final = "EXPEDIENT_ONE_YEAR"
FULFILMENT_NOT_ATTESTED: Final = "FULFILMENT_NOT_ATTESTED"
CONTRACT_NOT_ACTIVE: Final = "CONTRACT_NOT_ACTIVE"
STRAIGHT_LINE: Final = "STRAIGHT_LINE"
PROPORTIONAL: Final = "PROPORTIONAL_TO_RELATED_REVENUE"
CONTRACT_TERM: Final = "CONTRACT_TERM"
RENEWAL_EXPECTATION: Final = "RENEWAL_EXPECTATION"
CAPITALISE_FORMULA: Final = "cost.capitalise.v1"
EXPENSE_FORMULA: Final = "cost.expense_reason.v1"
_EXPEDIENT_POLICY: Final = "costs.obtain_expedient"  # POL-140
_PERIOD_POLICY: Final = "costs.amortisation_period"  # POL-141
_PATTERN_POLICY: Final = "costs.amortisation_pattern"  # POL-143
_CONVENTION_POLICY: Final = "recognition.time_convention"  # POL-090
_ATTESTATION_TOPIC: Final = "OTHER"  # E-56 has no fulfilment topic (L2-4-Q-33)
_ATTESTATION_MEMBER: Final = "fulfilment_25_5"
# T-CON-19 members of topic OTHER that the engine reads for other purposes.
_OTHER_MEMBERS: Final = frozenset(
    {"pol_044_override", "claim_enforceable", "returns_immaterial", "discount_exception_bundle"}
)
_ACTIVE: Final = "ACTIVE"
_STAGE: Final = 11


@dataclass(frozen=True, slots=True)
class CostAssetSpec:
    """T-CON-15 identity and terms of a capitalised cost (§11.1 ``cost_asset_specs``)."""

    asset_key: str  # the capitalising COST_INCURRED event key (L2-4-Q-32)
    contract_key: str
    entity: str  # contracting entity
    cost_kind: str  # E-83 OBTAIN | FULFILL
    payee: str | None
    plan_code: str | None
    capitalization_date: date
    amount_capitalized: int  # minor units
    related_obligation_keys: tuple[str, ...]  # obligation subject keys, sorted
    amortization_pattern: str  # POL-143
    amortization_start_date: date
    amortization_months: int
    amortization_end_date: date
    term_months: int  # contract term of the related obligations
    period_option: str  # POL-141
    time_convention: str  # POL-090
    renewal_version_key: str | None  # RENEWAL_EXPECTATION version in force at capitalisation
    has_clawback: bool


@dataclass(frozen=True, slots=True)
class ExpensedCost:
    """A cost not capitalised, with its reason (§11.1 ``expensed_costs``)."""

    event_key: str
    contract_key: str
    entity: str
    purpose: str
    amount: int
    # NOT_INCREMENTAL | EXPEDIENT_ONE_YEAR | FULFILMENT_NOT_ATTESTED | CONTRACT_NOT_ACTIVE
    reason: str
    node_id: str


@dataclass(frozen=True, slots=True)
class Gated:
    """The gate's result for one book."""

    specs: tuple[CostAssetSpec, ...]
    expensed: tuple[ExpensedCost, ...]
    findings: tuple[Finding, ...]
    capitalised_nodes: Mapping[str, str]  # asset key -> cost_capitalised node id


def _invariant(message: str, subject_key: str | None, **detail: str) -> EngineError:
    return EngineError("ENGINE_INVARIANT_VIOLATED", message, subject_key=subject_key, detail=detail)


def _narrative(formula_id: str) -> str:
    return formula_id.rsplit(".v", 1)[0]


def minor_unit(ctx: BookContext) -> int:
    """The minor unit of the book's transaction currency."""
    return ctx.currencies[ctx.txn_currency].minor_unit


def _text(ev: EventView, name: str) -> str | None:
    raw = ev.payload.get(name)
    return None if raw is None else str(raw)


def _flag(ev: EventView, name: str) -> bool:
    raw = ev.payload.get(name)
    return raw is True or raw == "true"


def amount_of(ev: EventView, mu: int) -> int:
    """The payload ``amount`` in minor units (CV-45)."""
    raw = ev.payload.get("amount")
    if isinstance(raw, str):
        raw = Decimal(raw)
    if isinstance(raw, bool) or not isinstance(raw, int | Decimal | Fraction):
        raise _invariant(
            "a cost event carries no amount", ev.contract_key, rule="CV-45", event_key=ev.event_key
        )
    exact = money.to_fraction(raw)
    posted = money.round_half_up(exact, mu)
    if Fraction(posted, 10**mu) != exact:
        raise _invariant(
            "a cost amount is not a whole number of minor units",
            ev.contract_key,
            rule="CV-45",
            event_key=ev.event_key,
        )
    return posted


def months_between(start: date, end: date) -> int:
    """Whole months of [start, end], rounded up, at least 1 (§11.2.2 ``contract_term_months``)."""
    months = 1
    while end_of(start, months) < end:
        months += 1
    return months


def end_of(start: date, months: int) -> date:
    """add_months(start, months) − 1 day (S11-R-03)."""
    year, month = divmod(start.month - 1 + months, 12)
    first = date(start.year + year, month + 1, 1)
    days_in = (date(first.year + (first.month // 12), first.month % 12 + 1, 1) - first).days
    return first.replace(day=min(start.day, days_in)) - timedelta(days=1)


def first_active_date(contract: ContractView, book_code: str) -> date | None:
    """The first date the contract is ``ACTIVE`` in the book (stage 02 ``status_in_book``)."""
    for when, status in contract.status_in_book.get(book_code, ()):
        if status == _ACTIVE:
            return when
    return None


def periods(ctx: BookContext, st: AllocatedState, entity_code: str) -> tuple[PeriodInput, ...]:
    """Periods of the contracting entity from the group's inception period through its horizon."""
    calendar = ctx.entities.get(entity_code)
    horizon_key = ctx.horizon.get(entity_code)
    if calendar is None or horizon_key is None:
        raise _invariant(
            "the contracting entity has no calendar or horizon", entity_code, rule="CV-13"
        )
    ordered = tuple(
        sorted(calendar.periods, key=lambda period: (period.start_date, period.end_date))
    )
    horizon = next((period for period in ordered if period.period_key == horizon_key), None)
    first = period_containing(ordered, st.inception_date, entity_code)
    if horizon is None:
        raise _invariant(
            "the horizon period is absent from the calendar", entity_code, rule="CV-13"
        )
    return tuple(
        period
        for period in ordered
        if period.start_date >= first.start_date and period.end_date <= horizon.end_date
    )


def period_containing(
    ordered: Sequence[PeriodInput], d: date, subject_key: str | None
) -> PeriodInput:
    """The period whose [start, end] contains ``d`` (CV-12)."""
    for period in ordered:
        if period.start_date <= d <= period.end_date:
            return period
    raise _invariant("a date lies outside the entity's calendar", subject_key, rule="CV-12")


def renewal_versions(st: AllocatedState, contract_key: str) -> tuple[EstimateVersionInput, ...]:
    """Every APPROVED ``RENEWAL_EXPECTATION`` version of the contract's elements, ascending."""
    found: dict[str, EstimateVersionInput] = {}
    for key in st.estimates.of_contract(contract_key):  # CV-21 encoded lookup (ENG-COST-ENC-1)
        for pin in st.estimates.pins[key]:
            version = pin.version
            if version.estimate_kind == RENEWAL_EXPECTATION and version.status == "APPROVED":
                found[version.version_key] = version
    return tuple(
        sorted(
            found.values(),
            key=lambda item: (item.effective_date, item.version_no, item.version_key),
        )
    )


def renewal_at(versions: Sequence[EstimateVersionInput], at: date) -> EstimateVersionInput | None:
    """The version in force at ``at``: the latest effective on or before it."""
    found: EstimateVersionInput | None = None
    for version in versions:
        if version.effective_date <= at:
            found = version
    return found


def progress_costs(
    st: AllocatedState, contract_key: str, obligation_keys: frozenset[str], t: date, mu: int
) -> int:
    """``PROGRESS_INPUT`` costs of the contract through ``t`` that name a related obligation or
    none."""
    total = 0
    for ev in st.measure_events:
        if ev.event_type != COST_EVENT or ev.contract_key != contract_key or ev.effective_date > t:
            continue
        if _text(ev, "purpose") != PROGRESS_INPUT:
            continue
        key = _text(ev, "obligation_key")
        if key is None or key in obligation_keys:
            total += amount_of(ev, mu)
    return total


def has_progress_input(
    st: AllocatedState, contract_key: str, obligation_keys: frozenset[str], t: date
) -> bool:
    """A ``PROGRESS_INPUT`` cost of the contract effective on or before ``t`` that names a related
    obligation or none (S11-R-09 as amended by D-89 L7-6-Q-7)."""
    for ev in st.measure_events:
        if ev.event_type != COST_EVENT or ev.contract_key != contract_key or ev.effective_date > t:
            continue
        if _text(ev, "purpose") != PROGRESS_INPUT:
            continue
        key = _text(ev, "obligation_key")
        if key is None or key in obligation_keys:
            return True
    return False


def _policy(ctx: BookContext, code: str, ob: ObligationState) -> str:
    """A pin K value for the plan's related obligation (CV-17)."""
    return str(
        ctx.policies.value(
            code, obligation=ob.subject_key, contract=ob.contract_key, entity=ob.contracting_entity
        )
    )


def _attested(
    ctx: BookContext,
    contract: ContractView,
    related: Sequence[ObligationState],
    plan_code: str | None,
) -> bool:
    """A REVIEWED ``OTHER`` record on the plan code, a related product or the contract attesting the
    340-40-25-5 criteria (S11-R-02; L2-4-Q-33)."""
    subjects = {
        contract.header.external_id,
        *(ob.product_code for ob in related if ob.product_code),
    }
    if plan_code is not None:
        subjects.add(plan_code)
    for judgement in contract.header.judgements:
        if judgement.topic != _ATTESTATION_TOPIC or judgement.subject_key not in subjects:
            continue
        if judgement.book_code not in (None, str(ctx.book_code)):
            continue
        member = judgement.outcome.get(_ATTESTATION_MEMBER)
        if member == "true" or (member is None and not _OTHER_MEMBERS & set(judgement.outcome)):
            return True
    return False


def gate(ctx: BookContext, st: AllocatedState, tb: TraceBuilder) -> Gated:
    """``capitalisation`` of §11.2.1 for every cost to obtain or fulfil of one book."""
    mu = minor_unit(ctx)
    contracts = {view.header.external_id: view for view in st.contracts}
    specs: list[CostAssetSpec] = []
    expensed: list[ExpensedCost] = []
    findings: list[Finding] = []
    nodes: dict[str, str] = {}
    for ev in st.measure_events:  # ENG-06 order
        purpose = _text(ev, "purpose")
        if ev.event_type != COST_EVENT or purpose not in (COST_TO_OBTAIN, COST_TO_FULFILL):
            continue
        if _text(ev, "cost_adjustment") is not None:
            continue  # clawbacks: S11-R-12 (ENC-16)
        contract = contracts.get(ev.contract_key)
        if contract is None:
            raise _invariant(
                "a cost event names a contract outside the group",
                ev.contract_key,
                rule="S11-R-01",
                event_key=ev.event_key,
            )
        header = contract.header
        entity = header.contracting_entity_code
        amount = amount_of(ev, mu)
        own = sorted(
            (ob for ob in st.obligations if ob.contract_key == ev.contract_key),
            key=lambda ob: ob.subject_key,
        )
        obligation_key = _text(ev, "obligation_key")
        related = (
            own
            if obligation_key is None
            else [ob for ob in own if ob.obligation_key == obligation_key]
        )
        if not related:
            findings.append(
                Finding(
                    "COST_RELATED_POB_MISSING",
                    "ERROR",
                    ev.event_key,
                    MappingProxyType({"obligation_key": obligation_key or "", "rule": "S11-R-01"}),
                    _STAGE,
                    ev.event_key,
                )
            )
            continue
        calendar = tuple(
            sorted(
                ctx.entities[entity].periods,
                key=lambda period: (period.start_date, period.end_date),
            )
        )
        source = SourceRef(
            "contract_event",
            ev.event_key,
            {"member": "amount", "value": money.format_money(amount, mu)},
        )
        active_on = first_active_date(contract, str(ctx.book_code))
        start = min(ob.start_date or header.inception_date for ob in related)
        ends = [ob.end_date for ob in related if ob.end_date is not None]
        term = months_between(start, max(ends)) if ends else 1
        cap_date = ev.effective_date if active_on is None else max(ev.effective_date, active_on)
        option = _policy(ctx, _PERIOD_POLICY, related[0])
        renewal = renewal_at(renewal_versions(st, ev.contract_key), cap_date)
        months = term
        if (
            option != CONTRACT_TERM
            and renewal is not None
            and renewal.amortization_months is not None
        ):
            months = renewal.amortization_months
        kind = OBTAIN if purpose == COST_TO_OBTAIN else FULFILL
        reason: str | None = None
        if active_on is None:
            reason = CONTRACT_NOT_ACTIVE
        elif kind == OBTAIN and not _flag(ev, "is_incremental"):
            reason = NOT_INCREMENTAL
        elif (
            kind == OBTAIN
            and months <= 12
            and _policy(ctx, _EXPEDIENT_POLICY, related[0]) == "APPLY"
        ):
            reason = EXPEDIENT_ONE_YEAR
        elif kind == FULFILL and (
            _flag(ev, "is_wasted") or not _attested(ctx, contract, related, _text(ev, "plan_code"))
        ):
            reason = FULFILMENT_NOT_ATTESTED
        params = {
            "as_of": ev.effective_date.isoformat(),
            "months": str(months),
            "period_option": option,
            "purpose": purpose,
            "term_months": str(term),
        }
        if reason is not None:
            node_id = tb.node(
                measure="cost_expensed",
                subject_key=ev.event_key,
                period_key=period_containing(calendar, ev.effective_date, ev.event_key).period_key,
                value=amount,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=EXPENSE_FORMULA,
                inputs=[source],
                params={**params, "reason": reason},
                narrative_key=_narrative(EXPENSE_FORMULA),
            )
            expensed.append(
                ExpensedCost(
                    ev.event_key, ev.contract_key, entity, purpose, amount, reason, node_id
                )
            )
            continue
        pattern = _policy(ctx, _PATTERN_POLICY, related[0])
        if pattern == PROPORTIONAL and months != term:
            detail = {"months": str(months), "rule": "POL-143", "term_months": str(term)}
            findings.append(
                Finding(
                    "COST_PATTERN_INVALID",
                    "ERROR",
                    ev.event_key,
                    MappingProxyType(detail),
                    _STAGE,
                    ev.event_key,
                )
            )
            continue
        spec = CostAssetSpec(
            asset_key=ev.event_key,
            contract_key=ev.contract_key,
            entity=entity,
            cost_kind=kind,
            payee=_text(ev, "payee"),
            plan_code=_text(ev, "plan_code"),
            capitalization_date=cap_date,
            amount_capitalized=amount,
            related_obligation_keys=tuple(ob.subject_key for ob in related),
            amortization_pattern=pattern,
            amortization_start_date=start,
            amortization_months=max(1, months),
            amortization_end_date=end_of(start, max(1, months)),
            term_months=term,
            period_option=option,
            time_convention=_policy(ctx, _CONVENTION_POLICY, related[0]),
            renewal_version_key=None if renewal is None else renewal.version_key,
            has_clawback=_flag(ev, "has_clawback"),
        )
        nodes[spec.asset_key] = tb.node(
            measure="cost_capitalised",
            subject_key=spec.asset_key,
            period_key=period_containing(calendar, cap_date, spec.asset_key).period_key,
            value=amount,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=CAPITALISE_FORMULA,
            inputs=[source],
            params={
                **params,
                "capitalization_date": cap_date.isoformat(),
                "convention": spec.time_convention,
                "end": spec.amortization_end_date.isoformat(),
                "has_clawback": "true" if spec.has_clawback else "false",
                "kind": kind,
                "pattern": pattern,
                "renewal_version": spec.renewal_version_key or "none",
                "start": start.isoformat(),
            },
            narrative_key=_narrative(CAPITALISE_FORMULA),
        )
        specs.append(spec)
    return Gated(
        specs=tuple(sorted(specs, key=lambda spec: spec.asset_key)),
        expensed=tuple(expensed),
        findings=tuple(findings),
        capitalised_nodes=MappingProxyType(nodes),
    )
