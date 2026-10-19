"""Mixed-input replay transaction checks in the scenario fixture."""

import hashlib
from copy import deepcopy
from dataclasses import replace
from uuid import UUID

import pytest
from erev_api.db.tables import contract, forecast_event_set, import_upload, job
from erev_api.domain.forecast import replay
from erev_api.domain.forecast.replay_inputs import ReplayInputs
from erev_api.enums import TenantKind
from erev_api.problems import Problem
from sqlalchemy import func, select
from support.factories import ImportWorld, workspace
from support.http import call
from support.principals import cookie_headers


def exercise_replay(world: ImportWorld, source: ReplayInputs) -> None:
    place = workspace(
        world.app, world.clock, world.runtime.keyring, world.runtime.files, world.actor
    )
    headers = cookie_headers(world.actor.token, world.actor.csrf_token)
    created = call(
        world.app,
        "POST",
        "/api/v1/forecast-event-sets",
        json={"code": "REPLAY_TXN", "name": "Replay transaction"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    target_id = UUID(created.json()["id"])
    file_step, command = deepcopy(source.steps)
    first = deepcopy(command)
    first["body"]["events"][0]["effective_date"] = "2026-06-01"
    first["body"]["events"][0]["payload"]["cumulative_progress_ratio"] = "0.92"
    command["body"]["events"][0]["effective_date"] = "2026-07-31"
    command["body"]["events"][0]["payload"]["cumulative_progress_ratio"] = "0.98"
    data = source.files[0].content.replace(b"0.80", b"0.95").replace(b"2026-04-30", b"2026-06-30")
    bundle = replace(
        source,
        steps=(first, file_step, command),
        files=(replace(source.files[0], content=data, sha256=hashlib.sha256(data).hexdigest()),),
    )
    contract_id = UUID(command["contract_id"])
    head = world.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
    imports = world.scalar(select(func.count()).select_from(import_upload))
    jobs = world.scalar(select(func.count()).select_from(job))
    calls = 0

    def cancel_after_file() -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise Problem("precondition-failed", "Replay was cancelled after its file.")

    with place.uow() as uow:
        uow.ctx = replace(uow.ctx, tenant_kind=TenantKind.SANDBOX)
        with pytest.raises(Problem, match="cancelled after its file"):
            replay.apply(uow, bundle, target_set_id=target_id, heartbeat=cancel_after_file)
        uow.commit()
    assert calls == 3
    assert world.scalar(select(func.count()).select_from(import_upload)) == imports
    assert (
        world.scalar(select(contract.c.head_stream_version).where(contract.c.id == contract_id))
        == head
    )
    row = world.rows(select(forecast_event_set).where(forecast_event_set.c.id == target_id))[0]
    assert row["status"] == "DRAFT" and row["input_sequence"] == []
    with place.uow() as uow:
        uow.ctx = replace(uow.ctx, tenant_kind=TenantKind.SANDBOX)
        published = replay.apply(uow, bundle, target_set_id=target_id)
        assert published["status"] == "PUBLISHED"
        assert [entry["kind"] for entry in published["input_sequence"]] == [
            "API_COMMAND",
            "IMPORT_UPLOAD",
            "API_COMMAND",
        ]
        with pytest.raises(Problem):
            replay.apply(uow, bundle, target_set_id=target_id)
        uow.commit()
    assert world.scalar(select(func.count()).select_from(import_upload)) == imports + 1
    assert world.scalar(select(func.count()).select_from(job)) == jobs
