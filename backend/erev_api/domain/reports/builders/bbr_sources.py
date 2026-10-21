"""Source-time billing and posted revenue contributions for RPT-37.

Keep event inputs (including voids and invoice status updates) so the report can rebuild the
engine's document identity decisions. Revenue belongs to the posting entity and posting period;
billing belongs to the contracting entity and document effective date. Neither is inferred from
current contract balances. Booking/application valuation is supplied separately by the report.
"""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import func, select

from erev_api.db.tables import contract_event, modification, subledger_line, subledger_posting_seal
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.contract_balance_rollforward import (
    BillingSourceEvent,
    kept_documents,
)
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.uow import UnitOfWork

EVIDENCE: Final = "bbr_source_rows_v1"
EVENT_TYPES: Final = (
    "CONTRACT_BOOKED",
    "CONTRACT_ACTIVATED",
    "CONTRACT_AMENDED",
    "CONTRACT_TERMINATED",
    "REGROUPED",
    "BILLING_RECORDED",
    "CREDIT_MEMO_RECORDED",
    "EVENT_VOIDED",
    "CONTRACT_VOIDED",
)


@dataclass(frozen=True, slots=True)
class Contribution:
    source_type: str
    source_id: UUID
    contract_id: UUID
    entity_id: UUID
    effective_date: date
    currency: str
    amount: Decimal
    # Revenue has an authoritative posting period and functional amount. Billing conversion
    # must use its own governed FX basis; a missing value must never mean zero or parity.
    period_id: UUID | None = None
    functional_currency: str | None = None
    functional_amount: Decimal | None = None
    basis_ids: tuple[UUID, ...] = ()


def read(uow: UnitOfWork, params: ReportParams, *, period_ids: Iterable[UUID]) -> dict[str, Any]:
    """Capture raw scoped inputs or reload exactly the inputs retained by the original run."""
    if params.period_lock_id is not None:
        raise Problem("validation-failed", "Bookings, billings and revenue has no lock dataset.")
    if params.book_code is None:
        raise tie_outs.invalid("book", "Choose a book.")
    cutoff = params.binding.cutoff if params.binding is not None else params.known_at
    wanted_periods = sorted({str(p) for p in period_ids})
    if params.sources is not None:
        params.sources.record_cutoff(cutoff)
    if params.binding is not None:
        result = tie_outs.bound_evidence(params, EVIDENCE)
    else:
        tenant = uow.principal.tenant_id
        events = (
            select(
                contract_event.c.id,
                contract_event.c.contract_id,
                contract_event.c.contracting_entity_id,
                contract_event.c.event_type,
                contract_event.c.effective_date,
                contract_event.c.record_seq,
                contract_event.c.recorded_at,
                contract_event.c.created_at,
                contract_event.c.payload,
                contract_event.c.supersedes_event_id,
            )
            .where(
                contract_event.c.tenant_id == tenant,
                contract_event.c.contracting_entity_id.in_(params.entity_ids),
                contract_event.c.event_type.in_(EVENT_TYPES),
                contract_event.c.recorded_at <= cutoff,
                contract_event.c.created_at <= cutoff,
            )
            .order_by(contract_event.c.record_seq, contract_event.c.id)
        )
        revenue = (
            select(
                subledger_line.c.id,
                subledger_line.c.contract_id,
                subledger_line.c.entity_id,
                subledger_line.c.effective_date,
                subledger_line.c.period_id,
                subledger_line.c.txn_currency,
                subledger_line.c.amount_txn,
                subledger_line.c.functional_currency,
                subledger_line.c.amount_functional,
                subledger_line.c.book_code,
                subledger_line.c.recorded_at,
                subledger_line.c.recorded_server_at,
                subledger_posting_seal.c.sealed_server_at,
                func.erev.subledger_commit_time(subledger_line.c.subledger_posting_id).label(
                    "committed_server_at"
                ),
            )
            .select_from(subledger_line)
            .join(
                subledger_posting_seal,
                (subledger_posting_seal.c.tenant_id == subledger_line.c.tenant_id)
                & (
                    subledger_posting_seal.c.subledger_posting_id
                    == subledger_line.c.subledger_posting_id
                )
                & (subledger_posting_seal.c.book_code == subledger_line.c.book_code),
            )
            .where(
                subledger_line.c.tenant_id == tenant,
                subledger_line.c.entity_id.in_(params.entity_ids),
                subledger_line.c.book_code == params.book_code,
                subledger_line.c.period_id.in_([UUID(p) for p in wanted_periods]),
                subledger_line.c.account_role == "REVENUE",
                subledger_line.c.recorded_at <= cutoff,
                subledger_line.c.recorded_server_at <= cutoff,
                subledger_posting_seal.c.sealed_server_at <= cutoff,
                func.erev.subledger_commit_time(subledger_line.c.subledger_posting_id) <= cutoff,
            )
            .order_by(subledger_line.c.period_id, subledger_line.c.id)
        )
        event_rows = [dict(r) for r in uow.session.execute(events).mappings()]
        booking_ids = [r["id"] for r in event_rows if str(r["event_type"]) == "CONTRACT_BOOKED"]
        modification_bookings = list(
            uow.session.scalars(
                select(modification.c.applied_event_id).where(
                    modification.c.tenant_id == tenant,
                    modification.c.applied_event_id.in_(booking_ids),
                )
            )
        )
        result = json.loads(
            canonical_bytes(
                redact_contacts(
                    {
                        "book_code": params.book_code,
                        "commit_visibility": True,
                        "period_ids": wanted_periods,
                        "events": event_rows,
                        "modification_booking_ids": modification_bookings,
                        "revenue": [dict(r) for r in uow.session.execute(revenue).mappings()],
                    }
                )
            )
        )
        tie_outs.record_evidence(params, EVIDENCE, result)
    validate(result, params, cutoff=cutoff, period_ids=wanted_periods)
    return dict(result)


def validate(
    source: Mapping[str, Any], params: ReportParams, *, cutoff: datetime, period_ids: list[str]
) -> None:
    if source["book_code"] != params.book_code or source["period_ids"] != period_ids:
        raise Problem("invalid-transition", "Retained BBR sources belong to another book or range.")
    scope = {str(e) for e in params.entity_ids}
    for row in source["events"]:
        if row["contracting_entity_id"] not in scope:
            raise Problem("forbidden", "Retained billing sources exceed the report entity scope.")
        if any(datetime.fromisoformat(row[k]) > cutoff for k in ("recorded_at", "created_at")):
            raise Problem("invalid-transition", "Retained event exceeds the source cutoff.")
    for row in source["revenue"]:
        if row["entity_id"] not in scope:
            raise Problem("forbidden", "Retained revenue sources exceed the report entity scope.")
        if source.get("commit_visibility"):
            if not row.get("committed_server_at") or (
                datetime.fromisoformat(row["committed_server_at"]) > cutoff
            ):
                raise Problem("invalid-transition", "Retained revenue commit exceeds the cutoff.")
        if (
            row["book_code"] != params.book_code
            or row["period_id"] not in period_ids
            or any(
                datetime.fromisoformat(row[k]) > cutoff
                for k in ("recorded_at", "recorded_server_at", "sealed_server_at")
            )
        ):
            raise Problem("invalid-transition", "Retained revenue exceeds the source window.")


def billings(source: Mapping[str, Any]) -> tuple[Contribution, ...]:
    """Net billing documents, retaining their event identities for period/cell contributors."""
    streams: dict[str, list[BillingSourceEvent]] = {}
    voided: dict[str, set[UUID]] = {}
    void_contracts: set[str] = set()
    by_id = {r["id"]: r for r in source["events"]}
    for row in source["events"]:
        cid = row["contract_id"]
        if row["event_type"] == "EVENT_VOIDED":
            if row["supersedes_event_id"] is not None:
                voided.setdefault(cid, set()).add(UUID(row["supersedes_event_id"]))
        elif row["event_type"] == "CONTRACT_VOIDED":
            void_contracts.add(cid)
        else:
            streams.setdefault(cid, []).append(
                BillingSourceEvent(
                    UUID(row["id"]),
                    UUID(cid),
                    row["event_type"],
                    date.fromisoformat(row["effective_date"]),
                    row["record_seq"],
                    row["payload"],
                    datetime.fromisoformat(row["recorded_at"]),
                )
            )
    result = []
    for cid, events in streams.items():
        if cid in void_contracts:
            continue
        for doc in kept_documents(events, voided.get(cid, ())):
            row = by_id[str(doc.event_id)]
            result.append(
                Contribution(
                    "contract_event",
                    doc.event_id,
                    UUID(cid),
                    UUID(row["contracting_entity_id"]),
                    doc.effective_date,
                    row["payload"]["amount"]["currency"],
                    doc.amount,
                )
            )
    return tuple(sorted(result, key=lambda r: (r.effective_date, str(r.source_id))))


def revenue(source: Mapping[str, Any]) -> tuple[Contribution, ...]:
    """Credits increase revenue; debit reversals reduce it. Preserve both currency amounts."""
    return tuple(
        Contribution(
            "subledger_line",
            UUID(row["id"]),
            UUID(row["contract_id"]),
            UUID(row["entity_id"]),
            date.fromisoformat(row["effective_date"]),
            row["txn_currency"],
            -Decimal(row["amount_txn"]),
            UUID(row["period_id"]),
            row["functional_currency"],
            -Decimal(row["amount_functional"]),
        )
        for row in source["revenue"]
    )
