"""Contract event streams KRN-EVT (dev-guide §5.11 DG-KRN-EVT-01; 04 T-CON-05 append protocol,
DB-08; 05 RCP-17, RCP-22; BUILD_SPEC CTR-1).

``append_events`` runs the T-CON-05 append protocol in the caller's unit of work:

1. An event whose ``idempotency_key`` is already stored for the contract is not appended again; the
   stored row answers it (``ux_contract_event__idempotency``; REQ-INT-001). When every event is such
   a replay nothing is written and the head is not compared.
2. ``UPDATE contract SET head_stream_version = head_stream_version + :n …
   WHERE head_stream_version = :expected`` must affect one row, otherwise 412
   ``precondition-failed`` with code ``EREV-EVT-001`` (404 ``not-found`` when the contract is not
   visible). The same statement applies the header projection of the events (T-CON-01;
   L3-1-Q-17), folded over the current status along PRD SM-02 (BUILD_SPEC CTR-7; L4-1-Q-10):
   ``CONTRACT_ACTIVATED`` sets ``ACTIVE`` from ``DRAFT`` or ``PENDING_REVIEW``;
   ``COLLECTIBILITY_ASSESSED`` with ``is_probable`` false sets ``NOT_A_CONTRACT`` from ``DRAFT``
   when the not-a-contract gate follows it in the same append (supervisor ruling R-20 (b): the
   events route appends the pair only when every enabled book is not probable);
   ``CONTRACT_CRITERIA_MET`` sets ``PENDING_REVIEW`` from ``NOT_A_CONTRACT``; ``CONTRACT_VOIDED``
   sets ``VOIDED`` and a ``FULL`` ``CONTRACT_TERMINATED`` of an ``ACTIVE`` contract
   ``TERMINATED``, each with its timestamp, so DB-18 sees the head rise with the change. Every
   status change writes ``contract.<status lowercase>`` (DG-SM-03).
3. The ``n`` events are inserted with ``stream_version = expected + 1 … expected + n``,
   ``payload_sha256`` over the canonical payload JSON and ``request_id`` from the context. The DB-08
   trigger assigns ``recorded_at`` and ``record_seq``.
4. ``combination_group.dirty_since = uow.now`` for the contract's group (RCP-17), then one AUD-FACT
   summary of the appended ids.

Obligation keys resolve to the contract's obligations. [J] L3-1-Q-16: a key without an obligation is
refused (422 ``validation-failed``, rule ``T-CON-10``) except for the event types that create
obligations (``CONTRACT_BOOKED``, ``CONTRACT_AMENDED``, ``MATERIAL_RIGHT_EXERCISED``,
``REGROUPED``). Such an event names a new id, and the command inserts the obligation with that id
after the event (``obligation.created_by_event_id``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from erev_engine.canonical import sha256_hex
from pydantic import BaseModel
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from erev_api.audit import writer as audit_writer
from erev_api.db import new_id
from erev_api.db.tables import combination_group, contract, contract_event, obligation
from erev_api.enums import ContractEventType, ContractStatus
from erev_api.events.payloads import (
    LATEST_SCHEMA_VERSION,
    PAYLOADS,
    CollectibilityAssessedV1,
    ContractActivatedV1,
    ContractBookedV1,
    ContractTerminatedV1,
    MemoUpdatedV1,
    payload_json,
)
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

type Origin = Literal["API", "UI", "IMPORT", "ADAPTER", "SYSTEM", "MIGRATION"]

EVT_CODE: Final = "EREV-EVT-001"
RULE_OBLIGATION: Final = "T-CON-10"
APPEND_ACTION: Final = "contract_event.append"
EVENT_OBJECT: Final = "contract_event"
CONTRACT_OBJECT: Final = "contract"
STALE_MESSAGE: Final = "The contract changed since it was read. Reload it and try again."
# E-03 types whose obligation keys may name obligations created with the event (L3-1-Q-16).
CREATING_TYPES: Final = frozenset(
    {
        ContractEventType.CONTRACT_BOOKED,
        ContractEventType.CONTRACT_AMENDED,
        ContractEventType.MATERIAL_RIGHT_EXERCISED,
        ContractEventType.REGROUPED,
    }
)


@dataclass(frozen=True, slots=True)
class EventIn:
    event_type: ContractEventType  # E-03
    effective_date: date
    payload: BaseModel  # a class from events.payloads.PAYLOADS
    obligation_keys: tuple[str, ...] = ()
    is_manual: bool = False
    supersedes_event_id: UUID | None = None
    modification_id: UUID | None = None
    estimate_version_id: UUID | None = None
    manual_adjustment_id: UUID | None = None
    approval_request_id: UUID | None = None
    idempotency_key: str | None = None
    import_upload_id: UUID | None = None
    source_record_id: UUID | None = None
    sync_run_id: UUID | None = None


def _check(events: Sequence[EventIn]) -> None:
    """Programming errors: a payload of another model, a void without a target, repeated keys."""
    for event in events:
        model = PAYLOADS[(event.event_type, LATEST_SCHEMA_VERSION[event.event_type])]
        if type(event.payload) is not model:
            raise TypeError(f"{event.event_type.value} needs a {model.__name__} payload")
        voids = event.event_type is ContractEventType.EVENT_VOIDED
        if voids != (event.supersedes_event_id is not None):
            raise ValueError("supersedes_event_id names the target of EVENT_VOIDED and only that")
    keys = [event.idempotency_key for event in events if event.idempotency_key is not None]
    if len(set(keys)) != len(keys):
        raise ValueError("idempotency keys repeat within one append")


def _stored(session: Session, contract_id: UUID, keys: Sequence[str]) -> dict[str, dict[str, Any]]:
    if not keys:
        return {}
    statement = select(contract_event).where(
        contract_event.c.contract_id == contract_id, contract_event.c.idempotency_key.in_(keys)
    )
    return {str(row["idempotency_key"]): dict(row) for row in session.execute(statement).mappings()}


def _obligation_ids(
    session: Session, contract_id: UUID, pending: Sequence[tuple[int, EventIn]]
) -> list[list[UUID]]:
    statement = select(obligation.c.obligation_key, obligation.c.id).where(
        obligation.c.contract_id == contract_id
    )
    known = {str(key): UUID(str(value)) for key, value in session.execute(statement)}
    errors: list[ProblemError] = []
    resolved: list[list[UUID]] = []
    for index, event in pending:
        ids: list[UUID] = []
        for key in event.obligation_keys:
            found = known.get(key)
            if found is None and event.event_type in CREATING_TYPES:
                found = known[key] = new_id()
            if found is None:
                errors.append(
                    ProblemError(
                        field=f"events.{index}.obligation_keys",
                        rule_id=RULE_OBLIGATION,
                        message=f"The contract has no obligation {key}.",
                    )
                )
                continue
            ids.append(found)
        resolved.append(ids)
    if errors:
        raise Problem("validation-failed", errors=errors)
    return resolved


def booking_projection(payload: ContractBookedV1) -> dict[str, Any]:
    """The T-CON-01 header members a booking establishes (API-S-ContractCreate). A replacement
    booking (replace-draft, L3-1-Q-42) keeps the external id, contracting entity and currency."""
    termination = payload.termination
    return {
        "customer_id": payload.customer_id,
        "inception_date": payload.inception_date,
        "signature_date": payload.signature_date,
        "document_ref": payload.document_ref,
        "payment_terms": payload.payment_terms,
        "termination_party": None if termination is None else termination.party,
        "termination_has_penalty": None if termination is None else termination.has_penalty,
        "termination_notice_days": None if termination is None else termination.notice_days,
        "acceptance_clause": payload.acceptance_clause,
        "side_letter": payload.side_letter,
        "has_commercial_substance": payload.has_commercial_substance,
        "region": payload.region,
        "channel": payload.channel,
        "contract_type": payload.contract_type,
        "memo_1": payload.memo_1,
        "memo_2": payload.memo_2,
        "memo_3": payload.memo_3,
        "custom_attributes": dict(payload.custom_attributes or {}),
        "renewal_of_contract_id": payload.renewal_of_contract_id,
        "scope_605_35": payload.scope_605_35,
    }


def _next_status(event: EventIn, status: str, following: EventIn | None = None) -> str:
    """PRD SM-02 of one event from ``status`` (CTR-7; L4-1-Q-10). ``following`` is the next event
    of the same append: a not-probable assessment moves a DRAFT header to NOT_A_CONTRACT only as
    the pair the events route appends — the assessment with the not-a-contract gate right behind
    it (supervisor ruling R-20 (b); 04 T-CON-01 rev 1.105). Alone, the assessment is recorded and
    the contract stays DRAFT: the engine has not left DRAFT in any book either."""
    match event.event_type:
        case ContractEventType.CONTRACT_ACTIVATED if status in (
            ContractStatus.DRAFT.value,
            ContractStatus.PENDING_REVIEW.value,
        ):
            return ContractStatus.ACTIVE.value
        case ContractEventType.COLLECTIBILITY_ASSESSED if status == ContractStatus.DRAFT.value:
            payload = event.payload
            gated = (
                following is not None
                and following.event_type is ContractEventType.CONTRACT_ACTIVATED
            )
            if isinstance(payload, CollectibilityAssessedV1) and not payload.is_probable and gated:
                return ContractStatus.NOT_A_CONTRACT.value
        case ContractEventType.CONTRACT_CRITERIA_MET if (
            status == ContractStatus.NOT_A_CONTRACT.value
        ):
            return ContractStatus.PENDING_REVIEW.value
        case ContractEventType.CONTRACT_VOIDED if status != ContractStatus.VOIDED.value:
            return ContractStatus.VOIDED.value
        case ContractEventType.CONTRACT_TERMINATED if status == ContractStatus.ACTIVE.value:
            payload = event.payload
            if isinstance(payload, ContractTerminatedV1) and payload.termination_kind == "FULL":
                return ContractStatus.TERMINATED.value
        case _:
            pass
    return status


_MEMO_HEADER: Final = frozenset({"memo_1", "memo_2", "memo_3", "custom_attributes"})


def memo_header_values(payload: MemoUpdatedV1) -> dict[str, Any]:
    """The T-CON-01 header members a header-scope ``MEMO_UPDATED`` sets at append time — the
    three memos and ``custom_attributes`` — read from the presence set ``named`` alone when it is
    present (ENGINE_SPEC CV-47 (a); 04 §16.3: a supplied null clears a memo / empties the attribute
    set; the engine's replay reads the same set), whether the model is the live request or an
    approval submission's stored body re-parsed on approval; a payload without ``named`` (stored
    before the presence set existed) keeps the earlier ``model_fields_set`` reading — no presence is
    invented for it. Stored rows are never re-projected from old events."""
    members: set[str]
    if payload.named is not None:
        # Every header member from the presence set alone: a stored approval body writes the
        # omitted members as null and is re-parsed on approval, so its ``model_fields_set`` proves
        # nothing (Codex 1510 (b)); ``dimensions`` is not a header member.
        members = {str(name) for name in payload.named if name in _MEMO_HEADER}
    else:
        members = set(payload.model_fields_set & _MEMO_HEADER)
    values: dict[str, Any] = {}
    for name in sorted(members):
        value = getattr(payload, name)
        values[name] = dict(value or {}) if name == "custom_attributes" else value
    return values


_STATUS_STAMPS: Final = {
    ContractStatus.ACTIVE.value: "activated_at",
    ContractStatus.VOIDED.value: "voided_at",
    ContractStatus.TERMINATED.value: "terminated_at",
}


def header_projection(
    uow: UnitOfWork, events: Sequence[EventIn], *, current_status: str
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """The T-CON-01 header columns the events establish (L3-1-Q-17) and the status changes, in
    order: a booking that names its customer projects its header members (L3-1-Q-42), and the
    status follows PRD SM-02 from ``current_status``."""
    values: dict[str, Any] = {}
    changes: list[tuple[str, str]] = []
    status = current_status
    for index, event in enumerate(events):
        payload = event.payload
        if (
            event.event_type is ContractEventType.CONTRACT_BOOKED
            and isinstance(payload, ContractBookedV1)
            and payload.customer_id is not None
        ):
            values |= booking_projection(payload)
        if (
            event.event_type is ContractEventType.MEMO_UPDATED
            and isinstance(payload, MemoUpdatedV1)
            and payload.obligation_key is None
        ):
            # T-CON-01 memos and custom attributes; the members sent replace (BUILD_SPEC CTR-10).
            values |= memo_header_values(payload)
        following = _next_status(
            event, status, events[index + 1] if index + 1 < len(events) else None
        )
        if following != status:
            changes.append((status, following))
            values["status"] = following
            stamp = _STATUS_STAMPS.get(following)
            if stamp is not None:
                values[stamp] = uow.now
            if following == ContractStatus.ACTIVE.value and isinstance(
                payload, ContractActivatedV1
            ):
                # T-CON-01 ``activation_checklist`` (REQ-CON-005; BUILD_SPEC CTR-9).
                values["activation_checklist"] = {
                    "items": [item.model_dump(mode="json") for item in payload.checklist],
                    "evaluated_at": uow.now.isoformat(),
                }
            status = following
    return values, changes


def _current_status(uow: UnitOfWork, contract_id: UUID) -> str | None:
    found = uow.session.execute(
        select(contract.c.status).where(contract.c.id == contract_id)
    ).scalar_one_or_none()
    return None if found is None else str(getattr(found, "value", found))


def _raise_head(
    uow: UnitOfWork, contract_id: UUID, expected: int, pending: Sequence[EventIn]
) -> tuple[UUID, UUID]:
    principal = uow.principal
    current = _current_status(uow, contract_id)
    projected, changes = header_projection(
        uow, pending, current_status=current or ContractStatus.DRAFT.value
    )
    statement = (
        update(contract)
        .where(
            contract.c.tenant_id == principal.tenant_id,
            contract.c.id == contract_id,
            contract.c.head_stream_version == expected,
        )
        .values(
            head_stream_version=contract.c.head_stream_version + len(pending),
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
            row_version=contract.c.row_version + 1,
            **projected,
        )
        .returning(contract.c.contracting_entity_id, contract.c.combination_group_id)
    )
    row = uow.session.execute(statement).one_or_none()
    if row is None:
        if current is None:
            raise Problem("not-found")
        raise Problem(
            "precondition-failed",
            STALE_MESSAGE,
            code=EVT_CODE,
            errors=[ProblemError(field="If-Match", rule_id=EVT_CODE, message=STALE_MESSAGE)],
        )
    for before, after in changes:
        audit_writer.record(
            uow,
            action=f"{CONTRACT_OBJECT}.{after.lower()}",
            object_type=CONTRACT_OBJECT,
            object_id=contract_id,
            object_version=str(expected + len(pending)),
            before={"status": before},
            after={"status": after},
            contract_id=contract_id,
        )
    return UUID(str(row.contracting_entity_id)), UUID(str(row.combination_group_id))


def _mark_dirty(uow: UnitOfWork, group_id: UUID) -> None:
    principal = uow.principal
    uow.session.execute(
        update(combination_group)
        .where(
            combination_group.c.tenant_id == principal.tenant_id,
            combination_group.c.id == group_id,
        )
        .values(
            # 05 RCP-17 rev 1.207 (item COMPUTE-BEHIND-GROUP-1): a mark is never moved back
            dirty_since=func.greatest(combination_group.c.dirty_since, uow.now),
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
            row_version=combination_group.c.row_version + 1,
        )
    )


def _sources(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The import or the sync run the appended events came from, as members of the append's audit
    fact (04 T-PLT-19, rev 1.154): the commit of an import and the run of a sync touch many
    contracts and their own events name none, so a contract's trail names them through its
    appends. One append comes from one source; a member is absent when no row names one."""
    found: dict[str, Any] = {}
    for member in ("import_upload_id", "sync_run_id"):
        named = sorted({str(row[member]) for row in rows if row[member] is not None})
        if len(named) == 1:
            found[member] = named[0]
        elif named:
            found[f"{member}s"] = named
    return found


def append_events(
    uow: UnitOfWork,
    *,
    contract_id: UUID,
    expected_stream_version: int,
    events: Sequence[EventIn],
    origin: Literal["API", "UI", "IMPORT", "ADAPTER", "SYSTEM", "MIGRATION"],
) -> list[Mapping[str, Any]]:
    """Append ``events`` after ``expected_stream_version``; returns the rows in input order."""
    if not events:
        raise ValueError("append_events needs at least one event")
    if expected_stream_version < 0:
        raise ValueError("expected_stream_version is at least 0")
    _check(events)
    session = uow.session
    keys = [event.idempotency_key for event in events if event.idempotency_key is not None]
    stored = _stored(session, contract_id, keys)
    pending = [
        (index, event)
        for index, event in enumerate(events)
        if event.idempotency_key is None or event.idempotency_key not in stored
    ]
    if not pending:
        return [stored[str(event.idempotency_key)] for event in events]

    obligation_ids = _obligation_ids(session, contract_id, pending)
    entity_id, group_id = _raise_head(
        uow, contract_id, expected_stream_version, [event for _, event in pending]
    )
    principal = uow.principal
    inserted: dict[int, dict[str, Any]] = {}
    for offset, ((index, event), ids) in enumerate(zip(pending, obligation_ids, strict=True), 1):
        body = payload_json(event.payload)
        statement = (
            insert(contract_event)
            .values(
                tenant_id=principal.tenant_id,
                id=new_id(),
                contract_id=contract_id,
                contracting_entity_id=entity_id,
                stream_version=expected_stream_version + offset,
                event_type=event.event_type.value,
                schema_version=LATEST_SCHEMA_VERSION[event.event_type],
                effective_date=event.effective_date,
                origin=origin,
                is_manual=event.is_manual,
                obligation_ids=ids,
                payload=body,
                payload_sha256=sha256_hex(body),
                idempotency_key=event.idempotency_key,
                supersedes_event_id=event.supersedes_event_id,
                approval_request_id=event.approval_request_id,
                modification_id=event.modification_id,
                estimate_version_id=event.estimate_version_id,
                manual_adjustment_id=event.manual_adjustment_id,
                import_upload_id=event.import_upload_id,
                source_record_id=event.source_record_id,
                sync_run_id=event.sync_run_id,
                request_id=uow.ctx.request_id,
                created_at=uow.now,
                created_by=principal.id,
                created_by_kind=principal.kind.value,
            )
            .returning(*contract_event.c)
        )
        inserted[index] = dict(session.execute(statement).mappings().one())

    _mark_dirty(uow, group_id)
    rows = list(inserted.values())
    audit_writer.record_facts(
        uow,
        action=APPEND_ACTION,
        object_type=EVENT_OBJECT,
        ids=[row["id"] for row in rows],
        detail={
            "origin": origin,
            "stream_versions": [row["stream_version"] for row in rows],
            "event_types": [str(row["event_type"]) for row in rows],
            **_sources(rows),
        },
        contract_id=contract_id,
    )
    return [
        inserted[index] if index in inserted else stored[str(event.idempotency_key)]
        for index, event in enumerate(events)
    ]
