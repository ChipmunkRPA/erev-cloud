"""API-R-36 Subledger: detail lines and postings.

04 §15.3 API-R-36, §16 API-S-SubledgerLine, API-C-09 to API-C-11; T-SL-01 to T-SL-04; BUILD_SPEC
CTR-3. Reads need ``contract.read``; row-level security scopes lines to the caller's entities.
``GET /subledger-lines`` filters by ``entity`` (code or id, repeatable), ``book`` (default the
primary book), ``period`` and ``origin_period`` (period key or id), ``account_role``, ``contract``
and ``known_at`` (lines recorded by then).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Select
from sqlalchemy.orm import Session

from erev_api.api.deps import (
    API_PREFIX,
    GuardedRoute,
    KernelDeps,
    kernel_deps,
    problem_responses,
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
from erev_api.db.tables import subledger_line
from erev_api.domain.journals import subledger
from erev_api.enums import AccountRole, BookCode
from erev_api.schemas.common import ListOut
from erev_api.schemas.subledger import SubledgerLineOut, SubledgerPostingOut

TAG: Final = "API-R-36 Subledger"
READ_PERMISSION: Final = "contract.read"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
LINE_LIST: Final = ListSpec(
    resource="subledger-lines",
    sort_keys={"id": subledger_line.c.id, "recorded_at": subledger_line.c.recorded_at},
    default_sort="-id",
    filters={
        "account_role": FilterSpec(
            name="account_role",
            column=subledger_line.c.account_role,
            kind="exact",
            choices=frozenset(role.value for role in AccountRole),
        )
    },
    custom_filters=frozenset({"entity", "book", "period", "origin_period", "contract", "known_at"}),
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


@router.get(
    "/subledger-lines",
    operation_id="subledger_lines_list",
    response_model=ListOut[SubledgerLineOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def subledger_lines_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
    params: Annotated[ListParams, Depends(list_params)],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
    entity: Annotated[list[str] | None, Query(description="Entity code or id; repeatable")] = None,
    book: Annotated[BookCode | None, Query(description="Default the primary book")] = None,
    period: Annotated[str | None, Query(description="Period key or id")] = None,
    origin_period: Annotated[str | None, Query(description="Period key or id")] = None,
    account_role: Annotated[AccountRole | None, Query()] = None,
    contract: Annotated[uuid.UUID | None, Query()] = None,
    known_at: Annotated[datetime | None, Query(description="Lines recorded by then")] = None,
) -> ListOut[SubledgerLineOut]:
    """The workspace's subledger lines; sort ``id`` (default ``-id``) or ``recorded_at``. Each
    line names the journal run that journalises it (``journal_run_id``, 04 rev 1.288)."""
    del account_role  # applied by ``paginate`` through LINE_LIST
    if known_at is not None and known_at.utcoffset() is None:
        raise invalid("known_at", "Send known_at as an RFC 3339 timestamp with an offset.")
    filters = subledger.LineFilters(
        entity=tuple(entity or ()),
        book=None if book is None else book.value,
        period=period,
        origin_period=origin_period,
        contract=contract,
        known_at=known_at,
    )

    def page(session: Session, statement: Select[Any]) -> tuple[ListResult, list[SubledgerLineOut]]:
        result = paginate(session, statement, LINE_LIST, params)
        runs = subledger.journal_runs_of(
            session, result.items, files=deps.files, keyring=deps.keyring
        )
        return result, subledger.line_outs(result.items, runs)

    result, items = subledger.list_lines(ctx, filters, page=page)
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[SubledgerLineOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/subledger-postings/{posting_id}",
    operation_id="subledger_postings_get",
    response_model=SubledgerPostingOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found"),
)
def subledger_postings_get(
    posting_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require(READ_PERMISSION))],
) -> SubledgerPostingOut:
    """A posting with its seal, chain sequence and control totals."""
    return subledger.get_posting(ctx, posting_id)
