"""Monthly RPO disclosure translation with explicit FX, rounding and source differences."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Any
from uuid import UUID

from erev_engine.money import minor_to_decimal, round_half_up

from erev_api.domain.reports import reporting_currency, rpo_currency, tie_outs
from erev_api.domain.reports.builders import ReportParams, rpo
from erev_api.uow import UnitOfWork


def project(
    uow: UnitOfWork,
    params: ReportParams,
    store: rpo.Store,
    entities: Sequence[tie_outs.EntityRef],
    periods: Mapping[UUID, tuple[tie_outs.PeriodRef, ...]],
    before: Mapping[UUID, tie_outs.PeriodRef | None],
    applied: Mapping[UUID, frozenset[str]],
) -> tuple[tuple[rpo.ContractLines, ...], list[dict[str, Any]], bool]:
    session = uow.session
    cache: dict[tuple[UUID, str, UUID, str], tuple[reporting_currency.Translation, ...]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    totals: dict[tuple[str, str, str], rpo.ContractLines] = {}
    source_unexplained = False
    codes = (*rpo.ROLLFORWARD_LINES, "ROUNDING")

    def chain(
        entity: tie_outs.EntityRef, source: str, at: tie_outs.PeriodRef, kind: str
    ) -> tuple[reporting_currency.Translation, ...]:
        key = (entity.id, source, at.id, kind)
        if key not in cache:
            legs: list[tuple[tie_outs.EntityRef, str | None]] = []
            if source != entity.functional_currency:
                legs.append(
                    (replace(entity, functional_currency=source), entity.functional_currency)
                )
            if params.parameters.get("currency_view") == "reporting":
                legs.append((entity, None))
            translations = []
            for base, target in legs:
                # Share closing evidence with the standalone RPO disclosure.
                name = (
                    f"rpo_fx_v1:{entity.id}:{base.functional_currency}:"
                    f"{target or 'reporting'}:{at.key}"
                )
                if kind != "closing":
                    name += f":{kind}"
                translation = reporting_currency.rates_for_period(
                    session,
                    params,
                    tenant_id=uow.principal.tenant_id,
                    entities=(base,),
                    periods={entity.id: at},
                    rate_type=kind,
                    evidence_key=name,
                    target_currency=target,
                )
                translations.append(translation)
                evidence[name] = {"entity_id": str(entity.id), **translation.rates[entity.id]}
            cache[key] = tuple(translations)
        return cache[key]

    def convert(
        entity_id: UUID, amount: Decimal, legs: Sequence[reporting_currency.Translation]
    ) -> Decimal:
        for leg in legs:
            amount = leg.amount(entity_id, amount)
        return amount

    def factor(entity_id: UUID, legs: Sequence[reporting_currency.Translation]) -> Fraction:
        result = Fraction(1)
        for leg in legs:
            result *= Fraction(str(leg.rates[entity_id]["rate"]))
        return result

    def endpoint(
        entity: tie_outs.EntityRef, day: date, at: tie_outs.PeriodRef | None
    ) -> dict[tuple[str, str], tuple[Decimal, Decimal]]:
        rows = rpo.rows_at(store, as_of={entity.id: day}, bands=rpo.DEFAULT_BANDS, applied=applied)
        rows = tuple(item for item in rows if item.exemption is None)
        if at is None and any(item.total or item.excluded for item in rows):
            raise tie_outs.invalid(
                "currency_view", "Nonzero opening RPO requires a preceding period."
            )
        if at is None:
            return {}
        translated, _ = rpo_currency.translate(session, params, rows, (entity,), {entity.id: at})
        result: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}
        for raw, shown in zip(rows, translated, strict=True):
            key = (raw.ob.external_id, raw.ob.currency)
            a, b = result.get(key, (tie_outs.ZERO, tie_outs.ZERO))
            result[key] = a + raw.total, b + shown.total
        return result

    for entity in entities:
        prior = before.get(entity.id)
        for index, period in enumerate(periods[entity.id]):
            start = period.start - timedelta(days=1)
            opening = endpoint(entity, start, prior)
            closing = endpoint(entity, period.end, period)
            monthly = rpo.rollforward_lines(
                store, ranges={entity.id: (start, period.end)}, applied=applied
            )
            for item in monthly:
                key = (item.external_id, item.currency)
                raw_open, shown_open = opening.get(key, (tie_outs.ZERO, tie_outs.ZERO))
                raw_close, shown_close = closing.get(key, (tie_outs.ZERO, tie_outs.ZERO))
                if raw_open != item.lines["OPENING"] or raw_close != item.lines["CLOSING"]:
                    raise tie_outs.invalid(
                        "currency_view", "RPO movement endpoints disagree with disclosure sources."
                    )
                close_legs = chain(entity, item.currency, period, "closing")
                average_legs = chain(entity, item.currency, period, "average")
                open_legs = (
                    chain(entity, item.currency, prior, "closing") if prior is not None else ()
                )
                target = close_legs[-1].currency if close_legs else entity.functional_currency
                values = {
                    code: convert(entity.id, item.lines[code], average_legs)
                    for code in rpo.ROLLFORWARD_LINES
                }
                values["OPENING"], values["CLOSING"] = shown_open, shown_close
                average = factor(entity.id, average_legs)
                fx = Fraction(raw_close) * (factor(entity.id, close_legs) - average) - Fraction(
                    raw_open
                ) * (factor(entity.id, open_legs) - average)
                minor = tie_outs.minor_unit(target)
                values["FX"] += minor_to_decimal(round_half_up(fx, minor), minor)
                values["ROUNDING"] = (
                    shown_close
                    - shown_open
                    - sum((values[code] for code in rpo.MOVEMENTS), tie_outs.ZERO)
                    - values["UNEXPLAINED"]
                )
                source_unexplained |= item.lines["UNEXPLAINED"] != 0
                total_key = (item.external_id, entity.code, target)
                previous = totals.get(total_key)
                summed = (
                    dict.fromkeys(codes, tie_outs.ZERO)
                    if previous is None
                    else dict(previous.lines)
                )
                for code in codes:
                    if code == "OPENING" and index != 0:
                        continue
                    if code == "CLOSING" and index != len(periods[entity.id]) - 1:
                        continue
                    summed[code] += values[code]
                totals[total_key] = replace(item, currency=target, lines=summed)
            prior = period
    return tuple(totals[key] for key in sorted(totals)), list(evidence.values()), source_unexplained
