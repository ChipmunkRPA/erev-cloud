"""API-R-32 portfolio metadata and audited member changes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    assert_version,
    command,
    kernel_deps,
    problem_responses,
    row_etag,
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    ListParams,
    ListResult,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import contract, estimate, estimate_version, portfolio, portfolio_member
from erev_api.domain.contracts import (
    estimates,
    portfolio_estimate_versions,
    portfolios,
    queries,
    portfolio_preview,
    portfolio_impact,
    portfolio_workflow,
)
from erev_api.schemas.common import ListOut
from erev_api.schemas.estimates import EstimateOut, EstimateVersionOut, EstimateVersionSubmitIn
from erev_api.schemas.portfolios import (
    PortfolioBreakagePreviewOut,
    PortfolioImpactOut,
    PortfolioEstimateIn,
    PortfolioEstimateVersionIn,
    PortfolioIn,
    PortfolioMemberCloseIn,
    PortfolioMemberIn,
    PortfolioMemberOut,
    PortfolioOut,
)
from erev_api.uow import UnitOfWork

router = APIRouter(
    prefix=API_PREFIX, tags=["API-R-32 Estimates and portfolios"], route_class=GuardedRoute
)
READ_PROBLEMS = (
    "unauthenticated",
    "session-expired",
    "forbidden",
    "not-found",
    "validation-failed",
)
WRITE_PROBLEMS = (
    *READ_PROBLEMS,
    "idempotency-key-reused",
    "idempotency-in-progress",
    "precondition-required",
    "precondition-failed",
    "invalid-transition",
)
type ReadContext = Annotated[RequestContext, Depends(require("contract.read"))]
type CreateContext = Annotated[CommandContext, Depends(command("estimate.create"))]
type EditContext = Annotated[
    CommandContext, Depends(command("estimate.create", precondition="row"))
]
type Deps = Annotated[KernelDeps, Depends(kernel_deps)]
type Params = Annotated[ListParams, Depends(list_params)]
LIST = ListSpec(
    resource="portfolios",
    sort_keys={"id": portfolio.c.id, "code": portfolio.c.code, "name": portfolio.c.name},
    default_sort="code",
    filters={},
    search_columns=(portfolio.c.code, portfolio.c.name),
)
MEMBERS = ListSpec(
    resource="portfolio-members",
    sort_keys={
        "id": portfolio_member.c.id,
        "contract_external_id": contract.c.external_id,
        "valid_from_known_at": portfolio_member.c.valid_from_known_at,
    },
    default_sort="contract_external_id",
    filters={},
    custom_filters=frozenset({"include_history"}),
)


@router.get(
    "/portfolios",
    operation_id="portfolios_list",
    response_model=ListOut[PortfolioOut],
    responses=problem_responses(*READ_PROBLEMS),
)
def list_portfolios(ctx: ReadContext, params: Params, response: Response) -> ListOut[PortfolioOut]:
    result = queries.read(
        ctx,
        lambda session: paginate(
            session, select(*[portfolio.c[k] for k in PortfolioOut.model_fields]), LIST, params
        ),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[PortfolioOut](
        items=[PortfolioOut.model_validate(row) for row in result.items],
        next_cursor=result.next_cursor,
    )


@router.get(
    "/portfolios/{portfolio_id}",
    operation_id="portfolios_get",
    response_model=PortfolioOut,
    responses=problem_responses(*READ_PROBLEMS),
)
def get_portfolio(portfolio_id: UUID, ctx: ReadContext, response: Response) -> PortfolioOut:
    out = queries.read(ctx, lambda session: portfolios.get(session, portfolio_id))
    response.headers["ETag"] = row_etag(out.row_version)
    return out


@router.post(
    "/portfolios",
    operation_id="portfolios_create",
    response_model=PortfolioOut,
    status_code=201,
    responses=problem_responses(*WRITE_PROBLEMS),
)
def create_portfolio(body: PortfolioIn, cmd: CreateContext, deps: Deps) -> Response:
    return run_command(
        cmd,
        deps,
        lambda uow: portfolios.save(uow, body),
        status_code=201,
        location=lambda out: f"{API_PREFIX}/portfolios/{out.id}",
        etag=lambda out: row_etag(out.row_version),
    )


@router.put(
    "/portfolios/{portfolio_id}",
    operation_id="portfolios_update",
    response_model=PortfolioOut,
    responses=problem_responses(*WRITE_PROBLEMS),
)
def update_portfolio(
    portfolio_id: UUID, body: PortfolioIn, cmd: EditContext, deps: Deps
) -> Response:
    return run_command(
        cmd,
        deps,
        lambda uow: portfolios.save(
            uow,
            body,
            portfolio_id=portfolio_id,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        ),
        etag=lambda out: row_etag(out.row_version),
    )


@router.get(
    "/portfolios/{portfolio_id}/members",
    operation_id="portfolio_members_list",
    response_model=ListOut[PortfolioMemberOut],
    responses=problem_responses(*READ_PROBLEMS),
)
def list_members(
    portfolio_id: UUID,
    ctx: ReadContext,
    params: Params,
    response: Response,
    include_history: bool = False,
) -> ListOut[PortfolioMemberOut]:
    def read(session: Session) -> ListResult:
        portfolios.get(session, portfolio_id)
        return paginate(
            session, portfolios.members(portfolio_id, history=include_history), MEMBERS, params
        )

    result = queries.read(ctx, read)
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[PortfolioMemberOut](
        items=[PortfolioMemberOut.model_validate(row) for row in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/portfolios/{portfolio_id}/members",
    operation_id="portfolio_members_join",
    response_model=PortfolioMemberOut,
    status_code=201,
    responses=problem_responses(*WRITE_PROBLEMS),
)
def join_member(
    portfolio_id: UUID, body: PortfolioMemberIn, cmd: EditContext, deps: Deps
) -> Response:
    def handle(uow: UnitOfWork) -> PortfolioMemberOut:
        return portfolios.change_member(
            uow,
            portfolio_id,
            contract_id=body.contract_id,
            rationale=body.rationale,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(
        cmd, deps, handle, status_code=201, etag=lambda out: row_etag(out.portfolio_row_version)
    )


@router.post(
    "/portfolios/{portfolio_id}/members/{contract_id}/remove",
    operation_id="portfolio_members_remove",
    response_model=PortfolioMemberOut,
    responses=problem_responses(*WRITE_PROBLEMS),
)
def remove_member(
    portfolio_id: UUID,
    contract_id: UUID,
    body: PortfolioMemberCloseIn,
    cmd: EditContext,
    deps: Deps,
) -> Response:
    return run_command(
        cmd,
        deps,
        lambda uow: portfolios.change_member(
            uow,
            portfolio_id,
            contract_id=contract_id,
            remove=True,
            rationale=body.rationale,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        ),
        etag=lambda out: row_etag(out.portfolio_row_version),
    )


ESTIMATES = ListSpec(
    resource="portfolio-estimates",
    default_sort="element_code",
    sort_keys={"id": estimate.c.id, "element_code": estimate.c.element_code},
    filters={},
    search_columns=(estimate.c.element_code,),
)


@router.get(
    "/portfolios/{portfolio_id}/estimates",
    operation_id="portfolio_estimates_list",
    response_model=ListOut[EstimateOut],
    responses=problem_responses(*READ_PROBLEMS),
)
def list_estimates(
    portfolio_id: UUID, ctx: ReadContext, params: Params, response: Response
) -> ListOut[EstimateOut]:
    def read(session: Session) -> tuple[ListResult, list[EstimateOut]]:
        portfolios.require_estimate_scope(session, ctx, portfolio_id, "contract.read")
        result = paginate(
            session,
            select(estimate).where(estimate.c.portfolio_id == portfolio_id),
            ESTIMATES,
            params,
        )
        return result, estimates.estimate_outs(session, [dict(row) for row in result.items])

    result, items = queries.read(ctx, read)
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[EstimateOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/portfolios/{portfolio_id}/estimates/{estimate_id}",
    operation_id="portfolio_estimates_get",
    response_model=EstimateOut,
    responses=problem_responses(*READ_PROBLEMS),
)
def get_estimate(portfolio_id: UUID, estimate_id: UUID, ctx: ReadContext) -> EstimateOut:
    return queries.read(
        ctx,
        lambda session: portfolios.get_estimate_definition(session, ctx, portfolio_id, estimate_id),
    )


@router.post(
    "/portfolios/{portfolio_id}/estimates",
    operation_id="portfolio_estimates_create",
    response_model=EstimateOut,
    status_code=201,
    responses=problem_responses(*WRITE_PROBLEMS),
)
def create_estimate(
    portfolio_id: UUID, body: PortfolioEstimateIn, cmd: EditContext, deps: Deps
) -> Response:
    return run_command(
        cmd,
        deps,
        lambda uow: portfolios.create_estimate_definition(
            uow,
            portfolio_id,
            body,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        ),
        status_code=201,
        location=lambda out: f"{API_PREFIX}/portfolios/{portfolio_id}/estimates/{out.id}",
    )


VERSIONS = ListSpec(
    resource="portfolio-estimate-versions",
    default_sort="-version_no",
    sort_keys={"id": estimate_version.c.id, "version_no": estimate_version.c.version_no},
    filters={},
)
VERSION_PATH = "/portfolios/{portfolio_id}/estimates/{estimate_id}/versions"


@router.get(
    VERSION_PATH,
    operation_id="portfolio_estimate_versions_list",
    response_model=ListOut[EstimateVersionOut],
    responses=problem_responses(*READ_PROBLEMS),
)
def list_versions(
    portfolio_id: UUID, estimate_id: UUID, ctx: ReadContext, params: Params, response: Response
) -> ListOut[EstimateVersionOut]:
    def read(session: Session) -> tuple[ListResult, list[EstimateVersionOut]]:
        portfolios.get_estimate_definition(session, ctx, portfolio_id, estimate_id)
        result = paginate(
            session,
            select(estimate_version).where(estimate_version.c.estimate_id == estimate_id),
            VERSIONS,
            params,
        )
        return result, estimates.version_outs(session, [dict(row) for row in result.items])

    result, items = queries.read(ctx, read)
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[EstimateVersionOut](items=items, next_cursor=result.next_cursor)


@router.get(
    VERSION_PATH + "/{version_id}",
    operation_id="portfolio_estimate_versions_get",
    response_model=EstimateVersionOut,
    responses=problem_responses(*READ_PROBLEMS),
)
def get_version(
    portfolio_id: UUID, estimate_id: UUID, version_id: UUID, ctx: ReadContext, response: Response
) -> EstimateVersionOut:
    out = queries.read(
        ctx,
        lambda session: portfolio_estimate_versions.get(
            session, ctx, portfolio_id, estimate_id, version_id
        ),
    )
    response.headers["ETag"] = row_etag(out.row_version)
    return out


@router.post(
    VERSION_PATH,
    operation_id="portfolio_estimate_versions_create",
    status_code=201,
    response_model=EstimateVersionOut,
    responses=problem_responses(*WRITE_PROBLEMS),
)
def create_version(
    portfolio_id: UUID,
    estimate_id: UUID,
    body: PortfolioEstimateVersionIn,
    cmd: EditContext,
    deps: Deps,
) -> Response:
    """Create a draft; If-Match is the portfolio's current row version."""
    return run_command(
        cmd,
        deps,
        lambda uow: portfolio_estimate_versions.save(
            uow,
            portfolio_id,
            estimate_id,
            body,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        ),
        status_code=201,
        etag=lambda out: row_etag(out.row_version),
        location=lambda out: (
            f"{API_PREFIX}/portfolios/{portfolio_id}/estimates/{estimate_id}/versions/{out.id}"
        ),
    )


@router.put(
    VERSION_PATH + "/{version_id}",
    operation_id="portfolio_estimate_versions_update",
    response_model=EstimateVersionOut,
    responses=problem_responses(*WRITE_PROBLEMS),
)
def update_version(
    portfolio_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    body: PortfolioEstimateVersionIn,
    cmd: EditContext,
    deps: Deps,
) -> Response:
    """Replace draft values; If-Match is this estimate version's row version."""
    return run_command(
        cmd,
        deps,
        lambda uow: portfolio_estimate_versions.save(
            uow,
            portfolio_id,
            estimate_id,
            body,
            version_id=version_id,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        ),
        etag=lambda out: row_etag(out.row_version),
    )


@router.post(
    VERSION_PATH + "/{version_id}/discard",
    operation_id="portfolio_estimate_versions_discard",
    response_model=EstimateVersionOut,
    responses=problem_responses(*WRITE_PROBLEMS),
)
def discard_version(
    portfolio_id: UUID, estimate_id: UUID, version_id: UUID, cmd: EditContext, deps: Deps
) -> Response:
    """Retain the version as VOIDED; If-Match is the version's row version."""
    return run_command(
        cmd,
        deps,
        lambda uow: portfolio_estimate_versions.save(
            uow,
            portfolio_id,
            estimate_id,
            None,
            version_id=version_id,
            discard=True,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        ),
        etag=lambda out: row_etag(out.row_version),
    )


@router.get(
    VERSION_PATH + "/{version_id}/allocation-preview",
    operation_id="portfolio_breakage_allocation_preview",
    response_model=PortfolioBreakagePreviewOut,
    responses=problem_responses(*READ_PROBLEMS),
)
def allocation_preview(
    portfolio_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    ctx: ReadContext,
    book_code: str | None = None,
) -> PortfolioBreakagePreviewOut:
    return queries.read(
        ctx,
        lambda session: portfolio_preview.preview(
            session,
            ctx,
            portfolio_id,
            estimate_id,
            version_id,
            book_code,
        ),
    )


@router.get(
    VERSION_PATH + "/{version_id}/impact-preview",
    operation_id="portfolio_return_impact_preview",
    response_model=PortfolioImpactOut,
    responses=problem_responses(*READ_PROBLEMS),
)
def impact_preview(
    portfolio_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    ctx: ReadContext,
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> PortfolioImpactOut:
    # Authorization, membership, baseline and native input must see one population.
    with tenant_session(
        ctx.principal.db_context, read_only=True, isolation_level="REPEATABLE READ"
    ) as session:
        return portfolio_impact.preview(
            session, ctx, portfolio_id, estimate_id, version_id, deps.clock.now()
        )


@router.post(
    VERSION_PATH + "/{version_id}/submit",
    operation_id="portfolio_estimate_versions_submit",
    response_model=EstimateVersionOut,
    responses=problem_responses(*WRITE_PROBLEMS),
)
def submit_version(
    portfolio_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    body: EstimateVersionSubmitIn,
    cmd: EditContext,
    deps: Deps,
) -> Response:
    def handle(uow: UnitOfWork) -> EstimateVersionOut:
        portfolio_estimate_versions.get(uow.session, uow.ctx, portfolio_id, estimate_id, version_id)
        return portfolio_workflow.submit(
            uow,
            version_id,
            comment=body.comment,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle, etag=lambda out: row_etag(out.row_version))


@router.post(
    VERSION_PATH + "/{version_id}/withdraw",
    operation_id="portfolio_estimate_versions_withdraw",
    response_model=EstimateVersionOut,
    responses=problem_responses(*WRITE_PROBLEMS),
)
def withdraw_version(
    portfolio_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    body: EstimateVersionSubmitIn,
    cmd: EditContext,
    deps: Deps,
) -> Response:
    def handle(uow: UnitOfWork) -> EstimateVersionOut:
        portfolio_estimate_versions.get(uow.session, uow.ctx, portfolio_id, estimate_id, version_id)
        return portfolio_workflow.withdraw(
            uow,
            version_id,
            comment=body.comment,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle, etag=lambda out: row_etag(out.row_version))
