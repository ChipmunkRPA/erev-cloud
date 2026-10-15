"""Human AI controls and submission; HTTP commands never call a provider."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from erev_api.audit.writer import record
from erev_api.auth import mfa
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import job, tenant
from erev_api.db.transitions import apply
from erev_api.domain.ai.access import AIAccessRefused
from erev_api.domain.ai.document_preparation import MAX_PDF_BYTES
from erev_api.domain.ai.extraction_fields import CONTRACT_EXTRACTION_PATHS
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.domain.ai.queries import proposal_in
from erev_api.domain.ai.retrieval import retrieve_for_user
from erev_api.domain.ai.settings import AISettingsRefused, load_settings
from erev_api.domain.platform import file_access
from erev_api.enums import JobKind, JobState, PrincipalKind
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.ai import AIProposalOut
from erev_api.schemas.explain import ExplainObjectType
from erev_api.uow import UnitOfWork

EXPLANATION_MAX_TOKENS: Final = 2048
EXTRACTION_MAX_TOKENS: Final = 16000


def disable(uow: UnitOfWork, *, comment: str) -> datetime:
    """API-R-04: disable the workspace and cancel its queued AI work atomically."""
    principal = uow.principal
    if (
        principal.kind is not PrincipalKind.USER
        or principal.id is None
        or "settings.manage" not in principal.permissions
        or principal.permission_scopes.get("settings.manage") != "*"
    ):
        raise Problem("forbidden")
    if not mfa.step_up_fresh_at(principal.mfa_verified_at, uow.now):
        raise Problem("mfa-step-up-required", mfa.STEP_UP_REQUIRED)
    if not comment.strip() or len(comment) > 4000:
        raise Problem("validation-failed", "Provide a comment for turning off AI.")
    tenant_id = principal.tenant_id
    # NO KEY UPDATE serializes switches without blocking FK checks on the tenant.
    disabled_at = uow.session.scalar(
        select(tenant.c.ai_disabled_at)
        .where(tenant.c.id == tenant_id)
        .with_for_update(key_share=True)
    )
    if disabled_at is not None:
        assert isinstance(disabled_at, datetime)
        return disabled_at
    uow.session.execute(
        update(tenant)
        .where(tenant.c.id == tenant_id)
        .values(
            ai_disabled_at=uow.now,
            ai_disabled_by=principal.id,
            ai_disabled_by_kind=principal.kind.value,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
    )
    queued = tuple(
        uow.session.scalars(
            select(job.c.id)
            .where(
                job.c.tenant_id == tenant_id,
                job.c.kind == JobKind.AI_TASK.value,
                job.c.state == JobState.QUEUED.value,
            )
            .order_by(job.c.id)
            .with_for_update()
        )
    )
    for job_id in queued:
        apply(
            uow.session,
            "job",
            job_id,
            to_status=JobState.CANCELLED.value,
            expected_status=JobState.QUEUED.value,
            set_values={
                "cancel_requested_at": uow.now,
                "finished_at": uow.now,
                "updated_at": uow.now,
                "updated_by": principal.id,
                "updated_by_kind": principal.kind.value,
            },
        )
        uow.audit(
            action="job.cancel",
            object_type="job",
            object_id=job_id,
            before={"state": JobState.QUEUED.value, "cancel_requested_at": None},
            after={
                "kind": JobKind.AI_TASK.value,
                "state": JobState.CANCELLED.value,
                "cancel_requested_at": uow.now,
            },
        )
    uow.audit(
        action="ai.disabled",
        object_type="tenant",
        object_id=tenant_id,
        before={"ai_disabled_at": None},
        after={"ai_disabled_at": uow.now, "cancelled_jobs": len(queued)},
        comment=comment.strip(),
    )
    return uow.now


def request_explanation(
    uow: UnitOfWork,
    *,
    object_type: ExplainObjectType,
    object_id: UUID,
    measure: str,
    period: str | None,
    platform_kill_switch: bool,
) -> UUID:
    """Authorize the source, then queue selectors as the human; no provider call here."""
    principal = uow.principal
    # Shared with disable and approved re-enable: the queue insertion and AI
    # admission must commit before a competing switch can finish its cancellation.
    uow.session.execute(
        select(tenant.c.id)
        .where(tenant.c.id == principal.tenant_id)
        .with_for_update(key_share=True)
    ).scalar_one()
    try:
        settings = load_settings(
            uow.session,
            tenant_id=principal.tenant_id,
            now=uow.now,
            platform_kill_switch=platform_kill_switch,
        )
        settings.require_available()
    except AISettingsRefused as error:
        if str(error) == "AI_DISABLED":
            raise Problem("ai-disabled") from None
        raise Problem("validation-failed", "AI configuration is unavailable.") from None
    try:
        retrieved = retrieve_for_user(
            principal,
            now=uow.now,
            object_type=object_type,
            object_id=object_id,
            measure=measure,
            period=period,
            model=settings.model,
            max_tokens=EXPLANATION_MAX_TOKENS,
            redact_contact_details=settings.redact_contact_details,
        )
    except AIAccessRefused:
        raise Problem("forbidden") from None
    except PreparationRefused:
        raise Problem(
            "validation-failed", "This source cannot be prepared for AI explanation."
        ) from None
    requested = uow.defer(
        JobKind.AI_TASK,
        {
            "operation": "narrative",
            "object_type": object_type,
            "object_id": str(object_id),
            "measure": measure,
            "period": period,
            "max_tokens": EXPLANATION_MAX_TOKENS,
            "expected_trace_id": str(retrieved.prepared.trace_id),
        },
    )
    return UUID(str(requested["id"]))


def reject_proposal(
    uow: UnitOfWork, proposal_id: UUID, *, reason: str, check_version: Callable[[int], None]
) -> AIProposalOut:
    """Reject retained evidence as a human, with no provider or accounting side effects."""
    principal = uow.principal
    if principal.kind is not PrincipalKind.USER or principal.id is None:
        raise Problem("forbidden")
    reason = reason.strip()
    if not reason or len(reason) > 4000:
        raise Problem("validation-failed", "Provide a rejection reason.")
    current = proposal_in(uow.session, principal, proposal_id, lock=True)
    check_version(current.row_version)
    if current.status != "proposed" or current.expires_at <= uow.now:
        raise Problem("invalid-transition", "Only an unexpired proposed item can be rejected.")
    apply(
        uow.session,
        "ai_proposal",
        proposal_id,
        to_status="rejected",
        expected_status="proposed",
        expected_row_version=current.row_version,
        set_values={
            "row_version": current.row_version + 1,
            "rejected_by": principal.id,
            "rejected_at": uow.now,
            "rejection_reason": reason,
            "updated_by": principal.id,
            "updated_by_kind": principal.kind.value,
            "updated_at": uow.now,
        },
    )
    record(
        uow,
        action="ai_proposal.reject",
        object_type="ai_proposal",
        object_id=proposal_id,
        before={"status": "proposed"},
        after={"status": "rejected"},
        detail={"reason": reason},
    )
    return proposal_in(uow.session, principal, proposal_id)


def extraction_file(session: Session, ctx: RequestContext, file_id: UUID) -> Mapping[str, Any]:
    """Bind current human source access before inspecting metadata; read no document bytes."""
    principal = ctx.principal
    held = principal.permission_scopes.get("ai.use", frozenset())
    if (
        principal.kind is not PrincipalKind.USER
        or principal.id is None
        or "ai.use" not in principal.permissions
        or not held
        or (
            held != "*"
            and (principal.entity_scope == "*" or not set(principal.entity_scope).issubset(held))
        )
    ):
        raise Problem("forbidden")
    source = file_access.bound(session, ctx, file_id)
    if source is None or source["shredded_at"] is not None:
        raise Problem("not-found")
    if source["purpose"] != "ATTACHMENT" or source["media_type"] != "application/pdf":
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="file_id", rule_id="AI_INVALID_PDF", message="Select a PDF attachment."
                )
            ],
        )
    if source["size_bytes"] > MAX_PDF_BYTES:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="file_id",
                    rule_id="AI_DOCUMENT_FILE_LIMIT",
                    message="The PDF exceeds the extraction size limit.",
                )
            ],
        )
    return source


def request_extraction(uow: UnitOfWork, *, file_id: UUID, platform_kill_switch: bool) -> UUID:
    """Serialize admission with emergency disable, then defer a bounded source-only task."""
    uow.session.execute(
        select(tenant.c.id)
        .where(tenant.c.id == uow.principal.tenant_id)
        .with_for_update(key_share=True)
    ).scalar_one()
    source = extraction_file(uow.session, uow.ctx, file_id)
    try:
        settings = load_settings(
            uow.session,
            tenant_id=uow.principal.tenant_id,
            now=uow.now,
            platform_kill_switch=platform_kill_switch,
        )
        settings.require_available()
    except AISettingsRefused as error:
        if str(error) == "AI_DISABLED":
            raise Problem("ai-disabled") from None
        raise Problem("validation-failed", "AI configuration is unavailable.") from None
    if not settings.send_contract_text:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="file_id",
                    rule_id="AI_TEXT_DISABLED",
                    message="Contract text sending is disabled.",
                )
            ],
        )
    requested = uow.defer(
        JobKind.AI_TASK,
        {
            "operation": "extraction",
            "file_id": str(file_id),
            "file_sha256": str(source["sha256"]).strip(),
            "allowed_paths": sorted(CONTRACT_EXTRACTION_PATHS),
            "max_tokens": EXTRACTION_MAX_TOKENS,
        },
    )
    return UUID(str(requested["id"]))
