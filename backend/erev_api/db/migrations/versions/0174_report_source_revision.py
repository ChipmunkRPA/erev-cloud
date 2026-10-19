"""Retain mutable contract headers and code labels for historical extracts."""

# SQL interpolation below uses only the fixed migration literals.
# ruff: noqa: S608

import sqlalchemy as sa
from erev_api.db import migration_ops as ops
from sqlalchemy.dialects.postgresql import JSONB

revision = "0174"
down_revision = "0173"
branch_labels = None
depends_on = None


UP = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["report_source_revision"],"joins":["captured contract customer_id and contracting_entity_id to latest captured code labels at known_at"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","latest database-captured revision at known_at; uncovered migration-era history refuses","mode INCREMENTAL: contract created_at after known_since; not an update or deletion feed","lock datasets unsupported"],"parameters":["mode","entity_codes","period_lock_id","known_at","known_since","known_at_basis"]}\'::jsonb WHERE code = \'extract_contracts\' AND version = 1'  # noqa: E501
DOWN = 'UPDATE erev.report_definition SET ipe_logic = \'{"version":1,"source_tables":["contract","customer","legal_entity"],"joins":["contract.customer_id = customer.id","contract.contracting_entity_id = legal_entity.id"],"filters":["entity code in entity_codes and within the caller\'\'s entity scope","source time: the lock of period_lock_id when given, else known_at","mode INCREMENTAL: rows created (recorded for events and subledger lines) after known_since and at or before the source time"],"parameters":["mode","entity_codes","period_lock_id","known_at","known_since","known_at_basis"]}\'::jsonb WHERE code = \'extract_contracts\' AND version = 1'  # noqa: E501


def _ipe(statement: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(statement)
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    ops.create_tenant_table(
        "report_source_revision",
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("revision_no", sa.BigInteger(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_baseline", sa.Boolean(), nullable=False),
        sa.Column("document", JSONB(), nullable=False),
        checks=[
            (
                "ck_report_source_revision__kind",
                "source_kind IN ('contract', 'customer_code', 'entity_code')",
            ),
            ("ck_report_source_revision__number", "revision_no > 0"),
        ],
        unique=[
            (
                "ux_report_source_revision__source",
                ["tenant_id", "source_kind", "source_id", "revision_no"],
                None,
            )
        ],
        indexes=[
            ("ix_report_source_revision__time", ["tenant_id", "source_kind", "recorded_at"], None)
        ],
    )
    ops.apply_class("report_source_revision", "IM-A")
    ops.enable_rls(
        "report_source_revision", "RLS-TE", entity_column="entity_id", entity_nullable=True
    )
    ops.execute(
        "LOCK TABLE erev.contract, erev.customer, erev.legal_entity IN SHARE ROW EXCLUSIVE MODE"
    )
    # Baselines attest only to migration-time state. They never claim prior coverage.
    for table, kind, entity, document in (
        ("contract", "contract", "s.contracting_entity_id", "to_jsonb(s) - 'tenant_id'"),
        (
            "customer",
            "customer_code",
            "NULL::uuid",
            "jsonb_build_object('id', s.id, 'code', s.code)",
        ),
        (
            "legal_entity",
            "entity_code",
            "NULL::uuid",
            "jsonb_build_object('id', s.id, 'code', s.code)",
        ),
    ):
        ops.execute(f"""INSERT INTO erev.report_source_revision
          (tenant_id,id,source_kind,source_id,entity_id,revision_no,recorded_at,is_baseline,document)
          SELECT s.tenant_id,gen_random_uuid(),'{kind}',s.id,{entity},1,
            clock_timestamp(),TRUE,{document}
          FROM erev.{table} s""")
    ops.create_trigger(
        "report_source_revision",
        "capture_only",
        """
DECLARE expected jsonb; scoped_entity uuid;
BEGIN
  IF pg_trigger_depth() < 2 OR NEW.is_baseline THEN
    RAISE EXCEPTION 'Report source revisions are written only by source triggers'
      USING ERRCODE='23514';
  END IF;
  IF NEW.source_kind = 'contract' THEN
    SELECT to_jsonb(c) - 'tenant_id', c.contracting_entity_id INTO expected,scoped_entity
      FROM erev.contract c WHERE c.tenant_id=NEW.tenant_id AND c.id=NEW.source_id;
  ELSIF NEW.source_kind = 'customer_code' THEN
    SELECT jsonb_build_object('id',c.id,'code',c.code) INTO expected
      FROM erev.customer c WHERE c.tenant_id=NEW.tenant_id AND c.id=NEW.source_id;
  ELSIF NEW.source_kind = 'entity_code' THEN
    SELECT jsonb_build_object('id',c.id,'code',c.code) INTO expected
      FROM erev.legal_entity c WHERE c.tenant_id=NEW.tenant_id AND c.id=NEW.source_id;
  END IF;
  IF expected IS NULL OR NEW.document IS DISTINCT FROM expected
     OR NEW.entity_id IS DISTINCT FROM scoped_entity THEN
    RAISE EXCEPTION 'Report revision must equal its current source row' USING ERRCODE='23514';
  END IF;
  SELECT coalesce(max(r.revision_no),0)+1 INTO NEW.revision_no
    FROM erev.report_source_revision r WHERE r.tenant_id=NEW.tenant_id
      AND r.source_kind=NEW.source_kind AND r.source_id=NEW.source_id;
  NEW.recorded_at := clock_timestamp();
  RETURN NEW;
END
""",
        timing="BEFORE",
        events="INSERT",
    )
    for table, kind, entity, document, changed in (
        (
            "contract",
            "contract",
            "NEW.contracting_entity_id",
            "to_jsonb(NEW) - 'tenant_id'",
            "to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD)",
        ),
        (
            "customer",
            "customer_code",
            "NULL::uuid",
            "jsonb_build_object('id', NEW.id, 'code', NEW.code)",
            "NEW.code IS DISTINCT FROM OLD.code",
        ),
        (
            "legal_entity",
            "entity_code",
            "NULL::uuid",
            "jsonb_build_object('id', NEW.id, 'code', NEW.code)",
            "NEW.code IS DISTINCT FROM OLD.code",
        ),
    ):
        ops.create_trigger(
            table,
            "report_revision",
            f"""
BEGIN
  IF TG_OP = 'INSERT' OR {changed} THEN
    INSERT INTO erev.report_source_revision
      (tenant_id,id,source_kind,source_id,entity_id,revision_no,recorded_at,is_baseline,document)
    VALUES (NEW.tenant_id,gen_random_uuid(),'{kind}',NEW.id,{entity},1,
      clock_timestamp(),FALSE,{document});
  END IF;
  RETURN NEW;
END
""",
            timing="AFTER",
            events="INSERT OR UPDATE",
        )

    _ipe(UP)


def downgrade() -> None:
    # Do not silently discard historical evidence once captured.
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.report_source_revision) THEN
        RAISE EXCEPTION 'Retained report source revisions prevent downgrade';
      END IF;
    END $$""")
    for table in ("contract", "customer", "legal_entity"):
        ops.execute(f"DROP TRIGGER tg_{table}__report_revision ON erev.{table}")
        ops.execute(f"DROP FUNCTION erev.tg_{table}__report_revision()")
    ops.execute("DROP TABLE erev.report_source_revision")
    ops.execute("DROP FUNCTION erev.tg_report_source_revision__capture_only()")
    _ipe(DOWN)
