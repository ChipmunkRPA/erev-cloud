"""RPT-37 period presentation over attributed monetary contributions.

The source adapter must supply all four measures before publication. Revenue uses its posting
period (including late-event carries); bookings and billing use their effective date. Fiscal
quarters and years come from the entity calendar, not calendar-month arithmetic.
"""

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, localcontext
from typing import Any, Final
from uuid import UUID

from erev_engine.stages.s01_canonicalize import encode_key

from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders.bbr_sources import Contribution
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import EntityRef, PeriodRef
from erev_api.problems import Problem

CODE: Final = "bookings_billings_revenue"
MEASURES: Final = ("booked_new", "booked_modifications", "billings", "revenue")
COLUMNS: Final = (
    Column("period_label", "Period", "text"),
    Column("entity_code", "Entity", "code"),
    Column("currency", "Currency", "code"),
    Column("booked_new", "Booked, new contracts", "money"),
    Column("booked_modifications", "Booked, modifications", "money"),
    Column("billings", "Billings", "money"),
    Column("revenue", "Revenue", "money"),
)


def _bucket(period: PeriodRef, granularity: str) -> tuple[str, str]:
    if granularity == "MONTH":
        return period.key, period.name
    if granularity == "YEAR":
        return f"FY{period.fiscal_year}", f"FY{period.fiscal_year}"
    quarter = period.quarter_no or (period.period_no - 1) // 3 + 1
    return f"FY{period.fiscal_year}-Q{quarter}", f"FY{period.fiscal_year} Q{quarter}"


def dataset(
    contributions: Mapping[str, Sequence[Contribution]],
    *,
    entities: Sequence[EntityRef],
    periods: Mapping[UUID, Sequence[PeriodRef]],
    granularity: str,
    currency_view: str,
    journal_revenue: Mapping[str, Decimal],
) -> ReportData:
    """Aggregate attributed sources; the journal comparator must use the selected currency view.

    An absent measure is an incomplete adapter, never an implicit zero-valued population.
    """
    if set(contributions) != set(MEASURES):
        raise Problem("invalid-transition", "BBR requires all four attributed measures.")
    if granularity not in {"MONTH", "QUARTER", "YEAR"}:
        raise tie_outs.invalid("granularity", "Choose Month, Quarter or Year.")
    if currency_view not in {"transaction", "functional"}:
        raise tie_outs.invalid("currency_view", "Choose a transaction or functional currency view.")
    by_entity = {e.id: e for e in entities}
    values: dict[tuple[UUID, str, str], dict[str, Decimal]] = {}
    labels: dict[tuple[UUID, str], str] = {}
    starts: dict[tuple[UUID, str], date] = {}
    expected_periods = {entity: {p.id: p for p in found} for entity, found in periods.items()}
    with localcontext() as context:
        context.prec = 80
        for measure in MEASURES:
            for source in contributions[measure]:
                entity = by_entity.get(source.entity_id)
                if entity is None:
                    raise Problem("forbidden", "BBR contribution exceeds the report entity scope.")
                wanted = periods[entity.id]
                if measure == "revenue":
                    if source.period_id is None:
                        raise Problem("invalid-transition", "Revenue has no posting period.")
                    period = expected_periods[entity.id].get(source.period_id)
                else:
                    period = next(
                        (p for p in wanted if p.start <= source.effective_date <= p.end), None
                    )
                if period is None:
                    continue
                currency, amount = source.currency, source.amount
                if currency_view == "functional":
                    currency = entity.functional_currency
                    if source.functional_amount is not None:
                        if source.functional_currency != currency:
                            raise Problem(
                                "invalid-transition",
                                "Functional currency basis differs from the entity.",
                            )
                        amount = source.functional_amount
                    elif source.currency != currency:
                        raise Problem(
                            "invalid-transition",
                            "The contribution lacks a functional FX valuation.",
                        )
                bucket, label = _bucket(period, granularity)
                key = (entity.id, bucket, currency)
                labels[(entity.id, bucket)] = label
                starts[(entity.id, bucket)] = min(
                    starts.get((entity.id, bucket), period.start), period.start
                )
                values.setdefault(key, dict.fromkeys(MEASURES, Decimal(0)))[measure] += amount
        totals: dict[str, dict[str, Decimal]] = {}
        rows: list[dict[str, Any]] = []
        # Currency splitting keeps transaction-view totals meaningful for multi-currency entities.
        currencies: dict[tuple[UUID, str], set[str]] = {}
        for entity_id, bucket, currency in values:
            currencies.setdefault((entity_id, bucket), set()).add(currency)
        for (entity_id, bucket, currency), amounts in sorted(
            values.items(),
            key=lambda item: (
                starts[(item[0][0], item[0][1])],
                by_entity[item[0][0]].code,
                item[0][2],
            ),
        ):
            entity = by_entity[entity_id]
            row_key = f"period:{encode_key(bucket)}:{encode_key(entity.code)}"
            if len(currencies[(entity_id, bucket)]) > 1:
                row_key += f":{currency}"
            rows.append(
                {
                    "row_key": row_key,
                    "period_label": labels[(entity_id, bucket)],
                    "entity_code": entity.code,
                    "currency": currency,
                    **{m: tie_outs.money(amounts[m], currency) for m in MEASURES},
                }
            )
            total = totals.setdefault(currency, dict.fromkeys(MEASURES, Decimal(0)))
            for measure in MEASURES:
                total[measure] += amounts[measure]
    actual_revenue = {c: values["revenue"] for c, values in totals.items()}
    return ReportData(
        COLUMNS,
        tuple(rows),
        {
            "row_count": len(rows),
            **{
                f"{m}_total": tie_outs.by_currency({c: v[m] for c, v in totals.items()})
                for m in MEASURES
            },
        },
        tie_out_results=(
            tie_outs.compared("TO_BBR_EQ_JE_REVENUE", journal_revenue, actual_revenue),
        ),
    )
