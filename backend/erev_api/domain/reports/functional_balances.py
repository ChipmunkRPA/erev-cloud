"""Dated functional balances from the engine's retained member targets.

Historical-layer liabilities and monetary asset remeasurement already differ in
stage 12. Reporting must read those amounts, never apply one current FX rate to
transaction captions. A locked endpoint selects only a computation available at
its frozen cutoff and must reproduce its transaction balances before translation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract_computation, contract_version, contract_version_balance
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.explain import store
from erev_api.problems import Problem
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.trace import Trace


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Functional balance: {detail}")


def project(
    trace: Trace,
    *,
    external_id: str,
    entity_code: str,
    period_key: str,
    stored: Mapping[str, Any],
    version_id: UUID,
    measures: Sequence[str] = tie_outs.BALANCE_MEASURES,
) -> dict[str, Decimal]:
    subject = contract_entity_subject_key(external_id, entity_code)
    currency = str(stored["functional_currency"]).strip()
    traced = tie_outs.traced_balances((node.id, node.value) for node in trace.nodes)
    transaction = tie_outs.period_balances(
        traced,
        external_id=external_id,
        entity_code=entity_code,
        period_key=period_key,
        stored=stored,
        version_id=version_id,
    )
    if str(stored["txn_currency"]).strip() == currency:
        return {name: transaction[name] for name in measures}
    output: dict[str, Decimal] = {}
    measured_periods = {
        key
        for name, values in traced.nodes.items()
        if name.endswith(f":{subject}")
        for key, _ in values
        if key <= period_key
    }
    measured = max(measured_periods, default=None)
    for measure in measures:
        prefix = f"{measure}_functional:{subject}:"
        nodes = sorted(
            (node for node in trace.nodes if node.id.startswith(prefix)), key=lambda node: node.id
        )
        if nodes:
            value = Decimal(0)
            seen = set()
            for node in nodes:
                key = node.id[len(prefix) :]
                if key in seen or node.currency != currency or not key.startswith("FY"):
                    raise _refuse(
                        f"{external_id}: inconsistent {measure} period/currency evidence."
                    )
                seen.add(key)
                if key <= period_key:
                    value = Decimal(node.value)
                    if not value.is_finite():
                        raise _refuse(f"{external_id}: non-finite {measure} evidence.")
            if measured is not None and measured not in seen:
                raise _refuse(f"{external_id}: missing functional {measure} at {measured}.")
            output[measure] = value
            continue
        # Fields outside the engine's functional-member projection may be zero,
        # but a nonzero transaction amount must never silently become zero.
        held = Decimal(stored.get(f"{measure}_functional") or 0)
        if transaction[measure] != 0 or held != 0:
            raise _refuse(
                f"{external_id}: no dated functional {measure} at {period_key} "
                f"in version {version_id}."
            )
        output[measure] = Decimal(0)
    return output


def read(
    session: Session,
    params: ReportParams,
    rows: Sequence[tie_outs.BalanceRow],
    *,
    entities: Sequence[tie_outs.EntityRef],
    periods: Mapping[UUID, tie_outs.PeriodRef | None],
    book_code: str,
    locked: tie_outs.LockedEnds | None = None,
    measures: Sequence[str] = tie_outs.BALANCE_MEASURES,
) -> tuple[tie_outs.BalanceRow, ...]:
    currencies = {entity.id: entity.functional_currency for entity in entities}
    traces: dict[UUID, Trace] = {}
    result = []
    for row in rows:
        currency = currencies[row.entity_id]
        if row.currency == currency:
            result.append(row)
            continue
        at = periods.get(row.entity_id)
        if at is None:
            result.append(replace(row, currency=currency, values={}))
            continue
        end = None if locked is None else locked.at(row.entity_id, at)
        if end is None:
            from .acquisition_functional import project as acquired

            projected = acquired(params, row, at, currency=currency, measures=measures)
            if projected is not None:
                result.append(replace(row, currency=currency, values=projected))
                continue
        identity = f"{row.entity_id}:{row.contract_id}:{at.key}"
        selected = row.version_id
        if params.binding is None and end is not None:
            eligible = tuple(
                session.execute(
                    select(contract_version.c.id)
                    .join(
                        contract_computation,
                        (contract_computation.c.id == contract_version.c.contract_computation_id)
                        & (contract_computation.c.tenant_id == contract_version.c.tenant_id),
                    )
                    .where(
                        contract_version.c.book_code == book_code,
                        contract_version.c.created_at <= end.frozen_at,
                        contract_computation.c.created_at <= end.frozen_at,
                        contract_computation.c.cutoff_at <= end.frozen_at,
                        contract_computation.c.status == "SUCCEEDED",
                    )
                ).scalars()
            )
            selected_row = session.execute(
                select(contract_version_balance.c.contract_version_id).where(
                    contract_version_balance.c.contract_id == row.contract_id,
                    contract_version_balance.c.entity_id == row.entity_id,
                    tie_outs.read_from(
                        contract_version_balance.c.contract_id,
                        contract_version_balance.c.contract_version_id,
                        book_code=book_code,
                        cutoff=end.frozen_at,
                        versions=eligible,
                        only_contract=row.contract_id,
                    ),
                )
            ).scalar_one_or_none()
            if selected_row is None:
                raise _refuse(f"{row.external_id}: no computation available at the lock cutoff.")
            selected = UUID(str(selected_row))
        bound = tie_outs.label_for(params, "functional_balance_version", identity, str(selected))
        if bound is None:
            raise _refuse("the retained functional source is missing.")
        selected = UUID(bound)
        stored_row = (
            session.execute(
                select(contract_version_balance).where(
                    contract_version_balance.c.contract_version_id == selected,
                    contract_version_balance.c.contract_id == row.contract_id,
                    contract_version_balance.c.entity_id == row.entity_id,
                    contract_version_balance.c.book_code == book_code,
                )
            )
            .mappings()
            .one_or_none()
        )
        if stored_row is None or str(stored_row["functional_currency"]).strip() != currency:
            raise _refuse(f"{row.external_id}: the functional source has changed scope/currency.")
        stored = dict(stored_row)
        if selected not in traces:
            trace = store.load_trace(session, selected)
            if trace is None:
                raise _refuse(f"{row.external_id}: the retained calculation trace is missing.")
            traces[selected] = trace
        trace = traces[selected]
        transaction = tie_outs.period_balances(
            tie_outs.traced_balances((node.id, node.value) for node in trace.nodes),
            external_id=row.external_id,
            entity_code=row.entity_code,
            period_key=at.key,
            stored=stored,
            version_id=selected,
        )
        if str(stored["txn_currency"]).strip() != row.currency or any(
            transaction[name] != row.value(name) for name in tie_outs.BALANCE_MEASURES
        ):
            raise _refuse(
                f"{row.external_id}: the functional source does not reproduce "
                "the report's transaction endpoint."
            )
        values = project(
            trace,
            external_id=row.external_id,
            entity_code=row.entity_code,
            period_key=at.key,
            stored=stored,
            version_id=selected,
            measures=measures,
        )
        result.append(replace(row, currency=currency, values=values, version_id=selected))
    return tuple(result)
