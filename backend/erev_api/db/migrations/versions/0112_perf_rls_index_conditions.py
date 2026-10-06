"""Lane API-GAPS, item PERF-RLS-INDEX-1 (supervisor ruling R-116; number assigned by the
supervisor, register index 90): index keys the row-level-security policy can use (04 NC-20 and
§1.4 "Index conditions under a policy", rev 1.181; dev-guide DG-KRN-DB-10).

Under a policy PostgreSQL makes a caller's condition an index condition only when the function
behind its operator is leakproof. The comparisons of ``uuid``, ``text``, the integers, ``date``
and ``timestamptz`` are; the comparison of an enumeration is not, and only a superuser can mark
it so. A key such as ``(tenant_id, book_code, idempotency_key)`` is therefore entered by the
tenant alone: the enumeration bounds no scan, and neither does the column behind it. Measured
as ``erev_app`` on 200,000 rows of one tenant: for the stored version of a source record and
for the live jobs the planner read the whole table, in 25.6 ms and 16.5 ms; through the same
columns with the enumerations last, and through a partial index on the live states, the two
reads took 0.07 ms and 0.08 ms.

Index definitions only — no table, column, type, function, trigger, grant or data step:

- ``REORDERED``: fifteen keys keep their name, their columns and what they keep unique; the
  enumeration moves behind every column a read binds. ``INSERT … ON CONFLICT (columns)`` infers
  a unique index by its set of columns, and the code that maps a unique violation reads the
  index name, so no statement changes.
- ``REPLACED``: six indexes that led with a status or a kind give way to five partial indexes on
  the values the reads ask for — a predicate is proved from the statement and needs no leakproof
  operator — and three plain ``(tenant_id, <date>)`` indexes for the lists over every status.
  ``ix_outbox_message__due`` holds the messages that are not settled (``status NOT IN
  ('DISPATCHED','DEAD')``): the relay's claim takes a message that is due or one left
  ``DISPATCHING`` for fifteen minutes, and PostgreSQL proves that predicate from both arms of
  the claim — it does not prove a list of the three statuses from an arm that is itself a list.

``schedule_line`` is partitioned: its index is dropped and created on the parent, which does the
same on each partition; the number of indexes on a partitioned table does not change, so the
lock footprint of 05 §2.7 does not either. The downgrade restores the definitions of the
revisions that created the indexes (0012, 0013, 0016, 0021, 0029, 0031, 0038, 0039, 0040, 0041,
0049).

Revision 0112 on 0086: main's head at the supervisor's merge (0115 at the lane's merge of main
42d8f48f; supervisor ruling R-68 (e): a revision keeps its number and follows main's head). A
revision imports nothing of ``erev_api`` beyond the DDL helpers (DG-MIG-12).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from erev_api.db import migration_ops as ops

revision = "0112"
down_revision = "0086"
branch_labels = None
depends_on = None

type Columns = Sequence[str]
# (table, index, unique, the key as it stood, the key now, predicate)
REORDERED: Final[tuple[tuple[str, str, bool, Columns, Columns, str | None], ...]] = (
    (
        "subledger_posting",
        "ux_subledger_posting__idempotency",
        True,
        ("tenant_id", "book_code", "idempotency_key"),
        ("tenant_id", "idempotency_key", "book_code"),
        None,
    ),
    (
        "subledger_posting_seal",
        "ux_subledger_posting_seal__chain",
        True,
        ("tenant_id", "book_code", "chain_seq"),
        ("tenant_id", "chain_seq", "book_code"),
        None,
    ),
    (
        "source_record",
        "ux_source_record__identity",
        True,
        ("tenant_id", "source_system", "object_type", "external_id", "external_version"),
        ("tenant_id", "external_id", "external_version", "source_system", "object_type"),
        None,
    ),
    (
        "source_record",
        "ix_source_record__order",
        False,
        ("tenant_id", "source_system", "object_type", "external_id", "version_order"),
        ("tenant_id", "external_id", "version_order", "source_system", "object_type"),
        None,
    ),
    (
        "source_order",
        "ux_source_order__external",
        True,
        ("tenant_id", "source_system", "external_order_id", "external_version"),
        ("tenant_id", "external_order_id", "external_version", "source_system"),
        None,
    ),
    (
        "source_invoice",
        "ux_source_invoice__external",
        True,
        ("tenant_id", "source_system", "external_invoice_id", "external_version"),
        ("tenant_id", "external_invoice_id", "external_version", "source_system"),
        None,
    ),
    (
        "source_usage",
        "ux_source_usage__external",
        True,
        ("tenant_id", "source_system", "external_usage_id", "external_version"),
        ("tenant_id", "external_usage_id", "external_version", "source_system"),
        None,
    ),
    (
        "source_payment",
        "ux_source_payment__external",
        True,
        ("tenant_id", "source_system", "external_payment_id", "external_version"),
        ("tenant_id", "external_payment_id", "external_version", "source_system"),
        None,
    ),
    (
        "customer",
        "ux_customer__external",
        True,
        ("tenant_id", "source_system", "external_id"),
        ("tenant_id", "external_id", "source_system"),
        "external_id IS NOT NULL",
    ),
    (
        "outbox_message",
        "ux_outbox_message__dedupe",
        True,
        ("tenant_id", "topic", "dedupe_key"),
        ("tenant_id", "dedupe_key", "topic"),
        None,
    ),
    (
        "approval_request",
        "ux_approval_request__pending_subject",
        True,
        ("tenant_id", "subject_type", "subject_id"),
        ("tenant_id", "subject_id", "subject_type"),
        "status = 'PENDING'",
    ),
    (
        "period_state",
        "ux_period_state__period",
        True,
        ("tenant_id", "entity_id", "book_code", "period_id"),
        ("tenant_id", "entity_id", "period_id", "book_code"),
        None,
    ),
    (
        "period_state",
        "ix_period_state__open",
        False,
        ("tenant_id", "entity_id", "book_code", "state", "period_end_date"),
        ("tenant_id", "entity_id", "state", "period_end_date", "book_code"),
        None,
    ),
    (
        "schedule_line",
        "ix_schedule_line__release",
        False,
        (
            "tenant_id",
            "period_end_date",
            "period_id",
            "book_code",
            "entity_id",
            "is_released_at_close",
        ),
        (
            "tenant_id",
            "period_end_date",
            "period_id",
            "entity_id",
            "is_released_at_close",
            "book_code",
        ),
        None,
    ),
    (
        "contract_event",
        "ix_contract_event__type",
        False,
        ("tenant_id", "event_type", "effective_date"),
        ("tenant_id", "effective_date", "event_type"),
        None,
    ),
)

type Index = tuple[str, Columns, str | None]  # (index, key, predicate)
LIVE_JOBS: Final = "state IN ('QUEUED','RUNNING')"
PENDING_REQUESTS: Final = "status = 'PENDING'"
OPEN_ITEMS: Final = "status IN ('OPEN','IN_PROGRESS')"
UNSETTLED_MESSAGES: Final = "status NOT IN ('DISPATCHED','DEAD')"
DUE_DELIVERIES: Final = "status IN ('PENDING','FAILED')"
# (table, the indexes as they stood, the indexes now)
REPLACED: Final[tuple[tuple[str, tuple[Index, ...], tuple[Index, ...]], ...]] = (
    (
        "job",
        (
            ("ix_job__state", ("tenant_id", "state", "created_at"), None),
            ("ix_job__kind", ("tenant_id", "kind", "created_at"), None),
        ),
        (
            ("ix_job__live", ("tenant_id", "created_at"), LIVE_JOBS),
            ("ix_job__created", ("tenant_id", "created_at"), None),
        ),
    ),
    (
        "approval_request",
        (("ix_approval_request__status", ("tenant_id", "status", "submitted_at"), None),),
        (
            ("ix_approval_request__pending", ("tenant_id", "submitted_at"), PENDING_REQUESTS),
            ("ix_approval_request__submitted", ("tenant_id", "submitted_at"), None),
        ),
    ),
    (
        "exception_item",
        (
            (
                "ix_exception_item__status",
                ("tenant_id", "status", "severity", "created_at"),
                None,
            ),
        ),
        (
            ("ix_exception_item__open", ("tenant_id", "created_at"), OPEN_ITEMS),
            ("ix_exception_item__created", ("tenant_id", "created_at"), None),
        ),
    ),
    (
        "outbox_message",
        (("ix_outbox_message__due", ("tenant_id", "status", "next_attempt_at"), None),),
        (("ix_outbox_message__due", ("tenant_id", "next_attempt_at"), UNSETTLED_MESSAGES),),
    ),
    (
        "webhook_delivery",
        (("ix_webhook_delivery__due", ("tenant_id", "status", "next_attempt_at"), None),),
        (("ix_webhook_delivery__due", ("tenant_id", "next_attempt_at"), DUE_DELIVERIES),),
    ),
)


def _drop(index: str) -> None:
    ops.execute(f"DROP INDEX {ops.qualified(index)}")


def _replace(table: str, old: Sequence[Index], new: Sequence[Index]) -> None:
    for index, _, _ in old:
        _drop(index)
    ops.create_indexes(
        table, [(index, list(key), where) for index, key, where in new], unique=False
    )


def upgrade() -> None:
    """Each key in the order the policy can use; a status index as partial and plain ones."""
    for table, index, unique, _, key, where in REORDERED:
        _drop(index)
        ops.create_indexes(table, [(index, list(key), where)], unique=unique)
    for table, old, new in REPLACED:
        _replace(table, old, new)


def downgrade() -> None:
    """The definitions of the revisions that created the indexes (DG-MIG-04)."""
    for table, old, new in reversed(REPLACED):
        _replace(table, new, old)
    for table, index, unique, key, _, where in reversed(REORDERED):
        _drop(index)
        ops.create_indexes(table, [(index, list(key), where)], unique=unique)
