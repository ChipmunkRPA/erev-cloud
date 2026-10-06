"""S11-R-06 straight-line amortisation over a ``MONTHLY`` calendar reads calendar months (lane L5-5,
MOD-FS-09, COST-CAP).

POLICIES ALG-11 (inputs: the entity's periods, "04 E-50 calendar pattern"; rule 3) and ENGINE_SPEC_B
C-04. Stage 09 already evaluates time elapsed over calendar months when the performing entity's
calendar pattern is ``MONTHLY`` (``progress_time.calendar_of``). Stage 11 passed the entity's
periods instead. Bundle assembly supplies periods only through the horizon (CV-12, RCP-15), while an
asset amortises to its end date (S11-R-03), for example 36 months. ``covering_periods`` then raised
``ENGINE_INVARIANT_VIOLATED`` "no accounting period of the entity contains the date" at the first
period-end test. Now a ``MONTHLY`` calendar gives calendar months, and the node carries no
``periods`` param, so the trace re-evaluates. COST-CAP figures: a commission of 30,000.00
capitalised on 10 January 2026, amortised over 36 months from 1 January 2026 (``MONTHLY_EVEN``).
No database.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import EntityInput, EstimateVersionInput
from erev_engine.stages import s09_recognition, s10_billing_balances, s11_costs_loss
from erev_engine.stages.s11_costs_loss import CostLossState
from erev_engine.stages.state import EstimatePin, EstimatePins, EventView
from erev_engine.trace import Trace, TraceBuilder, reevaluate
from support.bundles import INCEPTION, entity
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    emit_catch_up_nodes,
    estimate_version,
    event_view,
    obligation,
    segment,
    usd,
)

MONTHLY_EVEN = ("recognition.time_convention", "ENTITY", "US01", "MONTHLY_EVEN")
ASSET = f"{CONTRACT_KEY}/EV-000003"


def _renewal() -> EstimatePins:
    version: EstimateVersionInput = dataclasses.replace(
        estimate_version(f"{CONTRACT_KEY}/AMORT", "RENEWAL_EXPECTATION", 1, INCEPTION),
        amortization_months=36,
    )
    order_key = (version.effective_date, 2, f"{CONTRACT_KEY}/EV-000002")
    return EstimatePins({version.estimate_key: (EstimatePin(version, order_key),)})


def _commission() -> EventView:
    payload: dict[str, object] = {
        "purpose": "COST_TO_OBTAIN",
        "amount": Decimal("30000.00"),
        "plan_code": "AE-2026",
        "is_incremental": True,
    }
    return event_view(CONTRACT_KEY, 3, "COST_INCURRED", date(2026, 1, 10), payload)


def _run(calendar: EntityInput) -> tuple[CostLossState, Trace]:
    ctx = book_context(calendar, overrides=[MONTHLY_EVEN])
    services = segment(
        Fraction(Decimal("120000")), usd("120000"), start=INCEPTION, end=date(2026, 12, 31)
    )
    ob = obligation("P1", [services], convention="MONTHLY_EVEN")
    st = allocated_state([ob], events=[_commission()], estimates=_renewal())
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(tb, ctx, st)
    recognition = s09_recognition.run(ctx, st, tb)
    balances = s10_billing_balances.run(ctx, recognition, tb)
    state = s11_costs_loss.run(ctx, balances, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state, trace


def test_amortisation_beyond_the_monthly_calendar_uses_calendar_months() -> None:
    # Calendar January to December 2026, the obligation's term and the horizon; the asset amortises
    # to 31 December 2028.
    state, trace = _run(entity(months=12))
    (spec,) = state.cost_asset_specs
    assert (spec.amortization_start_date, spec.amortization_end_date) == (
        INCEPTION,
        date(2028, 12, 31),
    )
    january = state.cost_asset_measures[(ASSET, "FY2026-P01")]
    june = state.cost_asset_measures[(ASSET, "FY2026-P06")]
    # 30,000.00 × 1 ÷ 36 = 833.33 by cumulative rounding; 6 ÷ 36 gives 5,000.00 through June.
    assert (january.amortized_cum, january.carrying_amount) == (usd("833.33"), usd("29166.67"))
    assert (june.amortized_cum, june.carrying_amount) == (usd("5000.00"), usd("25000.00"))
    node = next(n for n in trace.nodes if n.id == f"cost_amortised_cum:{ASSET}:FY2026-P01")
    assert node.formula_id == "cost.amortise.straight_line.v1"
    assert "periods" not in node.params


def test_a_calendar_through_the_asset_end_gives_the_same_amounts() -> None:
    short, _ = _run(entity(months=12))
    long, _ = _run(entity(months=36))
    for period in ("FY2026-P01", "FY2026-P02", "FY2026-P06"):
        assert (
            short.cost_asset_measures[(ASSET, period)].amortized_cum
            == long.cost_asset_measures[(ASSET, period)].amortized_cum
        )
