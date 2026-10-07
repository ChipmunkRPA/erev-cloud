"""RPT-36 balance aging (REQ-BIL-013; CHK-117; POL-125/POL-126).

Liabilities use immutable T-CON-18 movements of the versions selected by the report binding.
Asset and unbilled balances use those versions' period-end engine attributions in T-ENG-03,
including the revenue date and the separate presentation-role amounts. No close journal is
required, including with ERP billing. Each contract/entity/role/currency reconciles separately.

Older versions without aging attributions refuse rather than reconstructing presentation or
ages from today's configuration. This report currently supports transaction currency; functional
view is accepted only when transaction and functional currencies coincide.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import fx_layer_movement
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams, aging_attributions
from erev_api.domain.reports.builders.contract_balance_rollforward import FUNCTIONAL_ONLY
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import ZERO, BalanceRow, EntityRef, PeriodRef, add
from erev_api.explain import store
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
    roles per currency, with agreement also required per contract, entity and role
    (SCREENS_B RPT-R-08 "Aging totals equal contract balances")."""
    expected: dict[str, Decimal] = {}
    for balance in balances:
        for role in ROLES:
            add(expected, balance.currency, balance.value(ROLE_MEASURES[role]))
    actual: dict[str, Decimal] = {}
    for row in rows:
        add(actual, row.currency, row.total)
    result = tie_outs.compared(TO_AGING_EQ_BALANCES, expected, actual)
    # A grand-total match must not hide misclassification or attribution to the wrong owner.
    expected_parts: dict[tuple[UUID, UUID, str, str], Decimal] = {}
    actual_parts: dict[tuple[UUID, UUID, str, str], Decimal] = {}
    for balance in balances:
        for role in ROLES:
            key = (balance.contract_id, balance.entity_id, role, balance.currency)
            expected_parts[key] = expected_parts.get(key, ZERO) + balance.value(ROLE_MEASURES[role])
    for row in rows:
        key = (row.contract_id, row.entity_id, row.balance_role, row.currency)
        actual_parts[key] = actual_parts.get(key, ZERO) + row.total
    if any(
        tie_outs.quantized(expected_parts.get(key, ZERO), key[3])
        != tie_outs.quantized(actual_parts.get(key, ZERO), key[3])
        for key in expected_parts.keys() | actual_parts.keys()
    ):
        result["result"] = tie_outs.FAIL
    return result


def _liability_layers(
    session: Session,
    *,
    book_code: str,
    period_ends: Mapping[UUID, date],
    balances: Sequence[BalanceRow],
) -> list[Layer]:
    """Age the exact remaining layers of the versions selected by the report binding.

    A layer's creation date survives partial consumption; movement IDs determine its identity,
    so the reader must not replay FIFO across contracts or independently select a newer version.
    Remeasurements do not change the transaction-currency amount aged by this report.
    """
    if not balances or not period_ends:
        return []
    names = {(row.contract_id, row.entity_id, row.version_id): row for row in balances}
    movement = fx_layer_movement.c
    statement = select(fx_layer_movement).where(
        movement.contract_version_id.in_({row.version_id for row in balances}),
        movement.entity_id.in_(period_ends),
        movement.book_code == book_code,
        movement.balance_role == "CONTRACT_LIABILITY",
        movement.effective_date <= max(period_ends.values()),
    )
    grouped: dict[tuple[UUID, UUID, UUID, str, str], tuple[date | None, Decimal]] = {}
    for row in session.execute(statement).mappings():
        owner = (row["contract_id"], row["entity_id"], row["contract_version_id"])
        if owner not in names or row["effective_date"] > period_ends[row["entity_id"]]:
            continue
        key = (*owner, str(row["layer_key"]), str(row["txn_currency"]).strip())
        created_on, amount = grouped.get(key, (None, ZERO))
        kind = row["movement_kind"]
        if kind == "LIABILITY_LAYER_CREATED":
            day = row["effective_date"]
            created_on = day if created_on is None else min(created_on, day)
            amount += Decimal(row["amount_txn"])
        elif kind == "LIABILITY_LAYER_CONSUMED":
            amount -= Decimal(row["amount_txn"])
        grouped[key] = (created_on, amount)
    result: list[Layer] = []
    for (contract_id, entity_id, version_id, _, currency), (created_on, amount) in grouped.items():
        if amount == ZERO:
            continue
        if created_on is None:
            raise tie_outs.invalid("period_key", "A liability layer has no creation date.")
        named = names[(contract_id, entity_id, version_id)]
        result.append(
            Layer(
                contract_id=contract_id,
                external_id=named.external_id,
                customer_name=named.customer_name,
                entity_id=entity_id,
                entity_code=named.entity_code,
                balance_role="CONTRACT_LIABILITY",
                currency=currency,
                amount=amount,
                effective_date=created_on,
            )
        )
    return result


def _layers(
    session: Session,
    *,
    book_code: str,
    period_ends: Mapping[UUID, date],
    balances: Sequence[BalanceRow],
) -> list[Layer]:
    """Version-bound liability movements and engine asset/unbilled presentation shares."""
    layers = _liability_layers(
        session, book_code=book_code, period_ends=period_ends, balances=balances
    )
    traces = {
        version_id: store.load_trace(session, version_id)
        for version_id in {row.version_id for row in balances}
    }
    for row in balances:
        end = period_ends.get(row.entity_id)
        if end is None:
            continue
        for day, role, amount in aging_attributions.attributions(
            traces[row.version_id],
            contract=row.external_id,
            entity=row.entity_code,
            currency=row.currency,
            end=end,
        ):
            layers.append(
                Layer(
                    contract_id=row.contract_id,
                    external_id=row.external_id,
                    customer_name=row.customer_name,
                    entity_id=row.entity_id,
                    entity_code=row.entity_code,
                    balance_role=role,
                    currency=row.currency,
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
    found = tie_outs.entities(session, params.entity_ids, params=params)
    calendars = tie_outs.calendars(session, found, params=params)
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
        book_code=book_code,
        period_ends=period_ends,
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
