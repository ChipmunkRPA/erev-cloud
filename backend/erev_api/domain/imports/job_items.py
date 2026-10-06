"""The exception item of a failed job (05 JOB-07 rev 1.165; 04 §15.4 ``JOB_FAILED`` rev 1.226,
T-IMP-05 ``dedupe_key``, §16.14; PRD IMP-137, BR-DAT-04; dev-guide DG-KRN-JOB-05 rev 1.212; 03
REQ-OPS-006; CTL-040; item JOB-FAILED-ITEM-1).

A job that ends FAILED after its last attempt and whose record names one legal entity leaves one
``INFO`` item in the exception queue of that entity. The jobs registry ends the job and decides
when; this module is what it writes through, because the registry is a kernel module and imports
no domain module (DG-ARC-01). A handler's module registers its kind with
``task(kind, …, failed_item=failed_item(source, reader))``: ``reader`` reads the job's subject and
answers the entity (``jobs.registry.FailedSubject``) or None, and ``failed_item`` binds the three
functions of this module to the source.

- ``raise_item`` runs in the transaction that ends the job, inside a savepoint of the unit of
  work: one open item per job kind and record (``dedupe_key`` ``<source>:JOB_FAILED:<job
  kind>:<record>``); a later failure counts it again (``raise_exception_item``). The record is
  the job's subject id, or the business key its reader states where the job's subject is not
  what a later job works on again.
- ``is_open`` and ``settle`` serve the job of that kind and record that runs to its end: the
  open item is RESOLVED by the system (``settle_gone``).

The item is ``INFO`` (04 E-43): the close gates count ``BLOCKING`` and ``WARNING`` items, for
every period when an item names none, and a failed job would then hold the locks of its entity
beside what it failed to produce, which the gates watch already (03 REQ-OPS-006). A person closes
an item whose record sees no later job by dismissing it with a comment (``exceptions.actions_of``).

The three import kinds register no reader here (05 §5.6 rev 1.185; 04 §15.4 rev 1.270; the
supervisor's ruling of 2026-10-02): their failure hooks end the upload with an item of its
own, ``IMPORT_PROCESSING_FAILED``, and a kind whose hook raises its own item registers none
(``jobs.registry.task``). Until then ``IMPORT_VALIDATE`` and ``IMPORT_DIFF`` read the upload
that names one entity: the item would have promised a later run to an import that is
``INVALID`` for good.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import Select, select, text
from sqlalchemy.orm import Session

from erev_api.db.tables import exception_item
from erev_api.domain.imports.exceptions import (
    JOB_FAILED,
    OPEN_PREDICATE,
    dedupe_key,
    raise_exception_item,
    settle_gone,
)
from erev_api.enums import ExceptionSeverity, ExceptionSource, JobKind
from erev_api.jobs.registry import (
    JOB_FAILED_TITLE,
    FailedItem,
    FailedJob,
    SubjectReader,
    problem_slug,
)

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "MESSAGE",
    "RESOLUTION",
    "failed_item",
    "item_key",
    "open_item",
]

# PRD IMP-137.
MESSAGE: Final = (
    "{label} failed at attempt {attempt}: {reason}. The job is {job_id}. This item closes when "
    "a later run for the same record completes; dismiss it with a comment if none will follow."
)
RESOLUTION: Final = "A later job for the same record completed: {job_id}."


def item_key(source: ExceptionSource, kind: JobKind, record: str) -> str:
    """T-IMP-05 ``dedupe_key`` of the item: the subject is the job kind and the record."""
    return dedupe_key(source, JOB_FAILED, f"{kind.value}:{record}")


def open_item(key: str) -> Select[Any]:
    """The ids of the OPEN and IN_PROGRESS items of ``key``. The status condition is the literal
    predicate of ``ux_exception_item__open``, so that the read is one probe of that index
    whatever the plan mode (``exceptions.OPEN_PREDICATE``)."""
    return select(exception_item.c.id).where(
        exception_item.c.dedupe_key == key, text(OPEN_PREDICATE)
    )


def _reason(failed: FailedJob) -> str:
    """The problem's detail, or its title: what PRD NTF-05 names as the reason. An unexpected
    error states no more than that it was one (``registry.failure_problem``)."""
    problem = failed.problem
    return str(problem.get("detail") or problem["title"]).rstrip(".")


def raise_item(source: ExceptionSource, uow: UnitOfWork, failed: FailedJob) -> None:
    """The item of ``failed``, or one more occurrence of the open item of its kind and record."""
    subject = failed.subject
    raise_exception_item(
        uow,
        source=source,
        code=JOB_FAILED,
        severity=ExceptionSeverity.INFO,
        title=JOB_FAILED_TITLE.format(label=failed.label),
        message=MESSAGE.format(
            label=failed.label,
            attempt=failed.attempt,
            reason=_reason(failed),
            job_id=failed.job_id,
        ),
        dedupe=item_key(source, failed.kind, failed.record),
        source_payload={
            "job_id": str(failed.job_id),
            "job_kind": failed.kind.value,
            "attempt": failed.attempt,
            "problem": problem_slug(failed.problem),
        },
        entity_id=subject.entity_id,
        period_id=subject.period_id,
        contract_id=subject.contract_id,
        combination_group_id=subject.combination_group_id,
        import_upload_id=subject.import_upload_id,
        sync_run_id=subject.sync_run_id,
    )


def is_open(source: ExceptionSource, session: Session, kind: JobKind, record: str) -> bool:
    """Whether the kind and record have an open item: the one read a succeeding job makes."""
    found = session.execute(open_item(item_key(source, kind, record)).limit(1)).first()
    return found is not None


def settle(
    source: ExceptionSource, uow: UnitOfWork, kind: JobKind, record: str, job_id: UUID
) -> None:
    """RESOLVED by the system: a job of the kind and record ran to its end (PRD BR-DAT-04)."""
    ids = [
        UUID(str(value))
        for value in uow.session.execute(open_item(item_key(source, kind, record))).scalars()
    ]
    settle_gone(uow, ids, resolution=RESOLUTION.format(job_id=job_id))


def failed_item(source: ExceptionSource, subject: SubjectReader) -> FailedItem:
    """What a handler's module passes to ``task(…, failed_item=…)``: the item's source, the
    reader of the kind's subject, and this module's functions bound to the source."""
    return FailedItem(
        source=source,
        subject=subject,
        raise_item=partial(raise_item, source),
        is_open=partial(is_open, source),
        settle=partial(settle, source),
    )
