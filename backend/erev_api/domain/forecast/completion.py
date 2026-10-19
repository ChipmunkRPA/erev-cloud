"""Atomic source pointer replacement, target activation and old-copy retirement."""

from uuid import UUID

from sqlalchemy import select, update

from erev_api.audit import chain, writer
from erev_api.db.session import DbContext, set_tenant_context
from erev_api.db.tables import tenant, tenant_snapshot
from erev_api.db.transitions import apply
from erev_api.domain.forecast import activation, archive, refresh_state
from erev_api.domain.platform import sandboxes
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def complete(
    uow: UnitOfWork,
    *,
    source_tenant_id: UUID,
    refresh_id: UUID,
    job_id: UUID,
    input_set_id: UUID,
    content_sha256: str,
) -> None:
    """Run in the target replay transaction. No intermediate pointer/status is committed."""
    actor = uow.principal
    if actor.id is None:
        raise Problem("forbidden")
    source_actor = sandboxes.sandbox_actor(source_tenant_id, actor.id, at=uow.now)
    if (
        "scenario.use" not in source_actor.permissions
        or source_actor.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    source_context = source_actor.db_context
    set_tenant_context(uow.session, source_context)
    try:
        current = refresh_state.start(uow, refresh_id)
        source = archive._row(uow.session, current["scenario_id"], lock=True)
        snapshot = (
            uow.session.execute(
                select(tenant_snapshot).where(tenant_snapshot.c.id == current["tenant_snapshot_id"])
            )
            .mappings()
            .one()
        )
        if (
            current["job_id"] != job_id
            or current["target_tenant_id"] != actor.tenant_id
            or current["created_by"] != actor.id
            or snapshot["status"] != "SUCCEEDED"
            or snapshot["target_tenant_id"] != actor.tenant_id
        ):
            raise Problem("precondition-failed", "The refresh completion does not match its copy.")
    finally:
        set_tenant_context(uow.session, actor.db_context)
    activation.activate(
        uow,
        snapshot_id=current["tenant_snapshot_id"],
        input_set_id=input_set_id,
        content_sha256=content_sha256,
    )
    old_context = DbContext(
        tenant_id=current["source_tenant_id"], user_id=actor.id, entity_scope="*"
    )
    set_tenant_context(uow.session, old_context)
    try:
        retired = uow.session.execute(
            update(tenant)
            .where(
                tenant.c.id == current["source_tenant_id"],
                tenant.c.kind == "sandbox",
                tenant.c.status == "ACTIVE",
                tenant.c.source_tenant_id == source_tenant_id,
            )
            .values(
                status="ARCHIVED",
                updated_at=uow.now,
                updated_by=actor.id,
                updated_by_kind=actor.kind.value,
            )
            .returning(tenant.c.id)
        ).first()
        if retired is None:
            raise Problem("precondition-failed", "The old forecast workspace cannot be retired.")
    finally:
        set_tenant_context(uow.session, actor.db_context)
    set_tenant_context(uow.session, source_context)
    try:
        apply(
            uow.session,
            "scenario",
            source["id"],
            to_status=None,
            set_values={
                "scenario_tenant_id": actor.tenant_id,
                "tenant_snapshot_id": snapshot["id"],
                "base_known_at": snapshot["known_at"],
                "last_refreshed_at": uow.now,
                "updated_by": actor.id,
                "updated_by_kind": actor.kind.value,
            },
        )
        apply(
            uow.session,
            "scenario_refresh",
            refresh_id,
            to_status="SUCCEEDED",
            expected_status="RUNNING",
            set_values={
                "target_input_set_id": input_set_id,
                "target_content_sha256": content_sha256,
                "finished_at": uow.now,
                "updated_by": actor.id,
                "updated_by_kind": actor.kind.value,
            },
        )
    finally:
        set_tenant_context(uow.session, actor.db_context)
    detail = {
        "refresh_id": str(refresh_id),
        "old_tenant_id": str(current["source_tenant_id"]),
        "new_tenant_id": str(actor.tenant_id),
        "input_set_id": str(input_set_id),
        "content_sha256": content_sha256,
        "tenant_snapshot_id": str(snapshot["id"]),
    }
    uow.audit(
        action="scenario.refresh_completed",
        object_type="scenario",
        object_id=source["id"],
        detail=detail,
    )
    mirrors = [
        (
            context,
            writer.build_event(
                tenant_id=context.tenant_id,
                actor=writer.actor_of(uow.ctx),
                occurred_at=uow.now,
                action="scenario.refresh_completed",
                object_type="scenario",
                object_id=source["id"],
                detail=detail,
            ),
        )
        for context in (source_context, old_context)
    ]

    def mirror() -> None:
        try:
            for context, event in mirrors:
                set_tenant_context(uow.session, context)
                chain.append_events(
                    uow.session, tenant_id=context.tenant_id, keyring=uow.keyring, events=[event]
                )
        finally:
            set_tenant_context(uow.session, actor.db_context)

    uow.before_commit(mirror)
