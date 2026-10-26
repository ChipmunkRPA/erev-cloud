"""Period-by-period reporting translation, using the engine's S12-R-18 projection.

Functional FIFO attribution is supplied by cumulative paths. Translation and rounding
remain separate from remeasurement and unexplained OTHER; nothing posts to the ledger.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.orm import Session

from erev_api.domain.reports import reporting_currency, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_engine.bundle import FxRateInput, PeriodInput
from erev_engine.currencies import ISO_4217
from erev_engine.money import decimal_to_minor, minor_to_decimal
from erev_engine.stages.s12_fx_entities import FunctionalLine, translate_to_reporting
from erev_engine.stages.state import RateIndex

if TYPE_CHECKING:
    from erev_api.domain.reports.builders.contract_balance_rollforward import ContractRollforward

EXTRA_LINES = ("TRANSLATION", "ROUNDING")


def engine_period(period: tie_outs.PeriodRef) -> PeriodInput:
    return PeriodInput(
        period.key, period.fiscal_year, period.period_no, period.start, period.end, ()
    )


def project(
    session: Session,
    params: ReportParams,
    *,
    tenant_id: UUID,
    entities: Sequence[tie_outs.EntityRef],
    periods: Mapping[UUID, tuple[tie_outs.PeriodRef, ...]],
    before: Mapping[UUID, tie_outs.PeriodRef | None],
    items: Sequence[ContractRollforward],
    locked: tie_outs.LockedEnds,
) -> tuple[tuple[ContractRollforward, ...], list[dict[str, Any]]]:
    rates: dict[tuple[UUID, UUID, str], reporting_currency.Translation] = {}
    evidence = []
    for entity in entities:
        prior = before[entity.id]
        requests = [(p, kind) for p in periods[entity.id] for kind in ("closing", "average")]
        if prior is not None:
            requests.append((prior, "closing"))
        for period, kind in requests:
            selected = reporting_currency.rates_for_period(
                session,
                params,
                tenant_id=tenant_id,
                entities=(entity,),
                periods={entity.id: period},
                locked=locked,
                rate_type=kind,
                evidence_key=f"rollforward_reporting_rate_v1:{entity.id}:{period.key}:{kind}",
            )
            rates[(entity.id, period.id, kind)] = selected
            evidence.append({"entity_code": entity.code, **selected.rates[entity.id]})
    result = []
    for item in items:
        selected_periods = periods[item.entity_id]
        if not selected_periods:
            raise tie_outs.invalid("currency_view", "Reporting requires a period range.")
        target = rates[(item.entity_id, selected_periods[0].id, "closing")].currency
        totals = {
            line: dict.fromkeys(tie_outs.ROLLFORWARD_BALANCES, tie_outs.ZERO)
            for line in (*item.lines, *EXTRA_LINES)
        }
        prior = before[item.entity_id]
        for index, period in enumerate(selected_periods):
            monthly = item.period_lines[period.id]
            wanted = [(period, "closing"), (period, "average")]
            if prior is not None:
                wanted.append((prior, "closing"))
            inputs = []
            for at, kind in wanted:
                selected = rates[(item.entity_id, at.id, kind)]
                if selected.currency != target:
                    raise tie_outs.invalid("currency_view", "Retained reporting currencies differ.")
                fact = selected.rates[item.entity_id]
                if item.currency != fact["base_currency"]:
                    raise tie_outs.invalid(
                        "currency_view", "Functional currency differs from rates."
                    )
                if item.currency != target:
                    inputs.append(
                        FxRateInput(
                            str(fact["rate_id"]),
                            str(fact["version_id"]),
                            kind,
                            item.currency,
                            target,
                            at.end,
                            at.key,
                            Decimal(fact["rate"]),
                        )
                    )
            for balance in tie_outs.ROLLFORWARD_BALANCES:
                lines = []
                for code, values in monthly.items():
                    if code == "OPENING" and prior is None:
                        if values[balance] != 0:
                            raise tie_outs.invalid(
                                "currency_view", "Nonzero opening requires a preceding period."
                            )
                        continue
                    lines.append(
                        FunctionalLine(
                            code,
                            code if code in {"OPENING", "CLOSING"} else "FLOW",
                            decimal_to_minor(values[balance], tie_outs.minor_unit(item.currency)),
                        )
                    )
                translated = translate_to_reporting(
                    lines,
                    currencies=ISO_4217,
                    functional_currency=item.currency,
                    reporting_currency=target,
                    rates=RateIndex(tuple(inputs)),
                    period=engine_period(period),
                    previous_period=None if prior is None else engine_period(prior),
                )
                for line in translated.lines:
                    if line.label == "OPENING" and index != 0:
                        continue
                    if line.label == "CLOSING" and index != len(selected_periods) - 1:
                        continue
                    totals[line.label][balance] += minor_to_decimal(
                        line.amount_reporting, tie_outs.minor_unit(target)
                    )
            prior = period
        members = []
        for member in item.group_members:
            member_lines = {code: dict(values) for code, values in member.lines.items()}
            for code, endpoint in (
                ("OPENING", before[item.entity_id]),
                ("CLOSING", selected_periods[-1]),
            ):
                if endpoint is None:
                    if any(member_lines[code].values()):
                        raise tie_outs.invalid(
                            "currency_view", "Member opening lacks a preceding rate."
                        )
                    continue
                selected = rates[(item.entity_id, endpoint.id, "closing")]
                member_lines[code] = {
                    balance: selected.amount(item.entity_id, value)
                    for balance, value in member_lines[code].items()
                }
            members.append(replace(member, currency=target, lines=member_lines))
        result.append(replace(item, currency=target, lines=totals, group_members=tuple(members)))
    return tuple(result), evidence
