"""Archive a source scenario without removing its sandbox's read access (SM-14)."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from erev_api.audit import chain, writer
from erev_api.auth.principal import Principal, RequestContext
from erev_api.db.session import DbContext, set_tenant_context, tenant_session
from erev_api.db.tables import job, scenario, scenario_refresh
from erev_api.domain.platform import actors
from erev_api.enums import PrincipalKind
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def _row(session: Session, scenario_id: UUID, *, lock: bool = False) -> Mapping[str, Any]:
    statement = select(
        *scenario.c,
        actors.named(scenario.c.created_by, tenant_id=scenario.c.tenant_id).label("creator_name"),
    ).where(scenario.c.id == scenario_id)
    if lock:
        statement = statement.with_for_update(key_share=True, of=scenario)
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return dict(row)


def authorize(principal: Principal, row: Mapping[str, Any]) -> None:
    if (
        principal.kind is not PrincipalKind.USER
        or principal.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden", "Scenario access across the workspace is required.")
    if row["created_by"] != principal.id and principal.role_scopes.get("controller") != "*":
        raise Problem("forbidden", "Only the scenario creator or a Controller can archive it.")


def authorize_replay(ctx: RequestContext, scenario_id: UUID) -> None:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        authorize(ctx.principal, _row(session, scenario_id))


def archive(uow: UnitOfWork, scenario_id: UUID, *, expected_version: int) -> Mapping[str, Any]:
    row = _row(uow.session, scenario_id, lock=True)
    authorize(uow.principal, row)
    if row["row_version"] != expected_version:
        raise Problem("precondition-failed", "The scenario changed; refresh it before archiving.")
    if row["status"] != "ACTIVE":
        raise Problem("invalid-transition", "The scenario is already archived.")
    if (
        uow.session.scalar(
            select(scenario_refresh.c.id).where(
                scenario_refresh.c.scenario_id == scenario_id,
                scenario_refresh.c.status.in_(("QUEUED", "RUNNING")),
            )
        )
        is not None
    ):
        raise Problem(
            "invalid-transition", "Finish or cancel the scenario refresh before archiving."
        )
    target_id = UUID(str(row["scenario_tenant_id"]))
    # This source-row lock waits for admitted sandbox command transactions, including enqueues.
    busy = uow.session.execute(
        select(job.c.id)
        .where(job.c.subject_id == target_id, job.c.state.in_(("QUEUED", "RUNNING")))
        .limit(1)
    ).first()
    target = DbContext(tenant_id=target_id, user_id=uow.principal.id, entity_scope="*")
    set_tenant_context(uow.session, target)
    try:
        busy_target = uow.session.execute(
            select(job.c.id).where(job.c.state.in_(("QUEUED", "RUNNING"))).limit(1)
        ).first()
    finally:
        set_tenant_context(uow.session, uow.principal.db_context)
    if busy is not None or busy_target is not None:
        raise Problem(
            "invalid-transition", "Finish or cancel the scenario's pending jobs before archiving."
        )
    uow.session.execute(
        update(scenario)
        .where(scenario.c.id == scenario_id)
        .values(
            status="ARCHIVED",
            updated_at=uow.now,
            updated_by=uow.principal.id,
            updated_by_kind="USER",
        )
    )
    uow.audit(
        action="scenario.archive",
        object_type="scenario",
        object_id=scenario_id,
        before={"status": "ACTIVE"},
        after={"status": "ARCHIVED"},
        detail={"scenario_tenant_id": str(target_id)},
    )
    event = writer.build_event(
        tenant_id=target_id,
        actor=writer.actor_of(uow.ctx),
        occurred_at=uow.now,
        action="scenario.archive",
        object_type="scenario",
        object_id=scenario_id,
        before={"status": "ACTIVE"},
        after={"status": "ARCHIVED"},
        detail={"source_tenant_id": str(uow.principal.tenant_id)},
    )

    def mirror() -> None:
        set_tenant_context(uow.session, target)
        try:
            chain.append_events(
                uow.session, tenant_id=target_id, keyring=uow.keyring, events=[event]
            )
        finally:
            set_tenant_context(uow.session, uow.principal.db_context)

    uow.before_commit(mirror)
    return _row(uow.session, scenario_id)
