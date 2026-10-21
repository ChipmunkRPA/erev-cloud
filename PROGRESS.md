# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## Current owner-authorized goal — October 21, 2026

Finish the repository for public source publication under its noncommercial license;
prioritize feature completion with necessary targeted validation. Continue directly on main,
review and publish changes without PR accumulation, and do not deploy.

- Reporting priorities remain difference attribution, multi-currency, RPO exemptions and GL
  reconciliation. Combined contracts now retain original receiving-contract aging and separately
  show member allocation adjustments; continue the remaining evidenced Reporting gaps.
- Migration-to-live promotion/replay completion is outside scope; no actual business launch.
- Keep key financial permissions, segregation of duties and audit evidence; full approval
  coverage is not required. Implementation is not a SOX certification.
- Sandbox goal: refresh from production and allow experimentation isolated from production.
  Reproduction of production lock history and sandbox locking are not completion requirements.
- Independent accounting review belongs to the owner and is not a development completion gate.
- Owner resumed development October 21. The app goal tool cannot edit the existing objective
  or resume its paused state; this section records the superseding scope for repository work.

## Original-date usage across initial eligibility batches — October 21, 2026

- Stage 09 now retains realized allocation at original contract-event dates for usage/royalty
  components, using the same realization calculation as its retained period/version amounts.
  A dedicated reader validates these dated trace values; missing dates are not inferred from
  month-end values. Recognition and realization remain distinct.
- Initial usage timelines now use these exact dates at admission, eligibility exit and re-entry.
  Fees realized before exit are VC movements; fees realized while excluded enter with the
  remaining re-entry balance. Old report bindings keep the previous timeline. Migration 0271
  adds rpo_initial_usage_timeline_v1 to both RPO definitions.
- Two original-engine usage journeys cover fees before exit and while excluded within the
  same month. Opening/closing, VC, eligibility and zero unexplained movement reconcile;
  missing original date evidence is refused. The 43 scoped usage/royalty/eligibility checks,
  public initial-usage and sequential eligibility/rerun regressions, lint/types and reversible
  migration/catalogue parity pass. The royalty checks cover the existing engine behavior,
  not a complete royalty eligibility journey.
- Same-day monetary events after a status transition, multiple transitions on a monetary date,
  the public mixed-batch witness, full royalty eligibility witness and B4-11 historical commit
  visibility remain open. No deployment.

## Monetary events in initial eligibility batches — October 21, 2026

- Initial RPO eligibility timelines now retain dated amendment and estimate slices, using
  original event-specific allocation shares. Changes before exit are separately classified;
  changes while excluded are included in the remaining re-entry balance, not NEW_CONTRACTS
  or in-scope modification/VC lines. Original computation IDs and amounts remain unchanged.
- The dated reader now exposes the fixed-allocation measurement date separately from revenue.
  A frozen revenue target may be dated at the exit while allocation still measures month-end.
  Lifecycle cuts remove later same-period changes using complete original boundaries/shares,
  preventing an excluded-period amendment from being included in the earlier exit balance.
- Fixed an engine invariant failure on estimates during a Step 1 revenue freeze. Matching
  frozen before/after targets retain a zero catch-up with the freeze date and S02-R-05 guard;
  the new allocation remains available for subsequent re-entry. Other segment checks remain.
- New reports retain rpo_initial_monetary_timeline_v1; older bindings retain their prior
  timeline. Migration 0270 updates both RPO definitions. Eight original-engine scenarios cover
  price/estimate/both at exit and during exclusion, final included/excluded states and four
  report start positions. The 132 scoped engine/reader/report cases, public sequential
  eligibility/rerun regression, lint/types and reversible migration/catalogue parity pass.
- Initial usage/royalty batches, monetary changes after a same-day status transition, and
  multiple transitions on a monetary-event date still need ordered amount evidence. The public
  batch-to-report witness and B4-11 historical commit visibility remain open. No deployment.

## Initial RPO eligibility timelines — October 21, 2026

- RPO and its rollforward now read original Step 1 status nodes, linked to dated immutable
  source events, when one initial computation contains eligibility-only entry/exit/re-entry.
  Timeline slices retain the original computation ID, allocation and recognition evidence.
  A report starting during an excluded interval recognizes later re-entry as eligibility,
  not a new contract; initial computations ending excluded retain their earlier admission.
- Stage 09 now retains original-cut deterministic schedules before later contract-status
  changes. Without these projections, an excluded final computation erased the future lines
  needed to report its earlier included opening. No proportional schedule reconstruction is
  used. Older traces lacking the required historical projection still refuse that read.
- New runs bind rpo_initial_eligibility_timeline_v1; old bound runs keep the previous timeline.
  Migration 0269 updates both RPO definitions. Original-engine witnesses cover whole-lifecycle,
  opening-included, opening-excluded and post-re-entry ranges, including a final excluded
  computation. The 42 scoped engine/chain/report cases, public sequential eligibility journey
  and retained rerun, lint/types and reversible migration/catalogue parity pass.
- Initial batches mixing these status transitions with monetary events remain unfinished.
  A public batch-to-report witness remains to verify; the public regression above is sequential.
  Arbitrary historical commit visibility (B4-11) also remains open. No deployment.

## Mixed allocation changes at RPO eligibility exit — October 21, 2026

- Retained collectibility exits can now separate concurrent CONTRACT_AMENDED and
  ESTIMATE_CHANGED allocations from the eligibility movement. Original amendment boundaries
  and complete estimate-event shares must reconcile the fixed allocation change; events after
  the exit, missing evidence and competing unsupported causes retain their unresolved result.
  Dated realization stays in VC; the resulting remaining balance leaves through eligibility.
- Trace loading includes excluded eligibility versions with estimates even when there is no
  amendment or entry. New report runs retain rpo_mixed_eligibility_v1; older bound runs retain
  the previous classification. Migration 0268 documents the rule without changing report columns.
- Four original-engine journeys cover plain exit/re-entry, price modification, estimate change,
  and both together. Their separate movements reconcile to original revenue schedules and
  remaining allocation. Missing evidence and legacy behavior are checked. The public reviewed
  exit/re-entry report and bound rerun, scoped types/lint, and reversible migration/catalogue
  parity pass. Mixed-event public command batching is not yet independently verified.
- Multiple eligibility transitions within one initial computation and B4-11 arbitrary historical
  commit visibility remain open. This closes the supported retained mixed-exit decomposition,
  not every lifecycle combination. No deployment or additional accounting sign-off gate.

## Public eligibility workflow and historical projection reads — October 21, 2026

- The public reviewed collectibility/re-entry journey exposed two implementation faults.
  Operational HOLD_APPLIED/HOLD_RELEASED dates could move a June business change into September;
  RPO now dates versions by their business causes, while retaining each original computation
  and its dated recognition/hold evidence. Hold-only versions inherit the prior business date.
  New runs bind rpo_operational_hold_dates_v1; older bindings retain their previous dates.
- Database trace reads omitted cut, period_key and reason even though the engine retained them.
  These parameters now reach the existing projection reader: historical fixed schedules can use
  their original period projections, and unavailable-projection reasons are not silently lost.
- The public journey reviews a not-probable assessment, appends the significant change and
  assessment, generates June RPO, then reviews probable collection, submits/approves criteria
  re-entry and generates July RPO. Eligibility movements reconcile; rerunning June after July
  preserves its original rows. This closes the public-workflow gap recorded in the 0266 note.
- Migration 0267 updates both RPO definitions; reversible migration/catalogue parity, 93 dated
  reader cases, scoped lint/types and the public journey pass. Mixed eligibility exits with
  amendments/estimates, multiple transitions in one initial computation and B4-11 commit
  visibility remain open. No deployment or expanded approval requirement.

## RPO contract eligibility changes — October 21, 2026

- New RPO runs show ELIGIBILITY_CHANGES separately from new contracts, legal termination and
  disclosure exemptions. A retained collectibility exit requires an original not-probable event
  in the selected book at the version date, unchanged fixed allocation and dated realization.
  Criteria-met re-entry carries the remaining balance, excluding already recognized revenue
  and fees from earlier excluded segments. Repeated supported exits/re-entry are handled; a
  first-ever criteria admission remains NEW_CONTRACTS.
- The original Step 1 engine journey exits with opening RPO 1,100 and re-enters with 900: the
  net eligibility movement is -200, with no new-contract or termination amount and no unexplained
  difference. Repeated segments, start-after-exit and realized fees have targeted witnesses;
  monthly functional/reporting translation uses each month's retained average rates.
- New bindings retain rpo_eligibility_changes_v1. Older bindings keep their original calculation
  and columns. Generic output rows/columns and re-lock comparison include the new monetary line;
  migration 0266 updates IPE. Targeted RPO checks, the public rollforward path, lint/types and
  reversible migration/catalogue parity pass.
- Fully terminated contracts cannot be reactivated by the product. Earlier supplied re-entry
  fixtures did not prove that workflow. Mixed eligibility exits with price/estimate changes,
  multiple transitions inside one initial computation and B4-11 commit visibility remain open.
  The new eligibility journey uses original engine outputs; a public reassessment-to-report
  journey is still unverified. No deployment.

## Public same-day usage, estimate and price-change sequence — October 21, 2026

- Extended the public termination journey with an approved 200 bonus estimate and 100 price
  increase after 150 usage, all effective on inception day. The original 160,000 computation
  already exists: NEW_CONTRACTS stays 160,000, VC_ESTIMATE_CHANGES is 350, MODIFICATIONS is 100,
  and CANCELLATIONS is the negative refund. Full termination recognizes the remaining pool;
  partial termination reallocates fixed consideration to the continuing obligation.
- This checks sequential retained computations, public preparation/review/preview/application,
  report ties and bound reruns for FULL/PARTIAL and refunds 0/40. It does not prove one initial
  computation containing every event, or repeated termination/re-entry. No calculation change
  was needed for this sequence. All eight targeted journeys and scoped lint pass; broader
  lifecycle and B4-11 gaps remain open. No deployment.

## GL source selection uses one database snapshot — October 21, 2026

- GL comparisons now resolve source identities, latest captured states, review status and totals
  from immutable report_source_revision rows in one SQL statement across all requested entities.
  The previous current-header query followed by a separate revision query could mix snapshots
  when an already-inserted source revision committed between those reads. Windowed selection
  preserves latest-source precedence and requires a source attachment known at the cutoff.
- New runs retain rollforward_gl_inputs_v6; v1-v5 bound comparisons still rebuild from their
  original evidence. Migration 0265 updates IPE for contract_balances and
  contract_balance_rollforward. Uncovered source history remains unavailable.
- A real two-transaction witness commits a change to a reopened reconciliation after the source
  statement executes: the comparison retains the pre-commit source revision, performs one source
  query and preserves the earlier reviewed historical/bound result. The public uploaded-GL
  report path, 14 GL cases, lint/types and reversible migration/catalogue parity pass.
- This establishes a consistent GL source-selection statement, not historical commit timestamps
  or a transaction-wide snapshot for every report source. B4-11 arbitrary historical commit
  visibility remains open, as do broader RPO mixed-lifecycle journeys. No deployment.

## Public termination controls and same-day usage calculations — October 21, 2026

- The modification form/API now accepts explicit FULL/PARTIAL termination scope and a refund
  in contract currency. Preview and approval use the same CONTRACT_TERMINATED event; the terms
  are stored, displayed in the detail, included in the approval fingerprint and cleared when
  switching to another modification kind. REMOVE lines must have non-positive deltas and cover
  the refund. New/edited termination drafts require terms; already approved historical rows
  without terms retain their original amendment semantics and hash. Migration 0264 retains
  the terms and refuses downgrade while any remain.
- The real command journey exposed two engine faults: inception-day realized fees were included
  in FIXED allocation and then counted again as period fees; an inception-day termination tried
  to extend recognition through a truncated segment ending before the first calendar period.
  Inception allocation now excludes separately recognized period fees, preserving zero trace
  nodes and contract-wide royalty-estimate allocation. Only later term ends extend the horizon.
- Four public journeys exercise two usage obligations, FULL/PARTIAL scope and refunds 0/40,
  including original engine calculations, required approval steps, contract status, reporting and
  retained reruns. Entry 160,000 and VC 150 remain separate; FULL recognizes the nonrefundable
  pool at termination, PARTIAL allocates it to continuing O2 and recognizes it over its term.
  Revenue, refunds and closing RPO reconcile. This closes the supplied-evidence-only limitation
  for this same-day usage/termination case, not every mixed amendment or re-entry sequence.
- Necessary checks pass: four public journeys, three ordinary modification regressions, 236
  pricing/allocation/recognition cases, 48 modification units, 88 RPO cases, 68 frontend cases,
  scoped lint/types, generated API parity, and migration round-trip/data-retention guard.
  Broader repeated cancellation/re-entry, combined same-day amendment/estimate/usage journeys
  and concurrent commit visibility remain open. No deployment.

## Same-day RPO entry with realized usage — October 21, 2026

- Same-day activation/termination can now retain gross new-contract amounts when usage is
  present. Original termination before-state and traced realized fees are required; fixed entry,
  original amendments, usage changes, recognition and cancellation remain distinct movements.
  Later retained usage corrections adjust VC and cancellation without repeating entry/amendments.
- New bindings retain rpo_same_day_entry_usage_v1 and require the existing batch cancelled-usage
  decomposition. Missing realized evidence and older bindings preserve previous eligibility.
  Migration 0263 records the matching IPE rule.
- All 88 related cases, public currency/rate rerun, scoped lint/types and reversible migration
  catalogue parity pass. The new same-day usage/mixed-amendment and retained-correction witnesses
  use supplied boundary/cut evidence, not a new original-engine/public-command usage journey.
- Original-engine/public-command coverage for these same-day usage mixtures remains outstanding,
  along with broader repeated cancellation/re-entry and concurrent commit visibility. Continue
  the October 21 repository-only scope; no deployment or independent accounting review gate.

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
