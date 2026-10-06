"""BUILD_SPEC item CLO-1: journal and manual adjustment tables.

04 ids created: E-30 ``je_type``, E-32 ``journal_run_mode``, E-33 ``journal_run_grain``, E-34
``journal_state``, E-36 ``posting_ack_kind``, E-37 ``gl_adapter``, E-93
``manual_adjustment_kind`` and E-94 ``manual_adjustment_status``, each with its rev 1.2 values
(04 §18 rules 5 and 6).

- T-SL-05 ``manual_adjustment`` (IM-S, RLS-TE on ``entity_id``): ``ux_manual_adjustment__no``,
  ``ix_manual_adjustment__period`` and ``ck_manual_adjustment__amount_functional_abs``; the foreign
  keys to ``contract``, ``obligation``, ``legal_entity``, ``period``, ``currency``, ``file_object``,
  ``approval_request``, ``contract_event`` and ``subledger_posting``. DB-03
  ``tg_manual_adjustment__transition``. The key of ``subledger_posting.manual_adjustment_id``, which
  the CTR-3 revision left for this table, is added here (04 §18 rule 2).
- T-SL-06 ``journal_run`` (IM-S, RLS-TE): ``ux_journal_run__no``, ``ix_journal_run__period``, the 04
  checks ``ck_journal_run__book_code``, ``__delta_book``, ``__chain_range`` and ``__totals`` and the
  checks ``__delta_range`` and ``__counts``; the foreign keys to ``legal_entity``, ``period``,
  ``currency``, ``job`` and ``approval_request``. DB-03 ``tg_journal_run__transition``; DB-16
  ``tg_journal_run__coverage`` (``EREV-JR-001``) and ``tg_journal_run__je_sequence``
  (``EREV-JE-002``). The key of ``exception_item.journal_run_id``, which the CTR-5 revision
  left for this table, is added here (DG-MIG-03; chain B follows chain A since the L4 merge).
- T-SL-07 ``journal_batch`` (IM-S, RLS-TE): ``ux_journal_batch__no``,
  ``ux_journal_batch__external``, ``ix_journal_batch__state`` and ``ck_journal_batch__counts``; the
  foreign keys to ``journal_run``, ``legal_entity``, ``period``, ``currency``, ``engine_release``,
  ``file_object`` and ``outbox_message``. DB-03 ``tg_journal_batch__transition``; DB-16
  ``tg_journal_batch__approve`` (``EREV-JE-001``) with its deferred constraint trigger
  ``tg_journal_batch__approve_at_commit`` on the same function; DB-15 ``tg_journal_batch__sandbox``
  (``EREV-SBX-001``).
- T-SL-08 ``journal_entry`` (IM-A, RLS-TE): ``ux_journal_entry__no``, ``ux_journal_entry__seq``,
  ``ix_journal_entry__batch`` and ``ck_journal_entry__je_seq``; the foreign keys to
  ``journal_batch``, ``legal_entity``, ``manual_adjustment`` and itself. DB-01.
- T-SL-09 ``journal_line`` (IM-A, RLS-TE): ``ux_journal_line__no``, ``ix_journal_line__batch``,
  ``ix_journal_line__account``, the 04 checks ``ck_journal_line__txn_amounts`` and
  ``__functional_amounts`` and the check ``__line_no``; the foreign keys to ``journal_entry``,
  ``journal_batch``, ``legal_entity``, ``period``, ``gl_account``, ``currency``, ``contract`` and
  ``obligation``. DB-01; DB-07 ``tg_journal_line__period_guard`` (``EREV-LED-003``; BS4-D-02).
- T-SL-10 ``posting_ack`` (IM-A, RLS-T): ``ix_posting_ack__batch`` and
  ``ck_posting_ack__gl_document`` (the ``gl_document_id`` note); the foreign keys to
  ``journal_batch`` and ``file_object``. DB-01.

``journal_run.close_run_id`` waits for T-CLS-01 (CLO-2) and
``journal_batch.integration_connection_id`` for T-INT-01; their revisions add the keys (DG-MIG-03;
L4-2-Q-13). Every INSERT trigger returns early for a row outside the tenant context or the entity
scope, so row-level security answers 42501 (DG-TST-20; L3-1-Q-19). Eight functions are added.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

# 04 §3.4 with the rev 1.2 values (DG-MIG-06).
ENUMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("je_type", ("automated", "manual", "reversal")),
    ("journal_run_mode", ("GROSS", "DELTA")),
    (
        "journal_run_grain",
        (
            "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS",
            "LEGACY_CONTRACT_POB",
            "CONTRACT_ACCOUNT_DIMENSIONS",
        ),
    ),
    ("journal_state", ("draft", "approved", "exported", "acknowledged", "failed", "cancelled")),
    ("posting_ack_kind", ("POSTED", "REJECTED", "DUPLICATE", "MANUAL_CONFIRMATION")),
    ("gl_adapter", ("CSV", "NETSUITE", "QUICKBOOKS_ONLINE")),
    (
        "manual_adjustment_kind",
        (
            "SCHEDULE_OVERRIDE",
            "MANUAL_RELEASE",
            "MANUAL_DEFER",
            "MANUAL_JOURNAL",
            "ACCOUNT_RECLASS",
        ),
    ),
    (
        "manual_adjustment_status",
        ("DRAFT", "SUBMITTED", "APPROVED", "POSTED", "REJECTED", "VOIDED"),
    ),
)

_SC_M = ("updated_at", "updated_by", "updated_by_kind", "row_version")
# 04 T-SL-05 class IM-S: the draft content (every editable column while DRAFT, less the identity of
# the contract, entity, book and number) and the columns that change afterwards (L4-2-Q-12).
MANUAL_ADJUSTMENT_UPDATE_COLUMNS = (
    "kind",
    "obligation_id",
    "period_id",
    "effective_date",
    "payload",
    "amount_functional_abs",
    "currency",
    "reason_code",
    "memo",
    "impact_preview_file_id",
    "content_sha256",
    "status",
    "approval_request_id",
    "applied_event_id",
    "subledger_posting_id",
    "is_deferred_past_lock",
    *_SC_M,
)
# 04 T-SL-06 and T-SL-07 class IM-S.
JOURNAL_RUN_UPDATE_COLUMNS = (
    "state",
    "approval_request_id",
    "approved_at",
    "exported_at",
    "acknowledged_at",
    "cancelled_at",
    *_SC_M,
)
JOURNAL_BATCH_UPDATE_COLUMNS = (
    "state",
    "export_file_id",
    "export_sha256",
    "outbox_message_id",
    "attempt_count",
    "last_error",
    "exported_at",
    "acknowledged_at",
    *_SC_M,
)

# 04 T-SL-06 column notes.
RUN_DELTA_BOOK_CHECK = (
    "((mode = 'DELTA') = (delta_book_code IS NOT NULL)) "
    "AND (delta_book_code IS NULL OR delta_book_code = 'LEGACY')"
)
RUN_DELTA_RANGE_CHECK = (
    "((delta_from_chain_seq IS NULL) = (delta_to_chain_seq IS NULL)) "
    "AND (delta_to_chain_seq IS NULL OR delta_to_chain_seq >= delta_from_chain_seq)"
)
# 04 T-SL-09 column notes.
LINE_TXN_CHECK = "debit_txn >= 0 AND credit_txn >= 0 AND (debit_txn = 0 OR credit_txn = 0)"
LINE_FUNCTIONAL_CHECK = (
    "debit_functional >= 0 AND credit_functional >= 0 "
    "AND (debit_functional = 0 OR credit_functional = 0)"
)

# DB-03: erev_api.db.transitions.transition_trigger_sql(<table>) at CLO-1; DG-ARC-07 compares the
# installed functions with a fresh rendering.
MANUAL_ADJUSTMENT_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['applied_event_id', 'approval_request_id', 'is_deferred_past_lock', 'row_version', 'status', 'subledger_posting_id', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.applied_event_id IS NOT NULL AND NEW.applied_event_id IS DISTINCT FROM OLD.applied_event_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: applied_event_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.subledger_posting_id IS NOT NULL AND NEW.subledger_posting_id IS DISTINCT FROM OLD.subledger_posting_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: subledger_posting_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>POSTED', 'DRAFT>SUBMITTED', 'POSTED>VOIDED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

JOURNAL_RUN_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['acknowledged_at', 'approval_request_id', 'approved_at', 'cancelled_at', 'exported_at', 'row_version', 'state', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.acknowledged_at IS NOT NULL AND NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: acknowledged_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.approved_at IS NOT NULL AND NEW.approved_at IS DISTINCT FROM OLD.approved_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: approved_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.cancelled_at IS NOT NULL AND NEW.cancelled_at IS DISTINCT FROM OLD.cancelled_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: cancelled_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.state IS DISTINCT FROM OLD.state
     AND (OLD.state::text || '>' || NEW.state::text) <> ALL (ARRAY['approved>cancelled', 'approved>exported', 'draft>approved', 'draft>cancelled', 'exported>acknowledged', 'exported>failed', 'failed>exported']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: state of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.state, NEW.state);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

JOURNAL_BATCH_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['acknowledged_at', 'attempt_count', 'export_file_id', 'export_sha256', 'exported_at', 'last_error', 'outbox_message_id', 'row_version', 'state', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.acknowledged_at IS NOT NULL AND NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: acknowledged_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.state IS DISTINCT FROM OLD.state
     AND (OLD.state::text || '>' || NEW.state::text) <> ALL (ARRAY['approved>cancelled', 'approved>exported', 'draft>approved', 'draft>cancelled', 'exported>acknowledged', 'exported>failed', 'failed>exported']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: state of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.state, NEW.state);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# DB-16: the non-cancelled runs of one (entity, book, period, mode) cover contiguous seal ranges
# from 0. The transaction-level advisory lock on that key serialises the writers of its runs, so
# each sees the runs the others committed.
RUN_COVERAGE_BODY = """
DECLARE
  covered bigint;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN
    RETURN NEW;
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(
    'erev.journal_run:' || NEW.tenant_id::text || ':' || NEW.entity_id::text || ':'
    || NEW.book_code::text || ':' || NEW.period_id::text || ':' || NEW.mode::text, 0));
  SELECT coalesce(max(r.to_chain_seq), 0) INTO covered
    FROM erev.journal_run r
   WHERE r.tenant_id = NEW.tenant_id AND r.entity_id = NEW.entity_id
     AND r.book_code = NEW.book_code AND r.period_id = NEW.period_id AND r.mode = NEW.mode
     AND r.state <> 'cancelled' AND r.id <> NEW.id;
  IF NEW.from_chain_seq IS DISTINCT FROM covered THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-JR-001: run %s starts at chain sequence %s, but the runs of '
                       'entity %s, book %s, period %s and mode %s cover up to %s', NEW.run_no,
                       NEW.from_chain_seq, NEW.entity_id, NEW.book_code, NEW.period_id, NEW.mode,
                       covered);
  END IF;
  RETURN NEW;
END
"""

# DB-16: on approval, the je_seq values of the run's entries per entity form a contiguous range that
# starts right after the entity's greatest je_seq below it (0 when none; L4-2-Q-14).
RUN_JE_SEQUENCE_BODY = """
DECLARE
  gap text;
BEGIN
  IF NEW.state::text <> 'approved' OR OLD.state::text = 'approved' THEN
    RETURN NEW;
  END IF;
  WITH run_entries AS (
    SELECT e.entity_id, min(e.je_seq) AS first_seq, max(e.je_seq) AS last_seq, count(*) AS entries
      FROM erev.journal_entry e
      JOIN erev.journal_batch b ON b.tenant_id = e.tenant_id AND b.id = e.journal_batch_id
     WHERE b.tenant_id = NEW.tenant_id AND b.journal_run_id = NEW.id
     GROUP BY e.entity_id
  ), ranges AS (
    SELECT r.entity_id, r.first_seq, r.last_seq, r.entries,
           coalesce((SELECT max(p.je_seq) FROM erev.journal_entry p
                      WHERE p.tenant_id = NEW.tenant_id AND p.entity_id = r.entity_id
                        AND p.je_seq < r.first_seq), 0) AS previous
      FROM run_entries r
  )
  SELECT string_agg(format('entity %s numbers je_seq %s to %s in %s entries after je_seq %s',
                           g.entity_id, g.first_seq, g.last_seq, g.entries, g.previous),
                    '; ' ORDER BY g.entity_id::text)
    INTO gap
    FROM ranges g
   WHERE g.first_seq <> g.previous + 1 OR g.last_seq - g.first_seq + 1 <> g.entries;
  IF gap IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-JE-002: journal entries of run %s have a sequence gap: %s',
                       NEW.run_no, gap);
  END IF;
  RETURN NEW;
END
"""

# DB-16: a batch moves to approved only when its lines balance in transaction and functional
# currency and their count equals line_count. The BEFORE UPDATE trigger and the deferred constraint
# trigger run this one function; for the constraint trigger the lines are read again at commit.
BATCH_APPROVE_BODY = """
DECLARE
  counted bigint;
  debit_txn_total numeric;
  credit_txn_total numeric;
  debit_functional_total numeric;
  credit_functional_total numeric;
BEGIN
  IF NEW.state::text <> 'approved' OR OLD.state::text = 'approved' THEN
    RETURN NEW;
  END IF;
  SELECT count(*), coalesce(sum(l.debit_txn), 0), coalesce(sum(l.credit_txn), 0),
         coalesce(sum(l.debit_functional), 0), coalesce(sum(l.credit_functional), 0)
    INTO counted, debit_txn_total, credit_txn_total, debit_functional_total,
         credit_functional_total
    FROM erev.journal_line l
   WHERE l.tenant_id = NEW.tenant_id AND l.journal_batch_id = NEW.id;
  IF counted IS DISTINCT FROM NEW.line_count::bigint THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-JE-001: batch %s counts %s lines, but has %s',
                       NEW.external_id, NEW.line_count, counted);
  END IF;
  IF debit_txn_total <> credit_txn_total OR debit_functional_total <> credit_functional_total THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-JE-001: batch %s does not balance: debits %s and credits %s %s, '
                       'debits %s and credits %s %s', NEW.external_id, debit_txn_total,
                       credit_txn_total, NEW.txn_currency, debit_functional_total,
                       credit_functional_total, NEW.functional_currency);
  END IF;
  RETURN NEW;
END
"""
BATCH_APPROVE_AT_COMMIT = (
    "CREATE CONSTRAINT TRIGGER tg_journal_batch__approve_at_commit AFTER UPDATE OF state "
    "ON erev.journal_batch DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
    "EXECUTE FUNCTION erev.tg_journal_batch__approve()"
)

# DB-15: in a sandbox tenant a batch reaches exported only as a CSV download: never through another
# adapter and never with an outbox message.
BATCH_SANDBOX_BODY = """
DECLARE
  tenant_kind text;
BEGIN
  IF TG_OP = 'INSERT' AND (NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false)) THEN
    RETURN NEW;
  END IF;
  IF NEW.state::text <> 'exported' AND NEW.outbox_message_id IS NULL THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.state IS NOT DISTINCT FROM OLD.state
     AND NEW.outbox_message_id IS NOT DISTINCT FROM OLD.outbox_message_id THEN
    RETURN NEW;
  END IF;
  SELECT t.kind::text INTO tenant_kind FROM erev.tenant t WHERE t.id = NEW.tenant_id;
  IF tenant_kind = 'sandbox'
     AND (NEW.adapter::text <> 'CSV' OR NEW.outbox_message_id IS NOT NULL) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-SBX-001: batch %s of a sandbox tenant is exported only as a CSV '
                       'download, not through adapter %s or an outbox message',
                       NEW.external_id, NEW.adapter);
  END IF;
  RETURN NEW;
END
"""

# DB-07 (rev 1.3; BS4-D-02): a journal line posts into an open, closing or reopened period of its
# entity and book, as a subledger line does.
LINE_PERIOD_GUARD_BODY = """
DECLARE
  period_state_now text;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN
    RETURN NEW;
  END IF;
  SELECT s.state::text INTO period_state_now
    FROM erev.period_state s
   WHERE s.tenant_id = NEW.tenant_id AND s.entity_id = NEW.entity_id
     AND s.book_code = NEW.book_code AND s.period_id = NEW.period_id;
  IF period_state_now IS NULL OR period_state_now NOT IN ('open', 'closing', 'reopened') THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-003: period %s of entity %s is %s in book %s, so journal line %s '
                       'cannot post into it', NEW.period_id, NEW.entity_id,
                       coalesce(period_state_now, 'without a state'), NEW.book_code, NEW.id);
  END IF;
  RETURN NEW;
END
"""


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _text(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Text(), nullable=nullable)


def _integer(name: str, *, default: str | None = None) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(name, sa.Integer(), nullable=False, server_default=server_default)


def _bigint(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.BigInteger(), nullable=nullable)


def _named(
    name: str, type_name: str, *, nullable: bool, default: str | None = None
) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(
        name, ops.NamedType(type_name), nullable=nullable, server_default=server_default
    )


def _date(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Date(), nullable=nullable)


def _instant(name: str, *, nullable: bool = True, now_default: bool = False) -> sa.Column[Any]:
    server_default = sa.text("now()") if now_default else None
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=nullable, server_default=server_default
    )


def _flag(name: str) -> sa.Column[Any]:
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("false"))


def _create_manual_adjustment() -> None:
    table = "manual_adjustment"
    ops.create_tenant_table(
        table,
        _text("adjustment_no", nullable=False),
        _named("kind", "erev.manual_adjustment_kind", nullable=False),
        _named("status", "erev.manual_adjustment_status", nullable=False, default="'DRAFT'"),
        _uuid("contract_id", nullable=False),
        _uuid("obligation_id"),
        _uuid("entity_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _uuid("period_id", nullable=False),
        _date("effective_date", nullable=False),
        _named("payload", "jsonb", nullable=False),
        _named("amount_functional_abs", "erev.money", nullable=False),
        _named("currency", "erev.currency_code", nullable=False),
        _text("reason_code", nullable=False),
        _named("memo", "erev.memo", nullable=False),
        _uuid("impact_preview_file_id"),
        _named("content_sha256", "erev.sha256", nullable=True),
        _uuid("approval_request_id"),
        _uuid("applied_event_id"),
        _uuid("subledger_posting_id"),
        _flag("is_deferred_past_lock"),
        standard_sets=["SC-C", "SC-M"],
        checks=[("ck_manual_adjustment__amount_functional_abs", "amount_functional_abs >= 0")],
        unique=[("ux_manual_adjustment__no", ["tenant_id", "adjustment_no"], None)],
        indexes=[
            (
                "ix_manual_adjustment__period",
                ["tenant_id", "entity_id", "book_code", "period_id", "status"],
                None,
            )
        ],
    )
    ops.add_tenant_fk(table, "contract_id", "contract")
    ops.add_tenant_fk(table, "obligation_id", "obligation")
    ops.add_tenant_fk(table, "entity_id", "legal_entity")
    ops.add_tenant_fk(table, "period_id", "period")
    ops.add_global_fk(table, "currency", "currency", target_column="code")
    ops.add_tenant_fk(table, "impact_preview_file_id", "file_object")
    ops.add_tenant_fk(table, "approval_request_id", "approval_request")
    ops.add_tenant_fk(table, "applied_event_id", "contract_event")
    ops.add_tenant_fk(table, "subledger_posting_id", "subledger_posting")
    ops.apply_class(table, "IM-S", update_columns=MANUAL_ADJUSTMENT_UPDATE_COLUMNS)
    ops.enable_rls(table, "RLS-TE", entity_column="entity_id")
    ops.create_trigger(
        table, "transition", MANUAL_ADJUSTMENT_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )
    # 04 §18 rule 2: the posting's key to the adjustment waited for this table.
    ops.add_tenant_fk("subledger_posting", "manual_adjustment_id", table)


def _create_journal_run() -> None:
    table = "journal_run"
    ops.create_tenant_table(
        table,
        _text("run_no", nullable=False),
        _uuid("entity_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _uuid("period_id", nullable=False),
        _named("mode", "erev.journal_run_mode", nullable=False),
        _named("delta_book_code", "erev.book_code", nullable=True),
        _named("grain", "erev.journal_run_grain", nullable=False),
        _named("state", "erev.journal_state", nullable=False, default="'draft'"),
        _instant("cutoff_known_at", nullable=False),
        _bigint("from_chain_seq", nullable=False),
        _bigint("to_chain_seq", nullable=False),
        _bigint("delta_from_chain_seq"),
        _bigint("delta_to_chain_seq"),
        _named("functional_currency", "erev.currency_code", nullable=False),
        _integer("line_count"),
        _named("total_debit_functional", "erev.money", nullable=False),
        _named("total_credit_functional", "erev.money", nullable=False),
        _uuid("close_run_id"),
        _uuid("job_id"),
        _uuid("approval_request_id"),
        _instant("approved_at"),
        _instant("exported_at"),
        _instant("acknowledged_at"),
        _instant("cancelled_at"),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_journal_run__book_code", "book_code <> 'LEGACY'"),
            ("ck_journal_run__delta_book", RUN_DELTA_BOOK_CHECK),
            ("ck_journal_run__chain_range", "to_chain_seq >= from_chain_seq"),
            ("ck_journal_run__totals", "total_debit_functional = total_credit_functional"),
            ("ck_journal_run__delta_range", RUN_DELTA_RANGE_CHECK),
            ("ck_journal_run__counts", "from_chain_seq >= 0 AND line_count >= 0"),
        ],
        unique=[("ux_journal_run__no", ["tenant_id", "run_no"], None)],
        indexes=[
            (
                "ix_journal_run__period",
                ["tenant_id", "entity_id", "book_code", "period_id", "created_at"],
                None,
            )
        ],
    )
    ops.add_tenant_fk(table, "entity_id", "legal_entity")
    ops.add_tenant_fk(table, "period_id", "period")
    ops.add_global_fk(table, "functional_currency", "currency", target_column="code")
    ops.add_tenant_fk(table, "job_id", "job")
    ops.add_tenant_fk(table, "approval_request_id", "approval_request")
    ops.apply_class(table, "IM-S", update_columns=JOURNAL_RUN_UPDATE_COLUMNS)
    ops.enable_rls(table, "RLS-TE", entity_column="entity_id")
    ops.create_trigger(
        table, "transition", JOURNAL_RUN_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )
    ops.create_trigger(table, "coverage", RUN_COVERAGE_BODY, timing="BEFORE", events="INSERT")
    ops.create_trigger(
        table, "je_sequence", RUN_JE_SEQUENCE_BODY, timing="BEFORE", events="UPDATE OF state"
    )
    # DG-MIG-03: the exception queue's key to the run waited for this table (CTR-5, 0041).
    ops.add_tenant_fk("exception_item", "journal_run_id", table)


def _create_journal_batch() -> None:
    table = "journal_batch"
    ops.create_tenant_table(
        table,
        _uuid("journal_run_id", nullable=False),
        _integer("batch_no"),
        _integer("chunk_no", default="1"),
        _uuid("entity_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _uuid("period_id", nullable=False),
        _named("txn_currency", "erev.currency_code", nullable=False),
        _named("functional_currency", "erev.currency_code", nullable=False),
        _named("state", "erev.journal_state", nullable=False, default="'draft'"),
        _integer("line_count"),
        _named("total_debit_txn", "erev.money", nullable=False),
        _named("total_credit_txn", "erev.money", nullable=False),
        _named("total_debit_functional", "erev.money", nullable=False),
        _named("total_credit_functional", "erev.money", nullable=False),
        _uuid("engine_release_id", nullable=False),
        _named("adapter", "erev.gl_adapter", nullable=False),
        _uuid("integration_connection_id"),
        _text("external_id", nullable=False),
        _uuid("export_file_id"),
        _named("export_sha256", "erev.sha256", nullable=True),
        _uuid("detail_file_id"),
        _named("detail_sha256", "erev.sha256", nullable=True),
        _uuid("outbox_message_id"),
        _integer("attempt_count", default="0"),
        _text("last_error"),
        _instant("exported_at"),
        _instant("acknowledged_at"),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            (
                "ck_journal_batch__counts",
                "batch_no >= 1 AND chunk_no >= 1 AND line_count >= 0 AND attempt_count >= 0",
            )
        ],
        unique=[
            (
                "ux_journal_batch__no",
                ["tenant_id", "journal_run_id", "batch_no", "chunk_no"],
                None,
            ),
            ("ux_journal_batch__external", ["tenant_id", "external_id"], None),
        ],
        indexes=[
            ("ix_journal_batch__state", ["tenant_id", "entity_id", "period_id", "state"], None)
        ],
    )
    ops.add_tenant_fk(table, "journal_run_id", "journal_run")
    ops.add_tenant_fk(table, "entity_id", "legal_entity")
    ops.add_tenant_fk(table, "period_id", "period")
    ops.add_global_fk(table, "txn_currency", "currency", target_column="code")
    ops.add_global_fk(table, "functional_currency", "currency", target_column="code")
    ops.add_global_fk(table, "engine_release_id", "engine_release")
    ops.add_tenant_fk(table, "export_file_id", "file_object")
    ops.add_tenant_fk(table, "detail_file_id", "file_object")
    ops.add_tenant_fk(table, "outbox_message_id", "outbox_message")
    ops.apply_class(table, "IM-S", update_columns=JOURNAL_BATCH_UPDATE_COLUMNS)
    ops.enable_rls(table, "RLS-TE", entity_column="entity_id")
    ops.create_trigger(
        table, "transition", JOURNAL_BATCH_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )
    ops.create_trigger(
        table, "approve", BATCH_APPROVE_BODY, timing="BEFORE", events="UPDATE OF state"
    )
    ops.execute(BATCH_APPROVE_AT_COMMIT)
    ops.create_trigger(
        table, "sandbox", BATCH_SANDBOX_BODY, timing="BEFORE", events="INSERT OR UPDATE"
    )


def _create_journal_entry() -> None:
    table = "journal_entry"
    ops.create_tenant_table(
        table,
        _uuid("journal_batch_id", nullable=False),
        _uuid("entity_id", nullable=False),
        _bigint("je_seq", nullable=False),
        _text("je_no", nullable=False),
        _named("je_type", "erev.je_type", nullable=False),
        _named("entry_kind", "erev.subledger_entry_kind", nullable=True),
        _text("description", nullable=False),
        _named("source_event_ids", "uuid[]", nullable=False, default="'{}'::uuid[]"),
        _uuid("manual_adjustment_id"),
        _uuid("reverses_journal_entry_id"),
        _flag("is_post_close"),
        standard_sets=["SC-C"],
        checks=[("ck_journal_entry__je_seq", "je_seq >= 1")],
        unique=[
            ("ux_journal_entry__no", ["tenant_id", "je_no"], None),
            ("ux_journal_entry__seq", ["tenant_id", "entity_id", "je_seq"], None),
        ],
        indexes=[("ix_journal_entry__batch", ["tenant_id", "journal_batch_id"], None)],
    )
    ops.add_tenant_fk(table, "journal_batch_id", "journal_batch")
    ops.add_tenant_fk(table, "entity_id", "legal_entity")
    ops.add_tenant_fk(table, "manual_adjustment_id", "manual_adjustment")
    ops.add_tenant_fk(table, "reverses_journal_entry_id", "journal_entry")
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-TE", entity_column="entity_id")


def _create_journal_line() -> None:
    table = "journal_line"
    ops.create_tenant_table(
        table,
        _uuid("journal_entry_id", nullable=False),
        _uuid("journal_batch_id", nullable=False),
        _integer("line_no"),
        _uuid("entity_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _uuid("period_id", nullable=False),
        _named("account_role", "erev.account_role", nullable=False),
        _uuid("gl_account_id", nullable=False),
        _text("gl_account_code", nullable=False),
        _named("dimensions", "jsonb", nullable=False, default="'{}'::jsonb"),
        _named("dimension_set_sha256", "erev.sha256", nullable=False),
        _named("txn_currency", "erev.currency_code", nullable=False),
        _named("debit_txn", "erev.money", nullable=False, default="0"),
        _named("credit_txn", "erev.money", nullable=False, default="0"),
        _named("functional_currency", "erev.currency_code", nullable=False),
        _named("debit_functional", "erev.money", nullable=False, default="0"),
        _named("credit_functional", "erev.money", nullable=False, default="0"),
        _uuid("contract_id"),
        _uuid("obligation_id"),
        _text("legacy_key"),
        _uuid("counterparty_entity_id"),
        _uuid("origin_period_id"),
        _named("fx_rate_set_version_ids", "uuid[]", nullable=False, default="'{}'::uuid[]"),
        _named("fx_rate_ids", "uuid[]", nullable=False, default="'{}'::uuid[]"),
        _text("memo"),
        _integer("source_line_count"),
        _named("source_grouping_sha256", "erev.sha256", nullable=False),
        standard_sets=["SC-C"],
        checks=[
            ("ck_journal_line__txn_amounts", LINE_TXN_CHECK),
            ("ck_journal_line__functional_amounts", LINE_FUNCTIONAL_CHECK),
            ("ck_journal_line__line_no", "line_no >= 1"),
        ],
        unique=[("ux_journal_line__no", ["tenant_id", "journal_entry_id", "line_no"], None)],
        indexes=[
            ("ix_journal_line__batch", ["tenant_id", "journal_batch_id"], None),
            (
                "ix_journal_line__account",
                ["tenant_id", "entity_id", "period_id", "gl_account_id"],
                None,
            ),
        ],
    )
    ops.add_tenant_fk(table, "journal_entry_id", "journal_entry")
    ops.add_tenant_fk(table, "journal_batch_id", "journal_batch")
    ops.add_tenant_fk(table, "entity_id", "legal_entity")
    ops.add_tenant_fk(table, "period_id", "period")
    ops.add_tenant_fk(table, "gl_account_id", "gl_account")
    ops.add_global_fk(table, "txn_currency", "currency", target_column="code")
    ops.add_global_fk(table, "functional_currency", "currency", target_column="code")
    ops.add_tenant_fk(table, "contract_id", "contract")
    ops.add_tenant_fk(table, "obligation_id", "obligation")
    ops.add_tenant_fk(table, "counterparty_entity_id", "legal_entity")
    ops.add_tenant_fk(table, "origin_period_id", "period")
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-TE", entity_column="entity_id")
    ops.create_trigger(
        table, "period_guard", LINE_PERIOD_GUARD_BODY, timing="BEFORE", events="INSERT"
    )


def _create_posting_ack() -> None:
    table = "posting_ack"
    ops.create_tenant_table(
        table,
        _uuid("journal_batch_id", nullable=False),
        _named("ack_kind", "erev.posting_ack_kind", nullable=False),
        _text("gl_document_id"),
        _date("gl_posted_date"),
        _named("response_sha256", "erev.sha256", nullable=True),
        _uuid("response_file_id"),
        _text("message"),
        _instant("received_at", nullable=False, now_default=True),
        standard_sets=["SC-C"],
        checks=[
            ("ck_posting_ack__gl_document", "ack_kind = 'REJECTED' OR gl_document_id IS NOT NULL")
        ],
        indexes=[("ix_posting_ack__batch", ["tenant_id", "journal_batch_id", "received_at"], None)],
    )
    ops.add_tenant_fk(table, "journal_batch_id", "journal_batch")
    ops.add_tenant_fk(table, "response_file_id", "file_object")
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-T")


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    for name, values in ENUMS:
        ops.create_enum(name, values)
    _create_manual_adjustment()
    _create_journal_run()
    _create_journal_batch()
    _create_journal_entry()
    _create_journal_line()
    _create_posting_ack()


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute("ALTER TABLE erev.exception_item DROP CONSTRAINT fk_exception_item__journal_run")
    ops.execute(
        "ALTER TABLE erev.subledger_posting DROP CONSTRAINT fk_subledger_posting__manual_adjustment"
    )
    for table in (
        "posting_ack",
        "journal_line",
        "journal_entry",
        "journal_batch",
        "journal_run",
        "manual_adjustment",
    ):
        ops.drop_tenant_table(table)
    for name, _ in reversed(ENUMS):
        ops.drop_enum(name)
