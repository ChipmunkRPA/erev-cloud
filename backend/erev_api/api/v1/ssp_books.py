"""API-R-26 SSP books: books, versions, entries and the version diff.

04 §15.3 API-R-26, §16.4, T-REF-28 to T-REF-31, API-C-08, API-C-09; SCREENS §11.4; BUILD_SPEC
RFD-12, RFD-13. Reads need ``ssp.read``; creating or changing a book, a version or its entries,
and submitting or withdrawing a version, needs ``ssp.create``; ``PATCH`` and ``/submit`` need
``If-Match``. A version and its entries change only while the version is DRAFT (DB-04).
A book of an entity is listed, read and changed only where the caller's permission covers
that entity, and answers 404 otherwise — the book, its versions and their entries alike
(``domain/ssp/scope.py``; item SSP-ENTITY-SCOPE-1); a book of all entities is every holder's.
``GET /ssp/resolve`` prices one line through stage 05 over the APPROVED versions (RFD-14).
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from decimal import Decimal
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
from erev_api.db.tables import product, ssp_book, ssp_book_version, ssp_entry
from erev_api.domain.ssp import commands, publication, queries, resolution
from erev_api.enums import ConfigStatus
from erev_api.schemas.common import ListOut
from erev_api.schemas.ssp_books import (
    SspBookIn,
    SspBookOut,
    SspBookUpdateIn,
    SspBookVersionCommandIn,
    SspBookVersionIn,
    SspBookVersionOut,
    SspBookVersionUpdateIn,
    SspEntriesIn,
    SspEntriesOut,
    SspEntryOut,
    SspResolutionOut,
    SspVersionDiffOut,
)
from erev_api.uow import UnitOfWork

TAG: Final = "API-R-26 SSP books"
READ_PERMISSION: Final = "ssp.read"
CREATE_PERMISSION: Final = "ssp.create"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
_UPDATE_PROBLEMS: Final = (
    *_COMMAND_PROBLEMS,
    "not-found",
    "precondition-failed",
    "precondition-required",
)
BOOK_LIST: Final = ListSpec(
    resource="ssp-books",
    sort_keys={"id": ssp_book.c.id, "code": ssp_book.c.code, "name": ssp_book.c.name},
    default_sort="code",
    filters={},
    search_columns=(ssp_book.c.code, ssp_book.c.name),
)
VERSION_LIST: Final = ListSpec(
    resource="ssp-book-versions",
    sort_keys={"id": ssp_book_version.c.id, "version_no": ssp_book_version.c.version_no},
    default_sort="-version_no",
    filters={
        "status": FilterSpec(
            name="status",
            column=ssp_book_version.c.status,
            kind="exact",
            choices=frozenset(status.value for status in ConfigStatus),
        )
    },
)
ENTRY_LIST: Final = ListSpec(
    resource="ssp-entries",
    sort_keys={"id": ssp_entry.c.id, "product_code": product.c.code},
    default_sort="product_code",
    filters={
        "product": FilterSpec(name="product", column=product.c.code, kind="exact"),
        "stratification": FilterSpec(
            name="stratification", column=ssp_entry.c.stratification, kind="exact"
        ),
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)
DECIMAL_PATTERN: Final = r"^-?[0-9]+(\.[0-9]+)?$"  # API-C-06 decimal strings
DECIMAL_LENGTH: Final = 40


@router.get(
    "/ssp/resolve",
    operation_id="ssp_resolve",
    response_model=SspResolutionOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def ssp_resolve(
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    product: Annotated[str, Query(min_length=1, max_length=128)],
    date: Annotated[date_type, Query(description="Pricing date (S05-R-01)")],
    currency: Annotated[str, Query(pattern=r"^[A-Z]{3}$")],
    quantity: Annotated[str, Query(pattern=DECIMAL_PATTERN, max_length=DECIMAL_LENGTH)] = "1",
    stated_price: Annotated[
        str | None, Query(pattern=DECIMAL_PATTERN, max_length=DECIMAL_LENGTH)
    ] = None,
    stratification: Annotated[str | None, Query(max_length=200)] = None,
    book_version: Annotated[str | None, Query(max_length=200)] = None,
    entity: Annotated[str | None, Query(description="Performing entity code or id")] = None,
) -> SspResolutionOut:
    """The SSP of one line: the APPROVED version effective on ``date``, or the version named by
    ``book_version``, its entry extended by ``quantity`` and the point POL-071 and POL-072 select
    for ``stated_price`` (without it: the point or the midpoint, S05-R-06). The answer is the
    one a computation for ``entity`` takes; ``entity`` names an entity the caller's ``ssp.read``
    covers, and without it no book of an entity applies."""
    result = resolution.resolve(
        ctx,
        product_code=product,
        at=date,
        currency=currency,
        quantity=Decimal(quantity),
        stated_price=None if stated_price is None else Decimal(stated_price),
        stratification=stratification,
        book_version=book_version,
        entity_ref=entity,
    )
    return SspResolutionOut.model_validate(result)


def book_etag(out: SspBookOut) -> str:
    """API-C-08: a book is IM-M, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def version_etag(out: SspBookVersionOut) -> str:
    """API-C-08: a version is IM-P, so its ETag is ``"r<row_version>"``."""
    return row_etag(out.row_version)


def _book_out(uow: UnitOfWork, book_id: uuid.UUID) -> SspBookOut:
    return SspBookOut.model_validate(queries.ssp_book_row(uow.session, book_id))


def _version_out(uow: UnitOfWork, version_id: uuid.UUID) -> SspBookVersionOut:
    return SspBookVersionOut.model_validate(queries.ssp_book_version_row(uow.session, version_id))


@router.get(
    "/ssp-books",
    operation_id="ssp_books_list",
    response_model=ListOut[SspBookOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def ssp_books_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
) -> ListOut[SspBookOut]:
    """The SSP books the caller reaches — the books of all entities and the books of the entities
    its ``ssp.read`` covers; sort ``code`` (default), ``name`` or ``id``; ``q`` searches code and
    name (SCREENS §11.4 books grid)."""
    result, items = queries.list_ssp_books(
        ctx, page=lambda session, statement: paginate(session, statement, BOOK_LIST, params)
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[SspBookOut](
        items=[SspBookOut.model_validate(item) for item in items], next_cursor=result.next_cursor
    )


@router.post(
    "/ssp-books",
    operation_id="ssp_books_create",
    status_code=201,
    response_model=SspBookOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def ssp_books_create(
    body: SspBookIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Create an SSP book with its scope; its code is unique in the workspace. ``entity_code``
    names an entity the caller's ``ssp.create`` covers."""

    def handle(uow: UnitOfWork) -> SspBookOut:
        return _book_out(uow, commands.create_ssp_book(uow, body=body))

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/ssp-books/{out.id}",
        etag=book_etag,
    )


@router.get(
    "/ssp-books/{book_id}",
    operation_id="ssp_books_get",
    response_model=SspBookOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def ssp_books_get(
    book_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
) -> SspBookOut:
    """One SSP book with its current and draft versions and its ``ETag``; 404 for a book of an
    entity the caller's ``ssp.read`` does not cover."""
    out = SspBookOut.model_validate(queries.get_ssp_book(ctx, book_id))
    response.headers["ETag"] = book_etag(out)
    return out


@router.patch(
    "/ssp-books/{book_id}",
    operation_id="ssp_books_update",
    response_model=SspBookOut,
    responses=problem_responses(*_UPDATE_PROBLEMS, "configuration-frozen"),
)
def ssp_books_update(
    book_id: uuid.UUID,
    body: SspBookUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE_PERMISSION, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change the code, name, description, scope or resolution mode of a book. The scope and the
    resolution mode are frozen while a version is submitted (409) and once one is approved (422).
    """
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> SspBookOut:
        commands.update_ssp_book(
            uow,
            book_id,
            changes=changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return _book_out(uow, book_id)

    return run_command(cmd, deps, handle, etag=book_etag)


@router.get(
    "/ssp-books/{book_id}/versions",
    operation_id="ssp_book_versions_list",
    response_model=ListOut[SspBookVersionOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def ssp_book_versions_list(
    book_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    status: Annotated[list[ConfigStatus] | None, Query()] = None,
) -> ListOut[SspBookVersionOut]:
    """The versions of a book; sort ``version_no`` (default ``-version_no``) or ``id``."""
    result, items = queries.list_ssp_book_versions(
        ctx,
        book_id,
        page=lambda session, statement: paginate(session, statement, VERSION_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[SspBookVersionOut](
        items=[SspBookVersionOut.model_validate(item) for item in items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "/ssp-books/{book_id}/versions",
    operation_id="ssp_book_versions_create",
    status_code=201,
    response_model=SspBookVersionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found"),
)
def ssp_book_versions_create(
    book_id: uuid.UUID,
    body: SspBookVersionIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Start the next version of a book as DRAFT, optionally copying a version's entries."""

    def handle(uow: UnitOfWork) -> SspBookVersionOut:
        return _version_out(uow, commands.create_ssp_book_version(uow, book_id, body=body))

    return run_command(
        cmd,
        deps,
        handle,
        status_code=201,
        location=lambda out: f"{API_PREFIX}/ssp-book-versions/{out.id}",
        etag=version_etag,
    )


@router.get(
    "/ssp-book-versions/{version_id}",
    operation_id="ssp_book_versions_get",
    response_model=SspBookVersionOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def ssp_book_versions_get(
    version_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
) -> SspBookVersionOut:
    """One version with its ``ETag``."""
    out = SspBookVersionOut.model_validate(queries.get_ssp_book_version(ctx, version_id))
    response.headers["ETag"] = version_etag(out)
    return out


@router.patch(
    "/ssp-book-versions/{version_id}",
    operation_id="ssp_book_versions_update",
    response_model=SspBookVersionOut,
    responses=problem_responses(*_UPDATE_PROBLEMS, "configuration-frozen"),
)
def ssp_book_versions_update(
    version_id: uuid.UUID,
    body: SspBookVersionUpdateIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE_PERMISSION, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Change the label, effective dates or methodology of a DRAFT version."""
    changes = body.model_dump(include=body.model_fields_set)

    def handle(uow: UnitOfWork) -> SspBookVersionOut:
        commands.update_ssp_book_version(
            uow,
            version_id,
            changes=changes,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return _version_out(uow, version_id)

    return run_command(cmd, deps, handle, etag=version_etag)


@router.post(
    "/ssp-book-versions/{version_id}/submit",
    operation_id="ssp_book_versions_submit",
    response_model=SspBookVersionOut,
    responses=problem_responses(*_UPDATE_PROBLEMS, "invalid-transition", "ssp-study-required"),
)
def ssp_book_versions_submit(
    version_id: uuid.UUID,
    body: SspBookVersionCommandIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE_PERMISSION, precondition="row"))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Submit a DRAFT version for approval with its study and methodology label (REQ-SSP-008)."""

    def handle(uow: UnitOfWork) -> SspBookVersionOut:
        publication.submit_ssp_book_version(
            uow,
            version_id,
            comment=body.comment,
            check_version=lambda actual: assert_version(cmd.expected_version, actual),
        )
        return _version_out(uow, version_id)

    return run_command(cmd, deps, handle, etag=version_etag)


@router.post(
    "/ssp-book-versions/{version_id}/withdraw",
    operation_id="ssp_book_versions_withdraw",
    response_model=SspBookVersionOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "invalid-transition"),
)
def ssp_book_versions_withdraw(
    version_id: uuid.UUID,
    body: SspBookVersionCommandIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """The preparer withdraws the pending request, and the version returns to DRAFT."""

    def handle(uow: UnitOfWork) -> SspBookVersionOut:
        publication.withdraw_ssp_book_version(uow, version_id, comment=body.comment)
        return _version_out(uow, version_id)

    return run_command(cmd, deps, handle, etag=version_etag)


@router.get(
    "/ssp-book-versions/{version_id}/entries",
    operation_id="ssp_entries_list",
    response_model=ListOut[SspEntryOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def ssp_entries_list(
    version_id: uuid.UUID,
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    product: Annotated[str | None, Query(description="Product code")] = None,
    stratification: Annotated[str | None, Query()] = None,
) -> ListOut[SspEntryOut]:
    """The entries of a version with their bands; sort ``product_code`` (default) or ``id``."""
    result, items = queries.list_ssp_entries(
        ctx,
        version_id,
        page=lambda session, statement: paginate(session, statement, ENTRY_LIST, params),
    )
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[SspEntryOut](
        items=[SspEntryOut.model_validate(item) for item in items], next_cursor=result.next_cursor
    )


@router.post(
    "/ssp-book-versions/{version_id}/entries",
    operation_id="ssp_entries_upsert",
    response_model=SspEntriesOut,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "configuration-frozen"),
)
def ssp_entries_upsert(
    version_id: uuid.UUID,
    body: SspEntriesIn,
    cmd: Annotated[CommandContext, Depends(command(CREATE_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Upsert 1 to 5,000 entries of a DRAFT version by key; the stored entries in request order."""

    def handle(uow: UnitOfWork) -> SspEntriesOut:
        ids = commands.upsert_ssp_entries(uow, version_id, body=body)
        entries = queries.entries_by_id(uow.session, ids)
        return SspEntriesOut(entries=[SspEntryOut.model_validate(item) for item in entries])

    return run_command(cmd, deps, handle)


@router.delete(
    "/ssp-book-versions/{version_id}/entries/{entry_id}",
    operation_id="ssp_entries_delete",
    status_code=204,
    response_class=Response,
    responses=problem_responses(*_COMMAND_PROBLEMS, "not-found", "configuration-frozen"),
)
def ssp_entries_delete(
    version_id: uuid.UUID,
    entry_id: uuid.UUID,
    cmd: Annotated[CommandContext, Depends(command(CREATE_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Delete an entry and its bands from a DRAFT version."""
    return run_command(
        cmd,
        deps,
        lambda uow: commands.delete_ssp_entry(uow, version_id, entry_id),
        status_code=204,
    )


@router.get(
    "/ssp-book-versions/{version_id}/diff",
    operation_id="ssp_book_versions_diff",
    response_model=SspVersionDiffOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed", "not-found"),
)
def ssp_book_versions_diff(
    version_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    against: Annotated[uuid.UUID, Query(description="A version of the same book")],
) -> SspVersionDiffOut:
    """The entries added, removed and changed against another version of the book (REQ-SSP-007)."""
    return SspVersionDiffOut.model_validate(queries.ssp_version_diff(ctx, version_id, against))
