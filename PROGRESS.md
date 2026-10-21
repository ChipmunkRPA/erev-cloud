# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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

## Locked balance aging — October 20, 2026

- New closes freeze BALANCE_AGING alongside the existing twelve datasets. Original age buckets,
  transaction/functional/reporting amounts and reporting FX controls are authenticated in the
  manifest. The viewer supports retained currency selection; CSV exports and close evidence
  archives read only those bytes. Additional aging filters cannot alter a locked population.
- Re-lock comparison measures each aging bucket and total by entity, contract, role and currency,
  including a move between buckets with an unchanged total. Existing twelve-kind manifests remain
  verifiable/exportable; old locks without aging explicitly refuse that report, with no live backfill.
- Migration 0234 adds the snapshot enum and IPE metadata. Targeted API read/export, real foreign
  close-run freeze, public lock, new/legacy evidence archive, re-lock and viewer checks pass.
  Scoped lint/types and migrated catalogue parity pass. No deployment; direct main publication.
- This does not fill missing original layer evidence: combined-member functional aging whose
  owner layers do not reconcile still refuses. A new close now also requires its aging dataset
  to be reproducible; historical computations missing the required traces can require recompute.
  Independent accounting sign-off and final-candidate release checks remain open.

## Priced right-to-invoice advance billing — October 20, 2026

- Fixed the shared RTI source selector: a booked unit price selects delivered quantity even
  before the first delivery. Advance invoices therefore cannot become performance revenue,
  and later delivery cannot switch from an invoice-based price to a performance-based price.
- Stage 04 allocation and stage 09 recognition use the same corrected source. Rated usage
  retains priority; invoice fallback remains available when no unit price/performance source
  exists. Existing stored outputs are unchanged until a new computation is requested.
- Whole-engine checks cover before delivery, after delivery and additional billing, asserting
  price/allocation/revenue together. Related RTI/source/recognition checks pass (25 cases).
  The previously failing EUR case now computes: EUR 20,000 billed, EUR 10,000 earned, with
  USD 5,500 and 5,550 remaining in their original liability-age buckets. The public aging
  report reconciles. Scoped lint/types pass. No deployment.
- This closes the S04-R-02 diagnostic recorded in the functional-aging checkpoint. Broader
  combined-member aging, locked aging datasets, accounting acceptance and final release
  verification remain outstanding.

## Original functional aging layers — October 20, 2026

- Foreign asset/unbilled aging now reads original S12 reclass shares in functional currency,
  retaining the original S10 revenue date. Missing, wrong-currency or unlinked share evidence
  is refused; no report-side FX ratio is applied to those balances.
- Liability aging uses signed functional creation/consumption/remeasurement amounts from the
  selected version's immutable layers. Historical carrying and the approved monetary override
  preserve original creation dates, including partial consumption.
- New functional bindings retain this source path. Each member/role must match its dated
  functional balance before display; unmatched combined-member ownership remains unavailable.
  Reporting translation follows the existing retained closing-rate/cumulative-rounding path.
- Four API journeys pass: EUR unbilled dated remeasurement and reruns, historical and monetary
  USD/GBP liability layers with partial consumption, and reporting translation compatibility.
  Targeted core checks, lint/types and migration 0233 roundtrip/IPE agreement pass.
- A separate diagnostic exposed S04-R-02 failure after over-billing a right-to-invoice contract;
  it is recorded in LIMITS for follow-up. Locked aging datasets, combined-member allocation
  expansion, independent accounting acceptance and final candidate checks remain open.

## Reporting-currency balance aging — October 20, 2026

- Fixed reporting view returning untranslated aging amounts when transaction and functional
  currencies coincide. Supported functional age buckets now translate at approved retained
  closing rates, with currency/rate columns and source evidence in control totals.
- Cumulative bucket rounding conserves the translated contract/role total, including signed
  amounts and tiny balances. Functional balance reconciliation remains separate and explicitly
  labelled. New bindings retain translation behavior; legacy bindings keep original output.
- GBP-to-USD public report/rerun, existing asset/unbilled aging and later-billing rerun journeys
  pass. Focused core/catalogue checks, lint/types and migration 0232 roundtrip/IPE agreement pass.
- Foreign transaction-to-functional aging still requires exact functional layer attribution;
  this path remains unavailable. Locked aging datasets, independent accounting acceptance and
  final candidate verification remain open. Direct main publication; no deployment.

## Dated revenue-waterfall population — October 20, 2026

- New waterfall calculations exclude contracts entering after each performing entity's as-of
  period end. Entry comes from the first included version along the contract's membership
  chain and the book-specific activation/criteria/opening event, using the existing historical
  entry rule (fallback: that version's effective date). Later measurements do not delay entry.
- Entry dates and source-version identities are retained in versioned evidence. Bound reruns
  do not read current entry events; old bindings and already-frozen datasets retain their
  original population. Missing entry evidence is refused, not replaced by inception guesses.
- Public API checks cover March exclusion/April entry, retained reruns, performing-entity
  journal tie-out, restricted entity access and dated FX. Both regrouping computation orders
  pass. A pure retained-binding check covers differing calendar endpoints and legacy behavior.
  Migration 0231 updates the waterfall IPE and source list; scoped lint/types pass.
- B4-1/C-3's population implementation gap is closed. Independent accounting acceptance,
  broader lifecycle acceptance and final candidate verification remain open. No deployment.

## Filterable GL bridge workpapers — October 20, 2026

- Excel exports now render GL tie-out evidence as a filterable table, one row per retained
  entity/role. GL, retained subledger, report closing and both bridge differences are numeric
  cells with amount precision; review state, source ID, book/period and unavailability reasons
  remain separate columns. No balances or differences are recalculated during export.
- Missing evidence stays blank, distinct from zero. Equal/opposite bridge differences remain
  visible with FAIL even when the net difference is zero. Text retains formula protection.
- Single reports and disclosure workbooks share the renderer. Focused workbook and existing
  export checks pass; production renderer lint/types pass. Independent accounting acceptance
  and final candidate verification remain outstanding. Direct main publication; no deployment.

## Reviewed GL source gate — October 20, 2026

- New contract balance and rollforward runs require reviewed/certified GL reconciliation
  sources. Draft, prepared, reopened or missing review states remain unavailable, with source
  identity and reason retained; matching numbers alone cannot produce PASS.
- Versioned v3 bindings freeze review status. Earlier v1/v2 bindings retain their original
  arithmetic controls without live reads. Reopening a source changes new runs, not retained
  historical reruns.
- Eleven focused comparison/binding checks and two public API journeys pass, including
  draft/review/reopen, deterministic reruns and dated foreign functional balances. Migration
  0230 updates both IPE definitions. No deployment; broader lifecycle/accounting acceptance
  and final release-candidate verification remain outstanding.

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
