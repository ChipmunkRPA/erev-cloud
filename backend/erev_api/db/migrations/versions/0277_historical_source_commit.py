"""Retain original commit evidence for contract events and computed versions."""

import json

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0277"
down_revision = "0276"
branch_labels = None
depends_on = None


NOTE = (
    "historical_source_commit_v1 retains original event and contract-version "
    "transaction commits; new event/version extracts and BBR event sources use "
    "commit cutoffs; historical version populations exclude later commits before "
    "latest selection; bound inputs keep their original interpretation"
)

INCREMENTAL = (
    "mode INCREMENTAL: original source transaction committed after known_since and "
    "at or before known_at; old bound extracts preserve their original record or "
    "creation time basis"
)

OLD_INCREMENTAL = (
    "mode INCREMENTAL: rows created (recorded for events and subledger lines) after"
    " known_since and at or before the source time"
)

CODES = (
    "adoption_bridge",
    "allocations_by_ssp_version",
    "balance_aging",
    "book_bridge",
    "bookings_billings_revenue",
    "contract_balance_rollforward",
    "contract_balances",
    "contract_cost_rollforward",
    "contract_history",
    "estimate_change_listing",
    "extract_balances",
    "extract_contract_versions",
    "extract_events",
    "extract_obligations",
    "extract_schedule_lines",
    "latest_contract_status",
    "loss_provision_register",
    "modification_register",
    "revenue_from_opening_liability",
    "revenue_from_prior_period_obligations",
    "revenue_waterfall",
    "rpo",
    "rpo_rollforward",
    "scope_exclusion_register",
    "ssp_override_listing",
)


def _metadata(*, undo: bool) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    note = NOTE.replace("'", "''")
    for code in CODES:
        filters = (
            "(ipe_logic->'filters') - '" + note + "'"
            if undo
            else ("(ipe_logic->'filters') || to_jsonb('" + note + "'::text)")
        )
        sources = (
            "(ipe_logic->'source_tables') - 'historical_source_commit'"
            if undo
            else ("(ipe_logic->'source_tables') || to_jsonb('historical_source_commit'::text)")
        )
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic = "  # noqa: S608 — frozen metadata
            "jsonb_set(jsonb_set(ipe_logic, '{filters}', "
            + filters
            + "), '{source_tables}', "
            + sources
            + ") WHERE code='"
            + code
            + "' AND version=1"
        )
    before, after = (INCREMENTAL, OLD_INCREMENTAL) if undo else (OLD_INCREMENTAL, INCREMENTAL)
    before_json = json.dumps(before).replace("'", "''")
    after_json = json.dumps(after).replace("'", "''")
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "  # noqa: S608
        "(SELECT jsonb_agg(CASE WHEN value='"
        + before_json
        + "'::jsonb THEN '"
        + after_json
        + "'::jsonb ELSE value END ORDER BY ordinal) FROM "
        "jsonb_array_elements(ipe_logic->'filters') WITH ORDINALITY AS f(value, ordinal))) "
        "WHERE code IN ('extract_events','extract_contract_versions') AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    # No live-data migration is in scope; do not fabricate pre-upgrade commits.
    for source in ("contract_event", "contract_version"):
        ops.execute(
            f"ALTER TABLE erev.{source} ADD CONSTRAINT ck_source__0277_empty "
            "CHECK (false) NOT VALID"
        )
        ops.execute(f"ALTER TABLE erev.{source} VALIDATE CONSTRAINT ck_source__0277_empty")
        ops.execute(f"ALTER TABLE erev.{source} DROP CONSTRAINT ck_source__0277_empty")
    ops.create_tenant_table(
        "historical_source_commit",
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_transaction", sa.Text(), nullable=False),
        sa.Column("committed_server_at", sa.DateTime(timezone=True), nullable=True),
        include_id=False,
        primary_key=["tenant_id", "source_kind", "source_id"],
        checks=[
            (
                "ck_historical_source_commit__kind",
                "source_kind IN ('contract_event', 'contract_version')",
            ),
            ("ck_historical_source_commit__transaction", "source_transaction ~ '^[0-9]+$'"),
        ],
    )
    ops.apply_class("historical_source_commit", "IM-S", update_columns=["committed_server_at"])
    ops.enable_rls("historical_source_commit", "RLS-T")
    ops.execute(
        "CREATE INDEX ix_historical_source_commit__pending ON "
        "erev.historical_source_commit (tenant_id, source_kind, source_id) "
        "WHERE committed_server_at IS NULL"
    )
    ops.execute("""
        CREATE FUNCTION erev.tg_source_commit__queue() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        BEGIN
            IF current_setting('track_commit_timestamp') <> 'on' THEN
                RAISE EXCEPTION 'EREV-HIS-001: PostgreSQL commit timestamp tracking is required';
            END IF;
            INSERT INTO erev.historical_source_commit
                (tenant_id, source_kind, source_id, source_transaction)
            VALUES (NEW.tenant_id, TG_TABLE_NAME, NEW.id, pg_current_xact_id()::text);
            RETURN NEW;
        END $$
    """)
    ops.execute("REVOKE ALL ON FUNCTION erev.tg_source_commit__queue() FROM PUBLIC")
    for source in ("contract_event", "contract_version"):
        ops.execute(
            f"CREATE TRIGGER zz_source__commit_queue AFTER INSERT ON erev.{source} "
            "FOR EACH ROW EXECUTE FUNCTION erev.tg_source_commit__queue()"
        )
    ops.execute("""
        CREATE FUNCTION erev.source_commit_time(p_kind text, p_source uuid) RETURNS timestamptz
        LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        DECLARE source_tx text; stamp timestamptz; state text;
        BEGIN
            SELECT source_transaction, committed_server_at INTO source_tx, stamp
            FROM erev.historical_source_commit
            WHERE tenant_id = erev.current_tenant_id()
                AND source_kind = p_kind AND source_id = p_source;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'EREV-HIS-001: Original source commit evidence is unavailable';
            END IF;
            IF stamp IS NOT NULL THEN RETURN stamp; END IF;
            IF current_setting('track_commit_timestamp') <> 'on' THEN
                RAISE EXCEPTION 'EREV-HIS-001: PostgreSQL commit timestamp tracking is required';
            END IF;
            state := pg_xact_status(source_tx::xid8);
            IF state = 'in progress' THEN RETURN NULL; END IF;
            -- xid8 preserves the epoch for status checks; pg_commit_ts takes the 32-bit xid.
            -- Never consult a recycled low xid once the full transaction status has expired.
            IF state IS DISTINCT FROM 'committed' THEN
                RAISE EXCEPTION 'EREV-HIS-001: Original transaction commit evidence has expired';
            END IF;
            stamp := pg_xact_commit_timestamp(mod(source_tx::numeric, 4294967296)::text::xid);
            IF stamp IS NULL THEN
                RAISE EXCEPTION 'EREV-HIS-001: Transaction commit timestamp is unavailable';
            END IF;
            RETURN stamp;
        END $$
    """)
    ops.execute("REVOKE ALL ON FUNCTION erev.source_commit_time(text, uuid) FROM PUBLIC")
    ops.execute("GRANT EXECUTE ON FUNCTION erev.source_commit_time(text, uuid) TO erev_app")
    ops.execute("""
        CREATE FUNCTION erev.tg_source_commit__stamp() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NOT (
                    (NEW.source_kind = 'contract_event' AND EXISTS (
                        SELECT 1 FROM erev.contract_event
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'contract_version' AND EXISTS (
                        SELECT 1 FROM erev.contract_version
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
    """)
    ops.execute("REVOKE ALL ON FUNCTION erev.tg_source_commit__stamp() FROM PUBLIC")
    ops.execute("""
        CREATE TRIGGER tg_source_commit__stamp BEFORE INSERT OR UPDATE
        ON erev.historical_source_commit FOR EACH ROW
        EXECUTE FUNCTION erev.tg_source_commit__stamp()
    """)
    ops.execute("""
        CREATE FUNCTION erev.capture_source_commit(p_kind text, p_source uuid) RETURNS timestamptz
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        DECLARE stamp timestamptz;
        BEGIN
            stamp := erev.source_commit_time(p_kind, p_source);
            IF stamp IS NOT NULL THEN
                UPDATE erev.historical_source_commit SET committed_server_at = stamp
                WHERE tenant_id = erev.current_tenant_id()
                AND source_kind = p_kind AND source_id = p_source
                    AND committed_server_at IS NULL;
            END IF;
            RETURN stamp;
        END $$
    """)
    ops.execute("REVOKE ALL ON FUNCTION erev.capture_source_commit(text, uuid) FROM PUBLIC")
    ops.execute("GRANT EXECUTE ON FUNCTION erev.capture_source_commit(text, uuid) TO erev_app")

    _metadata(undo=False)


def downgrade() -> None:
    _metadata(undo=True)
    for source in ("contract_event", "contract_version"):
        ops.execute(f"DROP TRIGGER zz_source__commit_queue ON erev.{source}")
    ops.execute("DROP FUNCTION erev.tg_source_commit__queue()")
    ops.execute("DROP FUNCTION erev.capture_source_commit(text, uuid)")
    ops.drop_tenant_table("historical_source_commit")
    ops.execute("DROP FUNCTION erev.tg_source_commit__stamp()")
    ops.execute("DROP FUNCTION erev.source_commit_time(text, uuid)")
