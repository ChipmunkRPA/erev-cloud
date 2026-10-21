"""Capture immutable GL reconciliation state for historical report comparisons."""

# Interpolation is limited to the fixed migration NOTE.
# ruff: noqa: S608

from erev_api.db import migration_ops as ops

revision = "0257"
down_revision = "0256"
branch_labels = None
depends_on = None

CAPTURE_BODY = """
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
  ELSIF NEW.source_kind = 'gl_reconciliation' THEN
    SELECT to_jsonb(r) - 'tenant_id', r.entity_id INTO expected,scoped_entity
      FROM erev.reconciliation r WHERE r.tenant_id=NEW.tenant_id AND r.id=NEW.source_id
      AND r.kind='SUBLEDGER_TO_GL';
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
"""


NOTE = (
    "GL bridge v5 reads the latest database-captured reconciliation revision at the report "
    "cutoff for the latest source identity, preserving original review state and totals after "
    "later changes; migration baselines attest only to capture-time state and uncovered "
    "history is unavailable; original revision identity and amounts are bound for reruns; "
    "retained v1-v4 comparisons keep their prior rules"
)


def upgrade() -> None:
    ops.execute("LOCK TABLE erev.reconciliation IN SHARE ROW EXCLUSIVE MODE")
    ops.execute(
        "ALTER TABLE erev.report_source_revision DROP CONSTRAINT ck_report_source_revision__kind"
    )
    ops.execute(
        "ALTER TABLE erev.report_source_revision ADD CONSTRAINT ck_report_source_revision__kind "
        "CHECK (source_kind IN ('contract','customer_code','entity_code','gl_reconciliation'))"
    )
    ops.execute(
        "ALTER TABLE erev.report_source_revision DISABLE TRIGGER "
        "tg_report_source_revision__capture_only"
    )
    ops.execute("""INSERT INTO erev.report_source_revision
      (tenant_id,id,source_kind,source_id,entity_id,revision_no,recorded_at,is_baseline,document)
      SELECT tenant_id,gen_random_uuid(),'gl_reconciliation',id,entity_id,1,
        clock_timestamp(),TRUE,to_jsonb(r)-'tenant_id'
      FROM erev.reconciliation r WHERE kind='SUBLEDGER_TO_GL'""")
    ops.execute(
        "DROP TRIGGER tg_report_source_revision__capture_only ON erev.report_source_revision"
    )
    ops.execute("DROP FUNCTION erev.tg_report_source_revision__capture_only()")
    ops.create_trigger(
        "report_source_revision", "capture_only", CAPTURE_BODY, timing="BEFORE", events="INSERT"
    )
    ops.create_trigger(
        "reconciliation",
        "report_revision",
        """
BEGIN
  IF NEW.kind='SUBLEDGER_TO_GL' AND
     (TG_OP='INSERT' OR to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD)) THEN
    INSERT INTO erev.report_source_revision
      (tenant_id,id,source_kind,source_id,entity_id,revision_no,recorded_at,is_baseline,document)
    VALUES (NEW.tenant_id,gen_random_uuid(),'gl_reconciliation',NEW.id,NEW.entity_id,1,
      clock_timestamp(),FALSE,to_jsonb(NEW)-'tenant_id');
  END IF;
  RETURN NEW;
END
""",
        timing="AFTER",
        events="INSERT OR UPDATE",
    )

    _ipe(True)


def downgrade() -> None:
    # Never discard the evidence needed to reconstruct reviewed historical comparisons.
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.report_source_revision
                 WHERE source_kind='gl_reconciliation') THEN
        RAISE EXCEPTION 'Retained GL reconciliation revisions prevent downgrade';
      END IF;
    END $$""")
    ops.execute("DROP TRIGGER tg_reconciliation__report_revision ON erev.reconciliation")
    ops.execute("DROP FUNCTION erev.tg_reconciliation__report_revision()")
    ops.execute(
        "ALTER TABLE erev.report_source_revision DROP CONSTRAINT ck_report_source_revision__kind"
    )
    ops.execute(
        "ALTER TABLE erev.report_source_revision ADD CONSTRAINT ck_report_source_revision__kind "
        "CHECK (source_kind IN ('contract','customer_code','entity_code'))"
    )

    ops.execute(
        "DROP TRIGGER tg_report_source_revision__capture_only ON erev.report_source_revision"
    )
    ops.execute("DROP FUNCTION erev.tg_report_source_revision__capture_only()")
    ops.create_trigger(
        "report_source_revision", "capture_only", OLD_CAPTURE_BODY, timing="BEFORE", events="INSERT"
    )
    _ipe(False)


def _ipe(up: bool) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    if up:
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{source_tables}', "
            "(CASE WHEN (ipe_logic->'source_tables') ? 'reconciliation' THEN "
            "ipe_logic->'source_tables' ELSE (ipe_logic->'source_tables') || "
            "'[\"reconciliation\"]'::jsonb END) || "
            "'[\"report_source_revision\"]'::jsonb) WHERE code IN "
            "('contract_balances','contract_balance_rollforward') AND version=1"
        )
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
            "(ipe_logic->'filters') || to_jsonb('"
            + NOTE
            + "'::text)) WHERE code IN ('contract_balances','contract_balance_rollforward') "
            "AND version=1"
        )
    else:
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{source_tables}', "
            "(ipe_logic->'source_tables') - 'report_source_revision') WHERE code IN "
            "('contract_balances','contract_balance_rollforward') AND version=1"
        )
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{source_tables}', "
            "(ipe_logic->'source_tables') - 'reconciliation') WHERE code='contract_balances' AND "
            "version=1"
        )
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "
            "(ipe_logic->'filters') - '"
            + NOTE
            + "') WHERE code IN ('contract_balances','contract_balance_rollforward') AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


OLD_CAPTURE_BODY = """
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
"""
