# Current development scope

Owner scope confirmed October 22, 2026. This is the current development index, not a
certificate that every historical limitation has been resolved. Dated checkpoints in
LIMITS-1.0.md and BUILD-HISTORY remain evidence, not a cumulative list of unfinished work.

## Delivery boundary

Finish the repository for public publication under its existing noncommercial license.
Prioritize features and targeted verification. Publish reviewed changes directly to main;
do not deploy. Migration into live business, exhaustive approval workflows, sandbox lock
history reproduction and independent accounting sign-off are not development gates.
Keep critical financial permissions, segregation of duties and audit evidence. Sandbox
refresh from production must preserve isolation and allow experimentation.

## Reporting implementation status

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

## Repository completion evidence still required

After feature completion, refresh the bounded release-candidate checks recorded in PROGRESS.md
(dependency audit, local build/compose, local baseline security scan, configuration validation
and disposable restore drill). They authorize local verification, not deployment or a live
business launch. Audit remaining historical limitations against current code before treating
any as either open or complete. Registration of all report definitions alone is insufficient.

This index incorporates subsequent October 22 feature checkpoints recorded in PROGRESS.md. No independent accounting sign-off is requested
as part of this development scope.
