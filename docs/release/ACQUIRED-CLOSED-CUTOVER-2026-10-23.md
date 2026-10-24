# Acquisition closing at a closed cutover — October 23, 2026

A closed acquisition period can fall after the last postable calculation period. Stage 10 then
has no presented group balance at the cutover, while the original acquired baseline exists.
The native transaction rollforward previously treated this missing target as zero and offset
the entire BUSINESS_COMBINATIONS amount through OTHER.

Evidence revision 15 now uses the complete original acquisition baseline when the acquisition
cutover is exactly the reporting period end and no presented balance targets exist. Existing
targets retain priority, including genuine zero balances. The fallback requires same-entity
principal obligations with complete matching cutovers; debit positions also require original
asset-caption classification. It does not extrapolate a cutover amount to a later date, create
journals, reopen a period or replace an authenticated frozen opening.

32 focused cases pass. Four complete engine scenarios cover both FIFO policies and both
onboarding methods in ASC606 and IFRS15: acquired liability is 120,000 and 90,000 respectively,
closing equals BUSINESS_COMBINATIONS, OTHER is zero, and no posting is created. Six existing
open-period engine scenarios produce identical books under revisions 14 and 15. Native
snapshot compatibility and scoped lint/types pass. Older evidence revisions retain their outputs.

This fixes native transaction group closing at an exact closed cutover. It does not complete
foreign-functional acquisition sources, later-period recompute-baseline POB eligibility, acquired
agent/cross-entity attribution or the broader public acquired-report and lock-history workflow.
No deployment or migration-to-live work.
