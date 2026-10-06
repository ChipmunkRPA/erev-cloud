"""Field locks, memo edits and attribute changes (04 §15.2 ``field-locked-after-activation``,
§16.1 ``update-memos``, §16.3 ``LINE_ATTRIBUTES_CHANGED``, ``MEMO_UPDATED``, API-S-EventAppend; PRD
BR-CON-02, ERR-11, §2.5 routing row ``ATTRIBUTE_CHANGE``; 03 REQ-CON-007, REQ-CON-008,
REQ-MOD-021; BUILD_SPEC CTR-10; control CTL-006).

- ``refuse_locked_fields``: while the contract is ACTIVE, COMPLETED or TERMINATED, a
  ``LINE_ATTRIBUTES_CHANGED`` whose ``changes`` name a stated price, quantity, date or product is
  refused with 409 ``field-locked-after-activation`` (one error per member, ERR-11 copy), and the
  refusal is audited with outcome ``DENIED`` in a transaction of its own.
- [J] L4-1-Q-23: accounts and the performing entity change only through an approved
  ``ATTRIBUTE_CHANGE`` submission (``events.record_events``); approval checks the stored events
  again, appends them as SYSTEM on behalf of the preparer and computes the group (the
  event-submission lifecycle of ``events``, shared with ``MANUAL_EVENT``).
- ``refuse_version_pin`` (04 §16.3 rev 1.231; 03 REQ-SSP-006; item ATTR-SSP-PIN-1): the SSP
  version of an obligation is not this route's to change. Until rev 1.231 the judgement above
  routed it with the accounts and the entity — one step, ``event.approve``, no preview — and the
  approval pinned the obligation, listed in RPT-22 as an approved override. It belongs to the SSP
  override command (``policies.overrides``; ``ssp.approve``), whose approval appends the event
  below the route.
- ``update_memos``: ``MEMO_UPDATED`` with a mandatory comment, audited field by field;
  contract-level members project into the header (T-CON-01), and the group is computed, so posted
  amounts stay as they were (REQ-CON-008).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final
from uuid import UUID

from erev_api.audit import writer as audit_writer
from erev_api.auth.dependencies import require_for_entity
from erev_api.db import transitions
from erev_api.domain.contracts import holds, queries, repo
from erev_api.enums import ContractEventType, ContractStatus, PrincipalKind
from erev_api.events import payloads as payloads_module
from erev_api.events.payloads import MemoUpdatedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.contracts import ContractOut
from erev_api.schemas.events import EventAppendItemIn, MemosUpdateIn
from erev_api.uow import UnitOfWork

__all__ = [
    "ATTRIBUTE_TYPES",
    "LOCKED_MEMBERS",
    "VERSION_PIN_DETAIL",
    "VERSION_PIN_MEMBERS",
    "locked_fields",
    "names_version_pin",
    "refuse_locked_fields",
    "refuse_version_pin",
    "update_memos",
    "version_pin_errors",
]

LOCKED_STATUSES: Final = frozenset(
    {ContractStatus.ACTIVE.value, ContractStatus.COMPLETED.value, ContractStatus.TERMINATED.value}
)
# PRD BR-CON-02: stated prices, quantities and dates (and the product of a line) are read-only.
LOCKED_MEMBERS: Final[Mapping[str, str]] = {
    "product_code": "Product",
    "quantity": "Quantity",
    "unit_price": "Unit price",
    "total_price": "Total price",
    "start_date": "Start date",
    "end_date": "End date",
}
LOCKED_DETAIL: Final = (  # PRD ERR-11
    "{label} of an active contract changes only through a modification or price change."
)
RULE_LOCK: Final = "REQ-CON-007"
DENIED_ACTION: Final = "contract.record_events"
ATTRIBUTE_TYPES: Final = frozenset({ContractEventType.LINE_ATTRIBUTES_CHANGED})
# 04 §16.3 ``LINE_ATTRIBUTES_CHANGED`` (rev 1.231): the members of ``changes`` that name an SSP
# version. The SSP override command alone sets one (03 REQ-SSP-006).
VERSION_PIN_MEMBERS: Final[tuple[str, ...]] = ("ssp_book_version_id", "ssp_version_label")
RULE_VERSION_PIN: Final = "REQ-SSP-006"
VERSION_PIN_DETAIL: Final = (
    "Change the SSP version of an obligation with an SSP override request, which an SSP approver "
    "decides."
)
MEMO_MEMBERS: Final = payloads_module.MEMO_UPDATED_MEMBERS  # one member set (CV-47 (a))
HEADER_MEMBERS: Final = frozenset({"memo_1", "memo_2", "memo_3", "custom_attributes"})
MEMOS_ACTION: Final = "contract.update_memos"
RULE_MEMOS: Final = "REQ-CON-008"
NO_MEMBERS: Final = "Send a memo, custom attributes or dimensions."
NOT_EDITABLE: Final = "A voided contract takes no memo edit."
# PRD ERR-07.
STALE_CONTRACT: Final = (
    "This record changed since you opened it. Reload to see the latest version, then try again."
)


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def locked_fields(status: str, items: Sequence[EventAppendItemIn]) -> list[str]:
    """The locked members an append would change (BR-CON-02), in first-seen order."""
    if status not in LOCKED_STATUSES:
        return []
    fields: list[str] = []
    for item in items:
        if item.event_type not in ATTRIBUTE_TYPES:
            continue
        changes = item.payload.get("changes")
        names = list(changes) if isinstance(changes, Mapping) else []
        fields += [name for name in names if name in LOCKED_MEMBERS and name not in fields]
    return fields


def refuse_locked_fields(
    uow: UnitOfWork,
    current: Mapping[str, Any],
    items: Sequence[EventAppendItemIn],
    *,
    permission: str,
) -> None:
    """409 ``field-locked-after-activation`` with a ``DENIED`` audit event (REQ-CON-007)."""
    status = _text(current["status"])
    fields = locked_fields(status, items)
    if not fields:
        return
    audit_writer.record_denied(
        uow.ctx,
        action=DENIED_ACTION,
        object_type="contract",
        object_id=_uuid(current["id"]),
        permission=permission,
        detail={"rule_id": RULE_LOCK, "fields": fields, "status": status},
        keyring=uow.keyring,
        contract_id=_uuid(current["id"]),
    )
    raise Problem(
        "field-locked-after-activation",
        LOCKED_DETAIL.format(label=LOCKED_MEMBERS[fields[0]]),
        errors=[
            ProblemError(
                field=name,
                rule_id=RULE_LOCK,
                message=LOCKED_DETAIL.format(label=LOCKED_MEMBERS[name]),
            )
            for name in fields
        ],
    )


def version_pin_errors(items: Sequence[EventAppendItemIn]) -> list[ProblemError]:
    """One error per ``changes`` member that names an SSP version, in request order."""
    errors: list[ProblemError] = []
    for index, item in enumerate(items):
        if item.event_type not in ATTRIBUTE_TYPES:
            continue
        changes = item.payload.get("changes")
        if not isinstance(changes, Mapping):
            continue
        errors += [
            ProblemError(
                field=f"events.{index}.payload.changes.{name}",
                rule_id=RULE_VERSION_PIN,
                message=VERSION_PIN_DETAIL,
            )
            for name in VERSION_PIN_MEMBERS
            if changes.get(name) is not None
        ]
    return errors


def refuse_version_pin(items: Sequence[EventAppendItemIn]) -> None:
    """422 ``validation-failed`` for an attribute change that names an SSP version, whoever
    sends it and whatever the contract's status: before anything is stored or routed."""
    errors = version_pin_errors(items)
    if errors:
        detail = errors[0].message if len(errors) == 1 else f"{len(errors)} fields need attention."
        raise Problem("validation-failed", detail, errors=errors)


def names_version_pin(events: Sequence[EventIn]) -> bool:
    """Whether a stored batch holds an attribute change that names an SSP version — what
    ``events.check_stored`` reads where a submission is appended (04 T-CON-24)."""
    for event in events:
        if event.event_type not in ATTRIBUTE_TYPES:
            continue
        changes = getattr(event.payload, "changes", None)
        if any(getattr(changes, name, None) is not None for name in VERSION_PIN_MEMBERS):
            return True
    return False


def update_memos(
    uow: UnitOfWork,
    *,
    contract_id: UUID,
    expected_stream_version: int | None,
    body: MemosUpdateIn,
) -> ContractOut:
    """``POST /contracts/{id}/update-memos`` (04 §16.1; REQ-CON-008)."""
    session = uow.session
    _, current = repo.lock_group_then_contract(session, contract_id)  # DG-KRN-DB-08 rev 1.36
    require_for_entity(uow.ctx, holds.MANAGE_PERMISSION, current["contracting_entity_id"])
    head = int(current["head_stream_version"])
    if expected_stream_version != head:
        raise Problem("precondition-failed", STALE_CONTRACT)
    if _text(current["status"]) == ContractStatus.VOIDED.value:
        raise Problem(
            "invalid-transition",
            NOT_EDITABLE,
            errors=[
                ProblemError(field="status", rule_id=transitions.RULE_ID, message=NOT_EDITABLE)
            ],
        )
    members = [name for name in MEMO_MEMBERS if name in body.model_fields_set]
    if not members:
        raise Problem(
            "validation-failed",
            NO_MEMBERS,
            errors=[ProblemError(field="memo_1", rule_id=RULE_MEMOS, message=NO_MEMBERS)],
        )
    key = body.obligation_key
    if key is not None and key not in {
        str(row["obligation_key"]) for row in repo.obligations(session, contract_id)
    }:
        message = holds.OBLIGATION_UNKNOWN.format(key=key)
        raise Problem(
            "validation-failed",
            message,
            errors=[ProblemError(field="obligation_key", rule_id="T-CON-10", message=message)],
        )
    changes = {name: getattr(body, name) for name in members}
    # CV-47 (a): the presence set — the supplied members, a supplied None clearing the memo.
    payload = MemoUpdatedV1(obligation_key=key, named=tuple(members), **changes)
    append_events(
        uow,
        contract_id=contract_id,
        expected_stream_version=head,
        events=[
            EventIn(
                event_type=ContractEventType.MEMO_UPDATED,
                effective_date=holds.entity_date(session, current, uow.now),
                payload=payload,
                obligation_keys=() if key is None else (key,),
                is_manual=uow.principal.kind is PrincipalKind.USER,
            )
        ],
        origin="API" if uow.principal.kind is PrincipalKind.API_CLIENT else "UI",
    )
    header = key is None
    uow.audit(
        action=MEMOS_ACTION,
        object_type="contract",
        object_id=contract_id,
        object_version=str(head + 1),
        before={
            name: current[name] if header and name in HEADER_MEMBERS else None for name in members
        },
        after=changes,
        comment=body.comment,
        detail={"obligation_key": key},
        contract_id=contract_id,
    )
    holds.compute(uow, current)
    return queries.contract_out(session, contract_id, now=uow.now)


# --- ATTRIBUTE_CHANGE (PRD §2.5; 04 T-CON-24; REQ-MOD-021) ----------------------------------------
# The lifecycle of an attribute-change request is the event submission's, registered for both
# subjects in ``erev_api.domain.contracts.events`` (BUILD_SPEC CTR-6; dev-guide DG-KRN-EVT-02 rev
# 1.177): the stored batch is checked again where it is appended, then the group is computed.
