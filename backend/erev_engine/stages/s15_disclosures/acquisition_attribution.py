"""Original S10 asset attribution for a recomputed acquisition observation."""

from fractions import Fraction
from typing import Any

from erev_engine.bundle import PeriodInput
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import group_entity_subject_key
from erev_engine.stages.s10_billing_balances import reclass
from erev_engine.stages.s10_billing_balances.position import PositionComponents
from erev_engine.stages.state import AllocatedState, BookContext


def capture(
    ctx: BookContext,
    st: AllocatedState,
    entity: str,
    period: PeriodInput,
    obligations: dict[str, Any],
) -> dict[str, Any] | None:
    own = sorted(
        (ob for ob in st.obligations if ob.contracting_entity == entity),
        key=lambda ob: ob.subject_key,
    )
    if set(obligations) != {ob.subject_key for ob in own} or any(
        item.get("right_class") not in {"CONDITIONAL", "UNCONDITIONAL"}
        for item in obligations.values()
    ):
        return None
    billed = {key: item["billed"] for key, item in obligations.items()}
    revenue = {key: item["revenue"] for key, item in obligations.items()}
    # This observation is the original recomputed billed-minus-revenue position.
    # The reader must reconcile the resulting CA/UR to the original rollforward;
    # it cannot apply this attribution to a different control position.
    position = PositionComponents(
        group_entity_subject_key(st.group_code, entity),
        entity,
        period.period_key,
        period.end_date,
        sum(billed.values()) - sum(revenue.values()),
        sum(billed.values()),
        sum(revenue.values()),
        0,
        0,
        0,
        0,
        0,
        0,
        "",
    )
    point = reclass._Point(
        period,
        position,
        revenue,
        revenue,
        billed,
        {key: item["right_class"] for key, item in obligations.items()},
    )
    policy = ctx.policies.value(reclass.ATTRIBUTION_POLICY, entity=entity, period=period.period_key)
    mu = ctx.currencies[ctx.txn_currency].minor_unit
    try:
        if policy == reclass.POB_DEBIT_POSITIONS:
            plan = reclass._pob_debit_plan(own, point, mu)
        elif policy == reclass.CUMULATIVE_SSP_DELIVERED:
            # Residue affects exact quota evidence only, not integer allocation. This
            # snapshot retains integer parts and makes no claim about exact quotas.
            plan = reclass._ssp_delivered_plan(st, own, point, Fraction(0), mu)
        else:
            return None
    except EngineError:
        # Optional disclosure evidence cannot extend the financial posting horizon
        # or turn an unmeasured, unsupported attribution into a posting failure.
        return None
    return {
        "rule": "S10-R-22",
        "policy": policy,
        "as_of": period.end_date.isoformat(),
        "basis": dict(plan.params),
        "contract_asset": plan.asset,
        "unbilled_receivable": plan.receivable,
        "parts": {
            key: {"contract_asset": ca, "unbilled_receivable": ur}
            for key, (ur, ca) in plan.parts.items()
        },
        "sources": sorted({source for item in obligations.values() for source in item["sources"]}),
    }
