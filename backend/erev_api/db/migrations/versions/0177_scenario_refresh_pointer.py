"""Allow scenario refresh to replace the sandbox pointer (FCS-2 / SBX-09).

The new target must still be a sandbox sourced from the same production tenant.
This removes an unintended restriction; it does not enable a refresh workflow.
"""

from erev_api.db import migration_ops as ops

revision = "0177"
down_revision = "0176"
branch_labels = None
depends_on = None

OLD_BODY = """
BEGIN
  IF NOT EXISTS (SELECT 1 FROM erev.tenant WHERE id = NEW.tenant_id AND kind = 'production')
     OR NOT EXISTS (SELECT 1 FROM erev.tenant WHERE id = NEW.scenario_tenant_id
       AND kind = 'sandbox' AND source_tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'Scenario must link production to its own sandbox' USING ERRCODE = '23514';
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.scenario_tenant_id IS DISTINCT FROM OLD.scenario_tenant_id THEN
    RAISE EXCEPTION 'Scenario tenant is immutable' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
"""

NEW_BODY = """
BEGIN
  IF NOT EXISTS (SELECT 1 FROM erev.tenant WHERE id = NEW.tenant_id AND kind = 'production')
     OR NOT EXISTS (SELECT 1 FROM erev.tenant WHERE id = NEW.scenario_tenant_id
       AND kind = 'sandbox' AND source_tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'Scenario must link production to its own sandbox' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
"""


def _replace(body: str) -> None:
    ops.execute("DROP TRIGGER tg_scenario__scope ON erev.scenario")
    ops.execute("DROP FUNCTION erev.tg_scenario__scope()")
    ops.create_trigger("scenario", "scope", body, timing="BEFORE", events="INSERT OR UPDATE")


def upgrade() -> None:
    _replace(NEW_BODY)


def downgrade() -> None:
    _replace(OLD_BODY)
