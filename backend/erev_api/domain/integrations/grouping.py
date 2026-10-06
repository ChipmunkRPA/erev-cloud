"""Ingestion grouping policy (ENGINE_SPEC §2.4 S02-R-13; 04 T-PLT-31
``integration.grouping_fields``, T-SRC-02 ``grouping_values``, T-SRC-03, T-CON-02; 05 §5.1 ADP-03,
ADP-05; SCREENS_B §9.6; 03 REQ-CON-011; BUILD_SPEC DIN-10).

``integration.grouping_fields`` lists at most five canonical order fields (``FIELDS``, the T-SRC-02
header members; the legacy parity value ``contract_unique_name`` names ``order_number``). The
grouping key of a normalised order is the canonical JSON array of their values in setting order
(``grouping_key``), and ``source_order.grouping_values`` records the values by field.

``ingest_order`` routes one normalised order (``NormalisedOrder``: the header and lines that an
adapter's normalisation produces, T-SRC-02 and T-SRC-03):

1. an order whose key equals the key of an order booked on a contract (``contract_source_link``
   ``BOOKING``) is a candidate modification of that contract (ADP-05): its ``source_order`` rows are
   recorded and nothing is appended to the contract;
2. any other order books a DRAFT contract whose ``external_id`` is the order number, with origin
   ``ADAPTER``, the ADP-03 idempotency key of its source version, its ``source_order`` rows and the
   ``BOOKING`` link.

[J] L6-1-Q-6: the DRAFT ``modification`` of step 1 (04 T-CON-06) is BUILD_SPEC CTR-17's object,
which this release defers (plan-vabc ``moved_to_post_rc``), and no revision creates the table.
``ingest_order`` returns the candidate (``CANDIDATE_MODIFICATION`` with the contract) for CTR-17 to
store.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import and_, insert, or_, select
from sqlalchemy.orm import Session

from erev_api.audit import writer as audit_writer
from erev_api.db import new_id
from erev_api.db.tables import (
    audit_event,
    contract_source_link,
    external_id_map,
    product,
    source_order,
    source_order_line,
    source_record,
)
from erev_api.domain.integrations.normalise import SourceIdentity, adapter_event_key
from erev_api.enums import AuditOutcome, SourceObjectType, SourceSystem
from erev_api.problems import ProblemError
from erev_api.registry import resolve as registry
from erev_api.schemas.contracts import ContractCreateIn

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "FIELDS",
    "MAX_FIELDS",
    "SETTING",
    "TOO_MANY",
    "GroupingOutcome",
    "NormalisedOrder",
    "OrderLine",
    "Routed",
    "grouping_fields",
    "grouping_key",
    "grouping_values",
    "ingest_order",
    "matching_contract",
    "setting_errors",
]

SETTING: Final = "integration.grouping_fields"
MAX_FIELDS: Final = 5
TOO_MANY: Final = "Choose at most five fields."  # SCREENS_B §9.6
UNKNOWN_FIELD: Final = "{field} is not a canonical order field."
RULE_ID: Final = "POLICY_VALUE_INVALID"  # 04 table 15.4-B
BOOKING: Final = "BOOKING"  # T-CON-02 link role
ORDER_ACTION: Final = "source_order.create"
ORDER_LINE_ACTION: Final = "source_order_line.create"
LINK_ACTION: Final = "contract_source_link.create"
# Canonical order field → ``NormalisedOrder`` member (T-SRC-02).
FIELDS: Final[Mapping[str, str]] = {
    "order_number": "order_number",
    "contract_unique_name": "order_number",
    "external_order_id": "external_order_id",
    "customer_external_id": "customer_external_id",
    "legal_entity_code": "legal_entity_code",
    "transaction_currency": "transaction_currency",
    "po_number": "po_number",
    "parent_order_external_id": "parent_order_external_id",
    "payment_terms": "payment_terms",
    "document_ref": "document_ref",
}


class GroupingOutcome(StrEnum):
    """What S02-R-13 made of an order."""

    NEW_CONTRACT = "NEW_CONTRACT"
    CANDIDATE_MODIFICATION = "CANDIDATE_MODIFICATION"


@dataclass(frozen=True, slots=True)
class OrderLine:
    """One normalised order line (T-SRC-03)."""

    line_external_id: str
    product_code: str
    quantity: Decimal
    total_price: Decimal
    start_date: date | None = None
    end_date: date | None = None
    performing_entity_code: str | None = None
    # Codex 0652 §1: the resolved record code when the source code is an alias — BOOKING data only;
    # ``product_code`` stays the SOURCE code (T-SRC-03), never overwritten by the resolution.
    booking_product_code: str | None = None

    @property
    def booked_code(self) -> str:
        return self.booking_product_code or self.product_code


@dataclass(frozen=True, slots=True)
class NormalisedOrder:
    """One normalised order header with its lines (T-SRC-02), stored as ``source_record_id``."""

    source_record_id: UUID
    source_system: SourceSystem
    external_order_id: str
    external_version: str
    order_number: str
    order_date: date
    customer_external_id: str
    customer_id: UUID
    legal_entity_code: str
    transaction_currency: str
    lines: tuple[OrderLine, ...]
    po_number: str | None = None
    parent_order_external_id: str | None = None
    payment_terms: str | None = None
    document_ref: str | None = None
    custom_attributes: Mapping[str, Any] = field(default_factory=dict)
    amendment_reason: str | None = None  # T-SRC-02 ``amendment_reason``; a class-A retained fact
    # 05 ADP-16, ADP-17 rev 1.204 (item ACT-FLAGS-1): BOOKING data only, as the source object
    # states it at this normalisation — the two terms are kept on the booking (04 T-CON-01, the
    # ``CONTRACT_BOOKED`` payload) and in the raw source record, not in T-SRC-02.
    acceptance_clause: bool | None = None
    side_letter: bool | None = None


@dataclass(frozen=True, slots=True)
class Routed:
    """The route of one order: the contract it booked or would modify, and its stored order."""

    outcome: GroupingOutcome
    contract_id: UUID
    grouping_key: str
    source_order_id: UUID
    event_id: UUID | None


def setting_errors(values: Mapping[str, Any]) -> list[ProblemError]:
    """The findings of ``integration.grouping_fields`` in a registry version's values: at most five
    canonical order fields (SCREENS_B §9.6)."""
    chosen = values.get(SETTING)
    if not isinstance(chosen, list):
        return []
    where = f"values.{SETTING}"
    if len(chosen) > MAX_FIELDS:
        return [ProblemError(field=where, rule_id=RULE_ID, message=TOO_MANY)]
    unknown = [name for name in chosen if isinstance(name, str) and name not in FIELDS]
    if unknown:
        message = UNKNOWN_FIELD.format(field=unknown[0])
        return [ProblemError(field=where, rule_id=RULE_ID, message=message)]
    return []


def grouping_fields(session: Session, *, known_at: datetime) -> tuple[str, ...]:
    """The tenant's ``integration.grouping_fields`` at ``known_at``."""
    return tuple(str(name) for name in registry.setting(session, SETTING, known_at=known_at))


def grouping_values(order: NormalisedOrder, fields: Sequence[str]) -> dict[str, Any]:
    """T-SRC-02 ``grouping_values``: the order's value of each field, by field."""
    return {name: getattr(order, FIELDS.get(name, name), None) for name in fields}


def grouping_key(values: Mapping[str, Any], fields: Sequence[str]) -> str:
    """S02-R-13: the canonical JSON array of the values in setting order."""
    ordered = [values.get(name) for name in fields]
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))


def matching_contract(session: Session, key: str, fields: Sequence[str]) -> UUID | None:
    """The contract whose booked order has the key, earliest link first."""
    rows = session.execute(
        select(contract_source_link.c.contract_id, source_order.c.grouping_values)
        .select_from(
            contract_source_link.join(
                source_order,
                and_(
                    source_order.c.tenant_id == contract_source_link.c.tenant_id,
                    source_order.c.source_record_id == contract_source_link.c.source_record_id,
                ),
            )
        )
        .where(contract_source_link.c.link_role == BOOKING)
        .order_by(contract_source_link.c.created_at, contract_source_link.c.id)
    ).all()
    for contract_id, values in rows:
        if grouping_key(dict(values or {}), fields) == key:
            return UUID(str(contract_id))
    return None


def _created(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }


# --- reuse of a stored order identity (04 §16.14 rev 1.81, amended in place; Codex 0545 §2 R1 /
# 0603 §4 / 0606): T-SRC-02 / T-SRC-03 are IM-A — an identity already stored is reused, never
# stored again, and the reuse is checked in three classes BEFORE any write.
CONTENT_RULE: Final = "SOURCE_ORDER_CONTENT_MISMATCH"
DERIVATION_RULE: Final = "SOURCE_ORDER_DERIVATION_CHANGED"
CONTENT_MISMATCH: Final = (
    "order {order} version {version}: the stored source_order rows differ from the incoming record"
    " in source-authored members ({members}) — refused by name; never reused silently, never"
    " overwritten (04 §16.14; T-SRC-02 / T-SRC-03 are IM-A)"
)
DERIVATION_CHANGED: Final = (
    "order {order} version {version}: the current connection configuration or mapping derives"
    " ({members}) differently from the stored rows — refused by name; restore the setting or ingest"
    " a new source version (04 §16.14)"
)
# Class A header members: T-SRC-02 column ↔ draft member (source-authored; salesforce.py:127–147).
RETAINED_HEADER: Final[Mapping[str, str]] = {
    "order_number": "order_number",
    "order_date": "order_date",
    "customer_external_id": "customer_external_id",
    "transaction_currency": "transaction_currency",
    "po_number": "po_number",
    "parent_order_external_id": "parent_order_external_id",
    "document_ref": "document_ref",
}
# Class A line members: T-SRC-03 column ↔ draft line member (the SOURCE product code, quantities,
# money, dates; salesforce.py:113–122).
RETAINED_LINE: Final[tuple[str, ...]] = (
    "product_code",
    "quantity",
    "total_price",
    "start_date",
    "end_date",
)


@dataclass(frozen=True, slots=True)
class StoredOrder:
    """The stored T-SRC-02 row of an order identity and its T-SRC-03 lines by line external id."""

    id: UUID
    source_record_id: UUID
    header: Mapping[str, Any]
    lines: Mapping[str, Mapping[str, Any]]


def stored_order(
    session: Session, *, source_system: SourceSystem, external_order_id: str, external_version: str
) -> StoredOrder | None:
    """The stored rows of the ``ux_source_order`` identity (system, external order id, version)."""
    row = (
        session.execute(
            select(source_order).where(
                source_order.c.source_system == source_system.value,
                source_order.c.external_order_id == external_order_id,
                source_order.c.external_version == external_version,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    lines = session.execute(
        select(source_order_line).where(source_order_line.c.source_order_id == row["id"])
    ).mappings()
    return StoredOrder(
        id=UUID(str(row["id"])),
        source_record_id=UUID(str(row["source_record_id"])),
        header=dict(row),
        lines={str(line["line_external_id"]): dict(line) for line in lines},
    )


def same_digest(session: Session, stored_record: UUID, incoming_record: UUID) -> bool:
    """Class A identity: the same record, else an equal retained TOKENISED payload digest
    (``source_record.payload_sha256`` — the representation stored at first receipt, which a
    reprocess reconstructs; never pre-tokenisation bytes)."""
    if stored_record == incoming_record:
        return True
    digests = {
        UUID(str(row_id)): str(digest)
        for row_id, digest in session.execute(
            select(source_record.c.id, source_record.c.payload_sha256).where(
                source_record.c.id.in_([stored_record, incoming_record])
            )
        )
    }
    found = digests.get(stored_record)
    return found is not None and found == digests.get(incoming_record)


def _same(stored: Any, incoming: Any) -> bool:
    if stored is None or incoming is None:
        return stored is None and incoming is None
    if isinstance(incoming, Decimal) or isinstance(stored, Decimal):
        return Decimal(str(stored)) == Decimal(str(incoming))
    if isinstance(incoming, date) or isinstance(stored, date):
        return _as_date(stored) == _as_date(incoming)
    return str(stored) == str(incoming)


def _as_date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


# --- the product's code AT a row's receipt (04 §16.14 rev 1.91; Codex production-20260922-1442 §1
# and 1508 §1, DIN-HISTORICAL-ALIAS-RENAME-1): the audit trail is the receipt-time code evidence,
# ordered by CHAIN POSITION and never by clock — a rename, a receipt and a second rename may share
# one clock instant (``uow.now`` is captured once per command; DB-09 orders the chain, not the
# clock), and only the chain separates them. The chain is read tenant-scoped and read-only.
PRODUCT_OBJECT: Final = "product"  # == approvals.subjects.PRODUCT_OBJECT (pinned by a CPU witness)
PRODUCT_UPDATE_ACTION: Final = "product.update"  # == reference.commands.PRODUCT_UPDATE_ACTION
SOURCE_ORDER_OBJECT: Final = "source_order"  # the object_type of ``_store_order``'s receipt anchor


class HistoryState(StrEnum):
    """How the code compared for a pre-1.81 row's alias target was established — the failure
    record's ``history`` names it. Only RECEIPT_ANCHORED is recovery; every other state compares
    the CURRENT code, today's comparison kept as a CONSERVATIVE REFUSAL of renamed rows."""

    RECEIPT_ANCHORED = "receipt-anchored"
    ANCHOR_MISSING = "anchor-missing"  # no SUCCESS source_order.create event names the row
    ANCHOR_AMBIGUOUS = "anchor-ambiguous"  # more than one does
    HISTORY_DISCONTINUOUS = "history-discontinuous"  # an event disagrees with the reconstruction
    NO_RECEIPT_ROW = "no-receipt-row"  # the stored row's id is unknown to the caller


HISTORY_UNVERIFIED: Final = (
    " — the alias target's code at receipt could not be established from the audit trail"
    " ({states}); compared against the current code: a conservative refusal, not a recovery"
)


@dataclass(frozen=True, slots=True)
class AliasLineage:
    """Per raw source code: the alias target at receipt and the code compared for it, with how that
    code was established (``evidence``) and how many code-bearing renames were walked back."""

    targets: Mapping[str, tuple[UUID, str]]
    evidence: Mapping[str, HistoryState]
    renames: Mapping[str, int]

    @property
    def unanchored(self) -> dict[str, str]:
        return {
            code: state.value
            for code, state in self.evidence.items()
            if state is not HistoryState.RECEIPT_ANCHORED
        }


EMPTY_LINEAGE: Final = AliasLineage(targets={}, evidence={}, renames={})


def receipt_anchor(
    session: Session, tenant_id: UUID, order_id: UUID
) -> tuple[int | None, HistoryState]:
    """The chain position of the row's own SUCCESS ``source_order.create`` event — the receipt
    anchor (``_store_order`` → ``audit_writer.record_facts(ids=[order_id])``: ``object_id`` NULL,
    the row's id in ``detail.ids``): matched by tenant, action, object type, outcome and exact id
    membership; exactly one → anchored."""
    rows = session.execute(
        select(audit_event.c.chain_seq).where(
            audit_event.c.tenant_id == tenant_id,
            audit_event.c.action == ORDER_ACTION,
            audit_event.c.object_type == SOURCE_ORDER_OBJECT,
            audit_event.c.outcome == AuditOutcome.SUCCESS.value,
            audit_event.c.detail["ids"].contains([str(order_id)]),
        )
    ).all()
    if len(rows) == 1:
        return int(rows[0][0]), HistoryState.RECEIPT_ANCHORED
    return None, HistoryState.ANCHOR_MISSING if not rows else HistoryState.ANCHOR_AMBIGUOUS


def code_at_receipt(
    session: Session, tenant_id: UUID, product_id: UUID, current: str, anchor_seq: int
) -> tuple[str, HistoryState, int]:
    """``current`` walked back through the product's code-bearing SUCCESS ``product.update`` events
    AFTER the receipt's chain position (latest first), each ``after.code`` agreeing with the
    reconstructed value before its ``before.code`` is taken; ``before`` == ``after`` is a no-op; a
    null code or a disagreement is HISTORY_DISCONTINUOUS (the current code is then compared). No
    clock predicate: ``update_product`` audits only the CHANGED members (a rename carries both
    codes, a non-code update neither), so the two ``has_key`` predicates select actual code changes.
    """
    events = session.execute(
        select(audit_event.c.before["code"].astext, audit_event.c.after["code"].astext)
        .where(
            audit_event.c.tenant_id == tenant_id,
            audit_event.c.object_type == PRODUCT_OBJECT,
            audit_event.c.action == PRODUCT_UPDATE_ACTION,
            audit_event.c.object_id == product_id,
            audit_event.c.outcome == AuditOutcome.SUCCESS.value,
            audit_event.c.before.has_key("code"),
            audit_event.c.after.has_key("code"),
            audit_event.c.chain_seq > anchor_seq,
        )
        .order_by(audit_event.c.chain_seq.desc())
    ).all()
    reconstructed, renames = current, 0
    for before_code, after_code in events:
        if before_code is None or after_code is None:
            return current, HistoryState.HISTORY_DISCONTINUOUS, renames
        if before_code == after_code:
            continue  # a no-op update: no code change
        if str(after_code) != reconstructed:
            return current, HistoryState.HISTORY_DISCONTINUOUS, renames
        reconstructed, renames = str(before_code), renames + 1
    return reconstructed, HistoryState.RECEIPT_ANCHORED, renames


def alias_lineage_at(
    session: Session,
    connection_id: UUID,
    codes: Collection[str],
    at: Any,
    *,
    tenant_id: UUID,
    order_id: UUID | None,
) -> AliasLineage:
    """The connection's T-INT-04 ``product`` links of ``codes`` in force at ``at`` (``valid_from <=
    at < valid_to``, ``valid_to`` null = live) — the alias lineage a row stored before rev 1.81's
    source-code rule resolved through at its receipt (Codex 0652 §1; a non-mutating compatibility
    path) — each with the product's code AT THE RECEIPT: rev 1.91 (Codex 1442 §1 / 1508 §1) locates
    the receipt by ``receipt_anchor`` and walks the rename audit back by chain position
    (``code_at_receipt``), so a lawful rename at any clock instant never refuses an unchanged
    pre-revision source whose history is anchored. Missing or ambiguous history keeps the current
    code and is named in ``evidence`` (a conservative refusal, not recovery)."""
    if not codes or at is None:
        return EMPTY_LINEAGE
    rows = session.execute(
        select(external_id_map.c.external_id, product.c.id, product.c.code)
        .select_from(external_id_map.join(product, product.c.id == external_id_map.c.internal_id))
        .where(
            external_id_map.c.integration_connection_id == connection_id,
            external_id_map.c.object_type == "product",
            external_id_map.c.external_id.in_(sorted(set(codes))),
            external_id_map.c.valid_from <= at,
            or_(external_id_map.c.valid_to.is_(None), external_id_map.c.valid_to > at),
        )
    ).all()
    links = {str(external): (UUID(str(pid)), str(code)) for external, pid, code in rows}
    if not links:
        return EMPTY_LINEAGE
    if order_id is None:
        anchor, state = None, HistoryState.NO_RECEIPT_ROW
    else:
        anchor, state = receipt_anchor(session, tenant_id, order_id)
    targets: dict[str, tuple[UUID, str]] = {}
    evidence: dict[str, HistoryState] = {}
    renames: dict[str, int] = {}
    resolved: dict[UUID, tuple[str, HistoryState, int]] = {}
    for external, (pid, current) in links.items():
        if anchor is None:
            targets[external], evidence[external], renames[external] = (pid, current), state, 0
            continue
        if pid not in resolved:
            resolved[pid] = code_at_receipt(session, tenant_id, pid, current, anchor)
        code, found, count = resolved[pid]
        targets[external], evidence[external], renames[external] = (pid, code), found, count
    return AliasLineage(targets=targets, evidence=evidence, renames=renames)


def history_of(lineage: AliasLineage, members: Collection[str], draft: Any) -> dict[str, Any]:
    """The failure record's ``history``: for every line named on ``product_code``, its raw code's
    alias target, the evidence state and the renames walked back."""
    named = {
        member.split(".")[1]
        for member in members
        if member.startswith("lines.") and member.endswith(".product_code")
    }
    history: dict[str, Any] = {}
    for line in draft.lines:
        code = line.product_code
        if line.line_external_id in named and code in lineage.evidence:
            product_id, _compared = lineage.targets[code]
            history[code] = {
                "product_id": str(product_id),
                "evidence": lineage.evidence[code].value,
                "renames": lineage.renames[code],
            }
    return history


def content_conflicts(
    stored: StoredOrder,
    draft: Any,
    *,
    same_content: bool,
    aliased_at_receipt: Mapping[str, tuple[UUID, str]] | None = None,
) -> list[str]:
    """Class A — RETAINED FACTS that must equal the stored rows: the retained payload digest, the
    header members and, per line (the same line set), the SOURCE product code, quantity, money and
    dates. ``draft`` is the ORIGINAL normalised draft (before the product alias rewrites codes)."""
    found: list[str] = []
    if not same_content:
        found.append("payload_sha256")
    for column, member in RETAINED_HEADER.items():
        if not _same(stored.header.get(column), getattr(draft, member, None)):
            found.append(column)
    # ``amendment_reason`` was not stored before this revision: a stored NULL is "not recorded".
    stored_reason = stored.header.get("amendment_reason")
    if stored_reason is not None and not _same(
        stored_reason, getattr(draft, "amendment_reason", None)
    ):
        found.append("amendment_reason")
    incoming_lines = {line.line_external_id: line for line in draft.lines}
    if set(incoming_lines) != set(stored.lines):
        found.append("lines")
    for key in sorted(set(incoming_lines) & set(stored.lines)):
        for member in RETAINED_LINE:
            stored_value = stored.lines[key].get(member)
            incoming_value = getattr(incoming_lines[key], member)
            if _same(stored_value, incoming_value):
                continue
            if member == "product_code" and _stored_alias_target(
                stored.lines[key], str(incoming_value), aliased_at_receipt or {}
            ):
                continue  # a row stored before the source-code rule: the alias target at receipt
            found.append(f"lines.{key}.{member}")
    return found


def _stored_alias_target(
    stored_line: Mapping[str, Any], raw_code: str, lineage: Mapping[str, tuple[UUID, str]]
) -> bool:
    """Codex 0652 §1 compatibility: a stored line whose code is not the raw source code is admitted
    only when the connection's alias lineage mapped the raw code, at the row's receipt, to exactly
    the product the row carries (``product_id`` and code) — evidence from the retained payload plus
    the alias lineage; nothing is rewritten."""
    found = lineage.get(raw_code)
    if found is None or stored_line.get("product_id") is None:
        return False
    return (
        UUID(str(stored_line["product_id"])) == found[0]
        and str(stored_line.get("product_code")) == found[1]
    )


def derivation_conflicts(
    stored: StoredOrder,
    draft: Any,
    *,
    customer_id: UUID | None,
    grouping: Mapping[str, Any],
) -> list[str]:
    """Class C — members derived from the CURRENT connection configuration or mapping, frozen at
    first ingestion: the entity (header and line) when the source names none, the mapping version,
    the customer resolution and the grouping values. A difference is a named refusal."""
    found: list[str] = []
    if not _same(stored.header.get("legal_entity_code"), draft.legal_entity_code):
        found.append("legal_entity_code")
    for key, line in ((line.line_external_id, line) for line in draft.lines):
        stored_line = stored.lines.get(key)
        if stored_line is None:
            continue
        expected = line.performing_entity_code or draft.legal_entity_code
        if not _same(stored_line.get("performing_entity_code"), expected):
            found.append(f"lines.{key}.performing_entity_code")
    stored_attributes = dict(stored.header.get("custom_attributes") or {})
    if not _same(
        stored_attributes.get("mapping_version"),
        dict(draft.custom_attributes).get("mapping_version"),
    ):
        found.append("custom_attributes.mapping_version")
    stored_customer = stored.header.get("customer_id")
    if customer_id is not None and stored_customer is not None:
        if UUID(str(stored_customer)) != customer_id:
            found.append("customer_id")
    if json.dumps(dict(stored.header.get("grouping_values") or {}), sort_keys=True) != json.dumps(
        {name: _json(value) for name, value in grouping.items()}, sort_keys=True
    ):
        found.append("grouping_values")
    return found


def _json(value: Any) -> Any:
    if isinstance(value, UUID | date):
        return str(value) if isinstance(value, UUID) else value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _store_order(uow: UnitOfWork, order: NormalisedOrder, values: Mapping[str, Any]) -> UUID:
    """The ``source_order`` and ``source_order_line`` rows of an order (T-SRC-02, T-SRC-03)."""
    session = uow.session
    tenant_id = uow.principal.tenant_id
    order_id = new_id()
    session.execute(
        insert(source_order).values(
            tenant_id=tenant_id,
            id=order_id,
            source_record_id=order.source_record_id,
            source_system=order.source_system.value,
            external_order_id=order.external_order_id,
            external_version=order.external_version,
            order_number=order.order_number,
            order_date=order.order_date,
            customer_external_id=order.customer_external_id,
            customer_id=order.customer_id,
            legal_entity_code=order.legal_entity_code,
            transaction_currency=order.transaction_currency,
            po_number=order.po_number,
            parent_order_external_id=order.parent_order_external_id,
            amendment_reason=order.amendment_reason,
            grouping_values=dict(values),
            payment_terms=order.payment_terms,
            document_ref=order.document_ref,
            custom_attributes=dict(order.custom_attributes),
            **_created(uow),
        )
    )
    codes = sorted({line.booked_code for line in order.lines})  # the resolution, for product_id
    products = {
        str(code): UUID(str(value))
        for code, value in session.execute(
            select(product.c.code, product.c.id).where(product.c.code.in_(codes))
        )
    }
    lines = [
        {
            "tenant_id": tenant_id,
            "id": new_id(),
            "source_order_id": order_id,
            "line_external_id": line.line_external_id,
            "line_no": number,
            "product_code": line.product_code,  # the SOURCE code (T-SRC-03; Codex 0652 §1)
            "product_id": products.get(line.booked_code),  # its resolution at this time
            "quantity": line.quantity,
            "total_price": line.total_price,
            "start_date": line.start_date,
            "end_date": line.end_date,
            "selling_entity_code": order.legal_entity_code,
            "performing_entity_code": line.performing_entity_code or order.legal_entity_code,
            "account_codes": {},
            "effective_date": order.order_date,
            "custom_attributes": {},
            **_created(uow),
        }
        for number, line in enumerate(order.lines, start=1)
    ]
    if lines:
        session.execute(insert(source_order_line), lines)
    audit_writer.record_facts(uow, action=ORDER_ACTION, object_type="source_order", ids=[order_id])
    audit_writer.record_facts(
        uow,
        action=ORDER_LINE_ACTION,
        object_type="source_order_line",
        ids=[line["id"] for line in lines],
        detail={"source_order_id": str(order_id)},
    )
    return order_id


def booking_body(order: NormalisedOrder, keys: Collection[str] | None = None) -> ContractCreateIn:
    """The API-S-ContractCreate members of a contract of the order; ``keys`` restricts the booked
    lines to those line external ids (04 §16.14 rev 1.81: a partial booking from the MAPPED lines —
    the others stay candidate rows until their product is mapped and the record reprocessed)."""
    return _booking(order, keys)


def _booking(order: NormalisedOrder, keys: Collection[str] | None = None) -> ContractCreateIn:
    """The API-S-ContractCreate members of a new contract of the order."""
    currency = order.transaction_currency
    return ContractCreateIn.model_validate(
        {
            "external_id": order.order_number,
            "customer_id": str(order.customer_id),
            "contracting_entity_code": order.legal_entity_code,
            "transaction_currency": currency,
            "inception_date": order.order_date.isoformat(),
            "document_ref": order.document_ref,
            "acceptance_clause": order.acceptance_clause,
            "side_letter": order.side_letter,
            "custom_attributes": dict(order.custom_attributes) or None,
            "lines": [
                {
                    "obligation_key": line.line_external_id,
                    "product_code": line.booked_code,  # the booking sees the resolved product
                    "quantity": format(line.quantity, "f"),
                    "total_price": {"amount": format(line.total_price, "f"), "currency": currency},
                    "start_date": None if line.start_date is None else line.start_date.isoformat(),
                    "end_date": None if line.end_date is None else line.end_date.isoformat(),
                    "performing_entity_code": line.performing_entity_code,
                }
                for line in order.lines
                if keys is None or line.line_external_id in keys
            ],
        }
    )


def record_candidate(uow: UnitOfWork, order: NormalisedOrder) -> UUID:
    """The ``source_order`` rows of an order that is routed by its parent, not by its key (ADP-05:
    an amendment the sync run opens a DRAFT modification for, BUILD_SPEC DIN-12); nothing is
    appended to any contract. A stored identity is REUSED, never stored again (04 §16.14 rev 1.81;
    the three-class check ran in ``sync.ingest_draft`` before any write)."""
    existing = stored_order(
        uow.session,
        source_system=order.source_system,
        external_order_id=order.external_order_id,
        external_version=order.external_version,
    )
    if existing is not None:
        return existing.id
    fields = grouping_fields(uow.session, known_at=uow.now)
    return _store_order(uow, order, grouping_values(order, fields))


def ingest_order(
    uow: UnitOfWork,
    order: NormalisedOrder,
    *,
    sync_run_id: UUID | None = None,
    booked_lines: Collection[str] | None = None,
) -> Routed:
    """S02-R-13 for one normalised order (module docstring); ``sync_run_id`` names the T-INT-02 run
    on the booking event (05 ADP-03); ``booked_lines`` restricts the booking to those line external
    ids while every line is stored (04 §16.14 rev 1.81 partial booking); a stored order identity is
    reused, never stored again (Codex 0545 §2 R1)."""
    # Imported here: the contract commands reach ``ssp.resolution``, which imports
    # ``policies.registry_versions``, which imports this module for ``setting_errors``.
    from erev_api.domain.contracts.commands import book_contract

    session = uow.session
    fields = grouping_fields(session, known_at=uow.now)
    values = grouping_values(order, fields)
    key = grouping_key(values, fields)
    existing = matching_contract(session, key, fields)
    # 04 §16.14 rev 1.81 (Codex 0545 §2 R1): a stored identity (the first ingestion of an order
    # whose lines were all unmapped, now repaired) is reused — IM-A, never stored again.
    stored_identity = stored_order(
        session,
        source_system=order.source_system,
        external_order_id=order.external_order_id,
        external_version=order.external_version,
    )
    order_id = (
        stored_identity.id if stored_identity is not None else _store_order(uow, order, values)
    )
    if existing is not None:
        return Routed(GroupingOutcome.CANDIDATE_MODIFICATION, existing, key, order_id, None)
    identity = SourceIdentity(
        source_system=order.source_system,
        object_type=SourceObjectType.ORDER,
        external_id=order.external_order_id,
        external_version=order.external_version,
    )
    booked = book_contract(
        uow,
        body=_booking(order, booked_lines).booking(),
        origin="ADAPTER",
        source_system=order.source_system,
        idempotency_key=adapter_event_key(identity, 1),
        source_record_id=order.source_record_id,
        sync_run_id=sync_run_id,
    )
    contract_id = UUID(str(booked.contract["id"]))
    event_id = UUID(str(booked.event["id"]))
    link_id = new_id()
    session.execute(
        insert(contract_source_link).values(
            tenant_id=uow.principal.tenant_id,
            id=link_id,
            contract_id=contract_id,
            source_record_id=order.source_record_id,
            link_role=BOOKING,
            contract_event_id=event_id,
            **_created(uow),
        )
    )
    audit_writer.record_facts(
        uow,
        action=LINK_ACTION,
        object_type="contract_source_link",
        ids=[link_id],
        detail={"link_role": BOOKING},
        contract_id=contract_id,
    )
    return Routed(GroupingOutcome.NEW_CONTRACT, contract_id, key, order_id, event_id)
