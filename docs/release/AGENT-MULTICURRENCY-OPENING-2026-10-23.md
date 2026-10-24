# Agent opening disclosure across currencies — October 23, 2026

This supersedes the currency and dedicated-agent-report verification gaps in
[the earlier net-opening checkpoint](AGENT-NET-OPENING-2026-10-23.md), within FIFO_WITHIN_POB.

## Behavior

- Transaction and functional views use the original REVENUE leg, excluding supplier payable.
  Functional net income is verified independently; it is not derived by multiplying the
  transaction net amount by a gross-control exchange ratio.
- Later agent delivery can increase net revenue and reduce supplier payable without moving
  contract liability. The new net-posting population includes these two-leg reallocations,
  validates both original components, and avoids counting net legs already matched to a
  gross control entry twice. A real two-delivery scenario previously displayed 10,800 instead
  of the full 18,000; it now retains both the original 10,800 and subsequent 7,200.
- Functional POB opening eligibility retains signed original-source net income separately
  from total net income. Reporting currency translates signed period eligibility changes
  and each period's net income using that period's retained average rate. It does not
  substitute the projected gross balance path for revenue.
- Existing original invoice FX/opening-source checks and gross balance reconciliation remain
  in place. Original source sets are retained without invented per-layer monetary shares.
- Cell explanations distinguish zero-control net/supplier reallocations and expose functional
  net revenue by period before reporting translation.
- New runs use source-set revision 2, with a retained net-posting population and paid-line
  membership. Revision-1 bound transaction reports and pre-feature functional/reporting runs
  keep their original behavior; new reports receive the corrected complete population.

## Verification

47 focused cases pass, covering independent functional net amounts, missing/mixed source rejection,
net-only reallocations without double counting, signed period eligibility, reporting FX,
opening caps and cell explanations.

Four populated database cases pass. The agent fixture uses a seeded reviewed principal/agent judgement and public
commands for billing/delivery/refund. It runs public transaction, functional and reporting
opening-income reports, cell explanation and retained rerun for both original-period
prepayments and current-period receipts. Existing default-policy refund/rollforward checks
and ordinary-contract opening-report reruns are retained.

Scoped Python types, lint and whitespace checks pass. No deployment.

## Remaining boundaries

FIFO_WITHIN_CONTRACT agent net disclosure, cross-owner/cross-entity/acquired original sources,
and mixed opening/non-opening source sets with positive opening remain unfinished. Aggregate
source-set provenance does not authorize proportional net allocation. This change does not
alter postings, declare full agent-report completion, or deploy the application.
