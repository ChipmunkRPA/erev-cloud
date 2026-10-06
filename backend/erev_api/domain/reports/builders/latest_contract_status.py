"""RPT-11 ``latest_contract_status`` Latest contract status (SCREENS_B §5.6.2 RPT-11; 04 §17.1
rule 1, T-CON-09; legacy 06 §7.3 TC-REP-03, TC-REP-07, FX-07; DEVIATIONS DEV-024; 03 REQ-RPT-013;
BUILD_SPEC RPS-5).

Rows: the obligation versions of each combination group's latest contract version effective on or
before ``as_of`` (``contract_history.latest_where``), one row ``obligation:<external id>:<key>``
each, in contract external id and line order. A backdated event is reported by its effective date,
not by the order it was processed in (TC-REP-07; DEV-024). "Version" is the version's number along
the contract's chain (``contract_history.chain_numbers``; item RPT-FORMER-GROUP-READERS-1). A
contract enters the report on the day it is activated (SCREENS_B RPT-11 rev 1.70; ENGINE_SPEC_B
S15-R-24a rev 1.161; item RPT-RPO-ROLLFWD-1): its first included version counts from that date,
as in the RPO report, and every figure of the row is read at ``as_of`` (below). The legacy export
RPT-12 keeps the stored rule (``latest_rows(entered=False)``).

**One date** (SCREENS_B RPT-11 rev 1.55; item RPT-ASOF-FIGURES-1; supervisor ruling R-116 (c)
(4)). A row states the obligation at ``as_of``, every figure of it: the reported allocation, the
revenue and billing to date, the remaining allocation, the scheduled and the awaiting-trigger
amount and the status are read at the cut of ``as_of`` through the reader of the contract reads
(``reports.cuts``; 04 API-C-10), and so are the balance columns — ``contract_liability`` and
``contract_asset_and_unbilled`` (contract asset plus unbilled receivable) of the member contract
and contracting entity. ``effective_date`` and ``version_no`` name the version the row is read
from; ``remaining_quantity`` is the version's, a quantity moves with an event. Before this
revision the money columns were the version's stored columns, the state at its effective date,
beside the stored balances of its latest period: revenue 219.18 at 1 January beside an asset of
59,835.62 at 30 September in one row. ``latest_rows`` stays the stored population — the legacy
export RPT-12 prints the version as the legacy system did.

Control totals: per currency, the money columns summed over the rows, and the two balance columns
once per member contract and entity; ``row_count``, ``contract_count`` and ``as_of``. No tie-out.

[J] ``as_of`` defaults to the last day of the period holding the run's as-of date
(``contract_history.default_dates``). The totals are control totals, not a totals row, so the row
count is the number of obligations (SCREENS_B RPT-11 sample: 17 rows).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract_version_balance, legal_entity
from erev_api.domain.contracts import to_date
from erev_api.domain.reports import cuts, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_history as history
from erev_api.domain.reports.legacy_columns import decimal_text
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, add
from erev_api.uow import UnitOfWork

CODE: Final = "latest_contract_status"
MONEY: Final = (
    "allocated_amount",
    "revenue_cum",
    "billed_cum",
    "remaining_allocation",
    "scheduled_amount",
    "awaiting_trigger_amount",
)
BALANCES: Final = ("contract_liability", "contract_asset_and_unbilled")
COLUMNS: Final = (
    Column("contract_external_id", "Contract", "code"),
    Column("obligation_key", "Obligation", "code"),
    Column("product_code", "Product", "code"),
    Column("entity_code", "Entity", "code"),
    Column("version_no", "Version", "integer"),
    Column("effective_date", "Effective date", "date"),
    Column("currency", "Currency", "code"),
    Column("allocated_amount", "Allocated", "money"),
    Column("revenue_cum", "Revenue to date", "money"),
    Column("billed_cum", "Billed to date", "money"),
    Column("remaining_quantity", "Remaining quantity", "decimal"),
    Column("remaining_allocation", "Remaining allocation", "money"),
    Column("scheduled_amount", "Scheduled", "money"),
    Column("awaiting_trigger_amount", "Awaiting trigger", "money"),
    Column("contract_liability", "Contract liability", "money"),
    Column("contract_asset_and_unbilled", "Contract asset and unbilled receivable", "money"),
    Column("satisfaction_status", "Status", "text"),
)

type BalanceKey = tuple[UUID, UUID, UUID]  # (contract version, contract, entity)


def as_of_date(session: Session, params: ReportParams) -> date:
    if params.as_of_date is not None:
        return params.as_of_date
    return history.default_dates(session, params, year=False)[1]


def latest_rows(
    session: Session, params: ReportParams, *, book_code: str, entered: bool = False
) -> list[dict[str, Any]]:
    """The population of the latest rule at the run's ``as_of`` (module docstring); with
    ``entered`` — RPT-11 — a contract's first included version counts from its activation."""
    as_of = as_of_date(session, params)
    return history.population(
        session,
        params,
        book_code=book_code,
        where=history.latest_where(
            session, params, book_code=book_code, as_of=as_of, entered=entered
        ),
    )


def _balance_key(row: Mapping[str, Any]) -> BalanceKey:
    return (
        UUID(str(row["contract_version_id"])),
        UUID(str(row["contract_id"])),
        UUID(str(row["contracting_entity_id"])),
    )


def _balance_rows(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The T-CON-09 rows of the population's versions, each with its entity's code."""
    version_ids = sorted({UUID(str(row["contract_version_id"])) for row in rows}, key=str)
    if not version_ids:
        return []
    statement = (
        select(contract_version_balance, legal_entity.c.code.label("entity_code"))
        .select_from(
            contract_version_balance.join(
                legal_entity,
                (legal_entity.c.tenant_id == contract_version_balance.c.tenant_id)
                & (legal_entity.c.id == contract_version_balance.c.entity_id),
            )
        )
        .where(contract_version_balance.c.contract_version_id.in_(version_ids))
    )
    return [dict(item) for item in session.execute(statement).mappings()]


def _balances(
    found: cuts.Versions,
    rows: Sequence[Mapping[str, Any]],
    balance_rows: Sequence[Mapping[str, Any]],
    as_of: date,
) -> dict[BalanceKey, tuple[Decimal, Decimal]]:
    """Contract liability, and contract asset plus unbilled receivable, at the cut of ``as_of``
    for each (contract version, contract, entity) the population names."""
    wanted = {_balance_key(row) for row in rows}
    balances: dict[BalanceKey, tuple[Decimal, Decimal]] = {}
    for item in balance_rows:
        key = (
            UUID(str(item["contract_version_id"])),
            UUID(str(item["contract_id"])),
            UUID(str(item["entity_id"])),
        )
        if key not in wanted:
            continue
        at = found.balance(item, as_of).values
        balances[key] = (
            at["contract_liability"],
            at["contract_asset"] + at["unbilled_receivable"],
        )
    return balances


def _at_as_of(row: Mapping[str, Any], at: to_date.ObligationAt) -> dict[str, Decimal]:
    """The money columns of a row at the cut (module docstring "One date"; 04 API-C-10)."""
    moved = at.delta + at.shift
    return {
        "allocated_amount": Decimal(row["allocated_amount"]) - at.shift,
        "revenue_cum": at.revenue,
        "billed_cum": at.billed,
        "remaining_allocation": Decimal(row["remaining_allocation"]) - moved,
        "scheduled_amount": at.scheduled,
        "awaiting_trigger_amount": at.awaiting,
    }


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    as_of = as_of_date(session, params)
    rows = latest_rows(session, params, book_code=book_code, entered=True)
    found = cuts.load(
        session, {UUID(str(row["contract_version_id"])) for row in rows}, (as_of,), balances=True
    )
    balances = _balances(found, rows, _balance_rows(session, rows), as_of)
    cut: dict[UUID, Mapping[UUID, to_date.ObligationAt]] = {}
    items: list[dict[str, Any]] = []
    totals: dict[str, dict[str, Decimal]] = {}
    counted: set[BalanceKey] = set()
    for row in rows:
        currency = str(row["txn_currency"]).strip()
        external_id = str(row["contract_external_id"])
        key = _balance_key(row)
        liability, asset = balances.get(key, (ZERO, ZERO))
        version_id = UUID(str(row["contract_version_id"]))
        if version_id not in cut:
            cut[version_id] = found.at(version_id, as_of)
        at = cut[version_id][UUID(str(row["id"]))]
        figures = _at_as_of(row, at)
        items.append(
            {
                "row_key": f"obligation:{external_id}:{row['obligation_key']}",
                "contract_external_id": external_id,
                "obligation_key": str(row["obligation_key"]),
                "product_code": str(row["product_code"]),
                "entity_code": str(row["entity_code"]),
                "version_no": int(row["chain_version_no"]),
                "effective_date": row["effective_date"],
                "currency": currency,
                **{name: tie_outs.money(figures[name], currency) for name in MONEY},
                "remaining_quantity": decimal_text(row["remaining_quantity"]),
                "contract_liability": tie_outs.money(liability, currency),
                "contract_asset_and_unbilled": tie_outs.money(asset, currency),
                "satisfaction_status": history.status_text(at.satisfaction_status),
            }
        )
        into = totals.setdefault(currency, {})
        for name in MONEY:
            add(into, name, figures[name])
        if key not in counted:
            counted.add(key)
            add(into, "contract_liability", liability)
            add(into, "contract_asset_and_unbilled", asset)
    control: dict[str, Any] = {
        name: tie_outs.by_currency(
            {code: values.get(name, ZERO) for code, values in totals.items()}
        )
        for name in (*MONEY, *BALANCES)
    }
    control["row_count"] = len(items)
    control["contract_count"] = len({item["contract_external_id"] for item in items})
    control["as_of"] = as_of.isoformat()
    return ReportData(columns=COLUMNS, rows=tuple(items), control_totals=control)
