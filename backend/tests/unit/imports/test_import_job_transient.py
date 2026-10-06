"""Supervisor rulings R-108 (2) and R-105 (2): the catch-alls of the import jobs take the
transient predicate (``db.errors.is_transient``). A transient database error met by the commit or
the validation of an import leaves the handler — the attempt fails, nothing is stored for the
upload, the job is settled by its retry policy — and every other error is stored as before. The
job that ends FAILED ends the upload through the kind's failure hook (05 §5.6 rev 1.165 and
1.185), which ``tests/domain/imports/test_commit_job_failed.py`` and
``tests/domain/imports/test_import_job_transient_db.py`` witness with a database. No database
here: the units of work and the stage functions are stand-ins.

Before: both handlers stored a failure for a serialization failure and answered
SUCCEEDED_WITH_EXCEPTIONS — a wait recorded as a finding about the file.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.db import errors as db_errors
from erev_api.db import transitions
from erev_api.domain.imports import commit, diff, validate
from erev_api.enums import ImportStatus, JobKind
from erev_api.jobs import registry
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError


class _Driver(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__("driver error")
        self.sqlstate = sqlstate


def _database_error(sqlstate: str) -> OperationalError:
    return OperationalError("UPDATE import_upload ...", {}, _Driver(sqlstate))


class _Context:
    """A job context whose units of work are stand-ins."""

    def __init__(self) -> None:
        self.job_id = uuid4()
        self.progress = None

    @contextmanager
    def unit_of_work(self) -> Iterator[Any]:
        yield SimpleNamespace(
            session=None, commit=lambda: None, ctx=SimpleNamespace(request_id="request-1")
        )


SERIALIZATION_FAILURE = "40001"  # class 40: transient
UNIQUE_VIOLATION = "23505"  # class 23: deterministic


def test_the_two_errors_are_what_the_predicate_says() -> None:
    assert db_errors.is_transient(_database_error(SERIALIZATION_FAILURE))
    assert not db_errors.is_transient(_database_error(UNIQUE_VIOLATION))


@pytest.mark.parametrize(
    ("error", "stored", "left"),
    [
        (_database_error(SERIALIZATION_FAILURE), False, True),
        (_database_error(UNIQUE_VIOLATION), True, False),
        (ValueError("a defect of the handler"), True, False),
    ],
    ids=["transient", "deterministic", "crash"],
)
def test_the_commit_stores_a_failure_for_everything_but_a_transient_error(
    monkeypatch: pytest.MonkeyPatch, error: Exception, stored: bool, left: bool
) -> None:
    calls: list[dict[str, Any]] = []

    def refuse(*_: Any, **__: Any) -> None:
        raise error

    monkeypatch.setattr(commit, "start_commit", lambda uow, import_id: True)
    monkeypatch.setattr(commit, "commit_upload", refuse)
    monkeypatch.setattr(commit, "fail_commit", lambda *args, **kwargs: calls.append(kwargs))
    ctx, import_id = _Context(), uuid4()
    if left:
        with pytest.raises(OperationalError):
            commit.import_commit(ctx, {"import_upload_id": str(import_id)})  # type: ignore[arg-type]
    else:
        outcome = commit.import_commit(ctx, {"import_upload_id": str(import_id)})  # type: ignore[arg-type]
        assert outcome.state == "SUCCEEDED_WITH_EXCEPTIONS"
    assert [call["code"] for call in calls] == (["IMPORT_PROCESSING_FAILED"] if stored else [])


@pytest.mark.parametrize(
    ("error", "stored", "left"),
    [
        (_database_error(SERIALIZATION_FAILURE), False, True),
        (_database_error(UNIQUE_VIOLATION), True, False),
        (ValueError("a defect of the handler"), True, False),
    ],
    ids=["transient", "deterministic", "crash"],
)
def test_the_validation_stores_a_failure_for_everything_but_a_transient_error(
    monkeypatch: pytest.MonkeyPatch, error: Exception, stored: bool, left: bool
) -> None:
    calls: list[UUID] = []

    def refuse(*_: Any, **__: Any) -> None:
        raise error

    def failed(uow: Any, upload_id: UUID, **_: Any) -> None:
        calls.append(upload_id)

    monkeypatch.setattr(validate, "start_validation", lambda uow, upload_id: True)
    monkeypatch.setattr(validate, "validate_upload", refuse)
    monkeypatch.setattr(validate, "fail_validation", failed)
    ctx, upload_id = _Context(), uuid4()
    if left:
        with pytest.raises(OperationalError):
            validate.import_validate(ctx, {"import_upload_id": str(upload_id)})  # type: ignore[arg-type]
    else:
        validate.import_validate(ctx, {"import_upload_id": str(upload_id)})  # type: ignore[arg-type]
    assert calls == ([upload_id] if stored else [])


def test_each_kind_ends_its_upload_through_its_failure_hook() -> None:
    """What a handler lets through is settled by the job, so each of the three kinds registers
    the hook that ends its upload when the job ends FAILED — after however many attempts the
    retry table gives the kind (05 §5.6; item JOB-RETRY-TABLE-1)."""
    assert registry.HANDLERS[JobKind.IMPORT_COMMIT].on_failure is commit.commit_job_failed
    assert registry.HANDLERS[JobKind.IMPORT_VALIDATE].on_failure is validate.validation_job_failed
    assert registry.HANDLERS[JobKind.IMPORT_DIFF].on_failure is diff.diff_job_failed
    # ... and, raising an item of its own there, registers no ``failed_item`` (the
    # kernel's rule, ``jobs.registry.task``; 04 §15.4 ``JOB_FAILED`` rev 1.270).
    for kind in (JobKind.IMPORT_VALIDATE, JobKind.IMPORT_DIFF, JobKind.IMPORT_COMMIT):
        assert registry.HANDLERS[kind].failed_item is None, kind


def test_the_states_a_hook_takes_lead_to_the_end_it_gives() -> None:
    """One rule (``job_hooks``): the state the job found the upload in, the job's own state, and
    the end — each step a DB-03 pair of ``import_upload``. ``DIFFING`` → ``INVALID`` is revision
    0122's (04 T-IMP-02 rev 1.270); nothing but that end, the diff and a cancel leaves
    ``DIFFING``."""
    pairs = transitions.TRANSITIONS["import_upload"].pairs
    for found, own, end in (
        ("UPLOADED", "VALIDATING", "INVALID"),
        ("VALIDATED", "DIFFING", "INVALID"),
        ("APPROVED", "COMMITTING", "FAILED"),
    ):
        assert {(found, own), (own, end)} <= pairs
    assert {to for start, to in pairs if start == "DIFFING"} == {
        "DIFF_READY",
        "INVALID",
        "CANCELLED",
    }


class _Recorder:
    """A session that records the one statement ``held_status`` sends and answers no row."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def execute(self, statement: Any) -> Any:
        compiled = statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
        self.sent.append(" ".join(str(compiled).split()))
        return SimpleNamespace(scalar_one_or_none=lambda: None)


def test_a_hook_looks_once_for_its_two_states_and_never_waits() -> None:
    """``job_hooks.held_status``: one locking read of the upload in the two states it is given,
    ``FOR UPDATE SKIP LOCKED`` — a row another transaction holds is passed over, not waited for —
    and None when the read finds no row."""
    from erev_api.domain.imports import job_hooks

    session, upload_id = _Recorder(), uuid4()
    found = job_hooks.held_status(
        session,  # type: ignore[arg-type]
        upload_id,
        (ImportStatus.VALIDATED, ImportStatus.DIFFING),
    )
    assert found is None
    (sent,) = session.sent
    assert sent.endswith("FOR UPDATE SKIP LOCKED")
    assert "import_upload.status IN ('VALIDATED', 'DIFFING')" in sent
    assert f"import_upload.id = '{upload_id}'" in sent
