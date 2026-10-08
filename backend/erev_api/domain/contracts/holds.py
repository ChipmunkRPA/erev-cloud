"""Recognition and journal-export holds (04 T-CON-20, §3.4 E-45, E-46, E-55, T-REF-26 ``HOLD``
outputs, §16.1 ``apply-hold`` and ``release-hold``, §16.3 ``HOLD_APPLIED``, ``HOLD_RELEASED``; PRD
SMAP-15, BR-PLT-08; ENGINE_SPEC_B §9.2.12 S09-R-42 to S09-R-44; 03 REQ-POL-010, REQ-REC-022;
BUILD_SPEC CTR-10).

A hold is appended as ``HOLD_APPLIED`` and projected into ``contract_hold`` in the same unit of
work; ``HOLD_RELEASED`` sets ``released_event_id`` and ``released_at``. [J] L4-1-Q-22: the row id
equals the id of its ``HOLD_APPLIED`` event, so ``HOLD_RELEASED.hold_id`` resolves to the event key
the engine reads (``bundles``; S09-R-42). A hold is effective on the contracting entity's current
date, and a contract-level hold (no ``obligation_key``) covers every obligation.

- ``apply_hold`` and ``release_hold``: MANUAL holds of a person or API client holding
  ``contract.create`` for the entity (API-R-28), with ``If-Match`` and a reason or comment of at
  least 10 characters (BR-PLT-08); the group is computed (fact capture, DG-CMD-09).
- ``apply_system_hold`` and ``release_system_holds``: SYSTEM recognition holds (REQ-POL-010); a
  submitted judgement record of an ACTIVE contract applies one and its review releases it.
- ``apply_rule_holds``: the PUBLISHED ``HOLD`` rule set rules matched per obligation on booking,
  as USER_RULE holds naming the rule set version and the rule (E-55; T-REF-26 outputs
  ``{hold_type, level}``).

The hold of a judgement record (04 T-CON-20 "Judgement holds", rev 1.209; item
STEP1-HOLD-RELEASE-1, the supervisor's ruling of 2026-10-01 on the lane's pre-build line). T-CON-20
has no column that names the record: the hold is FOUND BY ITS REASON TEXT. ``judgement_hold_reason``
is the one writer of that sentence and the one reader — the submission that places the hold, the
review, the supersession and the Step 1 assessment that release it, and ``release_hold``, which
asks whether a SYSTEM hold is a record's, all call it — so a reworded sentence finds nothing that
was placed under the earlier one; the wording changes only with a revision that also re-reads the
stored holds. One hold with one reason that is true for as long as the hold stands:

- every topic but ``NOT_A_CONTRACT``: placed at the submission that waits for a person, released
  by the review. A rejected, a withdrawn or a stale-voided review leaves it (the record is still
  not reviewed); then it is released by hand, or by the review of the revised record;
- ``NOT_A_CONTRACT``: placed at the submission whatever the routing, and NOT released by the
  review — between the review and the assessment the book would recognise revenue under a
  reviewed "not a contract". It is released in the unit of work that appends the first
  not-probable ``COLLECTIBILITY_ASSESSED`` citing the record (``events.record_events``), when
  the record is superseded, or when a ``COLLECTIBILITY`` record of the same subject and book is
  reviewed after it — a second person has since concluded the opposite, and a record that is
  never assessed with would otherwise hold the contract for good;
- ``release_hold`` refuses such a hold while its record is SUBMITTED — the preparer does not
  release alone the hold her own unreviewed record placed — and, for a ``NOT_A_CONTRACT``
  record, while it is REVIEWED.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final, Literal
from uuid import UUID

from erev_engine.rules import match
from sqlalchemy import and_, insert, or_, select, update
from sqlalchemy.orm import Session

from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import system_principal
from erev_api.clock import to_entity_date
from erev_api.db import transitions
from erev_api.db.tables import (
    contract,
    contract_event,
    contract_hold,
    judgement_record,
    legal_entity,
    product,
    rule,
    rule_set,
    rule_set_version,
)
from erev_api.domain.contracts import queries, repo
from erev_api.domain.contracts.compute_job import (
    ENGINE_BUDGET_SECONDS,
    OBLIGATION_BUDGET,
    compute_group,
    defer_compute,
    obligation_count,
)
from erev_api.enums import (
    ConfigStatus,
    ContractEventType,
    ContractStatus,
    HoldSource,
    HoldType,
    JudgementStatus,
    JudgementTopic,
    PrincipalKind,
    RuleSetKind,
)
from erev_api.events.payloads import HoldAppliedV1, HoldReleasedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.contracts import ContractOut
from erev_api.schemas.events import HoldApplyIn, HoldReleaseIn
from erev_api.uow import UnitOfWork

__all__ = [
    "JUDGEMENT_HOLD_REASON",
    "JUDGEMENT_RELEASE_COMMENT",
    "OVERTAKEN_RELEASE_COMMENT",
    "RELEASED_BY_ASSESSMENT",
    "RELEASED_BY_REVIEW",
    "STEP1_HOLD_REASON",
    "STEP1_RELEASE_COMMENT",
    "SUPERSEDED_RELEASE_COMMENT",
    "apply_hold",
    "apply_rule_holds",
    "apply_system_hold",
    "compute",
    "entity_date",
    "judgement_hold_reason",
    "listed_holds",
    "open_holds",
    "pending_system_releases",
    "release_hold",
    "release_refusal",
    "release_system_holds",
]

MANAGE_PERMISSION: Final = "contract.create"  # 04 API-R-28 command permission
OBJECT_TYPE: Final = "contract_hold"
APPLY_ACTION: Final = "contract_hold.apply"
RELEASE_ACTION: Final = "contract_hold.release"
RULE_OBLIGATION: Final = "T-CON-10"
HOLDABLE: Final = frozenset(
    {
        ContractStatus.DRAFT.value,
        ContractStatus.PENDING_REVIEW.value,
        ContractStatus.NOT_A_CONTRACT.value,
        ContractStatus.ACTIVE.value,
        ContractStatus.COMPLETED.value,
    }
)
# PRD ERR-07.
STALE_CONTRACT: Final = (
    "This record changed since you opened it. Reload to see the latest version, then try again."
)
NOT_HOLDABLE: Final = "A voided or terminated contract takes no hold."
HOLD_UNKNOWN: Final = "The contract has no hold with this id."
ALREADY_RELEASED: Final = "This hold is already released."
OBLIGATION_UNKNOWN: Final = "The contract has no obligation {key}."
# The reason of a judgement record's hold (module docstring): true before the review and after
# a review that was rejected, withdrawn or voided as stale — "awaits review" (before rev 1.209)
# was not. No seed and no fixture stores the earlier sentence, so one form is written and read.
JUDGEMENT_HOLD_REASON: Final = "Judgement record {judgement_no} ({topic}) is not reviewed."
# A NOT_A_CONTRACT record holds until its assessment is recorded: one reason, true in both phases.
STEP1_HOLD_TOPIC: Final = JudgementTopic.NOT_A_CONTRACT.value
STEP1_HOLD_REASON: Final = (
    "Judgement record {judgement_no} (NOT_A_CONTRACT) is not reviewed, or the Step 1 assessment "
    "that cites it is not recorded."
)
JUDGEMENT_RELEASE_COMMENT: Final = "Judgement record {judgement_no} was reviewed."
STEP1_RELEASE_COMMENT: Final = (
    "The Step 1 assessment that cites judgement record {judgement_no} was recorded."
)
SUPERSEDED_RELEASE_COMMENT: Final = (
    "Judgement record {judgement_no} was superseded by judgement record {superseded_by}."
)
OVERTAKEN_RELEASE_COMMENT: Final = (
    "Judgement record {judgement_no} was overtaken by the review of judgement record "
    "{overtaken_by}."
)
# ``release_hold`` of a judgement record's hold (409 ``invalid-transition``).
RELEASED_BY_REVIEW: Final = (
    "This hold is released by the review of judgement record {judgement_no}."
)
RELEASED_BY_ASSESSMENT: Final = (
    "This hold is released when the Step 1 assessment that cites judgement record "
    "{judgement_no} is recorded."
)
RULE_HOLD_REASON: Final = "Hold rule {rule_key} of rule set {rule_set_code}."
CONTRACT_LEVEL: Final = "contract"
OBLIGATION_LEVEL: Final = "obligation"  # API-S-Contract / API-S-Obligation ``holds[].level``

type Origin = Literal["API", "UI", "IMPORT", "ADAPTER", "SYSTEM", "MIGRATION"]


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _origin(uow: UnitOfWork) -> Origin:
    return "API" if uow.principal.kind is PrincipalKind.API_CLIENT else "UI"


def _refuse(message: str) -> Problem:
    return Problem(
        "invalid-transition",
        message,
        errors=[ProblemError(field="status", rule_id=transitions.RULE_ID, message=message)],
    )


def judgement_hold_reason(judgement_no: Any, topic: Any) -> str:
    """The reason of the REQ-POL-010 hold of a judgement record — the sentence the hold is
    stored with and FOUND by (module docstring): every writer and every reader calls this."""
    if _text(topic) == STEP1_HOLD_TOPIC:
        return STEP1_HOLD_REASON.format(judgement_no=judgement_no)
    return JUDGEMENT_HOLD_REASON.format(judgement_no=judgement_no, topic=_text(topic))


def entity_date(session: Session, contract_row: Mapping[str, Any], now: Any) -> date:
    """The contracting entity's current date (05 TZ-03)."""
    zone = session.execute(
        select(legal_entity.c.time_zone).where(
            legal_entity.c.id == contract_row["contracting_entity_id"]
        )
    ).scalar_one()
    return to_entity_date(now, str(zone))


def compute(uow: UnitOfWork, contract_row: Mapping[str, Any]) -> None:
    """Unit of work B of a fact-capture command: compute the group, or defer ``CONTRACT_COMPUTE``
    beyond the budget (DG-CMD-09; RCP-18)."""
    session = uow.session
    group_id = _uuid(contract_row["combination_group_id"])
    outcome = None
    if obligation_count(session, group_id) <= OBLIGATION_BUDGET:
        outcome = compute_group(uow, group_id, budget_seconds=ENGINE_BUDGET_SECONDS)
    if outcome is None or outcome.deferred:
        defer_compute(uow, group_id, contract_id=_uuid(contract_row["id"]))


def open_holds(
    session: Session,
    contract_id: UUID,
    *,
    source: HoldSource | None = None,
    reason: str | None = None,
    lock: bool = True,
) -> list[dict[str, Any]]:
    """The contract's open holds, oldest first; ``FOR UPDATE`` unless a reader that writes
    nothing asks without the lock (the preview of an append)."""
    statement = select(contract_hold).where(
        contract_hold.c.contract_id == contract_id, contract_hold.c.released_at.is_(None)
    )
    if source is not None:
        statement = statement.where(contract_hold.c.hold_source == source.value)
    if reason is not None:
        statement = statement.where(contract_hold.c.reason == reason)
    statement = statement.order_by(contract_hold.c.applied_at, contract_hold.c.id)
    if lock:
        statement = statement.with_for_update()
    return [dict(row) for row in session.execute(statement).mappings()]


def _locked(uow: UnitOfWork, contract_id: UUID, expected: int | None) -> dict[str, Any]:
    # DG-KRN-DB-08 rev 1.36 (D-98 101b): group row first — the hold events mark the group dirty.
    _, current = repo.lock_group_then_contract(uow.session, contract_id)
    require_for_entity(uow.ctx, MANAGE_PERMISSION, current["contracting_entity_id"])
    if expected != int(current["head_stream_version"]):
        raise Problem("precondition-failed", STALE_CONTRACT)
    if _text(current["status"]) not in HOLDABLE:
        raise _refuse(NOT_HOLDABLE)
    return current


def _obligation_id(session: Session, contract_id: UUID, key: str) -> UUID:
    found = next(
        (
            row
            for row in repo.obligations(session, contract_id)
            if str(row["obligation_key"]) == key
        ),
        None,
    )
    if found is None:
        message = OBLIGATION_UNKNOWN.format(key=key)
        raise Problem(
            "validation-failed",
            message,
            errors=[ProblemError(field="obligation_key", rule_id=RULE_OBLIGATION, message=message)],
        )
    return _uuid(found["id"])


def _insert(
    uow: UnitOfWork,
    event_row: Mapping[str, Any],
    *,
    contract_id: UUID,
    obligation_id: UUID | None,
    payload: HoldAppliedV1,
    rule_set_version_id: UUID | None = None,
) -> UUID:
    """The T-CON-20 row of an appended ``HOLD_APPLIED`` (L4-1-Q-22)."""
    principal = uow.principal
    hold_id = _uuid(event_row["id"])
    values: dict[str, Any] = {
        "contract_id": contract_id,
        "obligation_id": obligation_id,
        "hold_type": payload.hold_type.value,
        "hold_source": payload.hold_source.value,
        "reason": payload.reason,
        "rule_set_version_id": rule_set_version_id,
        "rule_id": payload.rule_id,
    }
    uow.session.execute(
        insert(contract_hold).values(
            tenant_id=principal.tenant_id,
            id=hold_id,
            applied_event_id=hold_id,
            applied_at=uow.now,
            **values,
        )
    )
    uow.audit(
        action=APPLY_ACTION,
        object_type=OBJECT_TYPE,
        object_id=hold_id,
        after={name: None if value is None else str(value) for name, value in values.items()},
        contract_id=contract_id,
    )
    return hold_id


def _released(
    uow: UnitOfWork, hold: Mapping[str, Any], event_row: Mapping[str, Any], comment: str
) -> None:
    hold_id = _uuid(hold["id"])
    uow.session.execute(
        update(contract_hold)
        .where(contract_hold.c.id == hold_id)
        .values(released_event_id=event_row["id"], released_at=uow.now)
    )
    uow.audit(
        action=RELEASE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=hold_id,
        before={"released_at": None},
        after={"released_event_id": str(event_row["id"]), "released_at": uow.now.isoformat()},
        comment=comment,
        contract_id=_uuid(hold["contract_id"]),
    )


def _system_unit(uow: UnitOfWork) -> UnitOfWork:
    """The SYSTEM principal in the caller's transaction, stamped with the caller's instant."""
    ctx = dataclasses.replace(
        uow.ctx,
        principal=system_principal(
            uow.principal.tenant_id, on_behalf_of_id=uow.principal.on_behalf_of_id
        ),
    )
    system = UnitOfWork(
        ctx=ctx, session=uow.session, clock=uow.clock, keyring=uow.keyring, files=uow.files
    )
    system.now = uow.now
    return system


def apply_hold(
    uow: UnitOfWork, *, contract_id: UUID, expected_stream_version: int | None, body: HoldApplyIn
) -> ContractOut:
    """``POST /contracts/{id}/apply-hold``: a MANUAL hold (REQ-REC-022)."""
    session = uow.session
    current = _locked(uow, contract_id, expected_stream_version)
    key = body.obligation_key
    obligation_id = None if key is None else _obligation_id(session, contract_id, key)
    payload = HoldAppliedV1(
        hold_type=body.hold_type,
        hold_source=HoldSource.MANUAL,
        obligation_key=key,
        reason=body.reason,
    )
    (event_row,) = append_events(
        uow,
        contract_id=contract_id,
        expected_stream_version=int(current["head_stream_version"]),
        events=[
            EventIn(
                event_type=ContractEventType.HOLD_APPLIED,
                effective_date=entity_date(session, current, uow.now),
                payload=payload,
                obligation_keys=() if key is None else (key,),
                is_manual=uow.principal.kind is PrincipalKind.USER,
            )
        ],
        origin=_origin(uow),
    )
    _insert(uow, event_row, contract_id=contract_id, obligation_id=obligation_id, payload=payload)
    compute(uow, current)
    return queries.contract_out(session, contract_id, now=uow.now)


def _judgement_refusal(session: Session, hold: Mapping[str, Any]) -> str | None:
    """Why a hold is not released by hand, or None (04 §16.1 ``release-hold`` rev 1.209; the
    supervisor's addition to item STEP1-HOLD-RELEASE-1): a SYSTEM hold that is the hold of a
    judgement record of the contract — found by its reason text (module docstring) — while that
    record is SUBMITTED, because the review releases it and the preparer would otherwise end
    alone the hold her own unreviewed record placed; and the hold of a ``NOT_A_CONTRACT`` record
    while the record is REVIEWED, because the assessment that cites it releases it. A record
    that is back in DRAFT, REJECTED or SUPERSEDED refuses nothing: its hold is released by
    hand, as before."""
    if _text(hold["hold_source"]) != HoldSource.SYSTEM.value:
        return None
    records = session.execute(
        select(judgement_record.c.judgement_no, judgement_record.c.topic, judgement_record.c.status)
        .where(judgement_record.c.contract_id == hold["contract_id"])
        .order_by(judgement_record.c.judgement_no)
    ).all()
    return _record_refusal(hold, [tuple(record) for record in records])


def _record_refusal(hold: Mapping[str, Any], records: Sequence[tuple[Any, ...]]) -> str | None:
    """``_judgement_refusal`` over the contract's judgement records — (``judgement_no``,
    ``topic``, ``status``) by number — once they are read: the command reads them for its one
    hold, the reads of a contract's holds once for all of them (``listed_holds``). Pure."""
    if _text(hold["hold_source"]) != HoldSource.SYSTEM.value:
        return None
    for judgement_no, topic, status in records:
        if judgement_hold_reason(judgement_no, topic) != hold["reason"]:
            continue
        if _text(status) == JudgementStatus.SUBMITTED.value:
            return RELEASED_BY_REVIEW.format(judgement_no=judgement_no)
        if _text(status) == JudgementStatus.REVIEWED.value and _text(topic) == STEP1_HOLD_TOPIC:
            return RELEASED_BY_ASSESSMENT.format(judgement_no=judgement_no)
        return None
    return None


def listed_holds(session: Session, contract_ids: Iterable[Any]) -> list[dict[str, Any]]:
    """The OPEN holds of the contracts among ``contract_ids`` that the session sees, oldest
    first, as API-S-Contract and API-S-Obligation list them under ``holds`` (04 §16.1, §16.2 rev
    1.299; item HOLD-RELEASE-READ-1; ``queries.hold_outs`` builds the answer). Until the item
    the reads answered no hold, so ``release-hold`` took an id no read gave: a hold applied from
    a screen had no exit on the screens.

    Each row is the T-CON-20 row with ``level`` (``contract`` when it names no obligation),
    ``applied_by`` and ``applied_by_kind`` — who recorded its ``HOLD_APPLIED`` event — and
    ``release_refusal``. T-CON-20 is RLS-T, so the rows are bound to their contract HERE: a hold
    is read with its contract and with its event, both RLS-TE — either join alone hides the hold
    of a contract the session does not see, and neither is left to do it alone.
    ``release_refusal`` is what ``release_hold`` would answer for the hold as it stands, in the
    command's own order — a voided or terminated contract takes no hold command, then the hold
    of a judgement record that waits — or None where the command would take it. The permission
    and ``If-Match`` are the caller's, not the hold's, and are not answered here; the command's
    409 stays the backstop."""
    ids = sorted({_uuid(value) for value in contract_ids})
    if not ids:
        return []
    rows = (
        session.execute(
            select(
                contract_hold,
                contract.c.status.label("contract_status"),
                contract_event.c.created_by.label("applied_by"),
                contract_event.c.created_by_kind.label("applied_by_kind"),
            )
            .select_from(
                contract_hold.join(
                    contract,
                    and_(
                        contract.c.tenant_id == contract_hold.c.tenant_id,
                        contract.c.id == contract_hold.c.contract_id,
                    ),
                ).join(
                    contract_event,
                    and_(
                        contract_event.c.tenant_id == contract_hold.c.tenant_id,
                        contract_event.c.id == contract_hold.c.applied_event_id,
                    ),
                )
            )
            .where(contract_hold.c.contract_id.in_(ids), contract_hold.c.released_at.is_(None))
            .order_by(contract_hold.c.applied_at, contract_hold.c.id)
        )
        .mappings()
        .all()
    )
    if not rows:
        return []
    of_records = sorted(
        {
            _uuid(row["contract_id"])
            for row in rows
            if _text(row["hold_source"]) == HoldSource.SYSTEM.value
        }
    )
    records: dict[UUID, list[tuple[Any, ...]]] = {}
    if of_records:
        for found in session.execute(
            select(
                judgement_record.c.contract_id,
                judgement_record.c.judgement_no,
                judgement_record.c.topic,
                judgement_record.c.status,
            )
            .where(judgement_record.c.contract_id.in_(of_records))
            .order_by(judgement_record.c.judgement_no)
        ):
            records.setdefault(_uuid(found.contract_id), []).append(
                (found.judgement_no, found.topic, found.status)
            )
    return [
        {
            **hold,
            "level": CONTRACT_LEVEL if hold["obligation_id"] is None else OBLIGATION_LEVEL,
            "release_refusal": release_refusal(
                hold["contract_status"], hold, records.get(_uuid(hold["contract_id"]), ())
            ),
        }
        for hold in (dict(row) for row in rows)
    ]


def release_refusal(
    contract_status: Any, hold: Mapping[str, Any], records: Sequence[tuple[Any, ...]]
) -> str | None:
    """What ``release_hold`` would answer for an open hold, or None (``listed_holds``): the
    command's own refusals in its own order — the contract's status first (``_locked``), then the
    hold of a judgement record that waits (``_record_refusal``). Pure."""
    if _text(contract_status) not in HOLDABLE:
        return NOT_HOLDABLE
    return _record_refusal(hold, records)


def release_hold(
    uow: UnitOfWork,
    *,
    contract_id: UUID,
    expected_stream_version: int | None,
    body: HoldReleaseIn,
) -> ContractOut:
    """``POST /contracts/{id}/release-hold``: the held amount catches up in the period that contains
    the release date (S09-R-44). The hold of a judgement record that is waiting for its review —
    or, for a ``NOT_A_CONTRACT`` record, for its assessment — is not released by hand
    (``_judgement_refusal``; 409 ``invalid-transition``)."""
    session = uow.session
    current = _locked(uow, contract_id, expected_stream_version)
    hold = (
        session.execute(
            select(contract_hold)
            .where(contract_hold.c.id == body.hold_id, contract_hold.c.contract_id == contract_id)
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if hold is None:
        raise Problem("not-found", HOLD_UNKNOWN)
    if hold["released_at"] is not None:
        raise _refuse(ALREADY_RELEASED)
    refusal = _judgement_refusal(session, dict(hold))
    if refusal is not None:
        raise _refuse(refusal)
    (event_row,) = append_events(
        uow,
        contract_id=contract_id,
        expected_stream_version=int(current["head_stream_version"]),
        events=[
            EventIn(
                event_type=ContractEventType.HOLD_RELEASED,
                effective_date=entity_date(session, current, uow.now),
                payload=HoldReleasedV1(hold_id=body.hold_id, comment=body.comment),
                is_manual=uow.principal.kind is PrincipalKind.USER,
            )
        ],
        origin=_origin(uow),
    )
    _released(uow, dict(hold), event_row, body.comment)
    compute(uow, current)
    return queries.contract_out(session, contract_id, now=uow.now)


def apply_system_hold(uow: UnitOfWork, contract_id: UUID, *, reason: str) -> UUID | None:
    """A SYSTEM recognition hold of an ACTIVE contract (REQ-POL-010); an open SYSTEM hold with the
    same reason answers instead. None while the contract is not ACTIVE."""
    session = uow.session
    _, current = repo.lock_group_then_contract(session, contract_id)  # DG-KRN-DB-08 rev 1.36
    if _text(current["status"]) != ContractStatus.ACTIVE.value:
        return None
    existing = open_holds(session, contract_id, source=HoldSource.SYSTEM, reason=reason)
    if existing:
        return _uuid(existing[0]["id"])
    payload = HoldAppliedV1(
        hold_type=HoldType.RECOGNITION, hold_source=HoldSource.SYSTEM, reason=reason
    )
    system = _system_unit(uow)
    (event_row,) = append_events(
        system,
        contract_id=contract_id,
        expected_stream_version=int(current["head_stream_version"]),
        events=[
            EventIn(
                event_type=ContractEventType.HOLD_APPLIED,
                effective_date=entity_date(session, current, uow.now),
                payload=payload,
            )
        ],
        origin="SYSTEM",
    )
    for event in system.drain_audit_events():
        uow.buffer_audit_event(event)
    hold_id = _insert(uow, event_row, contract_id=contract_id, obligation_id=None, payload=payload)
    compute(uow, current)
    return hold_id


def release_system_holds(
    uow: UnitOfWork,
    contract_id: UUID,
    *,
    reason: str,
    comment: str,
    approval_request_id: UUID | None = None,
) -> list[UUID]:
    """Release the open SYSTEM holds of ``reason``; the caller computes the group."""
    session = uow.session
    _, current = repo.lock_group_then_contract(session, contract_id)  # DG-KRN-DB-08 rev 1.36
    holds = open_holds(session, contract_id, source=HoldSource.SYSTEM, reason=reason)
    if not holds:
        return []
    system = _system_unit(uow)
    today = entity_date(session, current, uow.now)
    rows = append_events(
        system,
        contract_id=contract_id,
        expected_stream_version=int(current["head_stream_version"]),
        events=[
            EventIn(
                event_type=ContractEventType.HOLD_RELEASED,
                effective_date=today,
                payload=HoldReleasedV1(hold_id=_uuid(hold["id"]), comment=comment),
                approval_request_id=approval_request_id,
            )
            for hold in holds
        ],
        origin="SYSTEM",
    )
    for event in system.drain_audit_events():
        uow.buffer_audit_event(event)
    for hold, event_row in zip(holds, rows, strict=True):
        _released(uow, hold, event_row, comment)
    return [_uuid(hold["id"]) for hold in holds]


def pending_system_releases(
    session: Session, contract_row: Mapping[str, Any], now: Any, *, reason: str, comment: str
) -> list[EventIn]:
    """The ``HOLD_RELEASED`` events ``release_system_holds`` would append for ``reason``, for a
    dry run that appends nothing (the preview of an append computes what recording would
    append; 04 §16.3 rev 1.138). No lock is taken."""
    holds = open_holds(
        session, _uuid(contract_row["id"]), source=HoldSource.SYSTEM, reason=reason, lock=False
    )
    today = entity_date(session, contract_row, now)
    return [
        EventIn(
            event_type=ContractEventType.HOLD_RELEASED,
            effective_date=today,
            payload=HoldReleasedV1(hold_id=_uuid(hold["id"]), comment=comment),
        )
        for hold in holds
    ]


# --- user hold rules -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Rule:
    rule_key: str
    priority: int
    specificity: int
    conditions: Sequence[Mapping[str, object]]
    outputs: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _RuleSet:
    kind: str
    rules: Sequence[_Rule]


@dataclass(frozen=True, slots=True)
class _HoldRules:
    version_id: UUID
    code: str
    rule_set: _RuleSet
    rule_ids: Mapping[str, UUID]


def _hold_rules(session: Session, at: Any) -> list[_HoldRules]:
    """The PUBLISHED ``HOLD`` rule set versions in force at ``at``."""
    versions = session.execute(
        select(rule_set_version.c.id, rule_set.c.code)
        .select_from(
            rule_set_version.join(
                rule_set,
                and_(
                    rule_set.c.tenant_id == rule_set_version.c.tenant_id,
                    rule_set.c.id == rule_set_version.c.rule_set_id,
                ),
            )
        )
        .where(
            rule_set_version.c.kind == RuleSetKind.HOLD.value,
            rule_set_version.c.status == ConfigStatus.PUBLISHED.value,
            or_(
                rule_set_version.c.effective_from.is_(None), rule_set_version.c.effective_from <= at
            ),
            or_(rule_set_version.c.effective_to.is_(None), rule_set_version.c.effective_to > at),
        )
        .order_by(rule_set.c.code, rule_set_version.c.id)
    ).all()
    found: list[_HoldRules] = []
    for version_id, code in versions:
        rows = session.execute(
            select(
                rule.c.id,
                rule.c.rule_key,
                rule.c.priority,
                rule.c.specificity,
                rule.c.conditions,
                rule.c.outputs,
            )
            .where(rule.c.rule_set_version_id == version_id)
            .order_by(rule.c.rule_key)
        ).all()
        found.append(
            _HoldRules(
                version_id=_uuid(version_id),
                code=str(code),
                rule_set=_RuleSet(
                    kind=RuleSetKind.HOLD.value,
                    rules=tuple(
                        _Rule(
                            rule_key=str(row.rule_key),
                            priority=int(row.priority),
                            specificity=int(row.specificity),
                            conditions=row.conditions,
                            outputs=row.outputs,
                        )
                        for row in rows
                    ),
                ),
                rule_ids={str(row.rule_key): _uuid(row.id) for row in rows},
            )
        )
    return found


def apply_rule_holds(uow: UnitOfWork, contract_id: UUID) -> list[UUID]:
    """USER_RULE holds of the booked obligations (REQ-POL-010; E-55 ``HOLD``). Across versions the
    most specific rule wins, then the highest priority, the rule key and the rule set code; a
    ``level: contract`` output holds the contract once. The holds are effective from inception."""
    session = uow.session
    sets = _hold_rules(session, uow.now)
    if not sets:
        return []
    _, current = repo.lock_group_then_contract(session, contract_id)  # DG-KRN-DB-08 rev 1.36
    obligations = repo.obligations(session, contract_id)
    products = {
        _uuid(row.id): row
        for row in session.execute(
            select(product.c.id, product.c.code, product.c.product_family).where(
                product.c.id.in_(sorted({_uuid(item["product_id"]) for item in obligations}))
            )
        )
    }
    base: dict[str, object] = {
        "contract.region": current["region"],
        "contract.channel": current["channel"],
        "contract.contract_type": current["contract_type"],
        "contract.currency": str(current["transaction_currency"]).strip(),
        "effective_date": current["inception_date"],
    }
    events: list[EventIn] = []
    meta: list[tuple[UUID | None, UUID, HoldAppliedV1]] = []
    contract_held = False
    for row in obligations:
        found = products.get(_uuid(row["product_id"]))
        facts = {
            **base,
            "product.code": None if found is None else str(found.code),
            "product.product_family": None if found is None else found.product_family,
        }
        best: tuple[tuple[int, int, str, str], _HoldRules, Any] | None = None
        for item in sets:
            matched = match(item.rule_set, facts)
            if matched is None:
                continue
            rank = (-matched.specificity, -matched.priority, matched.rule_key, item.code)
            if best is None or rank < best[0]:
                best = (rank, item, matched)
        if best is None:
            continue
        _, chosen, matched = best
        level = str(matched.outputs.get("level", "obligation"))
        if level == CONTRACT_LEVEL:
            if contract_held:
                continue
            contract_held = True
        key = None if level == CONTRACT_LEVEL else str(row["obligation_key"])
        payload = HoldAppliedV1(
            hold_type=HoldType(str(matched.outputs.get("hold_type", HoldType.RECOGNITION.value))),
            hold_source=HoldSource.USER_RULE,
            obligation_key=key,
            reason=RULE_HOLD_REASON.format(rule_key=matched.rule_key, rule_set_code=chosen.code),
            rule_id=chosen.rule_ids[matched.rule_key],
        )
        events.append(
            EventIn(
                event_type=ContractEventType.HOLD_APPLIED,
                effective_date=current["inception_date"],
                payload=payload,
                obligation_keys=() if key is None else (key,),
            )
        )
        meta.append((None if key is None else _uuid(row["id"]), chosen.version_id, payload))
    if not events:
        return []
    rows = append_events(
        uow,
        contract_id=contract_id,
        expected_stream_version=int(current["head_stream_version"]),
        events=events,
        origin=_origin(uow),
    )
    return [
        _insert(
            uow,
            event_row,
            contract_id=contract_id,
            obligation_id=obligation_id,
            payload=payload,
            rule_set_version_id=version_id,
        )
        for event_row, (obligation_id, version_id, payload) in zip(rows, meta, strict=True)
    ]
