"""API-R-28 Contracts: creation, drafts and time-travel reads.

04 §15.3 API-R-28, §16.1, §16.2 API-S-ScheduleLine, §16.14 API-S-ContractHistoryItem, API-C-06 to
API-C-11; DG-CMD-12, DG-CMD-13; BUILD_SPEC CTR-4. Reads need ``contract.read``; ``POST /contracts``
and ``replace-draft`` need ``contract.create``, which the handler checks for the contracting entity.
Every command takes ``Idempotency-Key``; ``replace-draft`` also takes
``If-Match: "s<head_stream_version>"`` (API-C-08). Computed reads take ``book``, ``as_of`` and
``known_at`` (API-C-10, API-C-11); ``known_at`` needs an offset, else 422 API-C-09.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Select
from sqlalchemy.orm import Session

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    command,
    contract_etag,
    kernel_deps,
    problem_responses,
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListResult,
    ListSpec,
    invalid,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.clock import Clock, get_clock
from erev_api.db.tables import contract, contract_version, customer, schedule_line, subledger_line
from erev_api.domain.contracts import (
    activation,
    combination,
    commands,
    holds,
    locks,
    queries,
    void,
)
from erev_api.domain.contracts import (
    regroup as regroup_module,
)
from erev_api.domain.integrations import normalise
from erev_api.enums import BookCode, ContractQuickList, ContractStatus, HistoryItemKind
from erev_api.schemas.common import ListOut
from erev_api.schemas.contracts import (
    ActivationChecklistOut,
    AllocationWalkOut,
    ContractBalanceOut,
    ContractCreateIn,
    ContractHistoryItemOut,
    ContractListItemOut,
    ContractOut,
    ContractVersionOut,
    ContractVersionSummaryOut,
    ContractVoidRequestedOut,
    ContractVoidRequestIn,
    DistinctReviewIn,
    DistinctReviewOut,
    ScheduleLineOut,
    SubmitActivationIn,
    VersionCompareOut,
)
from erev_api.schemas.events import HoldApplyIn, HoldReleaseIn, MemosUpdateIn
from erev_api.schemas.modifications import RegroupIn, RegroupOut
from erev_api.schemas.source_records import ContractSourceOut
from erev_api.schemas.subledger import SubledgerLineOut
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-28 Contracts"
READ: Final = "contract.read"
CREATE: Final = "contract.create"
VOID: Final = "contract.void"  # 04 API-R-28 request-void
# 04 §16.1 rev 1.263 (item REGROUP-PERMISSION-PRD-1; PRD ACT-04; API-R-28): a regroup moves
# obligations between two drafts, which is draft editing. Until then: ``modification.create``.
REGROUP: Final = CREATE
JUDGEMENT_CREATE: Final = "judgement.create"
APPROVAL_HEADER: Final = "X-Erev-Approval-Request"  # 04 §16.1 submit-activation
DECIMAL_PATTERN: Final = r"^-?[0-9]{1,20}(\.[0-9]{1,18})?$"  # API-C-06 decimal strings
LARGEST_VALUE_SORT: Final = "-transaction_price"  # E-111 LARGEST_VALUE
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
_TIME_TRAVEL: Final = frozenset({"book", "as_of", "known_at"})
CONTRACT_LIST: Final = ListSpec(
    resource="contracts",
    sort_keys={
        "id": contract.c.id,
        "contract_no": contract.c.contract_no,
        "inception_date": contract.c.inception_date,
        "transaction_price": queries.LIST_PRICE,
        "updated_at": contract.c.updated_at,
    },
    default_sort="-id",
    filters={
        "status": FilterSpec(
            name="status",
            column=contract.c.status,
            kind="exact",
            choices=frozenset(status.value for status in ContractStatus),
        )
    },
    search_columns=(contract.c.external_id, contract.c.contract_no, customer.c.name),
    custom_filters=frozenset(
        {
            "entity",
            "customer",
            "on_hold",
            "modified_in_period",
            "value_min",
            "value_max",
            "has_exceptions",
            "quick_list",
        }
    )
    | _TIME_TRAVEL,
)
VERSION_LIST: Final = ListSpec(
    resource="contract-versions",
    sort_keys={"id": contract_version.c.id, "version_no": contract_version.c.version_no},
    default_sort="-version_no",
    filters={},
    custom_filters=frozenset({"book"}),
)
SCHEDULE_LIST: Final = ListSpec(
    resource="contract-schedule",
    sort_keys={"id": schedule_line.c.id, "period_end_date": schedule_line.c.period_end_date},
    default_sort="period_end_date",
    filters={},
    custom_filters=_TIME_TRAVEL,
)
SUBLEDGER_LIST: Final = ListSpec(
    resource="contract-subledger-lines",
    sort_keys={"id": subledger_line.c.id, "recorded_at": subledger_line.c.recorded_at},
    default_sort="-id",
    filters={},
    custom_filters=_TIME_TRAVEL,
)

type ReadContext = Annotated[RequestContext, Depends(require(READ))]
type AppClock = Annotated[Clock, Depends(get_clock)]
type Params = Annotated[ListParams, Depends(list_params)]
type Book = Annotated[BookCode | None, Query(description="Default the primary book (API-C-11)")]
type AsOf = Annotated[date | None, Query(description="Effective cut-off (API-C-10)")]
type KnownAt = Annotated[
    datetime | None, Query(description="Record cut-off, RFC 3339 with an offset (API-C-10)")
]

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _read_params(
    book: BookCode | None, as_of: date | None, known_at: datetime | None
) -> queries.ReadParams:
    if known_at is not None and known_at.utcoffset() is None:
        raise invalid("known_at", "Send known_at as an RFC 3339 timestamp with an offset.")
    return queries.ReadParams(
        book=None if book is None else book.value, as_of=as_of, known_at=known_at
    )


def _etag(out: ContractOut) -> str:
    """API-C-08: a contract's ETag is ``"s<head_stream_version>"``."""
    return contract_etag(out.head_stream_version)


def _total(response: Response, result: ListResult) -> None:
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count


@router.get(
    "/contracts",
    operation_id="contracts_list",
    response_model=ListOut[ContractListItemOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def contracts_list(
    response: Response,
    ctx: ReadContext,
    clock: AppClock,
    params: Params,
    entity: Annotated[list[str] | None, Query(description="Entity code or id; repeatable")] = None,
    customer_ref: Annotated[
        list[str] | None, Query(alias="customer", description="Customer code or id; repeatable")
    ] = None,
    status: Annotated[list[ContractStatus] | None, Query()] = None,
    on_hold: Annotated[bool | None, Query()] = None,
    modified_in_period: Annotated[str | None, Query(description="Period key")] = None,
    value_min: Annotated[str | None, Query(pattern=DECIMAL_PATTERN)] = None,
    value_max: Annotated[str | None, Query(pattern=DECIMAL_PATTERN)] = None,
    has_exceptions: Annotated[bool | None, Query()] = None,
    quick_list: Annotated[ContractQuickList | None, Query(description="E-111")] = None,
    book: Book = None,
    as_of: AsOf = None,
    known_at: KnownAt = None,
) -> ListOut[ContractListItemOut]:
    """Contracts with filters and E-111 quick lists; ``q`` searches the external id, contract number
    and customer name; sort ``contract_no``, ``inception_date``, ``transaction_price``,
    ``updated_at`` or ``id`` (default ``-id``). List items omit ``kpis.balances`` and ``links``."""
    del status  # applied by ``paginate`` through CONTRACT_LIST
    read_params = _read_params(book, as_of, known_at)
    now = clock.now()
    filters = queries.ListFilters(
        entity=tuple(entity or ()),
        customer=tuple(customer_ref or ()),
        on_hold=on_hold,
        modified_in_period=modified_in_period,
        value_min=None if value_min is None else Decimal(value_min),
        value_max=None if value_max is None else Decimal(value_max),
        has_exceptions=has_exceptions,
        quick_list=quick_list,
    )
    if quick_list is ContractQuickList.LARGEST_VALUE and params.sort is None:
        params = dataclasses.replace(params, sort=LARGEST_VALUE_SORT)
    listing = params

    def page(
        session: Session, statement: Select[Any]
    ) -> tuple[ListResult, list[ContractListItemOut]]:
        result = paginate(session, statement, CONTRACT_LIST, listing)
        items = queries.contract_list_items(session, result.items, params=read_params, now=now)
        return result, items

    result, items = queries.list_contracts(ctx, filters, now=now, page=page)
    _total(response, result)
    return ListOut[ContractListItemOut](items=items, next_cursor=result.next_cursor)


@router.post(
    "/contracts",
    operation_id="contracts_create",
    status_code=201,
    response_model=ContractOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def contracts_create(
    body: ContractCreateIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create the contract in DRAFT, append ``CONTRACT_BOOKED`` and compute a provisional version;
    nothing posts while the contract is DRAFT (REQ-CON-001, REQ-CON-002)."""

    def handle(uow: UnitOfWork) -> ContractOut:
        created = commands.create_contract(uow, body=body)
        combination.raise_suggestions(uow, created.id)  # S02-R-14 (BUILD_SPEC CTR-8)
        if holds.apply_rule_holds(uow, created.id):  # REQ-POL-010 user hold rules (CTR-10)
            created = queries.contract_out(uow.session, created.id, now=uow.now)
        return created

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/contracts/{out.id}",
        etag=_etag,
    )


@router.get(
    "/contracts/{contract_id}",
    operation_id="contracts_get",
    response_model=ContractOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def contracts_get(
    contract_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    clock: AppClock,
    book: Book = None,
    as_of: AsOf = None,
    known_at: KnownAt = None,
) -> ContractOut:
    """API-S-Contract at the version in context (API-C-10); ETag ``"s<head_stream_version>"``."""
    out = queries.get_contract(
        ctx, contract_id, params=_read_params(book, as_of, known_at), now=clock.now()
    )
    response.headers["ETag"] = _etag(out)
    return out


@router.post(
    "/contracts/{contract_id}/replace-draft",
    operation_id="contracts_replace_draft",
    response_model=ContractOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "not-found",
        "invalid-transition",
        "precondition-failed",
        "precondition-required",
    ),
)
def contracts_replace_draft(
    contract_id: uuid.UUID,
    body: ContractCreateIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE, precondition="contract"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Replace the booking of a DRAFT contract: ``EVENT_VOIDED`` by SYSTEM, the new
    ``CONTRACT_BOOKED`` and a recomputation in one transaction; 409 ``invalid-transition`` unless
    DRAFT (04 §16.1)."""

    def handle(uow: UnitOfWork) -> ContractOut:
        return commands.replace_draft(
            uow, contract_id=contract_id, expected_stream_version=cmd.expected_version, body=body
        )

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/contracts/{contract_id}/submit-activation",
    operation_id="contracts_submit_activation",
    response_model=ContractOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "not-found",
        "invalid-transition",
        "precondition-failed",
        "precondition-required",
        "activation-checklist-failed",
    ),
)
def contracts_submit_activation(
    contract_id: uuid.UUID,
    body: SubmitActivationIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE, precondition="contract"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Evaluate the activation checklist, compute the activation dry run and route
    ``CONTRACT_ACTIVATION``: status PENDING_REVIEW with header ``X-Erev-Approval-Request``, or
    ACTIVE when an auto-approval rule approves it; 409 ``activation-checklist-failed`` names each
    failed item (04 §16.1; REQ-CON-005, REQ-CON-006)."""
    requests: list[uuid.UUID] = []

    def handle(uow: UnitOfWork) -> ContractOut:
        submitted = activation.submit_activation(
            uow, contract_id=contract_id, expected_stream_version=cmd.expected_version, body=body
        )
        requests.append(submitted.approval_request_id)
        return submitted.contract

    return run_command(
        cmd,
        deps,
        handle,
        etag=_etag,
        extra_headers=lambda _out: {APPROVAL_HEADER: str(requests[-1])},
    )


@router.post(
    "/contracts/{contract_id}/request-void",
    operation_id="contracts_request_void",
    response_model=ContractVoidRequestedOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS,
        "not-found",
        "invalid-transition",
        "precondition-failed",
        "precondition-required",
    ),
)
def contracts_request_void(
    contract_id: uuid.UUID,
    body: ContractVoidRequestIn,
    cmd: Annotated[CommandContext, Depends(command(VOID, precondition="contract"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Open a ``CONTRACT_VOID`` approval request with the dry run of the void as its impact
    preview: one ``contract.approve`` step, and a Controller second step when the contract has
    posted lines; on approval SYSTEM appends ``CONTRACT_VOIDED`` and the reversal posts in the
    first open period (04 §16.1; PRD §2.5, SM-02; REQ-CON-015; CTL-046)."""

    def handle(uow: UnitOfWork) -> ContractVoidRequestedOut:
        return void.request_void(
            uow, contract_id=contract_id, expected_stream_version=cmd.expected_version, body=body
        )

    return run_command(cmd, deps, handle)


@router.post(
    "/contracts/{contract_id}/regroup",
    operation_id="contracts_regroup",
    status_code=201,
    response_model=RegroupOut,
    responses=problem_responses(
        *_COMMAND_PROBLEMS, "not-found", "invalid-transition", "precondition-failed"
    ),
)
def contracts_regroup(
    contract_id: uuid.UUID,
    body: RegroupIn,
    cmd: Annotated[CommandContext, Depends(command(REGROUP))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Move obligations to another (or a new) contract (04 §16.1; REQ-CON-012; ENGINE_SPEC
    S06-R-27; CTR-17). In release 1.0 the command is taken between two draft contracts: the
    paired ``REGROUPED`` events apply at once and both contracts recompute from inception. With a
    contract that is not a draft, or after a posting, it answers 409 ``invalid-transition``: such
    an obligation is moved by a modification of each contract (04 §16.1 rev 1.234)."""

    def handle(uow: UnitOfWork) -> RegroupOut:
        return regroup_module.regroup(uow, contract_id=contract_id, body=body)

    return run_command(cmd, deps, handle, status_code=201)


_HOLD_PROBLEMS: Final = (
    *_COMMAND_PROBLEMS,
    "not-found",
    "invalid-transition",
    "precondition-failed",
    "precondition-required",
)


@router.post(
    "/contracts/{contract_id}/apply-hold",
    operation_id="contracts_apply_hold",
    response_model=ContractOut,
    responses=problem_responses(*_HOLD_PROBLEMS),
)
def contracts_apply_hold(
    contract_id: uuid.UUID,
    body: HoldApplyIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE, precondition="contract"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Append ``HOLD_APPLIED`` (MANUAL) on the contract or one obligation and compute the group;
    a ``recognition`` hold freezes the targets, a ``journal_export`` hold excludes the lines from
    export (04 §16.1; REQ-REC-022)."""

    def handle(uow: UnitOfWork) -> ContractOut:
        return holds.apply_hold(
            uow, contract_id=contract_id, expected_stream_version=cmd.expected_version, body=body
        )

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/contracts/{contract_id}/release-hold",
    operation_id="contracts_release_hold",
    response_model=ContractOut,
    responses=problem_responses(*_HOLD_PROBLEMS),
)
def contracts_release_hold(
    contract_id: uuid.UUID,
    body: HoldReleaseIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE, precondition="contract"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Append ``HOLD_RELEASED`` for an open hold and compute the group; the held amount catches up
    in the period that contains the release date (04 §16.1; ENGINE_SPEC_B S09-R-44)."""

    def handle(uow: UnitOfWork) -> ContractOut:
        return holds.release_hold(
            uow, contract_id=contract_id, expected_stream_version=cmd.expected_version, body=body
        )

    return run_command(cmd, deps, handle, etag=_etag)


@router.post(
    "/contracts/{contract_id}/update-memos",
    operation_id="contracts_update_memos",
    response_model=ContractOut,
    responses=problem_responses(*_HOLD_PROBLEMS),
)
def contracts_update_memos(
    contract_id: uuid.UUID,
    body: MemosUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE, precondition="contract"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Append ``MEMO_UPDATED`` with a mandatory comment, audited field by field; posted amounts do
    not change (04 §16.1; REQ-CON-008)."""

    def handle(uow: UnitOfWork) -> ContractOut:
        return locks.update_memos(
            uow, contract_id=contract_id, expected_stream_version=cmd.expected_version, body=body
        )

    return run_command(cmd, deps, handle, etag=_etag)


@router.get(
    "/contracts/{contract_id}/activation-checklist",
    operation_id="contracts_activation_checklist",
    response_model=ActivationChecklistOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def contracts_activation_checklist(
    contract_id: uuid.UUID, ctx: ReadContext, clock: AppClock
) -> ActivationChecklistOut:
    """API-S-ActivationChecklist: the items of table 15.4-I, evaluated without storing (04 §16.14;
    SCREENS R-05)."""
    return activation.checklist_out(ctx, contract_id, now=clock.now())


@router.get(
    "/contracts/{contract_id}/sources",
    operation_id="contracts_sources",
    response_model=ListOut[ContractSourceOut],
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def contracts_sources(contract_id: uuid.UUID, ctx: ReadContext) -> ListOut[ContractSourceOut]:
    """The source records that established or changed the contract (T-CON-02), each with its sheet
    and row number when it came from an import; one page (04 API-R-28; SCREENS §6.6; BUILD_SPEC
    DIN-4, BS3-D-04)."""
    items = queries.read(ctx, lambda session: normalise.contract_sources(session, contract_id))
    return ListOut[ContractSourceOut](items=items, next_cursor=None)


@router.post(
    "/contracts/{contract_id}/obligations/{obligation_key}/distinct-review",
    operation_id="contracts_distinct_review",
    status_code=201,
    response_model=DistinctReviewOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found"),
)
def contracts_distinct_review(
    contract_id: uuid.UUID,
    obligation_key: str,
    body: DistinctReviewIn,
    cmd: Annotated[CommandContext, Depends(command(JUDGEMENT_CREATE))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Record the obligation's distinct review: a ``POB_DISTINCT_OVERRIDE`` judgement record
    submitted for review; 201 ``{judgement_record_id, approval_request_id}``, no ``If-Match`` (04
    §16.1; REQ-POB-001; SCREENS R-17)."""

    def handle(uow: UnitOfWork) -> DistinctReviewOut:
        return activation.record_distinct_review(
            uow, contract_id=contract_id, obligation_key=obligation_key, body=body
        )

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/judgements/{out.judgement_record_id}",
    )


@router.get(
    "/contracts/{contract_id}/versions",
    operation_id="contract_versions_list",
    response_model=ListOut[ContractVersionSummaryOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def contract_versions_list(
    contract_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    params: Params,
    book: Book = None,
) -> ListOut[ContractVersionSummaryOut]:
    """The group's versions in the book; sort ``version_no`` (default ``-version_no``) or ``id``.
    Items omit ``obligations`` and ``balances``."""

    def load(session: Session) -> tuple[ListResult, list[ContractVersionSummaryOut]]:
        statement = queries.versions_statement(
            session, contract_id, book_code=None if book is None else book.value
        )
        result = paginate(session, statement, VERSION_LIST, params)
        return result, queries.version_summaries(session, result.items)

    result, items = queries.read(ctx, load)
    _total(response, result)
    return ListOut[ContractVersionSummaryOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/contracts/{contract_id}/versions/compare",
    operation_id="contract_versions_compare",
    response_model=VersionCompareOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def contract_versions_compare(
    contract_id: uuid.UUID,
    ctx: ReadContext,
    from_no: Annotated[int, Query(alias="from", ge=1, description="Earlier version_no")],
    to_no: Annotated[int, Query(alias="to", ge=1, description="Later version_no")],
    book: Book = None,
) -> VersionCompareOut:
    """Field-by-field differences between two versions (REQ-CON-014)."""
    return queries.compare_versions(
        ctx,
        contract_id,
        from_no=from_no,
        to_no=to_no,
        book_code=None if book is None else book.value,
    )


@router.get(
    "/contracts/{contract_id}/versions/{version_no}",
    operation_id="contract_versions_get",
    response_model=ContractVersionOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def contract_versions_get(
    contract_id: uuid.UUID,
    version_no: int,
    ctx: ReadContext,
    clock: AppClock,
    book: Book = None,
    as_of: AsOf = None,
    known_at: KnownAt = None,
) -> ContractVersionOut:
    """API-S-ContractVersion with the contract's obligations and balances."""
    return queries.get_version(
        ctx, contract_id, version_no, params=_read_params(book, as_of, known_at), now=clock.now()
    )


@router.get(
    "/contracts/{contract_id}/balances",
    operation_id="contract_balances_list",
    response_model=ListOut[ContractBalanceOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def contract_balances_list(
    contract_id: uuid.UUID,
    ctx: ReadContext,
    clock: AppClock,
    book: Book = None,
    as_of: AsOf = None,
    known_at: KnownAt = None,
) -> ListOut[ContractBalanceOut]:
    """API-S-ContractBalance per entity at the version in context; one page."""
    items = queries.balances(
        ctx, contract_id, params=_read_params(book, as_of, known_at), now=clock.now()
    )
    return ListOut[ContractBalanceOut](items=items, next_cursor=None)


@router.get(
    "/contracts/{contract_id}/allocation",
    operation_id="contract_allocation_get",
    response_model=AllocationWalkOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def contract_allocation_get(
    contract_id: uuid.UUID,
    ctx: ReadContext,
    clock: AppClock,
    book: Book = None,
    as_of: AsOf = None,
    known_at: KnownAt = None,
) -> AllocationWalkOut:
    """API-S-AllocationWalk (REQ-ALC-009); 404 while no version exists."""
    return queries.allocation_walk(
        ctx, contract_id, params=_read_params(book, as_of, known_at), now=clock.now()
    )


@router.get(
    "/contracts/{contract_id}/schedule",
    operation_id="contract_schedule_list",
    response_model=ListOut[ScheduleLineOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def contract_schedule_list(
    contract_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    params: Params,
    book: Book = None,
    as_of: AsOf = None,
    known_at: KnownAt = None,
) -> ListOut[ScheduleLineOut]:
    """API-S-ScheduleLine rows at the version in context; ``as_of`` keeps periods ending by the end
    of its period; sort ``period_end_date`` (default) or ``id``."""
    read_params = _read_params(book, as_of, known_at)

    def load(session: Session) -> tuple[ListResult, list[ScheduleLineOut]]:
        statement = queries.schedule_statement(session, contract_id, params=read_params)
        result = paginate(session, statement, SCHEDULE_LIST, params)
        return result, queries.schedule_items(result.items)

    result, items = queries.read(ctx, load)
    _total(response, result)
    return ListOut[ScheduleLineOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/contracts/{contract_id}/subledger-lines",
    operation_id="contract_subledger_lines_list",
    response_model=ListOut[SubledgerLineOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def contract_subledger_lines_list(
    contract_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    clock: AppClock,
    params: Params,
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
    book: Book = None,
    as_of: AsOf = None,
    known_at: KnownAt = None,
) -> ListOut[SubledgerLineOut]:
    """The contract's API-S-SubledgerLine rows (API-C-10 ledger semantics); sort ``id`` (default
    ``-id``) or ``recorded_at``. Each line names the journal run that journalises it
    (``journal_run_id``, 04 rev 1.288)."""
    read_params = _read_params(book, as_of, known_at)
    now = clock.now()

    def load(session: Session) -> tuple[ListResult, list[SubledgerLineOut]]:
        statement = queries.subledger_statement(session, contract_id, params=read_params, now=now)
        result = paginate(session, statement, SUBLEDGER_LIST, params)
        # lane F-CLO-A, item SUBLEDGER-LINE-JOURNAL-RUN-1: the file store and the key ring, as
        # the gate hands them to the reader of a run's record
        items = queries.subledger_items(
            session, result.items, files=deps.files, keyring=deps.keyring
        )
        return result, items

    result, items = queries.read(ctx, load)
    _total(response, result)
    return ListOut[SubledgerLineOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/contracts/{contract_id}/history",
    operation_id="contract_history_list",
    response_model=ListOut[ContractHistoryItemOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def contract_history_list(
    contract_id: uuid.UUID,
    response: Response,
    ctx: ReadContext,
    params: Params,
    kind: Annotated[list[HistoryItemKind] | None, Query(description="E-116; repeatable")] = None,
    include_system: Annotated[bool, Query()] = False,
) -> ListOut[ContractHistoryItemOut]:
    """API-S-ContractHistoryItem, newest first (04 §16.14)."""
    del kind  # applied by ``paginate`` through the history list spec

    def load(session: Session) -> tuple[ListResult, list[ContractHistoryItemOut]]:
        statement = queries.history_statement(session, contract_id, include_system=include_system)
        columns = statement.selected_columns
        spec = ListSpec(
            resource="contract-history",
            sort_keys={"id": columns["id"], "occurred_at": columns["occurred_at"]},
            default_sort="-occurred_at",
            filters={
                "kind": FilterSpec(
                    name="kind",
                    column=columns["kind"],
                    kind="exact",
                    choices=frozenset(item.value for item in HistoryItemKind),
                )
            },
            custom_filters=frozenset({"include_system"}),
        )
        result = paginate(session, statement, spec, params)
        return result, queries.history_items(session, contract_id, result.items)

    result, items = queries.read(ctx, load)
    _total(response, result)
    return ListOut[ContractHistoryItemOut](items=items, next_cursor=result.next_cursor)
