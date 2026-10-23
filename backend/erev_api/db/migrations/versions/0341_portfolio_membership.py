"""Portfolio identities and retained membership intervals for shared estimates."""

import sqlalchemy as sa

from erev_api.db import migration_ops as ops

revision = "0341"
down_revision = "0340"
branch_labels = None
depends_on = None

MEMBERSHIP = """
BEGIN
  PERFORM 1 FROM erev.portfolio
    WHERE tenant_id = NEW.tenant_id AND id = NEW.portfolio_id FOR UPDATE;
  IF TG_OP = 'UPDATE' AND
     ((to_jsonb(OLD) - 'valid_to_known_at') IS DISTINCT FROM
      (to_jsonb(NEW) - 'valid_to_known_at') OR NEW.valid_to_known_at IS NULL) THEN
    RAISE EXCEPTION USING ERRCODE = '23514',
      MESSAGE = 'only closing portfolio membership is allowed';
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.valid_to_known_at IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'closed portfolio membership is immutable';
  END IF;
  IF EXISTS (
    SELECT 1 FROM erev.portfolio_member m
    WHERE m.tenant_id = NEW.tenant_id AND m.portfolio_id = NEW.portfolio_id
      AND m.contract_id = NEW.contract_id AND m.id <> NEW.id
      AND tstzrange(m.valid_from_known_at, m.valid_to_known_at, '[)') &&
          tstzrange(NEW.valid_from_known_at, NEW.valid_to_known_at, '[)')
  ) THEN
    RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'overlapping portfolio membership';
  END IF;
  RETURN NEW;
END;
"""


def upgrade() -> None:
    ops.create_tenant_table(
        "portfolio",
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("product_group", sa.Text(), nullable=True),
        sa.Column("description", ops.NamedType("erev.memo"), nullable=True),
        standard_sets=["SC-C", "SC-M"],
        unique=[("ux_portfolio__code", ["tenant_id", "code"], None)],
    )
    ops.apply_class("portfolio", "IM-M")
    ops.enable_rls("portfolio", "RLS-T")
    ops.create_tenant_table(
        "portfolio_member",
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column(
            "valid_from_known_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("valid_to_known_at", sa.DateTime(timezone=True), nullable=True),
        standard_sets=["SC-C"],
        checks=[
            (
                "ck_portfolio_member__interval",
                "valid_to_known_at IS NULL OR valid_to_known_at > valid_from_known_at",
            )
        ],
        unique=[
            (
                "ux_portfolio_member__current",
                ["tenant_id", "portfolio_id", "contract_id"],
                "valid_to_known_at IS NULL",
            )
        ],
        indexes=[("ix_portfolio_member__contract", ["tenant_id", "contract_id"], None)],
    )
    ops.add_tenant_fk("portfolio_member", "portfolio_id", "portfolio")
    ops.add_tenant_fk("portfolio_member", "contract_id", "contract")
    ops.add_tenant_fk("estimate", "portfolio_id", "portfolio")
    ops.add_tenant_fk("contract", "portfolio_id", "portfolio")
    ops.apply_class(
        "portfolio_member", "IM-S", update_columns=["valid_to_known_at"]
    )
    ops.enable_rls("portfolio_member", "RLS-T")
    ops.create_trigger(
        "portfolio_member", "interval", MEMBERSHIP, timing="BEFORE", events="INSERT OR UPDATE"
    )


def downgrade() -> None:
    ops.execute("ALTER TABLE erev.portfolio NO FORCE ROW LEVEL SECURITY")
    ops.execute("""
      DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM erev.portfolio) THEN
          RAISE EXCEPTION 'Cannot remove populated portfolio membership history';
        END IF;
      END $$
    """)
    ops.execute("ALTER TABLE erev.contract DROP CONSTRAINT fk_contract__portfolio")
    ops.execute("ALTER TABLE erev.estimate DROP CONSTRAINT fk_estimate__portfolio")
    ops.drop_tenant_table("portfolio_member")
    ops.drop_tenant_table("portfolio")
