"""Retain original audit commits with the partition key for source validation."""

import json

from erev_api.db import migration_ops as ops

revision = "0287"
down_revision = "0286"
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
                    OR (NEW.source_kind = 'audit_event' AND EXISTS (
                        SELECT 1 FROM erev.audit_event
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id
                            AND occurred_at = NEW.source_occurred_at))
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


OLD_IPE = (
    '{"contract_sample_pack":{"version":1,"source_tables":["evidence_pack","contract","con'
    'tract_event","contract_version","obligation_version","schedule_line","subledger_line"'
    ',"calc_trace","file_attachment","file_object","journal_line","journal_entry","journal'
    '_batch","journal_run","report_source_revision","historical_source_commit","subledger_'
    'posting_commit"],"joins":["evidence_pack.contract_ids holds the sampled contracts","c'
    'ontract_event.contract_id = contract.id","obligation_version.contract_id = contract.i'
    'd","schedule_line.contract_id = contract.id","subledger_line.contract_id = contract.i'
    'd","calc_trace.contract_version_id = contract_version.id"],"filters":["contract.exter'
    'nal_id in contract_external_ids (1 to 50)","figures as of as_of and known at known_at'
    '","sample/journals.json v2 uses original journal/underlying posting commits and commi'
    'tted run/batch revisions; cancelled lines remain explicitly labelled at cutoff","samp'
    "le event files and computations index v2 require original event/version commits by kn"
    'own_at before latest-version selection; retain commit timestamps and full schedules",'
    '"selection.json v2 and computation member identities use committed contract header re'
    "visions at known_at; missing history refuses; current and historical owner permission"
    's are enforced before export","documents.json v2 uses committed attachment lifecycle '
    "revisions at cutoff; current subject/file grants, availability and byte integrity rem"
    'ain mandatory","journal sample totals retain whole aggregated lines and separate samp'
    'led contributions; old archives remain unchanged","entity code in entity_codes and wi'
    'thin the caller\'s entity scope"],"parameters":["entity_codes","contract_external_ids"'
    ',"as_of","known_at","known_at_basis"]}}'
)

NEW_IPE = (
    '{"contract_sample_pack": {"version": 1, "source_tables": ["evidence_pack", "audit_eve'
    'nt", "audit_event_contract", "approval_request", "approval_decision", "contract", "co'
    'ntract_event", "contract_version", "obligation_version", "schedule_line", "subledger_'
    'line", "calc_trace", "file_attachment", "file_object", "journal_line", "journal_entry'
    '", "journal_batch", "journal_run", "report_source_revision", "historical_source_commi'
    't", "subledger_posting_commit"], "joins": ["evidence_pack.contract_ids holds the samp'
    'led contracts", "contract_event.contract_id = contract.id", "obligation_version.contr'
    'act_id = contract.id", "schedule_line.contract_id = contract.id", "subledger_line.con'
    'tract_id = contract.id", "calc_trace.contract_version_id = contract_version.id"], "fi'
    'lters": ["contract.external_id in contract_external_ids (1 to 50)", "figures as of as'
    '_of and known at known_at", "sample/journals.json v2 uses original journal/underlying'
    " posting commits and committed run/batch revisions; cancelled lines remain explicitly"
    ' labelled at cutoff", "sample event files and computations index v2 require original '
    "event/version commits by known_at before latest-version selection; retain commit time"
    'stamps and full schedules", "selection.json v2 and computation member identities use '
    "committed contract header revisions at known_at; missing history refuses; current and"
    ' historical owner permissions are enforced before export", "documents.json v2 uses co'
    "mmitted attachment lifecycle revisions at cutoff; current subject/file grants, availa"
    'bility and byte integrity remain mandatory", "sample approvals/audit v2 use committed'
    " request revisions and original decision/audit commits by known_at; decision and audi"
    't commit timestamps remain in the archive", "journal sample totals retain whole aggre'
    'gated lines and separate sampled contributions; old archives remain unchanged", "enti'
    'ty code in entity_codes and within the caller\'s entity scope"], "parameters": ["entit'
    'y_codes", "contract_external_ids", "as_of", "known_at", "known_at_basis"]}}'
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


def _kinds(*, undo: bool) -> None:
    kinds = "'contract_event','contract_version','report_source_revision','journal_line',"
    kinds += "'approval_decision','posting_ack'"
    if not undo:
        kinds += ",'audit_event'"
    ops.execute(
        "ALTER TABLE erev.historical_source_commit "
        "DROP CONSTRAINT ck_historical_source_commit__kind"
    )
    ops.execute(
        "ALTER TABLE erev.historical_source_commit "
        "ADD CONSTRAINT ck_historical_source_commit__kind CHECK (source_kind IN (" + kinds + "))"
    )


def upgrade() -> None:
    _metadata(NEW_IPE)
    # No live-data migration is required; never invent original commits for existing events.
    ops.execute(
        "ALTER TABLE erev.audit_event ADD CONSTRAINT ck_source__0287_empty CHECK (false) NOT VALID"
    )
    ops.execute("ALTER TABLE erev.audit_event VALIDATE CONSTRAINT ck_source__0287_empty")
    ops.execute("ALTER TABLE erev.audit_event DROP CONSTRAINT ck_source__0287_empty")
    ops.execute(
        "ALTER TABLE erev.historical_source_commit ADD COLUMN source_occurred_at timestamptz"
    )
    ops.execute(
        "ALTER TABLE erev.historical_source_commit "
        "ADD CONSTRAINT ck_historical_source_commit__locator "
        "CHECK ((source_kind = 'audit_event') = (source_occurred_at IS NOT NULL))"
    )
    _kinds(undo=False)
    ops.execute(NEW_STAMP)
    # Partition triggers see the child table name. Use a fixed source kind and retain
    # occurred_at so the validation probe prunes to the original monthly partition.
    ops.execute("""
        CREATE FUNCTION erev.tg_audit_commit__queue() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        BEGIN
            IF current_setting('track_commit_timestamp') <> 'on' THEN
                RAISE EXCEPTION 'EREV-HIS-001: PostgreSQL commit timestamp tracking is required';
            END IF;
            INSERT INTO erev.historical_source_commit
                (tenant_id, source_kind, source_id, source_transaction, source_occurred_at)
            VALUES (NEW.tenant_id, 'audit_event', NEW.id,
                pg_current_xact_id()::text, NEW.occurred_at);
            RETURN NEW;
        END $$
    """)
    ops.execute("REVOKE ALL ON FUNCTION erev.tg_audit_commit__queue() FROM PUBLIC")
    ops.execute(
        "CREATE TRIGGER zz_source__commit_queue AFTER INSERT ON erev.audit_event "
        "FOR EACH ROW EXECUTE FUNCTION erev.tg_audit_commit__queue()"
    )


def downgrade() -> None:
    _metadata(OLD_IPE)
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.historical_source_commit WHERE source_kind = 'audit_event') THEN
        RAISE EXCEPTION 'Retained audit commit evidence prevents downgrade';
      END IF;
    END $$""")
    ops.execute("DROP TRIGGER zz_source__commit_queue ON erev.audit_event")
    ops.execute("DROP FUNCTION erev.tg_audit_commit__queue()")
    ops.execute(OLD_STAMP)
    _kinds(undo=True)
    ops.execute(
        "ALTER TABLE erev.historical_source_commit "
        "DROP CONSTRAINT ck_historical_source_commit__locator"
    )
    ops.execute("ALTER TABLE erev.historical_source_commit DROP COLUMN source_occurred_at")
