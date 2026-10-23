# Royalty correction after eligibility exit — October 22, 2026

## Confirmed failure

Native computation fails when all these conditions hold:

- A functional licence with a 1,200 minimum guarantee has already been delivered.
- A January royalty statement states 600; a February statement states 1,000.
- The February statement precedes the same-day collectibility failure, freezing cumulative
  revenue at 1,600 when the contract becomes NOT_A_CONTRACT.
- A March correction replaces February's 1,000 statement with 800.
- The contract has not re-entered ACTIVE status by the computation/report date.

Stage 09's current realization includes the correction (allocation 1,400), while its status
boundary freezes revenue at 1,600. `obligation_measures` consequently obtains awaiting-trigger
amount -200 and raises ENGINE_INVARIANT_VIOLATED / S09-INV-03. This is a confirmed development
limitation, not a completed accounting behavior or a valid RPO result.

## Necessary owner decision

The owner has been asked whether to permit downward corrections of previously recognized
revenue during exclusion, while prohibiting new recognition, or to defer correction effects
until re-entry. This changes revenue and related allocation timing. No choice has been inferred
from elapsed time; no engine semantics have been changed for this case.

## Reproduction and boundaries

Use the native bundle in
`backend/tests/domain/reports/test_rpo_ordered_eligibility.py`, function
`test_royalty_guarantee_correction_and_satisfaction_across_eligibility`, omit its
`worlds.criteria_met(events, exited)` event, and call with `after=False, delivered_early=True`.
Keep the original statement-correction and delivery inputs. Inspect `compute(bundle)` before
asserting report totals. A local reproduction script is kept under `.run/` (not published).

The three neighboring no-reentry combinations (statement before/after exit and delivery
before/after exit) that do not leave recognized royalty above the corrected allocation compute
successfully and produce zero unexplained RPO movement. Existing same-day re-entry coverage
also does not reproduce this failure. These observations do not prove the entire royalty
lifecycle complete.

The separate POL-199 awaiting-satisfaction gap has now been implemented: native calculations
retain the unrecognized royalty remainder; RPO, rollforward and close-variance readers use
that quota while retaining fixed guarantees. Multiple partial exemptions are separately
listed and currency-projected totals reconcile. This does not resolve the correction-after-exit
income-treatment decision described above.
