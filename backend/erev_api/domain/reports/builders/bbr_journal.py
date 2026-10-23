"""BBR revenue comparator using the journal extract's retained lifecycle evidence."""

from collections.abc import Iterable, Mapping
from dataclasses import replace
from decimal import Decimal, localcontext
from typing import Any
from uuid import UUID

from erev_api.domain.reports.builders import ReportParams, extract_journal_lines
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def selected_rows(
    uow: UnitOfWork, params: ReportParams, period_ids: Iterable[UUID]
) -> tuple[Mapping[str, Any], ...]:
    wanted = {str(p) for p in period_ids}
    journal = extract_journal_lines.build(uow, replace(params, parameters={"mode": "FULL"}))
    return tuple(
        row
        for row in journal.rows
        if row["period_id"] in wanted and row["account_role"] == "REVENUE"
    )


def totals(
    uow: UnitOfWork, params: ReportParams, *, period_ids: Iterable[UUID], view: str
) -> dict[str, Decimal]:
    if view not in {"transaction", "functional"}:
        raise Problem("validation-failed", "Choose transaction or functional currency.")
    rows = selected_rows(uow, params, period_ids)
    result: dict[str, Decimal] = {}
    suffix = "txn" if view == "transaction" else "functional"
    with localcontext() as context:
        context.prec = 80
        for row in rows:
            currency = row[f"{suffix}_currency"] if suffix == "txn" else row["functional_currency"]
            amount = Decimal(row[f"credit_{suffix}"]) - Decimal(row[f"debit_{suffix}"])
            result[currency] = result.get(currency, Decimal(0)) + amount
    return result
