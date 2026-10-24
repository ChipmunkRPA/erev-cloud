"""Disclosure-pack child runs, with explicit month and fiscal-quarter selectors.

The parent orchestrator must persist this plan and child identities in its transaction.
This module queues ordinary authorized report jobs; it does not turn a live report
into a lock snapshot, resolve practical expedients, or publish a completed pack.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select

from erev_api.db.tables import report_run
from erev_api.domain.reports import framework, tie_outs
from erev_api.problems import Problem
from erev_api.schemas.reports import ReportRunCreateIn
from erev_api.uow import UnitOfWork

# The eight core child reports plus the cost rollforward required by section 6.
# Section 7 resolves registry values separately; it is never an invented report run.
SECTIONS: dict[str, tuple[int, ...]] = {
    "revenue_waterfall": (),
    "contract_balances": (2,),
    "contract_balance_rollforward": (2,),
    "revenue_from_opening_liability": (3,),
    "revenue_from_prior_period_obligations": (4,),
    "rpo": (5,),
    "rpo_rollforward": (5,),
    "disaggregation": (1,),
    "contract_cost_rollforward": (6,),
}
POINT_IN_TIME = frozenset({"contract_balances", "rpo"})


@dataclass(frozen=True, slots=True)
class ChildRequest:
    key: str
    sections: tuple[int, ...]
    basis: str
    body: ReportRunCreateIn


@dataclass(frozen=True, slots=True)
class ChildSource:
    key: str
    sections: tuple[int, ...]
    basis: str
    run_id: UUID
    job_id: UUID | None
    parameters_sha256: str


def requests(
    *,
    entity_code: str,
    book: str,
    calendar: tie_outs.Calendar,
    period_key: str,
    known_at: datetime,
    quarter: bool,
    currency_view: str = "transaction",
) -> tuple[ChildRequest, ...]:
    if not entity_code or book not in {"ASC606", "IFRS15"} or known_at.tzinfo is None:
        raise Problem(
            "validation-failed", "Choose one entity, an accounting book and an aware cutoff."
        )
    if currency_view not in {"transaction", "functional"}:
        raise Problem("validation-failed", "Choose transaction or functional disclosure currency.")
    period = calendar.named(period_key, "period_key")
    ranges = [("PERIOD", period)]
    if quarter:
        if period.quarter_no is None:
            raise Problem("validation-failed", "The selected fiscal period has no quarter.")
        quarter_periods = tuple(
            p
            for p in calendar.periods
            if (
                p.fiscal_year == period.fiscal_year
                and p.quarter_no == period.quarter_no
                and p.start <= period.start
            )
        )
        ranges.append(("QUARTER_TO_DATE", quarter_periods[0]))
    common: dict[str, Any] = {
        "entity_codes": [entity_code],
        "book": book,
        "known_at": known_at.astimezone(UTC).isoformat(),
        "known_at_basis": "historical",
        "currency_view": currency_view,
    }
    planned = []
    for code, sections in SECTIONS.items():
        for basis, first in ranges:
            # Closing balances and RPO are the SAME period-end stock in both columns.
            if code in POINT_IN_TIME and basis == "QUARTER_TO_DATE":
                continue
            if code == "contract_balances":
                selectors: dict[str, Any] = {"period_key": period.key, "include_zero": True}
            elif code == "rpo":
                selectors = {"period_key": period.key, "row_dimension": "CONTRACT"}
            else:
                selectors = {"from_period_key": first.key, "to_period_key": period.key}
            if code == "disaggregation":
                selectors.update(dimension_code="revenue_category", include_timing=True)
            if code == "revenue_waterfall":
                selectors.update(
                    row_dimension="REVENUE_CATEGORY",
                    measure="BY_STATE",
                    granularity="MONTH",
                    as_of=period.end.isoformat(),
                )
            planned.append(
                ChildRequest(
                    key=f"{code}:{basis}",
                    sections=sections,
                    basis=basis,
                    body=ReportRunCreateIn(
                        report_code=code, output_format="JSON", parameters={**common, **selectors}
                    ),
                )
            )
    return tuple(planned)


def queue(uow: UnitOfWork, planned: tuple[ChildRequest, ...]) -> tuple[ChildSource, ...]:
    """Queue in the caller's transaction after normal report permission/schema checks.

    The caller owns idempotency and parent attachment. Never call again on retry when
    persisted child IDs already exist. No commits or implicit SYSTEM permissions here.
    """
    if not planned or len({item.key for item in planned}) != len(planned):
        raise Problem("validation-failed", "The disclosure child plan is empty or duplicated.")
    with uow.savepoint():
        queued = []
        for item in planned:
            run_id, job = framework.create_run(uow, item.body)
            row = (
                uow.session.execute(
                    select(report_run).where(
                        report_run.c.tenant_id == uow.principal.tenant_id, report_run.c.id == run_id
                    )
                )
                .mappings()
                .one()
            )
            expected = item.body.parameters
            if (
                row["book_code"] != expected["book"]
                or row["known_at"] != datetime.fromisoformat(expected["known_at"])
                or row["parameters"].get("entity_codes") != expected["entity_codes"]
                or row["parameters"].get("currency_view") != expected["currency_view"]
                or row["period_lock_id"] is not None
            ):
                raise Problem(
                    "validation-failed", "Child normalization changed the disclosure scope."
                )
            queued.append(
                ChildSource(
                    item.key,
                    item.sections,
                    item.basis,
                    run_id,
                    job.id,
                    sha256_hex(row["parameters"]),
                )
            )
    return tuple(queued)
