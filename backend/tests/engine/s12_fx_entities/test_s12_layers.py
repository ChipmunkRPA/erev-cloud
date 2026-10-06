"""Stage 12 rates and contract-liability layers.

ENGINE_SPEC_B §12.2.1 and §12.2.2 (S12-R-01 to S12-R-08), §12.3 (S12-INV-01, S12-INV-03), §12.5
and §12.7 EX-12-A; POLICIES ALG-08 §2.9.1 to §2.9.3 (CHK-080), POL-160 to POL-162. Stages 10 and 11
are built in lane L2-4, so the tests pass a fake consumed state that carries ``FxFlows`` (D-81
integration after merge; L2-5-Q-10). Every trace re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import FxRateInput
from erev_engine.dates import month_end
from erev_engine.errors import EngineError
from erev_engine.money import cumulative_posted, largest_remainder, to_fraction
from erev_engine.stages import s12_fx_entities
from erev_engine.stages.s12_fx_entities import ControlFlow, FxFlows, FxState, LayerMovement
from erev_engine.stages.state import AllocatedState, BookContext, PolicyResolver, RateIndex
from erev_engine.trace import Trace, TraceBuilder, TraceNode, reevaluate
from support import bundles
from support.recognition import CONTRACT_KEY, allocated_state, book_context, period_amounts, usd

ENTITY = bundles.ENTITY_CODE
GROUP = "CG-1"
UNIT = f"{GROUP}@{ENTITY}"
CONTRACT = f"{CONTRACT_KEY}@{ENTITY}"
SERVICES = f"{CONTRACT_KEY}/S"
LICENCE = f"{CONTRACT_KEY}/L"
RATE_SET = "EURUSD-PUBLISHED@v1"
YEAR_2026 = [f"FY2026-P{month:02d}" for month in range(1, 13)]


@dataclass(frozen=True, slots=True)
class _Costs:
    """A fake stage 11 output as stage 12 reads it (L2-5-Q-10)."""

    allocated: AllocatedState
    fx_flows: FxFlows


def _context(
    *, book: str = "ASC606", months: int = 12, policies: Mapping[str, str] | None = None
) -> BookContext:
    calendar = bundles.entity(months=months, books=(book,))
    ctx = book_context(calendar, book_code=book, currency="EUR")
    ctx = dataclasses.replace(ctx, currencies=bundles.currencies("EUR", "USD"))
    for code, value in (policies or {}).items():
        ctx = _period_policy(ctx, code, value)
    return ctx


def _period_policy(ctx: BookContext, code: str, value: str) -> BookContext:
    """Every PERIOD-scope value of ``code`` replaced by a resolved override (CV-17)."""
    policies = tuple(
        dataclasses.replace(policy, value=value, level="C", source_ref="OVR-TEST")
        if policy.code == code
        else policy
        for policy in ctx.policies.all()
    )
    assert any(policy.code == code for policy in policies)
    return dataclasses.replace(ctx, policies=PolicyResolver(policies))


def _spot(on: date, rate: str) -> FxRateInput:
    key = f"EURUSD-SPOT-{on.isoformat()}"
    return FxRateInput(key, RATE_SET, "spot", "EUR", "USD", on, None, Decimal(rate))


def _period_rate(kind: str, on: date, rate: str) -> FxRateInput:
    period_key = f"FY{on.year}-P{on.month:02d}"
    key = f"EURUSD-{kind.upper()}-{period_key}"
    return FxRateInput(key, RATE_SET, kind, "EUR", "USD", month_end(on), period_key, Decimal(rate))


def _event(stream_version: int) -> str:
    return f"{CONTRACT_KEY}/EV-{stream_version:06d}"


def _invoice(
    stream_version: int,
    issued: date,
    amount: str,
    *,
    cancellable: bool = False,
    unconditional: date | None = None,
    receipt: date | None = None,
) -> ControlFlow:
    due = unconditional if cancellable else (unconditional or issued)
    return ControlFlow(
        "BILLING",
        ENTITY,
        CONTRACT,
        _event(stream_version),
        issued,
        stream_version,
        usd(amount),
        unconditional_date=due,
        first_receipt_date=receipt,
    )


def _release(subject: str, on: date, amount: str, kind: str = "REVENUE") -> ControlFlow:
    """A time-driven release at a period end (``record_seq`` None)."""
    source = f"{subject}@FY{on.year}-P{on.month:02d}"
    return ControlFlow(kind, ENTITY, subject, source, on, None, usd(amount))


def _on_event(
    kind: str, stream_version: int, on: date, amount: str, subject: str = CONTRACT
) -> ControlFlow:
    return ControlFlow(
        kind, ENTITY, subject, _event(stream_version), on, stream_version, usd(amount)
    )


def _run(
    ctx: BookContext,
    flows: Iterable[ControlFlow],
    rates: Iterable[FxRateInput],
    *,
    positions: Mapping[tuple[str, str], int] | None = None,
) -> tuple[FxState, Trace]:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    costs = _Costs(allocated_state([]), FxFlows(tuple(flows), dict(positions or {})))
    state = s12_fx_entities.run(ctx, costs, tb, rates=RateIndex(tuple(rates)))
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _moves(state: FxState, kind: str, layer_key: str | None = None) -> list[LayerMovement]:
    return [
        move
        for move in state.layer_movements
        if move.movement_kind == kind and (layer_key is None or move.layer_key == layer_key)
    ]


def _created(state: FxState, kind: str = "LIABILITY_LAYER_CREATED") -> list[tuple[object, ...]]:
    return [
        (
            move.layer_key,
            move.effective_date,
            move.amount_txn,
            move.amount_functional,
            move.rate_key,
        )
        for move in _moves(state, kind)
    ]


def _cumulative(state: FxState, measure: str, subject: str) -> dict[str, int]:
    return {
        target.period_key: target.amount_functional
        for target in state.functional_targets + state.remeasurement_targets
        if target.measure == measure and target.subject_key == subject
    }


def _chk_080() -> tuple[BookContext, list[ControlFlow], list[FxRateInput]]:
    flows = [_invoice(2, date(2026, 1, 1), "6000.00"), _invoice(3, date(2026, 7, 1), "6000.00")]
    flows += [_release(SERVICES, month_end(date(2026, m, 1)), "1000.00") for m in range(1, 13)]
    rates = [_spot(date(2026, 1, 1), "1.1000"), _spot(date(2026, 7, 1), "1.2000")]
    return _context(), flows, rates


def _ex_12_a(policies: Mapping[str, str] | None = None) -> tuple[FxState, Trace]:
    flows = [
        _invoice(1, date(2026, 1, 1), "3000.00"),
        _release(SERVICES, date(2026, 1, 31), "1000.00"),
        _release(SERVICES, date(2026, 2, 28), "1000.00"),
        _on_event("REVENUE", 5, date(2026, 3, 15), "1500.00", LICENCE),
        _release(SERVICES, date(2026, 3, 31), "1000.00"),
    ]
    rates = [
        _spot(date(2026, 1, 1), "1.123456"),
        _spot(date(2026, 3, 15), "1.1400"),
        _period_rate("average", date(2026, 3, 1), "1.1350"),
        _period_rate("closing", date(2026, 3, 1), "1.1400"),
    ]
    return _run(_context(months=3, policies=policies), flows, rates)


def _credit_memos() -> tuple[BookContext, list[ControlFlow], list[FxRateInput]]:
    flows = [
        _invoice(2, date(2026, 1, 1), "1000.00"),
        _on_event("CREDIT_MEMO", 3, date(2026, 2, 15), "400.00"),
        _on_event("CREDIT_MEMO", 4, date(2026, 3, 10), "100.00"),
        _on_event("CREDIT_MEMO", 5, date(2026, 3, 20), "600.00"),
    ]
    rates = [
        _spot(date(2026, 1, 1), "1.1000"),
        _spot(date(2026, 2, 15), "1.1500"),
        _spot(date(2026, 3, 10), "1.0500"),
        _spot(date(2026, 3, 20), "1.0800"),
        _period_rate("closing", date(2026, 3, 1), "1.0800"),
    ]
    return _context(months=3), flows, rates


def test_chk_080_liability_layers_at_historical_rates() -> None:
    ctx, flows, rates = _chk_080()
    state, trace = _run(ctx, flows, rates)

    first, second = f"CONTRACT_LIABILITY:{_event(2)}", f"CONTRACT_LIABILITY:{_event(3)}"
    assert _created(state) == [
        (first, date(2026, 1, 1), 600000, 660000, "EURUSD-SPOT-2026-01-01"),
        (second, date(2026, 7, 1), 600000, 720000, "EURUSD-SPOT-2026-07-01"),
    ]
    revenue = _cumulative(state, "revenue_cum", SERVICES)
    assert list(revenue) == YEAR_2026
    assert period_amounts(revenue) == {
        period: 110000 if index < 6 else 120000 for index, period in enumerate(YEAR_2026)
    }
    assert revenue["FY2026-P12"] == 1380000
    # L1 is exactly 0 on 30 June and L2 on 31 December; the historical amounts never change.
    assert [
        move.amount_functional for move in _moves(state, "LIABILITY_LAYER_CONSUMED", first)
    ] == [110000] * 6
    assert sum(
        move.amount_functional for move in _moves(state, "LIABILITY_LAYER_CONSUMED", second)
    ) == (720000)
    balances = {
        period: [
            (b.layer_key, b.txn_open, b.fn_carrying)
            for b in state.layer_balances
            if b.period_key == period
        ]
        for period in YEAR_2026
    }
    assert balances["FY2026-P05"] == [(first, 100000, 110000)]
    assert balances["FY2026-P06"] == []
    assert balances["FY2026-P07"] == [(second, 500000, 600000)]
    assert balances["FY2026-P12"] == []
    # No FX movement exists.
    assert {move.movement_kind for move in state.layer_movements} == {
        "LIABILITY_LAYER_CREATED",
        "LIABILITY_LAYER_CONSUMED",
    }
    assert state.remeasurement_targets == ()
    assert state.findings == ()

    june = _node(
        trace, f"fx_layer_consumed:{first}@{SERVICES}@FY2026-P06#REVENUE@{SERVICES}:FY2026-P06"
    )
    assert (june.formula_id, june.value, june.inputs) == (
        "fx.layer.consume.fifo.v1",
        "1100.00",
        (f"fx_layer_created:{first}:FY2026-P01",),
    )
    assert june.params["consumed_before"] == "500000"
    assert _node(trace, f"revenue_functional:{SERVICES}:FY2026-P12").value == "13800.00"


def test_ex_12_a_layer_relief() -> None:
    state, trace = _ex_12_a()

    layer = f"CONTRACT_LIABILITY:{_event(1)}"
    assert _created(state) == [(layer, date(2026, 1, 1), 300000, 337037, "EURUSD-SPOT-2026-01-01")]
    reliefs = _moves(state, "LIABILITY_LAYER_CONSUMED", layer)
    assert [(move.effective_date, move.amount_txn, move.amount_functional) for move in reliefs] == [
        (date(2026, 1, 31), 100000, 112346),
        (date(2026, 2, 28), 100000, 112345),
        (date(2026, 3, 15), 100000, 112346),
    ]
    assert sum(move.amount_functional for move in reliefs) == 337037
    # Cumulatively rounded shares of 3,370.37 (S12-R-05): 1,123.46, then 2,246.91, then all.
    shares = (Fraction(1, 3), Fraction(2, 3), Fraction(1))
    assert [cumulative_posted(to_fraction("3370.37"), 337037, f, 2) for f in shares] == [
        112346,
        224691,
        337037,
    ]
    january = _node(trace, reliefs[0].trace_node_id)
    assert (january.value, january.rounding_residue) == ("1123.46", "-0.003333333333333333")
    assert _cumulative(state, "revenue_cum", SERVICES) == {
        "FY2026-P01": 112346,
        "FY2026-P02": 224691,
        "FY2026-P03": 224691 + 113500,
    }


def test_s12_r06_remainder_rate() -> None:
    state, trace = _ex_12_a()

    licence_asset = f"CONTRACT_ASSET:{_event(5)}"
    services_asset = f"CONTRACT_ASSET:{SERVICES}@FY2026-P03"
    assert _created(state, "ASSET_LAYER_CREATED") == [
        (licence_asset, date(2026, 3, 15), 50000, 56750, "EURUSD-AVERAGE-FY2026-P03"),
        (services_asset, date(2026, 3, 31), 100000, 113500, "EURUSD-AVERAGE-FY2026-P03"),
    ]
    # Licence revenue USD 1,690.96: the L1 remainder relieved to completion plus A1 (EX-12-A).
    assert _cumulative(state, "revenue_cum", LICENCE) == {"FY2026-P03": 169096}
    node = _node(trace, f"fx_layer_created:{licence_asset}:FY2026-P03")
    assert (node.formula_id, node.value, node.params["rate_type"]) == (
        "fx.asset_layer.create.v1",
        "567.50",
        "average",
    )
    licence = _node(trace, f"revenue_functional:{LICENCE}:FY2026-P03")
    assert licence.value == "1690.96"
    assert set(licence.inputs) == {
        f"fx_layer_consumed:CONTRACT_LIABILITY:{_event(1)}@{_event(5)}#REVENUE@{LICENCE}:FY2026-P03",
        f"fx_layer_created:{licence_asset}:FY2026-P03",
    }

    spot, _ = _ex_12_a({"fx.unbilled_revenue_rate": "TRANSACTION_DATE_SPOT"})
    assert _created(spot, "ASSET_LAYER_CREATED") == [
        (licence_asset, date(2026, 3, 15), 50000, 57000, "EURUSD-SPOT-2026-03-15"),
        (services_asset, date(2026, 3, 31), 100000, 114000, "EURUSD-SPOT-2026-03-15"),
    ]


def test_s12_r01_missing_rate() -> None:
    ctx = _context(months=3)
    state, _ = _run(ctx, [_invoice(2, date(2026, 1, 1), "1000.00")], [])
    assert [
        (f.code, f.severity, f.subject_key, f.event_key, dict(f.detail)) for f in state.findings
    ] == [
        (
            "FX_RATE_MISSING",
            "ERROR",
            UNIT,
            _event(2),
            {
                "base": "EUR",
                "date": "2026-01-01",
                "quote": "USD",
                "rate_type": "spot",
                "rule": "S12-R-01",
            },
        )
    ]
    assert (state.layer_movements, state.functional_targets, state.layer_balances) == ((), (), ())

    revenue_only = [_release(SERVICES, date(2026, 1, 31), "100.00")]
    state, _ = _run(ctx, revenue_only, [_spot(date(2026, 1, 1), "1.1000")])
    assert [
        (f.code, f.event_key, f.detail["rate_type"], f.detail["period_key"]) for f in state.findings
    ] == [("FX_RATE_MISSING", None, "average", "FY2026-P01")]

    # A same-currency conversion needs no rate: rate 1 and no rate id (S12-R-01).
    same = dataclasses.replace(
        ctx, entities={ENTITY: bundles.entity(months=3, functional_currency="EUR")}
    )
    state, _ = _run(same, [_invoice(2, date(2026, 1, 1), "1000.00")], [])
    assert state.findings == ()
    assert [(m.amount_functional, m.rate_key, m.rate) for m in state.layer_movements] == [
        (100000, None, 1)
    ]

    with pytest.raises(EngineError, match="ENGINE_INVARIANT_VIOLATED"):
        tb = TraceBuilder(engine_version=ENGINE_VERSION)
        flows = FxFlows((_invoice(2, date(2026, 1, 1), "1000.00"),))
        s12_fx_entities.run(ctx, _Costs(allocated_state([]), flows), tb)


def test_s12_r04_layer_date() -> None:
    rates = [
        _spot(date(2026, 3, 1), "1.1000"),
        _spot(date(2026, 3, 10), "1.1200"),
        _spot(date(2026, 3, 20), "1.1500"),
        _spot(date(2026, 3, 25), "1.1800"),
    ]
    received_first = _invoice(
        2,
        date(2026, 3, 1),
        "1000.00",
        cancellable=True,
        unconditional=date(2026, 3, 20),
        receipt=date(2026, 3, 10),
    )
    due_first = _invoice(
        3,
        date(2026, 3, 1),
        "1000.00",
        cancellable=True,
        unconditional=date(2026, 3, 20),
        receipt=date(2026, 3, 25),
    )
    memo_only = _invoice(4, date(2026, 3, 1), "1000.00", cancellable=True)

    earlier, _ = _run(_context(months=3), [received_first, due_first, memo_only], rates)
    assert _created(earlier) == [
        (
            f"CONTRACT_LIABILITY:{_event(2)}",
            date(2026, 3, 10),
            100000,
            112000,
            "EURUSD-SPOT-2026-03-10",
        ),
        (
            f"CONTRACT_LIABILITY:{_event(3)}",
            date(2026, 3, 20),
            100000,
            115000,
            "EURUSD-SPOT-2026-03-20",
        ),
    ]

    issue = _context(months=3, policies={"fx.cl_layer_date": "INVOICE_ISSUE_DATE"})
    issued, _ = _run(issue, [received_first, due_first], rates)
    assert _created(issued) == [
        (
            f"CONTRACT_LIABILITY:{_event(2)}",
            date(2026, 3, 1),
            100000,
            110000,
            "EURUSD-SPOT-2026-03-01",
        ),
        (
            f"CONTRACT_LIABILITY:{_event(3)}",
            date(2026, 3, 1),
            100000,
            110000,
            "EURUSD-SPOT-2026-03-01",
        ),
    ]

    # IFRS15 forces the earlier date (IFRIC 22.8, 22.9); each advance is a separate layer.
    ifrs = _context(book="IFRS15", months=3, policies={"fx.cl_layer_date": "INVOICE_ISSUE_DATE"})
    ifrs_state, _ = _run(ifrs, [received_first, due_first], rates)
    assert _created(ifrs_state) == _created(earlier)
    assert {move.book_code for move in ifrs_state.layer_movements} == {"IFRS15"}


def test_s12_r04_layer_date_stays_in_the_period_of_entry() -> None:
    """S12-R-04 rev 1.83 (supervisor ruling R-81, amending D-87 L6-5-Q-14; item
    ENG-S12-DUE-DATE-1): under the earlier-of option the layer date may not leave the accounting
    period in which the line enters the position (the flow's effective date, S10-R-06). Issued 12
    January and due 12 February, unpaid or paid on 5 February: the end of January (spot 1.1200).
    Issued 15 February and named by a receipt of 12 January: 15 February (spot 1.2000), not the
    receipt. Inside the period the earlier of due date and receipt stands (10 March, 1.2500). The
    layers then equal the position at every period end (S12-INV-03): 2,000.00 / 3,000.00 /
    4,000.00; before the rule the January end stood at 1,000.00 against 2,000.00."""
    rates = [
        _spot(date(2026, 1, 12), "1.1000"),
        _spot(date(2026, 1, 31), "1.1200"),
        _spot(date(2026, 2, 5), "1.1500"),
        _spot(date(2026, 2, 15), "1.2000"),
        _spot(date(2026, 3, 10), "1.2500"),
    ]
    due_later = _invoice(2, date(2026, 1, 12), "1000.00", unconditional=date(2026, 2, 12))
    paid_later = _invoice(
        3,
        date(2026, 1, 12),
        "1000.00",
        unconditional=date(2026, 2, 12),
        receipt=date(2026, 2, 5),
    )
    paid_before = _invoice(4, date(2026, 2, 15), "1000.00", receipt=date(2026, 1, 12))
    inside = _invoice(
        5,
        date(2026, 3, 1),
        "1000.00",
        unconditional=date(2026, 3, 20),
        receipt=date(2026, 3, 10),
    )
    flows = [due_later, paid_later, paid_before, inside]
    positions = {
        (ENTITY, "FY2026-P01"): 200000,
        (ENTITY, "FY2026-P02"): 300000,
        (ENTITY, "FY2026-P03"): 400000,
    }
    expected = [
        (
            f"CONTRACT_LIABILITY:{_event(2)}",
            date(2026, 1, 31),
            100000,
            112000,
            "EURUSD-SPOT-2026-01-31",
        ),
        (
            f"CONTRACT_LIABILITY:{_event(3)}",
            date(2026, 1, 31),
            100000,
            112000,
            "EURUSD-SPOT-2026-01-31",
        ),
        (
            f"CONTRACT_LIABILITY:{_event(4)}",
            date(2026, 2, 15),
            100000,
            120000,
            "EURUSD-SPOT-2026-02-15",
        ),
        (
            f"CONTRACT_LIABILITY:{_event(5)}",
            date(2026, 3, 10),
            100000,
            125000,
            "EURUSD-SPOT-2026-03-10",
        ),
    ]
    for book in ("ASC606", "IFRS15"):
        state, _ = _run(_context(book=book, months=3), flows, rates, positions=positions)
        assert state.findings == ()
        assert _created(state) == expected

    # The ASC606 election reads the flow's effective date, which is the date of entry: unchanged.
    issue = _context(months=3, policies={"fx.cl_layer_date": "INVOICE_ISSUE_DATE"})
    issued, _ = _run(issue, flows, rates, positions=positions)
    assert issued.findings == ()
    assert [(move[1], move[3]) for move in _created(issued)] == [
        (date(2026, 1, 12), 110000),
        (date(2026, 1, 12), 110000),
        (date(2026, 2, 15), 120000),
        (date(2026, 3, 1), 120000),
    ]


def test_s12_r07_pro_rata_consumption() -> None:
    ctx = _context(months=3, policies={"fx.cl_layer_consumption": "PRO_RATA"})
    flows = [
        _invoice(2, date(2026, 1, 1), "6000.00"),
        _invoice(3, date(2026, 2, 1), "3000.00"),
        _release(SERVICES, date(2026, 2, 28), "1000.00"),
    ]
    rates = [_spot(date(2026, 1, 1), "1.1000"), _spot(date(2026, 2, 1), "1.2000")]
    state, trace = _run(ctx, flows, rates)

    first, second = f"CONTRACT_LIABILITY:{_event(2)}", f"CONTRACT_LIABILITY:{_event(3)}"
    assert largest_remainder(
        100000, [to_fraction(600000), to_fraction(300000)], [first, second]
    ) == [
        66667,
        33333,
    ]
    assert [
        (m.layer_key, m.amount_txn, m.amount_functional)
        for m in _moves(state, "LIABILITY_LAYER_CONSUMED")
    ] == [
        (first, 66667, 73334),
        (second, 33333, 40000),
    ]
    node = _node(trace, _moves(state, "LIABILITY_LAYER_CONSUMED")[1].trace_node_id)
    assert (node.formula_id, node.params["weights"], node.params["index"]) == (
        "fx.layer.consume.pro_rata.v1",
        "600000|300000",
        "1",
    )

    # A tie goes to the smaller layer key, not to the older layer.
    tie = [
        _invoice(9, date(2026, 1, 1), "1.00"),
        _invoice(2, date(2026, 1, 2), "1.00"),
        _release(SERVICES, date(2026, 1, 31), "0.01"),
    ]
    tie_rates = [_spot(date(2026, 1, 1), "1.1000")]
    pro_rata, _ = _run(ctx, tie, tie_rates)
    assert [
        (m.layer_key, m.amount_txn, m.amount_functional)
        for m in _moves(pro_rata, "LIABILITY_LAYER_CONSUMED")
    ] == [(f"CONTRACT_LIABILITY:{_event(2)}", 1, 1)]
    fifo, _ = _run(_context(months=3), tie, tie_rates)
    assert [m.layer_key for m in _moves(fifo, "LIABILITY_LAYER_CONSUMED")] == [
        f"CONTRACT_LIABILITY:{_event(9)}"
    ]


def test_s12_r08_credit_memo_settlement_difference() -> None:
    ctx, flows, rates = _credit_memos()
    state, trace = _run(ctx, flows, rates)

    layer = f"CONTRACT_LIABILITY:{_event(2)}"
    assert [m.amount_functional for m in _moves(state, "LIABILITY_LAYER_CONSUMED", layer)] == [
        44000,
        11000,
        55000,
    ]
    differences = [
        _node(trace, f"fx_credit_memo_difference:{_event(v)}#CREDIT_MEMO@{CONTRACT}:{period}")
        for v, period in ((3, "FY2026-P02"), (4, "FY2026-P03"), (5, "FY2026-P03"))
    ]
    # 400.00 at 1.15 = 460.00 against 440.00; 100.00 at 1.05 = 105.00 against 110.00; 500.00
    # relieved at 1.08 = 540.00 against 550.00.
    assert [node.value for node in differences] == ["20.00", "-5.00", "-10.00"]
    assert differences[0].inputs[1:] == (
        _moves(state, "LIABILITY_LAYER_CONSUMED", layer)[0].trace_node_id,
    )
    target = f"{UNIT}#JET-10c#CONTRACT_LIABILITY"
    assert _cumulative(state, "fx_remeasurement_cum", target) == {
        "FY2026-P02": 2000,
        "FY2026-P03": 500,
    }
    jet_10c = [t for t in state.remeasurement_targets if t.period_key == "FY2026-P03"]
    assert [(t.part, t.balance_role, t.amount_txn) for t in jet_10c] == [
        ("JET-10c", "CONTRACT_LIABILITY", 0)
    ]
    # A credit memo beyond the open liability creates an asset layer at spot (S12-R-06).
    assert _created(state, "ASSET_LAYER_CREATED") == [
        (f"CONTRACT_ASSET:{_event(5)}", date(2026, 3, 20), 10000, 10800, "EURUSD-SPOT-2026-03-20")
    ]


def test_fx_001_currency_roles_and_rate_ids() -> None:
    for ctx, flows, rates in (_chk_080(), _credit_memos()):
        state, _ = _run(ctx, flows, rates)
        pinned = {(rate.rate_key, rate.version_key): to_fraction(rate.rate) for rate in rates}
        targets = state.functional_targets + state.remeasurement_targets
        assert targets
        for target in targets:
            assert (target.txn_currency, target.functional_currency) == ("EUR", "USD")
            assert isinstance(target.amount_txn, int) and isinstance(target.amount_functional, int)
            assert target.rates
            assert {(ref.rate_key, ref.version_key) for ref in target.rates} <= set(pinned)
        for move in state.layer_movements:
            assert (move.txn_currency, move.functional_currency) == ("EUR", "USD")
            assert pinned[(move.rate_key, move.version_key)] == move.rate
    state, _ = _run(*_chk_080())
    december = next(t for t in state.functional_targets if t.period_key == "FY2026-P12")
    assert (december.amount_txn, december.amount_functional) == (1200000, 1380000)
    assert [(ref.rate_key, ref.version_key) for ref in december.rates] == [
        ("EURUSD-SPOT-2026-01-01", RATE_SET),
        ("EURUSD-SPOT-2026-07-01", RATE_SET),
    ]


def _net_positions(
    flows: Sequence[ControlFlow], periods: Sequence[str]
) -> dict[tuple[str, str], int]:
    """NP = cumulative credits − cumulative debits through each period end (S10-INV-05, D-12)."""
    positions = {}
    for period in periods:
        year, month = int(period[2:6]), int(period[-2:])
        end = month_end(date(year, month, 1))
        net = 0
        for flow in flows:
            if flow.effective_date <= end:
                net += flow.amount if flow.side == "CREDIT" else -flow.amount
        positions[(ENTITY, period)] = net
    return positions


def test_s12_inv_03_layers_equal_net_position() -> None:
    ctx, flows, rates = _chk_080()
    positions = _net_positions(flows, YEAR_2026)
    state, _ = _run(ctx, flows, rates, positions=positions)
    assert state.findings == ()
    for period in YEAR_2026:
        net = sum(
            b.txn_open if b.balance_role == "CONTRACT_LIABILITY" else -b.txn_open
            for b in state.layer_balances
            if b.period_key == period
        )
        assert net == positions[(ENTITY, period)], period
    assert positions[(ENTITY, "FY2026-P06")] == 0

    wrong = {**positions, (ENTITY, "FY2026-P03"): positions[(ENTITY, "FY2026-P03")] + 1}
    state, _ = _run(ctx, flows, rates, positions=wrong)
    assert [
        (f.code, f.severity, f.subject_key, f.detail["rule"], f.detail["period_key"])
        for f in state.findings
    ] == [("ENGINE_INVARIANT_VIOLATION", "ERROR", UNIT, "S12-INV-03", "FY2026-P03")]
