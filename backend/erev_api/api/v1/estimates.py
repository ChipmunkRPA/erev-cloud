"""API-R-32 Estimates and portfolios: estimated elements and their versions.

04 §15.3 API-R-32, T-CON-12, T-CON-13, E-09, E-10, E-12, §16.14 estimates; PRD SM-04, §2.5 routing
row ``ESTIMATE_VERSION``, ERR-13; SCREENS §8, R-16, R-24; BUILD_SPEC CTR-12. Reads need
``contract.read``; commands need ``estimate.create``, which the handlers check for the contracting
entity. No route takes ``If-Match``. The portfolio routes arrive with CTR-13.

[J] L5-2-Q-7: API-R-32 has no ``GET /estimates/{id}``, so the ``Location`` of a created element is
its versions collection.
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
from erev_api.db.tables import estimate, estimate_version
from erev_api.domain.contracts import estimates, queries, repo
from erev_api.enums import ConfigStatus, EstimateKind
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.estimates import (
    EstimateCreateIn,
    EstimateOut,
    EstimateVersionCreateIn,
    EstimateVersionOut,
    EstimateVersionSubmitIn,
    EstimateVersionUpdateIn,
    EstimateVersionWithdrawIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-32 Estimates and portfolios"
READ: Final = "contract.read"
CREATE: Final = estimates.CREATE_PERMISSION
JOB_PATH: Final = "/api/v1/jobs/{job_id}"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
    "not-found",
)
ESTIMATE_LIST: Final = ListSpec(
    resource="estimates",
    sort_keys={
        "id": estimate.c.id,
        "element_code": estimate.c.element_code,
        "created_at": estimate.c.created_at,
    },
    default_sort="-id",
    filters={},
    custom_filters=frozenset({"estimate_kind", "status"}),
)
VERSION_LIST: Final = ListSpec(
    resource="estimate_versions",
    sort_keys={
        "id": estimate_version.c.id,
        "version_no": estimate_version.c.version_no,
        "effective_date": estimate_version.c.effective_date,
    },
    default_sort="-id",
    filters={},
    custom_filters=frozenset({"status", "modification_id"}),
)

type ReadContext = Annotated[RequestContext, Depends(require(READ))]
type Params = Annotated[ListParams, Depends(list_params)]
type Deps = Annotated[KernelDeps, Depends(kernel_deps)]

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _total(response: Response, result: ListResult) -> None:
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count


@router.get(
    "/contracts/{contract_id}/estimates",
    operation_id="contract_estimates_list",
    response_model=ListOut[EstimateOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def contract_estimates_list(
    contract_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    params: Params,
    estimate_kind: Annotated[list[EstimateKind] | None, Query(description="E-09")] = None,
    status: Annotated[
        list[ConfigStatus] | None, Query(description="E-12 status of the latest version")
    ] = None,
) -> ListOut[EstimateOut]:
    """The contract's estimated elements with ``current_version`` (latest APPROVED) and
    ``latest_version`` (04 §16.14); sort ``id`` (default ``-id``), ``element_code`` or
    ``created_at``."""

    def page(session: Session) -> tuple[ListResult, list[EstimateOut]]:
        repo.get_contract(session, contract_id)
        statement = estimates.estimates_statement(
            contract_id=contract_id, kinds=tuple(estimate_kind or ()), statuses=tuple(status or ())
        )
        result = paginate(session, statement, ESTIMATE_LIST, params)
        return result, estimates.estimate_outs(session, [dict(row) for row in result.items])

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[EstimateOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/contracts/{contract_id}/estimates",
    operation_id="contract_estimates_create",
    status_code=201,
    response_model=EstimateOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def contract_estimates_create(
    contract_id: uuid.UUID,
    body: EstimateCreateIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Add an estimated element (T-CON-12); its versions carry the figures."""

    def handle(uow: UnitOfWork) -> EstimateOut:
        return estimates.create_estimate(uow, contract_id=contract_id, body=body)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/estimates/{out.id}/versions",
    )


@router.get(
    "/estimates/{estimate_id}/versions",
    operation_id="estimate_versions_list",
    response_model=ListOut[EstimateVersionOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def estimate_versions_list(
    estimate_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    params: Params,
    status: Annotated[list[ConfigStatus] | None, Query(description="E-12")] = None,
    modification_id: Annotated[
        uuid.UUID | None,
        Query(description="T-CON-13: the versions created inside this modification"),
    ] = None,
) -> ListOut[EstimateVersionOut]:
    """The element's versions with ``approver``, ``approved_at`` and the kind additions of 04
    §16.14; sort ``id`` (default ``-id``), ``version_no`` or ``effective_date``."""

    def page(session: Session) -> tuple[ListResult, list[EstimateVersionOut]]:
        estimates.visible_estimate(session, estimate_id)
        statement = estimates.versions_statement(
            estimate_id=estimate_id,
            statuses=tuple(status or ()),
            modification_id=modification_id,
        )
        result = paginate(session, statement, VERSION_LIST, params)
        return result, estimates.version_outs(session, [dict(row) for row in result.items])

    result, items = queries.read(ctx, page)
    _total(response, result)
    return ListOut[EstimateVersionOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/estimates/{estimate_id}/versions",
    operation_id="estimate_versions_create",
    status_code=201,
    response_model=EstimateVersionOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "invalid-transition", "eac-below-costs-incurred"
    ),
)
def estimate_versions_create(
    estimate_id: uuid.UUID,
    body: EstimateVersionCreateIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Prepare a DRAFT version; the method is fixed after version 1 (``ESTIMATE_METHOD_LOCKED``)
    and the constrained amount lies in the V6 range (``ESTIMATE_CONSTRAINT_RANGE``).
    ``modification_id`` names a DRAFT modification of the estimate's contract the version is
    created inside (04 T-CON-13 rev 1.210). One version of an element is prepared at a time:
    while another one is DRAFT or SUBMITTED the answer is 409 ``invalid-transition`` naming it
    (PRD ERR-93; 04 T-CON-13 rev 1.241)."""

    def handle(uow: UnitOfWork) -> EstimateVersionOut:
        return estimates.create_version(uow, estimate_id=estimate_id, body=body)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/estimate-versions/{out.id}",
    )


@router.get(
    "/estimate-versions/{version_id}",
    operation_id="estimate_versions_get",
    response_model=EstimateVersionOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def estimate_versions_get(version_id: uuid.UUID, ctx: ReadContext) -> EstimateVersionOut:
    return queries.read(ctx, lambda session: estimates.get_version(session, version_id))


@router.patch(
    "/estimate-versions/{version_id}",
    operation_id="estimate_versions_update",
    response_model=EstimateVersionOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "invalid-transition", "eac-below-costs-incurred"
    ),
)
def estimate_versions_update(
    version_id: uuid.UUID,
    body: EstimateVersionUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Edit a DRAFT version; a REJECTED or WITHDRAWN version returns to DRAFT — unless another
    version of its element is DRAFT or SUBMITTED, which answers 409 ``invalid-transition`` naming
    it (PRD ERR-93); a submitted or approved version answers 409 ``invalid-transition`` (DB-03)."""

    def handle(uow: UnitOfWork) -> EstimateVersionOut:
        return estimates.update_version(uow, version_id=version_id, body=body)

    return run_command(cmd, deps, handle)


@router.post(
    "/estimate-versions/{version_id}/submit",
    operation_id="estimate_versions_submit",
    response_model=EstimateVersionOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "invalid-transition", "eac-below-costs-incurred"
    ),
)
def estimate_versions_submit(
    version_id: uuid.UUID,
    body: EstimateVersionSubmitIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Submit a DRAFT version with its dry run as the impact preview; the request needs
    ``estimate.approve`` (PRD §2.5) and pins the contract's group and head: once the contract
    changes, its decision answers 409 ``stale-approval`` and the version is WITHDRAWN (04
    §16.10 rev 1.233). A version whose modification was discarded answers 409 (PRD ERR-88).
    A variable-consideration, EAC or return-rate version is submitted with its evidence
    attached (``ESTIMATE_EVIDENCE_REQUIRED``), and a variable-consideration version names the
    ``CONSTRAINT`` judgement record of its element, sent for review or reviewed
    (``ESTIMATE_CONSTRAINT_RECORD``); a variable-consideration version whose values equal the
    approved version's is an attestation of no change and states its reason instead
    (``ESTIMATE_ATTESTATION_REASON``, ``ESTIMATE_ATTESTATION_VALUES``; 04 §16.14 rev 1.241)."""

    def handle(uow: UnitOfWork) -> EstimateVersionOut:
        return estimates.submit_version(uow, version_id=version_id, body=body)

    return run_command(cmd, deps, handle)


@router.post(
    "/estimate-versions/{version_id}/withdraw",
    operation_id="estimate_versions_withdraw",
    response_model=EstimateVersionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def estimate_versions_withdraw(
    version_id: uuid.UUID,
    body: EstimateVersionWithdrawIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """The preparer withdraws the pending request; the version becomes WITHDRAWN (E-12)."""

    def handle(uow: UnitOfWork) -> EstimateVersionOut:
        return estimates.withdraw_version(uow, version_id=version_id, body=body)

    return run_command(cmd, deps, handle)


@router.post(
    "/estimate-versions/{version_id}/discard",
    operation_id="estimate_versions_discard",
    response_model=EstimateVersionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def estimate_versions_discard(
    version_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Discard a DRAFT version (PRD SM-04 ``DRAFT`` → ``VOIDED``; item EST-DISCARD-1): no body;
    any other status answers 409 ``invalid-transition``."""

    def handle(uow: UnitOfWork) -> EstimateVersionOut:
        return estimates.discard_version(uow, version_id=version_id)

    return run_command(cmd, deps, handle)


@router.post(
    "/estimate-versions/{version_id}/preview",
    operation_id="estimate_versions_preview",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def estimate_versions_preview(
    version_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Deps,
) -> Response:
    """Defer the dry run with the version applied; the job's ``result.summary`` is
    API-S-ImpactSummary (04 §16.14; SCREENS R-16)."""

    def handle(uow: UnitOfWork) -> JobOut:
        return estimates.request_preview(uow, version_id=version_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        extra_headers=lambda job: {"Location": JOB_PATH.format(job_id=job.id)},
    )
