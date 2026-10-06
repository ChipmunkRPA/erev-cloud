"""API-R-23 Products and bundles: products, principal-or-agent and policy-values proposals and
bundle components.

04 §15.3 API-R-23, T-REF-20, T-REF-21, API-C-06, API-C-08, API-C-09; SCREENS §10.3; PRD §2.5
routing row ``PRINCIPAL_AGENT_CHANGE``; BUILD_SPEC RFD-9. Reading needs ``contract.read``; creating
or changing a product, proposing a principal-or-agent change or replacing bundle components needs
``masterdata.maintain``, and ``PATCH`` needs ``If-Match``. No route deletes a product: it is
deactivated with ``PATCH {is_active: false}`` (T-REF-20, IM-M). Approval of a proposal
(``config.approve``, API-R-09) sets the conclusion, or the proposed level-P policy values (04 rev
1.110; security ruling R-21).
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
from erev_api.db.tables import product
from erev_api.domain.reference import commands, queries
from erev_api.schemas.common import ListOut
from erev_api.schemas.products import (
    BundleComponentsIn,
    BundleComponentsOut,
    PolicyValuesChangeIn,
    PolicyValuesChangeOut,
    PrincipalAgentChangeIn,
    PrincipalAgentChangeOut,
    ProductIn,
    ProductOut,
    ProductUpdateIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-23 Products and bundles"
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
PRODUCT_LIST: Final = ListSpec(
    resource="products",
    sort_keys={
        "id": product.c.id,
        "code": product.c.code,
        "name": product.c.name,
        "updated_at": product.c.updated_at,
    },
    default_sort="code",
    filters={
        "product_family": FilterSpec(
            name="product_family", column=product.c.product_family, kind="exact"
        ),
        "is_active": FilterSpec(name="is_active", column=product.c.is_active, kind="bool"),
    },
    search_columns=(product.c.code, product.c.name, product.c.sku_number),
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def product_etag(out: ProductOut) -> str:
    """API-C-08: a product is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def product_location(out: ProductOut) -> str:
    return f"{API_PREFIX}/products/{out.id}"


@router.get(
    "/products",
    operation_id="products_list",
    response_model=ListOut[ProductOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def products_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    product_family: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> ListOut[ProductOut]:
    """The tenant's products; sort ``code`` (default), ``name``, ``updated_at`` or ``id``; ``q``
    searches code, name and SKU number (SCREENS §10.3)."""
    result, items = queries.list_products(
        ctx, page=lambda session, statement: paginate(session, statement, PRODUCT_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[ProductOut](
        items=[ProductOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/products",
    operation_id="products_create",
    status_code=201,
    response_model=ProductOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def products_create(
    body: ProductIn,
    cmd: Annotated[CommandContext, Depends(command(MAINTAIN_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a product; its code is unique in the workspace (REQ-REF-012)."""

    def handle(uow: UnitOfWork) -> ProductOut:
        return commands.create_product(uow, body=body)

    return run_command(
        cmd, deps, handle, status_code=201, location=product_location, etag=product_etag
    )


@router.get(
    "/products/{product_id}",
    operation_id="products_get",
    response_model=ProductOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def products_get(
    product_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
) -> ProductOut:
    """One product with its ``ETag``."""
    out = ProductOut.model_validate(queries.get_product(ctx, product_id))
    response.headers["ETag"] = product_etag(out)
    return out


@router.patch(
    "/products/{product_id}",
    operation_id="products_update",
    response_model=ProductOut,
    responses=problem_responses(*_UPDATE_PROBLEMS),
)
def products_update(
    product_id: uuid.UUID,
    body: ProductUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(MAINTAIN_PERMISSION, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change a product's attributes or (de)activate it. A changed ``principal_agent`` returns
    422: propose the change for approval instead (REQ-REF-012)."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> ProductOut:
        return commands.update_product(
            uow,
            product_id=product_id,
            changes=changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle, etag=product_etag)


@router.post(
    "/products/{product_id}/propose-principal-agent-change",
    operation_id="products_propose_principal_agent_change",
    response_model=PrincipalAgentChangeOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def products_propose_principal_agent_change(
    product_id: uuid.UUID,
    body: PrincipalAgentChangeIn,
    cmd: Annotated[CommandContext, Depends(command(MAINTAIN_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Open a ``PRINCIPAL_AGENT_CHANGE`` request; the product keeps its conclusion until a
    ``config.approve`` holder other than the proposer approves (PRD §2.5; CTL-031)."""

    def handle(uow: UnitOfWork) -> PrincipalAgentChangeOut:
        return commands.propose_principal_agent_change(uow, product_id=product_id, body=body)

    return run_command(cmd, deps, handle)


@router.post(
    "/products/{product_id}/propose-policy-values-change",
    operation_id="products_propose_policy_values_change",
    response_model=PolicyValuesChangeOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def products_propose_policy_values_change(
    product_id: uuid.UUID,
    body: PolicyValuesChangeIn,
    cmd: Annotated[CommandContext, Depends(command(MAINTAIN_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Open a ``PRINCIPAL_AGENT_CHANGE`` request for the product's level-P policy values; the
    product keeps its values until a ``config.approve`` holder other than the proposer approves
    (POLICIES §0.6; REQ-POL-003; CTL-031)."""

    def handle(uow: UnitOfWork) -> PolicyValuesChangeOut:
        return commands.propose_policy_values_change(uow, product_id=product_id, body=body)

    return run_command(cmd, deps, handle)


@router.get(
    "/products/{product_id}/bundle-components",
    operation_id="products_bundle_components_get",
    response_model=BundleComponentsOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def products_bundle_components_get(
    product_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
) -> BundleComponentsOut:
    """Every component row of the bundle, current and historical (T-REF-21)."""
    return BundleComponentsOut.model_validate(queries.get_bundle_components(ctx, product_id))


@router.put(
    "/products/{product_id}/bundle-components",
    operation_id="products_bundle_components_put",
    response_model=BundleComponentsOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found"),
)
def products_bundle_components_put(
    product_id: uuid.UUID,
    body: BundleComponentsIn,
    cmd: Annotated[CommandContext, Depends(command(MAINTAIN_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Replace the bundle's component rows; fixed percentages of a set total 100% (REQ-REF-013)."""

    def handle(uow: UnitOfWork) -> BundleComponentsOut:
        return commands.put_bundle_components(uow, product_id=product_id, body=body)

    return run_command(cmd, deps, handle)
