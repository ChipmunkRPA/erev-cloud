"""Retain append-only upgrade processing events for each group/entity/book portion."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0166"
down_revision = "0165"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The processing-state enum was introduced by revision 0055.
    ops.create_tenant_table(
        "release_group_processing",
        sa.Column("release_validation_id", sa.Uuid(), nullable=False),
        sa.Column("release_validation_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("combination_group_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("book_code", ops.NamedType("erev.book_code"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("upgrade_state", ops.NamedType("erev.upgrade_processing_state"), nullable=False),
        sa.Column("contract_computation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "subledger_posting_ids",
            ARRAY(sa.Uuid()),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "unresolved_origin_period_keys",
            ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        standard_sets=["SC-C"],
        checks=[
            (
                "ck_release_group_processing__sequence",
                "seq >= 1 AND ((seq = 1) = (upgrade_state = 'PENDING'))",
            ),
            (
                "ck_release_group_processing__arrays",
                "array_position(subledger_posting_ids, NULL) IS NULL "
                "AND array_position(unresolved_origin_period_keys, NULL) IS NULL",
            ),
            (
                "ck_release_group_processing__outcome",
                """
                (upgrade_state = 'PENDING' AND contract_computation_id IS NULL
                 AND cardinality(subledger_posting_ids) = 0
                 AND cardinality(unresolved_origin_period_keys) = 0)
                OR (contract_computation_id IS NOT NULL AND (
                    (upgrade_state = 'DEFERRED_NO_OPEN_PERIOD'
                 AND cardinality(unresolved_origin_period_keys) > 0)
                    OR (upgrade_state = 'POSTED' AND cardinality(subledger_posting_ids) > 0
                 AND cardinality(unresolved_origin_period_keys) = 0)
                    OR (upgrade_state = 'SETTLED_NO_POSTING'
                 AND cardinality(subledger_posting_ids) = 0
                 AND cardinality(unresolved_origin_period_keys) = 0
                 AND reason IS NOT NULL AND reason = 'NO_POSTING_DELTA')
                ))
            """,
            ),
        ],
        unique=[
            (
                "ux_release_group_processing__portion",
                [
                    "tenant_id",
                    "release_validation_id",
                    "combination_group_id",
                    "entity_id",
                    "book_code",
                    "seq",
                ],
                None,
            )
        ],
    )
    for column, target in (
        ("release_validation_id", "release_validation"),
        ("release_validation_attempt_id", "release_validation_attempt"),
        ("combination_group_id", "combination_group"),
        ("entity_id", "legal_entity"),
        ("contract_computation_id", "contract_computation"),
    ):
        ops.add_tenant_fk("release_group_processing", column, target)
    ops.apply_class("release_group_processing", "IM-A")
    ops.enable_rls("release_group_processing", "RLS-T")
    ops.create_trigger(
        "release_group_processing",
        "accepted_owner",
        """
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
""",
        timing="BEFORE",
        events="INSERT",
    )


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.release_group_processing ADD CONSTRAINT "
        "ck_release_group_processing__empty CHECK (false) NOT VALID"
    )
    ops.execute(
        "ALTER TABLE erev.release_group_processing VALIDATE CONSTRAINT "
        "ck_release_group_processing__empty"
    )
    ops.drop_tenant_table("release_group_processing")
