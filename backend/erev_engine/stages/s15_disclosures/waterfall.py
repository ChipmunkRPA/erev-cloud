"""Stage 15 revenue waterfall measures (ENGINE_SPEC_B §15.2.1; S15-R-01, S15-R-02; EDS-2).

Private to stage 15 (DG-ENG-07). The engine part of report ``revenue_waterfall`` (REQ-RPT-004) for
one book at the version date d_v, per obligation that stage 09 measured:

- recognised (S15-R-01): Σ ``REVENUE`` lines by entity and posting period, credit positive, over
  the subledger after this computation. That is the book's posted amounts (RCP-05
  ``PostedAmountInput``) plus the ``REVENUE`` lines of the stage 14 posting intents, with every
  reason code and late-event carry. A line belongs to the obligation its entry's subject key names.
  The group totals take every ``REVENUE`` line of the book, so each period equals its revenue
  journal (S14-INV-06; CTL-019; L3-2-Q-31);
- scheduled: Σ ``REVENUE`` schedule lines of the version, all line types, for periods ending after
  the as-of period, which is the contracting entity's period holding d_v;
- awaiting: ``awaiting_trigger_amount`` of the obligation version, one column.

S15-R-02 tie-out per included obligation (E-22 ``UNSATISFIED`` or ``PARTIALLY_SATISFIED``):
recognised to date (posting periods ending on or before the as-of period) + scheduled + awaiting =
``allocated_amount`` (PROP:P7; DB-17). ``WaterfallRow.unexplained`` shows a difference; stage 15
raises no finding, because a failed tie-out is a report-run entry (§15.4). Cells name their
contributing nodes (intent lines, schedule lines, the stage 09 awaiting node) for the drill to
schedule lines (REQ-RPT-004). §15.5 names no waterfall node, so none is emitted. Standard library
only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import PostingIntent
from erev_engine.errors import EngineError
from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.s15_disclosures.rpo import INCLUDED, period_of
from erev_engine.stages.state import AllocatedState, BookContext, PostedIndex

__all__ = ["Waterfall", "WaterfallRow", "build"]

REVENUE: Final = "REVENUE"  # E-01 account role and E-27 schedule kind
RECOGNISED: Final = "recognised"
SCHEDULED: Final = "scheduled"
AWAITING: Final = "awaiting"


@dataclass(frozen=True, slots=True)
class WaterfallRow:
    """The waterfall measures of one obligation (S15-R-01) and its S15-R-02 tie-out."""

    subject_key: str
    contract_key: str
    as_of_period_key: str  # the contracting entity's period holding d_v
    included: bool  # E-22 UNSATISFIED or PARTIALLY_SATISFIED at d_v
    allocated: int  # T-CON-11 allocated_amount, minor units
    recognised: Mapping[tuple[str, str], int]  # (entity, posting period key) -> Σ REVENUE lines
    recognised_to_date: int  # Σ recognised of posting periods ending on or before the as-of period
    scheduled: Mapping[tuple[str, str], int]  # (entity, period key) after the as-of period
    awaiting: int  # T-CON-11 awaiting_trigger_amount
    contributors: Mapping[tuple[str, str, str], tuple[str, ...]]  # (measure, entity, period) -> ids

    @property
    def unexplained(self) -> int:
        """Allocated − (recognised to date + scheduled + awaiting) of an included obligation."""
        if not self.included:
            return 0
        planned = self.recognised_to_date + sum(self.scheduled.values()) + self.awaiting
        return self.allocated - planned


@dataclass(frozen=True, slots=True)
class Waterfall:
    """The revenue waterfall of one book at d_v: the rows and the group totals per cell."""

    as_of: date
    rows: tuple[WaterfallRow, ...]  # subject key order
    recognised: Mapping[tuple[str, str], int]  # every REVENUE line of the book (S14-INV-06)
    scheduled: Mapping[tuple[str, str], int]  # Σ rows
    awaiting: int  # Σ rows

    @property
    def balanced(self) -> bool:
        """Every included obligation ties (S15-R-02)."""
        return all(row.unexplained == 0 for row in self.rows)


def build(
    ctx: BookContext,
    st: AllocatedState,
    recognition: RecognitionState,
    intents: Sequence[PostingIntent],
    posted: PostedIndex | None,
    as_of: date,
) -> Waterfall:
    """The revenue waterfall measures of every obligation stage 09 measured (§15.2.1)."""
    book = str(ctx.book_code)
    periods = {
        (code, period.period_key): (period.start_date, period.end_date)
        for code, calendar in ctx.entities.items()
        for period in calendar.periods
    }
    subledger: list[tuple[str, str, str, int, str | None]] = []  # subject, entity, period, amount
    if posted is not None:
        for record in posted.amounts:
            if record.book_code == book and record.account_role == REVENUE:
                subledger.append(
                    (
                        record.subject_key,
                        record.entity_code,
                        record.period_key,
                        -record.amount_txn,
                        None,
                    )
                )
    for intent in intents:
        if intent.book_code != book:
            continue
        for line in intent.lines:
            if line.account_role != REVENUE:
                continue
            signed = line.amount_txn if line.side == "C" else -line.amount_txn
            subledger.append(
                (
                    intent.subject_key,
                    intent.entity,
                    intent.posting_period_key,
                    signed,
                    line.trace_node_id,
                )
            )
    group: dict[tuple[str, str], int] = {}
    recognised: dict[str, dict[tuple[str, str], int]] = {}
    nodes: dict[str, dict[tuple[str, str, str], list[str]]] = {}
    for subject, entity, period_key, amount, node_id in subledger:
        cell = _cell(periods, entity, period_key)
        group[cell] = group.get(cell, 0) + amount
        cells = recognised.setdefault(subject, {})
        cells[cell] = cells.get(cell, 0) + amount
        if node_id is not None:
            nodes.setdefault(subject, {}).setdefault((RECOGNISED, *cell), []).append(node_id)
    obligations = {ob.subject_key: ob for ob in st.obligations}
    as_of_periods: dict[str, tuple[str, date]] = {}
    for subject, measures in sorted(recognition.obligation_measures.items()):
        ob = obligations.get(subject)
        if ob is None:
            continue
        key = period_of(ctx, ob.contracting_entity, measures.as_of)
        as_of_periods[subject] = (key, periods[(ob.contracting_entity, key)][1])
    scheduled: dict[str, dict[tuple[str, str], int]] = {}
    for item in recognition.schedule_lines:
        if str(item.schedule_kind) != REVENUE or item.subject_key not in as_of_periods:
            continue
        cell = _cell(periods, item.entity, item.period_key)
        if periods[cell][1] <= as_of_periods[item.subject_key][1]:
            continue
        cells = scheduled.setdefault(item.subject_key, {})
        cells[cell] = cells.get(cell, 0) + item.amount
        nodes.setdefault(item.subject_key, {}).setdefault((SCHEDULED, *cell), []).append(
            item.trace_node_id
        )
    rows: list[WaterfallRow] = []
    for ob in sorted(st.obligations, key=lambda item: item.subject_key):
        m = recognition.obligation_measures.get(ob.subject_key)
        if m is None:
            continue
        key, end = as_of_periods[ob.subject_key]
        found = recognised.get(ob.subject_key, {})
        contributors = {
            cell: tuple(sorted(set(ids)))
            for cell, ids in sorted(nodes.get(ob.subject_key, {}).items())
        }
        awaiting_node = m.trace_nodes.get("awaiting_trigger_amount")
        if awaiting_node is not None:
            contributors[(AWAITING, "-", "-")] = (awaiting_node,)
        rows.append(
            WaterfallRow(
                subject_key=ob.subject_key,
                contract_key=ob.contract_key,
                as_of_period_key=key,
                included=str(m.satisfaction_status) in INCLUDED,
                allocated=m.allocated_amount,
                recognised=_ordered(found, periods),
                recognised_to_date=sum(
                    amount for cell, amount in found.items() if periods[cell][1] <= end
                ),
                scheduled=_ordered(scheduled.get(ob.subject_key, {}), periods),
                awaiting=m.awaiting_trigger_amount,
                contributors=MappingProxyType(dict(sorted(contributors.items()))),
            )
        )
    totals: dict[tuple[str, str], int] = {}
    for row in rows:
        for cell, amount in row.scheduled.items():
            totals[cell] = totals.get(cell, 0) + amount
    return Waterfall(
        as_of=as_of,
        rows=tuple(rows),
        recognised=_ordered(group, periods),
        scheduled=_ordered(totals, periods),
        awaiting=sum(row.awaiting for row in rows),
    )


def _cell(
    periods: Mapping[tuple[str, str], tuple[date, date]], entity: str, period_key: str
) -> tuple[str, str]:
    """(entity, period key) of a line, which must name a period of the entity's calendar."""
    cell = (entity, period_key)
    if cell not in periods:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "a revenue line names a period its entity does not keep",
            detail={"entity": entity, "period_key": period_key, "rule": "CV-12", "stage": "15"},
        )
    return cell


def _ordered(
    values: Mapping[tuple[str, str], int], periods: Mapping[tuple[str, str], tuple[date, date]]
) -> Mapping[tuple[str, str], int]:
    """The cells in (entity, period start) order, read-only."""
    ordered = sorted(values.items(), key=lambda item: (item[0][0], periods[item[0]][0], item[0][1]))
    return MappingProxyType(dict(ordered))
