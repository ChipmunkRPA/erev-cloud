"""CSV v2 template ``contracts``: one ``POST /contracts`` request per ``external_id`` (04 T-IMP-01,
NC-19, §16.1 API-S-ContractCreate; ENGINE_SPEC S01-R-03; BUILD_SPEC DIN-3).

Rows group by ``external_id`` in file order; the first row of a contract gives the header members
and every row one booking line. A new external id books a DRAFT contract (``CONTRACT_BOOKED``
with origin IMPORT, the upload and source record ids, and the S01-R-03 import key). [J] L5-1-Q-5:
an external id of a DRAFT contract replaces the draft booking (``replace_draft``), and any other
status is refused by the command.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract, contract_event
from erev_api.domain.contracts import repo
from erev_api.domain.contracts.commands import book_contract, provisional_compute, replace_draft
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
from erev_api.domain.integrations.normalise import import_event_key
from erev_api.enums import ContractEventType, SourceObjectType, SourceSystem
from erev_api.schemas.contracts import ContractCreateIn

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = ["COLUMNS", "ROW_MODEL", "TEMPLATE"]

CODE: Final = "contracts"
COLUMNS: Final = tuple(flatten(ContractCreateIn))
ROW_MODEL: Final = row_model("CsvContractsRow", COLUMNS)
_LINES: Final = frozenset({"lines"})
# The rows of one external id make one contract; its header members are read from the first of
# them, so a later row states them alike or not at all (05 IPL-05 rev 1.210).
KEY: Final = ("external_id",)
REPEATS: Final = (Repeated("contract", KEY, header_cells(COLUMNS, KEY), KEY),)


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per ``external_id``: header members of its first row, one line per row."""
    return [
        Plan(
            key=key,
            rows=tuple(members),
            body={
                **unflatten(members[0].normalized, skip=_LINES),
                "lines": [unflatten(row.normalized).get("lines", {}) for row in members],
            },
        )
        for (key,), members in grouped(rows, KEY).items()
    ]


def _booking_event(uow: UnitOfWork, contract_id: UUID) -> UUID:
    return UUID(
        str(
            uow.session.execute(
                select(contract_event.c.id)
                .where(
                    contract_event.c.contract_id == contract_id,
                    contract_event.c.event_type == ContractEventType.CONTRACT_BOOKED.value,
                )
                .order_by(contract_event.c.stream_version.desc())
                .limit(1)
            ).scalar_one()
        )
    )


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """Book or replace the draft of one contract; the dry run also computes its provisional
    version, which ``replace_draft`` computes itself."""
    body: Any = ContractCreateIn.model_validate(dict(plan.body))
    existing = repo.contract_by_external_id(uow.session, body.external_id)
    first = plan.rows[0]
    head: int | None = None
    if existing is None:
        booked = book_contract(
            uow,
            body=body.booking(),
            origin="IMPORT",
            source_system=SourceSystem.CSV_V2,
            idempotency_key=import_event_key(
                file_sha256=context.file_sha256,
                template_code=context.template_code,
                template_version=context.template_version,
                business_key=plan.key,
                ordinal=1,
            ),
            import_upload_id=context.import_upload_id,
            source_record_id=context.record_ids.get(first.id),
        )
        contract_id = UUID(str(booked.contract["id"]))
        group_id = UUID(str(booked.combination_group["id"]))
        event_id = UUID(str(booked.event["id"]))
        if context.dry_run:
            provisional_compute(uow, group_id)
    else:
        contract_id = UUID(str(existing["id"]))
        group_id = UUID(str(existing["combination_group_id"]))
        head = int(existing["head_stream_version"])
        replace_draft(
            uow,
            contract_id=contract_id,
            expected_stream_version=head,
            body=body,
            origin="IMPORT",
            import_upload_id=context.import_upload_id,
            source_record_id=context.record_ids.get(first.id),
            idempotency_key=import_event_key(
                file_sha256=context.file_sha256,
                template_code=context.template_code,
                template_version=context.template_version,
                business_key=plan.key,
                ordinal=1,
            ),
        )
        event_id = _booking_event(uow, contract_id)
    applied = Applied()
    # 04 T-IMP-04 ``target_type`` names the event; the contract is reached through it.
    applied.targets.append(("contract_event", event_id))
    for row in plan.rows:
        applied.row_targets[row.id] = [("contract_event", event_id)]
    applied.contracts.append((str(body.external_id), contract_id, group_id, head))
    return applied


def _decimal(value: Any) -> str | None:
    if value is None:
        return None
    with localcontext() as ctx:
        ctx.prec = 80
        return format(Decimal(str(value)).normalize(), "f")


def _money(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    return (
        None
        if value is None
        else {
            "amount": _decimal(value["amount"]),
            "currency": str(value["currency"]),
        }
    )


def _line_amounts(line: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "obligation_key": line["obligation_key"],
        "product_code": line["product_code"],
        "quantity": _decimal(line["quantity"]),
        "unit_price": _decimal(line.get("unit_price")),
        "scope_flag": line.get("scope_flag") or "IN_SCOPE_606",
        "total_price": _money(line.get("total_price")),
        "out_of_scope_amount": _money(line.get("out_of_scope_amount")),
    }


def reconcile_amounts(
    session: Session, plan: Plan, applied: Applied, *, context: ApplyContext
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """CTL-002: file prices against the actual booking, including draft replacements.

    Match individual obligation/product identities, quantities and unit prices so
    offsetting line errors cannot pass by leaving the contract total unchanged.
    """
    first = plan.rows[0]
    expected = {
        "bookings": [
            {
                "external_id": first.normalized["external_id"],
                "transaction_currency": first.normalized["transaction_currency"],
                "payload_currency": first.normalized["transaction_currency"],
                "source_record_id": str(context.record_ids[first.id]),
                "lines": sorted(
                    [_line_amounts(unflatten(row.normalized)["lines"]) for row in plan.rows],
                    key=lambda line: line["obligation_key"],
                ),
            }
        ]
    }
    rows = session.execute(
        select(
            contract.c.external_id,
            contract.c.transaction_currency,
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
            contract_event.c.event_type == "CONTRACT_BOOKED",
            contract_event.c.import_upload_id == context.import_upload_id,
        )
    ).mappings()
    actual = {
        "bookings": [
            {
                "external_id": row["external_id"],
                "transaction_currency": str(row["transaction_currency"]).strip(),
                "payload_currency": row["payload"]["transaction_currency"],
                "source_record_id": str(row["source_record_id"]),
                "lines": sorted(
                    [_line_amounts(line) for line in row["payload"]["lines"]],
                    key=lambda line: line["obligation_key"],
                ),
            }
            for row in rows
        ]
    }
    return expected, actual


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.ORDER,
    target_type="contract",
    key_column="external_id",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
    group_key=KEY,
    repeats=REPEATS,
    reconcile_amounts=reconcile_amounts,
)
