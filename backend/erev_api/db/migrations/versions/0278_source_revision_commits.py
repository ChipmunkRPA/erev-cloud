"""Use original commit cutoffs for mutable-source revisions."""

import json

from erev_api.db import migration_ops as ops

revision = "0278"
down_revision = "0277"
branch_labels = None
depends_on = None

OLD_STAMP = """
        CREATE OR REPLACE FUNCTION erev.tg_source_commit__stamp() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NOT (
                    (NEW.source_kind = 'contract_event' AND EXISTS (
                        SELECT 1 FROM erev.contract_event
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'contract_version' AND EXISTS (
                        SELECT 1 FROM erev.contract_version
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id))
                ) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: Original source is required';
                END IF;
                NEW.source_transaction := pg_current_xact_id()::text;
                NEW.committed_server_at := NULL;
            ELSE
                IF OLD.committed_server_at IS NOT NULL THEN
                    RAISE EXCEPTION 'EREV-IMM-001: Commit evidence is immutable';
                END IF;
                IF NEW.committed_server_at IS NULL OR NEW.committed_server_at IS DISTINCT FROM
                    erev.source_commit_time(OLD.source_kind, OLD.source_id) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: Commit evidence must match PostgreSQL';
                END IF;
            END IF;
            RETURN NEW;
        END $$
"""

NEW_STAMP = """
        CREATE OR REPLACE FUNCTION erev.tg_source_commit__stamp() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, erev AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NOT (
                    (NEW.source_kind = 'contract_event' AND EXISTS (
                        SELECT 1 FROM erev.contract_event
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'contract_version' AND EXISTS (
                        SELECT 1 FROM erev.contract_version
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id)) OR
                    (NEW.source_kind = 'report_source_revision' AND EXISTS (
                        SELECT 1 FROM erev.report_source_revision
                        WHERE tenant_id = NEW.tenant_id AND id = NEW.source_id))
                ) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: Original source is required';
                END IF;
                NEW.source_transaction := pg_current_xact_id()::text;
                NEW.committed_server_at := NULL;
            ELSE
                IF OLD.committed_server_at IS NOT NULL THEN
                    RAISE EXCEPTION 'EREV-IMM-001: Commit evidence is immutable';
                END IF;
                IF NEW.committed_server_at IS NULL OR NEW.committed_server_at IS DISTINCT FROM
                    erev.source_commit_time(OLD.source_kind, OLD.source_id) THEN
                    RAISE EXCEPTION 'EREV-HIS-001: Commit evidence must match PostgreSQL';
                END IF;
            END IF;
            RETURN NEW;
        END $$
"""


OLD_IPE = (
    '{"contract_balances":{"version":1,"source_tables":["contract_version_balance",'
    '"contract_version","contract","customer","legal_entity","period","lock_snapsho'
    't","combination_group_member","contract_computation","tenant","fx_rate","fx_ra'
    'te_set","fx_rate_set_version","reconciliation","report_source_revision","histo'
    'rical_source_commit"],"joins":["contract_version_balance.contract_version_id ='
    ' contract_version.id","contract_version_balance.contract_id = '
    'contract.id","contract.customer_id = '
    'customer.id","contract_version_balance.entity_id = '
    'legal_entity.id","combination_group_member.combination_group_id = contract_ver'
    'sion.combination_group_id","contract_version.contract_computation_id = '
    'contract_computation.id"],"filters":["entity code in entity_codes and within '
    'the caller\'s entity scope","book_code = book","per contract, the last '
    "contract_version known at known_at along the contract's chain of combination "
    "groups, of the versions computed with the contract among their members "
    "(combination_group_member, contract_computation), read at the end of "
    'period_key","include_zero false: contracts with a non-zero balance '
    'only","contract.external_id = contract_external_id when given","with '
    "period_lock_id, the values frozen at that lock (lock_snapshot kind "
    'CONTRACT_BALANCES)","GL bridge v2 compares report, retained reconciliation '
    "subledger and GL per entity and role in functional currency; either nonzero "
    "leg fails even when net differences cancel; missing subledger evidence is "
    'unavailable and v1 bindings retain two-way semantics","GL bridge v3 requires '
    "the latest retained reconciliation to be reviewed or certified; draft, "
    "prepared, reopened or missing status is unavailable; historical v1 and v2 "
    'bindings preserve their original arithmetic controls","GL bridge v4 selects '
    "the latest source identity before checking mutable state; a source changed "
    "after the report cutoff is unavailable and never replaced by an older reviewed"
    ' source; retained v1-v3 bindings remain unchanged","GL bridge v5 reads the '
    "latest database-captured reconciliation revision at the report cutoff for the "
    "latest source identity, preserving original review state and totals after "
    "later changes; migration baselines attest only to capture-time state and "
    "uncovered history is unavailable; original revision identity and amounts are "
    'bound for reruns; retained v1-v4 comparisons keep their prior rules","GL '
    "bridge v6 selects source identities and their latest captured states from "
    "immutable revisions in one database statement for all requested entities; a "
    "concurrent source change cannot mix identity and review snapshots; timestamp "
    "cutoffs still do not reconstruct arbitrary historical commit visibility; "
    "retained v1-v5 comparisons use their bound evidence "
    'unchanged","historical_source_commit_v1 retains original event and '
    "contract-version transaction commits; new event/version extracts and BBR event"
    " sources use commit cutoffs; historical version populations exclude later "
    "commits before latest selection; bound inputs keep their original interpretati"
    'on"],"parameters":["entity_codes","book","period_key","period_lock_id","includ'
    'e_zero","contract_external_id","currency_view","known_at","known_at_basis"]},"'
    'contract_balance_rollforward":{"version":1,"source_tables":["subledger_line","'
    'subledger_posting","close_pass_evidence","computation_evidence","contract_vers'
    'ion","subledger_posting_seal","file_object","contract_version_balance","calc_t'
    'race","fx_layer_movement","contract_event","contract","customer","period","loc'
    'k_snapshot","reconciliation","tenant","fx_rate","fx_rate_set","fx_rate_set_ver'
    'sion","report_source_revision","subledger_posting_commit","historical_source_c'
    'ommit"],"joins":["subledger_line.subledger_posting_id = '
    'subledger_posting.id","close_pass_evidence.subledger_posting_id = '
    "subledger_posting.id; retained entry index identifies the source "
    'group","close_pass_evidence.file_id = file_object.id; authenticated pass '
    'input/output and paid-line history","subledger_line.contract_version_id = '
    "contract_version.id; contract_version.contract_computation_id = "
    'computation_evidence.contract_computation_id","computation_evidence retains '
    "original input/output files and per-book seal "
    'cutoff","subledger_line.contract_id = contract.id","subledger_line.period_id ='
    ' period.id","contract_version_balance.contract_id = '
    'contract.id","calc_trace.contract_version_id = '
    'contract_version_balance.contract_version_id","contract_event.contract_id = '
    'contract.id (billing documents)","contract.customer_id = '
    'customer.id"],"filters":["entity code in entity_codes and within the caller\'s '
    'entity scope","book_code = book","period_key from from_period_key to '
    'to_period_key","subledger_line.account_role is a contract balance '
    'role","opening: balance at the end of the period before from_period_key; '
    'closing: balance at the end of to_period_key","billing that posts no line '
    "(billing.posting = ERP): per period the delta of the calc_trace node "
    "billed_unconditional_cum less the BILLING and CREDIT_MEMO lines of the role; "
    "where not zero and the role holds no such line, the period's kept "
    "BILLING_RECORDED lines and CREDIT_MEMO_RECORDED events, not voided, at their "
    'effective dates","functional/reporting close FX uses signed asset/liability '
    'source layers, prior targets and recursively retained paid lines","source '
    "binding retains posted-history dependencies and evidence hashes; unavailable "
    'source attribution refuses","EVENT FX nets actual retained deltas by dated '
    "source before billing or revenue; source-backed reports replace synthetic "
    'settlement offsets","combined memo billing reads authorized same-version '
    "member layers; credit-memo spot portions follow retained relief order with "
    'cumulative rounding","combined liability reclassifications bridge original '
    "layer carrying and retained member presentation at each endpoint, plus "
    "cross-member memo source transfers; each original computation group conserves "
    'zero and evidence is bound","new member presentation bridges include all '
    "foreign contract/entity endpoints, even without a memo or FX journal; legacy "
    'v1 bindings retain memo-triggered scope","cross-member revenue reconciles the '
    "entire posted delta to original signed sources; liability consumption "
    "separately reproduces retained owner/layer relief while own-member asset "
    "creation remains asset revenue; original layer dates classify opening "
    'consumption and v4 presentation binds the liability relief amounts","new '
    "source-backed revenue runs recursively reconcile original functional targets, "
    "prior targets and sealed paid-line history; reversals must reproduce the same "
    'owner/layer relief population and preserve evidence on rerun","v5 presentation'
    " includes own-member asset settlements and newly created liabilities from "
    "original signed revenue sources, including returns whose source consumption "
    "predates the selected range; new liabilities are not opening "
    'relief","cross-member revenue asset settlements retain their original layer '
    "owner and signed member transfers; an asset bridge reconciles original "
    "carrying to presented contract-asset/unbilled endpoints and conserves the full"
    ' group at each endpoint","cross-member billing asset settlements retain '
    "original asset amounts and owner transfers; asset bridge v2 separates settled "
    "assets from any excess billing that creates a liability, with independently "
    'reconciled per-period billing roles","contracting intercompany relief uses the'
    " same-entity INTERCOMPANY_DUE_TO counterpart and its original paid population;"
    " bridge v6 includes source-backed same-currency groups and return-month-only "
    'presentation, while earlier bindings retain their scope","unexplained OTHER on'
    ' any individual contract fails even when currency totals cancel","with '
    "period_lock_id, the values frozen at that lock (lock_snapshot kind "
    'CONTRACT_BALANCE_ROLLFORWARD)","mixed revenue inputs use retained per-input '
    "TIME amounts in both currencies only when original sources have one contract, "
    "layer, movement kind, date and source identity; ambiguous ownership is not "
    'proportionally assigned","GL bridge v2 compares report, retained '
    "reconciliation subledger and GL per entity and role in functional currency; "
    "either nonzero leg fails even when net differences cancel; missing subledger "
    'evidence is unavailable and v1 bindings retain two-way semantics","mixed '
    "revenue inputs spanning original sources use retained recognition-period "
    "classes only when every source period is uniform TIME or EVENT and both "
    "currency TIME totals reconcile; mixed periods and unmatched functional "
    'allocation remain unavailable","agent gross control relief is reconciled to '
    "separately retained net revenue and AP_SUPPLIER components in both currencies;"
    " split targets require unique original source ownership and supplier history "
    'capability, otherwise attribution is unavailable","zero-net agent control '
    "relief uses its sole retained AP_SUPPLIER counterpart, with no synthetic "
    "revenue line; supplier amounts and original signed sources must reconcile in "
    'both currencies","mixed recognition periods may use retained transaction and '
    "functional TIME target deltas only with one original provenance per mixed "
    "period; totals must reconcile in both currencies and ambiguous within-period "
    'owners remain unavailable","multi-source agent relief uses original gross '
    "control target and paid history for ownership; net revenue and supplier "
    "components separately verify split formulas and paid amounts in both "
    "currencies without allocating component amounts across "
    'owners","combined-member refunds classify billing from retained asset and '
    "liability sources even when asset consumption is zero; full-return recipients "
    "replay original negative postings when latest targets no longer retain prior "
    'consumed layers","GL bridge v3 requires the latest retained reconciliation to '
    "be reviewed or certified; draft, prepared, reopened or missing status is "
    "unavailable; historical v1 and v2 bindings preserve their original arithmetic "
    'controls","GL bridge v4 selects the latest source identity before checking '
    "mutable state; a source changed after the report cutoff is unavailable and "
    "never replaced by an older reviewed source; retained v1-v3 bindings remain "
    'unchanged","GL bridge v5 reads the latest database-captured reconciliation '
    "revision at the report cutoff for the latest source identity, preserving "
    "original review state and totals after later changes; migration baselines "
    "attest only to capture-time state and uncovered history is unavailable; "
    "original revision identity and amounts are bound for reruns; retained v1-v4 "
    'comparisons keep their prior rules","GL bridge v6 selects source identities '
    "and their latest captured states from immutable revisions in one database "
    "statement for all requested entities; a concurrent source change cannot mix "
    "identity and review snapshots; timestamp cutoffs still do not reconstruct "
    "arbitrary historical commit visibility; retained v1-v5 comparisons use their "
    'bound evidence unchanged","subledger_commit_visibility_v1 requires original '
    "PostgreSQL posting commit time at or before the historical cutoff; retained "
    "commit evidence is immutable; older bindings preserve their original seal-time"
    ' interpretation","historical_source_commit_v1 retains original event and '
    "contract-version transaction commits; new event/version extracts and BBR event"
    " sources use commit cutoffs; historical version populations exclude later "
    "commits before latest selection; bound inputs keep their original interpretati"
    'on"],"parameters":["entity_codes","book","from_period_key","to_period_key","ba'
    'lance_role","period_lock_id","currency_view","known_at","known_at_basis"]},"ex'
    'tract_contracts":{"version":1,"source_tables":["report_source_revision"],"join'
    's":["captured contract customer_id and contracting_entity_id to latest '
    'captured code labels at known_at"],"filters":["entity code in entity_codes and'
    ' within the caller\'s entity scope","latest database-captured revision at '
    'known_at; uncovered migration-era history refuses","mode INCREMENTAL: contract'
    ' created_at after known_since; not an update or deletion feed","lock datasets '
    'unsupported"],"parameters":["mode","entity_codes","period_lock_id","known_at",'
    '"known_since","known_at_basis"]}}'
)

NEW_IPE = (
    '{"contract_balances":{"version":1,"source_tables":["contract_version_balance",'
    '"contract_version","contract","customer","legal_entity","period","lock_snapsho'
    't","combination_group_member","contract_computation","tenant","fx_rate","fx_ra'
    'te_set","fx_rate_set_version","reconciliation","report_source_revision","histo'
    'rical_source_commit"],"joins":["contract_version_balance.contract_version_id ='
    ' contract_version.id","contract_version_balance.contract_id = '
    'contract.id","contract.customer_id = '
    'customer.id","contract_version_balance.entity_id = '
    'legal_entity.id","combination_group_member.combination_group_id = contract_ver'
    'sion.combination_group_id","contract_version.contract_computation_id = '
    'contract_computation.id"],"filters":["GL bridge v7 selects only source '
    "revisions committed at or before known_at, then ranks source identities and "
    "states in one statement; original commit time is retained with the revision; "
    'retained v1-v6 comparisons keep their original rules","entity code in '
    'entity_codes and within the caller\'s entity scope","book_code = book","per '
    "contract, the last contract_version known at known_at along the contract's "
    "chain of combination groups, of the versions computed with the contract among "
    "their members (combination_group_member, contract_computation), read at the "
    'end of period_key","include_zero false: contracts with a non-zero balance '
    'only","contract.external_id = contract_external_id when given","with '
    "period_lock_id, the values frozen at that lock (lock_snapshot kind "
    'CONTRACT_BALANCES)","GL bridge v2 compares report, retained reconciliation '
    "subledger and GL per entity and role in functional currency; either nonzero "
    "leg fails even when net differences cancel; missing subledger evidence is "
    'unavailable and v1 bindings retain two-way semantics","GL bridge v3 requires '
    "the latest retained reconciliation to be reviewed or certified; draft, "
    "prepared, reopened or missing status is unavailable; historical v1 and v2 "
    'bindings preserve their original arithmetic controls","GL bridge v4 selects '
    "the latest source identity before checking mutable state; a source changed "
    "after the report cutoff is unavailable and never replaced by an older reviewed"
    ' source; retained v1-v3 bindings remain unchanged","GL bridge v5 reads the '
    "latest database-captured reconciliation revision at the report cutoff for the "
    "latest source identity, preserving original review state and totals after "
    "later changes; migration baselines attest only to capture-time state and "
    "uncovered history is unavailable; original revision identity and amounts are "
    'bound for reruns; retained v1-v4 comparisons keep their prior rules","GL '
    "bridge v6 selects source identities and their latest captured states from "
    "immutable revisions in one database statement for all requested entities; a "
    "concurrent source change cannot mix identity and review snapshots; timestamp "
    "cutoffs still do not reconstruct arbitrary historical commit visibility; "
    "retained v1-v5 comparisons use their bound evidence "
    'unchanged","historical_source_commit_v1 retains original event and '
    "contract-version transaction commits; new event/version extracts and BBR event"
    " sources use commit cutoffs; historical version populations exclude later "
    "commits before latest selection; bound inputs keep their original interpretati"
    'on"],"parameters":["entity_codes","book","period_key","period_lock_id","includ'
    'e_zero","contract_external_id","currency_view","known_at","known_at_basis"]},"'
    'contract_balance_rollforward":{"version":1,"source_tables":["subledger_line","'
    'subledger_posting","close_pass_evidence","computation_evidence","contract_vers'
    'ion","subledger_posting_seal","file_object","contract_version_balance","calc_t'
    'race","fx_layer_movement","contract_event","contract","customer","period","loc'
    'k_snapshot","reconciliation","tenant","fx_rate","fx_rate_set","fx_rate_set_ver'
    'sion","report_source_revision","subledger_posting_commit","historical_source_c'
    'ommit"],"joins":["subledger_line.subledger_posting_id = '
    'subledger_posting.id","close_pass_evidence.subledger_posting_id = '
    "subledger_posting.id; retained entry index identifies the source "
    'group","close_pass_evidence.file_id = file_object.id; authenticated pass '
    'input/output and paid-line history","subledger_line.contract_version_id = '
    "contract_version.id; contract_version.contract_computation_id = "
    'computation_evidence.contract_computation_id","computation_evidence retains '
    "original input/output files and per-book seal "
    'cutoff","subledger_line.contract_id = contract.id","subledger_line.period_id ='
    ' period.id","contract_version_balance.contract_id = '
    'contract.id","calc_trace.contract_version_id = '
    'contract_version_balance.contract_version_id","contract_event.contract_id = '
    'contract.id (billing documents)","contract.customer_id = '
    'customer.id"],"filters":["GL bridge v7 selects only source revisions committed'
    " at or before known_at, then ranks source identities and states in one "
    "statement; original commit time is retained with the revision; retained v1-v6 "
    'comparisons keep their original rules","entity code in entity_codes and within'
    ' the caller\'s entity scope","book_code = book","period_key from '
    'from_period_key to to_period_key","subledger_line.account_role is a contract '
    'balance role","opening: balance at the end of the period before '
    'from_period_key; closing: balance at the end of to_period_key","billing that '
    "posts no line (billing.posting = ERP): per period the delta of the calc_trace "
    "node billed_unconditional_cum less the BILLING and CREDIT_MEMO lines of the "
    "role; where not zero and the role holds no such line, the period's kept "
    "BILLING_RECORDED lines and CREDIT_MEMO_RECORDED events, not voided, at their "
    'effective dates","functional/reporting close FX uses signed asset/liability '
    'source layers, prior targets and recursively retained paid lines","source '
    "binding retains posted-history dependencies and evidence hashes; unavailable "
    'source attribution refuses","EVENT FX nets actual retained deltas by dated '
    "source before billing or revenue; source-backed reports replace synthetic "
    'settlement offsets","combined memo billing reads authorized same-version '
    "member layers; credit-memo spot portions follow retained relief order with "
    'cumulative rounding","combined liability reclassifications bridge original '
    "layer carrying and retained member presentation at each endpoint, plus "
    "cross-member memo source transfers; each original computation group conserves "
    'zero and evidence is bound","new member presentation bridges include all '
    "foreign contract/entity endpoints, even without a memo or FX journal; legacy "
    'v1 bindings retain memo-triggered scope","cross-member revenue reconciles the '
    "entire posted delta to original signed sources; liability consumption "
    "separately reproduces retained owner/layer relief while own-member asset "
    "creation remains asset revenue; original layer dates classify opening "
    'consumption and v4 presentation binds the liability relief amounts","new '
    "source-backed revenue runs recursively reconcile original functional targets, "
    "prior targets and sealed paid-line history; reversals must reproduce the same "
    'owner/layer relief population and preserve evidence on rerun","v5 presentation'
    " includes own-member asset settlements and newly created liabilities from "
    "original signed revenue sources, including returns whose source consumption "
    "predates the selected range; new liabilities are not opening "
    'relief","cross-member revenue asset settlements retain their original layer '
    "owner and signed member transfers; an asset bridge reconciles original "
    "carrying to presented contract-asset/unbilled endpoints and conserves the full"
    ' group at each endpoint","cross-member billing asset settlements retain '
    "original asset amounts and owner transfers; asset bridge v2 separates settled "
    "assets from any excess billing that creates a liability, with independently "
    'reconciled per-period billing roles","contracting intercompany relief uses the'
    " same-entity INTERCOMPANY_DUE_TO counterpart and its original paid population;"
    " bridge v6 includes source-backed same-currency groups and return-month-only "
    'presentation, while earlier bindings retain their scope","unexplained OTHER on'
    ' any individual contract fails even when currency totals cancel","with '
    "period_lock_id, the values frozen at that lock (lock_snapshot kind "
    'CONTRACT_BALANCE_ROLLFORWARD)","mixed revenue inputs use retained per-input '
    "TIME amounts in both currencies only when original sources have one contract, "
    "layer, movement kind, date and source identity; ambiguous ownership is not "
    'proportionally assigned","GL bridge v2 compares report, retained '
    "reconciliation subledger and GL per entity and role in functional currency; "
    "either nonzero leg fails even when net differences cancel; missing subledger "
    'evidence is unavailable and v1 bindings retain two-way semantics","mixed '
    "revenue inputs spanning original sources use retained recognition-period "
    "classes only when every source period is uniform TIME or EVENT and both "
    "currency TIME totals reconcile; mixed periods and unmatched functional "
    'allocation remain unavailable","agent gross control relief is reconciled to '
    "separately retained net revenue and AP_SUPPLIER components in both currencies;"
    " split targets require unique original source ownership and supplier history "
    'capability, otherwise attribution is unavailable","zero-net agent control '
    "relief uses its sole retained AP_SUPPLIER counterpart, with no synthetic "
    "revenue line; supplier amounts and original signed sources must reconcile in "
    'both currencies","mixed recognition periods may use retained transaction and '
    "functional TIME target deltas only with one original provenance per mixed "
    "period; totals must reconcile in both currencies and ambiguous within-period "
    'owners remain unavailable","multi-source agent relief uses original gross '
    "control target and paid history for ownership; net revenue and supplier "
    "components separately verify split formulas and paid amounts in both "
    "currencies without allocating component amounts across "
    'owners","combined-member refunds classify billing from retained asset and '
    "liability sources even when asset consumption is zero; full-return recipients "
    "replay original negative postings when latest targets no longer retain prior "
    'consumed layers","GL bridge v3 requires the latest retained reconciliation to '
    "be reviewed or certified; draft, prepared, reopened or missing status is "
    "unavailable; historical v1 and v2 bindings preserve their original arithmetic "
    'controls","GL bridge v4 selects the latest source identity before checking '
    "mutable state; a source changed after the report cutoff is unavailable and "
    "never replaced by an older reviewed source; retained v1-v3 bindings remain "
    'unchanged","GL bridge v5 reads the latest database-captured reconciliation '
    "revision at the report cutoff for the latest source identity, preserving "
    "original review state and totals after later changes; migration baselines "
    "attest only to capture-time state and uncovered history is unavailable; "
    "original revision identity and amounts are bound for reruns; retained v1-v4 "
    'comparisons keep their prior rules","GL bridge v6 selects source identities '
    "and their latest captured states from immutable revisions in one database "
    "statement for all requested entities; a concurrent source change cannot mix "
    "identity and review snapshots; timestamp cutoffs still do not reconstruct "
    "arbitrary historical commit visibility; retained v1-v5 comparisons use their "
    'bound evidence unchanged","subledger_commit_visibility_v1 requires original '
    "PostgreSQL posting commit time at or before the historical cutoff; retained "
    "commit evidence is immutable; older bindings preserve their original seal-time"
    ' interpretation","historical_source_commit_v1 retains original event and '
    "contract-version transaction commits; new event/version extracts and BBR event"
    " sources use commit cutoffs; historical version populations exclude later "
    "commits before latest selection; bound inputs keep their original interpretati"
    'on"],"parameters":["entity_codes","book","from_period_key","to_period_key","ba'
    'lance_role","period_lock_id","currency_view","known_at","known_at_basis"]},"ex'
    'tract_contracts":{"version":1,"source_tables":["report_source_revision","histo'
    'rical_source_commit"],"joins":["captured contract customer_id and '
    "contracting_entity_id to latest captured code labels at "
    'known_at"],"filters":["entity code in entity_codes and within the caller\'s '
    'entity scope","latest committed database-captured revision at known_at; '
    'uncovered migration-era history refuses","mode INCREMENTAL: latest contract '
    "when its header or customer/entity code label committed after known_since and "
    "at or before known_at; not a deletion feed; "
    "extract_contracts_commit_visibility_v1 retains this basis and commit times; "
    'older bound extracts keep their original creation-time basis","lock datasets u'
    'nsupported"],"parameters":["mode","entity_codes","period_lock_id","known_at","'
    'known_since","known_at_basis"]}}'
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
    ops.execute(
        "ALTER TABLE erev.report_source_revision ADD CONSTRAINT ck_revision__0278_empty "
        "CHECK (false) NOT VALID"
    )
    ops.execute(
        "ALTER TABLE erev.report_source_revision VALIDATE CONSTRAINT ck_revision__0278_empty"
    )
    ops.execute("ALTER TABLE erev.report_source_revision DROP CONSTRAINT ck_revision__0278_empty")
    ops.execute(
        "ALTER TABLE erev.historical_source_commit "
        "DROP CONSTRAINT ck_historical_source_commit__kind"
    )
    ops.execute(
        "ALTER TABLE erev.historical_source_commit "
        "ADD CONSTRAINT ck_historical_source_commit__kind "
        "CHECK (source_kind IN ('contract_event','contract_version','report_source_revision'))"
    )
    ops.execute(NEW_STAMP)
    ops.execute(
        "CREATE TRIGGER zz_source__commit_queue AFTER INSERT ON erev.report_source_revision "
        "FOR EACH ROW EXECUTE FUNCTION erev.tg_source_commit__queue()"
    )

    _metadata(NEW_IPE)


def downgrade() -> None:
    ops.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM erev.historical_source_commit
                   WHERE source_kind='report_source_revision') THEN
            RAISE EXCEPTION 'Retained source-revision commits prevent downgrade';
        END IF;
    END $$""")
    ops.execute("DROP TRIGGER zz_source__commit_queue ON erev.report_source_revision")
    ops.execute(OLD_STAMP)
    ops.execute(
        "ALTER TABLE erev.historical_source_commit "
        "DROP CONSTRAINT ck_historical_source_commit__kind"
    )
    ops.execute(
        "ALTER TABLE erev.historical_source_commit "
        "ADD CONSTRAINT ck_historical_source_commit__kind "
        "CHECK (source_kind IN ('contract_event','contract_version'))"
    )

    _metadata(OLD_IPE)
