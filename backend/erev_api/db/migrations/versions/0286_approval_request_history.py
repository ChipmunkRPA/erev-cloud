"""Capture committed approval request states for historical registers."""

import json

from erev_api.db import migration_ops as ops

revision = "0286"
down_revision = "0285"
branch_labels = None
depends_on = None

OLD_CAPTURE = """

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
  ELSIF NEW.source_kind = 'journal_run' THEN
    SELECT to_jsonb(r) - 'tenant_id', r.entity_id INTO expected,scoped_entity
      FROM erev.journal_run r WHERE r.tenant_id=NEW.tenant_id AND r.id=NEW.source_id;
  ELSIF NEW.source_kind = 'journal_batch' THEN
    SELECT to_jsonb(r) - 'tenant_id', r.entity_id INTO expected,scoped_entity
      FROM erev.journal_batch r WHERE r.tenant_id=NEW.tenant_id AND r.id=NEW.source_id;
  ELSIF NEW.source_kind = 'file_attachment' THEN
    SELECT to_jsonb(a) - 'tenant_id' INTO expected
      FROM erev.file_attachment a WHERE a.tenant_id=NEW.tenant_id AND a.id=NEW.source_id;
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

NEW_CAPTURE = """

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
  ELSIF NEW.source_kind = 'journal_run' THEN
    SELECT to_jsonb(r) - 'tenant_id', r.entity_id INTO expected,scoped_entity
      FROM erev.journal_run r WHERE r.tenant_id=NEW.tenant_id AND r.id=NEW.source_id;
  ELSIF NEW.source_kind = 'journal_batch' THEN
    SELECT to_jsonb(r) - 'tenant_id', r.entity_id INTO expected,scoped_entity
      FROM erev.journal_batch r WHERE r.tenant_id=NEW.tenant_id AND r.id=NEW.source_id;
  ELSIF NEW.source_kind = 'file_attachment' THEN
    SELECT to_jsonb(a) - 'tenant_id' INTO expected
      FROM erev.file_attachment a WHERE a.tenant_id=NEW.tenant_id AND a.id=NEW.source_id;
  ELSIF NEW.source_kind = 'approval_request' THEN
    SELECT to_jsonb(a) - 'tenant_id' INTO expected
      FROM erev.approval_request a WHERE a.tenant_id=NEW.tenant_id AND a.id=NEW.source_id;
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


def _capture_guard(body: str) -> None:
    ops.execute(
        "CREATE OR REPLACE FUNCTION erev.tg_report_source_revision__capture_only() "
        "RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER "
        "SET search_path=pg_catalog,erev AS $$" + body + "$$"
    )


def _kinds(*, undo: bool) -> None:
    kinds = (
        "'contract','customer_code','entity_code','gl_reconciliation',"
        "'journal_run','journal_batch','file_attachment'"
    )
    if not undo:
        kinds += ",'approval_request'"
    ops.execute(
        "ALTER TABLE erev.report_source_revision DROP CONSTRAINT ck_report_source_revision__kind"
    )
    ops.execute(
        "ALTER TABLE erev.report_source_revision "
        "ADD CONSTRAINT ck_report_source_revision__kind "
        "CHECK (source_kind IN (" + kinds + "))"
    )


OLD_IPE = (
    '{"approvals_register":{"version":1,"source_tables":["approval_request","approval_step","'
    'approval_decision","app_user","legal_entity"],"joins":["approval_step.approval_request_i'
    'd = approval_request.id","approval_decision.approval_step_id = approval_step.id","approv'
    'al_decision.approver_id = app_user.id","approval_request.entity_id = legal_entity.id"],"'
    'filters":["requests whose every entity is in entity_codes, and tenant-level requests; a '
    'request of all entities when entity_codes names every entity","submitted from from_date '
    'to to_date inclusive","subject_types and status when given"],"parameters":["entity_codes'
    '","from_date","to_date","subject_types","status","currency_view","known_at","known_at_ba'
    'sis"]}}'
)

NEW_IPE = (
    '{"approvals_register":{"version":1,"source_tables":["approval_request","approval_step","'
    'approval_decision","app_user","legal_entity","report_source_revision","historical_source'
    '_commit"],"joins":["approval_step.approval_request_id = approval_request.id","approval_d'
    'ecision.approval_step_id = approval_step.id","approval_decision.approver_id = app_user.i'
    'd","approval_request.entity_id = legal_entity.id"],"filters":["requests whose every enti'
    "ty is in entity_codes, and tenant-level requests; a request of all entities when entity_"
    'codes names every entity","submitted from from_date to to_date inclusive","subject_types'
    ' and status when given","historical basis selects committed request revisions and origin'
    "al decision commits at known_at before status filtering; record basis preserves business"
    '-time behavior","display labels and ancillary rule/step references retain existing read '
    'semantics"],"parameters":["entity_codes","from_date","to_date","subject_types","status",'
    '"currency_view","known_at","known_at_basis"]}}'
)


def _metadata(encoded: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for code, ipe in json.loads(encoded).items():
        payload = json.dumps(ipe).replace("'", "''")
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic='"  # noqa: S608 — frozen metadata
            + payload
            + "'::jsonb WHERE code='"
            + code
            + "' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_IPE)
    ops.execute(
        "ALTER TABLE erev.approval_request ADD CONSTRAINT ck_request__0286_empty "
        "CHECK (false) NOT VALID"
    )
    ops.execute("ALTER TABLE erev.approval_request VALIDATE CONSTRAINT ck_request__0286_empty")
    ops.execute("ALTER TABLE erev.approval_request DROP CONSTRAINT ck_request__0286_empty")
    _kinds(undo=False)
    _capture_guard(NEW_CAPTURE)
    ops.create_trigger(
        "approval_request",
        "report_revision",
        """
BEGIN
  IF TG_OP='INSERT' OR to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
    INSERT INTO erev.report_source_revision
      (tenant_id,id,source_kind,source_id,entity_id,revision_no,recorded_at,is_baseline,document)
    VALUES (NEW.tenant_id,gen_random_uuid(),'approval_request',NEW.id,NULL,1,
      clock_timestamp(),FALSE,to_jsonb(NEW)-'tenant_id');
  END IF;
  RETURN NEW;
END
""",
        timing="AFTER",
        events="INSERT OR UPDATE",
    )


def downgrade() -> None:
    _metadata(OLD_IPE)
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.report_source_revision
                 WHERE source_kind='approval_request') THEN
        RAISE EXCEPTION 'Retained approval request history prevents downgrade';
      END IF;
    END $$""")
    ops.execute("DROP TRIGGER tg_approval_request__report_revision ON erev.approval_request")
    ops.execute("DROP FUNCTION erev.tg_approval_request__report_revision()")
    _capture_guard(OLD_CAPTURE)
    _kinds(undo=True)
