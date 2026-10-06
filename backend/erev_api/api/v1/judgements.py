"""API-R-33 Judgements: judgement records with preparer and reviewer.

04 §15.3 API-R-33, T-CON-19, E-56, E-57, §14.1 DB-10; PRD SM-10, §2.5 routing row
``JUDGEMENT_RECORD``; 03 REQ-POL-008; BUILD_SPEC CTR-7. Reads need ``contract.read``; commands need
``judgement.create``, which the handlers check for the subject's contracting entity. No route takes
``If-Match``.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

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
    ListParams,
    ListResult,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import judgement_record
from erev_api.domain.contracts import queries
from erev_api.domain.policies import judgements
from erev_api.enums import JudgementStatus, JudgementTopic
from erev_api.schemas.common import ListOut
from erev_api.schemas.judgements import (
    JudgementCreateIn,
    JudgementOut,
    JudgementSubmitIn,
    JudgementUpdateIn,
    SubjectType,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-33 Judgements"
READ: Final = "contract.read"
CREATE: Final = judgements.CREATE_PERMISSION
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
    "not-found",
)
JUDGEMENT_LIST: Final = ListSpec(
    resource="judgements",
    sort_keys={
        "id": judgement_record.c.id,
        "judgement_no": judgement_record.c.judgement_no,
        "created_at": judgement_record.c.created_at,
    },
    default_sort="-id",
    filters={},
    custom_filters=frozenset({"topic", "status", "subject_type", "subject_id"}),
)

type ReadContext = Annotated[RequestContext, Depends(require(READ))]
type Params = Annotated[ListParams, Depends(list_params)]
type Deps = Annotated[KernelDeps, Depends(kernel_deps)]

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _total(response: Response, result: ListResult) -> None:
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count


@router.get(
    "/judgements",
    operation_id="judgements_list",
    response_model=ListOut[JudgementOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def judgements_list(
    response: Response,
    ctx: ReadContext,
    params: Params,
    topic: Annotated[list[JudgementTopic] | None, Query(description="E-56")] = None,
    status: Annotated[list[JudgementStatus] | None, Query(description="E-57")] = None,
    subject_type: Annotated[SubjectType | None, Query()] = None,
    subject_id: Annotated[uuid.UUID | None, Query()] = None,
) -> ListOut[JudgementOut]:
    """Judgement records; sort ``id`` (default ``-id``), ``judgement_no`` or ``created_at``. The
    close gate lists ``status=SUBMITTED`` (CTL-049)."""

    def page(session: Session) -> tuple[ListResult, list[JudgementOut]]:
        statement = judgements.judgements_statement(
            topics=tuple(topic or ()),
            statuses=tuple(status or ()),
            subject_type=subject_type,
            subject_id=subject_id,
        )
        result = paginate(session, statement, JUDGEMENT_LIST, params)
        return result, judgements.judgement_outs(session, [dict(row) for row in result.items])

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[JudgementOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/judgements",
    operation_id="judgements_create",
    status_code=201,
    response_model=JudgementOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def judgements_create(
    body: JudgementCreateIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Prepare a DRAFT judgement record; the questionnaire is validated per topic (T-CON-19)."""

    def handle(uow: UnitOfWork) -> JudgementOut:
        return judgements.create_judgement(uow, body=body)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/judgements/{out.id}",
    )


@router.get(
    "/judgements/{judgement_id}",
    operation_id="judgements_get",
    response_model=JudgementOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def judgements_get(judgement_id: uuid.UUID, ctx: ReadContext) -> JudgementOut:
    return queries.read(ctx, lambda session: judgements.get_judgement(session, judgement_id))


@router.patch(
    "/judgements/{judgement_id}",
    operation_id="judgements_update",
    response_model=JudgementOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def judgements_update(
    judgement_id: uuid.UUID,
    body: JudgementUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Edit a DRAFT record; a REJECTED record returns to DRAFT (PRD SM-10)."""

    def handle(uow: UnitOfWork) -> JudgementOut:
        return judgements.update_judgement(uow, judgement_id=judgement_id, body=body)

    return run_command(cmd, deps, handle)


@router.post(
    "/judgements/{judgement_id}/submit",
    operation_id="judgements_submit",
    response_model=JudgementOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def judgements_submit(
    judgement_id: uuid.UUID,
    body: JudgementSubmitIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Submit a DRAFT record for review; the request needs ``judgement.review`` (PRD §2.5)."""

    def handle(uow: UnitOfWork) -> JudgementOut:
        return judgements.submit_judgement(uow, judgement_id=judgement_id, body=body)

    return run_command(cmd, deps, handle)


@router.post(
    "/judgements/{judgement_id}/discard",
    operation_id="judgements_discard",
    response_model=JudgementOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def judgements_discard(
    judgement_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Discard a DRAFT or a REJECTED record (PRD SM-10 ``DRAFT`` → ``VOIDED``; 04 T-CON-19 rev
    1.242, rev 1.296): no body; any other status, and the proposal of a combination group,
    answer 409 ``invalid-transition``. A rejected record is taken through the draft state inside
    the command."""

    def handle(uow: UnitOfWork) -> JudgementOut:
        return judgements.discard_judgement(uow, judgement_id=judgement_id)

    return run_command(cmd, deps, handle)
