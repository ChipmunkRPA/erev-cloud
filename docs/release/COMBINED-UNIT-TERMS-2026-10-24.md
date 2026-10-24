# Common-end-date continuation for combined unit obligations

Evidence revision 30 admits a dated CONTINUE assessment for a native in-scope combined
UNITS_DELIVERED or POINT_IN_TIME obligation when every original member changes to the same
end date. Every line must be CHANGE, quantity deltas must be zero, start dates must stay
unchanged, and the common end date cannot precede the modification effective date.
The complete original population and eligibility confirmations remain mandatory.

The modification uses PROSPECTIVE treatment. The existing boundary preserves recognized
income and prior segments while applying the new end date prospectively. Original component
quantities and product identities continue into later boundaries. Older evidence revisions
retain their term-change refusal.

The modification wizard exposes the same explicit confirmation for TERM_CHANGE and checks
the complete common-date population before submission. Editing date, kind or lines clears
the confirmation. Existing critical approval and audit controls remain in place.

Verification:
- 16 native reassessment cases, including valid terms, old-revision refusal, missing members,
  differing dates, changes before the effective date, start-date changes and nonzero quantities.
- 21 form/component cases, including actual quantity/term checkbox submission and invalidation.
- Two populated public workflows cover quantity and term changes through classification,
  preview, approval, application, status/register/causal reports and equal-hash saved replays.
- Scoped backend/frontend types and lint pass.

This completes common-end-date changes for combined unit measures only. Time-elapsed,
cost/hour/progress measures, divergent member terms, changed starts, simultaneous quantity
and term changes, member removal/splitting and combined-contract group reassessment remain
unfinished. No deployment.
