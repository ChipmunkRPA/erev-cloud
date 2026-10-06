"""API-R-19 Currencies and FX.

04 §15.3 API-R-19, T-REF-08 to T-REF-12, E-12, API-C-06, API-C-08, API-C-09; PRD SM-04; BUILD_SPEC
RFD-3. Reads need ``config.read``; ``PUT /tenant-currencies`` needs ``settings.manage`` for all
entities (04 API-C-03 rev 1.219: the workspace's currencies are no entity's). Rate sets,
rate set versions and rates need any of ``config.author`` and ``masterdata.maintain``; a single-code
guard cannot express a permission set, so those routes use ``command(per_subject=True)`` and the
handlers authorise (L1-1-Q-4). A version changes only while DRAFT and publishes through an
``FX_RATE_SET_VERSION`` approval; ``GET /fx-rates`` lists only rates of APPROVED versions.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query, Response

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    assert_version,
    command,
    expected_version,
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
from erev_api.db.tables import currency, fx_rate_set, fx_rate_set_version, tenant_currency
from erev_api.domain.reference import commands, fx, queries
from erev_api.enums import ConfigStatus, RateType
from erev_api.schemas.common import ListOut
from erev_api.schemas.currencies import (
    CurrencyOut,
    EffectiveFxRateOut,
    FxRateSetIn,
    FxRateSetOut,
    FxRateSetVersionCommandIn,
    FxRateSetVersionDetailOut,
    FxRateSetVersionIn,
    FxRateSetVersionOut,
    FxRateSetVersionUpdateIn,
    TenantCurrenciesIn,
    TenantCurrencyOut,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-19 Currencies and FX"
READ_PERMISSION: Final = "config.read"
SETTINGS_PERMISSION: Final = "settings.manage"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "mfa-required",
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
_VERSION_PROBLEMS: Final = (
    *_COMMAND_PROBLEMS,
    "not-found",
    "precondition-failed",
    "precondition-required",
    "invalid-transition",
    "configuration-frozen",
)
_RATE_TYPES: Final = frozenset(member.value for member in RateType)
CURRENCY_LIST: Final = ListSpec(
    resource="currencies",
    sort_keys={"id": currency.c.code, "code": currency.c.code, "name": currency.c.name},
    default_sort="code",
    filters={
        "code": FilterSpec(name="code", column=currency.c.code, kind="exact"),
        "is_active": FilterSpec(name="is_active", column=currency.c.is_active, kind="bool"),
    },
    search_columns=(currency.c.code, currency.c.name),
)
TENANT_CURRENCY_LIST: Final = ListSpec(
    resource="tenant-currencies",
    sort_keys={
        "id": tenant_currency.c.currency_code,
        "currency_code": tenant_currency.c.currency_code,
    },
    default_sort="currency_code",
    filters={
        "is_enabled": FilterSpec(
            name="is_enabled", column=tenant_currency.c.is_enabled, kind="bool"
        ),
    },
)
FX_RATE_SET_LIST: Final = ListSpec(
    resource="fx-rate-sets",
    sort_keys={"id": fx_rate_set.c.id, "code": fx_rate_set.c.code, "name": fx_rate_set.c.name},
    default_sort="code",
    filters={
        "rate_type": FilterSpec(
            name="rate_type", column=fx_rate_set.c.rate_type, kind="exact", choices=_RATE_TYPES
        ),
    },
    search_columns=(fx_rate_set.c.code, fx_rate_set.c.name),
)
FX_RATE_SET_VERSION_LIST: Final = ListSpec(
    resource="fx-rate-set-versions",
    sort_keys={
        "id": fx_rate_set_version.c.id,
        "version_no": fx_rate_set_version.c.version_no,
        "coverage_from": fx_rate_set_version.c.coverage_from,
    },
    default_sort="-version_no",
    filters={
        "status": FilterSpec(
            name="status",
            column=fx_rate_set_version.c.status,
            kind="exact",
            choices=frozenset(member.value for member in ConfigStatus),
        ),
    },
)
_EFFECTIVE: Final = fx.EFFECTIVE_RATES.c
FX_RATE_LIST: Final = ListSpec(
    resource="fx-rates",
    sort_keys={"id": _EFFECTIVE.id, "effective_date": _EFFECTIVE.effective_date},
    default_sort="effective_date",
    filters={
        "rate_type": FilterSpec(
            name="rate_type", column=_EFFECTIVE.rate_type, kind="exact", choices=_RATE_TYPES
        ),
        "base": FilterSpec(name="base", column=_EFFECTIVE.base_currency, kind="exact"),
        "quote": FilterSpec(name="quote", column=_EFFECTIVE.quote_currency, kind="exact"),
        "date": FilterSpec(name="date", column=_EFFECTIVE.effective_date, kind="exact"),
        "period": FilterSpec(name="period", column=_EFFECTIVE.period_key, kind="exact"),
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def row_version_etag(out: FxRateSetOut | FxRateSetVersionOut) -> str:
    """API-C-08: rate sets are IM-M and versions IM-P, so the ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def version_location(out: FxRateSetVersionOut) -> str:
    return f"{API_PREFIX}/fx-rate-set-versions/{out.id}"


def _version_check(cmd: CommandContext) -> commands.VersionCheck:
    """``If-Match`` of a per-subject command, checked once the handler has authorised."""
    return lambda actual: assert_version(expected_version(cmd.ctx.if_match, "row"), actual)


@router.get(
    "/currencies",
    operation_id="currencies_list",
    response_model=ListOut[CurrencyOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def currencies_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    code: Annotated[list[str] | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> ListOut[CurrencyOut]:
    """ISO 4217 currencies with their minor units (REQ-REF-004); sort ``code`` (default) or
    ``name``; filter ``code`` (repeatable) and ``is_active``."""
    result = queries.list_currencies(
        ctx, page=lambda session, statement: paginate(session, statement, CURRENCY_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[CurrencyOut](
        items=[CurrencyOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.get(
    "/tenant-currencies",
    operation_id="tenant_currencies_list",
    response_model=ListOut[TenantCurrencyOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def tenant_currencies_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    is_enabled: Annotated[bool | None, Query()] = None,
) -> ListOut[TenantCurrencyOut]:
    """The workspace's currencies, enabled or disabled; sort ``currency_code`` (default)."""
    result = queries.list_tenant_currencies(
        ctx,
        page=lambda session, statement: paginate(session, statement, TENANT_CURRENCY_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[TenantCurrencyOut](
        items=[TenantCurrencyOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.put(
    "/tenant-currencies",
    operation_id="tenant_currencies_put",
    response_model=ListOut[TenantCurrencyOut],
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def tenant_currencies_put(
    body: TenantCurrenciesIn,
    cmd: Annotated[CommandContext, Depends(command(SETTINGS_PERMISSION, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Enable the listed currencies and disable every other one; the reporting currency stays
    enabled. Rows are never deleted."""

    def handle(uow: UnitOfWork) -> ListOut[TenantCurrencyOut]:
        items = commands.put_tenant_currencies(uow, body=body)
        return ListOut[TenantCurrencyOut](items=items, next_cursor=None)

    return run_command(cmd, deps, handle)


@router.get(
    "/fx-rate-sets",
    operation_id="fx_rate_sets_list",
    response_model=ListOut[FxRateSetOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def fx_rate_sets_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    rate_type: Annotated[RateType | None, Query()] = None,
) -> ListOut[FxRateSetOut]:
    """FX rate sets; sort ``code`` (default), ``name`` or ``id``; filter ``rate_type``."""
    result = queries.list_fx_rate_sets(
        ctx, page=lambda session, statement: paginate(session, statement, FX_RATE_SET_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[FxRateSetOut](
        items=[FxRateSetOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/fx-rate-sets",
    operation_id="fx_rate_sets_create",
    status_code=201,
    response_model=FxRateSetOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def fx_rate_sets_create(
    body: FxRateSetIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a rate series of one rate type and source."""

    def handle(uow: UnitOfWork) -> FxRateSetOut:
        return commands.create_fx_rate_set(uow, body=body)

    return run_command(cmd, deps, handle, status_code=201, etag=row_version_etag)


@router.get(
    "/fx-rate-sets/{set_id}/versions",
    operation_id="fx_rate_set_versions_list",
    response_model=ListOut[FxRateSetVersionOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def fx_rate_set_versions_list(
    set_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[ConfigStatus | None, Query()] = None,
) -> ListOut[FxRateSetVersionOut]:
    """The versions of a rate set without their rates; sort ``-version_no`` (default),
    ``coverage_from`` or ``id``; filter ``status``."""
    result = queries.list_fx_rate_set_versions(
        ctx,
        set_id,
        page=lambda session, statement: paginate(
            session, statement, FX_RATE_SET_VERSION_LIST, params
        ),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[FxRateSetVersionOut](
        items=[FxRateSetVersionOut.model_validate(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/fx-rate-sets/{set_id}/versions",
    operation_id="fx_rate_set_versions_create",
    status_code=201,
    response_model=FxRateSetVersionDetailOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found"),
)
def fx_rate_set_versions_create(
    set_id: uuid.UUID,
    body: FxRateSetVersionIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create a DRAFT version with its entered rates."""

    def handle(uow: UnitOfWork) -> FxRateSetVersionDetailOut:
        return commands.create_fx_rate_set_version(uow, set_id=set_id, body=body)

    return run_command(
        cmd, deps, handle, status_code=201, location=version_location, etag=row_version_etag
    )


@router.get(
    "/fx-rate-set-versions/{version_id}",
    operation_id="fx_rate_set_versions_get",
    response_model=FxRateSetVersionDetailOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def fx_rate_set_versions_get(
    version_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
) -> FxRateSetVersionDetailOut:
    """One version with every rate it holds and its ``ETag``."""
    out = FxRateSetVersionDetailOut.model_validate(queries.get_fx_rate_set_version(ctx, version_id))
    response.headers["ETag"] = row_version_etag(out)
    return out


@router.patch(
    "/fx-rate-set-versions/{version_id}",
    operation_id="fx_rate_set_versions_update",
    response_model=FxRateSetVersionDetailOut,
    responses=problem_responses(*_VERSION_PROBLEMS),
)
def fx_rate_set_versions_update(
    version_id: uuid.UUID,
    body: FxRateSetVersionUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change the coverage or replace the entered rates of a DRAFT version; ``If-Match``
    required."""

    def handle(uow: UnitOfWork) -> FxRateSetVersionDetailOut:
        return commands.update_fx_rate_set_version(
            uow, version_id=version_id, body=body, check_version=_version_check(cmd)
        )

    return run_command(cmd, deps, handle, etag=row_version_etag)


@router.post(
    "/fx-rate-set-versions/{version_id}/submit",
    operation_id="fx_rate_set_versions_submit",
    response_model=FxRateSetVersionDetailOut,
    responses=problem_responses(*_VERSION_PROBLEMS),
)
def fx_rate_set_versions_submit(
    version_id: uuid.UUID,
    body: FxRateSetVersionCommandIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Add the derived inverses, then submit the DRAFT version for ``FX_RATE_SET_VERSION``
    approval; ``If-Match`` required."""

    def handle(uow: UnitOfWork) -> FxRateSetVersionDetailOut:
        return commands.submit_fx_rate_set_version(
            uow, version_id=version_id, body=body, check_version=_version_check(cmd)
        )

    return run_command(cmd, deps, handle, etag=row_version_etag)


@router.post(
    "/fx-rate-set-versions/{version_id}/withdraw",
    operation_id="fx_rate_set_versions_withdraw",
    response_model=FxRateSetVersionDetailOut,
    responses=problem_responses(*_VERSION_PROBLEMS),
)
def fx_rate_set_versions_withdraw(
    version_id: uuid.UUID,
    body: FxRateSetVersionCommandIn,
    cmd: Annotated[CommandContext, Depends(command(per_subject=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """The preparer withdraws the pending approval; the version returns to DRAFT. ``If-Match``
    required."""

    def handle(uow: UnitOfWork) -> FxRateSetVersionDetailOut:
        return commands.withdraw_fx_rate_set_version(
            uow, version_id=version_id, body=body, check_version=_version_check(cmd)
        )

    return run_command(cmd, deps, handle, etag=row_version_etag)


@router.get(
    "/fx-rates",
    operation_id="fx_rates_list",
    response_model=ListOut[EffectiveFxRateOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def fx_rates_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    rate_type: Annotated[RateType | None, Query()] = None,
    base: Annotated[str | None, Query(pattern=r"^[A-Z]{3}$")] = None,
    quote: Annotated[str | None, Query(pattern=r"^[A-Z]{3}$")] = None,
    date: Annotated[date | None, Query()] = None,
    period: Annotated[str | None, Query(max_length=16)] = None,
) -> ListOut[EffectiveFxRateOut]:
    """The rates in force: for each rate type, pair and date, the rate of the highest APPROVED
    version of its set whose coverage contains the date. Filter ``rate_type``, ``base``,
    ``quote``, ``date`` and ``period`` (the key of a closing or average rate's period)."""
    result, items = queries.list_fx_rates(
        ctx, page=lambda session, statement: paginate(session, statement, FX_RATE_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[EffectiveFxRateOut](
        items=[EffectiveFxRateOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )
