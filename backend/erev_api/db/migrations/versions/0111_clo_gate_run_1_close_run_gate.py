"""Item CLO-GATE-RUN-1 (supervisor rulings R-114 (b) and R-116 (e) of 2026-09-30; number assigned
by the supervisor): the lock's fourteenth gate and the mark of a contract group's period ends.

04 ids amended (rev 1.172):

- T-CLS-02 ``gate_check_code`` gains ``CLOSE_RUN_COMPLETED``, the thirteenth system gate; the
  certification stays the last. ``ck_close_checklist_template__gate_check_code`` is replaced with
  the list of revision 0047 plus that literal, in T-CLS-02 order.
- T-CON-03 ``combination_group.period_ends_open`` — ``jsonb NOT NULL DEFAULT '{}'``, an object
  (``ck_combination_group__period_ends_open``) with one member per ``"<entity code>|<book>"``:
  the date before which the group's period-end amounts of that entity and book are posted. The
  application role gains UPDATE on the column, and the DB-03 function
  ``tg_combination_group__transition()`` (installed by 0038) is replaced with the fresh rendering
  that names the column among those the application may move (``CREATE OR REPLACE FUNCTION``;
  grants and trigger kept — the 0065 / 0069 / 0093 precedent), so DG-ARC-07 (installed source ==
  fresh rendering) holds.

No row is written (DG-MIG-07: tenant data is never seeded by a migration). The gate's checklist
template is seeded by provisioning (``SYSTEM_CLOSE_GATES``): a database seeded before this
revision enforces the gate — the lock decision reads the evaluated results, not the checklist —
and lacks the checklist line until it is seeded again. No workspace is deployed; a system gate
added after a first deployment needs a seeding step of its own (known limitation
CLOSE-GATE-SEED-1). Rows of ``combination_group`` that predate the column take the default: no
entry, which the gate reads as not posted for a group of the entity (04 §16.8 rev 1.228; item
CLO-GATE-RUN-2 — a run's first period-end step can leave a group out).

The downgrade restores the 0038 function body verbatim, revokes the column grant, drops the
check and the column, and restores the gate list of revision 0047 (DG-MIG-04). A provisioned
tenant holds the template row of ``CLOSE_RUN_COMPLETED``, which that list does not admit, so the
list comes back ``NOT VALID`` and is validated in the same transaction (dev-guide DG-MIG-13, the
form of 0084 and 0103, here for a downgrade): on a database without such a row it ends validated;
over one that holds such rows the violation is caught inside the block, the constraint stays
``NOT VALID`` — enforced for every row written from then on — a NOTICE names the revision
(``EREV-MIG-0111``) and the walk continues. No row is deleted or rewritten and row-level
security is untouched: the owner connection does not see tenant rows (FORCE ROW LEVEL SECURITY),
so a DELETE here would remove nothing, and a guard deletes nothing in any case. Corrected in
place (PRODUCT DEFECT of this revision; the supervisor's message of 2026-10-01 13:32; nothing is
deployed): until then the downgrade re-added the list validated and failed with a bare
``check_violation`` on every populated database, which stopped every walk down through this
revision — the downgrade witnesses of 0067 and 0084 among them.

What the application of the earlier revision does with the rows that stay — measured on main
15ccedb6, whose Alembic head is 0108, over a tenant's kept template row and a period's item of it
that held ``FAILED``, "Close run not completed". It evaluates thirteen gates and has no result
for the kept one, so the item keeps the status it holds: the cockpit answers 200 and lists the
line as it stands — blocking, ``FAILED`` — before and after the lock. Its lock request and its
lock decision read their own thirteen results and no checklist item of an automatic gate: the
request was accepted, the decision approved, the period ``closed`` on a certification of
thirteen codes, and the item was still ``FAILED`` afterwards. The kept rows therefore stop no
lock of the earlier application; they leave a checklist line that application never evaluates
or clears, on a period it may lock all the same. Nothing but the upgrade restores the gate.

No table, type or function is added: the erev function count is unchanged. A revision imports
nothing of ``erev_api`` beyond the DDL helpers (DG-MIG-12): the literals and both bodies are
written out. ``down_revision`` was main's head at each of the lane's merges of main (0102 when
written, 0113 at da2ce39e, 0086 at 965ed2bd; supervisor ruling R-68 (e)) and is main's head 0108
since the supervisor's merge of the lane.
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0111"
down_revision = "0108"
branch_labels = None
depends_on = None

TEMPLATE_TABLE: Final = "close_checklist_template"
GATE_CHECK: Final = "ck_close_checklist_template__gate_check_code"
# 04 T-CLS-02 ``gate_check_code``: the list of revision 0047, then with the literal of rev 1.172
# in its T-CLS-02 place.
PREVIOUS_GATE_CHECK_CODES: Final = (
    "INTERFACES_COMPLETE",
    "JE_BALANCED",
    "JE_COMPLETE",
    "APPROVALS_CLEARED",
    "EXCEPTIONS_CLEARED",
    "HOLDS_REVIEWED",
    "BATCHES_ACKNOWLEDGED",
    "RECONCILIATIONS_GENERATED",
    "JUDGEMENTS_REVIEWED",
    "DATA_QUALITY_CLEAR",
    "NO_DIRTY_GROUPS",
    "MANUAL_ADJUSTMENTS_CLEARED",
    "CONTROLLER_CERTIFIED",
)
GATE_CHECK_CODES: Final = (
    *PREVIOUS_GATE_CHECK_CODES[:-1],
    "CLOSE_RUN_COMPLETED",
    PREVIOUS_GATE_CHECK_CODES[-1],
)

GROUP_TABLE: Final = "combination_group"
COLUMN: Final = "period_ends_open"
COLUMN_CHECK: Final = "ck_combination_group__period_ends_open"
APP_ROLE: Final = "erev_app"

BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'criterion', 'dirty_since', 'head_computation_id', 'inception_date', 'judgement_record_id', 'period_ends_open', 'rationale', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>APPLIED', 'PROPOSED>SUBMITTED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

PREVIOUS: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'criterion', 'dirty_since', 'head_computation_id', 'inception_date', 'judgement_record_id', 'rationale', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>APPLIED', 'PROPOSED>SUBMITTED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


# DG-MIG-13: the validation scans every physical row whatever row-level security hides from the
# owner connection. A constant statement (no interpolation). A template row of the gate this
# revision added does not satisfy the restored list: the check_violation is caught INSIDE the
# block, so the constraint stays NOT VALID — enforced for every new row — and the downgrade
# continues; nothing is deleted or rewritten.
VALIDATE_PREVIOUS_GATE_CHECK: Final = """
DO $$
BEGIN
  ALTER TABLE erev.close_checklist_template
    VALIDATE CONSTRAINT ck_close_checklist_template__gate_check_code;
EXCEPTION
  WHEN check_violation THEN
    RAISE NOTICE 'EREV-MIG-0111: close_checklist_template holds rows of the gate '
                 'CLOSE_RUN_COMPLETED, seeded after revision 0111; they are kept and '
                 'ck_close_checklist_template__gate_check_code stays NOT VALID (it is enforced '
                 'for every row written from this downgrade on). The application of the '
                 'earlier revision evaluates thirteen gates: it lists the kept gate with the '
                 'status its checklist item holds, never evaluates it, and locks a period '
                 'without it. Upgrade again to restore the gate';
END
$$;
"""


def _replace_gate_check(codes: tuple[str, ...], *, not_valid: bool = False) -> None:
    listed = ", ".join(f"'{code}'" for code in codes)
    ops.execute(f"ALTER TABLE erev.{TEMPLATE_TABLE} DROP CONSTRAINT {GATE_CHECK}")
    ops.execute(
        f"ALTER TABLE erev.{TEMPLATE_TABLE} ADD CONSTRAINT {GATE_CHECK} "
        "CHECK ((gate_kind <> 'AUTOMATIC' OR gate_check_code IS NOT NULL) "
        f"AND (gate_check_code IS NULL OR gate_check_code IN ({listed})))"
        + (" NOT VALID" if not_valid else "")
    )


def _replace_function(body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes) — the
    0069 helper, verbatim in shape (SECURITY INVOKER, search_path pinned, $fn$ quoting)."""
    if "$fn$" in body:
        raise ValueError("a trigger function body must not contain $fn$")
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.tg_{GROUP_TABLE}__transition() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    """The gate literal, the column with its check and grant, and the function that lets the
    application move it (04 T-CLS-02 and T-CON-03 rev 1.172)."""
    _replace_gate_check(GATE_CHECK_CODES)
    ops.execute(
        f"ALTER TABLE erev.{GROUP_TABLE} ADD COLUMN {COLUMN} jsonb NOT NULL DEFAULT '{{}}'::jsonb"
    )
    ops.execute(
        f"ALTER TABLE erev.{GROUP_TABLE} ADD CONSTRAINT {COLUMN_CHECK} "
        f"CHECK (jsonb_typeof({COLUMN}) = 'object')"
    )
    ops.execute(f"GRANT UPDATE ({COLUMN}) ON TABLE erev.{GROUP_TABLE} TO {APP_ROLE}")
    _replace_function(BODY)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04). The gate list of 0047
    is restored ``NOT VALID`` and validated in a block that keeps the template rows of the gate
    this revision added (DG-MIG-13; module docstring)."""
    _replace_function(PREVIOUS)
    ops.execute(f"REVOKE UPDATE ({COLUMN}) ON TABLE erev.{GROUP_TABLE} FROM {APP_ROLE}")
    ops.execute(f"ALTER TABLE erev.{GROUP_TABLE} DROP CONSTRAINT {COLUMN_CHECK}")
    ops.execute(f"ALTER TABLE erev.{GROUP_TABLE} DROP COLUMN {COLUMN}")
    _replace_gate_check(PREVIOUS_GATE_CHECK_CODES, not_valid=True)
    ops.execute(VALIDATE_PREVIOUS_GATE_CHECK)
