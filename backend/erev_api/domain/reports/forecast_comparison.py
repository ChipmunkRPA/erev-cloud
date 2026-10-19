"""RPT-40 projection of frozen forecast revenue and refresh-bound posted actuals.

Callers must supply separately captured sources. Scenario recomputation output is not an
actuals source. This module does not fetch live journals or convert currencies.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Any, Literal
from uuid import UUID

from erev_engine.stages.s01_canonicalize import encode_key

from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import money
from erev_api.problems import Problem


@dataclass(frozen=True)
class Revenue:
    entity_id: UUID
    contract_external_id: str
    revenue_category: str
    period_key: str
    currency: str
    amount: Decimal


def compare(
    forecast: Sequence[Revenue],
    actuals: Sequence[Revenue],
    *,
    horizon: Sequence[str],
    entity_ids: Sequence[UUID],
    actuals_known_at: datetime,
    row_dimension: Literal["CONTRACT", "REVENUE_CATEGORY"] = "CONTRACT",
    from_period_key: str | None = None,
    to_period_key: str | None = None,
) -> ReportData:
    """Union populations, signed actual-minus-forecast, and independent currency totals.

    The ordered horizon comes from the saved run, never from string sorting fiscal keys.
    Zero posted net revenue still counts as actuals; a population with no posted rows does not.
    """
    if (
        not horizon
        or any(not key for key in horizon)
        or len(set(horizon)) != len(horizon)
        or not entity_ids
        or len(set(entity_ids)) != len(entity_ids)
        or actuals_known_at.utcoffset() is None
        or row_dimension not in ("CONTRACT", "REVENUE_CATEGORY")
    ):
        raise Problem("validation-failed", "Invalid forecast comparison scope.")
    first = horizon[0] if from_period_key is None else from_period_key
    last = horizon[-1] if to_period_key is None else to_period_key
    if first not in horizon or last not in horizon or horizon.index(first) > horizon.index(last):
        raise Problem("validation-failed", "Choose periods inside the forecast horizon.")
    selected = tuple(horizon[horizon.index(first) : horizon.index(last) + 1])
    scope = set(entity_ids)
    key = "contract_external_id" if row_dimension == "CONTRACT" else "revenue_category"
    prefix = "contract" if row_dimension == "CONTRACT" else "revenue_category"
    values: dict[tuple[str, str, str], list[Decimal]] = {}
    actual_count = 0
    with localcontext() as context:
        context.prec = 80
        for side, population in enumerate((forecast, actuals)):
            for source in population:
                if source.entity_id not in scope or source.period_key not in selected:
                    continue
                label = getattr(source, key)
                if not label or not source.currency or not source.amount.is_finite():
                    raise Problem("precondition-failed", "Incomplete forecast comparison source.")
                # Currency minor units are shared with the normal report output writers.
                money(source.amount, source.currency)
                amounts = values.setdefault(
                    (label, source.period_key, source.currency), [Decimal(0), Decimal(0)]
                )
                amounts[side] += source.amount
                if side == 1:
                    actual_count += 1
        rows: list[dict[str, Any]] = []
        totals: dict[str, list[Decimal]] = {}
        # No invented zero actuals before the first production posting in the chosen horizon.
        if actual_count:
            currencies: dict[tuple[str, str], set[str]] = {}
            for label, period, currency in values:
                currencies.setdefault((label, period), set()).add(currency)
            for (label, period, currency), amounts in sorted(
                values.items(),
                key=lambda item: (item[0][0], selected.index(item[0][1]), item[0][2]),
            ):
                row_key = f"{prefix}:{encode_key(label)}:{encode_key(period)}"
                if len(currencies[(label, period)]) > 1:
                    row_key += f":{encode_key(currency)}"
                row = _row(row_key, key, label, period, currency, amounts)
                rows.append(row)
                aggregate = totals.setdefault(currency, [Decimal(0), Decimal(0)])
                aggregate[0] += Decimal(row["forecast_revenue"]["amount"])
                aggregate[1] += Decimal(row["actual_revenue"]["amount"])
            for currency, amounts in sorted(totals.items()):
                rows.append(_row(f"TOTAL:{currency}", key, None, None, currency, amounts))
        return ReportData(
            columns=(
                Column(
                    key, "Contract" if row_dimension == "CONTRACT" else "Revenue category", "text"
                ),
                Column("period_key", "Period", "code"),
                Column("currency", "Currency", "code"),
                Column("forecast_revenue", "Forecast revenue", "money"),
                Column("actual_revenue", "Actual revenue", "money"),
                Column("variance", "Variance", "money"),
                Column("variance_percent", "Variance %", "decimal", empty_text="—"),
            ),
            rows=tuple(rows),
            control_totals={
                "actuals_known_at": actuals_known_at.isoformat(),
                "actual_source_rows": actual_count,
                "horizon_periods": list(selected),
                "empty_title": None if actual_count else "No actuals yet for the forecast horizon",
                "empty_description": None
                if actual_count
                else (
                    "Refresh the scenario after production periods close to compare actual "
                    "revenue with the forecast."
                ),
                "revenue_by_currency": {
                    currency: {
                        "forecast": money(amounts[0], currency),
                        "actual": money(amounts[1], currency),
                        "variance": money(amounts[1] - amounts[0], currency),
                    }
                    for currency, amounts in sorted(totals.items())
                },
            },
        )


def _row(
    row_key: str,
    key: str,
    label: str | None,
    period: str | None,
    currency: str,
    amounts: Sequence[Decimal],
) -> dict[str, Any]:
    predicted, posted = (money(amount, currency) for amount in amounts)
    base, actual = Decimal(predicted["amount"]), Decimal(posted["amount"])
    variance = actual - base
    return {
        "row_key": row_key,
        key: label,
        "period_key": period,
        "currency": currency,
        "forecast_revenue": predicted,
        "actual_revenue": posted,
        "variance": money(variance, currency),
        "variance_percent": None if base == 0 else format(variance / base * 100, ".2f"),
    }
