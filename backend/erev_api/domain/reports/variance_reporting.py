"""Reporting-rate basis authenticated by the selected lock's currency snapshots.

No live rate lookup, inverse rate or inferred average is permitted. The average is
optional only until a nonzero revenue contribution needs it. Closing rates from
RPO and balances must identify the same retained conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from erev_engine.money import round_half_up

from erev_api.domain.reports import locked, tie_outs
from erev_api.domain.reports.evidence_close import FrozenClose
from erev_api.problems import Problem


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Close variance reporting rates: {detail}")


@dataclass(frozen=True)
class Basis:
    functional_currency: str
    currency: str
    period_key: str
    period_end: date
    closing: Fraction
    average: Fraction | None
    evidence_sha256: str

    def __post_init__(self) -> None:
        if self.closing <= 0 or (self.average is not None and self.average <= 0):
            raise _refuse("conversion rates must be positive.")

    def amount(self, amount: Fraction, *, revenue: bool = False) -> Fraction:
        rate = self.average if revenue else self.closing
        if not amount:
            return Fraction(0)
        if rate is None:
            raise _refuse("nonzero revenue requires a retained average rate.")
        places = tie_outs.minor_unit(self.currency)
        return Fraction(round_half_up(amount * rate, places), 10**places)


def from_close(source: FrozenClose, *, functional_currency: str, period_end: date) -> Basis:
    controls: dict[str, dict[str, Any]] = {}
    hashes = {}
    for report in source.reports:
        dataset = report.dataset
        if dataset.kind not in {"WATERFALL", "CONTRACT_BALANCES", "RPO"}:
            continue
        if dataset.kind in controls or dataset.lock_id != source.scope.lock_id:
            raise _refuse("duplicated or foreign monetary snapshot.")
        locked.verify(dataset)
        _, _, metadata = locked.currency_rows(dataset, "reporting")
        if metadata is None:
            raise _refuse("the lock did not retain reporting-rate controls.")
        controls[dataset.kind] = metadata
        hashes[dataset.kind] = dataset.file_sha256
    if set(controls) != {"WATERFALL", "CONTRACT_BALANCES", "RPO"}:
        raise _refuse("all three monetary snapshots are required.")
    currency = controls["CONTRACT_BALANCES"].get("reporting_currency")
    if not isinstance(currency, str):
        raise _refuse("the balances snapshot has no reporting currency.")
    tie_outs.minor_unit(currency)
    selected: dict[str, dict[str, Any]] = {}
    for kind, metadata in controls.items():
        facts = metadata.get("translation_rates", [])
        if not isinstance(facts, list):
            raise _refuse("invalid retained rate list.")
        own_closing = False
        for fact in facts:
            if not isinstance(fact, dict):
                raise _refuse("invalid retained rate record.")
            if (fact.get("base_currency"), fact.get("quote_currency")) != (
                functional_currency,
                currency,
            ):
                continue  # transaction-to-functional forecasts are a different conversion
            if fact.get("period_key") != source.scope.period_key:
                continue
            rate_type = fact.get("rate_type")
            if rate_type not in {"closing", "average"}:
                raise _refuse("invalid retained rate type.")
            try:
                rate = Decimal(fact["rate"])
                if (
                    fact["period_end"] != period_end.isoformat()
                    or not rate.is_finite()
                    or rate <= 0
                ):
                    raise ValueError("inconsistent rate")
                if currency == functional_currency:
                    if (
                        rate != 1
                        or fact.get("rate_id") is not None
                        or fact.get("version_id") is not None
                    ):
                        raise ValueError("invalid identity rate")
                else:
                    UUID(fact["rate_id"])
                    UUID(fact["version_id"])
            except (KeyError, TypeError, ValueError, ArithmeticError) as error:
                raise _refuse("invalid retained conversion identity or amount.") from error
            identity = {
                name: fact.get(name)
                for name in (
                    "base_currency",
                    "quote_currency",
                    "period_key",
                    "period_end",
                    "rate_type",
                    "rate",
                    "rate_id",
                    "version_id",
                    "rate_cutoff",
                )
            }
            if rate_type in selected and selected[rate_type] != identity:
                raise _refuse("monetary snapshots disagree on the retained conversion.")
            selected[rate_type] = identity
            own_closing |= rate_type == "closing"
        if kind == "CONTRACT_BALANCES" and not own_closing:
            raise _refuse("balances require their own retained closing rate.")
    if "closing" not in selected:
        raise _refuse("a retained closing rate is required.")
    return Basis(
        functional_currency,
        currency,
        source.scope.period_key,
        period_end,
        Fraction(selected["closing"]["rate"]),
        Fraction(selected["average"]["rate"]) if "average" in selected else None,
        sha256_hex({"lock_id": str(source.scope.lock_id), "datasets": hashes, "rates": selected}),
    )


def for_close(source: FrozenClose) -> Basis:
    """Resolve entity currency and calendar from the balances rate evidence, never live settings."""
    candidates = [r.dataset for r in source.reports if r.dataset.kind == "CONTRACT_BALANCES"]
    if len(candidates) != 1:
        raise _refuse("one balances snapshot is required.")
    dataset = locked.verify(candidates[0])
    _, _, metadata = locked.currency_rows(dataset, "reporting")
    if metadata is None:
        raise _refuse("the lock did not retain reporting-rate controls.")
    rates = metadata.get("translation_rates")
    if not isinstance(rates, list) or len(rates) != 1 or not isinstance(rates[0], dict):
        raise _refuse("one entity/period closing conversion is required.")
    try:
        functional = rates[0]["base_currency"]
        if not isinstance(functional, str):
            raise ValueError("invalid currency")
        tie_outs.minor_unit(functional)
        end = date.fromisoformat(rates[0]["period_end"])
    except (KeyError, TypeError, ValueError) as error:
        raise _refuse("invalid retained currency/calendar basis.") from error
    return from_close(source, functional_currency=functional, period_end=end)
