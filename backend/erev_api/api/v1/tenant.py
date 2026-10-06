"""API-R-04 Tenant: the active workspace's settings and its snapshots.

04 §15.3 API-R-04, T-PLT-01, T-PLT-34, DB-05, API-C-08; SCREENS_B SF-23 data bindings; PRD ERR-26,
ACT-50; BUILD_SPEC PLF-21, SNP-1 (slice I-4; lane record §13.2.10). The settings routes need
``settings.manage`` (``PATCH /tenant`` needs ``If-Match``); the snapshot routes need
``tenant.snapshot`` (MFA) and the request a fresh TOTP step-up; ``POST /tenant/reset`` needs
``sandbox.reset`` (MFA) and a step-up (BUILD_SPEC SNP-3). The routes import the domain modules
``snapshots`` and ``sandbox_reset``, never a job handler (DG-ARC-08). Every route asks its
permission for all entities: the settings, a snapshot, a sandbox and a reset are the workspace's,
not an entity's (04 API-C-03 rev 1.219; supervisor rulings R-28 and R-115 (c); item
SCOPE-WORKSPACE-LISTS-1).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Response

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    assert_version,
    command,
    header_responses,
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
from erev_api.auth.dependencies import require_all_entities
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import tenant_snapshot
from erev_api.domain.platform import sandbox_reset, sandboxes, snapshots, tenant_settings
from erev_api.domain.platform.snapshot_dataset import PURPOSES
from erev_api.enums import RunStatus
from erev_api.schemas.common import ListOut
from erev_api.schemas.tenant import (
    SnapshotPurpose,
    TenantOut,
    TenantResetIn,
    TenantResetRequestedOut,
    TenantSandboxRequestedOut,
    TenantSandboxRequestIn,
    TenantSnapshotOut,
    TenantSnapshotRequestedOut,
    TenantSnapshotRequestIn,
    TenantUpdateIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-04 Tenant"
PERMISSION: Final = "settings.manage"
SNAPSHOT_PERMISSION: Final = "tenant.snapshot"
RESET_PERMISSION: Final = "sandbox.reset"
MANIFEST_MEDIA_TYPE: Final = "application/json"
SNAPSHOT_LIST: Final = ListSpec(
    resource="tenant-snapshots",
    sort_keys={
        "id": tenant_snapshot.c.id,
        "created_at": tenant_snapshot.c.created_at,
        "known_at": tenant_snapshot.c.known_at,
    },
    default_sort="-created_at",
    filters={
        "status": FilterSpec(
            name="status",
            column=tenant_snapshot.c.status,
            kind="exact",
            choices=frozenset(status.value for status in RunStatus),
        ),
        "purpose": FilterSpec(
            name="purpose",
            column=tenant_snapshot.c.purpose,
            kind="exact",
            choices=frozenset(PURPOSES),
        ),
    },
)
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden", "mfa-required")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def tenant_etag(out: TenantOut) -> str:
    """API-C-08: the tenant is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


@router.get(
    "/tenant",
    operation_id="tenant_get",
    response_model=TenantOut,
    responses={
        **header_responses(200, "ETag", description="API-S-Tenant with its ETag"),
        **problem_responses(*_READ_PROBLEMS),
    },
)
def tenant_get(
    response: Response, ctx: Annotated[RequestContext, Depends(require_all_entities(PERMISSION))]
) -> TenantOut:
    """API-S-Tenant of the active workspace."""
    out = TenantOut.model_validate(dict(tenant_settings.get_tenant(ctx)))
    response.headers["ETag"] = tenant_etag(out)
    return out


@router.patch(
    "/tenant",
    operation_id="tenant_update",
    response_model=TenantOut,
    responses={
        **header_responses(200, "ETag", description="The updated API-S-Tenant with its ETag"),
        **problem_responses(
            *_COMMAND_PROBLEMS,
            "precondition-failed",
            "precondition-required",
            "tenant-kind-immutable",
        ),
    },
)
def tenant_update(
    body: TenantUpdateIn,
    cmd: Annotated[
        CommandContext, Depends(command(PERMISSION, precondition="row", all_entities=True))
    ],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Rename the workspace or change its default locale; the workspace type never changes."""
    sent = body.model_fields_set
    changes = {name: getattr(body, name) for name in sent if name != "kind"}

    def handle(uow: UnitOfWork) -> TenantOut:
        row = tenant_settings.update_tenant(
            uow,
            changes=changes,
            kind_requested="kind" in sent,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return TenantOut.model_validate(dict(row))

    return run_command(cmd, deps, handle, etag=tenant_etag)


@router.post(
    "/tenant/snapshots",
    status_code=202,
    operation_id="tenant_snapshots_request",
    response_model=TenantSnapshotRequestedOut,
    responses={
        **header_responses(
            202,
            "Location",
            "X-Erev-Tenant-Snapshot-Id",
            description="Accepted: the TENANT_SNAPSHOT job and the T-PLT-34 row it fills",
        ),
        **problem_responses(*_COMMAND_PROBLEMS, "mfa-step-up-required", "sandbox-restricted"),
    },
)
def tenant_snapshots_request(
    body: TenantSnapshotRequestIn,
    cmd: Annotated[CommandContext, Depends(command(SNAPSHOT_PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Take a snapshot of this production workspace as of ``known_at`` (REQ-PLT-023; 05 SBX-02,
    SBX-03): 202 with the job, ``Location: /api/v1/jobs/{id}`` and ``X-Erev-Tenant-Snapshot-Id``.
    Needs a TOTP verification inside the step-up window (PRD ACT-50)."""

    def handle(uow: UnitOfWork) -> TenantSnapshotRequestedOut:
        row, job = snapshots.request_snapshot(
            uow, known_at=body.known_at, purpose=body.purpose, sandbox_name=body.name
        )
        return TenantSnapshotRequestedOut.model_validate(
            {**job.model_dump(), "tenant_snapshot_id": row["id"]}
        )

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        location=lambda out: f"{API_PREFIX}/jobs/{out.id}",
        extra_headers=lambda out: {snapshots.SNAPSHOT_ID_HEADER: str(out.tenant_snapshot_id)},
    )


@router.post(
    "/tenant/sandboxes",
    status_code=202,
    operation_id="tenant_sandboxes_request",
    response_model=TenantSandboxRequestedOut,
    responses={
        **header_responses(
            202,
            "Location",
            sandboxes.SANDBOX_ID_HEADER,
            description="Accepted: the load-only TENANT_SNAPSHOT job and the new sandbox tenant",
        ),
        **problem_responses(
            *_COMMAND_PROBLEMS,
            "mfa-step-up-required",
            "sandbox-restricted",
            "forbidden",
            "not-found",
            "precondition-failed",
        ),
    },
)
def tenant_sandboxes_request(
    body: TenantSandboxRequestIn,
    cmd: Annotated[CommandContext, Depends(command(SNAPSHOT_PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Restore a stored snapshot of this production workspace into a NEW sandbox (REQ-PLT-024;
    05 SBX-02, SBX-04; 04 rev 1.67): 202 with the load-only ``TENANT_SNAPSHOT`` job (API-S-Job
    ``mode = "restore"``), ``Location: /api/v1/jobs/{id}`` and ``X-Erev-Sandbox-Tenant-Id``.
    Refusals by rule id ride existing slugs: ``SNAPSHOT_NOT_LOADABLE`` (412),
    ``SANDBOX_ACTOR_REQUIRED`` (403), ``SANDBOX_NAME_TAKEN`` (422 on ``name``). Needs a TOTP
    verification inside the step-up window (PRD ACT-50)."""

    def handle(uow: UnitOfWork) -> TenantSandboxRequestedOut:
        sandbox_tenant_id, job = snapshots.request_sandbox(
            uow, tenant_snapshot_id=body.tenant_snapshot_id, name=body.name
        )
        return TenantSandboxRequestedOut.model_validate(
            {**job.model_dump(), "sandbox_tenant_id": sandbox_tenant_id}
        )

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        location=lambda out: f"{API_PREFIX}/jobs/{out.id}",
        extra_headers=lambda out: {sandboxes.SANDBOX_ID_HEADER: str(out.sandbox_tenant_id)},
    )


@router.post(
    "/tenant/reset",
    status_code=202,
    operation_id="tenant_reset_request",
    response_model=TenantResetRequestedOut,
    responses={
        **header_responses(
            202,
            "Location",
            sandboxes.SANDBOX_ID_HEADER,
            description="Accepted: the SANDBOX_RESET job and the successor sandbox tenant",
        ),
        **problem_responses(
            *_COMMAND_PROBLEMS,
            "mfa-step-up-required",
            "production-reset-forbidden",
            "invalid-transition",
        ),
    },
)
def tenant_reset_request(
    body: TenantResetIn,
    cmd: Annotated[CommandContext, Depends(command(RESET_PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Reset this sandbox by supersession (REQ-PLT-025; 05 SBX-07; 04 rev 1.125): a successor
    sandbox from the seed snapshot (``mode = "SNAPSHOT"``) or empty (``"EMPTY"``) replaces it, this
    one is archived and nothing is deleted. 202 with the ``SANDBOX_RESET`` job,
    ``Location: /api/v1/jobs/{id}`` and ``X-Erev-Sandbox-Tenant-Id``. A production workspace
    answers 409 ``production-reset-forbidden`` (PRD ERR-25); a second reset while one is queued or
    running 409 ``invalid-transition``; a snapshot that is not the seed 422
    ``SANDBOX_SEED_REQUIRED``. Needs a TOTP verification inside the step-up window (PRD ACT-51)."""

    def handle(uow: UnitOfWork) -> TenantResetRequestedOut:
        successor_id, job = sandbox_reset.request_reset(
            uow,
            mode=body.mode,
            tenant_snapshot_id=body.tenant_snapshot_id,
            reason=body.reason,
        )
        return TenantResetRequestedOut.model_validate(
            {**job.model_dump(), "sandbox_tenant_id": successor_id}
        )

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        location=lambda out: f"{API_PREFIX}/jobs/{out.id}",
        extra_headers=lambda out: {sandboxes.SANDBOX_ID_HEADER: str(out.sandbox_tenant_id)},
    )


@router.get(
    "/tenant/snapshots",
    operation_id="tenant_snapshots_list",
    response_model=ListOut[TenantSnapshotOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def tenant_snapshots_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities(SNAPSHOT_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[RunStatus | None, Query()] = None,
    purpose: Annotated[SnapshotPurpose | None, Query()] = None,
) -> ListOut[TenantSnapshotOut]:
    """The workspace's snapshots; sort ``created_at`` (default, newest first), ``known_at`` or
    ``id``; filters ``status`` and ``purpose``."""
    result = snapshots.list_snapshots(
        ctx, page=lambda session, statement: paginate(session, statement, SNAPSHOT_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[TenantSnapshotOut](
        items=[
            TenantSnapshotOut.model_validate(snapshots.snapshot_out(item)) for item in result.items
        ],
        next_cursor=result.next_cursor,
    )


@router.get(
    "/tenant/snapshots/{tenant_snapshot_id}",
    operation_id="tenant_snapshots_get",
    response_model=TenantSnapshotOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def tenant_snapshots_get(
    tenant_snapshot_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require_all_entities(SNAPSHOT_PERMISSION))],
) -> TenantSnapshotOut:
    """One snapshot's status, counts and manifest digest."""
    return TenantSnapshotOut.model_validate(dict(snapshots.get_snapshot(ctx, tenant_snapshot_id)))


@router.get(
    "/tenant/snapshots/{tenant_snapshot_id}/manifest",
    operation_id="tenant_snapshots_manifest",
    response_class=Response,
    responses={
        200: {
            "content": {MANIFEST_MEDIA_TYPE: {}},
            **header_responses(
                200,
                "ETag",
                description="The stored manifest bytes; their SHA-256 is the row's manifest_sha256",
            )[200],
        },
        **problem_responses(*_READ_PROBLEMS, "not-found"),
    },
)
def tenant_snapshots_manifest(
    tenant_snapshot_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require_all_entities(SNAPSHOT_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """The manifest of a SUCCEEDED snapshot, verbatim (T-PLT-34); 404 until it exists."""
    row, content = snapshots.manifest_content(
        ctx, tenant_snapshot_id, files=deps.files, keyring=deps.keyring
    )
    return Response(
        content=content,
        media_type=MANIFEST_MEDIA_TYPE,
        headers={"ETag": f'"{row["manifest_sha256"]}"'},
    )
