"""Avenmoor Holdings (Demo), WLD-T-01: the builders of PRD §2.5 to §2.7 (BUILD_SPEC RFD-16).

``reference`` builds the structure, periods, FX rates, chart of accounts, account mapping,
customers and products; ``ssp`` the SSP books; ``policies`` the revenue policy templates, the
tenant policy versions and the approval routing and auto-approval rule sets. Personas prepare and
approve as PRD §2.3 assigns their roles, the approver always another persona (WLD-R-02).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Final

from erev_api.problems import Problem

# PRD §2.3 personas acting in the Avenmoor builders.
ACCOUNTANT: Final = "maya"  # Revenue Accountant; SSP Analyst: prepares configuration and SSP books
SSP_APPROVER: Final = "priya"  # Revenue Reviewer; SSP Approver
CONTROLLER: Final = "marcus"  # Controller: approves configuration, opens periods
TENANT_ADMIN: Final = "tomas"  # Tenant Admin: structure and tenant currencies
GO_LIVE: Final = date(2026, 1, 1)  # PRD WLD-P-01
CURRENT_PERIOD_START: Final = date(2026, 9, 1)  # PRD WLD-P-02 Sep 2026


def expect_version(row_version: int) -> Callable[[int], None]:
    """The ``If-Match`` check of a command for the row version the persona just read."""

    def check(current: int) -> None:
        if current != row_version:
            raise Problem("precondition-failed")

    return check


def next_period_start(now: datetime) -> datetime:
    """[J] The first day of the month after tomorrow, at 12:00 UTC so that the date is the same in
    every Avenmoor time zone: the effective start of a period-scoped policy version, which must be a
    future period (04 §16.5; ``registry_versions.period_start_errors``)."""
    day = (now + timedelta(days=1)).date()
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return datetime(year, month, 1, 12, tzinfo=UTC)
