# Explicit combined actual hours — October 23, 2026

Owner selected explicit whole-combination or original-member coverage, requiring every member
rather than guessing missing readings. New platform bundles use evidence revision 9.

PROGRESS_RECORDED accepts hours_scope COMBINATION or MEMBERS; the progress CSV template retains
and reconciles the same identity field. The event drawer offers the two scopes for combined
labour-hour obligations. Member scope presents every original member and submits all readings
in one approval batch. Explicit zero is valid; blank values prevent submission. Whole scope
submits one cumulative total. Original-component selectors support labour-hour events.

The engine takes the latest admitted cumulative event independently for each original member,
never the sum of historical readings. A complete member population is added once. One explicit
whole-combination reading is used directly. Missing members, unmarked scope, mixed scopes and
multiple whole-combination readings refuse the final measurement. Intermediate causal replay
may encounter the first record of a batch: it admits no partial numerator. A prospective
baseline always requires complete coverage, including when measured at an event position.

Formula rec.progress.labour_hours.v3 reconciles current, baseline and expected-hour sources,
including population counts, before applying the existing capped progress arithmetic. Trace
inputs retain each original event identity, member, scope and amount; expected hours retain
original EAC version identities. Older retained revisions keep their legacy scope behavior
and formula when events contain no explicit scope. Percentage/milestone choices are unchanged.

Necessary validation:
- 51 focused native cases across combined hours/EAC and input measures pass, including latest
  readings, zero members, scope refusals, original trace replay and legacy preservation.
  The prospective witness uses actual 500, baseline 150 and expected 1,000: progress 7/17;
  missing baseline members and altered source counts are refused.
- The populated public workflow creates/approves a whole EAC of 1,000 hours, submits/approves
  member readings of 200 and 100, and retains both original payloads. The 108,000 allocation
  reports 32,400 revenue; its saved report reruns with an identical output digest.
- All 15 event-drawer cases pass, including complete member-batch submission and missing-value
  prevention. Frontend types/lint, scoped backend types/lint and OpenAPI generation pass.
  The disposable PostgreSQL instance was stopped. No deployment.

Broader combined quantity/term/partial-removal reassessment, special opening-source reporting,
shared-estimate application and release-candidate checks remain open. Whole-combination
termination has separate native evidence; its populated public verification remains open.


## Measure-specific entry completion

The event drawer no longer asks for an output percentage when recording LABOUR_HOURS.
API and CSV event payload validation allow the ratio to be absent for hours, require actual
hours (including explicit zero), and continue to require a ratio for OUTPUT_PERCENT. Member
batches carry only their original hour observations and explicit scope. The canonical ledger
accepts these hour-only records without replacing a prior output-percentage observation;
recognition uses actual hours divided by the approved expected hours. Previously supplied
ratios remain readable, preserving historical ledger behavior.

Necessary verification: 55 payload/ledger/input-measure cases and all 15 event-drawer cases
pass. The native witness has the same 30,000 and 83,076.92 cumulative revenue with and without
supplied ratios. Scoped backend/frontend type and lint checks pass; regenerated OpenAPI/types
have no diff (the event payload is generic in that API schema). No database migration or
deployment. Public database approval/report replay was verified for the preceding scoped-hours
feature; it was not rerun for this input simplification.
