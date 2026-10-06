"""CSV v2 template ``usage``: one ``USAGE_REPORTED`` per row (04 T-IMP-01, NC-19, §16.3
``USAGE_REPORTED``; BUILD_SPEC DIN-9; L5-1-Q-19).

A row whose usage period ends after its ``effective_date`` is a finding of the row when the file
is validated (04 §16.3 "The usage period of a report" and table 15.4-B ``USAGE_PERIOD_NOT_ENDED``,
rev 1.320; PRD IMP-148; item USAGE-REPORT-PERIOD-ENDED-1): ``cross_findings`` asks the route's own
pure rule of the row's own dates. The commit passes ``events.check_bounds``, as every channel
does."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
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
from erev_api.domain.imports.legacy_v1.headers import RowFinding
from erev_api.enums import ContractEventType, SourceObjectType
from erev_api.money import MoneyIn
from erev_api.schemas.events import EventAppendItemIn

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.uow import UnitOfWork

__all__ = ["COLUMNS", "CROSS_RULE", "ROW_MODEL", "TEMPLATE", "UsageIn"]

CODE: Final = "usage"
HEADER_MEMBERS: Final = frozenset({"contract", "effective_date"})
# The columns of the rule of 04 §16.3 "The usage period of a report"; the finding stands at its end.
PERIOD_COLUMNS: Final = ("usage_period_start", "usage_period_end", "effective_date")
PERIOD_END_COLUMN: Final = "usage_period_end"


class UsageIn(BaseModel):
    """``USAGE_REPORTED`` of ``POST /contracts/{id}/events`` as a row (L5-1-Q-19)."""

    model_config = ConfigDict(extra="forbid")

    contract: str
    effective_date: date
    obligation_key: str
    usage_period_start: date
    usage_period_end: date
    metric: str
    quantity: str
    rated_amount: MoneyIn | None = None
    is_royalty_statement: bool | None = None


COLUMNS: Final = tuple(flatten(UsageIn))
ROW_MODEL: Final = row_model("CsvUsageRow", COLUMNS)


def cross_findings(
    session: Session,
    rows: Sequence[tuple[int, Mapping[str, Any]]],
    *,
    known_at: datetime,
    parameters: Mapping[str, Any],
) -> dict[int, list[RowFinding]]:
    """``CONTRACT_NOT_FOUND``, then ``USAGE_PERIOD_NOT_ENDED`` for each row whose usage period ends
    after its effective date (module docstring). The second reads the row alone, so a row of an
    unknown contract is told both."""
    from erev_api.domain.contracts import events as contract_events

    found = recorded.contract_findings(session, rows, known_at=known_at, parameters=parameters)
    for number, values in rows:
        try:
            start, end, effective = (
                date.fromisoformat(str(values[name])) for name in PERIOD_COLUMNS
            )
        except (KeyError, ValueError):
            continue  # a cell that is no date is the row model's finding
        message = contract_events.usage_period_refusal(start, end, effective)
        if message is None:
            continue
        code = contract_events.USAGE_PERIOD
        located = recorded.located(number, PERIOD_END_COLUMN, message, code)
        found.setdefault(number, []).append(RowFinding(code, "ERROR", located, PERIOD_END_COLUMN))
    return found


CROSS_RULE: Final = cross_findings


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    return recorded.row_plans(rows)


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    body: dict[str, Any] = dict(plan.body)
    UsageIn.model_validate(body)
    item = EventAppendItemIn(
        event_type=ContractEventType.USAGE_REPORTED,
        effective_date=date.fromisoformat(str(body["effective_date"])),
        obligation_key=str(body["obligation_key"]),
        payload={name: value for name, value in body.items() if name not in HEADER_MEMBERS},
    )
    return recorded.append(uow, plan, context=context, items=[item])


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.USAGE,
    target_type="contract_event",
    key_column="contract",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
)
