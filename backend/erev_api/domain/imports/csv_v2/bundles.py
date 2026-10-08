"""CSV v2 template ``bundles``: ``PUT /products/{id}/bundle-components`` per bundle (04 T-IMP-01,
NC-19, T-REF-21; API-R-23; BUILD_SPEC DIN-9).

[J] L5-1-Q-22: column ``product_code`` names the bundle (the path member ``{id}``), and each row
is one component row of API-S-BundleComponents with the bundle repeated; the rows of one bundle
replace its component rows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from erev_api.db.tables import product, product_bundle_component
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
    from sqlalchemy.orm import Session

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


def _numeric(value: Any) -> str | None:
    if value is None:
        return None
    with localcontext() as ctx:
        ctx.prec = 80
        return format(
            Decimal(str(value)).quantize(Decimal("1e-18"), rounding=ROUND_HALF_UP).normalize(),
            "f",
        )


def _component(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "component_product_id": str(value["component_product_id"]),
        "quantity_per_bundle": _numeric(value.get("quantity_per_bundle", "1")),
        "split_basis": value.get("split_basis", "relative_ssp"),
        "split_ratio": _numeric(value.get("split_ratio")),
        "sequence": int(value["sequence"]),
        "valid_from": str(value["valid_from"]),
        "valid_to": None if value.get("valid_to") is None else str(value["valid_to"]),
    }


def reconcile_amounts(
    session: Session, plan: Plan, applied: Applied, *, context: ApplyContext
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Verify the complete replacement and each source row's declared component target."""
    del context
    code = str(plan.rows[0].normalized["product_code"])
    bundle_id = session.execute(select(product.c.id).where(product.c.code == code)).scalar_one()
    stored = {
        row["id"]: row
        for row in session.execute(
            select(product_bundle_component).where(
                product_bundle_component.c.bundle_product_id == bundle_id
            )
        ).mappings()
    }
    expected: dict[str, Any] = {
        "complete": True,
        "components": [
            _component(
                {
                    key.removeprefix("lines."): value
                    for key, value in row.normalized.items()
                    if key.startswith("lines.") and value is not None
                }
            )
            for row in plan.rows
        ],
    }
    # Component windows end at the next source set unless an earlier end is explicit.
    components = expected["components"]
    starts = sorted({item["valid_from"] for item in components})
    for item in components:
        ends = [start for start in starts if start > item["valid_from"]]
        if item["valid_to"] is not None:
            ends.append(item["valid_to"])
        item["valid_to"] = min(ends) if ends else None
    actual_rows: list[Any] = []
    row_ids: list[UUID] = []
    for row in plan.rows:
        targets = applied.row_targets.get(row.id, [])
        if len(targets) != 1 or targets[0][0] != "product_bundle_component":
            actual_rows.append({"target_count": len(targets)})
            continue
        component_id = targets[0][1]
        row_ids.append(component_id)
        actual_rows.append(
            _component(dict(stored[component_id])) if component_id in stored else None
        )
    expected_targets = {("product_bundle_component", key) for key in stored}
    actual = {
        "complete": (
            len(row_ids) == len(set(row_ids)) == len(stored)
            and set(row_ids) == set(stored)
            and len(applied.targets) == len(expected_targets)
            and set(applied.targets) == expected_targets
        ),
        "components": actual_rows,
    }
    return expected, actual


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.PRODUCT,
    target_type="product_bundle_component",
    key_column="product_code",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
    group_key=KEY,
    reconcile_amounts=reconcile_amounts,
)
