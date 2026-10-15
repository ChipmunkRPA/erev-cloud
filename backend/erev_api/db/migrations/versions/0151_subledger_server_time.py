"""Server insertion time for historical ledger reads; never rewrite sealed rows."""

from erev_api.db import migration_ops as ops

revision = "0151"
down_revision = "0150"
branch_labels = None
depends_on = None


def _require_empty() -> None:
    # Constraint validation sees physical rows even under forced tenant RLS.
    # A column changes the canonical sealed line document in both directions.
    ops.execute(
        "ALTER TABLE erev.subledger_line ADD CONSTRAINT ck_subledger_line__0151_empty "
        "CHECK (false) NOT VALID"
    )
    ops.execute("ALTER TABLE erev.subledger_line VALIDATE CONSTRAINT ck_subledger_line__0151_empty")
    ops.execute("ALTER TABLE erev.subledger_line DROP CONSTRAINT ck_subledger_line__0151_empty")


def upgrade() -> None:
    _require_empty()
    ops.execute(
        "ALTER TABLE erev.subledger_line ADD COLUMN recorded_server_at timestamptz "
        "NOT NULL DEFAULT clock_timestamp()"
    )
    ops.execute("""
        CREATE FUNCTION erev.tg_subledger_line__server_time() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, erev AS $$
        BEGIN
            NEW.recorded_server_at := clock_timestamp();
            RETURN NEW;
        END $$
    """)
    ops.execute("REVOKE ALL ON FUNCTION erev.tg_subledger_line__server_time() FROM PUBLIC")
    # Run after the existing period guard, including any wait on its row lock.
    ops.execute("""
        CREATE TRIGGER zz_subledger_line__server_time BEFORE INSERT ON erev.subledger_line
        FOR EACH ROW EXECUTE FUNCTION erev.tg_subledger_line__server_time()
    """)


def downgrade() -> None:
    _require_empty()
    ops.execute("DROP TRIGGER zz_subledger_line__server_time ON erev.subledger_line")
    ops.execute("DROP FUNCTION erev.tg_subledger_line__server_time()")
    ops.execute("ALTER TABLE erev.subledger_line DROP COLUMN recorded_server_at")
