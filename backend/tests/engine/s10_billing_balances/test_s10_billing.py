"""Stage 10 billing ingestion, attribution and unconditional billing (ENC-11).

ENGINE_SPEC_B §10.1, §10.2.1 and §10.2.2 (S10-R-01 to S10-R-08), §10.3 S10-INV-04 and S10-INV-06,
§10.4 and §10.5; POLICIES ALG-02 step 3, POL-004, POL-045, POL-123 and JET-03 (CHK-023, CHK-024);
legacy 02 §7.3 TC-delivery-06. Stage 09 runs first over an ``AllocatedState`` built against the
documented contract (support.recognition; D-81 integration after merge).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.money import largest_remainder
from erev_engine.stages import s09_recognition, s10_billing_balances
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EventView,
    ObligationState,
    PolicyResolver,
    SegmentCause,
    Target,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder, TraceNode, reevaluate
from support.bundles import entity
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
O3 = f"{CONTRACT_KEY}/POB-03"
CONTRACT_AT_ENTITY = f"{CONTRACT_KEY}@US01"
CTX = book_context()
YEAR_START, YEAR_END = date(2026, 1, 1), date(2026, 12, 31)
RECEIVABLE_MEASURES = frozenset({"accounts_receivable", "receivable_contra", "sales_tax_payable"})


def _engine(ctx: BookContext) -> BookContext:
    """The book with POL-004 ``ENGINE`` and the derived POL-123 basis in every period (pin P)."""
    policies = []
    for policy in ctx.policies.all():
        if policy.code == "billing.posting":
            policy = dataclasses.replace(policy, value="ENGINE")
        elif policy.code == "balance.position_invoice_basis":
            policy = dataclasses.replace(policy, value="UNCONDITIONAL_INVOICES_ONLY")
        policies.append(policy)
    return dataclasses.replace(ctx, policies=PolicyResolver(tuple(policies)))


def _run(ctx: BookContext, st: AllocatedState) -> tuple[BalanceState, Trace]:
    """Stages 09 and 10 over one book; the trace re-evaluates node for node (DG-ENG-04)."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)
    recognition = s09_recognition.run(ctx, st, tb)
    state = s10_billing_balances.run(ctx, recognition, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    assert state.allocated is st and state.recognition is recognition
    for document in state.documents:  # S10-INV-04
        sign = -1 if document.kind == "CREDIT_MEMO" else 1
        total = sum(line.amount for line in document.lines)
        assert sum(document.attribution.values()) == sign * total
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _target(state: BalanceState, measure: str, subject_key: str, period_key: str) -> Target:
    return next(
        target
        for target in state.billing
        if (target.measure, target.subject_key, target.period_key)
        == (measure, subject_key, period_key)
    )


def _billed(state: BalanceState, subject_key: str, period_key: str) -> int:
    return _target(state, "billed_cum", subject_key, period_key).value


def _unconditional(state: BalanceState, period_key: str) -> int:
    return _target(state, "billed_unconditional_cum", CONTRACT_AT_ENTITY, period_key).value


def _service(key: str, amount: int = 1000) -> ObligationState:
    services = segment(Fraction(amount), amount * 100, start=YEAR_START, end=YEAR_END)
    return obligation(key, [services], convention="MONTHLY_EVEN")


def _invoice(
    version: int,
    when: date,
    number: str,
    amount: str,
    *,
    key: str | None = None,
    line: str = "L1",
    tax: str | None = None,
    cancellable: bool | None = None,
    contract_key: str = CONTRACT_KEY,
) -> EventView:
    payload: dict[str, object] = {
        "invoice_number": number,
        "line_external_id": line,
        "amount": Decimal(amount),
        "issue_date": when,
    }
    if key is not None:
        payload["obligation_key"] = key
    if tax is not None:
        payload["tax_amount"] = Decimal(tax)
    if cancellable is not None:
        payload["is_cancellable"] = cancellable
    keys = [] if key is None else [key]
    return event_view(
        contract_key, version, "BILLING_RECORDED", when, payload, obligation_keys=keys
    )


def _credit_memo(
    version: int,
    when: date,
    number: str,
    amount: str,
    *,
    key: str | None = None,
    credited: str | None = None,
    contract_key: str = CONTRACT_KEY,
) -> EventView:
    payload: dict[str, object] = {
        "credit_memo_number": number,
        "amount": Decimal(amount),
        "issue_date": when,
    }
    if key is not None:
        payload["obligation_key"] = key
    if credited is not None:
        payload["credited_invoice_number"] = credited
    keys = [] if key is None else [key]
    return event_view(
        contract_key, version, "CREDIT_MEMO_RECORDED", when, payload, obligation_keys=keys
    )


def _payment(
    version: int, when: date, reference: str, amount: str, applied: Sequence[str] = ()
) -> EventView:
    payload: dict[str, object] = {
        "receipt_reference": reference,
        "amount": Decimal(amount),
        "receipt_date": when,
    }
    if applied:
        payload["applied_invoice_numbers"] = list(applied)
    return event_view(CONTRACT_KEY, version, "PAYMENT_RECEIVED", when, payload)


def test_s10_r01_attribution_per_document() -> None:
    obligations = [_service("POB-01"), _service("POB-02"), _service("POB-03")]
    events = [
        _invoice(2, date(2026, 1, 31), "INV-1", "500.00", key="POB-01", line="L1"),
        _invoice(3, date(2026, 1, 31), "INV-1", "100.00", line="L2"),
        _invoice(4, date(2026, 1, 31), "INV-1", "200.00", line="L3"),
        _invoice(5, date(2026, 2, 28), "INV-2", "0.01", line="L1"),
        _invoice(6, date(2026, 2, 28), "INV-2", "0.01", line="L2"),
        _credit_memo(7, date(2026, 3, 31), "CM-1", "100.00"),
        _credit_memo(8, date(2026, 4, 30), "CM-2", "100.00", credited="INV-1"),
    ]
    state, trace = _run(CTX, allocated_state(obligations, events=events))
    attribution = {document.number: dict(document.attribution) for document in state.documents}
    # The referenced line goes to POB-01; the unreferenced 300.00 is apportioned once.
    assert attribution["INV-1"] == {O1: usd("600.00"), O2: usd("100.00"), O3: usd("100.00")}
    assert [_billed(state, key, "FY2026-P01") for key in (O1, O2, O3)] == [
        usd("600.00"),
        usd("100.00"),
        usd("100.00"),
    ]
    # Two unreferenced lines of 0.01 are summed and apportioned once: 0.01 / 0.01 / 0.00, not
    # 0.02 / 0.00 / 0.00 line by line.
    assert attribution["INV-2"] == {O1: 1, O2: 1, O3: 0}
    assert attribution["INV-2"] != {
        key: sum(pair)
        for key, *pair in zip(
            (O1, O2, O3),
            largest_remainder(1, [Fraction(1)] * 3, [O1, O2, O3]),
            largest_remainder(1, [Fraction(1)] * 3, [O1, O2, O3]),
            strict=True,
        )
    }
    # CHK-003c: an unreferenced credit memo of −100.00 over three equal weights.
    assert attribution["CM-1"] == {O1: usd("-33.34"), O2: usd("-33.33"), O3: usd("-33.33")}
    # A credit memo naming INV-1 is apportioned by that invoice's attribution (6 : 1 : 1).
    assert attribution["CM-2"] == {O1: usd("-75.00"), O2: usd("-12.50"), O3: usd("-12.50")}
    assert [_billed(state, key, "FY2026-P04") for key in (O1, O2, O3)] == [
        usd("600.00") + 1 - usd("33.34") - usd("75.00"),
        usd("100.00") + 1 - usd("33.33") - usd("12.50"),
        usd("100.00") - usd("33.33") - usd("12.50"),
    ]

    cm_1 = next(document for document in state.documents if document.number == "CM-1")
    share = _node(trace, f"billed_attributed@{cm_1.document_key}:{O1}:-")
    assert (share.formula_id, share.value, share.params["mode"], share.params["keys"]) == (
        "bil.attribution.v1",
        "-33.34",
        "apportion",
        f"{O1}|{O2}|{O3}",
    )
    billed = _node(trace, f"billed_cum:{O2}:FY2026-P03")  # 100.00 + 0.01 − 33.33
    assert billed.value == "66.68"
    assert billed.inputs == (f"billed_attributed_cum:{O2}:FY2026-P03",)
    assert _target(state, "billed_attributed_cum", O2, "FY2026-P03").value == usd("66.68")
    direct = _node(trace, f"billed_cum:{O1}:FY2026-P01")
    assert direct.inputs[0] == SourceRef(
        "contract_event", events[0].event_key, {"member": "amount", "value": "500.00"}
    )


def test_s10_r01_unreferenced_credit_memo_over_unequal_posted_allocations() -> None:
    """S10-R-01 and ALG-02 step 3 over unequal weights (D-88 L7-5-Q-4; supervisor ruling R-46).

    Posted allocations 573.20 / 385.19 / 141.61 of 1,100.00. A credit memo of 100.00 that names
    no obligation and no credited invoice is apportioned once by largest remainder, the sign
    applied afterwards: quotas 52.1091 / 35.0173 / 12.8736, floors 52.10 / 35.01 / 12.87, and the
    two remaining cents go to the largest remainders, POB-01 and POB-02.
    """
    allocations = (
        (Fraction(87_700, 153), usd("573.20")),
        (Fraction(10_400, 27), usd("385.19")),
        (Fraction(65_000, 459), usd("141.61")),
    )
    obligations = [
        obligation(
            f"POB-0{number}",
            [segment(exact, posted, start=YEAR_START, end=YEAR_END)],
            convention="MONTHLY_EVEN",
        )
        for number, (exact, posted) in enumerate(allocations, 1)
    ]
    events = [
        _invoice(2, date(2026, 10, 31), "INV-1", "800.00", key="POB-01"),
        _invoice(3, date(2026, 10, 31), "INV-2", "400.00", key="POB-02"),
        _credit_memo(4, date(2026, 10, 31), "CM-1", "100.00"),
    ]
    state, trace = _run(CTX, allocated_state(obligations, events=events))
    attribution = {document.number: dict(document.attribution) for document in state.documents}
    assert attribution["CM-1"] == {O1: usd("-52.11"), O2: usd("-35.02"), O3: usd("-12.87")}
    # POB-03 was never invoiced and still takes its share; the obligations sum to the contract.
    billed = [_billed(state, key, "FY2026-P10") for key in (O1, O2, O3)]
    assert billed == [usd("747.89"), usd("364.98"), usd("-12.87")]
    assert sum(billed) == usd("1100.00")
    credit = next(document for document in state.documents if document.number == "CM-1")
    share = _node(trace, f"billed_attributed@{credit.document_key}:{O2}:-")
    assert (share.formula_id, share.value, share.params["mode"]) == (
        "bil.attribution.v1",
        "-35.02",
        "apportion",
    )


def test_s10_r02_taxes_excluded() -> None:
    invoice = _invoice(2, date(2026, 1, 31), "INV-1", "1000.00", key="POB-01", tax="80.00")
    state, _ = _run(CTX, allocated_state([_service("POB-01")], events=[invoice]))
    assert _billed(state, O1, "FY2026-P01") == usd("1000.00")  # CHK-023 inputs
    (document,) = state.documents
    assert (document.lines[0].amount, document.lines[0].tax_amount) == (
        usd("1000.00"),
        usd("80.00"),
    )
    assert dict(document.attribution) == {O1: usd("1000.00")}
    assert _unconditional(state, "FY2026-P01") == usd("1000.00")


def test_s10_r06_erp_and_engine_modes() -> None:
    cancellable = _invoice(2, date(2026, 1, 31), "INV-A", "1000.00", key="POB-01", cancellable=True)
    paid = _payment(3, date(2026, 3, 1), "RCPT-1", "1000.00", applied=["INV-A"])
    case_a = allocated_state([_service("POB-01")], events=[cancellable, paid])

    # ERP mode: the invoice counts on its effective date.
    state, _ = _run(CTX, case_a)
    assert state.documents[0].lines[0].mode == "ERP"
    assert _unconditional(state, "FY2026-P01") == usd("1000.00")
    assert _billed(state, O1, "FY2026-P01") == usd("1000.00")

    # ENGINE mode, CHK-024 Case A: memo-only until the payment applied on 1 March.
    state, trace = _run(_engine(CTX), case_a)
    line = state.documents[0].lines[0]
    assert (line.mode, line.unconditional_date) == ("ENGINE", date(2026, 3, 1))
    assert [_unconditional(state, key) for key in ("FY2026-P01", "FY2026-P02", "FY2026-P03")] == [
        0,
        0,
        usd("1000.00"),
    ]
    assert [_billed(state, O1, k) for k in ("FY2026-P01", "FY2026-P02", "FY2026-P03")] == [
        0,
        0,
        usd("1000.00"),
    ]  # memo-only until the payment (POL-123)
    node = _node(trace, f"billed_unconditional_cum:{CONTRACT_AT_ENTITY}:FY2026-P03")
    assert (node.formula_id, node.value) == ("bil.unconditional_date.v1", "1000.00")

    # Case B: noncancellable from 31 January.
    noncancellable = _invoice(2, date(2026, 1, 31), "INV-B", "1000.00", key="POB-01")
    state, _ = _run(_engine(CTX), allocated_state([_service("POB-01")], events=[noncancellable]))
    assert _unconditional(state, "FY2026-P01") == usd("1000.00")

    # A status update with the same amount makes the line noncancellable and adds no billing.
    update = _invoice(3, date(2026, 2, 15), "INV-A", "1000.00", key="POB-01", cancellable=False)
    state, _ = _run(
        _engine(CTX), allocated_state([_service("POB-01")], events=[cancellable, update])
    )
    assert len(state.documents) == 1
    assert state.documents[0].lines[0].unconditional_date == date(2026, 2, 15)
    assert (_unconditional(state, "FY2026-P01"), _unconditional(state, "FY2026-P02")) == (
        0,
        usd("1000.00"),
    )
    assert _billed(state, O1, "FY2026-P02") == usd("1000.00")
    assert _billed(state, O1, "FY2026-P01") == 0
    assert state.findings == ()


def test_l8_e_engine_billed_cum_counts_from_the_unconditional_source() -> None:
    """D-89 L7-6-Q-9: in ENGINE mode ``billed_cum`` counts an invoice line from its S10-R-06
    unconditional date and a credit memo by its ENG-06 position; S10-R-04 stands. A line's
    ``unconditional_source`` is its own event when the unconditional date is its effective date,
    else the payment or status update that sets the date, and None while memo-only.
    ``billed_amount`` counts a line in the version whose events first include its source, and
    ``_billed_before`` counts a line whose source precedes the PROSPECTIVE boundary."""
    cancellable = _invoice(2, date(2026, 1, 31), "INV-A", "1000.00", key="POB-01", cancellable=True)
    noncancellable = _invoice(3, date(2026, 1, 31), "INV-B", "400.00", key="POB-01")
    paid = _payment(4, date(2026, 3, 1), "RCPT-1", "1000.00", applied=["INV-A"])
    world = allocated_state([_service("POB-01")], events=[cancellable, noncancellable, paid])

    state, _ = _run(_engine(CTX), world)
    sources = {
        line.number: line.unconditional_source for doc in state.documents for line in doc.lines
    }
    assert sources == {"INV-A": paid, "INV-B": noncancellable}
    assert [_billed(state, O1, k) for k in ("FY2026-P01", "FY2026-P02", "FY2026-P03")] == [
        usd("400.00"),
        usd("400.00"),
        usd("1400.00"),
    ]
    erp, _ = _run(CTX, world)
    assert {line.number: line.unconditional_source for d in erp.documents for line in d.lines} == {
        "INV-A": cancellable,
        "INV-B": noncancellable,
    }

    # Memo-only: no source, no billing at the version date.
    memo_only, _ = _run(_engine(CTX), allocated_state([_service("POB-01")], events=[cancellable]))
    assert memo_only.documents[0].lines[0].unconditional_source is None
    measures = memo_only.obligation_measures[O1]
    assert (measures.billed_cum, measures.billed_amount) == (0, 0)

    # The invoice was included earlier; the payment that makes it unconditional is new.
    old_invoice = dataclasses.replace(cancellable, is_new=False)
    events = [old_invoice, paid]
    counted, _ = _run(_engine(CTX), allocated_state([_service("POB-01")], events=events))
    measures = counted.obligation_measures[O1]
    assert (measures.billed_cum, measures.billed_amount) == (usd("1000.00"), usd("1000.00"))
    events = [old_invoice, dataclasses.replace(paid, is_new=False)]
    earlier, _ = _run(_engine(CTX), allocated_state([_service("POB-01")], events=events))
    measures = earlier.obligation_measures[O1]
    assert (measures.billed_cum, measures.billed_amount) == (usd("1000.00"), 0)

    # A PROSPECTIVE boundary on 15 February between the invoice and its payment.
    amended = event_view(
        CONTRACT_KEY,
        3,
        "CONTRACT_AMENDED",
        date(2026, 2, 15),
        {"modification_id": "MOD-1"},
        obligation_keys=["POB-01"],
    )
    inception = segment(Fraction(1000), usd("1000.00"), start=YEAR_START, end=YEAR_END)
    prospective = dataclasses.replace(
        segment(
            Fraction(1000),
            usd("1000.00"),
            start=YEAR_START,
            end=YEAR_END,
            effective=date(2026, 2, 15),
            basis="PROSPECTIVE",
            cause=SegmentCause.MODIFICATION,
            event_key=amended.event_key,
        ),
        remaining_billing_plan=Fraction(1000),
    )
    modified = obligation("POB-01", [inception, prospective], convention="MONTHLY_EVEN")
    events = [cancellable, amended, paid]
    engine, _ = _run(_engine(CTX), allocated_state([modified], events=events))
    # 1,000.00 plan − (1,000.00 billed − 0.00 before the boundary): the payment follows it.
    assert engine.obligation_measures[O1].remaining_billing == 0
    erp_modified, _ = _run(CTX, allocated_state([modified], events=events))
    # ERP: the invoice counts on 31 January, before the boundary.
    assert erp_modified.obligation_measures[O1].remaining_billing == usd("1000.00")


def test_l5_3_engine_mode_unconditional_billing_per_obligation() -> None:
    """JET-03 amounts per obligation (Table 14-A owner "contracting; obligation"; L5-3-Q-12).

    In ``ENGINE`` mode stage 10 publishes ``billed_unconditional_cum`` and, for a contract with
    taxed lines, ``sales_tax_billed_cum`` per obligation, and their sum over the obligations is B_u
    of S10-R-08 in every period. The noncancellable invoice counts from 31 January with its tax
    80.00 (CHK-023); the cancellable one from the payment applied on 1 March (CHK-024 Case A).
    """
    events = [
        _invoice(2, date(2026, 1, 31), "INV-1", "1000.00", key="POB-01", tax="80.00"),
        _invoice(3, date(2026, 1, 31), "INV-2", "500.00", key="POB-02", cancellable=True),
        _payment(4, date(2026, 3, 1), "RCPT-1", "500.00", applied=["INV-2"]),
    ]
    st = allocated_state([_service("POB-01"), _service("POB-02")], events=events)
    state, trace = _run(_engine(CTX), st)
    periods = ("FY2026-P01", "FY2026-P02", "FY2026-P03")
    by_obligation = {
        subject: [_target(state, "billed_unconditional_cum", subject, key).value for key in periods]
        for subject in (O1, O2)
    }
    assert by_obligation == {O1: [usd("1000.00")] * 3, O2: [0, 0, usd("500.00")]}
    assert [_unconditional(state, key) for key in periods] == [
        by_obligation[O1][index] + by_obligation[O2][index] for index in range(3)
    ]
    taxes = {
        subject: _target(state, "sales_tax_billed_cum", subject, "FY2026-P01").value
        for subject in (O1, O2)
    }
    assert taxes == {O1: usd("80.00"), O2: 0}
    node = _node(trace, f"billed_unconditional_cum:{O2}:FY2026-P03")
    assert (node.formula_id, node.value) == ("bil.unconditional_date.v1", "500.00")
    # ERP mode publishes neither: the billing system posts the invoices (POL-004).
    erp, _ = _run(CTX, st)
    per_obligation = ("billed_unconditional_cum", "sales_tax_billed_cum")
    assert not [t for t in erp.billing if t.subject_key in (O1, O2) and t.measure in per_obligation]


def test_s10_r07_status_update_mismatch() -> None:
    invoice = _invoice(2, date(2026, 1, 31), "INV-7", "1000.00", key="POB-01", cancellable=True)
    update = _invoice(3, date(2026, 2, 15), "INV-7", "900.00", key="POB-01", cancellable=False)
    state, _ = _run(CTX, allocated_state([_service("POB-01")], events=[invoice, update]))
    assert [(f.code, f.severity, f.subject_key, f.event_key) for f in state.findings] == [
        ("INVOICE_STATUS_UPDATE_MISMATCH", "ERROR", CONTRACT_KEY, update.event_key)
    ]
    assert dict(state.findings[0].detail) == {
        "invoice_number": "INV-7",
        "line_external_id": "L1",
        "rule": "S10-R-07",
    }
    assert _billed(state, O1, "FY2026-P02") == usd("1000.00")


def test_d91_status_update_obligation_key_mismatch() -> None:
    """D-91 C606-01 (3), S10-R-07 rev 1.7: a status update whose non-null ``obligation_key`` differs
    from the first line's non-null key raises ``INVOICE_STATUS_UPDATE_MISMATCH`` (detail member
    ``obligation_key``); the first line's attribution stands (billed 1,000.00 on POB-01 at P02). A
    null ``obligation_key`` on the update is no change: no finding, and the update is the line's
    ``unconditional_source``."""
    invoice = _invoice(2, date(2026, 1, 31), "INV-7", "1000.00", key="POB-01", cancellable=True)
    update = _invoice(3, date(2026, 2, 15), "INV-7", "1000.00", key="POB-02", cancellable=False)
    st = allocated_state([_service("POB-01"), _service("POB-02")], events=[invoice, update])
    state, _ = _run(CTX, st)
    assert [(f.code, f.severity, f.subject_key, f.event_key) for f in state.findings] == [
        ("INVOICE_STATUS_UPDATE_MISMATCH", "ERROR", CONTRACT_KEY, update.event_key)
    ]
    assert dict(state.findings[0].detail) == {
        "invoice_number": "INV-7",
        "line_external_id": "L1",
        "rule": "S10-R-07",
        "member": "obligation_key",
    }
    assert [
        (line.obligation_key, line.amount) for doc in state.documents for line in doc.lines
    ] == [("POB-01", usd("1000.00"))]
    assert (_billed(state, O1, "FY2026-P02"), _billed(state, O2, "FY2026-P02")) == (
        usd("1000.00"),
        0,
    )
    # Null on the update side: accepted, and in ENGINE mode the update dates the cancellable line.
    unnamed = _invoice(3, date(2026, 2, 15), "INV-7", "1000.00", cancellable=False)
    state, _ = _run(_engine(CTX), allocated_state([_service("POB-01")], events=[invoice, unnamed]))
    assert state.findings == ()
    (line,) = state.documents[0].lines
    assert (line.obligation_key, line.unconditional_date) == ("POB-01", date(2026, 2, 15))
    assert line.unconditional_source is not None
    assert line.unconditional_source.event_key == unnamed.event_key


def test_s10_r04_billing_while_not_a_contract() -> None:
    statuses = ((YEAR_START, "NOT_A_CONTRACT"), (date(2026, 6, 30), "ACTIVE"))
    events = [
        _invoice(2, date(2026, 3, 31), "INV-1", "300.00", key="POB-01"),
        _invoice(3, date(2026, 7, 31), "INV-2", "200.00", key="POB-01"),
    ]
    state, _ = _run(CTX, allocated_state([_service("POB-01")], events=events, statuses=statuses))
    assert (_billed(state, O1, "FY2026-P03"), _billed(state, O1, "FY2026-P07")) == (
        usd("300.00"),
        usd("500.00"),
    )
    assert [state.documents[index].lines[0].in_position for index in (0, 1)] == [False, True]
    assert [_unconditional(state, key) for key in ("FY2026-P03", "FY2026-P06", "FY2026-P07")] == [
        0,
        0,
        usd("200.00"),
    ]


# Golden Contract 1 (legacy 02 §5.3; golden step 02): (POB, quantity, extended SSP, stated price).
CONTRACT_1 = "Contract 1"
CONTRACT_1_LINES = (
    ("POB #1", 5, 500, 500),
    ("POB #2", 2, 368, 400),
    ("POB #3", 1, 150, 400),
    ("POB #4", 1000, 1000, 0),
)
PARITY = book_context(entity(start=date(2023, 1, 1), months=12), preset="LEGACY_PARITY")


def _contract_1() -> list[ObligationState]:
    """Inception segments under the units measure; the billing plan is the stated price."""
    posted = largest_remainder(
        1300 * 100,
        [Fraction(ssp) for _, _, ssp, _ in CONTRACT_1_LINES],
        [key for key, *_ in CONTRACT_1_LINES],
    )
    total = sum(ssp for _, _, ssp, _ in CONTRACT_1_LINES)
    obligations = []
    for (key, quantity, ssp, price), a_posted in zip(CONTRACT_1_LINES, posted, strict=True):
        seg = segment(
            Fraction(1300 * ssp, total),
            a_posted,
            start=date(2023, 1, 1),
            end=date(2023, 12, 31),
            quantity=Fraction(quantity),
            measure="UNITS_DELIVERED",
        )
        seg = dataclasses.replace(seg, remaining_billing_plan=Fraction(price))
        obligations.append(
            obligation(
                key,
                [seg],
                contract_key=CONTRACT_1,
                method="UNITS_DELIVERED",
                convention=None,
                quantity=Fraction(quantity),
            )
        )
    return obligations


def test_tc_delivery_06_contract1_return_billing() -> None:
    # Golden steps 04 to 07 of Contract 1 (docs/legacy/golden/0N-*/contract_live.csv).
    step_04, step_05, step_07 = date(2023, 1, 31), date(2023, 2, 28), date(2023, 4, 30)
    rows = (
        (step_04, "POB #1", "2", "100"),
        (step_04, "POB #2", "1", "100"),
        (step_04, "POB #3", "0.5", "100"),
        (step_05, "POB #1", "1", "100"),
        (step_07, "POB #1", "-3", "-200"),
        (step_07, "POB #2", "0", "300"),
    )
    events: list[EventView] = []
    for when, key, delivery, billing in rows:
        quantity, amount = Decimal(delivery), Decimal(billing)
        version = len(events) + 2
        if quantity > 0:
            payload = {"obligation_key": key, "quantity": quantity, "trigger": "DELIVERY"}
            events.append(
                event_view(
                    CONTRACT_1, version, "DELIVERY_RECORDED", when, payload, obligation_keys=[key]
                )
            )
        elif quantity < 0:
            payload = {"obligation_key": key, "quantity": -quantity}
            events.append(
                event_view(
                    CONTRACT_1, version, "RETURN_RECORDED", when, payload, obligation_keys=[key]
                )
            )
        version = len(events) + 2
        if amount > 0:
            events.append(
                _invoice(
                    version,
                    when,
                    f"INV-{when.isoformat()}",
                    billing,
                    key=key,
                    line=key,
                    contract_key=CONTRACT_1,
                )
            )
        elif amount < 0:
            events.append(
                _credit_memo(
                    version,
                    when,
                    f"CM-{when.isoformat()}",
                    str(-amount),
                    key=key,
                    contract_key=CONTRACT_1,
                )
            )
    st = allocated_state(
        _contract_1(),
        events=events,
        inception=date(2023, 1, 1),
        statuses=((date(2023, 1, 1), "ACTIVE"),),
    )
    state, trace = _run(PARITY, st)
    pob_1, pob_2 = f"{CONTRACT_1}/POB #1", f"{CONTRACT_1}/POB #2"
    first, second = state.obligation_measures[pob_1], state.obligation_measures[pob_2]
    assert (first.as_of, first.billed_cum, first.remaining_billing) == (step_07, 0, usd("500.00"))
    assert (second.billed_cum, second.remaining_billing) == (usd("400.00"), 0)
    assert (_billed(state, pob_1, "FY2023-P03"), _billed(state, pob_1, "FY2023-P04")) == (
        usd("200.00"),
        0,
    )
    assert _billed(state, pob_2, "FY2023-P04") == usd("400.00")
    remaining = _node(trace, f"remaining_billing:{pob_1}:-")
    assert (remaining.formula_id, remaining.value, remaining.inputs) == (
        "bil.remaining_billing.v1",
        "500.00",
        (f"billed_cum:{pob_1}:-",),
    )
    # The version first includes every event here, so the activity is the billing of the stream.
    assert (first.billed_amount, second.billed_amount) == (0, usd("400.00"))


def test_s10_inv_06_erp_mode_has_no_receivable_targets() -> None:
    invoice = _invoice(2, date(2026, 1, 31), "INV-1", "1000.00", key="POB-01", tax="80.00")
    payment = _payment(3, date(2026, 2, 10), "RCPT-1", "1080.00", applied=["INV-1"])
    state, trace = _run(CTX, allocated_state([_service("POB-01")], events=[invoice, payment]))
    assert state.documents[0].lines[0].mode == "ERP"
    assert (state.accounts_receivable, state.receivable_contra) == ((), ())
    for target in (*state.billing, *state.accounts_receivable, *state.receivable_contra):
        assert target.measure not in RECEIVABLE_MEASURES
    assert not {node.measure for node in trace.nodes} & RECEIVABLE_MEASURES


def test_cash_receipts() -> None:
    # EX-02-A: 720.00 over 36 months; NOT_A_CONTRACT until criteria are met at the end of month 6,
    # with receipts of 20.00 at the end of months 1 to 6.
    calendar = entity(months=36)
    ctx = book_context(calendar)
    services = segment(Fraction(720), usd("720.00"), start=YEAR_START, end=date(2028, 12, 31))
    ob = obligation("POB-01", [services], convention="MONTHLY_EVEN")
    month_ends = [calendar.periods[index].end_date for index in range(6)]
    receipts = [
        _payment(
            index + 2, when, f"RCPT-{index + 1}", "20.00", applied=["INV-1"] if index == 5 else ()
        )
        for index, when in enumerate(month_ends)
    ]
    statuses = ((YEAR_START, "NOT_A_CONTRACT"), (date(2026, 6, 30), "ACTIVE"))
    state, _ = _run(ctx, allocated_state([ob], events=receipts, statuses=statuses))
    paid = [state.paid_cum[(CONTRACT_AT_ENTITY, f"FY2026-P{month:02d}")] for month in range(1, 8)]
    assert paid == [usd("20.00") * month for month in range(1, 7)] + [usd("120.00")]
    assert [receipt.event.effective_date for receipt in state.receipts] == month_ends  # layer dates
    assert {receipt.entity for receipt in state.receipts} == {"US01"}
    assert state.receipts[-1].applied_invoice_numbers == ("INV-1",)
    assert state.receipts[0].applied_invoice_numbers == ()
    # The deposit transferred at criteria met (S02-R-08) is the 120.00 received by then, and the
    # stage 09 target at the transition is cumulative_posted(720, 72,000, 6/36) = 120.00.
    assert state.paid_cum[(CONTRACT_AT_ENTITY, "FY2026-P06")] == usd("120.00")
    revenue = next(
        target for target in state.recognition.revenue_targets if target.period_key == "FY2026-P06"
    )
    assert revenue.value == usd("120.00")
    assert _billed(state, O1, "FY2026-P06") == 0  # receipts are not billing


def test_d97_27_status_update_tax_mismatch_is_a_warning_without_value_effect() -> None:
    """D-97 (27), S10-R-07 rev 1.10: a status update whose ``tax_amount`` differs from the first
    line's raises ``INVOICE_STATUS_UPDATE_TAX_MISMATCH`` (WARNING, detail member ``tax_amount``);
    the update keeps its role — in ENGINE mode it still dates the cancellable line — and its tax is
    dropped: billing 1,000.00 and tax 80.00 exactly as with a matching update. Before D-97 (27)
    the difference was silent."""
    invoice = _invoice(
        2, date(2026, 1, 31), "INV-7", "1000.00", key="POB-01", tax="80.00", cancellable=True
    )
    update = _invoice(
        3, date(2026, 2, 15), "INV-7", "1000.00", key="POB-01", tax="50.00", cancellable=False
    )
    st = allocated_state([_service("POB-01")], events=[invoice, update])
    state, _ = _run(_engine(CTX), st)
    assert [(f.code, f.severity, f.subject_key, f.event_key) for f in state.findings] == [
        ("INVOICE_STATUS_UPDATE_TAX_MISMATCH", "WARNING", CONTRACT_KEY, update.event_key)
    ]
    assert dict(state.findings[0].detail) == {
        "invoice_number": "INV-7",
        "line_external_id": "L1",
        "member": "tax_amount",
        "rule": "S10-R-07",
    }
    (line,) = [line for doc in state.documents for line in doc.lines if doc.kind == "INVOICE"]
    assert line.unconditional_date == date(2026, 2, 15)  # the update still dates the line
    assert _billed(state, O1, "FY2026-P02") == usd("1000.00")
    matching = _invoice(
        3, date(2026, 2, 15), "INV-7", "1000.00", key="POB-01", tax="80.00", cancellable=False
    )
    same, _ = _run(_engine(CTX), allocated_state([_service("POB-01")], events=[invoice, matching]))
    assert same.findings == ()
    assert (
        _target(same, "sales_tax_billed_cum", O1, "FY2026-P02").value
        == _target(state, "sales_tax_billed_cum", O1, "FY2026-P02").value
    )  # no value effect: the update's tax never enters anything
