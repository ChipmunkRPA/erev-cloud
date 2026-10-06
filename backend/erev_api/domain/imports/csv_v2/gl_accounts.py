"""CSV v2 template ``gl_accounts``: one ``POST /gl-accounts`` request per row (04 T-IMP-01, NC-19,
T-REF-13; API-R-20; BUILD_SPEC DIN-9).

The array members ``entity_ids`` and ``required_dimensions`` are not columns (L5-1-Q-4); an
imported account is available to every entity and requires no dimension.
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
from erev_api.domain.reference.commands import create_gl_account
from erev_api.enums import SourceObjectType, SourceSystem
from erev_api.schemas.accounts import GlAccountIn

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = ["COLUMNS", "ROW_MODEL", "TEMPLATE"]

CODE: Final = "gl_accounts"
COLUMNS: Final = tuple(flatten(GlAccountIn))
ROW_MODEL: Final = row_model("CsvGlAccountsRow", COLUMNS)


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per row, keyed by the account code."""
    return [
        Plan(
            key=str(row.normalized.get("code") or row.row_number),
            rows=(row,),
            body=unflatten(row.normalized),
        )
        for row in rows
    ]


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """``create_gl_account`` with source system ``CSV_V2``."""
    del context
    body: Any = GlAccountIn.model_validate(dict(plan.body))
    created = create_gl_account(uow, body=body, source_system=SourceSystem.CSV_V2)
    applied = Applied()
    applied.targets.append(("gl_account", created.id))
    for row in plan.rows:
        applied.row_targets[row.id] = [("gl_account", created.id)]
    return applied


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.GL_ACCOUNT,
    target_type="gl_account",
    key_column="code",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
)
