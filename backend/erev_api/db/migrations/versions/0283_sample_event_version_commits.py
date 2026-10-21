"""Describe original event/version commit cutoffs in sample evidence."""

import json

from erev_api.db import migration_ops as ops

revision = "0283"
down_revision = "0282"
branch_labels = None
depends_on = None

OLD_IPE = (
    '{"contract_sample_pack":{"version":1,"source_tables":["evidence_pack","contract","contra'
    'ct_event","contract_version","obligation_version","schedule_line","subledger_line","calc'
    '_trace","journal_line","journal_entry","journal_batch","journal_run","report_source_revi'
    'sion","historical_source_commit","subledger_posting_commit"],"joins":["evidence_pack.con'
    'tract_ids holds the sampled contracts","contract_event.contract_id = contract.id","oblig'
    'ation_version.contract_id = contract.id","schedule_line.contract_id = contract.id","subl'
    'edger_line.contract_id = contract.id","calc_trace.contract_version_id = contract_version'
    '.id"],"filters":["contract.external_id in contract_external_ids (1 to 50)","figures as o'
    'f as_of and known at known_at","sample/journals.json v2 uses original journal/underlying'
    " posting commits and committed run/batch revisions; cancelled lines remain explicitly la"
    'belled at cutoff","journal sample totals retain whole aggregated lines and separate samp'
    'led contributions; old archives remain unchanged","entity code in entity_codes and withi'
    'n the caller\'s entity scope"],"parameters":["entity_codes","contract_external_ids","as_o'
    'f","known_at","known_at_basis"]}}'
)

NEW_IPE = (
    '{"contract_sample_pack":{"version":1,"source_tables":["evidence_pack","contract","contra'
    'ct_event","contract_version","obligation_version","schedule_line","subledger_line","calc'
    '_trace","journal_line","journal_entry","journal_batch","journal_run","report_source_revi'
    'sion","historical_source_commit","subledger_posting_commit"],"joins":["evidence_pack.con'
    'tract_ids holds the sampled contracts","contract_event.contract_id = contract.id","oblig'
    'ation_version.contract_id = contract.id","schedule_line.contract_id = contract.id","subl'
    'edger_line.contract_id = contract.id","calc_trace.contract_version_id = contract_version'
    '.id"],"filters":["contract.external_id in contract_external_ids (1 to 50)","figures as o'
    'f as_of and known at known_at","sample/journals.json v2 uses original journal/underlying'
    " posting commits and committed run/batch revisions; cancelled lines remain explicitly la"
    'belled at cutoff","sample event files and computations index v2 require original event/v'
    "ersion commits by known_at before latest-version selection; retain commit timestamps and"
    ' full schedules","journal sample totals retain whole aggregated lines and separate sampl'
    'ed contributions; old archives remain unchanged","entity code in entity_codes and within'
    ' the caller\'s entity scope"],"parameters":["entity_codes","contract_external_ids","as_of'
    '","known_at","known_at_basis"]}}'
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
