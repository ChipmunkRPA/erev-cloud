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

## Confirmed Reporting work remaining

### Actual functional-currency amounts for individual modifications

The modification register has original-currency event TP changes, catch-ups and TP component
breakdowns, plus explicitly selected analytical spot equivalents. Those equivalents are not
actual posted functional catch-ups.

An additional supported path now exposes the original functional **calculation** amount when
one modification exclusively explains its recognition-period flow. It verifies native layers
and both currency totals, retains node identities and shows the calculation period. Mixed
periods remain empty; this is not proof of a posted journal delta and does not close the
multi-event work below. Native USD/GBP positive/negative witnesses and retained-row checks
cover this path; public mixed-period tests verify refusal to misattribute the period total.

Current source boundary:

- `s09_recognition/decompose.py` identifies sequential event causes and cites individual
  `catch_up@event` amounts.
- `s13_books._control_flows` takes the difference between cumulative relief targets and emits
  one revenue flow per subject/period at period end. Its source is the cumulative target.
- S12 retains the historical functional pieces consumed by that flow. The report reader
  `functional_revenue_activity.py` verifies the complete piece population and both currency
  totals, but cannot identify several modification events inside that period flow.
- `builders/modification_register.py` therefore retains its original-source foreign-currency
  restriction; the explicit spot-equivalent mode is a separate supported feature.

Next implementation must carry original event decomposition into the functional source
calculation, retain the event-to-piece evidence, and consume it in the register. It must
handle positive and negative modifications together with ordinary recognition, opening
advances at different rates, period-boundary changes and multiple events on one day.
A scalar period amount or a proportional allocation is insufficient evidence. Preserve
historical bound-run behavior; any change to native monetary results requires explicit
calculation-version treatment and regression evidence, not a silent report-side adjustment.

Completion evidence: a populated public workflow with multiple same-period modifications,
transaction/functional/reporting amounts tied to native postings, and a retained rerun with
identical values after later source changes. A pure conversion helper does not close this item.

### Mixed original sources in revenue attribution

`revenue_trace.split_role_target` still refuses nonzero split roles with multiple original
provenances. Gross agent control can be reconciled to net revenue and supplier amounts, and
explicit zero-weight roles can reverse previous attributed amounts, but these do not establish
an individual owner/layer allocation for every nonzero component.

`split_mixed_sources` also requires finer evidence for a within-period TIME/EVENT mixture
spanning different original sources. Separately classified periods and the supported
single-origin path already work. Complete these through retained native source classification,
with signed amounts and independent transaction/functional reconciliation; do not replace
missing provenance with a ratio.

### Royalty correction after collectibility exit

A delivered royalty licence corrected downward while still outside contract status can have
allocation 1,400 against frozen recognized revenue 1,600, failing S09-INV-03. The revenue rule
for this case remains an owner decision: reverse previously recognized revenue during exit,
or defer the correction's recognition effect until re-entry. The question has been raised;
no choice is assumed. See ROYALTY-EXIT-CORRECTION.md for the concrete reproducer and neighbors.
Other engineering is not blocked by this decision.

## Implemented priorities, with bounded claims

- RPO: royalty remainder and targeted VC exclusions, fixed guarantee retention, separate
  partial-exemption rows, rollforward and close-variance projection, currency rounding and
  retained bindings. Missing exact dated royalty evidence still requires recomputation.
- GL reconciliation: balance plus document CSV/XLSX uploads, shared connector/file difference
  attribution, retained comparisons and role-level report reconciliation. Document amounts
  are not added to closing balances.
- Combined-contract aging: original receiving-contract aging and separate member allocation
  adjustments.
- Sandbox: production refresh and editable isolated periods; production lock-history replay
  is outside the requested scope.

These statements do not prove every combination of contracts, currencies, calendars and
lifecycle events. Cross-calendar period-key reports are intentionally refused when the same
key denotes different dates; support for a common dated multi-calendar presentation remains
an additional Reporting capability, not something to enable by removing that check.

## Repository completion evidence still required

After feature completion, refresh the bounded release-candidate checks recorded in PROGRESS.md
(dependency audit, local build/compose, local baseline security scan, configuration validation
and disposable restore drill). They authorize local verification, not deployment or a live
business launch. Audit remaining historical limitations against current code before treating
any as either open or complete. Registration of all report definitions alone is insufficient.

This index is verified against main c9e00e6. No independent accounting sign-off is requested
as part of this development scope.
