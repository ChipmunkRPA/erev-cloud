# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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

## Reference/policy phases with group changes — October 20, 2026

- Membership replay now reconstructs prior member policies for the new group, carrying only
  member-owned contract/obligation/contract-period policies and remapping group ownership.
  Shared prior policies and reference bases must agree; conflicts cannot silently become the
  baseline. Unknown policy scopes require an explicit ownership rule.
- The next OTHER phase applies later SSP/template/rule references and resolved policies together,
  before business events and FX. Execution hashes and changed-field names retain the basis of
  this attribution. Contract headers and estimate records still require separate handling.
- Necessary real-engine/frozen-data witness covers merge + RPO original-duration exemption
  election + late delivery, independently reconciles all three effects, and checks report/cell
  amounts and source details. Conflicting earlier policy bases are rejected. Existing reverse
  split and functional FX checks remain included. No deployment or accounting sign-off claimed.
- Remaining: contract/estimate record replay, incompatible earlier reference/policy bases,
  missing member sources, group-level posting redistribution, combined/late-carried liability
  FX, and alternate-currency locked datasets/close-report integration.

## FX after membership/event variance replay — October 20, 2026

- Reorganized groups now replay membership and business events on the coherent earlier FX
  basis, then apply the later source rates in a separate FX phase. Rates no longer have to
  remain identical across the two closes. Inconsistent earlier-group rate bases are refused
  explicitly rather than choosing one member's rates. Final frozen endpoint checks remain.
- The retained membership worker accepts an explicit transaction/functional projection, used
  consistently for original-source verification and every intermediate phase. Actual source
  and counterfactual hashes remain separate. Existing frozen CSV currency schemas are unchanged.
- Necessary real-engine witness merges two EUR contracts of a USD entity and revises rates:
  each contract's functional revenue increases by USD 60 under FX. Membership and FX effects
  independently equal their projected endpoint differences. Existing grouped replay, reverse
  split, mixed delivery, report/cell and export journey also passes; lint/types pass.
- Still open: alternate-currency frozen datasets and close-report integration; mixed contract/
  estimate/reference changes; missing members; group-level posting redistribution; combined
  contract/late-carried liability FX. No deployment or accounting sign-off claimed.

## Membership plus business-event variance replay — October 20, 2026

- Group merges/splits can now coexist with newly recorded business events. The replay first
  evaluates the new partition without those business events, then adds consecutive event-driver
  runs in effective-date/sequence order. Late-event precedence remains explicit. Each phase
  retains its input/output hashes and source event keys; final metrics must match frozen values.
- The targeted real-engine witness now combines a nonzero merge redistribution with a late
  delivery. Membership effects equal the isolated merge; delivery effects equal an independent
  before/after engine projection. Report/cell amounts and retained source identities reconcile.
  Existing reverse split, population and export checks in the same journey pass; lint/types pass.
- This supersedes the simultaneous-business-event refusal below. Mixed contract/estimate record,
  policy/reference or FX changes, missing member sources, group-level posted redistribution,
  combined-contract FX ownership and late-carried FX remain open. This is authored frozen-data
  validation, not full lock-flow acceptance. No deployment or accounting sign-off claimed.

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
