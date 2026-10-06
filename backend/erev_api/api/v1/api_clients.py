"""API-R-08 API clients: OAuth2 client-credentials clients, their secrets and revocation.

04 §15.3 API-R-08, T-PLT-15, T-PLT-16; PRD BR-PLT-06, ERR-24; SCREENS_B §9.15, SB-R-05; BUILD_SPEC
PLF-25. Every route requires ``api_client.manage``.
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
    command,
    kernel_deps,
    problem_responses,
    row_etag,
    run_command,
    withheld,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth import api_clients
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import api_client
from erev_api.domain.platform import setup
from erev_api.enums import ApiClientStatus
from erev_api.schemas.api_clients import (
    ApiClientIn,
    ApiClientOut,
    ApiClientRevokeIn,
    ApiClientSecretOut,
)
from erev_api.schemas.common import ListOut
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-08 API clients"
PERMISSION: Final = "api_client.manage"
# D-80: the stored and replayed body of create and rotate-secret carries the secret as null.
SECRET_MEMBER: Final = "client_secret"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden", "mfa-required")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
CLIENT_LIST: Final = ListSpec(
    resource="api-clients",
    sort_keys={
        "id": api_client.c.id,
        "name": api_client.c.name,
        "created_at": api_client.c.created_at,
    },
    default_sort="created_at",
    filters={
        "status": FilterSpec(
            name="status",
            column=api_client.c.status,
            kind="exact",
            choices=frozenset(status.value for status in ApiClientStatus),
        )
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def client_etag(out: ApiClientOut) -> str:
    """API-C-08: an API client is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _client_location(out: ApiClientOut) -> str:
    return f"{API_PREFIX}/api-clients/{out.id}"


@router.get(
    "/api-clients",
    operation_id="api_clients_list",
    response_model=ListOut[ApiClientOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def api_clients_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[ApiClientStatus | None, Query()] = None,
) -> ListOut[ApiClientOut]:
    """The API clients the caller reaches, never with a secret: a client is listed when the
    caller's ``api_client.manage`` covers every entity it names, and every client for a holder
    of all entities (04 T-PLT-10). Sort ``created_at`` (default), ``name`` or ``id``."""
    result = api_clients.list_api_clients(
        ctx, page=lambda session, statement: paginate(session, statement, CLIENT_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[ApiClientOut](
        items=[ApiClientOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/api-clients",
    operation_id="api_clients_create",
    status_code=201,
    response_model=ApiClientSecretOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "scope-not-allowed", "mfa-step-up-required"),
)
def api_clients_create(
    body: ApiClientIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Request an API client with non-approval scopes. Its scopes are an access grant: the client
    is ``PENDING_APPROVAL`` until another person approves the request named by
    ``approval_request_id``, and ``client_secret`` is null. Only a request approved at once — the
    bootstrap Tenant Admin during setup — answers ``ACTIVE`` with the secret."""

    def handle(uow: UnitOfWork) -> ApiClientSecretOut:
        # The grant is routed as a ROLE_ASSIGNMENT: like a role request it reads the conditions
        # of setup before it is submitted, and where completion is due it is kept from rule
        # AUTO-BOOTSTRAP; the evaluation after it sets the stamp (04 T-PLT-01 rev 1.224).
        due = setup.completion_due(uow)
        issued = api_clients.create_api_client(
            uow,
            name=body.name,
            scopes=body.scopes,
            is_all_entities=body.is_all_entities,
            entity_codes=body.entity_codes,
            expires_at=body.expires_at,
            rate_limit_per_minute=body.rate_limit_per_minute,
            auto_approval=not due,
        )
        setup.evaluate_setup_completion(uow)
        return ApiClientSecretOut.model_validate(
            {**issued.client, "client_secret": issued.client_secret}
        )

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=_client_location,
        etag=client_etag,
        stored_body=withheld(SECRET_MEMBER),
    )


@router.get(
    "/api-clients/{api_client_id}",
    operation_id="api_clients_get",
    response_model=ApiClientOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def api_clients_get(
    api_client_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(PERMISSION))],
) -> ApiClientOut:
    """API-S-ApiClient, never with the secret or its hash. 404 for a client the caller does
    not reach (04 T-PLT-10), as for an id that names no client."""
    out = ApiClientOut.model_validate(api_clients.get_api_client(ctx, api_client_id))
    response.headers["ETag"] = client_etag(out)
    return out


@router.post(
    "/api-clients/{api_client_id}/rotate-secret",
    operation_id="api_clients_rotate_secret",
    response_model=ApiClientSecretOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "mfa-step-up-required"
    ),
)
def api_clients_rotate_secret(
    api_client_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Issue the first secret of an approved client, or replace the secret; it is shown once, and
    tokens issued with the old secret stop working. 409 for a client that is not ``ACTIVE``;
    404 for a client the caller does not reach — the secret is a credential for the client's
    entities (04 T-PLT-10, T-PLT-15)."""

    def handle(uow: UnitOfWork) -> ApiClientSecretOut:
        issued = api_clients.rotate_secret(uow, api_client_id)
        return ApiClientSecretOut.model_validate(
            {**issued.client, "client_secret": issued.client_secret}
        )

    return run_command(cmd, deps, handle, etag=client_etag, stored_body=withheld(SECRET_MEMBER))


@router.post(
    "/api-clients/{api_client_id}/revoke",
    operation_id="api_clients_revoke",
    response_model=ApiClientOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def api_clients_revoke(
    api_client_id: uuid.UUID,
    body: ApiClientRevokeIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Revoke the API client with a reason; its tokens stop working immediately. 404 for a
    client the caller does not reach (04 T-PLT-10)."""

    def handle(uow: UnitOfWork) -> ApiClientOut:
        row = api_clients.revoke_api_client(uow, api_client_id, reason=body.reason)
        return ApiClientOut.model_validate(dict(row))

    return run_command(cmd, deps, handle, etag=client_etag)
