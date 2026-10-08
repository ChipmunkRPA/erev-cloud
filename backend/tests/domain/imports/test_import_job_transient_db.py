"""A database that could not do it now is no result about the file, and an import never waits
behind a job that has ended (supervisor rulings R-108 (2) and R-105 (2) and the supervisor's
rulings of 2026-10-02; 05 §5.6 and IPL-02, IPL-07, IPL-10 rev 1.185; 04 T-IMP-02 rev 1.270; PRD
SM-05 and NTF-05 rev 1.186; ``db.errors.is_transient``; ``domain.imports.job_hooks``).

A transient database error met by the validation or the commit of an import leaves the handler:
the attempt fails, nothing is stored for the upload, and the job is settled by its retry policy —
re-queued while attempts remain, FAILED after the last. The dry run has no catch-all and always
did so. A job that ends FAILED ends its upload through the kind's failure hook, in the same
transaction, when the upload is still in the state the job found it in or in the job's own:
``UPLOADED`` or ``VALIDATING`` and ``VALIDATED`` or ``DIFFING`` end ``INVALID``, ``APPROVED`` or
``COMMITTING`` ends ``FAILED``, each with ``IMPORT_PROCESSING_FAILED`` under the job's reference
and the uploader told.

How many attempts a kind takes is the retry table's (05 §5.6; item JOB-RETRY-TABLE-1), so every
test here states the policy it runs under — one attempt and two, for each kind — and holds
whatever the table gives the kind.

Before, the catch-alls of the validation and the commit stored a failure for any exception: a
serialization failure during the validation made the upload INVALID with
``IMPORT_PROCESSING_FAILED`` at the first attempt and ended the job SUCCEEDED_WITH_EXCEPTIONS — a
wait recorded as a finding about the file, with a second attempt never made — and one during the
commit failed the import and ended the job SUCCEEDED_WITH_EXCEPTIONS. A dry run that failed left
its upload ``DIFFING`` with nobody told. A fault before the upload entered the job's state left
it where it was: ``UPLOADED``, ``VALIDATED`` — or ``APPROVED``, which can be neither cancelled nor
submitted again.

The fault is injected at the session level, as in
``tests/domain/contracts/test_server_unavailable_compute.py``: the stage function of the job
makes the server itself raise the SQLSTATE through the unit of work's own session, so the driver
error, SQLAlchemy's wrapping and the transaction state are the real ones. World:
``support.factories.import_world`` (Maya uploads a ``customers`` file; Priya approves). The dead
worker is witnessed on rows in ``test_validate_job_failed``, ``test_diff_job_failed`` and
``test_commit_job_failed``.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    customer,
    exception_item,
    import_row,
    import_upload,
    job,
    notification,
)
from erev_api.domain.imports import commit, diff, templates, validate
from erev_api.enums import JobKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import system_unit_of_work
from erev_api.jobs.registry import RetryPolicy, run_job
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import exc, select, text
from support.db import TestDatabase
from support.factories import (
    IMPORTS_PATH,
    ImportWorld,
    create_import,
    import_world,
    upload_import_source,
)
from support.http import call
from support.principals import Actor, colleague, cookie_headers, enrolled
from support.reference import approve, assign, get, post

_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
# The server raises the code itself, as it does when two transactions meet.
_SERIALIZATION_FAILURE = text(
    "DO $fault$ BEGIN RAISE EXCEPTION 'could not serialize access due to concurrent update' "
    "USING ERRCODE = '40001'; END $fault$"
)
HEADERS = ("code", "name", "segment", "country_code")
CUSTOMERS = (
    ("C-701", "Harbourline Freight Ltd (Demo)", "Logistics", "PT"),
    ("C-702", "Orla Quay Foods SA (Demo)", "Food", "ES"),
    ("C-703", "Tamsin Row Studios LLP (Demo)", "Media", "GB"),
)
PROCESSING_FAILED = "IMPORT_PROCESSING_FAILED"
FAILED_FINDING = [{"code": PROCESSING_FAILED, "severity": "ERROR", "rows": 0}]
# PRD NTF-05, as the dry run's hook words it for the uploader.
DRY_RUN_FAILED = (
    "Job failed: Import dry run",
    "Import dry run failed at its last attempt: The job stopped with an unexpected error. "
    "Nothing was committed.",
)
Arm = Callable[[ModuleType, str, Callable[[Any], None], int], list[int]]
Policy = Callable[[JobKind, int], None]


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> ImportWorld:
    return import_world(app, keyring, clock, files)


@pytest.fixture
def fault(monkeypatch: pytest.MonkeyPatch) -> Arm:
    """Arm a failure of the first ``times`` calls of a job's stage function; the list counts its
    calls since. The failing call raises inside the unit of work the handler opened for it."""

    def arm(module: ModuleType, name: str, fail: Callable[[Any], None], times: int) -> list[int]:
        calls: list[int] = []
        real = getattr(module, name)

        def stage(uow: Any, *args: Any, **kwargs: Any) -> Any:
            calls.append(len(calls) + 1)
            if len(calls) <= times:
                fail(uow)
            return real(uow, *args, **kwargs)

        monkeypatch.setattr(module, name, stage)
        return calls

    return arm


@pytest.fixture
def attempts(monkeypatch: pytest.MonkeyPatch) -> Policy:
    """Give a kind ``count`` attempts for the test, whatever its handler is registered with."""

    def give(kind: JobKind, count: int) -> None:
        policy = RetryPolicy(max_attempts=count, backoff_seconds=(10,) * (count - 1))
        spec = registry.HANDLERS[kind]
        monkeypatch.setitem(registry.HANDLERS, kind, replace(spec, retry=policy))

    return give


def _could_not_serialize(uow: Any) -> None:
    uow.session.execute(_SERIALIZATION_FAILURE)


def _defect(uow: Any) -> None:
    raise RuntimeError("a programming error inside the job")


def customers_csv(rows: Sequence[Sequence[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADERS)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _work(world: ImportWorld, job_id: UUID, *, attempt: int) -> int:
    """Act as the worker for the job's current task; returns that task's id."""
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = int(
            session.execute(
                select(job.c.procrastinate_job_id).where(job.c.id == job_id)
            ).scalar_one()
        )
        session.execute(_FETCHED, {"id": task_id})
    run_job(job_id, world.tenant_id, attempt=attempt, runtime=world.runtime)
    return task_id


def _job(world: ImportWorld, job_id: UUID) -> dict[str, Any]:
    response = get(world.app, f"/api/v1/jobs/{job_id}", world.actor)
    assert response.status_code == 200, response.text
    return dict(response.json())


def _job_of(world: ImportWorld, import_id: str, kind: str) -> UUID:
    rows = world.rows(
        select(job.c.id)
        .where(job.c.subject_id == UUID(import_id), job.c.kind == kind)
        .order_by(job.c.created_at)
    )
    assert rows, f"no {kind} job for {import_id}"
    return UUID(str(rows[-1]["id"]))


def _shown(world: ImportWorld, import_id: str) -> dict[str, Any]:
    response = get(world.app, f"{IMPORTS_PATH}/{import_id}", world.actor)
    assert response.status_code == 200, response.text
    return dict(response.json())


def _items(world: ImportWorld, import_id: str) -> list[dict[str, Any]]:
    return world.rows(
        select(
            exception_item.c.id,
            exception_item.c.code,
            exception_item.c.status,
            exception_item.c.message,
            exception_item.c.owner_membership_id,
        ).where(exception_item.c.import_upload_id == UUID(import_id))
    )


def _rows(world: ImportWorld, import_id: str) -> int:
    return len(
        world.rows(select(import_row.c.id).where(import_row.c.import_upload_id == UUID(import_id)))
    )


def _loaded(world: ImportWorld) -> list[str]:
    """The customers of the file that exist."""
    codes = [row[0] for row in CUSTOMERS]
    found = world.rows(
        select(customer.c.code).where(customer.c.code.in_(codes)).order_by(customer.c.code)
    )
    return [str(row["code"]) for row in found]


def _told(world: ImportWorld, subject_id: UUID) -> list[tuple[str, UUID]]:
    """(kind, recipient's membership) of every notification about ``subject_id`` — a job (05
    JOB-07; PRD NTF-05) or an exception item (PRD NTF-11)."""
    found = world.rows(
        select(notification.c.kind, notification.c.recipient_membership_id)
        .where(notification.c.subject_id == subject_id)
        .order_by(notification.c.created_at, notification.c.id)
    )
    return [(str(row["kind"]), UUID(str(row["recipient_membership_id"]))) for row in found]


def _words(world: ImportWorld, subject_id: UUID) -> list[tuple[str, str]]:
    """(title, body) of the notifications about ``subject_id``."""
    found = world.rows(
        select(notification.c.title, notification.c.body).where(
            notification.c.subject_id == subject_id
        )
    )
    return [(str(row["title"]), str(row["body"])) for row in found]


def _uploader(world: ImportWorld) -> UUID:
    return world.actor.member.membership_id


def _uploaded(world: ImportWorld) -> tuple[str, UUID]:
    """A ``customers`` file of three rows, uploaded: the import and its validation job."""
    file_id = upload_import_source(world, "crm-customers.csv", customers_csv(CUSTOMERS))
    created = create_import(world, file_id, "customers")
    assert created.status_code == 202, created.text
    import_id = str(created.headers["X-Erev-Import-Id"])
    assert _shown(world, import_id)["status"] == "UPLOADED"
    return import_id, UUID(str(created.json()["id"]))


def _validated(world: ImportWorld) -> tuple[str, UUID]:
    """The file validated: the import and its dry-run job, not yet run."""
    import_id, job_id = _uploaded(world)
    _work(world, job_id, attempt=1)
    assert _shown(world, import_id)["status"] == "VALIDATED"
    return import_id, _job_of(world, import_id, "IMPORT_DIFF")


def _approved_by(world: ImportWorld) -> tuple[str, UUID, UUID, Actor]:
    """The file validated, diffed, submitted by Maya and approved by Priya: the import, its
    commit job, not yet run, and Priya's membership — Priya's decision started that job."""
    someone = colleague(world.tenant_id, "priya")
    assign(someone, "revenue_reviewer")
    priya: Actor = enrolled(world.app, world.clock, someone)
    import_id, diff_job = _validated(world)
    _work(world, diff_job, attempt=1)
    assert _shown(world, import_id)["status"] == "DIFF_READY"
    headers = cookie_headers(
        world.actor.token, world.actor.csrf_token, key=False, **{"Idempotency-Key": f"k-{uuid4()}"}
    )
    submitted = call(
        world.app,
        "POST",
        f"{IMPORTS_PATH}/{import_id}/submit",
        json={"comment": "Customer master from the CRM export"},
        headers=headers,
    )
    assert submitted.status_code == 200, submitted.text
    decided = approve(world.app, str(submitted.json()["approval_request_id"]), priya)
    assert decided.status_code == 200, decided.text
    assert _shown(world, import_id)["status"] == "APPROVED"
    return import_id, _job_of(world, import_id, "IMPORT_COMMIT"), someone.membership_id, priya


def _approved(world: ImportWorld) -> tuple[str, UUID, UUID]:
    import_id, job_id, membership_id, _ = _approved_by(world)
    return import_id, job_id, membership_id


def _ended_invalid(world: ImportWorld, import_id: str, job_id: UUID) -> dict[str, Any]:
    """What a failed validation or dry run leaves: the job FAILED, the upload INVALID with the
    one finding, and one open item under the job's reference. Returns the import as shown."""
    failed = _job(world, job_id)
    assert failed["state"] == "FAILED", failed
    assert failed["problem"]["instance"] == f"/api/v1/jobs/{job_id}", failed
    ended = _shown(world, import_id)
    assert (ended["status"], ended["finding_counts"]) == ("INVALID", FAILED_FINDING), ended
    (item,) = _items(world, import_id)
    assert (item["code"], str(item["status"])) == (PROCESSING_FAILED, "OPEN")
    assert item["message"] == validate.processing_failed(f"job-{job_id}")
    return ended


def _ended_failed(world: ImportWorld, import_id: str, commit_job: UUID, approver: UUID) -> None:
    """What a failed commit leaves: the job FAILED — not SUCCEEDED_WITH_EXCEPTIONS, as a result
    about the file would — the import FAILED with one item under the job's reference, assigned to
    the uploader, nothing committed; the approver, whose decision started the job, told that it
    failed (PRD NTF-05) and the uploader told of the item (PRD NTF-11)."""
    failed = _job(world, commit_job)
    assert failed["state"] == "FAILED", failed
    assert failed["problem"]["instance"] == f"/api/v1/jobs/{commit_job}", failed
    assert _shown(world, import_id)["status"] == "FAILED"
    (item,) = _items(world, import_id)
    assert (item["code"], str(item["status"])) == (PROCESSING_FAILED, "OPEN")
    assert item["message"] == commit.NOT_COMMITTED.format(reference=commit_job)
    assert item["owner_membership_id"] == _uploader(world)
    assert _loaded(world) == []
    assert _told(world, commit_job) == [("JOB_FAILED", approver)]
    assert _told(world, UUID(str(item["id"]))) == [("EXCEPTION_ASSIGNED", _uploader(world))]


# --- the validation -------------------------------------------------------------------------------


def test_a_wait_in_the_validation_is_retried_and_the_file_is_validated(
    world: ImportWorld, fault: Arm, attempts: Policy
) -> None:
    """Two attempts (05 §5.6). The first meets a serialization failure inside the validation's
    unit of work: nothing is stored for the upload — it stays VALIDATING without a finding, a row
    or an exception item — and the job is re-queued under a new task. The second attempt
    validates the file. Before: INVALID at the first attempt, and no second."""
    attempts(JobKind.IMPORT_VALIDATE, 2)
    import_id, job_id = _uploaded(world)
    calls = fault(validate, "validate_upload", _could_not_serialize, 1)

    first_task = _work(world, job_id, attempt=1)
    assert calls == [1]
    waiting = _shown(world, import_id)
    assert (waiting["status"], waiting["finding_counts"]) == ("VALIDATING", []), waiting
    assert _items(world, import_id) == [] and _rows(world, import_id) == 0
    queued = _job(world, job_id)
    assert (queued["state"], queued["problem"]) == ("QUEUED", None), queued

    second_task = _work(world, job_id, attempt=2)
    assert second_task != first_task, "the retry is a new task"
    assert calls == [1, 2]
    done = _shown(world, import_id)
    assert (done["status"], done["counts"]["rows"], done["counts"]["valid"]) == (
        "VALIDATED",
        3,
        3,
    ), done
    assert done["finding_counts"] == [] and _items(world, import_id) == []
    assert _job(world, job_id)["state"] == "SUCCEEDED"
    assert _told(world, job_id) == []


@pytest.mark.parametrize("count", [1, 2], ids=["one-attempt", "two-attempts"])
def test_a_validation_that_waits_at_its_last_attempt_is_ended_by_the_jobs_hook(
    world: ImportWorld, fault: Arm, attempts: Policy, count: int
) -> None:
    """Every attempt meets the fault, under a policy of one attempt and of two. Until the last
    the upload is VALIDATING behind a queued job with nothing stored; the last ends the job
    FAILED, and the same transaction makes the upload INVALID with ``IMPORT_PROCESSING_FAILED``
    under the job's reference and tells the uploader, who started the job, that it failed. No
    upload stays VALIDATING behind a job that has ended."""
    attempts(JobKind.IMPORT_VALIDATE, count)
    import_id, job_id = _uploaded(world)
    calls = fault(validate, "validate_upload", _could_not_serialize, count)

    for attempt in range(1, count):
        _work(world, job_id, attempt=attempt)
        assert _shown(world, import_id)["status"] == "VALIDATING"
        assert _job(world, job_id)["state"] == "QUEUED"
        assert _items(world, import_id) == []

    _work(world, job_id, attempt=count)
    assert calls == list(range(1, count + 1))
    _ended_invalid(world, import_id, job_id)
    assert _rows(world, import_id) == 0
    assert _told(world, job_id) == [("JOB_FAILED", _uploader(world))]


@pytest.mark.parametrize("count", [1, 2], ids=["one-attempt", "two-attempts"])
def test_a_validation_that_fails_before_it_began_ends_the_upload_invalid(
    world: ImportWorld, fault: Arm, attempts: Policy, count: int
) -> None:
    """The fault comes in the handler's first unit of work, before the upload is VALIDATING —
    outside the catch-all, so the error left the handler before rev 1.185 as after. Until the
    last attempt the upload is UPLOADED behind a queued job; the last ends the job FAILED and the
    hook takes the upload in the state the job found it in: UPLOADED to VALIDATING to INVALID in
    the job's last transaction, by the handler's own function (its call after the armed ones),
    with the finding and the uploader told. Before, the upload stayed UPLOADED."""
    attempts(JobKind.IMPORT_VALIDATE, count)
    import_id, job_id = _uploaded(world)
    calls = fault(validate, "start_validation", _could_not_serialize, count)

    for attempt in range(1, count):
        _work(world, job_id, attempt=attempt)
        assert _shown(world, import_id)["status"] == "UPLOADED"
        assert _job(world, job_id)["state"] == "QUEUED"
        assert _items(world, import_id) == []

    _work(world, job_id, attempt=count)
    _ended_invalid(world, import_id, job_id)
    assert _rows(world, import_id) == 0
    assert _told(world, job_id) == [("JOB_FAILED", _uploader(world))]
    assert calls == list(range(1, count + 2)), "the hook made the one call after the armed ones"


def test_any_other_error_is_still_stored_at_once(
    world: ImportWorld, fault: Arm, attempts: Policy
) -> None:
    """The boundary: a defect inside the validation keeps the documented behaviour — the upload
    is INVALID with ``IMPORT_PROCESSING_FAILED`` at the first attempt, the job ends
    SUCCEEDED_WITH_EXCEPTIONS, and no second attempt is asked for although one is left."""
    attempts(JobKind.IMPORT_VALIDATE, 2)
    import_id, job_id = _uploaded(world)
    calls = fault(validate, "validate_upload", _defect, 1)

    _work(world, job_id, attempt=1)
    assert calls == [1]
    ended = _shown(world, import_id)
    assert (ended["status"], ended["finding_counts"]) == ("INVALID", FAILED_FINDING), ended
    assert [row["code"] for row in _items(world, import_id)] == [PROCESSING_FAILED]
    assert _job(world, job_id)["state"] == "SUCCEEDED_WITH_EXCEPTIONS"
    assert _told(world, job_id) == []


# --- the commit -----------------------------------------------------------------------------------


def test_a_wait_in_the_commit_is_retried_where_the_kind_has_another_attempt(
    world: ImportWorld, fault: Arm, attempts: Policy
) -> None:
    """Under a policy of two attempts — whatever the retry table gives ``IMPORT_COMMIT`` — the
    first attempt meets a serialization failure inside the commit's unit of work: nothing is
    committed and nothing stored, the import stays COMMITTING behind a re-queued job, and the
    second attempt commits the file. The unit of work of the first attempt rolled back, so the
    second starts from the approved import as the first did."""
    attempts(JobKind.IMPORT_COMMIT, 2)
    import_id, commit_job, _ = _approved(world)
    calls = fault(commit, "commit_upload", _could_not_serialize, 1)

    first_task = _work(world, commit_job, attempt=1)
    assert calls == [1]
    assert _shown(world, import_id)["status"] == "COMMITTING"
    assert (_items(world, import_id), _loaded(world)) == ([], [])
    queued = _job(world, commit_job)
    assert (queued["state"], queued["problem"]) == ("QUEUED", None), queued

    second_task = _work(world, commit_job, attempt=2)
    assert second_task != first_task, "the retry is a new task"
    assert calls == [1, 2]
    assert _shown(world, import_id)["status"] == "COMMITTED"
    assert _loaded(world) == [row[0] for row in CUSTOMERS]
    assert _items(world, import_id) == []
    assert _job(world, commit_job)["state"] == "SUCCEEDED"
    assert _told(world, commit_job) == []


@pytest.mark.parametrize("count", [1, 2], ids=["one-attempt", "two-attempts"])
def test_a_commit_that_waits_at_its_last_attempt_fails_the_job_and_the_import(
    world: ImportWorld, fault: Arm, attempts: Policy, count: int
) -> None:
    """Every attempt meets the fault, under a policy of one attempt (what 05 §5.6 registers
    today: a failed commit rolls back; the user resubmits) and of two. The last ends the job
    FAILED and the kind's failure hook fails the import under the job's reference in the same
    transaction (``_ended_failed``). Before: the handler stored the failure itself and the job
    ended SUCCEEDED_WITH_EXCEPTIONS."""
    attempts(JobKind.IMPORT_COMMIT, count)
    import_id, commit_job, approver = _approved(world)
    calls = fault(commit, "commit_upload", _could_not_serialize, count)

    for attempt in range(1, count):
        _work(world, commit_job, attempt=attempt)
        assert _shown(world, import_id)["status"] == "COMMITTING"
        assert _job(world, commit_job)["state"] == "QUEUED"
        assert _items(world, import_id) == []

    _work(world, commit_job, attempt=count)
    assert calls == list(range(1, count + 1))
    _ended_failed(world, import_id, commit_job, approver)


@pytest.mark.parametrize("count", [1, 2], ids=["one-attempt", "two-attempts"])
def test_a_commit_that_fails_before_it_began_fails_the_import(
    world: ImportWorld, fault: Arm, attempts: Policy, count: int
) -> None:
    """The fault comes in the handler's first unit of work, before the import is COMMITTING.
    Until the last attempt the import is APPROVED behind a queued job; the last ends the job
    FAILED and the hook takes the import in the state the job found it in: APPROVED to COMMITTING
    to FAILED in the job's last transaction. Before, the import stayed APPROVED for good — its
    cancel answers 409 and so does a second submit — with the approver told that a job failed
    and the uploader told nothing."""
    attempts(JobKind.IMPORT_COMMIT, count)
    import_id, commit_job, approver = _approved(world)
    calls = fault(commit, "start_commit", _could_not_serialize, count)

    for attempt in range(1, count):
        _work(world, commit_job, attempt=attempt)
        assert _shown(world, import_id)["status"] == "APPROVED"
        assert _job(world, commit_job)["state"] == "QUEUED"
        assert _items(world, import_id) == []

    _work(world, commit_job, attempt=count)
    _ended_failed(world, import_id, commit_job, approver)
    assert calls == list(range(1, count + 2)), "the hook made the one call after the armed ones"


# --- the dry run ----------------------------------------------------------------------------------


def test_a_wait_in_the_dry_run_is_retried_and_the_diff_is_ready(
    world: ImportWorld, fault: Arm, attempts: Policy
) -> None:
    """The third job of the pipeline has no catch-all: every error leaves ``import_diff``, so a
    wait was never stored as a result about the file, and this test passes before rev 1.185 as
    after — it holds the rule for the dry run beside the two handlers the revision changes. The
    first attempt meets a serialization failure inside the diff's unit of work: the import stays
    DIFFING with nothing stored, behind a re-queued job; the second attempt makes the diff."""
    attempts(JobKind.IMPORT_DIFF, 2)
    import_id, diff_job = _validated(world)
    calls = fault(diff, "compute_diff", _could_not_serialize, 1)

    first_task = _work(world, diff_job, attempt=1)
    assert calls == [1]
    waiting = _shown(world, import_id)
    assert (waiting["status"], waiting["diff_summary"]) == ("DIFFING", None), waiting
    assert _items(world, import_id) == []
    queued = _job(world, diff_job)
    assert (queued["state"], queued["problem"]) == ("QUEUED", None), queued

    second_task = _work(world, diff_job, attempt=2)
    assert second_task != first_task, "the retry is a new task"
    assert calls == [1, 2]
    done = _shown(world, import_id)
    assert done["status"] == "DIFF_READY" and done["diff_summary"] is not None, done
    assert _items(world, import_id) == []
    assert _job(world, diff_job)["state"] == "SUCCEEDED"
    assert _told(world, diff_job) == []


def _ended_by_the_dry_run(world: ImportWorld, import_id: str, diff_job: UUID) -> None:
    """What a failed dry run leaves beside ``_ended_invalid``: the rows the validation stored,
    no diff, and the uploader told in the words of PRD NTF-05 — by the hook, because the system
    starts the dry run and its job's own notification reaches nobody."""
    ended = _ended_invalid(world, import_id, diff_job)
    assert (ended["counts"]["rows"], ended["counts"]["valid"]) == (3, 3), ended
    assert ended["diff_summary"] is None and _rows(world, import_id) == 3
    answered = get(world.app, f"{IMPORTS_PATH}/{import_id}/diff", world.actor)
    assert answered.status_code == 409, answered.text
    assert _told(world, diff_job) == [("JOB_FAILED", _uploader(world))]
    assert _words(world, diff_job) == [DRY_RUN_FAILED]
    # INVALID is an end: nothing is left to cancel.
    refused = post(world.app, f"{IMPORTS_PATH}/{import_id}/cancel", world.actor, {})
    assert refused.status_code == 409, refused.text


@pytest.mark.parametrize("count", [1, 2], ids=["one-attempt", "two-attempts"])
def test_a_dry_run_that_waits_at_its_last_attempt_ends_the_upload_invalid(
    world: ImportWorld, fault: Arm, attempts: Policy, count: int
) -> None:
    """Every attempt meets the fault inside the diff's unit of work. Until the last the upload
    is DIFFING behind a queued job; the last ends the job FAILED and the kind's failure hook
    makes the upload INVALID with ``IMPORT_PROCESSING_FAILED`` under the job's reference — the
    pair DIFFING to INVALID of revision 0122. Before, the upload stayed DIFFING for good and
    nobody was told."""
    attempts(JobKind.IMPORT_DIFF, count)
    import_id, diff_job = _validated(world)
    calls = fault(diff, "compute_diff", _could_not_serialize, count)

    for attempt in range(1, count):
        _work(world, diff_job, attempt=attempt)
        assert _shown(world, import_id)["status"] == "DIFFING"
        assert _job(world, diff_job)["state"] == "QUEUED"
        assert _items(world, import_id) == []

    _work(world, diff_job, attempt=count)
    assert calls == list(range(1, count + 1))
    _ended_by_the_dry_run(world, import_id, diff_job)


@pytest.mark.parametrize("count", [1, 2], ids=["one-attempt", "two-attempts"])
def test_a_dry_run_that_fails_before_it_began_ends_the_upload_invalid(
    world: ImportWorld, fault: Arm, attempts: Policy, count: int
) -> None:
    """The fault comes in the handler's first unit of work, before the upload is DIFFING. Until
    the last attempt the upload is VALIDATED behind a queued job; the last ends the job FAILED
    and the hook takes the upload in the state the job found it in: VALIDATED to DIFFING to
    INVALID in the job's last transaction. Before, the upload stayed VALIDATED and nobody was
    told."""
    attempts(JobKind.IMPORT_DIFF, count)
    import_id, diff_job = _validated(world)
    calls = fault(diff, "start_diff", _could_not_serialize, count)

    for attempt in range(1, count):
        _work(world, diff_job, attempt=attempt)
        assert _shown(world, import_id)["status"] == "VALIDATED"
        assert _job(world, diff_job)["state"] == "QUEUED"
        assert _items(world, import_id) == []

    _work(world, diff_job, attempt=count)
    _ended_by_the_dry_run(world, import_id, diff_job)
    assert calls == list(range(1, count + 2)), "the hook made the one call after the armed ones"


# --- a worker that is at work: the hook leaves its upload alone -----------------------------------


class _Abandoned(Exception):
    """Ends the stage's unit of work without a commit."""


def _stored(world: ImportWorld, import_id: str) -> str:
    """The upload's committed status, read without a lock."""
    return str(
        world.scalar(select(import_upload.c.status).where(import_upload.c.id == UUID(import_id)))
    )


def _row_is_held(world: ImportWorld, import_id: str) -> bool:
    """Whether another transaction holds the upload's row: a locking read that will not wait is
    refused with ``lock_not_available`` (SQLSTATE 55P03) — where a plain locking read would
    wait."""
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    try:
        with tenant_session(context) as session:
            session.execute(
                select(import_upload.c.id)
                .where(import_upload.c.id == UUID(import_id))
                .with_for_update(nowait=True)
            )
    except exc.OperationalError as refused:
        assert getattr(refused.orig, "sqlstate", None) == "55P03", refused
        return True
    return False


@pytest.mark.parametrize(
    ("kind", "start", "stage", "seam", "own"),
    [
        (
            JobKind.IMPORT_VALIDATE,
            "start_validation",
            "validate_upload",
            (templates, "find_template"),
            "VALIDATING",
        ),
        (JobKind.IMPORT_DIFF, "start_diff", "compute_diff", (diff, "emitter_of"), "DIFFING"),
    ],
    ids=["validation", "dry-run"],
)
def test_a_hook_leaves_an_upload_whose_row_the_handlers_own_stage_holds(
    world: ImportWorld,
    monkeypatch: pytest.MonkeyPatch,
    kind: JobKind,
    start: str,
    stage: str,
    seam: tuple[ModuleType, str],
    own: str,
) -> None:
    """A hook acts on the word of whoever ended the job, and the sweeper can end a job whose
    worker is alive and at work (lane OPS's measurement, item JOB-STALL-COMMIT-RACE-1). So a hook
    must leave an upload whose work is in flight. The handler's stage takes the upload's row at
    the start of its transaction, and the hook's one read passes over a held row
    (``job_hooks.held_status``).

    Here the stage function itself is at work in its own unit of work, and the hook is called
    from inside it — at the first thing the stage does after taking the row. The row is held: a
    locking read that will not wait is refused, where a plain one would wait. The hook returns
    without waiting and without failing, and says nothing: no status, no item, no notification.
    The row is as the handler left it, still held, when the hook returns.

    The stage's transaction is abandoned here. What the upload reads after the handler's commit,
    under a job that was ended meanwhile, is the kernel's (register index 242), not the
    hook's."""
    module = validate if kind is JobKind.IMPORT_VALIDATE else diff
    hook = registry.HANDLERS[kind].on_failure
    assert hook is not None
    import_id, job_id = _uploaded(world) if kind is JobKind.IMPORT_VALIDATE else _validated(world)
    upload_id = UUID(import_id)
    principal = system_principal(world.tenant_id)
    reference = f"job-{job_id}"
    problem = registry.failure_problem(RuntimeError("the job was ended"), job_id)
    with system_unit_of_work(world.runtime, principal, request_id=reference) as first:
        assert getattr(module, start)(first, upload_id) is True
        first.commit()
    assert _stored(world, import_id) == own and not _row_is_held(world, import_id)

    seen: dict[str, Any] = {}
    real = getattr(*seam)

    def at_work(*args: Any, **kwargs: Any) -> Any:
        """The stage has taken the row and written nothing yet."""
        seen["held"] = _row_is_held(world, import_id)
        with system_unit_of_work(world.runtime, principal, request_id=reference) as other:
            seen["returned"] = hook(other, {"import_upload_id": import_id}, problem)
            other.commit()
        seen["status"] = _stored(world, import_id)
        seen["items"] = _items(world, import_id)
        seen["told"] = _told(world, job_id)
        seen["still held"] = _row_is_held(world, import_id)
        return real(*args, **kwargs)

    monkeypatch.setattr(*seam, at_work)
    with (
        pytest.raises(_Abandoned),
        system_unit_of_work(world.runtime, principal, request_id=reference) as work,
    ):
        assert getattr(module, stage)(work, upload_id) is not None
        raise _Abandoned
    assert seen == {
        "held": True,
        "returned": None,
        "status": own,
        "items": [],
        "told": [],
        "still held": True,
    }


def test_failed_commit_waits_for_a_concurrent_upload_reader(
    world: ImportWorld, fault: Arm, attempts: Policy, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused command's row lock must not strand an approved import after job failure."""
    attempts(JobKind.IMPORT_COMMIT, 1)
    import_id, job_id, _ = _approved(world)
    fault(commit, "start_commit", _defect, 1)
    reached = Event()
    original = commit.job_hooks.held_status

    def observed(*args: Any, **kwargs: Any) -> Any:
        reached.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(commit.job_hooks, "held_status", observed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with tenant_session(DbContext(world.tenant_id, user_id=None, entity_scope="*")) as holder:
            holder.execute(
                select(import_upload.c.id)
                .where(import_upload.c.id == UUID(import_id))
                .with_for_update()
            ).one()
            pending = pool.submit(_work, world, job_id, attempt=1)
            assert reached.wait(timeout=10), "failure hook never reached the held upload"
            # Keep the competing lock long enough to reproduce the old SKIP LOCKED loss.
            assert not Event().wait(0.15)
        pending.result(timeout=15)
    assert _job(world, job_id)["state"] == "FAILED"
    assert _stored(world, import_id) == "FAILED"
    assert _loaded(world) == []
    assert [item["code"] for item in _items(world, import_id)] == [PROCESSING_FAILED]


def test_cancelling_a_queued_commit_releases_its_import(world: ImportWorld) -> None:
    """Cancellation before dispatch must end the upload and release duplicate-file protection."""
    import_id, job_id, _, priya = _approved_by(world)
    response = post(world.app, f"/api/v1/jobs/{job_id}/cancel", priya, {})
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "CANCELLED"
    assert _stored(world, import_id) == "FAILED"
    assert _loaded(world) == []
    assert [item["code"] for item in _items(world, import_id)] == [PROCESSING_FAILED]
    # A stale queued dispatch cannot commit after cancellation, and the exact bytes can be retried.
    _work(world, job_id, attempt=1)
    assert _loaded(world) == []
    replacement_id, _ = _uploaded(world)
    assert replacement_id != import_id


def test_queued_commit_cancellation_rolls_back_when_cleanup_fails(
    world: ImportWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    import_id, job_id, _, priya = _approved_by(world)
    spec = registry.HANDLERS[JobKind.IMPORT_COMMIT]
    assert spec.on_cancel is not None

    def refuse_after_cleanup(*args: Any, **kwargs: Any) -> None:
        assert spec.on_cancel is not None
        spec.on_cancel(*args, **kwargs)
        raise RuntimeError("cleanup could not finish")

    monkeypatch.setitem(
        registry.HANDLERS,
        JobKind.IMPORT_COMMIT,
        replace(spec, on_cancel=refuse_after_cleanup),
    )
    response = post(world.app, f"/api/v1/jobs/{job_id}/cancel", priya, {})
    assert response.status_code == 500, response.text
    assert _job(world, job_id)["state"] == "QUEUED"
    assert _stored(world, import_id) == "APPROVED"
    assert _items(world, import_id) == []
    # Rollback leaves the original queued job usable, not a cancelled job with a held import.
    monkeypatch.setitem(registry.HANDLERS, JobKind.IMPORT_COMMIT, spec)
    response = post(world.app, f"/api/v1/jobs/{job_id}/cancel", priya, {})
    assert response.status_code == 200, response.text
    assert _stored(world, import_id) == "FAILED"


def test_commit_failure_settlement_can_retry_after_cleanup_timeout(
    world: ImportWorld, fault: Arm, attempts: Policy, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts(JobKind.IMPORT_COMMIT, 1)
    import_id, job_id, _ = _approved(world)
    fault(commit, "start_commit", _defect, 1)
    original = commit.job_hooks.held_status

    def timeout(session: Any, *args: Any, **kwargs: Any) -> Any:
        session.execute(text("SET LOCAL lock_timeout = '50ms'"))
        return original(session, *args, **kwargs)

    monkeypatch.setattr(commit.job_hooks, "held_status", timeout)
    with tenant_session(DbContext(world.tenant_id, user_id=None, entity_scope="*")) as holder:
        holder.execute(
            select(import_upload.c.id)
            .where(import_upload.c.id == UUID(import_id))
            .with_for_update()
        ).one()
        with pytest.raises(exc.OperationalError) as refused:
            _work(world, job_id, attempt=1)
        assert getattr(refused.value.orig, "sqlstate", None) == "55P03"
    assert _job(world, job_id)["state"] == "RUNNING"
    assert _stored(world, import_id) == "APPROVED"
    assert _items(world, import_id) == []
    # This is the settlement entry point also used by the stalled-job sweeper.
    registry.fail_attempt(
        job_id,
        world.tenant_id,
        attempt=1,
        error=RuntimeError("worker stopped"),
        runtime=world.runtime,
    )
    assert _job(world, job_id)["state"] == "FAILED"
    assert _stored(world, import_id) == "FAILED"
    assert [item["code"] for item in _items(world, import_id)] == [PROCESSING_FAILED]
