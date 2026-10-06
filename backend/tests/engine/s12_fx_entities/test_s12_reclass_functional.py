"""S12-R-09: the functional amounts of the netting reclass (ENGINE_SPEC_B §12.2.3, Table 14-A row
JET-06; lane L5-5, LATE-POL-181).

Stage 14 builds the JET-06 part target of every reclass attribution, but stage 12 published no
functional amount for it, so any foreign-currency group with a debit position raised
``ENGINE_INVARIANT_VIOLATED`` "stage 12 publishes no functional amount for a foreign-currency part
target". Stage 12 now apportions the remeasured carrying of the open contract-asset layers over
the period's attributions by largest remainder and publishes cumulative targets, as stage 14
accumulates the attributions. The world: US01 (functional USD) recognises EUR 5,000.00 on the
licence and EUR 1,000.00 on services on 20 January 2026 without billing; average January 1.1100,
closing January 1.1200 and February 1.1400. Every trace re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import FxRateInput
from erev_engine.dates import month_end
from erev_engine.enums import BookCode
from erev_engine.stages import s12_fx_entities
from erev_engine.stages.s12_fx_entities import ControlFlow, FxFlows, FxState
from erev_engine.stages.s14_posting import PartInputs
from erev_engine.stages.state import AllocatedState, BookContext, RateIndex, Target
from erev_engine.trace import SourceRef, Trace, TraceBuilder, TraceNode, reevaluate
from support import bundles
from support.recognition import CONTRACT_KEY, allocated_state, book_context, usd

ENTITY = bundles.ENTITY_CODE
UNIT = f"CG-1@{ENTITY}"
LICENCE = f"{CONTRACT_KEY}/L"
SERVICES = f"{CONTRACT_KEY}/S"
RATE_SET = "EURUSD-PUBLISHED@v1"
JANUARY, FEBRUARY = "FY2026-P01", "FY2026-P02"
MEASURE = "netting_reclass_amount"


@dataclass(frozen=True, slots=True)
class _Costs:
    """The consumed state as stage 12 reads it from the book loop (``CostsView``)."""

    allocated: AllocatedState
    fx_flows: FxFlows
    part_inputs: PartInputs


def _context() -> BookContext:
    calendar = bundles.entity(months=2, books=("ASC606",))
    ctx = book_context(calendar, book_code="ASC606", currency="EUR")
    return dataclasses.replace(ctx, currencies=bundles.currencies("EUR", "USD"))


def _rate(kind: str, on: date, rate: str) -> FxRateInput:
    if kind == "spot":
        key = f"EURUSD-SPOT-{on.isoformat()}"
        return FxRateInput(key, RATE_SET, "spot", "EUR", "USD", on, None, Decimal(rate))
    period_key = f"FY{on.year}-P{on.month:02d}"
    key = f"EURUSD-{kind.upper()}-{period_key}"
    return FxRateInput(key, RATE_SET, kind, "EUR", "USD", month_end(on), period_key, Decimal(rate))


RATES = (
    _rate("spot", date(2026, 1, 20), "1.1100"),
    _rate("average", date(2026, 1, 1), "1.1100"),
    _rate("closing", date(2026, 1, 1), "1.1200"),
    _rate("average", date(2026, 2, 1), "1.1300"),
    _rate("closing", date(2026, 2, 1), "1.1400"),
)


def _attribution(tb: TraceBuilder, subject: str, role: str, period: str, amount: str) -> Target:
    """A stage 10 attribution (§10.2.7) whose node reads its value from a source record."""
    node = tb.node(
        measure=MEASURE,
        subject_key=subject,
        period_key=period,
        value=usd(amount),
        currency="EUR",
        minor_unit=2,
        formula_id="fx.gain_loss.sum.v1",
        inputs=[SourceRef("source_record", f"{subject}@{period}", {"value": amount})],
        params={"signs": "1"},
        narrative_key="fx.gain_loss.sum",
    )
    return Target(BookCode.ASC606, ENTITY, subject, MEASURE, period, role, usd(amount), None, node)


def _run(ctx: BookContext) -> tuple[FxState, Trace]:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    flows = FxFlows(
        (
            ControlFlow("REVENUE", ENTITY, LICENCE, f"{CONTRACT_KEY}/EV-000003", date(2026, 1, 20),
                        3, usd("5000.00")),
            ControlFlow("REVENUE", ENTITY, SERVICES, f"{CONTRACT_KEY}/EV-000004", date(2026, 1, 20),
                        4, usd("1000.00")),
        ),
    )  # fmt: skip
    reclass = tuple(
        _attribution(tb, subject, role, period, amount)
        for period in (JANUARY, FEBRUARY)
        for subject, role, amount in (
            (LICENCE, "CONTRACT_ASSET", "5000.00"),
            (SERVICES, "UNBILLED_RECEIVABLE", "1000.00"),
        )
    )
    costs = _Costs(allocated_state([]), flows, PartInputs(reclass=reclass))
    state = s12_fx_entities.run(ctx, costs, tb, rates=RateIndex(RATES))
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def test_s12_r09_reclass_uses_remeasured_carrying() -> None:
    state, trace = _run(_context())
    assert not state.findings
    # Closing January 1.1200: 5,600.00 + 1,120.00; February 1.1400: 5,700.00 + 1,140.00.
    assert _node(trace, f"fx_asset_carrying:{UNIT}:{JANUARY}").value == "6720.00"
    assert _node(trace, f"fx_asset_carrying:{UNIT}:{FEBRUARY}").value == "6840.00"
    shares = {
        (node.id.split(":")[1], node.id.split(":")[2]): node.value
        for node in trace.nodes
        if node.measure == "fx_reclass_share"
    }
    assert shares == {
        (f"{LICENCE}#CONTRACT_ASSET", JANUARY): "5600.00",
        (f"{SERVICES}#UNBILLED_RECEIVABLE", JANUARY): "1120.00",
        (f"{LICENCE}#CONTRACT_ASSET", FEBRUARY): "5700.00",
        (f"{SERVICES}#UNBILLED_RECEIVABLE", FEBRUARY): "1140.00",
    }
    cumulative = {
        (target.subject_key, target.balance_role, target.period_key): (
            target.amount_txn,
            target.amount_functional,
        )
        for target in state.functional_targets
        if target.measure == MEASURE
    }
    # Stage 14 accumulates the attributions into the JET-06 part target (S14-R-07).
    assert cumulative == {
        (f"{LICENCE}#CONTRACT_ASSET", "CONTRACT_ASSET", JANUARY): (500000, 560000),
        (f"{LICENCE}#CONTRACT_ASSET", "CONTRACT_ASSET", FEBRUARY): (1000000, 1130000),
        (f"{SERVICES}#UNBILLED_RECEIVABLE", "UNBILLED_RECEIVABLE", JANUARY): (100000, 112000),
        (f"{SERVICES}#UNBILLED_RECEIVABLE", "UNBILLED_RECEIVABLE", FEBRUARY): (200000, 226000),
    }


def test_s12_r09_same_currency_publishes_nothing() -> None:
    ctx = dataclasses.replace(_context(), txn_currency="USD")
    state, trace = _run(ctx)
    assert [target for target in state.functional_targets if target.measure == MEASURE] == []
    assert not any(node.measure.startswith("fx_reclass") for node in trace.nodes)
