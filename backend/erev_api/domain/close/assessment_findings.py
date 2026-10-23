"""Persist engine period-end assessment gaps and settle only superseded scoped findings."""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import exception_item
from erev_api.domain.contracts.bundles import BundleIndex
from erev_api.domain.imports import exceptions
from erev_api.enums import ExceptionSeverity, ExceptionSource
from erev_api.uow import UnitOfWork

from .gates import PeriodScope

CODES = frozenset({"VC_REASSESSMENT_MISSING", "ROYALTY_ACCRUAL_MISSING"})
MARKER = "close_period_v1"


def record(
    uow: UnitOfWork,
    scope: PeriodScope,
    group_id: UUID,
    found: BundleIndex,
    facts: Sequence[Mapping[str, Any]],
    *,
    input_sha256: str,
) -> None:
    """A successful final close pass assesses one group's selected entity/book/period only."""
    selected = [
        fact
        for fact in facts
        if fact["book_code"] == scope.book_code
        and fact["entity"] == scope.entity_code
        and fact["period_key"] == scope.period_key
    ]
    active: set[str] = set()
    for fact in selected:
        code = str(fact["code"])
        if code not in CODES:
            raise ValueError(f"Unknown close assessment {code}")
        contract_row = found.contracts[str(fact["contract_key"])]
        if UUID(str(contract_row["contracting_entity_id"])) != scope.entity_id:
            raise ValueError("Close assessment contract differs from selected entity")
        subject = fact.get("estimate_key") or fact.get("subject_key")
        identity = f"{scope.state_id}:{contract_row['id']}:{subject}"
        if code == "ROYALTY_ACCRUAL_MISSING":
            identity += f":{fact['usage_period_start']}:{fact['usage_period_end']}"
            message = (
                f"Royalty statement or accrual is missing for {fact['usage_period_start']} "
                f"through {fact['usage_period_end']} in {scope.book_code}."
            )
        else:
            message = (
                f"Variable consideration {subject} has no period-end reassessment "
                f"for {scope.period_key} in {scope.book_code}."
            )
        key = exceptions.dedupe_key(ExceptionSource.CLOSE, code, identity)
        active.add(key)
        payload = {k: v.isoformat() if isinstance(v, date) else v for k, v in fact.items()}
        payload.update(assessment=MARKER, input_sha256=input_sha256)
        obligation = found.obligations.get(str(fact.get("subject_key")))
        exceptions.raise_exception_item(
            uow,
            source=ExceptionSource.CLOSE,
            code=code,
            severity=ExceptionSeverity.BLOCKING,
            message=message,
            business_key=(
                str(subject).removeprefix(str(fact["contract_key"]) + "/")
                if code == "VC_REASSESSMENT_MISSING"
                else None
            ),
            dedupe=key,
            contract_id=UUID(str(contract_row["id"])),
            obligation_id=None if obligation is None else UUID(str(obligation["id"])),
            combination_group_id=group_id,
            entity_id=scope.entity_id,
            period_id=scope.period_id,
            source_payload=payload,
        )
    previous = uow.session.execute(
        select(exception_item.c.id, exception_item.c.dedupe_key).where(
            exception_item.c.source == ExceptionSource.CLOSE.value,
            exception_item.c.code.in_(sorted(CODES)),
            exception_item.c.entity_id == scope.entity_id,
            exception_item.c.period_id == scope.period_id,
            exception_item.c.contract_id.in_([row["id"] for row in found.contracts.values()]),
            exception_item.c.source_payload["assessment"].astext == MARKER,
            exception_item.c.source_payload["book_code"].astext == scope.book_code,
            exception_item.c.status.in_(("OPEN", "IN_PROGRESS")),
        )
    ).all()
    for item_id, key in previous:
        if key not in active:
            exceptions.settle_record_reprocess(
                uow,
                item_id,
                resolved=True,
                resolution=(
                    f"Rechecked {scope.book_code} {scope.period_key}; the gap no longer exists."
                ),
            )
