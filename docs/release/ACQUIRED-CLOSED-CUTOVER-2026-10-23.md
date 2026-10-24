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


## Original acquisition method — October 24, 2026

Public-path preparation exposed a bundle-input gap: only legacy migration pinned
`onboarding.method`; an acquisition opening otherwise retained the registry default of
`RECOMPUTE_FROM_INCEPTION`. Opening event schema version 3 now accepts an explicit
`onboarding_method`: `OPENING_BALANCES_AT_CUTOVER` or `RECOMPUTE_FROM_INCEPTION`.
The bundle builder resolves that value at contract scope for both books, citing the original
opening event. Conflicting original selections are refused. Legacy migration keeps its
fixed opening-balance method and rejects an explicit recompute selection.

Absent selections preserve historical behavior. Identity upcasts and omission of the new
unset field preserve the prior normalized opening JSON and stored event identity. This
adds a backend event capability; it does not add an acquisition submission screen or claim
the full public acquisition report/close/rerun workflow is complete.

Necessary validation: 15 focused payload, schema, bundle-policy and architecture checks
pass. The actual book-policy assembly and engine resolver honor each selection for both
books, preserve other contracts' defaults, and retain the original event source. Scoped
production types and lint pass; generated OpenAPI artifacts are unchanged.


## Public acquired report integration and remaining lock blocker — October 24, 2026

A database-backed acquisition now exercises original schema-3 opening input, persisted
computation, the public opening-liability report job, JSON data retrieval and retained rerun.
The EUR contract has EUR 10,000 opening liability / USD 11,000 historical carrying value.
Its fixed-price RTI progress is EUR 10,000 realized divided by EUR 20,000 stated price;
September recognizes half of the remaining EUR 10,000 allocation: EUR 5,000 / USD 5,500.
Both transaction and functional reports reproduce these values and reruns reproduce all rows.
The auxiliary setup contract is billed, avoiding an unrelated pending asset FX close pass.
Only POL-126 selection is fixture-resolved to FIFO_WITHIN_POB; acquisition calculation and
report input are not replaced. The opening event remains fixture-appended, not a public
acquisition-entry screen. This verifies the open-period, post-acquisition path only.

A separate real close run succeeded for August, but approval of the August lock failed with
`Transaction opening relief requires a reconciled group path.` The public rollforward path
has no acquisition-source flow family: its documents/posted entries do not represent the
acquired opening balances as BUSINESS_COMBINATIONS. Native revision-19 closing snapshots
therefore do not yet complete the public lock workflow. This is a confirmed implementation
blocker, not a missing sign-off or deployment prerequisite. Fix original acquisition-period
flows and their retained evidence in the public transaction/functional/reporting paths;
then recheck lock approval, September income, frozen opening reads and bound reruns.
Do not suppress OTHER, weaken reconciliation, or claim this closed-period path is complete.


## Public acquisition-period flows and locked continuation — October 24, 2026

The blocker above is fixed for admitted same-entity principal acquisitions using
OPENING_BALANCES_AT_CUTOVER. A new acquisition flow reads original input/output files from
the selected contract version, verifies metadata, digests and computation identity, confirms
that the original engine admitted the opening, and takes each carrying caption from its
cutover-period trace. It adds those balances to BUSINESS_COMBINATIONS, independently of
billing and revenue. New acquisition liability layers are not range-opening liability.
The event key, original hashes, trace nodes, currency and amounts are retained and checked
on rerun. Historical bindings without the new evidence key preserve their previous behavior.
Mixed existing/acquired groups, acquired agents and cross-entity attribution still refuse;
recomputed-baseline acquisitions are not covered by this new cutover-source path.

Two further source-reader defects exposed by the real lock flow are fixed: select the
transaction disclosure pack explicitly among the three frozen currency variants; and retain
authenticated all-zero original rows omitted by the locked balance report. Missing nonzero
balances continue to refuse. Neither fix relaxes a reconciliation or fabricates a balance.

Necessary validation: the database scenario now passes in both open and locked variants.
It performs an actual August close, journal workflow and lock approval, approves September
income, then reads August rollforwards and September opening-liability reports in transaction,
functional and reporting currencies. August shows EUR 10,000 / USD 11,000 acquisition increase,
zero unexplained liability OTHER, and reporting-currency translation separately. September
shows EUR 5,000 / USD 5,500 revenue relief; reporting EUR uses the retained closing/average
rates (opening EUR 9,954.75, relief EUR 4,954.95). Every report's retained rerun reproduces
all rows. As with the existing close fixtures, preceding empty periods and reconciliation
review rows are fixture-prepared; opening input is fixture-appended and POL-126 is selected
by the fixture. This does not establish an acquisition-entry UI or real-business migration.
Focused path/source checks, scoped types and lint also pass. No deployment or posting change.


## Acquisition cell explanations — October 24, 2026

The public contract-balance rollforward now exposes explanations for BUSINESS_COMBINATIONS
summary cells and the by-contract business_combinations amount. New report bindings retain
each member's actual presented acquisition amount beside the original event, computation
hashes and trace nodes. Reporting-currency explanations retain the presented amount and its
original functional amount, with the selected period rates; they do not retranslate using
current configuration. Contributions must reconcile exactly to each saved cell.

The explanation API returns internal contract-history and original trace links. The existing
entity-scope filter now recognizes acquisition contributions, naming sources only within the
reader's entity scope and aggregating amounts outside it. Historical bindings without cell
evidence refuse explanation rather than inventing it. Missing original trace IDs and
inconsistent contribution totals also refuse. Internal close calculations without a report
source collector do not create cell evidence or alter lock behavior.

The viewer enables only supported acquisition cells, including keyboard activation guards;
other rollforward lines keep their prior display. The public open and locked scenarios verify
summary/member explanations in all three currency views alongside the existing report/rerun
checks. Two source-retention checks and six focused UI checks pass, as do scoped backend types,
frontend typechecking and lint. No journal changes or deployment. Broader acquired-history
and mixed-member attribution limitations above remain open.
