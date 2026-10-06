"""API-R-25 Rule sets: decision tables, their versions, rules, example cases and lifecycle.

04 §15.3 API-R-25, T-REF-24 to T-REF-27, API-C-08, API-C-09, API-C-13, §16.2, §16.14 list additions;
PRD SM-04, BR-POL-01; SCREENS §11.1; BUILD_SPEC RFD-4, RFD-5. Reads and evaluation need
``config.read``; authoring and the lifecycle commands need ``config.author``. Rules and example
cases change only while their version is DRAFT or TESTED (DB-04); approval of the submitted version
publishes it (``config.approve``, API-R-09).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select

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
from erev_api.db.tables import rule, rule_set, rule_set_version, rule_test_case
from erev_api.domain.policies import commands, queries, rule_sets
from erev_api.enums import ConfigStatus, RuleSetKind
from erev_api.schemas.common import ListOut
from erev_api.schemas.rule_sets import (
    ConfigTestCaseOut,
    RuleIn,
    RuleOut,
    RuleSetEvaluateIn,
    RuleSetEvaluationOut,
    RuleSetIn,
    RuleSetOut,
    RuleSetVersionIn,
    RuleSetVersionOut,
    RuleSetVersionSubmitIn,
    RuleSetVersionUpdateIn,
    RuleTestCaseIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-25 Rule sets"
READ: Final = "config.read"
AUTHOR: Final = "config.author"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
_STATUSES: Final = frozenset(status.value for status in ConfigStatus)
_LATEST: Final = rule_set_version.alias("latest_version")
# The status filter of `GET /rule-sets` reads the status of the set's highest version_no.
LATEST_STATUS: Final = (
    select(_LATEST.c.status)
    .where(_LATEST.c.tenant_id == rule_set.c.tenant_id, _LATEST.c.rule_set_id == rule_set.c.id)
    .order_by(_LATEST.c.version_no.desc())
    .limit(1)
    .scalar_subquery()
)
RULE_SET_LIST: Final = ListSpec(
    resource="rule-sets",
    sort_keys={"id": rule_set.c.id, "code": rule_set.c.code, "name": rule_set.c.name},
    default_sort="code",
    filters={
        "kind": FilterSpec(
            name="kind",
            column=rule_set.c.kind,
            kind="exact",
            choices=frozenset(kind.value for kind in RuleSetKind),
        ),
        "status": FilterSpec(name="status", column=LATEST_STATUS, kind="exact", choices=_STATUSES),
    },
    search_columns=(rule_set.c.code, rule_set.c.name),
)
VERSION_LIST: Final = ListSpec(
    resource="rule-set-versions",
    sort_keys={"id": rule_set_version.c.id, "version_no": rule_set_version.c.version_no},
    default_sort="-version_no",
    filters={
        "status": FilterSpec(
            name="status", column=rule_set_version.c.status, kind="exact", choices=_STATUSES
        ),
    },
)
RULE_LIST: Final = ListSpec(
    resource="rules",
    sort_keys={"id": rule.c.id, "rule_key": rule.c.rule_key, "priority": rule.c.priority},
    default_sort="rule_key",
    filters={},
    search_columns=(rule.c.rule_key,),
)
TEST_CASE_LIST: Final = ListSpec(
    resource="test-cases",
    sort_keys={"id": rule_test_case.c.id, "name": rule_test_case.c.name},
    default_sort="id",
    filters={},
    search_columns=(rule_test_case.c.name,),
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _etag(out: RuleSetOut | RuleSetVersionOut) -> str:
    """API-C-08: rule sets are IM-M and versions IM-P, so the ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _version(uow: UnitOfWork, version_id: uuid.UUID) -> RuleSetVersionOut:
    """API-S-RuleSetVersion in the command's transaction."""
    return RuleSetVersionOut.model_validate(
        queries.version_out(uow.session, version_id, files=uow.files, keyring=uow.keyring)
    )


@router.get(
    "/rule-sets",
    operation_id="rule_sets_list",
    response_model=ListOut[RuleSetOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def rule_sets_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
    params: Annotated[ListParams, Depends(list_params)],
    kind: Annotated[list[RuleSetKind] | None, Query()] = None,
    status: Annotated[
        list[ConfigStatus] | None, Query(description="Status of the set's latest version")
    ] = None,
) -> ListOut[RuleSetOut]:
    """Rule sets with ``current_version`` and ``latest_version``; ``q`` searches code and name;
    sort ``code`` (default), ``name`` or ``id``."""
    result, items = queries.list_rule_sets(
        ctx, page=lambda session, statement: paginate(session, statement, RULE_SET_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[RuleSetOut](
        items=[RuleSetOut.model_validate(item) for item in items], next_cursor=result.next_cursor
    )


@router.post(
    "/rule-sets",
    operation_id="rule_sets_create",
    status_code=201,
    response_model=RuleSetOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def rule_sets_create(
    body: RuleSetIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a decision table of one kind; its kind never changes."""

    def handle(uow: UnitOfWork) -> RuleSetOut:
        rule_set_id = commands.create_rule_set(
            uow, code=body.code, kind=body.kind, name=body.name, description=body.description
        )
        return RuleSetOut.model_validate(queries.rule_set_out(uow.session, rule_set_id))

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/rule-sets/{out.id}",
        etag=_etag,
    )


@router.get(
    "/rule-sets/{rule_set_id}",
    operation_id="rule_sets_get",
    response_model=RuleSetOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def rule_sets_get(
    rule_set_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
) -> RuleSetOut:
    out = RuleSetOut.model_validate(queries.get_rule_set(ctx, rule_set_id))
    response.headers["ETag"] = _etag(out)
    return out


@router.post(
    "/rule-sets/{rule_set_id}/evaluate",
    operation_id="rule_sets_evaluate",
    response_model=RuleSetEvaluationOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found"),
)
def rule_sets_evaluate(
    rule_set_id: uuid.UUID,
    body: RuleSetEvaluateIn,
    cmd: Annotated[CommandContext, Depends(command(READ))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Evaluate facts against a version, or against the PUBLISHED version in force; the most
    specific rule wins, then the highest priority (REQ-POL-002). Nothing is written."""

    def handle(uow: UnitOfWork) -> RuleSetEvaluationOut:
        result = rule_sets.evaluate_rule_set(
            uow.session,
            rule_set_id,
            raw_facts=body.facts,
            version_id=body.version_id,
            at=uow.now if body.at is None else body.at,
        )
        return RuleSetEvaluationOut.model_validate(result)

    return run_command(cmd, deps, handle)


@router.get(
    "/rule-sets/{rule_set_id}/versions",
    operation_id="rule_set_versions_list",
    response_model=ListOut[RuleSetVersionOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def rule_set_versions_list(
    rule_set_id: uuid.UUID,
    request: Request,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[list[ConfigStatus] | None, Query()] = None,
) -> ListOut[RuleSetVersionOut]:
    """Every version of a set; sort ``version_no`` (default ``-version_no``) or ``id``."""
    result, items = queries.list_versions(
        ctx,
        rule_set_id,
        page=lambda session, statement: paginate(session, statement, VERSION_LIST, params),
        files=request.app.state.file_store,
        keyring=request.app.state.keyring,
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[RuleSetVersionOut](
        items=[RuleSetVersionOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/rule-sets/{rule_set_id}/versions",
    operation_id="rule_set_versions_create",
    status_code=201,
    response_model=RuleSetVersionOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-frozen"
    ),
)
def rule_set_versions_create(
    rule_set_id: uuid.UUID,
    body: RuleSetVersionIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Start the next version as DRAFT, optionally copying an earlier version's rules and cases."""

    def handle(uow: UnitOfWork) -> RuleSetVersionOut:
        version_id = commands.create_rule_set_version(
            uow,
            rule_set_id,
            effective_from=body.effective_from,
            source_version_id=body.source_version_id,
        )
        return _version(uow, version_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/rule-set-versions/{out.id}",
        etag=_etag,
    )


@router.get(
    "/rule-set-versions/{version_id}",
    operation_id="rule_set_versions_get",
    response_model=RuleSetVersionOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def rule_set_versions_get(
    version_id: uuid.UUID,
    request: Request,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
) -> RuleSetVersionOut:
    out = RuleSetVersionOut.model_validate(
        queries.get_version(
            ctx,
            version_id,
            files=request.app.state.file_store,
            keyring=request.app.state.keyring,
        )
    )
    response.headers["ETag"] = _etag(out)
    return out


@router.patch(
    "/rule-set-versions/{version_id}",
    operation_id="rule_set_versions_update",
    response_model=RuleSetVersionOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "not-found",
        "invalid-transition",
        "configuration-frozen",
        "precondition-failed",
        "precondition-required",
    ),
)
def rule_set_versions_update(
    version_id: uuid.UUID,
    body: RuleSetVersionUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change the effective date of a DRAFT or TESTED version (``If-Match`` required)."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> RuleSetVersionOut:
        commands.update_rule_set_version(
            uow,
            version_id,
            changes=changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return _version(uow, version_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/rule-set-versions/{version_id}/lint",
    operation_id="rule_set_versions_lint",
    response_model=RuleSetVersionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "configuration-frozen"),
)
def rule_set_versions_lint(
    version_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Report rules with equal specificity and priority that can match the same item."""

    def handle(uow: UnitOfWork) -> RuleSetVersionOut:
        commands.lint_rule_set_version(uow, version_id)
        return _version(uow, version_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/rule-set-versions/{version_id}/test",
    operation_id="rule_set_versions_test",
    response_model=RuleSetVersionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def rule_set_versions_test(
    version_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Run the example cases and the lint; a DRAFT version whose cases and lint pass is TESTED."""

    def handle(uow: UnitOfWork) -> RuleSetVersionOut:
        commands.run_rule_set_version_tests(uow, version_id)
        return _version(uow, version_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/rule-set-versions/{version_id}/submit",
    operation_id="rule_set_versions_submit",
    response_model=RuleSetVersionOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-overlap"
    ),
)
def rule_set_versions_submit(
    version_id: uuid.UUID,
    body: RuleSetVersionSubmitIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Submit a TESTED version for approval with its simulation report (PRD BR-POL-01)."""

    def handle(uow: UnitOfWork) -> RuleSetVersionOut:
        commands.submit_rule_set_version(uow, version_id, comment=body.comment)
        return _version(uow, version_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/rule-set-versions/{version_id}/publish",
    operation_id="rule_set_versions_publish",
    response_model=RuleSetVersionOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-overlap"
    ),
)
def rule_set_versions_publish(
    version_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Publish a version left APPROVED; approval publishes a version itself (04 §16.5)."""

    def handle(uow: UnitOfWork) -> RuleSetVersionOut:
        commands.publish_rule_set_version(uow, version_id)
        return _version(uow, version_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.get(
    "/rule-set-versions/{version_id}/rules",
    operation_id="rule_set_version_rules_list",
    response_model=ListOut[RuleOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def rule_set_version_rules_list(
    version_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[RuleOut]:
    """The rules of a version; sort ``rule_key`` (default), ``priority`` or ``id``."""
    result, items = queries.list_rules(
        ctx,
        version_id,
        page=lambda session, statement: paginate(session, statement, RULE_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[RuleOut](
        items=[RuleOut.model_validate(item) for item in items], next_cursor=result.next_cursor
    )


_REPLACED: Final[dict[int | str, dict[str, Any]]] = {
    200: {"model": RuleOut, "description": "The rule with the same rule_key was replaced."}
}


@router.post(
    "/rule-set-versions/{version_id}/rules",
    operation_id="rule_set_version_rules_upsert",
    status_code=201,
    response_model=RuleOut,
    responses={
        **_REPLACED,
        **problem_responses(
            *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-frozen"
        ),
    },
)
def rule_set_version_rules_upsert(
    version_id: uuid.UUID,
    body: RuleIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a rule (201) or replace the rule with the same ``rule_key`` (200) while the version
    is DRAFT or TESTED."""
    replacing = queries.rule_key_exists(cmd.ctx, version_id, body.rule_key)

    def handle(uow: UnitOfWork) -> RuleOut:
        rule_id, _ = commands.upsert_rule(
            uow,
            version_id,
            rule_key=body.rule_key,
            priority=body.priority,
            conditions=[condition.model_dump() for condition in body.conditions],
            outputs=body.outputs,
            description=body.description,
        )
        return RuleOut.model_validate(queries.rule_out(uow.session, rule_id))

    return run_command(cmd, deps, handle, status_code=200 if replacing else 201)


@router.delete(
    "/rule-set-versions/{version_id}/rules/{rule_id}",
    operation_id="rule_set_version_rules_delete",
    status_code=204,
    response_class=Response,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-frozen"
    ),
)
def rule_set_version_rules_delete(
    version_id: uuid.UUID,
    rule_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Delete a rule of a DRAFT or TESTED version."""
    return run_command(
        cmd, deps, lambda uow: commands.delete_rule(uow, version_id, rule_id), status_code=204
    )


@router.get(
    "/rule-set-versions/{version_id}/test-cases",
    operation_id="rule_set_version_test_cases_list",
    response_model=ListOut[ConfigTestCaseOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def rule_set_version_test_cases_list(
    version_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[ConfigTestCaseOut]:
    """The example cases of a version; sort ``id`` (default) or ``name``."""
    result, items = queries.list_rule_test_cases(
        ctx,
        version_id,
        page=lambda session, statement: paginate(session, statement, TEST_CASE_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[ConfigTestCaseOut](
        items=[ConfigTestCaseOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/rule-set-versions/{version_id}/test-cases",
    operation_id="rule_set_version_test_cases_create",
    status_code=201,
    response_model=ConfigTestCaseOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-frozen"
    ),
)
def rule_set_version_test_cases_create(
    version_id: uuid.UUID,
    body: RuleTestCaseIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Add an example case to a DRAFT or TESTED version."""

    def handle(uow: UnitOfWork) -> ConfigTestCaseOut:
        case_id = commands.create_config_test_case(
            uow,
            subject_type=rule_sets.SUBJECT_TYPE,
            subject_id=version_id,
            name=body.name,
            facts=body.input,
            expected_output=body.expected_output,
        )
        return ConfigTestCaseOut.model_validate(queries.case_out(uow.session, case_id))

    return run_command(cmd, deps, handle, status_code=201)
