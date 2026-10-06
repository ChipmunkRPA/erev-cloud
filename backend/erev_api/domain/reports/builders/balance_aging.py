"""RPT-36 ``balance_aging`` Balance aging (SCREENS_B §5.6.1 RPT-36; POLICIES §5.7 CHK-117, POL-125;
03 REQ-BIL-013; BUILD_SPEC RPS-12).

One row per contract and balance role with a non-zero balance at the end of ``period_key``,
``row_key`` ``contract:<external id>:<role>``, the amount by age bucket (0 to 30, 31 to 90, 91 to
180, 181 to 365, over 365 days) and its total. The age of an amount is the number of days from
the effective date of the layer it belongs to (T-CON-18 layer movements) to the period end.

The pure half (``bucket_of``, ``open_layers``, ``aged_rows``, ``aging_tie``) is what the tests
prove: first in, first out consumption of layers, the bucket boundaries and the tie-out
``TO_AGING_EQ_BALANCES`` (Σ aged amounts per currency equal the presented balances of
``tie_outs.balances_at``).

INTERIM SOURCE (supervisor ruling Q-2, `docs/reviews/loop/prod/F-RPS-ENG-E1-prep.md` §9): ``build``
reads the layers from what main persists today. T-CON-18 ``fx_layer_movement`` (the catalogue
source) is not persisted until CTR-14; until then the source is the T-SL-04 subledger: for
``CONTRACT_LIABILITY`` the credit lines create layers dated by their effective date and the debits
consume them first in first out; for ``CONTRACT_ASSET`` and ``UNBILLED_RECEIVABLE`` the JET-06
``NETTING_RECLASS`` debits are the attributions, each dated by the latest ``REVENUE_RECOGNITION``
line of its obligation (CHK-117: "the effective date of the latest revenue event of its
obligation"), and the credits (the S10-R-22 reversals) consume them. Totals per role and
currency are the rows ``TOTAL:<role>:<ISO>`` (accepted, ruling Q-2). This builder is not registered
in ``framework.BUILDERS`` until its database tests have passed in an admitted run (registration is
user-visible; ruling Q-2); the swap of the source to ``fx_layer_movement`` follows CTR-14.

NOT REGISTERED (BUILD_SPEC RPS-12, lane F-RPS-REG, 2026-09-30): the database acceptance
``tests/domain/reports/test_analysis_reports.py::test_balance_aging_chk_010`` builds the CHK-010
contract through the product's commands and cannot pass on the interim source. (1) The JET-06
netting reclass is a time-driven amount of the close run's ``NETTING_RECLASS`` pass (05 RCP-08
(b)); no command creates a close run before CLO-19 / CLO-20, so the subledger holds no
``NETTING_RECLASS`` line and the asset roles have no attribution to age. (2) Under
``billing.posting = ERP`` (POL-004) the engine posts no invoice, so the subledger's
``CONTRACT_LIABILITY`` lines are the revenue debits alone and the liability layers come out
negative. On that contract ``build`` returns one row "Contract liability (14,000.00)" and
``TO_AGING_EQ_BALANCES`` fails (expected 5,000.00). The presented balances, the JET-06 targets per
obligation and period (``netting_reclass_amount``) and the liability layers
(``fx_layer_created``, ``fx_layer_consumed``) are in the calc trace (T-ENG-03); reading them would
replace the source ruling Q-2 accepted and waits for the supervisor.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from erev_api.db.tables import subledger_line
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders.contract_balance_rollforward import FUNCTIONAL_ONLY
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, BalanceRow, EntityRef, PeriodRef, add
from erev_api.uow import UnitOfWork

CODE: Final = "balance_aging"
TO_AGING_EQ_BALANCES: Final = tie_outs.TO_AGING_EQ_BALANCES
ROLES: Final = ("CONTRACT_ASSET", "UNBILLED_RECEIVABLE", "CONTRACT_LIABILITY")
ROLE_MEASURES: Final[Mapping[str, str]] = {
    "CONTRACT_ASSET": "contract_asset",
    "UNBILLED_RECEIVABLE": "unbilled_receivable",
    "CONTRACT_LIABILITY": "contract_liability",
}
ROLE_LABELS: Final[Mapping[str, str]] = {
    "CONTRACT_ASSET": "Contract asset",
    "UNBILLED_RECEIVABLE": "Unbilled receivable",
    "CONTRACT_LIABILITY": "Contract liability",
}
# (field, first day, last day); None: no upper bound.
BUCKETS: Final[tuple[tuple[str, int, int | None], ...]] = (
    ("bucket_0_30", 0, 30),
    ("bucket_31_90", 31, 90),
    ("bucket_91_180", 91, 180),
    ("bucket_181_365", 181, 365),
    ("bucket_over_365", 366, None),
)
BUCKET_FIELDS: Final = tuple(field for field, _, _ in BUCKETS)
TOTAL_PREFIX: Final = "TOTAL:"
REVENUE_KIND: Final = "REVENUE_RECOGNITION"
NETTING_RECLASS: Final = "NETTING_RECLASS"
NETTING_REVERSAL: Final = "NETTING_RECLASS_REVERSAL"
COLUMNS: Final = (
    Column("contract_external_id", "Contract", "code"),
    Column("customer_name", "Customer", "text"),
    Column("entity_code", "Entity", "code"),
    Column("balance_role", "Balance", "text"),
    Column("currency", "Currency", "code"),
    Column("bucket_0_30", "0 to 30 days", "money"),
    Column("bucket_31_90", "31 to 90 days", "money"),
    Column("bucket_91_180", "91 to 180 days", "money"),
    Column("bucket_181_365", "181 to 365 days", "money"),
    Column("bucket_over_365", "Over 365 days", "money"),
    Column("total", "Total", "money"),
)


@dataclass(frozen=True, slots=True)
class Layer:
    """An open amount of one balance role of one contract and entity, aged from its date."""

    contract_id: UUID
    external_id: str
    customer_name: str | None
    entity_id: UUID
    entity_code: str
    balance_role: str
    currency: str
    amount: Decimal
    effective_date: date


@dataclass(frozen=True, slots=True)
class AgedRow:
    contract_id: UUID
    external_id: str
    customer_name: str | None
    entity_id: UUID
    entity_code: str
    balance_role: str
    currency: str
    buckets: Mapping[str, Decimal]

    @property
    def total(self) -> Decimal:
        return sum(self.buckets.values(), ZERO)

    @property
    def row_key(self) -> str:
        return f"contract:{self.external_id}:{self.balance_role}"


def bucket_of(age_days: int) -> str:
    """The bucket of an age in days; an amount dated after the as-of date (negative age) ages 0."""
    for field, _, last in BUCKETS:
        if last is None or age_days <= last:
            return field
    return BUCKET_FIELDS[-1]


def open_layers(flows: Iterable[tuple[date, Decimal]]) -> list[tuple[date, Decimal]]:
    """First in, first out (POL-126 ``FIFO_WITHIN_CONTRACT``): a positive flow opens a layer dated
    by its effective date; a negative flow consumes the oldest open POSITIVE layers, past any
    earlier negative layer (Codex review of 642363e, R2). A consumption beyond the open positive
    layers leaves a negative layer dated by that flow (a debit position the presentation nets
    elsewhere), so the sum of the result always equals the sum of the flows."""
    layers: list[tuple[date, Decimal]] = []
    for day, amount in flows:
        if amount > 0:
            layers.append((day, amount))
            continue
        remaining = -amount
        index = 0
        while remaining > 0 and index < len(layers):
            layer_day, layer_amount = layers[index]
            if layer_amount <= 0:
                index += 1
                continue
            taken = min(layer_amount, remaining)
            remaining -= taken
            if taken == layer_amount:
                layers.pop(index)
            else:
                layers[index] = (layer_day, layer_amount - taken)
        if remaining > 0:
            layers.append((day, -remaining))
    return layers


def aged_rows(layers: Sequence[Layer], as_of: Mapping[UUID, date]) -> tuple[AgedRow, ...]:
    """One row per (contract, entity, role) with a non-zero total, external id then entity code
    then role order; ``as_of`` is the period end per entity id."""
    grouped: dict[tuple[str, str, int, UUID, UUID], list[Layer]] = {}
    for layer in layers:
        key = (
            layer.external_id,
            layer.entity_code,
            ROLES.index(layer.balance_role),
            layer.contract_id,
            layer.entity_id,
        )
        grouped.setdefault(key, []).append(layer)
    rows: list[AgedRow] = []
    for key in sorted(grouped, key=lambda item: item[:3]):
        items = grouped[key]
        buckets = dict.fromkeys(BUCKET_FIELDS, ZERO)
        for layer in items:
            age = (as_of[layer.entity_id] - layer.effective_date).days
            buckets[bucket_of(age)] += layer.amount
        if sum(buckets.values(), ZERO) == 0:
            continue  # SCREENS_B RPT-36: rows carry a non-zero balance (R2)
        first = items[0]
        rows.append(
            AgedRow(
                contract_id=first.contract_id,
                external_id=first.external_id,
                customer_name=first.customer_name,
                entity_id=first.entity_id,
                entity_code=first.entity_code,
                balance_role=first.balance_role,
                currency=first.currency,
                buckets=buckets,
            )
        )
    return tuple(rows)


def total_rows(rows: Sequence[AgedRow]) -> list[dict[str, Any]]:
    """Totals per balance role and currency: ``TOTAL:<role>:<ISO>`` (SCREENS_B RPT-36)."""
    totals: dict[tuple[int, str], dict[str, Decimal]] = {}
    for row in rows:
        into = totals.setdefault((ROLES.index(row.balance_role), row.currency), {})
        for field, amount in row.buckets.items():
            add(into, field, amount)
    found: list[dict[str, Any]] = []
    for (index, currency), buckets in sorted(totals.items()):
        role = ROLES[index]
        found.append(
            {
                "row_key": f"{TOTAL_PREFIX}{role}:{currency}",
                "contract_external_id": None,
                "customer_name": None,
                "entity_code": None,
                "balance_role": ROLE_LABELS[role],
                "currency": currency,
                **{
                    field: tie_outs.money(buckets.get(field, ZERO), currency)
                    for field in BUCKET_FIELDS
                },
                "total": tie_outs.money(sum(buckets.values(), ZERO), currency),
            }
        )
    return found


def aging_tie(rows: Sequence[AgedRow], balances: Sequence[BalanceRow]) -> dict[str, Any]:
    """``TO_AGING_EQ_BALANCES``: Σ aged totals per currency equal Σ presented balances of the three
    roles per currency (SCREENS_B RPT-R-08 "Aging totals equal contract balances")."""
    expected: dict[str, Decimal] = {}
    for balance in balances:
        for role in ROLES:
            add(expected, balance.currency, balance.value(ROLE_MEASURES[role]))
    actual: dict[str, Decimal] = {}
    for row in rows:
        add(actual, row.currency, row.total)
    return tie_outs.compared(TO_AGING_EQ_BALANCES, expected, actual)


def _revenue_dates(
    session: Session, entity_ids: Sequence[UUID], book_code: str, known_at: datetime, last_end: date
) -> dict[UUID, date]:
    """Latest ``REVENUE_RECOGNITION`` effective date per obligation through ``last_end``."""
    statement = (
        select(subledger_line.c.obligation_id, func.max(subledger_line.c.effective_date))
        .where(
            subledger_line.c.book_code == book_code,
            subledger_line.c.entity_id.in_(list(entity_ids)),
            subledger_line.c.entry_kind == REVENUE_KIND,
            subledger_line.c.recorded_at <= known_at,
            subledger_line.c.effective_date <= last_end,
            subledger_line.c.obligation_id.is_not(None),
        )
        .group_by(subledger_line.c.obligation_id)
    )
    return {UUID(str(row[0])): row[1] for row in session.execute(statement) if row[1] is not None}


def _layers(
    session: Session,
    *,
    entity_ids: Sequence[UUID],
    book_code: str,
    period_ends: Mapping[UUID, date],
    known_at: datetime,
    balances: Sequence[BalanceRow],
) -> list[Layer]:
    """Open layers per (contract, entity, role) from the subledger through each entity's period
    end (interim source; see the module docstring)."""
    if not entity_ids or not period_ends:
        return []
    last_end = max(period_ends.values())
    revenue_dates = _revenue_dates(session, entity_ids, book_code, known_at, last_end)
    names = {(row.contract_id, row.entity_id): row for row in balances}
    statement = (
        select(
            subledger_line.c.contract_id,
            subledger_line.c.entity_id,
            subledger_line.c.obligation_id,
            subledger_line.c.account_role,
            subledger_line.c.entry_kind,
            subledger_line.c.effective_date,
            subledger_line.c.period_end_date,
            subledger_line.c.dr_cr,
            subledger_line.c.amount_txn,
            subledger_line.c.txn_currency,
        )
        .where(
            subledger_line.c.book_code == book_code,
            subledger_line.c.entity_id.in_(list(entity_ids)),
            subledger_line.c.account_role.in_(list(ROLES)),
            subledger_line.c.recorded_at <= known_at,
            subledger_line.c.period_end_date <= last_end,
        )
        .order_by(
            subledger_line.c.effective_date,
            subledger_line.c.period_end_date,
            subledger_line.c.recorded_at,
            subledger_line.c.entry_no,
            subledger_line.c.id,
        )
    )
    flows: dict[tuple[UUID, UUID, str, str], list[tuple[date, Decimal]]] = {}
    for row in session.execute(statement).mappings():
        entity_id = UUID(str(row["entity_id"]))
        if row["period_end_date"] > period_ends[entity_id]:
            continue
        role = str(row["account_role"])
        amount = Decimal(row["amount_txn"])
        # Liability layers grow with credits; asset layers grow with debits.
        sign = 1 if (str(row["dr_cr"]) == "C") == (role == "CONTRACT_LIABILITY") else -1
        day = row["effective_date"]
        if role != "CONTRACT_LIABILITY" and str(row["entry_kind"]) == NETTING_RECLASS:
            obligation = row["obligation_id"]
            if obligation is not None:
                day = revenue_dates.get(UUID(str(obligation)), day)
        key = (UUID(str(row["contract_id"])), entity_id, role, str(row["txn_currency"]).strip())
        flows.setdefault(key, []).append((day, sign * amount))
    layers: list[Layer] = []
    for (contract_id, entity_id, role, currency), items in flows.items():
        named = names.get((contract_id, entity_id))
        for day, amount in open_layers(items):
            if amount == 0:
                continue
            layers.append(
                Layer(
                    contract_id=contract_id,
                    external_id=named.external_id if named else str(contract_id),
                    customer_name=named.customer_name if named else None,
                    entity_id=entity_id,
                    entity_code=named.entity_code if named else str(entity_id),
                    balance_role=role,
                    currency=currency,
                    amount=amount,
                    effective_date=day,
                )
            )
    return layers


def _check_view(params: ReportParams, found: Sequence[EntityRef], rows: Sequence[AgedRow]) -> None:
    view = str(params.parameters.get("currency_view") or "transaction")
    functional = {entity.id: entity.functional_currency for entity in found}
    if view != "transaction" and any(row.currency != functional[row.entity_id] for row in rows):
        raise tie_outs.invalid("currency_view", FUNCTIONAL_ONLY)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    found = tie_outs.entities(session, params.entity_ids)
    calendars = tie_outs.calendars(session, found)
    at: dict[UUID, PeriodRef | None] = {
        entity.id: tie_outs.period_of(params, calendars[entity.id], entity) for entity in found
    }
    period_ends = {entity_id: item.end for entity_id, item in at.items() if item is not None}
    cutoff = tie_outs.cutoff_for(session, params)
    balances = tie_outs.balances_at(
        session,
        entity_ids=params.entity_ids,
        book_code=book_code,
        period_keys=at,
        cutoff=cutoff,
        params=params,
    )
    layers = _layers(
        session,
        entity_ids=params.entity_ids,
        book_code=book_code,
        period_ends=period_ends,
        known_at=params.known_at,
        balances=balances,
    )
    role_filter = str(params.parameters.get("balance_role") or "ALL")
    rows = aged_rows(layers, period_ends)
    _check_view(params, found, rows)
    shown = tuple(row for row in rows if role_filter == "ALL" or row.balance_role == role_filter)
    data: list[dict[str, Any]] = [
        {
            "row_key": row.row_key,
            "contract_external_id": row.external_id,
            "customer_name": row.customer_name,
            "entity_code": row.entity_code,
            "balance_role": ROLE_LABELS[row.balance_role],
            "currency": row.currency,
            **{field: tie_outs.money(row.buckets[field], row.currency) for field in BUCKET_FIELDS},
            "total": tie_outs.money(row.total, row.currency),
        }
        for row in shown
    ]
    data.extend(total_rows(shown))
    totals: dict[str, Decimal] = {}
    for row in shown:
        add(totals, row.currency, row.total)
    return ReportData(
        columns=COLUMNS,
        rows=tuple(data),
        control_totals={"total": tie_outs.by_currency(totals)},
        tie_out_results=(aging_tie(rows, balances),),
    )
