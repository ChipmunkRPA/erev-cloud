"""Quarantined contract groups whose quarantine was waived and still stands (04 T-CLS-01 "Ends of
a run"; 05 RCP-20; item CLO-GATE-RUN-2): the test ``RECOMPUTE_DIRTY`` applies before it computes
a dirty group again, and the one the gate ``CLOSE_RUN_COMPLETED`` applies before it counts one."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    combination_group_member,
    contract,
    contract_computation,
    exception_item,
)
from erev_api.enums import ComputationStatus, ExceptionSeverity, ExceptionSource, ExceptionStatus

__all__ = ["REFUSED_COMPUTATIONS", "standing_waived"]

REFUSED_COMPUTATIONS: Final = (
    ComputationStatus.QUARANTINED.value,
    ComputationStatus.FAILED.value,
)


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def standing_waived(session: Session, group_ids: Sequence[UUID]) -> set[UUID]:
    """The groups of ``group_ids`` whose quarantine was waived and still stands (T-CLS-01 "Ends of
    a run"): the latest computation is refused, the members' stream heads are the ones it
    recorded, and the latest blocking engine exception item of the group is ``WAIVED``."""
    if not group_ids:
        return set()
    latest: dict[UUID, Mapping[str, Any]] = {}
    for row in session.execute(
        select(
            contract_computation.c.combination_group_id,
            contract_computation.c.status,
            contract_computation.c.stream_heads,
        )
        .where(contract_computation.c.combination_group_id.in_(group_ids))
        .order_by(contract_computation.c.created_at, contract_computation.c.id)
    ).mappings():
        latest[UUID(str(row["combination_group_id"]))] = dict(row)
    refused = {
        group_id: dict(row["stream_heads"] or {})
        for group_id, row in latest.items()
        if _text(row["status"]) in REFUSED_COMPUTATIONS
    }
    if not refused:
        return set()
    heads: dict[UUID, dict[str, int]] = {group_id: {} for group_id in refused}
    for group_id, contract_id, head in session.execute(
        select(
            combination_group_member.c.combination_group_id,
            contract.c.id,
            contract.c.head_stream_version,
        )
        .select_from(
            combination_group_member.join(
                contract,
                and_(
                    contract.c.tenant_id == combination_group_member.c.tenant_id,
                    contract.c.id == combination_group_member.c.contract_id,
                ),
            )
        )
        .where(
            combination_group_member.c.combination_group_id.in_(sorted(refused, key=str)),
            combination_group_member.c.valid_to_known_at.is_(None),
        )
    ):
        heads[UUID(str(group_id))][str(contract_id)] = int(head)
    unmoved = {
        group_id
        for group_id, recorded in refused.items()
        if {key: int(value) for key, value in recorded.items()} == heads[group_id]
    }
    if not unmoved:
        return set()
    items: dict[UUID, str] = {}
    for group_id, status in session.execute(
        select(exception_item.c.combination_group_id, exception_item.c.status)
        .where(
            exception_item.c.source == ExceptionSource.ENGINE.value,
            exception_item.c.severity == ExceptionSeverity.BLOCKING.value,
            exception_item.c.combination_group_id.in_(sorted(unmoved, key=str)),
        )
        .order_by(exception_item.c.created_at, exception_item.c.id)
    ):
        items[UUID(str(group_id))] = _text(status)
    return {group_id for group_id in unmoved if items.get(group_id) == ExceptionStatus.WAIVED.value}
