"""Original acquired-cutover balance and maturity report sources."""

import json

from erev_api.db import migration_ops as ops

revision = "0346"
down_revision = "0345"
branch_labels = None
depends_on = None

OLD = {
    "contract_balances": {
        "version": 1,
        "source_tables": [
            "contract_version_balance",
            "contract_version",
            "contract",
            "customer",
            "legal_entity",
            "period",
            "lock_snapshot",
            "combination_group_member",
            "contract_computation",
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "reconciliation",
            "report_source_revision",
            "historical_source_commit",
        ],
        "joins": [
            "contract_version_balance.contract_version_id = contract_version.id",
            "contract_version_balance.contract_id = contract.id",
            "contract.customer_id = customer.id",
            "contract_version_balance.entity_id = legal_entity.id",
            "combination_group_member.combination_group_id = contract_version.combination_group_id",
            "contract_version.contract_computation_id = contract_computation.id",
        ],
        "filters": [
            "GL bridge v7 selects only source revisions committed at or "
            "before known_at, then ranks source identities and states "
            "in one statement; original commit time is retained with "
            "the revision; retained v1-v6 comparisons keep their "
            "original rules",
            "entity code in entity_codes and within the caller's entity scope",
            "book_code = book",
            "per contract, the last contract_version known at known_at "
            "along the contract's chain of combination groups, of the "
            "versions computed with the contract among their members "
            "(combination_group_member, contract_computation), read at "
            "the end of period_key",
            "include_zero false: contracts with a non-zero balance only",
            "contract.external_id = contract_external_id when given",
            "with period_lock_id, the values frozen at that lock "
            "(lock_snapshot kind CONTRACT_BALANCES)",
            "GL bridge v2 compares report, retained reconciliation "
            "subledger and GL per entity and role in functional "
            "currency; either nonzero leg fails even when net "
            "differences cancel; missing subledger evidence is "
            "unavailable and v1 bindings retain two-way semantics",
            "GL bridge v3 requires the latest retained reconciliation "
            "to be reviewed or certified; draft, prepared, reopened or "
            "missing status is unavailable; historical v1 and v2 "
            "bindings preserve their original arithmetic controls",
            "GL bridge v4 selects the latest source identity before "
            "checking mutable state; a source changed after the report "
            "cutoff is unavailable and never replaced by an older "
            "reviewed source; retained v1-v3 bindings remain unchanged",
            "GL bridge v5 reads the latest database-captured "
            "reconciliation revision at the report cutoff for the "
            "latest source identity, preserving original review state "
            "and totals after later changes; migration baselines attest "
            "only to capture-time state and uncovered history is "
            "unavailable; original revision identity and amounts are "
            "bound for reruns; retained v1-v4 comparisons keep their "
            "prior rules",
            "GL bridge v6 selects source identities and their latest "
            "captured states from immutable revisions in one database "
            "statement for all requested entities; a concurrent source "
            "change cannot mix identity and review snapshots; timestamp "
            "cutoffs still do not reconstruct arbitrary historical "
            "commit visibility; retained v1-v5 comparisons use their "
            "bound evidence unchanged",
            "historical_source_commit_v1 retains original event and "
            "contract-version transaction commits; new event/version "
            "extracts and BBR event sources use commit cutoffs; "
            "historical version populations exclude later commits "
            "before latest selection; bound inputs keep their original "
            "interpretation",
        ],
        "parameters": [
            "entity_codes",
            "book",
            "period_key",
            "period_lock_id",
            "include_zero",
            "contract_external_id",
            "currency_view",
            "known_at",
            "known_at_basis",
        ],
    },
    "contract_balance_rollforward": {
        "version": 1,
        "source_tables": [
            "subledger_line",
            "subledger_posting",
            "close_pass_evidence",
            "computation_evidence",
            "contract_version",
            "subledger_posting_seal",
            "file_object",
            "contract_version_balance",
            "calc_trace",
            "fx_layer_movement",
            "contract_event",
            "contract",
            "customer",
            "period",
            "lock_snapshot",
            "reconciliation",
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "report_source_revision",
            "subledger_posting_commit",
            "historical_source_commit",
        ],
        "joins": [
            "subledger_line.subledger_posting_id = subledger_posting.id",
            "close_pass_evidence.subledger_posting_id = "
            "subledger_posting.id; retained entry index "
            "identifies the source group",
            "close_pass_evidence.file_id = file_object.id; "
            "authenticated pass input/output and paid-line "
            "history",
            "subledger_line.contract_version_id = "
            "contract_version.id; "
            "contract_version.contract_computation_id = "
            "computation_evidence.contract_computation_id",
            "computation_evidence retains original input/output files and per-book seal cutoff",
            "subledger_line.contract_id = contract.id",
            "subledger_line.period_id = period.id",
            "contract_version_balance.contract_id = contract.id",
            "calc_trace.contract_version_id = contract_version_balance.contract_version_id",
            "contract_event.contract_id = contract.id (billing documents)",
            "contract.customer_id = customer.id",
        ],
        "filters": [
            "GL bridge v7 selects only source revisions "
            "committed at or before known_at, then ranks "
            "source identities and states in one statement; "
            "original commit time is retained with the "
            "revision; retained v1-v6 comparisons keep their "
            "original rules",
            "entity code in entity_codes and within the caller's entity scope",
            "book_code = book",
            "period_key from from_period_key to to_period_key",
            "subledger_line.account_role is a contract balance role",
            "opening: balance at the end of the period "
            "before from_period_key; closing: balance at the "
            "end of to_period_key",
            "billing that posts no line (billing.posting = "
            "ERP): per period the delta of the calc_trace "
            "node billed_unconditional_cum less the BILLING "
            "and CREDIT_MEMO lines of the role; where not "
            "zero and the role holds no such line, the "
            "period's kept BILLING_RECORDED lines and "
            "CREDIT_MEMO_RECORDED events, not voided, at "
            "their effective dates",
            "functional/reporting close FX uses signed "
            "asset/liability source layers, prior targets "
            "and recursively retained paid lines",
            "source binding retains posted-history "
            "dependencies and evidence hashes; unavailable "
            "source attribution refuses",
            "EVENT FX nets actual retained deltas by dated "
            "source before billing or revenue; source-backed "
            "reports replace synthetic settlement offsets",
            "combined memo billing reads authorized "
            "same-version member layers; credit-memo spot "
            "portions follow retained relief order with "
            "cumulative rounding",
            "combined liability reclassifications bridge "
            "original layer carrying and retained member "
            "presentation at each endpoint, plus "
            "cross-member memo source transfers; each "
            "original computation group conserves zero and "
            "evidence is bound",
            "new member presentation bridges include all "
            "foreign contract/entity endpoints, even without "
            "a memo or FX journal; legacy v1 bindings retain "
            "memo-triggered scope",
            "cross-member revenue reconciles the entire "
            "posted delta to original signed sources; "
            "liability consumption separately reproduces "
            "retained owner/layer relief while own-member "
            "asset creation remains asset revenue; original "
            "layer dates classify opening consumption and v4 "
            "presentation binds the liability relief amounts",
            "new source-backed revenue runs recursively "
            "reconcile original functional targets, prior "
            "targets and sealed paid-line history; reversals "
            "must reproduce the same owner/layer relief "
            "population and preserve evidence on rerun",
            "v5 presentation includes own-member asset "
            "settlements and newly created liabilities from "
            "original signed revenue sources, including "
            "returns whose source consumption predates the "
            "selected range; new liabilities are not opening "
            "relief",
            "cross-member revenue asset settlements retain "
            "their original layer owner and signed member "
            "transfers; an asset bridge reconciles original "
            "carrying to presented contract-asset/unbilled "
            "endpoints and conserves the full group at each "
            "endpoint",
            "cross-member billing asset settlements retain "
            "original asset amounts and owner transfers; "
            "asset bridge v2 separates settled assets from "
            "any excess billing that creates a liability, "
            "with independently reconciled per-period "
            "billing roles",
            "contracting intercompany relief uses the "
            "same-entity INTERCOMPANY_DUE_TO counterpart and "
            "its original paid population; bridge v6 "
            "includes source-backed same-currency groups and "
            "return-month-only presentation, while earlier "
            "bindings retain their scope",
            "unexplained OTHER on any individual contract fails even when currency totals cancel",
            "with period_lock_id, the values frozen at that "
            "lock (lock_snapshot kind "
            "CONTRACT_BALANCE_ROLLFORWARD)",
            "mixed revenue inputs use retained per-input "
            "TIME amounts in both currencies only when "
            "original sources have one contract, layer, "
            "movement kind, date and source identity; "
            "ambiguous ownership is not proportionally "
            "assigned",
            "GL bridge v2 compares report, retained "
            "reconciliation subledger and GL per entity and "
            "role in functional currency; either nonzero leg "
            "fails even when net differences cancel; missing "
            "subledger evidence is unavailable and v1 "
            "bindings retain two-way semantics",
            "mixed revenue inputs spanning original sources "
            "use retained recognition-period classes only "
            "when every source period is uniform TIME or "
            "EVENT and both currency TIME totals reconcile; "
            "mixed periods and unmatched functional "
            "allocation remain unavailable",
            "agent gross control relief is reconciled to "
            "separately retained net revenue and AP_SUPPLIER "
            "components in both currencies; split targets "
            "require unique original source ownership and "
            "supplier history capability, otherwise "
            "attribution is unavailable",
            "zero-net agent control relief uses its sole "
            "retained AP_SUPPLIER counterpart, with no "
            "synthetic revenue line; supplier amounts and "
            "original signed sources must reconcile in both "
            "currencies",
            "mixed recognition periods may use retained "
            "transaction and functional TIME target deltas "
            "only with one original provenance per mixed "
            "period; totals must reconcile in both "
            "currencies and ambiguous within-period owners "
            "remain unavailable",
            "multi-source agent relief uses original gross "
            "control target and paid history for ownership; "
            "net revenue and supplier components separately "
            "verify split formulas and paid amounts in both "
            "currencies without allocating component amounts "
            "across owners",
            "combined-member refunds classify billing from "
            "retained asset and liability sources even when "
            "asset consumption is zero; full-return "
            "recipients replay original negative postings "
            "when latest targets no longer retain prior "
            "consumed layers",
            "GL bridge v3 requires the latest retained "
            "reconciliation to be reviewed or certified; "
            "draft, prepared, reopened or missing status is "
            "unavailable; historical v1 and v2 bindings "
            "preserve their original arithmetic controls",
            "GL bridge v4 selects the latest source identity "
            "before checking mutable state; a source changed "
            "after the report cutoff is unavailable and "
            "never replaced by an older reviewed source; "
            "retained v1-v3 bindings remain unchanged",
            "GL bridge v5 reads the latest database-captured "
            "reconciliation revision at the report cutoff "
            "for the latest source identity, preserving "
            "original review state and totals after later "
            "changes; migration baselines attest only to "
            "capture-time state and uncovered history is "
            "unavailable; original revision identity and "
            "amounts are bound for reruns; retained v1-v4 "
            "comparisons keep their prior rules",
            "GL bridge v6 selects source identities and "
            "their latest captured states from immutable "
            "revisions in one database statement for all "
            "requested entities; a concurrent source change "
            "cannot mix identity and review snapshots; "
            "timestamp cutoffs still do not reconstruct "
            "arbitrary historical commit visibility; "
            "retained v1-v5 comparisons use their bound "
            "evidence unchanged",
            "subledger_commit_visibility_v1 requires "
            "original PostgreSQL posting commit time at or "
            "before the historical cutoff; retained commit "
            "evidence is immutable; older bindings preserve "
            "their original seal-time interpretation",
            "historical_source_commit_v1 retains original "
            "event and contract-version transaction commits; "
            "new event/version extracts and BBR event "
            "sources use commit cutoffs; historical version "
            "populations exclude later commits before latest "
            "selection; bound inputs keep their original "
            "interpretation",
        ],
        "parameters": [
            "entity_codes",
            "book",
            "from_period_key",
            "to_period_key",
            "balance_role",
            "period_lock_id",
            "currency_view",
            "known_at",
            "known_at_basis",
        ],
    },
}

NEW = {
    "contract_balances": {
        "version": 1,
        "source_tables": [
            "contract_version_balance",
            "contract_version",
            "contract",
            "customer",
            "legal_entity",
            "period",
            "lock_snapshot",
            "combination_group_member",
            "contract_computation",
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "reconciliation",
            "report_source_revision",
            "historical_source_commit",
            "computation_evidence",
            "file_object",
            "contract_event",
            "calc_trace",
        ],
        "joins": [
            "contract_version_balance.contract_version_id = contract_version.id",
            "contract_version_balance.contract_id = contract.id",
            "contract.customer_id = customer.id",
            "contract_version_balance.entity_id = legal_entity.id",
            "combination_group_member.combination_group_id = contract_version.combination_group_id",
            "contract_version.contract_computation_id = contract_computation.id",
        ],
        "filters": [
            "GL bridge v7 selects only source revisions committed at or "
            "before known_at, then ranks source identities and states "
            "in one statement; original commit time is retained with "
            "the revision; retained v1-v6 comparisons keep their "
            "original rules",
            "entity code in entity_codes and within the caller's entity scope",
            "book_code = book",
            "per contract, the last contract_version known at known_at "
            "along the contract's chain of combination groups, of the "
            "versions computed with the contract among their members "
            "(combination_group_member, contract_computation), read at "
            "the end of period_key",
            "include_zero false: contracts with a non-zero balance only",
            "contract.external_id = contract_external_id when given",
            "with period_lock_id, the values frozen at that lock "
            "(lock_snapshot kind CONTRACT_BALANCES)",
            "GL bridge v2 compares report, retained reconciliation "
            "subledger and GL per entity and role in functional "
            "currency; either nonzero leg fails even when net "
            "differences cancel; missing subledger evidence is "
            "unavailable and v1 bindings retain two-way semantics",
            "GL bridge v3 requires the latest retained reconciliation "
            "to be reviewed or certified; draft, prepared, reopened or "
            "missing status is unavailable; historical v1 and v2 "
            "bindings preserve their original arithmetic controls",
            "GL bridge v4 selects the latest source identity before "
            "checking mutable state; a source changed after the report "
            "cutoff is unavailable and never replaced by an older "
            "reviewed source; retained v1-v3 bindings remain unchanged",
            "GL bridge v5 reads the latest database-captured "
            "reconciliation revision at the report cutoff for the "
            "latest source identity, preserving original review state "
            "and totals after later changes; migration baselines attest "
            "only to capture-time state and uncovered history is "
            "unavailable; original revision identity and amounts are "
            "bound for reruns; retained v1-v4 comparisons keep their "
            "prior rules",
            "GL bridge v6 selects source identities and their latest "
            "captured states from immutable revisions in one database "
            "statement for all requested entities; a concurrent source "
            "change cannot mix identity and review snapshots; timestamp "
            "cutoffs still do not reconstruct arbitrary historical "
            "commit visibility; retained v1-v5 comparisons use their "
            "bound evidence unchanged",
            "historical_source_commit_v1 retains original event and "
            "contract-version transaction commits; new event/version "
            "extracts and BBR event sources use commit cutoffs; "
            "historical version populations exclude later commits "
            "before latest selection; bound inputs keep their original "
            "interpretation",
            "acquisition_cutover_balances_v1 and "
            "acquisition_native_cutover_sources_v1 read missing "
            "ordinary cutover amounts from authenticated original "
            "singleton principal recomputed acquisition snapshots; "
            "original maturity inputs determine current parts; mixed "
            "current-asset netting requires original attribution; "
            "locked endpoints and bindings without these markers retain "
            "their original sources",
        ],
        "parameters": [
            "entity_codes",
            "book",
            "period_key",
            "period_lock_id",
            "include_zero",
            "contract_external_id",
            "currency_view",
            "known_at",
            "known_at_basis",
        ],
    },
    "contract_balance_rollforward": {
        "version": 1,
        "source_tables": [
            "subledger_line",
            "subledger_posting",
            "close_pass_evidence",
            "computation_evidence",
            "contract_version",
            "subledger_posting_seal",
            "file_object",
            "contract_version_balance",
            "calc_trace",
            "fx_layer_movement",
            "contract_event",
            "contract",
            "customer",
            "period",
            "lock_snapshot",
            "reconciliation",
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "report_source_revision",
            "subledger_posting_commit",
            "historical_source_commit",
        ],
        "joins": [
            "subledger_line.subledger_posting_id = subledger_posting.id",
            "close_pass_evidence.subledger_posting_id = "
            "subledger_posting.id; retained entry index "
            "identifies the source group",
            "close_pass_evidence.file_id = file_object.id; "
            "authenticated pass input/output and paid-line "
            "history",
            "subledger_line.contract_version_id = "
            "contract_version.id; "
            "contract_version.contract_computation_id = "
            "computation_evidence.contract_computation_id",
            "computation_evidence retains original input/output files and per-book seal cutoff",
            "subledger_line.contract_id = contract.id",
            "subledger_line.period_id = period.id",
            "contract_version_balance.contract_id = contract.id",
            "calc_trace.contract_version_id = contract_version_balance.contract_version_id",
            "contract_event.contract_id = contract.id (billing documents)",
            "contract.customer_id = customer.id",
        ],
        "filters": [
            "GL bridge v7 selects only source revisions "
            "committed at or before known_at, then ranks "
            "source identities and states in one statement; "
            "original commit time is retained with the "
            "revision; retained v1-v6 comparisons keep their "
            "original rules",
            "entity code in entity_codes and within the caller's entity scope",
            "book_code = book",
            "period_key from from_period_key to to_period_key",
            "subledger_line.account_role is a contract balance role",
            "opening: balance at the end of the period "
            "before from_period_key; closing: balance at the "
            "end of to_period_key",
            "billing that posts no line (billing.posting = "
            "ERP): per period the delta of the calc_trace "
            "node billed_unconditional_cum less the BILLING "
            "and CREDIT_MEMO lines of the role; where not "
            "zero and the role holds no such line, the "
            "period's kept BILLING_RECORDED lines and "
            "CREDIT_MEMO_RECORDED events, not voided, at "
            "their effective dates",
            "functional/reporting close FX uses signed "
            "asset/liability source layers, prior targets "
            "and recursively retained paid lines",
            "source binding retains posted-history "
            "dependencies and evidence hashes; unavailable "
            "source attribution refuses",
            "EVENT FX nets actual retained deltas by dated "
            "source before billing or revenue; source-backed "
            "reports replace synthetic settlement offsets",
            "combined memo billing reads authorized "
            "same-version member layers; credit-memo spot "
            "portions follow retained relief order with "
            "cumulative rounding",
            "combined liability reclassifications bridge "
            "original layer carrying and retained member "
            "presentation at each endpoint, plus "
            "cross-member memo source transfers; each "
            "original computation group conserves zero and "
            "evidence is bound",
            "new member presentation bridges include all "
            "foreign contract/entity endpoints, even without "
            "a memo or FX journal; legacy v1 bindings retain "
            "memo-triggered scope",
            "cross-member revenue reconciles the entire "
            "posted delta to original signed sources; "
            "liability consumption separately reproduces "
            "retained owner/layer relief while own-member "
            "asset creation remains asset revenue; original "
            "layer dates classify opening consumption and v4 "
            "presentation binds the liability relief amounts",
            "new source-backed revenue runs recursively "
            "reconcile original functional targets, prior "
            "targets and sealed paid-line history; reversals "
            "must reproduce the same owner/layer relief "
            "population and preserve evidence on rerun",
            "v5 presentation includes own-member asset "
            "settlements and newly created liabilities from "
            "original signed revenue sources, including "
            "returns whose source consumption predates the "
            "selected range; new liabilities are not opening "
            "relief",
            "cross-member revenue asset settlements retain "
            "their original layer owner and signed member "
            "transfers; an asset bridge reconciles original "
            "carrying to presented contract-asset/unbilled "
            "endpoints and conserves the full group at each "
            "endpoint",
            "cross-member billing asset settlements retain "
            "original asset amounts and owner transfers; "
            "asset bridge v2 separates settled assets from "
            "any excess billing that creates a liability, "
            "with independently reconciled per-period "
            "billing roles",
            "contracting intercompany relief uses the "
            "same-entity INTERCOMPANY_DUE_TO counterpart and "
            "its original paid population; bridge v6 "
            "includes source-backed same-currency groups and "
            "return-month-only presentation, while earlier "
            "bindings retain their scope",
            "unexplained OTHER on any individual contract fails even when currency totals cancel",
            "with period_lock_id, the values frozen at that "
            "lock (lock_snapshot kind "
            "CONTRACT_BALANCE_ROLLFORWARD)",
            "mixed revenue inputs use retained per-input "
            "TIME amounts in both currencies only when "
            "original sources have one contract, layer, "
            "movement kind, date and source identity; "
            "ambiguous ownership is not proportionally "
            "assigned",
            "GL bridge v2 compares report, retained "
            "reconciliation subledger and GL per entity and "
            "role in functional currency; either nonzero leg "
            "fails even when net differences cancel; missing "
            "subledger evidence is unavailable and v1 "
            "bindings retain two-way semantics",
            "mixed revenue inputs spanning original sources "
            "use retained recognition-period classes only "
            "when every source period is uniform TIME or "
            "EVENT and both currency TIME totals reconcile; "
            "mixed periods and unmatched functional "
            "allocation remain unavailable",
            "agent gross control relief is reconciled to "
            "separately retained net revenue and AP_SUPPLIER "
            "components in both currencies; split targets "
            "require unique original source ownership and "
            "supplier history capability, otherwise "
            "attribution is unavailable",
            "zero-net agent control relief uses its sole "
            "retained AP_SUPPLIER counterpart, with no "
            "synthetic revenue line; supplier amounts and "
            "original signed sources must reconcile in both "
            "currencies",
            "mixed recognition periods may use retained "
            "transaction and functional TIME target deltas "
            "only with one original provenance per mixed "
            "period; totals must reconcile in both "
            "currencies and ambiguous within-period owners "
            "remain unavailable",
            "multi-source agent relief uses original gross "
            "control target and paid history for ownership; "
            "net revenue and supplier components separately "
            "verify split formulas and paid amounts in both "
            "currencies without allocating component amounts "
            "across owners",
            "combined-member refunds classify billing from "
            "retained asset and liability sources even when "
            "asset consumption is zero; full-return "
            "recipients replay original negative postings "
            "when latest targets no longer retain prior "
            "consumed layers",
            "GL bridge v3 requires the latest retained "
            "reconciliation to be reviewed or certified; "
            "draft, prepared, reopened or missing status is "
            "unavailable; historical v1 and v2 bindings "
            "preserve their original arithmetic controls",
            "GL bridge v4 selects the latest source identity "
            "before checking mutable state; a source changed "
            "after the report cutoff is unavailable and "
            "never replaced by an older reviewed source; "
            "retained v1-v3 bindings remain unchanged",
            "GL bridge v5 reads the latest database-captured "
            "reconciliation revision at the report cutoff "
            "for the latest source identity, preserving "
            "original review state and totals after later "
            "changes; migration baselines attest only to "
            "capture-time state and uncovered history is "
            "unavailable; original revision identity and "
            "amounts are bound for reruns; retained v1-v4 "
            "comparisons keep their prior rules",
            "GL bridge v6 selects source identities and "
            "their latest captured states from immutable "
            "revisions in one database statement for all "
            "requested entities; a concurrent source change "
            "cannot mix identity and review snapshots; "
            "timestamp cutoffs still do not reconstruct "
            "arbitrary historical commit visibility; "
            "retained v1-v5 comparisons use their bound "
            "evidence unchanged",
            "subledger_commit_visibility_v1 requires "
            "original PostgreSQL posting commit time at or "
            "before the historical cutoff; retained commit "
            "evidence is immutable; older bindings preserve "
            "their original seal-time interpretation",
            "historical_source_commit_v1 retains original "
            "event and contract-version transaction commits; "
            "new event/version extracts and BBR event "
            "sources use commit cutoffs; historical version "
            "populations exclude later commits before latest "
            "selection; bound inputs keep their original "
            "interpretation",
            "acquisition_cutover_balances_v1 and "
            "acquisition_native_cutover_sources_v1 read "
            "missing ordinary cutover amounts from "
            "authenticated original singleton principal "
            "recomputed acquisition snapshots; original "
            "maturity inputs determine current parts; mixed "
            "current-asset netting requires original "
            "attribution; locked endpoints and bindings "
            "without these markers retain their original "
            "sources",
        ],
        "parameters": [
            "entity_codes",
            "book",
            "from_period_key",
            "to_period_key",
            "balance_role",
            "period_lock_id",
            "currency_view",
            "known_at",
            "known_at_basis",
        ],
    },
}


def _set(definitions: dict) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    for code, value in definitions.items():
        payload = json.dumps(value).replace("'", "''")
        ops.execute(
            f"UPDATE erev.report_definition SET ipe_logic='{payload}'::jsonb "  # noqa: S608
            f"WHERE code='{code}' AND version=1"
        )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    _set(NEW)


def downgrade() -> None:
    _set(OLD)
