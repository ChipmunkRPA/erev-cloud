"""Retain original verification commits and describe repeatable verification reports."""

import json

from erev_api.db import migration_ops as ops

revision = "0291"
down_revision = "0290"
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
                    OR (NEW.source_kind = 'audit_chain_verification' AND EXISTS (
                        SELECT 1 FROM erev.audit_chain_verification
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

OLD_IPE = (
    '{"chain_verification_report": {"version": 1, "source_tables": ["audit_chain_verificat'
    'ion", "file_object"], "joins": ["audit_chain_verification.digest_file_id = file_objec'
    't.id"], "filters": ["audit_chain_verification.finished_at from from to to"], "paramet'
    'ers": ["entity_codes", "from", "to", "known_at", "known_at_basis"]}}'
)

NEW_IPE = (
    '{"chain_verification_report": {"version": 1, "source_tables": ["audit_chain_verificat'
    'ion", "file_object", "historical_source_commit"], "joins": ["audit_chain_verification'
    '.digest_file_id = file_object.id"], "filters": ["audit_chain_verification.finished_at'
    ' from from to to", "historical basis requires original verification commits by known_'
    'at; record basis preserves transaction-local visibility", "chain_verification_inputs_'
    "v1 retains verification records and date range; same-source reruns rebuild rows and f"
    'ailure counts without live reads"], "parameters": ["entity_codes", "from", "to", "kno'
    'wn_at", "known_at_basis"]}}'
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
    kinds += "'approval_decision','posting_ack','audit_event'"
    if not undo:
        kinds += ",'audit_chain_verification'"
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
    ops.execute(
        "ALTER TABLE erev.audit_chain_verification "
        "ADD CONSTRAINT ck_source__0291_empty CHECK (false) NOT VALID"
    )
    ops.execute(
        "ALTER TABLE erev.audit_chain_verification VALIDATE CONSTRAINT ck_source__0291_empty"
    )
    ops.execute("ALTER TABLE erev.audit_chain_verification DROP CONSTRAINT ck_source__0291_empty")
    _kinds(undo=False)
    ops.execute(NEW_STAMP)
    ops.execute(
        "CREATE TRIGGER zz_source__commit_queue AFTER INSERT ON erev.audit_chain_verification "
        "FOR EACH ROW EXECUTE FUNCTION erev.tg_source_commit__queue()"
    )


def downgrade() -> None:
    _metadata(OLD_IPE)
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.historical_source_commit
                 WHERE source_kind = 'audit_chain_verification') THEN
        RAISE EXCEPTION 'Retained verification commit evidence prevents downgrade';
      END IF;
    END $$""")
    ops.execute("DROP TRIGGER zz_source__commit_queue ON erev.audit_chain_verification")
    ops.execute(OLD_STAMP)
    _kinds(undo=True)
