"""Private operational navigation history; never a contract event or accounting mutation."""

from typing import Any

from sqlalchemy import Select, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from erev_api.auth.principal import Principal
from erev_api.db import new_id
from erev_api.db.tables import contract, contract_recent_view
from erev_api.enums import PrincipalKind

LIMIT = 50


def owned(principal: Principal) -> Any:
    row = contract_recent_view.c
    return (
        (row.tenant_id == principal.tenant_id)
        & (row.actor_id == principal.id)
        & (row.actor_kind == principal.kind.value)
    )


def record(session: Session, principal: Principal, contract_id: Any) -> None:
    if principal.id is None or principal.kind not in (PrincipalKind.USER, PrincipalKind.API_CLIENT):
        return
    # Serialize upsert/pruning only for this actor, including concurrent opens in separate tabs.
    key = f"contract-recent:{principal.tenant_id}:{principal.kind.value}:{principal.id}"
    session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))
    session.execute(
        insert(contract_recent_view)
        .values(
            tenant_id=principal.tenant_id,
            id=new_id(),
            actor_id=principal.id,
            actor_kind=principal.kind.value,
            contract_id=contract_id,
            viewed_at=func.clock_timestamp(),
            created_by=principal.id,
            created_by_kind=principal.kind.value,
            updated_by=principal.id,
            updated_by_kind=principal.kind.value,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "actor_id", "actor_kind", "contract_id"],
            set_={"viewed_at": func.clock_timestamp()},
        )
    )
    row = contract_recent_view.c
    retained = (
        select(row.id)
        .where(owned(principal))
        .order_by(row.viewed_at.desc(), row.contract_id.desc())
        .limit(LIMIT)
    )
    session.execute(delete(contract_recent_view).where(owned(principal), row.id.not_in(retained)))


def statement(principal: Principal) -> Select[Any]:
    """Recheck contract visibility now; saved history is never an authorization grant."""
    row = contract_recent_view.c
    return (
        select(row.contract_id, row.viewed_at)
        .join(
            contract, (contract.c.tenant_id == row.tenant_id) & (contract.c.id == row.contract_id)
        )
        .where(owned(principal))
        .order_by(row.viewed_at.desc(), row.contract_id.desc())
        .limit(LIMIT)
    )
