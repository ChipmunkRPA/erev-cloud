# Acquired member current liability — October 24, 2026

Evidence revision 59 extends the owner-selected carrying-value allocation to principal
business-combination obligations with original OPENING_BALANCES_AT_CUTOVER baselines,
including groups containing ordinary members. Transaction current liabilities use transaction
member carrying weights. Functional current liabilities retain the existing historical-layer
release policy and use functional member carrying weights. Existing source-total reconciliation,
minor-unit allocation and per-member caps remain enforced. Noncurrent is total less current.

The new dated member nodes feed the existing balance report projection. This is a presentation
change: journal intents, revenue schedules and FX layer movements remain unchanged. Older
input revisions retain their prior results. RECOMPUTE_FROM_INCEPTION, acquired agents and
non-acquisition openings remain outside this extension; no missing original evidence is inferred.

Validation: 32 focused mixed-acquisition and current-liability cases pass. The eight new
cases cover all-acquired/mixed groups, transaction/foreign currencies, FIFO/PRO_RATA, unequal
member balances and partial current amounts over extended terms. An additional run of those
eight cases verifies the stored transaction balance and functional report projection. Trace
replay, group totals, proportional allocation and unchanged postings are checked. Scoped Ruff,
mypy and diff checks pass. No deployment.
