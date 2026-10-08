"""CSV v2 template ``invoices``: invoices and credit memos (04 T-IMP-01, NC-19, T-SRC-04, T-SRC-05
``tax_lines`` rev 1.3, §16.3 ``BILLING_RECORDED`` and ``CREDIT_MEMO_RECORDED``; PRD WLD-F-22,
J-04.2; 03 REQ-BIL-001; BUILD_SPEC DIN-9).

[J] L5-1-Q-21: a document is one ``invoice_number`` of one ``document_kind`` for one ``contract``;
each row is a document line with the header members repeated (NC-19), and a line with several tax
lines repeats its row once per tax line (``lines.tax_lines.*``). A plan:

1. at commit, stores one ``source_invoice`` (the first row's source record; ``external_version`` =
   the upload id) and one ``source_invoice_line`` per line, whose ``tax_lines`` keep
   ``{tax_type, jurisdiction, amount, principal_or_agent}`` as evidence; ``total_amount`` and each
   line ``amount`` are signed — a credit memo is the negative of the amount the file states (04
   T-SRC-04, T-SRC-05) — while the event's ``amount`` stays the positive Money of §16.3;
2. appends per line of an ``INVOICE`` a ``BILLING_RECORDED`` with ``issue_date``, ``due_date``,
   ``is_cancellable``, ``tax_amount`` (the sum of the line's tax lines) and ``tax_lines`` items
   ``{tax_type, amount, principal_or_agent}``, ``source_invoice_id`` naming the stored document; and
   per line of a ``CREDIT_MEMO`` a ``CREDIT_MEMO_RECORDED`` whose ``credited_invoice_number`` and
   ``obligation_key`` link it to the invoice and obligation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import and_, insert, select

from erev_api.audit import writer as audit_writer
from erev_api.db import new_id
from erev_api.db.tables import (
    contract,
    contract_event,
    legal_entity,
    source_invoice,
    source_invoice_line,
)
from erev_api.domain.imports.csv_v2 import recorded
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
    line_cells,
    row_model,
    unflatten,
)
from erev_api.domain.imports.legacy_v1.headers import RowFinding
from erev_api.enums import ContractEventType, SourceObjectType, SourceSystem
from erev_api.money import MoneyIn
from erev_api.problems import Problem
from erev_api.schemas.events import EventAppendItemIn

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from erev_api.events.stream import EventIn
    from erev_api.uow import UnitOfWork

__all__ = ["COLUMNS", "CROSS_RULE", "ROW_MODEL", "TEMPLATE", "InvoiceIn"]

CODE: Final = "invoices"
INVOICE: Final = "INVOICE"
CREDIT_MEMO: Final = "CREDIT_MEMO"


class InvoiceTaxLineIn(BaseModel):
    """One tax line of a document line (T-SRC-05 ``tax_lines``)."""

    model_config = ConfigDict(extra="forbid")

    tax_type: str
    jurisdiction: str | None = None
    amount: MoneyIn
    principal_or_agent: Literal["PRINCIPAL", "AGENT"]


class InvoiceLineIn(BaseModel):
    """One document line (T-SRC-05)."""

    model_config = ConfigDict(extra="forbid")

    line_external_id: str
    obligation_key: str | None = None
    product_code: str | None = None
    quantity: str | None = None
    amount: MoneyIn
    service_period_start: date | None = None
    service_period_end: date | None = None
    tax_lines: InvoiceTaxLineIn | None = None  # one per row (L5-1-Q-21)


class InvoiceIn(BaseModel):
    """An invoice or credit memo of one contract as rows (L5-1-Q-21)."""

    model_config = ConfigDict(extra="forbid")

    contract: str
    document_kind: Literal["INVOICE", "CREDIT_MEMO"]
    invoice_number: str
    issue_date: date
    due_date: date | None = None
    is_cancellable: bool | None = None
    credited_invoice_number: str | None = None
    reason: str | None = None
    lines: list[InvoiceLineIn]


COLUMNS: Final = tuple(flatten(InvoiceIn))
ROW_MODEL: Final = row_model("CsvInvoicesRow", COLUMNS)
_LINES: Final = frozenset({"lines"})
# 04 table 15.4-B (rev 1.45): the S10-R-07 identity refusals a document line can earn against the
# contract's stored stream at validation (D-97 (30); PR-1.3), and the refund bound a credit memo
# row can break over the kept billing (05 §3.9 IMP-25; table 15.4-A #25; VOID-3a). Other bounds
# stay with the dry run.
CHANNEL_CODES: Final = frozenset(
    {"INVOICE_IDENTITY_REPEATED", "INVOICE_STATUS_UPDATE_MISMATCH", "REFUND_EXCEEDS_BILLED"}
)
# The BILLING_RECORDED payload member a refusal names -> the template column that carries it.
PAYLOAD_COLUMNS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "invoice_number": "invoice_number",
        "line_external_id": "lines.line_external_id",
        "amount": "lines.amount.amount",
        "obligation_key": "lines.obligation_key",
    }
)


# The rows of one contract, document kind and invoice number make one document, and within it the
# rows of one line id make one line, each row adding a tax line. The document's header members
# are read from its first row and a line's members from the line's first row — the billed amount
# among them — so a later row states them alike or not at all (05 IPL-05 rev 1.210).
KEY: Final = ("contract", "document_kind", "invoice_number")
LINE_KEY: Final = (*KEY, "lines.line_external_id")
REPEATS: Final = (
    Repeated("document", KEY, header_cells(COLUMNS, KEY), ("invoice_number",)),
    Repeated(
        "document line",
        LINE_KEY,
        line_cells(COLUMNS, LINE_KEY, own=("lines.tax_lines.",)),
        ("invoice_number", "lines.line_external_id"),
    ),
)


def plans(rows: Sequence[CsvRow]) -> list[Plan]:
    """One plan per document in worksheet order; the rows of one line merge their tax lines."""
    found: list[Plan] = []
    for (name, _, _), members in grouped(rows, KEY).items():
        lines: dict[str, dict[str, Any]] = {}
        for row in members:
            line = dict(unflatten(row.normalized).get("lines", {}))
            tax = line.pop("tax_lines", None)
            merged = lines.setdefault(str(line.get("line_external_id")), {**line, "tax_lines": []})
            if tax:
                merged["tax_lines"].append(tax)
        body = {**unflatten(members[0].normalized, skip=_LINES), "lines": list(lines.values())}
        found.append(Plan(key=name, rows=tuple(members), body=body))
    return found


def _document_bodies(
    rows: Sequence[tuple[int, Mapping[str, Any]]],
) -> list[tuple[str, dict[str, Any], list[int]]]:
    """``plans()`` over validated (row number, values) pairs: per document in file order, its
    contract, body and the first row number of each line (L5-1-Q-21)."""
    documents: dict[tuple[str, ...], list[tuple[int, Mapping[str, Any]]]] = {}
    for number, values in rows:
        documents.setdefault(tuple(str(values.get(name) or "") for name in KEY), []).append(
            (number, values)
        )
    found: list[tuple[str, dict[str, Any], list[int]]] = []
    for (name, _, _), members in documents.items():
        lines: dict[str, dict[str, Any]] = {}
        numbers: dict[str, int] = {}
        for number, values in members:
            line = dict(unflatten(values).get("lines", {}))
            tax = line.pop("tax_lines", None)
            line_id = str(line.get("line_external_id"))
            merged = lines.setdefault(line_id, {**line, "tax_lines": []})
            numbers.setdefault(line_id, number)
            if tax:
                merged["tax_lines"].append(tax)
        body = {**unflatten(members[0][1], skip=_LINES), "lines": list(lines.values())}
        found.append((name, body, [numbers[line_id] for line_id in lines]))
    return found


def _document_events(
    session: Session,
    contract_row: Mapping[str, Any],
    documents: Sequence[tuple[dict[str, Any], list[int]]],
) -> tuple[list[int], list[EventIn]]:
    """The recorded events of a contract's documents in file order with the row of each; a document
    or line the route would refuse for another reason is left to the row model and the dry run."""
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
    for body, rows_of_lines in documents:
        try:
            items = _items(body, None)
        except (KeyError, TypeError, ValueError, ValidationError):
            continue
        for item, number in zip(items, rows_of_lines, strict=True):
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
    """``CONTRACT_NOT_FOUND``, then the channel refusals of each existing contract's document
    lines against its stored stream, in file order: the S10-R-07 identity refusals (04 table 15.4-B
    rev 1.45; D-97 (30)) — a repeated identity flagged cancellable is ``INVOICE_IDENTITY_REPEATED``,
    a status update that changes the amount or re-attributes the line
    ``INVOICE_STATUS_UPDATE_MISMATCH`` — and the refund bound over the kept billing
    (``REFUND_EXCEEDS_BILLED``, 05 §3.9; VOID-3a); each on the first row of the line, in the column
    of the member named (CPY-06)."""
    from erev_api.domain.contracts import events as contract_events

    found = recorded.contract_findings(session, rows, known_at=known_at, parameters=parameters)
    usable = [(number, values) for number, values in rows if number not in found]
    by_contract: dict[str, list[tuple[dict[str, Any], list[int]]]] = {}
    for name, body, numbers in _document_bodies(usable):
        by_contract.setdefault(name, []).append((body, numbers))
    stored = {
        str(row["external_id"]): dict(row)
        for row in session.execute(
            select(contract).where(contract.c.external_id.in_(sorted(by_contract)))
        ).mappings()
    }
    for name in sorted(by_contract):
        if name not in stored:
            continue
        numbers, events = _document_events(session, stored[name], by_contract[name])
        if not events:
            continue
        try:
            contract_events.check_bounds(session, stored[name], events, known_at=known_at)
        except Problem as problem:
            for error in problem.errors:
                if error.rule_id not in CHANNEL_CODES or error.field is None:
                    continue
                parts = error.field.split(".")
                number = numbers[int(parts[1])]
                column = PAYLOAD_COLUMNS.get(parts[-1], parts[-1])
                message = recorded.located(number, column, error.message, error.rule_id)
                found.setdefault(number, []).append(
                    RowFinding(error.rule_id, "ERROR", message, column)
                )
    return found


CROSS_RULE: Final = cross_findings


def _money(value: Mapping[str, Any]) -> tuple[Decimal, str]:
    return Decimal(str(value["amount"])), str(value["currency"])


def _tax(line: Mapping[str, Any]) -> tuple[Decimal | None, str | None]:
    taxes = line.get("tax_lines") or []
    if not taxes:
        return None, None
    total = sum((_money(item["amount"])[0] for item in taxes), Decimal(0))
    return total, _money(taxes[0]["amount"])[1]


def _store(
    uow: UnitOfWork, plan: Plan, context: ApplyContext, body: Mapping[str, Any]
) -> UUID | None:
    """T-SRC-04 and T-SRC-05 of the document (commit only)."""
    record_id = context.record_ids.get(plan.rows[0].id)
    if record_id is None:
        return None
    session = uow.session
    principal = uow.principal
    created = {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }
    header = session.execute(
        select(contract.c.customer_id, legal_entity.c.code)
        .join(legal_entity, legal_entity.c.id == contract.c.contracting_entity_id)
        .where(contract.c.external_id == plan.key)
    ).one()
    lines = body["lines"]
    currency = _money(lines[0]["amount"])[1]
    # 04 T-SRC-04 ``total_amount`` "Signed: credit memos negative"; T-SRC-05 ``amount`` "Signed".
    sign = -1 if str(body["document_kind"]) == CREDIT_MEMO else 1
    total = sign * sum((_money(line["amount"])[0] for line in lines), Decimal(0))
    tax_total = sum((_tax(line)[0] or Decimal(0) for line in lines), Decimal(0))
    invoice_id = new_id()
    session.execute(
        insert(source_invoice).values(
            tenant_id=principal.tenant_id,
            id=invoice_id,
            source_record_id=record_id,
            source_system=SourceSystem.CSV_V2.value,
            external_invoice_id=str(body["invoice_number"]),
            external_version=str(context.import_upload_id),
            invoice_number=str(body["invoice_number"]),
            document_kind=str(body["document_kind"]),
            issue_date=date.fromisoformat(str(body["issue_date"])),
            due_date=None if body.get("due_date") is None else date.fromisoformat(body["due_date"]),
            is_cancellable=str(body.get("is_cancellable")).lower() == "true",
            customer_id=header.customer_id,
            legal_entity_code=str(header.code),
            currency=currency,
            total_amount=total,
            tax_amount=tax_total,
            credited_invoice_external_id=body.get("credited_invoice_number"),
            custom_attributes={},
            **created,
        )
    )
    rows = [
        {
            "tenant_id": principal.tenant_id,
            "id": new_id(),
            "source_invoice_id": invoice_id,
            "line_external_id": str(line["line_external_id"]),
            "contract_ref": plan.key,
            "obligation_ref": line.get("obligation_key"),
            "product_code": line.get("product_code"),
            "quantity": None if line.get("quantity") is None else Decimal(str(line["quantity"])),
            "amount": sign * _money(line["amount"])[0],
            "tax_lines": [
                {
                    "tax_type": item["tax_type"],
                    "jurisdiction": item.get("jurisdiction"),
                    "amount": item["amount"],
                    "principal_or_agent": item["principal_or_agent"],
                }
                for item in line.get("tax_lines") or []
            ],
            "service_period_start": line.get("service_period_start"),
            "service_period_end": line.get("service_period_end"),
            "custom_attributes": {},
            **created,
        }
        for line in lines
    ]
    session.execute(insert(source_invoice_line), rows)
    audit_writer.record_facts(
        uow, action="source_invoice.create", object_type="source_invoice", ids=[invoice_id]
    )
    audit_writer.record_facts(
        uow,
        action="source_invoice_line.create",
        object_type="source_invoice_line",
        ids=[row["id"] for row in rows],
        detail={"source_invoice_id": str(invoice_id)},
    )
    return invoice_id


def _items(body: Mapping[str, Any], invoice_id: UUID | None) -> list[EventAppendItemIn]:
    issue = date.fromisoformat(str(body["issue_date"]))
    found: list[EventAppendItemIn] = []
    for line in body["lines"]:
        key = line.get("obligation_key")
        if body["document_kind"] == CREDIT_MEMO:
            payload: dict[str, Any] = {
                "credit_memo_number": body["invoice_number"],
                "credited_invoice_number": body.get("credited_invoice_number"),
                "obligation_key": key,
                "amount": line["amount"],
                "issue_date": body["issue_date"],
                "reason": body.get("reason"),
            }
            event_type = ContractEventType.CREDIT_MEMO_RECORDED
        else:
            tax_amount, tax_currency = _tax(line)
            payload = {
                "invoice_number": body["invoice_number"],
                "line_external_id": line["line_external_id"],
                "obligation_key": key,
                "amount": line["amount"],
                "issue_date": body["issue_date"],
                "due_date": body.get("due_date"),
                "is_cancellable": body.get("is_cancellable"),
                "service_period_start": line.get("service_period_start"),
                "service_period_end": line.get("service_period_end"),
                "source_invoice_id": None if invoice_id is None else str(invoice_id),
            }
            if tax_amount is not None:
                payload["tax_amount"] = {
                    "amount": format(tax_amount, "f"),
                    "currency": tax_currency,
                }
                payload["tax_lines"] = [
                    {
                        "tax_type": item["tax_type"],
                        "amount": item["amount"],
                        "principal_or_agent": item["principal_or_agent"],
                    }
                    for item in line["tax_lines"]
                ]
            event_type = ContractEventType.BILLING_RECORDED
        found.append(
            EventAppendItemIn(
                event_type=event_type,
                effective_date=issue,
                obligation_key=None if key is None else str(key),
                payload={name: value for name, value in payload.items() if value is not None},
            )
        )
    return found


def apply(uow: UnitOfWork, plan: Plan, *, context: ApplyContext) -> Applied:
    """Store the document at commit and append its events (module docstring)."""
    for row in plan.rows:
        InvoiceIn.model_validate(
            unflatten(row.normalized, skip=_LINES)
            | {"lines": [unflatten(row.normalized).get("lines", {})]}
        )
    body = dict(plan.body)
    invoice_id = None if context.dry_run else _store(uow, plan, context, body)
    return recorded.append(uow, plan, context=context, items=_items(body, invoice_id))


def _exact(value: Any) -> str:
    with localcontext() as ctx:
        ctx.prec = 80
        return format(Decimal(str(value)).normalize(), "f")


def _stored_quantity(value: Any) -> str | None:
    if value is None:
        return None
    with localcontext() as ctx:
        ctx.prec = 80
        return _exact(Decimal(str(value)).quantize(Decimal("1e-18"), rounding=ROUND_HALF_UP))


def _day_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _tax_attributes(value: Mapping[str, Any], *, source: bool) -> dict[str, Any]:
    return {
        "tax_type": value.get("tax_type"),
        "principal_or_agent": value.get("principal_or_agent"),
        **({"jurisdiction": value.get("jurisdiction")} if source else {}),
    }


def _amount_pair(value: Mapping[str, Any]) -> list[str]:
    return [_exact(value["amount"]), str(value["currency"]).strip()]


def reconcile_amounts(
    session: Session, plan: Plan, applied: Applied, *, context: ApplyContext
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Read written monetary facts independently of the emitter's plan body (CTL-002).

    File rows repeat the invoice amount once per tax component. Count each line once,
    each tax row once, and compare currencies as well as amounts. Credit source lines
    are signed; credit events retain the positive source amount. Event order is stream
    order, including credit events which do not carry a line_external_id.
    """
    first = plan.rows[0].normalized
    credit = first["document_kind"] == CREDIT_MEMO
    sign = Decimal(-1 if credit else 1)
    source_lines: dict[str, dict[str, Any]] = {}
    for row in plan.rows:
        cells = row.normalized
        key = str(cells["lines.line_external_id"])
        line = source_lines.setdefault(
            key,
            {
                "amount": [
                    _exact(sign * Decimal(str(cells["lines.amount.amount"]))),
                    str(cells["lines.amount.currency"]),
                ],
                "contract": str(first["contract"]),
                "obligation": cells.get("lines.obligation_key"),
                "product": cells.get("lines.product_code"),
                "quantity": _stored_quantity(cells.get("lines.quantity")),
                "service_period_start": cells.get("lines.service_period_start"),
                "service_period_end": cells.get("lines.service_period_end"),
                "taxes": [],
                "tax_attributes": [],
            },
        )
        if cells.get("lines.tax_lines.amount.amount") is not None:
            line["taxes"].append(
                [
                    _exact(cells["lines.tax_lines.amount.amount"]),
                    str(cells["lines.tax_lines.amount.currency"]),
                ]
            )
            line["tax_attributes"].append(
                _tax_attributes(
                    {
                        "tax_type": cells.get("lines.tax_lines.tax_type"),
                        "principal_or_agent": cells.get("lines.tax_lines.principal_or_agent"),
                        "jurisdiction": cells.get("lines.tax_lines.jurisdiction"),
                    },
                    source=True,
                )
            )
    expected_events = [
        {
            "contract": str(first["contract"]),
            "event_type": "CREDIT_MEMO_RECORDED" if credit else "BILLING_RECORDED",
            "effective_date": str(first["issue_date"]),
            "source_record_id": str(context.record_ids[plan.rows[0].id]),
            "obligation": line["obligation"],
            "number": str(first["invoice_number"]),
            "line_external_id": None if credit else key,
            "source_invoice_linked": None if credit else True,
            "credited_invoice_number": first.get("credited_invoice_number") if credit else None,
            "issue_date": str(first["issue_date"]),
            "due_date": None if credit else first.get("due_date"),
            "is_cancellable": None
            if credit or first.get("is_cancellable") is None
            else str(first["is_cancellable"]).lower() == "true",
            "service_period_start": None if credit else line["service_period_start"],
            "service_period_end": None if credit else line["service_period_end"],
            "reason": first.get("reason") if credit else None,
            "tax_attributes": []
            if credit
            else [_tax_attributes(tax, source=False) for tax in line["tax_attributes"]],
            "amount": [_exact(sign * Decimal(line["amount"][0])), line["amount"][1]],
            "taxes": [] if credit else line["taxes"],
            "tax_amount": None
            if credit or not line["taxes"]
            else [
                _exact(sum((Decimal(tax[0]) for tax in line["taxes"]), Decimal(0))),
                line["taxes"][0][1],
            ],
        }
        for key, line in source_lines.items()
    ]
    expected = {
        "invoice_number": str(first["invoice_number"]),
        "document_kind": str(first["document_kind"]),
        "issue_date": str(first["issue_date"]),
        "due_date": first.get("due_date"),
        "is_cancellable": str(first.get("is_cancellable")).lower() == "true",
        "credited_invoice_number": first.get("credited_invoice_number"),
        "currency": str(first["lines.amount.currency"]),
        "total_amount": _exact(
            sum((Decimal(line["amount"][0]) for line in source_lines.values()), Decimal(0))
        ),
        "tax_amount": _exact(
            sum(
                (Decimal(tax[0]) for line in source_lines.values() for tax in line["taxes"]),
                Decimal(0),
            )
        ),
        "lines": source_lines,
        "events": expected_events,
    }
    documents = list(
        session.execute(
            select(source_invoice).where(
                source_invoice.c.source_record_id == context.record_ids[plan.rows[0].id],
                source_invoice.c.external_version == str(context.import_upload_id),
            )
        ).mappings()
    )
    if len(documents) != 1:
        return expected, {"document_count": len(documents)}
    document = documents[0]
    stored_lines = list(
        session.execute(
            select(source_invoice_line).where(
                source_invoice_line.c.source_invoice_id == document["id"]
            )
        ).mappings()
    )
    events = list(
        session.execute(
            select(
                contract_event.c.payload,
                contract_event.c.event_type,
                contract_event.c.effective_date,
                contract_event.c.source_record_id,
                contract.c.external_id,
            )
            .join(
                contract,
                and_(
                    contract.c.tenant_id == contract_event.c.tenant_id,
                    contract.c.id == contract_event.c.contract_id,
                ),
            )
            .where(
                contract_event.c.id.in_(
                    [key for kind, key in applied.targets if kind == "contract_event"]
                ),
                contract_event.c.import_upload_id == context.import_upload_id,
            )
            .order_by(contract_event.c.stream_version)
        ).mappings()
    )
    actual = {
        "invoice_number": str(document["invoice_number"]),
        "document_kind": str(document["document_kind"]),
        "issue_date": str(document["issue_date"]),
        "due_date": _day_text(document["due_date"]),
        "is_cancellable": document["is_cancellable"],
        "credited_invoice_number": document["credited_invoice_external_id"],
        "currency": str(document["currency"]).strip(),
        "total_amount": _exact(document["total_amount"]),
        "tax_amount": _exact(document["tax_amount"]),
        "lines": {
            str(line["line_external_id"]): {
                "contract": line["contract_ref"],
                "obligation": line["obligation_ref"],
                "product": line["product_code"],
                "quantity": _stored_quantity(line["quantity"]),
                "service_period_start": _day_text(line["service_period_start"]),
                "service_period_end": _day_text(line["service_period_end"]),
                "tax_attributes": [
                    _tax_attributes(tax, source=True) for tax in line["tax_lines"] or []
                ],
                "amount": [_exact(line["amount"]), str(document["currency"]).strip()],
                "taxes": [_amount_pair(tax["amount"]) for tax in line["tax_lines"] or []],
            }
            for line in stored_lines
        },
        "events": [
            {
                "contract": row["external_id"],
                "event_type": str(row["event_type"]),
                "effective_date": str(row["effective_date"]),
                "source_record_id": str(row["source_record_id"]),
                "obligation": event.get("obligation_key"),
                "number": event.get("invoice_number") or event.get("credit_memo_number"),
                "line_external_id": event.get("line_external_id"),
                "source_invoice_linked": (
                    event.get("source_invoice_id") == str(document["id"])
                    if str(row["event_type"]) == "BILLING_RECORDED"
                    else None
                ),
                "credited_invoice_number": event.get("credited_invoice_number"),
                "issue_date": event.get("issue_date"),
                "due_date": event.get("due_date"),
                "is_cancellable": event.get("is_cancellable"),
                "service_period_start": event.get("service_period_start"),
                "service_period_end": event.get("service_period_end"),
                "reason": event.get("reason"),
                "tax_attributes": [
                    _tax_attributes(tax, source=False) for tax in event.get("tax_lines") or []
                ],
                "amount": _amount_pair(event["amount"]),
                "taxes": [_amount_pair(tax["amount"]) for tax in event.get("tax_lines") or []],
                "tax_amount": None
                if event.get("tax_amount") is None
                else _amount_pair(event["tax_amount"]),
            }
            for row in events
            for event in (row["payload"],)
        ],
    }
    return expected, actual


TEMPLATE: Final = CsvTemplate(
    code=CODE,
    object_type=SourceObjectType.INVOICE,
    target_type="contract_event",
    key_column="contract",
    columns=COLUMNS,
    plans=plans,
    apply=apply,
    group_key=KEY,
    repeats=REPEATS,
    reconcile_amounts=reconcile_amounts,
)
