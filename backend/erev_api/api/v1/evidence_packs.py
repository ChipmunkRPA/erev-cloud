"""API-R-42 CLOSE pack creation and retained reads; other kinds remain pending."""

from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

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
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import evidence_pack, legal_entity, period
from erev_api.domain.reports import evidence_commands, evidence_queries
from erev_api.enums import BookCode, RunStatus
from erev_api.problems import Problem
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.evidence_packs import (
    ClosePackCreateIn,
    ClosePackOut,
    ClosePackSummaryOut,
    EvidencePackCreateIn,
)
from erev_api.uow import UnitOfWork, unit_of_work

router = APIRouter(prefix=API_PREFIX, tags=["API-R-42 Evidence packs"], route_class=GuardedRoute)
Deps = Annotated[KernelDeps, Depends(kernel_deps)]
PROBLEMS = ("unauthenticated", "session-expired", "forbidden", "not-found", "validation-failed")

PACK_LIST = ListSpec(
    resource="evidence_packs",
    sort_keys={
        "id": evidence_pack.c.id,
        "created_at": evidence_pack.c.created_at,
        "pack_no": evidence_pack.c.pack_no,
    },
    default_sort="-id",
    filters={
        "entity": FilterSpec("entity", legal_entity.c.code, "in"),
        "book": FilterSpec(
            "book",
            evidence_pack.c.book_code,
            "exact",
            choices=frozenset(value.value for value in BookCode),
        ),
        "period": FilterSpec("period", period.c.period_key, "exact"),
        "kind": FilterSpec("kind", evidence_pack.c.kind, "exact", choices=frozenset({"CLOSE"})),
        "status": FilterSpec(
            "status",
            evidence_pack.c.status,
            "in",
            choices=frozenset(value.value for value in RunStatus),
        ),
    },
)


@router.get(
    "/evidence-packs",
    operation_id="evidence_packs_list",
    response_model=ListOut[ClosePackSummaryOut],
    responses=problem_responses(*PROBLEMS),
)
def evidence_packs_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require("report.run"))],
    deps: Deps,
    params: Annotated[ListParams, Depends(list_params)],
    entity: Annotated[list[str] | None, Query(description="Entity code; repeatable")] = None,
    book: Annotated[BookCode | None, Query()] = None,
    period_key: Annotated[str | None, Query(alias="period", description="Period key")] = None,
    kind: Annotated[Literal["CLOSE"] | None, Query()] = None,
    status: Annotated[list[RunStatus] | None, Query()] = None,
) -> ListOut[ClosePackSummaryOut]:
    """Retained CLOSE register; entity/book/period/kind/status filters, id/created_at/pack_no sorts.

    Counts and pages intersect source permission scopes. Archive verification belongs to the
    individual read/download, not this metadata list. Legacy unbound and other kinds are omitted.
    """
    del entity, book, period_key, kind, status  # validated here; applied through PACK_LIST
    with unit_of_work(ctx, clock=deps.clock, keyring=deps.keyring, files=deps.files) as uow:
        evidence_queries.require_permissions(uow, None, evidence_queries.READ_PERMISSIONS)
        result = paginate(
            uow.session, evidence_queries.list_statement(uow.principal), PACK_LIST, params
        )
        items = [evidence_queries.summary(row) for row in result.items]
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[ClosePackSummaryOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/evidence-packs",
    status_code=202,
    operation_id="evidence_packs_create",
    response_model=JobOut,
    responses=problem_responses(
        *PROBLEMS, "idempotency-key-reused", "idempotency-in-progress", "release-mismatch"
    ),
)
def evidence_packs_create(
    body: EvidencePackCreateIn,
    cmd: Annotated[CommandContext, Depends(command("evidence.export"))],
    deps: Deps,
) -> Response:
    """Create a first-close pack with a dedicated audit job; replay its original IDs."""
    started: dict[str, UUID] = {}

    def handle(uow: UnitOfWork) -> JobOut:
        if not isinstance(body, ClosePackCreateIn):
            raise Problem("validation-failed", "This evidence pack kind is not yet supported.")
        # Supplemental denials are audited just as on the download route.
        evidence_queries.require_permissions(uow, None, evidence_commands.PERMISSIONS)
        pack_id, job = evidence_commands.create_close(uow, body)
        started["pack_id"] = pack_id
        return job

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        extra_headers=lambda job: {
            "Location": f"{API_PREFIX}/jobs/{job.id}",
            "X-Erev-Evidence-Pack-Id": str(started["pack_id"]),
        },
    )


@router.get(
    "/evidence-packs/{pack_id}",
    operation_id="evidence_packs_get",
    response_model=ClosePackOut,
    responses=problem_responses(*PROBLEMS),
)
def evidence_packs_get(
    pack_id: UUID, ctx: Annotated[RequestContext, Depends(require("report.run"))], deps: Deps
) -> ClosePackOut:
    """Read a retained CLOSE header and manifest under current source scope."""
    with unit_of_work(ctx, clock=deps.clock, keyring=deps.keyring, files=deps.files) as uow:
        return evidence_queries.get_close(uow, pack_id)


@router.get(
    "/evidence-packs/{pack_id}/download",
    operation_id="evidence_packs_download",
    response_class=Response,
    responses={
        200: {"content": {"application/zip": {}}, "description": "Verified evidence ZIP"},
        **problem_responses(*PROBLEMS, "invalid-transition"),
    },
)
def evidence_packs_download(
    pack_id: UUID, ctx: Annotated[RequestContext, Depends(require("evidence.export"))], deps: Deps
) -> Response:
    """Reauthorize and verify retained bytes, committing one export audit before serving them."""
    with unit_of_work(ctx, clock=deps.clock, keyring=deps.keyring, files=deps.files) as uow:
        filename, content = evidence_queries.download_close(uow, pack_id)
        uow.commit()
    return Response(
        content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
            "Content-Security-Policy": "sandbox",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
