"""Audit hash chain KRN-AUD (dev-guide §5.5 DG-KRN-AUD-02, DG-KRN-AUD-03, DG-KRN-AUD-09; 04
T-PLT-19, T-PLT-22, T-PLT-48, DB-09).

Events chain per tenant in ``chain_seq`` order. ``hmac`` = HMAC-SHA256 with the tenant key
(``tenant.audit_hmac_key_id``) over ``prev_hmac ‖ canonical(row without hmac)``. The append takes
the ``audit_chain_head`` row lock first, so it is the last lock of the transaction (DG-KRN-DB-08).
The DB-09 trigger re-checks the sequence and the previous HMAC and advances the head.

An event that names contracts (``detail.contract_id`` / ``detail.contract_ids``) gets one
``audit_event_contract`` row for each, in the same statement batch (04 T-PLT-48): the index a read
by contract uses. It is derived from the event as stored and is not part of the chain.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from erev_api.audit import contract_key
from erev_api.audit.redact import pseudonymise, pseudonymise_diff
from erev_api.auth.keyring import KeyRing
from erev_api.db.tables.platform import (
    audit_chain_head,
    audit_event,
    audit_event_contract,
    tenant,
)
from erev_api.problems import Problem

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

# The columns an event carries before the append assigns its chain position (T-PLT-19).
CHAIN_COLUMNS = ("chain_seq", "prev_hmac", "hmac", "hmac_key_id")


def canonical_event(row: Mapping[str, Any]) -> bytes:
    """Canonical bytes (§5.17) of every T-PLT-19 column except ``hmac``."""
    values = {name: row[name] for name in audit_event.c.keys() if name != "hmac"}
    if values["source_ip"] is not None:
        values["source_ip"] = str(ipaddress.ip_address(str(values["source_ip"])))
    return canonical_bytes(values)


def compute_hmac(key: bytes, prev_hmac: str | None, row: Mapping[str, Any]) -> str:
    message = (prev_hmac or "").encode("ascii") + canonical_event(row)
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def append_events(
    session: Session, *, tenant_id: UUID, keyring: KeyRing, events: Sequence[Mapping[str, Any]]
) -> int:
    """Append ``events`` in order to the tenant's chain inside the caller's transaction."""
    if not events:
        return 0
    head = session.execute(
        select(audit_chain_head.c.last_chain_seq, audit_chain_head.c.last_hmac)
        .where(audit_chain_head.c.tenant_id == tenant_id)
        .with_for_update()
    ).one_or_none()
    if head is None:
        # Fail closed: a tenant without a head row cannot be audited (DB-09).
        raise Problem("ledger-integrity", "The audit chain head is missing.", code="EREV-AUD-001")
    key_id = session.execute(
        select(tenant.c.audit_hmac_key_id).where(tenant.c.id == tenant_id)
    ).scalar_one()
    key = keyring.tenant_audit_key(str(key_id))
    seq, prev_hmac = int(head.last_chain_seq), head.last_hmac
    links: list[dict[str, Any]] = []
    for event in events:
        if event["tenant_id"] != tenant_id:
            raise ValueError("an audit event belongs to the tenant whose chain it joins")
        seq += 1
        row: dict[str, Any] = {
            **event,
            "before": pseudonymise(key, event["before"]),
            "after": pseudonymise(key, event["after"]),
            "diff": pseudonymise_diff(key, event["diff"]),
            "detail": pseudonymise(key, event["detail"]),
            "chain_seq": seq,
            "prev_hmac": prev_hmac,
            "hmac_key_id": str(key_id),
        }
        row["hmac"] = compute_hmac(key, prev_hmac, row)
        session.execute(insert(audit_event).values(**row))
        prev_hmac = row["hmac"]
        # 04 T-PLT-48: the key of the event as it is stored, once more as plain columns.
        links += [
            {
                "tenant_id": tenant_id,
                "contract_id": contract_id,
                "chain_seq": seq,
                "occurred_at": row["occurred_at"],
                "audit_event_id": row["id"],
            }
            for contract_id in contract_key.named(row["detail"])
        ]
    if links:
        session.execute(insert(audit_event_contract), links)
    return len(events)


def flush(uow: UnitOfWork) -> int:
    """DG-KRN-AUD-02: append the buffered events in buffer order; zero events write nothing."""
    return append_events(
        uow.session,
        tenant_id=uow.principal.tenant_id,
        keyring=uow.keyring,
        events=uow.drain_audit_events(),
    )
