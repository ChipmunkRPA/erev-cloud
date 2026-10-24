"""Dated member current-liability evidence without changing balance classification."""

from dataclasses import replace

from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.state import AllocatedState, BookContext, Target
from erev_engine.trace import TraceBuilder


def singleton(
    ctx: BookContext, state: AllocatedState, current: tuple[Target, ...], trace: TraceBuilder
) -> tuple[Target, ...]:
    member = state.contracts[0].header.external_id
    result = []
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
