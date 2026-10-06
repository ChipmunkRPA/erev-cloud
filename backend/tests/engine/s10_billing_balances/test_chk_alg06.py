"""Stage 10 refund liabilities and return assets (ENC-12).

ENGINE_SPEC_B §10.2.4 and §10.2.5 (S10-R-13 to S10-R-17), §10.3 S10-INV-07; POLICIES ALG-06 steps
3 and 4 (CHK-029, CHK-060), §5.6 PT-06 (CHK-116), POL-127, JET-04b, JET-07c and JET-07d. The
``AllocatedState``, including the stage 04 return paths (ENGINE_SPEC S04-R-08b), the stage 06
concession quota and the termination payload, is built against the documented contract
(support.recognition; D-81 integration after merge).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.errors import EngineError
from erev_engine.stages import s09_recognition, s10_billing_balances
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EventView,
    ObligationState,
    Quota,
    ReturnPath,
    ReturnPin,
    SegmentCause,
    Target,
)
from erev_engine.trace import Trace, TraceBuilder, TraceNode, reevaluate
from support.bundles import INCEPTION, entity
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    concession_history,
    emit_catch_up_nodes,
    event_view,
    obligation,
    segment,
    usd,
)

C_RET = "C-RET"
O_RET = f"{C_RET}/L1-PROD"
RETURN_KEY = f"CG-1@US01/RETURN/{O_RET}"
TRANSFER = date(2026, 1, 10)
RETURNED = date(2026, 2, 10)
WINDOW_END = date(2026, 3, 15)
PERIODS = ("FY2026-P01", "FY2026-P02", "FY2026-P03")
CTX = book_context(entity(months=3))
REDUCE_PRESET = {
    "returns.model": "EXPECTED_RETURNS",
    "returns.returned_units_scope": "REDUCE_CONTRACT_QUANTITY",
    "returns.reversal_rate": "AVERAGE_CARRYING_RATE",
}


def _run(ctx: BookContext, st: AllocatedState) -> tuple[BalanceState, Trace]:
    """Stages 09 and 10 over one book; the trace re-evaluates node for node (DG-ENG-04)."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)
    recognition = s09_recognition.run(ctx, st, tb)
    state = s10_billing_balances.run(ctx, recognition, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _values(targets: Sequence[Target], measure: str, subject_key: str) -> list[int]:
    """The values of one series at P01 to P03; 0 where no target exists yet."""
    by_period = {
        target.period_key: target.value
        for target in targets
        if (target.measure, target.subject_key) == (measure, subject_key)
    }
    return [by_period.get(period_key, 0) for period_key in PERIODS]


def _product() -> ObligationState:
    """RET-CHK-029-S3-EX22: 100 products sold for 10,000.00 (TPL-UNITS, UNITS_DELIVERED)."""
    goods = segment(
        Fraction(10000), usd("10000.00"), start=TRANSFER, end=TRANSFER, quantity=Fraction(100)
    )
    return obligation(
        "L1-PROD",
        [goods],
        contract_key=C_RET,
        method="UNITS_DELIVERED",
        convention=None,
        quantity=Fraction(100),
    )


def _pin(version_no: int, effective: date, expected: int, carrying: int = 60) -> ReturnPin:
    """A RETURN_RATE version: carrying cost 60.00 a unit, no recovery costs, window to 15 March."""
    key = f"{C_RET}/RET-JAN@v{version_no}"
    return ReturnPin(
        effective, key, Fraction(expected), Fraction(carrying), Fraction(0), WINDOW_END
    )


def _ret_event(version: int, event_type: str, when: date, payload: dict[str, object]) -> EventView:
    return event_view(C_RET, version, event_type, when, payload, obligation_keys=["L1-PROD"])


def _chk_029_state(
    pins: Sequence[ReturnPin], revisions: Sequence[tuple[int, date]] = ()
) -> AllocatedState:
    events = [
        _ret_event(3, "ESTIMATE_CHANGED", TRANSFER, {"estimate_version_id": f"{C_RET}/RET-JAN@v1"}),
        _ret_event(
            4,
            "DELIVERY_RECORDED",
            TRANSFER,
            {"obligation_key": "L1-PROD", "quantity": Decimal("100"), "trigger": "DELIVERY"},
        ),
        _ret_event(
            5,
            "BILLING_RECORDED",
            TRANSFER,
            {
                "invoice_number": "INV-RET-1",
                "line_external_id": "INV-RET-1-1",
                "obligation_key": "L1-PROD",
                "amount": Decimal("10000.00"),
                "issue_date": TRANSFER,
            },
        ),
        _ret_event(
            6,
            "RETURN_RECORDED",
            RETURNED,
            {
                "obligation_key": "L1-PROD",
                "quantity": Decimal("2"),
                "refund_amount": Decimal("200"),
            },
        ),
        _ret_event(
            7,
            "CREDIT_MEMO_RECORDED",
            RETURNED,
            {
                "credit_memo_number": "CM-RET-1",
                "credited_invoice_number": "INV-RET-1",
                "obligation_key": "L1-PROD",
                "amount": Decimal("200.00"),
                "issue_date": RETURNED,
            },
        ),
    ]
    for version, (version_no, when) in enumerate(revisions, start=8):
        payload = {"estimate_version_id": f"{C_RET}/RET-JAN@v{version_no}"}
        events.append(_ret_event(version, "ESTIMATE_CHANGED", when, payload))
    st = allocated_state(
        [_product()], events=events, inception=TRANSFER, statuses=((TRANSFER, "ACTIVE"),)
    )
    path = ReturnPath(
        f"{C_RET}/RET-JAN", tuple(pins), ((TRANSFER, Fraction(100)),), Fraction(100), REDUCE_PRESET
    )
    return dataclasses.replace(st, return_paths={O_RET: path})


def test_chk_029_refund_liability_and_return_asset() -> None:
    state, trace = _run(CTX, _chk_029_state([_pin(1, TRANSFER, 3)]))
    # ALG-06 step 3: round(p_ref × E_b) = 300.00, then 100.00 after two returns, 0.00 at expiry.
    assert _values(state.refund_liabilities, "refund_liability", RETURN_KEY) == [
        usd("300.00"),
        usd("100.00"),
        0,
    ]
    balance = _values(state.return_assets, "return_asset", O_RET)
    derecognised = _values(state.return_assets, "return_asset_derecognised_cum", O_RET)
    assert balance == [usd("180.00"), usd("60.00"), 0]
    assert derecognised == [0, usd("120.00"), usd("120.00")]  # JET-07d 120.00 in February
    # JET-07c cumulative = RA + D: 180.00 at transfer, nothing more in February, −60.00 at expiry.
    cumulative = [asset + out for asset, out in zip(balance, derecognised, strict=True)]
    assert [cumulative[0], cumulative[1] - cumulative[0], cumulative[2] - cumulative[1]] == [
        usd("180.00"),
        0,
        usd("-60.00"),
    ]
    node = _node(trace, f"return_asset_derecognised_cum:{O_RET}:FY2026-P02")
    assert (node.formula_id, node.params["quantities"], node.params["unit"]) == (
        "returns.return_asset.v1",
        "2",
        "60",
    )
    # D-91 C606-01 (7): the RETURN component cites stage 09's E_b node (rl.return.v2); E_b is no
    # longer replayed as a stored param.
    liability = _node(trace, f"refund_liability:{RETURN_KEY}:FY2026-P01")
    assert (liability.formula_id, liability.params["p_ref"], "e_b" in liability.params) == (
        "rl.return.v2",
        "100",
        False,
    )
    assert liability.inputs == (f"return_refundable_units:{O_RET}:FY2026-P01",)
    assert _node(trace, f"return_refundable_units:{O_RET}:FY2026-P01").value == "3"
    (component,) = state.refund_components
    assert (component.kind, component.subject_key, component.consumptions) == ("RETURN", O_RET, ())


def test_chk_060_revised_estimate() -> None:
    revised = date(2026, 1, 31)  # E revised to 4 at the first period end, before any return
    st = _chk_029_state([_pin(1, TRANSFER, 3), _pin(2, revised, 4)], revisions=[(2, revised)])
    state, _ = _run(CTX, st)
    assert _values(state.refund_liabilities, "refund_liability", RETURN_KEY) == [
        usd("400.00"),
        usd("200.00"),
        0,
    ]
    assert _values(state.return_assets, "return_asset", O_RET) == [
        usd("240.00"),
        usd("120.00"),
        0,
    ]
    derecognised = _values(state.return_assets, "return_asset_derecognised_cum", O_RET)
    assert derecognised[1] - derecognised[0] == usd("120.00")  # two returns: JET-07d 120.00
    revenue = {
        target.period_key: target.value
        for target in state.recognition.revenue_targets
        if target.subject_key == O_RET
    }
    assert revenue["FY2026-P03"] == usd("9800.00")


PORTFOLIO_KEY = "PORTFOLIO:PF-WIDGET-JAN-2026/RET-RATE"
SOLD, COHORT_RETURN, COHORT_CLOSE = date(2026, 1, 15), date(2026, 2, 10), date(2026, 2, 28)
MEMBERS = tuple(f"C-{index:03d}" for index in range(1, 51))


def _member_event(
    contract_key: str, version: int, event_type: str, when: date, payload: dict[str, object]
) -> EventView:
    return event_view(contract_key, version, event_type, when, payload, obligation_keys=["L1"])


def _portfolio_state() -> AllocatedState:
    """RET-CHK-116: 50 contracts of 10 units at 100.00, portfolio return rate 4% (PT-06)."""
    obligations: list[ObligationState] = []
    events: list[EventView] = []
    paths: dict[str, ReturnPath] = {}
    for index, contract_key in enumerate(MEMBERS, start=1):
        goods = segment(
            Fraction(1000),
            usd("1000.00"),
            start=SOLD,
            end=SOLD,
            quantity=Fraction(10),
            measure="UNITS_DELIVERED",
        )
        ob = obligation(
            "L1",
            [goods],
            contract_key=contract_key,
            method="UNITS_DELIVERED",
            convention=None,
            quantity=Fraction(10),
        )
        obligations.append(ob)
        invoice = f"INV-{contract_key}"
        events += [
            _member_event(
                contract_key,
                2,
                "ESTIMATE_CHANGED",
                SOLD,
                {"estimate_version_id": f"{PORTFOLIO_KEY}@v1"},
            ),
            _member_event(
                contract_key,
                3,
                "DELIVERY_RECORDED",
                SOLD,
                {"obligation_key": "L1", "quantity": Decimal("10"), "trigger": "DELIVERY"},
            ),
            _member_event(
                contract_key,
                4,
                "BILLING_RECORDED",
                SOLD,
                {
                    "invoice_number": invoice,
                    "line_external_id": "1",
                    "obligation_key": "L1",
                    "amount": Decimal("1000.00"),
                    "issue_date": SOLD,
                },
            ),
        ]
        if index <= 25:  # one unit comes back in each of 25 contracts and is refunded
            events += [
                _member_event(
                    contract_key,
                    5,
                    "RETURN_RECORDED",
                    COHORT_RETURN,
                    {
                        "obligation_key": "L1",
                        "quantity": Decimal("1"),
                        "refund_amount": Decimal("100"),
                    },
                ),
                _member_event(
                    contract_key,
                    6,
                    "CREDIT_MEMO_RECORDED",
                    COHORT_RETURN,
                    {
                        "credit_memo_number": f"CM-{contract_key}",
                        "credited_invoice_number": invoice,
                        "obligation_key": "L1",
                        "amount": Decimal("100.00"),
                        "issue_date": COHORT_RETURN,
                    },
                ),
            ]
        # The portfolio rate applied to each member with exact rationals: E = 10 × 4% = 0.4.
        pin = ReturnPin(
            SOLD, f"{PORTFOLIO_KEY}@v1", Fraction(2, 5), Fraction(0), Fraction(0), COHORT_CLOSE
        )
        paths[ob.subject_key] = ReturnPath(
            PORTFOLIO_KEY, (pin,), ((SOLD, Fraction(100)),), Fraction(100), REDUCE_PRESET
        )
    st = allocated_state(obligations, events=events)
    return dataclasses.replace(st, return_paths=paths)


def test_chk_116_portfolio_returns() -> None:
    state, _ = _run(CTX, _portfolio_state())
    keys = [f"{contract_key}/L1" for contract_key in MEMBERS]
    revenue = {
        (target.subject_key, target.period_key): target.value
        for target in state.recognition.revenue_targets
    }
    liability = {
        (target.subject_key, target.period_key): target.value for target in state.refund_liabilities
    }

    def at(values: dict[tuple[str, str], int], period_key: str, prefix: str = "") -> list[int]:
        return [values[(f"{prefix}{key}", period_key)] for key in keys]

    assert {state.recognition.return_states[(key, "FY2026-P01")].E for key in keys} == {
        Fraction(2, 5)
    }
    january_revenue = at(revenue, "FY2026-P01")
    january_liability = at(liability, "FY2026-P01", "CG-1@US01/RETURN/")
    assert (set(january_revenue), set(january_liability)) == ({usd("960.00")}, {usd("40.00")})
    assert (sum(january_revenue), sum(january_liability)) == (usd("48000.00"), usd("2000.00"))
    # Cohort close: actual returns of 25 units (5%) replace the estimate.
    march_revenue = at(revenue, "FY2026-P03")
    assert march_revenue == [usd("900.00")] * 25 + [usd("1000.00")] * 25
    assert sum(march_revenue) == usd("47500.00")
    assert sum(march_revenue) - sum(january_revenue) == usd("-500.00")  # true-up
    assert sum(at(liability, "FY2026-P03", "CG-1@US01/RETURN/")) == 0
    assert [
        next(
            target.value
            for target in state.positions
            if target.period_key == period_key and target.subject_key == "CG-1@US01"
        )
        for period_key in PERIODS
    ] == [0, 0, 0]


def test_s10_r13_refund_liability_excluded_from_position() -> None:
    positions = []
    for carrying in (60, 0):
        state, trace = _run(CTX, _chk_029_state([_pin(1, TRANSFER, 3, carrying=carrying)]))
        positions.append(_values(state.positions, "net_position", "CG-1@US01"))
        january = state.position_components[("US01", "FY2026-P01")]
        # ERP invoice Cr CL 10,000.00; JET-02 Dr CL 9,700.00; JET-04b Dr CL 300.00 / Cr RL.
        assert (january.billed_unconditional, january.revenue_relief, january.refund_liability) == (
            usd("10000.00"),
            usd("9700.00"),
            usd("300.00"),
        )
        node = _node(trace, "net_position:CG-1@US01:FY2026-P01")
        signs = node.params["signs"].split("|")
        assert signs[node.inputs.index(f"refund_liability:{RETURN_KEY}:FY2026-P01")] == "-"
        assert not any(str(ref).startswith("return_asset") for ref in node.inputs)
    # The refund liability enters NP only through JET-04b; the return asset never does.
    assert positions == [[0, 0, 0], [0, 0, 0]]


def test_s10_inv_07_credit_memo_consumption_bounded() -> None:
    concession_on, terminated = date(2026, 1, 20), date(2026, 2, 10)
    amended = event_view(
        CONTRACT_KEY,
        4,
        "CONTRACT_AMENDED",
        concession_on,
        {"modification_id": "MOD-1", "price_change_settlement": "CREDIT_OR_REFUND"},
        obligation_keys=["P1"],
    )
    goods = segment(
        Fraction(1000), usd("1000.00"), start=INCEPTION, end=INCEPTION, measure="POINT_IN_TIME"
    )
    reduced = segment(
        Fraction(800),
        usd("800.00"),
        start=INCEPTION,
        end=INCEPTION,
        effective=concession_on,
        cause=SegmentCause.MODIFICATION,
        event_key=amended.event_key,
        measure="POINT_IN_TIME",
    )
    p1 = obligation("P1", [goods, reduced], method="POINT_IN_TIME", convention=None)
    services = segment(Fraction(2000), usd("2000.00"), start=INCEPTION, end=date(2026, 3, 31))
    p2 = obligation("P2", [services], convention="DAILY")

    def memo(version: int, when: date, amount: str, key: str) -> EventView:
        payload = {
            "credit_memo_number": f"CM-{version}",
            "obligation_key": key,
            "amount": Decimal(amount),
            "issue_date": when,
        }
        return event_view(
            CONTRACT_KEY, version, "CREDIT_MEMO_RECORDED", when, payload, obligation_keys=[key]
        )

    memos = [
        memo(5, date(2026, 1, 25), "100.00", "P1"),
        memo(7, date(2026, 2, 20), "400.00", "P2"),
        memo(8, date(2026, 3, 5), "250.00", "P2"),
    ]
    events = [
        event_view(
            CONTRACT_KEY,
            2,
            "DELIVERY_RECORDED",
            date(2026, 1, 10),
            {"obligation_key": "P1", "quantity": Decimal("1"), "trigger": "DELIVERY"},
            obligation_keys=["P1"],
        ),
        event_view(
            CONTRACT_KEY,
            3,
            "BILLING_RECORDED",
            date(2026, 1, 10),
            {
                "invoice_number": "INV-1",
                "line_external_id": "1",
                "obligation_key": "P2",
                "amount": Decimal("3000.00"),
                "issue_date": date(2026, 1, 10),
            },
            obligation_keys=["P2"],
        ),
        amended,
        memos[0],
        event_view(
            CONTRACT_KEY,
            6,
            "CONTRACT_TERMINATED",
            terminated,
            {
                "modification_id": "MOD-2",
                "termination_kind": "FULL",
                "refund_amount": Decimal("300.00"),
            },
        ),
        memos[1],
        memos[2],
    ]
    st = dataclasses.replace(
        allocated_state([p1, p2], events=events),
        refund_components={f"{CONTRACT_KEY}/P1": Quota(Fraction(200), usd("200.00"))},
        concession_history=concession_history(
            f"{CONTRACT_KEY}/P1", amended, Quota(Fraction(200), usd("200.00"))
        ),
    )
    state, trace = _run(CTX, st)
    by_kind = {component.kind: component for component in state.refund_components}
    termination, concession = by_kind["TERMINATION"], by_kind["CONCESSION"]
    # Memo 1 precedes the termination; memo 2 consumes TERMINATION first, then CONCESSION.
    assert [(item.document_key, item.amount) for item in termination.consumptions] == [
        (memos[1].event_key, usd("300.00"))
    ]
    assert [(item.document_key, item.amount) for item in concession.consumptions] == [
        (memos[0].event_key, usd("100.00")),
        (memos[1].event_key, usd("100.00")),
    ]
    taken: dict[str, int] = {}
    for component in state.refund_components:
        for item in component.consumptions:
            taken[item.document_key] = taken.get(item.document_key, 0) + item.amount
    amounts = {ev.event_key: usd(str(ev.payload["amount"])) for ev in memos}
    assert all(taken[key] <= amounts[key] for key in taken)  # S10-INV-07
    assert memos[2].event_key not in taken  # nothing remains open for the third memo
    assert all(target.value >= 0 for target in state.refund_liabilities)
    assert _values(state.refund_liabilities, "refund_liability", concession.key) == [
        usd("100.00"),
        0,
        0,
    ]
    assert _values(state.refund_liabilities, "refund_liability", termination.key) == [0, 0, 0]
    node = _node(trace, f"refund_liability_consumed@{memos[1].event_key}:{concession.key}:-")
    assert (node.params["open_before"], node.params["taken_before"], node.value) == (
        "10000",
        "30000",
        "100.00",
    )
    # S10-R-15: the contract-level termination refund by posted allocation at 10 February.
    assert dict(termination.attribution) == {
        f"{CONTRACT_KEY}/P1": usd("85.71"),
        f"{CONTRACT_KEY}/P2": usd("214.29"),
    }


def test_l8_e_termination_refund_quota_is_not_a_concession() -> None:
    """D-88 L7-5-Q-2 (i) (MOD-FS-09): stage 06 publishes a termination refund in
    ``refund_components`` under the S06-R-21 key ``<contract subject>#TERMINATION@<event key>``.
    ``_terminations`` creates that component from the event, so ``_concessions`` skips the key;
    any other key that names no obligation still raises S06-R-09."""
    terminated_on = date(2026, 2, 10)
    services = segment(Fraction(2000), usd("2000.00"), start=INCEPTION, end=date(2026, 3, 31))
    p1 = obligation("P1", [services], convention="DAILY")
    terminated = event_view(
        CONTRACT_KEY,
        3,
        "CONTRACT_TERMINATED",
        terminated_on,
        {"modification_id": "MOD-1", "termination_kind": "FULL", "refund_amount": Decimal("300")},
    )
    invoice = event_view(
        CONTRACT_KEY,
        2,
        "BILLING_RECORDED",
        date(2026, 1, 10),
        {
            "invoice_number": "INV-1",
            "line_external_id": "1",
            "obligation_key": "P1",
            "amount": Decimal("2000.00"),
            "issue_date": date(2026, 1, 10),
        },
        obligation_keys=["P1"],
    )
    base = allocated_state([p1], events=[invoice, terminated])
    quota = Quota(Fraction(300), usd("300.00"))
    st = dataclasses.replace(
        base, refund_components={f"{CONTRACT_KEY}#TERMINATION@{terminated.event_key}": quota}
    )
    state, _ = _run(CTX, st)
    assert [
        (item.kind, item.source_key, item.created_amount) for item in state.refund_components
    ] == [("TERMINATION", terminated.event_key, usd("300.00"))]
    (termination,) = state.refund_components
    assert _values(state.refund_liabilities, "refund_liability", termination.key) == [
        0,
        usd("300.00"),
        usd("300.00"),
    ]
    # A key of another form that names no obligation still fails closed.
    for key in (f"{CONTRACT_KEY}/P9", f"{CONTRACT_KEY}#TERMINATION@{CONTRACT_KEY}/EV-000009"):
        with pytest.raises(EngineError) as raised:
            _run(CTX, dataclasses.replace(base, refund_components={key: quota}))
        assert raised.value.detail["rule"] == "S06-R-09"
