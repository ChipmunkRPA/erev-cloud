"""Reporting equivalents rounded once per entity/period/measure, with source-level pennies."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any
from uuid import UUID

from erev_engine.money import minor_to_decimal, round_half_up

from erev_api.domain.reports import reporting_currency, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.bbr_sources import Contribution
from erev_api.domain.reports.tie_outs import EntityRef, PeriodRef
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

Rates = Mapping[tuple[UUID, UUID], reporting_currency.Translation]


def period_for(source: Contribution, measure: str, periods: Sequence[PeriodRef]) -> PeriodRef:
    found = [
        p
        for p in periods
        if (
            p.id == source.period_id
            if measure == "revenue"
            else p.start <= source.effective_date <= p.end
        )
    ]
    if len(found) != 1:
        raise Problem("invalid-transition", "Reporting contribution requires one original period.")
    return found[0]


def rates_for(
    uow: UnitOfWork,
    params: ReportParams,
    sources: Mapping[str, Sequence[Contribution]],
    entities: Sequence[EntityRef],
    periods: Mapping[UUID, Sequence[PeriodRef]],
    journal: Sequence[Mapping[str, Any]],
) -> dict[tuple[UUID, UUID], reporting_currency.Translation]:
    needed = {
        (s.entity_id, period_for(s, measure, periods[s.entity_id]).id)
        for measure, rows in sources.items()
        for s in rows
    }
    needed.update((UUID(str(row["entity_id"])), UUID(str(row["period_id"]))) for row in journal)
    by_entity = {entity.id: entity for entity in entities}
    by_period = {(entity, p.id): p for entity, rows in periods.items() for p in rows}
    result = {}
    for entity_id, period_id in sorted(needed, key=lambda item: (str(item[0]), str(item[1]))):
        result[(entity_id, period_id)] = reporting_currency.rates_for_period(
            uow.session,
            params,
            tenant_id=uow.principal.tenant_id,
            entities=(by_entity[entity_id],),
            periods={entity_id: by_period[(entity_id, period_id)]},
            rate_type="average",
            evidence_key=f"bbr_reporting_rate_v1:{entity_id}:{period_id}",
        )
    return result


def translate(
    sources: Mapping[str, Sequence[Contribution]],
    entities: Sequence[EntityRef],
    periods: Mapping[UUID, Sequence[PeriodRef]],
    rates: Rates,
) -> dict[str, tuple[Contribution, ...]]:
    """Signed largest-remainder rounding; no allocation of accounting source ownership."""
    functional = {e.id: e.functional_currency for e in entities}
    result = {}
    for measure, rows in sources.items():
        groups: dict[tuple[UUID, UUID], list[Contribution]] = {}
        for source in rows:
            period = period_for(source, measure, periods[source.entity_id])
            groups.setdefault((source.entity_id, period.id), []).append(source)
        valued: list[Contribution] = []
        for (entity_id, period_id), group in sorted(groups.items(), key=lambda item: str(item[0])):
            rate = rates[(entity_id, period_id)]
            fact = rate.rates[entity_id]
            if fact["base_currency"] != functional[entity_id]:
                raise Problem(
                    "invalid-transition", "Reporting rate has a different functional basis."
                )
            minor = tie_outs.minor_unit(rate.currency)
            group.sort(
                key=lambda s: (
                    str(s.source_id),
                    s.source_type,
                    str(s.contract_id),
                    s.effective_date,
                )
            )
            exact = []
            originals = []
            for source in group:
                amount = source.functional_amount
                if amount is None and source.currency == functional[entity_id]:
                    amount = source.amount
                if amount is None or (
                    source.functional_amount is not None
                    and source.functional_currency != functional[entity_id]
                ):
                    raise Problem(
                        "invalid-transition", "Reporting requires original functional valuation."
                    )
                originals.append(amount)
                exact.append(Fraction(amount) * Fraction(fact["rate"]) * 10**minor)
            floors = [value.numerator // value.denominator for value in exact]
            target = round_half_up(sum(exact, Fraction(0)) / 10**minor, minor)
            pennies = target - sum(floors)
            order = sorted(range(len(group)), key=lambda i: (-(exact[i] - floors[i]), i))
            for index in order[:pennies]:
                floors[index] += 1
            valued.extend(
                replace(
                    source,
                    currency=rate.currency,
                    amount=minor_to_decimal(value, minor),
                    functional_currency=functional[entity_id],
                    functional_amount=original,
                )
                for source, value, original in zip(group, floors, originals, strict=True)
            )
        result[measure] = tuple(valued)
    return result


def journal_totals(rows: Sequence[Mapping[str, Any]], rates: Rates) -> dict[str, Decimal]:
    with localcontext() as context:
        context.prec = 80
        return _journal_totals(rows, rates)


def _journal_totals(rows: Sequence[Mapping[str, Any]], rates: Rates) -> dict[str, Decimal]:
    amounts: dict[tuple[UUID, UUID], Decimal] = {}
    for row in rows:
        key = UUID(str(row["entity_id"])), UUID(str(row["period_id"]))
        rate = rates[key]
        if row["functional_currency"] != rate.rates[key[0]]["base_currency"]:
            raise Problem("invalid-transition", "Journal reporting currency basis differs.")
        amounts[key] = (
            amounts.get(key, Decimal(0))
            + Decimal(row["credit_functional"])
            - Decimal(row["debit_functional"])
        )
    result: dict[str, Decimal] = {}
    for key, amount in amounts.items():
        rate = rates[key]
        result[rate.currency] = result.get(rate.currency, Decimal(0)) + rate.amount(key[0], amount)
    return result
