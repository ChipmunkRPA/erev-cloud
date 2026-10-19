"""Retain immutable attribution for postings made during accepted upgrade processing."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops
from sqlalchemy.dialects.postgresql import JSONB

revision = "0168"
down_revision = "0167"
branch_labels = None
depends_on = None


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

PROCESSING_AFTER = """
DECLARE
  previous erev.release_group_processing;
BEGIN
  IF NOT pg_try_advisory_xact_lock(hashtextextended(
    'erev:upgrade-group:' || NEW.tenant_id::text || ':' || NEW.combination_group_id::text, 0)) THEN
    RAISE EXCEPTION 'Another transaction is processing this upgrade group' USING ERRCODE = '55P03';
  END IF;
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


def _processing_guard(body: str) -> None:
    ops.execute(
        "CREATE OR REPLACE FUNCTION erev.tg_release_group_processing__accepted_owner() "
        "RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER "
        "SET search_path = erev, pg_catalog AS $fn$" + body + "$fn$"
    )


def upgrade() -> None:
    _processing_guard(PROCESSING_AFTER)
    ops.create_tenant_table(
        "posting_attribution",
        sa.Column("subledger_posting_id", sa.Uuid(), nullable=False),
        sa.Column("release_validation_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("combination_group_id", sa.Uuid(), nullable=False),
        sa.Column("contract_computation_id", sa.Uuid(), nullable=False),
        sa.Column("previous_computation_id", sa.Uuid(), nullable=True),
        sa.Column("cause", ops.NamedType("erev.posting_attribution_cause"), nullable=False),
        sa.Column("sampled", sa.Boolean(), nullable=False),
        sa.Column("origin_periods", JSONB(), nullable=False),
        sa.Column("input_comparison", JSONB(), nullable=True),
        standard_sets=["SC-C"],
        primary_key=["tenant_id", "subledger_posting_id"],
        unique=[("ux_posting_attribution__id", ["tenant_id", "id"], None)],
        checks=[
            ("ck_posting_attribution__origin", "jsonb_typeof(origin_periods) = 'object'"),
            (
                "ck_posting_attribution__comparison",
                "input_comparison IS NULL OR jsonb_typeof(input_comparison) = 'object'",
            ),
            (
                "ck_posting_attribution__cause",
                """
                cause = 'UPGRADE_CONTEXT' OR (
                  previous_computation_id IS NOT NULL AND input_comparison IS NOT NULL
                  AND COALESCE(jsonb_typeof(
                    input_comparison->'previous_attribution_input_sha256') = 'string', false)
                  AND COALESCE(jsonb_typeof(
                    input_comparison->'current_attribution_input_sha256') = 'string', false)
                  AND COALESCE(
                    input_comparison->>'previous_attribution_input_sha256' ~ '^[0-9a-f]{64}$',
                    false)
                  AND COALESCE(
                    input_comparison->>'current_attribution_input_sha256' ~ '^[0-9a-f]{64}$', false)
                  AND ((cause = 'UPGRADE_ONLY') =
                    ((input_comparison->>'previous_attribution_input_sha256') =
                     (input_comparison->>'current_attribution_input_sha256')))
                )
            """,
            ),
        ],
    )
    for column, target in (
        ("subledger_posting_id", "subledger_posting"),
        ("release_validation_attempt_id", "release_validation_attempt"),
        ("combination_group_id", "combination_group"),
        ("contract_computation_id", "contract_computation"),
        ("previous_computation_id", "contract_computation"),
    ):
        ops.add_tenant_fk("posting_attribution", column, target)
    ops.apply_class("posting_attribution", "IM-A")
    ops.enable_rls("posting_attribution", "RLS-T")
    ops.create_trigger(
        "posting_attribution",
        "upgrade_owner",
        """
BEGIN
  IF NOT pg_try_advisory_xact_lock(hashtextextended(
    'erev:upgrade-group:' || NEW.tenant_id::text || ':' || NEW.combination_group_id::text, 0)) THEN
    RAISE EXCEPTION 'Another transaction is processing this upgrade group' USING ERRCODE = '55P03';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM erev.subledger_posting p
    JOIN erev.contract_computation c ON c.tenant_id = p.tenant_id
      AND c.id = p.contract_computation_id
    JOIN erev.release_validation v ON v.tenant_id = c.tenant_id
      AND v.engine_release_id = c.engine_release_id
    WHERE p.tenant_id = NEW.tenant_id AND p.id = NEW.subledger_posting_id
      AND p.contract_computation_id = NEW.contract_computation_id
      AND p.combination_group_id = NEW.combination_group_id
      AND c.combination_group_id = NEW.combination_group_id
      AND v.accepted_attempt_id = NEW.release_validation_attempt_id
      AND v.effective_level IN ('MINOR', 'MAJOR') AND v.status IN ('PASSED', 'APPROVED')
      AND v.enabled_at IS NOT NULL AND v.processing_seed IS NOT NULL
      AND EXISTS (
        SELECT 1 FROM erev.release_group_processing s
        WHERE s.tenant_id = v.tenant_id AND s.release_validation_id = v.id
          AND s.combination_group_id = NEW.combination_group_id
          AND s.upgrade_state IN ('PENDING', 'DEFERRED_NO_OPEN_PERIOD')
          AND NOT EXISTS (
            SELECT 1 FROM erev.release_group_processing later
            WHERE later.tenant_id = s.tenant_id
              AND later.release_validation_id = s.release_validation_id
              AND later.combination_group_id = s.combination_group_id
              AND later.entity_id = s.entity_id AND later.book_code = s.book_code
              AND later.seq > s.seq
          )
      )
  ) THEN
    RAISE EXCEPTION 'Attribution requires an accepted unsettled upgrade and matching computation'
      USING ERRCODE = '23514';
  END IF;
  IF NEW.previous_computation_id IS NOT NULL AND (
    NEW.previous_computation_id = NEW.contract_computation_id OR NOT EXISTS (
      SELECT 1 FROM erev.contract_computation c WHERE c.tenant_id = NEW.tenant_id
        AND c.id = NEW.previous_computation_id AND c.combination_group_id = NEW.combination_group_id
    )
  ) THEN
    RAISE EXCEPTION 'Previous computation must be a different computation of the same group'
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
""",
        timing="BEFORE",
        events="INSERT",
    )


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.posting_attribution ADD CONSTRAINT "
        "ck_posting_attribution__empty CHECK (false) NOT VALID"
    )
    ops.execute(
        "ALTER TABLE erev.posting_attribution VALIDATE CONSTRAINT ck_posting_attribution__empty"
    )
    ops.drop_tenant_table("posting_attribution")
    _processing_guard(PROCESSING_BEFORE)
