"""The failure hook of ``IMPORT_VALIDATE`` (05 §5.6 rev 1.185; supervisor rulings R-108 (2) and
R-105 (2) and the supervisor's ruling of 2026-10-02), as ``test_commit_job_failed`` is the
commit's: a validation job that ends FAILED without its handler's own ending ends the upload it
finds ``UPLOADED`` or ``VALIDATING``.

The handler ends the upload for every error it stores. The hook is reached when it stored none:
the last attempt met a transient database error or failed before the upload was ``VALIDATING``
(``test_import_job_transient_db``), or the worker died — the job is ``RUNNING`` and silent, and
the sweeper settles it ten minutes later. The last is witnessed here, with the upload and the
job written as rows as in ``test_commit_job_failed``; the settlement is the product's
(``fail_stalled`` → ``fail_attempt`` → ``_fail_job`` → the hook). ``IMPORT_VALIDATE`` takes two
attempts, so the sweeper's first pass re-queues the job and the second ends it.
"""

from __future__ import annotations

import io
import json
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import tenant_session
from erev_api.db.tables import import_upload, job
from erev_api.db.transitions import apply
from erev_api.domain.imports import validate
from erev_api.enums import JobKind, PrincipalKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.sweeper import fail_stalled
from sqlalchemy import insert, select
from support.clock import FROZEN_AT, frozen_clock
from support.db import TestDatabase
from support.principals import Member, member
from support.rows import ROW_BUILDERS, RowContext
from test_commit_job_failed import _FETCHED, STALL, _db, _state
from test_diff_job_failed import _told


@pytest.fixture
def lena(committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> Member:
    return member(keyring, clock)


def _validating(someone: Member, status: str, *, attempt: int) -> tuple[UUID, UUID]:
    """An upload of ``someone`` in ``status`` and its RUNNING validation job at ``attempt``, as a
    worker that died left them: (upload id, job id)."""
    with tenant_session(_db(someone.tenant_id)) as session:
        row = dict(
            ROW_BUILDERS["import_upload"](RowContext(someone.tenant_id, someone.user_id), session)
        )
        row.update(status=status, created_by=someone.user_id, created_by_kind="USER")
        session.execute(insert(import_upload).values(**row))
        upload_id = UUID(str(row["id"]))
        queued = registry.insert_job(
            session,
            JobKind.IMPORT_VALIDATE,
            {"import_upload_id": str(upload_id)},
            tenant_id=someone.tenant_id,
            now=FROZEN_AT,
            created_by=someone.user_id,
            created_by_kind=PrincipalKind.USER,
            subject_type=validate.OBJECT_TYPE,
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


def _sweep(app_settings: Settings, keyring: KeyRing) -> None:
    fail_stalled(
        JobRuntime(
            clock=frozen_clock(FROZEN_AT + STALL),
            keyring=keyring,
            files=LocalFileStore(app_settings.file_root),
        )
    )


@pytest.mark.parametrize("status", ["VALIDATING", "UPLOADED"])
def test_a_validation_whose_worker_died_at_its_last_attempt_ends_its_upload_invalid(
    lena: Member, app_settings: Settings, keyring: KeyRing, status: str
) -> None:
    """A worker died at the job's second attempt — while the upload was ``VALIDATING``, or before
    it had left ``UPLOADED``. The sweeper ends the job FAILED and the kind's failure hook ends
    the upload ``INVALID`` with ``IMPORT_PROCESSING_FAILED`` under the job's reference, as the
    handler does after an error it stores — from ``UPLOADED`` through ``VALIDATING``. Before, the
    upload stayed where it was for good."""
    upload_id, job_id = _validating(lena, status, attempt=2)
    _sweep(app_settings, keyring)
    found, state, items = _state(lena.tenant_id, upload_id, job_id)
    assert (found, state) == ("INVALID", "FAILED")
    assert [(item["source"], item["code"], item["severity"]) for item in items] == [
        ("IMPORT", "IMPORT_PROCESSING_FAILED", "BLOCKING")
    ]
    assert items[0]["message"] == validate.processing_failed(f"job-{job_id}")


def test_the_validation_hook_leaves_an_upload_that_ended_or_is_held(
    lena: Member, app_settings: Settings, keyring: KeyRing, log_stream: io.StringIO
) -> None:
    """The hook ends only an upload that is ``UPLOADED`` or ``VALIDATING`` and that nobody
    holds: an upload whose validation had committed before the worker died stays ``VALIDATED``,
    and an upload whose row another transaction holds is not waited for; it is that
    transaction's to end. Since 05 JOB-06 rev 1.200 the holder is never the job's own
    validation, whose open transaction keeps the job from being stopped; the session here holds
    the row without the job's lock, as a transaction of another actor would."""
    validated, first = _validating(lena, "VALIDATED", attempt=2)
    held, second = _validating(lena, "VALIDATING", attempt=2)
    with tenant_session(_db(lena.tenant_id)) as holder:
        holder.execute(
            select(import_upload.c.id).where(import_upload.c.id == held).with_for_update()
        )
        _sweep(app_settings, keyring)
    assert _state(lena.tenant_id, validated, first) == ("VALIDATED", "FAILED", [])
    assert _state(lena.tenant_id, held, second) == ("VALIDATING", "FAILED", [])
    # What is still said of a job that failed after its result was stored: the job's row reads
    # FAILED and its initiator — the uploader — is told (PRD NTF-05); no item (04 §15.4).
    assert [
        (row["kind"], row["recipient_membership_id"]) for row in _told(lena.tenant_id, first)
    ] == [("JOB_FAILED", lena.membership_id)]
    # Not waited for and not refused: the hook returned for both — it did not fail on the held
    # row's lock, nor on a transition no upload makes.
    lines = [json.loads(raw) for raw in log_stream.getvalue().splitlines() if raw.strip()]
    mine = {str(first), str(second)}
    assert [line["event"] for line in lines if line.get("job_id") in mine] == ["job.failed"] * 2
