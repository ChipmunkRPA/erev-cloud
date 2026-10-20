# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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

## Isolated group-membership variance replay — October 20, 2026

- Close variance now detects connected group reorganizations and can attribute pure merge/split
  changes as MODIFICATION with explicit group.membership evidence. It verifies every original
  output/frozen endpoint, checks earlier groups at the later cutoff, and replays the new partition
  on the earlier contract-qualified posting basis before accepting the difference.
- Business events, contract terms, policy/reference changes and missing population sources are
  checked separately. Unchanged unions cannot hide a member's different group-policy basis.
  New bundle fields require an explicit comparison rule. Group-level posted amounts still need
  a redistribution basis; they are not reassigned by weight or replaced with empty computations.
- Per-contract execution aliases preserve distinct earlier/later computation and group identities.
  Report rows and cell contributors verify those identities against the authorized frozen sources;
  existing one-group and whole-population entry/exit evidence remains compatible.
- Necessary real-engine/frozen-CSV witness covers two differently priced contracts merging,
  reverse split, exact redistribution, presentation and cell sums/provenance. A simultaneous
  delivery is refused as a mixed change. Existing grouped replay/population/export checks pass;
  lint/types pass. This witness is not a full production close/lock workflow.
- Still open: simultaneous membership/business/reference replay, members entering/leaving a
  surviving group without a prior source, group-level posted redistribution, combined-contract
  FX ownership and late-carried FX. No deployment or accounting sign-off claimed.

## Layer-specific liability FX attribution — October 20, 2026

- Functional balance rollforwards now retain new billing layer identities and read verified
  liability creation/remeasurement movements. Period totals must equal posted control FX;
  missing layers, inconsistent traces/currencies or mismatched totals are refused explicitly.
- Opening layers retain their original range-opening classification; new layers remain separate.
  Revenue-relief FX precedes revenue and closing FX follows it. Billing settlement FX also carries
  its source layer identity. No functional-balance-weight apportionment is used. Source movement
  membership is retained for reruns; existing transaction paths and locked schemas are unchanged.
- Necessary real API witness: approved POL-163 override, one opening advance plus two new advances,
  monthly close FX, then delivery and a new close pass. Closing GBP 94,600 becomes GBP 55,900;
  revenue from opening is GBP 37,575, and balance ties pass. The pre-delivery report reruns unchanged.
  FIFO layer unit checks and ERP/ENGINE functional-invoice regressions pass; lint/types checked.
- This supersedes the blanket multi-open-layer FX refusal for attributable movements. Combined
  contract layer ownership and late-carried FX that cannot match dated movement evidence remain
  separate work, along with group-membership variance attribution and broader release acceptance.
  No deployment or independent accounting sign-off claimed.

## RPO rollforward currency attribution — October 20, 2026

- Functional/reporting RPO rollforwards now translate month-by-month: business movements at
  monthly average rates and opening/closing disclosures at their own closing rates. Endpoints
  use the same per-obligation gross/exclusion projection as RPO, so partial-exemption rounding
  does not create mismatched closing totals. Approved rate identities are retained for reruns.
- FX is calculated independently from opening/closing exposures and rate differences; currency
  rounding has its own line. Source UNEXPLAINED remains separate, and any nonzero source monthly
  unexplained amount forces a failed balance tie even if display rounding could erase it.
- Necessary API witness covers three months of GBP/USD revenue and FX, both endpoint disclosure
  ties, a revised closing-rate set versus retained rerun, and injected unsupported movement that
  still fails the tie without changing FX. Existing transaction CTL-030 passes; lint/types pass.
- This completes the current RPO live-report currency path, not every reporting feature or
  alternate currency lock datasets. Multi-layer liability FX, group membership/combined-contract
  attribution and broader release acceptance remain outstanding. No deployment or accounting
  sign-off claimed.

## RPO disclosure currency views — October 20, 2026

- RPO now translates foreign transaction consideration to functional currency and then to
  reporting currency using retained approved as-of closing rates. The former foreign-currency
  refusal and reporting-as-functional shortcut are removed for the RPO disclosure report.
- Gross RPO and exclusion are translated first; net disclosure is their difference. Largest
  remainder allocation distributes net rounding through bands and contributors, preserving
  total = current + noncurrent = sum(bands) = sum(contributors), including partial exemptions.
  The source store remains untouched and the independent rollforward tie explicitly stays in
  transaction currency. Headers/control evidence/cell details state the as-of translation basis.
- Necessary checks: GBP disclosures translated to USD, currency-band/current conservation,
  converted cell contributors, published closing-rate revision versus retained rerun, POL-197
  excluded totals, and a foreign-functional partial-exemption cent-rounding witness. Existing
  approved targeted-VC journey and snapshot producer remain valid. Lint/types checked.
- RPO rollforward multi-currency movement/FX attribution is still outstanding, as are the other
  documented multi-layer FX and group-change attribution gaps. Existing locked datasets remain
  transaction currency. No deployment or independent accounting sign-off claimed.

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
