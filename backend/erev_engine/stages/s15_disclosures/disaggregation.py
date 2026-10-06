"""Stage 15 disaggregation of revenue (ENGINE_SPEC_B §15.2.5 S15-R-15, S15-R-16; S15-INV-03;
POLICIES POL-191; 606-10-50-5 to 50-7, 55-89 to 55-91; REQ-RPT-011; EDS-4).

Stage 14 writes on every ``REVENUE`` line of an obligation the S15-R-15 dimension values stamped
on ``ObligationState.dimensions`` (``stages.state.disaggregation_tags``: the template
``disaggregation`` mapping, product family, revenue category, contract region, channel and
contract type, performing entity and ``timing_of_transfer``). ``build`` groups the period's
``REVENUE`` lines of the consumed posting intents — JET-02 recognition, JET-13 performing-side,
JET-05c concession, JET-14 release and JET-01b 25-7 lines alike (S15-R-16) — per (entity, posting
period, dimension code, value), credit positive; a line without a dimension falls under ``-`` so the
tie-out holds. S15-INV-03: per (entity, period) and dimension, Σ rows = the ``REVENUE`` journal
total of the period (CTL-028); a violation fails closed. Under POL-191 ``ELECT`` (nonpublic) the
rows are still produced; the pack shows timing of transfer and the qualitative factors (the
platform report, F-RPS). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import PostingIntent
from erev_engine.errors import EngineError
from erev_engine.stages.state import DISAGGREGATION_DERIVED

__all__ = ["ABSENT", "REVENUE", "Disaggregation", "DisaggregationRow", "build"]

REVENUE: Final = "REVENUE"  # E-01
ABSENT: Final = "-"  # a line without the dimension


@dataclass(frozen=True, slots=True)
class DisaggregationRow:
    """Σ revenue of one dimension value (S15-R-16), transaction currency minor units, credit
    positive."""

    entity: str
    period_key: str
    dimension: str
    value: str
    amount: int


@dataclass(frozen=True, slots=True)
class Disaggregation:
    """S15-R-16 rows of one book, (entity, period, dimension, value) order, and the revenue journal
    total per (entity, period) they tie to (S15-INV-03)."""

    rows: tuple[DisaggregationRow, ...]
    totals: Mapping[tuple[str, str], int]
    dimensions: tuple[str, ...]  # every dimension code seen, sorted


def build(intents: Sequence[PostingIntent]) -> Disaggregation:
    """Group the ``REVENUE`` lines of ``intents`` by dimension value and tie them out."""
    totals: dict[tuple[str, str], int] = {}
    cells: dict[tuple[str, str, str, str], int] = {}
    codes: set[str] = set(DISAGGREGATION_DERIVED)
    for intent in intents:
        cell = (intent.entity, intent.posting_period_key)
        for line in intent.lines:
            if line.account_role != REVENUE:
                continue
            signed = line.amount_txn if line.side == "C" else -line.amount_txn
            totals[cell] = totals.get(cell, 0) + signed
            codes.update(code for code in line.dimensions if code not in _LINE_KEYS)
    for intent in intents:
        for line in intent.lines:
            if line.account_role != REVENUE:
                continue
            signed = line.amount_txn if line.side == "C" else -line.amount_txn
            for code in codes:
                key = (
                    intent.entity,
                    intent.posting_period_key,
                    code,
                    line.dimensions.get(code, ABSENT),
                )
                cells[key] = cells.get(key, 0) + signed
    rows = tuple(
        DisaggregationRow(entity, period, dimension, value, amount)
        for (entity, period, dimension, value), amount in sorted(cells.items())
    )
    _check(rows, totals)
    return Disaggregation(
        rows=rows,
        totals=MappingProxyType(dict(sorted(totals.items()))),
        dimensions=tuple(sorted(codes)),
    )


# JET rule R3 identity dimensions (S14-R-13) are not disaggregation attributes.
_LINE_KEYS: Final = frozenset({"contract", "contract_key", "obligation_key", "product"})


def _check(rows: Sequence[DisaggregationRow], totals: Mapping[tuple[str, str], int]) -> None:
    """S15-INV-03: for every (entity, period) and dimension, Σ rows = the revenue journal total."""
    sums: dict[tuple[str, str, str], int] = {}
    for row in rows:
        key = (row.entity, row.period_key, row.dimension)
        sums[key] = sums.get(key, 0) + row.amount
    for (entity, period, dimension), amount in sorted(sums.items()):
        expected = totals.get((entity, period), 0)
        if amount != expected:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the disaggregation total differs from the revenue journal total",
                subject_key=entity,
                detail={
                    "dimension": dimension,
                    "disaggregation_total": str(amount),
                    "journal_total": str(expected),
                    "period_key": period,
                    "rule": "S15-INV-03",
                    "stage": "15",
                },
            )
