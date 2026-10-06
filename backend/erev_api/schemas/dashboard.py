"""API-R-50 dashboard schemas: API-S-DashboardHome (04 §16.13; SCREENS R-02, §2.5, §2.6; BUILD_SPEC
RPS-17)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from erev_api.enums import BookCode, PeriodState
from erev_api.money import MoneyOut
from erev_api.schemas.common import RefOut
from erev_api.schemas.periods import CloseRunRefOut, PeriodBlockersOut


class DashboardPeriodOut(BaseModel):
    period_key: str
    name: str
    end_date: date


class DashboardContextOut(BaseModel):
    """``entity`` is null unless exactly one entity is named; ``currency`` is that entity's
    functional currency, else the tenant reporting currency (API-C-11 ``currency_view``)."""

    entity: RefOut | None
    book: BookCode
    period: DashboardPeriodOut
    currency: str
    known_at: datetime


class RevenueTrendOut(BaseModel):
    period_key: str
    recognized: MoneyOut


class DashboardRevenueOut(BaseModel):
    """Recognised revenue of the context period and the period before; ``change_ratio`` is
    (current − prior) ÷ absolute prior, null when prior is 0 or absent."""

    current: MoneyOut
    prior: MoneyOut | None
    change_ratio: str | None
    trend: list[RevenueTrendOut]


class DashboardContractLiabilityOut(BaseModel):
    closing: MoneyOut
    opening: MoneyOut


class DashboardRpoOut(BaseModel):
    total: MoneyOut
    within_12_months: MoneyOut


class DashboardPendingApprovalsOut(BaseModel):
    count: int
    oldest_submitted_at: datetime | None


class DashboardOpenExceptionsOut(BaseModel):
    total: int
    blocking: int
    warning: int
    info: int


class DashboardCloseOut(BaseModel):
    """API-S-Period ``id``, ``state``, ``blockers`` and ``close_run`` of the context entity's
    period. ``id`` (04 §16.13, rev 1.206) is what the row "Exceptions holding the lock" passes
    to the exception list as ``blocking`` (SCREENS §2.6, rev 1.37)."""

    id: uuid.UUID
    state: PeriodState
    blockers: PeriodBlockersOut
    close_run: CloseRunRefOut | None


class RevenueChartPeriodOut(BaseModel):
    """``total`` is recognized plus scheduled (L7-2-Q-21: DG-FE-08 adds no money in the browser)."""

    period_key: str
    recognized: MoneyOut
    scheduled: MoneyOut
    total: MoneyOut


class RevenueChartTotalsOut(BaseModel):
    """DS-CH-01 Table view totals row over ``periods`` and the awaiting trigger (L7-2-Q-21)."""

    recognized: MoneyOut
    scheduled: MoneyOut
    awaiting_trigger: MoneyOut
    total: MoneyOut


class RevenueChartOut(BaseModel):
    periods: list[RevenueChartPeriodOut]
    awaiting_trigger: MoneyOut
    pending_trigger_count: int
    totals: RevenueChartTotalsOut


class DashboardHomeOut(BaseModel):
    """API-S-DashboardHome (``GET /dashboard/home``)."""

    context: DashboardContextOut
    revenue: DashboardRevenueOut
    contract_liability: DashboardContractLiabilityOut
    rpo: DashboardRpoOut
    pending_approvals: DashboardPendingApprovalsOut
    open_exceptions: DashboardOpenExceptionsOut
    close: DashboardCloseOut | None
    revenue_chart: RevenueChartOut
