"""Seed the release-validation sampling parameter on existing databases."""

from erev_api.db import migration_ops as ops

revision = "0162"
down_revision = "0161"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Frozen seed metadata; 0003 may already have supplied it on a fresh installation.
    ops.execute("""
        INSERT INTO erev.registry_parameter
          (code, pol_id, category, value_schema, default_asc606, default_ifrs15,
           is_forced_asc606, is_forced_ifrs15, legacy_parity_value, allowed_levels,
           pin, approval_code, description, source_ref, section)
        VALUES ('platform.replay_seed', NULL, 'PLATFORM',
          '{"type":"integer","minimum":-9223372036854775808,"maximum":9223372036854775807}',
          '20260912', NULL, false, false, '20260912', '{TENANT}', 'P', 'CFG',
          'Deterministic seed for release-validation sampling; frozen per attempt.',
          'REQ-OPS-011; RCP-29', 'Platform')
        ON CONFLICT (code) DO NOTHING
    """)


def downgrade() -> None:
    """Keep the append-only catalogue row, as in 0063; 0003 ultimately drops its table.

    Retaining it preserves the meaning of existing configuration versions and frozen attempts.
    """
