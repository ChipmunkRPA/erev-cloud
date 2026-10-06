"""Revision 0066 on 0065 (lane F-SNP; 04 rev 1.59 T-PLT-47; D-98 candidate 125): the append-only
metadata correction table ``registry_parameter_correction`` and correction 1 of
``platform.snapshot_retention_families`` — the value schema that admits ``{}`` (04 rev 1.56) — for
databases whose 0003 / 0063 seed predates it (``registry_parameter`` is append-only with primary key
``code`` and is never updated).

Literals only (DG-MIG-12): the correction row is the Python catalogue's rendering at authoring time,
pinned by tests/unit/test_registry_parameter_correction.py (the seed drift oracle). The downgrade
drops only the table this revision created (DG-MIG-04); no seeded row is touched.

Revision ID: 0066
Revises: 0065
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None

TABLE = "registry_parameter_correction"
COLUMNS = (
    "code",
    "correction_no",
    "value_schema",
    "description",
    "source_ref",
    "section",
    "applied_by_revision",
    "created_by_kind",
)
CODE = "platform.snapshot_retention_families"
# json.dumps(PLATFORM_PARAMETERS[CODE].value_schema) at authoring: anyOf [{} | all five families].
VALUE_SCHEMA = (
    '{"anyOf": [{"const": {}}, {"type": "object", "properties": {"file_object": {"type": '
    '"string", "enum": ["TENANT_LIFETIME", "AUDIT_RETENTION_YEARS", "EXPIRES_AT_SWEEP", '
    '"FILE_RETENTION"]}, "import_row": {"type": "string", "enum": ["TENANT_LIFETIME", '
    '"AUDIT_RETENTION_YEARS", "EXPIRES_AT_SWEEP", "FILE_RETENTION"]}, "source_record": '
    '{"type": "string", "enum": ["TENANT_LIFETIME", "AUDIT_RETENTION_YEARS", '
    '"EXPIRES_AT_SWEEP", "FILE_RETENTION"]}, "contract_event": {"type": "string", "enum": '
    '["TENANT_LIFETIME", "AUDIT_RETENTION_YEARS", "EXPIRES_AT_SWEEP", "FILE_RETENTION"]}, '
    '"manual_adjustment": {"type": "string", "enum": ["TENANT_LIFETIME", '
    '"AUDIT_RETENTION_YEARS", "EXPIRES_AT_SWEEP", "FILE_RETENTION"]}}, "required": '
    '["file_object", "import_row", "source_record", "contract_event", "manual_adjustment"], '
    '"additionalProperties": false}]}'
)
DESCRIPTION = (
    "Retention literal per copied snapshot family; {} confirms nothing and TENANT_SNAPSHOT "
    "refuses until counsel confirms all five (ruling Q-4)."
)
SOURCE_REF = "F-SNP SNP-1 slice I-5; D-98 cand. 25 Q-4"
SECTION = "Platform"
CORRECTION: tuple[ops.SeedValue, ...] = (
    CODE,
    1,
    VALUE_SCHEMA,
    DESCRIPTION,
    SOURCE_REF,
    SECTION,
    "0066",
    "SYSTEM",
)


def upgrade() -> None:
    """Create T-PLT-47 and append correction 1 of the retention parameter."""
    jsonb = ops.NamedType("jsonb")
    ops.create_global_table(
        TABLE,
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("correction_no", sa.Integer(), nullable=False),
        sa.Column("value_schema", jsonb, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("applied_by_revision", sa.Text(), nullable=False),
        primary_key=("code", "correction_no"),
        standard_sets=["SC-C"],
        checks=[("ck_registry_parameter_correction__correction_no", "correction_no >= 1")],
    )
    ops.add_global_fk(TABLE, "code", "registry_parameter", target_column="code")
    ops.apply_class(TABLE, "IM-A", global_reference=True)
    ops.insert_rows(TABLE, COLUMNS, [CORRECTION])


def downgrade() -> None:
    """Drop only the table this revision created (DG-MIG-04); the seeded catalogue stays."""
    ops.drop_global_table(TABLE)
