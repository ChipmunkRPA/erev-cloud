"""Freeze archived scenarios and forbid reactivation (SM-14)."""

from erev_api.db import migration_ops as ops

revision = "0178"
down_revision = "0177"
branch_labels = None
depends_on = None

TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF OLD.status::text = ANY (ARRAY['ARCHIVED']::text[]) THEN
    SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
      FROM jsonb_each(new_row) n
     WHERE n.key <> ALL (ARRAY['row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
       AND n.value IS DISTINCT FROM old_row -> n.key;
    IF changed IS NOT NULL THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change while status is %s',
                         changed, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status);
    END IF;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['base_known_at', 'last_refreshed_at', 'name', 'purpose', 'row_version', 'scenario_tenant_id', 'status', 'tenant_snapshot_id', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['ACTIVE>ARCHIVED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


OLD_SCOPE = """
BEGIN
  IF NOT EXISTS (SELECT 1 FROM erev.tenant WHERE id = NEW.tenant_id AND kind = 'production')
     OR NOT EXISTS (SELECT 1 FROM erev.tenant WHERE id = NEW.scenario_tenant_id
       AND kind = 'sandbox' AND source_tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'Scenario must link production to its own sandbox' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
"""

SCOPE = """
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.tenant_id = OLD.tenant_id
     AND NEW.scenario_tenant_id = OLD.scenario_tenant_id THEN
    RETURN NEW;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM erev.tenant WHERE id = NEW.tenant_id AND kind = 'production')
     OR NOT EXISTS (SELECT 1 FROM erev.tenant WHERE id = NEW.scenario_tenant_id
       AND kind = 'sandbox' AND source_tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'Scenario must link production to its own sandbox' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
"""


def _scope(body: str) -> None:
    ops.execute("DROP TRIGGER tg_scenario__scope ON erev.scenario")
    ops.execute("DROP FUNCTION erev.tg_scenario__scope()")
    ops.create_trigger("scenario", "scope", body, timing="BEFORE", events="INSERT OR UPDATE")


def upgrade() -> None:
    _scope(SCOPE)
    ops.create_trigger("scenario", "transition", TRANSITION_BODY, timing="BEFORE", events="UPDATE")


def downgrade() -> None:
    _scope(OLD_SCOPE)
    ops.execute("DROP TRIGGER tg_scenario__transition ON erev.scenario")
    ops.execute("DROP FUNCTION erev.tg_scenario__transition()")
