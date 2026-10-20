"""Retain period projection provenance independently of surviving schedule lines."""

import json

from erev_api.db import migration_ops as ops

revision = "0215"
down_revision = "0214"
branch_labels = None
depends_on = None

_UP = {
    "revenue_waterfall": {
        "source_tables": [
            "schedule_line",
            "subledger_line",
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "contract_version",
            "obligation_version",
            "contract",
            "customer",
            "legal_entity",
            "product",
            "period",
            "journal_line",
            "lock_snapshot",
            "combination_group_member",
            "contract_computation",
            "calc_trace",
        ],
        "filters": [
            "entity code in entity_codes and within the caller's entity scope",
            "book_code = book",
            "schedule_line.subject_type = 'obligation'",
            "per contract, the last contract_version of the book known "
            "at known_at along the contract's chain of combination "
            "groups, of the versions computed with the contract among "
            "their members (combination_group_member, "
            "contract_computation)",
            "period_key from from_period_key to to_period_key",
            "contract.external_id = contract_external_id when given",
            "with period_lock_id, the values frozen at that lock (lock_snapshot kind WATERFALL)",
            "historical time-based schedules freeze the original "
            "allocation segment at the reporting cut; dated "
            "projections reconcile to the remainder and retain "
            "cut-specific drill-through",
            "original period projections survive removed current "
            "schedule lines; source evidence is the contract version "
            "trace for the exact reporting cut and future period",
        ],
    },
    "rpo": {
        "source_tables": [
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "obligation_version",
            "schedule_line",
            "contract_version",
            "contract_computation",
            "computation_evidence",
            "contract",
            "customer",
            "product",
            "legal_entity",
            "period",
            "registry_version",
            "lock_snapshot",
            "combination_group_member",
            "calc_trace",
        ],
        "filters": [
            "entity code in entity_codes and within the caller's entity scope",
            "book_code = book",
            "per contract, the contract_version at the date along the contract's "
            "chain of combination groups: the versions recorded while the contract "
            "was a member of their group (combination_group_member)",
            "unsatisfied and partially satisfied obligations at the end of period_key",
            "remaining amounts by expected period of recognition, banded by time_bands (POL-201)",
            "section 2: contracts exempt under POL-197 to POL-200 set to APPLY",
            "with period_lock_id, the values frozen at that lock (lock_snapshot kind RPO)",
            "historical time-based schedules freeze the original allocation segment "
            "at the reporting cut; dated projections reconcile to the remainder and "
            "retain cut-specific drill-through",
            "original period projections survive removed current schedule lines; "
            "source evidence is the contract version trace for the exact reporting "
            "cut and future period",
        ],
    },
    "rpo_rollforward": {
        "source_tables": [
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "calc_trace",
            "obligation_version",
            "contract_version",
            "contract_computation",
            "computation_evidence",
            "contract_event",
            "contract",
            "period",
            "lock_snapshot",
            "combination_group_member",
        ],
        "filters": [
            "entity code in entity_codes and within the caller's entity scope",
            "book_code = book",
            "opening: RPO at the end of the period before "
            "from_period_key; closing: RPO at the end of to_period_key",
            "per contract, the contract_version at the date along the "
            "contract's chain of combination groups: the versions "
            "recorded while the contract was a member of their group "
            "(combination_group_member)",
            "movements classified by the contract_event that caused each contract version",
            "full RPO exemption eligibility is evaluated per retained "
            "version; opening and closing exclusions are separate, with "
            "eligibility changes in EXEMPTIONS",
            "terminal cancellations remove only unrecognized allocation; "
            "retained cancelled-version revenue separates period "
            "recognition and late restatement",
            "cancellation and re-entry histories use separate disclosure "
            "segments; re-entry admits remaining RPO and revenue "
            "excludes changes while outside disclosure",
            "mixed modification and estimate changes use original "
            "event-specific estimate shares reconciled to each price "
            "delta; unsupported or incomplete evidence stays unexplained",
            "with period_lock_id, the values frozen at that lock "
            "(lock_snapshot kind RPO_ROLLFORWARD)",
            "measurement-only estimate pins prove no allocation "
            "movement; inception estimates and legacy pins without an "
            "explicit effect are not assumed to have zero impact",
            "first-entry batches separate later estimate-event shares "
            "from new contracts when all changes fall within the range "
            "and no modification or cancellation competes",
            "dated fixed-allocation evidence reconciles to version "
            "remainders and excludes future estimate changes from "
            "earlier RPO; same-version estimate movements require "
            "complete original shares matching the dated allocation "
            "difference",
            "historical time-based schedules freeze the original "
            "allocation segment at the reporting cut; dated projections "
            "reconcile to the remainder and retain cut-specific "
            "drill-through",
            "original period projections survive removed current "
            "schedule lines; source evidence is the contract version "
            "trace for the exact reporting cut and future period",
        ],
    },
}

_DOWN = {
    "revenue_waterfall": {
        "source_tables": [
            "schedule_line",
            "subledger_line",
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "contract_version",
            "obligation_version",
            "contract",
            "customer",
            "legal_entity",
            "product",
            "period",
            "journal_line",
            "lock_snapshot",
            "combination_group_member",
            "contract_computation",
        ],
        "filters": [
            "entity code in entity_codes and within the caller's entity scope",
            "book_code = book",
            "schedule_line.subject_type = 'obligation'",
            "per contract, the last contract_version of the book known "
            "at known_at along the contract's chain of combination "
            "groups, of the versions computed with the contract among "
            "their members (combination_group_member, "
            "contract_computation)",
            "period_key from from_period_key to to_period_key",
            "contract.external_id = contract_external_id when given",
            "with period_lock_id, the values frozen at that lock (lock_snapshot kind WATERFALL)",
            "historical time-based schedules freeze the original "
            "allocation segment at the reporting cut; dated "
            "projections reconcile to the remainder and retain "
            "cut-specific drill-through",
        ],
    },
    "rpo": {
        "source_tables": [
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "obligation_version",
            "schedule_line",
            "contract_version",
            "contract_computation",
            "computation_evidence",
            "contract",
            "customer",
            "product",
            "legal_entity",
            "period",
            "registry_version",
            "lock_snapshot",
            "combination_group_member",
        ],
        "filters": [
            "entity code in entity_codes and within the caller's entity scope",
            "book_code = book",
            "per contract, the contract_version at the date along the contract's "
            "chain of combination groups: the versions recorded while the contract "
            "was a member of their group (combination_group_member)",
            "unsatisfied and partially satisfied obligations at the end of period_key",
            "remaining amounts by expected period of recognition, banded by time_bands (POL-201)",
            "section 2: contracts exempt under POL-197 to POL-200 set to APPLY",
            "with period_lock_id, the values frozen at that lock (lock_snapshot kind RPO)",
            "historical time-based schedules freeze the original allocation segment "
            "at the reporting cut; dated projections reconcile to the remainder and "
            "retain cut-specific drill-through",
        ],
    },
    "rpo_rollforward": {
        "source_tables": [
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "calc_trace",
            "obligation_version",
            "contract_version",
            "contract_computation",
            "computation_evidence",
            "contract_event",
            "contract",
            "period",
            "lock_snapshot",
            "combination_group_member",
        ],
        "filters": [
            "entity code in entity_codes and within the caller's entity scope",
            "book_code = book",
            "opening: RPO at the end of the period before "
            "from_period_key; closing: RPO at the end of to_period_key",
            "per contract, the contract_version at the date along the "
            "contract's chain of combination groups: the versions "
            "recorded while the contract was a member of their group "
            "(combination_group_member)",
            "movements classified by the contract_event that caused each contract version",
            "full RPO exemption eligibility is evaluated per retained "
            "version; opening and closing exclusions are separate, with "
            "eligibility changes in EXEMPTIONS",
            "terminal cancellations remove only unrecognized allocation; "
            "retained cancelled-version revenue separates period "
            "recognition and late restatement",
            "cancellation and re-entry histories use separate disclosure "
            "segments; re-entry admits remaining RPO and revenue "
            "excludes changes while outside disclosure",
            "mixed modification and estimate changes use original "
            "event-specific estimate shares reconciled to each price "
            "delta; unsupported or incomplete evidence stays unexplained",
            "with period_lock_id, the values frozen at that lock "
            "(lock_snapshot kind RPO_ROLLFORWARD)",
            "measurement-only estimate pins prove no allocation "
            "movement; inception estimates and legacy pins without an "
            "explicit effect are not assumed to have zero impact",
            "first-entry batches separate later estimate-event shares "
            "from new contracts when all changes fall within the range "
            "and no modification or cancellation competes",
            "dated fixed-allocation evidence reconciles to version "
            "remainders and excludes future estimate changes from "
            "earlier RPO; same-version estimate movements require "
            "complete original shares matching the dated allocation "
            "difference",
            "historical time-based schedules freeze the original "
            "allocation segment at the reporting cut; dated projections "
            "reconcile to the remainder and retain cut-specific "
            "drill-through",
        ],
    },
}


def _apply(definitions: dict) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for code, fields in definitions.items():
        value = json.dumps(fields).replace("'", "''")
        ops.execute(
            "UPDATE erev.report_definition SET ipe_logic = ipe_logic || "  # noqa: S608
            f"'{value}'::jsonb WHERE code = '{code}' AND version = 1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _apply(_UP)


def downgrade() -> None:
    _apply(_DOWN)
