"""API-R-18 Calendars and periods: the tenant's close tasks (``/close-checklist-templates``).

04 §15.3 API-R-18 (rev 1.3), T-CLS-02; BUILD_SPEC CLO-4, BS4-D-06. Reads need ``config.read``;
``POST`` and ``PATCH`` need ``settings.manage`` for all entities — a template applies to every
entity's close (04 API-C-03 rev 1.219) — and ``PATCH`` requires ``If-Match``
(``"r<row_version>"``, API-C-08). The system gates are listed with the tenant's tasks in sequence
order; a system gate changes only in its owner role and due offset.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Response
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
from erev_api.db.session import tenant_session
from erev_api.db.tables import close_checklist_template
from erev_api.domain.close import commands as close_commands
from erev_api.enums import ChecklistGateKind
from erev_api.schemas.close import (
    CloseChecklistTemplateCreateIn,
    CloseChecklistTemplateOut,
    CloseChecklistTemplateUpdateIn,
)
from erev_api.schemas.common import ListOut
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-18 Calendars and periods"
READ_PERMISSION: Final = "config.read"
WRITE_PERMISSION: Final = "settings.manage"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden", "validation-failed")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "mfa-required",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
TEMPLATE_LIST: Final = ListSpec(
    resource="close-checklist-templates",
    sort_keys={
        "id": close_checklist_template.c.id,
        "sequence": close_checklist_template.c.sequence,
    },
    default_sort="sequence",
    filters={
        "gate_kind": FilterSpec(
            name="gate_kind",
            column=close_checklist_template.c.gate_kind,
            kind="in",
            choices=frozenset(member.value for member in ChecklistGateKind),
        ),
        "is_active": FilterSpec(
            name="is_active", column=close_checklist_template.c.is_active, kind="bool"
        ),
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def template_etag(out: CloseChecklistTemplateOut) -> str:
    """API-C-08: ``"r<row_version>"``."""
    return row_etag(out.row_version)


@router.get(
    "/close-checklist-templates",
    operation_id="close_checklist_templates_list",
    response_model=ListOut[CloseChecklistTemplateOut],
    responses=problem_responses(*_READ_PROBLEMS),
)
def close_checklist_templates_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[CloseChecklistTemplateOut]:
    """The system gates and the tenant's close tasks; sort ``sequence`` (default) or ``id``; filters
    ``gate_kind`` and ``is_active``."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = paginate(session, select(*close_commands.TEMPLATE_COLUMNS), TEMPLATE_LIST, params)
        items = [
            CloseChecklistTemplateOut.model_validate(
                {
                    **dict(row),
                    "gate_kind": str(getattr(row["gate_kind"], "value", row["gate_kind"])),
                }
            )
            for row in result.items
        ]
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[CloseChecklistTemplateOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/close-checklist-templates",
    operation_id="close_checklist_templates_create",
    status_code=201,
    response_model=CloseChecklistTemplateOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def close_checklist_templates_create(
    body: CloseChecklistTemplateCreateIn,
    cmd: Annotated[CommandContext, Depends(command(WRITE_PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Add a manual close task after every gate and task (REQ-CLS-021)."""

    def handle(uow: UnitOfWork) -> CloseChecklistTemplateOut:
        return close_commands.create_close_task(uow, body=body)

    return run_command(cmd, deps, handle, status_code=201, etag=template_etag)


@router.patch(
    "/close-checklist-templates/{template_id}",
    operation_id="close_checklist_templates_update",
    response_model=CloseChecklistTemplateOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "precondition-failed", "precondition-required"
    ),
)
def close_checklist_templates_update(
    template_id: uuid.UUID,
    body: CloseChecklistTemplateUpdateIn,
    cmd: Annotated[
        CommandContext, Depends(command(WRITE_PERMISSION, precondition="row", all_entities=True))
    ],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change a close task, or a system gate's owner role and due offset; ``If-Match`` required."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> CloseChecklistTemplateOut:
        return close_commands.update_close_task(
            uow,
            template_id=template_id,
            changes=changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle, etag=template_etag)
