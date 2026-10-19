"""Execute a reserved refresh using the snapshot job's durable attempt."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from erev_api.controls.release import current_release
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import scenario_refresh, tenant
from erev_api.domain.forecast import completion, event_sets, refresh_state, replay, replay_inputs
from erev_api.domain.platform import sandboxes
from erev_api.jobs.context import JobContext, system_unit_of_work
from erev_api.jobs.registry import JobOutcome
from erev_api.problems import Problem


def find(jc: JobContext) -> dict[str, Any] | None:
    with jc.unit_of_work() as uow:
        found = (
            uow.session.execute(
                select(scenario_refresh).where(scenario_refresh.c.job_id == jc.job_id)
            )
            .mappings()
            .one_or_none()
        )
        return None if found is None else dict(found)


def result(current: Mapping[str, Any]) -> JobOutcome:
    return JobOutcome(
        state="SUCCEEDED",
        result={
            "scenario_id": str(current["scenario_id"]),
            "refresh_id": str(current["id"]),
            "sandbox_tenant_id": str(current["target_tenant_id"]),
            "forecast_event_set_id": str(current["target_input_set_id"]),
            "href": "/api/v1/scenarios",
        },
    )


def run(jc: JobContext, params: Mapping[str, Any], reserved: Mapping[str, Any]) -> JobOutcome:
    from erev_api.domain.platform import snapshot_job as snapshots

    if reserved["status"] == "SUCCEEDED":
        return result(reserved)
    actor = sandboxes.sandbox_actor(jc.tenant_id, reserved["created_by"], at=jc.clock.now())
    if (
        "scenario.use" not in actor.permissions
        or actor.permission_scopes.get("scenario.use") != "*"
    ):
        raise Problem("forbidden")
    with system_unit_of_work(jc.runtime, actor, request_id=f"job-{jc.job_id}-refresh-start") as uow:
        current = refresh_state.start(uow, reserved["id"])
        uow.commit()
    old_actor = sandboxes.sandbox_actor(current["source_tenant_id"], actor.id, at=jc.clock.now())
    with system_unit_of_work(
        jc.runtime, old_actor, request_id=f"job-{jc.job_id}-refresh-inputs"
    ) as uow:
        inputs = replay_inputs.load(uow, current["source_input_set_id"])
        metadata = event_sets._row(uow.session, current["source_input_set_id"])
        if inputs.content_sha256 != current["source_content_sha256"]:
            raise Problem("precondition-failed", "The selected forecast publication changed.")
    parsed = snapshots.parse_params(params)
    load = sandboxes.parse_load(params)
    if (
        load is None
        or load.requested_by != actor.id
        or parsed.purpose != "SANDBOX_COPY"
        or load.sandbox_tenant_id != current["target_tenant_id"]
        or parsed.tenant_snapshot_id != current["tenant_snapshot_id"]
    ):
        raise Problem("precondition-failed", "The refresh job does not match its reservation.")
    from erev_api.domain.forecast import actuals_retention

    actuals_retention.retain(
        jc, snapshot_id=parsed.tenant_snapshot_id, requested_by=actor.id, known_at=parsed.known_at
    )
    with jc.unit_of_work() as uow:
        resolution = snapshots.retention_policy_for(uow.session, parsed.known_at)
        reader = snapshots.DbSnapshotReader(
            uow.principal.db_context,
            engine_release=snapshots.engine_release_of(current_release()),
            retention=resolution.policy,
            retention_refusal=resolution.refusal,
            retention_unset=resolution.unset,
        )
        snapshots.export_snapshot(
            snapshots.DbSnapshotRepository(uow),
            reader,
            snapshots.writer_for(uow),
            params=parsed,
            heartbeat=jc.heartbeat,
        )
        uow.commit()
    target_context = DbContext(tenant_id=load.sandbox_tenant_id, user_id=None, entity_scope="*")
    with tenant_session(target_context, read_only=True) as session:
        existing = (
            session.execute(select(tenant).where(tenant.c.id == load.sandbox_tenant_id))
            .mappings()
            .one_or_none()
        )
        held = (
            None
            if existing is None
            else sandboxes.sandbox_load_of(session, dict(existing), awaiting_forecast=True)
        )
        if existing is not None and (
            existing["status"] != "SUSPENDED"
            or held is None
            or held["tenant_snapshot_id"] != parsed.tenant_snapshot_id
        ):
            raise Problem(
                "precondition-failed", "The previous refresh copy did not finish loading."
            )
    if existing is None:
        sandboxes.load_sandbox(
            jc,
            snapshot_id=parsed.tenant_snapshot_id,
            load=load,
            heartbeat=jc.heartbeat,
            scenario_creator=actor.id,
            defer_activation=True,
        )
    target_actor = sandboxes.sandbox_actor(load.sandbox_tenant_id, actor.id, at=jc.clock.now())
    with system_unit_of_work(
        jc.runtime, target_actor, request_id=f"job-{jc.job_id}-refresh-replay"
    ) as uow:
        sandboxes.require_point_in_time(uow.session, load.sandbox_tenant_id)
        target = event_sets.create(
            uow, {key: metadata[key] for key in ("code", "name", "effective_from", "effective_to")}
        )
        published = replay.apply(uow, inputs, target_set_id=target["id"], heartbeat=jc.heartbeat)
        completion.complete(
            uow,
            source_tenant_id=jc.tenant_id,
            refresh_id=current["id"],
            job_id=jc.job_id,
            input_set_id=target["id"],
            content_sha256=published["content_sha256"],
        )
        uow.commit()
    return result({**current, "target_input_set_id": target["id"]})
