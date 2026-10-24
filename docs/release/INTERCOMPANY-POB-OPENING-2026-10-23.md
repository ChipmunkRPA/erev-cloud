# Cross-entity principal POB opening reports — October 23, 2026

The public opening-liability report now accepts cross-entity principal obligations under
FIFO_WITHIN_POB when the contracting entity's original liability release reconciles to its
intercompany due-to posting. It no longer refuses every positive-opening cross-entity case.

The reader checks original contract/entity/subject/entry identity, verifies the due-to source
chain and exact control amount, and restricts original owners to the selected historical
computation group. Agent splits are not admitted through this principal path. Original
obligation billing/revenue evidence and the single combination cap remain in force.

Transaction and functional readers retain these proofs; reporting currency uses the existing
signed period changes and retained average rates. Drill-down distinguishes contracting and
performing entities, identifies the due-to counterpart, and exposes original source IDs.
This is contracting-entity control attribution, not a second posting of performer revenue.
Saved runs bind the new source evidence and paid-history membership; prior runs without the
new revision retain the earlier behavior. No journal amount or recognition timing changes.

## Necessary verification

40 focused cases and two populated API scenarios pass; scoped lint and Python types pass.
Focused cases cover original identities, wrong entities/roles/amounts, unsupported agents,
source owners outside the selected group, legacy admission and retained cell behavior.
The populated public scenario includes a combined group, cross-entity output progress,
a subsequent progress reversal, both same-obligation and other-member advance receipts,
all three currency views, source drill-down and saved reruns.

The scenario selects the POB policy through a fixture override; this is not a policy approval
workflow test. Its transaction currency equals the contracting entity's functional currency;
reporting translation is exercised. Distinct transaction/functional currency and authenticated
cross-entity locked history still need broader evidence. Native S15 special-source classification,
cross-entity agents, acquired openings and owners outside the selected historical group remain
separate unfinished scope. No deployment and no overall completion claim.
