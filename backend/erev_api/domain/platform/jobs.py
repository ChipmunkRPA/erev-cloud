"""Jobs: reads and cancellation (04 API-R-11, API-S-Job, T-PLT-27; 05 JOB-05; REQ-PLT-029;
BUILD_SPEC PLF-22).

A job is visible to the user who started it and to holders of ``audit.read`` for all entities — a
job carries no entity, so a holder of named entities sees the jobs he started and no other
(supervisor ruling R-28; item SCOPE-WORKSPACE-LISTS-1); anyone else gets 404 ``not-found``. Only
the initiator cancels a job. A QUEUED job is CANCELLED at once; a RUNNING job
records ``cancel_requested_at`` and ends CANCELLED after its current chunk (DG-KRN-JOB-04); a
finished job returns 409 ``invalid-transition``.

Jobs are AUD-OPS with a listed exception (04 T-PLT-27 rev 1.106; supervisor ruling R-50 (a)): the
commands that start, cancel and finish a job are audited. A cancellation that changes the job
writes ``job.cancel`` as the caller, whatever the kind: for a QUEUED job it is the event of the
terminal state (``after.state`` is ``CANCELLED``; the registry writes no ``job.finish`` for it),
for a RUNNING job the event of the request (the registry writes ``job.finish`` when the handler
stops). A repeated request on a job already asked to stop changes nothing and writes nothing.

A job's result is answered as the job stored it, with one exception (04 API-S-Job rev 1.314; item
PREVIEW-JOB-RESULT-SCOPE-1): ``summary``, the API-S-ImpactSummary of a dry run, holds figures of
the whole combination group, so it is answered to a reader of the job who holds the read
permission of the dry run's subject for every entity the subject is bound to
(``file_access.preview_summary_readable``) — and withheld from every other reader, the initiator
too (``job_outs``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, exists, false, or_, select, update
from sqlalchemy.orm import Session

from erev_api.approvals.engine import CONTRACT_SUBJECT
from erev_api.auth import entity_scope
from erev_api.db.session import tenant_session
from erev_api.db.tables import job
from erev_api.db.transitions import apply
from erev_api.domain.platform import approval_queries, file_access
from erev_api.enums import ApprovalSubjectType, JobKind, JobState
from erev_api.jobs.registry import CANCEL_ACTION, JOB_SUBJECT
from erev_api.problems import Problem
from erev_api.schemas.common import JobOut, job_out

if TYPE_CHECKING:
    from erev_api.auth.principal import Principal, RequestContext
    from erev_api.uow import UnitOfWork

AUDIT_READ: Final = "audit.read"
ONLY_INITIATOR: Final = "Only the person who started this job can cancel it."
ALREADY_FINISHED: Final = "This job has already finished."
JOB_COLUMNS: Final = (
    job.c.id,
    job.c.kind,
    job.c.state,
    job.c.progress_done,
    job.c.progress_total,
    job.c.result,
    job.c.problem,
    job.c.created_by,
    job.c.created_by_kind,
    job.c.created_at,
    job.c.started_at,
    job.c.finished_at,
    job.c.cancel_requested_at,
    # read for API-S-Job `mode` alone (04 API-R-04 rev 1.67: `restore` when a TENANT_SNAPSHOT job
    # carries `params.load`; API-S-Job rev 1.281: `params.mode` of a JOURNAL_EXPORT job);
    # `schemas.common.job_out` shows no other member of it — `job_outs` reads it besides for the
    # subject of a dry run (`SUMMARY_SUBJECTS`)
    job.c.params,
)
# 04 API-S-Job rev 1.314 (item PREVIEW-JOB-RESULT-SCOPE-1): the member of a result that holds the
# summary of a dry run, and the member that says it is withheld from this reader.
SUMMARY: Final = "summary"
SUMMARY_WITHHELD: Final = "summary_withheld"
# The dry runs, by the ``mode`` a ``CONTRACT_COMPUTE`` job stores in its params
# (``contracts.compute_job``; the four preview routes of 04 §16.10 "Who may ask for a preview"):
# the subject ``file_access.preview_summary_readable`` is asked about, and the member of the
# params that names it. The literals are the deferring commands' own; they are not imported,
# because those modules import this one (``tests/architecture/test_preview_scope.py`` holds the
# two to each other, both ways). Pending events are stored nowhere and are named by their
# contract — the kernel's word, ``file_access.PENDING_EVENTS``, which this module does not read
# while it is imported: ``file_access`` reaches it through ``approval_queries`` (DG-ARC-17).
SUMMARY_SUBJECTS: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        "PREVIEW": (CONTRACT_SUBJECT, "contract_id"),
        "ESTIMATE_PREVIEW": (ApprovalSubjectType.ESTIMATE_VERSION.value, "estimate_version_id"),
        "MODIFICATION_PREVIEW": (ApprovalSubjectType.MODIFICATION.value, "modification_id"),
        "ADJUSTMENT_PREVIEW": (
            ApprovalSubjectType.MANUAL_ADJUSTMENT.value,
            "manual_adjustment_id",
        ),
    }
)


def newest_of_subject() -> ColumnElement[bool]:
    """A predicate over ``job``: no later job works on the row's subject — the row is the NEWEST
    job of its resource (04 T-PLT-27 ``subject_type`` and ``subject_id``; ``ix_job__subject``).
    One rule for every count of failed jobs by subject, so that a resource whose later job
    succeeded shows none: the close runs and journal runs of a period (supervisor ruling
    R-103 (a), item CLO-BLK08-NEWEST-1) and the re-marking job of a period a lock opened
    (R-106 (a))."""
    later = job.alias("later_job")
    return ~exists().where(
        later.c.tenant_id == job.c.tenant_id,
        later.c.subject_type == job.c.subject_type,
        later.c.subject_id == job.c.subject_id,
        or_(
            later.c.created_at > job.c.created_at,
            and_(later.c.created_at == job.c.created_at, later.c.id > job.c.id),
        ),
    )


def _visible(statement: Select[Any], principal: Principal) -> Select[Any]:
    if entity_scope.holds_all(principal, AUDIT_READ):
        return statement
    if principal.id is None:
        return statement.where(false())
    return statement.where(job.c.created_by == principal.id)


def summary_subject(row: Mapping[str, Any]) -> tuple[str, UUID] | None:
    """The subject of the dry run whose summary the job's result holds — (subject type, id), as
    ``file_access.preview_summary_readable`` takes them — or None for a job that names no dry run
    of ``SUMMARY_SUBJECTS``. Pure."""
    kind = row["kind"]
    if str(getattr(kind, "value", kind)) != JobKind.CONTRACT_COMPUTE.value:
        return None
    params: Mapping[str, Any] = row.get("params") or {}
    found = SUMMARY_SUBJECTS.get(str(params.get("mode")))
    if found is None:
        return None
    subject_type, member = found
    try:
        return subject_type, UUID(str(params[member]))
    except (KeyError, ValueError):
        return None


def _answered(
    session: Session,
    reader: Principal | None,
    row: Mapping[str, Any],
    asked: dict[tuple[str, UUID], bool],
) -> Mapping[str, Any]:
    """The row as ``reader`` is answered it (04 API-S-Job rev 1.314): whole, unless its result
    holds the summary of a dry run the reader is not shown — then with ``summary`` null and
    ``summary_withheld`` true, and every other member of the result as stored. Withheld also
    where nobody is named as the reader, and where the job names no dry run the rule knows: a
    summary is answered by this rule or not at all. ``asked`` keeps the answers of one page."""
    result = row["result"]
    if not isinstance(result, Mapping) or result.get(SUMMARY) is None:
        return row
    subject = summary_subject(row)
    if reader is not None and subject is not None:
        if subject not in asked:
            asked[subject] = file_access.preview_summary_readable(session, reader, *subject)
        if asked[subject]:
            return row
    return {**row, "result": {**result, SUMMARY: None, SUMMARY_WITHHELD: True}}


def job_outs(
    session: Session, rows: Sequence[Mapping[str, Any]], *, reader: Principal | None = None
) -> list[JobOut]:
    """API-S-Job of each row, with the initiators' display names read in ``session``.

    ``reader`` is who the answer is for: the summary of a dry run is answered to a reader who
    holds the read permission of its subject for every entity it is bound to, and withheld
    otherwise (``_answered``). A command that answers the job it just deferred names no reader
    — the job has no result yet."""
    names = approval_queries.display_names(session, (row["created_by"] for row in rows))
    asked: dict[tuple[str, UUID], bool] = {}
    return [
        job_out(
            _answered(session, reader, row, asked),
            created_by=approval_queries.actor(row["created_by"], row["created_by_kind"], names),
        )
        for row in rows
    ]


def list_jobs[T](ctx: RequestContext, *, page: Callable[[Session, Select[Any]], T]) -> T:
    """One page of the jobs the caller may see; ``page`` applies the list parameters and answers
    the rows with ``job_outs(..., reader=ctx.principal)``."""
    statement = _visible(select(*JOB_COLUMNS), ctx.principal)
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return page(session, statement)


def get_job(ctx: RequestContext, job_id: UUID) -> JobOut:
    """One job the caller may see, else 404 ``not-found``."""
    statement = _visible(select(*JOB_COLUMNS).where(job.c.id == job_id), ctx.principal)
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = session.execute(statement).mappings().one_or_none()
        if row is None:
            raise Problem("not-found")
        return job_outs(session, [dict(row)], reader=ctx.principal)[0]


def _read(session: Session, job_id: UUID) -> Mapping[str, Any]:
    row = session.execute(select(*JOB_COLUMNS).where(job.c.id == job_id)).mappings().one()
    return MappingProxyType(dict(row))


def job_out_of(session: Session, job_id: UUID) -> JobOut:
    """API-S-Job of a job in ``session``'s transaction, such as one a command just deferred."""
    return job_outs(session, [_read(session, job_id)])[0]


def cancel_job(uow: UnitOfWork, job_id: UUID) -> JobOut:
    """``POST /jobs/{id}/cancel`` (05 JOB-05)."""
    principal = uow.principal
    current = (
        uow.session.execute(
            _visible(select(*JOB_COLUMNS).where(job.c.id == job_id), principal).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if current is None:
        raise Problem("not-found")
    if principal.id is None or current["created_by"] != principal.id:
        raise Problem("forbidden", ONLY_INITIATOR)
    stamp = {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }
    state = JobState(current["state"])
    if state == JobState.QUEUED:
        apply(
            uow.session,
            "job",
            job_id,
            to_status=JobState.CANCELLED.value,
            set_values={"cancel_requested_at": uow.now, "finished_at": uow.now, **stamp},
            expected_status=JobState.QUEUED.value,
        )
        after = JobState.CANCELLED
    elif state == JobState.RUNNING:
        if current["cancel_requested_at"] is not None:
            # Already asked to stop: nothing changes, so nothing is audited.
            return job_out_of(uow.session, job_id)
        uow.session.execute(
            update(job)
            .where(job.c.tenant_id == principal.tenant_id, job.c.id == job_id)
            .values(cancel_requested_at=uow.now, **stamp)
        )
        after = JobState.RUNNING
    else:
        raise Problem("invalid-transition", ALREADY_FINISHED)
    uow.audit(
        action=CANCEL_ACTION,
        object_type=JOB_SUBJECT,
        object_id=job_id,
        before={"state": state.value, "cancel_requested_at": None},
        after={
            "kind": str(current["kind"]),
            "state": after.value,
            "cancel_requested_at": uow.now,
        },
    )
    return job_out_of(uow.session, job_id)
