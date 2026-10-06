"""API-R-50 Dashboard: the home read model (04 §15.3 API-R-50, §16.13 API-S-DashboardHome, API-C-11;
SCREENS R-02, §2.5; BUILD_SPEC RPS-17)."""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import APIRouter, Depends, Query

from erev_api.api.deps import API_PREFIX, GuardedRoute, KernelDeps, kernel_deps, problem_responses
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.domain.reports import dashboard
from erev_api.enums import BookCode
from erev_api.schemas.dashboard import DashboardHomeOut

TAG: Final = "API-R-50 Dashboard"

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


@router.get(
    "/dashboard/home",
    operation_id="dashboard_home",
    response_model=DashboardHomeOut,
    responses=problem_responses(
        "unauthenticated", "session-expired", "forbidden", "validation-failed"
    ),
)
def dashboard_home(
    ctx: Annotated[RequestContext, Depends(require(dashboard.READ_PERMISSION))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
    entity: Annotated[
        list[str] | None,
        Query(description="Entity code or id; repeatable. Default: every entity in scope"),
    ] = None,
    period: Annotated[
        str | None,
        Query(description="Period key or id. Default: the earliest open period of the entities"),
    ] = None,
    book: Annotated[BookCode | None, Query(description="Default: the primary book")] = None,
) -> DashboardHomeOut:
    """Revenue, contract liability, RPO, pending approvals, open exceptions, close status and the
    revenue chart for the context entities, book and period (SCREENS §2.5)."""
    return dashboard.read_home(
        ctx,
        clock=deps.clock,
        keyring=deps.keyring,
        files=deps.files,
        entities=entity or (),
        book=None if book is None else book.value,
        period_value=period,
    )
