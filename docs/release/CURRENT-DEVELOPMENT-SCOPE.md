# Current development scope

Owner scope confirmed October 22, 2026. This is the current development index, not a
certificate that every historical limitation has been resolved. Dated checkpoints in
LIMITS-1.0.md and BUILD-HISTORY remain evidence, not a cumulative list of unfinished work.

## Contract costs across aligned calendars — October 24, 2026

Contract cost rollforward now accepts separate calendar records with explicit from/to keys when
all selected periods and the preceding period match exactly. Each entity keeps its original
cost movements, carrying-balance checks and currency sources. Incompatible or incomplete
ranges still refuse. See [checkpoint](COST-CALENDAR-ALIGNMENT-2026-10-24.md).

## Multi-currency locked disclosure packs — October 24, 2026

New ASC606/IFRS15 close approvals retain all three currency packs atomically at one cutoff.
The viewer and public report APIs read the selected original snapshots; historical locks
without that view refuse explicitly. See [checkpoint](LOCKED-DISCLOSURE-CURRENCIES-2026-10-24.md).
This supersedes the currency-lock gap in the earlier disclosure checkpoints below.

## Reporting-currency disclosure packs — October 24, 2026

Live packs now admit reporting currency across all nine children. Contract costs translate
monthly with explicit FX/rounding, conserved category endpoints, retained rates and independent
original carrying checks. See [checkpoint](REPORTING-DISCLOSURE-2026-10-24.md). This supersedes
the live reporting-pack gap below; currency lock snapshots are covered by the later checkpoint.

## Functional disclosure packs — October 23, 2026

Live disclosure packs now support functional currency across all nine child reports, section
assembly and retained reruns. Zero-opening RPO no longer requires a preceding FX rate solely
for a zero opening term. Locked packs retain their transaction sources; reporting-currency
packs remain unfinished. See [checkpoint](FUNCTIONAL-DISCLOSURE-2026-10-23.md).

## Acquired functional sources — October 23, 2026

Revision 16 connects original cutover billing attribution and actual FX amounts to native
functional POB classification, closing eligibility and the API source reader; journals remain
unchanged. See [checkpoint](ACQUIRED-FUNCTIONAL-SOURCES-2026-10-23.md) for tested boundaries.
Public acquired report/lock workflows and mixed-sign/special histories remain open; older
blanket foreign-source limitations below are partially superseded.


## Closed acquisition cutover — October 23, 2026

Revision 15 uses complete original baselines for native transaction closing at an exact
closed cutover with absent presented targets, removing the false zero/OTHER offset without
posting or reopening periods. See [checkpoint](ACQUIRED-CLOSED-CUTOVER-2026-10-23.md).
Foreign and broader acquired-history work remains open.


## Acquired POB baseline — October 23, 2026

Native transaction POB eligibility and closing snapshots now retain original acquisition
baselines under evidence revision 14; journals remain unchanged. See
[checkpoint](ACQUIRED-POB-BASELINE-2026-10-23.md) for validated cases and remaining foreign,
recomputed-baseline, public-report and acquired-lock boundaries. Historical acquired-source
limitations below are partially superseded; the overall acquired feature remains incomplete.


## Cross-entity principal POB opening — October 23, 2026

Public POB reports now verify contracting-entity liability relief against original intercompany
due-to sources, retaining entity identities and source proofs across transaction, functional and
reporting views. Original POB caps and combination caps remain distinct. See
[checkpoint](INTERCOMPANY-POB-OPENING-2026-10-23.md) for implemented scope and remaining boundaries.

## Agent contract and POB FIFO reports — October 23, 2026

Both FIFO policies admit original agent sources from any selected-group member across all
three currency views. POB caps remain tied to original attributed opening evidence; combination
totals are not allocated to members. Revision-3 reports preserve older saved-version behavior.
See [checkpoint](AGENT-POB-GROUP-SOURCES-2026-10-23.md).
Mixed opening/current sources now retain net totals and full sources with explicitly unavailable
opening amounts and incomplete currency totals; see [mixed-source checkpoint](AGENT-MIXED-SOURCES-2026-10-23.md).
Remaining: cross-entity agent/acquired sources and owners outside the selected historical group. Historical gross-closing notes below are source
preparation, not the current report boundary.

## Original agent gross-control closing evidence — October 23, 2026

- Revision 8 captures same-entity agent closing control balances and complete original billing,
  control-release and functional source identities. Agent control relief is labelled gross and
  never stored as net revenue. Functional targets must match original transaction control flows.
- Evidence explicitly keeps net opening-revenue attribution UNAVAILABLE and places these facts
  in a separate control_closing record. Existing frozen-opening admission cannot mistake the
  record for supported net commission attribution. Older revisions remain unchanged.
- Necessary checks: 26 focused cases pass. A full merchant-agent calculation retains the
  120,000 prepayment and 120,000 gross release with identical posting intents/balances; foreign
  source validation retains gross-control amounts and refuses a substituted net commission.
  Scoped lint/types pass. No deployment.
- This is retained-source preparation for the unfinished agent opening report, not completion
  of net revenue attribution. Owner choice for mixed opening/current-period agent receipts is
  pending, alongside percentage/milestone progress. Cross-entity/acquired sources remain open.


## Original labour-hour progress sources — October 23, 2026

- Evidence revision 7 retains the latest admitted cumulative-hour event and every selected
  original EAC expected-hour version. Prospective segments also retain the original baseline
  event; superseded cumulative readings are not added together.
- Registered labour-hours formula v2 verifies current, baseline and expected source totals
  before evaluating the existing arithmetic. Earlier retained bundles keep formula v1.
  The full-engine comparison proves identical contract figures and posting intents.
- Calculation explanations include the new source-verified formula text. Registered the
  existing multi-member cost formula v3 in the stage catalogue and added its explanation.
- Necessary validation: 43 focused cases pass, including original combined EAC sources,
  exact trace replay, rejected changed source amounts, latest-record selection and prospective
  baseline reconciliation. Scoped lint/types pass. No deployment.
- Actual-hour aggregation across original members and the pending percentage/milestone choice
  remain separate work. The broader Reporting/system gaps remain open.


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


## Delivery boundary

Finish the repository for public publication under its existing noncommercial license.
Prioritize features and targeted verification. Publish reviewed changes directly to main;
do not deploy. Migration into live business, exhaustive approval workflows, sandbox lock
history reproduction and independent accounting sign-off are not development gates.
Keep critical financial permissions, segregation of duties and audit evidence. Sandbox
refresh from production must preserve isolation and allow experimentation.

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

## Reporting implementation status

### Aligned range reports across separate calendars — implemented October 23

Contract balance rollforward, revenue from opening liability and RPO rollforward can now use
separate calendar records when an explicit from/to selection proves the same complete fiscal
range. The proof compares every selected period's key/start/end and the preceding period, and
checks continuity. Matching first/last dates alone is insufficient. Missing endpoints, reversed
ranges, different interior periods and missing/different opening periods retain the existing
calendar refusal. Implicit endpoint selections and other unsupported builders remain guarded.

Necessary verification extends the populated duplicate-January-calendar workflow to all three
range reports: each aggregate monetary cell equals the sum of independent entity runs and each
saved rerun reproduces its original rows. Adding the April calendar still refuses the different
population. Both populated calendar workflows pass; a focused interval case covers same-edge
interior differences, missing opening/endpoint, reversed and empty selections. Two production
modules pass type checks and scoped lint passes. Existing postings, currency conversion, source
retention and date-allocation semantics are unchanged. No deployment or schema migration.


### Snapshot reports across separate calendars — implemented October 23

RPO and contract balances accept an explicitly selected fiscal period across different calendar
records when every selected calendar contains that key and its start/end dates are identical.
The framework proves date equality before creating a report. Different or missing intervals
retain CALENDARS_DIFFER. This does not enable unmatched dates or range reports with implicit
endpoints/interior-period differences. Existing currency conversion, source retention and saved
rerun behavior remain unchanged; there is no new schema or accounting interpretation.

Necessary verification: a populated duplicate January calendar/entity with a separate contract
runs both report types alongside the original January entity. Every monetary total equals the
sum of independent entity runs; saved rerun rows are identical. Adding the April-calendar entity
still refuses the mixed September/December population. The existing all-report calendar-guard
workflow also passes, as do scoped types/lint. Other calendar restrictions remain where the
builders lack date alignment. No deployment.


### Opening-liability POB attribution — current consolidated status, October 23

The dated sections below are checkpoints; this current summary supersedes their earlier blanket
statements that functional/reporting, native foreign or ordinary partial-amount credit memos
are unfinished.

Implemented for complete retained principal/same-entity sources:
- Public transaction, functional and reporting views, retained policies and original-source reruns.
- Existing-contract recomputation refreshes earlier evidence to revision 3 once, even when
  monetary inputs are unchanged. Original saved records remain immutable; new reports use fresh sources.
- Original functional invoice/credit values and exact source-population checks, including a credit
  for only part of the original invoice. Full transaction cancellation preserves functional FX
  residuals; no source disappears merely because its net amount is zero.
- Direct multi-line invoices and nonnegative cumulative increments of shared/mixed invoice lines,
  with original dates/rates and partial opening-period admission.
- Native S15 functional POB classification, preserving total revenue and all posting targets.
- Reporting period deltas against one original range opening, with retained average rates.
- Combined group totals with complete member sets and one group cap; no member ownership invented.
- Public lock-time opening recovery from authenticated original report bindings. This is distinct
  from the native snapshot handoff for unchanged groups, complete group unions and proven new members.

Remaining implementation/evidence:
- Negative redistribution caused by cumulative largest-remainder rounding: a presentation/source
  choice is pending; do not assign negative changes to positive invoice FX weights.
- Positive-opening agent/cross-entity attribution and acquired/baseline openings with complete
  original sources. Zero-opening functional/reporting contracting-entity rows are admitted as
  described in the latest checkpoint, with no assertion about historical ownership.
- Native snapshot handoff is connected for unchanged groups, complete original-group unions and
  proven post-lock new members. Combined foreign locked groups now have populated native and
  public functional/reporting verification above. Partial historical-group splits and special
  source populations remain open; a group cap alone does not prove POB ownership.
- Credit populations where only a subset of a source document belongs to the admitted position,
  if such a retained lifecycle population is encountered. This is **not** a normal partial-amount
  credit memo, which already uses credited-invoice weights and has been verified.

Focused partial-credit audit: a EUR 3 invoice at USD 3.01 and a EUR 1 credit at USD 1.00 yield
USD 0.67 on each of three obligations (USD 2.01 total), with EUR 0.66/0.67/0.67 transaction
quantities. Both document sources survive in every public-reader result. The existing full-credit
case retains the USD 0.01 residual when transaction balances net to zero. Connected trace replay
passes, and layer movements/ordinary posting targets match execution without disclosure evidence.
These two necessary cases verify existing behavior; no new accounting or posting rule was added.


### Rollforward Other explanation threshold — implemented October 23

The rollforward now reads `close.rollforward_other_threshold_ratio` and retains its value
with report evidence. An expandable viewer warning lists signed Other and closing amounts
when absolute Other exceeds the configured share of absolute closing balance. A nonzero
Other against a zero closing balance is flagged; equality is not. Checks run separately for
each currency and contract as well as currency totals, preserving offsetting contract
exceptions. Contract details link to the corresponding ending-period reconciliations.
Existing tie-out failures remain unchanged, including those below the display threshold.
Saved reruns use the retained threshold; legacy bindings without it keep their old shape.
This adds report-level explanation details, not new monetary columns or posting rules.
Necessary verification: two backend unit cases covering thresholds, offsets and retained
bindings; one populated database rollforward case; two viewer cases; scoped lint/types.

### Sequential modification causal analysis — owner-selected scope

On October 22 the owner chose original-event-order recomputation, explicitly labelled causal
analysis and reconciled to the period total. This replaces the previous requirement to assign
unique original posted functional amounts to individual events. Do not change posting or FX
semantics to manufacture such ownership.

The register already has native event TP/catch-up/components, analytical spot equivalents,
source drill, and a limited original functional calculation path for an exclusively explained
period. These remain distinct from the new causal analysis. Close variance already supports
individual event replay; the modification register integration is implemented below.

Implement the selected mode using authorized retained computation inputs and fixed reference,
currency and reporting-period bases. Replay events in effective-date/record-sequence/key order;
retain each signed change and executed input/output hashes. Preserve positive and negative
changes even when their net is zero. Reconcile baseline plus modification and other event effects
to the reproduced final period amount, showing other effects explicitly rather than assigning
them to a modification. Labels and cell evidence must say causal analysis, not posted ownership.

Execute engine calls outside database transactions, with worker heartbeats. Saved report reruns
must use their bound results, and source access must cover the full computation group. Keep old
saved reports unchanged.

Implemented in the register through Currency amount basis → Sequential causal analysis
(`currency_basis=causal_analysis`). The worker authorizes retained original computations and
requires all entities in a computation group to be selected. It calculates outside SQL
transactions with heartbeats, retains per-step hashes, and rechecks requester access before
saving. Baseline includes the fixed original posted history; it is not an opening balance.

Transaction, functional and reporting views show baseline, individual selected modifications,
other events and final period revenue. Signed zero-net changes remain separate; reporting uses
pinned period-average rates. Approved but unapplied modifications show an explicit unavailable
row. Separate-contract bookings can show an explicit zero before activation. Amount cells show
retained calculation evidence. Existing saved reports retain their earlier shape and semantics;
causal reruns rebuild the saved results without rerunning the engine or reading current amounts.
Migration 0335 freezes catalogue/schema metadata for the new option.

Necessary verification: nine native causal cases (including USD/GBP effects, reporting,
offsetting changes and a delivery between modifications); 40 existing variance replay cases;
two populated database workflows, including public runs/cells in all three views, a later second
modification and equal-output retained reruns, plus separate-contract booking; ten frontend
parameter/drill cases; scoped lint/types and catalogue checks. These are bounded examples,
not proof of every contract/currency combination. Original posted event ownership is no longer
required for this owner-selected causal-analysis feature.

### Mixed original sources — aggregate presentation implemented

The owner selected net revenue totals with complete original source membership, without
inventing individual layer amounts. BBR revenue cells now retain verified transaction and
functional ledger totals, source contract/layer/date/key identities, prior postings and evidence
hashes. Scalar histories verify independently of source ownership, including mixed TIME/EVENT
inputs. Source identities carry no net amount. Saved reruns preserve this evidence; older reports
keep their prior drill. Missing original evidence is explicitly unavailable. Source details are
withheld when they span entities outside the viewer's access scope. Migration 0336 records IPE.

Necessary verification: two populated multi-deposit agent workflows, including a combined
contract, public BBR cells and identical retained cell reruns; 50 revenue-trace/BBR unit cases;
eight catalogue cases; populated migration/catalogue parity and scoped lint/types pass.

Gross-control aging continues to use actual gross sources. Per-layer net allocation and finer
within-period TIME/EVENT ownership remain deliberately unavailable where native evidence does
not determine them; the owner-selected aggregate presentation does not assert such ownership.

### Royalty correction after collectibility exit — implemented

The owner selected reductions of already recognized income, with no new income while excluded.
Stage 09 now revisits previously recognized usage periods in original event order, allowing the
1,600 to 1,400 correction while preserving the frozen licence satisfaction and minimum guarantee.
Upward corrections, later satisfaction and newly reported usage periods cannot create income;
an upward revision after a reduction does not re-recognize that reduction before re-entry.
Trace nodes retain the actual statement/estimate inputs of the reduced target. Existing same-day
re-entry behavior is retained. See ROYALTY-EXIT-CORRECTION.md for bounded verification.

## Implemented priorities, with bounded claims

- BBR reporting currency: all four measures translate original functional amounts at pinned
  entity-period averages, with signed source rounding tied to period totals. Journal revenue
  uses the same aggregate conversion basis; retained cell evidence names rates and original
  functional amounts. Foreign-entity report/cell/rerun and signed rounding checks cover this path.

- Modification amount drill: new report cells rebuild saved inputs and open original native
  calculation nodes where retained. Analytical spot/reporting equivalents list their pinned
  rates separately. Missing source identity in older runs requires a new report; amounts are
  never taken from today's modification. This adds navigation/evidence, not per-event posted
  functional ownership.

- Close-variance event detail: an opt-in mode now evaluates each business event in original
  order, retains signed differences, preserves offsetting effects and reconciles driver totals
  and frozen endpoints. Functional positive/negative same-period modifications are covered,
  including net zero. Membership/reference/population phases retain explicit boundaries.
  This is causal replay attribution, not original per-event journal-line ownership; the latter
  is outside the owner-selected causal-analysis scope described above.

- RPO: royalty remainder and targeted VC exclusions, fixed guarantee retention, separate
  partial-exemption rows, rollforward and close-variance projection, currency rounding and
  retained bindings. Missing exact dated royalty evidence still requires recomputation.
- GL reconciliation: balance plus document CSV/XLSX uploads, shared connector/file difference
  attribution, retained comparisons and role-level report reconciliation. Document amounts
  are not added to closing balances.
- Billing reconciliation: post-lock invoices enter the first later period open at receipt on
  both sides; origin periods persist in differences and sign-off evidence, and new late documents
  invalidate reviewed comparisons. See LATE-BILLING-RECONCILIATION-2026-10-23.md.
- Combined-contract aging: original receiving-contract aging and separate member allocation
  adjustments.
- Sandbox: production refresh and editable isolated periods; production lock-history replay
  is outside the requested scope.

The revenue waterfall now aligns whole selected intervals by actual dates across calendars.
Identical dates can combine different local period keys; different dates get separate columns
and entity-specific contributor populations. Aligned layouts keep fiscal labels; older saved
runs preserve their earlier interpretation. This does not reallocate partial fiscal periods
into common calendar months. Other reports with calendar-compatibility guards still require
separate implementation and must not be enabled by simply removing those checks.

These statements do not prove every combination of contracts, currencies, calendars and
lifecycle events.

## Forecast publication re-export

Original forecast publications now accept the report rerun API as well as the existing UI
catalogue re-export flow. The API first verifies the original publication identity and digest,
then binds its saved format and five-section dataset through the existing catalogue adapter.
It does not rerun the forecast engine. Re-export retains requester/scenario/entity/export
permissions and the original dataset hash. Original reports remain immutable.
The populated forecast lifecycle passes with original and catalogue reruns in JSON, CSV and
XLSX, identical data hashes and bindings, and retained source-access checks; scoped lint/types pass.

## GL zero-variance automatic certification

GL reconciliation now evaluates published AUTO_APPROVAL rules at trial-balance attachment,
using the same kind-specific matching as billing. Only a nonempty, fully stated comparison
with zero variance can qualify; absent policy or unresolved amounts retain manual review.
Both file and connector attachments share this path. Rule identity is written once (migration
0337); CTL-025, CTL-026 and the audit trail retain the comparison and certification evidence.
No policy is created or published automatically. Necessary verification covers populated file
attachment with/without policy, differences under the same policy, source-free drafts, and
existing billing certification, plus transition-migration parity and scoped lint/types.

## Secondary-book late-event reporting

New computations retain separate late-event findings for each book kept by the contracting
entity, using that book's actual posting-period resolution. Engine diagnostics and fallback
findings share book-specific identities; a primary-book diagnostic cannot suppress a secondary
finding. The out-of-period register accepts these identities and keeps its existing book,
entity, known-at and ledger-deduplication filters. Legacy findings retain their original book
scope; no historical findings or saved reports are rewritten. This does not restate historical
balance classification. Migration 0338 records the source join interpretation.

Necessary verification: two producer unit cases cover different posting periods, entity-book
membership, prior inclusion and diagnostic deduplication; a populated K07 report workflow covers
original import computation, currency views, cutoff/origin filters and separately stored IFRS15
finding visibility without ASC606 duplication. The secondary finding in that database witness
is fixture evidence, not a full second-book lock/computation lifecycle. Eight catalogue checks,
migration metadata equality and scoped lint/types pass.

## Cross-calendar revenue disaggregation

New disaggregation runs align selected whole fiscal periods by actual start/end dates. Identical
intervals combine even when local period keys differ; different or partially overlapping
intervals get separate date-labelled columns. Aligned calendars retain existing fiscal labels.
Control totals retain entity/local-period/date-to-column mappings and explain that supplied keys
select local fiscal periods. No partial-period reallocation is implied. The report can now run
across entity calendars; other reports' compatibility guards remain in place.

A retained layout marker preserves new reruns; older saved bindings keep their original fiscal
columns. Existing transaction/functional/reporting amount logic and journal comparison remain.
Migration 0339 freezes the catalogue interpretation. Necessary checks cover two interval-layout
cases, a populated mixed-calendar report compared to separate entity runs and a saved rerun,
existing journal tie-out and retained functional/reporting rate workflows, plus scoped lint/types
and migration metadata equality. These do not claim common-month allocation of 4-4-5 periods.

## Explicit cross-calendar waterfall selections

The waterfall API now accepts explicit local fiscal-key ranges across entity calendars. Its
existing retained date buckets and entity-specific amount/contributor selection supply the
required semantics: a key selects each entity's own interval, and actual dates label separate
columns. This applies to month, quarter and year; it does not force different intervals into
one common period. Legacy saved bindings retain their prior layout. Other unsupported report
kinds still reject incompatible calendars.

Necessary verification: three populated API workflows (month/quarter/year), each compared to
separate entity runs, every dated cell value checked through the explain API, and identical
retained rerun rows. The remaining calendar-guard workflow passes. Six existing date-bucket
unit cases check source separation and retained layout; scoped lint/types pass. No new financial
calculation, API schema or database migration was needed for this entry-point change.

## Period-end VC and royalty assessment controls

The final NETTING_RECLASS close pass now collects native VC reassessment and royalty coverage
facts from the engine states it already calculated, without another engine pass or changing
financial output serialization. Applicable facts become blocking CLOSE exceptions for the
selected entity/book/period, retaining subject/version or usage dates and the exact input hash.
The existing exception gate prevents lock while those findings remain open. The close run can
finish so the accountant can inspect and remedy its findings. The cockpit's VC count and
its queue link use that same period-state blocking filter, including book scope. Generated VC
findings carry the element code for the contract's reassessment banner; OPEN and IN_PROGRESS
items both remain visible. Royalty findings have a readable title. The extended lifecycle and
two focused UI workflows verify these connections; frontend type/lint checks pass.

Rechecks use stable contract-based identities, including after combination membership moves,
and settle only previously generated findings for the same book/period and assessed contracts
that are no longer present. Failed or skipped groups do not clear findings. Legacy/manual
exceptions retain existing scope. No new approval workflow is introduced.

Necessary verification: existing normal close workflow; an injected-gap end-to-end close
workflow proving persistence, book-specific gate counts and subsequent automatic settlement;
the native stage-08 reassessment and stage-09 royalty coverage cases; scoped lint/types.
The lifecycle witness injects both fact types rather than representing a full royalty contract
through the API. Existing engine limits remain: VC follows the enforced reassessment election;
royalty coverage requires a satisfied licence, accrual policy, prior covered usage and a
whole-month cadence. This does not invent an initial reporting cadence where none is recorded.

## October 23 publication and historical-backlog audit

Read against main `47db35bfc3db6de9ad624823dbca085823b31e51`:

- Approval availability is implemented, not a new development task. `_notify_assigned` sends
  APPROVAL_UNASSIGNED alerts to independently scoped access administrators; pending-request UI
  hides the warning when content is withheld. LIMITS already records B1-15 closed in its dated
  October 7 entry; its later historical C-6 table must not be treated as a new missing feature.
  This was code/evidence inspection, not a fresh approval-workflow test run.
- Close-run input freshness compares retained rate/policy signatures with the current standing
  inputs. This is distinct from historical B2-2/C-7's per-contract pinned-rate race. The latter
  was reproduced and addressed by the retained-input check described below;
  `run_inputs.standing` alone was not completion evidence for it.
- Secret-pattern scan: 4,183 tracked/nonignored files, nine allow-listed matches, zero findings
  and zero unused exceptions. It does not inspect ignored local credentials or all Git history.
- Runtime dependency licences: 142 packages (86 Python, 56 npm), eight allow-listed packages,
  zero findings and zero allow-list errors. This is a licence check, not a vulnerability audit.
- `git ls-files research-harness docs/research` returns no paths. LICENSE remains PolyForm
  Noncommercial 1.0.0; the repository is source-available under a noncommercial restriction,
  not an OSI open-source licence. No deployment or external accounting approval was attempted.

The rest of the release-candidate verification below remains outstanding; these two refreshed
checks do not certify the whole repository or replace feature-specific evidence.

## Repository completion evidence still required

After feature completion, refresh the bounded release-candidate checks recorded in PROGRESS.md
(dependency audit, local build/compose, local baseline security scan, configuration validation
and disposable restore drill). They authorize local verification, not deployment or a live
business launch. Audit remaining historical limitations against current code before treating
any as either open or complete. Registration of all report definitions alone is insufficient.

This index incorporates subsequent October 22 feature checkpoints recorded in PROGRESS.md. No independent accounting sign-off is requested
as part of this development scope.

## October 23 contract FX freshness at close — implemented

Migration 0340 retains each new computation's actual currency set and economic FX inputs.
The lock gate compares those inputs with currently committed rates through the closing date,
including contracting groups and groups with posted activity for the performing entity/book.
The close worker marks stale heads FX_REPUBLISH and uses the existing computation worker to
repair them before period-end passes. Original computations and their postings remain immutable.
Identical economic values under a new version and changes dated after the closing period do not
by themselves fail this comparison. The check conservatively covers available inputs for the
recorded currencies, not only rates individually stamped on posted lines. Legacy heads without
this evidence fail closed until a fresh computation records it; current rates are never passed
off as original historical inputs. A populated downgrade refuses to discard the new evidence.

Bounded verification: both native concurrency witnesses (approval commits after computation,
and approval published after computation cutoff) detect a clean stale head at the lock gate;
the actual close worker repairs revenue from 5,550 to 5,600 under FX_REPUBLISH and clears the
freshness mismatch. The third ordering still refuses the stale computation before posting.
The ordinary K01 close/rerun passes, as do economic-signature checks, scoped lint/types and
12 selected unit/privacy checks. Migration 0340 was applied in these populated database runs.

Two pre-existing verification gaps were surfaced and remain outstanding: the privacy catalogue
omits 11 columns (historical_source_commit, subledger_posting_commit and modification.termination),
and the offline ORM/migration comparison parser fails while reading revision 0166. The full
privacy coverage check and five dependent schema comparisons therefore do not pass. New fx_inputs
is classified and documented; these results are not a full-suite or release-candidate pass.

## October 23 privacy field catalogue reconciliation — completed

Added the two existing historical commit-evidence tables (10 identity/timing columns) and
modification.termination to the classification registry and data-model declarations. Commit
identifiers and timestamps use the existing internal-metadata rule and audit retention;
termination terms use the existing confidential-contract-terms rule. These entries do not
implement or change export authorization, deletion or retention execution. All 12 privacy
catalogue checks now pass, including complete code-column coverage and bidirectional document
agreement. This supersedes the 11-column omission reported in the preceding checkpoint.
The separate offline schema parser failure remains open; its first failure is revision 0166,
where a trailing constraint fragment is incorrectly interpreted as a column.

## October 23 migration/schema verification repair — completed

The offline migration interpreter now splits CREATE/ALTER clauses by top-level commas while
preserving nested parentheses, multiline constraints and SQL quoted text. Transactional LOCK
TABLE statements are explicitly recognized as having no column-definition effect. This fixes
the revision-0166 constraint-fragment failure and permits replay of the complete current chain.
The resulting comparison exposed documentation omissions: five composite primary keys, two
array defaults, and two nonstandard column-table headers. These declarations now match the ORM
and migration definitions; no production schema or accounting behavior changed.

All ten architecture checks and all twelve privacy catalogue checks pass. The architecture
checks include negative witnesses for type/scale, nullability and primary-key mismatches,
plus the new multiline/quoted-comma witness. This supersedes the earlier parser gap. It is an
offline definition comparison, not a new database upgrade/downgrade or full release-suite run.

## October 23 current-source audit — remaining cost-policy implementation

Read against main `53eb3d9b1a4e0f11b02d4b7815ecad036c360e4d`. The historical B3-22
cost-policy gap is still present: `s11_costs_loss/capitalise.py` selects the contract term or
approved RENEWAL_EXPECTATION.amortization_months under POL-141, without evaluating POL-142.
`costs.commensurate_ratio` occurs in the stage key list and policy memo, but has no calculation
reader. The public renewal-estimate schemas and typed estimate input expose amortization
months without the initial/renewal commission-rate comparison inputs.

Required development: carry explicit initial/renewal commission and contract-value evidence
through the approved renewal estimate and typed input; evaluate the configured comparison;
apply the resulting term in the existing capitalization/amortization paths and retain its
calculation evidence. Cover both sides of the threshold and later estimate changes with
necessary native checks. Preserve existing explicit month estimates when comparison evidence
is absent; do not invent commission rates from unrelated revenue or relabel missing evidence
as a completed commensurateness test. This remains an implementation task, not an independent
accounting-signoff dependency. Other historical policies still require reader-by-reader audit.

## October 23 runtime dependency audit refresh

`make audit-deps` passed on the clean exported source for
`53eb3d9b1a4e0f11b02d4b7815ecad036c360e4d` (tree
`00ebb6bfed4b6009b5e02c7de7519ae7f3f2c46f`). All 86 pinned Python runtime distributions
were audited, including eight marker-qualified requirements; zero Python vulnerabilities
and zero npm runtime advisories across all severities. Output digest:
`d3eadb3604981c65ab13422ffd9a537f2fa90505545fdde6256c0111d951e363`.
Machine-readable source-bound evidence remains under `.run/reports/audit-deps/`.
This is a dated dependency check, not a container build, deployment or full-goal completion.

## October 23 renewal commission comparison — implemented

POL-142 now reads explicit comparison evidence from approved RENEWAL_EXPECTATION parameters:
initial commission/value and renewal commission/value, all in the estimate currency. Public
estimate forms expose the four optional amounts, require a complete comparison and positive
contract values, and show the saved evidence in the version figures. API validation enforces
the same rules; CSV parameter schemas admit the fields. Existing JSON parameter storage and
typed bundle capture retain the evidence without a schema migration.

For acquisition costs under TERM_PLUS_EXPECTED_RENEWALS_UNLESS_COMMENSURATE, exact rational
comparison evaluates renewal rate >= configured ratio * initial rate. A passing comparison
uses the related contract term; otherwise approved amortization months remain. Subsequent
approved estimates adjust the remaining amortization from the following day under the existing
prospective convention. Capitalization/expense and later amortization trace parameters retain
the comparison amounts, ratio, outcome and estimate version. Contract-term/customer-life modes,
fulfilment costs and old estimates without comparison evidence retain their existing behavior.
Comparison evidence is at the renewal estimate's existing contract scope, not a new per-payee
commission-plan allocation mechanism.

Necessary verification: 14 native cost cases (including threshold boundary, below threshold,
configured ratio and prospective change) plus parameter validation pass; the public API workflow
rejects incomplete evidence and preserves approved amounts in the original computation bundle.
Seventeen frontend form cases, frontend type checking and scoped lint/types pass. No deployment,
new database migration or independent accounting approval was performed. This supersedes the
POL-142 reader/input gap in the preceding audit; other historical policies remain unaudited.

## October 23 legacy FX-evidence refresh — repaired

A populated legacy witness exposed an idempotency collision: a head without fx_inputs, already
computed under FX_REPUBLISH with unchanged inputs, was reused by the close worker. The close
reported success while the group remained dirty and stale. New platform bundles now carry
optional evidence_revision=1 in their logical identity, requiring fresh persistence once after
this upgrade. The original calculation and its missing evidence remain untouched. Repeated
current-format inputs retain ordinary idempotency; no duplicate ledger amounts are introduced.
Historical inputs omit the marker from hash views and still decode/recompute with their original
hashes. The upgrade comparison's CV-25 view also now uses contract, SSP and posting hash views,
matching the actual input hash for populated bundles rather than only minimal fixtures.

Verification: the fail-first populated legacy close now clears its dirty/stale state, preserves
revenue and original evidence, and closes successfully again. The existing persistence-idempotency
case, 21 codec/upgrade cases and replay decision checks cover current repeats and historical
replay. Scoped lint/types pass. No schema migration, deployment or accounting-rule change.

## October 23 remaining policy reader audit

POL-015 portfolio estimates still lack shared portfolio-rate application to member contracts;
POL-231 still lacks eligible lease/nonlease combination and predominant-component routing.
POL-026 is driven by explicitly entered option terms; product policy values are not consulted
for that method. These are implementation gaps, not release-check substitutes. POL-142's
commission comparison is implemented above. Preserve explicit historical option terms when
adding product-policy behavior; the existence of registry entries is not completion evidence.

## October 23 material-right product default — implemented

POL-026 now supplies new option-entry defaults through the same resolved per-book policy
inputs as computation, retaining product/template pins where they already exist. The new
material-right-defaults read requires contract.read and the visible obligation/contract; it
returns each book's method and source. The form initializes from a common default, displays
its required inputs and allows explicit selection. Conflicting book defaults or a failed read
require explicit selection. New API terms may omit/null ssp_method to resolve the common default
inside the authorized creation transaction. Missing method inputs still fail validation.

Creation persists the concrete method in immutable option terms before computing; an explicit
method always wins. Drafts without an inception pin read the currently resolved product policy.
Changing that policy later does not rewrite saved option terms or their calculated SSP. This
implements a product default at entry, not retroactive replacement of explicit contract facts.
Existing contract creation permissions, activation review/SoD and rollback behavior remain.

Necessary checks: populated public option entry selects the approved ENTERED_AMOUNT product
default when method is omitted, retains SSP 123.45 after the draft product default changes,
rolls back a failed calculation and preserves independent activation review; two existing
explicit discount/likelihood workflows pass; two per-book resolution cases and 18 form cases
pass, with scoped lint/types. API document and generated frontend types are refreshed. POL-015
portfolio estimates and POL-231 lessor combination remain implementation gaps. No deployment.

## October 23 portfolio implementation — storage foundation in progress

Current-source audit: engine returns already accepts a portfolio RETURN_RATE pin and applies
its rate to transferred units, but platform bundles always supply portfolios=() and omit
portfolio estimate versions. Approval explicitly refuses estimates without contract_id.
BREAKAGE selection is contract-only. These paths need integration; a registry flag alone is
not sufficient. Do not mark shared estimates complete from the following storage work.

Revision 0341 implements the specified portfolio and portfolio_member tables, tenant foreign
keys, non-overlapping record-time intervals and once-only closure without history rewriting.
The application role cannot delete membership history or change its identifying fields; the
closure trigger also protects owner updates. Downgrade refuses populated records. Privacy
classification is promoted from pending to implemented for these two tables.

Snapshot inventory/order/reference resolution now includes both tables, retains contract and
estimate portfolio references, and exports membership at the requested cutoff without future
closure data. This is dataset-level coverage, not a populated end-to-end sandbox refresh proof.
Necessary checks cover schema/document/privacy agreement, snapshot inventory/cutoff and
membership ownership/history plus empty upgrade/downgrade and populated downgrade refusal.

Next development: authorized portfolio/member commands and UI; reviewed shared estimate
versions; member-specific application events and recomputation; retained input/source reporting;
populated snapshot restoration and end-to-end reconciliation. The owner has been asked about
local-versus-portfolio precedence and redemption-ratio versus total-quantity distribution.
Neither choice is assumed to be approved. No deployment.

## October 23 portfolio management — implemented

The public API and Settings → Reference data → Portfolios now support creating and editing
named portfolios, searching contracts to join, ending current memberships with a reason, and
viewing retained membership history. Both portfolio and member lists use cursor pagination
and optional counts. Commands serialize on the portfolio row, require its current ETag and
write audit facts. Membership changes require estimate.create for the contract's entity;
contract RLS also filters member reads and counts. Historical joins are never overwritten.
The UI retains unsaved metadata after a version conflict and offers an explicit latest-value
reload. Read-only users can inspect the population and history without editing controls.

Necessary verification: one populated public API workflow covers create/update, joining,
closure/rejoin, stale and missing ETags, hidden-entity reads/counts/writes, read-only users,
cross-tenant access, audit facts and an unchanged computation head. Four UI workflows cover
creation, join/remove requests, history, stale-edit retention and read-only access. The 24
route checks, frontend type/lint and scoped backend type/lint checks pass. The route inventory
also now lists four previously implemented screens omitted from its expectation. Generated
OpenAPI/types include the new routes; existing API path definitions remain unchanged.

This completes population management only. Shared estimate approval/application, per-member
calculation/reporting and populated snapshot restoration remain. The two previously asked
estimation choices remain unapproved. No deployment or accounting-signoff gate is introduced.

## October 23 portfolio sandbox refresh — populated verification complete

A populated K01 workflow now exercises the actual TENANT_SNAPSHOT copy and SANDBOX_RESET
LATEST handlers with portfolio data. It creates a portfolio and member through public APIs,
loads the original sandbox, closes and rejoins that member in production, then refreshes the
sandbox from production. Both retained member intervals and identifiers match the source.
An authorized member removal in the successor sandbox leaves production's current member
and complete history unchanged. The real copy/load/recompute jobs succeed on this population;
no copy implementation change was needed. The focused database workflow and file lint pass.

This closes populated portfolio/member restoration and isolation coverage noted above.
It does not establish shared-estimate application or restoration of portfolio estimate
versions that the public authoring/approval workflow does not yet implement. Those calculation
and reporting paths, along with the two owner estimation choices, remain outstanding.

## October 23 shared-estimate definitions — authoring foundation implemented

Portfolio detail now exposes shared estimate definitions for RETURN_RATE and BREAKAGE, with
an explicit estimation method. Public nested list/get/create routes use the existing estimate
table and estimate output shape. Creation requires a current portfolio ETag, rejects duplicate
codes, records audit facts and advances the parent version. Lists support cursor paging,
code search/sort and counts. The detail page exposes the definition form and list.

Shared definition access requires contract.read for every retained member, including former
members; creation additionally requires estimate.create for the same complete population.
Hidden members cause a generic refusal without returning identities or counts. Removing the
last current member cannot reveal historical shared-estimate evidence. Partial write scopes
cannot create a shared definition even when the actor holds broader read permission.

This is definition authoring only: version values, approval, application/recomputation and
reporting are not yet enabled, and the UI explicitly states that boundary. No portfolio/local
estimate precedence or breakage distribution choice has been assumed. Necessary verification:
the populated portfolio API workflow covers definitions, duplicate/stale requests, full-member
scope and historical-member protection; five UI cases plus frontend types/lint and scoped
backend types/lint pass. No deployment.

## October 23 shared-estimate draft versions — implemented

Portfolio estimates now support explicit-currency draft versions through nested create/list/get,
full-value update and discard APIs and the portfolio detail page. The editor includes effective
date, decimal amounts/rate/quantity, return carrying/recovery costs and window, rationale and
scenario values. It preserves decimal strings and existing additional version fields. Currency
is required rather than inferred from a member contract; contract-specific modification and
judgement links are refused. Existing method, parameter and amount validation is reused; shared
rates are bounded to zero through one. These saved values remain unapplied drafts.

Population locking serializes membership and draft commands. Creation checks the parent ETag
and permits one open version; editing/discard checks the version ETag and explicitly increments
its row version (the existing IM-S transition mechanism does not do that automatically). Discard
retains the numbered version as VOIDED, and later versions do not reuse that number. Reads and
writes retain full current/former member permissions. UI conflicts keep the typed values; closing
and reopening loads the latest version. Voided values remain viewable without editing controls.

Necessary verification: the populated portfolio API workflow covers required/invalid currency,
rate bounds, method immutability, one-open-version, stale edit, discard/history/numbering and
hidden-member access, with an unchanged computation head. One existing contract constraint-range
workflow checks the shared-validator refactor. Six UI workflows include decimal preservation,
create/edit/discard payloads, stale-value retention and read-only void history. Frontend types/lint
and scoped backend types/lint pass. OpenAPI and frontend types are regenerated. No deployment.

Remaining shared-estimate work: evidence/submission, independent approval and application events,
member recomputation and retained reporting sources. Portfolio/local precedence and breakage
allocation choices remain unapproved; this draft workflow chooses neither and changes no posting.

## October 23 shared-estimate evidence — implemented and access leak repaired

Saved portfolio draft versions now expose supporting-file upload/attachment, download and
uploader-only reasoned void controls. The page uses the existing attachment/file APIs and
server controls. After upload succeeds but attachment fails, retry reuses the uploaded file
identity and the retained attachment command key. Voided versions expose evidence read-only;
new versions must be saved before files can be attached to their identity.

A populated API witness first reproduced a permission leak: the attachment registry treated
an estimate version without contract_id as a tenant-level subject, so a member outside the
portfolio could list its evidence. The registry now resolves shared versions through every
current and former portfolio member. Its outer join preserves RLS-hidden contracts as missing
scope and refuses access instead of silently authorizing only a visible subset. Existing
contract-level estimate attachment authorization remains in place. List, direct content read,
attach and file-reference scope use the same resolver; the existing uploader's own file-read
rule is unchanged. The authoritative data-model subject table now matches this rule.

Necessary verification: the populated public workflow permits full-scope readers, refuses an
outside member's list/download/attach and a partially authorized writer's attach, and permits
the uploader's reasoned void, after all current members have left. Seven file-access registry
checks pass. Seven portfolio UI cases include failed-attachment retry with one upload and the
same command key, download navigation and reasoned void. Frontend and scoped backend lint/types
pass. Shared estimate approval, application/recomputation and reporting remain outstanding.
The two calculation choices were re-presented to the owner before starting their dependent
work. No deployment and no inferred accounting approval.

## October 23 shared-estimate audit history

Shared definition and version commands now retain the actual object id instead of only a
bulk fact id list. Version edits/discards retain before/after values and row version.
The event freezes all distinct current/former member contract ids after full-population
authorization, allowing the existing contract audit trail to find shared changes even
after memberships end. Existing events are not rewritten. Portfolio metadata is classified
as tenant-level and membership as contract-scoped; metadata gains a business label.

Necessary verification covers the populated create/edit/discard workflow and historical
member key, scoped writer classification, lint and types. The full writer architecture
scan reports 29 unrelated existing findings: release_validation and forecast audit object
types are unclassified, and sandbox_reset_job has an unregistered computed writer.
These remain outstanding; this checkpoint does not establish a full architecture pass.

## October 23 lessor component combination — initial computation implemented

POL-231 now reads the election resolved for the associated lease obligation (including product
policy). A reviewed OTHER assessment on each nonlease obligation provides:
obligation_key, lessor_lease_obligation_key, lessor_asset_class,
lessor_same_transfer_pattern, lessor_operating_lease and lessor_nonlease_predominates.
All three assessments are strict booleans and all fields are required together. The existing
judgement API schema validates these fields; existing review/bundle selection still determines
which records reach computation. Unrelated later OTHER assessments do not mask this assessment.

At inception, eligible associated components combine under S03-R-11. Their prices and original
member identities are retained; the nonlease host supplies its transfer measure when nonlease
predominates, otherwise the lease host routes the entire amount out. Contradictory dates,
unknown lease targets, inconsistent group predominance/asset class and differing nonlease
transfer measures refuse computation. IFRS remains separate, as do absent assessments,
unelected policies and components failing either eligibility criterion. Trace parameters retain
the reviewed judgement keys and resulting scope. Predominance is never inferred from price.

Necessary verification: 12 targeted cases include both full engine allocation/revenue paths,
strict input validation, product-level election, unrelated OTHER records and absent/ineligible/
IFRS cases. Eight existing scope/election cases pass; scoped lint and types pass.

This is NOT completion of POL-231. Remaining: dedicated assessment entry UI, populated public
create/review-to-computation verification, modification/variable-payment handling across combined
members, and scope-exclusion/reporting display of the full combined population and assessment.
Those paths must be inspected and completed before claiming this policy is release-ready.
No deployment.

## October 23 combined lessor scope Reporting — implemented

Scope exclusion rows now show the full original component set, exact reviewed assessment
numbers, rationales and retained-evidence basis for a combined lease. The amount remains one
combined allocation, counted once; no per-component attribution is invented. The source is
the selected version's hash-checked calculation trace, not current membership or the latest
host judgement. Structured JSON component keys preserve delimiters inside identifiers.
Older combined traces without that structured field explicitly report unavailable membership
instead of guessing from comma-separated text. Existing non-combination rows and saved reports
keep their old column shape. New saved report evidence retains the added fields for reruns.

A populated workflow publishes the lease template election, creates/submits a contract-level
assessment through the public judgement API, independently approves it, activates with the
existing fixture and runs the report through its public job. It exposed and repaired a real
initial-combination defect: the lease host's standalone entered out_of_scope_amount was retained
after combination. Combined drafts now clear that standalone measure so the full component is
measured. The 108,000 combined case now reports 108,000 rather than the old 81,000 lease-only
memo, with both original components and the actual reviewed rationale.

Verification: the populated combined report and identical saved rerun pass; the existing scope
workflow (including functional/reporting and saved reruns) passes. Twelve targeted engine and
27 pure register cases pass, along with production lint/types. Test-file lint excluding existing
import-order drift passes. No deployment.

Still open for POL-231: dedicated user entry UI; modification and variable-payment treatment
across combined members; broader in-scope combined-component visibility (nonlease-predominant
components correctly do not appear as scope exclusions). This checkpoint does not close those.

## October 23 lessor assessment workbench — implemented

Contract workbench Step 2 now opens Lease combination assessment. Readers can inspect the
retained record status, original component keys, underlying asset class, three assessment
answers, conclusion and rationale. Holders of judgement.create in the editable workbench can
record an ASC606 assessment with explicit same-transfer-pattern, operating-lease and nonlease-
predominance answers and submit it through the existing independent judgement review flow.
The associated lease policy election remains managed through the existing policy controls.

The form selects component keys from current obligations plus retained assessments, so a merged
original component can still be named. All answers and the rationale are required. Creation and
submission preserve command identities on uncertain responses; a completed create is retained
when submission fails. Fields freeze during that retry to prevent accidentally submitting changed
answers against an existing record. A known create validation refusal permits correction.
Read-only and historical workbench views show evidence without authoring controls.

Necessary verification: two interaction cases cover complete payload/required answers,
create-once/submit-retry, disabled editing after create and reader-only history. TypeScript and
scoped ESLint pass. The previous populated backend judgement/approval/report workflow validates
the API path reused here. No deployment.

POL-231 still requires modification/variable-payment integration and in-scope combined-component
visibility. This UI does not mark the overall policy or repository complete.

## October 23 combined-component rated usage — implemented for USAGE measure

Reviewed POL-231 component keys now survive allocation-state construction. The shared derived
usage reader selects the host and every original component within the same contract, retaining
original event identity and counting each event once even when it names multiple components.
Stage 04 price and stage 09 recognition use this same set. Other obligations retain their
existing single-obligation behavior. This applies to USAGE / PERIOD_VC, not every payment mode.

For a nonlease-predominant USAGE component, a 200 rated fee recorded on the original lease
increases both transaction price and revenue by 200. The complete trace re-evaluates.
For a lease-predominant USAGE component, all rated fees follow the combined lease out of 606.
This required fixing the version-date lease-scope trace collision and publishing the total
lease allocation (including rated fees), with linked source events and consistent contract/
obligation totals. A 10,000 fixed amount plus 300 fees produces 10,300 excluded allocation,
zero 606 transaction price/revenue/RPO and no schedules. The scope register already consumes
that obligation allocation; fees are not added again by the report.

Verification: three full-engine scenarios cover original-source collection, duplicate naming
and the lease-predominant path, including trace reevaluation. Twelve earlier combination and
14 existing usage cases also pass (29 total); scoped lint and eight-file mypy pass.

Remaining: public event-entry/persistence and report verification for these new fee cases;
RIGHT_TO_INVOICE source selection across original components; variable payments where the host
uses a different recognition method; contract modifications; in-scope combined-component
visibility. Do not describe all variable-payment handling as complete. No deployment.

## October 23 combined usage public persistence — verified

The USAGE implementation above now has a populated public event-submission workflow: Maya
submits rated fees on both original components, Priya independently approves, and both source
events retain their original obligation keys. Persisted contract output and the public scope
report agree on 108,300 (108,000 fixed plus 200 and 100 usage), with zero ASC606 transaction
price, revenue and RPO. The saved report reruns with an identical output hash and row data.
The helper uses the existing activation fixture; this is not a new public activation test.

This checkpoint adds necessary end-to-end evidence for the previous implementation, not a new
payment mode. The selected workflow and scoped test lint (excluding existing import-order drift)
pass. RIGHT_TO_INVOICE across original members, other host recognition methods, modifications
and in-scope combined-component visibility remain unfinished. No deployment.

## October 23 combined right-to-invoice — implemented

Stage 04 pricing and stage 09 fixed/variable progress now read every original POL-231 member.
Each component retains rated-usage, delivered-units-times-original-rate, then net-invoice source
priority. One member's rated usage does not suppress another member's performance. Shared source
events count once; conflicting prices for one multi-target delivery are refused rather than
inventing an allocation. Event order is retained for the cumulative above-stated-price boundary.
The nonlinear-price/variable-element expedient guard now checks every original member.

Billing lookup, cumulative billed traces and tax attribution resolve original members to their
combined host. This fixes a real failure when a service invoice names a merged-away member.
Combined lease scope measures also support RIGHT_TO_INVOICE: fixed consideration plus excess
performance is routed out once, with consistent obligation and contract outputs. Full-engine
cases with 12,000 rated lease performance and a 6,000 service invoice plus separate 500 tax
produce 18,000 in-scope revenue, or 18,000 excluded allocation with zero 606 revenue/RPO when
the lease predominates. Billed consideration is 6,000 in both paths; traces re-evaluate.

The same exercise found the RTI invoice fallback deducted tax twice. The canonical event schema
(04 OQ-AKI-10) explicitly supplies amount net of tax, as stage 10 already implements. The shared
RTI kernel now uses that net amount directly; ENGINE_SPEC_B's conflicting pseudocode/text is
aligned. This correction applies to standalone RTI obligations as well as combined components.

Necessary verification: 38 targeted native cases cover mixed sources, original rates, returns,
advance-invoice exclusion, deduplication/conflicting rates, the original-member pricing guard,
full 606/842 outputs and existing usage/billing behavior. Six production modules pass scoped
mypy and changed Python files pass lint. No deployment.

Still open: populated public RTI persistence/Reporting workflow; other host recognition methods;
contract modifications; in-scope combined-component visibility. This is not a general ASC842
measurement engine and does not close the overall publication-readiness goal.

## October 23 in-scope combined-component Reporting — implemented

Latest contract status now shows original component membership, exact reviewed assessment
numbers, rationales, scope and retained-evidence basis beside the combined obligation amount.
Both service-predominant IN_SCOPE_606 and lease-predominant LEASE_842 combinations are eligible;
the scope exclusion register correctly remains restricted to routed-out components. No amounts
are invented for individual original members and totals continue counting the combined row once.

The source is the selected contract version's hash-checked calculation trace and the exact
immutable reviewed records it names. The existing scope register shares the rationale reader.
Latest-status saved inputs now retain this evidence; reruns use it without live membership or
judgement queries. Old saved inputs and reports without combinations keep their original column
shape. Mixed datasets leave combination fields blank for ordinary rows. Older combined traces
without structured membership retain the explicit unavailable-membership explanation.

Verification: a populated approved service-predominant case reports one 108,000 allocation,
retains both original members and rationale, reruns with identical hash/data and is absent from
scope exclusions. The existing lease-predominant scope report/rerun also passes. Twenty-eight
unit cases cover retained/latest inputs and register builders, including old column shape,
mixed rows and unchanged totals. Both production files pass scoped mypy and lint. User guide
updated, including its stale statement that POL-231 was entirely unimplemented. No deployment.

This closes the previously listed basic in-scope combination visibility gap through Latest
contract status. Other recognition measures, contract modifications and public RTI persistence
verification remain unfinished; the repository is not yet declared complete.

## October 23 combined-component price modifications — engine implementation

Pure CHANGE price deltas on original POL-231 members now resolve to the reviewed combined
obligation in proposal/application, including treatments, questionnaire and native SSP basis.
The integrity reader recognizes original members while preserving original duplicate/sign checks.
Original line payloads remain intact; only the calculation target changes. Conflicting member
instructions are refused. Quantity, removal and term changes require combination reassessment;
they are not silently applied to a synthetic combined quantity or service term.

The modification's remaining SSP now resolves every original component product, quantity and
price, retaining each source. Previously it priced the summed quantity using only the host
product. Compatible SSP quantity bases are required in this implementation. The existing D18
trace formula accepts an explicit remaining-component count and scales all those parts; older
traces default to one part. A combined 10,000 SSP and a separate 10,000 SSP receive equal shares
of a 1,000 price increase: 10,500 each, with fully re-evaluable trace evidence.

Combined lease output now publishes its current fixed allocation even without usage measures,
and contract scope totals include the change from inception allocation. A 10,000 lease-
predominant combination increased by 1,000 reports 11,000 excluded and zero 606 transaction
price/revenue. Existing usage/RTI scope handling remains consistent. In-scope price increases
and decreases produce 11,000 and 9,000 respectively.

Verification: 46 targeted cases cover new price modifications, shared allocation, scope routing,
conflicting treatments and existing combination/usage/proposal/integrity/prospective behavior.
Seven production modules pass scoped mypy; changed Python files pass lint. No deployment.

Remaining: public modification entry/approval/persistence and saved Reporting verification;
quantity/removal/term changes with reassessed combinations; mixed SSP quantity-basis support;
other host recognition measures. These restrictions are explicit outstanding implementation,
not evidence that the complete modification feature is finished.

## October 23 combined price-change public workflow — verified and SSP defaults fixed

A populated service-predominant combination now has end-to-end evidence through the public
modification API: create a price change on the original L1-LEASE member, explicitly confirm the
classification questionnaire, run the queued preview, submit, independently approve, persist
APPLIED and run Latest contract status. The authored line still names L1-LEASE while the report
has one combined 109,000 allocation (108,000 plus 1,000), both original members and an identical
saved-report rerun hash. Existing activation fixtures are reused.

Classification previously restricted displayed SSP defaults to authored line keys, so a combined
host proposed by the engine had no default when the line named its original member. It now also
includes proposed treatment keys, using each accounting obligation's actual selected version.
This does not fabricate a per-original-member version. Existing authored overrides remain intact.
The wizard's treatment table already reads this basis by proposed obligation key.

Verification: the populated workflow passes with the combined-host default asserted. Existing
K02 classification and five targeted unit cases for selected versions/defaults/overrides pass.
Scoped mypy passes; lint excluding pre-existing import-order drift passes. No deployment.

Next UI gap confirmed in source: the modification wizard gets its line choices only from the
current obligation-version list, which omits merged-away original members. The API supports
those original keys, but the UI selector still needs retained original-component choices. This
checkpoint does not claim that original-component authoring is fully accessible in the UI.
Quantity/removal/term reassessment, mixed SSP quantity bases and other recognition measures
remain open as previously recorded.

## October 23 original-component modification selector — implemented

API-S-Obligation now exposes optional combined_component_keys from the selected contract
version's hash-checked calculation trace. Keys are matched by encoded contract/obligation
identity, parsed as structured JSON, deduplicated and sorted. No keys are inferred from legacy
comma-separated membership or from current judgement records. Existing permission and version
selection apply; only rows already visible to the caller receive their own component identities.
Historical traces lacking structured identity return an empty list.

The modification wizard adds original members absent from the current obligation list to its
choices, labelled with their combined host and Price changes only. A price change submits the
original key with zero quantity; no host product, quantity or end date is invented for the
original component. Other change kinds and duplicate ADD attempts on these keys are refused by
the form. OpenAPI and TypeScript contracts are regenerated. The existing NettingReclassOut role
read now explicitly constructs its AccountRole enum, fixing a pre-existing type error without
changing the serialized value.

Verification: populated obligation read returns both original keys and continues through public
classification, preview, independent approval and identical saved Reporting. A UI interaction
selects the original component and asserts the submitted price-change payload. Four focused
frontend cases cover selection, ordinary price entry and restricted/duplicate-key validation;
TypeScript and scoped ESLint pass. A pure parser case covers delimiter preservation, subject
isolation, legacy/missing evidence and malformed data. Three production modules pass mypy;
scoped Python lint excludes existing import-order drift. No deployment.

The previously identified original-component UI selection gap is closed. Quantity/removal/term
reassessment, mixed SSP bases, other recognition measures and remaining publication checks
remain unfinished. This does not declare the overall goal complete.

## October 23 mixed-basis combined price changes — native implementation

Combined series price-change weights now resolve each original component's SSP basis and
quantity unit separately. PER_BOOKED_TERM scales by remaining service; PER_INCREMENT uses
its declared SERVICE_UNITS or INCREMENTS meaning; AMOUNT remains a directly supplied amount.
The resulting component weights are summed, while added parts keep their existing treatment.
Each component retains its own quantity, term, convention, progress and basis parameters in
the calculation trace so the saved weight can be independently recomputed. Existing common-basis
and inception-all formula paths retain their previous behavior.

Verification: 42 focused native cases pass, including three mixed-basis combinations, complete
trace reevaluation and existing prospective/series regressions. Two production modules pass
mypy and scoped lint passes. This closes the native mixed-basis rejection for the supported
price-change path; it does not claim public mixed-basis approval/Reporting workflow verification.
Quantity/removal/term reassessment, other recognition measures, portfolio application and final
publication checks remain unfinished. No deployment; the overall development goal remains open.

## October 23 mixed-basis public workflow — verified

The combined original-component price-change API workflow now runs with both the existing
AMOUNT SSP entries and a mixed AMOUNT/PER_INCREMENT (SERVICE_UNITS) book created through public
SSP publication. Both paths classify, preview, submit and independently approve the original
lease-member price increase. Latest Contract Status reports the combined 109,000 allocation
and original membership; saved report replay produces an identical output hash.

The mixed path additionally reads the persisted, hash-checked calculation trace, verifies that
two original-component scale records retain AMOUNT and PER_INCREMENT/SERVICE_UNITS, and
reevaluates the entire trace to its stored values. Both API paths passed; the mixed case passed
again after adding the retained-trace assertions. Scoped lint passes, excluding existing import
ordering. This closes the prior public mixed-basis verification gap for this price-only path.
Quantity/removal/term reassessment and the broader unfinished scope remain open. No deployment.

## October 23 forecast contract audit linkage — implemented

Forecast input-set version creation now retains the inherited contract population; updates
and publication retain the union of before/after populations. Captured API commands supply
explicit contract identities and committed import stream events supply actual imported contract
identities. Unapplied files do not acquire guessed identities. Replay publication/completion
and command evidence-file materialization retain their known contract keys. The audit writer
normalizes/deduplicates them into the existing immutable chain and audit_event_contract index;
old audit events are not rewritten. Ordinary capture commands already had their own contract key.

Deal previews are classified as optionally contract-scoped: request/computation explicitly name
no contract, while saving the preview retains the actual created contract. Scenario lifecycle,
refresh, scenario-wide forecast publications and release-validation commands are classified as
tenant-level operations; their individual input/application facts retain contract linkage.
Latest-production sandbox export names its tenant_snapshot audit object explicitly.

Necessary verification: the populated forecast capture/import/publication/replay workflow passes,
including inherited-version and publication contract index rows, import-only identity resolution,
replay/materialization index rows and cancellation rollback. All three audit-contract-key
architecture checks pass, closing the previously reported 29 writer classification findings.
Seven changed production modules pass mypy; scoped lint passes. This is not a claim that all
other audit/security or publication checks pass. Portfolio application awaits the owner's two
calculation choices; other unfinished feature scope remains unchanged. No deployment.

## October 23 filtered audit export — UI integration completed

The Audit log page no longer applies an obsolete restriction that disabled export whenever
Contract or Outcome was selected. The existing audit_log_export backend and catalogue already
support contract_id and outcome; the UI now submits the resolved contract identity and complete
selected outcome array alongside the same actor/action/object-type/date filters used by the list.
A selected contract must resolve before export is available, so failed/pending lookups cannot
fall back to a workspace-wide export. Contract trails without explicit dates preserve their
whole-history semantics. Existing permissions, report retention and downloads are unchanged.

Necessary verification: a UI submission asserts the exact combined contract, multiple-outcome
and action payload; an unresolved-contract case has no export entry point. Both pass, as do
TypeScript and scoped ESLint. Backend filtering and retained-source behavior were inspected;
no backend logic or schema was changed and no new database workflow is claimed. No deployment.

## October 23 original-component deliveries and returns — native implementation

The shared delivery tally now resolves an event's explicit original combined-component key
within its own contract before matching it. Combined UNITS_DELIVERED and POINT_IN_TIME measures
therefore include deliveries/returns naming merged-away original components. Each event is
visited once even when its subject list names both host and member. Existing combined quantity
and allocation semantics are unchanged; this does not implement quantity-changing modifications.

Control-trigger policy and repurchase classification are evaluated using the event's original
component identity. Bill-and-hold eligibility and unmet-criteria diagnostics also use that
original component; a host judgement cannot authorize a sibling's transfer. This change does
not reinterpret cumulative percentage, milestone or labour-hour events as additive quantities.

Necessary verification: eight complete native calculations cover both recognition measures,
original/both-subject event references and a return, with 10,000 recognized after two one-unit
deliveries and 5,000 after one unit is returned. All calculation traces reevaluate. A control case
proves original-member acceptance policy and bill-and-hold judgement isolation. Six existing
recognition regression cases pass (15 total); scoped lint and production mypy pass. Public
combined delivery authoring/report verification, remaining combined recognition measures and
quantity/removal/term reassessment remain open. No deployment.

## October 23 combined delivery/return public workflow — completed

The delivery and return drawers now include merged-away original component choices from the
existing obligation read's retained combined_component_keys. Labels name the combined host;
choices are deduplicated against current obligations. A drawer opened with a combined host
preselected permits switching to its original members. The submitted payload and top-level
obligation_key retain the selected original identity. Ordinary pinned obligations remain fixed.
Other progress, milestone and cost forms are unchanged; their distinct measurement semantics
are not inferred from this delivery implementation.

Necessary verification: two UI submissions prove original keys for delivery and return;
TypeScript and scoped ESLint pass. A populated public API workflow records and independently
approves original lease/service deliveries, then a lease return. Latest Contract Status moves
revenue from 108,000 to 54,000 while retaining the 108,000 allocation. Original event keys persist,
and both saved report reruns produce identical output hashes. Fixture activation remains the
existing system helper, not a newly claimed public activation workflow. Scoped Python lint passes.
This closes the prior public original-delivery/return verification and authoring gap for this
combined units path. Other combined measures and quantity/removal/term modifications remain open.
No deployment.

## October 23 opening-liability policy evidence — retained; amount gap confirmed

New opening-liability disclosures freeze the resolved consumption policy for every consumed
entity and book in opening_consumption_policies_v1. Transaction, functional and reporting
explanations use that original evidence on bound reruns. Mismatched books, missing/extra entity
populations, malformed values and unsupported options refuse; no current policy is substituted.
Older saved bindings without the new evidence retain their existing behavior. The legacy builder
uses the same helper for newly collected inputs. Monetary calculations are unchanged.

Necessary verification: three currency-view finish/rebuild cases forbid current policy reads
and compare identical control totals, including incomplete/altered retained evidence refusals.
The populated public K01 opening-liability report passes. Three production modules pass mypy
and scoped lint passes. No deployment.

A real unfinished reporting feature was confirmed: native S15 implements FIFO_WITHIN_POB using
obligation-attributed billing and revenue, but the public revenue_from_opening_liability builders
still consume the contract/group control path and disclose that limitation in their footnote.
Complete this integration across selected ranges, currency views, locked openings and retained
reruns before claiming that policy is supported by the public report. The native period-level
calculation alone is not sufficient evidence for the report's selected-range semantics. The
policy-retention change above does not close this monetary implementation gap.

## October 23 frozen opening consumption cap — native correction

Reinspection for the public FIFO_WITHIN_POB integration found that native S15 classified opening
consumption before substituting a supplied frozen opening. A smaller retained opening could
therefore be exceeded by the disclosed revenue from opening. After the frozen balances are
applied, positive consumption now respects the displayed nonnegative opening liability; any
excess moves to revenue from other period increases. Total liability relief, total revenue,
closing amounts and memo causes remain unchanged. Existing differences caused by replacing a
restated opening remain explicit in Other; this correction does not erase a tie-out failure.
A larger frozen opening does not invent additional consumption or change original attribution.

Necessary verification: six frozen-opening cases across both consumption policies plus five
existing native rollforward cases pass (11 total), including unchanged total relief and exact
opening/movement/closing arithmetic. Scoped lint and production mypy pass. No deployment.

The public report integration remains open. Further source inspection also confirms that native
foreign-functional layer processing currently follows its layer path without applying the
transaction branch's FIFO_WITHIN_POB adjustment. Thus the native transaction formula cannot be
cited as proof of complete foreign-functional or arbitrary-range policy implementation. Original
functional billing attribution and locked-source consistency must be resolved in that work.

## October 23 public transaction POB opening relief — bounded implementation

New transaction opening-liability reports apply FIFO_WITHIN_POB for an uncombined contract whose
principal obligations are performed by its contracting entity and whose opening is unlocked.
The selected version supplies exact prior-period billed_cum/revenue_cum nodes per obligation;
selected-range actual posted control lines supply net revenue by their original subject keys.
Each obligation contributes min(max(opening billing minus revenue, 0), max(range-net revenue, 0)).
The contract amount is capped by its displayed opening liability and actual liability revenue
relief. The whole range is evaluated once; monthly opening figures are not summed. This is a
report classification, not a change to accounting postings or an invented functional-layer split.

New bindings retain policy by entity, opening node identities and values, posted source identities,
individual eligibility and contract caps. Reruns recompute and compare this evidence. Older bindings
retain their prior calculation. The footnote identifies the applied POB method. Missing original
nodes, unidentified revenue subjects, combined members, locked openings, agent obligations and
cross-entity performance receive explicit refusals when this new transaction method is selected.
Functional/reporting views keep their existing explicitly disclosed contract/layer method; POB
integration there remains unfinished. New obligations without prior-period nodes also remain an
unsupported opening-evidence case, rather than silently substituting zero or latest balances.

Necessary verification: the populated public K01 report applies the new policy and reproduces its
control totals without consulting current policy on rerun; the existing contract-policy report
still passes (two DB cases). Seven focused cases cover the 5,000 service opening with an unrelated
8,000 delivery (only 800 eligible), opening caps, range-net corrections, missing evidence and
policy retention across views. Five production modules pass mypy; scoped lint passes. Disposable
DB stopped after verification. No deployment. This closes the ordinary transaction path only;
combined/locked/foreign-functional and other special-case integration remain work in progress.

## October 23 locked transaction POB openings — original source integration

The transaction POB method now accepts locked openings when the lock retains its authenticated
seven-snapshot disclosure pack and original contract-balance report binding. It verifies the
frozen pack, original source run identity/scope/output digest and binding, reads precisely those
original versions, and ties all three contract position captions to the frozen balance dataset.
It never selects today's version at a historical date. The original POB billing/revenue nodes
supply the opening; current selected-range posted lines supply revenue. Contract absence from the
original frozen population gives no opening, and obligations introduced after that original
version cannot inherit an invented opening. Source run/binding digests and version are retained
with the calculation facts. Original disclosure inputs are cached once per lock/entity/book.

The prior blanket locked-opening refusal is superseded for this path. Missing original lock
sources (including older locks without the disclosure attachments), missing original nodes or a
failed balance tie still refuse. Combined contracts, agent/cross-entity attribution and functional/
reporting currency POB consumption remain unfinished. Saved earlier reports retain their existing
methods; this change does not rewrite snapshots, posting amounts or locks.

Necessary verification: a populated foreign-receivable world closes through its existing public
workflow, then appends a memo to produce a different contract version. The transaction POB report
proves that its opening source version differs from its current version and belongs to the frozen
balance report binding; saved rerun rows match without current policy reads. This case verifies
source integration, not positive liability consumption. Seven focused cases separately verify
positive 800 consumption against a 5,000 original opening, range-net corrections, caps, proven
absence, missing evidence, lock balance mismatch refusal and one-time source loading. The existing
unlocked public POB report/rerun also passes. Three production modules pass mypy and scoped lint
passes. Disposable DB stopped; no deployment.

## October 23 combined transaction POB disclosure — group total presentation

The transaction FIFO_WITHIN_POB builder no longer rejects a retained combination group solely
because it contains multiple member contracts. It reads each member's obligation opening sources
and selected-range posted revenue, then applies opening liability and actual-relief caps once to
the combined eligibility. A combined row presents the group's opening, revenue and opening relief,
with every member's external ID in the summary. It does not invent a contract ID for the group or
present member eligibility as attributable relief. Currency summaries include the group exactly
once. Retained evidence names all member identities and their obligation inputs, labels individual
figures as eligibility capped by the group, and separately records the actual group total.

Single-contract rows and their saved output wording remain unchanged. Locked members use the
previously implemented authenticated frozen-source reader. The public acceptance case here covers
an unlocked combination; combined/locked special histories remain to be exercised as needed.
Foreign-functional/reporting POB consumption and agent/cross-entity attribution remain unfinished.

Necessary verification: the existing approved two-order combination is computed after opening
October. The public report displays one combined row with opening 77,591.97 and positive opening
relief equal to recognized revenue; both member identities appear, individual member rows do not,
and currency totals sum once. Rerun reproduces rows and stored output hash without current policy
resolution. Retained evidence has both original contract IDs and no invented member relief value.
The ordinary public POB case also passes. Eleven focused cases cover eligibility, a binding group
cap, original lock sources, range corrections and policy retention. Scoped lint and three production
module type checks pass. No deployment.

## October 23 functional POB billing evidence — original invoice bridge

Stage 10 now emits one complete signed attribution node per original billing document and POB,
combining direct event amounts with the existing shared-line allocation nodes. BillingDocumentOut
carries those node identities. Stage 12 uses the original billing_activity_functional amount at
its admitted layer date and the stage-10 attributed transaction amounts to allocate invoice
functional value with existing ALG-01 largest-remainder rounding. Trace inputs link to both the
actual functional invoice node and original obligation attribution nodes. Credit memo weights
are normalized to positive weights, then their original sign enters cumulative billing evidence.
The cumulative nodes retain transaction quantities so a future report consumer can check source
coverage against its independent billing population before using the functional amounts.

The resulting billed_obligation_functional nodes and billing_disclosure_targets are disclosure
inputs, never posting targets or assertions about individual historical liability-layer ownership.
Missing document nodes, mixed signs and partial/mixed-date document flows whose amount does not
match the complete original attribution do not receive fabricated allocations. Consumers must
prove complete coverage; merely finding some cumulative evidence is insufficient. No current
report switches to an incomplete source population. Public functional/reporting POB consumption
and native foreign-functional POL-126 classification remain unfinished and must consume these
original sources in subsequent work. Existing traces without these nodes need recomputation
before that new path can use them.

Necessary verification: a connected S09/S10/S11/S12 foreign invoice and credit workflow allocates
a EUR 3 invoice (USD 3.01) across three equally weighted POBs and nets a later EUR 3 credit
(USD 3.00), preserving the deterministic USD 0.01 residual. Every trace node re-evaluates, and
running with versus without disclosure attribution yields identical layer movements and ordinary
functional posting targets. Twenty-four existing billing/FX cases also pass. Three production
modules pass mypy and scoped lint passes. No database, deployment or ledger migration was needed.

## October 23 public functional POB consumption — original-currency integration

New functional opening-liability reports apply FIFO_WITHIN_POB using original POB opening billing
and revenue, actual functional control revenue posted over the selected range, and original group
opening/actual-relief caps. Original invoice functional shares come from the preceding checkpoint's
trace nodes, with their signed invoice/credit population checked document by document against
original transaction attribution. Matching only a net transaction amount is insufficient: cancelling
documents with different FX rates must both be present. Original functional revenue also reconciles
to the transaction revenue quantity. Missing/mixed/partial coverage refuses; older traces lacking
original invoice attribution require recomputation for a nonzero opening. A zero displayed group
opening gives zero relief explicitly, without inventing missing invoice values.

The builder reuses authenticated locked opening sources and groups combined members without
inventing a member split. It checks posted functional revenue against the existing reconciled
balance path. Evidence retains source nodes, posting identities, currency units, method and caps;
reruns rebuild and compare it. Older saved bindings retain their prior method. Reporting-currency
POB projection and native S15 foreign-functional classification are still unfinished. Agent and
cross-entity attribution, partial/mixed-date billing subsets and onboarding source coverage still
need their own complete evidence. Combined/locked functional special histories are not claimed as
fully verified by the single-contract acceptance case below. Migration 0342 adds the actual POB,
original report and disclosure snapshot sources and rules to the report's IPE explanation.

Necessary verification: the EUR receivable fixture optionally books 200 service units, records an
EUR 20,000 August advance and approves 100 units in each of August and September. The public
functional report consumes USD 11,000 from September's opening liability using the original 1.10
invoice rate, rather than USD 11,100 at September's 1.11 rate. Saved rerun rows match without current
policy reads. Existing same-currency transaction and functional POB reports also reproduce their
results (three DB cases). Twelve focused cases include cancelling EUR invoices/credits with a
nonzero functional difference and refusal of missing coverage or wrong currency. Four production
modules pass mypy; scoped lint passes. Migration and public foreign case checked on disposable DB.
No deployment.

## October 23 public reporting POB consumption — period translation

Public reporting-currency opening-liability reports now consume the original functional POB
sources. Each posting-period prefix uses the same range-opening obligation balances, net posted
POB revenue and cumulative actual liability consumption. Differences between capped prefix totals
are signed period attribution changes, not independent monthly opening disclosures. They telescope
to the functional range result before translation. Each group delta is translated and rounded at
that period's retained average rate; opening and recognized amounts retain the existing projected
rollforward sources. The prior closing rate for opening may differ from average rates, so no
second cap against the translated opening is invented. Combined groups retain complete member
sets without per-member relief allocation. Existing saved methods remain compatible; new runs
retain a separate reporting POB evidence marker and original signed period amounts.

Necessary verification: public functional and reporting report/rerun workflows pass. A further
nonidentity reporting case shows USD 11,000 opening as EUR 9,954.75 at the original closing rate
and EUR 9,909.91 revenue/relief at the September average, with identical retained rerun rows.
The focused multi-period case recognizes 120 then reverses 40 against an original opening of
100: cumulative eligibility changes by +100 then -20, translating at 1.2 and 1.5 to 90 rather
than resetting the opening or applying one rate to the net 80. It also rejects an inconsistent
range total. Scoped lint and four production module type checks pass.

This supersedes the public reporting-currency gap above for the supported source population.
Native S15 foreign-functional policy classification remains unfinished. Partial/mixed-date billing,
agent/cross-entity, acquired opening sources and combined/locked foreign special histories still
need their remaining implementation/evidence; this checkpoint does not assert their completion.
No deployment or independent-accounting approval gate was introduced.

## October 23 native foreign-functional POL-126 classification

S12 now carries immutable original signed document/obligation shares alongside its existing
disclosure-only cumulative targets. They include original source keys, posting periods, transaction
and functional amounts and trace node IDs. These are not posting targets or liability-layer
ownership allocations. Native S15 reads the exact source population for the opening, validates it
against S10 document attribution (including each signed transaction share), and reconciles
cumulative functional revenue against original transaction flows at both ends. It then applies
POB eligibility and the group opening/actual consumption caps to the two revenue captions.
Total revenue, closing balances, layer movements and journal targets are unchanged. The existing
frozen group-opening cap still applies after a supplied opening replaces the restated balance.

The supported path is principal obligations performed by the contracting entity with complete
original documents. Missing, duplicated or inconsistent sources refuse instead of silently using
contract FIFO. Acquired opening sources, partial/mixed-date billing, agent/cross-entity attribution
and authoritative frozen per-obligation history still need their remaining work; a group cap alone
is not evidence of original lock-time POB ownership. This supersedes the ordinary native foreign
classification gap above, not those special histories.

Necessary verification: a connected S09/S10/S11/S12/S15 foreign-currency example bills EUR 3,000
in advance to one of two obligations, then recognizes EUR 1,500 on each. At original 1.1 FX,
contract FIFO calls USD 3,300 opening consumption; POB classification correctly calls USD 1,650
opening and USD 1,650 other consumption, preserving total revenue and all balance ties. Removing
original document sources is rejected. Complete trace replay and the existing foreign invoice/
credit rounding test pass, together with 11 native rollforward cases. Four production modules
pass scoped type checks and lint. No database migration or deployment.

## October 23 direct multi-line invoice attribution

The prior whole-document bridge did not cover S13's separate invoice-line flows. S10 now emits
original line attribution and replayable line nodes for multi-line invoices whose every line
explicitly names an obligation. Each line retains its event key and unconditional date; a line
that has not become unconditional cannot enter the opening population. S12 consumes those exact
line amounts/nodes and original per-line FX values instead of reusing the full document for its
first line. S15's transaction and functional source maps use the same line identities. The public
functional opening reader replaces a partitioned document with its original dated line population,
checks the cumulative transaction billing, and requires matching functional activity sources.
There is no additional journal target or change to liability-layer movements.

Necessary evidence: connected S09–S15 cases cover the original single invoice, two directly
attributed lines on different January dates/rates, and a second line entering only in February.
The January opening is respectively USD 3,300, USD 3,450 and USD 1,650. Native POB revenue
classification and public source-reader values agree with those originals; transaction POB
classification reads each line once. Removing original functional sources still refuses, and
all trace nodes re-evaluate. The selected billing-position/native-rollforward/source-coverage
suite passes 27 cases; four production modules pass type checks and scoped lint passes.

Multi-line invoices containing unreferenced/shared lines remain unfinished: independent line
rounding cannot stand in for the document's cumulative restricted allocation. Those require an
explicit conserving source bridge. Partial credit memo populations, agent/cross-entity, acquired
openings and original frozen POB histories retain their existing limitations. This checkpoint
adds no deployment or database migration.

## October 23 shared invoice-line cumulative attribution

Shared and mixed invoice lines now receive source amounts from differences between consecutive
restricted document allocations, ordered by the original unconditional date and event order.
Each prefix uses S10's existing weights, keys and largest-remainder rule. Thus two one-cent
unreferenced lines allocated equally give the first obligation one cent from the first line and
the second one cent from the second line; independent line rounding would incorrectly assign
both to the first obligation. Replayable cumulative/apportionment/difference nodes preserve the
original event amounts. The existing S12 bridge consumes those line increments and each line's
original functional amount. No posting targets, liability movements or original billing measures
are changed.

This only admits nonnegative increments conserving each positive invoice line. Largest remainder
can reduce an earlier obligation's allocation when the total increases. In that case no fabricated
positive-weight FX attribution is emitted; complete-source consumers still refuse that missing
population. An explicit source-based rule is needed before that redistribution can be supported.

Necessary evidence: four connected S09/S10/S11/S12/public-source-reader cases use a single grouped
invoice with two lines, testing direct and shared attribution and a cancellable second line that
becomes unconditional in January or February. The first one-cent line uses rate 1 and the second
rate 2. Shared January evidence is USD 0.01 and USD 0.02 across obligations; when the second line
enters only in February, January admits just USD 0.01. Each selected transaction quantity is
checked and every trace node re-evaluates. Earlier same-number/different-event-date samples were
separate engine documents, not proof of a single grouped invoice; this new coverage corrects that
verification limitation. A 25-to-26-cent largest-remainder redistribution example confirms that
negative increments do not receive invented FX sources. The focused suite passes 32 cases and
scoped type/lint checks pass. Partial credit memos, source-based negative redistribution and the
remaining agent/cross-entity/acquired/frozen-history paths remain unfinished. No deployment.

## October 23 zero-opening functional/reporting special contracts

The POB reader previously refused an agent or cross-entity performer before checking its
already-reconciled zero group opening. That unnecessarily prevented a report from showing actual
period revenue even though opening consumption is conclusively zero. The functional path now
applies its existing ZERO_GROUP_OPENING basis before requiring principal-only opening sources
or loading an opening trace. It still validates current/original obligation membership and every
posted revenue line identity, retaining signed net revenue and all line IDs. The reporting path
uses this same functional result before translation. Existing supported zero-opening evidence
keeps the same shape; transaction behavior is unchanged.

This supports contracting-entity rows with a retained obligation population. It does not invent
performing-entity ownership, bypass original lock-source authentication, or admit positive-opening
agent/cross-entity attribution. Those remain separate requirements. Necessary verification: agent
and cross-entity-performer cases retain 50 less 10 of posted income, return zero opening relief
without reading a historical trace, reject unknown subjects, and continue to reject positive
openings. Eleven focused POB/frozen/range-translation cases pass, with scoped types/lint. No
posting changes, database migration or deployment. Combined-component quantity/removal/term
reassessment remains unfinished; this change does not alter reviewed combination decisions.

## October 23 existing-contract POB evidence refresh

The original document/line attribution implementation changed the retained source graph after
revision 1 was introduced, but bundle assembly still declared revision 1. Consequently unchanged
business inputs could reuse a succeeded computation instead of persisting the new sources that
Reporting requires. Current bundles now declare evidence_revision=2. This changes the retained
input identity once, not the accounting rules, and leaves old bundle decoding/defaults unchanged.
No original input/output evidence is backfilled or overwritten. Users recompute the contract and
run a new report; old saved reports keep their original sources and methods.

Necessary verification: a populated foreign-currency group is stabilized under revision 1, then
recomputed with current assembly. The new computation has a different identity/input hash, posts
zero additional lines, and leaves cumulative income unchanged. A repeated current recomputation
returns the same new ID; the original evidence row remains byte-for-byte equivalent as read from
the database. Two codec/identity cases cover absent legacy revision and revision 1 -> 2, preserved
old hashes, changed CV-25/attribution identities, typed roundtrip, and equal accounting views.
The populated case and both codec cases pass; scoped lint passes. Temporary database only,
no deployment or schema migration. Special-source and contract-reassessment gaps remain open.
