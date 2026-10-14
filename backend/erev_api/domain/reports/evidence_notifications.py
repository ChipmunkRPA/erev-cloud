"""NTF-06 for the first successful retention of an automatically prepared CLOSE pack."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from erev_api.approvals.subjects import PERIOD_LINK
from erev_api.db.session import of_session_tenant
from erev_api.db.tables import app_user, job, period_lock
from erev_api.domain.reports import evidence_preparation
from erev_api.enums import NotificationKind
from erev_api.events.notifications import notify, role_holders
from erev_api.jobs.registry import handler_params
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def completed(uow: UnitOfWork, *, pack_id: UUID, preparation_id: UUID | None) -> None:
    """Called only for the RUNNING-to-SUCCEEDED transition, inside its transaction.

    Manual packs have no preparation parent and do not repeat the period's notification.
    The caller holds job/pack locks; retention and notification either both commit or neither.
    """
    if preparation_id is None:
        return
    parent = uow.session.execute(
        select(job.c.params, job.c.subject_id).where(
            of_session_tenant(job), job.c.id == preparation_id
        )
    ).one_or_none()
    if parent is None:
        raise Problem("validation-failed", "The automatic pack has no preparation job.")
    scope = evidence_preparation.selected_lock(
        uow.session, preparation_id, handler_params(parent.params)
    )
    if evidence_preparation.retained_pack(uow.session, preparation_id, scope) != pack_id:
        raise Problem(
            "validation-failed", "The automatic pack differs from its preparation result."
        )
    actor = uow.session.execute(
        select(app_user.c.display_name, period_lock.c.created_by_kind)
        .select_from(period_lock.outerjoin(app_user, app_user.c.id == period_lock.c.created_by))
        .where(of_session_tenant(period_lock), period_lock.c.id == scope.lock_id)
    ).one()
    name = actor.display_name or ("System" if actor.created_by_kind == "SYSTEM" else "A user")
    notify(
        uow,
        recipient_membership_ids=role_holders(
            uow.session,
            role_codes=("controller", "revenue_reviewer", "auditor"),
            entity_id=scope.entity_id,
            at=uow.now,
        ),
        kind=NotificationKind.PERIOD_LOCKED,
        title=f"{scope.entity_code} {scope.period_key} locked",
        body=(
            f"{name} locked {scope.period_key} for {scope.entity_code} in book {scope.book_code}. "
            "The evidence pack is available."
        ),
        link_path=PERIOD_LINK.format(state_id=parent.subject_id),
        # The immutable lock distinguishes successive closes within the merge window.
        subject_type="period_lock",
        subject_id=scope.lock_id,
    )
