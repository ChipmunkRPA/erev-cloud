"""Describe original dated modification evidence in RPO rollforwards."""

from erev_api.db import migration_ops as ops

revision = "0236"
down_revision = "0235"
branch_labels = None
depends_on = None

CHANGES = (
    (
        "first-entry batches separate later estimate-event shares from new contracts when "
        "all changes fall within the range and no modification or cancellation competes",
        "first-entry batches separate later original estimate shares and dated "
        "fixed-boundary modification deltas from new contracts; modification "
        "decomposition requires complete event evidence and cancellations retain existing "
        "limits",
    ),
    (
        "dated fixed-allocation evidence reconciles to version remainders and excludes "
        "future estimate changes from earlier RPO; same-version estimate movements "
        "require complete original shares matching the dated allocation difference",
        "dated fixed-allocation evidence reconciles to version remainders and excludes "
        "future changes from earlier RPO; same-version estimate and modification "
        "movements require original shares and boundary deltas matching the dated "
        "allocation difference",
    ),
)


def _update(reverse: bool) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for old, new in CHANGES:
        if reverse:
            old, new = new, old
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic=jsonb_set(ipe_logic, '{filters}', "  # noqa: S608 -- fixed migration constants
            "(SELECT jsonb_agg(CASE value #>> '{}' "
            f"WHEN '{old}' THEN to_jsonb('{new}'::text) ELSE value END ORDER BY ord) "
            "FROM jsonb_array_elements(ipe_logic->'filters') WITH ORDINALITY AS f(value, ord))) "
            "WHERE code='rpo_rollforward' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _update(False)


def downgrade() -> None:
    _update(True)
