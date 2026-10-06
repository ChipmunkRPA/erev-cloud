"""Stage 15 contract-cost rollforward (ENGINE_SPEC_B §15.2.6 S15-R-17; S15-INV-04; POLICIES
POL-196; 03 REQ-CST-006; BUILD_SPEC EDS-5).

Per contracting entity, book and cost kind (``OBTAIN``, ``FULFILL``) and period: opening carrying
(the previous period's closing from the engine's own measures; 0 only at inception; a lock snapshot,
when one exists, is a check against that opening and never its source — supervisor ruling Q-5 of
`docs/reviews/loop/prod/F-RPS-ENG-E1-prep.md`), additions
(JET-09a, 09a′), clawbacks (JET-09f), amortisation (JET-09b), acceleration on termination (JET-09e),
impairment (JET-09c), impairment reversal (JET-09d, IFRS15) and closing. The movements are the
period differences of the stage 11 cumulative T-CON-16 measures (``CostAssetMeasures``:
``capitalized_cum``, ``clawback_cum``, ``amortized_cum``, ``accelerated_cum``, ``impaired_cum``,
``impairment_reversed_cum``) and the closing is Σ ``carrying_amount`` of the assets at the period
end. Tie-out (S15-INV-04, S11-INV-06): opening + additions − clawbacks − amortisation − acceleration
− impairment + reversal = closing; any difference is ``OTHER``, shown and never absorbed (the
S15-R-07 convention).

Pure over stage 11 outputs (``CostAssetSpec`` for the entity and kind, ``CostAssetMeasures`` per
asset and period); no ``DisclosureState`` wiring here. Integration into ``s15_disclosures.run``
follows ENG-C4's EDS-4 (the Stage 15 barrier of lane F-RPS + ENG-E1). Standard library only
(DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from erev_engine.stages.s11_costs_loss.capitalise import CostAssetSpec
from erev_engine.stages.s11_costs_loss.impair import CostAssetMeasures

__all__ = [
    "COST_KINDS",
    "LINES",
    "MOVEMENTS",
    "CostRollforward",
    "CostRollforwardRow",
    "cost_rollforward",
    "rows_of",
]

COST_KINDS: Final = ("OBTAIN", "FULFILL")  # E-83
# S15-R-17 lines in presentation order; the movements between OPENING and CLOSING are signed as they
# enter the carrying amount (additions and reversals positive; the others negative).
LINES: Final = (
    "OPENING",
    "ADDITIONS",
    "CLAWBACKS",
    "AMORTIZATION",
    "ACCELERATION",
    "IMPAIRMENT",
    "IMPAIRMENT_REVERSAL",
    "OTHER",
    "CLOSING",
)
# movement line -> (cumulative measure, sign in the carrying amount)
MOVEMENTS: Final[Mapping[str, tuple[str, int]]] = MappingProxyType(
    {
        "ADDITIONS": ("capitalized_cum", 1),
        "CLAWBACKS": ("clawback_cum", -1),
        "AMORTIZATION": ("amortized_cum", -1),
        "ACCELERATION": ("accelerated_cum", -1),
        "IMPAIRMENT": ("impaired_cum", -1),
        "IMPAIRMENT_REVERSAL": ("impairment_reversed_cum", 1),
    }
)


@dataclass(frozen=True, slots=True)
class CostRollforwardRow:
    """One (entity, book, kind, period) row: the S15-R-17 lines in minor units, signed."""

    entity: str
    book_code: str
    cost_kind: str
    period_key: str
    lines: Mapping[str, int]  # LINES -> minor units; movements carry their carrying-amount sign
    asset_keys: tuple[str, ...]  # the assets measured at the period end, sorted

    @property
    def ties(self) -> bool:
        """S15-INV-04: opening plus the movements equals closing (OTHER is 0)."""
        return self.lines["OTHER"] == 0


@dataclass(frozen=True, slots=True)
class CostRollforward:
    """The rollforward of one book over the periods given (§15.1 output of EDS-5)."""

    book_code: str
    rows: tuple[CostRollforwardRow, ...]  # (entity, kind, period order) as ``periods`` lists them

    def row(self, entity: str, cost_kind: str, period_key: str) -> CostRollforwardRow:
        for row in self.rows:
            if (row.entity, row.cost_kind, row.period_key) == (entity, cost_kind, period_key):
                return row
        raise KeyError((entity, cost_kind, period_key))


def _cumulative(measure: CostAssetMeasures, name: str) -> int:
    value = getattr(measure, name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"CostAssetMeasures.{name} is not an int of minor units")
    return value


def cost_rollforward(
    book_code: str,
    specs: Iterable[CostAssetSpec],
    measures: Mapping[tuple[str, str], CostAssetMeasures],
    periods: Sequence[str],
    *,
    entities: Iterable[str] | None = None,
    prior: Mapping[str, CostAssetMeasures] | None = None,
) -> CostRollforward:
    """S15-R-17 rows per (entity, kind) of ``specs`` and period of ``periods``, in that order.

    ``measures`` maps (asset key, period key) to the stage 11 T-CON-16 values; an asset absent from
    a period contributes nothing to it (not yet capitalised, or measured only through its last
    period). ``prior`` carries the engine's own measures of the assets at the end of the period
    before ``periods[0]`` (a caller computing one period at a time passes the previous period's
    rows): the first period opens at Σ their carrying amounts and its movements are the differences
    from their cumulatives. Without ``prior`` the first period opens at 0, which is right only at
    inception. Every period after the first opens at the previous period's closing. A lock
    snapshot's ``COST_ROLLFORWARD`` closing is a check against the opening (S15-R-17 "previous
    snapshot"), never its source (ruling Q-5).
    """
    by_asset = {spec.asset_key: spec for spec in specs}
    scope = sorted(
        set(entities) if entities is not None else {spec.entity for spec in by_asset.values()}
    )
    rows: list[CostRollforwardRow] = []
    period_index = {period: index for index, period in enumerate(periods)}
    for entity in scope:
        for kind in COST_KINDS:
            assets = sorted(
                key
                for key, spec in by_asset.items()
                if spec.entity == entity and spec.cost_kind == kind
            )
            previous_closing: int | None = None
            for period in periods:
                current = {
                    key: measures[(key, period)] for key in assets if (key, period) in measures
                }
                if previous_closing is None:
                    previous_closing = sum(
                        _cumulative(prior[key], "carrying_amount")
                        for key in assets
                        if prior is not None and key in prior
                    )
                lines: dict[str, int] = dict.fromkeys(LINES, 0)
                lines["OPENING"] = previous_closing
                for line, (name, sign) in MOVEMENTS.items():
                    lines[line] = sign * sum(
                        _cumulative(measure, name)
                        - _previous_cumulative(
                            key, name, measures, periods, period_index[period], prior
                        )
                        for key, measure in current.items()
                    )
                closing = sum(
                    _cumulative(measure, "carrying_amount") for measure in current.values()
                )
                lines["CLOSING"] = closing
                lines["OTHER"] = closing - (
                    lines["OPENING"] + sum(lines[line] for line in MOVEMENTS)
                )
                rows.append(
                    CostRollforwardRow(
                        entity, book_code, kind, period, lines, tuple(sorted(current))
                    )
                )
                previous_closing = closing
    return CostRollforward(book_code, tuple(rows))


def _previous_cumulative(
    asset_key: str,
    name: str,
    measures: Mapping[tuple[str, str], CostAssetMeasures],
    periods: Sequence[str],
    index: int,
    prior: Mapping[str, CostAssetMeasures] | None,
) -> int:
    """The asset's cumulative measure at the previous period end: the latest earlier period of
    ``periods`` that measured it, else its ``prior`` row, else 0 (not yet capitalised)."""
    for earlier in range(index - 1, -1, -1):
        found = measures.get((asset_key, periods[earlier]))
        if found is not None:
            return _cumulative(found, name)
    if prior is not None and asset_key in prior:
        return _cumulative(prior[asset_key], name)
    return 0


def rows_of(rollforward: CostRollforward, period_key: str) -> tuple[CostRollforwardRow, ...]:
    """The rows of one period, (entity, kind) order: the E-64 ``COST_ROLLFORWARD`` dataset rows."""
    return tuple(row for row in rollforward.rows if row.period_key == period_key)
