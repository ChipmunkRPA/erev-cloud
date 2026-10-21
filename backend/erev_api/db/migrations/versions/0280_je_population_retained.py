"""Describe retained JE Population source records and committed lifecycle reads."""

import json

from erev_api.db import migration_ops as ops

revision = "0280"
down_revision = "0279"
branch_labels = None
depends_on = None

OLD_IPE = (
    '{"je_population":{"version":1,"source_tables":["journal_line","journal_entry","journal_b'
    'atch","journal_run","posting_ack","gl_account","legal_entity","period","contract","oblig'
    'ation","lock_snapshot"],"joins":["journal_line.journal_entry_id = journal_entry.id","jou'
    'rnal_line.journal_batch_id = journal_batch.id","journal_batch.journal_run_id = journal_r'
    'un.id","posting_ack.journal_batch_id = journal_batch.id","journal_line.gl_account_id = g'
    'l_account.id","journal_line.period_id = period.id","journal_line.contract_id = contract.'
    'id","journal_line.obligation_id = obligation.id"],"filters":["entity code in entity_code'
    's and within the caller\'s entity scope","book_code = book","period_key from from_period_'
    'key to to_period_key","include_cancelled false: runs not cancelled","with period_lock_id'
    ', the values frozen at that lock (lock_snapshot kind JE_POPULATION)"],"parameters":["ent'
    'ity_codes","book","from_period_key","to_period_key","period_lock_id","include_cancelled"'
    ',"known_at","known_at_basis"]}}'
)

NEW_IPE = (
    '{"je_population":{"version":1,"source_tables":["journal_line","journal_entry","journal_b'
    'atch","journal_run","posting_ack","gl_account","legal_entity","period","contract","oblig'
    'ation","lock_snapshot","report_source_revision","historical_source_commit"],"joins":["jo'
    'urnal_line.journal_entry_id = journal_entry.id","journal_line.journal_batch_id = journal'
    '_batch.id","journal_batch.journal_run_id = journal_run.id","posting_ack.journal_batch_id'
    ' = journal_batch.id","journal_line.gl_account_id = gl_account.id","journal_line.period_i'
    'd = period.id","journal_line.contract_id = contract.id","journal_line.obligation_id = ob'
    'ligation.id"],"filters":["entity code in entity_codes and within the caller\'s entity sco'
    'pe","book_code = book","period_key from from_period_key to to_period_key","include_cance'
    'lled false: runs not cancelled","historical basis: original line commits and committed r'
    'un/batch revisions by known_at","je_population_inputs_v1 retains input rows, labels and '
    "independent run debit totals; same-source rebuilds recompute rows and controls without q"
    'uerying mutable sources","record basis and DATASET_FREEZE preserve transaction-local jou'
    'rnal visibility","first-generation ancillary approval/ack/name reads retain existing cut'
    "off semantics; retention guarantees repeatability, not complete historical reconstructio"
    'n","with period_lock_id, the values frozen at that lock (lock_snapshot kind JE_POPULATIO'
    'N)"],"parameters":["entity_codes","book","from_period_key","to_period_key","period_lock_'
    'id","include_cancelled","known_at","known_at_basis"]}}'
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
