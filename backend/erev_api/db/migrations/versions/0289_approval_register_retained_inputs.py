"""Describe retained approval-register inputs and stable same-source rebuilds."""

import json

from erev_api.db import migration_ops as ops

revision = "0289"
down_revision = "0288"
branch_labels = None
depends_on = None

OLD_IPE = (
    '{"approvals_register": {"version": 1, "source_tables": ["approval_request", "approval'
    '_step", "approval_decision", "app_user", "legal_entity", "report_source_revision", "h'
    'istorical_source_commit"], "joins": ["approval_step.approval_request_id = approval_re'
    'quest.id", "approval_decision.approval_step_id = approval_step.id", "approval_decisio'
    'n.approver_id = app_user.id", "approval_request.entity_id = legal_entity.id"], "filte'
    'rs": ["requests whose every entity is in entity_codes, and tenant-level requests; a r'
    'equest of all entities when entity_codes names every entity", "submitted from from_da'
    'te to to_date inclusive", "subject_types and status when given", "historical basis se'
    "lects committed request revisions and original decision commits at known_at before st"
    'atus filtering; record basis preserves business-time behavior", "display labels and a'
    'ncillary rule/step references retain existing read semantics"], "parameters": ["entit'
    'y_codes", "from_date", "to_date", "subject_types", "status", "currency_view", "known_'
    'at", "known_at_basis"]}}'
)

NEW_IPE = (
    '{"approvals_register": {"version": 1, "source_tables": ["approval_request", "approval'
    '_step", "approval_decision", "app_user", "legal_entity", "report_source_revision", "h'
    'istorical_source_commit"], "joins": ["approval_step.approval_request_id = approval_re'
    'quest.id", "approval_decision.approval_step_id = approval_step.id", "approval_decisio'
    'n.approver_id = app_user.id", "approval_request.entity_id = legal_entity.id"], "filte'
    'rs": ["requests whose every entity is in entity_codes, and tenant-level requests; a r'
    'equest of all entities when entity_codes names every entity", "submitted from from_da'
    'te to to_date inclusive", "subject_types and status when given", "historical basis se'
    "lects committed request revisions and original decision commits at known_at before st"
    'atus filtering; record basis preserves business-time behavior", "first-generation dis'
    'play labels and rule/step references retain existing read semantics", "approvals_regi'
    "ster_inputs_v1 retains requests, decisions, names, rules, entity codes and first step"
    's; same-source reruns rebuild rows and totals without live source reads"], "parameter'
    's": ["entity_codes", "from_date", "to_date", "subject_types", "status", "currency_vie'
    'w", "known_at", "known_at_basis"]}}'
)


def _metadata(encoded: str) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for code, ipe in json.loads(encoded).items():
        payload = json.dumps(ipe).replace("'", "''")
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic='"  # noqa: S608 — frozen metadata
            + payload
            + "'::jsonb WHERE code='"
            + code
            + "' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _metadata(NEW_IPE)


def downgrade() -> None:
    _metadata(OLD_IPE)
