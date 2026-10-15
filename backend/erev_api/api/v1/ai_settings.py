"""AI-scoped policy authoring for workspace administrators.

These routes retain the normal registry lifecycle. They do not publish or enable AI;
publication still requires the approval engine and the independent-admin safeguard.
"""

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Response

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
from erev_api.auth.dependencies import require_all_entities
from erev_api.auth.principal import RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import registry_version
from erev_api.domain.ai import configuration
from erev_api.domain.ai.settings import AISettingsRefused, load_settings
from erev_api.domain.platform.jobs import job_out_of
from erev_api.domain.policies import registry_versions
from erev_api.enums import ConfigStatus, RegistryCategory, RegistryScope
from erev_api.problems import Problem
from erev_api.registry.versions import BASIS_PREDECESSOR
from erev_api.schemas.ai_settings import (
    AISettingsStatusOut,
    AISettingsValuesOut,
    AISettingsVersionIn,
    AISettingsVersionUpdateIn,
)
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.policies import PolicyCommentIn, PolicyOut, PolicyTestIn
from erev_api.uow import UnitOfWork

PERMISSION: Final = "settings.manage"
PATH: Final = "/ai/settings/versions"
PROBLEMS: Final = (
    "unauthenticated",
    "session-expired",
    "forbidden",
    "mfa-required",
    "not-found",
    "validation-failed",
    "invalid-transition",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
router = APIRouter(prefix=API_PREFIX, tags=["API-R-47 AI settings"], route_class=GuardedRoute)


@router.get(
    "/ai/settings",
    operation_id="ai_settings_status",
    response_model=AISettingsStatusOut,
    responses=problem_responses(*PROBLEMS, "ai-disabled"),
)
def status(
    ctx: Annotated[RequestContext, Depends(require_all_entities(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> AISettingsStatusOut:
    """Read availability even while disabled; never instantiate or call a provider."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        try:
            effective = load_settings(
                session,
                tenant_id=ctx.principal.tenant_id,
                now=ctx.now,
                platform_kill_switch=deps.settings.ai_kill_switch,
            )
        except AISettingsRefused:
            raise Problem("ai-disabled") from None
    return AISettingsStatusOut(
        provider=deps.settings.ai_provider,
        enabled=effective.enabled,
        registry_enabled=effective.registry_enabled,
        tenant_disabled_at=effective.tenant_disabled_at,
        platform_disabled=effective.platform_disabled,
        workspace_active=effective.workspace_active,
        model=effective.model,
        monthly_token_budget=effective.monthly_token_budget,
        send_contract_text=effective.send_contract_text,
        redact_contact_details=effective.redact_contact_details,
    )


@router.get(
    "/ai/settings/values",
    operation_id="ai_settings_values",
    response_model=AISettingsValuesOut,
    responses=problem_responses(*PROBLEMS),
)
def values(
    ctx: Annotated[RequestContext, Depends(require_all_entities(PERMISSION))],
) -> AISettingsValuesOut:
    """Read AI form values and defaults without general configuration read access."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        current, defaults = configuration.form_values(session, known_at=ctx.now)
    return AISettingsValuesOut(values=current, defaults=defaults)


VERSION_LIST: Final = ListSpec(
    resource="ai-settings-versions",
    sort_keys={
        "id": registry_version.c.id,
        "version_no": registry_version.c.version_no,
        "created_at": registry_version.c.created_at,
    },
    default_sort="-version_no",
    filters={
        "status": FilterSpec(
            name="status",
            column=registry_version.c.status,
            kind="exact",
            choices=frozenset(status.value for status in ConfigStatus),
        ),
    },
)


@router.get(
    PATH,
    operation_id="ai_settings_versions_list",
    response_model=ListOut[PolicyOut],
    responses=problem_responses(*PROBLEMS),
)
def list_versions(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities(PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> ListOut[PolicyOut]:
    """Discover tenant AI versions without access to accounting policies."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        statement = registry_versions.policy_select().where(*configuration.version_scope())
        result = paginate(session, statement, VERSION_LIST, params)
        items = registry_versions.policy_outs(
            session, result.items, files=deps.files, keyring=deps.keyring
        )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[PolicyOut](
        items=[PolicyOut.model_validate(item) for item in items], next_cursor=result.next_cursor
    )


def _out(uow: UnitOfWork, version_id: UUID) -> PolicyOut:
    return PolicyOut.model_validate(
        registry_versions.policy_out(uow.session, version_id, files=uow.files, keyring=uow.keyring)
    )


def _etag(out: PolicyOut) -> str:
    return row_etag(out.row_version)


@router.post(
    PATH,
    operation_id="ai_settings_versions_create",
    status_code=201,
    response_model=PolicyOut,
    responses=problem_responses(*PROBLEMS),
)
def create(
    body: AISettingsVersionIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    def handle(uow: UnitOfWork) -> PolicyOut:
        version_id = registry_versions.create_policy(
            uow,
            category=RegistryCategory.AI,
            scope=RegistryScope.TENANT,
            entity_code=None,
            book_code=None,
            values=body.values,
            unset=body.unset,
            basis=body.basis or BASIS_PREDECESSOR,
            effective_from=None,
        )
        return _out(uow, version_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}{PATH}/{out.id}",
        etag=_etag,
    )


@router.get(
    PATH + "/{version_id}",
    operation_id="ai_settings_versions_get",
    response_model=PolicyOut,
    responses=problem_responses(*PROBLEMS),
)
def get(
    version_id: UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities(PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> PolicyOut:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        configuration.require_version(session, version_id)
        out = PolicyOut.model_validate(
            registry_versions.policy_out(
                session,
                version_id,
                files=deps.files,
                keyring=deps.keyring,
            )
        )
    response.headers["ETag"] = _etag(out)
    return out


@router.patch(
    PATH + "/{version_id}",
    operation_id="ai_settings_versions_update",
    response_model=PolicyOut,
    responses=problem_responses(
        *PROBLEMS, "precondition-failed", "precondition-required", "configuration-frozen"
    ),
)
def update(
    version_id: UUID,
    body: AISettingsVersionUpdateIn,
    cmd: Annotated[
        CommandContext, Depends(command(PERMISSION, precondition="row", all_entities=True))
    ],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    def handle(uow: UnitOfWork) -> PolicyOut:
        configuration.require_version(uow.session, version_id)
        registry_versions.update_policy(
            uow,
            version_id,
            changes=body.model_dump(exclude_unset=True, exclude_none=True),
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return _out(uow, version_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    PATH + "/{version_id}/test",
    operation_id="ai_settings_versions_test",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(*PROBLEMS),
)
def test_version(
    version_id: UUID,
    body: PolicyTestIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    def handle(uow: UnitOfWork) -> JobOut:
        configuration.require_version(uow.session, version_id)
        return job_out_of(
            uow.session,
            registry_versions.request_test(
                uow,
                version_id,
                run_simulation=body.run_simulation,
            ),
        )

    return run_command(
        cmd, deps, handle, status_code=202, location=lambda job: f"{API_PREFIX}/jobs/{job.id}"
    )


@router.post(
    PATH + "/{version_id}/submit",
    operation_id="ai_settings_versions_submit",
    response_model=PolicyOut,
    responses=problem_responses(*PROBLEMS),
)
def submit(
    version_id: UUID,
    body: PolicyCommentIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    def handle(uow: UnitOfWork) -> PolicyOut:
        configuration.require_version(uow.session, version_id)
        registry_versions.submit_policy(uow, version_id, comment=body.comment)
        return _out(uow, version_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    PATH + "/{version_id}/withdraw",
    operation_id="ai_settings_versions_withdraw",
    response_model=PolicyOut,
    responses=problem_responses(*PROBLEMS),
)
def withdraw(
    version_id: UUID,
    body: PolicyCommentIn,
    cmd: Annotated[CommandContext, Depends(command(PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    def handle(uow: UnitOfWork) -> PolicyOut:
        configuration.require_version(uow.session, version_id)
        registry_versions.withdraw_policy(uow, version_id, comment=body.comment)
        return _out(uow, version_id)

    return run_command(cmd, deps, handle, etag=_etag)
