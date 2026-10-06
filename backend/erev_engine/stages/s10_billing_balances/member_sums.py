"""T-CON-09 member balance sums of stage 10 (ENGINE_SPEC_B S10-R-23; dev-guide DG-KRN-EXP-01;
ENGINE_SPEC CV-50 links; D-97 (8); lane ENG-T1F).

One node per member ``<contract>@<entity>``, period end and measure — ``refund_liability``,
``return_asset``, ``deposit_liability``, ``customer_incentive_asset``, ``consideration_payable``
and, where the book measures receivables (S10-R-19 ``ENGINE`` mode), ``accounts_receivable`` — the
signed sum ``bal.member_sum.v1`` of the component targets of that member and period, 0 citing no
component when none exists. A component target that is itself the member's node (EMOD-12 deposit
and EMOD-22 consideration targets are per ``<contract>@<entity>``) is the member node and no sum
node is emitted. The assembler publishes the T-CON-09 ``<measure>_txn`` columns from these targets
and links their nodes; the component targets, their nodes and every posting stay unchanged.
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.state import AllocatedState, BookContext, Target
from erev_engine.trace import TraceBuilder

__all__ = ["FORMULA", "MEASURES", "measure"]

FORMULA: Final = "bal.member_sum.v1"
MEASURES: Final = (
    "refund_liability",
    "return_asset",
    "deposit_liability",
    "customer_incentive_asset",
    "consideration_payable",
)
RECEIVABLE: Final = "accounts_receivable"
CPC_MEASURES: Final = frozenset({"customer_incentive_asset", "consideration_payable"})


def measure(
    ctx: BookContext,
    st: AllocatedState,
    members: Sequence[Target],
    *,
    refund_liabilities: Sequence[Target],
    return_assets: Sequence[Target],
    receivables: Sequence[Target],
    component_contracts: dict[str, str],
    tb: TraceBuilder,
) -> tuple[Target, ...]:
    """The member sum targets (see module); ``members`` are the S10-R-23 member balance targets
    whose (subject, period) pairs define the T-CON-09 rows; ``component_contracts`` maps a refund
    component key to its contract key."""
    contract_of = dict(component_contracts)
    contract_of.update({ob.subject_key: ob.contract_key for ob in st.obligations})
    grouped: dict[tuple[str, str, str], list[Target]] = {}
    components = (
        *(item for item in refund_liabilities if item.measure == "refund_liability"),
        *(item for item in return_assets if item.measure == "return_asset"),
        *(item for item in receivables if item.measure == RECEIVABLE),
        *(item for item in st.specialist_targets.deposit if item.measure == "deposit_liability"),
        *(
            item
            for item in st.specialist_targets.customer_consideration
            if item.measure in CPC_MEASURES
        ),
    )
    for target in components:
        member = contract_of.get(target.subject_key)
        subject = (
            target.subject_key
            if member is None
            else contract_entity_subject_key(member, target.entity)
        )
        grouped.setdefault((subject, target.period_key, target.measure), []).append(target)
    rows = sorted({(item.subject_key, item.period_key, item.entity) for item in members})
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    out: list[Target] = []
    for subject, period_key, entity in rows:
        measures: tuple[str, ...] = MEASURES
        if (subject, period_key, RECEIVABLE) in grouped:
            measures = (*MEASURES, RECEIVABLE)
        for name in measures:
            items = sorted(grouped.get((subject, period_key, name), ()), key=lambda t: t.node_id)
            node_id = f"{name}:{subject}:{period_key}"
            value = sum(item.value for item in items)
            if len(items) == 1 and items[0].node_id == node_id:
                out.append(
                    Target(
                        ctx.book_code, entity, subject, name, period_key, None, value, None, node_id
                    )
                )
                continue
            if tb.value(node_id) is not None:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "a member balance node exists beside several component targets",
                    subject_key=subject,
                    detail={"rule": "S10-R-23", "measure": name, "period_key": period_key},
                )
            emitted = tb.node(
                measure=name,
                subject_key=subject,
                period_key=period_key,
                value=value,
                currency=ctx.txn_currency,
                minor_unit=minor_unit,
                formula_id=FORMULA,
                inputs=[item.node_id for item in items],
                params={"as_of": period_key, "role": "member_sum"},
                narrative_key=FORMULA.rsplit(".v", 1)[0],
            )
            out.append(
                Target(ctx.book_code, entity, subject, name, period_key, None, value, None, emitted)
            )
    return tuple(out)
