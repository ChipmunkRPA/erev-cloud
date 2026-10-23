"""Five forecast sections read real computed scenario sources at one cutoff."""

from dataclasses import replace
from typing import Any

from erev_api.db.tables import contract, forecast_event_set
from erev_api.domain.reports import forecast_capture
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.forecast_exports import Identity, render
from erev_api.domain.reports.outputs import RunStamp
from erev_api.enums import TenantKind
from sqlalchemy import func, select


def exercise_capture(world: Any, source_actor: Any) -> None:
    with world.place.uow() as uow:
        uow.ctx = replace(uow.ctx, tenant_kind=TenantKind.SANDBOX)
        entities = tuple(uow.session.scalars(select(contract.c.contracting_entity_id).distinct()))
        cutoff = max(uow.now, uow.session.scalar(select(func.clock_timestamp())))
        params = ReportParams(
            report_code="forecast_outputs",
            report_version=1,
            parameters={},
            entity_ids=entities,
            known_at=cutoff,
            book_code="ASC606",
            output_format="JSON",
        )
        result = forecast_capture.capture(
            uow,
            params,
            horizon=("FY2026-P06", "FY2026-P07"),
        )
        assert [s.key for s in result.sections] == [
            "revenue",
            "billing",
            "balances",
            "rpo",
            "journals",
        ]
        assert all(not section.data.tie_out_results for section in result.sections)
        assert result.sections[0].data.rows
        assert result.sections[2].data.rows
        assert result.sections[4].data.rows
        assert all(source.cutoff == cutoff for source in result.sources.values())
        balance_keys = [key for key in result.sources if key.startswith("balances:")]
        assert len(balance_keys) == 2 * len(entities)
        assert all("section" not in row for row in result.sections[3].data.rows)
        publication = (
            uow.session.execute(
                select(forecast_event_set).where(
                    forecast_event_set.c.code == "REPLAY_TXN",
                )
            )
            .mappings()
            .one()
        )
        identity = Identity(
            publication["production_scenario_id"],
            "Scenario capture",
            publication["id"],
            publication["name"],
            publication["version_no"],
            publication["content_sha256"],
        )
        stamp = RunStamp(
            "forecast_outputs",
            "Forecast outputs",
            1,
            "RPT-CAPTURE",
            {},
            result.entity_codes,
            result.book,
            None,
            "Scenario",
            "test",
            "test",
            "Scenario requester",
            cutoff,
            "",
        )
        exported = render(result, identity, stamp, format="JSON")
        assert exported.content == exported.dataset
        assert b'"source_evidence_sha256"' in exported.content
        from unittest.mock import patch
        from uuid import uuid4

        import pytest
        from erev_api.db.tables import file_object, forecast_run, report_run
        from erev_api.db.transitions import apply
        from erev_api.domain.reports import forecast_publication, framework
        from erev_api.problems import Problem
        from sqlalchemy import insert

        parent_id = uuid4()
        uow.session.execute(
            insert(forecast_run).values(
                tenant_id=uow.principal.tenant_id,
                id=parent_id,
                forecast_event_set_id=publication["id"],
                status="QUEUED",
                parameters={
                    "entity_ids": [str(e) for e in entities],
                    "book_code": "ASC606",
                    "horizon_periods": ["FY2026-P06", "FY2026-P07"],
                },
                **framework._stamp(uow),
            )
        )
        apply(
            uow.session,
            "forecast_run",
            parent_id,
            to_status="RUNNING",
            expected_status="QUEUED",
            set_values={"started_at": uow.now},
        )
        prior_reports = uow.session.scalar(select(func.count()).select_from(report_run))
        prior_files = uow.session.scalar(select(func.count()).select_from(file_object))
        store = framework._store

        def fail_after_store(*args, **kwargs):
            store(*args, **kwargs)
            raise RuntimeError("publication failure")

        with patch.object(framework, "_store", fail_after_store), pytest.raises(RuntimeError):
            forecast_publication.publish(uow, parent_id, result, identity)
        assert uow.session.scalar(select(func.count()).select_from(report_run)) == prior_reports
        assert uow.session.scalar(select(func.count()).select_from(file_object)) == prior_files
        saved_id = forecast_publication.publish(uow, parent_id, result, identity)
        assert uow.session.scalar(
            select(forecast_run.c.report_run_ids).where(forecast_run.c.id == parent_id)
        ) == [saved_id]
        with pytest.raises(Problem, match="already published"):
            forecast_publication.publish(uow, parent_id, result, identity)
        downloads = {}
        for output_format in ("CSV", "XLSX"):
            formatted = forecast_capture.capture(
                uow,
                replace(params, output_format=output_format),
                horizon=("FY2026-P06", "FY2026-P07"),
            )
            downloads[output_format] = forecast_publication.publish(
                uow,
                parent_id,
                formatted,
                identity,
            )
        apply(
            uow.session,
            "forecast_run",
            parent_id,
            to_status="SUCCEEDED",
            expected_status="RUNNING",
            set_values={"finished_at": uow.now},
        )
        context = uow.ctx
        uow.commit()
    document = framework.run_document(
        context, saved_id, files=world.place.files, keyring=world.place.keyring
    )
    assert len(document["sections"]) == 5
    assert document["parameters"]["forecast_run_id"] == str(parent_id)
    assert document["event_set"]["sha256"] == identity.event_set_sha256
    import hashlib
    import json
    from uuid import UUID

    from erev_api.db.tables import report_run
    from erev_api.domain.forecast import history
    from erev_api.domain.reports import forecast_catalogue, forecast_saved
    from erev_api.files.store import open_file

    with world.place.uow() as uow:
        uow.ctx = replace(uow.ctx, tenant_kind=TenantKind.SANDBOX)
        saved = history.resolve(uow, parent_id)
        for output_id in [saved_id, *downloads.values()]:
            output_row = (
                uow.session.execute(select(report_run).where(report_run.c.id == output_id))
                .mappings()
                .one()
            )
            evidence = output_row["source_binding"]["evidence"]
            _, stream = open_file(
                uow.session,
                UUID(evidence["forecast_dataset_file_id"]),
                files=uow.files,
                keyring=uow.keyring,
            )
            with stream:
                retained = stream.read()
            assert hashlib.sha256(retained).hexdigest() == output_row["output_sha256"]
            assert forecast_saved._revenue(json.loads(retained), saved, evidence)["rows"]
            assert forecast_catalogue.document_for_run(uow, dict(output_row)) == json.loads(
                retained
            )
            pending = {
                **dict(output_row),
                "status": "QUEUED",
                "source_binding": None,
            }
            values = forecast_catalogue.prepare(uow, pending)
            bound = {**pending, **values}
            export_stamp = replace(
                stamp,
                parameters=values["parameters"],
                entity_codes=tuple(values["parameters"]["entity_codes"]),
                report_run_no="RPT-REEXPORT",
            )
            reexport = forecast_catalogue.render(uow, bound, export_stamp)
            assert reexport.dataset == retained
            assert reexport.dataset_sha256 == output_row["output_sha256"]
            with pytest.raises(Problem, match="differs"):
                forecast_catalogue.read(uow, {**bound, "output_format": "PDF"})
    from support.http import call
    from support.principals import cookie_headers

    response = call(
        world.app,
        "GET",
        f"/api/v1/report-runs/{saved_id}/data",
        headers=cookie_headers(world.place.author.token, key=False),
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["sections"]) == 5
    assert response.json()["forecast"]["event_set_name"] == identity.event_set_name
    csv_file = framework.open_output(
        context,
        downloads["CSV"],
        part="output",
        files=world.place.files,
        keyring=world.place.keyring,
    )
    assert csv_file.file_name.endswith(".zip") and csv_file.media_type == "application/zip"
    csv_file.stream.close()
    manifest_file = framework.open_output(
        context,
        downloads["CSV"],
        part="manifest",
        files=world.place.files,
        keyring=world.place.keyring,
    )
    assert manifest_file.file_name.endswith(".zip.manifest.json")
    manifest_file.stream.close()
    from erev_api.db.session import tenant_session
    from erev_api.db.tables import job
    from erev_api.domain.forecast import run_job
    from erev_api.jobs import registry
    from erev_api.jobs.context import JobRuntime
    from sqlalchemy import text

    body = {
        "forecast_event_set_id": str(publication["id"]),
        "parameters": {
            "horizon_periods": ["FY2026-P06", "FY2026-P07"],
            "entity_ids": [str(e) for e in entities],
            "book_code": "ASC606",
            "output_formats": ["JSON", "XLSX", "CSV"],
        },
    }
    headers = cookie_headers(world.place.author.token, world.place.author.csrf_token)
    requested = call(world.app, "POST", "/api/v1/forecast-runs", headers=headers, json=body)
    assert requested.status_code == 202, requested.text
    assert (
        call(world.app, "POST", "/api/v1/forecast-runs", headers=headers, json=body).json()
        == requested.json()
    )
    from uuid import UUID

    job_id = UUID(requested.json()["id"])
    requested_id = UUID(requested.json()["forecast_run_id"])
    with tenant_session(world.place.principal.db_context) as session:
        queued = session.execute(select(job).where(job.c.id == job_id)).mappings().one()
        session.execute(
            text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"),
            {"id": queued["procrastinate_job_id"]},
        )
    registry.run_job(
        job_id,
        world.place.tenant_id,
        attempt=1,
        runtime=JobRuntime(
            clock=world.place.clock, keyring=world.place.keyring, files=world.place.files
        ),
    )
    done = call(
        world.app,
        "GET",
        f"/api/v1/forecast-runs/{requested_id}",
        headers=cookie_headers(world.place.author.token, key=False),
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "SUCCEEDED", done.text
    assert len(done.json()["report_run_ids"]) == 3
    # Public catalogue creation and ordinary REPORT_RUN worker retain the forecast dataset.
    for output_format in ("JSON", "CSV", "XLSX"):
        requested_report = call(
            world.app,
            "POST",
            "/api/v1/report-runs",
            headers=cookie_headers(world.place.author.token, world.place.author.csrf_token),
            json={
                "report_code": "forecast_outputs",
                "output_format": output_format,
                "parameters": {
                    "forecast_run_id": str(parent_id),
                    "book": "ASC606",
                    "entity_codes": list(document["entity_codes"]),
                },
            },
        )
        assert requested_report.status_code == 202, requested_report.text
        report_job_id = UUID(requested_report.json()["id"])
        with tenant_session(world.place.principal.db_context) as session:
            queued_report = (
                session.execute(select(job).where(job.c.id == report_job_id)).mappings().one()
            )
            catalogue_id = queued_report["subject_id"]
            session.execute(
                text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"),
                {"id": queued_report["procrastinate_job_id"]},
            )
        registry.run_job(
            report_job_id,
            world.place.tenant_id,
            attempt=1,
            runtime=JobRuntime(
                clock=world.place.clock, keyring=world.place.keyring, files=world.place.files
            ),
        )
        response = call(
            world.app,
            "GET",
            f"/api/v1/report-runs/{catalogue_id}",
            headers=cookie_headers(world.place.author.token, key=False),
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "SUCCEEDED", response.text
        preview = call(
            world.app,
            "GET",
            f"/api/v1/report-runs/{catalogue_id}/data",
            headers=cookie_headers(world.place.author.token, key=False),
        )
        assert preview.status_code == 200, preview.text
        assert len(preview.json()["sections"]) == 5
        table = call(
            world.app,
            "GET",
            f"/api/v1/report-runs/{catalogue_id}/data?section_table=revenue&limit=1",
            headers=cookie_headers(world.place.author.token, key=False),
        )
        assert table.status_code == 200, table.text
        assert len(table.json()["items"]) == 1
        download = call(
            world.app,
            "GET",
            f"/api/v1/report-runs/{catalogue_id}/output",
            headers=cookie_headers(world.place.author.token, key=False),
        )
        assert download.status_code == 200, download.text
        if output_format == "JSON":
            assert len(download.json()["sections"]) == 5
            assert download.json()["parameters"] == document["parameters"]
        # Both catalogue and original-publication APIs re-export the same saved dataset.
        for rerun_source in (
            catalogue_id,
            saved_id if output_format == "JSON" else downloads[output_format],
        ):
            rerun_response = call(
                world.app,
                "POST",
                f"/api/v1/report-runs/{rerun_source}/rerun",
                headers=cookie_headers(world.place.author.token, world.place.author.csrf_token),
            )
            assert rerun_response.status_code == 202, rerun_response.text
            rerun_job_id = UUID(rerun_response.json()["id"])
            with tenant_session(world.place.principal.db_context) as session:
                rerun_job = (
                    session.execute(select(job).where(job.c.id == rerun_job_id)).mappings().one()
                )
                rerun_id = rerun_job["subject_id"]
                session.execute(
                    text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"),
                    {"id": rerun_job["procrastinate_job_id"]},
                )
            registry.run_job(
                rerun_job_id,
                world.place.tenant_id,
                attempt=1,
                runtime=JobRuntime(
                    clock=world.place.clock, keyring=world.place.keyring, files=world.place.files
                ),
            )
            with world.place.uow() as uow:
                uow.ctx = replace(uow.ctx, tenant_kind=TenantKind.SANDBOX)
                original_report = dict(
                    uow.session.execute(select(report_run).where(report_run.c.id == catalogue_id))
                    .mappings()
                    .one()
                )
                repeated = (
                    uow.session.execute(select(report_run).where(report_run.c.id == rerun_id))
                    .mappings()
                    .one()
                )
                assert repeated["status"] == "SUCCEEDED", repeated["problem"]
                assert repeated["output_sha256"] == original_report["output_sha256"]
                assert repeated["source_binding"] == original_report["source_binding"]
                from erev_api.domain.reports import evidence_catalogue_access

                uow.ctx = replace(
                    uow.ctx,
                    principal=replace(
                        uow.principal, permissions=uow.principal.permissions - {"scenario.use"}
                    ),
                )
                with pytest.raises(Problem):
                    evidence_catalogue_access.authorize(uow, original_report)
    with world.place.uow() as uow, pytest.raises(Problem, match="already been published"):
        run_job.cancel_guard(uow, {"forecast_run_id": str(requested_id)}, job_id)
    production = call(
        world.app,
        "POST",
        "/api/v1/forecast-runs",
        json=body,
        headers=cookie_headers(source_actor.token, source_actor.csrf_token),
    )
    assert production.status_code == 409, production.text
    listing = call(
        world.app,
        "GET",
        "/api/v1/forecast-runs",
        headers=cookie_headers(world.place.author.token, key=False),
    )
    assert listing.status_code == 200, listing.text
    assert str(requested_id) in {item["id"] for item in listing.json()["items"]}
    for cancel in (True, False):
        another = call(
            world.app,
            "POST",
            "/api/v1/forecast-runs",
            json=body,
            headers=cookie_headers(world.place.author.token, world.place.author.csrf_token),
        )
        assert another.status_code == 202, another.text
        other_job = UUID(another.json()["id"])
        if cancel:
            stopped = call(
                world.app,
                "POST",
                f"/api/v1/jobs/{other_job}/cancel",
                headers=cookie_headers(world.place.author.token, world.place.author.csrf_token),
            )
            assert stopped.status_code == 200, stopped.text
        else:
            with tenant_session(world.place.principal.db_context) as session:
                queued = session.execute(select(job).where(job.c.id == other_job)).mappings().one()
                session.execute(
                    text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id"),
                    {"id": queued["procrastinate_job_id"]},
                )
            with patch.object(
                run_job.computation,
                "recompute",
                side_effect=Problem("invalid-transition", "Forecast computation refused"),
            ):
                registry.run_job(
                    other_job,
                    world.place.tenant_id,
                    attempt=1,
                    runtime=JobRuntime(
                        clock=world.place.clock,
                        keyring=world.place.keyring,
                        files=world.place.files,
                    ),
                )
        settled = call(
            world.app,
            "GET",
            f"/api/v1/forecast-runs/{another.json()['forecast_run_id']}",
            headers=cookie_headers(world.place.author.token, key=False),
        )
        assert settled.json()["status"] == "FAILED", settled.text
        assert settled.json()["report_run_ids"] == []
