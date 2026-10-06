"""API-R-45 Integrations (04 §15.3 API-R-45; §16.14 ``last_sync_run`` / ``duration_seconds``;
T-INT-01, T-INT-02, T-INT-04; 05 ADP-01, ADP-14; PRD J-23.1, J-23.4, J-23-AC-1, BR-INT-01; SCREENS
SF-16; BUILD_SPEC DIN-12).

``GET, POST /integrations``; ``GET, PATCH /integrations/{id}`` (If-Match); ``POST
/integrations/{id}/test`` (synchronous probe); ``POST /integrations/{id}/sync`` (202 API-S-Job with
``X-Erev-Sync-Run-Id``, the evidence-pack header precedent); ``GET /sync-runs`` (filter
``connection``, ``status``, ``kind``); ``GET /sync-runs/{id}``; ``GET /external-ids`` (filter
``connection``, ``object_type``); every one under ``integration.manage``. Connection responses carry
``secret_ref`` — the reference name — and never a secret value (J-23-AC-1; REQ-INT-006).

A connection serves entities, and a caller reaches it when its scope of the route's permission
covers every one of them (``queries.in_reach``; 04 API-C-03 rev 1.243): the lists hold the
connections in reach with their runs and external ids, and a connection or a run out of reach is
404 to a read and to a command.

``POST /webhooks/{adapter}/{connection_id}`` is the ADP-01 receiver on the API-C-01 allow-list
(``PUBLIC_PATHS``): ``connection_id`` is the receiver id ``erevw_<tenant hex>_<connection hex>``
(``commands.parse_receiver_id``; pending team-lead's Q-A ruling on its name), which names the tenant
session to open; the connection must be ACTIVE and of ``{adapter}``; its ``secret_ref`` resolves
through the key ring and the adapter verifies the signature over the raw body; then one unit of work
stores the ``WEBHOOK_BATCH`` sync run and defers ``SYNC_RUN``. Every refusal is one 401
``unauthenticated`` with the same detail (the reason is logged, never the secret), so the route is
no enumeration oracle; the answer is 202 well inside ADP-01's two seconds because nothing is fetched
here.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Annotated, Any, Final, get_args

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

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
    ListResult,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.clock import Clock, get_clock
from erev_api.config import LOCAL_ENVIRONMENTS
from erev_api.db.session import tenant_session
from erev_api.db.tables import external_id_map, integration_connection, sync_run, tenant
from erev_api.domain.integrations import commands, ports, queries
from erev_api.domain.integrations import sync as sync_module
from erev_api.enums import SyncRunStatus, TenantKind
from erev_api.logging import get_logger
from erev_api.problems import Problem
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.integrations import (
    Adapter,
    ConnectionStatus,
    ExternalIdMapIn,
    ExternalIdMapOut,
    ExternalObjectType,
    IntegrationConnectionIn,
    IntegrationConnectionOut,
    IntegrationConnectionUpdateIn,
    SyncRequestIn,
    SyncRunKind,
    SyncRunOut,
    WebhookAcceptedOut,
)
from erev_api.uow import UnitOfWork, unit_of_work

TAG: Final = "API-R-45 Integrations"
PERMISSION: Final = commands.MANAGE_PERMISSION
MAINTAIN_PERMISSION: Final = commands.MAINTAIN_PERMISSION  # POST /external-ids (04 rev 1.81)
JOB_PATH: Final = f"{API_PREFIX}/jobs/{{job_id}}"
SYNC_RUN_ID_HEADER: Final = "X-Erev-Sync-Run-Id"
WEBHOOK_PATH: Final = "/webhooks/{adapter}/{connection_id}"
WEBHOOK_REFUSED: Final = "The webhook was not accepted."
_LOGGER: Final = "erev_api.api.integrations"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden", "mfa-required")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)

CONNECTION_LIST: Final = ListSpec(
    resource="integrations",
    sort_keys={
        "id": integration_connection.c.id,
        "code": integration_connection.c.code,
        "name": integration_connection.c.name,
        "created_at": integration_connection.c.created_at,
    },
    default_sort="code",
    filters={
        "adapter": FilterSpec(
            name="adapter",
            column=integration_connection.c.adapter,
            kind="exact",
            choices=frozenset(get_args(Adapter)),
        ),
        "status": FilterSpec(
            name="status",
            column=integration_connection.c.status,
            kind="exact",
            choices=frozenset(get_args(ConnectionStatus)),
        ),
    },
)
SYNC_RUN_LIST: Final = ListSpec(
    resource="sync-runs",
    sort_keys={
        "id": sync_run.c.id,
        "created_at": sync_run.c.created_at,
        "finished_at": sync_run.c.finished_at,
    },
    default_sort="-created_at",
    filters={
        "connection": FilterSpec(
            name="connection", column=sync_run.c.integration_connection_id, kind="exact"
        ),
        "status": FilterSpec(
            name="status",
            column=sync_run.c.status,
            kind="in",
            choices=frozenset(status.value for status in SyncRunStatus),
        ),
        "kind": FilterSpec(
            name="kind",
            column=sync_run.c.kind,
            kind="exact",
            choices=frozenset(get_args(SyncRunKind)),
        ),
    },
)
EXTERNAL_ID_LIST: Final = ListSpec(
    resource="external-ids",
    sort_keys={
        "id": external_id_map.c.id,
        "created_at": external_id_map.c.created_at,
        "external_id": external_id_map.c.external_id,
    },
    default_sort="-created_at",
    filters={
        "connection": FilterSpec(
            name="connection", column=external_id_map.c.integration_connection_id, kind="exact"
        ),
        "object_type": FilterSpec(
            name="object_type",
            column=external_id_map.c.object_type,
            kind="exact",
            choices=frozenset(get_args(ExternalObjectType)),
        ),
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)

type ReadContext = Annotated[RequestContext, Depends(require(PERMISSION))]
type Deps = Annotated[KernelDeps, Depends(kernel_deps)]


def _local(deps: KernelDeps) -> bool:
    """Whether the deployment admits the in-process mock URLs as a connection's ``base_url``:
    ``dev``, ``test`` and ``e2e`` only (05 SAR-15; 04 T-INT-01 rev 1.115)."""
    return deps.settings.env in LOCAL_ENVIRONMENTS


def connection_etag(out: IntegrationConnectionOut) -> str:
    return row_etag(out.row_version)


def _connection_location(out: IntegrationConnectionOut) -> str:
    return f"{API_PREFIX}/integrations/{out.id}"


def _connection(row: Mapping[str, Any]) -> IntegrationConnectionOut:
    return IntegrationConnectionOut.model_validate(row)


# --- connections ----------------------------------------------------------------------------------


@router.get(
    "/integrations",
    operation_id="integrations_list",
    response_model=ListOut[IntegrationConnectionOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def integrations_list(
    response: Response,
    ctx: ReadContext,
    params: Annotated[ListParams, Depends(list_params)],
    adapter: Annotated[Adapter | None, Query()] = None,
    status: Annotated[ConnectionStatus | None, Query()] = None,
) -> ListOut[IntegrationConnectionOut]:
    """The connections in the caller's reach with their newest sync run; sort ``code`` (default),
    ``name``, ``created_at`` or ``id``; filters ``adapter`` and ``status``."""

    def fn(session: Session) -> tuple[ListResult, dict[uuid.UUID, Mapping[str, Any]]]:
        statement = queries.connection_statement(ctx.principal, PERMISSION)
        result = paginate(session, statement, CONNECTION_LIST, params)
        latest = queries.latest_sync_runs(session, [item["id"] for item in result.items])
        return result, latest

    result, latest = queries.read(ctx, fn)
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[IntegrationConnectionOut](
        items=[
            _connection(queries.connection_out(item, latest.get(uuid.UUID(str(item["id"])))))
            for item in result.items
        ],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/integrations",
    operation_id="integrations_create",
    status_code=201,
    response_model=IntegrationConnectionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "mfa-step-up-required", "sandbox-restricted"),
)
def integrations_create(
    body: IntegrationConnectionIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Deps,
) -> Response:
    """Create a DISABLED connection; ``secret_ref`` names a secret of the workspace's own
    namespace of the secret store and is stored as given. ``entity_ids`` names entities of the
    caller's own scope; the empty list, every entity, is for a holder of all entities."""
    return run_command(
        cmd,
        deps,
        lambda uow: _connection(
            commands.create_connection(uow, body, local_destinations=_local(deps))
        ),
        status_code=201,
        location=_connection_location,
        etag=connection_etag,
    )


@router.get(
    "/integrations/{connection_id}",
    operation_id="integrations_get",
    response_model=IntegrationConnectionOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def integrations_get(
    connection_id: uuid.UUID, response: Response, ctx: ReadContext
) -> IntegrationConnectionOut:
    """API-S-IntegrationConnection with ``last_sync_run`` (04 §16.14)."""
    out = _connection(queries.get_connection(ctx, PERMISSION, connection_id))
    response.headers["ETag"] = connection_etag(out)
    return out


@router.patch(
    "/integrations/{connection_id}",
    operation_id="integrations_update",
    response_model=IntegrationConnectionOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "not-found",
        "precondition-failed",
        "precondition-required",
        "sandbox-restricted",
    ),
)
def integrations_update(
    connection_id: uuid.UUID,
    body: IntegrationConnectionUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, precondition="row"))],
    deps: Deps,
) -> Response:
    """Change the name, entities, URL, settings, secret reference or status (If-Match); DB-15
    refuses an ACTIVE outbound GL adapter other than CSV_GL in a sandbox tenant."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> IntegrationConnectionOut:
        return _connection(
            commands.update_connection(
                uow,
                connection_id,
                changes,
                check_version=lambda actual: assert_version(cmd.expected_version, actual),
                local_destinations=_local(deps),
            )
        )

    return run_command(cmd, deps, handle, etag=connection_etag)


@router.post(
    "/integrations/{connection_id}/test",
    operation_id="integrations_test",
    response_model=IntegrationConnectionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found"),
)
def integrations_test(
    connection_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Deps,
) -> Response:
    """Probe the source through the adapter and the secret store; records ``last_test_at`` (UTC),
    ``last_test_result`` and ``last_test_detail`` and a ``TEST_CONNECTION`` sync run (BR-INT-01)."""
    return run_command(
        cmd,
        deps,
        lambda uow: _connection(commands.test_connection(uow, connection_id)),
        etag=connection_etag,
    )


@router.post(
    "/integrations/{connection_id}/sync",
    operation_id="integrations_sync",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "sandbox-restricted"
    ),
)
def integrations_sync(
    connection_id: uuid.UUID,
    body: SyncRequestIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Deps,
) -> Response:
    """Queue a sync run of ``kind`` (default ``INBOUND_POLL``) and its ``SYNC_RUN`` job (202
    API-S-Job; ``Location`` the job, ``X-Erev-Sync-Run-Id`` the run)."""
    # Imported here: the platform job reads are the 202 body of every job command.
    from erev_api.domain.platform.jobs import job_out_of

    run_ids: dict[str, str] = {}

    def handle(uow: UnitOfWork) -> JobOut:
        requested = commands.request_sync(uow, connection_id, kind=body.kind)
        run_ids["id"] = str(requested.run_id)
        return job_out_of(uow.session, requested.job_id)

    def headers(job: JobOut) -> dict[str, str]:
        return {"Location": JOB_PATH.format(job_id=job.id), SYNC_RUN_ID_HEADER: run_ids["id"]}

    return run_command(cmd, deps, handle, status_code=202, extra_headers=headers)


# --- sync runs and external ids -------------------------------------------------------------------


@router.get(
    "/sync-runs",
    operation_id="sync_runs_list",
    response_model=ListOut[SyncRunOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def sync_runs_list(
    response: Response,
    ctx: ReadContext,
    params: Annotated[ListParams, Depends(list_params)],
    connection: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[SyncRunStatus | None, Query()] = None,
    kind: Annotated[SyncRunKind | None, Query()] = None,
) -> ListOut[SyncRunOut]:
    """The interface runs of the connections in the caller's reach, newest first; filters
    ``connection``, ``status`` (several) and ``kind`` (J-23-AC-3: source and loaded control totals
    on every run)."""
    statement = queries.sync_run_statement(ctx.principal, PERMISSION)
    result = queries.read(ctx, lambda session: paginate(session, statement, SYNC_RUN_LIST, params))
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[SyncRunOut](
        items=[SyncRunOut.model_validate(queries.sync_run_out(item)) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.get(
    "/sync-runs/{sync_run_id}",
    operation_id="sync_runs_get",
    response_model=SyncRunOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def sync_runs_get(sync_run_id: uuid.UUID, response: Response, ctx: ReadContext) -> SyncRunOut:
    """API-S-SyncRun with ``duration_seconds`` (04 §16.14)."""
    out = SyncRunOut.model_validate(queries.get_sync_run(ctx, PERMISSION, sync_run_id))
    response.headers["ETag"] = row_etag(out.row_version)
    return out


@router.get(
    "/external-ids",
    operation_id="external_ids_list",
    response_model=ListOut[ExternalIdMapOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def external_ids_list(
    response: Response,
    ctx: ReadContext,
    params: Annotated[ListParams, Depends(list_params)],
    connection: Annotated[uuid.UUID | None, Query()] = None,
    object_type: Annotated[ExternalObjectType | None, Query()] = None,
) -> ListOut[ExternalIdMapOut]:
    """T-INT-04 links of the connections in the caller's reach, newest first; filters
    ``connection`` and ``object_type`` (SCREENS R-40)."""
    statement = queries.external_id_statement(ctx.principal, PERMISSION)
    result = queries.read(
        ctx, lambda session: paginate(session, statement, EXTERNAL_ID_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[ExternalIdMapOut](
        items=[
            ExternalIdMapOut.model_validate(queries.external_id_out(item)) for item in result.items
        ],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/external-ids",
    operation_id="external_ids_create",
    status_code=201,
    response_model=ExternalIdMapOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found"),
)
def external_ids_create(
    body: ExternalIdMapIn,
    cmd: Annotated[CommandContext, Depends(command(MAINTAIN_PERMISSION))],
    deps: Deps,
) -> Response:
    """Link an external id to a product, customer, contract or other record under a connection in
    the caller's reach (04 §16.14 rev 1.81; the alias J-23.5 adds before "Reprocess"); a
    superseded live link is closed."""
    return run_command(
        cmd,
        deps,
        lambda uow: ExternalIdMapOut.model_validate(commands.create_external_id(uow, body)),
        status_code=201,
    )


# --- the webhook receiver (ADP-01) ----------------------------------------------------------------


def _refused(reason: str, **fields: Any) -> Problem:
    """One 401 for every refusal; the reason is logged and never answered (no enumeration oracle;
    the secret is never part of it)."""
    get_logger(_LOGGER).info("webhook.refused", reason=reason, **fields)
    return Problem("unauthenticated", WEBHOOK_REFUSED)


def receive_webhook(
    *,
    adapter: str,
    receiver: str,
    headers: Mapping[str, str],
    body: bytes,
    request_id: str,
    clock: Clock,
    deps: KernelDeps,
) -> WebhookAcceptedOut:
    """The receiver's synchronous work (run in the threadpool): resolve, verify, record, defer."""
    parsed = commands.parse_receiver_id(receiver)
    if parsed is None:
        raise _refused("receiver id malformed")
    tenant_id, connection_id = parsed
    principal = system_principal(tenant_id)
    with tenant_session(principal.db_context, read_only=True) as session:
        kind = session.execute(
            select(tenant.c.kind).where(tenant.c.id == tenant_id)
        ).scalar_one_or_none()
        row = (
            session.execute(
                select(integration_connection).where(integration_connection.c.id == connection_id)
            )
            .mappings()
            .one_or_none()
        )
        tenant_code = None if kind is None else sync_module.tenant_code_of(session, tenant_id)
    if kind is None or row is None or tenant_code is None:
        raise _refused("connection unknown")
    if TenantKind(str(kind)) is TenantKind.SANDBOX:
        # 05 SBX-08: no inbound work for a sandbox; the same 401 as every other refusal (no oracle),
        # the domain command refuses again behind it (defense in depth).
        raise _refused("sandbox tenant", connection_id=str(connection_id))
    connection = dict(row)
    if str(connection["status"]) != "ACTIVE":
        raise _refused("connection not ACTIVE", connection_id=str(connection_id))
    if str(connection["adapter"]).upper() != adapter.upper():
        raise _refused("adapter mismatch", connection_id=str(connection_id))
    secret_ref = connection.get("secret_ref")
    if not secret_ref:
        raise _refused("connection has no secret_ref", connection_id=str(connection_id))
    try:
        # One refusal on both providers (``KeyRing.adapter_secret``): absent, refused by name, not
        # pinned or denied under the hosted store — never a 500 for a reference a tenant typed.
        secret = deps.keyring.adapter_secret(str(secret_ref), tenant_id=tenant_id)
    except KeyError:
        raise _refused("secret_ref not resolvable", connection_id=str(connection_id)) from None
    try:
        # The application clock is the adapter's ``now``: where the scheme signs a timestamp, the
        # adapter refuses a notification outside the replay window (05 ADP-01 rev 1.47).
        inbound = sync_module.adapter_for(
            connection, tenant_code=tenant_code, client=object(), clock=clock
        )
    except (LookupError, ValueError, ports.Permanent) as error:
        raise _refused(f"adapter unavailable: {type(error).__name__}") from None
    notice = inbound.verify_webhook(headers, body, SecretStr(secret))
    del secret
    if not notice.verified:
        raise _refused(f"signature: {notice.reason}", connection_id=str(connection_id))
    ctx = RequestContext(
        principal=principal,
        tenant_kind=TenantKind(str(kind)),
        request_id=request_id,
        source_ip=None,
        user_agent=headers.get("user-agent"),
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    with unit_of_work(ctx, clock=clock, keyring=deps.keyring, files=deps.files) as uow:
        requested = commands.receive_webhook(uow, connection, notice)
        uow.commit()
    return WebhookAcceptedOut(
        sync_run_id=requested.run_id,
        job_id=requested.job_id,
        notifications=len(notice.notifications),
        received_at=ctx.now,
    )


@router.post(
    WEBHOOK_PATH,
    operation_id="webhooks_receive",
    status_code=202,
    response_model=WebhookAcceptedOut,
    responses=problem_responses("unauthenticated"),
)
async def webhooks_receive(
    adapter: str,
    connection_id: str,
    request: Request,
    clock: Annotated[Clock, Depends(get_clock)],
    deps: Deps,
) -> WebhookAcceptedOut:
    """ADP-01: verify the signature, store a ``WEBHOOK_BATCH`` sync run with the notification ids
    and defer ``SYNC_RUN``; unauthenticated, signature-verified, 202 within two seconds."""
    body = await request.body()
    request_id = str(getattr(request.state, "request_id", "") or f"webhook-{uuid.uuid4()}")
    return await run_in_threadpool(
        receive_webhook,
        adapter=adapter,
        receiver=connection_id,
        headers=dict(request.headers),
        body=body,
        request_id=request_id,
        clock=clock,
        deps=deps,
    )
