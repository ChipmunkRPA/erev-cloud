"""Database sealing time prevents historical cutoffs from splitting a posting."""

from erev_api.db import migration_ops as ops

revision = "0152"
down_revision = "0151"
branch_labels = None
depends_on = None


def _require_empty() -> None:
    # A historical completion instant cannot be reconstructed from application timestamps.
    # Validation sees physical rows even when forced RLS hides them from the migration owner.
    ops.execute(
        "ALTER TABLE erev.subledger_posting_seal ADD CONSTRAINT ck_subledger_seal__0152_empty "
        "CHECK (false) NOT VALID"
    )
    ops.execute(
        "ALTER TABLE erev.subledger_posting_seal VALIDATE CONSTRAINT ck_subledger_seal__0152_empty"
    )
    ops.execute(
        "ALTER TABLE erev.subledger_posting_seal DROP CONSTRAINT ck_subledger_seal__0152_empty"
    )


def upgrade() -> None:
    _require_empty()
    ops.execute(
        "ALTER TABLE erev.subledger_posting_seal ADD COLUMN sealed_server_at timestamptz "
        "NOT NULL DEFAULT clock_timestamp()"
    )
    ops.execute("""
        CREATE FUNCTION erev.tg_subledger_seal__server_time() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, erev AS $$
        BEGIN
            NEW.sealed_server_at := clock_timestamp();
            RETURN NEW;
        END $$
    """)
    ops.execute("REVOKE ALL ON FUNCTION erev.tg_subledger_seal__server_time() FROM PUBLIC")
    # Follow the balance/chain guard, including any wait for the ledger chain-head lock.
    ops.execute("""
        CREATE TRIGGER zz_subledger_seal__server_time BEFORE INSERT ON erev.subledger_posting_seal
        FOR EACH ROW EXECUTE FUNCTION erev.tg_subledger_seal__server_time()
    """)


def downgrade() -> None:
    _require_empty()
    ops.execute("DROP TRIGGER zz_subledger_seal__server_time ON erev.subledger_posting_seal")
    ops.execute("DROP FUNCTION erev.tg_subledger_seal__server_time()")
    ops.execute("ALTER TABLE erev.subledger_posting_seal DROP COLUMN sealed_server_at")
