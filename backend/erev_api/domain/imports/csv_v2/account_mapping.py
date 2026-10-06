"""CSV v2 template ``account_mapping``: a DRAFT account mapping version and its rules (04 T-IMP-01,
NC-19, T-REF-14, T-REF-15; API-R-20; PRD SM-04; BUILD_SPEC DIN-9).

[J] L5-1-Q-22: the members of API-S-AccountMappingCreate are repeated on each row, and each row
is one rule of ``POST /account-mappings/{id}/rules``; the rows of one ``name`` make one version,
which stays DRAFT and follows the RFD lifecycle.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

from erev_api.domain.imports.csv_v2.framework import (
    Applied,
    ApplyContext,
    CsvRow,
    CsvTemplate,
    Plan,
    Repeated,
    flatten,
    grouped,
    header_cells,
    row_model,
    unflatten,
)
from erev_api.domain.reference.commands import (
    add_account_mapping_rule,
    create_account_mapping_version,
)
from erev_api.enums import SourceObjectType
from erev_api.schemas.account_mappings import AccountMappingIn, AccountMappingRuleIn

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = ["COLUMNS", "ROW_MODEL", "TEMPLATE", "AccountMappingRowsIn"]

CODE: Final = "account_mapping"
_LINES: Final = frozenset({"lines"})


class AccountMappingRowsIn(AccountMappingIn):
    """A DRAFT version with its rules (L5-1-Q-22)."""

    lines: list[AccountMappingRuleIn]


COLUMNS: Final = tuple(flatten(AccountMappingRowsIn))
ROW_MODEL: Final = row_model("CsvAccountMappingRow", COLUMNS)
# The rows of one name make one version; its other header members are read from the first of
# them, so a later row states them alike or not at all (05 IPL-05 rev 1.210).
KEY: Final = ("name",)
REPEATS: Final = (Repeated("mapping version", KEY, header_cells(COLUMNS, KEY), KEY),)


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per version name in worksheet order."""
    return [
        Plan(
            key=name,
            rows=tuple(members),
            body={
                **unflatten(members[0].normalized, skip=_LINES),
                "lines": [unflatten(row.normalized).get("lines", {}) for row in members],
            },
        )
        for (name,), members in grouped(rows, KEY).items()
    ]


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """``create_account_mapping_version``, then one ``add_account_mapping_rule`` per row."""
    del context
    body = AccountMappingRowsIn.model_validate(dict(plan.body))
    version_id = create_account_mapping_version(
        uow, body=AccountMappingIn.model_validate(body.model_dump(exclude={"lines"}))
    )
    applied = Applied()
    for row, rule in zip(plan.rows, body.lines, strict=True):
        rule_id = add_account_mapping_rule(uow, version_id, body=rule)
        applied.targets.append(("account_mapping_rule", rule_id))
        applied.row_targets[row.id] = [("account_mapping_rule", rule_id)]
    return applied


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.GL_ACCOUNT,
    target_type="account_mapping_rule",
    key_column="name",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
    group_key=KEY,
    repeats=REPEATS,
)
