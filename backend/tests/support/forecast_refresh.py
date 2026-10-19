"""Durable refresh reservation against a real source scenario and published inputs."""

from typing import Any
from uuid import UUID

import pytest
from erev_api.db.tables import forecast_event_set, scenario, scenario_refresh
from erev_api.domain.forecast import archive, refresh_state
from erev_api.domain.platform import snapshots
from erev_api.problems import Problem
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from support.factories import workspace
from support.principals import Actor


def exercise_refresh_state(world: Any, source_actor: Actor, scenario_id: UUID) -> None:
    input_id = world.place.scalar(
        select(forecast_event_set.c.id).where(forecast_event_set.c.code == "REPLAY_TXN")
    )
    source = workspace(
        world.app, world.place.clock, world.place.keyring, world.place.files, source_actor
    )
    with source.uow() as uow:
        current = dict(
            uow.session.execute(select(scenario).where(scenario.c.id == scenario_id))
            .mappings()
            .one()
        )
        snapshot, _job = snapshots.request_scenario_snapshot(
            uow,
            known_at=uow.now,
            name="Refresh reservation",
            scenario_request={
                "id": str(scenario_id),
                "name": current["name"],
                "purpose": current["purpose"],
                "requested_by": str(uow.principal.id),
            },
        )
        pending = refresh_state.reserve(
            uow,
            scenario_id=scenario_id,
            expected_version=current["row_version"],
            input_set_id=input_id,
            snapshot_id=snapshot["id"],
        )
        assert pending["source_tenant_id"] == world.place.principal.tenant_id
        assert pending["source_input_set_id"] == input_id
        assert pending["status"] == "QUEUED"
        with pytest.raises(Problem, match="pending refresh"):
            refresh_state.reserve(
                uow,
                scenario_id=scenario_id,
                expected_version=current["row_version"],
                input_set_id=input_id,
                snapshot_id=snapshot["id"],
            )
        with pytest.raises(Problem, match="refresh before archiving"):
            archive.archive(uow, scenario_id, expected_version=current["row_version"])
        running = refresh_state.start(uow, pending["id"])
        assert running["status"] == "RUNNING"
        assert refresh_state.start(uow, pending["id"])["started_at"] == running["started_at"]
        with pytest.raises(DBAPIError), uow.savepoint():
            uow.session.execute(
                update(scenario_refresh)
                .where(scenario_refresh.c.id == pending["id"])
                .values(source_content_sha256="0" * 64)
            )
        refresh_state.fail(uow, pending["id"], {"detail": "Fixture cancellation"})
        failed = refresh_state.row(uow, pending["id"])
        assert failed["status"] == "FAILED" and failed["finished_at"] is not None
        with pytest.raises(Problem, match="already finished"):
            refresh_state.start(uow, pending["id"])
        with pytest.raises(DBAPIError), uow.savepoint():
            uow.session.execute(
                update(scenario_refresh)
                .where(scenario_refresh.c.id == pending["id"])
                .values(problem={"detail": "changed"})
            )
        uow.commit()
