"""Stage 12 performing and contracting entities, intercompany pairs and reporting translation.

ENGINE_SPEC_B §12.2.5 and §12.2.6 (S12-R-14 to S12-R-18), §12.3 (S12-INV-05, S12-INV-07), §12.5 and
§12.7 EX-12-A; POLICIES ALG-07 §2.8 (CHK-070, CHK-071), POL-170, POL-171 and JET-13; REQ-ENT-001 to
REQ-ENT-004 and REQ-FX-005. Stages 10 and 11 are built in lane L2-4, so the tests pass a fake
consumed state carrying ``FxFlows`` (D-81 integration after merge; L2-5-Q-10). Golden Contract 2
replays stages 01 to 05, and stage 09 runs for the S12-R-17 calendars. Every trace re-evaluates
node for node (DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION, dates
from erev_engine.bundle import EntityInput, FxRateInput, InputBundle, PeriodInput
from erev_engine.dates import add_months, month_end
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
    s09_recognition,
    s12_fx_entities,
)
from erev_engine.stages.s12_fx_entities import (
    ControlFlow,
    FunctionalLine,
    FxFlows,
    FxState,
    translate_to_reporting,
)
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    ObligationState,
    PolicyResolver,
    RateIndex,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder, TraceNode, reevaluate
from support import bundles, golden_streams
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    obligation,
    segment,
    usd,
)

US, UK, DE = "US01", "UK01", "DE01"
MOCK_1, MOCK_2 = "Mock Entity 1", "Mock Entity 2"
RATE_SET = "FX-PUBLISHED@v1"
SERVICES = f"{CONTRACT_KEY}/S"
LICENCE = f"{CONTRACT_KEY}/L"


@dataclass(frozen=True, slots=True)
class _Costs:
    """A fake stage 11 output as stage 12 reads it (L2-5-Q-10)."""

    allocated: AllocatedState
    fx_flows: FxFlows


def _context(
    calendars: Sequence[EntityInput],
    *,
    currency: str,
    policies: Mapping[str, str] | None = None,
    preset: str = "DEFAULT",
) -> BookContext:
    """One book over several entities: every calendar, horizon and PERIOD policy value (CV-17)."""
    ctx = book_context(calendars[0], currency=currency, preset=preset)
    resolved = {(p.code, p.scope, p.subject_key): p for p in ctx.policies.all()}
    for calendar in calendars[1:]:
        for policy in bundles.policy_set(preset, entity=calendar):
            resolved.setdefault((policy.code, policy.scope, policy.subject_key), policy)
    for code, value in (policies or {}).items():
        keys = [key for key in resolved if key[0] == code]
        assert keys, code
        for key in keys:
            resolved[key] = dataclasses.replace(
                resolved[key], value=value, level="T", source_ref="OVR-TEST"
            )
    codes = {calendar.functional_currency for calendar in calendars} | {currency}
    return dataclasses.replace(
        ctx,
        currencies=bundles.currencies(*codes),
        entities={calendar.code: calendar for calendar in calendars},
        horizon={calendar.code: calendar.periods[-1].period_key for calendar in calendars},
        policies=PolicyResolver(tuple(resolved[key] for key in sorted(resolved))),
    )


def _spot(base: str, quote: str, on: date, rate: str) -> FxRateInput:
    key = f"{base}{quote}-SPOT-{on.isoformat()}"
    return FxRateInput(key, RATE_SET, "spot", base, quote, on, None, Decimal(rate))


def _period_rate(
    kind: str, base: str, quote: str, period_key: str, end: date, rate: str
) -> FxRateInput:
    key = f"{base}{quote}-{kind.upper()}-{period_key}"
    return FxRateInput(key, RATE_SET, kind, base, quote, end, period_key, Decimal(rate))


def _monthly(kind: str, base: str, quote: str, rates: Mapping[int, str]) -> list[FxRateInput]:
    return [
        _period_rate(
            kind, base, quote, f"FY2026-P{month:02d}", month_end(date(2026, month, 1)), rate
        )
        for month, rate in rates.items()
    ]


def _event_key(stream_version: int) -> str:
    return f"{CONTRACT_KEY}/EV-{stream_version:06d}"


def _invoice(stream_version: int, issued: date, amount: str) -> ControlFlow:
    """A noncancellable invoice of the contracting entity US01 (S12-R-04)."""
    return ControlFlow(
        "BILLING",
        US,
        f"{CONTRACT_KEY}@{US}",
        _event_key(stream_version),
        issued,
        stream_version,
        usd(amount),
        unconditional_date=issued,
    )


def _release(subject: str, on: date, amount: str, *, period_key: str | None = None) -> ControlFlow:
    """A time-driven revenue release of US01 at a period end (``record_seq`` None)."""
    source = f"{subject}@{period_key or f'FY{on.year}-P{on.month:02d}'}"
    return ControlFlow("REVENUE", US, subject, source, on, None, usd(amount))


def _on_event(kind: str, stream_version: int, on: date, amount: str, subject: str) -> ControlFlow:
    return ControlFlow(
        kind, US, subject, _event_key(stream_version), on, stream_version, usd(amount)
    )


def _obligation(
    key: str,
    performing: str,
    *,
    start: date = date(2026, 1, 1),
    end: date = date(2026, 3, 31),
    amount: str = "3000.00",
) -> ObligationState:
    """An obligation contracted by US01 and performed by ``performing`` (T-CON-10 entities)."""
    minor = usd(amount)
    ob = obligation(
        key,
        [segment(Fraction(minor, 100), minor, start=start, end=end)],
        convention="MONTHLY_EVEN",
        start=start,
        end=end,
        entity_code=US,
    )
    return dataclasses.replace(ob, performing_entity=performing)


def _run(
    ctx: BookContext,
    allocated: AllocatedState,
    flows: Iterable[ControlFlow],
    rates: Iterable[FxRateInput],
    *,
    positions: Mapping[tuple[str, str], int] | None = None,
) -> tuple[FxState, Trace]:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    costs = _Costs(allocated, FxFlows(tuple(flows), dict(positions or {})))
    state = s12_fx_entities.run(ctx, costs, tb, rates=RateIndex(tuple(rates)))
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _pairs(state: FxState) -> list[tuple[object, ...]]:
    return [
        (
            pair.obligation,
            pair.contracting_entity,
            pair.performing_entity,
            pair.contracting_period_key,
            pair.performing_period_key,
            pair.amount_txn,
            pair.amount_contracting,
            pair.amount_performing,
        )
        for pair in state.ic_pairs
    ]


def _cumulative(state: FxState, measure: str, subject: str) -> dict[str, int]:
    return {
        target.period_key: target.amount_functional
        for target in state.functional_targets + state.remeasurement_targets
        if target.measure == measure and target.subject_key == subject
    }


def _balances(state: FxState, period_key: str) -> list[tuple[str, str, str, int, int]]:
    return [
        (b.entity, b.layer_key, b.balance_role, b.txn_open, b.fn_carrying)
        for b in state.layer_balances
        if b.period_key == period_key
    ]


def _ex_12_a() -> tuple[FxState, Trace]:
    us = bundles.entity(US, months=4)
    uk = bundles.entity(UK, functional_currency="GBP", months=4)
    ctx = _context([us, uk], currency="EUR")
    licence = _obligation("L", US, start=date(2026, 3, 15), end=date(2026, 3, 15), amount="1500.00")
    allocated = allocated_state([_obligation("S", UK), licence])
    flows = [
        _invoice(1, date(2026, 1, 1), "3000.00"),
        _release(SERVICES, date(2026, 1, 31), "1000.00"),
        _release(SERVICES, date(2026, 2, 28), "1000.00"),
        _on_event("REVENUE", 5, date(2026, 3, 15), "1500.00", LICENCE),
        _release(SERVICES, date(2026, 3, 31), "1000.00"),
        _invoice(6, date(2026, 4, 20), "1500.00"),
    ]
    rates = [
        _spot("EUR", "USD", date(2026, 1, 1), "1.123456"),
        _spot("EUR", "USD", date(2026, 4, 20), "1.1450"),
        *_monthly("average", "EUR", "USD", {3: "1.1350"}),
        *_monthly("closing", "EUR", "USD", {3: "1.1400"}),
        *_monthly("average", "EUR", "GBP", {1: "0.8612", 2: "0.8655", 3: "0.8700"}),
    ]
    return _run(ctx, allocated, flows, rates)


def test_ex_12_a_layers_asset_layers_and_pairs() -> None:
    state, trace = _ex_12_a()
    assert state.findings == ()
    # Pair amounts: US reliefs and the A2 asset layer against UK revenue at its average rates.
    assert _pairs(state) == [
        (SERVICES, US, UK, "FY2026-P01", "FY2026-P01", 100000, 112346, 86120),
        (SERVICES, US, UK, "FY2026-P02", "FY2026-P02", 100000, 112345, 86550),
        (SERVICES, US, UK, "FY2026-P03", "FY2026-P03", 100000, 113500, 87000),
    ]
    # The licence is performed by the contracting entity: US revenue, no pair.
    assert _cumulative(state, "revenue_cum", LICENCE) == {
        "FY2026-P03": 169096,
        "FY2026-P04": 169096,
    }
    # 31 March: A1 + A2 of EUR 1,500.00 remeasured from 1,702.50 to 1,710.00 (JET-10a 7.50); the
    # JET-06 contract asset is their carrying amount, 1,710.00.
    a1, a2 = f"CONTRACT_ASSET:{_event_key(5)}", f"CONTRACT_ASSET:{SERVICES}@FY2026-P03"
    assert _balances(state, "FY2026-P03") == [
        (US, a1, "CONTRACT_ASSET", 50000, 57000),
        (US, a2, "CONTRACT_ASSET", 100000, 114000),
    ]
    remeasured = [
        move.amount_functional
        for move in state.layer_movements
        if move.movement_kind == "ASSET_LAYER_REMEASURED" and move.reason == "PERIOD_END"
    ]
    assert remeasured == [250, 500]
    # 20 April: the invoice at spot 1.1450 settles both layers with a gain of 7.50.
    assert _cumulative(state, "fx_remeasurement_cum", f"CG-1@{US}#JET-10a#CONTRACT_ASSET") == {
        "FY2026-P03": 750,
        "FY2026-P04": 1500,
    }
    assert _balances(state, "FY2026-P04") == []
    # Totals: US FX gain 15.00; intercompany pairs EUR 3,000.00; UK revenue GBP 2,596.70.
    assert [(t.period_key, t.amount_functional) for t in state.gain_loss_targets][-1] == (
        "FY2026-P04",
        1500,
    )
    assert sum(pair.amount_txn for pair in state.ic_pairs) == 300000
    assert sum(pair.amount_performing for pair in state.ic_pairs) == 259670
    # Balances, layers and targets belong to the contracting entity (S12-R-14).
    assert {move.entity for move in state.layer_movements} == {US}
    assert {target.entity for target in state.functional_targets} == {US}
    # S12-INV-05: each entity's JET-13 entries balance in both currencies from one amount each.
    entries: dict[str, list[tuple[int, int]]] = {US: [], UK: []}
    for pair in state.ic_pairs:
        assert (pair.txn_currency, pair.contracting_currency, pair.performing_currency) == (
            "EUR",
            "USD",
            "GBP",
        )
        entries[US] += [(pair.amount_txn, pair.amount_contracting)]  # Dr CONTRACT_LIABILITY
        entries[US] += [(-pair.amount_txn, -pair.amount_contracting)]  # Cr INTERCOMPANY_DUE_TO
        entries[UK] += [(pair.amount_txn, pair.amount_performing)]  # Dr INTERCOMPANY_DUE_FROM
        entries[UK] += [(-pair.amount_txn, -pair.amount_performing)]  # Cr REVENUE
    for lines in entries.values():
        assert sum(txn for txn, _ in lines) == 0 and sum(fn for _, fn in lines) == 0
    # Nodes of §12.5 at subject <obligation>@<contracting entity>><performing entity>.
    january, _, march = state.ic_pairs
    performing = _node(trace, january.performing_node_id)
    assert (
        january.performing_node_id
        == f"ic_pair_functional_performing:{SERVICES}@US01>UK01:FY2026-P01"
    )
    assert (performing.formula_id, performing.value, performing.currency) == (
        "ent.performing_revenue_rate.v1",
        "861.20",
        "GBP",
    )
    (rate,) = performing.inputs
    assert isinstance(rate, SourceRef)
    assert (rate.ref_type, rate.ref_id, rate.detail["value"]) == (
        "fx_rate",
        "EURGBP-AVERAGE-FY2026-P01",
        "0.8612",
    )
    assert january.performing_rates[0].rate_key == "EURGBP-AVERAGE-FY2026-P01"
    created = next(
        move.trace_node_id
        for move in state.layer_movements
        if move.layer_key == a2 and move.movement_kind == "ASSET_LAYER_CREATED"
    )
    contracting = _node(trace, march.contracting_node_id)
    assert (contracting.formula_id, contracting.value, contracting.inputs) == (
        "ent.pair.v1",
        "1135.00",
        (created,),
    )
    assert _node(trace, march.txn_node_id).value == "1000.00"


def _chk_070(*, invoiced: bool, policies: Mapping[str, str] | None = None) -> tuple[FxState, Trace]:
    us = bundles.entity(US, months=2)
    uk = bundles.entity(UK, months=2)  # one currency: every functional currency is USD
    ctx = _context([us, uk], currency="USD", policies=policies)
    allocated = allocated_state(
        [
            _obligation("L1-LICENCE", US, amount="60000.00"),
            _obligation("L2-SERVICES", UK, amount="40000.00"),
        ]
    )
    flows = [_invoice(2, date(2026, 1, 1), "100000.00")] if invoiced else []
    flows += [
        _on_event("REVENUE", 3, date(2026, 1, 15), "60000.00", f"{CONTRACT_KEY}/L1-LICENCE"),
        _on_event("REVENUE", 4, date(2026, 1, 31), "20000.00", f"{CONTRACT_KEY}/L2-SERVICES"),
    ]
    position = 2000000 if invoiced else -8000000
    return _run(ctx, allocated, flows, [], positions={(US, "FY2026-P01"): position})


def test_chk_070_intercompany_pair() -> None:
    state, trace = _chk_070(invoiced=True)
    assert state.findings == ()
    licence, services = f"{CONTRACT_KEY}/L1-LICENCE", f"{CONTRACT_KEY}/L2-SERVICES"
    # US revenue relief of the licence (JET-02).
    assert _cumulative(state, "revenue_cum", licence)["FY2026-P01"] == 6000000
    # US JET-13 Dr CL 20,000.00 / Cr INTERCOMPANY_DUE_TO (UK); UK Dr INTERCOMPANY_DUE_FROM (US)
    # 20,000.00 / Cr REVENUE 20,000.00.
    assert _pairs(state) == [
        (services, US, UK, "FY2026-P01", "FY2026-P01", 2000000, 2000000, 2000000)
    ]
    (pair,) = state.ic_pairs
    assert (pair.contracting_rates, pair.performing_rates) == ((), ())
    assert pair.subject_key == f"{services}@US01>UK01"
    assert _node(trace, pair.performing_node_id).params["rate_inputs"] == "false"
    # End of P1: US contract liability 20,000.00; UK holds no contract balance.
    assert _balances(state, "FY2026-P01") == [
        (US, f"CONTRACT_LIABILITY:{_event_key(2)}", "CONTRACT_LIABILITY", 2000000, 2000000)
    ]
    assert {move.entity for move in state.layer_movements} == {US}
    # POL-170 CONTRACTING_ENTITY: US revenue 80,000.00, no intercompany lines.
    contracting, _ = _chk_070(invoiced=True, policies={"ic.revenue_entity": "CONTRACTING_ENTITY"})
    assert contracting.ic_pairs == ()
    assert (
        _cumulative(contracting, "revenue_cum", licence)["FY2026-P01"]
        + _cumulative(contracting, "revenue_cum", services)["FY2026-P01"]
    ) == 8000000


def test_chk_071_contract_asset_held_by_contracting_entity() -> None:
    state, _ = _chk_070(invoiced=False)
    # US NP (80,000.00), presented as a US contract asset of 80,000.00; S12-INV-03 holds.
    assert state.findings == ()
    assert _balances(state, "FY2026-P01") == [
        (US, f"CONTRACT_ASSET:{_event_key(3)}", "CONTRACT_ASSET", 6000000, 6000000),
        (US, f"CONTRACT_ASSET:{_event_key(4)}", "CONTRACT_ASSET", 2000000, 2000000),
    ]
    # UK revenue 20,000.00 and due-from 20,000.00; no balance exists for UK (S10-INV-08).
    (pair,) = state.ic_pairs
    assert (pair.performing_entity, pair.amount_txn, pair.amount_performing) == (
        UK,
        2000000,
        2000000,
    )
    assert all(balance.entity == US for balance in state.layer_balances)


def test_s12_inv_07_pairs_agree() -> None:
    us = bundles.entity(US, months=3)
    uk = bundles.entity(UK, functional_currency="GBP", months=3)
    de = bundles.entity(DE, functional_currency="EUR", months=3)
    ctx = _context([us, uk, de], currency="EUR")
    a, b, c = f"{CONTRACT_KEY}/A", f"{CONTRACT_KEY}/B", f"{CONTRACT_KEY}/C"
    allocated = allocated_state(
        [_obligation("A", UK), _obligation("B", DE), _obligation("C", US, amount="800.00")]
    )
    flows = [
        _invoice(1, date(2026, 1, 1), "5000.00"),
        *(_release(a, month_end(date(2026, month, 1)), "1000.00") for month in (1, 2, 3)),
        _on_event("REVENUE", 2, date(2026, 2, 10), "1500.00", b),
        _on_event("NEGATIVE_REVENUE", 3, date(2026, 3, 20), "500.00", b),
        _on_event("REVENUE", 4, date(2026, 3, 31), "800.00", c),
    ]
    rates = [
        _spot("EUR", "USD", date(2026, 1, 1), "1.1000"),
        *_monthly("average", "EUR", "GBP", {1: "0.8600", 2: "0.8700", 3: "0.8800"}),
    ]
    state, _ = _run(ctx, allocated, flows, rates)
    assert state.findings == ()
    due_to: dict[tuple[str, str, str], int] = {}
    due_from: dict[tuple[str, str, str], int] = {}
    for pair in state.ic_pairs:
        head = (pair.contracting_entity, pair.performing_entity)
        key = (*head, pair.contracting_period_key)
        due_to[key] = due_to.get(key, 0) + pair.amount_txn
        key = (*head, pair.performing_period_key)
        due_from[key] = due_from.get(key, 0) + pair.amount_txn
    assert (
        due_to
        == due_from
        == {
            (US, UK, "FY2026-P01"): 100000,
            (US, UK, "FY2026-P02"): 100000,
            (US, UK, "FY2026-P03"): 100000,
            (US, DE, "FY2026-P02"): 150000,
            (US, DE, "FY2026-P03"): -50000,
        }
    )
    # The negative revenue of B reverses the pair: a US liability layer at spot, EUR at rate 1.
    assert _pairs(state)[-1] == (b, US, DE, "FY2026-P03", "FY2026-P03", -50000, -55000, -50000)
    # C is performed by the contracting entity: no pair.
    assert {pair.obligation for pair in state.ic_pairs} == {a, b}
    assert [pair.amount_performing for pair in state.ic_pairs if pair.obligation == a] == [
        86000,
        87000,
        88000,
    ]


def _fold(bundle: InputBundle) -> tuple[BookContext, AllocatedState]:
    """Stages 01 to 05 of one book (§0.3), as ``tests/engine/s05_allocation`` folds them."""
    book = bundle.books[0]
    ctx = BookContext(
        book_code=BookCode(book.book_code),
        framework=BookCode(book.book_code),
        currencies=bundle.currencies,
        txn_currency=bundle.group.transaction_currency,
        entities={entity.code: entity for entity in bundle.entities},
        horizon={entity.code: entity.periods[-1].period_key for entity in bundle.entities},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=bundle.trigger,
        tenant_preset=bundle.tenant_preset,
    )
    cb = s01_canonicalize.run(bundle, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb)
    return ctx, s05_allocation.run(ctx, priced, tb)


def _cross_entity_contract_2() -> InputBundle:
    """Golden Contract 2 (step 02) with POB #1 performed by Mock Entity 1 (L2-5-Q-22)."""
    base = golden_streams.stream("Contract 2", "02").input_bundle(preset="LEGACY_PARITY")
    (calendar,) = base.entities
    other = bundles.entity(
        MOCK_1, start=calendar.periods[0].start_date, months=len(calendar.periods)
    )
    events = []
    for event in base.events:
        lines = event.payload.get("lines")
        if event.event_type == "CONTRACT_BOOKED" and isinstance(lines, list | tuple):
            relabelled: list[object] = []
            for line in lines:
                assert isinstance(line, Mapping)
                if line["obligation_key"] == "POB #1":
                    accounts = {"CONTRACT_ASSET": "15001", "CONTRACT_LIABILITY": "21001"}
                    accounts["UNBILLED_RECEIVABLE"] = "15001"
                    line = {**line, "performing_entity_code": MOCK_1, "account_overrides": accounts}
                relabelled.append(line)
            event = dataclasses.replace(event, payload={**event.payload, "lines": relabelled})
        events.append(event)
    books = []
    for book in base.books:
        merged = {(p.code, p.scope, p.subject_key): p for p in book.policies}
        for policy in bundles.policy_set("LEGACY_PARITY", book_code=book.book_code, entity=other):
            merged.setdefault((policy.code, policy.scope, policy.subject_key), policy)
        policies = tuple(merged[key] for key in sorted(merged))
        books.append(dataclasses.replace(book, entity_codes=(MOCK_1, MOCK_2), policies=policies))
    return dataclasses.replace(
        base, entities=(other, calendar), books=tuple(books), events=tuple(events)
    )


def test_ent_004_legacy_cross_entity_one_allocation() -> None:
    ctx, allocated = _fold(_cross_entity_contract_2())
    assert ctx.tenant_preset == "LEGACY_PARITY"
    assert allocated.findings == ()
    # One allocation across entities: 470.77 / 313.85 / 115.38 / 0.00 (CHK-002).
    assert [ob.obligation_key for ob in allocated.obligations] == [
        "POB #1",
        "POB #2",
        "POB #3",
        "VC #1",
    ]
    assert [ob.original_allocation.a_posted for ob in allocated.obligations] == [
        47077,
        31385,
        11538,
        0,
    ]
    assert [(ob.contracting_entity, ob.performing_entity) for ob in allocated.obligations] == [
        (MOCK_2, MOCK_1),
        (MOCK_2, MOCK_2),
        (MOCK_2, MOCK_2),
        (MOCK_2, MOCK_2),
    ]
    # Deferred-revenue and unbilled accounts are per obligation.
    assert [
        (ob.account_overrides["CONTRACT_LIABILITY"], ob.account_overrides["UNBILLED_RECEIVABLE"])
        for ob in allocated.obligations
    ] == [("21001", "15001"), ("21002", "15002"), ("21002", "15002"), ("21002", "15002")]
    # Balances and netting are per (group, contracting entity): the January delivery revenue of
    # POB #1 nets in Mock Entity 2 and pairs with Mock Entity 1 (DEV-076; S12-R-14, S12-R-15).
    first = allocated.obligations[0]
    january = dates.period_of(ctx.entities[MOCK_2], allocated.inception_date)
    flow = ControlFlow(
        "REVENUE",
        MOCK_2,
        first.subject_key,
        f"{first.subject_key}@{january.period_key}",
        january.end_date,
        None,
        5885,
    )
    state, _ = _run(ctx, allocated, [flow], [], positions={(MOCK_2, january.period_key): -5885})
    assert state.findings == ()
    assert _pairs(state) == [
        (
            first.subject_key,
            MOCK_2,
            MOCK_1,
            january.period_key,
            january.period_key,
            5885,
            5885,
            5885,
        )
    ]
    assert [(b.entity, b.balance_role, b.txn_open) for b in state.layer_balances][:1] == [
        (MOCK_2, "CONTRACT_ASSET", 5885)
    ]
    assert {balance.entity for balance in state.layer_balances} == {MOCK_2}


def _april_calendar(code: str, functional_currency: str, months: int) -> EntityInput:
    """A fiscal year starting in April: April 2026 is ``FY2027-P01`` (C-04; T-REF-05)."""
    periods = []
    for offset in range(months):
        first = add_months(date(2026, 4, 1), offset)
        periods.append(
            PeriodInput(
                period_key=f"FY2027-P{offset + 1:02d}",
                fiscal_year=2027,
                period_no=offset + 1,
                start_date=first,
                end_date=month_end(first),
                states=(("ASC606", "open"),),
            )
        )
    return EntityInput(code, functional_currency, "Europe/London", "MONTHLY", tuple(periods))


def test_s12_r17_revenue_in_performing_entity_calendar() -> None:
    us = bundles.entity(US, months=6)
    uk = _april_calendar(UK, "GBP", 3)
    ctx = _context([us, uk], currency="EUR")
    services = _obligation("S", UK, start=date(2026, 4, 1), end=date(2026, 6, 30))
    allocated = allocated_state([services], inception=date(2026, 4, 1))
    recognition = s09_recognition.run(ctx, allocated, TraceBuilder(engine_version=ENGINE_VERSION))
    # Revenue lines carry the performing entity in that entity's calendar.
    revenue = [target for target in recognition.revenue_targets if target.subject_key == SERVICES]
    assert [(t.entity, t.period_key, t.value) for t in revenue] == [
        (UK, "FY2027-P01", 100000),
        (UK, "FY2027-P02", 200000),
        (UK, "FY2027-P03", 300000),
    ]
    assert {target.entity for target in recognition.revenue_by_cause} == {UK}
    previous = 0
    flows = [_invoice(1, date(2026, 4, 1), "3000.00")]
    for target, period in zip(revenue, uk.periods, strict=True):
        amount = target.value - previous
        previous = target.value
        source = f"{SERVICES}@{period.period_key}"
        flows.append(ControlFlow("REVENUE", US, SERVICES, source, period.end_date, None, amount))
    rates = [
        _spot("EUR", "USD", date(2026, 4, 1), "1.1000"),
        *(
            _period_rate("average", "EUR", "GBP", period.period_key, period.end_date, rate)
            for period, rate in zip(uk.periods, ("0.8600", "0.8650", "0.8700"), strict=True)
        ),
    ]
    state, _ = _run(ctx, allocated, flows, rates)
    assert state.findings == ()
    # Contract-balance targets carry the contracting entity in its calendar.
    assert _cumulative(state, "revenue_cum", SERVICES) == {
        "FY2026-P04": 110000,
        "FY2026-P05": 220000,
        "FY2026-P06": 330000,
    }
    assert {target.entity for target in state.functional_targets} == {US}
    assert {move.entity for move in state.layer_movements} == {US}
    assert {balance.period_key for balance in state.layer_balances} <= {
        period.period_key for period in us.periods
    }
    # The pair dates each side in its own entity's calendar.
    assert _pairs(state) == [
        (SERVICES, US, UK, "FY2026-P04", "FY2027-P01", 100000, 110000, 86000),
        (SERVICES, US, UK, "FY2026-P05", "FY2027-P02", 100000, 110000, 86500),
        (SERVICES, US, UK, "FY2026-P06", "FY2027-P03", 100000, 110000, 87000),
    ]
    first = state.ic_pairs[0]
    assert first.contracting_node_id.endswith(":FY2026-P04")
    assert first.txn_node_id.endswith(":FY2026-P04")
    assert first.performing_node_id.endswith(":FY2027-P01")


def test_s12_r18_reporting_translation() -> None:
    calendar = bundles.entity(months=3)
    february, march = calendar.periods[1], calendar.periods[2]
    currencies = bundles.currencies("EUR", "USD")
    rates = RateIndex(
        (
            _period_rate("closing", "EUR", "USD", "FY2026-P02", date(2026, 2, 28), "1.1200"),
            _period_rate("average", "EUR", "USD", "FY2026-P03", date(2026, 3, 31), "1.123456"),
            _period_rate("closing", "EUR", "USD", "FY2026-P03", date(2026, 3, 31), "1.1400"),
        )
    )
    lines = [
        FunctionalLine("Contract liability, opening", "OPENING", 1000000),
        FunctionalLine("Billing", "FLOW", 100000),
        FunctionalLine("Revenue, POB 1", "FLOW", -33333),
        FunctionalLine("Revenue, POB 2", "FLOW", -33333),
        FunctionalLine("Revenue, POB 3", "FLOW", -33334),
        FunctionalLine("Contract liability, closing", "CLOSING", 1000000),
    ]
    view = translate_to_reporting(
        lines,
        currencies=currencies,
        functional_currency="EUR",
        reporting_currency="USD",
        rates=rates,
        period=march,
        previous_period=february,
    )
    closing_feb, average, closing = (
        "EURUSD-CLOSING-FY2026-P02",
        "EURUSD-AVERAGE-FY2026-P03",
        "EURUSD-CLOSING-FY2026-P03",
    )
    # Balances at the closing rate, flows at the average rate, a translation line (the rate effect
    # 11,400.00 − 11,200.00 − 0 × 1.123456 = 200.00) and the residue (0.01) to ROUNDING.
    assert [
        (line.kind, line.amount_functional, line.amount_reporting, line.rate_type, line.rate_key)
        for line in view.lines
    ] == [
        ("OPENING", 1000000, 1120000, "closing", closing_feb),
        ("FLOW", 100000, 112346, "average", average),
        ("FLOW", -33333, -37448, "average", average),
        ("FLOW", -33333, -37448, "average", average),
        ("FLOW", -33334, -37449, "average", average),
        ("TRANSLATION", 0, 20000, None, None),
        ("ROUNDING", 0, -1, None, None),
        ("CLOSING", 1000000, 1140000, "closing", closing),
    ]
    assert (view.period_key, view.functional_currency, view.reporting_currency) == (
        "FY2026-P03",
        "EUR",
        "USD",
    )
    assert sum(
        line.amount_reporting for line in view.lines if line.kind != "CLOSING"
    ) == view.amount("CLOSING")
    # Equal currencies: rate 1, no translation and no residue.
    same = translate_to_reporting(
        lines,
        currencies=currencies,
        functional_currency="EUR",
        reporting_currency="EUR",
        rates=RateIndex(()),
        period=march,
        previous_period=february,
    )
    assert [line.amount_reporting for line in same.lines] == [
        1000000,
        100000,
        -33333,
        -33333,
        -33334,
        0,
        0,
        1000000,
    ]
    assert {line.rate_key for line in same.lines} == {None}
    # A rollforward that does not foot, an opening without its closing rate, and a missing rate.
    with pytest.raises(ValueError, match="does not foot"):
        translate_to_reporting(
            lines[:-1],
            currencies=currencies,
            functional_currency="EUR",
            reporting_currency="USD",
            rates=rates,
            period=march,
            previous_period=february,
        )
    with pytest.raises(ValueError, match="previous period"):
        translate_to_reporting(
            lines,
            currencies=currencies,
            functional_currency="EUR",
            reporting_currency="USD",
            rates=rates,
            period=march,
        )
    with pytest.raises(EngineError) as missing:
        translate_to_reporting(
            lines,
            currencies=currencies,
            functional_currency="EUR",
            reporting_currency="USD",
            rates=RateIndex(rates.rates[:1]),
            period=march,
            previous_period=february,
        )
    assert missing.value.code == "FX_RATE_MISSING"
    assert missing.value.detail == {
        "base": "EUR",
        "period_key": "FY2026-P03",
        "quote": "USD",
        "rate_type": "average",
        "rule": "S12-R-01",
    }
