"""API-R-41 Reports: definitions, report runs, run data, outputs and reruns.

04 §15.3 API-R-41, §16.9, T-RPT-01, T-RPT-02; SCREENS_B §0.5 RV-01 to RV-14; 03 REQ-RPT-002,
REQ-RPT-024, REQ-RPT-027, REQ-PLT-019; BUILD_SPEC RPS-2. The permission is the report's
(supervisor ruling R-63 (a)): reads and runs need the report's run permission — ``report.run``,
or ``audit.read`` for the user access listing, the SoD conflict report and the API client
inventory (``framework.RUN_PERMISSIONS``) — so the routes are guarded per subject
(``require_authenticated`` / ``command(per_subject=True)``): a principal that may run no report
is refused by ``_admitted`` as ``require("report.run")`` refused it, and the framework authorises
each report and run. A file output (``XLSX``, ``CSV``, ``PDF``, ``ZIP``) and
``GET /report-runs/{id}/output`` need ``report.export``, which also returns ``ipe_logic`` on
definitions. A report may declare further permissions (rev 1.99;
``framework.REQUIRED_PERMISSIONS``): without them every route of its runs answers 403
``forbidden`` and the list leaves them out. ``GET /report-runs/{id}/data``
pages the rows of a JSON run with API-C-09 cursors and takes no filter, sort or search; every page
carries the additive member ``columns`` of the stored dataset document (D-88 L7-1-Q-5).

[J] L5-2-Q-12: ``POST /report-runs`` and ``/rerun`` answer 202 API-S-Job with ``Location`` of the
job and header ``X-Erev-Report-Run-Id`` (the 04 §16.14 ``X-Erev-Evidence-Pack-Id`` precedent);
``GET /report-runs/{id}/output?part=manifest`` downloads the JSON manifest of a CSV run.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    command,
    kernel_deps,
    problem_responses,
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListResult,
    ListSpec,
    decode_cursor,
    encode_cursor,
    invalid,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import refresh_request_context, require, require_authenticated
from erev_api.auth.principal import RequestContext
from erev_api.clock import get_clock
from erev_api.db.tables import report_run
from erev_api.domain.ai import export_visibility
from erev_api.domain.contracts import queries
from erev_api.domain.reports import framework
from erev_api.enums import RunStatus
from erev_api.idempotency.store import Replay
from erev_api.problems import Problem
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.reports import (
    DisclosureSectionOut,
    ForecastHeaderOut,
    ReportColumnOut,
    ReportDefinitionOut,
    ReportRowOut,
    ReportRunCreateIn,
    ReportRunDataOut,
    ReportRunOut,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-41 Reports"
EXPORT: Final = framework.EXPORT_PERMISSION
JOB_PATH: Final = "/api/v1/jobs/{job_id}"
RUN_ID_HEADER: Final = "X-Erev-Report-Run-Id"
DOWNLOAD_CSP: Final = "sandbox"
DATA_SORT: Final = "row"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden", "mfa-required")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
    "release-mismatch",
)
RUN_LIST: Final = ListSpec(
    resource="report_runs",
    sort_keys={"id": report_run.c.id, "created_at": report_run.c.created_at},
    default_sort="-id",
    filters={
        "report_code": FilterSpec("report_code", report_run.c.report_code, "exact"),
        "status": FilterSpec(
            "status",
            report_run.c.status,
            "exact",
            choices=frozenset(status.value for status in RunStatus),
        ),
        "created_from": FilterSpec("created_from", report_run.c.created_at, "from"),
        "created_to": FilterSpec("created_to", report_run.c.created_at, "to"),
    },
)


def _route_path(request: Request) -> str:
    return str(getattr(request.scope.get("route"), "path", request.url.path))


def _admitted(
    request: Request, ctx: Annotated[RequestContext, Depends(require_authenticated())]
) -> RequestContext:
    """The guard of the read routes (ruling R-63 (a)): a principal that may run a report —
    ``report.run``, or ``audit.read`` for the access registers; any other is refused 403 after one
    ``DENIED`` audit event (``framework.require_admitted``)."""
    framework.require_admitted(
        ctx, method=request.method, path=_route_path(request), keyring=request.app.state.keyring
    )
    source = export_visibility.source_permission(ctx.principal)
    if source is not None:
        # Preserve the original context for ordinary reports; this checks source MFA only.
        require(source)(request, ctx)
    return ctx


def _call_export_replay_access(request: Request, ctx: RequestContext, replay: Replay) -> None:
    """Authorize the actual stored response after lookup, before returning any cached bytes."""
    saved_id = next(
        (value for name, value in replay.headers.items() if name.lower() == RUN_ID_HEADER.lower()),
        None,
    )
    if saved_id is not None and _call_export_run_access(request, uuid.UUID(saved_id), ctx):
        current = refresh_request_context(request, get_clock(request))
        before, after = ctx.principal, current.principal
        if (before.tenant_id, before.id, before.kind) != (after.tenant_id, after.id, after.kind):
            raise Problem("not-found")
        _call_export_run_access(request, uuid.UUID(saved_id), current)


type RunContext = Annotated[RequestContext, Depends(_admitted)]
# A command's guard is ``command(per_subject=True)``; its handler admits the principal first.
type RunCommand = Annotated[
    CommandContext,
    Depends(command(per_subject=True, replay_guard=_call_export_replay_access)),
]
type Params = Annotated[ListParams, Depends(list_params)]
type Deps = Annotated[KernelDeps, Depends(kernel_deps)]

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _total(response: Response, result: ListResult) -> None:
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count


def _deferred(
    request: Request,
    cmd: CommandContext,
    deps: KernelDeps,
    start: Callable[[UnitOfWork], tuple[uuid.UUID, JobOut]],
) -> Response:
    """Run a command that creates a report run: 202 API-S-Job, ``Location`` of the job and the run
    id header, both kept for replay. The principal is admitted first, as on the read routes."""
    started: dict[str, uuid.UUID] = {}

    def handle(uow: UnitOfWork) -> JobOut:
        framework.require_admitted(
            uow.ctx, method=request.method, path=_route_path(request), keyring=uow.keyring
        )
        run_id, job = start(uow)
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
    "/report-definitions",
    operation_id="report_definitions_list",
    response_model=ListOut[ReportDefinitionOut],
    response_model_exclude_unset=True,
    responses=problem_responses(*_READ_PROBLEMS),
)
def report_definitions_list(ctx: RunContext) -> ListOut[ReportDefinitionOut]:
    """The current standard report definitions in catalogue order (REQ-RPT-001): every one for a
    holder of ``report.run``; for a caller without it, those of the reports it may run."""
    items = queries.read(
        ctx,
        lambda session: [
            framework.definition_out(row, ctx.principal)
            for row in framework.definition_rows(session)
            if framework.definition_listed(ctx.principal, str(row["code"]))
        ],
    )
    return ListOut[ReportDefinitionOut](items=items, next_cursor=None)


@router.get(
    "/report-definitions/{code}",
    operation_id="report_definitions_get",
    response_model=ReportDefinitionOut,
    response_model_exclude_unset=True,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def report_definitions_get(code: str, ctx: RunContext) -> ReportDefinitionOut:
    """A current definition; ``ipe_logic`` only for holders of ``report.export`` (REQ-RPT-027)."""
    return queries.read(ctx, lambda session: framework.get_definition(session, ctx.principal, code))


@router.get(
    "/report-runs",
    operation_id="report_runs_list",
    response_model=ListOut[ReportRunOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def report_runs_list(response: Response, ctx: RunContext, params: Params) -> ListOut[ReportRunOut]:
    """Report runs visible to the caller — each within its scope of the report's run permission;
    filters ``report_code``, ``status``, ``created_from``, ``created_to``; sort ``id`` (default
    ``-id``) or ``created_at``."""

    def page(session: Session) -> tuple[ListResult, list[ReportRunOut]]:
        result = paginate(session, framework.runs_statement(ctx.principal), RUN_LIST, params)
        return result, framework.run_outs(session, [dict(row) for row in result.items])

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[ReportRunOut](items=items, next_cursor=result.next_cursor)


def _require_call_export(request: Request, ctx: RequestContext) -> None:
    source = export_visibility.source_permission(ctx.principal) or "ai.use"
    require(source)(request, ctx)
    require(EXPORT)(request, ctx)


def _call_export_run_access(
    request: Request,
    run_id: uuid.UUID,
    ctx: RequestContext,
) -> bool:
    """Source MFA and retained ownership precede both direct reads and cached rerun replies."""
    protected = queries.read(
        ctx,
        lambda session: session.scalar(
            select(report_run.c.id).where(report_run.c.id == run_id, export_visibility.protected())
        ),
    )
    if protected is not None:
        queries.read(
            ctx,
            lambda session: framework.run_row(
                session, ctx.principal, run_id, framework.RUN_PERMISSION
            ),
        )
        _require_call_export(request, ctx)
        return True
    return False


@router.post(
    "/report-runs",
    operation_id="report_runs_create",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def report_runs_create(
    request: Request,
    body: ReportRunCreateIn,
    cmd: RunCommand,
    deps: Deps,
) -> Response:
    """Start a report run: the caller holds the report's run permission and what it declares; the
    parameters are validated against the definition's ``parameters_schema`` and stored with their
    defaults; a file format needs ``report.export``."""

    def start(uow: UnitOfWork) -> tuple[uuid.UUID, JobOut]:
        if body.report_code == export_visibility.CODE:
            _require_call_export(request, uow.ctx)
        return framework.create_run(uow, body)

    return _deferred(request, cmd, deps, start)


@router.get(
    "/report-runs/{run_id}",
    operation_id="report_runs_get",
    response_model=ReportRunOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def report_runs_get(run_id: uuid.UUID, ctx: RunContext, deps: Deps) -> ReportRunOut:
    """API-S-ReportRun: every parameter, scope, source, engine release, totals and output. A run
    of a report that declares a further permission needs it (04 API-R-41 rev 1.99)."""
    return queries.read(
        ctx, lambda session: framework.get_run(ctx, session, run_id, keyring=deps.keyring)
    )


@router.get(
    "/report-runs/{run_id}/data",
    operation_id="report_runs_data",
    response_model=ReportRunDataOut,
    responses=problem_responses(
        *_READ_PROBLEMS, "validation-failed", "not-found", "invalid-transition"
    ),
)
def report_runs_data(
    run_id: uuid.UUID,
    response: Response,
    ctx: RunContext,
    deps: Deps,
    params: Params,
    section_table: Annotated[str | None, Query(max_length=200)] = None,
) -> ReportRunDataOut:
    """The rows of a JSON run in response order, ``limit`` rows a page (RV-11 pages of 200); every
    page also carries ``columns``, the definition's columns in builder order (D-88 L7-1-Q-5)."""
    unsupported = set(params.filters) - {"section_table"}
    if unsupported:
        name = sorted(unsupported)[0]
        raise invalid(name, f"{name} is not a filter of report run data.")
    if len(params.filters.get("section_table", ())) > 1:
        raise invalid("section_table", "Choose one table.")
    if params.sort is not None:
        raise invalid("sort", "Report run data keeps the response order.")
    if params.q is not None:
        raise invalid("q", "report run data has no search.")
    document = framework.run_document(ctx, run_id, files=deps.files, keyring=deps.keyring)
    sections = []
    selected = None
    for section in document.get("sections", ()):
        tables = []
        for table in section["tables"]:
            dataset = table["dataset"]
            tables.append(
                {
                    **{
                        key: table[key]
                        for key in (
                            "key",
                            "basis",
                            "omitted",
                            "notes",
                            "source_run_id",
                            "source_sha256",
                        )
                    },
                    "title": dataset["report"]["name"],
                    "row_count": dataset["row_count"],
                }
            )
            if table["key"] == section_table:
                selected = dataset
        sections.append(
            {
                "number": section["number"],
                "title": section["title"],
                "interim_required": section["interim_required"],
                "tables": tables,
            }
        )
    if section_table is not None and selected is None:
        raise invalid("section_table", "This table is not part of the saved report.")
    dataset = document if selected is None else selected
    rows, columns = dataset["rows"], dataset["columns"]
    marker = str(run_id) if section_table is None else f"{run_id}:{section_table}"
    offset = 0
    if params.cursor is not None:
        last = decode_cursor(params.cursor, sort=DATA_SORT, filters_sha256=marker)
        if len(last) != 1 or not isinstance(last[0], str) or not last[0].isdigit():
            raise invalid("cursor", "This cursor is not valid. Reload the list.")
        offset = int(last[0])
    page = rows[offset : offset + params.limit]
    following = offset + len(page)
    next_cursor = (
        encode_cursor(DATA_SORT, marker, [str(following)]) if following < len(rows) else None
    )
    if params.count:
        response.headers[TOTAL_COUNT_HEADER] = str(len(rows))
    return ReportRunDataOut(
        items=[ReportRowOut.model_validate(item) for item in page],
        next_cursor=next_cursor,
        columns=[ReportColumnOut.model_validate(column) for column in columns],
        sections=[DisclosureSectionOut.model_validate(section) for section in sections],
        forecast=None
        if document.get("forecast") is None
        else ForecastHeaderOut.model_validate(document["forecast"]),
    )


def _output_access(
    request: Request,
    run_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require(EXPORT))],
) -> RequestContext:
    _call_export_run_access(request, run_id, ctx)
    return ctx


@router.get(
    "/report-runs/{run_id}/output",
    operation_id="report_runs_output",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"application/octet-stream": {}}, "description": "The run output"},
        **problem_responses(*_READ_PROBLEMS, "not-found", "invalid-transition"),
    },
)
def report_runs_output(
    run_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(_output_access)],
    deps: Deps,
    part: Annotated[Literal["output", "manifest"], Query()] = "output",
) -> StreamingResponse:
    """Stream the output file, or the JSON manifest of a CSV run, as an attachment; one
    ``report.export`` audit event names the run (REQ-PLT-019)."""
    download = framework.open_output(ctx, run_id, part=part, files=deps.files, keyring=deps.keyring)
    return StreamingResponse(
        framework.chunks(download.stream),
        media_type=download.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{download.file_name}"',
            "Content-Security-Policy": DOWNLOAD_CSP,
        },
    )


@router.post(
    "/report-runs/{run_id}/rerun",
    operation_id="report_runs_rerun",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def report_runs_rerun(
    request: Request,
    run_id: uuid.UUID,
    cmd: RunCommand,
    deps: Deps,
) -> Response:
    """Rerun from the same source: identical parameters; the job result adds
    ``output_sha256_equal`` and ``control_totals_equal`` (REQ-RPT-002; CTL-029)."""

    def start(uow: UnitOfWork) -> tuple[uuid.UUID, JobOut]:
        _call_export_run_access(request, run_id, uow.ctx)
        return framework.rerun(uow, run_id)

    return _deferred(request, cmd, deps, start)
