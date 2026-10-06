"""Stage 12 rates and conversion (ENGINE_SPEC_B §12.2.1; S12-R-01, S12-R-02; BUILD_SPEC END-1).

Private to stage 12 (DG-ENG-07). A rate converts one unit of the transaction currency into the
functional currency: base = transaction currency, quote = functional currency. Only explicit rates
of the pinned rate set are used, with no inversion or triangulation (research 06 §9.5). ``spot`` is
the latest rate on or before the date; ``average`` and ``closing`` are the rates of the period
(T-REF-12 ``period_key``), or for ``closing`` the rate dated the period end. A same-currency
conversion has rate 1 and no rate id. A missing rate raises ``RateMissing``; ``run`` records the
``FX_RATE_MISSING`` finding and continues with the other units (S12-R-01; CV-42). Every functional
amount is round(transaction exact × rate) at the functional minor unit (S12-R-02). Standard library
only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine.bundle import FxRateInput
from erev_engine.dates import PeriodLike
from erev_engine.money import round_half_up, to_fraction
from erev_engine.trace import SourceRef

__all__ = [
    "AVERAGE",
    "CLOSING",
    "SPOT",
    "RateMissing",
    "RateView",
    "Rates",
    "to_functional",
]

SPOT: Final = "spot"  # E-51
AVERAGE: Final = "average"
CLOSING: Final = "closing"
_RATE_TYPES: Final = frozenset({SPOT, AVERAGE, CLOSING})


@dataclass(frozen=True, slots=True)
class RateView:
    """One conversion rate with the natural keys of the row used (REQ-FX-001, REQ-FX-006)."""

    value: Fraction
    text: str  # plain decimal, as pinned (NUMERIC(28,12))
    rate_type: str  # E-51
    rate_key: str | None  # None only for a same-currency conversion
    version_key: str | None
    base: str
    quote: str

    def inputs(self) -> list[str | SourceRef]:
        """The rate as a trace source reference (ENGINE_SPEC_B §12.5), or no input at rate 1."""
        if self.rate_key is None or self.version_key is None:
            return []
        detail = {
            "base": self.base,
            "quote": self.quote,
            "rate_type": self.rate_type,
            "value": self.text,
            "version_key": self.version_key,
        }
        return [SourceRef("fx_rate", self.rate_key, detail=detail)]


class RateMissing(Exception):
    """A rate the conversion needs is absent from the pinned rate set (S12-R-01)."""

    def __init__(self, detail: Mapping[str, str]) -> None:
        super().__init__("FX_RATE_MISSING")
        self.detail = dict(sorted(detail.items()))
        self.event_key: str | None = None


class Rates:
    """Rate lookups of one (transaction, functional) currency pair over the pinned rows."""

    def __init__(self, rows: Sequence[FxRateInput], base: str, quote: str) -> None:
        self.base = base
        self.quote = quote
        selected = []
        for row in rows:
            if (row.base_currency, row.quote_currency) != (base, quote):
                continue
            if row.rate_type not in _RATE_TYPES:
                raise ValueError(f"{row.rate_key}: unknown rate type {row.rate_type!r} (E-51)")
            if to_fraction(row.rate) <= 0:
                raise ValueError(f"{row.rate_key}: a rate must be positive (CV-45)")
            selected.append(row)
        self._rows = tuple(selected)

    @property
    def identity(self) -> bool:
        return self.base == self.quote

    def spot(self, on: date) -> RateView:
        """The latest ``spot`` rate on or before ``on``; ties: greatest version, then rate key."""
        if self.identity:
            return self._one(SPOT)
        candidates = [r for r in self._rows if r.rate_type == SPOT and r.effective_date <= on]
        if not candidates:
            raise RateMissing(self._missing(SPOT, date=on.isoformat()))
        return self._view(
            max(candidates, key=lambda r: (r.effective_date, r.version_key, r.rate_key))
        )

    def period_rate(self, kind: str, period: PeriodLike) -> RateView:
        """The one ``average`` or ``closing`` rate of ``period`` (S12-R-01)."""
        if kind not in (AVERAGE, CLOSING):
            raise ValueError(f"a period rate is average or closing, not {kind!r}")
        if self.identity:
            return self._one(kind)
        typed = [r for r in self._rows if r.rate_type == kind]
        candidates = [r for r in typed if r.period_key == period.period_key]
        if not candidates and kind == CLOSING:
            candidates = [r for r in typed if r.effective_date == period.end_date]
        if len(candidates) != 1:
            raise RateMissing(self._missing(kind, period_key=period.period_key))
        return self._view(candidates[0])

    def _one(self, kind: str) -> RateView:
        return RateView(Fraction(1), "1", kind, None, None, self.base, self.quote)

    def _view(self, row: FxRateInput) -> RateView:
        text = format(row.rate, "f")
        return RateView(
            to_fraction(row.rate),
            text,
            row.rate_type,
            row.rate_key,
            row.version_key,
            self.base,
            self.quote,
        )

    def _missing(self, kind: str, **where: str) -> dict[str, str]:
        return {
            "base": self.base,
            "quote": self.quote,
            "rate_type": kind,
            "rule": "S12-R-01",
            **where,
        }


def to_functional(
    amount_minor: int, rate: RateView, txn_minor_unit: int, fn_minor_unit: int
) -> int:
    """round(transaction exact × rate) at the functional minor unit (S12-R-02)."""
    return round_half_up(Fraction(amount_minor, 10**txn_minor_unit) * rate.value, fn_minor_unit)
