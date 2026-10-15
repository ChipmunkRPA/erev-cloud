"""T-CON-14 immutable material-right option terms and ownership constraints."""

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0145"
down_revision = "0144"
branch_labels = None
depends_on = None

OWNERSHIP = """
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id() THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'material_right tenant context required';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM erev.obligation o
    WHERE o.tenant_id = NEW.tenant_id AND o.id = NEW.obligation_id
      AND o.contract_id = NEW.contract_id
  ) THEN
    RAISE EXCEPTION USING ERRCODE = '23514',
      MESSAGE = 'material_right obligation must belong to its contract';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM erev.contract c
    WHERE c.tenant_id = NEW.tenant_id AND c.id = NEW.contract_id
      AND c.transaction_currency = NEW.currency
  ) THEN
    RAISE EXCEPTION USING ERRCODE = '23514',
      MESSAGE = 'material_right currency must match its contract';
  END IF;
  IF NEW.likelihood_estimate_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM erev.estimate e
    WHERE e.tenant_id = NEW.tenant_id AND e.id = NEW.likelihood_estimate_id
      AND e.contract_id = NEW.contract_id AND e.estimate_kind = 'EXERCISE_LIKELIHOOD'
      AND (e.obligation_id IS NULL OR e.obligation_id = NEW.obligation_id)
  ) THEN
    RAISE EXCEPTION USING ERRCODE = '23514',
      MESSAGE = 'material_right likelihood must match its contract, obligation and exercise kind';
  END IF;
  RETURN NEW;
END;
"""


def _named(name: str, kind: str, *, nullable: bool = False) -> sa.Column[Any]:
    return sa.Column(name, ops.NamedType(kind), nullable=nullable)


def upgrade() -> None:
    ops.create_enum(
        "option_type",
        (
            "DISCOUNT_VOUCHER",
            "LOYALTY_POINTS",
            "RENEWAL_OPTION",
            "TIERED_DISCOUNT",
            "OTHER",
        ),
    )
    ops.create_tenant_table(
        "material_right",
        sa.Column("obligation_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        _named("option_type", "erev.option_type"),
        _named("incremental_discount_ratio", "erev.exact", nullable=True),
        sa.Column(
            "is_discount_available_without_contract",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        _named("expected_purchase_amount", "erev.money", nullable=True),
        _named("currency", "erev.currency_code"),
        sa.Column("ssp_method", sa.Text(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("likelihood_estimate_id", sa.Uuid(), nullable=True),
        sa.Column(
            "is_legacy_quantity_ssp_dollars",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        standard_sets=["SC-C"],
        checks=(
            (
                "ck_material_right__method",
                "ssp_method IN ('DISCOUNT_X_LIKELIHOOD','RENEWAL_ALTERNATIVE','ENTERED_AMOUNT')",
            ),
            (
                "ck_material_right__ratio",
                "incremental_discount_ratio >= 0 AND incremental_discount_ratio <= 1",
            ),
            ("ck_material_right__purchase", "expected_purchase_amount >= 0"),
            (
                "ck_material_right__discount_terms",
                "ssp_method <> 'DISCOUNT_X_LIKELIHOOD' OR "
                "(incremental_discount_ratio IS NOT NULL AND expected_purchase_amount IS NOT NULL "
                "AND likelihood_estimate_id IS NOT NULL)",
            ),
        ),
        unique=[("ux_material_right__obligation", ["tenant_id", "obligation_id"], None)],
        indexes=[("ix_material_right__contract", ["tenant_id", "contract_id"], None)],
    )
    ops.execute(
        "CREATE UNIQUE INDEX ux_contract__material_right_currency "
        "ON erev.contract (tenant_id, id, transaction_currency)"
    )
    ops.execute(
        "ALTER TABLE erev.material_right ADD CONSTRAINT fk_material_right__contract_currency "
        "FOREIGN KEY (tenant_id, contract_id, currency) "
        "REFERENCES erev.contract (tenant_id, id, transaction_currency)"
    )
    ops.add_tenant_fk("material_right", "contract_id", "contract")
    ops.add_tenant_fk("material_right", "obligation_id", "obligation")
    ops.add_tenant_fk("material_right", "likelihood_estimate_id", "estimate")
    ops.add_global_fk("material_right", "currency", "currency", target_column="code")
    ops.apply_class("material_right", "IM-A")
    ops.enable_rls("material_right", "RLS-T")
    ops.create_trigger("material_right", "ownership", OWNERSHIP, timing="BEFORE", events="INSERT")


def downgrade() -> None:
    ops.drop_tenant_table("material_right")
    ops.execute("DROP INDEX erev.ux_contract__material_right_currency")
    ops.drop_enum("option_type")
