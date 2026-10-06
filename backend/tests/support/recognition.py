"""Stage 09 state builders for engine tests (ENGINE_SPEC_B §0.5; ENGINE_SPEC §0.11; ENC-1).

Stage 09 tests build ``AllocatedState`` directly against the documented state contract, because the
stages that fold it (02 to 08) are built in other sprint lanes (D-81 integration after merge). The
builders read no clock, draw no random values and need no database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

from erev_engine.bundle import (
    EntityInput,
    EstimateVersionInput,
    JudgementInput,
    ResolvedPolicyInput,
)
from erev_engine.enums import (
    BookCode,
    Distinctness,
    LicenceNature,
    ObligationKind,
    PrincipalAgent,
    RatableConvention,
    RecognitionMethod,
    SatisfactionPattern,
    ScopeFlag,
    WarrantyType,
)
from erev_engine.money import decimal_to_minor, format_money
from erev_engine.stages import BOUNDARY_EVENT_TYPES
from erev_engine.stages.s09_recognition import RecognitionState, components, decompose
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    ConcessionAddition,
    ContractView,
    EstimatePins,
    EventView,
    ObligationState,
    PolicyResolver,
    ProgressBase,
    ProgressTotals,
    QuantityLedger,
    Quota,
    SegmentCause,
    SpecialistTargets,
)
from erev_engine.trace import SourceRef, TraceBuilder
from support.bundles import (
    ENTITY_CODE,
    INCEPTION,
    account_mapping,
    contract,
    currencies,
    entity,
    policy_set,
)

CONTRACT_KEY = "K-01"
ZERO = Fraction(0)
ONE = Fraction(1)
POINT_IN_TIME_METHODS = frozenset({"POINT_IN_TIME", "UNITS_DELIVERED", "MANUAL"})
BILL_AND_HOLD_MEMBERS = (
    "reason_substantive",
    "identified_as_customer_product",
    "ready_for_physical_transfer",
    "cannot_use_or_direct_to_another_customer",
)


def usd(amount: str) -> int:
    """USD minor units of a plain decimal string."""
    return decimal_to_minor(Decimal(amount), 2)


def book_context(
    calendar: EntityInput | None = None,
    *,
    book_code: str = "ASC606",
    horizon: str | None = None,
    preset: str = "DEFAULT",
    currency: str = "USD",
    overrides: Iterable[tuple[str, str, str, str]] = (),
) -> BookContext:
    """One entity and book; the horizon defaults to the entity's last period (C-05).

    ``overrides`` adds pin ``K`` values as (code, scope, subject key, value), for example an
    obligation-level POL-095 option (level ``O``, CV-17).
    """
    calendar = entity() if calendar is None else calendar
    code = BookCode(book_code)
    resolved = list(policy_set(preset, book_code=book_code, entity=calendar))
    for policy_code, scope, subject_key, value in overrides:
        level = {"OBLIGATION": "O", "CONTRACT": "C", "ENTITY": "E"}[scope]
        resolved.append(
            ResolvedPolicyInput(policy_code, scope, subject_key, value, level, "OVR-TEST", "K")
        )
    return BookContext(
        book_code=code,
        framework=code,
        currencies=currencies(currency),
        txn_currency=currency,
        entities={calendar.code: calendar},
        horizon={calendar.code: horizon or calendar.periods[-1].period_key},
        policies=PolicyResolver(
            tuple(sorted(resolved, key=lambda p: (p.code, p.scope, p.subject_key)))
        ),
        mapping=account_mapping(),
        trigger="COMMAND",
        tenant_preset=preset,
    )


def segment(
    x_exact: Fraction | int,
    a_posted: int,
    *,
    start: date | None,
    end: date | None,
    effective: date | None = None,
    basis: str = "INCEPTION",
    cause: SegmentCause = SegmentCause.INCEPTION,
    component: str = "FIXED",
    event_key: str | None = None,
    base_revenue_posted: int = 0,
    base_revenue_exact: Fraction = ZERO,
    quantity: Fraction = ONE,
    base_delivered: Fraction = ZERO,
    measure: str = "TIME_ELAPSED",
) -> AllocationSegment:
    """An allocation segment effective on ``effective`` (default ``start``) with updated totals."""
    effective_date = effective or start or INCEPTION
    return AllocationSegment(
        component=component,
        effective_date=effective_date,
        event_key=event_key,
        cause=cause,
        basis=basis,
        x_exact=Fraction(x_exact),
        a_posted=a_posted,
        base_revenue_posted=base_revenue_posted,
        base_revenue_exact=base_revenue_exact,
        base_progress=ProgressBase(
            base_delivered, ZERO, ZERO, effective_date if basis == "PROSPECTIVE" else None
        ),
        totals=ProgressTotals(quantity, None, start, end),
        progress_measure=measure,
        unit_ssp=None,
        remaining_ssp=ZERO,
        remaining_billing_plan=ZERO,
        estimate_pair=(None, None),
        modification_boundary_no=1 if basis == "PROSPECTIVE" else 0,
    )


def obligation(
    obligation_key: str,
    segments: Sequence[AllocationSegment],
    *,
    contract_key: str = CONTRACT_KEY,
    method: str = "TIME_ELAPSED",
    convention: str | None = "DAILY",
    pattern: str | None = None,
    criterion: str | None = None,
    kind: str = "STANDARD",
    start: date | None = None,
    end: date | None = None,
    recognition_start: date | None = None,
    entity_code: str = ENTITY_CODE,
    scope: str = "IN_SCOPE_606",
    quantity: Fraction = ONE,
    inception_weight: Fraction | None = None,
) -> ObligationState:
    """An obligation over ``segments``; pattern and criterion follow the method (T-REF-23).

    ``inception_weight`` is the S08-R-04 routing weight; it defaults to the first segment's exact
    allocation, the ``resolved_ssp`` of the builder.
    """
    point_in_time = method in POINT_IN_TIME_METHODS
    if pattern is None:
        pattern = "POINT_IN_TIME" if point_in_time else "OVER_TIME"
    if criterion is None:
        criterion = "NOT_APPLICABLE" if pattern == "POINT_IN_TIME" else "OT_A"
    first = segments[0]
    return ObligationState(
        subject_key=f"{contract_key}/{obligation_key}",
        contract_key=contract_key,
        obligation_key=obligation_key,
        obligation_kind=ObligationKind(kind),
        distinctness=Distinctness.DISTINCT,
        satisfaction_pattern=SatisfactionPattern(pattern),
        recognition_method=RecognitionMethod(method),
        ratable_convention=(
            RatableConvention(convention)
            if method == "TIME_ELAPSED" and convention is not None
            else None
        ),
        principal_agent=PrincipalAgent.PRINCIPAL,
        licence_nature=LicenceNature.NOT_APPLICABLE,
        scope_flag=ScopeFlag(scope),
        start_date=start or first.totals.start_date,
        end_date=end or first.totals.end_date,
        recognition_start_date=recognition_start,
        contracting_entity=entity_code,
        performing_entity=entity_code,
        quantity=quantity,
        resolved_ssp=first.x_exact,
        revenue_category=None,
        dimensions={},
        account_overrides={},
        segments=tuple(segments),
        opening=None,
        terminated_on=None,
        template_version_key="TPL-TEST@v1",
        product_code="SKU-1",
        sku_number=None,
        stratification=None,
        series_increment_unit=None,
        over_time_criterion=criterion,
        warranty_type=WarrantyType.NONE,
        material_right=None,
        ssp=None,
        original_quantity=quantity,
        original_stated_price=first.x_exact,
        stated_price=first.x_exact,
        original_allocation=Quota(first.x_exact, first.a_posted),
        original_total_contract_price=first.x_exact,
        original_total_contract_ssp=first.x_exact,
        is_vc_line=False,
        gross_to_net=None,
        lineage_pre_modification=(),
        assurance_cost_per_unit=None,
        last_modification_key=None,
        inception_weight=first.x_exact if inception_weight is None else inception_weight,
    )


def bill_and_hold_judgement(
    obligation_key: str, *, unmet: Iterable[str] = (), book_code: str | None = None
) -> JudgementInput:
    """A REVIEWED ``BILL_AND_HOLD`` record; members named in ``unmet`` are ``false`` (S09-R-12)."""
    failed = set(unmet)
    outcome = {member: "false" if member in failed else "true" for member in BILL_AND_HOLD_MEMBERS}
    return JudgementInput(
        judgement_key=f"JDG-BH-{obligation_key}",
        topic="BILL_AND_HOLD",
        subject_key=f"{CONTRACT_KEY}/{obligation_key}",
        book_code=book_code,
        outcome={"obligation_key": obligation_key, **outcome},
    )


def contract_view(
    external_id: str = CONTRACT_KEY,
    *,
    statuses: Sequence[tuple[date, str]] = ((INCEPTION, "ACTIVE"),),
    book_code: str = "ASC606",
    judgements: Sequence[JudgementInput] = (),
) -> ContractView:
    """A member contract whose book status history is ``statuses`` (stage 02 ``status_in_book``)."""
    header = dataclasses.replace(contract(external_id), judgements=tuple(judgements))
    return ContractView(header=header, booking={}, status_in_book={book_code: tuple(statuses)})


def concession_history(
    subject_key: str, event: EventView, quota: Quota, producer: str = "06"
) -> tuple[ConcessionAddition, ...]:
    """The one-entry dated concession subledger that conserves a hand-built ``CONCESSION`` refund
    quota (S10-R-26): the whole quota produced by ``event`` (stage 06 ``CREDIT_OR_REFUND`` by
    default), so ``check_history`` accepts the state a test assembles from ``refund_components``."""
    return (
        ConcessionAddition(
            subject_key,
            event.event_key,
            event.effective_date,
            event.order_key,
            quota.x_exact,
            quota.a_posted,
            producer,
            "EMBEDDED",
        ),
    )


def event_view(
    contract_key: str,
    stream_version: int,
    event_type: str,
    effective_date: date,
    payload: Mapping[str, object],
    *,
    obligation_keys: Iterable[str] = (),
    record_seq: int | None = None,
) -> EventView:
    """A canonical event with the CV-22 key and obligation subject keys."""
    event_key = f"{contract_key}/EV-{stream_version:06d}"
    return EventView(
        event_key=event_key,
        contract_key=contract_key,
        event_type=event_type,
        effective_date=effective_date,
        record_seq=stream_version if record_seq is None else record_seq,
        recorded_at=datetime(
            effective_date.year, effective_date.month, effective_date.day, 12, tzinfo=UTC
        ),
        obligation_subject_keys=tuple(f"{contract_key}/{key}" for key in obligation_keys),
        payload=payload,
        is_new=True,
        source=SourceRef("contract_event", event_key),
    )


def estimate_version(
    estimate_key: str,
    kind: str,
    version_no: int,
    effective: date,
    *,
    obligation_key: str | None = None,
) -> EstimateVersionInput:
    """An APPROVED T-CON-13 version of ``kind`` (E-09) effective on ``effective``."""
    return EstimateVersionInput(
        estimate_key=estimate_key,
        estimate_kind=kind,
        element_code=estimate_key.rsplit("/", 1)[-1],
        method="MOST_LIKELY_AMOUNT",
        vc_element_type=None,
        allocation_target="OBLIGATION",
        target_obligation_keys=() if obligation_key is None else (obligation_key,),
        obligation_key=obligation_key,
        version_key=f"{estimate_key}@v{version_no}",
        version_no=version_no,
        status="APPROVED",
        effective_date=effective,
        scenarios=(),
        parameters={},
        unconstrained_amount=None,
        most_conservative_amount=None,
        constrained_amount=None,
        rate=None,
        expected_total_amount=None,
        expected_quantity=None,
        amortization_months=None,
        currency="USD",
        supersedes_version_key=None if version_no == 1 else f"{estimate_key}@v{version_no - 1}",
        judgement_key=None,
        content_sha256="0" * 64,
    )


def emit_catch_up_nodes(
    tb: TraceBuilder,
    ctx: BookContext,
    st: AllocatedState,
    values: Mapping[tuple[str, str], int] | None = None,
) -> dict[tuple[str, str], int]:
    """Fake the stage 06 and stage 08 nodes ``catch_up@<event key>:<ob>:-`` (S06-R-17; D-81).

    ``values`` maps (event key, obligation subject key) to the published catch-up in minor units;
    other boundaries publish C_after(d) − C_before(d) of the segment targets at the boundary
    position. Returns the values published.
    """
    mu = ctx.currencies[ctx.txn_currency].minor_unit
    published: dict[tuple[str, str], int] = {}
    for ob in st.obligations:
        if all(seg.event_key is None for seg in ob.segments):
            continue
        evaluator = components.Evaluator(ctx, st, ob)
        for point in decompose.boundary_points(st, ob, segments=evaluator.segment_value):
            if point.catch_up_node is None:
                continue
            key = (point.event.event_key, ob.subject_key)
            value = point.delta if values is None or key not in values else values[key]
            detail = {"member": "catch_up", "value": format_money(value, mu)}
            tb.node(
                measure=f"catch_up@{point.event.event_key}",
                subject_key=ob.subject_key,
                period_key=None,
                value=value,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id="rec.catch_up.sum.v1",
                inputs=[SourceRef("contract_event", point.event.event_key, detail)],
                narrative_key="rec.catch_up.sum",
            )
            published[key] = value
    return published


def allocated_state(
    obligations: Sequence[ObligationState],
    *,
    contracts: Sequence[ContractView] | None = None,
    events: Sequence[EventView] = (),
    inception: date = INCEPTION,
    statuses: Sequence[tuple[date, str]] | None = None,
    judgements: Sequence[JudgementInput] = (),
    estimates: EstimatePins | None = None,
) -> AllocatedState:
    """The state stage 09 consumes; one contract per distinct obligation contract key by default."""
    if contracts is None:
        keys = sorted({ob.contract_key for ob in obligations})
        history = ((inception, "ACTIVE"),) if statuses is None else tuple(statuses)
        contracts = [contract_view(key, statuses=history, judgements=judgements) for key in keys]
    ordered = tuple(sorted(events, key=lambda ev: ev.order_key))
    return AllocatedState(
        group_code="CG-1",
        inception_date=inception,
        contracts=tuple(contracts),
        obligations=tuple(sorted(obligations, key=lambda ob: ob.subject_key)),
        events=ordered,
        measure_events=tuple(ev for ev in ordered if ev.event_type not in BOUNDARY_EVENT_TYPES),
        ledger=QuantityLedger({}),
        return_paths={},
        estimates=EstimatePins({}) if estimates is None else estimates,
        tp_unconstrained={},
        specialist_targets=SpecialistTargets((), (), (), (), ()),
        proposals=(),
        time_triggers=(),
        tp_history=(),
        targeted_vc_quotas={},
        targeted_vc_quota_history={},
        refund_components={},
        findings=(),
    )


def targets_by_period(state: RecognitionState, subject_key: str) -> dict[str, int]:
    """``revenue_cum`` minor units by period key for one obligation."""
    return {
        target.period_key: target.value
        for target in state.revenue_targets
        if target.subject_key == subject_key and target.measure == "revenue_cum"
    }


def period_amounts(targets: Mapping[str, int]) -> dict[str, int]:
    """Period amounts C_t − C_(t−1) in period-key order, with C_0 = 0 (ALG-01 §2.1.3)."""
    amounts: dict[str, int] = {}
    previous = 0
    for period_key in sorted(targets):
        amounts[period_key] = targets[period_key] - previous
        previous = targets[period_key]
    return amounts
