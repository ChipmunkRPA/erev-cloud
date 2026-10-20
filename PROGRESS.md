# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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

## Revenue waterfall currency views — October 20, 2026

- Removed the foreign-contract refusal and the reporting-as-functional shortcut. Recognized
  revenue uses posted functional amounts; reporting translates each contributing revenue line
  using its posting period's approved average rate, preserving independent functional JE ties.
- Scheduled and awaiting-trigger amounts are explicitly forecast translations at the as-of
  period closing rate (transaction to functional, then functional to reporting). They do not
  restate historical revenue or value deferred-revenue layers. Rates/version IDs and rounding
  inputs are retained; future average rates are not required. Headers and cell details identify
  the forecast basis, and displayed cell contributions sum to converted totals.
- Necessary API checks cover EUR actual revenue, functional JE agreement, revised reporting
  average rates versus retained reruns, GBP future schedules performed by a USD entity,
  awaiting-trigger translation, and cell contributors. Existing cross-entity transaction
  waterfall and row-identity checks pass; Python lint/types pass. No deployment.
- RPO currency views, multi-layer FX attribution, combined-contract/group membership replay
  and independent accounting acceptance remain outstanding. Locked snapshots retain their
  existing transaction-currency schema; this change does not add alternate lock-dataset views.

## Revenue disaggregation currency views — October 20, 2026

- Fixed currency_view being ignored by revenue disaggregation. Functional view now reads posted
  functional amounts; reporting view translates each posted functional revenue line at its own
  posting period's approved average rate. Display totals sum the rounded line contributions.
- Rates/version IDs are retained per entity/period; locked endpoints use frozen rate cutoffs.
  Reporting journal tie-outs explicitly compare functional subledger and journal amounts before
  translation. The general journal-revenue reader now supports functional amounts without
  changing its default transaction behavior or retained run-membership rules.
- Targeted API journey: EUR 10,000 transaction revenue is USD 11,000 functional revenue; changing
  the reporting average to 0.8 yields EUR 8,800 in a fresh report while the original rerun keeps
  EUR 10,000. Functional journal tie passes. Existing transaction disaggregation control passes;
  Python lint/types pass. No deployment.
- Revenue waterfall and RPO currency coverage remain separate unfinished work, along with the
  previously documented multi-layer FX, combined-contract and difference-attribution gaps.

## Targeted VC evidence through the platform — October 20, 2026

- Fixed a missing production adapter path: the estimate element's allocation-criteria evidence
  now enters the engine input during previews and computations. Editable version parameters
  cannot replace or invent that evidence. The engine's existing POL-044 control is unchanged.
- RPO later-share eligibility now reads the element's evidence alongside the named version,
  rather than looking in version parameters where the product never saved that field.
- Positive API journey approves two targeted bonus versions, computes each, then verifies fixed
  consideration USD 132,000 remains disclosed while USD 20,000 is excluded. The witness uses the
  explicitly published tenant POL-044 NOT_ENFORCED election, with reviewed constraint evidence.
- Net time-band/cell contributors, snapshot producer rows and control totals, CSV export and
  retained rerun agree. A partially exempt obligation freezes as one section-1 row carrying both
  its net amount and exclusion metadata. Adapter checks also reject version-parameter overrides.
- This closes the populated partial-exemption report/snapshot-producer/export gap for this path;
  it does not assert a complete production lock workflow or all exemption combinations. Broader
  revenue/RPO currency views and the other documented reporting gaps remain. No deployment.

## RPO original-duration exemption — October 20, 2026

- POL-197 now uses original inception segments from verified retained computation inputs,
  matching the engine's inclusive service-date boundary (end before the first anniversary).
  Contract extensions and shortening no longer change the original-duration qualification.
- RPO, RPO rollforward, dashboard and close-variance projection share this basis. Reports show
  the original inception/end dates in the exemption detail and retain terms per source version
  for same-source reruns and cell explanations. Current templates/events never replace the input.
- Report jobs resolve the actual requester's source permissions; dashboard uses contract.read.
  Close snapshots use their explicit internal read-only SYSTEM path. Source integrity checks
  remain the same. No engine output or posting behavior is changed.
- Real-engine witnesses cover short-contract extension, long-contract shortening and the exact
  anniversary boundary; the existing partial-VC cases still pass. The API journey checks original
  dates, Home totals, cell explanation, retained rerun and read-only SYSTEM snapshot totals.
  Existing RPO rollforward and Python lint/types pass. Remaining RPO work includes
  broader positive partial-exemption lock/export acceptance and multi-currency reporting.
- Retained reports predating original-term evidence cannot silently reconstruct it from current
  data. Missing retained input/terms is refused; create a fresh report after source availability.
  No deployment; the four priority workstreams are not yet all complete.

## Reporting-currency contract balance rollforward — October 20, 2026

- Reporting view now uses the engine's S12-R-18 translation: preceding closing rate for opening,
  each posting period's average rate for movements, closing rate for closing. TRANSLATION and
  ROUNDING are explicit aggregate and by-contract lines, separate from FX_REMEASUREMENT.
- Intermediate functional endpoints and cumulative path deltas retain the original range's
  opening-liability identity across months. Rate/version facts are pinned per entity, period and
  type; locked endpoints use frozen cutoffs. Balance and GL comparisons remain functional.
- Unexplained functional OTHER fails the movement tie even if translation rounds it to zero.
  Missing flow periods or required rates are refused; no current-rate substitution on reruns.
- Targeted two-month API journey: EUR 10,000 closing, translated functional FX 180.59 and separate
  translation -180.59. Publishing a new closing rate changes a fresh run to EUR 8,960 while the
  original rerun retains its rows. Range-opening versus new-billing attribution is checked.
  Locked-period reporting and the existing balance translation journey also pass; lint/types pass.
- Remaining: broader reporting-currency coverage (including revenue/RPO), multi-layer monetary
  liability FX and combined-contract attribution; the other priority workstream gaps remain as
  previously stated. No deployment; this does not close the entire four-workstream request.

## Reporting-currency contract balances — October 20, 2026

- Contract balances now translates dated functional balances into the tenant reporting currency
  using approved closing rates. Rows show functional currency and the closing rate; totals sum
  rounded contract rows. Currency precision uses exact rational half-up rounding.
- Rate amounts, row/version IDs and cutoffs are retained for reruns. Locked endpoints select rates
  at their frozen cutoff. Missing or ambiguous rates are refused; no runtime rate inversion or
  triangulation is performed. Balance and GL comparisons remain explicitly functional.
- Targeted API journey verifies USD 11,050 becomes EUR 9,945.01 at 0.900001; after publishing
  0.8, a new report shows EUR 8,840 and the retained rerun reproduces the earlier rows.
  Locked-period identity translation/rerun also passes; Python lint and types pass.
- Remaining: reporting-currency movement reports need opening/flow/closing rate treatment and
  explicit translation differences; broader report coverage, multi-layer FX and combined-contract
  attribution remain open. This is an incremental feature completion, not four-workstream closure.

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
