"""Stage 10 net position, obligation positions and concession refund liabilities (ENC-12).

ENGINE_SPEC_B §10.2.3 to §10.2.5 (S10-R-09 to S10-R-15), §10.3 S10-INV-05 and S10-INV-08, §10.7
EX-10-A and EX-10-C; POLICIES ALG-02 (CHK-012 NP part), JET-05c and JET-11 (CHK-137); legacy 02
§7.3 TC-delivery-01 and 08; legacy 05 §7.3 TC-pob-vc-16 (CHK-113; REQ-TP-018). Stages 09 and 10 run
over an ``AllocatedState`` built against the documented contract. The stage 06 concession segments
and refund quotas and the stage 04 financing targets are faked (support.recognition; D-81
integration after merge).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.money import format_exact, largest_remainder
from erev_engine.stages import s09_recognition, s10_billing_balances, s11_costs_loss, s13_books
from erev_engine.stages.s10_billing_balances import BalanceState, refund_liability
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EventView,
    ObligationState,
    PolicyResolver,
    ProgressBase,
    Quota,
    SegmentCause,
    SpecialistTargets,
    Target,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder, TraceNode, reevaluate
from support.bundles import INCEPTION, entity, policy_set
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    concession_history,
    contract_view,
    emit_catch_up_nodes,
    event_view,
    obligation,
    segment,
    usd,
)

CTX = book_context(entity(months=3))
JAN_31, FEB_28 = date(2026, 1, 31), date(2026, 2, 28)
O1, O2, O3 = (f"{CONTRACT_KEY}/P{index}" for index in (1, 2, 3))
GROUP_AT_ENTITY = "CG-1@US01"
CREDIT_OR_REFUND = {"price_change_settlement": "CREDIT_OR_REFUND"}


def _run(
    ctx: BookContext, st: AllocatedState, *, tb: TraceBuilder | None = None
) -> tuple[BalanceState, Trace]:
    """Stages 09 and 10 over one book; the trace re-evaluates node for node (DG-ENG-04)."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION) if tb is None else tb
    emit_catch_up_nodes(tb, ctx, st)
    recognition = s09_recognition.run(ctx, st, tb)
    state = s10_billing_balances.run(ctx, recognition, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    for parts in state.position_components.values():  # S10-INV-05
        inflows = parts.billed_unconditional + parts.deposit_transferred
        inflows += parts.noncash_unconditional + parts.interest_expense
        outflows = parts.interest_income + parts.revenue_relief + parts.receivable_contra
        assert parts.net_position == inflows - outflows - parts.refund_liability
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _target(targets: Sequence[Target], measure: str, subject_key: str, period_key: str) -> Target:
    return next(
        target
        for target in targets
        if (target.measure, target.subject_key, target.period_key)
        == (measure, subject_key, period_key)
    )


def _net_position(state: BalanceState, period_key: str, subject_key: str = GROUP_AT_ENTITY) -> int:
    return _target(state.positions, "net_position", subject_key, period_key).value


def _billed(state: BalanceState, subject_key: str, period_key: str) -> int:
    return _target(state.billing, "billed_cum", subject_key, period_key).value


def _revenue(state: BalanceState, subject_key: str, period_key: str) -> int:
    return _target(state.recognition.revenue_targets, "revenue_cum", subject_key, period_key).value


def _refund_liability(state: BalanceState, period_key: str) -> int:
    return sum(
        target.value for target in state.refund_liabilities if target.period_key == period_key
    )


def _six(value: Fraction) -> Decimal:
    """An exact value at the six places of the legacy figures (legacy 02 §3.13)."""
    return Decimal(format_exact(value, 6))


def _invoice(
    version: int,
    when: date,
    number: str,
    amount: str,
    key: str,
    *,
    contract_key: str = CONTRACT_KEY,
) -> EventView:
    payload = {
        "invoice_number": number,
        "line_external_id": key,
        "obligation_key": key,
        "amount": Decimal(amount),
        "issue_date": when,
    }
    return event_view(
        contract_key, version, "BILLING_RECORDED", when, payload, obligation_keys=[key]
    )


def _credit_memo(
    version: int,
    when: date,
    number: str,
    amount: str,
    key: str,
    *,
    contract_key: str = CONTRACT_KEY,
) -> EventView:
    payload = {
        "credit_memo_number": number,
        "obligation_key": key,
        "amount": Decimal(amount),
        "issue_date": when,
    }
    return event_view(
        contract_key, version, "CREDIT_MEMO_RECORDED", when, payload, obligation_keys=[key]
    )


def _delivery(
    version: int, when: date, key: str, quantity: str = "1", *, contract_key: str = CONTRACT_KEY
) -> EventView:
    payload = {"obligation_key": key, "quantity": Decimal(quantity), "trigger": "DELIVERY"}
    return event_view(
        contract_key, version, "DELIVERY_RECORDED", when, payload, obligation_keys=[key]
    )


def _service(
    key: str, amount: str, start: date, end: date, *, contract_key: str = CONTRACT_KEY
) -> ObligationState:
    services = segment(Fraction(Decimal(amount)), usd(amount), start=start, end=end)
    return obligation(key, [services], contract_key=contract_key, convention="DAILY")


def _goods(
    key: str,
    amount: str,
    *,
    contract_key: str = CONTRACT_KEY,
    concession: tuple[date, str, str] | None = None,
) -> ObligationState:
    """A point-in-time obligation; ``concession`` = (date, event key, reduced allocation) adds the
    stage 06 ``MODIFICATION`` segment of a price change on satisfied performance (S06-R-09)."""
    goods = segment(
        Fraction(Decimal(amount)),
        usd(amount),
        start=INCEPTION,
        end=INCEPTION,
        measure="POINT_IN_TIME",
    )
    segments = [goods]
    if concession is not None:
        when, event_key, reduced = concession
        segments.append(
            segment(
                Fraction(Decimal(reduced)),
                usd(reduced),
                start=INCEPTION,
                end=INCEPTION,
                effective=when,
                cause=SegmentCause.MODIFICATION,
                event_key=event_key,
                measure="POINT_IN_TIME",
            )
        )
    return obligation(
        key, segments, contract_key=contract_key, method="POINT_IN_TIME", convention=None
    )


def test_ex_10_a_position_concession_and_credit_memo() -> None:
    feb_15, mar_10 = date(2026, 2, 15), date(2026, 3, 10)
    amended = event_view(
        CONTRACT_KEY,
        10,
        "CONTRACT_AMENDED",
        feb_15,
        {"modification_id": "MOD-1", **CREDIT_OR_REFUND},
        obligation_keys=["P3"],
    )
    obligations = [
        _service("P1", "3000", INCEPTION, JAN_31),  # time and materials
        _service("P2", "10000", INCEPTION, JAN_31),  # cost-to-cost project
        _goods("P3", "1000", concession=(feb_15, amended.event_key, "500")),  # hardware
    ]
    memo = _credit_memo(11, mar_10, "CM-P3", "500.00", "P3")
    events = [
        _delivery(2, date(2026, 1, 20), "P3"),
        _invoice(3, JAN_31, "INV-P2", "4000.00", "P2"),
        _invoice(4, JAN_31, "INV-P3", "5000.00", "P3"),
        amended,
        memo,
    ]
    st = dataclasses.replace(
        allocated_state(obligations, events=events),
        refund_components={O3: Quota(Fraction(500), usd("500.00"))},
        concession_history=concession_history(O3, amended, Quota(Fraction(500), usd("500.00"))),
    )
    state, trace = _run(CTX, st)

    # 31 Jan: revenue and billing to date.
    assert [
        (_revenue(state, key, "FY2026-P01"), _billed(state, key, "FY2026-P01"))
        for key in (O1, O2, O3)
    ] == [
        (usd("3000.00"), 0),
        (usd("10000.00"), usd("4000.00")),
        (usd("1000.00"), usd("5000.00")),
    ]
    assert (_net_position(state, "FY2026-P01"), _refund_liability(state, "FY2026-P01")) == (
        usd("-5000.00"),
        0,
    )

    # 15 Feb: the concession of 500.00 on P3 (JET-05c Dr REVENUE / Cr REFUND_LIABILITY).
    (component,) = state.refund_components
    assert (component.kind, component.subject_key, component.created_on) == (
        "CONCESSION",
        O3,
        feb_15,
    )
    assert _revenue(state, O3, "FY2026-P02") == usd("500.00")
    february = state.position_components[("US01", "FY2026-P02")]
    assert (february.revenue_relief, february.refund_liability) == (usd("14000.00"), 0)
    assert (_net_position(state, "FY2026-P02"), _refund_liability(state, "FY2026-P02")) == (
        usd("-5000.00"),
        usd("500.00"),
    )

    # 10 Mar: the credit memo consumes the CONCESSION component (JET-04b Dr RL / Cr CL).
    assert _billed(state, O3, "FY2026-P03") == usd("4500.00")
    consumed = _node(trace, f"refund_liability_consumed@{memo.event_key}:{component.key}:-")
    assert (consumed.formula_id, consumed.value) == ("rl.consumption.v1", "500.00")
    march = state.position_components[("US01", "FY2026-P03")]
    revenue = sum(_revenue(state, key, "FY2026-P03") for key in (O1, O2, O3))
    assert (march.billed_unconditional, revenue, _refund_liability(state, "FY2026-P03")) == (
        usd("8500.00"),
        usd("13500.00"),
        0,
    )
    # S10-INV-05: billed 8,500.00 − revenue 13,500.00 − refund liability 0.00.
    assert _net_position(state, "FY2026-P03") == usd("8500.00") - usd("13500.00") == usd("-5000.00")
    node = _node(trace, f"net_position:{GROUP_AT_ENTITY}:FY2026-P03")
    assert node.formula_id == "pos.net_position.v1"
    assert node.params["signs"].split("|")[node.inputs.index(consumed.id)] == "+"


def test_l6_5_concession_created_binds_jet_05c() -> None:
    """JET-05c reads ``concession_created_cum`` per obligation and period end (ENGINE_SPEC_B Table
    14-A; L4-3-Q-42, L5-5-Q-6). Stage 10 publishes the created amount of each ``CONCESSION``
    component from its creation on, unchanged by the credit memo that consumes it (JET-04b carries
    the consumption), and stage 13 binds the targets as ``PartInputs.concessions``. Before the fix
    no target existed, so a CREDIT_OR_REFUND concession posted no JET-05c line."""
    feb_15, mar_10 = date(2026, 2, 15), date(2026, 3, 10)
    amended = event_view(
        CONTRACT_KEY,
        10,
        "CONTRACT_AMENDED",
        feb_15,
        {"modification_id": "MOD-1", **CREDIT_OR_REFUND},
        obligation_keys=["P3"],
    )
    obligations = [
        _service("P1", "3000", INCEPTION, JAN_31),
        _service("P2", "10000", INCEPTION, JAN_31),
        _goods("P3", "1000", concession=(feb_15, amended.event_key, "500")),
    ]
    events = [
        _delivery(2, date(2026, 1, 20), "P3"),
        _invoice(3, JAN_31, "INV-P2", "4000.00", "P2"),
        _invoice(4, JAN_31, "INV-P3", "5000.00", "P3"),
        amended,
        _credit_memo(11, mar_10, "CM-P3", "500.00", "P3"),
    ]
    st = dataclasses.replace(
        allocated_state(obligations, events=events),
        refund_components={O3: Quota(Fraction(500), usd("500.00"))},
        concession_history=concession_history(O3, amended, Quota(Fraction(500), usd("500.00"))),
    )
    state, trace = _run(CTX, st)

    assert [(t.measure, t.subject_key, t.period_key, t.value) for t in state.concessions] == [
        ("concession_created_cum", O3, "FY2026-P02", usd("500.00")),
        ("concession_created_cum", O3, "FY2026-P03", usd("500.00")),
    ]
    node = _node(trace, f"concession_created_cum:{O3}:FY2026-P03")
    assert (node.formula_id, node.value, node.params["mode"]) == (
        "rl.concession.v1",
        "500.00",
        "open",
    )
    assert _refund_liability(state, "FY2026-P03") == 0  # consumed by the credit memo

    costs = s11_costs_loss.run(CTX, state, TraceBuilder(engine_version=ENGINE_VERSION))
    assert s13_books.costs_view(CTX, costs).part_inputs.concessions == state.concessions


def test_l8_e_concession_cause_relief_and_monetary_flows() -> None:
    """D-88 L7-5-Q-4 (L7-6 part), the EX-10-A concession world: 500.00 created on P3 on 15 Feb
    and consumed by the 10 March credit memo.

    - (2) each ``concession_created_cum`` target names its component key as ``cause``;
    - (1) stage 13 relief = stage 09 ``revenue_cum`` + Σ CONCESSION created (Refunds.
      concession_total): P3 relieves 1,000.00 in every period, revenue 500.00 after the concession;
    - (3) the component binds its creation (INCREASE 500.00 at the February end, no control side)
      and its consumption (DECREASE 500.00 at the March end, control CREDIT), not the balance
      movements. Before the fix relief was 500.00 in February and the flows were the balance
      movements with control DEBIT."""
    feb_15, mar_10, mar_31 = date(2026, 2, 15), date(2026, 3, 10), date(2026, 3, 31)
    amended = event_view(
        CONTRACT_KEY,
        10,
        "CONTRACT_AMENDED",
        feb_15,
        {"modification_id": "MOD-1", **CREDIT_OR_REFUND},
        obligation_keys=["P3"],
    )
    obligations = [
        _service("P1", "3000", INCEPTION, JAN_31),
        _service("P2", "10000", INCEPTION, JAN_31),
        _goods("P3", "1000", concession=(feb_15, amended.event_key, "500")),
    ]
    events = [
        _delivery(2, date(2026, 1, 20), "P3"),
        _invoice(3, JAN_31, "INV-P2", "4000.00", "P2"),
        _invoice(4, JAN_31, "INV-P3", "5000.00", "P3"),
        amended,
        _credit_memo(11, mar_10, "CM-P3", "500.00", "P3"),
    ]
    st = dataclasses.replace(
        allocated_state(obligations, events=events),
        refund_components={O3: Quota(Fraction(500), usd("500.00"))},
        concession_history=concession_history(O3, amended, Quota(Fraction(500), usd("500.00"))),
    )
    state, _ = _run(CTX, st)
    (component,) = state.refund_components
    assert [(t.subject_key, t.period_key, t.cause) for t in state.concessions] == [
        (O3, "FY2026-P02", component.key),
        (O3, "FY2026-P03", component.key),
    ]
    assert _revenue(state, O3, "FY2026-P02") == usd("500.00")

    costs = s11_costs_loss.run(CTX, state, TraceBuilder(engine_version=ENGINE_VERSION))
    view = s13_books.costs_view(CTX, costs)
    relief = [(t.period_key, t.value) for t in view.part_inputs.relief if t.subject_key == O3]
    assert relief == [
        ("FY2026-P01", usd("1000.00")),
        ("FY2026-P02", usd("1000.00")),
        ("FY2026-P03", usd("1000.00")),
    ]
    flows = [
        (flow.direction, flow.effective_date, flow.amount, flow.control, flow.source_key)
        for flow in view.fx_flows.monetary
        if flow.component_key == component.key
    ]
    assert flows == [
        ("INCREASE", FEB_28, usd("500.00"), None, f"{component.key}@FY2026-P02"),
        ("DECREASE", mar_31, usd("500.00"), "CREDIT", f"{component.key}@FY2026-P03#consumed"),
    ]


def test_l8_e_concession_event_accepts_a_tp_change_boundary() -> None:
    """D-88 L7-5-Q-4 (iii): the stage 08 producer keys a concession quota on the ESTIMATE_CHANGED
    boundary of a ``TP_CHANGE`` segment; ``_concession_event`` accepts that boundary when the
    obligation has no ``MODIFICATION`` boundary. Before the fix it raised S10-R-13."""
    feb_15 = date(2026, 2, 15)
    changed = event_view(
        CONTRACT_KEY,
        10,
        "ESTIMATE_CHANGED",
        feb_15,
        {"estimate_key": "VC-1"},
        obligation_keys=["P3"],
    )
    goods = _goods("P3", "1000")
    reduced = segment(
        Fraction(500),
        usd("500"),
        start=INCEPTION,
        end=INCEPTION,
        effective=feb_15,
        cause=SegmentCause.TP_CHANGE,
        event_key=changed.event_key,
        measure="POINT_IN_TIME",
    )
    ob = dataclasses.replace(goods, segments=(*goods.segments, reduced))
    st = allocated_state([ob], events=[_delivery(2, date(2026, 1, 20), "P3"), changed])
    assert refund_liability._concession_event(st, ob) == changed
    # A MODIFICATION boundary still wins over a TP_CHANGE boundary (L2-4-Q-14 unchanged).
    amended = event_view(
        CONTRACT_KEY, 11, "CONTRACT_AMENDED", date(2026, 3, 1), {}, obligation_keys=["P3"]
    )
    modified = dataclasses.replace(
        reduced, effective_date=date(2026, 3, 1), cause=SegmentCause.MODIFICATION
    )
    modified = dataclasses.replace(modified, event_key=amended.event_key)
    both = dataclasses.replace(ob, segments=(*goods.segments, modified, reduced))
    st = allocated_state([both], events=[changed, amended])
    assert refund_liability._concession_event(st, both) == amended


def test_s10_r11_unit_per_group_entity_book() -> None:
    licence = _goods("LICENCE", "60000", contract_key="X")
    services = _service("SERVICES", "20000", INCEPTION, JAN_31, contract_key="X")
    x_events = [
        _delivery(2, date(2026, 1, 10), "LICENCE", contract_key="X"),
        _invoice(3, JAN_31, "INV-X-1", "10000.00", "LICENCE", contract_key="X"),
        _invoice(4, JAN_31, "INV-X-2", "40000.00", "SERVICES", contract_key="X"),
    ]
    x = dataclasses.replace(
        allocated_state([licence, services], events=x_events), group_code="CG-X"
    )
    y_services = _service("SERVICES", "5000", date(2026, 2, 1), FEB_28, contract_key="Y")
    y_events = [_invoice(2, JAN_31, "INV-Y-1", "5000.00", "SERVICES", contract_key="Y")]
    y = dataclasses.replace(allocated_state([y_services], events=y_events), group_code="CG-Y")
    x_state, _ = _run(CTX, x)
    y_state, _ = _run(CTX, y)
    # CHK-012 NP part: X nets its two obligations; Y is not combined, so it is not netted with X.
    assert _net_position(x_state, "FY2026-P01", "CG-X@US01") == usd("-30000.00")
    assert _net_position(y_state, "FY2026-P01", "CG-Y@US01") == usd("5000.00")
    assert {target.subject_key for target in x_state.positions} == {"CG-X@US01"}
    assert {target.subject_key for target in y_state.positions} == {"CG-Y@US01"}


def test_l9_run_q3_position_subjects_are_cv_21_encoded() -> None:
    """D-90d L9-RUN-Q-3: the ``<group>@<entity>`` position and current-split subjects and the
    ``<contract>@<entity>`` billing and member-balance subjects percent-encode a delimiter in the
    group code, the contract id or the entity code (CV-21), as the runner and the platform mapper
    expect. Without a delimiter the subjects are unchanged
    (``test_s10_r11_unit_per_group_entity_book``)."""
    ctx = book_context(entity("US@01", months=3))
    licence = dataclasses.replace(
        _goods("LICENCE", "60000", contract_key="X/1"),
        subject_key="X%2F1/LICENCE",
        contracting_entity="US@01",
        performing_entity="US@01",
    )
    events = [
        dataclasses.replace(
            _delivery(2, date(2026, 1, 10), "LICENCE", contract_key="X/1"),
            event_key="X%2F1/EV-000002",
            obligation_subject_keys=("X%2F1/LICENCE",),
        ),
        dataclasses.replace(
            _invoice(3, JAN_31, "INV-X-1", "10000.00", "LICENCE", contract_key="X/1"),
            event_key="X%2F1/EV-000003",
            obligation_subject_keys=("X%2F1/LICENCE",),
        ),
    ]
    view = contract_view("X/1")
    view = dataclasses.replace(
        view, header=dataclasses.replace(view.header, contracting_entity_code="US@01")
    )
    st = dataclasses.replace(
        allocated_state([licence], contracts=[view], events=events), group_code="CG-X/1"
    )
    state, _ = _run(ctx, st)
    assert {target.subject_key for target in state.positions} == {"CG-X%2F1@US%4001"}
    assert {target.subject_key for target in state.current_split} == {"CG-X%2F1@US%4001"}
    assert {target.subject_key for target in state.member_balances} == {"X%2F1@US%4001"}
    assert {
        target.subject_key
        for target in state.billing
        if target.measure == "billed_unconditional_cum"
    } == {"X%2F1@US%4001"}
    assert {subject for subject, _ in state.paid_cum} == {"X%2F1@US%4001"}
    assert _net_position(state, "FY2026-P01", "CG-X%2F1@US%4001") == usd("-50000.00")


def test_chk_137_np_includes_accretion() -> None:
    # EX-10-C: P1 transfers on 1 January 2026; JET-11a accretes 8,483.47 in month 1 (EX-04-B2).
    ob = _goods("P1", "848346.53")
    events = [_delivery(2, INCEPTION, "P1"), _invoice(3, JAN_31, "INV-1", "18871.00", "P1")]
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    detail = {"member": "financing_interest", "value": "8483.47"}
    interest_node = tb.node(  # the stage 04 node stage 10 cites (S04-R-13; D-81)
        measure="financing_interest_cum",
        subject_key=f"{CONTRACT_KEY}@US01",
        period_key="FY2026-P01",
        value=usd("8483.47"),
        currency="USD",
        minor_unit=2,
        formula_id="rec.catch_up.sum.v1",
        inputs=[SourceRef("contract_event", f"{CONTRACT_KEY}/EV-000001", detail)],
        params={"as_of": JAN_31.isoformat()},
        narrative_key="rec.catch_up.sum",
    )
    interest = Target(
        CTX.book_code,
        "US01",
        f"{CONTRACT_KEY}@US01",
        "financing_interest_cum",
        "FY2026-P01",
        "JET-11a",
        usd("8483.47"),
        None,
        interest_node,
    )
    st = dataclasses.replace(
        allocated_state([ob], events=events),
        specialist_targets=SpecialistTargets((), (interest,), (), (), ()),
    )
    state, trace = _run(CTX, st, tb=tb)
    january = state.position_components[("US01", "FY2026-P01")]
    assert (january.billed_unconditional, january.interest_income, january.revenue_relief) == (
        usd("18871.00"),
        usd("8483.47"),
        usd("848346.53"),
    )
    # NP = 18,871.00 − 8,483.47 − 848,346.53 (CHK-137; D-76).
    assert _net_position(state, "FY2026-P01") == usd("-837959.00")
    node = _node(trace, f"net_position:{GROUP_AT_ENTITY}:FY2026-P01")
    assert node.params["signs"].split("|")[node.inputs.index(interest_node)] == "-"


# Golden Contracts 1 to 4 (legacy 02 §5.3, §5.7; legacy 07 §4.4): (price, ((POB, quantity, SSP))).
PARITY = book_context(entity(start=date(2023, 1, 1), months=12), preset="LEGACY_PARITY")
STEP_04, STEP_05, STEP_06, STEP_07 = (
    date(2023, 1, 31),
    date(2023, 2, 28),
    date(2023, 3, 31),
    date(2023, 4, 30),
)
STEP_14, TERM_END = date(2023, 10, 31), date(2023, 12, 31)
SETUP = {
    "Contract 1": date(2023, 1, 1),
    "Contract 2": date(2023, 1, 1),
    "Contract 3": date(2023, 2, 1),
    "Contract 4": date(2023, 2, 1),
}
CONTRACTS: Mapping[str, tuple[int, tuple[tuple[str, str, int], ...]]] = {
    "Contract 1": (
        1300,
        (
            ("POB #1", "5", 500),
            ("POB #2", "2", 368),
            ("POB #3", "1", 150),
            ("POB #4", "1000", 1000),
        ),
    ),
    "Contract 2": (
        900,
        (("POB #1", "8", 612), ("POB #2", "3", 408), ("POB #3", "1", 150), ("VC #1", "1", 0)),
    ),
    "Contract 3": (
        1300,
        (
            ("POB #1", "5", 500),
            ("POB #2", "2", 368),
            ("POB #3", "1", 150),
            ("POB #4", "1000", 1000),
        ),
    ),
    "Contract 4": (
        950,
        (("POB #1", "8", 612), ("POB #2", "4", 544), ("POB #3", "1", 150), ("VC #1", "1", 0)),
    ),
}
Row = tuple[date, str, str, str]  # (upload date, POB, Current Delivery, Current Billing)
UPLOADS: Mapping[str, tuple[Row, ...]] = {  # golden steps 04 to 07 (docs/legacy/golden/0N-*)
    "Contract 1": (
        (STEP_04, "POB #1", "2", "100"),
        (STEP_04, "POB #2", "1", "100"),
        (STEP_04, "POB #3", "0.5", "100"),
        (STEP_05, "POB #1", "1", "100"),
        (STEP_07, "POB #1", "-3", "-200"),
        (STEP_07, "POB #2", "0", "300"),
    ),
    "Contract 2": (
        (STEP_04, "POB #1", "1", "0"),
        (STEP_06, "POB #3", "0.4", "0"),
        (STEP_07, "POB #1", "0", "20"),
    ),
    "Contract 3": ((STEP_05, "POB #3", "0.5", "200"), (STEP_06, "POB #2", "1", "200")),
    "Contract 4": (
        (STEP_05, "POB #1", "2", "150"),
        (STEP_06, "POB #2", "1", "200"),
        (STEP_06, "VC #1", "0.5", "-100"),
    ),
}
# State after golden step 13, latest row per POB: (POB, RQ_k, N_k, R_k, remaining allocation,
# step 14 delivery), as in s09_recognition/test_tc_delivery.py (ENC-4).
STEP_13: Mapping[str, tuple[date, tuple[tuple[str, str, str, str, str, str], ...]]] = {
    "Contract 1": (
        date(2023, 6, 15),
        (
            ("POB #1", "0", "0", "0", "0", "0"),
            ("POB #2", "1", "1", "118.53320118929634", "92.5336782303195", "1"),
            ("POB #3", "0.5", "0.5", "43.01634770780214", "43.01634770780214", "0.5"),
            ("POB #4", "1000", "0", "0", "502.90042516477985", "1000"),
        ),
    ),
    "Contract 2": (
        date(2023, 5, 31),
        (
            ("POB #1", "9", "1", "53.54090354090354", "519.6617108381814", "9"),
            ("POB #2", "3", "0", "0", "385.1851851851852", "3"),
            ("POB #3", "0.6", "0.4", "56.64488017429194", "84.96732026143789", "0.6"),
            ("VC #1", "1", "0", "0", "0", "1"),
        ),
    ),
    "Contract 3": (
        date(2023, 9, 15),
        (
            ("POB #1", "3", "0", "0", "678.0182497533068", "3"),
            ("POB #2", "1", "1", "153.41323606044816", "311.1106183406695", "1"),
            ("POB #3", "0.5", "0.5", "94.67198119587995", "94.67198119587994", "0.5"),
            ("POB #4", "0", "0", "0", "0", "0"),
            ("POB #5", "5", "0", "0", "1268.113933453816", "5"),
        ),
    ),
    "Contract 4": (
        date(2023, 8, 15),
        (
            ("POB #1", "6", "2", "119.92161985630305", "359.76485956890923", "6"),
            ("POB #2", "3", "1", "106.59699542782496", "319.7909862834749", "3"),
            ("POB #3", "2.5", "0", "0", "293.92553886348793", "2.5"),
            ("VC #1", "0.5", "0.5", "0", "0", "0.5"),
        ),
    ),
}
FINAL_PRICE = {"Contract 1": 800, "Contract 2": 1100, "Contract 3": 2600, "Contract 4": 1200}
# Golden step 14 latest_contracts.csv "Current Billing - Cumulative" per POB.
FINAL_BILLING: Mapping[str, Mapping[str, str]] = {
    "Contract 1": {"POB #1": "0", "POB #2": "400", "POB #3": "400", "POB #4": "0"},
    "Contract 2": {"POB #1": "800", "POB #2": "400", "POB #3": "0", "VC #1": "-100"},
    "Contract 3": {
        "POB #1": "800",
        "POB #2": "400",
        "POB #3": "400",
        "POB #4": "0",
        "POB #5": "1000",
    },
    "Contract 4": {"POB #1": "600", "POB #2": "400", "POB #3": "400", "VC #1": "-200"},
}


def _golden_events(contract_key: str, rows: Sequence[Row]) -> list[EventView]:
    """Upload rows as delivery, return, billing and credit-memo events (04 LM-TPL-PROG-01 to 09)."""
    events: list[EventView] = []
    for upload, key, delivery_text, billing_text in rows:
        delivery, billing = Decimal(delivery_text), Decimal(billing_text)
        version = len(events) + 2  # stream version 1 is CONTRACT_BOOKED
        if delivery > 0:
            events.append(_delivery(version, upload, key, delivery_text, contract_key=contract_key))
        elif delivery < 0:
            payload = {"obligation_key": key, "quantity": -delivery}
            events.append(
                event_view(
                    contract_key, version, "RETURN_RECORDED", upload, payload, obligation_keys=[key]
                )
            )
        version = len(events) + 2
        number = upload.isoformat()
        if billing > 0:
            events.append(
                _invoice(
                    version, upload, f"INV-{number}", billing_text, key, contract_key=contract_key
                )
            )
        elif billing < 0:
            events.append(
                _credit_memo(
                    version, upload, f"CM-{number}", str(-billing), key, contract_key=contract_key
                )
            )
    return events


def _inception(contract_key: str) -> list[ObligationState]:
    price, lines = CONTRACTS[contract_key]
    total = sum(ssp for _, _, ssp in lines)
    posted = largest_remainder(
        price * 100, [Fraction(ssp) for _, _, ssp in lines], [key for key, _, _ in lines]
    )
    obligations = []
    for (key, quantity, ssp), a_posted in zip(lines, posted, strict=True):
        seg = segment(
            Fraction(price * ssp, total),
            a_posted,
            start=SETUP[contract_key],
            end=TERM_END,
            quantity=Fraction(quantity),
            measure="UNITS_DELIVERED",
        )
        obligations.append(_units(contract_key, key, [seg]))
    return obligations


def _units(contract_key: str, key: str, segments: Sequence[AllocationSegment]) -> ObligationState:
    return obligation(
        key,
        segments,
        contract_key=contract_key,
        method="UNITS_DELIVERED",
        convention=None,
        start=SETUP.get(contract_key),
        quantity=segments[-1].totals.quantity,
    )


def _after_modifications(contract_key: str) -> list[ObligationState]:
    """Step 13 segments: each POB's last boundary is ``PROSPECTIVE`` over the remaining totals."""
    boundary, rows = STEP_13[contract_key]
    exact = [
        Fraction(Decimal(revenue)) + Fraction(Decimal(rest)) for _, _, _, revenue, rest, _ in rows
    ]
    posted = largest_remainder(FINAL_PRICE[contract_key] * 100, exact, [row[0] for row in rows])
    inception = {ob.obligation_key: ob for ob in _inception(contract_key)}
    obligations = []
    for (key, remaining, delivered, revenue, _, _), x_exact, a_posted in zip(
        rows, exact, posted, strict=True
    ):
        base = Fraction(Decimal(revenue))
        prospective = segment(
            x_exact,
            a_posted,
            start=boundary,
            end=TERM_END,
            basis="PROSPECTIVE",
            cause=SegmentCause.MODIFICATION,
            event_key=f"{contract_key}/EV-000099",
            base_revenue_posted=usd(format_exact(base, 2)),
            base_revenue_exact=base,
            quantity=Fraction(Decimal(remaining)),
            base_delivered=Fraction(Decimal(delivered)),
            measure="UNITS_DELIVERED",
        )
        before = inception.get(key)  # Contract 3 POB #5 is created by the 09.15 modification
        segments = [prospective] if before is None else [*before.segments, prospective]
        obligations.append(_units(contract_key, key, segments))
    return obligations


def _full_uat(contract_key: str) -> list[Row]:
    """Steps 04 to 07 and the step 14 deliveries, with the billing that brings each POB to its
    golden step 14 cumulative billing."""
    billed: dict[str, Decimal] = {}
    for _, key, _, billing in UPLOADS[contract_key]:
        billed[key] = billed.get(key, Decimal(0)) + Decimal(billing)
    step_14: list[Row] = []
    for key, *_, delivery in STEP_13[contract_key][1]:
        difference = Decimal(FINAL_BILLING[contract_key][key]) - billed.get(key, Decimal(0))
        if delivery != "0" or difference != 0:
            step_14.append((STEP_14, key, delivery, str(difference)))
    return [*UPLOADS[contract_key], *step_14]


def _golden(
    contract_key: str,
    rows: Sequence[Row],
    obligations: Sequence[ObligationState],
    *,
    payloads: Mapping[str, Mapping[str, object]] | None = None,
    refund_components: Mapping[str, Quota] | None = None,
) -> tuple[BalanceState, Trace]:
    """Stages 09 and 10 over one golden contract, its own group; boundary events are faked."""
    boundaries = {
        seg.event_key: seg.effective_date
        for ob in obligations
        for seg in ob.segments
        if seg.event_key is not None
    }
    amended = [
        event_view(
            contract_key,
            int(key.rsplit("-", 1)[1]),
            "CONTRACT_AMENDED",
            when,
            {"modification_id": f"MOD-{when.isoformat()}", **(payloads or {}).get(key, {})},
        )
        for key, when in sorted(boundaries.items())
    ]
    st = allocated_state(
        obligations,
        events=[*_golden_events(contract_key, rows), *amended],
        inception=SETUP[contract_key],
        statuses=((SETUP[contract_key], "ACTIVE"),),
    )
    if refund_components is not None:
        st = dataclasses.replace(st, refund_components=refund_components)
    return _run(PARITY, st)


def test_tc_delivery_01_contract1_step04_positions() -> None:
    rows = [row for row in UPLOADS["Contract 1"] if row[0] == STEP_04]
    state, trace = _golden("Contract 1", rows, _inception("Contract 1"))
    measures = state.obligation_measures
    exact = {
        key: _six(measures[f"Contract 1/{key}"].position_obligation_exact)
        for key in ("POB #1", "POB #2", "POB #3", "POB #4")
    }
    assert exact == {
        "POB #1": Decimal("-28.840436"),
        "POB #2": Decimal("-18.533201"),
        "POB #3": Decimal("51.684836"),
        "POB #4": Decimal("0"),
    }
    first = measures["Contract 1/POB #1"]
    assert _six(first.position_contract_entity_exact) == Decimal("4.311199")
    assert (first.position_obligation, first.position_contract_entity) == (
        usd("-28.84"),
        usd("4.31"),
    )
    node = _node(trace, "position_contract_entity:Contract 1@US01:-")
    assert (node.formula_id, node.value, node.params["mode"]) == (
        "pos.obligation.v1",
        "4.31",
        "sum",
    )
    obligation_node = _node(trace, "position_obligation:Contract 1/POB #1:-")
    assert obligation_node.inputs == (
        "billed_cum:Contract 1/POB #1:-",
        "revenue_cum:Contract 1/POB #1:-",
    )


def test_tc_delivery_08_full_uat_positions() -> None:
    for contract_key in STEP_13:
        state, _ = _golden(
            contract_key, _full_uat(contract_key), _after_modifications(contract_key)
        )
        measures = state.obligation_measures
        for key, amount in FINAL_BILLING[contract_key].items():
            assert measures[f"{contract_key}/{key}"].billed_cum == usd(amount)
        # TC-delivery-08 production value: every contract position is exactly 0.00 (GT-16).
        assert {item.position_contract_entity for item in measures.values()} == {0}
        assert _net_position(state, "FY2023-P10") == 0


def test_tc_pob_vc_16_concession_on_billed_amount() -> None:
    contract_key, subject_key = "Contract 2", "Contract 2/POB #2"
    nov_15, event_key = date(2023, 11, 15), "Contract 2/EV-000100"
    obligations = []
    for ob in _after_modifications(contract_key):
        if ob.subject_key == subject_key:
            # Billing after the 05.31 boundary is 400.00 (legacy B 0 before the modification).
            last = dataclasses.replace(ob.segments[-1], remaining_billing_plan=Fraction(400))
            concession = dataclasses.replace(  # S06-R-09: satisfied performance, basis INCEPTION
                last,
                effective_date=nov_15,
                event_key=event_key,
                cause=SegmentCause.MODIFICATION,
                basis="INCEPTION",
                x_exact=last.x_exact - 60,
                a_posted=last.a_posted - usd("60.00"),
                base_revenue_posted=0,
                base_revenue_exact=Fraction(0),
                base_progress=ProgressBase.zero(),
            )
            ob = dataclasses.replace(ob, segments=(*ob.segments[:-1], last, concession))
        obligations.append(ob)
    state, trace = _golden(
        contract_key,
        _full_uat(contract_key),
        obligations,
        payloads={event_key: CREDIT_OR_REFUND},
        refund_components={subject_key: Quota(Fraction(60), usd("60.00"))},
    )
    revenue = _target(state.recognition.revenue_targets, "revenue_cum", subject_key, "FY2023-P11")
    assert revenue.exact is not None and _six(revenue.exact) == Decimal("325.185185")
    assert _node(trace, f"catch_up@{event_key}:{subject_key}:-").value == "-60.00"  # CU −60.00
    (component,) = state.refund_components
    assert (component.kind, component.subject_key, component.created_amount) == (
        "CONCESSION",
        subject_key,
        usd("60.00"),
    )
    assert _refund_liability(state, "FY2023-P11") == usd("60.00")
    # The concession is a refund liability, not negative remaining billing (REQ-TP-018).
    measures = state.obligation_measures[subject_key]
    assert (measures.billed_cum, measures.remaining_billing) == (usd("400.00"), 0)
    november = state.position_components[("US01", "FY2023-P11")]
    assert november.revenue_relief == usd("1100.00")
    assert _net_position(state, "FY2023-P11") == 0


def test_s10_inv_08_performing_entity_holds_no_balance() -> None:
    us01, us02 = entity(months=3), entity("US02", months=3)
    base = book_context(us01)
    resolved = {
        (policy.code, policy.scope, policy.subject_key): policy
        for policy in (*base.policies.all(), *policy_set(entity=us02))
    }
    ctx = dataclasses.replace(
        base,
        entities={"US01": us01, "US02": us02},
        horizon={"US01": "FY2026-P03", "US02": "FY2026-P03"},
        policies=PolicyResolver(tuple(resolved[key] for key in sorted(resolved))),
    )
    performed = dataclasses.replace(
        _service("P1", "3000", INCEPTION, JAN_31), performing_entity="US02"
    )
    st = allocated_state([performed], events=[_invoice(2, JAN_31, "INV-1", "1000.00", "P1")])
    state, _ = _run(ctx, st)
    assert {target.entity for target in state.recognition.revenue_targets} == {"US02"}
    balances = (*state.positions, *state.refund_liabilities, *state.return_assets)
    assert balances and {target.entity for target in balances} == {"US01"}
    assert not any("@US02" in target.subject_key for target in balances)
    assert set(state.position_components) == {
        ("US01", period_key) for period_key in ("FY2026-P01", "FY2026-P02", "FY2026-P03")
    }
    assert _net_position(state, "FY2026-P01") == usd("1000.00") - usd("3000.00")
