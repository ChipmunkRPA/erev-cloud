"""CSV v2 template ``cost_events``: one ``COST_INCURRED`` per row (04 T-IMP-01, NC-19, §16.3
``COST_INCURRED``; PRD WLD-F-25, WLD-F-27, J-10.1, J-12.1, J-12-ALT-1; 03 REQ-CST-001 CSV channel;
BUILD_SPEC DIN-9, BS3-D-07; L5-1-Q-19)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from functools import partial
from typing import TYPE_CHECKING, Any, Final, Literal

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

__all__ = ["COLUMNS", "CROSS_RULE", "ROW_MODEL", "TEMPLATE", "CostEventIn"]

CODE: Final = "cost_events"
HEADER_MEMBERS: Final = frozenset({"contract", "effective_date"})


class CostEventIn(BaseModel):
    """``COST_INCURRED`` of ``POST /contracts/{id}/events`` as a row (L5-1-Q-19)."""

    model_config = ConfigDict(extra="forbid")

    contract: str
    effective_date: date
    purpose: Literal["PROGRESS_INPUT", "COST_TO_OBTAIN", "COST_TO_FULFILL", "WARRANTY_CLAIM"]
    obligation_key: str | None = None
    amount: MoneyIn
    is_wasted: bool | None = None
    is_uninstalled_material: bool | None = None
    payee: str | None = None
    plan_code: str | None = None
    is_incremental: bool | None = None
    has_clawback: bool | None = None
    cost_adjustment: Literal["CLAWBACK"] | None = None


COLUMNS: Final = tuple(flatten(CostEventIn))
ROW_MODEL: Final = row_model("CsvCostEventsRow", COLUMNS)
CROSS_RULE: Final = recorded.contract_findings


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    return recorded.row_plans(rows)


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    body: dict[str, Any] = dict(plan.body)
    CostEventIn.model_validate(body)
    key = body.get("obligation_key")
    item = EventAppendItemIn(
        event_type=ContractEventType.COST_INCURRED,
        effective_date=date.fromisoformat(str(body["effective_date"])),
        obligation_key=None if key is None else str(key),
        payload={name: value for name, value in body.items() if name not in HEADER_MEMBERS},
    )
    return recorded.append(uow, plan, context=context, items=[item])


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.ORDER,
    target_type="contract_event",
    key_column="contract",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
    reconcile_amounts=partial(
        recorded.reconcile_amounts,
        event_type="COST_INCURRED",
        amount_field="amount",
        identity_fields=(
            "obligation_key",
            "purpose",
            "is_wasted",
            "is_uninstalled_material",
            "payee",
            "plan_code",
        ),
    ),
)
