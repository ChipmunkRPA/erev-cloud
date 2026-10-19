"""Retain a write-once manifest for the initial upgrade processing queue."""

from erev_api.db import migration_ops as ops

revision = "0167"
down_revision = "0166"
branch_labels = None
depends_on = None

BEFORE = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['accepted_attempt_id', 'enabled_at', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.accepted_attempt_id IS NOT NULL AND NEW.accepted_attempt_id IS DISTINCT FROM OLD.accepted_attempt_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: accepted_attempt_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.enabled_at IS NOT NULL AND NEW.enabled_at IS DISTINCT FROM OLD.enabled_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: enabled_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['INCOMPLETE>RUNNING', 'PENDING>RUNNING', 'PENDING_APPROVAL>APPROVED', 'PENDING_APPROVAL>REJECTED', 'RUNNING>FAILED', 'RUNNING>INCOMPLETE', 'RUNNING>PASSED', 'RUNNING>PENDING_APPROVAL']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
AFTER = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['processing_seed', 'accepted_attempt_id', 'enabled_at', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.accepted_attempt_id IS NOT NULL AND NEW.accepted_attempt_id IS DISTINCT FROM OLD.accepted_attempt_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: accepted_attempt_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.enabled_at IS NOT NULL AND NEW.enabled_at IS DISTINCT FROM OLD.enabled_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: enabled_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['INCOMPLETE>RUNNING', 'PENDING>RUNNING', 'PENDING_APPROVAL>APPROVED', 'PENDING_APPROVAL>REJECTED', 'RUNNING>FAILED', 'RUNNING>INCOMPLETE', 'RUNNING>PASSED', 'RUNNING>PENDING_APPROVAL']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.processing_seed IS NOT NULL AND NEW.processing_seed IS DISTINCT FROM OLD.processing_seed THEN
    RAISE EXCEPTION 'Processing seed is already set' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


PROCESSING_BEFORE = """
DECLARE
  previous erev.release_group_processing;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM erev.release_validation v
    WHERE v.tenant_id = NEW.tenant_id AND v.id = NEW.release_validation_id
      AND v.accepted_attempt_id = NEW.release_validation_attempt_id
      AND v.effective_level IN ('MINOR', 'MAJOR')
      AND v.status IN ('PASSED', 'APPROVED') AND v.enabled_at IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'Processing requires the accepted attempt of an enabled upgrade'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.seq = 1 AND (NOT EXISTS (
    SELECT 1 FROM erev.book b WHERE b.tenant_id = NEW.tenant_id
      AND b.code = NEW.book_code AND b.is_enabled
  ) OR NOT EXISTS (
    SELECT 1 FROM erev.combination_group_member m JOIN erev.contract c
      ON c.tenant_id = m.tenant_id AND c.id = m.contract_id
    WHERE m.tenant_id = NEW.tenant_id AND m.combination_group_id = NEW.combination_group_id
      AND m.valid_to_known_at IS NULL AND c.contracting_entity_id = NEW.entity_id
  )) THEN
    RAISE EXCEPTION 'Initial processing portion is not a current member and enabled book'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.contract_computation_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM erev.contract_computation c JOIN erev.release_validation v
      ON v.tenant_id = c.tenant_id AND v.engine_release_id = c.engine_release_id
    WHERE c.tenant_id = NEW.tenant_id AND c.id = NEW.contract_computation_id
      AND c.combination_group_id = NEW.combination_group_id AND v.id = NEW.release_validation_id
  ) THEN
    RAISE EXCEPTION 'Processing computation does not belong to this group and release'
      USING ERRCODE = '23514';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(NEW.subledger_posting_ids) AS requested(posting_id)
    WHERE NOT EXISTS (
      SELECT 1 FROM erev.subledger_posting p
      JOIN erev.contract_computation c
        ON c.tenant_id = p.tenant_id AND c.id = p.contract_computation_id
      JOIN erev.release_validation v
        ON v.tenant_id = c.tenant_id AND v.engine_release_id = c.engine_release_id
      WHERE p.tenant_id = NEW.tenant_id AND p.id = requested.posting_id
        AND p.combination_group_id = NEW.combination_group_id AND p.book_code = NEW.book_code
        AND v.id = NEW.release_validation_id AND EXISTS (
          SELECT 1 FROM erev.subledger_line l WHERE l.tenant_id = p.tenant_id
            AND l.subledger_posting_id = p.id AND l.entity_id = NEW.entity_id
        )
    )
  ) THEN
    RAISE EXCEPTION 'Processing posting does not belong to this portion and release'
      USING ERRCODE = '23514';
  END IF;
  IF NOT pg_try_advisory_xact_lock(hashtextextended(
    'erev:upgrade-portion:' || NEW.tenant_id::text || ':' || NEW.release_validation_id::text
    || ':' || NEW.combination_group_id::text || ':' || NEW.entity_id::text
    || ':' || NEW.book_code::text, 0)) THEN
    RAISE EXCEPTION 'Another transaction is updating this upgrade portion' USING ERRCODE = '55P03';
  END IF;
  SELECT * INTO previous FROM erev.release_group_processing p
   WHERE p.tenant_id = NEW.tenant_id AND p.release_validation_id = NEW.release_validation_id
     AND p.combination_group_id = NEW.combination_group_id AND p.entity_id = NEW.entity_id
     AND p.book_code = NEW.book_code ORDER BY p.seq DESC LIMIT 1;
  IF (previous.id IS NULL AND NEW.seq <> 1)
     OR (previous.id IS NOT NULL AND (NEW.seq <> previous.seq + 1
         OR previous.upgrade_state NOT IN ('PENDING', 'DEFERRED_NO_OPEN_PERIOD')
         OR NOT previous.subledger_posting_ids <@ NEW.subledger_posting_ids)) THEN
    RAISE EXCEPTION 'Invalid upgrade portion event sequence' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
"""

PROCESSING_AFTER = """
DECLARE
  previous erev.release_group_processing;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM erev.release_validation v
    WHERE v.tenant_id = NEW.tenant_id AND v.id = NEW.release_validation_id
      AND v.accepted_attempt_id = NEW.release_validation_attempt_id
      AND v.effective_level IN ('MINOR', 'MAJOR')
      AND v.status IN ('PASSED', 'APPROVED') AND v.enabled_at IS NOT NULL
      AND (NEW.seq <> 1 OR v.processing_seed IS NULL)
  ) THEN
    RAISE EXCEPTION 'Processing requires the accepted attempt of an enabled upgrade'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.seq = 1 AND (NOT EXISTS (
    SELECT 1 FROM erev.book b WHERE b.tenant_id = NEW.tenant_id
      AND b.code = NEW.book_code AND b.is_enabled
  ) OR NOT EXISTS (
    SELECT 1 FROM erev.combination_group_member m JOIN erev.contract c
      ON c.tenant_id = m.tenant_id AND c.id = m.contract_id
    WHERE m.tenant_id = NEW.tenant_id AND m.combination_group_id = NEW.combination_group_id
      AND m.valid_to_known_at IS NULL AND c.contracting_entity_id = NEW.entity_id
  )) THEN
    RAISE EXCEPTION 'Initial processing portion is not a current member and enabled book'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.contract_computation_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM erev.contract_computation c JOIN erev.release_validation v
      ON v.tenant_id = c.tenant_id AND v.engine_release_id = c.engine_release_id
    WHERE c.tenant_id = NEW.tenant_id AND c.id = NEW.contract_computation_id
      AND c.combination_group_id = NEW.combination_group_id AND v.id = NEW.release_validation_id
  ) THEN
    RAISE EXCEPTION 'Processing computation does not belong to this group and release'
      USING ERRCODE = '23514';
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(NEW.subledger_posting_ids) AS requested(posting_id)
    WHERE NOT EXISTS (
      SELECT 1 FROM erev.subledger_posting p
      JOIN erev.contract_computation c
        ON c.tenant_id = p.tenant_id AND c.id = p.contract_computation_id
      JOIN erev.release_validation v
        ON v.tenant_id = c.tenant_id AND v.engine_release_id = c.engine_release_id
      WHERE p.tenant_id = NEW.tenant_id AND p.id = requested.posting_id
        AND p.combination_group_id = NEW.combination_group_id AND p.book_code = NEW.book_code
        AND v.id = NEW.release_validation_id AND EXISTS (
          SELECT 1 FROM erev.subledger_line l WHERE l.tenant_id = p.tenant_id
            AND l.subledger_posting_id = p.id AND l.entity_id = NEW.entity_id
        )
    )
  ) THEN
    RAISE EXCEPTION 'Processing posting does not belong to this portion and release'
      USING ERRCODE = '23514';
  END IF;
  IF NOT pg_try_advisory_xact_lock(hashtextextended(
    'erev:upgrade-portion:' || NEW.tenant_id::text || ':' || NEW.release_validation_id::text
    || ':' || NEW.combination_group_id::text || ':' || NEW.entity_id::text
    || ':' || NEW.book_code::text, 0)) THEN
    RAISE EXCEPTION 'Another transaction is updating this upgrade portion' USING ERRCODE = '55P03';
  END IF;
  SELECT * INTO previous FROM erev.release_group_processing p
   WHERE p.tenant_id = NEW.tenant_id AND p.release_validation_id = NEW.release_validation_id
     AND p.combination_group_id = NEW.combination_group_id AND p.entity_id = NEW.entity_id
     AND p.book_code = NEW.book_code ORDER BY p.seq DESC LIMIT 1;
  IF (previous.id IS NULL AND NEW.seq <> 1)
     OR (previous.id IS NOT NULL AND (NEW.seq <> previous.seq + 1
         OR previous.upgrade_state NOT IN ('PENDING', 'DEFERRED_NO_OPEN_PERIOD')
         OR NOT previous.subledger_posting_ids <@ NEW.subledger_posting_ids)) THEN
    RAISE EXCEPTION 'Invalid upgrade portion event sequence' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
"""


def _replace(body: str, function: str = "tg_release_validation__transition") -> None:
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.{function}() "
        "RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER "
        "SET search_path = erev, pg_catalog AS $fn$" + body + "$fn$"
    )


def upgrade() -> None:
    ops.execute("ALTER TABLE erev.release_validation ADD COLUMN processing_seed jsonb")
    ops.execute(
        "ALTER TABLE erev.release_validation ADD CONSTRAINT ck_release_validation__processing_seed "
        "CHECK (processing_seed IS NULL OR (jsonb_typeof(processing_seed) = 'object' "
        "AND accepted_attempt_id IS NOT NULL AND enabled_at IS NOT NULL "
        "AND effective_level IN ('MINOR', 'MAJOR') AND status IN ('PASSED', 'APPROVED')))"
    )
    ops.execute("GRANT UPDATE (processing_seed) ON erev.release_validation TO erev_app")
    _replace(AFTER)
    _replace(PROCESSING_AFTER, "tg_release_group_processing__accepted_owner")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.release_validation ADD CONSTRAINT ck_release_validation__seed_empty "
        "CHECK (processing_seed IS NULL) NOT VALID"
    )
    ops.execute(
        "ALTER TABLE erev.release_validation VALIDATE CONSTRAINT ck_release_validation__seed_empty"
    )
    _replace(PROCESSING_BEFORE, "tg_release_group_processing__accepted_owner")
    _replace(BEFORE)
    ops.execute(
        "ALTER TABLE erev.release_validation DROP CONSTRAINT ck_release_validation__seed_empty"
    )
    ops.execute("ALTER TABLE erev.release_validation DROP COLUMN processing_seed")
