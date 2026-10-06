"""The failure hook of ``SSP_CALCULATOR`` (05 §5.6 rev 1.165; item JOB-FAILED-ITEM-1; BUILD_SPEC
PLF-22): a calculator job that ends FAILED without its handler's own ending ends the run.

The handler ends the run ``FAILED`` for an error it catches (``_fail_run``), so the hook is
reached only when the worker died — or the job never ran: the run is ``RUNNING`` or ``QUEUED``,
the job silent, and the sweeper settles the job ten minutes later. The run and the job are
written as rows (``support.rows``), because the state under test is the one a dead worker leaves
behind; the settlement is the product's.
"""

from __future__ import annotations

import io
import json
from datetime import timedelta
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, exception_item, job, ssp_calculator_run
from erev_api.db.transitions import apply
from erev_api.domain.ssp import calculator
from erev_api.enums import JobKind, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.sweeper import fail_stalled
from sqlalchemy import func, insert, select, text
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.principals import Member, member
from support.rows import ssp_calculator_run_values

STALL = timedelta(minutes=10, seconds=1)
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def lena(committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> Member:
    return member(keyring, clock)


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _running(someone: Member, status: str) -> tuple[UUID, UUID]:
    """A calculator run of ``someone`` in ``status`` and its RUNNING job, as a worker that died
    left them: (run id, job id)."""
    with tenant_session(_db(someone.tenant_id)) as session:
        row = ssp_calculator_run_values(someone.tenant_id, status=status)
        session.execute(insert(ssp_calculator_run).values(**row))
        run_id = UUID(str(row["id"]))
        queued = registry.insert_job(
            session,
            JobKind.SSP_CALCULATOR,
            {"ssp_calculator_run_id": str(run_id)},
            tenant_id=someone.tenant_id,
            now=FROZEN_AT,
            created_by=someone.user_id,
            created_by_kind=PrincipalKind.USER,
            subject_type=calculator.OBJECT_RUN,
            subject_id=run_id,
        )
        registry.dispatch(
            session,
            job_id=queued["id"],
            tenant_id=someone.tenant_id,
            queue=str(queued["queue"]),
            now=FROZEN_AT,
        )
        job_id = UUID(str(queued["id"]))
    with tenant_session(_db(someone.tenant_id)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
        apply(
            session,
            "job",
            job_id,
            to_status="RUNNING",
            set_values={
                "started_at": FROZEN_AT,
                "updated_at": FROZEN_AT,
                "updated_by": None,
                "updated_by_kind": PrincipalKind.SYSTEM.value,
            },
            expected_status="QUEUED",
        )
    return run_id, job_id


def _sweep(app_settings: Settings, keyring: KeyRing) -> None:
    fail_stalled(
        JobRuntime(
            clock=frozen_clock(FROZEN_AT + STALL),
            keyring=keyring,
            files=LocalFileStore(app_settings.file_root),
        )
    )


def _run(tenant_id: UUID, run_id: UUID) -> tuple[str, object]:
    with tenant_session(_db(tenant_id), read_only=True) as session:
        found = session.execute(
            select(ssp_calculator_run.c.status, ssp_calculator_run.c.finished_at).where(
                ssp_calculator_run.c.id == run_id
            )
        ).one()
    return str(getattr(found[0], "value", found[0])), found[1]


def _fails(tenant_id: UUID, run_id: UUID) -> list[tuple[object, object, object]]:
    """(request id, before, detail) of the run's ``ssp_calculator_run.fail`` events."""
    with tenant_session(_db(tenant_id), read_only=True) as session:
        rows = session.execute(
            select(audit_event.c.request_id, audit_event.c.before, audit_event.c.detail).where(
                audit_event.c.action == calculator.RUN_FAIL, audit_event.c.object_id == run_id
            )
        ).all()
    return [tuple(row) for row in rows]


@pytest.mark.parametrize("left_in", ["RUNNING", "QUEUED"])
def test_job_failed_item_1_a_stalled_run_ends_failed(
    left_in: str, lena: Member, app_settings: Settings, keyring: KeyRing
) -> None:
    """A worker died while the run was ``RUNNING`` — or before it had started the run. The
    sweeper ends the job FAILED and the kind's failure hook ends the run ``FAILED`` with
    ``ssp_calculator_run.fail`` naming the job's problem; before, the run stayed as it was for
    good. The kind raises no exception item: a calculator run names no legal entity."""
    spec = registry.HANDLERS[JobKind.SSP_CALCULATOR]
    assert spec.on_failure is calculator.run_job_failed and spec.failed_item is None
    run_id, job_id = _running(lena, left_in)
    _sweep(app_settings, keyring)
    assert _run(lena.tenant_id, run_id) == ("FAILED", FROZEN_AT + STALL)
    assert _fails(lena.tenant_id, run_id) == [
        (f"job-{job_id}", {"status": left_in}, {"problem": "job-stalled"})
    ]
    with tenant_session(_db(lena.tenant_id), read_only=True) as session:
        state = session.execute(select(job.c.state).where(job.c.id == job_id)).scalar_one()
        items = session.execute(select(func.count()).select_from(exception_item)).scalar_one()
    assert (state, items) == ("FAILED", 0)


def test_job_failed_item_1_the_calculator_hook_leaves_a_run_that_ended_or_is_held(
    lena: Member, app_settings: Settings, keyring: KeyRing, log_stream: io.StringIO
) -> None:
    """The hook ends only a run that is still to end and that nobody holds: a run that
    ``SUCCEEDED`` before the worker died stays as it is, and a run whose row another transaction
    holds is not waited for. Since 05 JOB-06 rev 1.200 the holder is never the job's own
    computation, whose open transaction keeps the job from being stopped; the session here
    holds the row without the job's lock, as a transaction of another actor would."""
    done, first = _running(lena, "SUCCEEDED")
    held, second = _running(lena, "RUNNING")
    with tenant_session(_db(lena.tenant_id)) as holder:
        holder.execute(
            select(ssp_calculator_run.c.id).where(ssp_calculator_run.c.id == held).with_for_update()
        )
        _sweep(app_settings, keyring)
    assert _run(lena.tenant_id, done)[0] == "SUCCEEDED"
    assert _run(lena.tenant_id, held) == ("RUNNING", None)
    assert _fails(lena.tenant_id, done) == [] and _fails(lena.tenant_id, held) == []
    with tenant_session(_db(lena.tenant_id), read_only=True) as session:
        states = sorted(
            str(state)
            for state in session.execute(
                select(job.c.state).where(job.c.id.in_([first, second]))
            ).scalars()
        )
    assert states == ["FAILED", "FAILED"]
    # Not waited for: the hook returned, it did not fail on the held row's lock.
    lines = [json.loads(raw) for raw in log_stream.getvalue().splitlines() if raw.strip()]
    mine = {str(first), str(second)}
    assert [line["event"] for line in lines if line.get("job_id") in mine] == ["job.failed"] * 2
