"""T-CON-09 ``cost_asset_carrying_txn`` and ``loss_provision_txn`` from the stage 11 measures (04
T-CON-09 "Sum of obtain and fulfil assets; detail in ``cost_asset_version``" and
``loss_provision_txn``; ENGINE_SPEC_B §11.1; lane L5-5; D-92 (3), lane ENG-C7).

``_balances`` builds the labelled balances from the stage 10 member balances only, so no row held
the carrying amount of the member's contract cost assets or the provision of its loss units, and
every COST, JE-CHK-13x, LOSS and IFRS-SW11 key read ``cost_asset_carrying`` or ``loss_provision``
as ``<absent>``. Each row now takes the sum of the T-CON-16 carrying amounts of the assets of its
member contract and contracting entity at the period end, and the sum of the T-CON-17 required
provisions (S11-R-14 ``provision_balance``) of the member's loss units at the period end, else 0
(the T-CON-09 default). Private to stage 11 (DG-ENG-07). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import BalanceOut
from erev_engine.errors import EngineError
from erev_engine.stages.state import BookContext, Target
from erev_engine.trace import TraceBuilder

__all__ = ["member_sums", "cost_asset_carrying_columns", "loss_provision_columns"]

_CARRYING_COLUMN: Final = "cost_asset_carrying_txn"
_LOSS_COLUMN: Final = "loss_provision_txn"
MEMBER_SUM_FORMULA: Final = "cost.member_sum.v1"
CARRYING_MEASURE: Final = "cost_asset_carrying"
LOSS_MEASURE: Final = "loss_provision"


def cost_asset_carrying_columns(
    rows: Sequence[BalanceOut],
    *,
    carrying: Mapping[tuple[str, str], int],
    member_of: Mapping[str, str],
) -> tuple[BalanceOut, ...]:
    """The rows with ``cost_asset_carrying_txn``.

    ``carrying`` maps (asset key, period key) to the T-CON-16 carrying amount, and ``member_of`` an
    asset key to its member balance subject ``<contract>@<contracting entity>``.
    """
    return _summed_column(
        rows, _CARRYING_COLUMN, carrying, member_of, "a cost asset names no member contract"
    )


def loss_provision_columns(
    rows: Sequence[BalanceOut],
    *,
    provisions: Mapping[tuple[str, str], int],
    member_of: Mapping[str, str],
) -> tuple[BalanceOut, ...]:
    """The rows with ``loss_provision_txn`` (S11-R-14; JET-12; D-92 (3)).

    ``provisions`` maps (loss unit key, period key) to the T-CON-17 ``provision_balance``, the
    provision required at the period end, and ``member_of`` a loss unit key to its member balance
    subject ``<contract>@<contracting entity>``. A member's column sums its units: one under
    POL-150 ``CONTRACT``, one per obligation under ``POB``. A member the book does not test
    (S11-R-15: outside the POL-151 scope) has no unit and reads the T-CON-09 default 0.
    """
    return _summed_column(
        rows, _LOSS_COLUMN, provisions, member_of, "a loss unit names no member contract"
    )


def _summed_column(
    rows: Sequence[BalanceOut],
    column: str,
    amounts: Mapping[tuple[str, str], int],
    member_of: Mapping[str, str],
    missing: str,
) -> tuple[BalanceOut, ...]:
    sums: dict[tuple[str, str], int] = {}
    for (subject_key, period_key), amount in sorted(amounts.items()):
        member = member_of.get(subject_key)
        if member is None:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                missing,
                subject_key=subject_key,
                detail={"period_key": period_key, "rule": "CV-45"},
            )
        sums[(member, period_key)] = sums.get((member, period_key), 0) + amount
    out: list[BalanceOut] = []
    for row in rows:
        columns = dict(row.columns)
        columns[column] = sums.get((row.subject_key, row.period_key), 0)
        out.append(
            BalanceOut(
                subject_key=row.subject_key,
                period_key=row.period_key,
                columns=MappingProxyType(columns),
                trace_nodes=row.trace_nodes,
            )
        )
    return tuple(out)


def member_sums(
    ctx: BookContext,
    members: Sequence[Target],
    *,
    carrying: Mapping[tuple[str, str], tuple[int, str]],
    provisions: Mapping[tuple[str, str], tuple[int, str]],
    member_of: Mapping[str, str],
    tb: TraceBuilder,
) -> tuple[Target, ...]:
    """T-CON-09 ``cost_asset_carrying_txn`` and ``loss_provision_txn`` per member and period as
    targets with their own nodes (DG-KRN-EXP-01; ENGINE_SPEC CV-50 links; D-97 (8); lane ENG-T1F):
    ``cost.member_sum.v1`` over the T-CON-16 ``carrying_amount`` nodes (or the T-CON-17
    ``loss_provision_required`` nodes) of the member's assets (units) at the period end, 0 citing
    no node when the member has none (S11-R-15). ``members`` are the stage 10 member balance
    targets whose (subject, period) pairs define the T-CON-09 rows; ``carrying`` / ``provisions``
    map (asset or unit key, period key) to (value, node id); ``member_of`` an asset or unit key to
    its member ``<contract>@<contracting entity>``."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    grouped: dict[tuple[str, str, str], list[tuple[int, str]]] = {}
    for measure_name, amounts in ((CARRYING_MEASURE, carrying), (LOSS_MEASURE, provisions)):
        for (subject_key, period_key), (value, node_id) in sorted(amounts.items()):
            member = member_of.get(subject_key)
            if member is None:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "a cost asset or loss unit names no member contract",
                    subject_key=subject_key,
                    detail={"period_key": period_key, "rule": "CV-45"},
                )
            grouped.setdefault((member, period_key, measure_name), []).append((value, node_id))
    out: list[Target] = []
    for subject, period_key, entity in sorted(
        {(m.subject_key, m.period_key, m.entity) for m in members}
    ):
        for measure_name in (CARRYING_MEASURE, LOSS_MEASURE):
            items = grouped.get((subject, period_key, measure_name), [])
            value = sum(amount for amount, _ in items)
            node_id = tb.node(
                measure=measure_name,
                subject_key=subject,
                period_key=period_key,
                value=value,
                currency=ctx.txn_currency,
                minor_unit=minor_unit,
                formula_id=MEMBER_SUM_FORMULA,
                inputs=[node for _, node in items],
                params={"as_of": period_key, "role": "member_sum"},
                narrative_key=MEMBER_SUM_FORMULA.rsplit(".v", 1)[0],
            )
            out.append(
                Target(
                    ctx.book_code,
                    entity,
                    subject,
                    measure_name,
                    period_key,
                    None,
                    value,
                    None,
                    node_id,
                )
            )
    return tuple(out)
