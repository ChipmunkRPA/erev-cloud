# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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

## Reporting-currency close variance — October 20, 2026

- The public variance report now offers reporting currency (migration 0191). Ordinary replay,
  connected membership changes and independent population changes use authenticated lock rate
  bases. Business effects use earlier reporting rates; a final FX phase applies later reporting
  rates after any transaction/functional FX phase. Identical retained computations with changed
  lock rates produce FX effects, never a fabricated business event or PROGRESS residual.
- Replay evidence retains both reporting-basis hashes and marks the reporting_rates phase.
  Entry effects are valued at earlier rates before FX; exits remove the earlier frozen value.
  Currency/period basis changes and missing historical rates explicitly refuse. New reporting
  waterfall snapshots retain the selected period's average even when there is no revenue, so
  later population comparisons need not read current reference settings.
- Necessary checks: real-engine business/FX and unchanged-computation cases, population entry,
  combined-membership reporting replay against authored frozen datasets, and public empty-lock
  jobs with bound reruns/revocation. Actual empty lock publication verifies retained averages;
  68 focused registry/rate checks, 96 frontend checks and scoped lint/types pass.
- Still outstanding: populated foreign-currency public lock-to-lock acceptance, combined and
  late-carried liability FX, other documented reporting gaps and final release verification.
  Older locks missing required currency/rate evidence cannot be silently reconstructed.
  No deployment or independent accounting sign-off; production readiness remains unproven.

## Retained reporting-rate projection — October 20, 2026

- Added a reporting-rate basis read only from verified WATERFALL, CONTRACT_BALANCES and RPO
  currency bundles. The basis binds source hashes and selected rate identities; balances must
  supply their own closing rate, conflicting retained conversions refuse, and nonzero revenue
  cannot borrow a closing rate when its average rate is absent.
- The replay projection now supports reporting amounts using per-line average revenue rates,
  separately rounded balance components, and sequential functional/reporting rounding of gross
  RPO and its exemptions per obligation. Original-source verification accepts this explicit basis.
- Necessary checks cover real-engine projected amounts and source reproduction, missing rates,
  corrupted snapshot hashes and conflicting metadata. A database witness reads all three actual
  snapshot producers and retains USD 11,000 -> EUR 10,000 revenue conversion. Targeted lint/types pass.
- This is the projection prerequisite: the public variance report still offers transaction and
  functional views only. Reporting rates must next be bound through each replay phase, with a
  separate reporting FX change (including unchanged engine inputs) and population/membership
  handling. Public reporting-currency variance, populated foreign lock-to-lock acceptance and
  the other documented gaps remain. No deployment or independent accounting sign-off.

## Functional close-variance attribution — October 20, 2026

- Variance between closes now exposes transaction/functional currency selection. The selected
  basis flows through frozen endpoints, ordinary groups, membership changes, population changes,
  driver totals and presentation. Functional source identity and cell evidence bind the currency
  choice; old transaction bindings retain their original form. Migration 0190 updates the stored
  report schema so existing repositories receive the selector.
- Foreign RPO replay now values each obligation from retained positive closing rates, rounding
  gross consideration and exempt amounts separately before subtraction. Missing/ambiguous rates
  and historical locks without the selected frozen view refuse; endpoint differences are never
  hidden in OTHER. A real-engine EUR example gives USD 79.51 of RPO FX movement, including
  per-obligation rounding, and conserves all replay endpoints.
- Necessary checks: populated real-engine group replay against authored frozen bundles; retained
  currency selection and missing-view refusal; database worker/reauthorization/bound-rerun on
  empty published locks; frontend fixtures and scoped lint/types. These are distinct witnesses,
  not a populated foreign-currency public-lock acceptance test.
- Remaining: reporting-currency close variance (not offered yet), populated foreign-currency
  lock-to-lock acceptance, combined/late-carried liability FX and documented release gaps.
  No deployment or independent accounting sign-off; the overall objective remains unfinished.

## Rollforward and disaggregation currency locks — October 20, 2026

- Extended immutable three-view lock storage, as-locked API/UI selection, CSV export and relock
  comparisons to contract balance rollforward, RPO rollforward and revenue disaggregation.
  Per-view schemas (including RPO translation rounding) and controls remain inside the hashed
  snapshot; report readers do not rebuild live inputs. Existing historical locks still refuse
  alternate views they never retained.
- Database checks cover each added report in all three views through API and exact CSV output
  with its live builder disabled, plus public empty/populated lock publication. A foreign-currency
  disaggregation witness retains EUR 10,000 transaction, USD 11,000 functional and EUR 10,000
  reporting revenue with rate evidence. Targeted fixture/unit checks, 94 frontend checks,
  frontend types and scoped lint pass.
- Remaining implementation includes close-variance currency selection and attribution against
  these snapshots, combined/late-carried liability FX and documented reporting/release gaps.
  No deployment or independent accounting sign-off; no production-readiness claim.

## Immutable currency views at lock — October 20, 2026

- Public lock publication now retains transaction, functional and reporting variants for
  waterfall, contract balances and RPO in one manifest-hashed machine CSV per dataset. Per-view
  columns, controls and available rate evidence are authenticated inside that same file.
- As-locked API, report viewer and exports select retained variants without live recomputation.
  Old locks remain readable on their original basis and explicitly refuse missing alternatives.
  Relock comparisons expose functional/reporting changes separately from transaction changes.
- Necessary checks: actual public lock publication and populated K01 balances; retained API/CSV
  selection with the live builder disabled; 62 focused Python checks and 94 frontend checks;
  targeted lint, types and frontend compilation. No deployment.
- Remaining: alternate-currency rollforward/disaggregation lock datasets and close-variance
  integration, combined/late-carried liability FX, and other release limitations. This checkpoint
  does not complete all four reporting workstreams or provide independent accounting sign-off.

## Explicit currency bases for snapshot producers — October 20, 2026

- SnapshotScope now carries an optional currency view. Producers normalize it through the
  actual report parameter schema, reject unsupported/invalid views and use the report's existing
  currency calculations. None preserves current defaults, including functional-only registers.
  Explicit-view output controls name the view and exact historical currency cutoff.
- Real database witnesses cover functional/reporting waterfall amounts (USD 11,000 / EUR 10,000),
  reporting RPO bands/totals and re-generation at the original cutoff after a revised approved rate.
  The latter follows the record clock before publishing the revision, so the temporal assertion
  is meaningful. Existing snapshot unit checks pass after updating stale adapter stub signatures.
- This is producer support, not completed lock integration: lock publication still stores each
  kind's default view, and as-locked currency selection remains unsupported. Next work must bind
  alternative datasets to immutable lock evidence and serve those retained variants, preserving
  existing default datasets and reconciliation behavior. No deployment or accounting sign-off.

## Contract records and combined-template modifications — October 20, 2026

- Both ordinary and membership variance replay now introduce retained contract-record changes
  in the reference phase before business application events. Membership uses original member
  records first. Unique contract identities, transaction currency, contracting entity and inception
  must remain fixed; changing these requires an explicit basis migration instead of attribution.
- The real-engine merge + delivery + approved legacy prospective amendment witness uncovered an
  engine defect: the single-member template total was compared to whole-group TP. Templates now
  include unchanged members in the group check and preserve those members' posted allocations,
  assigning only the residual fixed-basis budget to the amended member. Final group checks remain.
- Necessary verification covers real monetary amendment effects, ordinary replay, isolated merge
  invariance, unapplied-record zero effect, late application provenance and unchanged other-member
  allocations/revenue/RPO (group balance attribution may change). Existing prospective/retrospective/POB-VC cases and basis-migration refusal checks
  pass; lint/types checked. This supersedes the blanket contract-record refusal below.
- Still open: missing member sources, incompatible earlier bases, group-level posted redistribution,
  combined/late-carried liability FX and alternate-currency frozen close integration. Broader release
  acceptance remains outstanding; no deployment or independent accounting sign-off claimed.

## Estimate versions in membership replay — October 20, 2026

- Group changes can now coexist with new approved estimate versions. The membership phase
  reconstructs the earlier contract/portfolio-owned estimate set; the reference phase introduces
  later versions before their ordered business application events. Original versions must remain
  unchanged and retained, and duplicate identities with different contents are refused.
- A real-engine/frozen-data witness combines merge, delivery and an added VC version/application
  event. Membership effects equal the isolated merge; introducing an unapplied version has zero
  effect; the dated application contributes the independently projected change under LATE_EVENT.
  The actual VC amount changes, all sums reconcile and application keys remain in the evidence.
- Necessary grouped journey also covers reverse split, RPO policy changes, conflicting policies,
  report/cell provenance and exports. Lint/types checked. This supersedes the blanket estimate-
  record refusal below; contract-header changes and incompatible earlier bases remain separate.
- Remaining: contract-header replay, missing member sources, group-level posting redistribution,
  combined/late-carried liability FX and alternate-currency frozen close integration. No deployment
  or independent accounting sign-off claimed.

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
