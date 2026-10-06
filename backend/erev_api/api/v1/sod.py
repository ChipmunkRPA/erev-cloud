"""API-R-07 SoD: separation-of-duties rule versions and exceptions.

04 §15.3 API-R-07, T-PLT-13, T-PLT-14, API-C-09; SCREENS_B §9.10 exception drawer and §9.12
bindings; PRD SM-04, SM-13, ERR-22; BUILD_SPEC PLF-19, BS1-D-29. Every route needs ``role.manage``;
rule versions and exceptions take effect once another ``access.approve`` holder approves them.

A rule is the workspace's: a new version of one asks the permission for ALL entities. An exception
is a member's: asking for one and revoking one need the permission for every entity of the
member's role assignments (04 API-C-03 and API-R-07 rev 1.243; supervisor ruling R-119 (b); the
supervisor's ruling of 2026-10-01 on item SCOPE-WORKSPACE-LISTS-1 (c3)). The two lists name a rule
and a member, no entity, and stay as they are.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Path, Query, Response

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
    FilterSpec,
    ListParams,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import sod_exception, sod_rule
from erev_api.domain.platform import sod
from erev_api.enums import ConfigStatus, GrantStatus
from erev_api.schemas.common import ListOut
from erev_api.schemas.sod import (
    CODE_LENGTH,
    SodExceptionIn,
    SodExceptionOut,
    SodExceptionRevokeIn,
    SodRuleOut,
    SodRuleVersionIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-07 SoD"
PERMISSION: Final = sod.MANAGE_PERMISSION
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden", "mfa-required")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
RULE_LIST: Final = ListSpec(
    resource="sod-rules",
    sort_keys={"id": sod_rule.c.id, "code": sod_rule.c.code, "version_no": sod_rule.c.version_no},
    default_sort="code",
    filters={
        "status": FilterSpec(
            name="status",
            column=sod_rule.c.status,
            kind="exact",
            choices=frozenset(status.value for status in ConfigStatus),
        ),
        "code": FilterSpec(name="code", column=sod_rule.c.code, kind="exact"),
    },
    search_columns=(sod_rule.c.code, sod_rule.c.name),
)
EXCEPTION_LIST: Final = ListSpec(
    resource="sod-exceptions",
    sort_keys={
        "id": sod_exception.c.id,
        "valid_from": sod_exception.c.valid_from,
        "valid_to": sod_exception.c.valid_to,
    },
    default_sort="-id",
    filters={
        "status": FilterSpec(
            name="status",
            column=sod_exception.c.status,
            kind="exact",
            choices=frozenset(status.value for status in GrantStatus),
        ),
        "membership_id": FilterSpec(
            name="membership_id", column=sod_exception.c.membership_id, kind="exact"
        ),
        "sod_rule_code": FilterSpec(
            name="sod_rule_code", column=sod_exception.c.sod_rule_code, kind="exact"
        ),
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


@router.get(
    "/sod-rules",
    operation_id="sod_rules_list",
    response_model=ListOut[SodRuleOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def sod_rules_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[list[ConfigStatus] | None, Query()] = None,
    code: Annotated[str | None, Query(max_length=CODE_LENGTH)] = None,
) -> ListOut[SodRuleOut]:
    """Every version of every rule; ``q`` searches code and name; sort ``code`` (default), ``id``
    or ``version_no``."""
    result, items = sod.list_sod_rules(
        ctx, page=lambda session, statement: paginate(session, statement, RULE_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[SodRuleOut](
        items=[SodRuleOut.model_validate(item) for item in items], next_cursor=result.next_cursor
    )


@router.post(
    "/sod-rules/{code}/versions",
    operation_id="sod_rule_versions_create",
    status_code=201,
    response_model=SodRuleOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def sod_rule_versions_create(
    code: Annotated[str, Path(max_length=CODE_LENGTH)],
    body: SodRuleVersionIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Propose the next version of a rule; approval publishes it and supersedes the published
    version. A rule binds every member of the workspace: the command asks ``role.manage`` for
    all entities."""

    def handle(uow: UnitOfWork) -> SodRuleOut:
        version_id = sod.create_sod_rule_version(
            uow,
            code,
            name=body.name,
            function_a_permissions=body.function_a_permissions,
            function_b_permissions=body.function_b_permissions,
            rationale=body.rationale,
            comment=body.comment,
        )
        return SodRuleOut.model_validate(sod.rule_out(uow, version_id))

    return run_command(cmd, deps, handle, status_code=201)


@router.get(
    "/sod-exceptions",
    operation_id="sod_exceptions_list",
    response_model=ListOut[SodExceptionOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def sod_exceptions_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[list[GrantStatus] | None, Query()] = None,
    membership_id: Annotated[uuid.UUID | None, Query()] = None,
    sod_rule_code: Annotated[str | None, Query(max_length=CODE_LENGTH)] = None,
) -> ListOut[SodExceptionOut]:
    """SoD exceptions in every status; sort ``id`` (default ``-id``), ``valid_from`` or
    ``valid_to``."""
    result, items = sod.list_sod_exceptions(
        ctx, page=lambda session, statement: paginate(session, statement, EXCEPTION_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[SodExceptionOut](
        items=[SodExceptionOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/sod-exceptions",
    operation_id="sod_exceptions_create",
    status_code=201,
    response_model=SodExceptionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def sod_exceptions_create(
    body: SodExceptionIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Request an exception for a member and rule; it covers conflicts once approved."""

    def handle(uow: UnitOfWork) -> SodExceptionOut:
        exception_id = sod.request_sod_exception(
            uow,
            sod_rule_code=body.sod_rule_code,
            membership_id=body.membership_id,
            compensating_control=body.compensating_control,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            comment=body.comment,
        )
        return SodExceptionOut.model_validate(sod.exception_out(uow, exception_id))

    return run_command(cmd, deps, handle, status_code=201)


@router.post(
    "/sod-exceptions/{exception_id}/revoke",
    operation_id="sod_exceptions_revoke",
    response_model=SodExceptionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def sod_exceptions_revoke(
    exception_id: uuid.UUID,
    body: SodExceptionRevokeIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Revoke an approved exception now; the conflicts it covered become uncovered."""

    def handle(uow: UnitOfWork) -> SodExceptionOut:
        sod.revoke_sod_exception(uow, exception_id, reason=body.reason)
        return SodExceptionOut.model_validate(sod.exception_out(uow, exception_id))

    return run_command(cmd, deps, handle)
