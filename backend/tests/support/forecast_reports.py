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


def exercise_capture(world: Any) -> None:
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
