"""One lock order for every unit of work that touches both the combination-group row and a contract
row (dev-guide DG-KRN-DB-08 rev 1.36; D-98 candidates 101a and 101b).

The two rows are locked explicitly (``repo.get_contract(for_update=True)``, ``repo.lock_group``), by
the implicit row locks of ``UPDATE`` statements (``events.stream._raise_head`` on ``contract``,
``_mark_dirty`` on ``combination_group``, ``computation._update_heads``) and transitively
(``append_events``, ``compute_group``, imports, approval hooks). Whatever the path, the group row is
locked first: ``lock_group_then_contract`` reads the contract without a lock for its group id, locks
the group row, then (``between``) the proposal / judgement record the path holds, then the contract
row, and re-verifies under the locks that the contract's group EQUALS the one read before — no pre-
lock check is the last check (D-98 candidate 101c; a residual 40P01 is 409 ``lock-conflict``,
resubmitted by the client, never retried automatically). A kernel module, so the approval hooks
(``approvals.subjects``) and the domain share one implementation.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Final
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from erev_api.db.tables import combination_group, contract
from erev_api.problems import Problem

__all__ = [
    "REGROUPED",
    "hold_fx_publication",
    "holds_chain_head",
    "lock_group_then_contract",
    "lock_groups_then_contracts",
    "mark_chain_head",
]

# The contract left the group locked for it between the unlocked read and the row lock: the request
# is stale (412), never continued on a group that no longer holds the contract.
REGROUPED: Final = (
    "This contract joined another combination group while the request was being checked. "
    "Reload to see the latest version, then try again."
)


# dev-guide DG-KRN-DB-08 (1c) rev 1.218 (finding F4 of the independent review of 2026-10-01): a
# transaction that holds a ``ledger_chain_head`` row waits for no ``period_state`` row — every
# posting of that book in the workspace queues behind the head. ``subledger.post`` marks the
# transaction; a window read made under the mark is NOWAIT (``period_ends._window_rows_held``).
_CHAIN_HEAD: Final = "erev.ledger_chain_head"


def mark_chain_head(session: Session) -> None:
    """This transaction has taken a ``ledger_chain_head`` row. The mark is the transaction itself,
    so it ends with it; a savepoint that took the head and was rolled back leaves it set — the
    reads after it then refuse where they could have waited, which costs a resubmission and
    never a wait under a head."""
    session.info[_CHAIN_HEAD] = session.get_transaction()


def holds_chain_head(session: Session) -> bool:
    """Whether ``mark_chain_head`` was called in the transaction the session is in."""
    held = session.info.get(_CHAIN_HEAD)
    return held is not None and held is session.get_transaction()


def hold_fx_publication(session: Session, tenant_id: UUID, *, exclusive: bool = False) -> None:
    """Transaction gate for FX publication and estimate decisions (B1-7).

    Estimate submission and final approval take a shared lock before group/contract locks;
    FX publication takes the exclusive side before changing status or touching groups.
    This also covers a new rate set, for which a reader could lock no existing parent row.
    Multiple estimates proceed together; tenants have separate keys.
    """
    key = func.hashtextextended(f"erev:fx-publication:{tenant_id}", 0)
    lock = func.pg_advisory_xact_lock if exclusive else func.pg_advisory_xact_lock_shared
    session.execute(select(lock(key)))


def lock_group_then_contract(
    session: Session, contract_id: UUID, *, between: Callable[[UUID], object] | None = None
) -> tuple[UUID, dict[str, Any]]:
    """Lock the contract's combination group row, then the contract row, and return
    ``(group_id, contract row)``; 404 ``not-found`` when either is not visible, 412
    ``precondition-failed`` when the contract's group under the lock differs from the one read
    before it (equality, D-98 candidate 101c). ``between`` takes the rows the order places between
    the two tiers — the proposal / judgement record — and runs with the locked group id after the
    group lock and before the contract lock (DG-KRN-DB-08 rev 1.36)."""
    peek = session.execute(
        select(contract.c.combination_group_id).where(contract.c.id == contract_id)
    ).scalar_one_or_none()
    if peek is None:
        raise Problem("not-found")
    group_id = UUID(str(peek))
    locked_group = session.execute(
        select(combination_group.c.id).where(combination_group.c.id == group_id).with_for_update()
    ).scalar_one_or_none()
    if locked_group is None:
        raise Problem("not-found")
    if between is not None:
        between(group_id)
    row = (
        session.execute(select(contract).where(contract.c.id == contract_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    if UUID(str(row["combination_group_id"])) != group_id:
        raise Problem("precondition-failed", REGROUPED)
    return group_id, dict(row)


def lock_groups_then_contracts(
    session: Session, contract_ids: Iterable[UUID]
) -> dict[UUID, dict[str, Any]]:
    """Several contracts on the one order (DG-KRN-DB-08): their groups read without locks, every
    group row ``FOR UPDATE`` in ascending id order, then every contract row ``FOR UPDATE`` in
    ascending id order, each contract's group re-verified for EQUALITY with the observed one
    (412 ``precondition-failed`` on a difference). Returns the locked contract rows by id. Used by
    an import's consumption of its approved basis (D-98 candidate 119), before any effect."""
    wanted = sorted(set(contract_ids))
    if not wanted:
        return {}
    observed = {
        UUID(str(row.id)): UUID(str(row.combination_group_id))
        for row in session.execute(
            select(contract.c.id, contract.c.combination_group_id).where(contract.c.id.in_(wanted))
        )
    }
    missing = [cid for cid in wanted if cid not in observed]
    if missing:
        raise Problem("not-found")
    for group_id in sorted(set(observed.values())):
        session.execute(
            select(combination_group.c.id)
            .where(combination_group.c.id == group_id)
            .with_for_update()
        ).scalar_one_or_none()
    rows: dict[UUID, dict[str, Any]] = {}
    for cid in wanted:
        row = (
            session.execute(select(contract).where(contract.c.id == cid).with_for_update())
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise Problem("not-found")
        if UUID(str(row["combination_group_id"])) != observed[cid]:
            raise Problem("precondition-failed", REGROUPED)
        rows[cid] = dict(row)
    return rows
