"""BUILD_SPEC item DIN-12 (integration connections, the Salesforce mock adapter and canonical
ingestion): T-INT-01, T-INT-02, T-INT-04, E-72 and DB-15.

Creates ``integration_connection`` (04 T-INT-01; IM-M, DELETE forbidden; RLS-T), ``sync_run``
(04 T-INT-02; IM-S — ``status``, ``checkpoint_after``, ``source_totals``, ``loaded_totals``,
``record_count``, ``exception_count``, ``problem``, ``started_at``, ``finished_at``, SC-M updatable
under the DB-03 transition trigger; RLS-T) and ``external_id_map`` (04 T-INT-04; IM-S — ``valid_to``
updatable once, a re-link inserts a new row; RLS-T; SC-C only), the PostgreSQL type of E-72
``sync_run_status`` (owed by DIN-12 per 04 §3.4; literal labels, DG-MIG-12), the DB-15 trigger
``tg_integration_connection__sandbox`` (in a sandbox tenant an outbound adapter other than CSV_GL
cannot be ACTIVE: ``EREV-SBX-001``), and the tenant foreign keys that waited for ``sync_run``:
``source_record.sync_run_id`` (0049) and ``exception_item.sync_run_id`` (0041), plus the keys of
the new tables to ``integration_connection`` and ``sync_run``. T-INT-03 ``outbox_message`` exists
since 0016 (BS3-D-03). The text columns ``adapter``, ``direction``, ``status``, ``kind``,
``object_type`` and ``last_test_result`` carry the 04 CHECK lists; no PostgreSQL type is owed for
them. The ``sync_run`` transitions are E-72's ledger order: QUEUED → RUNNING → SUCCEEDED |
CONTROL_TOTAL_MISMATCH | FAILED, and QUEUED → FAILED (a run refused before it started).

Revision number 0072 assigned by team-lead on 2026-09-21 (first 0071, renumbered the same day:
0070 is F-CTR's urgent main-defect fix, 0071 F-LMG's PG-7b, both landing before this one).
``down_revision`` is ``0069`` while 0070 / 0071 are not on the branch — a dangling down_revision
would break the chain replay and ``alembic heads`` — and is re-pointed to the main head at the
pre-READY merge (the 0067 precedent — never two heads on main). Lane F-ADM as the F-DIN worktree's
sole writer (F-DIN-LAND, D-98 candidate 146).
"""

from __future__ import annotations

from typing import Any, Final

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0072"
# Re-pointed "0069" → "0071" at the pre-READY merge of main 109bf240 (0070 F-CTR, 0071 F-LMG).
down_revision = "0071"
branch_labels = None
depends_on = None

CONNECTION: Final = "integration_connection"
SYNC_RUN: Final = "sync_run"
EXTERNAL_ID_MAP: Final = "external_id_map"
TABLES: Final = (CONNECTION, SYNC_RUN, EXTERNAL_ID_MAP)

# E-72 ``sync_run_status`` (04 §3.4) — literal labels, never the live enum (DG-MIG-12).
SYNC_RUN_STATUS: Final = ("QUEUED", "RUNNING", "SUCCEEDED", "CONTROL_TOTAL_MISMATCH", "FAILED")
# 04 T-INT-01 / T-INT-02 / T-INT-04 CHECK lists (text columns).
ADAPTERS: Final = ("SALESFORCE", "STRIPE", "NETSUITE", "QUICKBOOKS_ONLINE", "CSV_GL")
DIRECTIONS: Final = ("INBOUND", "OUTBOUND", "BOTH")
CONNECTION_STATUSES: Final = ("ACTIVE", "DISABLED")
TEST_RESULTS: Final = ("SUCCESS", "FAILURE")
SYNC_RUN_KINDS: Final = (
    "INBOUND_POLL",
    "WEBHOOK_BATCH",
    "RECONCILIATION_SWEEP",
    "COA_SYNC",
    "TRIAL_BALANCE_PULL",
    "JOURNAL_EXPORT",
    "TEST_CONNECTION",
)
OBJECT_TYPES: Final = (
    "legal_entity",
    "gl_account",
    "dimension_value",
    "customer",
    "product",
    "contract",
    "obligation",
    "journal_batch",
)
_SC_M: Final = ("updated_at", "updated_by", "updated_by_kind", "row_version")
# 04 T-INT-02 IM-S: the columns UPDATE may change — the header's ledger members and SC-M (the run's
# moves stamp SC-M themselves: an IM-S table has the DB-03 transition trigger, no DB-02 touch).
# Corrected in place on 2026-09-29 (lane FIX-B; pre-release, no deployed database had run 0072):
# the list omitted SC-M, so PostgreSQL refused every move of a run with 42501 and the SYNC_RUN job
# failed ``forbidden`` before it started.
SYNC_RUN_UPDATE_COLUMNS: Final = (
    "status",
    "checkpoint_after",
    "source_totals",
    "loaded_totals",
    "record_count",
    "exception_count",
    "problem",
    "started_at",
    "finished_at",
    *_SC_M,
)
# The foreign keys to ``sync_run`` that earlier revisions left waiting (0049, 0041).
WAITING_KEYS: Final = (("source_record", "sync_run_id"), ("exception_item", "sync_run_id"))


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _array(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in values) + "]"


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _text(name: str, *, nullable: bool = False, default: str | None = None) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(name, sa.Text(), nullable=nullable, server_default=server_default)


def _jsonb(name: str, *, nullable: bool = True, default: str | None = None) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(name, ops.NamedType("jsonb"), nullable=nullable, server_default=server_default)


def _stamp(name: str, *, nullable: bool = True, now: bool = False) -> sa.Column[Any]:
    server_default = sa.text("now()") if now else None
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=nullable, server_default=server_default
    )


# DB-03: erev_api.db.transitions.transition_trigger_sql("sync_run") at DIN-12; DG-ARC-07 compares
# the installed source with this literal (tests/unit/test_integration_tables.py binds them).
SYNC_RUN_TRANSITION_BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['checkpoint_after', 'exception_count', 'finished_at', 'loaded_totals', 'problem', 'record_count', 'row_version', 'source_totals', 'started_at', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['QUEUED>FAILED', 'QUEUED>RUNNING', 'RUNNING>CONTROL_TOTAL_MISMATCH', 'RUNNING>FAILED', 'RUNNING>SUCCEEDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# DB-03: erev_api.db.transitions.transition_trigger_sql("external_id_map") at DIN-12 — ``valid_to``
# set once; every other column frozen.
EXTERNAL_ID_MAP_TRANSITION_BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['valid_to']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.valid_to IS NOT NULL AND NEW.valid_to IS DISTINCT FROM OLD.valid_to THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: valid_to of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""

# DB-15: in a sandbox tenant an outbound adapter other than CSV_GL cannot be ACTIVE (04 §14.1).
CONNECTION_SANDBOX_BODY: Final = """
DECLARE
  tenant_kind text;
BEGIN
  IF NEW.status <> 'ACTIVE' OR NEW.direction = 'INBOUND' OR NEW.adapter = 'CSV_GL' THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.status IS NOT DISTINCT FROM OLD.status
     AND NEW.direction IS NOT DISTINCT FROM OLD.direction
     AND NEW.adapter IS NOT DISTINCT FROM OLD.adapter THEN
    RETURN NEW;
  END IF;
  SELECT t.kind::text INTO tenant_kind FROM erev.tenant t WHERE t.id = NEW.tenant_id;
  IF tenant_kind = 'sandbox' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-SBX-001: connection %s of a sandbox tenant cannot activate outbound '
                       'adapter %s; only CSV_GL exports leave a sandbox',
                       NEW.code, NEW.adapter);
  END IF;
  RETURN NEW;
END
"""


def _create_integration_connection() -> None:
    ops.create_tenant_table(
        CONNECTION,
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        _text("adapter"),
        _text("direction"),
        sa.Column(
            "entity_ids",
            sa.ARRAY(sa.Uuid()),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        _text("base_url", nullable=True),
        _jsonb("config", nullable=False, default="'{}'::jsonb"),
        _text("secret_ref", nullable=True),
        _text("status", default="'DISABLED'"),
        _jsonb("checkpoint", nullable=False, default="'{}'::jsonb"),
        _stamp("last_test_at"),
        _text("last_test_result", nullable=True),
        _text("last_test_detail", nullable=True),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            (f"ck_{CONNECTION}__adapter", f"adapter IN ({_in(ADAPTERS)})"),
            (f"ck_{CONNECTION}__direction", f"direction IN ({_in(DIRECTIONS)})"),
            (f"ck_{CONNECTION}__status", f"status IN ({_in(CONNECTION_STATUSES)})"),
            (
                f"ck_{CONNECTION}__last_test_result",
                f"last_test_result IS NULL OR last_test_result IN ({_in(TEST_RESULTS)})",
            ),
        ],
        unique=[(f"ux_{CONNECTION}__code", ["tenant_id", "code"], None)],
    )
    ops.apply_class(CONNECTION, "IM-M")
    ops.enable_rls(CONNECTION, "RLS-T")
    ops.create_trigger(
        CONNECTION, "sandbox", CONNECTION_SANDBOX_BODY, timing="BEFORE", events="INSERT OR UPDATE"
    )


def _create_sync_run() -> None:
    ops.create_tenant_table(
        SYNC_RUN,
        _uuid("integration_connection_id", nullable=False),
        _text("kind"),
        sa.Column(
            "status",
            ops.NamedType("erev.sync_run_status"),
            nullable=False,
            server_default=sa.text("'QUEUED'"),
        ),
        _jsonb("checkpoint_before"),
        _jsonb("checkpoint_after"),
        _jsonb("source_totals"),
        _jsonb("loaded_totals"),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("exception_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        _jsonb("problem"),
        _uuid("job_id"),
        _stamp("started_at"),
        _stamp("finished_at"),
        standard_sets=["SC-C", "SC-M"],
        checks=[(f"ck_{SYNC_RUN}__kind", f"kind IN ({_in(SYNC_RUN_KINDS)})")],
        indexes=[
            (
                f"ix_{SYNC_RUN}__connection",
                ["tenant_id", "integration_connection_id", "created_at"],
                None,
            )
        ],
    )
    ops.add_tenant_fk(SYNC_RUN, "integration_connection_id", CONNECTION)
    ops.apply_class(SYNC_RUN, "IM-S", update_columns=SYNC_RUN_UPDATE_COLUMNS)
    ops.create_trigger(
        SYNC_RUN, "transition", SYNC_RUN_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )
    ops.enable_rls(SYNC_RUN, "RLS-T")


def _create_external_id_map() -> None:
    ops.create_tenant_table(
        EXTERNAL_ID_MAP,
        _uuid("integration_connection_id", nullable=False),
        _text("object_type"),
        _uuid("internal_id", nullable=False),
        _text("external_id"),
        _text("external_version", nullable=True),
        _stamp("valid_from", nullable=False, now=True),
        _stamp("valid_to"),
        _uuid("sync_run_id"),
        standard_sets=["SC-C"],
        checks=[(f"ck_{EXTERNAL_ID_MAP}__object_type", f"object_type IN ({_in(OBJECT_TYPES)})")],
        unique=[
            (
                f"ux_{EXTERNAL_ID_MAP}__external",
                ["tenant_id", "integration_connection_id", "object_type", "external_id"],
                "valid_to IS NULL",
            ),
            (
                f"ux_{EXTERNAL_ID_MAP}__internal",
                ["tenant_id", "integration_connection_id", "object_type", "internal_id"],
                "valid_to IS NULL",
            ),
        ],
    )
    ops.add_tenant_fk(EXTERNAL_ID_MAP, "integration_connection_id", CONNECTION)
    ops.add_tenant_fk(EXTERNAL_ID_MAP, "sync_run_id", SYNC_RUN)
    ops.apply_class(EXTERNAL_ID_MAP, "IM-S", update_columns=("valid_to",))
    ops.create_trigger(
        EXTERNAL_ID_MAP,
        "transition",
        EXTERNAL_ID_MAP_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )
    ops.enable_rls(EXTERNAL_ID_MAP, "RLS-T")


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("sync_run_status", SYNC_RUN_STATUS)
    _create_integration_connection()
    _create_sync_run()
    _create_external_id_map()
    for table, column in WAITING_KEYS:
        ops.add_tenant_fk(table, column, SYNC_RUN)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    for table, column in reversed(WAITING_KEYS):
        stem = column.removesuffix("_id")
        ops.execute(f"ALTER TABLE erev.{table} DROP CONSTRAINT fk_{table}__{stem}")
    for table in reversed(TABLES):
        ops.drop_tenant_table(table)
    ops.drop_enum("sync_run_status")
