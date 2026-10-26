"""RPT-36 balance aging (REQ-BIL-013; CHK-117; POL-125/POL-126).

Liabilities use immutable T-CON-18 movements of the versions selected by the report binding.
Asset and unbilled balances use those versions' period-end engine attributions in T-ENG-03,
including the revenue date and the separate presentation-role amounts. No close journal is
required, including with ERP billing. Each contract/entity/role/currency reconciles separately.

Older versions without aging attributions refuse rather than reconstructing presentation or
ages from today's configuration. Functional views read original reclass shares and signed
liability-layer movements, preserving original dates and reconciling each member/role to its
retained functional balance. Reporting view applies retained closing rates with cumulative
bucket rounding; its balance tie-out remains in functional currency.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from uuid import UUID

from erev_engine.stages.s01_canonicalize.convert import contract_entity_subject_key
from erev_engine.trace import Trace, TraceNode
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import fx_layer_movement
from erev_api.domain.reports import functional_balances, reporting_currency, tie_outs
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
    allocation_adjustment: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return sum(self.buckets.values(), ZERO) + self.allocation_adjustment

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


def member_adjustments(
    rows: Sequence[AgedRow],
    balances: Sequence[BalanceRow],
    traces: Mapping[UUID, Trace | None],
    ends: Mapping[UUID, date],
) -> tuple[AgedRow, ...]:
    """Keep source ages; bridge only complete, conserving engine member allocations."""
    grouped: dict[tuple[UUID, UUID, str], list[BalanceRow]] = {}
    for balance in balances:
        grouped.setdefault((balance.version_id, balance.entity_id, balance.currency), []).append(
            balance
        )
    result = list(rows)
    index = {
        (r.contract_id, r.entity_id, r.balance_role, r.currency): i for i, r in enumerate(result)
    }
    for (version, entity, currency), members in grouped.items():
        if len(members) < 2:
            continue
        names = {m.external_id for m in members}
        trace = traces.get(version)
        if trace is None:
            continue
        # Engine member_cl nodes identify the allocation population, not merely a
        # convenient group whose unrelated discrepancies happen to cancel out.
        latest: dict[str, tuple[date, frozenset[str], TraceNode]] = {}
        for node in trace.nodes:
            if (
                node.measure != "contract_liability"
                or node.params.get("mode") != "member_cl"
                or node.formula_id != "pos.split_ca_ur.v1"
                or len(node.id.split(":")) != 3
                or node.id.endswith(":-")
            ):
                continue
            member_name = node.params.get("key", "")
            if member_name not in names or node.id.split(":")[1] != contract_entity_subject_key(
                member_name, members[0].entity_code
            ):
                continue
            try:
                day = date.fromisoformat(node.params["as_of"])
                population = frozenset(node.params["keys"].split("|"))
            except (KeyError, ValueError) as exc:
                raise tie_outs.invalid("period_key", "Invalid member allocation evidence.") from exc
            if day <= ends[entity] and (member_name not in latest or latest[member_name][0] < day):
                latest[member_name] = (day, population, node)
        if (
            set(latest) != names
            or any(keys != names for _, keys, _ in latest.values())
            or len({day for day, _, _ in latest.values()}) != 1
        ):
            continue
        # A zero group delta alone cannot authorize arbitrary member transfers.
        # Each destination must agree with its actual original engine target.
        for member in members:
            original = latest[member.external_id][2]
            target = original
            if original.currency != currency:
                target_id = original.id.replace(
                    "contract_liability:", "contract_liability_functional:", 1
                )
                candidates = [node for node in trace.nodes if node.id == target_id]
                if len(candidates) != 1:
                    raise tie_outs.invalid(
                        "currency_view", "Member allocation has no unique functional target."
                    )
                target = candidates[0]
            try:
                value = Decimal(target.value)
                if (
                    not value.is_finite()
                    or target.currency != currency
                    or value != member.value("contract_liability")
                ):
                    raise ValueError("Mismatched target")
            except (InvalidOperation, ValueError) as exc:
                raise tie_outs.invalid(
                    "period_key", "Member allocation disagrees with its retained engine target."
                ) from exc
        originals = {}
        for member in members:
            key = (member.contract_id, entity, "CONTRACT_LIABILITY", currency)
            originals[key] = result[index[key]].total if key in index else ZERO
        expected = sum((m.value("contract_liability") for m in members), ZERO)
        if sum(originals.values(), ZERO) != expected:
            raise tie_outs.invalid(
                "period_key", "Original liability layers do not conserve the combined balance."
            )
        for member in members:
            key = (member.contract_id, entity, "CONTRACT_LIABILITY", currency)
            adjustment = member.value("contract_liability") - originals[key]
            if adjustment == ZERO:
                continue
            if key in index:
                result[index[key]] = replace(result[index[key]], allocation_adjustment=adjustment)
            else:
                index[key] = len(result)
                result.append(
                    AgedRow(
                        member.contract_id,
                        member.external_id,
                        member.customer_name,
                        entity,
                        member.entity_code,
                        "CONTRACT_LIABILITY",
                        currency,
                        dict.fromkeys(BUCKET_FIELDS, ZERO),
                        adjustment,
                    )
                )
    return tuple(
        sorted(
            result,
            key=lambda row: (row.external_id, row.entity_code, ROLES.index(row.balance_role)),
        )
    )


def total_rows(rows: Sequence[AgedRow], *, adjustments: bool = False) -> list[dict[str, Any]]:
    """Totals per balance role and currency: ``TOTAL:<role>:<ISO>`` (SCREENS_B RPT-36)."""
    totals: dict[tuple[int, str], dict[str, Decimal]] = {}
    for row in rows:
        into = totals.setdefault((ROLES.index(row.balance_role), row.currency), {})
        for field, amount in row.buckets.items():
            add(into, field, amount)
        if adjustments:
            add(into, "allocation_adjustment", row.allocation_adjustment)
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
                **(
                    {
                        "allocation_adjustment": tie_outs.money(
                            buckets.get("allocation_adjustment", ZERO), currency
                        )
                    }
                    if adjustments
                    else {}
                ),
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
    functional: Mapping[UUID, str] | None = None,
) -> list[Layer]:
    """Age the exact remaining layers of the versions selected by the report binding.

    A layer's creation date survives partial consumption; movement IDs determine its identity,
    so the reader must not replay FIFO across contracts or independently select a newer version.
    Remeasurements affect functional carrying only and never reset the original age.
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
    traces = {}
    grouped: dict[tuple[UUID, UUID, UUID, str, str], tuple[date | None, Decimal]] = {}
    for row in session.execute(statement).mappings():
        owner = (row["contract_id"], row["entity_id"], row["contract_version_id"])
        if owner not in names or row["effective_date"] > period_ends[row["entity_id"]]:
            continue
        currency = str(row["txn_currency"]).strip()
        foreign = functional is not None and currency != functional[row["entity_id"]]
        if foreign and functional is not None:
            currency = str(row["functional_currency"]).strip()
            if currency != functional[row["entity_id"]]:
                raise tie_outs.invalid(
                    "currency_view", "Functional layer currency is inconsistent."
                )
        field = "amount_functional" if foreign else "amount_txn"
        key = (*owner, str(row["layer_key"]), currency)
        created_on, amount = grouped.get(key, (None, ZERO))
        kind = row["movement_kind"]
        if kind == "LIABILITY_LAYER_CREATED":
            version = row["contract_version_id"]
            if version not in traces:
                trace = store.load_trace(session, version)
                traces[version] = {} if trace is None else {n.id: n for n in trace.nodes}
            from ..split_sources import original_date

            day = original_date(
                traces[version].get(str(row["trace_node_id"])), row["effective_date"]
            )
            created_on = day if created_on is None else min(created_on, day)
            amount += Decimal(row[field])
        elif kind == "LIABILITY_LAYER_CONSUMED":
            amount -= Decimal(row[field])
        elif foreign and kind == "LIABILITY_LAYER_REMEASURED":
            amount += Decimal(row[field])
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
    functional: Mapping[UUID, str] | None = None,
) -> list[Layer]:
    """Version-bound liability movements and engine asset/unbilled presentation shares."""
    layers = _liability_layers(
        session,
        book_code=book_code,
        period_ends=period_ends,
        balances=balances,
        functional=functional,
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
            functional_currency=None if functional is None else functional[row.entity_id],
        ):
            layers.append(
                Layer(
                    contract_id=row.contract_id,
                    external_id=row.external_id,
                    customer_name=row.customer_name,
                    entity_id=row.entity_id,
                    entity_code=row.entity_code,
                    balance_role=role,
                    currency=row.currency if functional is None else functional[row.entity_id],
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


def _translated(
    rows: Sequence[AgedRow], translation: reporting_currency.Translation
) -> tuple[AgedRow, ...]:
    """Carry minor-unit rounding across ordered buckets, preserving the translated total."""
    result = []
    for row in rows:
        cumulative = previous = ZERO
        buckets = {}
        for field in BUCKET_FIELDS:
            cumulative += row.buckets[field]
            current = translation.amount(row.entity_id, cumulative)
            buckets[field] = current - previous
            previous = current
        result.append(
            replace(
                row,
                currency=translation.currency,
                buckets=buckets,
                allocation_adjustment=translation.amount(row.entity_id, row.total) - previous,
            )
        )
    return tuple(result)


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
    functional_key = "aging_functional_layers_v1"
    functional = (
        {entity.id: entity.functional_currency for entity in found}
        if params.parameters.get("currency_view") in {"functional", "reporting"}
        and (params.binding is None or functional_key in params.binding.evidence)
        else None
    )
    layers = _layers(
        session,
        book_code=book_code,
        period_ends=period_ends,
        balances=balances,
        functional=functional,
    )
    if functional is not None:
        balances = functional_balances.read(
            session,
            params,
            balances,
            entities=found,
            periods=at,
            book_code=book_code,
        )
        if params.sources is not None:
            params.sources.record_evidence(functional_key, {"basis": "retained_engine_sources"})
    role_filter = str(params.parameters.get("balance_role") or "ALL")
    rows = aged_rows(layers, period_ends)
    adjustment_key = "aging_member_adjustments_v1"
    adjustments = params.binding is None or adjustment_key in params.binding.evidence
    if adjustments:
        rows = member_adjustments(
            rows,
            balances,
            {b.version_id: store.load_trace(session, b.version_id) for b in balances},
            period_ends,
        )
        if params.sources is not None:
            params.sources.record_evidence(
                adjustment_key, {"basis": "original_owner_ages_separate_allocation"}
            )
    _check_view(params, found, rows)
    check = aging_tie(rows, balances)
    if functional is not None and check["result"] != tie_outs.PASS:
        raise tie_outs.invalid(
            "currency_view", "Functional aging layers do not reconcile to retained member balances."
        )
    translation = None
    key = "aging_reporting_translation_v1"
    if params.parameters.get("currency_view") == "reporting" and (
        params.binding is None or key in params.binding.evidence
    ):
        translation = reporting_currency.closing(
            session,
            params,
            tenant_id=uow.principal.tenant_id,
            entities=found,
            periods=at,
        )
        rows = _translated(rows, translation)
        if params.sources is not None:
            params.sources.record_evidence(key, {"rounding": "cumulative_bucket"})
    shown = tuple(
        row
        for row in rows
        if (row.total != ZERO or (adjustments and row.allocation_adjustment != ZERO))
        and (role_filter == "ALL" or row.balance_role == role_filter)
    )
    data: list[dict[str, Any]] = [
        {
            "row_key": row.row_key,
            "contract_external_id": row.external_id,
            "customer_name": row.customer_name,
            "entity_code": row.entity_code,
            "balance_role": ROLE_LABELS[row.balance_role],
            "currency": row.currency,
            **(
                {
                    "functional_currency": translation.rates[row.entity_id]["base_currency"],
                    "closing_fx_rate": translation.rates[row.entity_id]["rate"],
                }
                if translation is not None
                else {}
            ),
            **{field: tie_outs.money(row.buckets[field], row.currency) for field in BUCKET_FIELDS},
            **(
                {"allocation_adjustment": tie_outs.money(row.allocation_adjustment, row.currency)}
                if adjustments
                else {}
            ),
            "total": tie_outs.money(row.total, row.currency),
        }
        for row in shown
    ]
    data.extend(total_rows(shown, adjustments=adjustments))
    totals: dict[str, Decimal] = {}
    for row in shown:
        add(totals, row.currency, row.total)
    control: dict[str, Any] = {"total": tie_outs.by_currency(totals)}
    columns: tuple[Column, ...] = COLUMNS
    if adjustments:
        columns = COLUMNS[:-1] + (
            Column("allocation_adjustment", "Member allocation adjustment", "money"),
            COLUMNS[-1],
        )
        control["aging_basis"] = (
            "Original receiving-contract ages; member allocations shown separately without an age. "
            "Total equals aged buckets plus member allocation adjustment."
        )

    if translation is not None:
        control.update(
            reporting_currency=translation.currency,
            translation_rates=list(translation.rates.values()),
            translation_rounding="cumulative_bucket",
            tie_out_currency_basis="functional",
        )
        columns += (
            Column("functional_currency", "Functional currency", "code"),
            Column("closing_fx_rate", "Closing FX rate", "decimal"),
        )
        check.setdefault("details", []).append(
            {"reason": "Compared in functional currency before reporting-currency translation."}
        )
    return ReportData(
        columns=columns,
        rows=tuple(data),
        control_totals=control,
        tie_out_results=(check,),
    )
