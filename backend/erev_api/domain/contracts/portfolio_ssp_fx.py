"""Convert preview SSP weights without rounding them to monetary posting precision."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal, localcontext

from erev_api.problems import Problem
from erev_api.schemas.portfolios import PortfolioSspConversionOut
from erev_engine.bundle import FxRateInput
from erev_engine.stages.s12_fx_entities.rates import RateMissing, Rates


def convert(
    amount: Decimal,
    source: str,
    target: str,
    effective_date: date,
    rates: Sequence[FxRateInput],
) -> PortfolioSspConversionOut:
    if not amount.is_finite() or amount < 0:
        raise Problem("validation-failed", "SSP weights must be finite and nonnegative.")
    try:
        selected = Rates(rates, source, target).spot(effective_date)
    except RateMissing as error:
        raise Problem(
            "validation-failed",
            f"Publish a direct {source}/{target} spot rate "
            "on or before the estimate effective date.",
        ) from error
    rate = Decimal(selected.text)
    original = next(
        (
            r
            for r in rates
            if r.rate_key == selected.rate_key and r.version_key == selected.version_key
        ),
        None,
    )
    if source != target and (original is None or not selected.rate_key or not selected.version_key):
        raise Problem(
            "validation-failed", "An original published SSP conversion source is required."
        )
    with localcontext() as context:
        context.prec = max(60, len(amount.as_tuple().digits) + len(rate.as_tuple().digits) + 2)
        converted = format(amount * rate, "f")
    return PortfolioSspConversionOut(
        original_ssp=format(amount, "f"),
        source_currency=source,
        target_currency=target,
        converted_ssp=converted,
        rate=selected.text,
        effective_date=effective_date,
        rate_key=selected.rate_key,
        rate_version_key=selected.version_key,
        rate_date=original.effective_date if original is not None else None,
    )
