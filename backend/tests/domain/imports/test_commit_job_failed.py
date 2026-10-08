"""The failure hook of ``IMPORT_COMMIT`` (05 §5.6 rev 1.165; item JOB-FAILED-ITEM-1; BUILD_SPEC
PLF-22): a commit job that ends FAILED without its handler's own ending ends the upload.

The handler ends the upload for every error it stores, so the hook is reached when the worker
died — and, from 05 rev 1.185, when an attempt met a transient database error, which the handler
lets through, or failed before the import was ``COMMITTING``
(``test_import_job_transient_db.py``). Here the worker died: the upload is ``COMMITTING`` — or
still ``APPROVED`` — the job ``RUNNING`` and silent, and the sweeper settles the job ten minutes
later. The upload and the job are written as rows (``support.rows``), because
the state under test is the one a dead worker leaves behind; the settlement is the product's
(``fail_stalled`` → ``fail_attempt`` → ``_fail_job`` → the hook).
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import audit_event, exception_item, import_upload, job
from erev_api.db.transitions import apply
from erev_api.domain.imports import commit
from erev_api.enums import JobKind, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobAttempt, JobRuntime, system_unit_of_work
from erev_api.jobs.sweeper import fail_stalled
from sqlalchemy import insert, select, text
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.principals import Member, member
from support.rows import ROW_BUILDERS, RowContext

STALL = timedelta(minutes=10, seconds=1)
_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


@pytest.fixture
def lena(committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> Member:
    return member(keyring, clock)


def _db(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _committing(someone: Member, status: str) -> tuple[UUID, UUID]:
    """An upload of ``someone`` in ``status`` and its RUNNING commit job, as a worker that died
    left them: (upload id, job id)."""
    with tenant_session(_db(someone.tenant_id)) as session:
        row = dict(
            ROW_BUILDERS["import_upload"](RowContext(someone.tenant_id, someone.user_id), session)
        )
        row.update(status=status, created_by=someone.user_id, created_by_kind="USER")
        session.execute(insert(import_upload).values(**row))
        upload_id = UUID(str(row["id"]))
        queued = registry.insert_job(
            session,
            JobKind.IMPORT_COMMIT,
            {"import_upload_id": str(upload_id)},
            tenant_id=someone.tenant_id,
            now=FROZEN_AT,
            created_by=someone.user_id,
            created_by_kind=PrincipalKind.USER,
            subject_type=commit.OBJECT_TYPE,
            subject_id=upload_id,
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
    return upload_id, job_id


def _sweep(app_settings: Settings, keyring: KeyRing) -> None:
    fail_stalled(
        JobRuntime(
            clock=frozen_clock(FROZEN_AT + STALL),
            keyring=keyring,
            files=LocalFileStore(app_settings.file_root),
        )
    )


def _state(
    tenant_id: UUID, upload_id: UUID, job_id: UUID
) -> tuple[str, str, list[Mapping[str, Any]]]:
    """(upload status, job state, the exception items of the upload)."""
    with tenant_session(_db(tenant_id), read_only=True) as session:
        status = session.execute(
            select(import_upload.c.status).where(import_upload.c.id == upload_id)
        ).scalar_one()
        state = session.execute(select(job.c.state).where(job.c.id == job_id)).scalar_one()
        items = (
            session.execute(
                select(
                    exception_item.c.source,
                    exception_item.c.code,
                    exception_item.c.severity,
                    exception_item.c.message,
                    exception_item.c.owner_membership_id,
                ).where(exception_item.c.import_upload_id == upload_id)
            )
            .mappings()
            .all()
        )
    return str(getattr(status, "value", status)), str(state), [dict(item) for item in items]


def test_job_failed_item_1_a_stalled_commit_ends_its_upload_failed(
    lena: Member, app_settings: Settings, keyring: KeyRing
) -> None:
    """A worker died while the upload was ``COMMITTING``. The sweeper ends the job FAILED and the
    kind's failure hook ends the upload ``FAILED`` with ``IMPORT_PROCESSING_FAILED`` for its
    uploader, as the handler does after an error it catches — before, the upload stayed
    ``COMMITTING`` for good. No ``JOB_FAILED`` item is raised beside it: the upload's own item
    tells the record's readers."""
    assert registry.HANDLERS[JobKind.IMPORT_COMMIT].on_failure is commit.commit_job_failed
    assert registry.HANDLERS[JobKind.IMPORT_COMMIT].failed_item is None
    upload_id, job_id = _committing(lena, "COMMITTING")
    _sweep(app_settings, keyring)
    status, state, items = _state(lena.tenant_id, upload_id, job_id)
    assert (status, state) == ("FAILED", "FAILED")
    assert items == [
        {
            "source": "IMPORT",
            "code": "IMPORT_PROCESSING_FAILED",
            "severity": "BLOCKING",
            "message": commit.NOT_COMMITTED.format(reference=job_id),
            "owner_membership_id": lena.membership_id,
        }
    ]
    with tenant_session(_db(lena.tenant_id), read_only=True) as session:
        actions = sorted(
            str(action)
            for action in session.execute(
                select(audit_event.c.action).where(audit_event.c.request_id == f"job-{job_id}")
            ).scalars()
        )
    # One transaction: the job's end, the upload's end and the item.
    assert actions == ["exception_item.create", "import_upload.fail", "job.finish"]


def test_a_commit_whose_worker_died_before_it_began_fails_the_import(
    lena: Member, app_settings: Settings, keyring: KeyRing
) -> None:
    """05 §5.6 rev 1.185 (the supervisor's ruling of 2026-10-02): a worker died before the import
    was ``COMMITTING`` — the job ``RUNNING``, the import still ``APPROVED``. The hook takes the
    import in the state its job found it in: ``APPROVED`` to ``COMMITTING`` to ``FAILED`` in the
    transaction that ends the job, with the item for its uploader. Before, the import stayed
    ``APPROVED`` for good: it can be neither cancelled nor submitted again."""
    upload_id, job_id = _committing(lena, "APPROVED")
    _sweep(app_settings, keyring)
    status, state, items = _state(lena.tenant_id, upload_id, job_id)
    assert (status, state) == ("FAILED", "FAILED")
    assert items == [
        {
            "source": "IMPORT",
            "code": "IMPORT_PROCESSING_FAILED",
            "severity": "BLOCKING",
            "message": commit.NOT_COMMITTED.format(reference=job_id),
            "owner_membership_id": lena.membership_id,
        }
    ]
    with tenant_session(_db(lena.tenant_id), read_only=True) as session:
        actions = sorted(
            str(action)
            for action in session.execute(
                select(audit_event.c.action).where(audit_event.c.request_id == f"job-{job_id}")
            ).scalars()
        )
    # One transaction, and the same three events as from COMMITTING: the move into the job's own
    # state writes none, as the handler's does not.
    assert actions == ["exception_item.create", "import_upload.fail", "job.finish"]


def test_job_failed_item_1_the_commit_hook_leaves_an_upload_that_ended_or_is_held(
    lena: Member, app_settings: Settings, keyring: KeyRing, log_stream: io.StringIO
) -> None:
    """Completed imports stay completed. A competing lock must not strand a COMMITTING
    import behind a FAILED job: required cleanup rolls settlement back after lock timeout,
    then a later sweep finishes both records when the competing holder has released it.
    The holder here is a different actor, not the job's own transaction/advisory lock.
    """
    committed, first = _committing(lena, "COMMITTED")
    held, second = _committing(lena, "COMMITTING")
    with tenant_session(_db(lena.tenant_id)) as holder:
        holder.execute(
            select(import_upload.c.id).where(import_upload.c.id == held).with_for_update()
        )
        _sweep(app_settings, keyring)
        assert _state(lena.tenant_id, held, second) == ("COMMITTING", "RUNNING", [])
    assert _state(lena.tenant_id, committed, first) == ("COMMITTED", "FAILED", [])
    # Required cleanup is retried after the competing command releases the upload.
    _sweep(app_settings, keyring)
    status, state, items = _state(lena.tenant_id, held, second)
    assert (status, state) == ("FAILED", "FAILED")
    assert len(items) == 1 and items[0]["code"] == "IMPORT_PROCESSING_FAILED"
    lines = [json.loads(raw) for raw in log_stream.getvalue().splitlines() if raw.strip()]
    mine = {str(first), str(second)}
    failures = [
        line for line in lines if line.get("job_id") in mine and line["event"] == "job.failed"
    ]
    assert sorted(line["job_id"] for line in failures) == sorted(mine)
    assert any(
        line.get("job_id") == str(second) and line["event"] == "job.failure_hook_failed"
        for line in lines
    )


def test_job_06_a_commit_in_flight_keeps_its_job_from_being_stopped(
    lena: Member, app_settings: Settings, keyring: KeyRing, log_stream: io.StringIO
) -> None:
    """05 JOB-06 rev 1.200 (item JOB-STALL-COMMIT-RACE-1): the case measured on 2026-10-02,
    turned round. The commit of an import is ONE unit of work, without a beat, and it holds the
    upload's row from its first statement. A unit of work of the job's attempt stands for it
    here. Ten minutes and a second into it the sweeper passes the job over - the hook is not
    reached, the upload is ``COMMITTING`` under a RUNNING job - and the commit then ends the
    upload ``COMMITTED`` under the job that is still its own, with a fresh heartbeat. Before,
    the job ended FAILED beside the open transaction, the hook left the held upload alone, the
    commit went through, and the member read "Nothing was committed." of an import that was."""
    upload_id, job_id = _committing(lena, "COMMITTING")
    with tenant_session(_db(lena.tenant_id), read_only=True) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
    clock = frozen_clock(FROZEN_AT)
    worker = JobRuntime(
        clock=clock,
        keyring=keyring,
        files=LocalFileStore(app_settings.file_root),
        attempt=JobAttempt(job_id=job_id, tenant_id=lena.tenant_id, task_id=task_id),
    )
    with system_unit_of_work(
        worker, system_principal(lena.tenant_id), request_id=f"job-{job_id}"
    ) as uow:
        uow.session.execute(
            select(import_upload.c.id).where(import_upload.c.id == upload_id).with_for_update()
        )
        clock.advance(STALL)
        _sweep(app_settings, keyring)
        assert _state(lena.tenant_id, upload_id, job_id) == ("COMMITTING", "RUNNING", [])
        apply(
            uow.session,
            commit.OBJECT_TYPE,
            upload_id,
            to_status="COMMITTED",
            set_values={"committed_at": uow.now},
            expected_status="COMMITTING",
        )
        uow.commit()
    assert _state(lena.tenant_id, upload_id, job_id) == ("COMMITTED", "RUNNING", [])
    with tenant_session(_db(lena.tenant_id), read_only=True) as session:
        heartbeat = session.execute(select(job.c.updated_at).where(job.c.id == job_id)).scalar_one()
    assert heartbeat == FROZEN_AT + STALL
    lines = [json.loads(raw) for raw in log_stream.getvalue().splitlines() if raw.strip()]
    assert [
        (line["event"], line["job_kind"], line["attempt"], line["silent_seconds"])
        for line in lines
        if line.get("job_id") == str(job_id)
    ] == [("job.sweep_passed_over", "IMPORT_COMMIT", 1, 601)]
