"""The lock record whose datasets stand for a period (04 T-CLS-04, T-CLS-05, T-REF-06
``current_lock_id``; API-S-Period ``dataset_lock``, rev 1.301; ENGINE_SPEC_B S15-R-19 rev 1.167;
item PERMLOCK-DATASETS-1, the supervisor's ruling of 2026-10-02 16:16).

Only a ``LOCK`` record freezes datasets: a ``REOPEN`` and a ``PERMANENT_LOCK`` record hold none
(T-CLS-05). A period's CURRENT record is its ``LOCK`` while it is ``closed``, its ``REOPEN`` from
the reopen until the next lock and its ``PERMANENT_LOCK`` afterwards (T-REF-06), so the current
record is not always the one whose datasets stand. Read by its current record, a permanently
locked period had no dataset: every report run "as locked" of it was created, queued and ended
``FAILED`` (measured on 2026-10-02 through the product).

The datasets that stand for a period are those of

- its current record, while that record is a ``LOCK``;
- the record a current ``PERMANENT_LOCK`` names as ``previous_lock_id``, when that record is a
  ``LOCK`` of the same entity, book and period — the period's last lock: SM-07 admits the
  permanent lock from ``closed`` alone, and every lock record names the record that was current
  when it was written (``commands._persist_lock``);
- no record otherwise: a period never locked, a period under a ``REOPEN`` record, and a
  permanent lock that follows no ``LOCK`` of its period, which no writer of the product leaves.

One rule, two readers: API-S-Period ``dataset_lock`` (``close.queries``) and the refusal of a
report run "as locked" that names a record which froze nothing (``reports.locked``).
"""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, FromClause, Select, and_, case, select

from erev_api.db.tables import period_lock, period_state
from erev_api.enums import LockKind

# The ``LOCK`` record whose datasets stand, beside the period's current record (``stands_for``).
DATASET_LOCK: Final = period_lock.alias("dataset_lock")


def stands_for(current: FromClause = period_lock) -> ColumnElement[bool]:
    """The join of a period's current lock record ``current`` to ``DATASET_LOCK``, the ``LOCK``
    record whose datasets stand for the period (module docstring). It finds the record itself
    for a ``LOCK``, the record it names for a ``PERMANENT_LOCK`` and no row for a ``REOPEN``;
    the record found is a ``LOCK`` of the current record's entity, book and period, or none."""
    named = case(
        (current.c.kind == LockKind.LOCK.value, current.c.id),
        (current.c.kind == LockKind.PERMANENT_LOCK.value, current.c.previous_lock_id),
    )
    return and_(
        DATASET_LOCK.c.tenant_id == current.c.tenant_id,
        DATASET_LOCK.c.id == named,
        DATASET_LOCK.c.kind == LockKind.LOCK.value,
        DATASET_LOCK.c.entity_id == current.c.entity_id,
        DATASET_LOCK.c.book_code == current.c.book_code,
        DATASET_LOCK.c.period_id == current.c.period_id,
    )


def dataset_lock_of(*, entity_id: UUID, book_code: str, period_id: UUID) -> Select[Any]:
    """The id of the ``LOCK`` record whose datasets stand for the entity, book and period, read
    through the period's state row and its current record; no row where none stands."""
    names_current = and_(
        period_lock.c.tenant_id == period_state.c.tenant_id,
        period_lock.c.id == period_state.c.current_lock_id,
    )
    return (
        select(DATASET_LOCK.c.id)
        .select_from(period_state.join(period_lock, names_current).join(DATASET_LOCK, stands_for()))
        .where(
            period_state.c.entity_id == entity_id,
            period_state.c.book_code == book_code,
            period_state.c.period_id == period_id,
        )
    )
