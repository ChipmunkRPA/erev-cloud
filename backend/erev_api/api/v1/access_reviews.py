"""API-R-51 Access reviews: campaigns that snapshot memberships for certification or revocation.

04 §15.3 API-R-51, T-PLT-40, T-PLT-41, DB-10; SCREENS_B §9.13 SF-14:access-reviews and
SF-14:access-review; REQ-CTL-006; BUILD_SPEC PLF-28, BS1-D-28. Every route needs
``access.approve`` for ALL entities — a campaign snapshots every member of the workspace with
the roles and entities each holds, so a holder of named entities is refused its commands and its
reads alike, 403 after a DENIED event that states the scope (04 API-C-03 and API-R-51 rev 1.243;
supervisor rulings R-28 and R-115 (c); the supervisor's ruling of 2026-10-01 on item
SCOPE-WORKSPACE-LISTS-1 (c3), answer Q3; reviewers of named entities are item
ACCESS-REVIEW-SCOPED-REVIEWERS-1). A reviewer never decides the item of their own membership.
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
from erev_api.db.tables import access_review_campaign, access_review_item
from erev_api.domain.platform import access_reviews
from erev_api.enums import AccessReviewStatus
from erev_api.schemas.access_reviews import (
    AccessReviewCreateIn,
    AccessReviewDecideIn,
    AccessReviewItemOut,
    AccessReviewOut,
)
from erev_api.schemas.common import ListOut
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-51 Access reviews"
PERMISSION: Final = access_reviews.REVIEW_PERMISSION
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden", "mfa-required")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
CAMPAIGN_LIST: Final = ListSpec(
    resource="access-reviews",
    sort_keys={
        "id": access_review_campaign.c.id,
        "as_of": access_review_campaign.c.as_of,
        "name": access_review_campaign.c.name,
    },
    default_sort="-id",
    filters={
        "status": FilterSpec(
            name="status",
            column=access_review_campaign.c.status,
            kind="exact",
            choices=frozenset(status.value for status in AccessReviewStatus),
        )
    },
)
ITEM_LIST: Final = ListSpec(
    resource="access-review-items",
    sort_keys={
        "id": access_review_item.c.id,
        "user_email_snapshot": access_review_item.c.user_email_snapshot,
    },
    default_sort="user_email_snapshot",
    filters={},
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def campaign_etag(out: AccessReviewOut) -> str:
    """API-C-08: the campaign is IM-S with SC-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _campaign_location(out: AccessReviewOut) -> str:
    return f"{API_PREFIX}/access-reviews/{out.id}"


@router.get(
    "/access-reviews",
    operation_id="access_reviews_list",
    response_model=ListOut[AccessReviewOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def access_reviews_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities(PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[list[AccessReviewStatus] | None, Query()] = None,
) -> ListOut[AccessReviewOut]:
    """Access review campaigns in every status with their item counts; sort ``id`` (default
    ``-id``), ``as_of`` or ``name``."""
    result, items = access_reviews.list_campaigns(
        ctx, page=lambda session, statement: paginate(session, statement, CAMPAIGN_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[AccessReviewOut](
        items=[AccessReviewOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/access-reviews",
    operation_id="access_reviews_create",
    status_code=201,
    response_model=AccessReviewOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def access_reviews_create(
    body: AccessReviewCreateIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a draft campaign with its reviewers, members who hold access approval for all
    entities."""

    def handle(uow: UnitOfWork) -> AccessReviewOut:
        campaign_id = access_reviews.create_campaign(
            uow,
            name=body.name,
            as_of=body.as_of,
            reviewer_membership_ids=body.reviewer_membership_ids,
        )
        return AccessReviewOut.model_validate(access_reviews.campaign_out(uow, campaign_id))

    return run_command(
        cmd, deps, handle, status_code=201, location=_campaign_location, etag=campaign_etag
    )


@router.get(
    "/access-reviews/{access_review_id}",
    operation_id="access_reviews_get",
    response_model=AccessReviewOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def access_reviews_get(
    access_review_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities(PERMISSION))],
) -> AccessReviewOut:
    """API-S-AccessReview with its reviewers, item counts and snapshot file."""
    out = AccessReviewOut.model_validate(access_reviews.get_campaign(ctx, access_review_id))
    response.headers["ETag"] = campaign_etag(out)
    return out


@router.post(
    "/access-reviews/{access_review_id}/start",
    operation_id="access_reviews_start",
    response_model=AccessReviewOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def access_reviews_start(
    access_review_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Start the review: snapshot every membership that is not removed, with its roles, entity
    scopes, last sign-in, grant date and grantor, into one pending item per member and a snapshot
    file."""

    def handle(uow: UnitOfWork) -> AccessReviewOut:
        access_reviews.start_campaign(uow, access_review_id)
        return AccessReviewOut.model_validate(access_reviews.campaign_out(uow, access_review_id))

    return run_command(cmd, deps, handle, etag=campaign_etag)


@router.post(
    "/access-reviews/{access_review_id}/complete",
    operation_id="access_reviews_complete",
    response_model=AccessReviewOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def access_reviews_complete(
    access_review_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Complete a campaign in review once every item is decided; the certification is kept as
    evidence."""

    def handle(uow: UnitOfWork) -> AccessReviewOut:
        access_reviews.complete_campaign(uow, access_review_id)
        return AccessReviewOut.model_validate(access_reviews.campaign_out(uow, access_review_id))

    return run_command(cmd, deps, handle, etag=campaign_etag)


@router.post(
    "/access-reviews/{access_review_id}/cancel",
    operation_id="access_reviews_cancel",
    response_model=AccessReviewOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def access_reviews_cancel(
    access_review_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Cancel a draft campaign or a campaign in review; decided items stay as history."""

    def handle(uow: UnitOfWork) -> AccessReviewOut:
        access_reviews.cancel_campaign(uow, access_review_id)
        return AccessReviewOut.model_validate(access_reviews.campaign_out(uow, access_review_id))

    return run_command(cmd, deps, handle, etag=campaign_etag)


@router.get(
    "/access-reviews/{access_review_id}/items",
    operation_id="access_reviews_items_list",
    response_model=ListOut[AccessReviewItemOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def access_reviews_items_list(
    access_review_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities(PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[AccessReviewItemOut]:
    """The campaign's items with the roles at snapshot and the decisions; sort
    ``user_email_snapshot`` (default) or ``id``."""
    result, items = access_reviews.list_items(
        ctx,
        access_review_id,
        page=lambda session, statement: paginate(session, statement, ITEM_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[AccessReviewItemOut](
        items=[AccessReviewItemOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/access-reviews/{access_review_id}/items/{item_id}/decide",
    operation_id="access_reviews_items_decide",
    response_model=AccessReviewItemOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "self-approval"
    ),
)
def access_reviews_items_decide(
    access_review_id: uuid.UUID,
    item_id: uuid.UUID,
    body: AccessReviewDecideIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Certify a member's access, or request its revocation with a comment of at least 10
    characters; a reviewer cannot review their own access."""

    def handle(uow: UnitOfWork) -> AccessReviewItemOut:
        access_reviews.decide_item(
            uow, access_review_id, item_id, decision=body.decision, comment=body.comment
        )
        return AccessReviewItemOut.model_validate(access_reviews.item_out(uow, item_id))

    return run_command(cmd, deps, handle)


@router.post(
    "/access-reviews/{access_review_id}/items/{item_id}/confirm-revocation",
    operation_id="access_reviews_items_confirm_revocation",
    response_model=AccessReviewItemOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "self-approval"
    ),
)
def access_reviews_items_confirm_revocation(
    access_review_id: uuid.UUID,
    item_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Record that a requested revocation is complete, after the member's role was revoked or the
    member removed."""

    def handle(uow: UnitOfWork) -> AccessReviewItemOut:
        access_reviews.confirm_revocation(uow, access_review_id, item_id)
        return AccessReviewItemOut.model_validate(access_reviews.item_out(uow, item_id))

    return run_command(cmd, deps, handle)
