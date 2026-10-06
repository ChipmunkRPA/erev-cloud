"""CSV v2 template ``customers``: one ``POST /customers`` request per row (04 T-IMP-01, NC-19,
T-REF-19; BUILD_SPEC DIN-3)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final

from erev_api.domain.imports.csv_v2.framework import (
    Applied,
    ApplyContext,
    CsvRow,
    CsvTemplate,
    Plan,
    flatten,
    row_model,
    unflatten,
)
from erev_api.domain.reference.commands import create_customer
from erev_api.enums import SourceObjectType, SourceSystem
from erev_api.schemas.customers import CustomerIn

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = ["COLUMNS", "ROW_MODEL", "TEMPLATE"]

CODE: Final = "customers"
COLUMNS: Final = tuple(flatten(CustomerIn))
ROW_MODEL: Final = row_model("CsvCustomersRow", COLUMNS)


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per row, keyed by the customer code."""
    return [
        Plan(
            key=str(row.normalized.get("code") or row.row_number),
            rows=(row,),
            body=unflatten(row.normalized),
        )
        for row in rows
    ]


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """``create_customer`` with source system ``CSV_V2``."""
    body: Any = CustomerIn.model_validate(dict(plan.body))
    created = create_customer(uow, body=body, source_system=SourceSystem.CSV_V2)
    applied = Applied()
    applied.targets.append(("customer", created.id))
    for row in plan.rows:
        applied.row_targets[row.id] = [("customer", created.id)]
    return applied


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.CUSTOMER,
    target_type="customer",
    key_column="code",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
)
