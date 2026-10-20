# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





## Credit-memo FX source attribution — October 20, 2026

- JET-10c attribution now resolves the original credit-memo difference trace into its
  retained liability reliefs, source owners, layer creation dates and event sequence.
  Each relief matches its original output and trace; the pinned rate and full difference
  formula are verified. Transaction portions are cumulatively converted in original trace
  order, preserving the once-rounded memo total and offsetting owner differences without a
  residual bucket or an allocation based on historical carrying value.
- Functional rollforward billing now uses the same retained spot conversion for those memo
  portions; actual posted EVENT FX adjusts each liability layer before its memo. Historical
  report bindings without the EVENT source path retain their former behavior. Derived source
  identities remain tied to immutable computation evidence and participate in paid-history
  subtraction. The engine and sealed journal amounts are unchanged.
- Necessary checks passed: actual single-layer and two-layer public memo/report workflows,
  ERP-imported and ENGINE-posted billing, source attribution and identical bound reruns. A
  USD 40,000 memo converts GBP 32,000 historical relief to GBP 33,600 at spot, with GBP 1,600
  FX and a GBP 40,000 closing liability. The two-layer full credit closes to zero with
  GBP 4,000 FX. Focused rounding/offsetting-owner and corruption checks, lint and types pass.
- Still open: public combined-contract credit-memo acceptance, late-carried public acceptance
  without reopening, recorded privacy/snapshot registry gaps and final accounting/release
  acceptance. This closes the ordinary JET-10c source gap, not every FX scenario. No deployment.

## Foreign lock-to-lock business attribution — October 20, 2026

- Difference replay now holds operational period states constant after verifying both original
  computations and frozen endpoints. A public reopen no longer blocks late-event attribution
  as an unsupported entity change. Entity, currency, book population and calendar dates remain
  strict; the evidence records entities.periods.states normalization and the final replay must
  still reproduce the later frozen money, including posted revenue.
- Control FX projection verifies the retained settlement formula when S12 emits a zero
  difference node without a movement row. It does not discard zero cumulative sums, so
  offsetting owners remain visible; altered rate evidence refuses.
- Necessary verification passed: actual foreign close/export/acknowledgement/lock, two-controller
  public reopen, EUR 4,000 late invoice, actual second close/lock, and public variance jobs in
  transaction, functional and reporting currency. Each attributes the asset reduction solely to
  LATE_EVENT (EUR 4,000 / USD 4,420 / EUR 4,000) and retains normalization evidence. Reviewed
  reconciliation rows are fixtures, not independent accounting approval. Scoped unit checks,
  lint and types pass. No deployment.
- Still open: credit-memo FX difference attribution (JET-10c has a retained difference trace
  but no remeasurement movement leaf), end-to-end late-carried public acceptance without
  reopening, recorded privacy/snapshot registry gaps and final accounting/release acceptance.
  This populated foreign two-lock witness does not establish every FX or membership scenario.

## Exact paid-origin window for carried FX — October 20, 2026

- TIME FX historical attribution now selects the target period plus its immediately preceding
  continuous closed/permanently-locked run, bounded by the retained anchor. It no longer treats
  every period between sparse calculation targets as paid: an intervening open period stops
  pooling, matching S14. EVENT/ALL retain their exact source origin. All period states come from
  the original encrypted computation input; today's calendar does not change reruns.
- Necessary verification covers sparse targets across an intervening open period, a retained
  anchor inside a locked run, EVENT origin isolation and refusal of TIME in a non-postable
  period; the existing actual multi-layer repeated-close/report scenario checks integration.
  Scoped lint/types pass. No deployment.
- Still open: end-to-end late-carried public acceptance, populated foreign two-lock acceptance,
  recorded privacy/snapshot registry gaps and final accounting/release acceptance. Correcting
  this selector does not establish those broader acceptance cases or production readiness.

## Regrouped FX source ownership — October 20, 2026

- Historical FX matching now uses S14's retained-membership regrouping rule. A stored group
  subject is compared under the computation's original member population; keyless legacy
  lines use that retained group/entity subject. Neither the sealed ledger fields nor the
  original source calculation is rewritten. Command intent checks retain exact stored subjects;
  only a missing subject uses the historical fallback.
- Necessary checks cover keyless settlement attribution, the actual reversal after the listing
  member leaves a three-contract group, and a two-contract public functional report. The latter
  assigns GBP 1,080 to the actual asset owner even though the ledger lists another member.
  The regrouping reversal retains the original paid-line dependency and delivered owner.
  The public August–September report after exit nets original/reversal/reposted FX to USD 200
  and passes the balance tie-out. Scoped lint/type checks pass.
- Scope correction: current control FX templates JET-10a/b/c select one role on each side;
  S14 does not emit split-weight targets for these flows. Unknown split formulas still refuse,
  but are not an outstanding feature for the current FX report path.
- Still open: late-carried public acceptance, populated foreign two-lock
  acceptance, recorded privacy/snapshot registry gaps and final accounting/release acceptance.
  Group settlement/exit cases do not establish every membership transition or production
  readiness. No deployment.

## Source-timed EVENT FX reporting — October 20, 2026

- Functional/reporting rollforwards now consume actual command EVENT posting deltas with
  original event sequence, source key, owner and asset/liability layer. Original and correcting
  postings net by dated source before walking the balance path. Billing settlement precedes
  its invoice; relief FX precedes revenue. New reports remove both old synthetic settlement
  movements, avoiding duplicate timing. Historical bindings retain the original path.
- New event_posted_fx_v1 bindings retain every command line, recursive paid dependency and
  evidence hash. Report execution rechecks its requester before authorized computation reads;
  close snapshots retain the restricted read-only SYSTEM path. Migration 0194 documents these
  source tables and semantics in the report IPE catalogue.
- Necessary checks: ERP and ENGINE foreign invoice rollforwards with source bindings and
  identical reruns; repeated liability close; command reversal and its net-zero report; scoped
  projection/path/catalogue checks and lint/types. No deployment.
- Still open: split-target formulas, regrouped/keyless historical subjects, combined-membership
  and late-carried public acceptance, populated foreign two-lock acceptance, recorded privacy/
  snapshot registry gaps and final accounting/release acceptance. These ordinary settlement
  cases do not establish production readiness or all Reporting requirements.

## Contract-computation FX evidence — October 20, 2026

- The shared FX attribution reader now adapts original command-computation input/output
  evidence as well as close-pass envelopes. It authorizes the complete retained group,
  verifies the encrypted source hashes, version trace and exact posting intent, and uses
  the original per-book seal cutoff to select historical paid lines. Version evidence keeps
  its real version identity; no synthetic close record or current-rate reconstruction is used.
- Paid attribution now follows actual command settlement and reversal histories recursively.
  Necessary checks passed: actual GBP 1,080 settlement and GBP 540 reversal with the original
  paid-line identity and both computation evidence hashes, plus scoped lint/types.
- Still open: public rollforward EVENT settlement timing must consume these sources without
  duplicating the existing before-invoice settlement flow and period-end offset. The TIME
  report path is unchanged. Split targets, regrouped/keyless historical subjects, combined
  and late-carried public acceptance, populated foreign two-lock acceptance, recorded registry
  gaps and final accounting/release acceptance remain open. No deployment or readiness claim.

## Mixed asset/liability FX sources — October 20, 2026

- Signed control-target attribution now admits retained contract-asset and liability
  remeasurement leaves, preserving role, owner, layer and creation date through prior-target
  and paid-history subtraction. Functional/reporting rollforwards direct asset FX to assets
  even with a live liability layer; liability FX remains layer-specific. Same-day closing
  corrections net per role/layer before application, so UUID ordering cannot overdraw a layer
  when a later close reverses an earlier remeasurement.
- New reports bind control_posted_fx_v2. Historical liability_posted_fx_v1 bindings preserve
  their original asset-path choice. Migration 0193 updates the report IPE source catalogue to
  name encrypted close-pass evidence and recursive paid-line attribution.
- Necessary checks: actual reporting-currency asset rollforward/rate change/rerun, actual
  repeated liability close and report source binding, snapshot producer/migration checks,
  36 focused catalogue/trace/path checks, scoped lint/types. Synthetic mixed-target checks
  verify opposite asset/liability signs and asset flows that must not consume liabilities.
- Still open: command-computation evidence adapters and paid attribution, split-target
  formulas, combined-membership and late-carried public acceptance, populated foreign
  lock-to-lock acceptance, the recorded privacy/snapshot registry gaps and final accounting
  acceptance. A synthetic mixed target is not a populated combined-contract public witness.
  No deployment or production-readiness claim.

## Historical paid FX and rollforward integration — October 20, 2026

- Close-pass evidence format 2 freezes the exact sealed FX control-line population read by
  the pass, including zero-net histories. The reader selects paid lines by retained role,
  currency, class, reason and origin/anchor periods, verifies their ledger fields and recursively
  resolves their retained close-pass deltas. Per-call memoization shares repeated dependencies;
  results bind every paid line and retained evidence hash. Format 1 remains readable but cannot
  establish automatic paid attribution; missing history refuses rather than allocating a plug.
- Functional/reporting contract-balance rollforwards now consume retained liability TIME
  deltas. Original creation dates keep opening/current-range layer identities, and group-level
  amounts follow source owners. New source bindings retain and recheck attribution dependencies;
  old bindings keep their original path. Asset-only FX remains on its existing path.
- Necessary checks passed: actual same-period second close after delivery, with nonzero prior
  paid amounts and explicit report source-binding assertions; original report rerun; the single
  liability close; ERP/ENGINE functional invoice paths; 25 focused projection/path checks and
  scoped lint/types. No deployment.
- Still open: command-computation paid adapters, mixed asset/liability target decomposition,
  combined-membership and late-carried public acceptance, populated foreign two-lock acceptance,
  recorded privacy/snapshot registry gaps and final release/accounting acceptance. Current tests
  do not establish completion of all combined/late-carried FX or production readiness.

## Signed liability FX posting attribution — October 20, 2026

- Added a signed trace projection from retained S14 targets through S12 cumulative sums to
  actual liability layer owners. The posting calculation subtracts the prior target and
  explicitly supplied attributed paid layers, distinguishes TIME from EVENT, and verifies
  every intermediate sum, retained time component, paid total and final journal delta.
  Missing/corrupt sources, unknown split formulas and unprovided nonzero paid history refuse.
- The internal close-pass reader now resolves a selected sealed FX control line to its unique
  retained delta by target, posting period, currency and amount. Its evidence adapter keeps
  source identities scoped to the immutable close record rather than inventing version rows.
  A real GBP 5,400 close-pass delta reproduces with its actual contract/layer ownership. Two
  synthetic two-owner cases verify TIME/EVENT subtraction, differing owner shares and refusal
  of missing paid/source evidence. Scoped lint/types and these necessary checks pass.
- Still unfinished: selecting/authorizing and recursively attributing historical paid lines,
  command-computation evidence adapters, wiring attribution into rollforward presentation and
  acceptance for combined/late-carried cases. No report-completion or production-readiness
  claim; no deployment. Registry issues recorded in the preceding checkpoint remain open.

## Retained close-pass calculation evidence — October 20, 2026

- Found the underlying CLOSE-PASS-TRACE-1 gap: actual close-pass ledger lines have no contract
  version/trace record. Latest contract traces cannot establish what an earlier pass posted.
  Revision 0192 now retains each actual pass's typed input, explicit pass name, selected book
  output, trace and selected line fields in encrypted storage, atomically with its sealed
  posting. Group entry indexes distinguish pooled postings. Source reads check file, logical
  input/output and trace hashes and the selected ledger line; historical absence stays absent.
- Added immutable tenant-scoped links, file ownership/retention holds, privacy classification
  and scenario regeneration rules. FX pass/idempotence, populated foreign public lock and
  automatic netting reversal checks pass; evidence remains after recomputation. Mutation and
  cross-tenant checks, 12 scoped file-registry/census checks, lint and scoped types pass.
- Not complete: reporting must consume this evidence and reconstruct attributed paid history
  for combined/late-carried liability FX; existing historical passes cannot be silently rebuilt.
  A broader registry check also exposed pre-existing unclassified evidence_sample_file,
  forecast_actuals_capture, scenario_refresh and forecast/import fields, plus stale snapshot
  reference-count/excluded-column expectations. Those remain release work (four checks fail
  after updating the regenerated-table census). No deployment or accounting acceptance.

## Currency exports in close evidence packs — October 20, 2026

- Close/re-lock packs now include functional and reporting CSVs for all six retained currency
  snapshot kinds, alongside the existing transaction paths. Snapshot identities retain original
  bundle hashes/counts and list each delivered view's path, hash, row count and control totals.
  Each export uses its retained column schema and spreadsheet formula guard. Historical
  single-view locks remain single-view; no current rates or live rebuilds are substituted.
- Targeted archive checks cover actual snapshot production, legacy locks, manifest/hash/count
  refusal and formula guards. Combined/late-carried liability FX and populated foreign two-lock
  acceptance remain outstanding. No deployment or production-readiness claim.

## Populated foreign-currency public lock — October 20, 2026

- The public lock witness now includes a EUR contract of a USD entity reporting in EUR. It runs
  actual close jobs and journal submit/approve/export/acknowledgement before requesting lock and
  obtaining a different Controller's approval. Frozen unbilled balances are EUR 10,000 in
  transaction/reporting currency and USD 11,050 functional. All monetary endpoints in all three
  views reproduce from the retained computation, after the source-read transaction closes.
- Reconciliation review rows remain test fixtures; this is not independent accounting approval.
  The domestic K01 public lock remains covered. This closes the single populated foreign-lock
  witness, not the still-outstanding two-lock foreign-currency report acceptance.
- Inspection for late liability FX found that S14 emits cumulative target differences and the
  ledger trace points to that target; fx_layer_key is not populated by the current product writer.
  The report's latest-version layer movements cannot simply be treated as those posted deltas.
  Next implementation must reconcile retained target/posted history and source-layer ownership;
  direct allocation from an assumed ledger layer key would be unsupported. Combined/late-carried
  liability FX remains unfinished. No deployment or production-readiness claim.

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
