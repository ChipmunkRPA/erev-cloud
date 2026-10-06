"""The failure hook of ``IMPORT_DIFF`` (05 §5.6 rev 1.185; 04 T-IMP-02 rev 1.270, revision 0122;
PRD SM-05 and NTF-05 rev 1.186; the supervisor's ruling of 2026-10-02), as
``test_commit_job_failed`` is the commit's and ``test_validate_job_failed`` the validation's: a
dry run whose job ends FAILED ends the upload it finds ``VALIDATED`` or ``DIFFING``.

``import_diff`` has no catch-all, so every failed dry run reaches the hook. The fault at the
last attempt is witnessed in ``test_import_job_transient_db``; here the worker died — the job is
``RUNNING`` and silent, and the sweeper settles it ten minutes later — with the upload and the
job written as rows, as a dead worker leaves them. The job is the system's, as in the product:
the validation job defers it, so the job's own notification reaches nobody and the hook tells
the uploader.
"""

from __future__ import annotations

import io
import json
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import tenant_session
from erev_api.db.tables import import_upload, job, notification
from erev_api.db.transitions import apply
from erev_api.domain.imports import commit, diff, validate
from erev_api.enums import JobKind, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.sweeper import redispatch_stranded
from sqlalchemy import insert, select, text
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.principals import Member, member
from support.rows import ROW_BUILDERS, RowContext, insert_probe_row
from test_commit_job_failed import _FETCHED, _db, _state, _sweep

FINDING = ("IMPORT", "IMPORT_PROCESSING_FAILED", "BLOCKING")
_TASK_FAILED = text("UPDATE procrastinate_jobs SET status = 'failed' WHERE id = :id")


@pytest.fixture
def lena(committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> Member:
    return member(keyring, clock)


def _diffing(
    someone: Member, status: str, *, attempt: int = 2, named: list[UUID] | None = None
) -> tuple[UUID, UUID]:
    """An upload of ``someone`` in ``status`` and its RUNNING dry-run job at ``attempt``, started
    by the system, as a worker that died left them: (upload id, job id)."""
    with tenant_session(_db(someone.tenant_id)) as session:
        row = dict(
            ROW_BUILDERS["import_upload"](RowContext(someone.tenant_id, someone.user_id), session)
        )
        row.update(
            status=status,
            created_by=someone.user_id,
            created_by_kind="USER",
            named_entity_ids=named,
        )
        session.execute(insert(import_upload).values(**row))
        upload_id = UUID(str(row["id"]))
        queued = registry.insert_job(
            session,
            JobKind.IMPORT_DIFF,
            {"import_upload_id": str(upload_id)},
            tenant_id=someone.tenant_id,
            now=FROZEN_AT,
            created_by=None,
            created_by_kind=PrincipalKind.SYSTEM,
            subject_type=diff.OBJECT_TYPE,
            subject_id=upload_id,
        )
        registry.dispatch(
            session,
            job_id=queued["id"],
            tenant_id=someone.tenant_id,
            queue=str(queued["queue"]),
            now=FROZEN_AT,
            attempt=attempt,
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


def _told(tenant_id: UUID, job_id: UUID) -> list[dict[str, Any]]:
    """The notifications about the job, and what the job's stored problem gives as its reason."""
    with tenant_session(_db(tenant_id), read_only=True) as session:
        found = (
            session.execute(
                select(
                    notification.c.kind,
                    notification.c.recipient_membership_id,
                    notification.c.title,
                    notification.c.body,
                ).where(notification.c.subject_id == job_id)
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in found]


def _reason(tenant_id: UUID, job_id: UUID) -> str:
    with tenant_session(_db(tenant_id), read_only=True) as session:
        problem = session.execute(select(job.c.problem).where(job.c.id == job_id)).scalar_one()
    return str(problem.get("detail") or problem["title"]).rstrip(".")


@pytest.mark.parametrize("status", ["DIFFING", "VALIDATED"])
def test_a_dry_run_whose_worker_died_at_its_last_attempt_ends_its_upload_invalid(
    lena: Member, app_settings: Settings, keyring: KeyRing, status: str
) -> None:
    """A worker died at the job's second attempt — while the upload was ``DIFFING``, or before
    it had left ``VALIDATED``. The sweeper ends the job FAILED and the kind's failure hook ends
    the upload ``INVALID`` with ``IMPORT_PROCESSING_FAILED`` under the job's reference: the pair
    of revision 0122, reached from ``VALIDATED`` through ``DIFFING``. Lena, who uploaded the
    file, is told in the words of PRD NTF-05. Before, the upload stayed where it was for good
    and nobody was told."""
    upload_id, job_id = _diffing(lena, status)
    _sweep(app_settings, keyring)
    found, state, items = _state(lena.tenant_id, upload_id, job_id)
    assert (found, state) == ("INVALID", "FAILED")
    assert [(item["source"], item["code"], item["severity"]) for item in items] == [FINDING]
    assert items[0]["message"] == validate.processing_failed(f"job-{job_id}")
    reason = _reason(lena.tenant_id, job_id)
    assert _told(lena.tenant_id, job_id) == [
        {
            "kind": "JOB_FAILED",
            "recipient_membership_id": lena.membership_id,
            "title": "Job failed: Import dry run",
            "body": f"Import dry run failed at its last attempt: {reason}. Nothing was committed.",
        }
    ]


def test_a_dry_run_that_stalls_before_its_last_attempt_is_run_again(
    lena: Member, app_settings: Settings, keyring: KeyRing
) -> None:
    """The hook is the job's end, not an attempt's: a worker that died at the first of two
    attempts leaves the upload ``DIFFING`` behind a re-queued job, with nothing said."""
    upload_id, job_id = _diffing(lena, "DIFFING", attempt=1)
    _sweep(app_settings, keyring)
    assert _state(lena.tenant_id, upload_id, job_id) == ("DIFFING", "QUEUED", [])
    assert _told(lena.tenant_id, job_id) == []


def test_the_dry_run_hook_leaves_an_upload_that_ended_or_is_held(
    lena: Member, app_settings: Settings, keyring: KeyRing, log_stream: io.StringIO
) -> None:
    """The hook ends only an upload that is ``VALIDATED`` or ``DIFFING`` and that nobody holds:
    an upload whose diff was stored before the worker died stays ``DIFF_READY``, one its uploader
    cancelled stays ``CANCELLED``, and an upload whose row another transaction holds is not
    waited for; it is that transaction's to end. Since 05 JOB-06 rev 1.200 the holder is never
    the job's own dry run, whose open transaction keeps the job from being stopped; the session
    here holds the row without the job's lock, as a transaction of another actor would."""
    ready, first = _diffing(lena, "DIFF_READY")
    cancelled, second = _diffing(lena, "CANCELLED")
    held, third = _diffing(lena, "DIFFING")
    with tenant_session(_db(lena.tenant_id)) as holder:
        holder.execute(
            select(import_upload.c.id).where(import_upload.c.id == held).with_for_update()
        )
        _sweep(app_settings, keyring)
    assert _state(lena.tenant_id, ready, first) == ("DIFF_READY", "FAILED", [])
    assert _state(lena.tenant_id, cancelled, second) == ("CANCELLED", "FAILED", [])
    assert _state(lena.tenant_id, held, third) == ("DIFFING", "FAILED", [])
    for job_id in (first, second, third):
        assert _told(lena.tenant_id, job_id) == []
    # Not waited for and not refused: the hook returned for each — it did not fail on the held
    # row's lock, nor on a transition no upload makes.
    lines = [json.loads(raw) for raw in log_stream.getvalue().splitlines() if raw.strip()]
    mine = {str(first), str(second), str(third)}
    assert [line["event"] for line in lines if line.get("job_id") in mine] == ["job.failed"] * 3


def test_a_failed_dry_run_of_an_upload_that_names_one_entity_leaves_its_finding_alone(
    lena: Member, app_settings: Settings, keyring: KeyRing
) -> None:
    """The upload's finding is the one item of a failed dry run (05 §5.6 rev 1.185; 04 §15.4
    ``JOB_FAILED`` rev 1.270; the supervisor's ruling of 2026-10-02). The kind registers no
    ``failed_item`` — a kind whose hook raises an item of its own registers none
    (``jobs.registry.task``) — so an upload that names exactly one legal entity gets no
    ``INFO`` item ``JOB_FAILED`` beside it. Before the ruling it did, and that item's text
    promised a later run of the record, which an ``INVALID`` import never has."""
    with tenant_session(_db(lena.tenant_id)) as session:
        entity = insert_probe_row(session, "legal_entity", RowContext(lena.tenant_id, lena.user_id))
    upload_id, job_id = _diffing(lena, "DIFFING", named=[UUID(str(entity["id"]))])
    _sweep(app_settings, keyring)
    found, state, items = _state(lena.tenant_id, upload_id, job_id)
    assert (found, state) == ("INVALID", "FAILED")
    assert [(item["source"], item["code"], item["severity"]) for item in items] == [FINDING]
    assert registry.HANDLERS[JobKind.IMPORT_DIFF].failed_item is None


def _stranded(someone: Member, kind: JobKind, status: str, *, attempt: int) -> tuple[UUID, UUID]:
    """An upload of ``someone`` in ``status`` and its job of ``kind``, QUEUED under a task that
    failed at ``attempt`` before the job started — a job that can no longer be run
    (``jobs.registry.retry_stranded``): (upload id, job id)."""
    by_system = kind is JobKind.IMPORT_DIFF  # the validation job defers the dry run
    with tenant_session(_db(someone.tenant_id)) as session:
        row = dict(
            ROW_BUILDERS["import_upload"](RowContext(someone.tenant_id, someone.user_id), session)
        )
        row.update(status=status, created_by=someone.user_id, created_by_kind="USER")
        session.execute(insert(import_upload).values(**row))
        upload_id = UUID(str(row["id"]))
        queued = registry.insert_job(
            session,
            kind,
            {"import_upload_id": str(upload_id)},
            tenant_id=someone.tenant_id,
            now=FROZEN_AT,
            created_by=None if by_system else someone.user_id,
            created_by_kind=PrincipalKind.SYSTEM if by_system else PrincipalKind.USER,
            subject_type=diff.OBJECT_TYPE,
            subject_id=upload_id,
        )
        registry.dispatch(
            session,
            job_id=queued["id"],
            tenant_id=someone.tenant_id,
            queue=str(queued["queue"]),
            now=FROZEN_AT,
            attempt=attempt,
        )
        job_id = UUID(str(queued["id"]))
    with tenant_session(_db(someone.tenant_id)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_TASK_FAILED, {"id": task_id})
    return upload_id, job_id


@pytest.mark.parametrize(
    ("kind", "found", "ended", "message"),
    [
        (JobKind.IMPORT_VALIDATE, "UPLOADED", "INVALID", validate.processing_failed("job-{job}")),
        (JobKind.IMPORT_DIFF, "VALIDATED", "INVALID", validate.processing_failed("job-{job}")),
        (
            JobKind.IMPORT_COMMIT,
            "APPROVED",
            "FAILED",
            commit.NOT_COMMITTED.format(reference="{job}"),
        ),
    ],
    ids=["validation", "dry-run", "commit"],
)
def test_a_job_that_failed_while_queued_ends_the_upload_it_never_began(
    lena: Member,
    app_settings: Settings,
    keyring: KeyRing,
    kind: JobKind,
    found: str,
    ended: str,
    message: str,
) -> None:
    """The third way a job ends FAILED (05 JOB-06; ``jobs.registry.retry_stranded``): its worker
    task failed at the kind's last attempt before the job started, so the job is still QUEUED and
    the upload still in the state the job found it in. The sweeper settles the job, and the
    kind's hook takes the upload there and ends it — through the job's own state, with the
    finding under the job's reference. Before, the upload stayed ``UPLOADED``, ``VALIDATED`` or
    ``APPROVED`` behind a FAILED job."""
    last = registry.HANDLERS[kind].retry.max_attempts
    upload_id, job_id = _stranded(lena, kind, found, attempt=last)
    settled = redispatch_stranded(
        JobRuntime(
            clock=frozen_clock(FROZEN_AT),
            keyring=keyring,
            files=LocalFileStore(app_settings.file_root),
        )
    )
    assert settled == 1
    status, state, items = _state(lena.tenant_id, upload_id, job_id)
    assert (status, state) == (ended, "FAILED")
    assert [(item["source"], item["code"], item["severity"]) for item in items] == [FINDING]
    assert items[0]["message"] == message.format(job=job_id)
