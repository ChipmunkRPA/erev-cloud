"""Stage 09 attribution of the 606-10-25-7 deposit revenue and the STEP1_MET netting (ENGINE_SPEC
S02-R-04 rev 1.6, §2.5; ENGINE_SPEC_B S14-R-25 rev 1.7; D-91 gaps (iv), (v); END-4b, ENA-2b).

``deposit_revenue_share:<obligation>:<period>`` nodes carry params ``keys``, ``weights``, ``key``
and ``basis``; the weights are the posted inception allocation A_p, else the resolved SSP, else the
stated prices, else ``TOTAL_WEIGHT_ZERO``; the netting node ``step1_netted_target`` gives
max(C_p − R25_p, 0). The states come from ``support.recognition`` (DG-ENG-11); no database.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.errors import EngineError
from erev_engine.formulas import FORMULAS
from erev_engine.stages import s09_recognition
from erev_engine.stages.s09_recognition import (
    deposit_attributions,
    deposit_share,
    deposit_share_weights,
)
from erev_engine.stages.state import DepositRelease, Quota, SpecialistTargets
from erev_engine.trace import TraceBuilder
from support import bundles
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    event_view,
    obligation,
    segment,
)

ENTITY = bundles.ENTITY_CODE
INCEPTION = date(2026, 1, 1)
RELEASED = date(2026, 6, 30)


def _release(
    amount: str, on: date = RELEASED, *, timed: bool = False, key: str = "EV-000005"
) -> DepositRelease:
    return DepositRelease(
        contract_key=CONTRACT_KEY,
        entity=ENTITY,
        reason="EVENT_25_7_A",
        effective_date=on,
        order_key=(on, 2**63 - 1 if timed else 5, "" if timed else f"{CONTRACT_KEY}/{key}"),
        amount=Fraction(amount),
        node_id=(
            f"deposit_to_revenue@{on.isoformat() if timed else f'{CONTRACT_KEY}/{key}'}"
            f":{CONTRACT_KEY}@{ENTITY}:-"
        ),
        timed=timed,
    )


def _state(
    releases: tuple[DepositRelease, ...], *, statuses=None, a_goods: int = 80000, a_svc: int = 40000
):
    goods = obligation(
        "G",
        [segment(Fraction(a_goods, 100), a_goods, start=None, end=None, measure="POINT_IN_TIME")],
        method="POINT_IN_TIME",
        convention=None,
    )
    service = obligation(
        "S",
        [segment(Fraction(a_svc, 100), a_svc, start=INCEPTION, end=date(2026, 12, 31))],
        convention="MONTHLY_EVEN",
    )
    # A memo on 31 December dates the version d_v (T-CON-11) after every release.
    memo = event_view(
        CONTRACT_KEY,
        9,
        "MEMO_UPDATED",
        date(2026, 12, 31),
        {"obligation_key": "S", "memo_1": "year end"},
        obligation_keys=["S"],
    )
    st = allocated_state([goods, service], statuses=statuses, events=[memo])
    return dataclasses.replace(
        st, specialist_targets=SpecialistTargets((), (), (), (), (), deposit_releases=releases)
    )


def test_deposit_share_weights_fall_back_from_allocation_to_ssp_to_stated_price() -> None:
    """S14-R-25: Σ A_p = 0 falls back to the resolved SSP, then to the stated prices, then raises
    ``TOTAL_WEIGHT_ZERO``."""
    goods = obligation(
        "G",
        [segment(Fraction(800), 80000, start=None, end=None, measure="POINT_IN_TIME")],
        method="POINT_IN_TIME",
        convention=None,
    )
    service = obligation(
        "S", [segment(Fraction(400), 40000, start=INCEPTION, end=date(2026, 12, 31))]
    )
    assert deposit_share_weights(CONTRACT_KEY, [goods, service]) == (
        (Fraction(80000), Fraction(40000)),
        "ALLOCATION",
    )
    zero_allocation = [
        dataclasses.replace(
            ob, original_allocation=Quota(Fraction(0), 0), resolved_ssp=Fraction(ssp)
        )
        for ob, ssp in ((goods, 300), (service, 100))
    ]
    assert deposit_share_weights(CONTRACT_KEY, zero_allocation) == (
        (Fraction(300), Fraction(100)),
        "SSP",
    )
    stated = [
        dataclasses.replace(ob, resolved_ssp=Fraction(0), stated_price=Fraction(price))
        for ob, price in zip(zero_allocation, (75, 25), strict=True)
    ]
    assert deposit_share_weights(CONTRACT_KEY, stated) == (
        (Fraction(75), Fraction(25)),
        "STATED_PRICE",
    )
    nothing = [dataclasses.replace(ob, stated_price=Fraction(0)) for ob in stated]
    with pytest.raises(EngineError) as raised:
        deposit_share_weights(CONTRACT_KEY, nothing)
    assert (raised.value.code, raised.value.detail["rule"]) == ("TOTAL_WEIGHT_ZERO", "S14-R-25")


def test_deposit_revenue_share_nodes_and_params() -> None:
    """A 1,200.00 release at a dated point on 30 June is apportioned [800.00, 400.00] over the
    posted inception allocation; the nodes cite the stage 02 recognition and carry the S14-R-25
    params; the time-share sibling carries the same value for a dated point; every node
    re-evaluates (PROP:P14)."""
    st = _state((_release("1200", timed=True),), statuses=((INCEPTION, "NOT_A_CONTRACT"),))
    ctx = book_context(bundles.entity(months=12))
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    state = s09_recognition.run(ctx, st, tb)
    trace = tb.build(root_measures={})
    nodes = {node.id: node for node in trace.nodes}
    goods, service = f"{CONTRACT_KEY}/G", f"{CONTRACT_KEY}/S"
    share = nodes[f"deposit_revenue_share:{goods}:FY2026-P06"]
    assert (share.value, share.formula_id, dict(share.params)) == (
        "800.00",
        "step1.deposit_revenue_share.v1",
        {
            "as_of": "2026-06-30",
            "basis": "ALLOCATION",
            "index": "0",
            "key": goods,
            "keys": f"{goods}|{service}",
            "minor_unit": "2",
            "weights": "80000|40000",
        },
    )
    assert share.inputs == (f"deposit_to_revenue@2026-06-30:{CONTRACT_KEY}@{ENTITY}:-",)
    assert nodes[f"deposit_revenue_share:{service}:FY2026-P06"].value == "400.00"
    assert nodes[f"deposit_revenue_time_share:{service}:FY2026-P06"].value == "400.00"
    assert nodes[f"deposit_revenue_share:{goods}:FY2026-P05"].value == "0.00"  # before the release
    assert nodes[f"deposit_revenue_share:{goods}:-"].value == "800.00"  # the version date
    shares = {
        (t.measure, t.subject_key, t.period_key): t.value for t in state.deposit_revenue_shares
    }
    assert shares[("deposit_revenue_share", goods, "FY2026-P12")] == 80000
    assert shares[("deposit_revenue_time_share", goods, "FY2026-P12")] == 80000
    # The registered formula reproduces the share from the recognition's value and the params
    # (the stage 02 node itself belongs to the compute-level traces, PROP:P14 there).
    assert FORMULAS[share.formula_id]([Fraction(1200)], share.params) == Fraction(800)
    # While NOT_A_CONTRACT the revenue targets stay 0 (S02-R-03; D-91 gaps (vii)).
    assert {t.value for t in state.revenue_targets} == {0}
    attribution = deposit_attributions(st)[CONTRACT_KEY]
    assert deposit_share(attribution, goods, date(2026, 6, 29), 2) == (0, ())
    assert deposit_share(attribution, goods, RELEASED, 2, timed=True)[0] == 80000


def test_step1_met_netting_after_criteria_met() -> None:
    """S02-R-04 (D-91 gaps (v)): a 1,200.00 release under 25-7 on 30 June while NOT_A_CONTRACT
    (shares 800.00 goods, 400.00 service), criteria met 1 July: the service's STEP1_MET target is
    max(C − 40,000, 0), 0 at July (C = 400 × 7/12 = 233.33) and 0 at December (C = 400.00); the
    undelivered goods stay at 0; the chain ``segment_target`` → ``step1_netted_target`` →
    ``revenue_cum`` re-evaluates. A 600.00 release (shares 400.00, 200.00) leaves the service's
    excess 400.00 − 200.00 = 200.00 at December."""
    statuses = ((INCEPTION, "NOT_A_CONTRACT"), (date(2026, 7, 1), "ACTIVE"))
    st = _state((_release("1200"),), statuses=statuses)
    ctx = book_context(bundles.entity(months=12))
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    state = s09_recognition.run(ctx, st, tb)
    trace = tb.build(root_measures={})
    nodes = {node.id: node for node in trace.nodes}
    goods, service = f"{CONTRACT_KEY}/G", f"{CONTRACT_KEY}/S"
    by_period = {(t.subject_key, t.period_key): t.value for t in state.revenue_targets}
    assert by_period[(goods, "FY2026-P06")] == 0 and by_period[(goods, "FY2026-P12")] == 0
    assert by_period[(service, "FY2026-P07")] == 0
    assert by_period[(service, "FY2026-P12")] == 0
    netted = nodes[f"step1_netted_target:{service}:FY2026-P12"]
    assert (netted.value, netted.params["r25"], netted.inputs) == (
        "0.00",
        "40000",
        (f"segment_target:{service}:FY2026-P12", f"deposit_revenue_share:{service}:FY2026-P12"),
    )
    assert nodes[f"segment_target:{service}:FY2026-P12"].value == "400.00"
    assert nodes[f"segment_target:{service}:FY2026-P07"].value == "233.33"
    revenue = nodes[f"revenue_cum:{service}:FY2026-P12"]
    assert (revenue.value, revenue.params["adjusted"], revenue.inputs) == (
        "0.00",
        "true",
        (netted.id,),
    )
    assert FORMULAS[netted.formula_id]([Fraction(400), Fraction(400)], netted.params) == 0
    assert FORMULAS[netted.formula_id]([Fraction(400), Fraction(200)], netted.params) == 200
    measures = state.obligation_measures[service]
    assert (measures.revenue_cum, str(measures.satisfaction_status)) == (0, "SATISFIED")
    assert measures.allocated_amount == measures.scheduled_amount + measures.awaiting_trigger_amount
    partial = _state((_release("600"),), statuses=statuses)
    partial_state = s09_recognition.run(ctx, partial, TraceBuilder(engine_version=ENGINE_VERSION))
    targets = {(t.subject_key, t.period_key): t.value for t in partial_state.revenue_targets}
    assert targets[(service, "FY2026-P12")] == 40000 - 20000
    assert targets[(service, "FY2026-P07")] == max(23333 - 20000, 0)
    assert targets[(goods, "FY2026-P12")] == 0
