"""BUILD_SPEC item CLO-2: close tables and the system close checklist.

04 ids created: E-58 ``reconciliation_kind``, E-59 ``reconciliation_status``, E-60
``checklist_status``, E-61 ``checklist_gate_kind``, E-62 ``close_run_status``, E-63 ``lock_kind``,
E-64 ``snapshot_kind`` and E-99 ``signoff_role``, each with its rev 1.2 values (04 §18 rules 5 and
6).

- T-CLS-01 ``close_run`` (IM-S, RLS-TE on ``entity_id``): ``ux_close_run__no``,
  ``ux_close_run__active`` and the checks ``ck_close_run__steps``, ``__counts`` and
  ``__current_step_code``; the foreign keys to ``legal_entity``, ``period`` and ``job``. DB-03
  ``tg_close_run__transition``, under which a SUCCEEDED run changes only the ``LOCK`` element of
  ``steps`` (BS4-D-03). The keys ``close_run_id`` of ``period_state_transition``,
  ``contract_computation``, ``subledger_posting``, ``journal_run`` and ``exception_item``, which
  earlier revisions left for this table, are added here (DG-MIG-03).
- T-CLS-02 ``close_checklist_template`` (IM-M, RLS-T): ``ux_close_checklist_template__code`` and
  the checks ``__gate_check_code`` and ``__due_offset_days``; the foreign key to ``role``.
  ``tg_close_checklist_template__system``: a system row changes only in ``owner_role_id``,
  ``due_offset_days`` and SC-M and is never deleted, and a tenant row never becomes a system row
  (``EREV-TRN-001``).
- T-CLS-03 ``close_checklist_item`` (IM-M without DELETE, RLS-TE on ``entity_id``): the 04 key
  ``ux_close_checklist_item`` named ``ux_close_checklist_item__period`` (NC-16) and the check
  ``__waiver``; the foreign keys to the template, ``legal_entity``, ``period``,
  ``tenant_membership``, ``signoff`` and ``approval_request``. DB-03
  ``tg_close_checklist_item__transition``.
- T-CLS-04 ``period_lock`` (IM-A, RLS-TE on ``entity_id``): ``ix_period_lock__period``, the 04
  check ``ck_period_lock__reason_code`` and the check ``__chain_seq``; the foreign keys to
  ``legal_entity``, ``period``, ``period_state_transition`` (deferrable, because the transition row
  names the lock as well), ``approval_request``, ``file_object`` and itself. DB-01. The keys
  ``period_state.current_lock_id`` and ``period_state_transition.period_lock_id`` are added here.
- T-CLS-05 ``lock_snapshot`` (IM-A, RLS-T): the 04 key ``ux_lock_snapshot`` named
  ``ux_lock_snapshot__kind`` and the check ``__row_count``; the foreign keys to ``period_lock`` and
  ``file_object``. DB-01.
- T-CLS-06 ``reconciliation`` (IM-S, RLS-TE on ``entity_id``): ``ux_reconciliation__no``,
  ``ix_reconciliation__period`` and the check ``__variance_count``; the foreign keys to
  ``legal_entity``, ``period``, ``period_lock``, ``file_object``, ``rule_set_version`` and ``rule``.
  DB-03 ``tg_reconciliation__transition``: nothing changes after CERTIFIED except the move to
  REOPENED.
- T-CLS-07 ``reconciliation_item`` (IM-S, RLS-T): ``ix_reconciliation_item__recon``, the 04 check
  ``ck_reconciliation_item__item_kind`` and the check ``__high_risk``; the foreign keys to
  ``reconciliation``, ``contract`` and ``currency``. DB-03 ``tg_reconciliation_item__transition``:
  nothing changes while the parent is CERTIFIED or not visible.
- T-CLS-08 ``signoff`` (IM-A, RLS-T): the 04 key ``ux_signoff`` named ``ux_signoff__signer`` and the
  04 check ``ck_signoff__subject_type``; the foreign key to ``app_user``. DB-01; DB-10
  ``tg_signoff__separation`` (``EREV-APR-001``).

``close_checklist_item.control_execution_id`` waits for T-PLT-39, ``lock_snapshot.report_run_id``
and ``reconciliation.report_run_id`` for T-RPT-02 (RPS-1), and ``reconciliation.sync_run_id`` for
T-INT-02; the revisions that create those tables add the keys (DG-MIG-03; L4-2-Q-24). Every INSERT
trigger returns early for a row outside the tenant context, so row-level security answers 42501
(L3-1-Q-19). Six functions are added.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

# 04 §3.4 with the rev 1.2 values (DG-MIG-06).
ENUMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "reconciliation_kind",
        (
            "BILLING_TO_SUBLEDGER",
            "SUBLEDGER_TO_GL",
            "CONTRACT_BALANCE_ROLLFORWARD",
            "RPO_ROLLFORWARD",
            "MIGRATION_OPENING_BALANCE",
        ),
    ),
    (
        "reconciliation_status",
        ("DRAFT", "PREPARED", "AUTO_CERTIFIED", "REVIEWED", "CERTIFIED", "REOPENED"),
    ),
    (
        "checklist_status",
        ("NOT_STARTED", "IN_PROGRESS", "PASSED", "FAILED", "WAIVED", "NOT_APPLICABLE"),
    ),
    ("checklist_gate_kind", ("AUTOMATIC", "MANUAL")),
    ("close_run_status", ("PENDING", "RUNNING", "BLOCKED", "SUCCEEDED", "FAILED", "CANCELLED")),
    ("lock_kind", ("LOCK", "REOPEN", "PERMANENT_LOCK")),
    (
        "snapshot_kind",
        (
            "WATERFALL",
            "CONTRACT_BALANCES",
            "CONTRACT_BALANCE_ROLLFORWARD",
            "RPO",
            "RPO_ROLLFORWARD",
            "DISAGGREGATION",
            "PRIOR_PERIOD_POB_REVENUE",
            "COST_ROLLFORWARD",
            "JE_POPULATION",
            "OUT_OF_PERIOD_REGISTER",
            "MODIFICATION_REGISTER",
            "MANUAL_ADJUSTMENT_REGISTER",
        ),
    ),
    ("signoff_role", ("PREPARER", "REVIEWER", "CONTROLLER")),
)

_SC_M = ("updated_at", "updated_by", "updated_by_kind", "row_version")
# 04 T-CLS-01, T-CLS-06 and T-CLS-07 class IM-S.
CLOSE_RUN_UPDATE_COLUMNS = (
    "status",
    "current_step_code",
    "steps",
    "counts",
    "started_at",
    "finished_at",
    *_SC_M,
)
RECONCILIATION_UPDATE_COLUMNS = (
    "status",
    "totals",
    "variance_count",
    "unexplained_other_amount",
    "report_run_id",
    "certified_at",
    *_SC_M,
)
RECONCILIATION_ITEM_UPDATE_COLUMNS = (
    "explanation",
    "resolved_at",
    "resolved_by",
    "resolved_by_kind",
    *_SC_M,
)


def _literals(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


# 04 T-CLS-01 ``steps``: the fixed step order (REQ-CLS-012).
STEP_CODES = (
    "CUTOFF",
    "INTERFACE_COMPLETENESS",
    "EXCEPTION_CHECK",
    "RECOMPUTE_DIRTY",
    "RELEASE_SCHEDULES",
    "FX_REMEASUREMENT",
    "NETTING_RECLASS",
    "INVARIANTS",
    "JOURNAL_SUMMARIZATION",
    "EXPORT",
    "ACKNOWLEDGEMENT_WAIT",
    "GL_TIE_OUT",
    "DATASET_FREEZE",
    "LOCK",
)
# 04 T-CLS-02 ``gate_check_code`` (REQ-CLS-008, -009).
GATE_CHECK_CODES = (
    "INTERFACES_COMPLETE",
    "JE_BALANCED",
    "JE_COMPLETE",
    "APPROVALS_CLEARED",
    "EXCEPTIONS_CLEARED",
    "HOLDS_REVIEWED",
    "BATCHES_ACKNOWLEDGED",
    "RECONCILIATIONS_GENERATED",
    "JUDGEMENTS_REVIEWED",
    "DATA_QUALITY_CLEAR",
    "NO_DIRTY_GROUPS",
    "MANUAL_ADJUSTMENTS_CLEARED",
    "CONTROLLER_CERTIFIED",
)
TEMPLATE_GATE_CHECK = (
    "(gate_kind <> 'AUTOMATIC' OR gate_check_code IS NOT NULL) "
    f"AND (gate_check_code IS NULL OR gate_check_code IN ({_literals(GATE_CHECK_CODES)}))"
)
# 04 T-CLS-04 ``reason_code``: required for REOPEN, from the request-reopen subset of table 3.4-R.
LOCK_REASON_CHECK = (
    "kind <> 'REOPEN' OR (reason_code IS NOT NULL "
    "AND reason_code IN ('ERROR_CORRECTION', 'LATE_SOURCE_DATA', 'AUDIT_ADJUSTMENT', 'OTHER'))"
)
# 04 T-CLS-07 ``item_kind`` and T-CLS-08 ``subject_type``.
ITEM_KINDS = (
    "UNMATCHED_SOURCE",
    "UNMATCHED_SUBLEDGER",
    "AMOUNT_VARIANCE",
    "UNPOSTED_BATCH",
    "TIMING",
    "DIRECT_GL_ENTRY",
    "OTHER",
)
SIGNOFF_SUBJECT_TYPES = (
    "reconciliation",
    "close_checklist_item",
    "period_lock",
    "journal_run",
    "access_review_campaign",
)

# DB-03: erev_api.db.transitions.transition_trigger_sql(<table>) at CLO-2; DG-ARC-07 compares the
# installed functions with a fresh rendering.
CLOSE_RUN_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF OLD.status::text = ANY (ARRAY['SUCCEEDED']::text[]) THEN
    SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
      FROM jsonb_each(new_row) n
     WHERE n.key <> ALL (ARRAY['row_version', 'status', 'steps', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
       AND n.value IS DISTINCT FROM old_row -> n.key;
    IF changed IS NOT NULL THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change while status is %s',
                         changed, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status);
    END IF;
    IF jsonb_typeof(NEW.steps) IS DISTINCT FROM 'array' THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: steps of %I.%I must stay an array',
                         TG_TABLE_SCHEMA, TG_TABLE_NAME);
    END IF;
    IF jsonb_array_length(NEW.steps) <> jsonb_array_length(OLD.steps)
       OR EXISTS (
         SELECT 1
           FROM jsonb_array_elements(OLD.steps) WITH ORDINALITY o(item, ordinal)
           JOIN jsonb_array_elements(NEW.steps) WITH ORDINALITY n(item, ordinal)
             USING (ordinal)
          WHERE o.item IS DISTINCT FROM n.item
            AND NOT (o.item ->> 'step_code' = 'LOCK' AND n.item ->> 'step_code' = 'LOCK')) THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: steps of %I.%I change only in element LOCK while status is %s',
                         TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status);
    END IF;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['counts', 'current_step_code', 'finished_at', 'row_version', 'started_at', 'status', 'steps', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.started_at IS NOT NULL AND NEW.started_at IS DISTINCT FROM OLD.started_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: started_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['BLOCKED>RUNNING', 'FAILED>RUNNING', 'PENDING>RUNNING', 'RUNNING>BLOCKED', 'RUNNING>CANCELLED', 'RUNNING>FAILED', 'RUNNING>SUCCEEDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

CLOSE_CHECKLIST_ITEM_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['comment', 'control_execution_id', 'due_date', 'owner_membership_id', 'result', 'row_version', 'signoff_id', 'status', 'updated_at', 'updated_by', 'updated_by_kind', 'waiver_approval_request_id']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['FAILED>IN_PROGRESS', 'FAILED>PASSED', 'FAILED>WAIVED', 'IN_PROGRESS>FAILED', 'IN_PROGRESS>NOT_APPLICABLE', 'IN_PROGRESS>PASSED', 'IN_PROGRESS>WAIVED', 'NOT_STARTED>FAILED', 'NOT_STARTED>IN_PROGRESS', 'NOT_STARTED>NOT_APPLICABLE', 'NOT_STARTED>PASSED', 'NOT_STARTED>WAIVED', 'PASSED>FAILED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

RECONCILIATION_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF OLD.status::text = ANY (ARRAY['CERTIFIED']::text[]) THEN
    SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
      FROM jsonb_each(new_row) n
     WHERE n.key <> ALL (ARRAY['row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
       AND n.value IS DISTINCT FROM old_row -> n.key;
    IF changed IS NOT NULL THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change while status is %s',
                         changed, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status);
    END IF;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['certified_at', 'report_run_id', 'row_version', 'status', 'totals', 'unexplained_other_amount', 'updated_at', 'updated_by', 'updated_by_kind', 'variance_count']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['AUTO_CERTIFIED>CERTIFIED', 'CERTIFIED>REOPENED', 'DRAFT>AUTO_CERTIFIED', 'DRAFT>PREPARED', 'PREPARED>REOPENED', 'PREPARED>REVIEWED', 'REOPENED>DRAFT', 'REVIEWED>CERTIFIED', 'REVIEWED>REOPENED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

RECONCILIATION_ITEM_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
  parent_status text;
BEGIN
  SELECT p.status::text INTO parent_status
    FROM erev.reconciliation p
   WHERE p.tenant_id = OLD.tenant_id AND p.id = OLD.reconciliation_id;
  IF parent_status IS NULL OR parent_status = ANY (ARRAY['CERTIFIED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: %I.%I cannot change while its reconciliation is %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME,
                       coalesce(parent_status, 'not visible'));
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['explanation', 'resolved_at', 'resolved_by', 'resolved_by_kind', 'row_version', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# 04 T-CLS-02 class IM-M: a system row changes only in owner_role_id, due_offset_days and SC-M and
# is never deleted; a tenant-defined row never becomes a system row.
TEMPLATE_SYSTEM_BODY = """
DECLARE
  changed text;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.is_system THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: system row %s of %I.%I cannot be deleted',
                         OLD.code, TG_TABLE_SCHEMA, TG_TABLE_NAME);
    END IF;
    RETURN OLD;
  END IF;
  IF NOT OLD.is_system THEN
    IF NEW.is_system THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: row %s of %I.%I cannot become a system row',
                         OLD.code, TG_TABLE_SCHEMA, TG_TABLE_NAME);
    END IF;
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(to_jsonb(NEW)) n
   WHERE n.key <> ALL (ARRAY['due_offset_days', 'owner_role_id', 'row_version', 'updated_at',
                             'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM to_jsonb(OLD) -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of system row %s of %I.%I cannot change',
                       changed, OLD.code, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""

# DB-10: a REVIEWER or CONTROLLER signer differs from every PREPARER signer of the subject,
# whichever of the two signs first. The transaction-level advisory lock on the subject serialises
# its signers.
SIGNOFF_SEPARATION_BODY = """
DECLARE
  other_role text;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id() THEN
    RETURN NEW;
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(
    'erev.signoff:' || NEW.tenant_id::text || ':' || NEW.subject_type || ':'
    || NEW.subject_id::text, 0));
  SELECT s.role::text INTO other_role
    FROM erev.signoff s
   WHERE s.tenant_id = NEW.tenant_id AND s.subject_type = NEW.subject_type
     AND s.subject_id = NEW.subject_id AND s.signer_id = NEW.signer_id
     AND (s.role::text = 'PREPARER') <> (NEW.role::text = 'PREPARER')
   ORDER BY s.role::text
   LIMIT 1;
  IF other_role IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-APR-001: signer %s of the %s sign-off of %s %s signed it as %s',
                       NEW.signer_id, NEW.role, NEW.subject_type, NEW.subject_id, other_role);
  END IF;
  RETURN NEW;
END
"""

# The lock names its transition, and the transition names the lock (04 T-REF-07 ``period_lock_id``),
# so one of the two keys is checked at commit.
LOCK_TRANSITION_FK = (
    "ALTER TABLE erev.period_lock ADD CONSTRAINT fk_period_lock__period_state_transition "
    "FOREIGN KEY (tenant_id, period_state_transition_id) REFERENCES erev.period_state_transition "
    "(tenant_id, id) ON DELETE RESTRICT ON UPDATE RESTRICT DEFERRABLE INITIALLY DEFERRED"
)
# Keys of earlier tables to the tables of this revision (DG-MIG-03), dropped first on downgrade.
INBOUND_KEYS: tuple[tuple[str, str, str], ...] = (
    ("period_state_transition", "close_run_id", "close_run"),
    ("contract_computation", "close_run_id", "close_run"),
    ("subledger_posting", "close_run_id", "close_run"),
    ("journal_run", "close_run_id", "close_run"),
    ("exception_item", "close_run_id", "close_run"),
    ("period_state", "current_lock_id", "period_lock"),
    ("period_state_transition", "period_lock_id", "period_lock"),
)


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _text(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Text(), nullable=nullable)


def _named(
    name: str, type_name: str, *, nullable: bool, default: str | None = None
) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(
        name, ops.NamedType(type_name), nullable=nullable, server_default=server_default
    )


def _integer(name: str, *, nullable: bool, default: str | None = None) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(name, sa.Integer(), nullable=nullable, server_default=server_default)


def _bigint(name: str) -> sa.Column[Any]:
    return sa.Column(name, sa.BigInteger(), nullable=False)


def _instant(name: str, *, nullable: bool = True, now_default: bool = False) -> sa.Column[Any]:
    server_default = sa.text("now()") if now_default else None
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=nullable, server_default=server_default
    )


def _flag(name: str, *, default: str) -> sa.Column[Any]:
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text(default))


def _create_close_run() -> None:
    table = "close_run"
    ops.create_tenant_table(
        table,
        _text("close_run_no", nullable=False),
        _uuid("entity_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _uuid("period_id", nullable=False),
        _named("status", "erev.close_run_status", nullable=False, default="'PENDING'"),
        _instant("cutoff_known_at", nullable=False),
        _text("current_step_code"),
        _named("steps", "jsonb", nullable=False),
        _named("counts", "jsonb", nullable=False, default="'{}'::jsonb"),
        _uuid("job_id"),
        _instant("started_at"),
        _instant("finished_at"),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_close_run__steps", "jsonb_typeof(steps) = 'array'"),
            ("ck_close_run__counts", "jsonb_typeof(counts) = 'object'"),
            (
                "ck_close_run__current_step_code",
                f"current_step_code IS NULL OR current_step_code IN ({_literals(STEP_CODES)})",
            ),
        ],
        unique=[
            ("ux_close_run__no", ["tenant_id", "close_run_no"], None),
            (
                "ux_close_run__active",
                ["tenant_id", "entity_id", "book_code", "period_id"],
                "status IN ('PENDING', 'RUNNING', 'BLOCKED')",
            ),
        ],
    )
    ops.add_tenant_fk(table, "entity_id", "legal_entity")
    ops.add_tenant_fk(table, "period_id", "period")
    ops.add_tenant_fk(table, "job_id", "job")
    ops.apply_class(table, "IM-S", update_columns=CLOSE_RUN_UPDATE_COLUMNS)
    ops.enable_rls(table, "RLS-TE", entity_column="entity_id")
    ops.create_trigger(
        table, "transition", CLOSE_RUN_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )


def _create_close_checklist_template() -> None:
    table = "close_checklist_template"
    ops.create_tenant_table(
        table,
        _named("code", "erev.code", nullable=False),
        _named("name", "erev.label", nullable=False),
        _named("description", "erev.memo", nullable=True),
        _named("gate_kind", "erev.checklist_gate_kind", nullable=False),
        _text("gate_check_code"),
        _flag("is_blocking", default="true"),
        _flag("is_system", default="false"),
        _uuid("owner_role_id"),
        _integer("due_offset_days", nullable=True),
        _integer("sequence", nullable=False),
        _flag("is_active", default="true"),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_close_checklist_template__gate_check_code", TEMPLATE_GATE_CHECK),
            (
                "ck_close_checklist_template__due_offset_days",
                "due_offset_days IS NULL OR due_offset_days >= 0",
            ),
        ],
        unique=[("ux_close_checklist_template__code", ["tenant_id", "code"], None)],
    )
    ops.add_tenant_fk(table, "owner_role_id", "role")
    ops.apply_class(table, "IM-M")
    ops.enable_rls(table, "RLS-T")
    ops.create_trigger(
        table, "system", TEMPLATE_SYSTEM_BODY, timing="BEFORE", events="UPDATE OR DELETE"
    )


def _create_period_lock() -> None:
    table = "period_lock"
    ops.create_tenant_table(
        table,
        _named("kind", "erev.lock_kind", nullable=False),
        _uuid("entity_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _uuid("period_id", nullable=False),
        _uuid("period_state_transition_id", nullable=False),
        _uuid("approval_request_id", nullable=False),
        _named("reason_code", "erev.reason_code", nullable=True),
        _named("comment", "erev.memo", nullable=True),
        _named("certification", "jsonb", nullable=False),
        _bigint("ledger_head_chain_seq"),
        _named("ledger_head_sha256", "erev.sha256", nullable=True),
        _bigint("audit_head_chain_seq"),
        _named("audit_head_hmac", "erev.sha256", nullable=True),
        _named("snapshot_manifest_sha256", "erev.sha256", nullable=True),
        _uuid("previous_lock_id"),
        _uuid("diff_report_file_id"),
        standard_sets=["SC-C"],
        checks=[
            ("ck_period_lock__reason_code", LOCK_REASON_CHECK),
            (
                "ck_period_lock__chain_seq",
                "ledger_head_chain_seq >= 0 AND audit_head_chain_seq >= 0",
            ),
        ],
        indexes=[
            (
                "ix_period_lock__period",
                ["tenant_id", "entity_id", "book_code", "period_id", "created_at"],
                None,
            )
        ],
    )
    ops.add_tenant_fk(table, "entity_id", "legal_entity")
    ops.add_tenant_fk(table, "period_id", "period")
    ops.execute(LOCK_TRANSITION_FK)
    ops.add_tenant_fk(table, "approval_request_id", "approval_request")
    ops.add_tenant_fk(table, "previous_lock_id", table)
    ops.add_tenant_fk(table, "diff_report_file_id", "file_object")
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-TE", entity_column="entity_id")


def _create_lock_snapshot() -> None:
    table = "lock_snapshot"
    ops.create_tenant_table(
        table,
        _uuid("period_lock_id", nullable=False),
        _named("snapshot_kind", "erev.snapshot_kind", nullable=False),
        _uuid("report_run_id"),
        _uuid("file_id", nullable=False),
        _named("file_sha256", "erev.sha256", nullable=False),
        _bigint("row_count"),
        _named("control_totals", "jsonb", nullable=False),
        standard_sets=["SC-C"],
        checks=[("ck_lock_snapshot__row_count", "row_count >= 0")],
        unique=[("ux_lock_snapshot__kind", ["tenant_id", "period_lock_id", "snapshot_kind"], None)],
    )
    ops.add_tenant_fk(table, "period_lock_id", "period_lock")
    ops.add_tenant_fk(table, "file_id", "file_object")
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-T")


def _create_reconciliation() -> None:
    table = "reconciliation"
    ops.create_tenant_table(
        table,
        _text("reconciliation_no", nullable=False),
        _named("kind", "erev.reconciliation_kind", nullable=False),
        _uuid("entity_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _uuid("period_id", nullable=False),
        _named("status", "erev.reconciliation_status", nullable=False, default="'DRAFT'"),
        _instant("as_of_known_at", nullable=False),
        _uuid("period_lock_id"),
        _uuid("source_file_id"),
        _uuid("sync_run_id"),
        _named("totals", "jsonb", nullable=False, default="'{}'::jsonb"),
        _integer("variance_count", nullable=False, default="0"),
        _named("unexplained_other_amount", "erev.money", nullable=True),
        _uuid("auto_certify_rule_set_version_id"),
        _uuid("auto_certify_rule_id"),
        _uuid("report_run_id"),
        _instant("certified_at"),
        standard_sets=["SC-C", "SC-M"],
        checks=[("ck_reconciliation__variance_count", "variance_count >= 0")],
        unique=[("ux_reconciliation__no", ["tenant_id", "reconciliation_no"], None)],
        indexes=[
            (
                "ix_reconciliation__period",
                ["tenant_id", "entity_id", "book_code", "period_id", "kind"],
                None,
            )
        ],
    )
    ops.add_tenant_fk(table, "entity_id", "legal_entity")
    ops.add_tenant_fk(table, "period_id", "period")
    ops.add_tenant_fk(table, "period_lock_id", "period_lock")
    ops.add_tenant_fk(table, "source_file_id", "file_object")
    ops.add_tenant_fk(table, "auto_certify_rule_set_version_id", "rule_set_version")
    ops.add_tenant_fk(table, "auto_certify_rule_id", "rule")
    ops.apply_class(table, "IM-S", update_columns=RECONCILIATION_UPDATE_COLUMNS)
    ops.enable_rls(table, "RLS-TE", entity_column="entity_id")
    ops.create_trigger(
        table, "transition", RECONCILIATION_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )


def _create_reconciliation_item() -> None:
    table = "reconciliation_item"
    ops.create_tenant_table(
        table,
        _uuid("reconciliation_id", nullable=False),
        _text("item_kind", nullable=False),
        _text("account_code"),
        _uuid("contract_id"),
        _text("invoice_number"),
        _named("subledger_amount", "erev.money", nullable=True),
        _named("source_amount", "erev.money", nullable=True),
        _named("difference", "erev.money", nullable=False),
        _named("currency", "erev.currency_code", nullable=False),
        _flag("is_high_risk", default="false"),
        _text("gl_document_reference"),
        _named("explanation", "erev.memo", nullable=True),
        _instant("resolved_at"),
        _uuid("resolved_by"),
        _named("resolved_by_kind", "erev.principal_kind", nullable=True),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_reconciliation_item__item_kind", f"item_kind IN ({_literals(ITEM_KINDS)})"),
            ("ck_reconciliation_item__high_risk", "item_kind <> 'DIRECT_GL_ENTRY' OR is_high_risk"),
        ],
        indexes=[("ix_reconciliation_item__recon", ["tenant_id", "reconciliation_id"], None)],
    )
    ops.add_tenant_fk(table, "reconciliation_id", "reconciliation")
    ops.add_tenant_fk(table, "contract_id", "contract")
    ops.add_global_fk(table, "currency", "currency", target_column="code")
    ops.apply_class(table, "IM-S", update_columns=RECONCILIATION_ITEM_UPDATE_COLUMNS)
    ops.enable_rls(table, "RLS-T")
    ops.create_trigger(
        table, "transition", RECONCILIATION_ITEM_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )


def _create_signoff() -> None:
    table = "signoff"
    ops.create_tenant_table(
        table,
        _text("subject_type", nullable=False),
        _uuid("subject_id", nullable=False),
        _named("role", "erev.signoff_role", nullable=False),
        _uuid("signer_id", nullable=False),
        _text("statement", nullable=False),
        _named("subject_content_sha256", "erev.sha256", nullable=False),
        _instant("mfa_verified_at", nullable=False),
        _instant("signed_at", nullable=False, now_default=True),
        checks=[
            (
                "ck_signoff__subject_type",
                f"subject_type IN ({_literals(SIGNOFF_SUBJECT_TYPES)})",
            )
        ],
        unique=[
            (
                "ux_signoff__signer",
                ["tenant_id", "subject_type", "subject_id", "role", "signer_id"],
                None,
            )
        ],
    )
    ops.add_global_fk(table, "signer_id", "app_user")
    ops.apply_class(table, "IM-A")
    ops.enable_rls(table, "RLS-T")
    ops.create_trigger(
        table, "separation", SIGNOFF_SEPARATION_BODY, timing="BEFORE", events="INSERT"
    )


def _create_close_checklist_item() -> None:
    table = "close_checklist_item"
    ops.create_tenant_table(
        table,
        _uuid("close_checklist_template_id", nullable=False),
        _uuid("entity_id", nullable=False),
        _named("book_code", "erev.book_code", nullable=False),
        _uuid("period_id", nullable=False),
        _named("status", "erev.checklist_status", nullable=False, default="'NOT_STARTED'"),
        _uuid("owner_membership_id"),
        sa.Column("due_date", sa.Date(), nullable=True),
        _named("result", "jsonb", nullable=True),
        _uuid("control_execution_id"),
        _uuid("signoff_id"),
        _uuid("waiver_approval_request_id"),
        _named("comment", "erev.memo", nullable=True),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            (
                "ck_close_checklist_item__waiver",
                "status <> 'WAIVED' OR waiver_approval_request_id IS NOT NULL",
            )
        ],
        unique=[
            (
                "ux_close_checklist_item__period",
                ["tenant_id", "close_checklist_template_id", "entity_id", "book_code", "period_id"],
                None,
            )
        ],
    )
    ops.add_tenant_fk(table, "close_checklist_template_id", "close_checklist_template")
    ops.add_tenant_fk(table, "entity_id", "legal_entity")
    ops.add_tenant_fk(table, "period_id", "period")
    ops.add_tenant_fk(table, "owner_membership_id", "tenant_membership")
    ops.add_tenant_fk(table, "signoff_id", "signoff")
    ops.add_tenant_fk(table, "waiver_approval_request_id", "approval_request")
    ops.apply_class(table, "IM-M")
    ops.enable_rls(table, "RLS-TE", entity_column="entity_id")
    ops.create_trigger(
        table, "transition", CLOSE_CHECKLIST_ITEM_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    for name, values in ENUMS:
        ops.create_enum(name, values)
    _create_close_run()
    _create_close_checklist_template()
    _create_period_lock()
    _create_lock_snapshot()
    _create_reconciliation()
    _create_reconciliation_item()
    _create_signoff()
    _create_close_checklist_item()
    for table, column, target in INBOUND_KEYS:
        ops.add_tenant_fk(table, column, target)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    for table, column, target in reversed(INBOUND_KEYS):
        stem = column.removesuffix("_id")
        suffix = target if stem == target else stem
        ops.execute(f"ALTER TABLE erev.{table} DROP CONSTRAINT fk_{table}__{suffix}")
    for table in (
        "close_checklist_item",
        "signoff",
        "reconciliation_item",
        "reconciliation",
        "lock_snapshot",
        "period_lock",
        "close_checklist_template",
        "close_run",
    ):
        ops.drop_tenant_table(table)
    for name, _ in reversed(ENUMS):
        ops.drop_enum(name)
