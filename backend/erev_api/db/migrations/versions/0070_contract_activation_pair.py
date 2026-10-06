"""D-98 candidate 143 AMENDMENT 1 (dev-guide 1.70 DG-KRN-DB-09; 04 rev 1.79 T-CON-01 status note /
§1.5 IM-S): the ``contract`` DB-03 spec gains the pair (DRAFT, ACTIVE) — the STORED form of the
SM-02 approved activation (L4-1-Q-18: the submit appends no event, so the stored status stays DRAFT
while the request is pending and the approved ``activate`` writes ACTIVE from DRAFT) and of the
SYSTEM activation (BS3-D-19 / L4-1-Q-11); ``events/stream._next_status`` already projects
CONTRACT_ACTIVATED from DRAFT or PENDING_REVIEW. Revision 0069 (GUARD-TRN-1) moved the pair guard
before the editable early-return, which exposed the omitted stored pair: every approved activation
and the legacy ``Contract Setup`` import COMMIT raised ``EREV-TRN-001: status of erev.contract
cannot change from DRAFT to ACTIVE`` on main 0959b560.

This revision replaces the body of ``tg_contract__transition`` (installed by 0038 / 0042,
re-rendered by 0069) with the fresh rendering (``CREATE OR REPLACE FUNCTION``; grants and triggers
kept — the 0065 / 0069 precedent), so DG-ARC-07 (installed source == fresh rendering) holds; the
downgrade restores the 0069 literal verbatim (DG-MIG-04). No table, column, type or function is
added (the erev function count is unchanged). A revision imports nothing of ``erev_api`` beyond the
DDL helpers (DG-MIG-12): both bodies are literals.
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None

TABLE: Final = "contract"

BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['ACTIVE>COMPLETED', 'ACTIVE>TERMINATED', 'ACTIVE>VOIDED', 'COMPLETED>ACTIVE', 'COMPLETED>VOIDED', 'DRAFT>ACTIVE', 'DRAFT>NOT_A_CONTRACT', 'DRAFT>PENDING_REVIEW', 'DRAFT>VOIDED', 'NOT_A_CONTRACT>PENDING_REVIEW', 'NOT_A_CONTRACT>VOIDED', 'PENDING_REVIEW>ACTIVE', 'PENDING_REVIEW>DRAFT', 'PENDING_REVIEW>VOIDED', 'TERMINATED>VOIDED']::text[]) THEN
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

PREVIOUS: Final = """
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


def _replace_function(body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes) — the
    0069 helper, verbatim in shape (SECURITY INVOKER, search_path pinned, $fn$ quoting)."""
    if "$fn$" in body:
        raise ValueError("a trigger function body must not contain $fn$")
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.tg_{TABLE}__transition() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    _replace_function(BODY)


def downgrade() -> None:
    """Restore exactly the 0069 body, verbatim (DG-MIG-04)."""
    _replace_function(PREVIOUS)
