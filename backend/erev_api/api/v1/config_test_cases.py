"""API-R-57 Configuration test cases: example cases of configuration versions.

04 §15.3 API-R-57, T-REF-27, API-C-08, API-C-09, §14.1 DB-04; SCREENS R-30; BUILD_SPEC RFD-5. Reads
need ``config.read`` and writes ``config.author``; a case changes only while its version is DRAFT
or TESTED. Example cases of ``account_mapping_version`` are refused until an item defines their
shape (XR-12; L2-1-Q-10); ``pob_template_version`` cases follow RFD-10.
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
from erev_api.db.tables import rule_test_case
from erev_api.domain.policies import commands, queries
from erev_api.schemas.common import ListOut
from erev_api.schemas.rule_sets import (
    ConfigSubjectType,
    ConfigTestCaseIn,
    ConfigTestCaseOut,
    ConfigTestCaseUpdateIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-57 Configuration test cases"
READ: Final = "config.read"
AUTHOR: Final = "config.author"
SUBJECT_TYPES: Final = frozenset(
    {"rule_set_version", "pob_template_version", "account_mapping_version", "registry_version"}
)
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
    "not-found",
    "invalid-transition",
    "configuration-frozen",
)
_PRECONDITION_PROBLEMS: Final = ("precondition-failed", "precondition-required")
CASE_LIST: Final = ListSpec(
    resource="config-test-cases",
    sort_keys={"id": rule_test_case.c.id, "name": rule_test_case.c.name},
    default_sort="id",
    filters={
        "subject_type": FilterSpec(
            name="subject_type",
            column=rule_test_case.c.subject_type,
            kind="exact",
            choices=SUBJECT_TYPES,
        ),
        "subject_id": FilterSpec(
            name="subject_id", column=rule_test_case.c.subject_id, kind="exact"
        ),
    },
    search_columns=(rule_test_case.c.name,),
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _etag(out: ConfigTestCaseOut) -> str:
    """API-C-08: ``"r<row_version>"``."""
    return row_etag(out.row_version)


@router.get(
    "/config-test-cases",
    operation_id="config_test_cases_list",
    response_model=ListOut[ConfigTestCaseOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def config_test_cases_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
    params: Annotated[ListParams, Depends(list_params)],
    subject_type: Annotated[ConfigSubjectType | None, Query()] = None,
    subject_id: Annotated[uuid.UUID | None, Query()] = None,
) -> ListOut[ConfigTestCaseOut]:
    """Example cases; filter by ``subject_type`` and ``subject_id``; sort ``id`` or ``name``."""
    result, items = queries.list_config_test_cases(
        ctx, page=lambda session, statement: paginate(session, statement, CASE_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[ConfigTestCaseOut](
        items=[ConfigTestCaseOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/config-test-cases",
    operation_id="config_test_cases_create",
    status_code=201,
    response_model=ConfigTestCaseOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def config_test_cases_create(
    body: ConfigTestCaseIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Add an example case to a DRAFT or TESTED configuration version."""

    def handle(uow: UnitOfWork) -> ConfigTestCaseOut:
        case_id = commands.create_config_test_case(
            uow,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            name=body.name,
            facts=body.input,
            expected_output=body.expected_output,
        )
        return ConfigTestCaseOut.model_validate(queries.case_out(uow.session, case_id))

    return run_command(cmd, deps, handle, status_code=201, etag=_etag)


@router.patch(
    "/config-test-cases/{test_case_id}",
    operation_id="config_test_cases_update",
    response_model=ConfigTestCaseOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, *_PRECONDITION_PROBLEMS),
)
def config_test_cases_update(
    test_case_id: uuid.UUID,
    body: ConfigTestCaseUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change the name, facts or expected evaluation of a case (``If-Match`` required)."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> ConfigTestCaseOut:
        commands.update_config_test_case(
            uow,
            test_case_id,
            changes=changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return ConfigTestCaseOut.model_validate(queries.case_out(uow.session, test_case_id))

    return run_command(cmd, deps, handle, etag=_etag)


@router.delete(
    "/config-test-cases/{test_case_id}",
    operation_id="config_test_cases_delete",
    status_code=204,
    response_class=Response,
    responses=problem_responses(*_COMMAND_PROBLEMS, *_PRECONDITION_PROBLEMS),
)
def config_test_cases_delete(
    test_case_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Delete a case of a DRAFT or TESTED version (``If-Match`` required)."""
    return run_command(
        cmd,
        deps,
        lambda uow: commands.delete_config_test_case(
            uow,
            test_case_id,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        ),
        status_code=204,
    )
