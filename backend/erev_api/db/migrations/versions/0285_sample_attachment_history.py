"""Capture committed attachment lifecycle for historical sample membership."""

import json

from erev_api.db import migration_ops as ops

revision = "0285"
down_revision = "0284"
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
        "'contract','customer_code','entity_code','gl_reconciliation','journal_run','journal_batch'"
    )
    if not undo:
        kinds += ",'file_attachment'"
    ops.execute(
        "ALTER TABLE erev.report_source_revision DROP CONSTRAINT ck_report_source_revision__kind"
    )
    ops.execute(
        "ALTER TABLE erev.report_source_revision "
        "ADD CONSTRAINT ck_report_source_revision__kind "
        "CHECK (source_kind IN (" + kinds + "))"
    )


OLD_IPE = (
    '{"contract_sample_pack":{"version":1,"source_tables":["evidence_pack","contract","contra'
    'ct_event","contract_version","obligation_version","schedule_line","subledger_line","calc'
    '_trace","journal_line","journal_entry","journal_batch","journal_run","report_source_revi'
    'sion","historical_source_commit","subledger_posting_commit"],"joins":["evidence_pack.con'
    'tract_ids holds the sampled contracts","contract_event.contract_id = contract.id","oblig'
    'ation_version.contract_id = contract.id","schedule_line.contract_id = contract.id","subl'
    'edger_line.contract_id = contract.id","calc_trace.contract_version_id = contract_version'
    '.id"],"filters":["contract.external_id in contract_external_ids (1 to 50)","figures as o'
    'f as_of and known at known_at","sample/journals.json v2 uses original journal/underlying'
    " posting commits and committed run/batch revisions; cancelled lines remain explicitly la"
    'belled at cutoff","sample event files and computations index v2 require original event/v'
    "ersion commits by known_at before latest-version selection; retain commit timestamps and"
    ' full schedules","selection.json v2 and computation member identities use committed cont'
    "ract header revisions at known_at; missing history refuses; current and historical owner"
    ' permissions are enforced before export","journal sample totals retain whole aggregated '
    'lines and separate sampled contributions; old archives remain unchanged","entity code in'
    ' entity_codes and within the caller\'s entity scope"],"parameters":["entity_codes","contr'
    'act_external_ids","as_of","known_at","known_at_basis"]}}'
)

NEW_IPE = (
    '{"contract_sample_pack":{"version":1,"source_tables":["evidence_pack","contract","contra'
    'ct_event","contract_version","obligation_version","schedule_line","subledger_line","calc'
    '_trace","file_attachment","file_object","journal_line","journal_entry","journal_batch","'
    'journal_run","report_source_revision","historical_source_commit","subledger_posting_comm'
    'it"],"joins":["evidence_pack.contract_ids holds the sampled contracts","contract_event.c'
    'ontract_id = contract.id","obligation_version.contract_id = contract.id","schedule_line.'
    'contract_id = contract.id","subledger_line.contract_id = contract.id","calc_trace.contra'
    'ct_version_id = contract_version.id"],"filters":["contract.external_id in contract_exter'
    'nal_ids (1 to 50)","figures as of as_of and known at known_at","sample/journals.json v2 '
    "uses original journal/underlying posting commits and committed run/batch revisions; canc"
    'elled lines remain explicitly labelled at cutoff","sample event files and computations i'
    "ndex v2 require original event/version commits by known_at before latest-version selecti"
    'on; retain commit timestamps and full schedules","selection.json v2 and computation memb'
    "er identities use committed contract header revisions at known_at; missing history refus"
    'es; current and historical owner permissions are enforced before export","documents.json'
    " v2 uses committed attachment lifecycle revisions at cutoff; current subject/file grants"
    ', availability and byte integrity remain mandatory","journal sample totals retain whole '
    'aggregated lines and separate sampled contributions; old archives remain unchanged","ent'
    'ity code in entity_codes and within the caller\'s entity scope"],"parameters":["entity_co'
    'des","contract_external_ids","as_of","known_at","known_at_basis"]}}'
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
        "ALTER TABLE erev.file_attachment ADD CONSTRAINT ck_attachment__0285_empty "
        "CHECK (false) NOT VALID"
    )
    ops.execute("ALTER TABLE erev.file_attachment VALIDATE CONSTRAINT ck_attachment__0285_empty")
    ops.execute("ALTER TABLE erev.file_attachment DROP CONSTRAINT ck_attachment__0285_empty")
    _kinds(undo=False)
    _capture_guard(NEW_CAPTURE)
    ops.create_trigger(
        "file_attachment",
        "report_revision",
        """
BEGIN
  IF TG_OP='INSERT' OR to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN
    INSERT INTO erev.report_source_revision
      (tenant_id,id,source_kind,source_id,entity_id,revision_no,recorded_at,is_baseline,document)
    VALUES (NEW.tenant_id,gen_random_uuid(),'file_attachment',NEW.id,NULL,1,
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
      IF EXISTS (SELECT 1 FROM erev.report_source_revision WHERE source_kind='file_attachment') THEN
        RAISE EXCEPTION 'Retained attachment history prevents downgrade';
      END IF;
    END $$""")
    ops.execute("DROP TRIGGER tg_file_attachment__report_revision ON erev.file_attachment")
    ops.execute("DROP FUNCTION erev.tg_file_attachment__report_revision()")
    _capture_guard(OLD_CAPTURE)
    _kinds(undo=True)
