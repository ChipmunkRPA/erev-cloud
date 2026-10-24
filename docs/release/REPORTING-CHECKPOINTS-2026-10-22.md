# Archived Reporting checkpoints — October 22, 2026

## Foreign locked-group reporting and original posted ownership — October 23, 2026

- Fixed a public Reporting failure after separately computed foreign contracts are combined.
  The latest group computation can redistribute historical layer ownership while original
  posted revenue still names its original sources. Previously an exact ownership comparison
  rejected these otherwise reconciled reports.
- New reports retain both posted and target ownership. Original posted evidence and authenticated
  layer creation dates determine opening-revenue attribution; target ownership still determines
  the member balance reclassification. The two relief totals must match exactly. The retained
  alignment makes their zero-sum ownership differences explicit without inventing new revenue.
  Older bound reports retain their original method; new bound reruns validate the saved alignment.
- Populated EUR-to-USD workflow: separate contracts, September lock, October deliveries and
  combination. Native frozen opening is EUR 34,000 / USD 37,400 with both original versions.
  Public functional revenue/relief is USD 15,400; EUR reporting opening is 33,392.86 at the
  September closing rate, and revenue/relief is 13,873.87 at the October average rate. Both saved
  public reports replay identically, including the retained ownership alignment.
- Four targeted populated workflows pass across the final runs: foreign locked-group reporting,
  cross-member revenue/returns, exhaustion into an asset, and settlement of another member asset.
  Scoped types/lint pass. An obsolete test expectation was corrected to select the revenue
  population from the complete saved control evidence, matching the existing reader.
- No posting algorithm change or deployment. Partial old-group splits, special/acquired sources
  and other documented implementation gaps remain open; this is not overall release completion.

## Post-lock new contract joining a frozen group — October 23, 2026

- A genuinely new contract can join a complete historical group while retaining the old group's
  frozen native opening. The original locked group proof remains intact and explicitly lists
  the new contracts with proven zero opening; no historical amount is apportioned to them.
- Proof requires inception and every retained event after the opening date, exactly one booking,
  absence from locked balances, and no imported/acquired OPENING_BALANCE_ESTABLISHED event.
  The engine independently checks retained headers/events and refuses existing obligation
  openings before supplying zero eligibility for new-contract obligations.
- Historical membership matching now uses canonical encoded contract keys, including slash and
  percent characters. Missing, overlapping and partial original groups still do not receive
  inferred historical openings.
- Validation: nine focused source/proof cases and 17 native rollforward cases pass. Populated
  public workflows for both two old groups and an old group plus a newly booked contract pass,
  retaining FROZEN openings and explicit original/zero sources. Scoped types/lint pass.
- Partial old-group splits, special/acquired original sources, broader foreign lock histories
  and the other development scope remain open. No deployment or posting algorithm change.

## Whole-group union of frozen native openings — October 23, 2026

- After complete original contract groups are combined, the next native rollforward can use
  the sum of their authenticated locked closings. Original obligation eligibility remains
  separate from group balances; no member/layer allocation is invented.
- Read every original member source, deduplicate original versions, and require complete,
  disjoint coverage in each currency view. Check each transaction group against its own locked
  member totals, so offsetting errors cannot pass an aggregate reconciliation.
- Multiple original versions retain a deterministic full source set and its digest; the set
  digest is never presented as an original output-file hash. Single-group proof stays unchanged.
  Engine handoff validates the source set and retains it in saved native output.
- Validation: focused union and native/codec checks pass, plus a populated product workflow
  that computes two contracts separately, closes/locks September, combines them in October,
  and saves FROZEN openings with both original versions. Scoped lint/types pass.
- Still open: partial historical-group splits, broader foreign-currency lock histories and
  special/acquired opening sources. This change does not claim those populations complete.
  Posting calculation remains unchanged; no deployment.

## Automatic frozen native opening handoff — October 23, 2026

- Computation and preview paths attach available authenticated prior-lock native snapshots to
  a typed disclosure_openings input. The loader reads the original lock/version/output under
  the computation's group scope, checks unchanged group/member coverage and transaction closing
  totals, and retains original lock/version/output/binding hashes. Saved inputs replay directly.
- Stage 15 applies matching book/entity/period/view openings and records FROZEN plus their source
  proof in saved native outputs. Group balances and original obligation eligibility remain
  distinct; posting targets are unchanged. Explicit post-opening ADD events can prove zero
  opening for new obligations; missing ownership proof is refused, not manufactured.
- The optional input/output fields are omitted for old evidence, preserving earlier hashes.
  Previews use the same preparation as actual computation. Existing records without a complete
  matching native snapshot keep their existing RESTATED native path; public report historical
  source recovery remains available separately.
- Necessary validation: 25 codec/upgrade cases, 17 focused native/handoff cases, functional and
  reporting public locked-opening workflows, and a modification preview/approval workflow pass.
  Saved next-period outputs point to the original locked version; source-bound report reruns
  remain identical. Scoped lint/types pass. No deployment or journal calculation changes.
- Remaining scope includes changed combination membership across the lock, broader combined
  foreign lock histories, and unavailable special-contract/acquired sources. These are not
  claimed complete by the unchanged-group workflow above.

## BBR reporting currency — October 22, 2026

- Reporting view now values all four measures at retained entity-period average rates after
  original functional valuation. Signed source pennies match period totals; journal comparison
  uses the same aggregation basis. Cells disclose rates and original functional amounts.
- Migration 0334 records scope. Eleven BBR unit cases and a populated USD/GBP public report,
  cell and retained-rerun workflow pass, with scoped lint/types and metadata parity. No deployment.

## Waterfall calendar columns — October 22, 2026

- New runs align whole reporting intervals by actual dates and retain entity-local period
  mappings. Same dates combine; differing boundaries remain separate labelled columns, with
  matching cell sources. Matching layouts and older saved runs preserve their prior shape.
- Migration 0333 pins IPE metadata. Necessary validation: 14 waterfall unit cases, populated
  report/retained-rerun workflow, date-label frontend case, scoped lint/types and metadata parity.
  No partial-period allocation or change to native amounts; no deployment.


## Modification amount source drill — October 22, 2026

- Money cells rebuild saved inputs and link original native trace nodes. Analytical equivalents
  show pinned spot/average rates separately. Retained UUIDs resolve source visibility only;
  old runs without identity, missing cells and scope changes refuse. Internal-link filtering
  rejects external/API destinations. Migration 0332 freezes IPE metadata.
- Necessary checks: 22 register and eight catalogue cases, populated K02 source/component/
  catch-up/spot/reporting drills and refusals, four frontend cases, scoped lint/types and
  metadata parity. No deployment; per-event functional posting ownership remains open.

## Optional per-event close variance — October 22, 2026

- Added Attribution detail: By driver (default) / By event. Detailed mode executes each business
  event in ENG-06 order, retaining individual signed changes and execution hashes. Driver totals
  and frozen monetary endpoints still reconcile; reference/FX and membership/population phases
  remain explicit. No proportional split or journal-posting ownership is claimed.
- Ordinary and membership replay share the detailed-boundary implementation. A retained choice
  is checked at prepare/rebuild and contributor reads; old/default runs keep grouped behavior.
  Migration 0331 freezes schema/IPE metadata; the existing toolbar exposes labelled choices.
- Necessary verification: 46 replay/catalogue cases, plus two new native net-zero modification
  variants (USD and GBP), eight toolbar cases, and the event-mode worker/bound-rerun workflow
  with real empty lock snapshots. Native positive/negative effects are checked against grouped
  totals; membership functional endpoints also match. Scoped lint/types and metadata parity pass.
- Original per-event journal ownership in the modification register remains open. This completes
  a user-selectable causal replay capability, not that separate feature. No deployment.

## GL automatic certification — October 23, 2026

- Attached GL comparisons now use published kind-specific rules for automatic certification.
  Only complete, nonempty zero-variance comparisons qualify; no policy is created automatically.
  Write-once rule IDs, CTL-025/026 and audit evidence retain the decision (migration 0337).
- Two populated GL/billing workflows and transition parity checks pass; scoped lint/types pass.
  See CURRENT-DEVELOPMENT-SCOPE.md. No deployment.

## Secondary-book late-event reporting — October 23, 2026

- New computations record late-event evidence separately for each enabled entity book, with
  that book's posting period. The register reads secondary identities without duplicating the
  primary row; historical evidence and saved reports stay unchanged (migration 0338).
- Two producer cases, the extended K07 report workflow and eight catalogue cases pass;
  metadata equality and scoped lint/types pass. Scope and test boundaries are recorded in
  CURRENT-DEVELOPMENT-SCOPE.md. No deployment.

## Cross-calendar revenue disaggregation — October 23, 2026

- New runs combine only identical actual date intervals, with separate columns for different
  periods and retained entity/local-period mappings. Same-calendar labels and legacy bindings
  keep their existing interpretation. No partial-period reallocation (migration 0339).
- Populated mixed-calendar totals and saved reruns, existing journal tie-out and currency
  workflows, two interval-layout cases and scoped lint/types pass. See CURRENT-DEVELOPMENT-SCOPE.
- Earlier GL checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md. No deployment.

## Cross-calendar waterfall selections — October 23, 2026

- Explicit fiscal-key ranges now reach the existing date-aligned waterfall implementation.
  Each entity's local intervals and contributor sources stay distinct; month/quarter/year
  totals and retained reruns match separate entity reports. Other report guards remain.
- Three populated API/cell/rerun workflows and the remaining guard check pass; existing
  date-bucket unit cases and scoped lint/types pass. See CURRENT-DEVELOPMENT-SCOPE.
- Earlier late-event checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md. No deployment.

## Original forecast report re-export — October 23, 2026

- Original forecast reports now accept the rerun API, binding the verified saved publication
  through the catalogue adapter without recomputing the forecast. Existing UI flow is unchanged.
- Populated forecast lifecycle passes: JSON/CSV/XLSX original and catalogue reruns preserve
  dataset hashes and bound sources; source-access checks remain. Scoped lint/types pass.

## VC / royalty close assessment controls — October 23, 2026

- Final close passes now persist native reassessment/accrual gaps as blocking exceptions with
  book/period scope and input hashes. Successful rechecks settle only superseded findings;
  no extra engine pass or approval workflow. Existing engine coverage limits remain explicit.
- Normal close and injected-gap lifecycle workflows pass, including cross-book gate isolation
  and settlement; two native gap cases and scoped lint/types pass. See CURRENT-DEVELOPMENT-SCOPE.
- UI follow-through: VC counts/links use the same book-specific blocking scope; element banners
  recognize generated findings and retain in-progress items; royalty titles are readable.
  Extended backend lifecycle and two focused UI cases pass, with frontend types/lint.
- Earlier disaggregation checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md. No deployment.

## Publication checks and backlog audit — October 23, 2026

- On 47db35bf: secrets scan 4,183 files / nine allow-lists / zero findings; runtime licence
  check 142 packages / eight allow-lists / zero findings. Research directories remain untracked;
  PolyForm Noncommercial remains intact. No deployment.
- Confirmed existing unassigned-approval alerts and warning UI; historical C-6 is superseded by
  the October 7 B1-15 completion. B2-2/C-7 was reproduced and repaired below.
- Earlier waterfall checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md.

## Privacy field catalogue — October 23, 2026

- Reconciled all 11 missing columns: historical commit identity/timing evidence and modification
  termination terms, with matching data-model declarations. All 12 catalogue checks pass.
- Export permissions and retention execution are unchanged. The separate revision-0166 schema
  parser issue remains open. This supersedes the privacy omission in the preceding checkpoint.

## Migration/schema verification — October 23, 2026

- Fixed multiline constraint and quoted-comma parsing; full migration-chain comparison now runs.
  Corrected document-only primary-key/default/header omissions; no runtime schema change.
- Ten architecture and twelve privacy checks pass, including mismatch-detection witnesses.
  Supersedes the previous parser gap. Release-candidate verification remains outstanding.
- Publication audit checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md.

## Modification causal reporting — October 22, 2026

- Owner-selected sequential causal analysis is now exposed in the modification register.
  Baseline, selected/other event effects and final period revenue reconcile in transaction,
  functional and reporting views. Cells retain execution evidence; saved reruns preserve results.
- Migration 0335; nine native causal cases, 40 existing replay cases, two populated public
  workflows and ten frontend cases pass, with scoped lint/types. No posting-rule change or deployment.
- BBR reporting currency (0334) and waterfall calendar columns (0333) checkpoints moved to
  REPORTING-CHECKPOINTS-2026-10-22.md; current scope remains in CURRENT-DEVELOPMENT-SCOPE.

## Close-variance offsetting effects — October 22, 2026

- Retain contract rows whose nonzero replay effects offset to zero, including repeated runs
  of one driver. Retain driver summary rows when opposing contract contributions net to zero.
  Unchanged replays still render empty; section totals remain the original net amounts.
- Drill evidence includes signed intermediate effects and event references. The cell reader
  checks each retained effect population against its contract/driver amount before displaying it;
  original source/hash/entity checks remain. New bindings pin offset details; older bound runs
  preserve their original row population and evidence without the additive details works.
- Migration 0330 documents the presentation scope. Necessary checks cover native replay/export
  compatibility, authored offset witnesses, contributor reads, corrupt effects, catalogue parity
  and scoped types/lint. No engine calculation, event grouping or deployment changed.
- Individual amounts within a consecutive same-driver event run remain an implementation gap.

## Modification functional calculation evidence — October 22, 2026

- New register runs expose original functional catch-up calculations and period/basis when a
  single event explains the full native period flow. Historical FX pieces and both currency
  totals are verified; trace hashes/node identities and resolved values remain in retained inputs.
- Columns distinguish native calculation from spot equivalents and journal posting deltas.
  Mixed/missing evidence stays empty; older bound runs keep their columns. Migration 0329
  records the scope. No native monetary calculation or deployment changed.
- Necessary checks: 36 focused reader/register/catalogue cases, native USD/GBP positive and
  negative catch-ups, mixed-period and corrupt-source refusals; existing populated register,
  approved-rate and mixed-period API workflows, plus retained reconstruction and scoped lint/types.
- Multi-event functional allocation and actual per-event posted deltas remain open; this is
  incremental calculation evidence, not completion of that larger feature.


## Portfolio storage foundation — October 23, 2026

- Revision 0341 adds named portfolios and retained member intervals, tenant foreign keys,
  overlap prevention, once-only closure and populated-downgrade protection.
- Snapshot datasets include both tables and references; record cutoffs omit future closure.
  Schema/privacy, dataset and focused database checks cover this foundation.
- Shared estimates are NOT complete: commands/UI, approval fan-out, member calculations,
  reporting and populated restore remain. Engine portfolio returns can be reused; breakage
  still selects contract-only estimates. Two estimation choices await the owner's response.


## Material-right product defaults — October 23, 2026

- POL-026 now initializes option entry from resolved product policy, using retained pins
  when present. API omission resolves the common book default; explicit methods win.
  Conflicting defaults require a choice. Saved immutable terms govern later calculations.
- Public entry/rollback/activation and two explicit discount workflows pass; two resolution
  and 18 UI cases pass, with scoped lint/types and regenerated API types. No deployment.
- Remaining policy implementation: portfolio estimates (POL-015) and lessor combination
  (POL-231). This supersedes POL-026 in the preceding reader audit.


## Portfolio management — October 23, 2026

- Added public portfolio/member commands and Settings → Reference data → Portfolios.
  Create/edit, search/add, reasoned exit and retained history are available with pagination.
- Parent ETags, audit facts and contract/entity permissions protect writes; reads/counts omit
  hidden members. Stale metadata edits stay visible until the user explicitly reloads.
- Populated API workflow, four UI cases, 24 route checks and scoped lint/types pass; existing
  computation head is unchanged. Shared estimate application remains.
- Actual copy and LATEST refresh jobs now preserve populated member history; a successor
  sandbox membership edit leaves production unchanged. The focused database workflow passes.
  Two previously asked estimation choices still await the owner. No deployment.


## Shared-estimate definitions — October 23, 2026

- Portfolio page/API can create and list RETURN_RATE/BREAKAGE definitions with an explicit
  method, parent-version protection and audit facts. Full retained-member read/write scope
  protects shared evidence, including after all current members leave.
- Populated API workflow and five UI cases plus scoped lint/types pass. Definition authoring
  is available; values, approval, calculation application and reporting are still pending.
  The UI states this boundary. No estimation-choice assumptions and no deployment.

## Shared-estimate draft versions — October 23, 2026

- Added explicit-currency numerical drafts, version history, full edits and retained discard
  in the portfolio API/page. Required return parameters, existing method/amount validation,
  decimal strings and full historical-member permissions are preserved.
- Parent/version ETags and explicit version increments prevent stale overwrites; one open
  version per element, retained VOIDED rows and monotonic version numbers are verified.
- Populated API and existing contract constraint workflows, six UI cases and scoped lint/types
  pass; the computation head is unchanged. Approval/application/reporting remain pending,
  with the two owner estimation choices still open. No deployment.

## Shared-estimate supporting evidence — October 23, 2026

- Added upload/attach, download and uploader-only reasoned void on saved portfolio drafts.
  Failed attachment retry reuses the uploaded file and command key.
- Reproduced and repaired the attachment registry's tenant-level fallback for shared versions:
  current/former member scope now guards list/content/attach and file reference resolution.
- Populated API, seven registry and seven UI cases plus scoped lint/types pass. Approval,
  calculation and Reporting integration remain; two calculation choices await the owner.
  No deployment.

## Shared-estimate audit history — October 23, 2026

- Definitions and draft version changes now identify their audited object; versions retain
  before/after values and row version. Current/former member contracts are frozen into each
  event for contract audit trails. Portfolio audit types and metadata labels are registered.
- Scoped writer scan, lint and types pass; populated workflow checks version evidence.
  Full audit architecture scan still reports 29 pre-existing findings in forecast,
  release-validation and sandbox dispatch. Track these separately; no full-suite claim.
- Shared approval/application still await the two calculation choices. No deployment.

## Lessor combination initial computation — October 23, 2026

- POL-231 now combines reviewed eligible components at inception, retains their prices and
  membership, and routes by assessed predominance. Reads the associated lease product policy;
  IFRS, unelected and ineligible cases stay separate. Strict assessment fields use OTHER.
- Twelve targeted cases (including two full-engine paths), eight existing election cases and
  scoped lint/types pass. UI, populated approval, modification/variable-payment integration
  and Reporting remain open; see CURRENT-DEVELOPMENT-SCOPE.md. No deployment.

## Combined lessor scope Reporting — October 23, 2026

- Scope exclusions now show retained original components and exact reviewed assessments/
  rationales, with the combined amount counted once. Saved reruns retain these fields;
  older traces without structured membership explicitly state that limitation.
- Populated approval-to-report workflow exposed/fixed the standalone lease amount surviving
  combination: 108,000 now routes out as 108,000, not its former 81,000 lease-only memo.
- Combined report/rerun, existing scope workflow and 39 engine/register checks pass; production
  lint/types pass. UI, modification/variable-payment and in-scope visibility remain open.
  No deployment; see CURRENT-DEVELOPMENT-SCOPE.md for scope.

## Combined usage persistence — October 23, 2026

- Original lease/service usage fees now verified through public event submission, independent
  approval, persisted computation and scope-report jobs: 108,000 + 300 = 108,300, zero 606
  revenue/RPO, identical saved rerun. Existing activation fixture is reused.
- RTI, other payment measures, modifications and in-scope combined visibility remain open;
  see CURRENT-DEVELOPMENT-SCOPE. No deployment.

## Combined right-to-invoice — October 23, 2026

- Original components retain their own usage/delivery/invoice source priority and rates;
  shared events count once. Billing and tax attribution resolve original members to the host.
- Fixed/excess consideration follows the reviewed 606/842 routing; all-member pricing guards
  apply. Corrected duplicate tax deduction from already-net invoice amounts.
- 38 focused cases and scoped lint/types pass. Other measures, modifications and in-scope
  combination visibility remain open. No deployment.

## Combined components in latest status — October 23, 2026

- Latest contract status now shows original members, reviewed rationale and scope alongside
  the combined amount, including in-scope service-predominant combinations. Saved evidence
  reruns identically; ordinary and older saved reports retain their column shape.
- Two populated workflows and 28 unit cases pass; scoped production lint/types pass.
  Other measures and modifications remain open. No deployment. See CURRENT-DEVELOPMENT-SCOPE.

## Combined component price modifications — October 23, 2026

- Original-member price changes now reach the combined obligation; conflicting instructions
  are refused. Remaining SSP includes every original product, and lease scope totals update.
- 46 targeted engine cases and scoped types/lint pass. Quantity/term reassessment, mixed SSP
  bases and public modification/Reporting workflow remain open. No deployment.

## Combined price-change public flow — October 23, 2026

- Original-member changes now verified through public classification, preview, independent
  approval, persisted calculation and saved Reporting: 108,000 becomes 109,000.
- Classification now displays the selected SSP default for proposed combined hosts too.
  Authored overrides are preserved. The wizard still lacks original-component selection;
  this is the next UI gap. No deployment. See CURRENT-DEVELOPMENT-SCOPE.

## Original component selection — October 23, 2026

- The modification wizard now offers original combined components for price changes, from
  retained calculation membership. It preserves the original key and labels the combined host.
- Other changes and duplicate additions using those keys are refused in the form. API workflow,
  UI submission, parser/model cases, TypeScript and scoped Python types/lint pass. No deployment.

## Mixed component SSP bases — October 23, 2026

- Combined price changes now calculate each original series component using its own SSP basis
  and quantity unit before summing remaining weights. Trace parameters preserve each calculation.
- 42 native cases and scoped lint/types pass. Public classification, preview, approval and saved
  Reporting now pass for mixed bases, including retained trace reevaluation. Quantity/removal/term
  reassessment and final publication checks remain open. No deployment.

## Forecast contract audit linkage — October 23, 2026

- Forecast input-set creation/update/publication and replay now freeze affected contract keys
  from captured commands and applied imports, making them available in contract audit history.
- Populated import/replay workflow, all three audit-writer architecture checks and scoped
  lint/types pass. Prior mixed-SSP checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md.

## Filtered audit export — October 23, 2026

- The Audit log page now exports selected contract trails and outcome filters using the existing
  report backend. Contract lookup must succeed before exporting; the scope cannot widen silently.
- Two targeted UI cases, TypeScript and scoped ESLint pass. Updated the user guide. Forecast
  audit checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md. No deployment.

## Combined component delivery recognition — October 23, 2026

- Combined delivery/time-of-transfer measures now count original component deliveries and returns
  once, applying the original member's acceptance/repurchase/bill-and-hold controls.
- 15 native cases and public original-component delivery/return approval and Reporting pass. The
  event drawer now exposes original members; two UI cases and scoped types/lint pass. Remaining
  combined reassessment/measures stay open. No deployment.

## Opening-liability policy evidence — October 23, 2026

- New disclosures retain resolved consumption policies by entity/book, so rerun explanations do
  not read current policy. Three currency-view cases, the public K01 report and lint/types pass.
- Confirmed remaining gap: FIFO_WITHIN_POB exists in native S15 but public opening-liability
  disclosure still applies contract/group consumption. Amount integration remains unfinished.

## Renewal commission comparison — October 23, 2026

- Added optional complete commission/value evidence to renewal estimate forms, API and CSV
  schema. POL-142 now decides the acquisition-cost term under the applicable POL-141 option.
- Later approved changes adjust remaining amortization prospectively; trace records retain
  comparison inputs, configured ratio and result. Existing estimates without evidence keep months.
- Native cost/validation cases, populated API approval-to-bundle workflow, frontend forms and
  scoped types/lint pass. See CURRENT-DEVELOPMENT-SCOPE for scope and evidence.
- Schema-verification checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md.

## Frozen opening consumption cap — October 23, 2026

- Native S15 now caps positive opening consumption after applying a frozen opening balance;
  excess is classified as relief from period increases without changing total relief or closing.
- Eleven focused cases and scoped lint/types pass. Restatement differences remain in Other.
  Public FIFO_WITHIN_POB range/currency integration remains unfinished. No deployment.

## Transaction POB opening disclosure — October 23, 2026

- Public opening-liability reports now apply FIFO_WITHIN_POB for uncombined principal contracts
  with the same contracting/performing entity and an unlocked opening. Selected-range posted
  revenue is netted per obligation and capped by its opening billing less revenue, then by the
  contract's displayed opening and actual liability relief. Original evidence is retained.
- Public report/rerun and default-policy cases plus seven focused cases pass; scoped types/lint
  pass. Combined/locked, agent/cross-entity and functional/reporting POB integration remain open.
- Renewal-commission checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md. No deployment.

## Combined transaction POB disclosure — October 23, 2026

- Combined members now contribute obligation eligibility to one capped group total, displayed
  with the full member set. No individual relief allocation is invented or double-counted.
- Public combined report/rerun hashes, ordinary POB regression, 11 focused cases and scoped
  lint/types pass. Foreign-functional/reporting and special attribution remain open. No deployment.

## Functional POB billing evidence — October 23, 2026

- Added original document attribution nodes and functional POB billing evidence using admitted
  invoice FX amounts and existing remainder allocation. Credit signs and source nodes survive;
  liability movements and posting targets are unchanged. Public multi-currency integration remains open.
- Connected S09–S12 invoice/credit case and 24 existing billing/FX cases pass; trace replay,
  unchanged ledger targets, scoped lint/types pass. Combined checkpoint archived. No deployment.

## Public functional POB consumption — October 23, 2026

- Functional opening reports now use original invoice FX attribution and actual posted POB
  revenue, with complete document coverage, group caps and retained rerun evidence. Migration
  0342 updates IPE sources. Zero group openings are explicitly capped without invented inputs.
- Foreign advance-billing and same-currency report/rerun cases, 12 focused cases and scoped
  lint/types pass. Reporting currency and native foreign S15 classification remain open.
- Functional billing checkpoint archived. No deployment.

## Public reporting-currency POB consumption — October 23, 2026

- Reporting opening-liability reports now translate signed period changes in POB eligibility
  against one original range opening, with retained average rates and one combined group total.
  Functional deltas reconcile before translation; prior reports retain their original method.
- Public foreign-currency report/rerun and functional regression pass; focused reversal/rate
  checks and scoped types/lint pass. Native foreign S15 and special attribution remain open.
- Functional checkpoint archived. No deployment.

## Native foreign-functional POB classification — October 23, 2026

- Native S15 now applies FIFO_WITHIN_POB to original functional invoice attribution and cumulative
  revenue, proving the full document population and transaction quantities before classification.
  Only disclosure captions change; signed total revenue, postings and balances are preserved.
- Connected S09–S15 case plus 12 relevant cases and scoped lint/types pass. Special attribution,
  partial billing and frozen POB opening histories still need their remaining sources/evidence.
- Reporting-currency checkpoint archived. No deployment.

## Direct multi-line invoice POB sources — October 23, 2026

- Directly attributed invoice lines now carry original source amounts/dates into functional POB
  evidence. Native and public readers use each line once, including partial opening-period coverage.
  Each line keeps its actual FX amount; whole-document attribution is not reused for every line.
- Connected mixed-date/rate, partial-opening and single-line cases plus relevant regressions pass
  (27 cases), with scoped types/lint. Shared unreferenced lines and special histories remain open.
- Native functional checkpoint archived. No deployment.

## Shared invoice-line cumulative attribution — October 23, 2026

- Shared/mixed invoice lines now retain increments of original cumulative restricted allocation,
  conserving document rounding at each billing-date prefix and original per-line FX sources.
  Negative redistribution is explicitly excluded pending a source-based FX rule.
- True single-document multi-line, differing-rate, partial-opening and refusal cases pass with
  relevant regressions (32 cases), scoped types/lint. No posting or balance logic changed.
- Direct-line checkpoint archived. No deployment.

## Partial-credit audit — October 23, 2026

- Ordinary partial-amount credits already retain credited-invoice weights, original functional
  amounts and all source identities. Two connected full/partial-credit cases and public readers
  verify signed amounts, FX residuals, complete trace replay and unchanged posting targets.
- Removed the blanket partial-credit gap from current status; consolidated POB implementation
  and gaps in CURRENT-DEVELOPMENT-SCOPE.md.
- Negative redistribution pending; shared-line checkpoint archived.
- No accounting-rule change or deployment.

## Zero-opening special-contract disclosure — October 23, 2026

- Functional/reporting POB calculations now admit zero-opening contracting-entity rows for
  agents and cross-entity performers, retaining signed posted revenue and line identities.
  A verified zero group cap requires no invented historical attribution or opening trace.
- Positive openings retain special-source restrictions; unknown posting subjects still refuse.
  Eleven focused cases and scoped types/lint pass. Other contract/reassessment gaps remain.
- Partial-credit checkpoint archived. No deployment.

## POB evidence refresh for existing contracts — October 23, 2026

- Current bundles now declare evidence revision 2, so unchanged monetary inputs do not reuse
  revision-1 calculations lacking original document/line POB evidence. Original history stays intact.
- Populated recompute creates fresh evidence with zero new postings and unchanged income;
  repetition reuses the new result. Two codec/hash/accounting cases and scoped lint pass.
- Zero-opening checkpoint archived. No deployment or database migration.

## Same-date snapshots across calendars — October 23, 2026

- RPO and contract balances now accept separate calendar records when every selected entity's
  explicit period resolves to the identical start/end interval. Missing/different dates refuse;
  range-report guards remain. Existing retained output and currency semantics are unchanged.
- Populated combined totals equal separate runs and retained reruns match; mixed-date refusal
  and the existing calendar-guard workflow pass, with scoped types/lint. No deployment.
- POB evidence-refresh checkpoint archived.

## Combined-component rated usage — October 23, 2026

- USAGE price/recognition now includes original component events once, preserving their ids.
  Nonlease-predominant fees enter revenue; lease-predominant fees enter the excluded allocation.
- Fixed lease-scope trace collision and total allocation: 10,000 + 300 routes out as 10,300
  with zero revenue/RPO. Three full-engine cases plus 26 existing cases, lint/types pass.
- Other payment modes, public persistence/report evidence, modifications and in-scope visibility
  remain open; this does not complete all variable payments. No deployment.


## Lessor assessment workbench — October 23, 2026

- Contract Step 2 now provides explicit component/asset/eligibility/predominance entry and
  independent review submission, plus retained answers and rationale for readers.
- Failed submission reuses the created record; answers freeze through uncertain retries.
  Original component keys remain selectable from retained assessments after combination.
- Two interaction cases, TypeScript and scoped ESLint pass. Modification/variable-payment
  integration and in-scope combined visibility remain open. No deployment.

## Legacy FX-evidence refresh — October 23, 2026

- Fixed unchanged legacy FX runs being reused indefinitely: current bundles declare an
  evidence revision, forcing fresh retained evidence once without rewriting original history.
  Populated close now clears dirty/stale state, preserves revenue and succeeds again.
- Historical hashes/typed inputs remain compatible; populated CV-25 comparison now uses the
  same contract/SSP/posting views as computation. Necessary codec/replay/idempotency checks pass.
- Reader audit confirms POL-015 portfolio application, POL-231 lessor combination and POL-026
  product method behavior remain gaps. Details in CURRENT-DEVELOPMENT-SCOPE.md. No deployment.

## Combined original-component cost recognition — October 23, 2026

- COST_RECOVERY and COST_TO_COST now consume original combined-component costs once per
  event, including events naming several members. Waste treatment remains method-specific.
- Eight full-engine cases and 27 existing input-progress cases pass; original event sources,
  trace replay, scoped lint and types verified. Uses the existing single combined EAC.
- Separate component EAC consolidation, cumulative hours/percentage measures and
  quantity/removal/term reassessment remain open. No deployment.

## Combined-component progress-cost entry — October 23, 2026

The cost drawer now offers original combined members for Progress input, submitting the selected
identity in both the event and payload. Switching to obtaining/fulfilling costs removes that choice
and resets an original member to the pinned host (or clears an unpinned selection), so a hidden
member cannot leak into another cost purpose. Evidence attachments remain required.
Four targeted interaction cases pass, including the existing delivery/return choices and cost
submission with attachment plus purpose switching. TypeScript and scoped ESLint pass.
Independent component EAC aggregation still awaits an explicit scope rule; this UI change does
not decide whether a host EAC represents its component or the entire combination. No deployment.

## Cost-progress original-source drill — October 23, 2026

- Cost recovery/cost-to-cost progress nodes now link original admitted cost events and the
  selected EAC version. Period, event-endpoint and scheduled progress retain those references.
- Version-2 formulas verify source amounts against costs/EAC before the unchanged calculation;
  source roles retain waste/uninstalled distinctions. Version 1 remains available for old traces.
- Evidence revision 3 refreshes existing computation evidence once without duplicate postings.
- 35 focused native cases, three evidence-codec checks and two populated database workflows pass:
  original member costs approve into revenue of 300, saved reporting reruns match, and evidence
  refresh creates no extra posting lines. Scoped lint/types pass. No deployment.
- Separate-member EAC scope and the other documented feature gaps remain unfinished.

## Locked foreign POB opening — October 23, 2026

- Connected the existing functional/reporting POB scenario to the actual August close run,
  journal acknowledgement, reviewed reconciliation gate and approved period lock, followed
  by September performance. Both populated cases pass and saved reruns reproduce all rows.
- USD opening/relief are 11,000. Reporting EUR opening is 9,954.75 and relief is 9,909.91,
  preserving the different retained closing/average rates. The original opening version
  differs from the current version and belongs to the authenticated lock-time child report.
- This verifies existing public report behavior for a single principal, same-entity foreign
  contract with positive opening liability; no production calculation change was needed.
  Combined foreign lock histories and native frozen per-POB inputs remain separate gaps.
  No deployment.

## New obligation opening absence — October 23, 2026

- Public POB opening relief can now use proven zero openings for new obligations whose
  prior-period nodes are absent. Proof joins the selected version's identity to its original
  CONTRACT_AMENDED event, requires an ADD after the opening date, and excludes inherited or
  regrouped identities. Existing obligations without history still require original evidence.
- Saved facts retain the creating event ID/date. Nonzero or wrong-currency historical nodes
  conflict with absence and are refused; the foreign opening reader is not asked to invent FX
  for a proven zero position. Normal report shape and group caps are unchanged.
- 13 focused reader cases pass. A populated approved-modification case proves only the new O2
  qualifies at August end, and no obligation qualifies once its September creation is in the
  opening. Scoped lint/types pass. No deployment; broader special-source work remains open.

## Special-contract zero consumption — October 23, 2026

- Functional POB rows for agent/cross-entity obligations can now retain a positive opening
  when actual group liability consumption is nonpositive: relief is necessarily zero.
  Evidence labels ZERO_CONSUMPTION and retains opening/consumption caps and signed posted
  revenue/line IDs. Unknown posting subjects and positive-consumption special cases still refuse.
- Reporting-currency ranges use this shortcut only when no selected period has positive
  consumption. A release followed by reversal can carry a reporting FX effect despite a zero
  range total, so it still requires original POB attribution. Principal histories retain their
  existing evidence shape. Frozen-source authentication and posted/path reconciliation remain.
- 18 focused reader/period cases, scoped lint and types pass. Positive special attribution and
  other documented gaps remain unfinished. No deployment.

## Visible opening-attribution explanations — October 23, 2026

- Opening-liability reports now expose retained zero-opening, zero-consumption and newly
  created-obligation reasons in an expandable viewer panel. New-obligation proofs show the
  effective date and original event ID, with navigation to the member contract's history.
- Explanation content comes only from the run's retained POB facts. Combined members stay
  individually identified without invented monetary allocation. Legacy reports without the
  new evidence marker keep their previous control totals and display.
- Two source/replay cases, two viewer cases, TypeScript and scoped lint/types pass. A populated
  functional report verifies the marker/control output and identical saved-row replay.
  This adds visible explanations, not complete general-purpose money-cell attribution.
  No deployment; remaining functional gaps stay open.

## Opening-liability money-cell contributors — October 23, 2026

- New transaction, functional and reporting runs retain pre-summary contributions for
  opening liability, recognized revenue and revenue from opening. Summary and detail cells
  explain saved amounts without consulting current calculations. Same-source reruns
  recompute contributions and reject differences; legacy bindings are not backfilled.
- Combined rows remain one monetary contribution with the complete original member set.
  Retained POB evidence exposes opening/consumption caps, posted source IDs, opening trace
  nodes and reporting rates. Contract-policy rows expose their retained balance contribution;
  they do not claim obligation-level source detail. Reader entity restrictions still apply.
- Necessary checks: functional/reporting public cells and saved reruns, combined transaction
  public cell/rerun, four focused backend cases, two viewer cases, TypeScript and scoped lint.
  No journal or recognition calculation changes; no deployment. Broader gaps remain open.

## Opening-disclosure source navigation — October 23, 2026

- Amount contributors now offer internal links to original member histories/journals and
  retained opening calculation nodes. Combined rows keep one amount with multiple source
  links; unknown contributor kinds no longer render a button that does nothing.
- Opening links resolve the original contract version to its actual calculation-trace ID.
  Frozen openings use the authenticated historical version; an absent frozen version never
  falls back to the current version. Source links share the source-detail entity filter.
- Necessary validation: a public foreign-functional locked-opening report opens its linked
  trace and proves the historical version, then reproduces saved rows. Three focused backend
  cases, a rendered viewer case, existing link-route cases, TypeScript, scoped lint/types and
  regenerated API schemas pass. Amounts, source bindings and journal calculations are unchanged.
  No deployment; the broader implementation gaps remain open.

## Native historical obligation openings — October 23, 2026

- Native rollforward_balances accepts explicit opening_obligations alongside the frozen group
  opening. It requires a complete current obligation population, nonnegative integer minor-unit
  amounts and FIFO_WITHIN_POB. The amounts use the selected view's currency; the caller is
  responsible for authenticating the original snapshot and source provenance.
- Transaction and foreign-functional classification can use those original obligation balances
  instead of restated ownership, capped by frozen group liability and actual period consumption.
  Total revenue relief and other movement lines remain unchanged. Calls without the new input
  preserve their existing group-cap-only behavior and do not establish historical POB ownership.
- Thirteen focused native rollforward cases pass, including changed historical ownership at an
  unchanged group total, incomplete/negative/unknown inputs, and functional classification.
  Scoped lint/types pass. No deployment or posting changes.
- This completes the calculation input path only: platform/native snapshot capture and automatic
  handoff of authenticated per-obligation history remain unfinished. Existing public report
  frozen-source recovery is separate; positive special-contract attribution remains guarded.

## Opening-relief calculation breakdown — October 23, 2026

- Opening-liability amount drill now exposes retained obligation opening billing, opening
  recognized revenue, selected-range net posted revenue and eligibility before group caps.
  Eligibility is explicitly not an allocation of combined group relief; absent inputs remain
  absent rather than becoming manufactured zero balances.
- Source amounts and caps name the retained pre-projection currency. Reporting cells show
  signed period relief before translation alongside the report-currency result and retained
  rates, so reversals and different closing/average-rate bases remain visible.
- Five focused contributor cases and scoped lint/types pass. This reads existing saved evidence;
  report amounts, bindings and posting calculations are unchanged. No deployment.
- Native snapshot integration audit: S15 constructs balance_rollforwards, but the platform output
  adapter currently persists no such collection. Completing native frozen-history integration
  requires a persisted output/snapshot path as well as authenticated bundle inputs; adding a
  keyword to the stage call alone would not create a usable platform feature. This remains open.

## Native disclosure output persistence — October 23, 2026

- Evidence revision 4 adds typed native group balance rollforwards to each framework book's
  immutable computation output: entity, period, view, currency/minor unit, opening/closing
  dates, balance movements, memo causes and revenue relief. Current rows explicitly declare
  RESTATED opening basis; they are not presented as authenticated frozen openings.
- The existing computation_evidence output file and SHA-256 checks persist this collection;
  no new table or duplicate report store is introduced. Output encoding omits the optional
  field for older evidence revisions, preserving their prior shape. Monetary differences in
  the new collection are classified as monetary during output comparison.
- 24 codec/upgrade checks and scoped lint/types pass. A populated refresh workflow reads the
  saved output file, verifies its digest and native rows, preserves the old evidence, refreshes
  once and confirms no extra journal postings. No deployment.
- This closes the missing output-persistence link identified in the preceding audit. Original
  per-obligation snapshot capture and authenticated frozen-input handoff remain unfinished;
  the new stored collection alone does not establish historical obligation ownership.

## Original obligation closing capture — October 23, 2026

- Evidence revision 5 captures obligation-level cumulative billing, revenue, nonnegative
  liability eligibility and original flow/node identities inside native rollforward output.
  The stage-13/15 path supplies this data to the existing immutable computation output file.
  Group caps remain separate; obligation eligibility is not allocated group liability.
- Transaction source coverage is checked against each original document. Functional capture
  requires the same complete document population and reconciled revenue quantities; signed
  invoice/credit sources survive zero transaction balances and functional FX residuals.
  Agent/cross-entity/acquired or incomplete sources explicitly record UNAVAILABLE rather than
  inventing snapshot amounts. These records still describe the original computation, not a lock.
- Sixteen focused native/codec cases pass, including changed population, a zero-transaction FX
  residual and unchanged revision-4 outputs. A populated persistence/refresh workflow reads back
  available obligation data with matching file digest and no additional journal postings;
  scoped lint/types pass. No deployment.
- Remaining: bind these original computation snapshots to authenticated lock history, then
  automatically feed their retained obligation balances into the next native calculation.
  No older computation files or lock records are rewritten or backfilled.

## Lock-bound native closing reader — October 23, 2026

- New opening-relief runs bind native closing evidence to the original version already proven
  by the authenticated lock-time balance report. The reader uses that version's computation,
  checks the output file against all retained digests and input identity, then checks book,
  entity, period end, currency scale and group identity. Duplicate views are refused.
- The original output payload, file/hash identity and version are retained with the frozen
  source proof. Reading is cached by version/entity/period/book. Older report bindings keep
  their previous proof shape; absent historical native output is not backfilled from current data.
- Public foreign-functional and reporting locked-opening workflows pass: original USD closing
  obligation eligibility is 11,000, the version differs from the later computation, and saved
  report rows rerun identically. Three reader cases cover digest/duplicate refusal, legacy
  absence and old-binding behavior; scoped lint/types pass. No deployment.
- Remaining native integration: automatically feed the authenticated original obligation
  balances into the next engine bundle and identify that calculation's opening as frozen.
  This reader establishes provenance; it does not yet change the next native computation.


## Visible original-versus-target ownership differences — October 23, 2026

- Opening-liability money-cell explanations now show retained original posted relief, latest
  target relief and the ownership adjustment for each authenticated owner/layer. The explanation
  labels these as member reclassifications, not extra revenue or an allocation of group relief,
  and shows the zero adjustment total alongside the equal posted/target totals.
- Reporting-currency drill keeps these source differences in the original functional currency.
  Only matching computation/entity/recipient sources enter a contribution; an owner outside the
  retained contract set is refused. Existing source-set entity access filtering remains in use.
- A dedicated retained-detail marker preserves old saved explanations. New reports save the
  full matching source set and compare it on replay; no live source inference occurs on drill.
- Eight focused cases and the populated foreign locked-group public workflow pass, including
  both functional/reporting cell endpoints and identical saved reruns. Scoped lint/types pass.
  No journal or engine amount changes, no deployment. The overall development scope remains open.

## Explicit combined EAC coverage — October 23, 2026

- Owner selected explicit coverage: a COMBINATION EAC replaces member totals; MEMBERS
  estimates aggregate only with complete, non-overlapping coverage. Ambiguous host scope,
  overlap, duplicate whole-combination EACs and mixed member currencies stop calculation.
- The estimate-version drawer, validated API parameters and import parameter schema carry
  the scope. Existing element obligation/target keys identify member coverage.
- Cost progress, modification boundary totals and causal estimate replay use the selected
  total. Trace version 3 retains every original component estimate and verifies their sum.
  Loss and impairment selection use the same coverage rule. Later member revisions recompute
  the aggregate without fabricating a persisted combined estimate.
- Evidence revision 6 applies the rule to new computations. Older retained bundles preserve
  their single-host convention; reopening a current combination requires explicit host scope.
  Intermediate event positions wait for complete members; incomplete period totals are refused.
- Necessary checks: full-engine member/whole totals, later revisions, ambiguity/incompleteness,
  overlapping/currency/duplicate scope, loss totals, source replay and adjacent cost cases;
  rendered estimate submission, TypeScript, scoped lint/types. No deployment.
- Limits: mixed explicit/implicit uninstalled-material forecasts require complete explicit
  material inputs. Combined cumulative hours/percentage/milestones and quantity/removal/term
  reassessment remain separate unfinished features. Overall development remains open.

## Hours-only combined EAC entry and calculation — October 23, 2026

- EAC versions may now be entered with expected hours and no invented cost amount. The
  form requires at least one measure and the estimate list displays hours for hours-only EACs.
- Combined EAC aggregates each measure only when every selected member supplies it. Labour
  progress no longer fails merely because cost estimates or cost-material parameters are absent;
  cost progress still refuses missing member cost totals. Missing member hours block recognition
  through the existing EXPECTED_HOURS_MISSING finding, instead of using a partial denominator.
- Full-engine valid hours-only calculation, missing-hours and missing-cost rejection, retained
  trace replay and existing scope cases pass; form submission models, scoped types/lint pass.
- This completes expected-hours input and denominator selection, not original-member actual-hour
  aggregation. Owner choice for combined percentage/milestone progress remains pending.
  Other documented development gaps remain open. No deployment.

## Scoped EAC incurred-cost validation and display — October 23, 2026

- The public EAC cost-floor check and displayed incurred-cost/progress figures now use the
  version's explicit coverage. MEMBERS includes the named obligation/target union once;
  COMBINATION resolves one complete original member set from a hash-verified current trace.
  Missing or ambiguous combination identity requires recomputation/clarification.
- Full-contract coverage includes unassigned contract-level progress costs. Partial-member
  coverage refuses unassigned costs rather than silently ignoring or allocating them. Existing
  versions without explicit coverage retain their prior filter. Date and void filters remain.
- Populated event approval/report replay and EAC API checks passed: whole/member/member-union
  costs are 300/100/300; another unassigned 50 raises the whole threshold to 350 and prevents
  partial-member validation. The existing ordinary EAC cost-floor workflow also passes.
  Scoped lint/types passed; the disposable database was stopped. No deployment.
- Broader Reporting source gaps and combined progress/reassessment development remain open;
  the pending owner choice for percentage/milestone progress is not inferred here.
