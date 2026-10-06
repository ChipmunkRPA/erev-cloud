"""API-R-27 SSP calculator: runs, results, observations, exclusions and the draft version.

04 §15.3 API-R-27, §16.14, T-REF-32 to T-REF-34, API-C-06, API-C-09, API-C-12; SCREENS §11.5;
BUILD_SPEC RFD-15. Reads need ``ssp.read``; running the calculator, excluding an observation and
creating the draft version need ``ssp.create`` (PRD ACT-19). ``POST /ssp-calculator-runs`` answers
202 with API-S-Job, ``Location: /api/v1/jobs/{id}`` and the run id in
``X-Erev-Ssp-Calculator-Run-Id`` (L2-1-Q-52). An exclusion recomputes the statistics in its own
request (L2-1-Q-57).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Final

from erev_engine.canonical import sha256_hex
from fastapi import APIRouter, Depends, Query, Response

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
    COUNT_CAP,
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListSpec,
    decode_cursor,
    encode_cursor,
    invalid,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import product, ssp_calculator_result, ssp_calculator_run
from erev_api.domain.platform import jobs
from erev_api.domain.ssp import calculator, queries
from erev_api.enums import RunStatus
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.ssp_books import SspBookVersionOut
from erev_api.schemas.ssp_calculator import (
    SspCalculatorDraftVersionIn,
    SspCalculatorExclusionIn,
    SspCalculatorExclusionOut,
    SspCalculatorObservationOut,
    SspCalculatorResultOut,
    SspCalculatorRunIn,
    SspCalculatorRunOut,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-27 SSP calculator"
READ_PERMISSION: Final = "ssp.read"
CREATE_PERMISSION: Final = "ssp.create"
RUN_ID_HEADER: Final = "X-Erev-Ssp-Calculator-Run-Id"
OBSERVATION_RESOURCE: Final = "ssp-calculator-observations"
OBSERVATION_SORT: Final = "date"
OBSERVATION_FILTERS: Final = frozenset({"product"})
CURSOR_INVALID: Final = "This cursor is not valid. Reload the list."
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
RUN_LIST: Final = ListSpec(
    resource="ssp-calculator-runs",
    sort_keys={
        "id": ssp_calculator_run.c.id,
        "name": ssp_calculator_run.c.name,
        "created_at": ssp_calculator_run.c.created_at,
    },
    default_sort="-created_at",
    filters={
        "status": FilterSpec(
            name="status",
            column=ssp_calculator_run.c.status,
            kind="exact",
            choices=frozenset(status.value for status in RunStatus),
        )
    },
    search_columns=(ssp_calculator_run.c.name,),
)
RESULT_LIST: Final = ListSpec(
    resource="ssp-calculator-results",
    sort_keys={"id": ssp_calculator_result.c.id, "product_code": product.c.code},
    default_sort="product_code",
    filters={"product": FilterSpec(name="product", column=product.c.code, kind="exact")},
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def observation_page(
    items: list[dict[str, Any]], params: ListParams
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """One page of observations in date order, filtered by ``product`` (a product code); the
    cursor carries the offset of the next item (API-C-09)."""
    if params.sort is not None and params.sort != OBSERVATION_SORT:
        raise invalid(
            "sort", f"Sort by {OBSERVATION_SORT} without a leading -; its order is fixed."
        )
    unknown = sorted(set(params.filters) - OBSERVATION_FILTERS)
    if unknown:
        raise invalid(unknown[0], f"{unknown[0]} is not a filter of {OBSERVATION_RESOURCE}.")
    if params.q:
        raise invalid("q", f"{OBSERVATION_RESOURCE} has no search.")
    products = params.filters.get("product")
    if products:
        items = [item for item in items if item["product_code"] in products]
    filters_sha256 = sha256_hex(
        {"filters": {name: list(values) for name, values in params.filters.items()}, "q": params.q}
    )
    start = 0
    if params.cursor is not None:
        last = decode_cursor(params.cursor, sort=OBSERVATION_SORT, filters_sha256=filters_sha256)
        if len(last) != 1 or not str(last[0]).isdigit():
            raise invalid("cursor", CURSOR_INVALID)
        start = int(str(last[0]))
    end = start + params.limit
    next_cursor = (
        encode_cursor(OBSERVATION_SORT, filters_sha256, [str(end)]) if end < len(items) else None
    )
    total_count = None
    if params.count:
        total_count = f"{COUNT_CAP}+" if len(items) > COUNT_CAP else str(len(items))
    return items[start:end], next_cursor, total_count


@router.get(
    "/ssp-calculator-runs",
    operation_id="ssp_calculator_runs_list",
    response_model=ListOut[SspCalculatorRunOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def ssp_calculator_runs_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[list[RunStatus] | None, Query()] = None,
) -> ListOut[SspCalculatorRunOut]:
    """The calculator runs the caller reaches — the runs whose scope its ``contract.read``
    covers (04 T-REF-32); sort ``created_at`` (default ``-created_at``), ``name`` or ``id``;
    ``q`` searches the name (SCREENS §11.5 runs panel)."""
    result, items = calculator.list_runs(
        ctx, page=lambda session, statement: paginate(session, statement, RUN_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[SspCalculatorRunOut](
        items=[SspCalculatorRunOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/ssp-calculator-runs",
    operation_id="ssp_calculator_runs_create",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def ssp_calculator_runs_create(
    body: SspCalculatorRunIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Run the historical SSP calculator over a pool of standalone sales or committed contract
    lines; the run posts nothing and needs no approval (PRD BR-SSP-04). It reads the contracts
    of the entities the caller's ``contract.read`` covers and keeps that scope: the run is read
    and commanded by members whose ``contract.read`` covers it, and is 404 for anyone else."""
    created: dict[str, uuid.UUID] = {}

    def handle(uow: UnitOfWork) -> JobOut:
        run_id, job_id = calculator.create_run(uow, body=body)
        created["run_id"] = run_id
        return jobs.job_out_of(uow.session, job_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        location=lambda job: f"{API_PREFIX}/jobs/{job.id}",
        extra_headers=lambda _job: {RUN_ID_HEADER: str(created["run_id"])},
    )


@router.get(
    "/ssp-calculator-runs/{run_id}",
    operation_id="ssp_calculator_runs_get",
    response_model=SspCalculatorRunOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def ssp_calculator_runs_get(
    run_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
) -> SspCalculatorRunOut:
    """One calculator run with its status, observation count and draft version; 404 for a run
    out of the caller's reach."""
    return SspCalculatorRunOut.model_validate(calculator.get_run(ctx, run_id))


@router.get(
    "/ssp-calculator-runs/{run_id}/results",
    operation_id="ssp_calculator_results_list",
    response_model=ListOut[SspCalculatorResultOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def ssp_calculator_results_list(
    run_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    product_code: Annotated[str | None, Query(alias="product", description="Product code")] = None,
) -> ListOut[SspCalculatorResultOut]:
    """The current statistics of each product and key; sort ``product_code`` (default) or ``id``
    (SCREENS §11.5 figures, statistics and distribution)."""
    result, items = calculator.list_results(
        ctx,
        run_id,
        page=lambda session, statement: paginate(session, statement, RESULT_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[SspCalculatorResultOut](
        items=[SspCalculatorResultOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.get(
    "/ssp-calculator-runs/{run_id}/observations",
    operation_id="ssp_calculator_observations_list",
    response_model=ListOut[SspCalculatorObservationOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def ssp_calculator_observations_list(
    run_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
    product_code: Annotated[str | None, Query(alias="product", description="Product code")] = None,
) -> ListOut[SspCalculatorObservationOut]:
    """The observations of the run from its observations file, in date order (04 §16.14)."""
    items = calculator.observation_items(ctx, run_id, files=deps.files, keyring=deps.keyring)
    page, next_cursor, total_count = observation_page(items, params)
    if total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = total_count
    return ListOut[SspCalculatorObservationOut](
        items=[SspCalculatorObservationOut.model_validate(item) for item in page],
        next_cursor=next_cursor,
    )


@router.post(
    "/ssp-calculator-runs/{run_id}/exclusions",
    operation_id="ssp_calculator_exclusions_create",
    status_code=201,
    response_model=SspCalculatorExclusionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def ssp_calculator_exclusions_create(
    run_id: uuid.UUID,
    body: SspCalculatorExclusionIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Exclude an observation as an outlier with a reason of at least 10 characters; the statistics
    are recomputed (REQ-SSP-009; SCREENS §11.5 exclude modal)."""

    def handle(uow: UnitOfWork) -> SspCalculatorExclusionOut:
        exclusion_id = calculator.exclude_observation(uow, run_id, body=body)
        row = calculator.exclusion_row(
            uow.session, exclusion_id, source_reference=body.source_reference.strip()
        )
        return SspCalculatorExclusionOut.model_validate(row)

    return run_command(cmd, deps, handle, status_code=201)


@router.post(
    "/ssp-calculator-runs/{run_id}/create-draft-version",
    operation_id="ssp_calculator_runs_create_draft_version",
    status_code=201,
    response_model=SspBookVersionOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-frozen"
    ),
)
def ssp_calculator_runs_create_draft_version(
    run_id: uuid.UUID,
    body: SspCalculatorDraftVersionIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a DRAFT version of the run's book from its results: the latest approved entries with
    each result's band around the median (PRD J-02.3)."""

    def handle(uow: UnitOfWork) -> SspBookVersionOut:
        version_id = calculator.create_draft_version(uow, run_id, body=body)
        return SspBookVersionOut.model_validate(
            queries.ssp_book_version_row(uow.session, version_id)
        )

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/ssp-book-versions/{out.id}",
        etag=lambda out: row_etag(out.row_version),
    )
