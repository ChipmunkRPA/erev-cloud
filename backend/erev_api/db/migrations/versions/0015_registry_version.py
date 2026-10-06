"""BUILD_SPEC item PLF-13: registry versions and setting resolution.

04 ids created: E-02 ``book_code``; T-PLT-32 ``registry_version`` (IM-P, SC-V; RLS-TE, where a row
without ``entity_id`` is tenant-wide and visible to every scope) with ``ux_registry_version__no``
and the DB-04 trigger ``tg_registry_version__config_version`` (scope key ``category``, ``scope``,
``book_code``, ``entity_id``). The foreign key ``registry_version.entity_id`` → ``legal_entity`` is
added by the revision that creates ``legal_entity`` (04 §18 rule 2).
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

# 04 §3.2 E-02.
BOOK_CODE = ("ASC606", "IFRS15", "LEGACY")


def _named(name: str) -> ops.NamedType:
    return ops.NamedType(name)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("book_code", BOOK_CODE)
    ops.create_tenant_table(
        "registry_version",
        sa.Column("category", _named("erev.registry_category"), nullable=False),
        sa.Column("scope", _named("erev.registry_scope"), nullable=False),
        sa.Column("book_code", _named("erev.book_code"), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("values", _named("jsonb"), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("preset_code", sa.Text(), nullable=True),
        sa.Column("test_evidence", _named("jsonb"), nullable=True),
        sa.Column("impact_simulation_file_id", sa.Uuid(), nullable=True),
        standard_sets=["SC-C", "SC-M", "SC-V"],
        checks=[
            ("ck_registry_version__scope", "scope IN ('TENANT', 'ENTITY', 'BOOK')"),
            ("ck_registry_version__book_code", "(scope = 'BOOK') = (book_code IS NOT NULL)"),
            ("ck_registry_version__entity_id", "(scope = 'ENTITY') = (entity_id IS NOT NULL)"),
            ("ck_registry_version__values", "jsonb_typeof(\"values\") = 'object'"),
        ],
    )
    # [J] SPEC-Q-178: 04 keys on coalesce(book_code::text, '') and coalesce(entity_id, <nil uuid>),
    # but an enum-to-text cast is not IMMUTABLE and cannot sit in an index. NULLS NOT DISTINCT gives
    # the same uniqueness; the §6.5 index helper does not render it.
    ops.execute(
        "CREATE UNIQUE INDEX ux_registry_version__no ON erev.registry_version "
        "(tenant_id, category, scope, book_code, entity_id, version_no) NULLS NOT DISTINCT"
    )
    ops.add_tenant_fk("registry_version", "impact_simulation_file_id", "file_object")
    ops.apply_class("registry_version", "IM-P")
    ops.enable_rls("registry_version", "RLS-TE", entity_column="entity_id", entity_nullable=True)
    ops.add_config_version_trigger(
        "registry_version", scope_columns=["category", "scope", "book_code", "entity_id"]
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("registry_version")
    ops.drop_enum("book_code")
