# Common-end-date continuation for combined obligations

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

Revision 31 additionally covers TIME_ELAPSED as described below. Revisions 32–33 add
cost/hour and cost-recovery terms (see the corresponding release checkpoints). Revision 34
adds simultaneous unit quantity and term changes below. Divergent member terms, changed
starts, member removal/splitting and combined-contract group reassessment remain unfinished.
No deployment.

## Time-elapsed continuation

Evidence revision 31 additionally admits the same complete common-end-date TERM_CHANGE for
TIME_ELAPSED combinations. The existing prospective segment measures service under the old
term up to the boundary, preserves earlier segments and recognized revenue, then spreads the
remaining allocation over the new remaining term. Original-component SSP is resolved through
the existing combined remaining-service path. No quantity changes are admitted for this measure.

The wizard offers common-term confirmation for time-elapsed hosts and continues to limit
quantity continuation to unit measures. Native daily-convention checks preserve a complete
pre-change period while changing later service, retain exact trace replay and reject revision-30
replay of the new path. The earlier unit witness now uses a genuinely different end date.

Validation also covers a populated MONTHLY_EVEN series through classification, preview,
approval, application and status/register/causal report replay. For the 108,000 three-year
combination, shortening the end to June 2028 from September 10, 2026 preserves 24,000 for eight completed original months before
the boundary and recognizes 2,709.68 afterward in September (26,709.68 cumulative), under
the existing MONTHLY_EVEN completed-period convention.
Seventeen native cases and 21 frontend cases pass, together with the quantity, unit-term
and time-term public workflows. Scoped types/lint pass. All remaining scope limits above
still apply. No deployment.


## Simultaneous unit quantity and term changes

Evidence revision 34 accepts a TERM_CHANGE that changes original-member quantities along
with the complete common end date for UNITS_DELIVERED and POINT_IN_TIME combinations.
Every original member must still appear exactly once, keep its start date, and participate
in the dated eligibility assessment. Each member must remain positive and retain all units
already transferred. The engine preserves original SSP identities and applies the native
PROSPECTIVE boundary; earlier income is unchanged. Time, cost, hours and cost-recovery
methods still require zero quantity deltas for this term-continuation path.

The wizard admits the same mixed change only for unit-based hosts and explains the distinction.
Evidence revisions through 33 retain their prior refusal, preserving saved replay behavior.

Necessary verification: 28 native reassessment cases, 21 frontend form/component cases and
one populated mixed-change public workflow pass. The public workflow increases transaction
price from 108,000 to 109,000, preserves prior income of 27,000, and verifies status,
modification-register and causal-analysis saved report hashes after approval/application.
Scoped types, lint and diff checks pass. No deployment.
