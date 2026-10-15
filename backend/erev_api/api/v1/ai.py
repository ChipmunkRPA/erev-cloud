"""API-R-47: AI submission and authorized retained proposal reads."""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

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
    FilterSpec,
    ListParams,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require, require_authenticated
from erev_api.auth.entity_scope import holds_all
from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_model_log, ai_proposal
from erev_api.domain.ai import acceptance, commands, extraction_reads, queries
from erev_api.domain.platform.jobs import job_out_of
from erev_api.enums import AiProposalKind, AiProposalStatus
from erev_api.schemas.ai import (
    AIContractExtractionIn,
    AIDocumentTextOut,
    AIExplanationIn,
    AIExtractionDraftIn,
    AIExtractionProposalOut,
    AIModelLogOut,
    AIProposalAcceptedOut,
    AIProposalOut,
    AIProposalRejectIn,
)
from erev_api.schemas.common import JobOut, ListOut
from erev_api.uow import UnitOfWork

PROPOSAL_LIST: Final = ListSpec(
    resource="ai_proposals",
    sort_keys={"id": ai_proposal.c.id, "created_at": ai_proposal.c.created_at},
    default_sort="-created_at",
    filters={
        "kind": FilterSpec(
            name="kind",
            column=ai_proposal.c.kind,
            kind="exact",
            choices=frozenset(value.value for value in AiProposalKind),
        ),
        "status": FilterSpec(
            name="status",
            column=ai_proposal.c.status,
            kind="exact",
            choices=frozenset(value.value for value in AiProposalStatus),
        ),
    },
)

router = APIRouter(prefix=API_PREFIX, tags=["API-R-47 AI"], route_class=GuardedRoute)


@router.post(
    "/ai/explanations",
    operation_id="ai_explanations_create",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(
        "unauthenticated",
        "session-expired",
        "forbidden",
        "not-found",
        "validation-failed",
        "idempotency-key-reused",
        "idempotency-in-progress",
        "ai-disabled",
    ),
)
def explanations_create(
    body: AIExplanationIn,
    cmd: Annotated[CommandContext, Depends(command("ai.use"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Queue a number explanation after checking the human's current source access."""

    def handle(uow: UnitOfWork) -> JobOut:
        job_id = commands.request_explanation(
            uow,
            object_type=body.object_type,
            object_id=body.id,
            measure=body.measure,
            period=body.period,
            platform_kill_switch=deps.settings.ai_kill_switch,
        )
        return job_out_of(uow.session, job_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        location=lambda result: f"{API_PREFIX}/jobs/{result.id}",
    )


@router.get(
    "/ai/proposals",
    operation_id="ai_proposals_list",
    response_model=ListOut[AIProposalOut | AIExtractionProposalOut],
    responses=problem_responses(
        "unauthenticated", "session-expired", "forbidden", "validation-failed"
    ),
)
def proposals_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require("ai.use"))],
    params: Annotated[ListParams, Depends(list_params)],
    kind: Annotated[AiProposalKind | None, Query()] = None,
    status: Annotated[AiProposalStatus | None, Query()] = None,
) -> ListOut[AIProposalOut | AIExtractionProposalOut]:
    """Page authorized retained proposals with kind/status filters and stable cursor order."""
    result, items = queries.list_proposals(
        ctx,
        page=lambda session, statement: paginate(session, statement, PROPOSAL_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[AIProposalOut | AIExtractionProposalOut](
        items=items, next_cursor=result.next_cursor
    )


@router.get(
    "/ai/proposals/{id}",
    operation_id="ai_proposals_get",
    response_model=AIProposalOut | AIExtractionProposalOut,
    responses=problem_responses("unauthenticated", "session-expired", "forbidden", "not-found"),
)
def proposals_get(
    id: UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require("ai.use"))],
) -> AIProposalOut | AIExtractionProposalOut:
    """Read retained evidence under the caller's current source permissions."""
    out = queries.proposal_detail(ctx, id)
    response.headers["ETag"] = row_etag(out.row_version)
    return out


def _proposal_reject_access(
    id: UUID,
    ctx: Annotated[RequestContext, Depends(require("ai.use"))],
) -> None:
    """Check current source access before command middleware can replay a saved response."""
    queries.proposal_detail(ctx, id)


@router.post(
    "/ai/proposals/{id}/reject",
    operation_id="ai_proposals_reject",
    dependencies=[Depends(_proposal_reject_access)],
    response_model=AIProposalOut | AIExtractionProposalOut,
    responses=problem_responses(
        "unauthenticated",
        "session-expired",
        "forbidden",
        "not-found",
        "validation-failed",
        "invalid-transition",
        "precondition-required",
        "precondition-failed",
        "idempotency-key-reused",
        "idempotency-in-progress",
    ),
)
def proposals_reject(
    id: UUID,
    body: AIProposalRejectIn,
    cmd: Annotated[CommandContext, Depends(command("ai.use", precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Reject retained suggestions with a reason and their current row-version ETag."""

    def handle(uow: UnitOfWork) -> AIProposalOut | AIExtractionProposalOut:
        return commands.reject_proposal(
            uow,
            id,
            reason=body.reason,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle, etag=lambda result: row_etag(result.row_version))


def _extraction_access(
    body: AIContractExtractionIn,
    ctx: Annotated[RequestContext, Depends(require("ai.use"))],
) -> None:
    """Current file access is required even before a saved command response is replayed."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        commands.extraction_file(session, ctx, body.file_id)


@router.post(
    "/ai/contract-extractions",
    operation_id="ai_contract_extractions_create",
    status_code=202,
    response_model=JobOut,
    dependencies=[Depends(_extraction_access)],
    responses=problem_responses(
        "unauthenticated",
        "session-expired",
        "forbidden",
        "not-found",
        "validation-failed",
        "idempotency-key-reused",
        "idempotency-in-progress",
        "ai-disabled",
    ),
)
def contract_extractions_create(
    body: AIContractExtractionIn,
    cmd: Annotated[CommandContext, Depends(command("ai.use"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Queue extraction of a readable PDF using server-selected fields and token limit."""

    def handle(uow: UnitOfWork) -> JobOut:
        job_id = commands.request_extraction(
            uow, file_id=body.file_id, platform_kill_switch=deps.settings.ai_kill_switch
        )
        return job_out_of(uow.session, job_id)

    return run_command(
        cmd, deps, handle, status_code=202, location=lambda result: f"{API_PREFIX}/jobs/{result.id}"
    )


@router.get(
    "/ai/proposals/{id}/document-text",
    operation_id="ai_proposals_document_text",
    response_model=AIDocumentTextOut,
    responses=problem_responses("unauthenticated", "session-expired", "forbidden", "not-found"),
)
def proposals_document_text(
    id: UUID,
    ctx: Annotated[RequestContext, Depends(require("ai.use"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> AIDocumentTextOut:
    """Return audited retained original pages for an authorized extraction proposal."""
    return extraction_reads.document_text(ctx, id, files=deps.files, keyring=deps.keyring)


def _proposal_accept_access(
    id: UUID,
    body: AIExtractionDraftIn,
    ctx: Annotated[RequestContext, Depends(require("ai.use"))],
) -> None:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        acceptance.access(session, ctx, id, body)


@router.post(
    "/ai/proposals/{id}/accept",
    operation_id="ai_proposals_accept",
    status_code=201,
    response_model=AIProposalAcceptedOut,
    dependencies=[Depends(_proposal_accept_access)],
    responses=problem_responses(
        "unauthenticated",
        "session-expired",
        "forbidden",
        "not-found",
        "validation-failed",
        "invalid-transition",
        "precondition-required",
        "precondition-failed",
        "idempotency-key-reused",
        "idempotency-in-progress",
    ),
)
def proposals_accept(
    id: UUID,
    body: AIExtractionDraftIn,
    cmd: Annotated[CommandContext, Depends(command("ai.use", precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a reviewed draft and accept its extraction proposal atomically as the human."""
    return run_command(
        cmd,
        deps,
        lambda uow: acceptance.accept_draft(
            uow, id, body, check_version=lambda actual: assert_version(cmd.expected_version, actual)
        ),
        status_code=201,
        location=lambda out: f"{API_PREFIX}/contracts/{out.contract_id}",
    )


MODEL_LOG_LIST: Final = ListSpec(
    resource="ai-model-logs",
    sort_keys={"id": ai_model_log.c.id, "created_at": ai_model_log.c.created_at},
    default_sort="-created_at",
    filters={},
)


def _model_log_reader(
    request: Request,
    ctx: Annotated[RequestContext, Depends(require_authenticated())],
) -> RequestContext:
    # A scoped settings role cannot expand visibility to the whole workspace.
    permission = "settings.manage" if holds_all(ctx.principal, "settings.manage") else "ai.use"
    return require(permission)(request, ctx)


@router.get(
    "/ai/model-logs",
    operation_id="ai_model_logs_list",
    response_model=ListOut[AIModelLogOut],
    responses=problem_responses(
        "unauthenticated", "session-expired", "forbidden", "mfa-required", "validation-failed"
    ),
)
def model_logs_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(_model_log_reader)],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[AIModelLogOut]:
    """Page call evidence after applying tenant and owner visibility to counts and rows."""
    result, items = queries.list_model_logs(
        ctx,
        page=lambda session, statement: paginate(session, statement, MODEL_LOG_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[AIModelLogOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/ai/model-logs/{id}",
    operation_id="ai_model_logs_get",
    response_model=AIModelLogOut,
    responses=problem_responses(
        "unauthenticated", "session-expired", "forbidden", "mfa-required", "not-found"
    ),
)
def model_logs_get(
    id: UUID,
    ctx: Annotated[RequestContext, Depends(_model_log_reader)],
) -> AIModelLogOut:
    """Read a bookmarked call with exactly the list's current owner/tenant visibility."""
    return queries.model_log_detail(ctx, id)
