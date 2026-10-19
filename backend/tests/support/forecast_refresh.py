"""Durable refresh reservation against a real source scenario and published inputs."""

from typing import Any
from uuid import UUID

import pytest
from erev_api.db.tables import forecast_event_set, forecast_run, scenario, scenario_refresh
from erev_api.domain.forecast import archive, refresh_state
from erev_api.domain.platform import snapshots
from erev_api.problems import Problem
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from support.factories import workspace
from support.principals import Actor


def exercise_refresh_state(world: Any, source_actor: Actor, scenario_id: UUID) -> None:
    saved_run_id = world.place.scalar(
        select(forecast_run.c.id).where(forecast_run.c.status == "SUCCEEDED").limit(1)
    )
    assert saved_run_id is not None
    input_id = world.place.scalar(
        select(forecast_event_set.c.id).where(forecast_event_set.c.code == "REPLAY_TXN")
    )
    source = workspace(
        world.app, world.place.clock, world.place.keyring, world.place.files, source_actor
    )
    from erev_api.db.tables import legal_entity
    from erev_api.domain.reports import forecast_actuals
    from erev_api.domain.reports.builders import ReportParams

    with source.uow() as uow:
        actual_params = ReportParams(
            report_code="actual_vs_forecast",
            report_version=1,
            parameters={},
            entity_ids=tuple(uow.session.scalars(select(legal_entity.c.id))),
            known_at=uow.now,
            book_code="ASC606",
            historical=True,
        )
        actuals = forecast_actuals.capture(uow, actual_params)
        assert actuals["rows"] == []  # Scenario forecasts do not become production postings.
        assert actuals["source_tenant_id"] == str(source.principal.tenant_id)
        assert actuals["known_at"] == uow.now.isoformat()
    with world.place.uow() as uow:
        from dataclasses import replace

        from erev_api.enums import TenantKind

        uow.ctx = replace(uow.ctx, tenant_kind=TenantKind.SANDBOX)
        with pytest.raises(Problem):
            forecast_actuals.capture(uow, actual_params)

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

    from unittest.mock import patch

    from erev_api.db.session import DbContext, tenant_session
    from erev_api.db.tables import job, tenant
    from erev_api.domain.forecast import completion
    from erev_api.jobs import registry
    from erev_api.jobs.context import JobRuntime
    from sqlalchemy import text

    runtime = JobRuntime(
        clock=world.place.clock, keyring=world.place.keyring, files=world.place.files
    )
    old_target = world.place.principal.tenant_id
    for fail_completion in (True, False):
        from support.http import call
        from support.principals import cookie_headers

        with source.uow() as uow:
            current = archive._row(uow.session, scenario_id)
        headers = cookie_headers(source_actor.token, source_actor.csrf_token)
        headers["If-Match"] = f'"r{current["row_version"]}"'
        response = call(
            world.app,
            "POST",
            f"/api/v1/scenarios/{scenario_id}/refresh",
            headers=headers,
            json={"forecast_event_set_id": str(input_id)},
        )
        assert response.status_code == 202, response.text
        retried = call(
            world.app,
            "POST",
            f"/api/v1/scenarios/{scenario_id}/refresh",
            headers=headers,
            json={"forecast_event_set_id": str(input_id)},
        )
        assert retried.status_code == 202 and retried.json() == response.json()
        requested_id = UUID(response.json()["id"])
        snapshot_id = UUID(response.json()["tenant_snapshot_id"])
        with source.uow() as uow:
            pending = refresh_state.row(uow, UUID(response.json()["refresh_id"]))
            queued = (
                uow.session.execute(select(job).where(job.c.id == requested_id)).mappings().one()
            )
            uow.session.execute(
                text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"),
                {"id": queued["procrastinate_job_id"]},
            )
            uow.commit()
        if fail_completion:
            with patch.object(
                completion,
                "complete",
                side_effect=Problem("precondition-failed", "Injected completion failure"),
            ):
                registry.run_job(
                    requested_id, source.principal.tenant_id, attempt=1, runtime=runtime
                )
        else:
            registry.run_job(requested_id, source.principal.tenant_id, attempt=1, runtime=runtime)
        with source.uow() as uow:
            refreshed = refresh_state.row(uow, pending["id"])
            current = archive._row(uow.session, scenario_id)
            job_row = (
                uow.session.execute(select(job).where(job.c.id == requested_id)).mappings().one()
            )
            assert job_row["state"] == ("FAILED" if fail_completion else "SUCCEEDED"), job_row[
                "problem"
            ]
            assert refreshed["status"] == ("FAILED" if fail_completion else "SUCCEEDED")
            import hashlib
            import json

            from erev_api.db.tables import forecast_actuals_capture
            from erev_api.files.store import open_file

            retained = (
                uow.session.execute(
                    select(forecast_actuals_capture).where(
                        forecast_actuals_capture.c.tenant_snapshot_id == snapshot_id,
                    )
                )
                .mappings()
                .one()
            )
            _, stream = open_file(
                uow.session, retained["dataset_file_id"], files=uow.files, keyring=uow.keyring
            )
            with stream:
                content = stream.read()
            assert hashlib.sha256(content).hexdigest() == retained["dataset_sha256"]
            actuals_document = json.loads(content)
            assert actuals_document["tenant_snapshot_id"] == str(snapshot_id)
            assert set(actuals_document["books"]) == {"ASC606", "IFRS15"}
            assert all(book["rows"] == [] for book in actuals_document["books"].values())
            with pytest.raises(DBAPIError), uow.savepoint():
                uow.session.execute(
                    update(forecast_actuals_capture)
                    .where(
                        forecast_actuals_capture.c.id == retained["id"],
                    )
                    .values(dataset_sha256="0" * 64)
                )
            assert current["scenario_tenant_id"] == (
                old_target if fail_completion else pending["target_tenant_id"]
            )
            if not fail_completion:
                assert current["last_refreshed_at"] is not None
                assert current["tenant_snapshot_id"] == snapshot_id
        with tenant_session(
            DbContext(tenant_id=pending["target_tenant_id"], user_id=None, entity_scope="*")
        ) as session:
            assert session.scalar(
                select(tenant.c.status).where(tenant.c.id == pending["target_tenant_id"])
            ) == ("ARCHIVED" if fail_completion else "ACTIVE")
            if not fail_completion:
                inputs = (
                    session.execute(
                        select(forecast_event_set).where(
                            forecast_event_set.c.id == refreshed["target_input_set_id"]
                        )
                    )
                    .mappings()
                    .one()
                )
                assert inputs["status"] == "PUBLISHED"
                assert inputs["production_scenario_id"] == scenario_id
                assert [step["kind"] for step in inputs["input_sequence"]] == [
                    "API_COMMAND",
                    "IMPORT_UPLOAD",
                    "API_COMMAND",
                ]
        with tenant_session(
            DbContext(tenant_id=old_target, user_id=None, entity_scope="*")
        ) as session:
            assert session.scalar(select(tenant.c.status).where(tenant.c.id == old_target)) == (
                "ACTIVE" if fail_completion else "ARCHIVED"
            )

    from erev_api.db.scenario_writes import require_writable
    from erev_api.domain.platform.snapshot_job import snapshot_cancel_guard

    with tenant_session(DbContext(tenant_id=old_target, user_id=None, entity_scope="*")) as session:
        with pytest.raises(Problem, match="archived and read-only"):
            require_writable(
                session, DbContext(tenant_id=old_target, user_id=None, entity_scope="*")
            )
    with source.uow() as uow:
        with pytest.raises(Problem, match="already completed"):
            snapshot_cancel_guard(uow, {}, requested_id)

    with source.uow() as uow:
        current = archive._row(uow.session, scenario_id)
    headers = cookie_headers(source_actor.token, source_actor.csrf_token)
    headers["If-Match"] = f'"r{current["row_version"]}"'
    queued_refresh = call(
        world.app,
        "POST",
        f"/api/v1/scenarios/{scenario_id}/refresh",
        headers=headers,
        json={"forecast_event_set_id": str(refreshed["target_input_set_id"])},
    )
    assert queued_refresh.status_code == 202, queued_refresh.text
    cancelled = call(
        world.app,
        "POST",
        f"/api/v1/jobs/{queued_refresh.json()['id']}/cancel",
        headers=cookie_headers(source_actor.token, source_actor.csrf_token),
    )
    assert cancelled.status_code == 200, cancelled.text
    with source.uow() as uow:
        cancelled_state = refresh_state.row(uow, UUID(queued_refresh.json()["refresh_id"]))
        assert cancelled_state["status"] == "FAILED"
        assert (
            archive._row(uow.session, scenario_id)["scenario_tenant_id"]
            == current["scenario_tenant_id"]
        )

    # A refreshed workspace resolves its old saved forecast through successful lineage only.
    from erev_api.domain.forecast import history
    from erev_api.domain.platform import sandboxes
    from erev_api.jobs.context import system_unit_of_work

    actor = sandboxes.sandbox_actor(
        refreshed["target_tenant_id"], source.principal.id, at=world.place.clock.now()
    )
    with system_unit_of_work(runtime, actor, request_id="forecast-history") as uow:
        saved = history.resolve(uow, saved_run_id)
        assert saved.forecast_tenant_id == old_target
        assert saved.scenario_id == scenario_id
        assert saved.source_tenant_id == source.principal.tenant_id
        assert saved.actuals_cutoff == current["base_known_at"]
        assert saved.last_refreshed_at == current["last_refreshed_at"]
        from erev_api.domain.reports import forecast_saved

        revenue = forecast_saved.read(uow, saved_run_id)
        assert revenue.forecast.forecast_tenant_id == old_target
        assert any(column["key"].startswith("period:") for column in revenue.revenue["columns"])
        assert "sections" not in revenue.revenue
        from erev_api.domain.reports.forecast_dimensions import forecast_rows

        projected = forecast_rows(revenue, require_category=True)
        assert projected
        assert {str(row.entity_id) for row in projected} <= set(
            saved.run["parameters"]["entity_ids"]
        )
        assert {row.period_key for row in projected} <= set(
            saved.run["parameters"]["horizon_periods"]
        )
        from erev_api.domain.reports import forecast_actuals_saved

        actuals = forecast_actuals_saved.read(uow, saved_run_id)
        assert actuals.rows == ()
        assert actuals.forecast.actuals_snapshot_id == snapshot_id
        assert actuals.forecast.actuals_cutoff == saved.actuals_cutoff
        assert actuals.dataset_sha256 == retained["dataset_sha256"]
        assert uow.session.scalar(text("SELECT current_setting('app.tenant_id')")) == str(
            actor.tenant_id
        )
        with pytest.raises(Problem):
            history.resolve(uow, UUID(int=999))
        assert uow.session.scalar(text("SELECT current_setting('app.tenant_id')")) == str(
            actor.tenant_id
        )

        from dataclasses import replace

        uow.ctx = replace(
            uow.ctx, principal=replace(actor, permission_scopes={"scenario.use": "*"})
        )
        with pytest.raises(Problem):
            history.resolve(uow, saved_run_id)
        with pytest.raises(Problem):
            forecast_actuals_saved.read(uow, saved_run_id)
        assert uow.session.scalar(text("SELECT current_setting('app.tenant_id')")) == str(
            actor.tenant_id
        )
