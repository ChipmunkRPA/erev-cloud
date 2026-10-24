# Agent net opening-income disclosure — October 23, 2026

## Implemented boundary

For new transaction-currency FIFO_WITHIN_POB reports, same-entity agent obligations read
their original gross control entry, net REVENUE leg and supplier counterpart separately.
The original posting and retained computation must reconcile. A gross release of 100 with
net revenue of 20 contributes 20 to revenue recognized, never 100.

The complete original net source set carries original layer-creation dates, including
recursively retained paid history. A nonzero amount qualifies as opening-sourced only when
every source consumes a liability layer created before the reporting range. Asset sources
and in-range sources do not qualify. Mixed categories with positive group opening are
refused rather than apportioned. A zero opening contributes zero, while verified net income
remains visible. Source ownership across original contracts remains unsupported here.

Per-obligation eligibility uses signed net range income and signed opening-source income,
then existing obligation/group liability and consumption caps. The gross control balance path
continues to reconcile independently. The report's cell explanation labels gross opening
control relief explicitly and presents the net total and complete source identities without
per-layer monetary allocations.

Saved reports retain the new source-set evidence and authorized paid-line membership.
Bound reruns compare those facts; saved reports lacking the new evidence key retain their
previous implementation. Engine postings and original revision-8 gross closing facts are
unchanged.

## Necessary verification

- 43 focused cases pass across source classification, net/gross signs, source ownership,
  missing/mixed-source refusal, per-obligation caps and cell explanation.
- Five existing populated public database rollforward cases pass.
- Two existing public opening-report/rerun cases pass (transaction and functional).
- Scoped Python types, lint and whitespace checks pass.
- No deployment.

The database cases above verify existing report compatibility, not a newly constructed agent
public-API lifecycle. That dedicated end-to-end agent scenario is still outstanding; do not
treat this checkpoint as complete agent reporting or production certification.

## Remaining work

Functional/reporting-currency agent opening income, FIFO_WITHIN_CONTRACT agent net disclosure,
cross-owner/cross-entity/acquired sources, and mixed opening/non-opening net allocation remain
unfinished. A complete source set does not determine an individual source's monetary share.
No missing net allocation is derived from gross proportions.
