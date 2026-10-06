"""API-R-09 Approvals: the approval inbox, request detail, decisions, bulk approval and delegations.

04 §15.3 API-R-09, §16.10, API-C-08, API-C-09; SCREENS §15.3 to §15.7 bindings; PRD BR-PLT-06,
BR-PLT-07; dev-guide §5.6 DG-KRN-APR-02, DG-KRN-APR-03; BUILD_SPEC PLF-16. Reads are open to any
member and show the requests ``approval_queries.visible`` allows. The approval engine authorises
each decision against the active step, so the commands guard per subject. Approving, alone or in
bulk, needs a TOTP verification at most five minutes old (BR-PLT-06); rejecting and withdrawing
rely on the session's MFA.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Annotated, Any, Final

import sqlalchemy as sa
from erev_engine.canonical import sha256_hex
from fastapi import APIRouter, Depends, Query, Request, Response

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    command,
    kernel_deps,
    problem_responses,
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.approvals import engine
from erev_api.auth import mfa
from erev_api.auth.dependencies import require_authenticated
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import approval_delegation, approval_request
from erev_api.domain.platform import (
    approval_delegations,
    approval_queries,
    attachments,
    setup,
)
from erev_api.enums import ApprovalRequestStatus, ApprovalSubjectType
from erev_api.problems import INSTANCE_BASE, Problem
from erev_api.schemas.approvals import (
    ApprovalApproveIn,
    ApprovalDelegationIn,
    ApprovalDelegationOut,
    ApprovalDelegationRevokeIn,
    ApprovalOut,
    ApprovalRejectIn,
    ApprovalWithdrawIn,
    BulkApproveIn,
    BulkApproveOut,
    BulkApproveResultOut,
)
from erev_api.schemas.common import ListOut, ProblemOut
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-09 Approvals"
APPROVE_ACTION: Final = engine.DECISION_ACTIONS["APPROVE"]
REJECT_ACTION: Final = engine.DECISION_ACTIONS["REJECT"]
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
_DECISION_PROBLEMS: Final = (
    *_COMMAND_PROBLEMS,
    "not-found",
    "mfa-required",
    "invalid-transition",
    "self-approval",
    "approver-already-decided",
    "stale-approval",
)
# The catalogue of the list (04 API-R-09; DG-FE-21 reads it). ``amount`` is content (04 §16.10
# rev 1.208): the route never orders by the column named here — ``approval_list`` puts the
# reader's own key in its place — and a filter or a search column added here reads a content
# column (``approval_queries.CONTENT_COLUMNS``) through ``approval_queries.shown`` or not at
# all; ``tests/unit/approvals/test_content_scope.py`` walks this specification.
APPROVAL_LIST: Final = ListSpec(
    resource="approvals",
    sort_keys={
        "id": approval_request.c.id,
        "submitted_at": approval_request.c.submitted_at,
        "amount": approval_request.c.amount_functional,
    },
    default_sort="-submitted_at",
    filters={
        "status": FilterSpec(
            name="status",
            column=approval_request.c.status,
            kind="exact",
            choices=frozenset(status.value for status in ApprovalRequestStatus),
        ),
        "subject_type": FilterSpec(
            name="subject_type",
            column=approval_request.c.subject_type,
            kind="exact",
            choices=frozenset(kind.value for kind in ApprovalSubjectType),
        ),
    },
    directions={"amount": "desc"},  # 04 API-R-09: amount largest first
    custom_filters=approval_queries.CUSTOM_FILTERS,
)
DELEGATION_LIST: Final = ListSpec(
    resource="approval-delegations",
    sort_keys={
        "id": approval_delegation.c.id,
        "valid_from": approval_delegation.c.valid_from,
        "valid_to": approval_delegation.c.valid_to,
        "created_at": approval_delegation.c.created_at,
    },
    default_sort="-created_at",
    filters={},
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def approval_list(amount: sa.ColumnElement[Any]) -> ListSpec:
    """``APPROVAL_LIST`` with the sort key ``amount`` of one reader
    (``approval_queries.amount_key``): a row whose content the reader is not shown is ordered as
    a request without an amount, last."""
    return replace(APPROVAL_LIST, sort_keys={**APPROVAL_LIST.sort_keys, "amount": amount})


def approval_etag(out: ApprovalOut) -> str:
    """API-C-08 for an IM-S row without SC-M: the SHA-256 of the representation less
    ``can_decide``, which depends on the caller (SPEC-Q-181)."""
    return f'"h{sha256_hex(out.model_dump(mode="json", exclude={"can_decide"}))[:32]}"'


def _require_step_up(
    uow: UnitOfWork, approval_request_id: uuid.UUID | None = None, **facts: Any
) -> None:
    """BR-PLT-06: approving needs a TOTP verification at most five minutes old. A principal that
    never decides is refused first with 403 ``forbidden`` (DG-KRN-APR-04). Both refusals come
    before a request is read, and both are recorded with the id as sent (``facts`` for the
    ids of a bulk call): the ``DENIED`` event is the same for an id that exists and one that
    does not (item APR-DENIED-AUDIT-1; ruling R-41 (8))."""
    engine.require_person(
        uow, action=APPROVE_ACTION, approval_request_id=approval_request_id, **facts
    )
    if not mfa.step_up_fresh_at(uow.principal.mfa_verified_at, uow.now):
        engine.record_denial(
            uow,
            action=APPROVE_ACTION,
            reason=engine.DENIED_STEP_UP,
            approval_request_id=approval_request_id,
            **facts,
        )
        raise Problem("mfa-step-up-required", mfa.STEP_UP_REQUIRED)


def _approval(uow: UnitOfWork, approval_request_id: uuid.UUID) -> ApprovalOut:
    return ApprovalOut.model_validate(approval_queries.request_out(uow, approval_request_id))


def _bulk_approve(
    uow: UnitOfWork,
    cmd: CommandContext,
    deps: KernelDeps,
    items: list[engine.BulkApproveItem],
    *,
    comment: str | None,
) -> list[engine.BulkApproveResult]:
    """``engine.bulk_approve`` over the items whose impact preview the approver can read; the
    others keep their place in the answer with the REQ-PLT-015 refusal and are not decided. A list
    the engine refuses as a whole (empty, or over its limit) goes to it untouched."""
    refused: dict[uuid.UUID, attachments.PreviewRefusal] = {}
    if 1 <= len(items) <= engine.BULK_LIMIT:
        for item in items:
            refusal = attachments.preview_refusal(uow, item.approval_request_id)
            if refusal is not None:
                refused[item.approval_request_id] = refusal
    readable = [item for item in items if item.approval_request_id not in refused]
    decided = iter(
        engine.bulk_approve(
            cmd.ctx,
            readable,
            comment=comment,
            clock=deps.clock,
            keyring=deps.keyring,
            files=deps.files,
        )
        if readable or not refused
        else []
    )
    results: list[engine.BulkApproveResult] = []
    for item in items:
        refusal = refused.get(item.approval_request_id)
        results.append(
            next(decided)
            if refusal is None
            else engine.BulkApproveResult(item.approval_request_id, refusal.status, refusal.problem)
        )
    return results


@router.get(
    "/approvals",
    operation_id="approvals_list",
    response_model=ListOut[ApprovalOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def approvals_list(
    request: Request,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_authenticated())],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[list[ApprovalRequestStatus] | None, Query()] = None,
    subject_type: Annotated[list[ApprovalSubjectType] | None, Query()] = None,
    assigned_to_me: Annotated[
        bool | None,
        Query(description="true: pending requests the caller can decide, oldest first by sort"),
    ] = None,
    entity: Annotated[
        list[str] | None,
        Query(description="An entity code or id (API-C-11); requests of the named entities"),
    ] = None,
    preparer: Annotated[str | None, Query(description="me or a membership id")] = None,
) -> ListOut[ApprovalOut]:
    """Visible approval requests; sort ``submitted_at``, ``-submitted_at`` or ``amount``."""
    result, items = approval_queries.list_approvals(
        ctx,
        filters=params.filters,
        page=lambda session, statement, amount: paginate(
            session, statement, approval_list(amount), params
        ),
        files=request.app.state.file_store,
        keyring=request.app.state.keyring,
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[ApprovalOut](
        items=[ApprovalOut.model_validate(item) for item in items], next_cursor=result.next_cursor
    )


@router.get(
    "/approvals/{approval_request_id}",
    operation_id="approvals_get",
    response_model=ApprovalOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def approvals_get(
    approval_request_id: uuid.UUID,
    request: Request,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_authenticated())],
) -> ApprovalOut:
    """API-S-Approval with its steps, decisions, impact preview and ``can_decide``."""
    out = ApprovalOut.model_validate(
        approval_queries.get_approval(
            ctx,
            approval_request_id,
            files=request.app.state.file_store,
            keyring=request.app.state.keyring,
        )
    )
    response.headers["ETag"] = approval_etag(out)
    return out


@router.post(
    "/approvals/{approval_request_id}/approve",
    operation_id="approvals_approve",
    response_model=ApprovalOut,
    responses=problem_responses(*_DECISION_PROBLEMS, "mfa-step-up-required", "sandbox-restricted"),
)
def approvals_approve(
    approval_request_id: uuid.UUID,
    body: ApprovalApproveIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Approve the active step with the hashes the approver reviewed (REQ-PLT-014). A request
    whose stored impact preview the approver cannot read is refused 409 ``invalid-transition``
    (REQ-PLT-015) before any decision is written. In a sandbox the approval of an
    ``EVIDENCE_SHRED`` request for a file the sandbox shares with the workspace it was copied
    from is refused 403 ``sandbox-restricted`` and the request stays pending (05 SBX-08): a
    sandbox destroys nothing it shares."""

    def handle(uow: UnitOfWork) -> ApprovalOut:
        _require_step_up(uow, approval_request_id)
        attachments.require_preview_readable(uow, approval_request_id)
        engine.decide(
            uow,
            approval_request_id=approval_request_id,
            decision="APPROVE",
            subject_content_sha256=body.subject_content_sha256,
            impact_preview_sha256=body.impact_preview_sha256,
            comment=body.comment,
            reason_code=body.reason_code,
        )
        # An approved ROLE_ASSIGNMENT can complete setup (PRD BR-PLT-02; BUILD_SPEC RFD-19).
        setup.evaluate_setup_completion(uow)
        return _approval(uow, approval_request_id)

    return run_command(cmd, deps, handle, etag=approval_etag)


@router.post(
    "/approvals/{approval_request_id}/reject",
    operation_id="approvals_reject",
    response_model=ApprovalOut,
    responses=problem_responses(*_DECISION_PROBLEMS),
)
def approvals_reject(
    approval_request_id: uuid.UUID,
    body: ApprovalRejectIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Reject the request with a comment; the preparer is notified (NTF-03)."""

    def handle(uow: UnitOfWork) -> ApprovalOut:
        # Before the row is read: a caller that is no person gets the same 403 for every id, so
        # the answer never confirms a request it could not read (REQ-PLT-012; R-41 (8)).
        engine.require_person(uow, action=REJECT_ACTION, approval_request_id=approval_request_id)
        request = approval_queries.request_row(uow, approval_request_id)
        engine.decide(
            uow,
            approval_request_id=approval_request_id,
            decision="REJECT",
            subject_content_sha256=str(request["subject_content_sha256"]),
            impact_preview_sha256=request["impact_preview_sha256"],
            comment=body.comment,
            reason_code=body.reason_code,
        )
        return _approval(uow, approval_request_id)

    return run_command(cmd, deps, handle, etag=approval_etag)


@router.post(
    "/approvals/{approval_request_id}/withdraw",
    operation_id="approvals_withdraw",
    response_model=ApprovalOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def approvals_withdraw(
    approval_request_id: uuid.UUID,
    body: ApprovalWithdrawIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """The preparer withdraws a pending request (PRD SM-01)."""

    def handle(uow: UnitOfWork) -> ApprovalOut:
        engine.withdraw(uow, approval_request_id=approval_request_id, comment=body.comment)
        return _approval(uow, approval_request_id)

    return run_command(cmd, deps, handle, etag=approval_etag)


@router.post(
    "/approvals/bulk-approve",
    operation_id="approvals_bulk_approve",
    response_model=BulkApproveOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "mfa-step-up-required"),
)
def approvals_bulk_approve(
    body: BulkApproveIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Approve each item in its own transaction; refusals are per-item problems (REQ-PLT-017).
    An item whose stored impact preview the approver cannot read is refused like any other, with
    409 ``invalid-transition`` (REQ-PLT-015), and is not decided."""

    def handle(uow: UnitOfWork) -> BulkApproveOut:
        # A bulk call refused as a whole is one attempt: one event, naming the ids it sent.
        _require_step_up(
            uow,
            approval_request_ids=[
                str(item.approval_request_id) for item in body.items[: engine.BULK_LIMIT]
            ],
            items=len(body.items),
        )
        items = [
            engine.BulkApproveItem(
                approval_request_id=item.approval_request_id,
                subject_content_sha256=item.subject_content_sha256,
                impact_preview_sha256=item.impact_preview_sha256,
            )
            for item in body.items
        ]
        results = _bulk_approve(uow, cmd, deps, items, comment=body.comment)
        # Each item committed in its own transaction; this command reads their grants (RFD-19).
        setup.evaluate_setup_completion(uow)
        instance = INSTANCE_BASE + cmd.ctx.request_id
        return BulkApproveOut(
            results=[
                BulkApproveResultOut(
                    approval_request_id=result.approval_request_id,
                    status=result.status,
                    problem=None
                    if result.problem is None
                    else ProblemOut.model_validate(result.problem.to_json(instance=instance)),
                )
                for result in results
            ]
        )

    return run_command(cmd, deps, handle)


@router.get(
    "/approval-delegations",
    operation_id="approval_delegations_list",
    response_model=ListOut[ApprovalDelegationOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def approval_delegations_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_authenticated())],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[ApprovalDelegationOut]:
    """The delegations the caller gave or received, newest first, and for an access
    administrator (``role.manage``) the delegations they may end: every delegation of the
    workspace for an administrator of all entities, and for an administrator of named entities
    those whose delegator's access lies within their own."""
    result, items = approval_delegations.list_delegations(
        ctx, page=lambda session, statement: paginate(session, statement, DELEGATION_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[ApprovalDelegationOut](
        items=[ApprovalDelegationOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/approval-delegations",
    operation_id="approval_delegations_create",
    status_code=201,
    response_model=ApprovalDelegationOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "mfa-required", "mfa-step-up-required", "sod-conflict"
    ),
)
def approval_delegations_create(
    body: ApprovalDelegationIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Delegate approval permissions the caller holds, with a TOTP verification at most five
    minutes old (BR-PLT-06). The delegation ends within 90 days of the command, goes to a member
    with a confirmed second factor only, and is checked for separation of duties as a role
    assignment is (BR-PLT-07)."""
    return run_command(
        cmd,
        deps,
        lambda uow: ApprovalDelegationOut.model_validate(
            approval_delegations.create_delegation(
                uow,
                delegate_membership_id=body.delegate_membership_id,
                permissions=body.permissions,
                valid_from=body.valid_from,
                valid_to=body.valid_to,
                reason=body.reason,
            )
        ),
        status_code=201,
    )


@router.post(
    "/approval-delegations/{delegation_id}/revoke",
    operation_id="approval_delegations_revoke",
    response_model=ApprovalDelegationOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "not-found",
        "invalid-transition",
        "mfa-required",
        "mfa-step-up-required",
    ),
)
def approval_delegations_revoke(
    delegation_id: uuid.UUID,
    body: ApprovalDelegationRevokeIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """The delegator, or an access administrator (``role.manage`` for the delegator's
    entities), ends the delegation now, with a TOTP verification at most five minutes old
    (BR-PLT-06, BR-PLT-07)."""
    return run_command(
        cmd,
        deps,
        lambda uow: ApprovalDelegationOut.model_validate(
            approval_delegations.revoke_delegation(uow, delegation_id, reason=body.reason)
        ),
    )
