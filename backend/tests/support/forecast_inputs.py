"""Exercise the forecast input API inside a real created scenario."""

from uuid import UUID

import pytest
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import forecast_event_set
from fastapi import FastAPI
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError
from support.http import call
from support.principals import Actor, cookie_headers


def exercise_input_sets(app: FastAPI, source: Actor, sandbox: Actor, tenant_id: UUID) -> None:
    base = "/api/v1/forecast-event-sets"
    body = {"code": "Q4_BASE", "name": "Q4 base"}
    denied = call(
        app, "POST", base, json=body, headers=cookie_headers(source.token, source.csrf_token)
    )
    assert denied.status_code == 403 and denied.json()["type"].endswith("sandbox-restricted"), (
        denied.text
    )
    headers = cookie_headers(sandbox.token, sandbox.csrf_token)
    created = call(app, "POST", base, json=body, headers=headers)
    assert created.status_code == 201, created.text
    replay = call(app, "POST", base, json=body, headers=headers)
    assert replay.status_code == 201 and replay.json() == created.json(), replay.text
    path = f"{base}/{created.json()['id']}"
    edit_headers = cookie_headers(sandbox.token, sandbox.csrf_token)
    edit_headers["If-Match"] = created.headers["ETag"]
    edited = call(app, "PATCH", path, json={"name": "Q4 reviewed base"}, headers=edit_headers)
    assert edited.status_code == 200, edited.text
    stale_headers = cookie_headers(sandbox.token, sandbox.csrf_token)
    stale_headers["If-Match"] = created.headers["ETag"]
    stale = call(app, "POST", path + "/publish", headers=stale_headers)
    assert stale.status_code == 412, stale.text
    publish_headers = cookie_headers(sandbox.token, sandbox.csrf_token)
    publish_headers["If-Match"] = edited.headers["ETag"]
    published = call(app, "POST", path + "/publish", headers=publish_headers)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "PUBLISHED"
    assert len(published.json()["content_sha256"]) == 64
    blocked_headers = cookie_headers(sandbox.token, sandbox.csrf_token)
    blocked_headers["If-Match"] = published.headers["ETag"]
    blocked = call(app, "PATCH", path, json={"name": "Changed"}, headers=blocked_headers)
    assert blocked.status_code == 409, blocked.text
    with pytest.raises(DBAPIError, match="EREV-CFG-002"):
        with tenant_session(
            DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        ) as session:
            session.execute(
                update(forecast_event_set)
                .where(forecast_event_set.c.id == UUID(created.json()["id"]))
                .values(name="SQL mutation")
            )
    next_version = call(
        app, "POST", base, json=body, headers=cookie_headers(sandbox.token, sandbox.csrf_token)
    )
    assert next_version.status_code == 201, next_version.text
    assert next_version.json()["version_no"] == 2
    assert next_version.json()["supersedes_version_id"] == created.json()["id"]
    next_headers = cookie_headers(sandbox.token, sandbox.csrf_token)
    next_headers["If-Match"] = next_version.headers["ETag"]
    next_published = call(
        app, "POST", f"{base}/{next_version.json()['id']}/publish", headers=next_headers
    )
    assert next_published.status_code == 200, next_published.text
    previous = call(app, "GET", path, headers=cookie_headers(sandbox.token, key=False))
    assert previous.status_code == 200 and previous.json()["status"] == "SUPERSEDED", previous.text
    assert previous.json()["content_sha256"] == published.json()["content_sha256"]
    listed = call(
        app,
        "GET",
        base,
        params={"status": "PUBLISHED"},
        headers=cookie_headers(sandbox.token, key=False),
    )
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["items"]] == [next_version.json()["id"]]


def exercise_forecast_imports(world: object) -> None:
    """Run a real progress file through validation, diff and scenario commit."""
    from erev_api.db.tables import (
        approval_request,
        contract,
        forecast_event_set,
        import_upload,
        job,
    )
    from sqlalchemy import func, select
    from support.factories import ImportWorld, run_import_job, upload_import_source

    assert isinstance(world, ImportWorld)

    def headers() -> dict[str, str]:
        return cookie_headers(world.actor.token, world.actor.csrf_token)

    created_set = call(
        world.app,
        "POST",
        "/api/v1/forecast-event-sets",
        json={"code": "FILE_BASE", "name": "File base"},
        headers=headers(),
    )
    assert created_set.status_code == 201, created_set.text
    set_id = UUID(created_set.json()["id"])

    contract_id = world.scalar(
        select(contract.c.id).where(contract.c.external_id == "SF-ORD-10001")
    )

    def progress(ratio: str, day: str) -> None:
        event_headers = headers()
        head = world.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
        event_headers["If-Match"] = f'"s{head}"'
        appended = call(
            world.app,
            "POST",
            f"/api/v1/contracts/{contract_id}/events",
            params={"forecast_event_set_id": str(set_id)},
            headers=event_headers,
            json={
                "events": [
                    {
                        "event_type": "PROGRESS_RECORDED",
                        "effective_date": day,
                        "payload": {
                            "obligation_key": "O2",
                            "cumulative_progress_ratio": ratio,
                            "measure": "OUTPUT_PERCENT",
                        },
                    }
                ]
            },
        )
        assert appended.status_code == 201, appended.text

    progress("0.50", "2026-02-01")
    content = (
        b"contract,event_type,effective_date,obligation_key,cumulative_progress_ratio,measure\n"
        b"SF-ORD-10001,PROGRESS_RECORDED,2026-02-28,O2,0.60,OUTPUT_PERCENT\n"
    )
    source = upload_import_source(world, "forecast-progress.csv", content)
    created = call(
        world.app,
        "POST",
        "/api/v1/imports",
        headers=headers(),
        json={
            "file_id": source,
            "template_code": "progress_events",
            "forecast_event_set_id": str(set_id),
        },
    )
    assert created.status_code == 202, created.text
    import_id = UUID(created.headers["X-Erev-Import-Id"])
    set_path = f"/api/v1/forecast-event-sets/{set_id}"
    publish_headers = headers()
    before_publish = call(
        world.app, "GET", set_path, headers=cookie_headers(world.actor.token, key=False)
    )
    publish_headers["If-Match"] = before_publish.headers["ETag"]
    premature = call(world.app, "POST", set_path + "/publish", headers=publish_headers)
    assert premature.status_code == 409, premature.text
    run_import_job(world, UUID(created.json()["id"]))
    row = world.rows(select(import_upload).where(import_upload.c.id == import_id))[0]
    assert row["status"] == "VALIDATED", row
    diff_id = world.scalar(
        select(job.c.id).where(job.c.subject_id == import_id, job.c.kind == "IMPORT_DIFF")
    )
    run_import_job(world, diff_id)
    before_approvals = world.scalar(select(func.count()).select_from(approval_request))
    submitted = call(
        world.app, "POST", f"/api/v1/imports/{import_id}/submit", headers=headers(), json={}
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["approval_request_id"] is None
    assert submitted.json()["status"] == "APPROVED"
    assert submitted.json()["forecast_event_set_id"] == str(set_id)
    commit_id = world.scalar(
        select(job.c.id).where(job.c.subject_id == import_id, job.c.kind == "IMPORT_COMMIT")
    )
    run_import_job(world, commit_id)
    committed = world.rows(select(import_upload).where(import_upload.c.id == import_id))[0]
    assert committed["status"] == "COMMITTED", committed
    assert world.scalar(select(func.count()).select_from(approval_request)) == before_approvals
    captured = world.rows(select(forecast_event_set).where(forecast_event_set.c.id == set_id))[0]
    assert captured["import_upload_ids"] == [import_id]
    progress("0.70", "2026-03-31")
    expected_order = [
        {"kind": "API_COMMAND", "index": 0},
        {"kind": "IMPORT_UPLOAD", "id": str(import_id)},
        {"kind": "API_COMMAND", "index": 1},
    ]
    assert (
        world.scalar(
            select(forecast_event_set.c.input_sequence).where(forecast_event_set.c.id == set_id)
        )
        == expected_order
    )
    invalid_source = upload_import_source(
        world,
        "forecast-invalid.csv",
        b"contract,event_type,effective_date,obligation_key,quantity,trigger\n"
        b"SF-ORD-10001,DELIVERY_RECORDED,2026-02-28,O1,2,DELIVERY\n",
    )
    invalid = call(
        world.app,
        "POST",
        "/api/v1/imports",
        headers=headers(),
        json={
            "file_id": invalid_source,
            "template_code": "progress_events",
            "forecast_event_set_id": str(set_id),
        },
    )
    assert invalid.status_code == 202, invalid.text
    run_import_job(world, UUID(invalid.json()["id"]))
    invalid_id = UUID(invalid.headers["X-Erev-Import-Id"])
    assert (
        world.scalar(select(import_upload.c.status).where(import_upload.c.id == invalid_id))
        == "INVALID"
    )
    assert world.scalar(
        select(forecast_event_set.c.import_upload_ids).where(forecast_event_set.c.id == set_id)
    ) == [import_id]
    current = call(world.app, "GET", set_path, headers=cookie_headers(world.actor.token, key=False))
    publish_headers = headers()
    publish_headers["If-Match"] = current.headers["ETag"]
    published = call(world.app, "POST", set_path + "/publish", headers=publish_headers)
    assert published.status_code == 200, published.text

    assert published.json()["input_sequence"] == expected_order
    next_version = call(
        world.app,
        "POST",
        "/api/v1/forecast-event-sets",
        json={"code": "FILE_BASE", "name": "Next outlook"},
        headers=headers(),
    )
    assert next_version.status_code == 201, next_version.text
    assert next_version.json()["input_sequence"] == expected_order

    # Materialize the published version through the future refresh worker's source reader.
    import io
    from dataclasses import replace
    from unittest.mock import patch

    from erev_api.db.tables import file_object
    from erev_api.domain.forecast import event_sets, replay_inputs
    from erev_api.problems import Problem
    from support.factories import workspace as command_workspace

    place = command_workspace(
        world.app, world.clock, world.runtime.keyring, world.runtime.files, world.actor
    )
    next_headers = headers()
    next_headers["If-Match"] = next_version.headers["ETag"]
    next_id = UUID(next_version.json()["id"])
    next_published = call(
        world.app, "POST", f"/api/v1/forecast-event-sets/{next_id}/publish", headers=next_headers
    )
    assert next_published.status_code == 200, next_published.text
    with place.uow() as uow:
        inputs = replay_inputs.load(uow, next_id)
        assert [step["kind"] for step in inputs.steps] == [
            "API_COMMAND",
            "IMPORT_UPLOAD",
            "API_COMMAND",
        ]
        assert (
            inputs.steps[0]["body"]["events"][0]["payload"]["cumulative_progress_ratio"] == "0.50"
        )
        assert (
            inputs.steps[2]["body"]["events"][0]["payload"]["cumulative_progress_ratio"] == "0.70"
        )
        assert inputs.steps[1]["source_upload_id"] == str(import_id)
        assert len(inputs.files) == 1 and inputs.files[0].content == content
        assert inputs.content_sha256 == next_published.json()["content_sha256"]
        metadata = (
            uow.session.execute(select(file_object).where(file_object.c.id == inputs.files[0].id))
            .mappings()
            .one()
        )
        with patch.object(
            replay_inputs, "open_file", return_value=(dict(metadata), io.BytesIO(b"changed"))
        ):
            with pytest.raises(Problem, match="retained metadata"):
                replay_inputs.load(uow, next_id)
        row = event_sets._row(uow.session, next_id)
        with patch.object(event_sets, "_row", return_value={**row, "content_sha256": "0" * 64}):
            with pytest.raises(Problem, match="does not match its hash"):
                replay_inputs.load(uow, next_id)
    denied = replace(place.principal, permissions=place.principal.permissions - {"scenario.use"})
    with place.uow(denied) as uow, pytest.raises(Problem):
        replay_inputs.load(uow, next_id)

    from erev_api.domain.forecast import replay_apply
    from erev_api.enums import TenantKind
    from erev_api.schemas.imports import ImportCreateIn

    inline_set = call(
        world.app,
        "POST",
        "/api/v1/forecast-event-sets",
        json={"code": "INLINE", "name": "Inline replay"},
        headers=headers(),
    )
    assert inline_set.status_code == 201, inline_set.text
    inline_id = UUID(inline_set.json()["id"])

    from erev_api.domain.forecast import replay_resources

    with place.uow() as uow:
        uow.ctx = replace(uow.ctx, tenant_kind=TenantKind.SANDBOX)
        materialized = replay_resources.materialize_files(uow, inputs, target_set_id=inline_id)
        assert materialized.file_ids[inputs.files[0].id] == inputs.files[0].id
        assert materialized.steps[1]["file_id"] == str(inputs.files[0].id)
        assert materialized.steps[1]["template_version"] == inputs.steps[1]["template_version"]
        assert materialized.steps[1] is not inputs.steps[1]
        # A source-only evidence id must be rewritten to a real target upload.
        from uuid import uuid4

        source_evidence_id = uuid4()
        evidence = replace(inputs.files[0], id=source_evidence_id, purpose="ATTACHMENT")
        command_step = {
            **inputs.steps[0],
            "body": {**inputs.steps[0]["body"], "evidence_file_ids": [str(source_evidence_id)]},
        }
        with_evidence = replace(
            inputs,
            files=(*inputs.files, evidence),
            steps=(command_step, *inputs.steps[1:]),
        )
        rebound = replay_resources.materialize_files(uow, with_evidence, target_set_id=inline_id)
        target_evidence_id = rebound.file_ids[source_evidence_id]
        assert target_evidence_id != source_evidence_id
        assert rebound.steps[0]["body"]["evidence_file_ids"] == [str(target_evidence_id)]
        assert command_step["body"]["evidence_file_ids"] == [str(source_evidence_id)]
        _, copied_stream = replay_inputs.open_file(
            uow.session, target_evidence_id, files=uow.files, keyring=uow.keyring
        )
        with copied_stream:
            assert copied_stream.read() == evidence.content
        with pytest.raises(Problem, match="retained hash"):
            replay_resources.materialize_files(
                uow,
                replace(inputs, files=(replace(inputs.files[0], content=b"corrupt"),)),
                target_set_id=inline_id,
            )
        with pytest.raises(Problem, match="manifest"):
            replay_resources.materialize_files(
                uow, replace(inputs, files=()), target_set_id=inline_id
            )
        uow.commit()
    inline_source = upload_import_source(
        world,
        "inline-progress.csv",
        content.replace(b"0.60", b"0.80")
        .replace(b"2026-02-28", b"2026-04-30")
        .replace(b"cumulative_progress_ratio", b"completion"),
    )
    from erev_engine.canonical import sha256_hex

    retained_mapping = {
        "id": str(uuid4()),
        "code": "ORIGINAL_MAPPING",
        "name": "Original source mapping",
        "version_no": 1,
        "effective_from": None,
        "template_code": "progress_events",
        "mappings": {"aliases": {"completion": "cumulative_progress_ratio"}},
    }
    retained_mapping["content_sha256"] = sha256_hex(
        {key: value for key, value in retained_mapping.items() if key != "id"}
    )
    before_jobs = world.scalar(select(func.count()).select_from(job))
    before_imports = world.scalar(select(func.count()).select_from(import_upload))
    with place.uow() as uow:
        uow.ctx = replace(uow.ctx, tenant_kind=TenantKind.SANDBOX)
        # The executor, like the eventual refresh worker, owns one complete transaction.
        applied_id = replay_apply.apply_file(
            uow,
            ImportCreateIn(
                file_id=UUID(inline_source),
                template_code="progress_events",
                forecast_event_set_id=inline_id,
            ),
            quarantine=False,
            mapping_snapshot=retained_mapping,
        )
        uow.commit()
    applied = world.rows(select(import_upload).where(import_upload.c.id == applied_id))[0]
    assert applied["status"] == "COMMITTED" and applied["job_id"] is None
    assert applied["approval_request_id"] is None
    assert applied["forecast_mapping_snapshot"] == retained_mapping
    assert applied["mapping_profile_id"] is None
    assert world.scalar(select(func.count()).select_from(job)) == before_jobs
    assert world.scalar(
        select(forecast_event_set.c.import_upload_ids).where(forecast_event_set.c.id == inline_id)
    ) == [applied_id]
    # Invalid replay inputs are rolled back even if the parent catches the failure and commits.
    with place.uow() as uow:
        uow.ctx = replace(uow.ctx, tenant_kind=TenantKind.SANDBOX)
        with pytest.raises(Problem, match="failed validation"):
            replay_apply.apply_file(
                uow,
                ImportCreateIn(
                    file_id=UUID(invalid_source),
                    template_code="progress_events",
                    forecast_event_set_id=inline_id,
                ),
                quarantine=False,
            )
        uow.commit()
    assert world.scalar(select(func.count()).select_from(import_upload)) == before_imports + 1
    assert world.scalar(select(func.count()).select_from(job)) == before_jobs

    from erev_api.domain.contracts import events as contract_events
    from erev_api.schemas.events import EventAppendIn

    command_body = EventAppendIn.model_validate(
        {
            "events": [
                {
                    "event_type": "PROGRESS_RECORDED",
                    "effective_date": "2026-05-31",
                    "payload": {
                        "obligation_key": "O2",
                        "cumulative_progress_ratio": "0.90",
                        "measure": "OUTPUT_PERCENT",
                    },
                }
            ],
        }
    )
    before_head = world.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    compute = contract_events.compute_group

    def fail_after_compute(*args, **kwargs):
        compute(*args, **kwargs)
        raise Problem("validation-failed", "injected replay computation failure")

    with place.uow() as uow:
        uow.ctx = replace(uow.ctx, tenant_kind=TenantKind.SANDBOX)
        with patch.object(contract_events, "compute_group", side_effect=fail_after_compute):
            with pytest.raises(Problem, match="injected replay computation failure"):
                replay_apply.apply_command(
                    uow, contract_id=contract_id, input_set_id=inline_id, body=command_body
                )
        uow.commit()
    assert (
        world.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
        == before_head
    )
    assert (
        world.scalar(
            select(forecast_event_set.c.api_commands).where(forecast_event_set.c.id == inline_id)
        )
        == []
    )
    with place.uow() as uow:
        uow.ctx = replace(uow.ctx, tenant_kind=TenantKind.SANDBOX)
        with patch.object(contract_events, "obligation_count", return_value=201):
            recorded = replay_apply.apply_command(
                uow, contract_id=contract_id, input_set_id=inline_id, body=command_body
            )
        assert recorded.job is None and recorded.appended is not None
        assert recorded.appended.computation.status == "SUCCEEDED"
        uow.commit()
    assert world.scalar(select(func.count()).select_from(job)) == before_jobs
    assert world.scalar(
        select(forecast_event_set.c.input_sequence).where(forecast_event_set.c.id == inline_id)
    ) == [{"kind": "IMPORT_UPLOAD", "id": str(applied_id)}, {"kind": "API_COMMAND", "index": 0}]

    inline_path = f"/api/v1/forecast-event-sets/{inline_id}"
    inline_current = call(world.app, "GET", inline_path, headers=headers())
    inline_headers = headers()
    inline_headers["If-Match"] = inline_current.headers["ETag"]
    inline_published = call(world.app, "POST", inline_path + "/publish", headers=inline_headers)
    assert inline_published.status_code == 200, inline_published.text
    with place.uow() as uow:
        next_replay = replay_inputs.load(uow, inline_id)
        assert next_replay.steps[0]["mapping_profile"] == retained_mapping
