"""Retain true PostgreSQL commit evidence for complete ledger postings."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0274"
down_revision = "0273"
branch_labels = None
depends_on = None


NOTE = (
    "subledger_commit_visibility_v1 requires original PostgreSQL posting commit time "
    "at or before the historical cutoff; retained commit evidence is immutable; older"
    " bindings preserve their original seal-time interpretation"
)
CODES = (
    "'adoption_bridge','book_bridge','contract_balance_rollforward','contract_cost_ro"
    "llforward','disaggregation','intercompany_pairs','out_of_period_register','reven"
    "ue_from_opening_liability','revenue_from_prior_period_obligations','revenue_wate"
    "rfall'"
)


OLD_DISAGGREGATION = (
    '{"joins":["journal_line.journal_entry_id = '
    'journal_entry.id","journal_line.obligation_id = '
    'obligation_version.obligation_id","obligation_version.product_id = '
    'product.id","journal_line.period_id = period.id"],"filters":["entity code in '
    'entity_codes and within the caller\'s entity scope","book_code = '
    'book","period_key from from_period_key to '
    "to_period_key\",\"journal_line.account_role = 'REVENUE' of runs not "
    'cancelled","grouped by dimension_code and, with include_timing, the timing of '
    'transfer","with period_lock_id, the values frozen at that lock (lock_snapshot '
    'kind DISAGGREGATION)"],"version":1,"parameters":["entity_codes","book","period'
    '_lock_id","from_period_key","to_period_key","dimension_code","include_timing",'
    '"currency_view","known_at","known_at_basis"],"source_tables":["journal_line","'
    'journal_entry","journal_run","obligation_version","product","dimension_value",'
    '"period","lock_snapshot"]}'
)

NEW_DISAGGREGATION = (
    '{"version":1,"source_tables":["subledger_line","tenant","fx_rate","fx_rate_set'
    '","fx_rate_set_version","journal_line","journal_batch","journal_run","obligati'
    'on_version","product","dimension_value","period","lock_snapshot","subledger_po'
    'sting_commit"],"joins":["subledger_line.obligation_id = '
    "obligation_version.obligation_id and subledger_line.contract_version_id = "
    'obligation_version.contract_version_id","obligation_version.product_id = '
    'product.id","subledger_line.period_id = '
    'period.id","journal_line.journal_batch_id = journal_batch.id for the '
    'independent journal tie-out"],"filters":["entity code in entity_codes and '
    'within the caller\'s entity scope","book_code = book","period_key from '
    "from_period_key to to_period_key\",\"subledger_line.account_role = 'REVENUE'; "
    'independent tie-out uses journal runs not cancelled","functional reads posted '
    "amounts; reporting translates posted functional lines at their period average "
    'rates, retained for reruns","grouped by dimension_code and, with '
    'include_timing, the timing of transfer","with period_lock_id, the values '
    "frozen at that lock (lock_snapshot kind "
    'DISAGGREGATION)","subledger_commit_visibility_v1 requires original PostgreSQL '
    "posting commit time at or before the historical cutoff; retained commit "
    "evidence is immutable; older bindings preserve their original seal-time interp"
    'retation"],"parameters":["entity_codes","book","period_lock_id","from_period_k'
    'ey","to_period_key","dimension_code","include_timing","currency_view","known_a'
    't","known_at_basis"]}'
)


def upgrade() -> None:
    # As with 0151/0152, do not invent historical instants for an existing ledger.
    ops.execute(
        "ALTER TABLE erev.subledger_posting_seal ADD CONSTRAINT ck_seal__0274_empty "
        "CHECK (false) NOT VALID"
    )
    ops.execute("ALTER TABLE erev.subledger_posting_seal VALIDATE CONSTRAINT ck_seal__0274_empty")
    ops.execute("ALTER TABLE erev.subledger_posting_seal DROP CONSTRAINT ck_seal__0274_empty")
    ops.create_tenant_table(
        "subledger_posting_commit",
        sa.Column("subledger_posting_id", sa.Uuid(), nullable=False),
        sa.Column("source_transaction", sa.Text(), nullable=False),
        sa.Column("committed_server_at", sa.DateTime(timezone=True), nullable=True),
        include_id=False,
        primary_key=["tenant_id", "subledger_posting_id"],
        checks=[("ck_subledger_posting_commit__transaction", "source_transaction ~ '^[0-9]+$'")],
    )
    ops.add_tenant_fk("subledger_posting_commit", "subledger_posting_id", "subledger_posting")
    ops.apply_class("subledger_posting_commit", "IM-S", update_columns=["committed_server_at"])
    ops.enable_rls("subledger_posting_commit", "RLS-T")
    ops.execute("""
        CREATE FUNCTION erev.tg_subledger_commit__queue() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        BEGIN
            IF current_setting('track_commit_timestamp') <> 'on' THEN
                RAISE EXCEPTION 'EREV-HIS-001: PostgreSQL commit timestamp tracking is required';
            END IF;
            INSERT INTO erev.subledger_posting_commit
                (tenant_id, subledger_posting_id, source_transaction)
            VALUES (NEW.tenant_id, NEW.subledger_posting_id, pg_current_xact_id()::text);
            RETURN NEW;
        END $$
    """)
    ops.execute("REVOKE ALL ON FUNCTION erev.tg_subledger_commit__queue() FROM PUBLIC")
    ops.execute("""
        CREATE TRIGGER zz_subledger_seal__commit_queue AFTER INSERT ON erev.subledger_posting_seal
        FOR EACH ROW EXECUTE FUNCTION erev.tg_subledger_commit__queue()
    """)
    ops.execute("""
        CREATE FUNCTION erev.subledger_commit_time(p_posting uuid) RETURNS timestamptz
        LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        DECLARE source_id text; stamp timestamptz; state text;
        BEGIN
            SELECT source_transaction, committed_server_at INTO source_id, stamp
            FROM erev.subledger_posting_commit
            WHERE tenant_id = erev.current_tenant_id() AND subledger_posting_id = p_posting;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'EREV-HIS-001: Original posting commit evidence is unavailable';
            END IF;
            IF stamp IS NOT NULL THEN RETURN stamp; END IF;
            IF current_setting('track_commit_timestamp') <> 'on' THEN
                RAISE EXCEPTION 'EREV-HIS-001: PostgreSQL commit timestamp tracking is required';
            END IF;
            state := pg_xact_status(source_id::xid8);
            IF state = 'in progress' THEN RETURN NULL; END IF;
            -- xid8 preserves the epoch for status checks; pg_commit_ts takes the 32-bit xid.
            -- Never consult a recycled low xid once the full transaction status has expired.
            IF state IS DISTINCT FROM 'committed' THEN
                RAISE EXCEPTION 'EREV-HIS-001: Original transaction commit evidence has expired';
            END IF;
            stamp := pg_xact_commit_timestamp(mod(source_id::numeric, 4294967296)::text::xid);
            IF stamp IS NULL THEN
                RAISE EXCEPTION 'EREV-HIS-001: Transaction commit timestamp is unavailable';
            END IF;
            RETURN stamp;
        END $$
    """)
    ops.execute("REVOKE ALL ON FUNCTION erev.subledger_commit_time(uuid) FROM PUBLIC")
    ops.execute("GRANT EXECUTE ON FUNCTION erev.subledger_commit_time(uuid) TO erev_app")
    ops.execute("""
        CREATE FUNCTION erev.tg_subledger_commit__stamp() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NOT EXISTS (SELECT 1 FROM erev.subledger_posting_seal
                    WHERE tenant_id = NEW.tenant_id
                        AND subledger_posting_id = NEW.subledger_posting_id) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: A complete posting seal is required';
                END IF;
                NEW.source_transaction := pg_current_xact_id()::text;
                NEW.committed_server_at := NULL;
            ELSE
                IF OLD.committed_server_at IS NOT NULL THEN
                    RAISE EXCEPTION 'EREV-IMM-001: Commit evidence is immutable';
                END IF;
                IF NEW.committed_server_at IS NULL OR NEW.committed_server_at IS DISTINCT FROM
                    erev.subledger_commit_time(OLD.subledger_posting_id) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: Commit evidence must match PostgreSQL';
                END IF;
            END IF;
            RETURN NEW;
        END $$
    """)
    ops.execute("REVOKE ALL ON FUNCTION erev.tg_subledger_commit__stamp() FROM PUBLIC")
    ops.execute("""
        CREATE TRIGGER tg_subledger_commit__stamp BEFORE INSERT OR UPDATE
        ON erev.subledger_posting_commit FOR EACH ROW
        EXECUTE FUNCTION erev.tg_subledger_commit__stamp()
    """)
    ops.execute("""
        CREATE FUNCTION erev.capture_subledger_commit(p_posting uuid) RETURNS timestamptz
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        DECLARE stamp timestamptz;
        BEGIN
            stamp := erev.subledger_commit_time(p_posting);
            IF stamp IS NOT NULL THEN
                UPDATE erev.subledger_posting_commit SET committed_server_at = stamp
                WHERE tenant_id = erev.current_tenant_id() AND subledger_posting_id = p_posting
                    AND committed_server_at IS NULL;
            END IF;
            RETURN stamp;
        END $$
    """)
    ops.execute("REVOKE ALL ON FUNCTION erev.capture_subledger_commit(uuid) FROM PUBLIC")
    ops.execute("GRANT EXECUTE ON FUNCTION erev.capture_subledger_commit(uuid) TO erev_app")

    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = "  # noqa: S608 — static release metadata
        "jsonb_set(jsonb_set(ipe_logic, '{filters}', (ipe_logic->'filters') || to_jsonb('"
        + NOTE
        + "'::text)), '{source_tables}', (ipe_logic->'source_tables') || "
        "to_jsonb('subledger_posting_commit'::text)) WHERE version=1 AND code IN (" + CODES + ")"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = '"  # noqa: S608 — frozen release metadata
        + NEW_DISAGGREGATION.replace("'", "''")
        + "'::jsonb WHERE code='disaggregation' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = "  # noqa: S608 — static release metadata
        "jsonb_set(jsonb_set(ipe_logic, '{filters}', (ipe_logic->'filters') - '"
        + NOTE
        + "'), '{source_tables}', (ipe_logic->'source_tables') - "
        "'subledger_posting_commit') WHERE version=1 AND code IN (" + CODES + ")"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic = '"  # noqa: S608 — frozen release metadata
        + OLD_DISAGGREGATION.replace("'", "''")
        + "'::jsonb WHERE code='disaggregation' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")
    ops.execute("DROP TRIGGER zz_subledger_seal__commit_queue ON erev.subledger_posting_seal")
    ops.execute("DROP FUNCTION erev.tg_subledger_commit__queue()")
    ops.execute("DROP FUNCTION erev.capture_subledger_commit(uuid)")
    ops.drop_tenant_table("subledger_posting_commit")
    ops.execute("DROP FUNCTION erev.tg_subledger_commit__stamp()")
    ops.execute("DROP FUNCTION erev.subledger_commit_time(uuid)")
