"""API-R-42 disclosure snapshot register and verified retained detail."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from erev_api.api.deps import API_PREFIX, GuardedRoute, problem_responses
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
from erev_api.db.tables import disclosure_snapshot as snapshot
from erev_api.db.tables import legal_entity, period
from erev_api.domain.contracts import queries
from erev_api.domain.reports import disclosure_queries
from erev_api.enums import BookCode, DisclosureKind
from erev_api.schemas.common import ListOut
from erev_api.schemas.disclosures import DisclosureSnapshotOut, DisclosureSnapshotSummaryOut

router = APIRouter(prefix=API_PREFIX, tags=["API-R-42 Disclosures"], route_class=GuardedRoute)
ReadContext = Annotated[RequestContext, Depends(require("report.run"))]
PROBLEMS = ("unauthenticated", "session-expired", "forbidden", "validation-failed")
SPEC = ListSpec(
    resource="disclosure_snapshots",
    default_sort="-id",
    sort_keys={"id": snapshot.c.id, "created_at": snapshot.c.created_at},
    filters={
        "entity": FilterSpec("entity", legal_entity.c.code, "in"),
        "book": FilterSpec("book", snapshot.c.book_code, "exact", choices=frozenset(BookCode)),
        "period": FilterSpec("period", period.c.period_key, "exact"),
        "disclosure_kind": FilterSpec(
            "disclosure_kind", snapshot.c.disclosure_kind, "in", choices=frozenset(DisclosureKind)
        ),
        "report_run_id": FilterSpec("report_run_id", snapshot.c.report_run_id, "exact"),
    },
)


@router.get(
    "/disclosure-snapshots",
    operation_id="disclosure_snapshots_list",
    response_model=ListOut[DisclosureSnapshotSummaryOut],
    responses=problem_responses(*PROBLEMS),
)
def disclosure_snapshots_list(
    response: Response,
    ctx: ReadContext,
    params: Annotated[ListParams, Depends(list_params)],
    entity: Annotated[list[str] | None, Query()] = None,
    book: Annotated[BookCode | None, Query()] = None,
    period_key: Annotated[str | None, Query(alias="period")] = None,
    disclosure_kind: Annotated[list[DisclosureKind] | None, Query()] = None,
    report_run_id: Annotated[UUID | None, Query()] = None,
) -> ListOut[DisclosureSnapshotSummaryOut]:
    del entity, book, period_key, disclosure_kind, report_run_id
    result = queries.read(
        ctx,
        lambda session: paginate(
            session, disclosure_queries.statement(ctx.principal), SPEC, params
        ),
    )
    response.headers["Cache-Control"] = "no-store"
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = str(result.total_count)
    return ListOut(
        items=[disclosure_queries.summary(row) for row in result.items],
        next_cursor=result.next_cursor,
    )


@router.get(
    "/disclosure-snapshots/{snapshot_id}",
    operation_id="disclosure_snapshots_get",
    response_model=DisclosureSnapshotOut,
    responses=problem_responses(*PROBLEMS, "not-found"),
)
def disclosure_snapshots_get(
    snapshot_id: UUID, response: Response, ctx: ReadContext
) -> DisclosureSnapshotOut:
    response.headers["Cache-Control"] = "no-store"
    return queries.read(
        ctx, lambda session: disclosure_queries.get(session, ctx.principal, snapshot_id)
    )
