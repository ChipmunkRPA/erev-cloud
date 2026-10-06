"""CSV v2 template ``pre_standard_revenue``: one ``PRE_STANDARD_REVENUE_RECORDED`` per row with its
signed amount (04 T-IMP-01, NC-19, §16.3; POLICIES POL-008; BUILD_SPEC DIN-9; L5-1-Q-19)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING, Any, Final

from pydantic import BaseModel, ConfigDict

from erev_api.domain.imports.csv_v2 import recorded
from erev_api.domain.imports.csv_v2.framework import (
    Applied,
    ApplyContext,
    CsvRow,
    CsvTemplate,
    Plan,
    flatten,
    row_model,
)
from erev_api.enums import ContractEventType, SourceObjectType
from erev_api.money import MoneyIn
from erev_api.schemas.events import EventAppendItemIn

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = ["COLUMNS", "CROSS_RULE", "ROW_MODEL", "TEMPLATE", "PreStandardRevenueIn"]

CODE: Final = "pre_standard_revenue"


class PreStandardRevenueIn(BaseModel):
    """``PRE_STANDARD_REVENUE_RECORDED`` of ``POST /contracts/{id}/events`` as a row."""

    model_config = ConfigDict(extra="forbid")

    contract: str
    effective_date: date
    obligation_key: str
    amount: MoneyIn  # signed (POL-008)


COLUMNS: Final = tuple(flatten(PreStandardRevenueIn))
ROW_MODEL: Final = row_model("CsvPreStandardRevenueRow", COLUMNS)
CROSS_RULE: Final = recorded.contract_findings


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    return recorded.row_plans(rows)


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    body: dict[str, Any] = dict(plan.body)
    PreStandardRevenueIn.model_validate(body)
    item = EventAppendItemIn(
        event_type=ContractEventType.PRE_STANDARD_REVENUE_RECORDED,
        effective_date=date.fromisoformat(str(body["effective_date"])),
        obligation_key=str(body["obligation_key"]),
        payload={"obligation_key": body["obligation_key"], "amount": body["amount"]},
    )
    return recorded.append(uow, plan, context=context, items=[item])


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.PROGRESS_ROW,
    target_type="contract_event",
    key_column="contract",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
)
