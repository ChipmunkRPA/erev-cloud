"""BUILD_SPEC item RFD-2: legal entities, books, period states and entity-scoped access.

04 ids created: E-110 ``reason_code`` (E-02 ``book_code`` exists from 0015; the E-04 columns are
``text`` with a CHECK of the E-04 literals, because table T-REF-06 creates the row type
``erev.period_state`` that an enum type of that name would collide with, L1-1-Q-20);
T-REF-01 ``legal_entity`` (IM-M, RLS-TE on ``id``) with ``ux_legal_entity__code``,
``ck_legal_entity__country_code`` and its foreign keys to ``currency``, ``fiscal_calendar`` and
itself; T-REF-02 ``book`` (IM-M, RLS-T; UPDATE granted on every column except ``code``, which is
immutable) with ``ux_book__code``, ``ux_book__primary`` and the posting target checks; T-REF-03
``entity_book`` (IM-M, RLS-TE on ``entity_id``) with ``ux_entity_book__entity`` and its foreign
keys to ``legal_entity``, ``book (tenant_id, code)`` and ``period``; T-REF-06 ``period_state``
(IM-X, RLS-TE) with ``ux_period_state__period`` (04 names the two keys ``ux_entity_book`` and
``ux_period_state``; NC-16 names, L1-1-Q-19) and ``ix_period_state__open``; T-REF-07
``period_state_transition``
(IM-A, RLS-TE) with ``ix_period_state_transition__state`` and the reason code, approval and lock
checks of its column notes. Triggers: DB-07 ``tg_period_state__update`` (a state change needs a
transition row of the transaction and an allowed pair, ``EREV-PER-001``) and
``tg_period_state_transition__pair`` (the allowed pairs of T-REF-07); DB-05 ``tg_period__frozen``
and ``tg_fiscal_calendar__frozen`` (a period, and the pattern fields of its calendar, freeze once a
non-``future`` period state references it, ``EREV-REF-001``; L1-1-Q-3); DB-12 replaces the bodies
of ``tg_role_assignment__entity_ids`` and ``tg_api_client__entity_ids``, which failed closed
(BS1-D-06), with the check against ``legal_entity`` (``EREV-REF-002``). The foreign keys
``period_state.current_lock_id`` and ``period_state_transition.close_run_id`` belong to the
revisions that create ``period_lock`` and ``close_run`` (DG-MIG-03), as does the
``subledger_line`` leg of DB-05.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

# 04 §3.4 E-04 and E-110.
PERIOD_STATE = ("future", "open", "closing", "closed", "reopened", "permanently_locked")
REASON_CODE = (
    "DUPLICATE",
    "CREATED_IN_ERROR",
    "CUSTOMER_CANCELLED",
    "DATA_CORRECTION",
    "ESTIMATE_CORRECTION",
    "OTHER",
    "ERROR_CORRECTION",
    "LATE_SOURCE_DATA",
    "AUDIT_ADJUSTMENT",
    "CLOSE_RESTARTED",
    "DATA_CORRECTION_PENDING",
)
_STATES = ", ".join(f"'{state}'" for state in PERIOD_STATE)
# 04 T-REF-02: the book columns erev_app may update; ``code`` is immutable.
BOOK_UPDATE_COLUMNS = (
    "name",
    "is_primary",
    "is_enabled",
    "posting_target",
    "updated_at",
    "updated_by",
    "updated_by_kind",
    "row_version",
)
_APPROVED_STATES = "'closed', 'reopened', 'permanently_locked'"

# DB-07: a state change needs an allowed pair of T-REF-07 ``to_state`` and a transition row inserted
# in this transaction for the same pair; the entity, book and period of a state never change.
PERIOD_STATE_UPDATE_BODY = """
BEGIN
  IF NEW.entity_id IS DISTINCT FROM OLD.entity_id OR NEW.book_code IS DISTINCT FROM OLD.book_code
     OR NEW.period_id IS DISTINCT FROM OLD.period_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-PER-001: the entity, book and period of %I.%I row %s cannot change',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id);
  END IF;
  IF NEW.state IS NOT DISTINCT FROM OLD.state THEN
    RETURN NEW;
  END IF;
  IF (OLD.state::text || '>' || NEW.state::text) <> ALL (ARRAY[
       'future>open', 'open>closing', 'closing>open', 'closing>closed', 'closed>reopened',
       'reopened>closing', 'closed>permanently_locked']) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-PER-001: %I.%I row %s cannot move from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id, OLD.state, NEW.state);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM erev.period_state_transition t
     WHERE t.tenant_id = NEW.tenant_id AND t.period_state_id = NEW.id
       AND t.created_txid = txid_current()
       AND t.from_state = OLD.state AND t.to_state = NEW.state
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-PER-001: %I.%I row %s moved from %s to %s without a transition',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id, OLD.state, NEW.state);
  END IF;
  RETURN NEW;
END
"""

# DB-07 with T-REF-07: a transition row names an allowed pair (NULL → future on creation).
TRANSITION_PAIR_BODY = """
BEGIN
  IF (coalesce(NEW.from_state::text, '') || '>' || NEW.to_state::text) <> ALL (ARRAY[
       '>future', 'future>open', 'open>closing', 'closing>open', 'closing>closed',
       'closed>reopened', 'reopened>closing', 'closed>permanently_locked']) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-PER-001: %I.%I allows no transition from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, coalesce(NEW.from_state::text, 'NULL'),
                       NEW.to_state);
  END IF;
  RETURN NEW;
END
"""

# DB-05: a period referenced by a period state other than ``future`` is immutable.
PERIOD_FROZEN_BODY = """
BEGIN
  IF EXISTS (
    SELECT 1 FROM erev.period_state s
     WHERE s.tenant_id = OLD.tenant_id AND s.period_id = OLD.id AND s.state <> 'future'
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-001: period %s of %I.%I is frozen: a period state beyond future '
                       'references it', OLD.period_key, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END
"""

# DB-05: the pattern fields of a calendar freeze once any of its periods is referenced.
CALENDAR_FROZEN_BODY = """
BEGIN
  IF (NEW.pattern, NEW.fiscal_year_start_month, NEW.week_end_day, NEW.year_end_anchor)
     IS NOT DISTINCT FROM
     (OLD.pattern, OLD.fiscal_year_start_month, OLD.week_end_day, OLD.year_end_anchor) THEN
    RETURN NEW;
  END IF;
  IF EXISTS (
    SELECT 1 FROM erev.period p
      JOIN erev.period_state s ON s.tenant_id = p.tenant_id AND s.period_id = p.id
     WHERE p.tenant_id = OLD.tenant_id AND p.calendar_id = OLD.id AND s.state <> 'future'
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-001: the pattern of calendar %s of %I.%I is frozen: a period '
                       'state beyond future references its periods',
                       OLD.code, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""

# DB-12: every entity id names a legal entity of the tenant.
ENTITY_IDS_BODY = """
DECLARE
  unknown text;
BEGIN
  SELECT string_agg(e.id::text, ', ' ORDER BY e.id::text) INTO unknown
    FROM unnest(NEW.entity_ids) AS e(id)
   WHERE NOT EXISTS (
     SELECT 1 FROM erev.legal_entity l WHERE l.tenant_id = NEW.tenant_id AND l.id = e.id
   );
  IF unknown IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-002: entity_ids of %I.%I name no existing legal entity: %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, unknown);
  END IF;
  RETURN NEW;
END
"""
# The DB-12 fail-closed body of revisions 0007 and 0022 (BS1-D-06), restored by downgrade().
ENTITY_IDS_FAIL_CLOSED_BODY = """
BEGIN
  IF cardinality(NEW.entity_ids) > 0 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-002: entity_ids of %I.%I name no existing legal entity',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""
ENTITY_IDS_FUNCTIONS = ("tg_role_assignment__entity_ids()", "tg_api_client__entity_ids()")


def _replace_function(signature: str, body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger; NC-18 attributes."""
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.{signature} RETURNS trigger LANGUAGE plpgsql "
        f"SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def _timestamp(name: str, *, nullable: bool = True, now_default: bool = False) -> sa.Column[Any]:
    default = sa.text("now()") if now_default else None
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=default)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("reason_code", REASON_CODE)

    ops.create_tenant_table(
        "legal_entity",
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("functional_currency", ops.NamedType("erev.currency_code"), nullable=False),
        sa.Column("time_zone", ops.NamedType("erev.tz_name"), nullable=False),
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("parent_entity_id", sa.Uuid(), nullable=True),
        sa.Column("country_code", sa.CHAR(2), nullable=True),
        sa.Column("tax_id", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        standard_sets=["SC-C", "SC-M"],
        checks=[("ck_legal_entity__country_code", "country_code ~ '^[A-Z]{2}$'")],
        unique=[("ux_legal_entity__code", ["tenant_id", "code"], None)],
    )
    ops.add_global_fk("legal_entity", "functional_currency", "currency", target_column="code")
    ops.add_tenant_fk("legal_entity", "calendar_id", "fiscal_calendar")
    ops.add_tenant_fk("legal_entity", "parent_entity_id", "legal_entity")
    ops.apply_class("legal_entity", "IM-M")
    ops.enable_rls("legal_entity", "RLS-TE", entity_column="id")

    ops.create_tenant_table(
        "book",
        sa.Column("code", ops.NamedType("erev.book_code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("posting_target", sa.Text(), nullable=False),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            (
                "ck_book__posting_target",
                "posting_target IN ('GL_PRIMARY', 'GL_SECONDARY', 'NONE')",
            ),
            ("ck_book__legacy_posting_target", "code <> 'LEGACY' OR posting_target = 'NONE'"),
        ],
        unique=[
            ("ux_book__code", ["tenant_id", "code"], None),
            ("ux_book__primary", ["tenant_id"], "is_primary"),
        ],
    )
    ops.apply_class("book", "IM-M", update_columns=BOOK_UPDATE_COLUMNS)
    ops.enable_rls("book", "RLS-T")

    ops.create_tenant_table(
        "entity_book",
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("book_code", ops.NamedType("erev.book_code"), nullable=False),
        sa.Column("first_period_id", sa.Uuid(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        standard_sets=["SC-C", "SC-M"],
        # 04 T-REF-03 ``ux_entity_book``, named per NC-16 (L1-1-Q-19).
        unique=[("ux_entity_book__entity", ["tenant_id", "entity_id", "book_code"], None)],
    )
    ops.add_tenant_fk("entity_book", "entity_id", "legal_entity")
    ops.execute(
        "ALTER TABLE erev.entity_book ADD CONSTRAINT fk_entity_book__book "
        "FOREIGN KEY (tenant_id, book_code) REFERENCES erev.book (tenant_id, code) "
        "ON DELETE RESTRICT ON UPDATE RESTRICT"
    )
    ops.add_tenant_fk("entity_book", "first_period_id", "period")
    ops.apply_class("entity_book", "IM-M")
    ops.enable_rls("entity_book", "RLS-TE", entity_column="entity_id")

    ops.create_tenant_table(
        "period_state",
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("book_code", ops.NamedType("erev.book_code"), nullable=False),
        sa.Column("period_id", sa.Uuid(), nullable=False),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default=sa.text("'future'")),
        sa.Column("current_lock_id", sa.Uuid(), nullable=True),
        _timestamp("state_changed_at", nullable=False, now_default=True),
        standard_sets=["SC-M"],
        checks=[("ck_period_state__state", f"state IN ({_STATES})")],
        # 04 T-REF-06 ``ux_period_state``, named per NC-16 (L1-1-Q-19).
        unique=[
            (
                "ux_period_state__period",
                ["tenant_id", "entity_id", "book_code", "period_id"],
                None,
            )
        ],
        indexes=[
            (
                "ix_period_state__open",
                ["tenant_id", "entity_id", "book_code", "state", "period_end_date"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("period_state", "entity_id", "legal_entity")
    ops.add_tenant_fk("period_state", "period_id", "period")
    ops.apply_class("period_state", "IM-X")
    ops.enable_rls("period_state", "RLS-TE", entity_column="entity_id")
    ops.create_trigger(
        "period_state", "update", PERIOD_STATE_UPDATE_BODY, timing="BEFORE", events="UPDATE"
    )

    ops.create_tenant_table(
        "period_state_transition",
        sa.Column("period_state_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("book_code", ops.NamedType("erev.book_code"), nullable=False),
        sa.Column("period_id", sa.Uuid(), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=True),
        sa.Column("to_state", sa.Text(), nullable=False),
        sa.Column("reason_code", ops.NamedType("erev.reason_code"), nullable=True),
        sa.Column("comment", ops.NamedType("erev.memo"), nullable=True),
        sa.Column("approval_request_id", sa.Uuid(), nullable=True),
        sa.Column("period_lock_id", sa.Uuid(), nullable=True),
        sa.Column("close_run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_txid",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("txid_current()"),
        ),
        standard_sets=["SC-C"],
        checks=[
            ("ck_period_state_transition__from_state", f"from_state IN ({_STATES})"),
            ("ck_period_state_transition__to_state", f"to_state IN ({_STATES})"),
            (
                "ck_period_state_transition__reason_code",
                "(NOT (from_state = 'closing' AND to_state = 'open') "
                "OR reason_code IN ('CLOSE_RESTARTED', 'DATA_CORRECTION_PENDING', 'OTHER')) "
                "AND (NOT (from_state = 'closed' AND to_state = 'reopened') "
                "OR reason_code IN ('ERROR_CORRECTION', 'LATE_SOURCE_DATA', 'AUDIT_ADJUSTMENT', "
                "'OTHER'))",
            ),
            (
                "ck_period_state_transition__approval",
                f"to_state NOT IN ({_APPROVED_STATES}) OR approval_request_id IS NOT NULL",
            ),
            (
                "ck_period_state_transition__lock",
                f"to_state NOT IN ({_APPROVED_STATES}) OR period_lock_id IS NOT NULL",
            ),
        ],
        indexes=[
            (
                "ix_period_state_transition__state",
                ["tenant_id", "period_state_id", "created_at"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("period_state_transition", "period_state_id", "period_state")
    ops.apply_class("period_state_transition", "IM-A")
    ops.enable_rls("period_state_transition", "RLS-TE", entity_column="entity_id")
    ops.create_trigger(
        "period_state_transition", "pair", TRANSITION_PAIR_BODY, timing="BEFORE", events="INSERT"
    )

    ops.create_trigger(
        "period", "frozen", PERIOD_FROZEN_BODY, timing="BEFORE", events="UPDATE OR DELETE"
    )
    ops.create_trigger(
        "fiscal_calendar",
        "frozen",
        CALENDAR_FROZEN_BODY,
        timing="BEFORE",
        events="UPDATE OF pattern, fiscal_year_start_month, week_end_day, year_end_anchor",
    )
    for signature in ENTITY_IDS_FUNCTIONS:
        _replace_function(signature, ENTITY_IDS_BODY)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    for signature in ENTITY_IDS_FUNCTIONS:
        _replace_function(signature, ENTITY_IDS_FAIL_CLOSED_BODY)
    ops.execute("DROP TRIGGER tg_fiscal_calendar__frozen ON erev.fiscal_calendar")
    ops.execute("DROP FUNCTION erev.tg_fiscal_calendar__frozen()")
    ops.execute("DROP TRIGGER tg_period__frozen ON erev.period")
    ops.execute("DROP FUNCTION erev.tg_period__frozen()")
    ops.drop_tenant_table("period_state_transition")
    ops.drop_tenant_table("period_state")
    ops.drop_tenant_table("entity_book")
    ops.drop_tenant_table("book")
    ops.drop_tenant_table("legal_entity")
    ops.drop_enum("reason_code")
