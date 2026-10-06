"""API-R-15 Webhooks: endpoint subscriptions and the delivery log.

04 §15.3 API-R-15, T-PLT-35, T-PLT-36, API-C-08; 05 NTR-10 to NTR-13; BUILD_SPEC PLF-24. Every
route requires ``webhook.manage`` for all entities: an endpoint receives the events of the whole
workspace, and a delivery carries any entity's payload (04 API-C-03 rev 1.219; supervisor rulings
R-28 and R-115 (c); item SCOPE-WORKSPACE-LISTS-1).
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
from erev_api.auth.dependencies import require_all_entities
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import webhook_delivery, webhook_endpoint
from erev_api.domain.platform import webhook_endpoints
from erev_api.enums import WebhookDeliveryStatus
from erev_api.schemas.common import ListOut
from erev_api.schemas.webhooks import (
    WebhookDeliveryOut,
    WebhookEndpointCreatedOut,
    WebhookEndpointIn,
    WebhookEndpointOut,
    WebhookEndpointUpdateIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-15 Webhooks"
PERMISSION: Final = "webhook.manage"
# D-80: the stored and replayed body of create carries the signing secret as null.
SECRET_MEMBER: Final = "signing_secret"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
ENDPOINT_LIST: Final = ListSpec(
    resource="webhook-endpoints",
    sort_keys={
        "id": webhook_endpoint.c.id,
        "url": webhook_endpoint.c.url,
        "created_at": webhook_endpoint.c.created_at,
    },
    default_sort="created_at",
    filters={
        "is_active": FilterSpec(name="is_active", column=webhook_endpoint.c.is_active, kind="bool")
    },
)
DELIVERY_LIST: Final = ListSpec(
    resource="webhook-deliveries",
    sort_keys={"id": webhook_delivery.c.id, "created_at": webhook_delivery.c.created_at},
    default_sort="-created_at",
    filters={
        "status": FilterSpec(
            name="status",
            column=webhook_delivery.c.status,
            kind="exact",
            choices=frozenset(status.value for status in WebhookDeliveryStatus),
        ),
        "webhook_endpoint_id": FilterSpec(
            name="webhook_endpoint_id", column=webhook_delivery.c.webhook_endpoint_id, kind="exact"
        ),
        "event_kind": FilterSpec(
            name="event_kind", column=webhook_delivery.c.event_kind, kind="exact"
        ),
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def endpoint_etag(out: WebhookEndpointOut) -> str:
    """API-C-08: an endpoint is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _endpoint_location(out: WebhookEndpointOut) -> str:
    return f"{API_PREFIX}/webhook-endpoints/{out.id}"


@router.get(
    "/webhook-endpoints",
    operation_id="webhook_endpoints_list",
    response_model=ListOut[WebhookEndpointOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def webhook_endpoints_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities(PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    is_active: Annotated[bool | None, Query()] = None,
) -> ListOut[WebhookEndpointOut]:
    """The workspace's endpoints; sort ``created_at`` (default), ``url`` or ``id``."""
    result = webhook_endpoints.list_endpoints(
        ctx, page=lambda session, statement: paginate(session, statement, ENDPOINT_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[WebhookEndpointOut](
        items=[WebhookEndpointOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/webhook-endpoints",
    operation_id="webhook_endpoints_create",
    status_code=201,
    response_model=WebhookEndpointCreatedOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "sandbox-restricted"),
)
def webhook_endpoints_create(
    body: WebhookEndpointIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Subscribe a URL to event kinds; the response carries the signing secret once. A sandbox
    answers 403 ``sandbox-restricted`` (05 SBX-08): an endpoint is created active."""

    def handle(uow: UnitOfWork) -> WebhookEndpointCreatedOut:
        created = webhook_endpoints.create_endpoint(
            uow, url=body.url, description=body.description, event_kinds=body.event_kinds
        )
        return WebhookEndpointCreatedOut.model_validate(
            {**created.endpoint, "signing_secret": created.signing_secret}
        )

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=_endpoint_location,
        etag=endpoint_etag,
        stored_body=withheld(SECRET_MEMBER),
    )


@router.get(
    "/webhook-endpoints/{endpoint_id}",
    operation_id="webhook_endpoints_get",
    response_model=WebhookEndpointOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def webhook_endpoints_get(
    endpoint_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities(PERMISSION))],
) -> WebhookEndpointOut:
    """API-S-WebhookEndpoint, never with the signing secret."""
    out = WebhookEndpointOut.model_validate(webhook_endpoints.get_endpoint(ctx, endpoint_id))
    response.headers["ETag"] = endpoint_etag(out)
    return out


@router.patch(
    "/webhook-endpoints/{endpoint_id}",
    operation_id="webhook_endpoints_update",
    response_model=WebhookEndpointOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "not-found",
        "precondition-failed",
        "precondition-required",
        "sandbox-restricted",
    ),
)
def webhook_endpoints_update(
    endpoint_id: uuid.UUID,
    body: WebhookEndpointUpdateIn,
    cmd: Annotated[
        CommandContext, Depends(command(PERMISSION, precondition="row", all_entities=True))
    ],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change the URL, description or event kinds, or deactivate the endpoint. In a sandbox a
    change that would leave the endpoint active answers 403 ``sandbox-restricted`` (05 SBX-08)."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> WebhookEndpointOut:
        row = webhook_endpoints.update_endpoint(
            uow,
            endpoint_id,
            changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return WebhookEndpointOut.model_validate(dict(row))

    return run_command(cmd, deps, handle, etag=endpoint_etag)


@router.get(
    "/webhook-deliveries",
    operation_id="webhook_deliveries_list",
    response_model=ListOut[WebhookDeliveryOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def webhook_deliveries_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities(PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[WebhookDeliveryStatus | None, Query()] = None,
    webhook_endpoint_id: Annotated[uuid.UUID | None, Query()] = None,
    event_kind: Annotated[str | None, Query()] = None,
) -> ListOut[WebhookDeliveryOut]:
    """The delivery log; sort ``created_at`` (default ``-created_at``, newest first) or ``id``."""
    result = webhook_endpoints.list_deliveries(
        ctx, page=lambda session, statement: paginate(session, statement, DELIVERY_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[WebhookDeliveryOut](
        items=[WebhookDeliveryOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )
