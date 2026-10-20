"""Transaction opening relief follows the retained combination group's control path."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from decimal import Decimal, localcontext
from typing import Any
from uuid import UUID

from erev_engine.money import DECIMAL_CONTEXT
from sqlalchemy import select

from erev_api.db.tables import subledger_line
from erev_api.domain.reports import locked_ends, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_balance_rollforward as rollforward
from erev_api.domain.reports.opening_relief_currency import finish
from erev_api.domain.reports.outputs import ReportData
from erev_api.uow import UnitOfWork

KEY = "opening_relief_transaction_v1"
ZERO = Decimal(0)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    with localcontext(DECIMAL_CONTEXT):
        return _build(uow, params)


def _build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book = tie_outs.book_of(session, params)
    entities, periods, before = rollforward.ranges(session, params)
    if params.binding is None:
        negative = session.execute(
            select(subledger_line.c.id)
            .where(
                subledger_line.c.book_code == book,
                subledger_line.c.entity_id.in_(list(params.entity_ids)),
                subledger_line.c.period_id.in_([p.id for items in periods.values() for p in items]),
                subledger_line.c.account_role == rollforward.LIABILITY_ROLE,
                subledger_line.c.entry_kind.in_(rollforward.REVENUE_KINDS),
                subledger_line.c.amount_txn < 0,
                tie_outs.line_recorded_by(params, params.known_at),
            )
            .limit(1)
        ).scalar_one_or_none()
        if negative is not None:
            from .builders.revenue_from_opening_liability import legacy_build

            # Preserve the existing net-reversal calculation until original
            # reversal attribution is available, rather than rejecting old use cases.
            tie_outs.record_evidence(params, "opening_relief_legacy_negative_v1", True)
            return legacy_build(uow, params)
    cutoff = tie_outs.cutoff_for(session, params)
    locked = locked_ends.Reader(
        uow,
        params,
        book_code=book,
        cutoff=cutoff,
        entity_codes={entity.id: entity.code for entity in entities},
    )
    traces: dict[UUID, tie_outs.TracedBalances] = {}

    def balances(at: Mapping[UUID, tie_outs.PeriodRef | None]) -> tuple[tie_outs.BalanceRow, ...]:
        return tie_outs.balances_at(
            session,
            entity_ids=params.entity_ids,
            book_code=book,
            period_keys=at,
            cutoff=cutoff,
            params=params,
            traces=traces,
            locked_ends=locked,
        )

    opening = balances(before)
    closing = balances({key: (items[-1] if items else None) for key, items in periods.items()})
    selected = {(row.contract_id, row.entity_id): row for row in (*opening, *closing)}
    posted = rollforward._lines(
        session,
        params.entity_ids,
        book,
        periods,
        params.known_at,
        None,
        params=params,
        functional=False,
    )
    documents = rollforward._billing(
        session,
        rows=selected,
        posted=posted,
        periods=periods,
        before=before,
        traces=traces,
        cutoff=cutoff,
        params=params,
        locked=locked,
    )
    # A version identifies the original computation's combination membership;
    # never substitute today's group table for the selected report version.
    groups: dict[tuple[UUID, UUID, str], list[tuple[UUID, UUID]]] = defaultdict(list)
    for member, row in selected.items():
        groups[(row.version_id, row.entity_id, row.currency)].append(member)
    open_rows = {(row.contract_id, row.entity_id): row for row in opening}
    close_rows = {(row.contract_id, row.entity_id): row for row in closing}
    contracts: list[dict[str, Any]] = []
    totals: dict[str, dict[str, Decimal]] = {}
    membership: dict[str, list[str]] = {}
    for (version, entity, currency), members in groups.items():
        first = {
            name: sum((open_rows[key].value(name) for key in members if key in open_rows), ZERO)
            for name in tie_outs.ROLLFORWARD_BALANCES
        }
        last = {
            name: sum((close_rows[key].value(name) for key in members if key in close_rows), ZERO)
            for name in tie_outs.ROLLFORWARD_BALANCES
        }
        entries = sorted(
            (
                (key, entry)
                for key in members
                for entry in (*posted.get(key, ()), *documents.get(key, ()))
            ),
            key=lambda pair: (pair[1].order, selected[pair[0]].external_id),
        )
        # A negative recognition needs reversal provenance; assigning a credit to
        # a new billing layer would erase which opening release it reverses.
        if any(entry.flow.is_revenue and entry.flow.amount < 0 for _, entry in entries):
            raise tie_outs.invalid(
                "currency_view", "Opening relief reversal requires original source replay."
            )
        attribution: dict[int, Decimal] = {}
        path = rollforward.path(
            first, [entry.flow for _, entry in entries], last, opening_relief=attribution
        )
        if any(path["OTHER"][name] != 0 for name in tie_outs.ROLLFORWARD_BALANCES):
            raise tie_outs.invalid(
                "currency_view", "Transaction opening relief requires a reconciled group path."
            )
        recognized: dict[tuple[UUID, UUID], Decimal] = defaultdict(Decimal)
        relief: dict[tuple[UUID, UUID], Decimal] = defaultdict(Decimal)
        for index, (member, entry) in enumerate(entries):
            if entry.flow.is_revenue:
                recognized[member] += entry.flow.amount
                relief[member] += attribution.get(index, ZERO)
        membership[f"{version}:{entity}:{currency}"] = sorted(str(member[0]) for member in members)
        for member in members:
            row = selected[member]
            amount = open_rows[member].value("contract_liability") if member in open_rows else ZERO
            if amount == 0 and recognized[member] == 0 and relief[member] == 0:
                continue
            contracts.append(
                {
                    "row_key": f"contract:{row.external_id}:{row.entity_code}",
                    "section": 2,
                    "contract_external_id": row.external_id,
                    "customer_name": row.customer_name,
                    "entity_code": row.entity_code,
                    "currency": currency,
                    "opening_contract_liability": tie_outs.money(amount, currency),
                    "revenue_recognized": tie_outs.money(recognized[member], currency),
                    "revenue_from_opening": tie_outs.money(relief[member], currency),
                }
            )
            group = totals.setdefault(currency, {})
            for name, value in (
                ("opening", amount),
                ("revenue", recognized[member]),
                ("relief", relief[member]),
            ):
                tie_outs.add(group, name, value)
    if (
        params.binding is not None
        and params.binding.evidence["opening_relief_groups_v1"] != membership
    ):
        raise tie_outs.invalid(
            "currency_view", "Opening-relief member population differs from retained evidence."
        )
    tie_outs.record_evidence(params, "opening_relief_groups_v1", membership)
    contracts.sort(key=lambda row: row["row_key"])
    return finish(
        uow,
        params,
        contracts=contracts,
        totals=totals,
        entities=entities,
        periods=periods,
        book=book,
        view="transaction",
        rates=[],
        source_key=KEY,
        legacy_contract_footnote=all(len(members) == 1 for members in groups.values()),
    )
