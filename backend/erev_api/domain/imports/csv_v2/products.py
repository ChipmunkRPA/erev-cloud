"""CSV v2 template ``products``: one ``POST /products`` request per row (04 T-IMP-01, NC-19,
T-REF-20; API-R-23; BUILD_SPEC DIN-9).

Members that hold arrays or free-form objects (``disaggregation``, ``policy_values``) are not
columns (L5-1-Q-4).
"""

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
from erev_api.domain.reference.commands import create_product
from erev_api.enums import SourceObjectType
from erev_api.schemas.products import ProductIn

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = ["COLUMNS", "ROW_MODEL", "TEMPLATE"]

CODE: Final = "products"
COLUMNS: Final = tuple(flatten(ProductIn))
ROW_MODEL: Final = row_model("CsvProductsRow", COLUMNS)


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per row, keyed by the product code."""
    return [
        Plan(
            key=str(row.normalized.get("code") or row.row_number),
            rows=(row,),
            body=unflatten(row.normalized),
        )
        for row in rows
    ]


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """``create_product``."""
    del context
    body: Any = ProductIn.model_validate(dict(plan.body))
    created = create_product(uow, body=body)
    applied = Applied()
    applied.targets.append(("product", created.id))
    for row in plan.rows:
        applied.row_targets[row.id] = [("product", created.id)]
    return applied


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.PRODUCT,
    target_type="product",
    key_column="code",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
)
