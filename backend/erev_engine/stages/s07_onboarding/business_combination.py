"""Stage 07 business combinations (ENGINE_SPEC §7.3 S07-R-08; POLICIES PT-11, POL-215 to POL-217).

ASC606 book (POL-215 ``ASC606_AS_IF_ORIGINATED``, FORCED): the acquired contract is booked as if
originated, POL-216 and POL-217 being applied by the platform booking and by stage 05 (S05-R-01),
and its acquisition-date balances become opening state through ``opening.establish`` or
``difference.baseline`` as POL-210 resolves. IFRS15 book (``FAIR_VALUE_IFRS3``, FORCED):
``ifrs_fair_value`` apportions the acquisition-date fair value V of the contract liability
(payload ``fair_value_contract_liability``) over the contract's obligations by
``largest_remainder``(V, remaining allocations measured in the ASC606 book, keys). Each obligation
takes a ``PROSPECTIVE`` segment with base 0 and ``x_exact`` its share, so revenue thereafter
recognises those amounts. The baseline records revenue 0 and the share as billed, so the opening
net position equals the fair-valued liability (L1-3-Q-28). The IFRS15 transaction price becomes V:
one build-up at the acquisition event with fixed = total = allocation_basis = V, every other member
0, so Σ a_posted = V (S04-R-02) and DB-17 V1 hold (D-88 L7-5-Q-9; IFRS 3.18). Standard library
only (DG-ARC-02).
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from typing import Final

from erev_engine import money
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.stages.s01_canonicalize.convert import encode_key
from erev_engine.stages.s07_onboarding import opening
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EventView,
    ObligationState,
    Quota1,
    TpBuildUp,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = ["FAIR_VALUE_IFRS3", "SPLIT_FORMULA", "ifrs_fair_value"]

FAIR_VALUE_IFRS3: Final = "FAIR_VALUE_IFRS3"
SPLIT_FORMULA: Final = "onb.ifrs_fair_value_split.v1"
# The stage 04 build-up formulas of the fair-value price nodes (§4.4; D-88 L7-5-Q-9).
FIXED_FORMULA: Final = "tp.fixed.v1"
BUILDUP_FORMULA: Final = "tp.buildup.v1"


def ifrs_fair_value(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    payload: opening.Payload,
    tb: TraceBuilder,
) -> AllocatedState:
    """S07-R-08 in the IFRS15 book: the fair value of the contract liability, recognised from 0."""
    mu = opening.minor_unit(ctx)
    fair_value = payload.fair_value
    scaled = None if fair_value is None else fair_value * 10**mu
    if fair_value is None or scaled is None or scaled.denominator != 1:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the fair value of the contract liability is not a whole number of minor units",
            subject_key=ev.contract_key,
            detail={"event_key": ev.event_key, "rule": "S07-R-08"},
        )
    total = scaled.numerator
    cutover = payload.cutover_date.isoformat()
    obligations = opening.contract_obligations(st, ev)
    keys = [ob.subject_key for ob in obligations]
    weights = [payload.rows[ob.obligation_key].value("remaining_allocation") for ob in obligations]
    shares = opening.apportion(total, weights, keys)
    weight_sum = sum(weights, Fraction(0))
    fair_value_ref = SourceRef(
        "contract_event",
        ev.event_key,
        {"member": "fair_value_contract_liability", "value": money.format_exact(fair_value)},
    )
    common = {
        "cutover_date": cutover,
        "keys": opening.SEPARATOR.join(keys),
        "weights": opening.SEPARATOR.join(rational_param(weight) for weight in weights),
    }
    replaced: dict[str, ObligationState] = {}
    for ob, weight, a_posted in zip(obligations, weights, shares, strict=True):
        row = payload.rows[ob.obligation_key]
        x_exact = Fraction(0) if weight_sum == 0 else Fraction(total, 10**mu) * weight / weight_sum
        tb.node(
            measure=f"opening_allocation@{ev.event_key}",
            subject_key=ob.subject_key,
            period_key=None,
            value=a_posted,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=SPLIT_FORMULA,
            inputs=[fair_value_ref],
            params={**common, "key": ob.subject_key},
            exact=x_exact,
            narrative_key=SPLIT_FORMULA.rsplit(".v", 1)[0],
        )
        revenue = row.value("revenue_cum")
        node_id = tb.node(
            measure=f"opening_revenue_cum@{ev.event_key}",
            subject_key=ob.subject_key,
            period_key=None,
            value=0,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=opening.BASELINE_FORMULA,
            inputs=[opening.payload_ref(ev, ob.obligation_key, "revenue_cum", revenue)],
            params={"cutover_date": cutover, "mode": "fair_value"},
            exact=Fraction(0),
            narrative_key=opening.BASELINE_FORMULA.rsplit(".v", 1)[0],
        )
        seg = opening.opening_segment(
            st,
            ob,
            opening.required_in_force(st, ob, ev),
            ev,
            row,
            cutover=payload.cutover_date,
            x_exact=x_exact,
            a_posted=a_posted,
            base_exact=Fraction(0),
            base_posted=0,
        )
        record = opening.OpeningBaseline(
            subject_key=ob.subject_key,
            cutover_date=payload.cutover_date,
            revenue_cum=0,
            billed_cum=a_posted,
            deposit_liability=row.optional("deposit_liability", mu),
            pre_standard_revenue_cum=0,
            method=opening.OPENING_BALANCES,
            node_id=node_id,
            absent_members=row.absent(("deposit_liability",)),  # billed_cum is the fair-value share
        )
        existing = opening.differences_of(ob)
        replaced[ob.subject_key] = replace(
            ob,
            segments=(*ob.segments, seg),
            opening=opening.view(row, payload, ev, record, existing, measurement=FAIR_VALUE_IFRS3),
        )
    after = replace(
        st, obligations=tuple(replaced.get(ob.subject_key, ob) for ob in st.obligations)
    )
    return _fair_value_price(ctx, after, ev, Quota1(fair_value, total), fair_value_ref, tb)


def _fair_value_price(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    value: Quota1,
    fair_value_ref: SourceRef,
    tb: TraceBuilder,
) -> AllocatedState:
    """D-88 L7-5-Q-9: the IFRS15 build-up appended at the acquisition event.

    fixed = total = allocation_basis = V, citing the payload member
    ``fair_value_contract_liability``; every other member 0. Like a boundary price, it is measured
    at the event date before the next event, and its nodes take the CV-50 names
    ``<column>@<event key>``, because the version-state nodes keep the inception price that stage
    05 cites (L5-3-Q-2).
    """
    mu = opening.minor_unit(ctx)
    zero = Quota1(Fraction(0), 0)
    following = next((item for item in st.events if item.order_key > ev.order_key), None)
    buildup = TpBuildUp(
        at=ev.effective_date,
        before_event_key=None if following is None else following.event_key,
        fixed=value,
        vc_constrained=zero,
        vc_excluded=zero,
        expected_returns=zero,
        consideration_payable=zero,
        financing_adjustment=zero,
        noncash=zero,
        sales_tax_excluded=zero,
        out_of_scope=zero,
        total=value,
        allocation_basis=value,
        elements=(),
    )
    group = encode_key(st.group_code)
    node_id: str | SourceRef = fair_value_ref
    for measure, formula, params in (
        ("fixed_consideration", FIXED_FORMULA, {}),
        ("transaction_price", BUILDUP_FORMULA, {"signs": "+"}),
        ("tp_allocation_basis", BUILDUP_FORMULA, {"signs": "+"}),
    ):
        node_id = tb.node(
            measure=f"{measure}@{ev.event_key}",
            subject_key=group,
            period_key=None,
            value=value.posted,
            currency=ctx.txn_currency,
            minor_unit=mu,
            formula_id=formula,
            inputs=[node_id],
            params=dict(params),
            exact=value.exact,
            narrative_key=formula.rsplit(".v", 1)[0],
        )
    return replace(st, tp_history=(*st.tp_history, buildup))
