# Cross-performer agents with contracting-entity revenue

The existing `ic.revenue_entity=CONTRACTING_ENTITY` policy could select JET-02 for an agent
performed by another entity, while stage 10 still restricted gross relief to same-entity
performance. Net revenue was posted but the supplier share remained in contract liability.

Current bundles use evidence revision 21. Under the retained contracting-entity election,
stage 10 now computes gross liability relief and the supplier share for these agents. Targets
belong to the contracting calendar; stage 13 matches gross relief by period-end date rather
than a performing entity's period key. Original inputs below revision 21 retain their previous
interpretation. The supported calendar path requires aligned period ends; a missing counterpart
end refuses instead of projecting an unsupported supplier amount.

Opening-liability Reporting now reads the original verified computation's revenue-entity policy
before admitting a cross-performer agent. It still verifies original net/supplier components,
gross control conservation, complete source sets, layer dates and historical owners. Contract
FIFO and POB FIFO use the net income cap; no per-layer net amounts are fabricated. POB evidence
and cell explanations identify the original contracting revenue entity. A separate retained
report marker preserves old saved-run admission. The performing-entity revenue election is not
admitted by this change, including through the existing zero-opening report path.

Necessary verification: the populated public-command scenario uses two advance billing layers,
two deliveries, a different USD performer, GBP contracting functional currency, and the existing
contracting-revenue policy. It checks original net/supplier proofs, transaction/functional/reporting
reports, contract and POB FIFO, and exact saved reruns. Focused cases cover legacy admission,
policy/revision gates, gross relief across different period keys, and net POB caps. The existing
native agent gross-relief cases are included. This is not full cross-entity-agent support:
performing-entity revenue, nonaligned calendars and acquired agents remain unfinished.

Validation completed: the populated scenario passes, as do 60 focused report cases and eight
existing native agent cases. Scoped lint and Python types pass.

No deployment. Changes to supplier payable and contract liability are intentional; this is not
merely a presentation change, and it does not change the agent's retained transaction revenue.
