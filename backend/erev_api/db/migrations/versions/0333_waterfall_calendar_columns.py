"""Align new waterfall columns to each entity's actual reporting intervals."""

import json

from erev_api.db import migration_ops as ops

revision = "0333"
down_revision = "0332"
branch_labels = None
depends_on = None

OLD_IPE = {
    "version": 1,
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
        "contract_event",
        "subledger_posting_commit",
        "historical_source_commit",
        "report_source_revision",
    ],
    "joins": [
        "schedule_line.contract_version_id = contract_version.id",
        "schedule_line.subject_id = obligation_version.obligation_id and "
        "schedule_line.contract_version_id = obligation_version.contract_version_id",
        "schedule_line.contract_id = contract.id",
        "contract.customer_id = customer.id",
        "schedule_line.entity_id = legal_entity.id",
        "schedule_line.period_id = period.id",
        "obligation_version.product_id = product.id",
        "combination_group_member.combination_group_id = contract_version.combination_group_id",
        "contract_version.contract_computation_id = contract_computation.id",
    ],
    "filters": [
        "entity code in entity_codes and within the caller's entity scope",
        "book_code = book",
        "schedule_line.subject_type = 'obligation'",
        "per contract, the last contract_version of the book known at known_at "
        "along the contract's chain of combination groups, of the versions "
        "computed with the contract among their members "
        "(combination_group_member, contract_computation)",
        "period_key from from_period_key to to_period_key",
        "contract.external_id = contract_external_id when given",
        "with period_lock_id, the values frozen at that lock (lock_snapshot kind WATERFALL)",
        "historical time-based schedules freeze the original allocation segment "
        "at the reporting cut; dated projections reconcile to the remainder and "
        "retain cut-specific drill-through",
        "original period projections survive removed current schedule lines; "
        "source evidence is the contract version trace for the exact reporting "
        "cut and future period",
        "scheduled and awaiting remainders use original period-level "
        "recognition-hold and pattern evidence reconciled to the version state; "
        "future holds do not alter earlier time-based projections",
        "fixed-only manual releases, deferrals and schedule overrides replay only "
        "events effective at the reporting cut; unsupported component mixtures or "
        "unreproducible snapshots retain explicit projection errors",
        "manual projection freezes realized usage at the reporting cut and "
        "replays fixed plus PERIOD_VC targets without proportional allocation; "
        "schedule overrides retain anchor-period realized consideration and "
        "recognize subsequent usage immediately; royalty and netted projections "
        "remain unavailable",
        "royalty manual projections freeze original statements and effective "
        "estimate pins at the reporting cut; minimum guarantees and recognized "
        "royalty sources must remain stable over the frozen horizon; schedule "
        "overrides retain anchor royalties and subsequent signed royalty changes "
        "separately",
        "Step-1 netted forecasts freeze original deposit recognitions and cite "
        "their attributed shares; a separate dated reporting remainder excludes "
        "already-recognized deposit revenue while preserving contract measurement "
        "balances; projected future periods must reconcile to that net remainder",
        "Waterfall entry dates come from the first included contract version on "
        "its membership chain and its book-specific entry event; contracts "
        "entering after the performing entity as-of period are excluded; retained "
        "entry bindings and legacy populations remain unchanged on rerun",
        "subledger_commit_visibility_v1 requires original PostgreSQL posting "
        "commit time at or before the historical cutoff; retained commit evidence "
        "is immutable; older bindings preserve their original seal-time "
        "interpretation",
        "historical_source_commit_v1 retains original event and contract-version "
        "transaction commits; new event/version extracts and BBR event sources "
        "use commit cutoffs; historical version populations exclude later commits "
        "before latest selection; bound inputs keep their original interpretation",
        "Historical journal populations use original line commits and the latest "
        "committed journal-run/batch source revision at known_at. New journal "
        "incremental extracts use line commits in (known_since, known_at]; "
        "retained legacy bindings keep their original basis.",
    ],
    "parameters": [
        "entity_codes",
        "book",
        "from_period_key",
        "to_period_key",
        "as_of",
        "known_at",
        "period_lock_id",
        "row_dimension",
        "granularity",
        "measure",
        "contract_external_id",
        "currency_view",
        "filters",
        "known_at_basis",
    ],
}

NEW_IPE = {
    "version": 1,
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
        "contract_event",
        "subledger_posting_commit",
        "historical_source_commit",
        "report_source_revision",
    ],
    "joins": [
        "schedule_line.contract_version_id = contract_version.id",
        "schedule_line.subject_id = obligation_version.obligation_id and "
        "schedule_line.contract_version_id = obligation_version.contract_version_id",
        "schedule_line.contract_id = contract.id",
        "contract.customer_id = customer.id",
        "schedule_line.entity_id = legal_entity.id",
        "schedule_line.period_id = period.id",
        "obligation_version.product_id = product.id",
        "combination_group_member.combination_group_id = contract_version.combination_group_id",
        "contract_version.contract_computation_id = contract_computation.id",
    ],
    "filters": [
        "New runs align waterfall columns by actual interval dates across entity "
        "calendars; different dates remain separate, identical dates may use "
        "different local period keys, and cells and contributors use the owning "
        "entity period map; matching calendar layouts keep fiscal labels and "
        "older bound runs keep their original column interpretation",
        "entity code in entity_codes and within the caller's entity scope",
        "book_code = book",
        "schedule_line.subject_type = 'obligation'",
        "per contract, the last contract_version of the book known at known_at "
        "along the contract's chain of combination groups, of the versions "
        "computed with the contract among their members "
        "(combination_group_member, contract_computation)",
        "period_key from from_period_key to to_period_key",
        "contract.external_id = contract_external_id when given",
        "with period_lock_id, the values frozen at that lock (lock_snapshot kind WATERFALL)",
        "historical time-based schedules freeze the original allocation segment "
        "at the reporting cut; dated projections reconcile to the remainder and "
        "retain cut-specific drill-through",
        "original period projections survive removed current schedule lines; "
        "source evidence is the contract version trace for the exact reporting "
        "cut and future period",
        "scheduled and awaiting remainders use original period-level "
        "recognition-hold and pattern evidence reconciled to the version state; "
        "future holds do not alter earlier time-based projections",
        "fixed-only manual releases, deferrals and schedule overrides replay only "
        "events effective at the reporting cut; unsupported component mixtures or "
        "unreproducible snapshots retain explicit projection errors",
        "manual projection freezes realized usage at the reporting cut and "
        "replays fixed plus PERIOD_VC targets without proportional allocation; "
        "schedule overrides retain anchor-period realized consideration and "
        "recognize subsequent usage immediately; royalty and netted projections "
        "remain unavailable",
        "royalty manual projections freeze original statements and effective "
        "estimate pins at the reporting cut; minimum guarantees and recognized "
        "royalty sources must remain stable over the frozen horizon; schedule "
        "overrides retain anchor royalties and subsequent signed royalty changes "
        "separately",
        "Step-1 netted forecasts freeze original deposit recognitions and cite "
        "their attributed shares; a separate dated reporting remainder excludes "
        "already-recognized deposit revenue while preserving contract measurement "
        "balances; projected future periods must reconcile to that net remainder",
        "Waterfall entry dates come from the first included contract version on "
        "its membership chain and its book-specific entry event; contracts "
        "entering after the performing entity as-of period are excluded; retained "
        "entry bindings and legacy populations remain unchanged on rerun",
        "subledger_commit_visibility_v1 requires original PostgreSQL posting "
        "commit time at or before the historical cutoff; retained commit evidence "
        "is immutable; older bindings preserve their original seal-time "
        "interpretation",
        "historical_source_commit_v1 retains original event and contract-version "
        "transaction commits; new event/version extracts and BBR event sources "
        "use commit cutoffs; historical version populations exclude later commits "
        "before latest selection; bound inputs keep their original interpretation",
        "Historical journal populations use original line commits and the latest "
        "committed journal-run/batch source revision at known_at. New journal "
        "incremental extracts use line commits in (known_since, known_at]; "
        "retained legacy bindings keep their original basis.",
    ],
    "parameters": [
        "entity_codes",
        "book",
        "from_period_key",
        "to_period_key",
        "as_of",
        "known_at",
        "period_lock_id",
        "row_dimension",
        "granularity",
        "measure",
        "contract_external_id",
        "currency_view",
        "filters",
        "known_at_basis",
    ],
}


def _set(value: dict) -> None:
    payload = json.dumps(value).replace("'", "''")
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET ipe_logic='"  # noqa: S608 — frozen metadata
        + payload
        + "'::jsonb WHERE code='revenue_waterfall' AND version=1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _set(NEW_IPE)


def downgrade() -> None:
    _set(OLD_IPE)
