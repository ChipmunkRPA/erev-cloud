"""Pinned reporting-currency rates and exact translation of functional balances.

Uses the same approved-rate admission and period selection as the engine. No
inversion/triangulation and no substitution of current rates on retained reruns.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from fractions import Fraction
from typing import Any
from uuid import UUID

from erev_engine.money import minor_to_decimal, round_half_up
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import fx_rate, tenant
from erev_api.domain.contracts.bundles import fx_rates_in_force
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams

EVIDENCE = "reporting_currency_rates_v1"


@dataclass(frozen=True)
class Translation:
    currency: str
    rates: Mapping[UUID, Mapping[str, Any]]

    def amount(self, entity_id: UUID, amount: Decimal) -> Decimal:
        rate = Fraction(str(self.rates[entity_id]["rate"]))
        minor = tie_outs.minor_unit(self.currency)
        return minor_to_decimal(round_half_up(Fraction(amount) * rate, minor), minor)

    def balances(self, rows: Sequence[tie_outs.BalanceRow]) -> tuple[tie_outs.BalanceRow, ...]:
        result = []
        for row in rows:
            if row.currency != self.rates[row.entity_id]["base_currency"]:
                raise tie_outs.invalid("currency_view", "Translation requires functional balances.")
            result.append(
                replace(
                    row,
                    currency=self.currency,
                    values={
                        name: self.amount(row.entity_id, row.value(name))
                        for name in tie_outs.BALANCE_MEASURES
                    },
                )
            )
        return tuple(result)


def rates_for_period(
    session: Session,
    params: ReportParams,
    *,
    tenant_id: UUID,
    entities: Sequence[tie_outs.EntityRef],
    periods: Mapping[UUID, tie_outs.PeriodRef | None],
    locked: tie_outs.LockedEnds | None = None,
    rate_type: str = "closing",
    evidence_key: str = EVIDENCE,
) -> Translation:
    if params.binding is not None:
        evidence = params.binding.evidence.get(evidence_key)
        if not isinstance(evidence, dict):
            raise tie_outs.invalid(
                "currency_view", "Retained reporting-currency rates are missing."
            )
    else:
        target = str(
            session.execute(
                select(tenant.c.reporting_currency).where(tenant.c.id == tenant_id)
            ).scalar_one()
        ).strip()
        evidence = {"currency": target, "rates": {}}
        cutoff = tie_outs.cutoff_for(session, params)
        for entity in entities:
            at = periods.get(entity.id)
            if at is None:
                raise tie_outs.invalid(
                    "currency_view", "Reporting currency requires a dated endpoint."
                )
            endpoint = None if locked is None else locked.at(entity.id, at)
            rate_cutoff = cutoff if endpoint is None else endpoint.frozen_at
            fact: dict[str, Any] = {
                "rate_cutoff": rate_cutoff.isoformat(),
                "base_currency": entity.functional_currency,
                "quote_currency": target,
                "period_key": at.key,
                "period_end": at.end.isoformat(),
                "rate_type": rate_type,
                "rate": "1",
                "rate_id": None,
                "version_id": None,
            }
            if entity.functional_currency != target:
                candidates = list(
                    session.execute(
                        fx_rates_in_force(rate_cutoff).where(
                            fx_rate.c.rate_type == rate_type,
                            fx_rate.c.base_currency == entity.functional_currency,
                            fx_rate.c.quote_currency == target,
                        )
                    ).mappings()
                )
                matched = [
                    row
                    for row in candidates
                    if row["period_key"] == at.key and row["effective_date"] == at.end
                ]
                if not matched and rate_type == "closing":
                    matched = [row for row in candidates if row["effective_date"] == at.end]
                if len(matched) != 1:
                    raise tie_outs.invalid(
                        "currency_view",
                        f"One approved {rate_type} rate is required for "
                        f"{entity.functional_currency}/{target} at {at.key}.",
                    )
                selected = matched[0]
                fact.update(
                    rate=str(selected["rate"]),
                    rate_id=str(selected["id"]),
                    version_id=str(selected["fx_rate_set_version_id"]),
                )
            evidence["rates"][str(entity.id)] = fact
        if params.sources is not None:
            params.sources.record_evidence(evidence_key, evidence)
    try:
        target = str(evidence["currency"])
        tie_outs.minor_unit(target)
        rates = {}
        for entity in entities:
            at = periods[entity.id]
            fact = evidence["rates"][str(entity.id)]
            rate = Decimal(fact["rate"])
            if (
                at is None
                or fact["base_currency"] != entity.functional_currency
                or fact["quote_currency"] != target
                or fact["period_key"] != at.key
                or fact["period_end"] != at.end.isoformat()
                or fact["rate_type"] != rate_type
                or not rate.is_finite()
                or rate <= 0
            ):
                raise ValueError("inconsistent rate")
            if entity.functional_currency == target:
                if rate != 1 or fact["rate_id"] is not None or fact["version_id"] is not None:
                    raise ValueError("invalid identity rate")
            else:
                UUID(fact["rate_id"])
                UUID(fact["version_id"])
            rates[entity.id] = fact
        return Translation(target, rates)
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        raise tie_outs.invalid(
            "currency_view", "Reporting-currency evidence is inconsistent."
        ) from error


def closing(
    session: Session,
    params: ReportParams,
    *,
    tenant_id: UUID,
    entities: Sequence[tie_outs.EntityRef],
    periods: Mapping[UUID, tie_outs.PeriodRef | None],
    locked: tie_outs.LockedEnds | None = None,
) -> Translation:
    return rates_for_period(
        session, params, tenant_id=tenant_id, entities=entities, periods=periods, locked=locked
    )
