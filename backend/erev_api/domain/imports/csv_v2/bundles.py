"""CSV v2 template ``bundles``: ``PUT /products/{id}/bundle-components`` per bundle (04 T-IMP-01,
NC-19, T-REF-21; API-R-23; BUILD_SPEC DIN-9).

[J] L5-1-Q-22: column ``product_code`` names the bundle (the path member ``{id}``), and each row
is one component row of API-S-BundleComponents with the bundle repeated; the rows of one bundle
replace its component rows.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from erev_api.db.tables import product
from erev_api.domain.imports.csv_v2.framework import (
    Applied,
    ApplyContext,
    CsvRow,
    CsvTemplate,
    Plan,
    flatten,
    grouped,
    row_model,
    unflatten,
)
from erev_api.domain.reference.commands import put_bundle_components
from erev_api.enums import SourceObjectType
from erev_api.problems import Problem
from erev_api.schemas.products import BundleComponentIn, BundleComponentsIn

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = ["COLUMNS", "ROW_MODEL", "TEMPLATE", "BundleIn"]

CODE: Final = "bundles"
BUNDLE_UNKNOWN: Final = "No product has the bundle code {code}."


class BundleIn(BaseModel):
    """The component rows of one bundle (L5-1-Q-22)."""

    model_config = ConfigDict(extra="forbid")

    product_code: str
    lines: list[BundleComponentIn]


COLUMNS: Final = tuple(flatten(BundleIn))
ROW_MODEL: Final = row_model("CsvBundlesRow", COLUMNS)
# The rows of one product code make one bundle; it has no header member beside its key, so its
# rows repeat nothing (05 IPL-05 rev 1.210).
KEY: Final = ("product_code",)


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per bundle in worksheet order."""
    return [
        Plan(
            key=code,
            rows=tuple(members),
            body={
                "product_code": code,
                "lines": [unflatten(row.normalized).get("lines", {}) for row in members],
            },
        )
        for (code,), members in grouped(rows, KEY).items()
    ]


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """``put_bundle_components`` of the bundle."""
    del context
    body = BundleIn.model_validate(dict(plan.body))
    found = uow.session.execute(
        select(product.c.id).where(product.c.code == body.product_code)
    ).scalar_one_or_none()
    if found is None:
        raise Problem("validation-failed", BUNDLE_UNKNOWN.format(code=body.product_code))
    stored = put_bundle_components(
        uow, product_id=UUID(str(found)), body=BundleComponentsIn(components=body.lines)
    )
    by_key = {
        (item.component_product_id, item.valid_from, item.sequence): item.id
        for item in stored.components
    }
    applied = Applied()
    for row, line in zip(plan.rows, body.lines, strict=True):
        component_id = by_key[(line.component_product_id, line.valid_from, line.sequence)]
        applied.targets.append(("product_bundle_component", component_id))
        applied.row_targets[row.id] = [("product_bundle_component", component_id)]
    return applied


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.PRODUCT,
    target_type="product_bundle_component",
    key_column="product_code",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
    group_key=KEY,
)
