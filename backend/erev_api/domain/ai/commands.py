"""Human AI controls; disabling is immediate and never calls a provider."""

from __future__ import annotations

from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import select, update

from erev_api.auth import mfa
from erev_api.db.tables import job, tenant
from erev_api.db.transitions import apply
from erev_api.domain.ai.access import AIAccessRefused
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.domain.ai.retrieval import retrieve_for_user
from erev_api.domain.ai.settings import AISettingsRefused, load_settings
from erev_api.enums import JobKind, JobState, PrincipalKind
from erev_api.problems import Problem
from erev_api.schemas.explain import ExplainObjectType
from erev_api.uow import UnitOfWork

EXPLANATION_MAX_TOKENS: Final = 2048


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
