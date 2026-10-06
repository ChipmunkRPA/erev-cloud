"""Billing documents of an inbound adapter (05 §5.1 canonical ingestion, ADP-03, ADP-17; 04
T-SRC-04, T-SRC-05, T-CON-02 ``link_role`` ``INVOICE``, §16.3 ``BILLING_RECORDED`` and
``CREDIT_MEMO_RECORDED``; 03 REQ-INT-005, REQ-BIL-001; PRD J-23.6; BUILD_SPEC DIN-13).

An adapter's normalised invoice or credit note (``ports.NormalisedInvoiceDraft``) becomes

1. one ``source_invoice`` row and one ``source_invoice_line`` per line (``store_document``): the
   document as the source states it, signed — a credit memo negative — each line keeping its
   service period and the source's contract reference. A stored identity (source system, external
   id, version) is reused, never stored again (IM-A);
2. per line of an ``INVOICE`` a ``BILLING_RECORDED`` whose payload carries the line's service
   period (the ADP-17 hint) and ``source_invoice_id``; per line of a ``CREDIT_MEMO`` a
   ``CREDIT_MEMO_RECORDED`` naming the credited invoice by its NUMBER (§16.3), which
   ``credited_invoice`` reads from the stored invoice the credit note names by external id
   (``append_document``);
3. a ``contract_source_link`` of role ``INVOICE`` from each contract to the source record
   (``link_document``).

The events are validated as the route validates them (``to_events``, the Step 1 gate, the 05 §3.9
bounds) and appended with origin ``ADAPTER``, the ADP-03 key of the document's identity and the
line's ordinal in the document, ``source_record_id`` and ``sync_run_id``; a replay of the same
version appends nothing (``ux_contract_event__idempotency``). A later version of an invoice repeats
the identity of its lines with the same amount: a status update that adds no billing (§16.3;
ENGINE_SPEC_B S10-R-07). The group is left dirty for the next computation, as an import commit
leaves it.

A line names its contract by the source's own reference (a Stripe subscription id); the sync
resolves the reference through T-INT-04 and passes the contract here, so this module reads no
connection. A validation refusal is the ``Problem`` the route would answer; the caller records it.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import insert, select

from erev_api.audit import writer as audit_writer
from erev_api.db import new_id
from erev_api.db.tables import (
    contract_source_link,
    legal_entity,
    source_invoice,
    source_invoice_line,
)
from erev_api.domain.integrations import ports
from erev_api.domain.integrations.normalise import SourceIdentity, adapter_event_key
from erev_api.enums import ContractEventType, SourceObjectType
from erev_api.schemas.events import EventAppendItemIn

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.uow import UnitOfWork

__all__ = [
    "CREDIT_MEMO",
    "INVOICE",
    "LINK_ROLE",
    "append_document",
    "credited_invoice",
    "document_lines",
    "event_items",
    "link_document",
    "object_type_of",
    "store_document",
    "stored_document",
]

INVOICE: Final = "INVOICE"
CREDIT_MEMO: Final = "CREDIT_MEMO"
LINK_ROLE: Final = "INVOICE"  # T-CON-02 ``link_role`` of a billing document
DOCUMENT_ACTION: Final = "source_invoice.create"
DOCUMENT_LINE_ACTION: Final = "source_invoice_line.create"
LINK_ACTION: Final = "contract_source_link.create"


def object_type_of(draft: ports.NormalisedInvoiceDraft) -> SourceObjectType:
    """The T-SRC-01 object type of the document: ``INVOICE`` or ``CREDIT_MEMO``."""
    return (
        SourceObjectType.CREDIT_MEMO
        if draft.document_kind == CREDIT_MEMO
        else SourceObjectType.INVOICE
    )


def _created(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }


def _signed(draft: ports.NormalisedInvoiceDraft, amount: Decimal) -> Decimal:
    """T-SRC-04 ``total_amount`` and T-SRC-05 ``amount`` are signed: a credit memo is negative."""
    return -amount if draft.document_kind == CREDIT_MEMO else amount


def _version_rank(external_version: str) -> tuple[int, int | str]:
    """Integer versions numerically, other texts after them (``sync.version_rank``)."""
    text = external_version.strip()
    try:
        return (0, int(text))
    except ValueError:
        return (1, text)


def stored_document(
    session: Session, draft: ports.NormalisedInvoiceDraft
) -> Mapping[str, Any] | None:
    """The T-SRC-04 row of the draft's identity (``ux_source_invoice``), or None."""
    row = (
        session.execute(
            select(source_invoice).where(
                source_invoice.c.source_system == draft.source_system.value,
                source_invoice.c.external_invoice_id == draft.external_invoice_id,
                source_invoice.c.external_version == draft.external_version,
            )
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)


def document_lines(session: Session, source_invoice_id: UUID) -> list[dict[str, Any]]:
    """The T-SRC-05 rows of a stored document, in line external id order."""
    rows = session.execute(
        select(source_invoice_line)
        .where(source_invoice_line.c.source_invoice_id == source_invoice_id)
        .order_by(source_invoice_line.c.line_external_id)
    ).mappings()
    return [dict(row) for row in rows]


def credited_invoice(
    session: Session, draft: ports.NormalisedInvoiceDraft
) -> Mapping[str, Any] | None:
    """The stored INVOICE a credit memo names by ``credited_invoice_external_id``: its newest
    stored version, or None while no version of it is stored."""
    if draft.credited_invoice_external_id is None:
        return None
    rows = (
        session.execute(
            select(source_invoice).where(
                source_invoice.c.source_system == draft.source_system.value,
                source_invoice.c.external_invoice_id == draft.credited_invoice_external_id,
                source_invoice.c.document_kind == INVOICE,
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return None
    return dict(max(rows, key=lambda row: _version_rank(str(row["external_version"]))))


def store_document(
    uow: UnitOfWork,
    draft: ports.NormalisedInvoiceDraft,
    *,
    source_record_id: UUID,
    customer_id: UUID,
    contracting_entity_id: UUID,
) -> UUID:
    """T-SRC-04 and T-SRC-05 of the document; the id of the stored row when its identity already
    exists (a reprocess, a replayed version)."""
    session = uow.session
    existing = stored_document(session, draft)
    if existing is not None:
        return UUID(str(existing["id"]))
    entity_code = draft.legal_entity_code or str(
        session.execute(
            select(legal_entity.c.code).where(legal_entity.c.id == contracting_entity_id)
        ).scalar_one()
    )
    principal = uow.principal
    created = _created(uow)
    invoice_id = new_id()
    session.execute(
        insert(source_invoice).values(
            tenant_id=principal.tenant_id,
            id=invoice_id,
            source_record_id=source_record_id,
            source_system=draft.source_system.value,
            external_invoice_id=draft.external_invoice_id,
            external_version=draft.external_version,
            invoice_number=draft.invoice_number,
            document_kind=draft.document_kind,
            issue_date=draft.issue_date,
            due_date=draft.due_date,
            is_cancellable=draft.is_cancellable,
            customer_external_id=draft.customer_external_id,
            customer_id=customer_id,
            legal_entity_code=entity_code,
            currency=draft.currency,
            total_amount=draft.total,
            tax_amount=Decimal(0),
            credited_invoice_external_id=draft.credited_invoice_external_id,
            custom_attributes=dict(draft.custom_attributes),
            **created,
        )
    )
    rows = [
        {
            "tenant_id": principal.tenant_id,
            "id": new_id(),
            "source_invoice_id": invoice_id,
            "line_external_id": line.line_external_id,
            "contract_ref": line.contract_ref,
            "obligation_ref": line.obligation_ref,
            "product_code": line.product_code,
            "quantity": line.quantity,
            "amount": _signed(draft, line.amount),
            "tax_lines": [],
            "service_period_start": line.service_period_start,
            "service_period_end": line.service_period_end,
            "custom_attributes": {},
            **created,
        }
        for line in draft.lines
    ]
    session.execute(insert(source_invoice_line), rows)
    audit_writer.record_facts(
        uow, action=DOCUMENT_ACTION, object_type="source_invoice", ids=[invoice_id]
    )
    audit_writer.record_facts(
        uow,
        action=DOCUMENT_LINE_ACTION,
        object_type="source_invoice_line",
        ids=[row["id"] for row in rows],
        detail={"source_invoice_id": str(invoice_id)},
    )
    return invoice_id


def _money(amount: Decimal, currency: str) -> dict[str, str]:
    return {"amount": format(amount, "f"), "currency": currency}


def event_items(
    draft: ports.NormalisedInvoiceDraft,
    lines: Sequence[ports.NormalisedInvoiceLine],
    *,
    source_invoice_id: UUID,
    credited_invoice_number: str | None,
) -> list[EventAppendItemIn]:
    """The API-S-EventAppend items of ``lines`` (§16.3 payloads), effective on the issue date."""
    found: list[EventAppendItemIn] = []
    for line in lines:
        payload: dict[str, Any]
        if draft.document_kind == CREDIT_MEMO:
            payload = {
                "credit_memo_number": draft.invoice_number,
                "credited_invoice_number": credited_invoice_number,
                "obligation_key": line.obligation_ref,
                "amount": _money(line.amount, draft.currency),
                "issue_date": draft.issue_date.isoformat(),
            }
            event_type = ContractEventType.CREDIT_MEMO_RECORDED
        else:
            payload = {
                "invoice_number": draft.invoice_number,
                "line_external_id": line.line_external_id,
                "obligation_key": line.obligation_ref,
                "amount": _money(line.amount, draft.currency),
                "issue_date": draft.issue_date.isoformat(),
                "due_date": None if draft.due_date is None else draft.due_date.isoformat(),
                "is_cancellable": draft.is_cancellable or None,
                "service_period_start": (
                    None
                    if line.service_period_start is None
                    else line.service_period_start.isoformat()
                ),
                "service_period_end": (
                    None if line.service_period_end is None else line.service_period_end.isoformat()
                ),
                "source_invoice_id": str(source_invoice_id),
            }
            event_type = ContractEventType.BILLING_RECORDED
        found.append(
            EventAppendItemIn(
                event_type=event_type,
                effective_date=draft.issue_date,
                obligation_key=line.obligation_ref,
                payload={name: value for name, value in payload.items() if value is not None},
            )
        )
    return found


def append_document(
    uow: UnitOfWork,
    draft: ports.NormalisedInvoiceDraft,
    lines: Sequence[tuple[int, ports.NormalisedInvoiceLine]],
    *,
    contract_id: UUID,
    source_invoice_id: UUID,
    source_record_id: UUID,
    sync_run_id: UUID,
    credited_invoice_number: str | None,
) -> list[Mapping[str, Any]]:
    """Append the events of ``lines`` — (ordinal in the document, line) pairs of ONE contract — and
    answer the event rows in line order; ``Problem`` when the route would refuse them."""
    # Imported here: the contract commands reach this package through ssp.resolution.
    from erev_api.domain.contracts import events as contract_events
    from erev_api.domain.contracts import repo
    from erev_api.events.stream import append_events

    session = uow.session
    _, current = repo.lock_group_then_contract(session, contract_id)  # DG-KRN-DB-08 rev 1.36
    time_zone = str(
        session.execute(
            select(legal_entity.c.time_zone).where(
                legal_entity.c.id == current["contracting_entity_id"]
            )
        ).scalar_one()
    )
    items = event_items(
        draft,
        [line for _, line in lines],
        source_invoice_id=source_invoice_id,
        credited_invoice_number=credited_invoice_number,
    )
    recorded = contract_events.to_events(items, time_zone=time_zone, is_manual=False)
    recorded = contract_events.step1_events(uow, current, recorded)
    contract_events.check_bounds(session, current, recorded, known_at=uow.now)
    identity = SourceIdentity(
        draft.source_system,
        object_type_of(draft),
        draft.external_invoice_id,
        draft.external_version,
    )
    stamped = [
        dataclasses.replace(
            event,
            idempotency_key=adapter_event_key(identity, ordinal),
            source_record_id=source_record_id,
            sync_run_id=sync_run_id,
        )
        for (ordinal, _), event in zip(lines, recorded, strict=True)
    ]
    return append_events(
        uow,
        contract_id=contract_id,
        expected_stream_version=int(current["head_stream_version"]),
        events=stamped,
        origin="ADAPTER",
    )


def link_document(
    uow: UnitOfWork, *, contract_id: UUID, source_record_id: UUID, event_id: UUID
) -> UUID | None:
    """T-CON-02: the contract ↔ source record link of role ``INVOICE`` naming the first event of
    the document on that contract; None when the link exists (a replay)."""
    session = uow.session
    existing = session.execute(
        select(contract_source_link.c.id).where(
            contract_source_link.c.contract_id == contract_id,
            contract_source_link.c.source_record_id == source_record_id,
            contract_source_link.c.link_role == LINK_ROLE,
        )
    ).first()
    if existing is not None:
        return None
    link_id = new_id()
    session.execute(
        insert(contract_source_link).values(
            tenant_id=uow.principal.tenant_id,
            id=link_id,
            contract_id=contract_id,
            source_record_id=source_record_id,
            link_role=LINK_ROLE,
            contract_event_id=event_id,
            **_created(uow),
        )
    )
    audit_writer.record_facts(
        uow,
        action=LINK_ACTION,
        object_type="contract_source_link",
        ids=[link_id],
        detail={"link_role": LINK_ROLE},
        contract_id=contract_id,
    )
    return link_id
