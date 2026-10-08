"""Shared services of the CSV v2 event templates ``invoices``, ``progress_events``, ``usage``,
``cost_events`` and ``pre_standard_revenue`` (04 T-IMP-01, NC-19, §16.3; API-R-30; ENGINE_SPEC
S01-R-03; 05 §3.9; PRD CPY-06, IMP-20; BUILD_SPEC DIN-9).

[J] L5-1-Q-19: the command of an event template is ``POST /contracts/{id}/events``, whose items
carry a free-form payload, so a row is one event: column ``contract`` names the contract by its
external id (the path member ``{id}``), ``effective_date`` and ``obligation_key`` are the
API-S-EventAppend members, and the other columns are the payload members of the event type (§16.3)
flattened with ``.`` (NC-19).

``append`` validates the items as the route does (``to_events``, the Step 1 gate, the 05 §3.9
bounds), names the upload, the row's source record and the S01-R-03 import key on each event and
appends them with origin ``IMPORT``. The business key of a CSV v2 event row is ``<contract> / row
<n>``, so two rows of one contract keep distinct keys. The dry run computes the group so the diff
reads the provisional version; the commit leaves the group dirty (L5-1-Q-12).

Validation raises ``CONTRACT_NOT_FOUND`` (IMP-20) for a row whose contract does not exist, with the
CPY-06 location: "Row <n>, column Contract: ... (CONTRACT_NOT_FOUND)". [J] L5-1-Q-20: a column is
named in a message by its label, the name with its first letter capitalised and ``_`` and ``.`` as
spaces.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract, contract_event, legal_entity
from erev_api.domain.imports import findings
from erev_api.domain.imports.csv_v2.framework import Applied, ApplyContext, CsvRow, Plan, unflatten
from erev_api.domain.imports.legacy_v1.headers import RowFinding
from erev_api.domain.integrations.normalise import import_event_key
from erev_api.problems import Problem

if TYPE_CHECKING:
    from erev_api.schemas.events import EventAppendItemIn
    from erev_api.uow import UnitOfWork

__all__ = [
    "CONTRACT_COLUMN",
    "append",
    "column_label",
    "contract_findings",
    "row_plans",
    "reconcile_amounts",
]

CONTRACT_COLUMN: Final = "contract"
NOT_FOUND: Final = "Contract {contract} does not exist in this workspace."  # PRD IMP-20


def column_label(name: str) -> str:
    """The label of a column in a message: ``contract`` → "Contract" (L5-1-Q-20)."""
    return findings.column_label(name)


def located(row_number: int, column: str, message: str, code: str) -> str:
    """PRD CPY-06: a finding of a CSV row starts with its location and ends with its code
    (``findings.csv_located``; D-87, L6-1-Q-2)."""
    return findings.csv_located(message, code, row_number=row_number, column=column)


def row_plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per row, keyed by the contract external id."""
    return [
        Plan(
            key=str(row.normalized.get(CONTRACT_COLUMN) or ""),
            rows=(row,),
            body=unflatten(row.normalized),
        )
        for row in rows
    ]


def contract_findings(
    session: Session,
    rows: Sequence[tuple[int, Mapping[str, Any]]],
    *,
    known_at: datetime,
    parameters: Mapping[str, Any],
) -> dict[int, list[RowFinding]]:
    """``CONTRACT_NOT_FOUND`` for each row naming a contract that does not exist (IMP-20)."""
    del known_at, parameters
    names = sorted({str(values.get(CONTRACT_COLUMN) or "") for _, values in rows})
    existing = {
        str(value)
        for value in session.execute(
            select(contract.c.external_id).where(contract.c.external_id.in_(names))
        ).scalars()
    }
    found: dict[int, list[RowFinding]] = {}
    for number, values in rows:
        name = str(values.get(CONTRACT_COLUMN) or "")
        if name in existing:
            continue
        message = located(
            number, CONTRACT_COLUMN, NOT_FOUND.format(contract=name), "CONTRACT_NOT_FOUND"
        )
        found.setdefault(number, []).append(
            RowFinding("CONTRACT_NOT_FOUND", "ERROR", message, CONTRACT_COLUMN)
        )
    return found


def _time_zone(session: Session, entity_id: Any) -> str:
    return str(
        session.execute(
            select(legal_entity.c.time_zone).where(legal_entity.c.id == entity_id)
        ).scalar_one()
    )


def append(
    uow: UnitOfWork,
    plan: Plan,
    *,
    context: ApplyContext,
    items: Sequence[EventAppendItemIn],
) -> Applied:
    """Append the events of one plan as the import principal (module docstring)."""
    from erev_api.domain.contracts import compute_job, repo
    from erev_api.domain.contracts import events as contract_events
    from erev_api.events.stream import append_events

    session = uow.session
    found = repo.contract_by_external_id(session, plan.key)
    if found is None:
        raise Problem("validation-failed", NOT_FOUND.format(contract=plan.key))
    contract_id = UUID(str(found["id"]))
    _, current = repo.lock_group_then_contract(session, contract_id)  # DG-KRN-DB-08 rev 1.36
    recorded = contract_events.to_events(
        items,
        time_zone=_time_zone(session, current["contracting_entity_id"]),
        is_manual=False,
    )
    recorded = contract_events.step1_events(uow, current, recorded)
    contract_events.check_bounds(session, current, recorded, known_at=uow.now)
    first = plan.rows[0]
    business_key = f"{plan.key} / row {first.row_number}"
    stamped = [
        dataclasses.replace(
            event,
            idempotency_key=import_event_key(
                file_sha256=context.file_sha256,
                template_code=context.template_code,
                template_version=context.template_version,
                business_key=business_key,
                ordinal=ordinal,
            ),
            import_upload_id=context.import_upload_id,
            source_record_id=context.record_ids.get(first.id),
        )
        for ordinal, event in enumerate(recorded, start=1)
    ]
    head = int(current["head_stream_version"])
    rows = append_events(
        uow,
        contract_id=contract_id,
        expected_stream_version=head,
        events=stamped,
        origin="IMPORT",
    )
    group_id = UUID(str(current["combination_group_id"]))
    if context.dry_run:
        compute_job.compute_group(uow, group_id)
    applied = Applied()
    targets = [("contract_event", UUID(str(row["id"]))) for row in rows]
    applied.targets += targets
    for row in plan.rows:
        applied.row_targets[row.id] = list(targets)
    applied.contracts.append((plan.key, contract_id, group_id, head))
    return applied


def reconcile_amounts(
    session: Session,
    plan: Plan,
    applied: Applied,
    *,
    context: ApplyContext,
    event_type: str | None,
    amount_field: str,
    numeric_fields: tuple[str, ...] = (),
    identity_fields: tuple[str, ...] = ("obligation_key",),
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Independent monetary read-back for one-event-per-row templates (CTL-002).

    Bind amounts to contract, event kind, date, source record and obligation. Templates
    may also name numeric inputs and identity fields; expectations come from original
    validated rows, not emitter plan bodies. A null amount/input stays distinct from zero.
    A mixed-event template takes its expected event kind from each source row.
    """

    def number(value: Any) -> str | None:
        if value is None:
            return None
        with localcontext() as ctx:
            ctx.prec = 80
            decimal = Decimal(str(value))
            return format(decimal.normalize(), "f") if decimal else "0"

    def money(value: Mapping[str, Any] | None) -> list[Any] | None:
        if value is None:
            return None
        return [number(value["amount"]), str(value["currency"])]

    def fields(value: Mapping[str, Any]) -> dict[str, Any]:
        return {
            **{key: value.get(key) for key in identity_fields},
            **{key: number(value.get(key)) for key in numeric_fields},
        }

    expected = {
        "events": [
            {
                "contract": str(row.normalized["contract"]),
                "event_type": event_type or str(row.normalized["event_type"]),
                "fields": fields(row.normalized),
                "effective_date": str(row.normalized["effective_date"]),
                "source_record_id": str(context.record_ids[row.id]),
                "amount": money(
                    None
                    if row.normalized.get(f"{amount_field}.amount") is None
                    else {
                        "amount": row.normalized[f"{amount_field}.amount"],
                        "currency": row.normalized[f"{amount_field}.currency"],
                    }
                ),
            }
            for row in plan.rows
        ]
    }
    rows = session.execute(
        select(
            contract.c.external_id,
            contract_event.c.event_type,
            contract_event.c.effective_date,
            contract_event.c.source_record_id,
            contract_event.c.payload,
        )
        .select_from(
            contract_event.join(
                contract,
                and_(
                    contract.c.tenant_id == contract_event.c.tenant_id,
                    contract.c.id == contract_event.c.contract_id,
                ),
            )
        )
        .where(
            contract_event.c.id.in_(
                [key for kind, key in applied.targets if kind == "contract_event"]
            ),
            contract_event.c.import_upload_id == context.import_upload_id,
        )
        .order_by(contract_event.c.stream_version)
    ).mappings()
    actual = {
        "events": [
            {
                "contract": str(row["external_id"]),
                "event_type": str(row["event_type"]),
                "effective_date": str(row["effective_date"]),
                "source_record_id": str(row["source_record_id"]),
                "amount": money(row["payload"].get(amount_field)),
                "fields": fields(row["payload"]),
            }
            for row in rows
        ]
    }
    return expected, actual
