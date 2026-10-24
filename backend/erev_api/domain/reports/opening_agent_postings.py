"""Original net postings, including supplier reallocations with no gross control movement."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import subledger_line
from erev_api.domain.reports import revenue_attribution, revenue_roles, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.contract_balance_rollforward import Entry, Flow
from erev_api.uow import UnitOfWork

MEMBERS = "agent_opening_net_posting"


def read(
    uow: UnitOfWork,
    params: ReportParams,
    book: str,
    periods: Mapping[UUID, tuple[tie_outs.PeriodRef, ...]],
    *,
    view: str,
) -> dict[tuple[UUID, UUID], list[Entry]]:
    rows = (
        uow.session.execute(
            select(subledger_line)
            .where(
                subledger_line.c.book_code == book,
                subledger_line.c.entity_id.in_(params.entity_ids),
                subledger_line.c.period_id.in_([p.id for ps in periods.values() for p in ps]),
                subledger_line.c.account_role == "REVENUE",
                subledger_line.c.entry_kind == "REVENUE_RECOGNITION",
                tie_outs.line_recorded_by(params, params.known_at),
                *tie_outs.bound_member_where(params, MEMBERS, subledger_line.c.id),
            )
            .order_by(subledger_line.c.id)
        )
        .mappings()
        .all()
    )
    tie_outs.require_members(params, MEMBERS, [r["id"] for r in rows])
    tie_outs.record_members(params, MEMBERS, [r["id"] for r in rows])
    result: dict[tuple[UUID, UUID], list[Entry]] = {}
    for row in rows:
        result.setdefault((row["contract_id"], row["entity_id"]), []).append(
            Entry(
                order=(str(row["id"]),),
                flow=Flow(
                    -Decimal(row["amount_txn" if view == "transaction" else "amount_functional"]),
                    True,
                ),
                period_id=row["period_id"],
                entry_kind=row["entry_kind"],
                line_id=row["id"],
                subject_key=row["subject_key"],
            )
        )
    return result


def supplier_pair(
    uow: UnitOfWork,
    line_id: UUID,
    *,
    view: str,
) -> tuple[Sequence[Mapping[str, Any]], revenue_attribution.AmountProof]:
    net = (
        uow.session.execute(select(subledger_line).where(subledger_line.c.id == line_id))
        .mappings()
        .one()
    )
    lines = (
        uow.session.execute(
            select(subledger_line)
            .where(
                subledger_line.c.subledger_posting_id == net["subledger_posting_id"],
                subledger_line.c.entry_no == net["entry_no"],
            )
            .order_by(subledger_line.c.id)
        )
        .mappings()
        .all()
    )
    suppliers = [row for row in lines if revenue_roles.is_supplier(row)]
    if len(lines) != 2 or len(suppliers) != 1 or net["account_role"] != "REVENUE":
        raise ValueError("Unmatched agent net posting lacks one original supplier counterpart.")
    supplier = suppliers[0]
    if any(
        supplier[key] != net[key]
        for key in (
            "contract_id",
            "entity_id",
            "subject_key",
            "contract_version_id",
            "period_id",
            "origin_period_id",
            "book_code",
            "txn_currency",
            "functional_currency",
            "entry_kind",
        )
    ) or any(net[key] + supplier[key] != 0 for key in ("amount_txn", "amount_functional")):
        raise ValueError("Agent net-only posting and supplier counterpart do not reconcile.")
    proof = revenue_attribution.verify_component(uow, supplier["id"], view=view)
    field = "amount_txn" if view == "transaction" else "amount_functional"
    if proof.amount != supplier[field]:
        raise ValueError("Agent supplier amount differs from its original evidence.")
    return [dict(line) for line in lines], proof
