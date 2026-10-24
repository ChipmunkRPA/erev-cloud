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


## Cross-entity principal API verification — October 24, 2026

The public acquisition/report path also passes when the EUR contract belongs to AVM-US and a
separate USD entity performs its obligation on the same calendar. The scenario includes both
entities in the report selection and has complete intercompany account mappings. Both an open
cutover and an actually closed/locked August cutover pass subsequent September delivery,
transaction/functional/reporting views, acquisition cell explanations and retained reruns.
The original 10,000 EUR liability is shown once; later contracting-entity relief is 5,000 EUR /
5,500 USD (4,954.95 EUR reporting), matching the retained layer basis.

This corrects the earlier blanket public cross-entity limitation; no new calculation or reporting
algorithm was needed for this scenario. The first exploratory zero-revenue result came from
missing intercompany account mappings in the fixture, which prevented the expected posting.

Boundaries: both entities use USD functional currency and the same calendar; only the contracting
entity's August is locked. The public opening report uses the existing fixture-selected POB
consumption policy after lock. This does not establish native S15 cross-entity POB snapshot
coverage under a published POB policy, different functional currencies/calendars, acquired
agents, mixed acquired/existing groups, or recomputed acquisition baselines. Opening acquisition
facts are fixture-appended, not a public acquisition-entry workflow. Two targeted database
scenarios pass; no deployment or full-system readiness claim.


## Native cross-entity acquisition control sources — October 24, 2026

Evidence revision 20 connects original principal acquisition baselines and FX control sources
when the contracting and performing entities differ. The closed-cutover FX evidence pass can
retain the contracting entity's original sources; transaction and functional POB disclosures
and closing eligibility use those sources at cutover and in subsequent periods. Closing evidence
explicitly labels CONTRACTING_ENTITY_CONTROL and retains the performing entity. The resulting
liability is the original obligation eligibility before the combination cap, not a second
recognition of performing-entity income.

Admission still requires BUSINESS_COMBINATION, OPENING_BALANCES_AT_CUTOVER and principal status.
Complete baselines, consistent cutover dates, original billing attribution, currency and amount
reconciliation continue to be checked. Existing stored input revisions preserve prior behavior.
No journal, balance, schedule or FX-layer amounts are changed, and closed periods are not posted.

Native verification covers ASC606 and IFRS15 at the closed cutover and the following month,
USD transaction with USD or EUR contracting functional currency and a USD performing entity,
FIFO_WITHIN_POB, original trace formulas, and unchanged financial output. Twenty focused cases
pass, including existing same-entity acquisition cases and the earlier revision's refusal.
Scoped lint and types pass. Two public open/locked cross-entity scenarios also pass.
Different-calendar and broader multiple-member histories, mixed acquired/existing populations,
agents and recomputed baselines remain unfinished; no overall readiness claim or deployment.


## October 24: mixed-group closing eligibility

Evidence revision 24 allows original POB closing eligibility for principal groups containing
ordinary obligations alongside acquired obligations with a common admitted cutover. Transaction
capture seeds only acquired baselines and excludes pre-cutover flows only for those obligations.
Ordinary members retain their earlier billing/revenue, credit memos and negative revenue. A shared
billing source can therefore contribute its ordinary share without duplicating its acquired share.

Functional capture retains the full original billing/cutover-correction population and reconciles
transaction amounts against original FX attribution and revenue targets before accepting functional
amounts. Missing FX source records remain unavailable. Prior revisions retain their original result,
and a full native single-acquisition comparison proves revision 23/24 book outputs unchanged.
The closing witness covers baseline plus post-cutover activity, ordinary prior history, returns,
shared documents, foreign sources and missing-source refusal. All 18 acquired-closing cases and
scoped lint/types pass. The mixed closing witness supplies original flow/FX records to capture;
a full native mixed-group public report path is still to be verified.

This does not complete mixed acquisition rollforward increases. `acquisition_flows.read` still
requires explicit acquisition attribution before relaxing its population guard, and closed foreign
mixed-group cutovers may still lack supplementary FX evidence. Agents, different acquisition dates,
and recomputed baselines remain open. No deployment.


## October 24: mixed transaction rollforward follows original event order

Native evidence revision 25 removes the group-wide acquisition cutoff for mixed transaction
rollforwards. Ordinary member activity remains in billing/revenue captions. Each acquired member's
original cutover event inserts its admitted net baseline at that event position, so acquisition
can settle an existing asset or consume an existing liability before creating a new position.
BUSINESS_COMBINATIONS records that change in presented balances rather than forcing a gross
liability increase and leaving ordinary business in OTHER. Pre-cutover acquired activity is
excluded by original obligation; ordinary members' activity and memo causes remain included.

Both FIFO_WITHIN_CONTRACT and FIFO_WITHIN_POB paths use these histories; POB opening consumption
seeds acquired baselines only when they precede the period. Authenticated frozen opening inputs
retain priority. A native two-contract witness (including escaped/colliding identities) covers
ordinary invoices before/on cutover, acquired net assets/liabilities, both FIFO methods and a
subsequent-period opening-consumption check. It proves no unexplained OTHER in those cases and
unchanged posting intents and FX layer movements. The 44 focused mixed/acquired/rollforward cases
pass with scoped lint/types. Two old functional-capture test doubles now supply their existing
acquisition_functional_cutover field explicitly.

Foreign functional mixed rollforwards still use their prior path and require further implementation.
The public report builder also still needs explicit retained group/member acquisition-change sources;
its population guard has not been removed. No claim of a complete mixed-acquisition report path,
and no deployment.


## October 24: mixed functional rollforward uses original FX sources

Evidence revision 26 classifies acquired cutover control sources from their original obligation
owners and billing attribution. Functional rollforwards retain ordinary activity and put acquired
layer creation, consumption and settlement in BUSINESS_COMBINATIONS; remeasurement remains in FX.
Classification follows the triggering source, including when acquisition settles an ordinary
member's asset, rather than mistaking the original layer owner for the acquisition owner.

Eight native foreign-currency cases cover ordinary invoices before/on cutover, acquired net
assets/liabilities, both FIFO policies, different average/spot rates and subsequent-period opening
consumption. They reconcile closing balances with no unexplained OTHER and prove unchanged posting
intents and FX layer movements. All 52 focused mixed/acquired/rollforward checks pass; scoped lint
and types pass. Earlier revisions retain their prior disclosure behavior.

This path requires complete original cutover source ownership. Earlier acquired FX history and
a single net source mixing acquired and ordinary owners remain explicitly unavailable rather than
receiving fabricated allocations. Closed mixed foreign cutovers may still lack supplementary FX
evidence. Public report integration still requires retained group/member acquisition-change sources;
its population guard remains in place. The full mixed-acquisition reporting path is unfinished.
No deployment.


## October 24: retain signed mixed acquisition source contributions

Evidence revision 27 adds optional acquisition_sources to native mixed-group disclosure rows.
Transaction entries retain the original cutover event, effective date, original obligation subjects,
admitted baseline and the signed change in each presented balance. Foreign entries retain the
original FX source, layer, movement kind, trace node and rate key alongside their signed change.
The engine checks these contributions against every BUSINESS_COMBINATIONS balance caption.
Amounts are integer minor units in the enclosing row's currency; source order is original execution
order. These are group presentation changes, not an invented allocation to individual members.

Eight native foreign-currency witnesses check both transaction and functional source totals,
original event/FX trace identities, and exact revision 26/27 book equality after removing the new
evidence field. The 52 focused mixed/acquired/rollforward checks and scoped lint/types pass.
Historical revisions omit the field and retain their prior output. No journal calculation changes.

Public report integration remains open: its existing acquisition path admits only positive carrying
balances, and member reporting needs explicit signed contributions consistent with group netting.
This change retains the original group evidence needed for that integration; it does not remove the
public guard or claim that member allocation is complete. No deployment.


## October 24: signed acquisition changes in the report path

The report path now accepts explicit acquisition_changes separately from legacy positive
acquisition_balances. Signed changes adjust the exact asset caption or consume liability layers
without recording revenue relief. Unnamed transaction changes consume FIFO; a named functional
liability reduction requires its exact existing layer. New acquired liabilities enter the NEW
bucket, preserving range-opening provenance. Missing/ambiguous layers, overdrawn assets or
liabilities, duplicate roles, nonfinite amounts and mixed legacy/signed payloads are rejected.
Monthly reporting paths preserve these changes and subsequent original-opening revenue relief.

All 42 contract-rollforward unit cases pass, including asset settlement, opening consumption,
named acquired layers, cross-month provenance and invalid inputs. Scoped lint/types pass. This
is the signed path consumer needed by revision 27 native acquisition evidence. The public source
reader still uses its existing guarded legacy path: member ownership and group-to-member transfer
evidence must be connected before admitting mixed-group sources. No public completeness claim,
no deployment.
