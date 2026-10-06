"""Reporting-currency translation views (ENGINE_SPEC_B §12.2.6 S12-R-18; BUILD_SPEC END-3).

Exported for the RPS reports through the stage package (DG-ENG-07). Reporting-currency views are
platform projections: the engine posts no translation adjustment (research 06 §9.6; REQ-FX-005).
``translate_to_reporting`` converts one functional-currency rollforward of one period into the
reporting currency:

- balances at the closing rate: the opening balance at the closing rate of the previous period,
  the closing balance at the closing rate of the period;
- flows at the average rate of the period;
- a translation line, round(closing × closing rate − opening × previous closing rate − Σ flows ×
  average rate), the rate effect that makes opening + flows + translation = closing;
- the residue of converting each line on its own posts to ``ROUNDING`` (D-16; §14.3.5), so the
  reporting lines foot exactly.

Rates are explicit pinned rates of base = functional currency and quote = reporting currency, with
no inversion or triangulation (S12-R-01; research 06 §9.5). A same-currency view uses rate 1. A
missing rate raises ``EngineError("FX_RATE_MISSING")`` with the S12-R-01 detail. Standard library
only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from erev_engine.currencies import CurrencyTable
from erev_engine.dates import PeriodLike
from erev_engine.errors import EngineError
from erev_engine.money import round_half_up
from erev_engine.stages.s12_fx_entities.rates import (
    AVERAGE,
    CLOSING,
    RateMissing,
    Rates,
    RateView,
    to_functional,
)
from erev_engine.stages.state import RateIndex

__all__ = [
    "CLOSING_BALANCE",
    "FLOW",
    "INPUT_KINDS",
    "OPENING_BALANCE",
    "ROUNDING",
    "TRANSLATION",
    "FunctionalLine",
    "ReportingLine",
    "ReportingTranslation",
    "translate_to_reporting",
]

OPENING_BALANCE: Final = "OPENING"
FLOW: Final = "FLOW"
CLOSING_BALANCE: Final = "CLOSING"
TRANSLATION: Final = "TRANSLATION"
ROUNDING: Final = "ROUNDING"  # E-01 role of the batch residue (D-16)
INPUT_KINDS: Final = frozenset({OPENING_BALANCE, FLOW, CLOSING_BALANCE})


@dataclass(frozen=True, slots=True)
class FunctionalLine:
    """One line of a functional-currency rollforward: a balance or a flow, signed minor units."""

    label: str
    kind: str  # OPENING | FLOW | CLOSING
    amount: int

    def __post_init__(self) -> None:
        if self.kind not in INPUT_KINDS:
            raise ValueError(f"unknown rollforward line kind {self.kind!r}")
        if isinstance(self.amount, bool) or not isinstance(self.amount, int):
            raise TypeError("a rollforward amount is an integer of minor units")


@dataclass(frozen=True, slots=True)
class ReportingLine:
    """A translated line; ``TRANSLATION`` and ``ROUNDING`` carry no functional amount or rate."""

    label: str
    kind: str  # OPENING | FLOW | TRANSLATION | ROUNDING | CLOSING
    amount_functional: int
    amount_reporting: int
    rate_type: str | None  # closing | average
    rate: Fraction | None
    rate_key: str | None  # None for rate 1 and for TRANSLATION and ROUNDING (REQ-FX-006)
    version_key: str | None


@dataclass(frozen=True, slots=True)
class ReportingTranslation:
    """A reporting-currency view: openings, flows, translation, rounding, then closings."""

    period_key: str
    functional_currency: str
    reporting_currency: str
    lines: tuple[ReportingLine, ...]

    def amount(self, kind: str) -> int:
        """Σ reporting amounts of the lines of ``kind``."""
        return sum(line.amount_reporting for line in self.lines if line.kind == kind)


def translate_to_reporting(
    lines: Sequence[FunctionalLine],
    *,
    currencies: CurrencyTable,
    functional_currency: str,
    reporting_currency: str,
    rates: RateIndex,
    period: PeriodLike,
    previous_period: PeriodLike | None = None,
) -> ReportingTranslation:
    """Translate one rollforward of ``period`` into the reporting currency (S12-R-18)."""
    openings = [line for line in lines if line.kind == OPENING_BALANCE]
    flows = [line for line in lines if line.kind == FLOW]
    closings = [line for line in lines if line.kind == CLOSING_BALANCE]
    if len(openings) > 1 or len(closings) > 1:
        raise ValueError("a rollforward has at most one opening and one closing balance")
    opening_fn = sum(line.amount for line in openings)
    closing_fn = sum(line.amount for line in closings)
    if opening_fn + sum(line.amount for line in flows) != closing_fn:
        raise ValueError("the functional rollforward does not foot: opening + flows ≠ closing")
    if openings and previous_period is None:
        raise ValueError("an opening balance needs the previous period's closing rate")
    mu_fn = currencies[functional_currency].minor_unit
    mu_rep = currencies[reporting_currency].minor_unit
    pair = Rates(rates.rates, functional_currency, reporting_currency)
    try:
        opening_rate = (
            pair.period_rate(CLOSING, previous_period)
            if openings and previous_period is not None
            else None
        )
        average = pair.period_rate(AVERAGE, period) if flows else None
        closing = pair.period_rate(CLOSING, period) if closings else None
    except RateMissing as missing:
        raise EngineError(
            "FX_RATE_MISSING",
            "a reporting-currency rate is absent from the pinned rate set",
            detail=missing.detail,
        ) from missing

    def translated(line: FunctionalLine, view: RateView) -> ReportingLine:
        return ReportingLine(
            label=line.label,
            kind=line.kind,
            amount_functional=line.amount,
            amount_reporting=to_functional(line.amount, view, mu_fn, mu_rep),
            rate_type=view.rate_type,
            rate=view.value,
            rate_key=view.rate_key,
            version_key=view.version_key,
        )

    out_openings = [translated(line, opening_rate) for line in openings if opening_rate]
    out_flows = [translated(line, average) for line in flows if average]
    out_closings = [translated(line, closing) for line in closings if closing]
    scale = 10**mu_fn
    exact = Fraction(0)
    if closing is not None:
        exact += Fraction(closing_fn, scale) * closing.value
    if opening_rate is not None:
        exact -= Fraction(opening_fn, scale) * opening_rate.value
    if average is not None:
        exact -= sum((Fraction(line.amount, scale) for line in flows), Fraction(0)) * average.value
    translation = round_half_up(exact, mu_rep)
    before = sum(line.amount_reporting for line in out_openings + out_flows)
    after = sum(line.amount_reporting for line in out_closings)
    residue = after - before - translation
    effects = [
        ReportingLine(TRANSLATION, TRANSLATION, 0, translation, None, None, None, None),
        ReportingLine(ROUNDING, ROUNDING, 0, residue, None, None, None, None),
    ]
    return ReportingTranslation(
        period_key=period.period_key,
        functional_currency=functional_currency,
        reporting_currency=reporting_currency,
        lines=tuple(out_openings + out_flows + effects + out_closings),
    )
