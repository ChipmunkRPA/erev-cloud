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


## Foreign closed-cutover evidence — October 24, 2026

Revision 18 computes supplementary original FX evidence through an exact closed/locked
acquisition cutover beyond the ordinary posting horizon. Admission requires same-entity
principal obligations with complete OPENING_BALANCES_AT_CUTOVER business-combination
baselines sharing the cutover. It uses the existing FX calculation and published rate inputs;
its posting targets, layer movements and balances are discarded. Only its trace nodes are
merged, atomically requiring every overlapping node to equal the original. Current fiscal
period states remain unchanged; future cutovers are not admitted by this path.

The original functional POB reader can now consume cutover billing and revenue sources:
the USD/EUR fixture retains ASC606 EUR 216,000 billing and EUR 108,000 revenue and IFRS15
EUR 81,000 billing and zero revenue. Subsequent illustrative relief of EUR 9,000 / 6,750
passes the reader against these original traces. Open cutovers keep their existing traces.
All other book output fields match revision 17, and every original trace node is unchanged.
Missing original FX rates leave the supplementary evidence absent; readers retain their
explicit missing-source refusal. Existing native disclosure snapshot outputs are unchanged.

Validation: 53 acquired-opening, FX-source, trace-kernel and POB-reader cases pass, including
closed/open cutovers, missing rates and atomic conflicting-evidence rejection. Scoped lint
and types pass. New bundles select revision 18; old evidence remains immutable. Public
report/approval/lock/rerun integration, acquisition agents/cross-entity cases and mixed-sign
allocations remain open. No migration or deployment.


## Functional acquisition closing snapshots — October 24, 2026

Revision 19 connects the supplementary cutover FX sources to native functional closing
snapshots. Previously revision 18 retained the trace but kept the snapshot on the posting
horizon: a closed cutover showed no functional closing, and an open cutover's established
balance fell into OTHER. At an exact period-end cutover, complete same-entity principal
OPENING_BALANCES_AT_CUTOVER acquisition baselines now retain the original functional
closing and classify it as BUSINESS_COMBINATIONS. Opening and OTHER are zero. The native
obligation eligibility snapshot uses the same original billing/revenue FX sources.

Supplementary FX results are held separately from ordinary producer targets. They are
consumed only for this disclosure scope; posting intents, FX movements, trace nodes and
all non-disclosure book outputs match revision 18. Old revisions remain unchanged. Missing
rates still leave evidence unavailable, without fabricating a functional closing.

Necessary validation: closed and open USD/EUR acquisitions show ASC606 EUR 108,000 and
IFRS15 EUR 81,000 closing liability, equal business-combination increases, no OTHER offset,
and matching per-obligation eligibility. Every balance rollforward reconciles. Acquired,
FX-source, native-snapshot-reader and POB-reader checks pass together (49 tests), with scoped
lint and types. This validates native snapshot production, not the still-open populated
public report/approval/lock/rerun workflow. Mid-period cutovers, acquired agents/cross-entity
and mixed-sign source allocations remain separate gaps. No deployment or reopened period.


## Cutover admission clarification — October 24, 2026

The earlier references to mid-period cutovers as unfinished Reporting work were incorrect.
The native S07-R-01 admission rule explicitly requires the acquisition cutover to be a period
end in every contracting entity's calendar. `s07_onboarding/opening.py` compares the cutover
to the containing period's end and emits ONBOARDING_CUTOVER_NOT_PERIOD_END; computation
then refuses with CV-15 before disclosure calculation. A January 15 acquisition fixture
reproduced this refusal. Its exploratory Reporting change was discarded without publication.

This is an intentional existing input constraint, not evidence that Reporting silently omits
an admitted mid-period acquisition. The current remaining work is public report/close/rerun
integration for admitted period-end acquisitions and special-source attribution. Introducing
mid-period acquisition accounting would require changing the upstream admission and baseline
rules as a separate feature; this checkpoint neither changes nor claims that capability.
