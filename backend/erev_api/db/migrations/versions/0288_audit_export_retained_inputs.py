"""Describe retained audit inputs and original commit cutoffs in the catalogue."""

import json

from erev_api.db import migration_ops as ops

revision = "0288"
down_revision = "0287"
branch_labels = None
depends_on = None

OLD_IPE = (
    '{"audit_log_export": {"version": 1, "source_tables": ["audit_event", "audit_event_con'
    'tract"], "joins": ["audit_event_contract.audit_event_id = audit_event.id"], "filters"'
    ': ["audit_event.occurred_at from from to to", "object_type, object_id, actor_id and a'
    'ction when given", "outcome among the literals given", "with contract_id the events t'
    'hat name the contract (audit_event_contract)", "chain_seq order; JSON columns redacte'
    'd per erev_api.audit.REDACT"], "parameters": ["entity_codes", "from", "to", "object_t'
    'ype", "object_id", "contract_id", "actor_id", "action", "outcome", "known_at", "known'
    '_at_basis"]}}'
)

NEW_IPE = (
    '{"audit_log_export": {"version": 1, "source_tables": ["audit_event", "audit_event_con'
    'tract", "historical_source_commit"], "joins": ["audit_event_contract.audit_event_id ='
    ' audit_event.id"], "filters": ["audit_event.occurred_at from from to to", "object_typ'
    'e, object_id, actor_id and action when given", "outcome among the literals given", "w'
    'ith contract_id the events that name the contract (audit_event_contract)", "historica'
    "l basis requires original audit commits by known_at; record basis preserves transacti"
    'on-local visibility", "audit_log_export_inputs_v1 retains redacted input events and h'
    "istorical commit evidence; same-source reruns rebuild rows and controls without live "
    'audit reads", "chain_seq order; JSON columns redacted per erev_api.audit.REDACT"], "p'
    'arameters": ["entity_codes", "from", "to", "object_type", "object_id", "contract_id",'
    ' "actor_id", "action", "outcome", "known_at", "known_at_basis"]}}'
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
