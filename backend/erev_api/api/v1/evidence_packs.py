"""API-R-42 CLOSE pack creation and retained reads; list/other kinds remain pending."""

from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Response

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
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.domain.reports import evidence_commands, evidence_queries
from erev_api.problems import Problem
from erev_api.schemas.common import JobOut
from erev_api.schemas.evidence_packs import ClosePackCreateIn, ClosePackOut, EvidencePackCreateIn
from erev_api.uow import UnitOfWork, unit_of_work

router = APIRouter(prefix=API_PREFIX, tags=["API-R-42 Evidence packs"], route_class=GuardedRoute)
Deps = Annotated[KernelDeps, Depends(kernel_deps)]
PROBLEMS = ("unauthenticated", "session-expired", "forbidden", "not-found", "validation-failed")


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
    """Create a first-close pack using a completed verification; replay its original IDs."""
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
