"""API-R-20 Chart of accounts and mapping: GL accounts, account mapping versions and resolution.

04 §15.3 API-R-20, T-REF-13, T-REF-14, T-REF-15, API-C-08, API-C-09, §16.14; SCREENS_B §9.5 and
SCREENS §9.6 data bindings; BUILD_SPEC RFD-6, RFD-7. Reads need ``config.read``; creating or
changing an account or a mapping version needs ``config.author``, and ``PATCH`` needs ``If-Match``.
Rules change only while their version is DRAFT or TESTED (DB-04); approval of the submitted version
publishes it (``config.approve``, API-R-09).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Response
from pydantic import AwareDatetime

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
from erev_api.clock import Clock, get_clock
from erev_api.db.tables import account_mapping_rule, account_mapping_version, gl_account
from erev_api.domain.reference import commands, queries
from erev_api.enums import AccountRole, AccountType, BookCode, ClearingPurpose, ConfigStatus
from erev_api.schemas.account_mappings import (
    AccountMappingIn,
    AccountMappingOut,
    AccountMappingRuleIn,
    AccountMappingRuleOut,
    AccountMappingSubmitIn,
    AccountMappingUpdateIn,
    AccountResolutionOut,
)
from erev_api.schemas.accounts import GlAccountIn, GlAccountOut, GlAccountUpdateIn
from erev_api.schemas.common import ListOut
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-20 Chart of accounts and mapping"
READ_PERMISSION: Final = "config.read"
AUTHOR_PERMISSION: Final = "config.author"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
GL_ACCOUNT_LIST: Final = ListSpec(
    resource="gl-accounts",
    sort_keys={
        "id": gl_account.c.id,
        "code": gl_account.c.code,
        "name": gl_account.c.name,
    },
    default_sort="code",
    filters={
        "account_type": FilterSpec(
            name="account_type",
            column=gl_account.c.account_type,
            kind="exact",
            choices=frozenset(member.value for member in AccountType),
        ),
        "is_active": FilterSpec(name="is_active", column=gl_account.c.is_active, kind="bool"),
    },
    search_columns=(gl_account.c.code, gl_account.c.name),
)
MAPPING_LIST: Final = ListSpec(
    resource="account-mappings",
    sort_keys={
        "id": account_mapping_version.c.id,
        "version_no": account_mapping_version.c.version_no,
    },
    default_sort="-version_no",
    filters={
        "status": FilterSpec(
            name="status",
            column=account_mapping_version.c.status,
            kind="exact",
            choices=frozenset(status.value for status in ConfigStatus),
        ),
    },
    search_columns=(account_mapping_version.c.name,),
)
MAPPING_RULE_LIST: Final = ListSpec(
    resource="account-mapping-rules",
    sort_keys={
        "id": account_mapping_rule.c.id,
        "priority": account_mapping_rule.c.priority,
        "specificity": account_mapping_rule.c.specificity,
    },
    default_sort="id",
    filters={
        "account_role": FilterSpec(
            name="account_role",
            column=account_mapping_rule.c.account_role,
            kind="exact",
            choices=frozenset(role.value for role in AccountRole),
        ),
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def gl_account_etag(out: GlAccountOut) -> str:
    """API-C-08: an account is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def gl_account_location(out: GlAccountOut) -> str:
    return f"{API_PREFIX}/gl-accounts/{out.id}"


@router.get(
    "/gl-accounts",
    operation_id="gl_accounts_list",
    response_model=ListOut[GlAccountOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def gl_accounts_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    account_type: Annotated[AccountType | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> ListOut[GlAccountOut]:
    """The tenant's GL accounts; sort ``code`` (default), ``name`` or ``id``; ``q`` searches code
    and name (SCREENS_B RT-78 ``f.account_type``, ``q``)."""
    result = queries.list_gl_accounts(
        ctx, page=lambda session, statement: paginate(session, statement, GL_ACCOUNT_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[GlAccountOut](
        items=[GlAccountOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/gl-accounts",
    operation_id="gl_accounts_create",
    status_code=201,
    response_model=GlAccountOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def gl_accounts_create(
    body: GlAccountIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a GL account; its code is unique in the workspace."""

    def handle(uow: UnitOfWork) -> GlAccountOut:
        return commands.create_gl_account(uow, body=body)

    return run_command(
        cmd, deps, handle, status_code=201, location=gl_account_location, etag=gl_account_etag
    )


@router.get(
    "/gl-accounts/{account_id}",
    operation_id="gl_accounts_get",
    response_model=GlAccountOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def gl_accounts_get(
    account_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
) -> GlAccountOut:
    """One GL account with its ``ETag``."""
    out = GlAccountOut.model_validate(queries.get_gl_account(ctx, account_id))
    response.headers["ETag"] = gl_account_etag(out)
    return out


@router.patch(
    "/gl-accounts/{account_id}",
    operation_id="gl_accounts_update",
    response_model=GlAccountOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "precondition-failed", "precondition-required"
    ),
)
def gl_accounts_update(
    account_id: uuid.UUID,
    body: GlAccountUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR_PERMISSION, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Rename an account, change its type, normal balance, entities or required dimensions, or
    (de)activate it; the code does not change."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> GlAccountOut:
        return commands.update_gl_account(
            uow,
            account_id=account_id,
            changes=changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )

    return run_command(cmd, deps, handle, etag=gl_account_etag)


def mapping_etag(out: AccountMappingOut) -> str:
    """API-C-08: a mapping version is IM-P, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _mapping_out(uow: UnitOfWork, version_id: uuid.UUID) -> AccountMappingOut:
    """The mapping version in the command's transaction."""
    return AccountMappingOut.model_validate(
        queries.account_mapping_version_row(uow.session, version_id)
    )


# Declared before `/account-mappings/{version_id}`, whose uuid parameter would refuse "resolve".
@router.get(
    "/account-mappings/resolve",
    operation_id="account_mappings_resolve",
    response_model=AccountResolutionOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "unmapped-account-role"),
)
def account_mappings_resolve(
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    clock: Annotated[Clock, Depends(get_clock)],
    role: Annotated[AccountRole, Query()],
    clearing_purpose: Annotated[ClearingPurpose | None, Query()] = None,
    entity: Annotated[str | None, Query(description="Entity code or id")] = None,
    book: Annotated[BookCode | None, Query()] = None,
    product: Annotated[str | None, Query(description="Product code or id")] = None,
    revenue_category: Annotated[str | None, Query()] = None,
    known_at: Annotated[AwareDatetime | None, Query(description="Default: now")] = None,
) -> AccountResolutionOut:
    """The GL account of a role from the PUBLISHED mapping version effective at ``known_at``: the
    most specific matching rule, then the highest priority (T-REF-15 step 3)."""
    result = queries.resolve_account_mapping(
        ctx,
        role=role,
        clearing_purpose=clearing_purpose,
        entity=entity,
        book=book,
        product_ref=product,
        revenue_category=revenue_category,
        known_at=clock.now() if known_at is None else known_at,
    )
    return AccountResolutionOut.model_validate(result)


@router.get(
    "/account-mappings",
    operation_id="account_mappings_list",
    response_model=ListOut[AccountMappingOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def account_mappings_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[list[ConfigStatus] | None, Query()] = None,
) -> ListOut[AccountMappingOut]:
    """Every mapping version with ``rule_count``; ``q`` searches the name; sort ``version_no``
    (default ``-version_no``) or ``id``."""
    result = queries.list_account_mapping_versions(
        ctx, page=lambda session, statement: paginate(session, statement, MAPPING_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[AccountMappingOut](
        items=[
            AccountMappingOut.model_validate(queries.account_mapping_out(item))
            for item in result.items
        ],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/account-mappings",
    operation_id="account_mappings_create",
    status_code=201,
    response_model=AccountMappingOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "invalid-transition"),
)
def account_mappings_create(
    body: AccountMappingIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Start the next mapping version as DRAFT, optionally copying a version's rules."""

    def handle(uow: UnitOfWork) -> AccountMappingOut:
        return _mapping_out(uow, commands.create_account_mapping_version(uow, body=body))

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/account-mappings/{out.id}",
        etag=mapping_etag,
    )


@router.get(
    "/account-mappings/{version_id}",
    operation_id="account_mappings_get",
    response_model=AccountMappingOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def account_mappings_get(
    version_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
) -> AccountMappingOut:
    """One mapping version with its ``ETag``."""
    out = AccountMappingOut.model_validate(queries.get_account_mapping_version(ctx, version_id))
    response.headers["ETag"] = mapping_etag(out)
    return out


@router.patch(
    "/account-mappings/{version_id}",
    operation_id="account_mappings_update",
    response_model=AccountMappingOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "not-found",
        "invalid-transition",
        "configuration-frozen",
        "precondition-failed",
        "precondition-required",
    ),
)
def account_mappings_update(
    version_id: uuid.UUID,
    body: AccountMappingUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR_PERMISSION, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change the name, notes or effective date of a DRAFT or TESTED version."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> AccountMappingOut:
        commands.update_account_mapping_version(
            uow,
            version_id,
            changes=changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return _mapping_out(uow, version_id)

    return run_command(cmd, deps, handle, etag=mapping_etag)


@router.get(
    "/account-mappings/{version_id}/rules",
    operation_id="account_mapping_rules_list",
    response_model=ListOut[AccountMappingRuleOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def account_mapping_rules_list(
    version_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    account_role: Annotated[AccountRole | None, Query()] = None,
) -> ListOut[AccountMappingRuleOut]:
    """The rules of a version; sort ``id`` (default, creation order), ``priority`` or
    ``specificity``."""
    result, items = queries.list_account_mapping_rules(
        ctx,
        version_id,
        page=lambda session, statement: paginate(session, statement, MAPPING_RULE_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[AccountMappingRuleOut](
        items=[AccountMappingRuleOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/account-mappings/{version_id}/rules",
    operation_id="account_mapping_rules_create",
    status_code=201,
    response_model=AccountMappingRuleOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-frozen"
    ),
)
def account_mapping_rules_create(
    version_id: uuid.UUID,
    body: AccountMappingRuleIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Add a rule to a DRAFT or TESTED version."""

    def handle(uow: UnitOfWork) -> AccountMappingRuleOut:
        rule_id = commands.add_account_mapping_rule(uow, version_id, body=body)
        return AccountMappingRuleOut.model_validate(
            queries.account_mapping_rule_row(uow.session, rule_id)
        )

    return run_command(cmd, deps, handle, status_code=201)


@router.delete(
    "/account-mappings/{version_id}/rules/{rule_id}",
    operation_id="account_mapping_rules_delete",
    status_code=204,
    response_class=Response,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-frozen"
    ),
)
def account_mapping_rules_delete(
    version_id: uuid.UUID,
    rule_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Delete a rule of a DRAFT or TESTED version."""
    return run_command(
        cmd,
        deps,
        lambda uow: commands.delete_account_mapping_rule(uow, version_id, rule_id),
        status_code=204,
    )


@router.post(
    "/account-mappings/{version_id}/test",
    operation_id="account_mappings_test",
    response_model=AccountMappingOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def account_mappings_test(
    version_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Run the publish lint; a DRAFT version whose rules pass becomes TESTED."""

    def handle(uow: UnitOfWork) -> AccountMappingOut:
        commands.run_account_mapping_tests(uow, version_id)
        return _mapping_out(uow, version_id)

    return run_command(cmd, deps, handle, etag=mapping_etag)


@router.post(
    "/account-mappings/{version_id}/submit",
    operation_id="account_mappings_submit",
    response_model=AccountMappingOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-overlap"
    ),
)
def account_mappings_submit(
    version_id: uuid.UUID,
    body: AccountMappingSubmitIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Submit a TESTED version for approval with its simulation report (PRD BR-POL-01)."""

    def handle(uow: UnitOfWork) -> AccountMappingOut:
        commands.submit_account_mapping_version(uow, version_id, comment=body.comment)
        return _mapping_out(uow, version_id)

    return run_command(cmd, deps, handle, etag=mapping_etag)


@router.post(
    "/account-mappings/{version_id}/publish",
    operation_id="account_mappings_publish",
    response_model=AccountMappingOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-overlap"
    ),
)
def account_mappings_publish(
    version_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Publish a version left APPROVED; approval publishes a version itself (04 §16.5)."""

    def handle(uow: UnitOfWork) -> AccountMappingOut:
        commands.publish_account_mapping_version(uow, version_id)
        return _mapping_out(uow, version_id)

    return run_command(cmd, deps, handle, etag=mapping_etag)
