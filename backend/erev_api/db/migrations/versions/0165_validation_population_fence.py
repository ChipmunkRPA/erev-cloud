"""Fence population writes during the final release-validation transaction."""

from erev_api.db import migration_ops as ops

revision = "0165"
down_revision = "0164"
branch_labels = None
depends_on = None

# Every table read by validation_population.read, including append-only evidence and
# partitioned roots. PostgreSQL clones row triggers onto existing and future partitions.
TABLES = (
    "book",
    "combination_group",
    "combination_group_member",
    "contract",
    "contract_event",
    "contract_version",
    "obligation_version",
    "period",
    "period_state",
    "subledger_line",
    "subledger_posting",
    "subledger_posting_seal",
)
BODY = """
DECLARE
  scope_id uuid;
BEGIN
  IF TG_OP = 'DELETE' THEN
    scope_id := OLD.tenant_id;
  ELSE
    scope_id := NEW.tenant_id;
  END IF;
  IF NOT pg_try_advisory_xact_lock_shared(
    hashtextextended('erev:validation-population:' || scope_id::text, 0)) THEN
    RAISE EXCEPTION USING ERRCODE = '55P03',
      MESSAGE = 'Release validation is checking this tenant population; retry the transaction';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END
"""


def upgrade() -> None:
    for table in TABLES:
        ops.create_trigger(
            table,
            "validation_population",
            BODY,
            timing="BEFORE",
            events="INSERT OR UPDATE OR DELETE",
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        name = f"tg_{table}__validation_population"
        ops.execute(f"DROP TRIGGER {name} ON erev.{table}")
        ops.execute(f"DROP FUNCTION erev.{name}()")
