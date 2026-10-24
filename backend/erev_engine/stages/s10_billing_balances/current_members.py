"""Dated member current-liability evidence without changing balance classification."""

from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.state import AllocatedState, BookContext, Target
from erev_engine.trace import TraceBuilder

if TYPE_CHECKING:
    from .reclass import Presentation


def supported(ctx: BookContext, state: AllocatedState) -> bool:
    """Opening balances must retain an admitted principal acquisition baseline."""
    from erev_engine.stages.s07_onboarding import baseline_of

    for ob in state.obligations:
        if ob.opening is None:
            continue
        baseline = baseline_of(ob)
        if (
            not ctx.acquired_member_current_liability
            or ob.opening.get("reason") != "BUSINESS_COMBINATION"
            or ob.principal_agent.value != "PRINCIPAL"
            or baseline is None
            or baseline.method
            not in (
                {"OPENING_BALANCES_AT_CUTOVER", "RECOMPUTE_FROM_INCEPTION"}
                if ctx.recomputed_member_current_liability
                else {"OPENING_BALANCES_AT_CUTOVER"}
            )
        ):
            return False
    return True


def singleton(
    ctx: BookContext, state: AllocatedState, current: tuple[Target, ...], trace: TraceBuilder
) -> tuple[Target, ...]:
    member = state.contracts[0].header.external_id
    result: list[Target] = []
    for target in current:
        if target.measure != "contract_liability_current":
            continue
        subject = contract_entity_subject_key(member, target.entity)
        node = target.node_id
        if subject != target.subject_key:
            node = trace.node(
                measure=target.measure,
                subject_key=subject,
                period_key=target.period_key,
                value=target.value,
                currency=ctx.txn_currency,
                minor_unit=ctx.currencies[ctx.txn_currency].minor_unit,
                formula_id="rec.activity_sum.v1",
                inputs=[target.node_id],
                params={"signs": "+"},
                narrative_key="rec.activity_sum",
            )
        result.append(replace(target, subject_key=subject, node_id=node))
    return tuple(result)


def apportion(
    ctx: BookContext,
    current: Target,
    totals: Sequence[Target],
    trace: TraceBuilder,
    *,
    currency: str,
    measure: str,
) -> tuple[Target, ...]:
    """Allocate only a presentation classification, using original carrying weights."""
    from fractions import Fraction

    from erev_engine.money import largest_remainder

    ordered = sorted(totals, key=lambda t: t.subject_key)
    if not ordered or not 0 <= current.value <= sum(t.value for t in ordered):
        raise ValueError("Current liability does not reconcile with member carrying amounts")
    keys = [t.subject_key for t in ordered]
    weights = [Fraction(t.value) for t in ordered]
    shares = largest_remainder(current.value, weights, keys) if current.value else [0] * len(keys)
    result: list[Target] = []
    for index, (total, share) in enumerate(zip(ordered, shares, strict=True)):
        if not 0 <= share <= total.value:
            raise ValueError("Member current liability exceeds its total carrying amount")
        node = trace.node(
            measure=measure,
            subject_key=total.subject_key,
            period_key=total.period_key,
            value=share,
            currency=currency,
            minor_unit=ctx.currencies[currency].minor_unit,
            formula_id="alloc.largest_remainder.v1",
            inputs=[current.node_id, *(t.node_id for t in ordered)],
            params={
                "index": str(index),
                "keys": ",".join(f"{i:08}" for i in range(len(keys))),
                "minor_unit": str(ctx.currencies[currency].minor_unit),
                "basis": "MEMBER_LIABILITY_CARRYING",
                "members": "|".join(keys),
            },
            narrative_key="alloc.largest_remainder",
        )
        result.append(replace(total, measure=measure, value=share, node_id=node))
    return tuple(result)


def allocate(
    ctx: BookContext,
    state: AllocatedState,
    presentation: "Presentation",
    current: Sequence[Target],
    destination_currents: Sequence[Target],
    trace: TraceBuilder,
) -> tuple[Target, ...]:
    scopes = {
        (subject, period): {
            contract_entity_subject_key(ob.contract_key, ob.contracting_entity)
            for ob in state.obligations
            if ob.subject_key in obligations
        }
        for subject, period, obligations in presentation.destination_members
    }
    result: list[Target] = []
    for group in current:
        if group.measure != "contract_liability_current":
            continue
        partitions = [
            t
            for t in destination_currents
            if (t.entity, t.period_key) == (group.entity, group.period_key)
        ]
        for target in partitions or [group]:
            totals = [
                t
                for t in presentation.members
                if t.measure == "contract_liability"
                and (t.entity, t.period_key) == (target.entity, target.period_key)
                and (
                    not partitions or t.subject_key in scopes[target.subject_key, target.period_key]
                )
            ]
            result.extend(
                apportion(
                    ctx,
                    target,
                    totals,
                    trace,
                    currency=ctx.txn_currency,
                    measure="contract_liability_current",
                )
            )
    return tuple(result)
