"""Revision 0063 on 0062 (F-SNP SNP-1 slice I-5; lane record §13.2.14; assigned at merge prep
2026-09-20, provisional 0100 on the branch before): seed the T-PLT-31 platform parameter
``platform.snapshot_retention_families`` (04 rev 1.47, catalogue rule 2).

Migration 0003 seeds every platform parameter on a fresh database, so this revision matters only to
databases already past 0003: one idempotent insert (``ON CONFLICT (code) DO NOTHING``); the
downgrade is a documented no-op: the table is append-only (DB-01) and 0003's downgrade drops it
with the row (DG-MIG-04 exception, dev-guide rev 1.48).

Revision ID: 0063
Revises: 0062
"""

from __future__ import annotations

import json
from typing import Any

from erev_api.db import migration_ops as ops
from erev_api.registry.platform import PLATFORM_PARAMETERS
from erev_api.registry.policies import RegistryParameterSpec

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

CODE = "platform.snapshot_retention_families"
COLUMNS = (
    "code",
    "pol_id",
    "category",
    "value_schema",
    "default_asc606",
    "default_ifrs15",
    "is_forced_asc606",
    "is_forced_ifrs15",
    "legacy_parity_value",
    "allowed_levels",
    "pin",
    "approval_code",
    "description",
    "source_ref",
    "section",
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _row(spec: RegistryParameterSpec) -> tuple[ops.SeedValue, ...]:
    """The 0003 row shape of one T-PLT-31 parameter."""
    levels = ",".join(
        sorted(scope.value for scope in spec.allowed_levels)
    )  # DG-MIG-12: no enum import
    return (
        spec.code,
        spec.pol_id,
        spec.category.value,
        _json(spec.value_schema),
        _json(spec.default_asc606),
        None if spec.default_ifrs15 is None else _json(spec.default_ifrs15),
        spec.is_forced_asc606,
        spec.is_forced_ifrs15,
        None if spec.legacy_parity_value is None else _json(spec.legacy_parity_value),
        "{" + levels + "}",
        spec.pin,
        spec.approval_code,
        spec.description,
        spec.source_ref,
        spec.section,
    )


def upgrade() -> None:
    """Seed the one parameter where 0003 has not (idempotent)."""
    statement = ops.insert_rows_sql(
        "registry_parameter", COLUMNS, [_row(PLATFORM_PARAMETERS[CODE])]
    )
    ops.execute(statement + " ON CONFLICT (code) DO NOTHING")


def downgrade() -> None:
    """A documented no-op (DG-MIG-04 append-only seed exception, dev-guide rev 1.48; DG-MIG-08):
    ``registry_parameter`` is append-only — DB-01 ``tg_registry_parameter__immutable`` refuses
    DELETE with EREV-IMM-001 (the integrated batch on main 0cb36c14 hit it) — so the seeded
    ``platform.snapshot_retention_families`` row stays; 0003's downgrade drops the table with the
    row, which keeps the round trip complete."""
