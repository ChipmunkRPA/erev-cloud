"""As-of currency projection of RPO disclosures, with conserved bands and exclusions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from erev_engine.formulas import rpo_bands
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import legal_entity
from erev_api.domain.reports import reporting_currency, tie_outs
from erev_api.domain.reports.builders import ReportParams

if TYPE_CHECKING:
    from erev_api.domain.reports.builders.rpo import ObligationRpo


def translate(
    session: Session,
    params: ReportParams,
    rows: Sequence[ObligationRpo],
    entities: Sequence[tie_outs.EntityRef],
    periods: Mapping[UUID, tie_outs.PeriodRef],
) -> tuple[tuple[ObligationRpo, ...], tuple[Mapping[str, Any], ...]]:
    """Translate gross RPO and its exclusion, then apportion net rounding to sources.

    These are closing-rate disclosures of future consideration, not historical
    deferred-revenue balances or journal amounts. The store remains in transaction
    currency for independent rollforward reconciliation and retained source reads.
    """
    if not rows or params.parameters.get("currency_view", "transaction") == "transaction":
        return tuple(rows), ()
    tenant_id = session.execute(
        select(legal_entity.c.tenant_id).where(legal_entity.c.id == rows[0].ob.entity_id)
    ).scalar_one()
    by_id = {entity.id: entity for entity in entities}
    rates: dict[str, reporting_currency.Translation] = {}

    def rate(entity: tie_outs.EntityRef, target: str | None) -> reporting_currency.Translation:
        period = periods[entity.id]
        key = (
            f"rpo_fx_v1:{entity.id}:{entity.functional_currency}:"
            f"{target or 'reporting'}:{period.key}"
        )
        if key not in rates:
            rates[key] = reporting_currency.rates_for_period(
                session,
                params,
                tenant_id=tenant_id,
                entities=(entity,),
                periods={entity.id: period},
                evidence_key=key,
                target_currency=target,
            )
        return rates[key]

    result = []
    for item in rows:
        entity = by_id[item.ob.entity_id]
        translations = []
        currency = entity.functional_currency
        if item.ob.currency != currency:
            translations.append(
                rate(replace(entity, functional_currency=item.ob.currency), currency)
            )
        if params.parameters.get("currency_view") == "reporting":
            translations.append(rate(entity, None))
            currency = translations[-1].currency
        gross, excluded = item.total + item.excluded, item.excluded
        for translation in translations:
            gross = translation.amount(entity.id, gross)
            excluded = translation.amount(entity.id, excluded)
        total = gross - excluded
        source_scale = 10 ** tie_outs.minor_unit(item.ob.currency)
        target_scale = 10 ** tie_outs.minor_unit(currency)
        bands = rpo_bands(int(total * target_scale), [int(v * source_scale) for v in item.placed])
        contributors: list[tuple[str, UUID, Decimal, int, bool]] = []
        for index, amount in enumerate(bands):
            held = [entry for entry in item.contributors if entry[3] == index]
            if not held:
                if amount:
                    raise tie_outs.invalid("currency_view", "RPO band has no source contributors.")
                continue
            shares = rpo_bands(amount, [int(entry[2] * source_scale) for entry in held])
            contributors.extend(
                (entry[0], entry[1], Decimal(share) / target_scale, index, entry[4])
                for entry, share in zip(held, shares, strict=True)
            )
        result.append(
            replace(
                item,
                ob=replace(item.ob, currency=currency),
                total=total,
                excluded=excluded,
                placed=tuple(Decimal(value) / target_scale for value in bands),
                current=sum((entry[2] for entry in contributors if entry[4]), tie_outs.ZERO),
                contributors=tuple(contributors),
            )
        )
    return tuple(result), tuple(
        {"entity_id": str(entity_id), **fact}
        for translation in rates.values()
        for entity_id, fact in translation.rates.items()
    )
