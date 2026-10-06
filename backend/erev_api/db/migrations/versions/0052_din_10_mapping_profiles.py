"""BUILD_SPEC item DIN-10: mapping profiles.

04 ids created: T-IMP-06 ``import_mapping_profile`` (IM-P, SC-V, RLS-T) with the key
``ux_import_mapping_profile__version``, the check ``ck_import_mapping_profile__mappings`` (a JSON
object) and the DB-04 trigger ``tg_import_mapping_profile__config_version`` (scope key ``code``);
the foreign key ``import_upload.mapping_profile_id`` → ``import_mapping_profile``, which revision
0044 left to this revision (DG-MIG-03).

One table is added.
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

PROFILE = "import_mapping_profile"


def _named(name: str) -> ops.NamedType:
    return ops.NamedType(name)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_tenant_table(
        PROFILE,
        sa.Column("code", _named("erev.code"), nullable=False),
        sa.Column("name", _named("erev.label"), nullable=False),
        sa.Column("template_code", sa.Text(), nullable=False),
        sa.Column("mappings", _named("jsonb"), nullable=False),
        standard_sets=["SC-C", "SC-M", "SC-V"],
        checks=[("ck_import_mapping_profile__mappings", "jsonb_typeof(mappings) = 'object'")],
        unique=[("ux_import_mapping_profile__version", ["tenant_id", "code", "version_no"], None)],
    )
    ops.apply_class(PROFILE, "IM-P")
    ops.enable_rls(PROFILE, "RLS-T")
    ops.add_config_version_trigger(PROFILE, scope_columns=["code"])
    ops.add_tenant_fk("import_upload", "mapping_profile_id", PROFILE)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute("ALTER TABLE erev.import_upload DROP CONSTRAINT fk_import_upload__mapping_profile")
    ops.drop_tenant_table(PROFILE)
