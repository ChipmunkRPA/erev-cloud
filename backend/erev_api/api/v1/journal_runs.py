"""API-R-38 Journal runs: calculation, approval states and reads.

04 §15.3 API-R-38, §16.7 API-S-JournalRunCreate, API-S-JournalRun, API-S-JournalLine,
API-S-JournalRunSummary, "Journal commands"; T-SL-06 to T-SL-10; 05 RCP-27; PRD SM-08;
BUILD_SPEC CLO-8, CLO-11. Reads need ``contract.read``; ``POST /journal-runs`` needs
``journal.run`` and answers 202 API-S-Job with the job's ``Location`` and the run id header.
``submit`` and ``cancel`` need ``journal.run`` (CLO-11). ``export`` needs ``journal.export`` and
answers 202 API-S-Job ``JOURNAL_EXPORT``; ``GET /journal-batches/{id}/download`` returns the batch's
CSV export with its manifest to holders of ``journal.export`` or ``report.export`` (CLO-13; D-87
L6-3-Q-12). ``POST /journal-batches/{id}/acknowledge`` (201 API-S-PostingAck) and ``POST
/journal-batches/{id}/retry`` (202 API-S-Job) need ``journal.export`` for the batch's entity
(CLO-14; REQ-JE-016; CTL-021). ``cancel`` answers 202 API-S-Job for a run with a failed batch, and
``POST /journal-batches/{id}/hand-over`` (202 API-S-Job; ``journal.export``) hands a failed batch
over for manual posting (04 rev 1.159; item JRN-FAILED-CANCEL-1).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Select
from sqlalchemy.orm import Session

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    command,
    kernel_deps,
    problem_responses,
    row_etag,
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListResult,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import (
    journal_batch,
    journal_entry,
    journal_line,
    journal_run,
    legal_entity,
    period,
    subledger_line,
)
from erev_api.domain.journals import commands, export, failed_exits, queries, subledger
from erev_api.enums import AccountRole, BookCode, JournalRunMode, JournalState
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.journals import (
    JournalBatchOut,
    JournalEntryOut,
    JournalLineOut,
    JournalRunCancelIn,
    JournalRunCreateIn,
    JournalRunExportIn,
    JournalRunOut,
    JournalRunSubmitIn,
    JournalRunSummaryOut,
    PostingAckCreateIn,
    PostingAckOut,
)
from erev_api.schemas.subledger import SubledgerLineOut
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-38 Journal runs"
READ_PERMISSION: Final = "contract.read"
JOB_PATH: Final = f"{API_PREFIX}/jobs/{{job_id}}"
RUN_ID_HEADER: Final = "X-Erev-Journal-Run-Id"
DOWNLOAD_CSP: Final = "sandbox"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "mfa-required",
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
    "not-found",
    "release-mismatch",
)

RUN_LIST: Final = ListSpec(
    resource="journal-runs",
    # SCREENS_B §3.1 binds SF-06 to sort=-period; runs order by their period's start date.
    sort_keys={
        "id": journal_run.c.id,
        "created_at": journal_run.c.created_at,
        "period": period.c.start_date,
    },
    default_sort="-id",
    filters={
        "state": FilterSpec(
            name="state",
            column=journal_run.c.state,
            kind="in",
            choices=frozenset(member.value for member in JournalState),
        ),
        "mode": FilterSpec(
            name="mode",
            column=journal_run.c.mode,
            kind="exact",
            choices=frozenset(member.value for member in JournalRunMode),
        ),
    },
    custom_filters=frozenset({"entity", "book", "period"}),
)
BATCH_LIST: Final = ListSpec(
    resource="journal-run-batches",
    sort_keys={"id": journal_batch.c.id, "batch_no": journal_batch.c.batch_no},
    default_sort="batch_no",
    filters={},
)
ENTRY_LIST: Final = ListSpec(
    resource="journal-run-entries",
    sort_keys={"id": journal_entry.c.id, "je_seq": journal_entry.c.je_seq},
    default_sort="je_seq",
    filters={},
)
LINE_LIST: Final = ListSpec(
    resource="journal-run-lines",
    sort_keys={"id": journal_line.c.id, "line_no": journal_line.c.line_no},
    default_sort="id",
    filters={
        "account_code": FilterSpec(
            name="account_code", column=journal_line.c.gl_account_code, kind="exact"
        ),
        "account_role": FilterSpec(
            name="account_role",
            column=journal_line.c.account_role,
            kind="exact",
            choices=frozenset(member.value for member in AccountRole),
        ),
    },
    custom_filters=frozenset({"contract", "batch_id"}),
)
DRILL_LIST: Final = ListSpec(
    resource="journal-line-drill",
    sort_keys={"id": subledger_line.c.id},
    default_sort="id",
    filters={},
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)
ReadContext = Annotated[RequestContext, Depends(require(READ_PERMISSION))]
Params = Annotated[ListParams, Depends(list_params)]


def _total(response: Response, result: ListResult) -> None:
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count


@router.get(
    "/journal-runs",
    operation_id="journal_runs_list",
    response_model=ListOut[JournalRunOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def journal_runs_list(
    response: Response,
    ctx: ReadContext,
    params: Params,
    entity: Annotated[list[str] | None, Query(description="Entity code; repeatable")] = None,
    book: Annotated[BookCode | None, Query()] = None,
    period_key: Annotated[str | None, Query(alias="period", description="Period key")] = None,
    state: Annotated[list[JournalState] | None, Query()] = None,
    mode: Annotated[JournalRunMode | None, Query()] = None,
) -> ListOut[JournalRunOut]:
    """Journal runs in the caller's entity scope; sort ``id`` (default ``-id``), ``created_at``
    or ``period`` (the period start date)."""
    del state, mode  # applied by ``paginate`` through RUN_LIST
    statement = queries.runs_statement()
    if entity:
        statement = statement.where(legal_entity.c.code.in_(entity))
    if book is not None:
        statement = statement.where(journal_run.c.book_code == book.value)
    if period_key is not None:
        statement = statement.where(period.c.period_key == period_key)

    def page(session: Session) -> tuple[ListResult, list[JournalRunOut]]:
        result = paginate(session, statement, RUN_LIST, params)
        return result, queries.run_outs(session, [dict(row) for row in result.items])

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[JournalRunOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/journal-runs",
    operation_id="journal_runs_create",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def journal_runs_create(
    body: JournalRunCreateIn,
    cmd: Annotated[CommandContext, Depends(command(commands.RUN_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Calculate a journal run: 202 API-S-Job; the job inserts the run in ``draft`` with its
    batches, entries and lines. ``book`` LEGACY is refused (T-SL-06)."""
    started: dict[str, uuid.UUID] = {}

    def handle(uow: UnitOfWork) -> JobOut:
        run_id, job = commands.create_run(uow, body)
        started["run_id"] = run_id
        return job

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        extra_headers=lambda job: {
            "Location": JOB_PATH.format(job_id=job.id),
            RUN_ID_HEADER: str(started["run_id"]),
        },
    )


@router.get(
    "/journal-runs/{run_id}",
    operation_id="journal_runs_get",
    response_model=JournalRunOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def journal_runs_get(run_id: uuid.UUID, response: Response, ctx: ReadContext) -> JournalRunOut:
    """API-S-JournalRun with its ``ETag``."""
    out = queries.read(ctx, lambda session: queries.get_run(session, run_id))
    response.headers["ETag"] = row_etag(out.row_version)
    return out


@router.post(
    "/journal-runs/{run_id}/submit",
    operation_id="journal_runs_submit",
    response_model=JournalRunOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def journal_runs_submit(
    run_id: uuid.UUID,
    body: JournalRunSubmitIn,
    cmd: Annotated[CommandContext, Depends(command(commands.RUN_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Submit a ``draft`` run: 200 API-S-JournalRun with ``approval_request_id``. The request needs
    ``journal.approve`` (PRD §2.5); approval moves the run and its batches to ``approved`` (DB-16).
    """

    def handle(uow: UnitOfWork) -> JournalRunOut:
        return commands.submit_run(uow, run_id, body)

    return run_command(cmd, deps, handle, etag=lambda out: row_etag(out.row_version))


def _cancel_status(result: Any) -> int:
    return 202 if isinstance(result, JobOut) else 200


def _cancel_headers(result: Any) -> dict[str, str]:
    if isinstance(result, JobOut):
        return {"Location": JOB_PATH.format(job_id=result.id)}
    assert isinstance(result, JournalRunOut)
    return {"ETag": row_etag(result.row_version)}


@router.post(
    "/journal-runs/{run_id}/cancel",
    operation_id="journal_runs_cancel",
    response_model=JournalRunOut,
    responses={
        **problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
        202: {
            "model": JobOut,
            "description": "The job that asks the ledger and cancels a run with a failed batch",
        },
    },
)
def journal_runs_cancel(
    run_id: uuid.UUID,
    body: JournalRunCancelIn,
    cmd: Annotated[CommandContext, Depends(command(commands.RUN_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Cancel a ``draft`` or ``approved`` run with its batches: 200 API-S-JournalRun; ``reason``
    is required. A pending request is voided (``SUBJECT_VOIDED``). A run with a ``failed`` batch
    answers 202 API-S-Job ``JOURNAL_EXPORT`` with the job's ``Location``: the job asks the ledger
    for every failed batch and cancels the run only when the ledger holds none — read
    ``result.outcome`` (``CANCELLED`` or ``NOT_CANCELLED`` with ``result.refusal``). A run with a
    batch ``exported`` or ``acknowledged`` answers 409 ``invalid-transition`` (PRD ERR-74)."""

    def handle(uow: UnitOfWork) -> JournalRunOut | JobOut:
        return failed_exits.cancel_run(uow, run_id, body)

    return run_command(cmd, deps, handle, status_of=_cancel_status, extra_headers=_cancel_headers)


@router.post(
    "/journal-runs/{run_id}/export",
    operation_id="journal_runs_export",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition", "sandbox-restricted"),
)
def journal_runs_export(
    run_id: uuid.UUID,
    body: JournalRunExportIn,
    cmd: Annotated[CommandContext, Depends(command(export.EXPORT_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Export an approved run: 202 API-S-Job ``JOURNAL_EXPORT`` with the job's ``Location``. Each
    batch has one outbox message, so a repeated export writes no second message (BR-JE-02); a
    sandbox answers 403 ``sandbox-restricted`` (REQ-PLT-022)."""

    def handle(uow: UnitOfWork) -> JobOut:
        return export.export_run(uow, run_id, body)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        extra_headers=lambda job: {"Location": JOB_PATH.format(job_id=job.id)},
    )


@router.get(
    "/journal-runs/{run_id}/batches",
    operation_id="journal_runs_batches",
    response_model=ListOut[JournalBatchOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def journal_runs_batches(
    run_id: uuid.UUID, response: Response, ctx: ReadContext, params: Params
) -> ListOut[JournalBatchOut]:
    """The batches of a run; sort ``batch_no`` (default) or ``id``."""

    def page(session: Session) -> tuple[ListResult, list[JournalBatchOut]]:
        queries.run_row(session, run_id)
        statement = queries.batches_statement().where(journal_batch.c.journal_run_id == run_id)
        result = paginate(session, statement, BATCH_LIST, params)
        return result, queries.batch_outs(session, [dict(row) for row in result.items])

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[JournalBatchOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/journal-runs/{run_id}/entries",
    operation_id="journal_runs_entries",
    response_model=ListOut[JournalEntryOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def journal_runs_entries(
    run_id: uuid.UUID, response: Response, ctx: ReadContext, params: Params
) -> ListOut[JournalEntryOut]:
    """The journal entries of a run; sort ``je_seq`` (default) or ``id``."""

    def page(session: Session) -> tuple[ListResult, list[JournalEntryOut]]:
        queries.run_row(session, run_id)
        result = paginate(session, queries.entries_statement(run_id), ENTRY_LIST, params)
        return result, queries.entry_outs(result.items)

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[JournalEntryOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/journal-runs/{run_id}/lines",
    operation_id="journal_runs_lines",
    response_model=ListOut[JournalLineOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def journal_runs_lines(
    run_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    params: Params,
    account_code: Annotated[str | None, Query()] = None,
    account_role: Annotated[AccountRole | None, Query()] = None,
    contract: Annotated[uuid.UUID | None, Query()] = None,
    batch_id: Annotated[uuid.UUID | None, Query()] = None,
) -> ListOut[JournalLineOut]:
    """API-S-JournalLine rows of a run; filters ``account_code``, ``account_role``, ``contract`` and
    ``batch_id``; sort ``id`` (default) or ``line_no``."""
    del account_code, account_role  # applied by ``paginate`` through LINE_LIST

    def page(session: Session) -> tuple[ListResult, list[JournalLineOut]]:
        queries.run_row(session, run_id)
        statement = queries.lines_statement(run_id, contract_id=contract, batch_id=batch_id)
        result = paginate(session, statement, LINE_LIST, params)
        return result, queries.line_outs(
            result.items, queries.counterparties(session, result.items)
        )

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[JournalLineOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/journal-runs/{run_id}/summary",
    operation_id="journal_runs_summary",
    response_model=JournalRunSummaryOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def journal_runs_summary(run_id: uuid.UUID, ctx: ReadContext) -> JournalRunSummaryOut:
    """API-S-JournalRunSummary: account sums and balance checks computed from the run's lines."""
    return queries.read(ctx, lambda session: queries.summary(session, run_id))


@router.get(
    "/journal-lines/{line_id}/drill",
    operation_id="journal_lines_drill",
    response_model=ListOut[SubledgerLineOut],
    responses=problem_responses(
        *_READ_PROBLEMS, "validation-failed", "not-found", "invalid-transition"
    ),
)
def journal_lines_drill(
    line_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    params: Params,
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> ListOut[SubledgerLineOut]:
    """The subledger lines that a journal line summarises (RCP-27); at most 500 a page. They
    are read from the run's own record (04 T-SL-06 drill-back rev 1.288): a run whose record
    cannot be read answers 409 ``invalid-transition``, rule ``RUN_RECORD_UNREADABLE`` (PRD
    ERR-101)."""

    def page(session: Session) -> tuple[ListResult, list[SubledgerLineOut]]:
        # the file store and the key ring, as the gate hands them to the record's reader
        ids = queries.drill_ids(session, line_id, files=deps.files, keyring=deps.keyring)
        statement: Select[Any] = queries.drill_statement(ids)
        result = paginate(session, statement, DRILL_LIST, params)
        runs = subledger.journal_runs_of(
            session, result.items, files=deps.files, keyring=deps.keyring
        )
        return result, subledger.line_outs(result.items, runs)

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[SubledgerLineOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/journal-batches/{batch_id}",
    operation_id="journal_batches_get",
    response_model=JournalBatchOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def journal_batches_get(
    batch_id: uuid.UUID, response: Response, ctx: ReadContext
) -> JournalBatchOut:
    """A batch with its totals, detail file and acknowledgements."""
    out = queries.read(ctx, lambda session: queries.get_batch(session, batch_id))
    response.headers["ETag"] = row_etag(out.row_version)
    return out


@router.get(
    "/journal-batches/{batch_id}/download",
    operation_id="journal_batches_download",
    response_class=Response,
    responses={
        200: {
            "content": {export.ZIP_MEDIA_TYPE: {}},
            "description": "The batch's CSV export and its JSON manifest",
        },
        **problem_responses(*_READ_PROBLEMS, "not-found", "invalid-transition"),
    },
)
def journal_batches_download(
    batch_id: uuid.UUID,
    ctx: ReadContext,
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """A ZIP holding the REQ-JE-011 CSV and its JSON manifest, as an attachment; one
    ``journal_batch.download`` audit event. The route guard is ``contract.read``, because a route
    records one permission (DG-KRN-AUTH-03); the download itself needs ``journal.export`` or
    ``report.export`` for the batch's entity (D-87 L6-3-Q-12)."""
    download = export.download_batch(ctx, batch_id, files=deps.files, keyring=deps.keyring)
    return Response(
        content=download.content,
        media_type=export.ZIP_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{download.file_name}"',
            "Content-Security-Policy": DOWNLOAD_CSP,
        },
    )


@router.post(
    "/journal-batches/{batch_id}/acknowledge",
    operation_id="journal_batches_acknowledge",
    status_code=201,
    response_model=PostingAckOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def journal_batches_acknowledge(
    batch_id: uuid.UUID,
    body: PostingAckCreateIn,
    cmd: Annotated[CommandContext, Depends(command(export.EXPORT_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Record the ERP document reference of an ``exported`` batch ("Record ERP reference", PRD
    BR-JE-03): 201 API-S-PostingAck of kind ``MANUAL_CONFIRMATION``; the batch is ``acknowledged``
    and, once every batch is, so is the run (REQ-JE-016). ``gl_document_id`` is required; a batch
    in another state answers 409 ``invalid-transition``."""

    def handle(uow: UnitOfWork) -> PostingAckOut:
        return export.acknowledge_batch(uow, batch_id, body)

    return run_command(cmd, deps, handle, status_code=201)


@router.post(
    "/journal-batches/{batch_id}/retry",
    operation_id="journal_batches_retry",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition", "sandbox-restricted"),
)
def journal_batches_retry(
    batch_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(export.EXPORT_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Send a ``failed`` batch again: 202 API-S-Job ``JOURNAL_EXPORT`` with the job's ``Location``.
    The chunk keeps its external id, so a retry never posts twice (BR-JE-02); the batch is
    ``exported`` again once the adapter accepts it. A batch in another state answers 409
    ``invalid-transition``; a sandbox 403 ``sandbox-restricted``."""

    def handle(uow: UnitOfWork) -> JobOut:
        return export.retry_batch(uow, batch_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        extra_headers=lambda job: {"Location": JOB_PATH.format(job_id=job.id)},
    )


@router.post(
    "/journal-batches/{batch_id}/hand-over",
    operation_id="journal_batches_hand_over",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition", "sandbox-restricted"),
)
def journal_batches_hand_over(
    batch_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(export.EXPORT_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Hand a ``failed`` batch of an ERP adapter over for manual posting: 202 API-S-Job
    ``JOURNAL_EXPORT`` with the job's ``Location``. The job asks the ledger first; a batch the
    ledger holds is acknowledged instead. Otherwise the batch is ``exported`` with its file and
    waits for ``acknowledge`` — read ``result.outcome`` (``HANDED_OVER`` or ``NOT_HANDED_OVER``
    with ``result.refusal``). A batch in another state and a ``CSV`` batch answer 409
    ``invalid-transition``; a sandbox 403 ``sandbox-restricted``."""

    def handle(uow: UnitOfWork) -> JobOut:
        return failed_exits.hand_over_batch(uow, batch_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        extra_headers=lambda job: {"Location": JOB_PATH.format(job_id=job.id)},
    )
