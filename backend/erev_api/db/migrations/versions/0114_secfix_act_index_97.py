"""Lane SECFIX-ACT, Alembic revision 0114 of register index 97, for the documents of register
index 119 (supervisor rulings R-118 (e), R-119 (e) and R-120 (e) and the supervisor's rulings of
2026-10-01; 04 rev 1.210 T-CON-06, T-CON-12, T-CON-13, E-12; PRD rev 1.139 SM-03, SM-04): what
the modification and estimate items share.

- ``modification.classification`` (item MOD-PREFILL-READ-1): what ``/classify`` answered as
  ``prefill_reasons``, kept so that a read answers it. jsonb, NULL until the row is classified
  and again after every edit, an object otherwise (``ck_modification__classification``).
  ``erev_app`` gains the column UPDATE grant (T-CON-06 is IM-S: editable while DRAFT).
- ``estimate_version.modification_id`` (item MOD-LINKED-ESTIMATES-1): the modification a version
  was created inside. Written by the INSERT and never changed: NO column UPDATE grant is added,
  so the application role cannot update it in any status. Composite foreign key to
  ``modification`` (NC-06) and the partial index ``ix_estimate_version__modification``.
- E-12 ``config_status`` gains ``VOIDED``, ``ck_estimate_version__status`` admits it, and the
  DB-03 function ``tg_estimate_version__transition()`` gains the pair (DRAFT, VOIDED) (item
  EST-DISCARD-1): a DRAFT estimate version is discarded. The check is re-created over the status
  as text: the label is added by this same revision, and PostgreSQL refuses a new enum value as
  an enum literal before the transaction commits (the 0060 precedent). The function body is
  REPLACED (``CREATE OR REPLACE``: grants and trigger kept — the 0065 / 0069 / 0093 precedent)
  with the fresh rendering of ``erev_api.db.transitions``, so DG-ARC-07 holds. No other table
  typed by E-12 changes: each keeps its own status check.
- ``ux_modification__reference`` (item MOD-DISCARD-1, the supervisor's ruling on the lane's
  question): the unique index of a modification's reference on its contract is re-created with
  the predicate ``reference IS NOT NULL AND NOT (status = 'VOIDED' AND applied_event_id IS
  NULL)`` — a discarded draft frees its reference, an applied modification that was voided keeps
  it. The downgrade re-creates the 0068 predicate and fails while a discarded draft shares its
  reference with another row.
- ``ix_estimate__contract (tenant_id, contract_id)`` (lane API-GAPS' finding F1): every read of
  a contract's estimated elements compares ``contract_id``, and the one key that held the
  contract, ``ux_estimate__code``, holds it inside ``coalesce(contract_id, portfolio_id)``, which
  no such comparison matches — the read entered by the tenant alone. Plain, not unique, no
  predicate; ``ux_estimate__code`` stays as it is.

The downgrade removes exactly that, in reverse order (DG-MIG-04): the 0069 body verbatim, the
two new indexes, the foreign key and the column, the 0068 predicate of the reference index, the
grant, the check and the column, the label through ``remove_enum_value`` — which fails while a
row still carries ``VOIDED`` (DG-MIG-06) — and then the 0051 status check, created after the
type is replaced because it holds constants of it.
E-12 is the first enumeration to lose a label while a check (``ck_policy_override__status``) and
two partial indexes (``ux_policy_override__active``, ``ux_sod_rule__published``) compare a column
with its constants: ``remove_enum_value`` carries such objects across the swap (dev-guide rev
1.171). No table, type or function is added (the erev function count is unchanged). Both bodies
are literals and the module imports ``migration_ops`` only (DG-MIG-12).

Revision 0114, assigned by the supervisor (04 §18 rule 9). ``down_revision`` was the head of the
lane branch (0085) when the revision was written and is main's head since the supervisor's merge
(ruling R-68 (e)).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0114"
down_revision = "0103"
branch_labels = None
depends_on = None

# The application role of 04 §1.5, spelt as a literal (DG-MIG-12).
APP_ROLE: Final = "erev_app"
ENUM: Final = "config_status"
VALUE: Final = "VOIDED"
MODIFICATION: Final = "modification"
CLASSIFICATION: Final = "classification"
CLASSIFICATION_CHECK: Final = "ck_modification__classification"
VERSION: Final = "estimate_version"
LINK: Final = "modification_id"
LINK_FK: Final = "fk_estimate_version__modification"
LINK_INDEX: Final = "ix_estimate_version__modification"
STATUS_CHECK: Final = "ck_estimate_version__status"
REFERENCE_INDEX: Final = "ux_modification__reference"
REFERENCE_COLUMNS: Final = ("tenant_id", "contract_id", "reference")
# 0068: every row with a reference holds it.
REFERENCE_PREDICATE_0068: Final = "reference IS NOT NULL"
# A discarded draft (VOIDED, never applied) does not.
REFERENCE_PREDICATE: Final = (
    "reference IS NOT NULL AND NOT (status = 'VOIDED' AND applied_event_id IS NULL)"
)
ESTIMATE: Final = "estimate"
CONTRACT_INDEX: Final = "ix_estimate__contract"
# 0051: the six statuses an estimate version takes of E-12.
STATUSES_0051: Final = ("DRAFT", "SUBMITTED", "APPROVED", "SUPERSEDED", "REJECTED", "WITHDRAWN")

# DB-03: erev_api.db.transitions.transition_trigger_sql("estimate_version") at this revision.
BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>SUPERSEDED', 'DRAFT>SUBMITTED', 'DRAFT>VOIDED', 'REJECTED>DRAFT', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'SUBMITTED>WITHDRAWN', 'WITHDRAWN>DRAFT']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['applied_event_ids', 'approval_request_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# The 0069 body (without DRAFT>VOIDED), restored by ``downgrade``.
PREVIOUS: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>SUPERSEDED', 'DRAFT>SUBMITTED', 'REJECTED>DRAFT', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'SUBMITTED>WITHDRAWN', 'WITHDRAWN>DRAFT']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['applied_event_ids', 'approval_request_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def _replace_function(body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes)."""
    if "$fn$" in body:
        raise ValueError("a trigger function body must not contain $fn$")
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.tg_{VERSION}__transition() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def _listed(statuses: tuple[str, ...]) -> str:
    return ",".join(f"'{status}'" for status in statuses)


def _reference_index(predicate: str) -> None:
    ops.execute(f"DROP INDEX erev.{REFERENCE_INDEX}")
    ops.create_indexes(
        MODIFICATION, [(REFERENCE_INDEX, list(REFERENCE_COLUMNS), predicate)], unique=True
    )


def upgrade() -> None:
    ops.add_enum_value(ENUM, VALUE)
    ops.execute(f"ALTER TABLE erev.{VERSION} DROP CONSTRAINT {STATUS_CHECK}")
    # As text: VOIDED is added above, and a new enum value is no enum literal before the commit.
    ops.execute(
        f"ALTER TABLE erev.{VERSION} ADD CONSTRAINT {STATUS_CHECK} "
        f"CHECK (status::text IN ({_listed((*STATUSES_0051, VALUE))}))"
    )
    ops.execute(f"ALTER TABLE erev.{MODIFICATION} ADD COLUMN {CLASSIFICATION} jsonb NULL")
    ops.execute(
        f"ALTER TABLE erev.{MODIFICATION} ADD CONSTRAINT {CLASSIFICATION_CHECK} "
        f"CHECK ({CLASSIFICATION} IS NULL OR jsonb_typeof({CLASSIFICATION}) = 'object')"
    )
    ops.execute(f"GRANT UPDATE ({CLASSIFICATION}) ON TABLE erev.{MODIFICATION} TO {APP_ROLE}")
    _reference_index(REFERENCE_PREDICATE)
    ops.execute(f"ALTER TABLE erev.{VERSION} ADD COLUMN {LINK} uuid NULL")
    ops.add_tenant_fk(VERSION, LINK, MODIFICATION)
    ops.create_indexes(
        VERSION,
        [(LINK_INDEX, ["tenant_id", LINK], f"{LINK} IS NOT NULL")],
        unique=False,
    )
    ops.create_indexes(
        ESTIMATE, [(CONTRACT_INDEX, ["tenant_id", "contract_id"], None)], unique=False
    )
    _replace_function(BODY)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    _replace_function(PREVIOUS)
    ops.execute(f"DROP INDEX erev.{CONTRACT_INDEX}")
    ops.execute(f"DROP INDEX erev.{LINK_INDEX}")
    ops.execute(f"ALTER TABLE erev.{VERSION} DROP CONSTRAINT {LINK_FK}")
    ops.execute(f"ALTER TABLE erev.{VERSION} DROP COLUMN {LINK}")
    _reference_index(REFERENCE_PREDICATE_0068)
    ops.execute(f"REVOKE UPDATE ({CLASSIFICATION}) ON TABLE erev.{MODIFICATION} FROM {APP_ROLE}")
    ops.execute(f"ALTER TABLE erev.{MODIFICATION} DROP CONSTRAINT {CLASSIFICATION_CHECK}")
    ops.execute(f"ALTER TABLE erev.{MODIFICATION} DROP COLUMN {CLASSIFICATION}")
    ops.execute(f"ALTER TABLE erev.{VERSION} DROP CONSTRAINT {STATUS_CHECK}")
    ops.remove_enum_value(ENUM, VALUE)
    # After the swap: the 0051 check compares the status with enum literals, and a constant of
    # the type has to be one of the type that stays.
    ops.execute(
        f"ALTER TABLE erev.{VERSION} ADD CONSTRAINT {STATUS_CHECK} "
        f"CHECK (status IN ({_listed(STATUSES_0051)}))"
    )
