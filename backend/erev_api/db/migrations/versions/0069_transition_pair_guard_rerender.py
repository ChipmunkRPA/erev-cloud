"""D-98 candidate 143 GUARD-TRN-1 (dev-guide 1.62 DG-KRN-DB-09; 04 rev 1.70 §1.5 IM-S note):
re-render the six installed DB-03 transition functions whose spec has an editable status.

The renderer (``erev_api.db.transitions.render_trigger_body``) now emits the status-pair guard
BEFORE the ``editable_while`` early-return, so a DRAFT row may change any column but may still move
only along a listed pair at the database layer; ``editable_while`` relaxes only the column freeze.
This revision replaces the bodies of ``tg_contract__transition`` (0038, body 0042),
``tg_estimate_version__transition`` (0051), ``tg_event_submission__transition`` (0038),
``tg_judgement_record__transition`` (0042), ``tg_manual_adjustment__transition`` (0046) and
``tg_policy_override__transition`` (0045) with ``CREATE OR REPLACE FUNCTION`` (the 0065 precedent:
grants and triggers are kept), so DG-ARC-07 (installed source == fresh rendering) holds; the
seventh editable spec, ``modification``, is created by 0068 with the regenerated literal. The
downgrade restores the six previous literals verbatim. No table, column, type or function is
added (the erev function count is unchanged). A revision imports nothing of ``erev_api`` beyond
the DDL helpers (DG-MIG-12): every body is a literal.
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None

TABLES: Final = (
    "contract",
    "estimate_version",
    "event_submission",
    "judgement_record",
    "manual_adjustment",
    "policy_override",
)

BODY_CONTRACT = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['ACTIVE>COMPLETED', 'ACTIVE>TERMINATED', 'ACTIVE>VOIDED', 'COMPLETED>ACTIVE', 'COMPLETED>VOIDED', 'DRAFT>NOT_A_CONTRACT', 'DRAFT>PENDING_REVIEW', 'DRAFT>VOIDED', 'NOT_A_CONTRACT>PENDING_REVIEW', 'NOT_A_CONTRACT>VOIDED', 'PENDING_REVIEW>ACTIVE', 'PENDING_REVIEW>DRAFT', 'PENDING_REVIEW>VOIDED', 'TERMINATED>VOIDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['activated_at', 'activation_checklist', 'combination_group_id', 'completed_at', 'custom_attributes', 'head_stream_version', 'latest_computation_id', 'memo_1', 'memo_2', 'memo_3', 'row_version', 'scope_605_35', 'status', 'terminated_at', 'updated_at', 'updated_by', 'updated_by_kind', 'voided_at']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

BODY_ESTIMATE_VERSION = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>SUPERSEDED', 'DRAFT>SUBMITTED', 'REJECTED>DRAFT', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'SUBMITTED>WITHDRAWN', 'WITHDRAWN>DRAFT']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['applied_event_ids', 'approval_request_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

BODY_EVENT_SUBMISSION = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>APPLIED', 'DRAFT>SUBMITTED', 'DRAFT>VOIDED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'SUBMITTED>VOIDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['applied_event_ids', 'approval_request_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

BODY_JUDGEMENT_RECORD = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['DRAFT>SUBMITTED', 'REJECTED>DRAFT', 'REVIEWED>SUPERSEDED', 'SUBMITTED>REJECTED', 'SUBMITTED>REVIEWED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'reviewed_at', 'reviewer_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.reviewed_at IS NOT NULL AND NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: reviewed_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.reviewer_id IS NOT NULL AND NEW.reviewer_id IS DISTINCT FROM OLD.reviewer_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: reviewer_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

BODY_MANUAL_ADJUSTMENT = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>POSTED', 'DRAFT>SUBMITTED', 'POSTED>VOIDED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
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
  RETURN NEW;
END
"""  # noqa: E501

BODY_POLICY_OVERRIDE = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>SUPERSEDED', 'DRAFT>SUBMITTED', 'REJECTED>DRAFT', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'SUBMITTED>WITHDRAWN', 'WITHDRAWN>DRAFT']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'approved_at', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.approved_at IS NOT NULL AND NEW.approved_at IS DISTINCT FROM OLD.approved_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: approved_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

PREVIOUS_CONTRACT = """
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
   WHERE n.key <> ALL (ARRAY['activated_at', 'activation_checklist', 'combination_group_id', 'completed_at', 'custom_attributes', 'head_stream_version', 'latest_computation_id', 'memo_1', 'memo_2', 'memo_3', 'row_version', 'scope_605_35', 'status', 'terminated_at', 'updated_at', 'updated_by', 'updated_by_kind', 'voided_at']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['ACTIVE>COMPLETED', 'ACTIVE>TERMINATED', 'ACTIVE>VOIDED', 'COMPLETED>ACTIVE', 'COMPLETED>VOIDED', 'DRAFT>NOT_A_CONTRACT', 'DRAFT>PENDING_REVIEW', 'DRAFT>VOIDED', 'NOT_A_CONTRACT>PENDING_REVIEW', 'NOT_A_CONTRACT>VOIDED', 'PENDING_REVIEW>ACTIVE', 'PENDING_REVIEW>DRAFT', 'PENDING_REVIEW>VOIDED', 'TERMINATED>VOIDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

PREVIOUS_ESTIMATE_VERSION = """
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
   WHERE n.key <> ALL (ARRAY['applied_event_ids', 'approval_request_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>SUPERSEDED', 'DRAFT>SUBMITTED', 'REJECTED>DRAFT', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'SUBMITTED>WITHDRAWN', 'WITHDRAWN>DRAFT']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

PREVIOUS_EVENT_SUBMISSION = """
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
   WHERE n.key <> ALL (ARRAY['applied_event_ids', 'approval_request_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>APPLIED', 'DRAFT>SUBMITTED', 'DRAFT>VOIDED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'SUBMITTED>VOIDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

PREVIOUS_JUDGEMENT_RECORD = """
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
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'reviewed_at', 'reviewer_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.reviewed_at IS NOT NULL AND NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: reviewed_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.reviewer_id IS NOT NULL AND NEW.reviewer_id IS DISTINCT FROM OLD.reviewer_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: reviewer_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['DRAFT>SUBMITTED', 'REJECTED>DRAFT', 'REVIEWED>SUPERSEDED', 'SUBMITTED>REJECTED', 'SUBMITTED>REVIEWED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

PREVIOUS_MANUAL_ADJUSTMENT = """
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

PREVIOUS_POLICY_OVERRIDE = """
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
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'approved_at', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.approved_at IS NOT NULL AND NEW.approved_at IS DISTINCT FROM OLD.approved_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: approved_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>SUPERSEDED', 'DRAFT>SUBMITTED', 'REJECTED>DRAFT', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'SUBMITTED>WITHDRAWN', 'WITHDRAWN>DRAFT']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

BODIES: Final = {
    "contract": BODY_CONTRACT,
    "estimate_version": BODY_ESTIMATE_VERSION,
    "event_submission": BODY_EVENT_SUBMISSION,
    "judgement_record": BODY_JUDGEMENT_RECORD,
    "manual_adjustment": BODY_MANUAL_ADJUSTMENT,
    "policy_override": BODY_POLICY_OVERRIDE,
}
PREVIOUS: Final = {
    "contract": PREVIOUS_CONTRACT,
    "estimate_version": PREVIOUS_ESTIMATE_VERSION,
    "event_submission": PREVIOUS_EVENT_SUBMISSION,
    "judgement_record": PREVIOUS_JUDGEMENT_RECORD,
    "manual_adjustment": PREVIOUS_MANUAL_ADJUSTMENT,
    "policy_override": PREVIOUS_POLICY_OVERRIDE,
}


def _replace_function(table: str, body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes)."""
    if "$fn$" in body:
        raise ValueError("a trigger function body must not contain $fn$")
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.tg_{table}__transition() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    for table in TABLES:
        _replace_function(table, BODIES[table])


def downgrade() -> None:
    """Restore exactly the six previous bodies, verbatim (DG-MIG-04)."""
    for table in TABLES:
        _replace_function(table, PREVIOUS[table])
