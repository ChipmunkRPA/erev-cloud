"""BUILD_SPEC item SOP-5 (05 PRV-07 a ``user.anonymise``): the DB-13 grant of ``app_user.email``
/ ``external_id`` and the DB-19 erasure guard (04 rev 1.86, docs first by lane P8; this code
step and the §15.2 binding of rev 1.96 by lane FIX-D2).

04 ids amended / created: §14.2 DB-13 ``app_user`` — ``erev_app``'s UPDATE grant gains exactly
``email`` and ``external_id``, the two columns ``erev_api.domain.platform.privacy.anonymise_user``
rewrites and the rev 1.2 grant of 0004 never admitted (the command failed closed with SQLSTATE
42501 → 403 ``forbidden`` at its acting-tenant UPDATE); §14.1 DB-19
``tg_app_user__erasure_guard`` ``BEFORE UPDATE OF email, external_id … FOR EACH ROW`` — the
compensating control of that grant (supervisor ruling of 2026-09-22: path (i) with a guard;
SECURITY DEFINER rejected): a change of either column is admitted only when, in the same UPDATE,
``NEW.email = 'erased+' || NEW.id::text || '@invalid.erev' AND NEW.external_id IS NULL AND
NEW.status = 'DISABLED'`` holds — the erased form (``privacy.erased_email``; Python ``str(UUID)``
equals ``uuid::text``), the cleared external id and the disabled status together — and any other
change of either column is refused by name, ``EREV-PRV-001`` (403 ``forbidden``, 04 §15.2), so a
defect running as ``erev_app`` cannot repoint a login e-mail. A SET that leaves both columns at
their stored values is not a change. The trigger fires for every role; its message names the row
and never a value of either column (both are personal data, 05 PRV-01).

The guard is installed before the grant and the downgrade revokes the grant before it drops the
guard (DG-MIG-04: exactly what ``upgrade()`` created, in reverse order), so the two columns are
never updatable without it. One erev function is added (``tests/pg/test_migrations.py`` counts
it): SECURITY INVOKER with ``search_path`` pinned and EXECUTE granted to ``erev_app`` by
``create_trigger`` (NC-18; DB-14 (h)). Revision 0073 on 0072, assigned by the supervisor (04 §18
rule 9). A revision reads no live Python constant (DG-MIG-12): the role name is a literal (the
0059 / 0065 precedent).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None

TABLE: Final = "app_user"
PURPOSE: Final = "erasure_guard"
# The schema's application role (04 §14.2; ``erev_api.db.session.APP_ROLE`` at this revision's
# authoring state) as a literal.
APP_ROLE: Final = "erev_app"
COLUMNS: Final = "email, external_id"

# DB-19 (04 §14.1 rev 1.86): the ruling's predicate, verbatim; ``IS NOT TRUE`` so that a predicate
# that does not evaluate to true — including NULL — refuses.
GUARD_BODY: Final = """
BEGIN
  IF (NEW.email IS DISTINCT FROM OLD.email OR NEW.external_id IS DISTINCT FROM OLD.external_id)
     AND (NEW.email = 'erased+' || NEW.id::text || '@invalid.erev'
          AND NEW.external_id IS NULL
          AND NEW.status = 'DISABLED') IS NOT TRUE THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-PRV-001: email and external_id of %I.%I row %s change only in the '
                       'erased form of user.anonymise',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id);
  END IF;
  RETURN NEW;
END
"""


def upgrade() -> None:
    """DB-19 first, then the §14.2 grant it compensates (DG-MIG-11: the explicit row)."""
    ops.create_trigger(TABLE, PURPOSE, GUARD_BODY, timing="BEFORE", events=f"UPDATE OF {COLUMNS}")
    ops.execute(f"GRANT UPDATE ({COLUMNS}) ON TABLE erev.{TABLE} TO {APP_ROLE}")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute(f"REVOKE UPDATE ({COLUMNS}) ON TABLE erev.{TABLE} FROM {APP_ROLE}")
    ops.execute(f"DROP TRIGGER tg_{TABLE}__{PURPOSE} ON erev.{TABLE}")
    ops.execute(f"DROP FUNCTION erev.tg_{TABLE}__{PURPOSE}()")
