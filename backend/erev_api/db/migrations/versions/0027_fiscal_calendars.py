"""BUILD_SPEC item RFD-1: fiscal calendars.

04 ids created: E-50 ``calendar_pattern``; T-REF-04 ``fiscal_calendar`` (IM-M, RLS-T) with
``ux_fiscal_calendar__code``; T-REF-05 ``period`` (IM-M, RLS-T) with ``ux_period__no``,
``ux_period__key``, ``ix_period__dates`` and its composite foreign key to ``fiscal_calendar``;
DB-05 ``tg_period__contiguous``: the periods of a calendar are contiguous without overlap
(``EREV-REF-001``). The DB-05 freezes of a referenced period and of the calendar pattern fields
test rows of tables created later (``period_state``, ``subledger_line``); the revisions that create
those tables add them (DG-MIG-03; L1-1-Q-3).
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

# 04 §3.4 E-50.
CALENDAR_PATTERN = ("MONTHLY", "P445", "P454", "P544", "P13", "W5253")
WEEK_PATTERNS = "'P445', 'P454', 'P544', 'P13', 'W5253'"

# DB-05: the periods of a calendar are contiguous without overlap. Locking the calendar row first
# serialises the writers of one calendar, so each sees the periods the others committed.
CONTIGUOUS_BODY = """
DECLARE
  span_days integer;
  covered_days integer;
BEGIN
  PERFORM 1 FROM erev.fiscal_calendar c
   WHERE c.tenant_id = NEW.tenant_id AND c.id = NEW.calendar_id
     FOR NO KEY UPDATE;
  IF EXISTS (
    SELECT 1 FROM erev.period p
     WHERE p.tenant_id = NEW.tenant_id AND p.calendar_id = NEW.calendar_id AND p.id <> NEW.id
       AND p.start_date <= NEW.end_date AND NEW.start_date <= p.end_date
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-001: period %s of %I.%I overlaps another period of calendar %s',
                       NEW.period_key, TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.calendar_id);
  END IF;
  SELECT max(d.end_date) - min(d.start_date) + 1, sum(d.end_date - d.start_date + 1)
    INTO span_days, covered_days
    FROM (
      SELECT p.start_date, p.end_date FROM erev.period p
       WHERE p.tenant_id = NEW.tenant_id AND p.calendar_id = NEW.calendar_id AND p.id <> NEW.id
      UNION ALL
      SELECT NEW.start_date, NEW.end_date
    ) AS d;
  IF span_days <> covered_days THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-001: period %s of %I.%I leaves a gap in calendar %s',
                       NEW.period_key, TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.calendar_id);
  END IF;
  RETURN NEW;
END
"""


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("calendar_pattern", CALENDAR_PATTERN)

    ops.create_tenant_table(
        "fiscal_calendar",
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column(
            "pattern",
            ops.NamedType("erev.calendar_pattern"),
            nullable=False,
            server_default=sa.text("'MONTHLY'"),
        ),
        sa.Column(
            "fiscal_year_start_month",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("week_end_day", sa.SmallInteger(), nullable=True),
        sa.Column("year_end_anchor", sa.Text(), nullable=True),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            (
                "ck_fiscal_calendar__fiscal_year_start_month",
                "fiscal_year_start_month BETWEEN 1 AND 12",
            ),
            ("ck_fiscal_calendar__week_end_day", "week_end_day BETWEEN 1 AND 7"),
            (
                "ck_fiscal_calendar__year_end_anchor",
                "year_end_anchor IN ('LAST_WEEKDAY_OF_MONTH', 'NEAREST_WEEKDAY_TO_MONTH_END')",
            ),
            (
                "ck_fiscal_calendar__week_fields",
                f"pattern NOT IN ({WEEK_PATTERNS}) "
                "OR (week_end_day IS NOT NULL AND year_end_anchor IS NOT NULL)",
            ),
        ],
        unique=[("ux_fiscal_calendar__code", ["tenant_id", "code"], None)],
    )
    ops.apply_class("fiscal_calendar", "IM-M")
    ops.enable_rls("fiscal_calendar", "RLS-T")

    ops.create_tenant_table(
        "period",
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("period_no", sa.SmallInteger(), nullable=False),
        sa.Column("quarter_no", sa.SmallInteger(), nullable=False),
        sa.Column("period_key", sa.Text(), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_period__period_no", "period_no BETWEEN 1 AND 13"),
            ("ck_period__quarter_no", "quarter_no BETWEEN 1 AND 4"),
            ("ck_period__dates", "end_date >= start_date"),
        ],
        unique=[
            ("ux_period__no", ["tenant_id", "calendar_id", "fiscal_year", "period_no"], None),
            ("ux_period__key", ["tenant_id", "calendar_id", "period_key"], None),
        ],
        indexes=[
            ("ix_period__dates", ["tenant_id", "calendar_id", "start_date", "end_date"], None)
        ],
    )
    ops.add_tenant_fk("period", "calendar_id", "fiscal_calendar")
    ops.apply_class("period", "IM-M")
    ops.enable_rls("period", "RLS-T")
    ops.create_trigger(
        "period",
        "contiguous",
        CONTIGUOUS_BODY,
        timing="BEFORE",
        events="INSERT OR UPDATE OF calendar_id, start_date, end_date",
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("period")
    ops.drop_tenant_table("fiscal_calendar")
    ops.drop_enum("calendar_pattern")
