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


## Original cutover billing trace — October 24, 2026

A closed cutover beyond the posting horizon had its original revenue baseline but no
period-keyed `billed_cum` trace node. An original-version POB reader therefore could not
read the transaction opening from that trace, even though the native closing snapshot
retained its liability. Evidence revision 17 now emits the existing billing formula at
an exact period-end BUSINESS_COMBINATION cutover under OPENING_BALANCES_AT_CUTOVER.
It adds evidence only, with no new billing target or posting period. If that period is
already measured, its existing node is retained without duplication. New API computation
bundles select revision 17; older retained bundles keep their prior evidence behavior.

The native engine-to-POB-reader regression covers ASC606 (240,000 billing, 120,000 revenue,
10,000 subsequent relief) and IFRS15 (90,000 billing, zero revenue, 7,500 relief), with both
open and closed cutovers. Original event references and formulas re-evaluate; posting
intents, FX layer movements and disclosure rollforwards match revision 16 exactly. The
open-cutover trace remains identical. The acquired-opening, original FX attribution and
POB-reader suites pass together (43 cases); scoped Python lint/types pass.

This closes the missing transaction billing trace. It does not establish the full public
acquired-report/approval/lock/rerun journey or complete foreign closed-cutover revenue
sources. Existing authenticated native lock snapshots retain their separate path.
No database migration, historical evidence rewrite, reopened period or deployment.
