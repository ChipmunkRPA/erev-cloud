"""Functional current assets use original obligation reclassification amounts."""

from collections.abc import Sequence
from typing import TYPE_CHECKING

from erev_engine import dates
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s10_billing_balances.current_split import CURRENT_POLICY, NONE
from erev_engine.stages.s12_fx_entities.balances import _presented_shares
from erev_engine.stages.state import BookContext, Target
from erev_engine.trace import TraceBuilder

if TYPE_CHECKING:
    from erev_engine.stages.s12_fx_entities import FxState


def measure(
    ctx: BookContext,
    fx: "FxState",
    members: Sequence[Target],
    totals: Sequence[Target],
    trace: TraceBuilder,
    *,
    acquired_cutover: bool = False,
) -> tuple[Target, ...]:
    from erev_engine.stages.s10_billing_balances.current_members import supported

    if (
        not acquired_cutover
        and any(ob.opening is not None for ob in fx.allocated.obligations)
        and not (ctx.acquired_member_current_asset and supported(ctx, fx.allocated))
    ):
        return ()
    periods = {
        entity: tuple(p.period_key for p in view.periods) for entity, view in ctx.entities.items()
    }
    shares = _presented_shares(
        fx, periods, {ob.subject_key: ob.subject_key for ob in fx.allocated.obligations}
    )
    total_values = {
        (t.subject_key, t.period_key): t.value
        for t in totals
        if t.measure == "contract_asset_functional"
    }
    result = []
    for current in members:
        if current.measure != "contract_asset_current":
            continue
        currency = ctx.entities[current.entity].functional_currency
        if currency == ctx.txn_currency:
            continue
        end = next(
            p.end_date
            for p in ctx.entities[current.entity].periods
            if p.period_key == current.period_key
        )
        horizon = dates.add_months(end, 12)
        enabled = (
            ctx.policies.value(CURRENT_POLICY, entity=current.entity, period=current.period_key)
            != NONE
        )
        selected = (
            {
                ob.subject_key
                for ob in fx.allocated.obligations
                if contract_entity_subject_key(ob.contract_key, ob.contracting_entity)
                == current.subject_key
                and (ob.end_date is None or ob.end_date <= horizon)
            }
            if enabled
            else set()
        )
        value = sum(shares.get((key, "CONTRACT_ASSET", current.period_key), 0) for key in selected)
        total = total_values.get((current.subject_key, current.period_key))
        if total is None or not 0 <= value <= total:
            raise ValueError("Functional current asset does not reconcile with total carrying")
        ordered = periods[current.entity]
        index = ordered.index(current.period_key)
        period_keys = {current.period_key, *(() if index == 0 else (ordered[index - 1],))}
        sources = [
            t.node_id
            for t in fx.functional_targets
            if t.entity == current.entity
            and t.measure == "netting_reclass_amount"
            and t.balance_role == "CONTRACT_ASSET"
            and t.subject_key.rsplit("#", 1)[0] in selected
            and t.period_key in period_keys
        ]
        name = "contract_asset_current_functional"
        node = trace.node(
            measure=name,
            subject_key=current.subject_key,
            period_key=current.period_key,
            value=value,
            currency=currency,
            minor_unit=ctx.currencies[currency].minor_unit,
            formula_id="fx.functional_member.v1",
            inputs=[current.node_id, *sources],
            params={
                "value": str(value),
                "as_of": end.isoformat(),
                "horizon": horizon.isoformat(),
                "classification_basis": "ORIGINAL_OBLIGATION_RECLASS",
                "keys": "|".join(sorted(selected)),
            },
            narrative_key="fx.functional_member",
        )
        result.append(
            Target(
                ctx.book_code,
                current.entity,
                current.subject_key,
                name,
                current.period_key,
                None,
                value,
                None,
                node,
            )
        )
    return tuple(result)
