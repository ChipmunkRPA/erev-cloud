# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





## Step-1 netted reporting forecasts — October 20, 2026

- Dated projections now freeze original deposit recognitions and apply the engine's existing
  Step-1 netting formula after manual adjustments. Every net target cites the attributed original
  deposit share; later adjustments cannot rewrite the historical schedule.
- Added a separate dated reporting remainder that excludes already-recognized 25-7 deposit
  revenue. The contract's stored cumulative measurement identity remains unchanged. Report
  schedule readers require projected periods to sum to the net remainder; zero means no future
  forecast. Legacy traces retain their original checks, without guessed deposit deductions.
- Six engine journeys cover release/defer/override with partial and full prior deposit revenue,
  replay every source chain and compare future periods with original schedules. Reader checks
  confirm the separate reporting basis and reject negative/excess balances. Related usage,
  royalty and historical-reader regressions pass (132 cases plus 3 new reader checks). Migration
  0229 applied locally and all three IPE definitions match; lint/types pass.
- Broader public API lifecycle and close-pass acceptance, independent accounting acceptance
  and final release checks remain outstanding. This completes the deterministic Step-1/manual
  projection path, not arbitrary source-changing or event-driven forecasts. No deployment.

## Original-cut royalty manual projection — October 20, 2026

- Added historical manual release/defer/override projection for fixed guarantees plus realized
  royalty components. Frozen snapshots filter both measure events and estimate pins by their
  original effective/application dates. Separate royalty projection nodes retain statement and
  accrual sources without duplicating live true-up nodes.
- Projections require stable original royalty sources, recognized amounts and guarantees over
  the frozen horizon. Unsupported source changes remain explicit refusals. The override anchor
  now retains recognized royalties, with subsequent signed changes separate from time respread.
- Six JPY journeys cover all three adjustment kinds, later statements above/below the guarantee,
  later accruals and releases. Every trace replays; future periods equal the original schedule,
  survive the contract reader, and sum to the original dated remainder. Downward corrections
  preserve the existing approved manual-release floor rather than bypassing S09-R-38.
- Related recognition/dated-reader checks and lint/types pass. Migration 0228 was applied locally;
  the three IPE definitions match the catalogue. Netted mixed projections, broader public API lifecycle
  and close-pass acceptance, independent accounting acceptance and final release checks remain
  open. Direct main publication; no deployment.

## Mixed usage manual projection — October 20, 2026

- Historical projections now freeze already-realized PERIOD_VC amounts and replay manual
  release, deferral and schedule override against the complete original-cut target. Later usage
  and later adjustments are excluded; changing realized amounts within the frozen horizon
  retain an explicit refusal rather than becoming a fixed forecast.
- Fixed-plus-usage overrides exposed an engine defect: after the last listed period, respread
  discarded the realized consideration and completed at only the fixed allocation. The anchor
  now includes already-realized consideration; usage realized after that anchor enters revenue
  immediately through a retained realized_delta parameter (legacy traces default to zero).
- Three adjustment journeys compare every historical future period with the original schedule,
  replay every trace node, pass through the contract trace reader, and reconcile to the dated
  scheduled remainder. Explicit checks preserve 1,200 fixed + 100 original usage at completion
  and recognize later 400 usage in its own month. Existing dated/fixed/manual paths also pass.
- 113 scoped engine/reader cases and 7 catalogue cases pass; migration 0227 was applied locally
  and all three IPE definitions match the catalogue. Lint/types pass. Royalty/netted mixed projections, broader
  public API lifecycle and close-pass acceptance, independent accounting acceptance and final
  release checks remain open. Direct main publication; no deployment.

## Combined-member agent refund reporting — October 20, 2026

- Fixed a real GBP 75,600 unexplained rollforward difference after a combined agent contract
  refunded its two deposits and returned all delivered units. A full return can erase prior
  consumed layers from the latest target; negative posted controls now identify recipients
  for original target/paid-history replay.
- Member billing classification now uses retained asset amounts including explicit zero.
  This moves liability-only credit memos out of the local member's apparent asset activity,
  without using OTHER as a plug. New source bindings preserve legacy report rerun behavior.
- The scenario funds agent deliveries from another contract's two USD 45,000 advances at .80;
  the agent's own advances use .84. Group allocation is independently checked, original source
  owners remain retained, and the full return preserves the USD 90,000 x .04 GBP difference
  in revenue/control rather than inventing a supplier balance. Both public reports rerun in
  all three currency views; the rollforward must tie across all members.
- Six scoped DB journeys and 35 report/catalogue unit checks pass, with lint/types and migration
  metadata checked. Migration 0226 updates the report's IPE explanation. Broader close-pass acceptance, dated
  mixed manual-adjustment projection, independent accounting acceptance and final release
  verification remain open. No deployment.


## Agent refund and full-return reversal — October 20, 2026

- A real two-deposit refund/return journey exposed two engine defects: returned units did not
  advance the agent's latest transfer date (so a preceding credit memo was ignored), and a
  zero-weight role was omitted instead of clearing its old cumulative target. The original
  return quarantined with an unbalanced revenue-recognition entry; both defects are fixed.
- S10 now includes returned_cum changes as transfer boundaries. S14 retains zero-weight targets.
  Split-source readers validate explicit zero baselines only before any original functional
  source, using the retained calendar; missing later source history still refuses attribution.
- The DB journey posts the full reversal: USD 90,000 gross / 18,000 net / 72,000 supplier, with
  all three role balances zero in transaction and functional currency. September reports show
  negative gross revenue and zero opening-liability relief, with retained reruns in all views.
- Single-deposit and zero-net journeys, 63 scoped engine/source cases, lint and types pass.
  Cross-contract agent groups and broader close-pass acceptance remain open; this supersedes
  the prior unverified gross-refund/return case. Independent accounting acceptance and final
  release checks remain outstanding. Direct main publication only; no deployment.


## Agent gross relief across original source layers — October 20, 2026

- Two prepayment layers previously failed the split-role reader's unique-origin guard. Agent
  control attribution now falls back specifically on that ambiguity: gross control targets and
  original control paid history supply the source owners; net/supplier scalar targets and paid
  histories are independently replayed in both currencies. No per-owner net split is invented.
- Revenue history captures CONTRACT_LIABILITY only for REVENUE_RECOGNITION. Close envelopes
  declare that capability; older envelopes without it refuse the gross fallback. Both report
  consumers retain the gross control ID alongside component amounts and original evidence.
- The DB journey covers two 45,000 deposits, separate source layers, later supplier paid history,
  both public reports in all currency views and identical reruns. Single-layer and zero-net cases
  also pass. Scalar evidence has no movements and cannot masquerade as an attributed delta;
  changed functional split amounts fail. Scoped lint/types and source checks pass.
- Migration 0225 documents this path. Cross-contract agent groups, gross-control reversals and
  close-pass agent acceptance still need representative coverage; individual net/supplier
  source allocation remains unavailable without original owner evidence. Existing disclosure
  gross-relief policy and independent accounting acceptance remain open. No deployment.


## Public revenue cause / posting-class distinction — October 20, 2026

- Correction to preceding mixed-TIME entries: the production S13 costs_view explicitly leaves
  released_at_close empty for revenue (L3-2-Q-15). Deterministic NORMAL revenue and TP_CHANGE
  therefore post as EVENT. The schedule close-release flag is not the posting classifier.
  Conditional mixed-TIME support is an internal producer capability, not a presently missing
  public revenue workflow; do not change posting timing merely to exercise that capability.
- The actual public workflow uses a prepaid GBP service and an approved May bonus. Its May
  schedule separates NORMAL 3,224.18 and TP_CHANGE 445.05; public revenue/opening relief is
  3,669.23. Original counterpart amounts and EVENT-only target evidence are checked independently.
  Both public reports pass all three views and retained reruns, with zero OTHER and balance ties.
- Remaining live priorities include multi-origin agent split attribution and documented dated
  projection gaps. Independent accounting sign-off and final-candidate checks remain required.
  No deployment. This entry supersedes the earlier public mixed-TIME acceptance task.


## Mixed-period TIME source amounts — October 20, 2026

- S14 retains per-period transaction and functional TIME deltas from its original cumulative
  targets, including rounding and role signs. No posting amounts or allocation policy change.
- Reporting now handles a mixed cumulative input spanning periods/owners when each mixed period
  has one original provenance. That period's TIME/EVENT amounts use the retained pair, with
  both-currency total checks. Multiple owners within one mixed period still require finer evidence.
- Source tests cover signed foreign amounts, changed functional evidence, missing history and
  ambiguous owners. An original S14 mixed-period output feeds the report reader directly.
  Uniform-period legacy source ordering is preserved for retained reruns.
- Scoped source/engine cases, the DB intercompany reversal/public-report rerun journey, lint/types
  and migrated catalogue checks pass. Migration 0224 documents the two consumers. A dedicated
  public mixed-period workflow, multi-origin split and independent accounting sign-off remain
  open. No deployment; direct main publication.


## Zero-net agent reporting — October 20, 2026

- A zero-net agent entry can now use its sole AP_SUPPLIER counterpart. No zero revenue line is
  invented. The entry must contain exactly the control and supplier lines; scope, currencies,
  original source amounts and both-currency balancing remain mandatory.
- Unsplit gross-billing targets now resolve original functional revenue sources. Retained report
  evidence identifies the supplier counterpart explicitly, preserving earlier nonzero shapes.
- The DB journey covers zero and nonzero fees, net posted amounts, original supplier history,
  both source currencies, and both public reports in all three views with identical reruns.
  No unexplained OTHER remains and balance tie-outs pass. Scoped lint/types pass.
- Migration 0223 describes this path. Multi-origin split and within-period mixed attribution,
  broader agent close/reversal acceptance and independent accounting sign-off remain open.
  The disclosure's existing gross-control-relief column policy is unchanged. No deployment.


## Agent gross/net reporting attribution — October 20, 2026

- Retained revenue histories now include only the AP_SUPPLIER purpose of revenue-recognition
  clearing lines. Close-pass envelopes declare that capability; older envelopes without it
  remain unavailable. Original intent, purpose and paid-history amounts are checked.
- Agent control relief is reconciled against separate net revenue and supplier components in
  both currencies. Original split formulas/rounding and unique source ownership are replayed;
  report evidence retains both component IDs and amounts without relabelling gross relief as net revenue.
- The actual merchant engine example reproduces 120,000 gross / 19,200 net / 100,800 supplier.
  The DB workflow exercises two deliveries, supplier paid history and public balance-rollforward
  and opening-liability reports in transaction, functional and reporting views with identical
  retained reruns. Intercompany reversal, 36 scoped cases, lint/types and migration checks pass.
- This supersedes the preceding entry's missing supplier-history/control matcher limitation.
  Multiple-origin split inputs, zero-net agent paths, within-period mixed-source attribution,
  and broad close-pass agent acceptance remain open; no overall production readiness is claimed.
  Migration 0222 documents the two consumers. Direct main publication; no deployment.


## Split-role revenue source reader foundation — October 20, 2026

- The retained revenue reader now replays the original split role formula for a single uniquely
  owned revenue input. Both currency shares must match original weights, role index, side sign
  and minor-unit rounding. TIME/EVENT amounts and provenance remain independently checked.
- 36 scoped role-template/source cases and lint/types pass, including split rounding, mixed
  TIME amounts, changed transaction evidence and changed functional role amounts.
- Agent report integration is NOT complete: for_control still requires net revenue to equal
  gross control relief. Supplier history is absent from the close-pass revenue paid population.
  Next work must retain/verify AP_SUPPLIER and reconcile the separate gross/net components;
  removing the equality check alone would be incorrect. No public agent acceptance is claimed.
- Multiple-origin split inputs, other mixed-source gaps and independent sign-off remain open.
  Direct main publication only; no deployment.


## Readable RPO exemption exports — October 20, 2026

- XLSX exports now render retained exemption facts as rows with readable policy names, wrapped
  text and numeric amounts, instead of one JSON cell that can exceed Excel's 32,767-character
  limit. PDF exports emit per-obligation endpoint and movement lines with existing pagination.
- A 120-obligation case larger than the cell limit retains the final record, all signed amounts
  and the transaction-currency basis. Text retains the formula guard; amounts are not recomputed.
  The CSV companion manifest retains the complete original facts without changing CSV columns.
- Focused export checks and lint/types pass. No accounting or report-total changes, no deployment.
  Remaining mixed-source functionality and independent accounting acceptance are still open.


## RPO exemption change detail viewer — October 20, 2026

- RPO rollforward now retains obligation-level opening/closing excluded amounts, dates, rule
  codes and the signed exemption movement. Full eligibility transitions and partial POL-200
  release use the same figures as the rollforward, without changing its accounting totals.
- Both report and run pages show a collapsible detail table with readable exemption names.
  Functional/reporting views explicitly label these original transaction-currency figures;
  the browser formats backend amounts without recomputing the movement.
- New source bindings opt into the details; legacy bindings retain their earlier output shape.
  Migration 0221 records the metadata. Focused policy/endpoint tests, the viewer case, lint/types
  and migrated catalogue checks pass. The DB multi-currency RPO journey also confirms retained
  exemption details after a rate revision and rerun. Broader reporting and independent accounting acceptance
  remain open. Direct main publication only; no deployment.


## Mixed revenue by retained recognition period — October 20, 2026

- S14 now retains per-input period classes from original relief causes, bounded by each target
  period. NORMAL is TIME only for close-released obligations; mixed periods stay explicit.
  Concession/multiple-input/split shares do not acquire invented classification evidence.
- Reporting can attribute mixed cumulative inputs across multiple owners/layers when each
  source period has a uniform class. It preserves original signed amounts and reconciles TIME
  independently in transaction and functional currency. FX readers accept the new annotation.
- 46 scoped engine/source cases, the DB intercompany progress-reversal workflow and two-month
  foreign-balance/GL journey pass. Scoped lint/types and both migrated IPE definitions match.
  Within-period mixtures, functional allocation mismatches, split/non-revenue inputs and broad
  mixed public-workflow acceptance remain open. Migration 0220 describes the two consumers.
- No deployment. Independent accounting sign-off and final release verification remain open.



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
