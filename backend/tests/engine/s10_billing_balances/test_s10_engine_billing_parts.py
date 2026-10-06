"""JET-03 invoice inputs per obligation under ``billing.posting = ENGINE`` (ENGINE_SPEC_B Table
14-A row "JET-03 invoice (ENGINE)": unconditional billing and tax (10), subject obligation;
S10-R-02, S10-R-06 to S10-R-08; POLICIES JET-03, CHK-023; lane L5-5, L2-5-Q-40, L4-3-Q-19).

Stage 10 published ``billed_unconditional_cum`` per ``<contract>@<entity>`` only, the book loop
bound obligation subjects only and no stage published ``sales_tax_billed_cum``, so ENGINE-mode
billing posted no AR, contract-liability or sales-tax line. Stage 10 now publishes both measures
per obligation for contracts billed under ENGINE mode, and nothing new under ERP mode. No database.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.stages import s09_recognition, s10_billing_balances
from erev_engine.stages.s04_transaction_price.taxes import collected_tax
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.state import AllocatedState, BookContext, EventView, PolicyResolver
from erev_engine.trace import SourceRef, Trace, TraceBuilder, reevaluate
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    emit_catch_up_nodes,
    event_view,
    obligation,
    segment,
    usd,
)

O1 = f"{CONTRACT_KEY}/POB-01"
O2 = f"{CONTRACT_KEY}/POB-02"
CTX = book_context()
YEAR_START, YEAR_END = date(2026, 1, 1), date(2026, 12, 31)


def _engine(ctx: BookContext) -> BookContext:
    policies = []
    for policy in ctx.policies.all():
        if policy.code == "billing.posting":
            policy = dataclasses.replace(policy, value="ENGINE")
        elif policy.code == "balance.position_invoice_basis":
            policy = dataclasses.replace(policy, value="UNCONDITIONAL_INVOICES_ONLY")
        policies.append(policy)
    return dataclasses.replace(ctx, policies=PolicyResolver(tuple(policies)))


def _run(ctx: BookContext, st: AllocatedState) -> tuple[BalanceState, Trace]:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)
    state = s10_billing_balances.run(ctx, s09_recognition.run(ctx, st, tb), tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def _service(key: str, amount: int) -> object:
    services = segment(Fraction(amount), amount * 100, start=YEAR_START, end=YEAR_END)
    return obligation(key, [services], convention="MONTHLY_EVEN")


def _invoice(
    version: int, when: date, number: str, line: str, amount: str, tax: str, key: str | None
) -> EventView:
    payload: dict[str, object] = {
        "invoice_number": number,
        "line_external_id": line,
        "amount": Decimal(amount),
        "issue_date": when,
        "tax_amount": Decimal(tax),
        "is_cancellable": False,
    }
    if key is not None:
        payload["obligation_key"] = key
    keys = [] if key is None else [key]
    return event_view(
        CONTRACT_KEY, version, "BILLING_RECORDED", when, payload, obligation_keys=keys
    )


def _values(state: BalanceState, measure: str, subject_key: str) -> dict[str, int]:
    return {
        target.period_key: target.value
        for target in state.billing
        if (target.measure, target.subject_key) == (measure, subject_key)
    }


def test_jet_03_inputs_per_obligation_under_engine_billing() -> None:
    obligations = [_service("POB-01", 1000), _service("POB-02", 1000)]
    events = [
        # CHK-023: a referenced line of 1,000.00 with tax 80.00.
        _invoice(2, date(2026, 1, 15), "INV-1", "L1", "1000.00", "80.00", "POB-01"),
        # An unreferenced line: its 200.00 and tax 15.01 are apportioned over equal weights.
        _invoice(3, date(2026, 2, 28), "INV-2", "L1", "200.00", "15.01", None),
    ]
    state, trace = _run(_engine(CTX), allocated_state(obligations, events=events))
    billed_1 = _values(state, "billed_unconditional_cum", O1)
    tax_1 = _values(state, "sales_tax_billed_cum", O1)
    tax_2 = _values(state, "sales_tax_billed_cum", O2)
    assert (billed_1["FY2026-P01"], tax_1["FY2026-P01"]) == (usd("1000.00"), usd("80.00"))
    assert tax_2["FY2026-P01"] == 0
    assert _values(state, "billed_unconditional_cum", O2)["FY2026-P02"] == usd("100.00")
    # 15.01 over two equal keys: 7.51 to the first key, 7.50 to the second (largest remainder).
    assert (tax_1["FY2026-P02"], tax_2["FY2026-P02"]) == (usd("87.51"), usd("7.50"))
    node = next(n for n in trace.nodes if n.id == f"sales_tax_billed_cum:{O1}:FY2026-P01")
    assert (node.formula_id, node.value) == ("bil.unconditional_date.v1", "80.00")
    assert node.inputs == (
        SourceRef("contract_event", events[0].event_key, {"member": "tax", "value": "80.00"}),
    )
    # The contract-level measure keeps its subject and figures (S10-R-08).
    contract = _values(state, "billed_unconditional_cum", f"{CONTRACT_KEY}@US01")
    assert contract["FY2026-P02"] == usd("1200.00")


def test_erp_billing_publishes_no_obligation_inputs() -> None:
    events = [_invoice(2, date(2026, 1, 15), "INV-1", "L1", "1000.00", "80.00", "POB-01")]
    state, _ = _run(CTX, allocated_state([_service("POB-01", 1000)], events=events))
    assert _values(state, "billed_unconditional_cum", O1) == {}
    assert _values(state, "sales_tax_billed_cum", O1) == {}


def test_s04_r20_collected_tax_at_the_version_date() -> None:
    first = _invoice(2, date(2026, 1, 31), "INV-1", "L1", "50000.00", "10000.00", "POB-01")
    repeat = _invoice(3, date(2026, 2, 5), "INV-1", "L1", "50000.00", "10000.00", "POB-01")
    later = _invoice(4, date(2026, 2, 28), "INV-2", "L1", "55000.00", "11000.00", "POB-01")
    lines = dataclasses.replace(
        later, payload={**later.payload, "tax_lines": [{"amount": Decimal("5000.00")}]}
    )
    events = [first, repeat, lines]
    assert collected_tax(events, {CONTRACT_KEY}, date(2026, 1, 31)) == Fraction(10000)
    # A status update counts once, and tax_lines govern over tax_amount (S10-R-07; §16.3).
    assert collected_tax(events, {CONTRACT_KEY}, date(2026, 2, 28)) == Fraction(15000)
    assert collected_tax(events, {"K-OTHER"}, date(2026, 2, 28)) == Fraction(0)
