"""Retain actual computation FX inputs and detect changes missed by approval-time reach."""

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.orm import Session

from erev_api.db.tables import combination_group, computation_evidence, contract, subledger_line
from erev_api.uow import UnitOfWork
from erev_engine.bundle import FxRateInput, InputBundle

from . import bundles


def rates_view(rates: Iterable[FxRateInput], through: date | None = None) -> list[list[str]]:
    """Economic inputs including set identity; equal values under a new version are unchanged."""
    return sorted(
        [
            [
                r.version_key.rsplit("@v", 1)[0],
                r.rate_type,
                r.base_currency,
                r.quote_currency,
                r.effective_date.isoformat(),
                r.period_key or "",
                str(r.rate.normalize()),
            ]
            for r in rates
            if through is None or r.effective_date <= through
        ]
    )


def capture(bundle: InputBundle) -> dict[str, Any]:
    return {
        "version": 1,
        "currencies": sorted(bundle.currencies),
        "rates": rates_view(bundle.fx_rates),
    }


def changed(
    snapshot: Mapping[str, Any] | None, current: Iterable[FxRateInput], through: date
) -> bool:
    if snapshot is None or snapshot.get("version") != 1:
        return True  # Missing original inputs require a new calculation, never a guessed backfill.
    before = [row for row in snapshot["rates"] if row[4] <= through.isoformat()]
    return before != rates_view(current, through)


def stale_groups(session: Session, *, entity_id: UUID, book_code: str, through: date) -> list[UUID]:
    members = (
        select(contract.c.id)
        .where(contract.c.combination_group_id == combination_group.c.id)
        .correlate(combination_group)
    )
    owned = exists().where(
        contract.c.combination_group_id == combination_group.c.id,
        contract.c.contracting_entity_id == entity_id,
    )
    performed = exists().where(
        subledger_line.c.contract_id.in_(members),
        subledger_line.c.entity_id == entity_id,
        subledger_line.c.book_code == book_code,
        subledger_line.c.period_end_date <= through,
    )
    rows = session.execute(
        select(combination_group.c.id, computation_evidence.c.fx_inputs)
        .select_from(
            combination_group.outerjoin(
                computation_evidence,
                and_(
                    computation_evidence.c.tenant_id == combination_group.c.tenant_id,
                    computation_evidence.c.contract_computation_id
                    == combination_group.c.head_computation_id,
                ),
            )
        )
        .where(
            combination_group.c.head_computation_id.is_not(None),
            or_(owned, performed),
            exists().where(contract.c.combination_group_id == combination_group.c.id),
        )
    ).all()
    cache: dict[tuple[str, ...], tuple[FxRateInput, ...]] = {}
    stale = []
    for group_id, snapshot in rows:
        if snapshot is None:
            stale.append(group_id)
            continue
        currencies = tuple(snapshot["currencies"])
        if currencies not in cache:
            cache[currencies] = bundles._fx_rates(session, currencies, None)
        if changed(snapshot, cache[currencies], through):
            stale.append(group_id)
    return sorted(stale, key=str)


def mark(uow: UnitOfWork, *, entity_id: UUID, book_code: str, through: date) -> list[UUID]:
    """Lock groups before rechecking their current head; the ordinary dirty worker repairs them."""
    candidates = stale_groups(
        uow.session, entity_id=entity_id, book_code=book_code, through=through
    )
    if not candidates:
        return []
    uow.session.execute(
        select(combination_group.c.id)
        .where(combination_group.c.id.in_(candidates))
        .order_by(combination_group.c.id)
        .with_for_update()
    ).all()
    current = set(
        stale_groups(uow.session, entity_id=entity_id, book_code=book_code, through=through)
    ) & set(candidates)
    if current:
        uow.session.execute(
            update(combination_group)
            .where(combination_group.c.id.in_(current))
            .values(
                dirty_since=func.greatest(combination_group.c.dirty_since, uow.now),
                dirty_trigger="FX_REPUBLISH",
                row_version=combination_group.c.row_version + 1,
                updated_at=uow.now,
                updated_by=uow.principal.id,
                updated_by_kind=uow.principal.kind.value,
            )
        )
    return sorted(current, key=str)
