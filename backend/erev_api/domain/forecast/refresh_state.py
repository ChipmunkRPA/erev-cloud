"""Production-side durable identity and admission of a scenario refresh."""

from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import insert, select

from erev_api.db import new_id
from erev_api.db.session import DbContext, set_tenant_context
from erev_api.db.tables import forecast_event_set, job, scenario_refresh, tenant_snapshot
from erev_api.db.transitions import apply
from erev_api.domain.forecast import archive, input_order
from erev_api.domain.platform import sandboxes
from erev_api.enums import PrincipalKind
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


def reserve(
    uow: UnitOfWork,
    *,
    scenario_id: UUID,
    expected_version: int,
    input_set_id: UUID,
    snapshot_id: UUID,
) -> dict[str, Any]:
    """Bind an enqueued fresh-copy job in its request transaction; only one refresh may run.

    The request handler must enqueue the snapshot and reserve together. It may not enqueue
    another job after this function returns. The worker reauthorizes and reads the retained
    input bytes separately before applying them to the held target.
    """
    actor = uow.principal
    if (
        actor.kind is not PrincipalKind.USER
        or "scenario.use" not in actor.permissions
        or actor.id is None
        or actor.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    source = archive._row(uow.session, scenario_id, lock=True)
    if source["status"] != "ACTIVE" or source["row_version"] != expected_version:
        raise Problem("precondition-failed", "The scenario changed before refresh was requested.")
    if (
        uow.session.scalar(
            select(scenario_refresh.c.id).where(
                scenario_refresh.c.scenario_id == scenario_id,
                scenario_refresh.c.status.in_(("QUEUED", "RUNNING")),
            )
        )
        is not None
    ):
        raise Problem("invalid-transition", "This scenario already has a pending refresh.")
    snapshot = (
        uow.session.execute(select(tenant_snapshot).where(tenant_snapshot.c.id == snapshot_id))
        .mappings()
        .one_or_none()
    )
    queued = (
        None
        if snapshot is None
        else uow.session.execute(select(job).where(job.c.id == snapshot["job_id"]))
        .mappings()
        .one_or_none()
    )
    load = None if queued is None else sandboxes.parse_load(queued["params"])
    if (
        snapshot is None
        or snapshot["status"] != "QUEUED"
        or snapshot["purpose"] != "SANDBOX_COPY"
        or queued is None
        or queued["state"] != "QUEUED"
        or queued["kind"] != "TENANT_SNAPSHOT"
        or load is None
        or load.requested_by != actor.id
        or queued["params"].get("scenario", {}).get("id") != str(scenario_id)
        or queued["subject_id"] != load.sandbox_tenant_id
        or load.sandbox_tenant_id == source["scenario_tenant_id"]
    ):
        raise Problem(
            "precondition-failed", "The refresh needs its requester's queued scenario copy."
        )
    old_target = UUID(str(source["scenario_tenant_id"]))
    set_tenant_context(
        uow.session, DbContext(tenant_id=old_target, user_id=actor.id, entity_scope="*")
    )
    try:
        found = (
            uow.session.execute(
                select(forecast_event_set).where(forecast_event_set.c.id == input_set_id)
            )
            .mappings()
            .one_or_none()
        )
        inputs = None if found is None else dict(found)
    finally:
        set_tenant_context(uow.session, actor.db_context)
    if (
        inputs is None
        or inputs["production_scenario_id"] != scenario_id
        or inputs["status"] != "PUBLISHED"
    ):
        raise Problem(
            "precondition-failed", "Choose a published input set of the current scenario."
        )
    input_order.sequence(inputs)
    if sha256_hex(input_order.content(inputs)) != inputs["content_sha256"]:
        raise Problem("precondition-failed", "The published forecast input hash does not match.")
    identity = new_id()
    values = {
        "tenant_id": actor.tenant_id,
        "id": identity,
        "scenario_id": scenario_id,
        "source_tenant_id": old_target,
        "source_input_set_id": input_set_id,
        "source_content_sha256": inputs["content_sha256"],
        "target_tenant_id": load.sandbox_tenant_id,
        "tenant_snapshot_id": snapshot_id,
        "job_id": queued["id"],
        "status": "QUEUED",
        "created_at": uow.now,
        "created_by": actor.id,
        "created_by_kind": actor.kind.value,
        "updated_at": uow.now,
        "updated_by": actor.id,
        "updated_by_kind": actor.kind.value,
    }
    uow.session.execute(insert(scenario_refresh).values(**values))
    uow.audit(
        action="scenario.refresh_requested",
        object_type="scenario",
        object_id=scenario_id,
        detail={
            key: str(values[key])
            for key in (
                "id",
                "source_tenant_id",
                "source_input_set_id",
                "source_content_sha256",
                "target_tenant_id",
                "tenant_snapshot_id",
                "job_id",
            )
        },
    )
    return row(uow, identity)


def row(uow: UnitOfWork, identity: UUID) -> dict[str, Any]:
    found = (
        uow.session.execute(
            select(scenario_refresh).where(scenario_refresh.c.id == identity).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if found is None:
        raise Problem("not-found")
    return dict(found)


def start(uow: UnitOfWork, identity: UUID) -> dict[str, Any]:
    # Match reservation/completion lock order: source scenario before refresh state.
    scenario_id = uow.session.scalar(
        select(scenario_refresh.c.scenario_id).where(scenario_refresh.c.id == identity)
    )
    if scenario_id is None:
        raise Problem("not-found")
    source = archive._row(uow.session, scenario_id, lock=True)
    current = row(uow, identity)
    if source["status"] != "ACTIVE" or source["scenario_tenant_id"] != current["source_tenant_id"]:
        raise Problem(
            "precondition-failed", "The source scenario changed before refresh execution."
        )
    if current["status"] == "RUNNING":
        return current
    if current["status"] != "QUEUED":
        raise Problem("invalid-transition", "The refresh is already finished.")
    apply(
        uow.session,
        "scenario_refresh",
        identity,
        to_status="RUNNING",
        expected_status="QUEUED",
        set_values={"started_at": uow.now},
    )
    uow.audit(action="scenario.refresh_started", object_type="scenario_refresh", object_id=identity)
    return row(uow, identity)


def fail(uow: UnitOfWork, identity: UUID, problem: dict[str, Any]) -> None:
    current = row(uow, identity)
    if current["status"] in {"FAILED", "SUCCEEDED"}:
        return
    apply(
        uow.session,
        "scenario_refresh",
        identity,
        to_status="FAILED",
        expected_status=current["status"],
        set_values={"finished_at": uow.now, "problem": problem},
    )
    uow.audit(
        action="scenario.refresh_failed",
        object_type="scenario_refresh",
        object_id=identity,
        detail={"problem": problem},
    )
