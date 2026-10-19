"""RPT-39 billing, period-end balance and journal-preview projections.

Inputs come from the existing cutoff-bound billing, balance and sealed-subledger readers.
These projections never convert currencies or infer billing from a balance movement.
"""

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, localcontext
from typing import Any
from uuid import UUID

from erev_engine.stages.s01_canonicalize import encode_key

from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders.bbr_sources import Contribution
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import PeriodRef
from erev_api.problems import Problem

BALANCES = ("contract_liability", "contract_asset", "unbilled_receivable")


def _horizon(periods: Sequence[PeriodRef]) -> None:
    if not periods or len({p.key for p in periods}) != len(periods):
        raise Problem("validation-failed", "Choose a nonempty, unique forecast horizon.")
    if any(first.end >= second.start for first, second in zip(periods, periods[1:], strict=False)):
        raise Problem("validation-failed", "Forecast periods must be in chronological order.")


def billing(
    contributions: Sequence[Contribution],
    *,
    periods: Sequence[PeriodRef],
    contract_labels: Mapping[UUID, str],
    entity_periods: Mapping[UUID, Sequence[PeriodRef]] | None = None,
) -> ReportData:
    """Net effective billing by contract/period, including credits and excluding voids upstream."""
    _horizon(periods)
    if entity_periods is not None:
        for entity_horizon in entity_periods.values():
            _horizon(entity_horizon)
            if tuple(p.key for p in entity_horizon) != tuple(p.key for p in periods):
                raise Problem("validation-failed", "Entity forecast period keys must agree.")
    values: dict[tuple[str, str], dict[str, Decimal]] = {}
    with localcontext() as context:
        context.prec = 80
        for source in contributions:
            horizon = periods if entity_periods is None else entity_periods.get(source.entity_id)
            if horizon is None:
                raise Problem("precondition-failed", "A billing entity has no forecast calendar.")
            period = next((p for p in horizon if p.start <= source.effective_date <= p.end), None)
            if period is None:
                continue
            label = contract_labels.get(source.contract_id)
            if label is None:
                raise Problem(
                    "precondition-failed", "A forecast billing contract has no retained label."
                )
            totals = values.setdefault((label, source.currency), {})
            tie_outs.add(totals, period.key, source.amount)
        by_currency: dict[str, dict[str, Decimal]] = {}
        rows: list[dict[str, Any]] = []
        for (contract, currency), amounts in sorted(values.items()):
            total = sum(amounts.values(), Decimal(0))
            row = {
                "row_key": f"contract:{encode_key(contract)}:{currency}",
                "contract_external_id": contract,
                "currency": currency,
                **{
                    f"period:{p.key}": tie_outs.money(amounts.get(p.key, Decimal(0)), currency)
                    for p in periods
                },
                "total": tie_outs.money(total, currency),
            }
            rows.append(row)
            aggregate = by_currency.setdefault(currency, {})
            for key, amount in amounts.items():
                tie_outs.add(aggregate, key, amount)
        for currency, amounts in sorted(by_currency.items()):
            rows.append(
                {
                    "row_key": f"TOTAL:{currency}",
                    "contract_external_id": None,
                    "currency": currency,
                    **{
                        f"period:{p.key}": tie_outs.money(amounts.get(p.key, Decimal(0)), currency)
                        for p in periods
                    },
                    "total": tie_outs.money(sum(amounts.values(), Decimal(0)), currency),
                }
            )
    return ReportData(
        columns=(
            Column("contract_external_id", "Contract", "code"),
            Column("currency", "Currency", "code"),
            *(Column(f"period:{p.key}", p.name, "money") for p in periods),
            Column("total", "Total", "money"),
        ),
        rows=tuple(rows),
        control_totals={
            "billing_by_currency": {
                row["currency"]: row["total"] for row in rows if row["row_key"].startswith("TOTAL:")
            }
        },
    )


def balances(ends: Sequence[tuple[date, ReportData]]) -> ReportData:
    """One stock per entity/currency/period end; never sum stocks across different ends."""
    if len({end for end, _ in ends}) != len(ends):
        raise Problem("validation-failed", "A forecast balance period end was supplied twice.")
    values: dict[tuple[date, str, str], dict[str, Decimal]] = {}
    with localcontext() as context:
        context.prec = 80
        for end, dataset in ends:
            for row in dataset.rows:
                if str(row["row_key"]).startswith("TOTAL:"):
                    continue
                if not row.get("entity_code") or not row.get("currency"):
                    raise Problem(
                        "precondition-failed", "A forecast balance has no entity or currency."
                    )
                entity, currency = str(row["entity_code"]), str(row["currency"])
                aggregate = values.setdefault((end, entity, currency), {})
                for key in BALANCES:
                    value = row.get(key)
                    if not isinstance(value, Mapping) or value.get("currency") != currency:
                        raise Problem(
                            "precondition-failed",
                            "A forecast balance has a missing or inconsistent currency amount.",
                        )
                    tie_outs.add(aggregate, key, Decimal(str(value["amount"])))
        totals: dict[tuple[date, str], dict[str, Decimal]] = {}
        rows: list[dict[str, Any]] = []
        for (end, entity, currency), amounts in sorted(values.items()):
            rows.append(
                {
                    "row_key": f"balance:{end}:{encode_key(entity)}:{currency}",
                    "period_end": end,
                    "entity_code": entity,
                    "currency": currency,
                    **{key: tie_outs.money(amounts[key], currency) for key in BALANCES},
                }
            )
            aggregate = totals.setdefault((end, currency), {})
            for key, amount in amounts.items():
                tie_outs.add(aggregate, key, amount)
        for (end, currency), amounts in sorted(totals.items()):
            rows.append(
                {
                    "row_key": f"TOTAL:{end}:{currency}",
                    "period_end": end,
                    "entity_code": None,
                    "currency": currency,
                    **{key: tie_outs.money(amounts[key], currency) for key in BALANCES},
                }
            )
    return ReportData(
        columns=(
            Column("period_end", "Period end", "date"),
            Column("entity_code", "Entity", "code"),
            Column("currency", "Currency", "code"),
            Column("contract_liability", "Contract liability", "money"),
            Column("contract_asset", "Contract asset", "money"),
            Column("unbilled_receivable", "Unbilled receivable", "money"),
        ),
        rows=tuple(rows),
        control_totals={
            "balances_by_period_currency": {
                f"{end}:{currency}": {
                    key: tie_outs.money(amounts[key], currency) for key in BALANCES
                }
                for (end, currency), amounts in sorted(totals.items())
            }
        },
    )


def journals(lines: ReportData, *, periods: Sequence[PeriodRef], currency_view: str) -> ReportData:
    """Preview sealed signed ledger amounts; this never creates or exports a journal batch."""
    _horizon(periods)
    if currency_view not in {"transaction", "functional"}:
        raise Problem(
            "validation-failed", "Journal preview requires a supported stored currency basis."
        )
    currency_key, amount_key = (
        ("txn_currency", "amount_txn")
        if currency_view == "transaction"
        else ("functional_currency", "amount_functional")
    )
    selected = {p.key: index for index, p in enumerate(periods)}
    values: dict[tuple[str, str, str], dict[str, Decimal]] = {}
    with localcontext() as context:
        context.prec = 80
        for row in lines.rows:
            period_key = str(row["period_key"])
            if period_key not in selected:
                continue
            currency, role = row.get(currency_key), row.get("account_role")
            if not currency or not role or row.get(amount_key) is None:
                raise Problem(
                    "precondition-failed",
                    "A forecast journal line has no currency, role or amount.",
                )
            amount = Decimal(str(row[amount_key]))
            if not amount:
                continue
            aggregate = values.setdefault(
                (period_key, str(role), str(currency)), {"debit": Decimal(0), "credit": Decimal(0)}
            )
            tie_outs.add(aggregate, "debit" if amount > 0 else "credit", abs(amount))
        totals: dict[str, dict[str, Decimal]] = {}
        rows: list[dict[str, Any]] = []
        for (period_key, role, currency), amounts in sorted(
            values.items(), key=lambda item: (selected[item[0][0]], item[0][1], item[0][2])
        ):
            rows.append(
                {
                    "row_key": f"journal:{encode_key(period_key)}:{encode_key(role)}:{currency}",
                    "period_key": period_key,
                    "account_role": role,
                    "currency": currency,
                    **{key: tie_outs.money(amounts[key], currency) for key in ("debit", "credit")},
                }
            )
            aggregate = totals.setdefault(currency, {})
            for key, amount in amounts.items():
                tie_outs.add(aggregate, key, amount)
        for currency, amounts in sorted(totals.items()):
            rows.append(
                {
                    "row_key": f"TOTAL:{currency}",
                    "period_key": None,
                    "account_role": None,
                    "currency": currency,
                    **{key: tie_outs.money(amounts[key], currency) for key in ("debit", "credit")},
                }
            )
    return ReportData(
        columns=(
            Column("period_key", "Period", "code"),
            Column("account_role", "Account role", "code"),
            Column("currency", "Currency", "code"),
            Column("debit", "Debit", "money"),
            Column("credit", "Credit", "money"),
        ),
        rows=tuple(rows),
        control_totals={
            "journal_by_currency": {
                currency: {
                    key: tie_outs.money(amounts[key], currency) for key in ("debit", "credit")
                }
                for currency, amounts in sorted(totals.items())
            }
        },
    )
