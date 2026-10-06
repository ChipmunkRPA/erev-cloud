"""Stage 05 SSP currency conversion (ENGINE_SPEC S05-R-05; POL-079 ``ssp.currency_conversion``).

Private to stage 05. An entry in a currency other than the transaction currency is converted at
the ``spot`` rate at the pricing date; the rate key is recorded and never re-converted (32-43).
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine.money import to_fraction
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import RawLine
from erev_engine.stages.state import BookContext

__all__ = ["CONVERT_AT_INCEPTION_SPOT", "CURRENCY_SPECIFIC_BOOK_REQUIRED", "Conversion", "rate"]

POLICY_CODE: Final = "ssp.currency_conversion"
CONVERT_AT_INCEPTION_SPOT: Final = "CONVERT_AT_INCEPTION_SPOT"
CURRENCY_SPECIFIC_BOOK_REQUIRED: Final = "CURRENCY_SPECIFIC_BOOK_REQUIRED"
SPOT: Final = "spot"  # E-51


@dataclass(frozen=True, slots=True)
class Conversion:
    """The factor from entry currency to transaction currency, or the finding that blocks it."""

    factor: Fraction | None
    rate_key: str | None
    finding: str | None  # "SSP_KEY_NOT_FOUND" | "FX_RATE_MISSING"


def rate(
    ctx: BookContext, st: IdentifiedState, line: RawLine, entry_currency: str, at: date
) -> Conversion:
    """S05-R-05 for an entry in ``entry_currency`` priced at ``at``.

    Same currency: factor 1. ``CONVERT_AT_INCEPTION_SPOT``: the ``spot`` rate with base = entry
    currency and quote = transaction currency, else 1 ÷ the inverse rate; of several rates the one
    with the greatest ``effective_date`` on or before ``at`` (ties: greatest ``version_key``), with
    the direct rate preferred at equal dates. No rate gives ``FX_RATE_MISSING``.
    ``CURRENCY_SPECIFIC_BOOK_REQUIRED`` gives ``SSP_KEY_NOT_FOUND``. Another value raises
    ``ValueError`` (CV-17).
    """
    quote = ctx.txn_currency
    if entry_currency == quote:
        return Conversion(Fraction(1), None, None)
    option = ctx.policies.value(
        POLICY_CODE, contract=line.contract_key, obligation=line.subject_key
    )
    if option == CURRENCY_SPECIFIC_BOOK_REQUIRED:
        return Conversion(None, None, "SSP_KEY_NOT_FOUND")
    if option != CONVERT_AT_INCEPTION_SPOT:
        raise ValueError(f"{POLICY_CODE} holds an unknown option {option!r} (CV-17)")
    best: tuple[tuple[date, bool, str], Fraction, str] | None = None
    for fx in st.canonical.fx.rates:
        if fx.rate_type != SPOT or fx.effective_date > at:
            continue
        direct = (fx.base_currency, fx.quote_currency) == (entry_currency, quote)
        inverse = (fx.base_currency, fx.quote_currency) == (quote, entry_currency)
        if not (direct or inverse):
            continue
        value = to_fraction(fx.rate)
        if value <= 0:
            raise ValueError(f"{fx.rate_key}: a spot rate must be positive (CV-45)")
        rank = (fx.effective_date, direct, fx.version_key)
        if best is None or rank > best[0]:
            best = (rank, value if direct else 1 / value, fx.rate_key)
    if best is None:
        return Conversion(None, None, "FX_RATE_MISSING")
    return Conversion(best[1], best[2], None)
