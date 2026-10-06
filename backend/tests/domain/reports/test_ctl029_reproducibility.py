"""CTL-029 reproducibility facts of report reruns (P4-CTL029-R1; D-98 candidate 100; REQ-RPT-002;
03 CTL-029; SOP-1 T-PLT-39).

The REPORT_RUN job computes the rerun comparison BEFORE recording and derives the persisted CTL-029
fact from it (``framework.ctl029_fact``): a first run PASSes with its reproducibility stamp; a rerun
whose hash and totals both equal the original's PASSes; a hash-only or totals-only mismatch FAILs
with one exception and both sides' evidence in ``detail``; a rerun of an original without output is
NOT_APPLICABLE (``ORIGINAL_WITHOUT_OUTPUT``). The run and the job stay SUCCEEDED whenever the rerun
produced its output — the mismatch is a control exception, not a job failure.

Database tests (lane P4 wrote them without a lane database — NOT RUN by the lane). The mismatch
originals are synthetic SUCCEEDED ``report_run`` rows copied from a real run with one stored value
altered, because T-RPT-02 is immutable after SUCCEEDED (DB-03) and the inventory report cannot
produce a hash-only or totals-only difference on its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import control_execution, job, report_run
from erev_api.domain.reports.framework import ORIGINAL_WITHOUT_OUTPUT
from erev_api.enums import ControlResult, RunStatus
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select, text
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.principals import Actor, colleague, enrolled, member
from support.reference import assign, calendar, entity, get, holding, post

RUNS: Final = "/api/v1/report-runs"
JOBS: Final = "/api/v1/jobs"
CLIENTS: Final = "/api/v1/api-clients"
INVENTORY: Final = "api_client_inventory"
CLIENT_NAMES: Final = ("svc-salesforce", "svc-netsuite", "svc-metering")
OTHER_SHA: Final = "0" * 64
OTHER_TOTALS: Final = {"client_count": 99}
_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _run_deferred(tenant_id: UUID, job_id: UUID, runtime: JobRuntime) -> None:
    with tenant_session(_db(tenant_id)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    registry.run_job(job_id, tenant_id, attempt=1, runtime=runtime)


def _world(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> tuple[Actor, UUID]:
    """Maya (revenue accountant) in a tenant with three API clients; returns (maya, tenant id)."""
    stamp_test_release()
    maya_member = member(keyring, clock)
    maya = holding(app, maya_member, "revenue_accountant")
    entity(app, maya, code="AVM-US", calendar_id=calendar(app, maya))
    tomas_member = colleague(maya_member.tenant_id, "tomas")
    assign(tomas_member, "tenant_admin")
    tomas = enrolled(app, clock, tomas_member)
    for name in CLIENT_NAMES:
        created = post(app, CLIENTS, tomas, {"name": name, "scopes": ["contract.read"]})
        assert created.status_code == 201, created.text
    return maya, maya_member.tenant_id


def _first_run(app: FastAPI, maya: Actor, tenant_id: UUID, runtime: JobRuntime) -> UUID:
    started = post(
        app, RUNS, maya, {"report_code": INVENTORY, "parameters": {}, "output_format": "JSON"}
    )
    assert started.status_code == 202, started.text
    run_id = UUID(started.headers["x-erev-report-run-id"])
    _run_deferred(tenant_id, UUID(started.json()["id"]), runtime)
    return run_id


def _rerun(
    app: FastAPI, maya: Actor, tenant_id: UUID, runtime: JobRuntime, original_id: UUID
) -> tuple[UUID, Mapping[str, Any]]:
    """``POST /report-runs/{id}/rerun`` run to completion; returns (rerun id, finished job)."""
    accepted = post(app, f"{RUNS}/{original_id}/rerun", maya, {})
    assert accepted.status_code == 202, accepted.text
    rerun_id = UUID(accepted.headers["x-erev-report-run-id"])
    job_id = UUID(accepted.json()["id"])
    _run_deferred(tenant_id, job_id, runtime)
    finished = get(app, f"{JOBS}/{job_id}", maya).json()
    return rerun_id, finished


def _stored_run(tenant_id: UUID, run_id: UUID) -> Mapping[str, Any]:
    with tenant_session(_db(tenant_id)) as session:
        return dict(
            session.execute(select(report_run).where(report_run.c.id == run_id)).mappings().one()
        )


def _synthetic_original(tenant_id: UUID, model: Mapping[str, Any], **changes: Any) -> UUID:
    """A SUCCEEDED (or otherwise finished) copy of a real run with chosen stored values, inserted
    directly because a finished T-RPT-02 row is immutable (DB-03)."""
    row = {
        **model,
        "id": new_id(),
        "report_run_no": f"RPT-S{model['report_run_no'][-5:]}",
        "job_id": None,
        **changes,
    }
    with tenant_session(_db(tenant_id)) as session:
        session.execute(insert(report_run).values(**row))
    return UUID(str(row["id"]))


def _ctl_029_fact(tenant_id: UUID, run_id: UUID) -> Mapping[str, Any]:
    """The one CTL-029 row recorded against ``run_id`` (REPORT_RUN)."""
    with tenant_session(_db(tenant_id)) as session:
        rows = (
            session.execute(
                select(control_execution).where(
                    control_execution.c.control_id == "CTL-029",
                    control_execution.c.run_ref_type == "REPORT_RUN",
                    control_execution.c.run_ref_id == run_id,
                )
            )
            .mappings()
            .all()
        )
    assert len(rows) == 1, rows
    return dict(rows[0])


def _assert_succeeded(app: FastAPI, maya: Actor, run_id: UUID, finished: Mapping[str, Any]) -> None:
    """Ruling (2): the run and the job stay SUCCEEDED when the rerun produced its output."""
    assert finished["state"] == "SUCCEEDED", finished
    shown = get(app, f"{RUNS}/{run_id}", maya).json()
    assert shown["status"] == "SUCCEEDED" and shown["problem"] is None


@pytest.mark.control("CTL-029")
def test_ctl_029_first_run_passes_with_the_reproducibility_stamp(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    maya, tenant_id = _world(app, keyring, clock)
    run_id = _first_run(app, maya, tenant_id, runtime)
    stored = _stored_run(tenant_id, run_id)
    fact = _ctl_029_fact(tenant_id, run_id)
    assert (fact["result"], fact["population_count"], fact["exception_count"]) == ("PASS", 1, 0)
    assert fact["detail"]["first_run"] is True
    assert fact["detail"]["output_sha256"] == stored["output_sha256"]
    assert fact["detail"]["control_totals"] == stored["control_totals"] == {"client_count": 3}
    assert fact["detail"]["row_count"] == 3 and "rerun_of" not in fact["detail"]


@pytest.mark.control("CTL-029")
def test_ctl_029_rerun_with_identical_hash_and_totals_passes(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    maya, tenant_id = _world(app, keyring, clock)
    original_id = _first_run(app, maya, tenant_id, runtime)
    rerun_id, finished = _rerun(app, maya, tenant_id, runtime, original_id)
    _assert_succeeded(app, maya, rerun_id, finished)
    assert finished["result"]["output_sha256_equal"] is True
    assert finished["result"]["control_totals_equal"] is True
    fact = _ctl_029_fact(tenant_id, rerun_id)
    assert (fact["result"], fact["population_count"], fact["exception_count"]) == ("PASS", 1, 0)
    detail = fact["detail"]
    assert detail["first_run"] is False and detail["rerun_of"] == str(original_id)
    assert detail["output_sha256_equal"] is True and detail["control_totals_equal"] is True
    original = _stored_run(tenant_id, original_id)
    assert detail["original"]["output_sha256"] == original["output_sha256"]
    assert detail["rerun"]["output_sha256"] == original["output_sha256"]


@pytest.mark.control("CTL-029")
def test_ctl_029_hash_only_mismatch_fails_the_control_not_the_job(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    maya, tenant_id = _world(app, keyring, clock)
    model = _stored_run(tenant_id, _first_run(app, maya, tenant_id, runtime))
    original_id = _synthetic_original(tenant_id, model, output_sha256=OTHER_SHA)
    rerun_id, finished = _rerun(app, maya, tenant_id, runtime, original_id)
    _assert_succeeded(app, maya, rerun_id, finished)
    assert finished["result"]["output_sha256_equal"] is False
    assert finished["result"]["control_totals_equal"] is True
    fact = _ctl_029_fact(tenant_id, rerun_id)
    assert (fact["result"], fact["population_count"], fact["exception_count"]) == ("FAIL", 1, 1)
    detail = fact["detail"]
    assert (detail["output_sha256_equal"], detail["control_totals_equal"]) == (False, True)
    assert detail["rerun_of"] == str(original_id)
    # Evidence retained on both sides, never overwritten.
    assert detail["original"] == {
        "output_sha256": OTHER_SHA,
        "control_totals": model["control_totals"],
    }
    assert detail["rerun"]["output_sha256"] == model["output_sha256"]
    assert detail["rerun"]["control_totals"] == model["control_totals"]
    assert _stored_run(tenant_id, original_id)["output_sha256"] == OTHER_SHA


@pytest.mark.control("CTL-029")
def test_ctl_029_totals_only_mismatch_fails_the_control_not_the_job(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    maya, tenant_id = _world(app, keyring, clock)
    model = _stored_run(tenant_id, _first_run(app, maya, tenant_id, runtime))
    original_id = _synthetic_original(tenant_id, model, control_totals=OTHER_TOTALS)
    rerun_id, finished = _rerun(app, maya, tenant_id, runtime, original_id)
    _assert_succeeded(app, maya, rerun_id, finished)
    assert finished["result"]["output_sha256_equal"] is True
    assert finished["result"]["control_totals_equal"] is False
    fact = _ctl_029_fact(tenant_id, rerun_id)
    assert (fact["result"], fact["population_count"], fact["exception_count"]) == ("FAIL", 1, 1)
    detail = fact["detail"]
    assert (detail["output_sha256_equal"], detail["control_totals_equal"]) == (True, False)
    assert detail["original"] == {
        "output_sha256": model["output_sha256"],
        "control_totals": OTHER_TOTALS,
    }
    assert detail["rerun"]["control_totals"] == model["control_totals"] == {"client_count": 3}


@pytest.mark.control("CTL-029")
def test_ctl_029_rerun_of_original_without_output_is_not_applicable(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    maya, tenant_id = _world(app, keyring, clock)
    model = _stored_run(tenant_id, _first_run(app, maya, tenant_id, runtime))
    original_id = _synthetic_original(
        tenant_id,
        model,
        status=RunStatus.FAILED.value,
        output_file_id=None,
        output_sha256=None,
        row_count=None,
        control_totals=None,
        finished_at=datetime(2026, 9, 12, 12, tzinfo=UTC),
        problem={"type": "job-failed", "title": "probe"},
    )
    rerun_id, finished = _rerun(app, maya, tenant_id, runtime, original_id)
    _assert_succeeded(app, maya, rerun_id, finished)
    assert finished["result"]["output_sha256_equal"] is False
    assert finished["result"]["control_totals_equal"] is False
    fact = _ctl_029_fact(tenant_id, rerun_id)
    assert (fact["result"], fact["population_count"], fact["exception_count"]) == (
        ControlResult.NOT_APPLICABLE.value,
        0,
        0,
    )
    detail = fact["detail"]
    assert detail["reason"] == ORIGINAL_WITHOUT_OUTPUT and detail["rerun_of"] == str(original_id)
    assert detail["original"]["status"] == "FAILED"
    assert detail["rerun"]["output_sha256"] == model["output_sha256"]
