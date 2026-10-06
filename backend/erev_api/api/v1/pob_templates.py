"""API-R-24 POB templates: obligation templates, their versions, outputs and lifecycle.

04 §15.3 API-R-24, T-REF-22, T-REF-23, API-C-08, API-C-09, API-C-13, §16.2 API-S-VersionSummary,
§16.14 list additions; PRD SM-04, BR-POL-01; SCREENS §11.2; BUILD_SPEC RFD-10. Reads need
``config.read``; authoring and the lifecycle commands need ``config.author``. A version's outputs
change only while it is DRAFT or TESTED (DB-04); its example cases are written through API-R-57;
approval of the submitted version publishes it (``config.approve``, API-R-09).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Response
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
from erev_api.db.tables import pob_template, pob_template_version
from erev_api.domain.policies import commands, queries
from erev_api.enums import ConfigStatus
from erev_api.schemas.common import ListOut
from erev_api.schemas.pob_templates import (
    PobTemplateIn,
    PobTemplateOut,
    PobTemplateVersionIn,
    PobTemplateVersionOut,
    PobTemplateVersionSubmitIn,
    PobTemplateVersionUpdateIn,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-24 POB templates"
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
_VERSION_MEMBERS: Final = frozenset({"effective_from", "source_version_id"})
_LATEST: Final = pob_template_version.alias("latest_version")
# The status filter of `GET /pob-templates` reads the status of the template's highest version_no.
LATEST_STATUS: Final = (
    select(_LATEST.c.status)
    .where(
        _LATEST.c.tenant_id == pob_template.c.tenant_id,
        _LATEST.c.pob_template_id == pob_template.c.id,
    )
    .order_by(_LATEST.c.version_no.desc())
    .limit(1)
    .scalar_subquery()
)
TEMPLATE_LIST: Final = ListSpec(
    resource="pob-templates",
    sort_keys={"id": pob_template.c.id, "code": pob_template.c.code, "name": pob_template.c.name},
    default_sort="code",
    filters={
        "status": FilterSpec(name="status", column=LATEST_STATUS, kind="exact", choices=_STATUSES),
    },
    search_columns=(pob_template.c.code, pob_template.c.name),
)
VERSION_LIST: Final = ListSpec(
    resource="pob-template-versions",
    sort_keys={"id": pob_template_version.c.id, "version_no": pob_template_version.c.version_no},
    default_sort="-version_no",
    filters={
        "status": FilterSpec(
            name="status", column=pob_template_version.c.status, kind="exact", choices=_STATUSES
        ),
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _etag(out: PobTemplateOut | PobTemplateVersionOut) -> str:
    """API-C-08: templates are IM-M and versions IM-P, so the ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _version(uow: UnitOfWork, version_id: uuid.UUID) -> PobTemplateVersionOut:
    """API-S-PobTemplateVersion in the command's transaction."""
    return PobTemplateVersionOut.model_validate(
        queries.pob_template_version_out(uow.session, version_id)
    )


def _outputs(body: PobTemplateVersionIn | PobTemplateVersionUpdateIn) -> dict[str, Any]:
    """The output members the request sets, explicit nulls included."""
    return body.model_dump(include=set(body.model_fields_set) - _VERSION_MEMBERS)


@router.get(
    "/pob-templates",
    operation_id="pob_templates_list",
    response_model=ListOut[PobTemplateOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def pob_templates_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[
        list[ConfigStatus] | None, Query(description="Status of the template's latest version")
    ] = None,
) -> ListOut[PobTemplateOut]:
    """Obligation templates with ``current_version`` and ``latest_version``; ``q`` searches code and
    name; sort ``code`` (default), ``name`` or ``id``."""
    result, items = queries.list_pob_templates(
        ctx, page=lambda session, statement: paginate(session, statement, TEMPLATE_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[PobTemplateOut](
        items=[PobTemplateOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/pob-templates",
    operation_id="pob_templates_create",
    status_code=201,
    response_model=PobTemplateOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def pob_templates_create(
    body: PobTemplateIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create an obligation template; its outputs live on its versions."""

    def handle(uow: UnitOfWork) -> PobTemplateOut:
        template_id = commands.create_pob_template(
            uow, code=body.code, name=body.name, description=body.description
        )
        return PobTemplateOut.model_validate(queries.pob_template_out(uow.session, template_id))

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/pob-templates/{out.id}",
        etag=_etag,
    )


@router.get(
    "/pob-templates/{template_id}",
    operation_id="pob_templates_get",
    response_model=PobTemplateOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def pob_templates_get(
    template_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
) -> PobTemplateOut:
    out = PobTemplateOut.model_validate(queries.get_pob_template(ctx, template_id))
    response.headers["ETag"] = _etag(out)
    return out


@router.get(
    "/pob-templates/{template_id}/versions",
    operation_id="pob_template_versions_list",
    response_model=ListOut[PobTemplateVersionOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def pob_template_versions_list(
    template_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[list[ConfigStatus] | None, Query()] = None,
) -> ListOut[PobTemplateVersionOut]:
    """Every version of a template; sort ``version_no`` (default ``-version_no``) or ``id``."""
    result, items = queries.list_pob_template_versions(
        ctx,
        template_id,
        page=lambda session, statement: paginate(session, statement, VERSION_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[PobTemplateVersionOut](
        items=[PobTemplateVersionOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/pob-templates/{template_id}/versions",
    operation_id="pob_template_versions_create",
    status_code=201,
    response_model=PobTemplateVersionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def pob_template_versions_create(
    template_id: uuid.UUID,
    body: PobTemplateVersionIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Start the next version as DRAFT with its outputs, optionally copying an earlier version's
    outputs and example cases; the outputs the request sets replace the copied ones."""
    outputs = _outputs(body)

    def handle(uow: UnitOfWork) -> PobTemplateVersionOut:
        version_id = commands.create_pob_template_version(
            uow,
            template_id,
            changes=outputs,
            effective_from=body.effective_from,
            source_version_id=body.source_version_id,
        )
        return _version(uow, version_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/pob-template-versions/{out.id}",
        etag=_etag,
    )


@router.get(
    "/pob-template-versions/{version_id}",
    operation_id="pob_template_versions_get",
    response_model=PobTemplateVersionOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def pob_template_versions_get(
    version_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
) -> PobTemplateVersionOut:
    out = PobTemplateVersionOut.model_validate(queries.get_pob_template_version(ctx, version_id))
    response.headers["ETag"] = _etag(out)
    return out


@router.patch(
    "/pob-template-versions/{version_id}",
    operation_id="pob_template_versions_update",
    response_model=PobTemplateVersionOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "not-found",
        "invalid-transition",
        "configuration-frozen",
        "precondition-failed",
        "precondition-required",
    ),
)
def pob_template_versions_update(
    version_id: uuid.UUID,
    body: PobTemplateVersionUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change the outputs or effective date of a DRAFT or TESTED version (``If-Match`` required)."""
    outputs = _outputs(body)
    effective = (
        {"effective_from": body.effective_from} if "effective_from" in body.model_fields_set else {}
    )

    def handle(uow: UnitOfWork) -> PobTemplateVersionOut:
        commands.update_pob_template_version(
            uow,
            version_id,
            changes={**outputs, **effective},
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return _version(uow, version_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/pob-template-versions/{version_id}/test",
    operation_id="pob_template_versions_test",
    response_model=PobTemplateVersionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def pob_template_versions_test(
    version_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Run the example cases through stage 03 ``build_lines``; a DRAFT version whose cases all pass
    is TESTED (REQ-POL-003)."""

    def handle(uow: UnitOfWork) -> PobTemplateVersionOut:
        commands.run_pob_template_version_tests(uow, version_id)
        return _version(uow, version_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/pob-template-versions/{version_id}/submit",
    operation_id="pob_template_versions_submit",
    response_model=PobTemplateVersionOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-overlap"
    ),
)
def pob_template_versions_submit(
    version_id: uuid.UUID,
    body: PobTemplateVersionSubmitIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Submit a TESTED version for approval with its simulation report (PRD BR-POL-01)."""

    def handle(uow: UnitOfWork) -> PobTemplateVersionOut:
        commands.submit_pob_template_version(uow, version_id, comment=body.comment)
        return _version(uow, version_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/pob-template-versions/{version_id}/publish",
    operation_id="pob_template_versions_publish",
    response_model=PobTemplateVersionOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-overlap"
    ),
)
def pob_template_versions_publish(
    version_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Publish a version left APPROVED; approval publishes a version itself (04 §16.5)."""

    def handle(uow: UnitOfWork) -> PobTemplateVersionOut:
        commands.publish_pob_template_version(uow, version_id)
        return _version(uow, version_id)

    return run_command(cmd, deps, handle, etag=_etag)
