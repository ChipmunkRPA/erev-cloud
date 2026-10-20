"""API-R-46 asynchronous deal previews and authorized retained evidence reads."""

from typing import Annotated, Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from fastapi import APIRouter, Depends, Response
from sqlalchemy import Select, select

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
from erev_api.api.lists import TOTAL_COUNT_HEADER, ListParams, ListSpec, list_params, paginate
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import deal_preview, legal_entity
from erev_api.domain.forecast import deal_job, deal_results, deal_save
from erev_api.problems import Problem
from erev_api.schemas.common import ListOut
from erev_api.schemas.contracts import ContractOut
from erev_api.schemas.deal_previews import (
    DealPreviewCreateIn,
    DealPreviewOut,
    DealPreviewRequestedOut,
    DealPreviewSaveIn,
    DealPreviewSummaryOut,
)

router = APIRouter(
    prefix=API_PREFIX, tags=["API-R-46 Scenarios and forecasts"], route_class=GuardedRoute
)
PROBLEMS = problem_responses(
    "unauthenticated",
    "session-expired",
    "forbidden",
    "not-found",
    "validation-failed",
    "invalid-transition",
    "precondition-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
type Reader = Annotated[RequestContext, Depends(require("scenario.use"))]


def visible(ctx: RequestContext, *, detail: bool = False) -> Select[Any]:
    columns = [
        deal_preview.c.id,
        deal_preview.c.input["proposal"].label("proposal"),
        deal_preview.c.input_sha256,
        deal_preview.c.result_sha256,
        deal_preview.c.engine_release_id,
        deal_preview.c.saved_contract_id,
        deal_preview.c.created_at,
    ]
    if detail:
        columns += [
            deal_preview.c.input,
            deal_preview.c.result,
            deal_preview.c.pinned_refs,
            legal_entity.c.id.label("entity_id"),
        ]
    statement = (
        select(*columns)
        .join(
            legal_entity,
            (legal_entity.c.tenant_id == deal_preview.c.tenant_id)
            & (legal_entity.c.code == deal_preview.c.input["proposal"]["entity_code"].astext),
        )
        .where(deal_preview.c.tenant_id == ctx.principal.tenant_id)
    )
    scope = ctx.principal.permission_scopes.get("scenario.use")
    if scope != "*":
        statement = statement.where(
            legal_entity.c.id.in_([UUID(str(value)) for value in scope or ()])
        )
    return statement


@router.post(
    "/deal-previews",
    operation_id="deal_previews_create",
    status_code=202,
    response_model=DealPreviewRequestedOut,
    responses=PROBLEMS,
)
def create(
    body: DealPreviewCreateIn,
    cmd: Annotated[CommandContext, Depends(command("scenario.use"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    return run_command(
        cmd,
        deps,
        lambda uow: deal_job.request(uow, body.input),
        status_code=202,
        location=lambda out: f"{API_PREFIX}/jobs/{out.id}",
    )


@router.get(
    "/deal-previews",
    operation_id="deal_previews_list",
    response_model=ListOut[DealPreviewSummaryOut],
    responses=PROBLEMS,
)
def listing(
    response: Response, ctx: Reader, params: Annotated[ListParams, Depends(list_params)]
) -> ListOut[DealPreviewSummaryOut]:
    spec = ListSpec(
        resource="deal-previews",
        filters={},
        default_sort="-created_at",
        sort_keys={"id": deal_preview.c.id, "created_at": deal_preview.c.created_at},
    )
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        page = paginate(session, visible(ctx), spec, params)
    response.headers["Cache-Control"] = "no-store"
    if page.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = page.total_count
    return ListOut(
        items=[DealPreviewSummaryOut.model_validate(row) for row in page.items],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/deal-previews/{preview_id}",
    operation_id="deal_previews_get",
    response_model=DealPreviewOut,
    responses=PROBLEMS,
)
def get(preview_id: UUID, response: Response, ctx: Reader) -> DealPreviewOut:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = (
            session.execute(visible(ctx, detail=True).where(deal_preview.c.id == preview_id))
            .mappings()
            .one_or_none()
        )
        create_scope = ctx.principal.permission_scopes.get("contract.create")
        save_allowed = (
            row is not None
            and row["saved_contract_id"] is None
            and "contract.create" in ctx.principal.permissions
            and (
                create_scope == "*"
                or str(row["entity_id"]) in {str(value) for value in create_scope or ()}
            )
            and deal_save.active_scenario(session, ctx.principal.db_context)
        )
    if row is None:
        raise Problem("not-found")
    if (
        sha256_hex(row["input"]) != row["input_sha256"]
        or sha256_hex(row["result"]) != row["result_sha256"]
    ):
        raise Problem("precondition-failed", "The retained preview evidence failed verification.")
    response.headers["Cache-Control"] = "no-store"
    return DealPreviewOut.model_validate(
        {
            **row,
            "save_allowed": save_allowed,
            "presentation": deal_results.project(row["input"], row["result"]),
        }
    )


@router.post(
    "/deal-previews/{preview_id}/save",
    operation_id="deal_previews_save",
    status_code=201,
    response_model=ContractOut,
    responses=PROBLEMS,
)
def save(
    preview_id: UUID,
    body: DealPreviewSaveIn,
    cmd: Annotated[CommandContext, Depends(command("scenario.use"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    return run_command(
        cmd,
        deps,
        lambda uow: deal_save.save(uow, preview_id, body.contract_external_id),
        status_code=201,
        location=lambda out: f"{API_PREFIX}/contracts/{out.id}",
    )
