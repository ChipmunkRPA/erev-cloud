"""API-R-13 Policies (registry): the parameter catalogue, registry versions and their lifecycle, the
legacy-parity preset and resolution.

04 §15.3 API-R-13, §16.5, T-PLT-31, T-PLT-32, API-C-08, API-C-09, API-C-12; PRD SM-04, BR-POL-01,
BR-POL-02; BUILD_SPEC RFD-11, BS3-D-04, BS3-D-17. Reads need ``config.read``; authoring and the
lifecycle commands need ``config.author`` FOR THE VERSION'S SCOPE — for all entities when the
version is a TENANT or BOOK version, for its entity when it is an ENTITY version (rev 1.309;
``registry_versions.require_authority``). A caller who does not hold it for all entities is
refused a TENANT or BOOK version 403 by name. An ENTITY version of an entity her
``config.author`` does not name is not read by the command's transaction at all, which runs
under the scope of that permission (04 API-C-03 rev 1.319; ``auth.dependencies.require``): 404
as for an id that names no version, and 422 at a create as for a code that names no entity,
before the command asks — its own 403 by name then answers only a caller no route narrowed.
Approval of a submitted version publishes it (``config.approve`` for the same entities,
API-R-09).
``POST /policies/{id}/test`` answers 202 with API-S-Job and
``Location: /api/v1/jobs/{id}``. The ``/policy-overrides`` routes (BS3-D-04; BUILD_SPEC CTR-15) read
with ``config.read`` and write with ``contract.create``, which the handler checks for the contract's
entity (PRD ACT-55; L4-2-Q-2); approval of a submitted override needs ``contract.approve``.
In release 1.0 the creation is refused by name and stores nothing (04 T-CON-23 rev 1.322;
PRD ERR-102).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Final

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
from erev_api.db.tables import policy_override, registry_version
from erev_api.domain.platform import jobs
from erev_api.domain.policies import overrides, registry_versions
from erev_api.enums import BookCode, ConfigStatus, RegistryCategory, RegistryScope
from erev_api.registry.effective import EFFECTIVE_REGISTRY_PARAMETER
from erev_api.registry.versions import BASIS_PREDECESSOR
from erev_api.schemas.common import JobOut, ListOut
from erev_api.schemas.obligations import (
    PolicyOverrideCommentIn,
    PolicyOverrideIn,
    PolicyOverrideOut,
)
from erev_api.schemas.policies import (
    LegacyParityPresetIn,
    PolicyCommentIn,
    PolicyIn,
    PolicyOut,
    PolicyResolutionOut,
    PolicyTestIn,
    PolicyUpdateIn,
    RegistryParameterOut,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-13 Policies (registry)"
READ: Final = "config.read"
AUTHOR: Final = "config.author"
OVERRIDE_AUTHOR: Final = "contract.create"  # PRD ACT-55 (L4-2-Q-2)
KEY_LENGTH: Final = 200
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
_CATEGORIES: Final = frozenset(category.value for category in RegistryCategory)
# API-R-13 (04 rev 1.59, T-PLT-31 rule 3): sort, filter, search and page the EFFECTIVE relation —
# the latest T-PLT-47 correction of each code over its seed — never the seed table itself.
_EFFECTIVE = EFFECTIVE_REGISTRY_PARAMETER
PARAMETER_LIST: Final = ListSpec(
    resource="registry-parameters",
    sort_keys={"id": _EFFECTIVE.c.code, "code": _EFFECTIVE.c.code},
    default_sort="code",
    filters={
        "category": FilterSpec(
            name="category", column=_EFFECTIVE.c.category, kind="exact", choices=_CATEGORIES
        ),
        "section": FilterSpec(name="section", column=_EFFECTIVE.c.section, kind="exact"),
    },
    search_columns=(_EFFECTIVE.c.code, _EFFECTIVE.c.description),
)
POLICY_LIST: Final = ListSpec(
    resource="policies",
    sort_keys={
        "id": registry_version.c.id,
        "version_no": registry_version.c.version_no,
        "created_at": registry_version.c.created_at,
    },
    default_sort="-version_no",
    filters={
        "category": FilterSpec(
            name="category", column=registry_version.c.category, kind="exact", choices=_CATEGORIES
        ),
        "scope": FilterSpec(
            name="scope",
            column=registry_version.c.scope,
            kind="exact",
            choices=frozenset(scope.value for scope in RegistryScope),
        ),
        "book": FilterSpec(
            name="book",
            column=registry_version.c.book_code,
            kind="exact",
            choices=frozenset(code.value for code in BookCode),
        ),
        "status": FilterSpec(
            name="status",
            column=registry_version.c.status,
            kind="exact",
            choices=frozenset(status.value for status in ConfigStatus),
        ),
    },
    custom_filters=frozenset({"entity"}),
)

POLICY_OVERRIDE_LIST: Final = ListSpec(
    resource="policy-overrides",
    sort_keys={"id": policy_override.c.id, "created_at": policy_override.c.created_at},
    default_sort="-created_at",
    filters={
        "status": FilterSpec(
            name="status",
            column=policy_override.c.status,
            kind="exact",
            choices=frozenset(status.value for status in ConfigStatus),
        ),
        "policy_key": FilterSpec(
            name="policy_key", column=policy_override.c.policy_key, kind="exact"
        ),
    },
    custom_filters=frozenset({"contract"}),
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _etag(out: PolicyOut) -> str:
    """API-C-08: ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _policy(uow: UnitOfWork, version_id: uuid.UUID) -> PolicyOut:
    return PolicyOut.model_validate(
        registry_versions.policy_out(uow.session, version_id, files=uow.files, keyring=uow.keyring)
    )


@router.get(
    "/registry/parameters",
    operation_id="registry_parameters_list",
    response_model=ListOut[RegistryParameterOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def registry_parameters_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[RegistryParameterOut]:
    """The T-PLT-31 catalogue: every non-retired POLICIES §1 parameter and every platform parameter
    (DG-KRN-REG-04); filters ``category``, ``section``; ``q`` over code and description."""
    result, items = registry_versions.list_parameters(
        ctx, page=lambda session, statement: paginate(session, statement, PARAMETER_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[RegistryParameterOut](
        items=[RegistryParameterOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.get(
    "/policies",
    operation_id="policies_list",
    response_model=ListOut[PolicyOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def policies_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
    params: Annotated[ListParams, Depends(list_params)],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
    entity: Annotated[str | None, Query(description="Entity code or id")] = None,
) -> ListOut[PolicyOut]:
    """Registry versions; filters ``category``, ``scope``, ``entity``, ``book``, ``status``; sort
    ``version_no`` (default descending), ``created_at``, ``id``."""
    result, items = registry_versions.list_policies(
        ctx,
        entity_ref=entity,
        page=lambda session, statement: paginate(session, statement, POLICY_LIST, params),
        files=deps.files,
        keyring=deps.keyring,
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[PolicyOut](
        items=[PolicyOut.model_validate(item) for item in items], next_cursor=result.next_cursor
    )


@router.post(
    "/policies",
    operation_id="policies_create",
    status_code=201,
    response_model=PolicyOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "invalid-transition", "policy-level-not-allowed"
    ),
)
def policies_create(
    body: PolicyIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """A DRAFT registry version of one category at one scope; the values are validated now."""

    def handle(uow: UnitOfWork) -> PolicyOut:
        version_id = registry_versions.create_policy(
            uow,
            category=body.category,
            scope=body.scope,
            entity_code=body.entity_code,
            book_code=body.book,
            values=body.values,
            unset=body.unset,
            basis=body.basis or BASIS_PREDECESSOR,
            effective_from=body.effective_from,
        )
        return _policy(uow, version_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/policies/{out.id}",
        etag=_etag,
    )


@router.post(
    "/policies/presets/legacy-parity",
    operation_id="policies_presets_legacy_parity",
    status_code=201,
    response_model=PolicyOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "invalid-transition", "policy-level-not-allowed"
    ),
)
def policies_presets_legacy_parity(
    body: LegacyParityPresetIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """The DRAFT ``LEGACY_PARITY`` version of the tenant accounting policy set (REQ-POL-005)."""

    def handle(uow: UnitOfWork) -> PolicyOut:
        version_id = registry_versions.create_legacy_parity_preset(
            uow, scope=body.scope, entity_code=body.entity_code, book_code=body.book
        )
        return _policy(uow, version_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/policies/{out.id}",
        etag=_etag,
    )


@router.get(
    "/policies/resolve",
    operation_id="policies_resolve",
    response_model=PolicyResolutionOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def policies_resolve(
    ctx: Annotated[RequestContext, Depends(require(READ))],
    key: Annotated[str, Query(min_length=1, max_length=KEY_LENGTH)],
    entity: Annotated[str | None, Query(description="Entity code or id")] = None,
    book: Annotated[BookCode | None, Query(description="Default: the primary book")] = None,
    contract: Annotated[str | None, Query()] = None,
    obligation: Annotated[str | None, Query()] = None,
    known_at: Annotated[AwareDatetime | None, Query(description="Default: now")] = None,
) -> PolicyResolutionOut:
    """The value of ``key`` at ``known_at`` and the chain of levels consulted (DG-KRN-REG-01)."""
    result = registry_versions.resolve_policy(
        ctx,
        key=key,
        entity_ref=entity,
        book_code=book,
        contract=contract,
        obligation=obligation,
        known_at=ctx.now if known_at is None else known_at,
    )
    return PolicyResolutionOut.model_validate(result)


@router.get(
    "/policies/{policy_id}",
    operation_id="policies_get",
    response_model=PolicyOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def policies_get(
    policy_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> PolicyOut:
    out = PolicyOut.model_validate(
        registry_versions.get_policy(ctx, policy_id, files=deps.files, keyring=deps.keyring)
    )
    response.headers["ETag"] = _etag(out)
    return out


@router.patch(
    "/policies/{policy_id}",
    operation_id="policies_update",
    response_model=PolicyOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "not-found",
        "invalid-transition",
        "configuration-frozen",
        "policy-level-not-allowed",
        "precondition-failed",
        "precondition-required",
    ),
)
def policies_update(
    policy_id: uuid.UUID,
    body: PolicyUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change the statement or effective date of a DRAFT or TESTED version (``If-Match``
    required)."""
    changes: dict[str, Any] = {
        name: getattr(body, name)
        for name in ("values", "unset", "basis", "effective_from")
        if name in body.model_fields_set
        and (name == "effective_from" or getattr(body, name) is not None)
    }

    def handle(uow: UnitOfWork) -> PolicyOut:
        registry_versions.update_policy(
            uow,
            policy_id,
            changes=changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return _policy(uow, policy_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/policies/{policy_id}/test",
    operation_id="policies_test",
    status_code=202,
    response_model=JobOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "policy-level-not-allowed"
    ),
)
def policies_test(
    policy_id: uuid.UUID,
    body: PolicyTestIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Validate the version and run the ``POLICY_SIMULATION`` job, which records TESTED with the
    test evidence and the simulation report (REQ-POL-003, REQ-POL-006)."""

    def handle(uow: UnitOfWork) -> JobOut:
        job_id = registry_versions.request_test(uow, policy_id, run_simulation=body.run_simulation)
        return jobs.job_out_of(uow.session, job_id)

    return run_command(
        cmd,
        deps,
        handle,
        status_code=202,
        location=lambda job: f"{API_PREFIX}/jobs/{job.id}",
    )


@router.post(
    "/policies/{policy_id}/submit",
    operation_id="policies_submit",
    response_model=PolicyOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def policies_submit(
    policy_id: uuid.UUID,
    body: PolicyCommentIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Submit a TESTED version for approval with its simulation report (PRD BR-POL-01)."""

    def handle(uow: UnitOfWork) -> PolicyOut:
        registry_versions.submit_policy(uow, policy_id, comment=body.comment)
        return _policy(uow, policy_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/policies/{policy_id}/withdraw",
    operation_id="policies_withdraw",
    response_model=PolicyOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def policies_withdraw(
    policy_id: uuid.UUID,
    body: PolicyCommentIn,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Withdraw the pending request of a SUBMITTED version, which returns to DRAFT."""

    def handle(uow: UnitOfWork) -> PolicyOut:
        registry_versions.withdraw_policy(uow, policy_id, comment=body.comment)
        return _policy(uow, policy_id)

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/policies/{policy_id}/publish",
    operation_id="policies_publish",
    response_model=PolicyOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "configuration-overlap"
    ),
)
def policies_publish(
    policy_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Publish a version left APPROVED; approval publishes a version itself (04 §16.5)."""

    def handle(uow: UnitOfWork) -> PolicyOut:
        registry_versions.publish_policy(uow, policy_id)
        return _policy(uow, policy_id)

    return run_command(cmd, deps, handle, etag=_etag)


# --- policy overrides (T-CON-23; BS3-D-04; BUILD_SPEC CTR-15) -------------------------------------


def _override_etag(out: PolicyOverrideOut) -> str:
    """API-C-08: ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _override(uow: UnitOfWork, override_id: uuid.UUID) -> PolicyOverrideOut:
    return PolicyOverrideOut.model_validate(overrides.override_out(uow.session, override_id))


@router.get(
    "/policy-overrides",
    operation_id="policy_overrides_list",
    response_model=ListOut[PolicyOverrideOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def policy_overrides_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
    params: Annotated[ListParams, Depends(list_params)],
    contract: Annotated[uuid.UUID | None, Query(description="Contract id")] = None,
) -> ListOut[PolicyOverrideOut]:
    """Overrides of visible contracts; filters ``contract``, ``status``, ``policy_key``; sort
    ``created_at`` (default descending) or ``id``."""
    result, items = overrides.list_overrides(
        ctx,
        contract_id=contract,
        page=lambda session, statement: paginate(session, statement, POLICY_OVERRIDE_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[PolicyOverrideOut](
        items=[PolicyOverrideOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/policy-overrides",
    operation_id="policy_overrides_create",
    status_code=201,
    response_model=PolicyOverrideOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "policy-level-not-allowed"),
)
def policy_overrides_create(
    body: PolicyOverrideIn,
    cmd: Annotated[CommandContext, Depends(command(OVERRIDE_AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a draft for an enabled policy/scope; other keys remain explicitly unavailable."""

    def handle(uow: UnitOfWork) -> PolicyOverrideOut:
        return PolicyOverrideOut.model_validate(overrides.create_override(uow, **body.model_dump()))

    return run_command(cmd, deps, handle, status_code=201)


@router.get(
    "/policy-overrides/{override_id}",
    operation_id="policy_overrides_get",
    response_model=PolicyOverrideOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def policy_overrides_get(
    override_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ))],
) -> PolicyOverrideOut:
    out = PolicyOverrideOut.model_validate(overrides.get_override(ctx, override_id))
    response.headers["ETag"] = _override_etag(out)
    return out


@router.post(
    "/policy-overrides/{override_id}/submit",
    operation_id="policy_overrides_submit",
    response_model=PolicyOverrideOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def policy_overrides_submit(
    override_id: uuid.UUID,
    body: PolicyOverrideCommentIn,
    cmd: Annotated[CommandContext, Depends(command(OVERRIDE_AUTHOR))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Submit a DRAFT override for approval of subject ``POLICY_OVERRIDE``."""

    def handle(uow: UnitOfWork) -> PolicyOverrideOut:
        overrides.submit_override(uow, override_id, comment=body.comment)
        return _override(uow, override_id)

    return run_command(cmd, deps, handle, etag=_override_etag)
