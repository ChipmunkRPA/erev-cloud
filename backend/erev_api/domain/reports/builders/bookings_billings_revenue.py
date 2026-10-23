"""RPT-37 period presentation over attributed monetary contributions.

The source adapter must supply all four measures before publication. Revenue uses its posting
period (including late-event carries); bookings and billing use their effective date. Fiscal
quarters and years come from the entity calendar, not calendar-month arithmetic.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from datetime import date
from decimal import Decimal, localcontext
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from erev_engine.stages.s01_canonicalize import encode_key
from sqlalchemy.orm import Session

from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import (
    ReportParams,
    bbr_bookings,
    bbr_currency,
    bbr_journal,
    bbr_modifications,
    bbr_reporting,
    bbr_sources,
    unknown_filter,
)
from erev_api.domain.reports.builders.bbr_sources import Contribution
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import EntityRef, PeriodRef
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

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
    if currency_view not in {"transaction", "functional", "reporting"}:
        raise tie_outs.invalid(
            "currency_view", "Choose transaction, functional or reporting currency."
        )
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
            **(
                {
                    "currency_view": "reporting",
                    "translation_basis": "entity_period_average",
                    "rounding_basis": "entity_period_measure_signed_largest_remainder",
                }
                if currency_view == "reporting"
                else {}
            ),
            **{
                f"{m}_total": tie_outs.by_currency({c: v[m] for c, v in totals.items()})
                for m in MEASURES
            },
        },
        tie_out_results=(
            tie_outs.compared("TO_BBR_EQ_JE_REVENUE", journal_revenue, actual_revenue),
        ),
    )


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    if params.period_lock_id is not None:
        raise Problem("validation-failed", "Bookings, billings and revenue has no lock dataset.")
    for name in params.filters:
        if name != "entity_code":
            raise unknown_filter(name, ("entity_code",))
    entities = tie_outs.entities(uow.session, params.entity_ids, params=params)
    if "entity_code" in params.filters:
        entities = tuple(e for e in entities if e.code == params.filters["entity_code"])
    book = tie_outs.book_of(uow.session, params)
    scoped = replace(params, entity_ids=tuple(e.id for e in entities), book_code=book)
    calendars = tie_outs.calendars(uow.session, entities, params=params)
    periods = {
        e.id: tie_outs.range_of(params, calendars[e.id], e, year_default=True) for e in entities
    }
    all_periods = [p for rows in periods.values() for p in rows]
    period_ids = [p.id for p in all_periods]
    raw = bbr_sources.read(uow, scoped, period_ids=period_ids)
    contributions: dict[str, Sequence[Contribution]] = {
        "booked_new": bbr_bookings.new_contracts(raw),
        "billings": bbr_sources.billings(raw),
        "revenue": bbr_sources.revenue(raw),
        "booked_modifications": (),
    }
    if all_periods:
        modified = bbr_modifications.read(
            uow,
            scoped,
            start=min(p.start for p in all_periods),
            end=max(p.end for p in all_periods),
        )
        contributions["booked_modifications"] = bbr_modifications.values(modified)
    # Restrict before FX valuation: out-of-range events cannot demand irrelevant rates.
    for measure, rows in contributions.items():
        contributions[measure] = tuple(
            r
            for r in rows
            if any(
                (
                    r.period_id == p.id
                    if measure == "revenue"
                    else p.start <= r.effective_date <= p.end
                )
                for p in periods[r.entity_id]
            )
        )
    view = str(params.parameters.get("currency_view") or "functional")
    if view in {"functional", "reporting"}:
        contributions = dict(bbr_currency.functional(uow, scoped, contributions, entities))
    if view == "reporting":
        journal = bbr_journal.selected_rows(uow, scoped, period_ids)
        rates = bbr_reporting.rates_for(uow, scoped, contributions, entities, periods, journal)
        contributions = dict(bbr_reporting.translate(contributions, entities, periods, rates))
        expected = bbr_reporting.journal_totals(journal, rates)
    else:
        expected = bbr_journal.totals(uow, scoped, period_ids=period_ids, view=view)
    tie_outs.record_evidence(
        params,
        "bbr_aggregation_inputs_v1",
        json.loads(
            canonical_bytes(
                {measure: [asdict(row) for row in rows] for measure, rows in contributions.items()}
            )
        ),
    )
    return dataset(
        contributions,
        entities=entities,
        periods=periods,
        granularity=str(params.parameters.get("granularity") or "MONTH"),
        currency_view=view,
        journal_revenue=expected,
    )


def cell(
    session: Session, params: ReportParams, row_key: str, column_key: str
) -> tuple[Mapping[str, str], list[dict[str, Any]]]:
    if column_key not in MEASURES:
        raise tie_outs.invalid("column_key", "Choose a bookings, billings or revenue amount.")
    raw = tie_outs.bound_evidence(params, "bbr_aggregation_inputs_v1")
    contributions = {}
    for measure in MEASURES:
        contributions[measure] = tuple(
            Contribution(
                source_type=r["source_type"],
                source_id=UUID(r["source_id"]),
                contract_id=UUID(r["contract_id"]),
                entity_id=UUID(r["entity_id"]),
                effective_date=date.fromisoformat(r["effective_date"]),
                currency=r["currency"],
                amount=Decimal(r["amount"]),
                period_id=UUID(r["period_id"]) if r["period_id"] else None,
                functional_currency=r["functional_currency"],
                functional_amount=Decimal(r["functional_amount"])
                if r["functional_amount"] is not None
                else None,
                basis_ids=tuple(UUID(i) for i in r["basis_ids"]),
            )
            for r in raw[measure]
        )
    entities = tie_outs.entities(session, params.entity_ids, params=params)
    if "entity_code" in params.filters:
        entities = tuple(e for e in entities if e.code == params.filters["entity_code"])
    calendars = tie_outs.calendars(session, entities, params=params)
    periods = {
        e.id: tie_outs.range_of(params, calendars[e.id], e, year_default=True) for e in entities
    }
    view = str(params.parameters.get("currency_view") or "functional")
    granularity = str(params.parameters.get("granularity") or "MONTH")
    data = dataset(
        contributions,
        entities=entities,
        periods=periods,
        granularity=granularity,
        currency_view=view,
        journal_revenue={},
    )
    row = next((r for r in data.rows if r["row_key"] == row_key), None)
    if row is None:
        raise tie_outs.invalid("row_key", "The retained BBR report has no such row.")
    by_entity = {e.id: e for e in entities}
    items = []
    for source in contributions[column_key]:
        entity = by_entity[source.entity_id]
        period = next(
            (
                p
                for p in periods[entity.id]
                if (
                    p.id == source.period_id
                    if column_key == "revenue"
                    else p.start <= source.effective_date <= p.end
                )
            ),
            None,
        )
        if period is None:
            continue
        currency = (
            source.currency if view in {"transaction", "reporting"} else entity.functional_currency
        )
        bucket, _ = _bucket(period, granularity)
        base = f"period:{encode_key(bucket)}:{encode_key(entity.code)}"
        if row_key not in {base, f"{base}:{currency}"} or row["currency"] != currency:
            continue
        amount = (
            source.amount
            if view in {"transaction", "reporting"} or source.functional_amount is None
            else source.functional_amount
        )
        if source.source_type == "modification":
            href = f"/contracts/{source.contract_id}/modifications/{source.source_id}"
        elif source.source_type == "contract_event":
            tab = "billing" if column_key == "billings" else "history"
            href = f"/contracts/{source.contract_id}/{tab}"
        elif source.source_type == "subledger_line":
            href = f"/contracts/{source.contract_id}/journals"
        else:
            raise Problem("invalid-transition", "Unknown retained BBR contribution source.")
        details = []
        if view == "reporting":
            held = tie_outs.bound_evidence(params, f"bbr_reporting_rate_v1:{entity.id}:{period.id}")
            rate = held["rates"][str(entity.id)]
            if held["currency"] != currency or rate["base_currency"] != entity.functional_currency:
                raise Problem("invalid-transition", "Retained reporting source rate differs.")
            details = [
                f"Original functional amount: {source.functional_amount} "
                f"{entity.functional_currency}",
                f"Period average: {rate['base_currency']}/{currency} {rate['rate']}; "
                f"period: {rate['period_key']}",
                f"Rate reference: {rate['rate_id'] or 'same currency'}; "
                f"version: {rate['version_id'] or 'same currency'}",
                "Reporting equivalent; source retains its original currency. "
                "Rounded per entity/period/measure; source pennies reconcile to that total.",
            ]
        items.append(
            {
                "object_type": source.source_type,
                "id": source.source_id,
                "measure": column_key,
                "value": tie_outs.money(amount, currency),
                "href": href,
                **({"details": details} if details else {}),
            }
        )
    return row[column_key], items
