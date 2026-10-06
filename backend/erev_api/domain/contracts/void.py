"""Contract void (04 §16.1 ``request-void``, §16.3 ``CONTRACT_VOIDED``, table 3.4-R, T-SL-01
``void:<contract_event_id>``; PRD §2.5 routing rows ``CONTRACT_VOID``, §5.2 SM-02, J-26;
03 REQ-CON-015; BUILD_SPEC CTR-11; control CTL-046).

A void is an approved command. ``POST /contracts/{id}/request-void`` (``contract.void``; If-Match)
checks the SM-02 guard (any status except ``VOIDED``, for a contract without a current
non-singleton applied group membership, SMAP-01), the table 3.4-R reason subset and the pending
request, computes the dry run with the pending ``CONTRACT_VOIDED`` as the impact preview
(REQ-PLT-015) and opens a ``CONTRACT_VOID`` request: one ``contract.approve`` step, and a second
step held by a Controller when the contract has posted lines (flag ``POSTED_LINES``; PRD §2.5).
Nothing changes on the contract while the request is pending (the request is the pending state,
04 SMAP rule). On approval the SYSTEM principal appends ``CONTRACT_VOIDED`` on behalf of the
preparer with the request id and recomputes the group: stage 01 zeroes every target of the
contract (ENGINE_SPEC S01-R-13) and stage 14 posts the difference as a ``VOID_REVERSAL`` delta in
the first open period, tagged with its origin periods (ENGINE_SPEC_B S14-R-08;
``computation._posting_source``). Nothing is deleted (D-01; REQ-CON-015).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

from erev_engine.errors import EngineError
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals.subjects import (
    CONTROLLER_ROLE,
    POSTED_LINES,
    PostedBasis,
    SubjectLifecycle,
    posted_basis,
    register_lifecycle,
    reversed_population,
)
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import system_principal
from erev_api.db import transitions
from erev_api.db.locking import lock_group_then_contract
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import approval_request, contract, subledger_line
from erev_api.domain.contracts import bundles, computation, repo
from erev_api.domain.contracts.activation import (
    DRY_RUN,
    STALE_CONTRACT,
    booked_amount,
    engine_problem,
)
from erev_api.domain.contracts.events import REASON_LABELS, VOID_REASONS, impact_summary
from erev_api.domain.contracts.holds import entity_date
from erev_api.enums import (
    ApprovalSubjectType,
    CombinationStatus,
    ComputationTrigger,
    ContractEventType,
    ContractStatus,
    PrincipalKind,
)
from erev_api.events.payloads import ContractVoidedV1
from erev_api.events.stream import EventIn, append_events
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.contracts import ContractVoidRequestedOut, ContractVoidRequestIn
from erev_api.uow import UnitOfWork

__all__ = [
    "COMBINED_MEMBER",
    "CONTROLLER_ROLE",
    "POSTED_LINES",
    "REQUEST_ACTION",
    "VOID_PERMISSION",
    "request_void",
    "void_flags",
]

VOID_PERMISSION: Final = "contract.void"  # 04 API-R-28; PRD ACT-05
OBJECT_TYPE: Final = "contract"
REQUEST_ACTION: Final = "contract.void_requested"
CLOSED_ACTION: Final = "contract.void_request_closed"
RULE_REASON: Final = "REASON_CODE_NOT_ALLOWED"  # 04 table 15.4-B
ALREADY_VOIDED: Final = "This contract is already voided."
COMBINED_MEMBER: Final = (
    "A contract combined into an applied group cannot be voided; take it out of the group first."
)
REASON_NOT_ALLOWED: Final = "The reason {label} cannot be used to void a contract."
EXECUTED_ACTION: Final = "contract.void_executed"  # D-98 99a: the approved cutoff, durably
# D-98 99b: the reversed set derived from the stored chain position must hold exactly the lines
# the request was approved over; a departure refuses the execution by name.
CUTOFF_CODE: Final = "CUTOFF_POPULATION_MISMATCH"
CUTOFF_MISMATCH: Final = (
    "The postings at or below the approved cutoff position hold {derived} lines, but the request "
    "was approved over {stored}; the void was not executed."
)
# D-98 92 / 101: the approval revalidates the posted-state basis, finally under the financial locks.
STALE_BASIS: Final = (
    "The contract's posted state changed since this void was routed ({before} → {after}); the "
    "request is stale — resubmit the void so it is routed under its current posted state."
)


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _refuse(message: str) -> Problem:
    return Problem(
        "invalid-transition",
        message,
        errors=[ProblemError(field="status", rule_id=transitions.RULE_ID, message=message)],
    )


def _voided(
    session: Session,
    current: Mapping[str, Any],
    now: Any,
    *,
    reason_code: str,
    comment: str,
    approval_request_id: UUID | None,
    basis: PostedBasis | None = None,
) -> EventIn:
    """The ``CONTRACT_VOIDED`` event at the contracting entity's current date (05 TZ-03); on
    approval the payload carries the approved posted-state cutoff — count, readable time and the
    per-book chain position (D-98 99a / 99b)."""
    members: dict[str, Any] = {"reason_code": reason_code, "comment": comment}
    if approval_request_id is not None and basis is not None:
        members["approval_request_id"] = str(approval_request_id)
        members.update(basis.members())
    return EventIn(
        event_type=ContractEventType.CONTRACT_VOIDED,
        effective_date=entity_date(session, current, now),
        payload=ContractVoidedV1.model_validate(members),
        approval_request_id=approval_request_id,
    )


def _preview(
    status: str, summary: Mapping[str, Any], basis: PostedBasis
) -> approvals.ImpactPreview:
    """The dry run with the pending void as the request's impact preview (REQ-PLT-015): the
    revenue by period, transaction price, RPO and journal lines the void reverses, and the
    posted-state basis the request was routed on (D-98 99a; readable in the stored preview)."""
    revenue = summary["revenue_by_period"]
    return approvals.ImpactPreview(
        before={
            "status": status,
            "posted_basis": basis.members(),
            "transaction_price": summary["transaction_price_before"],
            "rpo": summary["rpo_before"],
            "revenue_by_period": [
                {"period_key": row["period_key"], "amount": row["before"]} for row in revenue
            ],
            "balances": summary["balances_before"],
        },
        after={
            "status": ContractStatus.VOIDED.value,
            "transaction_price": summary["transaction_price_after"],
            "rpo": summary["rpo_after"],
            "revenue_by_period": [
                {"period_key": row["period_key"], "amount": row["after"]} for row in revenue
            ],
            "balances": summary["balances_after"],
            "journal_lines": summary["journal_lines"],
        },
    )


def void_flags(session: Session, contract_id: UUID) -> frozenset[str]:
    """PRD §2.5 ``CONTRACT_VOID`` rows: ``POSTED_LINES`` when any subledger line of the contract
    exists, which adds the Controller second step (04 T-PLT-17 ``flags``; BUILD_SPEC CTR-11)."""
    posted = session.execute(
        select(subledger_line.c.id).where(subledger_line.c.contract_id == contract_id).limit(1)
    ).first()
    return frozenset({POSTED_LINES}) if posted is not None else frozenset()


def request_void(
    uow: UnitOfWork,
    *,
    contract_id: UUID,
    expected_stream_version: int | None,
    body: ContractVoidRequestIn,
    engine: computation.Engine | None = None,
) -> ContractVoidRequestedOut:
    """``POST /contracts/{id}/request-void`` (04 §16.1; PRD SM-02; REQ-CON-015)."""
    session = uow.session
    # D-98 101 / 101c: the one lock order — the combination group, then the contract row FOR
    # UPDATE — through the kernel helper (membership re-verified under the locks; 412 REGROUPED).
    group_id, current = lock_group_then_contract(session, contract_id)
    require_for_entity(uow.ctx, VOID_PERMISSION, current["contracting_entity_id"])
    group = repo.get_group(session, group_id)  # the group row is locked already
    head = int(current["head_stream_version"])
    if expected_stream_version != head:
        raise Problem("precondition-failed", STALE_CONTRACT)
    reason = body.reason_code.value
    if reason not in VOID_REASONS:
        message = REASON_NOT_ALLOWED.format(label=REASON_LABELS.get(reason, reason))
        raise Problem(
            "validation-failed",
            message,
            errors=[ProblemError(field="reason_code", rule_id=RULE_REASON, message=message)],
        )
    status = _text(current["status"])
    if status == ContractStatus.VOIDED.value:
        raise _refuse(ALREADY_VOIDED)
    if not group["is_singleton"] and _text(group["status"]) == CombinationStatus.APPLIED.value:
        raise _refuse(COMBINED_MEMBER)
    # Item PREVIEW-INLINE-SCOPE-1 (04 API-S-ImpactSummary rev 1.319; R-64 (1)): the basis the
    # stored preview states is the basis the request's content hashes — the contract's posted
    # lines, whichever entity they were posted for, read under the tenant's scope. Measured
    # before: 16 posted lines of 28 for a preparer of the contracting entity alone.
    with system_entity_scope(session):
        basis = posted_basis(session, contract_id)
    pending = [
        _voided(
            session,
            current,
            uow.now,
            reason_code=reason,
            comment=body.comment,
            approval_request_id=None,
        )
    ]
    run = engine if engine is not None else computation.default_engine()
    try:
        bundle = bundles.build(
            session, group_id, uow.now, pending, DRY_RUN, pending_contract_id=contract_id
        )
        output = run(bundle)
    except EngineError as error:
        raise engine_problem(error) from error
    summary = impact_summary(
        session, current, bundle, output, pending, computed_at=uow.now
    ).model_dump(mode="json")
    request = approvals.submit(
        uow,
        subject_type=ApprovalSubjectType.CONTRACT_VOID,
        subject_id=contract_id,
        summary=f"Void {current['external_id']}",
        impact_preview=_preview(status, summary, basis),
        comment=body.comment,
        reason_code=reason,
        auto_approval=False,  # CTL-046: a void is always approved by another person
    )
    request_id = _uuid(request["id"])
    uow.audit(
        action=REQUEST_ACTION,
        object_type=OBJECT_TYPE,
        object_id=contract_id,
        object_version=str(head),
        before={"status": status},
        after={"status": status, "reason_code": reason, "approval_request_id": str(request_id)},
        reason_code=reason,
        comment=body.comment,
        approval_request_id=request_id,
        contract_id=contract_id,
    )
    return ContractVoidRequestedOut(approval_request_id=request_id)


def _system_unit(uow: UnitOfWork, on_behalf_of: UUID | None) -> UnitOfWork:
    """The SYSTEM principal in the caller's transaction, on behalf of the preparer."""
    principal = system_principal(uow.principal.tenant_id, on_behalf_of_id=on_behalf_of)
    ctx = dataclasses.replace(uow.ctx, principal=principal)
    system = UnitOfWork(
        ctx=ctx, session=uow.session, clock=uow.clock, keyring=uow.keyring, files=uow.files
    )
    system.now = uow.now
    return system


def _approved(uow: UnitOfWork, contract_id: UUID, approval_request_id: UUID) -> None:
    """``on_approved`` of ``CONTRACT_VOID`` (DG-CMD-09 decision command). D-98 92 / 101: the
    posted-state basis is revalidated against what the request was routed on — a pre-lock check as a
    fast path, then the FINAL check under the financial locks taken in the posting path's order (the
    combination group, then the contract row ``FOR UPDATE``; ``decide`` holds the request row): the
    subject content hash and the ``POSTED_LINES`` flag are recomputed there and any change is
    refused as 409 ``stale-approval`` (the decision rolls back; the void is resubmitted, never
    rerouted silently). Under the same locks and in the same transaction SYSTEM appends
    ``CONTRACT_VOIDED`` on behalf of the preparer with the request's reason, comment and approved
    cutoff (D-98 99a; the per-book chain position of D-98 99b, whose derived population must hold
    the approved line count — ``CUTOFF_POPULATION_MISMATCH`` otherwise), the execution is audited
    with the cutoff, and the group is recomputed and its reversal posted; an ``EngineError`` raises
    422 and rolls the decision back."""
    session = uow.session
    request = (
        session.execute(
            select(
                approval_request.c.preparer_id,
                approval_request.c.preparer_kind,
                approval_request.c.reason_code,
                approval_request.c.comment,
                approval_request.c.flags,
                approval_request.c.subject_content_sha256,
            ).where(approval_request.c.id == approval_request_id)
        )
        .mappings()
        .one()
    )
    routed = frozenset(str(flag) for flag in (request["flags"] or ()))
    _refuse_changed_basis(
        routed, void_flags(session, contract_id)
    )  # fast path, never the last check
    on_behalf_of = (
        _uuid(request["preparer_id"])
        if request["preparer_id"] is not None
        and _text(request["preparer_kind"]) == PrincipalKind.USER.value
        else None
    )
    # D-98 101 / 101c: the one lock order through the kernel helper (group, then contract row).
    group_id, current = lock_group_then_contract(session, contract_id)
    if _text(current["status"]) == ContractStatus.VOIDED.value:
        return
    # Final validation under the locks, before the first write (D-98 101 / 101d(2)): the engine
    # recomputes the subject content hash (posted-state basis included) against the basis the
    # approvers reviewed — a difference is StaleBasis, and ``decide`` voids the request
    # STALE_SUBJECT with 409 stale-approval; then the routed flags and the D-98 99b population.
    approvals.assert_fresh_basis(uow, approval_request_id)
    _refuse_changed_basis(routed, void_flags(session, contract_id))
    basis = posted_basis(session, contract_id)
    # D-98 99b: the reversed set is derived from the stored chain position, never from the
    # timestamps; its population must hold exactly the lines the request was approved over (the
    # content hash above ties ``basis`` to the request), else the execution is refused by name.
    _, derived = reversed_population(session, contract_id, basis.positions)
    if derived != basis.line_count:
        raise Problem(
            "stale-approval",
            CUTOFF_MISMATCH.format(derived=derived, stored=basis.line_count),
            code=CUTOFF_CODE,
        )
    system = _system_unit(uow, on_behalf_of)
    append_events(
        system,
        contract_id=contract_id,
        expected_stream_version=int(current["head_stream_version"]),
        events=[
            _voided(
                session,
                current,
                uow.now,
                reason_code=str(request["reason_code"]),
                comment=str(request["comment"] or ""),
                approval_request_id=approval_request_id,
                basis=basis,
            )
        ],
        origin="SYSTEM",
    )
    for event in system.drain_audit_events():
        uow.buffer_audit_event(event)
    uow.audit(
        action=EXECUTED_ACTION,
        object_type=OBJECT_TYPE,
        object_id=contract_id,
        object_version=str(int(current["head_stream_version"]) + 1),
        before={"status": _text(current["status"])},
        after={"status": ContractStatus.VOIDED.value},
        approval_request_id=approval_request_id,
        detail={
            "approval_request_id": str(approval_request_id),
            "flags": sorted(routed),
            **basis.members(),
        },
        contract_id=contract_id,
    )
    try:
        computation.recompute(uow, group_id, trigger=ComputationTrigger.COMMAND)
    except EngineError as error:
        raise engine_problem(error) from error


def _refuse_changed_basis(routed: frozenset[str], basis: frozenset[str]) -> None:
    if basis != routed:
        raise Problem(
            "stale-approval",
            STALE_BASIS.format(
                before=", ".join(sorted(routed)) or "none", after=", ".join(sorted(basis)) or "none"
            ),
        )


def _closed(uow: UnitOfWork, contract_id: UUID, approval_request_id: UUID) -> None:
    """``on_rejected`` and ``on_voided``: the contract never changed while the request was pending
    (SMAP rule), so the decision leaves an audit trail only."""
    status = uow.session.execute(
        select(contract.c.status).where(contract.c.id == contract_id)
    ).scalar_one_or_none()
    if status is None:
        return
    uow.audit(
        action=CLOSED_ACTION,
        object_type=OBJECT_TYPE,
        object_id=contract_id,
        before={"status": _text(status)},
        after={"status": _text(status)},
        approval_request_id=approval_request_id,
        contract_id=contract_id,
    )


register_lifecycle(
    ApprovalSubjectType.CONTRACT_VOID,
    SubjectLifecycle(
        on_approved=_approved,
        on_rejected=_closed,
        on_voided=_closed,
        flags=void_flags,
        # Item ACT-FLAGS-1 (04 T-PLT-17 rev 1.287): the booked consideration in the entity's
        # functional currency, also where the contract's currency is another.
        amount=booked_amount,
    ),
)
