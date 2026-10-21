"""Retain original approval-decision and GL acknowledgement commits."""

import json

from erev_api.db import migration_ops as ops

revision = "0282"
down_revision = "0281"
branch_labels = None
depends_on = None

OLD_STAMP = """

        CREATE OR REPLACE FUNCTION erev.tg_source_commit__stamp() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NOT (
                    (NEW.source_kind = 'contract_event' AND EXISTS (
                        SELECT 1 FROM erev.contract_event
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'contract_version' AND EXISTS (
                        SELECT 1 FROM erev.contract_version
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'report_source_revision' AND EXISTS (
                        SELECT 1 FROM erev.report_source_revision
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'journal_line' AND EXISTS (
                        SELECT 1 FROM erev.journal_line
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id))
                ) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: Original source is required';
                END IF;
                NEW.source_transaction := pg_current_xact_id()::text;
                NEW.committed_server_at := NULL;
            ELSE
                IF OLD.committed_server_at IS NOT NULL THEN
                    RAISE EXCEPTION 'EREV-IMM-001: Commit evidence is immutable';
                END IF;
                IF NEW.committed_server_at IS NULL OR NEW.committed_server_at IS DISTINCT FROM
                    erev.source_commit_time(OLD.source_kind, OLD.source_id) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: Commit evidence must match PostgreSQL';
                END IF;
            END IF;
            RETURN NEW;
        END $$
"""

NEW_STAMP = """

        CREATE OR REPLACE FUNCTION erev.tg_source_commit__stamp() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NOT (
                    (NEW.source_kind = 'contract_event' AND EXISTS (
                        SELECT 1 FROM erev.contract_event
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'contract_version' AND EXISTS (
                        SELECT 1 FROM erev.contract_version
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'report_source_revision' AND EXISTS (
                        SELECT 1 FROM erev.report_source_revision
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'journal_line' AND EXISTS (
                        SELECT 1 FROM erev.journal_line
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id))
                    OR (NEW.source_kind = 'approval_decision' AND EXISTS (
                        SELECT 1 FROM erev.approval_decision
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id))
                    OR (NEW.source_kind = 'posting_ack' AND EXISTS (
                        SELECT 1 FROM erev.posting_ack
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id))
                ) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: Original source is required';
                END IF;
                NEW.source_transaction := pg_current_xact_id()::text;
                NEW.committed_server_at := NULL;
            ELSE
                IF OLD.committed_server_at IS NOT NULL THEN
                    RAISE EXCEPTION 'EREV-IMM-001: Commit evidence is immutable';
                END IF;
                IF NEW.committed_server_at IS NULL OR NEW.committed_server_at IS DISTINCT FROM
                    erev.source_commit_time(OLD.source_kind, OLD.source_id) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: Commit evidence must match PostgreSQL';
                END IF;
            END IF;
            RETURN NEW;
        END $$
"""


def _kinds(*, undo: bool) -> None:
    kinds = "'contract_event','contract_version','report_source_revision','journal_line'"
    if not undo:
        kinds += ",'approval_decision','posting_ack'"
    ops.execute(
        "ALTER TABLE erev.historical_source_commit "
        "DROP CONSTRAINT ck_historical_source_commit__kind"
    )
    ops.execute(
        "ALTER TABLE erev.historical_source_commit "
        "ADD CONSTRAINT ck_historical_source_commit__kind "
        "CHECK (source_kind IN (" + kinds + "))"
    )


OLD_IPE = (
    '{"je_population":{"version":1,"source_tables":["journal_line","journal_entry","journal_b'
    'atch","journal_run","posting_ack","gl_account","legal_entity","period","contract","oblig'
    'ation","lock_snapshot","report_source_revision","historical_source_commit"],"joins":["jo'
    'urnal_line.journal_entry_id = journal_entry.id","journal_line.journal_batch_id = journal'
    '_batch.id","journal_batch.journal_run_id = journal_run.id","posting_ack.journal_batch_id'
    ' = journal_batch.id","journal_line.gl_account_id = gl_account.id","journal_line.period_i'
    'd = period.id","journal_line.contract_id = contract.id","journal_line.obligation_id = ob'
    'ligation.id"],"filters":["entity code in entity_codes and within the caller\'s entity sco'
    'pe","book_code = book","period_key from from_period_key to to_period_key","include_cance'
    'lled false: runs not cancelled","historical basis: original line commits and committed r'
    'un/batch revisions by known_at","je_population_inputs_v1 retains input rows, labels and '
    "independent run debit totals; same-source rebuilds recompute rows and controls without q"
    'uerying mutable sources","record basis and DATASET_FREEZE preserve transaction-local jou'
    'rnal visibility","first-generation ancillary approval/ack/name reads retain existing cut'
    "off semantics; retention guarantees repeatability, not complete historical reconstructio"
    'n","with period_lock_id, the values frozen at that lock (lock_snapshot kind JE_POPULATIO'
    'N)"],"parameters":["entity_codes","book","from_period_key","to_period_key","period_lock_'
    'id","include_cancelled","known_at","known_at_basis"]}}'
)

NEW_IPE = (
    '{"je_population":{"version":1,"source_tables":["journal_line","journal_entry","journal_b'
    'atch","journal_run","posting_ack","gl_account","legal_entity","period","contract","oblig'
    'ation","lock_snapshot","report_source_revision","historical_source_commit"],"joins":["jo'
    'urnal_line.journal_entry_id = journal_entry.id","journal_line.journal_batch_id = journal'
    '_batch.id","journal_batch.journal_run_id = journal_run.id","posting_ack.journal_batch_id'
    ' = journal_batch.id","journal_line.gl_account_id = gl_account.id","journal_line.period_i'
    'd = period.id","journal_line.contract_id = contract.id","journal_line.obligation_id = ob'
    'ligation.id"],"filters":["entity code in entity_codes and within the caller\'s entity sco'
    'pe","book_code = book","period_key from from_period_key to to_period_key","include_cance'
    'lled false: runs not cancelled","historical basis: original line commits and committed r'
    'un/batch revisions by known_at","je_population_inputs_v1 retains input rows, labels and '
    "independent run debit totals; same-source rebuilds recompute rows and controls without q"
    'uerying mutable sources","record basis and DATASET_FREEZE preserve transaction-local jou'
    'rnal visibility","historical approval decisions and GL acknowledgements also require ori'
    'ginal commits by known_at; record basis preserves transaction-local visibility","first-g'
    'eneration actor names remain current labels; retention freezes consumed labels","with pe'
    'riod_lock_id, the values frozen at that lock (lock_snapshot kind JE_POPULATION)"],"param'
    'eters":["entity_codes","book","from_period_key","to_period_key","period_lock_id","includ'
    'e_cancelled","known_at","known_at_basis"]}}'
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
    for source in ("approval_decision", "posting_ack"):
        ops.execute(
            f"ALTER TABLE erev.{source} ADD CONSTRAINT ck_source__0282_empty "
            "CHECK (false) NOT VALID"
        )
        ops.execute(f"ALTER TABLE erev.{source} VALIDATE CONSTRAINT ck_source__0282_empty")
        ops.execute(f"ALTER TABLE erev.{source} DROP CONSTRAINT ck_source__0282_empty")
    _kinds(undo=False)
    ops.execute(NEW_STAMP)
    for source in ("approval_decision", "posting_ack"):
        ops.execute(
            f"CREATE TRIGGER zz_source__commit_queue AFTER INSERT ON erev.{source} "
            "FOR EACH ROW EXECUTE FUNCTION erev.tg_source_commit__queue()"
        )


def downgrade() -> None:
    _metadata(OLD_IPE)
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.historical_source_commit
                 WHERE source_kind IN ('approval_decision','posting_ack')) THEN
        RAISE EXCEPTION 'Retained decision/acknowledgement evidence prevents downgrade';
      END IF;
    END $$""")
    for source in ("approval_decision", "posting_ack"):
        ops.execute(f"DROP TRIGGER zz_source__commit_queue ON erev.{source}")
    ops.execute(OLD_STAMP)
    _kinds(undo=True)
