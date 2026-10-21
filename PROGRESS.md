# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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

## RPO cancellations survive later retained versions — October 20, 2026

- A first-batch cancellation is settled before a later retained version supersedes its
  revenue evidence. The same bridge now handles an opening obligation cancelled before the
  next retained version. Later cancelled versions carry retained revenue; re-entry admits
  only its remaining allocation, preserving the earlier cancellation and revenue lines.
- New report bindings retain rpo_cancelled_chains_v1; existing bindings keep the prior
  classification on rerun. The change also reaches monthly converted rollforwards through
  the shared Store. Accounting computations and original events are unchanged.
- The 50 scoped cases pass, including real-engine cancellation traces adapted into later
  retained/memo and re-entry chains, both estimate directions, refunds/non-refunds, full-range
  and monthly balances, and legacy behavior. Existing public modification reports/reruns in
  three views, scoped lint/types and migration 0243 down/up catalogue parity pass.
- Multiple cancellations within one computation, versions intervening before the original
  termination, same-day entry/cancellation, usage mixtures and combined-member aging ownership
  remain open. Independent accounting sign-off and final-candidate checks remain open.
  Direct main publication; no deployment.

## Original cancellation dates preserve historical RPO — October 20, 2026

- Stage 06 retains each obligation's original termination date and pre-boundary end date.
  Historical RPO and close-variance reads now preserve the pre-cancellation remainder;
  cancellation no longer removes that obligation from earlier months. New trace evidence
  drives the change; old computations without those dates keep their former behavior.
- A fixed-only first computation containing entry, modification, estimate change and one
  later cancellation can separate those movements, recognized revenue and cancelled remainder.
  Same-version subsequent-month rollforwards reconcile original deltas to the termination
  boundary. Later/missing event order and realized-usage mixtures are not inferred.
- Full engine witnesses cover positive/negative estimates, same-day ordered termination,
  refund/non-refund cancellation, historical standalone RPO/variance and monthly rollforwards.
  All 50 scoped cases and existing public modification reports/reruns in three currency views
  pass. Scoped lint/types and migration 0242 down/up IPE parity pass. No deployment.
- Multiple cancellations, first-entry cancellation followed by another retained version in the
  same range, same-day entry/cancellation, realized-usage mixtures and combined-member aging
  ownership remain open. Independent accounting sign-off and final-candidate checks remain open.

## Same-day estimate and cancellation ordering — October 20, 2026

- RPO now loads the immutable contract-event record sequence for estimate causes, using the
  same (effective date, record sequence, event key) order as the engine. A same-day estimate
  before the original termination can participate in the reconciled cancellation bridge;
  missing order or an estimate at/after termination remains unsupported.
- New bindings retain rpo_cancelled_changes_v2. Existing v1 runs keep their date-only rule and
  retain v1 again on rerun; older runs without cancellation decomposition remain unchanged.
  No event is reordered and no engine accounting amount changes.
- Full-compute positive/negative estimate cases now cover same-day termination, missing order,
  reversed order and v1 behavior. The eight targeted first-batch cases, public modification
  reports/reruns in three views, lint/types and migration 0241 down/up catalogue parity pass.
  No deployment; direct main publication.
- First-entry cancellation batches, multiple cancellations, usage mixtures, combined-member
  aging ownership, independent accounting sign-off and final-candidate checks remain open.

## Source-reconciled mixed RPO cancellations — October 20, 2026

- RPO can now separate modification and original estimate changes from a single terminal
  cancellation in a later retained version. Admission requires opening fixed allocation plus
  those original deltas to equal the trace's amount immediately before termination. A residual
  is not used as evidence. Cancellation still removes only unrecognized allocation; current
  revenue and prior-period revenue restatements retain their own lines.
- Cancellation identities and original before/after boundary amounts are loaded explicitly.
  New bindings use rpo_cancelled_changes_v1; older bindings retain their former classification,
  including in converted monthly rollforwards. No engine posting change.
- Full-compute concession/estimate/termination traces prove the pre-termination bridge for both
  estimate directions; mismatched starting amounts are refused. The 48 scoped cases include
  recognized/reversed/restated revenue, realized consideration, missing bridges and legacy
  behavior. Existing public modification reports and reruns in three views pass. Lint/types
  and migration 0240 down/up catalogue parity pass. No deployment; direct main publication.
- First-entry-and-cancel batches, multiple cancellations, usage-event mixtures and estimates
  on the termination day remain unsupported by this decomposition. Combined-member aging date
  ownership, independent accounting sign-off and final-candidate verification also remain open.

## First-batch RPO creation boundaries — October 20, 2026

- Stage 06 records whether the obligation existed before each boundary and the original
  event record sequence. For an obligation added after earlier modifications, RPO can now prove
  those earlier subject boundaries are legitimately absent instead of requiring nonexistent rows.
  Earlier event order must still be retained on another obligation in that same computation.
- A zero before amount alone is not absence evidence. Missing creation or earlier event order,
  multiple creation histories and missing post-creation boundaries keep the conservative fallback.
  Legacy traces are not backfilled; original accounting amounts and event order are unchanged.
- Full compute witnesses combine a price decrease, an addition later on the SAME day and a
  subsequent estimate increase/decrease in one first computation. New contracts, modifications,
  estimates and historical/monthly cuts reconcile, and the new trace nodes re-evaluate. The
  40 scoped report cases and public modification/report journey pass, including three currency
  views and reruns. Lint/types and migration 0239 down/up catalogue parity pass. No deployment.
- Combined-member aging date ownership, legacy evidence gaps, cancellation mixtures, independent
  accounting sign-off and final-candidate verification remain outstanding.

## Monthly RPO exemption translation details — October 20, 2026

- Converted rollforwards now retain each nonzero contract-period exemption movement in its
  original currency and the exact translated amount already used by the report. This explains
  nonzero translated flows even when the full-range original exclusions cancel at the endpoints.
  Existing obligation endpoint details remain separate; no allocation or FX math is done in UI.
- The viewer displays the monthly bridge even with no endpoint detail rows. Excel exports
  numeric source/translated cells with guarded identities; PDF exports readable period and
  currency amounts; CSV manifests retain the structured records. New bindings record
  rpo_exemption_translation_v1 and older bindings keep their existing control shape.
- Focused witnesses cover EUR-to-USD and EUR-to-USD-to-GBP: opposite original 100 movements at
  different monthly rates produce net 20 USD / 16 GBP, matching EXEMPTIONS with separate FX and
  zero rounding. Export, viewer, scoped types/lint, public report reruns and migration 0238
  catalogue parity are the necessary checks. No deployment; direct main publication.
- Combined-member aging date ownership, missing first-batch boundary histories, independent
  accounting sign-off and final-candidate verification remain outstanding.

## RPO obligations added to existing contracts — October 20, 2026

- Fixed a classification defect: an obligation absent from the opening version was always
  treated as NEW_CONTRACTS, even when an already disclosed contract added it by amendment.
  Added obligations now follow the modification/estimate causes of that existing contract.
  First admission and cancellation re-entry keep their admission semantics; ambiguous mixed
  changes without original estimate shares remain unexplained rather than becoming new contracts.
- New report bindings retain rpo_added_obligations_v1. Earlier bindings preserve their original
  classification on rerun; the same selected semantics feed converted monthly rollforwards.
- The public Marrowby approval journey adds O2 and redistributes O1: all 60,000 is MODIFICATIONS,
  NEW_CONTRACTS and UNEXPLAINED are zero, and all ties pass in transaction, functional and
  reporting views with identical reruns (USD in each view). The 38 scoped report cases cover
  mixed additions, legacy behavior, entry/re-entry and exemptions; lint/types and migration
  0237 down/up catalogue parity pass. No deployment; publish directly to main.
- This does not supply missing first-batch boundary history, resolve combined-member aging date
  ownership or provide independent accounting sign-off. Those remain outstanding.

## RPO first-batch modification attribution — October 20, 2026

- Stage 06 now retains fixed-allocation before/after amounts and signed changes for every
  obligation present at each modification boundary, including explicit zero changes. The new
  nodes re-evaluate from the retained engine state; accounting postings are unchanged.
- RPO first-entry batches separate later modifications and estimate changes from NEW_CONTRACTS
  when original event evidence is complete. Within one retained version, monthly modification
  and estimate movements must reconcile together to the dated fixed-allocation difference.
  Earlier months exclude future changes. Invalid boundary evidence is rejected.
- Targeted engine/report checks cover a native price-only modification followed by estimate
  increases and decreases, first-entry and monthly views, original-node replay and invalid
  evidence. Existing same-date/prospective modification checks and the public K01 period
  rollforward pass. Lint/types and migration 0236 down/up catalogue parity pass. No deployment.
- Old traces are not backfilled. Missing modification boundaries, newly introduced obligations
  lacking a complete boundary history and cancellation mixtures retain existing limitations.
  Combined-member aging date ownership and independent accounting sign-off remain open.

## Historical GL source identity — October 20, 2026

- Fixed a historical comparison defect: filtering updated_at before selecting the latest GL
  reconciliation could skip a later-reopened source and falsely PASS against an older reviewed
  source. New v4 runs select the latest eligible identity first; a later mutation now records
  NOT_APPLICABLE with its source link and a historical-evidence reason, without future totals
  or future review status. No older source is substituted.
- Previously retained v1/v2 arithmetic and v3 reviewed-source evidence keep their original
  controls. Accepted and unavailable v4 runs also reproduce from their retained evidence.
- Public API checks create two independently reviewed GL sources, then reopen the latest after
  the cutoff. Both balance reports refuse the stale fallback; earlier accepted runs and new
  unavailable runs rerun identically. The existing review workflow and 12 scoped control cases
  pass, with lint/types and migration 0235 down/up catalogue parity. No deployment.
- This does not reconstruct mutable reconciliation history that was never retained. Combined
  member-aging date ownership, independent accounting sign-off and final-candidate checks remain.

## GL reconciliation review table — October 20, 2026

- The report viewer now presents retained GL comparisons as a table: GL, retained subledger,
  report closing, both bridge differences and the net difference. Each row keeps its comparison
  and bridge results, source review status and original reconciliation link. Functional-currency
  scope is stated explicitly; unavailable values stay blank rather than becoming zero.
- Users can show all rows, recorded discrepancies or unavailable comparisons without changing
  the accounting run. General comparison notes remain visible when filtering. Older details
  without recorded results are not inferred to pass from their displayed amounts.
- Targeted viewer checks exercise offsetting aggregate differences, filters, missing amounts,
  source links and retained notes; TypeScript and scoped lint pass. Direct main publication;
  no deployment or accounting-calculation change.
- Combined-contract aging needs a presentation decision: retain original payer-owned layers with
  a separate member-allocation adjustment, or apportion original dated layers on the existing
  member liability basis. Current engine member totals alone do not specify that date ownership.
  The question has been raised with the owner; no new allocation rule is silently assumed.

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
