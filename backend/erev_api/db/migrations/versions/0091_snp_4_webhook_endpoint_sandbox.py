"""BUILD_SPEC item SNP-4 (05 §10 SBX-08 rev 1.64; 04 §14.1 DB-15 rev 1.125): the DB-15 trigger of
``webhook_endpoint`` — security finding SF-1, supervisor ruling R-33.

04 ids amended / created: §14.1 DB-15 gains ``tg_webhook_endpoint__sandbox`` on the T-PLT-35
table of revision 0021, ``BEFORE INSERT OR UPDATE … FOR EACH ROW``: in a tenant of kind
``sandbox`` a row cannot BECOME active — an INSERT with ``is_active = true`` and an UPDATE that
turns ``is_active`` from false to true raise ``EREV-SBX-001`` (403 ``sandbox-restricted``, 04
§15.2). A row that is not active, and an UPDATE of a row that was active before it, pass: the
trigger refuses the activation, as ``tg_integration_connection__sandbox`` of revision 0072
refuses the transition and not the state. The tenant kind is read as the invoker (SECURITY
INVOKER under RLS-TN), the 0046 / 0072 precedent.

It is the third of the three layers of SBX-08 and the last one: the command guard
``domain.platform.guards.ensure_production`` refuses the creation and the activation first and
audits the attempt, and ``events.webhooks`` emits and delivers nothing from a sandbox whatever the
rows say. Before this revision no landed revision guarded the table (0021 holds only the
delivery transition trigger) although SBX-08 forbade the activation, and the API created an
ACTIVE endpoint in a sandbox (the reviewer's proof, reproduced by the lane).

One erev function is added (``tests/pg/test_migrations.py`` counts it): SECURITY INVOKER with
``search_path`` pinned and EXECUTE granted to ``erev_app`` by ``create_trigger`` (NC-18; DB-14
(h)). No table, column, grant or enum; no data step — nothing was ever deployed (D-99), and the
emission and delivery paths do not depend on the stored flag. ``downgrade()`` drops exactly what
``upgrade()`` created (DG-MIG-04).

Revision 0091, the number the register gave the lane, on 0085 — main's head when the lane last
merged main (supervisor ruling R-68 (e): the chain follows merge order, not number order; 04 §18
rule 13; built on 0095 and re-pointed at each merge of main, to 0087, to 0092 and then to 0085).
A revision reads no live Python constant (DG-MIG-12).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0091"
down_revision = "0085"
branch_labels = None
depends_on = None

TABLE: Final = "webhook_endpoint"
PURPOSE: Final = "sandbox"

# DB-15 (04 §14.1 rev 1.125): in a sandbox tenant an endpoint cannot become active.
ENDPOINT_SANDBOX_BODY: Final = """
DECLARE
  tenant_kind text;
BEGIN
  IF NOT NEW.is_active THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.is_active THEN
    RETURN NEW;
  END IF;
  SELECT t.kind::text INTO tenant_kind FROM erev.tenant t WHERE t.id = NEW.tenant_id;
  IF tenant_kind = 'sandbox' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-SBX-001: webhook endpoint %s of a sandbox tenant cannot be active; '
                       'a sandbox sends no webhooks',
                       NEW.id);
  END IF;
  RETURN NEW;
END
"""


def upgrade() -> None:
    ops.create_trigger(
        TABLE, PURPOSE, ENDPOINT_SANDBOX_BODY, timing="BEFORE", events="INSERT OR UPDATE"
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created (DG-MIG-04)."""
    ops.execute(f"DROP TRIGGER tg_{TABLE}__{PURPOSE} ON erev.{TABLE}")
    ops.execute(f"DROP FUNCTION erev.tg_{TABLE}__{PURPOSE}()")
