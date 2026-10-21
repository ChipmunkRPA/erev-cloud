# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## Current owner-authorized goal — October 21, 2026

Finish the repository for public source publication under its noncommercial license;
prioritize feature completion with necessary targeted validation. Continue directly on main,
review and publish changes without PR accumulation, and do not deploy.

- Reporting priorities remain difference attribution, multi-currency, RPO exemptions and GL
  reconciliation. Combined contracts now retain original receiving-contract aging and separately
  show member allocation adjustments; continue the remaining evidenced Reporting gaps.
- Migration-to-live promotion/replay completion is outside scope; no actual business launch.
- Keep key financial permissions, segregation of duties and audit evidence; full approval
  coverage is not required. Implementation is not a SOX certification.
- Sandbox goal: refresh from production and allow experimentation isolated from production.
  Reproduction of production lock history and sandbox locking are not completion requirements.
- Independent accounting review belongs to the owner and is not a development completion gate.
- Owner resumed development October 21. The app goal tool cannot edit the existing objective
  or resume its paused state; this section records the superseding scope for repository work.

## GL source selection uses one database snapshot — October 21, 2026

- GL comparisons now resolve source identities, latest captured states, review status and totals
  from immutable report_source_revision rows in one SQL statement across all requested entities.
  The previous current-header query followed by a separate revision query could mix snapshots
  when an already-inserted source revision committed between those reads. Windowed selection
  preserves latest-source precedence and requires a source attachment known at the cutoff.
- New runs retain rollforward_gl_inputs_v6; v1-v5 bound comparisons still rebuild from their
  original evidence. Migration 0265 updates IPE for contract_balances and
  contract_balance_rollforward. Uncovered source history remains unavailable.
- A real two-transaction witness commits a change to a reopened reconciliation after the source
  statement executes: the comparison retains the pre-commit source revision, performs one source
  query and preserves the earlier reviewed historical/bound result. The public uploaded-GL
  report path, 14 GL cases, lint/types and reversible migration/catalogue parity pass.
- This establishes a consistent GL source-selection statement, not historical commit timestamps
  or a transaction-wide snapshot for every report source. B4-11 arbitrary historical commit
  visibility remains open, as do broader RPO mixed-lifecycle journeys. No deployment.

## Public termination controls and same-day usage calculations — October 21, 2026

- The modification form/API now accepts explicit FULL/PARTIAL termination scope and a refund
  in contract currency. Preview and approval use the same CONTRACT_TERMINATED event; the terms
  are stored, displayed in the detail, included in the approval fingerprint and cleared when
  switching to another modification kind. REMOVE lines must have non-positive deltas and cover
  the refund. New/edited termination drafts require terms; already approved historical rows
  without terms retain their original amendment semantics and hash. Migration 0264 retains
  the terms and refuses downgrade while any remain.
- The real command journey exposed two engine faults: inception-day realized fees were included
  in FIXED allocation and then counted again as period fees; an inception-day termination tried
  to extend recognition through a truncated segment ending before the first calendar period.
  Inception allocation now excludes separately recognized period fees, preserving zero trace
  nodes and contract-wide royalty-estimate allocation. Only later term ends extend the horizon.
- Four public journeys exercise two usage obligations, FULL/PARTIAL scope and refunds 0/40,
  including original engine calculations, required approval steps, contract status, reporting and
  retained reruns. Entry 160,000 and VC 150 remain separate; FULL recognizes the nonrefundable
  pool at termination, PARTIAL allocates it to continuing O2 and recognizes it over its term.
  Revenue, refunds and closing RPO reconcile. This closes the supplied-evidence-only limitation
  for this same-day usage/termination case, not every mixed amendment or re-entry sequence.
- Necessary checks pass: four public journeys, three ordinary modification regressions, 236
  pricing/allocation/recognition cases, 48 modification units, 88 RPO cases, 68 frontend cases,
  scoped lint/types, generated API parity, and migration round-trip/data-retention guard.
  Broader repeated cancellation/re-entry, combined same-day amendment/estimate/usage journeys
  and concurrent commit visibility remain open. No deployment.

## Same-day RPO entry with realized usage — October 21, 2026

- Same-day activation/termination can now retain gross new-contract amounts when usage is
  present. Original termination before-state and traced realized fees are required; fixed entry,
  original amendments, usage changes, recognition and cancellation remain distinct movements.
  Later retained usage corrections adjust VC and cancellation without repeating entry/amendments.
- New bindings retain rpo_same_day_entry_usage_v1 and require the existing batch cancelled-usage
  decomposition. Missing realized evidence and older bindings preserve previous eligibility.
  Migration 0263 records the matching IPE rule.
- All 88 related cases, public currency/rate rerun, scoped lint/types and reversible migration
  catalogue parity pass. The new same-day usage/mixed-amendment and retained-correction witnesses
  use supplied boundary/cut evidence, not a new original-engine/public-command usage journey.
- Original-engine/public-command coverage for these same-day usage mixtures remains outstanding,
  along with broader repeated cancellation/re-entry and concurrent commit visibility. Continue
  the October 21 repository-only scope; no deployment or independent accounting review gate.

## Original inception estimates in same-day RPO entry — October 21, 2026

- Same-day activation/termination now retains initial variable consideration in NEW_CONTRACTS
  when every original estimate has an INCEPTION pin and an admission-date event. The engine
  treats inception-date versions as initial price regardless of same-day record order; the report
  follows that rule rather than inventing a routed estimate delta. Amendments and refunds remain
  separately attributed, including through later retained memo/re-entry versions.
- Missing original pins preserve prior eligibility. New bindings retain
  rpo_same_day_entry_estimates_v1; legacy bindings retain their old behavior. Migration 0262
  adds the matching IPE note. The reader loads the pins from original retained engine traces.
- All 80 related cases, public currency/rate rerun, scoped lint/types and reversible migration
  catalogue parity pass. Original-engine scenarios cover estimates before and after activation,
  optional amendments, refunds, later versions and missing evidence. These use supplied report
  versions; no new public same-day contract-command journey is claimed.
- Same-day usage mixtures, broader repeated cancellation/re-entry and concurrent commit visibility
  remain open. The October 21 repository-only scope continues; no deployment.

## Original same-day RPO entry amendments — October 21, 2026

- RPO now separates original amendments after same-day activation and before termination:
  an original 100 contract followed by a -20 amendment retains NEW_CONTRACTS 100 and
  MODIFICATIONS -20, alongside the original revenue and refund/cancellation amounts.
  Previously the mixed cause set suppressed the original entry entirely.
- The reader retains admission record sequence from the original bound cause events. Complete
  amendment boundaries, strictly ordered original records and continuity into termination's
  before-state are required. Later memo/re-entry versions do not count the amendment again.
  New bindings retain rpo_same_day_entry_modifications_v1; legacy eligibility is unchanged.
  Migration 0261 adds the IPE rule.
- All 76 related cases pass; targeted missing/contradictory admission-order checks also pass.
  The witnesses use original engine amendment/termination calculations with supplied retained
  report versions. Public currency/rate rerun, scoped lint/types and reversible migration
  catalogue parity pass; no claim of a new public same-day contract command journey.
- Same-day mixtures involving estimates/usage and broader repeated cancellation/re-entry remain
  open, as does concurrent commit visibility. Continue the October 21 repository-only scope;
  no deployment or independent accounting sign-off gate.

## Combined aging public command/report/rerun path — October 21, 2026

- The combined aging feature now has a real command-to-report witness: two seat contracts
  are activated and combined through the approved public route, each receives a distinct billing
  event, and the combined group is computed by the production engine. Both original owners
  remain in the liability aging output with nonzero offsetting allocation adjustments.
- The report reconciles every member, and original buckets plus adjustment equal each presented
  balance. Public report creation and the worker return exactly the builder rows; the public
  retained rerun reproduces those rows and the Member allocation adjustment column header.
- The targeted database journey and lint pass. This closes the missing transaction-currency
  command-to-report witness; earlier scoped functional/reporting evidence remains as recorded.
  No deployment or additional production-readiness gate is introduced.

## Member aging adjustments agree with original engine amounts — October 21, 2026

- Combined-member aging adjustments now require each presented member amount to equal its
  retained original engine target, beyond complete membership and conserving the group total.
  Functional amounts require the exact member/period functional target in the requested currency.
  Missing, ambiguous, non-finite, wrong-currency or mismatched targets are refused, rather than
  treating a zero aggregate difference as evidence for an arbitrary member transfer.
- Original-owner age buckets and the separate adjustment column remain unchanged for valid
  sources. Focused cases cover offsetting member drift, a fully transferred zero-net owner,
  original functional targets and reporting translation; ten aging cases plus lint/types pass.
  No migration/schema change; no new full combined-contract command-to-lock claim.
- Continue the October 21 public-repository scope. No deployment, no independent accounting
  sign-off gate, no migration-to-live or sandbox lock-chain requirement.

## Original-owner aging and separate member allocations — October 21, 2026

- Implemented aging_member_adjustments_v1: original liability buckets retain their receiving
  contract and date; a separate Member allocation adjustment column bridges to the member's
  presented balance. Allocation adjustments have no invented age. Original owners remain
  visible even when their adjusted balance is zero, and group adjustment totals conserve cash
  layer balances. Complete retained engine member populations are required; unsupported or
  missing evidence is not silently repaired. Reporting translation preserves buckets and the
  adjusted total; retained legacy bindings keep their earlier schema.
- Re-lock comparisons treat allocation_adjustment as a monetary measure. Migration 0260 adds
  the IPE explanation. Targeted aging and re-lock checks, the platform historical-aging journey,
  the public functional/reporting aging rerun, lint/types and reversible migration catalogue
  parity passed. The combined-owner witness exercises retained-row/trace inputs; a full combined
  contract command-to-lock journey remains to verify before claiming all scenarios covered.
- Development scope is now public repository completion, not production readiness. Migration
  promotion, complete approval coverage, sandbox lock-chain reproduction and independent
  accounting sign-off are not completion gates. Sandbox refresh/isolation and key financial
  controls remain in scope. Preserve noncommercial licensing/publication exclusions; no deployment.

## RPO pre-termination version attribution and requested pause — October 20, 2026

- RPO rollforward carries original pre-termination fixed balances across intervening
  retained versions. It no longer settles a future cancellation early or loses the original
  modifications, estimates and cancellation when a memo version precedes termination.
  A superseding computation determines the pending termination. Competing original modification,
  estimate and partial-cancellation amounts are separated before the pending cancellation settles.
- New bindings retain rpo_pretermination_versions_v1; older bindings preserve prior behavior.
  Original boundary coverage, chronology, fixed amount reconciliation and dated realization
  guards remain required. Migration 0259 records the rule in the IPE catalogue.
- All 74 related cases pass, including original engine termination amounts with intervening
  read-layer memo versions, mixed later-version causes, monthly/range cuts and legacy behavior.
  Public currency report/retained-rate rerun, scoped lint/types and migration downgrade/upgrade
  exact catalogue parity pass. Adapted version chains are not new public lifecycle witnesses.
- Remaining work includes broader repeated cancellation/re-entry and mixed same-day entry,
  B4-11 concurrent commit visibility, independent accounting sign-off and final-candidate checks.
  This does not establish production readiness. Direct main; no deployment.
- Owner decision, October 20: combined-contract aging must retain the original receiving
  contract's aging and show member allocation adjustments separately. The policy question is
  resolved; implementation remains outstanding. After this current RPO fix is published,
  pause development as requested; do not start the aging implementation until resumed.

## Same-day RPO entry/cancellation survives later versions — October 20, 2026

- RPO rollforward now preserves the original gross entry, revenue and cancellation when a
  fixed contract activates and terminates on the same day and later retained versions exist.
  Previously the single-version gate could silently omit all three movements despite a zero
  closing balance. Later memo versions retain the original movements; later disclosure re-entry
  adds only the remaining balance and does not recognize the earlier revenue twice.
- New bindings retain rpo_same_day_entry_chains_v1; legacy bindings keep the single-version
  eligibility. Original dated termination/realization requirements and competing-cause guards
  remain in force. Migration 0258 records the rule in the report IPE catalogue.
- Original engine termination witnesses with zero/40 refunds cover later memo and re-entry
  read-layer versions, legacy behavior and absent boundary evidence. The 74-case related suite
  had 73 passes and one overly broad legacy assertion; corrected scoped cases pass. Public
  currency report/retained-rate rerun, lint/types and migration down/up exact catalogue parity
  pass. Later versions are supplied read-layer witnesses, not new public lifecycle commands.
- Intervening versions before termination, mixed same-day entry causes, broader repeated
  cancellation/re-entry, B4-11 concurrent commit visibility, combined-member aging ownership,
  independent accounting sign-off and final-candidate checks remain open. No deployment.

## Retained RPO FX evidence is readable in viewers and exports — October 20, 2026

- RPO and RPO rollforward viewers now expose retained exchange-rate legs by entity,
  period, source/target currency and average/closing basis, with original rate IDs,
  rate-set versions and knowledge cutoffs. Exact rate strings are not money-rounded.
- Standalone and packed XLSX exports present the same retained legs as structured tables;
  PDF includes labeled rate details. Excel stores rates as text to preserve decimal precision.
  Unknown legacy export shapes retain their generic control presentation. No new FX reads,
  accounting calculations, binding changes or database migration are introduced.
- Two viewer cases and two export cases pass, including 18-decimal precision, original
  version identity, same-currency legs and spreadsheet formula escaping. Scoped lint and
  backend/frontend type checks pass.
- Complex RPO lifecycle attribution, B4-11 concurrent commit visibility, combined-member
  aging ownership, independent accounting sign-off and final-candidate checks remain open.
  This presentation improvement does not close those gaps. Direct main; no deployment.

## Outstanding release verification

These checks need current release-candidate evidence. Historical October 3 results
remain in the dated build history; they do not verify current main. This list does
not authorize deployment, provisioning or changes to a live database.

- make audit-deps passed on clean 74bd148 (October 15): all 86 pinned Python runtime packages and npm runtime dependencies report zero advisories. Rerun on the final candidate.
- make docker-build passed on clean b4b8210 (October 15); rerun on the final candidate.
- make compose-verify passed on clean 74bd148 (October 15), including cleanup. Rerun on the final candidate.
- make zap-baseline passed on clean 4c4b583 (October 15), including cleanup; one documented low COEP warning and three informational alerts remain. Unauthenticated surface only; rerun on the final candidate.
- SUPERVISOR VERIFICATION NEEDED: make tf-validate (October 14 backend-disabled development validation passed; rerun on a clean final candidate).
- make restore-drill passed on frozen d7e8715 (October 15), exercising backup and restore-verify
  on a fresh disposable server. Rerun on the final candidate; hosted recovery is outside this scope.

## Historical release record

The earlier build-loop notebook is preserved in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).
Current outstanding implementation and verification gaps remain in
[the release limitations](docs/release/LIMITS-1.0.md).
