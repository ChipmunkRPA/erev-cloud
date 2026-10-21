# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## Transaction-currency RPO retains monthly unexplained differences — October 20, 2026

- Transaction-view RPO rollforwards now measure every selected period boundary and inspect
  original contract/entity/currency monthly differences. Opposite monthly gaps can no longer
  disappear behind a zero range total: any nonzero source gap fails the rollforward tie-out.
  Existing range rows stay intact and unexplained_details exposes each problem month in the
  viewer, XLSX/PDF and manifest, with unchanged original/report-currency amounts.
- New rpo_transaction_monthly_gaps_v1 bindings preserve the monthly rule and dated inputs on
  rerun; older transaction bindings retain prior range-only checks. Converted views retain
  their existing monthly checks. UI/export explanation now describes both source netting and
  currency rounding, and the viewer labels the second value as Report difference.
- A real builder/read-layer case has unsupported +10/-10 monthly changes and a zero net range:
  it fails with both details, reruns identically, and preserves the legacy pass. Supported
  modification movements still pass with no gaps. Scoped converted/exemption checks, existing
  viewer/export cases, the public three-view report/rerun journey, lint/types and migration
  0255 down/up exact catalogue parity pass. The gap case uses supplied retained version rows,
  not a new public API contract lifecycle journey.
- Complex cancellation/reentry and intervening pre-termination versions, same-day entry
  mixtures, combined-member aging ownership, independent accounting sign-off and final-candidate
  checks remain open. No deployment and no production-readiness claim; direct main only.

## Mixed retained-version causes separate while obligations remain active — October 20, 2026

- A later retained version that combines modification, estimate and partial-termination causes
  now separates their original fixed amounts even when the affected obligation remains in RPO.
  Complete original modification/termination coverage and estimate shares/dates are required;
  their sum must equal the actual version movement. Missing evidence or mismatches remain
  unexplained. New bindings retain rpo_mixed_continuing_changes_v1; legacy attribution remains.
- The engine-generated cross-month partial-cancellation case now also feeds a prior January
  version and a later February version into reporting. The surviving obligation's modification
  and cancellation amounts complete the contract's separate February movement lines without
  waiting for its March cancellation. This is an adapted retained-version read-layer witness,
  not a new public API partial-termination lifecycle journey.
- All 74 scoped RPO cases, original close-pass witness, legacy/missing-source/mismatched-delta
  checks, existing public three-view reports/reruns, lint/types and migration 0254 down/up exact
  IPE parity pass. No deployment; commit directly to main.
- Intervening versions before original termination, repeated cancellation/reentry, complex
  same-day entry mixtures, combined-member aging ownership, independent accounting sign-off
  and final-candidate checks remain open. This is not a production-readiness claim.

## Partial-cancellation reporting works before the surviving obligation ends — October 20, 2026

- First-entry and same-version monthly RPO cuts now attribute original partial-termination
  allocation effects on still-disclosed obligations to CANCELLATIONS, and retain the separate
  modification/estimate movements. Original explicit state for every termination is required;
  monthly movements must match dated fixed allocations. New bindings retain
  rpo_continuing_cancellations_v1; older reports preserve their earlier attribution.
- Fixed the engine blocker revealed by the cross-month scenario: JET-06 cumulative reclass
  components have an immutable destination role, so their never-applicable zero-weight role
  shares no longer collide with another destination's real accumulated balance. Ordinary split
  targets still retain explicit zero shares needed to reverse prior nonzero contributions.
- The full-engine witness now covers both same-period and February/March partial/full
  cancellations. February opening/new/modification/estimate/cancellation/closing lines and March
  revenue/cancellation lines reconcile. Actual NETTING_RECLASS close-pass lines preserve CA 20
  reversal and UR 280 reclassification; this is not merely an endpoint-balance assertion.
- 77 scoped RPO/netting cases, the added close-pass witness, existing public three-view reports
  and reruns, lint/types, and migration 0253 down/up exact catalogue parity pass. New lifecycle
  evidence is engine/read-layer coverage, not a new public API lifecycle journey.
- Mixed later-version changes while an obligation remains active, intervening pre-termination
  versions, repeated cancellation/reentry and complex same-day entry still require completion.
  Combined-member aging ownership, independent sign-off and final-candidate checks remain open.
  No deployment; direct-main publication only.

## Partial cancellations attribute allocation effects on other obligations — October 20, 2026

- Original nonzero fixed-allocation changes from earlier partial terminations now enter
  CANCELLATIONS, including first-entry/monthly cuts and mixed later-version bridges. They no
  longer inflate NEW_CONTRACTS or prevent the original modification/estimate split. Explicit
  per-event state and unique actual cancellation are required; nonzero effects after that
  cancellation remain unsupported. Same-day cross-effects require original sequence evidence.
- New rpo_cancellation_cross_changes_v1 bindings preserve the expanded rule; older report runs
  retain their classification. Migration 0252 and catalogue describe the same evidence rule.
- A full engine witness pools B prospectively when cancelling A, then cancels B. Original dated
  trace reads verify full/monthly and later-version attribution, with legacy/refusal checks.
  73 scoped cases, existing public three-view report/rerun journey, lint/types and migration
  down/up exact IPE parity pass. The new lifecycle witness is not a new public API journey.
- Repeated cancellation/reentry mixtures, intervening pre-termination versions, complex same-day
  entry mixtures and combined-member aging ownership still need work. Independent accounting
  sign-off/final-candidate checks remain open. No deployment; publish directly to main.

## Separate obligations can cancel in one retained computation — October 20, 2026

- Mixed cancellation attribution now selects the original cancellation of each obligation,
  rather than rejecting every contract with multiple termination causes. Each termination
  must retain explicit per-obligation state, exactly one must cancel that obligation, and
  every other termination must have zero fixed-allocation effect on it. The existing original
  opening/modification/estimate bridge still must reconcile; missing or cross-affected evidence
  remains unsupported. New bindings use rpo_separate_cancellations_v1; legacy rules are retained.
- A full engine case now applies a concession and estimate change, partially terminates A,
  then terminates B with two refunds. First-batch/monthly reporting and the later retained
  version bridge reconcile; legacy, missing metadata and nonzero cross-effects are checked.
- The 72 scoped cases, targeted negative checks, existing public three-view reports/reruns,
  lint/types and migration 0251 down/up IPE parity pass. New split-cancellation evidence is an
  engine/read-layer witness, not a new public API journey. No deployment; direct main.
- Cancellations with cross-obligation reallocations or repeated effects on one obligation,
  intervening pre-termination versions, complex same-day entry mixtures and combined-member
  aging ownership remain open. Independent accounting sign-off/final-candidate checks remain open.

## Same-day fixed activation and cancellation retain gross movements — October 20, 2026

- A single first computation with same-day activation and cancellation can now retain the
  original fixed allocation as NEW_CONTRACTS, original recognized revenue and the cancelled
  remainder, instead of omitting every movement because closing status is CANCELLED.
  Original termination date/before allocation and explicit zero realized evidence are required.
  Booked/activation/termination/memo causes are admitted; other event mixtures remain outside
  this path. Full exemptions still omit the movement; closing disclosure remains zero.
- New bindings retain rpo_same_day_entry_cancel_v1; earlier runs preserve their classification.
- Full engine refund/non-refund witnesses use actual dated trace reads and all original event
  causes. The 72 scoped cases, existing public three-view reports/reruns, lint/types and
  migration 0250 down/up IPE parity pass. The new engine cases are not a new API lifecycle test.
- Same-day modification/estimate/usage mixtures, multiple cancellations in one computation,
  intervening pre-termination versions and combined-member aging ownership remain open.
  Independent accounting sign-off and final-candidate checks remain open. No deployment.

## Reviewable monthly unexplained RPO differences — October 20, 2026

- Confirmed all 59 catalogue definitions have registered execution paths. Converted RPO
  rollforwards now retain every nonzero source contract/entity/period difference with its
  original amount and the exact translated amount already used by the report. Offsetting
  months or rounding to zero no longer hide why the existing source tie-out failed.
- The report viewer and run record show an open detail table; XLSX/PDF render readable rows
  and the CSV manifest retains the same facts. Currency registration now includes currencies
  present only in retained RPO/exemption details. No UI allocation, FX or root-cause inference.
- New bindings retain rpo_unexplained_details_v1; older runs keep their original control totals.
  Functional/reporting offset cases, viewer display, formula-safe numeric XLSX/PDF/manifest
  exports, existing public three-view reports/reruns, lint/types and migration 0249 parity pass.
- This identifies source differences; it does not repair unsupported attribution combinations.
  Multiple cancellations within one computation, intervening pre-termination versions, same-day
  entry/cancellation and combined-member aging ownership remain open. Independent accounting
  sign-off and final-candidate checks remain open. Direct main publication; no deployment.

## First-batch realized-fee cancellation settles before re-entry — October 20, 2026

- An original cancellation embedded in the first/opening computation can now settle its dated
  realized fees at the next retained re-entry. Intermediate cancelled corrections supply the
  final evidence for that segment; fees are settled once before admission of the new remainder.
  The fixed allocation bridge and retained revenue recognition remain separate.
- New bindings use rpo_cancelled_usage_v5. Retained v1-v4 preserve scope and markers on rerun.
  Missing realized evidence, missing obligations or excluded intermediate versions still cannot
  authorize the new segment reader. Original accounting amounts and events are unchanged.
- The 70 scoped report cases cover direct and intermediate-correction re-entry after first-batch
  or same-version monthly cancellation, positive/negative realized changes, revenue reversals,
  line-level expected results and legacy behavior. Existing public modification reports/reruns
  in three views, scoped lint/types and migration 0248 down/up IPE parity are the release checks.
  New combinations use retained-reader witnesses, not a new public API lifecycle journey.
- Multiple cancellations within one computation, intervening pre-termination versions, same-day
  entry/cancellation and combined-member aging ownership remain open. Independent accounting
  sign-off and final-candidate verification remain open. Direct main; no deployment.

## Realized fees follow cancellation and re-entry segments — October 20, 2026

- For separately retained cancellation/re-entry versions, realized fees now use the final
  cancellation evidence up to the next re-entry cut. Re-entry admits fixed plus realized
  allocation net of pre-entry revenue, and pre-entry realized fees are removed from in-scope
  VC changes. This repairs misclassification that could previously balance in total while
  understating NEW_CONTRACTS and overstating VC_ESTIMATE_CHANGES.
- New bindings use rpo_cancelled_usage_v4; retained v1-v3 keep their feature scope and markers.
  Excluded/missing obligations or absent realization evidence do not authorize the segment read.
  Original fixed allocation and revenue traces remain unchanged.
- All 70 scoped cases pass, including usage fees through one/repeated cancellation and re-entry,
  reports beginning before/after cancellation, line-level expected amounts and legacy behavior.
  Existing public modification reports/reruns in three views, lint/types and migration 0247
  down/up IPE parity pass. New re-entry cases are retained-reader witnesses, not API journeys.
- First-batch/same-version usage cancellation followed by re-entry, multiple cancellations in one
  computation, versions intervening before termination, same-day entry/cancellation and combined-
  member aging ownership remain open. Independent sign-off/final-candidate checks remain open.
  Direct main publication; no deployment.

## Realized-fee cancellation follows continuously cancelled version chains — October 20, 2026

- A retained cancelled tail now supplies the final realized-fee amount only when every
  subsequent version remains included/cancelled and retains dated realization evidence.
  First-batch, same-version opening and later-version cancellation bridges can use that final
  source; recognized revenue also follows the retained final version. Original fixed changes
  remain tied to their termination boundary, with no new source amounts invented.
- New bindings use rpo_cancelled_usage_v3. Existing v1/v2 runs retain their prior feature scope
  and marker on rerun. Chains with re-entry, missing obligations, excluded versions or missing
  realization evidence are not admitted by the new tail reader.
- All 66 scoped cases pass, now including signed later fee corrections against first-entry,
  monthly opening and later-version cancellations, legacy classification and absent evidence.
  Existing public modification reports/reruns in three views, lint/types and migration 0246
  down/up IPE parity pass. New chain witnesses adapt retained report data, not public API events.
- Usage chains with re-entry, multiple cancellations within one computation, intervening
  pre-termination versions, same-day entry/cancellation and combined-member aging ownership
  remain open. Independent sign-off and final-candidate verification remain open. No deployment.

## First-batch and same-version realized-fee cancellation — October 20, 2026

- A single first-entry cancellation computation and an opening-to-closing cancellation within
  one retained version now separate original realized fees. VC carries the realized change;
  cancellation removes fixed plus realized allocation net of recognized revenue. Original
  fixed modification/estimate bridges and dated realization evidence remain required.
- New bindings use rpo_cancelled_usage_v2. Retained v1 keeps its later-version-only behavior
  and retains v1 again on rerun. No event, accounting posting or stored amount changes.
- The 66 scoped report cases pass, including eight new reader cases for first entry versus
  monthly opening, realized increases/corrections, partial recognition and full reversal, plus
  legacy behavior. Existing public modification reports/reruns in three currency views,
  scoped lint/types and migration 0245 down/up IPE parity pass.
- New cases are report-reader witnesses, not a full-compute/API usage-plus-cancellation journey.
  Multi-version usage chains, multiple cancellations within a computation, intervening versions,
  same-day entry/cancellation and combined-member aging ownership remain open. Independent
  accounting sign-off and final-candidate verification remain open. Direct main; no deployment.

## Terminal realized usage stays out of fixed cancellation attribution — October 20, 2026

- For an opening obligation and one later terminating version, the report now uses the
  terminating version's dated realized amount when both versions retain realization evidence.
  Newly realized fees and signed corrections remain VC changes, rather than distorting the
  cancelled remainder. Mixed modification/estimate attribution still requires the original
  fixed pre-termination bridge; missing realization evidence preserves unexplained differences.
- New bindings retain rpo_cancelled_usage_v1; older bindings preserve former classification.
  The shared reader covers transaction and monthly converted rollforwards. No engine postings
  or original usage events change.
- Fifty-eight scoped report cases plus six engine realization cases pass. New reader cases
  cover positive/negative/zero fee changes, revenue restatement/reversal, missing evidence and
  legacy behavior. Existing public modification reports/reruns in three views, lint/types and
  migration 0244 down/up IPE parity pass. No new public usage/termination journey is claimed.
- First-entry/same-version usage cancellation, multi-version usage chains, multiple cancellations
  inside one computation, intervening pre-termination versions and combined-member aging policy
  remain open, alongside independent accounting sign-off and final-candidate verification.
  Direct main publication; no deployment.

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
