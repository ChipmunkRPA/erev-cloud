"""API-R-22 Customers: customers and related-party groups.

04 §15.3 API-R-22, §16.14 list additions, T-REF-18, T-REF-19, API-C-08, API-C-09; SCREENS §9.4;
BUILD_SPEC RFD-8. Reading needs ``contract.read``; creating or changing a customer or a group needs
``masterdata.maintain``, and ``PATCH`` needs ``If-Match``. No route deletes: a customer is
deactivated with ``PATCH {is_active: false}`` (T-REF-19, IM-M).
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
from erev_api.db.tables import customer, related_party_group
from erev_api.domain.reference import commands, queries
from erev_api.enums import SourceSystem
from erev_api.schemas.common import ListOut
from erev_api.schemas.customers import (
    CustomerIn,
    CustomerOut,
    CustomerUpdateIn,
    RelatedPartyGroupIn,
    RelatedPartyGroupOut,
    RelatedPartyGroupUpdateIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-22 Customers"
READ_PERMISSION: Final = "contract.read"
MAINTAIN_PERMISSION: Final = "masterdata.maintain"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
_UPDATE_PROBLEMS: Final = (
    *_COMMAND_PROBLEMS,
    "not-found",
    "precondition-failed",
    "precondition-required",
)
CUSTOMER_LIST: Final = ListSpec(
    resource="customers",
    sort_keys={
        "id": customer.c.id,
        "code": customer.c.code,
        "name": customer.c.name,
        "updated_at": customer.c.updated_at,
    },
    default_sort="name",
    filters={
        "related_party_group_id": FilterSpec(
            name="related_party_group_id", column=customer.c.related_party_group_id, kind="exact"
        ),
        "source_system": FilterSpec(
            name="source_system",
            column=customer.c.source_system,
            kind="exact",
            choices=frozenset(member.value for member in SourceSystem),
        ),
        "external_id": FilterSpec(name="external_id", column=customer.c.external_id, kind="exact"),
        "is_active": FilterSpec(name="is_active", column=customer.c.is_active, kind="bool"),
    },
    search_columns=(customer.c.code, customer.c.name, customer.c.external_id),
)
RELATED_PARTY_GROUP_LIST: Final = ListSpec(
    resource="related-party-groups",
    sort_keys={
        "id": related_party_group.c.id,
        "code": related_party_group.c.code,
        "name": related_party_group.c.name,
        "updated_at": related_party_group.c.updated_at,
    },
    default_sort="code",
    filters={},
    search_columns=(related_party_group.c.code, related_party_group.c.name),
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def customer_etag(out: CustomerOut) -> str:
    """API-C-08: a customer is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def customer_location(out: CustomerOut) -> str:
    return f"{API_PREFIX}/customers/{out.id}"


def related_party_group_etag(out: RelatedPartyGroupOut) -> str:
    """API-C-08: a related-party group is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


@router.get(
    "/customers",
    operation_id="customers_list",
    response_model=ListOut[CustomerOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def customers_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    related_party_group_id: Annotated[uuid.UUID | None, Query()] = None,
    source_system: Annotated[SourceSystem | None, Query()] = None,
    external_id: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> ListOut[CustomerOut]:
    """The tenant's customers; sort ``name`` (default), ``code``, ``updated_at`` or ``id``; ``q``
    searches code, name and external id (SCREENS §9.4)."""
    result = queries.list_customers(
        ctx, page=lambda session, statement: paginate(session, statement, CUSTOMER_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[CustomerOut](
        items=[CustomerOut.model_validate(queries.customer_out(item)) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/customers",
    operation_id="customers_create",
    status_code=201,
    response_model=CustomerOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def customers_create(
    body: CustomerIn,
    cmd: Annotated[CommandContext, Depends(command(MAINTAIN_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a customer; its code is unique in the workspace, and its external id unique per
    source system (REQ-REF-010)."""

    def handle(uow: UnitOfWork) -> CustomerOut:
        return commands.create_customer(uow, body=body)

    return run_command(
        cmd, deps, handle, status_code=201, location=customer_location, etag=customer_etag
    )


@router.get(
    "/customers/{customer_id}",
    operation_id="customers_get",
    response_model=CustomerOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def customers_get(
    customer_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
) -> CustomerOut:
    """One customer with its ``ETag``."""
    out = CustomerOut.model_validate(queries.get_customer(ctx, customer_id))
    response.headers["ETag"] = customer_etag(out)
    return out


@router.patch(
    "/customers/{customer_id}",
    operation_id="customers_update",
    response_model=CustomerOut,
    responses=problem_responses(*_UPDATE_PROBLEMS),
)
def customers_update(
    customer_id: uuid.UUID,
    body: CustomerUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(MAINTAIN_PERMISSION, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change a customer's code, name, group, parent, credit grade, segment or country, or
    (de)activate it."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> CustomerOut:
        return commands.update_customer(
            uow,
            customer_id=customer_id,
            changes=changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle, etag=customer_etag)


@router.get(
    "/related-party-groups",
    operation_id="related_party_groups_list",
    response_model=ListOut[RelatedPartyGroupOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def related_party_groups_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[RelatedPartyGroupOut]:
    """The tenant's related-party groups with ``member_count``; sort ``code`` (default), ``name``,
    ``updated_at`` or ``id``; ``q`` searches code and name."""
    result = queries.list_related_party_groups(
        ctx,
        page=lambda session, statement: paginate(
            session, statement, RELATED_PARTY_GROUP_LIST, params
        ),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[RelatedPartyGroupOut](
        items=[RelatedPartyGroupOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/related-party-groups",
    operation_id="related_party_groups_create",
    status_code=201,
    response_model=RelatedPartyGroupOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def related_party_groups_create(
    body: RelatedPartyGroupIn,
    cmd: Annotated[CommandContext, Depends(command(MAINTAIN_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a related-party group; its code is unique in the workspace. API-R-22 has no
    single-group read, so the 201 carries an ``ETag`` but no ``Location`` (DG-CMD-12)."""

    def handle(uow: UnitOfWork) -> RelatedPartyGroupOut:
        return commands.create_related_party_group(uow, body=body)

    return run_command(cmd, deps, handle, status_code=201, etag=related_party_group_etag)


@router.patch(
    "/related-party-groups/{group_id}",
    operation_id="related_party_groups_update",
    response_model=RelatedPartyGroupOut,
    responses=problem_responses(*_UPDATE_PROBLEMS),
)
def related_party_groups_update(
    group_id: uuid.UUID,
    body: RelatedPartyGroupUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(MAINTAIN_PERMISSION, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change a group's code, name or description. Members join or leave a group from the
    customer (SCREENS §9.5)."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> RelatedPartyGroupOut:
        return commands.update_related_party_group(
            uow,
            group_id=group_id,
            changes=changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle, etag=related_party_group_etag)
