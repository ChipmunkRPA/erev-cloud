"""CSV v2 template ``progress_events``: one progress event per row (04 T-IMP-01, NC-19, §16.3
``DELIVERY_RECORDED``, ``RETURN_RECORDED``, ``PROGRESS_RECORDED``, ``MILESTONE_ACHIEVED``; PRD
WLD-F-21, J-04.1; BUILD_SPEC DIN-9).

[J] L5-1-Q-19: the columns are ``contract``, ``event_type``, ``effective_date`` and the members of
the four progress payloads; a blank cell is absent from the payload.

Validation raises ``CONTRACT_NOT_FOUND`` (IMP-20) and, for the rows of existing contracts, the
stage 01 quantity bounds of 05 §3.9 folded over the stored stream in row order:
``PROGRESS_OVER_DELIVERY`` (IMP-22) and ``RETURN_EXCEEDS_DELIVERED`` (IMP-24), with the CPY-06
location. A breach makes the upload ``INVALID`` with one exception item per row (PRD J-04-ALT-1,
§2.9 WLD-B-04; BUILD_SPEC DIN-15). [J] L6-4-Q-10: before DIN-15 the bounds ran only in the dry run,
where a breach became ``IMPORT_PROCESSING_FAILED`` and the upload still reached ``DIFF_READY``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from functools import partial
from typing import TYPE_CHECKING, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select

from erev_api.db.tables import contract, legal_entity
from erev_api.domain.imports.csv_v2 import recorded
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
from erev_api.domain.imports.legacy_v1.headers import RowFinding
from erev_api.enums import ContractEventType, SourceObjectType
from erev_api.money import MoneyIn
from erev_api.problems import Problem
from erev_api.schemas.events import EventAppendItemIn

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.events.stream import EventIn
    from erev_api.uow import UnitOfWork

__all__ = ["COLUMNS", "CROSS_RULE", "ROW_MODEL", "TEMPLATE", "ProgressEventIn"]

CODE: Final = "progress_events"
HEADER_MEMBERS: Final = frozenset({"contract", "event_type", "effective_date"})


class ProgressEventIn(BaseModel):
    """One progress event of ``POST /contracts/{id}/events`` as a row (L5-1-Q-19)."""

    model_config = ConfigDict(extra="forbid")

    contract: str
    event_type: Literal[
        "DELIVERY_RECORDED", "RETURN_RECORDED", "PROGRESS_RECORDED", "MILESTONE_ACHIEVED"
    ]
    effective_date: date
    obligation_key: str
    quantity: str | None = None
    trigger: str | None = None
    source_ref: str | None = None
    refund_amount: MoneyIn | None = None
    reason: str | None = None
    cumulative_progress_ratio: str | None = None
    measure: str | None = None
    hours_to_date: str | None = None
    milestone_code: str | None = None
    cumulative_weight: str | None = None


COLUMNS: Final = tuple(flatten(ProgressEventIn))
ROW_MODEL: Final = row_model("CsvProgressEventsRow", COLUMNS)
# 05 §3.9 bounds a progress row can break (IMP-22, IMP-24).
BOUND_CODES: Final = frozenset({"PROGRESS_OVER_DELIVERY", "RETURN_EXCEEDS_DELIVERED"})


def _bounded_events(
    session: Session, contract_row: Mapping[str, Any], rows: Sequence[tuple[int, EventAppendItemIn]]
) -> tuple[list[int], list[EventIn]]:
    """The recorded events of a contract's rows in row order; a row whose payload the route would
    refuse is left to the dry run."""
    from erev_api.domain.contracts import events as contract_events

    time_zone = str(
        session.execute(
            select(legal_entity.c.time_zone).where(
                legal_entity.c.id == contract_row["contracting_entity_id"]
            )
        ).scalar_one()
    )
    numbers: list[int] = []
    found: list[EventIn] = []
    for number, item in rows:
        try:
            [event] = contract_events.to_events([item], time_zone=time_zone, is_manual=False)
        except Problem:
            continue
        numbers.append(number)
        found.append(event)
    return numbers, found


def cross_findings(
    session: Session,
    rows: Sequence[tuple[int, Mapping[str, Any]]],
    *,
    known_at: datetime,
    parameters: Mapping[str, Any],
) -> dict[int, list[RowFinding]]:
    """``CONTRACT_NOT_FOUND``, then the quantity bounds of each existing contract (module
    docstring)."""
    from erev_api.domain.contracts import events as contract_events

    found = recorded.contract_findings(session, rows, known_at=known_at, parameters=parameters)
    by_contract: dict[str, list[tuple[int, EventAppendItemIn]]] = {}
    for number, values in rows:
        if number in found:
            continue
        try:
            item = item_of(dict(unflatten(values)))
        except (KeyError, ValueError, ValidationError):
            continue
        name = str(values.get(recorded.CONTRACT_COLUMN) or "")
        by_contract.setdefault(name, []).append((number, item))
    stored = {
        str(row["external_id"]): dict(row)
        for row in session.execute(
            select(contract).where(contract.c.external_id.in_(sorted(by_contract)))
        ).mappings()
    }
    for name in sorted(by_contract):
        numbers, recorded_events = _bounded_events(session, stored[name], by_contract[name])
        if not recorded_events:
            continue
        try:
            contract_events.check_bounds(session, stored[name], recorded_events, known_at=known_at)
        except Problem as problem:
            for error in problem.errors:
                if error.rule_id not in BOUND_CODES or error.field is None:
                    continue
                parts = error.field.split(".")
                number = numbers[int(parts[1])]
                column = parts[-1]
                message = recorded.located(number, column, error.message, error.rule_id)
                found.setdefault(number, []).append(
                    RowFinding(error.rule_id, "ERROR", message, column)
                )
    return found


CROSS_RULE: Final = cross_findings


def item_of(body: dict[str, Any]) -> EventAppendItemIn:
    """The API-S-EventAppend item of one row."""
    payload = {name: value for name, value in body.items() if name not in HEADER_MEMBERS}
    return EventAppendItemIn(
        event_type=ContractEventType(str(body["event_type"])),
        effective_date=date.fromisoformat(str(body["effective_date"])),
        obligation_key=str(body["obligation_key"]),
        payload=payload,
    )


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    return recorded.row_plans(rows)


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    ProgressEventIn.model_validate(dict(plan.body))
    return recorded.append(uow, plan, context=context, items=[item_of(dict(plan.body))])


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.PROGRESS_ROW,
    target_type="contract_event",
    key_column="contract",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
    reconcile_amounts=partial(
        recorded.reconcile_amounts,
        event_type=None,
        amount_field="refund_amount",
        numeric_fields=(
            "quantity",
            "cumulative_progress_ratio",
            "hours_to_date",
            "cumulative_weight",
        ),
        identity_fields=(
            "obligation_key",
            "trigger",
            "measure",
            "milestone_code",
            "source_ref",
            "reason",
        ),
    ),
)
