"""Retain configuration-change approval and evidence inputs."""

import json

from erev_api.db import migration_ops as ops

revision = "0317"
down_revision = "0316"
branch_labels = None
depends_on = None

OLD_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["approval_request", "approval_step", '
    '"approval_decision", "audit_event", "file_attachment"], "joins": '
    '["approval_step.approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id", '
    '"audit_event.approval_request_id = approval_request.id"], "filters": '
    '["approval_request.subject_type in subject_types (configuration subjects of E-08)", '
    '"decided from from_date to to_date inclusive", "requests whose every entity is in '
    "entity_codes, and tenant-level requests; a request of all entities when entity_codes "
    'names every entity"], "parameters": ["entity_codes", "from_date", "to_date", '
    '"subject_types", "known_at", "known_at_basis"]}}'
)

NEW_METADATA = (
    '{"ipe_logic": {"version": 1, "source_tables": ["approval_request", "approval_step", '
    '"approval_decision", "audit_event", "file_attachment"], "joins": '
    '["approval_step.approval_request_id = approval_request.id", '
    '"approval_decision.approval_request_id = approval_request.id", '
    '"audit_event.approval_request_id = approval_request.id"], "filters": ["same-source runs '
    "retain configuration approvals, subject/actor inputs and evidence counts; recompute "
    'author separation and rows without live reads", "approval_request.subject_type in '
    'subject_types (configuration subjects of E-08)", "decided from from_date to to_date '
    'inclusive", "requests whose every entity is in entity_codes, and tenant-level requests; '
    'a request of all entities when entity_codes names every entity"], "parameters": '
    '["entity_codes", "from_date", "to_date", "subject_types", "known_at", '
    '"known_at_basis"]}}'
)


def _metadata(encoded: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for column, value in json.loads(encoded).items():
        payload = json.dumps(value).replace("'", "''")
        ops.execute(
            "UPDATE erev.report_definition SET "  # noqa: S608 — frozen metadata
            + column
            + "='"
            + payload
            + "'::jsonb WHERE code='config_change_register' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_METADATA)


def downgrade() -> None:
    _metadata(OLD_METADATA)
